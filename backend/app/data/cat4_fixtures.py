"""India-authentic Wholesale Supplier Deal-Room Corpus & Audit Packs for Category 4.

Company: Deccan Smart Appliances & Energy Pvt. Ltd.
CIN: U29300KA2019PTC128441 | GSTIN: 29AABCD8841M1Z5 | Udyam MSE (Medium Excluded; Priority-45d Contractual)
Supplies private-label HEPA-14 IoT Air Purifiers & 1,200 Wh LFP Portable Power Stations
across NovaMart Fulfillment Centers: FC-BLR-01, FC-BOM-02, FC-HYD-01, FC-DEL-03.
"""

from __future__ import annotations

from typing import Any

DEAL_ROOM_PROFILE: dict[str, Any] = {
    "deal_room_id": "DR-NM-DECCAN-2026-Q4",
    "supplier_legal_name": "Deccan Smart Appliances & Energy Pvt. Ltd.",
    "cin": "U29300KA2019PTC128441",
    "gstin": "29AABCD8841M1Z5",
    "headquarters": "Peenya Industrial Estate Phase II, Bengaluru, Karnataka 560058",
    "skus_in_scope": [
        "NM-LFP-1200W (NovaVolt 1,200 Wh LiFePO4 Portable Power Station)",
        "NM-AIR-H14 (NovaPure Smart HEPA-14 Wi-Fi Air Purifier)",
    ],
    "annual_projected_gmv_inr": "INR 118.50 Crore (~$14.20M USD)",
    "fulfillment_hubs": ["FC-BLR-01 (Bengaluru)", "FC-BOM-02 (Bhiwandi)", "FC-HYD-01 (Hyderabad)", "FC-DEL-03 (Gurugram)"],
    "deal_room_status": "Pre-Sign-Off Legal, Tax, Statutory & Safety Due Diligence",
}

