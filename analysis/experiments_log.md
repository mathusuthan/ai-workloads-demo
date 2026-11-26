# Experiments log

This file is the history of the NovaMart archetype experiments. The app, the reports and `analysis/archetype_posts_source.md` show only the current runs: one design per archetype, without and with the improvement the deck suggests. Everything else that was run is recorded here.

Each archetype section has three parts:

- **Current runs.** What the dashboards and the posts file show, and where the records are.
- **Other levers we tried.** Valid runs of levers that are not the deck's improvement, or that split it into parts. Their records are kept in `other_levers/` folders and are not displayed.
- **Different or incorrect designs, and what replaced them.** Earlier runs that used a different design or had a fault: what they were, what was wrong, the fix, and the runs that replaced them. Their records are not in the working tree; commit `7807557` holds them.

All costs use the rate card in `backend/app/core/pricing.py`: Sonnet 5.5 at $2 in / $10 out per million tokens, cache write $2.50, cache read $0.10; Haiku 5.5 at $0.10 / $0.50, cache write $0.125, cache read $0.01. "Cold" means each run writes its own cache; "warm" means the cache is already written.

The results describe these tasks, prompts and settings in one synthetic lab. They are observations about system designs, not assessments of any model.

---

## Cross-cutting fixes

These apply to more than one archetype.

### Cache-read price for Sonnet

- **What was wrong.** `pricing.py` priced Sonnet 5.5 cache reads at $0.20 per million tokens. The published rate is $0.10.
- **Effect.** Every cached Sonnet version was overstated by about 2–10%, and one Archetype 4 row by 14%.
- **Fix (21 Nov 2026).** Rate corrected; stored traces re-priced with `backend/scripts/reprice_traces.py`.

| Version | Old card, $ per 1,000 | Published card, $ per 1,000 | Overstatement |
|---|---:|---:|---:|
| Archetype 3, cached history | 248.53 | 239.66 | +3.7% |
| Archetype 3, cached + summarised | 221.33 | 212.45 | +4.2% |
| Archetype 4, cached full corpus, 7 documents | 108.54 | 101.02 | +7.4% |
| Archetype 4, cached full corpus, 21 documents | 173.31 | 151.57 | +14.3% |
| Archetype 5, raw tables cached | 113.46 | 110.99 | +2.2% |
| Archetype 5, narrow query cached | 44.75 | 43.10 | +3.8% |
| Archetype 5, policy tool on Sonnet | 53.44 | 50.84 | +5.1% |
| Archetype 5, policy tool, Haiku first | 23.01 | 22.62 | +1.7% |
| Archetype 6, isolated + cached | 103.65 | 99.91 | +3.7% |

### Mixed-model runs priced at one model's rate

- **What was wrong.** For runs that call two models (Archetypes 5 and 6), the rollup priced all output at Sonnet's $10 per million, and the seed script priced a mixed run at one model's rates. Some traces had a total cost below their output cost.
- **Fix (21 Nov 2026).** All four rollups use `rollup_multi_call_finops`, which prices each call at its own model's rate.

### Cost per verified outcome was zero for unverified runs

- **What was wrong.** A run whose result did not verify showed a cost per verified outcome of 0.
- **Fix (25 Nov 2026, commit `41d4202`).** The value is empty for an unverified run, and the portfolio figure is empty when a version has no verified outcomes.

### Fixed numbers in labels

- **What was wrong.** Badges and notes in the app carried typed-in numbers ("-97% Cost", "~115k–130k prompt tokens per run") that no longer matched the data.
- **Fix (25 Nov 2026, commit `41d4202`).** Labels are computed from each run's measured values (`backend/app/core/measured_claims.py`, tested in `tests/test_measured_claims.py`).

### Capture scripts selected runs by outcome

- **What was wrong.** The scripts that recorded the first replays for Archetypes 4, 5 and 6 rejected and re-ran a run when its result was not the expected one (details in each archetype section).
- **Fix.** They now reject a run only for infrastructure failures. Every rerun keeps every run.

### Stop reasons were constant or missing

- **What was wrong.** The first captures for Archetypes 2 and 3 wrote `end_turn` for every call, and the Archetype 1 capture stored no stop reason, so a cut-off answer could not be seen.
- **Fix.** Every harness and the live paths record the stop reason the API returned.

### Trace store held many copies of each run

- **What was wrong.** The app wrote a trace file on every request, including replays, and re-seeding added new seed traces without removing old ones. At commit `7807557` the store held 1,074 files for 244 current runs; one run appeared up to 30 times. Averages over the index weighted a run by how often it had been viewed and mixed superseded captures with current ones.
- **Fix (26 Nov 2026).** One backup tarball was taken, the store was cleared and re-seeded from the current replays, and replay requests no longer write traces. Live requests still do.

| Commit | Files | Current runs | Most copies of one run | Replay / seed / live |
|---|---:|---:|---:|---|
| `41d4202` | 953 | 244 | 29 | 624 / 317 / 12 |
| `8fd79ea` | 985 | 244 | 29 | 624 / 349 / 12 |
| `a660739` | 994 | 244 | 29 | 624 / 358 / 12 |
| `7807557` | 1,074 | 244 | 30 | 624 / 438 / 12 |

### Unused code removed

- **Gemini (26 Nov 2026).** Once the Gemini Decision lever left the app, nothing called Gemini. Removed: the Gemini key settings and the reading of `GEMINI_API_KEY` / `GOOGLE_API_KEY`, the Gemini key handling in the credit shield, the `google-genai` dependency and the `.env.example` entries.
- **Keyword search (26 Nov 2026).** Removed: the BM25 retriever (`cat4_rag/retriever.py`), its reranker prompt, the harness's keyword-search + rerank version, and every BM25 field in the models, types, replays and summaries (all empty for the current versions). The clause-pick prompt of the current "with" version is unchanged byte for byte.
- **Where it is kept.** The removed code is in commit `7807557`. The recorded runs stay in `experiments/cat1_ablation/other_levers/` and `experiments/cat4_quality/other_levers/`.

### Validation scorecard over time

