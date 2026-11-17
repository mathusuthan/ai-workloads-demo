"""Two-axis Ground-Truth Accuracy & Schema Compliance Evaluator for Category 1."""

from __future__ import annotations

import re
from typing import Any

from app.models import FieldCheckResult, RungAccuracyEvaluation

_SEVERITY_SCORE_TO_PRIORITY = {
    0: "P3_LOW",
    1: "P2_MEDIUM",
    2: "P1_HIGH",
    3: "P0_CRITICAL",
}

_ENUM_CANONICAL_VALUES: dict[str, list[str]] = {
    "queue": [
        "replacements",
        "billing_payouts",
        "trust_and_safety",
        "shipping_logistics",
        "general_support",
    ],
    "priority": ["P0_CRITICAL", "P1_HIGH", "P2_MEDIUM", "P3_LOW"],
    "auto_action": [
        "escalate_security",
        "hold_and_audit",
        "auto_replace",
        "route_specialist",
    ],
    "leaf_category": [
        "apparel_ethnic_kurtas",
        "electronics_power_banks",
        "kitchen_espresso_grinders",
        "home_ceramic_dinnerware",
        "audio_bluetooth_speakers",
    ],
    "compliance_status": [
        "APPROVED_AUTO_PUBLISH",
        "SUPPRESS_CONTRADICTED_FACET",
        "HOLD_MISSING_CERT",
    ],
}

_SYNONYMS: dict[str, dict[str, tuple[str, ...]]] = {
    "queue": {
        "replacements": ("replacements", "replacement", "damaged merchandise", "instant replacement"),
        "billing_payouts": ("billing_payouts", "billing", "payouts", "settlement", "escrow", "invoice", "tax-exempt", "credit memo"),
        "trust_and_safety": ("trust_and_safety", "trust & safety", "trust and safety", "fraud", "account takeover", "security"),
        "shipping_logistics": ("shipping_logistics", "shipping", "logistics", "carrier", "tracking stall"),
        "general_support": ("general_support", "general support", "product inquiry", "pre-purchase", "sizing"),
    },
    "priority": {
        "P0_CRITICAL": ("p0_critical", "p0", "critical"),
        "P1_HIGH": ("p1_high", "p1", "high priority", "high"),
        "P2_MEDIUM": ("p2_medium", "p2", "medium"),
        "P3_LOW": ("p3_low", "p3", "low"),
    },
    "auto_action": {
        "escalate_security": ("escalate_security", "freeze account", "freeze everything", "security ops", "escalate to security"),
        "hold_and_audit": ("hold_and_audit", "hold and audit", "escrow hold", "hold payout", "legal audit", "compliance audit"),
        "auto_replace": ("auto_replace", "express replacement", "overnight replacement", "immediate replacement", "trigger replacement"),
        "route_specialist": ("route_specialist", "tier-2", "tier 2", "specialist queue", "standard sla", "route to specialist"),
    },
    "leaf_category": {
        "apparel_ethnic_kurtas": ("apparel_ethnic_kurtas", "ethnic", "kurta"),
        "electronics_power_banks": ("electronics_power_banks", "power bank", "powerbank", "portable charger"),
        "kitchen_espresso_grinders": ("kitchen_espresso_grinders", "espresso grinder", "burr grinder", "induction", "coffee & espresso"),
        "home_ceramic_dinnerware": ("home_ceramic_dinnerware", "ceramic", "espresso cup", "dinnerware", "stoneware"),
        "audio_bluetooth_speakers": ("audio_bluetooth_speakers", "bluetooth speaker", "portable speaker"),
    },
    "compliance_status": {
        "APPROVED_AUTO_PUBLISH": (
            "approved_auto_publish",
            "auto-publish",
            "auto publish",
            "approve for publish",
            "approved for publishing",
            "ready for auto-publish",
            "publish immediately",
            "clean & compliant",
        ),
        "SUPPRESS_CONTRADICTED_FACET": (
            "suppress_contradicted_facet",
            "suppress contradicted",
            "suppress the contradicted",
            "suppress material",
            "suppress facet",
        ),
        "HOLD_MISSING_CERT": (
            "hold_missing_cert",
            "do not publish",
            "hold for compliance",
            "hold until",
            "missing safety",
            "missing un38.3",
            "missing voltage",
            "quarantine",
            "must hold",
        ),
    },
}


def _extract_focused_snippet(text: str, sub_task: str, field: str) -> str:
    """Narrow search to explicit routing/taxonomy/publishing header lines when present."""
    if sub_task == "support_triage" and field in ("queue", "priority", "auto_action"):
        m = re.search(
            r"(?:recommended routing|routing recommendation|primary queue|priority:|##\s*2\.)[\s\S]{0,650}",
            text,
            re.IGNORECASE,
        )
        if m:
            return m.group(0)
    if sub_task == "sku_tagging" and field == "compliance_status":
        m = re.search(
            r"(?:recommendation up front|recommended publishing status|publishing status|status:|##\s*3\.)[\s\S]{0,500}",
            text,
            re.IGNORECASE,
        )
        if m:
            return m.group(0)
    return text


