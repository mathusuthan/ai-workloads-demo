"""Orchestrates the Category 1 four-rung arena and 12-item batch (replay and live).

Four rungs: Sonnet 5.5 and Haiku 5.5, each without the improvement (four-part write-up, free text) and with it
(classification with a strict JSON schema). The golden replays are repeat 0 of the four-cell experiment
(scripts/build_cat1_golden_from_ablation.py); its summary (replays/cat1_ablation_summary.json) is attached to every
response as `ablation_portfolio`.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4
from fastapi import HTTPException, Request

from app.config import get_settings
from app.core.anthropic_service import run_haiku_calibrated, run_haiku_naive, run_sonnet_naive
from app.core.credit_shield import credit_shield
from app.core.measured_claims import fmt_pct, pct_cut, set_note
from app.core.pricing import compute_run_finops
from app.core.trace_store import (
    TracePartition,
    TraceRecord,
    TraceRequestEnvelope,
    TraceResponseEnvelope,
    record_trace,
)
from app.data.cat1_fixtures import CAT1_EXTRA_BATCH_ITEMS, CAT1_PRESETS
from app.models import (
    BatchItemResult,
    Cat1AblationPortfolio,
    Cat1BatchRequest,
    Cat1BatchResponse,
    Cat1RunRequest,
    Cat1RunResponse,
    CfoScaleRow,
    ModelAccuracyRollup,
    PiiRedactionResult,
    RungAccuracyEvaluation,
    RungExecutionResult,
)
from app.archetypes.cat1_triage.accuracy import evaluate_rung_accuracy
from app.archetypes.cat1_triage.pii import scrub_pii_deterministic
from app.archetypes.cat1_triage.prompts import (
    get_haiku_calibrated_system_prompt,
    get_sonnet_naive_system_prompt,
)
from app.archetypes.cat1_triage.schemas import get_schema_for_subtask


CAT1_CATEGORY = "cat1_classification_routing"
RUNG_TO_PATTERN: dict[str, str] = {
    "sonnet_naive": "naive_chatbot",
    "haiku_naive": "naive_unconstrained_prose",
    "sonnet_calibrated": "strict_json_schema",
    "haiku_calibrated": "strict_json_schema",
}
PROSE_RUNGS = ("sonnet_naive", "haiku_naive")
SCHEMA_RUNGS = ("sonnet_calibrated", "haiku_calibrated")
RUNG_ORDER = ("sonnet_naive", "haiku_naive", "sonnet_calibrated", "haiku_calibrated")
SONNET_FALLBACKS = ["claude-sonnet-5-5", "claude-sonnet-4-6"]
HAIKU_FALLBACKS = ["claude-haiku-5-5", "claude-haiku-4-5"]
# Live path: the caps, timeouts and retry setting the ablation ran with (ablation.CAPS / TIMEOUTS_S / MAX_RETRIES).
# The old 2,048-token write-up cap cut off 19 of the 24 stored write-ups; no ablation run reached these caps.
CAT1_PROSE_MAX_TOKENS = 8192
CAT1_SCHEMA_MAX_TOKENS = 512
CAT1_PROSE_TIMEOUT_S = 300.0
CAT1_SCHEMA_TIMEOUT_S = 60.0
CAT1_MAX_RETRIES = 0
THINKING_BY_RUNG: dict[str, dict[str, str]] = {
    "sonnet_naive": {"type": "between_tools"},
    "haiku_naive": {"type": "disabled"},
    "sonnet_calibrated": {"type": "between_tools"},
    "haiku_calibrated": {"type": "disabled"},
}

READER_MODEL_NOTE = (
    "Write-up read by a reader model that was not under test and never saw the right answer (stored with this replay). "
    "The write-up prompt never lists the allowed labels, so this counts the fields where one allowed label could be read "
    "off the write-up and was right — whether the write-up is usable as a classification."
)
STRUCTURED_NOTE = "Fields compared directly with the ground truth."


def build_cat1_request_envelope(
    rung_id: str,
    sub_task: str,
    payload_text: str,
    request_params_override: dict[str, Any] | None = None,
) -> TraceRequestEnvelope:
    """Build the exact request envelope sent to Anthropic."""
    if rung_id in PROSE_RUNGS:
        return TraceRequestEnvelope(
            provider="Anthropic",
            endpoint="messages.create",
            system_instruction=get_sonnet_naive_system_prompt(sub_task),
            parameters=request_params_override
            or {"max_tokens": CAT1_PROSE_MAX_TOKENS, "endpoint": "messages.create", "thinking": THINKING_BY_RUNG[rung_id]},
            input_payload=payload_text,
        )
    return TraceRequestEnvelope(
        provider="Anthropic",
        endpoint="messages.create",
        system_instruction=get_haiku_calibrated_system_prompt(sub_task),
        parameters=request_params_override
        or {
            "max_tokens": CAT1_SCHEMA_MAX_TOKENS,
            "thinking": THINKING_BY_RUNG[rung_id],
            "output_config": {"format": {"type": "json_schema"}},
        },
        json_schema=get_schema_for_subtask(sub_task),
        input_payload=payload_text,
    )


def persist_cat1_trace(
    *,
    source_mode: str,
    run_group_id: str,
    item_id: str,
    item_title: str,
    sub_task: str,
    payload_text: str,
    rung_res: RungExecutionResult,
    pii_result: PiiRedactionResult,
    request_params_override: dict[str, Any] | None = None,
    stop_reason: str | None = None,
    thinking_tokens: int = 0,
    extra_metadata: dict[str, Any] | None = None,
    timestamp_utc: str | None = None,
) -> Path:
    """Write one partitioned TraceRecord for a Category 1 model/pattern execution."""
    pattern = RUNG_TO_PATTERN[rung_res.rung_id]
    envelope = build_cat1_request_envelope(
        rung_res.rung_id,
        sub_task,
        payload_text,
        request_params_override=request_params_override,
    )
    finops_dict = rung_res.finops.model_dump()
    if thinking_tokens:
        finops_dict["thinking_tokens"] = thinking_tokens

    kwargs: dict[str, Any] = {
        "run_group_id": run_group_id,
        "source_mode": source_mode,
        "item_id": item_id,
        "item_title": item_title,
        "partition": TracePartition(
            category=CAT1_CATEGORY,
            use_case=sub_task,
            model=rung_res.model_id,
            pattern=pattern,
        ),
        "request": envelope,
        "response": TraceResponseEnvelope(
            status=rung_res.status,
            error_message=rung_res.error_message,
            stop_reason=stop_reason,
            latency_ms=rung_res.latency_ms,
            raw_text=rung_res.raw_text_preview,
            structured_output=rung_res.structured_output,
            decision_probabilities=rung_res.decision_probabilities,
            pii_redaction=pii_result.model_dump(),
        ),
        "finops": finops_dict,
        "extra_metadata": extra_metadata or {},
    }
    if timestamp_utc:
        kwargs["timestamp_utc"] = timestamp_utc

    return record_trace(TraceRecord(**kwargs))


def _preset_map() -> dict[str, dict[str, Any]]:
    return {p["id"]: p for p in CAT1_PRESETS}


def load_golden_replays() -> dict[str, Any]:
    replays_file = Path(get_settings().replays_dir) / "cat1_golden_replays.json"
    if not replays_file.is_file():
        return {"presets": {}, "batch_items": {}}
    return json.loads(replays_file.read_text(encoding="utf-8"))


def load_cat1_ablation_portfolio() -> Cat1AblationPortfolio | None:
    """Four-cell experiment summary (replays/cat1_ablation_summary.json); None if absent or unreadable."""
    path = Path(get_settings().replays_dir) / "cat1_ablation_summary.json"
    if not path.is_file():
        return None
    try:
        return Cat1AblationPortfolio.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, OSError):
        return None


def _arm(portfolio: Cat1AblationPortfolio | None, arm_id: str) -> Any:
    return next((a for a in (portfolio.arms if portfolio else []) if a.arm_id == arm_id and a.runs > 0), None)


def live_prose_accuracy_note(portfolio: Cat1AblationPortfolio | None = None) -> str:
    """Why a live write-up has no accuracy: reading it needs a reader model, which the app does not call."""
    return "Not scored live: reading a write-up needs a reader model, which the app does not call."


_SONNET_RATE = "$2.00/M in · $10.00/M out"
_HAIKU_RATE = "$0.10/M in · $0.50/M out"


def _rung_metadata(rung_id: str) -> tuple[str, str, list[str]]:
    """Number-free fallback copy; `_apply_measured_claims` replaces the result-dependent sentences."""
    if rung_id == "sonnet_naive":
        return (
            "Without · Sonnet 5.5 four-part write-up (free text)",
            "Without the Improvement · Sonnet",
            [
                f"Single-pass call on Sonnet 5.5 ({_SONNET_RATE}) with today's write-up prompt: analysis, routing, "
                "risks and next steps in free text. The prompt never lists the allowed labels.",
                # replaced with the measured output size by _apply_measured_claims
                "Output tokens at $10/M dominate the cost of a write-up.",
            ],
        )
    if rung_id == "haiku_naive":
        return (
            "Without · Haiku 5.5 four-part write-up (free text)",
            "Without the Improvement · Haiku",
            [
                f"Same single-pass call and prompt on Haiku 5.5 ({_HAIKU_RATE}), thinking disabled. "
                "The prompt never lists the allowed labels.",
                # replaced with the measured output size by _apply_measured_claims
                "The answer is still a long write-up, not the classification fields.",
            ],
        )
    model, rate, thinking = (
        ("Sonnet 5.5", _SONNET_RATE, "thinking between tools") if rung_id == "sonnet_calibrated"
        else ("Haiku 5.5", _HAIKU_RATE, "thinking disabled")
    )
    return (
        f"With · {model} classification with strict JSON schema",
        f"With the Improvement · {model.split()[0]}",
        [
            f"Asks {model} ({rate}, {thinking}) for the classification fields only, through an enforced JSON schema.",
            # replaced with the measured output size and saving by _apply_measured_claims
            "Answering only the fields keeps the output to a short typed record.",
            "Companion <1ms deterministic regex gate masks raw PII without LLM echo.",
        ],
    )


_WITHOUT_FOR = {"sonnet_calibrated": "sonnet_naive", "haiku_calibrated": "haiku_naive"}


def _apply_measured_claims(results: list[RungExecutionResult], portfolio: Cat1AblationPortfolio | None = None) -> None:
    """Rewrite result-dependent rung notes with numbers measured on this run."""
    ok = {r.rung_id: r for r in results if r.status == "ok"}
    for rid in PROSE_RUNGS:
        r = ok.get(rid)
        if r:
            set_note(r, 1, f"Writes {r.finops.output_tokens:,} output tokens on this item; output is "
                           f"{fmt_pct(r.finops.output_cost_share_pct)} of its cost.")
    for rid, without_id in _WITHOUT_FOR.items():
        r, w = ok.get(rid), ok.get(without_id)
        if not r:
            continue
        text = f"The classification-only answer is {r.finops.output_tokens:,} output tokens"
        cut = pct_cut(w.finops.total_cost_usd, r.finops.total_cost_usd) if w else None
        if w and cut is not None:
            text += f" vs {w.finops.output_tokens:,} for the write-up on the same model, cutting cost {fmt_pct(cut)}"
        set_note(r, 1, text + ".")


def _build_rung_result(
    rung_id: str,
    model_id: str,
    provider: str,
    latency_ms: int,
    input_tokens: int,
    output_tokens: int,
    structured_output: dict[str, Any],
    raw_text_preview: str | None = None,
    decision_probabilities: dict[str, Any] | None = None,
    status: str = "ok",
    error_message: str | None = None,
    stop_reason: str | None = None,
    thinking_tokens: int = 0,
    max_tokens: int | None = None,
) -> RungExecutionResult:
    title, badge, notes = _rung_metadata(rung_id)
    finops = compute_run_finops(
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    return RungExecutionResult(
        rung_id=rung_id,  # type: ignore[arg-type]
        rung_title=title,
        badge_text=badge,
        model_id=model_id,
        provider=provider,
        status=status,  # type: ignore[arg-type]
        error_message=error_message,
        latency_ms=latency_ms,
        structured_output=structured_output,
        raw_text_preview=raw_text_preview,
        decision_probabilities=decision_probabilities,
        finops=finops,
        savings_vs_naive_pct=0.0,
        architectural_notes=notes,
        stop_reason=stop_reason,
        thinking_tokens=int(thinking_tokens or 0),
        max_tokens=max_tokens,
        truncated=(stop_reason == "max_tokens") if stop_reason is not None else None,
    )


def rung_result_from_replay(rung_id: str, r_data: dict[str, Any]) -> RungExecutionResult:
    """One stored golden rung -> RungExecutionResult (stop reason, thinking and cap when the replay has them)."""
    return _build_rung_result(
        rung_id=rung_id,
        model_id=r_data["model_id"],
        provider=r_data["provider"],
        latency_ms=int(r_data["latency_ms"]),
        input_tokens=int(r_data["input_tokens"]),
        output_tokens=int(r_data["output_tokens"]),
        structured_output=r_data.get("structured_output") or {},
        raw_text_preview=r_data.get("raw_text_preview"),
        decision_probabilities=r_data.get("decision_probabilities"),
        stop_reason=r_data.get("stop_reason"),
        thinking_tokens=int(r_data.get("thinking_tokens") or 0),
        max_tokens=r_data.get("max_tokens"),
    )


def score_rung(
    res: RungExecutionResult,
    sub_task: str,
    ground_truth: dict[str, Any],
    *,
    reader_extraction: dict[str, Any] | None,
    portfolio: Cat1AblationPortfolio | None,
) -> None:
    """Set `res.accuracy` (or `res.accuracy_note` when a write-up cannot be scored).

    Schema rungs: the structured output. Write-ups: the reader model's stored extraction (replay); a live write-up has
    no reader extraction and is not scored."""
    if res.rung_id in PROSE_RUNGS:
        values = (reader_extraction or {}).get("values")
        if values is None:
            res.accuracy = None
            res.accuracy_note = live_prose_accuracy_note(portfolio)
            return
        ev = evaluate_rung_accuracy(
            rung_id="haiku_calibrated",  # compare the extracted values field by field, exactly like a structured answer
            sub_task=sub_task,
            ground_truth=ground_truth,
            structured_output=dict(values),
            raw_text=None,
        )
        ev.schema_valid = False
        ev.method = "reader_model"
        ev.method_note = READER_MODEL_NOTE
        res.accuracy = ev
        return
    ev = evaluate_rung_accuracy(
        rung_id=res.rung_id,
        sub_task=sub_task,
        ground_truth=ground_truth,
        structured_output=res.structured_output,
        raw_text=res.raw_text_preview,
    )
    ev.method = "structured_output"
    ev.method_note = STRUCTURED_NOTE
    res.accuracy = ev


def _typical_sonnet_writeup_output(portfolio: Cat1AblationPortfolio | None) -> int:
    """Output tokens for the synthetic Sonnet baseline when the Sonnet rung was not run (median of the experiment)."""
    a = _arm(portfolio, "sonnet_report")
    return int(round(a.output_tokens_median)) if a and a.output_tokens_median else 2048


async def _live_rung(
    rung_id: str, payload_text: str, sub_task: str, anthropic_key: str | None
) -> tuple[RungExecutionResult, tuple[dict[str, Any] | None, str | None, int]]:
    """One live rung at the experiment's settings; errors become error results."""
    is_sonnet = rung_id in ("sonnet_naive", "sonnet_calibrated")
    try:
        assert anthropic_key
        if rung_id in PROSE_RUNGS:
            fn = run_sonnet_naive if rung_id == "sonnet_naive" else run_haiku_naive
            raw = await fn(payload_text, sub_task, anthropic_key, max_tokens=CAT1_PROSE_MAX_TOKENS,
                           timeout_s=CAT1_PROSE_TIMEOUT_S, max_retries=CAT1_MAX_RETRIES)
            cap = CAT1_PROSE_MAX_TOKENS
        else:
            settings = get_settings()
            raw = await run_haiku_calibrated(
                payload_text, sub_task, get_schema_for_subtask(sub_task), anthropic_key,
                model=settings.anthropic_sonnet_model if is_sonnet else settings.anthropic_haiku_model,
                fallback_models=SONNET_FALLBACKS if is_sonnet else HAIKU_FALLBACKS,
                max_tokens=CAT1_SCHEMA_MAX_TOKENS, thinking=THINKING_BY_RUNG[rung_id], timeout_s=CAT1_SCHEMA_TIMEOUT_S,
                max_retries=CAT1_MAX_RETRIES, allow_tool_fallback=False)
            cap = CAT1_SCHEMA_MAX_TOKENS
        res = _build_rung_result(rung_id=rung_id, model_id=raw.model_id, provider="Anthropic", latency_ms=raw.latency_ms,
                                 input_tokens=raw.input_tokens, output_tokens=raw.output_tokens, structured_output=raw.structured,
                                 raw_text_preview=raw.raw_text, stop_reason=raw.stop_reason, thinking_tokens=raw.thinking_tokens,
                                 max_tokens=cap)
        return res, (raw.request_params, raw.stop_reason, raw.thinking_tokens)
    except Exception as exc:
        res = _build_rung_result(
            rung_id=rung_id,
            model_id="claude-sonnet-5-5" if is_sonnet else "claude-haiku-5-5",
            provider="Anthropic",
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            structured_output={},
            status="error",
            error_message=str(exc)[:300],
        )
        return res, (None, None, 0)


