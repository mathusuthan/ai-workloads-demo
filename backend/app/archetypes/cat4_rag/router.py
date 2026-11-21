"""FastAPI routes for Category 4: Multi-Doc RAG & Deep Ingestion."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.archetypes.cat4_rag.prompts import CAT4_CODE_SNIPPETS
from app.archetypes.cat4_rag.runner import execute_cat4_adhoc_query, execute_cat4_run
from app.archetypes.cat4_rag.schemas import RERANK_JSON_SCHEMA
from app.data.cat4_fixtures import (
    CAT4_PRESETS,
    DEAL_ROOM_PROFILE,
    hydrate_deal_room_index,
)
from app.models import (
    Cat4AdhocQueryRequest,
    Cat4AdhocQueryResponse,
    Cat4RunRequest,
    Cat4RunResponse,
)

router = APIRouter(prefix="/api/cat4", tags=["category-4"])


@router.get("/presets")
async def get_cat4_presets() -> dict[str, object]:
    hydrated_docs, flat_chunks, total_chars = hydrate_deal_room_index()
    return {
        "deal_room_profile": DEAL_ROOM_PROFILE,
        "documents": [
            {
                "doc_index": d["doc_index"],
                "doc_id": d["doc_id"],
                "doc_code": d["doc_code"],
                "title": d["title"],
                "doc_type": d["doc_type"],
                "effective_date": d["effective_date"],
                "summary": d["summary"],
                "char_count": d["char_count"],
                "approx_tokens": d["approx_tokens"],
                "full_text": d["full_text"],
                "chunks": [
                    {
                        "chunk_id": c["chunk_id"],
                        "clause_ref": c["clause_ref"],
                        "section_heading": c["section_heading"],
                        "doc_char_start": c["doc_char_start"],
                        "doc_char_end": c["doc_char_end"],
                        "char_count": c["char_count"],
                        "approx_tokens": c["approx_tokens"],
                    }
                    for c in d["chunks"]
                ],
            }
            for d in hydrated_docs
        ],
        "total_docs": len(hydrated_docs),
        "total_chunks": len(flat_chunks),
        "corpus_char_count": total_chars,
        "approx_corpus_tokens": max(1, round(total_chars / 2.4)),
        "presets": CAT4_PRESETS,
        "rerank_schema": RERANK_JSON_SCHEMA,
        "code_snippets": CAT4_CODE_SNIPPETS,
    }


@router.post("/run", response_model=Cat4RunResponse)
async def run_cat4_endpoint(
    payload: Cat4RunRequest,
    request: Request,
) -> Cat4RunResponse:
    return await execute_cat4_run(payload, http_request=request)


@router.post("/query", response_model=Cat4AdhocQueryResponse)
async def query_cat4_endpoint(
    payload: Cat4AdhocQueryRequest,
    request: Request,
) -> Cat4AdhocQueryResponse:
    return await execute_cat4_adhoc_query(payload, http_request=request)
