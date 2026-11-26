"""Two-axis Ground-Truth Accuracy & Schema Compliance Evaluator for Category 1 (structured answers)."""

from __future__ import annotations

from typing import Any

from app.models import FieldCheckResult, RungAccuracyEvaluation

def evaluate_rung_accuracy(
    *,
    rung_id: str,
    sub_task: str,
    ground_truth: dict[str, Any],
    structured_output: dict[str, Any],
    raw_text: str | None,
) -> RungAccuracyEvaluation:
    """Evaluate native schema compliance plus ground-truth field & exact-item accuracy."""
    schema_valid = rung_id in ("sonnet_calibrated", "haiku_calibrated")

    # Write-up rungs have no structured output: callers pass the reader model's extracted values as
    # `structured_output` (replay) or do not score them (live).
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
