# Six AI Workload Archetypes: experiment notes for the post series

Source material for seven posts: one introduction and one post per archetype. Every number here comes from `analysis/deck_claims_validation.md` (regenerated 25 Nov 2026), the reruns and scoring in `analysis/cat6_fair_rerun.md`, `analysis/cat3_quality_rerun.md` and `analysis/cat2_quality.md`, or the golden replays the lab app serves. Part 0 feeds the intro post; Parts 1–6 each feed one archetype post; the appendix holds the rate card and definitions that every post may need.

## How to read the numbers

- **The deck.** "Six Key AI Archetypes for AI Workloads" is a 9-slide guide by Eric Lam. It sorts enterprise AI work into six archetypes, gives each a typical token profile, and names one architectural lever per archetype. The experiment tests those claims.
- **The lab.** Each archetype was built as a real workload at NovaMart, a fictional Indian omnichannel retailer (12M SKUs, 45,000 sellers, $2.4B GMV). All data is synthetic. Every workload was run live against the model APIs once and recorded.
- **Rungs.** Each archetype was run several ways on the same inputs, from a naive version up to the governed version the deck recommends. Each way is called a rung.
- **Models.** Claude Sonnet 5.5 and Claude Haiku 5.5 throughout. Archetype 1 also includes a Gemini Decision 1 rung.
- **Cost.** Costs are recomputed from the recorded token counts at the rate card in the appendix, and quoted per 1,000 units of work (items, documents, sessions, and so on).
- **Three cost views** appear wherever caching is involved:
  - *Billed*: what the recorded runs actually cost, cache hits and misses as they happened.
  - *Cold*: the first call has to write the cache. This is a single user starting from nothing.
  - *Warm*: the cached prefix is already there. This is a busy fleet in steady state.
- **Sample sizes are small**: 12 items, 4 documents, 2 sessions (each run 3 times), 8 questions, 3 invoices, 3 incidents (each run 5 times). Quote the percentages as indicative results from one lab, not as benchmarks.

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
| 1 | 1,000 items | $22.04 | $0.189 (Haiku, strict JSON) | −99.1% | Fields correct rose from 27/42 to 40/42 |
| 2 | 1,000 documents | $58.92 | $1.39 (Haiku, section template); $27.25 with the template on Sonnet | −98%; −54% | Every core fact kept, but a blind grader preferred the long draft in 16 of 16 comparisons; serious errors rose from 1 to 6 (Sonnet template) and 10 (Haiku template) |
| 3 | 1,000 ten-turn sessions | $399 | $212 (cache + compaction); $240 with caching alone | −47%; −40% | Caching: no change. Compaction: new answers unaffected, but recall of earlier details fell from 36/36 to 2/36 |
| 4 | 1,000 questions | $46.29 | $13.35 (cached corpus, warm) | −71% | Citations per answer rose from 0 to 10 |
| 5 | 1,000 invoices | $191 | $16.99 (Haiku first, Sonnet on escalation) | −91.1% | Correct voucher on 3/3 at every rung |
| 6 | 1,000 incidents | $696 | $56.20 (Haiku agents, Sonnet patch author, cold start) | −92% | Unchanged: every arm fixed 15 of 15 |

### The scorecard

The scorecard has 29 rows: the deck's 26 testable claims plus three implicit ones we added, that the cheaper version loses no quality in Archetypes 1, 2 and 3. Against the lab data:

- **11 supported**: the measurement falls inside the claimed range or clears the threshold.
- **15 partly supported**: the direction holds, but the magnitude is outside the range or a confound limits the conclusion.
- **2 not supported**: our added rows for Archetypes 2 and 3. Templated drafts lose to the long draft on quality, and compacting old turns loses recall.
- **1 not testable**: the per-developer daily token volume for swarms.

The Archetype 6 rows were re-judged on the fair rerun; none of the verdicts changed.

### Findings that cut across archetypes

