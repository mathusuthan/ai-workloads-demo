# Category 4 quality rerun — multi-document RAG

Generated 2026-11-26T05:02:14.237006+00:00 · answer key `2026-11-25.1` · rerun records 41 (ok sessions used 36, superseded 0) · judgements 376 (312 ok, judge claude-opus-5-5, spend $7.8395)

Sources: `/Users/mathu/Projects/NuSysDesPrac/novamart-ai-archetypes/backend/experiments/cat4_quality/runs.jsonl`, `/Users/mathu/Projects/NuSysDesPrac/novamart-ai-archetypes/backend/experiments/cat4_quality/judgements.jsonl`, `replays/cat4_golden_replays.json`, `app/data/cat4_quality_keys.json`. Every answer is scored; zero-citation, truncated and contaminated answers are reported, never dropped. Rates show hits/total (rate) [Wilson 95%]. Costs come from recorded tokens via `compute_run_finops` (billed = as recorded; cold = the cached call writes its whole prefix on question 1 of the session and reads after; warm = every cached-prefix token read).

Question scope line (rerun only): every rerun question is asked as `Deal room under audit: DR-NM-DECCAN-2026-Q4 (supplier: Deccan Smart Appliances & Energy Pvt. Ltd.). Answer for this supplier's contracts only.` followed by a blank line and the original question — identically for all four rungs and both scales, in the synthesis message, the reranker query (rungs 3 and 4) and the BM25 query (rung 3). The original capture (golden replays) was asked WITHOUT it, so original-capture vs rerun differences include this change. The judge sees each answer's question as asked.

Settings: synthesis max_tokens 4096 (timeout 300 s), rerank max_tokens 800 (timeout 180 s), max_retries 0. Session = 8 questions in order: audit-01/q1, audit-01/q2, audit-01/q3, audit-01/q4, audit-02/q1, audit-02/q2, audit-02/q3, audit-02/q4.

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
| R1 naive | 8 | 52/53 (98%) [90–100] | 37/37 (100%) [91–100] | 15/16 (94%) [72–99] | not requested | — | — | — | — |
| R2 cached+cite | 8 | 49/53 (92%) [82–97] | 35/37 (95%) [82–99] | 14/16 (88%) [64–97] | 11.6 | 0/8 (0%) [0–32] | 29/30 (97%) [83–99] | 68/93 (73%) [63–81] | 48/49 (98%) [89–100] |
| R3 BM25+rerank | 8 | 49/53 (92%) [82–97] | 36/37 (97%) [86–100] | 13/16 (81%) [57–93] | 10.2 | 0/8 (0%) [0–32] | 28/30 (93%) [79–98] | 65/82 (79%) [69–87] | 48/49 (98%) [89–100] |

### Original capture per question (key-fact hits / facts; citations)

| question | R1 naive | R2 cached+cite | R3 BM25+rerank |
|---|---|---|---|
| audit-01/q1 | 7/7 | 7/7; 12 cites, cited-chunk recall 4/4 | 7/7; 12 cites, cited-chunk recall 4/4 |
| audit-01/q2 | 7/7 | 7/7; 13 cites, cited-chunk recall 4/4 | 7/7; 12 cites, cited-chunk recall 4/4 |
| audit-01/q3 | 7/7 | 7/7; 11 cites, cited-chunk recall 4/4 | 6/7; 8 cites, cited-chunk recall 4/4; missed a1q3-telemetry-firewall-b2 |
| audit-01/q4 | 5/5 | 4/5; 11 cites, cited-chunk recall 2/3; missed a1q4-certin-6-hours | 4/5; 9 cites, cited-chunk recall 2/3; missed a1q4-certin-6-hours |
| audit-02/q1 | 5/6; missed a2q1-itc-16-2-aa | 5/6; 10 cites, cited-chunk recall 4/4; missed a2q1-itc-16-2-aa | 5/6; 8 cites, cited-chunk recall 3/4; missed a2q1-itc-16-2-aa |
| audit-02/q2 | 7/7 | 7/7; 15 cites, cited-chunk recall 4/4 | 6/7; 12 cites, cited-chunk recall 4/4; missed a2q2-net-worth-74-10 |
| audit-02/q3 | 7/7 | 7/7; 11 cites, cited-chunk recall 3/3 | 7/7; 11 cites, cited-chunk recall 3/3 |
| audit-02/q4 | 7/7 | 5/7; 10 cites, cited-chunk recall 4/4; missed a2q4-exclusivity-9-months, a2q4-rebate-2-75 | 7/7; 10 cites, cited-chunk recall 4/4 |

### Original capture cost per question (USD)

| group | billed Sonnet | billed Haiku | billed total | cold Sonnet | cold Haiku | cold total | warm Sonnet | warm Haiku | warm total | cache-write premium (one-off) |
|---|---|---|---|---|---|---|---|---|---|---|
| R1 naive | $0.0461 | $0.0000 | $0.0461 | $0.0461 | $0.0000 | $0.0461 | $0.0461 | $0.0000 | $0.0461 | $0.0000 |
| R2 cached+cite | $0.0270 | $0.0000 | $0.0270 | $0.0270 | $0.0000 | $0.0270 | $0.0205 | $0.0000 | $0.0205 | $0.0516 |
| R3 BM25+rerank | $0.0223 | $0.0011 | $0.0234 | $0.0223 | $0.0011 | $0.0234 | $0.0223 | $0.0011 | $0.0234 | $0.0000 |

| group | call | prompt tok mean | prompt range | output mean | output range | cache write mean | cache read mean | thinking mean |
|---|---|---|---|---|---|---|---|---|
| R1 naive | synthesis | 18492 | 18464–18511 | 907 | 786–1007 | 0 | 0 | 0 |
| R2 cached+cite | synthesis | 21666 | 21638–21685 | 1801 | 1050–2992 | 2685 | 18795 | 0 |
| R3 BM25+rerank | rerank | 9020 | 8640–9573 | 344 | 334–361 | 0 | 0 | 0 |
| R3 BM25+rerank | synthesis | 6248 | 5924–6922 | 983 | 846–1109 | 0 | 0 | 0 |

### Original capture break-even (warm $/question + one-off cache-write premium)

| A vs B | A one-off cache-write premium | A warm $/question | B premium | B warm $/question | N* | result |
|---|---|---|---|---|---|---|
| R2 cached+cite vs R3 BM25+rerank | $0.0516 | $0.0205 | $0.0000 | $0.0234 | 17.97 | A cheaper from question 18 |

### Original capture judge

| group | judged | correctness mean (1–5) | completeness mean (1–5) | material errors | minor errors | answers with ≥1 material error | answers the question |
|---|---|---|---|---|---|---|---|
| R1 naive | 0 | n/a | n/a | n/a | n/a | n/a | n/a |
| R2 cached+cite | 0 | n/a | n/a | n/a | n/a | n/a | n/a |
| R3 BM25+rerank | 0 | n/a | n/a | n/a | n/a | n/a | n/a |

## Rerun (rung × scale)

### Quality

| group | answers | key-fact recall | supplier-specific | statutory/mechanism/structure | citations/answer | zero-citation answers | expected-chunk recall (cited) | citations at expected chunks | cited support of hit facts |
|---|---|---|---|---|---|---|---|---|---|
| R1 naive · s1 | 24 | 156/159 (98%) [95–99] | 111/111 (100%) [97–100] | 45/48 (94%) [83–98] | not requested | — | — | — | — |
| R1 naive · s3 | 24 | 150/159 (94%) [90–97] | 104/111 (94%) [88–97] | 46/48 (96%) [86–99] | not requested | — | — | — | — |
| R2 cached+cite · s1 | 24 | 150/159 (94%) [90–97] | 106/111 (95%) [90–98] | 44/48 (92%) [80–97] | 11.7 | 0/24 (0%) [0–14] | 87/90 (97%) [91–99] | 207/281 (74%) [68–78] | 148/150 (99%) [95–100] |
| R2 cached+cite · s3 | 24 | 149/159 (94%) [89–97] | 107/111 (96%) [91–99] | 42/48 (88%) [75–94] | 11.4 | 0/24 (0%) [0–14] | 86/90 (96%) [89–98] | 204/273 (75%) [69–80] | 146/149 (98%) [94–99] |
| R3 BM25+rerank · s1 | 24 | 152/159 (96%) [91–98] | 108/111 (97%) [92–99] | 44/48 (92%) [80–97] | 10.9 | 0/24 (0%) [0–14] | 87/90 (97%) [91–99] | 212/262 (81%) [76–85] | 149/152 (98%) [94–99] |
| R3 BM25+rerank · s3 | 24 | 145/159 (91%) [86–95] | 103/111 (93%) [86–96] | 42/48 (88%) [75–94] | 9.0 | 0/24 (0%) [0–14] | 74/90 (82%) [73–89] | 184/216 (85%) [80–89] | 142/145 (98%) [94–99] |
| R4 cached-rerank · s1 | 24 | 154/159 (97%) [93–99] | 109/111 (98%) [94–100] | 45/48 (94%) [83–98] | 10.9 | 0/24 (0%) [0–14] | 87/90 (97%) [91–99] | 217/262 (83%) [78–87] | 151/154 (98%) [94–99] |
| R4 cached-rerank · s3 | 24 | 153/159 (96%) [92–98] | 108/111 (97%) [92–99] | 45/48 (94%) [83–98] | 10.7 | 0/24 (0%) [0–14] | 88/90 (98%) [92–99] | 216/257 (84%) [79–88] | 150/153 (98%) [94–99] |
| R3 BM25+rerank · s1 · scoped_absence | 24 | 150/159 (94%) [90–97] | 107/111 (96%) [91–99] | 43/48 (90%) [78–95] | 10.3 | 0/24 (0%) [0–14] | 84/90 (93%) [86–97] | 200/247 (81%) [76–85] | 147/150 (98%) [94–99] |
| R3 BM25+rerank · s3 · scoped_absence | 24 | 144/159 (91%) [85–94] | 103/111 (93%) [86–96] | 41/48 (85%) [73–93] | 8.9 | 0/24 (0%) [0–14] | 72/90 (80%) [71–87] | 183/214 (86%) [80–90] | 141/144 (98%) [94–99] |
| R4 cached-rerank · s1 · scoped_absence | 24 | 153/159 (96%) [92–98] | 109/111 (98%) [94–100] | 44/48 (92%) [80–97] | 10.2 | 0/24 (0%) [0–14] | 84/90 (93%) [86–97] | 205/245 (84%) [79–88] | 150/153 (98%) [94–99] |
| R4 cached-rerank · s3 · scoped_absence | 24 | 154/159 (97%) [93–99] | 110/111 (99%) [95–100] | 44/48 (92%) [80–97] | 10.5 | 0/24 (0%) [0–14] | 85/90 (94%) [88–98] | 206/251 (82%) [77–86] | 151/154 (98%) [94–99] |

