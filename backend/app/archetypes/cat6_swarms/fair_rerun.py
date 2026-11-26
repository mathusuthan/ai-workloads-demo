"""Category 6 fair-rerun experiment harness: three cells, one record per run, pure analysis helpers.

The design compared is the deck's lever (isolated agents + cached repo prefix) against the same swarm on one
shared bus, all with the same role instructions, output caps, sandbox gate and one retry:

                         Sonnet on every turn        Haiku agents + Sonnet patch author
    without the lever    shared_bus_matched_gate     (not run)
    with the lever       isolated_cached_gate        tiered_gate

This module is importable without an API key. Each arm follows the same control flow as the matching app rung
in `runner.py`, with per-run cold caches and full-text capture of every call.

Records hold raw tokens only (never dollars) so they stay valid if prices change; cost is derived at
analysis time from `app.core.pricing.compute_run_finops`.
"""

from __future__ import annotations

import asyncio
import math
import re
import statistics
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.archetypes.cat6_swarms.caps import (
    CALL_TIMEOUT_S,
    GOVERNED_ROLE_MAX_TOKENS,
    PATCH_AUTHOR_MAX_TOKENS,
    cat6_max_tokens,
)
from app.archetypes.cat6_swarms.prompts import (
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
from app.core.anthropic_service import AnthropicRawResult, run_cat6_swarm_agent_call
from app.core.pricing import LEGACY_MODEL_RATES, MODEL_RATES, compute_run_finops
from app.data.cat6_fixtures import CAT6_PRESETS, SHARED_REPO_PREFIX_MARKDOWN

SCHEMA_VERSION = 1

SONNET_MODEL_ID = "claude-sonnet-5-5"
HAIKU_MODEL_ID = "claude-haiku-5-5"

ROLE_SEQUENCE: tuple[str, ...] = (
    "orchestrator_plan",
    "ci_triager",
    "patch_author",
    "security_critic",
    "orchestrator_merge",
)

# Output caps and timeout live in caps.py, shared with the app's live path (runner.py).

CHECK_CATEGORIES: tuple[str, ...] = ("ci_unit", "adversarial", "ast")

_FENCED_BLOCK_RE = re.compile(r"```(?:python|py)?\s*\n([\s\S]*?)```", flags=re.IGNORECASE)


# --------------------------------------------------------------------------------------------------
# Arm definitions
# --------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ArmSpec:
    arm_id: str
    context: str  # "shared_bus" | "isolated_cached"
    prompt_rung_id: str  # rung id passed to get_cat6_agent_system_prompt
    tiered: bool  # Haiku for every role except patch_author
    gate_enabled: bool  # sandbox gate + max 1 patch-author retry
    context_summary: str
    instructions_summary: str
    models_summary: str

    @property
    def cached(self) -> bool:
        return self.context == "isolated_cached"


ARMS: dict[str, ArmSpec] = {
    spec.arm_id: spec
    for spec in (
        ArmSpec(
            arm_id="shared_bus_matched_gate",
            context="shared_bus",
            prompt_rung_id="unisolated_broadcast_swarm",
            tiered=False,
            gate_enabled=True,
            context_summary="Shared growing thread, repo manual + noise, uncached",
            instructions_summary="Governed per-role prompts (same as the isolated arms)",
            models_summary="Sonnet all turns",
        ),
        ArmSpec(
            arm_id="isolated_cached_gate",
            context="isolated_cached",
            prompt_rung_id="isolated_cached_sonnet_swarm",
            tiered=False,
            gate_enabled=True,
            context_summary="Isolated narrow thread per agent + per-run cached repo prefix",
            instructions_summary="Governed per-role prompts",
            models_summary="Sonnet all turns",
        ),
        ArmSpec(
            arm_id="tiered_gate",
            context="isolated_cached",
            prompt_rung_id="tiered_hybrid_cpo_swarm",
            tiered=True,
            gate_enabled=True,
            context_summary="Isolated narrow thread per agent + per-run cached repo prefix",
            instructions_summary="Governed per-role prompts",
            models_summary="Haiku except patch_author (Sonnet)",
        ),
    )
}
ARM_IDS: tuple[str, ...] = tuple(ARMS)

# The displayed design: the deck's lever (rows) x the models (columns); None = not run.
DESIGN_ROWS: dict[str, str] = {
    "without": "Without: shared bus, same instructions, sandbox check with one retry",
    "with": "With: isolated agents + cached repo prefix, sandbox check with one retry",
}
DESIGN_COLUMNS: dict[str, str] = {
    "sonnet": "Sonnet on every turn",
    "tiered": "Haiku agents + Sonnet patch author",
}
DESIGN_CELLS: dict[tuple[str, str], str | None] = {
    ("without", "sonnet"): "shared_bus_matched_gate",
    ("without", "tiered"): None,
    ("with", "sonnet"): "isolated_cached_gate",
    ("with", "tiered"): "tiered_gate",
}


def _arm(arm_id: str) -> ArmSpec:
    try:
        return ARMS[arm_id]
    except KeyError:
        raise ValueError(f"Unknown fair-rerun arm_id `{arm_id}`; expected one of {list(ARMS)}") from None


def intended_model_id(arm_id: str, role_key: str) -> str:
    if _arm(arm_id).tiered and role_key != "patch_author":
        return HAIKU_MODEL_ID
    return SONNET_MODEL_ID


def max_tokens_for(arm_id: str, role_key: str) -> int:
    """Same caps in every arm (and on every app rung)."""
    _arm(arm_id)
    return cat6_max_tokens(role_key=role_key)


def system_prompt_for(arm_id: str, role_key: str) -> str:
    return get_cat6_agent_system_prompt(_arm(arm_id).prompt_rung_id, role_key)


def build_cached_prefix(run_nonce: str) -> str:
    """Per-run shared prefix: a nonce comment makes each run write (and then read) its own cache."""
    return f"<!-- run:{run_nonce} -->\n" + SHARED_REPO_PREFIX_MARKDOWN


# The shared-bus prompts live in prompts.py, shared with the app's rung 1.
build_matched_bus_turn_message = build_cat6_shared_bus_turn_message
build_matched_bus_retry_message = build_cat6_shared_bus_retry_message
format_failing_checks = format_cat6_failing_checks


# --------------------------------------------------------------------------------------------------
# One run -> one record
# --------------------------------------------------------------------------------------------------

AgentCall = Callable[..., Awaitable[AnthropicRawResult]]
SandboxFn = Callable[[str, str], dict[str, Any]]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def has_fenced_python_block(raw_text: str) -> bool:
    """True when the response contains a complete (closed) fenced code block with content."""
    return any(blk.strip() for blk in _FENCED_BLOCK_RE.findall(raw_text or ""))


def _attempt_summary(raw: AnthropicRawResult, code: str, sandbox_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "patch_extracted": bool(code.strip()) and has_fenced_python_block(raw.raw_text),
        "patch_author_stop_reason": raw.stop_reason,
        "sandbox": sandbox_report,
    }


async def execute_run(
    *,
    arm_id: str,
    preset: dict[str, Any],
    repeat_index: int,
    api_key: str,
    agent_call: AgentCall = run_cat6_swarm_agent_call,
    sandbox: SandboxFn = evaluate_patch_in_sandbox,
) -> dict[str, Any]:
    """Execute ONE live run of `arm_id` on `preset`. Never raises for API/runtime errors."""
    arm = _arm(arm_id)
    run_nonce = uuid4().hex if arm.cached else None
    shared_prefix = build_cached_prefix(run_nonce) if run_nonce else ""
    turns: list[dict[str, Any]] = []
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": str(uuid4()),
        "arm_id": arm_id,
        "preset_id": preset["id"],
        "repeat_index": repeat_index,
        "started_at": _utc_now_iso(),
        "finished_at": None,
        "status": "ok",
        "error_message": None,
        "gate_enabled": arm.gate_enabled,
        "run_nonce": run_nonce,
        "turns": turns,
        "first_attempt": None,
        "final": None,
        "retries_used": 0,
        "patched_code_first": "",
        "patched_code_final": "",
        "final_signoff_memo": "",
    }

    async def call(role_key: str, attempt: int, messages: list[dict[str, Any]]) -> AnthropicRawResult:
        model = intended_model_id(arm_id, role_key)
        cap = max_tokens_for(arm_id, role_key)
        system_prompt = system_prompt_for(arm_id, role_key)
        raw = await agent_call(
            model_tier=model,
            shared_repo_prefix=shared_prefix,
            role_instructions=system_prompt,
            messages=[dict(m) for m in messages],
            use_prefix_cache=arm.cached,
            api_key=api_key,
            max_tokens=cap,
            timeout_s=CALL_TIMEOUT_S,
        )
        turns.append(
            {
                "step_number": len(turns) + 1,
                "agent_role": role_key,
                "attempt": attempt,
                "model_id": raw.model_id,
                "intended_model_id": model,
                "max_tokens": cap,
                "use_prefix_cache": arm.cached,
                "stop_reason": raw.stop_reason,
                "latency_ms": int(raw.latency_ms),
                "input_tokens": int(raw.input_tokens),
                "output_tokens": int(raw.output_tokens),
                "thinking_tokens": int(raw.thinking_tokens or 0),
                "cache_creation_tokens": int(raw.cache_creation_tokens),
                "cache_read_tokens": int(raw.cache_read_tokens),
                "request_params": dict(raw.request_params or {}),
                "system_prompt": system_prompt,
                "user_message": messages[-1]["content"],
                "raw_text": raw.raw_text,
            }
        )
        return raw

    async def judge(code: str) -> dict[str, Any]:
        # The sandbox spawns a subprocess (up to 5 s); keep it off the event loop for concurrent runs.
        return await asyncio.to_thread(sandbox, preset["id"], code)

    try:
        if arm.context == "shared_bus":
            await _run_shared_bus(arm, preset, record, call, judge)
        else:
            await _run_isolated(arm, preset, record, call, judge)
    except Exception as exc:  # noqa: BLE001 — an error is recorded, never raised
        record["status"] = "error"
        record["error_message"] = f"{type(exc).__name__}: {exc}"[:2000]
    record["finished_at"] = _utc_now_iso()
    return record


