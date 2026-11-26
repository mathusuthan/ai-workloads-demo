# Six AI Workload Archetypes: experiment notes for the post series

Source material for seven posts: one introduction and one post per archetype. Part 0 feeds the introduction; Parts 1–6 each feed one archetype post; the appendix holds the rate card and definitions.

Each archetype part has the same shape: the anti-pattern, the suggested path, what was built, the runs, the deck's claims against the data, points for the post, and limits. The tables are written to be charted directly: one row per design, model and condition, and one number per cell.

Runs made on the way to these results (other levers, and earlier designs that were replaced) are in `analysis/experiments_log.md`, not here.

## How to read the numbers

- **The deck.** "Six Key AI Archetypes for AI Workloads" is a 9-slide guide by Eric Lam. It sorts enterprise AI work into six archetypes, gives each a typical token profile, and names one architectural improvement per archetype.
- **The lab.** Each archetype was built as a workload at NovaMart, a fictional Indian omnichannel retailer (12M SKUs, 45,000 sellers, $2.4B GMV). All data is synthetic. Every run is a live call to the model APIs, recorded in full.
- **Without and with.** Each archetype is run as one design, without and with the improvement the deck suggests. "Without" is the anti-pattern; "with" is the suggested path.
- **Models.** Claude Sonnet 5.5 and Claude Haiku 5.5. Where a design was run on both, model is a column.
- **What is being compared.** System designs: what is asked for, how much context is sent, caching, tools, and which size of model does which step. These are not assessments of any model. Where a row names a model, read it as that configuration in this setup, on these tasks.
- **Cost.** Recomputed from recorded token counts at the rate card in the appendix, and quoted per 1,000 units of work (items, documents, sessions, questions, invoices, runs).
- **Cold and warm.** Where caching is involved there are two cost columns. *Cold*: the run writes the cache itself, as a single user starting from nothing. *Warm*: the cached prefix already exists, as in a busy fleet. Where nothing is cached the two are equal.
- **Sample sizes are small.** 12 items, 4 documents, 2 sessions, 8 questions, 12 invoices and 3 incidents, each run 3 times per configuration (incidents 5 times). Quote the results as observations from one lab, not as benchmarks.

---

## Part 0: Material for the introduction post

### The deck's argument

Treating every AI initiative like a chatbot breaks unit economics. Workloads differ in two ways: how much autonomy the system has, and how many tokens it moves. The deck plots six archetypes on those two axes.

| # | Archetype | Autonomy tier | Deck's token profile | Deck's improvement |
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

### The anti-pattern and the suggested path, per archetype

| # | Anti-pattern (without) | Suggested path (with) |
|---|---|---|
| 1 | A free-text analyst write-up for every item | Only the needed fields, in a strict JSON schema, on the small model |
| 2 | An unbounded long-form draft | A four-section template with length caps |
| 3 | The whole transcript and handbook re-sent at full price every turn | Cached handbook prefix, older turns replaced by a running summary |
| 4 | The whole document set pasted into every question | Small model picks five clauses from the cached corpus; large model answers from them with citations |
| 5 | A free loop over raw tables, the model does the policy arithmetic | Four-step budget, a deterministic policy tool, Haiku first with Sonnet on escalation |
| 6 | Every agent on one shared, growing thread | Isolated agent threads, cached repository guide, cost per verified fix |

### Headline results

One row per archetype, design and model.

| # | Unit of work | Design | Model or condition | Cost per 1,000 units, cold ($) | Cost per 1,000 units, warm ($) | Quality measure | Score | Out of |
|---|---|---|---|---:|---:|---|---:|---:|
| 1 | Items | Without | Sonnet 5.5 | 29.50 | 29.50 | Fields correct | 69 | 126 |
| 1 | Items | With | Sonnet 5.5 | 3.77 | 3.77 | Fields correct | 126 | 126 |
| 1 | Items | Without | Haiku 5.5 | 1.25 | 1.25 | Fields correct | 69 | 126 |
| 1 | Items | With | Haiku 5.5 | 0.188 | 0.188 | Fields correct | 120 | 126 |
| 2 | Documents | Without | Sonnet 5.5 | 57.43 | 57.43 | Supporting facts stated | 120 | 120 |
| 2 | Documents | With | Sonnet 5.5 | 26.82 | 26.82 | Supporting facts stated | 94 | 120 |
| 2 | Documents | Without | Haiku 5.5 | 3.11 | 3.11 | Supporting facts stated | 119 | 120 |
| 2 | Documents | With | Haiku 5.5 | 1.36 | 1.36 | Supporting facts stated | 92 | 120 |
| 3 | Ten-turn sessions | Without | Sonnet 5.5 | 398.68 | 398.68 | Recall questions answered | 36 | 36 |
| 3 | Ten-turn sessions | With | Sonnet 5.5 | 212.45 | 188.78 | Recall questions answered | 2 | 36 |
| 4 | Questions | Without | Sonnet 5.5, 7 documents | 45.93 | 45.93 | Answers with no serious error | 23 | 24 |
| 4 | Questions | With | Haiku picks, Sonnet answers, 7 documents | 22.98 | 22.68 | Answers with no serious error | 24 | 24 |
| 4 | Questions | Without | Sonnet 5.5, 21 documents | 117.28 | 117.28 | Answers with no serious error | 21 | 24 |
| 4 | Questions | With | Haiku picks, Sonnet answers, 21 documents | 24.97 | 24.06 | Answers with no serious error | 22 | 24 |
| 5 | Invoices | Without | Sonnet 5.5 | 153.41 | 153.41 | Exact vouchers | 36 | 36 |
| 5 | Invoices | With | Sonnet 5.5 | 51.22 | 30.49 | Exact vouchers | 36 | 36 |
| 5 | Invoices | With | Haiku 5.5 first, Sonnet on escalation | 10.42 | 5.94 | Exact vouchers | 36 | 36 |
| 6 | Incident runs | Without | Sonnet 5.5 on every turn | 469.02 | 469.02 | Verified fixes | 15 | 15 |
| 6 | Incident runs | With | Sonnet 5.5 on every turn | 99.91 | 77.50 | Verified fixes | 15 | 15 |
| 6 | Incident runs | With | Haiku 5.5 agents, Sonnet patch author | 56.20 | 32.71 | Verified fixes | 15 | 15 |

**Cost change from without to with, same model**

| # | Archetype | Model or condition | Cost change, cold (%) | Cost change, warm (%) |
|---|---|---|---:|---:|
| 1 | Classification | Sonnet 5.5 | −87.2 | −87.2 |
| 1 | Classification | Haiku 5.5 | −84.9 | −84.9 |
| 2 | Drafting | Sonnet 5.5 | −53.3 | −53.3 |
| 2 | Drafting | Haiku 5.5 | −56.3 | −56.3 |
| 3 | Assistants | Sonnet 5.5 | −46.7 | −52.6 |
| 4 | Document Q&A | 7 documents | −50.0 | −50.6 |
| 4 | Document Q&A | 21 documents | −78.7 | −79.5 |
| 5 | Orchestration | Sonnet 5.5 | −66.6 | −80.1 |
| 6 | Swarms | Sonnet 5.5 on every turn | −78.7 | −83.5 |

**Cost change from the larger to the smaller model, on the "with" design**

| # | Archetype | From | To | Cost change, cold (%) | Quality on the larger-model configuration | Quality on the smaller-model configuration |
|---|---|---|---|---:|---|---|
| 1 | Classification | Sonnet 5.5 | Haiku 5.5 | −95.0 | 126 of 126 fields | 120 of 126 fields |
| 2 | Drafting | Sonnet 5.5 | Haiku 5.5 | −94.9 | Accuracy 4.17; 0 serious errors in 12 drafts | Accuracy 3.83; 3 serious errors in 12 drafts |
| 5 | Orchestration | Sonnet 5.5 | Haiku 5.5 first | −79.7 | 36 of 36 vouchers | 36 of 36 vouchers |
| 6 | Swarms | Sonnet 5.5 on every turn | Haiku 5.5 agents, Sonnet patch author | −43.7 | 15 of 15 fixes | 15 of 15 fixes |

### The scorecard

The scorecard has 32 rows: the deck's 26 testable claims plus six we added, that the improvement loses no quality in each archetype.

| Group | Rows | Supported | Partly supported | Not supported | Not testable |
|---|---:|---:|---:|---:|---:|
| Archetype 1 | 5 | 1 | 4 | 0 | 0 |
| Archetype 2 | 6 | 3 | 2 | 1 | 0 |
| Rule for archetypes 1 and 2 | 1 | 0 | 1 | 0 | 0 |
| Archetype 3 | 5 | 1 | 3 | 1 | 0 |
| Archetype 4 | 5 | 3 | 2 | 0 | 0 |
| Archetype 5 | 4 | 1 | 3 | 0 | 0 |
| Archetype 6 | 5 | 0 | 3 | 1 | 1 |
| Ordering of the archetypes by token scale | 1 | 0 | 1 | 0 | 0 |
| Total | 32 | 9 | 19 | 3 | 1 |

- **Supported:** the measurement falls inside the claimed range or clears the threshold.
- **Partly supported:** the direction holds, but the magnitude is outside the range, a ceiling prevents a difference from showing, or a point estimate is lower.
- **Not supported:** the data contradicts the row. The three are our added quality rows for Archetypes 2 and 3 (supporting detail; recall of earlier turns) and the deck's output-token band for Archetype 6 (0 of 45 runs inside it).
- **Not testable:** the per-developer daily token volume for swarms.

All six of the deck's improvement rows are supported or partly supported. Each archetype's claims table is in its part below.

### Findings that cut across archetypes

