"""Deterministic Adjudication Accuracy, Evidence Recall & Tool Precision Evaluator for Cat 5."""

from __future__ import annotations

from typing import Any

from app.models import Cat5EvaluationResult, FieldCheckResult


def _rupee_close(a: Any, b: Any, tol: float = 1.0) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def evaluate_cat5_adjudication(
    *,
    committed_voucher: dict[str, Any] | None,
    ground_truth: dict[str, Any],
    tables_touched: set[str] | list[str],
    total_tool_calls: int,
    optimal_tool_calls: int,
    steps_used: int,
    max_step_budget: int,
) -> Cat5EvaluationResult:
    """Compare committed SQLite voucher + tool trajectory against ground truth."""
    voucher = committed_voucher or {}
    checks_spec: list[tuple[str, Any, Any, bool]] = [
        (
            "decision",
            ground_truth["decision"],
            voucher.get("decision"),
            str(voucher.get("decision") or "").strip() == str(ground_truth["decision"]),
        ),
        (
            "authorized_net_principal_inr",
            float(ground_truth["authorized_net_principal_inr"]),
            voucher.get("authorized_net_principal_inr"),
            voucher.get("authorized_net_principal_inr") is not None
            and _rupee_close(
                voucher.get("authorized_net_principal_inr"),
                ground_truth["authorized_net_principal_inr"],
            ),
        ),
        (
            "authorized_gst_payout_inr",
            float(ground_truth["authorized_gst_payout_inr"]),
            voucher.get("authorized_gst_payout_inr"),
            voucher.get("authorized_gst_payout_inr") is not None
            and _rupee_close(
                voucher.get("authorized_gst_payout_inr"),
                ground_truth["authorized_gst_payout_inr"],
            ),
        ),
        (
            "gst_escrow_holdback_inr",
            float(ground_truth["gst_escrow_holdback_inr"]),
            voucher.get("gst_escrow_holdback_inr"),
            voucher.get("gst_escrow_holdback_inr") is not None
            and _rupee_close(
                voucher.get("gst_escrow_holdback_inr"),
                ground_truth["gst_escrow_holdback_inr"],
            ),
        ),
        (
            "debit_note_deduction_inr",
            float(ground_truth["debit_note_deduction_inr"]),
            voucher.get("debit_note_deduction_inr"),
            voucher.get("debit_note_deduction_inr") is not None
            and _rupee_close(
                voucher.get("debit_note_deduction_inr"),
                ground_truth["debit_note_deduction_inr"],
            ),
        ),
    ]

    field_checks = [
        FieldCheckResult(field=fname, expected=exp, actual=act, matched=ok)
        for fname, exp, act, ok in checks_spec
    ]
    matched = sum(1 for fc in field_checks if fc.matched)
    total = len(field_checks)
    accuracy_pct = round((matched / max(1, total)) * 100, 1)

    req_tables = set(ground_truth.get("required_evidence_tables") or [])
    touched_set = set(tables_touched)
    ev_recall = (
        round((len(req_tables & touched_set) / len(req_tables)) * 100, 1)
        if req_tables
        else 100.0
    )
    tool_prec = (
        round((min(optimal_tool_calls, total_tool_calls) / max(1, total_tool_calls)) * 100, 1)
        if total_tool_calls > 0
        else 0.0
    )

    return Cat5EvaluationResult(
        voucher_committed=bool(committed_voucher),
        matched_fields=matched,
        total_fields=total,
        field_accuracy_pct=accuracy_pct,
        exact_match=(matched == total and bool(committed_voucher)),
        evidence_recall_pct=ev_recall,
        tool_precision_pct=tool_prec,
        within_step_budget=(steps_used <= max_step_budget),
        gate_verified=bool(voucher.get("gate_verified")),
        field_checks=field_checks,
    )
