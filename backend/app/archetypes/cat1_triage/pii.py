"""Deterministic <1ms regex PII scrubber pairing with Tier-1 classifiers and System-1 models."""

from __future__ import annotations

import re
from app.models import PiiRedactionResult

_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "PAYMENT_CARD",
        re.compile(r"(?<!\d)(?:\d{4}[-\s]?){3}\d{4}(?!\d)|\b\d{4}[-\s]?\d{6}[-\s]?\d{5}\b"),
        "[REDACTED_CARD_PII]",
    ),
    (
        "AADHAAR",
        re.compile(r"(?<![\d-])[2-9]\d{3}(?:[-\s]\d{4}){2}(?![\d-])"),
        "[REDACTED_AADHAAR_PII]",
    ),
    (
        "EMAIL",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED_EMAIL_PII]",
    ),
    (
        "PHONE",
        re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b|\+91[-\s]?\d{5}[-\s]?\d{5}\b"),
        "[REDACTED_PHONE_PII]",
    ),
    (
        "TAX_PAN_ID",
        re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
        "[REDACTED_PAN_TAX_ID]",
    ),
]


def scrub_pii_deterministic(raw_text: str, max_preview_chars: int = 8000) -> PiiRedactionResult:
    """Mask sensitive PII tokens deterministically in <1ms so Tier-1 LLMs never echo raw secrets."""
    masked = raw_text
    counts: dict[str, int] = {}

    for label, pattern, replacement in _PATTERNS:
        matches = pattern.findall(masked)
        if matches:
            counts[label] = len(matches)
            masked = pattern.sub(replacement, masked)

    total = sum(counts.values())
    preview = masked if len(masked) <= max_preview_chars else f"{masked[:max_preview_chars]}..."

    return PiiRedactionResult(
        contains_pii=total > 0,
        counts_by_type=counts,
        total_redactions=total,
        masked_preview=preview,
    )
