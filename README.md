# NovaMart AI Workload Archetypes Lab

Interactive FinOps & Architecture companion app mapping **Six Key AI Archetypes** onto a unified enterprise domain (**NovaMart Enterprise**: 12M SKUs · 45,000 sellers · \$2.4B GMV).

## Current Status
- **Phase 0 (Live):** Interactive Calibrated Matrix (`Autonomy Tier × Logarithmic Token Band`), Architectural FinOps Rules, Credit Shield (`Verified Replay ($0)` + `Passcode` + `Daily Cap` + `BYOK`), Cloud Run `Dockerfile` & deploy script.
- **Category 1 (Live — `/archetype/1`):** *Classification, Extraction & Routing* (`NovaMart Intake & Catalog Gate`), featuring:
  - **Sub-task 1A:** Omnichannel Support Triage & Deterministic Aadhaar/PII Regex Gate (`tkt-01`..`tkt-06`)
  - **Sub-task 1B:** Cold-Start Seller SKU Tagging & OCR Contradiction / Hazmat Gate (`sku-01`..`sku-06`)
  - **4-Rung Architecture Arena:**
    1. Rung 1: `claude-sonnet-5-5` (Unconstrained Prose Anti-Pattern)
    2. Rung 2: `claude-sonnet-5-5` + Strict JSON Schema
    3. Rung 3: `claude-haiku-5-5` + Strict JSON Schema (+ 50% Anthropic Message Batch comparator)
    4. Rung 4: `gemini-decision-1` (`v1beta` Decisions API, 0 output tokens) + `TypeSafe Jev` FinOps rate-card benchmark
  - **Two-Axis Ground-Truth Accuracy Evaluation & CFO Scale Simulator:** 42 field checks across 12 items + 5-tier CFO cost projection.
- **Category 2 (Live — `/archetype/2`):** *Generative Synthesis & Drafting* (`NovaMart Executive & Compliance Readout Studio`), featuring:
  - **Sub-task 2A:** Weekly Marketplace Executive Performance Readout (`brief-01`, `brief-02`)
  - **Sub-task 2B:** Hazmat / Regulatory Seller Escalation Dossier (`reg-01`, `reg-02`)
  - **3-Rung 5x Output-Tax Arena:**
    1. Rung 1: `claude-sonnet-5-5` Unbounded Full-Doc Rewrite (`max_tokens=8000`)
    2. Rung 2: `claude-sonnet-5-5` Structured Section Caps (`max_tokens=3000`, 4-section JSON schema with word budgets)
    3. Rung 3: `claude-haiku-5-5` on the same section template (+ optional Sonnet surgical section regen)
  - **Blind quality grading (`backend/experiments/cat2_quality/`):** the 12 stored drafts (3 rungs × 4 documents, one draft each) graded by `claude-opus-5-5` — not one of the models under test — on a 1–5 rubric (3 passes per draft) and in 24 position-swapped head-to-head comparisons, plus a fixed fact key. Every rung keeps all `32/32` core facts, and the templates read clearer and more concise (clarity `4.00` / `4.92` / `4.42`, concision `2.83` / `4.17` / `4.08`), but the cost cut is not free: accuracy `3.92` / `3.08` / `2.58`, coverage `4.92` / `4.00` / `3.50`, serious errors `1` / `6` / `10`, and the unbounded draft is preferred in `16/16` comparisons against the templated drafts (Sonnet template beats Haiku template `7/8`). The template requires an owner and a time window for every action item; the grader flagged an owner or deadline the source does not support in `8` of `12` action items on each templated rung (none on `brief-01`, whose source names owners and dates). Cost per 1k drafts: `$58.92` / `$27.25` / `$1.39`. One judge model and one draft per cell, so treat per-document differences as indicative.
  - **Measured fix, shown beside the app (`backend/experiments/cat2_not_stated/`):** the same template plus one sentence letting it write "Not stated in source" for an owner or time window the source does not give (48 fresh drafts: 3 per document × model × template, graded blind, one pass). Serious errors per draft fell from `1.25` / `2.25` to `0.00` / `0.25` (Sonnet / Haiku), accuracy rose from `3.25` / `2.67` to `4.17` / `3.83`, and no owner or time window was left that the source does not support (was `22` / `26` owners and `13` / `19` windows of `36`); it beat the original template in `47` of `48` comparisons. But an honest blank is graded less actionable (`3.67` / `3.25` → `3.08` / `2.67`), Haiku wrote "not stated" for all `36` owners, including ones the source names, and the long unbounded draft is still preferred in `15` of `16` comparisons. The app keeps the original template.
  - **Interactive HITL Section Studio:** Section `Lock`, `$0` inline edit, and single-section surgical regeneration without paying full-document regeneration tax.
