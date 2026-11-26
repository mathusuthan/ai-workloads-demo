"""Keep the Category 6 fair-rerun records to the displayed design, with the current sandbox's verdicts.

Step 1 — move: records of designs that are not displayed (`OTHER_DESIGN_ARMS`, the shared bus with the
"exhaustive commentary" instructions) are appended, line for line, to `experiments/cat6_fair_rerun/other_designs/
runs.jsonl` (skipping run ids already there) and then removed from the main file. The other-designs file is
written before the main file, so a record is never in neither. The main file keeps the four displayed cells:
`shared_bus_matched_gate`, `isolated_cached_gate`, `tiered_gate`, `shared_bus_tiered_gate`.

Step 2 — verdicts: for every record in both files, the sandbox report of `first_attempt` and `final` is
replaced by what the CURRENT `evaluate_patch_in_sandbox` returns on the recorded patch (`patched_code_first` /
`patched_code_final`), so the file holds the same verdicts the analysis and the app show. Nothing else in a record
changes: turns, tokens, retries and the patches stay as recorded. A report whose content already matches is left
byte-for-byte as is; a replaced report keeps the recorded `execution_ms` (wall-clock time, not a verdict), so the
output is deterministic and a second run changes nothing.

Unchanged lines are written back exactly as read; changed lines use the harness's own serialisation
(`json.dumps(record, ensure_ascii=False)`).

Both steps are deterministic and idempotent: a second run moves nothing and changes nothing.

Usage (from backend/):
    .venv/bin/python scripts/prune_cat6_records.py --dry-run
    .venv/bin/python scripts/prune_cat6_records.py [--in experiments/cat6_fair_rerun/runs.jsonl] [--other PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat6_swarms.sandbox_verifier import evaluate_patch_in_sandbox  # noqa: E402

DEFAULT_IN = BACKEND_DIR / "experiments" / "cat6_fair_rerun" / "runs.jsonl"
DEFAULT_OTHER = BACKEND_DIR / "experiments" / "cat6_fair_rerun" / "other_designs" / "runs.jsonl"
# Arms recorded in the fair rerun but not part of the displayed with/without design.
OTHER_DESIGN_ARMS: frozenset[str] = frozenset({"shared_bus_original"})
ATTEMPTS: tuple[tuple[str, str], ...] = (("first_attempt", "patched_code_first"), ("final", "patched_code_final"))

SandboxFn = Callable[[str, str], dict[str, Any]]


def _comparable(report: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in report.items() if k != "execution_ms"}


def _flipped_checks(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    o = {c["check_id"]: bool(c["passed"]) for c in old.get("checks") or []}
    n = {c["check_id"]: bool(c["passed"]) for c in new.get("checks") or []}
    return sorted(cid for cid in set(o) | set(n) if o.get(cid) != n.get(cid))


def prune_record(
    record: dict[str, Any],
    sandbox: SandboxFn = evaluate_patch_in_sandbox,
    cache: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(record with current-sandbox reports, list of changes). The input record is not mutated."""
    cache = {} if cache is None else cache
    out = dict(record)
    changes: list[dict[str, Any]] = []
    preset_id = str(record["preset_id"])
    for attempt_key, code_key in ATTEMPTS:
        attempt = record.get(attempt_key)
        if not attempt:
            continue
        code = str(record.get(code_key) or "")
        ck = (preset_id, code)
        if ck not in cache:
            cache[ck] = sandbox(preset_id, code)
        current = cache[ck]
        recorded = attempt.get("sandbox") or {}
        if _comparable(recorded) == _comparable(current):
            continue
        new_report = {**current}
        if "execution_ms" in recorded:
            new_report["execution_ms"] = recorded["execution_ms"]
        out[attempt_key] = {**attempt, "sandbox": new_report}
        changes.append(
            {
                "run_id": record.get("run_id"),
                "arm_id": record.get("arm_id"),
                "preset_id": preset_id,
                "repeat_index": record.get("repeat_index"),
                "attempt": attempt_key,
                "before": f"{recorded.get('passed_checks')}/{recorded.get('total_checks')} verified={bool(recorded.get('verified_outcome'))}",
                "after": f"{current.get('passed_checks')}/{current.get('total_checks')} verified={bool(current.get('verified_outcome'))}",
                "flipped_checks": _flipped_checks(recorded, current),
            }
        )
    return out, changes


