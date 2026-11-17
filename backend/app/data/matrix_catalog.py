"""Slide 1-9 Matrix Catalog & NovaMart Enterprise Narrative Across All 6 Archetypes."""

from __future__ import annotations


NOVAMART_PROFILE = {
    "company_name": "NovaMart Enterprise",
    "tagline": "Omnichannel Retail & Marketplace Platform · 12M SKUs · 45,000 Sellers · $2.4B GMV",
    "series_title": "Six Key AI Archetypes for Enterprise Workloads",
    "deck_attribution": "Based on Eric Lam's AI Workload Archetypes Matrix (Slides 01–09)",
}

AUTONOMY_TIERS = [
    {"tier": 4, "short": "Tier 4", "label": "Fully Agentic · Continuous Swarms"},
    {"tier": 3, "short": "Tier 3", "label": "Bounded Agentic & Stateful Sessions"},
    {"tier": 2, "short": "Tier 2", "label": "Human-in-Loop & Deep RAG"},
    {"tier": 1, "short": "Tier 1", "label": "Single-Pass Stateless / Schema API"},
]

TOKEN_BANDS = [
    {"band": 1, "code": "Band 1", "range": "~0.5k–1.5k", "subtitle": "Lightweight Call"},
    {"band": 2, "code": "Band 2", "range": "~2k–7k", "subtitle": "Output-Heavy Call"},
    {"band": 3, "code": "Band 3", "range": "10k–40k+", "subtitle": "Multi-Turn Session"},
    {"band": 4, "code": "Band 4", "range": "15k–150k+", "subtitle": "Deep RAG (4L) < Loops (4R)"},
    {"band": 5, "code": "Band 5", "range": "1.5M–10M+/day", "subtitle": "Massive Continuous"},
]

