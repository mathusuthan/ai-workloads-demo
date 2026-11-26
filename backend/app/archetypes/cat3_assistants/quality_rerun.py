"""Category 3 quality rerun: per-run orchestration, deterministic answer-key scoring and pure summaries.

Importable without an API key. Nothing here changes the behaviour of `runner.py`: the turn loop below
follows `_run_live_cat3_session_for_rung` exactly (same compaction rule and constants, same max_tokens,
same message assembly via the imported helpers) but records every call in full, adds a per-run nonce to
the system text for ALL rungs, and appends independent "turn 11" recall probes after turn 10.

Records hold raw tokens only (never dollars); cost is derived at analysis time from
`app.core.pricing.compute_run_finops` and `runner.compute_warm_turn_cost`.
"""

from __future__ import annotations

import asyncio
import statistics
from collections.abc import Awaitable, Callable, Iterable, Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.archetypes.cat3_assistants.prompts import (
    build_cat3_system_handbook,
    get_memory_summarizer_system_prompt,
)
from app.archetypes.cat3_assistants.runner import (
    KEEP_RECENT_TURNS,
    MAX_VERBATIM_TURNS,
    assemble_cat3_messages,
    build_compaction_payload,
    compute_warm_turn_cost,
)
from app.archetypes.cat3_assistants.schemas import SESSION_MEMORY_JSON_SCHEMA
from app.archetypes.cat3_assistants.scoring import (  # noqa: F401 — re-exported for scripts/tests
    KEYS_PATH,
    LEDGER_WINDOWS,
    NORMALISATION_RULES,
    PROBE_WINDOWS,
    TURN_WINDOWS,
    all_scored_items,
    compact_quality,
    contains_alternative,
    fact_hit,
    key_counts,
    load_quality_keys,
    normalise_text,
    probes_for,
    quality_metrics,
    score_reply,
    score_session,
)
from app.core.anthropic_service import (
    AnthropicRawResult,
    run_cat3_memory_summarizer,
    run_cat3_service_desk_turn,
)
from app.core.pricing import LEGACY_MODEL_RATES, MODEL_RATES, compute_run_finops
from app.data.cat3_fixtures import CAT3_PRESETS
from app.models import Cat3ChatTurnEntry

SCHEMA_VERSION = 1
SONNET_MODEL_ID = "claude-sonnet-5-5"
# The two versions the app and every summary show: without and with the deck improvement.
RUNG_IDS: tuple[str, ...] = ("naive_full_history", "prefix_cached_summarized")
# Another lever the harness can still run (prefix caching alone); its records live in
# experiments/cat3_quality/other_levers/ and nothing displayed reads them.
OTHER_LEVER_RUNG_IDS: tuple[str, ...] = ("prefix_cached_history",)
HARNESS_RUNG_IDS: tuple[str, ...] = (*RUNG_IDS, *OTHER_LEVER_RUNG_IDS)
CACHED_RUNGS: frozenset[str] = frozenset({"prefix_cached_history", "prefix_cached_summarized"})
SUMMARIZED_RUNG = "prefix_cached_summarized"

# Same caps as runner._run_live_cat3_session_for_rung.
TURN_MAX_TOKENS = 4096
SUMMARIZER_MAX_TOKENS = 1600
PROBE_MAX_TOKENS = 4096
PROBE_CONCURRENCY = 3
# Longer than the 60 s production default so a slow call is not silently retried (and double-billed)
# by the SDK; it does not change what the model sees.
CALL_TIMEOUT_S = 180.0

CONTEXT_TURNS: tuple[int, ...] = (1, 3, 6, 10)

TurnCall = Callable[..., Awaitable[AnthropicRawResult]]
SummarizerCall = Callable[..., Awaitable[AnthropicRawResult]]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rung(rung_id: str) -> str:
    if rung_id not in HARNESS_RUNG_IDS:
        raise ValueError(f"Unknown Category 3 rung_id `{rung_id}`; expected one of {list(HARNESS_RUNG_IDS)}")
    return rung_id


