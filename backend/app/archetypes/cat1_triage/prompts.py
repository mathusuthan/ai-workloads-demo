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
    "sonnet_naive": '''# WITHOUT THE IMPROVEMENT (Sonnet): four-part write-up ($2.00/M in · $10.00/M out)
resp = await anthropic_client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=8192,  # no write-up in the experiment reached this cap
    thinking={"type": "between_tools"},
    system="You are a thorough, helpful NovaMart ... assistant. Carefully analyze ... (1) ... (4) ...",
    messages=[{"role": "user", "content": ticket_payload}],
)
# A write-up, not a classification: the prompt never lists the allowed labels.
# Output tokens at $10/M dominate the cost.''',
    "haiku_naive": '''# WITHOUT THE IMPROVEMENT (Haiku): same write-up prompt on Haiku 5.5 ($0.10/M in · $0.50/M out)
resp = await anthropic_client.messages.create(
    model="claude-haiku-5-5",
    max_tokens=8192,
    thinking={"type": "disabled"},
    system="You are a thorough, helpful NovaMart ... assistant. Carefully analyze ... (1) ... (4) ...",
    messages=[{"role": "user", "content": ticket_payload}],
)
# Still a long write-up rather than the classification fields.''',
    "sonnet_calibrated": '''# WITH THE IMPROVEMENT (Sonnet): ask Sonnet 5.5 for the classification fields only, through a
# JSON schema ($2.00/M in · $10.00/M out; the Batch API price at 50% is computed, not run)
resp = await anthropic_client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=512,
    thinking={"type": "between_tools"},
    system="NovaMart Tier-1 Triage Classifier. Classify the payload strictly according to the JSON schema. ...",
    output_config={"format": {"type": "json_schema", "schema": TRIAGE_SCHEMA}},
    messages=[{"role": "user", "content": ticket_payload}],
)
# Same prompt and schema as the Haiku rung; only the model differs.''',
    "haiku_calibrated": '''# WITH THE IMPROVEMENT (Haiku): ask Haiku 5.5 for the classification fields only, through a
# JSON schema ($0.10/M in · $0.50/M out; the Batch API price at 50% is computed, not run)
resp = await anthropic_client.messages.create(
    model="claude-haiku-5-5",
    max_tokens=512,
    thinking={"type": "disabled"},
    system="NovaMart Tier-1 Triage Classifier. Classify the payload strictly according to the JSON schema. ...",
    output_config={"format": {"type": "json_schema", "schema": TRIAGE_SCHEMA}},
    messages=[{"role": "user", "content": ticket_payload}],
)
# Answering only the fields keeps the output to a short typed record.
# Companion deterministic <1ms regex gate scrubs raw Aadhaar/Card/Email/Phone inline.''',
}
