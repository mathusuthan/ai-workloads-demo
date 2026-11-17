"""Strict JSON Schemas (Rung 2 Haiku) and Decisions API Questions (Rung 3 Gemini Decision 1)."""

from __future__ import annotations

from typing import Any

SUPPORT_TRIAGE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "queue": {
            "type": "string",
            "enum": [
                "replacements",
                "billing_payouts",
                "trust_and_safety",
                "shipping_logistics",
                "general_support",
            ],
        },
        "priority": {
            "type": "string",
            "enum": ["P0_CRITICAL", "P1_HIGH", "P2_MEDIUM", "P3_LOW"],
        },
        "contains_pii": {"type": "boolean"},
        "pii_categories": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["AADHAAR", "PAYMENT_CARD", "EMAIL", "PHONE", "TAX_PAN_ID", "BANK_ROUTING"],
            },
        },
        "auto_action": {
            "type": "string",
            "enum": ["escalate_security", "hold_and_audit", "auto_replace", "route_specialist"],
        },
        "reason_code": {
            "type": "string",
            "enum": [
                "TRANSIT_DAMAGE",
                "SETTLEMENT_HOLD_LEGAL",
                "ACCOUNT_TAKEOVER",
                "POLICY_INQUIRY",
                "DELIVERY_DELAY",
            ],
        },
    },
    "required": [
        "queue",
        "priority",
        "contains_pii",
        "pii_categories",
        "auto_action",
        "reason_code",
    ],
    "additionalProperties": False,
}

SKU_TAGGING_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "leaf_category": {
            "type": "string",
            "enum": [
                "apparel_ethnic_kurtas",
                "electronics_power_banks",
                "kitchen_espresso_grinders",
                "home_ceramic_dinnerware",
                "audio_bluetooth_speakers",
                "beauty_aerosol_sprays",
            ],
        },
        "hazmat_class": {
            "type": "string",
            "enum": [
                "NONE",
                "LITHIUM_ION_DECLARED",
                "FRAGILE_GLASS_CERAMIC",
                "HIGH_VOLTAGE_COMMERCIAL",
            ],
        },
        "compliance_status": {
            "type": "string",
            "enum": [
                "APPROVED_AUTO_PUBLISH",
                "SUPPRESS_CONTRADICTED_FACET",
                "HOLD_MISSING_CERT",
            ],
        },
        "contradiction_detected": {"type": "boolean"},
        "primary_material_tag": {
            "type": "string",
            "enum": [
                "polyester_viscose_blend",
                "pure_mulberry_silk",
                "lithium_polymer_abs",
                "stainless_steel_burr",
                "stoneware_ceramic",
            ],
        },
    },
    "required": [
        "leaf_category",
        "hazmat_class",
        "compliance_status",
        "contradiction_detected",
        "primary_material_tag",
    ],
    "additionalProperties": False,
}

SUPPORT_DECISION_QUESTIONS: dict[str, Any] = {
    "queue": {
        "type": "choice",
        "instructions": "Select the single NovaMart support queue best suited to handle this ticket.",
        "criteria": {
            "replacements": "Damaged, cracked, defective, or wrong physical merchandise delivered to buyer.",
            "billing_payouts": "Seller disbursement holds, tax withholding, ledger disputes, or invoice/refund issues.",
            "trust_and_safety": "Account takeover, unauthorized password/email change, gift-card drain, or fraud.",
            "shipping_logistics": "Lost in transit, carrier delay, or address reroute with no damage confirmed.",
            "general_support": "Pre-purchase product inquiry, how-to question, or routine account feedback.",
        },
    },
    "auto_action": {
        "type": "choice",
        "instructions": "Select the immediate automated workflow action for this NovaMart intake event.",
        "criteria": {
            "escalate_security": "Freeze account/sessions immediately and page Fraud & Security Ops.",
            "hold_and_audit": "Hold financial payout or escalate to Compliance/Legal audit specialist.",
            "auto_replace": "Trigger instant buyer replacement shipment and carrier claim.",
            "route_specialist": "Assign to Tier-2 specialist queue with standard SLA.",
        },
    },
    "severity": {
        "type": "score",
        "instructions": "Rate operational severity and financial/legal urgency of this NovaMart escalation.",
        "criteria": [
            "P3 Low: Routine inquiry, zero financial loss, no compliance or safety exposure.",
            "P2 Medium: Standard delivery or billing delay, normal SLA handling.",
            "P1 High: Broken merchandise, legal/regulatory threat, or blocked seller payout.",
            "P0 Critical: Active account takeover, fraud drain, or immediate financial/security loss.",
        ],
    },
    "contains_sensitive_pii": {
        "type": "noul",
        "instructions": "Does the payload contain raw unmasked sensitive PII such as Aadhaar, payment card digits, PAN tax ID, personal phone, or personal email?",
    },
}

SKU_DECISION_QUESTIONS: dict[str, Any] = {
    "leaf_category": {
        "type": "choice",
        "instructions": "Assign the canonical NovaMart marketplace leaf category for this raw SKU payload.",
        "criteria": {
            "apparel_ethnic_kurtas": "Ethnic wear, kurtas, sarees, or woven/blended garments.",
            "electronics_power_banks": "Portable battery packs, USB-C chargers, and lithium-ion power banks.",
            "kitchen_espresso_grinders": "Coffee/espresso grinders and commercial countertop kitchen appliances.",
            "home_ceramic_dinnerware": "Ceramic plates, mugs, and dining tableware.",
            "audio_bluetooth_speakers": "Portable wireless speakers and soundbars.",
        },
    },
    "compliance_status": {
        "type": "choice",
        "instructions": "Determine NovaMart Catalog Legal & Compliance Gate decision.",
        "criteria": {
            "APPROVED_AUTO_PUBLISH": "All seller claims match OCR/spec sheets and required certifications are present.",
            "SUPPRESS_CONTRADICTED_FACET": "Seller text factually contradicts label OCR or lab specs (e.g., fake 100% silk claim); suppress contradicted search facet.",
            "HOLD_MISSING_CERT": "Missing mandatory safety/hazmat/voltage certification (e.g., UN38.3, BIS, UL) required for fulfillment.",
        },
    },
    "hazmat_compliance_risk": {
        "type": "score",
        "instructions": "Rate shipping hazmat, electrical safety, or legal misrepresentation risk (0=none to 3=severe).",
        "criteria": [
            "Level 0: Benign non-hazardous SKU with fully verified factual metadata.",
            "Level 1: Minor fragile handling requirement or incomplete non-safety attribute.",
            "Level 2: Material misrepresentation or missing regional electrical/safety cert requiring publish hold.",
            "Level 3: High-capacity lithium-ion / air-freight hazmat or dangerous misrepresentation requiring strict block.",
        ],
    },
    "has_factual_contradiction": {
        "type": "noul",
        "instructions": "Does the seller-submitted title/description factually contradict the attached OCR care label or manufacturer spec sheet?",
    },
}


def get_schema_for_subtask(sub_task: str) -> dict[str, Any]:
    return SUPPORT_TRIAGE_JSON_SCHEMA if sub_task == "support_triage" else SKU_TAGGING_JSON_SCHEMA


def get_questions_for_subtask(sub_task: str) -> dict[str, Any]:
    return SUPPORT_DECISION_QUESTIONS if sub_task == "support_triage" else SKU_DECISION_QUESTIONS
