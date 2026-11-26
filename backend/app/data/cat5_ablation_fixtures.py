"""Category 5 ablation fixtures: nine extra invoices (ERP rows + presets + hand-derived ground truth).

Nothing here changes `app/data/cat5_fixtures.py`, `ERP_SEED_DATA`, `CAT5_PRESETS` or
`create_seeded_erp_connection()`. The extra rows use new vendor, PO, invoice and GRN ids only; the
ablation harness inserts them into a connection that was first seeded by the app's own function.

Every new invoice carries a worked derivation (inputs -> each rupee field -> decision -> routing)
written by hand from SOP-AP-3WAY-2026.v4 (`AP_POLICY_MANUAL_MARKDOWN`). The ground truth is that hand
derivation, not the deterministic gate's output. `tests/test_cat5_ablation.py` compares the two:
invoices where they agree form the default matrix; the others are listed in
`CAT5_ABLATION_EXCLUDED_PENDING_REVIEW` with the manual text, the derivation and the gate output.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from app.data.cat5_fixtures import (
    CAT5_PRESETS,
    _make_dock_logs,
    _make_vendor_audit_trail,
    _make_wms_scan_dump,
)

CAT5_ABLATION_FIXTURE_VERSION = "cat5-ablation-fixtures-2026-11-26.v1"

# Coarse tier used for the per-arm x tier tables.
ANALYSIS_TIERS: tuple[str, ...] = ("routine", "dispute", "hard_stop")


def _irn(gstin: str, invoice_id: str) -> str:
    """Deterministic 64-hex-char IRN stand-in (the app's seed uses literal hashes of the same shape)."""
    return hashlib.sha256(f"NIC-IRP|{gstin}|{invoice_id}".encode()).hexdigest()


# --------------------------------------------------------------------------------------------------
# Compact invoice specs. Rows below are generated from these mechanically (qty x price, sums); the
# rupee ground truth further down is written out by hand and is NOT computed from these specs.
# --------------------------------------------------------------------------------------------------

_SPECS: list[dict[str, Any]] = [
    {
        "id": "inv-04",
        "invoice_id": "INV-TS-2026-1184",
        "po_id": "PO-NM-HYD-1184",
        "hub": "FC-HYD-01",
        "vendor": {
            "vendor_id": "VND-HYD-118",
            "name": "Deccan Brightline Electricals Pvt. Ltd.",
            "gstin": "36AAECD1184L1Z5",
            "udyam_tier": "Udyam MSE Tier-2 (Hyderabad Cluster)",
            "msmed_45d_applicable": 1,
            "payment_terms_days": 43,
            "risk_flag": "CLEAN",
        },
        "incoterms": "DDP Inside FC Dock",
        "freight_cap": 0.0,
        "claimed_freight": 0.0,
        "po_date": "2026-10-03",
        "invoice_date": "2026-10-15",
        "irn_status": "ACTIVE_VERIFIED",
        "gstr2b_status": "MATCHED_VERIFIED",
        "memo": (
            "Deccan Brightline festive lighting replenishment into FC-HYD-01. E-Way Bill EWB-361009184402 "
            "verified; GSTR-1 filed 11-Nov. Standard T+43 settlement requested."
        ),
        "grn_prefix": "GRN-HYD-61",
        "grn_date": "2026-10-15",
        "lines": [
            {"sku": "NM-FAN-1200-BLDC", "desc": "NovaBreeze 1200mm BLDC Ceiling Fan", "ordered": 600, "received": 600, "accepted": 600, "doa": 0, "po_price": 2450.0, "billed_qty": 600, "billed_price": 2450.0, "qc": "AQL Level II 1.0 passed zero defects"},
            {"sku": "NM-LED-BATTEN-20W", "desc": "NovaLume 20W LED Batten 4ft", "ordered": 2000, "received": 2000, "accepted": 2000, "doa": 0, "po_price": 185.0, "billed_qty": 2000, "billed_price": 185.0, "qc": "AQL Level II 1.0 passed zero defects"},
            {"sku": "NM-LED-BULB-9W-PK4", "desc": "NovaLume 9W LED Bulb Pack of 4", "ordered": 1500, "received": 1500, "accepted": 1500, "doa": 0, "po_price": 210.0, "billed_qty": 1500, "billed_price": 210.0, "qc": "AQL Level II 1.0 passed zero defects"},
        ],
        "gst_rate": 0.18,
        "amendments": [],
    },
    {
        "id": "inv-05",
        "invoice_id": "INV-KA-2026-2271",
        "po_id": "PO-NM-BLR-2271",
        "hub": "FC-BLR-01",
        "vendor": {
            "vendor_id": "VND-BLR-227",
            "name": "Nandi Power Tools & Abrasives Pvt. Ltd.",
            "gstin": "29AAFCN2271Q1Z9",
            "udyam_tier": "Udyam MSE Tier-1 (Peenya Cluster)",
            "msmed_45d_applicable": 1,
            "payment_terms_days": 43,
            "risk_flag": "CLEAN",
        },
        "incoterms": "DDP Inside FC Dock",
        "freight_cap": 0.0,
        "claimed_freight": 0.0,
        "po_date": "2026-10-04",
        "invoice_date": "2026-10-17",
        "irn_status": "ACTIVE_VERIFIED",
        "gstr2b_status": "MATCHED_VERIFIED",
        "memo": (
            "Nandi Power Tools DIY season stock into FC-BLR-01. Invoice raised on full dispatch quantity per "
            "packing list PL-2271-A; E-Way Bill EWB-291017227105."
        ),
        "grn_prefix": "GRN-BLR-27",
        "grn_date": "2026-10-17",
        "lines": [
            {"sku": "NM-DRL-13MM", "desc": "NovaForce 13mm Impact Drill 650W", "ordered": 800, "received": 800, "accepted": 776, "doa": 24, "po_price": 1650.0, "billed_qty": 800, "billed_price": 1650.0, "qc": "24 units rejected DOA (seized chuck / failed run test); RTV queued"},
            {"sku": "NM-AGR-100", "desc": "NovaForce 100mm Angle Grinder 850W", "ordered": 1000, "received": 1000, "accepted": 1000, "doa": 0, "po_price": 1180.0, "billed_qty": 1000, "billed_price": 1180.0, "qc": "Passed run and guard-fit test"},
        ],
        "gst_rate": 0.18,
        "amendments": [],
    },
    {
        "id": "inv-06",
        "invoice_id": "INV-DL-2026-4157",
        "po_id": "PO-NM-DEL-4157",
        "hub": "FC-DEL-03",
        "vendor": {
            "vendor_id": "VND-DEL-415",
            "name": "Indraprastha Cables & Wires Ltd.",
            "gstin": "07AABCI4157R1Z3",
            "udyam_tier": "Udyam MSE Tier-2 (Narela Cluster)",
            "msmed_45d_applicable": 1,
            "payment_terms_days": 43,
            "risk_flag": "CLEAN",
        },
        "incoterms": "DDP Inside FC Dock",
        "freight_cap": 0.0,
        "claimed_freight": 0.0,
        "po_date": "2026-10-06",
        "invoice_date": "2026-10-19",
        "irn_status": "ACTIVE_VERIFIED",
        "gstr2b_status": "MATCHED_VERIFIED",
        "memo": (
            "Indraprastha Cables house-wire coils into FC-DEL-03. 1.5 sq mm coils billed with +1.28% LME copper "
            "index surcharge per our October price circular; 2.5 sq mm at PO rate."
        ),
        "grn_prefix": "GRN-DEL-41",
        "grn_date": "2026-10-19",
        "lines": [
            {"sku": "NM-CBL-1.5SQ-90M", "desc": "FR-LSH 1.5 sq mm House Wire 90m Coil", "ordered": 1200, "received": 1200, "accepted": 1200, "doa": 0, "po_price": 1480.0, "billed_qty": 1200, "billed_price": 1499.0, "qc": "Conductor resistance test passed"},
            {"sku": "NM-CBL-2.5SQ-90M", "desc": "FR-LSH 2.5 sq mm House Wire 90m Coil", "ordered": 800, "received": 800, "accepted": 800, "doa": 0, "po_price": 2350.0, "billed_qty": 800, "billed_price": 2350.0, "qc": "Conductor resistance test passed"},
        ],
        "gst_rate": 0.18,
        "amendments": [],
    },
    {
        "id": "inv-07",
        "invoice_id": "INV-MH-2026-7331",
        "po_id": "PO-NM-BOM-7331",
        "hub": "FC-BOM-02",
        "vendor": {
            "vendor_id": "VND-BOM-733",
            "name": "Konkan Polymers & Moulders Pvt. Ltd.",
            "gstin": "27AAGCK7331H1Z6",
            "udyam_tier": "Udyam MSE Tier-2 (Vasai-Bhiwandi Cluster)",
            "msmed_45d_applicable": 1,
            "payment_terms_days": 43,
            "risk_flag": "WATCH_PRICE_CLAIMS",
        },
        "incoterms": "DDP Inside FC Dock",
        "freight_cap": 0.0,
        "claimed_freight": 0.0,
        "po_date": "2026-10-05",
        "invoice_date": "2026-10-18",
        "irn_status": "ACTIVE_VERIFIED",
        "gstr2b_status": "MATCHED_VERIFIED",
        "memo": (
            "Konkan Polymers moulded furniture into FC-BOM-02. Stackable chairs billed at revised resin-linked "
            "list price effective 01-Oct; tables and bins at PO rate."
        ),
        "grn_prefix": "GRN-BOM-73",
        "grn_date": "2026-10-18",
        "lines": [
            {"sku": "NM-CHR-STK-PP", "desc": "NovaHome Stackable PP Chair", "ordered": 2000, "received": 2000, "accepted": 2000, "doa": 0, "po_price": 640.0, "billed_qty": 2000, "billed_price": 672.0, "qc": "Load test 150 kg passed"},
            {"sku": "NM-TBL-FLD-4S", "desc": "NovaHome 4-Seater Folding Table", "ordered": 300, "received": 300, "accepted": 300, "doa": 0, "po_price": 2900.0, "billed_qty": 300, "billed_price": 2900.0, "qc": "Hinge cycle test passed"},
            {"sku": "NM-BIN-50L", "desc": "NovaHome 50L Pedal Bin", "ordered": 1000, "received": 1000, "accepted": 1000, "doa": 0, "po_price": 410.0, "billed_qty": 1000, "billed_price": 410.0, "qc": "Visual AQL passed"},
        ],
        "gst_rate": 0.18,
        "amendments": [],
    },
    {
        "id": "inv-08",
        "invoice_id": "INV-TS-2026-2645",
        "po_id": "PO-NM-HYD-2645",
        "hub": "FC-HYD-01",
        "vendor": {
            "vendor_id": "VND-HYD-264",
            "name": "Charminar Aquatech Appliances Pvt. Ltd.",
            "gstin": "36AAHCC2645E1Z1",
            "udyam_tier": "Udyam MSE Tier-1 (Hyderabad Cluster)",
            "msmed_45d_applicable": 1,
            "payment_terms_days": 43,
            "risk_flag": "CLEAN",
        },
        "incoterms": "DDP Inside FC Dock",
        "freight_cap": 0.0,
        "claimed_freight": 0.0,
        "po_date": "2026-10-02",
        "invoice_date": "2026-10-16",
        "irn_status": "ACTIVE_VERIFIED",
        "gstr2b_status": "MATCHED_VERIFIED",
        "memo": (
            "Charminar Aquatech RO purifiers into FC-HYD-01 at amended membrane-linked rate per AMD-HYD-2645-A; "
            "filter kits at PO rate."
        ),
        "grn_prefix": "GRN-HYD-26",
        "grn_date": "2026-10-16",
        "lines": [
            {"sku": "NM-WP-RO-8L", "desc": "NovaPure 8L RO+UV Water Purifier", "ordered": 350, "received": 350, "accepted": 350, "doa": 0, "po_price": 7800.0, "billed_qty": 350, "billed_price": 8190.0, "qc": "TDS rejection test passed"},
            {"sku": "NM-WP-FLT-KIT", "desc": "NovaPure Annual Filter Kit", "ordered": 700, "received": 700, "accepted": 700, "doa": 0, "po_price": 650.0, "billed_qty": 700, "billed_price": 650.0, "qc": "Seal integrity passed"},
        ],
        "gst_rate": 0.18,
        "amendments": [
            {
                "amendment_id": "AMD-HYD-2645-A",
                "sku": "NM-WP-RO-8L",
                "approved_unit_price_inr": 8190.0,
                "approved_freight_waiver_inr": 0.0,
                "status": "SIGNED_ACTIVE",
                "approvers": "Category Finance Director + VP Procurement (dual-signed 2026-10-07)",
                "notes": "Approves +5.0% RO membrane cost pass-through strictly on NM-WP-RO-8L; filter kits stay at PO rate.",
            }
        ],
    },
    {
        "id": "inv-09",
        "invoice_id": "INV-HR-2026-5826",
        "po_id": "PO-NM-DEL-5826",
        "hub": "FC-DEL-03",
        "vendor": {
            "vendor_id": "VND-DEL-582",
            "name": "Sohna Cool Appliances Pvt. Ltd.",
            "gstin": "06AAJCS5826B1Z7",
            "udyam_tier": "Udyam MSE Tier-1 (Manesar Cluster)",
            "msmed_45d_applicable": 1,
            "payment_terms_days": 43,
            "risk_flag": "CLEAN",
        },
        "incoterms": "FCA Vendor Works (Freight Capped)",
        "freight_cap": 18000.0,
        "claimed_freight": 27500.0,
        "po_date": "2026-10-07",
        "invoice_date": "2026-10-20",
        "irn_status": "ACTIVE_VERIFIED",
        "gstr2b_status": "MATCHED_VERIFIED",
        "memo": (
            "Sohna Cool summer pre-season coolers into FC-DEL-03. Freight billed at actuals INR 27,500 "
            "(two additional 32-ft trucks for bulky 55L units)."
        ),
        "grn_prefix": "GRN-DEL-58",
        "grn_date": "2026-10-20",
        "lines": [
            {"sku": "NM-COOLER-55L", "desc": "NovaChill 55L Desert Air Cooler", "ordered": 500, "received": 500, "accepted": 500, "doa": 0, "po_price": 6200.0, "billed_qty": 500, "billed_price": 6200.0, "qc": "Pump and fan run test passed"},
            {"sku": "NM-COOLER-20L", "desc": "NovaChill 20L Personal Air Cooler", "ordered": 400, "received": 400, "accepted": 400, "doa": 0, "po_price": 3450.0, "billed_qty": 400, "billed_price": 3450.0, "qc": "Pump and fan run test passed"},
        ],
        "gst_rate": 0.18,
        "amendments": [],
    },
    {
        "id": "inv-10",
        "invoice_id": "INV-MH-2026-8463",
        "po_id": "PO-NM-BOM-8463",
        "hub": "FC-BOM-02",
        "vendor": {
            "vendor_id": "VND-BOM-846",
            "name": "Thane Gourmet Foods Ltd.",
            "gstin": "27AAKCT8463F1Z2",
            "udyam_tier": "Large Enterprise (Non-MSE; MSMED Sec 15 not applicable)",
            "msmed_45d_applicable": 0,
            "payment_terms_days": 60,
            "risk_flag": "CLEAN",
        },
        "incoterms": "DDP Inside FC Dock",
        "freight_cap": 0.0,
        "claimed_freight": 0.0,
        "po_date": "2026-10-08",
        "invoice_date": "2026-10-21",
        "irn_status": "ACTIVE_VERIFIED",
        "gstr2b_status": "PENDING_FILING_MISMATCH",
        "memo": (
            "Thane Gourmet packaged staples into FC-BOM-02 (5% GST HSN 0405/1902/2106). October GSTR-1 filed late; "
            "please release GST portion together with principal."
        ),
        "grn_prefix": "GRN-BOM-84",
        "grn_date": "2026-10-21",
        "lines": [
            {"sku": "NM-GHEE-1L", "desc": "NovaKitchen Cow Ghee 1L Pouch", "ordered": 3000, "received": 3000, "accepted": 3000, "doa": 0, "po_price": 610.0, "billed_qty": 3000, "billed_price": 610.0, "qc": "FSSAI batch and seal check passed"},
            {"sku": "NM-PASTA-500G", "desc": "NovaKitchen Durum Penne 500g", "ordered": 8000, "received": 8000, "accepted": 8000, "doa": 0, "po_price": 95.0, "billed_qty": 8000, "billed_price": 95.0, "qc": "FSSAI batch and seal check passed"},
            {"sku": "NM-NMK-400G", "desc": "NovaKitchen Bhujia Namkeen 400g", "ordered": 6000, "received": 6000, "accepted": 6000, "doa": 0, "po_price": 88.0, "billed_qty": 6000, "billed_price": 88.0, "qc": "FSSAI batch and seal check passed"},
        ],
        "gst_rate": 0.05,
        "amendments": [],
    },
    {
        "id": "inv-11",
        "invoice_id": "INV-KA-2026-5193",
        "po_id": "PO-NM-BLR-5193",
        "hub": "FC-BLR-01",
        "vendor": {
            "vendor_id": "VND-BLR-519",
            "name": "Electronic City Mobile Accessories Pvt. Ltd.",
            "gstin": "29AALCE5193D1Z8",
            "udyam_tier": "Udyam MSE Tier-2 (Electronic City Cluster)",
            "msmed_45d_applicable": 1,
            "payment_terms_days": 43,
            "risk_flag": "CLEAN",
        },
        "incoterms": "DDP Inside FC Dock",
        "freight_cap": 0.0,
        "claimed_freight": 0.0,
        "po_date": "2026-10-09",
        "invoice_date": "2026-10-22",
        "irn_status": "ACTIVE_VERIFIED",
        "gstr2b_status": "MATCHED_VERIFIED",
        "memo": (
            "Electronic City Mobile Accessories consignment for FC-BLR-01 dispatched on two LRs; GaN chargers on "
            "second LR KA-51-LR-77213. Request settlement of full invoice on T+43."
        ),
        "grn_prefix": "GRN-BLR-51",
        "grn_date": "2026-10-22",
        "lines": [
            {"sku": "NM-PB-20K", "desc": "NovaCharge 20000mAh Power Bank", "ordered": 1500, "received": 1500, "accepted": 1500, "doa": 0, "po_price": 1150.0, "billed_qty": 1500, "billed_price": 1150.0, "qc": "BIS label and capacity sample passed"},
            {"sku": "NM-CHG-65W-GAN", "desc": "NovaCharge 65W GaN USB-C Charger", "ordered": 400, "received": 0, "accepted": 0, "doa": 0, "po_price": 1380.0, "billed_qty": 400, "billed_price": 1380.0, "qc": "NO SHIPMENT RECEIVED AT DOCK — ASN listed 400 units; second LR never presented at gate"},
            {"sku": "NM-CBL-USBC-1M", "desc": "NovaCharge USB-C Braided Cable 1m", "ordered": 3000, "received": 3000, "accepted": 3000, "doa": 0, "po_price": 140.0, "billed_qty": 3000, "billed_price": 140.0, "qc": "Continuity sample passed"},
        ],
        "gst_rate": 0.18,
        "amendments": [],
    },
    {
        "id": "inv-12",
        "invoice_id": "INV-TS-2026-3774",
        "po_id": "PO-NM-HYD-3774",
        "hub": "FC-HYD-01",
        "vendor": {
            "vendor_id": "VND-HYD-377",
            "name": "Kakatiya Kitchen Electricals Pvt. Ltd.",
            "gstin": "36AAMCK3774G1Z4",
            "udyam_tier": "Udyam MSE Tier-1 (Hyderabad Cluster)",
            "msmed_45d_applicable": 1,
            "payment_terms_days": 43,
            "risk_flag": "WATCH_PRICE_CLAIMS",
        },
        "incoterms": "FCA Vendor Works (Freight Capped)",
        "freight_cap": 12000.0,
        "claimed_freight": 20000.0,
        "po_date": "2026-10-06",
        "invoice_date": "2026-10-23",
        "irn_status": "ACTIVE_VERIFIED",
        "gstr2b_status": "PENDING_FILING_MISMATCH",
        "memo": (
            "Kakatiya Kitchen Electricals festive cooking appliances into FC-HYD-01. Microwaves invoiced on PO "
            "quantity; OTG and induction at revised component-linked rates; freight at actuals INR 20,000. "
            "GSTR-1 upload scheduled after month close."
        ),
        "grn_prefix": "GRN-HYD-37",
        "grn_date": "2026-10-23",
        "lines": [
            {"sku": "NM-MWO-25L", "desc": "NovaCook 25L Convection Microwave", "ordered": 400, "received": 380, "accepted": 380, "doa": 0, "po_price": 6900.0, "billed_qty": 400, "billed_price": 6900.0, "qc": "Short-shipped: 380 of 400 units received (ASN shortfall 20); all received units passed"},
            {"sku": "NM-OTG-30L", "desc": "NovaCook 30L Oven Toaster Grill", "ordered": 250, "received": 250, "accepted": 250, "doa": 0, "po_price": 4200.0, "billed_qty": 250, "billed_price": 4326.0, "qc": "Thermostat calibration passed"},
            {"sku": "NM-IND-2100W", "desc": "NovaCook 2100W Induction Cooktop", "ordered": 500, "received": 500, "accepted": 488, "doa": 12, "po_price": 2300.0, "billed_qty": 500, "billed_price": 2415.0, "qc": "12 units rejected DOA (cracked glass top); RTV queued"},
        ],
        "gst_rate": 0.18,
        "amendments": [
            {
                "amendment_id": "AMD-HYD-3774-A",
                "sku": "NM-IND-2100W",
                "approved_unit_price_inr": 2415.0,
                "approved_freight_waiver_inr": 0.0,
                "status": "SIGNED_ACTIVE",
                "approvers": "Category Finance Director + VP Procurement (dual-signed 2026-10-10)",
                "notes": "Approves +5.0% IGBT module surcharge on NM-IND-2100W only; no freight waiver.",
            },
            {
                "amendment_id": "AMD-HYD-3774-B",
                "sku": "NM-OTG-30L",
                "approved_unit_price_inr": 4326.0,
                "approved_freight_waiver_inr": 0.0,
                "status": "DRAFT_PENDING_SIGNATURE",
                "approvers": "Raised by Category Manager; Category Finance Director signature pending",
                "notes": "Draft +3.0% heating-element surcharge on NM-OTG-30L — not yet approved.",
            },
        ],
    },
]


def _rows_for(spec: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    v = spec["vendor"]
    po_id = spec["po_id"]
    hub = spec["hub"]
    inv_id = spec["invoice_id"]
    rate = float(spec["gst_rate"])
    po_lines = [
        {
            "po_id": po_id,
            "line_no": i,
            "sku": ln["sku"],
            "description": ln["desc"],
            "ordered_qty": ln["ordered"],
            "po_unit_price_inr": ln["po_price"],
            "gst_rate": rate,
        }
        for i, ln in enumerate(spec["lines"], start=1)
    ]
    grns = [
        {
            "grn_id": f"{spec['grn_prefix']}{i}",
            "po_id": po_id,
            "sku": ln["sku"],
            "received_qty": ln["received"],
            "accepted_qty": ln["accepted"],
            "doa_rejected_qty": ln["doa"],
            "grn_date": spec["grn_date"],
            "qc_notes": ln["qc"],
            "raw_wms_scan_dump": _make_wms_scan_dump(po_id, [ln["sku"]], hub),
        }
        for i, ln in enumerate(spec["lines"], start=1)
    ]
    inv_lines = [
        {
            "invoice_id": inv_id,
            "line_no": i,
            "sku": ln["sku"],
            "billed_qty": ln["billed_qty"],
            "billed_unit_price_inr": ln["billed_price"],
            "billed_line_total_inr": round(ln["billed_qty"] * ln["billed_price"], 2),
            "gst_rate": rate,
        }
        for i, ln in enumerate(spec["lines"], start=1)
    ]
    taxable = round(sum(r["billed_line_total_inr"] for r in inv_lines) + float(spec["claimed_freight"]), 2)
    gst = round(taxable * rate, 2)
    return {
        "vendors": [{**v, "full_audit_trail_json": _make_vendor_audit_trail(v["vendor_id"], v["name"])}],
        "purchase_orders": [
            {
                "po_id": po_id,
                "vendor_id": v["vendor_id"],
                "fc_hub": hub,
                "incoterms": spec["incoterms"],
                "approved_freight_cap_inr": float(spec["freight_cap"]),
                "po_total_taxable_inr": round(sum(ln["ordered"] * ln["po_price"] for ln in spec["lines"]), 2),
                "currency": "INR",
                "created_date": spec["po_date"],
            }
        ],
        "po_lines": po_lines,
        "goods_receipts": grns,
        "vendor_invoices": [
            {
                "invoice_id": inv_id,
                "po_id": po_id,
                "vendor_id": v["vendor_id"],
                "invoice_date": spec["invoice_date"],
                "irn_hash": _irn(v["gstin"], inv_id),
                "irn_status": spec["irn_status"],
                "gstr2b_status": spec["gstr2b_status"],
                "claimed_freight_inr": float(spec["claimed_freight"]),
                "invoice_total_taxable_inr": taxable,
                "invoice_gst_inr": gst,
                "invoice_grand_total_inr": round(taxable + gst, 2),
                "remittance_memo": spec["memo"],
            }
        ],
        "invoice_lines": inv_lines,
        "contract_amendments": [{"po_id": po_id, **a} for a in spec["amendments"]],
        "fc_dock_logs": [{"po_id": po_id, "hub": hub, "log_blob": _make_dock_logs(po_id, hub)}],
    }


ERP_TABLE_ORDER: tuple[str, ...] = (
    "vendors",
    "purchase_orders",
    "po_lines",
    "goods_receipts",
    "vendor_invoices",
    "invoice_lines",
    "contract_amendments",
    "fc_dock_logs",
)

ROWS_BY_INVOICE: dict[str, dict[str, list[dict[str, Any]]]] = {s["id"]: _rows_for(s) for s in _SPECS}

CAT5_ABLATION_ERP_ROWS: dict[str, list[dict[str, Any]]] = {
    table: [row for s in _SPECS for row in ROWS_BY_INVOICE[s["id"]][table]] for table in ERP_TABLE_ORDER
}


# --------------------------------------------------------------------------------------------------
# Hand derivations and ground truth (SOP-AP-3WAY-2026.v4). All figures INR. Written by hand.
# --------------------------------------------------------------------------------------------------

_HAND: dict[str, dict[str, Any]] = {
    "inv-04": {
        "scenario": "Clean full match",
        "analysis_tier": "routine",
        "complexity_tier": "routine_clean_match",
        "title": "Invoice 4: Clean Three-Way Match, GSTR-2B Verified",
        "subtitle": "3 lighting/fan lines at PO rate, 100% accepted at FC-HYD-01, IRN active, GSTR-2B matched",
        "required_evidence_tables": ["vendor_invoices", "purchase_orders", "goods_receipts"],
        "ground_truth": {
            "decision": "APPROVE_CLEAN",
            "authorized_net_principal_inr": 2155000.0,
            "authorized_gst_payout_inr": 387900.0,
            "gst_escrow_holdback_inr": 0.0,
            "debit_note_deduction_inr": 0.0,
            "expected_escalation": False,
        },
        "derivation": {
            "inputs": [
                "IRN ACTIVE_VERIFIED; GSTR-2B MATCHED_VERIFIED; vendor CLEAN; PO DDP, freight cap 0; claimed freight 0.",
                "Invoice taxable 2,155,000.00; invoice GST 387,900.00; grand total 2,542,900.00; GST rate 18% on every line.",
            ],
            "module4_check": "No IRN cancellation; no line with accepted_qty = 0. No hard block.",
            "lines": [
                "L1 NM-FAN-1200-BLDC: payable = MIN(600 ordered, 600 accepted) = 600; billed 2,450 = PO 2,450 -> rate 2,450; authorised 600 x 2,450 = 1,470,000; billed 1,470,000; deduction 0.",
                "L2 NM-LED-BATTEN-20W: payable = MIN(2,000, 2,000) = 2,000; rate 185 (= PO); authorised 370,000; deduction 0.",
                "L3 NM-LED-BULB-9W-PK4: payable = MIN(1,500, 1,500) = 1,500; rate 210 (= PO); authorised 315,000; deduction 0.",
            ],
            "freight": "MIN(claimed 0, cap 0) = 0 allowed; excess 0.",
            "authorized_net_principal_inr": "1,470,000 + 370,000 + 315,000 + 0 = 2,155,000.00",
            "debit_note_deduction_inr": "2,155,000.00 - 2,155,000.00 = 0.00",
            "gst": "Case A (MATCHED_VERIFIED): payout = ROUND(2,155,000 x 0.18, 2) = 387,900.00; escrow 0.00",
            "decision": "Case A and debit note 0 -> APPROVE_CLEAN",
            "escalation": "Gate rule (discrepancies >= 2 or debit > 0): 0 discrepancies, debit 0 -> no escalation.",
            "routing": "GL 210100 principal 2,155,000.00 (T+43); GL 142810 input GST 387,900.00; no exception queue.",
        },
    },
    "inv-05": {
        "scenario": "DOA rejects only",
        "analysis_tier": "dispute",
        "complexity_tier": "single_factor_dispute",
        "title": "Invoice 5: DOA Rejection Debit Note Only",
        "subtitle": "24 impact drills rejected DOA at FC-BLR-01 but billed in full; everything else clean",
        "required_evidence_tables": ["vendor_invoices", "purchase_orders", "goods_receipts"],
        "ground_truth": {
            "decision": "APPROVE_PARTIAL_DEBIT_NOTE",
            "authorized_net_principal_inr": 2460400.0,
            "authorized_gst_payout_inr": 442872.0,
            "gst_escrow_holdback_inr": 0.0,
            "debit_note_deduction_inr": 39600.0,
            "expected_escalation": True,
        },
        "derivation": {
            "inputs": [
                "IRN ACTIVE_VERIFIED; GSTR-2B MATCHED_VERIFIED; vendor CLEAN; PO DDP, freight cap 0; claimed freight 0.",
                "Invoice taxable 2,500,000.00; invoice GST 450,000.00; grand total 2,950,000.00; GST 18%.",
            ],
            "module4_check": "No IRN cancellation; no line with accepted_qty = 0. No hard block.",
            "lines": [
                "L1 NM-DRL-13MM: received 800, accepted 776, DOA 24; payable = MIN(800, 776) = 776; billed 1,650 = PO -> rate 1,650; authorised 776 x 1,650 = 1,280,400; billed 800 x 1,650 = 1,320,000; deduction 39,600 (24 x 1,650).",
                "L2 NM-AGR-100: payable = MIN(1,000, 1,000) = 1,000; rate 1,180 (= PO); authorised 1,180,000; deduction 0.",
            ],
            "freight": "MIN(0, 0) = 0; excess 0.",
            "authorized_net_principal_inr": "1,280,400 + 1,180,000 + 0 = 2,460,400.00",
            "debit_note_deduction_inr": "2,500,000.00 - 2,460,400.00 = 39,600.00",
            "gst": "Case A: payout = ROUND(2,460,400 x 0.18, 2) = 442,872.00; escrow 0.00",
            "decision": "Case A with debit note > 0 -> APPROVE_PARTIAL_DEBIT_NOTE",
            "escalation": "Gate rule: 1 discrepancy (DOA) but debit 39,600 > 0 -> escalation required.",
            "routing": "GL 210100 principal 2,460,400.00; GL 142810 GST 442,872.00; GL 520900 debit note 39,600.00; queue AP-DEBIT-RECON (SLA 12h).",
        },
    },
    "inv-06": {
        "scenario": "Price variance inside the 1.5% band (standard DDP INR PO, no amendment)",
        "analysis_tier": "routine",
        "complexity_tier": "routine_price_tolerance",
        "title": "Invoice 6: +1.28% Copper Surcharge Inside the 1.5% Band",
        "subtitle": "1.5 sq mm coils billed at 1,499 vs PO 1,480 (+1.28%) on a standard DDP INR PO with no amendment",
        "required_evidence_tables": ["vendor_invoices", "purchase_orders", "goods_receipts", "contract_amendments"],
        "ground_truth": {
            "decision": "APPROVE_PARTIAL_DEBIT_NOTE",
            "authorized_net_principal_inr": 3656000.0,
            "authorized_gst_payout_inr": 658080.0,
            "gst_escrow_holdback_inr": 0.0,
            "debit_note_deduction_inr": 22800.0,
            "expected_escalation": True,
        },
        "derivation": {
            "inputs": [
                "IRN ACTIVE_VERIFIED; GSTR-2B MATCHED_VERIFIED; PO incoterms 'DDP Inside FC Dock', currency 'INR' (no index-linked float note); no contract_amendments rows for the PO.",
                "Invoice taxable 3,678,800.00; invoice GST 662,184.00; grand total 4,340,984.00; GST 18%.",
            ],
            "module4_check": "No IRN cancellation; no line with accepted_qty = 0. No hard block.",
            "lines": [
                "L1 NM-CBL-1.5SQ-90M: payable = MIN(1,200, 1,200) = 1,200; billed 1,499 vs PO 1,480: 1,480 < 1,499 <= 1,480 x 1.015 = 1,502.20 (+1.28%). Manual 2.1 bullet 2: the band 'MAY pass ONLY when PO currency notes specify index-linked float; otherwise standard landed DDP catalog POs default to PO unit rate unless amended'. PO is standard DDP INR, no amendment -> rate 1,480; authorised 1,200 x 1,480 = 1,776,000; billed 1,798,800; deduction 22,800.",
                "L2 NM-CBL-2.5SQ-90M: payable 800; rate 2,350 (= PO); authorised 1,880,000; deduction 0.",
            ],
            "freight": "MIN(0, 0) = 0; excess 0.",
            "authorized_net_principal_inr": "1,776,000 + 1,880,000 + 0 = 3,656,000.00",
            "debit_note_deduction_inr": "3,678,800.00 - 3,656,000.00 = 22,800.00",
            "gst": "Case A: payout = ROUND(3,656,000 x 0.18, 2) = 658,080.00; escrow 0.00",
            "decision": "Case A with debit note > 0 -> APPROVE_PARTIAL_DEBIT_NOTE",
            "escalation": "Gate rule applied to these figures: debit 22,800 > 0 -> escalation required.",
            "routing": "GL 210100 principal 3,656,000.00; GL 142810 GST 658,080.00; GL 520900 debit note 22,800.00; queue AP-DEBIT-RECON.",
        },
    },
    "inv-07": {
        "scenario": "Price variance outside tolerance, no amendment",
        "analysis_tier": "dispute",
        "complexity_tier": "single_factor_dispute",
        "title": "Invoice 7: Unauthorised +5% Price Hike Capped to PO",
        "subtitle": "Stackable chairs billed 672 vs PO 640 (+5.0%) with no contract amendment at all",
        "required_evidence_tables": ["vendor_invoices", "purchase_orders", "goods_receipts", "contract_amendments"],
        "ground_truth": {
            "decision": "APPROVE_PARTIAL_DEBIT_NOTE",
            "authorized_net_principal_inr": 2560000.0,
            "authorized_gst_payout_inr": 460800.0,
            "gst_escrow_holdback_inr": 0.0,
            "debit_note_deduction_inr": 64000.0,
            "expected_escalation": True,
        },
        "derivation": {
            "inputs": [
                "IRN ACTIVE_VERIFIED; GSTR-2B MATCHED_VERIFIED; vendor WATCH_PRICE_CLAIMS (not a payment freeze); PO DDP, cap 0; claimed freight 0; no contract_amendments rows.",
                "Invoice taxable 2,624,000.00; invoice GST 472,320.00; grand total 3,096,320.00; GST 18%.",
            ],
            "module4_check": "No IRN cancellation; no line with accepted_qty = 0; risk flag is not PAYMENT_FREEZE. No hard block.",
            "lines": [
                "L1 NM-CHR-STK-PP: payable = MIN(2,000, 2,000) = 2,000; billed 672 > 640 x 1.015 = 649.60 and no SIGNED_ACTIVE amendment -> rate 640 (2.2); authorised 2,000 x 640 = 1,280,000; billed 1,344,000; deduction 64,000.",
                "L2 NM-TBL-FLD-4S: payable 300; rate 2,900 (= PO); authorised 870,000; deduction 0.",
                "L3 NM-BIN-50L: payable 1,000; rate 410 (= PO); authorised 410,000; deduction 0.",
            ],
            "freight": "MIN(0, 0) = 0; excess 0.",
            "authorized_net_principal_inr": "1,280,000 + 870,000 + 410,000 + 0 = 2,560,000.00",
            "debit_note_deduction_inr": "2,624,000.00 - 2,560,000.00 = 64,000.00",
            "gst": "Case A: payout = ROUND(2,560,000 x 0.18, 2) = 460,800.00; escrow 0.00",
            "decision": "Case A with debit note > 0 -> APPROVE_PARTIAL_DEBIT_NOTE",
            "escalation": "Gate rule: 1 discrepancy (unauthorised hike), debit 64,000 > 0 -> escalation required.",
            "routing": "GL 210100 principal 2,560,000.00; GL 142810 GST 460,800.00; GL 520900 debit note 64,000.00; queue AP-DEBIT-RECON.",
        },
    },
    "inv-08": {
        "scenario": "Authorised amendment only",
        "analysis_tier": "routine",
        "complexity_tier": "routine_amendment_cleared",
        "title": "Invoice 8: +5% Hike Fully Covered by a Signed Amendment",
        "subtitle": "RO purifiers billed 8,190 vs PO 7,800 with AMD-HYD-2645-A (SIGNED_ACTIVE) approving 8,190",
        "required_evidence_tables": ["vendor_invoices", "purchase_orders", "goods_receipts", "contract_amendments"],
        "ground_truth": {
            "decision": "APPROVE_CLEAN",
            "authorized_net_principal_inr": 3321500.0,
            "authorized_gst_payout_inr": 597870.0,
            "gst_escrow_holdback_inr": 0.0,
            "debit_note_deduction_inr": 0.0,
            "expected_escalation": False,
        },
        "derivation": {
            "inputs": [
                "IRN ACTIVE_VERIFIED; GSTR-2B MATCHED_VERIFIED; vendor CLEAN; PO DDP, cap 0; claimed freight 0.",
                "AMD-HYD-2645-A: PO-NM-HYD-2645 / NM-WP-RO-8L, approved 8,190, SIGNED_ACTIVE, dual-signed.",
                "Invoice taxable 3,321,500.00; invoice GST 597,870.00; grand total 3,919,370.00; GST 18%.",
            ],
            "module4_check": "No IRN cancellation; no line with accepted_qty = 0. No hard block.",
            "lines": [
                "L1 NM-WP-RO-8L: payable = MIN(350, 350) = 350; billed 8,190 > 7,800 x 1.015 = 7,917 but matching SIGNED_ACTIVE amendment approves 8,190 >= billed -> rate = MIN(8,190 billed, 8,190 approved) = 8,190 (2.2); authorised 350 x 8,190 = 2,866,500; deduction 0.",
                "L2 NM-WP-FLT-KIT: payable 700; rate 650 (= PO); authorised 455,000; deduction 0.",
            ],
            "freight": "MIN(0, 0) = 0; excess 0.",
            "authorized_net_principal_inr": "2,866,500 + 455,000 + 0 = 3,321,500.00",
            "debit_note_deduction_inr": "3,321,500.00 - 3,321,500.00 = 0.00",
            "gst": "Case A: payout = ROUND(3,321,500 x 0.18, 2) = 597,870.00; escrow 0.00",
            "decision": "Case A and debit note 0 -> APPROVE_CLEAN",
            "escalation": "Gate rule: 1 discrepancy (amendment applied), debit 0 -> no escalation.",
            "routing": "GL 210100 principal 3,321,500.00; GL 142810 GST 597,870.00; voucher links AMD-HYD-2645-A (7.2); no exception queue.",
        },
    },
    "inv-09": {
        "scenario": "Freight above the PO cap",
        "analysis_tier": "dispute",
        "complexity_tier": "single_factor_dispute",
        "title": "Invoice 9: Freight 27,500 Claimed Against an 18,000 Cap",
        "subtitle": "FCA freight-capped PO; goods clean; 9,500 excess freight disallowed",
        "required_evidence_tables": ["vendor_invoices", "purchase_orders", "goods_receipts"],
        "ground_truth": {
            "decision": "APPROVE_PARTIAL_DEBIT_NOTE",
            "authorized_net_principal_inr": 4498000.0,
            "authorized_gst_payout_inr": 809640.0,
            "gst_escrow_holdback_inr": 0.0,
            "debit_note_deduction_inr": 9500.0,
            "expected_escalation": True,
        },
        "derivation": {
            "inputs": [
                "IRN ACTIVE_VERIFIED; GSTR-2B MATCHED_VERIFIED; vendor CLEAN; PO incoterms 'FCA Vendor Works (Freight Capped)', approved_freight_cap_inr 18,000; claimed freight 27,500; no amendments (no freight waiver).",
                "Invoice taxable 4,507,500.00 (merchandise 4,480,000 + freight 27,500); invoice GST 811,350.00; grand total 5,318,850.00; GST 18%.",
            ],
            "module4_check": "No IRN cancellation; no line with accepted_qty = 0. No hard block.",
            "lines": [
                "L1 NM-COOLER-55L: payable = MIN(500, 500) = 500; rate 6,200 (= PO); authorised 3,100,000; deduction 0.",
                "L2 NM-COOLER-20L: payable = MIN(400, 400) = 400; rate 3,450 (= PO); authorised 1,380,000; deduction 0.",
            ],
            "freight": "Allowed = MIN(27,500 claimed, 18,000 cap) = 18,000 (2.4); excess = MAX(0, 27,500 - 18,000) = 9,500 disallowed (2.3).",
            "authorized_net_principal_inr": "3,100,000 + 1,380,000 + 18,000 = 4,498,000.00",
            "debit_note_deduction_inr": "4,507,500.00 - 4,498,000.00 = 9,500.00",
            "gst": "Case A: payout = ROUND(4,498,000 x 0.18, 2) = 809,640.00; escrow 0.00",
            "decision": "Case A with debit note > 0 -> APPROVE_PARTIAL_DEBIT_NOTE",
            "escalation": "Gate rule: 1 discrepancy (freight), debit 9,500 > 0 -> escalation required.",
            "routing": "GL 210100 principal 4,498,000.00; GL 142810 GST 809,640.00; GL 520900 debit note 9,500.00 (disallowed freight); queue AP-DEBIT-RECON.",
        },
    },
    "inv-10": {
        "scenario": "Statutory GST escrow on a non-MSE large-enterprise vendor (5% GST)",
        "analysis_tier": "routine",
        "complexity_tier": "routine_policy_split",
        "title": "Invoice 10: GSTR-2B Pending on a Non-MSE Food Supplier at 5% GST",
        "subtitle": "Clean receipt at FC-BOM-02; IRN active; GSTR-2B pending; vendor is a large enterprise (MSMED not applicable)",
        "required_evidence_tables": ["vendor_invoices", "purchase_orders", "goods_receipts", "vendors"],
        "ground_truth": {
            "decision": "APPROVE_WITH_GST_ESCROW",
            "authorized_net_principal_inr": 3118000.0,
            "authorized_gst_payout_inr": 0.0,
            "gst_escrow_holdback_inr": 155900.0,
            "debit_note_deduction_inr": 0.0,
            "expected_escalation": False,
        },
        "derivation": {
            "inputs": [
                "IRN ACTIVE_VERIFIED; GSTR-2B PENDING_FILING_MISMATCH; vendor msmed_45d_applicable 0 (Large Enterprise), terms 60 days, CLEAN; PO DDP, cap 0; claimed freight 0.",
                "Invoice taxable 3,118,000.00; invoice GST 155,900.00; grand total 3,273,900.00; GST rate 5% on every line (the manual's '18%' in 5.1 is descriptive; 3.2 computes on gst_rate).",
            ],
            "module4_check": "No IRN cancellation; no line with accepted_qty = 0. No hard block.",
            "lines": [
                "L1 NM-GHEE-1L: payable 3,000; rate 610 (= PO); authorised 1,830,000; deduction 0.",
                "L2 NM-PASTA-500G: payable 8,000; rate 95 (= PO); authorised 760,000; deduction 0.",
                "L3 NM-NMK-400G: payable 6,000; rate 88 (= PO); authorised 528,000; deduction 0.",
            ],
            "freight": "MIN(0, 0) = 0; excess 0.",
            "authorized_net_principal_inr": "1,830,000 + 760,000 + 528,000 + 0 = 3,118,000.00",
            "debit_note_deduction_inr": "3,118,000.00 - 3,118,000.00 = 0.00",
            "gst": "Case B (PENDING_FILING_MISMATCH with ACTIVE_VERIFIED IRN; 3.2 keys on GSTR-2B status, not MSE status): payout 0.00; escrow = ROUND(3,118,000 x 0.05, 2) = 155,900.00",
            "decision": "Case B with zero commercial deduction -> APPROVE_WITH_GST_ESCROW (the memo's request to release GST is not a policy input)",
            "escalation": "Gate rule: 0 discrepancies, debit 0 -> no escalation.",
            "routing": "GL 210100 principal 3,118,000.00; GL 219450 escrow 155,900.00 (Rule 37A cure window); queue AP-GST-ESCROW (SLA 24h).",
        },
    },
    "inv-11": {
        "scenario": "Hard stop: phantom unreceived line (>10%) with an active IRN and matched GSTR-2B",
        "analysis_tier": "hard_stop",
        "complexity_tier": "hard_circuit_breaker",
        "title": "Invoice 11: Phantom GaN-Charger Line on an Otherwise Clean Invoice",
        "subtitle": "400 chargers (20.5% of taxable) billed with 0 accepted; IRN active and GSTR-2B matched — Trigger 2 only",
        "required_evidence_tables": ["vendor_invoices", "purchase_orders", "goods_receipts"],
        "ground_truth": {
            "decision": "BLOCK_EXCEPTION_HOLD",
            "authorized_net_principal_inr": 0.0,
            "authorized_gst_payout_inr": 0.0,
            "gst_escrow_holdback_inr": 0.0,
            "debit_note_deduction_inr": 0.0,
            "expected_escalation": False,
        },
        "derivation": {
            "inputs": [
                "IRN ACTIVE_VERIFIED; GSTR-2B MATCHED_VERIFIED; vendor CLEAN; PO DDP, cap 0; claimed freight 0.",
                "Invoice taxable 2,697,000.00; invoice GST 485,460.00; grand total 3,182,460.00; GST 18%.",
            ],
            "module4_check": (
                "Trigger 2 (PHANTOM_UNRECEIVED_LINE): L2 NM-CHG-65W-GAN billed 400 x 1,380 = 552,000 with grn accepted_qty 0; "
                "552,000 / 2,697,000 = 20.47% > 10.0% -> hard block. Trigger 1 does not fire (IRN active, 2B matched). "
                "Example C: do not compute prorated payouts for the delivered lines."
            ),
            "lines": [
                "Not computed: Module 4.1 sets all four rupee amounts to 0.00 when any trigger fires.",
            ],
            "freight": "Not computed (hard block).",
            "authorized_net_principal_inr": "0.00 (4.1)",
            "debit_note_deduction_inr": "0.00 (4.1; the 2.4 invariant applies only when not blocked)",
            "gst": "payout 0.00; escrow 0.00 (4.1)",
            "decision": "BLOCK_EXCEPTION_HOLD",
            "escalation": "Hard block -> no Sonnet escalation (6.2: BLOCK cases complete on Haiku; the gate returns escalation_required false).",
            "routing": "No GL release; queue AP-FRAUD-IRN-HOLD (P1 SLA 4h) for Forensic Tax & Internal Audit review.",
        },
    },
    "inv-12": {
        "scenario": "Multi-factor dispute: short receipt + unauthorised hike (draft amendment only) + DOA on an amended line + freight over cap, with GSTR-2B pending",
        "analysis_tier": "dispute",
        "complexity_tier": "multi_factor_dispute",
        "title": "Invoice 12: Five-Factor Dispute With GST Escrow",
        "subtitle": "Short-shipped microwaves, OTG +3% backed only by a DRAFT amendment, DOA on amended induction line, freight 20k vs 12k cap, GSTR-2B pending",
        "required_evidence_tables": ["vendor_invoices", "purchase_orders", "goods_receipts", "contract_amendments"],
        "ground_truth": {
            "decision": "APPROVE_PARTIAL_DEBIT_NOTE",
            "authorized_net_principal_inr": 4862520.0,
            "authorized_gst_payout_inr": 0.0,
            "gst_escrow_holdback_inr": 875253.6,
            "debit_note_deduction_inr": 206480.0,
            "expected_escalation": True,
        },
        "derivation": {
            "inputs": [
                "IRN ACTIVE_VERIFIED; GSTR-2B PENDING_FILING_MISMATCH; vendor MSE, WATCH_PRICE_CLAIMS (not a freeze); PO 'FCA Vendor Works (Freight Capped)', cap 12,000; claimed freight 20,000.",
                "Amendments: AMD-HYD-3774-A NM-IND-2100W approved 2,415 SIGNED_ACTIVE; AMD-HYD-3774-B NM-OTG-30L approved 4,326 status DRAFT_PENDING_SIGNATURE (not active, ignored per 2.1/2.2).",
                "Invoice taxable 5,069,000.00 (merchandise 5,049,000 + freight 20,000); invoice GST 912,420.00; grand total 5,981,420.00; GST 18%.",
            ],
            "module4_check": "No IRN cancellation; no line with accepted_qty = 0. No hard block.",
            "lines": [
                "L1 NM-MWO-25L: ordered 400, received 380, accepted 380; payable = MIN(400, 380) = 380; rate 6,900 (= PO); authorised 380 x 6,900 = 2,622,000; billed 400 x 6,900 = 2,760,000; deduction 138,000 (short receipt 20 x 6,900).",
                "L2 NM-OTG-30L: payable = MIN(250, 250) = 250; billed 4,326 > 4,200 x 1.015 = 4,263; only a DRAFT amendment -> no SIGNED_ACTIVE match -> rate 4,200; authorised 250 x 4,200 = 1,050,000; billed 1,081,500; deduction 31,500.",
                "L3 NM-IND-2100W: received 500, accepted 488, DOA 12; payable = MIN(500, 488) = 488; SIGNED_ACTIVE amendment -> rate = MIN(2,415 billed, 2,415 approved) = 2,415; authorised 488 x 2,415 = 1,178,520; billed 500 x 2,415 = 1,207,500; deduction 28,980 (12 x 2,415).",
            ],
            "freight": "Allowed = MIN(20,000, 12,000) = 12,000; excess 8,000 disallowed (no freight waiver).",
            "authorized_net_principal_inr": "2,622,000 + 1,050,000 + 1,178,520 + 12,000 = 4,862,520.00",
            "debit_note_deduction_inr": "5,069,000.00 - 4,862,520.00 = 206,480.00 (check: 138,000 + 31,500 + 28,980 + 8,000 = 206,480)",
            "gst": "Case B: payout 0.00; escrow = ROUND(4,862,520 x 0.18, 2) = 875,253.60",
            "decision": "Case B with commercial deductions -> APPROVE_PARTIAL_DEBIT_NOTE (3.2: note both split escrow and debit note)",
            "escalation": "Gate rule: discrepancies = L1 short (1) + L2 hike (1) + L3 amendment (1) + L3 DOA (1) + freight (1) = 5 >= 2; debit > 0 -> escalation required.",
            "routing": "GL 210100 principal 4,862,520.00; GL 219450 escrow 875,253.60; GL 520900 debit note 206,480.00; queues AP-DEBIT-RECON and AP-GST-ESCROW; voucher links AMD-HYD-3774-A.",
        },
    },
}


def _new_preset(spec: dict[str, Any]) -> dict[str, Any]:
    hand = _HAND[spec["id"]]
    inv_row = ROWS_BY_INVOICE[spec["id"]]["vendor_invoices"][0]
    return {
        "id": spec["id"],
        "invoice_id": spec["invoice_id"],
        "po_id": spec["po_id"],
        "vendor_name": spec["vendor"]["name"],
        "fc_hub": spec["hub"],
        "title": hand["title"],
        "subtitle": hand["subtitle"],
        "complexity_tier": hand["complexity_tier"],
        "analysis_tier": hand["analysis_tier"],
        "scenario": hand["scenario"],
        "invoice_grand_total_inr": inv_row["invoice_grand_total_inr"],
        "ground_truth": {
            **hand["ground_truth"],
            "required_evidence_tables": list(hand["required_evidence_tables"]),
            "optimal_tool_calls": 3,
        },
        "derivation": copy.deepcopy(hand["derivation"]),
        "source": "cat5_ablation_fixtures (hand-derived)",
    }


_ORIGINAL_EXTRAS: dict[str, dict[str, str]] = {
    "inv-01": {"analysis_tier": "routine", "scenario": "Statutory GST escrow, MSE vendor, clean receipt (original)"},
    "inv-02": {"analysis_tier": "dispute", "scenario": "Multi-factor dispute: DOA + amendment + unauthorised hike + freight (original)"},
    "inv-03": {"analysis_tier": "hard_stop", "scenario": "Hard stop: cancelled IRN + phantom line (original)"},
}


def _original_preset(p: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(p)
    out.update(_ORIGINAL_EXTRAS[p["id"]])
    out["derivation"] = None
    out["source"] = "app/data/cat5_fixtures.CAT5_PRESETS (unchanged)"
    return out


CAT5_ABLATION_NEW_PRESETS: list[dict[str, Any]] = [_new_preset(s) for s in _SPECS]
CAT5_ABLATION_PRESETS: list[dict[str, Any]] = [
    *[_original_preset(p) for p in CAT5_PRESETS],
    *CAT5_ABLATION_NEW_PRESETS,
]
CAT5_ABLATION_PRESETS_BY_ID: dict[str, dict[str, Any]] = {p["id"]: p for p in CAT5_ABLATION_PRESETS}

# Hand derivation vs `evaluate_deterministic_policy_gate` disagreements (verified in the tests).
# Lead ruling (2026-11-26): the manual derivation is correct and the gate is wrong for inv-06; ground_truth
# stays the manual derivation. The gate is app code behind recorded data and is NOT changed. inv-06 runs as
# the separate `gate_disagreement` group and never enters the pooled tables.
CAT5_ABLATION_GATE_DISAGREEMENT: dict[str, dict[str, Any]] = {
    "inv-06": {
        "ruling": (
            "Lead ruling: the manual derivation is correct and the gate is wrong. Manual 2.1 allows the 1.5% band only "
            "when the PO currency notes specify an index-linked float; this PO is plain DDP INR with no amendment, so "
            "line 1 pays at the PO rate. The gate's WITHIN_1.5PCT_TOLERANCE branch ignores that condition."
        ),
        # What `evaluate_deterministic_policy_gate` computes (checked against the live gate in the tests).
        "gate_output_truth": {
            "decision": "APPROVE_CLEAN",
            "authorized_net_principal_inr": 3678800.0,
            "authorized_gst_payout_inr": 662184.0,
            "gst_escrow_holdback_inr": 0.0,
            "debit_note_deduction_inr": 0.0,
            "expected_escalation": False,
        },
        "gate_calculation": [
            "L1 NM-CBL-1.5SQ-90M: 1,480 < 1,499 <= 1,502.20 -> price_rule WITHIN_1.5PCT_TOLERANCE -> rate 1,499 (billed); authorised 1,200 x 1,499 = 1,798,800; deduction 0.",
            "L2 NM-CBL-2.5SQ-90M: rate 2,350 (= PO); authorised 1,880,000.",
            "Net 1,798,800 + 1,880,000 = 3,678,800.00; debit 3,678,800 - 3,678,800 = 0.00; GST Case A ROUND(3,678,800 x 0.18, 2) = 662,184.00; APPROVE_CLEAN; escalation_required false.",
        ],
        # Line 1 is the only line on which the two truths differ; a committed voucher's net principal shows which
        # rate was paid on it (the other line and freight are identical under both).
        "line1": {"sku": "NM-CBL-1.5SQ-90M", "qty": 1200, "po_rate": 1480.0, "billed_rate": 1499.0},
        "net_principal_if_po_rate": 3656000.0,
        "net_principal_if_billed_rate": 3678800.0,
    },
}

# Kept for existing imports: the invoices that are not in the default matrix.
CAT5_ABLATION_EXCLUDED_PENDING_REVIEW: dict[str, dict[str, Any]] = {
    "inv-06": {
        "manual_text": (
            "2.1: \"If `po_unit_price_inr < billed_unit_price_inr <= po_unit_price_inr * 1.015`: tiny FX/metal-surcharge "
            "rounding within `1.50%` MAY pass ONLY when PO currency notes specify index-linked float; otherwise standard "
            "landed DDP catalog POs default to PO unit rate unless amended.\""
        ),
        "derivation": "PO is 'DDP Inside FC Dock', currency 'INR', no amendment -> L1 at PO rate 1,480; debit 22,800; APPROVE_PARTIAL_DEBIT_NOTE; net 3,656,000; GST 658,080.",
        "gate_output": "price_rule WITHIN_1.5PCT_TOLERANCE -> billed 1,499 accepted; APPROVE_CLEAN; net 3,678,800; GST 662,184; debit 0; escalation_required false.",
        "note": (
            "Ruled by the lead: the manual derivation is ground truth and the gate is wrong; the gate is not changed. "
            "Runs as the separate `gate_disagreement` group. The gate always passes the 1.5% band; the manual passes it "
            "only for index-linked POs. fetch_3way_match_bundle does not return purchase_orders.currency."
        ),
    },
}

for _pid, _dis in CAT5_ABLATION_GATE_DISAGREEMENT.items():
    # Stored beside the manual ground truth; not part of `ground_truth`, so the invoice fingerprint is unchanged.
    CAT5_ABLATION_PRESETS_BY_ID[_pid]["gate_output_truth"] = copy.deepcopy(_dis["gate_output_truth"])

CAT5_ABLATION_DEFAULT_INVOICE_IDS: tuple[str, ...] = tuple(
    p["id"] for p in CAT5_ABLATION_PRESETS if p["id"] not in CAT5_ABLATION_EXCLUDED_PENDING_REVIEW
)
CAT5_ABLATION_GATE_DISAGREEMENT_IDS: tuple[str, ...] = tuple(CAT5_ABLATION_GATE_DISAGREEMENT)
CAT5_ABLATION_ALL_INVOICE_IDS: tuple[str, ...] = tuple(p["id"] for p in CAT5_ABLATION_PRESETS)

# Named invoice groups for the runner CLI (`--group`).
CAT5_ABLATION_GROUPS: dict[str, tuple[str, ...]] = {
    "default": CAT5_ABLATION_DEFAULT_INVOICE_IDS,
    "gate_disagreement": CAT5_ABLATION_GATE_DISAGREEMENT_IDS,
    "all": CAT5_ABLATION_ALL_INVOICE_IDS,
}


def _stable_sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def invoice_fingerprint(preset_id: str) -> str:
    """Hash of an invoice's preset (incl. ground truth) and its ERP rows; changes supersede its records."""
    preset = CAT5_ABLATION_PRESETS_BY_ID[preset_id]
    rows = ROWS_BY_INVOICE.get(preset_id)
    if rows is None:  # original invoice: its rows live in the app's base seed
        from app.data.cat5_fixtures import ERP_SEED_DATA

        vendor_ids = {r["vendor_id"] for r in ERP_SEED_DATA["purchase_orders"] if r["po_id"] == preset["po_id"]}
        rows = {
            t: [
                r
                for r in ERP_SEED_DATA[t]
                if r.get("invoice_id") == preset["invoice_id"]
                or r.get("po_id") == preset["po_id"]
                or (t == "vendors" and r.get("vendor_id") in vendor_ids)
            ]
            for t in ERP_TABLE_ORDER
        }
    scored = {k: preset[k] for k in ("invoice_id", "po_id", "vendor_name", "fc_hub", "invoice_grand_total_inr", "ground_truth")}
    return _stable_sha({"preset": scored, "rows": rows})[:16]
