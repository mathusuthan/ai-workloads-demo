"""Run the Category 5 matrix live (the deck's lever without and with) and append one JSONL record per run.

Usage (from backend/):
    .venv/bin/python scripts/cat5_ablation.py --dry-run
    .venv/bin/python scripts/cat5_ablation.py --repeats 3 --max-usd 25

Versions (default): raw_free_sonnet (without), bundle_gate_sonnet_cached and bundle_gate_haiku_escalate (with), on all
12 invoices. Append-only and resumable: an (arm, invoice, repeat) key with a current record (status ok, current
settings, and every policy-tool call returning what the tool returns now) is skipped; any other key is pending.
Wrong vouchers, cap hits and truncated turns are `ok` outcomes and are never dropped or retried. The single levers
tried on the way (`--arms raw_free_sonnet_cached,bundle_sonnet_cached,bundle_haiku_cached`) can be run into
`--out experiments/cat5_ablation/other_levers/runs.jsonl`.

Full tool results are stored once per sha256 in `tool_results.jsonl` next to the runs file. Order: repeat -> invoice
-> arm. The budget guard counts the billed cost of every record in the output file and reserves each in-flight run's
worst-case estimate; it stops launching runs that could cross --max-usd.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat5_orchestration.ablation import (  # noqa: E402
    ARM_IDS,
    ARMS,
    CALL_TIMEOUT_S,
    BudgetGuard,
    RunKey,
    calibrate,
    estimate_matrix,
    estimate_run,
    execute_run,
    load_jsonl,
    plan_matrix,
    select_pending,
)
from app.data.cat5_ablation_fixtures import (  # noqa: E402
    CAT5_ABLATION_DEFAULT_INVOICE_IDS,
    CAT5_ABLATION_PRESETS_BY_ID,
)

DEFAULT_OUT = BACKEND_DIR / "experiments" / "cat5_ablation" / "runs.jsonl"
BUDGET_EXIT_CODE = 2


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def blobs_path_for(runs_path: Path) -> Path:
    return runs_path.parent / "tool_results.jsonl"


def _run_line(rec: dict[str, Any], cost: float) -> str:
    ev = rec.get("evaluation") or {}
    turns = rec.get("turns") or []
    prompt = sum(int(t.get("input_tokens") or 0) + int(t.get("cache_creation_tokens") or 0) + int(t.get("cache_read_tokens") or 0) for t in turns)
    out = sum(int(t.get("output_tokens") or 0) for t in turns)
    trunc = sum(1 for t in turns if t.get("stop_reason") == "max_tokens")
    v = rec.get("committed_voucher") or {}
    line = (
        f"{rec['arm_id']:<27} {rec['preset_id']} r{rec['repeat_index']} | committed={bool(rec.get('committed_voucher'))} "
        f"{v.get('decision', '-')} exact={ev.get('exact_match')} fields={ev.get('matched_fields')}/{ev.get('total_fields')} | "
        f"turns={len(turns)} cap_hit={rec.get('cap_hit')} trunc={trunc} esc={rec.get('escalation_fired')} | "
        f"prompt={prompt:,} out={out:,} | billed=${cost:.4f} | wall={float(rec.get('wall_s') or 0):.1f}s"
    )
    if rec.get("status") != "ok":
        line += f" | STATUS=error {rec.get('error_message')}"
    return line


async def run_matrix(args: argparse.Namespace) -> int:
    arm_ids = _csv(args.arms) if args.arms else list(ARM_IDS)
    invoice_ids = _csv(args.invoices) if args.invoices else list(CAT5_ABLATION_DEFAULT_INVOICE_IDS)
    unknown = [a for a in arm_ids if a not in ARMS] + [p for p in invoice_ids if p not in CAT5_ABLATION_PRESETS_BY_ID]
    if unknown:
        print(f"Unknown arm/invoice ids: {unknown}", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    existing = load_jsonl(out_path)
    planned = plan_matrix(arm_ids, invoice_ids, args.repeats)
    pending = select_pending(planned, existing)
    guard = BudgetGuard(args.max_usd, existing)
    cal = calibrate()

    print(
        f"Matrix: {len(arm_ids)} arms x {len(invoice_ids)} invoices x {args.repeats} repeats = {len(planned)} runs; "
        f"{len(planned) - len(pending)} done, {len(pending)} pending. Existing records: {len(existing)}; "
        f"billed so far (this file) ${guard.spent_usd:.4f} of ${args.max_usd:.2f} cap."
    )
    print(f"Invoices{' (--invoices)' if args.invoices else ''}: {', '.join(invoice_ids)}")
    print(f"Output: {out_path} (+ {blobs_path_for(out_path).name})")

    if args.dry_run:
        est = estimate_matrix(pending, cal)
        cpt = est["calibration"]["chars_per_token"]
        print(
            f"Cost estimate for the {len(pending)} pending runs (calibrated on {est['calibration']['source']}: "
            + ", ".join(f"{m} {v:.2f} chars/token" for m, v in cpt.items())
            + "):"
        )
        print(f"  {'arm':<27} {'runs':>5} {'typical $/run':>14} {'typical $/1k inv':>17} {'typical total':>14} {'worst $/run':>12} {'worst total':>12}")
        for a in arm_ids:
            s = est["per_arm"].get(a)
            if not s:
                print(f"  {a:<27} {0:>5}")
                continue
            print(
                f"  {a:<27} {s['runs']:>5} {s['typical_usd_per_run']:>14.4f} {s['typical_usd_per_1k_invoices']:>17.2f} "
                f"{s['typical_usd']:>14.2f} {s['worst_case_usd_per_run']:>12.4f} {s['worst_case_usd']:>12.2f}"
            )
        print(f"  TOTAL typical ${est['total_typical_usd']:.2f}; worst case ${est['total_worst_case_usd']:.2f}; "
              f"cap ${args.max_usd:.2f} (already billed ${guard.spent_usd:.4f}).")
        print("Typical = golden-replay turn pattern re-priced with each arm's prefix/cache/model; worst = turn cap x max_tokens.")
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
    blobs_path = blobs_path_for(out_path)
    seen_hashes = {b.get("sha256") for b in load_jsonl(blobs_path)}
    write_lock = asyncio.Lock()
    pending_blobs: dict[str, str] = {}
    sem = asyncio.Semaphore(max(1, args.concurrency))
    finished = {"ok": 0, "error": 0}
    budget_stopped = False

    def sink(digest: str, content: str) -> None:
        if digest not in seen_hashes:
            pending_blobs[digest] = content

    async def one(key: RunKey, reserved: float) -> None:
        arm_id, pid, rep = key
        try:
            t0 = time.perf_counter()
            rec = await execute_run(
                arm_id=arm_id,
                preset=CAT5_ABLATION_PRESETS_BY_ID[pid],
                repeat_index=rep,
                api_key=api_key,
                blob_sink=sink,
                timeout_s=args.timeout_s,
            )
            rec["wall_s"] = round(time.perf_counter() - t0, 3)
            async with write_lock:
                with blobs_path.open("a", encoding="utf-8") as fh:
                    for digest in list(pending_blobs):
                        if digest in seen_hashes:
                            pending_blobs.pop(digest, None)
                            continue
                        fh.write(json.dumps({"sha256": digest, "content": pending_blobs.pop(digest)}, ensure_ascii=False) + "\n")
                        seen_hashes.add(digest)
                    fh.flush()
                    os.fsync(fh.fileno())
                with out_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    fh.flush()
                    os.fsync(fh.fileno())
                cost = guard.settle(reserved, rec)
                finished["ok" if rec["status"] == "ok" else "error"] += 1
                print(_run_line(rec, cost), flush=True)
        finally:
            sem.release()

    tasks: list[asyncio.Task[None]] = []
    for i, key in enumerate(pending):
        await sem.acquire()
        worst = estimate_run(key[0], CAT5_ABLATION_PRESETS_BY_ID[key[1]], cal)["worst_case_usd"]
        if not guard.try_reserve(worst):
            sem.release()
            budget_stopped = True
            print(f"BUDGET STOP before run {i + 1}/{len(pending)} {key}: billed ${guard.spent_usd:.4f} + reserved "
                  f"${guard.reserved_usd:.4f} + worst case ${worst:.4f} > cap ${args.max_usd:.2f}.")
            break
        tasks.append(asyncio.create_task(one(key, worst)))
    if tasks:
        await asyncio.gather(*tasks)

    print(f"Finished {finished['ok']} ok + {finished['error']} error runs this session; billed total ${guard.spent_usd:.4f} (cap ${args.max_usd:.2f}).")
    return BUDGET_EXIT_CODE if budget_stopped else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repeats", type=int, default=3, help="repeat indices 0..N-1 (default 3)")
    ap.add_argument("--arms", default="", help=f"comma list (default: {','.join(ARM_IDS)})")
    ap.add_argument("--invoices", default="", help="comma list of preset ids (default: all 12)")
    ap.add_argument("--concurrency", type=int, default=4, help="concurrent whole runs (default 4)")
    ap.add_argument("--max-usd", type=float, default=25.0, help="billed-cost cap incl. existing records (default 25)")
    ap.add_argument("--timeout-s", type=float, default=CALL_TIMEOUT_S, help=f"per-call HTTP timeout (default {CALL_TIMEOUT_S:.0f})")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="append-only JSONL path")
    ap.add_argument("--dry-run", action="store_true", help="print the planned matrix and cost estimate, then exit")
    return ap.parse_args(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(run_matrix(parse_args())))
