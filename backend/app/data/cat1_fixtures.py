"""Realistic 550–1,050 token NovaMart Enterprise fixtures for Category 1 (Triage & SKU Gate)."""

from __future__ import annotations

from typing import Any

CAT1_PRESETS: list[dict[str, Any]] = [
    {
        "id": "tkt-01",
        "sub_task": "support_triage",
        "title": "Damaged Ceramic Dinnerware + Exposed Payment Card & Phone",
        "subtitle": "Multi-message email escalation · Order JSON · Carrier telemetry · Raw PII",
        "channel": "Omnichannel Email + Portal",
        "approx_tokens": 785,
        "payload": """=== NOVAMART INTAKE ENVELOPE ===
ticket_id: NM-CS-2026-884921
channel: email_escalation
vip_tier: NovaPrime_Gold
order_id: NM-ORD-99401283
seller_id: SLR-40192 (Artisanal Hearth Studio)
timestamp_utc: 2026-11-16T13:42:18Z

--- CUSTOMER MESSAGE THREAD (MOST RECENT FIRST) ---
From: Priya Nair <priya.nair@customer-demo.example>
Phone: +1 (415) 555-0194
Subject: URGENT: Shattered Diwali Dinnerware Set + Wrong Card Charge on Reorder!!

Hi NovaMart Escalations,
I am writing for the third time today because your automated chat bot kept looping me back to the FAQ. My 16-piece Artisanal Stoneware Ceramic Dinnerware Set (SKU: NM-HOME-77412) arrived about two hours ago via BlueDart/FedEx Ground, and when I opened the outer carton, six dinner plates and four soup bowls were completely shattered into jagged shards inside the box. The inner foam divider was completely missing—just one sheet of thin brown paper around heavy ceramic plates! I have guests arriving tomorrow evening for our family Diwali dinner, and I cannot wait 7 business days for a slow carrier investigation.

Even worse, when I tried placing an emergency backup order in the app, my stored Visa card 4532-8910-4421-0099 got charged twice ($189.50 pending + $189.50 posted), and your checkout screen threw a timeout error. Please either trigger an express overnight replacement for the shattered ceramic dinnerware set right away OR refund the duplicate charge to my card 4532-8910-4421-0099 and confirm by calling me back at 415-555-0194 or emailing priya.nair@customer-demo.example before 6 PM PT. I attached three photos of the shattered box and packing slip below.

--- PRIOR SUPPORT CHAT LOG (TRUNCATED) ---
[12:04Z] User: Box arrived crushed and rattling. Half the stoneware bowls are broken.
[12:05Z] Bot: Sorry to hear that! Please review our 14-day return window policy.
[12:07Z] User: I need an immediate replacement shipment today and someone to check my double charge on card ending 0099. Escalate me to a specialist!

--- CARRIER & ORDER TELEMETRY SNAPSHOT ---
{
  "order_total_usd": 189.50,
  "sku": "NM-HOME-77412",
  "item_title": "Artisanal Stoneware Ceramic Dinnerware Set - 16pc Matte Indigo",
  "fragile_flag": true,
  "fulfillment_node": "FBO-OAK-04",
  "carrier": "FedEx Ground",
  "tracking": "774920194812",
  "hub_scans": [
    {"hub": "OAK-SORT-1", "event": "EXCEPTION_REPACK_DAMAGED_CARTON", "ts": "2026-11-15T04:11Z"},
    {"hub": "SFO-DEL-02", "event": "DELIVERED_FRONT_PORCH_LEFT_AT_DOOR", "ts": "2026-11-16T11:30Z"}
  ],
  "payment_gateway_events": [
    {"auth_id": "AUTH-991A", "amount": 189.50, "status": "CAPTURED"},
    {"auth_id": "AUTH-991B", "amount": 189.50, "status": "PENDING_HOLD_RETRY_TIMEOUT"}
  ],
  "customer_lifetime_orders": 47,
  "prior_return_rate_pct": 2.1
}""",
        "ground_truth": {
            "queue": "replacements",
            "priority": "P1_HIGH",
            "auto_action": "auto_replace",
            "contains_pii": True,
        },
    },
    {
        "id": "tkt-02",
        "sub_task": "support_triage",
        "title": "Seller Diwali Settlement Hold + Exposed Aadhaar/PAN Tax ID",
        "subtitle": "Seller portal dispute · Ledger dump · Regulatory threat · High PII exposure",
        "channel": "Seller Central Portal",
        "approx_tokens": 860,
        "payload": """=== NOVAMART SELLER PORTAL ESCALATION ===
ticket_id: NM-SLR-2026-552019
channel: seller_portal_high_priority
seller_id: SLR-88210 (Apex Lumina Electronics LLC)
seller_tier: Marketplace_Pro_Platinum
gmv_trailing_90d_usd: 412800.00
timestamp_utc: 2026-11-16T14:05:44Z

--- SELLER DISPUTE SUBMISSION ---
Submitted By: Vikram Mehta (vikram.mehta@apexlumina.example) | Direct Tel: +1 (312) 555-0148
Attention: NovaMart Seller Finance, Compliance & Legal Escrow Team,

Our scheduled Diwali peak settlement disbursement of $148,920.00 (Batch ID: PAY-2026-W46-88210) has been frozen in "COMPLIANCE_ESCROW_HOLD" for 96 hours with zero prior notice, right when we owe our upstream logistics suppliers for 4,200 shipped units! Our vendor dashboard shows an automated flag claiming a mismatch between our W-9/PAN tax filing and our beneficiary bank account.

I am re-attaching our verified corporate owner credentials directly here so your team can release the $148,920.00 payout immediately:
- Beneficial Owner Aadhaar: 4829-6173-9042
- India Cross-Border Entity PAN: ABCDE1234F
- Direct Contact Email: vikram.mehta@apexlumina.example
- Backup Accounting Phone: 312-555-0148
- Corporate Settlement Card on File (for fee billing): 5412-7500-8812-3344

If NovaMart does not release our undisputed $148,920.00 ledger balance or assign a senior Treasury Compliance specialist within 24 hours, our legal counsel will file a formal commercial arbitration notice under Section 14.3 of the Marketplace Seller Agreement and pause our remaining 1,850 active Diwali catalog listings. Please review the attached ledger reconciliation summary below.

--- AUTOMATED RISK & LEDGER DUMP ---
{
  "settlement_batch_id": "PAY-2026-W46-88210",
  "gross_sales_usd": 176400.00,
  "marketplace_commission_usd": -21168.00,
  "fulfillment_fees_usd": -6312.00,
  "net_payable_usd": 148920.00,
  "escrow_hold_reason": "TAX_TIN_KYC_MISMATCH_TRIGGER_409",
  "chargeback_rate_30d_pct": 0.18,
  "order_defect_rate_pct": 0.42,
  "tax_profile_snapshot": {
    "entity_legal_name": "Apex Lumina Electronics LLC",
    "tin_verification_status": "PENDING_MANUAL_REVIEW_NAME_VARIANCE",
    "last_kyc_audit": "2025-09-14"
  },
  "legal_keywords_detected": ["arbitration notice", "Section 14.3", "escrow hold", "undisputed balance"]
}""",
        "ground_truth": {
            "queue": "billing_payouts",
            "priority": "P1_HIGH",
            "auto_action": "hold_and_audit",
            "contains_pii": True,
        },
    },
    {
        "id": "tkt-03",
        "sub_task": "support_triage",
        "title": "Suspected Account Takeover & Gift-Card Drain via IVR Transcript",
        "subtitle": "Voice IVR transcript · Session anomaly JSON · Device mismatch · P0 Security",
        "channel": "Voice IVR + Fraud Telemetry",
        "approx_tokens": 730,
        "payload": """=== NOVAMART VOICE IVR + TRUST & SAFETY TELEMETRY ===
ticket_id: NM-SEC-2026-910442
channel: inbound_ivr_voice_transcript
account_id: CUST-3091882
timestamp_utc: 2026-11-16T14:52:09Z

--- SPEECH-TO-TEXT CALL TRANSCRIPT (CONFIDENCE: 0.96) ---
[00:00:03] Caller: "Hi, please connect me to a human immediately, my NovaMart account is being hacked right now! I just got three SMS codes I never requested, and then an email saying my login email was changed to some random address I don't recognize!"
[00:00:18] IVR: "I can help with account questions. Can you briefly describe what happened?"
[00:00:24] Caller: "Someone logged into my account, locked me out of the app, and just redeemed my $450 NovaMart gift card balance plus tried ordering two gaming consoles to a drop-off locker in Newark! My real email is david.chen88@mail-demo.example and my registered phone is 206-555-0173. Wait—now I see an alert for an unauthorized Visa 4916-3320-1194-8821 pre-auth for $1,199! Freeze everything right now before the gift card digital codes get exported!"
[00:00:51] IVR: "Escalating call metadata to automated intake queue..."

--- REAL-TIME SESSION & FRAUD TELEMETRY ---
{
  "account_age_days": 1420,
  "email_change_event": {
    "ts": "2026-11-16T14:49:11Z",
    "old_email": "david.chen88@mail-demo.example",
    "new_email": "x992_drop_acc@proton-temp.example",
    "mfa_bypass_flag": true
  },
  "geo_velocity_anomaly": {
    "prior_login_city": "Seattle, WA",
    "prior_login_ts": "2026-11-16T11:10:00Z",
    "current_session_ip": "185.220.101.44",
    "current_asn": "TOR_EXIT_PROXY_SUSPECT",
    "device_fingerprint_match": false
  },
  "pending_high_risk_orders": [
    {"order_id": "NM-ORD-99419002", "item": "Digital Gift Card Wallet Drain", "amount_usd": 450.00, "fulfillment": "INSTANT_EMAIL_DELIVERY_QUEUED"},
    {"order_id": "NM-ORD-99419009", "item": "NovaStation Pro Console x2", "amount_usd": 1199.00, "fulfillment": "LOCKER_PICKUP_NEWARK"}
  ],
  "security_risk_signals": {
    "ato_model_score": 0.984,
    "sms_otp_velocity_last_10m": 4,
    "password_reset_attempts_last_10m": 3,
    "saved_payment_tokens_count": 2,
    "recommended_playbooks": ["LOCK_WALLET_EXPORT", "REVOKE_REFRESH_TOKENS", "HOLD_LOCKER_DISPATCH", "NOTIFY_ORIGINAL_EMAIL"]
  }
}""",
        "ground_truth": {
            "queue": "trust_and_safety",
            "priority": "P0_CRITICAL",
            "auto_action": "escalate_security",
            "contains_pii": True,
        },
    },
    {
        "id": "sku-01",
        "sub_task": "sku_tagging",
        "title": "Cold-Start Apparel: '100% Pure Mulberry Silk Kurta' w/ Label OCR Contradiction",
        "subtitle": "Seller JSON feed vs. garment care-tag OCR · Hinglish copy · Legal Class-C gate",
        "channel": "Bulk Supplier Catalog Ingestion",
        "approx_tokens": 765,
        "payload": """=== NOVAMART COLD-START SKU EVIDENCE BUNDLE ===
sku_ingestion_id: ING-APP-2026-773901
seller_id: SLR-21904 (Jaipur Heritage Looms)
feed_source: supplier_csv_diwali_burst
predicted_leaf_hint: Apparel > Ethnic Wear

--- SELLER-SUBMITTED METADATA ---
title: "Royal Banarasi 100% Pure Mulberry Silk Festive Kurta Set for Men - Handloom Gold Zari"
brand: "Jaipur Heritage Looms"
declared_material: "100% Pure Mulberry Silk"
declared_care: "Hand wash gentle"
bullet_points:
  - "Pure resham mulberry silk fabric ekdum royal festive look for Diwali & wedding functions"
  - "Breathable natural protein fiber, zero synthetic mix, authentic Banarasi weave"
  - "Includes matching chanderi dupatta and tailored trouser"
mrp_inr: 6999
selling_price_inr: 2499

--- GARMENT CARE LABEL OCR EXTRACTION (PHOTO #4: ZOOMED NECK & WASH TAG) ---
{
  "ocr_engine": "vlm_label_reader_v3",
  "ocr_confidence": 0.98,
  "raw_label_lines": [
    "JHL FASHION APPARELS PVT LTD",
    "STYLE: JHL-KRT-884 | SIZE: L (40)",
    "SHELL FABRIC: 80% POLYESTER / 20% VISCOSE",
    "LINING: 100% POLYESTER TAFFETA",
    "CARE: DRY CLEAN ONLY. DO NOT BLEACH. COOL IRON REVERSE SIDE.",
    "MADE IN SURAT, INDIA"
  ]
}

--- POLICY & SEARCH FACET CHECK ---
seller_claim_material: "100% Pure Mulberry Silk"
ocr_verified_material: "80% Polyester / 20% Viscose"
search_facet_impact: "30% of Ethnic Wear buyers filter explicitly by Material=Pure Silk; high Not-As-Described (NAD) return risk if unverified silk facet is indexed."
visual_color_cielab: "Crimson Maroon (#7F1D1D) with metallic gold border"
hazmat_indicators_present: false
catalog_enrichment_telemetry:
  seller_historical_nad_return_rate_pct: 14.8
  category_median_nad_return_rate_pct: 4.1
  size_chart_ocr_rows:
    - "M: Chest 40 in | Length 41 in | Shoulder 17.5 in"
    - "L: Chest 42 in | Length 42 in | Shoulder 18.2 in"
    - "XL: Chest 44 in | Length 43 in | Shoulder 19.0 in"
  legal_policy_rule: "Class-C Factual Contradiction: Never silently rewrite seller title, suppress contradicted Material=Pure Silk search facet & route to compliance audit."
  image_audit_summary: "4 photos supplied: Front studio, close-up zari border, back view, zoomed inner collar care tag (source of polyester/viscose OCR)."
  diwali_demand_score: 0.91""",
        "ground_truth": {
            "leaf_category": "apparel_ethnic_kurtas",
            "compliance_status": "SUPPRESS_CONTRADICTED_FACET",
            "contradiction_detected": True,
        },
    },
    {
        "id": "sku-02",
        "sub_task": "sku_tagging",
        "title": "Electronics XML Feed: 27,000mAh 140W PowerBank Missing UN38.3 Air-Freight Cert",
        "subtitle": "Supplier spec sheet · Wh battery calculation (99.9Wh) · Hazmat gate",
        "channel": "Supplier XML API",
        "approx_tokens": 845,
        "payload": """=== NOVAMART COLD-START SKU EVIDENCE BUNDLE ===
sku_ingestion_id: ING-ELC-2026-441082
seller_id: SLR-67330 (VoltEdge Distribution Co.)
feed_source: edi_xml_v4
declared_hazmat_flag: false

--- SUPPLIER XML / SPEC PAYLOAD ---
title: "VoltEdge TitanCharge 27000mAh 140W PD 3.1 GaN Laptop Power Bank - Airline Approved"
brand: "VoltEdge"
declared_category: "Mobile & Laptop Accessories > Portable Chargers"
declared_battery_included: true
declared_dangerous_goods: "NONE - Safe Standard Ground & Air Parcel"
technical_specs:
  cell_chemistry: "Lithium-Ion Polymer (21700 High-Density Cells x 6)"
  nominal_capacity_mah: 27000
  nominal_voltage_v: 3.7
  rated_energy_wh: 99.9
  max_output_watts: 140
  ports: "2x USB-C PD 3.1 (140W/65W), 1x USB-A QC 3.0 (22.5W)"
  dimensions_mm: "155 x 54 x 49"
  weight_grams: 585
marketing_copy: >
  Charge a MacBook Pro 16" to 50% in 26 minutes! TSA/FAA friendly 99.9Wh capacity right under
  the 100Wh aviation ceiling. Ships fast via NovaMart Express Air from all regional hubs.

--- COMPLIANCE DOCUMENT AUDIT (ATTACHED PDF METADATA) ---
{
  "un38_3_test_summary_pdf": "MISSING",
  "msds_safety_sheet_pdf": "MISSING",
  "bis_crs_registration_number": "R-41099281 (Valid)",
  "watt_hour_check": "27000mAh * 3.7V / 1000 = 99.9 Wh (Class 9 Lithium Battery UN3480/UN3481 Air Cargo Rules Apply)",
  "seller_contradiction": "Seller marked declared_dangerous_goods=NONE despite 99.9Wh Lithium-Ion cell pack requiring Class-9 hazmat labeling and UN38.3 test report before air-freight dispatch.",
  "logistics_impact": {
    "air_express_eligible_without_un38_3": false,
    "ground_surface_hazmat_lane_required": true,
    "fulfillment_centers_impacted": ["FBO-DEL-01", "FBO-BLR-03", "FBO-OAK-04"],
    "packaging_spec_ocr_lines": [
      "MODEL: VE-TC27K-140 | INPUT: USB-C1 5V-20V/5A MAX 100W",
      "OUTPUT: USB-C1/C2 PD3.1 140W MAX | CELL RATING: 99.9Wh / 27000mAh Li-Polymer",
      "CAUTIONS: DO NOT CRUSH, INCINERATE OR EXPOSE ABOVE 60C. RECYCLE LITHIUM BATTERY."
    ]
  }
}""",
        "ground_truth": {
            "leaf_category": "electronics_power_banks",
            "compliance_status": "HOLD_MISSING_CERT",
            "contradiction_detected": True,
        },
    },
    {
        "id": "sku-03",
        "sub_task": "sku_tagging",
        "title": "Kitchen Appliance Feed: Commercial Burr Espresso Grinder (Verified Clean & Compliant)",
        "subtitle": "Clean distributor CSV + UL/BIS spec match · Auto-publish fast path",
        "channel": "Distributor Feed",
        "approx_tokens": 695,
        "payload": """=== NOVAMART COLD-START SKU EVIDENCE BUNDLE ===
sku_ingestion_id: ING-KIT-2026-119044
seller_id: SLR-10482 (BaristaCraft Official Store)
feed_source: verified_brand_csv
brand_authorization: AUTHORIZED_DIRECT_MANUFACTURER

--- DISTRIBUTOR METADATA & SPEC TABLE ---
title: "BaristaCraft Precision 64mm Flat Steel Burr Espresso Grinder - Matte Obsidian (110-120V)"
brand: "BaristaCraft"
model_number: "BC-FG64-PRO"
declared_category: "Home & Kitchen > Coffee & Espresso > Burr Grinders"
materials:
  burr_assembly: "64mm Hardened Stainless Steel Flat Burrs (DLC Coated)"
  chassis: "Die-Cast Anodized Aluminum Body"
  hopper: "BPA-Free Smoked Tritan Bean Hopper (350g capacity)"
electrical_rating:
  voltage: "110-120V ~ 60Hz (North America)"
  wattage: "400W Brushless DC Motor"
  plug_type: "NEMA 5-15P Grounded 3-Prong"
dimensions_weight: "21cm x 13cm x 34cm · 5.4 kg"
box_contents: "Grinder unit, 58mm magnetic dosing cup, RDT spray bottle, bellows, user manual"

--- VERIFICATION & COMPLIANCE TELEMETRY ---
{
  "rating_plate_ocr_match": {
    "model": "BC-FG64-PRO (EXACT MATCH)",
    "electrical": "110-120V~ 60Hz 400W (EXACT MATCH)",
    "certifications_stamped": ["UL Listed E492104", "FCC Part 15", "RoHS"]
  },
  "battery_present": false,
  "hazmat_materials": false,
  "factual_contradictions": [],
  "ready_for_auto_publish": true,
  "spec_pdf_extracted_attributes": {
    "grind_retention_grams": "<0.2g with bellows",
    "stepless_micrometric_dial": true,
    "noise_level_dba": 64.5,
    "duty_cycle_rating": "Continuous light-commercial / prosumer espresso bar",
    "warranty_terms": "24-month limited motor & burr housing warranty (BaristaCraft USA/IN service centers)",
    "packaging_drop_test_ista_3a": "PASS - molded pulp cradle verified",
    "search_facets_verified": ["Burr Type=Flat Steel", "Burr Size=64mm", "Voltage=110-120V", "Motor=Brushless DC"],
    "food_contact_compliance": "FDA 21 CFR & LFGB BPA-free hopper certification verified on file (REF-BC-2026-09)",
    "seller_marketing_bullets": [
      "Zero-retention single-dose design with low-static plasma ionizer chute for clumpless espresso extraction",
      "Tool-free magnetic upper burr carrier opens in 5 seconds for effortless brush cleaning",
      "Precision CNC-machined 64mm hardened steel flat burrs calibrated at 1,400 RPM low-heat grind speed"
    ]
  }
}""",
        "ground_truth": {
            "leaf_category": "kitchen_espresso_grinders",
            "compliance_status": "APPROVED_AUTO_PUBLISH",
            "contradiction_detected": False,
        },
    },
]

