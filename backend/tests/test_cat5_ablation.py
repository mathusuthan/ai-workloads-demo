"""Category 5 ablation harness tests — no network; `run_cat5_tool_loop_step` is replaced by a scripted fake."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from app.archetypes.cat5_orchestration import ablation as ab
from app.archetypes.cat5_orchestration.erp_db import (
    GOVERNED_TOOLS,
    NAIVE_TOOLS,
    Cat5ErpSession,
    create_seeded_erp_connection,
)
from app.archetypes.cat5_orchestration.prompts import build_cat5_user_task_prompt, get_cat5_system_prompt
from app.core.anthropic_service import AnthropicRawResult
from app.data.cat5_ablation_fixtures import (
    CAT5_ABLATION_DEFAULT_INVOICE_IDS,
    CAT5_ABLATION_ERP_ROWS,
    CAT5_ABLATION_EXCLUDED_PENDING_REVIEW,
    CAT5_ABLATION_NEW_PRESETS,
    CAT5_ABLATION_PRESETS,
    CAT5_ABLATION_PRESETS_BY_ID,
    ERP_TABLE_ORDER,
    ROWS_BY_INVOICE,
)
from app.data.cat5_fixtures import CAT5_PRESETS, ERP_SEED_DATA

BACKEND = Path(__file__).resolve().parent.parent
P = CAT5_ABLATION_PRESETS_BY_ID
GATE_ARMS = ("bundle_gate_sonnet_cached", "bundle_gate_haiku_escalate")
NEUTRAL_ARMS = ("raw_free_sonnet", "raw_free_sonnet_cached", "bundle_sonnet_cached", "bundle_haiku_cached")


# --------------------------------------------------------------------------------------------------
# Scripted fake for run_cat5_tool_loop_step
# --------------------------------------------------------------------------------------------------


def _commit_input(preset: dict[str, Any], **override: Any) -> dict[str, Any]:
    gt = preset["ground_truth"]
    d = {
        "invoice_id": preset["invoice_id"],
        "po_id": preset["po_id"],
        "decision": gt["decision"],
        "authorized_net_principal_inr": gt["authorized_net_principal_inr"],
        "authorized_gst_payout_inr": gt["authorized_gst_payout_inr"],
        "gst_escrow_holdback_inr": gt["gst_escrow_holdback_inr"],
        "debit_note_deduction_inr": gt["debit_note_deduction_inr"],
        "audit_summary": "test",
    }
    d.update(override)
    return d


class Scripted:
    """Each script entry: (stop_reason, [(tool_name, input), ...], text). Repeats the last entry if exhausted."""

    def __init__(self, script: list[tuple[str, list[tuple[str, dict[str, Any]]], str]], *, fail_on: int | None = None,
                 tokens: dict[str, int] | None = None) -> None:
        self.script = script
        self.calls: list[dict[str, Any]] = []
        self.fail_on = fail_on
        self.tokens = tokens or {}

    async def __call__(self, **kw: Any) -> AnthropicRawResult:
        self.calls.append(kw)
        i = len(self.calls)
        if self.fail_on == i:
            raise RuntimeError("simulated API failure")
        stop, uses, text = self.script[min(i - 1, len(self.script) - 1)]
        tool_uses = [{"type": "tool_use", "id": f"tu_{i}_{j}", "name": n, "input": inp} for j, (n, inp) in enumerate(uses)]
        blocks = ([{"type": "text", "text": text}] if text else []) + tool_uses
        cached = kw["use_prefix_cache"]
        model = "claude-sonnet-5-5" if "sonnet" in kw["model_tier"] else "claude-haiku-5-5"
        first_on_model = sum(1 for c in self.calls if c["model_tier"] == kw["model_tier"]) == 1
        prefix = 8600
        return AnthropicRawResult(
            model_id=model,
            latency_ms=10,
            input_tokens=self.tokens.get("input", 500 if cached else 9000),
            output_tokens=self.tokens.get("output", 120),
            cache_creation_tokens=(prefix if (cached and first_on_model) else 0),
            cache_read_tokens=(prefix if (cached and not first_on_model) else 0),
            raw_text=text,
            structured={"assistant_blocks": blocks, "tool_uses": tool_uses, "thinking_text": ""},
            system_prompt=kw["system_text"],
            request_params={"max_tokens": kw["max_tokens"]},
            stop_reason=stop,
            thinking_tokens=0,
        )


def run(arm_id: str, preset_id: str, agent: Scripted, repeat_index: int = 0, sink: dict[str, str] | None = None) -> dict[str, Any]:
    return asyncio.run(
        ab.execute_run(
            arm_id=arm_id,
            preset=P[preset_id],
            repeat_index=repeat_index,
            api_key="test-key",
            agent_call=agent,
            blob_sink=(None if sink is None else sink.__setitem__),
        )
    )


def governed_script(preset_id: str) -> list:
    inv = P[preset_id]["invoice_id"]
    return [
        ("tool_use", [("fetch_3way_match_bundle", {"invoice_id": inv})], "fetch"),
        ("tool_use", [("run_policy_tolerance_gate", {"invoice_id": inv})], "gate"),
        ("tool_use", [("commit_reconciliation_voucher", _commit_input(P[preset_id]))], "commit"),
        ("end_turn", [], "Summary citing voucher."),
    ]


def bundle_script(preset_id: str, **override: Any) -> list:
    inv = P[preset_id]["invoice_id"]
    return [
        ("tool_use", [("fetch_3way_match_bundle", {"invoice_id": inv})], ""),
        ("tool_use", [("commit_reconciliation_voucher", _commit_input(P[preset_id], **override))], ""),
        ("end_turn", [], "Done."),
    ]


# --------------------------------------------------------------------------------------------------
# Arms, tools, prompts
# --------------------------------------------------------------------------------------------------


def test_six_arms_and_tool_lists() -> None:
    assert ab.ARM_IDS == (
        "raw_free_sonnet", "raw_free_sonnet_cached", "bundle_sonnet_cached",
        "bundle_gate_sonnet_cached", "bundle_haiku_cached", "bundle_gate_haiku_escalate",
    )
    for a in ("raw_free_sonnet", "raw_free_sonnet_cached"):
        tools = ab.tools_for(a)
        assert tools == NAIVE_TOOLS and all(x is y for x, y in zip(tools, NAIVE_TOOLS))
        assert [t["name"] for t in tools] == [
            "query_invoice_raw", "query_po_raw", "query_grn_wms_telemetry", "query_vendor_audit_history",
            "query_contract_amendments_and_dock_logs", "commit_reconciliation_voucher",
        ]
    for a in ("bundle_sonnet_cached", "bundle_haiku_cached"):
        tools = ab.tools_for(a)
        assert [t["name"] for t in tools] == ["fetch_3way_match_bundle", "commit_reconciliation_voucher"]
        assert tools[0] is GOVERNED_TOOLS[0]
        assert tools[1] is NAIVE_TOOLS[-1]
        assert "run_policy_tolerance_gate" not in json.dumps(tools)
    for a in GATE_ARMS:
        assert ab.tools_for(a) == GOVERNED_TOOLS


def test_caps_and_flags() -> None:
    assert ab.MAX_TOKENS_PER_TURN == 4096
    for a in NEUTRAL_ARMS:
        assert ab.ARMS[a].turn_cap == 12 and not ab.ARMS[a].gate and ab.ARMS[a].session_rung_id == "unbounded_sonnet_loop"
    for a in GATE_ARMS:
        assert ab.ARMS[a].step_budget == 4 and ab.ARMS[a].turn_cap == 5 and ab.ARMS[a].gate
    assert not ab.ARMS["raw_free_sonnet"].cached
    assert all(ab.ARMS[a].cached for a in ab.ARM_IDS if a != "raw_free_sonnet")
    assert ab.ARMS["bundle_haiku_cached"].start_model == "claude-haiku-5-5"
    assert ab.ARMS["bundle_gate_haiku_escalate"].escalate
    assert sum(ab.ARMS[a].escalate for a in ab.ARM_IDS) == 1


def test_neutral_protocol_identical_and_names_no_tool_order() -> None:
    texts = {ab.base_system_text(a) for a in NEUTRAL_ARMS}
    assert len(texts) == 1
    assert texts.pop().endswith(ab.NEUTRAL_PROTOCOL)
    for banned in ("fetch_3way_match_bundle", "run_policy_tolerance_gate", "query_", "Step 1", "1."):
        assert banned not in ab.NEUTRAL_PROTOCOL


def test_gate_prompts_byte_identical_to_today() -> None:
    assert ab.base_system_text("bundle_gate_sonnet_cached") == get_cat5_system_prompt("bounded_sonnet_cached_gate")
    assert ab.base_system_text("bundle_gate_haiku_escalate") == get_cat5_system_prompt("hybrid_haiku_sonnet_governed")
    for a in GATE_ARMS:
        assert ab.system_text_for(a, "abc") == ab.nonce_line("abc") + get_cat5_system_prompt(ab.ARMS[a].prompt)


def test_every_arm_gets_todays_user_task_and_call_settings() -> None:
    for a in ab.ARM_IDS:
        agent = Scripted([("end_turn", [], "x")])
        rec = run(a, "inv-01", agent)
        kw = agent.calls[0]
        assert kw["messages"][0]["content"] == build_cat5_user_task_prompt(P["inv-01"]) == rec["user_task"]
        assert kw["max_tokens"] == 4096
        assert kw["timeout_s"] == ab.CALL_TIMEOUT_S
        assert kw["use_prefix_cache"] is ab.ARMS[a].cached
        assert kw["model_tier"] == ab.ARMS[a].start_model
        assert kw["tools"] == ab.tools_for(a)
        assert rec["settings"]["max_tokens_per_turn"] == 4096


def test_nonce_per_run_for_cached_arms_only() -> None:
    a1, a2 = Scripted([("end_turn", [], "x")]), Scripted([("end_turn", [], "x")])
    r1, r2 = run("bundle_sonnet_cached", "inv-01", a1), run("bundle_sonnet_cached", "inv-01", a2)
    s1, s2 = a1.calls[0]["system_text"], a2.calls[0]["system_text"]
    assert s1.startswith(f"[run-nonce: {r1['run_nonce']}]\n") and s2.startswith(f"[run-nonce: {r2['run_nonce']}]\n")
    assert r1["run_nonce"] != r2["run_nonce"] and s1 != s2
    assert s1[len(ab.nonce_line(r1["run_nonce"])):] == ab.neutral_system_text()
    a3 = Scripted([("end_turn", [], "x")])
    r3 = run("raw_free_sonnet", "inv-01", a3)
    assert r3["run_nonce"] is None and a3.calls[0]["system_text"] == ab.neutral_system_text()


# --------------------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------------------


def test_multi_tool_call_turn_executes_all_and_returns_all_results() -> None:
    pre = P["inv-02"]
    batch = [
        ("query_invoice_raw", {"invoice_id": pre["invoice_id"]}),
        ("query_po_raw", {"po_id": pre["po_id"]}),
        ("query_grn_wms_telemetry", {"po_id": pre["po_id"]}),
        ("query_vendor_audit_history", {"vendor_id": "VND-BOM-512"}),
        ("query_contract_amendments_and_dock_logs", {"po_id": pre["po_id"]}),
    ]
    agent = Scripted([
        ("tool_use", batch, ""),
        ("tool_use", [("commit_reconciliation_voucher", _commit_input(pre))], ""),
        ("end_turn", [], "Summary."),
    ])
    sink: dict[str, str] = {}
    rec = run("raw_free_sonnet", "inv-02", agent, sink=sink)
    t1 = rec["turns"][0]
    assert [c["name"] for c in t1["tool_calls"]] == [n for n, _ in batch]
    assert all(c["executed"] for c in t1["tool_calls"])
    second_msgs = agent.calls[1]["messages"]
    results = second_msgs[-1]["content"]
    assert second_msgs[-1]["role"] == "user" and [r["tool_use_id"] for r in results] == [f"tu_1_{j}" for j in range(5)]
    for c, r in zip(t1["tool_calls"], results):
        assert c["result_sha256"] == ab._sha(r["content"]) and sink[c["result_sha256"]] == r["content"]
        assert c["result_chars"] == len(r["content"]) and c["result_head"] == r["content"][:1500]
    assert rec["evaluation"]["exact_match"] and rec["evaluation"]["evidence_recall_pct"] == 100.0
    assert rec["total_tool_calls"] == 6 and rec["turns_used"] == 3 and not rec["cap_hit"]
    assert rec["final_message"] == "Summary." and rec["ended_with_stop_reason"] == "end_turn"


def test_commit_without_gate_in_no_gate_arms() -> None:
    for a in ("bundle_sonnet_cached", "bundle_haiku_cached", "raw_free_sonnet_cached"):
        if ab.ARMS[a].tool_set == "raw":
            pre = P["inv-04"]
            script = [("tool_use", [("query_invoice_raw", {"invoice_id": pre["invoice_id"]})], ""),
                      ("tool_use", [("commit_reconciliation_voucher", _commit_input(pre))], ""), ("end_turn", [], "ok")]
        else:
            script = bundle_script("inv-04")
        rec = run(a, "inv-04", Scripted(script))
        v = rec["committed_voucher"]
        assert v is not None and v["gate_verified"] == 0 and v["decision"] == "APPROVE_CLEAN"
        assert rec["evaluation"]["exact_match"]


def test_gate_enforced_in_gate_arms() -> None:
    pre = P["inv-04"]
    for a in GATE_ARMS:
        agent = Scripted([("tool_use", [("commit_reconciliation_voucher", _commit_input(pre))], ""), ("end_turn", [], "x")])
        rec = run(a, "inv-04", agent)
        assert rec["committed_voucher"] is None
        assert "REJECTED_BY_GOVERNANCE_GATE" in rec["turns"][0]["tool_calls"][0]["result_head"]
        rec2 = run(a, "inv-04", Scripted(governed_script("inv-04")))
        assert rec2["committed_voucher"]["gate_verified"] == 1 and rec2["evaluation"]["exact_match"]


def test_tool_outside_arm_toolset_is_rejected_not_executed() -> None:
    pre = P["inv-04"]
    agent = Scripted([("tool_use", [("run_policy_tolerance_gate", {"invoice_id": pre["invoice_id"]})], ""), ("end_turn", [], "x")])
    rec = run("bundle_sonnet_cached", "inv-04", agent)
    c = rec["turns"][0]["tool_calls"][0]
    assert not c["executed"] and c["rejected_reason"] == "not_in_arm_toolset" and "Unknown tool" in c["result_head"]
    assert rec["total_tool_calls"] == 1 and "vendor_invoices" not in rec["tables_touched"]


def test_escalation_routing_matches_runner() -> None:
    agent = Scripted(governed_script("inv-02"))
    rec = run("bundle_gate_haiku_escalate", "inv-02", agent)
    assert [c["model_tier"] for c in agent.calls] == ["claude-haiku-5-5", "claude-haiku-5-5", "claude-sonnet-5-5", "claude-sonnet-5-5"]
    assert [t["escalated_turn"] for t in rec["turns"]] == [False, False, True, False]
    assert rec["escalation_fired"] and rec["gate_escalation_flagged"]
    agent1 = Scripted(governed_script("inv-01"))
    rec1 = run("bundle_gate_haiku_escalate", "inv-01", agent1)
    assert {c["model_tier"] for c in agent1.calls} == {"claude-haiku-5-5"} and not rec1["escalation_fired"]
    agent_s = Scripted(governed_script("inv-02"))
    rec_s = run("bundle_gate_sonnet_cached", "inv-02", agent_s)
    assert {c["model_tier"] for c in agent_s.calls} == {"claude-sonnet-5-5"}
    assert not rec_s["escalation_fired"] and rec_s["gate_escalation_flagged"]


def test_turn_cap_recorded() -> None:
    inv = P["inv-04"]["invoice_id"]
    forever = [("tool_use", [("fetch_3way_match_bundle", {"invoice_id": inv})], "")]
    agent = Scripted(forever)
    rec = run("bundle_sonnet_cached", "inv-04", agent)
    assert len(agent.calls) == 12 and rec["turns_used"] == 12 and rec["cap_hit"]
    assert rec["committed_voucher"] is None and not rec["evaluation"]["voucher_committed"]
    agent_g = Scripted(forever)
    rec_g = run("bundle_gate_sonnet_cached", "inv-04", agent_g)
    assert len(agent_g.calls) == 5 and rec_g["cap_hit"] and not rec_g["evaluation"]["within_step_budget"]
    s = ab.score_record(rec)
    assert s["cap_hit"] and not s["committed"] and s["turns"] == 12


def test_truncated_turn_flagged_and_its_tool_calls_not_executed() -> None:
    pre = P["inv-04"]
    agent = Scripted([("max_tokens", [("commit_reconciliation_voucher", {"invoice_id": pre["invoice_id"]})], "partial")])
    rec = run("bundle_sonnet_cached", "inv-04", agent)
    t = rec["turns"][0]
    assert t["truncated"] and t["stop_reason"] == "max_tokens" and t["tool_calls"] == []
    assert t["tool_calls_not_executed"][0]["name"] == "commit_reconciliation_voucher"
    assert rec["committed_voucher"] is None and rec["status"] == "ok" and not rec["cap_hit"]
    assert ab.score_record(rec)["truncated_turns"] == 1


def test_mid_run_error_is_recorded_not_raised() -> None:
    agent = Scripted(governed_script("inv-01"), fail_on=2)
    rec = run("bundle_gate_sonnet_cached", "inv-01", agent)
    assert rec["status"] == "error" and "simulated API failure" in rec["error_message"]
    assert len(rec["turns"]) == 1 and rec["evaluation"] is not None and rec["finished_at"]
    assert rec["tables_touched"]  # the turn-1 bundle call is kept


# --------------------------------------------------------------------------------------------------
# ERP isolation
# --------------------------------------------------------------------------------------------------


def test_fresh_erp_per_run() -> None:
    rec1 = run("bundle_sonnet_cached", "inv-04", Scripted(bundle_script("inv-04")))
    assert rec1["committed_voucher"] is not None
    agent = Scripted([("end_turn", [], "x")])
    rec2 = run("bundle_sonnet_cached", "inv-04", agent)
    assert rec2["committed_voucher"] is None and rec2["all_vouchers"] == []
    base = create_seeded_erp_connection()
    assert base.execute("SELECT COUNT(*) FROM vendor_invoices").fetchone()[0] == len(ERP_SEED_DATA["vendor_invoices"])
    s = ab.AblationErpSession(rung_id="unbounded_sonnet_loop")
    n = s.conn.execute("SELECT COUNT(*) FROM vendor_invoices").fetchone()[0]
    assert n == len(ERP_SEED_DATA["vendor_invoices"]) + len(CAT5_ABLATION_ERP_ROWS["vendor_invoices"]) == 12


def _tool_calls_for_original(p: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    vendor_id = next(r["vendor_id"] for r in ERP_SEED_DATA["purchase_orders"] if r["po_id"] == p["po_id"])
    return [
        ("query_invoice_raw", {"invoice_id": p["invoice_id"]}),
        ("query_po_raw", {"po_id": p["po_id"]}),
        ("query_grn_wms_telemetry", {"po_id": p["po_id"]}),
        ("query_vendor_audit_history", {"vendor_id": vendor_id}),
        ("query_contract_amendments_and_dock_logs", {"po_id": p["po_id"]}),
        ("fetch_3way_match_bundle", {"invoice_id": p["invoice_id"]}),
        ("run_policy_tolerance_gate", {"invoice_id": p["invoice_id"]}),
    ]


def test_original_invoices_tool_outputs_identical_with_extra_rows() -> None:
    for p in CAT5_PRESETS:
        base = Cat5ErpSession(rung_id="bounded_sonnet_cached_gate")
        ext = ab.AblationErpSession(rung_id="bounded_sonnet_cached_gate")
        for name, inp in _tool_calls_for_original(p):
            assert base.execute_tool(name, inp) == ext.execute_tool(name, inp), (p["id"], name)
        base.close()
        ext.close()


def test_base_rows_unchanged_in_extended_erp() -> None:
    ext = ab.AblationErpSession(rung_id="unbounded_sonnet_loop")
    base = create_seeded_erp_connection()
    new_keys = {
        "vendors": {r["vendor_id"] for r in CAT5_ABLATION_ERP_ROWS["vendors"]},
        "purchase_orders": {r["po_id"] for r in CAT5_ABLATION_ERP_ROWS["purchase_orders"]},
    }
    for table in ERP_TABLE_ORDER:
        base_rows = [dict(r) for r in base.execute(f"SELECT * FROM {table} ORDER BY rowid")]
        ext_rows = [dict(r) for r in ext.conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
        assert ext_rows[: len(base_rows)] == base_rows
        assert len(ext_rows) == len(base_rows) + len(CAT5_ABLATION_ERP_ROWS[table])
    # no new row reuses an existing vendor, PO, invoice or GRN id
    assert not new_keys["vendors"] & {r["vendor_id"] for r in ERP_SEED_DATA["vendors"]}
    assert not new_keys["purchase_orders"] & {r["po_id"] for r in ERP_SEED_DATA["purchase_orders"]}
    assert not {r["grn_id"] for r in CAT5_ABLATION_ERP_ROWS["goods_receipts"]} & {r["grn_id"] for r in ERP_SEED_DATA["goods_receipts"]}


# --------------------------------------------------------------------------------------------------
# Fixture invariants
# --------------------------------------------------------------------------------------------------

DERIVATION_KEYS = ("inputs", "module4_check", "lines", "freight", "authorized_net_principal_inr",
                   "debit_note_deduction_inr", "gst", "decision", "escalation", "routing")


def test_fixture_shape_and_derivations() -> None:
    assert len(CAT5_ABLATION_NEW_PRESETS) == 9 and len(CAT5_ABLATION_PRESETS) == 12
    ids = [p["id"] for p in CAT5_ABLATION_PRESETS]
    assert ids == [f"inv-{i:02d}" for i in range(1, 13)]
    assert len({p["invoice_id"][-4:] for p in CAT5_ABLATION_PRESETS}) == 12  # voucher ids stay unique
    for orig, copy_ in zip(CAT5_PRESETS, CAT5_ABLATION_PRESETS[:3]):
        assert copy_["ground_truth"] == orig["ground_truth"] and copy_["invoice_id"] == orig["invoice_id"]
    for p in CAT5_ABLATION_NEW_PRESETS:
        gt = p["ground_truth"]
        for k in ("decision", "authorized_net_principal_inr", "authorized_gst_payout_inr", "gst_escrow_holdback_inr",
                  "debit_note_deduction_inr", "required_evidence_tables", "optimal_tool_calls", "expected_escalation"):
            assert k in gt, (p["id"], k)
        assert set(gt["required_evidence_tables"]) >= {"vendor_invoices", "purchase_orders", "goods_receipts"}
        for k in DERIVATION_KEYS:
            assert p["derivation"].get(k), (p["id"], k)
        assert p["analysis_tier"] in ("routine", "dispute", "hard_stop")
        rows = ROWS_BY_INVOICE[p["id"]]
        inv = rows["vendor_invoices"][0]
        lines = rows["invoice_lines"]
        for ln in lines:
            assert ln["billed_line_total_inr"] == round(ln["billed_qty"] * ln["billed_unit_price_inr"], 2)
        assert inv["invoice_total_taxable_inr"] == round(sum(ln["billed_line_total_inr"] for ln in lines) + inv["claimed_freight_inr"], 2)
        assert inv["invoice_gst_inr"] == round(inv["invoice_total_taxable_inr"] * lines[0]["gst_rate"], 2)
        assert inv["invoice_grand_total_inr"] == p["invoice_grand_total_inr"] == round(inv["invoice_total_taxable_inr"] + inv["invoice_gst_inr"], 2)
        # Module 2.4 invariant on the hand figures (when not blocked)
        if gt["decision"] != "BLOCK_EXCEPTION_HOLD":
            assert abs(gt["authorized_net_principal_inr"] + gt["debit_note_deduction_inr"] - inv["invoice_total_taxable_inr"]) < 0.005
        else:
            assert all(gt[f] == 0.0 for f in ab.VOUCHER_FIELDS[1:])
        # the hand-written final figures appear in the worked derivation text
        assert f"{gt['authorized_net_principal_inr']:,.2f}" in p["derivation"]["authorized_net_principal_inr"]
        assert f"{gt['debit_note_deduction_inr']:,.2f}" in p["derivation"]["debit_note_deduction_inr"]


def test_default_matrix_equals_gate_and_exclusions_differ() -> None:
    for pid in CAT5_ABLATION_DEFAULT_INVOICE_IDS:
        cmp = ab.compare_with_gate(pid)
        assert cmp["agree"], (pid, cmp["differences"])
    assert set(CAT5_ABLATION_EXCLUDED_PENDING_REVIEW) == {"inv-06"}
    for pid in CAT5_ABLATION_DEFAULT_INVOICE_IDS:  # ... and with the pre-fix gate the experiment ran on
        assert ab.compare_with_gate(pid, ab.GATE_VERSION_V1)["agree"], pid
    for pid in CAT5_ABLATION_EXCLUDED_PENDING_REVIEW:
        cmp = ab.compare_with_gate(pid, ab.GATE_VERSION_V1)  # the recorded disagreement
        assert not cmp["agree"]
        assert cmp["differences"]["decision"] == {"derivation": "APPROVE_PARTIAL_DEBIT_NOTE", "gate": "APPROVE_CLEAN"}
        assert ab.compare_with_gate(pid)["agree"], ab.compare_with_gate(pid)["differences"]  # fixed gate = manual
    assert set(CAT5_ABLATION_DEFAULT_INVOICE_IDS) | set(CAT5_ABLATION_EXCLUDED_PENDING_REVIEW) == set(P)


def test_fixture_spread() -> None:
    tiers = [p["analysis_tier"] for p in CAT5_ABLATION_PRESETS]
    assert tiers.count("routine") >= 4 and tiers.count("dispute") >= 4 and tiers.count("hard_stop") == 2
    esc = [p["ground_truth"]["expected_escalation"] for p in CAT5_ABLATION_PRESETS if p["id"] in CAT5_ABLATION_DEFAULT_INVOICE_IDS]
    assert esc.count(True) >= 4 and esc.count(False) >= 4
    assert len({p["fc_hub"] for p in CAT5_ABLATION_NEW_PRESETS}) == 4
    assert len({p["vendor_name"] for p in CAT5_ABLATION_NEW_PRESETS}) == 9


# --------------------------------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------------------------------


def _hand_record(preset_id: str, voucher: dict[str, Any] | None, arm_id: str = "bundle_sonnet_cached") -> dict[str, Any]:
    pre = P[preset_id]
    return {
        "run_id": f"r-{preset_id}-{arm_id}-{id(voucher)}",
        "arm_id": arm_id,
        "preset_id": preset_id,
        "invoice_id": pre["invoice_id"],
        "repeat_index": 0,
        "status": "ok",
        "settings": ab.current_settings(arm_id, preset_id),
        "arm": {"cached": ab.ARMS[arm_id].cached},
        "turns": [{"turn_number": 1, "model_id": ab.ARMS[arm_id].start_model, "intended_model_id": ab.ARMS[arm_id].start_model,
                   "input_tokens": 1000, "output_tokens": 100, "cache_creation_tokens": 8600, "cache_read_tokens": 0,
                   "stop_reason": "end_turn", "tool_calls": [{"name": "fetch_3way_match_bundle"}, {"name": "commit_reconciliation_voucher"}]}],
        "turns_used": 1,
        "committed_voucher": voucher,
        "all_vouchers": [voucher] if voucher else [],
        "tables_touched": ["vendor_invoices", "purchase_orders", "goods_receipts", "contract_amendments", "vendors"],
        "total_tool_calls": 2,
        "optimal_tool_calls": 2,
        "cap_hit": False,
        "escalation_fired": False,
        "final_message": "msg",
    }


def _voucher(preset_id: str, **override: Any) -> dict[str, Any]:
    pre = P[preset_id]
    v = {k: pre["ground_truth"][k] for k in ab.VOUCHER_FIELDS}
    v.update({"voucher_id": "VCH-x", "invoice_id": pre["invoice_id"], "po_id": pre["po_id"], "gate_verified": 0, "audit_summary": ""})
    v.update(override)
    return v


def test_scoring_hand_built_vouchers() -> None:
    exact = ab.score_record(_hand_record("inv-12", _voucher("inv-12")))
    assert exact["exact"] and exact["decision_correct"] and exact["committed"] and exact["field_accuracy_pct"] == 100.0
    near = ab.score_record(_hand_record("inv-12", _voucher("inv-12", gst_escrow_holdback_inr=875254.4)))  # +0.80 within ±1
    assert near["exact"]
    off = ab.score_record(_hand_record("inv-12", _voucher("inv-12", debit_note_deduction_inr=198480.0)))
    assert not off["exact"] and off["decision_correct"] and off["fields"]["debit_note_deduction_inr"] is False
    assert off["field_accuracy_pct"] == 80.0
    wrong = ab.score_record(_hand_record("inv-12", _voucher("inv-12", decision="APPROVE_WITH_GST_ESCROW")))
    assert not wrong["exact"] and not wrong["decision_correct"]
    none = ab.score_record(_hand_record("inv-12", None))
    assert not none["committed"] and not none["exact"] and not none["decision_correct"] and none["field_accuracy_pct"] == 0.0
    assert exact["tool_precision_pct"] == 100.0 and exact["evidence_recall_pct"] == 100.0


def test_cost_views() -> None:
    rec = run("raw_free_sonnet", "inv-01", Scripted([("end_turn", [], "x")]))
    c = ab.record_costs_usd(rec)
    assert c["billed"] == c["cold"] == c["warm"] > 0
    rec2 = run("bundle_gate_sonnet_cached", "inv-01", Scripted(governed_script("inv-01")))
    c2 = ab.record_costs_usd(rec2)
    # fake: turn 1 writes 8,600, turns 2-4 read it -> billed equals cold; warm reads on turn 1 too
    assert abs(c2["billed"] - c2["cold"]) < 1e-9 and c2["warm"] < c2["cold"]


def test_lever_table_maths() -> None:
    def m(exact: int, n: int, billed: float, cold: float, warm: float) -> dict[str, Any]:
        return {"runs": n, "exact": ab._rate_block(exact, n), "decision_correct": ab._rate_block(exact, n),
                "cost_per_1k_invoices_usd": {"billed": billed, "cold": cold, "warm": warm}}

    metrics = {
        "raw_free_sonnet": m(18, 36, 240.0, 240.0, 240.0),
        "raw_free_sonnet_cached": m(27, 36, 150.0, 150.0, 120.0),
        "bundle_sonnet_cached": m(36, 36, 50.0, 50.0, 30.0),
    }
    rows = {r["lever"]: r for r in ab.lever_table(metrics)}
    c = rows["caching alone"]
    assert c["available"] and c["changes"] == ["cached: False -> True"]
    assert c["exact"]["delta_pp"] == pytest.approx(25.0)
    assert c["cost_per_1k_invoices_usd"]["billed"]["delta"] == pytest.approx(-90.0)
    assert c["cost_per_1k_invoices_usd"]["billed"]["ratio"] == pytest.approx(0.625)
    assert c["cost_per_1k_invoices_usd"]["warm"]["delta"] == pytest.approx(-120.0)
    assert rows["narrow query"]["exact"]["delta_pp"] == pytest.approx(25.0)
    assert not rows["deterministic gate"]["available"]
    assert "gate: False -> True" in rows["deterministic gate"]["changes"]
    assert "prompt: neutral -> bounded_sonnet_cached_gate" in rows["deterministic gate"]["changes"]


# --------------------------------------------------------------------------------------------------
# Resume, superseded settings, budget guard, plan order
# --------------------------------------------------------------------------------------------------


def test_plan_order_resume_and_superseded() -> None:
    planned = ab.plan_matrix(["a1", "a2"], ["inv-01", "inv-02"], 2)
    assert planned[:4] == [("a1", "inv-01", 0), ("a2", "inv-01", 0), ("a1", "inv-02", 0), ("a2", "inv-02", 0)]
    assert planned[4] == ("a1", "inv-01", 1)

    ok = _hand_record("inv-01", _voucher("inv-01"))
    err = {**_hand_record("inv-02", None), "status": "error"}
    stale = _hand_record("inv-03", _voucher("inv-03"))
    stale["settings"] = {**stale["settings"], "max_tokens_per_turn": 2048}
    plan = [("bundle_sonnet_cached", p, 0) for p in ("inv-01", "inv-02", "inv-03", "inv-04")]
    pending = ab.select_pending(plan, [ok, err, stale])
    assert pending == plan[1:]
    assert ab.is_current_settings(ok) and not ab.is_current_settings(stale)
    sup = ab.superseded_records([ok, err, stale])
    assert len(sup) == 1 and sup[0]["recorded"]["max_tokens_per_turn"] == 2048
    tampered = _hand_record("inv-01", None)
    tampered["settings"] = {**tampered["settings"], "invoice_fingerprint": "different"}
    assert not ab.is_current_settings(tampered)
    latest = ab.latest_ok_current([ok, err, stale])
    assert list(latest) == [("bundle_sonnet_cached", "inv-01", 0)]


def test_budget_guard() -> None:
    rec = _hand_record("inv-01", None)
    cost = ab.record_billed_usd(rec)
    g = ab.BudgetGuard(1.0, [rec])
    assert g.spent_usd == pytest.approx(cost)
    assert g.try_reserve(0.5)
    assert not g.try_reserve(0.6)  # spent + 0.5 reserved + 0.6 > 1.0
    g.settle(0.5, rec)
    assert g.reserved_usd == 0.0 and g.spent_usd == pytest.approx(2 * cost)


def test_dry_run_estimates_are_calibrated_and_ordered() -> None:
    cal = ab.calibrate()
    assert cal.source.endswith("cat5_golden_replays.json")
    ests = {a: ab.estimate_run(a, P["inv-02"], cal) for a in ab.ARM_IDS}
    for e in ests.values():
        assert 0 < e["typical_usd"] <= e["worst_case_usd"]
    assert ests["raw_free_sonnet"]["typical_usd"] > ests["raw_free_sonnet_cached"]["typical_usd"] > ests["bundle_sonnet_cached"]["typical_usd"]
    assert ests["bundle_haiku_cached"]["typical_usd"] < ests["bundle_sonnet_cached"]["typical_usd"]
    m = ab.estimate_matrix(ab.plan_matrix(list(ab.ARM_IDS), list(CAT5_ABLATION_DEFAULT_INVOICE_IDS), 1), cal)
    assert set(m["per_arm"]) == set(ab.ARM_IDS) and m["total_typical_usd"] > 0


# --------------------------------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------------------------------


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, BACKEND / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_analysis_with_zero_records(tmp_path: Path) -> None:
    s = ab.summarise([])
    assert s["ok_runs_used"] == 0 and s["arms"]["raw_free_sonnet"]["exact"]["rate"] is None
    assert all(not row["available"] for row in s["levers"])
    assert len(s["baseline"]["golden_scripted"]) == 3
    md = ab.render_markdown(s)
    assert "Lever table" in md and "inv-06" in md
    mod = _load_script("analyze_cat5_ablation")
    out_md = tmp_path / "a.md"
    assert mod.main(["--in", str(tmp_path / "missing.jsonl"), "--out-md", str(out_md)]) == 0
    assert out_md.is_file() and json.loads(out_md.with_suffix(".json").read_text())["record_count"] == 0


def test_analysis_with_records(tmp_path: Path) -> None:
    recs = [
        run("bundle_sonnet_cached", "inv-04", Scripted(bundle_script("inv-04"))),
        run("bundle_sonnet_cached", "inv-05", Scripted(bundle_script("inv-05", debit_note_deduction_inr=0.0))),
        run("bundle_gate_sonnet_cached", "inv-04", Scripted(governed_script("inv-04"))),
        run("bundle_gate_sonnet_cached", "inv-05", Scripted(governed_script("inv-05")), sink={}),
        {**run("bundle_gate_sonnet_cached", "inv-05", Scripted(governed_script("inv-05"), fail_on=1), repeat_index=1)},
    ]
    stale = run("bundle_sonnet_cached", "inv-04", Scripted(bundle_script("inv-04")))
    stale["settings"] = {**stale["settings"], "turn_cap": 99}
    recs.append(stale)
    s = ab.summarise(recs, preset_ids=["inv-04", "inv-05"], expected_repeats=1)
    a = s["arms"]["bundle_sonnet_cached"]
    assert a["runs"] == 2 and a["exact"]["k"] == 1 and a["decision_correct"]["k"] == 2
    assert a["by_tier"]["routine"]["exact"]["k"] == 1 and a["by_tier"]["dispute"]["exact"]["k"] == 0
    assert a["tool_calls_per_run"] == {"commit_reconciliation_voucher": 1.0, "fetch_3way_match_bundle": 1.0}
    g = s["arms"]["bundle_gate_sonnet_cached"]
    assert g["runs"] == 2 and g["exact"]["k"] == 2 and g["escalation"]["gate_flagged"] == 1
    lever = next(r for r in s["levers"] if r["lever"] == "deterministic gate")
    assert lever["available"] and lever["exact"]["delta_pp"] == pytest.approx(50.0)
    assert [e["preset_id"] for e in s["for_lead_review"]] == ["inv-05"]
    assert s["for_lead_review"][0]["mismatched_fields"] == ["debit_note_deduction_inr"]
    dq = s["data_quality"]
    assert len(dq["errors"]) == 1 and len(dq["superseded_records"]) == 1 and dq["cache_anomalies"] == []
    assert not s["matrix"]["complete"] and len(s["matrix"]["missing_keys"]) == 8 and s["matrix"]["balanced"] is False
    two = ab.summarise(recs, arm_ids=["bundle_sonnet_cached", "bundle_gate_sonnet_cached"], preset_ids=["inv-04", "inv-05"], expected_repeats=1)
    assert two["matrix"]["complete"] and two["matrix"]["balanced"]
    md = ab.render_markdown(s)
    assert "bundle_sonnet_cached / inv-05 / r0" in md
    path = tmp_path / "runs.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    out_md = tmp_path / "out.md"
    assert _load_script("analyze_cat5_ablation").main(["--in", str(path), "--out-md", str(out_md), "--invoices", "inv-04,inv-05"]) == 0
    assert "deterministic gate" in out_md.read_text()


def test_runner_cli_dry_run(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    mod = _load_script("cat5_ablation")
    rc = asyncio.run(mod.run_matrix(mod.parse_args(["--dry-run", "--out", str(tmp_path / "runs.jsonl"), "--repeats", "1"])))
    out = capsys.readouterr().out
    assert rc == 0 and "66 pending" in out and "TOTAL typical" in out and "no API calls" in out
    assert not (tmp_path / "runs.jsonl").exists()


# --------------------------------------------------------------------------------------------------
# Follow-up: stop-reason robustness, harness-artefact records, gate-disagreement group, tool-use report
# --------------------------------------------------------------------------------------------------

PINNED_INVOICE_FP = {
    "inv-01": "7cf8887fd14c32e5", "inv-02": "a2863817d86a8d20", "inv-03": "a1eec6da9fd884c2", "inv-04": "ab5d8a45ad022f55",
    "inv-05": "b00d2b4e4745b105", "inv-06": "f9d0dee6c94f3058", "inv-07": "b4cca9f670e84fbd", "inv-08": "b98a32b944a8b5b5",
    "inv-09": "ef4f2e61a1a7cba9", "inv-10": "194a3141c2e06e21", "inv-11": "03d7cc95b28df22f", "inv-12": "4585cf644d485303",
}
PINNED_ARM_FP = {
    "raw_free_sonnet": "fa74bab5f98fe213", "raw_free_sonnet_cached": "822ce1258d319483",
    "bundle_sonnet_cached": "939b70b26767c959", "bundle_gate_sonnet_cached": "12bad949bbbfe136",
    "bundle_haiku_cached": "5e361d76fef73f56", "bundle_gate_haiku_escalate": "6bd6026d3c4df79a",
}


def test_fingerprints_pinned_so_recorded_runs_stay_current() -> None:
    from app.data.cat5_ablation_fixtures import invoice_fingerprint

    assert {p: invoice_fingerprint(p) for p in PINNED_INVOICE_FP} == PINNED_INVOICE_FP
    assert {a: ab.arm_fingerprint(a) for a in ab.ARM_IDS} == PINNED_ARM_FP


def test_end_turn_with_tool_use_blocks_executes_and_continues() -> None:
    pre = P["inv-05"]
    agent = Scripted([
        ("end_turn", [("query_invoice_raw", {"invoice_id": pre["invoice_id"]}), ("query_po_raw", {"po_id": pre["po_id"]})],
         "I'll pull the invoice and PO in parallel."),
        ("tool_use", [("commit_reconciliation_voucher", _commit_input(pre))], ""),
        ("end_turn", [], "Summary."),
    ])
    rec = run("raw_free_sonnet", "inv-05", agent)
    t1 = rec["turns"][0]
    assert [c["name"] for c in t1["tool_calls"]] == ["query_invoice_raw", "query_po_raw"]
    assert all(c["executed"] for c in t1["tool_calls"]) and t1["tool_calls_not_executed"] == []
    assert t1["tool_use_with_stop_reason"] == "end_turn"
    assert len(agent.calls) == 3 and [r["tool_use_id"] for r in agent.calls[1]["messages"][-1]["content"]] == ["tu_1_0", "tu_1_1"]
    assert rec["committed_voucher"] is not None and rec["ended_with_stop_reason"] == "end_turn"
    assert not ab.harness_artifact(rec) and ab.is_current_settings(rec)
    assert rec["settings"]["loop_rule"] == ab.LOOP_RULE
    dq = ab.data_quality([rec], [rec])
    assert dq["tool_use_blocks_with_other_stop_reason"][0]["stop_reason"] == "end_turn"


def test_truncated_turn_is_not_an_artifact() -> None:
    pre = P["inv-04"]
    rec = run("bundle_sonnet_cached", "inv-04",
              Scripted([("max_tokens", [("fetch_3way_match_bundle", {"invoice_id": pre["invoice_id"]})], "")]))
    assert rec["turns"][0]["tool_calls_not_executed"] and rec["turns"][0]["truncated"]
    assert not ab.harness_artifact(rec) and ab.is_current_settings(rec)
    assert ab.select_pending([("bundle_sonnet_cached", "inv-04", 0)], [rec]) == []


def _v1_artifact_record() -> dict[str, Any]:
    """A record as the v1 loop wrote it: end_turn + unexecuted tool_use blocks on a non-truncated turn."""
    rec = run("raw_free_sonnet", "inv-05", Scripted([("end_turn", [], "I'll start by pulling the data in parallel.")]))
    rec["turns"][0]["tool_calls_not_executed"] = [
        {"tool_use_id": "toolu_x", "name": "query_invoice_raw", "input": {"invoice_id": P["inv-05"]["invoice_id"]}},
        {"tool_use_id": "toolu_y", "name": "query_po_raw", "input": {"po_id": P["inv-05"]["po_id"]}},
    ]
    return rec


def test_artifact_record_is_superseded_retried_and_excluded() -> None:
    art = _v1_artifact_record()
    good = run("raw_free_sonnet", "inv-01", Scripted([("end_turn", [], "x")]))
    assert ab.harness_artifact(art) and not ab.is_current_settings(art)
    keys = [("raw_free_sonnet", "inv-05", 0), ("raw_free_sonnet", "inv-01", 0)]
    assert ab.select_pending(keys, [art, good]) == [keys[0]]
    sup = ab.superseded_records([art, good])
    assert [s["reason"] for s in sup] == ["harness ended the run with tool calls not executed"]
    s = ab.summarise([art, good], arm_ids=["raw_free_sonnet"], preset_ids=["inv-01", "inv-05"], expected_repeats=1)
    assert s["ok_runs_used"] == 1 and s["matrix"]["missing_keys"] == [["raw_free_sonnet", "inv-05", 0]]
    md = ab.render_markdown(s)
    assert "superseded: harness ended the run with tool calls not executed — raw_free_sonnet / inv-05 / r0" in md
    # a fresh retry appended after the artefact is used
    retry = run("raw_free_sonnet", "inv-05", Scripted([
        ("tool_use", [("commit_reconciliation_voucher", _commit_input(P["inv-05"]))], ""), ("end_turn", [], "ok")]))
    assert ab.select_pending(keys, [art, good, retry]) == []
    assert ab.latest_ok_current([art, good, retry])[keys[0]]["run_id"] == retry["run_id"]


def test_groups_and_both_truths_for_inv06() -> None:
    from app.data.cat5_ablation_fixtures import CAT5_ABLATION_GATE_DISAGREEMENT, CAT5_ABLATION_GROUPS

    assert CAT5_ABLATION_GROUPS["default"] == CAT5_ABLATION_DEFAULT_INVOICE_IDS and len(CAT5_ABLATION_DEFAULT_INVOICE_IDS) == 11
    assert CAT5_ABLATION_GROUPS["gate_disagreement"] == ("inv-06",)
    pre = P["inv-06"]
    assert pre["ground_truth"]["decision"] == "APPROVE_PARTIAL_DEBIT_NOTE" and pre["ground_truth"]["debit_note_deduction_inr"] == 22800.0
    # gate_output_truth is frozen: what the pre-fix gate returned on 2026-11-26 (reproduced by the v1 gate)
    g = ab.gate_output_for("inv-06", ab.GATE_VERSION_V1)
    got = {"decision": g["recommended_decision"], **{f: g[f] for f in ab.VOUCHER_FIELDS[1:]}, "expected_escalation": g["escalation_required"]}
    assert pre["gate_output_truth"] == got == CAT5_ABLATION_GATE_DISAGREEMENT["inv-06"]["gate_output_truth"]
    assert "before the fix" in CAT5_ABLATION_GATE_DISAGREEMENT["inv-06"]["gate_output_note"]
    assert "gate_output_truth" not in pre["ground_truth"]
    # the FIXED gate now equals the manual derivation on inv-06
    g2 = ab.gate_output_for("inv-06")
    fixed = {"decision": g2["recommended_decision"], **{f: g2[f] for f in ab.VOUCHER_FIELDS[1:]}, "expected_escalation": g2["escalation_required"]}
    assert fixed == {f: pre["ground_truth"][f] for f in (*ab.VOUCHER_FIELDS, "expected_escalation")}
    assert g2["line_findings"][0]["price_rule"] == "WITHIN_1.5PCT_NOT_INDEX_LINKED_PO_RATE"


def test_gate_disagreement_section_and_never_pooled() -> None:
    pre = P["inv-06"]
    gate_vals = {k: v for k, v in pre["gate_output_truth"].items() if k != "expected_escalation"}
    recs = [
        run("bundle_sonnet_cached", "inv-06", Scripted(bundle_script("inv-06"))),  # manual figures
        run("raw_free_sonnet", "inv-06", Scripted([
            ("tool_use", [("query_po_raw", {"po_id": pre["po_id"]})], ""),
            ("tool_use", [("commit_reconciliation_voucher", _commit_input(pre, **gate_vals))], ""), ("end_turn", [], "ok")])),
        run("bundle_haiku_cached", "inv-06", Scripted(bundle_script("inv-06", authorized_net_principal_inr=3600000.0))),
        run("raw_free_sonnet_cached", "inv-06", Scripted([("end_turn", [], "no commit")])),
        run("bundle_sonnet_cached", "inv-04", Scripted(bundle_script("inv-04"))),
    ]
    gated = run("bundle_gate_sonnet_cached", "inv-06", Scripted([
        ("tool_use", [("fetch_3way_match_bundle", {"invoice_id": pre["invoice_id"]})], ""),
        ("tool_use", [("run_policy_tolerance_gate", {"invoice_id": pre["invoice_id"]})], ""),
        ("tool_use", [("commit_reconciliation_voucher", _commit_input(pre, **gate_vals))], ""), ("end_turn", [], "ok")]))
    assert gated["settings"]["gate_version"] == ab.GATE_VERSION
    legacy = json.loads(json.dumps(gated))  # a record written before the fix: no gate_version / bundle_version
    for k in ("gate_version", "bundle_version"):
        legacy["settings"].pop(k)
    after = run("bundle_gate_sonnet_cached", "inv-06", Scripted([
        ("tool_use", [("fetch_3way_match_bundle", {"invoice_id": pre["invoice_id"]})], ""),
        ("tool_use", [("run_policy_tolerance_gate", {"invoice_id": pre["invoice_id"]})], ""),
        ("tool_use", [("commit_reconciliation_voucher", _commit_input(pre))], ""), ("end_turn", [], "ok")]))
    recs += [legacy, after]
    assert ab.is_current_settings(legacy) and not ab.is_current_gate(legacy) and ab.is_current_gate(after)
    assert not ab.superseded_records([legacy])  # before-fix evidence, not superseded
    s = ab.summarise(recs, preset_ids=["inv-04", "inv-06"], expected_repeats=1)
    assert s["preset_ids"] == ["inv-04"] and s["pooled_excludes"] == ["inv-06"]
    assert s["arms"]["bundle_sonnet_cached"]["runs"] == 1 and "inv-06" not in s["arms"]["bundle_sonnet_cached"]["by_invoice"]
    assert all(e["preset_id"] != "inv-06" for e in s["for_lead_review"])
    sec = s["gate_disagreement"]["inv-06"]
    pa = sec["per_arm"]
    assert (pa["bundle_sonnet_cached"]["matches_manual"], pa["bundle_sonnet_cached"]["line1_rate"]) == (1, {"po_rate": 1})
    assert (pa["raw_free_sonnet"]["matches_gate_output"], pa["raw_free_sonnet"]["line1_rate"]) == (1, {"billed_rate": 1})
    assert pa["raw_free_sonnet"]["decisions"] == {"APPROVE_CLEAN": 1}
    assert pa["bundle_haiku_cached"]["neither"] == 1 and pa["bundle_haiku_cached"]["line1_rate"] == {"other": 1}
    assert pa["raw_free_sonnet_cached"]["no_commit"] == 1 and pa["raw_free_sonnet_cached"]["decisions"] == {"(no commit)": 1}
    assert pa["bundle_gate_sonnet_cached"]["matches_gate_output"] == 1 and pa["bundle_gate_sonnet_cached"]["gate_arm"]
    assert pa["bundle_gate_haiku_escalate"]["runs"] == 0 and sec["missing_keys"] == [["bundle_gate_haiku_escalate", "inv-06", 0]]
    af = sec["after_fix"]
    assert af["gate_version"] == ab.GATE_VERSION and set(af["per_arm"]) == {"bundle_gate_sonnet_cached", "bundle_gate_haiku_escalate"}
    assert af["per_arm"]["bundle_gate_sonnet_cached"]["matches_manual"] == 1 and af["per_arm"]["bundle_gate_haiku_escalate"]["runs"] == 0
    assert af["missing_keys"] == [["bundle_gate_haiku_escalate", "inv-06", 0]]
    assert sec["gate_fix"]["current_gate_matches_manual"] is True
    assert s["run_ids"]["gate_disagreement"]["bundle_gate_sonnet_cached"] == [legacy["run_id"]]
    assert s["run_ids"]["gate_disagreement_after_fix"]["bundle_gate_sonnet_cached"] == [after["run_id"]]
    md = ab.render_markdown(s)
    assert "### Before the fix (recorded, gate v1-band-unconditional)" in md and "### After the fix (gate v2-manual-aligned" in md
    assert "| bundle_gate_haiku_escalate | 0 | - | - | - | - | not run yet | - |" in md
    assert "## When the deterministic gate is wrong (inv-06)" in md
    assert "MAY pass ONLY when PO currency notes specify index-linked float" in md
    assert "3,656,000.00" in md and "3,678,800.00" in md and "did not return purchase_orders.currency" in md
    assert "| bundle_sonnet_cached | 1 | 1 | 0 | 0 | 0 | APPROVE_PARTIAL_DEBIT_NOTE 1 | 1 / 0 / 0 |" in md
    assert "| bundle_gate_sonnet_cached | 1 | 0 | 1 | 0 | 0 | APPROVE_CLEAN 1 | gate computes (n/a) |" in md


def test_tool_use_report_and_notes() -> None:
    pre = P["inv-01"]
    rec = run("raw_free_sonnet", "inv-01", Scripted([
        ("tool_use", [("query_invoice_raw", {"invoice_id": pre["invoice_id"]}), ("query_vendor_audit_history", {"vendor_id": "VND-BLR-401"}),
                      ("run_policy_tolerance_gate", {"invoice_id": pre["invoice_id"]})], ""),
        ("tool_use", [("commit_reconciliation_voucher", _commit_input(pre))], ""), ("end_turn", [], "ok")]))
    s = ab.summarise([rec], arm_ids=["raw_free_sonnet"], preset_ids=["inv-01"], expected_repeats=1)
    m = s["arms"]["raw_free_sonnet"]
    assert list(m["tool_calls_per_run"])[:6] == [t["name"] for t in NAIVE_TOOLS]
    assert m["tool_calls_per_run"]["query_po_raw"] == 0 and m["tool_calls_per_run"]["query_vendor_audit_history"] == 1
    assert m["runs_calling_tool"]["query_vendor_audit_history"] == 1 and m["runs_calling_tool"]["query_po_raw"] == 0
    assert m["disallowed_tool_calls"] == {"total": 1, "per_run": 1.0, "by_name": {"run_policy_tolerance_gate": 1}}
    md = ab.render_markdown(s)
    assert "## Tool use" in md and "Raw arms: how often each raw SELECT * tool was called" in md
    assert "Tool precision is not comparable between raw and bundle arms" in md
    assert "## Analysis notes" in md
    for needle in ("4-step budget", "debit note is above zero", "Haiku", "-UNB", "approved_freight_waiver_inr", "max_retries=2"):
        assert needle in md
    empty = ab.render_markdown(ab.summarise([]))
    assert "## Tool use" in empty and "When the deterministic gate is wrong (inv-06)" in empty


def test_runner_cli_group_dry_run(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    mod = _load_script("cat5_ablation")
    rc = asyncio.run(mod.run_matrix(mod.parse_args(["--dry-run", "--group", "gate_disagreement", "--out", str(tmp_path / "r.jsonl")])))
    cap = capsys.readouterr()
    assert rc == 0 and "6 arms x 1 invoices x 3 repeats = 18 runs" in cap.out and "group gate_disagreement" in cap.out
    assert "WARNING" not in cap.err
    rc = asyncio.run(mod.run_matrix(mod.parse_args(["--dry-run", "--invoices", "inv-06", "--repeats", "1", "--out", str(tmp_path / "r.jsonl")])))
    assert rc == 0 and "WARNING" not in capsys.readouterr().err