- **Category 3 (Live — `/archetype/3`):** *Multi-Turn Conversational Assistants* (`NovaMart IT & HR Unified Service Desk`), featuring:
  - **10-Turn Log-Heavy Dialogues (`desk-01`, `desk-02`):** Employee troubleshooting sessions on `claude-sonnet-5-5` grounded in an `~9,860`-token IT & HR Policy Handbook prefix (measured cache write).
  - **3-Rung Session Cost Arena (Same Model, Pure Context Strategy):**
    1. Rung 1: Naive Full History (re-pays uncached system handbook + growing transcript every turn)
    2. Rung 2: Ephemeral Prefix Context Caching (`cache_control: {"type": "ephemeral"}`, `-95%` cache read rate after turn 1)
    3. Rung 3: Prefix Caching + Sliding-Window Memory Summarization (compacts once more than `4` turns are verbatim, keeping the latest turn raw + compacted structured memory; `-46.7%` billed / `-52.6%` warm session cost vs Rung 1 in the quality rerun, summarizer calls included)
  - **Quality rerun (`backend/experiments/cat3_quality/`):** 18 live runs (3 rungs × 2 sessions × 3 repeats) scored against a fixed answer key. Answers on turns 1–9 stay grounded on every rung (`99.0%` / `98.1%` / `99.0%` of key facts), but compaction is not free: the turn-10 summary keeps `47.1%` of turn 1–3 details vs `76.5%` with cached full history, and the compacted rung answers `2/36` recall questions about earlier turns vs `36/36` for both full-history rungs. Cost per 1k sessions (billed): `$398.68` / `$239.66` / `$212.45`. The golden replays are repeat 0 of every rung (fixed mapping, not selected by outcome) and include the recall probes.
  - **Turn-by-Turn Cost Growth Chart & Interactive Context Window X-Ray:** Inspect Layer 1 (Cached Handbook Prefix), Layer 2 (Compacted Memory JSON), and Layer 3 (Raw Recent Turns).