def build_run_system_text(rung_id: str, employee_profile: dict[str, Any], run_nonce: str) -> str:
    """Production system text with a per-run nonce comment prepended (identical treatment for every rung)."""
    return f"<!-- run:{run_nonce} -->\n" + build_cat3_system_handbook(_rung(rung_id), employee_profile)


# --------------------------------------------------------------------------------------------------
# One run -> one record
# --------------------------------------------------------------------------------------------------


def _usage(raw: AnthropicRawResult) -> dict[str, Any]:
    return {
        "model_id": raw.model_id,
        "stop_reason": raw.stop_reason,
        "latency_ms": int(raw.latency_ms),
        "input_tokens": int(raw.input_tokens),
        "output_tokens": int(raw.output_tokens),
        "thinking_tokens": int(raw.thinking_tokens or 0),
        "cache_creation_tokens": int(raw.cache_creation_tokens),
        "cache_read_tokens": int(raw.cache_read_tokens),
    }


async def _compact(
    *,
    verbatim: list[Cat3ChatTurnEntry],
    memory: dict[str, Any] | None,
    api_key: str,
    summarizer_call: SummarizerCall,
) -> tuple[dict[str, Any], dict[str, Any], list[Cat3ChatTurnEntry]]:
    """One compaction exactly as the runner does it: evict all but the most recent KEEP_RECENT_TURNS."""
    evict = verbatim[:-KEEP_RECENT_TURNS]
    keep = verbatim[-KEEP_RECENT_TURNS:]
    payload = build_compaction_payload(memory, evict)
    raw = await summarizer_call(
        compaction_payload=payload,
        system_prompt=get_memory_summarizer_system_prompt(),
        schema=SESSION_MEMORY_JSON_SCHEMA,
        api_key=api_key,
        max_tokens=SUMMARIZER_MAX_TOKENS,
        timeout_s=CALL_TIMEOUT_S,
    )
    new_memory = dict(raw.structured)
    new_memory["compacted_through_turn"] = evict[-1].turn_number
    compaction = {
        "evicted_turns": [t.turn_number for t in evict],
        "kept_turns": [t.turn_number for t in keep],
        "payload": payload,
        "raw_text": raw.raw_text,
        "memory_after": dict(new_memory),
        **_usage(raw),
    }
    return compaction, new_memory, list(keep)


