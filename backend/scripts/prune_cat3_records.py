#!/usr/bin/env python3
"""Keep only the current Category 3 quality-rerun records (deterministic, idempotent).

runs.jsonl                latest ok record per (rung, session, repeat) of the two displayed versions
                          (`quality_rerun.RUNG_IDS`: without and with the deck improvement); error and
                          superseded records are dropped.
other_levers/runs.jsonl   latest ok record per key of the other lever the harness ran (prefix caching alone,
                          `quality_rerun.OTHER_LEVER_RUNG_IDS`), moved out of runs.jsonl. Nothing displayed
                          reads this file.

Usage:
  .venv/bin/python scripts/prune_cat3_records.py --dry-run
  .venv/bin/python scripts/prune_cat3_records.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat3_assistants.quality_rerun import OTHER_LEVER_RUNG_IDS, RUNG_IDS  # noqa: E402

EXPERIMENT_DIR = BACKEND_DIR / "experiments" / "cat3_quality"


def _key(r: dict) -> tuple:
    return (r.get("rung_id"), r.get("preset_id") or r.get("session_id"), int(r.get("repeat_index") or 0))


def _read(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def latest_ok(runs: list[dict], rung_ids: tuple[str, ...]) -> list[dict]:
    """Latest ok record per key among `rung_ids`, in file order (a record seen twice by run_id counts once)."""
    latest: dict[tuple, dict] = {}
    for r in runs:
        if r.get("status") == "ok" and r.get("rung_id") in rung_ids:
            latest[_key(r)] = r
    out, seen = [], set()
    kept = {id(v) for v in latest.values()}
    for r in runs:
        if id(r) in kept and r.get("run_id") not in seen:
            seen.add(r.get("run_id"))
            out.append(r)
    return out


def keep_runs(runs: list[dict]) -> list[dict]:
    return latest_ok(runs, RUNG_IDS)


def split(runs: list[dict], other_existing: list[dict]) -> tuple[list[dict], list[dict]]:
    """(main records, other-lever records). Other-lever records already moved are kept (existing file first)."""
    return keep_runs(runs), latest_ok([*other_existing, *runs], OTHER_LEVER_RUNG_IDS)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=str(EXPERIMENT_DIR))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    d = Path(args.dir)
    runs_p, other_p = d / "runs.jsonl", d / "other_levers" / "runs.jsonl"
    runs, other_existing = _read(runs_p), _read(other_p)
    kept, other = split(runs, other_existing)
    moved = sum(1 for r in runs if r.get("rung_id") in OTHER_LEVER_RUNG_IDS)
    print(f"runs.jsonl: {len(runs)} -> {len(kept)} ({len(runs) - len(kept)} removed, of which {moved} moved)")
    print(f"other_levers/runs.jsonl: {len(other_existing)} -> {len(other)}")
    if args.dry_run:
        return 0
    if other != other_existing:
        _write(other_p, other)
    if kept != runs:
        _write(runs_p, kept)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
