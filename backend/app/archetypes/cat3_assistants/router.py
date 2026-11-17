"""FastAPI routes for Category 3: Multi-Turn Conversational Assistants."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.archetypes.cat3_assistants.prompts import CAT3_CODE_SNIPPETS
from app.archetypes.cat3_assistants.runner import execute_cat3_chat_turn, execute_cat3_run
from app.archetypes.cat3_assistants.schemas import SESSION_MEMORY_JSON_SCHEMA
from app.data.cat3_fixtures import CAT3_PRESETS, IT_HR_HANDBOOK_MARKDOWN
from app.models import (
    Cat3ChatTurnRequest,
    Cat3ChatTurnResponse,
    Cat3RunRequest,
    Cat3RunResponse,
)

router = APIRouter(prefix="/api/cat3", tags=["category-3"])


@router.get("/presets")
async def get_cat3_presets() -> dict[str, object]:
    return {
        "presets": CAT3_PRESETS,
        "handbook_preview": IT_HR_HANDBOOK_MARKDOWN,
        "handbook_char_count": len(IT_HR_HANDBOOK_MARKDOWN),
        "memory_schema": SESSION_MEMORY_JSON_SCHEMA,
        "code_snippets": CAT3_CODE_SNIPPETS,
    }


@router.post("/run", response_model=Cat3RunResponse)
async def run_cat3_endpoint(
    payload: Cat3RunRequest,
    request: Request,
) -> Cat3RunResponse:
    return await execute_cat3_run(payload, http_request=request)


@router.post("/chat-turn", response_model=Cat3ChatTurnResponse)
async def chat_turn_cat3_endpoint(
    payload: Cat3ChatTurnRequest,
    request: Request,
) -> Cat3ChatTurnResponse:
    return await execute_cat3_chat_turn(payload, http_request=request)