| Date (commit) | Rows | Supported | Partly | Not supported | Not testable | What moved |
|---|---:|---:|---:|---:|---:|---|
| 21 Nov (not in git) | 27 | 11 | 15 | 0 | 1 | First pass |
| 25 Nov (`41d4202`) | 29 | 11 | 15 | 2 | 1 | Quality rows added for Archetypes 2 and 3; Archetype 6 rerun |
| 26 Nov (`8fd79ea`) | 30 | 11 | 16 | 2 | 1 | Archetype 4 rerun and quality row |
| 26 Nov (`a660739`) | 31 | 10 | 18 | 2 | 1 | Archetype 5 ablation: lever row moved to partly; accuracy row added |
| 26 Nov (`7807557`) | 31 | 9 | 19 | 2 | 1 | Archetype 1 ablation: lever and accuracy rows moved to partly; Archetype 4 paired-retrieval row moved to supported |
| 26 Nov (one design per archetype, commit `0a141f0`) | 32 | 9 | 19 | 3 | 1 | Rows re-judged on without versus with only. Archetype 1 lever row moved to supported; Archetype 2 input-to-output ratio row moved to partly (unbounded drafts on both models now measured: 0.74:1 and 0.67:1); Archetype 6 output band moved to not supported (0 of 45 runs in band); Archetype 6 quality row added as partly |
| 26 Nov (Archetypes 5 and 6 on both model set-ups) | 32 | 9 | 19 | 3 | 1 | No verdict changed. Archetype 5's guardrail part is now partly supported: on Haiku the "with" design cost 32% more than "without" from a cold start |

---

## Archetype 1: Classification, extraction and routing (support triage and SKU tagging)

### Current runs

Deck improvement: small model + strict JSON schema + batching. Shown as one design, without and with "classification with a strict JSON schema", on Sonnet 5.5 and Haiku 5.5; the Batch API price is computed (50%) on the two "with" cells, not run.

| Design | Version id (app rung) | Model | Runs | Fields correct of 126 (95% Wilson) | Items fully correct of 36 | $ per 1,000 items | Batch API, computed | Prompt / output tokens (median; output range) | Median latency |
|---|---|---|---:|---:|---:|---:|---:|---|---:|
| Without: four-part write-up, free text | `sonnet_report` (`sonnet_naive`) | Sonnet 5.5 | 36 | 69 (46–63%)* | 6 | 29.50 | — | 791 / 2,739 (1,703–4,046) | 22.1 s |
| Without: four-part write-up, free text | `haiku_report` (`haiku_naive`) | Haiku 5.5 | 36 | 69 (46–63%)* | 3 | 1.25 | — | 791 / 2,283 (1,227–3,894) | 11.2 s |
| With: classification + strict JSON schema | `sonnet_schema` (`sonnet_calibrated`) | Sonnet 5.5 | 36 | 126 (97–100%) | 36 | 3.77 | 1.88 | 1,389 / 96 (71–125) | 2.0 s |
| With: classification + strict JSON schema | `haiku_schema` (`haiku_calibrated`) | Haiku 5.5 | 36 | 120 (90–98%) | 33 | 0.188 | 0.094 | 1,389 / 98 (71–125) | 1.4 s |

- 12 items (6 presets, 6 batch items) × 3 repeats per cell; caps 8,192 (write-up) and 512 (schema); `max_retries=0`; real stop reasons; 0 of 144 runs truncated. Run 26 Nov 2026, 03:54–03:58 UTC.
- \* The write-up prompt never lists the allowed labels, so a write-up's score counts the fields where one allowed label can be read off it (usable as a classification). Write-ups were read by a blind reader model (`claude-opus-5-5`, one pass); it read all 100 known fields of 20 JSON answers rewritten as plain text correctly.
- Haiku with the schema missed 6 fields, all on tkt-01 and tkt-02.
- Records: `backend/experiments/cat1_ablation/runs.jsonl` (144 runs) and `extractions.jsonl` (72 reader-model extractions of the write-ups). The golden replays are repeat 0 of each cell (`scripts/build_cat1_golden_from_ablation.py`).

### Other levers we tried

All from the same experiment: same 12 items, 3 repeats, ground truth, app call wrappers and settings. Records: `backend/experiments/cat1_ablation/other_levers/runs.jsonl` (108 runs: 72 plain-text classification, 36 Gemini Decision 1) and `other_levers/extractions.jsonl` (72 reader-model extractions of the plain-text answers).

**1. Classification as plain text, without a schema (`sonnet_classify_text`, `haiku_classify_text`).** Asks only for the classification fields, one `field: value` line each, allowed values listed, "Do not explain"; no JSON schema; max_tokens 1,024. Tried to separate "ask only for the classification" from "enforce a schema".

| Version | Fields correct of 126 (95% Wilson) | Items fully correct of 36 | $ per 1,000 items | Prompt / output tokens (median; output range) | Median latency |
|---|---:|---:|---:|---|---:|
| Sonnet, plain text | 126 (97–100%) | 36 | 2.89 | 980 / 88 (62–114) | 1.9 s |
| Haiku, plain text | 120 (90–98%) | 33 | 0.145 | 980 / 88 (62–140) | 1.1 s |

What it showed:

- Write-up → plain-text classification: −90.2% (Sonnet), −88.4% (Haiku).
- Plain text → JSON schema: +30.4% (Sonnet), +29.8% (Haiku) cost, with the same fields correct (126 → 126, 120 → 120).
- All 72 plain-text answers stated every field with an allowed label. The schema guarantees the format; the saving comes from asking for the classification alone and from the smaller model.
- Haiku plain text missed the same tkt-01 fields as Haiku with the schema.

**2. Gemini Decision 1 through the decisions API (`gemini_decision`).** A non-generative decision model: one pass over fixed questions per sub-task, 0 output tokens. It was the app's fourth rung. Its questions differ from the JSON schema: priority comes from a 0–3 severity score mapped to P0–P3, and the category list and PII question are worded differently. The rate ($0.10 per million input tokens, $0 output) is the repo's and was not verified.

| Version | Fields correct of 126 (95% Wilson) | Items fully correct of 36 | $ per 1,000 items | Prompt / output tokens (median) | Median latency |
|---|---:|---:|---:|---|---:|
| Gemini Decision 1 | 123 (93–99%) | 33 | 0.099 | 973 / 0 | 0.54 s |

- The fields that did not match: `contains_pii` on tkt-05 returned false in 3 of 3 runs.
- Against Haiku with the schema: −47.5% cost, +2.4 points.

**3. TypeSafe Jev rate card (not run).** A rate-card comparator ($0.042 per million input tokens, $0 output) applied to each item's input tokens and shown next to Gemini as "Rate Card Ref". No call was made and no quality was measured.

Removed from the app with these levers: the Gemini rung and its decisions-API service (`backend/app/core/gemini_decision_service.py`), the decision questions (`SUPPORT_DECISION_QUESTIONS`, `SKU_DECISION_QUESTIONS`, `get_questions_for_subtask`), the Gemini and Jev rates and `compute_jev_reference` in `pricing.py`, the Gemini/Jev rows in the run and batch responses, and the old capture script `backend/scripts/capture_live_replays.py`. The harness keeps the plain-text arms (`OTHER_LEVER_ARMS`) so they can be re-run; the Gemini arm was removed from it.

### Different or incorrect designs, and what replaced them

**1. Original capture (4 rungs, 12 items, 1 run per cell)**

