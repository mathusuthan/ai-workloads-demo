# Six AI Workload Archetypes: experiment notes for the post series

Source material for seven posts: one introduction and one post per archetype. Every number here comes from `analysis/deck_claims_validation.md` (regenerated 26 Nov 2026), the reruns and scoring in `analysis/cat6_fair_rerun.md`, `analysis/cat3_quality_rerun.md`, `analysis/cat1_ablation.md`, `analysis/cat4_quality_rerun.md`, `analysis/cat5_ablation.md` and `analysis/cat2_quality.md`, or the golden replays the lab app serves. Part 0 feeds the intro post; Parts 1–6 each feed one archetype post; the appendix holds the rate card and definitions that every post may need.

## How to read the numbers

- **The deck.** "Six Key AI Archetypes for AI Workloads" is a 9-slide guide by Eric Lam. It sorts enterprise AI work into six archetypes, gives each a typical token profile, and names one architectural lever per archetype. The experiment tests those claims.
- **The lab.** Each archetype was built as a real workload at NovaMart, a fictional Indian omnichannel retailer (12M SKUs, 45,000 sellers, $2.4B GMV). All data is synthetic. Every workload was run live against the model APIs once and recorded.
- **What is being compared.** These experiments compare system designs: what is asked for, how much context is sent, caching, tools, and which size of model does which step. They are not an assessment of any model. Where a row names a model, read it as that configuration in this setup, on these tasks.
- **Rungs.** Each archetype was run several ways on the same inputs, from a naive version up to the governed version the deck recommends. Each way is called a rung.
- **Models.** Claude Sonnet 5.5 and Claude Haiku 5.5 throughout. Archetype 1 also includes a Gemini Decision 1 rung.
- **Cost.** Costs are recomputed from the recorded token counts at the rate card in the appendix, and quoted per 1,000 units of work (items, documents, sessions, and so on).
- **Three cost views** appear wherever caching is involved:
  - *Billed*: what the recorded runs actually cost, cache hits and misses as they happened.
  - *Cold*: the first call has to write the cache. This is a single user starting from nothing.
  - *Warm*: the cached prefix is already there. This is a busy fleet in steady state.
- **Sample sizes are small**: 12 items (each run 3 times per version), 4 documents, 2 sessions (each run 3 times), 8 questions (each asked 3 times per version and corpus size), 12 invoices (each run 3 times per version), 3 incidents (each run 5 times). Quote the percentages as indicative results from one lab, not as benchmarks.

---

## Part 0: Material for the introduction post

### The deck's argument

Treating every AI initiative like a chatbot breaks unit economics. Workloads differ in two ways: how much autonomy the system has, and how many tokens it moves. The deck plots six archetypes on those two axes.

| # | Archetype | Autonomy tier | Deck's token profile | Deck's lever |
|---|---|---|---|---|
| 1 | Classification, extraction and routing | Tier 1: single-pass API | 500–1,500 in, 10–100 out | Small model, strict JSON schema, batching: ">80% lower unit cost" |
| 2 | Generative synthesis and drafting | Tier 2: human in the loop | 1,500–4,000 in, 800–3,000+ out | Section templates and length bounds, because output costs 3–5× input |
| 3 | Multi-turn conversational assistants | Tier 3: stateful session | 10k–40k+ per session | Prefix caching plus sliding-window summaries |
| 4 | Multi-document RAG and deep ingestion | Tier 2+: human in the loop | 15k–100k+ in, 400–1,500 out | Hybrid retrieval with reranking, paired with context caching |
| 5 | Autonomous process orchestration | Tier 3+: bounded agent | 25k–150k+ in, 1,500–8,000 out | Step budgets, deterministic guardrails, small-model routing |
| 6 | Multi-agent swarms and automated engineering | Tier 4: agent swarm | 100k–1M+ in, 1.5M–10M+ tokens per developer per day | Isolated agent contexts, cached repo prefix, cost per verified outcome |

The deck closes with three rules:

1. **Archetypes 1 and 2: right-size single-pass calls and output.** Claimed impact: 60–80% lower unit inference cost.
2. **Archetypes 3 and 4: cache session and document context.** Claimed impact: eliminates quadratic context bloat.
3. **Archetypes 5 and 6: govern agent loops and track cost per outcome.** Claimed impact: predictable unit economics at scale.

### Headline results

| # | Unit of work | Naive | Best governed rung | Cost cut | What happened to quality |
|---|---|---:|---:|---:|---|
| 1 | 1,000 items | $29.50 | $0.188 (Haiku, classification with JSON schema); $0.145 as plain text | −99.4% | On the same classification task the Haiku version matched 120 of 126 fields, against 126 for the Sonnet version |
| 2 | 1,000 documents | $58.92 | $1.39 (Haiku, section template); $27.25 with the template on Sonnet | −98%; −54% | Every core fact kept, but a blind grader preferred the long draft in 16 of 16 comparisons; serious errors rose from 1 to 6 (Sonnet template) and 10 (Haiku template) |
| 3 | 1,000 ten-turn sessions | $399 | $212 (cache + compaction); $240 with caching alone | −47%; −40% | Caching: no change. Compaction: new answers unaffected, but recall of earlier details fell from 36/36 to 2/36 |
| 4 | 1,000 questions | $46 | $19 (cached corpus, warm); $24–25 with retrieval | −59%; −46% | Caching: best answers, no serious errors in 48. Retrieval: fine on the small corpus; on one three times larger, 6 to 8 answers in 24 had a serious error |
| 5 | 1,000 invoices | $154 | $2.40 (one narrow query, Haiku computes the voucher) | −98% | 197 of 198 vouchers correct across six versions; the cheapest got all 33 |
| 6 | 1,000 incidents | $696 | $56.20 (Haiku agents, Sonnet patch author, cold start) | −92% | Unchanged: every arm fixed 15 of 15. The tasks were small; harder ones might separate the versions |

### The scorecard

The scorecard has 31 rows: the deck's 26 testable claims plus five implicit ones we added, that the cheaper version loses no quality in Archetypes 1 to 5. Against the lab data:

- **9 supported**: the measurement falls inside the claimed range or clears the threshold.
- **19 partly supported**: the direction holds, but the magnitude is outside the range or a confound limits the conclusion.
- **2 not supported**: our added rows for Archetypes 2 and 3. Templated drafts lose to the long draft on quality, and compacting old turns loses recall.
- **1 not testable**: the per-developer daily token volume for swarms.

The Archetype 6 rows were re-judged on the fair rerun; none of the verdicts changed.

### Findings that cut across archetypes

- **Most cost levers worked in the direction the deck says, and none of the deck's own claims was contradicted outright.** The exceptions are in Archetype 5, where the deterministic guardrail added cost and the step budget never came into play. The two rows scored not supported are quality costs the deck does not mention.
- **The "60–80%" rule missed on both sides.** Changing the model as well as the prompt gave 98–99%. A template alone, on the same model, gave 54%.
- **Where the work has a checkable right answer, the cheaper versions scored the same or close; where it does not, they scored lower.** In Archetype 1 the smaller-model version matched 120 of 126 fields against 126 for the larger-model version on the same task, and in Archetypes 5 and 6 the cheaper versions matched as often as the others. In Archetype 2 the templated drafts kept every core fact but were not preferred in any blind comparison with the long draft, mostly because they filled in owners and deadlines the template demanded and the source did not give; one added sentence allowing "not stated" removed nearly all of those errors but did not close the gap. In Archetype 3, caching cost nothing in quality, but compacting old turns bought an extra 11% saving at the price of nearly all recall of earlier details. In Archetype 4, caching the whole corpus gave the best answers, while answers built from five retrieved clauses reported terms as absent that were in clauses not sent; two added lines of instruction removed those claims and halved the serious errors.
- **The deck's token bands describe context size, not the bill.** A ten-turn session peaks at 22k tokens of context but bills 163k prompt tokens, because every turn re-sends the history.
- **The archetype ordering depends on the unit.** The deck's scale runs 1 < 2 < 3 < 4 < 5 << 6. Measured, 1 < 2 < {3, 4, 5} < 6 holds, but a ten-turn session moves more tokens than a whole invoice or a four-question audit.
- **The first baselines were the weakest part of the experiment.** In Archetypes 1, 5 and 6 the naive version had been cut off at its output cap, scripted into extra steps, or asked to do a different job from the version it was compared with. Each was rerun against a fair baseline, and each time the headline saving or quality gap shrank or changed its cause.
- **Output control and model choice dominate the cheap end; context control dominates the expensive end.** In Archetypes 1 and 2, output is 88–93% of the naive bill. In Archetypes 3, 5 and 6, input is 71–91% of it.

### Measured token scale

Median total tokens per unit of work, on the rung closest to what the deck describes:

| Unit | Tokens |
|---|---:|
| Archetype 1, one item | 1.5k |
| Archetype 2, one document | 8.5k |
| Archetype 4, one question | 19.4k (55.1k on the 3× corpus) |
| Archetype 4, one four-question audit | 77.5k |
| Archetype 5, one invoice (raw tables) | 76.1k |
| Archetype 3, one ten-turn session | 169.6k |
| Archetype 6, one incident (rerun, mean) | 266.9k |

