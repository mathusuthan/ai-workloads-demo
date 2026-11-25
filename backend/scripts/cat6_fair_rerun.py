"""Run the Category 6 fair-rerun experiment matrix live and append one JSONL record per run.

Usage (from backend/):
    .venv/bin/python scripts/cat6_fair_rerun.py --dry-run
    .venv/bin/python scripts/cat6_fair_rerun.py --repeats 5 --max-usd 40

Append-only and resumable: a (arm, preset, repeat) key that already has an `ok` record is skipped;
`error` records stay in the file and their key is retried. Sandbox-failed runs are `ok` outcomes and
are never skipped, dropped, or retried.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "NOVAMART_TRACES_DIR",
    str(Path(tempfile.gettempdir()) / "novamart_cat6_fair_rerun"),
)

from app.archetypes.cat6_swarms.fair_rerun import (  # noqa: E402
    ARM_IDS,
    BudgetGuard,
    RunKey,
    execute_run,
    plan_matrix,
    select_pending,
)
from app.data.cat6_fixtures import CAT6_PRESETS  # noqa: E402

DEFAULT_OUT = BACKEND_DIR / "experiments" / "cat6_fair_rerun" / "runs.jsonl"
BUDGET_EXIT_CODE = 2


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"WARNING: skipping malformed JSONL line {lineno} in {path}", file=sys.stderr)
    return records


def _run_line(record: dict[str, Any], cost: float) -> str:
    turns = record.get("turns") or []
    first = (record.get("first_attempt") or {}).get("sandbox") or {}
    final = (record.get("final") or {}).get("sandbox") or {}
    prompt = sum(
        int(t.get("input_tokens") or 0) + int(t.get("cache_creation_tokens") or 0) + int(t.get("cache_read_tokens") or 0)
        for t in turns
    )
    out = sum(int(t.get("output_tokens") or 0) for t in turns)
    truncated = [f"{t['agent_role']}#{t['attempt']}" for t in turns if t.get("stop_reason") == "max_tokens"]
    wall = float(record.get("wall_s") or 0.0)
    line = (
        f"{record['arm_id']:<24} {record['preset_id']} r{record['repeat_index']} | "
        f"first {first.get('passed_checks', '-')}/{first.get('total_checks', '-')} | "
        f"final {final.get('passed_checks', '-')}/{final.get('total_checks', '-')} "
        f"verified={bool(final.get('verified_outcome'))} | retries={record.get('retries_used', 0)} | "
        f"prompt={prompt:,} out={out:,} | max_tokens_stops={len(truncated)}"
        f"{' ' + ','.join(truncated) if truncated else ''} | billed=${cost:.4f} | wall={wall:.1f}s"
    )
    if record.get("status") != "ok":
        line += f" | STATUS=error ({len(turns)} turns) {record.get('error_message')}"
    return line


async def run_matrix(args: argparse.Namespace) -> int:
    presets = {p["id"]: p for p in CAT6_PRESETS}
    arm_ids = _csv(args.arms) if args.arms else list(ARM_IDS)
    preset_ids = _csv(args.presets) if args.presets else list(presets)
    unknown = [a for a in arm_ids if a not in ARM_IDS] + [p for p in preset_ids if p not in presets]
    if unknown:
        print(f"Unknown arm/preset ids: {unknown}", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    existing = load_records(out_path)
    planned = plan_matrix(arm_ids, preset_ids, args.repeats)
    pending = select_pending(planned, existing)
    guard = BudgetGuard(args.max_usd, existing)

    print(
        f"Matrix: {len(arm_ids)} arms x {len(preset_ids)} presets x {args.repeats} repeats = {len(planned)} runs; "
        f"{len(planned) - len(pending)} already ok, {len(pending)} pending. "
        f"Existing records: {len(existing)}; billed so far ${guard.spent_usd:.4f} of ${args.max_usd:.2f} cap."
    )
    print(f"Output: {out_path}")

    if args.dry_run:
        for i, (a, p, r) in enumerate(pending, start=1):
            print(f"  {i:>3}. {a:<24} {p} repeat={r}")
        print("Dry run: no API calls made.")
        return 0

    if not pending:
        print("Nothing to do.")
        return 0

    from app.config import get_settings

    api_key = get_settings().anthropic_api_key
    if not api_key:
        print("ANTHROPIC_API_KEY must be set (env or .env) for a live run.", file=sys.stderr)
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_lock = asyncio.Lock()
    sem = asyncio.Semaphore(max(1, args.concurrency))
    budget_stopped = False
    finished = {"ok": 0, "error": 0}

    async def one(key: RunKey) -> None:
        arm_id, preset_id, repeat_index = key
        try:
            t0 = time.perf_counter()
            record = await execute_run(
                arm_id=arm_id,
                preset=presets[preset_id],
                repeat_index=repeat_index,
                api_key=api_key,
            )
            record["wall_s"] = round(time.perf_counter() - t0, 3)
            async with write_lock:
                with out_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                    fh.flush()
                    os.fsync(fh.fileno())
                cost = guard.add(record)
                finished["ok" if record["status"] == "ok" else "error"] += 1
                print(_run_line(record, cost), flush=True)
        finally:
            sem.release()

    tasks: list[asyncio.Task[None]] = []
    for key in pending:
        await sem.acquire()
        if guard.exhausted:
            sem.release()
            budget_stopped = True
            break
        tasks.append(asyncio.create_task(one(key)))
    if tasks:
        await asyncio.gather(*tasks)

    print(
        f"Finished {finished['ok']} ok + {finished['error']} error runs this session; "
        f"billed total ${guard.spent_usd:.4f} (cap ${args.max_usd:.2f})."
    )
    if budget_stopped:
        print(
            f"BUDGET STOP: billed total reached the --max-usd cap of ${args.max_usd:.2f}; "
            "no new runs were launched after that point. Re-run with a higher cap to resume."
        )
        return BUDGET_EXIT_CODE
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repeats", type=int, default=5, help="repeat indices 0..N-1 (default 5)")
    ap.add_argument("--arms", default="", help=f"comma list (default all: {','.join(ARM_IDS)})")
    ap.add_argument("--presets", default="", help="comma list (default all presets)")
    ap.add_argument("--concurrency", type=int, default=3, help="concurrent whole runs (default 3)")
    ap.add_argument("--max-usd", type=float, default=40.0, help="billed-cost cap incl. existing records")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="append-only JSONL path")
    ap.add_argument("--dry-run", action="store_true", help="print the planned matrix and exit")
    return ap.parse_args(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(run_matrix(parse_args())))