SUPPLIER_DEAL_ROOM_DOCS: list[dict[str, Any]] = [
    {
        "doc_id": "DOC-01",
        "doc_code": "MSA-NM-DSA-2026",
        "title": "Master Wholesale Supply & Private-Label Agreement",
        "doc_type": "Core Master Agreement",
        "effective_date": "2026-04-01",
        "summary": "Core commercial supply terms, T+43 MSMED-safe principal settlement, baseline 96.5% OTIF SLA, INR 4.50 Cr aggregate liability cap with carve-outs, 24-month LFP exclusivity, and Change-of-Control termination rights.",
        "chunks": [
            {
                "chunk_id": "DOC-01#c01",
                "clause_ref": "Clauses 1–3 (Scope, MSMED 45-Day Settlement & Early-Pay CD)",
                "section_heading": "Principal Supply Scope, Invoice Settlement Cycle & Statutory MSMED Compliance",
                "keywords": [
                    "MSMED", "Section 43B(h)", "Section 15", "T+43", "45 days", "GRN",
                    "early settlement", "cash discount", "1.75%", "T+10", "Udyam", "payment terms",
                ],
                "text": (
                    "CLAUSE 1 (DEFINITIONS & COMMERCIAL SCOPE): This Master Wholesale Supply Agreement (MSA-NM-DSA-2026), executed on April 1, 2026 between NovaMart Commerce India Pvt. Ltd. ('NovaMart') and Deccan Smart Appliances & Energy Pvt. Ltd., CIN U29300KA2019PTC128441 ('Supplier' or 'Deccan'), governs the engineering, private-label OEM manufacturing, and wholesale delivery of NovaVolt 1,200 Wh LiFePO4 Portable Power Stations (SKU NM-LFP-1200W, HSN 85076000) and NovaPure Smart HEPA-14 IoT Air Purifiers (SKU NM-AIR-H14, HSN 84213990) into NovaMart fulfillment centers FC-BLR-01, FC-BOM-02, FC-HYD-01, and FC-DEL-03.\n\n"
                    "CLAUSE 2 (PURCHASE ORDERS, QC RECEIVING & FORECAST BANDS): NovaMart issues binding electronic Purchase Orders via SAP Ariba/EDI 850 referencing landed DDP (Delivered Duty Paid inside FC dock) INR transfer prices inclusive of primary insurance and factory transit packaging. Rolling 90-day volume forecasts are non-binding planning signals except to the extent of confirmed 30-day firm PO schedules. Upon dock arrival at FC-BLR-01, FC-BOM-02, FC-HYD-01, or FC-DEL-03, NovaMart QA performs AQL Level II 1.0 physical barcoding, BIS R-number laser check, and carton drop inspection within 24 hours; defective-on-arrival ('DOA') lots exceeding 0.80% trigger lot-level RTV (Return-to-Vendor) pickup within 5 business days at Deccan's expense. All commercial invoices must quote valid HSN codes, NIC e-Invoice IRN, and SAP PO line-item references.\n\n"
                    "CLAUSE 3 (PAYMENT TERMS, MSMED SECTION 15 & INCOME TAX SECTION 43B(h) SAFE HARBOR): Although Deccan transitioned above Small Enterprise turnover thresholds during FY 2025-26, Deccan's Peenya PCB and BMS sub-tier cluster operates under Udyam registration covenants requiring strict adherence to statutory payment discipline. Accordingly, NovaMart shall settle 100% of undisputed Base Invoice Principal (pre-GST taxable value) on Net T+43 calendar days measured strictly from the physical Goods Receipt Note ('GRN') timestamp at the destination NovaMart FC, maintaining a 2-day buffer inside the mandatory 45-day ceiling under Section 15 of the MSMED Act, 2006 and preserving NovaMart's corporate tax deduction under Section 43B(h) of the Income Tax Act, 1961. Undisputed delays beyond Day 45 accrue compound statutory interest at three times the RBI Bank Rate notified under Section 16 of the MSMED Act. At NovaMart's sole treasury election, invoices settled electronically via NEFT/RTGS within T+10 calendar days of GRN earn a flat 1.75% Early-Settlement Cash Discount ('CD') deducted from net remittance, automatically posted via SAP clearing document."
                ),
            },
            {
                "chunk_id": "DOC-01#c02",
                "clause_ref": "Clauses 4–6 (Baseline OTIF SLA, Force Majeure & 24-Mo Exclusivity)",
                "section_heading": "Baseline Fulfillment SLA, Standard Force Majeure & Private-Label Exclusivity",
                "keywords": [
                    "OTIF", "96.5%", "0.5%", "2.0%", "cap", "force majeure", "24 hours",
                    "exclusivity", "24 months", "1200 Wh", "LFP", "baseline SLA", "penalty",
                ],
                "text": (
                    "CLAUSE 4 (BASELINE FULFILLMENT SERVICE LEVEL & LIQUIDATED DAMAGES): Outside designated Festive Peak Windows governed by Addendum A (SLA-PEAK-2026), Deccan shall maintain a minimum monthly On-Time-In-Full ('OTIF') fill rate of 96.5% measured across confirmed PO quantities delivered within assigned FC dock appointment slots. Deliveries arriving later than +/- 120 minutes during non-peak windows are rescheduled to the next available yard slot at zero demurrage to NovaMart. For any calendar month in which Deccan's verified OTIF falls below 96.5%, NovaMart may assess baseline Liquidated Damages equal to 0.50% of affected PO landed value for each full percentage point shortfall below 96.5%, subject to an overall baseline monthly SLA penalty cap of 2.0% of total monthly invoiced PO value. ASN (Advance Shipment Notice) telemetry must transmit >= 12 hours prior to vehicle gate-in with e-Way Bill Part-B vehicle details.\n\n"
                    "CLAUSE 5 (BASELINE EXCLUSIVITY, SPARE PARTS & INTELLECTUAL PROPERTY): In consideration of NovaMart's INR 3.80 Crore joint mold tooling advance and front-page marketplace merchandising commitment, Clause 5.4 grants NovaMart exclusive online and omnichannel retail distribution rights across India for the custom industrial design, battery BMS thermal enclosure, and app firmware bundle of SKU NM-LFP-1200W (1,200 Wh LFP Portable Power Station) for an initial period of twenty-four (24) consecutive months commencing April 1, 2026 ('Exclusivity Period'). Deccan shall not manufacture, white-label, or supply functionally identical 1,000–1,400 Wh LFP enclosures to competing Indian horizontal or quick-commerce marketplaces during the Exclusivity Period, unless expressly amended by a signed Side Letter, and must stock spare HEPA-14 cartridges and BMS boards for 36 months post-discontinuation.\n\n"
                    "CLAUSE 6 (STANDARD FORCE MAJEURE): Neither party is liable for baseline fulfillment delays directly caused by Acts of God, declared earthquakes, cyclone red alerts, nationwide rail/highway closures ordered by central government authorities, or regional common-carrier transport blockades lasting longer than twenty-four (24) consecutive hours, provided the affected party notifies the other within 12 hours of onset and mitigates using alternate routes. Economic price inflation, lithium carbonate spot-price volatility, or component vendor backorders do not constitute Force Majeure."
                ),
            },
            {
                "chunk_id": "DOC-01#c03",
                "clause_ref": "Clauses 7–9 (Indemnification & Clause 9.2 INR 4.50 Cr Liability Cap)",
                "section_heading": "IP Indemnification, Clause 9.2 Aggregate Liability Cap & Explicit Schedule Carve-Outs",
                "keywords": [
                    "Clause 9.2", "liability cap", "INR 4,50,00,000", "4.50 Crore", "12 months",
                    "GMV", "carve-out", "uncapped", "DPDP", "BIS", "recall", "GST", "Schedule B", "Schedule C", "Schedule D",
                ],
                "text": (
                    "CLAUSE 7 (THIRD-PARTY IP, QUALITY REJECTION & PRODUCT CONFORMITY INDEMNITY): Deccan shall defend, indemnify, and hold harmless NovaMart, its directors, fulfillment operators, and marketplace affiliates against all third-party patent, copyright, or trademark infringement claims arising from Deccan's BMS firmware, industrial casing, or HEPA filtration sub-assemblies, and against consumer statutory claims under the Consumer Protection Act, 2019 (including e-Commerce Rules 2020 product-seller liability) resulting from manufacturing defects or deceptive energy-efficiency claims.\n\n"
                    "CLAUSE 8 (CONSEQUENTIAL DAMAGES WAIVER & DEFENSE COOPERATION): Except for the uncapped obligations enumerated in Clause 9.2(b) and willful abandonment during a Festive Peak Window, neither party shall be liable to the other for remote indirect loss of goodwill or speculative lost future profits arising solely from routine commercial order cancellations. NovaMart retains the right to assume joint defense control with counsel of its choosing whenever any third-party statutory claim names NovaMart directly as marketplace intermediary.\n\n"
                    "CLAUSE 9 (AGGREGATE LIABILITY CAP & MANDATORY STATUTORY CARVE-OUTS): \n"
                    "9.1 General Cap: Subject strictly to Clause 9.2, each party's cumulative aggregate contractual liability arising out of or in connection with this Agreement during any twelve (12) consecutive calendar months shall not exceed the GREATER OF (a) INR 4,50,00,000 (Rupees Four Crore Fifty Lakh Only), OR (b) 100% of net GMV wholesale payouts invoiced by NovaMart to Deccan during the trailing twelve (12) months immediately preceding the first claim event.\n"
                    "9.2 Uncapped Express Carve-Outs: Nothing in Clause 9.1 or Clause 8 limits, caps, or restricts Deccan's full financial liability, direct indemnity, or statutory reimbursement obligations with respect to: (i) any unauthorized cross-border telemetry exposure, IoT customer data breach, or statutory penalty under Schedule B (DPDP Act 2023 & CERT-In Addendum, DPA-DPDP-2026); (ii) any BIS CRS non-conformity, UN 3480 hazmat shipping violation, bodily injury, property fire damage, or mandatory 48-hour nationwide recall under Schedule C (REG-BIS-EPR-2026); or (iii) fraudulent tax invoicing, blocked Input Tax Credit under CGST Section 16(2)(c)/Section 74, or unreimbursed tax assessments under Schedule D (TAX-GST-ITC-2026)."
                ),
            },
            {
                "chunk_id": "DOC-01#c04",
                "clause_ref": "Clauses 10–12 (Term, Clause 11.4 Change-of-Control & Arbitration)",
                "section_heading": "Term, Clause 11.4 Change-of-Control Termination & Bengaluru Arbitration",
                "keywords": [
                    "Clause 11.4", "Change of Control", "Change-of-Control", "25%", "equity",
                    "termination", "90 days", "arbitration", "Bengaluru", "SIAC", "1996",
                ],
                "text": (
                    "CLAUSE 10 (INITIAL TERM, RENEWAL & CONVENIENCE EXIT): This Agreement remains effective for three (3) years from the Effective Date and renews automatically for successive 12-month terms unless non-renewal notice issues 60 days ahead. Either party may terminate for convenience without cause upon delivering ninety (90) calendar days prior written notice, provided all confirmed Purchase Orders issued prior to the notice date are fulfilled and MSMED-compliant principal settlements plus pro-rata warranty reserves are completed.\n\n"
                    "CLAUSE 11 (TERMINATION FOR CAUSE & CLAUSE 11.4 CHANGE-OF-CONTROL TRIGGER): \n"
                    "11.1 Material Breach & Insolvency: NovaMart may terminate immediately if Deccan fails to cure a material operational or statutory breach within fifteen (15) days of written notice (or zero cure period for willful safety or GST fraud), or upon IBC Section 7/9 insolvency admission or ROC strike-off proceedings.\n"
                    "11.4 Change-of-Control & Foreign Strategic Investment Gate: Deccan shall notify NovaMart in writing at least thirty (30) days prior to closing any merger, slump sale, board voting-control shift, or primary/secondary equity issuance transferring 25.0% or more of Deccan's fully diluted voting share capital or conferring affirmative investor veto rights over key supply decisions to any domestic competitor or foreign strategic entity. Absent NovaMart's express written waiver prior to closing, any such >= 25% Change-of-Control or strategic equity transfer entitles NovaMart to terminate this Agreement immediately upon notice and claw back unamortized INR 3.80 Cr tooling advances on a straight-line pro-rata basis.\n\n"
                    "CLAUSE 12 (GOVERNING LAW, ANTI-BRIBERY & BENGALURU ARBITRATION): Both parties warrant full compliance with the Prevention of Corruption Act, 1988. Governed exclusively by the laws of the Republic of India. Courts at Bengaluru, Karnataka hold exclusive supervisory jurisdiction. Unresolved disputes exceeding 30 days of CXO escalation shall be finally resolved by a tribunal of three (3) arbitrators seated in Bengaluru under the Arbitration and Conciliation Act, 1996 (administered per SIAC procedural rules if cross-border parties join), conducted in English."
                ),
            },
        ],
    },
    {
        "doc_id": "DOC-02",
        "doc_code": "SLA-PEAK-2026",
        "title": "Addendum A — Diwali & Festive Peak Fulfillment SLA Override",
        "doc_type": "Binding SLA Addendum",
        "effective_date": "2026-09-15",
        "summary": "Overrides MSA Clauses 4 & 6 during Oct 10–Nov 15 Diwali Peak: enforces 98.8% OTIF, 4,500-unit buffer staging, INR 1,250/pallet-hr + 3.5% deduction lifting penalty cap from 2.0% to 6.5%, and narrows Force Majeure threshold from 24h to >=72h.",
        "chunks": [
            {
                "chunk_id": "DOC-02#c01",
                "clause_ref": "Clause A.1 (Order of Precedence & Diwali Peak Window)",
                "section_heading": "Festive Peak Precedence Override & Designated Fulfillment Corridors",
                "keywords": [
                    "Addendum A", "SLA-PEAK-2026", "precedence", "supersedes", "Diwali",
                    "Oct 10", "Nov 15", "FC-BLR-01", "FC-BOM-02", "Festive Peak",
                ],
                "text": (
                    "CLAUSE A.1 (ORDER OF PRECEDENCE OVER MSA CLAUSES 4 & 6): This Addendum A (SLA-PEAK-2026) constitutes an integral binding schedule to MSA-NM-DSA-2026 and applies automatically without requiring annual re-execution across all Peak Event PO series. During the designated 'Festive Peak Window' spanning October 10, 2026 through November 15, 2026 (inclusive of NovaMart Great Diwali Festival Event Waves 1 and 2, Dhanteras Prime Lighting Blitz, plus any 7-day Republic Day Mega Sale declared with 45 days advance written notice), the heightened operational standards, tiered liquidated damages, buffer-stock covenants, and narrowed Force Majeure exclusions set forth in Clauses A.2 through A.5 expressly OVERRIDE and supersede baseline Clauses 4 and 6 of the MSA. All Addendum A metrics apply strictly to priority ingestion hubs FC-BLR-01 (Bengaluru) and FC-BOM-02 (Bhiwandi) as well as northern fulfillment spoke FC-DEL-03 and southern spoke FC-HYD-01, while baseline 96.5% SLA terms resume automatically at 00:00 IST on November 16, 2026 for all standard replenishment POs."
                ),
            },
            {
                "chunk_id": "DOC-02#c02",
                "clause_ref": "Clauses A.2–A.3 (98.8% Peak OTIF & 4,500-Unit Buffer Staging)",
                "section_heading": "Elevated 98.8% Peak OTIF, 30-Min Dock Tolerance & Pre-Positioned Safety Stock",
                "keywords": [
                    "98.8%", "OTIF", "30 min", "ASN", "48 hours", "safety stock",
                    "4,500", "Oct 5", "replenishment", "Peak SLA",
                ],
                "text": (
                    "CLAUSE A.2 (ELEVATED 98.8% PEAK OTIF & DOCK SLOT PRECISION): During any Festive Peak Window, Deccan's minimum mandatory On-Time-In-Full ('OTIF') threshold escalates from the MSA baseline of 96.5% to 98.8%, calculated weekly (Monday 00:00 IST through Sunday 23:59 IST) rather than monthly, with zero carry-over credit from non-peak weeks. Every inbound linehaul truck arriving at FC-BLR-01 or FC-BOM-02 must check in within +/- 30 minutes of its booked WMS dock slot and carry verified GS1-128 SSCC pallet barcode manifests synchronized via EDI 856 at least 24 hours before arrival; un-manifested pallets are turned away at security gate.\n\n"
                    "CLAUSE A.3 (PRE-EVENT BUFFER STAGING & 48-HOUR REPLENISHMENT SLA): No later than October 5, 2026 (five days prior to Festive Peak launch), Deccan must pre-position dedicated ring-fenced safety stock of 4,500 finished units of SKU NM-LFP-1200W and 9,000 units of SKU NM-AIR-H14 split 55%/45% across Peenya (Bengaluru) and Bhiwandi bonded regional staging hubs, enabling emergency milk-run replenishment into NovaMart FCs within 48 hours of flash-sale depletion alerts. NovaMart Category Planning receives daily automated ERP inventory-feed snapshots confirming zero cross-allocation of buffer lots to competing marketplaces."
                ),
            },
            {
                "chunk_id": "DOC-02#c03",
                "clause_ref": "Clause A.4 (INR 1,250/Pallet-Hr & 6.5% Peak Penalty Cap)",
                "section_heading": "Peak Liquidated Damages Escalator: INR 1,250/Pallet-Hr, 3.5% Flash Cut & 6.5% Cap",
                "keywords": [
                    "1,250", "pallet-hour", "3.5%", "6.5%", "penalty cap", "2.0%",
                    "flash sale", "liquidated damages", "credit note", "Peak PO",
                ],
                "text": (
                    "CLAUSE A.4 (PEAK LIQUIDATED DAMAGES ESCALATOR — SUPERSEDING 2.0% MSA CAP): Recognizing that stockouts during Diwali Flash-Sale Hero Slots cause irreversible customer acquisition and paid-search ad-spend loss, shortfalls during the Festive Peak Window trigger tiered remedies replacing baseline Clause 4.2:\n"
                    "(a) Dock Detention & Late Linehaul Fee: Inbound deliveries missing the +/- 30-minute WMS dock window or arriving short-shipped incur INR 1,250 per delayed pallet-hour (billed in 60-minute increments per stalled bay allocation, regardless of carrier fault unless excused beyond 72 hours under Clause A.5).\n"
                    "(b) Instant Flash-Sale Unfulfilled Deduction: Where short-delivery or late replenishment forces NovaMart to delist a promoted Hero Deal homepage slot, Deccan incurs an instant 3.50% commercial invoice deduction on the unfulfilled PO tranche.\n"
                    "(c) Elevated Aggregate Peak Cap: Combined dock fees and fill-rate deductions under Clause A.4 are capped at 6.50% of total Festive Peak PO landed value (explicitly overriding the baseline 2.0% monthly cap in MSA Clause 4), settleable directly via automated GST Credit Note adjustment after weekly variance reconciliation."
                ),
            },
            {
                "chunk_id": "DOC-02#c04",
                "clause_ref": "Clause A.5 (Narrowed Force Majeure: <72h Strikes Excluded)",
                "section_heading": "Narrowed Peak Force Majeure Exclusion (<72 Hours State Strikes Not Excused)",
                "keywords": [
                    "Clause A.5", "force majeure", "72", "consecutive hours", "bandh",
                    "transporter strike", "backup fleet", "24 hours", "Festive Peak",
                ],
                "text": (
                    "CLAUSE A.5 (NARROWED PEAK FORCE MAJEURE EXCLUSION — SUPERSEDING 24-HOUR BASELINE): Expressly overriding MSA Clause 6, during any Festive Peak Window regional or state-level commercial transporter strikes, local highway bandhs, municipal octroi/green-tax checkpoints, smog truck-entry curbs in NCR, or Nhava Sheva / Chennai port congestion lasting FEWER THAN seventy-two (72) consecutive hours do NOT qualify as an excused Force Majeure event for Deccan. To invoke Force Majeure even beyond 72 hours, Deccan must contemporaneously demonstrate that it activated at least two pre-contracted dedicated third-party closed-body container fleets (with live FASTag & GPS waybills shared to NovaMart Control Tower) along alternative National Highway corridors within 8 hours of route blockage and exhausted all pre-staged Peenya/Bhiwandi buffer units."
                ),
            },
        ],
    },
    {
        "doc_id": "DOC-03",
        "doc_code": "DPA-DPDP-2026",
        "title": "Schedule B — DPDP Act 2023 & CERT-In Smart-Appliance IoT DPA",
        "doc_type": "Data Privacy & Security Schedule",
        "effective_date": "2026-04-01",
        "summary": "Governs IoT Wi-Fi telemetry under India's DPDP Act 2023: mandates strict AWS ap-south-1/ap-south-2 localization, prohibits foreign shareholder telemetry mirroring, imposes 4-hour CERT-In & 72-hour DPB breach SLA, and carves out uncapped liability up to INR 250 Cr statutory ceiling.",
        "chunks": [
            {
                "chunk_id": "DOC-03#c01",
                "clause_ref": "Clause B.1 (DPDP Act 2023 Roles & IoT Telemetry Scope)",
                "section_heading": "Data Fiduciary / Processor Designation & Smart-Appliance Telemetry Inventory",
                "keywords": [
                    "DPDP Act 2023", "Data Fiduciary", "Data Processor", "IoT", "Wi-Fi",
                    "telemetry", "MAC address", "smart purifier", "warranty registration", "consent",
                ],
                "text": (
                    "CLAUSE B.1 (STATUTORY ROLES UNDER DPDP ACT, 2023 & TELEMETRY INVENTORY): Schedule B (DPA-DPDP-2026) governs all processing of Digital Personal Data generated through NovaMart customer warranty activation, mobile app Bluetooth/Wi-Fi onboarding, indoor PM2.5 air-quality schedules, geofenced home-automation triggers, and BMS battery health logs transmitted by SKUs NM-AIR-H14 and NM-LFP-1200W. Under the Digital Personal Data Protection Act, 2023 ('DPDP Act'), NovaMart acts strictly as Data Fiduciary determining purpose and lawful itemised consent notices (Section 6), and Deccan acts strictly as Data Processor (Section 8(2)). Deccan shall process personal identifiers (customer mobile SHA-256 hash, device MAC/UUID, static/dynamic home IP, GPS city-level pairing metadata, and OTA diagnostic crash dumps) solely upon documented instructions from NovaMart, maintain immutable RBAC audit logs retained for 180 days per CERT-In Directions, and honor automated erasure or Consent Manager revocation webhooks within 48 hours of Data Principal withdrawal."
                ),
            },
            {
                "chunk_id": "DOC-03#c02",
                "clause_ref": "Clause B.2 (AWS Mumbai/Hyderabad Localization & Zero Foreign Mirroring)",
                "section_heading": "India-Only Cloud Residency (ap-south-1 / ap-south-2) & Sub-Processor Gate",
                "keywords": [
                    "localization", "ap-south-1", "Mumbai", "ap-south-2", "Hyderabad",
                    "cross-border", "KMS", "foreign", "shareholder", "mirroring", "KroneVolt", "telemetry",
                ],
                "text": (
                    "CLAUSE B.2 (INDIA DATA RESIDENCY, CMK ENCRYPTION & ZERO FOREIGN DIAGNOSTIC MIRRORING): \n"
                    "(a) Strict India Cloud Localization: Deccan shall ingest, store, and process 100% of raw IoT customer telemetry, paired mobile identifiers, MQTT broker message queues, and TLS session logs exclusively within AWS Asia Pacific ap-south-1 (Mumbai) and disaster-recovery failover region ap-south-2 (Hyderabad), encrypted at rest using NovaMart Customer-Managed Keys ('CMK' via AWS KMS with 90-day automatic key rotation) and TLS 1.3 in transit, with strict AWS SCP guardrails blocking cross-region S3 replication or EBS snapshot sharing.\n"
                    "(b) Cross-Border & Shareholder Access Prohibition: Under no circumstances shall Deccan replicate, stream, export, or expose un-anonymized Indian customer personal data, MAC/IP telemetry, or live OTA diagnostic streams to servers outside India—nor grant remote engineering console, bastion, or observability access to any offshore parent, minority equity investor, joint-venture partner, or foreign strategic shareholder (including European or Asian engineering teams)—without NovaMart's prior written CISO & DPO authorization and formal Standard Contractual Safeguards under Section 16 of the DPDP Act.\n"
                    "(c) Quarterly VAPT & SOC-2 Attestation: Deccan must submit independent CERT-In empanelled auditor Vulnerability Assessment & Penetration Testing ('VAPT') clearance certificates every 180 days covering mobile firmware, BLE pairing handshakes, and cloud API gateways."
                ),
            },
            {
                "chunk_id": "DOC-03#c03",
                "clause_ref": "Clause B.3 (4-Hour CERT-In Readiness & 72-Hour DPB Notification)",
                "section_heading": "Dual Breach Notification SLA: 4-Hr CERT-In Pre-Packet, 24-Hr Rotation & 72-Hr DPB",
                "keywords": [
                    "CERT-In", "4 hours", "6 hours", "6-hour", "72 hours", "DPB",
                    "Data Protection Board", "breach", "notification", "24 hours", "rotation",
                ],
                "text": (
                    "CLAUSE B.3 (STATUTORY INCIDENT & BREACH NOTIFICATION PROTOCOL): \n"
                    "(a) 4-Hour CERT-In Feeder Window: Because Section 70B CERT-In Directions (No. 20(3)/2022-CERT-In dated April 28, 2022) require covered entities to report specified cybersecurity incidents (unauthorized access, cloud data exfiltration, IoT firmware tampering, DoS/DDoS, or MQTT broker compromise) within six (6) hours of noticing or being brought to notice, Deccan MUST escalate a preliminary machine-readable incident packet (affected device cohorts, IOC hashes, CloudTrail/VPC logs, and containment status) to NovaMart SOC within four (4) consecutive hours of detection 24x7x365 using NTP-synchronized IST server clocks.\n"
                    "(b) 24-Hour Secret Rotation & 72-Hour DPDP Board Packet: Within twenty-four (24) hours, Deccan shall revoke all compromised X.509 MQTT certificates, MQTT broker credentials, and signing keys. Within seventy-two (72) hours, Deccan shall deliver a complete forensic root-cause dossier enabling NovaMart to file formal Data Protection Board of India ('DPB') and affected Data Principal breach notifications without delay."
                ),
            },
            {
                "chunk_id": "DOC-03#c04",
                "clause_ref": "Clause B.4 (Uncapped DPDP Indemnity up to INR 250 Cr Ceiling)",
                "section_heading": "Schedule B Uncapped Breach Indemnity & INR 250 Crore Statutory Risk Exposure",
                "keywords": [
                    "Clause B.4", "uncapped", "250 Crore", "INR 250", "DPDP", "penalty",
                    "carve-out", "4.50", "forensic", "Schedule B",
                ],
                "text": (
                    "CLAUSE B.4 (UNCAPPED BREACH INDEMNITY & STATUTORY PENALTY PASS-THROUGH): Expressly cross-referencing Clause 9.2(b)(i) of the MSA, Deccan's aggregate contractual liability cap of INR 4,50,00,000 (INR 4.50 Crore) does NOT apply to breaches of Schedule B (DPA-DPDP-2026). Deccan unconditionally indemnifies NovaMart for 100% of administrative monetary penalties imposed by the Data Protection Board of India (which carry statutory maximums up to INR 250 Crore under the Schedule to the DPDP Act, 2023 for failure to maintain reasonable security safeguards to prevent personal data breaches, and up to INR 200 Crore for failure to notify DPB/Data Principals), together with CERT-In forensic audit fees, regulatory defense costs, statutory Section 43A/Section 70B orders under the Information Technology Act, 2000, and free credit/device security remediation provided to affected NovaMart shoppers. Cyber-risk insurance of INR 15.00 Crore minimum must cover IoT telemetry incidents."
                ),
            },
        ],
    },
    {
        "doc_id": "DOC-04",
        "doc_code": "REG-BIS-EPR-2026",
        "title": "Schedule C — BIS CRS, CPCB EPR & Lithium-Ion Hazmat Safety Exhibit",
        "doc_type": "Statutory Safety & Regulatory Schedule",
        "effective_date": "2026-04-01",
        "summary": "Mandates BIS CRS IS 16046/IS 302 registration, tracks CPCB EPR certificate EPR-KA-2025-08814 expiring 2026-12-31 (auto-delist Dec 15 if unrenewed by Dec 10), bans Air Express for >100 Wh UN 3480 LFP packs (surface only <=30% SoC), and mandates 48h recall + INR 25 Cr insurance.",
        "chunks": [
            {
                "chunk_id": "DOC-04#c01",
                "clause_ref": "Clause C.1 (BIS CRS IS 16046 / IS 302 Compliance & NABL Labs)",
                "section_heading": "Mandatory BIS Compulsory Registration Scheme (CRS) & Test Reports",
                "keywords": [
                    "BIS", "CRS", "IS 16046", "IS 302", "R-41209877", "NABL",
                    "MeitY", "Standard Mark", "certification", "lab report",
                ],
                "text": (
                    "CLAUSE C.1 (MANDATORY BIS COMPULSORY REGISTRATION SCHEME COMPLIANCE): Under the Electronics and Information Technology Goods (Requirement for Compulsory Registration) Order, 2021 notified by MeitY/BIS, every unit of SKU NM-LFP-1200W (cell chemistry governed under IS 16046 (Part 2): 2018 / IEC 62133-2 under active BIS CRS Registration No. R-41209877, factory code Peenya-Unit-2) and SKU NM-AIR-H14 (IS 302 (Part 1) & EMI/EMC household appliance safety) delivered to NovaMart must carry authentic embossed/lasered BIS Standard Mark R-numbers matching serial batch manifests and QR-linked model codes. Deccan must upload valid NABL-accredited Indian laboratory renewal and annual BIS surveillance factory-inspection reports to NovaMart's Compliance Vault at least 15 days prior to SKU launch and immediately upon any battery cell vendor, electrolyte, or BMS MOSFET Bill-of-Materials engineering change notice; unapproved cell substitutions entitle NovaMart to reject entire container lots at gate."
                ),
            },
            {
                "chunk_id": "DOC-04#c02",
                "clause_ref": "Clause C.2 (CPCB EPR Certificate Expiring Dec 31, 2026 & Dec 15 Auto-Delist)",
                "section_heading": "CPCB EPR Registration EPR-KA-2025-08814 Expiry & Automatic Catalog Delisting Gate",
                "keywords": [
                    "CPCB", "EPR", "EPR-KA-2025-08814", "2026-12-31", "2026-12-10", "Dec 10",
                    "2026-12-15", "Dec 15", "delist", "delisting", "Battery Waste", "E-Waste",
                ],
                "text": (
                    "CLAUSE C.2 (CPCB EXTENDED PRODUCER RESPONSIBILITY — BATTERY & E-WASTE COVENANTS): Pursuant to the Battery Waste Management Rules, 2022 and E-Waste (Management) Rules, 2022 (as amended through 2024) issued by the Central Pollution Control Board ('CPCB'), Deccan represents that it holds active Producer Registration Certificate EPR-KA-2025-08814, which currently carries a statutory validity expiry date of December 31, 2026 across Li-ion battery packs and Category ITEW/CEEW appliances. Deccan covenants to maintain registered PRO recycler tie-ups covering 100% of FY27 collection targets and submit verified CPCB centralized portal renewal confirmation plus quarterly Form-3 recycling credit certificates for FY 2026-27 to NovaMart Seller Compliance Ops NO LATER THAN December 10, 2026 (21 days prior to expiry). If renewed FY27 EPR credentials are not verified on NovaMart's portal by 18:00 IST on December 10, 2026, NovaMart is expressly authorized to automatically delist, suppress Buy-Box visibility, and inventory-freeze all Deccan battery and appliance ASINs effective December 15, 2026 without penalty, notice period, or breach liability."
                ),
            },
            {
                "chunk_id": "DOC-04#c03",
                "clause_ref": "Clause C.3 (UN 3480 Class 9 Air Express Ban & <=30% SoC Surface Linehaul)",
                "section_heading": "Lithium-Ion Dangerous Goods Transport: Air Express Ban & 30% SoC Surface Protocol",
                "keywords": [
                    "UN 3480", "UN 38.3", "Class 9", "Air Express", "prohibition", "100 Wh",
                    "1200 Wh", "30%", "SoC", "State of Charge", "surface", "CMVR", "hazmat",
                ],
                "text": (
                    "CLAUSE C.3 (UN 3480 CLASS 9 LITHIUM-ION DANGEROUS GOODS TRANSPORT PROTOCOL): Because SKU NM-LFP-1200W contains a 1,200 Wh lithium-iron-phosphate battery pack—exceeding the 100 Wh civil aviation / IATA PI 965 cargo exception threshold by 12x—it is strictly classified as UN 3480 Class 9 Miscellaneous Dangerous Goods.\n"
                    "(a) Absolute Air Express Prohibition: Deccan is STRICTLY PROHIBITED from tendering, booking, relabeling, or cross-docking SKU NM-LFP-1200W on any NovaMart Air Express, domestic belly-cargo flight, or priority air-courier manifest across BlueDart Air, Delhivery Air, or Indiamart Express; misdeclaration triggers immediate INR 5,00,000 per-consignment liquidated indemnity plus DGCA reporting.\n"
                    "(b) Mandatory <=30% SoC Surface Hazmat Linehaul: All factory dispatches and inter-FC transfers (e.g., Peenya Bengaluru to FC-DEL-03 Gurugram) must travel exclusively via DG-certified surface linehaul complying with Central Motor Vehicles Rules (CMVR) Rule 137 TREM Card emergency markings, with every pack factory-discharged to a verified State-of-Charge ('SoC') <= 30%, packed in UN-specification 4G flame-retardant fiberboard cartons with Class 9 Lithium Hazard Labels, and accompanied by a valid UN 38.3 Lithium Battery Test Summary attached to the GST e-Way Bill."
                ),
            },
            {
                "chunk_id": "DOC-04#c04",
                "clause_ref": "Clause C.4 (48-Hour Nationwide Recall & INR 25 Cr Product Liability Cover)",
                "section_heading": "Uncapped 48-Hour Thermal Recall Obligations & INR 25 Crore CGL Insurance",
                "keywords": [
                    "recall", "48 hours", "48-hour", "uncapped", "INR 25", "25.00 Cr",
                    "insurance", "CGL", "thermal runaway", "bodily injury", "Clause 9.2",
                ],
                "text": (
                    "CLAUSE C.4 (48-HOUR MANDATORY SAFETY RECALL & INR 25 CRORE LIABILITY INSURANCE): Upon any field thermal event, cell venting anomaly, BIS surveillance sample failure, or Central Consumer Protection Authority ('CCPA') safety recall directive affecting Deccan SKUs, Deccan shall initiate and pre-fund a 100% supplier-funded nationwide customer outreach, SMS/app push advisory, and Class-9 hazmat reverse-logistics pickup program within forty-eight (48) hours of escalation. Expressly carved out from the MSA Clause 9.1 cap per Clause 9.2(b)(ii), Deccan bears uncapped liability for full customer refunds, warehouse hazardous-disposal fees, FC rack remediation, bodily injury, and property fire damage claims. Deccan shall continuously maintain Commercial General & Product Liability (including Mandatory Recall Expense Extension and Cross-Liability Endorsement) insurance of at least INR 25,00,00,000 (Rupees Twenty-Five Crore) per occurrence with an IRDAI-licensed insurer naming NovaMart Commerce India Pvt. Ltd. as Additional Insured & Loss Payee, with 30 days non-cancellation undertaking."
                ),
            },
        ],
    },
    {
        "doc_id": "DOC-05",
        "doc_code": "TAX-GST-ITC-2026",
        "title": "Schedule D — CGST Section 16(2)(aa) ITC & MSMED Principal Escrow Rider",
        "doc_type": "Tax & Input Credit Compliance Schedule",
        "effective_date": "2026-04-01",
        "summary": "Enforces NIC IRP e-Invoicing, GSTR-1 by 11th / GSTR-3B by 20th; preserves MSMED 45-day / Sec 43B(h) compliance by paying 100% pre-tax principal at T+43 while holding only 18% GST in escrow until GSTR-2B match (180-day / Rule 37A cure or permanent debit + 18% p.a. interest).",
        "chunks": [
            {
                "chunk_id": "DOC-05#c01",
                "clause_ref": "Clause D.1 (NIC IRP e-Invoice, GSTR-1 by 11th & GSTR-3B by 20th)",
                "section_heading": "CGST Section 16(2)(aa) Invoice Reporting & Auto-Drafted GSTR-2B Discipline",
                "keywords": [
                    "GSTR-1", "GSTR-2B", "GSTR-3B", "CGST", "Section 16(2)(aa)", "11th", "20th",
                    "IRN", "e-Invoice", "NIC IRP", "Input Tax Credit", "ITC",
                ],
                "text": (
                    "CLAUSE D.1 (MANDATORY E-INVOICING & MONTHLY GST FILING CADENCE): Under Section 16(2)(aa) of the Central Goods and Services Tax Act, 2017 ('CGST Act'), NovaMart cannot legally avail Input Tax Credit ('ITC') unless supplier tax invoices appear intact in NovaMart's auto-drafted monthly Form GSTR-2B statement without supplier filing defaults or Section 16(2)(ba) restricted flags. Deccan shall generate real-time Invoice Reference Numbers ('IRN') and signed QR codes on the NIC Invoice Registration Portal ('IRP') prior to dispatch from Peenya, attach validated e-Way Bills matching transporter LR numbers, file error-free Form GSTR-1 strictly by the 11th calendar day of the month succeeding dispatch, and discharge full output tax liability in cash/credit via Form GSTR-3B strictly by the 20th calendar day of that month across GSTIN 29AABCD8841M1Z5. Weekly SAP GST reconciliation alerts flag mismatches automatically within 48 hours."
                ),
            },
            {
                "chunk_id": "DOC-05#c02",
                "clause_ref": "Clause D.2 (100% Principal Released T+43 vs. 18% GST Escrow Holdback)",
                "section_heading": "Split-Remittance Design: Safeguarding MSMED 45-Day & Section 43B(h) Principal Payment",
                "keywords": [
                    "holdback", "escrow", "18%", "principal", "T+43", "45-day", "43B(h)",
                    "MSMED", "GSTR-2B", "mismatch", "split remittance", "tax component",
                ],
                "text": (
                    "CLAUSE D.2 (SPLIT-REMITTANCE DESIGN: MSMED-SAFE PRINCIPAL RELEASE + GST TAX ESCROW HOLDBACK): To protect NovaMart against CGST Section 16(2)(aa) ITC disallowance notices WITHOUT triggering statutory late-payment compound interest under MSMED Act Section 15/16 or corporate income-tax expenditure disallowance under Section 43B(h) of the Income Tax Act, 1961, NovaMart operates a bifurcated SAP ERP payment rail whenever a Deccan tax invoice is missing or mismatched in NovaMart's monthly GSTR-2B pull:\n"
                    "(a) Protected Principal Release: NovaMart STILL releases 100% of the undisputed pre-tax base principal invoice value on schedule by T+43 days from GRN, keeping underlying goods principal settlement strictly inside the 45-day statutory MSMED/43B(h) safe harbor.\n"
                    "(b) Targeted 18% Tax Escrow Holdback: NovaMart withholds ONLY the 18% GST tax component (CGST 9% + SGST 9% on intra-Karnataka Peenya-to-FC-BLR-01 supplies, or IGST 18% on inter-state dispatches to FC-BOM-02/FC-HYD-01/FC-DEL-03) in a non-interest-bearing 'Tax Compliance Escrow Holdback Account' until Deccan's invoice populates cleanly in NovaMart's verified GSTR-2B without Section 16(2)(c) supplier-default flags."
                ),
            },
            {
                "chunk_id": "DOC-05#c03",
                "clause_ref": "Clause D.3 (Rule 37A / 180-Day Cure Window & 18% p.a. Debit Conversion)",
                "section_heading": "180-Day / Sept 30 Rule 37A Cure Deadline & Permanent Commercial Setoff",
                "keywords": [
                    "Rule 37A", "180 days", "Sept 30", "September 30", "cure", "debit note",
                    "18% p.a.", "interest", "setoff", "escrow release",
                ],
                "text": (
                    "CLAUSE D.3 (GSTR-2B CURE WINDOW, CGST RULE 37A DEADLINE & PERMANENT CONVERSION): Escrow holdbacks resolved via timely GSTR-1 IFF/monthly amendment or Form DRC-03 tax deposit populate on NovaMart's next GSTR-2B pull and release automatically on the following Friday AP payment run with zero administrative deduction. However, Deccan is granted a strict maximum cure window ending on the EARLIER of (i) 180 calendar days from the original tax invoice date, OR (ii) September 30 following the close of the relevant Financial Year (aligning with mandatory buyer ITC reversal mandates under CGST Rule 37A and the Section 16(4) statutory cutoff prior to November 30 annual return deadlines). If Deccan fails to cure GSTR-1 and remit GSTR-3B within this cure deadline, the escrowed 18% GST balance converts permanently into a non-refundable commercial debit note deducted against Deccan's vendor ledger, together with statutory interest recovery at 18% per annum under CGST Section 50(3) and any Section 73/74 departmental penalty assessed against NovaMart."
                ),
            },
            {
                "chunk_id": "DOC-05#c04",
                "clause_ref": "Clause D.4 (HSN 85076000 Lock & Uncapped Tax Fraud Indemnity)",
                "section_heading": "Uncapped Section 16(2)(c) / Section 74 GST Indemnity & Verified HSN Classification",
                "keywords": [
                    "85076000", "84213990", "HSN", "18%", "Section 16(2)(c)", "Section 74",
                    "uncapped", "anti-profiteering", "Schedule D", "fake ITC",
                ],
                "text": (
                    "CLAUSE D.4 (HSN CLASSIFICATION LOCK & UNCAPPED TAX INDEMNITY): Invoices must uniformly apply HSN 85076000 (18% GST) for SKU NM-LFP-1200W Li-ion LFP storage packs and HSN 84213990 (18% GST) for SKU NM-AIR-H14 purifiers, verified quarterly by independent GST tax sign-off; any supplier HSN misclassification or rate discrepancy resulting in short-levy demands under CGST Section 73/74 or loss of B2B customer ITC is borne 100% by Deccan. Additionally, under CGST Section 171 anti-profiteering covenants, any statutory GST rate reduction must be passed immediately into landed DDP transfer pricing via amended PO schedules. Per MSA Clause 9.2(b)(iii), Deccan's obligation to indemnify NovaMart against ITC disallowances under CGST Section 16(2)(c) (supplier non-remittance of tax collected) or Section 74 fraud proceedings is expressly UNCAPPED and survives contract expiration for eight (8) years covering the full statutory GST audit and reassessment limitation period."
                ),
            },
        ],
    },
    {
        "doc_id": "DOC-06",
        "doc_code": "MCA-AOC4-FY26",
        "title": "Statutory Auditor's Extract — MCA Form AOC-4, CARO 2020 & Charge Register (FY 2025–26)",
        "doc_type": "Statutory Financial & Audit Disclosure",
        "effective_date": "2026-08-28",
        "summary": "Audited FY26 MCA AOC-4 extract: Revenue INR 312.40 Cr (+24.8% YoY), EBITDA INR 28.60 Cr, Net Worth INR 74.10 Cr, DSCR 1.62x; discloses CARO Clause (vii)(b) disputed MH GST claim INR 6.85 Cr (10% pre-deposit INR 0.685 Cr paid) and SBI Form CHG-1 INR 45 Cr facility requiring SBI NOC for >25% CoC.",
        "chunks": [
            {
                "chunk_id": "DOC-06#c01",
                "clause_ref": "Note 14 (MCA Form AOC-4 FY 2025–26 Financial Results)",
                "section_heading": "Audited Standalone Income Statement & Balance Sheet Key Metrics (FY26)",
                "keywords": [
                    "AOC-4", "Form AOC-4", "MCA", "FY 2025-26", "312.40", "EBITDA", "28.60",
                    "9.15%", "PAT", "14.90", "Net Worth", "74.10", "Current Ratio", "1.48x", "revenue",
                ],
                "text": (
                    "NOTE 14 (AUDITED FINANCIALS — MCA FORM AOC-4, FY ENDED MARCH 31, 2026, SIGNED AUGUST 28, 2026 BY K. RAGHAVAN & ASSOCIATES LLP): Deccan Smart Appliances & Energy Pvt. Ltd. filed its audited standalone financial statements under Schedule III Division I in MCA e-Form AOC-4 (SRN AB9920411) pursuant to Section 137 of the Companies Act, 2013:\n"
                    "- Revenue from Operations: INR 312.40 Crore in FY 2025-26 vs. INR 250.32 Crore in FY 2024-25 (+24.80% YoY, driven 62% by LFP portable storage and 38% by smart purifiers).\n"
                    "- Operating EBITDA: INR 28.60 Crore (9.15% EBITDA margin, up +85 bps YoY following Peenya SMT BMS assembly automation).\n"
                    "- Profit After Tax (PAT): INR 14.90 Crore (4.77% net margin); Operating Cash Flow INR 21.30 Crore.\n"
                    "- Shareholders' Net Worth: INR 74.10 Crore (Paid-up Equity INR 12.50 Cr + Free Reserves INR 61.60 Cr); Total Borrowings INR 38.40 Crore (Net Debt/EBITDA 0.89x; Unencumbered Cash & Liquid FD Balances INR 12.90 Crore; Current Ratio 1.48x; Trade Receivable Days 54d). Statutory Auditors issued an UNMODIFIED (clean) audit opinion with emphasis strictly on standard contingent disclosures in Note 18 and CARO Clause (vii)(b)."
                ),
            },
            {
                "chunk_id": "DOC-06#c02",
                "clause_ref": "CARO 2020 Clause (vii)(b) (INR 6.85 Cr Disputed MH GST Notice)",
                "section_heading": "CARO 2020 Statutory Dues Dispute: Maharashtra GST INR 6.85 Cr Appeal & 10% Pre-Deposit",
                "keywords": [
                    "CARO 2020", "vii(b)", "disputed statutory dues", "6.85", "INR 6.85 Cr",
                    "Maharashtra GST", "0.685", "10%", "pre-deposit", "Section 73", "Section 74", "GSTAT",
                ],
                "text": (
                    "CARO 2020 CLAUSE (vii)(b) DISCLOSURE (DISPUTED STATUTORY DUES NOT DEPOSITED ON ACCOUNT OF DISPUTE): Pursuant to Paragraph 3(vii)(b) of the Companies (Auditor's Report) Order, 2020 ('CARO 2020') annexed to the Independent Auditor's Report, the Statutory Auditors confirm that undisputed Provident Fund (EPFO), ESIC, Income Tax TDS, Customs Duty, and routine monthly GST filings were regularly deposited with appropriate authorities with zero >6-month arrears, EXCEPT for one disputed indirect tax demand currently under formal statutory appeal:\n"
                    "- Authority & Order: Office of the Joint Commissioner of State Tax (Maharashtra GST, Mazgaon Division), Order-in-Original dated November 19, 2025 relating to FY 2022-23 imported BMS integrated-circuit and LFP pouch cell IGST transition credits examined under Section 73(9) credit documentation review.\n"
                    "- Disputed Gross Amount: INR 6.85 Crore (comprising INR 4.60 Cr tax principal + applicable statutory interest & 10% general penalty — non-fraud classification confirmed after withdrawal of initial Section 74 allegations).\n"
                    "- Mandatory Pre-Deposit & Status: Deccan remitted the mandatory 10% statutory pre-deposit of INR 0.685 Crore (INR 68.50 Lakh) in electronic cash ledger under Section 107(6) CGST/MGST Act, securing automatic statutory stay of balance recovery (INR 6.165 Cr) pending adjudication before the GST Appellate Tribunal ('GSTAT'), Mumbai Bench. Treated strictly as an off-balance-sheet contingent liability (not accrued in P&L) backed by external Big-4 tax counsel written opinion estimating >= 75% success probability on merits."
                ),
            },
            {
                "chunk_id": "DOC-06#c03",
                "clause_ref": "Note 18 & Form CHG-1 (SBI INR 45 Cr Working Capital Charge & CoC NOC)",
                "section_heading": "MCA Charge Register (Form CHG-1): SBI Hypothecation Covenants & Change-of-Control NOC",
                "keywords": [
                    "CHG-1", "Form CHG-1", "100884129", "SBI", "State Bank of India",
                    "45.00 Cr", "45 Cr", "DSCR", "1.40x", "1.62x", "NOC", "hypothecation", "covenant",
                ],
                "text": (
                    "NOTE 18 & MCA REGISTER OF CHARGES (FORM CHG-1 — CHARGE ID 100884129): Working capital facilities totaling INR 45.00 Crore (INR 35.00 Cr Fund-Based Cash Credit/WCDL + INR 10.00 Cr Non-Fund-Based Inland Letter of Credit / Bank Guarantee sub-limit) sanctioned by State Bank of India ('SBI'), Mid-Corporate Branch Bengaluru via Sanction Letter dated January 18, 2026, are secured by a first-ranking pari passu hypothecation charge (registered in MCA Form CHG-1, Charge ID 100884129, active as of March 31, 2026 with zero overdue installments or SMA-0/1/2 flags) over all current assets, raw LFP cell inventories, work-in-progress, and trade receivables of Deccan, plus equitable mortgage over Peenya industrial leasehold plot #44.\n"
                    "Financial & Negative Covenants: SBI sanction terms require (a) Minimum Debt-Service Coverage Ratio ('DSCR') >= 1.40x and TOL/TNW <= 1.75x (Deccan FY 2025-26 audited DSCR = 1.62x and TOL/TNW = 1.12x, comfortably compliant; CC utilization as of March 31, 2026 = INR 27.20 Cr of INR 45.00 Cr limit), and (b) Negative Covenant Clause 14.3 strictly prohibiting any equity allotment exceeding 25.0% dilution, board control modification, or foreign strategic stake entry WITHOUT prior written No-Objection Certificate ('NOC') from SBI."
                ),
            },
            {
                "chunk_id": "DOC-06#c04",
                "clause_ref": "Note 21 (Q2 FY26 Thermal-Cutoff Retrofit & INR 2.85 Cr Reserve)",
                "section_heading": "Product Warranty Provisioning, Proactive Field Retrofit & Zero Safety Claims",
                "keywords": [
                    "Note 21", "warranty", "retrofit", "3,100", "1.42 Cr", "2.85 Cr",
                    "thermal cutoff", "provision", "Gen-1", "safety",
                ],
                "text": (
                    "NOTE 21 (PROVISIONS FOR PRODUCT WARRANTY & PROACTIVE FIELD RETROFIT): Opening warranty provision on April 1, 2025 stood at INR 2.15 Crore; fresh prudent additions of INR 2.12 Crore were charged to Cost of Goods Sold during FY 2025-26 against INR 1.42 Crore actual service utilization, leaving a closing Warranty Reserve of INR 2.85 Crore as of March 31, 2026 (~0.91% of revenue, independently validated by actuarial failure-curve modeling). Utilization of INR 1.42 Crore reflects a strictly voluntary Q2 FY26 preventive service bulletin executed proactively across 3,100 early Gen-1 domestic inverter packs in Karnataka and Maharashtra to upgrade redundant secondary thermal-cutoff fuses and potting sealant ahead of peak summer ambient temperatures. Note 21 explicitly confirms ZERO thermal runaway incidents, ZERO BIS show-cause or non-conformity notices, and ZERO personal injury or third-party warehouse property claims arising prior to audit sign-off."
                ),
            },
        ],
    },
    {
        "doc_id": "DOC-07",
        "doc_code": "SL-2026-09",
        "title": "Side Letter #2 — KroneVolt 26% Equity Waiver, Exclusivity Carve-Out & Rebate Cap",
        "doc_type": "Executed Side Letter Amendment",
        "effective_date": "2026-09-24",
        "summary": "Waives MSA Clause 11.4 termination for KroneVolt GmbH's 26.0% Series-C stake subject to SBI Form CHG-1 NOC + Schedule B zero foreign IoT mirroring; cuts 24-mo exclusivity to 9 months unless NovaMart orders >= INR 85 Cr by 2027-09-30; caps annual rebate clawbacks at 3.25%.",
        "chunks": [
            {
                "chunk_id": "DOC-07#c01",
                "clause_ref": "Clause SL.1 (KroneVolt GmbH 26% Stake CoC Waiver & Dual Conditions)",
                "section_heading": "Conditional Change-of-Control Waiver for KroneVolt GmbH (Germany) 26% Series-C Round",
                "keywords": [
                    "KroneVolt", "GmbH", "26%", "26.0%", "Series-C", "Change-of-Control",
                    "waiver", "Clause 11.4", "SBI", "NOC", "Schedule B", "IoT", "telemetry",
                ],
                "text": (
                    "CLAUSE SL.1 (CONDITIONAL CHANGE-OF-CONTROL WAIVER FOR KRONEVOLT GMBH INVESTMENT): Executed September 24, 2026 by authorized signatories of NovaMart and Deccan, this Side Letter #2 (SL-2026-09) directly modifies MSA Clause 11.4 solely with respect to Deccan's proposed Series-C primary investment (INR 65.00 Crore fresh growth capital) in which KroneVolt Energy Systems GmbH (Munich, Germany) will subscribe for 26.0% of Deccan's post-money fully diluted voting equity alongside one non-executive investor director seat.\n"
                    "NovaMart conditionally WAIVES its immediate termination and INR 3.80 Cr tooling-clawback rights under MSA Clause 11.4 arising solely from the 26.0% KroneVolt transaction, STRICTLY CONTINGENT ON two continuing Conditions Precedent prior to share allotment:\n"
                    "(1) Banking Covenant Clearance: Deccan must deliver a certified copy of State Bank of India's written No-Objection Certificate ('NOC') satisfying SBI's Negative Covenant Clause 14.3 under MCA Form CHG-1 Charge ID 100884129 at least 5 business days before share allotment (so SBI working capital lines remain uninterrupted); and\n"
                    "(2) Absolute Telemetry Firewall: Neither KroneVolt GmbH, its Munich R&D engineers, nor its nominee director shall receive API keys, bulk telemetry exports, or remote SSH access to Indian customer IoT data or AWS ap-south-1/ap-south-2 KMS realms, maintaining strict compliance with Schedule B (Clause B.2)."
                ),
            },
            {
                "chunk_id": "DOC-07#c02",
                "clause_ref": "Clause SL.2 (Exclusivity Cut from 24 Mo to 9 Mo Below INR 85 Cr POs)",
                "section_heading": "Conditional Reduction of LFP Private-Label Exclusivity (24 Mo -> 9 Mo Threshold)",
                "keywords": [
                    "SL.2", "exclusivity", "24 months", "9 months", "INR 85", "85.00 Crore",
                    "2027-09-30", "Sept 30 2027", "binding PO", "LFP",
                ],
                "text": (
                    "CLAUSE SL.2 (AMENDMENT OF MSA CLAUSE 5.4 — CONDITIONAL REDUCTION OF LFP EXCLUSIVITY): Expressly overriding the unconditional 24-month Exclusivity Period set forth in MSA Clause 5.4, the parties agree that NovaMart's private-label exclusivity for SKU NM-LFP-1200W (1,200 Wh LFP Portable Power Station) SHALL AUTOMATICALLY EXPIRE AT NINE (9) MONTHS (effective December 31, 2026) UNLESS NovaMart issues cumulative binding, non-cancellable Purchase Orders aggregating at least INR 85.00 Crore (Rupees Eighty-Five Crore landed value, net of GST) across Deccan SKUs prior to 23:59 IST on September 30, 2027 (with at least INR 42.00 Crore ordered in the initial 9-month milestone ending December 31, 2026). If NovaMart fails to meet either the INR 42.00 Cr interim gate or INR 85.00 Crore cumulative hurdle, Deccan becomes free to supply unbranded 1,200 Wh LFP OEM variants to competing horizontal/quick-commerce marketplaces without refunding unamortized tooling advances, while keeping SKU NM-AIR-H14 firmware proprietary."
                ),
            },
            {
                "chunk_id": "DOC-07#c03",
                "clause_ref": "Clause SL.3 (Volume Rebate Tiers & 3.25% Promotional Clawback Cap)",
                "section_heading": "Commercial Economics: Annual Volume Rebates vs. 3.25% Rebate & Clawback Ceiling",
                "keywords": [
                    "SL.3", "rebate", "clawback", "3.25%", "50 Cr", "85 Cr", "120 Cr",
                    "1.5%", "2.75%", "3.5%", "margin", "promotional",
                ],
                "text": (
                    "CLAUSE SL.3 (BACK-END VOLUME REBATES & 3.25% CLAWBACK CEILING): In connection with KroneVolt's incoming institutional board governance and working-capital debt-coverage covenants, annual back-end volume growth rebates payable by Deccan to NovaMart apply on a strictly progressive annual net-purchase ladder reconciled within 30 days after March 31 fiscal close: 1.50% upon crossing INR 50.00 Crore, 2.75% upon crossing INR 85.00 Crore, and 3.50% upon crossing INR 120.00 Crore in cumulative annual net invoiced PO value (settled via CGST Section 34 commercial/tax credit notes). Provided further that aggregate annual promotional co-op fees, catalog banner charges, marketing deductions, and volume rebate clawbacks claimed by NovaMart against Deccan (EXPRESSLY EXCLUDING punitive Peak SLA liquidated damages assessed under Addendum A Clause A.4 and GST escrow/debit adjustments under Schedule D) shall NEVER exceed a hard contractual ceiling of 3.25% of Deccan's realized annual net wholesale purchases."
                ),
            },
            {
                "chunk_id": "DOC-07#c04",
                "clause_ref": "Clause SL.4 (Precedence Hierarchy Over MSA vs. Intact Schedules)",
                "section_heading": "Contractual Order of Precedence Across MSA, Addendum A & Schedules B–D",
                "keywords": [
                    "SL.4", "order of precedence", "prevails", "hierarchy", "Addendum A",
                    "Schedules B", "survival", "conflict",
                ],
                "text": (
                    "CLAUSE SL.4 (CONTRACTUAL PRECEDENCE, SURVIVAL & COUNTERPARTS): In the event of any conflict or ambiguity across deal-room instruments: (1) On matters of KroneVolt 26% Change-of-Control consent, LFP 9-month/24-month exclusivity thresholds, and the 3.25% annual rebate/clawback ceiling, Side Letter #2 (SL-2026-09) strictly PREVAILS over MSA-NM-DSA-2026; (2) On Festive Peak fulfillment SLA (98.8% OTIF, 4,500-unit staging, INR 1,250/pallet-hr fee, 6.5% cap, <72h Force Majeure exclusion), Addendum A (SLA-PEAK-2026) strictly prevails over the MSA; and (3) Schedules B (DPA-DPDP-2026), C (REG-BIS-EPR-2026), and D (TAX-GST-ITC-2026) remain completely untouched and fully enforceable alongside Clause 9.2 uncapped carve-outs. Expiry or non-fulfillment of the INR 85.00 Cr exclusivity hurdle under Clause SL.2 shall never impair NovaMart's uncapped indemnification, 48-hour recall rights, or 8-year GST audit survival."
                ),
            },
        ],
    },
]


