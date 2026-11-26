"""Orchestrates the Category 2 four-rung drafting arena and single-section HITL regeneration.

Four rungs: Sonnet 5.5 and Haiku 5.5, each without the deck's improvement (unbounded long-form draft, free text) and
with it (section template with length caps, strict JSON schema). The golden replays are repeat 0 of the Category 2
experiment (scripts/build_cat2_golden_from_experiment.py); a rung whose experiment drafts do not exist yet replays as
"pending". The experiment summary (replays/cat2_quality_summary.json) is attached as `quality_portfolio`.
"""

from __future__ import annotations

import asyncio
import hashlib
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
from app.archetypes.cat2_drafting.quality_scoring import (
    LIVE_JUDGE_REASON,
    deterministic_quality_for_text,
    render_draft,
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
from app.core.measured_claims import fmt_pct, pct_cut, set_note
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
    Cat2QualityPortfolio,
    Cat2RunRequest,
    Cat2RunResponse,
    Cat2RungQuality,
    Cat2RungResult,
    Cat2SectionRegenRequest,
    Cat2SectionRegenResponse,
    HitlCostComparison,
)

CAT2_CATEGORY = "cat2_synthesis_drafting"
CAT2_RUNG_TO_PATTERN: dict[str, str] = {
    "sonnet_unbounded": "unbounded_longform_draft",
    "haiku_unbounded": "unbounded_longform_draft",
    "sonnet_templated": "section_templated_bounded",
    "haiku_templated": "section_templated_bounded",
}
RUNG_ORDER = ("sonnet_unbounded", "haiku_unbounded", "sonnet_templated", "haiku_templated")
UNBOUNDED_RUNGS = ("sonnet_unbounded", "haiku_unbounded")
MODEL_FOR_RUNG = {"sonnet_unbounded": "claude-sonnet-5-5", "haiku_unbounded": "claude-haiku-5-5",
                  "sonnet_templated": "claude-sonnet-5-5", "haiku_templated": "claude-haiku-5-5"}
# with-rung -> the without-rung on the same model
WITHOUT_FOR = {"sonnet_templated": "sonnet_unbounded", "haiku_templated": "haiku_unbounded"}
UNBOUNDED_MAX_TOKENS = 8000
TEMPLATE_MAX_TOKENS = 3000
HITL_REGEN_PATTERN = "hitl_section_regen"
SECTION_REGEN_MAX_TOKENS = 1800
TEMPLATED_RUNG_FOR_TIER = {"claude-sonnet-5-5": "sonnet_templated", "claude-haiku-5-5": "haiku_templated"}
CAT2_QUALITY_SUMMARY_FILE = "cat2_quality_summary.json"
REPLAY_PENDING_MESSAGE = "Run pending: the experiment drafts for this version have not been made yet, so there is nothing to replay."
REPLAY_GRADES_STALE_REASON = (
    "The stored grades are for a different version of this draft, so only the free checks are shown."
)
RUNG_LABEL = {
    "sonnet_unbounded": "Sonnet unbounded draft",
    "haiku_unbounded": "Haiku unbounded draft",
    "sonnet_templated": "Sonnet section template",
    "haiku_templated": "Haiku section template",
}
_RATE = {"claude-sonnet-5-5": "$2.00/M in · $10.00/M out", "claude-haiku-5-5": "$0.10/M in · $0.50/M out"}


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


def section_regen_request(
    *, sub_task: str, section_key: str, source_text: str, current_section: Any, reviewer_instruction: str
) -> dict[str, Any]:
    """The exact single-section regeneration request the app sends (live path and capture harness)."""
    return {
        "system": get_section_regen_system_prompt(sub_task, section_key),
        "payload": build_section_regen_payload(source_text=source_text, section_key=section_key,
                                               current_section=current_section, reviewer_instruction=reviewer_instruction),
        "schema": get_single_section_schema(section_key),
        "max_tokens": SECTION_REGEN_MAX_TOKENS,
    }


