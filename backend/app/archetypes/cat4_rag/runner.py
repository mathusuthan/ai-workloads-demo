"""Orchestrates the Category 4 deal-room comparison (without vs with the deck improvement) and ad-hoc queries.

Without: the whole corpus as uncached plain text, no citations (Sonnet answers). With: hybrid retrieval paired with
context caching — Haiku picks 5 clauses from the cached corpus, Sonnet answers over them with citations (`paired.py`).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4
from fastapi import HTTPException, Request

from app.archetypes.cat4_rag.answer_formats import rung_answer_format, rung_synthesis_system_prompt
from app.archetypes.cat4_rag.paired import (
    PAIRED_RUNG,
    build_rerank_content,
    get_full_corpus_reranker_system_prompt,
    picked_funnel,
    select_picked_chunks,
)
from app.archetypes.cat4_rag.schemas import RERANK_JSON_SCHEMA
from app.archetypes.cat4_rag.scope import scoped_question
from app.config import get_settings
from app.core.anthropic_service import (
    run_cat4_haiku_reranker,
    run_cat4_rag_synthesis,
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
from app.data.cat4_fixtures import (
    CAT4_PRESETS,
    DEAL_ROOM_PROFILE,
    hydrate_deal_room_index,
)
from app.models import (
    Cat4AdhocQueryRequest,
    Cat4AdhocQueryResponse,
    Cat4AnswerSegment,
    Cat4PortfolioCell,
    Cat4QualityPortfolio,
    Cat4CitationSpan,
    Cat4QueryResult,
    Cat4RetrievalChunkTrace,
    Cat4RunRequest,
    Cat4RunResponse,
    Cat4RungId,
    Cat4RungSummary,
    FinOpsBreakdown,
)

CAT4_CATEGORY = "cat4_multidoc_rag"
CAT4_USE_CASE = "supplier_msa_due_diligence"
CAT4_RUNG_TO_PATTERN: dict[str, str] = {
    "naive_full_corpus": "uncached_full_corpus_stuffing",
    PAIRED_RUNG: "cached_corpus_haiku_pick_citations",
}
RERANKER_PATTERN = "haiku_cached_corpus_clause_picker"
# Synthesis output cap (the app and the rerun both use 4,096; the live path raises on truncation). The reranker
# keeps 800.
CAT4_SYNTH_MAX_TOKENS = 4096
CAT4_RERANK_MAX_TOKENS = 800


def _preset_map() -> dict[str, dict[str, Any]]:
    return {p["id"]: p for p in CAT4_PRESETS}


def load_cat4_replays() -> dict[str, Any]:
    replays_file = Path(get_settings().replays_dir) / "cat4_golden_replays.json"
    if not replays_file.is_file():
        return {"presets": {}}
    return json.loads(replays_file.read_text(encoding="utf-8"))


def _rung_metadata(rung_id: str) -> tuple[str, str, str | None, list[str]]:
    if rung_id == "naive_full_corpus":
        return (
            "1. Without: Full Corpus, No Cache, No Citations",
            "Without the improvement",
            None,
            [
                # replaced with the measured prompt size by _apply_measured_claims
                "Sends all 7 Deal-Room documents as plain uncached user text on every query ($2.00/M input).",
                "Requests no citations — a reviewer has to search the 7 agreements to check each claim.",
                # replaced with this audit's measured answer quality by _apply_measured_claims
                "Answer quality for this audit is scored against the answer key in the results panel.",
            ],
        )
    return (
        "2. With: Retrieval Paired with Caching + Citations",
        "With the improvement",  # measured share of corpus not sent to Sonnet added by _apply_measured_claims
        "claude-haiku-5-5",
        [
            # replaced with the measured cached block size by _apply_measured_claims
            "Haiku 5.5 reads all 28 deal-room clauses from one cached block (the first question writes it, later "
            "questions read it) and picks the 5 it judges most relevant; Sonnet 5.5 answers over those 5 with native citations.",
            # replaced with the measured single-query saving by _apply_measured_claims
            "Haiku's spend, including the cache write, is included in this version's cost.",
            # replaced with this audit's measured answer quality by _apply_measured_claims
            "The answering model sees only the picked clauses, so a clause Haiku does not pick can't be cited or used.",
            "Because it sees only the picked clauses, its answer prompt tells it to say when a term is not in the "
            "text provided.",
        ],
    )


def build_uncached_corpus_text(hydrated_docs: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"=== {d['block_title']} ({d['effective_date']}) ===\n{d['full_text']}"
        for d in hydrated_docs
    )


def build_rung2_doc_blocks(hydrated_docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "doc_id": d["doc_id"],
            "doc_char_offset": 0,
            "clause_ref": "",
            "block_title": d["block_title"],
            "block_context": d["block_context"],
            "data": d["full_text"],
        }
        for d in hydrated_docs
    ]


def build_rung3_chunk_blocks(selected_chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "doc_id": ch["doc_id"],
            "doc_char_offset": int(ch["doc_char_start"]),
            "clause_ref": ch["clause_ref"],
            "block_title": f"{ch['chunk_id']} :: {ch['doc_code']} · {ch['clause_ref']}",
            "block_context": (
                f"{ch['doc_type']} — {ch['section_heading']} "
                f"(Excerpt from {ch['doc_id']} {ch['doc_title']})"
            ),
            "data": ch["full_block_text"],
        }
        for ch in selected_chunks
    ]


def _resolve_clause_ref_for_span(
    doc_by_id: dict[str, dict[str, Any]],
    doc_id: str,
    start_char: int,
    end_char: int,
) -> str:
    doc = doc_by_id.get(doc_id)
    if not doc:
        return ""
    for ch in doc["chunks"]:
        if start_char < ch["doc_char_end"] and end_char >= ch["doc_char_start"]:
            return str(ch["clause_ref"])
    return str(doc["chunks"][0]["clause_ref"]) if doc.get("chunks") else ""


def _enrich_citations(
    raw_citations: list[dict[str, Any]],
    doc_by_id: dict[str, dict[str, Any]],
) -> list[Cat4CitationSpan]:
    out: list[Cat4CitationSpan] = []
    for c in raw_citations:
        doc_id = str(c.get("doc_id") or "")
        s = int(c.get("start_char_index") or 0)
        e = int(c.get("end_char_index") or s)
        clause_ref = str(c.get("clause_ref") or "").strip()
        if not clause_ref:
            clause_ref = _resolve_clause_ref_for_span(doc_by_id, doc_id, s, e)
        out.append(
            Cat4CitationSpan(
                cite_number=int(c["cite_number"]),
                doc_id=doc_id,
                document_title=str(c.get("document_title") or ""),
                clause_ref=clause_ref,
                cited_text=str(c.get("cited_text") or ""),
                start_char_index=s,
                end_char_index=e,
            )
        )
    return out


def _cold_warm(fin: FinOpsBreakdown | None, q_idx: int) -> tuple[float, float]:
    """(cold, warm) for one call: a call with a cached prefix writes it on the audit's first question and reads it
    after (cold), or reads it on every question (warm). A call without cache tokens costs the same in both views."""
    if fin is None:
        return 0.0, 0.0
    prefix = fin.cache_creation_tokens + fin.cache_read_tokens
    if prefix <= 0:
        return fin.total_cost_usd, fin.total_cost_usd
    cold = compute_run_finops(
        model_id=fin.model_id,
        input_tokens=fin.input_tokens,
        output_tokens=fin.output_tokens,
        cache_creation_tokens=prefix if q_idx == 0 else 0,
        cache_read_tokens=0 if q_idx == 0 else prefix,
    )
    warm = compute_run_finops(
        model_id=fin.model_id,
        input_tokens=fin.input_tokens,
        output_tokens=fin.output_tokens,
        cache_creation_tokens=0,
        cache_read_tokens=prefix,
    )
    return cold.total_cost_usd, warm.total_cost_usd


def compute_cat4_cold_warm_costs(
    *,
    rung_id: str,
    q_idx: int,
    synth_finops: FinOpsBreakdown,
    rerank_finops: FinOpsBreakdown | None,
) -> tuple[float, float]:
    """Return (cold_query_cost_usd, warm_query_cost_usd) normalized cleanly for cache state (synthesis + rerank)."""
    s_cold, s_warm = _cold_warm(synth_finops, q_idx)
    r_cold, r_warm = _cold_warm(rerank_finops, q_idx)
    return round(s_cold + r_cold, 8), round(s_warm + r_warm, 8)


def persist_cat4_trace(
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
            "max_tokens": CAT4_SYNTH_MAX_TOKENS,
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
            category=CAT4_CATEGORY,
            use_case=CAT4_USE_CASE,
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


def finalize_cat4_rung_summary(
    *,
    rung_id: Cat4RungId,
    model_id: str,
    queries: list[Cat4QueryResult],
    status: str = "ok",
    error_message: str | None = None,
) -> Cat4RungSummary:
    title, badge, reranker_model, notes = _rung_metadata(rung_id)
    pattern = CAT4_RUNG_TO_PATTERN[rung_id]

    total_uncached_in = sum(q.finops.input_tokens for q in queries)
    total_c_write = sum(q.finops.cache_creation_tokens for q in queries)
    total_c_read = sum(q.finops.cache_read_tokens for q in queries)
    total_out = sum(q.finops.output_tokens for q in queries)

    rerank_queries = [q for q in queries if q.reranker_finops is not None]
    rerank_calls = len(rerank_queries)
    rerank_in = sum(q.reranker_finops.input_tokens for q in rerank_queries if q.reranker_finops)
    rerank_out = sum(q.reranker_finops.output_tokens for q in rerank_queries if q.reranker_finops)
    rerank_cost = round(
        sum(q.reranker_finops.total_cost_usd for q in rerank_queries if q.reranker_finops),
        8,
    )

    cold_audit = round(sum(q.cold_query_cost_usd for q in queries), 8)
    warm_audit = round(sum(q.warm_query_cost_usd for q in queries), 8)
    single_cold_1k = round(queries[0].cold_query_cost_usd * 1000, 4) if queries else 0.0

    avg_cits = round(sum(len(q.citations) for q in queries) / len(queries), 2) if queries else 0.0
    avg_cov = (
        round(sum(q.doc_citation_coverage_pct for q in queries) / len(queries), 1)
        if queries
        else 0.0
    )
    recalls = [q.reranker_recall_pct for q in queries if q.reranker_recall_pct is not None]
    avg_recall = round(sum(recalls) / len(recalls), 1) if recalls else None
    tot_lat = sum(q.latency_ms + q.reranker_latency_ms for q in queries)

    return Cat4RungSummary(
        rung_id=rung_id,
        rung_title=title,
        badge_text=badge,
        pattern=pattern,
        model_id=model_id,
        reranker_model_id=reranker_model if queries else None,
        provider="Anthropic",
        status=status,  # type: ignore[arg-type]
        error_message=error_message,
        queries=queries,
        total_uncached_input_tokens=total_uncached_in,
        total_cache_creation_tokens=total_c_write,
        total_cache_read_tokens=total_c_read,
        total_output_tokens=total_out,
        reranker_calls=rerank_calls,
        reranker_input_tokens=rerank_in,
        reranker_output_tokens=rerank_out,
        reranker_cost_usd=rerank_cost,
        cold_audit_cost_usd=cold_audit,
        warm_audit_cost_usd=warm_audit,
        cost_per_1k_audits_cold_usd=round(cold_audit * 1000, 4),
        cost_per_1k_audits_warm_usd=round(warm_audit * 1000, 4),
        single_query_cold_per_1k_usd=single_cold_1k,
        avg_citations_per_query=avg_cits,
        avg_doc_coverage_pct=avg_cov,
        avg_reranker_recall_pct=avg_recall,
        total_latency_ms=tot_lat,
        architectural_notes=notes,
    )


def _frac(m: Any) -> str:
    return f"{m.hits}/{m.total}" if m is not None else "n/a"


def _portfolio_cell(portfolio: Cat4QualityPortfolio | None, rung_id: str, scale: int) -> Cat4PortfolioCell | None:
    """The rerun cell for (rung, scale)."""
    if portfolio is None:
        return None
    return next((c for c in portfolio.cells if c.rung_id == rung_id and c.scale == scale), None)


def _audit_quality_text(res: Cat4RungSummary) -> str | None:
    """'On this audit: …' sentence from the rung's quality block; None when unscored."""
    q = res.quality
    if q is None:
        return None
    a = q.audit
    parts = [f"stated {_frac(a.key_facts)} key contract facts"]
    if a.citations_requested and a.citations_at_expected is not None:
        parts.append(f"{_frac(a.citations_at_expected)} citations pointed at the expected clauses")
    if a.retrieval_recall is not None:
        parts.append(f"the picked clauses held {_frac(a.retrieval_recall)} expected clauses")
    if a.judged:
        parts.append(
            f"the blind grader gave {a.correctness_mean:.2f}/5 for correctness and found a serious error in "
            f"{a.answers_with_material_error}/{a.judged} answers"
        )
    return f"On this audit it {', '.join(parts[:-1])}{', and ' if len(parts) > 1 else ''}{parts[-1]}."