async def execute_session_run(
    *,
    preset: dict[str, Any],
    rung_id: str,
    repeat_index: int,
    api_key: str,
    probes: Sequence[dict[str, Any]],
    turn_call: TurnCall = run_cat3_service_desk_turn,
    summarizer_call: SummarizerCall = run_cat3_memory_summarizer,
) -> dict[str, Any]:
    """Execute ONE live session (turns 1-10 + probes) of `rung_id` on `preset`. Never raises."""
    run_nonce = uuid4().hex
    turns: list[dict[str, Any]] = []
    probe_rows: list[dict[str, Any]] = []
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": str(uuid4()),
        "preset_id": preset.get("id"),
        "rung_id": rung_id,
        "repeat_index": repeat_index,
        "run_nonce": run_nonce,
        "started_at": _utc_now_iso(),
        "finished_at": None,
        "status": "ok",
        "error_message": None,
        "intended_model_id": SONNET_MODEL_ID,
        "max_verbatim_turns": MAX_VERBATIM_TURNS,
        "keep_recent_turns": KEEP_RECENT_TURNS,
        "turns": turns,
        "probe_compaction": None,
        "probes": probe_rows,
    }
    try:
        system_text = build_run_system_text(rung_id, preset["employee_profile"], run_nonce)
        use_cache = rung_id in CACHED_RUNGS
        summarize = rung_id == SUMMARIZED_RUNG
        verbatim: list[Cat3ChatTurnEntry] = []
        memory: dict[str, Any] | None = None

        for spec in preset["turns"]:
            t_num = int(spec["turn_number"])
            user_msg = str(spec["user_message"])
            compaction: dict[str, Any] | None = None
            if summarize and len(verbatim) >= MAX_VERBATIM_TURNS:
                compaction, memory, verbatim = await _compact(
                    verbatim=verbatim, memory=memory, api_key=api_key, summarizer_call=summarizer_call
                )
            messages = assemble_cat3_messages(
                verbatim_turns=verbatim, memory_summary=memory, current_user_message=user_msg
            )
            try:
                raw = await turn_call(
                    system_text=system_text,
                    messages=messages,
                    use_prefix_cache=use_cache,
                    api_key=api_key,
                    max_tokens=TURN_MAX_TOKENS,
                    timeout_s=CALL_TIMEOUT_S,
                )
            except Exception:
                if compaction is not None:
                    # Keep the completed compaction even though its turn failed.
                    record["orphan_compaction"] = {"before_turn": t_num, **compaction}
                raise
            turns.append(
                {
                    "turn_number": t_num,
                    "topic_tag": str(spec["topic_tag"]),
                    "user_message": user_msg,
                    "assistant_message": raw.raw_text,
                    **_usage(raw),
                    "messages_count": len(messages),
                    "active_history_turns": len(verbatim),
                    "verbatim_turn_numbers": [t.turn_number for t in verbatim],
                    "compacted_through_turn": int(memory.get("compacted_through_turn") or 0) if memory else 0,
                    "memory_summary_snapshot": dict(memory) if memory else None,
                    "compaction": compaction,
                }
            )
            verbatim.append(Cat3ChatTurnEntry(turn_number=t_num, user_message=user_msg, assistant_message=raw.raw_text))

        # Probe phase: the state a real turn 11 would see, then one independent branch per probe.
        if summarize and len(verbatim) >= MAX_VERBATIM_TURNS:
            record["probe_compaction"], memory, verbatim = await _compact(
                verbatim=verbatim, memory=memory, api_key=api_key, summarizer_call=summarizer_call
            )
        branch_verbatim = list(verbatim)
        branch_memory = dict(memory) if memory else None
        sem = asyncio.Semaphore(PROBE_CONCURRENCY)

        async def one_probe(probe: dict[str, Any]) -> dict[str, Any]:
            messages = assemble_cat3_messages(
                verbatim_turns=branch_verbatim,
                memory_summary=branch_memory,
                current_user_message=str(probe["question"]),
            )
            async with sem:
                raw = await turn_call(
                    system_text=system_text,
                    messages=messages,
                    use_prefix_cache=use_cache,
                    api_key=api_key,
                    max_tokens=PROBE_MAX_TOKENS,
                    timeout_s=CALL_TIMEOUT_S,
                )
            return {
                "probe_id": probe["probe_id"],
                "origin_turn": probe.get("origin_turn"),
                "question": str(probe["question"]),
                "answer": raw.raw_text,
                **_usage(raw),
                "messages_count": len(messages),
                "active_history_turns": len(branch_verbatim),
                "verbatim_turn_numbers": [t.turn_number for t in branch_verbatim],
                "compacted_through_turn": int(branch_memory.get("compacted_through_turn") or 0) if branch_memory else 0,
            }

        results = await asyncio.gather(*(one_probe(p) for p in probes), return_exceptions=True)
        first_exc: BaseException | None = None
        for res in results:
            if isinstance(res, BaseException):
                first_exc = first_exc or res
            else:
                probe_rows.append(res)
        if first_exc is not None:
            raise first_exc
    except Exception as exc:  # noqa: BLE001 — an error is recorded, never raised
        record["status"] = "error"
        record["error_message"] = f"{type(exc).__name__}: {exc}"[:2000]
    record["finished_at"] = _utc_now_iso()
    return record


# --------------------------------------------------------------------------------------------------
# Matrix planning, resume selection, costs, budget guard (pure)
# --------------------------------------------------------------------------------------------------

RunKey = tuple[str, str, int]  # (rung_id, preset_id, repeat_index)


def record_key(record: dict[str, Any]) -> RunKey:
    return (str(record["rung_id"]), str(record["preset_id"]), int(record["repeat_index"]))


