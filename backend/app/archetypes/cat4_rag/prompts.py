"""System prompts & SDK Inspector code snippets for Category 4 Multi-Doc RAG."""

from __future__ import annotations


def get_cat4_synthesis_system_prompt(with_citations: bool) -> str:
    """High-signal executive due-diligence synthesis prompt across all 3 rungs."""
    cite_rule = (
        "- Rely ONLY on claims directly supported in the attached `document` blocks so native Anthropic citations anchor cleanly to exact contract clauses."
        if with_citations
        else "- Cite exact Document Codes (e.g., MSA-NM-DSA-2026, SLA-PEAK-2026, DPA-DPDP-2026, REG-BIS-EPR-2026, TAX-GST-ITC-2026, MCA-AOC4-FY26, SL-2026-09) and Clause IDs inline."
    )
    return (
        "You are NovaMart Enterprise's Senior Supplier Deal-Room Due Diligence Counsel & Financial Analyst.\n"
        "Answer the executive diligence question concisely in 150–230 words using EXACTLY 4 structured bullets:\n"
        "- **Verdict / Controlling Rule**: Direct yes/no or overriding instrument hierarchy.\n"
        "- **Key Clauses & Override Mechanics**: Exact clause IDs, timelines, and legal/technical mechanisms.\n"
        "- **Quantified Financial / Statutory Exposure**: Exact INR/Crore/USD figures, percentages, and statutory sections (DPDP Act 2023, CERT-In 2022, MSMED Sec 15 / 43B(h), CGST Sec 16(2)(aa) / Rule 37A, BIS/CPCB/UN 3480, MCA AOC-4 / CARO 2020 / Form CHG-1).\n"
        "- **Required Sign-Off Gate**: Concrete operational, banking NOC, escrow, or delisting gate before execution.\n"
        f"{cite_rule}\n"
        "- Never invent figures, clauses, or dates not explicitly present in the provided deal-room text."
    )


def get_cat4_haiku_reranker_system_prompt() -> str:
    """System prompt for Stage-2 Haiku 5.5 cross-chunk reranker."""
    return (
        "You are NovaMart's Stage-2 Legal & Statutory RAG Reranker.\n"
        "From the 10 BM25 candidate contract chunks, select the EXACT 5 most decisive chunks needed to answer the query completely.\n"
        "Rules:\n"
        "1. Prioritize controlling overrides (Addendum A Peak overrides, Side Letter #2 SL.1–SL.4, Clause 9.2 carve-outs) AND their corresponding baseline clauses when both are asked.\n"
        "2. Return exact chunk_id strings matching `CHUNK_ID:` (e.g., `DOC-07#c01`) sorted from highest to lowest relevance_score (0–100).\n"
        "3. Keep each rationale <= 12 words."
    )


CAT4_CODE_SNIPPETS: dict[str, str] = {
    "naive_full_corpus": """# RUNG 1 ANTI-PATTERN: Uncached Full-Corpus Stuffing (the whole corpus is re-billed on every query)
# Sends all 7 Deal-Room documents as plain text on every question — no cache_control, no citations requested.
resp = await client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=4096,
    thinking={"type": "between_tools"},
    system=DILIGENCE_SYNTHESIS_PROMPT,
    messages=[{
        "role": "user",
        "content": f"=== FULL 7-DOC DEAL ROOM ===\\n{all_7_docs_text}\\n\\nQUESTION: {query}",
    }],
)""",
    "cached_full_corpus_citations": """# RUNG 2 LEVER 1: Document Block Prefix Caching + Native Citations
# Attaches cache_control on the 7th document block: the first query writes the prefix ($2.50/M), later queries
# within the cache lifetime read it ($0.10/M). Citations point at exact spans; they show where a claim came from.
doc_blocks = [
    {
        "type": "document",
        "title": doc["block_title"],
        "source": {"type": "text", "media_type": "text/plain", "data": doc["full_text"]},
        "citations": {"enabled": True},
        **({"cache_control": {"type": "ephemeral"}} if idx == len(docs) - 1 else {}),
    }
    for idx, doc in enumerate(deal_room_docs)
]
resp = await client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=4096,
    thinking={"type": "between_tools"},
    system=DILIGENCE_SYNTHESIS_PROMPT,
    messages=[{"role": "user", "content": [*doc_blocks, {"type": "text", "text": query}]}],
)
# IMPORTANT: Join TextBlock.text with "" (empty string) to preserve unbroken sentences around citations!""",
    "hybrid_rag_rerank_citations": """# RUNG 3 LEVER 2: Hybrid BM25 (28 -> 10) + Haiku 5.5 Rerank (10 -> 5) + Native Citations
# Sends only the 5 reranked chunks to Sonnet 5.5; a clause retrieval misses can't be cited or used.
bm25_top10 = rank_chunks_bm25(query, all_28_chunks, top_k=10)
rerank = await client.messages.create(
    model="claude-haiku-5-5",  # $0.10/M in · $0.50/M out (thinking disabled)
    max_tokens=800,
    thinking={"type": "disabled"},
    system=HAIKU_RERANKER_PROMPT,
    output_config={"format": {"type": "json_schema", "schema": RERANK_JSON_SCHEMA}},
    messages=[{"role": "user", "content": format_rerank_candidates(query, bm25_top10)}],
)
top5_doc_blocks = [as_document_block(chunk, citations=True) for chunk in pick_top5(rerank)]
resp = await client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=4096,
    thinking={"type": "between_tools"},
    system=DILIGENCE_SYNTHESIS_PROMPT,
    messages=[{"role": "user", "content": [*top5_doc_blocks, {"type": "text", "text": query}]}],
)""",
}