- **Numbers.** $ per 1,000 items: Sonnet write-up 22.04, Haiku write-up 1.02, Haiku schema 0.189, Gemini 0.099. Fields correct of 42 (keyword scorer for write-ups, structured output otherwise): 27, 24, 40, 41; items fully correct of 12: 2, 1, 11, 11. The same 24 write-ups re-read by the reader model: 23 and 22 of 42.
- **What was wrong.** Write-ups were capped at 2,048 tokens and 19 of 24 were cut off (Sonnet 11 of 12, Haiku 8 of 12), so their costs were lower bounds; stop reasons were not stored; the schema cap was 256; one run per cell; the write-ups were scored by a keyword scorer (item 2).
- **Verdicts that relied on it.** "Small model + strict JSON schema + batching cuts unit cost by >80%": supported ("−99.1%; even the schema alone, on the same model, clears 80%"). "…without losing accuracy": supported.
- **Fix (commit `7807557`).** The experiment above: 3 repeats, caps 8,192 / 512, real stop reasons and thinking tokens, a blind reader model for free text. App caps set to match; the schema rung no longer falls back silently to tool use. The golden replays were rebuilt from repeat 0.

**2. Keyword scorer for write-ups**

- **What it was.** A regex extractor (`extract_prose_predictions`) that scored write-ups in the app.
- **What was wrong.** Run beside the reader model on the same 36 answers per version: write-ups over-scored (Sonnet 90 vs 69 of 126, Haiku 74 vs 69), plain-text classifications under-scored (108 vs 126, 102 vs 120). Field agreement: 75, 73, 108 and 108 of 126.
- **Fix (26 Nov 2026).** Replayed write-ups are scored from the stored reader-model extraction; live write-ups are shown as not scored, because the app does not call a reader model. The keyword scorer was removed.

**3. Interrupted reader-model pass**

- On 26 Nov 2026, 04:01 UTC, 43 reader-model calls failed with an API usage-limit error (23 re-readings of the original capture, 20 schema-as-text checks). The limit was raised and all 43 succeeded at 04:08–04:09 UTC. The 20 schema-as-text checks read 100 of 100 fields correctly; that result is kept as one method sentence. The error records and the original-capture extractions were deleted.

**4. Seven versions on the dashboard**

- **What it was.** The app and reports showed all seven versions of the experiment (four app rungs including Gemini, plus the plain-text and Sonnet-schema versions in the tables), a lever table, and the Jev rate card.
- **Fix (26 Nov 2026).** One design, without and with the improvement, on both models; the Sonnet-schema version became a runnable app rung. The other levers are recorded above.
- **Verdicts after the change.** "Small model + strict JSON schema + batching cuts unit cost by >80%": partly → supported. It is now judged on Sonnet write-up → Haiku schema (−99.4%), and each step clears 80% on its own (write-up → schema −87.2% Sonnet, −84.9% Haiku; Sonnet → Haiku −95.0%). The earlier "partly" came from the plain-text lever, which showed that the schema itself adds cost. "…without losing accuracy (implicit)": partly, unchanged. With beats without on every count on the same model; on the "with" row, Haiku is 6 fields below Sonnet with overlapping intervals. The input, output and ratio rows stay partly. The input row is now measured on the prompts sent (schema median 1,389, write-up median 791) and a fitted payload estimate (≈122–1,388 tokens). It was previously measured on Gemini's input tokens (581–1,472).

**Record files after pruning (26 Nov 2026).** `runs.jsonl` 252 → 144 (108 other-lever runs moved to `other_levers/runs.jsonl`). `extractions.jsonl` 231 → 72: 43 error records, 24 original-capture extractions and 20 schema-as-text records deleted, and 72 plain-text extractions moved to `other_levers/extractions.jsonl`. `backend/replays/cat1_original_capture.json` deleted. Earlier copies: commit `7807557`.

---

## Archetype 2: Generative synthesis and drafting (executive and regulatory briefs)

### Current runs

Deck improvement: structured section templates and length bounds. Shown as one design, without ("unbounded long-form draft") and with ("section template with length caps"), on Sonnet 5.5 and Haiku 5.5. The template includes one rule for action items: give the owner and time window only if the source states them, otherwise write exactly `Not stated in source`.

| Design | Version id (app rung) | Model | Drafts | $ per 1,000 documents | Output tokens (mean; range) | Core facts | Detail facts | Accuracy | Coverage | Clarity | Actionability | Concision | Serious errors per draft | Owners in source / not stated / not in source | Time windows (same) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| Without: unbounded long-form draft | `unbounded` (`sonnet_unbounded`) | Sonnet 5.5 | 12 | 57.43 | 5,012 (4,370–5,885) | 95 of 96 | 120 of 120 | 3.92 | 5.00 | 3.83 | 3.42 | 2.75 | 0.42 | n/a | n/a |
| Without: unbounded long-form draft | `unbounded` (`haiku_unbounded`) | Haiku 5.5 | 12 | 3.11 | 5,487 (4,703–6,521) | 94 of 96 | 119 of 120 | 2.92 | 4.33 | 3.42 | 3.42 | 2.58 | 1.83 | n/a | n/a |
| With: section template + length caps | `template_not_stated` (`sonnet_templated`) | Sonnet 5.5 | 12 | 26.82 | 1,694 (1,586–1,839) | 94 of 96 | 94 of 120 | 4.17 | 3.42 | 4.17 | 3.08 | 4.00 | 0.00 | 8 / 28 / 0 | 21 / 15 / 0 |
| With: section template + length caps | `template_not_stated` (`haiku_templated`) | Haiku 5.5 | 12 | 1.36 | 1,723 (1,569–1,892) | 92 of 96 | 92 of 120 | 3.83 | 3.58 | 4.08 | 2.67 | 4.08 | 0.25 | 0 / 36 / 0 | 22 / 14 / 0 |

- 4 documents × 3 repeats per cell; template max_tokens 3,000, unbounded 8,000; real stop reasons; 0 of 48 drafts truncated. All drafts made 26 Nov 2026.
- Graded by one blind judge (`claude-opus-5-5`, not a model under test), one rubric pass per draft (1–5); fact coverage from a fixed answer key. Head-to-head, template against unbounded on the same document, model and repeat in both orders (48 calls): template preferred in 21, unbounded in 27 (Sonnet 6–18, Haiku 15–9); on accuracy alone template 25, unbounded 18, 5 ties; on usefulness to the reader template 9, unbounded 39.
- Serious errors in total: 5 (Sonnet unbounded), 22 (Haiku unbounded), 0 (Sonnet template), 3 (Haiku template). Each one's quoted claim was found in the draft and its quoted source text in the source.
- The unbounded drafts and their grading cost $6.19 (drafting $0.73, grading $5.46).
- Records: `backend/experiments/cat2_not_stated/drafts.jsonl` and `judgements.jsonl`. The golden replays are repeat 0 of each cell (`scripts/build_cat2_golden_from_experiment.py`). Section regenerations: one call per document, section and model on the repeat-0 template drafts (32 calls, `section_regens.jsonl`, $0.23): $13.87 per 1,000 edits against $26.94 for the full Sonnet template draft (−49%), and $0.732 against $1.38 on Haiku (−47%).

