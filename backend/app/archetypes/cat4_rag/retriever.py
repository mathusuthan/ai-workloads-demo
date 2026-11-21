"""Hybrid Okapi BM25 + Legal Metadata Retriever for Category 4 Multi-Doc Deal Room."""

from __future__ import annotations

import math
import re
from typing import Any

BM25_TOP_K = 10
RERANK_TOP_K = 5

_STOPWORDS = frozenset(
    {
        "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
        "what", "which", "when", "where", "how", "does", "under", "into", "onto",
        "any", "all", "its", "their", "shall", "must", "may", "will", "not", "can",
        "have", "has", "been", "being", "than", "then", "also", "other", "such",
        "per", "including", "between", "across", "during", "prior", "against",
    }
)


def tokenize_legal_terms(text: str) -> list[str]:
    """Tokenize preserving Indian statutory numbers/codes (43b, 16, 2b, 3480, chg, aoc)."""
    raw = re.findall(r"[a-z0-9]+(?:[.\-][a-z0-9]+)*", text.lower())
    out: list[str] = []
    for tok in raw:
        parts = re.split(r"[.\-]", tok) if ("." in tok or "-" in tok) else [tok]
        if len(tok) > 1 and tok not in _STOPWORDS:
            out.append(tok)
        for p in parts:
            if len(p) > 1 and p not in _STOPWORDS and p != tok:
                out.append(p)
    return out


def _chunk_searchable_tokens(chunk: dict[str, Any]) -> list[str]:
    # Give extra weight to section_heading, clause_ref, doc_code, and keywords
    metadata_text = " ".join(
        [
            str(chunk.get("doc_code", "")),
            str(chunk.get("doc_title", "")),
            str(chunk.get("clause_ref", "")),
            str(chunk.get("section_heading", "")),
            " ".join(chunk.get("keywords") or []),
        ]
    )
    meta_tokens = tokenize_legal_terms(metadata_text)
    body_tokens = tokenize_legal_terms(str(chunk.get("text", "")))
    return (meta_tokens * 2) + body_tokens


def rank_chunks_bm25(
    query: str,
    chunks: list[dict[str, Any]],
    *,
    top_k: int = BM25_TOP_K,
) -> list[dict[str, Any]]:
    """Score all corpus chunks with Okapi BM25 + exact clause-code phrase bonus."""
    q_tokens = tokenize_legal_terms(query)
    if not chunks:
        return []

    doc_tokens_list = [_chunk_searchable_tokens(ch) for ch in chunks]
    n_docs = len(doc_tokens_list)
    avgdl = sum(len(d) for d in doc_tokens_list) / max(1, n_docs)

    df: dict[str, int] = {}
    for d_toks in doc_tokens_list:
        for term in set(d_toks):
            df[term] = df.get(term, 0) + 1

    k1 = 1.5
    b = 0.75
    q_lower = query.lower()

    scored: list[tuple[float, int, dict[str, Any]]] = []
    for idx, (ch, d_toks) in enumerate(zip(chunks, doc_tokens_list)):
        dl = len(d_toks)
        tf: dict[str, int] = {}
        for t in d_toks:
            tf[t] = tf.get(t, 0) + 1

        score = 0.0
        for q in set(q_tokens):
            if q not in tf:
                continue
            n_q = df.get(q, 0)
            idf = math.log((n_docs - n_q + 0.5) / (n_q + 0.5) + 1.0)
            freq = tf[q]
            denom = freq + k1 * (1.0 - b + b * (dl / max(1.0, avgdl)))
            score += idf * ((freq * (k1 + 1.0)) / max(1e-9, denom))

        # Exact legal/statutory phrase bonus for override clarity
        chunk_haystack = (
            f"{ch.get('doc_code', '')} {ch.get('clause_ref', '')} {' '.join(ch.get('keywords') or [])}"
        ).lower()
        for phrase in (
            "clause 9", "clause 11.4", "addendum a", "schedule b", "schedule c", "schedule d",
            "side letter", "kronevolt", "gstr-2b", "rule 37a", "43b(h)", "msmed",
            "aoc-4", "caro 2020", "chg-1", "cert-in", "dpdp", "un 3480", "epr-ka",
            "3.25%", "98.8%", "72", "nov 15", "oct 10", "exclusivity",
        ):
            if phrase in q_lower and phrase in chunk_haystack:
                score += 2.2

        scored.append((round(score, 4), idx, ch))

    scored.sort(key=lambda row: (-row[0], row[1]))

    ranked: list[dict[str, Any]] = []
    for rank_num, (bm25_score, _orig_idx, ch) in enumerate(scored, start=1):
        ranked.append(
            {
                **ch,
                "bm25_score": bm25_score,
                "bm25_rank": rank_num,
                "is_bm25_candidate": rank_num <= top_k,
            }
        )
    return ranked


