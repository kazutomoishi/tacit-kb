# tacit-kb

Scripts for the paper

> Ishi K. Externalizing tacit experimental know-how with large language models:
> a workflow, its preliminary expert evaluation, and a proposed extension to
> materials science. *Science and Technology of Advanced Materials: Methods*, 2026.

The workflow treats the vague wording that survives in published protocols —
"gently", "until clear", "approximately" — as a trace of an expert judgement the
text leaves unstated, and externalizes it into structured, source-linked
"tacit-knowledge cards".

## The two stages

| Script | Stage | What it does |
| --- | --- | --- |
| `collect.py` | 1 | Retrieves open-access protocol papers from Europe PMC and NCBI BioC, then detects candidate vague expressions by matching a lexicon of 49 alternatives, held as six regular expressions, one per trace category. No language-model inference. |
| `extract_batch.py` | 2 | Sends up to 25 candidate snippets per paper to a large language model via the Anthropic Batch API and stores the resulting cards. |

The control condition used for the paired comparison in the paper was produced by
the same Stage-2 script with the three theoretical commitments removed from the
system prompt and nothing else changed. 
The prompt is reproduced in extract_batch.py. 
Its control-condition variant is available from the author on request.

Note: the system prompt (embedded in `extract_batch.py`) refers to "SECIモデル"
(the SECI model). The paper's own terminology was later revised to "Nonaka's
model of knowledge conversion," since the SECI acronym does not appear in
Nonaka (1994). The prompt is reproduced verbatim, as actually used, and was not
retroactively edited to match the paper's revised wording.

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
| `why_vague` | what judgement the expression leaves unstated |
| `body_sense` | the bodily sense underlying that judgement |
| `concrete_steps` | an explicit procedure, inferred from the passage |
| `failure_mode` | what goes wrong if the judgement is omitted |
| `criticality` | high, medium or low, as judged by the model |

## Running them

```bash
pip install anthropic requests

export ANTHROPIC_API_KEY="sk-ant-..."      # bash
# $env:ANTHROPIC_API_KEY="sk-ant-..."      # PowerShell

python collect.py                 # build tacit_kb.db and detect candidates
python collect.py 5               # try five papers first
python collect.py 500             # approximates the paper's retrieval cap; exact counts (349 retrieved,
                                   # 315 after filtering) may not reproduce exactly, since Europe PMC and
                                   # NCBI BioC are updated over time
python extract_batch.py --limit 5 # try five papers first
python extract_batch.py           # process every paper with candidates
```

Both write to a single SQLite file, `tacit_kb.db`, with three tables:
`papers`, `candidate_terms` and `cards`. `extract_batch.py` is re-runnable —
papers that already have cards are skipped.

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
1,531 cards) is a prototype produced during and shortly after a hackathon and is
not deposited as a public resource. The database, the control-condition variant of the prompt, the blinded evaluation instruments, the blinding keys and the complete rating data are available from the author on reasonable request.


## Origin

Built at DxMT AIMHack 2026 (Gotemba, 24–26 June 2026), a hackathon of the Data
Creation and Utilization-Type Materials Research and Development Project (DxMT).
The corpus-scale application and the expert evaluation reported in the paper were
carried out afterwards.

## Licence

MIT

## Contact

Kazutomo Ishi — ishikazutomo@yahoo.co.jp — ORCID 0009-0001-3508-4983