async def _gate_patch(
    record: dict[str, Any],
    raw: AnthropicRawResult,
    judge: Callable[[str], Awaitable[dict[str, Any]]],
    *,
    first: bool,
) -> dict[str, Any]:
    code = extract_python_code(raw.raw_text)
    sbx = await judge(code)
    summary = _attempt_summary(raw, code, sbx)
    if first:
        record["first_attempt"] = summary
        record["patched_code_first"] = code
    record["final"] = summary
    record["patched_code_final"] = code
    return sbx


async def _run_shared_bus(
    arm: ArmSpec,
    preset: dict[str, Any],
    record: dict[str, Any],
    call: Callable[[str, int, list[dict[str, Any]]], Awaitable[AnthropicRawResult]],
    judge: Callable[[str], Awaitable[dict[str, Any]]],
) -> None:
    bus: list[dict[str, Any]] = []

    async def bus_turn(role_key: str, user_text: str, attempt: int = 1) -> AnthropicRawResult:
        bus.append({"role": "user", "content": user_text})
        raw = await call(role_key, attempt, bus)
        bus.append({"role": "assistant", "content": raw.raw_text})
        return raw

    await bus_turn("orchestrator_plan", build_matched_bus_turn_message(preset, "orchestrator_plan"))
    await bus_turn("ci_triager", build_matched_bus_turn_message(preset, "ci_triager"))
    author = await bus_turn("patch_author", build_matched_bus_turn_message(preset, "patch_author"))
    sbx = await _gate_patch(record, author, judge, first=True)
    if not sbx["verified_outcome"]:
        record["retries_used"] = 1
        retry_text = build_matched_bus_retry_message(preset, format_failing_checks(sbx))
        retry = await bus_turn("patch_author", retry_text, attempt=2)
        sbx = await _gate_patch(record, retry, judge, first=False)
    await bus_turn("security_critic", build_matched_bus_turn_message(preset, "security_critic", sandbox_report=sbx))
    merge = await bus_turn(
        "orchestrator_merge",
        build_matched_bus_turn_message(preset, "orchestrator_merge", sandbox_report=sbx),
    )
    record["final_signoff_memo"] = merge.raw_text


