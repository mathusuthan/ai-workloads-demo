"""India-grounded ERP Seed Data, AP Policy Manual & 3-Way Invoice Presets for Category 5."""

from __future__ import annotations

import json
from typing import Any

AP_POLICY_MANUAL_MARKDOWN = """# NOVAMART ENTERPRISE ACCOUNTS PAYABLE & 3-WAY ERP RECONCILIATION STANDARD OPERATING MANUAL (SOP-AP-3WAY-2026.v4)

Document ID: SOP-AP-3WAY-2026.v4 | Custodian: NovaMart Controller & Procurement Finance Office, Bengaluru
Applies to: Automated 3-Way Invoice Reconciliation across FC-BLR-01 (Bengaluru), FC-BOM-02 (Bhiwandi), FC-HYD-01 (Hyderabad), and FC-DEL-03 (Gurugram)

---

## MODULE 1: THREE-WAY MATCH CORE INVARIANTS (PO × GRN × TAX INVOICE)

1.1 Mandatory Evidence Chain: No supplier invoice in SAP / SQLite ERP may enter the settlement batch without reconciling three independent ledger records:
   (a) The authoritative Purchase Order (`purchase_orders` + `po_lines`) fixing ordered SKU quantities, landed DDP INR unit rates, freight terms (`approved_freight_cap_inr`), and HSN/GST rates.
   (b) The Warehouse Goods Receipt Note (`goods_receipts`) certified at the destination FC inward receiving dock, splitting `received_qty`, `accepted_qty` (QC-passed), and `doa_rejected_qty` (damaged/failed AQL Level II inspection).
   (c) The Supplier Tax Invoice (`vendor_invoices` + `invoice_lines`) bearing a valid 64-character NIC Invoice Registration Portal ('IRP') IRN hash, supplier GSTIN, e-Way Bill link, billed unit prices, and claimed freight.

1.2 Payable Quantity Rule (`PAYABLE_QTY`):
   - NovaMart NEVER pays for undelivered or dock-rejected DOA inventory.
   - For every invoice line item, `payable_qty = MIN(po_ordered_qty, grn_accepted_qty)`.
   - Any delta `(billed_qty - payable_qty) * effective_approved_unit_price` constitutes an automatic commercial shortage / DOA deduction rolled into `debit_note_deduction_inr` (settled via CGST Section 34 credit/debit note workflow).

1.3 Receiving Tolerance & Over-Shipment Lock:
   - NovaMart warehouses strictly reject unscheduled over-shipments (`billed_qty > po_ordered_qty`). Even if `received_qty` exceeds `po_ordered_qty`, payable units are capped strictly at `po_ordered_qty`.
   - Zero-accepted-quantity lines (`grn_accepted_qty == 0`) with positive billed quantity MUST be flagged immediately under Module 4 Circuit-Breaker thresholds.

---

## MODULE 2: UNIT-PRICE VARIANCE & FREIGHT TOLERANCE MATRIX

2.1 Baseline Unit-Price Variance Tolerance (`1.50%` Rounding Band):
   - Compare `billed_unit_price_inr` against `po_unit_price_inr`:
     * If `billed_unit_price_inr <= po_unit_price_inr`: authorized rate = `billed_unit_price_inr`.
     * If `po_unit_price_inr < billed_unit_price_inr <= po_unit_price_inr * 1.015`: tiny FX/metal-surcharge rounding within `1.50%` MAY pass ONLY when PO currency notes specify index-linked float; otherwise standard landed DDP catalog POs default to PO unit rate unless amended. Under automated gate enforcement, check first whether an active signed `Contract Amendment` exists in `contract_amendments`.
     * If `billed_unit_price_inr > po_unit_price_inr * 1.015`: STRICTLY UNAUTHORIZED unless an active row in `contract_amendments` matching `(po_id, sku)` with `status = 'SIGNED_ACTIVE'` explicitly approves `approved_unit_price_inr >= billed_unit_price_inr`.

2.2 Signed Contract Amendment Precedence (`contract_amendments`):
   - Only Category Finance Director + VP Procurement dual-signed amendments bearing an active `amendment_id` (e.g., `AMD-BOM-5512-A`) can override PO unit rates or freight caps.
   - Where a line item matches a `SIGNED_ACTIVE` amendment, `effective_approved_unit_price = MIN(billed_unit_price_inr, amendment_approved_unit_price_inr)`.
   - Where a line item exceeds `1.50%` over PO price WITHOUT any matching amendment row, `effective_approved_unit_price = po_unit_price_inr`, and the unauthorized price overrun `(billed_unit_price_inr - po_unit_price_inr) * payable_qty` MUST be added to `debit_note_deduction_inr` (note: combined with any DOA shortage on `(billed_qty * billed_unit_price) - (payable_qty * effective_approved_unit_price)` so deductions equal `billed_merchandise_total - authorized_merchandise_total`, never double-counted).

2.3 Landed DDP Freight Rule (`approved_freight_cap_inr`):
   - Standard NovaMart POs specify DDP (Delivered Duty Paid inside FC dock) with `approved_freight_cap_inr = 0.0`.
   - Any vendor `claimed_freight_inr > approved_freight_cap_inr` without an active freight waiver amendment is disallowed in full (`excess_freight = MAX(0, claimed_freight_inr - approved_freight_cap_inr)`), added to `debit_note_deduction_inr`.

2.4 Deduplication Math Verification (Line-Item Principal Accounting):
   - Compute `authorized_line_total = payable_qty * effective_approved_unit_price`.
   - Sum across all invoice lines: `authorized_net_principal_inr = SUM(authorized_line_total) + MIN(claimed_freight_inr, approved_freight_cap_inr)`.
   - Total pre-tax debit note deduction: `debit_note_deduction_inr = ROUND(invoice_total_taxable_inr - authorized_net_principal_inr, 2)`.
   - Invariant Check: `authorized_net_principal_inr + debit_note_deduction_inr == invoice_total_taxable_inr` whenever the invoice is NOT blocked (`decision != 'BLOCK_EXCEPTION_HOLD'`).

---

## MODULE 3: CGST SECTION 16(2)(aa) GSTR-2B ESCROW VS. MSMED SECTION 15 / 43B(h) SPLIT-REMITTANCE

3.1 Why Principal & GST Tax Are Evaluated Separately in India:
   - Under Section 16(2)(aa) of the Central Goods and Services Tax Act, 2017 ('CGST Act'), NovaMart cannot claim Input Tax Credit ('ITC') unless the supplier's invoice populates intact in NovaMart's monthly auto-drafted Form GSTR-2B.
   - HOWEVER, under Section 15 of the Micro, Small and Medium Enterprises Development (MSMED) Act, 2006 and Section 43B(h) of the Income Tax Act, 1961, withholding the *entire* invoice payment beyond 45 days for Udyam MSE suppliers triggers compound RBI 3x statutory interest AND corporate income-tax expenditure disallowance on the underlying purchase cost.

3.2 Split-Remittance Adjudication Matrix (Assuming Active Valid NIC IRP e-Invoice IRN):
   - Case A (`gstr2b_status == 'MATCHED_VERIFIED'`):
     * Invoice is confirmed intact in current GSTR-2B without supplier default flags.
     * Release `authorized_net_principal_inr` AND `authorized_gst_payout_inr = ROUND(authorized_net_principal_inr * gst_rate, 2)` (note: GST is paid strictly on the *authorized* net principal after DOA/price/freight deductions, NOT on unapproved excess charges!).
     * Set `gst_escrow_holdback_inr = 0.0`.
     * Decision = `'APPROVE_CLEAN'` if `debit_note_deduction_inr == 0`, else `'APPROVE_PARTIAL_DEBIT_NOTE'`.
   - Case B (`gstr2b_status == 'PENDING_FILING_MISMATCH'` with `irn_status == 'ACTIVE_VERIFIED'`):
     * Supplier generated a valid IRN at dispatch, but Form GSTR-1 has not yet synced into NovaMart's current GSTR-2B pull.
     * To preserve strict compliance with MSMED 45-day / Section 43B(h) settlement on `Net T+43 days`, RELEASE `100%` of `authorized_net_principal_inr` immediately!
     * WITHHOLD the authorized GST portion (`ROUND(authorized_net_principal_inr * gst_rate, 2)`) into NovaMart's non-interest-bearing Tax Compliance Escrow Account: `authorized_gst_payout_inr = 0.0`, `gst_escrow_holdback_inr = ROUND(authorized_net_principal_inr * gst_rate, 2)`.
     * Decision = `'APPROVE_WITH_GST_ESCROW'` (or `'APPROVE_PARTIAL_DEBIT_NOTE'` only if taxable principal also has commercial deductions — policy requires noting both split escrow and debit note if both occur).

---

## MODULE 4: HARD CIRCUIT-BREAKER GATE (`AP-POL-GATE-01` -> `BLOCK_EXCEPTION_HOLD`)

4.1 Mandatory Hard-Block Triggers (Zero Payout Authorized):
   An automated ERP agent MUST immediately halt payment processing and commit `decision = 'BLOCK_EXCEPTION_HOLD'` with ALL four rupee amounts equal to `0.00` (`authorized_net_principal_inr = 0`, `authorized_gst_payout_inr = 0`, `gst_escrow_holdback_inr = 0`, `debit_note_deduction_inr = 0`) whenever ANY of these statutory/fraud triggers fire:
   - Trigger 1 (`CANCELLED_OR_FORGED_IRN`): NIC IRP validation returns `gstr2b_status == 'IRN_CANCELLED_INVALID'` or `irn_status == 'CANCELLED_ON_IRP_WITHIN_24H'`. Cancelling an e-Invoice IRN within 24 hours of dispatch while attempting to collect payment constitutes high-severity ITC fraud exposure under CGST Section 74.
   - Trigger 2 (`PHANTOM_UNRECEIVED_LINE`): Any billed invoice line item has `grn_accepted_qty == 0` and represents `> 10.0%` of `invoice_total_taxable_inr`. Never authorize partial line settlement when a major shipment failed dock arrival/receiving altogether!
   - Trigger 3 (`DUPLICATE_OR_SANCTIONED_VENDOR`): Duplicate `invoice_id` already posted in `reconciliation_vouchers` or vendor flagged `PAYMENT_FREEZE`.

4.2 Loop Governance & Early Termination Rule:
   - The moment `run_policy_tolerance_gate` returns `"hard_block": true` / `"circuit_breaker_halt": true`, DO NOT waste further LLM turns calling secondary dock-gate logs, historical audit trails, or payment calculators. Proceed directly to committing `BLOCK_EXCEPTION_HOLD` in `reconciliation_vouchers` and emitting the exception escalation summary.

---

## MODULE 5: CANONICAL VOUCHER DECISION ENUM & RECONCILIATION TABLE SCHEMA

5.1 Valid `decision` Values in `reconciliation_vouchers`:
   - `APPROVE_CLEAN`: Zero principal deduction (`debit_note_deduction_inr == 0`) AND `GSTR-2B MATCHED_VERIFIED` (`gst_escrow_holdback_inr == 0`).
   - `APPROVE_WITH_GST_ESCROW`: Zero commercial dispute (`debit_note_deduction_inr == 0`) AND valid principal released on T+43 (`authorized_net_principal_inr > 0`), while `18%` GST is placed in `gst_escrow_holdback_inr` (`authorized_gst_payout_inr == 0`) pending GSTR-2B sync.
   - `APPROVE_PARTIAL_DEBIT_NOTE`: Verified quantity shortage/DOA rejection, unauthorized price overrun, or disallowed DDP freight yields `debit_note_deduction_inr > 0`, while verified accepted goods principal (`authorized_net_principal_inr > 0`) and applicable net GST settle cleanly.
   - `BLOCK_EXCEPTION_HOLD`: Hard Circuit-Breaker fired (`IRN_CANCELLED_INVALID`, phantom shipment >10%, or fraud block). All payout and debit fields are set to `0.00` pending Forensic Tax & Internal Audit review (`SLA: P1 4 hours`).

5.2 Voucher Persistence Integrity:
   - Only `commit_reconciliation_voucher` writes the final posting record to SQLite `reconciliation_vouchers`.
   - Under Governed Orchestration (Rungs 2 & 3), `commit_reconciliation_voucher` refuses to commit unless `run_policy_tolerance_gate(invoice_id)` has verified the deterministic arithmetic first—preventing hallucinated rupee payouts caused by LLM mental math errors across multi-line INR calculations.

---

## MODULE 6: DETERMINISTIC MODEL ROUTING, COST PER OUTCOME & ERP QUERY HYGIENE

6.1 Why Naive Exploratory Agent Loops Break Band 4R Unit Economics:
   - Unprojected `SELECT *` tool endpoints (e.g., dumping 1,500-token `raw_wms_scan_dump` barcode arrays, `full_audit_trail_json` 3-year histories, and yard dock logs across 5–7 sequential uncached ReAct steps on `claude-sonnet-5-5`) cause cumulative input tokens to scale quadratically to `30,000–60,000+` tokens per single invoice—plus uncached system prompt re-reads on every tool step!

6.2 Two Production Levers for Category 5 Autonomous Agents:
   - Lever A (Schema Projection + Ephemeral Prefix Caching + Bounded Step Budget): Consolidate 3-way ERP reads into one projection-pruned SQL JOIN (`fetch_3way_match_bundle`), attach `cache_control: {"type": "ephemeral"}` on this SOP policy manual (`>= 4,096` tokens), enforce a strict `max_step_budget = 4`, and gate commitments via deterministic Python math (`run_policy_tolerance_gate`).
   - Lever B (Haiku-First Triage with Deterministic Sonnet Escalation): Run routine bundle fetch + policy gate execution on `claude-haiku-5-5` (`$0.10/M in · $0.50/M out` — 20x cheaper than Sonnet!). Escalate to `claude-sonnet-5-5` ONLY when `run_policy_tolerance_gate` flags `escalation_required = true` (e.g., multi-factor commercial disputes mixing partial DOA returns, signed contract amendments, unauthorized line price hikes, and disallowed freight), allowing straightforward `APPROVE_WITH_GST_ESCROW` and `BLOCK_EXCEPTION_HOLD` cases to complete end-to-end on Haiku at >90% cost reduction while maintaining 100% rupee accuracy.

6.3 GL Account Codes, TDS Sections & Exception Queue Reference (SAP S/4HANA Integration):
   - GL `210100`: Trade Payables Principal (Released T+43 MSMED-Safe Rail; Income Tax Section 43B(h) compliant)
   - GL `142810`: Input CGST/IGST Claimable Clearing (Released upon GSTR-2B Verified Match under CGST Sec 16(2)(aa))
   - GL `219450`: Tax Compliance Escrow Holdback Account (180-day / Sept 30 CGST Rule 37A cure window before DRC-03 or permanent setoff)
   - GL `520900`: Commercial Debit Note Recoveries (DOA Rejections, Price Overruns, Disallowed DDP Freight)
   - GL `214194`: Income Tax TDS Section 194Q (`0.1%` purchase of goods threshold above INR 50.00 Lakh aggregate per FY, tracked separately by SAP withholding engine at payment batch release — do NOT net 194Q TDS inside 3-way reconciliation voucher amounts).
   - Exception Queues: `AP-GST-ESCROW` (SLA 24h), `AP-DEBIT-RECON` (SLA 12h), `AP-FRAUD-IRN-HOLD` (P1 SLA 4h).

6.4 Reference Worked Adjudication Examples for Agents:
   - Example A (Split Escrow on Clean Receipt): Supplier bills INR 10,00,000 taxable + INR 1,80,000 GST (18%). All units pass GRN at FC-BLR-01; NIC IRN is `ACTIVE_VERIFIED`; `gstr2b_status = 'PENDING_FILING_MISMATCH'`. Principal = INR 10,00,000 released on T+43; GST Payout = INR 0; GST Escrow Holdback = INR 1,80,000; Debit Note = INR 0; Decision = `'APPROVE_WITH_GST_ESCROW'`.
   - Example B (DOA Shortage + Signed Amendment + Unapproved Price Hike + Disallowed Freight): Line 1 has 10 DOA @ INR 1,000 -> deduct INR 10,000. Line 2 has +6% price hike backed by signed amendment -> allowed (`INR 0` deduction). Line 3 has +4% price hike with NO amendment -> cap to PO rate. Unapproved DDP freight INR 15,000 -> deduct INR 15,000. Compute authorized net principal first, sum debit note deductions as `invoice_total_taxable_inr - authorized_net_principal_inr`, then calculate 18% net GST strictly on `authorized_net_principal_inr` (NEVER on the raw claimed pre-deduction taxable invoice amount!).
   - Example C (Cancelled IRN or Phantom Line >10%): Stop immediately under Module 4 `AP-POL-GATE-01`. Do not compute prorated payouts for delivered lines when `IRN_CANCELLED_INVALID` or a phantom unreceived line (`accepted_qty == 0` >10% invoice value) triggers `hard_block = true`. Set ALL 4 rupee columns to `0.00` and commit `'BLOCK_EXCEPTION_HOLD'`.

---

## MODULE 7: STATUTORY AUDIT TRAIL, RULE 37A TIMELINE & INTERNAL CONTROLS (IFC / CARO)

7.1 Rule 37A ITC Reversal Reconciliation SLA:
   - Whenever GL `219450` (Tax Compliance Escrow Holdback Account) captures withheld GST under `APPROVE_WITH_GST_ESCROW`, NovaMart SAP schedules automated weekly GSTR-2B re-pulls for up to 180 calendar days from invoice date or September 30 following financial year close (whichever occurs earlier). Upon verified GSTR-2B population, the escrow balance releases on the next Friday NEFT run with zero supplier penalty. Uncured escrow balances convert permanently into supplier debit notes plus CGST Section 50(3) 18% p.a. statutory interest recovery.

7.2 Internal Financial Controls (IFC) & Evidentiary Audit Logging:
   - Every automated reconciliation decision recorded in `reconciliation_vouchers` must link back to raw PO, GRN QC, NIC IRP IRN validation, and (when applicable) `SIGNED_ACTIVE` Contract Amendments so Statutory Auditors executing Section 143(3)(i) IFC walkthroughs can verify zero unauthorized disbursements, zero uninspected SQL mutations, and strict adherence to step-budget limits.
[SOP_BUILD: v2026.11.cat5]"""


