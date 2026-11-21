"""Capture real live Claude 5.5 Category 6 swarm traces into replays/cat6_golden_replays.json."""

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

os.environ.setdefault(
    "NOVAMART_TRACES_DIR",
    str(Path(tempfile.gettempdir()) / "novamart_cat6_capture"),
)

from app.archetypes.cat6_swarms.runner import (  # noqa: E402
    _build_cat6_result_from_replay,
    _run_live_cat6_for_rung,
)
from app.config import get_settings  # noqa: E402
from app.data.cat6_fixtures import CAT6_PRESETS  # noqa: E402
from app.models import Cat6RungId, Cat6RungResult  # noqa: E402

RUNGS: list[Cat6RungId] = [
    "unisolated_broadcast_swarm",
    "isolated_cached_sonnet_swarm",
    "tiered_hybrid_cpo_swarm",
]


def _validate_rung(
    preset: dict[str, Any],
    rid: Cat6RungId,
    res: Cat6RungResult,
    raw_rung: dict[str, Any],
) -> str | None:
    if res.status != "ok":
        return f"status={res.status} error={res.error_message}"
    turns = raw_rung.get("agent_turns") or []
    if len(turns) < 5:
        return f"Expected >= 5 agent turns, got {len(turns)}"

    tot_prompt = (
        res.total_uncached_input_tokens
        + res.total_cache_creation_tokens
        + res.total_cache_read_tokens
    )
    if rid == "unisolated_broadcast_swarm":
        if not (res.patched_code or "").strip():
            return "Rung 1 failed to extract non-empty patched_code"
        if tot_prompt < 100_000:
            return f"Rung 1 below 100k Band 5 threshold (got {tot_prompt})"
        return None

    sbx = res.sandbox_report
    if not sbx or not sbx.verified_outcome:
        fails = [
            f"{c.check_id}:{c.detail[:120]}"
            for c in (sbx.checks if sbx else [])
            if not c.passed
        ]
        return f"Sandbox failed ({sbx.passed_checks if sbx else 0}/10): {fails}"

    t0 = turns[0]
    if int(t0.get("cache_creation_tokens") or 0) + int(t0.get("cache_read_tokens") or 0) < 4096:
        return "Turn 1 missed 4,096-token shared repo prefix cache floor"

    t1 = turns[1]
    if int(t1.get("cache_read_tokens") or 0) < 4096:
        return f"Turn 2 missed prefix cache hit on shared repo (cr={t1.get('cache_read_tokens')})"

    if rid == "tiered_hybrid_cpo_swarm":
        if res.haiku_turns < 4 or res.sonnet_turns < 1:
            return f"Expected >=4 Haiku turns and >=1 Sonnet turn, got H={res.haiku_turns}/S={res.sonnet_turns}"
        last_turn = turns[-1]
        if int(last_turn.get("cache_read_tokens") or 0) < 4096:
            return f"Final Haiku merge turn missed prefix cache read (cr={last_turn.get('cache_read_tokens')})"

    return None


async def capture_cat6() -> None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY must be set in .env before capturing Cat 6 replays."
        )

    out_path = settings.replays_dir / "cat6_golden_replays.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(out_path.read_text(encoding="utf-8")) if out_path.is_file() else {}
    captured: dict[str, Any] = {"presets": dict(existing.get("presets") or {})}

    for preset in CAT6_PRESETS:
        pid = preset["id"]
        existing_rungs: dict[str, Any] = dict(
            ((captured["presets"].get(pid) or {}).get("rungs")) or {}
        )
        missing_rungs: list[Cat6RungId] = []
        for rid in RUNGS:
            if rid not in existing_rungs:
                missing_rungs.append(rid)
                continue
            built = _build_cat6_result_from_replay(
                rung_id=rid,
                preset=preset,
                raw_rung=existing_rungs[rid],
            )
            if _validate_rung(preset, rid, built, existing_rungs[rid]) is not None:
                missing_rungs.append(rid)

        if not missing_rungs:
            print(f"[Cat 6] Reusing valid 3-rung captures for {pid} ({preset['pr_id']})...")
            continue

        print(f"[Cat 6] Capturing {missing_rungs} live swarm runs for {pid} ({preset['pr_id']})...")
        rungs_payload: dict[str, Any] = dict(existing_rungs)
        errors: list[str] = []

        for rid in missing_rungs:
            res, raw_rec = await _run_live_cat6_for_rung(
                preset=preset,
                rung_id=rid,
                api_key=settings.anthropic_api_key,
            )
            sbx = res.sandbox_report
            sbx_str = (
                f"{sbx.passed_checks}/{sbx.total_checks} verified={sbx.verified_outcome}"
                if sbx
                else "None"
            )
            tot_prompt = (
                res.total_uncached_input_tokens
                + res.total_cache_creation_tokens
                + res.total_cache_read_tokens
            )
            print(
                f"  [{pid}/{rid}] turns={len(res.agent_turns)} (H:{res.haiku_turns}/S:{res.sonnet_turns} retries={res.retries_used}) "
                f"| prompt={tot_prompt:,} (in={res.total_uncached_input_tokens:,} cw={res.total_cache_creation_tokens:,} cr={res.total_cache_read_tokens:,}) "
                f"| out={res.total_output_tokens:,} | CpR cold=${res.cost_per_1k_runs_cold_usd:.2f}/1k warm=${res.cost_per_1k_runs_warm_usd:.2f}/1k "
                f"| sandbox={sbx_str}"
            )
            err = _validate_rung(preset, rid, res, raw_rec)
            if err:
                errors.append(f"{pid}/{rid}: {err}")
            else:
                rungs_payload[rid] = raw_rec
                captured["presets"][pid] = {
                    "use_case": "checkout_ci_self_healing_swarm",
                    "rungs": rungs_payload,
                }
                out_path.write_text(json.dumps(captured, indent=2), encoding="utf-8")

        if rungs_payload:
            print(f"Checkpointed rungs {list(rungs_payload.keys())} for {pid} to {out_path}")

        if errors:
            raise RuntimeError(" ; ".join(errors))

    print(f"Saved live Category 6 golden replays to {out_path}")


if __name__ == "__main__":
    asyncio.run(capture_cat6())
