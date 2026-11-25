"""Orchestrates Category 3 IT & HR Service Desk 3-Pattern Arena & Interactive Simulator."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4
from fastapi import HTTPException, Request

from app.archetypes.cat3_assistants.prompts import (
    build_cat3_system_handbook,
    get_memory_summarizer_system_prompt,
)
from app.archetypes.cat3_assistants.schemas import SESSION_MEMORY_JSON_SCHEMA
from app.archetypes.cat3_assistants.scoring import (
    cached_quality_keys,
    classify_probe_answer,
    compact_quality,
    fact_hit,
    probes_for,
    quality_metrics,
    score_session,
)
from app.config import get_settings
from app.core.anthropic_service import (
    run_cat3_memory_summarizer,
    run_cat3_service_desk_turn,
)
from app.core.credit_shield import credit_shield
from app.core.measured_claims import set_note
from app.core.pricing import compute_run_finops
from app.core.trace_store import (
    TracePartition,
    TraceRecord,
    TraceRequestEnvelope,
    TraceResponseEnvelope,
    record_trace,
)
from app.data.cat3_fixtures import CAT3_PRESETS
from app.models import (
    Cat3ChatTurnEntry,
    Cat3ChatTurnRequest,
    Cat3ChatTurnResponse,
    Cat3Measure,
    Cat3ProbeResult,
    Cat3QualityPortfolio,
    Cat3RungQuality,
    Cat3RunRequest,
    Cat3RunResponse,
    Cat3RungId,
    Cat3RungSummary,
    Cat3TurnResult,
    FinOpsBreakdown,
)

CAT3_CATEGORY = "cat3_conversational_assistants"
CAT3_USE_CASE = "it_hr_service_desk"
CAT3_RUNG_TO_PATTERN: dict[str, str] = {
    "naive_full_history": "uncached_full_history",
    "prefix_cached_history": "prefix_cached_full_history",
    "prefix_cached_summarized": "prefix_cached_sliding_summary",
}
SUMMARIZER_PATTERN = "sliding_window_memory_compactor"
MAX_VERBATIM_TURNS = 4
KEEP_RECENT_TURNS = 1


def _preset_map() -> dict[str, dict[str, Any]]:
    return {p["id"]: p for p in CAT3_PRESETS}


def load_cat3_replays() -> dict[str, Any]:
    replays_file = Path(get_settings().replays_dir) / "cat3_golden_replays.json"
    if not replays_file.is_file():
        return {"presets": {}}
    return json.loads(replays_file.read_text(encoding="utf-8"))


LIVE_PROBES_REASON = (
    "Recall probes are not run in live mode (each adds paid API calls); the recorded rerun has them."
)
NO_PROBES_REASON = "This recorded capture has no recall probes."


def load_cat3_quality_portfolio() -> Cat3QualityPortfolio | None:
    """Pooled quality-rerun summary (replays/cat3_quality_summary.json); None if absent or unreadable."""
    path = Path(get_settings().replays_dir) / "cat3_quality_summary.json"
    if not path.is_file():
        return None
    try:
        return Cat3QualityPortfolio.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, OSError):
        return None


def build_rung_quality(
    *,
    preset_id: str,
    turn_texts: dict[int, str],
    probe_phase: dict[str, Any] | None,
    probes_unavailable_reason: str | None,
) -> Cat3RungQuality | None:
    """Score one session with the answer key: turn facts and ledger always; probes when recorded."""
    try:
        keys = cached_quality_keys()
    except (OSError, ValueError):
        return None
    probe_rows = list((probe_phase or {}).get("probes") or [])
    answers = {str(p["probe_id"]): str(p.get("answer") or "") for p in probe_rows} if probe_rows else None
    rows = score_session(preset_id=preset_id, turn_texts=turn_texts, probe_answers=answers, keys=keys)
    if not rows:
        return None
    q = compact_quality(quality_metrics([rows]))
    probes: list[Cat3ProbeResult] | None = None
    if answers is not None:
        probes = []
        for key in probes_for(keys, preset_id):
            if key["probe_id"] not in answers:
                continue
            answer = answers[key["probe_id"]]
            hit = fact_hit(answer, key["any_of"])
            probes.append(
                Cat3ProbeResult(
                    probe_id=key["probe_id"],
                    origin_turn=int(key["origin_turn"]),
                    question=key["question"],
                    expected=str(key.get("expected_display") or key["any_of"][0]),
                    answer=answer,
                    hit=hit,
                    outcome=classify_probe_answer(answer, hit),  # type: ignore[arg-type]
                )
            )
    return Cat3RungQuality(
        keys_version=(keys.get("meta") or {}).get("keys_version"),
        turn_recall=Cat3Measure(**q["turn_recall"]),
        ledger_recall=Cat3Measure(**q["ledger_recall"]),
        ledger_by_origin={k: Cat3Measure(**v) for k, v in q["ledger_by_origin"].items()},
        probe_accuracy=Cat3Measure(**q["probe_accuracy"]) if probes is not None else None,
        probes=probes,
        probes_unavailable_reason=None if probes is not None else probes_unavailable_reason,
    )


def _rung_metadata(rung_id: str) -> tuple[str, str, list[str]]:
    if rung_id == "naive_full_history":
        return (
            "1. Uncached Full History (Naive Chat)",
            "Anti-Pattern: Quadratic O(N²) Session",
            [
                # replaced with the measured prefix size by _apply_measured_claims
                "Re-sends the IT/HR Handbook + full verbatim multi-turn log stack at full $2.00/M input price on every turn.",
                "Cumulative session spend explodes quadratically across 10 turns because prior raw JSON/CLI telemetry is re-read repeatedly.",
            ],
        )
    if rung_id == "prefix_cached_history":
        return (
            "2. Prefix Context Caching Only",
            "Lever 1: 95% Cache Read Discount",
            [
                # replaced with the measured prefix size by _apply_measured_claims
                "Attaches cache_control={'type': 'ephemeral'} to the static IT/HR Handbook prefix ($0.10/M on cache hits).",
                "Eliminates static prefix bloat, but uncached verbatim log history still ramps linearly per turn unless compacted.",
                # replaced with this session's measured answer-key scores by _apply_measured_claims
                "Keeps the full verbatim history, so caching changes the cost but not what the model can see.",
            ],
        )
    return (
        "3. Prefix Caching + Sliding-Window Memory",
        "Lever 1 + Lever 2 (Flat Tail)",
        [
            "Combines the cached IT/HR Handbook prefix with automatic Sonnet 5.5 JSON memory compaction whenever more than 4 turns are verbatim ([T1..T3] before T5, +[T4..T6] before T8).",
            # replaced with the measured final-turn context by _apply_measured_claims
            "100% of summarizer input/output spend is billed transparently here — yet net session cost stays lowest while keeping late-turn context bounded.",
            # replaced with this session's measured answer-key scores by _apply_measured_claims
            "Quality trade-off: details the compacted memory drops are no longer available, so specifics from early "
            "turns can't be recalled later in the session.",
        ],
    )


def build_compaction_payload(
    prior_summary: dict[str, Any] | None,
    evicted_turns: list[Cat3ChatTurnEntry],
) -> str:
    payload: dict[str, Any] = {
        "prior_session_memory": prior_summary or {"compacted_through_turn": 0, "note": "First compaction"},
        "newly_evicted_turns": [
            {
                "turn_number": t.turn_number,
                "user_message": t.user_message,
                "assistant_message": t.assistant_message,
            }
            for t in evicted_turns
        ],
    }
    return json.dumps(payload, indent=2)


def assemble_cat3_messages(
    *,
    verbatim_turns: list[Cat3ChatTurnEntry],
    memory_summary: dict[str, Any] | None,
    current_user_message: str,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if memory_summary:
        through_turn = int(memory_summary.get("compacted_through_turn") or 0)
        compact_json = json.dumps(memory_summary, separators=(",", ":"))
        messages.append(
            {
                "role": "user",
                "content": (
                    f"=== COMPACTED SESSION MEMORY STATE (Turns 1–{through_turn}) ===\n"
                    f"{compact_json}"
                ),
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": (
                    f"Session memory state through Turn {through_turn} confirmed. "
                    "Continuing Service Desk diagnosis with recent active turns."
                ),
            }
        )
    for t in verbatim_turns:
        messages.append({"role": "user", "content": t.user_message})
        messages.append({"role": "assistant", "content": t.assistant_message})
    messages.append({"role": "user", "content": current_user_message})
    return messages


def compute_warm_turn_cost(finops: FinOpsBreakdown) -> float:
    """Price cold Turn-1 cache creation tokens at warm shared-prefix cache-read rate ($0.10/M)."""
    if finops.cache_creation_tokens <= 0:
        return finops.total_cost_usd
    warm_fin = compute_run_finops(
        model_id=finops.model_id,
        input_tokens=finops.input_tokens,
        output_tokens=finops.output_tokens,
        cache_creation_tokens=0,
        cache_read_tokens=finops.cache_creation_tokens + finops.cache_read_tokens,
    )
    return warm_fin.total_cost_usd


def estimate_active_context_tokens(
    *,
    system_text: str,
    messages: list[dict[str, Any]],
) -> int:
    total_chars = len(system_text) + sum(len(str(m.get("content") or "")) for m in messages)
    return max(1, round(total_chars / 2.9))


def persist_cat3_trace(
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
    json_schema: dict[str, Any] | None = None,
    stop_reason: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> Path:
    envelope = TraceRequestEnvelope(
        provider="Anthropic",
        endpoint="messages.create",
        system_instruction=system_instruction,
        parameters=request_params
        or {
            "max_tokens": 4096,
            "endpoint": "messages.create",
            "thinking": {"type": "between_tools"},
        },
        json_schema=json_schema,
        input_payload=payload_text,
    )
    record = TraceRecord(
        run_group_id=run_group_id,
        source_mode=source_mode,  # type: ignore[arg-type]
        item_id=item_id,
        item_title=item_title,
        partition=TracePartition(
            category=CAT3_CATEGORY,
            use_case=CAT3_USE_CASE,
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


def finalize_cat3_rung_summary(
    *,
    rung_id: Cat3RungId,
    model_id: str,
    turns: list[Cat3TurnResult],
    status: str = "ok",
    error_message: str | None = None,
) -> Cat3RungSummary:
    title, badge, notes = _rung_metadata(rung_id)
    pattern = CAT3_RUNG_TO_PATTERN[rung_id]

    total_uncached_in = sum(t.finops.input_tokens for t in turns)
    total_c_write = sum(t.finops.cache_creation_tokens for t in turns)
    total_c_read = sum(t.finops.cache_read_tokens for t in turns)
    total_out = sum(t.finops.output_tokens for t in turns)

    sum_calls = sum(1 for t in turns if t.compaction_finops is not None)
    sum_in = sum(t.compaction_finops.input_tokens for t in turns if t.compaction_finops is not None)
    sum_out = sum(t.compaction_finops.output_tokens for t in turns if t.compaction_finops is not None)
    sum_cost = round(
        sum(t.compaction_finops.total_cost_usd for t in turns if t.compaction_finops is not None),
        8,
    )

    total_session_cost = round(turns[-1].cumulative_cost_usd, 8) if turns else 0.0
    warm_session_cost = round(turns[-1].cumulative_warm_cost_usd, 8) if turns else 0.0
    total_latency = sum(t.latency_ms + t.compaction_latency_ms for t in turns)

    return Cat3RungSummary(
        rung_id=rung_id,
        rung_title=title,
        badge_text=badge,
        pattern=pattern,
        model_id=model_id,
        provider="Anthropic",
        status=status,  # type: ignore[arg-type]
        error_message=error_message,
        turns=turns,
        total_uncached_input_tokens=total_uncached_in,
        total_cache_creation_tokens=total_c_write,
        total_cache_read_tokens=total_c_read,
        total_output_tokens=total_out,
        summarizer_calls=sum_calls,
        summarizer_input_tokens=sum_in,
        summarizer_output_tokens=sum_out,
        summarizer_cost_usd=sum_cost,
        total_session_cost_usd=total_session_cost,
        warm_fleet_session_cost_usd=warm_session_cost,
        cost_per_1k_sessions_usd=round(total_session_cost * 1_000, 4),
        warm_cost_per_1k_sessions_usd=round(warm_session_cost * 1_000, 4),
        total_latency_ms=total_latency,
        architectural_notes=notes,
    )


def _cached_prefix_tokens(results: list[Cat3RungSummary]) -> int | None:
    """Measured size of the cached handbook prefix (cache write + read on the first cached turn)."""
    for r in results:
        if r.status == "ok" and r.rung_id != "naive_full_history" and r.turns:
            f = r.turns[0].finops
            if f.cache_creation_tokens + f.cache_read_tokens > 0:
                return f.cache_creation_tokens + f.cache_read_tokens
    return None


def _frac(m: Cat3Measure | None) -> str:
    return f"{m.hits}/{m.total}" if m is not None else "n/a"


def _portfolio_rung(portfolio: Cat3QualityPortfolio | None, rung_id: str):
    return next((r for r in portfolio.rungs if r.rung_id == rung_id), None) if portfolio else None


def _quality_notes(
    results: list[Cat3RungSummary],
    portfolio: Cat3QualityPortfolio | None,
) -> None:
    """Note 3 of the cached rungs: this session's answer-key scores (fallback text stays if unscored)."""
    ok = {r.rung_id: r for r in results if r.status == "ok" and r.quality is not None}
    naive, cached, summ = ok.get("naive_full_history"), ok.get("prefix_cached_history"), ok.get("prefix_cached_summarized")

    def early(r: Cat3RungSummary) -> Cat3Measure | None:
        return r.quality.ledger_by_origin.get("1-3") if r.quality else None

    if cached and cached.quality:
        q = cached.quality
        parts = []
        if q.probe_accuracy is not None:
            parts.append(f"answered {_frac(q.probe_accuracy)} recall questions")
        parts.append(f"kept {_frac(early(cached))} turn 1–3 details in the final summary")
        text = "Keeps the full verbatim history; on this session it " + " and ".join(parts)
        if naive and naive.quality:
            ref = [f"{_frac(naive.quality.probe_accuracy)} recall"] if naive.quality.probe_accuracy is not None else []
            ref.append(f"{_frac(early(naive))} early details")
            text += f" (Rung 1: {', '.join(ref)})"
        set_note(cached, 2, text + ".")

    if summ and summ.quality:
        q = summ.quality
        ref_rung = cached or naive
        ref_label = "Rung 2" if cached else "Rung 1"
        rq = ref_rung.quality if ref_rung else None
        if q.probe_accuracy is not None:
            text = f"Quality trade-off on this session: answered {_frac(q.probe_accuracy)} recall questions"
            if rq is not None and rq.probe_accuracy is not None:
                text += f" vs {_frac(rq.probe_accuracy)} with full history ({ref_label})"
            text += f", and kept {_frac(early(summ))} turn 1–3 details in the final summary"
        else:
            text = f"Quality trade-off on this session: kept {_frac(early(summ))} turn 1–3 details in the final summary"
        if rq is not None:
            text += f" vs {_frac(early(ref_rung))}"
        if q.probe_accuracy is None and q.probes_unavailable_reason:
            text += " (recall probes are not run live)"
        pf_s = _portfolio_rung(portfolio, "prefix_cached_summarized")
        pf_r = _portfolio_rung(portfolio, ref_rung.rung_id) if ref_rung else None
        if pf_s is not None and pf_r is not None and portfolio is not None:
            text += (
                f". Across the {portfolio.runs}-run rerun ({pf_s.runs} sessions per rung): "
                f"{_frac(pf_s.probe_accuracy)} recall questions vs {_frac(pf_r.probe_accuracy)}"
            )
        set_note(summ, 2, text + ".")


