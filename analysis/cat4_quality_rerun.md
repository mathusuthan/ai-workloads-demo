# Category 4 — without vs with hybrid retrieval paired with context caching

Without: the whole corpus as uncached plain text, no citations; Sonnet 5.5 answers. With: Haiku 5.5 picks 5 clauses from the cached corpus and Sonnet 5.5 answers over them with native citations. Both corpus sizes: 1× (the app's 7-document deal room) and 3× (21 documents: two other suppliers' look-alike contracts added).

Generated 2026-11-26T11:10:20.324243+00:00 · answer key `2026-11-25.1` · sessions 12 · judgements 96 (judge claude-opus-5-5, spend $2.4549)

Sources: `/Users/mathu/Projects/NuSysDesPrac/novamart-ai-archetypes/backend/experiments/cat4_quality/runs.jsonl`, `/Users/mathu/Projects/NuSysDesPrac/novamart-ai-archetypes/backend/experiments/cat4_quality/judgements.jsonl`, `app/data/cat4_quality_keys.json`. Every answer is scored; zero-citation, truncated and contaminated answers are reported, never dropped. Rates show hits/total (rate) [Wilson 95%]. Costs come from recorded tokens via `compute_run_finops` (billed = as recorded; cold = the cached call writes its whole prefix on question 1 of the session and reads after; warm = every cached-prefix token read).

Question scope line: every question is asked as `Deal room under audit: DR-NM-DECCAN-2026-Q4 (supplier: Deccan Smart Appliances & Energy Pvt. Ltd.). Answer for this supplier's contracts only.` followed by a blank line and the question — identically for both versions and both corpus sizes, in the synthesis message and Haiku's clause-pick query. The judge sees each answer's question as asked.

Synthesis prompts: without the lever (whole corpus) the app prompt; with it (picked clauses only) the same prompt with two lines telling the model to say when something is not in the text provided (`app/archetypes/cat4_rag/answer_formats.py`).

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

## Without vs with (version × corpus size)

### Quality

| group | answers | key-fact recall | supplier-specific | statutory/mechanism/structure | citations/answer | zero-citation answers | expected-chunk recall (cited) | citations at expected chunks | cited support of hit facts |
|---|---|---|---|---|---|---|---|---|---|
| Without · corpus 1× (7 docs) | 24 | 156/159 (98%) [95–99] | 111/111 (100%) [97–100] | 45/48 (94%) [83–98] | not requested | — | — | — | — |
| Without · corpus 3× (21 docs) | 24 | 150/159 (94%) [90–97] | 104/111 (94%) [88–97] | 46/48 (96%) [86–99] | not requested | — | — | — | — |
| With · corpus 1× (7 docs) | 24 | 153/159 (96%) [92–98] | 109/111 (98%) [94–100] | 44/48 (92%) [80–97] | 10.2 | 0/24 (0%) [0–14] | 84/90 (93%) [86–97] | 205/245 (84%) [79–88] | 150/153 (98%) [94–99] |
| With · corpus 3× (21 docs) | 24 | 154/159 (97%) [93–99] | 110/111 (99%) [95–100] | 44/48 (92%) [80–97] | 10.5 | 0/24 (0%) [0–14] | 85/90 (94%) [88–98] | 206/251 (82%) [77–86] | 151/154 (98%) [94–99] |

### Contamination and clause picks

Contaminated = the answer states a distractor supplier's value for a keyed fact, or cites a distractor chunk. 'Without naming the other supplier' drops values whose 150-char neighbourhood names that supplier or one of its document ids (typically an explicit exclusion). Exposure = the synthesis prompt contained distractor text (the whole corpus at scale 3, or ≥ 1 distractor chunk selected); it is not counted as contamination.