def build_reranker_payload(query: str, candidate_chunks: list[dict[str, Any]]) -> str:
    """Serialize the BM25 top-K candidate chunks compactly for Haiku 5.5 reranking."""
    blocks = []
    for ch in candidate_chunks:
        blocks.append(
            f"CHUNK_ID: {ch['chunk_id']} | BM25_RANK: #{ch['bm25_rank']} ({ch['bm25_score']}) | "
            f"DOC: {ch['doc_code']} — {ch['doc_title']} | CLAUSE: {ch['clause_ref']}\n"
            f"HEADING: {ch['section_heading']}\n"
            f"EXCERPT:\n{ch['text']}"
        )
    return (
        f"=== DUE-DILIGENCE QUERY ===\n{query}\n\n"
        f"=== CANDIDATE CHUNKS TO RERANK (Select the exact {RERANK_TOP_K} most decisive chunks) ===\n\n"
        + "\n\n---\n\n".join(blocks)
    )


def merge_rerank_funnel(
    *,
    bm25_ranked: list[dict[str, Any]],
    reranker_structured: dict[str, Any] | None,
    expected_chunk_ids: list[str],
    top_k_rerank: int = RERANK_TOP_K,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float | None, float | None]:
    """Apply Haiku reranker picks onto BM25 ranked chunks and compute stage recall metrics."""
    expected_set = set(expected_chunk_ids)
    candidates = [c for c in bm25_ranked if c["is_bm25_candidate"]]
    cand_by_id = {c["chunk_id"]: c for c in candidates}

    selected_meta: dict[str, tuple[int, str]] = {}
    selected_order: list[str] = []

    for entry in (reranker_structured or {}).get("selected_chunks") or []:
        cid = str(entry.get("chunk_id") or "").strip()
        if cid in cand_by_id and cid not in selected_meta:
            score = max(0, min(100, int(entry.get("relevance_score") or 80)))
            rationale = str(entry.get("rationale") or "Selected by Haiku reranker")[:140]
            selected_meta[cid] = (score, rationale)
            selected_order.append(cid)
            if len(selected_order) >= top_k_rerank:
                break

    # Deterministic backfill if Haiku returned fewer than top_k_rerank valid IDs
    for c in candidates:
        if len(selected_order) >= top_k_rerank:
            break
        cid = c["chunk_id"]
        if cid not in selected_meta:
            selected_meta[cid] = (65, "Backfilled from top BM25 candidate rank")
            selected_order.append(cid)

    selected_set = set(selected_order)
    selected_chunks = [cand_by_id[cid] for cid in selected_order]

    funnel: list[dict[str, Any]] = []
    for c in bm25_ranked:
        cid = c["chunk_id"]
        if cid in selected_set:
            stage = "selected_by_reranker"
            r_score, r_rat = selected_meta[cid]
        elif c["is_bm25_candidate"]:
            stage = "pruned_by_reranker"
            r_score, r_rat = None, "Pruned after cross-chunk rerank (outside top 5)"
        else:
            stage = "pruned_by_bm25"
            r_score, r_rat = None, None
        funnel.append(
            {
                "chunk_id": cid,
                "doc_id": c["doc_id"],
                "doc_title": f"{c['doc_code']} · {c['doc_title']}",
                "clause_ref": c["clause_ref"],
                "section_heading": c["section_heading"],
                "char_count": c["char_count"],
                "approx_tokens": c["approx_tokens"],
                "bm25_score": c["bm25_score"],
                "bm25_rank": c["bm25_rank"],
                "stage": stage,
                "reranker_score": r_score,
                "reranker_rationale": r_rat,
                "is_expected_gold": cid in expected_set,
            }
        )

    bm25_recall: float | None = None
    rerank_recall: float | None = None
    if expected_set:
        bm25_ids = {c["chunk_id"] for c in candidates}
        bm25_recall = round((len(expected_set & bm25_ids) / len(expected_set)) * 100, 1)
        rerank_recall = round((len(expected_set & selected_set) / len(expected_set)) * 100, 1)

    return selected_chunks, funnel, bm25_recall, rerank_recall