def _apply_measured_claims(
    results: list[Cat3RungSummary],
    portfolio: Cat3QualityPortfolio | None = None,
) -> None:
    """Rewrite result-dependent rung notes with numbers measured on this session."""
    ok = {r.rung_id: r for r in results if r.status == "ok" and r.turns}
    naive, cached, summ = ok.get("naive_full_history"), ok.get("prefix_cached_history"), ok.get("prefix_cached_summarized")
    prefix = _cached_prefix_tokens(results)

    def context(t: Any) -> int:
        return t.finops.input_tokens + t.finops.cache_creation_tokens + t.finops.cache_read_tokens

    if naive and prefix:
        set_note(
            naive,
            0,
            f"Re-sends the ~{prefix:,}-tok IT/HR Handbook prefix + full verbatim multi-turn log stack at full "
            "$2.00/M input price on every turn.",
        )
    if cached and prefix:
        set_note(
            cached,
            0,
            "Attaches cache_control={'type': 'ephemeral'} to the static IT/HR Handbook prefix "
            f"(~{prefix:,} tok -> $0.10/M on cache hits).",
        )
    if summ:
        last = summ.turns[-1]
        others = [r.total_session_cost_usd for r in (naive, cached) if r is not None]
        lowest = bool(others) and summ.total_session_cost_usd <= min(others)
        text = (
            "100% of summarizer input/output spend is billed transparently here"
            + (" — yet net session cost stays lowest" if lowest else "")
            + f"{' while holding' if lowest else ', and it holds'} Turn {last.turn_number} context to {context(last):,} tok"
        )
        if naive and len(naive.turns) >= len(summ.turns):
            text += f" (vs {context(naive.turns[len(summ.turns) - 1]):,} uncompacted)"
        set_note(summ, 1, text + ".")
    _quality_notes(results, portfolio)


