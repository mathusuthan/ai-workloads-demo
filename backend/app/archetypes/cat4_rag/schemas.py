"""Strict JSON Schema for Category 4 Stage-2 Haiku Cross-Chunk Reranker."""

from __future__ import annotations

from typing import Any

RERANK_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "selected_chunks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "chunk_id": {"type": "string"},
                    "relevance_score": {
                        "type": "integer",
                        "description": "0-100 relevance score for answering the due-diligence query.",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "<= 12 words explaining why this clause is decisive (or overrides MSA).",
                    },
                },
                "required": ["chunk_id", "relevance_score", "rationale"],
            },
        }
    },
    "required": ["selected_chunks"],
}