def plan_matrix(rung_ids: Sequence[str], preset_ids: Sequence[str], repeats: int) -> list[RunKey]:
    """Interleaved order (repeat, then session, then rung) so a partial run stays balanced."""
    return [(rg, p, r) for r in range(repeats) for p in preset_ids for rg in rung_ids]


def select_pending(planned: Iterable[RunKey], existing_records: Iterable[dict[str, Any]]) -> list[RunKey]:
    """Keys still to run: any key without an `ok` record (error keys are retried; ok runs never are)."""
    done = {record_key(r) for r in existing_records if r.get("status") == "ok"}
    return [k for k in planned if k not in done]


def _finops(call: dict[str, Any]):
    model_id = str(call.get("model_id") or "")
    if model_id not in MODEL_RATES and model_id not in LEGACY_MODEL_RATES:
        model_id = SONNET_MODEL_ID
    return compute_run_finops(
        model_id=model_id,
        input_tokens=int(call.get("input_tokens") or 0),
        output_tokens=int(call.get("output_tokens") or 0),
        cache_creation_tokens=int(call.get("cache_creation_tokens") or 0),
        cache_read_tokens=int(call.get("cache_read_tokens") or 0),
    )


def call_billed_usd(call: dict[str, Any]) -> float:
    """Billed cost of one call from its recorded tokens (output tokens already include thinking)."""
    return _finops(call).total_cost_usd


def call_warm_usd(call: dict[str, Any]) -> float:
    """Warm cost with the same rule as runner.compute_warm_turn_cost (cache writes priced as reads)."""
    return compute_warm_turn_cost(_finops(call))


def prompt_tokens(call: dict[str, Any]) -> int:
    return (
        int(call.get("input_tokens") or 0)
        + int(call.get("cache_creation_tokens") or 0)
        + int(call.get("cache_read_tokens") or 0)
    )


