"""Rebuild replays/cat3_golden_replays.json and replays/cat3_quality_summary.json from the Category 3 quality rerun.

Golden replays — fixed, pre-declared mapping (never chosen by outcome): repeat_index 0 of every rung for
every session. Each rung keeps the turn-list schema `runner._build_cat3_summary_from_replay` reads (the live
path's raw capture), with real `stop_reason`s for turns and compactions. The probe phase (the probe-phase
compaction and the six recall Q/As with tokens) and provenance are stored as sibling keys under the preset
(`probe_phase`, `provenance`), which the existing reader ignores.

Quality summary — the full rerun (every latest ok record), pooled per rung and per rung x session, from the
same `quality_rerun.summarise()` code path as scripts/analyze_cat3_quality.py. The app reads it at runtime
because analysis/ and experiments/ are not in the Docker image.

The records file is only read. Idempotent: a file whose content is unchanged (ignoring
`provenance.rebuilt_at`) is not rewritten.

Usage (from backend/):
    .venv/bin/python scripts/build_cat3_golden_from_rerun.py [--in runs.jsonl]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat3_assistants.quality_rerun import (  # noqa: E402
    RUNG_IDS,
    build_quality_portfolio,
    load_quality_keys,
    summarise,
)
from app.data.cat3_fixtures import CAT3_PRESETS  # noqa: E402

DEFAULT_IN = BACKEND_DIR / "experiments" / "cat3_quality" / "runs.jsonl"
DEFAULT_OUT = BACKEND_DIR / "replays" / "cat3_golden_replays.json"
DEFAULT_SUMMARY_OUT = BACKEND_DIR / "replays" / "cat3_quality_summary.json"
GOLDEN_REPEAT_INDEX = 0
USE_CASE = "it_hr_service_desk"

_USAGE_FIELDS = ("input_tokens", "output_tokens", "thinking_tokens", "cache_creation_tokens", "cache_read_tokens")


def _select(records: Iterable[dict[str, Any]], rung_id: str, preset_id: str) -> dict[str, Any]:
    """Latest ok record for (rung, session, repeat 0) — same rule the analysis uses."""
    chosen = None
    for r in records:
        if (
            r.get("status") == "ok"
            and r.get("rung_id") == rung_id
            and r.get("preset_id") == preset_id
            and int(r.get("repeat_index", -1)) == GOLDEN_REPEAT_INDEX
        ):
            chosen = r
    if chosen is None:
        raise ValueError(f"No ok quality-rerun record for {rung_id} / {preset_id} / repeat {GOLDEN_REPEAT_INDEX}")
    return chosen


def _usage(call: dict[str, Any]) -> dict[str, int]:
    return {f: int(call.get(f) or 0) for f in _USAGE_FIELDS}


def convert_turn(t: dict[str, Any]) -> dict[str, Any]:
    """One rerun turn -> one golden turn (runner raw-capture schema + thinking/cache detail)."""
    comp = t.get("compaction")
    return {
        "turn_number": int(t["turn_number"]),
        "topic_tag": t["topic_tag"],
        "user_message": t["user_message"],
        "assistant_message": t["assistant_message"],
        "model_id": t["model_id"],
        "latency_ms": int(t["latency_ms"]),
        "stop_reason": t.get("stop_reason"),
        **_usage(t),
        "active_history_turns": int(t["active_history_turns"]),
        "compacted_turns_count": int(t.get("compacted_through_turn") or 0),
        "compaction_triggered_before_turn": bool(comp),
        "memory_summary_snapshot": t.get("memory_summary_snapshot"),
        "compaction_payload": comp["payload"] if comp else None,
        "compaction_model_id": comp["model_id"] if comp else None,
        "compaction_latency_ms": int(comp["latency_ms"]) if comp else 0,
        "compaction_input_tokens": int(comp["input_tokens"]) if comp else 0,
        "compaction_output_tokens": int(comp["output_tokens"]) if comp else 0,
        "compaction_thinking_tokens": int(comp.get("thinking_tokens") or 0) if comp else 0,
        "compaction_cache_creation_tokens": int(comp.get("cache_creation_tokens") or 0) if comp else 0,
        "compaction_cache_read_tokens": int(comp.get("cache_read_tokens") or 0) if comp else 0,
        "compaction_stop_reason": comp.get("stop_reason") if comp else None,
    }


def convert_probe_phase(record: dict[str, Any]) -> dict[str, Any]:
    pc = record.get("probe_compaction")
    compaction = None
    if pc:
        compaction = {
            "evicted_turns": list(pc.get("evicted_turns") or []),
            "kept_turns": list(pc.get("kept_turns") or []),
            "payload": pc["payload"],
            "memory_after": pc.get("memory_after"),
            "model_id": pc["model_id"],
            "stop_reason": pc.get("stop_reason"),
            "latency_ms": int(pc["latency_ms"]),
            **_usage(pc),
        }
    probes = [
        {
            "probe_id": p["probe_id"],
            "origin_turn": int(p["origin_turn"]),
            "question": p["question"],
            "answer": p["answer"],
            "model_id": p["model_id"],
            "stop_reason": p.get("stop_reason"),
            "latency_ms": int(p["latency_ms"]),
            **_usage(p),
            "active_history_turns": int(p.get("active_history_turns") or 0),
            "compacted_through_turn": int(p.get("compacted_through_turn") or 0),
        }
        for p in record.get("probes") or []
    ]
    return {"compaction": compaction, "probes": probes}


def build_golden(
    records: list[dict[str, Any]],
    *,
    source_file: str,
    keys_version: str | None,
    preset_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Golden-replay document without the rebuild timestamp (added by `write_if_changed`)."""
    pids = list(preset_ids) if preset_ids is not None else [p["id"] for p in CAT3_PRESETS]
    presets: dict[str, Any] = {}
    for pid in pids:
        chosen = {rid: _select(records, rid, pid) for rid in RUNG_IDS}
        presets[pid] = {
            "use_case": USE_CASE,
            "rungs": {rid: [convert_turn(t) for t in rec["turns"]] for rid, rec in chosen.items()},
            "probe_phase": {rid: convert_probe_phase(rec) for rid, rec in chosen.items()},
            "provenance": {
                rid: {
                    "run_id": rec["run_id"],
                    "repeat_index": int(rec["repeat_index"]),
                    "run_nonce": rec.get("run_nonce"),
                    "started_at": rec.get("started_at"),
                    "keys_version_at_capture": rec.get("keys_version"),
                }
                for rid, rec in chosen.items()
            },
        }
    return {
        "provenance": {
            "source": "cat3 quality rerun",
            "source_file": source_file,
            "selection_rule": "fixed pre-declared mapping: repeat_index 0 of every rung for every session (not selected by outcome)",
            "keys_version": keys_version,
            "probe_phase": "presets[*].probe_phase[rung] holds the probe-phase compaction (summarised rung only) and the recall probes; "
            "they are not part of the 10-turn session cost",
        },
        "presets": presets,
    }


