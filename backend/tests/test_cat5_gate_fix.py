"""Category 5 policy-gate fixes (gate v2-manual-aligned, 2026-11-26) and the bundle's added fields, with the
recorded experiment kept reproducible. No live API calls.

Fixes, each tested on synthetic rows (positive and negative): the 1.5% band only for index-linked POs (2.1); the
approved freight waiver of a signed amendment (2.2/2.3); GST at each line's own rate (1.1(a)/3.2); Trigger 3,
duplicate invoice or PAYMENT_FREEZE vendor (4.1)."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat5_orchestration import ablation as ab  # noqa: E402
from app.archetypes.cat5_orchestration.erp_db import (  # noqa: E402
    BUNDLE_VERSION,
    BUNDLE_VERSION_V1,
    GATE_VERSION,
    GATE_VERSION_V1,
    HARD_BLOCK_ROUTE,
    PRICE_RULE_WITHIN_BAND,
    PRICE_RULE_WITHIN_BAND_NOT_INDEX_LINKED,
    Cat5ErpSession,
    evaluate_deterministic_policy_gate,
    po_currency_index_linked,
)
from app.data.cat5_ablation_fixtures import (  # noqa: E402
    CAT5_ABLATION_DEFAULT_INVOICE_IDS,
    CAT5_ABLATION_ERP_ROWS,
    CAT5_ABLATION_PRESETS_BY_ID,
)

RUNS = BACKEND_DIR / "experiments" / "cat5_ablation" / "runs.jsonl"
HAVE_RECORDS = RUNS.is_file()
INV06 = CAT5_ABLATION_PRESETS_BY_ID["inv-06"]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------------ the predicate


@pytest.mark.parametrize(
    ("notes", "linked"),
    [
        ("INR", False),
        ("", False),
        (None, False),
        ("INR fixed price", False),
        ("INR (index-linked float: LME copper)", True),
        ("INR Index Linked float", True),
        ("inr; INDEX_LINKED", True),
        ("indexlinked float", True),
        ("INR, linked to an index", False),  # only the manual's wording counts
        ("INR fixed; index-linked float (LME copper)", True),
        ("INR; no surcharge, index-linked float", True),  # the negation is in another clause
        # negated forms
        ("INR - not index linked", False),
        ("INR, not index-linked", False),
        ("INR non-index-linked", False),
        ("Non_Index_Linked INR", False),
        ("INR, no index linked float", False),
        ("INR without index-linked pricing", False),
        ("INR, not an index-linked float", False),
        ("never indexlinked", False),
    ],
)
def test_po_currency_index_linked(notes: Any, linked: bool) -> None:
    assert po_currency_index_linked(notes) is linked


def test_every_seeded_po_is_plain_inr() -> None:
    s = ab.AblationErpSession(rung_id="bounded_sonnet_cached_gate")
    try:
        cur = [r[0] for r in s.conn.execute("SELECT currency FROM purchase_orders")]
    finally:
        s.close()
    assert cur and set(cur) == {"INR"} and not any(po_currency_index_linked(c) for c in cur)


# ------------------------------------------------------------------------ synthetic ERP rows


def _rows(*, currency: str = "INR", billed_rate: float | None = None) -> dict[str, list[dict[str, Any]]]:
    """The ablation rows with inv-06's PO currency notes and/or line-1 billed rate changed."""
    rows = copy.deepcopy(CAT5_ABLATION_ERP_ROWS)
    for po in rows["purchase_orders"]:
        if po["po_id"] == INV06["po_id"]:
            po["currency"] = currency
    if billed_rate is not None:
        for ln in rows["invoice_lines"]:
            if ln["invoice_id"] == INV06["invoice_id"] and ln["sku"] == "NM-CBL-1.5SQ-90M":
                ln["billed_unit_price_inr"] = billed_rate
    return rows


def _gate(rows: dict[str, list[dict[str, Any]]], version: str = GATE_VERSION) -> dict[str, Any]:
    s = ab.AblationErpSession(rung_id="bounded_sonnet_cached_gate", extra_rows=rows)
    try:
        return evaluate_deterministic_policy_gate(s.conn, INV06["invoice_id"], gate_version=version)
    finally:
        s.close()