def _apply_measured_claims(
    results: list[Cat4RungSummary],
    portfolio: Cat4QualityPortfolio | None = None,
) -> None:
    """Rewrite result-dependent rung badges/notes with numbers measured on this audit (and the rerun)."""
    ok = {r.rung_id: r for r in results if r.status == "ok" and r.queries}
    naive = ok.get("naive_full_corpus")
    paired = ok.get(PAIRED_RUNG)
    if naive:
        per_q = round(naive.total_uncached_input_tokens / len(naive.queries))
        set_note(
            naive,
            0,
            f"Sends all 7 Deal-Room documents ({per_q:,} prompt tok per query) as plain uncached user text "
            "on every query ($2.00/M input).",
        )
    if paired:
        avg_red = sum(q.context_reduction_pct for q in paired.queries) / len(paired.queries)
        paired.badge_text = f"With the improvement: ~{fmt_pct(avg_red)} of Corpus Not Sent to Sonnet + Citations"
        block = max(
            (q.reranker_finops.cache_creation_tokens + q.reranker_finops.cache_read_tokens
             for q in paired.queries if q.reranker_finops),
            default=0,
        )
        if block:
            set_note(
                paired,
                0,
                f"Haiku 5.5 reads all 28 deal-room clauses from one cached ~{block:,}-tok block (the first question "
                "writes it, later questions read it) and picks the 5 it judges most relevant; Sonnet 5.5 answers over those 5 "
                "with native citations.",
            )
        cut = pct_cut(naive.single_query_cold_per_1k_usd, paired.single_query_cold_per_1k_usd) if naive else None
        if cut is not None:
            set_note(
                paired,
                1,
                f"Haiku's spend, including the cache write, is included in this version's cost — a single cold "
                f"question costs {fmt_pct(cut)} less than without the improvement.",
            )
    # note 2 of both versions: this audit's quality (+ the rerun at the larger corpus)
    for res in (naive, paired):
        if res is None:
            continue
        text = _audit_quality_text(res)
        if text is None:
            continue
        cell = _portfolio_cell(portfolio, res.rung_id, 3)
        if cell is not None and cell.judged and cell.answers_with_material_error is not None:
            extra = f" In the rerun with a 3× corpus (two other suppliers' look-alike contracts added), {cell.answers_with_material_error.hits}/{cell.judged} answers had a serious error"
            if cell.recall_after_rerank is not None:
                extra += f" and Haiku's picks held {fmt_pct((cell.recall_after_rerank.rate or 0) * 100)} of the expected clauses"
            text += extra + "."
        set_note(res, 2, text)


