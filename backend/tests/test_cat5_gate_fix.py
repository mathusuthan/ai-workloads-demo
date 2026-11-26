"""Category 5 deterministic policy tool (AP-POL-GATE-01) against the policy manual, and the narrow query's fields,
with the recorded runs kept reproducible. No live API calls.

Each rule is tested on synthetic rows (positive and negative): the 1.5% band only for index-linked POs (2.1); the
approved freight waiver of a signed amendment (2.2/2.3); GST at each line's own PO rate (1.1(a)/3.2); Trigger 3,
duplicate invoice or PAYMENT_FREEZE vendor (4.1); escalation only for a multi-factor dispute (6.2); held-line labels
from the lowest-numbered hard-block trigger that fired (4.1)."""

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
    ESCALATION_FACTOR_KINDS,
    FACTOR_AMENDMENT,
    FACTOR_FREIGHT,
    FACTOR_PRICE_HIKE,
    FACTOR_QUANTITY_DOA,
    HARD_BLOCK_ROUTE,
    HELD_LABEL_TRIGGER1,
    HELD_LABEL_TRIGGER2,
    HELD_LABEL_TRIGGER3,
    PRICE_RULE_WITHIN_BAND,
    PRICE_RULE_WITHIN_BAND_NOT_INDEX_LINKED,
    escalation_factor_kinds,
    evaluate_deterministic_policy_gate,
    po_currency_index_linked,
)
from app.data.cat5_ablation_fixtures import (  # noqa: E402
    CAT5_ABLATION_DEFAULT_INVOICE_IDS,
    CAT5_ABLATION_ERP_ROWS,
    CAT5_ABLATION_PRESETS_BY_ID,
)

EXP_DIR = BACKEND_DIR / "experiments" / "cat5_ablation"
RUNS = EXP_DIR / "runs.jsonl"
OTHER_RUNS = EXP_DIR / "other_levers" / "runs.jsonl"
HAVE_RECORDS = RUNS.is_file()
INV06 = CAT5_ABLATION_PRESETS_BY_ID["inv-06"]
P = CAT5_ABLATION_PRESETS_BY_ID


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