async def _run_isolated(
    arm: ArmSpec,
    preset: dict[str, Any],
    record: dict[str, Any],
    call: Callable[[str, int, list[dict[str, Any]]], Awaitable[AnthropicRawResult]],
    judge: Callable[[str], Awaitable[dict[str, Any]]],
) -> None:
    """Same control flow as runner._run_live_cat6_for_rung's isolated branch."""

    async def iso_turn(role_key: str, payload: str, attempt: int = 1) -> AnthropicRawResult:
        return await call(role_key, attempt, [{"role": "user", "content": payload}])

    plan = await iso_turn(
        "orchestrator_plan",
        build_cat6_isolated_payload(preset=preset, role_key="orchestrator_plan"),
    )
    triage = await iso_turn(
        "ci_triager",
        build_cat6_isolated_payload(preset=preset, role_key="ci_triager", orchestrator_brief=plan.raw_text),
    )
    author = await iso_turn(
        "patch_author",
        build_cat6_isolated_payload(preset=preset, role_key="patch_author", triage_brief=triage.raw_text),
    )
    sbx = await _gate_patch(record, author, judge, first=True)
    if arm.gate_enabled and not sbx["verified_outcome"]:
        record["retries_used"] = 1
        retry = await iso_turn(
            "patch_author",
            build_cat6_isolated_payload(
                preset=preset,
                role_key="patch_author",
                triage_brief=triage.raw_text,
                retry_feedback=format_failing_checks(sbx),
            ),
            attempt=2,
        )
        sbx = await _gate_patch(record, retry, judge, first=False)
    critic = await iso_turn(
        "security_critic",
        build_cat6_isolated_payload(
            preset=preset,
            role_key="security_critic",
            patched_code=record["patched_code_final"],
            sandbox_report=sbx,
        ),
    )
    merge = await iso_turn(
        "orchestrator_merge",
        build_cat6_isolated_payload(
            preset=preset,
            role_key="orchestrator_merge",
            sandbox_report=sbx,
            critic_verdict=critic.raw_text,
        ),
    )
    record["final_signoff_memo"] = merge.raw_text