- **Every "with" design cost less than its "without".** On the same model the change ranged from −47% (Archetype 3) to −87% (Archetype 1).
- **The deck's "60–80%" rule for Archetypes 1 and 2.** Measured on the same model: −85% and −87% for Archetype 1, −53% and −56% for Archetype 2. With the change of model as well, Archetype 1 reached −99.4%.
- **Where the task has a checkable right answer, the "with" design scored the same or higher.** Archetype 1: 126 and 120 fields of 126 against 69. Archetype 5: 36 of 36 vouchers in every configuration. Archetype 6: 15 of 15 fixes in every configuration.
- **In three archetypes a quality measure was lower with the improvement.** Archetype 2: supporting facts 94 of 120 against 120. Archetype 3: recall of earlier details 2 of 36 against 36. Archetype 4: completeness graded 4.54 against 4.83 and 4.75.
- **In two of those, another measure was higher.** Archetype 2: accuracy grades, and 0 and 3 serious errors against 5 and 22. Archetype 4: correctness 4.75 and 4.54 against 4.50.
- **A smaller model on the same design** cost 44% to 95% less. Scores were equal in Archetypes 5 and 6, six fields of 126 lower in Archetype 1, and lower on accuracy grade in Archetype 2.
- **Two archetypes hit a ceiling.** In Archetypes 5 and 6 every configuration scored 100%, so these tasks cannot show a quality difference. Harder tasks might.
- **The deck's token bands describe context size, not the bill.** A ten-turn session peaked at 22,626 tokens of context and billed 163,020 prompt tokens, because every turn re-sends the history.
- **Output dominates the cost of the cheap archetypes and input the cost of the expensive ones** (table below).

**Where the cost sits, "without" design on Sonnet 5.5**

| # | Archetype | Input share of cost (%) | Output share of cost (%) |
|---|---|---:|---:|
| 1 | Classification | 5 | 95 |
| 2 | Drafting | 13 | 87 |
| 3 | Assistants | 82 | 18 |
| 4 | Document Q&A, 7 documents | 81 | 19 |
| 5 | Orchestration | 89 | 11 |
| 6 | Swarms | 91 | 9 |

### Measured token scale

Total tokens per unit of work.

| # | Unit | Configuration | Tokens |
|---|---|---|---:|
| 1 | One item | With, schema classification | 1,500 |
| 2 | One document | Without, unbounded draft | 8,500 |
| 4 | One question, 7 documents | Without | 19,400 |
| 4 | One question, 21 documents | Without | 55,100 |
| 5 | One invoice | Without | 75,900 |
| 4 | One four-question audit, 7 documents | Without | 77,500 |
| 3 | One ten-turn session | Without | 169,600 |
| 6 | One incident run | Without | 217,800 |

The deck orders the archetypes 1 < 2 < 3 < 4 < 5 << 6. Measured, 1 < 2 < {3, 4, 5} < 6 holds; the order of 3, 4 and 5 depends on the unit, because a ten-turn session moves more tokens than one question or one invoice.

### Limits to state in the intro

- Samples are small: three runs per configuration, five for Archetype 6.
- Archetypes 2 and 4 are graded by one model acting as a blind grader, in one pass, with its serious findings checked against the sources.
- Each "with" design changes several things at once, so its saving cannot be split between them from these runs.
- Not every design was run on both models: the "without" designs of Archetypes 5 and 6 and both designs of Archetypes 3 and 4 were run with Sonnet as the main model only.
- All data is synthetic and the corpus sizes are at the low end of the deck's bands.

---

## Part 1: Classification, extraction and routing

**One-line result:** asking for a schema-bound classification in place of a free-text write-up cut cost by 87% on Sonnet and 85% on Haiku. Running it on Haiku cost 95% less again. On the same classification task the Haiku configuration matched 120 of 126 fields and the Sonnet configuration 126.

### The anti-pattern

A triage step that asks a large model for a free-text analyst write-up of every item. The answer runs to thousands of output tokens, takes many seconds, and the downstream system still has to work out which queue, priority or category the write-up means.

### The suggested path

The deck's improvement: route to small models with strict JSON schema output, and batch.

- The request asks only for the fields the system needs, each chosen from a fixed list.
- A strict JSON schema guarantees that every answer parses.
- The work runs on the small model.
- The Batch API halves the price where an answer is not needed immediately. Batch prices here are computed from the published discount; no batch job was run.

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

Four configurations, each run three times on every item: 144 runs.

| Design | Model | What is asked for | Answer format |
|---|---|---|---|
| Without | Sonnet 5.5 | A four-part analyst write-up: summary, routing with reasoning, a personal-data audit, next steps | Free text |
| With | Sonnet 5.5 | Only the fields, chosen from the allowed values | Strict JSON schema |
| Without | Haiku 5.5 | The same write-up | Free text |
| With | Haiku 5.5 | Only the fields | Strict JSON schema |

Scoring: schema answers are compared with the right answer field by field. Write-ups are first read by a separate model (Opus 5.5), which records what the write-up says for each field without being shown the right answer or which configuration wrote it; those fields are then compared the same way.

### The runs

**Per configuration** (36 runs and 126 fields each)

| Design | Model | Fields correct (of 126) | Items fully correct (of 36) | Cost per 1,000 items ($) | Prompt tokens (median) | Output tokens (median) | Response time (median, s) |
|---|---|---:|---:|---:|---:|---:|---:|
| Without | Sonnet 5.5 | 69 | 6 | 29.50 | 790 | 2,739 | 22.1 |
| With | Sonnet 5.5 | 126 | 36 | 3.77 | 1,388 | 96 | 2.0 |
| Without | Haiku 5.5 | 69 | 3 | 1.25 | 790 | 2,283 | 11.2 |
| With | Haiku 5.5 | 120 | 33 | 0.188 | 1,388 | 98 | 1.4 |

A write-up's "fields correct" counts the fields where one allowed value could be read off the write-up and was right. The write-up prompt does not list the allowed values. In 44 of 126 fields per model the write-up addressed the question without committing to a single allowed value, for example "Status: HOLD / DO NOT PUBLISH. Route to Compliance Audit."

**Cost change between cells**

| Step | Model | From ($ per 1,000) | To ($ per 1,000) | Cost change (%) |
|---|---|---:|---:|---:|
| Write-up to schema classification | Sonnet 5.5 | 29.50 | 3.77 | −87.2 |
| Write-up to schema classification | Haiku 5.5 | 1.25 | 0.188 | −84.9 |
| Sonnet to Haiku, write-up | Both | 29.50 | 1.25 | −95.8 |
| Sonnet to Haiku, schema classification | Both | 3.77 | 0.188 | −95.0 |
| Sonnet write-up to Haiku schema classification | Both | 29.50 | 0.188 | −99.4 |

**With the Batch API** (computed at the published 50% discount; no batch job was run)

| Design | Model | Cost per 1,000 items ($) | Cost per 1,000 items with Batch API ($) |
|---|---|---:|---:|
| With | Sonnet 5.5 | 3.77 | 1.88 |
| With | Haiku 5.5 | 0.188 | 0.094 |

**By task** (18 runs per row)

| Design | Model | Task | Fields correct | Fields (out of) | Items fully correct (of 18) | Cost per 1,000 items ($) | Output tokens (median) |
|---|---|---|---:|---:|---:|---:|---:|
| Without | Sonnet 5.5 | Support triage | 30 | 72 | 0 | 30.00 | 2,739 |
| Without | Sonnet 5.5 | SKU tagging | 39 | 54 | 6 | 28.99 | 2,602 |
| With | Sonnet 5.5 | Support triage | 72 | 72 | 18 | 3.76 | 92 |
| With | Sonnet 5.5 | SKU tagging | 54 | 54 | 18 | 3.77 | 100 |
| Without | Haiku 5.5 | Support triage | 37 | 72 | 0 | 1.16 | 2,166 |
| Without | Haiku 5.5 | SKU tagging | 32 | 54 | 3 | 1.33 | 2,283 |
| With | Haiku 5.5 | Support triage | 66 | 72 | 15 | 0.188 | 92 |
| With | Haiku 5.5 | SKU tagging | 54 | 54 | 18 | 0.189 | 102 |

**By field** (correct of 18 runs)

| Design | Model | Queue | Priority | Automatic action | Personal data present | Category | Compliance status | Contradiction detected |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Without | Sonnet 5.5 | 12 | 3 | 0 | 15 | 15 | 9 | 15 |
| With | Sonnet 5.5 | 18 | 18 | 18 | 18 | 18 | 18 | 18 |
| Without | Haiku 5.5 | 12 | 7 | 0 | 18 | 14 | 6 | 12 |
| With | Haiku 5.5 | 17 | 16 | 15 | 18 | 18 | 18 | 18 |

**Scale illustration.** NovaMart's story has 5 million items a week. Extrapolating from these runs:

| Design | Model | Cost per week at 5 million items ($) |
|---|---|---:|
| Without | Sonnet 5.5 | 147,500 |
| With | Sonnet 5.5 | 18,850 |
| Without | Haiku 5.5 | 6,250 |
| With | Haiku 5.5 | 940 |
| With, Batch API (computed) | Haiku 5.5 | 470 |

### Deck claims against the data

| Claim | Measured | Verdict |
|---|---|---|
| Input 500–1,500 tokens | Schema prompt 859–2,066 (median 1,388); write-up prompt 261–1,468 (median 790) | Partly |
| Output 10–100 tokens | 71–125 with the schema (medians 96 and 98) | Partly |
| Input:output of 20:1 to 50:1 | 13:1 with the schema | Partly |
| Small model + strict JSON schema + batching cuts unit cost by more than 80% | −99.4% from the Sonnet write-up to the Haiku schema classification; −87.2% and −84.9% from write-up to schema on the same model; −95.0% from Sonnet to Haiku with the schema. Batching was priced, not run | Supported |
| …without losing accuracy (our addition; the deck does not claim it) | With against without on the same model: 126 against 69, and 120 against 69, fields of 126. With the schema, Haiku against Sonnet: 120 against 126 | Partly |

### Points for the post