def _make_wms_scan_dump(po_id: str, sku_list: list[str], hub: str) -> str:
    pallets = []
    for idx in range(1, 21):
        pallets.append(
            {
                "sscc_barcode": f"89040021{po_id[-4:]}{idx:04d}",
                "dock_bay": f"{hub}-DOCK-{(idx % 6) + 1:02d}",
                "sku": sku_list[idx % len(sku_list)],
                "rfid_gate_ts": f"2026-10-14T0{(idx % 8) + 1}:{(idx * 7) % 60:02d}:19Z",
                "seal_ok": True,
                "aql_sample_temp_c": 26.4,
            }
        )
    return json.dumps({"po_id": po_id, "pallet_scans": pallets})


def _make_vendor_audit_trail(vendor_id: str, name: str) -> str:
    quarters = []
    for yr in (2024, 2025, 2026):
        for q in ("Q1", "Q2", "Q3", "Q4"):
            quarters.append(
                {
                    "period": f"{yr}-{q}",
                    "pos_fulfilled": 14 + (yr % 3),
                    "otif_pct": 97.4,
                    "historical_dispute_note": (
                        f"{name} ({vendor_id}) completed quarterly SAP vendor scorecard audit "
                        "with e-Invoice NIC IRP registration active and Peenya/MH compliance verified."
                    ),
                }
            )
    return json.dumps({"vendor_id": vendor_id, "history": quarters})


