"""JSON schemas for Category 3 Sliding-Window Session Memory Summarization."""

from __future__ import annotations

from typing import Any

SESSION_MEMORY_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "compacted_through_turn": {
            "type": "integer",
            "description": "Highest turn number absorbed into this compacted session memory.",
        },
        "employee_and_device_anchors": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Concise IDs anchored across turns (Employee ID, MacBook Asset Tag, Case IDs).",
        },
        "resolved_issues": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Concise bullets of diagnosed & resolved IT/HR issues with exact Policy/Queue/Command used.",
        },
        "active_open_items": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Concise open approvals, pending wires, SLA deadlines, or blocking gates.",
        },
        "key_numeric_facts": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Exact verified numbers (INR/USD amounts, days, cutoffs, percentages, SLA timers).",
        },
    },
    "required": [
        "compacted_through_turn",
        "employee_and_device_anchors",
        "resolved_issues",
        "active_open_items",
        "key_numeric_facts",
    ],
}
