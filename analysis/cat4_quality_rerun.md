# Category 4 quality rerun — multi-document RAG

Generated 2026-11-25T17:29:19.370333+00:00 · answer key `2026-11-25.1` · rerun records 0 (ok sessions used 0) · judgements 0 (0 ok, judge claude-opus-5-5, spend $0.0000)

Sources: `/Users/mathu/Projects/NuSysDesPrac/novamart-ai-archetypes/backend/experiments/cat4_quality/runs.jsonl`, `/Users/mathu/Projects/NuSysDesPrac/novamart-ai-archetypes/backend/experiments/cat4_quality/judgements.jsonl`, `replays/cat4_golden_replays.json`, `app/data/cat4_quality_keys.json`. Every answer is scored; zero-citation, truncated and contaminated answers are reported, never dropped. Rates show hits/total (rate) [Wilson 95%]. Costs come from recorded tokens via `compute_run_finops` (billed = as recorded; cold = the cached call writes its whole prefix on question 1 of the session and reads after; warm = every cached-prefix token read).

Settings: synthesis max_tokens 2048 (timeout 300 s), rerank max_tokens 800 (timeout 180 s), max_retries 0. Session = 8 questions in order: audit-01/q1, audit-01/q2, audit-01/q3, audit-01/q4, audit-02/q1, audit-02/q2, audit-02/q3, audit-02/q4.

## Answer key and corpus

| question | facts | supplier-specific | commercial | statutory | mechanism | structure |
|---|---|---|---|---|---|---|
| audit-01/q1 | 7 | 3 | 3 | 1 | 0 | 3 |
| audit-01/q2 | 7 | 7 | 7 | 0 | 0 | 0 |
| audit-01/q3 | 7 | 6 | 6 | 0 | 0 | 1 |
| audit-01/q4 | 5 | 3 | 3 | 1 | 1 | 0 |
| audit-02/q1 | 6 | 1 | 1 | 4 | 1 | 0 |
| audit-02/q2 | 7 | 7 | 7 | 0 | 0 | 0 |
| audit-02/q3 | 7 | 3 | 3 | 4 | 0 | 0 |
| audit-02/q4 | 7 | 7 | 7 | 0 | 0 | 0 |

| scale | documents | chunks | chars | est. tokens (chars/2.4) | ratio to base |
|---|---|---|---|---|---|
| 1 | 7 | 28 | 38,758 | 16,149 | 1.0 |
| 3 | 21 | 84 | 116,511 | 48,546 | 3.006 |

## Original capture (golden replays, scale 1, n = 1 per rung × question)

One answer per rung and question, captured once; audit-02's cached prefix was already warm from audit-01. Small n: read the intervals.

| group | answers | key-fact recall | supplier-specific | statutory/mechanism/structure | citations/answer | zero-citation answers | expected-chunk recall (cited) | citations at expected chunks | cited support of hit facts |
|---|---|---|---|---|---|---|---|---|---|
| R1 naive | 8 | 52/53 (98%) [90–100] | 37/37 (100%) [91–100] | 15/16 (94%) [72–99] | not requested | — | n/a | n/a | n/a |
| R2 cached+cite | 8 | 52/53 (98%) [90–100] | 37/37 (100%) [91–100] | 15/16 (94%) [72–99] | 11.1 | 0/8 (0%) [0–32] | 28/30 (93%) [79–98] | 67/89 (75%) [65–83] | 51/52 (98%) [90–100] |
| R3 BM25+rerank | 8 | 51/53 (96%) [87–99] | 36/37 (97%) [86–100] | 15/16 (94%) [72–99] | 10.8 | 0/8 (0%) [0–32] | 29/30 (97%) [83–99] | 69/86 (80%) [71–87] | 51/51 (100%) [93–100] |

### Original capture per question (key-fact hits / facts; citations)

