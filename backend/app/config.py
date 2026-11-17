"""Runtime configuration loader for NovaMart AI Workload Archetypes Lab."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Resolve key directories cleanly whether run from backend/, repo root, or Docker container
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_DIR = BACKEND_DIR.parent
WORKSPACE_ROOT_DIR = PROJECT_DIR.parent

# Load .env files in priority order (project .env overrides workspace fallback)
for env_candidate in (
    PROJECT_DIR / ".env",
    BACKEND_DIR / ".env",
    WORKSPACE_ROOT_DIR / ".env",
):
    if env_candidate.is_file():
        load_dotenv(env_candidate, override=False)


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    gemini_api_key: str
    author_passcode: str
    daily_live_budget_usd: float
    anthropic_sonnet_model: str
    anthropic_haiku_model: str
    gemini_decision_model: str
    frontend_dist_dir: Path
    replays_dir: Path
    traces_dir: Path


def get_settings() -> Settings:
    """Return current runtime settings read from environment / .env."""
    for env_candidate in (
        PROJECT_DIR / ".env",
        BACKEND_DIR / ".env",
        WORKSPACE_ROOT_DIR / ".env",
    ):
        if env_candidate.is_file():
            load_dotenv(env_candidate, override=False)

    # Support both GEMINI_API_KEY and GOOGLE_API_KEY if provided
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
    anthropic_key = os.getenv("ANTHROPIC_API_KEY") or ""

    dist_candidates = (
        PROJECT_DIR / "frontend" / "dist",
        BACKEND_DIR / "frontend_dist",
        Path("/app/frontend/dist"),
    )
    frontend_dist = next((p for p in dist_candidates if p.is_dir()), dist_candidates[0])

    traces_dir = Path(os.getenv("NOVAMART_TRACES_DIR") or (BACKEND_DIR / "traces"))

    return Settings(
        anthropic_api_key=anthropic_key.strip(),
        gemini_api_key=gemini_key.strip(),
        author_passcode=os.getenv("AUTHOR_PASSCODE", "").strip(),
        daily_live_budget_usd=float(os.getenv("DAILY_LIVE_BUDGET_USD", "2.00")),
        anthropic_sonnet_model=os.getenv("ANTHROPIC_SONNET_MODEL", "claude-sonnet-5-5").strip(),
        anthropic_haiku_model=os.getenv("ANTHROPIC_HAIKU_MODEL", "claude-haiku-5-5").strip(),
        gemini_decision_model=os.getenv("GEMINI_DECISION_MODEL", "gemini-decision-1").strip(),
        frontend_dist_dir=frontend_dist,
        replays_dir=BACKEND_DIR / "replays",
        traces_dir=traces_dir,
    )
