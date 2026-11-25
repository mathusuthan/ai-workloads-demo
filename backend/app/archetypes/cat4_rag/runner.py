"""Orchestrates Category 4 Multi-Doc RAG & Deep Ingestion Arena and Ad-Hoc Queries."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4
from fastapi import HTTPException, Request

from app.archetypes.cat4_rag.prompts import (
    get_cat4_haiku_reranker_system_prompt,
    get_cat4_synthesis_system_prompt,
)
from app.archetypes.cat4_rag.retriever import (
    BM25_TOP_K,
    RERANK_TOP_K,
    build_reranker_payload,
    merge_rerank_funnel,
    rank_chunks_bm25,
)
from app.archetypes.cat4_rag.schemas import RERANK_JSON_SCHEMA
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
    "cached_full_corpus_citations": "prefix_cached_full_corpus_citations",
    "hybrid_rag_rerank_citations": "hybrid_bm25_haiku_rerank_citations",
}
RERANKER_PATTERN = "haiku_cross_chunk_reranker"


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
            "1. Uncached Full-Corpus Stuffing",
            "Anti-Pattern: Uncached Dump ($2.00/M In)",
            None,
            [
                # replaced with the measured prompt size by _apply_measured_claims
                "Sends all 7 Deal-Room documents as plain uncached user text on every query ($2.00/M input).",
                "Produces zero verifiable Document Block citations — analysts must manually Cmd+F across 7 agreements to verify claims.",
            ],
        )
    if rung_id == "cached_full_corpus_citations":
        return (
            "2. Cached Full Corpus + Native Citations",
            "Lever 1: 95% Cache Reads + Citations",
            None,
            [
                "Attaches cache_control={'type': 'ephemeral'} on the 7th DocumentBlock: Q1 writes prefix ($2.50/M), Q2+ hit $0.10/M cache reads.",
                "Native Anthropic Citations return character-exact doc spans without chunking or missing subtle override clauses.",
            ],
        )
    return (
        "3. Hybrid BM25 + Haiku Rerank + Citations",
        "Lever 2: Token Pruning + Citations",  # measured pruning % added by _apply_measured_claims
        "claude-haiku-5-5",
        [
            "Deterministic BM25 retrieves top-10 of 28 clauses; Haiku 5.5 ($0.10/M) reranks to top-5 decisive chunks for Sonnet synthesis.",
            # replaced with the measured single-query saving by _apply_measured_claims
            "100% of Haiku reranker spend is included here, so its cost comparison with Rung 1 is like-for-like.",
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


def compute_cat4_cold_warm_costs(
    *,
    rung_id: str,
    q_idx: int,
    synth_finops: FinOpsBreakdown,
    rerank_finops: FinOpsBreakdown | None,
) -> tuple[float, float]:
    """Return (cold_query_cost_usd, warm_query_cost_usd) normalized cleanly for cache state."""
    rerank_cost = rerank_finops.total_cost_usd if rerank_finops else 0.0
    if rung_id != "cached_full_corpus_citations":
        tot = round(synth_finops.total_cost_usd + rerank_cost, 8)
        return tot, tot

    prefix_tok = synth_finops.cache_creation_tokens + synth_finops.cache_read_tokens
    if prefix_tok <= 0:
        return synth_finops.total_cost_usd, synth_finops.total_cost_usd

    cold_fin = compute_run_finops(
        model_id=synth_finops.model_id,
        input_tokens=synth_finops.input_tokens,
        output_tokens=synth_finops.output_tokens,
        cache_creation_tokens=prefix_tok if q_idx == 0 else 0,
        cache_read_tokens=0 if q_idx == 0 else prefix_tok,
    )
    warm_fin = compute_run_finops(
        model_id=synth_finops.model_id,
        input_tokens=synth_finops.input_tokens,
        output_tokens=synth_finops.output_tokens,
        cache_creation_tokens=0,
        cache_read_tokens=prefix_tok,
    )
    return cold_fin.total_cost_usd, warm_fin.total_cost_usd


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
            "max_tokens": 2048,
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


def _apply_measured_claims(results: list[Cat4RungSummary]) -> None:
    """Rewrite result-dependent rung badges/notes with numbers measured on this audit."""
    ok = {r.rung_id: r for r in results if r.status == "ok" and r.queries}
    naive, hybrid = ok.get("naive_full_corpus"), ok.get("hybrid_rag_rerank_citations")
    if naive:
        per_q = round(naive.total_uncached_input_tokens / len(naive.queries))
        set_note(
            naive,
            0,
            f"Sends all 7 Deal-Room documents ({per_q:,} prompt tok per query) as plain uncached user text "
            "on every query ($2.00/M input).",
        )
    if hybrid:
        avg_red = sum(q.context_reduction_pct for q in hybrid.queries) / len(hybrid.queries)
        hybrid.badge_text = f"Lever 2: ~{fmt_pct(avg_red)} Token Pruning + Citations"
        synth_prompt = round(
            sum(q.finops.input_tokens + q.finops.cache_creation_tokens + q.finops.cache_read_tokens for q in hybrid.queries)
            / len(hybrid.queries)
        )
        set_note(
            hybrid,
            0,
            "Deterministic BM25 retrieves top-10 of 28 clauses; Haiku 5.5 ($0.10/M) reranks to top-5 decisive "
            f"chunks for Sonnet synthesis (~{synth_prompt:,}-tok synthesis prompt).",
        )
        cut = pct_cut(naive.single_query_cold_per_1k_usd, hybrid.single_query_cold_per_1k_usd) if naive else None
        if cut is not None:
            set_note(
                hybrid,
                1,
                f"100% of Haiku reranker spend is included here — cuts single cold-query cost {fmt_pct(cut)} vs Rung 1.",
            )


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
    expected_docs = list(q_spec.get("expected_doc_ids") or [])
    expected_chunks = list(q_spec.get("expected_chunk_ids") or [])
    full_est_tokens = max(1, round(total_corpus_chars / 2.4))

    rerank_finops: FinOpsBreakdown | None = None
    rerank_latency = 0
    rerank_payload_text: str | None = None
    rerank_raw_structured: dict[str, Any] | None = None
    funnel: list[Cat4RetrievalChunkTrace] = []
    bm25_recall: float | None = None
    rerank_recall: float | None = None
    doc_blocks: list[dict[str, Any]] | None = None
    uncached_text: str | None = None
    use_cache = False
    ctx_chars_sent = total_corpus_chars

    if rung_id == "naive_full_corpus":
        uncached_text = build_uncached_corpus_text(hydrated_docs)
    elif rung_id == "cached_full_corpus_citations":
        doc_blocks = build_rung2_doc_blocks(hydrated_docs)
        use_cache = True
    else:
        bm25_ranked = rank_chunks_bm25(q_text, flat_chunks, top_k=BM25_TOP_K)
        candidates = [c for c in bm25_ranked if c["is_bm25_candidate"]]
        rerank_payload_text = build_reranker_payload(q_text, candidates)
        rerank_raw = await run_cat4_haiku_reranker(
            rerank_payload=rerank_payload_text,
            system_prompt=get_cat4_haiku_reranker_system_prompt(),
            schema=RERANK_JSON_SCHEMA,
            api_key=api_key,
            max_tokens=800,
        )
        rerank_latency = rerank_raw.latency_ms
        rerank_finops = compute_run_finops(
            model_id=rerank_raw.model_id,
            input_tokens=rerank_raw.input_tokens,
            output_tokens=rerank_raw.output_tokens,
        )
        rerank_raw_structured = rerank_raw.structured
        selected_chunks, funnel_dicts, bm25_recall, rerank_recall = merge_rerank_funnel(
            bm25_ranked=bm25_ranked,
            reranker_structured=rerank_raw.structured,
            expected_chunk_ids=expected_chunks,
            top_k_rerank=RERANK_TOP_K,
        )
        funnel = [Cat4RetrievalChunkTrace(**fd) for fd in funnel_dicts]
        doc_blocks = build_rung3_chunk_blocks(selected_chunks)
        ctx_chars_sent = sum(len(b["data"]) for b in doc_blocks)

    with_citations = doc_blocks is not None
    synth_raw = await run_cat4_rag_synthesis(
        system_prompt=get_cat4_synthesis_system_prompt(with_citations=with_citations),
        user_question=q_text,
        documents_for_blocks=doc_blocks,
        uncached_corpus_text=uncached_text,
        use_prefix_cache=use_cache,
        api_key=api_key,
        max_tokens=2048,
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
        if total_corpus_chars > 0 and rung_id == "hybrid_rag_rerank_citations"
        else 0.0
    )

    q_res = Cat4QueryResult(
        question_id=str(q_spec["question_id"]),
        question_number=int(q_spec["question_number"]),
        topic_tag=str(q_spec["topic_tag"]),
        question=q_text,
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
        retrieval_funnel=funnel,
        bm25_recall_pct=bm25_recall,
        reranker_recall_pct=rerank_recall,
        context_tokens_sent=ctx_tokens_sent or full_est_tokens,
        context_reduction_pct=reduction_pct,
    )
    raw_record: dict[str, Any] = {
        "question_id": q_res.question_id,
        "question_number": q_res.question_number,
        "topic_tag": q_res.topic_tag,
        "question": q_text,
        "model_id": synth_raw.model_id,
        "latency_ms": synth_raw.latency_ms,
        "stop_reason": synth_raw.stop_reason or "end_turn",
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
        "reranker_latency_ms": rerank_latency,
        "reranker_input_tokens": rerank_finops.input_tokens if rerank_finops else 0,
        "reranker_output_tokens": rerank_finops.output_tokens if rerank_finops else 0,
        "reranker_payload": rerank_payload_text,
        "reranker_structured": rerank_raw_structured,
        "retrieval_funnel": [f.model_dump() for f in funnel],
        "bm25_recall_pct": bm25_recall,
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
    """Run all 4 questions sequentially for one rung (preserving Rung 2 prefix cache chain)."""
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
        if int(rq.get("reranker_input_tokens") or 0) > 0:
            rerank_fin = compute_run_finops(
                model_id=str(rq.get("reranker_model_id") or "claude-haiku-5-5"),
                input_tokens=int(rq["reranker_input_tokens"]),
                output_tokens=int(rq["reranker_output_tokens"]),
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
            if total_corpus_chars > 0 and rung_id == "hybrid_rag_rerank_citations"
            else 0.0
        )

        q_results.append(
            Cat4QueryResult(
                question_id=q_id,
                question_number=int(rq["question_number"]),
                topic_tag=str(rq["topic_tag"]),
                question=str(rq["question"]),
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
                retrieval_funnel=[
                    Cat4RetrievalChunkTrace(**f) for f in (rq.get("retrieval_funnel") or [])
                ],
                bm25_recall_pct=rq.get("bm25_recall_pct"),
                reranker_recall_pct=rq.get("reranker_recall_pct"),
                context_tokens_sent=fin.input_tokens + fin.cache_creation_tokens + fin.cache_read_tokens,
                context_reduction_pct=reduction_pct,
            )
        )

    return finalize_cat4_rung_summary(rung_id=rung_id, model_id=used_model, queries=q_results)


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
        system_instruction=get_cat4_synthesis_system_prompt(
            with_citations=(res.rung_id != "naive_full_corpus")
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
            "prefix_cache_enabled": res.rung_id == "cached_full_corpus_citations",
            "native_document_citations": res.rung_id != "naive_full_corpus",
            "queries": len(res.queries),
        },
        stop_reason="end_turn",
        extra_metadata={"source_endpoint": source_endpoint, "rung_id": res.rung_id},
    )
    if res.rung_id == "hybrid_rag_rerank_citations":
        for q in res.queries:
            if q.reranker_finops:
                persist_cat4_trace(
                    source_mode=source_mode,
                    run_group_id=run_group_id,
                    item_id=f"{item_prefix}__{q.question_id}_rerank",
                    item_title=f"{preset_title} · Haiku Rerank ({q.question_id})",
                    model_id=q.reranker_finops.model_id,
                    pattern=RERANKER_PATTERN,
                    system_instruction=get_cat4_haiku_reranker_system_prompt(),
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
                        "max_tokens": 800,
                        "thinking": {"type": "disabled"},
                        "output_config": {"format": {"type": "json_schema"}},
                    },
                    json_schema=RERANK_JSON_SCHEMA,
                    stop_reason="end_turn",
                    extra_metadata={"source_endpoint": source_endpoint, "question_id": q.question_id},
                )


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
            results.append(
                _build_cat4_summary_from_replay(
                    rung_id=rung_id,
                    preset=preset,
                    raw_queries=r_queries,
                    total_corpus_chars=total_chars,
                )
            )
        mode_used = "replay"
    else:
        creds = credit_shield.resolve_live_credentials(
            http_request,
            need_anthropic=True,
            need_gemini=False,
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
        mode_used = "live"

    _apply_cross_rung_savings(results)
    _apply_measured_claims(results)

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
    cached = next(
        (r for r in results if r.rung_id == "cached_full_corpus_citations" and r.status == "ok"),
        None,
    )
    hybrid = next(
        (r for r in results if r.rung_id == "hybrid_rag_rerank_citations" and r.status == "ok"),
        None,
    )
    if naive and cached and hybrid:
        callout = (
            f"4-Query Deal-Room Audit FinOps (7 Docs · {round(total_chars / 2.4):,} est. tok): "
            f"Uncached Full-Corpus Stuffing costs ${naive.cost_per_1k_audits_cold_usd:.2f}/1k audits with 0 verifiable citations. "
            f"Prefix Caching + Native Citations cuts 4-query audit spend to ${cached.cost_per_1k_audits_cold_usd:.2f}/1k cold "
            f"(${cached.cost_per_1k_audits_warm_usd:.2f}/1k warm, -{cached.savings_vs_naive_cold_pct:.1f}% cold). "
            f"Hybrid BM25 + Haiku Rerank prunes ~{hybrid.queries[0].context_reduction_pct:.0f}% of irrelevant clauses for "
            f"${hybrid.single_query_cold_per_1k_usd:.2f}/1k on a single cold query (-{100 - (hybrid.single_query_cold_per_1k_usd / max(0.001, naive.single_query_cold_per_1k_usd)) * 100:.1f}% vs naive) "
            f"and ${hybrid.cost_per_1k_audits_cold_usd:.2f}/1k across the 4-query audit (${hybrid.reranker_cost_usd * 1000:.2f}/1k Haiku rerank included)!"
        )
    else:
        callout = (
            "Category 4 contrasts Uncached Full-Corpus Stuffing vs. Document-Block Prefix Caching + Native Citations "
            "vs. Hybrid BM25 + Haiku 5.5 Reranking + Native Citations."
        )

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
    )


async def execute_cat4_adhoc_query(
    req: Cat4AdhocQueryRequest,
    http_request: Request | None = None,
) -> Cat4AdhocQueryResponse:
    if req.mode != "live":
        raise HTTPException(
            status_code=400,
            detail=(
                "Custom Deal-Room questions execute live BM25 + Haiku 5.5 reranking and native Anthropic "
                "DocumentBlock citations. Switch Credit Shield to Live API mode to ask ad-hoc questions."
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
        need_gemini=False,
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
            return finalize_cat4_rung_summary(
                rung_id=rid,
                model_id=q_res.finops.model_id,
                queries=[q_res],
            )
        except Exception as exc:
            return finalize_cat4_rung_summary(
                rung_id=rid,
                model_id="claude-sonnet-5-5",
                queries=[],
                status="error",
                error_message=str(exc)[:300],
            )

    results = list(await asyncio.gather(*(_safe_adhoc(r) for r in req.rungs)))
    _apply_cross_rung_savings(results)
    _apply_measured_claims(results)

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
    )