- **Category 4 (Live — `/archetype/4`):** *Multi-Doc RAG & Deep Ingestion* (`NovaMart Supplier Deal-Room & Statutory Due Diligence`), featuring:
  - **7-Document Indian Deal Room (`28` Clauses, `~16k–21k` tokens):** Wholesale MSA (`MSA-NM-DSA-2026`), Diwali Peak SLA Override (`SLA-PEAK-2026`), DPDP Act 2023 & CERT-In IoT DPA (`DPA-DPDP-2026`), BIS CRS / CPCB EPR / UN 3480 Safety (`REG-BIS-EPR-2026`), CGST Sec 16(2)(aa) / MSMED 45-Day Rider (`TAX-GST-ITC-2026`), MCA Form AOC-4 / CARO 2020 / Form CHG-1 Audit Extract (`MCA-AOC4-FY26`), and Side Letter #2 (`SL-2026-09`).
  - **3-Rung Deal-Room FinOps Arena:**
    1. Rung 1: Naive Full-Corpus Stuffing (`claude-sonnet-5-5`, uncached plain text, no citations requested)
    2. Rung 2: DocumentBlock Prefix Caching (the first question writes the cache at `$2.50/M`, later questions read it at `$0.10/M`) + Native Citations (each points at a contract span; it shows where a claim came from, not that it is right)
    3. Rung 3: Hybrid Okapi BM25 (`28 → 10`) + `claude-haiku-5-5` Cross-Chunk Rerank (`10 → 5`) + Native Citations
  - **Quality rerun (`backend/experiments/cat4_quality/`):** `192` answers (4 versions × 2 corpus sizes × 3 sessions of 8 questions; the 4th version, a small model picking clauses from the cached corpus, is measured only in the rerun) scored against a fixed answer key and graded blind once by `claude-opus-5-5`. On the 7-document deal room, grader correctness is `4.50` / `4.96` / `4.71` (Rungs 1–3) with serious errors in `1` / `0` / `0` of 24 answers. With two other suppliers' look-alike contracts added (21 documents), retrieval keeps `77/90` needed clauses and passes `25/120` other-supplier clauses to the answering model, and serious errors rise to `8/24` (correctness `3.96`) vs `0/24` for the cached whole corpus. Cost per question in an 8-question session from a cold cache: `$0.0459` / `$0.0253` / `$0.0247` (7 docs), `$0.1173` / `$0.0379` / `$0.0278` (21 docs); the cached whole corpus becomes cheaper than retrieval from question `9` / `18` on one cache write. The golden replays are repeat 0, 7-document size, of the three app rungs (fixed mapping, not selected by outcome); one grading pass, so treat small differences as indicative.
  - **Interactive Clause Citation Verifier & 3-Stage Retrieval Funnel X-Ray:** Click inline citation pills (`[1]`, `[2]`) to highlight the cited span inside searchable `<details>` contracts, plus an answer-quality panel, a Query-Count Crossover Chart (measured costs, straight-line beyond the questions asked) and a CFO Audit Scale Simulator (linear projection of measured cost).
- **Category 5 (Live — `/archetype/5`):** *Autonomous Process Orchestration* (`NovaMart 3-Way Invoice Reconciliation Agent`), featuring:
  - **Live In-Memory SQLite ERP (8 Tables):** `vendors`, `purchase_orders`, `po_lines`, `goods_receipts`, `vendor_invoices`, `invoice_lines`, `contract_amendments`, `fc_dock_logs`, and committed `reconciliation_vouchers`.
  - **3-Rung Process Arena (`inv-01` GST Escrow Split, `inv-02` DOA + Amendment Dispute, `inv-03` Cancelled IRN Hard Block):**
    1. Rung 1: Free-Choice Raw-Table Loop (`claude-sonnet-5-5`, the model picks its own raw `SELECT *` lookups, several per turn allowed; uncached policy manual, no policy gate, 12-turn safety cap)
    2. Rung 2: One Narrow Query + Cached Policy Manual + Deterministic Policy Gate `AP-POL-GATE-01` (the commit tool refuses until the gate has computed the voucher; 4-step budget)
    3. Rung 3: Rung 2 on `claude-haiku-5-5`, switching to `claude-sonnet-5-5` when the gate flags escalation (it flags every debit note)
  - **Six-version ablation (`backend/experiments/cat5_ablation/`):** 216 live runs (6 versions × 12 invoices × 3 runs, every run kept, vouchers scored field by field against a hand-derived answer) add the levers one at a time. Every version got 32–33 of 33 vouchers exactly right on the 11 invoices where the gate agrees with the manual. Cost per 1,000 invoices (billed): raw tables `$153.72`, + cached manual `$110.99`, + one narrow query `$43.10`, + policy gate `$50.84` (Rung 2), narrow query on Haiku `$2.40`, Haiku + gate + escalation `$22.62` (Rung 3). The narrow query (`-61%`) and the model choice (`-94%`) carry the saving; the gate added a turn and `+18%` cost with no measured accuracy gain, and on `inv-06`, where the gate's 1.5% price band contradicts manual 2.1, all 6 gated runs committed the gate's wrong figures while all 12 runs without it matched the manual. No run hit a step cap. The golden replays are repeat 0 of the three versions the app runs (fixed mapping, not selected by outcome); the old scripted Rung 1 captures are kept in `backend/replays/cat5_ablation_summary.json` as a baseline.
  - **Portfolio Scorecard, Experiment Panel & Interactive Trajectory / SQL Inspector:** Voucher accuracy on the recorded runs, evidence recall, tool precision, turns used against each rung's cap, real stop reasons per turn, live executed SQL, and the six-version results (what each step saved, the policy-gate disagreement, scripted vs free-choice Rung 1, raw-table lookups chosen).
