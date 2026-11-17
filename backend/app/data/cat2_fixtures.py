"""Realistic 3,200–3,700 token NovaMart Enterprise fixtures for Category 2 (Synthesis & Drafting)."""

from __future__ import annotations

from typing import Any

CAT2_REVIEWER_PRESETS: dict[str, dict[str, str]] = {
    "executive_summary": {
        "label": "Tighten <75 words for CFO & Board deck",
        "instruction": (
            "Tighten executive narrative under 75 words for the CFO & Board deck while "
            "preserving exact rupee/dollar exposure and SLA numbers."
        ),
    },
    "key_findings": {
        "label": "Sharpen variance %, root cause & anchors",
        "instruction": (
            "Sharpen each finding around hard variance percentages, root-cause bottleneck "
            "metrics, and exact source timestamps."
        ),
    },
    "risk_and_compliance_matrix": {
        "label": "Escalate statutory & SLA triggers",
        "instruction": (
            "Escalate statutory, financial, and SLA penalty triggers with concrete "
            "containment thresholds per row."
        ),
    },
    "action_plan": {
        "label": "Convert into 24h / 7d / 30d execution gates",
        "instruction": (
            "Convert milestones into strict 24h / 7d / 30d execution gates with "
            "measurable exit criteria."
        ),
    },
}