### Contamination and retrieval

Contaminated = the answer states a distractor supplier's value for a keyed fact, or cites a distractor chunk. 'Without naming the other supplier' drops values whose 150-char neighbourhood names that supplier or one of its document ids (typically an explicit exclusion). Exposure = the synthesis prompt contained distractor text (the whole corpus at scale 3, or ≥ 1 distractor chunk selected); it is not counted as contamination.

| group | contaminated answers | …distractor value stated | …value stated without naming the other supplier | …distractor chunk cited | synthesis saw distractor text (exposure) | citations at Deccan | citations at distractors | expected recall after BM25 | expected recall after rerank | distractor chunks selected | backfilled / invalid picks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 naive · s1 | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | — | — | — | — | — | — |
| R1 naive · s3 | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 24/24 (100%) [86–100] | — | — | — | — | — | — |
| R2 cached+cite · s1 | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 281/281 (100%) [99–100] | 0/281 (0%) [0–1] | — | — | — | — |
| R2 cached+cite · s3 | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 24/24 (100%) [86–100] | 273/273 (100%) [99–100] | 0/273 (0%) [0–1] | — | — | — | — |
| R3 BM25+rerank · s1 | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 262/262 (100%) [99–100] | 0/262 (0%) [0–1] | 90/90 (100%) [96–100] | 89/90 (99%) [94–100] | 0/120 (0%) [0–3] | 0 / 0 |
| R3 BM25+rerank · s3 | 1/24 (4%) [1–20] | 1/24 (4%) [1–20] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 24/24 (100%) [86–100] | 216/216 (100%) [98–100] | 0/216 (0%) [0–2] | 78/90 (87%) [78–92] | 77/90 (86%) [77–91] | 25/120 (21%) [15–29] | 7 / 1 |
| R4 cached-rerank · s1 | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 262/262 (100%) [99–100] | 0/262 (0%) [0–1] | — | 90/90 (100%) [96–100] | 0/120 (0%) [0–3] | 0 / 0 |
| R4 cached-rerank · s3 | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 257/257 (100%) [99–100] | 0/257 (0%) [0–1] | — | 90/90 (100%) [96–100] | 0/120 (0%) [0–3] | 0 / 0 |
| R3 BM25+rerank · s1 · scoped_absence | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 247/247 (100%) [98–100] | 0/247 (0%) [0–2] | 90/90 (100%) [96–100] | 90/90 (100%) [96–100] | 0/120 (0%) [0–3] | 0 / 0 |
| R3 BM25+rerank · s3 · scoped_absence | 2/24 (8%) [2–26] | 2/24 (8%) [2–26] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 24/24 (100%) [86–100] | 214/214 (100%) [98–100] | 0/214 (0%) [0–2] | 78/90 (87%) [78–92] | 78/90 (87%) [78–92] | 24/120 (20%) [14–28] | 2 / 1 |
| R4 cached-rerank · s1 · scoped_absence | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 245/245 (100%) [98–100] | 0/245 (0%) [0–2] | — | 89/90 (99%) [94–100] | 0/120 (0%) [0–3] | 0 / 0 |
| R4 cached-rerank · s3 · scoped_absence | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 251/251 (100%) [98–100] | 0/251 (0%) [0–2] | — | 89/90 (99%) [94–100] | 0/120 (0%) [0–3] | 0 / 0 |

### Judge

| group | judged | correctness mean (1–5) | completeness mean (1–5) | material errors | minor errors | answers with ≥1 material error | answers the question |
|---|---|---|---|---|---|---|---|
| R1 naive · s1 | 24 | 4.50 | 4.83 | 1 | 17 | 1/24 (4%) [1–20] | yes 24 |
| R1 naive · s3 | 24 | 4.50 | 4.75 | 3 | 17 | 3/24 (12%) [4–31] | yes 24 |
| R2 cached+cite · s1 | 24 | 4.96 | 4.58 | 0 | 3 | 0/24 (0%) [0–14] | yes 24 |
| R2 cached+cite · s3 | 24 | 4.83 | 4.67 | 0 | 6 | 0/24 (0%) [0–14] | yes 24 |
| R3 BM25+rerank · s1 | 24 | 4.71 | 4.67 | 0 | 9 | 0/24 (0%) [0–14] | partly 1, yes 23 |
| R3 BM25+rerank · s3 | 24 | 3.96 | 4.21 | 11 | 21 | 8/24 (33%) [18–53] | partly 4, yes 20 |
| R4 cached-rerank · s1 | 24 | 4.54 | 4.71 | 1 | 12 | 1/24 (4%) [1–20] | yes 24 |
| R4 cached-rerank · s3 | 24 | 4.38 | 4.50 | 6 | 9 | 6/24 (25%) [12–45] | yes 24 |
| R3 BM25+rerank · s1 · scoped_absence | 24 | 4.54 | 4.58 | 2 | 11 | 2/24 (8%) [2–26] | yes 24 |
| R3 BM25+rerank · s3 · scoped_absence | 24 | 4.33 | 4.00 | 4 | 14 | 3/24 (12%) [4–31] | partly 3, yes 21 |
| R4 cached-rerank · s1 · scoped_absence | 24 | 4.75 | 4.54 | 0 | 11 | 0/24 (0%) [0–14] | yes 24 |
| R4 cached-rerank · s3 · scoped_absence | 24 | 4.54 | 4.54 | 2 | 13 | 2/24 (8%) [2–26] | yes 24 |

### Absence claims

Deterministic detector over each answer: a sentence saying the documents / deal room / contracts / text contain, specify or state no X (documents-lack form), or that X is not in the text provided / the excerpts (not-in-text-provided form). The judge column counts answers whose material errors include such a claim about a term the documents do contain. Answer formats: `original`, `scoped_absence`.