def _apply_cross_rung_savings(results: list[Cat3RungSummary]) -> None:
    naive = next((r for r in results if r.rung_id == "naive_full_history" and r.status == "ok"), None)
    cached_only = next(
        (r for r in results if r.rung_id == "prefix_cached_history" and r.status == "ok"),
        None,
    )
    naive_cold = naive.total_session_cost_usd if naive else 0.0
    naive_warm = naive.warm_fleet_session_cost_usd if naive else 0.0
    ch_cold = cached_only.total_session_cost_usd if cached_only else 0.0
    ch_warm = cached_only.warm_fleet_session_cost_usd if cached_only else 0.0

    for res in results:
        if res.status != "ok":
            continue
        if naive_cold > 0:
            res.savings_vs_naive_pct = round(
                ((naive_cold - res.total_session_cost_usd) / naive_cold) * 100, 2
            )
        if naive_warm > 0:
            res.warm_savings_vs_naive_pct = round(
                ((naive_warm - res.warm_fleet_session_cost_usd) / naive_warm) * 100, 2
            )
        if ch_cold > 0:
            res.savings_vs_cached_history_pct = round(
                ((ch_cold - res.total_session_cost_usd) / ch_cold) * 100, 2
            )
        if ch_warm > 0:
            res.warm_savings_vs_cached_history_pct = round(
                ((ch_warm - res.warm_fleet_session_cost_usd) / ch_warm) * 100, 2
            )