# --------------------------------------------------------------------------------------------------
# Matrix planning, resume selection, budget guard (pure)
# --------------------------------------------------------------------------------------------------

RunKey = tuple[str, str, int]  # (arm_id, preset_id, repeat_index)


def record_key(record: dict[str, Any]) -> RunKey:
    return (str(record["arm_id"]), str(record["preset_id"]), int(record["repeat_index"]))


def plan_matrix(arm_ids: Sequence[str], preset_ids: Sequence[str], repeats: int) -> list[RunKey]:
    """Interleaved order (repeat, then preset, then arm) so a partial run stays balanced."""
    return [(a, p, r) for r in range(repeats) for p in preset_ids for a in arm_ids]


def select_pending(planned: Iterable[RunKey], existing_records: Iterable[dict[str, Any]]) -> list[RunKey]:
    """Keys still to run: any key without an `ok` record. Sandbox-failed `ok` runs are outcomes, not retried."""
    done = {record_key(r) for r in existing_records if r.get("status") == "ok"}
    return [k for k in planned if k not in done]


def _price_turn(turn: dict[str, Any], *, cache_creation: int, cache_read: int) -> float:
    model_id = str(turn.get("model_id") or "")
    if model_id not in MODEL_RATES and model_id not in LEGACY_MODEL_RATES:
        model_id = str(turn["intended_model_id"])
    return compute_run_finops(
        model_id=model_id,
        input_tokens=int(turn.get("input_tokens") or 0),
        output_tokens=int(turn.get("output_tokens") or 0),
        cache_creation_tokens=cache_creation,
        cache_read_tokens=cache_read,
    ).total_cost_usd


def turn_billed_cost_usd(turn: dict[str, Any]) -> float:
    """Billed cost of one call, from its recorded tokens priced at the returned model's rates.

    Note: `output_tokens` already includes any thinking tokens, so thinking is not priced separately.
    """
    return _price_turn(
        turn,
        cache_creation=int(turn.get("cache_creation_tokens") or 0),
        cache_read=int(turn.get("cache_read_tokens") or 0),
    )


def record_billed_cost_usd(record: dict[str, Any]) -> float:
    return sum(turn_billed_cost_usd(t) for t in record.get("turns") or [])


