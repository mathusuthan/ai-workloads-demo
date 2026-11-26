"""Strict JSON schemas for the Category 1 classification rungs (Sonnet 5.5 and Haiku 5.5)."""

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

def get_schema_for_subtask(sub_task: str) -> dict[str, Any]:
    return SUPPORT_TRIAGE_JSON_SCHEMA if sub_task == "support_triage" else SKU_TAGGING_JSON_SCHEMA