def test_index_linked_po_inside_band_passes_at_billed_rate() -> None:
    g = _gate(_rows(currency="INR (index-linked float: LME copper)"))
    l1 = g["line_findings"][0]
    assert l1["price_rule"] == PRICE_RULE_WITHIN_BAND
    assert (l1["effective_unit_price_inr"], l1["line_deduction_inr"]) == (1499.0, 0.0)
    assert g["recommended_decision"] == "APPROVE_CLEAN" and g["debit_note_deduction_inr"] == 0.0
    assert g["authorized_net_principal_inr"] == 3678800.0


def test_plain_po_inside_band_pays_po_rate_with_deduction() -> None:
    g = _gate(_rows(currency="INR"))
    l1 = g["line_findings"][0]
    assert l1["price_rule"] == PRICE_RULE_WITHIN_BAND_NOT_INDEX_LINKED
    assert l1["effective_unit_price_inr"] == 1480.0
    assert l1["line_deduction_inr"] == pytest.approx(1200 * (1499.0 - 1480.0)) == 22800.0
    assert g["recommended_decision"] == "APPROVE_PARTIAL_DEBIT_NOTE"
    assert (g["authorized_net_principal_inr"], g["authorized_gst_payout_inr"], g["debit_note_deduction_inr"]) == (3656000.0, 658080.0, 22800.0)
    assert g["escalation_required"] is True
    gt = INV06["ground_truth"]  # equals the manual derivation
    assert g["recommended_decision"] == gt["decision"] and g["authorized_net_principal_inr"] == gt["authorized_net_principal_inr"]
    # the pre-fix gate (kept for replay only) still passes the band unconditionally
    g1 = _gate(_rows(currency="INR"), GATE_VERSION_V1)
    assert g1["line_findings"][0]["price_rule"] == PRICE_RULE_WITHIN_BAND and g1["recommended_decision"] == "APPROVE_CLEAN"


@pytest.mark.parametrize("currency", ["INR", "INR (index-linked float: LME copper)"])
def test_rise_above_band_is_unaffected_by_the_fix(currency: str) -> None:
    rows = _rows(currency=currency, billed_rate=1520.0)  # +2.7% > 1.5%
    g2, g1 = _gate(rows), _gate(rows, GATE_VERSION_V1)
    assert g2 == g1
    l1 = g2["line_findings"][0]
    assert l1["price_rule"] == "UNAUTHORIZED_HIKE_CAPPED_TO_PO" and l1["effective_unit_price_inr"] == 1480.0


def test_unknown_versions_are_rejected() -> None:
    with pytest.raises(ValueError):
        Cat5ErpSession(rung_id="bounded_sonnet_cached_gate", gate_version="v3")
    with pytest.raises(ValueError):
        Cat5ErpSession(rung_id="bounded_sonnet_cached_gate", bundle_version="v3")


# ------------------------------------------------------------------------ the three other gaps (synthetic rows)
#
# Each test edits a fresh in-memory ERP (the ablation rows) with SQL and runs the gate. Hand derivations in comments.

INV04, INV09, INV01, INV03 = "INV-TS-2026-1184", "INV-HR-2026-5826", "INV-KA-2026-9921", "INV-DL-2026-8803"
ZERO4 = ("authorized_net_principal_inr", "authorized_gst_payout_inr", "gst_escrow_holdback_inr", "debit_note_deduction_inr")


def _gate_sql(invoice_id: str, *sql: tuple[str, tuple[Any, ...]], version: str = GATE_VERSION) -> dict[str, Any]:
    s = ab.AblationErpSession(rung_id="bounded_sonnet_cached_gate")
    try:
        for stmt, params in sql:
            s.conn.execute(stmt, params)
        return evaluate_deterministic_policy_gate(s.conn, invoice_id, gate_version=version)
    finally:
        s.close()


def _amend(waiver: float, status: str = "SIGNED_ACTIVE", amd: str = "AMD-DEL-5826-FW") -> tuple[str, tuple[Any, ...]]:
    # sku not on the invoice, so the amendment changes no unit rate: only its freight waiver can matter
    return (
        "INSERT INTO contract_amendments VALUES (?, 'PO-NM-DEL-5826', 'FREIGHT', 0, ?, ?, 'CFD+VP Procurement', 'freight waiver')",
        (amd, waiver, status),
    )