def cold_warm_costs_usd(turns: Sequence[dict[str, Any]], *, cached_arm: bool) -> tuple[float, float]:
    """Run-level (cold, warm) cost, modelled exactly like runner._compute_step_cold_warm.

    For a cached arm, the prefix on a turn is cache_creation + cache_read. Cold: the first call per model
    writes the whole prefix and later calls read it. Warm: every call reads it. Uncached arms (or turns with
    no prefix tokens) cost the same as billed in both views.
    """
    seen_models: set[str] = set()
    cold = 0.0
    warm = 0.0
    for t in turns:
        prefix = int(t.get("cache_creation_tokens") or 0) + int(t.get("cache_read_tokens") or 0)
        if not cached_arm or prefix <= 0:
            billed = turn_billed_cost_usd(t)
            cold += billed
            warm += billed
            continue
        model_id = str(t.get("model_id") or "")
        is_first_cold = model_id not in seen_models
        seen_models.add(model_id)
        cold += _price_turn(t, cache_creation=prefix if is_first_cold else 0, cache_read=0 if is_first_cold else prefix)
        warm += _price_turn(t, cache_creation=0, cache_read=prefix)
    return round(cold, 8), round(warm, 8)


class BudgetGuard:
    """Running billed-cost total; stop launching new runs once it reaches `max_usd`."""

    def __init__(self, max_usd: float, existing_records: Iterable[dict[str, Any]] = ()) -> None:
        self.max_usd = float(max_usd)
        self.spent_usd = sum(record_billed_cost_usd(r) for r in existing_records)

    def add(self, record: dict[str, Any]) -> float:
        cost = record_billed_cost_usd(record)
        self.spent_usd += cost
        return cost

    @property
    def exhausted(self) -> bool:
        return self.spent_usd >= self.max_usd


# --------------------------------------------------------------------------------------------------
# Analysis (pure)
# --------------------------------------------------------------------------------------------------


def wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float] | None:
    """95% Wilson score interval for a binomial proportion; None when n == 0."""
    if n <= 0:
        return None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, centre - half), min(1.0, centre + half)


def _verified(attempt: dict[str, Any] | None) -> bool:
    return bool(attempt and (attempt.get("sandbox") or {}).get("verified_outcome"))


def _checks(attempt: dict[str, Any] | None) -> tuple[int, int]:
    sbx = (attempt or {}).get("sandbox") or {}
    return int(sbx.get("passed_checks") or 0), int(sbx.get("total_checks") or 10)