### Other levers we tried

None beyond the deck's lever. Haiku with the template was earlier a separate rung; it is now the Haiku column of the same design.

### Different or incorrect designs, and what replaced them

**1. Stored drafts and the first grading round (3 rungs, 4 documents, 1 draft per cell)**

- **What it was.** Drafts captured 17 Nov 2026 (`cat2_golden_replays.json`): Sonnet unbounded, Sonnet template, Haiku template. Graded 25 Nov 2026 with 3 rubric passes per draft and 24 head-to-head calls (`experiments/cat2_quality/`).

| Rung | $ per 1,000 | Output tokens (mean) | Core facts | Detail facts | Accuracy | Coverage | Clarity | Actionability | Concision | Serious / minor errors | Numbers not in source | Action items flagged (serious) | Head-to-head |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---|
| Sonnet, unbounded | 58.92 | 5,162 | 32 of 32 | 40 of 40 | 3.92 | 4.92 | 4.00 | 3.75 | 2.83 | 1 / 21 | 46 (44 derived correct, 1 derived wrong, 1 not a claim) | — | won 8–0 against each template |
| Sonnet, template | 27.25 | 1,753 | 32 of 32 | 37 of 40 | 3.08 | 4.00 | 4.92 | 3.75 | 4.17 | 6 / 18 | 6 (1 derived correct, 5 unverifiable) | 8 of 12 (6) | 0–8 vs unbounded; 7–1 vs Haiku template |
| Haiku, template | 1.39 | 1,817 | 32 of 32 | 36 of 40 | 2.58 | 3.50 | 4.42 | 3.25 | 4.08 | 10 / 18 | 8 (2 derived correct, 6 unverifiable) | 8 of 12 (6) | 0–8 vs unbounded; 1–7 vs Sonnet template |

- **What was wrong.** The template required "exactly 3 owned milestones" and the schema requires an owner and time window on every action item, with no way to say the source gives none; the drafts filled them with owners and deadlines the source does not give. One draft per cell. The capture script wrote `end_turn` as every stop reason. The comparison mixed model and template changes in one rung.
- **Verdicts that relied on it.** "Section templates + length bounds control output cost": supported (−54% same model, −98% with Haiku). "…without losing draft quality": not supported (templated drafts preferred in 0 of 16 comparisons).
- **Fix.** The rule for action items was added to the template, verbatim: "For each action-plan item, give the owner and the time window only if the source states them. If the source does not name an owner, or gives no date or time window, write exactly `Not stated in source` in that field. Never supply an owner, team, date or deadline the source does not give." Fresh drafts, 3 per document and model, with real stop reasons.
- **Records.** Deleted: the stored drafts' rubric judgements, the 24 head-to-head judgements, and the `experiments/cat2_quality/` folder. Earlier copies: commit `7807557`.

**2. Fresh drafts with the earlier template (`template_original`, 26 Nov 2026)**

- 3 drafts per document and model (24), max_tokens 3,000, 0 truncated, one rubric pass each.

| Model | Drafts | $ per 1,000 | Output tokens (mean) | Core facts | Detail facts | Numbers not in source (derived correct / wrong / unverifiable / not a claim) | Accuracy | Coverage | Clarity | Actionability | Concision | Serious per draft (total) | Minor per draft | Items flagged | Owners in source / not stated / not in source | Time windows (same) |
|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| Sonnet | 12 | 27.19 | 1,748 | 96 of 96 | 110 of 120 | 14 (4 / 0 / 9 / 1) | 3.25 | 3.75 | 5.00 | 3.67 | 4.33 | 1.25 (15) | 3.00 | 25 | 14 / 0 / 22 | 23 / 0 / 13 |
| Haiku | 12 | 1.39 | 1,808 | 93 of 96 | 104 of 120 | 34 (11 / 2 / 19 / 2) | 2.67 | 3.58 | 4.42 | 3.25 | 4.08 | 2.25 (27) | 3.42 | 27 | 10 / 0 / 26 | 17 / 0 / 19 |

- Matched head-to-head, current template against this one on the same document, model and repeat, both orders (48 calls): the current template was preferred 47–1 (Sonnet 23–1, Haiku 24–0); position-consistent in 23 of 24 pairs.
- **Records.** 24 drafts, 24 rubric judgements and 48 head-to-head judgements were deleted. Earlier copies: commit `7807557`.

**3. Head-to-head against the stored unbounded drafts**

- Current template (repeat 0) against the 4 stored unbounded Sonnet drafts, both orders, 16 calls: unbounded preferred 15–1 (Sonnet template 1–7, Haiku template 0–8); position-consistent in 7 of 8 pairs.
- **What was wrong.** The two sides came from different drafting runs, so they were not matched on repeat, and Haiku had no unbounded draft.
- **Replacement.** Fresh unbounded drafts on both models and the matched 48-call head-to-head in "Current runs": template 21, unbounded 27. The 16 unmatched records were deleted.

**4. Three rungs on the dashboard**

- **What it was.** Sonnet unbounded, Sonnet template and Haiku template, with a separate "template fix" panel beside them.
- **Fix (26 Nov 2026).** One design, without and with the improvement, on both models; Haiku unbounded added as a runnable app rung. The app's template is now the one the current drafts used (byte-identical prompt, checked against the recorded `system_sha256`).
- **Verdicts after the change.** "Section templates + length bounds control output cost": supported (−53% on Sonnet, −56% on Haiku, same model). "…without losing draft quality" (our addition): not supported, on detail facts (94 of 120 against 120 of 120 on Sonnet; 92 against 119 on Haiku). Under the template, accuracy grades were higher and serious errors fewer on both models. "Output tokens cost 3–5× input" stays supported.

**5. Section regenerations captured on the earlier drafts**

- **What it was.** The app's "regenerate one section" replays (16, Sonnet only) were made on the stored drafts of item 1, and their saving was computed against a fixed 3,200-token Sonnet re-prompt. A Haiku regeneration in the app started from the Sonnet draft.
- **Numbers.** $13.81 per 1,000 edits on Sonnet, reported as −49% against the full Sonnet template draft; $0.74 on Haiku.
- **Fix (26 Nov 2026).** 32 regenerations re-captured on the current repeat-0 template drafts, 4 documents × 4 sections × 2 models, each on its own model's draft; real stop reasons recorded; the saving is computed against the full template draft of the same document and model.
- **Replacement.** Sonnet $13.87 per 1,000 edits against $26.94 (−49%); Haiku $0.732 against $1.38 (−47%); 0 of 32 cut off.