def _make_dock_logs(po_id: str, hub: str) -> str:
    events = [
        f"[{hub}] Gate-In LR#TN-38-AW-90{i} for {po_id}: FASTag verified, security seal intact, weighbridge OK, bay idle {4 + i}m."
        for i in range(1, 16)
    ]
    return "\n".join(events)


ERP_SEED_DATA: dict[str, Any] = {
    "vendors": [
        {
            "vendor_id": "VND-BLR-401",
            "name": "Kaveri Smart Kitchens Pvt. Ltd.",
            "gstin": "29AABCK7740M1Z2",
            "udyam_tier": "Udyam MSE Tier-2 (Bengaluru Cluster)",
            "msmed_45d_applicable": 1,
            "payment_terms_days": 43,
            "risk_flag": "CLEAN",
            "full_audit_trail_json": _make_vendor_audit_trail("VND-BLR-401", "Kaveri Smart Kitchens Pvt. Ltd."),
        },
        {
            "vendor_id": "VND-BOM-512",
            "name": "Sahyadri Powerware India Ltd.",
            "gstin": "27AADCS5512P1Z8",
            "udyam_tier": "Udyam MSE Tier-1 (Pune/Bhiwandi Cluster)",
            "msmed_45d_applicable": 1,
            "payment_terms_days": 43,
            "risk_flag": "WATCH_PRICE_CLAIMS",
            "full_audit_trail_json": _make_vendor_audit_trail("VND-BOM-512", "Sahyadri Powerware India Ltd."),
        },
        {
            "vendor_id": "VND-DEL-309",
            "name": "Aravalli Logistics & Packaging Co.",
            "gstin": "06AABCA3309K1Z4",
            "udyam_tier": "Medium Enterprise (Non-MSE Cap Exempt)",
            "msmed_45d_applicable": 0,
            "payment_terms_days": 60,
            "risk_flag": "HIGH_AUDIT_ALERT",
            "full_audit_trail_json": _make_vendor_audit_trail("VND-DEL-309", "Aravalli Logistics & Packaging Co."),
        },
    ],
    "purchase_orders": [
        {
            "po_id": "PO-NM-BLR-7740",
            "vendor_id": "VND-BLR-401",
            "fc_hub": "FC-BLR-01",
            "incoterms": "DDP Inside FC Dock",
            "approved_freight_cap_inr": 0.0,
            "po_total_taxable_inr": 1840000.0,
            "currency": "INR",
            "created_date": "2026-10-02",
        },
        {
            "po_id": "PO-NM-BOM-5512",
            "vendor_id": "VND-BOM-512",
            "fc_hub": "FC-BOM-02",
            "incoterms": "DDP Inside FC Dock",
            "approved_freight_cap_inr": 0.0,
            "po_total_taxable_inr": 3200000.0,
            "currency": "INR",
            "created_date": "2026-10-05",
        },
        {
            "po_id": "PO-NM-DEL-3309",
            "vendor_id": "VND-DEL-309",
            "fc_hub": "FC-DEL-03",
            "incoterms": "DDP Inside FC Dock",
            "approved_freight_cap_inr": 0.0,
            "po_total_taxable_inr": 2650000.0,
            "currency": "INR",
            "created_date": "2026-10-08",
        },
    ],
    "po_lines": [
        # inv-01 / PO-NM-BLR-7740
        {"po_id": "PO-NM-BLR-7740", "line_no": 1, "sku": "NM-IND-2000W", "description": "NovaCook 2000W Induction Cooktop", "ordered_qty": 400, "po_unit_price_inr": 2200.0, "gst_rate": 0.18},
        {"po_id": "PO-NM-BLR-7740", "line_no": 2, "sku": "NM-MIX-750W", "description": "NovaGrind 750W Silent Mixer", "ordered_qty": 300, "po_unit_price_inr": 2400.0, "gst_rate": 0.18},
        {"po_id": "PO-NM-BLR-7740", "line_no": 3, "sku": "NM-KTL-18L", "description": "NovaBoil 1.8L SS Kettle", "ordered_qty": 300, "po_unit_price_inr": 800.0, "gst_rate": 0.18},
        # inv-02 / PO-NM-BOM-5512
        {"po_id": "PO-NM-BOM-5512", "line_no": 1, "sku": "NM-UPS-1000", "description": "Sahyadri 1000VA Pure-Sine UPS", "ordered_qty": 500, "po_unit_price_inr": 3200.0, "gst_rate": 0.18},
        {"po_id": "PO-NM-BOM-5512", "line_no": 2, "sku": "NM-UPS-2200", "description": "Sahyadri 2200VA Inverter UPS", "ordered_qty": 200, "po_unit_price_inr": 6500.0, "gst_rate": 0.18},
        {"po_id": "PO-NM-BOM-5512", "line_no": 3, "sku": "NM-AVR-500", "description": "Sahyadri Digital Voltage Guard", "ordered_qty": 300, "po_unit_price_inr": 1000.0, "gst_rate": 0.18},
        # inv-03 / PO-NM-DEL-3309
        {"po_id": "PO-NM-DEL-3309", "line_no": 1, "sku": "NM-PKG-TAPE-48", "description": "NovaMart Security Void Tape 48mm", "ordered_qty": 10000, "po_unit_price_inr": 150.0, "gst_rate": 0.18},
        {"po_id": "PO-NM-DEL-3309", "line_no": 2, "sku": "NM-PKG-CORR-XL", "description": "5-Ply Export Master Carton XL", "ordered_qty": 5000, "po_unit_price_inr": 230.0, "gst_rate": 0.18},
    ],
    "goods_receipts": [
        # inv-01 (all accepted clean)
        {"grn_id": "GRN-BLR-901", "po_id": "PO-NM-BLR-7740", "sku": "NM-IND-2000W", "received_qty": 400, "accepted_qty": 400, "doa_rejected_qty": 0, "grn_date": "2026-10-14", "qc_notes": "AQL Level II 1.0 passed zero defects", "raw_wms_scan_dump": _make_wms_scan_dump("PO-NM-BLR-7740", ["NM-IND-2000W", "NM-MIX-750W", "NM-KTL-18L"], "FC-BLR-01")},
        {"grn_id": "GRN-BLR-902", "po_id": "PO-NM-BLR-7740", "sku": "NM-MIX-750W", "received_qty": 300, "accepted_qty": 300, "doa_rejected_qty": 0, "grn_date": "2026-10-14", "qc_notes": "AQL Level II 1.0 passed zero defects", "raw_wms_scan_dump": _make_wms_scan_dump("PO-NM-BLR-7740", ["NM-MIX-750W"], "FC-BLR-01")},
        {"grn_id": "GRN-BLR-903", "po_id": "PO-NM-BLR-7740", "sku": "NM-KTL-18L", "received_qty": 300, "accepted_qty": 300, "doa_rejected_qty": 0, "grn_date": "2026-10-14", "qc_notes": "AQL Level II 1.0 passed zero defects", "raw_wms_scan_dump": _make_wms_scan_dump("PO-NM-BLR-7740", ["NM-KTL-18L"], "FC-BLR-01")},
        # inv-02 (15 DOA rejected on line 1; clean on lines 2 & 3)
        {"grn_id": "GRN-BOM-410", "po_id": "PO-NM-BOM-5512", "sku": "NM-UPS-1000", "received_qty": 500, "accepted_qty": 485, "doa_rejected_qty": 15, "grn_date": "2026-10-16", "qc_notes": "15 units rejected DOA (cracked battery casing); RTV queued", "raw_wms_scan_dump": _make_wms_scan_dump("PO-NM-BOM-5512", ["NM-UPS-1000", "NM-UPS-2200", "NM-AVR-500"], "FC-BOM-02")},
        {"grn_id": "GRN-BOM-411", "po_id": "PO-NM-BOM-5512", "sku": "NM-UPS-2200", "received_qty": 200, "accepted_qty": 200, "doa_rejected_qty": 0, "grn_date": "2026-10-16", "qc_notes": "Passed load test", "raw_wms_scan_dump": _make_wms_scan_dump("PO-NM-BOM-5512", ["NM-UPS-2200"], "FC-BOM-02")},
        {"grn_id": "GRN-BOM-412", "po_id": "PO-NM-BOM-5512", "sku": "NM-AVR-500", "received_qty": 300, "accepted_qty": 300, "doa_rejected_qty": 0, "grn_date": "2026-10-16", "qc_notes": "Passed voltage cutoff test", "raw_wms_scan_dump": _make_wms_scan_dump("PO-NM-BOM-5512", ["NM-AVR-500"], "FC-BOM-02")},
        # inv-03 (phantom unreceived line 2!)
        {"grn_id": "GRN-DEL-201", "po_id": "PO-NM-DEL-3309", "sku": "NM-PKG-TAPE-48", "received_qty": 10000, "accepted_qty": 10000, "doa_rejected_qty": 0, "grn_date": "2026-10-18", "qc_notes": "10,000 rolls accepted at dock", "raw_wms_scan_dump": _make_wms_scan_dump("PO-NM-DEL-3309", ["NM-PKG-TAPE-48"], "FC-DEL-03")},
        {"grn_id": "GRN-DEL-202", "po_id": "PO-NM-DEL-3309", "sku": "NM-PKG-CORR-XL", "received_qty": 0, "accepted_qty": 0, "doa_rejected_qty": 0, "grn_date": "2026-10-18", "qc_notes": "NO SHIPMENT RECEIVED AT DOCK — PHANTOM LINE ON INVOICE", "raw_wms_scan_dump": _make_wms_scan_dump("PO-NM-DEL-3309", ["NM-PKG-CORR-XL"], "FC-DEL-03")},
    ],
    "vendor_invoices": [
        {
            "invoice_id": "INV-KA-2026-9921",
            "po_id": "PO-NM-BLR-7740",
            "vendor_id": "VND-BLR-401",
            "invoice_date": "2026-10-14",
            "irn_hash": "8a91e302f9b11a08e61e2409b4410d20e3aa5518c27248917d110e849921c401",
            "irn_status": "ACTIVE_VERIFIED",
            "gstr2b_status": "PENDING_FILING_MISMATCH",
            "claimed_freight_inr": 0.0,
            "invoice_total_taxable_inr": 1840000.0,
            "invoice_gst_inr": 331200.0,
            "invoice_grand_total_inr": 2171200.0,
            "remittance_memo": (
                "Kaveri Smart Kitchens Diwali Batch #1 into FC-BLR-01. E-Way Bill EWB-291008841221 verified. "
                "Supplier GSTR-1 scheduled before Nov 11 filing cutoff; NIC IRP IRN active. Request timely T+43 principal settlement under MSMED Act Sec 15."
            ),
        },
        {
            "invoice_id": "INV-MH-2026-4418",
            "po_id": "PO-NM-BOM-5512",
            "vendor_id": "VND-BOM-512",
            "invoice_date": "2026-10-16",
            "irn_hash": "4d19f203c4e22b19a72f3518d3320a19f4bb6627d38359028e221f954418a512",
            "irn_status": "ACTIVE_VERIFIED",
            "gstr2b_status": "MATCHED_VERIFIED",
            "claimed_freight_inr": 20000.0,
            "invoice_total_taxable_inr": 3305000.0,
            "invoice_gst_inr": 594900.0,
            "invoice_grand_total_inr": 3899900.0,
            "remittance_memo": (
                "Sahyadri Powerware inverter & stabilizer dispatch to FC-BOM-02 Bhiwandi. "
                "Includes revised copper transformer pricing on NM-UPS-2200 & NM-AVR-500 plus INR 20,000 expedited surface surcharge."
            ),
        },
        {
            "invoice_id": "INV-DL-2026-8803",
            "po_id": "PO-NM-DEL-3309",
            "vendor_id": "VND-DEL-309",
            "invoice_date": "2026-10-18",
            "irn_hash": "9c72a114b8d33e20c83a4627e4431b20e5cc7736e49460139f332a068803b309",
            "irn_status": "CANCELLED_ON_IRP_WITHIN_24H",
            "gstr2b_status": "IRN_CANCELLED_INVALID",
            "claimed_freight_inr": 0.0,
            "invoice_total_taxable_inr": 2650000.0,
            "invoice_gst_inr": 477000.0,
            "invoice_grand_total_inr": 3127000.0,
            "remittance_memo": (
                "Aravalli Packaging consolidated consignment for FC-DEL-03 Gurugram. "
                "Vendor uploaded PDF to portal without disclosing IRP e-Invoice cancellation timestamp."
            ),
        },
    ],
    "invoice_lines": [
        # inv-01
        {"invoice_id": "INV-KA-2026-9921", "line_no": 1, "sku": "NM-IND-2000W", "billed_qty": 400, "billed_unit_price_inr": 2200.0, "billed_line_total_inr": 880000.0, "gst_rate": 0.18},
        {"invoice_id": "INV-KA-2026-9921", "line_no": 2, "sku": "NM-MIX-750W", "billed_qty": 300, "billed_unit_price_inr": 2400.0, "billed_line_total_inr": 720000.0, "gst_rate": 0.18},
        {"invoice_id": "INV-KA-2026-9921", "line_no": 3, "sku": "NM-KTL-18L", "billed_qty": 300, "billed_unit_price_inr": 800.0, "billed_line_total_inr": 240000.0, "gst_rate": 0.18},
        # inv-02
        {"invoice_id": "INV-MH-2026-4418", "line_no": 1, "sku": "NM-UPS-1000", "billed_qty": 500, "billed_unit_price_inr": 3200.0, "billed_line_total_inr": 1600000.0, "gst_rate": 0.18},
        {"invoice_id": "INV-MH-2026-4418", "line_no": 2, "sku": "NM-UPS-2200", "billed_qty": 200, "billed_unit_price_inr": 6850.0, "billed_line_total_inr": 1370000.0, "gst_rate": 0.18},
        {"invoice_id": "INV-MH-2026-4418", "line_no": 3, "sku": "NM-AVR-500", "billed_qty": 300, "billed_unit_price_inr": 1050.0, "billed_line_total_inr": 315000.0, "gst_rate": 0.18},
        # inv-03
        {"invoice_id": "INV-DL-2026-8803", "line_no": 1, "sku": "NM-PKG-TAPE-48", "billed_qty": 10000, "billed_unit_price_inr": 150.0, "billed_line_total_inr": 1500000.0, "gst_rate": 0.18},
        {"invoice_id": "INV-DL-2026-8803", "line_no": 2, "sku": "NM-PKG-CORR-XL", "billed_qty": 5000, "billed_unit_price_inr": 230.0, "billed_line_total_inr": 1150000.0, "gst_rate": 0.18},
    ],
    "contract_amendments": [
        {
            "amendment_id": "AMD-BOM-5512-A",
            "po_id": "PO-NM-BOM-5512",
            "sku": "NM-UPS-2200",
            "approved_unit_price_inr": 6850.0,
            "approved_freight_waiver_inr": 0.0,
            "status": "SIGNED_ACTIVE",
            "approvers": "VP Procurement + Finance Controller (Signed 2026-10-12)",
            "notes": "Approves +5.38% copper winding surcharge strictly on SKU NM-UPS-2200; does NOT cover NM-AVR-500 or freight.",
        }
    ],
    "fc_dock_logs": [
        {"po_id": "PO-NM-BLR-7740", "hub": "FC-BLR-01", "log_blob": _make_dock_logs("PO-NM-BLR-7740", "FC-BLR-01")},
        {"po_id": "PO-NM-BOM-5512", "hub": "FC-BOM-02", "log_blob": _make_dock_logs("PO-NM-BOM-5512", "FC-BOM-02")},
        {"po_id": "PO-NM-DEL-3309", "hub": "FC-DEL-03", "log_blob": _make_dock_logs("PO-NM-DEL-3309", "FC-DEL-03")},
    ],
}


