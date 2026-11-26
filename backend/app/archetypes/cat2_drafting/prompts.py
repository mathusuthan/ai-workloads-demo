"""Prompts & SDK Inspector snippets for Category 2 (Generative Synthesis & Drafting)."""

from __future__ import annotations


def get_unbounded_draft_system_prompt(sub_task: str) -> str:
    """Without: open-ended long-form prose prompt (no section template, no length caps)."""
    role = (
        "VP Chief-of-Staff at NovaMart Enterprise preparing a comprehensive board briefing or B2B partnership proposal"
        if sub_task == "exec_synthesis"
        else "Chief Compliance & Regulatory Counsel at NovaMart Enterprise preparing an exhaustive statutory filing"
    )
    return (
        f"You are an expert {role}.\n"
        "Write a thorough, publication-grade, multi-section narrative report in clean Markdown covering EVERY detail in the source bundle. "
        "Include:\n"
        "1. Situation Background & Context (~200-250 words)\n"
        "2. Detailed Chronological / Thematic Breakdown with direct stakeholder attributions and metric analysis (~350-420 words)\n"
        "3. Full Commercial, Legal & Operational Risk Assessment prose (~280-340 words)\n"
        "4. Financial Exposure vs. Mitigation ROI Deep-Dive table and commentary (~200-260 words)\n"
        "5. Action Roadmap across teams plus Verification Appendix (~240-300 words).\n"
        "Do not abbreviate numbers or compress prose — produce a complete executive document ready for external distribution."
    )


NOT_STATED_IN_SOURCE = "Not stated in source"
# The action-plan rule for missing owners and dates (one bullet directly after the `action_plan` rule).
ACTION_PLAN_SOURCE_RULE = (
    "For each action-plan item, give the owner and the time window only if the source states them. "
    "If the source does not name an owner, or gives no date or time window, write exactly `Not stated in source` "
    "in that field. Never supply an owner, team, date or deadline the source does not give."
)


def get_templated_draft_system_prompt(sub_task: str) -> str:
    """With: section template with length caps (same prompt for Sonnet and Haiku)."""
    doc_focus = (
        "executive operational readout or commercial B2B partnership proposal"
        if sub_task == "exec_synthesis"
        else "statutory safety filing or internal risk/KYC regulatory compliance audit report"
    )
    return (
        f"You are NovaMart Enterprise's AI Drafting Engine producing a strict section-templated {doc_focus}.\n"
        "BECAUSE OUTPUT TOKENS COST 5x MORE THAN INPUT TOKENS, obey these exact section density & word budgets (~1,200–1,600 output tokens total):\n"
        "- `executive_summary.headline`: 10–14 words, high-signal takeaway.\n"
        "- `executive_summary.narrative`: 60–80 words strictly grounded in source figures.\n"
        "- `executive_summary.bottom_line_impact`: 14–20 words summarizing net financial/SLA impact.\n"
        "- `key_findings`: Exactly 3 high-signal items; each `quantified_evidence` MUST be 20–30 words citing exact numbers; `source_anchor` <=6 words.\n"
        "- `risk_and_compliance_matrix`: Exactly 3 rows; each `exposure_summary` 16–24 words and `mitigation_control` 16–24 words.\n"
        "- `action_plan`: Exactly 3 owned milestones; each `milestone` 16–24 words and `verification_metric` 10–15 words.\n"
        f"- {ACTION_PLAN_SOURCE_RULE}\n"
        "Emit compact JSON matching the enforced schema without extra filler. Never invent metrics absent from the source bundle."
    )


def get_section_regen_system_prompt(sub_task: str, section_key: str) -> str:
    """Surgical HITL Single-Section Regeneration prompt."""
    domain = (
        "executive synthesis & commercial drafting"
        if sub_task == "exec_synthesis"
        else "statutory & regulatory compliance drafting"
    )
    return (
        f"You are NovaMart's HITL Co-Author performing a SURGICAL SINGLE-SECTION revision ({domain}).\n"
        f"Regenerate ONLY the `{section_key}` section to satisfy the human reviewer's instruction.\n"
        "Rules:\n"
        "1. Preserve factual fidelity strictly to the provided NovaMart source bundle (zero hallucinated figures).\n"
        "2. Keep output concise: for executive_summary keep narrative <=75 words; for list/matrix sections return exactly 3 high-signal items with each text field <=26 words.\n"
        "3. Do NOT repeat unchanged sections—output strictly the updated JSON schema for `{section_key}`."
    )


CAT2_CODE_SNIPPETS: dict[str, str] = {
    "sonnet_unbounded": """# RUNG 1 ANTI-PATTERN: Unbounded Longform Prose on Sonnet 5.5
# Output tokens cost $10.00/M (5x input rate!) -> drives >80% of invoice
resp = await client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=8000,
    thinking={"type": "between_tools"},
    system="Write a comprehensive, publication-grade multi-page report...",
    messages=[{"role": "user", "content": source_bundle}],
)""",
    "sonnet_templated": """# RUNG 2 (CALIBRATED LEVER): Strict Section Template + Length Bounds (Sonnet 5.5)
# Caps array lengths & word budgets (prompt asks for ~1,200–1,600 out tokens); an action item's owner or time window
# is "Not stated in source" when the source gives none
resp = await client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=3000,
    thinking={"type": "between_tools"},
    system=SECTION_BOUNDED_TEMPLATE_PROMPT,
    output_config={"format": {"type": "json_schema", "schema": STRUCTURED_DRAFT_JSON_SCHEMA}},
    messages=[{"role": "user", "content": source_bundle}],
)""",
    "haiku_templated": """# RUNG 3 HYBRID ROUTING: Haiku 5.5 First-Draft Template
# Same section template on Haiku 5.5 ($0.50/M out); a reviewer can regenerate any single section on Sonnet 5.5
resp = await client.messages.create(
    model="claude-haiku-5-5",
    max_tokens=3000,
    thinking={"type": "disabled"},
    system=SECTION_BOUNDED_TEMPLATE_PROMPT,
    output_config={"format": {"type": "json_schema", "schema": STRUCTURED_DRAFT_JSON_SCHEMA}},
    messages=[{"role": "user", "content": source_bundle}],
)""",
    "hitl_section_regen": """# HITL SURGICAL REVISION: Regenerate Only One Un-Locked Section (~250–700 Out Tokens)
# Saves ~70%–98% vs pasting full draft back into multi-turn chat to rewrite everything
resp = await client.messages.create(
    model=selected_tier,  # claude-sonnet-5-5 or claude-haiku-5-5
    max_tokens=1800,
    thinking={"type": "between_tools"} if "sonnet" in selected_tier else {"type": "disabled"},
    system=SURGICAL_SECTION_PROMPT,
    output_config={"format": {"type": "json_schema", "schema": get_single_section_schema(section_key)}},
    messages=[{"role": "user", "content": f"SOURCE:\\n{source}\\n\\nCURRENT:\\n{section}\\n\\nEDIT:\\n{instruction}"}],
)""",
}