- **Category 6 (Live — `/archetype/6`):** *Multi-Agent Swarms & Auto Eng* (`NovaMart Checkout & Pricing CI Self-Healing Swarm`), featuring:
  - **3 Engineering Swarm Incidents (`inc-01` Checkout GST Sec 15(3), `inc-02` NPCI UPI Auth & DPDP Act 2023, `inc-03` Multi-FC Split-Cart Concurrency):**
  - **Shared `~9.3k`-Token Monorepo Prefix (measured cache write) & `PR-SANDBOX-GATE-01`:** Isolated Python `-I` subprocess verifier running `4` CI unit checks + `4` adversarial/concurrency checks + `2` static AST security gates (`10` checks per incident) alongside unified diffs.
  - **3-Rung Swarm Arena Graded by Cost per Verified Outcome (CpO):**
    1. Rung 1: Unisolated Shared-Bus Broadcast Swarm (`claude-sonnet-5-5`, uncached omnibus history + noisy OTel spans, `~247k` prompt tok/run measured; no sandbox gate before sign-off)
    2. Rung 2: Isolated Sub-Agents + Cached Repo Prefix (`-95%` reads) + Bounded 1-Retry `PR-SANDBOX-GATE-01`
    3. Rung 3: Tier-Routed Haiku (`claude-haiku-5-5` Orchestrator, CI Triager, Security Critic & Merge Gate) + Sonnet (`claude-sonnet-5-5` Patch Author)
  - **Fair rerun & replays:** `backend/experiments/cat6_fair_rerun/` holds 60 live runs (4 arms × 3 incidents × 5 repeats, equal output caps, per-run cold caches, no outcome-based selection). Every arm verified 15/15 with the current sandbox (3 shared-bus runs were first scored 9/10 by an AST-SEC-01 false positive, since fixed), so the rungs differ in cost, not in correctness on these incidents; the golden replays are repeat 0 of the matching arms, re-scored with the current sandbox.
  - **Org Cost Simulator:** Projects per-developer daily tokens and monthly org cost from each rung's measured tokens and cost per run (the deck's `1.5M–10M+ tok/day` band is not measured here).

## Local Development

### 1. Backend (FastAPI + Python 3.12)
```bash
cp .env.example .env
# Populate ANTHROPIC_API_KEY and GEMINI_API_KEY in .env only if you want Live API Mode.
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
# Optional: re-capture live traces per archetype
.venv/bin/python scripts/capture_live_replays.py
.venv/bin/python scripts/capture_cat2_replays.py
.venv/bin/python scripts/capture_cat3_replays.py
.venv/bin/python scripts/capture_cat4_replays.py
.venv/bin/python scripts/capture_cat5_replays.py
.venv/bin/python scripts/capture_cat6_replays.py
```

### 4. Partitioned Trace Storage & Local Streamlit Trace Explorer
Every request (`live` and `replay`) is automatically saved under `backend/traces/` partitioned by:
```text
backend/traces/category=<category>/use_case=<use_case>/model=<model>/pattern=<pattern>/<timestamp>_<item>_<id>.json
```
To seed all `244` pre-captured traces (`48` Cat 1 + `44` Cat 2 + `102` Cat 3 + `32` Cat 4 + `9` Cat 5 + `9` Cat 6; Cat 3 includes the recall-probe calls) from golden replays and launch the dedicated **Streamlit Trace Explorer**:
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
