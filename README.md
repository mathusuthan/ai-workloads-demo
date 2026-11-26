# NovaMart AI Workload Archetypes Lab

Interactive FinOps & Architecture companion app mapping **Six Key AI Archetypes** onto a unified enterprise domain (**NovaMart Enterprise**: 12M SKUs · 45,000 sellers · \$2.4B GMV).

## Current Status
- **Phase 0 (Live):** Interactive Calibrated Matrix (`Autonomy Tier × Logarithmic Token Band`), Architectural FinOps Rules, Credit Shield (`Verified Replay ($0)` + `Passcode` + `Daily Cap` + `BYOK`), Cloud Run `Dockerfile` & deploy script.
- **Category 1 (Live — `/archetype/1`):** *Classification, Extraction & Routing* (`NovaMart Intake & Catalog Gate`), featuring:
  - **Sub-task 1A:** Omnichannel Support Triage & Deterministic Aadhaar/PII Regex Gate (`tkt-01`..`tkt-06`)
  - **Sub-task 1B:** Cold-Start Seller SKU Tagging & OCR Contradiction / Hazmat Gate (`sku-01`..`sku-06`)
  - **Without vs With the Lever, on Sonnet 5.5 and Haiku 5.5 (4 rungs):**
    1. Without: four-part write-up, free text (`claude-sonnet-5-5` and `claude-haiku-5-5`, `max_tokens=8192`; the prompt never lists the allowed labels)
    2. With: classification with a strict JSON schema (`claude-sonnet-5-5` and `claude-haiku-5-5`, `max_tokens=512`; the 50% Message Batch price is shown as computed, not run)
  - **Ground-truth accuracy & CFO Scale Simulator:** 42 field checks across 12 items (6 presets + 6 shorter batch items) and a per-rung cost projection with the computed Batch API price on the two "with" rows. Replayed write-ups are scored from a stored blind reader-model extraction; a live write-up is shown as not scored, because the app does not call a reader model.
  - **Experiment (`backend/experiments/cat1_ablation/`):** 144 live runs (4 cells × 12 items × 3 runs, every run kept; free text read by a blind reader model, `claude-opus-5-5`). Fields correct of 126, items fully correct of 36 and cost per 1,000 items: without, Sonnet `69` (usable as a classification) `6` `$29.50`, Haiku `69` `3` `$1.25`; with, Sonnet `126` `36` `$3.77` (batch `$1.88`, computed), Haiku `120` `33` `$0.188` (batch `$0.094`, computed). Haiku's 6 missed fields are all on `tkt-01` and `tkt-02`. No run reached its token cap. The app's golden replays are repeat 0 of each cell.