def _comparable(doc: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(doc))
    (out.get("provenance") or {}).pop("rebuilt_at", None)
    return out


def write_if_changed(doc: dict[str, Any], out_path: Path, *, stamp: bool) -> bool:
    """Write `doc` unless the file already holds the same content; `stamp` adds provenance.rebuilt_at."""
    if out_path.is_file():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = None
        if existing is not None and _comparable(existing) == _comparable(doc):
            return False
    out_doc = dict(doc)
    if stamp:
        out_doc["provenance"] = {
            **doc["provenance"],
            "rebuilt_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def load_records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="in_path", default=str(DEFAULT_IN))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--summary-out", default=str(DEFAULT_SUMMARY_OUT))
    args = ap.parse_args(argv)

    in_path = Path(args.in_path)
    try:
        source_file = str(in_path.resolve().relative_to(BACKEND_DIR))
    except ValueError:
        source_file = str(in_path)
    records = load_records(in_path)
    keys = load_quality_keys()

    golden = build_golden(records, source_file=source_file, keys_version=keys["meta"].get("keys_version"))
    changed = write_if_changed(golden, Path(args.out), stamp=True)
    for pid, p in golden["presets"].items():
        for rid, turns in p["rungs"].items():
            prov = p["provenance"][rid]
            comps = sum(1 for t in turns if t["compaction_triggered_before_turn"])
            pp = p["probe_phase"][rid]
            print(
                f"{pid} {rid:<25} <- r{prov['repeat_index']} {prov['run_id'][:8]} | turns={len(turns)} "
                f"compactions={comps}{'+1 probe-phase' if pp['compaction'] else ''} probes={len(pp['probes'])}"
            )
    print(f"{'Wrote' if changed else 'Unchanged:'} {args.out}")

    portfolio = build_quality_portfolio(summarise(records, keys=keys), source_file=source_file)
    changed = write_if_changed(portfolio, Path(args.summary_out), stamp=False)
    for r in portfolio["rungs"]:
        print(
            f"  {r['rung_id']:<25} n={r['runs']} turn {r['turn_recall']['hits']}/{r['turn_recall']['total']} "
            f"ledger {r['ledger_recall']['hits']}/{r['ledger_recall']['total']} "
            f"probes {r['probe_accuracy']['hits']}/{r['probe_accuracy']['total']} "
            f"${r['session_billed_per_1k_usd']:.2f}/1k sessions"
        )
    print(f"{'Wrote' if changed else 'Unchanged:'} {args.summary_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