**Record files after pruning (26 Nov 2026).** `cat2_not_stated/drafts.jsonl` holds 48 drafts (24 unbounded, 24 template); `cat2_not_stated/judgements.jsonl` holds 96 judgements (48 rubric, 48 head-to-head); `experiments/cat2_quality/` deleted. Deleted: `replays/cat2_not_stated_summary.json`, `analysis/cat2_not_stated.*`, and the first-round scripts (`analyze_cat2_quality.py`, `build_cat2_quality_summary.py`, `cat2_quality_score.py`, `capture_cat2_replays.py`, `analyze_cat2_not_stated.py`, `build_cat2_not_stated_summary.py`).

---

## Archetype 3: Multi-turn assistants (IT and HR help desk)

### Current runs

Deck improvement: prefix caching plus sliding-window summarisation.

| Design | Version id | Model | Sessions | $ per 1,000 sessions, cold | Warm | Context at turn 10 (tokens) | Answers grounded | Early details in final summary | Recall questions |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| Without: full history, no cache | `naive_full_history` | Sonnet 5.5 | 6 | 398.68 | 398.68 | 21,872 | 205 of 207 | 37 of 51 | 36 of 36 |
| With: cached prefix + summaries | `prefix_cached_summarized` | Sonnet 5.5 | 6 | 212.45 | 188.78 | 14,824 | 205 of 207 | 24 of 51 | 2 of 36 |

- 2 ten-turn sessions, 3 runs each, 6 recall questions asked after turn 10. Scored against a fixed answer key by string matching.
- "Early details" are the details from turns 1–3 that appear in the final summary.
- Context grows by 1,247 tokens per turn without the improvement and 288 with it.
- Records: `backend/experiments/cat3_quality/runs.jsonl` (12 records).

### Other levers we tried

**Prefix caching alone (`prefix_cached_history`).** The full transcript as in the "without" version, with the 9,900-token handbook sent as a cached prefix and no summarisation. Tried to separate the two parts of the deck's improvement. Same harness, sessions, recall questions and answer key; 6 sessions. Records: `backend/experiments/cat3_quality/other_levers/runs.jsonl` (6 records).

| Version | $ per 1,000 sessions, cold | Warm | Context at turn 1 | Turn 3 | Turn 6 | Turn 10 | Answers grounded | Final-summary details | Early details | Recall questions |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Without | 398.68 | 398.68 | 10,617 | 13,169 | 17,054 | 21,872 | 205 of 207 | 106 of 147 | 37 of 51 | 36 of 36 |
| Prefix caching alone | 239.66 | 216.00 | 10,626 | 13,157 | 16,803 | 21,496 | 203 of 207 | 110 of 147 | 39 of 51 | 36 of 36 |
| With | 212.45 | 188.78 | 10,633 | 13,200 | 13,783 | 14,824 | 205 of 207 | 91 of 147 | 24 of 51 | 2 of 36 |

Per session:

| Version | desk-01 recall | desk-01 summary details | desk-01 $ per 1,000 | desk-02 recall | desk-02 summary details | desk-02 $ per 1,000 |
|---|---:|---:|---:|---:|---:|---:|
| Without | 18 of 18 | 63 of 75 | 415.86 | 18 of 18 | 43 of 72 | 381.51 |
| Prefix caching alone | 18 of 18 | 67 of 75 | 265.90 | 18 of 18 | 43 of 72 | 213.42 |
| With | 2 of 18 | 59 of 75 | 215.58 | 0 of 18 | 32 of 72 | 209.33 |

What it showed:

- Caching alone cut cost by 39.9% and changed no quality measure.
- It did not bound the context: turn 10 was still 21,496 tokens.
- Adding summarisation bounded the context and cut a further 11% of cost. It is also the step after which recall of early details fell to 2 of 36.

### Different or incorrect designs, and what replaced them

**1. Original capture (3 versions, 2 sessions, 1 run per cell)**

- **Numbers.** $376.20, $216.82 and $182.82 per 1,000 sessions (full history, cached prefix, cached prefix + summary). Details given in turns 1–9: 69 of 69 in every version. Final-summary details: 32, 35 and 30 of 49. No recall questions were asked.
- **What was wrong.** One run per cell; the capture was re-run until it passed its checks; the summariser's stop reason was written as a constant, so a cut-off summary could not be seen; nothing measured recall.
- **Fix (commit `41d4202`).** A rerun with 3 runs per session and recall questions after turn 10; real stop reasons recorded; replays rebuilt from repeat 0 by a fixed mapping.
- **Replacement.** The table above.

**2. Analysis that could not be regenerated**

- **What was wrong.** The analysis script scored an "original capture" group from whatever the replay file held. After the replays were rebuilt from the rerun, that group could no longer be reproduced.
- **Fix.** The group was removed. The analysis regenerates from the rerun records alone.

**3. Three versions on the dashboard**

- **What it was.** The app and reports showed prefix caching alone as a middle version, and the quality row compared the summarised version with it.
- **Fix.** One design, without and with the improvement. Caching alone is recorded above.
- **Verdicts after the change.** "Prefix caching + sliding-window summary prevents quadratic session cost": supported. "…without losing answer quality" (our addition): not supported, on recall of 2 of 36 against 36 of 36.

---

## Archetype 4: Multi-document question answering (supplier contract audit)

### Current runs

Deck improvement: pair retrieval with context caching.

| Design | Version id | Corpus | Answers | $ per question, cold | Warm | Key facts (of 159) | Answers with a serious error | Correctness (1–5) | Completeness (1–5) | Needed clauses kept (of 90) | Other-supplier clauses picked |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Without: full corpus, no cache | `naive_full_corpus` | 7 documents | 24 | 0.0459 | 0.0459 | 156 | 1 | 4.50 | 4.83 | n/a | n/a |
| With: retrieval paired with caching | `cached_rerank_hybrid` | 7 documents | 24 | 0.0230 | 0.0227 | 153 | 0 | 4.75 | 4.54 | 89 | 0 |
| Without: full corpus, no cache | `naive_full_corpus` | 21 documents | 24 | 0.1173 | 0.1173 | 150 | 3 | 4.50 | 4.75 | n/a | n/a |
| With: retrieval paired with caching | `cached_rerank_hybrid` | 21 documents | 24 | 0.0250 | 0.0241 | 154 | 2 | 4.54 | 4.54 | 89 | 0 |

- 8 questions per session, 3 sessions per cell. The 21-document corpus adds two synthetic look-alike suppliers.
- "Without": Sonnet 5.5 reads the whole corpus on every question, with no citations.
- "With": Haiku 5.5 reads all clauses from one cached block and picks five; Sonnet 5.5 answers over those five with citations.
- Scored against a fixed answer key and by one blind grader pass per answer (Opus 5.5).
- Every question starts with the line "Deal room under audit: DR-NM-DECCAN-2026-Q4 (supplier: Deccan Smart Appliances & Energy Pvt. Ltd.). Answer for this supplier's contracts only."
- Records: `backend/experiments/cat4_quality/runs.jsonl` (12 sessions) and `judgements.jsonl` (96 judgements).

