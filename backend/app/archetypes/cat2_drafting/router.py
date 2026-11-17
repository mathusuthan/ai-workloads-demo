"""FastAPI router for Category 2: Generative Synthesis & Drafting."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.archetypes.cat2_drafting.prompts import CAT2_CODE_SNIPPETS
from app.archetypes.cat2_drafting.runner import (
    execute_cat2_run,
    execute_cat2_section_regen,
)
from app.archetypes.cat2_drafting.schemas import STRUCTURED_DRAFT_JSON_SCHEMA
from app.data.cat2_fixtures import CAT2_PRESETS, CAT2_REVIEWER_PRESETS
from app.models import (
    Cat2RunRequest,
    Cat2RunResponse,
    Cat2SectionRegenRequest,
    Cat2SectionRegenResponse,
)

router = APIRouter(prefix="/api/cat2", tags=["Category 2"])


@router.get("/presets")
async def get_cat2_presets() -> dict[str, object]:
    return {
        "presets": CAT2_PRESETS,
        "schema": STRUCTURED_DRAFT_JSON_SCHEMA,
        "reviewer_presets": CAT2_REVIEWER_PRESETS,
        "code_snippets": CAT2_CODE_SNIPPETS,
    }


@router.post("/run", response_model=Cat2RunResponse)
async def run_cat2(req: Cat2RunRequest, request: Request) -> Cat2RunResponse:
    return await execute_cat2_run(req, http_request=request)


@router.post("/regenerate-section", response_model=Cat2SectionRegenResponse)
async def regenerate_cat2_section(
    req: Cat2SectionRegenRequest,
    request: Request,
) -> Cat2SectionRegenResponse:
    return await execute_cat2_section_regen(req, http_request=request)