- **Every cost lever worked in the direction the deck says.** None of the deck's own claims was contradicted. The two failures are quality costs the deck does not mention.
- **The "60–80%" rule missed on both sides.** Changing the model as well as the prompt gave 98–99%. A template alone, on the same model, gave 54%.
- **Cheaper was not worse where the work has a checkable right answer, and was worse where it does not.** The governed rungs were more accurate in Archetype 1 and equally accurate in Archetypes 5 and 6. In Archetype 2 the templated drafts kept every core fact but lost every blind comparison with the long draft, mostly by inventing owners and deadlines the template demanded. In Archetype 3, caching cost nothing in quality, but compacting old turns bought an extra 11% saving at the price of nearly all recall of earlier details.
- **The deck's token bands describe context size, not the bill.** A ten-turn session peaks at 22k tokens of context but bills 163k prompt tokens, because every turn re-sends the history.
- **The archetype ordering depends on the unit.** The deck's scale runs 1 < 2 < 3 < 4 < 5 << 6. Measured, 1 < 2 < {3, 4, 5} < 6 holds, but a ten-turn session moves more tokens than a whole invoice or a four-question audit.
- **The Archetype 1 naive baseline is understated.** Most of its naive runs hit their output cap and were cut off, so the true naive cost is higher than shown. Archetype 6 had the same problem and was rerun without it.
- **Output control and model choice dominate the cheap end; context control dominates the expensive end.** In Archetypes 1 and 2, output is 88–93% of the naive bill. In Archetypes 3, 5 and 6, input is 71–91% of it.

### Measured token scale

Median total tokens per unit of work, on the rung closest to what the deck describes:

| Unit | Tokens |
|---|---:|
| Archetype 1, one item | 1.5k |
| Archetype 2, one document | 8.5k |
| Archetype 4, one question | 19.3k |
| Archetype 4, one four-question audit | 77.5k |
| Archetype 5, one invoice | 116.9k |
| Archetype 3, one ten-turn session | 169.6k |
| Archetype 6, one incident (rerun, mean) | 266.9k |

### What we got wrong while measuring

Good material for the intro: the measurement itself needed six corrections.

- **Duplicate traces.** At the first audit the trace folder held 842 files but only 206 distinct runs. The rest were copies written each time the app replayed a recorded run; one run appeared 29 times. Averaging the raw folder weights each run by how often someone viewed it.
- **A wrong price.** The rate card had Sonnet cache reads at $0.20 per million tokens; the published rate is $0.10. Every cached Sonnet rung was overstated by 2–10%.
- **Failures that cost nothing.** Cost per verified outcome was recorded as zero for runs that failed verification, which made the worst rung look free. It is now undefined when nothing was verified.
- **Claims that drifted from the data.** The app's labels carried fixed numbers that no longer matched the runs. One badge promised "-65%+" where the data showed −97%; one note said "~115k–130k prompt tokens" where the run used 236k. Labels are now computed from each run.
- **A rigged comparison.** The first swarm experiment showed the naive swarm verifying 1 fix in 3 against 3 in 3 for the governed ones. The naive agents had been cut off at their output cap, and the capture script discarded governed runs that failed. Rerun fairly, every arm fixed 15 of 15 (Part 6).
- **A check that failed good code.** One static security check flagged a harmless comparison because of a variable's name. Three correct patches were scored as failures until the check was fixed.

### Limits to state in the intro

- Samples are small. Archetypes 3 and 6 were repeated (3 and 5 times); everything else ran once.
- Archetype 2's quality grades come from one model acting as a blind grader, with its serious findings checked by hand. Archetype 4's quality scoring is still to come.
- Several rungs change more than one thing at a time, so a saving cannot always be split between levers.
- All data is synthetic and the corpus sizes are at the low end of the deck's bands.

---

## Part 1: Classification, extraction and routing

**One-line result:** a small model with a strict JSON schema cost 99% less than a large model writing prose, and got more fields right.

### What the deck says

- **Shape:** high-volume, low-latency triage that turns unstructured payloads into tags, masked fields and routing decisions.
- **Profile:** 500–1,500 tokens in, 10–100 out, input-to-output ratio of 20:1 to 50:1.
- **Lever:** route to small models with strict JSON schema output and batching, to cut unit cost by more than 80%.
- **Use cases:** omnichannel support, PII and compliance masking, catalog tagging.

### What was built

The NovaMart Intake and Catalog Gate, tested on 12 items across two tasks:

- **Support ticket triage (6 items).** Examples: a damaged-goods email exposing a payment card and phone number; a seller settlement dispute exposing Aadhaar and PAN tax IDs; a suspected account takeover from a voice transcript.
- **Seller SKU tagging (6 items).** Examples: a "100% pure mulberry silk" kurta whose care-label scan contradicts the listing; a 27,000 mAh power bank missing its air-freight certificate; a clean espresso grinder that should auto-publish.

Accuracy was scored on 42 ground-truth fields across the 12 items. PII masking is done by a separate deterministic regex step, not by the model.

### Results

| Rung | Cost per 1,000 items | vs naive | Prompt tokens (median) | Output tokens (median) | Output share of cost |
|---|---:|---:|---:|---:|---:|
| Sonnet 5.5, free-text prose | $22.04 | — | 790 | 2,048 | 93% |
| Haiku 5.5, free-text prose | $1.02 | −95.4% | 790 | 2,048 | 92% |
| Haiku 5.5, strict JSON schema | $0.189 | −99.1% | 1,387 | 100 | 28% |
| Gemini Decision 1, decisions API | $0.099 | −99.6% | 972 | 0 | 0% |
| Haiku 5.5, strict JSON, Batch API | $0.094 | −99.6% | 1,387 | 100 | 28% |

| Rung | Fields correct (of 42) | Items fully correct (of 12) | Valid schema output |
|---|---:|---:|---:|
| Sonnet 5.5, free-text prose | 27 | 2 | 0 |
| Haiku 5.5, free-text prose | 24 | 1 | 0 |
| Haiku 5.5, strict JSON schema | 40 | 11 | 12 |
| Gemini Decision 1 | 41 | 11 | 12 |

### Deck claims against the data

| Claim | Measured | Verdict |
|---|---|---|
| Input 500–1,500 tokens | Raw payloads 581–1,472; with schema and system prompt 856–2,063 | Partly |
| Output 10–100 tokens | 71–135, median 100 | Partly |
| Input:output of 20:1 to 50:1 | Median 13:1 | Partly |
| Small model + schema + batching cuts cost >80% | −99.1%; the schema alone on the same model gives −81.5% | Supported |
| No accuracy loss | 27/42 → 40/42 | Supported |

### Points worth making in the post

- **The schema alone clears the deck's bar.** Haiku prose to Haiku JSON is −81.5% with no model change. The schema caps output at about 100 tokens where prose ran to 2,048.
- **Output is the bill.** In the prose rungs, output is 92–93% of cost. With the schema it is 28%.
- **The schema makes the prompt bigger and the bill smaller.** It adds about 600 prompt tokens per item and still cuts cost by four fifths.
- **Structure improved accuracy.** Prose answers were scored by generous text matching and still lost. The prose rungs produced no machine-readable output at all.
- **The naive cost is a lower bound.** 11 of 12 Sonnet prose runs and 8 of 12 Haiku prose runs hit the 2,048-token output cap.
- **Latency moved the same way.** On one ticket, Sonnet prose took 15.4 s, Haiku prose 9.7 s, Haiku JSON 1.9 s and Gemini Decision 0.9 s.
- **Scale illustration.** NovaMart's story has 5 million items a week. Extrapolating from these 12 items: about $110,000 a week on Sonnet prose, about $940 on Haiku JSON, about $470 through the Batch API.

### Caveats

- The input-to-output ratio came in below the deck's range because real schema output is about 100 tokens, not 10–50.
- The Gemini Decision 1 price was not checked against a published rate card.
- A decision model returns labels and probabilities only; it cannot rewrite text, so it cannot mask PII inline.

---

## Part 2: Generative synthesis and drafting

**One-line result:** a section template halved the cost of a draft and made it clearer and tighter, but a blind grader preferred the long draft every time, and the template itself pushed both models to invent owners and deadlines.

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

- **Invented deadlines.** The audit-report source asks for "time-bound" milestones but states no dates. Both templated drafts supplied their own: "Within 30 days", "Within 45 days", "Q1 2027".
- **Invented owners.** The safety-filing source attributes its commitments only to "Management". The templated drafts named teams such as "Customer Safety Operations".
- **Misassigned obligations.** In the partnership brief, pre-positioning stock is the brand's condition for a lower fee. Both templated drafts made it a NovaMart manager's task, and the Haiku draft attached a deadline that belongs to a different milestone.
- **The unbounded draft's one serious error** was of the same kind: a quarterly reporting commitment that is not in the source.