### What we got wrong while measuring

Good material for the intro: the measurement itself needed ten corrections.

- **Duplicate traces.** At the first audit the trace folder held 842 files but only 206 distinct runs. The rest were copies written each time the app replayed a recorded run; one run appeared 29 times. Averaging the raw folder weights each run by how often someone viewed it.
- **A wrong price.** The rate card had Sonnet cache reads at $0.20 per million tokens; the published rate is $0.10. Every cached Sonnet rung was overstated by 2–10%.
- **Failures that cost nothing.** Cost per verified outcome was recorded as zero for runs that failed verification, which made the worst rung look free. It is now undefined when nothing was verified.
- **Claims that drifted from the data.** The app's labels carried fixed numbers that no longer matched the runs. One badge promised "-65%+" where the data showed −97%; one note said "~115k–130k prompt tokens" where the run used 236k. Labels are now computed from each run.
- **A rigged comparison.** The first swarm experiment showed the naive swarm verifying 1 fix in 3 against 3 in 3 for the governed ones. The naive agents had been cut off at their output cap, and the capture script discarded governed runs that failed. Rerun fairly, every arm fixed 15 of 15 (Part 6).
- **A check that failed good code.** One static security check flagged a harmless comparison because of a variable's name. Three correct patches were scored as failures until the check was fixed.
- **A scripted baseline.** The naive invoice agent was told to make five lookups one at a time in a fixed order. Left to choose, it took about half the turns, and the saving credited to the governed design shrank accordingly (Part 5).
- **A guardrail nobody had tested.** Writing new invoices by hand showed that the lab's deterministic policy tool misapplied one rule. Every run that used the tool committed its figure; every run without it matched the manual (Part 5).
- **A comparison of two different jobs.** The classification baseline was asked for a four-part write-up and the lever for four fields. Most of the saving credited to the JSON schema came from asking for less; the schema itself added cost (Part 1).
- **A scorer that could not be trusted.** Free-text answers were scored by keyword search. Checked against a reader model on the same answers, it was wrong in both directions by up to 17 points (Part 1).

### Limits to state in the intro

- Samples are small. Archetypes 1, 3, 4 and 5 were run 3 times each and Archetype 6 5 times; Archetype 2's original drafts ran once, and its follow-up 3 times.
- Archetype 2's quality grades come from one model acting as a blind grader, with its serious findings checked by hand. Archetype 4's answers were graded the same way, in one pass.
- Several rungs change more than one thing at a time, so a saving cannot always be split between levers.
- All data is synthetic and the corpus sizes are at the low end of the deck's bands.

---

## Part 1: Classification, extraction and routing

**One-line result:** asking for a classification instead of a write-up cut cost by about 90%, and a smaller model cut it by a further 95% with about five points fewer fields matched; the strict JSON schema, which the first version of this experiment credited, added 30% to the cost and changed no answer.

This section uses the ablation of 26 Nov 2026: 252 live runs (seven versions, twelve items, three runs each), with nothing cut off and every run kept.

### What the deck says

- **Shape:** high-volume, low-latency triage that turns unstructured payloads into tags, masked fields and routing decisions.
- **Profile:** 500–1,500 tokens in, 10–100 out, input-to-output ratio of 20:1 to 50:1.
- **Lever:** route to small models with strict JSON schema output and batching, to cut unit cost by more than 80%.
- **Use cases:** omnichannel support, PII and compliance masking, catalog tagging.

### What was built

The NovaMart Intake and Catalog Gate, tested on 12 items across two tasks:

- **Support ticket triage (6 items).** Examples: a damaged-goods email exposing a payment card and phone number; a seller settlement dispute exposing Aadhaar and PAN tax IDs; a suspected account takeover from a voice transcript.
- **Seller SKU tagging (6 items).** Examples: a "100% pure mulberry silk" kurta whose care-label scan contradicts the listing; a 27,000 mAh power bank missing its air-freight certificate; a clean espresso grinder that should auto-publish.

Half the items are long (about 1,100 tokens) and half short (about 150). Each has a known right answer on three or four fields, 42 fields in all: for tickets the queue, priority, automatic action and whether personal data is present; for SKUs the category, compliance status and whether the listing contradicts itself. PII masking is done by a separate deterministic step, not by the model.

Seven versions, changing one thing at a time:

| Version | Model | What is asked for | Answer format |
|---|---|---|---|
| Sonnet write-up | Sonnet 5.5 | A four-part analyst write-up: summary, routing with reasoning, a personal-data audit, next steps | Free text |
| Sonnet classification, plain text | Sonnet 5.5 | Only the fields, chosen from the allowed values | One line per field |
| Sonnet classification, schema | Sonnet 5.5 | Only the fields | Strict JSON schema |
| Haiku write-up | Haiku 5.5 | The same write-up | Free text |
| Haiku classification, plain text | Haiku 5.5 | Only the fields | One line per field |
| Haiku classification, schema | Haiku 5.5 | Only the fields | Strict JSON schema |
| Gemini Decision | Gemini Decision 1 | A set of decision questions | Decisions API, no generated text |

Scoring: structured answers are compared with the right answer field by field. Free-text answers are first read by a separate model (Opus 5.5), which records what the answer says for each field without being shown the right answer or which version wrote it; those fields are then compared the same way.

### Results

Each row is 36 runs and 126 fields.

| Version | Fields correct | Items fully correct | Cost per 1,000 items | Output tokens (median) | Response time (median) |
|---|---:|---:|---:|---:|---:|
| Sonnet write-up | 69 | 6 | $29.50 | 2,739 | 22.1 s |
| Sonnet classification, plain text | 126 | 36 | $2.89 | 88 | 1.9 s |
| Sonnet classification, schema | 126 | 36 | $3.77 | 96 | 2.0 s |
| Haiku write-up | 69 | 3 | $1.25 | 2,283 | 11.2 s |
| Haiku classification, plain text | 120 | 33 | $0.145 | 88 | 1.1 s |
| Haiku classification, schema | 120 | 33 | $0.188 | 98 | 1.4 s |
| Gemini Decision | 123 | 33 | $0.099 | 0 | 0.5 s |

The Batch API would halve the two schema rows, to $1.88 and $0.094. That price is computed, not run.

What each change did:

| Change | Cost | Fields correct |
|---|---:|---|
| Write-up → classification only (Sonnet) | −90% | 69 → 126 |
| Write-up → classification only (Haiku) | −88% | 69 → 120 |
| Plain text → JSON schema (Sonnet) | +30% | 126 → 126 |
| Plain text → JSON schema (Haiku) | +30% | 120 → 120 |
| Sonnet → Haiku (classification, either format) | −95% | 126 → 120 |
| Haiku schema → Gemini Decision | −47% | 120 → 123 |
| Everything: Sonnet write-up → Haiku schema | −99.4% | 69 → 120 |

**Read the write-up rows with care.** The write-up prompt never lists the allowed values, so a write-up cannot be expected to use them. Its score is how often one allowed value could be read off it and was right. In 44 of 126 fields per model the write-up addressed the question without committing to a single allowed value, for example "Status: HOLD / DO NOT PUBLISH. Route to Compliance Audit." That is a measure of usability as a classification, not of reasoning.

Where the scores differed:

- **Haiku with the schema:** 6 fields did not match, all on two tickets. On the seller settlement dispute the answer gave a priority one level above the reference and the security escalation, in two of three runs; on the damaged-goods ticket it gave a different queue and action once. The plain-text Haiku version also had 6 fields that did not match.
- **Gemini Decision:** 3 fields did not match, the same one each time: a short ticket whose reference answer is that it contains personal data was answered "no", in three of three runs.

### How the first version went wrong

The first version of this experiment reported a 99.1% saving from "small model plus strict JSON schema", and fields correct rising from 27 to 40 of 42. Three things were wrong with that:

- **The two versions were doing different jobs.** The baseline was asked for a four-part write-up and the lever for four fields. The saving was credited to the schema; most of it comes from asking for less.
- **The baseline answers were cut off.** Eleven of twelve Sonnet write-ups hit the 2,048-token cap, some mid-sentence. Uncapped, they run to about 2,700 tokens, so the true baseline cost was a third higher than reported.
- **The accuracy scoring could not be trusted.** Write-ups were scored by searching the text for keywords and taking the first match. Against the reader model on the same answers, that scorer was 14 points too low on plain-text classifications and up to 17 points too high on write-ups, and the two agreed on only 24 or 25 of 42 fields on the original answers.

### Deck claims against the data

| Claim | Measured | Verdict |
|---|---|---|
| Input 500–1,500 tokens | Raw payloads 581–1,472; with instructions and schema 859–2,066 | Partly |
| Output 10–100 tokens | 71–125 with the schema, median 98 | Partly |
| Input:output of 20:1 to 50:1 | About 13:1 | Partly |
| Small model + strict JSON schema + batching cuts cost >80% | −99.4% overall. The classification-only request gives −90% and the small model −95%; the schema adds 30%; batching was priced, not run | Partly |
| …without losing accuracy (our addition; the deck does not claim it) | Haiku 120 of 126 against Sonnet's 126 on the same task; Gemini 123 | Partly |