- **Cost.** $29.50 per 1,000 items for a Sonnet write-up; $3.77 for a Sonnet schema classification; $0.188 for a Haiku schema classification.
- **Output is the bill in a write-up.** A write-up produced 2,283 to 2,739 output tokens from a 790-token prompt. A schema classification produced about 97 from a 1,388-token prompt, so the schema adds prompt tokens and removes output tokens.
- **The answer becomes usable.** Schema answers gave an allowed value on every field. Write-ups left 44 of 126 fields without a single allowed value, and no write-up named an automatic action from the allowed list (0 of 18 on both models).
- **Model size, on the same task.** With the schema, Haiku cost 95% less than Sonnet and matched 120 of 126 fields against 126. All six fields that did not match were on two of the twelve items: a seller settlement dispute and a damaged-goods ticket.
- **Speed follows output.** A write-up took 22.1 s on Sonnet and 11.2 s on Haiku; a schema classification took 2.0 s and 1.4 s.
- **The two designs do different jobs.** The "without" design is asked for a write-up and the "with" design for fields, so the comparison measures both the smaller request and the schema together.
- **Batch.** The Batch API would halve the "with" costs to $1.88 and $0.094 per 1,000 items. That price is computed, not run.

### Limits

- Twelve items, three runs each, with the right answer defined on 42 fields. The gap between the Haiku and Sonnet schema configurations is six fields on two items.
- The write-ups were read by a single model in one pass.
- The write-up prompt does not list the allowed values, so a write-up's score measures how usable it is as a classification.
- Batch pricing is computed from the published discount; no batch job was run.
- Sonnet and Haiku ran with different thinking settings, as the app configures them.

Full results: `analysis/cat1_ablation.md`. Records: `backend/experiments/cat1_ablation/runs.jsonl` and `extractions.jsonl`. Other levers tried (classification as plain text without a schema; a decision model): `analysis/experiments_log.md`.

---

## Part 2: Generative synthesis and drafting

**One-line result:** a section template with length caps cut the cost of a draft by 53% on Sonnet and 56% on Haiku. Templated drafts were graded higher on accuracy and had fewer serious errors; they carried fewer supporting details (94 and 92 of 120, against 120 and 119). Head to head, the blind grader preferred the unbounded draft in 18 of 24 comparisons on Sonnet and the templated draft in 15 of 24 on Haiku.

### The anti-pattern

An open-ended request for a long-form report. Nothing bounds the output, and output tokens cost five times as much as input tokens, so the length of the draft sets the bill.

### The suggested path

The deck's improvement: structured section templates and length bounds.

- The draft is a four-section JSON document: a summary, three findings, three risks and three actions, each with a word cap.
- Each action has an owner field and a time-window field. The template says to fill them only if the source states them, and otherwise to write exactly "Not stated in source".
- A reviewer can lock a section, edit it by hand, or regenerate one section without redrafting the rest.

### What the deck says

- **Shape:** long-form content creation where dense output dominates the economics.
- **Profile:** 1,500–4,000 tokens in, 800–3,000+ out, ratio around 1:1 to 1:2.
- **Lever:** because output tokens cost 3–5× input tokens, enforce structured section templates and length bounds.
- **Use cases:** collateral drafting, transcript synthesis, regulatory reporting.

### What was built

The NovaMart Executive and Compliance Readout Studio, tested on 4 documents:

- **Executive synthesis.** `brief-01`, a 45-minute Diwali peak operations war-room transcript; `brief-02`, a brand partnership proposal brief.
- **Regulatory filing.** `reg-01`, a lithium-ion thermal event safety filing; `reg-02`, a cross-border seller KYC and anti-money-laundering audit report.

Four configurations, each drafting every document three times: 48 drafts.

- **Without, on Sonnet 5.5 and on Haiku 5.5.** An unbounded long-form report, output limit 8,000 tokens.
- **With, on Sonnet 5.5 and on Haiku 5.5.** The section template, output limit 3,000 tokens.

No draft was cut off at its limit.

Quality was measured three ways:

- **Fact checklist.** 18 facts per source document, written from the source alone: 8 core (what a decision-maker cannot act without) and 10 supporting. Scored by matching. Over 12 drafts that is 96 core and 120 supporting facts per configuration.
- **Blind grading.** A model not under test (Opus 5.5) graded each draft once on five dimensions, 1 to 5, and listed every factual error with quotes from the draft and the source. It was not told which model or design wrote the draft.
- **Head to head.** For each document, model and repeat, the grader was shown the templated draft and the unbounded draft, in both orders, and asked which should be sent as is: 48 comparisons.

### The runs

**Cost and tokens, per configuration** (12 drafts each)

| Design | Model | Cost per 1,000 documents ($) | Prompt tokens (median) | Output tokens (mean) | Output share of cost (%) |
|---|---|---:|---:|---:|---:|
| Without | Sonnet 5.5 | 57.43 | 3,640 | 5,012 | 87 |
| With | Sonnet 5.5 | 26.82 | 4,924 | 1,694 | 63 |
| Without | Haiku 5.5 | 3.11 | 3,640 | 5,487 | 88 |
| With | Haiku 5.5 | 1.36 | 4,924 | 1,723 | 64 |

Change from without to with: −53.3% on Sonnet, −56.3% on Haiku. From Sonnet to Haiku on the same design: −94.6% without, −94.9% with.

**Grades** (mean of 12 drafts, 1 to 5)

| Design | Model | Accuracy | Coverage | Clarity | Actionability | Concision |
|---|---|---:|---:|---:|---:|---:|
| Without | Sonnet 5.5 | 3.92 | 5.00 | 3.83 | 3.42 | 2.75 |
| With | Sonnet 5.5 | 4.17 | 3.42 | 4.17 | 3.08 | 4.00 |
| Without | Haiku 5.5 | 2.92 | 4.33 | 3.42 | 3.42 | 2.58 |
| With | Haiku 5.5 | 3.83 | 3.58 | 4.08 | 2.67 | 4.08 |

**Facts and errors**

| Design | Model | Core facts stated (of 96) | Supporting facts stated (of 120) | Serious errors (12 drafts) | Serious errors per draft | Minor errors per draft | Numbers not in the source |
|---|---|---:|---:|---:|---:|---:|---:|
| Without | Sonnet 5.5 | 95 | 120 | 5 | 0.42 | 3.58 | 120 |
| With | Sonnet 5.5 | 94 | 94 | 0 | 0.00 | 1.92 | 2 |
| Without | Haiku 5.5 | 94 | 119 | 22 | 1.83 | 6.83 | 81 |
| With | Haiku 5.5 | 92 | 92 | 3 | 0.25 | 2.58 | 9 |

"Numbers not in the source" counts every number in a draft that does not appear in the source, including totals and percentages the draft worked out.

**Head to head: which draft should be sent as is** (24 comparisons per model)

| Model | Templated draft preferred | Unbounded draft preferred | Ties |
|---|---:|---:|---:|
| Sonnet 5.5 | 6 | 18 | 0 |
| Haiku 5.5 | 15 | 9 | 0 |

**Head to head by dimension** (48 comparisons, both models)

| Dimension | Templated draft preferred | Unbounded draft preferred | Ties |
|---|---:|---:|---:|
| Overall | 21 | 27 | 0 |
| Accuracy | 25 | 18 | 5 |
| Usefulness to the reader | 9 | 39 | 0 |

**Owner and time-window fields in the templated drafts** (36 action items per model)

| Model | Field | Value found in the source | Written as "Not stated in source" | Value not in the source |
|---|---|---:|---:|---:|
| Sonnet 5.5 | Owner | 8 | 28 | 0 |
| Sonnet 5.5 | Time window | 21 | 15 | 0 |
| Haiku 5.5 | Owner | 0 | 36 | 0 |
| Haiku 5.5 | Time window | 22 | 14 | 0 |

**By document** (three drafts per row)

| Document | Design | Model | Accuracy | Coverage | Serious errors per draft |
|---|---|---|---:|---:|---:|
| brief-01 | Without | Sonnet 5.5 | 4.00 | 5.00 | 0.33 |
| brief-01 | With | Sonnet 5.5 | 4.00 | 3.67 | 0.00 |
| brief-01 | Without | Haiku 5.5 | 3.33 | 5.00 | 0.67 |
| brief-01 | With | Haiku 5.5 | 4.00 | 4.00 | 0.00 |
| brief-02 | Without | Sonnet 5.5 | 4.00 | 5.00 | 0.00 |
| brief-02 | With | Sonnet 5.5 | 4.67 | 3.00 | 0.00 |
| brief-02 | Without | Haiku 5.5 | 3.00 | 4.33 | 1.00 |
| brief-02 | With | Haiku 5.5 | 3.67 | 3.33 | 0.33 |
| reg-01 | Without | Sonnet 5.5 | 3.67 | 5.00 | 1.33 |
| reg-01 | With | Sonnet 5.5 | 4.00 | 3.00 | 0.00 |
| reg-01 | Without | Haiku 5.5 | 2.67 | 4.00 | 2.33 |
| reg-01 | With | Haiku 5.5 | 3.67 | 3.00 | 0.67 |
| reg-02 | Without | Sonnet 5.5 | 4.00 | 5.00 | 0.00 |
| reg-02 | With | Sonnet 5.5 | 4.00 | 4.00 | 0.00 |
| reg-02 | Without | Haiku 5.5 | 2.67 | 4.00 | 3.33 |
| reg-02 | With | Haiku 5.5 | 4.00 | 4.00 | 0.00 |

**Regenerating one section of a templated draft** (16 regenerations per model: 4 documents × 4 sections)

| Model | Cost per 1,000 section regenerations ($) | Cost per 1,000 full templated drafts, same documents ($) | Cost change (%) | Regenerations cut off |
|---|---:|---:|---:|---:|
| Sonnet 5.5 | 13.87 | 26.94 | −49 | 0 |
| Haiku 5.5 | 0.732 | 1.38 | −47 | 0 |