def _apply_cross_rung_savings(results: list[Cat4RungSummary]) -> None:
    naive = next((r for r in results if r.rung_id == "naive_full_corpus" and r.status == "ok"), None)
    if not naive:
        return
    for res in results:
        if res.status != "ok":
            continue
        if naive.cold_audit_cost_usd > 0:
            res.savings_vs_naive_cold_pct = round(
                ((naive.cold_audit_cost_usd - res.cold_audit_cost_usd) / naive.cold_audit_cost_usd)
                * 100,
                2,
            )
        if naive.warm_audit_cost_usd > 0:
            res.savings_vs_naive_warm_pct = round(
                ((naive.warm_audit_cost_usd - res.warm_audit_cost_usd) / naive.warm_audit_cost_usd)
                * 100,
                2,
            )


async def _run_live_cat4_query_for_rung(
    *,
    q_idx: int,
    q_spec: dict[str, Any],
    rung_id: Cat4RungId,
    hydrated_docs: list[dict[str, Any]],
    flat_chunks: list[dict[str, Any]],
    total_corpus_chars: int,
    api_key: str,
) -> tuple[Cat4QueryResult, dict[str, Any]]:
    doc_by_id = {d["doc_id"]: d for d in hydrated_docs}
    q_text = str(q_spec["question"])
    # The question as the models receive it: the supplier-scope line + the original text, in the clause-pick query
    # and the synthesis message (as in the quality rerun). `question` stays the original text.
    q_asked = scoped_question(q_text)
    expected_docs = list(q_spec.get("expected_doc_ids") or [])
    expected_chunks = list(q_spec.get("expected_chunk_ids") or [])
    full_est_tokens = max(1, round(total_corpus_chars / 2.4))

    rerank_finops: FinOpsBreakdown | None = None
    rerank_latency = 0
    rerank_stop: str | None = None
    rerank_payload_text: str | None = None
    rerank_raw_structured: dict[str, Any] | None = None
    funnel: list[Cat4RetrievalChunkTrace] = []
    rerank_recall: float | None = None
    doc_blocks: list[dict[str, Any]] | None = None
    uncached_text: str | None = None
    use_cache = False
    ctx_chars_sent = total_corpus_chars

    if rung_id == "naive_full_corpus":
        uncached_text = build_uncached_corpus_text(hydrated_docs)
    elif rung_id == PAIRED_RUNG:
        rerank_payload_text = q_asked
        rerank_raw = await run_cat4_haiku_reranker(
            rerank_payload="",
            system_prompt=get_full_corpus_reranker_system_prompt(),
            schema=RERANK_JSON_SCHEMA,
            api_key=api_key,
            max_tokens=CAT4_RERANK_MAX_TOKENS,
            user_content=build_rerank_content(flat_chunks, q_asked),
        )
        rerank_latency = rerank_raw.latency_ms
        rerank_stop = rerank_raw.stop_reason
        rerank_finops = compute_run_finops(
            model_id=rerank_raw.model_id,
            input_tokens=rerank_raw.input_tokens,
            output_tokens=rerank_raw.output_tokens,
            cache_creation_tokens=rerank_raw.cache_creation_tokens,
            cache_read_tokens=rerank_raw.cache_read_tokens,
        )
        rerank_raw_structured = rerank_raw.structured
        selected_chunks, _invalid = select_picked_chunks({c["chunk_id"]: c for c in flat_chunks}, rerank_raw.structured)
        funnel_dicts, rerank_recall = picked_funnel(selected_chunks, rerank_raw.structured, expected_chunks)
        funnel = [Cat4RetrievalChunkTrace(**fd) for fd in funnel_dicts]
        doc_blocks = build_rung3_chunk_blocks(selected_chunks)
        ctx_chars_sent = sum(len(b["data"]) for b in doc_blocks)
    else:
        raise ValueError(f"Unknown Category 4 rung `{rung_id}`")

    with_citations = doc_blocks is not None
    synth_raw = await run_cat4_rag_synthesis(
        # per-rung prompt (answer_formats.RUNG_ANSWER_FORMAT)
        system_prompt=rung_synthesis_system_prompt(rung_id, with_citations=with_citations),
        user_question=q_asked,
        documents_for_blocks=doc_blocks,
        uncached_corpus_text=uncached_text,
        use_prefix_cache=use_cache,
        api_key=api_key,
        max_tokens=CAT4_SYNTH_MAX_TOKENS,
    )
    fin = compute_run_finops(
        model_id=synth_raw.model_id,
        input_tokens=synth_raw.input_tokens,
        output_tokens=synth_raw.output_tokens,
        cache_creation_tokens=synth_raw.cache_creation_tokens,
        cache_read_tokens=synth_raw.cache_read_tokens,
    )
    cold_cost, warm_cost = compute_cat4_cold_warm_costs(
        rung_id=rung_id,
        q_idx=q_idx,
        synth_finops=fin,
        rerank_finops=rerank_finops,
    )
    citations = _enrich_citations(
        synth_raw.structured.get("citations") or [],
        doc_by_id,
    )
    segments = [
        Cat4AnswerSegment(text=str(seg["text"]), cite_numbers=list(seg.get("cite_numbers") or []))
        for seg in (synth_raw.structured.get("segments") or [])
    ]
    cited_doc_ids = sorted({c.doc_id for c in citations if c.doc_id})
    doc_cov_pct = (
        round((len(set(expected_docs) & set(cited_doc_ids)) / len(expected_docs)) * 100, 1)
        if expected_docs
        else (100.0 if cited_doc_ids else 0.0)
    )
    ctx_tokens_sent = fin.input_tokens + fin.cache_creation_tokens + fin.cache_read_tokens
    reduction_pct = (
        round(((total_corpus_chars - ctx_chars_sent) / total_corpus_chars) * 100, 1)
        if total_corpus_chars > 0 and rung_id == PAIRED_RUNG
        else 0.0
    )

    q_res = Cat4QueryResult(
        question_id=str(q_spec["question_id"]),
        question_number=int(q_spec["question_number"]),
        topic_tag=str(q_spec["topic_tag"]),
        question=q_text,
        question_as_asked=q_asked,
        stop_reason=synth_raw.stop_reason,
        expected_doc_ids=expected_docs,
        expected_chunk_ids=expected_chunks,
        answer_markdown=synth_raw.raw_text,
        segments=segments,
        citations=citations,
        cited_doc_ids=cited_doc_ids,
        doc_citation_coverage_pct=doc_cov_pct,
        latency_ms=synth_raw.latency_ms,
        finops=fin,
        cold_query_cost_usd=cold_cost,
        warm_query_cost_usd=warm_cost,
        reranker_finops=rerank_finops,
        reranker_latency_ms=rerank_latency,
        reranker_stop_reason=rerank_stop,
        retrieval_funnel=funnel,
        reranker_recall_pct=rerank_recall,
        context_tokens_sent=ctx_tokens_sent or full_est_tokens,
        context_reduction_pct=reduction_pct,
    )
    raw_record: dict[str, Any] = {
        "question_id": q_res.question_id,
        "question_number": q_res.question_number,
        "topic_tag": q_res.topic_tag,
        "question": q_text,
        "question_as_asked": q_asked,
        "model_id": synth_raw.model_id,
        "latency_ms": synth_raw.latency_ms,
        "stop_reason": synth_raw.stop_reason,
        "max_tokens": CAT4_SYNTH_MAX_TOKENS,
        "answer_format": rung_answer_format(rung_id),
        "input_tokens": synth_raw.input_tokens,
        "output_tokens": synth_raw.output_tokens,
        "cache_creation_tokens": synth_raw.cache_creation_tokens,
        "cache_read_tokens": synth_raw.cache_read_tokens,
        "answer_markdown": synth_raw.raw_text,
        "segments": [s.model_dump() for s in segments],
        "citations": [c.model_dump() for c in citations],
        "context_chars_sent": ctx_chars_sent,
        "context_reduction_pct": reduction_pct,
        "reranker_model_id": rerank_finops.model_id if rerank_finops else None,
        "reranker_stop_reason": rerank_stop,
        "reranker_latency_ms": rerank_latency,
        "reranker_input_tokens": rerank_finops.input_tokens if rerank_finops else 0,
        "reranker_output_tokens": rerank_finops.output_tokens if rerank_finops else 0,
        "reranker_cache_creation_tokens": rerank_finops.cache_creation_tokens if rerank_finops else 0,
        "reranker_cache_read_tokens": rerank_finops.cache_read_tokens if rerank_finops else 0,
        "reranker_payload": rerank_payload_text,
        "reranker_structured": rerank_raw_structured,
        "retrieval_funnel": [f.model_dump() for f in funnel],
        "reranker_recall_pct": rerank_recall,
    }
    return q_res, raw_record