def _rate(invoice_id: str, sku: str, rate: float, *, invoice_too: bool = True) -> list[tuple[str, tuple[Any, ...]]]:
    out = [("UPDATE po_lines SET gst_rate = ? WHERE sku = ? AND po_id = (SELECT po_id FROM vendor_invoices WHERE invoice_id = ?)",
            (rate, sku, invoice_id))]
    if invoice_too:
        out.append(("UPDATE invoice_lines SET gst_rate = ? WHERE invoice_id = ? AND sku = ?", (rate, invoice_id, sku)))
    return out


def _voucher(invoice_id: str, po_id: str) -> tuple[str, tuple[Any, ...]]:
    return (
        "INSERT INTO reconciliation_vouchers VALUES ('VCH-PRIOR-0001', ?, ?, 'APPROVE_CLEAN', 1, 0, 0, 0, 1, 'posted earlier')",
        (invoice_id, po_id),
    )


def _freeze(invoice_id: str, flag: str = "PAYMENT_FREEZE") -> tuple[str, tuple[Any, ...]]:
    return ("UPDATE vendors SET risk_flag = ? WHERE vendor_id = (SELECT vendor_id FROM vendor_invoices WHERE invoice_id = ?)",
            (flag, invoice_id))


# --- 2.2 / 2.3 freight waiver.  inv-09 (INV-HR-2026-5826): lines 3,100,000 + 1,380,000, PO cap 18,000, claimed 27,500.


def test_no_waiver_disallows_the_excess_freight() -> None:
    g = _gate_sql(INV09)
    assert (g["authorized_net_principal_inr"], g["debit_note_deduction_inr"], g["freight_disallowed_inr"]) == (4498000.0, 9500.0, 9500.0)
    assert "freight_waiver_applied_inr" not in g and g == _gate_sql(INV09, version=GATE_VERSION_V1)


def test_signed_waiver_covering_the_excess_allows_all_freight() -> None:
    # cap 18,000 + waiver 9,500 = 27,500 -> freight 27,500 allowed; net 4,480,000 + 27,500 = 4,507,500;
    # GST ROUND(4,507,500 x 0.18, 2) = 811,350; debit 0 -> APPROVE_CLEAN; one discrepancy (freight over PO cap), no escalation
    g = _gate_sql(INV09, _amend(9500.0))
    assert (g["recommended_decision"], g["authorized_net_principal_inr"], g["authorized_gst_payout_inr"],
            g["debit_note_deduction_inr"], g["freight_disallowed_inr"], g["freight_waiver_applied_inr"]) == (
        "APPROVE_CLEAN", 4507500.0, 811350.0, 0.0, 0.0, 9500.0)
    assert g["escalation_required"] is False
    # the pre-fix gate ignored the waiver
    assert _gate_sql(INV09, _amend(9500.0), version=GATE_VERSION_V1)["debit_note_deduction_inr"] == 9500.0


def test_partial_waiver_disallows_the_rest() -> None:
    # cap 18,000 + 5,000 = 23,000 allowed; 4,500 disallowed; net 4,503,000; GST 810,540
    g = _gate_sql(INV09, _amend(5000.0))
    assert (g["recommended_decision"], g["authorized_net_principal_inr"], g["authorized_gst_payout_inr"],
            g["debit_note_deduction_inr"], g["freight_disallowed_inr"], g["freight_waiver_applied_inr"]) == (
        "APPROVE_PARTIAL_DEBIT_NOTE", 4503000.0, 810540.0, 4500.0, 4500.0, 5000.0)
    assert g["escalation_required"] is True


def test_waiver_larger_than_the_excess_allows_only_the_claim() -> None:
    g = _gate_sql(INV09, _amend(6000.0), _amend(14000.0, amd="AMD-DEL-5826-FW2"))  # two signed waivers: summed
    assert (g["authorized_net_principal_inr"], g["debit_note_deduction_inr"], g["freight_waiver_applied_inr"]) == (4507500.0, 0.0, 9500.0)


def test_unsigned_waiver_is_ignored() -> None:
    g = _gate_sql(INV09, _amend(9500.0, status="DRAFT_PENDING_SIGNATURE"))
    assert g == _gate_sql(INV09)