### Other levers we tried

Both ran in the same rerun on the same terms as the current versions. Records: `backend/experiments/cat4_quality/other_levers/runs.jsonl` (12 sessions) and `other_levers/judgements.jsonl` (96 judgements).

- **Cached full corpus with citations (`cached_full_corpus_citations`).** Sonnet gets the whole corpus as cached document blocks. Caching without retrieval: the context is unchanged and only its price drops.
- **Keyword search + Haiku rerank (`hybrid_rag_rerank_citations`).** BM25 keeps 10 clauses, Haiku reranks them to 5, Sonnet answers over the 5. Retrieval without caching.

Quality, 24 answers per cell:

| Version | Corpus | Key facts (of 159) | Answers with a serious error | Correctness | Completeness | Citations per answer | Needed clauses kept (of 90) | Other-supplier clauses picked (of 120) | Answers using another supplier's values |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Cached full corpus | 7 documents | 150 | 0 | 4.96 | 4.58 | 11.71 | n/a | n/a | 0 |
| Keyword search + rerank | 7 documents | 150 | 2 | 4.54 | 4.58 | 10.29 | 90 | 0 | 0 |
| Cached full corpus | 21 documents | 149 | 0 | 4.83 | 4.67 | 11.38 | n/a | n/a | 0 |
| Keyword search + rerank | 21 documents | 144 | 3 | 4.33 | 4.00 | 8.92 | 78 | 24 | 2 |

Cost per question in 8-question sessions:

| Version | Corpus | Cold | Warm | One-off cache-write premium |
|---|---|---:|---:|---:|
| Cached full corpus | 7 documents | 0.0253 | 0.0188 | 0.0516 |
| Keyword search + rerank | 7 documents | 0.0234 | 0.0234 | 0 |
| Paired (the current "with") | 7 documents | 0.0230 | 0.0227 | 0.0025 |
| Cached full corpus | 21 documents | 0.0379 | 0.0193 | 0.1491 |
| Keyword search + rerank | 21 documents | 0.0262 | 0.0262 | 0 |
| Paired (the current "with") | 21 documents | 0.0250 | 0.0241 | 0.0073 |

Break-even: the number of questions that must share one cache write before the first version costs less than the second.

| Corpus | Cached full corpus vs keyword search | Paired vs keyword search | Cached full corpus vs paired |
|---|---:|---:|---:|
| 7 documents | 12 | 4 | 13 |
| 21 documents | 22 | 4 | 30 |

What they showed:

- **Cached full corpus.** No answer with a serious error at either size and the highest correctness scores. Its cache write is large, so in 8-question sessions it cost more per question than either retrieval version.
- **Keyword search + rerank.** At 7 documents it kept every needed clause. At 21 documents the keyword stage kept 78 of 90 and passed 24 other-supplier clauses to the reranker; 2 of 24 answers used another supplier's values.
- **Paired.** Picking from the whole cached corpus kept 89 of 90 needed clauses at both sizes with no other-supplier clause.

### Different or incorrect designs, and what replaced them

**1. Original capture (3 versions, 2 audits of 4 questions, 7 documents, 1 run per cell)**

- **Numbers.** $46.29, $19.79 and $24.33 per 1,000 questions (full corpus, cached full corpus, keyword search + rerank). Zero-citation answers 0 of 8 on both citation versions. Break-even between caching and retrieval at 4.7 questions.
- **What was wrong.** One run per cell and no measure of answer quality. The second audit read the cache the first one wrote. Questions carried no supplier line. The answer cap was 2,048 tokens. The capture script rejected any audit with a zero-citation answer and re-ran it.
- **Fix (commit `8fd79ea`).** A rerun at two corpus sizes with every answer kept, a fixed answer key and a blind grader; the capture script checks infrastructure only; replays rebuilt from repeat 0 at 7 documents.
- **Replacement.** The table above. Zero-citation answers in the rerun: 0 of 48 on the current "with" version, measured.

**2. Pilot at the 2,048-token answer cap (64 answers)**

- **What was wrong.** 3 of 64 answers were cut off at the cap.
- **Fix.** Cap raised to 4,096 in the rerun and the app. In the 96 current answers none was cut off; the longest used 1,584 output tokens.

**3. Questions without the supplier line**

- **What was wrong.** With look-alike suppliers in the corpus, an unscoped question does not say whose contracts to answer from.
- **Fix.** The supplier line above is on every rerun question and on live questions in the app.

**4. Retrieval versions with the original answer instructions (96 answers)**

- **What it was.** The answer template's last bullet asked for a "Required Sign-Off Gate: concrete operational, banking NOC, escrow, or delisting gate before execution".
- **What was wrong.** With only five clauses in the prompt, answers filled that bullet by stating that the documents contain no such gate. All 18 serious errors the grader reported on these sessions were statements that the documents lack something they contain.
- **Fix.** The retrieval versions' instructions say to write "None stated in the text provided", and to say a term is not in the text provided instead of saying the documents lack it. Measured on 96 new answers.

| Version | Corpus | Instructions | Answers saying the documents lack something | Answers with a serious error | Correctness | Key facts (of 159) | $ per question |
|---|---|---|---:|---:|---:|---:|---:|
| Keyword search + rerank | 7 documents | Original | 9 | 0 | 4.71 | 152 | 0.0247 |
| Keyword search + rerank | 7 documents | Current | 0 | 2 | 4.54 | 150 | 0.0234 |
| Keyword search + rerank | 21 documents | Original | 12 | 8 | 3.96 | 145 | 0.0278 |
| Keyword search + rerank | 21 documents | Current | 0 | 3 | 4.33 | 144 | 0.0262 |
| Paired | 7 documents | Original | 12 | 1 | 4.54 | 154 | 0.0244 |
| Paired | 7 documents | Current | 0 | 0 | 4.75 | 153 | 0.0230 |
| Paired | 21 documents | Original | 13 | 6 | 4.38 | 153 | 0.0264 |
| Paired | 21 documents | Current | 0 | 2 | 4.54 | 154 | 0.0250 |

- **Replacement.** The current-instruction sessions are the only retrieval sessions kept. The original-instruction sessions and their judgements were deleted.

**5. Error records from an API usage limit**

- **What happened.** 5 session records and 64 grader records failed (one connection error; the rest "API usage limit reached"). Each was completed on retry.
- **Fix.** The error records were deleted; every current answer has one grader judgement.

**6. Four versions on the dashboard**