- **Category 2 (Live — `/archetype/2`):** *Generative Synthesis & Drafting* (`NovaMart Executive & Compliance Readout Studio`), featuring:
  - **Sub-task 2A:** Weekly Marketplace Executive Performance Readout (`brief-01`, `brief-02`)
  - **Sub-task 2B:** Hazmat / Regulatory Seller Escalation Dossier (`reg-01`, `reg-02`)
  - **Without vs With the Lever, on Sonnet 5.5 and Haiku 5.5 (4 rungs):**
    1. Without: unbounded long-form draft (`claude-sonnet-5-5` and `claude-haiku-5-5`, `max_tokens=8000`)
    2. With: section template with length caps (`claude-sonnet-5-5` and `claude-haiku-5-5`, `max_tokens=3000`, 4-section JSON schema with word budgets; an action item's owner or time window is filled only when the source states it, otherwise `Not stated in source`)
  - **Experiment (`backend/experiments/cat2_not_stated/`):** 3 drafts per document and model per cell (12 per cell), graded blind by `claude-opus-5-5` (not one of the models under test; one rubric pass per draft, 1–5) plus a fixed fact key. With the template: Sonnet `$26.82` per 1,000 documents, accuracy `4.17`, coverage `3.42`, `0` serious errors in 12 drafts, core facts `94/96`; Haiku `$1.36`, accuracy `3.83`, coverage `3.58`, `3` serious errors, core facts `92/96`. Unbounded: Sonnet `$57.43`, accuracy `3.92`, coverage `5.00`, `5` serious errors, core facts `95/96`; Haiku `$3.11`, accuracy `2.92`, coverage `4.33`, `22` serious errors, core facts `94/96`. Matched head-to-head (template vs unbounded on the same document, model and repeat, both orders, 48 calls): template preferred in `21`, unbounded in `27` (Sonnet `6`–`18`, Haiku `15`–`9`).
  - **Interactive HITL Section Studio:** Section `Lock`, `$0` inline edit, and single-section surgical regeneration without paying full-document regeneration tax.
- **Category 3 (Live — `/archetype/3`):** *Multi-Turn Conversational Assistants* (`NovaMart IT & HR Unified Service Desk`), featuring:
  - **10-Turn Log-Heavy Dialogues (`desk-01`, `desk-02`):** Employee troubleshooting sessions on `claude-sonnet-5-5` grounded in an `~9,860`-token IT & HR Policy Handbook prefix (measured cache write).
  - **Session Cost: Without vs With the Lever (Same Model, Pure Context Strategy):**
    1. Without: Full History, No Cache (re-pays the uncached handbook + growing transcript every turn)
    2. With: Cached Prefix + Sliding-Window Summaries (`cache_control: {"type": "ephemeral"}` on the handbook; compacts once more than `4` turns are verbatim, keeping the latest turn raw + compacted structured memory; `-46.7%` billed / `-52.6%` warm session cost, summarizer calls included)
  - **Quality rerun (`backend/experiments/cat3_quality/`):** 12 live runs (2 versions × 2 sessions × 3 repeats) scored against a fixed answer key. Answers on turns 1–9 stay grounded in both versions (`205/207` key facts each), but compaction is not free: the turn-10 summary keeps `24/51` turn 1–3 details with the lever vs `37/51` without, and the version with the lever answers `2/36` recall questions about earlier turns vs `36/36` without. Cost per 1k sessions (billed): `$398.68` without, `$212.45` with. The golden replays are repeat 0 of both versions (fixed mapping, not selected by outcome) and include the recall probes. Other levers tried (prefix caching alone) are recorded in `analysis/experiments_log.md` (Category 3), not shown in the app.
  - **Turn-by-Turn Cost Growth Chart & Interactive Context Window X-Ray:** Inspect Layer 1 (Cached Handbook Prefix), Layer 2 (Compacted Memory JSON), and Layer 3 (Raw Recent Turns).
- **Category 4 (Live — `/archetype/4`):** *Multi-Doc RAG & Deep Ingestion* (`NovaMart Supplier Deal-Room & Statutory Due Diligence`), featuring:
  - **7-Document Indian Deal Room (`28` Clauses, `~16k–21k` tokens):** Wholesale MSA (`MSA-NM-DSA-2026`), Diwali Peak SLA Override (`SLA-PEAK-2026`), DPDP Act 2023 & CERT-In IoT DPA (`DPA-DPDP-2026`), BIS CRS / CPCB EPR / UN 3480 Safety (`REG-BIS-EPR-2026`), CGST Sec 16(2)(aa) / MSMED 45-Day Rider (`TAX-GST-ITC-2026`), MCA Form AOC-4 / CARO 2020 / Form CHG-1 Audit Extract (`MCA-AOC4-FY26`), and Side Letter #2 (`SL-2026-09`).
  - **Deal-Room FinOps: Without vs With the Lever:**
    1. Without: Full Corpus, No Cache, No Citations (`claude-sonnet-5-5`, uncached plain text)
    2. With: Retrieval Paired with Caching + Citations (`claude-haiku-5-5` reads all `28` clauses from one cached block — written by the first question, read by later ones — and picks the `5` it judges most relevant; `claude-sonnet-5-5` answers over those 5 with native citations, and says when a term is not in the text provided. Each citation points at a contract span; it shows where a claim came from, not that it is right)
  - **Quality rerun (`backend/experiments/cat4_quality/`):** `96` answers (2 versions × 2 corpus sizes × 3 sessions of 8 questions) scored against a fixed answer key and graded blind once by `claude-opus-5-5`. On the 7-document deal room, grader correctness is `4.50` without vs `4.75` with, serious errors in `1` vs `0` of 24 answers, key facts `156/159` vs `153/159`. With two other suppliers' look-alike contracts added (21 documents): correctness `4.50` vs `4.54`, serious errors `3/24` vs `2/24`, key facts `150/159` vs `154/159`; Haiku's picks held `89/90` needed clauses at both sizes and no other supplier's clause. Cost per question billed in an 8-question session: `$0.0459` vs `$0.0230` (7 docs), `$0.1173` vs `$0.0250` (21 docs). The golden replays are repeat 0, 7-document size, of both versions (fixed mapping, not selected by outcome); one grading pass, so treat small differences as indicative. Other levers tried (cached full corpus with citations; retrieval + rerank without a cache) and the earlier designs are recorded in `analysis/experiments_log.md` (Category 4), not shown in the app.
  - **Interactive Clause Citation Verifier & Clause-Pick X-Ray:** Click inline citation pills (`[1]`, `[2]`) to highlight the cited span inside searchable `<details>` contracts, see the 5 clauses Haiku picked, plus an answer-quality panel (corpus 1× and 3× side by side) and a CFO Audit Scale Simulator (linear projection of measured cost).
- **Category 5 (Live — `/archetype/5`):** *Autonomous Process Orchestration* (`NovaMart 3-Way Invoice Reconciliation Agent`), featuring:
  - **Live In-Memory SQLite ERP (8 Tables):** `vendors`, `purchase_orders`, `po_lines`, `goods_receipts`, `vendor_invoices`, `invoice_lines`, `contract_amendments`, `fc_dock_logs`, and committed `reconciliation_vouchers`.
  - **4-Version Process Arena (`inv-01` GST Escrow Split, `inv-02` DOA + Amendment Dispute, `inv-03` Cancelled IRN Hard Block), shown in this order (without the lever in red, with the lever in green):**
    1. Version 1 — without the lever, Sonnet: free-choice raw-table loop (`claude-sonnet-5-5`, the model picks its own raw `SELECT *` lookups, several per turn allowed; uncached policy manual, no policy tool, 12-turn safety cap)
    2. Version 2 — without the lever, Haiku: version 1's raw tools, prompt, 12-turn safety cap and uncached manual on `claude-haiku-5-5` (thinking disabled, as the app configures Haiku). With no policy tool nothing can flag escalation, so this version has no escalation path to Sonnet
    3. Version 3 — with the lever, Sonnet: 4-step budget + deterministic policy tool `AP-POL-GATE-01` (the commit tool refuses until the tool has computed the voucher); this design also uses one narrow query in place of the raw tables and sends the policy manual as a cached prefix (`claude-sonnet-5-5`)
    4. Version 4 — with the lever, Haiku-first: version 3 on `claude-haiku-5-5`, switching to `claude-sonnet-5-5` when the policy tool flags a multi-factor commercial dispute (manual 6.2: two or more of partial DOA or short receipt, a signed contract amendment, an unauthorized line price rise, disallowed freight)
  - **One design with and without the deck's lever, on Sonnet and Haiku (`backend/experiments/cat5_ablation/`):** a 2×2 of 12 invoices × 3 runs per cell, vouchers scored field by field against a hand-derived answer. Without the lever on Sonnet 36 of 36 exact vouchers, `$153.41` per 1,000 invoices cold and warm, 3.9 model turns; without the lever on Haiku 36 of 36, `$7.89` cold and warm, 3.9 turns; with the lever on Sonnet 36 of 36, `$51.22` cold / `$30.49` warm, 4.0 turns; with the lever, Haiku-first 36 of 36, `$10.42` cold / `$5.94` warm, 4.0 turns, switching to Sonnet on 6 of 36 runs (`inv-02`, `inv-12`, the multi-factor disputes). No run hit a step cap. The golden replays are repeat 0 of each cell on `inv-01..03` (fixed mapping, not selected by outcome).
  - **Portfolio Scorecard, Experiment Panel & Interactive Trajectory / SQL Inspector:** Voucher accuracy on the recorded runs, evidence recall, tool precision, turns used against each version's cap, real stop reasons per turn, live executed SQL, and the with/without table (correct vouchers, cost per 1,000 invoices cold and warm, model turns, escalations).
- **Category 6 (Live — `/archetype/6`):** *Multi-Agent Swarms & Auto Eng* (`NovaMart Checkout & Pricing CI Self-Healing Swarm`), featuring:
  - **3 Engineering Swarm Incidents (`inc-01` Checkout GST Sec 15(3), `inc-02` NPCI UPI Auth & DPDP Act 2023, `inc-03` Multi-FC Split-Cart Concurrency):**
  - **Shared `~9.3k`-Token Monorepo Prefix (measured cache write) & `PR-SANDBOX-GATE-01`:** Isolated Python `-I` subprocess verifier running `4` CI unit checks + `4` adversarial/concurrency checks + `2` static AST security gates (`10` checks per incident) alongside unified diffs.
  - **One swarm with and without the deck's lever (isolated sub-agent contexts + cached repo prefix), graded by Cost per Verified Outcome (CpO).** Every version has the same role instructions, output caps and `PR-SANDBOX-GATE-01` with one retry; the screen shows the two versions without the lever first (red), then the two with it (green):
    1. Version 1 — without the lever: one shared growing thread (`claude-sonnet-5-5`, uncached repo manual + unrelated services and OTel spans, `~214k` prompt tok/run measured)
    2. Version 2 — without the lever, Haiku agents + Sonnet patch author: version 1's shared thread, prompts, caps and gate with version 4's model assignment (fair-rerun arm `shared_bus_tiered_gate`)
    3. Version 3 — with the lever: isolated sub-agents + cached repo prefix (`claude-sonnet-5-5`)
    4. Version 4 — with the lever, Haiku agents (`claude-haiku-5-5` Orchestrator, CI Triager, Security Critic & Merge Gate) + Sonnet patch author (`claude-sonnet-5-5`)
  - **Fair rerun & replays:** `backend/experiments/cat6_fair_rerun/runs.jsonl` holds 60 live runs (4 versions × 3 incidents × 5 repeats, per-run cold caches, every run kept). Every version verified 15/15 (150/150 sandbox checks), so on these single-file incidents they differ in tokens, cost and model time, not in correctness. Cost per verified outcome, cold / warm: $0.469 / $0.469 without the lever on Sonnet, $0.125 / $0.125 without it on Haiku agents + Sonnet patch author, $0.100 / $0.078 with it on Sonnet, $0.056 / $0.033 with it on Haiku agents + Sonnet patch author. The golden replays are repeat 0 of each version. Results: `analysis/cat6_fair_rerun.md`.
  - **Org Cost Simulator:** Projects per-developer daily tokens and monthly org cost from each version's measured tokens and cost per run (the deck's `1.5M–10M+ tok/day` band is not measured here).

