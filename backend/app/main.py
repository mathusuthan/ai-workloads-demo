"""FastAPI application entrypoint serving API endpoints and React SPA."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.archetypes.cat1_triage.router import router as cat1_router
from app.archetypes.cat2_drafting.router import router as cat2_router
from app.archetypes.cat3_assistants.router import router as cat3_router
from app.archetypes.cat4_rag.router import router as cat4_router
from app.archetypes.cat5_orchestration.router import router as cat5_router
from app.archetypes.cat6_swarms.router import router as cat6_router
from app.config import get_settings
from app.core.credit_shield import credit_shield
from app.core.trace_store import summarize_traces
from app.data.matrix_catalog import (
    ARCHETYPES_CATALOG,
    AUTONOMY_TIERS,
    FINOPS_RULES,
    NOVAMART_PROFILE,
    TOKEN_BANDS,
)

app = FastAPI(
    title="NovaMart AI Workload Archetypes Lab",
    version="1.0.0",
    description="Interactive FinOps & AI Architecture Lab across 6 Enterprise AI Archetypes.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cat1_router)
app.include_router(cat2_router)
app.include_router(cat3_router)
app.include_router(cat4_router)
app.include_router(cat5_router)
app.include_router(cat6_router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "novamart-ai-archetypes"}


@app.get("/api/system/status")
async def system_status() -> dict[str, object]:
    return credit_shield.status_snapshot()


@app.get("/api/traces/summary")
async def traces_summary() -> dict[str, object]:
    return summarize_traces()


@app.get("/api/archetypes")
async def list_archetypes() -> dict[str, object]:
    return {
        "enterprise": NOVAMART_PROFILE,
        "autonomy_tiers": AUTONOMY_TIERS,
        "token_bands": TOKEN_BANDS,
        "archetypes": ARCHETYPES_CATALOG,
        "finops_rules": FINOPS_RULES,
    }


# Serve compiled React SPA when frontend/dist exists (must stay AFTER all /api/* routes)
_settings = get_settings()
_dist_dir = _settings.frontend_dist_dir
_assets_dir = _dist_dir / "assets"

if _assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="static-assets")


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    settings = get_settings()
    dist_dir = settings.frontend_dist_dir
    index_file = dist_dir / "index.html"
    if not index_file.is_file():
        return {
            "message": "Frontend bundle not built yet. Run `npm run build` in frontend/.",
            "api_docs": "/docs",
        }
    requested = (dist_dir / full_path).resolve()
    if full_path and requested.is_file() and str(requested).startswith(str(dist_dir.resolve())):
        return FileResponse(str(requested))
    return FileResponse(str(index_file))
