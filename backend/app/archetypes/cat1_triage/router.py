"""FastAPI router for Category 1: Classification, Extraction & Routing."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.archetypes.cat1_triage.prompts import CODE_SNIPPETS
from app.archetypes.cat1_triage.runner import execute_cat1_batch, execute_cat1_run
from app.archetypes.cat1_triage.schemas import SKU_TAGGING_JSON_SCHEMA, SUPPORT_TRIAGE_JSON_SCHEMA
from app.data.cat1_fixtures import CAT1_PRESETS
from app.models import Cat1BatchRequest, Cat1BatchResponse, Cat1RunRequest, Cat1RunResponse

router = APIRouter(prefix="/api/cat1", tags=["Category 1"])


@router.get("/presets")
async def get_cat1_presets() -> dict[str, object]:
    return {
        "presets": CAT1_PRESETS,
        "schemas": {
            "support_triage": SUPPORT_TRIAGE_JSON_SCHEMA,
            "sku_tagging": SKU_TAGGING_JSON_SCHEMA,
        },
        "code_snippets": CODE_SNIPPETS,
    }


@router.post("/run", response_model=Cat1RunResponse)
async def run_cat1(req: Cat1RunRequest, request: Request) -> Cat1RunResponse:
    return await execute_cat1_run(req, http_request=request)


@router.post("/batch", response_model=Cat1BatchResponse)
async def run_cat1_batch(req: Cat1BatchRequest, request: Request) -> Cat1BatchResponse:
    return await execute_cat1_batch(req, http_request=request)