### Points worth making in the post

- **The biggest lever is the request, not the model or the format.** Asking for four fields instead of a four-part write-up cut cost by about 90% on either model, and made the answer usable.
- **The schema is insurance, and it has a premium.** It added about 400 prompt tokens and 30% to the cost, and changed no answer. All 72 plain-text classification answers were readable without it. What it buys is a guarantee that every answer will parse.
- **The smaller-model version cost a twentieth as much and matched slightly fewer fields.** 95% against 100% in this setup, with every difference on two of the twelve items.
- **Output is the bill in a write-up, and almost nothing in a classification.** A write-up produces about 2,700 tokens from a 790-token prompt. A classification produces about 90.
- **A write-up is not a worse classification; it is a different product.** It never commits to "queue: billing". If the system needs a routing decision, ask for one.
- **How you score matters as much as what you run.** The keyword scorer was wrong in both directions. A reader model that never sees the right answer, followed by an exact comparison, gave a consistent result; it read back 100 of 100 fields correctly on a check where the answer was known.
- **Speed follows output.** The write-up took 22 seconds on Sonnet; the classification took 2, and Gemini's decision call half a second.
- **Scale illustration.** NovaMart's story has 5 million items a week. Extrapolating from these runs: about $147,500 a week for Sonnet write-ups, about $940 for Haiku with the schema, about $725 for Haiku in plain text, about $470 through the Batch API.

### Caveats

- Twelve items, three runs each, with the right answer defined on 42 fields. The five-point gap between Haiku and Sonnet is six fields on two items.
- The free-text answers were read by a single model in one pass.
- The Gemini version is not like for like: its questions differ from the schema (priority comes from a severity score), and its price was not checked against a published rate card.
- A decision model returns labels and probabilities only; it cannot rewrite text, so it cannot mask personal data inline.
- Batch pricing is computed from the published discount; no batch job was run.
- Sonnet and Haiku ran with different thinking settings, as the app configures them.

Full results: `analysis/cat1_ablation.md`. Raw records: `backend/experiments/cat1_ablation/runs.jsonl` and `extractions.jsonl`.

---

## Part 2: Generative synthesis and drafting

**One-line result:** a section template halved the cost of a draft and made it clearer and tighter, but a blind grader preferred the long draft every time, and under the template the drafts filled in owners and deadlines the source did not give. One added sentence, allowing the template to say "not stated", removed almost all of those errors at no cost.

Cost figures are from the original 12 recorded drafts. Quality was added on 25 Nov 2026 by scoring those same drafts; nothing was redrafted.

### What the deck says

- **Shape:** long-form content creation where dense output dominates the economics.
- **Profile:** 1,500–4,000 tokens in, 800–3,000+ out, ratio around 1:1 to 1:2.
- **Lever:** because output tokens cost 3–5× input tokens, enforce structured section templates and length bounds.
- **Use cases:** collateral drafting, transcript synthesis, regulatory reporting.

### What was built

The NovaMart Executive and Compliance Readout Studio, tested on 4 documents:

- **Executive synthesis (2).** A 45-minute Diwali peak operations war-room transcript; a brand partnership proposal brief.
- **Regulatory filing (2).** A lithium-ion thermal event safety filing; a cross-border seller KYC and anti-money-laundering audit report.

Three versions of each document:

- **Sonnet, unbounded.** An open-ended long-form report.
- **Sonnet, template.** A four-section JSON document (summary, three findings, three risks, three actions) with word caps. Every action must have an owner and a time window.
- **Haiku, template.** The same template on the small model.

A reviewer can lock a section, edit it by hand, or regenerate one section without redrafting the rest.

Quality was measured three ways:

- **Fact checklist.** 18 facts per source document, written from the source alone: 8 core (what a decision-maker cannot act without) and 10 supporting. Scored by deterministic matching.
- **Numbers not in the source.** Every number in each draft was checked against the source; the rest were reviewed one by one.
- **Blind grading.** A model that was not one of those under test (Opus 5.5) graded each draft three times on five dimensions, listed every factual error with quotes, and chose between drafts head to head in both orders. It was not told which model or version wrote what, or anything about cost. Every serious error it reported was then checked by hand against the source.

### Results: cost

| Rung | Cost per 1,000 documents | vs naive | Prompt tokens (median) | Output tokens (median) | Output share of cost |
|---|---:|---:|---:|---:|---:|
| Sonnet 5.5, unbounded long-form | $58.92 | — | 3,640 | 4,975 | 88% |
| Sonnet 5.5, section template with caps | $27.25 | −53.8% | 4,844 | 1,733 | 65% |
| Haiku 5.5, section template with caps | $1.39 | −97.6% | 4,844 | 1,820 | 65% |

| Review action | Cost per 1,000 | Note |
|---|---:|---|
| Regenerate one section on Sonnet | $13.81 | −49% against redrafting the whole templated document |
| Regenerate one section on Haiku | $0.74 | |
| Haiku draft plus one Sonnet section fix | $15.20 | −74% against the unbounded Sonnet draft |

### Results: quality

| Rung | Core facts | Supporting facts | Accuracy | Coverage | Clarity | Actionability | Concision | Serious errors | Minor errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Sonnet, unbounded | 32/32 | 40/40 | 3.9 | 4.9 | 4.0 | 3.8 | 2.8 | 1 | 21 |
| Sonnet, template | 32/32 | 37/40 | 3.1 | 4.0 | 4.9 | 3.8 | 4.2 | 6 | 18 |
| Haiku, template | 32/32 | 36/40 | 2.6 | 3.5 | 4.4 | 3.3 | 4.1 | 10 | 18 |

Grades are 1 to 5, averaged over four documents and three grading passes. Error counts are distinct errors across the four drafts.

Head to head, "which draft should be sent as is":

| Pairing | Result |
|---|---|
| Sonnet unbounded against Sonnet template | Unbounded preferred in 8 of 8 |
| Sonnet unbounded against Haiku template | Unbounded preferred in 8 of 8 |
| Sonnet template against Haiku template | Sonnet preferred in 7 of 8 |

Numbers that do not appear in the source:

| Rung | Numbers checked | Not in source | Correct arithmetic | Wrong arithmetic | Not derivable from the source |
|---|---:|---:|---:|---:|---:|
| Sonnet, unbounded | 783 | 46 | 44 | 1 | 0 |
| Sonnet, template | 273 | 6 | 1 | 0 | 5 |
| Haiku, template | 295 | 8 | 2 | 0 | 6 |

