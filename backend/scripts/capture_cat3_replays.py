"""Capture real live Claude Sonnet 5.5 multi-turn Category 3 traces into replays/cat3_golden_replays.json."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("NOVAMART_TRACES_DIR", str(Path(tempfile.gettempdir()) / "novamart_cat3_capture"))

from app.archetypes.cat3_assistants.runner import _run_live_cat3_session_for_rung  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.data.cat3_fixtures import CAT3_PRESETS  # noqa: E402
from app.models import Cat3RungId  # noqa: E402

RUNGS: list[Cat3RungId] = [
    "naive_full_history",
    "prefix_cached_summarized",
]


def _validate_rung(rid: Cat3RungId, raw_turns: list[dict[str, Any]], expected_turns: int) -> str | None:
    if len(raw_turns) != expected_turns:
        return f"expected {expected_turns} turns, got {len(raw_turns)}"
    for t in raw_turns:
        if t.get("stop_reason") != "end_turn":
            return f"Turn {t.get('turn_number')} stop_reason={t.get('stop_reason')}"
        if rid == "prefix_cached_summarized":
            cw = int(t.get("cache_creation_tokens") or 0)
            cr = int(t.get("cache_read_tokens") or 0)
            if cw + cr < 4096:
                return f"Turn {t.get('turn_number')} below 4,096-tok cache floor (cw={cw}, cr={cr})"
            if int(t.get("turn_number") or 0) >= 2 and cr < 4096:
                return f"Turn {t.get('turn_number')} missed prefix cache read (cw={cw}, cr={cr})"
    return None


async def capture_cat3() -> None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY must be set in .env before capturing Cat 3 replays.")

    out_path = settings.replays_dir / "cat3_golden_replays.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(out_path.read_text(encoding="utf-8")) if out_path.is_file() else {}
    captured: dict[str, Any] = {"presets": dict(existing.get("presets") or {})}

    for preset in CAT3_PRESETS:
        pid = preset["id"]
        expected_turns = len(preset["turns"])
        existing_rungs: dict[str, Any] = dict(((captured["presets"].get(pid) or {}).get("rungs")) or {})

        missing_rungs = [
            rid
            for rid in RUNGS
            if _validate_rung(rid, existing_rungs.get(rid) or [], expected_turns) is not None
        ]
        if not missing_rungs:
            print(f"[Cat 3] Reusing valid 10-turn captures for {pid}...")
            continue

        print(f"[Cat 3] Capturing {missing_rungs} x {expected_turns} turns concurrently for {pid} on Sonnet 5.5...")

        async def _cap_rung(rid: Cat3RungId) -> tuple[Cat3RungId, Any, list[dict[str, Any]]]:
            summary, raw_turns = await _run_live_cat3_session_for_rung(
                preset=preset,
                rung_id=rid,
                api_key=settings.anthropic_api_key,
            )
            return rid, summary, raw_turns

        rung_outputs = await asyncio.gather(*(_cap_rung(r) for r in missing_rungs))
        rungs_payload: dict[str, list[dict[str, Any]]] = dict(existing_rungs)
        errors: list[str] = []

        for rid, summary, raw_turns in rung_outputs:
            print(
                f"  [{pid}/{rid}] model={summary.model_id} | in={summary.total_uncached_input_tokens:,} "
                f"| cw={summary.total_cache_creation_tokens:,} | cr={summary.total_cache_read_tokens:,} "
                f"| out={summary.total_output_tokens:,} | sum_calls={summary.summarizer_calls} "
                f"(${summary.summarizer_cost_usd:.4f}) | total=${summary.total_session_cost_usd:.4f} "
                f"| warm=${summary.warm_fleet_session_cost_usd:.4f} (${summary.cost_per_1k_sessions_usd:.2f}/1k)"
            )
            err = _validate_rung(rid, raw_turns, expected_turns)
            if err:
                errors.append(f"{pid}/{rid}: {err}")
            else:
                rungs_payload[rid] = raw_turns

        if rungs_payload:
            captured["presets"][pid] = {
                "use_case": preset["use_case"],
                "rungs": rungs_payload,
            }
            out_path.write_text(json.dumps(captured, indent=2), encoding="utf-8")
            print(f"Checkpointed valid rungs {list(rungs_payload.keys())} for {pid} to {out_path}")

        if errors:
            raise RuntimeError(" ; ".join(errors))

    print(f"Saved live Category 3 golden replays to {out_path}")


if __name__ == "__main__":
    asyncio.run(capture_cat3())
