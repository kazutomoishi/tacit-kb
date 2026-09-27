# tacit-kb

Scripts for the paper

> Ishi K. Externalizing tacit experimental know-how with large language models:
> a workflow, its preliminary expert evaluation, and a proposed extension to
> materials science. *Science and Technology of Advanced Materials: Methods*, 2026.

The workflow treats the vague wording that survives in published protocols —
"gently", "until clear", "approximately" — as a trace of an expert judgment the
text leaves unstated, and externalizes it into structured, source-linked
"tacit-knowledge cards".

## The two stages

| Script | Stage | What it does |
| --- | --- | --- |
| `collect.py` | 1 | Retrieves open-access protocol papers from Europe PMC and NCBI BioC, then detects candidate vague expressions by matching a lexicon of 49 alternatives, held as six regular expressions, one per trace category. No language-model inference. |
| `extract_batch.py` | 2 | Sends up to 25 candidate snippets per paper to a large language model via the Anthropic Batch API and stores the resulting cards. |

The prompt is reproduced in `extract_batch.py`.

Note: the system prompt (embedded in `extract_batch.py`) refers to "SECIモデル"
(the SECI model). The paper's own terminology was later revised to "Nonaka's
model of knowledge conversion," since the SECI acronym does not appear in
Nonaka (1994). The prompt is reproduced verbatim, as actually used, and was not
retroactively edited to match the paper's revised wording.

## Expert evaluation

| Script | What it does |
| --- | --- |
| `extract_batch_control.py` | Generates the control-condition cards and stores them with `source='llm_control'`. |
| `make_blind_eval.py` | Builds the blinded, paired evaluation sheet: for each selected paper, one theory-condition card and one control-condition card, shuffled and renumbered so that the condition cannot be seen. Writes the sheet for the evaluator and a separate key (`blind_key.csv`) that must not be given to the evaluator. |
| `analyze_ratings.py` | Computes the statistics reported in Section 4 and Table 3 from the completed rating sheets: Wilcoxon signed-rank and McNemar exact tests, Cohen's κ, hallucination rates, card length and Spearman ρ. |

The control condition used for the paired comparison in the paper was produced by
`extract_batch_control.py`. Its system prompt keeps the output format, the six
fields and the five-card limit of `extract_batch.py`, but omits the three
theoretical commitments, the priority on unstated decision criteria and the
theory-based role description, and describes `concrete_steps` without calling it
an estimate. The two prompts can be compared directly in the two scripts.

Evaluator B rated 40 of Evaluator A's cards, 20 per condition, drawn from 20
of the paired papers; that selection and the additional fabrication-subtype
column in Evaluator B's sheet were prepared separately and are not scripted here.

The version of `make_blind_eval.py` used for the paper could select the same
paper twice when a criticality stratum had too few cards and was filled from
the others. This affected one paper, which was excluded from the analysis
(Evaluator A: 38 pairs, 76 cards). The current version skips papers that have
already been used; the original is kept in the commit history.

## Trace categories

Six categories, 49 lexical alternatives in all.

| Category | What it marks | Example terms |
| --- | --- | --- |
| `vague_qty` | an imprecise quantity | approximately, a few, sufficient |
| `manner` | the quality of an action | gently, vigorously, carefully |
| `thermal` | a thermal condition | on ice, do not freeze |
| `adaptive` | a condition-dependent step | N to M times, if incomplete |
| `endpoint` | an observed end point | until clear, without clumps |
| `handling` | a caution cue | do not perturb, avoid bubbles |

## Card fields

| Field | Content |
| --- | --- |
| `term` | the vague expression, kept in English |
| `why_vague` | what judgment the expression leaves unstated |
| `body_sense` | the bodily sense underlying that judgment |
| `concrete_steps` | an explicit procedure, inferred from the passage |
| `failure_mode` | what goes wrong if the judgment is omitted |
| `criticality` | high, medium or low, as judged by the model |

## Running them

```bash
pip install -r requirements.txt

export ANTHROPIC_API_KEY="sk-ant-..."      # bash
# $env:ANTHROPIC_API_KEY="sk-ant-..."      # PowerShell

python collect.py                 # build tacit_kb.db and detect candidates
python collect.py 5               # try five papers first
python collect.py 500             # upper bound on papers attempted; the fifteen keyword queries
                                   # return at most a few hundred candidates regardless of this value,
                                   # so the run in the paper (349 retrieved, 315 after filtering)
                                   # was not limited by the argument
python extract_batch.py --limit 5 # try five papers first
python extract_batch.py           # process every paper with candidates

python extract_batch_control.py --limit 50   # control-condition cards
python make_blind_eval.py                     # blinded sheet, 40 cards per condition
python analyze_ratings.py                     # statistics, once the sheets are completed
```

`collect.py` and the card-generation scripts write to a single SQLite file,
`tacit_kb.db`, with three tables: `papers`, `candidate_terms` and `cards`. `extract_batch.py` and
`extract_batch_control.py` are re-runnable — papers that already have cards are
skipped.

Python 3.9 or later. No API key is stored in this repository; the scripts read
it from the environment.

## Implementation limits worth knowing

These shaped what the database could contain, and are reported in the paper.

- The fifteen search queries all contain the word "protocol", so the corpus is
  enriched for procedural venues by construction.
- A paper is kept only if its full text exceeds 1,500 characters and at least
  three candidates are detected. Papers in which no vague wording was found are
  therefore absent.
- Detection scans the first 80,000 characters of a paper.
- Only the first matching category is recorded for each sentence, in a fixed
  order, so the category counts are not independent of one another.
- At most 40 candidates are stored per paper, and at most 25 of them are shown
  to the model, taken in document order.

## What is not here

The database reported in the paper (`tacit_kb.db`, 315 papers, 4,189 candidates,
1,531 cards) is not deposited as a public resource. The database, the completed
evaluation sheets, the blinding keys and the complete rating data are available
from the author on reasonable request.

## Origin

Built at DxMT AIMHack 2026 (Gotemba, 24–26 June 2026), a hackathon of the Data
Creation and Utilization-Type Materials Research and Development Project (DxMT).
The corpus-scale application and the expert evaluation reported in the paper were
carried out afterwards.

## Licence

MIT

## Contact

Kazutomo Ishi — ishikazutomo@yahoo.co.jp — ORCID 0009-0001-3508-4983