The template requires an owner and a time window for every action. Across the eight templated drafts, the grader flagged an owner or deadline the source does not support in 16 of 24 action items, 8 for each model, and 12 of those were serious. The one document whose source names its owners and dates had none. Where the source left a field open, the model filled it anyway.

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
- **A required field is an instruction to fill it.** The template demands an owner and a time window per action. When the source had none, both models invented one. This is a property of the template, not of the cheaper model: the Sonnet template made the same kind of error.
- **The long draft's extra numbers were honest.** Of 46 numbers not found in the source, 44 were correct arithmetic on source figures, and one was a rounding slip (3.195 described as "over 3.2×").
- **The small model added errors of its own.** The Haiku drafts had 10 serious errors against Sonnet's 6 on the same template, including obligations assigned to the wrong party.
- **Section-level review is its own saving.** Fixing one section costs half of a full redraft, and editing by hand costs nothing. Given where the errors sit, the action plan is the section to review.
- **Checking is cheap.** Grading all 12 drafts three times and comparing them head to head took 60 calls and about $5.
- **Speed.** On one brief, the unbounded draft took 39.5 s; the templated drafts took 12–14 s.

### Caveats

- One draft per version per document. The three grading passes measure the grader's consistency, not how much drafts vary.
- The grades come from a single model acting as grader. It was consistent (every grade within one point across passes; 11 of 12 pairings unchanged when the order was swapped), and its serious findings were verified by hand, but it is one grader.
- The grader can see that a draft is long or short, even though it does not know what wrote it.
- The unbounded version was asked for an exhaustive report, the templated ones for a tight one. Coverage and concision grades partly reflect those instructions.
- Only four documents.
- The obvious fix, letting the template say "not stated in the source", was not tested.

Full results: `analysis/cat2_quality.md`. Grader records: `backend/experiments/cat2_quality/judgements.jsonl`. Fact checklist: `backend/app/data/cat2_quality_keys.json`.

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

What the compacting version did with the 34 recall questions it missed, checked by hand:

- **33 declined.** It said the detail was not in its session memory and pointed the user to where to find it.
- **1 gave a labelled estimate** of a dollar amount, $1,780 against a true $1,775, worked out from a figure in the latest message.
- **None invented a value.**

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
- **It failed honestly.** Asked for something it had lost, the assistant said so and suggested where to look. It did not make values up. That makes the forgetting visible to the user, which is the safer failure.
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

**One-line result:** caching the whole corpus and trimming it with retrieval each cut cost roughly in half, and which one wins depends on how many questions share a cache.

### What the deck says

- **Shape:** high-context reasoning over large document sets, producing grounded answers.
- **Profile:** 15k–100k+ tokens in, 400–1,500 out, ratio of 20:1 to 100:1.
- **Lever:** pair hybrid retrieval (reranking and chunk filtering) with context caching on shared document repositories.
- **Use cases:** legal due diligence, grounding repositories, financial filing analysis.

### What was built

The NovaMart Supplier Deal-Room: seven contract and compliance documents split into 28 clauses, about 18.4k tokens. The documents include a wholesale master agreement, a peak-season service-level addendum, a data-protection schedule, safety and tax riders, a statutory audit extract and a side letter.

Two audit packs of four questions each, eight questions in total:

- **Legal and privacy pack.** Liability caps and carve-outs, peak-season overrides, an equity-stake condition, data localisation.
- **Finance and compliance pack.** Tax escrow, small-supplier payment rules, statutory audit notes, product safety.

Three rungs:

- **Naive.** All seven documents pasted as plain text on every question. No citations.
- **Cached corpus.** All seven documents sent as cached document blocks, with the API's native citations.
- **Hybrid retrieval.** Keyword search narrows 28 clauses to 10, Haiku reranks to the best 5, Sonnet answers with citations. Not cached.

### Results

| Rung | Cost per 1,000 questions (billed) | Steady state (warm) | vs naive (warm) | Prompt tokens per question |
|---|---:|---:|---:|---:|
| Full corpus, no cache, no citations | $46.29 | $46.29 | — | 18.4k |
| Full corpus, cached, native citations | $19.79 | $13.35 | −71% | 21.5k |
| Keyword search + Haiku rerank + citations | $24.33 | $24.33 | −47% | 5.7k–6.7k |

