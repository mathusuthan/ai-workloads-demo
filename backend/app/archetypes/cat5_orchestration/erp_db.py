"""In-memory SQLite ERP Engine, Deterministic Policy Gate & Rung Tool Suites for Category 5."""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from app.data.cat5_fixtures import ERP_SEED_DATA

ERP_DDL_SCHEMA_SQL = """
CREATE TABLE vendors (
    vendor_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    gstin TEXT NOT NULL,
    udyam_tier TEXT NOT NULL,
    msmed_45d_applicable INTEGER NOT NULL,
    payment_terms_days INTEGER NOT NULL,
    risk_flag TEXT NOT NULL,
    full_audit_trail_json TEXT NOT NULL
);

CREATE TABLE purchase_orders (
    po_id TEXT PRIMARY KEY,
    vendor_id TEXT NOT NULL,
    fc_hub TEXT NOT NULL,
    incoterms TEXT NOT NULL,
    approved_freight_cap_inr REAL NOT NULL,
    po_total_taxable_inr REAL NOT NULL,
    currency TEXT NOT NULL,
    created_date TEXT NOT NULL
);

CREATE TABLE po_lines (
    po_id TEXT NOT NULL,
    line_no INTEGER NOT NULL,
    sku TEXT NOT NULL,
    description TEXT NOT NULL,
    ordered_qty INTEGER NOT NULL,
    po_unit_price_inr REAL NOT NULL,
    gst_rate REAL NOT NULL,
    PRIMARY KEY (po_id, line_no)
);

CREATE TABLE goods_receipts (
    grn_id TEXT PRIMARY KEY,
    po_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    received_qty INTEGER NOT NULL,
    accepted_qty INTEGER NOT NULL,
    doa_rejected_qty INTEGER NOT NULL,
    grn_date TEXT NOT NULL,
    qc_notes TEXT NOT NULL,
    raw_wms_scan_dump TEXT NOT NULL
);

CREATE TABLE vendor_invoices (
    invoice_id TEXT PRIMARY KEY,
    po_id TEXT NOT NULL,
    vendor_id TEXT NOT NULL,
    invoice_date TEXT NOT NULL,
    irn_hash TEXT NOT NULL,
    irn_status TEXT NOT NULL,
    gstr2b_status TEXT NOT NULL,
    claimed_freight_inr REAL NOT NULL,
    invoice_total_taxable_inr REAL NOT NULL,
    invoice_gst_inr REAL NOT NULL,
    invoice_grand_total_inr REAL NOT NULL,
    remittance_memo TEXT NOT NULL
);

CREATE TABLE invoice_lines (
    invoice_id TEXT NOT NULL,
    line_no INTEGER NOT NULL,
    sku TEXT NOT NULL,
    billed_qty INTEGER NOT NULL,
    billed_unit_price_inr REAL NOT NULL,
    billed_line_total_inr REAL NOT NULL,
    gst_rate REAL NOT NULL,
    PRIMARY KEY (invoice_id, line_no)
);

CREATE TABLE contract_amendments (
    amendment_id TEXT PRIMARY KEY,
    po_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    approved_unit_price_inr REAL NOT NULL,
    approved_freight_waiver_inr REAL NOT NULL,
    status TEXT NOT NULL,
    approvers TEXT NOT NULL,
    notes TEXT NOT NULL
);

CREATE TABLE fc_dock_logs (
    po_id TEXT PRIMARY KEY,
    hub TEXT NOT NULL,
    log_blob TEXT NOT NULL
);

CREATE TABLE reconciliation_vouchers (
    voucher_id TEXT PRIMARY KEY,
    invoice_id TEXT UNIQUE NOT NULL,
    po_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    authorized_net_principal_inr REAL NOT NULL,
    authorized_gst_payout_inr REAL NOT NULL,
    gst_escrow_holdback_inr REAL NOT NULL,
    debit_note_deduction_inr REAL NOT NULL,
    gate_verified INTEGER NOT NULL,
    audit_summary TEXT NOT NULL
);
""".strip()


