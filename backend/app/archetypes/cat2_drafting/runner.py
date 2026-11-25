"""Orchestrates Category 2 3-Rung Synthesis Arena & Surgical HITL Section Regeneration."""

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
    "sonnet_templated": "section_templated_bounded",
    "haiku_templated": "tier_routed_template_draft",
}
HITL_REGEN_PATTERN = "hitl_section_regen"
CAT2_QUALITY_SUMMARY_FILE = "cat2_quality_summary.json"
REPLAY_GRADES_STALE_REASON = (
    "The stored grades are for a different version of this draft, so only the free checks are shown."
)
RUNG_LABEL = {
    "sonnet_unbounded": "unbounded",
    "sonnet_templated": "Sonnet template",
    "haiku_templated": "Haiku template",
}


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
                # replaced with the measured output tokens and cost share by _apply_measured_claims
                "At 5x output token pricing, unbounded output tokens drive most of the inference bill.",
            ],
        )
    if rung_id == "sonnet_templated":
        return (
            "Rung 2 · Sonnet 5.5 + Bounded Section Template",
            "Calibrated Lever: Section-Bounded Schema",
            [
                "Same Sonnet 5.5 model, constrained to a 4-section JSON schema with strict word caps.",
                # replaced with the measured output and cost cut by _apply_measured_claims
                "Caps output tokens and unit cost while enabling single-section HITL locking & regen.",
            ],
        )
    return (
        "Rung 3 · Haiku 5.5 First-Draft Template",
        "Tier-Routed Draft",  # measured saving appended by _apply_measured_claims
        [
            "Runs the exact same 4-section bounded schema on Haiku 5.5 ($0.10/M in · $0.50/M out).",
            # replaced with the measured draft cost by _apply_measured_claims
            "Drafts all four sections at a fraction of Sonnet cost; a reviewer can regenerate any single section on Sonnet 5.5.",
        ],
    )


def _apply_measured_claims(results: list[Cat2RungResult]) -> None:
    """Rewrite result-dependent rung badges/notes with numbers measured on this run."""
    ok = {r.rung_id: r for r in results if r.status == "ok"}
    unb, tmpl, haiku = ok.get("sonnet_unbounded"), ok.get("sonnet_templated"), ok.get("haiku_templated")
    if unb:
        set_note(
            unb,
            1,
            f"At 5x output token pricing, {unb.finops.output_tokens:,} unbounded output tokens drive "
            f"{fmt_pct(unb.finops.output_cost_share_pct)} of this draft's inference bill.",
        )
    if tmpl and unb:
        out_cut = pct_cut(unb.finops.output_tokens, tmpl.finops.output_tokens)
        if out_cut is not None:
            set_note(
                tmpl,
                1,
                f"Cuts output tokens {fmt_pct(out_cut)} vs the unbounded draft "
                f"({unb.finops.output_tokens:,} → {tmpl.finops.output_tokens:,}) and unit cost "
                f"{fmt_pct(tmpl.savings_vs_unbounded_pct)}, while enabling single-section HITL locking & regen.",
            )
    if haiku:
        if unb:
            haiku.badge_text = f"Tier-Routed Draft (-{fmt_pct(haiku.savings_vs_unbounded_pct)} Cost)"
        set_note(
            haiku,
            1,
            f"Drafts all four sections for ${haiku.finops.total_cost_usd:.4f}; a reviewer can regenerate "
            "any single section on Sonnet 5.5.",
        )


# --------------------------------------------------------------------------------------------------
# Draft quality (blind-judge summary in replay mode; free deterministic checks in live mode)
# --------------------------------------------------------------------------------------------------


