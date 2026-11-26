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


CAT4_CODE_SNIPPETS: dict[str, str] = {
    "naive_full_corpus": """# WITHOUT: Uncached Full-Corpus Stuffing (the whole corpus is re-billed on every query)
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
    "cached_rerank_hybrid": """# WITH: Hybrid retrieval paired with context caching + native citations
# Haiku 5.5 reads all 28 deal-room clauses from one cached block (the first question writes it, later questions
# read it) and picks the 5 it judges most relevant; Sonnet 5.5 answers over those 5 only. A clause Haiku does not pick
# can't be cited or used.
rerank = await client.messages.create(
    model="claude-haiku-5-5",
    max_tokens=800,
    thinking={"type": "disabled"},
    system=HAIKU_FULL_CORPUS_RERANKER_PROMPT,
    output_config={"format": {"type": "json_schema", "schema": RERANK_JSON_SCHEMA}},
    messages=[{"role": "user", "content": [
        {"type": "text", "text": all_28_clauses_text, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": f"=== DUE-DILIGENCE QUERY ===\n{query}"},
    ]}],
)
top5_doc_blocks = [as_document_block(chunk, citations=True) for chunk in picked_clauses(rerank)]
resp = await client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=4096,
    thinking={"type": "between_tools"},
    system=DILIGENCE_SYNTHESIS_PROMPT_TEXT_PROVIDED,  # says when a term is not in the text provided
    messages=[{"role": "user", "content": [*top5_doc_blocks, {"type": "text", "text": query}]}],
)
# IMPORTANT: Join TextBlock.text with "" (empty string) to preserve unbroken sentences around citations!""",
}