async def _run_live_cat4_audit_for_rung(
    *,
    preset: dict[str, Any],
    rung_id: Cat4RungId,
    hydrated_docs: list[dict[str, Any]],
    flat_chunks: list[dict[str, Any]],
    total_corpus_chars: int,
    api_key: str,
) -> tuple[Cat4RungSummary, list[dict[str, Any]]]:
    """Run all 4 questions sequentially for one rung (so later questions read the cache the first one wrote)."""
    q_results: list[Cat4QueryResult] = []
    raw_records: list[dict[str, Any]] = []
    used_model = "claude-sonnet-5-5"

    for q_idx, q_spec in enumerate(preset["questions"]):
        q_res, raw_rec = await _run_live_cat4_query_for_rung(
            q_idx=q_idx,
            q_spec=q_spec,
            rung_id=rung_id,
            hydrated_docs=hydrated_docs,
            flat_chunks=flat_chunks,
            total_corpus_chars=total_corpus_chars,
            api_key=api_key,
        )
        used_model = q_res.finops.model_id
        q_results.append(q_res)
        raw_records.append(raw_rec)

    summary = finalize_cat4_rung_summary(
        rung_id=rung_id,
        model_id=used_model,
        queries=q_results,
    )
    return summary, raw_records


def _build_cat4_summary_from_replay(
    *,
    rung_id: Cat4RungId,
    preset: dict[str, Any],
    raw_queries: list[dict[str, Any]],
    total_corpus_chars: int,
) -> Cat4RungSummary:
    q_specs_by_id = {q["question_id"]: q for q in preset["questions"]}
    q_results: list[Cat4QueryResult] = []
    used_model = "claude-sonnet-5-5"

    for q_idx, rq in enumerate(raw_queries):
        q_id = str(rq["question_id"])
        q_spec = q_specs_by_id.get(q_id) or {}
        used_model = str(rq.get("model_id") or "claude-sonnet-5-5")
        fin = compute_run_finops(
            model_id=used_model,
            input_tokens=int(rq["input_tokens"]),
            output_tokens=int(rq["output_tokens"]),
            cache_creation_tokens=int(rq.get("cache_creation_tokens") or 0),
            cache_read_tokens=int(rq.get("cache_read_tokens") or 0),
        )
        rerank_fin: FinOpsBreakdown | None = None
        if int(rq.get("reranker_input_tokens") or 0) > 0 or rq.get("reranker_model_id"):
            rerank_fin = compute_run_finops(
                model_id=str(rq.get("reranker_model_id") or "claude-haiku-5-5"),
                input_tokens=int(rq.get("reranker_input_tokens") or 0),
                output_tokens=int(rq.get("reranker_output_tokens") or 0),
                cache_creation_tokens=int(rq.get("reranker_cache_creation_tokens") or 0),
                cache_read_tokens=int(rq.get("reranker_cache_read_tokens") or 0),
            )
        cold_cost, warm_cost = compute_cat4_cold_warm_costs(
            rung_id=rung_id,
            q_idx=q_idx,
            synth_finops=fin,
            rerank_finops=rerank_fin,
        )
        citations = [Cat4CitationSpan(**c) for c in (rq.get("citations") or [])]
        segments = [Cat4AnswerSegment(**s) for s in (rq.get("segments") or [])]
        expected_docs = list(q_spec.get("expected_doc_ids") or [])
        expected_chunks = list(q_spec.get("expected_chunk_ids") or [])
        cited_doc_ids = sorted({c.doc_id for c in citations if c.doc_id})
        doc_cov_pct = (
            round((len(set(expected_docs) & set(cited_doc_ids)) / len(expected_docs)) * 100, 1)
            if expected_docs
            else (100.0 if cited_doc_ids else 0.0)
        )
        ctx_chars = int(rq.get("context_chars_sent") or total_corpus_chars)
        reduction_pct = (
            round(((total_corpus_chars - ctx_chars) / total_corpus_chars) * 100, 1)
            if total_corpus_chars > 0 and rung_id == PAIRED_RUNG
            else 0.0
        )

        q_results.append(
            Cat4QueryResult(
                question_id=q_id,
                question_number=int(rq["question_number"]),
                topic_tag=str(rq["topic_tag"]),
                question=str(rq["question"]),
                question_as_asked=rq.get("question_as_asked") or str(rq["question"]),
                stop_reason=rq.get("stop_reason"),
                expected_doc_ids=expected_docs,
                expected_chunk_ids=expected_chunks,
                answer_markdown=str(rq["answer_markdown"]),
                segments=segments,
                citations=citations,
                cited_doc_ids=cited_doc_ids,
                doc_citation_coverage_pct=doc_cov_pct,
                latency_ms=int(rq["latency_ms"]),
                finops=fin,
                cold_query_cost_usd=cold_cost,
                warm_query_cost_usd=warm_cost,
                reranker_finops=rerank_fin,
                reranker_latency_ms=int(rq.get("reranker_latency_ms") or 0),
                reranker_stop_reason=rq.get("reranker_stop_reason"),
                retrieval_funnel=[
                    Cat4RetrievalChunkTrace(**f) for f in (rq.get("retrieval_funnel") or [])
                ],
                reranker_recall_pct=rq.get("reranker_recall_pct"),
                context_tokens_sent=fin.input_tokens + fin.cache_creation_tokens + fin.cache_read_tokens,
                context_reduction_pct=reduction_pct,
            )
        )

    return finalize_cat4_rung_summary(rung_id=rung_id, model_id=used_model, queries=q_results)