| group | answers | answers saying the documents lack something (detector) | answers saying it is not in the text provided (detector) | claims: documents-lack / not-in-text-provided | answers writing "None stated in the text provided" | judged answers with an unsupported absence claim (judge material error) | those judge errors: documents-lack / not-in-text-provided | answers with ≥1 material error | correctness mean | key-fact recall |
|---|---|---|---|---|---|---|---|---|---|---|
| R1 naive · s1 | 24 | 7/24 (29%) [15–49] | 0/24 (0%) [0–14] | 7 / 0 | 0 | 0/24 (0%) [0–14] | 0 / 0 | 1/24 (4%) [1–20] | 4.50 | 156/159 (98%) [95–99] |
| R1 naive · s3 | 24 | 1/24 (4%) [1–20] | 1/24 (4%) [1–20] | 1 / 1 | 0 | 0/24 (0%) [0–14] | 0 / 0 | 3/24 (12%) [4–31] | 4.50 | 150/159 (94%) [90–97] |
| R2 cached+cite · s1 | 24 | 4/24 (17%) [7–36] | 0/24 (0%) [0–14] | 4 / 0 | 0 | 0/24 (0%) [0–14] | 0 / 0 | 0/24 (0%) [0–14] | 4.96 | 150/159 (94%) [90–97] |
| R2 cached+cite · s3 | 24 | 3/24 (12%) [4–31] | 0/24 (0%) [0–14] | 4 / 0 | 0 | 0/24 (0%) [0–14] | 0 / 0 | 0/24 (0%) [0–14] | 4.83 | 149/159 (94%) [89–97] |
| R3 BM25+rerank · s1 | 24 | 9/24 (38%) [21–57] | 2/24 (8%) [2–26] | 11 / 2 | 0 | 0/24 (0%) [0–14] | 0 / 0 | 0/24 (0%) [0–14] | 4.71 | 152/159 (96%) [91–98] |
| R3 BM25+rerank · s3 | 24 | 12/24 (50%) [31–69] | 10/24 (42%) [24–61] | 15 / 13 | 0 | 8/24 (33%) [18–53] | 5 / 6 | 8/24 (33%) [18–53] | 3.96 | 145/159 (91%) [86–95] |
| R4 cached-rerank · s1 | 24 | 12/24 (50%) [31–69] | 1/24 (4%) [1–20] | 13 / 1 | 0 | 1/24 (4%) [1–20] | 1 / 0 | 1/24 (4%) [1–20] | 4.54 | 154/159 (97%) [93–99] |
| R4 cached-rerank · s3 | 24 | 13/24 (54%) [35–72] | 6/24 (25%) [12–45] | 13 / 9 | 0 | 6/24 (25%) [12–45] | 4 / 2 | 6/24 (25%) [12–45] | 4.38 | 153/159 (96%) [92–98] |
| R3 BM25+rerank · s1 · scoped_absence | 24 | 0/24 (0%) [0–14] | 21/24 (88%) [69–96] | 0 / 33 | 12 | 1/24 (4%) [1–20] | 0 / 1 | 2/24 (8%) [2–26] | 4.54 | 150/159 (94%) [90–97] |
| R3 BM25+rerank · s3 · scoped_absence | 24 | 0/24 (0%) [0–14] | 22/24 (92%) [74–98] | 0 / 36 | 15 | 3/24 (12%) [4–31] | 0 / 3 | 3/24 (12%) [4–31] | 4.33 | 144/159 (91%) [85–94] |
| R4 cached-rerank · s1 · scoped_absence | 24 | 0/24 (0%) [0–14] | 21/24 (88%) [69–96] | 0 / 32 | 13 | 0/24 (0%) [0–14] | 0 / 0 | 0/24 (0%) [0–14] | 4.75 | 153/159 (96%) [92–98] |
| R4 cached-rerank · s3 · scoped_absence | 24 | 0/24 (0%) [0–14] | 20/24 (83%) [64–93] | 0 / 30 | 12 | 1/24 (4%) [1–20] | 0 / 1 | 2/24 (8%) [2–26] | 4.54 | 154/159 (97%) [93–99] |

### Cost per question (USD, mean over answers)

| group | billed Sonnet | billed Haiku | billed total | cold Sonnet | cold Haiku | cold total | warm Sonnet | warm Haiku | warm total | cache-write premium (one-off) |
|---|---|---|---|---|---|---|---|---|---|---|
| R1 naive · s1 | $0.0459 | $0.0000 | $0.0459 | $0.0459 | $0.0000 | $0.0459 | $0.0459 | $0.0000 | $0.0459 | $0.0000 |
| R1 naive · s3 | $0.1173 | $0.0000 | $0.1173 | $0.1173 | $0.0000 | $0.1173 | $0.1173 | $0.0000 | $0.1173 | $0.0000 |
| R2 cached+cite · s1 | $0.0253 | $0.0000 | $0.0253 | $0.0253 | $0.0000 | $0.0253 | $0.0188 | $0.0000 | $0.0188 | $0.0516 |
| R2 cached+cite · s3 | $0.0379 | $0.0000 | $0.0379 | $0.0379 | $0.0000 | $0.0379 | $0.0193 | $0.0000 | $0.0193 | $0.1491 |
| R3 BM25+rerank · s1 | $0.0236 | $0.0011 | $0.0247 | $0.0236 | $0.0011 | $0.0247 | $0.0236 | $0.0011 | $0.0247 | $0.0000 |
| R3 BM25+rerank · s3 | $0.0267 | $0.0010 | $0.0278 | $0.0267 | $0.0010 | $0.0278 | $0.0267 | $0.0010 | $0.0278 | $0.0000 |
| R4 cached-rerank · s1 | $0.0237 | $0.0007 | $0.0244 | $0.0237 | $0.0007 | $0.0244 | $0.0237 | $0.0004 | $0.0241 | $0.0025 |
| R4 cached-rerank · s3 | $0.0246 | $0.0017 | $0.0264 | $0.0246 | $0.0017 | $0.0264 | $0.0246 | $0.0008 | $0.0254 | $0.0073 |
| R3 BM25+rerank · s1 · scoped_absence | $0.0224 | $0.0011 | $0.0234 | $0.0224 | $0.0011 | $0.0234 | $0.0224 | $0.0011 | $0.0234 | $0.0000 |
| R3 BM25+rerank · s3 · scoped_absence | $0.0252 | $0.0010 | $0.0262 | $0.0252 | $0.0010 | $0.0262 | $0.0252 | $0.0010 | $0.0262 | $0.0000 |
| R4 cached-rerank · s1 · scoped_absence | $0.0223 | $0.0007 | $0.0230 | $0.0223 | $0.0007 | $0.0230 | $0.0223 | $0.0004 | $0.0227 | $0.0025 |
| R4 cached-rerank · s3 · scoped_absence | $0.0232 | $0.0017 | $0.0250 | $0.0232 | $0.0017 | $0.0250 | $0.0232 | $0.0008 | $0.0241 | $0.0073 |

### Tokens per call

| group | call | prompt tok mean | prompt range | output mean | output range | cache write mean | cache read mean | thinking mean |
|---|---|---|---|---|---|---|---|---|
| R1 naive · s1 | synthesis | 18492 | 18464–18511 | 895 | 786–1007 | 0 | 0 | 0 |
| R1 naive · s3 | synthesis | 54221 | 54193–54240 | 884 | 760–1044 | 0 | 0 | 0 |
| R2 cached+cite · s1 | synthesis | 21665 | 21637–21685 | 1629 | 991–2992 | 2685 | 18794 | 606 |
| R2 cached+cite · s3 | synthesis | 62292 | 62263–62312 | 1268 | 949–2282 | 7763 | 54343 | 240 |
| R3 BM25+rerank · s1 | rerank | 9020 | 8640–9573 | 344 | 323–365 | 0 | 0 | 0 |
| R3 BM25+rerank · s1 | synthesis | 6072 | 5815–6240 | 1150 | 894–2420 | 0 | 0 | 141 |
| R3 BM25+rerank · s3 | rerank | 8591 | 7248–9712 | 327 | 79–360 | 0 | 0 | 0 |
| R3 BM25+rerank · s3 | synthesis | 6097 | 5325–7031 | 1455 | 954–2099 | 0 | 0 | 508 |
| R4 cached-rerank · s1 | rerank | 21649 | 21620–21669 | 344 | 310–379 | 2677 | 18740 | 0 |
| R4 cached-rerank · s1 | synthesis | 6184 | 5461–6813 | 1136 | 941–1646 | 0 | 0 | 123 |
| R4 cached-rerank · s3 | rerank | 63438 | 63409–63459 | 346 | 323–378 | 7901 | 55305 | 0 |
| R4 cached-rerank · s3 | synthesis | 6081 | 5435–6813 | 1245 | 935–2125 | 0 | 0 | 226 |
| R3 BM25+rerank · s1 · scoped_absence | rerank | 9020 | 8640–9573 | 347 | 317–372 | 0 | 0 | 0 |
| R3 BM25+rerank · s1 · scoped_absence | synthesis | 6201 | 5924–6922 | 995 | 789–1394 | 0 | 0 | 23 |
| R3 BM25+rerank · s3 · scoped_absence | rerank | 8591 | 7248–9712 | 341 | 315–385 | 0 | 0 | 0 |
| R3 BM25+rerank · s3 · scoped_absence | synthesis | 6193 | 5434–7140 | 1281 | 908–1756 | 0 | 0 | 349 |
| R4 cached-rerank · s1 · scoped_absence | rerank | 21652 | 21623–21675 | 340 | 300–366 | 2678 | 18743 | 0 |
| R4 cached-rerank · s1 · scoped_absence | synthesis | 6194 | 5452–6922 | 988 | 842–1112 | 0 | 0 | 0 |
| R4 cached-rerank · s3 · scoped_absence | rerank | 63437 | 63409–63457 | 349 | 327–376 | 7901 | 55305 | 0 |
| R4 cached-rerank · s3 · scoped_absence | synthesis | 6221 | 5544–6922 | 1079 | 823–1584 | 0 | 0 | 79 |

### Break-even (questions sharing one cache write)

cost_r(N) = P_r + N·c_r with P_r = measured one-off premium of writing the cached prefix (prefix tokens × (write − read) rate) and c_r = measured warm cost per question. N* = (P_a − P_b) / (c_b − c_a).

Scale 1:

| A vs B | A one-off cache-write premium | A warm $/question | B premium | B warm $/question | N* | result |
|---|---|---|---|---|---|---|
| R2 cached+cite vs R3 BM25+rerank | $0.0516 | $0.0188 | $0.0000 | $0.0247 | 8.72 | A cheaper from question 9 |
| R4 cached-rerank vs R3 BM25+rerank | $0.0025 | $0.0241 | $0.0000 | $0.0247 | 4.21 | A cheaper from question 5 |
| R2 cached+cite vs R4 cached-rerank | $0.0516 | $0.0188 | $0.0025 | $0.0241 | 9.22 | A cheaper from question 10 |