def _match_field_from_text(full_text: str, sub_task: str, field: str) -> str | None:
    """Match canonical enum token first, then contextual synonyms from unconstrained prose."""
    focused = _extract_focused_snippet(full_text, sub_task, field)
    for region in (focused.lower(), full_text.lower()):
        for canonical in _ENUM_CANONICAL_VALUES[field]:
            if re.search(rf"\b{re.escape(canonical.lower())}\b", region):
                return canonical

        best_canon: str | None = None
        best_pos = 10**9
        for canonical, phrases in _SYNONYMS[field].items():
            for phrase in phrases:
                idx = region.find(phrase)
                if idx != -1 and idx < best_pos:
                    best_pos = idx
                    best_canon = canonical
        if best_canon is not None:
            return best_canon
    return None


def extract_prose_predictions(raw_text: str, sub_task: str) -> dict[str, Any]:
    """Deterministic extractor evaluating semantic answers embedded in unconstrained prose."""
    text = (raw_text or "").strip()
    if not text:
        return {}

    lower = text.lower()
    if sub_task == "support_triage":
        queue = _match_field_from_text(text, sub_task, "queue")
        priority = _match_field_from_text(text, sub_task, "priority")
        auto_action = _match_field_from_text(text, sub_task, "auto_action")

        has_no_pii_phrase = bool(
            re.search(
                r"\b(no sensitive pii|no pii detected|zero pii|no raw pii|no pii found|contains_pii:\s*false)\b",
                lower,
            )
        )
        mentions_pii = bool(
            re.search(
                r"\b(aadhaar|pan\b|payment card|visa|mastercard|card ending|email|phone|pii)\b",
                lower,
            )
        )
        contains_pii: bool | None = (
            False if has_no_pii_phrase else (True if mentions_pii else None)
        )
        return {
            "queue": queue,
            "priority": priority,
            "auto_action": auto_action,
            "contains_pii": contains_pii,
        }

    leaf = _match_field_from_text(text, sub_task, "leaf_category")
    compliance = _match_field_from_text(text, sub_task, "compliance_status")
    has_no_contra = bool(
        re.search(
            r"\b(no (?:factual )?contradictions?|zero contradictions?|no contradictions? detected|contradictions?:\s*none|false\s*\(?none\)?)\b",
            lower,
        )
    )
    mentions_contra = bool(
        re.search(r"\b(contradict(?:s|ed|ing|ion|ions)?|mismatch|misrepresent\w*|falsified|conflicting|conflicts)\b", lower)
    )
    contradiction_detected: bool | None = (
        False if has_no_contra else (True if mentions_contra else None)
    )
    return {
        "leaf_category": leaf,
        "compliance_status": compliance,
        "contradiction_detected": contradiction_detected,
    }


def _extract_gemini_predictions(
    structured_output: dict[str, Any],
    sub_task: str,
) -> dict[str, Any]:
    """Map Gemini Decision 1 question outputs onto canonical ground-truth keys."""
    if sub_task == "support_triage":
        sev_raw = structured_output.get("severity")
        sev_priority: str | None = None
        if isinstance(sev_raw, (int, float)):
            clamped = max(0, min(3, round(float(sev_raw))))
            sev_priority = _SEVERITY_SCORE_TO_PRIORITY.get(clamped)
        return {
            "queue": structured_output.get("queue"),
            "priority": sev_priority,
            "auto_action": structured_output.get("auto_action"),
            "contains_pii": structured_output.get("contains_sensitive_pii"),
        }

    return {
        "leaf_category": structured_output.get("leaf_category"),
        "compliance_status": structured_output.get("compliance_status"),
        "contradiction_detected": structured_output.get("has_factual_contradiction"),
    }


def evaluate_rung_accuracy(
    *,
    rung_id: str,
    sub_task: str,
    ground_truth: dict[str, Any],
    structured_output: dict[str, Any],
    raw_text: str | None,
) -> RungAccuracyEvaluation:
    """Evaluate native schema compliance plus ground-truth field & exact-item accuracy."""
    schema_valid = rung_id in ("haiku_calibrated", "gemini_decision")

    if rung_id in ("sonnet_naive", "haiku_naive"):
        predicted = extract_prose_predictions(raw_text or "", sub_task)
    elif rung_id == "gemini_decision":
        predicted = _extract_gemini_predictions(structured_output, sub_task)
    else:
        predicted = structured_output

    checks: list[FieldCheckResult] = []
    matched_count = 0
    for field, expected in ground_truth.items():
        actual = predicted.get(field)
        matched = actual == expected
        if matched:
            matched_count += 1
        checks.append(
            FieldCheckResult(
                field=field,
                expected=expected,
                actual=actual,
                matched=matched,
            )
        )

    total_fields = len(ground_truth)
    field_pct = round((matched_count / total_fields) * 100, 1) if total_fields > 0 else 0.0
    exact = total_fields > 0 and matched_count == total_fields

    return RungAccuracyEvaluation(
        schema_valid=schema_valid,
        matched_count=matched_count,
        total_fields=total_fields,
        field_accuracy_pct=field_pct,
        exact_match=exact,
        field_checks=checks,
    )