CAT5_PRESETS: list[dict[str, Any]] = [
    {
        "id": "inv-01",
        "invoice_id": "INV-KA-2026-9921",
        "po_id": "PO-NM-BLR-7740",
        "vendor_name": "Kaveri Smart Kitchens Pvt. Ltd.",
        "fc_hub": "FC-BLR-01",
        "title": "Invoice 1: MSMED T+43 Principal Release + 18% GSTR-2B Escrow Split",
        "subtitle": "All 1,000 appliances accepted cleanly at FC-BLR-01, active NIC IRN, but GSTR-2B pending Nov 11 filing — no escalation expected",
        "complexity_tier": "routine_policy_split",
        "invoice_grand_total_inr": 2171200.0,
        "ground_truth": {
            "decision": "APPROVE_WITH_GST_ESCROW",
            "authorized_net_principal_inr": 1840000.0,
            "authorized_gst_payout_inr": 0.0,
            "gst_escrow_holdback_inr": 331200.0,
            "debit_note_deduction_inr": 0.0,
            "required_evidence_tables": [
                "vendor_invoices",
                "purchase_orders",
                "goods_receipts",
                "vendors",
            ],
            "optimal_tool_calls": 3,
            "expected_escalation": False,
        },
    },
    {
        "id": "inv-02",
        "invoice_id": "INV-MH-2026-4418",
        "po_id": "PO-NM-BOM-5512",
        "vendor_name": "Sahyadri Powerware India Ltd.",
        "fc_hub": "FC-BOM-02",
        "title": "Invoice 2: Multi-Factor Dispute (15 DOA Units + Amendment vs Price Hike + Freight)",
        "subtitle": "Mixes 15 DOA rejects (INR 48k), an authorized amendment on NM-UPS-2200, an unauthorized +5% hike on NM-AVR-500 (INR 15k) & disallowed freight (INR 20k) — triggers Haiku -> Sonnet escalation",
        "complexity_tier": "multi_factor_dispute",
        "invoice_grand_total_inr": 3899900.0,
        "ground_truth": {
            "decision": "APPROVE_PARTIAL_DEBIT_NOTE",
            "authorized_net_principal_inr": 3222000.0,
            "authorized_gst_payout_inr": 579960.0,
            "gst_escrow_holdback_inr": 0.0,
            "debit_note_deduction_inr": 83000.0,
            "required_evidence_tables": [
                "vendor_invoices",
                "purchase_orders",
                "goods_receipts",
                "contract_amendments",
            ],
            "optimal_tool_calls": 3,
            "expected_escalation": True,
        },
    },
    {
        "id": "inv-03",
        "invoice_id": "INV-DL-2026-8803",
        "po_id": "PO-NM-DEL-3309",
        "vendor_name": "Aravalli Logistics & Packaging Co.",
        "fc_hub": "FC-DEL-03",
        "title": "Invoice 3: Cancelled IRN + Phantom Line Hard Circuit-Breaker",
        "subtitle": "IRP IRN cancelled within 24h & 5,000 XL cartons (43.4% of invoice) never arrived at FC-DEL-03 — Gate triggers immediate ZERO-payout halt",
        "complexity_tier": "hard_circuit_breaker",
        "invoice_grand_total_inr": 3127000.0,
        "ground_truth": {
            "decision": "BLOCK_EXCEPTION_HOLD",
            "authorized_net_principal_inr": 0.0,
            "authorized_gst_payout_inr": 0.0,
            "gst_escrow_holdback_inr": 0.0,
            "debit_note_deduction_inr": 0.0,
            "required_evidence_tables": [
                "vendor_invoices",
                "purchase_orders",
                "goods_receipts",
            ],
            "optimal_tool_calls": 3,
            "expected_escalation": False,
        },
    },
]