Scale 3:

| A vs B | A one-off cache-write premium | A warm $/question | B premium | B warm $/question | N* | result |
|---|---|---|---|---|---|---|
| R2 cached+cite vs R3 BM25+rerank | $0.1491 | $0.0193 | $0.0000 | $0.0278 | 17.54 | A cheaper from question 18 |
| R4 cached-rerank vs R3 BM25+rerank | $0.0073 | $0.0254 | $0.0000 | $0.0278 | 3.13 | A cheaper from question 4 |
| R2 cached+cite vs R4 cached-rerank | $0.1491 | $0.0193 | $0.0073 | $0.0254 | 22.94 | A cheaper from question 23 |

Adopted answer formats (what the app and its portfolio use: retrieval versions on their scoped_absence sessions, full-corpus versions on the original):

Scale 1 (adopted):

| A vs B | A one-off cache-write premium | A warm $/question | B premium | B warm $/question | N* | result |
|---|---|---|---|---|---|---|
| R2 cached+cite vs R3 BM25+rerank | $0.0516 | $0.0188 | $0.0000 | $0.0234 | 11.16 | A cheaper from question 12 |
| R4 cached-rerank vs R3 BM25+rerank | $0.0025 | $0.0227 | $0.0000 | $0.0234 | 3.26 | A cheaper from question 4 |
| R2 cached+cite vs R4 cached-rerank | $0.0516 | $0.0188 | $0.0025 | $0.0227 | 12.70 | A cheaper from question 13 |

Scale 3 (adopted):

| A vs B | A one-off cache-write premium | A warm $/question | B premium | B warm $/question | N* | result |
|---|---|---|---|---|---|---|
| R2 cached+cite vs R3 BM25+rerank | $0.1491 | $0.0193 | $0.0000 | $0.0262 | 21.39 | A cheaper from question 22 |
| R4 cached-rerank vs R3 BM25+rerank | $0.0073 | $0.0241 | $0.0000 | $0.0262 | 3.36 | A cheaper from question 4 |
| R2 cached+cite vs R4 cached-rerank | $0.1491 | $0.0193 | $0.0073 | $0.0241 | 29.52 | A cheaper from question 30 |

### Per question

