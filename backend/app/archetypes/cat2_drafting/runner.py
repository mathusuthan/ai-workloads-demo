"""Orchestrates Category 2 3-Rung Synthesis Arena & Surgical HITL Section Regeneration."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4
from fastapi import HTTPException, Request

from app.archetypes.cat2_drafting.prompts import (
    get_section_regen_system_prompt,
    get_templated_draft_system_prompt,
    get_unbounded_draft_system_prompt,
)
from app.archetypes.cat2_drafting.schemas import (
    STRUCTURED_DRAFT_JSON_SCHEMA,
    get_single_section_schema,
)
from app.config import get_settings
from app.core.anthropic_service import (
    run_cat2_structured_draft,
    run_cat2_unbounded_sonnet,
)
from app.core.credit_shield import credit_shield
from app.core.pricing import compute_run_finops
from app.core.trace_store import (
    TracePartition,
    TraceRecord,
    TraceRequestEnvelope,
    TraceResponseEnvelope,
    record_trace,
)
from app.data.cat2_fixtures import CAT2_PRESETS, CAT2_REVIEWER_PRESETS
from app.models import (
    Cat2RunRequest,
    Cat2RunResponse,
    Cat2RungResult,
    Cat2SectionRegenRequest,
    Cat2SectionRegenResponse,
    HitlCostComparison,
)

CAT2_CATEGORY = "cat2_synthesis_drafting"
CAT2_RUNG_TO_PATTERN: dict[str, str] = {
    "sonnet_unbounded": "unbounded_longform_draft",
    "sonnet_templated": "section_templated_bounded",
    "haiku_templated": "tier_routed_template_draft",
}
HITL_REGEN_PATTERN = "hitl_section_regen"


def _preset_map() -> dict[str, dict[str, Any]]:
    return {p["id"]: p for p in CAT2_PRESETS}


def load_cat2_replays() -> dict[str, Any]:
    replays_file = Path(get_settings().replays_dir) / "cat2_golden_replays.json"
    if not replays_file.is_file():
        return {"presets": {}, "section_regens": {}}
    return json.loads(replays_file.read_text(encoding="utf-8"))


def build_section_regen_payload(
    *,
    source_text: str,
    section_key: str,
    current_section: Any,
    reviewer_instruction: str,
) -> str:
    """Build concise single-section HITL rewrite prompt input."""
    serialized_curr = (
        json.dumps(current_section, indent=2)
        if not isinstance(current_section, str)
        else current_section
    )
    return (
        f"=== SOURCE BUNDLE ===\n{source_text}\n\n"
        f"=== TARGET SECTION TO REWRITE (`{section_key}`) ===\n{serialized_curr}\n\n"
        f"=== REVIEWER INSTRUCTION ===\n{reviewer_instruction}"
    )


def _cat2_rung_metadata(rung_id: str) -> tuple[str, str, list[str]]:
    if rung_id == "sonnet_unbounded":
        return (
            "Rung 1 · Sonnet 5.5 (Unbounded Longform)",
            "Anti-Pattern: Uncapped Output Tax",
            [
                "Prompts Claude Sonnet 5.5 ($2.00/M in · $10.00/M out) for an exhaustive multi-page narrative + appendices.",
                "At 5x output token pricing, ~4,700+ unbounded output tokens drive >85% of your entire inference bill.",
            ],
        )
    if rung_id == "sonnet_templated":
        return (
            "Rung 2 · Sonnet 5.5 + Bounded Section Template",
            "Slide 4 Lever: Section-Bounded Schema",
            [
                "Same frontier Sonnet 5.5 quality anchored to a 4-section JSON schema with strict word caps & disabled thinking.",
                "Cuts output tokens by ~50%–65%, cutting unit cost >45% while enabling single-section HITL locking & regen.",
            ],
        )
    return (
        "Rung 3 · Haiku 5.5 First-Draft Template",
        "Tier-Routed Draft (-97% Cost)",
        [
            "Runs the exact same 4-section bounded schema on Haiku 5.5 ($0.10/M in · $0.50/M out).",
            "Generates a complete auditable first draft for <$0.001 so reviewers escalate only critical sections to Sonnet 5.5.",
        ],
    )


def build_cat2_rung_result(
    *,
    rung_id: str,
    model_id: str,
    provider: str,
    latency_ms: int,
    input_tokens: int,
    output_tokens: int,
    structured_draft: dict[str, Any] | None = None,
    raw_markdown: str | None = None,
    thinking_tokens: int = 0,
    status: str = "ok",
    error_message: str | None = None,
) -> Cat2RungResult:
    title, badge, notes = _cat2_rung_metadata(rung_id)
    finops = compute_run_finops(
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    return Cat2RungResult(
        rung_id=rung_id,  # type: ignore[arg-type]
        rung_title=title,
        badge_text=badge,
        model_id=model_id,
        provider=provider,
        status=status,  # type: ignore[arg-type]
        error_message=error_message,
        latency_ms=latency_ms,
        structured_draft=structured_draft or {},
        raw_markdown=raw_markdown,
        thinking_tokens=thinking_tokens,
        finops=finops,
        savings_vs_unbounded_pct=0.0,
        architectural_notes=notes,
    )


def build_cat2_request_envelope(
    *,
    pattern: str,
    sub_task: str,
    payload_text: str,
    model_id: str = "claude-sonnet-5-5",
    section_key: str | None = None,
    request_params_override: dict[str, Any] | None = None,
) -> TraceRequestEnvelope:
    thinking_default = (
        {"type": "between_tools"} if "sonnet" in model_id else {"type": "disabled"}
    )
    if pattern == "unbounded_longform_draft":
        return TraceRequestEnvelope(
            provider="Anthropic",
            endpoint="messages.create",
            system_instruction=get_unbounded_draft_system_prompt(sub_task),
            parameters=request_params_override
            or {
                "max_tokens": 8000,
                "endpoint": "messages.create",
                "thinking": {"type": "between_tools"},
            },
            input_payload=payload_text,
        )
    if pattern == HITL_REGEN_PATTERN:
        sk = section_key or "executive_summary"
        return TraceRequestEnvelope(
            provider="Anthropic",
            endpoint="messages.create",
            system_instruction=get_section_regen_system_prompt(sub_task, sk),
            parameters=request_params_override
            or {
                "max_tokens": 1800,
                "thinking": thinking_default,
                "output_config": {"format": {"type": "json_schema"}},
            },
            json_schema=get_single_section_schema(sk),
            input_payload=payload_text,
        )
    return TraceRequestEnvelope(
        provider="Anthropic",
        endpoint="messages.create",
        system_instruction=get_templated_draft_system_prompt(sub_task),
        parameters=request_params_override
        or {
            "max_tokens": 3000,
            "thinking": thinking_default,
            "output_config": {"format": {"type": "json_schema"}},
        },
        json_schema=STRUCTURED_DRAFT_JSON_SCHEMA,
        input_payload=payload_text,
    )


def persist_cat2_trace(
    *,
    source_mode: str,
    run_group_id: str,
    item_id: str,
    item_title: str,
    sub_task: str,
    model_id: str,
    pattern: str,
    payload_text: str,
    status: str,
    latency_ms: int,
    finops_dict: dict[str, Any],
    raw_text: str | None,
    structured_output: dict[str, Any],
    section_key: str | None = None,
    request_params_override: dict[str, Any] | None = None,
    stop_reason: str | None = None,
    thinking_tokens: int = 0,
    error_message: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> Path:
    """Persist one partitioned Category 2 TraceRecord."""
    envelope = build_cat2_request_envelope(
        pattern=pattern,
        sub_task=sub_task,
        payload_text=payload_text,
        model_id=model_id,
        section_key=section_key,
        request_params_override=request_params_override,
    )
    fin = dict(finops_dict)
    if thinking_tokens:
        fin["thinking_tokens"] = thinking_tokens

    record = TraceRecord(
        run_group_id=run_group_id,
        source_mode=source_mode,  # type: ignore[arg-type]
        item_id=item_id,
        item_title=item_title,
        partition=TracePartition(
            category=CAT2_CATEGORY,
            use_case=sub_task,
            model=model_id,
            pattern=pattern,
        ),
        request=envelope,
        response=TraceResponseEnvelope(
            status=status,  # type: ignore[arg-type]
            error_message=error_message,
            stop_reason=stop_reason,
            latency_ms=latency_ms,
            raw_text=raw_text,
            structured_output=structured_output,
        ),
        finops=fin,
        extra_metadata=extra_metadata or {},
    )
    return record_trace(record)


def build_hitl_cost_comparison(
    *,
    model_id: str,
    surgical_in_tokens: int,
    surgical_out_tokens: int,
    section_key: str,
) -> HitlCostComparison:
    """Compare single-section HITL regeneration vs naive full-draft chat re-prompt."""
    surgical = compute_run_finops(model_id, surgical_in_tokens, surgical_out_tokens)
    naive = compute_run_finops(
        "claude-sonnet-5-5",
        input_tokens=surgical_in_tokens + 3200,
        output_tokens=3200,
    )
    savings_pct = (
        round(((naive.total_cost_usd - surgical.total_cost_usd) / naive.total_cost_usd) * 100, 2)
        if naive.total_cost_usd > 0
        else 0.0
    )
    tokens_avoided = max(
        0,
        (naive.input_tokens + naive.output_tokens) - (surgical.input_tokens + surgical.output_tokens),
    )
    return HitlCostComparison(
        surgical_finops=surgical,
        naive_full_reprompt_finops=naive,
        revision_savings_pct=savings_pct,
        tokens_avoided=tokens_avoided,
        explanation=(
            f"Regenerating only `{section_key}` on {surgical.model_label} emitted "
            f"{surgical.output_tokens} output tokens (${surgical.cost_per_1k_usd:.2f}/1k edits) vs. "
            f"re-prompting the full ~3,200-token narrative in chat (${naive.cost_per_1k_usd:.2f}/1k edits) "
            f"— avoiding {tokens_avoided:,} tokens (-{savings_pct:.1f}%)."
        ),
    )


async def execute_cat2_run(
    req: Cat2RunRequest,
    http_request: Request | None = None,
) -> Cat2RunResponse:
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
    run_group_id = str(uuid4())
    item_id = preset["id"] if preset else "custom"
    item_title = preset["title"] if preset else "Custom Synthesis Bundle"
    trace_extras: dict[str, tuple[dict[str, Any] | None, str | None]] = {}

    if req.mode == "replay":
        is_exact_preset = preset is not None and payload_text.strip() == preset["payload"].strip()
        if not is_exact_preset:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Verified Replay mode ($0) only serves the 4 pre-captured NovaMart Category 2 bundles. "
                    "Re-select an unmodified preset or switch to Live API mode for custom drafts."
                ),
            )
        replays = load_cat2_replays()
        preset_trace = (replays.get("presets") or {}).get(preset["id"])
        if not preset_trace:
            raise HTTPException(status_code=404, detail=f"Replay trace missing for {preset['id']}.")

        results: list[Cat2RungResult] = []
        for rung_id in req.rungs:
            r_data = preset_trace["rungs"][rung_id]
            trace_extras[rung_id] = (None, r_data.get("stop_reason") or "end_turn")
            results.append(
                build_cat2_rung_result(
                    rung_id=rung_id,
                    model_id=r_data["model_id"],
                    provider=r_data["provider"],
                    latency_ms=int(r_data["latency_ms"]),
                    input_tokens=int(r_data["input_tokens"]),
                    output_tokens=int(r_data["output_tokens"]),
                    structured_draft=r_data.get("structured_draft") or {},
                    raw_markdown=r_data.get("raw_markdown"),
                    thinking_tokens=int(r_data.get("thinking_tokens") or 0),
                )
            )
        mode_used = "replay"
    else:
        # Category 2 uses Anthropic ONLY (user constraint: Gemini Decision Model for Category 1 only)
        creds = credit_shield.resolve_live_credentials(
            http_request,
            need_anthropic=True,
            need_gemini=False,
        )
        assert creds.anthropic_api_key

        async def _run_one(rung_id: str) -> Cat2RungResult:
            try:
                if rung_id == "sonnet_unbounded":
                    raw = await run_cat2_unbounded_sonnet(
                        payload_text,
                        get_unbounded_draft_system_prompt(sub_task),
                        creds.anthropic_api_key or "",
                    )
                    trace_extras[rung_id] = (raw.request_params, raw.stop_reason)
                    return build_cat2_rung_result(
                        rung_id="sonnet_unbounded",
                        model_id=raw.model_id,
                        provider="Anthropic",
                        latency_ms=raw.latency_ms,
                        input_tokens=raw.input_tokens,
                        output_tokens=raw.output_tokens,
                        structured_draft=raw.structured,
                        raw_markdown=raw.raw_text,
                        thinking_tokens=raw.thinking_tokens,
                    )

                model_tier = (
                    "claude-sonnet-5-5" if rung_id == "sonnet_templated" else "claude-haiku-5-5"
                )
                raw = await run_cat2_structured_draft(
                    payload_text,
                    get_templated_draft_system_prompt(sub_task),
                    STRUCTURED_DRAFT_JSON_SCHEMA,
                    model_tier,
                    creds.anthropic_api_key or "",
                    max_tokens=3000,
                )
                trace_extras[rung_id] = (raw.request_params, raw.stop_reason)
                return build_cat2_rung_result(
                    rung_id=rung_id,
                    model_id=raw.model_id,
                    provider="Anthropic",
                    latency_ms=raw.latency_ms,
                    input_tokens=raw.input_tokens,
                    output_tokens=raw.output_tokens,
                    structured_draft=raw.structured,
                    raw_markdown=raw.raw_text,
                    thinking_tokens=raw.thinking_tokens,
                )
            except Exception as exc:
                fallback_model = (
                    "claude-haiku-5-5" if rung_id == "haiku_templated" else "claude-sonnet-5-5"
                )
                return build_cat2_rung_result(
                    rung_id=rung_id,
                    model_id=fallback_model,
                    provider="Anthropic",
                    latency_ms=0,
                    input_tokens=0,
                    output_tokens=0,
                    status="error",
                    error_message=str(exc)[:300],
                )

        results = list(await asyncio.gather(*(_run_one(r) for r in req.rungs)))
        if creds.uses_server_budget:
            total_spend = sum(r.finops.total_cost_usd for r in results if r.status == "ok")
            credit_shield.record_server_spend(total_spend)
        mode_used = "live"

    unbounded_res = next(
        (r for r in results if r.rung_id == "sonnet_unbounded" and r.status == "ok"),
        None,
    )
    est_tokens = max(1, round(len(payload_text) / 2.15))
    ref_input_tokens = (
        unbounded_res.finops.input_tokens
        if unbounded_res
        else next(
            (r.finops.input_tokens for r in results if r.status == "ok" and r.finops.input_tokens > 0),
            est_tokens,
        )
    )
    unbounded_cost = (
        unbounded_res.finops.total_cost_usd
        if unbounded_res
        else compute_run_finops("claude-sonnet-5-5", ref_input_tokens, 4800).total_cost_usd
    )

    for res in results:
        if res.status == "ok" and unbounded_cost > 0:
            res.savings_vs_unbounded_pct = round(
                ((unbounded_cost - res.finops.total_cost_usd) / unbounded_cost) * 100, 2
            )

    # Persist partitioned traces (category / use_case / model / pattern)
    for res in results:
        req_params, stop_reason = trace_extras.get(res.rung_id, (None, None))
        persist_cat2_trace(
            source_mode=mode_used,
            run_group_id=run_group_id,
            item_id=item_id,
            item_title=item_title,
            sub_task=sub_task,
            model_id=res.model_id,
            pattern=CAT2_RUNG_TO_PATTERN[res.rung_id],
            payload_text=payload_text,
            status=res.status,
            latency_ms=res.latency_ms,
            finops_dict=res.finops.model_dump(),
            raw_text=res.raw_markdown,
            structured_output=res.structured_draft,
            request_params_override=req_params,
            stop_reason=stop_reason,
            thinking_tokens=res.thinking_tokens,
            error_message=res.error_message,
            extra_metadata={
                "source_endpoint": "/api/cat2/run",
                "savings_vs_unbounded_pct": res.savings_vs_unbounded_pct,
            },
        )

    templated_sonnet = next(
        (r for r in results if r.rung_id == "sonnet_templated" and r.status == "ok"),
        None,
    )
    haiku_res = next(
        (r for r in results if r.rung_id == "haiku_templated" and r.status == "ok"),
        None,
    )
    haiku_batch = (
        compute_run_finops(
            "claude-haiku-5-5-batch",
            haiku_res.finops.input_tokens,
            haiku_res.finops.output_tokens,
        )
        if haiku_res
        else None
    )

    unb_share = unbounded_res.finops.output_cost_share_pct if unbounded_res else 80.0
    unb_out = unbounded_res.finops.output_tokens if unbounded_res else 4800
    tmp_out = templated_sonnet.finops.output_tokens if templated_sonnet else 1750
    tmp_save = templated_sonnet.savings_vs_unbounded_pct if templated_sonnet else 50.0
    h_save = haiku_res.savings_vs_unbounded_pct if haiku_res else 97.0

    callout = (
        f"5x Output Tax Exposed: Unbounded Sonnet 5.5 emitted {unb_out:,} output tokens "
        f"({unb_share:.1f}% of the entire invoice!). Adding Section Templates & Length Bounds cut Sonnet 5.5 output "
        f"to {tmp_out:,} tokens (-{tmp_save:.1f}% on the same frontier model), while Haiku 5.5 First-Draft routing drops "
        f"initial synthesis cost by -{h_save:.1f}% with selective HITL escalation."
    )

    return Cat2RunResponse(
        mode_used=mode_used,  # type: ignore[arg-type]
        preset_id=preset["id"] if preset else None,
        sub_task=sub_task,  # type: ignore[arg-type]
        input_char_count=len(payload_text),
        estimated_input_tokens=ref_input_tokens,
        results=results,
        haiku_batch_comparator=haiku_batch,
        output_tax_callout=callout,
    )


async def execute_cat2_section_regen(
    req: Cat2SectionRegenRequest,
    http_request: Request | None = None,
) -> Cat2SectionRegenResponse:
    presets = _preset_map()
    preset = presets.get(req.preset_id or "")

    if req.custom_input is not None and req.custom_input.strip():
        source_text = req.custom_input.strip()
    elif preset is not None:
        source_text = preset["payload"]
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either a valid preset_id or non-empty custom_input.",
        )

    sub_task = preset["sub_task"] if (preset and req.custom_input is None) else req.sub_task
    canonical_instruction = CAT2_REVIEWER_PRESETS[req.section_key]["instruction"]
    effective_instruction = req.reviewer_instruction.strip() or canonical_instruction
    item_id = preset["id"] if preset else "custom"
    item_title = preset["title"] if preset else "Custom Synthesis Bundle"

    if req.mode == "replay":
        is_exact_preset = preset is not None and source_text.strip() == preset["payload"].strip()
        if not is_exact_preset or effective_instruction != canonical_instruction:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Verified Replay ($0) serves the pre-captured reviewer instruction for each section. "
                    "Click a preset instruction chip or switch to Live API mode for custom edit prompts."
                ),
            )
        replays = load_cat2_replays()
        regen_map = (
            ((replays.get("section_regens") or {}).get(preset["id"]) or {}).get(req.section_key)
            or {}
        )
        r_data = regen_map.get(req.model_tier)
        if not r_data:
            raise HTTPException(
                status_code=404,
                detail=f"Replay trace missing for {preset['id']}/{req.section_key}/{req.model_tier}.",
            )
        model_used = r_data["model_id"]
        latency_ms = int(r_data["latency_ms"])
        in_tok = int(r_data["input_tokens"])
        out_tok = int(r_data["output_tokens"])
        updated_section = r_data["updated_section"]
        raw_text = json.dumps({req.section_key: updated_section}, indent=2)
        req_payload = build_section_regen_payload(
            source_text=source_text,
            section_key=req.section_key,
            current_section=req.current_section or r_data.get("prior_section") or {},
            reviewer_instruction=effective_instruction,
        )
        req_params = None
        stop_reason = "end_turn"
        mode_used = "replay"
    else:
        creds = credit_shield.resolve_live_credentials(
            http_request,
            need_anthropic=True,
            need_gemini=False,
        )
        assert creds.anthropic_api_key

        current_sec = req.current_section
        if current_sec is None and preset is not None:
            replays = load_cat2_replays()
            templated = (
                ((replays.get("presets") or {}).get(preset["id"]) or {})
                .get("rungs", {})
                .get("sonnet_templated", {})
                .get("structured_draft", {})
            )
            current_sec = templated.get(req.section_key, {})

        req_payload = build_section_regen_payload(
            source_text=source_text,
            section_key=req.section_key,
            current_section=current_sec or {},
            reviewer_instruction=effective_instruction,
        )
        raw = await run_cat2_structured_draft(
            req_payload,
            get_section_regen_system_prompt(sub_task, req.section_key),
            get_single_section_schema(req.section_key),
            req.model_tier,
            creds.anthropic_api_key,
            max_tokens=1800,
        )
        model_used = raw.model_id
        latency_ms = raw.latency_ms
        in_tok = raw.input_tokens
        out_tok = raw.output_tokens
        updated_section = raw.structured.get(req.section_key, raw.structured)
        raw_text = raw.raw_text
        req_params = raw.request_params
        stop_reason = raw.stop_reason
        if creds.uses_server_budget:
            fin_spent = compute_run_finops(model_used, in_tok, out_tok).total_cost_usd
            credit_shield.record_server_spend(fin_spent)
        mode_used = "live"

    comparison = build_hitl_cost_comparison(
        model_id=model_used,
        surgical_in_tokens=in_tok,
        surgical_out_tokens=out_tok,
        section_key=req.section_key,
    )

    persist_cat2_trace(
        source_mode=mode_used,
        run_group_id=f"regen-{uuid4()}",
        item_id=f"{item_id}__{req.section_key}",
        item_title=f"{item_title} · Section `{req.section_key}`",
        sub_task=sub_task,
        model_id=model_used,
        pattern=HITL_REGEN_PATTERN,
        payload_text=req_payload,
        status="ok",
        latency_ms=latency_ms,
        finops_dict=comparison.surgical_finops.model_dump(),
        raw_text=raw_text,
        structured_output={req.section_key: updated_section},
        section_key=req.section_key,
        request_params_override=req_params,
        stop_reason=stop_reason,
        extra_metadata={
            "source_endpoint": "/api/cat2/regenerate-section",
            "section_key": req.section_key,
            "reviewer_instruction": effective_instruction,
            "revision_savings_pct": comparison.revision_savings_pct,
        },
    )

    return Cat2SectionRegenResponse(
        mode_used=mode_used,  # type: ignore[arg-type]
        preset_id=preset["id"] if preset else None,
        section_key=req.section_key,
        model_used=model_used,
        latency_ms=latency_ms,
        updated_section=updated_section,
        finops_comparison=comparison,
    )