def session_calls(record: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(turn calls, compaction calls) of turns 1-10, including a compaction whose turn then failed."""
    turns = list(record.get("turns") or [])
    comps = [t["compaction"] for t in turns if t.get("compaction")]
    if record.get("orphan_compaction"):
        comps.append(record["orphan_compaction"])
    return turns, comps


def probe_calls(record: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    return list(record.get("probes") or []), record.get("probe_compaction")


def record_costs(record: dict[str, Any]) -> dict[str, float]:
    """Billed and warm cost, split into session (turns 1-10 + their compactions) and probe phase.

    Warm: turn and probe calls use compute_warm_turn_cost; compactions (no cached prefix) count as billed,
    exactly as the runner accumulates `cumulative_warm_cost_usd`.
    """
    turns, comps = session_calls(record)
    probes, pcomp = probe_calls(record)
    comp_cost = sum(call_billed_usd(c) for c in comps)
    pcomp_cost = call_billed_usd(pcomp) if pcomp else 0.0
    session_billed = sum(call_billed_usd(t) for t in turns) + comp_cost
    session_warm = sum(call_warm_usd(t) for t in turns) + comp_cost
    probe_billed = sum(call_billed_usd(p) for p in probes) + pcomp_cost
    probe_warm = sum(call_warm_usd(p) for p in probes) + pcomp_cost
    return {
        "session_billed_usd": round(session_billed, 8),
        "session_warm_usd": round(session_warm, 8),
        "probe_billed_usd": round(probe_billed, 8),
        "probe_warm_usd": round(probe_warm, 8),
        "total_billed_usd": round(session_billed + probe_billed, 8),
    }


def record_billed_cost_usd(record: dict[str, Any]) -> float:
    return record_costs(record)["total_billed_usd"]


class BudgetGuard:
    """Running billed-cost total (session + probe phase); stop launching new runs once it reaches `max_usd`."""

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


def score_record(record: dict[str, Any], keys: dict[str, Any]) -> list[dict[str, Any]]:
    turn_texts = {int(t["turn_number"]): str(t.get("assistant_message") or "") for t in record.get("turns") or []}
    probe_answers = {str(p["probe_id"]): str(p.get("answer") or "") for p in record.get("probes") or []}
    return score_session(
        preset_id=str(record["preset_id"]), turn_texts=turn_texts, probe_answers=probe_answers, keys=keys
    )


def _dist(values: Sequence[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "min": None, "max": None}
    return {"mean": statistics.fmean(values), "min": min(values), "max": max(values)}


def _all_calls(record: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    turns, comps = session_calls(record)
    probes, pcomp = probe_calls(record)
    out: list[tuple[str, dict[str, Any]]] = [(f"turn {t['turn_number']}", t) for t in turns]
    for t in turns:
        if t.get("compaction"):
            out.append((f"compaction before turn {t['turn_number']}", t["compaction"]))
    if record.get("orphan_compaction"):
        out.append((f"compaction before turn {record['orphan_compaction'].get('before_turn')}", record["orphan_compaction"]))
    if pcomp:
        out.append(("probe-phase compaction", pcomp))
    out += [(f"probe {p['probe_id']}", p) for p in probes]
    return out


def cost_metrics(runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Cost, token and context metrics over a list of rerun records (one rung, or rung x session)."""
    costs = [record_costs(r) for r in runs]

    def tok(sel: Callable[[dict[str, Any]], int]) -> dict[str, float | None]:
        return _dist([float(sel(r)) for r in runs])

    def ctx_at(n: int) -> dict[str, float | None]:
        vals = [float(prompt_tokens(t)) for r in runs for t in r.get("turns") or [] if int(t["turn_number"]) == n]
        return _dist(vals)

    return {
        "runs": len(runs),
        "session_billed_usd": _dist([c["session_billed_usd"] for c in costs]),
        "session_warm_usd": _dist([c["session_warm_usd"] for c in costs]),
        "probe_billed_usd": _dist([c["probe_billed_usd"] for c in costs]),
        "probe_warm_usd": _dist([c["probe_warm_usd"] for c in costs]),
        "session_billed_per_1k_sessions_usd": (
            statistics.fmean(c["session_billed_usd"] for c in costs) * 1000 if costs else None
        ),
        "session_warm_per_1k_sessions_usd": (
            statistics.fmean(c["session_warm_usd"] for c in costs) * 1000 if costs else None
        ),
        "tokens_per_session": {
            "turn_prompt": tok(lambda r: sum(prompt_tokens(t) for t in session_calls(r)[0])),
            "turn_output": tok(lambda r: sum(int(t.get("output_tokens") or 0) for t in session_calls(r)[0])),
            "compaction_prompt": tok(lambda r: sum(prompt_tokens(c) for c in session_calls(r)[1])),
            "compaction_output": tok(lambda r: sum(int(c.get("output_tokens") or 0) for c in session_calls(r)[1])),
            "probe_phase_prompt": tok(
                lambda r: sum(prompt_tokens(p) for p in probe_calls(r)[0])
                + (prompt_tokens(probe_calls(r)[1]) if probe_calls(r)[1] else 0)
            ),
            "probe_phase_output": tok(
                lambda r: sum(int(p.get("output_tokens") or 0) for p in probe_calls(r)[0])
                + (int(probe_calls(r)[1].get("output_tokens") or 0) if probe_calls(r)[1] else 0)
            ),
            "thinking": tok(lambda r: sum(int(c.get("thinking_tokens") or 0) for _, c in _all_calls(r))),
        },
        "context_prompt_tokens_at_turn": {str(n): ctx_at(n) for n in CONTEXT_TURNS},
        "session_compactions": _dist([float(len(session_calls(r)[1])) for r in runs]),
        "probe_phase_compactions": _dist([float(1 if r.get("probe_compaction") else 0) for r in runs]),
    }


def non_end_turn_calls(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "run_id": r.get("run_id"),
            "rung_id": r.get("rung_id"),
            "preset_id": r.get("preset_id"),
            "repeat_index": r.get("repeat_index"),
            "call": label,
            "stop_reason": c.get("stop_reason"),
            "output_tokens": c.get("output_tokens"),
        }
        for r in records
        for label, c in _all_calls(r)
        if c.get("stop_reason") != "end_turn"
    ]


