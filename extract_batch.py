#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_batch.py  —  Batch APIで暗黙知カードを一括生成（標準APIより50%安い）
  事前準備:
      pip install anthropic
      $env:ANTHROPIC_API_KEY="sk-ant-..."   (PowerShell) #ここにAPIキーをいれる。
  使い方:
      python extract_batch.py --limit 5     # まず5本でテスト送信
      python extract_batch.py               # 候補のある全論文を一括処理
  動作: 1論文=1リクエストとしてバッチ送信 → 完了まで待機 → cards(source='llm')へ保存
        既にllmカードがある論文はスキップ（再実行可）。custom_id は paper_id。
        JSONが崩れた結果は1本ずつ復旧を試み、ダメな論文だけスキップして継続。
"""
import sqlite3, os, json, sys, time, re
import anthropic
from anthropic.types.messages.batch_create_params import Request
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming

DB = "tacit_kb.db"
MODEL = "claude-sonnet-5"   # 安さ優先なら "claude-haiku-4-5-20251001"

SYSTEM = """あなたは認知心理学に基づく「暗黙知抽出エンジン」です。科学論文のMethods本文から、熟練研究者が体得し言語化されないまま圧縮・省略した実践的暗黙知の痕跡＝曖昧表現を特定し、若手向けの暗黙知カードに展開します。

理論的枠組み（必ず準拠）:
- 二重過程理論: 熟練動作はSystem1（自動・無意識）化され、System2（言語）への変換時に圧縮される。
- スキーマ理論: ベテランは精製スキーマ共有読者を前提に前提知識を省略する。
- SECIモデル（表出化）: 曖昧表現を「読める知識・実行できる知識」に逆変換する。

最重要の観点: 動作が書いてあっても、「どうやってその状態だと判断するか」という判断のしきい値が省略されていることが多い。この『判断基準の圧縮』を最優先で抽出する。

各曖昧表現につき日本語で生成:
- term(原文の語、英語のまま) / why_vague(なぜ曖昧か) / body_sense(身体的感覚) /
  concrete_steps(形式知へ逆変換した推定の目安) / failure_mode(欠けると何が起きるか) /
  criticality("高重要度"|"中重要度"|"低重要度")

出力は厳密なJSON配列のみ。前置き・マークダウン禁止。最大5件。
[{"term":"","why_vague":"","body_sense":"","concrete_steps":"","failure_mode":"","criticality":"高重要度"}]"""


def build_requests(c, limit):
    done = {r[0] for r in c.execute("SELECT DISTINCT paper_id FROM cards WHERE source='llm'")}
    papers = c.execute("SELECT id,title FROM papers ORDER BY n_candidates DESC").fetchall()
    reqs = []
    for pid, title in papers:
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
                           "content": "次の手順抜粋から暗黙知の痕跡を抽出しJSON配列で返してください:\n\n" + "\n".join(snips)}],
            ),
        ))
        if limit and len(reqs) >= limit:
            break
    return reqs


def parse_cards(text):
    # まず素直にJSON配列を取り出す
    s, e = text.find("["), text.rfind("]")
    if s != -1 and e != -1:
        try:
            return json.loads(text[s:e + 1])
        except json.JSONDecodeError:
            pass
    # 崩れている場合: {...} を1個ずつ拾って、読めたものだけ採用
    cards = []
    for m in re.finditer(r"\{[^{}]*\}", text, re.S):
        try:
            cards.append(json.loads(m.group(0)))
        except json.JSONDecodeError:
            continue
    return cards


def save_result(c, pid, text):
    cards = parse_cards(text)
    n = 0
    for cd in cards[:5]:
        if not isinstance(cd, dict):
            continue
        c.execute("""INSERT INTO cards(paper_id,term,why_vague,body_sense,concrete_steps,
                     failure_mode,criticality,source) VALUES(?,?,?,?,?,?,?, 'llm')""",
                  (pid, cd.get("term", ""), cd.get("why_vague", ""), cd.get("body_sense", ""),
                   cd.get("concrete_steps", ""), cd.get("failure_mode", ""),
                   cd.get("criticality", "中重要度")))
        n += 1
    return n


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("環境変数 ANTHROPIC_API_KEY を設定してください。")
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS cards(
        id INTEGER PRIMARY KEY, paper_id INTEGER, term TEXT, why_vague TEXT, body_sense TEXT,
        concrete_steps TEXT, failure_mode TEXT, criticality TEXT, source TEXT)""")
    conn.commit()

    reqs = build_requests(c, limit)
    if not reqs:
        sys.exit("処理対象がありません（すべてllm済み、または候補なし）。")
    print(f"バッチ送信: {len(reqs)} 論文ぶん")

    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=reqs)
    print(f"batch id: {batch.id}  ステータス確認中…（完了まで最大24時間・多くは1時間以内）")

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
            print(f"  paper-{pid}: {res.result.type}")
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


if __name__ == "__main__":
    main()