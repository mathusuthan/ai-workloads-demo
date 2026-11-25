"""System prompts & SDK Inspector snippets for Category 5 Autonomous ERP Orchestration."""

from __future__ import annotations

from app.data.cat5_fixtures import AP_POLICY_MANUAL_MARKDOWN


def get_cat5_system_prompt(rung_id: str) -> str:
    """Return SOP-grounded system instruction tailored to the rung's tool protocol."""
    if rung_id == "unbounded_sonnet_loop":
        contract = (
            "=== EXECUTION PROTOCOL: EXPLORATORY MULTI-STEP RECONCILIATION ===\n"
            "You are reconciling this invoice step-by-step against NovaMart's raw SQLite ERP tables.\n"
            "To maintain a complete step-by-step audit trail, call ONLY ONE tool per step in sequence "
            "(never batch multiple tool calls in a single turn):\n"
            "1. query_invoice_raw(invoice_id)\n"
            "2. query_po_raw(po_id)\n"
            "3. query_grn_wms_telemetry(po_id)\n"
            "4. query_vendor_audit_history(vendor_id)\n"
            "5. query_contract_amendments_and_dock_logs(po_id)\n"
            "6. Perform all Module 1–5 math carefully and call commit_reconciliation_voucher(...).\n"
            "7. Finish with a concise 120-word AP controller readout citing the committed voucher."
        )
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


CAT5_CODE_SNIPPETS: dict[str, str] = {
    "unbounded_sonnet_loop": """# RUNG 1 ANTI-PATTERN: Unbounded Exploratory ReAct Loop on Sonnet 5.5
# Calls 6 unprojected SELECT * tools (WMS scan arrays, 3-yr vendor audit logs, dock logs)
# WITHOUT prefix cache_control or deterministic policy gate -> ~35k–55k cumulative tokens/invoice!
for step in range(max_steps=10):
    resp = await client.messages.create(
        model="claude-sonnet-5-5",  # $2.00/M uncached in · $10.00/M out every turn!
        max_tokens=2048,
        thinking={"type": "between_tools"},
        system=AP_POLICY_MANUAL_TEXT,  # NO cache_control!
        tools=NAIVE_SELECT_STAR_TOOLS,
        messages=loop_history,
    )
    if resp.stop_reason != "tool_use":
        break""",
    "bounded_sonnet_cached_gate": """# RUNG 2 LEVER 1: Projected JOINs + Cached SOP Manual + Deterministic AP Gate (max_steps=4)
# Consolidates reads into fetch_3way_match_bundle, caches ~5.5k-tok manual (-95% read),
# and forces commit_reconciliation_voucher to pass run_policy_tolerance_gate first!
system_cached = [{
    "type": "text",
    "text": AP_POLICY_MANUAL_TEXT,
    "cache_control": {"type": "ephemeral"},  # >= 4,096 tok floor satisfied!
}]
resp = await client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=2048,
    thinking={"type": "between_tools"},
    system=system_cached,
    tools=GOVERNED_TOOLS,
    messages=loop_history,
)""",
    "hybrid_haiku_sonnet_governed": """# RUNG 3 LEVER 2: Haiku-First ERP Lookups + Conditional Sonnet Escalation (-92% Cost!)
# Steps 1–2 run on Haiku 5.5 ($0.10/M in · $0.50/M out, $0.01/M cached read).
# Escalates to Sonnet 5.5 ONLY when AP-POL-GATE-01 flags multi-factor commercial disputes!
active_model = "claude-haiku-5-5"
for step in range(max_steps=4):
    resp = await client.messages.create(
        model=active_model,
        thinking={"type": "between_tools"} if "sonnet" in active_model else {"type": "disabled"},
        system=[{"type": "text", "text": AP_POLICY_MANUAL_TEXT, "cache_control": {"type": "ephemeral"}}],
        tools=GOVERNED_TOOLS,
        messages=loop_history,
    )
    gate_out = execute_sqlite_tool(resp)
    if gate_out and gate_out.get("escalation_required"):
        active_model = "claude-sonnet-5-5"  # Escalate complex disputes only!""",
}