def _dist(values: Sequence[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "min": None, "max": None}
    return {"mean": statistics.fmean(values), "min": min(values), "max": max(values)}


def _rate(k: int, n: int) -> float | None:
    return k / n if n else None


def _per_verified(total: float, verified: int) -> float | None:
    return total / verified if verified > 0 else None


def model_fallbacks(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every turn whose returned model differs from the one intended (a silent fallback invalidates a run)."""
    out: list[dict[str, Any]] = []
    for r in records:
        for t in r.get("turns") or []:
            if t.get("model_id") != t.get("intended_model_id"):
                out.append(
                    {
                        "run_id": r.get("run_id"),
                        "arm_id": r.get("arm_id"),
                        "preset_id": r.get("preset_id"),
                        "repeat_index": r.get("repeat_index"),
                        "status": r.get("status"),
                        "step_number": t.get("step_number"),
                        "agent_role": t.get("agent_role"),
                        "intended_model_id": t.get("intended_model_id"),
                        "model_id": t.get("model_id"),
                    }
                )
    return out


def max_tokens_stopped_turns(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every turn that stopped on `max_tokens`, with enough context to locate it."""
    return [
        {
            "run_id": r.get("run_id"),
            "arm_id": r.get("arm_id"),
            "preset_id": r.get("preset_id"),
            "repeat_index": r.get("repeat_index"),
            "status": r.get("status"),
            "step_number": t.get("step_number"),
            "agent_role": t.get("agent_role"),
            "attempt": t.get("attempt"),
            "max_tokens": t.get("max_tokens"),
            "output_tokens": t.get("output_tokens"),
        }
        for r in records
        for t in r.get("turns") or []
        if t.get("stop_reason") == "max_tokens"
    ]


def compute_group_metrics(runs: Sequence[dict[str, Any]], *, cached_arm: bool) -> dict[str, Any]:
    """Metrics over a set of `ok` records (one arm, or one arm x preset)."""
    n = len(runs)
    first_ver = sum(1 for r in runs if _verified(r.get("first_attempt")))
    final_ver = sum(1 for r in runs if _verified(r.get("final")))
    first_checks = [_checks(r.get("first_attempt")) for r in runs]
    final_checks = [_checks(r.get("final")) for r in runs]
    retries = sum(int(r.get("retries_used") or 0) for r in runs)
    rescued = sum(
        1
        for r in runs
        if int(r.get("retries_used") or 0) > 0 and not _verified(r.get("first_attempt")) and _verified(r.get("final"))
    )

    failed = [r for r in runs if not _verified(r.get("final"))]
    runs_failing_cat = {c: 0 for c in CHECK_CATEGORIES}
    checks_failing_cat = {c: 0 for c in CHECK_CATEGORIES}
    for r in failed:
        cats = [
            str(c.get("category"))
            for c in ((r.get("final") or {}).get("sandbox") or {}).get("checks") or []
            if not c.get("passed")
        ]
        for cat in set(cats):
            runs_failing_cat[cat] = runs_failing_cat.get(cat, 0) + 1
        for cat in cats:
            checks_failing_cat[cat] = checks_failing_cat.get(cat, 0) + 1
    failed_author_truncated = sum(
        1 for r in failed if (r.get("final") or {}).get("patch_author_stop_reason") == "max_tokens"
    )
    failed_no_patch = sum(1 for r in failed if not (r.get("final") or {}).get("patch_extracted"))

    all_turns = [t for r in runs for t in r.get("turns") or []]
    by_role: dict[str, dict[str, int]] = {}
    for t in all_turns:
        slot = by_role.setdefault(str(t.get("agent_role")), {"max_tokens": 0, "total": 0})
        slot["total"] += 1
        if t.get("stop_reason") == "max_tokens":
            slot["max_tokens"] += 1
    truncated_total = sum(v["max_tokens"] for v in by_role.values())

    def tok(field: str) -> dict[str, float | None]:
        return _dist([sum(int(t.get(field) or 0) for t in r.get("turns") or []) for r in runs])

    billed = [record_billed_cost_usd(r) for r in runs]
    cw = [cold_warm_costs_usd(r.get("turns") or [], cached_arm=cached_arm) for r in runs]
    cold = [c for c, _ in cw]
    warm = [w for _, w in cw]
    totals = {"billed": sum(billed), "cold": sum(cold), "warm": sum(warm)}
    latencies = [sum(int(t.get("latency_ms") or 0) for t in r.get("turns") or []) for r in runs]

    return {
        "runs": n,
        "first_attempt_verified": first_ver,
        "first_attempt_verified_rate": _rate(first_ver, n),
        "first_attempt_verified_wilson95": wilson_interval(first_ver, n),
        "final_verified": final_ver,
        "final_verified_rate": _rate(final_ver, n),
        "final_verified_wilson95": wilson_interval(final_ver, n),
        "first_attempt_checks_passed": sum(p for p, _ in first_checks),
        "first_attempt_checks_total": sum(t for _, t in first_checks),
        "final_checks_passed": sum(p for p, _ in final_checks),
        "final_checks_total": sum(t for _, t in final_checks),
        "retries_used": retries,
        "retries_fail_to_pass": rescued,
        "failure_breakdown": {
            "final_failed_runs": len(failed),
            "runs_with_failing_category": runs_failing_cat,
            "failing_checks_by_category": checks_failing_cat,
            "patch_author_stopped_on_max_tokens": failed_author_truncated,
            "no_fenced_patch_extracted": failed_no_patch,
        },
        "max_tokens_stops": {"turns": truncated_total, "total_turns": len(all_turns), "by_role": by_role},
        "tokens_per_run": {
            "uncached_input": tok("input_tokens"),
            "cache_write": tok("cache_creation_tokens"),
            "cache_read": tok("cache_read_tokens"),
            "output": tok("output_tokens"),
            "thinking": tok("thinking_tokens"),
        },
        "cost_per_run_usd": {"billed": _dist(billed), "cold": _dist(cold), "warm": _dist(warm)},
        "cost_per_1k_runs_usd": {
            view: (statistics.fmean(vals) * 1000 if vals else None)
            for view, vals in (("billed", billed), ("cold", cold), ("warm", warm))
        },
        "total_spend_usd": totals,
        "cost_per_verified_outcome_usd": {view: _per_verified(total, final_ver) for view, total in totals.items()},
        "cost_per_first_attempt_verified_outcome_usd": {
            view: _per_verified(total, first_ver) for view, total in totals.items()
        },
        "model_latency_ms_per_run": _dist([float(x) for x in latencies]),
    }


def summarise(
    records: Sequence[dict[str, Any]],
    *,
    arm_ids: Sequence[str] = ARM_IDS,
    preset_ids: Sequence[str] | None = None,
    expected_repeats: int | None = None,
) -> dict[str, Any]:
    """Summarise fair-rerun records: latest ok record per key, errors counted separately."""
    preset_ids = [p["id"] for p in CAT6_PRESETS] if preset_ids is None else list(preset_ids)
    arm_ids = list(arm_ids)

    latest_ok: dict[RunKey, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    for r in records:
        if r.get("status") == "ok":
            latest_ok[record_key(r)] = r  # file order: later wins
        else:
            errors.append(r)
    superseded_ok = sum(1 for r in records if r.get("status") == "ok") - len(latest_ok)

    if expected_repeats is None:
        idx = [int(r["repeat_index"]) for r in records if "repeat_index" in r]
        expected_repeats = (max(idx) + 1) if idx else 0
    expected = plan_matrix(arm_ids, preset_ids, expected_repeats)
    missing = [k for k in expected if k not in latest_ok]

    def ok_runs(arm_id: str, preset_id: str | None = None) -> list[dict[str, Any]]:
        return [
            r
            for (a, p, _), r in sorted(latest_ok.items())
            if a == arm_id and (preset_id is None or p == preset_id)
        ]

    def err_count(arm_id: str, preset_id: str | None = None) -> int:
        return sum(
            1 for r in errors if r.get("arm_id") == arm_id and (preset_id is None or r.get("preset_id") == preset_id)
        )

    arms_out: dict[str, Any] = {}
    for arm_id in arm_ids:
        spec = ARMS[arm_id]
        m = compute_group_metrics(ok_runs(arm_id), cached_arm=spec.cached)
        m["error_records"] = err_count(arm_id)
        m["missing_keys"] = [list(k) for k in missing if k[0] == arm_id]
        m["by_preset"] = {}
        for pid in preset_ids:
            pm = compute_group_metrics(ok_runs(arm_id, pid), cached_arm=spec.cached)
            pm["error_records"] = err_count(arm_id, pid)
            m["by_preset"][pid] = pm
        arms_out[arm_id] = m

    cell_counts = {(a, p): len(ok_runs(a, p)) for a in arm_ids for p in preset_ids}
    balanced = len(set(cell_counts.values())) <= 1

    ok_list = [r for _, r in sorted(latest_ok.items())]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "design": {
            "rows": DESIGN_ROWS,
            "columns": DESIGN_COLUMNS,
            "cells": {f"{r}|{c}": arm for (r, c), arm in DESIGN_CELLS.items()},
        },
        "arm_ids": arm_ids,
        "preset_ids": preset_ids,
        "expected_repeats": expected_repeats,
        "record_count": len(records),
        "ok_runs_used": len(latest_ok),
        "superseded_ok_records": superseded_ok,
        "error_records": len(errors),
        "matrix": {
            "expected_runs": len(expected),
            "complete": not missing,
            "balanced": balanced,
            "missing_keys": [list(k) for k in missing],
            "ok_runs_per_cell": {f"{a}|{p}": n for (a, p), n in cell_counts.items()},
        },
        "errors": [
            {
                "run_id": r.get("run_id"),
                "arm_id": r.get("arm_id"),
                "preset_id": r.get("preset_id"),
                "repeat_index": r.get("repeat_index"),
                "completed_turns": len(r.get("turns") or []),
                "billed_usd": record_billed_cost_usd(r),
                "error_message": r.get("error_message"),
            }
            for r in errors
        ],
        "error_spend_usd": sum(record_billed_cost_usd(r) for r in errors),
        "model_fallbacks": model_fallbacks([*ok_list, *errors]),
        "max_tokens_stopped_turns": max_tokens_stopped_turns([*ok_list, *errors]),
        "arms": arms_out,
    }