- **What it was.** The app showed the full corpus, the cached full corpus and keyword search + rerank; the paired version appeared in the results panel only. Reports carried break-even tables and compared quality against the cached full corpus.
- **Fix.** One design, without and with the improvement. The app runs the paired version live. The other two versions are recorded above.
- **Verdicts after the change.** "Pair hybrid retrieval with context caching": supported. "…without losing answer quality" (our addition): partly, because key facts at 7 documents are 153 against 156.

---

## Archetype 5: Process orchestration (three-way invoice match)

### Current runs

Deck improvement: step budgets, deterministic guardrails and small-model routing.

| Design | Version id | Model | Runs | Exact vouchers | $ per 1,000 invoices, cold | Warm | Model turns | Escalations |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Without: free-choice loop over raw tables | `raw_free_sonnet` | Sonnet 5.5 | 36 | 36 | 153.41 | 153.41 | 3.86 | 0 |
| Without: free-choice loop over raw tables | `raw_free_haiku` | Haiku 5.5 | 36 | 36 | 7.89 | 7.89 | 3.92 | 0 |
| With: 4-step budget + policy tool | `bundle_gate_sonnet_cached` | Sonnet 5.5 | 36 | 36 | 51.22 | 30.49 | 4.00 | 0 |
| With: 4-step budget + policy tool | `bundle_gate_haiku_escalate` | Haiku 5.5 first, Sonnet on escalation | 36 | 36 | 10.42 | 5.94 | 4.00 | 6 |

- 12 invoices, 3 runs each. The "with" design also uses one narrow query in place of the raw tables and sends the policy manual as a cached prefix.
- The six escalations are the three runs each of inv-02 and inv-12, the two invoices that mix two or more dispute factors.
- No run hit the step budget or was cut off.
- The Haiku "without" cell was added on 26 Nov 2026 (36 runs, $0.28) so that model and design can be separated. With no policy tool it has no escalation path.
- Records: `backend/experiments/cat5_ablation/runs.jsonl` (144 records) and `tool_results.jsonl`.

### Other levers we tried

Run on 26 Nov 2026 as part of a six-version ablation that added the deck's levers one at a time. These three versions are valid; none of them calls the policy tool. Records: `backend/experiments/cat5_ablation/other_levers/runs.jsonl` (108 records) and `other_levers/tool_results.jsonl`.

| Lever | Version id | Configuration |
|---|---|---|
| Prefix caching alone | `raw_free_sonnet_cached` | Raw-table tools, policy manual cached, Sonnet, 12-turn safety cap |
| One narrow query, no policy tool | `bundle_sonnet_cached` | `fetch_3way_match_bundle` + commit, cached, Sonnet computes the voucher itself |
| The same on Haiku | `bundle_haiku_cached` | As above on Haiku 5.5 |

Results on all 12 invoices, 36 runs each:

| Version | Exact vouchers | Model turns | Uncached input tokens | Cache write | Cache read | Output tokens | $ per 1,000, cold | Warm |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `raw_free_sonnet` (the current "without") | 36 | 3.86 | 68,266 | 0 | 0 | 1,688 | 153.41 | 153.41 |
| `raw_free_sonnet_cached` | 35 | 3.86 | 34,971 | 8,643 | 24,729 | 1,653 | 110.55 | 89.81 |
| `bundle_sonnet_cached` | 36 | 3.00 | 3,931 | 8,284 | 16,569 | 1,278 | 43.01 | 23.12 |
| `bundle_haiku_cached` | 36 | 3.00 | 4,241 | 8,285 | 16,569 | 1,556 | 2.40 | 1.45 |

- The one voucher that did not match: `raw_free_sonnet_cached`, inv-12, repeat 2. The decision was right; net principal was 3,862,520 against 4,862,520 expected.
- `bundle_haiku_cached` is the lowest-cost configuration measured for this archetype.
- Tool use: both raw-table versions called four of the five raw tools in every run and the vendor audit history in 31 of 36. The narrow-query versions called the bundle once and the commit once.

What each step did, as measured on 11 invoices (inv-06 excluded) with the policy tool as it then was:

| Step | From | To | Exact vouchers (of 33) | $ per 1,000, from | To | Ratio |
|---|---|---|---|---:|---:|---:|
| Caching alone | `raw_free_sonnet` | `raw_free_sonnet_cached` | 33 → 32 | 153.72 | 110.99 | 0.72 |
| Narrow query | `raw_free_sonnet_cached` | `bundle_sonnet_cached` | 32 → 33 | 110.99 | 43.10 | 0.39 |
| Policy tool | `bundle_sonnet_cached` | `bundle_gate_sonnet_cached` | 33 → 33 | 43.10 | 50.84 | 1.18 |
| Sonnet → Haiku, no policy tool | `bundle_sonnet_cached` | `bundle_haiku_cached` | 33 → 33 | 43.10 | 2.40 | 0.06 |

### Different or incorrect designs, and what replaced them

**1. Scripted seven-step baseline and outcome-based capture (original capture, 3 invoices, 1 run per version)**

- **What it was.** The first "unbounded loop" told Sonnet to call one raw-table tool per step in a fixed seven-step order, with a 2,048-token cap. Its turn count and cost were set by the script. The capture script also re-ran a version until its voucher matched, tool precision was 100%, the Haiku-first version escalated as expected and the baseline used more than 25,000 prompt tokens.
- **Numbers.** $191 per 1,000 invoices (baseline), $37.47 (budget + cached manual + policy tool), $16.99 (Haiku first). 3 of 3 exact in every version. Baseline per invoice: inv-01 7 turns, $247.48; inv-02 7 turns, $255.09; inv-03 3 turns, $71.81.
- **Fix.** The baseline is a free-choice loop: the model chooses which raw queries to run, several per turn allowed, 12-turn safety cap, 4,096-token cap. The capture script rejects only infrastructure failures. Replays are built from repeat 0 of the ablation by a fixed mapping.
- **Replacement.** Free choice on the same three invoices: inv-01 4 turns, $164.05; inv-02 4 turns, $170.41; inv-03 3 turns, $104.72. On all 12 invoices: the "without" row above.

**2. Harness ended a run that still held tool calls**

- **What was wrong.** The API can return `end_turn` together with tool calls. The harness and the app's runner ended the run without executing them. One record was affected (`raw_free_sonnet`, inv-05, repeat 0, $0.0207).
- **Fix.** Every tool call in a turn that was not cut off is executed, whatever the stop reason. The affected run was repeated; the first record was deleted.

**3. Policy tool applied the 1.5% price band without its condition (inv-06)**

