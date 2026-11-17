"""Capture real live Anthropic Category 2 traces into replays/cat2_golden_replays.json."""

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

# Keep scratch capture traces out of backend/traces until seed_traces_from_replays.py runs
os.environ.setdefault("NOVAMART_TRACES_DIR", str(Path(tempfile.gettempdir()) / "novamart_cat2_capture"))

from app.archetypes.cat2_drafting.runner import (  # noqa: E402
    execute_cat2_run,
    execute_cat2_section_regen,
)
from app.config import get_settings  # noqa: E402
from app.data.cat2_fixtures import CAT2_PRESETS, CAT2_REVIEWER_PRESETS  # noqa: E402
from app.models import (  # noqa: E402
    Cat2ModelTier,
    Cat2RunRequest,
    Cat2SectionKey,
    Cat2SectionRegenRequest,
)

SECTIONS: list[Cat2SectionKey] = [
    "executive_summary",
    "key_findings",
    "risk_and_compliance_matrix",
    "action_plan",
]
TIERS: list[Cat2ModelTier] = ["claude-sonnet-5-5", "claude-haiku-5-5"]


async def capture_cat2() -> None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY must be set in .env before capturing Cat 2 replays.")

    out_path = settings.replays_dir / "cat2_golden_replays.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(out_path.read_text(encoding="utf-8")) if out_path.is_file() else {}
    captured: dict[str, Any] = {
        "presets": dict(existing.get("presets") or {}),
        "section_regens": dict(existing.get("section_regens") or {}),
    }

    # Part 1: Capture 3-Rung Synthesis Arena for all 4 presets (checkpoint after each preset)
    for preset in CAT2_PRESETS:
        pid = preset["id"]
        existing_rungs = dict(((captured["presets"].get(pid) or {}).get("rungs")) or {})
        missing_rungs = [
            k
            for k in ("sonnet_unbounded", "sonnet_templated", "haiku_templated")
            if k not in existing_rungs
            or (
                k == "sonnet_unbounded"
                and (
                    existing_rungs[k].get("output_tokens") == 4500
                    or existing_rungs[k].get("stop_reason") != "end_turn"
                )
            )
        ]

        rungs_dict: dict[str, Any] = dict(existing_rungs)
        changed_metadata = False
        for k in ("sonnet_templated", "haiku_templated"):
            if k in rungs_dict and rungs_dict[k].get("stop_reason") != "end_turn":
                rungs_dict[k] = {**rungs_dict[k], "stop_reason": "end_turn"}
                changed_metadata = True

        if not missing_rungs:
            if changed_metadata:
                captured["presets"][pid] = {"sub_task": preset["sub_task"], "rungs": rungs_dict}
                out_path.write_text(json.dumps(captured, indent=2), encoding="utf-8")
            print(f"[Part 1] Reusing existing captured rungs for {pid}...")
            continue

        print(f"[Part 1] Capturing missing/updated rungs {missing_rungs} for {pid} ({preset['sub_task']})...")
        resp = await execute_cat2_run(
            Cat2RunRequest(
                preset_id=pid,
                sub_task=preset["sub_task"],
                rungs=missing_rungs,
                mode="live",
            )
        )
        for r in resp.results:
            if r.status != "ok":
                raise RuntimeError(f"Live capture failed on {pid}/{r.rung_id}: {r.error_message}")
            if r.rung_id == "sonnet_unbounded" and r.finops.output_tokens >= 8000:
                raise RuntimeError(
                    f"Live capture for {pid}/sonnet_unbounded hit max_tokens ceiling "
                    f"({r.finops.output_tokens} out tokens)"
                )
            rungs_dict[r.rung_id] = {
                "model_id": r.model_id,
                "provider": r.provider,
                "latency_ms": r.latency_ms,
                "input_tokens": r.finops.input_tokens,
                "output_tokens": r.finops.output_tokens,
                "thinking_tokens": r.thinking_tokens,
                "stop_reason": "end_turn",
                "structured_draft": r.structured_draft,
                "raw_markdown": r.raw_markdown,
            }
            print(
                f"  {r.rung_id}: model={r.model_id}, in={r.finops.input_tokens}, "
                f"out={r.finops.output_tokens}, out_share={r.finops.output_cost_share_pct}%, "
                f"$/1k=${r.finops.cost_per_1k_usd:.2f}, lat={r.latency_ms}ms, chars={len(r.raw_markdown or '')}"
            )
        captured["presets"][pid] = {"sub_task": preset["sub_task"], "rungs": rungs_dict}
        out_path.write_text(json.dumps(captured, indent=2), encoding="utf-8")

    # Part 2: Capture Surgical HITL Section Regenerations (4 presets x 4 sections x 2 tiers = 32 calls)
    sem = asyncio.Semaphore(4)

    async def _cap_regen(preset: dict[str, Any], sec: Cat2SectionKey, tier: Cat2ModelTier) -> tuple[str, Cat2SectionKey, Cat2ModelTier, dict[str, Any]]:
        pid = preset["id"]
        existing_regen = (((captured["section_regens"].get(pid) or {}).get(sec)) or {}).get(tier)
        if existing_regen and existing_regen.get("updated_section"):
            return pid, sec, tier, existing_regen
        prior_sec = captured["presets"][pid]["rungs"]["sonnet_templated"]["structured_draft"].get(sec, {})
        instruction = CAT2_REVIEWER_PRESETS[sec]["instruction"]
        async with sem:
            res = await execute_cat2_section_regen(
                Cat2SectionRegenRequest(
                    preset_id=pid,
                    sub_task=preset["sub_task"],
                    section_key=sec,
                    current_section=prior_sec,
                    reviewer_instruction=instruction,
                    model_tier=tier,
                    mode="live",
                )
            )
        fin = res.finops_comparison.surgical_finops
        return pid, sec, tier, {
            "model_id": res.model_used,
            "latency_ms": res.latency_ms,
            "input_tokens": fin.input_tokens,
            "output_tokens": fin.output_tokens,
            "prior_section": prior_sec,
            "updated_section": res.updated_section,
        }

    print("[Part 2] Capturing 32 surgical HITL section regenerations (concurrency=4)...")
    tasks = [_cap_regen(p, s, t) for p in CAT2_PRESETS for s in SECTIONS for t in TIERS]
    regen_results = await asyncio.gather(*tasks)
    for pid, sec, tier, payload in regen_results:
        captured["section_regens"].setdefault(pid, {}).setdefault(sec, {})[tier] = payload
        print(
            f"  regen {pid}/{sec}/{tier}: in={payload['input_tokens']}, out={payload['output_tokens']}, lat={payload['latency_ms']}ms"
        )

    out_path.write_text(json.dumps(captured, indent=2), encoding="utf-8")
    print(f"Saved live Category 2 golden replays to {out_path}")


if __name__ == "__main__":
    asyncio.run(capture_cat2())