NAIVE_TOOLS: list[dict[str, Any]] = [
    {
        "name": "query_invoice_raw",
        "description": "Execute SELECT * on vendor_invoices and invoice_lines for a given invoice_id.",
        "input_schema": {
            "type": "object",
            "properties": {"invoice_id": {"type": "string"}},
            "required": ["invoice_id"],
        },
    },
    {
        "name": "query_po_raw",
        "description": "Execute SELECT * on purchase_orders and po_lines for a given po_id.",
        "input_schema": {
            "type": "object",
            "properties": {"po_id": {"type": "string"}},
            "required": ["po_id"],
        },
    },
    {
        "name": "query_grn_wms_telemetry",
        "description": "Execute SELECT * on goods_receipts (including raw WMS barcode telemetry) for a po_id.",
        "input_schema": {
            "type": "object",
            "properties": {"po_id": {"type": "string"}},
            "required": ["po_id"],
        },
    },
    {
        "name": "query_vendor_audit_history",
        "description": "Execute SELECT * on vendors (including quarterly historical compliance log) for a vendor_id.",
        "input_schema": {
            "type": "object",
            "properties": {"vendor_id": {"type": "string"}},
            "required": ["vendor_id"],
        },
    },
    {
        "name": "query_contract_amendments_and_dock_logs",
        "description": "Check contract_amendments and fc_dock_logs for a po_id.",
        "input_schema": {
            "type": "object",
            "properties": {"po_id": {"type": "string"}},
            "required": ["po_id"],
        },
    },
    {
        "name": "commit_reconciliation_voucher",
        "description": "Persist the final invoice reconciliation decision and exact INR payout breakdown into SQLite reconciliation_vouchers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "string"},
                "po_id": {"type": "string"},
                "decision": {
                    "type": "string",
                    "enum": [
                        "APPROVE_CLEAN",
                        "APPROVE_WITH_GST_ESCROW",
                        "APPROVE_PARTIAL_DEBIT_NOTE",
                        "BLOCK_EXCEPTION_HOLD",
                    ],
                },
                "authorized_net_principal_inr": {"type": "number"},
                "authorized_gst_payout_inr": {"type": "number"},
                "gst_escrow_holdback_inr": {"type": "number"},
                "debit_note_deduction_inr": {"type": "number"},
                "audit_summary": {"type": "string"},
            },
            "required": [
                "invoice_id",
                "po_id",
                "decision",
                "authorized_net_principal_inr",
                "authorized_gst_payout_inr",
                "gst_escrow_holdback_inr",
                "debit_note_deduction_inr",
                "audit_summary",
            ],
        },
    },
]


GOVERNED_TOOLS: list[dict[str, Any]] = [
    {
        "name": "fetch_3way_match_bundle",
        "description": (
            "Run a projection-bounded SQLite JOIN across vendor_invoices, invoice_lines, purchase_orders, "
            "po_lines, goods_receipts, vendors, and contract_amendments for invoice_id (omits noisy WMS scan blobs)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"invoice_id": {"type": "string"}},
            "required": ["invoice_id"],
        },
    },
    {
        "name": "run_policy_tolerance_gate",
        "description": (
            "Run NovaMart's deterministic AP Policy & Circuit-Breaker Engine (AP-POL-GATE-01) over SQLite ERP rows "
            "for invoice_id. Computes exact payable quantities, amendment/1.5% price caps, freight caps, GSTR-2B split escrow, "
            "circuit-breaker halts, and whether complex dispute escalation is required."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"invoice_id": {"type": "string"}},
            "required": ["invoice_id"],
        },
    },
    {
        "name": "commit_reconciliation_voucher",
        "description": (
            "Commit the gate-verified reconciliation voucher to SQLite reconciliation_vouchers. "
            "Requires run_policy_tolerance_gate to have verified invoice_id first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "string"},
                "po_id": {"type": "string"},
                "decision": {
                    "type": "string",
                    "enum": [
                        "APPROVE_CLEAN",
                        "APPROVE_WITH_GST_ESCROW",
                        "APPROVE_PARTIAL_DEBIT_NOTE",
                        "BLOCK_EXCEPTION_HOLD",
                    ],
                },
                "authorized_net_principal_inr": {"type": "number"},
                "authorized_gst_payout_inr": {"type": "number"},
                "gst_escrow_holdback_inr": {"type": "number"},
                "debit_note_deduction_inr": {"type": "number"},
                "audit_summary": {"type": "string"},
            },
            "required": [
                "invoice_id",
                "po_id",
                "decision",
                "authorized_net_principal_inr",
                "authorized_gst_payout_inr",
                "gst_escrow_holdback_inr",
                "debit_note_deduction_inr",
                "audit_summary",
            ],
        },
    },
]