def _tier_of(model_id: str) -> str:
    return "claude-sonnet-5-5" if "sonnet" in model_id else "claude-haiku-5-5"


def templated_draft_for(replays: dict[str, Any], preset_id: str | None, model_tier: str) -> dict[str, Any] | None:
    """The current repeat-0 templated draft of this preset on this model (golden replays), or None."""
    if not preset_id:
        return None
    rung = TEMPLATED_RUNG_FOR_TIER.get(_tier_of(model_tier))
    return (((replays.get("presets") or {}).get(preset_id) or {}).get("rungs") or {}).get(rung) or None


def _cat2_rung_metadata(rung_id: str) -> tuple[str, str, list[str]]:
    """Number-free fallback copy; `_apply_measured_claims` replaces the result-dependent sentences."""
    model = MODEL_FOR_RUNG[rung_id]
    name = "Sonnet 5.5" if "sonnet" in model else "Haiku 5.5"
    thinking = "thinking between tools" if "sonnet" in model else "thinking disabled"
    if rung_id in UNBOUNDED_RUNGS:
        return (
            f"Without · {name} unbounded long-form draft",
            f"Without the Improvement · {name.split()[0]}",
            [
                f"Asks {name} ({_RATE[model]}, {thinking}) for an exhaustive long-form draft in free text "
                f"(max_tokens {UNBOUNDED_MAX_TOKENS:,}).",
                # replaced with the measured output tokens and cost share by _apply_measured_claims
                "Output tokens are priced at 5x input, so a long draft's output drives most of its cost.",
            ],
        )
    return (
        f"With · {name} section template with length caps",
        f"With the Improvement · {name.split()[0]}",
        [
            f"Same {name} model ({_RATE[model]}, {thinking}), constrained to a 4-section JSON schema with word caps "
            f"(max_tokens {TEMPLATE_MAX_TOKENS:,}); action-plan owners and dates only when the source states them.",
            # replaced with the measured output and cost cut by _apply_measured_claims
            "Capping each section bounds output tokens and enables single-section HITL locking & regeneration.",
        ],
    )


def _apply_measured_claims(results: list[Cat2RungResult]) -> None:
    """Rewrite result-dependent rung notes with numbers measured on this run (with vs without on the same model)."""
    ok = {r.rung_id: r for r in results if r.status == "ok"}
    for rid in UNBOUNDED_RUNGS:
        r = ok.get(rid)
        if r:
            set_note(r, 1, f"Writes {r.finops.output_tokens:,} output tokens on this document; output is "
                           f"{fmt_pct(r.finops.output_cost_share_pct)} of its cost.")
    for rid, without_id in WITHOUT_FOR.items():
        r, w = ok.get(rid), ok.get(without_id)
        if not r:
            continue
        if w:
            out_cut = pct_cut(w.finops.output_tokens, r.finops.output_tokens)
            cost_cut = pct_cut(w.finops.total_cost_usd, r.finops.total_cost_usd)
            if out_cut is not None and cost_cut is not None:
                set_note(r, 1, f"Writes {r.finops.output_tokens:,} output tokens vs {w.finops.output_tokens:,} for the unbounded draft "
                               f"on the same model ({fmt_pct(out_cut)} fewer), cutting cost {fmt_pct(cost_cut)}.")
                continue
        set_note(r, 1, f"Writes {r.finops.output_tokens:,} output tokens (${r.finops.total_cost_usd:.4f} for this draft).")


# --------------------------------------------------------------------------------------------------
# Draft quality (blind-judge summary in replay mode; free deterministic checks in live mode)
# --------------------------------------------------------------------------------------------------


def load_cat2_quality_summary() -> dict[str, Any] | None:
    """replays/cat2_quality_summary.json (scripts/build_cat2_golden_from_experiment.py); None if absent or unreadable."""
    path = Path(get_settings().replays_dir) / CAT2_QUALITY_SUMMARY_FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    return data if isinstance(data, dict) else None


