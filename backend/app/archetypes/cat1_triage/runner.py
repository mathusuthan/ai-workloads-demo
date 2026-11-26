"""Orchestrates the Category 1 four-rung arena and 12-item batch (replay and live).

The golden replays are repeat 0 of the seven-version ablation (scripts/build_cat1_golden_from_ablation.py); the
ablation summary (replays/cat1_ablation_summary.json) is attached to every response as `ablation_portfolio`.
"""

from __future__ import annotations

import asyncio
import json
import statistics
from pathlib import Path
from typing import Any
from uuid import uuid4
from fastapi import HTTPException, Request

from app.config import get_settings
from app.core.anthropic_service import run_haiku_calibrated, run_haiku_naive, run_sonnet_naive
from app.core.credit_shield import credit_shield
from app.core.gemini_decision_service import run_gemini_decision
from app.core.measured_claims import fmt_pct, pct_cut, set_note
from app.core.pricing import compute_jev_reference, compute_run_finops
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
from app.archetypes.cat1_triage.schemas import (
    get_questions_for_subtask,
    get_schema_for_subtask,
)


CAT1_CATEGORY = "cat1_classification_routing"
RUNG_TO_PATTERN: dict[str, str] = {
    "sonnet_naive": "naive_chatbot",
    "haiku_naive": "naive_unconstrained_prose",
    "haiku_calibrated": "strict_json_schema",
    "gemini_decision": "system1_decisions_api",
}
PROSE_RUNGS = ("sonnet_naive", "haiku_naive")
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
    "haiku_calibrated": {"type": "disabled"},
}

READER_MODEL_NOTE = (
    "Write-up read by a reader model that was not under test and never saw the right answer (stored with this replay). "
    "The write-up prompt never lists the allowed labels, so this counts the fields where one allowed label could be read "
    "off the write-up and was right — whether the write-up is usable as a classification."
)
STRUCTURED_NOTE = "Fields compared directly with the ground truth."
GEMINI_NOTE = "Decisions mapped to the ground-truth fields (priority from the 0–3 severity score), as the app does."


def build_cat1_request_envelope(
    rung_id: str,
    sub_task: str,
    payload_text: str,
    request_params_override: dict[str, Any] | None = None,
) -> TraceRequestEnvelope:
    """Build exact request envelope sent to Anthropic or Gemini Decisions API."""
    if rung_id in PROSE_RUNGS:
        return TraceRequestEnvelope(
            provider="Anthropic",
            endpoint="messages.create",
            system_instruction=get_sonnet_naive_system_prompt(sub_task),
            parameters=request_params_override
            or {"max_tokens": CAT1_PROSE_MAX_TOKENS, "endpoint": "messages.create", "thinking": THINKING_BY_RUNG[rung_id]},
            input_payload=payload_text,
        )
    if rung_id == "haiku_calibrated":
        return TraceRequestEnvelope(
            provider="Anthropic",
            endpoint="messages.create",
            system_instruction=get_haiku_calibrated_system_prompt(sub_task),
            parameters=request_params_override
            or {
                "max_tokens": CAT1_SCHEMA_MAX_TOKENS,
                "thinking": {"type": "disabled"},
                "output_config": {"format": {"type": "json_schema"}},
            },
            json_schema=get_schema_for_subtask(sub_task),
            input_payload=payload_text,
        )
    return TraceRequestEnvelope(
        provider="Google Gemini Decisions API",
        endpoint="v1beta/decisions",
        system_instruction=None,
        parameters=request_params_override or {"api_version": "v1beta"},
        decision_questions=get_questions_for_subtask(sub_task),
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
    """Seven-version ablation summary (replays/cat1_ablation_summary.json); None if absent or unreadable."""
    path = Path(get_settings().replays_dir) / "cat1_ablation_summary.json"
    if not path.is_file():
        return None
    try:
        return Cat1AblationPortfolio.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, OSError):
        return None