| question | R1 naive | R2 cached+cite | R3 BM25+rerank |
|---|---|---|---|
| audit-01/q1 | 7/7 | 7/7; 11 cites, cited-chunk recall 4/4 | 7/7; 9 cites, cited-chunk recall 4/4 |
| audit-01/q2 | 7/7 | 7/7; 16 cites, cited-chunk recall 4/4 | 7/7; 14 cites, cited-chunk recall 4/4 |
| audit-01/q3 | 7/7 | 7/7; 8 cites, cited-chunk recall 3/4 | 7/7; 10 cites, cited-chunk recall 4/4 |
| audit-01/q4 | 5/5 | 5/5; 11 cites, cited-chunk recall 2/3 | 5/5; 10 cites, cited-chunk recall 2/3 |
| audit-02/q1 | 5/6; missed a2q1-itc-16-2-aa | 5/6; 9 cites, cited-chunk recall 4/4; missed a2q1-itc-16-2-aa | 5/6; 9 cites, cited-chunk recall 4/4; missed a2q1-itc-16-2-aa |
| audit-02/q2 | 7/7 | 7/7; 15 cites, cited-chunk recall 4/4 | 7/7; 12 cites, cited-chunk recall 4/4 |
| audit-02/q3 | 7/7 | 7/7; 9 cites, cited-chunk recall 3/3 | 7/7; 13 cites, cited-chunk recall 3/3 |
| audit-02/q4 | 7/7 | 7/7; 10 cites, cited-chunk recall 4/4 | 6/7; 9 cites, cited-chunk recall 4/4; missed a2q4-rebate-2-75 |

### Original capture cost per question (USD)

| group | billed Sonnet | billed Haiku | billed total | cold Sonnet | cold Haiku | cold total | warm Sonnet | warm Haiku | warm total | cache-write premium (one-off) |
|---|---|---|---|---|---|---|---|---|---|---|
| R1 naive | $0.0463 | $0.0000 | $0.0463 | $0.0463 | $0.0000 | $0.0463 | $0.0463 | $0.0000 | $0.0463 | $0.0000 |
| R2 cached+cite | $0.0198 | $0.0000 | $0.0198 | $0.0198 | $0.0000 | $0.0198 | $0.0134 | $0.0000 | $0.0134 | $0.0515 |
| R3 BM25+rerank | $0.0233 | $0.0011 | $0.0243 | $0.0233 | $0.0011 | $0.0243 | $0.0233 | $0.0011 | $0.0243 | $0.0000 |

| group | call | prompt tok mean | prompt range | output mean | output range | cache write mean | cache read mean | thinking mean |
|---|---|---|---|---|---|---|---|---|
| R1 naive | synthesis | 18419 | 18391–18438 | 945 | 798–1039 | 0 | 0 | 0 |
| R2 cached+cite | synthesis | 21566 | 21538–21585 | 1098 | 903–1709 | 2682 | 18771 | 0 |
| R3 BM25+rerank | rerank | 9046 | 8734–9334 | 342 | 330–357 | 0 | 0 | 0 |
| R3 BM25+rerank | synthesis | 6117 | 5742–6740 | 1102 | 960–1773 | 0 | 0 | 0 |

### Original capture break-even (warm $/question + one-off cache-write premium)

| A vs B | A one-off cache-write premium | A warm $/question | B premium | B warm $/question | N* | result |
|---|---|---|---|---|---|---|
| R2 cached+cite vs R3 BM25+rerank | $0.0515 | $0.0134 | $0.0000 | $0.0243 | 4.69 | A cheaper from question 5 |

### Original capture judge

| group | judged | correctness mean (1–5) | completeness mean (1–5) | material errors | minor errors | answers with ≥1 material error | answers the question |
|---|---|---|---|---|---|---|---|
| R1 naive | 0 | n/a | n/a | n/a | n/a | n/a | n/a |
| R2 cached+cite | 0 | n/a | n/a | n/a | n/a | n/a | n/a |
| R3 BM25+rerank | 0 | n/a | n/a | n/a | n/a | n/a | n/a |

## Rerun (rung × scale)

No ok rerun sessions yet (`scripts/cat4_quality_rerun.py` has not been run, or every session errored).

## Zero-citation and contaminated answers

No zero-citation answers on a citation rung.

No contaminated answers.

## For lead review

Items a person should read before quoting any number from this file.

- No judge material errors (no judgements yet, or none reported).

- The answer key was written from the question texts and Deccan chunks only; one dry pass over the golden answers added format variants (see key `meta.format_variants_added`).
- Golden capture: audit-02 questions read a cache written by audit-01 (no write), n = 1 per cell.
- BM25 phrase bonuses and chunk keywords in `retriever.py` / fixtures were tuned on these questions and Deccan values; rung 3 retrieval recall is optimistic for unseen questions.
- Two questions (audit-01/q2, audit-02/q4) do not name the supplier; at scale 3 they are ambiguous by construction.
- The contamination detector cannot flag a distractor value that also occurs in Deccan's own documents; such values are excluded.

## Data quality

- error sessions: 0
- non end turn calls: 0
- model mismatches: 0
- cache anomalies: 0
- haiku calls over 100k prompt: 0
