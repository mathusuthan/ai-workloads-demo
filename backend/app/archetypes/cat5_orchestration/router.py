"""FastAPI routes for Category 5: Autonomous Process Orchestration."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.archetypes.cat5_orchestration.erp_db import ERP_DDL_SCHEMA_SQL
from app.archetypes.cat5_orchestration.prompts import CAT5_CODE_SNIPPETS
from app.archetypes.cat5_orchestration.runner import execute_cat5_run
from app.data.cat5_fixtures import AP_POLICY_MANUAL_MARKDOWN, CAT5_PRESETS
from app.models import Cat5RunRequest, Cat5RunResponse

router = APIRouter(prefix="/api/cat5", tags=["category-5"])


@router.get("/presets")
async def get_cat5_presets() -> dict[str, object]:
    return {
        "presets": CAT5_PRESETS,
        "policy_char_count": len(AP_POLICY_MANUAL_MARKDOWN),
        "approx_policy_tokens": max(1, round(len(AP_POLICY_MANUAL_MARKDOWN) / 2.8)),
        "policy_manual_preview": AP_POLICY_MANUAL_MARKDOWN,
        "erp_ddl_schema": ERP_DDL_SCHEMA_SQL,
        "code_snippets": CAT5_CODE_SNIPPETS,
    }


@router.post("/run", response_model=Cat5RunResponse)
async def run_cat5_endpoint(
    payload: Cat5RunRequest,
    request: Request,
) -> Cat5RunResponse:
    return await execute_cat5_run(payload, http_request=request)