async def execute_cat1_run(
    req: Cat1RunRequest,
    http_request: Request | None = None,
) -> Cat1RunResponse:
    presets = _preset_map()
    preset = presets.get(req.preset_id or "")

    if req.custom_input is not None and req.custom_input.strip():
        payload_text = req.custom_input.strip()
    elif preset is not None:
        payload_text = preset["payload"]
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either a valid preset_id or non-empty custom_input.",
        )

    sub_task = preset["sub_task"] if (preset and req.custom_input is None) else req.sub_task
    is_exact_preset = preset is not None and payload_text.strip() == preset["payload"].strip()
    ground_truth: dict[str, Any] | None = (
        dict(preset["ground_truth"])
        if (is_exact_preset and preset and "ground_truth" in preset)
        else None
    )
    pii_result = scrub_pii_deterministic(payload_text)
    run_group_id = str(uuid4())
    item_id = preset["id"] if preset else "custom"
    item_title = preset["title"] if preset else "Custom Payload"
    trace_extras: dict[str, tuple[dict[str, Any] | None, str | None, int]] = {}
    reader: dict[str, dict[str, Any] | None] = {}
    portfolio = load_cat1_ablation_portfolio()
    replay_meta: dict[str, dict[str, Any]] = {}

    if req.mode == "replay":
        # Verified Replay only accepts canonical presets (exact text or unmodified preset_id)
        if not is_exact_preset:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Verified Replay mode ($0) only serves the 6 pre-captured NovaMart presets. "
                    "Re-select an unmodified preset or switch to Live API mode for custom payloads."
                ),
            )
        replays = load_golden_replays()
        preset_trace = (replays.get("presets") or {}).get(preset["id"])
        if not preset_trace:
            raise HTTPException(status_code=404, detail=f"Replay trace missing for {preset['id']}.")

        results: list[RungExecutionResult] = []
        for rung_id in req.rungs:
            r_data = preset_trace["rungs"][rung_id]
            res = rung_result_from_replay(rung_id, r_data)
            results.append(res)
            reader[rung_id] = r_data.get("reader_extraction")
            trace_extras[rung_id] = (r_data.get("request_params"), r_data.get("stop_reason"), int(r_data.get("thinking_tokens") or 0))
            replay_meta[rung_id] = (preset_trace.get("provenance") or {}).get(rung_id) or {}
        mode_used = "replay"
    else:
        creds = credit_shield.resolve_live_credentials(
            http_request,
            need_anthropic=True,
        )
        pairs = list(await asyncio.gather(*(_live_rung(r, payload_text, sub_task, creds.anthropic_api_key) for r in req.rungs)))
        results = [p[0] for p in pairs]
        for res, extra in pairs:
            if res.status == "ok":
                trace_extras[res.rung_id] = extra
        if creds.uses_server_budget:
            total_spend = sum(r.finops.total_cost_usd for r in results if r.status == "ok")
            credit_shield.record_server_spend(total_spend)
        mode_used = "live"

    # Compute savings vs Rung 1 (or a synthetic Sonnet write-up estimate if Rung 1 failed/omitted)
    naive_res = next((r for r in results if r.rung_id == "sonnet_naive" and r.status == "ok"), None)
    est_tokens = max(1, round(len(payload_text) / 3.8))
    ref_input_tokens = (
        naive_res.finops.input_tokens
        if naive_res
        else next((r.finops.input_tokens for r in results if r.status == "ok" and r.finops.input_tokens > 0), est_tokens)
    )
    naive_cost = (
        naive_res.finops.total_cost_usd
        if naive_res
        else compute_run_finops("claude-sonnet-5-5", ref_input_tokens, _typical_sonnet_writeup_output(portfolio)).total_cost_usd
    )

    for res in results:
        if res.status == "ok" and naive_cost > 0:
            res.savings_vs_naive_pct = round(((naive_cost - res.finops.total_cost_usd) / naive_cost) * 100, 2)
        if res.status == "ok" and ground_truth is not None:
            score_rung(res, sub_task, ground_truth, reader_extraction=reader.get(res.rung_id), portfolio=portfolio)
    _apply_measured_claims(results, portfolio)

    # Persist partitioned traces (category / use_case / model / pattern) for every rung
    for res in results:
        req_params, stop_reason, think_tok = trace_extras.get(res.rung_id, (None, None, 0))
        extra_meta: dict[str, Any] = {
            "source_endpoint": "/api/cat1/run",
            "savings_vs_naive_pct": res.savings_vs_naive_pct,
        }
        if res.accuracy is not None:
            extra_meta["accuracy"] = res.accuracy.model_dump()
        if res.accuracy_note:
            extra_meta["accuracy_note"] = res.accuracy_note
        if replay_meta.get(res.rung_id):
            extra_meta["ablation_run_id"] = replay_meta[res.rung_id].get("run_id")
        persist_cat1_trace(
            source_mode=mode_used,
            run_group_id=run_group_id,
            item_id=item_id,
            item_title=item_title,
            sub_task=sub_task,
            payload_text=payload_text,
            rung_res=res,
            pii_result=pii_result,
            request_params_override=req_params,
            stop_reason=stop_reason,
            thinking_tokens=think_tok,
            extra_metadata=extra_meta,
        )

    def _batch(rung_id: str, model_id: str) -> Any:
        r = next((x for x in results if x.rung_id == rung_id and x.status == "ok"), None)
        return compute_run_finops(model_id, r.finops.input_tokens, r.finops.output_tokens) if r else None

    boundary_note = (
        "PII boundary: a deterministic <1ms regex gate masks Aadhaar IDs, payment cards, PAN IDs, emails, and phones "
        "inline before any model sees the text."
        if sub_task == "support_triage"
        else "Catalog boundary: the classification fields gate publishing; free-text attribute rewriting is out of scope."
    )

    return Cat1RunResponse(
        mode_used=mode_used,  # type: ignore[arg-type]
        preset_id=preset["id"] if preset else None,
        sub_task=sub_task,  # type: ignore[arg-type]
        input_char_count=len(payload_text),
        estimated_input_tokens=ref_input_tokens,
        results=results,
        haiku_batch_comparator=_batch("haiku_calibrated", "claude-haiku-5-5-batch"),
        sonnet_batch_comparator=_batch("sonnet_calibrated", "claude-sonnet-5-5-batch"),
        pii_redaction=pii_result,
        system1_boundary_note=boundary_note,
        ground_truth=ground_truth,
        ablation_portfolio=portfolio,
    )


