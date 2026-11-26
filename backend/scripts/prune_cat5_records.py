"""Prune the Category 5 experiment records to the runs behind the displayed cells.

The main files (`experiments/cat5_ablation/runs.jsonl` + `tool_results.jsonl`) keep, for each of the three displayed
versions (`ablation.ARM_IDS`), the latest current record per (version, invoice, repeat): status ok, current settings
and loop rule, and every tool call returning what that tool returns now (`ablation.record_is_current`).

Runs of the other single levers tried (`ablation.OTHER_LEVER_ARM_IDS`: status ok, current settings and loop rule,
latest per key) move to `experiments/cat5_ablation/other_levers/runs.jsonl` with their tool results in
`other_levers/tool_results.jsonl` and stay there as recorded (they document those levers; nothing displayed reads
them, and they are not re-checked against the tools' current output).

Everything else is deleted: error records, records whose settings no longer match, harness-artifact records, older
records of a key, and records of a displayed version whose recorded tool output differs from what the tool returns
now. Tool results are kept only where a kept record references them.

Deterministic and idempotent: a second run changes nothing. `--dry-run` prints what would change and writes nothing.

Usage (from backend/):
    .venv/bin/python scripts/prune_cat5_records.py [--dry-run] [--dir experiments/cat5_ablation]
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

from app.archetypes.cat5_orchestration.ablation import (  # noqa: E402
    ARM_IDS,
    OTHER_LEVER_ARM_IDS,
    harness_artifact,
    is_current_settings,
    record_is_current,
    record_key,
)

DEFAULT_DIR = BACKEND_DIR / "experiments" / "cat5_ablation"


def _reason(r: dict[str, Any]) -> str:
    if r.get("status") != "ok":
        return "error record"
    if harness_artifact(r):
        return "harness artifact (tool calls not executed)"
    if not is_current_settings(r):
        return "settings changed"
    if not record_is_current(r):
        return "a recorded tool output differs from what the tool returns now"
    return "older record of the same key"


def _referenced(records: list[dict[str, Any]]) -> set[str]:
    return {
        c.get("result_sha256")
        for r in records
        for t in r.get("turns") or []
        for c in t.get("tool_calls") or []
        if c.get("result_sha256")
    }


def plan(records: list[dict[str, Any]], other: list[dict[str, Any]]) -> dict[str, Any]:
    """Split main-file records (plus any already moved) into keep / move / delete."""
    latest: dict[tuple[str, str, int], dict[str, Any]] = {}
    for r in [*other, *records]:  # already-moved first; the main file's later records win
        if r.get("arm_id") in ARM_IDS and record_is_current(r):
            latest[record_key(r)] = r
        elif r.get("arm_id") in OTHER_LEVER_ARM_IDS and r.get("status") == "ok" and is_current_settings(r):
            latest[record_key(r)] = r
    keep_ids = {r["run_id"] for k, r in latest.items() if k[0] in ARM_IDS}
    move_ids = {r["run_id"] for k, r in latest.items() if k[0] in OTHER_LEVER_ARM_IDS}
    keep = [r for r in records if r["run_id"] in keep_ids]
    moved_existing = [r for r in other if r["run_id"] in move_ids]
    seen_moved = {r["run_id"] for r in moved_existing}
    move = [r for r in records if r["run_id"] in move_ids and r["run_id"] not in seen_moved]
    delete = [r for r in records if r["run_id"] not in keep_ids and r["run_id"] not in move_ids]
    return {"keep": keep, "move": move, "other_after": moved_existing + move, "delete": delete}


_RAW: dict[int, str] = {}  # id(parsed object) -> its original line, so kept lines are written byte for byte


def _load_raw(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            obj = json.loads(line)
            _RAW[id(obj)] = line
            out.append(obj)
    return out


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(_RAW.get(id(r), json.dumps(r)) + "\n" for r in rows), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=str(DEFAULT_DIR))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    _RAW.clear()  # ids of objects from an earlier call in the same process could be reused
    d = Path(args.dir)
    runs_p, blobs_p = d / "runs.jsonl", d / "tool_results.jsonl"
    o_runs_p, o_blobs_p = d / "other_levers" / "runs.jsonl", d / "other_levers" / "tool_results.jsonl"
    records, blobs = _load_raw(runs_p), _load_raw(blobs_p)
    other, o_blobs = _load_raw(o_runs_p), _load_raw(o_blobs_p)

    pl = plan(records, other)
    all_blobs: dict[str, dict[str, Any]] = {}
    for b in [*o_blobs, *blobs]:
        all_blobs.setdefault(b["sha256"], b)
    keep_refs, other_refs = _referenced(pl["keep"]), _referenced(pl["other_after"])
    new_blobs = [b for b in blobs if b["sha256"] in keep_refs]
    have = {b["sha256"] for b in new_blobs}
    new_blobs += [all_blobs[h] for h in sorted(keep_refs - have) if h in all_blobs]
    new_o_blobs = [b for b in o_blobs if b["sha256"] in other_refs]
    have_o = {b["sha256"] for b in new_o_blobs}
    new_o_blobs += [all_blobs[h] for h in sorted(other_refs - have_o) if h in all_blobs]

    print(f"{runs_p}: {len(records)} records -> keep {len(pl['keep'])}, move {len(pl['move'])} to other_levers/, "
          f"delete {len(pl['delete'])}")
    print("  kept per version: " + ", ".join(f"{a} {n}" for a, n in sorted(Counter(r['arm_id'] for r in pl['keep']).items())))
    if pl["move"]:
        print("  moved per lever: " + ", ".join(f"{a} {n}" for a, n in sorted(Counter(r['arm_id'] for r in pl['move']).items())))
    for reason, n in sorted(Counter(_reason(r) for r in pl["delete"]).items()):
        print(f"  delete ({reason}): {n}")
    for r in pl["delete"]:
        print(f"    - {r['run_id']} {r['arm_id']} {r['preset_id']} r{r['repeat_index']}: {_reason(r)}")
    print(f"{blobs_p}: {len(blobs)} -> {len(new_blobs)}; {o_blobs_p}: {len(o_blobs)} -> {len(new_o_blobs)}")
    missing = (keep_refs | other_refs) - {b['sha256'] for b in (*new_blobs, *new_o_blobs)}
    if missing:
        print(f"  note: {len(missing)} referenced tool results were never stored (not an error)")
    changed = (len(pl["keep"]) != len(records) or pl["move"] or len(new_blobs) != len(blobs)
               or len(new_o_blobs) != len(o_blobs))
    if args.dry_run:
        print("Dry run: nothing written." if changed else "Dry run: nothing to change.")
        return 0
    if not changed:
        print("Nothing to change.")
        return 0
    _write_jsonl(o_runs_p, pl["other_after"])
    _write_jsonl(o_blobs_p, new_o_blobs)
    _write_jsonl(runs_p, pl["keep"])
    _write_jsonl(blobs_p, new_blobs)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