CAT2_PRESETS: list[dict[str, Any]] = [
    {
        "id": "brief-01",
        "sub_task": "exec_synthesis",
        "title": "Diwali Peak Ops War-Room Transcript & Sortation Backlog",
        "subtitle": "45-min multi-speaker VP transcript · Hub SLA telemetry · Carrier & payments lag",
        "channel": "War-Room Transcript + Hub SLA JSON",
        "approx_tokens": 3660,
        "payload": """=== NOVAMART ENTERPRISE · DIWALI PEAK OPS WAR-ROOM SOURCE BUNDLE ===
meeting_id: NM-WAR-2026-W46-09
date_utc: 2026-11-16T15:30:00Z
participants:
  - Ananya Deshmukh (VP Fulfillment & Linehaul Operations)
  - Rohan Kulkarni (Director, Bhiwandi & Western Hub Sortation)
  - Meera Subramanian (Principal SRE, Checkout & Payments Gateway)
  - Kabir Sethi (Head of 3PL Carrier Contracts & SLA Governance)
  - Divya Nair (VP Seller Support & Marketplace Escalations)
target_deliverable: Executive Operational Readout & Board Action Memo

--- SECTION A: VERBATIM WAR-ROOM TRANSCRIPT (TIMESTAMPS UTC) ---
[15:31:04] Ananya (VP Fulfillment): Team, we closed Diwali Sale Day 3 at $38.4M daily GMV across 612,000 orders, up 34% YoY against our $28.6M baseline plan. Customer demand held strong, especially across Consumer Electronics and Ethnic Apparel, but our regional sortation and payment retry telemetry slipped past Tier-1 thresholds between 09:00Z and 14:00Z. Let's anchor strictly to verified telemetry so the CEO and CFO readout tonight reflects reality without guesswork.

[15:33:19] Rohan (Bhiwandi Hub Director): Starting on the West Zone—Bhiwandi FC-WEST-01 and Thane sortation center absorbed 194,000 parcels in 18 hours against rated induction throughput of 145,000 parcels/day. Three cross-belt diverter jams on Sorter Lane 4 caused by oversized multi-SKU appliances (wet grinders and boxed microwave combos shipped without corrugated strap reinforcement) dropped mechanical availability to 81.4% for 3.5 hours. As of 15:00Z, backlog stands at 41,800 staged cages awaiting linehaul dispatch, putting our 24-hour Assured dispatch SLA at 86.2% versus the 96.5% contractual guarantee. Dankuni East Hub is clean at 97.4%, Hoskote South is tight at 94.1% due to dock crowding, and Tauru North is operating at 95.8%.

[15:36:42] Kabir (3PL Carrier Governance): Those Bhiwandi missed cutoff dispatches triggered late-tender clauses with Delhivery Air and BlueDart Express. Under Schedule B of our Q4 Peak Linehaul Agreement, missing the 13:30Z dock release incurs a flat $1.85 per-parcel surge re-slot surcharge plus forfeits our 12% volume rebate on delayed manifests. That exposes $77,330 in direct carrier surcharges if we do not clear the 41,800 cage backlog before 23:59Z tonight, plus an estimated $142,000 rebate forfeiture risk for Week 46 if Western Zone on-time-tender falls below 92.0%. BlueDart already offered 18 dedicated 32-foot closed-body linehaul trailers staged at Bhiwandi Gate 7 starting 17:00Z at a negotiated flat $14,400 standby fee—far cheaper than eating $219,330 in contractual penalties and Assured late-delivery voucher credits ($5 buyer coupon per missed promise).

[15:40:15] Meera (Payments SRE): Separately, between 10:12Z and 11:48Z, our primary UPI Collect webhook cluster experienced p99 callback latency spikes from 420ms to 4,850ms during the HDFC/ICICI flash-sale peak. Because checkout orchestration retried synchronous status polling with a 3-second client timeout while upstream PSP callbacks arrived at 4.8 seconds, 14,920 checkout attempts landed in "PENDING_RECONCILIATION" state and 3,410 customers saw duplicate authorization holds totaling $318,400 in temporary card/UPI holds. By 11:55Z we switched 70% of UPI volume onto secondary gateway Cashfree-Rail-B and pushed idempotency lease extensions from 3s to 8s. Duplicate auth generation dropped to 0.02% after 12:00Z, and our automated reversal batch already cleared 2,980 of the 3,410 duplicate holds. However, 430 high-value duplicate holds ($61,250 total) still require manual settlement file reconciliation before tomorrow's T+1 banking cutoff.

[15:44:50] Divya (VP Seller Support): Downstream impact hit Seller Support and Buyer Escalations hard: inbound P1 tickets spiked +210% above forecast (11,400 incremental tickets in 6 hours), largely from buyers asking about double holds and Apex Platinum sellers demanding exemption from our automated Late Dispatch Penalty (LDP 1.5% commission surcharge) when Bhiwandi dock queues blocked seller drop-offs. Notice we cannot waive LDP blindly—47 sellers actually submitted zero-inventory phantom manifest scans ("manifested-not-handed-over"), whereas 312 verified sellers waited 4+ hours in physical Gate 3 truck queues at Bhiwandi. Our badge telemetry shows dock-in timestamps so Compliance can isolate genuine carrier/hub queues from seller stockouts.

[15:48:10] Ananya (VP Fulfillment): Let's align on containment budget before presenting to the CFO: approve the $14,400 BlueDart standby fleet immediately, spin up 140 temporary peak sortation loaders on the Bhiwandi night shift ($9,800 incremental overtime), divert non-urgent oversized kitchen appliances from Automated Sorter Lane 4 to manual pallet staging immediately, and enforce dock-timestamp LDP waivers ONLY for the 312 Gate-3-verified sellers while auditing the 47 phantom-manifest accounts. Also factor in potential $94,000 Assured late-delivery buyer credits if backlog age crosses 16 hours.

--- SECTION B: REGIONAL FULFILLMENT & GATEWAY TELEMETRY SNAPSHOT (15:00Z) ---
{
  "sale_day_gmv_usd": 38400000,
  "daily_orders": 612000,
  "yoy_gmv_growth_pct": 34.0,
  "hubs": [
    {"hub_code": "FC-WEST-01 (Bhiwandi)", "rated_daily_cap": 145000, "inbound_volume_18h": 194000, "staged_backlog": 41800, "sla_attainment_pct": 86.2, "target_sla_pct": 96.5, "sorter_avail_pct": 81.4},
    {"hub_code": "FC-EAST-02 (Dankuni)", "rated_daily_cap": 110000, "inbound_volume_18h": 106200, "staged_backlog": 3100, "sla_attainment_pct": 97.4, "target_sla_pct": 96.5, "sorter_avail_pct": 99.1},
    {"hub_code": "FC-SOUTH-01 (Hoskote)", "rated_daily_cap": 135000, "inbound_volume_18h": 132900, "staged_backlog": 7400, "sla_attainment_pct": 94.1, "target_sla_pct": 96.5, "sorter_avail_pct": 96.8},
    {"hub_code": "FC-NORTH-03 (Tauru)", "rated_daily_cap": 120000, "inbound_volume_18h": 118400, "staged_backlog": 4900, "sla_attainment_pct": 95.8, "target_sla_pct": 96.5, "sorter_avail_pct": 98.4}
  ],
  "payments_incident": {
    "window_utc": "10:12Z-11:48Z",
    "p99_webhook_latency_ms": 4850,
    "baseline_p99_ms": 420,
    "pending_reconciliation_count": 14920,
    "duplicate_auth_holds_total": 3410,
    "duplicate_hold_gross_usd": 318400,
    "remaining_manual_holds_count": 430,
    "remaining_manual_holds_usd": 61250
  },
  "financial_exposure_vs_containment": {
    "unmitigated_carrier_surcharge_usd": 77330,
    "weekly_rebate_forfeiture_risk_usd": 142000,
    "projected_assured_voucher_risk_usd": 94000,
    "proposed_containment_spend_usd": 24200,
    "seller_queues_verified_gate3": 312,
    "suspected_phantom_manifest_sellers": 47
  },
  "action_owners_and_cutoffs": {
    "24h_ops_containment": "Deploy 18 BlueDart Gate-7 trailers by 17:00Z + 140 night-shift loaders; route heavy kitchen appliances off Sorter Lane 4 to manual pallet lanes.",
    "24h_payments_recon": "Clear remaining 430 manual duplicate UPI holds ($61,250) prior to 04:00Z T+1 bank settlement batch; keep Cashfree-Rail-B at 70% primary weight.",
    "7d_seller_compliance": "Issue automated Gate-3 timestamp LDP waivers for 312 verified sellers while placing 47 zero-inventory phantom-manifest sellers on mandatory 7-day inventory audit."
  }
}

--- SECTION C: EXECUTIVE BRIEFING & GOVERNANCE RUBRIC ---
- Required Sections: Executive Summary, Quantified Key Findings, Risk & Compliance Matrix, Action Plan (Owned & Time-Bound).
- Target Board Readout Constraints: Reconcile total unmitigated exposure ($313,330 carrier/rebate/voucher + $61,250 un-reversed UPI holds) cleanly against $24,200 immediate containment spend (12.9x gross exposure mitigation ratio). Do not grant blanket seller penalty waivers that mask phantom manifest abuse.""",
    },
    {
        "id": "brief-02",
        "sub_task": "exec_synthesis",
        "title": "AetherSonic Flagship Brand B2B Partnership Proposal Brief",
        "subtitle": "Brand discovery notes · SKU margin rate card · 1-Day Prime lift benchmarks",
        "channel": "Discovery Notes + Commercial Rate Card",
        "approx_tokens": 3590,
        "payload": """=== NOVAMART ENTERPRISE BRAND ONBOARDING · DISCOVERY & COMMERCIAL BUNDLE ===
opportunity_id: NM-B2B-2026-AETHER-04
brand_partner: AetherSonic Acoustics Inc. ($145M annual DTC + retail electronics brand)
category: Premium Audio (Noise-Cancelling Headphones, ANC Earbuds, Portable Bluetooth Speakers)
target_launch_window: Q1 FY2027 (February 15 Go-Live across Top 18 Metro Regions)
stakeholders:
  - Siddharth Rao (NovaMart VP Category Partnerships)
  - Elena Martinez (AetherSonic VP Global E-Commerce & Channels)
  - Tarun Kapoor (NovaMart FBO Supply Chain & Pricing Architect)
  - Nadia Jenkins (AetherSonic CFO / MAP & Margin Controller)

--- SECTION A: DISCOVERY & COMMERCIAL NEGOTIATION NOTES ---
1. Brand Pain Points on Competing Marketplaces:
AetherSonic currently generates $31.2M online marketplace GMV elsewhere, but suffers from three structural leaks: (a) unauthorized grey-market resellers undercutting Minimum Advertised Price (MAP) by 14%–19%, eroding flagship ANC-Pro Over-Ear headphones ($299 MSRP); (b) a 7.8% return/exchange rate driven by poor unboxing damage on high-gloss gift packaging and zero serial-number warranty validation; and (c) slow 4.1-day average transit times outside Tier-1 coastal cities, capping repeat accessories attach rate at 8.4%.

2. NovaMart Assured Brand-Gate Proposal & Exclusivity Lever:
AetherSonic proposes listing 28 active SKUs on NovaMart Enterprise as Official Brand Storefront ONLY if NovaMart enforces SKU-level Brand Gating (blocking 19 known unauthorized grey-market resellers at catalog ingestion), serial-number barcode capture at FBO outbound pack-out, and strict MSRP/MAP automated buy-box lock within +/-0.5% tolerance. In return, AetherSonic commits $18.0M Year-1 annualized inventory allocation including 45-day early launch exclusivity on their upcoming flagship "StudioPulse X2" ($349 MSRP, forecast 32,000 launch-quarter units).

3. Fee Structure, Co-Op Retail Media & Fulfillment Rate Card:
Standard NovaMart Consumer Electronics marketplace referral commission is 11.5%, which AetherSonic's CFO Nadia flagged as 150bps too high given their 44% gross margin and $1.9M co-op marketing spend. Tarun modeled a calibrated Tiered Brand Agreement:
- Reduce core Audio referral commission from 11.5% to 9.75% on verified MAP-compliant brand-direct orders (saving AetherSonic ~$315k/yr at $18M GMV).
- Lock FBO-Assured 1-Day Prime fulfillment fee at flat $3.65/unit for items <=1.2kg (below standard $4.40 FBO schedule) provided AetherSonic pre-positions 65% of safety stock across our 4 regional hubs (Bhiwandi, Dankuni, Hoskote, Tauru).
- AetherSonic commits $480,000/yr minimum Sponsored Search & Homepage Hero Co-Op budget with a guaranteed NovaMart 4.8x ROAS floor (if trailing-60d ROAS drops below 4.2x, NovaMart credits 15% bonus impressions, not cash rebates).
- Damage & Serial Fraud Shield: Mandatory double-walled craft overbox included in the $3.65 FBO tier; NovaMart internal FBO tests on comparable Sony/JBL audio cohorts cut transit crush returns from 7.4% down to 2.1% (-530bps margin recovery worth ~$954,000 annualized GMV retention) and cut counterfeit return swaps by 88% via outbound IMEI/serial scan matching.

4. Open Commercial Conditions & Compliance Gates:
- AetherSonic requires UN38.3 lithium battery transport certifications pre-cleared once at Brand Onboarding rather than per-lot manual holds so launch stock does not stall in hazmat quarantine.
- Payment settlement SLA: AetherSonic requests T+3 net settlement release (versus standard T+7 seller escrow) backed by a $250,000 rolling return reserve for 90 days post-launch. Treasury notes T+3 requires Director approval plus zero unresolved KYC/TIN mismatches.
- Termination trigger: If NovaMart buy-box MAP enforcement suffers >2% unauthorized grey-market leakage over any 14-day audit window, AetherSonic holds a 30-day exclusivity unwind right.

--- SECTION B: COMMERCIAL MODEL & BENCHMARK TELEMETRY JSON ---
{
  "projected_year1_gmv_usd": 18000000,
  "active_sku_count": 28,
  "exclusive_launch_sku": {"name": "StudioPulse X2", "msrp_usd": 349.00, "q1_forecast_units": 32000, "q1_gmv_usd": 11168000},
  "commission_proposal": {
    "standard_ce_commission_pct": 11.50,
    "proposed_brand_commission_pct": 9.75,
    "annual_commission_concession_usd": 315000,
    "guaranteed_coop_ad_spend_usd": 480000,
    "net_novamart_take_rate_incl_ads_pct": 12.42
  },
  "fulfillment_economics": {
    "standard_fbo_per_unit_usd": 4.40,
    "negotiated_fbo_per_unit_usd": 3.65,
    "min_regional_hub_split_pct": 65.0,
    "benchmark_delivery_speed_days": {"current_competitor": 4.1, "novamart_assured_4hub": 1.3},
    "benchmark_return_rate_pct": {"current_competitor": 7.8, "novamart_overbox_cohort": 2.1},
    "projected_annual_return_savings_usd": 954000
  },
  "risk_gates": {
    "grey_market_resellers_to_block": 19,
    "map_leakage_unwind_threshold_pct": 2.0,
    "settlement_tier_requested": "T+3 (vs T+7 standard)",
    "rolling_return_reserve_usd": 250000,
    "un38_3_certs_verified": "26 of 28 SKUs uploaded; 2 pending lab signoff"
  },
  "sku_assortment_and_margin_schedule": [
    {"sku_line": "StudioPulse X2 Flagship ANC (Launch Exclusive)", "msrp_usd": 349.00, "annual_units": 48000, "annual_gmv_usd": 16752000, "proposed_referral_pct": 9.75, "fbo_tier_usd": 3.65},
    {"sku_line": "ANC-Pro Gen 2 Over-Ear", "msrp_usd": 299.00, "annual_units": 21000, "annual_gmv_usd": 6279000, "proposed_referral_pct": 9.75, "fbo_tier_usd": 3.65},
    {"sku_line": "PulsePods Spatial True Wireless", "msrp_usd": 149.00, "annual_units": 36000, "annual_gmv_usd": 5364000, "proposed_referral_pct": 9.75, "fbo_tier_usd": 3.65},
    {"sku_line": "BoomTube Compact IP67 BT Speaker", "msrp_usd": 119.00, "annual_units": 19500, "annual_gmv_usd": 2320500, "proposed_referral_pct": 9.75, "fbo_tier_usd": 3.65}
  ]
}

--- SECTION C: TECHNICAL INTEGRATION & JOINT LAUNCH CHECKLIST (Q1 FY2027) ---
1. Catalog Gate & Brand Authorization Workflow:
NovaMart Catalog Engineering will enroll all 28 AetherSonic UPCs/EANs into Brand Registry Lock by January 10, 2027. Any third-party offer attempting to attach to StudioPulse X2 or ANC-Pro ASINs without a digitally signed AetherSonic Authorized Distributor Token will be auto-rejected at ingestion (0% manual Seller Support override).
2. Outbound Serial Capture & Counterfeit Return Deterrence:
At FBO pick-and-pack stations in Bhiwandi, Dankuni, Hoskote, and Tauru, handheld laser scanners must pair Order ID -> Master Box Serial -> Manufacturer Battery Serial prior to carrier handoff. Reverse logistics return grading will cross-check inbound serial numbers against outbound scan logs; mismatched swaps trigger automatic Buyer Abuse Hold and shield AetherSonic from counterfeit return write-offs.
3. Co-Op Marketing Attribution & Governance Review Cadence:
Quarterly Business Reviews (QBRs) scheduled Day 30, Day 60, and Day 90 post-launch will audit net ROAS against the 4.8x target, monitor 14-day grey-market MAP compliance (<2.0% leakage ceiling), and validate whether rolling 60-day return rates stay at or below 2.5% before stepping down the $250,000 rolling reserve.
4. Target Deliverable Structure:
Synthesize these commercial terms, margin tradeoffs (175bps commission concession + $0.75/unit FBO subsidy vs. $480k guaranteed Co-Op spend + $18M Year-1 exclusive launch allocation), operational safeguards, and contractual closure gates for AetherSonic Executive Sign-Off.""",
    },
    {
        "id": "reg-01",
        "sub_task": "regulatory_filing",
        "title": "Q3 Lithium-Ion Thermal Event & UN38.3 Hazmat Safety Filing",
        "subtitle": "Pune FC Zone-C thermal log · 412-SKU power-bank audit · Statutory CAPA report",
        "channel": "Safety Incident Log + Hazmat Audit",
        "approx_tokens": 3260,
        "payload": """=== NOVAMART MARKETPLACE SAFETY & DGCA/BUREAU COMPLIANCE FILING SOURCE ===
filing_reference: NM-REG-HAZMAT-2026-Q3-018
regulatory_framework: Marketplace Dangerous Goods Air/Surface Transport & Warehouse Fire Safety Rules (UN38.3 / IS 16046 / NFPA 855)
reporting_period: Q3 FY2026 (July 1 – September 30, 2026)
preparing_entity: NovaMart Marketplace Trust, Safety & Fulfillment Compliance Office
target_audience: Marketplace Safety Regulator & Board Audit Committee

--- SECTION A: CONTAINMENT INCIDENT CHRONOLOGY (FC-PUNE-02) ---
incident_id: INC-2026-08-29-PNQ2
facility: Pune Fulfillment Center FC-PUNE-02 (Hazmat Segregation Cage Zone-C, Bay 14)
date_time_ist: 2026-08-29T04:18:00+05:30
event_summary:
At 04:18 IST on August 29, 2026, overhead FLIR thermal cameras in FC-PUNE-02 Zone-C detected an anomalous temperature escalation (47C -> 118C in 9 minutes) inside a sealed seller inbound master carton (Lot ID: INB-88412, 60 units of nominal "20,000mAh FastCharge USB-C Power Bank", Seller: SLR-77401 VoltPeak Trading). Automated smoke/off-gas sensors triggered within 110 seconds. Night-shift ERT isolated the single steel mesh pallet into the external Class-D / aqueous vermiculite containment bath within 4 minutes 20 seconds. Zero human injuries occurred, sprinklers did not need roof discharge beyond Zone-C local misting heads, and main building operations resumed by 08:30 IST. Total physical inventory damaged: 180 units across 3 adjacent pallets ($4,860 wholesale cost); containment remediation cost: $12,400.

post_incident_forensic_findings:
1. Laboratory tear-down by TUV Rhineland India revealed Seller SLR-77401 actually packed unlabeled 26,800mAh / 99.16Wh high-density lithium-polymer pouch cells inside outer shells stamped "10,000mAh / 37Wh" to evade mandatory UN38.3 air-transport dangerous-goods declarations and bypass NovaMart Zone-C cage capacity caps.
2. Seller uploaded a forged BIS IS 16046 safety certificate PDF during April 2026 onboarding whose registration number belonged to an unrelated 5W wall adapter.
3. Furthermore, external shipping box lacked the required UN3480 Lithium-Ion Class 9 diamond hazard label and terminal short-circuit foam separators; crush vibration along highway transit fractured one internal nickel tab, initiating thermal runaway while staged prior to bin put-away.

--- SECTION B: MARKETPLACE-WIDE 412-SKU HAZMAT & SELLER AUDIT RESULTS ---
Following INC-2026-08-29-PNQ2, NovaMart Safety Engineering conducted a 14-day mandatory fleet-wide audit covering all 412 active portable power bank and rechargeable lithium-ion battery SKUs across 118 third-party sellers:
- Verified Compliant SKUs (Valid UN38.3 test summary + active BIS/UL registry cross-check matching exact Wh rating): 334 of 412 SKUs (81.1%).
- Suspended Pending Valid Test Summary / Label Mismatch (missing UN38.3 38.3.4 altitude/thermal/crush sheets or conflicting seller text vs. spec-label Wh): 63 of 412 SKUs (15.3%, $412,000/mo trailing GMV quarantined).
- Permanently Delisted & Seller Accounts Terminated for Falsified Safety Docs or Undeclared >100Wh Cells: 15 SKUs across 4 sellers including SLR-77401 (3.6% of audited catalog; $184,000 escrow frozen for potential statutory liability & buyer recall notices).
- Recall & Buyer Notification Action: Automated proactive SMS + email + in-app safety recall notice dispatched to 1,420 customers who purchased any of the 15 falsified SKUs between May and August 2026, offering prepaid ground hazardous-return kits + 100% instant refund ($58,220 cumulative refund reserve booked; 61.4% buyer response/return completion as of September 30).

--- SECTION C: PREVENTIVE CONTROLS & ENGINEERING CAPA TELEMETRY JSON ---
{
  "incident_metrics": {
    "injuries": 0,
    "ert_isolation_seconds": 260,
    "peak_carton_temp_c": 118,
    "damaged_inventory_usd": 4860,
    "facility_remediation_usd": 12400,
    "buyer_recall_reserve_usd": 58220
  },
  "fleet_audit_412_skus": {
    "compliant_skus": 334,
    "suspended_missing_un38_3_or_ocr_mismatch": 63,
    "permanently_delisted_forged_docs": 15,
    "terminated_sellers": 4,
    "frozen_seller_escrow_usd": 184000,
    "recalled_buyer_units": 1420,
    "recall_completion_pct_sept30": 61.4
  },
  "implemented_controls": {
    "api_registry_cross_check": "Automated real-time lookup against BIS/UL registration IDs replacing manual PDF upload review (deployed 2026-09-10)",
    "cat1_ocr_contradiction_gate": "Computer-vision + Haiku Category 1 SKU gate comparing seller description mAh/Wh claims against physical carton OCR labels before Air-Express eligibility",
    "inbound_xrf_flir_screening": "100% handheld FLIR thermal scan at dock receiving + random 10% carton weight/Wh density verification across top 12 fulfillment hubs",
    "carrier_air_block_policy": "Hard TMS API block preventing >37Wh spare batteries or UN3480 standalone packs from routing onto passenger/belly air manifests"
  },
  "remaining_gaps_and_deadlines": {
    "open_recall_unreturned_units": 548,
    "tier2_regional_spokes_flir_rollout": "10 of 18 Tier-2 sortation spokes pending FLIR handheld cameras (target completion Nov 30, 2026; capex $42,000)"
  },
  "quarterly_surface_vs_air_routing_audit": {
    "blocked_undeclared_air_shipments_sept": 114,
    "average_wh_discrepancy_flagged": "Seller listing stated 37Wh vs lab/carton physical 88.8Wh–99.2Wh (+140%–168% energy density understatement)",
    "insurance_notification_status": "Property insurer notified Sept 2, 2026; zero subrogation claims filed due to immediate ERT containment ($12,400 absorbed in Q3 Safety OpEx)"
  }
}

--- SECTION D: STATUTORY DISCLOSURES & REGULATORY ATTESTATION REQUIREMENTS ---
1. Mandatory Incident Classification & Surface Transport Notification:
Under Marketplace Dangerous Goods Handling Rules and Civil Aviation Circular DGR-2024-R2, INC-2026-08-29-PNQ2 qualifies as a "Declared Facility Thermal Containment Event Involving Misdeclared Seller Lithium-Ion Inventory" with zero personnel exposure, zero external smoke plume, and zero passenger-aircraft Uplift Exposure (intercepted at inbound FC dock prior to carrier handoff).
2. Chain-of-Custody & Law Enforcement Referral:
All remaining 154 intact units of Lot INB-88412 from terminated Seller SLR-77401 (VoltPeak Trading) have been moved to certified hazardous-waste destruction custody under Chain-of-Custody Manifest HAZ-PNQ-9921. NovaMart Legal referred forged BIS Certificate #BIS-R-41009912 evidence to the Bureau of Market Surveillance and Economic Offences Wing on September 18, 2026, while retaining $184,000 in terminated seller escrow accounts to backstop 100% of buyer recall refunds ($58,220 reserve) and third-party forensic testing ($18,500).
3. Continuous Monitoring & Next Audit Checkpoint:
Management commits to closing all 548 open customer recall returns via escalated SMS + IVR follow-ups by November 15, 2026, deploying FLIR handheld imaging across all remaining 10 Tier-2 regional sortation spokes ($42,000 approved capex) by November 30, 2026, and maintaining zero tolerance auto-delisting for any seller attempting UN38.3 / BIS document tampering.""",
    },
    {
        "id": "reg-02",
        "sub_task": "regulatory_filing",
        "title": "FY26 Cross-Border Seller KYC, Tax Escrow & AML Audit Report",
        "subtitle": "1,850-seller KYC sample · Section 14.3 escrow aging · Controls & remediation narrative",
        "channel": "Compliance Ledger + KYC Controls Audit",
        "approx_tokens": 3245,
        "payload": """=== NOVAMART TREASURY & RISK AUDIT · CROSS-BORDER SELLER KYC & ESCROW CONTROLS ===
audit_id: NM-IA-2026-KYC-044
audit_scope: Marketplace Payments, Cross-Border Seller Verification (KYC/KYB), TIN/PAN/GST Tax Matching & Escrow Holds
sample_size: 1,850 active cross-border & domestic Platinum/Gold sellers ($684M annualized GMV cohort)
audit_period: April 1, 2026 – October 31, 2026
prepared_for: Board Risk & Audit Committee + Payments Nodal Regulator

--- SECTION A: INTERNAL AUDIT FINDINGS & CONTROL TELEMETRY ---
1. Automated Tax TIN / PAN / Beneficial Owner Matching Variance:
NovaMart processes $190M/month in seller marketplace settlements under automated escrow rules ("ESCROW_HOLD_409") whenever a seller's legal entity name on their W-9/PAN tax registration diverges from the beneficiary bank account title or Ultimate Beneficial Owner (UBO >=25% equity) record. Across the 1,850 audited sellers:
- 1,592 sellers (86.1%) passed automated API KYC/KYB verification cleanly on initial onboarding and quarterly refresh.
- 214 sellers (11.6%) triggered automated ESCROW_HOLD_409 holds during the audit period totaling $4.82M in held funds; however, post-review audit revealed **68.2% (146 of 214 holds)** were *false-positive string-normalization mismatches* (e.g., "Apex Lumina Electronics LLC" vs. "Apex Lumina Electronics Pvt Ltd" or maiden/middle initial variations) rather than actual shell-entity or tax evasion risk.
- Conversely, 68 holds (31.8% of held accounts, $1.41M exposure) represented genuine material compliance gaps: 41 accounts had expired corporate board authorizations / stale UBO registries (>18 months unverified), 19 accounts routed payouts to third-party aggregator IBANs outside their incorporated jurisdiction without cross-border FEMA/tax documentation, and 8 accounts exhibited rapid post-onboarding bank-account swaps flagged by Velocity AML rules.

2. Section 14.3 Escrow Hold Aging & Arbitration SLA Breach Exposure:
Under Section 14.3 of the Marketplace Seller Agreement and Nodal Settlement Guidelines, NovaMart commits to completing manual compliance document review and issuing a clear cure notice or disbursement decision within **48 business hours** of placing an automated escrow hold. Audit timestamps show:
- Median manual review SLA slipped to **83.5 hours** during pre-Diwali onboarding surges (target <=48h), leaving 52 legitimate Platinum sellers blocked for >72–96 hours despite valid credentials attached in unstructured ticket threads.
- Critically, because sellers began pasting raw unmasked SSNs, India PAN IDs, and settlement credit cards directly into free-text dispute tickets to expedite release, 194 raw sensitive PII artifacts were inadvertently echoed into general support logs prior to our Category 1 deterministic regex redaction deployment!
- Financial Dispute Exposure: Three Tier-1 sellers (representing $412k trailing 90d GMV each) issued formal Section 14.3 arbitration pre-notices over wrongful 96-hour holds caused by false-positive name-normalization triggers; potential statutory interest + arbitration defense costs estimated at $115,000–$180,000 per quarter if SLA slippage persists.

3. Sanctions Screening & Multi-Account Shell Ring Detection:
Nightly OFAC/UN/Domestic PEP list fuzz-matching screened 100% of active seller cohorts (0 confirmed SDN sanctions breaches during the period). However, Device-Graph + GSTIN clustering flagged 14 interconnected seller shells attempting to cycle high-risk electronics warranty claims via circular self-purchases ($286,000 attempted synthetic GMV blocked prior to T+7 settlement).

--- SECTION B: RECONCILIATION AGING & REMEDIATION PLAN TELEMETRY JSON ---
{
  "cohort_metrics": {
    "audited_sellers": 1850,
    "clean_kyc_pass_count": 1592,
    "escrow_hold_409_triggers": 214,
    "total_escrow_held_usd": 4820000,
    "false_positive_normalization_holds": 146,
    "false_positive_rate_pct": 68.2,
    "true_compliance_gap_accounts": 68,
    "true_compliance_gap_held_usd": 1410000
  },
  "sla_and_privacy_metrics": {
    "contractual_review_sla_hours": 48,
    "observed_median_review_hours": 83.5,
    "holds_exceeding_72h_count": 52,
    "pii_artifacts_logged_before_regex_gate": 194,
    "pii_leakage_after_regex_gate": 0,
    "section_14_3_arbitration_notices": 3,
    "estimated_quarterly_dispute_cost_usd": 147500
  },
  "sanctions_and_aml": {
    "sdn_sanctions_breaches": 0,
    "blocked_shell_ring_accounts": 14,
    "blocked_synthetic_gmv_usd": 286000
  },
  "planned_controls_and_milestones": {
    "entity_resolution_fuzzy_canonicalizer": "Deploy legal-suffix normalizer (LLC/Pvt Ltd/Inc) + instant micro-deposit name check to cut false-positive 409 holds by 65% before hold activation",
    "zero_pii_ticket_vault": "Enforce deterministic <1ms regex masking at seller portal ingestion + tokenized secure tax-doc upload vault (zero SSN/PAN in support tickets)",
    "priority_treasury_fast_lane": "Dedicated 12-hour SLA fast-lane for false-positive holds on Platinum sellers with chargeback rate <0.3% and clean KYC history"
  },
  "escrow_hold_aging_distribution": [
    {"bucket": "0–24h (Within Target SLA)", "account_count": 108, "held_usd": 1920000, "share_pct": 50.5},
    {"bucket": "24–48h (At Contractual Deadline)", "account_count": 54, "held_usd": 1190000, "share_pct": 25.2},
    {"bucket": "48–72h (SLA Breach Warning)", "account_count": 21, "held_usd": 680000, "share_pct": 9.8},
    {"bucket": ">72–96h (Severe Section 14.3 Arbitration Risk)", "account_count": 31, "held_usd": 1030000, "share_pct": 14.5}
  ]
}

--- SECTION C: STATUTORY GOVERNANCE, PRIVACY & BOARD COMMITTEE ATTESTATION SCOPE ---
1. Privacy & Data Protection Remediation (Zero-PII Ticket Vault):
Following Audit Finding #2 (194 raw SSN, PAN, and settlement card strings pasted by frustrated sellers into general CRM support queues during >72h holds), Information Security audited all downstream Zendesk/CRM replicas. Every historical raw token was purged within 72 hours using deterministic pattern scanners, and live ingestion now enforces sub-millisecond deterministic regex scrubbing BEFORE persistence or LLM classification, while routing authentic tax credential uploads strictly to an encrypted FIPS-140-3 KMS vault.
2. Nodal Settlement & Fiduciary Compliance Posture:
Nodal escrow reconciliation confirms zero commingling of merchant settlement balances ($4.82M held under ESCROW_HOLD_409) with NovaMart corporate operating accounts; 100% of frozen balances remain ring-fenced inside Tier-1 scheduled bank nodal accounts earning statutory pass-through accounting transparency. However, Treasury Operations acknowledged that failing to separate benign legal-suffix normalization mismatches (146 false-positive accounts) from high-velocity IBAN swap risk (19 cross-border accounts + 8 velocity triggers) creates avoidable Section 14.3 commercial arbitration liability (~$147,500/quarter projected legal & interest exposure).
3. Target Committee Report Deliverable:
Synthesize the exact cohort metrics (1,850 audited sellers, 68.2% false-positive 409 rate vs 68 genuine compliance gaps totaling $1.41M), SLA slippage (83.5h observed vs 48h contractual cap), PII gate remediation (194 pre-gate vs 0 post-gate), AML shell-ring prevention ($286k synthetic GMV blocked), and time-bound engineering/Treasury remediation milestones.""",
    },
]
