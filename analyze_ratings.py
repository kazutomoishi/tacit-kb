#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_ratings.py — Statistics for Section 4 and Table 3 of the paper

Reproduces, from the blinded expert ratings:
  * Table 3: means, Wilcoxon signed-rank p (ordinal items), McNemar exact p
    (fabrication, hallucination), criticality label counts
  * Cohen's kappa on the 40 cards both evaluators rated
  * hallucination rates (Evaluator A on all 76 cards and on the common 40;
    Evaluator B on 40)
  * card length (theory vs control) and body_sense length, with a paired
    Wilcoxon test, and Spearman rho between card length and ratings

The rating data are not public; they are available from the author on
reasonable request (see the paper's Data availability statement).

Input files (default names; override with command-line options):
  blind_key.csv                      Evaluator A key: no, arm, criticality, paper_id, card_id
  tacit_card_eval_blind_T.xlsx       Evaluator A ratings, sheet '評価'
  260912tacit_card_eval_blind_W.xlsx Evaluator B ratings, sheet '評価'
  blind_key_W_対応表.xlsx             Evaluator B key, sheet '対応表'

Definitions used in the paper:
  * Pairs: one theory-condition card and one control-condition card from the
    same source paper. Paper 129 is excluded for Evaluator A, because it
    contributed two pairs and one control card (card_id 1643) was presented
    twice; this leaves 38 pairs (76 cards).
  * Hallucination: faithfulness <= 2 or fabrication present.
  * Criticality label "correct": the evaluator judged the level the model
    assigned (high/medium/low) to be appropriate (適切).
  * Card length: characters in why_vague + body_sense + concrete_steps +
    failure_mode.

Tests:
  * Wilcoxon signed-rank test (scipy), zero differences dropped
    (zero_method='wilcox'), normal approximation with tie correction
    (method='approx'), no continuity correction, two-sided. The method is
    fixed explicitly so that results do not depend on the scipy version.
  * McNemar exact test: two-sided binomial test on the discordant pairs.
  * Cohen's kappa for two raters and a binary judgment.
  * Spearman rank correlation.
  No correction for multiple comparisons is applied.

Usage:
  pip install openpyxl scipy numpy
  python analyze_ratings.py
"""
import argparse
import collections
import csv

import numpy as np
import openpyxl
from scipy.stats import binomtest, spearmanr, wilcoxon

EXCLUDED_PAPERS_A = {"129"}


# ---------------------------------------------------------------- loading
def load_rows(path, sheet):
    ws = openpyxl.load_workbook(path, data_only=True)[sheet]
    return [r for r in list(ws.iter_rows(values_only=True))[1:] if r and r[0] is not None]


def s(x):
    return str(x).strip() if x is not None else ""


def load_evaluator_a(key_csv, ratings_xlsx):
    key = {}
    with open(key_csv, encoding="utf-8-sig") as f:
        for d in csv.DictReader(f):
            key[int(d["no"])] = d
    cards = {}
    # Columns of sheet '評価' (0-based): 0 no, 5 why_vague, 6 body_sense,
    # 7 concrete_steps, 8 failure_mode, 9 faithfulness, 10 fabrication,
    # 11 theoretical validity, 12 usefulness, 13 criticality judgment
    for r in load_rows(ratings_xlsx, "評価"):
        no = int(r[0])
        k = key[no]
        cards[no] = dict(
            f=int(r[9]), fab=s(r[10]) == "有", v=int(r[11]), u=int(r[12]), lab=s(r[13]),
            length=sum(len(s(r[i])) for i in (5, 6, 7, 8)), bs=len(s(r[6])),
            arm=k["arm"], pid=str(k["paper_id"]), cid=str(k["card_id"]),
        )
    return cards


def load_evaluator_b(ratings_xlsx, key_xlsx):
    cards = {}
    # Columns of sheet '評価' (0-based): 0 no, 9 faithfulness, 10 fabrication,
    # 11 fabrication subtype, 12 theoretical validity, 13 usefulness,
    # 14 criticality judgment
    for r in load_rows(ratings_xlsx, "評価"):
        cards[int(r[0])] = dict(
            f=int(r[9]), fab=s(r[10]) == "有", sub=s(r[11]),
            v=int(r[12]), u=int(r[13]), lab=s(r[14]),
        )
    # Columns of sheet '対応表' (0-based): 0 no, 1 condition, 2 card_id,
    # 4 paper_id, 6 Evaluator A's presentation number for the same card
    for r in load_rows(key_xlsx, "対応表"):
        cards[int(r[0])].update(
            arm="theory" if s(r[1]) == "理論あり" else "control",
            cid=s(r[2]), pid=s(r[4]), a_no=int(r[6]),
        )
    return cards


def add_derived(cards):
    for d in cards.values():
        d["hal"] = d["f"] <= 2 or d["fab"]
        d["ok"] = d["lab"] == "適切"


def make_pairs(cards, exclude=()):
    by_paper = collections.defaultdict(lambda: collections.defaultdict(list))
    for no, d in sorted(cards.items()):
        if d["pid"] in exclude:
            continue
        by_paper[d["pid"]][d["arm"]].append(no)
    pairs = []
    for arms in by_paper.values():
        for i in range(min(len(arms["theory"]), len(arms["control"]))):
            pairs.append((arms["theory"][i], arms["control"][i]))
    return pairs


# ---------------------------------------------------------------- tests
def wilcoxon_paired(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if np.all(x == y):
        return float("nan")
    return wilcoxon(x, y, zero_method="wilcox", correction=False,
                    method="approx", alternative="two-sided").pvalue


def mcnemar_exact(x, y):
    b = sum(1 for i, j in zip(x, y) if i and not j)
    c = sum(1 for i, j in zip(x, y) if j and not i)
    p = binomtest(min(b, c), b + c, 0.5).pvalue if b + c else float("nan")
    return b, c, p


def cohen_kappa(a, b):
    n = len(a)
    po = sum(1 for i, j in zip(a, b) if i == j) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return (po - pe) / (1 - pe), po, pe


# ---------------------------------------------------------------- report
def fmt_p(p):
    return "—" if p != p else f"{p:.2f}"


def table3_column(name, cards, pairs):
    print(f"\n== {name}: {len(pairs)} pairs ({2 * len(pairs)} cards)")
    for item, label in (("f", "Faithfulness (1–4)"), ("v", "Theoretical validity (1–4)"),
                        ("u", "Usefulness (1–4)")):
        x = [cards[t][item] for t, c in pairs]
        y = [cards[c][item] for t, c in pairs]
        print(f"  {label:28s} {np.mean(x):.2f} / {np.mean(y):.2f}   p = {fmt_p(wilcoxon_paired(x, y))}")
    for item, label in (("fab", "Fabrication present"), ("ok", "Criticality label correct"),
                        ("hal", "Hallucination rate")):
        x = [cards[t][item] for t, c in pairs]
        y = [cards[c][item] for t, c in pairs]
        b, c, p = mcnemar_exact(x, y)
        if item == "hal":
            vals = f"{100 * sum(x) / len(x):.1f}% / {100 * sum(y) / len(y):.1f}%"
        else:
            vals = f"{sum(x)} / {sum(y)} of {len(pairs)}"
        print(f"  {label:28s} {vals:20s} p = {fmt_p(p)}   (discordant {b}:{c})")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--key-a", default="blind_key.csv")
    ap.add_argument("--ratings-a", default="tacit_card_eval_blind_T.xlsx")
    ap.add_argument("--ratings-b", default="260912tacit_card_eval_blind_W.xlsx")
    ap.add_argument("--key-b", default="blind_key_W_対応表.xlsx")
    args = ap.parse_args()

    A = load_evaluator_a(args.key_a, args.ratings_a)
    B = load_evaluator_b(args.ratings_b, args.key_b)
    add_derived(A)
    add_derived(B)

    pairs_a = make_pairs(A, EXCLUDED_PAPERS_A)
    pairs_b = make_pairs(B)
    cards_a76 = [n for pr in pairs_a for n in pr]

    # sanity checks
    print(f"Evaluator A: {len(A)} cards rated; {len(pairs_a)} pairs used")
    print(f"Evaluator B: {len(B)} cards rated; {len(pairs_b)} pairs used")
    assert len(set(A[n]["cid"] for n in cards_a76)) == len(cards_a76), "duplicate card among A's pairs"
    common = [(d["a_no"], n) for n, d in B.items()]
    assert all(A[a]["cid"] == B[b]["cid"] for a, b in common), "A/B card_id mismatch"
    assert all(a in cards_a76 for a, b in common), "a B card is outside A's 76"

    # Table 3
    table3_column("Evaluator A (theory / control)", A, pairs_a)
    table3_column("Evaluator B (theory / control)", B, pairs_b)

    # Evaluator B pooled (Section 4)
    print("\n== Evaluator B, all 40 cards")
    print(f"  theoretical validity {np.mean([d['v'] for d in B.values()]):.3f}, "
          f"usefulness {np.mean([d['u'] for d in B.values()]):.3f}, "
          f"criticality accepted {sum(d['ok'] for d in B.values())}/{len(B)}")
    print(f"  criticality judgments: {dict(collections.Counter(d['lab'] for d in B.values()))}")
    print(f"  fabrication: {sum(d['fab'] for d in B.values())}/{len(B)}; subtypes "
          f"{dict(collections.Counter(d['sub'] for d in B.values() if d['fab']))}")
    print("== Evaluator A, criticality judgments (all rated cards): "
          f"{dict(collections.Counter(d['lab'] for d in A.values()))}")

    # agreement on the common 40
    print(f"\n== Agreement on the {len(common)} cards both evaluators rated")
    for label, fn in (("fabrication", lambda d: int(d["fab"])),
                      ("faithfulness >= 3", lambda d: int(d["f"] >= 3)),
                      ("hallucination", lambda d: int(d["hal"]))):
        a = [fn(A[i]) for i, j in common]
        b = [fn(B[j]) for i, j in common]
        k, po, pe = cohen_kappa(a, b)
        only_b = sum(1 for i, j in zip(a, b) if j and not i)
        only_a = sum(1 for i, j in zip(a, b) if i and not j)
        print(f"  {label:18s} kappa = {k:.3f}  (po {po:.3f}, pe {pe:.3f}; B only {only_b}, A only {only_a})")

    # hallucination rates
    hal_a76 = sum(A[n]["hal"] for n in cards_a76)
    hal_a40 = sum(A[a]["hal"] for a, b in common)
    hal_b40 = sum(B[b]["hal"] for a, b in common)
    print("\n== Hallucination rates")
    print(f"  Evaluator A, all {len(cards_a76)} cards: {hal_a76}/{len(cards_a76)} = {100 * hal_a76 / len(cards_a76):.1f}%")
    print(f"  common {len(common)}: Evaluator A {hal_a40}/{len(common)} = {100 * hal_a40 / len(common):.1f}%, "
          f"Evaluator B {hal_b40}/{len(common)} = {100 * hal_b40 / len(common):.1f}%")

    # card length
    print(f"\n== Card length, Evaluator A's {len(cards_a76)} cards (characters)")
    for key, label in (("length", "whole card (four fields)"), ("bs", "body_sense")):
        x = [A[t][key] for t, c in pairs_a]
        y = [A[c][key] for t, c in pairs_a]
        print(f"  {label:26s} {np.mean(x):.1f} vs {np.mean(y):.1f}  "
              f"(ratio {np.mean(x) / np.mean(y):.2f}; Wilcoxon p = {wilcoxon_paired(x, y):.2g})")
    print("  Spearman rho, card length vs rating (both conditions pooled):")
    for item, label in (("f", "faithfulness"), ("v", "theoretical validity"), ("u", "usefulness")):
        r = spearmanr([A[n]["length"] for n in cards_a76], [A[n][item] for n in cards_a76])
        print(f"    {label:22s} rho = {r.statistic:.3f}, p = {r.pvalue:.3f}")


if __name__ == "__main__":
    main()
