"""Rebuild replays/cat6_golden_replays.json from the Category 6 fair-rerun records.

Fixed, pre-declared mapping (never chosen by outcome): repeat_index 0 of each arm below, for every preset.

    shared_bus_matched_gate -> unisolated_broadcast_swarm   (without the lever, Sonnet)
    isolated_cached_gate    -> isolated_cached_sonnet_swarm (with the lever, Sonnet)
    tiered_gate             -> tiered_hybrid_cpo_swarm      (with the lever, Haiku agents + Sonnet patch author)

The output keeps the schema `runner._build_cat6_result_from_replay` reads (the live path's `raw_record`),
adds `stop_reason`/`max_tokens` per turn and provenance, and stores `sandbox_report` as the current sandbox's
verdict on the recorded `patched_code_final` (the same verdict the records hold). The records file is only read.

Idempotent: if the rebuilt content equals the existing file (ignoring `provenance.rebuilt_at`), nothing is
written.

Usage (from backend/):
    .venv/bin/python scripts/build_cat6_golden_from_rerun.py [--in runs.jsonl] [--out replays/cat6_golden_replays.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat6_swarms.prompts import AGENT_ROLE_LABELS  # noqa: E402
from app.archetypes.cat6_swarms.sandbox_verifier import evaluate_patch_in_sandbox  # noqa: E402
from app.data.cat6_fixtures import CAT6_PRESETS  # noqa: E402

DEFAULT_IN = BACKEND_DIR / "experiments" / "cat6_fair_rerun" / "runs.jsonl"
DEFAULT_OUT = BACKEND_DIR / "replays" / "cat6_golden_replays.json"

# Pre-declared before looking at outcomes: app rung -> fair-rerun arm, always repeat 0.
GOLDEN_MAPPING: dict[str, str] = {
    "unisolated_broadcast_swarm": "shared_bus_matched_gate",
    "isolated_cached_sonnet_swarm": "isolated_cached_gate",
    "tiered_hybrid_cpo_swarm": "tiered_gate",
}
GOLDEN_REPEAT_INDEX = 0
USE_CASE = "checkout_ci_self_healing_swarm"
PROMPT_PREVIEW_CHARS = 450  # same truncation as runner._run_live_cat6_for_rung
OUTPUT_PREVIEW_CHARS = 2000


def _select(records: Iterable[dict[str, Any]], arm_id: str, preset_id: str) -> dict[str, Any]:
    """Latest ok record for (arm, preset, repeat 0) — same rule the analysis uses."""
    chosen = None
    for r in records:
        if (
            r.get("status") == "ok"
            and r.get("arm_id") == arm_id
            and r.get("preset_id") == preset_id
            and int(r.get("repeat_index", -1)) == GOLDEN_REPEAT_INDEX
        ):
            chosen = r
    if chosen is None:
        raise ValueError(f"No ok fair-rerun record for {arm_id} / {preset_id} / repeat {GOLDEN_REPEAT_INDEX}")
    return chosen


def convert_record(
    record: dict[str, Any],
    rung_id: str,
    *,
    sandbox: Callable[[str, str], dict[str, Any]] = evaluate_patch_in_sandbox,
) -> dict[str, Any]:
    """One fair-rerun record -> one golden-replay rung (the live path's raw_record schema)."""
    context_mode = "shared_omnibus_bus" if rung_id == "unisolated_broadcast_swarm" else "isolated_prefix_cached"
    turns = []
    for t in record["turns"]:
        role = str(t["agent_role"])
        turns.append(
            {
                "step_number": int(t["step_number"]),
                "agent_role": role,
                "agent_label": AGENT_ROLE_LABELS[role],
                "model_id": t["model_id"],
                "context_mode": context_mode,
                "attempt": int(t["attempt"]),
                "max_tokens": int(t["max_tokens"]),
                "stop_reason": t.get("stop_reason"),
                "latency_ms": int(t["latency_ms"]),
                "input_tokens": int(t["input_tokens"]),
                "output_tokens": int(t["output_tokens"]),
                "cache_creation_tokens": int(t["cache_creation_tokens"]),
                "cache_read_tokens": int(t["cache_read_tokens"]),
                "prompt_preview": str(t["user_message"])[:PROMPT_PREVIEW_CHARS],
                "output_preview": str(t["raw_text"])[:OUTPUT_PREVIEW_CHARS],
            }
        )
    patched = str(record.get("patched_code_final") or "")
    sandbox_report = sandbox(str(record["preset_id"]), patched)
    recorded_ms = (((record.get("final") or {}).get("sandbox") or {})).get("execution_ms")
    if recorded_ms is not None:
        # wall-clock time, not a verdict: keep the recorded value so rebuilds are deterministic
        sandbox_report = {**sandbox_report, "execution_ms": recorded_ms}
    return {
        "rung_id": rung_id,
        "primary_model_id": (
            "claude-haiku-5-5 + claude-sonnet-5-5" if rung_id == "tiered_hybrid_cpo_swarm" else "claude-sonnet-5-5"
        ),
        "retries_used": int(record.get("retries_used") or 0),
        "agent_turns": turns,
        "patched_code": patched,
        "final_signoff_memo": str(record.get("final_signoff_memo") or ""),
        "sandbox_report": sandbox_report,
        "provenance": {
            "arm_id": record["arm_id"],
            "repeat_index": int(record["repeat_index"]),
            "run_id": record["run_id"],
            "started_at": record.get("started_at"),
            "sandbox_report": "current sandbox on patched_code_final",
        },
    }


def build_golden(
    records: list[dict[str, Any]],
    *,
    source_file: str,
    preset_ids: Iterable[str] | None = None,
    sandbox: Callable[[str, str], dict[str, Any]] = evaluate_patch_in_sandbox,
) -> dict[str, Any]:
    """Golden-replay document without the rebuild timestamp (added by `write_golden`)."""
    pids = list(preset_ids) if preset_ids is not None else [p["id"] for p in CAT6_PRESETS]
    presets: dict[str, Any] = {}
    for pid in pids:
        presets[pid] = {
            "use_case": USE_CASE,
            "rungs": {
                rung_id: convert_record(_select(records, arm_id, pid), rung_id, sandbox=sandbox)
                for rung_id, arm_id in GOLDEN_MAPPING.items()
            },
        }
    return {
        "provenance": {
            "source": "cat6 fair rerun",
            "source_file": source_file,
            "mapping": {rung: {"arm_id": arm, "repeat_index": GOLDEN_REPEAT_INDEX} for rung, arm in GOLDEN_MAPPING.items()},
            "selection_rule": "fixed pre-declared mapping, repeat_index 0 for every preset (not selected by outcome)",
            "sandbox_report": "current sandbox on each record's patched_code_final",
        },
        "presets": presets,
    }


def _without_timestamp(doc: dict[str, Any]) -> dict[str, Any]:
    """Comparable form: drops provenance.rebuilt_at and each sandbox report's wall-clock execution_ms."""
    out = json.loads(json.dumps(doc))
    (out.get("provenance") or {}).pop("rebuilt_at", None)
    for p in (out.get("presets") or {}).values():
        for r in (p.get("rungs") or {}).values():
            (r.get("sandbox_report") or {}).pop("execution_ms", None)
    return out


def write_golden(doc: dict[str, Any], out_path: Path) -> bool:
    """Write `doc` (adding provenance.rebuilt_at) unless the file already holds the same content."""
    if out_path.is_file():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = None
        if existing is not None and _without_timestamp(existing) == _without_timestamp(doc):
            return False
    stamped = dict(doc)
    stamped["provenance"] = {
        **doc["provenance"],
        "rebuilt_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(stamped, indent=2), encoding="utf-8")
    return True


def load_records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="in_path", default=str(DEFAULT_IN))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)

    in_path = Path(args.in_path)
    try:
        source_file = str(in_path.resolve().relative_to(BACKEND_DIR))
    except ValueError:
        source_file = str(in_path)
    doc = build_golden(load_records(in_path), source_file=source_file)
    changed = write_golden(doc, Path(args.out))
    for pid, p in doc["presets"].items():
        for rid, r in p["rungs"].items():
            s = r["sandbox_report"]
            print(
                f"{pid} {rid:<30} <- {r['provenance']['arm_id']} r{r['provenance']['repeat_index']} "
                f"{r['provenance']['run_id'][:8]} | turns={len(r['agent_turns'])} retries={r['retries_used']} "
                f"| sandbox {s['passed_checks']}/{s['total_checks']} verified={s['verified_outcome']}"
            )
    print(f"{'Wrote' if changed else 'Unchanged:'} {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