| group | contaminated answers | …distractor value stated | …value stated without naming the other supplier | …distractor chunk cited | synthesis saw distractor text (exposure) | citations at Deccan | citations at distractors | expected clauses among Haiku's picks | distractor chunks selected | backfilled / invalid picks |
|---|---|---|---|---|---|---|---|---|---|---|
| Without · corpus 1× (7 docs) | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | — | — | — | — | — |
| Without · corpus 3× (21 docs) | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 24/24 (100%) [86–100] | — | — | — | — | — |
| With · corpus 1× (7 docs) | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 245/245 (100%) [98–100] | 0/245 (0%) [0–2] | 89/90 (99%) [94–100] | 0/120 (0%) [0–3] | 0 / 0 |
| With · corpus 3× (21 docs) | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 0/24 (0%) [0–14] | 251/251 (100%) [98–100] | 0/251 (0%) [0–2] | 89/90 (99%) [94–100] | 0/120 (0%) [0–3] | 0 / 0 |

### Judge

| group | judged | correctness mean (1–5) | completeness mean (1–5) | material errors | minor errors | answers with ≥1 material error | answers the question |
|---|---|---|---|---|---|---|---|
| Without · corpus 1× (7 docs) | 24 | 4.50 | 4.83 | 1 | 17 | 1/24 (4%) [1–20] | yes 24 |
| Without · corpus 3× (21 docs) | 24 | 4.50 | 4.75 | 3 | 17 | 3/24 (12%) [4–31] | yes 24 |
| With · corpus 1× (7 docs) | 24 | 4.75 | 4.54 | 0 | 11 | 0/24 (0%) [0–14] | yes 24 |
| With · corpus 3× (21 docs) | 24 | 4.54 | 4.54 | 2 | 13 | 2/24 (8%) [2–26] | yes 24 |

### Absence claims

Deterministic detector over each answer: a sentence saying the documents / deal room / contracts / text contain, specify or state no X (documents-lack form), or that X is not in the text provided / the excerpts (not-in-text-provided form). The judge column counts answers whose material errors include such a claim about a term the documents do contain.

| group | answers | answers saying the documents lack something (detector) | answers saying it is not in the text provided (detector) | claims: documents-lack / not-in-text-provided | answers writing "None stated in the text provided" | judged answers with an unsupported absence claim (judge material error) | those judge errors: documents-lack / not-in-text-provided | answers with ≥1 material error | correctness mean | key-fact recall |
|---|---|---|---|---|---|---|---|---|---|---|
| Without · corpus 1× (7 docs) | 24 | 7/24 (29%) [15–49] | 0/24 (0%) [0–14] | 7 / 0 | 0 | 0/24 (0%) [0–14] | 0 / 0 | 1/24 (4%) [1–20] | 4.50 | 156/159 (98%) [95–99] |
| Without · corpus 3× (21 docs) | 24 | 1/24 (4%) [1–20] | 1/24 (4%) [1–20] | 1 / 1 | 0 | 0/24 (0%) [0–14] | 0 / 0 | 3/24 (12%) [4–31] | 4.50 | 150/159 (94%) [90–97] |
| With · corpus 1× (7 docs) | 24 | 0/24 (0%) [0–14] | 21/24 (88%) [69–96] | 0 / 32 | 13 | 0/24 (0%) [0–14] | 0 / 0 | 0/24 (0%) [0–14] | 4.75 | 153/159 (96%) [92–98] |
| With · corpus 3× (21 docs) | 24 | 0/24 (0%) [0–14] | 20/24 (83%) [64–93] | 0 / 30 | 12 | 1/24 (4%) [1–20] | 0 / 1 | 2/24 (8%) [2–26] | 4.54 | 154/159 (97%) [93–99] |

### Cost per question (USD, mean over answers)

| group | billed Sonnet | billed Haiku | billed total | cold Sonnet | cold Haiku | cold total | warm Sonnet | warm Haiku | warm total | cache-write premium (one-off) |
|---|---|---|---|---|---|---|---|---|---|---|
| Without · corpus 1× (7 docs) | $0.0459 | $0.0000 | $0.0459 | $0.0459 | $0.0000 | $0.0459 | $0.0459 | $0.0000 | $0.0459 | $0.0000 |
| Without · corpus 3× (21 docs) | $0.1173 | $0.0000 | $0.1173 | $0.1173 | $0.0000 | $0.1173 | $0.1173 | $0.0000 | $0.1173 | $0.0000 |
| With · corpus 1× (7 docs) | $0.0223 | $0.0007 | $0.0230 | $0.0223 | $0.0007 | $0.0230 | $0.0223 | $0.0004 | $0.0227 | $0.0025 |
| With · corpus 3× (21 docs) | $0.0232 | $0.0017 | $0.0250 | $0.0232 | $0.0017 | $0.0250 | $0.0232 | $0.0008 | $0.0241 | $0.0073 |