def _rollup_stop_reason(stops: list[str | None]) -> str | None:
    """end_turn only when every query ended normally; otherwise the first other recorded stop reason."""
    if stops and all(s == "end_turn" for s in stops):
        return "end_turn"
    return next((s for s in stops if s != "end_turn"), None)


def _persist_cat4_rung_traces(
    *,
    source_mode: str,
    run_group_id: str,
    preset_title: str,
    item_prefix: str,
    res: Cat4RungSummary,
    source_endpoint: str,
    rerank_payloads: dict[str, str] | None = None,
) -> None:
    if res.status != "ok" or not res.queries:
        return
    last_q = res.queries[-1]
    rollup_fin = compute_run_finops(
        model_id=res.model_id,
        input_tokens=res.total_uncached_input_tokens,
        output_tokens=res.total_output_tokens,
        cache_creation_tokens=res.total_cache_creation_tokens,
        cache_read_tokens=res.total_cache_read_tokens,
    )
    persist_cat4_trace(
        source_mode=source_mode,
        run_group_id=run_group_id,
        item_id=f"{item_prefix}__audit_4q",
        item_title=f"{preset_title} · 4-Query Deal-Room Rollup",
        model_id=res.model_id,
        pattern=res.pattern,
        system_instruction=rung_synthesis_system_prompt(
            res.rung_id, with_citations=(res.rung_id != "naive_full_corpus")
        ),
        payload_text="\n".join(f"Q{q.question_number}: {q.question}" for q in res.queries),
        status=res.status,
        latency_ms=res.total_latency_ms,
        finops_dict=rollup_fin.model_dump(),
        raw_text=last_q.answer_markdown,
        structured_output={
            "queries_completed": len(res.queries),
            "cold_audit_cost_usd": res.cold_audit_cost_usd,
            "warm_audit_cost_usd": res.warm_audit_cost_usd,
            "cost_per_1k_audits_cold_usd": res.cost_per_1k_audits_cold_usd,
            "cost_per_1k_audits_warm_usd": res.cost_per_1k_audits_warm_usd,
            "reranker_calls": res.reranker_calls,
            "reranker_cost_usd": res.reranker_cost_usd,
            "avg_citations_per_query": res.avg_citations_per_query,
            "avg_reranker_recall_pct": res.avg_reranker_recall_pct,
        },
        request_params={
            "endpoint": "messages.create",
            "prefix_cache_enabled": res.rung_id == PAIRED_RUNG,
            "native_document_citations": res.rung_id != "naive_full_corpus",
            "queries": len(res.queries),
            "max_tokens": CAT4_SYNTH_MAX_TOKENS,
            "answer_format": rung_answer_format(res.rung_id),
        },
        stop_reason=_rollup_stop_reason([q.stop_reason for q in res.queries]),
        extra_metadata={"source_endpoint": source_endpoint, "rung_id": res.rung_id},
    )
    if res.rung_id == PAIRED_RUNG:
        for q in res.queries:
            if q.reranker_finops:
                persist_cat4_trace(
                    source_mode=source_mode,
                    run_group_id=run_group_id,
                    item_id=f"{item_prefix}__{q.question_id}_rerank",
                    item_title=f"{preset_title} · Haiku Clause Pick ({q.question_id})",
                    model_id=q.reranker_finops.model_id,
                    pattern=RERANKER_PATTERN,
                    system_instruction=get_full_corpus_reranker_system_prompt(),
                    payload_text=(rerank_payloads or {}).get(q.question_id, q.question),
                    status="ok",
                    latency_ms=q.reranker_latency_ms,
                    finops_dict=q.reranker_finops.model_dump(),
                    raw_text=json.dumps(
                        [f.chunk_id for f in q.retrieval_funnel if f.stage == "selected_by_reranker"]
                    ),
                    structured_output={
                        "selected_chunks": [
                            {
                                "chunk_id": f.chunk_id,
                                "relevance_score": f.reranker_score,
                                "rationale": f.reranker_rationale,
                            }
                            for f in q.retrieval_funnel
                            if f.stage == "selected_by_reranker"
                        ]
                    },
                    request_params={
                        "max_tokens": CAT4_RERANK_MAX_TOKENS,
                        "thinking": {"type": "disabled"},
                        "output_config": {"format": {"type": "json_schema"}},
                        "cached_clause_block": True,
                    },
                    json_schema=RERANK_JSON_SCHEMA,
                    stop_reason=q.reranker_stop_reason,
                    extra_metadata={"source_endpoint": source_endpoint, "question_id": q.question_id},
                )


