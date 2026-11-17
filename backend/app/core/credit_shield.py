"""Credit Shield: protects author's API budget via Replay default, Passcode, Cap & BYOK."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from fastapi import HTTPException, Request
from app.config import get_settings
from app.core.pricing import rate_card_payload


@dataclass(frozen=True)
class ResolvedCredentials:
    anthropic_api_key: str | None
    gemini_api_key: str | None
    anthropic_source: str  # "byok" | "server_env" | "none"
    gemini_source: str     # "byok" | "server_env" | "none"
    uses_server_budget: bool


class CreditShield:
    """In-memory daily spend tracker and credential resolver."""

    def __init__(self) -> None:
        self._daily_spend_by_date: dict[str, float] = {}

    def _today_key(self) -> str:
        return date.today().isoformat()

    def get_today_spend(self) -> float:
        return round(self._daily_spend_by_date.get(self._today_key(), 0.0), 6)

    def record_server_spend(self, cost_usd: float) -> None:
        if cost_usd <= 0:
            return
        day = self._today_key()
        self._daily_spend_by_date[day] = self._daily_spend_by_date.get(day, 0.0) + cost_usd

    def resolve_live_credentials(
        self,
        request: Request | None,
        need_anthropic: bool,
        need_gemini: bool,
    ) -> ResolvedCredentials:
        settings = get_settings()

        byok_anthropic = (request.headers.get("X-Anthropic-Api-Key") or "").strip() if request else ""
        byok_gemini = (request.headers.get("X-Gemini-Api-Key") or "").strip() if request else ""
        passcode = (request.headers.get("X-Author-Passcode") or "").strip() if request else ""

        anthropic_key: str | None = byok_anthropic or None
        anthropic_source = "byok" if byok_anthropic else "none"
        gemini_key: str | None = byok_gemini or None
        gemini_source = "byok" if byok_gemini else "none"

        needs_server_key = (need_anthropic and not anthropic_key) or (need_gemini and not gemini_key)
        uses_server_budget = False

        if needs_server_key:
            if settings.author_passcode and passcode != settings.author_passcode:
                raise HTTPException(
                    status_code=402,
                    detail=(
                        "Live API calls using the server budget require the Author Passcode or your own "
                        "BYOK API keys in the Credit Shield modal. Or stay in Verified Replay mode ($0 cost)."
                    ),
                )

            if self.get_today_spend() >= settings.daily_live_budget_usd:
                raise HTTPException(
                    status_code=402,
                    detail=(
                        f"Server daily Credit Shield cap (${settings.daily_live_budget_usd:.2f}) reached. "
                        "Switch to Verified Replay mode ($0) or supply your own BYOK key in Credit Shield."
                    ),
                )

            if need_anthropic and not anthropic_key and settings.anthropic_api_key:
                anthropic_key = settings.anthropic_api_key
                anthropic_source = "server_env"
                uses_server_budget = True

            if need_gemini and not gemini_key and settings.gemini_api_key:
                gemini_key = settings.gemini_api_key
                gemini_source = "server_env"
                uses_server_budget = True

        missing: list[str] = []
        if need_anthropic and not anthropic_key:
            missing.append("ANTHROPIC_API_KEY")
        if need_gemini and not gemini_key:
            missing.append("GEMINI_API_KEY")

        if missing:
            raise HTTPException(
                status_code=402,
                detail=(
                    f"Missing live credentials for {', '.join(missing)}. "
                    "Add your key in the Credit Shield modal (BYOK, stored in sessionStorage only), "
                    "configure .env on the server, or run in Verified Replay mode ($0 cost)."
                ),
            )

        return ResolvedCredentials(
            anthropic_api_key=anthropic_key,
            gemini_api_key=gemini_key,
            anthropic_source=anthropic_source,
            gemini_source=gemini_source,
            uses_server_budget=uses_server_budget,
        )

    def status_snapshot(self) -> dict[str, object]:
        settings = get_settings()
        spent = self.get_today_spend()
        return {
            "default_mode": "replay",
            "server_keys": {
                "anthropic_configured": bool(settings.anthropic_api_key),
                "gemini_configured": bool(settings.gemini_api_key),
            },
            "author_passcode_required": bool(settings.author_passcode),
            "daily_budget_usd": settings.daily_live_budget_usd,
            "daily_spend_usd": round(spent, 4),
            "daily_remaining_usd": round(max(0.0, settings.daily_live_budget_usd - spent), 4),
            "rate_card": rate_card_payload(),
        }


credit_shield = CreditShield()