def create_seeded_erp_connection() -> sqlite3.Connection:
    """Create and seed a fresh in-memory SQLite ERP database per invoice run."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(ERP_DDL_SCHEMA_SQL)

    conn.executemany(
        """
        INSERT INTO vendors VALUES (
            :vendor_id, :name, :gstin, :udyam_tier, :msmed_45d_applicable,
            :payment_terms_days, :risk_flag, :full_audit_trail_json
        )
        """,
        ERP_SEED_DATA["vendors"],
    )
    conn.executemany(
        """
        INSERT INTO purchase_orders VALUES (
            :po_id, :vendor_id, :fc_hub, :incoterms, :approved_freight_cap_inr,
            :po_total_taxable_inr, :currency, :created_date
        )
        """,
        ERP_SEED_DATA["purchase_orders"],
    )
    conn.executemany(
        """
        INSERT INTO po_lines VALUES (
            :po_id, :line_no, :sku, :description, :ordered_qty, :po_unit_price_inr, :gst_rate
        )
        """,
        ERP_SEED_DATA["po_lines"],
    )
    conn.executemany(
        """
        INSERT INTO goods_receipts VALUES (
            :grn_id, :po_id, :sku, :received_qty, :accepted_qty, :doa_rejected_qty,
            :grn_date, :qc_notes, :raw_wms_scan_dump
        )
        """,
        ERP_SEED_DATA["goods_receipts"],
    )
    conn.executemany(
        """
        INSERT INTO vendor_invoices VALUES (
            :invoice_id, :po_id, :vendor_id, :invoice_date, :irn_hash, :irn_status,
            :gstr2b_status, :claimed_freight_inr, :invoice_total_taxable_inr,
            :invoice_gst_inr, :invoice_grand_total_inr, :remittance_memo
        )
        """,
        ERP_SEED_DATA["vendor_invoices"],
    )
    conn.executemany(
        """
        INSERT INTO invoice_lines VALUES (
            :invoice_id, :line_no, :sku, :billed_qty, :billed_unit_price_inr,
            :billed_line_total_inr, :gst_rate
        )
        """,
        ERP_SEED_DATA["invoice_lines"],
    )
    conn.executemany(
        """
        INSERT INTO contract_amendments VALUES (
            :amendment_id, :po_id, :sku, :approved_unit_price_inr,
            :approved_freight_waiver_inr, :status, :approvers, :notes
        )
        """,
        ERP_SEED_DATA["contract_amendments"],
    )
    conn.executemany(
        "INSERT INTO fc_dock_logs VALUES (:po_id, :hub, :log_blob)",
        ERP_SEED_DATA["fc_dock_logs"],
    )
    conn.commit()
    return conn


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------------------------------
# Versions of the policy gate and of the bundle tool.
#
# v1 (the code the Category 5 ablation ran on 2026-11-26) is kept ONLY so recorded runs can be replayed and their
# sha256-pinned tool outputs reproduced. Everything else uses the current versions.
# --------------------------------------------------------------------------------------------------
GATE_VERSION_V1 = "v1-band-unconditional"  # the gate the experiment ran on (see below for what it got wrong)
# Fixed 2026-11-26, one version for four fixes, each read from the manual's wording:
#   2.1  the 1.5% band passes only when the PO's currency notes specify an index-linked float;
#   2.2/2.3  a SIGNED_ACTIVE amendment's approved_freight_waiver_inr raises the PO freight cap;
#   1.1(a)/3.2  GST at each line's own (PO) rate when an invoice mixes rates;
#   4.1 Trigger 3  duplicate invoice_id already in reconciliation_vouchers, or vendor risk_flag PAYMENT_FREEZE.
GATE_VERSION_V2 = "v2-manual-aligned"
GATE_VERSIONS: tuple[str, ...] = (GATE_VERSION_V1, GATE_VERSION_V2)
GATE_VERSION = GATE_VERSION_V2

BUNDLE_VERSION_V1 = "v1-no-po-currency"  # fetch_3way_match_bundle as the experiment ran it
# 2026-11-26: the bundle also returns what the fixed gate reads, so a model can check the same conditions:
# header.currency (PO currency notes, 2.1), header.risk_flag (vendor PAYMENT_FREEZE, Trigger 3),
# header.posted_vouchers (vouchers already posted for this invoice_id, Trigger 3), matched_lines[].po_gst_rate (1.1(a)).
BUNDLE_VERSION_V2 = "v2-manual-aligned"
BUNDLE_VERSIONS: tuple[str, ...] = (BUNDLE_VERSION_V1, BUNDLE_VERSION_V2)
BUNDLE_VERSION = BUNDLE_VERSION_V2

PRICE_RULE_WITHIN_BAND = "WITHIN_1.5PCT_TOLERANCE"
PRICE_RULE_WITHIN_BAND_NOT_INDEX_LINKED = "WITHIN_1.5PCT_NOT_INDEX_LINKED_PO_RATE"
PAYMENT_FREEZE_FLAG = "PAYMENT_FREEZE"
HARD_BLOCK_ROUTE = "route to Forensic Tax & Internal Audit review, queue AP-FRAUD-IRN-HOLD (P1 SLA 4h)"


def po_currency_index_linked(currency_notes: str | None) -> bool:
    """Manual 2.1: does the PO's currency note specify an index-linked float?

    The ERP keeps a PO's currency notes in `purchase_orders.currency` (free text). A plain currency code such as
    `"INR"` -- every PO in the seed and the ablation fixtures -- is NOT index-linked. The note qualifies only when it
    says "index-linked" (case-insensitive; a space, hyphen or underscore between the words, or none), e.g.
    `"INR (index-linked float: LME copper)"`. Anything else is treated as a standard fixed-price PO.

    Negation: a mention is ignored when one of `not / no / non / without / never / nor` appears among the three words
    before it in the same clause (clauses split at , ; : . ( ) / |), so "INR - not index linked", "non-index-linked",
    "no index linked float" and "without index-linked pricing" are NOT index-linked. The note qualifies if any
    un-negated mention remains (e.g. "INR; no surcharge, index-linked float")."""
    text = str(currency_notes or "").lower()
    for clause in re.split(r"[,;:.()/|]", text):
        words = re.findall(r"[a-z0-9]+", clause)
        for i, w in enumerate(words):
            if w == "indexlinked" or (w == "index" and words[i + 1 : i + 2] == ["linked"]):
                if not _INDEX_LINK_NEGATORS.intersection(words[max(0, i - 3) : i]):
                    return True
    return False


_INDEX_LINK_NEGATORS = frozenset({"not", "no", "non", "without", "never", "nor"})


def _check_version(value: str, allowed: tuple[str, ...], what: str) -> str:
    if value not in allowed:
        raise ValueError(f"Unknown {what} `{value}`; expected one of {list(allowed)}")
    return value


def evaluate_deterministic_policy_gate(
    conn: sqlite3.Connection,
    invoice_id: str,
    *,
    gate_version: str = GATE_VERSION,
) -> dict[str, Any]:
    """Deterministic Python AP tolerance & statutory gate over SQLite ERP rows.

    Current gate (`v2-manual-aligned`), each rule read from the manual (SOP-AP-3WAY-2026.v4):

    * Hard blocks (4.1): Trigger 1 cancelled IRN; Trigger 2 phantom line (0 accepted, >10% of taxable); Trigger 3
      `DUPLICATE_OR_SANCTIONED_VENDOR` -- the invoice_id already has a row in `reconciliation_vouchers`, or the
      vendor's `risk_flag` is `PAYMENT_FREEZE`. Any trigger: BLOCK_EXCEPTION_HOLD, all four amounts 0.00.
    * Price per line (2.1 / 2.2): a SIGNED_ACTIVE amendment caps the rate at its approved price; at or below the PO
      rate is paid as billed; a rise of at most 1.5% is paid as billed ONLY when the PO's currency notes specify an
      index-linked float (`po_currency_index_linked`), otherwise the PO rate (`WITHIN_1.5PCT_NOT_INDEX_LINKED_PO_RATE`);
      a larger rise is capped to the PO rate. The overrun goes to the debit note.
    * Freight (2.2 / 2.3 / 2.4): the allowed freight is MIN(claimed, PO cap + the approved_freight_waiver_inr of the
      PO's SIGNED_ACTIVE amendments); the rest is disallowed into the debit note.
    * GST (1.1(a) / 3.2): ROUND(authorized_net_principal_inr * gst_rate, 2) when every line has one rate (as before);
      when the PO lines carry different rates, ROUND(SUM(authorized_line_total * line rate) + allowed freight * the
      rate of the line with the largest authorized total, 2).

    `gate_version="v1-band-unconditional"` reproduces the gate the experiment ran on (band passed for every PO,
    waivers ignored, the first line's GST rate for the whole invoice, no Trigger 3) for replaying recorded runs only.
    On every invoice none of these conditions touches, the two versions return byte-identical output."""
    _check_version(gate_version, GATE_VERSIONS, "gate_version")
    inv_row = conn.execute(
        """
        SELECT vi.*, po.fc_hub, po.approved_freight_cap_inr, po.po_total_taxable_inr,
               po.currency AS po_currency_notes,
               v.name AS vendor_name, v.gstin, v.udyam_tier, v.msmed_45d_applicable,
               v.risk_flag AS vendor_risk_flag
        FROM vendor_invoices vi
        JOIN purchase_orders po ON vi.po_id = po.po_id
        JOIN vendors v ON vi.vendor_id = v.vendor_id
        WHERE vi.invoice_id = ?
        """,
        (invoice_id,),
    ).fetchone()
    if not inv_row:
        return {"error": f"Unknown invoice_id {invoice_id}"}

    inv = dict(inv_row)
    po_id = inv["po_id"]

    line_rows = _rows_to_dicts(
        conn.execute(
            """
            SELECT il.line_no, il.sku, il.billed_qty, il.billed_unit_price_inr,
                   il.billed_line_total_inr, il.gst_rate,
                   pl.ordered_qty, pl.po_unit_price_inr, pl.gst_rate AS po_gst_rate,
                   gr.received_qty, gr.accepted_qty, gr.doa_rejected_qty, gr.qc_notes
            FROM invoice_lines il
            JOIN po_lines pl ON pl.po_id = ? AND pl.sku = il.sku
            JOIN goods_receipts gr ON gr.po_id = ? AND gr.sku = il.sku
            WHERE il.invoice_id = ?
            ORDER BY il.line_no
            """,
            (po_id, po_id, invoice_id),
        ).fetchall()
    )
    v2 = gate_version != GATE_VERSION_V1
    amend_rows = _rows_to_dicts(
        conn.execute(
            """
            SELECT amendment_id, sku, approved_unit_price_inr, approved_freight_waiver_inr,
                   status, approvers
            FROM contract_amendments
            WHERE po_id = ? AND status = 'SIGNED_ACTIVE'
            """,
            (po_id,),
        ).fetchall()
    )
    amend_by_sku = {a["sku"]: a for a in amend_rows}

    block_reasons: list[str] = []
    if (
        inv["gstr2b_status"] == "IRN_CANCELLED_INVALID"
        or inv["irn_status"] == "CANCELLED_ON_IRP_WITHIN_24H"
    ):
        block_reasons.append(
            "HARD_BLOCK_IRN_CANCELLED: NIC IRP e-Invoice IRN cancelled within 24h (CGST Sec 74 risk)."
        )

    taxable_total = float(inv["invoice_total_taxable_inr"])
    for ln in line_rows:
        if int(ln["accepted_qty"]) == 0 and float(ln["billed_line_total_inr"]) > 0.10 * taxable_total:
            block_reasons.append(
                f"HARD_BLOCK_PHANTOM_LINE: SKU {ln['sku']} billed INR {ln['billed_line_total_inr']:,.0f} "
                f"with 0 units accepted at {inv['fc_hub']} GRN (>10% invoice threshold)."
            )
    trigger12 = bool(block_reasons)
    if v2:  # manual 4.1 Trigger 3 (DUPLICATE_OR_SANCTIONED_VENDOR)
        posted = conn.execute(
            "SELECT voucher_id, decision FROM reconciliation_vouchers WHERE invoice_id = ?", (invoice_id,)
        ).fetchall()
        for row in posted:
            block_reasons.append(
                f"HARD_BLOCK_DUPLICATE_INVOICE: invoice_id {invoice_id} already posted in reconciliation_vouchers "
                f"({row['voucher_id']}, {row['decision']}); {HARD_BLOCK_ROUTE}."
            )
        if str(inv.get("vendor_risk_flag") or "").strip().upper() == PAYMENT_FREEZE_FLAG:
            block_reasons.append(
                f"HARD_BLOCK_VENDOR_PAYMENT_FREEZE: vendor {inv['vendor_id']} ({inv['vendor_name']}) is flagged "
                f"{PAYMENT_FREEZE_FLAG}; {HARD_BLOCK_ROUTE}."
            )

    if block_reasons:
        return {
            "gate_id": "AP-POL-GATE-01",
            "invoice_id": invoice_id,
            "po_id": po_id,
            "hard_block": True,
            "circuit_breaker_halt": True,
            "escalation_required": False,
            "block_reasons": block_reasons,
            "recommended_decision": "BLOCK_EXCEPTION_HOLD",
            "authorized_net_principal_inr": 0.0,
            "authorized_gst_payout_inr": 0.0,
            "gst_escrow_holdback_inr": 0.0,
            "debit_note_deduction_inr": 0.0,
            "line_findings": [
                {
                    "sku": ln["sku"],
                    "billed_qty": ln["billed_qty"],
                    "grn_accepted_qty": ln["accepted_qty"],
                    "status": (
                        "PHANTOM_UNRECEIVED" if int(ln["accepted_qty"]) == 0
                        # Trigger 3 alone; the recorded label is kept whenever Trigger 1 or 2 fired
                        else "HELD_BY_IRN_BLOCK" if trigger12 else "HELD_BY_DUPLICATE_OR_FREEZE_BLOCK"
                    ),
                }
                for ln in line_rows
            ],
        }

    authorized_merch = 0.0
    line_findings: list[dict[str, Any]] = []
    discrepancy_count = 0

    for ln in line_rows:
        sku = ln["sku"]
        ordered_qty = int(ln["ordered_qty"])
        accepted_qty = int(ln["accepted_qty"])
        doa_qty = int(ln["doa_rejected_qty"])
        billed_qty = int(ln["billed_qty"])
        po_price = float(ln["po_unit_price_inr"])
        billed_price = float(ln["billed_unit_price_inr"])

        payable_qty = min(ordered_qty, accepted_qty)
        amd = amend_by_sku.get(sku)

        if amd is not None:
            eff_price = min(billed_price, float(amd["approved_unit_price_inr"]))
            price_rule = f"AMENDMENT_APPROVED ({amd['amendment_id']})"
            discrepancy_count += 1
        elif billed_price <= po_price:
            eff_price = billed_price
            price_rule = "EXACT_PO_MATCH"
        elif billed_price <= po_price * 1.015:
            if gate_version == GATE_VERSION_V1 or po_currency_index_linked(inv["po_currency_notes"]):
                eff_price = billed_price
                price_rule = PRICE_RULE_WITHIN_BAND
            else:  # manual 2.1: a standard (not index-linked) PO pays the PO unit rate unless amended
                eff_price = po_price
                price_rule = PRICE_RULE_WITHIN_BAND_NOT_INDEX_LINKED
                discrepancy_count += 1
        else:
            eff_price = po_price
            price_rule = "UNAUTHORIZED_HIKE_CAPPED_TO_PO"
            discrepancy_count += 1

        if billed_qty > payable_qty or doa_qty > 0:
            discrepancy_count += 1

        auth_line = round(payable_qty * eff_price, 2)
        billed_line = float(ln["billed_line_total_inr"])
        line_deduction = round(billed_line - auth_line, 2)
        authorized_merch += auth_line

        line_findings.append(
            {
                "sku": sku,
                "ordered_qty": ordered_qty,
                "grn_accepted_qty": accepted_qty,
                "doa_rejected_qty": doa_qty,
                "payable_qty": payable_qty,
                "po_unit_price_inr": po_price,
                "billed_unit_price_inr": billed_price,
                "effective_unit_price_inr": eff_price,
                "price_rule": price_rule,
                "authorized_line_total_inr": auth_line,
                "line_deduction_inr": line_deduction,
            }
        )

    claimed_freight = float(inv["claimed_freight_inr"])
    po_freight_cap = float(inv["approved_freight_cap_inr"])
    # manual 2.2 / 2.3: a SIGNED_ACTIVE amendment can override the PO freight cap by its approved waiver
    freight_waiver = round(sum(float(a["approved_freight_waiver_inr"] or 0.0) for a in amend_rows), 2) if v2 else 0.0
    freight_cap = po_freight_cap + freight_waiver
    if claimed_freight > po_freight_cap:
        discrepancy_count += 1
    auth_freight = min(claimed_freight, freight_cap)

    authorized_net_principal = round(authorized_merch + auth_freight, 2)
    debit_note_deduction = round(taxable_total - authorized_net_principal, 2)

    rates = [float(ln["po_gst_rate"] if v2 else ln["gst_rate"]) for ln in line_rows]
    mixed_rates = v2 and len(set(rates)) > 1
    if mixed_rates:
        # manual 1.1(a): the PO fixes each line's GST rate; 3.2's ROUND(principal * gst_rate, 2) applied per line,
        # freight at the rate of the line with the largest authorized total (the manual gives no freight rate)
        lead = max(range(len(line_findings)), key=lambda i: (line_findings[i]["authorized_line_total_inr"], -i))
        net_gst = round(
            sum(f["authorized_line_total_inr"] * r for f, r in zip(line_findings, rates)) + auth_freight * rates[lead], 2
        )
    else:
        gst_rate = rates[0] if rates else 0.18
        net_gst = round(authorized_net_principal * gst_rate, 2)

    if inv["gstr2b_status"] == "MATCHED_VERIFIED":
        authorized_gst_payout = net_gst
        gst_escrow_holdback = 0.0
        decision = (
            "APPROVE_CLEAN"
            if debit_note_deduction == 0.0
            else "APPROVE_PARTIAL_DEBIT_NOTE"
        )
    else:
        authorized_gst_payout = 0.0
        gst_escrow_holdback = net_gst
        decision = (
            "APPROVE_WITH_GST_ESCROW"
            if debit_note_deduction == 0.0
            else "APPROVE_PARTIAL_DEBIT_NOTE"
        )

    # Escalate to Sonnet 5.5 when multiple commercial/amendment/freight exceptions combine
    escalation_required = bool(discrepancy_count >= 2 or debit_note_deduction > 0)

    out: dict[str, Any] = {
        "gate_id": "AP-POL-GATE-01",
        "invoice_id": invoice_id,
        "po_id": po_id,
        "hard_block": False,
        "circuit_breaker_halt": False,
        "escalation_required": escalation_required,
        "gstr2b_status": inv["gstr2b_status"],
        "msmed_45d_applicable": bool(inv["msmed_45d_applicable"]),
        "recommended_decision": decision,
        "authorized_net_principal_inr": authorized_net_principal,
        "authorized_gst_payout_inr": authorized_gst_payout,
        "gst_escrow_holdback_inr": gst_escrow_holdback,
        "debit_note_deduction_inr": debit_note_deduction,
        "line_findings": line_findings,
        "freight_disallowed_inr": round(max(0.0, claimed_freight - freight_cap), 2),
    }
    # keys added only where the new rules apply, so the output elsewhere stays byte-identical to the recorded gate
    if freight_waiver > 0:
        out["freight_waiver_applied_inr"] = round(min(freight_waiver, max(0.0, claimed_freight - po_freight_cap)), 2)
    if mixed_rates:
        out["gst_rates_by_line"] = {f["sku"]: r for f, r in zip(line_findings, rates)}
    return out


class Cat5ErpSession:
    """Stateful SQLite ERP session tracking executed SQL, touched tables, and committed voucher."""

    def __init__(
        self,
        *,
        rung_id: str,
        gate_version: str = GATE_VERSION,
        bundle_version: str = BUNDLE_VERSION,
    ) -> None:
        self.conn = create_seeded_erp_connection()
        self.rung_id = rung_id
        # Non-current versions exist only to replay recorded runs (see GATE_VERSIONS / BUNDLE_VERSIONS).
        self.gate_version = _check_version(gate_version, GATE_VERSIONS, "gate_version")
        self.bundle_version = _check_version(bundle_version, BUNDLE_VERSIONS, "bundle_version")
        self.tables_touched: set[str] = set()
        self.gate_by_invoice: dict[str, dict[str, Any]] = {}
        self.total_tool_calls = 0
        self.optimal_tool_calls = 0

    def close(self) -> None:
        self.conn.close()

    def get_committed_voucher(self, invoice_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM reconciliation_vouchers WHERE invoice_id = ?",
            (invoice_id,),
        ).fetchone()
        return dict(row) if row else None

    def execute_tool(
        self,
        name: str,
        tool_input: dict[str, Any],
    ) -> tuple[str, str, list[str], bool, dict[str, Any] | None]:
        """Execute an ERP tool call against live SQLite and return trace metadata."""
        self.total_tool_calls += 1

        if name == "query_invoice_raw":
            inv_id = str(tool_input.get("invoice_id") or "")
            sql = (
                "SELECT * FROM vendor_invoices WHERE invoice_id = ?;\n"
                "SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY line_no;"
            )
            inv = _rows_to_dicts(
                self.conn.execute("SELECT * FROM vendor_invoices WHERE invoice_id = ?", (inv_id,)).fetchall()
            )
            lines = _rows_to_dicts(
                self.conn.execute(
                    "SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY line_no", (inv_id,)
                ).fetchall()
            )
            touched = ["vendor_invoices", "invoice_lines"]
            self.tables_touched.update(touched)
            is_opt = False
            return json.dumps({"invoice": inv, "lines": lines}, indent=2), sql, touched, is_opt, None

        if name == "query_po_raw":
            po_id = str(tool_input.get("po_id") or "")
            sql = (
                "SELECT * FROM purchase_orders WHERE po_id = ?;\n"
                "SELECT * FROM po_lines WHERE po_id = ? ORDER BY line_no;"
            )
            po = _rows_to_dicts(
                self.conn.execute("SELECT * FROM purchase_orders WHERE po_id = ?", (po_id,)).fetchall()
            )
            lines = _rows_to_dicts(
                self.conn.execute(
                    "SELECT * FROM po_lines WHERE po_id = ? ORDER BY line_no", (po_id,)
                ).fetchall()
            )
            touched = ["purchase_orders", "po_lines"]
            self.tables_touched.update(touched)
            return json.dumps({"purchase_order": po, "po_lines": lines}, indent=2), sql, touched, False, None

        if name == "query_grn_wms_telemetry":
            po_id = str(tool_input.get("po_id") or "")
            sql = "SELECT * FROM goods_receipts WHERE po_id = ? ORDER BY grn_id;"
            grns = _rows_to_dicts(
                self.conn.execute(
                    "SELECT * FROM goods_receipts WHERE po_id = ? ORDER BY grn_id", (po_id,)
                ).fetchall()
            )
            touched = ["goods_receipts"]
            self.tables_touched.update(touched)
            return json.dumps({"goods_receipts": grns}, indent=2), sql, touched, False, None

        if name == "query_vendor_audit_history":
            vendor_id = str(tool_input.get("vendor_id") or "")
            sql = "SELECT * FROM vendors WHERE vendor_id = ?;"
            vendors = _rows_to_dicts(
                self.conn.execute("SELECT * FROM vendors WHERE vendor_id = ?", (vendor_id,)).fetchall()
            )
            touched = ["vendors"]
            self.tables_touched.update(touched)
            return json.dumps({"vendors": vendors}, indent=2), sql, touched, False, None

        if name == "query_contract_amendments_and_dock_logs":
            po_id = str(tool_input.get("po_id") or "")
            sql = (
                "SELECT * FROM contract_amendments WHERE po_id = ?;\n"
                "SELECT * FROM fc_dock_logs WHERE po_id = ?;"
            )
            amends = _rows_to_dicts(
                self.conn.execute("SELECT * FROM contract_amendments WHERE po_id = ?", (po_id,)).fetchall()
            )
            logs = _rows_to_dicts(
                self.conn.execute("SELECT * FROM fc_dock_logs WHERE po_id = ?", (po_id,)).fetchall()
            )
            touched = ["contract_amendments", "fc_dock_logs"]
            self.tables_touched.update(touched)
            return json.dumps({"contract_amendments": amends, "fc_dock_logs": logs}, indent=2), sql, touched, False, None

        if name == "fetch_3way_match_bundle":
            inv_id = str(tool_input.get("invoice_id") or "")
            bundle_v1 = self.bundle_version == BUNDLE_VERSION_V1
            sql = (
                "SELECT vi.invoice_id, vi.po_id, vi.vendor_id, vi.irn_status, vi.gstr2b_status,\n"
                "       vi.claimed_freight_inr, vi.invoice_total_taxable_inr, vi.invoice_gst_inr,\n"
                "       vi.invoice_grand_total_inr, po.fc_hub, po.approved_freight_cap_inr,\n"
                "       v.name AS vendor_name, v.gstin, v.udyam_tier, v.msmed_45d_applicable"
                + ("\n" if bundle_v1 else ",\n       po.currency, v.risk_flag  -- PO currency notes (2.1), vendor flag (4.1)\n")
                + "FROM vendor_invoices vi\n"
                "JOIN purchase_orders po ON vi.po_id = po.po_id\n"
                "JOIN vendors v ON vi.vendor_id = v.vendor_id\n"
                "WHERE vi.invoice_id = ?;\n"
                "-- + projected JOIN on invoice_lines x po_lines x goods_receipts + contract_amendments"
                + ("" if bundle_v1 else "\n-- + SELECT voucher_id, decision FROM reconciliation_vouchers WHERE invoice_id = ? (4.1 Trigger 3)")
            )
            header = _rows_to_dicts(
                self.conn.execute(
                    """
                    SELECT vi.invoice_id, vi.po_id, vi.vendor_id, vi.invoice_date,
                           vi.irn_status, vi.gstr2b_status, vi.claimed_freight_inr,
                           vi.invoice_total_taxable_inr, vi.invoice_gst_inr, vi.invoice_grand_total_inr,
                           po.fc_hub, po.incoterms, po.approved_freight_cap_inr,
                           v.name AS vendor_name, v.gstin, v.udyam_tier, v.msmed_45d_applicable
                    FROM vendor_invoices vi
                    JOIN purchase_orders po ON vi.po_id = po.po_id
                    JOIN vendors v ON vi.vendor_id = v.vendor_id
                    WHERE vi.invoice_id = ?
                    """,
                    (inv_id,),
                ).fetchall()
            )
            if not header:
                return json.dumps({"error": f"Invoice {inv_id} not found"}), sql, ["vendor_invoices"], True, None
            po_id = header[0]["po_id"]
            if not bundle_v1:  # fields the fixed gate reads (v1, as recorded before 2026-11-26, has none of them)
                extra = self.conn.execute(
                    """
                    SELECT po.currency, v.risk_flag
                    FROM vendor_invoices vi
                    JOIN purchase_orders po ON vi.po_id = po.po_id
                    JOIN vendors v ON vi.vendor_id = v.vendor_id
                    WHERE vi.invoice_id = ?
                    """,
                    (inv_id,),
                ).fetchone()
                header[0]["currency"] = extra["currency"]
                header[0]["risk_flag"] = extra["risk_flag"]
                header[0]["posted_vouchers"] = _rows_to_dicts(
                    self.conn.execute(
                        "SELECT voucher_id, decision FROM reconciliation_vouchers WHERE invoice_id = ? ORDER BY voucher_id",
                        (inv_id,),
                    ).fetchall()
                )
            lines = _rows_to_dicts(
                self.conn.execute(
                    """
                    SELECT il.line_no, il.sku, il.billed_qty, il.billed_unit_price_inr,
                           il.billed_line_total_inr, il.gst_rate,
                           pl.ordered_qty, pl.po_unit_price_inr,
                           gr.grn_id, gr.received_qty, gr.accepted_qty, gr.doa_rejected_qty, gr.qc_notes,
                           pl.gst_rate AS po_gst_rate
                    FROM invoice_lines il
                    JOIN po_lines pl ON pl.po_id = ? AND pl.sku = il.sku
                    JOIN goods_receipts gr ON gr.po_id = ? AND gr.sku = il.sku
                    WHERE il.invoice_id = ?
                    ORDER BY il.line_no
                    """,
                    (po_id, po_id, inv_id),
                ).fetchall()
            )
            if bundle_v1:
                for ln in lines:
                    ln.pop("po_gst_rate", None)
            amends = _rows_to_dicts(
                self.conn.execute(
                    """
                    SELECT amendment_id, po_id, sku, approved_unit_price_inr,
                           approved_freight_waiver_inr, status, approvers, notes
                    FROM contract_amendments
                    WHERE po_id = ?
                    """,
                    (po_id,),
                ).fetchall()
            )
            touched = ["vendor_invoices", "purchase_orders", "vendors", "invoice_lines", "po_lines", "goods_receipts", "contract_amendments"]
            if not bundle_v1:
                touched.append("reconciliation_vouchers")
            self.tables_touched.update(touched)
            self.optimal_tool_calls += 1
            bundle = {
                "header": header[0],
                "matched_lines": lines,
                "contract_amendments": amends,
            }
            return json.dumps(bundle, indent=2), sql, touched, True, None

        if name == "run_policy_tolerance_gate":
            inv_id = str(tool_input.get("invoice_id") or "")
            sql = (
                "/* AP-POL-GATE-01 Deterministic Check over vendor_invoices + invoice_lines "
                "+ po_lines + goods_receipts + contract_amendments */"
            )
            gate_out = evaluate_deterministic_policy_gate(self.conn, inv_id, gate_version=self.gate_version)
            self.gate_by_invoice[inv_id] = gate_out
            touched = ["vendor_invoices", "purchase_orders", "goods_receipts", "contract_amendments"]
            self.tables_touched.update(touched)
            self.optimal_tool_calls += 1
            return json.dumps(gate_out, indent=2), sql, touched, True, gate_out

        if name == "commit_reconciliation_voucher":
            inv_id = str(tool_input.get("invoice_id") or "")
            po_id = str(tool_input.get("po_id") or "")
            governed = self.rung_id != "unbounded_sonnet_loop"
            if governed and inv_id not in self.gate_by_invoice:
                err = {
                    "status": "REJECTED_BY_GOVERNANCE_GATE",
                    "error": "Must call run_policy_tolerance_gate(invoice_id) before committing reconciliation voucher.",
                }
                return json.dumps(err), "-- REJECTED: Missing AP-POL-GATE-01 check", [], False, None

            voucher_id = f"VCH-{inv_id[-4:]}-{self.rung_id[:3].upper()}"
            gate_ver = 1 if inv_id in self.gate_by_invoice else 0
            sql = (
                "INSERT OR REPLACE INTO reconciliation_vouchers "
                "(voucher_id, invoice_id, po_id, decision, authorized_net_principal_inr, "
                "authorized_gst_payout_inr, gst_escrow_holdback_inr, debit_note_deduction_inr, "
                "gate_verified, audit_summary) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);"
            )
            params = (
                voucher_id,
                inv_id,
                po_id,
                str(tool_input.get("decision") or ""),
                round(float(tool_input.get("authorized_net_principal_inr") or 0.0), 2),
                round(float(tool_input.get("authorized_gst_payout_inr") or 0.0), 2),
                round(float(tool_input.get("gst_escrow_holdback_inr") or 0.0), 2),
                round(float(tool_input.get("debit_note_deduction_inr") or 0.0), 2),
                gate_ver,
                str(tool_input.get("audit_summary") or "")[:500],
            )
            self.conn.execute(sql, params)
            self.conn.commit()
            touched = ["reconciliation_vouchers"]
            self.tables_touched.update(touched)
            self.optimal_tool_calls += 1
            return (
                json.dumps(
                    {
                        "status": "COMMITTED",
                        "voucher_id": voucher_id,
                        "invoice_id": inv_id,
                        "decision": params[3],
                        "authorized_net_principal_inr": params[4],
                        "authorized_gst_payout_inr": params[5],
                        "gst_escrow_holdback_inr": params[6],
                        "debit_note_deduction_inr": params[7],
                        "gate_verified": bool(gate_ver),
                    },
                    indent=2,
                ),
                sql,
                touched,
                True,
                self.gate_by_invoice.get(inv_id),
            )

        return (
            json.dumps({"error": f"Unknown tool `{name}`"}),
            f"-- UNKNOWN TOOL {name}",
            [],
            False,
            None,
        )