# --- 1.1(a) / 3.2 GST per line.  inv-04 (INV-TS-2026-1184): 1,470,000 + 370,000 + 315,000 = 2,155,000, all at 18%.


def test_single_rate_invoice_keeps_the_invoice_level_formula() -> None:
    g = _gate_sql(INV04)
    assert g["authorized_gst_payout_inr"] == 387900.0 and "gst_rates_by_line" not in g  # ROUND(2,155,000 x 0.18, 2)
    g5 = _gate_sql(INV04, *[q for sku in ("NM-FAN-1200-BLDC", "NM-LED-BATTEN-20W", "NM-LED-BULB-9W-PK4") for q in _rate(INV04, sku, 0.05)])
    assert g5["authorized_gst_payout_inr"] == 107750.0 and "gst_rates_by_line" not in g5  # one rate, 5%
    assert g5 == _gate_sql(INV04, *[q for sku in ("NM-FAN-1200-BLDC", "NM-LED-BATTEN-20W", "NM-LED-BULB-9W-PK4") for q in _rate(INV04, sku, 0.05)], version=GATE_VERSION_V1)


def test_mixed_rates_apply_each_lines_rate() -> None:
    # line 3 at 12%: 1,470,000 x 0.18 + 370,000 x 0.18 + 315,000 x 0.12 = 264,600 + 66,600 + 37,800 = 369,000.00
    g = _gate_sql(INV04, *_rate(INV04, "NM-LED-BULB-9W-PK4", 0.12))
    assert g["authorized_gst_payout_inr"] == 369000.0
    assert g["gst_rates_by_line"] == {"NM-FAN-1200-BLDC": 0.18, "NM-LED-BATTEN-20W": 0.18, "NM-LED-BULB-9W-PK4": 0.12}
    # line 1 at 5%: the pre-fix gate took 5% for the whole invoice (107,750); per line 73,500 + 66,600 + 56,700 = 196,800
    rows = _rate(INV04, "NM-FAN-1200-BLDC", 0.05)
    assert _gate_sql(INV04, *rows)["authorized_gst_payout_inr"] == 196800.0
    assert _gate_sql(INV04, *rows, version=GATE_VERSION_V1)["authorized_gst_payout_inr"] == 107750.0


def test_mixed_rates_freight_at_the_largest_lines_rate() -> None:
    # inv-09, line 2 at 12%: 3,100,000 x 0.18 + 1,380,000 x 0.12 + freight 18,000 x 0.18 (rate of the largest line)
    # = 558,000 + 165,600 + 3,240 = 726,840.00
    assert _gate_sql(INV09, *_rate(INV09, "NM-COOLER-20L", 0.12))["authorized_gst_payout_inr"] == 726840.0


def test_gst_rate_is_read_from_the_po_line() -> None:
    # manual 1.1(a): the PO fixes the HSN/GST rates. Only the PO line changed -> the PO rate is used.
    g = _gate_sql(INV04, *_rate(INV04, "NM-LED-BULB-9W-PK4", 0.12, invoice_too=False))
    assert g["authorized_gst_payout_inr"] == 369000.0


# --- 4.1 Trigger 3 (DUPLICATE_OR_SANCTIONED_VENDOR).  inv-04 is otherwise APPROVE_CLEAN.


def _assert_trigger3_block(g: dict[str, Any], label: str) -> None:
    assert g["hard_block"] is True and g["circuit_breaker_halt"] is True and g["escalation_required"] is False
    assert g["recommended_decision"] == "BLOCK_EXCEPTION_HOLD" and all(g[k] == 0.0 for k in ZERO4)
    assert len(g["block_reasons"]) == 1 and g["block_reasons"][0].startswith(label) and HARD_BLOCK_ROUTE in g["block_reasons"][0]
    assert {f["status"] for f in g["line_findings"]} == {"HELD_BY_DUPLICATE_OR_FREEZE_BLOCK"}