def _quality_callout(
    summ: Cat3RungSummary,
    cached: Cat3RungSummary,
    portfolio: Cat3QualityPortfolio | None,
) -> str:
    """Quality sentence for the session callout; number-free when this session was not scored."""
    sq, cq = summ.quality, cached.quality
    if sq is None or cq is None:
        return (
            "Compaction is not free of quality cost: specifics the compacted memory drops can't be recalled "
            "later in the session."
        )
    early_s, early_c = sq.ledger_by_origin.get("1-3"), cq.ledger_by_origin.get("1-3")
    if sq.probe_accuracy is not None and cq.probe_accuracy is not None:
        text = (
            f"Quality trade-off: with compaction the assistant answered {_frac(sq.probe_accuracy)} recall questions "
            f"about earlier turns vs {_frac(cq.probe_accuracy)} with full history, and its final summary kept "
            f"{_frac(early_s)} turn 1–3 details vs {_frac(early_c)}"
        )
    else:
        text = (
            f"Quality trade-off: with compaction the final summary kept {_frac(early_s)} turn 1–3 details vs "
            f"{_frac(early_c)} with full history (recall probes are not run live)"
        )
    pf_s = _portfolio_rung(portfolio, "prefix_cached_summarized")
    pf_c = _portfolio_rung(portfolio, "prefix_cached_history")
    if portfolio is not None and pf_s is not None and pf_c is not None:
        text += (
            f"; across the {portfolio.runs}-run rerun ({pf_s.runs} sessions per rung), {_frac(pf_s.probe_accuracy)} vs "
            f"{_frac(pf_c.probe_accuracy)} recall questions"
        )
    return text + "."


