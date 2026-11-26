"""Capture real live Claude 5.5 Category 5 traces into replays/cat5_golden_replays.json."""

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
    str(Path(tempfile.gettempdir()) / "novamart_cat5_capture"),
)

from app.archetypes.cat5_orchestration.runner import _run_live_cat5_for_rung  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.data.cat5_fixtures import CAT5_PRESETS  # noqa: E402
from app.models import Cat5RungId, Cat5RungResult  # noqa: E402

RUNGS: list[Cat5RungId] = [
    "unbounded_sonnet_loop",
    "bounded_sonnet_cached_gate",
    "hybrid_haiku_sonnet_governed",
    "unbounded_haiku_loop",
]


CACHED_RUNGS: frozenset[str] = frozenset(
    {"bounded_sonnet_cached_gate", "hybrid_haiku_sonnet_governed"}
)


def _validate_rung(
    preset: dict[str, Any],
    rid: Cat5RungId,
    res: Cat5RungResult,
    raw_rung: dict[str, Any],
) -> str | None:
    """Return a reason to re-capture a rung, or None to keep it.

    Only infrastructure problems are grounds for rejection:

    * the run did not finish with status ``ok`` (API error, timeout, exception);
    * the last model turn was truncated at ``max_tokens`` (its tool calls were
      never executed, so the trajectory is incomplete through no fault of the
      model's choices);
    * on the cached rungs, the prompt cache did not engage (no cache write or
      read on the first turn, or no cache read on any later turn).

    Outcomes are deliberately NOT checked. Earlier versions re-captured a rung
    until the voucher matched exactly, recall/precision hit 100%, the hybrid
    rung escalated as "expected" and the naive rung burned more than 25k prompt
    tokens. That kept only the runs that told the intended story and made the
    recorded replays a selected sample. The Category 5 ablation keeps every
    run; this capture script now does the same, so a wrong voucher, a missed
    escalation or a cheap naive run is recorded as it happened.
    """
    del preset  # outcome expectations live in the preset; they are not used here
    if res.status != "ok":
        return f"status={res.status} error={res.error_message}"
    steps = raw_rung.get("steps") or []
    if not steps:
        return "no model turns recorded"
    if steps[-1].get("stop_reason") == "max_tokens":
        return "last turn truncated at max_tokens"
    if rid in CACHED_RUNGS:
        s0 = steps[0]
        if int(s0.get("cache_creation_tokens") or 0) + int(s0.get("cache_read_tokens") or 0) <= 0:
            return "cached rung: first turn shows no cache write or read"
        if len(steps) >= 2 and not any(
            int(st.get("cache_read_tokens") or 0) > 0 for st in steps[1:]
        ):
            return "cached rung: no cache read on any turn after the first"
    return None


async def capture_cat5() -> None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY must be set in .env before capturing Cat 5 replays."
        )

    out_path = settings.replays_dir / "cat5_golden_replays.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(out_path.read_text(encoding="utf-8")) if out_path.is_file() else {}
    captured: dict[str, Any] = {"presets": dict(existing.get("presets") or {})}

    from app.archetypes.cat5_orchestration.runner import _build_cat5_result_from_replay

    for preset in CAT5_PRESETS:
        pid = preset["id"]
        existing_rungs: dict[str, Any] = dict(
            ((captured["presets"].get(pid) or {}).get("rungs")) or {}
        )

        missing_rungs: list[Cat5RungId] = []
        for rid in RUNGS:
            if rid not in existing_rungs:
                missing_rungs.append(rid)
                continue
            built = _build_cat5_result_from_replay(
                rung_id=rid,
                preset=preset,
                raw_rung=existing_rungs[rid],
            )
            if _validate_rung(preset, rid, built, existing_rungs[rid]) is not None:
                missing_rungs.append(rid)

        if not missing_rungs:
            print(f"[Cat 5] Reusing valid 3-rung captures for {pid}...")
            continue

        print(f"[Cat 5] Capturing {missing_rungs} live SQLite loops for {pid} ({preset['invoice_id']})...")

        async def _cap_rung(rid: Cat5RungId) -> tuple[Cat5RungId, Cat5RungResult, dict[str, Any]]:
            res, raw_rec = await _run_live_cat5_for_rung(
                preset=preset,
                rung_id=rid,
                api_key=settings.anthropic_api_key,
            )
            return rid, res, raw_rec

        rung_outputs = await asyncio.gather(*(_cap_rung(r) for r in missing_rungs))
        rungs_payload: dict[str, Any] = dict(existing_rungs)
        errors: list[str] = []

        for rid, res, raw_rec in rung_outputs:
            ev = res.evaluation
            acc_str = f"{ev.matched_fields}/{ev.total_fields} ({ev.field_accuracy_pct}%)" if ev else "None"
            rec_str = f"recall={ev.evidence_recall_pct}% prec={ev.tool_precision_pct}%" if ev else ""
            tot_prompt = (
                res.total_uncached_input_tokens
                + res.total_cache_creation_tokens
                + res.total_cache_read_tokens
            )
            print(
                f"  [{pid}/{rid}] steps={res.steps_used} (H:{res.haiku_steps}/S:{res.sonnet_steps} esc={res.escalated_to_sonnet}) "
                f"| prompt={tot_prompt:,} (in={res.total_uncached_input_tokens:,} cw={res.total_cache_creation_tokens:,} cr={res.total_cache_read_tokens:,}) "
                f"| out={res.total_output_tokens:,} | cold=${res.cost_per_1k_invoices_cold_usd:.2f}/1k warm=${res.cost_per_1k_invoices_warm_usd:.2f}/1k "
                f"| acc={acc_str} {rec_str}"
            )
            err = _validate_rung(preset, rid, res, raw_rec)
            if err:
                errors.append(f"{pid}/{rid}: {err}")
            else:
                rungs_payload[rid] = raw_rec

        if rungs_payload:
            captured["presets"][pid] = {
                "use_case": "invoice_3way_reconciliation",
                "rungs": rungs_payload,
            }
            out_path.write_text(json.dumps(captured, indent=2), encoding="utf-8")
            print(f"Checkpointed valid rungs {list(rungs_payload.keys())} for {pid} to {out_path}")

        if errors:
            raise RuntimeError(" ; ".join(errors))

    print(f"Saved live Category 5 golden replays to {out_path}")


if __name__ == "__main__":
    asyncio.run(capture_cat5())