def test_duplicate_invoice_is_blocked() -> None:
    g = _gate_sql(INV04, _voucher(INV04, "PO-NM-HYD-1184"))
    _assert_trigger3_block(g, "HARD_BLOCK_DUPLICATE_INVOICE")
    assert "VCH-PRIOR-0001" in g["block_reasons"][0]
    assert _gate_sql(INV04, _voucher(INV04, "PO-NM-HYD-1184"), version=GATE_VERSION_V1)["recommended_decision"] == "APPROVE_CLEAN"


def test_voucher_for_another_invoice_does_not_block() -> None:
    assert _gate_sql(INV04, _voucher(INV01, "PO-NM-BLR-7740")) == _gate_sql(INV04)


def test_duplicate_includes_a_voucher_committed_earlier_in_the_same_session() -> None:
    """Literal reading of 4.1: any row already posted for this invoice_id, including one this session committed."""
    s = ab.AblationErpSession(rung_id="bounded_sonnet_cached_gate")
    try:
        s.execute_tool("run_policy_tolerance_gate", {"invoice_id": INV04})
        s.execute_tool("commit_reconciliation_voucher", {"invoice_id": INV04, "po_id": "PO-NM-HYD-1184", "decision": "APPROVE_CLEAN"})
        again = json.loads(s.execute_tool("run_policy_tolerance_gate", {"invoice_id": INV04})[0])
    finally:
        s.close()
    assert again["recommended_decision"] == "BLOCK_EXCEPTION_HOLD"


@pytest.mark.parametrize("flag", ["PAYMENT_FREEZE", " payment_freeze "])
def test_frozen_vendor_is_blocked(flag: str) -> None:
    g = _gate_sql(INV04, _freeze(INV04, flag))
    _assert_trigger3_block(g, "HARD_BLOCK_VENDOR_PAYMENT_FREEZE")
    assert _gate_sql(INV04, _freeze(INV04, flag), version=GATE_VERSION_V1)["recommended_decision"] == "APPROVE_CLEAN"


@pytest.mark.parametrize("flag", ["CLEAN", "WATCH_PRICE_CLAIMS", "HIGH_AUDIT_ALERT", "PAYMENT_FREEZE_LIFTED"])
def test_other_vendor_flags_do_not_block(flag: str) -> None:
    assert _gate_sql(INV04, _freeze(INV04, flag)) == _gate_sql(INV04)


def test_trigger3_with_trigger1_keeps_the_recorded_line_labels() -> None:
    g = _gate_sql(INV03, _freeze(INV03))  # inv-03: IRN cancelled + phantom line (Triggers 1, 2) and now a frozen vendor
    base = _gate_sql(INV03)
    assert g["block_reasons"][:-1] == base["block_reasons"]
    assert g["block_reasons"][-1].startswith("HARD_BLOCK_VENDOR_PAYMENT_FREEZE")
    assert g["line_findings"] == base["line_findings"] and all(g[k] == 0.0 for k in ZERO4)


@pytest.mark.parametrize("pid", sorted(CAT5_ABLATION_PRESETS_BY_ID))
def test_neither_condition_leaves_the_gate_unchanged(pid: str) -> None:
    """No recorded invoice has a waiver, mixed rates, a prior voucher or a frozen vendor: v2 == v1 except inv-06's band."""
    inv = CAT5_ABLATION_PRESETS_BY_ID[pid]["invoice_id"]
    v1, v2 = _gate_sql(inv, version=GATE_VERSION_V1), _gate_sql(inv)
    assert (v1 == v2) is (pid != "inv-06")


# ------------------------------------------------------------------------ bundle: added fields


def _bundle(pid: str, version: str) -> str:
    s = ab.AblationErpSession(rung_id="bounded_sonnet_cached_gate", bundle_version=version)
    try:
        return s.execute_tool("fetch_3way_match_bundle", {"invoice_id": CAT5_ABLATION_PRESETS_BY_ID[pid]["invoice_id"]})[0]
    finally:
        s.close()


_ADDED_HEADER = ("currency", "risk_flag", "posted_vouchers")


def _strip_v2(bundle: dict[str, Any]) -> dict[str, Any]:
    b = copy.deepcopy(bundle)
    for k in _ADDED_HEADER:
        b["header"].pop(k)
    for ln in b["matched_lines"]:
        ln.pop("po_gst_rate")
    return b