## Local Development

### 1. Backend (FastAPI + Python 3.12)
```bash
cp .env.example .env
# Populate ANTHROPIC_API_KEY in .env only if you want Live API Mode.
# Without any keys, Verified Replay Mode ($0) serves pre-captured golden replays immediately.

cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

### 2. Frontend (React + TypeScript + Vite + Tailwind)
```bash
cd frontend
npm install
npm run build   # Builds static bundle served directly by FastAPI at http://127.0.0.1:8000
# Or for hot reload dev:
npm run dev     # http://127.0.0.1:5173 (proxies /api -> 8000)
```

### 3. Tests & Refreshing Live Golden Replays
```bash
cd backend
.venv/bin/pytest -v
# Rebuild golden replays from the recorded experiments (no API calls)
.venv/bin/python scripts/build_cat1_golden_from_ablation.py
.venv/bin/python scripts/build_cat2_golden_from_experiment.py
# Optional: re-capture live traces per archetype
.venv/bin/python scripts/capture_cat3_replays.py
.venv/bin/python scripts/capture_cat4_replays.py
.venv/bin/python scripts/capture_cat5_replays.py
.venv/bin/python scripts/capture_cat6_replays.py
```

### 4. Partitioned Trace Storage & Local Streamlit Trace Explorer
Every live request is saved under `backend/traces/` (replay requests are not written, so the store holds only the seeded golden-replay runs and real live runs; set `NOVAMART_RECORD_REPLAY_TRACES=1` to record replays too). Backups go to `backend/traces/_backups/`, which the viewer and the report never read. Partitioned by:
```text
backend/traces/category=<category>/use_case=<use_case>/model=<model>/pattern=<pattern>/<timestamp>_<item>_<id>.json
```
To seed all `214` pre-captured traces (`48` Cat 1 + `48` Cat 2 + `70` Cat 3 + `24` Cat 4 + `12` Cat 5 + `12` Cat 6; Cat 3 includes the recall-probe calls) from golden replays and launch the dedicated **Streamlit Trace Explorer**:
```bash
backend/.venv/bin/pip install -r backend/requirements-viewer.txt   # one-time local install into backend/.venv
backend/.venv/bin/python backend/scripts/seed_traces_from_replays.py   # --cat3-only / --cat4-only / --cat5-only / --cat6-only append one category without clearing others
chmod +x run_trace_viewer.sh
./run_trace_viewer.sh   # opens http://127.0.0.1:8501
```

## Deploy to GCP Cloud Run
```bash
chmod +x deploy_cloud_run.sh
PROJECT_ID=my-gcp-project AUTHOR_PASSCODE=my-secret ./deploy_cloud_run.sh
```