### Tokens per call

| group | call | prompt tok mean | prompt range | output mean | output range | cache write mean | cache read mean | thinking mean |
|---|---|---|---|---|---|---|---|---|
| Without · corpus 1× (7 docs) | synthesis | 18492 | 18464–18511 | 895 | 786–1007 | 0 | 0 | 0 |
| Without · corpus 3× (21 docs) | synthesis | 54221 | 54193–54240 | 884 | 760–1044 | 0 | 0 | 0 |
| With · corpus 1× (7 docs) | rerank | 21652 | 21623–21675 | 340 | 300–366 | 2678 | 18743 | 0 |
| With · corpus 1× (7 docs) | synthesis | 6194 | 5452–6922 | 988 | 842–1112 | 0 | 0 | 0 |
| With · corpus 3× (21 docs) | rerank | 63437 | 63409–63457 | 349 | 327–376 | 7901 | 55305 | 0 |
| With · corpus 3× (21 docs) | synthesis | 6221 | 5544–6922 | 1079 | 823–1584 | 0 | 0 | 79 |

### Per question

| group | question | key-fact recall | supplier-specific | citations/answer | zero-citation | contaminated | judge correctness | judge completeness | billed $/question |
|---|---|---|---|---|---|---|---|---|---|
| Without · corpus 1× (7 docs) | audit-01/q1 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | — | — | 0/3 (0%) [0–56] | 4.67 | 5.00 | $0.0461 |
| Without · corpus 1× (7 docs) | audit-01/q2 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | — | — | 0/3 (0%) [0–56] | 4.33 | 5.00 | $0.0459 |
| Without · corpus 1× (7 docs) | audit-01/q3 | 21/21 (100%) [85–100] | 18/18 (100%) [82–100] | — | — | 0/3 (0%) [0–56] | 4.67 | 5.00 | $0.0460 |
| Without · corpus 1× (7 docs) | audit-01/q4 | 15/15 (100%) [80–100] | 9/9 (100%) [70–100] | — | — | 0/3 (0%) [0–56] | 4.33 | 5.00 | $0.0453 |
| Without · corpus 1× (7 docs) | audit-02/q1 | 15/18 (83%) [61–94] | 3/3 (100%) [44–100] | — | — | 0/3 (0%) [0–56] | 4.67 | 5.00 | $0.0458 |
| Without · corpus 1× (7 docs) | audit-02/q2 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | — | — | 0/3 (0%) [0–56] | 4.33 | 4.00 | $0.0462 |
| Without · corpus 1× (7 docs) | audit-02/q3 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | — | — | 0/3 (0%) [0–56] | 5.00 | 5.00 | $0.0458 |
| Without · corpus 1× (7 docs) | audit-02/q4 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | — | — | 0/3 (0%) [0–56] | 4.00 | 4.67 | $0.0465 |
| Without · corpus 3× (21 docs) | audit-01/q1 | 20/21 (95%) [77–99] | 8/9 (89%) [57–98] | — | — | 0/3 (0%) [0–56] | 4.67 | 4.67 | $0.1168 |
| Without · corpus 3× (21 docs) | audit-01/q2 | 20/21 (95%) [77–99] | 20/21 (95%) [77–99] | — | — | 0/3 (0%) [0–56] | 4.67 | 4.33 | $0.1172 |
| Without · corpus 3× (21 docs) | audit-01/q3 | 21/21 (100%) [85–100] | 18/18 (100%) [82–100] | — | — | 0/3 (0%) [0–56] | 4.33 | 5.00 | $0.1175 |
| Without · corpus 3× (21 docs) | audit-01/q4 | 13/15 (87%) [62–96] | 7/9 (78%) [45–94] | — | — | 0/3 (0%) [0–56] | 4.33 | 5.00 | $0.1171 |
| Without · corpus 3× (21 docs) | audit-02/q1 | 16/18 (89%) [67–97] | 3/3 (100%) [44–100] | — | — | 0/3 (0%) [0–56] | 5.00 | 5.00 | $0.1163 |
| Without · corpus 3× (21 docs) | audit-02/q2 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | — | — | 0/3 (0%) [0–56] | 4.00 | 4.67 | $0.1185 |
| Without · corpus 3× (21 docs) | audit-02/q3 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | — | — | 0/3 (0%) [0–56] | 5.00 | 5.00 | $0.1170 |
| Without · corpus 3× (21 docs) | audit-02/q4 | 18/21 (86%) [65–95] | 18/21 (86%) [65–95] | — | — | 0/3 (0%) [0–56] | 4.00 | 4.33 | $0.1178 |
| With · corpus 1× (7 docs) | audit-01/q1 | 20/21 (95%) [77–99] | 9/9 (100%) [70–100] | 10.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.33 | $0.0240 |
| With · corpus 1× (7 docs) | audit-01/q2 | 20/21 (95%) [77–99] | 20/21 (95%) [77–99] | 12.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.67 | $0.0219 |
| With · corpus 1× (7 docs) | audit-01/q3 | 21/21 (100%) [85–100] | 18/18 (100%) [82–100] | 8.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 5.00 | $0.0240 |
| With · corpus 1× (7 docs) | audit-01/q4 | 15/15 (100%) [80–100] | 9/9 (100%) [70–100] | 9.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.67 | $0.0219 |
| With · corpus 1× (7 docs) | audit-02/q1 | 15/18 (83%) [61–94] | 3/3 (100%) [44–100] | 7.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.67 | $0.0217 |
| With · corpus 1× (7 docs) | audit-02/q2 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | 13.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.00 | $0.0237 |
| With · corpus 1× (7 docs) | audit-02/q3 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 10.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.33 | 5.00 | $0.0227 |
| With · corpus 1× (7 docs) | audit-02/q4 | 20/21 (95%) [77–99] | 20/21 (95%) [77–99] | 9.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.00 | $0.0240 |
| With · corpus 3× (21 docs) | audit-01/q1 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 10.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.00 | 4.67 | $0.0301 |
| With · corpus 3× (21 docs) | audit-01/q2 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | 12.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.33 | 5.00 | $0.0227 |
| With · corpus 3× (21 docs) | audit-01/q3 | 21/21 (100%) [85–100] | 18/18 (100%) [82–100] | 9.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.67 | $0.0246 |
| With · corpus 3× (21 docs) | audit-01/q4 | 13/15 (87%) [62–96] | 9/9 (100%) [70–100] | 9.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.67 | $0.0224 |
| With · corpus 3× (21 docs) | audit-02/q1 | 16/18 (89%) [67–97] | 3/3 (100%) [44–100] | 7.7 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 4.33 | $0.0256 |
| With · corpus 3× (21 docs) | audit-02/q2 | 20/21 (95%) [77–99] | 20/21 (95%) [77–99] | 14.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 5.00 | 4.00 | $0.0243 |
| With · corpus 3× (21 docs) | audit-02/q3 | 21/21 (100%) [85–100] | 9/9 (100%) [70–100] | 10.0 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.67 | 5.00 | $0.0264 |
| With · corpus 3× (21 docs) | audit-02/q4 | 21/21 (100%) [85–100] | 21/21 (100%) [85–100] | 10.3 | 0/3 (0%) [0–56] | 0/3 (0%) [0–56] | 4.00 | 4.00 | $0.0238 |