def load_cat2_quality_portfolio(summary: dict[str, Any] | None = None) -> Cat2QualityPortfolio | None:
    summary = summary if summary is not None else load_cat2_quality_summary()
    if not summary:
        return None
    try:
        return Cat2QualityPortfolio.model_validate(summary)
    except ValueError:
        return None


def build_cat2_rung_quality(
    *,
    result: Cat2RungResult,
    payload_text: str,
    preset_id: str | None,
    mode: str,
    summary: dict[str, Any] | None,
) -> Cat2RungQuality | None:
    """Replay: the judged repeat-0 draft for this preset x rung (only if the draft text is the one that was graded).
    Live (or stale replay): fact coverage + unsupported numbers on the fresh draft, judge fields None."""
    if result.status != "ok":
        return None
    text = render_draft({"structured_draft": result.structured_draft, "raw_markdown": result.raw_markdown})
    if not text.strip():
        return None
    reason = LIVE_JUDGE_REASON
    if mode == "replay" and summary and preset_id:
        cell = (((summary.get("presets") or {}).get(preset_id) or {}).get("rungs") or {}).get(result.rung_id)
        if cell:
            if cell.get("text_sha256") == hashlib.sha256(text.encode("utf-8")).hexdigest():
                try:
                    return Cat2RungQuality.model_validate(
                        {
                            **cell,
                            "source": "replay_judged",
                            "preset_id": preset_id,
                            "keys_version": summary.get("keys_version"),
                            "judge_model": summary.get("judge_model"),
                            "passes": summary.get("passes_per_draft"),
                        }
                    )
                except ValueError:
                    pass
            reason = REPLAY_GRADES_STALE_REASON
    try:
        det = deterministic_quality_for_text(text, payload_text, preset_id)
    except (OSError, ValueError, KeyError):
        return None
    facts = det["facts"] or {}
    return Cat2RungQuality.model_validate(
        {
            "source": "live_deterministic",
            "preset_id": preset_id,
            "keys_version": facts.get("keys_version"),
            "core_facts": facts.get("core_facts"),
            "detail_facts": facts.get("detail_facts"),
            "missed_facts": facts.get("missed_facts") or [],
            "numbers": det["numbers"],
            "judge_unavailable_reason": reason,
        }
    )


def _g(x: float) -> str:
    return f"{x:.1f}"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _judged(r: Cat2RungResult | None) -> Cat2RungQuality | None:
    q = r.quality if r else None
    return q if q is not None and q.rubric and q.serious_errors is not None else None


def _cell(portfolio: Cat2QualityPortfolio | None, rung_id: str):
    return next((c for c in (portfolio.cells if portfolio else []) if c.rung_id == rung_id), None)


def _apply_quality_claims(results: list[Cat2RungResult], portfolio: Cat2QualityPortfolio | None) -> None:
    """Note 3: measured quality of this draft (replay) or, when this run is not graded, of the version's experiment
    drafts. No note is added when nothing was measured."""
    for r in results:
        if r.status != "ok":
            continue
        q = _judged(r)
        if q is not None:
            text = (f"Measured quality of this draft (blind grading, 1–5): accuracy {_g(q.rubric['factual_accuracy'].mean)}, "
                    f"coverage {_g(q.rubric['coverage'].mean)}, {_plural(q.serious_errors, 'serious error')}")
            if r.rung_id in WITHOUT_FOR:
                for h in q.head_to_head or []:
                    decided = [o for o in h.results if o.winner is not None]
                    if decided:
                        text += (f"; preferred over the unbounded draft in {sum(1 for o in decided if o.winner == r.rung_id)} of "
                                 f"{len(decided)} head-to-head comparisons")
            set_note(r, 2, text + ".")
            continue
        c = _cell(portfolio, r.rung_id)
        if c is None or c.status == "pending" or not c.rubric or c.rubric.get("factual_accuracy") is None:
            continue
        set_note(r, 2, f"Quality is not graded on this run; the version's {c.drafts} experiment drafts averaged accuracy "
                       f"{c.rubric['factual_accuracy']:.2f} and coverage {c.rubric['coverage']:.2f} (1–5), "
                       f"{c.serious_per_draft:.2f} serious errors per draft.")