| Rung | Citations per answer (median) | Answers with no citation | Rerank recall |
|---|---:|---:|---:|
| Full corpus, no cache, no citations | 0 | 8 of 8 | — |
| Full corpus, cached, native citations | 10 | 0 of 8 | — |
| Keyword search + Haiku rerank + citations | 10 | 0 of 8 | 100% |

Per four-question audit, starting cold: naive $185, cached corpus $105, hybrid $97 per 1,000 audits.

### Deck claims against the data

| Claim | Measured | Verdict |
|---|---|---|
| Input 15k–100k+ tokens | 18.4k per question | Supported |
| Output 400–1,500 tokens | 798–1,039 | Supported |
| Ratio 20:1 to 100:1 | 19.4:1 | Partly |
| Pair hybrid retrieval with caching | Each lever works alone; they were never combined | Partly |

### Points worth making in the post

- **There is a break-even.** Caching the whole corpus beats hybrid retrieval once about 4.7 questions share one cache write. Below that, retrieval is cheaper.
- **So the answer depends on traffic shape.** One analyst asking four questions: retrieval wins narrowly ($97 against $105). A team asking questions all day against the same contracts: the cached corpus wins clearly ($13 against $24).
- **The cache has a short life.** The standard cache lasts five minutes between uses, so the warm figure needs steady traffic.
- **Retrieval cut prompt tokens by 81% and lost nothing.** The reranker kept every clause the answers needed across all eight questions.
- **Citations are the quality gain.** The naive rung produced no verifiable citations on any answer. Both governed rungs averaged ten per answer.
- **Citations cost tokens.** Document blocks with citations raise the prompt from 18.4k to 21.5k tokens per question. Caching more than pays for it.
- **The deck's "pair them" was not tested.** The hybrid rung sends no cache instruction, so the combined effect is unknown.

### Caveats

- The corpus is at the very bottom of the deck's band. At 100k tokens the break-even and the ratio would both shift.
- The billed figure for the cached rung is flattered by run order: the second audit pack found the cache already warm.
- Eight questions; answer correctness was not scored beyond citation counts and rerank recall.

---

## Part 5: Autonomous process orchestration

**One-line result:** a step budget, a cached manual and a deterministic policy check cut cost by 80%; routing routine work to a small model took it to 91%, with the correct result every time.

### What the deck says

- **Shape:** goal-directed workflows that chain planning, tool calls, validation and state updates.
- **Profile:** 25k–150k+ tokens in, 1,500–8,000 out, in a plan, call, verify, dispatch loop.
- **Lever:** max-step loop budgets, deterministic guardrails, and small-model routing for routine tool calls.
- **Use cases:** invoice reconciliation, claims adjudication, supply chain dispatch.

### What was built

The NovaMart three-way invoice reconciliation agent. It matches a vendor invoice against the purchase order and the warehouse goods receipt in a live SQLite database, then commits a payment voucher.

Three invoices of rising difficulty:

- **Invoice 1, routine.** All 1,000 units received; a tax filing is pending, so the payment is split into a release and an escrow.
- **Invoice 2, multi-factor dispute.** 15 dead-on-arrival units, one authorised price amendment, one unauthorised 5% price rise, and a disallowed freight charge.
- **Invoice 3, hard stop.** The tax registration was cancelled and 5,000 cartons never arrived. The correct outcome is zero payment.

Three rungs:

- **Unbounded loop.** Sonnet explores with `SELECT *` queries, re-reads an uncached procedures manual every step, and commits with no policy check.
- **Bounded.** A four-step budget, queries that fetch only the needed columns, a cached prefix of about 8.6k tokens built around the procedures manual, and a deterministic policy check before the voucher is committed.
- **Haiku first.** The same governed loop on Haiku, escalating to Sonnet only when the policy check flags a multi-factor dispute.

### Results

| Rung | Cost per 1,000 invoices (billed) | vs naive | Cold | Warm | Prompt tokens (median) |
|---|---:|---:|---:|---:|---:|
| Unbounded Sonnet loop | $191 | — | $191 | $191 | 115.2k |
| Four-step budget, cached manual, policy check | $37.47 | −80.4% | $51.24 | $30.58 | 41.5k |
| Haiku first, Sonnet on escalation | $16.99 | −91.1% | $17.65 | $9.72 | 41.9k |

