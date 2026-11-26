"""Hybrid retrieval paired with context caching (`cached_rerank_hybrid`) — shared by the app and the quality rerun.

Haiku 5.5 reads every deal-room chunk as one cached content block plus the question and returns the 5 most
relevant chunk ids (the app's rerank schema); Sonnet 5.5 then answers over exactly those chunks with native
citations and the retrieval version's answer instructions (`answer_formats.RUNG_ANSWER_FORMAT`).
The first question writes the chunk cache; later questions read it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

PAIRED_RUNG = "cached_rerank_hybrid"
RERANK_TOP_K = 5  # clauses Haiku picks for the answer

# The clause-pick system prompt, byte for byte as recorded in the rerun sessions (sha256 pinned in the tests).
FULL_CORPUS_RERANKER_SYSTEM_PROMPT = (
    "You are NovaMart's Stage-2 Legal & Statutory RAG Reranker.\n"
    "From all deal-room contract chunks provided above the query, select the EXACT 5 most decisive chunks needed to "
    "answer the query completely.\n"
    "Rules:\n"
    "1. Prioritize controlling overrides (Addendum A Peak overrides, Side Letter #2 SL.1–SL.4, Clause 9.2 carve-outs) "
    "AND their corresponding baseline clauses when both are asked.\n"
    "2. Return exact chunk_id strings matching `CHUNK_ID:` (e.g., `DOC-07#c01`) sorted from highest to lowest "
    "relevance_score (0–100).\n"
    "3. Keep each rationale <= 12 words."
)


def get_full_corpus_reranker_system_prompt() -> str:
    """The clause-pick system prompt (see FULL_CORPUS_RERANKER_SYSTEM_PROMPT)."""
    return FULL_CORPUS_RERANKER_SYSTEM_PROMPT


def nonce_line(nonce: str) -> str:
    return f"[deal-room session {nonce}]\n"


def format_chunks_for_reranker(flat_chunks: Sequence[dict[str, Any]]) -> str:
    """Every chunk in the clause-pick format: id, document, clause, heading and excerpt."""
    blocks = [
        f"CHUNK_ID: {ch['chunk_id']} | DOC: {ch['doc_code']} — {ch['doc_title']} | CLAUSE: {ch['clause_ref']}\n"
        f"HEADING: {ch['section_heading']}\n"
        f"EXCERPT:\n{ch['text']}"
        for ch in flat_chunks
    ]
    return f"=== DEAL-ROOM CHUNKS (full corpus: {len(blocks)} chunks) ===\n\n" + "\n\n---\n\n".join(blocks)


def build_rerank_content(flat_chunks: Sequence[dict[str, Any]], question: str, nonce: str | None = None) -> list[dict[str, Any]]:
    """[cached block with every chunk, question block]. The rerun adds a per-session nonce so each session writes
    its own cache; the app sends none, so audits can share the cache."""
    head = nonce_line(nonce) if nonce else ""
    return [
        {"type": "text", "text": head + format_chunks_for_reranker(flat_chunks), "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": (f"=== DUE-DILIGENCE QUERY ===\n{question}\n\n"
                                  f"Select the exact {RERANK_TOP_K} most decisive chunks from the deal-room chunks above.")},
    ]


def select_picked_chunks(
    chunk_by_id: dict[str, dict[str, Any]], structured: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], list[str]]:
    """Valid, de-duplicated reranker picks in order (at most 5; no backfill) and the invalid ids returned."""
    picked: list[dict[str, Any]] = []
    invalid: list[str] = []
    for entry in (structured or {}).get("selected_chunks") or []:
        cid = str(entry.get("chunk_id") or "").strip()
        if cid not in chunk_by_id:
            invalid.append(cid)
            continue
        if any(p["chunk_id"] == cid for p in picked):
            continue
        picked.append(chunk_by_id[cid])
        if len(picked) >= RERANK_TOP_K:
            break
    return picked, invalid


def picked_funnel(
    picked: Sequence[dict[str, Any]], structured: dict[str, Any] | None, expected_chunk_ids: Sequence[str]
) -> tuple[list[dict[str, Any]], float | None]:
    """The clauses the small model picked, in pick order (for the app's citation viewer), and the share of expected
    clauses among them (%; None without an answer key)."""
    meta = {}
    for entry in (structured or {}).get("selected_chunks") or []:
        cid = str(entry.get("chunk_id") or "").strip()
        meta.setdefault(cid, entry)
    expected = set(expected_chunk_ids)
    rows = []
    for rank, ch in enumerate(picked, start=1):
        e = meta.get(ch["chunk_id"]) or {}
        rows.append({
            "chunk_id": ch["chunk_id"],
            "doc_id": ch["doc_id"],
            "doc_title": f"{ch['doc_code']} · {ch['doc_title']}",
            "clause_ref": ch["clause_ref"],
            "section_heading": ch["section_heading"],
            "char_count": ch["char_count"],
            "approx_tokens": ch["approx_tokens"],
            "pick_rank": rank,
            "stage": "selected_by_reranker",
            "reranker_score": max(0, min(100, int(e.get("relevance_score") or 0))) if e else None,
            "reranker_rationale": str(e.get("rationale") or "")[:140] or None,
            "is_expected_gold": ch["chunk_id"] in expected,
        })
    recall = round(len(expected & {c["chunk_id"] for c in picked}) / len(expected) * 100, 1) if expected else None
    return rows, recall