- **What was wrong.** The tool accepted any price up to 1.5% above the PO. Manual 2.1 allows that band only when the PO's currency notes say the price is index-linked. The narrow query also did not return those notes.
- **Numbers.** inv-06 bills 1,499 against a PO price of 1,480 on 1,200 units. Manual: partial approval, net 3,656,000, debit note 22,800. Old tool: clean approval, net 3,678,800. In 6 of 6 runs the versions with the tool committed the tool's figures; the four versions without it matched the manual in 12 of 12.
- **Fix.** The band passes only when the PO is index-linked ("not index linked" is handled); the narrow query returns the currency notes. After the fix, 6 of 6 runs with the tool matched the manual.
- **Replacement.** inv-06 is an ordinary invoice in the current matrix: 9 of 9 exact.

**4. Three gaps in the policy tool that no invoice exercised**

- **What was wrong.** The tool ignored an approved freight waiver, took the GST rate from the first line for the whole invoice, and had no check for a duplicate invoice or a vendor under payment freeze.
- **Fix.** All three added, with tests on synthetic rows (`backend/tests/test_cat5_gate_fix.py`). The tool's output on the 12 invoices did not change.

**5. Policy tool escalated on any deduction**

- **What was wrong.** The tool asked for escalation whenever a debit note was above zero. Manual 6.2 reserves escalation for disputes that mix factors (partial DOA or short receipt, signed amendment, unauthorised price rise, disallowed freight).
- **Numbers.** The Haiku-first version escalated in 15 of 33 runs (inv-02, 05, 07, 09, 12) and cost $22.62 per 1,000 invoices cold, $12.14 warm. An escalated run cost about $0.045; one that stayed on Haiku about $0.0027.
- **Fix.** Escalation only when two or more distinct factor kinds are present. inv-05, 06, 07 and 09 no longer escalate.
- **Replacement.** 6 escalations in 36 runs; $10.42 per 1,000 invoices cold, $5.94 warm. 30 runs on inv-05, 06, 07, 09 and 11 were repeated under the corrected tool (30 of 30 exact, $0.80).

**6. Hold label on inv-11**

- **What was wrong.** On a hard block every held line was labelled as an IRN block, including on inv-11, where the block is a phantom line. Decision and amounts were right.
- **Fix.** A held line takes the label of the lowest-numbered trigger that fired.

**7. Runs recorded on the older narrow query (42 runs)**

- **What it was.** 42 of the 72 "with" runs (inv-01, 02, 03, 04, 08, 10, 12) were recorded before the narrow query returned four added fields: PO currency notes, vendor risk flag, vouchers already posted, and per-line PO GST rate.
- **Numbers.** On those seven invoices: Sonnet 21 of 21 exact, $51.11 per 1,000 invoices cold, $30.38 warm; Haiku first 21 of 21 exact, $15.99 cold, $9.03 warm, 6 escalations. The policy tool's output on these invoices is the same with either query.
- **Fix.** A record counts as current only if every tool call in it returns what the tool returns now. The 42 runs were repeated on the current query (42 of 42 exact, $1.41) and the older records deleted.
- **Replacement.** The table at the top of this section. The app's replays are built from the new runs.

Records removed from the main file: 1 harness-bug record, 36 runs made with earlier versions of the policy tool, and 42 runs made with the older narrow query.

---

## Archetype 6: Multi-agent swarms (incident patching)

### Current runs

Deck improvement: isolate sub-agent contexts and cache the shared repository prefix; measure cost per verified outcome.

| Design | Version id | Models | Runs | Verified fixes | $ per 1,000 runs, cold | Warm | Uncached input tokens | Output tokens | Model time |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| Without: shared bus | `shared_bus_matched_gate` | Sonnet 5.5 on every turn | 15 | 15 | 469.02 | 469.02 | 214,112 | 4,079 | 30.8 s |
| Without: shared bus | `shared_bus_tiered_gate` | Haiku 5.5 agents, Sonnet patch author | 15 | 15 | 124.61 | 124.61 | 214,585 | 4,416 | 25.6 s |
| With: isolated agents + cached prefix | `isolated_cached_gate` | Sonnet 5.5 on every turn | 15 | 15 | 99.91 | 77.50 | 9,792 | 5,325 | 38.8 s |
| With: isolated agents + cached prefix | `tiered_gate` | Haiku 5.5 agents, Sonnet patch author | 15 | 15 | 56.20 | 32.71 | 10,095 | 5,408 | 28.4 s |

- 3 incidents, 5 runs each. Every version has the same role instructions, the same output caps, the same ten-check sandbox and one retry. No turn was cut off and no retry was used.
- Every version verified 15 of 15, so cost per verified fix equals cost per run.
- The shared bus with Haiku agents was added on 26 Nov 2026 (15 runs, $1.87) so that model and design can be separated. Its largest single Haiku prompt was under 100,000 tokens, so the standard Haiku rate applies.
- Records: `backend/experiments/cat6_fair_rerun/runs.jsonl` (60 records).

### Other levers we tried

None. Model tiering is the second model column of the current design.

### Different or incorrect designs, and what replaced them

**1. Original three-version capture (3 incidents, 1 run per version)**

- **Numbers.** Shared bus 1 of 3 verified, $1.87 per verified fix; isolated 3 of 3, $0.086; tiered 3 of 3, $0.029. The "64-fold gap" came from this capture.
- **What was wrong.**
  - Shared-bus answers were cut off at a 3,200-token cap, so the sandbox scored incomplete patches.
  - The capture script re-ran isolated runs whose patch did not verify until one did.
  - The isolated patch author had hints and word limits the shared-bus author lacked, and the shared bus had no sandbox check or retry.
  - Later runs read caches written by earlier ones.
- **Fix (commit `41d4202`).** Equal caps (16,000 for the patch author, 4,000 for other roles), a fresh cache per run, every run kept, the capture script rejecting only infrastructure failures.
- **Replacement.** The table above: $0.469 per verified fix without, $0.100 and $0.056 with.

**2. Shared bus with "exhaustive commentary" instructions (`shared_bus_original`, 15 runs)**

- **What it was.** The shared bus with the old instructions asking for exhaustive multi-section commentary, and no sandbox check before sign-off.
- **Numbers.** 15 of 15 verified, $696.10 per 1,000 runs, 246,633 uncached input tokens and 20,283 output tokens per run, 154.7 s of model time.
- **What was different.** It differs from the isolated versions in instructions and in the sandbox step as well as in context design, so it is not the deck's "without" case.
- **Replacement.** `shared_bus_matched_gate`, which differs from the isolated versions only in context design.
- **Records.** `backend/experiments/cat6_fair_rerun/other_designs/runs.jsonl`.

**3. Sandbox check counted a constant comparison as a signature comparison**

- **What was wrong.** The constant-time-comparison check treated a comparison against a module-level prefix constant (`_SIG_PREFIX = "sha256="`) as a direct signature `==`. Three `shared_bus_original` runs on inc-02 were first scored 9 of 10 checks, giving 12 of 15 verified.
- **Fix (commit `41d4202`).** Names bound once at module level to a literal count as constants. The three runs score 10 of 10. No other version was affected.
