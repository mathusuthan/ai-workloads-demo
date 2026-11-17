"""Architecture Inspector code snippets & prompt summary definitions for Category 1."""

from __future__ import annotations

def get_sonnet_naive_system_prompt(sub_task: str) -> str:
    if sub_task == "support_triage":
        return (
            "You are a thorough, helpful NovaMart Enterprise Operations Assistant. "
            "Carefully analyze the incoming customer/seller escalation thread. "
            "Provide: (1) a clear executive summary of the issue, (2) recommended routing queue and priority level "
            "with your step-by-step reasoning, (3) an explicit audit of every PII element found and a cleaned/redacted "
            "summary, and (4) suggested next steps and draft empathy talking points for the agent."
        )
    return (
        "You are a thorough, helpful NovaMart Catalog Merchandising Assistant. "
        "Analyze this raw seller SKU feed and OCR/spec dump in detail. "
        "Provide: (1) target marketplace category taxonomy and reasoning, (2) factual contradiction or "
        "hazmat/compliance risks with explanation, (3) recommended publishing status, and (4) rewritten "
        "merchandising recommendations for the catalog ops team."
    )


def get_haiku_calibrated_system_prompt(sub_task: str) -> str:
    if sub_task == "support_triage":
        return (
            "NovaMart Tier-1 Triage Classifier. Classify the payload strictly according to the JSON schema. "
            "Emit only compact schema fields. Do not repeat input text."
        )
    return (
        "NovaMart Tier-1 SKU Gate Classifier. Classify category, hazmat class, contradictions, and "
        "publish status strictly according to the JSON schema. Emit only schema fields."
    )


CODE_SNIPPETS: dict[str, str] = {
    "sonnet_naive": '''# RUNG 1A ANTI-PATTERN: Frontier Unconstrained Prose API ($2.00/M in · $10.00/M out)
resp = await anthropic_client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=2048,
    thinking={"type": "between_tools"},
    system="You are a thorough NovaMart assistant. Explain your reasoning...",
    messages=[{"role": "user", "content": ticket_payload}],
)
# Result: verbose uncapped prose @ $10/MTok -> Output dominates total cost!''',
    "haiku_naive": '''# RUNG 1B ABLATION: Model Swap Only — Haiku 5.5 Unconstrained Prose ($0.10/M in · $0.50/M out)
# Stateless single-pass API (NOT multi-turn chat), but still no JSON schema (needs regex scraping)
resp = await anthropic_client.messages.create(
    model="claude-haiku-5-5",
    max_tokens=2048,
    thinking={"type": "disabled"},
    system="You are a thorough NovaMart assistant. Explain your reasoning...",
    messages=[{"role": "user", "content": ticket_payload}],
)
# Saves 95% vs Sonnet 5.5, yet output prose still bloats cost & breaks schema contracts!''',
    "haiku_calibrated": '''# RUNG 2 SLIDE 3 LEVER: Haiku 5.5 + Strict JSON Schema ($0.10/M in · $0.50/M out)
# Disable thinking on Tier-1 classification to avoid 100+ extra thinking output tokens!
# Plus 50% discount when routed via Anthropic Message Batches ($0.05/M in · $0.25/M out)
resp = await anthropic_client.messages.create(
    model="claude-haiku-5-5",
    max_tokens=256,
    thinking={"type": "disabled"},
    system="NovaMart Tier-1 Classifier. Emit only schema fields.",
    output_config={"format": {"type": "json_schema", "schema": TRIAGE_SCHEMA}},
    messages=[{"role": "user", "content": ticket_payload}],
)
# Companion deterministic <1ms regex gate scrubs raw Aadhaar/Card/Email/Phone inline!''',
    "gemini_decision": '''# RUNG 3 SYSTEM-1 DECISION API: Gemini Decision 1 ($0.10/M in · $0.00 out)
client = genai.Client(http_options={"api_version": "v1beta"})
result = await client.aio.decisions.create(
    model="gemini-decision-1",
    input=ticket_payload,  # Shared input billed ONCE across all questions
    questions={
        "queue": {"type": "choice", "instructions": "...", "criteria": {...}},
        "severity": {"type": "score", "instructions": "...", "criteria": [...]},
        "contains_sensitive_pii": {"type": "noul", "instructions": "..."},
    },
)
# Returns calibrated probabilities + confidence with ZERO output tokens!
# Architectural boundary: cannot rewrite text -> pair with deterministic regex PII scrubber.''',
}