async def _run_live_cat3_session_for_rung(
    *,
    preset: dict[str, Any],
    rung_id: Cat3RungId,
    api_key: str,
) -> tuple[Cat3RungSummary, list[dict[str, Any]]]:
    """Run Turns 1..10 sequentially on Sonnet 5.5 for one rung, returning summary + raw capture records."""
    system_text = build_cat3_system_handbook(rung_id, preset["employee_profile"])
    use_cache = rung_id in ("prefix_cached_history", "prefix_cached_summarized")
    summarize = rung_id == "prefix_cached_summarized"

    verbatim_turns: list[Cat3ChatTurnEntry] = []
    memory_summary: dict[str, Any] | None = None
    compacted_count = 0
    cum_cold = 0.0
    cum_warm = 0.0
    turn_results: list[Cat3TurnResult] = []
    raw_capture_turns: list[dict[str, Any]] = []
    used_model = "claude-sonnet-5-5"

    for turn_spec in preset["turns"]:
        t_num = int(turn_spec["turn_number"])
        topic = str(turn_spec["topic_tag"])
        user_msg = str(turn_spec["user_message"])

        compaction_triggered = False
        compaction_finops: FinOpsBreakdown | None = None
        compaction_latency = 0
        compaction_payload_text: str | None = None
        compaction_stop_reason: str | None = None

        if summarize and len(verbatim_turns) >= MAX_VERBATIM_TURNS:
            evict = verbatim_turns[:-KEEP_RECENT_TURNS]
            keep = verbatim_turns[-KEEP_RECENT_TURNS:]
            compaction_payload_text = build_compaction_payload(memory_summary, evict)
            sum_raw = await run_cat3_memory_summarizer(
                compaction_payload=compaction_payload_text,
                system_prompt=get_memory_summarizer_system_prompt(),
                schema=SESSION_MEMORY_JSON_SCHEMA,
                api_key=api_key,
                max_tokens=1600,
            )
            compaction_triggered = True
            compaction_latency = sum_raw.latency_ms
            compaction_stop_reason = sum_raw.stop_reason
            compaction_finops = compute_run_finops(
                model_id=sum_raw.model_id,
                input_tokens=sum_raw.input_tokens,
                output_tokens=sum_raw.output_tokens,
                cache_creation_tokens=sum_raw.cache_creation_tokens,
                cache_read_tokens=sum_raw.cache_read_tokens,
            )
            memory_summary = dict(sum_raw.structured)
            memory_summary["compacted_through_turn"] = evict[-1].turn_number
            compacted_count = int(memory_summary["compacted_through_turn"])
            verbatim_turns = list(keep)
            cum_cold += compaction_finops.total_cost_usd
            cum_warm += compaction_finops.total_cost_usd

        messages = assemble_cat3_messages(
            verbatim_turns=verbatim_turns,
            memory_summary=memory_summary,
            current_user_message=user_msg,
        )
        turn_raw = await run_cat3_service_desk_turn(
            system_text=system_text,
            messages=messages,
            use_prefix_cache=use_cache,
            api_key=api_key,
            max_tokens=4096,
        )
        used_model = turn_raw.model_id
        fin = compute_run_finops(
            model_id=turn_raw.model_id,
            input_tokens=turn_raw.input_tokens,
            output_tokens=turn_raw.output_tokens,
            cache_creation_tokens=turn_raw.cache_creation_tokens,
            cache_read_tokens=turn_raw.cache_read_tokens,
        )
        warm_cost = compute_warm_turn_cost(fin)
        cum_cold = round(cum_cold + fin.total_cost_usd, 8)
        cum_warm = round(cum_warm + warm_cost, 8)

        active_hist = len(verbatim_turns)
        est_active = (
            fin.input_tokens + fin.cache_creation_tokens + fin.cache_read_tokens + fin.output_tokens
        )
        tr = Cat3TurnResult(
            turn_number=t_num,
            topic_tag=topic,
            user_message=user_msg,
            assistant_message=turn_raw.raw_text,
            latency_ms=turn_raw.latency_ms,
            finops=fin,
            cumulative_cost_usd=cum_cold,
            cumulative_warm_cost_usd=cum_warm,
            active_history_turns=active_hist,
            compacted_turns_count=compacted_count,
            memory_summary_snapshot=dict(memory_summary) if memory_summary else None,
            compaction_triggered_before_turn=compaction_triggered,
            compaction_finops=compaction_finops,
            compaction_latency_ms=compaction_latency,
            estimated_active_context_tokens=est_active,
        )
        turn_results.append(tr)
        raw_capture_turns.append(
            {
                "turn_number": t_num,
                "topic_tag": topic,
                "user_message": user_msg,
                "assistant_message": turn_raw.raw_text,
                "model_id": turn_raw.model_id,
                "latency_ms": turn_raw.latency_ms,
                "stop_reason": turn_raw.stop_reason,
                "input_tokens": turn_raw.input_tokens,
                "output_tokens": turn_raw.output_tokens,
                "thinking_tokens": turn_raw.thinking_tokens,
                "cache_creation_tokens": turn_raw.cache_creation_tokens,
                "cache_read_tokens": turn_raw.cache_read_tokens,
                "active_history_turns": active_hist,
                "compacted_turns_count": compacted_count,
                "compaction_triggered_before_turn": compaction_triggered,
                "memory_summary_snapshot": dict(memory_summary) if memory_summary else None,
                "compaction_payload": compaction_payload_text,
                "compaction_model_id": compaction_finops.model_id if compaction_finops else None,
                "compaction_latency_ms": compaction_latency,
                "compaction_input_tokens": compaction_finops.input_tokens if compaction_finops else 0,
                "compaction_output_tokens": compaction_finops.output_tokens if compaction_finops else 0,
                "compaction_stop_reason": compaction_stop_reason,
            }
        )
        verbatim_turns.append(
            Cat3ChatTurnEntry(
                turn_number=t_num,
                user_message=user_msg,
                assistant_message=turn_raw.raw_text,
            )
        )

    summary = finalize_cat3_rung_summary(
        rung_id=rung_id,
        model_id=used_model,
        turns=turn_results,
    )
    return summary, raw_capture_turns


