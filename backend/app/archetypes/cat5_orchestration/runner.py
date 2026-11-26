"""Orchestrates Category 5 3-Way SQLite ERP Reconciliation Agent Arena & Portfolio Evaluation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4
from fastapi import HTTPException, Request

from app.archetypes.cat5_orchestration.accuracy import evaluate_cat5_adjudication
from app.archetypes.cat5_orchestration.erp_db import (
    GOVERNED_TOOLS,
    NAIVE_TOOLS,
    Cat5ErpSession,
)
from app.archetypes.cat5_orchestration.prompts import (
    build_cat5_user_task_prompt,
    get_cat5_system_prompt,
)
from app.config import get_settings
from app.core.anthropic_service import run_cat5_tool_loop_step
from app.core.credit_shield import credit_shield
from app.core.measured_claims import fmt_pct, pct_cut, set_note
from app.core.pricing import compute_run_finops, rollup_multi_call_finops
from app.core.trace_store import (
    TracePartition,
    TraceRecord,
    TraceRequestEnvelope,
    TraceResponseEnvelope,
    record_trace,
)
from app.data.cat5_fixtures import AP_POLICY_MANUAL_MARKDOWN, CAT5_PRESETS
from app.models import (
    Cat5AblationPortfolio,
    Cat5CommittedVoucher,
    Cat5LoopStep,
    Cat5PortfolioRungRollup,
    Cat5RungId,
    Cat5RungResult,
    Cat5RunRequest,
    Cat5RunResponse,
    Cat5ToolCallTrace,
    FinOpsBreakdown,
)

CAT5_CATEGORY = "cat5_process_orchestration"
CAT5_USE_CASE = "invoice_3way_reconciliation"
CAT5_RUNG_TO_PATTERN: dict[str, str] = {
    "unbounded_sonnet_loop": "unbounded_uncached_react_loop",
    "bounded_sonnet_cached_gate": "bounded_sonnet_cached_gate",
    "hybrid_haiku_sonnet_governed": "hybrid_haiku_sonnet_governed_loop",
}
CAT5_BUDGETS: dict[str, int] = {
    "unbounded_sonnet_loop": 12,  # safety cap on model turns (the ablation's neutral-arm cap)
    "bounded_sonnet_cached_gate": 4,
    "hybrid_haiku_sonnet_governed": 4,
}
# Live path: same per-turn output cap and timeout as the ablation harness (ablation.MAX_TOKENS_PER_TURN / CALL_TIMEOUT_S).
CAT5_MAX_TOKENS = 4096
CAT5_CALL_TIMEOUT_S = 180.0


def _preset_map() -> dict[str, dict[str, Any]]:
    return {p["id"]: p for p in CAT5_PRESETS}


def load_cat5_replays() -> dict[str, Any]:
    replays_file = Path(get_settings().replays_dir) / "cat5_golden_replays.json"
    if not replays_file.is_file():
        return {"presets": {}}
    return json.loads(replays_file.read_text(encoding="utf-8"))


def load_cat5_ablation_portfolio() -> Cat5AblationPortfolio | None:
    """Six-arm ablation summary (replays/cat5_ablation_summary.json); None if absent or unreadable."""
    path = Path(get_settings().replays_dir) / "cat5_ablation_summary.json"
    if not path.is_file():
        return None
    try:
        return Cat5AblationPortfolio.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, OSError):
        return None


def _rung_metadata(rung_id: str) -> tuple[str, str, list[str]]:
    """Number-free fallback copy; `_apply_measured_claims` replaces result-dependent sentences."""
    if rung_id == "unbounded_sonnet_loop":
        return (
            "1. Free-Choice Raw-Table Loop (Sonnet 5.5)",
            "Baseline: Raw Tables, No Cache",
            [
                "The model chooses which raw SELECT * table queries to run (several per turn allowed), does the policy "
                "arithmetic itself and commits the voucher.",
                "No prompt cache and no policy gate; a safety cap on model turns.",
            ],
        )
    if rung_id == "bounded_sonnet_cached_gate":
        return (
            "2. Narrow Query + Cached Policy + Policy Gate",
            "Narrow Query + Cache + Policy Gate",
            [
                "One projected bundle query replaces the raw table dumps, and the policy manual is sent as a cached prefix.",
                "The commit tool refuses until the deterministic policy gate (AP-POL-GATE-01) has computed the voucher; "
                "the committed voucher carries its figures, as this version's instructions require.",
            ],
        )
    return (
        "3. Haiku + Policy Gate + Sonnet Escalation",
        "Tiered Routing + Policy Gate",
        [
            "Rung 2's tools and prompt on Haiku 5.5; the run switches to Sonnet 5.5 when the gate flags escalation.",
            "The gate flags escalation whenever the debit note is above zero or two or more discrepancies combine.",
        ],
    )


def _compute_step_cold_warm(
    *,
    rung_id: str,
    finops: FinOpsBreakdown,
    seen_cache_models: set[str],
) -> tuple[float, float]:
    prefix_tok = finops.cache_creation_tokens + finops.cache_read_tokens
    if rung_id == "unbounded_sonnet_loop" or prefix_tok <= 0:
        return finops.total_cost_usd, finops.total_cost_usd

    is_first_cold = finops.model_id not in seen_cache_models
    if is_first_cold:
        seen_cache_models.add(finops.model_id)

    cold_fin = compute_run_finops(
        model_id=finops.model_id,
        input_tokens=finops.input_tokens,
        output_tokens=finops.output_tokens,
        cache_creation_tokens=prefix_tok if is_first_cold else 0,
        cache_read_tokens=0 if is_first_cold else prefix_tok,
    )
    warm_fin = compute_run_finops(
        model_id=finops.model_id,
        input_tokens=finops.input_tokens,
        output_tokens=finops.output_tokens,
        cache_creation_tokens=0,
        cache_read_tokens=prefix_tok,
    )
    return cold_fin.total_cost_usd, warm_fin.total_cost_usd


def persist_cat5_trace(
    *,
    source_mode: str,
    run_group_id: str,
    item_id: str,
    item_title: str,
    model_id: str,
    pattern: str,
    system_instruction: str,
    payload_text: str,
    status: str,
    latency_ms: int,
    finops_dict: dict[str, Any],
    raw_text: str | None,
    structured_output: dict[str, Any],
    request_params: dict[str, Any] | None = None,
    stop_reason: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> Path:
    envelope = TraceRequestEnvelope(
        provider="Anthropic",
        endpoint="messages.create",
        system_instruction=system_instruction,
        parameters=request_params
        or {
            "max_tokens": CAT5_MAX_TOKENS,
            "endpoint": "messages.create",
            "thinking": {"type": "between_tools"} if "sonnet" in model_id else {"type": "disabled"},
        },
        input_payload=payload_text,
    )
    record = TraceRecord(
        run_group_id=run_group_id,
        source_mode=source_mode,  # type: ignore[arg-type]
        item_id=item_id,
        item_title=item_title,
        partition=TracePartition(
            category=CAT5_CATEGORY,
            use_case=CAT5_USE_CASE,
            model=model_id,
            pattern=pattern,
        ),
        request=envelope,
        response=TraceResponseEnvelope(
            status=status,  # type: ignore[arg-type]
            stop_reason=stop_reason,
            latency_ms=latency_ms,
            raw_text=raw_text,
            structured_output=structured_output,
        ),
        finops=finops_dict,
        extra_metadata=extra_metadata or {},
    )
    return record_trace(record)


def finalize_cat5_rung_result(
    *,
    rung_id: Cat5RungId,
    primary_model_id: str,
    steps: list[Cat5LoopStep],
    committed_voucher: Cat5CommittedVoucher | None,
    evaluation: Any,
    final_readout: str,
    circuit_breaker_triggered: bool,
    status: str = "ok",
    error_message: str | None = None,
) -> Cat5RungResult:
    title, badge, notes = _rung_metadata(rung_id)
    pattern = CAT5_RUNG_TO_PATTERN[rung_id]
    budget = CAT5_BUDGETS[rung_id]

    haiku_steps = sum(1 for s in steps if "haiku" in s.model_id)
    sonnet_steps = sum(1 for s in steps if "sonnet" in s.model_id)
    escalated = any(s.escalated_from_haiku for s in steps)

    tot_in = sum(s.finops.input_tokens for s in steps)
    tot_cw = sum(s.finops.cache_creation_tokens for s in steps)
    tot_cr = sum(s.finops.cache_read_tokens for s in steps)
    tot_out = sum(s.finops.output_tokens for s in steps)

    cold_run = round(steps[-1].cumulative_cold_cost_usd, 8) if steps else 0.0
    warm_run = round(steps[-1].cumulative_warm_cost_usd, 8) if steps else 0.0
    tot_lat = sum(s.latency_ms for s in steps)

    return Cat5RungResult(
        rung_id=rung_id,
        rung_title=title,
        badge_text=badge,
        pattern=pattern,
        primary_model_id=primary_model_id,
        status=status,  # type: ignore[arg-type]
        error_message=error_message,
        max_step_budget=budget,
        steps_used=len(steps),
        haiku_steps=haiku_steps,
        sonnet_steps=sonnet_steps,
        escalated_to_sonnet=escalated,
        circuit_breaker_triggered=circuit_breaker_triggered,
        steps=steps,
        total_uncached_input_tokens=tot_in,
        total_cache_creation_tokens=tot_cw,
        total_cache_read_tokens=tot_cr,
        total_output_tokens=tot_out,
        cold_run_cost_usd=cold_run,
        warm_run_cost_usd=warm_run,
        cost_per_1k_invoices_cold_usd=round(cold_run * 1000, 4),
        cost_per_1k_invoices_warm_usd=round(warm_run * 1000, 4),
        total_latency_ms=tot_lat,
        final_readout=final_readout,
        committed_voucher=committed_voucher,
        evaluation=evaluation,
        architectural_notes=notes,
    )


def _arm(portfolio: Cat5AblationPortfolio | None, arm_id: str) -> Any:
    return next((a for a in (portfolio.arms if portfolio else []) if a.arm_id == arm_id and a.runs > 0), None)


def _lever(portfolio: Cat5AblationPortfolio | None, name: str) -> Any:
    return next((lv for lv in (portfolio.levers if portfolio else []) if lv.lever == name and lv.available), None)


def _gate_disagreement(portfolio: Cat5AblationPortfolio | None) -> Any:
    return next((g for g in (portfolio.gate_disagreement if portfolio else []) if g.gate_runs or g.no_gate_runs), None)


def _apply_measured_claims(results: list[Cat5RungResult], portfolio: Cat5AblationPortfolio | None = None) -> None:
    """Rewrite result-dependent rung notes with numbers measured on this invoice and in the ablation."""
    ok = {r.rung_id: r for r in results if r.status == "ok" and r.steps}
    naive = ok.get("unbounded_sonnet_loop")
    bounded = ok.get("bounded_sonnet_cached_gate")
    hybrid = ok.get("hybrid_haiku_sonnet_governed")

    def prompt_tok(r: Cat5RungResult) -> int:
        return r.total_uncached_input_tokens + r.total_cache_creation_tokens + r.total_cache_read_tokens

    if naive:
        calls = [tc.tool_name for st in naive.steps for tc in st.tool_calls]
        lookups = sum(1 for c in calls if c != "commit_reconciliation_voucher")
        set_note(
            naive,
            0,
            f"The model chose {lookups} raw SELECT * table quer{'y' if lookups == 1 else 'ies'} across "
            f"{naive.steps_used} turns (several per turn allowed), did the policy arithmetic itself and "
            f"{'committed the voucher' if naive.committed_voucher else 'committed no voucher'}.",
        )
        set_note(
            naive,
            1,
            f"No prompt cache and no policy gate: {prompt_tok(naive):,} prompt tokens this run; "
            f"{naive.steps_used} of a {naive.max_step_budget}-turn safety cap used.",
        )
    if bounded:
        prefix = max(s.finops.cache_creation_tokens + s.finops.cache_read_tokens for s in bounded.steps)
        text = f"One bundle query and a cached ~{prefix / 1000:.1f}k-token policy prefix"
        cut = pct_cut(naive.total_uncached_input_tokens, bounded.total_uncached_input_tokens) if naive else None
        if cut is not None:
            text += (
                f": uncached prompt tokens {naive.total_uncached_input_tokens:,} → {bounded.total_uncached_input_tokens:,} "
                f"vs rung 1 ({fmt_pct(cut)} fewer)"
            )
        set_note(bounded, 0, text + ".")
        ev = bounded.evaluation
        gate_text = "The committed voucher carries the deterministic policy gate's figures"
        if ev is not None:
            gate_text += f" (rupee fields {ev.matched_fields}/{ev.total_fields} on this invoice)"
        lv = _lever(portfolio, "deterministic gate")
        no_gate, with_gate = _arm(portfolio, "bundle_sonnet_cached"), _arm(portfolio, "bundle_gate_sonnet_cached")
        gd = _gate_disagreement(portfolio)
        if lv and no_gate and with_gate and lv.cost_billed_ratio is not None:
            gate_text += (
                f". In the {with_gate.runs}-run ablation, adding the gate to the same narrow-query setup changed turns "
                f"{no_gate.turns_mean:.1f} → {with_gate.turns_mean:.1f} and cost per invoice by "
                f"{(lv.cost_billed_ratio - 1) * 100:+.0f}%, with exact vouchers {no_gate.exact}/{no_gate.runs} → "
                f"{with_gate.exact}/{with_gate.runs}"
            )
            if gd and gd.gate_runs:
                was = "was" if gd.gate_fixed_on else "is"
                gate_text += (
                    f"; on invoice {gd.invoice_id}, where the gate's own rule {was} wrong, gated runs committed its figures in "
                    f"{gd.gate_match_gate_output}/{gd.gate_runs} runs"
                )
                if gd.gate_fixed_on:
                    gate_text += f" (the gate has since been fixed, on {gd.gate_fixed_on}"
                    gate_text += (
                        f"; re-run on the fixed gate, {gd.after_fix_gate_match_manual}/{gd.after_fix_gate_runs} gated runs "
                        "matched the manual)" if gd.after_fix_gate_runs else "; not yet re-run on the fixed gate)"
                    )
        set_note(bounded, 1, gate_text + ".")
    if hybrid:
        set_note(
            hybrid,
            0,
            f"Haiku 5.5 ran {hybrid.haiku_steps} turn{'s' if hybrid.haiku_steps != 1 else ''} and Sonnet 5.5 "
            f"ran {hybrid.sonnet_steps} on this invoice "
            f"({'the gate flagged escalation' if hybrid.escalated_to_sonnet else 'no escalation flagged'}).",
        )
        small, tiered = _arm(portfolio, "bundle_haiku_cached"), _arm(portfolio, "bundle_gate_haiku_escalate")
        if small and tiered and small.cost_per_1k_billed_usd is not None and tiered.cost_per_1k_billed_usd is not None:
            set_note(
                hybrid,
                1,
                f"In the ablation, Haiku with the narrow query and no gate committed {small.exact}/{small.runs} exact "
                f"vouchers at ${small.cost_per_1k_billed_usd:.2f} per 1,000 invoices; adding the gate and escalation gave "
                f"{tiered.exact}/{tiered.runs} at ${tiered.cost_per_1k_billed_usd:.2f} (escalation fired on "
                f"{tiered.escalation_fired}/{tiered.runs} runs, because the gate flags every debit note).",
            )


def _orchestration_callout(
    preset: dict[str, Any],
    results: list[Cat5RungResult],
    portfolio: Cat5AblationPortfolio | None,
) -> str:
    ok = {r.rung_id: r for r in results if r.status == "ok" and r.steps}
    naive = ok.get("unbounded_sonnet_loop")
    bounded = ok.get("bounded_sonnet_cached_gate")
    hybrid = ok.get("hybrid_haiku_sonnet_governed")
    parts: list[str] = []
    if naive and bounded and hybrid:
        exact = sum(1 for r in (naive, bounded, hybrid) if r.evaluation and r.evaluation.exact_match)
        parts.append(
            f"{preset['invoice_id']}: free-choice raw-table loop {naive.steps_used} turns, "
            f"${naive.cost_per_1k_invoices_cold_usd:.2f} per 1,000 invoices; narrow query + cache + gate "
            f"${bounded.cost_per_1k_invoices_cold_usd:.2f} cold / ${bounded.cost_per_1k_invoices_warm_usd:.2f} warm; "
            f"Haiku + gate + escalation ${hybrid.cost_per_1k_invoices_cold_usd:.2f} cold / "
            f"${hybrid.cost_per_1k_invoices_warm_usd:.2f} warm. Exact vouchers on this invoice: {exact}/3."
        )
    nq = _lever(portfolio, "narrow query")
    ms = _lever(portfolio, "model swap without gate")
    gt = _lever(portfolio, "deterministic gate")
    ratios_ok = nq and ms and gt and None not in (nq.cost_billed_ratio, ms.cost_billed_ratio, gt.cost_billed_ratio)
    if portfolio and portfolio.arms and ratios_ok:
        low = min(a.exact for a in portfolio.arms if a.runs)
        caps = sum(a.cap_hits for a in portfolio.arms)
        parts.append(
            f"Across {portfolio.pooled_runs} ablation runs ({len(portfolio.arms)} versions × {portfolio.runs_per_arm}) every "
            f"version committed at least {low}/{portfolio.runs_per_arm} vouchers that matched exactly. The narrow query cut cost "
            f"{fmt_pct((1 - nq.cost_billed_ratio) * 100)} and the small model a further "
            f"{fmt_pct((1 - ms.cost_billed_ratio) * 100)}; adding the policy gate raised cost "
            f"{fmt_pct((gt.cost_billed_ratio - 1) * 100)} with exact vouchers {gt.exact_delta_pp:+.0f} pp; "
            f"{caps} run{'s' if caps != 1 else ''} hit a step cap."
        )
    if not parts:
        return (
            "Category 5 compares a free-choice loop over raw ERP tables with a narrow query + cached policy + "
            "deterministic gate, and the same on Haiku with Sonnet escalation, inside a live SQLite 3-way ERP."
        )
    return " ".join(parts)


def _apply_cross_rung_savings(results: list[Cat5RungResult]) -> None:
    naive = next((r for r in results if r.rung_id == "unbounded_sonnet_loop" and r.status == "ok"), None)
    if not naive:
        return
    for res in results:
        if res.status != "ok":
            continue
        if naive.cold_run_cost_usd > 0:
            res.savings_vs_naive_cold_pct = round(
                ((naive.cold_run_cost_usd - res.cold_run_cost_usd) / naive.cold_run_cost_usd) * 100,
                2,
            )
        if naive.warm_run_cost_usd > 0:
            res.savings_vs_naive_warm_pct = round(
                ((naive.warm_run_cost_usd - res.warm_run_cost_usd) / naive.warm_run_cost_usd) * 100,
                2,
            )


async def _run_live_cat5_for_rung(
    *,
    preset: dict[str, Any],
    rung_id: Cat5RungId,
    api_key: str,
) -> tuple[Cat5RungResult, dict[str, Any]]:
    """Execute a live SQLite tool-use loop on Claude 5.5 for one invoice & rung."""
    session = Cat5ErpSession(rung_id=rung_id)
    system_text = get_cat5_system_prompt(rung_id)
    user_task = build_cat5_user_task_prompt(preset)
    tools = NAIVE_TOOLS if rung_id == "unbounded_sonnet_loop" else GOVERNED_TOOLS
    use_cache = rung_id != "unbounded_sonnet_loop"
    max_budget = CAT5_BUDGETS[rung_id]

    active_model = (
        "claude-haiku-5-5"
        if rung_id == "hybrid_haiku_sonnet_governed"
        else "claude-sonnet-5-5"
    )
    primary_model = (
        "claude-haiku-5-5 -> claude-sonnet-5-5 (conditional)"
        if rung_id == "hybrid_haiku_sonnet_governed"
        else "claude-sonnet-5-5"
    )

    messages: list[dict[str, Any]] = [{"role": "user", "content": user_task}]
    seen_cache_models: set[str] = set()
    cum_cold = 0.0
    cum_warm = 0.0
    steps: list[Cat5LoopStep] = []
    raw_steps: list[dict[str, Any]] = []
    circuit_breaker = False
    final_readout = ""
    escalated_on_next = False

    # Allow +1 safety wrap-up step only if governed agent committed voucher on step == max_budget
    hard_loop_cap = max_budget if rung_id == "unbounded_sonnet_loop" else max_budget + 1

    try:
        for step_idx in range(1, hard_loop_cap + 1):
            is_escalated_turn = escalated_on_next
            escalated_on_next = False

            raw = await run_cat5_tool_loop_step(
                model_tier=active_model,
                system_text=system_text,
                tools=tools,
                messages=list(messages),
                use_prefix_cache=use_cache,
                api_key=api_key,
                max_tokens=CAT5_MAX_TOKENS,
                timeout_s=CAT5_CALL_TIMEOUT_S,
            )
            fin = compute_run_finops(
                model_id=raw.model_id,
                input_tokens=raw.input_tokens,
                output_tokens=raw.output_tokens,
                cache_creation_tokens=raw.cache_creation_tokens,
                cache_read_tokens=raw.cache_read_tokens,
            )
            s_cold, s_warm = _compute_step_cold_warm(
                rung_id=rung_id,
                finops=fin,
                seen_cache_models=seen_cache_models,
            )
            cum_cold = round(cum_cold + s_cold, 8)
            cum_warm = round(cum_warm + s_warm, 8)

            assistant_blocks = raw.structured.get("assistant_blocks") or []
            tool_uses = raw.structured.get("tool_uses") or []
            thought_text = str(raw.structured.get("thinking_text") or raw.raw_text or "").strip()

            messages.append({"role": "assistant", "content": assistant_blocks})

            executed_traces: list[Cat5ToolCallTrace] = []
            tool_result_blocks: list[dict[str, Any]] = []
            # A turn cut off by max_tokens may hold incomplete tool_use blocks: record them, never execute them.
            # Otherwise every tool_use block is executed whatever the stop_reason (the API can return end_turn
            # together with tool_use blocks) and the loop continues with their results.
            truncated = raw.stop_reason == "max_tokens"
            not_executed = (
                [{"tool_use_id": str(tu.get("id") or ""), "name": str(tu.get("name") or ""), "input": dict(tu.get("input") or {})}
                 for tu in tool_uses]
                if truncated
                else []
            )

            for tu in ([] if truncated else tool_uses):
                t_name = str(tu.get("name") or "")
                t_id = str(tu.get("id") or "")
                t_input = dict(tu.get("input") or {})
                out_str, sql_exec, touched, is_opt, gate_snap = session.execute_tool(t_name, t_input)

                if gate_snap and gate_snap.get("circuit_breaker_halt"):
                    circuit_breaker = True
                if (
                    rung_id == "hybrid_haiku_sonnet_governed"
                    and "haiku" in active_model
                    and gate_snap
                    and gate_snap.get("escalation_required")
                ):
                    active_model = "claude-sonnet-5-5"
                    escalated_on_next = True

                executed_traces.append(
                    Cat5ToolCallTrace(
                        tool_use_id=t_id,
                        tool_name=t_name,
                        tool_input=t_input,
                        sql_executed=sql_exec,
                        tables_touched=touched,
                        is_optimal_call=is_opt,
                        result_preview=out_str[:2200],
                        gate_snapshot=gate_snap,
                    )
                )
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": t_id,
                        "content": out_str,
                    }
                )

            step_obj = Cat5LoopStep(
                step_number=step_idx,
                model_id=raw.model_id,
                escalated_from_haiku=is_escalated_turn,
                stop_reason=raw.stop_reason or "none",
                assistant_thought=thought_text[:1200],
                tool_calls=executed_traces,
                tool_calls_not_executed=not_executed,
                latency_ms=raw.latency_ms,
                finops=fin,
                cumulative_cold_cost_usd=cum_cold,
                cumulative_warm_cost_usd=cum_warm,
            )
            steps.append(step_obj)
            raw_steps.append(
                {
                    "step_number": step_idx,
                    "model_id": raw.model_id,
                    "escalated_from_haiku": is_escalated_turn,
                    "stop_reason": step_obj.stop_reason,
                    "assistant_thought": step_obj.assistant_thought,
                    "tool_calls": [tc.model_dump() for tc in executed_traces],
                    "tool_calls_not_executed": not_executed,
                    "latency_ms": raw.latency_ms,
                    "input_tokens": raw.input_tokens,
                    "output_tokens": raw.output_tokens,
                    "thinking_tokens": int(raw.thinking_tokens or 0),
                    "cache_creation_tokens": raw.cache_creation_tokens,
                    "cache_read_tokens": raw.cache_read_tokens,
                    "max_tokens": CAT5_MAX_TOKENS,
                }
            )

            # Only a turn without tool calls (or a truncated turn) ends the run.
            if truncated or not tool_result_blocks:
                final_readout = raw.raw_text
                break

            messages.append({"role": "user", "content": tool_result_blocks})

        if not final_readout and steps:
            final_readout = steps[-1].assistant_thought

        voucher_dict = session.get_committed_voucher(preset["invoice_id"])
        committed_voucher = (
            Cat5CommittedVoucher(
                voucher_id=str(voucher_dict["voucher_id"]),
                invoice_id=str(voucher_dict["invoice_id"]),
                po_id=str(voucher_dict["po_id"]),
                decision=str(voucher_dict["decision"]),
                authorized_net_principal_inr=float(voucher_dict["authorized_net_principal_inr"]),
                authorized_gst_payout_inr=float(voucher_dict["authorized_gst_payout_inr"]),
                gst_escrow_holdback_inr=float(voucher_dict["gst_escrow_holdback_inr"]),
                debit_note_deduction_inr=float(voucher_dict["debit_note_deduction_inr"]),
                gate_verified=bool(voucher_dict["gate_verified"]),
                audit_summary=str(voucher_dict.get("audit_summary") or ""),
            )
            if voucher_dict
            else None
        )
        evaluation = evaluate_cat5_adjudication(
            committed_voucher=voucher_dict,
            ground_truth=preset["ground_truth"],
            tables_touched=session.tables_touched,
            total_tool_calls=session.total_tool_calls,
            optimal_tool_calls=session.optimal_tool_calls,
            steps_used=len(steps),
            max_step_budget=max_budget,
        )

        result = finalize_cat5_rung_result(
            rung_id=rung_id,
            primary_model_id=primary_model,
            steps=steps,
            committed_voucher=committed_voucher,
            evaluation=evaluation,
            final_readout=final_readout,
            circuit_breaker_triggered=circuit_breaker,
        )
        raw_record: dict[str, Any] = {
            "rung_id": rung_id,
            "primary_model_id": primary_model,
            "steps": raw_steps,
            "final_readout": final_readout,
            "circuit_breaker_triggered": circuit_breaker,
            "committed_voucher": committed_voucher.model_dump() if committed_voucher else None,
            "tables_touched": sorted(session.tables_touched),
            "total_tool_calls": session.total_tool_calls,
            "optimal_tool_calls": session.optimal_tool_calls,
        }
        return result, raw_record
    finally:
        session.close()


def _build_cat5_result_from_replay(
    *,
    rung_id: Cat5RungId,
    preset: dict[str, Any],
    raw_rung: dict[str, Any],
) -> Cat5RungResult:
    seen_cache_models: set[str] = set()
    cum_cold = 0.0
    cum_warm = 0.0
    steps: list[Cat5LoopStep] = []

    for rs in raw_rung.get("steps") or []:
        fin = compute_run_finops(
            model_id=str(rs["model_id"]),
            input_tokens=int(rs["input_tokens"]),
            output_tokens=int(rs["output_tokens"]),
            cache_creation_tokens=int(rs.get("cache_creation_tokens") or 0),
            cache_read_tokens=int(rs.get("cache_read_tokens") or 0),
        )
        s_cold, s_warm = _compute_step_cold_warm(
            rung_id=rung_id,
            finops=fin,
            seen_cache_models=seen_cache_models,
        )
        cum_cold = round(cum_cold + s_cold, 8)
        cum_warm = round(cum_warm + s_warm, 8)
        steps.append(
            Cat5LoopStep(
                step_number=int(rs["step_number"]),
                model_id=str(rs["model_id"]),
                escalated_from_haiku=bool(rs.get("escalated_from_haiku")),
                stop_reason=str(rs.get("stop_reason") or "end_turn"),
                assistant_thought=str(rs.get("assistant_thought") or ""),
                tool_calls=[Cat5ToolCallTrace(**tc) for tc in (rs.get("tool_calls") or [])],
                tool_calls_not_executed=list(rs.get("tool_calls_not_executed") or []),
                latency_ms=int(rs.get("latency_ms") or 0),
                finops=fin,
                cumulative_cold_cost_usd=cum_cold,
                cumulative_warm_cost_usd=cum_warm,
            )
        )

    v_raw = raw_rung.get("committed_voucher")
    committed_voucher = Cat5CommittedVoucher(**v_raw) if v_raw else None
    evaluation = evaluate_cat5_adjudication(
        committed_voucher=v_raw,
        ground_truth=preset["ground_truth"],
        tables_touched=raw_rung.get("tables_touched") or [],
        total_tool_calls=int(raw_rung.get("total_tool_calls") or 0),
        optimal_tool_calls=int(raw_rung.get("optimal_tool_calls") or 0),
        steps_used=len(steps),
        max_step_budget=CAT5_BUDGETS[rung_id],
    )
    return finalize_cat5_rung_result(
        rung_id=rung_id,
        primary_model_id=str(raw_rung.get("primary_model_id") or "claude-sonnet-5-5"),
        steps=steps,
        committed_voucher=committed_voucher,
        evaluation=evaluation,
        final_readout=str(raw_rung.get("final_readout") or ""),
        circuit_breaker_triggered=bool(raw_rung.get("circuit_breaker_triggered")),
    )


def _build_portfolio_scorecard(
    *,
    active_preset_id: str,
    active_results: list[Cat5RungResult],
    replays: dict[str, Any],
) -> list[Cat5PortfolioRungRollup]:
    """Aggregate accuracy, evidence recall, tool precision & FinOps across all 3 ERP invoices."""
    presets_replays = replays.get("presets") or {}
    by_rung_runs: dict[Cat5RungId, list[Cat5RungResult]] = {
        "unbounded_sonnet_loop": [],
        "bounded_sonnet_cached_gate": [],
        "hybrid_haiku_sonnet_governed": [],
    }
    by_rung_presets: dict[str, list[dict[str, Any]]] = {rid: [] for rid in by_rung_runs}
    for preset in CAT5_PRESETS:
        pid = preset["id"]
        if pid == active_preset_id:
            for res in active_results:
                if res.status == "ok":
                    by_rung_runs[res.rung_id].append(res)
                    by_rung_presets[res.rung_id].append(preset)
            continue
        rungs_map = (presets_replays.get(pid) or {}).get("rungs") or {}
        for rid in by_rung_runs:
            if rid in rungs_map:
                by_rung_presets[rid].append(preset)
                by_rung_runs[rid].append(
                    _build_cat5_result_from_replay(
                        rung_id=rid,
                        preset=preset,
                        raw_rung=rungs_map[rid],
                    )
                )

    rollups: list[Cat5PortfolioRungRollup] = []
    naive_cold_avg = 0.0

    for rid in (
        "unbounded_sonnet_loop",
        "bounded_sonnet_cached_gate",
        "hybrid_haiku_sonnet_governed",
    ):
        runs = by_rung_runs[rid]
        if not runs:
            continue
        n = len(runs)
        matched_tot = sum(r.evaluation.matched_fields for r in runs if r.evaluation)
        fields_tot = sum(r.evaluation.total_fields for r in runs if r.evaluation)
        exact_cnt = sum(1 for r in runs if r.evaluation and r.evaluation.exact_match)
        ev_avg = round(
            sum(r.evaluation.evidence_recall_pct for r in runs if r.evaluation) / n, 1
        )
        tp_avg = round(
            sum(r.evaluation.tool_precision_pct for r in runs if r.evaluation) / n, 1
        )
        prompt_avg = round(
            sum(
                r.total_uncached_input_tokens
                + r.total_cache_creation_tokens
                + r.total_cache_read_tokens
                for r in runs
            )
            / n
        )
        out_avg = round(sum(r.total_output_tokens for r in runs) / n)
        cold_1k_avg = round(sum(r.cost_per_1k_invoices_cold_usd for r in runs) / n, 2)
        warm_1k_avg = round(sum(r.cost_per_1k_invoices_warm_usd for r in runs) / n, 2)
        if rid == "unbounded_sonnet_loop":
            naive_cold_avg = cold_1k_avg

        label, _, _ = _rung_metadata(rid)
        if rid == "unbounded_sonnet_loop":
            routing_desc = "claude-sonnet-5-5 (raw tables, uncached, no gate)"
        elif rid == "bounded_sonnet_cached_gate":
            routing_desc = "claude-sonnet-5-5 (bundle + cached policy + gate)"
        else:
            escalated_on = [p["id"] for p, r in zip(by_rung_presets[rid], runs) if r.escalated_to_sonnet]
            routing_desc = (
                f"Haiku 5.5 -> Sonnet 5.5 on {', '.join(escalated_on)}" if escalated_on else "Haiku 5.5 only"
            )
        rollups.append(
            Cat5PortfolioRungRollup(
                rung_id=rid,
                label=label,
                model_routing_summary=routing_desc,
                invoices_evaluated=n,
                avg_steps=round(sum(r.steps_used for r in runs) / n, 1),
                avg_prompt_tokens=prompt_avg,
                avg_output_tokens=out_avg,
                fields_matched=matched_tot,
                fields_total=fields_tot,
                adjudication_accuracy_pct=round((matched_tot / max(1, fields_tot)) * 100, 1),
                exact_vouchers_matched=exact_cnt,
                avg_evidence_recall_pct=ev_avg,
                avg_tool_precision_pct=tp_avg,
                avg_cost_per_1k_cold_usd=cold_1k_avg,
                avg_cost_per_1k_warm_usd=warm_1k_avg,
                savings_vs_naive_cold_pct=round(
                    ((naive_cold_avg - cold_1k_avg) / naive_cold_avg) * 100, 1
                )
                if naive_cold_avg > 0
                else 0.0,
            )
        )
    return rollups


async def execute_cat5_run(
    req: Cat5RunRequest,
    http_request: Request | None = None,
) -> Cat5RunResponse:
    presets = _preset_map()
    preset = presets.get(req.preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Unknown Category 5 preset_id `{req.preset_id}`.")

    run_group_id = str(uuid4())
    replays = load_cat5_replays()
    results: list[Cat5RungResult] = []

    if req.mode == "replay":
        preset_trace = (replays.get("presets") or {}).get(preset["id"])
        if not preset_trace:
            raise HTTPException(
                status_code=404,
                detail=f"Replay trace missing for Category 5 preset {preset['id']}.",
            )
        for rid in req.rungs:
            raw_rung = (preset_trace.get("rungs") or {}).get(rid)
            if not raw_rung:
                raise HTTPException(
                    status_code=404,
                    detail=f"Replay trace missing rung `{rid}` on {preset['id']}.",
                )
            results.append(_build_cat5_result_from_replay(rung_id=rid, preset=preset, raw_rung=raw_rung))
        mode_used = "replay"
    else:
        creds = credit_shield.resolve_live_credentials(
            http_request,
            need_anthropic=True,
            need_gemini=False,
        )
        assert creds.anthropic_api_key

        async def _safe_rung(rid: Cat5RungId) -> Cat5RungResult:
            try:
                res, _ = await _run_live_cat5_for_rung(
                    preset=preset,
                    rung_id=rid,
                    api_key=creds.anthropic_api_key or "",
                )
                return res
            except Exception as exc:
                return finalize_cat5_rung_result(
                    rung_id=rid,
                    primary_model_id="claude-sonnet-5-5",
                    steps=[],
                    committed_voucher=None,
                    evaluation=None,
                    final_readout="",
                    circuit_breaker_triggered=False,
                    status="error",
                    error_message=str(exc)[:300],
                )

        results = list(await asyncio.gather(*(_safe_rung(r) for r in req.rungs)))
        if creds.uses_server_budget:
            total_spend = sum(r.cold_run_cost_usd for r in results if r.status == "ok")
            credit_shield.record_server_spend(total_spend)
        mode_used = "live"

    portfolio = load_cat5_ablation_portfolio()
    _apply_cross_rung_savings(results)
    _apply_measured_claims(results, portfolio)

    # Persist 1 partitioned trace rollup per rung
    for res in results:
        if res.status != "ok":
            continue
        rollup_fin = rollup_multi_call_finops(
            calls=[s.finops for s in res.steps],
            total_cost_usd=res.cold_run_cost_usd,
            model_id="claude-sonnet-5-5" if "sonnet" in res.primary_model_id else "claude-haiku-5-5",
            model_label=res.primary_model_id,
        )
        persist_cat5_trace(
            source_mode=mode_used,
            run_group_id=run_group_id,
            item_id=preset["id"],
            item_title=preset["title"],
            model_id="claude-haiku-5-5"
            if res.rung_id == "hybrid_haiku_sonnet_governed" and not res.escalated_to_sonnet
            else "claude-sonnet-5-5",
            pattern=res.pattern,
            system_instruction=get_cat5_system_prompt(res.rung_id),
            payload_text=build_cat5_user_task_prompt(preset),
            status=res.status,
            latency_ms=res.total_latency_ms,
            finops_dict=rollup_fin.model_dump(),
            raw_text=res.final_readout,
            structured_output={
                "steps_used": res.steps_used,
                "haiku_steps": res.haiku_steps,
                "sonnet_steps": res.sonnet_steps,
                "escalated_to_sonnet": res.escalated_to_sonnet,
                "committed_voucher": res.committed_voucher.model_dump() if res.committed_voucher else None,
                "evaluation": res.evaluation.model_dump() if res.evaluation else None,
            },
            request_params={
                "endpoint": "messages.create",
                "max_tokens": CAT5_MAX_TOKENS,
                "max_step_budget": res.max_step_budget,
                "prefix_cache_enabled": res.rung_id != "unbounded_sonnet_loop",
            },
            stop_reason=res.steps[-1].stop_reason if res.steps else None,
            extra_metadata={"source_endpoint": "/api/cat5/run", "rung_id": res.rung_id},
        )

    scorecard = _build_portfolio_scorecard(
        active_preset_id=preset["id"],
        active_results=results,
        replays=replays,
    )

    callout = _orchestration_callout(preset, results, portfolio)

    return Cat5RunResponse(
        mode_used=mode_used,  # type: ignore[arg-type]
        preset_id=preset["id"],
        use_case="invoice_3way_reconciliation",
        title=preset["title"],
        invoice_id=preset["invoice_id"],
        po_id=preset["po_id"],
        vendor_name=preset["vendor_name"],
        fc_hub=preset["fc_hub"],
        policy_char_count=len(AP_POLICY_MANUAL_MARKDOWN),
        approx_policy_tokens=max(1, round(len(AP_POLICY_MANUAL_MARKDOWN) / 2.8)),
        ground_truth=preset["ground_truth"],
        results=results,
        portfolio_scorecard=scorecard,
        orchestration_callout=callout,
        ablation_portfolio=portfolio,
    )