def prune_lines(lines: list[str], sandbox: SandboxFn = evaluate_patch_in_sandbox) -> tuple[list[str], list[dict[str, Any]]]:
    """Rewrite JSONL lines; unchanged records keep their original line text."""
    cache: dict[tuple[str, str], dict[str, Any]] = {}
    out: list[str] = []
    changes: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            out.append(line)
            continue
        new, ch = prune_record(json.loads(line), sandbox, cache)
        out.append(json.dumps(new, ensure_ascii=False) if ch else line)
        changes.extend(ch)
    return out, changes


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


def _write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{line}\n" for line in lines if line.strip()), encoding="utf-8")


def move_other_designs(main: Path, other: Path, *, dry_run: bool = False) -> list[dict[str, Any]]:
    """Move OTHER_DESIGN_ARMS records from `main` to `other`; returns one entry per record moved."""
    keep: list[str] = []
    move: list[str] = []
    for line in _read_lines(main):
        if not line.strip():
            continue
        (move if json.loads(line).get("arm_id") in OTHER_DESIGN_ARMS else keep).append(line)
    if not move:
        return []
    other_lines = [x for x in _read_lines(other) if x.strip()]
    present = {json.loads(x)["run_id"] for x in other_lines}
    appended = [x for x in move if json.loads(x)["run_id"] not in present]
    if not dry_run:
        _write_lines(other, other_lines + appended)  # first: the records exist in `other` before leaving `main`
        _write_lines(main, keep)
    return [
        {k: json.loads(x).get(k) for k in ("run_id", "arm_id", "preset_id", "repeat_index")}
        for x in move
    ]


def prune_file(path: Path, *, dry_run: bool = False, sandbox: SandboxFn = evaluate_patch_in_sandbox) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    trailing_newline = text.endswith("\n")
    lines = text.splitlines()
    new_lines, changes = prune_lines(lines, sandbox)
    if changes and not dry_run:
        path.write_text("\n".join(new_lines) + ("\n" if trailing_newline else ""), encoding="utf-8")
    return changes


def _count(path: Path) -> int:
    return sum(1 for x in _read_lines(path) if x.strip())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="in_path", default=str(DEFAULT_IN))
    ap.add_argument("--other", dest="other_path", default=str(DEFAULT_OTHER))
    ap.add_argument("--dry-run", action="store_true", help="print what would change and write nothing")
    args = ap.parse_args(argv)

    main_path, other_path = Path(args.in_path), Path(args.other_path)
    verb = "Would" if args.dry_run else "Did"
    moved = move_other_designs(main_path, other_path, dry_run=args.dry_run)
    by_arm: dict[str, int] = {}
    for m in moved:
        by_arm[str(m["arm_id"])] = by_arm.get(str(m["arm_id"]), 0) + 1
    print(f"{verb} move {len(moved)} record(s) to {other_path}: {by_arm or 'none'}")
    for path in (main_path, other_path):
        changes = prune_file(path, dry_run=args.dry_run)
        for c in changes:
            print(
                f"  {c['arm_id']} {c['preset_id']} r{c['repeat_index']} {c['attempt']} ({str(c['run_id'])[:8]}): "
                f"{c['before']} -> {c['after']}; checks changed: {', '.join(c['flipped_checks']) or 'none (detail only)'}"
            )
        print(
            f"{verb} change {len(changes)} sandbox report(s) in {len({c['run_id'] for c in changes})} record(s): "
            f"{path} ({_count(path)} records now)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