def _build_cat3_summary_from_replay(
    *,
    rung_id: Cat3RungId,
    raw_turns: list[dict[str, Any]],
) -> Cat3RungSummary:
    cum_cold = 0.0
    cum_warm = 0.0
    turn_results: list[Cat3TurnResult] = []
    model_id = "claude-sonnet-5-5"

    for rt in raw_turns:
        model_id = str(rt.get("model_id") or "claude-sonnet-5-5")
        fin = compute_run_finops(
            model_id=model_id,
            input_tokens=int(rt["input_tokens"]),
            output_tokens=int(rt["output_tokens"]),
            cache_creation_tokens=int(rt.get("cache_creation_tokens") or 0),
            cache_read_tokens=int(rt.get("cache_read_tokens") or 0),
        )
        comp_fin: FinOpsBreakdown | None = None
        if rt.get("compaction_triggered_before_turn") and (
            int(rt.get("compaction_input_tokens") or 0) > 0
            or int(rt.get("compaction_output_tokens") or 0) > 0
        ):
            comp_fin = compute_run_finops(
                model_id=str(rt.get("compaction_model_id") or model_id),
                input_tokens=int(rt["compaction_input_tokens"]),
                output_tokens=int(rt["compaction_output_tokens"]),
            )
            cum_cold += comp_fin.total_cost_usd
            cum_warm += comp_fin.total_cost_usd

        cum_cold = round(cum_cold + fin.total_cost_usd, 8)
        cum_warm = round(cum_warm + compute_warm_turn_cost(fin), 8)
        est_active = (
            fin.input_tokens + fin.cache_creation_tokens + fin.cache_read_tokens + fin.output_tokens
        )
        turn_results.append(
            Cat3TurnResult(
                turn_number=int(rt["turn_number"]),
                topic_tag=str(rt["topic_tag"]),
                user_message=str(rt["user_message"]),
                assistant_message=str(rt["assistant_message"]),
                latency_ms=int(rt["latency_ms"]),
                finops=fin,
                cumulative_cost_usd=cum_cold,
                cumulative_warm_cost_usd=cum_warm,
                active_history_turns=int(rt["active_history_turns"]),
                compacted_turns_count=int(rt["compacted_turns_count"]),
                memory_summary_snapshot=rt.get("memory_summary_snapshot"),
                compaction_triggered_before_turn=bool(rt.get("compaction_triggered_before_turn")),
                compaction_finops=comp_fin,
                compaction_latency_ms=int(rt.get("compaction_latency_ms") or 0),
                estimated_active_context_tokens=est_active,
            )
        )
    return finalize_cat3_rung_summary(rung_id=rung_id, model_id=model_id, turns=turn_results)