def _gate(rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    s = ab.AblationErpSession(rung_id="bounded_sonnet_cached_gate", extra_rows=rows)
    try:
        return evaluate_deterministic_policy_gate(s.conn, INV06["invoice_id"])
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
    assert g["escalation_required"] is False  # one factor (an unauthorized price rise): not a multi-factor dispute
    gt = INV06["ground_truth"]  # equals the manual derivation
    assert g["recommended_decision"] == gt["decision"] and g["authorized_net_principal_inr"] == gt["authorized_net_principal_inr"]


@pytest.mark.parametrize("currency", ["INR", "INR (index-linked float: LME copper)"])
def test_rise_above_band_is_capped_whatever_the_po_notes(currency: str) -> None:
    g = _gate(_rows(currency=currency, billed_rate=1520.0))  # +2.7% > 1.5%
    assert g == _gate(_rows(currency="INR", billed_rate=1520.0))
    l1 = g["line_findings"][0]
    assert l1["price_rule"] == "UNAUTHORIZED_HIKE_CAPPED_TO_PO" and l1["effective_unit_price_inr"] == 1480.0


# ------------------------------------------------------------------------ freight waiver, GST per line, Trigger 3 (synthetic rows)
#
# Each test edits a fresh in-memory ERP (the ablation rows) with SQL and runs the gate. Hand derivations in comments.

INV04, INV09, INV01, INV03 = "INV-TS-2026-1184", "INV-HR-2026-5826", "INV-KA-2026-9921", "INV-DL-2026-8803"
ZERO4 = ("authorized_net_principal_inr", "authorized_gst_payout_inr", "gst_escrow_holdback_inr", "debit_note_deduction_inr")


def _gate_sql(invoice_id: str, *sql: tuple[str, tuple[Any, ...]]) -> dict[str, Any]:
    s = ab.AblationErpSession(rung_id="bounded_sonnet_cached_gate")
    try:
        for stmt, params in sql:
            s.conn.execute(stmt, params)
        return evaluate_deterministic_policy_gate(s.conn, invoice_id)
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
    assert "freight_waiver_applied_inr" not in g and g["escalation_required"] is False  # one factor: disallowed freight


def test_signed_waiver_covering_the_excess_allows_all_freight() -> None:
    # cap 18,000 + waiver 9,500 = 27,500 -> freight 27,500 allowed; net 4,480,000 + 27,500 = 4,507,500;
    # GST ROUND(4,507,500 x 0.18, 2) = 811,350; debit 0 -> APPROVE_CLEAN; one factor (the amendment's waiver), no escalation
    g = _gate_sql(INV09, _amend(9500.0))
    assert (g["recommended_decision"], g["authorized_net_principal_inr"], g["authorized_gst_payout_inr"],
            g["debit_note_deduction_inr"], g["freight_disallowed_inr"], g["freight_waiver_applied_inr"]) == (
        "APPROVE_CLEAN", 4507500.0, 811350.0, 0.0, 0.0, 9500.0)
    assert g["escalation_required"] is False


def test_partial_waiver_disallows_the_rest() -> None:
    # cap 18,000 + 5,000 = 23,000 allowed; 4,500 disallowed; net 4,503,000; GST 810,540
    g = _gate_sql(INV09, _amend(5000.0))
    assert (g["recommended_decision"], g["authorized_net_principal_inr"], g["authorized_gst_payout_inr"],
            g["debit_note_deduction_inr"], g["freight_disallowed_inr"], g["freight_waiver_applied_inr"]) == (
        "APPROVE_PARTIAL_DEBIT_NOTE", 4503000.0, 810540.0, 4500.0, 4500.0, 5000.0)
    assert g["escalation_required"] is True  # two factors: the amendment's waiver and the freight still disallowed


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


def test_mixed_rates_apply_each_lines_rate() -> None:
    # line 3 at 12%: 1,470,000 x 0.18 + 370,000 x 0.18 + 315,000 x 0.12 = 264,600 + 66,600 + 37,800 = 369,000.00
    g = _gate_sql(INV04, *_rate(INV04, "NM-LED-BULB-9W-PK4", 0.12))
    assert g["authorized_gst_payout_inr"] == 369000.0
    assert g["gst_rates_by_line"] == {"NM-FAN-1200-BLDC": 0.18, "NM-LED-BATTEN-20W": 0.18, "NM-LED-BULB-9W-PK4": 0.12}
    # line 1 at 5% (each line at its own rate, not the first line's rate for the whole invoice): 73,500 + 66,600 + 56,700 = 196,800
    rows = _rate(INV04, "NM-FAN-1200-BLDC", 0.05)
    assert _gate_sql(INV04, *rows)["authorized_gst_payout_inr"] == 196800.0


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
    assert {f["status"] for f in g["line_findings"]} == {HELD_LABEL_TRIGGER3}


def test_duplicate_invoice_is_blocked() -> None:
    g = _gate_sql(INV04, _voucher(INV04, "PO-NM-HYD-1184"))
    _assert_trigger3_block(g, "HARD_BLOCK_DUPLICATE_INVOICE")
    assert "VCH-PRIOR-0001" in g["block_reasons"][0]


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


@pytest.mark.parametrize("flag", ["CLEAN", "WATCH_PRICE_CLAIMS", "HIGH_AUDIT_ALERT", "PAYMENT_FREEZE_LIFTED"])
def test_other_vendor_flags_do_not_block(flag: str) -> None:
    assert _gate_sql(INV04, _freeze(INV04, flag)) == _gate_sql(INV04)


def test_trigger3_with_trigger1_keeps_the_recorded_line_labels() -> None:
    g = _gate_sql(INV03, _freeze(INV03))  # inv-03: IRN cancelled + phantom line (Triggers 1, 2) and now a frozen vendor
    base = _gate_sql(INV03)
    assert g["block_reasons"][:-1] == base["block_reasons"]
    assert g["block_reasons"][-1].startswith("HARD_BLOCK_VENDOR_PAYMENT_FREEZE")
    assert g["line_findings"] == base["line_findings"] and all(g[k] == 0.0 for k in ZERO4)


# ------------------------------------------------------------------------ escalation: manual 6.2, multi-factor


def _line(**kw: Any) -> dict[str, Any]:
    base = {"sku": "X", "billed_qty": 10, "payable_qty": 10, "doa_rejected_qty": 0, "price_rule": "EXACT_PO_MATCH",
            "billed_unit_price_inr": 100.0, "effective_unit_price_inr": 100.0}
    base.update(kw)
    return base


_DOA = _line(sku="D", payable_qty=8, doa_rejected_qty=2)
_SHORT = _line(sku="S", payable_qty=9)
_AMD = _line(sku="A", price_rule="AMENDMENT_APPROVED (AMD-1)", billed_unit_price_inr=105.0, effective_unit_price_inr=105.0)
_HIKE = _line(sku="H", price_rule="UNAUTHORIZED_HIKE_CAPPED_TO_PO", billed_unit_price_inr=110.0)
_BAND_PLAIN = _line(sku="B", price_rule=PRICE_RULE_WITHIN_BAND_NOT_INDEX_LINKED, billed_unit_price_inr=101.0)
_BAND_LINKED = _line(sku="L", price_rule=PRICE_RULE_WITHIN_BAND, billed_unit_price_inr=101.0, effective_unit_price_inr=101.0)


@pytest.mark.parametrize(
    ("lines", "freight", "waiver", "kinds"),
    [
        ([_line()], 0.0, 0.0, []),
        ([_DOA], 0.0, 0.0, [FACTOR_QUANTITY_DOA]),
        ([_DOA, _SHORT], 0.0, 0.0, [FACTOR_QUANTITY_DOA]),  # DOA and short receipt are one kind
        ([_AMD], 0.0, 0.0, [FACTOR_AMENDMENT]),  # an amendment counts even when it deducts nothing
        ([_HIKE, _HIKE], 0.0, 0.0, [FACTOR_PRICE_HIKE]),  # several lines of one kind are one factor
        ([_BAND_PLAIN], 0.0, 0.0, [FACTOR_PRICE_HIKE]),  # inside the band on a PO that is not index-linked
        ([_BAND_LINKED], 0.0, 0.0, []),  # inside the band on an index-linked PO is paid as billed
        ([_line()], 500.0, 0.0, [FACTOR_FREIGHT]),
        ([_line()], 0.0, 500.0, [FACTOR_AMENDMENT]),  # a signed waiver applied is an amendment factor
        ([_DOA, _AMD], 0.0, 0.0, [FACTOR_QUANTITY_DOA, FACTOR_AMENDMENT]),
        ([_HIKE], 500.0, 0.0, [FACTOR_PRICE_HIKE, FACTOR_FREIGHT]),
        ([_DOA, _AMD, _HIKE], 500.0, 0.0, list(ESCALATION_FACTOR_KINDS)),
    ],
)
def test_escalation_factor_kinds(lines: list[dict[str, Any]], freight: float, waiver: float, kinds: list[str]) -> None:
    assert escalation_factor_kinds(lines, freight_disallowed_inr=freight, freight_waiver_applied_inr=waiver) == kinds


def test_escalation_on_every_invoice_follows_manual_6_2() -> None:
    """Two or more distinct factor kinds escalate; one factor or a hard block does not. Only inv-02 and inv-12 do."""
    fired = []
    for pid in sorted(P):
        g = ab.gate_output_for(pid)
        assert g["escalation_required"] is P[pid]["ground_truth"]["expected_escalation"], pid
        if g["hard_block"]:
            assert g["escalation_required"] is False, pid
        if g["escalation_required"]:
            fired.append(pid)
    assert fired == ["inv-02", "inv-12"]


def test_debit_note_alone_does_not_escalate() -> None:
    # inv-05, 06, 07, 09 each carry a debit note from a single factor kind
    for pid in ("inv-05", "inv-06", "inv-07", "inv-09"):
        g = ab.gate_output_for(pid)
        assert g["debit_note_deduction_inr"] > 0 and g["escalation_required"] is False, pid


# ------------------------------------------------------------------------ held-line labels (lowest trigger that fired)


def test_held_labels_name_the_lowest_trigger_that_fired() -> None:
    g3 = ab.gate_output_for("inv-03")  # Trigger 1 (cancelled IRN) + Trigger 2 (phantom line)
    held3 = {f["status"] for f in g3["line_findings"]} - {"PHANTOM_UNRECEIVED"}
    assert held3 == {HELD_LABEL_TRIGGER1}
    g11 = ab.gate_output_for("inv-11")  # Trigger 2 only
    held11 = {f["status"] for f in g11["line_findings"]} - {"PHANTOM_UNRECEIVED"}
    assert held11 == {HELD_LABEL_TRIGGER2} and HELD_LABEL_TRIGGER1 not in json.dumps(g11["line_findings"])
    assert all(g11[k] == 0.0 for k in ZERO4) and g11["escalation_required"] is False


# ------------------------------------------------------------------------ the tool's output per invoice, pinned

# sha256 (first 16 hex) of the tool's output per invoice. Every recorded policy-tool call must return these bytes to
# count (ablation.record_tool_outputs_current), so a change here makes the matching runs pending again.
PINNED_GATE_SHA16 = {
    "inv-01": "23cb32705ad7ae1b", "inv-02": "642cc6cba8d36fd1", "inv-03": "e2203739d075dda8", "inv-04": "6b944c4728b14d84",
    "inv-05": "d90bc05d9fdcce7e", "inv-06": "599a4b891adce324", "inv-07": "3f11324d650ba260", "inv-08": "ecfde045a71a90f2",
    "inv-09": "c61d2ce04aafac3e", "inv-10": "3aed494bbb3d15d8", "inv-11": "780b521e7a9adc85", "inv-12": "cdb396be01b7facf",
}


def _tool_out(name: str, inp: dict[str, Any]) -> str:
    s = ab.AblationErpSession(rung_id="bounded_sonnet_cached_gate")
    try:
        return s.execute_tool(name, inp)[0]
    finally:
        s.close()


def test_tool_output_per_invoice_is_pinned() -> None:
    got = {pid: _sha(_tool_out("run_policy_tolerance_gate", {"invoice_id": P[pid]["invoice_id"]}))[:16] for pid in sorted(P)}
    assert got == PINNED_GATE_SHA16


def test_no_recorded_invoice_has_a_waiver_mixed_rates_a_prior_voucher_or_a_frozen_vendor() -> None:
    for pid in sorted(P):
        g = ab.gate_output_for(pid)
        assert "freight_waiver_applied_inr" not in g and "gst_rates_by_line" not in g, pid
        assert not any(r.startswith(("HARD_BLOCK_DUPLICATE_INVOICE", "HARD_BLOCK_VENDOR_PAYMENT_FREEZE")) for r in g.get("block_reasons") or []), pid


# ------------------------------------------------------------------------ narrow query: the fields the tool reads


def _bundle(pid: str) -> dict[str, Any]:
    return json.loads(_tool_out("fetch_3way_match_bundle", {"invoice_id": P[pid]["invoice_id"]}))


_ADDED_HEADER = ("currency", "risk_flag", "posted_vouchers")


def _strip_added(bundle: dict[str, Any]) -> dict[str, Any]:
    b = copy.deepcopy(bundle)
    for k in _ADDED_HEADER:
        b["header"].pop(k)
    for ln in b["matched_lines"]:
        ln.pop("po_gst_rate")
    return b


@pytest.mark.parametrize("pid", sorted(CAT5_ABLATION_PRESETS_BY_ID))
def test_bundle_returns_the_fields_the_tool_reads(pid: str) -> None:
    b = _bundle(pid)
    assert all(k in b["header"] for k in _ADDED_HEADER)
    assert b["header"]["currency"] == "INR" and b["header"]["posted_vouchers"] == []
    assert b["header"]["risk_flag"] in {"CLEAN", "WATCH_PRICE_CLAIMS", "HIGH_AUDIT_ALERT"}
    assert all(ln["po_gst_rate"] == ln["gst_rate"] for ln in b["matched_lines"])


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


def test_only_inv06_has_an_inside_band_rise() -> None:
    inside = {pid: [ln["sku"] for ln in _bundle(pid)["matched_lines"]
                    if ln["po_unit_price_inr"] < ln["billed_unit_price_inr"] <= ln["po_unit_price_inr"] * 1.015] for pid in sorted(P)}
    assert {pid: v for pid, v in inside.items() if v} == {"inv-06": ["NM-CBL-1.5SQ-90M"]}


# ------------------------------------------------------------------------ recorded runs stay reproducible


def _recorded_calls(path: Path, name: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    out = []
    for r in ab.load_jsonl(path):
        for t in r.get("turns") or []:
            for c in t.get("tool_calls") or []:
                if c.get("name") == name and c.get("executed"):
                    out.append((r, c))
    return out


@pytest.mark.skipif(not HAVE_RECORDS, reason="experiment records not present")
def test_every_recorded_policy_tool_call_reproduces_on_the_current_tool() -> None:
    calls = _recorded_calls(RUNS, "run_policy_tolerance_gate")
    assert calls
    for r, c in calls:
        assert _sha(_tool_out(c["name"], c["input"])) == c["result_sha256"], (r["run_id"], r["preset_id"])


@pytest.mark.skipif(not HAVE_RECORDS, reason="experiment records not present")
def test_recorded_narrow_query_calls_reproduce_now_or_with_the_four_fields_removed() -> None:
    """Every recorded narrow query returned either today's bytes or today's minus the four added fields; a displayed
    version's run with the older bytes is not current (its key is pending until re-run)."""
    for path in (RUNS, OTHER_RUNS):
        for r, c in _recorded_calls(path, "fetch_3way_match_bundle"):
            now = _tool_out(c["name"], c["input"])
            older = json.dumps(_strip_added(json.loads(now)), indent=2)
            assert c["result_sha256"] in (_sha(now), _sha(older)), r["run_id"]
            if c["result_sha256"] == _sha(older):
                assert not ab.record_tool_outputs_current(r) and not ab.record_is_current(r)


# the invoices whose with-version runs were first recorded before the narrow query returned its four added fields
RECORDED_ON_THE_OLDER_NARROW_QUERY = ("inv-01", "inv-02", "inv-03", "inv-04", "inv-08", "inv-10", "inv-12")


@pytest.mark.skipif(not HAVE_RECORDS, reason="experiment records not present")
def test_main_file_holds_only_runs_of_the_four_cells_and_only_known_stale_ones() -> None:
    """Passes before and after the re-run of the older-narrow-query runs (and after the prune removes them), and before and
    after the Haiku "without" cell (raw_free_haiku) is recorded: until then its 36 keys are pending."""
    recs = ab.load_jsonl(RUNS)
    assert {r["arm_id"] for r in recs} <= set(ab.ARM_IDS)
    with_arms = ("bundle_gate_sonnet_cached", "bundle_gate_haiku_escalate")
    stale = [r for r in recs if not ab.record_is_current(r)]
    assert all(r["arm_id"] in with_arms and r["preset_id"] in RECORDED_ON_THE_OLDER_NARROW_QUERY for r in stale)
    current = [r for r in recs if ab.record_is_current(r)]
    assert len({ab.record_key(r) for r in current}) == len(current)  # one current record per key
    pending = ab.select_pending(ab.plan_matrix(list(ab.ARM_IDS), list(CAT5_ABLATION_DEFAULT_INVOICE_IDS), 3), recs)
    new_cell = [k for k in pending if k[0] == "raw_free_haiku"]  # the Haiku "without" cell: pending until its live run
    rest = [k for k in pending if k[0] != "raw_free_haiku"]
    assert set(rest) <= {(a, p, i) for a in with_arms for p in RECORDED_ON_THE_OLDER_NARROW_QUERY for i in range(3)}
    assert set(rest) == {ab.record_key(r) for r in stale} - {ab.record_key(r) for r in current}
    assert not [k for k in pending if k[0] == "raw_free_sonnet"]
    assert len(new_cell) <= 3 * len(CAT5_ABLATION_DEFAULT_INVOICE_IDS)


@pytest.mark.skipif(not OTHER_RUNS.is_file(), reason="other-lever records not present")
def test_other_levers_file_holds_current_runs_of_the_other_single_levers() -> None:
    recs = ab.load_jsonl(OTHER_RUNS)
    assert recs and {r["arm_id"] for r in recs} == set(ab.OTHER_LEVER_ARM_IDS)
    assert all(r["status"] == "ok" and ab.is_current_settings(r) for r in recs)  # kept as recorded
    assert len({ab.record_key(r) for r in recs}) == len(recs) == 3 * 12 * 3


def test_settings_carry_no_tool_versions() -> None:
    st = ab.current_settings("bundle_gate_sonnet_cached", "inv-06")
    assert "gate_version" not in st and "bundle_version" not in st, st