| group | question | key-fact recall | supplier-specific | citations/answer | zero-citation | contaminated | judge correctness | judge completeness | billed $/question |
|---|---|---|---|---|---|---|---|---|---|
| R1 naive · s1 | audit-01/q1 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | — | — | 0/3 (0%) [0–56] | 4.67 | 5.00 | $0.0461 |
| R1 naive · s1 | audit-01/q2 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | — | — | 0/3 (0%) [0–56] | 4.33 | 5.00 | $0.0459 |
| R1 naive · s1 | audit-01/q3 | 21/21 (100%) [85–100] | 18/18 (100%) [82–100] | — | — | 0/3 (0%) [0–56] | 4.67 | 5.00 | $0.0460 |
| R1 naive · s1 | audit-01/q4 | 15/15 (100%) [80–100] | 9/9 (100%) [70–100] | — | — | 0/3 (0%) [0–56] | 4.33 | 5.00 | $0.0453 |
| R1 naive · s1 | audit-02/q1 | 15/18 (83%) [61–94] | 3/3 (100%) [44–100] | — | — | 0/3 (0%) [0–56] | 4.67 | 5.00 | $0.0458 |
| R1 naive · s1 | audit-02/q2 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | — | — | 0/3 (0%) [0–56] | 4.33 | 4.00 | $0.0462 |
| R1 naive · s1 | audit-02/q3 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | — | — | 0/3 (0%) [0–56] | 5.00 | 5.00 | $0.0458 |
| R1 naive · s1 | audit-02/q4 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | — | — | 0/3 (0%) [0–56] | 4.00 | 4.67 | $0.0465 |
| R1 naive · s3 | audit-01/q1 | 20/21 (95%) [77–99] | 8/9 (89%) [57–98] | — | — | 0/3 (0%) [0–56] | 4.67 | 4.67 | $0.1168 |
| R1 naive · s3 | audit-01/q2 | 20/21 (95%) [77–99] | 20/21 (95%) [77–99] | — | — | 0/3 (0%) [0–56] | 4.67 | 4.33 | $0.1172 |
| R1 naive · s3 | audit-01/q3 | 21/21 (100%) [85–100] | 18/18 (100%) [82–100] | — | — | 0/3 (0%) [0–56] | 4.33 | 5.00 | $0.1175 |
| R1 naive · s3 | audit-01/q4 | 13/15 (87%) [62–96] | 7/9 (78%) [45–94] | — | — | 0/3 (0%) [0–56] | 4.33 | 5.00 | $0.1171 |
| R1 naive · s3 | audit-02/q1 | 16/18 (89%) [67–97] | 3/3 (100%) [44–100] | — | — | 0/3 (0%) [0–56] | 5.00 | 5.00 | $0.1163 |
| R1 naive · s3 | audit-02/q2 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | — | — | 0/3 (0%) [0–56] | 4.00 | 4.67 | $0.1185 |
| R1 naive · s3 | audit-02/q3 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | — | — | 0/3 (0%) [0–56] | 5.00 | 5.00 | $0.1170 |
| R1 naive · s3 | audit-02/q4 | 18/21 (86%) [65–95] | 18/21 (86%) [65–95] | — | — | 0/3 (0%) [0–56] | 4.00 | 4.33 | $0.1178 |
| R2 cached+cite · s1 | audit-01/q1 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 11.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 5.00 | $0.0721 |
| R2 cached+cite · s1 | audit-01/q2 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | 15.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.67 | $0.0176 |
| R2 cached+cite · s1 | audit-01/q3 | 21/21 (100%) [85–100] | 18/18 (100%) [82–100] | 10.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.67 | $0.0159 |
| R2 cached+cite · s1 | audit-01/q4 | 12/15 (80%) [55–93] | 7/9 (78%) [45–94] | 11.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.33 | $0.0190 |
| R2 cached+cite · s1 | audit-02/q1 | 15/18 (83%) [61–94] | 3/3 (100%) [44–100] | 10.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.67 | $0.0179 |
| R2 cached+cite · s1 | audit-02/q2 | 20/21 (95%) [77–99] | 20/21 (95%) [77–99] | 14.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.33 | $0.0198 |
| R2 cached+cite · s1 | audit-02/q3 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 11.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 5.00 | $0.0130 |
| R2 cached+cite · s1 | audit-02/q4 | 19/21 (90%) [71–97] | 19/21 (90%) [71–97] | 10.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.00 | $0.0268 |
| R2 cached+cite · s3 | audit-01/q1 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 10.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.67 | $0.1657 |
| R2 cached+cite · s3 | audit-01/q2 | 20/21 (95%) [77–99] | 20/21 (95%) [77–99] | 15.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.67 | $0.0197 |
| R2 cached+cite · s3 | audit-01/q3 | 21/21 (100%) [85–100] | 18/18 (100%) [82–100] | 9.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 5.00 | $0.0224 |
| R2 cached+cite · s3 | audit-01/q4 | 12/15 (80%) [55–93] | 9/9 (100%) [70–100] | 10.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.67 | $0.0169 |
| R2 cached+cite · s3 | audit-02/q1 | 15/18 (83%) [61–94] | 3/3 (100%) [44–100] | 9.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 5.00 | $0.0207 |
| R2 cached+cite · s3 | audit-02/q2 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | 14.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.00 | $0.0207 |
| R2 cached+cite · s3 | audit-02/q3 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 11.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 5.00 | $0.0168 |
| R2 cached+cite · s3 | audit-02/q4 | 18/21 (86%) [65–95] | 18/21 (86%) [65–95] | 10.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.33 | $0.0202 |
| R3 BM25+rerank · s1 | audit-01/q1 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 11.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 5.00 | $0.0243 |
| R3 BM25+rerank · s1 | audit-01/q2 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | 14.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.33 | 5.00 | $0.0254 |
| R3 BM25+rerank · s1 | audit-01/q3 | 20/21 (95%) [77–99] | 18/18 (100%) [82–100] | 9.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 5.00 | $0.0266 |
| R3 BM25+rerank · s1 | audit-01/q4 | 15/15 (100%) [80–100] | 9/9 (100%) [70–100] | 10.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 5.00 | $0.0231 |
| R3 BM25+rerank · s1 | audit-02/q1 | 15/18 (83%) [61–94] | 3/3 (100%) [44–100] | 8.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.67 | $0.0225 |
| R3 BM25+rerank · s1 | audit-02/q2 | 20/21 (95%) [77–99] | 20/21 (95%) [77–99] | 13.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 3.67 | $0.0240 |
| R3 BM25+rerank · s1 | audit-02/q3 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 11.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 5.00 | $0.0233 |
| R3 BM25+rerank · s1 | audit-02/q4 | 19/21 (90%) [71–97] | 19/21 (90%) [71–97] | 10.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.33 | 4.00 | $0.0286 |
| R3 BM25+rerank · s3 | audit-01/q1 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 8.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 3.67 | 4.67 | $0.0237 |
| R3 BM25+rerank · s3 | audit-01/q2 | 20/21 (95%) [77–99] | 20/21 (95%) [77–99] | 11.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.00 | 4.00 | $0.0282 |
| R3 BM25+rerank · s3 | audit-01/q3 | 20/21 (95%) [77–99] | 17/18 (94%) [74–99] | 8.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.67 | $0.0261 |
| R3 BM25+rerank · s3 | audit-01/q4 | 12/15 (80%) [55–93] | 9/9 (100%) [70–100] | 9.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.00 | 4.67 | $0.0245 |
| R3 BM25+rerank · s3 | audit-02/q1 | 15/18 (83%) [61–94] | 3/3 (100%) [44–100] | 8.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.67 | $0.0269 |
| R3 BM25+rerank · s3 | audit-02/q2 | 18/21 (86%) [65–95] | 18/21 (86%) [65–95] | 11.7 | 0/3 (0%) [0–56] | 1/3 (33%) [6–79] | 3.67 | 3.00 | $0.0297 |
| R3 BM25+rerank · s3 | audit-02/q3 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 8.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.33 | 5.00 | $0.0285 |
| R3 BM25+rerank · s3 | audit-02/q4 | 18/21 (86%) [65–95] | 18/21 (86%) [65–95] | 7.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 2.33 | 3.00 | $0.0345 |
| R4 cached-rerank · s1 | audit-01/q1 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 10.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.67 | $0.0281 |
| R4 cached-rerank · s1 | audit-01/q2 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | 15.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.33 | 5.00 | $0.0228 |
| R4 cached-rerank · s1 | audit-01/q3 | 21/21 (100%) [85–100] | 18/18 (100%) [82–100] | 9.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.00 | 5.00 | $0.0250 |
| R4 cached-rerank · s1 | audit-01/q4 | 13/15 (87%) [62–96] | 8/9 (89%) [57–98] | 10.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.33 | 5.00 | $0.0235 |
| R4 cached-rerank · s1 | audit-02/q1 | 16/18 (89%) [67–97] | 3/3 (100%) [44–100] | 8.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 5.00 | $0.0233 |
| R4 cached-rerank · s1 | audit-02/q2 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | 13.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.00 | $0.0233 |
| R4 cached-rerank · s1 | audit-02/q3 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 10.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 5.00 | $0.0254 |
| R4 cached-rerank · s1 | audit-02/q4 | 20/21 (95%) [77–99] | 20/21 (95%) [77–99] | 10.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.00 | $0.0242 |
| R4 cached-rerank · s3 | audit-01/q1 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 9.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.00 | $0.0349 |
| R4 cached-rerank · s3 | audit-01/q2 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | 14.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.33 | 5.00 | $0.0231 |
| R4 cached-rerank · s3 | audit-01/q3 | 21/21 (100%) [85–100] | 18/18 (100%) [82–100] | 8.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.00 | 4.67 | $0.0248 |
| R4 cached-rerank · s3 | audit-01/q4 | 14/15 (93%) [70–99] | 8/9 (89%) [57–98] | 9.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.67 | $0.0246 |
| R4 cached-rerank · s3 | audit-02/q1 | 15/18 (83%) [61–94] | 3/3 (100%) [44–100] | 9.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.33 | 4.67 | $0.0266 |
| R4 cached-rerank · s3 | audit-02/q2 | 19/21 (90%) [71–97] | 19/21 (90%) [71–97] | 14.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.33 | 4.00 | $0.0243 |
| R4 cached-rerank · s3 | audit-02/q3 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 10.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.00 | 5.00 | $0.0247 |
| R4 cached-rerank · s3 | audit-02/q4 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | 9.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.00 | 4.00 | $0.0279 |
| R3 BM25+rerank · s1 · scoped_absence | audit-01/q1 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 11.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.33 | 4.67 | $0.0231 |
| R3 BM25+rerank · s1 · scoped_absence | audit-01/q2 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | 12.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 5.00 | $0.0225 |
| R3 BM25+rerank · s1 · scoped_absence | audit-01/q3 | 20/21 (95%) [77–99] | 18/18 (100%) [82–100] | 9.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 5.00 | $0.0241 |
| R3 BM25+rerank · s1 · scoped_absence | audit-01/q4 | 14/15 (93%) [70–99] | 9/9 (100%) [70–100] | 9.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.33 | $0.0239 |
| R3 BM25+rerank · s1 · scoped_absence | audit-02/q1 | 15/18 (83%) [61–94] | 3/3 (100%) [44–100] | 7.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.67 | $0.0223 |
| R3 BM25+rerank · s1 · scoped_absence | audit-02/q2 | 19/21 (90%) [71–97] | 19/21 (90%) [71–97] | 13.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.00 | $0.0245 |
| R3 BM25+rerank · s1 · scoped_absence | audit-02/q3 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 10.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 5.00 | $0.0230 |
| R3 BM25+rerank · s1 · scoped_absence | audit-02/q4 | 19/21 (90%) [71–97] | 19/21 (90%) [71–97] | 10.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 3.33 | 4.00 | $0.0242 |
| R3 BM25+rerank · s3 · scoped_absence | audit-01/q1 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 8.7 | 0/3 (0%) [0–56] | 1/3 (33%) [6–79] | 4.33 | 4.00 | $0.0257 |
| R3 BM25+rerank · s3 · scoped_absence | audit-01/q2 | 18/21 (86%) [65–95] | 18/21 (86%) [65–95] | 10.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.00 | $0.0242 |
| R3 BM25+rerank · s3 · scoped_absence | audit-01/q3 | 20/21 (95%) [77–99] | 18/18 (100%) [82–100] | 8.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.00 | $0.0238 |
| R3 BM25+rerank · s3 · scoped_absence | audit-01/q4 | 12/15 (80%) [55–93] | 9/9 (100%) [70–100] | 8.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.33 | 4.33 | $0.0234 |
| R3 BM25+rerank · s3 · scoped_absence | audit-02/q1 | 15/18 (83%) [61–94] | 3/3 (100%) [44–100] | 6.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.00 | $0.0265 |
| R3 BM25+rerank · s3 · scoped_absence | audit-02/q2 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | 14.0 | 0/3 (0%) [0–56] | 1/3 (33%) [6–79] | 4.00 | 4.00 | $0.0275 |
| R3 BM25+rerank · s3 · scoped_absence | audit-02/q3 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 8.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 5.00 | $0.0269 |
| R3 BM25+rerank · s3 · scoped_absence | audit-02/q4 | 16/21 (76%) [55–89] | 16/21 (76%) [55–89] | 7.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 3.00 | 2.67 | $0.0318 |
| R4 cached-rerank · s1 · scoped_absence | audit-01/q1 | 20/21 (95%) [77–99] | 9/9 (100%) [70–100] | 10.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.33 | $0.0240 |
| R4 cached-rerank · s1 · scoped_absence | audit-01/q2 | 20/21 (95%) [77–99] | 20/21 (95%) [77–99] | 12.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.67 | $0.0219 |
| R4 cached-rerank · s1 · scoped_absence | audit-01/q3 | 21/21 (100%) [85–100] | 18/18 (100%) [82–100] | 8.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 5.00 | $0.0240 |
| R4 cached-rerank · s1 · scoped_absence | audit-01/q4 | 15/15 (100%) [80–100] | 9/9 (100%) [70–100] | 9.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.67 | $0.0219 |
| R4 cached-rerank · s1 · scoped_absence | audit-02/q1 | 15/18 (83%) [61–94] | 3/3 (100%) [44–100] | 7.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.67 | $0.0217 |
| R4 cached-rerank · s1 · scoped_absence | audit-02/q2 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | 13.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.00 | $0.0237 |
| R4 cached-rerank · s1 · scoped_absence | audit-02/q3 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 10.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.33 | 5.00 | $0.0227 |
| R4 cached-rerank · s1 · scoped_absence | audit-02/q4 | 20/21 (95%) [77–99] | 20/21 (95%) [77–99] | 9.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.00 | $0.0240 |
| R4 cached-rerank · s3 · scoped_absence | audit-01/q1 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 10.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.00 | 4.67 | $0.0301 |
| R4 cached-rerank · s3 · scoped_absence | audit-01/q2 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | 12.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.33 | 5.00 | $0.0227 |
| R4 cached-rerank · s3 · scoped_absence | audit-01/q3 | 21/21 (100%) [85–100] | 18/18 (100%) [82–100] | 9.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.67 | $0.0246 |
| R4 cached-rerank · s3 · scoped_absence | audit-01/q4 | 13/15 (87%) [62–96] | 9/9 (100%) [70–100] | 9.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.67 | $0.0224 |
| R4 cached-rerank · s3 · scoped_absence | audit-02/q1 | 16/18 (89%) [67–97] | 3/3 (100%) [44–100] | 7.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.33 | $0.0256 |
| R4 cached-rerank · s3 · scoped_absence | audit-02/q2 | 20/21 (95%) [77–99] | 20/21 (95%) [77–99] | 14.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.00 | $0.0243 |
| R4 cached-rerank · s3 · scoped_absence | audit-02/q3 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 10.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 5.00 | $0.0264 |
| R4 cached-rerank · s3 · scoped_absence | audit-02/q4 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | 10.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.00 | 4.00 | $0.0238 |