ARCHETYPES_CATALOG = [
    {
        "id": 1,
        "slug": "classification-extraction-routing",
        "category_label": "CATEGORY 1",
        "title": "Classification, Extraction & Routing",
        "novamart_product_name": "NovaMart Intake & Catalog Gate",
        "autonomy_tier": 1,
        "autonomy_tier_label": "Tier 1: Single-Pass API",
        "token_band": "Band 1 (~0.5k–1.5k tok)",
        "matrix_x_band": 1,
        "matrix_y_tier": 1,
        "input_profile": "500 – 1,500 tokens",
        "output_profile": "10 – 100 tokens",
        "dynamics": "~20:1 to 50:1 (Heavy Input Asymmetry)",
        "color_hex": "#2563EB",
        "deck_use_cases": [
            "Omnichannel Support",
            "PII / Compliance Masking",
            "Catalog Tagging",
        ],
        "architectural_lever": (
            "Route Tier 1 stateless triage to Flash/Haiku models with strict JSON schemas & batching "
            "to cut unit cost by >80% — or step down to System-1 Decision models (Gemini Decision 1 / Jev) "
            "for 0 output tokens on pure routing/classification."
        ),
        "novamart_story": (
            "Processes 5M weekly seller feed updates and customer escalations: routes support tickets "
            "with inline PII scrubbing and flags contradicted or hazmat cold-start SKUs before indexing."
        ),
        "status": "live",
        "blog_post_number": 1,
    },
    {
        "id": 2,
        "slug": "generative-synthesis-drafting",
        "category_label": "CATEGORY 2",
        "title": "Generative Synthesis & Drafting",
        "novamart_product_name": "NovaMart Executive & Compliance Readout Studio",
        "autonomy_tier": 2,
        "autonomy_tier_label": "Tier 2: HITL",
        "token_band": "Band 2 (~2k–7k tok)",
        "matrix_x_band": 2,
        "matrix_y_tier": 2,
        "input_profile": "1,500 – 4,000 tokens",
        "output_profile": "800 – 3,000+ tokens",
        "dynamics": "~1:1 to 1:2 (Output Dominated Cost)",
        "color_hex": "#DC2626",
        "deck_use_cases": [
            "Collateral Drafting",
            "Transcript Synthesis",
            "Regulatory Reporting",
        ],
        "architectural_lever": (
            "Because output tokens cost 5x more than input tokens on Claude, enforce structured section "
            "templates, explicit per-section token caps, and HITL section-level regeneration."
        ),
        "novamart_story": (
            "Turns messy Diwali Peak Ops incident transcripts and vendor metrics into bounded executive briefs "
            "and marketplace regulatory filings with side-by-side human review."
        ),
        "status": "live",
        "blog_post_number": 2,
    },
    {
        "id": 3,
        "slug": "multi-turn-conversational-assistants",
        "category_label": "CATEGORY 3",
        "title": "Multi-Turn Conversational Assistants",
        "novamart_product_name": "NovaMart IT & HR Unified Service Desk",
        "autonomy_tier": 3,
        "autonomy_tier_label": "Tier 3: Stateful Session",
        "token_band": "Band 3 (10k–40k+ tok)",
        "matrix_x_band": 3,
        "matrix_y_tier": 3,
        "input_profile": "1k – 25k+ tokens",
        "output_profile": "150 – 600 / turn",
        "dynamics": "Session: 10,000 – 40,000+ tokens",
        "color_hex": "#15803D",
        "deck_use_cases": [
            "IT & HR Service Desk",
            "Consumer Dialogue",
            "Field Ops Assistant",
        ],
        "architectural_lever": (
            "Enable Anthropic prefix context caching (90% read discount) and sliding-window memory "
            "summarization to eliminate quadratic O(N²) session cost across 10+ turns."
        ),
        "novamart_story": (
            "Guides 18,000 corporate and fulfillment employees through multi-turn Zero-Trust MDM/VPN "
            "diagnostics, Workday leave/payroll retro-adjustments, and policy approvals without re-paying "
            "full handbook or log history costs on Turn 10."
        ),
        "status": "live",
        "blog_post_number": 3,
    },
    {
        "id": 4,
        "slug": "multi-doc-rag-deep-ingestion",
        "category_label": "CATEGORY 4",
        "title": "Multi-Doc RAG & Deep Ingestion",
        "novamart_product_name": "NovaMart Supplier Contract & 10-K Due Diligence",
        "autonomy_tier": 2,
        "autonomy_tier_label": "Tier 2+: HITL Deep RAG",
        "token_band": "Band 4L (15k–100k+ tok)",
        "matrix_x_band": 4,
        "matrix_y_tier": 2,
        "input_profile": "15k – 100k+ tokens",
        "output_profile": "400 – 1,500 tokens",
        "dynamics": "~20:1 to 100:1 (Extreme Context Load)",
        "color_hex": "#D97706",
        "deck_use_cases": [
            "Legal Due Diligence",
            "Grounding Repositories",
            "Financial 10-K Analysis",
        ],
        "architectural_lever": (
            "Pair hybrid chunk retrieval & reranking with Anthropic Context Caching (cache_control) and "
            "native Document Citations on shared supplier policy & contract repositories."
        ),
        "novamart_story": (
            "Cross-examines 40k+ tokens of wholesale supplier MSAs, Diwali SLA addenda, and compliance "
            "handbooks into zero-hallucination clause risk matrices."
        ),
        "status": "coming_soon",
        "blog_post_number": 4,
    },
    {
        "id": 5,
        "slug": "autonomous-process-orchestration",
        "category_label": "CATEGORY 5",
        "title": "Autonomous Process Orchestration",
        "novamart_product_name": "NovaMart 3-Way Invoice Reconciliation Agent",
        "autonomy_tier": 3,
        "autonomy_tier_label": "Tier 3+: Bounded Agentic",
        "token_band": "Band 4R (25k–150k+ tok)",
        "matrix_x_band": 4,
        "matrix_y_tier": 3,
        "input_profile": "25k – 150k+ tokens",
        "output_profile": "1,500 – 8,000 tokens",
        "dynamics": "Multi-Turn Tool Loops (Iterative)",
        "color_hex": "#0F766E",
        "deck_use_cases": [
            "Invoice Reconciliation",
            "Claims Adjudication",
            "Supply Chain Dispatch",
        ],
        "architectural_lever": (
            "Enforce max-step loop budgets, deterministic policy verification gates, and Haiku-tier "
            "routing for routine ERP tool lookups inside Plan → Call → Verify → Dispatch loops."
        ),
        "novamart_story": (
            "Reconciles vendor invoices against Purchase Orders and warehouse Goods Receipts in a live "
            "SQLite ERP, stopping immediately on tolerance violations or step-budget limits."
        ),
        "status": "coming_soon",
        "blog_post_number": 5,
    },
    {
        "id": 6,
        "slug": "multi-agent-swarms-auto-eng",
        "category_label": "CATEGORY 6",
        "title": "Multi-Agent Swarms & Auto Eng",
        "novamart_product_name": "NovaMart Checkout & Pricing CI Self-Healing Swarm",
        "autonomy_tier": 4,
        "autonomy_tier_label": "Tier 4: Agentic Swarm",
        "token_band": "Band 5 (1.5M–10M+ tok/day)",
        "matrix_x_band": 5,
        "matrix_y_tier": 4,
        "input_profile": "100k – 1M+ tokens",
        "output_profile": "10k – 50k+ tokens",
        "dynamics": "1.5M – 10M+ tok/day (Per Dev Benchmark)",
        "color_hex": "#6D28D9",
        "deck_use_cases": [
            "Autonomous Feature Dev",
            "Security Threat Hunting",
            "CI/CD Failure Triage",
        ],
        "architectural_lever": (
            "Isolate sub-agent contexts (Author, Security/Test Critic, CI Triager), cache shared repo "
            "prefixes, and measure ROI by Cost per Verified Outcome (CpO)."
        ),
        "novamart_story": (
            "Lead Orchestrator dispatches isolated specialist agents to fix a failing NovaMart pricing "
            "micro-service, verify unit & security checks, and report exact CpO."
        ),
        "status": "coming_soon",
        "blog_post_number": 6,
    },
]