**The 30 serious errors, by kind** (grouped by hand from the grader's findings)

| Kind of error | Without, Sonnet 5.5 | With, Sonnet 5.5 | Without, Haiku 5.5 | With, Haiku 5.5 |
|---|---:|---:|---:|---:|
| An owner or a deadline the source does not give | 2 | 0 | 6 | 0 |
| A statement or conclusion the source does not make | 0 | 0 | 4 | 0 |
| A figure, label or relationship read differently from the source | 1 | 0 | 8 | 1 |
| Arithmetic that does not reproduce | 2 | 0 | 4 | 1 |
| "Not stated in source" written where the source names an owner | 0 | 0 | 0 | 1 |
| Total | 5 | 0 | 22 | 3 |

Examples from the unbounded drafts: a roadmap table naming "Fulfillment Operations" and "Customer Care / Recall Ops" as owners where the source attributes every commitment to "Management"; a cost total of $94,020 for four items that sum to $93,980; a milestone "within 60 days" where the source gives no timeline.

### Deck claims against the data

| Claim | Measured | Verdict |
|---|---|---|
| Input 1,500–4,000 tokens | 3,458–3,874 unbounded; 4,748–5,154 with the template | Partly |
| Output 800–3,000+ tokens | 4,370–6,521 unbounded; 1,569–1,892 with the template | Supported |
| Input:output of about 1:1 to 1:2, with output-dominated cost | 0.74:1 and 0.67:1 unbounded, output 87–88% of cost; 2.9:1 with the template, output 63–64% of cost | Partly |
| Output tokens cost 3–5× input | 5× on both models | Supported |
| Section templates and length bounds control output cost | −53% on Sonnet and −56% on Haiku; median output 4,833 to 1,673 and 5,542 to 1,720 tokens | Supported |
| …without losing draft quality (our addition; the deck does not claim it) | Supporting facts 94 of 120 against 120 (Sonnet) and 92 against 119 (Haiku). Accuracy grades were higher and serious errors fewer with the template. Head to head: templated 21, unbounded 27 | Not supported |
| Rule for Archetypes 1 and 2: 60–80% lower unit inference cost | Archetype 1: −85% and −87% on the same model, −99.4% with the change of model. Archetype 2: −53% and −56% | Partly |

### Points for the post

- **Cost.** $57.43 to $26.82 per 1,000 documents on Sonnet; $3.11 to $1.36 on Haiku. Output fell from about 5,000 tokens to about 1,700.
- **Output is the bill.** Output was 87–88% of the cost of an unbounded draft and 63–64% of a templated one.
- **What the template gave up.** Supporting detail: 94 and 92 of 120 supporting facts, against 120 and 119. Coverage grades were 3.42 and 3.58, against 5.00 and 4.33. Core facts were within three of each other in all four configurations.
- **What the template gained.** Accuracy grades (4.17 against 3.92 on Sonnet; 3.83 against 2.92 on Haiku), concision, and fewer serious errors (0 against 5; 3 against 22).
- **Where the errors were.** In the unbounded drafts, the grader's serious findings were mostly things a long draft adds: owners and deadlines for a roadmap, worked totals, conclusions. The templated drafts wrote "Not stated in source" in 64 of 72 owner fields and 29 of 72 time-window fields, and none of their owner or time-window values was absent from the source.
- **Head to head, the result depended on the model.** On Sonnet the unbounded draft was preferred 18 to 6. On Haiku the templated draft was preferred 15 to 9.
- **Accuracy and usefulness pulled in different directions.** Across both models the grader preferred the templated draft on accuracy 25 to 18, and the unbounded draft on usefulness to the reader 39 to 9.
- **Actionability.** Graded 3.08 and 2.67 with the template, against 3.42 and 3.42 without. An action whose owner reads "Not stated in source" is accurate and leaves the reader to assign it.
- **Fixing one section costs about half a redraft.** Regenerating a single section cost 49% less than a full templated draft on Sonnet and 47% less on Haiku.
- **Model size on the same design.** Haiku cost about 95% less than Sonnet in either design. With the template its accuracy grade was 3.83 against 4.17 and it had 3 serious errors in 12 drafts against 0.

### Limits

- Four documents, three drafts per configuration.
- One grading pass per draft by a single model. Each serious error's quotes were checked against the draft and the source; no person graded the drafts.
- The fact checklist uses literal matching, so a correct paraphrase can be missed.
- The grouping of serious errors by kind was done by hand.
- The unbounded request and the template differ in what they ask for as well as in length, so the comparison measures the template as a whole.
- Sonnet and Haiku ran with different thinking settings, as the app configures them.

Full results: `analysis/cat2_quality.md`. Records: `backend/experiments/cat2_not_stated/drafts.jsonl` and `judgements.jsonl`. Earlier template designs: `analysis/experiments_log.md`.

---

## Part 3: Multi-turn conversational assistants

**One-line result:** with a cached prefix and sliding-window summaries, a ten-turn session cost 47% less and its context grew a quarter as fast. Answers to new questions were unchanged. Recall of details from earlier turns was 2 of 36, against 36 of 36 without the improvement.

### The anti-pattern

Every turn re-sends the whole transcript and the whole policy handbook at full price. The context grows on every turn, so the tokens billed over a session grow with the square of its length.

### The suggested path

The deck's improvement: prefix caching plus sliding-window memory summarisation.

- The handbook, which never changes, is sent as a cached prefix.
- Once four turns are held word for word, all but the latest are replaced by a short structured summary (at most 14 items), written by a separate summariser call. This happens before turns 5 and 8. The summariser's cost is included.

### What the deck says

- **Shape:** stateful dialogue where history and retrieved context accumulate on every turn.
- **Profile:** 10,000–40,000+ tokens per session, 150–600 output tokens per turn. The deck's chart shows context of 1.2k, 6.5k, 14k and 25k+ at turns 1, 3, 6 and 10.
- **Lever:** prefix context caching and sliding-window memory summarisation, to prevent quadratic session cost.
- **Use cases:** IT and HR service desk, consumer dialogue, field operations assistant.

### What was built

The NovaMart IT and HR Unified Service Desk: two ten-turn employee sessions, grounded in a 9,860-token policy handbook.

- **Session 1 (`desk-01`).** An employee returning from parental leave: laptop management lockout, VPN certificate, and payroll back-pay.
- **Session 2 (`desk-02`).** A senior engineer's second day: security-key access to production, an expense hold, and a relocation tax gross-up.

Turn 10 of each session asks for a consolidated summary of everything resolved in turns 1–9.

Both designs run on Claude Sonnet 5.5. Each session was run three times per design: 12 sessions in all.

Quality was measured three ways, all by matching against an answer key written from the handbook and the scripted user messages:

- **Answers grounded.** Does each reply in turns 1–9 give the policy, queue, command and figures the handbook prescribes?
- **Details in the final summary.** How many specifics from turns 1–9 appear in the turn-10 summary?
- **Recall questions.** After turn 10, six short questions per session, each about one detail the user stated once in an earlier turn, such as a serial number, an invoice number or a date. Each is asked on its own.

### The runs

**Cost and context, per design**

| Design | Model | Sessions | Cost per 1,000 sessions, cold ($) | Cost per 1,000 sessions, warm ($) | Prompt tokens billed per session | Output tokens per session | Context at turn 10 (tokens) | Context growth per turn (tokens) | Largest context in any turn (tokens) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Without | Sonnet 5.5 | 6 | 398.68 | 398.68 | 163,020 | 7,264 | 21,872 | 1,247 | 22,626 |
| With | Sonnet 5.5 | 6 | 212.45 | 188.78 | 143,138 | 8,992 | 14,824 | 288 | 15,638 |

Change from without to with: cost −46.7% cold, −52.6% warm. The "with" token counts include the summariser calls (10,883 prompt and 1,038 output tokens per session).

**Context and cost, turn by turn** (mean of six sessions)

| Design | Turn | Context (prompt tokens) | Cost of the turn ($) | Output tokens |
|---|---:|---:|---:|---:|
| Without | 1 | 10,617 | 0.0314 | 1,013 |
| Without | 2 | 11,848 | 0.0300 | 634 |
| Without | 3 | 13,169 | 0.0320 | 567 |
| Without | 4 | 14,506 | 0.0344 | 537 |
| Without | 5 | 15,802 | 0.0438 | 1,219 |
| Without | 6 | 17,054 | 0.0388 | 467 |
| Without | 7 | 18,217 | 0.0446 | 815 |
| Without | 8 | 19,366 | 0.0447 | 597 |
| Without | 9 | 20,569 | 0.0469 | 572 |
| Without | 10 | 21,872 | 0.0522 | 842 |
| With | 1 | 10,633 | 0.0399 | 1,369 |
| With | 2 | 11,880 | 0.0107 | 565 |
| With | 3 | 13,200 | 0.0132 | 557 |
| With | 4 | 14,527 | 0.0159 | 560 |
| With | 5 | 12,548 | 0.0334 | 1,149 |
| With | 6 | 13,783 | 0.0141 | 524 |
| With | 7 | 15,003 | 0.0166 | 533 |
| With | 8 | 12,339 | 0.0305 | 797 |
| With | 9 | 13,519 | 0.0140 | 574 |
| With | 10 | 14,824 | 0.0242 | 1,326 |

In the "with" rows, turn 1 includes writing the cache, and turns 5 and 8 include the summariser call that runs before them.

**Quality**

| Design | Measure | Hits | Out of | Rate (%) |
|---|---|---:|---:|---:|
| Without | Answers grounded, turns 1–9 | 205 | 207 | 99.0 |
| With | Answers grounded, turns 1–9 | 205 | 207 | 99.0 |
| Without | Details in final summary, all turns | 106 | 147 | 72.1 |
| With | Details in final summary, all turns | 91 | 147 | 61.9 |
| Without | Details in final summary, from turns 1–3 | 37 | 51 | 72.5 |
| With | Details in final summary, from turns 1–3 | 24 | 51 | 47.1 |
| Without | Details in final summary, from turns 4–6 | 40 | 51 | 78.4 |
| With | Details in final summary, from turns 4–6 | 37 | 51 | 72.5 |
| Without | Details in final summary, from turns 7–9 | 29 | 45 | 64.4 |
| With | Details in final summary, from turns 7–9 | 30 | 45 | 66.7 |
| Without | Recall questions | 36 | 36 | 100.0 |
| With | Recall questions | 2 | 36 | 5.6 |

**Quality by session**

| Design | Session | Recall questions (hits) | Recall questions (out of) | Final-summary details (hits) | Final-summary details (out of) | Cost per 1,000 sessions, cold ($) |
|---|---|---:|---:|---:|---:|---:|
| Without | desk-01 | 18 | 18 | 63 | 75 | 415.86 |
| Without | desk-02 | 18 | 18 | 43 | 72 | 381.51 |
| With | desk-01 | 2 | 18 | 59 | 75 | 215.58 |
| With | desk-02 | 0 | 18 | 32 | 72 | 209.33 |

**What the "with" design answered on the 36 recall questions** (each read by hand)

| Answer | Count |
|---|---:|
| Gave the reference value | 2 |
| Said the detail was not in its session memory and pointed to where to find it | 33 |
| Gave a labelled estimate ($1,780 against $1,775) | 1 |
| Stated a different value as fact | 0 |

The two reference values given were the same detail both times: the laptop serial number, which the summary had kept.

### Deck claims against the data

| Claim | Measured | Verdict |
|---|---|---|
| Context grows 1.2k → 6.5k → 14k → 25k+ at turns 1, 3, 6 and 10 | 10.6k → 13.2k → 17.1k → 21.9k without the improvement | Partly |
| Session of 10k–40k+ tokens | Largest context 22.6k; 163k prompt tokens billed per session | Partly |
| Output 150–600 tokens per turn | Median 586, range 342–3,983; 68 of 120 turns in range | Partly |
| Prefix caching and sliding-window summaries prevent quadratic session cost | Context growth 1,247 tokens per turn without, 288 with; cost −47% | Supported |
| …without losing answer quality (our addition; the deck does not claim it) | Recall questions 2 of 36 against 36 of 36; early details in the final summary 24 of 51 against 37; answers grounded 205 of 207 in both | Not supported |

### Points for the post

- **Cost.** $398.68 to $212.45 per 1,000 ten-turn sessions, and to $188.78 when many sessions share the cached handbook.
- **Context growth.** 1,247 tokens per turn without, 288 with. At turn 10 the context was 21,872 tokens against 14,824.
- **What did not change.** Answers to the question in front of the assistant: 205 of 207 grounded in both designs.
- **What changed.** Exact values from earlier turns. Recall questions went from 36 of 36 to 2 of 36, and details from turns 1–3 in the final summary from 37 of 51 to 24 of 51.
- **The change follows the summarisation boundary.** Details from turns 7–9, still held word for word at turn 10, appear in the final summary about equally often in both designs (29 and 30 of 45).
- **Missing details were reported as missing.** In 33 of the 34 recall answers without the reference value, the reply said the detail was not available; none stated a different value as fact.
- **The first cached turn costs more.** Writing the cache is priced at 1.25× input, so turn 1 was $0.0399 against $0.0314. Turn 2 was $0.0107 against $0.0300.
- **The context band and the bill are different things.** Context peaked at 22,626 tokens, inside the deck's band. Because every turn re-sends what came before, one session without the improvement billed 163,020 prompt tokens.
- **Session length.** Ten turns is early on the growth curve. Longer sessions were not run.

### Limits

- Two scripted sessions, each run three times per design.
- Scoring is literal matching against an answer key, so a correct paraphrase can be missed. Every recall answer without the reference value was read by hand.
- One summary design was run: at most 14 short items. A summary that pins every identifier the user gives was not run.
- The "with" design's system prompt says that older turns are compressed.
- The recall questions come after turn 10, when a third summarisation has run, so all of turns 1–9 are in the summary by then.
- Output per turn ranged from 342 to 3,983 tokens because some calls include thinking tokens, so session cost varied between repeats ($0.37 to $0.43 without the improvement).
- One model. The designs were not run on Haiku 5.5.

Full results: `analysis/cat3_quality_rerun.md`. Records: `backend/experiments/cat3_quality/runs.jsonl`. Answer key: `backend/app/data/cat3_quality_keys.json`. Other levers tried (prefix caching alone): `analysis/experiments_log.md`.

---

## Part 4: Multi-document RAG and deep ingestion

**One-line result:** pairing retrieval with caching cut the cost of a question by 50% on a 7-document corpus and by 79% on a 21-document corpus. Answers with a serious error were 0 and 2 of 24 with the improvement, against 1 and 3 of 24 without it.

### The anti-pattern

Every question pastes the whole document set into the prompt at full price. Cost per question rises with the size of the corpus, and the answer carries no citations for a reviewer to check.

### The suggested path

The deck's improvement: pair hybrid retrieval (reranking and chunk filtering) with context caching on the shared document set.

- The corpus is cached once, on the small model.
- For each question, Haiku 5.5 reads all clauses from the cached corpus and picks five.
- Sonnet 5.5 answers from those five clauses, with the API's native citations.

### What the deck says

- **Shape:** high-context reasoning over large document sets, producing grounded answers.
- **Profile:** 15k–100k+ tokens in, 400–1,500 out, ratio of 20:1 to 100:1.
- **Lever:** pair hybrid retrieval (reranking and chunk filtering) with context caching on shared document repositories.
- **Use cases:** legal due diligence, grounding repositories, financial filing analysis.

### What was built

The NovaMart Supplier Deal-Room: seven contract and compliance documents for one supplier, split into 28 clauses. The documents include a wholesale master agreement, a peak-season service-level addendum, a data-protection schedule, safety and tax riders, a statutory audit extract and a side letter.

Eight due-diligence questions, each needing clauses from several documents: liability caps and carve-outs, peak-season overrides, an equity-stake condition, data localisation, tax escrow, statutory audit notes, product safety, and commercial price adjustments.

Two corpus sizes:

- **7 documents.** The deal room: 18.5k tokens as plain text.
- **21 documents.** The same deal room plus the equivalent seven documents for two other suppliers: 54k tokens. The added contracts have the same structure and clause numbers but different parties, amounts, percentages and dates.

Every question starts with a line naming the supplier under audit and asking for that supplier's contracts only.

Each design was run for three sessions of eight questions at each corpus size: 24 answers per cell, 96 in all.

Quality was measured three ways:

- **Key facts.** 53 facts across the eight questions, written from the contracts alone, scored by matching (159 per cell over three sessions).
- **Retrieval and citations.** Whether the clauses each question needs reached the answering model, whether any clause came from another supplier, and where the citations point.
- **Blind grading.** A model not under test (Opus 5.5) graded each answer for correctness and completeness against the audited supplier's contracts and listed every factual error with quotes. Each serious error's source quote was checked against the contracts.

### The runs

**Cost and quality, per design and corpus size**

| Design | Answering model | Corpus (documents) | Answers | Cost per question, cold ($) | Cost per question, warm ($) | Key facts stated (of 159) | Answers with a serious error (of 24) | Correctness (1–5) | Completeness (1–5) | Minor errors |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Without | Sonnet 5.5 | 7 | 24 | 0.0459 | 0.0459 | 156 | 1 | 4.50 | 4.83 | 17 |
| With | Haiku 5.5 picks, Sonnet 5.5 answers | 7 | 24 | 0.0230 | 0.0227 | 153 | 0 | 4.75 | 4.54 | 11 |
| Without | Sonnet 5.5 | 21 | 24 | 0.1173 | 0.1173 | 150 | 3 | 4.50 | 4.75 | 17 |
| With | Haiku 5.5 picks, Sonnet 5.5 answers | 21 | 24 | 0.0250 | 0.0241 | 154 | 2 | 4.54 | 4.54 | 13 |

Change from without to with: cost −50.0% at 7 documents and −78.7% at 21 documents (cold). "Cold" is the average over an eight-question session that starts with an empty cache.

**Tokens per question**

| Design | Corpus (documents) | Prompt tokens to Sonnet | Output tokens from Sonnet | Prompt tokens to Haiku | Of which read from cache | Output tokens from Haiku |
|---|---:|---:|---:|---:|---:|---:|
| Without | 7 | 18,492 | 895 | 0 | 0 | 0 |
| With | 7 | 6,194 | 988 | 21,652 | 18,743 | 340 |
| Without | 21 | 54,221 | 884 | 0 | 0 | 0 |
| With | 21 | 6,221 | 1,079 | 63,437 | 55,305 | 349 |

**Where the cost sits, per question (cold)**

| Design | Corpus (documents) | Sonnet ($) | Haiku ($) | Total ($) | One-off cost of writing the cache ($) |
|---|---:|---:|---:|---:|---:|
| Without | 7 | 0.0459 | 0.0000 | 0.0459 | 0.0000 |
| With | 7 | 0.0223 | 0.0007 | 0.0230 | 0.0025 |
| Without | 21 | 0.1173 | 0.0000 | 0.1173 | 0.0000 |
| With | 21 | 0.0232 | 0.0017 | 0.0250 | 0.0073 |

**Retrieval and citations, "with" design**

| Corpus (documents) | Needed clauses among the five picked (of 90) | Other-supplier clauses picked (of 120) | Citations | Citations at the audited supplier's documents | Citations at the clauses the question needs | Answers with no citation (of 24) | Answers stating another supplier's value (of 24) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 7 | 89 | 0 | 245 | 245 | 205 | 0 | 0 |
| 21 | 89 | 0 | 251 | 251 | 206 | 0 | 0 |

The "without" design sends every clause and asks for no citations. At 21 documents all 24 of its prompts held the other two suppliers' text; none of its answers stated another supplier's value.

**How answers described what they could not find**

| Design | Corpus (documents) | Answers saying the documents lack a term (of 24) | Answers saying a term is not in the text provided (of 24) |
|---|---:|---:|---:|
| Without | 7 | 7 | 0 |
| With | 7 | 0 | 21 |
| Without | 21 | 1 | 1 |
| With | 21 | 0 | 20 |

The "with" design's instructions tell the model to say when something is not in the text it was given, because it sees five clauses and not the whole corpus.

**By question** (three answers per row)

| Design | Corpus (documents) | Question | Key facts stated | Key facts (out of) | Correctness (1–5) | Completeness (1–5) | Cost per question, cold ($) |
|---|---:|---|---:|---:|---:|---:|---:|
| Without | 7 | audit-01/q1 | 21 | 21 | 4.67 | 5.00 | 0.0461 |
| Without | 7 | audit-01/q2 | 21 | 21 | 4.33 | 5.00 | 0.0459 |
| Without | 7 | audit-01/q3 | 21 | 21 | 4.67 | 5.00 | 0.0460 |
| Without | 7 | audit-01/q4 | 15 | 15 | 4.33 | 5.00 | 0.0453 |
| Without | 7 | audit-02/q1 | 15 | 18 | 4.67 | 5.00 | 0.0458 |
| Without | 7 | audit-02/q2 | 21 | 21 | 4.33 | 4.00 | 0.0462 |
| Without | 7 | audit-02/q3 | 21 | 21 | 5.00 | 5.00 | 0.0458 |
| Without | 7 | audit-02/q4 | 21 | 21 | 4.00 | 4.67 | 0.0465 |
| With | 7 | audit-01/q1 | 20 | 21 | 4.67 | 4.33 | 0.0240 |
| With | 7 | audit-01/q2 | 20 | 21 | 4.67 | 4.67 | 0.0219 |
| With | 7 | audit-01/q3 | 21 | 21 | 4.67 | 5.00 | 0.0240 |
| With | 7 | audit-01/q4 | 15 | 15 | 4.67 | 4.67 | 0.0219 |
| With | 7 | audit-02/q1 | 15 | 18 | 5.00 | 4.67 | 0.0217 |
| With | 7 | audit-02/q2 | 21 | 21 | 5.00 | 4.00 | 0.0237 |
| With | 7 | audit-02/q3 | 21 | 21 | 4.33 | 5.00 | 0.0227 |
| With | 7 | audit-02/q4 | 20 | 21 | 5.00 | 4.00 | 0.0240 |
| Without | 21 | audit-01/q1 | 20 | 21 | 4.67 | 4.67 | 0.1168 |
| Without | 21 | audit-01/q2 | 20 | 21 | 4.67 | 4.33 | 0.1172 |
| Without | 21 | audit-01/q3 | 21 | 21 | 4.33 | 5.00 | 0.1175 |
| Without | 21 | audit-01/q4 | 13 | 15 | 4.33 | 5.00 | 0.1171 |
| Without | 21 | audit-02/q1 | 16 | 18 | 5.00 | 5.00 | 0.1163 |
| Without | 21 | audit-02/q2 | 21 | 21 | 4.00 | 4.67 | 0.1185 |
| Without | 21 | audit-02/q3 | 21 | 21 | 5.00 | 5.00 | 0.1170 |
| Without | 21 | audit-02/q4 | 18 | 21 | 4.00 | 4.33 | 0.1178 |
| With | 21 | audit-01/q1 | 21 | 21 | 4.00 | 4.67 | 0.0301 |
| With | 21 | audit-01/q2 | 21 | 21 | 4.33 | 5.00 | 0.0227 |
| With | 21 | audit-01/q3 | 21 | 21 | 5.00 | 4.67 | 0.0246 |
| With | 21 | audit-01/q4 | 13 | 15 | 4.67 | 4.67 | 0.0224 |
| With | 21 | audit-02/q1 | 16 | 18 | 4.67 | 4.33 | 0.0256 |
| With | 21 | audit-02/q2 | 20 | 21 | 5.00 | 4.00 | 0.0243 |
| With | 21 | audit-02/q3 | 21 | 21 | 4.67 | 5.00 | 0.0264 |
| With | 21 | audit-02/q4 | 21 | 21 | 4.00 | 4.00 | 0.0238 |

**The six serious errors**

| Design | Corpus (documents) | Question | What the answer said | What the contracts say |
|---|---:|---|---|---|
| Without | 7 | audit-01/q4 | The CISO and DPO must confirm the Munich firewall in writing | The firewall is a continuing condition; written authorisation appears only for cross-border transfers |
| Without | 21 | audit-01/q2 | Peak deductions sit outside the master agreement's cap analysis | No document says so; credit notes appear only for volume rebates |
| Without | 21 | audit-02/q4 | Peak damages and tax debits are the only uncapped recovery routes | Peak damages are capped at 6.50% of the festive-peak order value |
| Without | 21 | audit-02/q2 | A final tax order would not be capped | The demand is a non-fraud dispute; the uncapped carve-out covers fraud |
| With | 21 | audit-02/q4 | The 6.5% cap and the 3.25% ceiling are not stackable | The 3.25% ceiling expressly excludes peak damages, so both can apply |
| With | 21 | audit-01/q1 | No bank certificate, escrow or delisting gate is stated in the text provided | The contracts contain all three, in clauses that were not among the five picked |

### Deck claims against the data

| Claim | Measured | Verdict |
|---|---|---|
| Input 15k–100k+ tokens | 18.5k and 54.2k per question without; 5.5k–6.9k to the answering model with | Supported |
| Output 400–1,500 tokens | Median 938, range 760–1,584; 94 of 96 answers in range | Partly |
| Input:output of 20:1 to 100:1 | 20.5:1 at 7 documents, 62.1:1 at 21 documents, without the improvement | Supported |
| Pair hybrid retrieval (reranking and chunk filtering) with context caching | 89 of 90 needed clauses among those picked at both sizes, none from another supplier; cost −50% and −79%; answers with a serious error 0 and 2 of 24, against 1 and 3 | Supported |
| …without losing answer quality (our addition; the deck does not claim it) | Serious errors 0 and 2 of 24 against 1 and 3; correctness 4.75 and 4.54 against 4.50 and 4.50; key facts 153 against 156 at 7 documents and 154 against 150 at 21 | Partly |

### Points for the post

- **Cost.** $0.0459 to $0.0230 per question at 7 documents; $0.1173 to $0.0250 at 21 documents.
- **Cost against corpus size.** Tripling the corpus raised the cost of a question 2.6 times without the improvement and 1.09 times with it.
- **Where the tokens went.** Without the improvement Sonnet read 18,492 or 54,221 prompt tokens per question. With it Sonnet read about 6,200 at either size; Haiku read the corpus from cache.
- **The cache is on the small model.** Writing it cost $0.0025 at 7 documents and $0.0073 at 21.
- **Retrieval.** The five clauses picked held 89 of the 90 needed clauses at both sizes, and none of the 240 picked clauses came from another supplier.
- **Serious errors.** 0 and 2 answers of 24 with the improvement; 1 and 3 of 24 without it. With 24 answers per cell the intervals overlap.
- **Completeness.** Graded 4.54 at both sizes with the improvement, against 4.83 and 4.75 without it. Correctness was 4.75 and 4.54 against 4.50 and 4.50.
- **Citations.** Every answer with the improvement carried citations (245 and 251 in 24 answers), all pointing at the audited supplier's documents.
- **Five clauses are not the whole corpus.** In 41 of 48 answers the "with" design said some term was not in the text provided. One of its two serious errors was such a statement about terms that exist in clauses it was not given.
- **Look-alike suppliers.** With three near-identical deal rooms in one prompt, no answer in either design attributed another supplier's value to the audited supplier.

### Limits

- Eight questions on one deal room, three sessions per cell. The added suppliers' contracts are mechanical variants of the first supplier's.
- One grading pass per answer by a single model. Its serious findings were checked against the contracts by hand.
- The larger corpus is 54k tokens. Results may differ where a corpus no longer fits in context.
- The clause boundaries and headings Haiku picks from were written for these documents.
- The two designs use different answer instructions in one respect: the "with" design is told to say when something is not in the text provided.
- The answering model is Sonnet 5.5 in both designs. Other answering models were not run.

Full results: `analysis/cat4_quality_rerun.md`. Records: `backend/experiments/cat4_quality/runs.jsonl` and `judgements.jsonl`. Answer key: `backend/app/data/cat4_quality_keys.json`. Other levers tried (cached full corpus; keyword search with reranking): `analysis/experiments_log.md`.

---

## Part 5: Autonomous process orchestration

**One-line result:** with a step budget and a deterministic policy tool, reconciling an invoice cost 67% less on Sonnet and 93% less when Haiku ran first and Sonnet took over only on multi-factor disputes. All 108 vouchers were exact in all three configurations.

### The anti-pattern

An agent loops over raw database tables with no step budget. Each lookup returns every column, every turn re-sends the policy manual and everything fetched so far at full price, and the model does the policy arithmetic itself.

### The suggested path

The deck's improvement: max-step loop budgets, deterministic guardrails, and small-model routing for routine tool calls.

- **Step budget.** Four steps.
- **Deterministic guardrail.** A policy tool computes the voucher in code from the policy manual's rules. The commit is refused until the tool has run.
- **Small-model routing.** Haiku 5.5 runs the invoice; the run switches to Sonnet 5.5 only when the policy tool flags a dispute that mixes two or more factors.

As built, the "with" design also fetches the invoice, purchase order and goods receipt with one narrow query in place of the raw tables, and sends the policy manual as a cached prefix. The runs measure the design as a whole.

### What the deck says

- **Shape:** goal-directed workflows that chain planning, tool calls, validation and state updates.
- **Profile:** 25k–150k+ tokens in, 1,500–8,000 out, in a plan, call, verify, dispatch loop.
- **Lever:** max-step loop budgets, deterministic guardrails, and small-model routing for routine tool calls.
- **Use cases:** invoice reconciliation, claims adjudication, supply chain dispatch.

### What was built

The NovaMart three-way invoice reconciliation agent. It matches a vendor invoice against the purchase order and the warehouse goods receipt in a SQLite database, applies an accounts-payable policy manual, and commits a payment voucher with five fields: the decision, the net principal, the tax paid, the tax held in escrow, and the deduction.

Twelve invoices, each with a voucher worked out by hand from the manual:

| Invoice | Scenario | Type | Expected decision | Mixes two or more dispute factors |
|---|---|---|---|---|
| inv-01 | Tax escrow, clean receipt | Routine | Approve with tax escrow | No |
| inv-02 | Rejected units, amendment, unauthorised price rise and freight | Dispute | Approve in part with debit note | Yes |
| inv-03 | Cancelled tax registration and a phantom line | Hard stop | Block | No |
| inv-04 | Clean full match | Routine | Approve | No |
| inv-05 | Rejected units only | Dispute | Approve in part with debit note | No |
| inv-06 | Price 1.28% above the purchase order, no amendment | Routine | Approve in part with debit note | No |
| inv-07 | Price rise outside tolerance, no amendment | Dispute | Approve in part with debit note | No |
| inv-08 | Authorised amendment only | Routine | Approve | No |
| inv-09 | Freight above the cap | Dispute | Approve in part with debit note | No |
| inv-10 | Tax escrow on a large-enterprise vendor | Routine | Approve with tax escrow | No |
| inv-11 | Phantom line that was never received | Hard stop | Block | No |
| inv-12 | Short receipt, unauthorised price rise, rejected units, freight over cap | Dispute | Approve in part with debit note | Yes |

Three configurations, each run three times on every invoice: 108 runs.

- **Without, on Sonnet 5.5.** Five raw-table lookups available, the model chooses which to call, no cache, no policy tool, a 12-turn safety cap.
- **With, on Sonnet 5.5.**
- **With, Haiku 5.5 first.** Sonnet takes over when the policy tool flags a multi-factor dispute.

The "without" design was not run with Haiku first.

### The runs

**Per configuration** (36 runs each)

| Design | Model | Exact vouchers (of 36) | Cost per 1,000 invoices, cold ($) | Cost per 1,000 invoices, warm ($) | Model turns per invoice | Runs that reached the step limit | Runs escalated to Sonnet | Uncached input tokens | Cache-write tokens | Cache-read tokens | Output tokens |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Without | Sonnet 5.5 | 36 | 153.41 | 153.41 | 3.86 | 0 | 0 | 68,266 | 0 | 0 | 1,688 |
| With | Sonnet 5.5 | 36 | 51.22 | 30.49 | 4.00 | 0 | 0 | 7,137 | 8,637 | 25,911 | 1,276 |
| With | Haiku 5.5 first | 36 | 10.42 | 5.94 | 4.00 | 0 | 6 | 7,307 | 10,142 | 24,630 | 1,352 |

Change from without: −66.6% cold and −80.1% warm on Sonnet; −93.2% cold and −96.1% warm with Haiku first. Token counts are means per invoice.

**By invoice type**

| Design | Model | Invoice type | Runs | Exact vouchers | Cost per 1,000 invoices, cold ($) | Cost per 1,000 invoices, warm ($) | Runs escalated to Sonnet |
|---|---|---|---:|---:|---:|---:|---:|
| Without | Sonnet 5.5 | Routine | 15 | 15 | 159.55 | 159.55 | 0 |
| With | Sonnet 5.5 | Routine | 15 | 15 | 50.33 | 29.61 | 0 |
| With | Haiku 5.5 first | Routine | 15 | 15 | 2.72 | 1.73 | 0 |
| Without | Sonnet 5.5 | Dispute | 15 | 15 | 161.06 | 161.06 | 0 |
| With | Sonnet 5.5 | Dispute | 15 | 15 | 52.60 | 31.87 | 0 |
| With | Haiku 5.5 first | Dispute | 15 | 15 | 21.19 | 11.85 | 6 |
| Without | Sonnet 5.5 | Hard stop | 6 | 6 | 118.97 | 118.97 | 0 |
| With | Sonnet 5.5 | Hard stop | 6 | 6 | 50.00 | 29.27 | 0 |
| With | Haiku 5.5 first | Hard stop | 6 | 6 | 2.73 | 1.73 | 0 |

**By invoice** (three runs per row)

| Design | Model | Invoice | Exact vouchers (of 3) | Cost per 1,000 invoices, cold ($) | Cost per 1,000 invoices, warm ($) | Runs escalated to Sonnet (of 3) |
|---|---|---|---:|---:|---:|---:|
| Without | Sonnet 5.5 | inv-01 | 3 | 164.05 | 164.05 | 0 |
| Without | Sonnet 5.5 | inv-02 | 3 | 170.41 | 170.41 | 0 |
| Without | Sonnet 5.5 | inv-03 | 3 | 104.72 | 104.72 | 0 |
| Without | Sonnet 5.5 | inv-04 | 3 | 167.59 | 167.59 | 0 |
| Without | Sonnet 5.5 | inv-05 | 3 | 147.20 | 147.20 | 0 |
| Without | Sonnet 5.5 | inv-06 | 3 | 150.01 | 150.01 | 0 |
| Without | Sonnet 5.5 | inv-07 | 3 | 168.13 | 168.13 | 0 |
| Without | Sonnet 5.5 | inv-08 | 3 | 150.95 | 150.95 | 0 |
| Without | Sonnet 5.5 | inv-09 | 3 | 146.83 | 146.83 | 0 |
| Without | Sonnet 5.5 | inv-10 | 3 | 165.13 | 165.13 | 0 |
| Without | Sonnet 5.5 | inv-11 | 3 | 133.21 | 133.21 | 0 |
| Without | Sonnet 5.5 | inv-12 | 3 | 172.73 | 172.73 | 0 |
| With | Sonnet 5.5 | inv-01 | 3 | 50.15 | 29.42 | 0 |
| With | Sonnet 5.5 | inv-02 | 3 | 54.47 | 33.74 | 0 |
| With | Sonnet 5.5 | inv-03 | 3 | 49.33 | 28.61 | 0 |
| With | Sonnet 5.5 | inv-04 | 3 | 50.00 | 29.27 | 0 |
| With | Sonnet 5.5 | inv-05 | 3 | 49.58 | 28.86 | 0 |
| With | Sonnet 5.5 | inv-06 | 3 | 51.60 | 30.88 | 0 |
| With | Sonnet 5.5 | inv-07 | 3 | 53.24 | 32.51 | 0 |
| With | Sonnet 5.5 | inv-08 | 3 | 49.59 | 28.86 | 0 |
| With | Sonnet 5.5 | inv-09 | 3 | 49.42 | 28.69 | 0 |
| With | Sonnet 5.5 | inv-10 | 3 | 50.34 | 29.61 | 0 |
| With | Sonnet 5.5 | inv-11 | 3 | 50.66 | 29.93 | 0 |
| With | Sonnet 5.5 | inv-12 | 3 | 56.28 | 35.54 | 0 |
| With | Haiku 5.5 first | inv-01 | 3 | 2.73 | 1.73 | 0 |
| With | Haiku 5.5 first | inv-02 | 3 | 47.76 | 25.90 | 3 |
| With | Haiku 5.5 first | inv-03 | 3 | 2.73 | 1.73 | 0 |
| With | Haiku 5.5 first | inv-04 | 3 | 2.73 | 1.73 | 0 |
| With | Haiku 5.5 first | inv-05 | 3 | 2.69 | 1.69 | 0 |
| With | Haiku 5.5 first | inv-06 | 3 | 2.70 | 1.70 | 0 |
| With | Haiku 5.5 first | inv-07 | 3 | 2.79 | 1.79 | 0 |
| With | Haiku 5.5 first | inv-08 | 3 | 2.74 | 1.74 | 0 |
| With | Haiku 5.5 first | inv-09 | 3 | 2.70 | 1.70 | 0 |
| With | Haiku 5.5 first | inv-10 | 3 | 2.72 | 1.72 | 0 |
| With | Haiku 5.5 first | inv-11 | 3 | 2.72 | 1.72 | 0 |
| With | Haiku 5.5 first | inv-12 | 3 | 50.01 | 28.15 | 3 |

### Deck claims against the data

| Claim | Measured | Verdict |
|---|---|---|
| Input 25k–150k+ tokens per task | 44k–77k without; 41k–44k with | Supported |
| Output 1,500–8,000 tokens per task | 1,050–2,071; 32 of 108 runs in range | Partly |
| Max-step budgets, deterministic guardrails and small-model routing | Step budget: no run reached it. With against without on Sonnet: cost −67%, 36 of 36 exact in both. Haiku first against Sonnet: cost −80%, 36 of 36 exact in both | Partly |
| …without losing accuracy (our addition; the deck does not claim it) | 36 of 36 exact vouchers in every configuration, so a loss could not be detected on these invoices | Partly |

### Points for the post

- **Cost.** $153.41 per 1,000 invoices without; $51.22 with, on Sonnet; $10.42 with, Haiku first.
- **Accuracy.** 36 of 36 exact vouchers in every configuration. These invoices do not separate the configurations on accuracy.
- **Where the tokens went.** Without the improvement a run sent 68,266 uncached input tokens. With it a run sent about 7,200 uncached and read about 25,000 from cache.
- **The step budget did not come into play.** The "with" runs took exactly four turns. The "without" runs, with only a 12-turn safety cap, took 3.86 on average.
- **The policy tool.** In all 72 "with" runs the committed voucher was the tool's figure, and the tool's figure equals the hand-derived answer on all 12 invoices. In the 36 "without" runs the model's own arithmetic also matched.
- **Routing.** With Haiku first, ten invoices completed on Haiku at about $2.72 per 1,000. The two multi-factor disputes switched to Sonnet and cost $47.76 and $50.01 per 1,000, close to the Sonnet configuration's $54.47 and $56.28.
- **The mix of invoices sets the Haiku-first cost.** Here 6 of 36 runs escalated. A portfolio with more multi-factor disputes would sit nearer the Sonnet figure.
- **A fleet sharing the cached manual** would sit between the cold and warm columns: $30.49 and $5.94 per 1,000 when warm.
- **The "with" design is a bundle.** It changes the query, the caching, the step limit and the tool at once. Runs that add those one at a time are in `analysis/experiments_log.md`.

### Limits

- Twelve invoices, three runs per configuration.
- Every configuration scored 36 of 36, so a difference in accuracy cannot be detected. Thirty-six of thirty-six leaves a 95% interval of 90–100%.
- The invoices test quantities, rates, a tax split and a debit note. Harder reconciliations were not run.
- The "without" design was run on Sonnet only.
- Sonnet ran with thinking between tool calls; Haiku ran with thinking off, as the app configures them.
- Every cached run started from an empty cache.

Full results: `analysis/cat5_ablation.md`. Records: `backend/experiments/cat5_ablation/runs.jsonl`. Invoices and hand-derived vouchers: `backend/app/data/cat5_ablation_fixtures.py`. Other levers tried (caching alone; the narrow query without the policy tool, on Sonnet and on Haiku): `analysis/experiments_log.md`.

---

## Part 6: Multi-agent swarms and automated engineering

**One-line result:** isolating the agents and caching the shared prefix cut the cost of a verified fix from $0.469 to $0.100 with Sonnet on every turn, and to $0.056 with Haiku agents and a Sonnet patch author. Every configuration fixed 15 of 15.

**Read this result with one limit in mind: harder tasks might give a different result.** Every configuration solved every task here, and the tasks were small, single-module fixes. On harder work (changes across several files, longer chains of agent turns, larger codebases) the configurations could differ in how often they get the fix right, and the cost ranking could change too. That was not tested.

### The anti-pattern

Every agent reads and writes one shared, growing thread. The thread carries the repository manual plus unrelated services and telemetry, and each of the five agent turns re-sends all of it at full price.

### The suggested path

The deck's improvement: isolate sub-agent contexts, cache shared repository prefixes, and measure return by cost per verified outcome.

- Each agent gets a fresh, narrow thread with only what its role needs.
- A 9.3k-token repository guide is cached and shared by all agents.
- Cost is divided by the number of runs whose patch passes verification.

### What the deck says

- **Shape:** coordinated teams of specialised agents working across large codebases, telemetry and test suites.
- **Profile:** 100k–1M+ tokens in, 10k–50k+ out per run, and 1.5M–10M+ tokens per developer per day.
- **Lever:** isolate sub-agent contexts, cache shared repository prefixes, and measure return by cost per verified outcome.
- **Use cases:** autonomous feature development, security threat hunting, CI/CD failure triage.

### What was built

The NovaMart checkout and pricing self-healing swarm. Five agent turns per run: an orchestrator, a CI triager, a patch author, a security critic and a merge gate.

Three incidents, each a single-file fix:

- **inc-01, CI failure.** A checkout tax module under-remitting tax through floating-point drift and coupon stacking.
- **inc-02, security finding.** A payment webhook open to replayed requests, with a timing leak and personal data in logs.
- **inc-03, feature.** Deadlock-free stock reservation across three fulfilment centres with all-or-nothing rollback.

Every patch is judged by a deterministic sandbox: 4 unit checks, 4 adversarial checks and 2 static code checks, 10 per incident. A run is a verified fix only if the patch passes all 10. Every configuration gets one retry if the first patch does not pass.

Three configurations, each run five times on each incident: 45 runs. All three use the same role instructions and the same output limits.

- **Without, Sonnet 5.5 on every turn.** The shared thread, nothing cached.
- **With, Sonnet 5.5 on every turn.** Isolated threads and the cached repository guide.
- **With, Haiku 5.5 agents and a Sonnet 5.5 patch author.** The same, with Haiku on four of the five roles.

The "without" design was not run with Haiku agents.

### The runs

**Per configuration** (15 runs each)

| Design | Models | Verified fixes (of 15) | Sandbox checks passed (of 150) | Retries used | Cost per verified fix, cold ($) | Cost per verified fix, warm ($) | Cost per 1,000 runs, cold ($) | Cost per 1,000 runs, warm ($) | Model time per run (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Without | Sonnet 5.5 on every turn | 15 | 150 | 0 | 0.4690 | 0.4690 | 469.02 | 469.02 | 30.8 |
| With | Sonnet 5.5 on every turn | 15 | 150 | 0 | 0.0999 | 0.0775 | 99.91 | 77.50 | 38.8 |
| With | Haiku 5.5 agents, Sonnet 5.5 patch author | 15 | 150 | 0 | 0.0562 | 0.0327 | 56.20 | 32.71 | 28.4 |

Change from without: −78.7% cold and −83.5% warm with Sonnet on every turn; −88.0% cold and −93.0% warm with Haiku agents.

**Tokens per run** (mean)

| Design | Models | Uncached input tokens | Cache-write tokens | Cache-read tokens | Output tokens | Total tokens |
|---|---|---:|---:|---:|---:|---:|
| Without | Sonnet 5.5 on every turn | 214,112 | 0 | 0 | 4,079 | 218,191 |
| With | Sonnet 5.5 on every turn | 9,792 | 9,337 | 37,350 | 5,325 | 61,804 |
| With | Haiku 5.5 agents, Sonnet 5.5 patch author | 10,095 | 18,675 | 28,013 | 5,408 | 62,191 |

**By incident** (five runs per row)

| Design | Models | Incident | Verified fixes (of 5) | Cost per 1,000 runs, cold ($) | Cost per 1,000 runs, warm ($) |
|---|---|---|---:|---:|---:|
| Without | Sonnet 5.5 on every turn | inc-01 | 5 | 471.73 | 471.73 |
| Without | Sonnet 5.5 on every turn | inc-02 | 5 | 466.93 | 466.93 |
| Without | Sonnet 5.5 on every turn | inc-03 | 5 | 468.38 | 468.38 |
| With | Sonnet 5.5 on every turn | inc-01 | 5 | 99.63 | 77.22 |
| With | Sonnet 5.5 on every turn | inc-02 | 5 | 99.68 | 77.27 |
| With | Sonnet 5.5 on every turn | inc-03 | 5 | 100.43 | 78.02 |
| With | Haiku 5.5 agents, Sonnet 5.5 patch author | inc-01 | 5 | 53.63 | 30.14 |
| With | Haiku 5.5 agents, Sonnet 5.5 patch author | inc-02 | 5 | 55.57 | 32.08 |
| With | Haiku 5.5 agents, Sonnet 5.5 patch author | inc-03 | 5 | 59.40 | 35.92 |

### Deck claims against the data

| Claim | Measured | Verdict |
|---|---|---|
| Input 100k–1M+ tokens per run | 213k–216k without; 56k–58k with | Partly |
| Output 10k–50k+ tokens per run | 3.9k–6.6k; 0 of 45 runs in range | Not supported |
| 1.5M–10M+ tokens per developer per day | Not measurable from 45 single runs | Not testable |
| Isolate sub-agent contexts, cache the shared repository prefix, measure cost per verified outcome | Cost per verified fix $0.469 without; $0.100 and $0.056 with. Every configuration verified 15 of 15, so the outcome side of the measure was not exercised | Partly |
| …without losing verified fixes (our addition; the deck does not claim it) | 15 of 15 in every configuration, so a loss could not be detected on these incidents | Partly |

### Points for the post

- **Cost per verified fix.** $0.469 without; $0.100 with, Sonnet on every turn; $0.056 with Haiku agents. With a warm cache, $0.078 and $0.033.
- **Correctness.** Every configuration fixed 15 of 15 and passed 150 of 150 sandbox checks on the first patch. On tasks this size the shared thread cost more and produced patches that passed the same checks.
- **Where the tokens went.** The shared thread sent 214,112 uncached input tokens per run. Isolated agents sent 9,792 uncached and read 37,350 from cache.
- **Model tiering and the cache.** A run with two models writes the cached prefix once per model (18,675 cache-write tokens against 9,337). Haiku agents cost 44% less than Sonnet on every turn from a cold start, and 58% less when warm.
- **Time.** Model time per run was 30.8 s without, 38.8 s with Sonnet on every turn, and 28.4 s with Haiku agents.
- **The retry was never used.** In all 45 runs the first patch passed, so the check-and-retry step added no cost and its benefit was not measured.
- **When everything passes, cost per verified fix equals cost per run.** The measure separates configurations only when their pass rates differ.
- **The daily-volume claim in context.** One shared-thread run moves about 218k tokens, so the deck's 1.5M–10M tokens per developer per day equals roughly 7–46 such runs. For the isolated configurations it is roughly 24–160 runs.

### Limits

- **Ceiling effect.** Every configuration scored 100%, so these runs cannot show a difference in correctness. Fifteen of fifteen leaves a 95% interval of 80–100%.
- **The tasks are small, and harder ones might perform differently.** Each is a fix to one small module, made in five turns. Multi-file work over more turns was not run, so the finding that the configurations are equally correct should not be carried over to harder tasks.
- **The "without" design was run with Sonnet on every turn only.**
- **Every run started from an empty cache.** A fleet sharing one cached prefix would sit between the cold and warm columns.
- The per-developer daily volume cannot be checked from single runs.

Full results: `analysis/cat6_fair_rerun.md`. Records, with every prompt and response: `backend/experiments/cat6_fair_rerun/runs.jsonl`.

---

## Appendix

### Rate card used

US dollars per million tokens.

| Model | Input | Output | Cache write | Cache read |
|---|---:|---:|---:|---:|
| Claude Sonnet 5.5 | 2.00 | 10.00 | 2.50 | 0.10 |
| Claude Haiku 5.5 (prompts up to 100k tokens) | 0.10 | 0.50 | 0.125 | 0.01 |

- Cache write is 1.25× input. Cache read is a 95% discount on Sonnet and 90% on Haiku.
- The Batch API is priced at 50% off.
- No recorded Haiku call exceeded 100k prompt tokens, so the higher long-prompt rate never applied.

### Terms

- **Without, with.** One design per archetype, run without and with the improvement the deck suggests.
- **Configuration.** One design on one model set-up, for example "with, Haiku 5.5 first".
- **Cold, warm.** The two cost views defined at the top of this file.
- **Cost per verified outcome.** Total spend divided by the number of runs that passed verification.
- **Recall question.** A short question, asked after a session's last scripted turn, about one detail the user stated once earlier.
- **Serious error.** A factual error the blind grader marked as material, with a quote from the answer and from the source.
- **Golden replay.** A recorded live run that the lab app plays back at no cost: repeat 0 of each configuration.

### Where the data lives

- Validation report with every claim, measurement and verdict: `analysis/deck_claims_validation.md` (and `.json`).
- Script that produces it: `backend/scripts/validate_deck_claims.py`.
- Per-archetype results: `analysis/cat1_ablation.md`, `analysis/cat2_quality.md`, `analysis/cat3_quality_rerun.md`, `analysis/cat4_quality_rerun.md`, `analysis/cat5_ablation.md`, `analysis/cat6_fair_rerun.md`.
- Records, with full prompts and responses: `backend/experiments/` (one folder per archetype).
- Replays the app serves: `backend/replays/cat{1..6}_golden_replays.json`.
- Other levers tried, and earlier designs that were replaced: `analysis/experiments_log.md`.
- The deck: `6 Key Production AI Archerypes.pdf`, one folder above the project.
