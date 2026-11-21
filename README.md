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
    2. Rung 2: `claude-sonnet-5-5` Structured Section Caps (`max_tokens=1400`)
    3. Rung 3: `claude-haiku-5-5` First Draft + Sonnet Surgical Regen
  - **Interactive HITL Section Studio:** Section `Lock`, `$0` inline edit, and single-section surgical regeneration without paying full-document regeneration tax.
- **Category 3 (Live — `/archetype/3`):** *Multi-Turn Conversational Assistants* (`NovaMart IT & HR Unified Service Desk`), featuring:
  - **10-Turn Log-Heavy Dialogues (`desk-01`, `desk-02`):** Employee troubleshooting sessions on `claude-sonnet-5-5` grounded in an `~9,830`-token IT & HR Policy Handbook prefix.
  - **3-Rung Session Cost Arena (Same Model, Pure Context Strategy):**
    1. Rung 1: Naive Full History (re-pays uncached system handbook + growing transcript every turn)
    2. Rung 2: Ephemeral Prefix Context Caching (`cache_control: {"type": "ephemeral"}`, `-90%` cache read rate after turn 1)
    3. Rung 3: Prefix Caching + Sliding-Window Memory Summarization (`4` raw recent turns + compacted structured memory, `-50%` to `-55%` session cost)
  - **Turn-by-Turn Cost Growth Chart & Interactive Context Window X-Ray:** Inspect Layer 1 (Cached Handbook Prefix), Layer 2 (Compacted Memory JSON), and Layer 3 (Raw Recent Turns).
- **Category 4 (Live — `/archetype/4`):** *Multi-Doc RAG & Deep Ingestion* (`NovaMart Supplier Deal-Room & Statutory Due Diligence`), featuring:
  - **7-Document Indian Deal Room (`28` Clauses, `~16k–21k` tokens):** Wholesale MSA (`MSA-NM-DSA-2026`), Diwali Peak SLA Override (`SLA-PEAK-2026`), DPDP Act 2023 & CERT-In IoT DPA (`DPA-DPDP-2026`), BIS CRS / CPCB EPR / UN 3480 Safety (`REG-BIS-EPR-2026`), CGST Sec 16(2)(aa) / MSMED 45-Day Rider (`TAX-GST-ITC-2026`), MCA Form AOC-4 / CARO 2020 / Form CHG-1 Audit Extract (`MCA-AOC4-FY26`), and Side Letter #2 (`SL-2026-09`).
  - **3-Rung Deal-Room FinOps Arena:**
    1. Rung 1: Naive Full-Corpus Stuffing (`claude-sonnet-5-5`, uncached plain text, `0` citations)
    2. Rung 2: DocumentBlock Prefix Caching (`-90%` cache reads) + Native Anthropic Character-Exact Citations
    3. Rung 3: Hybrid Okapi BM25 (`28 → 10`) + `claude-haiku-5-5` Cross-Chunk Rerank (`10 → 5`) + Native Citations
  - **Interactive Clause Citation Verifier & 3-Stage Retrieval Funnel X-Ray:** Click inline citation pills (`[1]`, `[2]`) to highlight exact character-offset spans inside searchable `<details>` contracts, plus Query-Count Crossover Chart & CFO Audit Scale Simulator.
- **Category 5 (Live — `/archetype/5`):** *Autonomous Process Orchestration* (`NovaMart 3-Way Invoice Reconciliation Agent`), featuring:
  - **Live In-Memory SQLite ERP (8 Tables):** `vendors`, `purchase_orders`, `po_lines`, `goods_receipts`, `vendor_invoices`, `invoice_lines`, `contract_amendments`, `fc_dock_logs`, and committed `reconciliation_vouchers`.
  - **3-Rung Process Governance Arena (`inv-01` GST Escrow Split, `inv-02` DOA + Amendment Dispute, `inv-03` Cancelled IRN Hard Block):**
    1. Rung 1: Unbounded Exploratory `SELECT *` ReAct Loop (`claude-sonnet-5-5`, uncached SOP manual, no gate pre-check)
    2. Rung 2: Bounded 4-Step Budget + Projection JOINs + Cached SOP Manual (`-90%` reads) + Deterministic `AP-POL-GATE-01`
    3. Rung 3: Haiku-First Tiered Agent (`claude-haiku-5-5`, escalating to Sonnet 5.5 solely when `AP-POL-GATE-01` flags multi-factor commercial disputes — `-81%` to `-99%` cost)
  - **3-Invoice Portfolio Evaluation Scorecard & Interactive Trajectory / SQL Inspector:** Tracks Rupee Accuracy (`15/15`), Evidence Recall %, Tool Precision %, `<progress>` Loop Budgets, and live executed SQL statements.
- **Category 6 (Live — `/archetype/6`):** *Multi-Agent Swarms & Auto Eng* (`NovaMart Checkout & Pricing CI Self-Healing Swarm`), featuring:
  - **3 Engineering Swarm Incidents (`inc-01` Checkout GST Sec 15(3), `inc-02` NPCI UPI Auth & DPDP Act 2023, `inc-03` Multi-FC Split-Cart Concurrency):**
  - **Shared `~6.7k`-Token Monorepo Prefix & `PR-SANDBOX-GATE-01`:** Isolated Python `-I` subprocess verifier running `4` CI unit checks + `4` adversarial/concurrency checks + `2` static AST security gates (`10` checks per incident) alongside unified diffs.
  - **3-Rung Swarm Arena Graded by Cost per Verified Outcome (CpO):**
    1. Rung 1: Unisolated Shared-Bus Broadcast Swarm (`claude-sonnet-5-5`, uncached omnibus history + noisy OTel spans, `>100k` prompt tok/run)
    2. Rung 2: Isolated Sub-Agents + Cached Repo Prefix (`-90%` reads) + Bounded 1-Retry `PR-SANDBOX-GATE-01`
    3. Rung 3: Tier-Routed Haiku (`claude-haiku-5-5` Orchestrator, CI Triager, Security Critic & Merge Gate) + Sonnet (`claude-sonnet-5-5` Patch Author)
  - **Band 5 Daily Developer Token (`1.5M–10M+ tok/day`) & Org CpO Simulator:** Benchmarks CpR vs. true Portfolio CpO across engineering pods and org scales.

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
To seed all `206` pre-captured traces (`48` Cat 1 + `44` Cat 2 + `64` Cat 3 + `32` Cat 4 + `9` Cat 5 + `9` Cat 6) from golden replays and launch the dedicated **Streamlit Trace Explorer**:
```bash
backend/.venv/bin/pip install -r backend/requirements-viewer.txt   # one-time local install into backend/.venv
backend/.venv/bin/python backend/scripts/seed_traces_from_replays.py
chmod +x run_trace_viewer.sh
./run_trace_viewer.sh   # opens http://127.0.0.1:8501
```

## Deploy to GCP Cloud Run
```bash
chmod +x deploy_cloud_run.sh
PROJECT_ID=my-gcp-project AUTHOR_PASSCODE=my-secret ./deploy_cloud_run.sh
```