def build_rung_quality(*args: Any, **kwargs: Any):
    """Lazy import: app.archetypes.cat4_rag.quality imports quality_rerun, which imports this module's builders."""
    from app.archetypes.cat4_rag.quality import build_rung_quality as _impl

    return _impl(*args, **kwargs)


def load_cat4_quality_portfolio() -> Cat4QualityPortfolio | None:
    from app.archetypes.cat4_rag.quality import load_cat4_quality_portfolio as _impl

    return _impl()


LIVE_GRADER_REASON = (
    "The blind grader is not run live (each grade is a paid call); recorded runs carry one grade per answer."
)


def _replay_billing_note(preset_trace: dict[str, Any]) -> str | None:
    """Billing note when the recorded paired version's first question READ a cache another audit wrote."""
    qs = (preset_trace.get("rungs") or {}).get(PAIRED_RUNG) or []
    if not qs:
        return None
    first = qs[0]
    if int(first.get("reranker_cache_creation_tokens") or 0) == 0 and int(first.get("reranker_cache_read_tokens") or 0) > 0:
        return (
            "Recorded billing: this audit ran in the same session right after the other audit, so its first question "
            "read the clause cache that audit had written — no cache write was billed here. The cold-audit figures "
            "model a fresh cache write for this audit."
        )
    return None