def build_doc_full_text(doc: dict[str, Any]) -> str:
    """Build deterministic full plain-text representation of one document for DocumentBlock & UI viewer."""
    parts = []
    for chunk in doc["chunks"]:
        parts.append(f"[{chunk['chunk_id']} · {chunk['clause_ref']}]\n{chunk['text']}")
    return "\n\n".join(parts)


def hydrate_deal_room_index() -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Return (hydrated_docs, flat_chunks_with_doc_offsets, total_corpus_chars)."""
    hydrated_docs: list[dict[str, Any]] = []
    flat_chunks: list[dict[str, Any]] = []
    total_chars = 0

    for doc_idx, doc in enumerate(SUPPLIER_DEAL_ROOM_DOCS):
        full_parts: list[str] = []
        cursor = 0
        doc_chunks_out: list[dict[str, Any]] = []
        for c_idx, ch in enumerate(doc["chunks"]):
            header_prefix = f"[{ch['chunk_id']} · {ch['clause_ref']}]\n"
            block_str = header_prefix + ch["text"]
            doc_char_start = cursor
            doc_char_end = cursor + len(block_str)
            chunk_rec = {
                **ch,
                "doc_index": doc_idx,
                "doc_id": doc["doc_id"],
                "doc_code": doc["doc_code"],
                "doc_title": doc["title"],
                "doc_type": doc["doc_type"],
                "doc_char_start": doc_char_start,
                "doc_char_end": doc_char_end,
                "header_len": len(header_prefix),
                "full_block_text": block_str,
                "char_count": len(block_str),
                "approx_tokens": max(1, round(len(block_str) / 2.6)),
            }
            doc_chunks_out.append(chunk_rec)
            flat_chunks.append(chunk_rec)
            full_parts.append(block_str)
            cursor = doc_char_end + (2 if c_idx < len(doc["chunks"]) - 1 else 0)

        full_text = "\n\n".join(full_parts)
        total_chars += len(full_text)
        hydrated_docs.append(
            {
                "doc_index": doc_idx,
                "doc_id": doc["doc_id"],
                "doc_code": doc["doc_code"],
                "title": doc["title"],
                "doc_type": doc["doc_type"],
                "effective_date": doc["effective_date"],
                "summary": doc["summary"],
                "block_title": f"{doc['doc_id']} :: {doc['doc_code']} — {doc['title']}",
                "block_context": (
                    f"{doc['doc_type']} (Effective {doc['effective_date']}) for supplier "
                    f"{DEAL_ROOM_PROFILE['supplier_legal_name']}"
                ),
                "full_text": full_text,
                "char_count": len(full_text),
                "approx_tokens": max(1, round(len(full_text) / 2.6)),
                "chunks": doc_chunks_out,
            }
        )

    return hydrated_docs, flat_chunks, total_chars


CAT4_PRESETS: list[dict[str, Any]] = [
    {
        "id": "audit-01",
        "use_case": "supplier_msa_due_diligence",
        "title": "Audit Pack 1: General Counsel Legal, Privacy & Contract Override Risk",
        "subtitle": "4 cross-document questions testing Clause 9.2 uncapped carve-outs, Diwali Peak SLA overrides, KroneVolt 26% stake conditions & DPDP/CERT-In localization",
        "reviewer_role": "Deputy General Counsel & CISO",
        "suggested_custom_queries": [
            "If an LFP battery shipment causes a warehouse fire during Diwali after a 48-hour highway bandh, what liability caps, recall timelines, and Force Majeure rules apply?",
            "Can Deccan's new German investor KroneVolt GmbH inspect live Indian customer Wi-Fi diagnostic logs during warranty debugging?",
        ],
        "questions": [
            {
                "question_id": "q1",
                "question_number": 1,
                "topic_tag": "Liability Cap & Carve-Outs",
                "question": (
                    "What is Deccan's general contractual liability cap under MSA Clause 9.1, and which "
                    "three statutory schedules are explicitly carved out as UNCAPPED under Clause 9.2 (including "
                    "exact INR ceilings and required insurance limits)?"
                ),
                "expected_doc_ids": ["DOC-01", "DOC-03", "DOC-04", "DOC-05"],
                "expected_chunk_ids": ["DOC-01#c03", "DOC-03#c04", "DOC-04#c04", "DOC-05#c04"],
            },
            {
                "question_id": "q2",
                "question_number": 2,
                "topic_tag": "Diwali Peak SLA & Force Majeure",
                "question": (
                    "During the Oct 10 – Nov 15 Diwali Festive Peak Window, how does Addendum A override baseline "
                    "MSA Clauses 4 and 6 on mandatory OTIF, liquidated damages, penalty cap %, and regional highway "
                    "transporter strikes lasting under 72 hours?"
                ),
                "expected_doc_ids": ["DOC-01", "DOC-02"],
                "expected_chunk_ids": ["DOC-01#c02", "DOC-02#c02", "DOC-02#c03", "DOC-02#c04"],
            },
            {
                "question_id": "q3",
                "question_number": 3,
                "topic_tag": "KroneVolt 26% Equity & Exclusivity",
                "question": (
                    "Does KroneVolt GmbH's proposed 26.0% Series-C equity stake allow NovaMart to terminate under MSA "
                    "Clause 11.4, what dual Conditions Precedent (including SBI Form CHG-1) bind Side Letter #2 Clause SL.1, "
                    "and how does Clause SL.2 shorten NovaMart's 24-month LFP exclusivity?"
                ),
                "expected_doc_ids": ["DOC-01", "DOC-06", "DOC-07"],
                "expected_chunk_ids": ["DOC-01#c04", "DOC-07#c01", "DOC-07#c02", "DOC-06#c03"],
            },
            {
                "question_id": "q4",
                "question_number": 4,
                "topic_tag": "DPDP Localization & 4-Hr CERT-In SLA",
                "question": (
                    "Under Schedule B (DPDP Act 2023), where must Indian smart-appliance IoT telemetry and KMS keys reside, "
                    "and what are Deccan's exact 4-hour CERT-In feeder, 24-hour key rotation, and 72-hour DPB breach timelines?"
                ),
                "expected_doc_ids": ["DOC-03"],
                "expected_chunk_ids": ["DOC-03#c01", "DOC-03#c02", "DOC-03#c03"],
            },
        ],
    },
    {
        "id": "audit-02",
        "use_case": "supplier_msa_due_diligence",
        "title": "Audit Pack 2: CFO Tax, MSMED, BIS Safety & MCA Statutory Audit",
        "subtitle": "4 multi-doc diligence questions spanning CGST Sec 16(2)(aa) split escrow, MSMED Sec 43B(h), MCA Form AOC-4 / CARO 2020, BIS/EPR/UN3480 & net margin economics",
        "reviewer_role": "VP Finance & Marketplace Risk",
        "suggested_custom_queries": [
            "What happens to Deccan's SKU listings on December 15, 2026 if CPCB EPR renewal isn't uploaded by December 10?",
            "Can NovaMart use Air Express for urgent replenishment of 1,200 Wh LFP power stations from Bengaluru to Delhi?",
        ],
        "questions": [
            {
                "question_id": "q1",
                "question_number": 1,
                "topic_tag": "GSTR-2B Holdback vs MSMED 45-Day Rule",
                "question": (
                    "If a Deccan invoice is missing in NovaMart's GSTR-2B pull, how does Schedule D preserve "
                    "MSMED Act 45-day & Income Tax Section 43B(h) compliance via split remittance, and what are the "
                    "exact Rule 37A 180-day cure deadline and permanent 18% p.a. setoff consequences?"
                ),
                "expected_doc_ids": ["DOC-01", "DOC-05"],
                "expected_chunk_ids": ["DOC-01#c01", "DOC-05#c01", "DOC-05#c02", "DOC-05#c03"],
            },
            {
                "question_id": "q2",
                "question_number": 2,
                "topic_tag": "MCA AOC-4 Solvency, CARO GST & SBI Charge",
                "question": (
                    "Summarize Deccan's FY 2025-26 MCA Form AOC-4 financial health, the CARO 2020 Clause (vii)(b) "
                    "disputed Maharashtra GST demand & pre-deposit, SBI Form CHG-1 Charge ID 100884129 DSCR covenant, "
                    "and Note 21 warranty retrofit reserve."
                ),
                "expected_doc_ids": ["DOC-06"],
                "expected_chunk_ids": ["DOC-06#c01", "DOC-06#c02", "DOC-06#c03", "DOC-06#c04"],
            },
            {
                "question_id": "q3",
                "question_number": 3,
                "topic_tag": "BIS CRS, EPR Expiry & UN 3480 Transport",
                "question": (
                    "Under Schedule C, what BIS CRS standard covers SKU NM-LFP-1200W, when does CPCB certificate "
                    "EPR-KA-2025-08814 expire (and what Dec 10 / Dec 15 auto-delist gates apply), and why is NovaMart "
                    "Air Express banned for UN 3480 LFP dispatches?"
                ),
                "expected_doc_ids": ["DOC-04"],
                "expected_chunk_ids": ["DOC-04#c01", "DOC-04#c02", "DOC-04#c03"],
            },
            {
                "question_id": "q4",
                "question_number": 4,
                "topic_tag": "Cash Discount vs Peak Cap & Rebate Ceiling",
                "question": (
                    "Contrast all commercial price adjustments across the deal room: T+10 Early-Settlement Cash Discount "
                    "(Clause 3), Addendum A Peak SLA penalty cap vs MSA baseline cap, Side Letter #2 INR 85 Cr exclusivity "
                    "hurdle, and the Clause SL.3 3.25% annual rebate clawback ceiling."
                ),
                "expected_doc_ids": ["DOC-01", "DOC-02", "DOC-07"],
                "expected_chunk_ids": ["DOC-01#c01", "DOC-02#c03", "DOC-07#c02", "DOC-07#c03"],
            },
        ],
    },
]