@pytest.mark.parametrize("pid", sorted(CAT5_ABLATION_PRESETS_BY_ID))
def test_bundle_adds_only_the_fields_the_gate_reads(pid: str) -> None:
    old, new = json.loads(_bundle(pid, BUNDLE_VERSION_V1)), json.loads(_bundle(pid, BUNDLE_VERSION))
    added = {k: v for k, v in new["header"].items() if k not in old["header"]}
    assert set(added) == set(_ADDED_HEADER)
    assert added["currency"] == "INR" and added["posted_vouchers"] == []
    assert added["risk_flag"] in {"CLEAN", "WATCH_PRICE_CLAIMS", "HIGH_AUDIT_ALERT"}
    assert all(ln["po_gst_rate"] == ln["gst_rate"] for ln in new["matched_lines"])
    assert _strip_v2(new) == old  # nothing else moves


def test_bundle_shows_a_posted_voucher_and_the_po_line_rate() -> None:
    s = ab.AblationErpSession(rung_id="bounded_sonnet_cached_gate")
    try:
        s.conn.execute(*_voucher(INV04, "PO-NM-HYD-1184"))
        s.conn.execute(*_rate(INV04, "NM-LED-BULB-9W-PK4", 0.12, invoice_too=False)[0])
        b = json.loads(s.execute_tool("fetch_3way_match_bundle", {"invoice_id": INV04})[0])
    finally:
        s.close()
    assert b["header"]["posted_vouchers"] == [{"voucher_id": "VCH-PRIOR-0001", "decision": "APPROVE_CLEAN"}]
    assert {ln["sku"]: (ln["gst_rate"], ln["po_gst_rate"]) for ln in b["matched_lines"]}["NM-LED-BULB-9W-PK4"] == (0.18, 0.12)


def test_no_default_invoice_has_an_inside_band_rise() -> None:
    """The ruling that the added bundle field does not bear on the 11 pooled invoices rests on this."""
    for pid in CAT5_ABLATION_DEFAULT_INVOICE_IDS:
        b = json.loads(_bundle(pid, BUNDLE_VERSION))
        inside = [ln["sku"] for ln in b["matched_lines"]
                  if ln["po_unit_price_inr"] < ln["billed_unit_price_inr"] <= ln["po_unit_price_inr"] * 1.015]
        assert inside == [], pid
    b6 = json.loads(_bundle("inv-06", BUNDLE_VERSION))
    assert [ln["sku"] for ln in b6["matched_lines"]
            if ln["po_unit_price_inr"] < ln["billed_unit_price_inr"] <= ln["po_unit_price_inr"] * 1.015] == ["NM-CBL-1.5SQ-90M"]


# ------------------------------------------------------------------------ recorded evidence stays reproducible