def _cat4_callout(
    naive: Cat4RungSummary | None,
    paired: Cat4RungSummary | None,
    *,
    total_chars: int,
    portfolio: Cat4QualityPortfolio | None,
) -> str:
    if not (naive and paired):
        return (
            "Category 4 compares the deal-room audit without the improvement (full corpus, no cache, no citations) "
            "and with it (Haiku picks 5 clauses from the cached corpus; Sonnet answers with citations)."
        )
    red = sum(q.context_reduction_pct for q in paired.queries) / len(paired.queries)
    text = (
        f"4-question deal-room audit (7 documents · {round(total_chars / 2.4):,} est. tok): without the improvement "
        f"(full corpus, no cache) it costs ${naive.cost_per_1k_audits_cold_usd:.2f}/1k audits and returns no "
        f"citations. With retrieval paired with caching, Sonnet sees ~{red:.0f}% less of the corpus and the audit costs "
        f"${paired.cost_per_1k_audits_cold_usd:.2f}/1k from a cold cache (${paired.cost_per_1k_audits_warm_usd:.2f}/1k "
        "warm), Haiku included."
    )
    qs = [("Without", naive.quality), ("With", paired.quality)]
    if all(q is not None and q.audit.judged for _, q in qs):
        text += (
            " Answer quality on this audit (key facts stated · grader correctness · answers with a serious error): "
            + "; ".join(
                f"{label} {_frac(q.audit.key_facts)} · {q.audit.correctness_mean:.2f}/5 · "
                f"{q.audit.answers_with_material_error}/{q.audit.judged}"
                for label, q in qs
                if q is not None
            )
            + "."
        )
    n3 = _portfolio_cell(portfolio, "naive_full_corpus", 3)
    p3 = _portfolio_cell(portfolio, PAIRED_RUNG, 3)
    if n3 and p3 and n3.answers_with_material_error and p3.answers_with_material_error:
        text += (
            f" In the rerun with a 3× corpus, {n3.answers_with_material_error.hits}/{n3.judged} answers had a serious "
            f"error without the improvement vs {p3.answers_with_material_error.hits}/{p3.judged} with it."
        )
    return text