def model_mismatches(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "run_id": r.get("run_id"),
            "rung_id": r.get("rung_id"),
            "preset_id": r.get("preset_id"),
            "repeat_index": r.get("repeat_index"),
            "call": label,
            "model_id": c.get("model_id"),
        }
        for r in records
        for label, c in _all_calls(r)
        if c.get("model_id") != SONNET_MODEL_ID
    ]


def summarise(
    records: Sequence[dict[str, Any]],
    *,
    keys: dict[str, Any],
    rung_ids: Sequence[str] = RUNG_IDS,
    preset_ids: Sequence[str] | None = None,
    expected_repeats: int | None = None,
    misses_excerpt_chars: int = 600,
    top_spread: int = 15,
) -> dict[str, Any]:
    """Quality + cost summary for rerun records (latest ok per key)."""
    preset_ids = [p["id"] for p in CAT3_PRESETS] if preset_ids is None else list(preset_ids)
    rung_ids = list(rung_ids)
    records = [r for r in records if r.get("rung_id") in rung_ids]

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
    expected = plan_matrix(rung_ids, preset_ids, expected_repeats)
    missing = [k for k in expected if k not in latest_ok]
    ok_list = [r for _, r in sorted(latest_ok.items())]
    scored = {record_key(r): score_record(r, keys) for r in ok_list}

    def ok_runs(rid: str, pid: str | None = None) -> list[dict[str, Any]]:
        return [r for (a, p, _), r in sorted(latest_ok.items()) if a == rid and (pid is None or p == pid)]

    rerun_rungs: dict[str, Any] = {}
    for rid in rung_ids:
        runs = ok_runs(rid)
        m = {
            "quality": quality_metrics([scored[record_key(r)] for r in runs]),
            "cost": cost_metrics(runs),
            "error_records": sum(1 for e in errors if e.get("rung_id") == rid),
            "by_preset": {},
        }
        for pid in preset_ids:
            pr = ok_runs(rid, pid)
            m["by_preset"][pid] = {
                "quality": quality_metrics([scored[record_key(r)] for r in pr]),
                "cost": cost_metrics(pr),
                "error_records": sum(1 for e in errors if e.get("rung_id") == rid and e.get("preset_id") == pid),
            }
        rerun_rungs[rid] = m

    # Per-fact table
    items = [i for i in all_scored_items(keys) if i["preset_id"] in preset_ids]
    rerun_hits: dict[tuple[str, str], list[bool]] = {}
    for (rid, _pid, _rep), rows in scored.items():
        for row in rows:
            rerun_hits.setdefault((row["fact_id"], rid), []).append(bool(row["hit"]))
    per_fact: list[dict[str, Any]] = []
    for it in items:
        rr = {}
        for rid in rung_ids:
            hs = rerun_hits.get((it["fact_id"], rid), [])
            rr[rid] = {"hits": sum(hs), "n": len(hs), "rate": (sum(hs) / len(hs)) if hs else None}
        any_obs = any(v["n"] for v in rr.values())
        any_hit = any(v["hits"] for v in rr.values())
        rates = [v["rate"] for v in rr.values() if v["rate"] is not None]
        per_fact.append(
            {
                **it,
                "rerun": rr,
                "observed": any_obs,
                "never_hit": bool(any_obs and not any_hit),
                "spread": (max(rates) - min(rates)) if len(rates) >= 2 else None,
            }
        )
    spread_rows = sorted(
        (f for f in per_fact if f["spread"]), key=lambda f: (-f["spread"], f["fact_id"])
    )[:top_spread]

    probe_index = {p["probe_id"]: p for p in keys["probes"]}
    misses: list[dict[str, Any]] = []
    for r in ok_list:
        for p in r.get("probes") or []:
            key = probe_index.get(p["probe_id"])
            if key and not fact_hit(p.get("answer"), key["any_of"]):
                misses.append(
                    {
                        "rung_id": r["rung_id"],
                        "preset_id": r["preset_id"],
                        "repeat_index": r["repeat_index"],
                        "run_id": r.get("run_id"),
                        "probe_id": p["probe_id"],
                        "origin_turn": key["origin_turn"],
                        "expected_any_of": key["any_of"],
                        "answer_excerpt": str(p.get("answer") or "")[:misses_excerpt_chars],
                    }
                )

    cell_counts = {(a, p): len(ok_runs(a, p)) for a in rung_ids for p in preset_ids}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "keys_version": (keys.get("meta") or {}).get("keys_version"),
        "normalisation_rules": list(NORMALISATION_RULES),
        "rung_ids": rung_ids,
        "preset_ids": preset_ids,
        "key_counts": key_counts(keys),
        "rerun": {
            "record_count": len(records),
            "ok_runs_used": len(latest_ok),
            "superseded_ok_records": superseded_ok,
            "error_records": len(errors),
            "expected_repeats": expected_repeats,
            "matrix": {
                "expected_runs": len(expected),
                "complete": not missing,
                "balanced": len(set(cell_counts.values())) <= 1,
                "missing_keys": [list(k) for k in missing],
                "ok_runs_per_cell": {f"{a}|{p}": n for (a, p), n in cell_counts.items()},
            },
            "errors": [
                {
                    "run_id": e.get("run_id"),
                    "rung_id": e.get("rung_id"),
                    "preset_id": e.get("preset_id"),
                    "repeat_index": e.get("repeat_index"),
                    "completed_turns": len(e.get("turns") or []),
                    "completed_probes": len(e.get("probes") or []),
                    "billed_usd": record_billed_cost_usd(e),
                    "error_message": e.get("error_message"),
                }
                for e in errors
            ],
            "error_spend_usd": sum(record_billed_cost_usd(e) for e in errors),
            "non_end_turn_calls": non_end_turn_calls([*ok_list, *errors]),
            "model_mismatches": model_mismatches([*ok_list, *errors]),
            "rungs": rerun_rungs,
        },
        "per_fact": per_fact,
        "never_hit_facts": [f["fact_id"] for f in per_fact if f["never_hit"]],
        "largest_spread_facts": [f["fact_id"] for f in spread_rows],
        "misses_for_review": misses,
    }