(One of the unbounded draft's 46 was a label, not a claim.)

### What the serious errors were

Of the 17 serious errors, most are the same kind: an owner or a deadline the source never gave.

- **Deadlines not in the source.** The audit-report source asks for "time-bound" milestones but states no dates. Both templated drafts contained dates of their own: "Within 30 days", "Within 45 days", "Q1 2027".
- **Owners not in the source.** The safety-filing source attributes its commitments only to "Management". The templated drafts named teams such as "Customer Safety Operations".
- **Misassigned obligations.** In the partnership brief, pre-positioning stock is the brand's condition for a lower fee. Both templated drafts made it a NovaMart manager's task, and the Haiku draft attached a deadline that belongs to a different milestone.
- **The unbounded draft's one serious error** was of the same kind: a quarterly reporting commitment that is not in the source.

The template requires an owner and a time window for every action. Across the eight templated drafts, the grader flagged an owner or deadline the source does not support in 16 of 24 action items, 8 for each model, and 12 of those were serious. The one document whose source names its owners and dates had none. Where the source left a field open, the draft still contained an entry for it.

### Follow-up: letting the template say "not stated"

On 26 Nov 2026 one sentence was added to the template's instructions: give an owner and a time window only if the source states them, otherwise write "Not stated in source", and never supply one the source does not give. Nothing else changed.

The test was 48 fresh drafts: the four documents, both models, the original template and the new one, three drafts of each. All were graded blind, and each new-template draft was compared head to head with its matching original-template draft. Each row below covers 12 drafts and 36 action items.

| Template | Model | Owners: found in source / "not stated" / unsupported | Time windows: found in source / "not stated" / unsupported | Serious errors per draft | Accuracy | Actionability | Cost per 1,000 documents |
|---|---|---|---|---:|---:|---:|---:|
| Original | Sonnet | 14 / 0 / 22 | 23 / 0 / 13 | 1.25 | 3.3 | 3.7 | $27.19 |
| Original | Haiku | 10 / 0 / 26 | 17 / 0 / 19 | 2.25 | 2.7 | 3.3 | $1.39 |
| With the sentence | Sonnet | 8 / 28 / 0 | 21 / 15 / 0 | 0.00 | 4.2 | 3.1 | $26.82 |
| With the sentence | Haiku | 0 / 36 / 0 | 22 / 14 / 0 | 0.25 | 3.8 | 2.7 | $1.36 |

Head to head:

| Pairing | Result |
|---|---|
| New template against original template, same document, model and draft number | New preferred in 47 of 48 |
| New template against the stored long draft | Long draft preferred in 15 of 16 |

What it shows:

- **One sentence removed almost all the serious errors, at no cost.** Across 24 drafts each, serious errors fell from 42 to 3.
- **Accuracy grades rose by about a point** on both models. The Sonnet template's 4.2 is in the range of the long draft's 3.9, though those are different drafts.
- **It did not close the gap to the long draft.** The long draft was still preferred 15 times in 16. The grader now split on accuracy (long draft 11, new template 1, tie 4) and chose the long draft every time on usefulness to the reader.
- **A stated blank scores lower on actionability.** A plan that says "owner not stated" is graded as less actionable than one that names an owner, including one the source does not give. The grade fell from 3.7 to 3.1 on Sonnet and from 3.3 to 2.7 on Haiku.
- **The two model sizes applied the sentence differently.** The Haiku drafts wrote "not stated" for all 36 owners, including on the document whose source names them. The Sonnet drafts kept 8 owners the source gives. Supporting facts covered fell as a result, from 110 to 94 of 120 on Sonnet and from 104 to 92 on Haiku.
- **The fresh original-template drafts reproduced the first finding.** By a mechanical check, 48 of their 72 owners and 32 of their 72 time windows had no support in the source.

### Deck claims against the data

| Claim | Measured | Verdict |
|---|---|---|
| Input 1,500–4,000 tokens | Unbounded 3,458–3,874; templated 4,667–5,073 | Partly |
| Output 800–3,000+ tokens | Unbounded 4,698–6,000; templated 1,695–1,853 | Supported |
| Ratio 1:1 to 1:2, output-dominated cost | 1:1.44, output is 88% of cost | Supported |
| Output costs 3–5× input | Exactly 5× on both Claude models | Supported |
| Templates and length bounds control output cost | −54% on the same model | Supported |
| …without losing draft quality (our addition; the deck does not claim it) | Long draft preferred in 16 of 16 comparisons; serious errors 1 against 6 and 10 | Not supported |

### Points worth making in the post

- **This is the one archetype where output is larger than input.** An unbounded draft writes about 5,000 tokens from a 3,600-token brief, and output is 88% of the bill.
- **The template trades cheap tokens for expensive ones.** It adds about 1,200 prompt tokens and removes about 3,200 output tokens. At 5× output pricing that is a 54% saving.
- **Nothing essential was dropped.** All three versions carried every core fact, and the templated drafts were graded clearer and far more concise.
- **The long draft still won every comparison.** The grader weighed accuracy first, and the templated drafts lost on it.
- **A required field is an instruction to fill it.** The template demands an owner and a time window per action. When the source had none, the drafts supplied one. The pattern follows the template, not the model size: it appeared with the template on both models.
- **The long draft's extra numbers were mostly derived from the source.** Of 46 numbers not found in the source, 44 were correct arithmetic on source figures, and one described 3.195 as "over 3.2×".
- **Serious errors were more frequent in the Haiku drafts.** They had 10 against 6 for the Sonnet drafts on the same template, including obligations assigned to a different party from the one in the source.
- **Section-level review is its own saving.** Fixing one section costs half of a full redraft, and editing by hand costs nothing. Given where the errors sit, the action plan is the section to review.
- **Checking is cheap.** Grading all 12 drafts three times and comparing them head to head took 60 calls and about $5.
- **Speed.** On one brief, the unbounded draft took 39.5 s; the templated drafts took 12–14 s.

### Caveats

- One draft per version per document. The three grading passes measure the grader's consistency, not how much drafts vary.
- The grades come from a single model acting as grader. It was consistent (every grade within one point across passes; 11 of 12 pairings unchanged when the order was swapped), and its serious findings were verified by hand, but it is one grader.
- The grader can see that a draft is long or short, even though it does not know what wrote it.
- The unbounded version was asked for an exhaustive report, the templated ones for a tight one. Coverage and concision grades partly reflect those instructions.
- Only four documents.
- The follow-up used one grading pass per draft, where the first round used three, and the phrase "Not stated in source" lets the grader tell the two templates apart in a head-to-head comparison.
- The follow-up's check of whether an owner or date is "found in source" only tests that the words occur there, not that the source assigns that action to them.

Full results: `analysis/cat2_quality.md`, and `analysis/cat2_not_stated.md` for the follow-up. Grader records: `backend/experiments/cat2_quality/judgements.jsonl` and `backend/experiments/cat2_not_stated/`. Fact checklist: `backend/app/data/cat2_quality_keys.json`.

---

## Part 3: Multi-turn conversational assistants

**One-line result:** caching the fixed prefix cut session cost by 40% with no loss of quality; compacting old turns saved a further 11% and cost the assistant almost all memory of earlier details.

This section uses the quality rerun of 25 Nov 2026: 18 live sessions (two scripted sessions, three versions, three repeats each), scored against a fixed answer key.

### What the deck says

- **Shape:** stateful dialogue where history and retrieved context accumulate on every turn.
- **Profile:** 10,000–40,000+ tokens per session, 150–600 output tokens per turn. The deck's chart shows context of 1.2k, 6.5k, 14k and 25k+ at turns 1, 3, 6 and 10.
- **Lever:** prefix context caching and sliding-window memory summarisation, to prevent quadratic session cost.
- **Use cases:** IT and HR service desk, consumer dialogue, field operations assistant.

### What was built

The NovaMart IT and HR Unified Service Desk: two ten-turn employee sessions on Sonnet 5.5, grounded in a 9,860-token policy handbook.

- **Session 1.** An employee returning from parental leave: laptop management lockout, VPN certificate, and payroll back-pay.
- **Session 2.** A senior engineer's second day: security-key access to production, an expense hold, and a relocation tax gross-up.

Turn 10 of each session asks for a consolidated summary of everything resolved in turns 1–9.

All three rungs use the same model. Only the context strategy changes:

- **Full history, no cache.** Everything is re-sent at full price on every turn.
- **Full history, cached prefix.** The same, with the handbook cached.
- **Cached prefix plus compaction.** Once four turns are held verbatim, all but the latest are compacted by a summariser call into a small structured memory of at most 14 short items. This happens before turns 5 and 8. The summariser's cost is included.

Quality was measured three ways, all by deterministic matching against an answer key written from the handbook and the scripted user messages, never from model replies:

- **Answers grounded.** Does each reply in turns 1–9 cite the policy, queue, command and figures the handbook prescribes? (69 facts.)
- **Details kept in the final summary.** How many specifics from turns 1–9 appear in the turn-10 summary? (49 facts.)
- **Recall questions.** After turn 10, six short questions per session, each about one detail the user stated once in an earlier turn, such as a serial number, an invoice number or a date. Each is asked independently.

### Results: cost

| Rung | Cost per 1,000 sessions | vs naive | Warm-fleet cost | Prompt tokens per session |
|---|---:|---:|---:|---:|
| Full history, no cache | $399 | — | $399 | 163.4k |
| Full history, cached prefix | $240 | −39.9% | $216 | 160.6k |
| Cached prefix plus compaction | $212 | −46.7% | $189 | 143.3k |

Context size per turn:

| Rung | Turn 1 | Turn 3 | Turn 6 | Turn 10 | Growth per turn | Peak |
|---|---:|---:|---:|---:|---:|---:|
| Full history, no cache | 10.6k | 13.2k | 17.1k | 21.9k | +1,247 | 22.6k |
| Full history, cached prefix | 10.6k | 13.2k | 16.8k | 21.5k | +1,197 | 22.0k |
| Cached prefix plus compaction | 10.6k | 13.2k | 13.8k | 14.8k | +288 | 15.6k |
| Deck's chart | 1.2k | 6.5k | 14k | 25k+ | about +2,600 | |

Average cost of a single turn:

| Rung | Turn 1 | Turn 2 | Turn 10 |
|---|---:|---:|---:|
| Full history, no cache | $0.031 | $0.030 | $0.052 |
| Full history, cached prefix | $0.039 | $0.011 | $0.033 |
| Cached prefix plus compaction | $0.040 | $0.011 | $0.024 |

### Results: quality

| Rung | Answers grounded (turns 1–9) | Details kept in final summary | …from turns 1–3 | …from turns 4–6 | …from turns 7–9 | Recall questions answered |
|---|---:|---:|---:|---:|---:|---:|
| Full history, no cache | 205/207 (99%) | 106/147 (72%) | 37/51 (73%) | 40/51 (78%) | 29/45 (64%) | 36/36 |
| Full history, cached prefix | 203/207 (98%) | 110/147 (75%) | 39/51 (76%) | 41/51 (80%) | 30/45 (67%) | 36/36 |
| Cached prefix plus compaction | 205/207 (99%) | 91/147 (62%) | 24/51 (47%) | 37/51 (73%) | 30/45 (67%) | 2/36 |

What the compacting version answered on the 34 recall questions where it did not give the reference value, checked by hand:

- **33 declined.** It said the detail was not in its session memory and pointed the user to where to find it.
- **1 gave a labelled estimate** of a dollar amount, $1,780 against a true $1,775, worked out from a figure in the latest message.
- **None stated a value that was not in the session.**

Its two correct answers were the same detail both times: the laptop serial number, which the summariser had chosen to keep.

### Deck claims against the data

| Claim | Measured | Verdict |
|---|---|---|
| Context grows 1.2k → 6.5k → 14k → 25k+ | 10.6k → 13.2k → 17.1k → 21.9k | Partly |
| Session of 10k–40k+ tokens | Peak context 22.6k; billed prompt tokens 163k per session | Partly |
| Output 150–600 tokens per turn | Median 576, range 342–3,983; 103 of 180 turns in range | Partly |
| Caching plus summaries prevent quadratic cost | Growth falls from +1,247 to +288 tokens per turn; cost −47% | Supported |
| …without losing answer quality (our addition; the deck does not claim it) | Recall questions 2/36 against 36/36; early details in the final summary 47% against 76% | Not supported |

### Points worth making in the post

- **Caching is the free lunch.** It cut cost by 40% and changed no quality measure. Nothing was traded away.
- **Compaction is a trade, and at ten turns a poor one.** It saved a further 11% ($240 to $212 per 1,000 sessions) and the assistant could then recall 2 of 36 earlier details.
- **What compaction keeps and loses.** Answers to new questions were unaffected, at 99%. The gist of the session survived. What went was the exact values: IDs, invoice numbers, dates, names, amounts.
- **The loss follows the compaction boundary.** In the final summary, details from turns 1–3 (compacted first) fell from 76% to 47%. Details from turns 7–9, still held verbatim at that point, were kept equally well by every version.
- **Missing details were reported as missing.** Asked for a detail that was no longer in its context, the assistant said so and suggested where to look in 33 of 34 cases, and in none did it state a different value. The gap is therefore visible to the user.
- **The saving should grow with session length.** Uncompacted context grows by about 1,250 tokens a turn; compacted, by about 290. Ten turns is early in that curve. Longer sessions were not tested.
- **The memory's design is a choice.** This compactor keeps at most 14 short items and costs about $32 per 1,000 sessions. A memory that pins every user-supplied identifier would cost more tokens and forget less. That variant was not tested.
- **Even full history loses detail in a capped summary.** With everything in context, the turn-10 summary still carried only about three quarters of the key details, because it is limited to 250 words.
- **The session band hides the bill.** Context peaks at 22k, inside the deck's band. But every turn re-sends everything before it, so one session bills 163k prompt tokens, four times the top of the band.
- **The first cached turn costs more.** Writing the cache costs 1.25× normal input, so turn 1 is $0.039 against $0.031. Turn 2 drops to $0.011.
- **Fleet economics are better than single-session economics.** When many sessions share the cached handbook, the saving rises to 46% with caching alone and 53% with compaction.

### Caveats

- Two scripted sessions, each run three times per version. The recall result is large enough to survive that; the smaller differences are not.
- Scoring is literal matching against an answer key, so a correct paraphrase can be missed. Every missed recall answer was read by hand.
- One compactor design was tested, with a deliberately tight memory.
- The compacting version's system prompt tells the model that older turns are compressed. That may make it readier to decline than it otherwise would be.
- The recall questions come after turn 10, by which point a third compaction has run, so all of turns 1–9 are in compacted memory.
- Output per turn varies a great deal between repeats (342–3,983 tokens) because the model sometimes thinks before answering. Session cost varies noticeably between repeats as a result (the naive version ranged from $0.37 to $0.43 a session).
- The "without losing answer quality" row is our addition. The deck's own claim, about cost, holds.

Full results: `analysis/cat3_quality_rerun.md`. Raw records: `backend/experiments/cat3_quality/runs.jsonl`. Answer key: `backend/app/data/cat3_quality_keys.json`.

---

## Part 4: Multi-document RAG and deep ingestion

**One-line result:** caching the whole corpus gave the best answers and the lowest steady-state cost; retrieval was cheaper for a short session but, once look-alike contracts were added, it began telling the reader that terms were "not in the documents" when they were. Two added lines of instruction removed those claims and halved the serious errors, without closing the gap to caching.

This section uses the rerun of 26 Nov 2026: 192 live answers (four versions, two corpus sizes, three sessions of eight questions each), scored against an answer key and graded blind.

### What the deck says

- **Shape:** high-context reasoning over large document sets, producing grounded answers.
- **Profile:** 15k–100k+ tokens in, 400–1,500 out, ratio of 20:1 to 100:1.
- **Lever:** pair hybrid retrieval (reranking and chunk filtering) with context caching on shared document repositories.
- **Use cases:** legal due diligence, grounding repositories, financial filing analysis.

### What was built

The NovaMart Supplier Deal-Room: seven contract and compliance documents for one supplier, split into 28 clauses. The documents include a wholesale master agreement, a peak-season service-level addendum, a data-protection schedule, safety and tax riders, a statutory audit extract and a side letter.

Eight due-diligence questions, each needing clauses from several documents: liability caps and carve-outs, peak-season overrides, an equity-stake condition, data localisation, tax escrow, statutory audit notes, product safety, and commercial price adjustments.

Two corpus sizes:

- **1×.** The seven documents: 18.5k tokens as plain text.
- **3×.** The same deal room plus the equivalent seven documents for two other suppliers, 21 documents and 54k tokens. The added contracts have the same structure and clause numbers but different parties, amounts, percentages and dates. Every question is scoped to the first supplier.

Four versions:

- **Full corpus, no cache.** Every document pasted as plain text on every question. No citations.
- **Full corpus, cached and cited.** Every document sent as a cached document block, with the API's native citations.
- **Keyword search plus rerank.** Keyword search narrows the clauses to 10, Haiku picks the best 5, Sonnet answers from those 5 with citations. Nothing cached.
- **Combined, the deck's lever.** Haiku reads the whole cached corpus and picks the best 5 clauses; Sonnet answers from those 5 with citations.

Quality was measured three ways:

- **Key facts.** 53 facts across the eight questions, written from the contracts alone, scored by deterministic matching.
- **Citations and retrieval.** Whether citations point at the clauses each question needs, whether the needed clauses reached the answering model, and whether another supplier's clauses or figures crept in.
- **Blind grading.** A model not under test (Opus 5.5) graded each answer for correctness and completeness against the first supplier's contracts and listed every factual error with quotes. Every serious error's source quote was then checked against the contracts.

### Results: cost

Cost per question, in dollars. "Session from cold" is the average over an eight-question session that starts with an empty cache; "warm" is the steady state once the cache exists.

| Version | 1× session from cold | 1× warm | 3× session from cold | 3× warm |
|---|---:|---:|---:|---:|
| Full corpus, no cache | $0.046 | $0.046 | $0.117 | $0.117 |
| Full corpus, cached and cited | $0.025 | $0.019 | $0.038 | $0.019 |
| Keyword search plus rerank | $0.025 | $0.025 | $0.028 | $0.028 |
| Combined | $0.024 | $0.024 | $0.026 | $0.025 |

How many questions must share one cache write before the first version is the cheaper of the pair:

| Comparison | 1× corpus | 3× corpus |
|---|---:|---:|
| Cached full corpus against keyword search plus rerank | 9 | 18 |
| Combined against keyword search plus rerank | 5 | 4 |
| Cached full corpus against combined | 10 | 23 |

The one-off cost of writing the cache is $0.052 at 1× and $0.149 at 3× for the full corpus on Sonnet, and under one cent for the combined version, where the cache is on Haiku.

### Results: quality

Each cell is 24 answers.

| Version | Corpus | Key facts stated | Answers with a serious error | Correctness (1–5) | Completeness (1–5) |
|---|---|---:|---:|---:|---:|
| Full corpus, no cache | 1× | 98% | 1 | 4.5 | 4.8 |
| | 3× | 94% | 3 | 4.5 | 4.8 |
| Full corpus, cached and cited | 1× | 94% | 0 | 5.0 | 4.6 |
| | 3× | 94% | 0 | 4.8 | 4.7 |
| Keyword search plus rerank | 1× | 96% | 0 | 4.7 | 4.7 |
| | 3× | 91% | 8 | 4.0 | 4.2 |
| Combined | 1× | 97% | 1 | 4.5 | 4.7 |
| | 3× | 96% | 6 | 4.4 | 4.5 |

Retrieval, for the two versions that pass only five clauses to the answering model:

| Version | Corpus | Needed clauses that reached the answering model | Clauses passed on that belonged to another supplier |
|---|---|---:|---:|
| Keyword search plus rerank | 1× | 99% | 0 of 120 |
| | 3× | 86% | 25 of 120 |
| Combined | 1× | 100% | 0 of 120 |
| | 3× | 100% | 0 of 120 |

Citations and supplier mix-ups:

- **Every cited version cited every answer.** 144 of 144, with nothing filtered out.
- **No citation pointed at another supplier's contract**, out of 746 citations on the larger corpus.
- **One answer in 192 stated another supplier's figure**, and it did so to exclude it by name.

### What the serious errors were

Nearly all of the retrieval versions' serious errors are the same statement: that the documents contain no such term.

- "The documents specify no banking NOC or escrow gate." The side letter makes a bank's no-objection certificate a condition, and the tax schedule sets up an escrow holdback.
- "The MSA baseline cap is not in the excerpts, so that contrast cannot be quantified." The master agreement states a 2.0% cap, and the addendum overrides it.
- "The Note 21 warranty reserve is not in the provided deal-room text." It is in the audit extract.

The answer format asks every answer to name a sign-off gate, such as a bank certificate or an escrow. When the five clauses in front of the model did not contain one, it reported that the documents had none. With the whole corpus in context, that error did not occur.

### Follow-up: telling the model it may not have seen everything

On 26 Nov 2026 the answer instructions for the two retrieval versions were changed in two lines. The sign-off gate is to be named "as stated in the text provided", with "None stated in the text provided" written when there is none. And one rule was added: when something is not in the text provided, say so; do not say the documents or the deal room lack it. Nothing else changed.

The two retrieval versions were rerun at both corpus sizes, three sessions of eight questions each, and graded the same way. Each cell is 24 answers.

| Version | Corpus | Answers claiming the contracts lack a term: before → after | Answers with a serious error: before → after | Correctness (1–5): before → after |
|---|---|---|---|---|
| Keyword search plus rerank | 1× | 9 → 0 | 0 → 2 | 4.7 → 4.5 |
| | 3× | 12 → 0 | 8 → 3 | 4.0 → 4.3 |
| Combined | 1× | 12 → 0 | 1 → 0 | 4.5 → 4.8 |
| | 3× | 13 → 0 | 6 → 2 | 4.4 → 4.5 |

What it shows:

- **The false claims disappeared.** Before, 46 of 96 retrieval answers said the contracts lacked something. After, none did; 84 said instead that it was not in the text provided.
- **Serious errors roughly halved,** from 15 to 7 of 96, and from 14 to 5 of 48 on the larger corpus.
- **Key facts stated did not change, and cost per question fell slightly,** to $0.023–0.026, because the answers were a little shorter. That moves the point at which caching the whole corpus becomes cheaper than keyword retrieval from 9 and 18 questions per cache write to 12 and 22.
- **It was not a gain in every cell.** On the small corpus the keyword-retrieval version went from 0 to 2 answers with a serious error.
- **It narrows the gap to the cached full corpus without closing it.** Caching had no serious errors in 48 answers. The grader, who can see every clause, still marks an answer down when it says a term is not in the text provided and the term exists elsewhere.
- **The reader still does not get the answer.** "Not in the text I was given" is accurate, and it tells the reader to look further, but the question stays open.

The change was measured on the retrieval versions only, and the lab app now uses it for its retrieval version. Its effect on the versions that see the whole corpus was not tested, and those versions keep the original instructions.

### Deck claims against the data

| Claim | Measured | Verdict |
|---|---|---|
| Input 15k–100k+ tokens | 18.5k per question at 1×, 54k at 3×; 6k when only five clauses are sent | Supported |
| Output 400–1,500 tokens | Median 1,036, range 760–2,992; 150 of 192 answers in range | Partly |
| Ratio 20:1 to 100:1 | 21:1 at 1×, 62:1 at 3× | Supported |
| Pair hybrid retrieval with context caching | The pairing kept 99–100% of the needed clauses, passed on no wrong-supplier clauses, and cost the least per question from a cold start. After the instruction change its serious errors (0 and 2 of 24) are not clearly above the cached full corpus's, though its answers are still graded lower | Supported |
| …without losing answer quality (our addition; the deck does not claim it) | Caching: no loss. Retrieval after the instruction change: 2 to 3 answers in 24 with a serious error against 0, and lower correctness grades; before it, 6 to 8 on the larger corpus | Partly |

### Points worth making in the post

- **Caching beats retrieval on quality when the corpus fits in context.** The cached full corpus had no serious errors in 48 answers and the highest correctness grade at both sizes.
- **Which is cheaper depends on traffic.** An eight-question session from a cold cache is cheapest with retrieval on the larger corpus ($0.026–0.028 against $0.038 a question). Steady traffic against a warm cache is cheapest with caching ($0.019). The crossover is 9 questions per cache write at 1× and 18 at 3×, and the cache lasts five minutes between uses.
- **Cached cost barely grows with the corpus.** Tripling the corpus raised the uncached cost per question 2.6 times. Warm cached cost rose 3%.
- **Keyword retrieval returned fewer of the needed clauses among look-alike documents.** With two other suppliers' contracts added, it delivered 86% of the needed clauses instead of 99%, and one clause in five it passed on was from another supplier.
- **The deck's pairing fixes retrieval, cheaply.** Letting the small model read the whole cached corpus found every needed clause and passed on nothing from another supplier, for the same cost as keyword retrieval. The cache it needs costs under a cent to write.
- **But perfect retrieval is not the same as full context.** The combined version still had a serious error in 6 of 24 answers on the larger corpus. Five clauses answer the question asked; they cannot show what else the contracts say.
- **"Not found" from a retrieval system means "not in what I was shown".** The dominant error was a confident statement that the documents lacked a term. A reader has no way to tell that from a true absence.
- **No answer mixed up the suppliers.** Even with three near-identical deal rooms in one prompt, no version attributed one supplier's terms to another.
- **Citations held up without filtering.** The original experiment rejected uncited answers and tried again. Here every answer was kept, and all 144 were cited.
- **The cheapest good answer had no citations.** Pasting everything with no cache scored 4.5 for correctness, above both retrieval versions on the larger corpus, at two to six times the cost and with nothing for a reviewer to check.

### Caveats

- Eight questions on one deal room, three sessions per cell. The added suppliers' contracts are mechanical variants of the first supplier's, not independently written.
- One grading pass per answer by a single model. Its serious findings were checked against the contracts by hand.
- The largest corpus is 54k tokens. The comparison will change where a corpus no longer fits in context or a cache write becomes too expensive to repeat.
- The keyword search was tuned on these questions and this supplier, so its results on the small corpus are optimistic.
- The answer format's request for a sign-off gate is what exposes the partial-context error. The follow-up shows better instructions reduce it; they do not remove the cause, which is that the model answers from five clauses.
- The follow-up's before and after figures come from separate sets of sessions with the same questions, three sessions each.
- Break-even points depend on answer length. Cited answers ran longer in this rerun than in the original capture, which had put the 1× crossover at 5 questions.

Full results: `analysis/cat4_quality_rerun.md`. Raw records: `backend/experiments/cat4_quality/runs.jsonl` and `judgements.jsonl`. Answer key: `backend/app/data/cat4_quality_keys.json`.

---

## Part 5: Autonomous process orchestration

**One-line result:** asking the database for less and using a smaller model cut the cost of reconciling an invoice by 98% with every voucher still correct; the deterministic policy tool and the step budget, which the first version of this experiment credited, added nothing measurable.

This section uses the ablation of 26 Nov 2026: 216 live runs (six versions, twelve invoices, three runs each), every run kept, scored field by field against vouchers derived by hand from the policy manual.

### What the deck says

- **Shape:** goal-directed workflows that chain planning, tool calls, validation and state updates.
- **Profile:** 25k–150k+ tokens in, 1,500–8,000 out, in a plan, call, verify, dispatch loop.
- **Lever:** max-step loop budgets, deterministic guardrails, and small-model routing for routine tool calls.
- **Use cases:** invoice reconciliation, claims adjudication, supply chain dispatch.

### What was built

The NovaMart three-way invoice reconciliation agent. It matches a vendor invoice against the purchase order and the warehouse goods receipt in a live SQLite database, applies an accounts-payable policy manual, and commits a payment voucher with five fields: the decision, the net principal, the tax paid, the tax held in escrow, and the deduction.

Twelve invoices: the original three plus nine new ones written to cover the manual's rules. They include a clean match, rejected units, price rises inside and outside tolerance, an authorised amendment, freight above the cap, a tax escrow, two hard stops, and two disputes with several problems at once.

Six versions, each adding or changing one thing:

| # | Version | What it adds |
|---|---|---|
| 1 | Raw tables, Sonnet chooses its tools | The baseline: five `SELECT *` lookups available, no cache, the model does the arithmetic |
| 2 | Same, manual cached | Caching alone |
| 3 | One narrow query, cached, Sonnet computes | A single query returning only the needed columns |
| 4 | Narrow query plus a deterministic policy tool, Sonnet | The tool computes the voucher in code and the model copies it |
| 5 | One narrow query, cached, Haiku computes | The small model, with no policy tool |
| 6 | Haiku first with the policy tool, escalating to Sonnet | The small model plus the tool, handing off to Sonnet when the tool flags a deduction |

Versions 4 and 6 are the "governed" designs from the first version of the experiment.

### Results

Eleven invoices, three runs each: 33 runs per version.

| # | Version | Correct vouchers | Cost per 1,000 invoices (cold start) | Warm cache | Model turns | Prompt tokens per run |
|---|---|---:|---:|---:|---:|---:|
| 1 | Raw tables, Sonnet | 33 | $154 | $154 | 3–4 | 68k |
| 2 | Raw tables, cached | 32 | $111 | $90 | 3–4 | 69k |
| 3 | Narrow query, Sonnet computes | 33 | $43 | $23 | 3 | 29k |
| 4 | Narrow query plus policy tool, Sonnet | 33 | $51 | $30 | 4 | 42k |
| 5 | Narrow query, Haiku computes | 33 | $2.40 | $1.45 | 3 | 29k |
| 6 | Haiku plus policy tool, escalating | 33 | $23 | $12 | 4 | 42k |

What each step did:

| Step | Cost change (cold start) | Correct vouchers |
|---|---:|---|
| Caching alone (1 → 2) | −28% | 33 → 32 |
| Narrow query (2 → 3) | −61% | 32 → 33 |
| Deterministic policy tool (3 → 4) | +18% | 33 → 33 |
| Smaller model, no tool (3 → 5) | −94% | 33 → 33 |
| Tool plus escalation on the smaller model (5 → 6) | 9.4 times the cost | 33 → 33 |

No run on any version reached a step cap, and no output was cut off.

### When the policy tool is wrong

The twelfth invoice is reported separately, because writing it exposed a bug in the lab's own policy tool.

- **The case.** One line is billed 1.28% above the purchase-order price. The manual allows a rise within 1.5% only on purchase orders marked as index-linked. This one is not, so the line should be paid at the purchase-order price and the difference deducted.
- **The tool.** It allows any rise within 1.5% and approves the invoice in full: an overpayment of ₹26,904.
- **The result.** In all 12 runs where the model worked out the voucher itself, it followed the manual and made the deduction. In all 6 runs that used the policy tool, the committed voucher carried the tool's figure, as those versions are instructed to do.
- **A detail from the records.** In one of those six runs the summary flagged the overrun for review and noted that "the gate allowed it under the 1.5% rounding band". The committed voucher was the tool's full payment, which is what that version's instructions require.

- **The fix.** The tool was corrected afterwards to apply the manual's condition. Rerun with the corrected tool, all 6 runs committed the right voucher. Three other gaps found while writing the new invoices were fixed at the same time: approved freight waivers were ignored, the tax rate was taken from the first line only, and there was no check for duplicate invoices or frozen vendors. None of the twelve invoices exercises those three, so no result here depends on them.

### How the first version went wrong

The first version of this experiment reported an 80% saving from a step budget, caching and a policy check together, and 91% with Haiku added, with a correct voucher on every version. Three things made that less than it seemed:

- **The baseline was scripted.** Its instructions told the model to call five lookups one at a time in a fixed order, including one it never needed. Left to choose, the model made the first four lookups in a single turn and finished in 3 or 4 turns, not 7. On the two larger original invoices the scripted run cost about half as much again as the free one.
- **The governed versions could not fail.** The capture script threw away any governed run that was not exactly right and tried again.
- **The governed versions did no arithmetic.** The policy tool computed the answer and the model copied it, so "Haiku is as accurate as Sonnet" was true by construction.

### Deck claims against the data

| Claim | Measured | Verdict |
|---|---|---|
| Input 25k–150k+ tokens per task | 44k–77k with raw tables; 28k–31k with a narrow query; 40k–43k with the policy tool added | Supported |
| Output 1,500–8,000 tokens per task | Median 1,426; 77 of 198 runs in range | Partly |
| Step budgets, deterministic guardrails and small-model routing | Small-model routing cut cost 94% with every voucher correct. The guardrail added 18% and no accuracy, and copied its own error. No run came near a step budget | Partly |
| …without losing accuracy (our addition; the deck does not claim it) | No loss detected: every version got at least 32 of 33 right. But on the invoice where the policy tool is wrong, the versions using it were wrong 6 times in 6 | Partly |

### Points worth making in the post

- **The saving came from two plain things.** Fetch only the columns you need (−61%), and use the smallest model that gets it right (−94%). Together with caching they took the cost from $154 to $2.40 per 1,000 invoices.
- **Without the policy tool, the vouchers matched the hand-derived answers in 143 of 144 runs,** including the case where the tool itself was wrong.
- **A guardrail written in code moves the error; it does not remove it.** When the tool was right it added a turn and 18% to the cost. When it was wrong, every run that used it committed its figure, as instructed.
- **So test the guardrail as hard as the model.** The bug surfaced only because the new invoices' answers were worked out by hand from the manual first and then compared with the tool.
- **The step budget was insurance, not a saving.** Every version finished in 3 or 4 turns with a cap of 12 available.
- **Eager escalation is expensive.** The Haiku-first design hands off to Sonnet whenever the tool reports any deduction, which was 15 runs in 33. It cost nine times as much as Haiku alone and was no more accurate.
- **Caching helps less when tool output dominates.** The cached manual is under 9k tokens of a 68k prompt; the rest is raw table dumps that change on every invoice. Caching alone saved 28% from a cold start and 41% warm.
- **Offer a tool and it gets used.** Free to choose, the model still made the unneeded vendor-history lookup in 28 of 33 runs.
- **One voucher in 198 did not match.** It differed from the reference by exactly ₹1,000,000 on the most complex invoice, in the cached raw-table version.
- **The bill is almost all input.** Even in the cheapest version, a run reads about 29k tokens and writes about 1.5k.

### Caveats

- Twelve invoices, three runs each. Every version scored at or near 100%, so the experiment cannot detect small differences in accuracy.
- The policy rules are simple and fully written down. A deterministic tool may earn its place on messier cases, or for audit reasons this experiment does not measure.
- The policy tool's bug is specific to this lab, and has since been fixed. The general point is that the tool was trusted without being tested.
- The tool still hands off to Sonnet on any deduction, where the manual describes escalation only for disputes with several problems. That rule was left as it is.
- The policy manual shown to every version mentions the narrow query, the policy tool and a four-step budget by name, including to versions that do not have them. None tried to call a tool it lacked.
- Sonnet and Haiku ran with different thinking settings, as the app configures them, so the model swap changes both.
- Costs here start every run from a cold cache; a busy system would sit between the cold and warm columns.

Full results: `analysis/cat5_ablation.md`. Raw records: `backend/experiments/cat5_ablation/runs.jsonl`. New invoices and their worked answers: `backend/app/data/cat5_ablation_fixtures.py`.

---

## Part 6: Multi-agent swarms and automated engineering

**One-line result:** isolating the agents, caching the shared prefix and tiering the models cut the cost of a verified fix about twelvefold; they made no difference to whether the fix was correct.

**Read this result with one limit in mind: harder tasks might give a different result.** Every version solved every task here, and the tasks were small, single-module fixes. On harder work (changes across several files, longer chains of agent turns, larger codebases) the versions could differ in how often they get the fix right, and the cost ranking could change too. That was not tested.

This section uses the fair rerun of 25 Nov 2026 (60 live runs). It replaces the first version of the experiment, which reported the shared-bus swarm verifying 1 fix in 3. That result was an artefact; the story of why is below and is worth telling in the post.

### What the deck says

- **Shape:** coordinated teams of specialised agents working across large codebases, telemetry and test suites.
- **Profile:** 100k–1M+ tokens in, 10k–50k+ out per run, and 1.5M–10M+ tokens per developer per day.
- **Lever:** isolate sub-agent contexts, cache shared repository prefixes, and measure return by cost per verified outcome.
- **Use cases:** autonomous feature development, security threat hunting, CI/CD failure triage.

### What was built

The NovaMart checkout and pricing self-healing swarm. Five agent turns per run: an orchestrator, a CI triager, a patch author, a security critic and a merge gate.

Three incidents, each a single-file fix:

- **CI failure.** A checkout tax module under-remitting tax through floating-point drift and coupon stacking.
- **Security finding.** A payment webhook open to replayed requests, with a timing leak and personal data in logs.
- **Feature.** Deadlock-free stock reservation across three fulfilment centres with all-or-nothing rollback.

Every patch is judged by a deterministic sandbox: 4 unit checks, 4 adversarial checks and 2 static code checks, 10 per incident. A run counts as a verified outcome only if the patch passes all 10.

Four arms, each run 5 times on each incident (15 runs per arm):

| Arm | Context | Instructions | Models | Sandbox check with one retry |
|---|---|---|---|---|
| 1. Shared bus, original | One growing thread carrying the repo manual plus unrelated services and telemetry; nothing cached | "Exhaustive commentary" prompts | Sonnet on every turn | No; the patch is scored once |
| 2. Shared bus, matched | Same shared thread | The same concise role prompts as arms 3 and 4 | Sonnet on every turn | Yes |
| 3. Isolated and cached | A fresh, narrow thread per agent; a 9.3k-token repo guide cached and shared | Concise role prompts | Sonnet on every turn | Yes |
| 4. Tiered | As arm 3 | Concise role prompts | Haiku for four roles, Sonnet for the patch author | Yes |

Rules of the rerun: no output was cut off in any of the 300 model calls, every run was kept whether it passed or failed, and every cached run started from a cold cache.

### Results

| Arm | Cost per 1,000 runs (cold start) | Warm cache | vs arm 1 (cold) | Prompt tokens per run | Output tokens per run | Model time per run |
|---|---:|---:|---:|---:|---:|---:|
| 1. Shared bus, original | $696 | $696 | — | 246.6k | 20.3k | 155 s |
| 2. Shared bus, matched | $469 | $469 | −33% | 214.1k | 4.1k | 31 s |
| 3. Isolated and cached | $100 | $77.50 | −86% | 56.5k | 5.3k | 39 s |
| 4. Tiered | $56.20 | $32.71 | −92% | 56.8k | 5.4k | 28 s |

| Arm | Verified fixes | Sandbox checks passed | Retries triggered | Cost per verified fix (cold) | Cost per verified fix (warm) |
|---|---:|---:|---:|---:|---:|
| 1. Shared bus, original | 15 of 15 | 150 of 150 | n/a | $0.70 | $0.70 |
| 2. Shared bus, matched | 15 of 15 | 150 of 150 | 0 | $0.47 | $0.47 |
| 3. Isolated and cached | 15 of 15 | 150 of 150 | 0 | $0.10 | $0.078 |
| 4. Tiered | 15 of 15 | 150 of 150 | 0 | $0.056 | $0.033 |

What each step saved, in order:

| Step | Cold | Warm | What changed |
|---|---:|---:|---|
| Concise role instructions (arm 1 → 2) | −33% | −33% | Output fell from 20.3k to 4.1k tokens; model time fell from 155 s to 31 s |
| Isolation and prefix caching (arm 2 → 3) | −79% | −83% | Full-price prompt tokens fell from 214k to about 10k per run |
| Model tiering (arm 3 → 4) | −44% | −58% | Four of five turns moved to Haiku |

**One scoring correction.** As first recorded, arm 1 scored 12 of 15. All three misses were the same static check on the security incident, and all three were false alarms: the patches passed every unit and adversarial test and compared signatures in constant time. The check had flagged a line comparing the public `sha256=` header prefix, because the constant holding it was named `_SIG_PREFIX`. The check was fixed and all stored patches re-scored, which is the table above. On the uncorrected score, arm 1 costs $0.87 per verified fix.

### Deck claims against the data

| Claim | Measured | Verdict |
|---|---|---|
| Input 100k–1M+ tokens per run | Shared bus 213k–258k; isolated about 56k | Partly |
| Output 10k–50k+ tokens per run | Arm 1: 12.0k–25.7k; all other arms 3.9k–6.6k | Partly |
| 1.5M–10M+ tokens per developer per day | Not measurable from single runs | Not testable |
| Isolate contexts, cache the prefix, measure cost per verified outcome | Cost per verified fix fell from $0.70 to $0.056; the share of fixes verified did not change | Partly |

### How the first version went wrong

The first run of this experiment reported the shared-bus swarm verifying 1 fix in 3 at $1.87 per verified fix, against 3 in 3 for the governed swarms: a 64-fold gap. Four things produced that gap, and none of them was context pollution:

- **Truncation.** Shared-bus agents were capped at 3,200 output tokens and told to be exhaustive. Eleven of fifteen turns hit the cap, and both failed patches were simply cut off mid-file.
- **Discarded failures.** The capture script threw away any governed run that failed the sandbox and tried again, while keeping failed shared-bus runs. The governed swarms' perfect score was guaranteed.
- **Unequal instructions.** The governed patch author was told the specific rules the static checks enforce. The shared-bus patch author was not.
- **A faulty check.** The false alarm described above.

### Points worth making in the post

- **The cost lever is real and large.** Twelve times cheaper per verified fix from a cold start, twenty-one times with a warm cache.
- **The quality lever did not show up.** With equal output room and every run counted, all four arms fixed all three incidents every time. On tasks this size, a bloated shared context wasted money but did not produce wrong code.
- **Isolation plus caching is the biggest single step.** The shared bus re-sends about 43k tokens of manual and noise on every turn at full price. Isolated agents send about 2k fresh tokens each and read the rest from cache at a 95% discount.
- **Asking for "exhaustive" output is expensive and buys nothing.** It produced five times the output and took five times as long, for the same result.
- **Tiering pays more when the cache is warm.** A cold tiered run writes the cached prefix twice, once per model. That is why tiering saves 44% cold and 58% warm.
- **When everything passes, cost per verified outcome is just cost per run.** The metric earns its keep only when failure rates differ. Here its real contribution was different: computing it without discarding any run is what exposed the flaws in the first version.
- **Verification needs verifying.** A static check that fails safe code is as misleading as a test that passes broken code.
- **The retry never fired.** In 45 gated runs the first patch always passed, so the check-and-retry loop cost nothing and its benefit is unmeasured.
- **The daily-volume claim in context.** One arm-1 run moves about 267k tokens, so the deck's 1.5M–10M per developer per day equals roughly 6–37 such runs. For the isolated swarms it would take roughly 25–160.

### Caveats

- **Ceiling effect.** Every arm scored 100%, so this experiment cannot detect a difference in correctness. Fifteen out of fifteen still leaves a 95% interval of 80–100%.
- **The tasks are small, and harder ones might perform differently.** Each is a fix to one small module, made in five turns. Harder, multi-file work over more turns is where context pollution would be expected to matter. It was not tested, so the finding that the versions are equally correct should not be carried over to harder tasks.
- **Arm 1 differs from arm 2 in two ways:** the instructions, and the absence of the check-and-retry loop. Since the retry never fired, the 33% is attributable to the instructions.
- **The scoring check was changed after seeing the results.** Both scores are reported; the correction was verified against deliberately unsafe code, which still fails.
- **Cost figures here start every run cold.** A fleet sharing one cached prefix would sit between the cold and warm columns.
- The per-developer daily volume cannot be checked from single runs.

Full results: `analysis/cat6_fair_rerun.md`. Raw records, with every prompt and response: `backend/experiments/cat6_fair_rerun/runs.jsonl`.

---

## Appendix

### Rate card used

US dollars per million tokens.

| Model | Input | Output | Cache write | Cache read |
|---|---:|---:|---:|---:|
| Claude Sonnet 5.5 | 2.00 | 10.00 | 2.50 | 0.10 |
| Claude Haiku 5.5 (prompts up to 100k tokens) | 0.10 | 0.50 | 0.125 | 0.01 |
| Gemini Decision 1 | 0.10 | 0 | — | — |

- Cache write is assumed at 1.25× input. Cache read is a 95% discount on Sonnet and 90% on Haiku.
- The Batch API is priced at 50% off.
- No recorded Haiku call exceeded 100k prompt tokens, so the higher long-prompt rate never applied.
- The Gemini Decision 1 rate was not checked against a published price.

### Terms

- **Rung.** One way of running an archetype's workload. Rungs run on the same inputs, ordered from naive to most governed.
- **Golden replay.** A recorded live API run that the lab app plays back at no cost. These are the canonical runs.
- **Billed, cold, warm.** The three cost views defined at the top of this file.
- **Cost per verified outcome (CpO).** Total spend divided by the number of runs that passed verification. Undefined when nothing passed.
- **Tool precision.** The share of an agent's tool calls that fetched evidence it needed.
- **Rerank recall.** The share of needed clauses that survived retrieval and reranking.
- **Recall question.** A short question, asked after a session's last scripted turn, about one detail the user stated once earlier. It tests what the assistant still remembers.

### Where the data lives

- Full validation report: `analysis/deck_claims_validation.md` (and `.json` for raw values).
- Script that produces it: `backend/scripts/validate_deck_claims.py`.
- Recorded runs: `backend/replays/cat{1..6}_golden_replays.json`.
- Trace files: `backend/traces/` (1,074 files, 244 distinct canonical runs).
- Archetype 1 ablation: `analysis/cat1_ablation.md`, with raw records in `backend/experiments/cat1_ablation/`.
- Archetype 5 ablation: `analysis/cat5_ablation.md`, with raw records in `backend/experiments/cat5_ablation/`.
- Archetype 4 rerun: `analysis/cat4_quality_rerun.md`, with raw records in `backend/experiments/cat4_quality/`.
- Archetype 2 quality scoring: `analysis/cat2_quality.md`, with grader records in `backend/experiments/cat2_quality/judgements.jsonl`.
- Archetype 3 rerun: `analysis/cat3_quality_rerun.md`, with raw records in `backend/experiments/cat3_quality/runs.jsonl`.
- Archetype 6 rerun: `analysis/cat6_fair_rerun.md`, with raw records in `backend/experiments/cat6_fair_rerun/runs.jsonl`.
- The deck: `6 Key Production AI Archerypes.pdf`, one folder above the project.