async def execute_cat4_run(
    req: Cat4RunRequest,
    http_request: Request | None = None,
) -> Cat4RunResponse:
    presets = _preset_map()
    preset = presets.get(req.preset_id)
    if not preset:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown Category 4 preset_id `{req.preset_id}`.",
        )

    hydrated_docs, flat_chunks, total_chars = hydrate_deal_room_index()
    run_group_id = str(uuid4())
    results: list[Cat4RungSummary] = []

    if req.mode == "replay":
        replays = load_cat4_replays()
        preset_trace = (replays.get("presets") or {}).get(preset["id"])
        if not preset_trace:
            raise HTTPException(
                status_code=404,
                detail=f"Replay trace missing for Category 4 preset {preset['id']}.",
            )
        for rung_id in req.rungs:
            r_queries = (preset_trace.get("rungs") or {}).get(rung_id)
            if not r_queries:
                raise HTTPException(
                    status_code=404,
                    detail=f"Replay trace missing rung `{rung_id}` on {preset['id']}.",
                )
            summary = _build_cat4_summary_from_replay(
                rung_id=rung_id,
                preset=preset,
                raw_queries=r_queries,
                total_corpus_chars=total_chars,
            )
            summary.quality, summary.quality_unavailable_reason = build_rung_quality(
                summary.queries,
                rung_id=rung_id,
                preset_id=preset["id"],
                judgements=[rq.get("judgement") for rq in r_queries],
                grader_unavailable_reason="This recorded run carries no grade.",
            )
            results.append(summary)
        billing_note = _replay_billing_note(preset_trace)
        mode_used = "replay"
    else:
        creds = credit_shield.resolve_live_credentials(
            http_request,
            need_anthropic=True,
        )
        assert creds.anthropic_api_key

        async def _safe_rung(rid: Cat4RungId) -> Cat4RungSummary:
            try:
                summary, _ = await _run_live_cat4_audit_for_rung(
                    preset=preset,
                    rung_id=rid,
                    hydrated_docs=hydrated_docs,
                    flat_chunks=flat_chunks,
                    total_corpus_chars=total_chars,
                    api_key=creds.anthropic_api_key or "",
                )
                summary.quality, summary.quality_unavailable_reason = build_rung_quality(
                    summary.queries, rung_id=rid, preset_id=preset["id"], judgements=None,
                    grader_unavailable_reason=LIVE_GRADER_REASON,
                )
                return summary
            except Exception as exc:
                return finalize_cat4_rung_summary(
                    rung_id=rid,
                    model_id="claude-sonnet-5-5",
                    queries=[],
                    status="error",
                    error_message=str(exc)[:300],
                )

        results = list(await asyncio.gather(*(_safe_rung(r) for r in req.rungs)))
        if creds.uses_server_budget:
            total_spend = sum(r.cold_audit_cost_usd for r in results if r.status == "ok")
            credit_shield.record_server_spend(total_spend)
        billing_note = None
        mode_used = "live"

    portfolio = load_cat4_quality_portfolio()
    _apply_cross_rung_savings(results)
    _apply_measured_claims(results, portfolio)

    for res in results:
        _persist_cat4_rung_traces(
            source_mode=mode_used,
            run_group_id=run_group_id,
            preset_title=preset["title"],
            item_prefix=preset["id"],
            res=res,
            source_endpoint="/api/cat4/run",
        )

    naive = next((r for r in results if r.rung_id == "naive_full_corpus" and r.status == "ok"), None)
    paired = next((r for r in results if r.rung_id == PAIRED_RUNG and r.status == "ok"), None)
    callout = _cat4_callout(naive, paired, total_chars=total_chars, portfolio=portfolio)

    return Cat4RunResponse(
        mode_used=mode_used,  # type: ignore[arg-type]
        preset_id=preset["id"],
        use_case="supplier_msa_due_diligence",
        title=preset["title"],
        deal_room_profile=DEAL_ROOM_PROFILE,
        total_docs=len(hydrated_docs),
        total_chunks=len(flat_chunks),
        corpus_char_count=total_chars,
        approx_corpus_tokens=max(1, round(total_chars / 2.4)),
        results=results,
        rag_callout=callout,
        billing_note=billing_note,
        quality_portfolio=portfolio,
    )


async def execute_cat4_adhoc_query(
    req: Cat4AdhocQueryRequest,
    http_request: Request | None = None,
) -> Cat4AdhocQueryResponse:
    if req.mode != "live":
        raise HTTPException(
            status_code=400,
            detail=(
                "Custom Deal-Room questions run live: Haiku 5.5 picks clauses from the cached corpus and Sonnet 5.5 "
                "answers with native citations. Switch Credit Shield to Live API mode to ask ad-hoc questions."
            ),
        )
    q_text = req.question.strip()
    if len(q_text) < 8:
        raise HTTPException(
            status_code=400,
            detail="Enter a due-diligence question of at least 8 characters.",
        )

    creds = credit_shield.resolve_live_credentials(
        http_request,
        need_anthropic=True,
    )
    assert creds.anthropic_api_key

    hydrated_docs, flat_chunks, total_chars = hydrate_deal_room_index()
    q_spec = {
        "question_id": "adhoc",
        "question_number": 1,
        "topic_tag": "Custom Deal-Room Query",
        "question": q_text,
        "expected_doc_ids": [],
        "expected_chunk_ids": [],
    }
    run_group_id = f"cat4-adhoc-{uuid4()}"

    async def _safe_adhoc(rid: Cat4RungId) -> Cat4RungSummary:
        try:
            q_res, _ = await _run_live_cat4_query_for_rung(
                q_idx=0,
                q_spec=q_spec,
                rung_id=rid,
                hydrated_docs=hydrated_docs,
                flat_chunks=flat_chunks,
                total_corpus_chars=total_chars,
                api_key=creds.anthropic_api_key or "",
            )
            summary = finalize_cat4_rung_summary(
                rung_id=rid,
                model_id=q_res.finops.model_id,
                queries=[q_res],
            )
            summary.quality, summary.quality_unavailable_reason = build_rung_quality(
                summary.queries, rung_id=rid, preset_id=req.preset_id, judgements=None,
                grader_unavailable_reason=LIVE_GRADER_REASON,
            )
            return summary
        except Exception as exc:
            return finalize_cat4_rung_summary(
                rung_id=rid,
                model_id="claude-sonnet-5-5",
                queries=[],
                status="error",
                error_message=str(exc)[:300],
            )

    results = list(await asyncio.gather(*(_safe_adhoc(r) for r in req.rungs)))
    portfolio = load_cat4_quality_portfolio()
    _apply_cross_rung_savings(results)
    _apply_measured_claims(results, portfolio)

    if creds.uses_server_budget:
        total_spend = sum(r.cold_audit_cost_usd for r in results if r.status == "ok")
        credit_shield.record_server_spend(total_spend)

    for res in results:
        _persist_cat4_rung_traces(
            source_mode="live",
            run_group_id=run_group_id,
            preset_title="Custom Deal-Room Query",
            item_prefix=f"{req.preset_id}-adhoc",
            res=res,
            source_endpoint="/api/cat4/query",
        )

    return Cat4AdhocQueryResponse(
        mode_used="live",
        preset_id=req.preset_id,
        question=q_text,
        results=results,
        quality_portfolio=portfolio,
    )
