"""Orchestrates Category 1 3-Rung Arena and 12-Item Batch Simulator (Replay & Live)."""

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
from app.core.gemini_decision_service import run_gemini_decision
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


def build_cat1_request_envelope(
    rung_id: str,
    sub_task: str,
    payload_text: str,
    request_params_override: dict[str, Any] | None = None,
) -> TraceRequestEnvelope:
    """Build exact request envelope sent to Anthropic or Gemini Decisions API."""
    if rung_id in ("sonnet_naive", "haiku_naive"):
        thinking_default = (
            {"type": "between_tools"} if rung_id == "sonnet_naive" else {"type": "disabled"}
        )
        return TraceRequestEnvelope(
            provider="Anthropic",
            endpoint="messages.create",
            system_instruction=get_sonnet_naive_system_prompt(sub_task),
            parameters=request_params_override
            or {"max_tokens": 2048, "endpoint": "messages.create", "thinking": thinking_default},
            input_payload=payload_text,
        )
    if rung_id == "haiku_calibrated":
        return TraceRequestEnvelope(
            provider="Anthropic",
            endpoint="messages.create",
            system_instruction=get_haiku_calibrated_system_prompt(sub_task),
            parameters=request_params_override
            or {
                "max_tokens": 256,
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


def _rung_metadata(rung_id: str) -> tuple[str, str, list[str]]:
    if rung_id == "sonnet_naive":
        return (
            "Rung 1A · Sonnet 5.5 (Unconstrained Prose)",
            "Anti-Pattern: Frontier Prose API",
            [
                "Single-pass stateless API on Sonnet 5.5 ($2.00/M in · $10.00/M out) with chat-style prose prompt.",
                "Unbounded output echoes ticket context at 5x output token pricing.",
            ],
        )
    if rung_id == "haiku_naive":
        return (
            "Rung 1B · Haiku 5.5 (Unconstrained Prose)",
            "Ablation: Model Swap Only (No Schema)",
            [
                "Same stateless single-pass messages.create API on Haiku 5.5 ($0.10/M in · $0.50/M out) — NOT multi-turn chat.",
                "Model swap cuts 95% vs Sonnet 5.5, yet unconstrained prose + default thinking still bloat output tokens.",
            ],
        )
    if rung_id == "haiku_calibrated":
        return (
            "Rung 2 · Haiku 5.5 + Strict JSON Schema",
            "Slide 3 Lever: Haiku 5.5 + Strict JSON",
            [
                "Routes stateless triage to Claude Haiku 5.5 ($0.10/M in · $0.50/M out) with thinking disabled.",
                "Strict JSON schema compresses output to ~90–125 tokens (cuts ~50% vs Haiku prose!).",
                "Companion <1ms deterministic regex gate masks raw PII without LLM echo.",
            ],
        )
    return (
        "Rung 3 · Gemini Decision 1 (System-1 API)",
        "Beyond Generative: 0 Output Tokens",
        [
            "Non-autoregressive forward pass ($0.10/M in · $0.00 out) across all questions at once.",
            "Shared input billed once; returns calibrated probabilities & confidence.",
            "Boundary: cannot rewrite text for inline PII masking — pairs with <1ms regex gate.",
        ],
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
    )


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
            results.append(
                _build_rung_result(
                    rung_id=rung_id,
                    model_id=r_data["model_id"],
                    provider=r_data["provider"],
                    latency_ms=int(r_data["latency_ms"]),
                    input_tokens=int(r_data["input_tokens"]),
                    output_tokens=int(r_data["output_tokens"]),
                    structured_output=r_data.get("structured_output") or {},
                    raw_text_preview=r_data.get("raw_text_preview"),
                    decision_probabilities=r_data.get("decision_probabilities"),
                )
            )
        mode_used = "replay"
    else:
        need_anthropic = any(r in ("sonnet_naive", "haiku_naive", "haiku_calibrated") for r in req.rungs)
        need_gemini = "gemini_decision" in req.rungs
        creds = credit_shield.resolve_live_credentials(
            http_request,
            need_anthropic=need_anthropic,
            need_gemini=need_gemini,
        )

        schema = get_schema_for_subtask(sub_task)
        questions = get_questions_for_subtask(sub_task)

        async def _run_one(rung_id: str) -> RungExecutionResult:
            try:
                if rung_id == "sonnet_naive":
                    assert creds.anthropic_api_key
                    raw = await run_sonnet_naive(payload_text, sub_task, creds.anthropic_api_key)
                    trace_extras[rung_id] = (raw.request_params, raw.stop_reason, raw.thinking_tokens)
                    return _build_rung_result(
                        rung_id="sonnet_naive",
                        model_id=raw.model_id,
                        provider="Anthropic",
                        latency_ms=raw.latency_ms,
                        input_tokens=raw.input_tokens,
                        output_tokens=raw.output_tokens,
                        structured_output=raw.structured,
                        raw_text_preview=raw.raw_text,
                    )
                if rung_id == "haiku_naive":
                    assert creds.anthropic_api_key
                    raw = await run_haiku_naive(payload_text, sub_task, creds.anthropic_api_key)
                    trace_extras[rung_id] = (raw.request_params, raw.stop_reason, raw.thinking_tokens)
                    return _build_rung_result(
                        rung_id="haiku_naive",
                        model_id=raw.model_id,
                        provider="Anthropic",
                        latency_ms=raw.latency_ms,
                        input_tokens=raw.input_tokens,
                        output_tokens=raw.output_tokens,
                        structured_output=raw.structured,
                        raw_text_preview=raw.raw_text,
                    )
                if rung_id == "haiku_calibrated":
                    assert creds.anthropic_api_key
                    raw = await run_haiku_calibrated(payload_text, sub_task, schema, creds.anthropic_api_key)
                    trace_extras[rung_id] = (raw.request_params, raw.stop_reason, raw.thinking_tokens)
                    return _build_rung_result(
                        rung_id="haiku_calibrated",
                        model_id=raw.model_id,
                        provider="Anthropic",
                        latency_ms=raw.latency_ms,
                        input_tokens=raw.input_tokens,
                        output_tokens=raw.output_tokens,
                        structured_output=raw.structured,
                        raw_text_preview=raw.raw_text,
                    )
                assert creds.gemini_api_key
                dec = await run_gemini_decision(payload_text, questions, creds.gemini_api_key)
                trace_extras[rung_id] = ({"api_version": "v1beta"}, "completed", 0)
                return _build_rung_result(
                    rung_id="gemini_decision",
                    model_id=dec.model_id,
                    provider="Google Gemini Decisions API",
                    latency_ms=dec.latency_ms,
                    input_tokens=dec.input_tokens,
                    output_tokens=dec.output_tokens,
                    structured_output=dec.structured_summary,
                    decision_probabilities=dec.decision_probabilities,
                )
            except Exception as exc:
                fallback_model = (
                    "claude-sonnet-5-5"
                    if rung_id == "sonnet_naive"
                    else ("claude-haiku-5-5" if rung_id == "haiku_calibrated" else "gemini-decision-1")
                )
                return _build_rung_result(
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

        results = list(await asyncio.gather(*(_run_one(r) for r in req.rungs)))
        if creds.uses_server_budget:
            total_spend = sum(r.finops.total_cost_usd for r in results if r.status == "ok")
            credit_shield.record_server_spend(total_spend)
        mode_used = "live"

    # Compute savings vs Rung 1 (or fallback synthetic Sonnet estimate if Rung 1 failed/omitted)
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
        else compute_run_finops("claude-sonnet-5-5", ref_input_tokens, 310).total_cost_usd
    )

    for res in results:
        if res.status == "ok" and naive_cost > 0:
            res.savings_vs_naive_pct = round(((naive_cost - res.finops.total_cost_usd) / naive_cost) * 100, 2)
        if res.status == "ok" and ground_truth is not None:
            res.accuracy = evaluate_rung_accuracy(
                rung_id=res.rung_id,
                sub_task=sub_task,
                ground_truth=ground_truth,
                structured_output=res.structured_output,
                raw_text=res.raw_text_preview,
            )

    # Persist partitioned traces (category / use_case / model / pattern) for every rung
    for res in results:
        req_params, stop_reason, think_tok = trace_extras.get(res.rung_id, (None, None, 0))
        extra_meta: dict[str, Any] = {
            "source_endpoint": "/api/cat1/run",
            "savings_vs_naive_pct": res.savings_vs_naive_pct,
        }
        if res.accuracy is not None:
            extra_meta["accuracy"] = res.accuracy.model_dump()
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
        "(0 output tokens, $0.04–$0.10/M in), but cannot rewrite text. Companion <1ms regex scrubbing "
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

    batch_results: list[BatchItemResult] = []
    sonnet_in_tokens_list: list[int] = []
    sonnet_out_tokens_list: list[int] = []
    haiku_naive_in_tokens_list: list[int] = []
    haiku_naive_out_tokens_list: list[int] = []
    gemini_in_tokens_list: list[int] = []
    batch_run_group_id = str(uuid4())
    batch_trace_payloads: list[tuple[dict[str, Any], PiiRedactionResult, list[RungExecutionResult]]] = []

    tally: dict[str, dict[str, int]] = {
        rid: {"matched": 0, "fields": 0, "exact": 0, "items": 0}
        for rid in ("sonnet_naive", "haiku_naive", "haiku_calibrated", "gemini_decision")
    }

    def _accumulate_accuracy(
        sub: str,
        gt: dict[str, Any],
        rungs_map: dict[str, RungExecutionResult],
    ) -> dict[str, RungAccuracyEvaluation]:
        evals: dict[str, RungAccuracyEvaluation] = {}
        for rid, rung_res in rungs_map.items():
            ev = evaluate_rung_accuracy(
                rung_id=rid,
                sub_task=sub,
                ground_truth=gt,
                structured_output=rung_res.structured_output,
                raw_text=rung_res.raw_text_preview,
            )
            rung_res.accuracy = ev
            evals[rid] = ev
            tally[rid]["matched"] += ev.matched_count
            tally[rid]["fields"] += ev.total_fields
            tally[rid]["exact"] += 1 if ev.exact_match else 0
            tally[rid]["items"] += 1
        return evals

    if req.mode == "replay":
        replays = load_golden_replays()
        preset_replays = replays.get("presets") or {}
        extra_replays = replays.get("batch_items") or {}

        for item in selected_items:
            iid = item["id"]
            sub = item["sub_task"]
            gt = dict(item.get("ground_truth") or {})
            pii = scrub_pii_deterministic(item["payload"])
            if iid in preset_replays:
                rungs = preset_replays[iid]["rungs"]
                s = rungs["sonnet_naive"]
                hn = rungs["haiku_naive"]
                h = rungs["haiku_calibrated"]
                g = rungs["gemini_decision"]

                in_tok = int(h["input_tokens"])
                s_in_tok = int(s["input_tokens"])
                hn_in_tok = int(hn["input_tokens"])
                s_out = int(s["output_tokens"])
                hn_out = int(hn["output_tokens"])
                h_out = int(h["output_tokens"])
                s_lat = int(s["latency_ms"])
                hn_lat = int(hn["latency_ms"])
                h_lat = int(h["latency_ms"])
                g_lat = int(g["latency_ms"])
                s_raw_text = s.get("raw_text_preview") or ""
                hn_raw_text = hn.get("raw_text_preview") or ""
                h_dec = h["structured_output"]
                g_dec = g["structured_output"]
                g_probs = g["decision_probabilities"]
                conf_vals = [float(v.get("confidence", 0.9)) for v in g_probs.values()] if g_probs else [0.92]
                g_conf = round(sum(conf_vals) / max(1, len(conf_vals)), 3)
                h_raw_text = h.get("raw_text_preview")
                h_model = h.get("model_id", "claude-haiku-5-5")
                s_model = s.get("model_id", "claude-sonnet-5-5")
                hn_model = hn.get("model_id", "claude-haiku-5-5")
                g_model = g.get("model_id", "gemini-decision-1")
                g_in_tok = int(g.get("input_tokens", in_tok))
            else:
                b = extra_replays[iid]
                in_tok = int(b["input_tokens"])
                s_in_tok = int(b.get("sonnet_input_tokens", in_tok))
                hn_in_tok = int(b.get("haiku_naive_input_tokens", s_in_tok))
                s_out = int(b.get("sonnet_output_tokens", b.get("sonnet_est_output_tokens", 285)))
                hn_out = int(b.get("haiku_naive_output_tokens", s_out))
                h_out = int(b["haiku_output_tokens"])
                s_lat = int(b.get("sonnet_latency_ms", 4200))
                hn_lat = int(b.get("haiku_naive_latency_ms", 2600))
                h_lat = int(b["haiku_latency_ms"])
                g_lat = int(b["gemini_latency_ms"])
                s_raw_text = b.get("sonnet_raw_text") or ""
                hn_raw_text = b.get("haiku_naive_raw_text") or ""
                h_dec = b["haiku_decision"]
                g_dec = b["gemini_decision"]
                g_conf = float(b["gemini_confidence"])
                g_probs = None
                h_raw_text = json.dumps(h_dec)
                h_model = "claude-haiku-5-5"
                s_model = "claude-sonnet-5-5"
                hn_model = "claude-haiku-5-5"
                g_model = "gemini-decision-1"
                g_in_tok = int(b.get("gemini_input_tokens", s_in_tok))

            s_rung = _build_rung_result(
                rung_id="sonnet_naive",
                model_id=s_model,
                provider="Anthropic",
                latency_ms=s_lat,
                input_tokens=s_in_tok,
                output_tokens=s_out,
                structured_output={"mode": "unstructured_chat_prose", "char_length": len(s_raw_text)},
                raw_text_preview=s_raw_text,
            )
            hn_rung = _build_rung_result(
                rung_id="haiku_naive",
                model_id=hn_model,
                provider="Anthropic",
                latency_ms=hn_lat,
                input_tokens=hn_in_tok,
                output_tokens=hn_out,
                structured_output={"mode": "unstructured_chat_prose", "char_length": len(hn_raw_text)},
                raw_text_preview=hn_raw_text,
            )
            h_rung = _build_rung_result(
                rung_id="haiku_calibrated",
                model_id=h_model,
                provider="Anthropic",
                latency_ms=h_lat,
                input_tokens=in_tok,
                output_tokens=h_out,
                structured_output=h_dec,
                raw_text_preview=h_raw_text,
            )
            g_rung = _build_rung_result(
                rung_id="gemini_decision",
                model_id=g_model,
                provider="Google Gemini Decisions API",
                latency_ms=g_lat,
                input_tokens=g_in_tok,
                output_tokens=0,
                structured_output=g_dec,
                decision_probabilities=g_probs,
            )
            rungs_map = {
                "sonnet_naive": s_rung,
                "haiku_naive": hn_rung,
                "haiku_calibrated": h_rung,
                "gemini_decision": g_rung,
            }
            evals = _accumulate_accuracy(sub, gt, rungs_map)
            batch_trace_payloads.append((item, pii, [s_rung, hn_rung, h_rung, g_rung]))

            sonnet_in_tokens_list.append(s_in_tok)
            sonnet_out_tokens_list.append(s_out)
            haiku_naive_in_tokens_list.append(hn_in_tok)
            haiku_naive_out_tokens_list.append(hn_out)
            gemini_in_tokens_list.append(g_in_tok)
            batch_results.append(
                BatchItemResult(
                    item_id=iid,
                    title=item["title"],
                    sub_task=sub,
                    input_tokens=in_tok,
                    haiku_output_tokens=h_out,
                    haiku_decision=h_dec,
                    gemini_decision=g_dec,
                    gemini_confidence=g_conf,
                    pii_redactions=pii.total_redactions,
                    haiku_latency_ms=h_lat,
                    gemini_latency_ms=g_lat,
                    ground_truth=gt,
                    sonnet_accuracy_pct=evals["sonnet_naive"].field_accuracy_pct,
                    haiku_naive_accuracy_pct=evals["haiku_naive"].field_accuracy_pct,
                    haiku_accuracy_pct=evals["haiku_calibrated"].field_accuracy_pct,
                    gemini_accuracy_pct=evals["gemini_decision"].field_accuracy_pct,
                    sonnet_exact=evals["sonnet_naive"].exact_match,
                    haiku_naive_exact=evals["haiku_naive"].exact_match,
                    haiku_exact=evals["haiku_calibrated"].exact_match,
                    gemini_exact=evals["gemini_decision"].exact_match,
                )
            )
        mode_used = "replay"
    else:
        creds = credit_shield.resolve_live_credentials(
            http_request,
            need_anthropic=True,
            need_gemini=True,
        )
        assert creds.anthropic_api_key and creds.gemini_api_key
        sem = asyncio.Semaphore(4)

        async def _eval_item(item: dict[str, Any]) -> tuple[BatchItemResult, int, int, int, int, int, float]:
            sub = item["sub_task"]
            text = item["payload"]
            gt = dict(item.get("ground_truth") or {})
            pii = scrub_pii_deterministic(text)
            async with sem:
                s_res, hn_res, h_res, g_res = await asyncio.gather(
                    run_sonnet_naive(text, sub, creds.anthropic_api_key or ""),
                    run_haiku_naive(text, sub, creds.anthropic_api_key or ""),
                    run_haiku_calibrated(text, sub, get_schema_for_subtask(sub), creds.anthropic_api_key or ""),
                    run_gemini_decision(text, get_questions_for_subtask(sub), creds.gemini_api_key or ""),
                )

            s_rung = _build_rung_result(
                rung_id="sonnet_naive",
                model_id=s_res.model_id,
                provider="Anthropic",
                latency_ms=s_res.latency_ms,
                input_tokens=s_res.input_tokens,
                output_tokens=s_res.output_tokens,
                structured_output=s_res.structured,
                raw_text_preview=s_res.raw_text,
            )
            hn_rung = _build_rung_result(
                rung_id="haiku_naive",
                model_id=hn_res.model_id,
                provider="Anthropic",
                latency_ms=hn_res.latency_ms,
                input_tokens=hn_res.input_tokens,
                output_tokens=hn_res.output_tokens,
                structured_output=hn_res.structured,
                raw_text_preview=hn_res.raw_text,
            )
            h_rung = _build_rung_result(
                rung_id="haiku_calibrated",
                model_id=h_res.model_id,
                provider="Anthropic",
                latency_ms=h_res.latency_ms,
                input_tokens=h_res.input_tokens,
                output_tokens=h_res.output_tokens,
                structured_output=h_res.structured,
                raw_text_preview=h_res.raw_text,
            )
            g_rung = _build_rung_result(
                rung_id="gemini_decision",
                model_id=g_res.model_id,
                provider="Google Gemini Decisions API",
                latency_ms=g_res.latency_ms,
                input_tokens=g_res.input_tokens,
                output_tokens=g_res.output_tokens,
                structured_output=g_res.structured_summary,
                decision_probabilities=g_res.decision_probabilities,
            )
            evals = _accumulate_accuracy(
                sub,
                gt,
                {
                    "sonnet_naive": s_rung,
                    "haiku_naive": hn_rung,
                    "haiku_calibrated": h_rung,
                    "gemini_decision": g_rung,
                },
            )
            batch_trace_payloads.append((item, pii, [s_rung, hn_rung, h_rung, g_rung]))

            confs = [float(v.get("confidence", 0.0)) for v in g_res.decision_probabilities.values()]
            avg_conf = round(sum(confs) / max(1, len(confs)), 3)
            item_spend = (
                s_rung.finops.total_cost_usd
                + hn_rung.finops.total_cost_usd
                + h_rung.finops.total_cost_usd
                + g_rung.finops.total_cost_usd
            )
            return (
                BatchItemResult(
                    item_id=item["id"],
                    title=item["title"],
                    sub_task=sub,
                    input_tokens=h_res.input_tokens,
                    haiku_output_tokens=h_res.output_tokens,
                    haiku_decision=h_res.structured,
                    gemini_decision=g_res.structured_summary,
                    gemini_confidence=avg_conf,
                    pii_redactions=pii.total_redactions,
                    haiku_latency_ms=h_res.latency_ms,
                    gemini_latency_ms=g_res.latency_ms,
                    ground_truth=gt,
                    sonnet_accuracy_pct=evals["sonnet_naive"].field_accuracy_pct,
                    haiku_naive_accuracy_pct=evals["haiku_naive"].field_accuracy_pct,
                    haiku_accuracy_pct=evals["haiku_calibrated"].field_accuracy_pct,
                    gemini_accuracy_pct=evals["gemini_decision"].field_accuracy_pct,
                    sonnet_exact=evals["sonnet_naive"].exact_match,
                    haiku_naive_exact=evals["haiku_naive"].exact_match,
                    haiku_exact=evals["haiku_calibrated"].exact_match,
                    gemini_exact=evals["gemini_decision"].exact_match,
                ),
                s_res.input_tokens,
                s_res.output_tokens,
                hn_res.input_tokens,
                hn_res.output_tokens,
                g_res.input_tokens,
                item_spend,
            )

        live_tuples = list(await asyncio.gather(*(_eval_item(it) for it in selected_items)))
        batch_results = [t[0] for t in live_tuples]
        sonnet_in_tokens_list = [t[1] for t in live_tuples]
        sonnet_out_tokens_list = [t[2] for t in live_tuples]
        haiku_naive_in_tokens_list = [t[3] for t in live_tuples]
        haiku_naive_out_tokens_list = [t[4] for t in live_tuples]
        gemini_in_tokens_list = [t[5] for t in live_tuples]
        if creds.uses_server_budget:
            credit_shield.record_server_spend(sum(t[6] for t in live_tuples))
        mode_used = "live"

    for item, pii, rung_list in batch_trace_payloads:
        for rung_res in rung_list:
            extra_meta: dict[str, Any] = {"source_endpoint": "/api/cat1/batch"}
            if rung_res.accuracy is not None:
                extra_meta["accuracy"] = rung_res.accuracy.model_dump()
            persist_cat1_trace(
                source_mode=mode_used,
                run_group_id=batch_run_group_id,
                item_id=item["id"],
                item_title=item["title"],
                sub_task=item["sub_task"],
                payload_text=item["payload"],
                rung_res=rung_res,
                pii_result=pii,
                extra_metadata=extra_meta,
            )

    count = max(1, len(batch_results))
    avg_in = round(sum(it.input_tokens for it in batch_results) / count)
    avg_h_out = round(sum(it.haiku_output_tokens for it in batch_results) / count)
    avg_s_in = round(sum(sonnet_in_tokens_list) / count)
    avg_s_out = round(sum(sonnet_out_tokens_list) / count)
    avg_hn_in = round(sum(haiku_naive_in_tokens_list) / count)
    avg_hn_out = round(sum(haiku_naive_out_tokens_list) / count)
    avg_g_in = round(sum(gemini_in_tokens_list) / count)

    def _acc_stats(rid: str) -> tuple[float, float]:
        t = tally[rid]
        f_pct = round((t["matched"] / t["fields"]) * 100, 1) if t["fields"] > 0 else 0.0
        e_pct = round((t["exact"] / t["items"]) * 100, 1) if t["items"] > 0 else 0.0
        return f_pct, e_pct

    s_f_pct, s_e_pct = _acc_stats("sonnet_naive")
    hn_f_pct, hn_e_pct = _acc_stats("haiku_naive")
    h_f_pct, h_e_pct = _acc_stats("haiku_calibrated")
    g_f_pct, g_e_pct = _acc_stats("gemini_decision")

    tiers_spec = [
        ("sonnet_naive", "1A. Sonnet 5.5 (Unconstrained Prose)", "claude-sonnet-5-5", avg_s_in, avg_s_out, "Stateless API w/ chat-style prose prompt (Anti-Pattern)", s_f_pct, s_e_pct, "0% (Unconstrained prose)"),
        ("haiku_naive", "1B. Haiku 5.5 (Unconstrained Prose)", "claude-haiku-5-5", avg_hn_in, avg_hn_out, "Model swap only: prose prompt, no JSON schema", hn_f_pct, hn_e_pct, "0% (Unconstrained prose)"),
        ("haiku_realtime", "2. Haiku 5.5 + Strict JSON", "claude-haiku-5-5", avg_in, avg_h_out, "Real-time Tier-1 schema + thinking disabled", h_f_pct, h_e_pct, "100% Typed JSON Schema"),
        ("haiku_batch", "3. Haiku 5.5 Message Batch (-50%)", "claude-haiku-5-5-batch", avg_in, avg_h_out, "Async batch ingestion (50% Anthropic Batch discount)", h_f_pct, h_e_pct, "100% Typed JSON (-50% async)"),
        ("gemini_decision", "4. Gemini Decision 1 (System-1)", "gemini-decision-1", avg_g_in, 0, "0 output tokens + regex PII gate · $0.10/M input", g_f_pct, g_e_pct, "100% Closed-Set Decisions API"),
        ("typesafe_jev", "5. TypeSafe Jev (Rate Card Ref)", "typesafe-jev", avg_s_in, 0, "FinOps benchmark · $0.042/M input · $0 output", None, None, "Rate-card ref (unexecuted)"),
    ]

    naive_finops = compute_run_finops("claude-sonnet-5-5", avg_s_in, avg_s_out)
    cfo_rows: list[CfoScaleRow] = []
    for tid, label, mid, tin, tout, scope_note, f_acc, e_acc, schema_lbl in tiers_spec:
        f = compute_run_finops(mid, tin, tout)
        savings = round(((naive_finops.total_cost_usd - f.total_cost_usd) / naive_finops.total_cost_usd) * 100, 2)
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

    accuracy_rollup = [
        ModelAccuracyRollup(
            rung_id="sonnet_naive",
            label="1A. Sonnet 5.5 (Prose)",
            model_id="claude-sonnet-5-5",
            schema_compliance_pct=0.0,
            fields_matched=tally["sonnet_naive"]["matched"],
            fields_total=tally["sonnet_naive"]["fields"],
            field_accuracy_pct=s_f_pct,
            exact_items_matched=tally["sonnet_naive"]["exact"],
            items_total=tally["sonnet_naive"]["items"],
            exact_match_pct=s_e_pct,
            cost_per_1k_usd=cfo_rows[0].cost_per_1k_usd,
            notes="Must scrape free-form prose via regex; high latency & $10/M output cost.",
        ),
        ModelAccuracyRollup(
            rung_id="haiku_naive",
            label="1B. Haiku 5.5 (Prose)",
            model_id="claude-haiku-5-5",
            schema_compliance_pct=0.0,
            fields_matched=tally["haiku_naive"]["matched"],
            fields_total=tally["haiku_naive"]["fields"],
            field_accuracy_pct=hn_f_pct,
            exact_items_matched=tally["haiku_naive"]["exact"],
            items_total=tally["haiku_naive"]["items"],
            exact_match_pct=hn_e_pct,
            cost_per_1k_usd=cfo_rows[1].cost_per_1k_usd,
            notes="20x cheaper than Sonnet prose, yet still unparsed prose without schema guarantees.",
        ),
        ModelAccuracyRollup(
            rung_id="haiku_calibrated",
            label="2. Haiku 5.5 + Strict JSON",
            model_id="claude-haiku-5-5",
            schema_compliance_pct=100.0,
            fields_matched=tally["haiku_calibrated"]["matched"],
            fields_total=tally["haiku_calibrated"]["fields"],
            field_accuracy_pct=h_f_pct,
            exact_items_matched=tally["haiku_calibrated"]["exact"],
            items_total=tally["haiku_calibrated"]["items"],
            exact_match_pct=h_e_pct,
            cost_per_1k_usd=cfo_rows[2].cost_per_1k_usd,
            notes="Zero regex scraping; identical prompt & accuracy runs asynchronously at 50% off.",
        ),
        ModelAccuracyRollup(
            rung_id="gemini_decision",
            label="4. Gemini Decision 1",
            model_id="gemini-decision-1",
            schema_compliance_pct=100.0,
            fields_matched=tally["gemini_decision"]["matched"],
            fields_total=tally["gemini_decision"]["fields"],
            field_accuracy_pct=g_f_pct,
            exact_items_matched=tally["gemini_decision"]["exact"],
            items_total=tally["gemini_decision"]["items"],
            exact_match_pct=g_e_pct,
            cost_per_1k_usd=cfo_rows[4].cost_per_1k_usd,
            notes="Non-autoregressive closed-set classifier with calibrated probabilities & 0 output tokens.",
        ),
    ]

    by_tier = {r.tier_id: r for r in cfo_rows}
    return Cat1BatchResponse(
        mode_used=mode_used,  # type: ignore[arg-type]
        total_items=len(batch_results),
        avg_input_tokens=avg_in,
        items=batch_results,
        cfo_comparison=cfo_rows,
        summary_callout=(
            f"At NovaMart scale (1M intake events/month, {avg_s_in} raw / {avg_in} schema in tok/item): "
            f"Sonnet 5.5 Prose costs ${by_tier['sonnet_naive'].monthly_1m_usd:,.2f}/mo ({s_f_pct:.1f}% field acc), "
            f"Haiku 5.5 + Strict JSON drops to ${by_tier['haiku_realtime'].monthly_1m_usd:,.2f}/mo ({h_f_pct:.1f}% field acc · Batch ${by_tier['haiku_batch'].monthly_1m_usd:,.2f}/mo), "
            f"and Gemini Decision 1 runs in real time for ${by_tier['gemini_decision'].monthly_1m_usd:,.2f}/mo ({g_f_pct:.1f}% field acc)."
        ),
        accuracy_rollup=accuracy_rollup,
    )
