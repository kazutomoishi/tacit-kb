#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect.py  —  論文の収集だけを行うスタンドアロン版
  やること: キーワード検索 → PMCID取得 → 全文取得 → SQLite(tacit_kb.db)へ格納
  （LLMもAPIキーも不要。Python標準ライブラリのみ。）

  使い方:
      python3 collect.py            # 既定100本を収集
      python3 collect.py 30         # 30本だけ収集
      python3 collect.py 500        # 500本だけ収集、引数を変えれば上限も変わる。
      python collect.py [数字]　     # 数字に収集する論文の上限値をいれる。
  出力: tacit_kb.db の papers / candidate_terms テーブル

  ※ candidate_terms（暗黙知候補の自動検出）も同時に作ります。
     本文だけ欲しい場合は detect() 呼び出しをコメントアウトしてください。
"""
import urllib.request, urllib.parse, json, re, time, sqlite3, sys

UA = {"User-Agent": "tacit-kb/1.0 (research; protocol mining)"}
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
BIOC = "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{}/unicode"
DB = "tacit_kb.db"

# 分野を散らした検索キーワード（自由に増減可）
QUERIES = [
    "protein purification protocol", "cell culture protocol", "RNA extraction protocol",
    "immunostaining protocol", "CRISPR Cas9 protocol", "bacterial transformation protocol",
    "western blot protocol", "tissue fixation protocol", "organoid culture protocol",
    "flow cytometry staining protocol", "chromatin immunoprecipitation protocol",
    "protein crystallization protocol", "yeast transformation protocol",
    "zebrafish microinjection protocol", "primary neuron culture protocol",
]

# 暗黙知が漏れ出やすい語彙（候補検出用の軽量ヒューリスティック）
PATTERNS = [
    ("manner",    r"\b(gently|vigorously|slowly|rapidly|carefully|thoroughly|briefly|lightly|firmly|dropwise|swiftly|delicately)\b"),
    ("thermal",   r"\b(on ice|ice[- ]cold|keep (?:it )?(?:cold|on ice)|do not freeze|pre[- ]?warm|warm to|chilled|kept cold)\b"),
    ("handling",  r"\b(do not (?:perturb|disturb)|without disturbing|avoid (?:bubbles|frothing|foaming)|take care not to|being careful not to|so as not to)\b"),
    ("endpoint",  r"\b(until (?:clear|translucent|dissolved|homog[e]?nous|homogeneous|no longer|the .{0,30}? (?:is|are|becomes?|turns?))|without clumps|no clumps|until .{0,25}? is reached)\b"),
    ("adaptive",  r"\b(if necessary|as needed|as required|if incomplete|more .{0,20}? if|shorter .{0,20}? if|repeat .{0,30}? times|several times|\d+\s*(?:to|-|\u2013)\s*\d+\s*times|if .{0,30}? (?:too (?:quickly|fast|slowly)|warms? up))\b"),
    ("vague_qty", r"\b(approximately|around |about ~|a few |sufficient|enough to|small amount|some (?:of the)?|a small volume)\b"),
]
PATTERNS = [(c, re.compile(p, re.I)) for c, p in PATTERNS]
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def get(url, timeout=45):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read().decode("utf-8", "ignore")


def detect(text):
    out, seen = [], set()
    for sent in SENT.split(text):
        s = sent.strip()
        if not (15 <= len(s) <= 400):
            continue
        for cat, rx in PATTERNS:
            m = rx.search(s)
            if m:
                term = m.group(0).strip().lower()
                key = (cat, term, s[:60])
                if key not in seen:
                    seen.add(key)
                    out.append({"category": cat, "term": term, "snippet": s})
                break
    return out


def epmc_search(query, page_size=25):
    q = urllib.parse.quote(f"{query} AND OPEN_ACCESS:Y AND IN_EPMC:Y AND HAS_FT:Y")
    url = f"{EPMC}?query={q}&format=json&pageSize={page_size}&resultType=core"
    try:
        return json.loads(get(url)).get("resultList", {}).get("result", [])
    except Exception as e:
        print("  search err", e)
        return []


def fetch_body(pmcid):
    try:
        d = json.loads(get(BIOC.format(pmcid)))
        doc = d[0]["documents"][0]
        lic = doc["infons"].get("license", "")
        paras = [p["text"] for p in doc["passages"]
                 if p["infons"].get("type") == "paragraph" and p.get("text")]
        return lic, "\n".join(paras)
    except Exception:
        return None, None


def main(target=100):
    # 1) 検索してPMCID一覧＋メタデータを集める
    rows = {}
    for query in QUERIES:
        print("search:", query)
        for r in epmc_search(query):
            pmcid = r.get("pmcid")
            if pmcid and pmcid not in rows and r.get("isOpenAccess") == "Y":
                rows[pmcid] = r
        time.sleep(0.4)
    print(f"candidate pool: {len(rows)} unique OA papers")

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.executescript("""
    DROP TABLE IF EXISTS papers; DROP TABLE IF EXISTS candidate_terms;
    CREATE TABLE papers(
      id INTEGER PRIMARY KEY, pmcid TEXT UNIQUE, pmid TEXT, doi TEXT, title TEXT,
      authors TEXT, journal TEXT, year TEXT, license TEXT,
      n_candidates INTEGER, body_text TEXT);
    CREATE TABLE candidate_terms(
      id INTEGER PRIMARY KEY, paper_id INTEGER, category TEXT, term TEXT, snippet TEXT,
      FOREIGN KEY(paper_id) REFERENCES papers(id));
    """)

    # 2) 各PMCIDの全文を取得して格納（＋候補検出）
    kept = 0
    for pmcid, r in rows.items():
        if kept >= target:
            break
        lic, body = fetch_body(pmcid)
        time.sleep(0.25)
        if not body or len(body) < 1500:
            continue
        cands = detect(body[:80000])          # ← 本文だけ欲しければこの行を消す
        if len(cands) < 3:                     #   （その場合この条件も外す）
            continue
        ji = r.get("journalInfo") or {}
        journal = r.get("journalTitle") or (ji.get("journal") or {}).get("title", "")
        c.execute("""INSERT OR IGNORE INTO papers
            (pmcid,pmid,doi,title,authors,journal,year,license,n_candidates,body_text)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (pmcid, r.get("pmid", ""), r.get("doi", ""), r.get("title", ""),
             r.get("authorString", ""), journal, str(r.get("pubYear", "")),
             lic, len(cands), body[:80000]))
        pid = c.lastrowid
        for cd in cands[:40]:
            c.execute("INSERT INTO candidate_terms(paper_id,category,term,snippet) VALUES(?,?,?,?)",
                      (pid, cd["category"], cd["term"], cd["snippet"]))
        kept += 1
        if kept % 10 == 0:
            print(f"  kept {kept}/{target}")
        conn.commit()

    print(f"DONE: {kept} papers stored in {DB}")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 100)
