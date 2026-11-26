"""Prune the Category 1 experiment record files to the runs behind the displayed cells.

Usage (from backend/):
    .venv/bin/python scripts/prune_cat1_records.py --dry-run
    .venv/bin/python scripts/prune_cat1_records.py

runs.jsonl keeps the latest ok record at the current settings for each run of the four displayed versions
(Sonnet / Haiku x write-up / JSON schema). Valid runs of the other levers tried (plain-text classification, a third-party
decisions API) move to other_levers/runs.jsonl (latest ok record per run id), with their reader-model extractions in
other_levers/extractions.jsonl. extractions.jsonl keeps the latest ok extraction of each displayed write-up made from
the current prompt. Everything else (error records, superseded records, extractions of texts that are not current
runs) is dropped.

Deterministic and idempotent: kept records stay in their original order and byte-identical; a file whose content
would not change is not rewritten. Back the files up before running without --dry-run.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat1_triage import ablation as ab  # noqa: E402

OTHER_LEVER_RUN_ARMS = (*(a.arm_id for a in ab.OTHER_LEVER_ARMS), "gemini_decision")


def _lines(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.is_file() else []


def _latest_ok_lines(pairs: list[tuple[str, dict[str, Any]]], key: str) -> list[str]:
    last: dict[str, int] = {}
    for i, (_, r) in enumerate(pairs):
        if r.get("status") == "ok":
            last[r[key]] = i
    keep = set(last.values())
    return [line for i, (line, _) in enumerate(pairs) if i in keep]


def split_runs(lines: list[str]) -> tuple[list[str], list[str], Counter]:
    records = [json.loads(line) for line in lines]
    keep_ids = {id(r) for r in ab.latest_ok_current(records).values()}
    main, other_pairs, dropped = [], [], Counter()
    for line, r in zip(lines, records):
        if id(r) in keep_ids:
            main.append(line)
        elif r.get("arm_id") in OTHER_LEVER_RUN_ARMS:
            other_pairs.append((line, r))
        else:
            dropped["error" if r.get("status") != "ok" else "superseded or older duplicate"] += 1
    other = _latest_ok_lines(other_pairs, "run_id")
    dropped["other-lever error or older duplicate"] += len(other_pairs) - len(other)
    return main, other, +dropped


def split_extractions(lines: list[str], main_runs: list[dict[str, Any]], other_run_ids: set[str]) -> tuple[list[str], list[str], Counter]:
    records = [json.loads(line) for line in lines]
    plan = ab.plan_extractions(ab.extraction_targets(ab.latest_ok_current(main_runs)))
    keep_ids = {id(r) for r in ab.latest_ok_extractions(records, plan).values()}
    main, other_pairs, dropped = [], [], Counter()
    for line, r in zip(lines, records):
        if id(r) in keep_ids:
            main.append(line)
        elif r.get("source") == "run" and r.get("target_id") in other_run_ids:
            other_pairs.append((line, r))
        elif r.get("status") != "ok":
            dropped["error"] += 1
        else:
            dropped[f"not a current run extraction (source {r.get('source')})"] += 1
    other = _latest_ok_lines(other_pairs, "call_id")
    dropped["other-lever error or older duplicate"] += len(other_pairs) - len(other)
    return main, other, +dropped


def _merge(existing: list[str], new: list[str]) -> list[str]:
    """Other-lever files: existing lines first, then new lines not already present (idempotent)."""
    seen = set(existing)
    return existing + [line for line in new if line not in seen]


def _write(path: Path, kept: list[str], dry_run: bool) -> bool:
    new = "".join(line + "\n" for line in kept)
    if path.is_file() and path.read_text(encoding="utf-8") == new:
        return False
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new, encoding="utf-8")
    return True


def _show(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(BACKEND_DIR))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", default=str(ab.RUNS_PATH))
    ap.add_argument("--extractions", default=str(ab.EXTRACTIONS_PATH))
    ap.add_argument("--other-levers-dir", default=str(ab.OTHER_LEVERS_DIR))
    ap.add_argument("--dry-run", action="store_true", help="report what would change; write nothing")
    args = ap.parse_args(argv)
    runs_path, ext_path, other_dir = Path(args.runs), Path(args.extractions), Path(args.other_levers_dir)
    o_runs_path, o_ext_path = other_dir / "runs.jsonl", other_dir / "extractions.jsonl"
    run_lines, ext_lines = _lines(runs_path), _lines(ext_path)
    o_run_before, o_ext_before = _lines(o_runs_path), _lines(o_ext_path)
    main_runs, other_runs, d_runs = split_runs(run_lines)
    other_runs = _merge(o_run_before, other_runs)
    other_ids = {json.loads(line)["run_id"] for line in other_runs}
    main_ext, other_ext, d_ext = split_extractions(ext_lines, [json.loads(line) for line in main_runs], other_ids)
    other_ext = _merge(o_ext_before, other_ext)
    verb = "would" if args.dry_run else "did"
    rows = ((runs_path, run_lines, main_runs, d_runs), (ext_path, ext_lines, main_ext, d_ext),
            (o_runs_path, o_run_before, other_runs, None), (o_ext_path, o_ext_before, other_ext, None))
    for path, before, kept, note in rows:
        changed = _write(path, kept, args.dry_run)
        print(f"{_show(path)}: {len(before)} -> {len(kept)} records" + (f"; dropped {dict(sorted(note.items()))}" if note else "")
              + f"; {verb} {'write' if changed else 'leave unchanged'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
