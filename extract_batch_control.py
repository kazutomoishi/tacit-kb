#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_batch_control.py  —  対照条件（理論なしプロンプト）でカードを生成
  extract_batch.py との差分は SYSTEM のみ。出力先は cards(source='llm_control')。
  同じ tacit_kb.db に格納されるので、source 列で直接比較できる。

  使い方:
      python extract_batch_control.py --limit 100    # llmカードがある論文から100本
      python extract_batch_control.py                # 全て

  注意: 既に llm_control カードがある論文はスキップ（再実行可）。
"""
import sqlite3, os, json, sys, time, re
import anthropic
from anthropic.types.messages.batch_create_params import Request
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming

DB = "tacit_kb.db"
MODEL = "claude-sonnet-5"
SOURCE = "llm_control"

# ---------------------------------------------------------------------------
# 対照プロンプト: 出力形式・フィールド・件数上限・言語は本条件と完全に同一。
# 削除したのは (1) 認知心理学の枠組み3行 (2)「判断基準の圧縮を最優先」の指示
#              (3) 「暗黙知抽出エンジン」という理論的役割付与
# ---------------------------------------------------------------------------
SYSTEM = """あなたは科学論文のMethods本文を読み、曖昧で解釈の幅がある表現を見つけて、若手研究者向けに補足説明を付けるアシスタントです。

各曖昧表現につき日本語で生成:
- term(原文の語、英語のまま) / why_vague(なぜ曖昧か) / body_sense(身体的感覚) /
  concrete_steps(具体的な目安) / failure_mode(欠けると何が起きるか) /
  criticality("高重要度"|"中重要度"|"低重要度")

出力は厳密なJSON配列のみ。前置き・マークダウン禁止。最大5件。
[{"term":"","why_vague":"","body_sense":"","concrete_steps":"","failure_mode":"","criticality":"高重要度"}]"""


def build_requests(c, limit):
    """本条件(llm)のカードを持つ論文だけを対象にする＝同一集合での比較を担保。"""
    done = {r[0] for r in c.execute(
        "SELECT DISTINCT paper_id FROM cards WHERE source=?", (SOURCE,))}
    papers = c.execute("""SELECT DISTINCT p.id
                          FROM papers p JOIN cards k ON k.paper_id=p.id
                          WHERE k.source='llm'
                          ORDER BY p.n_candidates DESC""").fetchall()
    reqs = []
    for (pid,) in papers:
        if pid in done:
            continue
        snips = [r[0] for r in c.execute(
            "SELECT snippet FROM candidate_terms WHERE paper_id=? LIMIT 25", (pid,))]
        if not snips:
            continue
        reqs.append(Request(
            custom_id=f"paper-{pid}",
            params=MessageCreateParamsNonStreaming(
                model=MODEL, max_tokens=4000, system=SYSTEM,
                messages=[{"role": "user",
                           "content": "次の手順抜粋から曖昧な表現を抽出しJSON配列で返してください:\n\n" + "\n".join(snips)}],
            ),
        ))
        if limit and len(reqs) >= limit:
            break
    return reqs


def parse_cards(text):
    s, e = text.find("["), text.rfind("]")
    if s != -1 and e != -1:
        try:
            return json.loads(text[s:e + 1])
        except json.JSONDecodeError:
            pass
    cards = []
    for m in re.finditer(r"\{[^{}]*\}", text, re.S):
        try:
            cards.append(json.loads(m.group(0)))
        except json.JSONDecodeError:
            continue
    return cards


def save_result(c, pid, text):
    n = 0
    for cd in parse_cards(text)[:5]:
        if not isinstance(cd, dict):
            continue
        c.execute("""INSERT INTO cards(paper_id,term,why_vague,body_sense,concrete_steps,
                     failure_mode,criticality,source) VALUES(?,?,?,?,?,?,?,?)""",
                  (pid, cd.get("term", ""), cd.get("why_vague", ""), cd.get("body_sense", ""),
                   cd.get("concrete_steps", ""), cd.get("failure_mode", ""),
                   cd.get("criticality", "中重要度"), SOURCE))
        n += 1
    return n


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("環境変数 ANTHROPIC_API_KEY を設定してください。")
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    reqs = build_requests(c, limit)
    if not reqs:
        sys.exit("処理対象がありません（すべて対照条件済み）。")
    print(f"対照条件バッチ送信: {len(reqs)} 論文ぶん  (source='{SOURCE}')")

    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=reqs)
    print(f"batch id: {batch.id}")

    while True:
        b = client.messages.batches.retrieve(batch.id)
        if b.processing_status == "ended":
            break
        rc = b.request_counts
        print(f"  processing={rc.processing} succeeded={rc.succeeded} errored={rc.errored}")
        time.sleep(30)

    saved_papers = saved_cards = skipped = errors = 0
    for res in client.messages.batches.results(batch.id):
        pid = int(res.custom_id.split("-")[1])
        if res.result.type != "succeeded":
            errors += 1
            continue
        text = "".join(blk.text for blk in res.result.message.content if blk.type == "text")
        n = save_result(c, pid, text)
        if n == 0:
            skipped += 1
            print(f"  paper-{pid}: JSON解析できずスキップ")
        else:
            saved_papers += 1
            saved_cards += n
    conn.commit()
    conn.close()
    print(f"\n完了: {saved_papers}論文 / {saved_cards}カード保存。スキップ {skipped}件、失敗 {errors}件。")
    print("次に  python compare_theory.py  を実行してください。")


if __name__ == "__main__":
    main()