def _arm(portfolio: Cat1AblationPortfolio | None, arm_id: str) -> Any:
    return next((a for a in (portfolio.arms if portfolio else []) if a.arm_id == arm_id and a.runs > 0), None)


def _lever(portfolio: Cat1AblationPortfolio | None, lever: str) -> Any:
    return next((lv for lv in (portfolio.levers if portfolio else []) if lv.lever == lever and lv.cost_change_pct is not None), None)


def _signed_pct(x: float) -> str:
    return f"+{fmt_pct(x)}" if x > 0 else f"−{fmt_pct(-x)}"


def live_prose_accuracy_note(portfolio: Cat1AblationPortfolio | None) -> str:
    """Why a live write-up has no accuracy: the app has no reader model, and the keyword matcher is unreliable."""
    base = "Not scored live: reading a write-up needs a reader model, which the app does not call."
    rows = {r.arm_id: r for r in (portfolio.scoring_comparison if portfolio else []) if r.difference_pp is not None}
    cls = [rows[a].difference_pp for a in ("sonnet_classify_text", "haiku_classify_text") if a in rows]
    rep = [rows[a].difference_pp for a in ("sonnet_report", "haiku_report") if a in rows]
    if not cls or not rep:
        return base + " The keyword matcher the app used before was found unreliable in the experiment."
    lo, hi = min(rep), max(rep)
    over = f"by {hi:.0f} points" if round(lo) == round(hi) else f"by {lo:.0f}–{hi:.0f} points"
    return (base + f" In the experiment the keyword matcher the app used before under-scored plain-text classifications by about "
            f"{-statistics.fmean(cls):.0f} points and over-scored write-ups {over}, so it is not shown.")


def _rung_metadata(rung_id: str) -> tuple[str, str, list[str]]:
    """Number-free fallback copy; `_apply_measured_claims` replaces the result-dependent sentences."""
    if rung_id == "sonnet_naive":
        return (
            "Rung 1A · Sonnet 5.5 write-up (free text)",
            "Baseline: Four-Part Write-Up",
            [
                "Single-pass call on Sonnet 5.5 ($2.00/M in · $10.00/M out) with today's write-up prompt: analysis, routing, "
                "risks and next steps in free text. The prompt never lists the allowed labels.",
                # replaced with the measured output size by _apply_measured_claims
                "Output tokens at $10/M dominate the cost of a write-up.",
            ],
        )
    if rung_id == "haiku_naive":
        return (
            "Rung 1B · Haiku 5.5 write-up (free text)",
            "Model Swap Only: Same Write-Up",
            [
                "Same single-pass messages.create call and prompt on Haiku 5.5 ($0.10/M in · $0.50/M out), thinking disabled.",
                # replaced with the measured saving by _apply_measured_claims
                "The model swap cuts cost vs Sonnet 5.5, but the answer is still a long write-up, not the classification fields.",
            ],
        )
    if rung_id == "haiku_calibrated":
        return (
            "Rung 2 · Haiku 5.5 classification + JSON schema",
            "Ask for the Classification: Haiku + Schema",
            [
                "Asks Claude Haiku 5.5 ($0.10/M in · $0.50/M out, thinking disabled) for the classification fields only, "
                "through an enforced JSON schema.",
                # replaced with the measured output size and saving by _apply_measured_claims
                "Answering only the fields keeps the output to a short typed record.",
                # replaced with the experiment's attribution by _apply_measured_claims
                "Most of the saving comes from asking for the classification instead of a write-up; the schema guarantees the format.",
                "Companion <1ms deterministic regex gate masks raw PII without LLM echo.",
            ],
        )
    return (
        "Rung 3 · Gemini Decision 1 (System-1 API)",
        "Beyond Generative: 0 Output Tokens",
        [
            "Non-autoregressive forward pass ($0.10/M in · $0.00 out; rate not verified) across all questions at once.",
            "Shared input billed once; returns calibrated probabilities & confidence. Its questions differ from the JSON "
            "schema: priority comes from a 0–3 severity score.",
            "Boundary: cannot rewrite text for inline PII masking — pairs with <1ms regex gate.",
        ],
    )