## Zero-citation and contaminated answers

No zero-citation answers with the lever.

No contaminated answers.

## For lead review

Items a person should read before quoting any number from this file.

### Material errors reported by the judge

| source | group | question | claim | problem | source quote |
|---|---|---|---|---|---|
| rerun | Without · corpus 1× (7 docs) r2 | audit-01/q4 | NovaMart CISO/DPO must confirm the Munich firewall in writing (Clause SL.1(2)) | SL.1(2) sets the telemetry firewall as a continuing condition but does not require written CISO/DPO confirmation before allotment; CISO and DPO authorization appears only in B.2(b), for cross-border a | Neither KroneVolt GmbH, its Munich R&D engineers, nor its nominee director shall receive API keys, bulk telemetry exports, or remote SSH access to Indian customer IoT data or AWS ap-south-1/ap-south-2 |
| rerun | Without · corpus 3× (21 docs) r0 | audit-01/q2 | Deductions are credit-note based, so they interact with CGST Section 34 adjustments and remain outside the MSA Clause 9.1 cap analysis. | Section 34 credit notes appear only for volume rebates in SL.3, and no document says Addendum A peak deductions sit outside the Clause 9.1 aggregate cap. | ABSENT |
| rerun | Without · corpus 3× (21 docs) r0 | audit-02/q4 | so peak LDs and GST debits are the only uncapped recovery routes | Peak LDs are excluded from the 3.25% ceiling but are themselves capped at 6.50% of Festive Peak PO landed value, so they are not uncapped; 'only' also ignores the Clause 9.2 uncapped carve-outs. | Combined dock fees and fill-rate deductions under Clause A.4 are capped at 6.50% of total Festive Peak PO landed value |
| rerun | Without · corpus 3× (21 docs) r1 | audit-02/q2 | A final order against Deccan would not be capped, because MSA Cl. 9.2(b)(iii) and TAX-GST-ITC-2026 Cl. D.4 keep tax-fraud indemnity uncapped. | The Maharashtra demand is Deccan's own non-fraud Section 73 tax dispute, whereas the uncapped carve-out covers indemnifying NovaMart for fraudulent invoicing, blocked ITC under Section 16(2)(c), Secti | non-fraud classification confirmed after withdrawal of initial Section 74 allegations |
| rerun | With · corpus 3× (21 docs) r0 | audit-02/q4 | The 6.5% cap exceeds the 3.25% ceiling, so the two are not stackable. | The 3.25% ceiling expressly excludes Addendum A Clause A.4 Peak liquidated damages, so the two caps are independent and can apply cumulatively; nothing supports a 'not stackable' conclusion. | (EXPRESSLY EXCLUDING punitive Peak SLA liquidated damages assessed under Addendum A Clause A.4 and GST escrow/debit adjustments under Schedule D) shall NEVER exceed a hard contractual ceiling of 3.25% |
| rerun | With · corpus 3× (21 docs) r2 | audit-01/q1 | No banking NOC, escrow, or delisting gate is stated in the text provided. | The documents do contain these mechanisms: a GST escrow holdback (Schedule D), an EPR delisting trigger (Schedule C) and an SBI NOC condition (Side Letter #2). | NovaMart is expressly authorized to automatically delist, suppress Buy-Box visibility, and inventory-freeze all Deccan battery and appliance ASINs effective December 15, 2026 |

- The answer key was written from the question texts and Deccan chunks only; one dry pass over recorded answers added format variants (see key `meta.format_variants_added`).
- The chunk boundaries and headings Haiku picks from were written for these documents; the share of expected clauses among its picks may be lower for unseen questions.
- Four questions (audit-01/q2, q3; audit-02/q3, q4) do not name the supplier; the scope line names it.
- The contamination detector cannot flag a distractor value that also occurs in Deccan's own documents; such values are excluded.

## Data quality

Counts over the sessions and judgements above: error sessions 0; non end turn calls 0; model mismatches 0; cache anomalies 0; haiku calls over 100k prompt 0; superseded sessions 0; judge failed calls 0; judge non end turn 0; judge model mismatches 0; judge cache misses 0; judgements not matching a scored answer 0; scored answers without judgement 0.