| Rung | Correct voucher | Tool precision | Policy check passed | Steps per invoice | Escalations |
|---|---:|---:|---:|---|---:|
| Unbounded Sonnet loop | 3 of 3 | 17% | 0 of 3 | 7, 7, 3 | 0 |
| Four-step budget, cached manual, policy check | 3 of 3 | 100% | 3 of 3 | 4, 4, 4 | 0 |
| Haiku first, Sonnet on escalation | 3 of 3 | 100% | 3 of 3 | 4, 4, 4 | 1 |

### Deck claims against the data

| Claim | Measured | Verdict |
|---|---|---|
| Input 25k–150k+ tokens per task | Unbounded 29k–116k; bounded 40k–42k, mostly cache reads | Supported |
| Output 1,500–8,000 tokens per task | 1,183–2,356 | Partly |
| Step budgets, guardrails and small-model routing | −80%, then −91%; correct voucher 3 of 3 on every rung | Supported |

### Points worth making in the post

- **The naive agent got the right answer too.** All three rungs produced the correct voucher on all three invoices. The governed rungs are not more accurate; they are cheaper, predictable and checked.
- **The waste is in what the agent reads.** The unbounded loop's tool precision was 17%: five of every six tool calls fetched data it did not need. Fresh (uncached) prompt tokens fell from about 115,000 to 7,000–8,000 on the first two invoices.
- **The bill is almost all input.** Output is 9% of the unbounded loop's cost. Loops are an input problem.
- **Predictability is a result in itself.** The unbounded loop took 7, 7 and 3 steps. The governed loops took exactly 4 every time.
- **Escalation is where the tiered saving goes.** Haiku handled the routine invoice and the hard stop alone, at about 99% and 96% below naive. The dispute escalated to Sonnet and saved 81%.
- **A step budget can cost more on easy cases.** On the hard-stop invoice the unbounded loop quit after 3 steps, so the bounded rung saved only 32% there.
- **Right answer, thin evidence.** On the hard-stop invoice the unbounded loop reached the correct voucher having gathered a third of the expected evidence, and with no policy check before committing.

### Caveats

- Three invoices; Haiku escalated on one of them.
- Each rung changes the step cap, the caching and the query style together, so the 80% cannot be split between them.
- The per-invoice percentages in the bullets use cold-cache costs; the table's headline uses billed costs.
- Output sits at or below the deck's band because these are short loops of three to seven steps.

---

## Part 6: Multi-agent swarms and automated engineering

**One-line result:** isolating the agents, caching the shared prefix and tiering the models cut the cost of a verified fix about twelvefold; they made no difference to whether the fix was correct.

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
- **When everything passes, cost per verified outcome is just cost per run.** The metric earns its keep only when failure rates differ. Here its real contribution was different: computing it honestly is what exposed the flaws in the first version.
- **Verification needs verifying.** A static check that fails safe code is as misleading as a test that passes broken code.
- **The retry never fired.** In 45 gated runs the first patch always passed, so the check-and-retry loop cost nothing and its benefit is unmeasured.
- **The daily-volume claim in context.** One arm-1 run moves about 267k tokens, so the deck's 1.5M–10M per developer per day equals roughly 6–37 such runs. For the isolated swarms it would take roughly 25–160.

### Caveats

- **Ceiling effect.** Every arm scored 100%, so this experiment cannot detect a difference in correctness. Fifteen out of fifteen still leaves a 95% interval of 80–100%.
- **The tasks are small.** Each is a fix to one small module, made in five turns. Harder, multi-file work over more turns is where context pollution would be expected to matter, and it was not tested.
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
- Trace files: `backend/traces/` (953 files, 244 distinct canonical runs).
- Archetype 2 quality scoring: `analysis/cat2_quality.md`, with grader records in `backend/experiments/cat2_quality/judgements.jsonl`.
- Archetype 3 rerun: `analysis/cat3_quality_rerun.md`, with raw records in `backend/experiments/cat3_quality/runs.jsonl`.
- Archetype 6 rerun: `analysis/cat6_fair_rerun.md`, with raw records in `backend/experiments/cat6_fair_rerun/runs.jsonl`.
- The deck: `6 Key Production AI Archerypes.pdf`, one folder above the project.