# 6 additional realistic medium-length payloads for the 12-item Batch & CFO Scale Simulator
CAT1_EXTRA_BATCH_ITEMS: list[dict[str, Any]] = [
    {
        "id": "tkt-04",
        "sub_task": "support_triage",
        "title": "Lost Holiday Parcel Tracking Stall (FedEx No Scan 5 Days)",
        "payload": (
            "ticket_id: NM-CS-2026-885102 | customer: Rahul Verma (rahul.v@demo.example, 408-555-0122) | "
            "Order NM-ORD-99301122 for Ergonomic Mesh Office Chair ($279.00) has shown 'LABEL CREATED - AWAITING CARRIER PICKUP' "
            "at fulfillment node FBO-DAL-02 for 5 consecutive business days. No damage reported, no unauthorized login, "
            "customer wants carrier dock scan trace and updated ETA before Friday."
        ),
        "ground_truth": {
            "queue": "shipping_logistics",
            "priority": "P2_MEDIUM",
            "auto_action": "route_specialist",
            "contains_pii": True,
        },
    },
    {
        "id": "tkt-05",
        "sub_task": "support_triage",
        "title": "Invoice GST/VAT Credit Correction Request on B2B Order",
        "payload": (
            "ticket_id: NM-CS-2026-885319 | buyer: NovaCorp Procurement (ap@novacorp-demo.example) | "
            "Order NM-ORD-99100441 ($3,420.00) billed to corporate account without applying uploaded tax-exempt certificate EX-99120. "
            "Accounting team requests credit memo reissue and invoice adjustment on current billing cycle."
        ),
        "ground_truth": {
            "queue": "billing_payouts",
            "priority": "P2_MEDIUM",
            "auto_action": "route_specialist",
            "contains_pii": True,
        },
    },
    {
        "id": "tkt-06",
        "sub_task": "support_triage",
        "title": "General Sizing & Care Question on Winter Wool Coat",
        "payload": (
            "ticket_id: NM-CS-2026-885490 | shopper inquiry before checkout | "
            "Asking whether NovaMart Essentials Tailored Wool Coat (SKU: NM-APP-3301) fits true to size over a heavy sweater "
            "and whether expedited gift-wrapping is available for Thursday delivery."
        ),
        "ground_truth": {
            "queue": "general_support",
            "priority": "P3_LOW",
            "auto_action": "route_specialist",
            "contains_pii": False,
        },
    },
    {
        "id": "sku-04",
        "sub_task": "sku_tagging",
        "title": "Ceramic 4-Pack Espresso Cup Set (Fragile Handling Flag)",
        "payload": (
            "sku_ingestion_id: ING-HOME-2026-209114 | title: 'CraftKiln Matte Stoneware Ceramic Espresso Cups Set of 4 (90ml)' | "
            "material: High-fired Stoneware Ceramic | box_label_ocr: '100% Stoneware Ceramic, Dishwasher & Microwave Safe, Fragile Handle With Care' | "
            "no batteries, no contradictions, requires fragile corrugated drop-pack routing."
        ),
        "ground_truth": {
            "leaf_category": "home_ceramic_dinnerware",
            "compliance_status": "APPROVED_AUTO_PUBLISH",
            "contradiction_detected": False,
        },
    },
    {
        "id": "sku-05",
        "sub_task": "sku_tagging",
        "title": "Portable Bluetooth Speaker w/ 5,200mAh Li-Ion (UN38.3 Attached)",
        "payload": (
            "sku_ingestion_id: ING-AUD-2026-308215 | title: 'SoundPulse Go 30W Waterproof Bluetooth Speaker' | "
            "battery: 5200mAh 3.7V (19.24Wh) Lithium-Ion declared | un38_3_cert: ATTACHED_VERIFIED_2026 | "
            "fcc_id: 2A9SP-GO30 | all spec claims match label OCR."
        ),
        "ground_truth": {
            "leaf_category": "audio_bluetooth_speakers",
            "compliance_status": "APPROVED_AUTO_PUBLISH",
            "contradiction_detected": False,
        },
    },
    {
        "id": "sku-06",
        "sub_task": "sku_tagging",
        "title": "Commercial Induction Hotplate Missing UL/BIS Voltage Rating",
        "payload": (
            "sku_ingestion_id: ING-KIT-2026-511908 | title: 'TurboChef 3500W Commercial Countertop Grinder & Induction Prep Station' | "
            "spec_sheet: 3500W heavy-duty motor, voltage rating omitted from feed and rating plate photo blurry, UL/BIS certificate field empty. "
            "Must hold until voltage & safety certificate verified."
        ),
        "ground_truth": {
            "leaf_category": "kitchen_espresso_grinders",
            "compliance_status": "HOLD_MISSING_CERT",
            "contradiction_detected": False,
        },
    },
]