def _recorded_calls(name: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    out = []
    for line in RUNS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        for t in r.get("turns") or []:
            for c in t.get("tool_calls") or []:
                if c.get("name") == name and c.get("executed"):
                    out.append((r, c))
    return out


def _tool_out(name: str, inp: dict[str, Any], *, gate_version: str = GATE_VERSION, bundle_version: str = BUNDLE_VERSION) -> str:
    s = ab.AblationErpSession(rung_id="bounded_sonnet_cached_gate", gate_version=gate_version, bundle_version=bundle_version)
    try:
        return s.execute_tool(name, inp)[0]
    finally:
        s.close()


@pytest.mark.skipif(not HAVE_RECORDS, reason="ablation records not present")
def test_fixed_gate_is_byte_identical_on_every_recorded_default_invoice_call() -> None:
    calls = _recorded_calls("run_policy_tolerance_gate")
    default = [(r, c) for r, c in calls if r["preset_id"] in CAT5_ABLATION_DEFAULT_INVOICE_IDS]
    inv06 = [(r, c) for r, c in calls if r["preset_id"] == "inv-06"]
    before = [(r, c) for r, c in inv06 if ab.record_gate_version(r) == GATE_VERSION_V1]
    after = [(r, c) for r, c in inv06 if ab.record_gate_version(r) == GATE_VERSION]
    # one gate call per run: 2 gate arms x 11 invoices x 3 repeats; on inv-06 6 recorded before the fix, 6 after
    assert len(default) == 66 and len(before) == 6 and len(after) == 6 and len(inv06) == 12
    for r, c in default:  # all recorded on v1; the fixed gate returns the same bytes
        assert _sha(_tool_out(c["name"], c["input"])) == c["result_sha256"], (r["run_id"], c["input"])
    for r, c in before:  # the pre-fix gate reproduces what was recorded; the fixed gate does not
        assert _sha(_tool_out(c["name"], c["input"], gate_version=GATE_VERSION_V1)) == c["result_sha256"]
        assert _sha(_tool_out(c["name"], c["input"])) != c["result_sha256"]
    for r, c in after:  # the after-fix runs reproduce on the fixed gate
        assert _sha(_tool_out(c["name"], c["input"])) == c["result_sha256"], r["run_id"]


@pytest.mark.skipif(not HAVE_RECORDS, reason="ablation records not present")
def test_recorded_bundle_calls_reproduce_with_v1_and_v2_only_adds_fields() -> None:
    calls = _recorded_calls("fetch_3way_match_bundle")
    assert calls
    for r, c in calls:
        v1 = _tool_out(c["name"], c["input"], bundle_version=BUNDLE_VERSION_V1)
        v2 = _tool_out(c["name"], c["input"])
        if ab.record_bundle_version(r) == BUNDLE_VERSION_V1:
            assert _sha(v1) == c["result_sha256"], r["run_id"]
        else:  # the after-fix inv-06 runs
            assert ab.record_bundle_version(r) == BUNDLE_VERSION and r["preset_id"] == "inv-06"
            assert _sha(v2) == c["result_sha256"], r["run_id"]
        assert _strip_v2(json.loads(v2)) == json.loads(v1)


@pytest.mark.skipif(not HAVE_RECORDS, reason="ablation records not present")
def test_records_stay_current_and_nothing_is_pending() -> None:
    recs = ab.load_jsonl(RUNS)
    arms = list(ab.ARM_IDS)
    assert ab.select_pending(ab.plan_matrix(arms, list(CAT5_ABLATION_DEFAULT_INVOICE_IDS), 3), recs) == []
    v2 = [r for r in recs if (r.get("settings") or {}).get("gate_version")]
    assert len(v2) == 6 and {(r["arm_id"], r["preset_id"]) for r in v2} == {
        (a, "inv-06") for a in ("bundle_gate_sonnet_cached", "bundle_gate_haiku_escalate")}
    assert all(r["settings"]["gate_version"] == GATE_VERSION and r["settings"]["bundle_version"] == BUNDLE_VERSION for r in v2)
    assert ab.select_pending(ab.plan_matrix(arms, ["inv-06"], 3), recs) == []  # the after-fix check ran
    assert len(ab.superseded_records(recs)) == 1  # only the earlier harness artifact; nothing new superseded
    s = ab.summarise(recs)
    assert s["ok_runs_used"] == 198
    g = s["gate_disagreement"]["inv-06"]
    gated = [m for m in g["per_arm"].values() if m["gate_arm"]]
    assert sum(m["runs"] for m in gated) == 6 and sum(m["matches_gate_output"] for m in gated) == 6
    assert sum(m["matches_manual"] for m in g["per_arm"].values() if not m["gate_arm"]) == 12
    assert sum(m["runs"] for m in g["after_fix"]["per_arm"].values()) == 6 and g["after_fix"]["missing_keys"] == []
    assert sum(m["matches_manual"] for m in g["after_fix"]["per_arm"].values()) == 6
    assert g["gate_fix"]["current_gate_matches_manual"] is True


def test_new_records_carry_tool_versions() -> None:
    st = ab.current_settings("bundle_gate_sonnet_cached", "inv-06")
    assert st["gate_version"] == GATE_VERSION == "v2-manual-aligned"
    assert st["bundle_version"] == BUNDLE_VERSION == "v2-manual-aligned"
    assert "gate_version" not in ab._SETTINGS_COMPARED and "bundle_version" not in ab._SETTINGS_COMPARED
    assert ab.gate_version_matters("bundle_gate_sonnet_cached", "inv-06")
    assert not ab.gate_version_matters("bundle_sonnet_cached", "inv-06")
    assert not any(ab.gate_version_matters(a, p) for a in ab.ARM_IDS for p in CAT5_ABLATION_DEFAULT_INVOICE_IDS)