FINOPS_RULES = [
    {
        "rule_number": 1,
        "tiers": "TIERS 1–2 · BANDS 1–2 (CAT 1 & 2)",
        "title": "Right-Size Single-Pass & Output",
        "bullets": [
            "Route Tier 1 stateless triage (Cat 1: 20:1–50:1 input asymmetry) to Haiku/Decision tiers with strict schemas.",
            "Bound Tier 2 drafting (Cat 2: 800–3k+ output) with section templates to control 5x output token pricing.",
        ],
        "impact": "Impact: 60–97% lower unit inference cost",
        "accent": "#2563EB",
    },
    {
        "rule_number": 2,
        "tiers": "TIERS 2+ & 3 · BANDS 3–4L (CAT 3 & 4)",
        "title": "Cache Session & Deep RAG Context",
        "bullets": [
            "Apply sliding-window summarization and prefix caching on Tier 3 multi-turn sessions (Cat 3: 10k–40k+ tok).",
            "Pair hybrid chunk reranking with Context Caching on Tier 2+ deep RAG corpora (Cat 4: 15k–100k+ tok).",
        ],
        "impact": "Impact: Eliminates quadratic context bloat",
        "accent": "#15803D",
    },
    {
        "rule_number": 3,
        "tiers": "TIERS 3+ & 4 · BANDS 4R–5 (CAT 5 & 6)",
        "title": "Govern Agent Loops & Track CpO",
        "bullets": [
            "Enforce max-step loop budgets on Tier 3+ tool orchestration (Cat 5: 25k–150k+ In, 1.5k–8k Out).",
            "Isolate sub-agent contexts on Tier 4 swarms (Cat 6: 1.5M–10M+ tok/day) and measure Cost per Outcome (CpO).",
        ],
        "impact": "Impact: Predictable unit economics at scale",
        "accent": "#6D28D9",
    },
]
