"""Strict Section-Templated JSON Schemas for Category 2 (Slide 4 Lever)."""

from __future__ import annotations

from typing import Any

STRUCTURED_DRAFT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "document_title": {"type": "string"},
        "document_type": {
            "type": "string",
            "enum": [
                "EXECUTIVE_OPS_READOUT",
                "CLIENT_PARTNERSHIP_PROPOSAL",
                "STATUTORY_SAFETY_FILING",
                "REGULATORY_COMPLIANCE_AUDIT",
            ],
        },
        "executive_summary": {
            "type": "object",
            "properties": {
                "headline": {"type": "string"},
                "narrative": {"type": "string"},
                "bottom_line_impact": {"type": "string"},
            },
            "required": ["headline", "narrative", "bottom_line_impact"],
            "additionalProperties": False,
        },
        "key_findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "theme": {"type": "string"},
                    "quantified_evidence": {"type": "string"},
                    "source_anchor": {"type": "string"},
                },
                "required": ["id", "theme", "quantified_evidence", "source_anchor"],
                "additionalProperties": False,
            },
        },
        "risk_and_compliance_matrix": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["CRITICAL", "HIGH", "MODERATE"],
                    },
                    "exposure_summary": {"type": "string"},
                    "mitigation_control": {"type": "string"},
                },
                "required": ["domain", "severity", "exposure_summary", "mitigation_control"],
                "additionalProperties": False,
            },
        },
        "action_plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "milestone": {"type": "string"},
                    "target_window": {"type": "string"},
                    "verification_metric": {"type": "string"},
                },
                "required": ["owner", "milestone", "target_window", "verification_metric"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "document_title",
        "document_type",
        "executive_summary",
        "key_findings",
        "risk_and_compliance_matrix",
        "action_plan",
    ],
    "additionalProperties": False,
}


def get_single_section_schema(section_key: str) -> dict[str, Any]:
    """Return a strict single-section JSON schema for surgical HITL regeneration."""
    section_prop = STRUCTURED_DRAFT_JSON_SCHEMA["properties"][section_key]
    return {
        "type": "object",
        "properties": {
            section_key: section_prop,
        },
        "required": [section_key],
        "additionalProperties": False,
    }
