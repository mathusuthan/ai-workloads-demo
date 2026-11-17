"""Capture real live Anthropic + Gemini Decision 1 traces into replays/cat1_golden_replays.json."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "NOVAMART_TRACES_DIR",
    str(Path(tempfile.gettempdir()) / "novamart_cat1_capture"),
)

from app.archetypes.cat1_triage.runner import execute_cat1_run  # noqa: E402
from app.archetypes.cat1_triage.schemas import get_questions_for_subtask, get_schema_for_subtask  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.core.anthropic_service import (  # noqa: E402
    run_haiku_calibrated,
    run_haiku_naive,
    run_sonnet_naive,
)
from app.core.gemini_decision_service import run_gemini_decision  # noqa: E402
from app.data.cat1_fixtures import CAT1_EXTRA_BATCH_ITEMS, CAT1_PRESETS  # noqa: E402
from app.models import Cat1RunRequest, RungId  # noqa: E402


async def capture_all(only_rung: RungId | None = None, refresh_prose_and_tkt02: bool = False) -> None:
    settings = get_settings()
    if not settings.anthropic_api_key or not settings.gemini_api_key:
        raise RuntimeError(
            "Both ANTHROPIC_API_KEY and GEMINI_API_KEY must be set in .env before capturing live replays."
        )

    out_path = settings.replays_dir / "cat1_golden_replays.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(out_path.read_text(encoding="utf-8")) if out_path.is_file() else {}
    captured: dict[str, dict] = {
        "presets": dict(existing.get("presets") or {}),
        "batch_items": dict(existing.get("batch_items") or {}),
    }

    for preset in CAT1_PRESETS:
        pid = preset["id"]
        if only_rung:
            target_rungs: list[RungId] = [only_rung]
        elif refresh_prose_and_tkt02:
            existing_rungs = (captured["presets"].get(pid) or {}).get("rungs") or {}
            target_rungs = (
                ["sonnet_naive", "haiku_naive"]
                if ("haiku_calibrated" in existing_rungs and "gemini_decision" in existing_rungs)
                else ["sonnet_naive", "haiku_naive", "haiku_calibrated", "gemini_decision"]
            )
        else:
            target_rungs = ["sonnet_naive", "haiku_naive", "haiku_calibrated", "gemini_decision"]

        print(f"Capturing live trace ({','.join(target_rungs)}) for {pid} ({preset['sub_task']})...")
        resp = await execute_cat1_run(
            Cat1RunRequest(
                preset_id=pid,
                sub_task=preset["sub_task"],
                rungs=target_rungs,
                mode="live",
            )
        )
        rungs_dict = dict((captured["presets"].get(pid) or {}).get("rungs") or {})
        for r in resp.results:
            if r.status != "ok":
                print(f"  WARNING {pid}/{r.rung_id} error: {r.error_message}")
                continue
            rungs_dict[r.rung_id] = {
                "model_id": r.model_id,
                "provider": r.provider,
                "latency_ms": r.latency_ms,
                "input_tokens": r.finops.input_tokens,
                "output_tokens": r.finops.output_tokens,
                "structured_output": r.structured_output,
                "raw_text_preview": r.raw_text_preview,
                "decision_probabilities": r.decision_probabilities,
            }
            print(
                f"  {r.rung_id}: in={r.finops.input_tokens}, out={r.finops.output_tokens}, "
                f"chars={len(r.raw_text_preview or '')}, lat={r.latency_ms}ms, $/1k=${r.finops.cost_per_1k_usd:.4f}"
            )
        captured["presets"][pid] = {"sub_task": preset["sub_task"], "rungs": rungs_dict}

    if not only_rung:
        for item in CAT1_EXTRA_BATCH_ITEMS:
            iid = item["id"]
            sub = item["sub_task"]
            b_prev = dict(captured["batch_items"].get(iid) or {})

            if refresh_prose_and_tkt02 and b_prev.get("haiku_decision") and b_prev.get("gemini_decision"):
                print(f"Capturing live naive prose + Gemini input_tokens for batch item {iid} ({sub})...")
                s_res, hn_res, g_res = await asyncio.gather(
                    run_sonnet_naive(item["payload"], sub, settings.anthropic_api_key),
                    run_haiku_naive(item["payload"], sub, settings.anthropic_api_key),
                    run_gemini_decision(item["payload"], get_questions_for_subtask(sub), settings.gemini_api_key),
                )
                b_prev.update(
                    {
                        "sonnet_input_tokens": s_res.input_tokens,
                        "sonnet_output_tokens": s_res.output_tokens,
                        "sonnet_latency_ms": s_res.latency_ms,
                        "sonnet_raw_text": s_res.raw_text,
                        "haiku_naive_input_tokens": hn_res.input_tokens,
                        "haiku_naive_output_tokens": hn_res.output_tokens,
                        "haiku_naive_latency_ms": hn_res.latency_ms,
                        "haiku_naive_raw_text": hn_res.raw_text,
                        "gemini_input_tokens": g_res.input_tokens,
                        "gemini_latency_ms": g_res.latency_ms,
                    }
                )
                print(
                    f"  {iid}: sonnet_out={s_res.output_tokens}, haiku_naive_out={hn_res.output_tokens}, gemini_in={g_res.input_tokens}"
                )
                captured["batch_items"][iid] = b_prev
            else:
                print(f"Capturing all 4 rungs for batch item {iid} ({sub})...")
                s_res, hn_res, h_res, g_res = await asyncio.gather(
                    run_sonnet_naive(item["payload"], sub, settings.anthropic_api_key),
                    run_haiku_naive(item["payload"], sub, settings.anthropic_api_key),
                    run_haiku_calibrated(item["payload"], sub, get_schema_for_subtask(sub), settings.anthropic_api_key),
                    run_gemini_decision(item["payload"], get_questions_for_subtask(sub), settings.gemini_api_key),
                )
                confs = [float(v.get("confidence", 0.0)) for v in g_res.decision_probabilities.values()]
                captured["batch_items"][iid] = {
                    "input_tokens": h_res.input_tokens,
                    "haiku_output_tokens": h_res.output_tokens,
                    "sonnet_input_tokens": s_res.input_tokens,
                    "sonnet_output_tokens": s_res.output_tokens,
                    "sonnet_latency_ms": s_res.latency_ms,
                    "sonnet_raw_text": s_res.raw_text,
                    "haiku_naive_input_tokens": hn_res.input_tokens,
                    "haiku_naive_output_tokens": hn_res.output_tokens,
                    "haiku_naive_latency_ms": hn_res.latency_ms,
                    "haiku_naive_raw_text": hn_res.raw_text,
                    "gemini_input_tokens": g_res.input_tokens,
                    "sonnet_est_output_tokens": s_res.output_tokens,
                    "haiku_decision": h_res.structured,
                    "gemini_decision": g_res.structured_summary,
                    "gemini_confidence": round(sum(confs) / max(1, len(confs)), 3),
                    "haiku_latency_ms": h_res.latency_ms,
                    "gemini_latency_ms": g_res.latency_ms,
                }

    out_path.write_text(json.dumps(captured, indent=2), encoding="utf-8")
    print(f"Saved live golden replays to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--only-rung", default=None, choices=["sonnet_naive", "haiku_naive", "haiku_calibrated", "gemini_decision"])
    parser.add_argument("--refresh-prose-and-tkt02", action="store_true")
    args = parser.parse_args()
    asyncio.run(capture_all(only_rung=args.only_rung, refresh_prose_and_tkt02=args.refresh_prose_and_tkt02))