## Zero-citation and contaminated answers

No zero-citation answers on a citation rung.

| source | group | question | distractor values | distractor chunks cited |
|---|---|---|---|---|
| rerun | R3 BM25+rerank · s3 r2 | audit-02/q2 | 9.25 (narmada, a2q2-gst-dispute-6-85, other supplier named nearby) | — |
| rerun | R3 BM25+rerank · s3 r1 | audit-01/q1 | 3.60 Cr (kaveri, a1q1-cap-4-50-cr, other supplier named nearby) | — |
| rerun | R3 BM25+rerank · s3 r1 | audit-02/q2 | 9.25 (narmada, a2q2-gst-dispute-6-85, other supplier named nearby) | — |

## Absence-claim detector validation

Known absence claims: the judge's material errors on the two retrieval rungs (original answer format) whose quoted claim matches the validation report's keyword rule — 18. Detector flags 18/18 (100%); by form: corpus 10, scoped 8.

Documents-lack claims the detector finds in cached full-corpus answers (that rung saw every clause; the judge reported a material error on 0 of these answers): 8.

- s1 r0 audit-01/q1: The documents state no INR ceiling for Schedules C and D.
- s1 r0 audit-01/q2: The documents give no INR total for the peak exposure.
- s1 r0 audit-02/q1: The documents give no rupee figure for the escrow.
- s1 r2 audit-02/q1: The documents state no INR figure for any specific escrow.
- s3 r0 audit-02/q1: The documents do not specify an escrow bank or NOC for this mechanism.
- s3 r1 audit-01/q1: The documents state no insurance limit for Schedule D.
- s3 r1 audit-01/q1: The documents specify no named insurer other than an IRDAI-licensed one for the product policy.
- s3 r1 audit-02/q1: The documents do not specify a separate banking NOC or escrow-bank gate for this mechanism.

## For lead review

Items a person should read before quoting any number from this file.

### Material errors reported by the judge