def _apply_measured_claims(results: list[RungExecutionResult], portfolio: Cat1AblationPortfolio | None = None) -> None:
    """Rewrite result-dependent rung notes with numbers measured on this run and in the ablation."""
    ok = {r.rung_id: r for r in results if r.status == "ok"}
    sonnet, h_prose, h_schema = ok.get("sonnet_naive"), ok.get("haiku_naive"), ok.get("haiku_calibrated")
    if sonnet:
        set_note(
            sonnet,
            1,
            f"Writes {sonnet.finops.output_tokens:,} output tokens on this item; output is "
            f"{fmt_pct(sonnet.finops.output_cost_share_pct)} of its cost.",
        )
    if h_prose and sonnet:
        set_note(
            h_prose,
            1,
            f"Model swap alone cuts {fmt_pct(h_prose.savings_vs_naive_pct)} vs the Sonnet 5.5 write-up on this item, yet "
            f"the write-up still emits {h_prose.finops.output_tokens:,} output tokens.",
        )
    if h_schema:
        text = f"The classification-only answer is {h_schema.finops.output_tokens:,} output tokens"
        cut = pct_cut(h_prose.finops.total_cost_usd, h_schema.finops.total_cost_usd) if h_prose else None
        if h_prose and cut is not None:
            text += (
                f" vs {h_prose.finops.output_tokens:,} for the Haiku write-up, cutting cost {fmt_pct(cut)} on the same model"
            )
        if sonnet:
            text += f" ({fmt_pct(h_schema.savings_vs_naive_pct)} vs the Sonnet write-up)"
        set_note(h_schema, 1, text + ".")
        ask_h = _lever(portfolio, "write-up → classification-only text (haiku)")
        ask_s = _lever(portfolio, "write-up → classification-only text (sonnet)")
        sch = _lever(portfolio, "text → schema (haiku)")
        swap = _lever(portfolio, "Sonnet → Haiku (schema)")
        readable = portfolio.classification_text_readable if portfolio else {}
        if ask_h and ask_s and sch and swap:
            acc = "no change in accuracy" if abs(sch.accuracy_change_pp or 0) < 0.05 else f"{sch.accuracy_change_pp:+.1f} points of accuracy"
            fmt_note = (f" What it buys is a guaranteed format; all {readable['every_field_stated']} plain-text classification answers "
                        "were readable in the experiment."
                        if readable.get("answers") and readable.get("every_field_stated") == readable.get("answers")
                        else " What it buys is a guaranteed format.")
            set_note(
                h_schema,
                2,
                f"Across {portfolio.ok_runs} experiment runs the saving comes from asking for the classification instead of a "
                f"write-up ({_signed_pct(ask_h.cost_change_pct)} on Haiku, {_signed_pct(ask_s.cost_change_pct)} on Sonnet) and from "
                f"the smaller model ({_signed_pct(swap.cost_change_pct)}). The JSON schema itself cost {_signed_pct(sch.cost_change_pct)} "
                f"over the same classification asked as plain text, with {acc}." + fmt_note,
            )


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

    Schema and Gemini rungs: the structured output, as before. Write-ups: the reader model's stored extraction (replay);
    a live write-up has no reader extraction and is not scored (the keyword matcher was found unreliable)."""
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
    ev.method_note = GEMINI_NOTE if res.rung_id == "gemini_decision" else STRUCTURED_NOTE
    res.accuracy = ev


def _typical_sonnet_writeup_output(portfolio: Cat1AblationPortfolio | None) -> int:
    """Output tokens for the synthetic Sonnet baseline when the Sonnet rung was not run (median of the experiment)."""
    a = _arm(portfolio, "sonnet_report")
    return int(round(a.output_tokens_median)) if a and a.output_tokens_median else 2048


async def _live_rung(
    rung_id: str, payload_text: str, sub_task: str, api_keys: tuple[str | None, str | None]
) -> tuple[RungExecutionResult, tuple[dict[str, Any] | None, str | None, int]]:
    """One live rung at the ablation's settings; errors become error results."""
    anthropic_key, gemini_key = api_keys
    try:
        if rung_id in PROSE_RUNGS:
            assert anthropic_key
            fn = run_sonnet_naive if rung_id == "sonnet_naive" else run_haiku_naive
            raw = await fn(payload_text, sub_task, anthropic_key, max_tokens=CAT1_PROSE_MAX_TOKENS,
                           timeout_s=CAT1_PROSE_TIMEOUT_S, max_retries=CAT1_MAX_RETRIES)
            res = _build_rung_result(rung_id=rung_id, model_id=raw.model_id, provider="Anthropic", latency_ms=raw.latency_ms,
                                     input_tokens=raw.input_tokens, output_tokens=raw.output_tokens, structured_output=raw.structured,
                                     raw_text_preview=raw.raw_text, stop_reason=raw.stop_reason, thinking_tokens=raw.thinking_tokens,
                                     max_tokens=CAT1_PROSE_MAX_TOKENS)
            return res, (raw.request_params, raw.stop_reason, raw.thinking_tokens)
        if rung_id == "haiku_calibrated":
            assert anthropic_key
            raw = await run_haiku_calibrated(payload_text, sub_task, get_schema_for_subtask(sub_task), anthropic_key,
                                             max_tokens=CAT1_SCHEMA_MAX_TOKENS, timeout_s=CAT1_SCHEMA_TIMEOUT_S,
                                             max_retries=CAT1_MAX_RETRIES, allow_tool_fallback=False)
            res = _build_rung_result(rung_id=rung_id, model_id=raw.model_id, provider="Anthropic", latency_ms=raw.latency_ms,
                                     input_tokens=raw.input_tokens, output_tokens=raw.output_tokens, structured_output=raw.structured,
                                     raw_text_preview=raw.raw_text, stop_reason=raw.stop_reason, thinking_tokens=raw.thinking_tokens,
                                     max_tokens=CAT1_SCHEMA_MAX_TOKENS)
            return res, (raw.request_params, raw.stop_reason, raw.thinking_tokens)
        assert gemini_key
        dec = await run_gemini_decision(payload_text, get_questions_for_subtask(sub_task), gemini_key)
        res = _build_rung_result(rung_id="gemini_decision", model_id=dec.model_id, provider="Google Gemini Decisions API",
                                 latency_ms=dec.latency_ms, input_tokens=dec.input_tokens, output_tokens=dec.output_tokens,
                                 structured_output=dec.structured_summary, decision_probabilities=dec.decision_probabilities)
        # The decisions API has no stop reason; none is invented.
        return res, ({"api_version": "v1beta"}, None, 0)
    except Exception as exc:
        fallback_model = (
            "claude-sonnet-5-5"
            if rung_id == "sonnet_naive"
            else ("claude-haiku-5-5" if rung_id in ("haiku_naive", "haiku_calibrated") else "gemini-decision-1")
        )
        res = _build_rung_result(
            rung_id=rung_id,
            model_id=fallback_model,
            provider="Anthropic" if rung_id != "gemini_decision" else "Google Gemini Decisions API",
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
        need_anthropic = any(r in ("sonnet_naive", "haiku_naive", "haiku_calibrated") for r in req.rungs)
        need_gemini = "gemini_decision" in req.rungs
        creds = credit_shield.resolve_live_credentials(
            http_request,
            need_anthropic=need_anthropic,
            need_gemini=need_gemini,
        )
        keys = (creds.anthropic_api_key, creds.gemini_api_key)
        pairs = list(await asyncio.gather(*(_live_rung(r, payload_text, sub_task, keys) for r in req.rungs)))
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

    haiku_res = next((r for r in results if r.rung_id == "haiku_calibrated" and r.status == "ok"), None)
    haiku_batch = (
        compute_run_finops(
            "claude-haiku-5-5-batch",
            haiku_res.finops.input_tokens,
            haiku_res.finops.output_tokens,
        )
        if haiku_res
        else None
    )

    gemini_res = next((r for r in results if r.rung_id == "gemini_decision" and r.status == "ok"), None)
    jev_input = gemini_res.finops.input_tokens if gemini_res else ref_input_tokens
    jev_comp = compute_jev_reference(jev_input, naive_cost)

    boundary_note = (
        "System-1 Boundary: Gemini Decision 1 & Jev classify queue, severity, and PII presence "
        "(0 output tokens, $0.04–$0.10/M in; rates not verified), but cannot rewrite text. Companion <1ms regex scrubbing "
        "masks Aadhaar IDs, payment cards, PAN IDs, emails, and phones inline — or escalate only flagged tickets to Haiku."
        if sub_task == "support_triage"
        else "System-1 Boundary: Gemini Decision 1 & Jev handle leaf taxonomy, contradiction gating, and "
        "hazmat risk scoring with 0 output tokens. Escalate to Haiku only when free-text attribute extraction is needed."
    )

    return Cat1RunResponse(
        mode_used=mode_used,  # type: ignore[arg-type]
        preset_id=preset["id"] if preset else None,
        sub_task=sub_task,  # type: ignore[arg-type]
        input_char_count=len(payload_text),
        estimated_input_tokens=ref_input_tokens,
        results=results,
        haiku_batch_comparator=haiku_batch,
        jev_comparator=jev_comp,
        pii_redaction=pii_result,
        system1_boundary_note=boundary_note,
        ground_truth=ground_truth,
        ablation_portfolio=portfolio,
    )


def _legacy_batch_rungs(b: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Flat batch-item replay (the first capture's layout) -> per-rung records."""
    s_raw = b.get("sonnet_raw_text") or ""
    hn_raw = b.get("haiku_naive_raw_text") or ""
    in_tok = int(b["input_tokens"])
    s_in = int(b.get("sonnet_input_tokens", in_tok))
    return {
        "sonnet_naive": {"model_id": "claude-sonnet-5-5", "provider": "Anthropic", "latency_ms": int(b.get("sonnet_latency_ms", 0)),
                         "input_tokens": s_in, "output_tokens": int(b.get("sonnet_output_tokens", 0)),
                         "structured_output": {"mode": "unstructured_chat_prose", "char_length": len(s_raw)}, "raw_text_preview": s_raw},
        "haiku_naive": {"model_id": "claude-haiku-5-5", "provider": "Anthropic", "latency_ms": int(b.get("haiku_naive_latency_ms", 0)),
                        "input_tokens": int(b.get("haiku_naive_input_tokens", s_in)), "output_tokens": int(b.get("haiku_naive_output_tokens", 0)),
                        "structured_output": {"mode": "unstructured_chat_prose", "char_length": len(hn_raw)}, "raw_text_preview": hn_raw},
        "haiku_calibrated": {"model_id": "claude-haiku-5-5", "provider": "Anthropic", "latency_ms": int(b["haiku_latency_ms"]),
                             "input_tokens": in_tok, "output_tokens": int(b["haiku_output_tokens"]),
                             "structured_output": b["haiku_decision"], "raw_text_preview": json.dumps(b["haiku_decision"])},
        "gemini_decision": {"model_id": "gemini-decision-1", "provider": "Google Gemini Decisions API", "latency_ms": int(b["gemini_latency_ms"]),
                            "input_tokens": int(b.get("gemini_input_tokens", s_in)), "output_tokens": 0,
                            "structured_output": b["gemini_decision"], "decision_probabilities": None,
                            "gemini_confidence": b.get("gemini_confidence")},
    }


def _gemini_confidence(g_rung: RungExecutionResult, fallback: float | None = None) -> float:
    probs = g_rung.decision_probabilities or {}
    confs = [float(v.get("confidence", 0.0)) for v in probs.values() if isinstance(v, dict)]
    if confs:
        return round(sum(confs) / len(confs), 3)
    return float(fallback or 0.0)


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
    order = ("sonnet_naive", "haiku_naive", "haiku_calibrated", "gemini_decision")

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
                     evals: dict[str, RungAccuracyEvaluation | None], g_conf: float) -> BatchItemResult:
        h, g = rungs_map["haiku_calibrated"], rungs_map["gemini_decision"]

        def pct(rid: str) -> float | None:
            ev = evals.get(rid)
            return ev.field_accuracy_pct if ev else None

        def exact(rid: str) -> bool | None:
            ev = evals.get(rid)
            return ev.exact_match if ev else None

        return BatchItemResult(
            item_id=item["id"], title=item["title"], sub_task=item["sub_task"],
            input_tokens=h.finops.input_tokens, haiku_output_tokens=h.finops.output_tokens,
            haiku_decision=h.structured_output, gemini_decision=g.structured_output, gemini_confidence=g_conf,
            pii_redactions=pii.total_redactions, haiku_latency_ms=h.latency_ms, gemini_latency_ms=g.latency_ms,
            ground_truth=dict(item.get("ground_truth") or {}),
            sonnet_accuracy_pct=pct("sonnet_naive"), haiku_naive_accuracy_pct=pct("haiku_naive"),
            haiku_accuracy_pct=pct("haiku_calibrated") or 0.0, gemini_accuracy_pct=pct("gemini_decision") or 0.0,
            sonnet_exact=exact("sonnet_naive"), haiku_naive_exact=exact("haiku_naive"),
            haiku_exact=bool(exact("haiku_calibrated")), gemini_exact=bool(exact("gemini_decision")),
        )

    if req.mode == "replay":
        replays = load_golden_replays()
        preset_replays = replays.get("presets") or {}
        extra_replays = replays.get("batch_items") or {}
        for item in selected_items:
            iid, sub = item["id"], item["sub_task"]
            gt = dict(item.get("ground_truth") or {})
            pii = scrub_pii_deterministic(item["payload"])
            src = preset_replays.get(iid) or extra_replays[iid]
            stored = src.get("rungs") or _legacy_batch_rungs(src)
            rungs_map = {rid: rung_result_from_replay(rid, stored[rid]) for rid in order}
            readers = {rid: stored[rid].get("reader_extraction") for rid in order}
            extras = {rid: (stored[rid].get("request_params"), stored[rid].get("stop_reason"), int(stored[rid].get("thinking_tokens") or 0))
                      for rid in order}
            evals = _score(sub, gt, rungs_map, readers)
            g_conf = _gemini_confidence(rungs_map["gemini_decision"], stored["gemini_decision"].get("gemini_confidence") or src.get("gemini_confidence"))
            batch_trace_payloads.append((item, pii, [rungs_map[r] for r in order], extras))
            batch_results.append(_item_result(item, pii, rungs_map, evals, g_conf))
        mode_used = "replay"
    else:
        creds = credit_shield.resolve_live_credentials(
            http_request,
            need_anthropic=True,
            need_gemini=True,
        )
        assert creds.anthropic_api_key and creds.gemini_api_key
        keys = (creds.anthropic_api_key, creds.gemini_api_key)
        sem = asyncio.Semaphore(4)

        async def _eval_item(item: dict[str, Any]) -> tuple[dict[str, Any], PiiRedactionResult, dict[str, RungExecutionResult], dict[str, tuple]]:
            async with sem:
                pairs = await asyncio.gather(*(_live_rung(r, item["payload"], item["sub_task"], keys) for r in order))
            return item, scrub_pii_deterministic(item["payload"]), {r: p[0] for r, p in zip(order, pairs)}, {r: p[1] for r, p in zip(order, pairs)}

        for item, pii, rungs_map, extras in await asyncio.gather(*(_eval_item(it) for it in selected_items)):
            evals = _score(item["sub_task"], dict(item.get("ground_truth") or {}), rungs_map, {})
            batch_trace_payloads.append((item, pii, [rungs_map[r] for r in order], extras))
            batch_results.append(_item_result(item, pii, rungs_map, evals, _gemini_confidence(rungs_map["gemini_decision"])))
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

    avg_in = round(sum(it.input_tokens for it in batch_results) / count)
    avg_h_out = round(sum(it.haiku_output_tokens for it in batch_results) / count)
    avg_s_in, avg_s_out = _avg("sonnet_naive", "input_tokens"), _avg("sonnet_naive", "output_tokens")
    avg_hn_in, avg_hn_out = _avg("haiku_naive", "input_tokens"), _avg("haiku_naive", "output_tokens")
    avg_g_in = _avg("gemini_decision", "input_tokens")

    def _acc_stats(rid: str) -> tuple[float | None, float | None]:
        t = tally[rid]
        if t["fields"] == 0:
            return None, None
        return round((t["matched"] / t["fields"]) * 100, 1), round((t["exact"] / t["items"]) * 100, 1)

    s_f_pct, s_e_pct = _acc_stats("sonnet_naive")
    hn_f_pct, hn_e_pct = _acc_stats("haiku_naive")
    h_f_pct, h_e_pct = _acc_stats("haiku_calibrated")
    g_f_pct, g_e_pct = _acc_stats("gemini_decision")
    prose_lbl = "Free text · read by a reader model" if s_f_pct is not None else "Free text · not scored live"

    tiers_spec = [
        ("sonnet_naive", "1A. Sonnet 5.5 write-up (free text)", "claude-sonnet-5-5", avg_s_in, avg_s_out, "Four-part write-up; the prompt never lists the allowed labels", s_f_pct, s_e_pct, prose_lbl),
        ("haiku_naive", "1B. Haiku 5.5 write-up (free text)", "claude-haiku-5-5", avg_hn_in, avg_hn_out, "Model swap only: the same write-up prompt on the small model", hn_f_pct, hn_e_pct, prose_lbl),
        ("haiku_realtime", "2. Haiku 5.5 classification + JSON schema", "claude-haiku-5-5", avg_in, avg_h_out, "Classification fields only, enforced schema, thinking disabled", h_f_pct, h_e_pct, "Enforced JSON schema"),
        ("haiku_batch", "3. Haiku 5.5 via Batch API (computed)", "claude-haiku-5-5-batch", avg_in, avg_h_out, "Same calls priced at the 50% Batch API rate — computed, not run", h_f_pct, h_e_pct, "Enforced JSON schema (price computed)"),
        ("gemini_decision", "4. Gemini Decision 1 (System-1)", "gemini-decision-1", avg_g_in, 0, "0 output tokens + regex PII gate · $0.10/M input (rate not verified)", g_f_pct, g_e_pct, "Closed-set decisions API"),
        ("typesafe_jev", "5. TypeSafe Jev (Rate Card Ref)", "typesafe-jev", avg_s_in, 0, "FinOps benchmark · $0.042/M input · $0 output", None, None, "Rate-card ref (unexecuted)"),
    ]

    naive_finops = compute_run_finops("claude-sonnet-5-5", avg_s_in, avg_s_out)
    cfo_rows: list[CfoScaleRow] = []
    for tid, label, mid, tin, tout, scope_note, f_acc, e_acc, schema_lbl in tiers_spec:
        f = compute_run_finops(mid, tin, tout)
        base = naive_finops.total_cost_usd
        savings = round(((base - f.total_cost_usd) / base) * 100, 2) if base > 0 else 0.0
        cfo_rows.append(
            CfoScaleRow(
                tier_id=tid,
                label=label,
                model_id=mid,
                avg_input_tokens=tin,
                avg_output_tokens=tout,
                cost_per_1k_usd=f.cost_per_1k_usd,
                monthly_100k_usd=f.monthly_cost_at_100k_usd,
                monthly_1m_usd=round(f.total_cost_usd * 1_000_000, 2),
                annual_12m_usd=f.annual_cost_at_1m_per_mo_usd,
                savings_vs_naive_pct=savings,
                scope_note=scope_note,
                field_accuracy_pct=f_acc,
                exact_match_pct=e_acc,
                schema_compliance_label=schema_lbl,
            )
        )

    hn_x = (cfo_rows[0].cost_per_1k_usd / cfo_rows[1].cost_per_1k_usd) if cfo_rows[1].cost_per_1k_usd else None
    writeup_note = ("Fields read by a reader model from the stored write-up. The write-up prompt never lists the allowed labels: "
                    "this counts fields where one allowed label could be read off the write-up and was right."
                    if s_f_pct is not None else live_prose_accuracy_note(portfolio))

    def _rollup(rid: str, label: str, model_id: str, schema_pct: float, f_pct: float | None, e_pct: float | None, cost: float,
                notes: str, method: str) -> ModelAccuracyRollup:
        t = tally[rid]
        return ModelAccuracyRollup(rung_id=rid, label=label, model_id=model_id, schema_compliance_pct=schema_pct,
                                   fields_matched=t["matched"], fields_total=t["fields"], field_accuracy_pct=f_pct,
                                   exact_items_matched=t["exact"], items_total=t["items"], exact_match_pct=e_pct,
                                   cost_per_1k_usd=cost, notes=notes, scoring_method=method if t["fields"] else "not_scored")

    accuracy_rollup = [
        _rollup("sonnet_naive", "1A. Sonnet 5.5 write-up", "claude-sonnet-5-5", 0.0, s_f_pct, s_e_pct, cfo_rows[0].cost_per_1k_usd,
                writeup_note, "reader_model"),
        _rollup("haiku_naive", "1B. Haiku 5.5 write-up", "claude-haiku-5-5", 0.0, hn_f_pct, hn_e_pct, cfo_rows[1].cost_per_1k_usd,
                (f"{hn_x:.0f}× cheaper than the Sonnet write-up on these items; same write-up prompt. " if hn_x else "") + writeup_note,
                "reader_model"),
        _rollup("haiku_calibrated", "2. Haiku 5.5 classification + JSON schema", "claude-haiku-5-5", 100.0, h_f_pct, h_e_pct,
                cfo_rows[2].cost_per_1k_usd,
                "Classification fields through the enforced schema, compared directly. The Batch API price (50%) is computed, not run.",
                "structured_output"),
        _rollup("gemini_decision", "4. Gemini Decision 1", "gemini-decision-1", 100.0, g_f_pct, g_e_pct, cfo_rows[4].cost_per_1k_usd,
                "Closed-set decisions with probabilities and 0 output tokens; priority mapped from a 0–3 severity score.",
                "structured_output"),
    ]

    by_tier = {r.tier_id: r for r in cfo_rows}

    def _acc_txt(p: float | None, what: str) -> str:
        return f"{p:.1f}% {what}" if p is not None else "not scored live"

    return Cat1BatchResponse(
        mode_used=mode_used,  # type: ignore[arg-type]
        total_items=len(batch_results),
        avg_input_tokens=avg_in,
        items=batch_results,
        cfo_comparison=cfo_rows,
        summary_callout=(
            f"At NovaMart scale (1M intake events/month, {avg_s_in} write-up / {avg_in} schema prompt tokens per item): "
            f"the Sonnet 5.5 write-up costs ${by_tier['sonnet_naive'].monthly_1m_usd:,.2f}/mo "
            f"({_acc_txt(s_f_pct, 'of fields usable as a classification')}); "
            f"Haiku 5.5 classification + JSON schema ${by_tier['haiku_realtime'].monthly_1m_usd:,.2f}/mo "
            f"({_acc_txt(h_f_pct, 'fields correct')}; Batch API price ${by_tier['haiku_batch'].monthly_1m_usd:,.2f}/mo, computed); "
            f"Gemini Decision 1 ${by_tier['gemini_decision'].monthly_1m_usd:,.2f}/mo ({_acc_txt(g_f_pct, 'fields correct')})."
        ),
        accuracy_rollup=accuracy_rollup,
        ablation_portfolio=portfolio,
    )
