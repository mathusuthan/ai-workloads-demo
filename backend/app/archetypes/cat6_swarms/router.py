"""FastAPI routes for Category 6: Multi-Agent Swarms & Auto Eng."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.archetypes.cat6_swarms.prompts import CAT6_CODE_SNIPPETS
from app.archetypes.cat6_swarms.runner import execute_cat6_run
from app.archetypes.cat6_swarms.sandbox_verifier import SANDBOX_SUITE_PREVIEW_SOURCE
from app.data.cat6_fixtures import CAT6_PRESETS, SHARED_REPO_PREFIX_MARKDOWN
from app.models import Cat6RunRequest, Cat6RunResponse

router = APIRouter(prefix="/api/cat6", tags=["category-6"])


@router.get("/presets")
async def get_cat6_presets() -> dict[str, object]:
    return {
        "presets": CAT6_PRESETS,
        "shared_repo_char_count": len(SHARED_REPO_PREFIX_MARKDOWN),
        "approx_shared_repo_tokens": max(1, round(len(SHARED_REPO_PREFIX_MARKDOWN) / 3.0)),
        "shared_repo_preview": SHARED_REPO_PREFIX_MARKDOWN,
        "sandbox_suite_source": SANDBOX_SUITE_PREVIEW_SOURCE,
        "code_snippets": CAT6_CODE_SNIPPETS,
    }


@router.post("/run", response_model=Cat6RunResponse)
async def run_cat6_endpoint(
    payload: Cat6RunRequest,
    request: Request,
) -> Cat6RunResponse:
    return await execute_cat6_run(payload, http_request=request)