async def execute_cat3_run(
    req: Cat3RunRequest,
    http_request: Request | None = None,
) -> Cat3RunResponse:
    presets = _preset_map()
    preset = presets.get(req.preset_id)
    if not preset:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown Category 3 preset_id `{req.preset_id}`.",
        )

    run_group_id = str(uuid4())
    results: list[Cat3RungSummary] = []

    if req.mode == "replay":
        replays = load_cat3_replays()
        preset_trace = (replays.get("presets") or {}).get(preset["id"])
        if not preset_trace:
            raise HTTPException(
                status_code=404,
                detail=f"Replay trace missing for Category 3 preset {preset['id']}.",
            )
        for rung_id in req.rungs:
            r_turns = (preset_trace.get("rungs") or {}).get(rung_id)
            if not r_turns:
                raise HTTPException(
                    status_code=404,
                    detail=f"Replay trace missing rung `{rung_id}` on {preset['id']}.",
                )
            summary = _build_cat3_summary_from_replay(rung_id=rung_id, raw_turns=r_turns)
            probe_phase = (preset_trace.get("probe_phase") or {}).get(rung_id)
            summary.quality = build_rung_quality(
                preset_id=preset["id"],
                turn_texts={t.turn_number: t.assistant_message for t in summary.turns},
                probe_phase=probe_phase,
                probes_unavailable_reason=None if probe_phase else NO_PROBES_REASON,
            )
            results.append(summary)
        mode_used = "replay"
    else:
        creds = credit_shield.resolve_live_credentials(
            http_request,
            need_anthropic=True,
            need_gemini=False,
        )
        assert creds.anthropic_api_key

        async def _safe_rung(rid: Cat3RungId) -> Cat3RungSummary:
            try:
                summary, _ = await _run_live_cat3_session_for_rung(
                    preset=preset,
                    rung_id=rid,
                    api_key=creds.anthropic_api_key or "",
                )
                summary.quality = build_rung_quality(
                    preset_id=preset["id"],
                    turn_texts={t.turn_number: t.assistant_message for t in summary.turns},
                    probe_phase=None,
                    probes_unavailable_reason=LIVE_PROBES_REASON,
                )
                return summary
            except Exception as exc:
                return finalize_cat3_rung_summary(
                    rung_id=rid,
                    model_id="claude-sonnet-5-5",
                    turns=[],
                    status="error",
                    error_message=str(exc)[:300],
                )

        results = list(await asyncio.gather(*(_safe_rung(r) for r in req.rungs)))
        if creds.uses_server_budget:
            total_spend = sum(r.total_session_cost_usd for r in results if r.status == "ok")
            credit_shield.record_server_spend(total_spend)
        mode_used = "live"

    portfolio = load_cat3_quality_portfolio()
    _apply_cross_rung_savings(results)
    _apply_measured_claims(results, portfolio)

    handbook_preview = build_cat3_system_handbook(
        "prefix_cached_summarized",
        preset["employee_profile"],
    )

    # Persist 1 partitioned session-rollup trace per rung
    for res in results:
        last_turn = res.turns[-1] if res.turns else None
        first_turn = res.turns[0] if res.turns else None
        rollup_finops = compute_run_finops(
            model_id=res.model_id,
            input_tokens=res.total_uncached_input_tokens + res.summarizer_input_tokens,
            output_tokens=res.total_output_tokens + res.summarizer_output_tokens,
            cache_creation_tokens=res.total_cache_creation_tokens,
            cache_read_tokens=res.total_cache_read_tokens,
        )
        persist_cat3_trace(
            source_mode=mode_used,
            run_group_id=run_group_id,
            item_id=f"{preset['id']}__session_10t",
            item_title=f"{preset['title']} · 10-Turn Session Rollup",
            model_id=res.model_id,
            pattern=res.pattern,
            system_instruction=build_cat3_system_handbook(res.rung_id, preset["employee_profile"]),
            payload_text=json.dumps(
                {
                    "session_turns": len(res.turns),
                    "first_turn_topic": first_turn.topic_tag if first_turn else None,
                    "final_turn_topic": last_turn.topic_tag if last_turn else None,
                    "final_turn_user_prompt": last_turn.user_message if last_turn else "",
                },
                indent=2,
            ),
            status=res.status,
            latency_ms=res.total_latency_ms,
            finops_dict=rollup_finops.model_dump(),
            raw_text=last_turn.assistant_message if last_turn else res.error_message,
            structured_output={
                "turns_completed": len(res.turns),
                "total_session_cost_usd": res.total_session_cost_usd,
                "warm_fleet_session_cost_usd": res.warm_fleet_session_cost_usd,
                "cost_per_1k_sessions_usd": res.cost_per_1k_sessions_usd,
                "warm_cost_per_1k_sessions_usd": res.warm_cost_per_1k_sessions_usd,
                "summarizer_calls": res.summarizer_calls,
                "summarizer_cost_usd": res.summarizer_cost_usd,
                "savings_vs_naive_pct": res.savings_vs_naive_pct,
                "final_memory_summary": last_turn.memory_summary_snapshot if last_turn else None,
                "quality": res.quality.model_dump() if res.quality else None,
            },
            request_params={
                "endpoint": "messages.create",
                "prefix_cache_enabled": res.rung_id != "naive_full_history",
                "sliding_window_compaction": res.rung_id == "prefix_cached_summarized",
                "turns": len(res.turns),
            },
            stop_reason="end_turn" if res.status == "ok" else "error",
            extra_metadata={
                "source_endpoint": "/api/cat3/run",
                "session_turns": len(res.turns),
                "warm_fleet_session_cost_usd": res.warm_fleet_session_cost_usd,
                "savings_vs_naive_pct": res.savings_vs_naive_pct,
            },
        )

    naive_res = next((r for r in results if r.rung_id == "naive_full_history" and r.status == "ok"), None)
    cached_res = next(
        (r for r in results if r.rung_id == "prefix_cached_history" and r.status == "ok"),
        None,
    )
    compacted_res = next(
        (r for r in results if r.rung_id == "prefix_cached_summarized" and r.status == "ok"),
        None,
    )
    measured_prefix = _cached_prefix_tokens(results) or int(preset["approx_handbook_tokens"])
    if naive_res and cached_res and compacted_res:
        callout = (
            f"10-Turn Sonnet 5.5 Session FinOps: Uncached Full History costs ${naive_res.cost_per_1k_sessions_usd:.2f}/1k sessions "
            f"(O(N²) context growth). Enabling Prefix Context Caching (-95% reads on ~{measured_prefix:,}-tok handbook prefix) "
            f"drops cost to ${cached_res.cost_per_1k_sessions_usd:.2f}/1k (-{cached_res.savings_vs_naive_pct:.1f}% cold, "
            f"-{cached_res.warm_savings_vs_naive_pct:.1f}% warm fleet), and adding Sliding-Window Memory Compaction "
            f"({compacted_res.summarizer_calls} Sonnet summarizer calls = ${compacted_res.summarizer_cost_usd * 1000:.2f}/1k overhead included) "
            f"cuts total session spend further to ${compacted_res.cost_per_1k_sessions_usd:.2f}/1k "
            f"(-{compacted_res.savings_vs_naive_pct:.1f}% cold / -{compacted_res.warm_savings_vs_naive_pct:.1f}% warm vs Rung 1)."
        )
        callout += " " + _quality_callout(compacted_res, cached_res, portfolio)
    else:
        callout = (
            "Category 3 compares Uncached Full History vs Prefix Context Caching vs "
            "Prefix Caching + Sliding-Window Memory Summarization on Claude Sonnet 5.5."
        )

    return Cat3RunResponse(
        quality_portfolio=portfolio,
        mode_used=mode_used,  # type: ignore[arg-type]
        preset_id=preset["id"],
        use_case="it_hr_service_desk",
        title=preset["title"],
        employee_profile=preset["employee_profile"],
        handbook_char_count=len(handbook_preview),
        approx_handbook_tokens=int(preset["approx_handbook_tokens"]),
        results=results,
        session_callout=callout,
    )