async def execute_cat1_batch(
    req: Cat1BatchRequest,
    http_request: Request | None = None,
) -> Cat1BatchResponse:
    all_items = list(CAT1_PRESETS) + list(CAT1_EXTRA_BATCH_ITEMS)
    if req.sub_task != "mixed":
        selected_items = [item for item in all_items if item["sub_task"] == req.sub_task]
    else:
        selected_items = all_items
    portfolio = load_cat1_ablation_portfolio()
    order = RUNG_ORDER

    batch_results: list[BatchItemResult] = []
    batch_run_group_id = str(uuid4())
    # per item: (item, pii, rung results, {rung: (request_params, stop_reason, thinking)})
    batch_trace_payloads: list[tuple[dict[str, Any], PiiRedactionResult, list[RungExecutionResult], dict[str, tuple]]] = []
    tally: dict[str, dict[str, int]] = {rid: {"matched": 0, "fields": 0, "exact": 0, "items": 0} for rid in order}
    spend = 0.0

    def _score(sub: str, gt: dict[str, Any], rungs_map: dict[str, RungExecutionResult], readers: dict[str, Any]) -> dict[str, RungAccuracyEvaluation | None]:
        evals: dict[str, RungAccuracyEvaluation | None] = {}
        for rid, rung_res in rungs_map.items():
            if rung_res.status != "ok":
                evals[rid] = None
                continue
            score_rung(rung_res, sub, gt, reader_extraction=readers.get(rid), portfolio=portfolio)
            ev = rung_res.accuracy
            evals[rid] = ev
            if ev is None:
                continue
            tally[rid]["matched"] += ev.matched_count
            tally[rid]["fields"] += ev.total_fields
            tally[rid]["exact"] += 1 if ev.exact_match else 0
            tally[rid]["items"] += 1
        return evals

    def _item_result(item: dict[str, Any], pii: PiiRedactionResult, rungs_map: dict[str, RungExecutionResult],
                     evals: dict[str, RungAccuracyEvaluation | None]) -> BatchItemResult:
        h, ss = rungs_map["haiku_calibrated"], rungs_map["sonnet_calibrated"]

        def pct(rid: str) -> float | None:
            ev = evals.get(rid)
            return ev.field_accuracy_pct if ev else None

        def exact(rid: str) -> bool | None:
            ev = evals.get(rid)
            return ev.exact_match if ev else None

        return BatchItemResult(
            item_id=item["id"], title=item["title"], sub_task=item["sub_task"],
            input_tokens=h.finops.input_tokens, haiku_output_tokens=h.finops.output_tokens,
            haiku_decision=h.structured_output, sonnet_schema_output_tokens=ss.finops.output_tokens,
            sonnet_schema_decision=ss.structured_output, pii_redactions=pii.total_redactions,
            haiku_latency_ms=h.latency_ms, sonnet_schema_latency_ms=ss.latency_ms,
            ground_truth=dict(item.get("ground_truth") or {}),
            sonnet_accuracy_pct=pct("sonnet_naive"), haiku_naive_accuracy_pct=pct("haiku_naive"),
            sonnet_schema_accuracy_pct=pct("sonnet_calibrated"), haiku_accuracy_pct=pct("haiku_calibrated"),
            sonnet_exact=exact("sonnet_naive"), haiku_naive_exact=exact("haiku_naive"),
            sonnet_schema_exact=exact("sonnet_calibrated"), haiku_exact=exact("haiku_calibrated"),
        )

    if req.mode == "replay":
        replays = load_golden_replays()
        preset_replays = replays.get("presets") or {}
        extra_replays = replays.get("batch_items") or {}
        for item in selected_items:
            iid, sub = item["id"], item["sub_task"]
            gt = dict(item.get("ground_truth") or {})
            pii = scrub_pii_deterministic(item["payload"])
            stored = (preset_replays.get(iid) or extra_replays[iid])["rungs"]
            rungs_map = {rid: rung_result_from_replay(rid, stored[rid]) for rid in order}
            readers = {rid: stored[rid].get("reader_extraction") for rid in order}
            extras = {rid: (stored[rid].get("request_params"), stored[rid].get("stop_reason"), int(stored[rid].get("thinking_tokens") or 0))
                      for rid in order}
            evals = _score(sub, gt, rungs_map, readers)
            batch_trace_payloads.append((item, pii, [rungs_map[r] for r in order], extras))
            batch_results.append(_item_result(item, pii, rungs_map, evals))
        mode_used = "replay"
    else:
        creds = credit_shield.resolve_live_credentials(
            http_request,
            need_anthropic=True,
        )
        assert creds.anthropic_api_key
        key = creds.anthropic_api_key
        sem = asyncio.Semaphore(4)

        async def _eval_item(item: dict[str, Any]) -> tuple[dict[str, Any], PiiRedactionResult, dict[str, RungExecutionResult], dict[str, tuple]]:
            async with sem:
                pairs = await asyncio.gather(*(_live_rung(r, item["payload"], item["sub_task"], key) for r in order))
            return item, scrub_pii_deterministic(item["payload"]), {r: p[0] for r, p in zip(order, pairs)}, {r: p[1] for r, p in zip(order, pairs)}

        for item, pii, rungs_map, extras in await asyncio.gather(*(_eval_item(it) for it in selected_items)):
            evals = _score(item["sub_task"], dict(item.get("ground_truth") or {}), rungs_map, {})
            batch_trace_payloads.append((item, pii, [rungs_map[r] for r in order], extras))
            batch_results.append(_item_result(item, pii, rungs_map, evals))
            spend += sum(r.finops.total_cost_usd for r in rungs_map.values() if r.status == "ok")
        if creds.uses_server_budget:
            credit_shield.record_server_spend(spend)
        mode_used = "live"

    for item, pii, rung_list, extras in batch_trace_payloads:
        for rung_res in rung_list:
            req_params, stop_reason, think_tok = extras.get(rung_res.rung_id, (None, None, 0))
            extra_meta: dict[str, Any] = {"source_endpoint": "/api/cat1/batch"}
            if rung_res.accuracy is not None:
                extra_meta["accuracy"] = rung_res.accuracy.model_dump()
            if rung_res.accuracy_note:
                extra_meta["accuracy_note"] = rung_res.accuracy_note
            persist_cat1_trace(
                source_mode=mode_used,
                run_group_id=batch_run_group_id,
                item_id=item["id"],
                item_title=item["title"],
                sub_task=item["sub_task"],
                payload_text=item["payload"],
                rung_res=rung_res,
                pii_result=pii,
                request_params_override=req_params if rung_res.status == "ok" else None,
                stop_reason=stop_reason if rung_res.status == "ok" else None,
                thinking_tokens=think_tok,
                extra_metadata=extra_meta,
            )

    count = max(1, len(batch_results))

    def _avg(rid: str, field: str) -> int:
        vals = [getattr(rl[[r.rung_id for r in rl].index(rid)].finops, field) for _, _, rl, _ in batch_trace_payloads]
        return round(sum(vals) / count) if vals else 0

    def _acc_stats(rid: str) -> tuple[float | None, float | None]:
        t = tally[rid]
        if t["fields"] == 0:
            return None, None
        return round((t["matched"] / t["fields"]) * 100, 1), round((t["exact"] / t["items"]) * 100, 1)

    acc = {rid: _acc_stats(rid) for rid in order}
    prose_scored = acc["sonnet_naive"][0] is not None
    prose_lbl = "Free text · read by a reader model" if prose_scored else "Free text · not scored live"
    writeup_note = ("Fields read by a reader model from the stored write-up. The write-up prompt never lists the allowed labels: "
                    "this counts fields where one allowed label could be read off the write-up and was right "
                    "(usable as a classification)."
                    if prose_scored else live_prose_accuracy_note(portfolio))
    schema_note = "Classification fields through the enforced schema, compared directly with the ground truth."

    # (rung, label, model, batch model or None, scope note, schema label, rollup note, scoring method)
    tiers_spec = [
        ("sonnet_naive", "Sonnet 5.5 · without: four-part write-up", "claude-sonnet-5-5", None,
         "Four-part write-up in free text; the prompt never lists the allowed labels", prose_lbl, writeup_note, "reader_model"),
        ("haiku_naive", "Haiku 5.5 · without: four-part write-up", "claude-haiku-5-5", None,
         "Same write-up prompt on Haiku 5.5", prose_lbl, writeup_note, "reader_model"),
        ("sonnet_calibrated", "Sonnet 5.5 · with: classification + strict JSON schema", "claude-sonnet-5-5", "claude-sonnet-5-5-batch",
         "Classification fields only, enforced schema", "Enforced JSON schema", schema_note, "structured_output"),
        ("haiku_calibrated", "Haiku 5.5 · with: classification + strict JSON schema", "claude-haiku-5-5", "claude-haiku-5-5-batch",
         "Classification fields only, enforced schema, thinking disabled", "Enforced JSON schema", schema_note, "structured_output"),
    ]

    base = compute_run_finops("claude-sonnet-5-5", _avg("sonnet_naive", "input_tokens"), _avg("sonnet_naive", "output_tokens")).total_cost_usd
    cfo_rows: list[CfoScaleRow] = []
    accuracy_rollup: list[ModelAccuracyRollup] = []
    for rid, label, mid, batch_mid, scope_note, schema_lbl, roll_note, method in tiers_spec:
        tin, tout = _avg(rid, "input_tokens"), _avg(rid, "output_tokens")
        f = compute_run_finops(mid, tin, tout)
        fb = compute_run_finops(batch_mid, tin, tout) if batch_mid else None
        f_acc, e_acc = acc[rid]
        cfo_rows.append(
            CfoScaleRow(
                tier_id=rid,
                label=label,
                model_id=mid,
                avg_input_tokens=tin,
                avg_output_tokens=tout,
                cost_per_1k_usd=f.cost_per_1k_usd,
                monthly_100k_usd=f.monthly_cost_at_100k_usd,
                monthly_1m_usd=round(f.total_cost_usd * 1_000_000, 2),
                annual_12m_usd=f.annual_cost_at_1m_per_mo_usd,
                savings_vs_naive_pct=round(((base - f.total_cost_usd) / base) * 100, 2) if base > 0 else 0.0,
                scope_note=scope_note,
                field_accuracy_pct=f_acc,
                exact_match_pct=e_acc,
                schema_compliance_label=schema_lbl,
                batch_cost_per_1k_usd=fb.cost_per_1k_usd if fb else None,
                batch_monthly_1m_usd=round(fb.total_cost_usd * 1_000_000, 2) if fb else None,
            )
        )
        t = tally[rid]
        accuracy_rollup.append(
            ModelAccuracyRollup(rung_id=rid, label=label, model_id=mid, schema_compliance_pct=100.0 if batch_mid else 0.0,
                                fields_matched=t["matched"], fields_total=t["fields"], field_accuracy_pct=f_acc,
                                exact_items_matched=t["exact"], items_total=t["items"], exact_match_pct=e_acc,
                                cost_per_1k_usd=f.cost_per_1k_usd, notes=roll_note,
                                scoring_method=method if t["fields"] else "not_scored")
        )

    by_tier = {r.tier_id: r for r in cfo_rows}

    def _acc_txt(p: float | None, what: str) -> str:
        return f"{p:.1f}% {what}" if p is not None else "not scored live"

    def _with_txt(rid: str) -> str:
        r = by_tier[rid]
        return (f"${r.monthly_1m_usd:,.2f}/mo ({_acc_txt(r.field_accuracy_pct, 'fields correct')}; "
                f"Batch API price ${r.batch_monthly_1m_usd:,.2f}/mo, computed)")

    return Cat1BatchResponse(
        mode_used=mode_used,  # type: ignore[arg-type]
        total_items=len(batch_results),
        avg_input_tokens=round(sum(it.input_tokens for it in batch_results) / count),
        items=batch_results,
        cfo_comparison=cfo_rows,
        summary_callout=(
            f"At NovaMart scale (1M intake events/month): without the improvement, the four-part write-up costs "
            f"${by_tier['sonnet_naive'].monthly_1m_usd:,.2f}/mo on Sonnet 5.5 and ${by_tier['haiku_naive'].monthly_1m_usd:,.2f}/mo on "
            f"Haiku 5.5 ({_acc_txt(by_tier['sonnet_naive'].field_accuracy_pct, 'of fields usable as a classification')} on Sonnet). "
            f"With classification + strict JSON schema: Sonnet 5.5 {_with_txt('sonnet_calibrated')}; "
            f"Haiku 5.5 {_with_txt('haiku_calibrated')}."
        ),
        accuracy_rollup=accuracy_rollup,
        ablation_portfolio=portfolio,
    )