def load_cat2_quality_summary() -> dict[str, Any] | None:
    """replays/cat2_quality_summary.json (scripts/build_cat2_quality_summary.py); None if absent or unreadable."""
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
    """Replay: the judged cell for this preset x rung (only if the draft text is the one that was graded).
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


def _doc_record(q: Cat2RungQuality, opponent: str | None = None) -> tuple[int, int]:
    """(wins, comparisons) on this document, against one opponent or all."""
    wins = total = 0
    for h in q.head_to_head or []:
        if opponent and h.opponent != opponent:
            continue
        for o in h.results:
            if o.winner is None:
                continue
            total += 1
            wins += o.winner not in (h.opponent, "tie")
    return wins, total


def _judged(r: Cat2RungResult | None) -> Cat2RungQuality | None:
    q = r.quality if r else None
    return q if q is not None and q.rubric and q.serious_errors is not None else None


def _apply_quality_claims(results: list[Cat2RungResult], portfolio: Cat2QualityPortfolio | None) -> None:
    """Note 3 (and 4 for templated rungs): measured quality on this document, or the pooled stored-draft
    results when this run was not graded. No note is added when nothing was measured."""
    ok = {r.rung_id: r for r in results if r.status == "ok"}
    unb_q = _judged(ok.get("sonnet_unbounded"))
    pooled = {p.rung_id: p for p in (portfolio.rungs if portfolio else [])}
    n_docs = len(portfolio.documents) if portfolio else 0
    for rid, r in ok.items():
        q = _judged(r)
        if q is not None:
            acc, cov = q.rubric["factual_accuracy"].mean, q.rubric["coverage"].mean
            text = (
                f"Measured quality on this document (blind grading, 1–5): accuracy {_g(acc)}, coverage {_g(cov)}, "
                f"{_plural(q.serious_errors, 'serious error')}"
            )
            if rid == "sonnet_unbounded":
                w, t = _doc_record(q)
                if t:
                    text += f"; preferred over the templated drafts in {w} of {t} head-to-head comparisons"
            else:
                if unb_q is not None:
                    text += (
                        f" (unbounded: accuracy {_g(unb_q.rubric['factual_accuracy'].mean)}, coverage "
                        f"{_g(unb_q.rubric['coverage'].mean)}, {unb_q.serious_errors})"
                    )
                w, t = _doc_record(q, "sonnet_unbounded")
                if t:
                    text += f"; preferred over the unbounded draft in {w} of {t} head-to-head comparisons"
            set_note(r, 2, text + ".")
            if q.action_items and q.action_items.total:
                ai = q.action_items
                set_note(
                    r,
                    3,
                    "The template requires an owner and a time window for every action item; on this document the "
                    f"grader flagged an owner or deadline the source does not support in {ai.flagged} of {ai.total} "
                    f"action items ({ai.flagged_serious} serious).",
                )
            continue
        p = pooled.get(rid)
        if p is None or not n_docs:
            continue
        acc, cov = p.rubric["factual_accuracy"].mean, p.rubric["coverage"].mean
        if acc is None or cov is None:
            continue
        text = (
            f"Quality is not graded on this run; on the {n_docs} stored documents this version averaged accuracy "
            f"{acc:.2f} and coverage {cov:.2f} (1–5) with {_plural(p.serious_errors, 'serious error')} in total"
        )
        if rid != "sonnet_unbounded" and "sonnet_unbounded" in p.head_to_head:
            rec = p.head_to_head["sonnet_unbounded"]
            text += f", and was preferred over the unbounded draft in {rec.wins} of {rec.wins + rec.losses + rec.ties} comparisons"
        set_note(r, 2, text + ".")
        if p.action_items and p.action_items.total:
            set_note(
                r,
                3,
                "The template requires an owner and a time window for every action item; on the stored documents "
                f"the grader flagged an owner or deadline the source does not support in {p.action_items.flagged} "
                f"of {p.action_items.total} action items.",
            )


def _quality_callout(results: list[Cat2RungResult], portfolio: Cat2QualityPortfolio | None) -> str:
    ok = {r.rung_id: r for r in results if r.status == "ok"}
    unb_q = _judged(ok.get("sonnet_unbounded"))
    templ = [(rid, _judged(ok.get(rid))) for rid in ("sonnet_templated", "haiku_templated")]
    templ = [(rid, q) for rid, q in templ if q is not None]
    if unb_q is not None and templ:
        wins = sum(_doc_record(unb_q, rid)[0] for rid, _ in templ)
        total = sum(_doc_record(unb_q, rid)[1] for rid, _ in templ)
        errs = " and ".join(f"{q.serious_errors} ({RUNG_LABEL[rid]})" for rid, q in templ)
        return (
            f" The savings are not free on this document: the blind grader preferred the unbounded draft in {wins} of "
            f"{total} head-to-head comparisons, and the templated drafts had {errs} serious errors vs "
            f"{unb_q.serious_errors} for the unbounded draft."
        )
    if portfolio:
        pooled = {p.rung_id: p for p in portfolio.rungs}
        unb = pooled.get("sonnet_unbounded")
        tp = [(rid, pooled[rid]) for rid in ("sonnet_templated", "haiku_templated") if rid in pooled and rid in ok]
        if unb and tp:
            wins = sum(unb.head_to_head[rid].wins for rid, _ in tp if rid in unb.head_to_head)
            total = sum(
                unb.head_to_head[rid].wins + unb.head_to_head[rid].losses + unb.head_to_head[rid].ties
                for rid, _ in tp
                if rid in unb.head_to_head
            )
            errs = " and ".join(f"{p.serious_errors} ({RUNG_LABEL[rid]})" for rid, p in tp)
            return (
                f" Quality is not graded on this run; on the {len(portfolio.documents)} stored documents the blind "
                f"grader preferred the unbounded draft in {wins} of {total} comparisons, and the templated drafts had "
                f"{errs} serious errors vs {unb.serious_errors}."
            )
    return " Draft quality is not graded on this run."


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
                    res = build_cat2_rung_result(
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
                    res.stop_reason = raw.stop_reason
                    return res

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
        f"5x Output Tax: Unbounded Sonnet 5.5 emitted {unb_out:,} output tokens "
        f"({unb_share:.1f}% of its draft's bill). Section templates & length bounds cut Sonnet 5.5 output "
        f"to {tmp_out:,} tokens (-{tmp_save:.1f}% cost on the same model), and the same template on Haiku 5.5 cuts "
        f"draft cost by -{h_save:.1f}%." + _quality_callout(results, portfolio)
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