| source | group | question | claim | problem | source quote |
|---|---|---|---|---|---|
| rerun | R1 naive · s1 r2 | audit-01/q4 | NovaMart CISO/DPO must confirm the Munich firewall in writing (Clause SL.1(2)) | SL.1(2) sets the telemetry firewall as a continuing condition but does not require written CISO/DPO confirmation before allotment; CISO and DPO authorization appears only in B.2(b), for cross-border a | Neither KroneVolt GmbH, its Munich R&D engineers, nor its nominee director shall receive API keys, bulk telemetry exports, or remote SSH access to Indian customer IoT data or AWS ap-south-1/ap-south-2 |
| rerun | R1 naive · s3 r0 | audit-01/q2 | Deductions are credit-note based, so they interact with CGST Section 34 adjustments and remain outside the MSA Clause 9.1 cap analysis. | Section 34 credit notes appear only for volume rebates in SL.3, and no document says Addendum A peak deductions sit outside the Clause 9.1 aggregate cap. | ABSENT |
| rerun | R1 naive · s3 r0 | audit-02/q4 | so peak LDs and GST debits are the only uncapped recovery routes | Peak LDs are excluded from the 3.25% ceiling but are themselves capped at 6.50% of Festive Peak PO landed value, so they are not uncapped; 'only' also ignores the Clause 9.2 uncapped carve-outs. | Combined dock fees and fill-rate deductions under Clause A.4 are capped at 6.50% of total Festive Peak PO landed value |
| rerun | R1 naive · s3 r1 | audit-02/q2 | A final order against Deccan would not be capped, because MSA Cl. 9.2(b)(iii) and TAX-GST-ITC-2026 Cl. D.4 keep tax-fraud indemnity uncapped. | The Maharashtra demand is Deccan's own non-fraud Section 73 tax dispute, whereas the uncapped carve-out covers indemnifying NovaMart for fraudulent invoicing, blocked ITC under Section 16(2)(c), Secti | non-fraud classification confirmed after withdrawal of initial Section 74 allegations |
| rerun | R3 BM25+rerank · s3 r0 | audit-02/q2 | The documents state no other gates. | Other gates exist for equity or control changes: Side Letter #2 requires the SBI NOC at least 5 business days before allotment plus a telemetry firewall, and MSA Clause 11.4 requires 30 days' prior no | Deccan must deliver a certified copy of State Bank of India's written No-Objection Certificate ('NOC') satisfying SBI's Negative Covenant Clause 14.3 under MCA Form CHG-1 Charge ID 100884129 at least  |
| rerun | R3 BM25+rerank · s3 r0 | audit-02/q4 | The excerpts give no MSA baseline SLA cap, so the Addendum A versus MSA cap contrast cannot be quantified. | MSA Clause 4 expressly sets a 2.0% baseline monthly SLA penalty cap, and Addendum A Clause A.4(c) explicitly overrides it with 6.50%. | subject to an overall baseline monthly SLA penalty cap of 2.0% of total monthly invoiced PO value |
| rerun | R3 BM25+rerank · s3 r1 | audit-02/q2 | Note 21 warranty retrofit reserve is not in the provided deal-room text | Note 21 is present in DOC-06 and gives a closing warranty reserve of INR 2.85 Cr and details of the retrofit. | leaving a closing Warranty Reserve of INR 2.85 Crore as of March 31, 2026 |
| rerun | R3 BM25+rerank · s3 r1 | audit-02/q2 | obtain the Note 21 warranty retrofit reserve disclosure, which is currently missing from the record | The disclosure is already in the record, so this recommended gate rests on a false premise. | NOTE 21 (PROVISIONS FOR PRODUCT WARRANTY & PROACTIVE FIELD RETROFIT) |
| rerun | R3 BM25+rerank · s3 r1 | audit-02/q4 | The MSA baseline cap is not in the excerpts, so that contrast cannot be quantified. | The MSA baseline cap is expressly stated in the documents as 2.0% of total monthly invoiced PO value. | subject to an overall baseline monthly SLA penalty cap of 2.0% of total monthly invoiced PO value |
| rerun | R3 BM25+rerank · s3 r1 | audit-02/q4 | Legal must obtain the full Addendum A and the MSA baseline cap, which are missing here. | Both Addendum A (Clauses A.1–A.5) and the MSA baseline cap are present in the deal room, and A.4(c) itself states that 6.50% overrides the 2.0% cap. | capped at 6.50% of total Festive Peak PO landed value (explicitly overriding the baseline 2.0% monthly cap in MSA Clause 4) |
| rerun | R3 BM25+rerank · s3 r2 | audit-01/q1 | The documents specify no banking NOC or escrow gate. | The documents do require an SBI No-Objection Certificate as a Condition Precedent to the KroneVolt waiver, and Schedule D sets up a GST Tax Compliance Escrow Holdback. | Deccan must deliver a certified copy of State Bank of India's written No-Objection Certificate ('NOC') satisfying SBI's Negative Covenant Clause 14.3 |
| rerun | R3 BM25+rerank · s3 r2 | audit-01/q4 | The text names the CMK owner and rotation cycle but does not state a KMS key region. | The deal room does locate the KMS realms in the Indian AWS regions, so this assertion is unsupported and leaves the key-residency question unanswered. | remote SSH access to Indian customer IoT data or AWS ap-south-1/ap-south-2 KMS realms, maintaining strict compliance with Schedule B (Clause B.2) |
| rerun | R3 BM25+rerank · s3 r2 | audit-02/q2 | The documents do not specify other gates. | Side Letter #2 also conditions the KroneVolt waiver on delivering the SBI NOC at least 5 business days before allotment and on an absolute telemetry firewall, and MSA 11.4 requires 30 days' prior noti | STRICTLY CONTINGENT ON two continuing Conditions Precedent prior to share allotment |
| rerun | R3 BM25+rerank · s3 r2 | audit-02/q4 | The MSA baseline SLA cap is not in the supplied Deccan text, so the Addendum A vs MSA comparison cannot be quantified. | MSA Clause 4 explicitly sets a 2.0% baseline monthly SLA penalty cap, and Addendum A expressly overrides it. | subject to an overall baseline monthly SLA penalty cap of 2.0% of total monthly invoiced PO value |
| rerun | R3 BM25+rerank · s3 r2 | audit-02/q4 | The supplied text specifies no banking NOC or escrow gate. | Side Letter #2 conditions the waiver on an SBI NOC, and Schedule D provides an 18% GST escrow holdback. | Deliver a certified copy of State Bank of India's written No-Objection Certificate ('NOC') satisfying SBI's Negative Covenant Clause 14.3 |
| rerun | R4 cached-rerank · s1 r1 | audit-01/q3 | The deal room does not quantify DPDP Act or CERT-In penalties for the telemetry condition. | Schedule B Clause B.4 does quantify DPDP penalty exposure (up to INR 250 Crore and INR 200 Crore) and requires INR 15 Crore of cyber insurance, all uncapped against Deccan. | which carry statutory maximums up to INR 250 Crore under the Schedule to the DPDP Act, 2023 for failure to maintain reasonable security safeguards to prevent personal data breaches, and up to INR 200  |
| rerun | R4 cached-rerank · s3 r0 | audit-02/q2 | The provided text does not state what dilution the KroneVolt 26% change-of-control would cause, so confirm whether it triggers the 25.0% threshold. | The documents explicitly state that KroneVolt takes 26.0% of post-money fully diluted voting equity, which exceeds 25.0% and triggers the SBI NOC, a condition Side Letter #2 expressly imposes. | KroneVolt Energy Systems GmbH (Munich, Germany) will subscribe for 26.0% of Deccan's post-money fully diluted voting equity |
| rerun | R4 cached-rerank · s3 r0 | audit-02/q3 | The documents do not specify any banking NOC or escrow gate. | The deal room does specify an SBI NOC condition precedent (Side Letter SL.1 and SBI Negative Covenant 14.3) and a GST tax escrow holdback (Schedule D Clause D.2), so this statement is false. | Deccan must deliver a certified copy of State Bank of India's written No-Objection Certificate ('NOC') satisfying SBI's Negative Covenant Clause 14.3 |
| rerun | R4 cached-rerank · s3 r0 | audit-02/q4 | No banking NOC or escrow gate appears in these excerpts. | The documents do contain an SBI NOC condition precedent and a GST tax escrow holdback, so this statement is false. | Deccan must deliver a certified copy of State Bank of India's written No-Objection Certificate ('NOC') satisfying SBI's Negative Covenant Clause 14.3 |
| rerun | R4 cached-rerank · s3 r2 | audit-01/q3 | The documents give no DPDP or CERT-In penalty figures. | Schedule B Clause B.4 explicitly gives DPDP penalty maximums of INR 250 Crore and INR 200 Crore and a minimum cyber insurance of INR 15.00 Crore, so stating that no figures exist misrepresents the unc | which carry statutory maximums up to INR 250 Crore under the Schedule to the DPDP Act, 2023 for failure to maintain reasonable security safeguards to prevent personal data breaches, and up to INR 200  |
| rerun | R4 cached-rerank · s3 r2 | audit-02/q3 | The documents contain no banking NOC or escrow gate. | The deal room does contain an SBI NOC condition precedent in Side Letter #2 and a GST escrow holdback in Schedule D. | Deccan must deliver a certified copy of State Bank of India's written No-Objection Certificate ('NOC') satisfying SBI's Negative Covenant Clause 14.3 |
| rerun | R4 cached-rerank · s3 r2 | audit-02/q4 | The deal room contains no banking NOC or escrow terms beyond the Schedule D reference, so none can be confirmed. | The deal room does contain SBI NOC terms (Note 18 Negative Covenant 14.3 and SL.1 Condition Precedent 1), and Schedule D sets out detailed escrow holdback terms, so this statement misrepresents the do | Deccan must deliver a certified copy of State Bank of India's written No-Objection Certificate ('NOC') satisfying SBI's Negative Covenant Clause 14.3 |
| rerun | R3 BM25+rerank · s1 · scoped_absence r0 | audit-02/q4 | The Schedule D GST escrow terms and any banking NOC are not in the text provided. | Both items are in the deal room: Schedule D Clause D.2 sets out the 18% GST escrow holdback, and SL.1 and Note 18 require an SBI NOC before the KroneVolt share allotment. | NovaMart withholds ONLY the 18% GST tax component (CGST 9% + SGST 9% on intra-Karnataka Peenya-to-FC-BLR-01 supplies, or IGST 18% on inter-state dispatches to FC-BOM-02/FC-HYD-01/FC-DEL-03) in a non-i |
| rerun | R3 BM25+rerank · s1 · scoped_absence r2 | audit-02/q4 | The 3.25% clawback ceiling is a separate limit on co-op, banner, and marketing deductions, so the 3.50% top rebate tier is not capped by it. | SL.3 expressly includes volume rebate clawbacks within the 3.25% ceiling, so the claim that the rebate tier is not capped contradicts the clause. | aggregate annual promotional co-op fees, catalog banner charges, marketing deductions, and volume rebate clawbacks claimed by NovaMart against Deccan ... shall NEVER exceed a hard contractual ceiling  |
| rerun | R3 BM25+rerank · s3 · scoped_absence r0 | audit-02/q4 | the MSA baseline cap and the A.4 text are not in the text provided, so the two caps cannot be contrasted | Both caps are in the documents: MSA Clause 4 sets a 2.0% monthly cap, and Addendum A Clause A.4(c) sets 6.50% and expressly overrides it. | Combined dock fees and fill-rate deductions under Clause A.4 are capped at 6.50% of total Festive Peak PO landed value (explicitly overriding the baseline 2.0% monthly cap in MSA Clause 4) |
| rerun | R3 BM25+rerank · s3 · scoped_absence r1 | audit-02/q4 | The MSA baseline Peak SLA cap is not in the text provided. | The MSA baseline cap is stated as 2.0% of total monthly invoiced PO value, and Addendum A expressly overrides it, so the claim that it is absent is false and drops a requested comparison. | subject to an overall baseline monthly SLA penalty cap of 2.0% of total monthly invoiced PO value |
| rerun | R3 BM25+rerank · s3 · scoped_absence r2 | audit-02/q4 | The MSA baseline cap and Clause A.4 text are not in the text provided, so that contrast cannot be completed. | Both provisions appear in the deal room, so the contrast was possible and was wrongly abandoned. | subject to an overall baseline monthly SLA penalty cap of 2.0% of total monthly invoiced PO value |
| rerun | R3 BM25+rerank · s3 · scoped_absence r2 | audit-02/q4 | Addendum A's 6.5% cap is cited only in SL.4. | The 6.50% peak cap is set out directly in Addendum A Clause A.4(c), not only in SL.4. | Combined dock fees and fill-rate deductions under Clause A.4 are capped at 6.50% of total Festive Peak PO landed value (explicitly overriding the baseline 2.0% monthly cap in MSA Clause 4) |
| rerun | R4 cached-rerank · s3 · scoped_absence r0 | audit-02/q4 | The 6.5% cap exceeds the 3.25% ceiling, so the two are not stackable. | The 3.25% ceiling expressly excludes Addendum A Clause A.4 Peak liquidated damages, so the two caps are independent and can apply cumulatively; nothing supports a 'not stackable' conclusion. | (EXPRESSLY EXCLUDING punitive Peak SLA liquidated damages assessed under Addendum A Clause A.4 and GST escrow/debit adjustments under Schedule D) shall NEVER exceed a hard contractual ceiling of 3.25% |
| rerun | R4 cached-rerank · s3 · scoped_absence r2 | audit-01/q1 | No banking NOC, escrow, or delisting gate is stated in the text provided. | The documents do contain these mechanisms: a GST escrow holdback (Schedule D), an EPR delisting trigger (Schedule C) and an SBI NOC condition (Side Letter #2). | NovaMart is expressly authorized to automatically delist, suppress Buy-Box visibility, and inventory-freeze all Deccan battery and appliance ASINs effective December 15, 2026 |

### Contaminated-answer excerpts

- rerun R3 BM25+rerank s3 r2 audit-02/q2: `9.25` (narmada — other supplier named within 150 chars) — …tatutory Auditors issued an unmodified (clean) audit opinion on AOC-4 FY26 (SRN AB9920411). DOC-20 (Narmada, TN GST INR 9.25 Cr) is excluded as it is not Deccan's contract.  - **Key Clauses & Override Mechanics**: CARO 2020 Para 3(vii)(b): Maha…
- rerun R3 BM25+rerank s3 r1 audit-01/q1: `3.60 Cr` (kaveri — other supplier named within 150 chars) — …Schedules B, C and D untouched and fully enforceable alongside the Clause 9.2 carve-outs. (The Kaveri MSA, with its INR 3.60 Cr cap, is a different supplier and is excluded.)  - **Key Clauses & Override Mechanics**: Clause 9.2 states nothing in Cl…
- rerun R3 BM25+rerank s3 r1 audit-02/q2: `9.25` (narmada — other supplier named within 150 chars) — …(clean) audit opinion on AOC-4 financials. Deccan's own disputed GST demand is Maharashtra (DOC-06); the Tamil Nadu INR 9.25 Cr notice (DOC-20) concerns Narmada, so it is excluded.  - **Key Clauses & Override Mechanics**: The Maharashtra GST Or…

- The answer key was written from the question texts and Deccan chunks only; one dry pass over the golden answers added format variants (see key `meta.format_variants_added`).
- Golden capture: audit-02 questions read a cache written by audit-01 (no write), n = 1 per cell.
- BM25 phrase bonuses and chunk keywords in `retriever.py` / fixtures were tuned on these questions and Deccan values; rung 3 retrieval recall is optimistic for unseen questions.
- Four original questions (audit-01/q2, q3; audit-02/q3, q4) do not name the supplier; the rerun's scope line names it. Golden answers were scored on the unscoped questions.
- The contamination detector cannot flag a distractor value that also occurs in Deccan's own documents; such values are excluded.

## Data quality

- error sessions: 5
  - {"rung_id": "naive_full_corpus", "scale": 3, "repeat_index": 0, "run_id": "6aefd50d-c43f-4b70-a5a1-de57b23bf2dc", "error_message": "q1 (audit-01/q1): APIConnectionError: Connection error."}
  - {"rung_id": "cached_rerank_hybrid", "scale": 3, "repeat_index": 2, "run_id": "85aacb99-eddd-4677-9729-bcbf5cafd077", "error_message": "q2 (audit-01/q2): BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.'}, 'request_id': 'req_011ChQsb4vooWQJwcFJx96SU'}"}
  - {"rung_id": "hybrid_rag_rerank_citations", "scale": 1, "repeat_index": 2, "run_id": "d1ac7d3d-b628-4009-9dfb-52c1af017e26", "error_message": "q5 (audit-02/q1): BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.'}, 'request_id': 'req_011ChQsbGVpufcL7rxvcpxyE'}"}
  - {"rung_id": "cached_rerank_hybrid", "scale": 1, "repeat_index": 2, "run_id": "1325b457-9e41-48ce-9ee7-f633e0b75235", "error_message": "q5 (audit-02/q1): BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.'}, 'request_id': 'req_011ChQsbL1fSngnGXczE5Ega'}"}
  - {"rung_id": "hybrid_rag_rerank_citations", "scale": 3, "repeat_index": 2, "run_id": "0d99b838-0be0-4c56-b1ec-7445c3de2197", "error_message": "q3 (audit-01/q3): BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.'}, 'request_id': 'req_011ChQsbSLfixPRJJK7BV2bh'}"}
- non end turn calls: 0
- model mismatches: 0
- cache anomalies: 0
- haiku calls over 100k prompt: 0
- superseded: recorded at a different output cap (excluded from every table): 0
- judge failed calls: 64
  - {"call_id": "judge:rerun:hybrid_rag_rerank_citations:s1:r0:scoped_absence:audit-01:q1:j0", "status": "error", "error_type": "api_error", "error_message": "BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.'}, 'request_id': 'req_011ChQsbXWj19Hst1Hitkyox'}"}
  - {"call_id": "judge:rerun:hybrid_rag_rerank_citations:s1:r0:scoped_absence:audit-01:q2:j0", "status": "error", "error_type": "api_error", "error_message": "BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.'}, 'request_id': 'req_011ChQsbZ1kaVJYpWMKJ4NPP'}"}
  - {"call_id": "judge:rerun:hybrid_rag_rerank_citations:s1:r0:scoped_absence:audit-01:q3:j0", "status": "error", "error_type": "api_error", "error_message": "BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.'}, 'request_id': 'req_011ChQsbZFehj8zsUyhEdxEX'}"}
  - {"call_id": "judge:rerun:hybrid_rag_rerank_citations:s1:r0:scoped_absence:audit-01:q4:j0", "status": "error", "error_type": "api_error", "error_message": "BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.'}, 'request_id': 'req_011ChQsbZFQ1ckC9yBit3avM'}"}
  - {"call_id": "judge:rerun:hybrid_rag_rerank_citations:s1:r0:scoped_absence:audit-02:q1:j0", "status": "error", "error_type": "api_error", "error_message": "BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.'}, 'request_id': 'req_011ChQsbZEQ8iWzfBp5haZoz'}"}
  - {"call_id": "judge:rerun:hybrid_rag_rerank_citations:s1:r0:scoped_absence:audit-02:q2:j0", "status": "error", "error_type": "api_error", "error_message": "BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.'}, 'request_id': 'req_011ChQsbaKPr8zpn5zmjHP43'}"}
  - {"call_id": "judge:rerun:hybrid_rag_rerank_citations:s1:r0:scoped_absence:audit-02:q3:j0", "status": "error", "error_type": "api_error", "error_message": "BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.'}, 'request_id': 'req_011ChQsbaixF1A6EGqU5f7KZ'}"}
  - {"call_id": "judge:rerun:hybrid_rag_rerank_citations:s1:r0:scoped_absence:audit-02:q4:j0", "status": "error", "error_type": "api_error", "error_message": "BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.'}, 'request_id': 'req_011ChQsbar8uQQeSX1r2ChHL'}"}
  - {"call_id": "judge:rerun:hybrid_rag_rerank_citations:s1:r1:scoped_absence:audit-01:q1:j0", "status": "error", "error_type": "api_error", "error_message": "BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.'}, 'request_id': 'req_011ChQsbar9Wq3JFYSbwTngr'}"}
  - {"call_id": "judge:rerun:hybrid_rag_rerank_citations:s1:r1:scoped_absence:audit-01:q2:j0", "status": "error", "error_type": "api_error", "error_message": "BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.'}, 'request_id': 'req_011ChQsbbyMTtqFqFak2JBMF'}"}
  - {"call_id": "judge:rerun:hybrid_rag_rerank_citations:s1:r1:scoped_absence:audit-01:q3:j0", "status": "error", "error_type": "api_error", "error_message": "BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.'}, 'request_id': 'req_011ChQsbc8nTuRpNFKxBUc8k'}"}
  - {"call_id": "judge:rerun:hybrid_rag_rerank_citations:s1:r1:scoped_absence:audit-02:q1:j0", "status": "error", "error_type": "api_error", "error_message": "BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.'}, 'request_id': 'req_011ChQsbcCzb5KFTuZ5VEVm2'}"}
  - {"call_id": "judge:rerun:hybrid_rag_rerank_citations:s1:r1:scoped_absence:audit-01:q4:j0", "status": "error", "error_type": "api_error", "error_message": "BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.'}, 'request_id': 'req_011ChQsbcHxVUaTZpWNnAhPe'}"}
  - {"call_id": "judge:rerun:hybrid_rag_rerank_citations:s1:r1:scoped_absence:audit-02:q2:j0", "status": "error", "error_type": "api_error", "error_message": "BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.'}, 'request_id': 'req_011ChQsbdMhkpAatf3SM2Q1N'}"}
  - {"call_id": "judge:rerun:hybrid_rag_rerank_citations:s1:r1:scoped_absence:audit-02:q3:j0", "status": "error", "error_type": "api_error", "error_message": "BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.'}, 'request_id': 'req_011ChQsbdYc7oYQsUKwZcUMW'}"}
  - … 49 more (see JSON)
- judge non end turn: 0
- judge model mismatches: 0
- judge cache misses: 0
- judgements not matching a scored answer: 24
  - {"call_id": "judge:golden:naive_full_corpus:s1:r0:audit-01:q1:j0", "status": "ok", "source": "golden", "run_id": null}
  - {"call_id": "judge:golden:cached_full_corpus_citations:s1:r0:audit-01:q1:j0", "status": "ok", "source": "golden", "run_id": null}
  - {"call_id": "judge:golden:naive_full_corpus:s1:r0:audit-01:q4:j0", "status": "ok", "source": "golden", "run_id": null}
  - {"call_id": "judge:golden:naive_full_corpus:s1:r0:audit-01:q3:j0", "status": "ok", "source": "golden", "run_id": null}
  - {"call_id": "judge:golden:naive_full_corpus:s1:r0:audit-01:q2:j0", "status": "ok", "source": "golden", "run_id": null}
  - {"call_id": "judge:golden:cached_full_corpus_citations:s1:r0:audit-01:q3:j0", "status": "ok", "source": "golden", "run_id": null}
  - {"call_id": "judge:golden:cached_full_corpus_citations:s1:r0:audit-01:q2:j0", "status": "ok", "source": "golden", "run_id": null}
  - {"call_id": "judge:golden:cached_full_corpus_citations:s1:r0:audit-01:q4:j0", "status": "ok", "source": "golden", "run_id": null}
  - {"call_id": "judge:golden:hybrid_rag_rerank_citations:s1:r0:audit-01:q1:j0", "status": "ok", "source": "golden", "run_id": null}
  - {"call_id": "judge:golden:hybrid_rag_rerank_citations:s1:r0:audit-01:q3:j0", "status": "ok", "source": "golden", "run_id": null}
  - {"call_id": "judge:golden:hybrid_rag_rerank_citations:s1:r0:audit-01:q2:j0", "status": "ok", "source": "golden", "run_id": null}
  - {"call_id": "judge:golden:naive_full_corpus:s1:r0:audit-02:q1:j0", "status": "ok", "source": "golden", "run_id": null}
  - {"call_id": "judge:golden:hybrid_rag_rerank_citations:s1:r0:audit-01:q4:j0", "status": "ok", "source": "golden", "run_id": null}
  - {"call_id": "judge:golden:naive_full_corpus:s1:r0:audit-02:q2:j0", "status": "ok", "source": "golden", "run_id": null}
  - {"call_id": "judge:golden:naive_full_corpus:s1:r0:audit-02:q3:j0", "status": "ok", "source": "golden", "run_id": null}
  - … 9 more (see JSON)
- scored answers without judgement: 24
