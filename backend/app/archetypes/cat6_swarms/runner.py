"""Orchestrates Category 6 Multi-Agent Swarms & Auto Eng (Checkout CI Swarm + CpO)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4
from fastapi import HTTPException, Request

from app.archetypes.cat6_swarms.caps import (
    CALL_TIMEOUT_S,
    cat6_caps_by_role,
    cat6_max_tokens,
)
from app.archetypes.cat6_swarms.prompts import (
    AGENT_ROLE_LABELS,
    CAT6_CODE_SNIPPETS,
    build_cat6_isolated_payload,
    build_cat6_shared_bus_retry_message,
    build_cat6_shared_bus_turn_message,
    format_cat6_failing_checks,
    get_cat6_agent_system_prompt,
)
from app.archetypes.cat6_swarms.sandbox_verifier import (
    evaluate_patch_in_sandbox,
    extract_python_code,
)
from app.config import get_settings
from app.core.anthropic_service import run_cat6_swarm_agent_call
from app.core.credit_shield import credit_shield
from app.core.measured_claims import fmt_pct, set_note
from app.core.pricing import compute_run_finops, rollup_multi_call_finops
from app.core.trace_store import (
    TracePartition,
    TraceRecord,
    TraceRequestEnvelope,
    TraceResponseEnvelope,
    record_trace,
)
from app.data.cat6_fixtures import CAT6_PRESETS, SHARED_REPO_PREFIX_MARKDOWN, UNFILTERED_REPO_AND_TELEMETRY_NOISE
from app.models import (
    Cat6AgentTurnTrace,
    Cat6PortfolioRungRollup,
    Cat6RungId,
    Cat6RungResult,
    Cat6RunRequest,
    Cat6RunResponse,
    Cat6SandboxCheckResult,
    Cat6SandboxReport,
    FinOpsBreakdown,
)

CAT6_CATEGORY = "cat6_multi_agent_swarms"
CAT6_USE_CASE = "checkout_ci_self_healing_swarm"
CAT6_RUNG_TO_PATTERN: dict[str, str] = {
    "unisolated_broadcast_swarm": "unisolated_shared_bus_swarm",
    "isolated_cached_sonnet_swarm": "isolated_repo_cached_swarm",
    "tiered_hybrid_cpo_swarm": "tiered_hybrid_cpo_swarm",
}


def _preset_map() -> dict[str, dict[str, Any]]:
    return {p["id"]: p for p in CAT6_PRESETS}


def load_cat6_replays() -> dict[str, Any]:
    replays_file = Path(get_settings().replays_dir) / "cat6_golden_replays.json"
    if not replays_file.is_file():
        return {"presets": {}}
    return json.loads(replays_file.read_text(encoding="utf-8"))


def _rung_metadata(rung_id: str) -> tuple[str, str, list[str]]:
    if rung_id == "unisolated_broadcast_swarm":
        return (
            "1. Shared-Bus Swarm + Sandbox Gate (Sonnet 5.5)",
            "Without the lever: one shared thread, no cache",
            [
                # replaced with measured sizes by _apply_measured_claims
                "Streams the entire repo standards + unrelated neighbor services & OTel spans uncached across one growing shared thread.",
                # completed with the measured portfolio verified count by _apply_measured_claims
                "Same role instructions, output caps, PR-SANDBOX-GATE-01 and one-retry limit as the isolated rungs; only the context design differs.",
            ],
        )
    if rung_id == "isolated_cached_sonnet_swarm":
        return (
            "2. Isolated + Cached Prefix + Sandbox (Sonnet 5.5)",
            "With the lever: isolated agents + cached repo prefix",
            [
                # replaced with the measured prefix size by _apply_measured_claims
                "Gives every specialist sub-agent a fresh, narrow thread while sharing a byte-identical cached repo prefix (-95% reads across sub-agents).",
                "Runs deterministic PR-SANDBOX-GATE-01 (4 CI unit + 4 adversarial + 2 static AST checks in Python -I) with max-1 bounded self-heal before merge sign-off.",
            ],
        )
    return (
        "3. Tier-Routed Haiku + Sonnet Author Swarm",
        "With the lever, Haiku agents + Sonnet patch author",  # measured CpO change added by _apply_measured_claims
        [
            "Routes Orchestrator Plan, CI Triager, Security Critic & Merge Gate to Claude Haiku 5.5 ($0.10/M in · $0.01/M cache read), reserving Sonnet 5.5 for isolated Patch Authoring.",
            # replaced with the measured portfolio outcome by _apply_measured_claims
            "Same isolated agents, cached repo prefix, PR-SANDBOX-GATE-01 and one-retry limit as the isolated Sonnet rung; only the models differ.",
        ],
    )


def _compute_step_cold_warm(
    *,
    rung_id: str,
    finops: FinOpsBreakdown,
    seen_cache_models: set[str],
) -> tuple[float, float]:
    prefix_tok = finops.cache_creation_tokens + finops.cache_read_tokens
    if rung_id == "unisolated_broadcast_swarm" or prefix_tok <= 0:
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


def persist_cat6_trace(
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
            "max_tokens_by_role": cat6_caps_by_role(),
            "timeout_s": CALL_TIMEOUT_S,
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
            category=CAT6_CATEGORY,
            use_case=CAT6_USE_CASE,
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


def finalize_cat6_rung_result(
    *,
    rung_id: Cat6RungId,
    primary_model_id: str,
    agent_turns: list[Cat6AgentTurnTrace],
    retries_used: int,
    patched_code: str,
    final_signoff_memo: str,
    sandbox_dict: dict[str, Any] | None,
    status: str = "ok",
    error_message: str | None = None,
) -> Cat6RungResult:
    title, badge, notes = _rung_metadata(rung_id)
    pattern = CAT6_RUNG_TO_PATTERN[rung_id]

    haiku_turns = sum(1 for t in agent_turns if "haiku" in t.model_id)
    sonnet_turns = sum(1 for t in agent_turns if "sonnet" in t.model_id)
    tot_in = sum(t.finops.input_tokens for t in agent_turns)
    tot_cw = sum(t.finops.cache_creation_tokens for t in agent_turns)
    tot_cr = sum(t.finops.cache_read_tokens for t in agent_turns)
    tot_out = sum(t.finops.output_tokens for t in agent_turns)

    cold_run = round(agent_turns[-1].cumulative_cold_cost_usd, 8) if agent_turns else 0.0
    warm_run = round(agent_turns[-1].cumulative_warm_cost_usd, 8) if agent_turns else 0.0
    tot_lat = sum(t.latency_ms for t in agent_turns) + (
        int(sandbox_dict.get("execution_ms") or 0) if sandbox_dict else 0
    )

    sandbox_report = (
        Cat6SandboxReport(
            total_checks=int(sandbox_dict["total_checks"]),
            passed_checks=int(sandbox_dict["passed_checks"]),
            ci_unit_passed=int(sandbox_dict["ci_unit_passed"]),
            adversarial_passed=int(sandbox_dict["adversarial_passed"]),
            ast_passed=int(sandbox_dict["ast_passed"]),
            verified_outcome=bool(sandbox_dict["verified_outcome"]),
            execution_ms=int(sandbox_dict["execution_ms"]),
            checks=[Cat6SandboxCheckResult(**c) for c in (sandbox_dict.get("checks") or [])],
            unified_diff=str(sandbox_dict.get("unified_diff") or ""),
        )
        if sandbox_dict
        else None
    )

    cpr_cold = round(cold_run * 1000, 4)
    cpr_warm = round(warm_run * 1000, 4)
    verified = bool(sandbox_report and sandbox_report.verified_outcome)

    return Cat6RungResult(
        rung_id=rung_id,
        rung_title=title,
        badge_text=badge,
        pattern=pattern,
        primary_model_id=primary_model_id,
        status=status,  # type: ignore[arg-type]
        error_message=error_message,
        agent_turns=agent_turns,
        retries_used=retries_used,
        haiku_turns=haiku_turns,
        sonnet_turns=sonnet_turns,
        total_uncached_input_tokens=tot_in,
        total_cache_creation_tokens=tot_cw,
        total_cache_read_tokens=tot_cr,
        total_output_tokens=tot_out,
        cold_run_cost_usd=cold_run,
        warm_run_cost_usd=warm_run,
        cost_per_1k_runs_cold_usd=cpr_cold,
        cost_per_1k_runs_warm_usd=cpr_warm,
        # A run with no verified outcome has no finite CpO; None (not 0.0) so it never reads as "free".
        cpo_cold_per_1k_usd=cpr_cold if verified else None,
        cpo_warm_per_1k_usd=cpr_warm if verified else None,
        total_latency_ms=tot_lat,
        patched_code=patched_code,
        final_signoff_memo=final_signoff_memo,
        sandbox_report=sandbox_report,
        architectural_notes=notes,
    )


def _apply_measured_claims(
    results: list[Cat6RungResult],
    scorecard: list[Cat6PortfolioRungRollup],
) -> None:
    """Rewrite result-dependent rung badges/notes with numbers measured on this run and portfolio."""
    ok = {r.rung_id: r for r in results if r.status == "ok" and r.agent_turns}
    rows = {row.rung_id: row for row in scorecard}
    naive = ok.get("unisolated_broadcast_swarm")
    iso = ok.get("isolated_cached_sonnet_swarm")
    hybrid = ok.get("tiered_hybrid_cpo_swarm")
    if naive:
        prompt = naive.total_uncached_input_tokens + naive.total_cache_creation_tokens + naive.total_cache_read_tokens
        set_note(
            naive,
            0,
            f"Streams the entire ~{len(SHARED_REPO_PREFIX_MARKDOWN) / 1000:.0f}k-char repo standards + "
            f"~{len(UNFILTERED_REPO_AND_TELEMETRY_NOISE) / 1000:.0f}k-char unrelated neighbor services & OTel spans "
            f"uncached across one growing shared thread ({prompt:,} prompt tok this run).",
        )
    if iso:
        prefix = max(t.finops.cache_creation_tokens + t.finops.cache_read_tokens for t in iso.agent_turns)
        set_note(
            iso,
            0,
            "Gives every specialist sub-agent a fresh, narrow thread while sharing a byte-identical "
            f"~{prefix / 1000:.1f}k-tok cached repo prefix (-95% reads across sub-agents).",
        )
    if naive:
        row = rows.get("unisolated_broadcast_swarm")
        if row is not None:
            set_note(
                naive,
                1,
                "Same role instructions, output caps, PR-SANDBOX-GATE-01 and one-retry limit as the isolated rungs; "
                f"{row.verified_outcomes_count}/{row.prs_evaluated} of its {row.prs_evaluated}-incident portfolio "
                f"patches verified ({row.checks_passed_total}/{row.checks_total} sandbox checks).",
            )
    if hybrid:
        row = rows.get("tiered_hybrid_cpo_swarm")
        if row is not None and row.cpo_savings_vs_naive_cold_pct is not None:
            hybrid.badge_text = (
                "With the lever, Haiku agents + Sonnet patch author "
                f"(-{fmt_pct(row.cpo_savings_vs_naive_cold_pct)} portfolio CpO vs rung 1)"
            )
        elif naive:
            hybrid.badge_text = (
                "With the lever, Haiku agents + Sonnet patch author "
                f"(-{fmt_pct(hybrid.savings_vs_naive_cold_pct)} cost/run vs rung 1)"
            )
        if row is not None:
            set_note(
                hybrid,
                1,
                "Same isolated agents, cached repo prefix, PR-SANDBOX-GATE-01 and one-retry limit as the isolated Sonnet rung; "
                f"{row.verified_outcomes_count}/{row.prs_evaluated} of its {row.prs_evaluated}-incident portfolio "
                f"patches verified ({row.checks_passed_total}/{row.checks_total} sandbox checks).",
            )


def _apply_cross_rung_savings(results: list[Cat6RungResult]) -> None:
    naive = next(
        (r for r in results if r.rung_id == "unisolated_broadcast_swarm" and r.status == "ok"),
        None,
    )
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


def _role_model(rung_id: Cat6RungId, role_key: str) -> str:
    if rung_id == "tiered_hybrid_cpo_swarm" and role_key != "patch_author":
        return "claude-haiku-5-5"
    return "claude-sonnet-5-5"


async def _run_live_cat6_for_rung(
    *,
    preset: dict[str, Any],
    rung_id: Cat6RungId,
    api_key: str,
) -> tuple[Cat6RungResult, dict[str, Any]]:
    """Execute one live Category 6 Multi-Agent Swarm run + isolated Python sandbox gate."""
    seen_cache_models: set[str] = set()
    cum_cold = 0.0
    cum_warm = 0.0
    turns: list[Cat6AgentTurnTrace] = []
    raw_turns: list[dict[str, Any]] = []
    patched_code = ""
    retries_used = 0
    final_memo = ""
    sandbox_dict: dict[str, Any] | None = None

    if rung_id == "unisolated_broadcast_swarm":
        # Shared growing bus: same role instructions, caps, sandbox gate and one retry as the isolated rungs.
        bus_messages: list[dict[str, Any]] = []
        step_counter = 0

        async def _call_bus(role_key: str, u_text: str, attempt: int = 1) -> str:
            nonlocal step_counter, cum_cold, cum_warm
            step_counter += 1
            max_tokens = cat6_max_tokens(role_key=role_key)
            bus_messages.append({"role": "user", "content": u_text})
            raw = await run_cat6_swarm_agent_call(
                model_tier="claude-sonnet-5-5",
                shared_repo_prefix="",
                role_instructions=get_cat6_agent_system_prompt(rung_id, role_key),
                messages=[dict(m) for m in bus_messages],
                use_prefix_cache=False,
                api_key=api_key,
                max_tokens=max_tokens,
                timeout_s=CALL_TIMEOUT_S,
            )
            bus_messages.append({"role": "assistant", "content": raw.raw_text})
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
            turn_obj = Cat6AgentTurnTrace(
                step_number=step_counter,
                agent_role=role_key,
                agent_label=AGENT_ROLE_LABELS[role_key],
                model_id=raw.model_id,
                context_mode="shared_omnibus_bus",
                attempt=attempt,
                latency_ms=raw.latency_ms,
                finops=fin,
                cumulative_cold_cost_usd=cum_cold,
                cumulative_warm_cost_usd=cum_warm,
                prompt_preview=u_text[:450],
                output_preview=raw.raw_text[:2000],
            )
            turns.append(turn_obj)
            raw_turns.append(
                {
                    "step_number": step_counter,
                    "agent_role": role_key,
                    "agent_label": turn_obj.agent_label,
                    "model_id": raw.model_id,
                    "context_mode": "shared_omnibus_bus",
                    "attempt": attempt,
                    "max_tokens": max_tokens,
                    "stop_reason": raw.stop_reason,
                    "latency_ms": raw.latency_ms,
                    "input_tokens": raw.input_tokens,
                    "output_tokens": raw.output_tokens,
                    "cache_creation_tokens": raw.cache_creation_tokens,
                    "cache_read_tokens": raw.cache_read_tokens,
                    "prompt_preview": turn_obj.prompt_preview,
                    "output_preview": turn_obj.output_preview,
                }
            )
            return raw.raw_text

        await _call_bus("orchestrator_plan", build_cat6_shared_bus_turn_message(preset, "orchestrator_plan"))
        await _call_bus("ci_triager", build_cat6_shared_bus_turn_message(preset, "ci_triager"))
        author_raw = await _call_bus("patch_author", build_cat6_shared_bus_turn_message(preset, "patch_author"))
        patched_code = extract_python_code(author_raw)
        sandbox_dict = evaluate_patch_in_sandbox(preset["id"], patched_code)
        if not sandbox_dict["verified_outcome"]:
            retries_used = 1
            retry_raw = await _call_bus(
                "patch_author",
                build_cat6_shared_bus_retry_message(preset, format_cat6_failing_checks(sandbox_dict)),
                attempt=2,
            )
            patched_code = extract_python_code(retry_raw)
            sandbox_dict = evaluate_patch_in_sandbox(preset["id"], patched_code)
        await _call_bus(
            "security_critic",
            build_cat6_shared_bus_turn_message(preset, "security_critic", sandbox_report=sandbox_dict),
        )
        final_memo = await _call_bus(
            "orchestrator_merge",
            build_cat6_shared_bus_turn_message(preset, "orchestrator_merge", sandbox_report=sandbox_dict),
        )
        primary_model_id = "claude-sonnet-5-5"
    else:
        # Context-isolated + Byte-identical Cached Repo Prefix + Deterministic Sandbox Gate
        step_counter = 0

        async def _call_isolated(
            role_key: str,
            payload: str,
            attempt: int = 1,
        ) -> str:
            nonlocal step_counter, cum_cold, cum_warm
            step_counter += 1
            model_tier = _role_model(rung_id, role_key)
            max_tokens = cat6_max_tokens(role_key=role_key)
            raw = await run_cat6_swarm_agent_call(
                model_tier=model_tier,
                shared_repo_prefix=SHARED_REPO_PREFIX_MARKDOWN,
                role_instructions=get_cat6_agent_system_prompt(rung_id, role_key),
                messages=[{"role": "user", "content": payload}],
                use_prefix_cache=True,
                api_key=api_key,
                max_tokens=max_tokens,
                timeout_s=CALL_TIMEOUT_S,
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
            turn_obj = Cat6AgentTurnTrace(
                step_number=step_counter,
                agent_role=role_key,
                agent_label=AGENT_ROLE_LABELS[role_key],
                model_id=raw.model_id,
                context_mode="isolated_prefix_cached",
                attempt=attempt,
                latency_ms=raw.latency_ms,
                finops=fin,
                cumulative_cold_cost_usd=cum_cold,
                cumulative_warm_cost_usd=cum_warm,
                prompt_preview=payload[:450],
                output_preview=raw.raw_text[:2000],
            )
            turns.append(turn_obj)
            raw_turns.append(
                {
                    "step_number": step_counter,
                    "agent_role": role_key,
                    "agent_label": turn_obj.agent_label,
                    "model_id": raw.model_id,
                    "context_mode": "isolated_prefix_cached",
                    "attempt": attempt,
                    "max_tokens": max_tokens,
                    "stop_reason": raw.stop_reason,
                    "latency_ms": raw.latency_ms,
                    "input_tokens": raw.input_tokens,
                    "output_tokens": raw.output_tokens,
                    "cache_creation_tokens": raw.cache_creation_tokens,
                    "cache_read_tokens": raw.cache_read_tokens,
                    "prompt_preview": turn_obj.prompt_preview,
                    "output_preview": turn_obj.output_preview,
                }
            )
            return raw.raw_text

        orchestrator_brief = await _call_isolated(
            "orchestrator_plan",
            build_cat6_isolated_payload(preset=preset, role_key="orchestrator_plan"),
        )
        triage_brief = await _call_isolated(
            "ci_triager",
            build_cat6_isolated_payload(
                preset=preset,
                role_key="ci_triager",
                orchestrator_brief=orchestrator_brief,
            ),
        )
        author_raw = await _call_isolated(
            "patch_author",
            build_cat6_isolated_payload(
                preset=preset,
                role_key="patch_author",
                triage_brief=triage_brief,
            ),
            attempt=1,
        )
        patched_code = extract_python_code(author_raw)
        sandbox_dict = evaluate_patch_in_sandbox(preset["id"], patched_code)

        if not sandbox_dict["verified_outcome"]:
            retries_used = 1
            failing_lines = format_cat6_failing_checks(sandbox_dict)
            retry_raw = await _call_isolated(
                "patch_author",
                build_cat6_isolated_payload(
                    preset=preset,
                    role_key="patch_author",
                    triage_brief=triage_brief,
                    retry_feedback=failing_lines,
                ),
                attempt=2,
            )
            patched_code = extract_python_code(retry_raw)
            sandbox_dict = evaluate_patch_in_sandbox(preset["id"], patched_code)

        critic_verdict = await _call_isolated(
            "security_critic",
            build_cat6_isolated_payload(
                preset=preset,
                role_key="security_critic",
                patched_code=patched_code,
                sandbox_report=sandbox_dict,
            ),
        )
        final_memo = await _call_isolated(
            "orchestrator_merge",
            build_cat6_isolated_payload(
                preset=preset,
                role_key="orchestrator_merge",
                sandbox_report=sandbox_dict,
                critic_verdict=critic_verdict,
            ),
        )
        primary_model_id = (
            "claude-haiku-5-5 + claude-sonnet-5-5"
            if rung_id == "tiered_hybrid_cpo_swarm"
            else "claude-sonnet-5-5"
        )

    result = finalize_cat6_rung_result(
        rung_id=rung_id,
        primary_model_id=primary_model_id,
        agent_turns=turns,
        retries_used=retries_used,
        patched_code=patched_code,
        final_signoff_memo=final_memo,
        sandbox_dict=sandbox_dict,
    )
    raw_record: dict[str, Any] = {
        "rung_id": rung_id,
        "primary_model_id": primary_model_id,
        "retries_used": retries_used,
        "agent_turns": raw_turns,
        "patched_code": patched_code,
        "final_signoff_memo": final_memo,
        "sandbox_report": sandbox_dict,
    }
    return result, raw_record


def _build_cat6_result_from_replay(
    *,
    rung_id: Cat6RungId,
    preset: dict[str, Any],
    raw_rung: dict[str, Any],
) -> Cat6RungResult:
    seen_cache_models: set[str] = set()
    cum_cold = 0.0
    cum_warm = 0.0
    turns: list[Cat6AgentTurnTrace] = []

    for rt in raw_rung.get("agent_turns") or []:
        fin = compute_run_finops(
            model_id=str(rt["model_id"]),
            input_tokens=int(rt["input_tokens"]),
            output_tokens=int(rt["output_tokens"]),
            cache_creation_tokens=int(rt.get("cache_creation_tokens") or 0),
            cache_read_tokens=int(rt.get("cache_read_tokens") or 0),
        )
        s_cold, s_warm = _compute_step_cold_warm(
            rung_id=rung_id,
            finops=fin,
            seen_cache_models=seen_cache_models,
        )
        cum_cold = round(cum_cold + s_cold, 8)
        cum_warm = round(cum_warm + s_warm, 8)
        turns.append(
            Cat6AgentTurnTrace(
                step_number=int(rt["step_number"]),
                agent_role=str(rt["agent_role"]),
                agent_label=str(rt.get("agent_label") or AGENT_ROLE_LABELS.get(rt["agent_role"], rt["agent_role"])),
                model_id=str(rt["model_id"]),
                context_mode=rt.get("context_mode")
                or ("shared_omnibus_bus" if rung_id == "unisolated_broadcast_swarm" else "isolated_prefix_cached"),
                attempt=int(rt.get("attempt") or 1),
                latency_ms=int(rt.get("latency_ms") or 0),
                finops=fin,
                cumulative_cold_cost_usd=cum_cold,
                cumulative_warm_cost_usd=cum_warm,
                prompt_preview=str(rt.get("prompt_preview") or ""),
                output_preview=str(rt.get("output_preview") or ""),
            )
        )

    patched_code = str(raw_rung.get("patched_code") or "")
    sandbox_dict = raw_rung.get("sandbox_report")
    if not sandbox_dict and patched_code:
        sandbox_dict = evaluate_patch_in_sandbox(preset["id"], patched_code)

    return finalize_cat6_rung_result(
        rung_id=rung_id,
        primary_model_id=str(raw_rung.get("primary_model_id") or "claude-sonnet-5-5"),
        agent_turns=turns,
        retries_used=int(raw_rung.get("retries_used") or 0),
        patched_code=patched_code,
        final_signoff_memo=str(raw_rung.get("final_signoff_memo") or ""),
        sandbox_dict=sandbox_dict,
    )


def _build_portfolio_scorecard(
    *,
    active_preset_id: str,
    active_results: list[Cat6RungResult],
    replays: dict[str, Any],
) -> list[Cat6PortfolioRungRollup]:
    """Compute Cost per Verified Outcome (CpO) & daily Band 5 tokens across all 3 PRs."""
    presets_replays = replays.get("presets") or {}
    by_rung_runs: dict[Cat6RungId, list[Cat6RungResult]] = {
        "unisolated_broadcast_swarm": [],
        "isolated_cached_sonnet_swarm": [],
        "tiered_hybrid_cpo_swarm": [],
    }
    for preset in CAT6_PRESETS:
        pid = preset["id"]
        if pid == active_preset_id:
            for res in active_results:
                if res.status == "ok":
                    by_rung_runs[res.rung_id].append(res)
            continue
        rungs_map = (presets_replays.get(pid) or {}).get("rungs") or {}
        for rid in by_rung_runs:
            if rid in rungs_map:
                by_rung_runs[rid].append(
                    _build_cat6_result_from_replay(
                        rung_id=rid,
                        preset=preset,
                        raw_rung=rungs_map[rid],
                    )
                )

    rollups: list[Cat6PortfolioRungRollup] = []
    naive_ref_cpo: float | None = None

    for rid in (
        "unisolated_broadcast_swarm",
        "isolated_cached_sonnet_swarm",
        "tiered_hybrid_cpo_swarm",
    ):
        runs = by_rung_runs[rid]
        if not runs:
            continue
        n = len(runs)
        verified_cnt = sum(1 for r in runs if r.sandbox_report and r.sandbox_report.verified_outcome)
        checks_passed = sum(r.sandbox_report.passed_checks for r in runs if r.sandbox_report)
        checks_tot = sum(r.sandbox_report.total_checks for r in runs if r.sandbox_report)
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
        total_cold_1k = sum(r.cost_per_1k_runs_cold_usd for r in runs)
        total_warm_1k = sum(r.cost_per_1k_runs_warm_usd for r in runs)
        avg_cpr_cold = round(total_cold_1k / n, 2)
        avg_cpr_warm = round(total_warm_1k / n, 2)

        # CpO = all spend (failed runs included) / verified outcomes; undefined (None) with zero outcomes.
        cpo_cold = round(total_cold_1k / verified_cnt, 2) if verified_cnt > 0 else None
        cpo_warm = round(total_warm_1k / verified_cnt, 2) if verified_cnt > 0 else None
        if rid == "unisolated_broadcast_swarm":
            naive_ref_cpo = cpo_cold
        cpo_savings = (
            round(((naive_ref_cpo - cpo_cold) / naive_ref_cpo) * 100, 1)
            if naive_ref_cpo is not None and naive_ref_cpo > 0 and cpo_cold is not None
            else None
        )

        label, _, _ = _rung_metadata(rid)
        routing_desc = (
            "Sonnet 5.5 on one shared thread (uncached) + Sandbox"
            if rid == "unisolated_broadcast_swarm"
            else (
                "Sonnet 5.5 Isolated + Cached Repo + Sandbox"
                if rid == "isolated_cached_sonnet_swarm"
                else "Haiku 5.5 Orch/Triage/Critic/Merge + Sonnet Author"
            )
        )
        rollups.append(
            Cat6PortfolioRungRollup(
                rung_id=rid,
                label=label,
                routing_summary=routing_desc,
                prs_evaluated=n,
                verified_outcomes_count=verified_cnt,
                verified_outcome_rate_pct=round((verified_cnt / n) * 100, 1),
                checks_passed_total=checks_passed,
                checks_total=checks_tot,
                avg_prompt_tokens=prompt_avg,
                avg_output_tokens=out_avg,
                daily_tokens_per_dev_at_25_runs=(prompt_avg + out_avg) * 25,
                avg_cpr_cold_per_1k_usd=avg_cpr_cold,
                avg_cpr_warm_per_1k_usd=avg_cpr_warm,
                portfolio_cpo_cold_per_1k_usd=cpo_cold,
                portfolio_cpo_warm_per_1k_usd=cpo_warm,
                cpo_savings_vs_naive_cold_pct=cpo_savings,
            )
        )
    return rollups


async def execute_cat6_run(
    req: Cat6RunRequest,
    http_request: Request | None = None,
) -> Cat6RunResponse:
    presets = _preset_map()
    preset = presets.get(req.preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Unknown Category 6 preset_id `{req.preset_id}`.")

    run_group_id = str(uuid4())
    replays = load_cat6_replays()
    results: list[Cat6RungResult] = []

    if req.mode == "replay":
        preset_trace = (replays.get("presets") or {}).get(preset["id"])
        if not preset_trace:
            raise HTTPException(
                status_code=404,
                detail=f"Replay trace missing for Category 6 preset {preset['id']}.",
            )
        for rid in req.rungs:
            raw_rung = (preset_trace.get("rungs") or {}).get(rid)
            if not raw_rung:
                raise HTTPException(
                    status_code=404,
                    detail=f"Replay trace missing rung `{rid}` on {preset['id']}.",
                )
            results.append(_build_cat6_result_from_replay(rung_id=rid, preset=preset, raw_rung=raw_rung))
        mode_used = "replay"
    else:
        creds = credit_shield.resolve_live_credentials(
            http_request,
            need_anthropic=True,
        )
        assert creds.anthropic_api_key

        async def _safe_rung(rid: Cat6RungId) -> Cat6RungResult:
            try:
                res, _ = await _run_live_cat6_for_rung(
                    preset=preset,
                    rung_id=rid,
                    api_key=creds.anthropic_api_key or "",
                )
                return res
            except Exception as exc:
                return finalize_cat6_rung_result(
                    rung_id=rid,
                    primary_model_id="claude-sonnet-5-5",
                    agent_turns=[],
                    retries_used=0,
                    patched_code="",
                    final_signoff_memo="",
                    sandbox_dict=None,
                    status="error",
                    error_message=str(exc)[:300],
                )

        results = list(await asyncio.gather(*(_safe_rung(r) for r in req.rungs)))
        if creds.uses_server_budget:
            total_spend = sum(r.cold_run_cost_usd for r in results if r.status == "ok")
            credit_shield.record_server_spend(total_spend)
        mode_used = "live"

    _apply_cross_rung_savings(results)

    # Persist 1 partitioned trace rollup per executed rung
    for res in results:
        if res.status != "ok":
            continue
        fin_model = (
            "claude-haiku-5-5"
            if res.rung_id == "tiered_hybrid_cpo_swarm" and res.haiku_turns >= res.sonnet_turns
            else "claude-sonnet-5-5"
        )
        rollup_fin = rollup_multi_call_finops(
            calls=[t.finops for t in res.agent_turns],
            total_cost_usd=res.cold_run_cost_usd,
            model_id=fin_model,
            model_label=res.primary_model_id,
        )
        persist_cat6_trace(
            source_mode=mode_used,
            run_group_id=run_group_id,
            item_id=preset["id"],
            item_title=preset["title"],
            model_id=fin_model,
            pattern=res.pattern,
            system_instruction=get_cat6_agent_system_prompt(res.rung_id, "patch_author"),
            payload_text=f"{preset['pr_id']} ({preset['target_file']})\n{preset['ci_failure_log']}",
            status=res.status,
            latency_ms=res.total_latency_ms,
            finops_dict=rollup_fin.model_dump(),
            raw_text=res.final_signoff_memo or res.patched_code,
            structured_output={
                "haiku_turns": res.haiku_turns,
                "sonnet_turns": res.sonnet_turns,
                "retries_used": res.retries_used,
                "sandbox_report": res.sandbox_report.model_dump() if res.sandbox_report else None,
            },
            request_params={
                "endpoint": "messages.create",
                "prefix_cache_enabled": res.rung_id != "unisolated_broadcast_swarm",
                "max_tokens_by_role": cat6_caps_by_role(),
                "timeout_s": CALL_TIMEOUT_S,
                "code_snippets": list(CAT6_CODE_SNIPPETS.keys()),
            },
            stop_reason="end_turn",
            extra_metadata={"source_endpoint": "/api/cat6/run", "rung_id": res.rung_id},
        )

    scorecard = _build_portfolio_scorecard(
        active_preset_id=preset["id"],
        active_results=results,
        replays=replays,
    )
    _apply_measured_claims(results, scorecard)

    naive = next((r for r in results if r.rung_id == "unisolated_broadcast_swarm" and r.status == "ok"), None)
    iso = next((r for r in results if r.rung_id == "isolated_cached_sonnet_swarm" and r.status == "ok"), None)
    hyb = next((r for r in results if r.rung_id == "tiered_hybrid_cpo_swarm" and r.status == "ok"), None)

    if naive and iso and hyb:
        n_tot = (
            naive.total_uncached_input_tokens
            + naive.total_cache_creation_tokens
            + naive.total_cache_read_tokens
        )
        n_pass = naive.sandbox_report.passed_checks if naive.sandbox_report else 0
        h_pass = hyb.sandbox_report.passed_checks if hyb.sandbox_report else 0
        i_pass = iso.sandbox_report.passed_checks if iso.sandbox_report else 0
        callout = (
            f"Multi-Agent Swarm FinOps ({preset['pr_id']} · {preset['service_name']}), same instructions and sandbox "
            f"gate on every rung: the shared-bus swarm sent {n_tot:,} uncached prompt tokens "
            f"(${naive.cost_per_1k_runs_cold_usd:.2f}/1k runs, sandbox {n_pass}/10). Isolated agents + cached repo "
            f"prefix on Sonnet: ${iso.cost_per_1k_runs_cold_usd:.2f}/1k cold (${iso.cost_per_1k_runs_warm_usd:.2f}/1k "
            f"warm, -{iso.savings_vs_naive_cold_pct:.1f}%, sandbox {i_pass}/10). The same with Haiku agents + a Sonnet "
            f"patch author: ${hyb.cost_per_1k_runs_cold_usd:.2f}/1k cold (${hyb.cost_per_1k_runs_warm_usd:.2f}/1k "
            f"warm, -{hyb.savings_vs_naive_cold_pct:.1f}%, sandbox {h_pass}/10)."
        )
    else:
        callout = (
            "Category 6 compares one swarm with and without isolated agents + a cached repo prefix (same instructions "
            "and PR-SANDBOX-GATE-01 on every rung), on Sonnet and on Haiku agents + a Sonnet patch author, by Cost "
            "per Verified Outcome (CpO)."
        )

    return Cat6RunResponse(
        mode_used=mode_used,  # type: ignore[arg-type]
        preset_id=preset["id"],
        use_case="checkout_ci_self_healing_swarm",
        title=preset["title"],
        pr_id=preset["pr_id"],
        service_name=preset["service_name"],
        target_file=preset["target_file"],
        use_case_tag=preset["use_case_tag"],
        shared_repo_char_count=len(SHARED_REPO_PREFIX_MARKDOWN),
        approx_shared_repo_tokens=max(1, round(len(SHARED_REPO_PREFIX_MARKDOWN) / 3.0)),
        results=results,
        portfolio_scorecard=scorecard,
        swarm_callout=callout,
    )