def _quality_callout(portfolio: Cat2QualityPortfolio | None) -> str:
    if portfolio is None:
        return " Draft quality is not graded on this run."
    h = portfolio.head_to_head
    if h.status == "pending" or h.all is None:
        return " The template-vs-unbounded quality comparison is pending (the unbounded drafts have not been made yet)."
    o = h.all.overall
    return (f" Graded blind on the same document, model and repeat, the template draft was preferred in {o.template_wins} "
            f"and the unbounded draft in {o.unbounded_wins} of {h.all.calls} comparisons ({o.ties} ties).")


def _pending_result(rung_id: str) -> Cat2RungResult:
    res = build_cat2_rung_result(rung_id=rung_id, model_id=MODEL_FOR_RUNG[rung_id], provider="Anthropic", latency_ms=0,
                                 input_tokens=0, output_tokens=0, status="pending", error_message=REPLAY_PENDING_MESSAGE)
    res.architectural_notes = res.architectural_notes[:1] + [REPLAY_PENDING_MESSAGE]
    return res


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
                "max_tokens": UNBOUNDED_MAX_TOKENS,
                "endpoint": "messages.create",
                "thinking": thinking_default,
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
                "max_tokens": SECTION_REGEN_MAX_TOKENS,
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
    preset_id: str | None = None,
    replays: dict[str, Any] | None = None,
) -> HitlCostComparison:
    """A single-section regeneration vs a full templated draft of the same document on the same model.

    The full draft is the current repeat-0 templated draft of this preset and model (golden replays); for a custom
    input it is the mean of that model's templated drafts over the presets. `naive_full_reprompt_finops` keeps its
    field name for API compatibility; it holds that full-draft cost."""
    replays = replays if replays is not None else load_cat2_replays()
    tier = _tier_of(model_id)
    surgical = compute_run_finops(model_id, surgical_in_tokens, surgical_out_tokens)
    own = templated_draft_for(replays, preset_id, tier)
    if own:
        f_in, f_out, what = int(own["input_tokens"]), int(own["output_tokens"]), "this document's"
    else:
        rung = TEMPLATED_RUNG_FOR_TIER[tier]
        drafts = [((p.get("rungs") or {}).get(rung)) for p in (replays.get("presets") or {}).values()]
        drafts = [d for d in drafts if d]
        if drafts:
            f_in = round(sum(int(d["input_tokens"]) for d in drafts) / len(drafts))
            f_out = round(sum(int(d["output_tokens"]) for d in drafts) / len(drafts))
            what = f"the mean ({len(drafts)} documents)"
        else:
            f_in, f_out, what = surgical_in_tokens, surgical_out_tokens, "no stored"
    full = compute_run_finops(tier, f_in, f_out)
    savings_pct = (
        round(((full.total_cost_usd - surgical.total_cost_usd) / full.total_cost_usd) * 100, 2)
        if full.total_cost_usd > 0
        else 0.0
    )
    tokens_avoided = max(0, (full.input_tokens + full.output_tokens) - (surgical.input_tokens + surgical.output_tokens))
    return HitlCostComparison(
        surgical_finops=surgical,
        naive_full_reprompt_finops=full,
        revision_savings_pct=savings_pct,
        tokens_avoided=tokens_avoided,
        explanation=(
            f"Regenerating only `{section_key}` on {surgical.model_label} wrote {surgical.output_tokens:,} output tokens "
            f"(${surgical.cost_per_1k_usd:.2f}/1k edits) vs {what} full {full.model_label} template draft "
            f"({full.input_tokens:,} in / {full.output_tokens:,} out tokens, ${full.cost_per_1k_usd:.2f}/1k): "
            f"{savings_pct:.1f}% less."
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
    replay_meta: dict[str, dict[str, Any]] = {}
    rungs = [r for r in RUNG_ORDER if r in req.rungs]

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
        for rung_id in rungs:
            r_data = (preset_trace.get("rungs") or {}).get(rung_id)
            if not r_data:
                results.append(_pending_result(rung_id))
                continue
            trace_extras[rung_id] = (r_data.get("request_params"), r_data.get("stop_reason"))
            replay_meta[rung_id] = (preset_trace.get("provenance") or {}).get(rung_id) or {}
            res = build_cat2_rung_result(
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
            res.stop_reason = r_data.get("stop_reason")
            results.append(res)
        mode_used = "replay"
    else:
        creds = credit_shield.resolve_live_credentials(
            http_request,
            need_anthropic=True,
        )
        assert creds.anthropic_api_key

        async def _run_one(rung_id: str) -> Cat2RungResult:
            model_tier = MODEL_FOR_RUNG[rung_id]
            try:
                if rung_id in UNBOUNDED_RUNGS:
                    raw = await run_cat2_unbounded_sonnet(
                        payload_text,
                        get_unbounded_draft_system_prompt(sub_task),
                        creds.anthropic_api_key or "",
                        max_tokens=UNBOUNDED_MAX_TOKENS,
                        model_tier=model_tier,
                    )
                else:
                    raw = await run_cat2_structured_draft(
                        payload_text,
                        get_templated_draft_system_prompt(sub_task),
                        STRUCTURED_DRAFT_JSON_SCHEMA,
                        model_tier,
                        creds.anthropic_api_key or "",
                        max_tokens=TEMPLATE_MAX_TOKENS,
                    )
                trace_extras[rung_id] = (raw.request_params, raw.stop_reason)
                res = build_cat2_rung_result(
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
                res.stop_reason = raw.stop_reason
                return res
            except Exception as exc:
                return build_cat2_rung_result(
                    rung_id=rung_id,
                    model_id=model_tier,
                    provider="Anthropic",
                    latency_ms=0,
                    input_tokens=0,
                    output_tokens=0,
                    status="error",
                    error_message=str(exc)[:300],
                )

        results = list(await asyncio.gather(*(_run_one(r) for r in rungs)))
        if creds.uses_server_budget:
            total_spend = sum(r.finops.total_cost_usd for r in results if r.status == "ok")
            credit_shield.record_server_spend(total_spend)
        mode_used = "live"

    ok = {r.rung_id: r for r in results if r.status == "ok"}
    # savings: each rung vs the unbounded draft on the same model (0 when that rung did not run)
    for res in results:
        w = ok.get(WITHOUT_FOR.get(res.rung_id, ""))
        if res.status == "ok" and w and w.finops.total_cost_usd > 0:
            res.savings_vs_unbounded_pct = round(((w.finops.total_cost_usd - res.finops.total_cost_usd) / w.finops.total_cost_usd) * 100, 2)
    _apply_measured_claims(results)

    quality_summary = load_cat2_quality_summary()
    portfolio = load_cat2_quality_portfolio(quality_summary)
    quality_preset_id = (
        preset["id"] if preset is not None and payload_text.strip() == preset["payload"].strip() else None
    )
    for res in results:
        res.quality = build_cat2_rung_quality(
            result=res,
            payload_text=payload_text,
            preset_id=quality_preset_id,
            mode=mode_used,
            summary=quality_summary,
        )
    _apply_quality_claims(results, portfolio)

    # Persist partitioned traces (category / use_case / model / pattern); pending replays have nothing to record
    for res in results:
        if res.status == "pending":
            continue
        req_params, stop_reason = trace_extras.get(res.rung_id, (None, None))
        meta: dict[str, Any] = {
            "source_endpoint": "/api/cat2/run",
            "rung_id": res.rung_id,
            "savings_vs_unbounded_pct": res.savings_vs_unbounded_pct,
        }
        if replay_meta.get(res.rung_id):
            meta["experiment_draft_id"] = replay_meta[res.rung_id].get("draft_id")
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
            extra_metadata=meta,
        )

    haiku_res = ok.get("haiku_templated")
    haiku_batch = (
        compute_run_finops("claude-haiku-5-5-batch", haiku_res.finops.input_tokens, haiku_res.finops.output_tokens)
        if haiku_res
        else None
    )

    parts = []
    for rid, without_id in WITHOUT_FOR.items():
        r, w = ok.get(rid), ok.get(without_id)
        name = "Sonnet 5.5" if rid.startswith("sonnet") else "Haiku 5.5"
        if r and w:
            parts.append(f"on {name} the section template writes {r.finops.output_tokens:,} output tokens vs {w.finops.output_tokens:,} "
                         f"for the unbounded draft ({fmt_pct(r.savings_vs_unbounded_pct)} lower cost)")
        elif r:
            parts.append(f"on {name} the section template writes {r.finops.output_tokens:,} output tokens "
                         f"(the unbounded draft {'is pending' if any(x.rung_id == without_id and x.status == 'pending' for x in results) else 'was not run'})")
    callout = ("Output tokens cost 5x input on both models: " + "; ".join(parts) + "." if parts
               else "Output tokens cost 5x input on both models.") + _quality_callout(portfolio)

    return Cat2RunResponse(
        mode_used=mode_used,  # type: ignore[arg-type]
        preset_id=preset["id"] if preset else None,
        sub_task=sub_task,  # type: ignore[arg-type]
        input_char_count=len(payload_text),
        estimated_input_tokens=next((r.finops.input_tokens for r in results if r.status == "ok" and r.finops.input_tokens > 0),
                                    max(1, round(len(payload_text) / 2.15))),
        results=results,
        haiku_batch_comparator=haiku_batch,
        output_tax_callout=callout,
        quality_portfolio=portfolio,
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
        raw_text = r_data.get("raw_text") or json.dumps({req.section_key: updated_section}, indent=2)
        req_payload = r_data.get("request_payload") or build_section_regen_payload(
            source_text=source_text,
            section_key=req.section_key,
            current_section=r_data.get("prior_section") or {},
            reviewer_instruction=effective_instruction,
        )
        req_params = r_data.get("request_params")
        stop_reason = r_data.get("stop_reason")
        thinking_tok = int(r_data.get("thinking_tokens") or 0)
        mode_used = "replay"
    else:
        creds = credit_shield.resolve_live_credentials(
            http_request,
            need_anthropic=True,
        )
        assert creds.anthropic_api_key

        current_sec = req.current_section
        if current_sec is None and preset is not None:
            base = templated_draft_for(load_cat2_replays(), preset["id"], req.model_tier) or {}
            current_sec = (base.get("structured_draft") or {}).get(req.section_key, {})

        rq = section_regen_request(sub_task=sub_task, section_key=req.section_key, source_text=source_text,
                                   current_section=current_sec or {}, reviewer_instruction=effective_instruction)
        req_payload = rq["payload"]
        raw = await run_cat2_structured_draft(
            req_payload,
            rq["system"],
            rq["schema"],
            req.model_tier,
            creds.anthropic_api_key,
            max_tokens=rq["max_tokens"],
        )
        model_used = raw.model_id
        latency_ms = raw.latency_ms
        in_tok = raw.input_tokens
        out_tok = raw.output_tokens
        updated_section = raw.structured.get(req.section_key, raw.structured)
        raw_text = raw.raw_text
        req_params = raw.request_params
        stop_reason = raw.stop_reason
        thinking_tok = int(raw.thinking_tokens or 0)
        if creds.uses_server_budget:
            fin_spent = compute_run_finops(model_used, in_tok, out_tok).total_cost_usd
            credit_shield.record_server_spend(fin_spent)
        mode_used = "live"

    comparison = build_hitl_cost_comparison(
        model_id=model_used,
        surgical_in_tokens=in_tok,
        surgical_out_tokens=out_tok,
        section_key=req.section_key,
        preset_id=preset["id"] if (preset is not None and source_text.strip() == preset["payload"].strip()) else None,
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
        thinking_tokens=thinking_tok,
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