async def execute_cat3_chat_turn(
    req: Cat3ChatTurnRequest,
    http_request: Request | None = None,
) -> Cat3ChatTurnResponse:
    if req.mode != "live":
        raise HTTPException(
            status_code=400,
            detail=(
                "Interactive Turn-11+ custom follow-ups execute real multi-turn compaction and Anthropic "
                "prefix caching. Switch Credit Shield to Live API mode to send live Turn-11+ messages."
            ),
        )
    user_msg = req.user_message.strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="Enter a non-empty follow-up question.")

    presets = _preset_map()
    preset = presets.get(req.preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Unknown Category 3 preset_id `{req.preset_id}`.")

    creds = credit_shield.resolve_live_credentials(
        http_request,
        need_anthropic=True,
        need_gemini=False,
    )
    assert creds.anthropic_api_key

    verbatim_turns = list(req.prior_turns)
    memory_summary = dict(req.memory_summary) if req.memory_summary else None
    next_turn_num = (verbatim_turns[-1].turn_number + 1) if verbatim_turns else 11
    run_group_id = f"cat3-chat-{uuid4()}"

    compaction_triggered = False
    compaction_finops: FinOpsBreakdown | None = None
    compaction_latency = 0

    if req.rung_id == "prefix_cached_summarized" and len(verbatim_turns) >= MAX_VERBATIM_TURNS:
        evict = verbatim_turns[:-KEEP_RECENT_TURNS]
        keep = verbatim_turns[-KEEP_RECENT_TURNS:]
        comp_payload = build_compaction_payload(memory_summary, evict)
        sum_raw = await run_cat3_memory_summarizer(
            compaction_payload=comp_payload,
            system_prompt=get_memory_summarizer_system_prompt(),
            schema=SESSION_MEMORY_JSON_SCHEMA,
            api_key=creds.anthropic_api_key,
            max_tokens=1600,
        )
        compaction_triggered = True
        compaction_latency = sum_raw.latency_ms
        compaction_finops = compute_run_finops(
            model_id=sum_raw.model_id,
            input_tokens=sum_raw.input_tokens,
            output_tokens=sum_raw.output_tokens,
        )
        memory_summary = dict(sum_raw.structured)
        memory_summary["compacted_through_turn"] = evict[-1].turn_number
        verbatim_turns = list(keep)
        persist_cat3_trace(
            source_mode="live",
            run_group_id=run_group_id,
            item_id=f"{preset['id']}__t{next_turn_num:02d}_compact",
            item_title=f"{preset['title']} · Compaction Before Turn {next_turn_num}",
            model_id=sum_raw.model_id,
            pattern=SUMMARIZER_PATTERN,
            system_instruction=get_memory_summarizer_system_prompt(),
            payload_text=comp_payload,
            status="ok",
            latency_ms=compaction_latency,
            finops_dict=compaction_finops.model_dump(),
            raw_text=sum_raw.raw_text,
            structured_output=memory_summary,
            request_params=sum_raw.request_params,
            json_schema=SESSION_MEMORY_JSON_SCHEMA,
            stop_reason=sum_raw.stop_reason,
            extra_metadata={"source_endpoint": "/api/cat3/chat-turn", "turn_number": next_turn_num},
        )

    system_text = build_cat3_system_handbook(req.rung_id, preset["employee_profile"])
    use_cache = req.rung_id in ("prefix_cached_history", "prefix_cached_summarized")
    messages = assemble_cat3_messages(
        verbatim_turns=verbatim_turns,
        memory_summary=memory_summary,
        current_user_message=user_msg,
    )
    raw = await run_cat3_service_desk_turn(
        system_text=system_text,
        messages=messages,
        use_prefix_cache=use_cache,
        api_key=creds.anthropic_api_key,
        max_tokens=4096,
    )
    fin = compute_run_finops(
        model_id=raw.model_id,
        input_tokens=raw.input_tokens,
        output_tokens=raw.output_tokens,
        cache_creation_tokens=raw.cache_creation_tokens,
        cache_read_tokens=raw.cache_read_tokens,
    )
    if creds.uses_server_budget:
        spend = fin.total_cost_usd + (compaction_finops.total_cost_usd if compaction_finops else 0.0)
        credit_shield.record_server_spend(spend)

    compacted_count = int(memory_summary.get("compacted_through_turn") or 0) if memory_summary else 0
    active_hist = len(verbatim_turns)
    est_active = (
        fin.input_tokens + fin.cache_creation_tokens + fin.cache_read_tokens + fin.output_tokens
    )
    turn_res = Cat3TurnResult(
        turn_number=next_turn_num,
        topic_tag=f"Live Follow-Up Turn {next_turn_num}",
        user_message=user_msg,
        assistant_message=raw.raw_text,
        latency_ms=raw.latency_ms,
        finops=fin,
        cumulative_cost_usd=round(
            fin.total_cost_usd + (compaction_finops.total_cost_usd if compaction_finops else 0.0),
            8,
        ),
        cumulative_warm_cost_usd=round(
            compute_warm_turn_cost(fin)
            + (compaction_finops.total_cost_usd if compaction_finops else 0.0),
            8,
        ),
        active_history_turns=active_hist,
        compacted_turns_count=compacted_count,
        memory_summary_snapshot=memory_summary,
        compaction_triggered_before_turn=compaction_triggered,
        compaction_finops=compaction_finops,
        compaction_latency_ms=compaction_latency,
        estimated_active_context_tokens=est_active,
    )
    persist_cat3_trace(
        source_mode="live",
        run_group_id=run_group_id,
        item_id=f"{preset['id']}__t{next_turn_num:02d}",
        item_title=f"{preset['title']} · Live Turn {next_turn_num}",
        model_id=raw.model_id,
        pattern=CAT3_RUNG_TO_PATTERN[req.rung_id],
        system_instruction=system_text,
        payload_text=json.dumps({"turn": next_turn_num, "messages": messages}, indent=2),
        status="ok",
        latency_ms=raw.latency_ms,
        finops_dict=fin.model_dump(),
        raw_text=raw.raw_text,
        structured_output={
            "turn_number": next_turn_num,
            "active_history_turns": active_hist,
            "compacted_turns_count": compacted_count,
        },
        request_params=raw.request_params,
        stop_reason=raw.stop_reason,
        extra_metadata={"source_endpoint": "/api/cat3/chat-turn", "turn_number": next_turn_num},
    )

    updated_verbatim = [
        *verbatim_turns,
        Cat3ChatTurnEntry(
            turn_number=next_turn_num,
            user_message=user_msg,
            assistant_message=raw.raw_text,
        ),
    ]
    return Cat3ChatTurnResponse(
        mode_used="live",
        preset_id=preset["id"],
        rung_id=req.rung_id,
        turn_result=turn_res,
        updated_verbatim_turns=updated_verbatim,
        updated_memory_summary=memory_summary,
    )