# --------------------------------------------------------------------------------------------------
# App portfolio (replays/cat3_quality_summary.json) — derived from summarise(), nothing recomputed
# --------------------------------------------------------------------------------------------------

PORTFOLIO_SCHEMA_VERSION = 1


def _portfolio_cell(quality: dict[str, Any], cost: dict[str, Any]) -> dict[str, Any]:
    return {
        "runs": int(cost["runs"]),
        **compact_quality(quality),
        "session_billed_usd_mean": cost["session_billed_usd"]["mean"],
        "session_warm_usd_mean": cost["session_warm_usd"]["mean"],
        "session_billed_per_1k_usd": cost["session_billed_per_1k_sessions_usd"],
        "session_warm_per_1k_usd": cost["session_warm_per_1k_sessions_usd"],
        "probe_phase_billed_usd_mean": cost["probe_billed_usd"]["mean"],
    }


def build_quality_portfolio(summary: dict[str, Any], *, source_file: str) -> dict[str, Any]:
    """Compact, timestamp-free n=18 picture for the app, from a `summarise()` result."""
    rr = summary["rerun"]
    rungs = []
    for rid in summary["rung_ids"]:
        m = rr["rungs"][rid]
        rungs.append(
            {
                "rung_id": rid,
                **_portfolio_cell(m["quality"], m["cost"]),
                "by_preset": {
                    pid: _portfolio_cell(bp["quality"], bp["cost"]) for pid, bp in m["by_preset"].items()
                },
            }
        )
    probes_per_session = {pid: c.get("probe|session", 0) for pid, c in summary["key_counts"].items()}
    return {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "source": "cat3 quality rerun",
        "source_file": source_file,
        "keys_version": summary["keys_version"],
        "runs": rr["ok_runs_used"],
        "error_records": rr["error_records"],
        "repeats": rr["expected_repeats"],
        "sessions": list(summary["preset_ids"]),
        "probes_per_session": probes_per_session,
        "matrix_complete": rr["matrix"]["complete"],
        "rungs": rungs,
    }
