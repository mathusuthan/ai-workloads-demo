"""System prompts & SDK Inspector snippets for Category 5 Autonomous ERP Orchestration."""

from __future__ import annotations

from app.data.cat5_fixtures import AP_POLICY_MANUAL_MARKDOWN


# The raw-table loops (versions 1 and 2) / the ablation's neutral arms: the model chooses its own tools and order (no scripted sequence).
# Shared verbatim with app/archetypes/cat5_orchestration/ablation.py (NEUTRAL_PROTOCOL).
CAT5_FREE_CHOICE_PROTOCOL = (
    "=== EXECUTION PROTOCOL ===\n"
    "Reconcile this invoice against the ERP records using the tools available. Use only the tools you need; "
    "you may call several in one step. Apply the policy manual exactly, then commit the final voucher with "
    "`commit_reconciliation_voucher`, and finish with a summary of at most 130 words that cites the committed voucher."
)


def get_cat5_system_prompt(rung_id: str) -> str:
    """SOP policy manual + the rung's execution protocol."""
    if rung_id in ("unbounded_sonnet_loop", "unbounded_haiku_loop"):  # version 2 = version 1 on Haiku, same text
        contract = CAT5_FREE_CHOICE_PROTOCOL
    elif rung_id == "bounded_sonnet_cached_gate":
        contract = (
            "=== EXECUTION PROTOCOL: GOVERNED 4-STEP BUDGET + DETERMINISTIC GATE (SONNET 5.5) ===\n"
            "Obey strict max_step_budget = 4 (at most 1 tool call per step):\n"
            "- Step 1: Call fetch_3way_match_bundle(invoice_id).\n"
            "- Step 2: Call run_policy_tolerance_gate(invoice_id) to run AP-POL-GATE-01 deterministic verification.\n"
            "- Step 3: Copy the exact gate numbers & recommended_decision into commit_reconciliation_voucher(...).\n"
            "- Step 4: Emit a concise <=130-word executive AP audit summary referencing the verified voucher_id and GL/queue routing."
        )
    else:
        contract = (
            "=== EXECUTION PROTOCOL: HYBRID HAIKU -> SONNET GOVERNED ORCHESTRATION ===\n"
            "Obey strict max_step_budget = 4 (at most 1 tool call per step):\n"
            "- Step 1 (Haiku 5.5): Call fetch_3way_match_bundle(invoice_id).\n"
            "- Step 2 (Haiku 5.5): Call run_policy_tolerance_gate(invoice_id). Note: if escalation_required=true, the runtime escalates Step 3+ to Sonnet 5.5; otherwise Haiku 5.5 completes cleanly.\n"
            "- Step 3: Call commit_reconciliation_voucher(...) using the exact verified figures from run_policy_tolerance_gate.\n"
            "- Step 4: Emit a concise <=130-word executive AP audit summary naming the verified voucher_id and whether Sonnet escalation fired."
        )

    return f"{AP_POLICY_MANUAL_MARKDOWN.strip()}\n\n{contract}"


def build_cat5_user_task_prompt(preset: dict) -> str:
    return (
        f"Reconcile NovaMart supplier invoice `{preset['invoice_id']}` "
        f"(PO `{preset['po_id']}`, supplier `{preset['vendor_name']}`, hub `{preset['fc_hub']}`, "
        f"claimed grand total `INR {preset['invoice_grand_total_inr']:,.2f}`) "
        "against live SQLite ERP records and commit the final voucher into `reconciliation_vouchers`."
    )


# Display-only (Code Inspector), in display order. Describes what each version does; measured results are in the ablation panel.
CAT5_CODE_SNIPPETS: dict[str, str] = {
    "unbounded_sonnet_loop": """# VERSION 1 (without the lever, Sonnet): free-choice loop over raw SELECT * tools on Sonnet 5.5
# The model picks which raw table queries to run (several per turn allowed), does the policy arithmetic
# itself and commits the voucher. No prompt cache, no policy gate; safety cap of 12 model turns.
for turn in range(12):
    resp = await client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=4096,
        thinking={"type": "between_tools"},
        system=AP_POLICY_MANUAL_TEXT + FREE_CHOICE_PROTOCOL,  # no cache_control
        tools=RAW_SELECT_STAR_TOOLS + [COMMIT_VOUCHER],
        messages=loop_history,
    )
    tool_uses = [b for b in resp.content if b.type == "tool_use"]
    if resp.stop_reason == "max_tokens" or not tool_uses:
        break  # a truncated turn or a turn without tool calls ends the run
    loop_history += [assistant(resp.content), user(execute_all(tool_uses))]  # whatever the stop_reason""",
    "unbounded_haiku_loop": """# VERSION 2 (without the lever, Haiku): version 1 on Haiku 5.5 -- the same free-choice loop over raw SELECT * tools
# Same tools, prompt, 12-turn safety cap and loop rule as version 1; no prompt cache and no policy tool, so there is
# no escalation path to Sonnet. Thinking is disabled for Haiku in the app's call function.
for turn in range(12):
    resp = await client.messages.create(
        model="claude-haiku-5-5",
        max_tokens=4096,
        thinking={"type": "disabled"},
        system=AP_POLICY_MANUAL_TEXT + FREE_CHOICE_PROTOCOL,  # no cache_control
        tools=RAW_SELECT_STAR_TOOLS + [COMMIT_VOUCHER],
        messages=loop_history,
    )
    tool_uses = [b for b in resp.content if b.type == "tool_use"]
    if resp.stop_reason == "max_tokens" or not tool_uses:
        break
    loop_history += [assistant(resp.content), user(execute_all(tool_uses))]""",
    "bounded_sonnet_cached_gate": """# VERSION 3 (with the lever, Sonnet): narrow bundle query + cached policy manual + deterministic policy gate
# One projected JOIN replaces the raw table dumps; the manual is sent as a cached prefix; the commit tool
# refuses until run_policy_tolerance_gate has computed the figures, which the committed voucher carries.
system_cached = [{
    "type": "text",
    "text": AP_POLICY_MANUAL_TEXT + GOVERNED_PROTOCOL,
    "cache_control": {"type": "ephemeral"},
}]
resp = await client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=4096,
    thinking={"type": "between_tools"},
    system=system_cached,
    tools=GOVERNED_TOOLS,  # fetch_3way_match_bundle, run_policy_tolerance_gate, commit (gate first)
    messages=loop_history,
)""",
    "hybrid_haiku_sonnet_governed": """# VERSION 4 (with the lever, Haiku-first): version 3's tools on Haiku 5.5, switching to Sonnet 5.5 when the gate flags escalation
# The gate sets escalation_required only for a multi-factor dispute (2+ of: DOA/short receipt, amendment, price rise, freight).
active_model = "claude-haiku-5-5"
for turn in range(5):  # step budget 4 + one wrap-up turn
    resp = await client.messages.create(
        model=active_model,
        max_tokens=4096,
        thinking={"type": "between_tools"} if "sonnet" in active_model else {"type": "disabled"},
        system=[{"type": "text", "text": AP_POLICY_MANUAL_TEXT + HYBRID_PROTOCOL, "cache_control": {"type": "ephemeral"}}],
        tools=GOVERNED_TOOLS,
        messages=loop_history,
    )
    gate_out = execute_sqlite_tools(resp)
    if gate_out and gate_out.get("escalation_required"):
        active_model = "claude-sonnet-5-5"  # from the next turn on
""",
}
