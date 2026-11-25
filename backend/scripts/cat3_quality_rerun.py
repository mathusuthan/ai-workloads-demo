"""Run the Category 3 quality-rerun matrix live and append one JSONL record per session run.

Usage (from backend/):
    .venv/bin/python scripts/cat3_quality_rerun.py --dry-run
    .venv/bin/python scripts/cat3_quality_rerun.py --repeats 3 --max-usd 15

One run = one scripted session (turns 1-10) on one rung, plus the six turn-11 recall probes for that
session. Append-only and resumable: a (rung, session, repeat) key that already has an `ok` record is
skipped; `error` records stay in the file and their key is retried. No record is ever dropped for a
quality reason.
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
    str(Path(tempfile.gettempdir()) / "novamart_cat3_quality_rerun"),
)

from app.archetypes.cat3_assistants.quality_rerun import (  # noqa: E402
    RUNG_IDS,
    BudgetGuard,
    RunKey,
    execute_session_run,
    load_quality_keys,
    plan_matrix,
    probes_for,
    prompt_tokens,
    record_costs,
    select_pending,
    session_calls,
)
from app.data.cat3_fixtures import CAT3_PRESETS  # noqa: E402

DEFAULT_OUT = BACKEND_DIR / "experiments" / "cat3_quality" / "runs.jsonl"
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


def _run_line(record: dict[str, Any]) -> str:
    turns, comps = session_calls(record)
    costs = record_costs(record)
    prompt = sum(prompt_tokens(c) for c in [*turns, *comps])
    out = sum(int(c.get("output_tokens") or 0) for c in [*turns, *comps])
    probes = record.get("probes") or []
    probe_prompt = sum(prompt_tokens(p) for p in probes)
    wall = float(record.get("wall_s") or 0.0)
    ok_turns = sum(1 for t in turns if t.get("stop_reason") == "end_turn")
    line = (
        f"{record['rung_id']:<25} {record['preset_id']} r{record['repeat_index']} | "
        f"turns {len(turns)}/10 (end_turn {ok_turns}) | compactions {len(comps)}"
        f"{'+1 probe-phase' if record.get('probe_compaction') else ''} | "
        f"session prompt={prompt:,} out={out:,} | probes {len(probes)} (prompt={probe_prompt:,}) | "
        f"session billed=${costs['session_billed_usd']:.4f} | probe billed=${costs['probe_billed_usd']:.4f} | "
        f"wall={wall:.1f}s"
    )
    if record.get("status") != "ok":
        line += f" | STATUS=error {record.get('error_message')}"
    return line


async def run_matrix(args: argparse.Namespace) -> int:
    presets = {p["id"]: p for p in CAT3_PRESETS}
    rung_ids = _csv(args.rungs) if args.rungs else list(RUNG_IDS)
    preset_ids = _csv(args.presets) if args.presets else list(presets)
    unknown = [r for r in rung_ids if r not in RUNG_IDS] + [p for p in preset_ids if p not in presets]
    if unknown:
        print(f"Unknown rung/preset ids: {unknown}", file=sys.stderr)
        return 1

    keys = load_quality_keys()
    out_path = Path(args.out)
    existing = load_records(out_path)
    planned = plan_matrix(rung_ids, preset_ids, args.repeats)
    pending = select_pending(planned, existing)
    guard = BudgetGuard(args.max_usd, existing)

    print(
        f"Matrix: {len(rung_ids)} rungs x {len(preset_ids)} sessions x {args.repeats} repeats = {len(planned)} runs "
        f"(10 turns + {len(probes_for(keys, preset_ids[0]))} probes each); "
        f"{len(planned) - len(pending)} already ok, {len(pending)} pending. "
        f"Existing records: {len(existing)}; billed so far ${guard.spent_usd:.4f} of ${args.max_usd:.2f} cap."
    )
    print(f"Answer key: {keys['meta'].get('keys_version')} · Output: {out_path}")

    if args.dry_run:
        for i, (rg, p, r) in enumerate(pending, start=1):
            print(f"  {i:>3}. {rg:<25} {p} repeat={r}")
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
        rung_id, preset_id, repeat_index = key
        try:
            t0 = time.perf_counter()
            record = await execute_session_run(
                preset=presets[preset_id],
                rung_id=rung_id,
                repeat_index=repeat_index,
                api_key=api_key,
                probes=probes_for(keys, preset_id),
            )
            record["wall_s"] = round(time.perf_counter() - t0, 3)
            record["keys_version"] = keys["meta"].get("keys_version")
            async with write_lock:
                with out_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                    fh.flush()
                    os.fsync(fh.fileno())
                guard.add(record)
                finished["ok" if record["status"] == "ok" else "error"] += 1
                print(_run_line(record), flush=True)
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
    ap.add_argument("--repeats", type=int, default=3, help="repeat indices 0..N-1 (default 3)")
    ap.add_argument("--rungs", default="", help=f"comma list (default all: {','.join(RUNG_IDS)})")
    ap.add_argument("--presets", default="", help="comma list of sessions (default all: desk-01,desk-02)")
    ap.add_argument("--concurrency", type=int, default=3, help="concurrent whole runs (default 3)")
    ap.add_argument("--max-usd", type=float, default=15.0, help="billed-cost cap incl. existing records")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="append-only JSONL path")
    ap.add_argument("--dry-run", action="store_true", help="print the planned matrix and exit")
    return ap.parse_args(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(run_matrix(parse_args())))
