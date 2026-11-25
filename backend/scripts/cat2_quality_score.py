"""Score the 12 stored Category 2 drafts: deterministic phase (offline) + optional blind-judge phase (live).

Usage (from backend/):
    .venv/bin/python scripts/cat2_quality_score.py                      # deterministic only, no key needed
    .venv/bin/python scripts/cat2_quality_score.py --judge --dry-run    # planned judge calls + estimate, no calls
    .venv/bin/python scripts/cat2_quality_score.py --judge --max-usd 13 --concurrency 4

Deterministic phase: renders every draft, scores fact coverage and unsupported numbers, and writes
experiments/cat2_quality/deterministic.json. It always runs first (the judge prompts are built from it).

Judge phase (--judge): rubric (36 calls = 12 drafts x 3 repeats) and pairwise (24 calls = 4 bundles x 3 pairs x
2 orders) on claude-opus-5-5. Append-only JSONL; a call_id with an `ok` record is skipped, error records stay
and their call is retried. --max-usd counts every recorded call (ok and error) at the ASSUMED Opus 5.5 rate in
quality_scoring.py and refuses to launch a call whose worst case (estimated input + max_tokens output) could
cross the cap.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat2_drafting.quality_scoring import (  # noqa: E402
    DETERMINISTIC_PATH,
    JUDGE_EFFORT,
    JUDGE_MAX_TOKENS,
    JUDGE_MODEL,
    JUDGE_TIMEOUT_S,
    JUDGEMENTS_PATH,
    KEYS_PATH,
    OPUS_INPUT_PER_1M_USD,
    OPUS_OUTPUT_PER_1M_USD,
    REPLAYS_PATH,
    RUBRIC_REPEATS,
    RUNG_IDS,
    BudgetGuard,
    calibrate_chars_per_token,
    estimate_input_tokens,
    estimate_plan,
    load_judgements,
    load_quality_keys,
    load_replays,
    make_anthropic_judge_call,
    plan_judge_calls,
    record_cost_usd,
    run_deterministic,
    run_judge_plan,
    select_pending,
    stale_ok_records,
)

BUDGET_EXIT_CODE = 2


def _pct(p: dict[str, Any]) -> str:
    if not p["total"]:
        return "n/a"
    lo, hi = p["wilson95"]
    return f"{p['hits']}/{p['total']} {p['rate'] * 100:.0f}% [{lo * 100:.0f}–{hi * 100:.0f}]"


def print_deterministic(det: dict[str, Any]) -> None:
    print(f"Answer key {det['keys_version']} · {len(det['drafts'])} drafts")
    print()
    print(f"{'rung':<18} {'overall':<22} {'core':<22} {'detail':<22} {'facts/1k out':>12} {'out tok':>8} {'$/1k docs':>10}")
    for rid in RUNG_IDS:
        r = det["rungs"][rid]
        c = r["coverage"]
        print(
            f"{rid:<18} {_pct(c['overall']):<22} {_pct(c['core']):<22} {_pct(c['detail']):<22} "
            f"{c['facts_per_1k_output_tokens']:>12.2f} {r['output_tokens']['total']:>8,} {r['cost_per_1k_docs_usd']:>10.2f}"
        )
    print()
    print(f"{'rung':<18} {'bundle':<9} {'cov':>6} {'core':>6} {'detail':>7} {'num tok':>8} {'not in src':>11} {'ignored':>8}")
    for rid in RUNG_IDS:
        for pid, b in det["rungs"][rid]["by_preset"].items():
            c, n = b["coverage"], b["numbers"]
            print(
                f"{rid:<18} {pid:<9} {c['overall']['hits']:>3}/{c['overall']['total']:<2} {c['core']['hits']:>3}/{c['core']['total']:<2} "
                f"{c['detail']['hits']:>3}/{c['detail']['total']:<3} {n['numeric_tokens']:>8} "
                f"{n['not_in_source']:>4} ({(n['not_in_source_share'] or 0) * 100:4.1f}%) {n['ignored']:>6}"
            )
    print()
    if det["facts_covered_by_no_draft"]:
        print(f"Facts covered by no draft: {det['facts_covered_by_no_draft']}")


def write_record(path: Path, rec: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _call_line(rec: dict[str, Any]) -> str:
    line = (
        f"{rec['call_id']:<62} {rec['status']:<5} model={rec.get('model_id')} stop={rec.get('stop_reason')} "
        f"in={rec.get('input_tokens')} out={rec.get('output_tokens')} (think {rec.get('thinking_tokens')}) "
        f"${record_cost_usd(rec):.4f} {rec.get('latency_ms')}ms"
    )
    if rec["status"] != "ok":
        line += f" | {rec.get('error_type')}: {str(rec.get('error_message'))[:200]}"
    return line


async def judge_phase(args: argparse.Namespace, det: dict[str, Any], replays: dict[str, Any]) -> int:
    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
    plan = plan_judge_calls(det, repeats=args.repeats, tasks=tasks)
    out_path = Path(args.out)
    existing = load_judgements(out_path)
    pending = select_pending(plan, existing)
    stale = stale_ok_records(plan, existing)
    guard = BudgetGuard(args.max_usd, existing)
    cpt = calibrate_chars_per_token(replays)
    est = estimate_plan(pending, chars_per_token=cpt, max_tokens=args.max_tokens)

    print(
        f"Judge {JUDGE_MODEL} (thinking adaptive, effort {JUDGE_EFFORT}, max_tokens {args.max_tokens}, timeout "
        f"{JUDGE_TIMEOUT_S:.0f}s, max_retries 0). Assumed rate ${OPUS_INPUT_PER_1M_USD:.2f}/${OPUS_OUTPUT_PER_1M_USD:.2f} per MTok."
    )
    print(
        f"Planned {len(plan)} calls ({', '.join(f'{t}: {sum(1 for p in plan if p['task'] == t)}' for t in tasks)}); "
        f"{len(plan) - len(pending)} already ok, {len(pending)} pending. Existing records {len(existing)}, "
        f"billed so far ${guard.spent_usd:.4f} of ${args.max_usd:.2f} cap. Output: {out_path}"
    )
    if stale:
        print(f"WARNING: {len(stale)} ok records were made from a different prompt than the current plan: {stale[:6]}")
    print(f"Estimate for pending calls (chars/token {cpt:.2f}, calibrated on the stored unbounded rung):")
    for task, s in est["by_task"].items():
        print(
            f"  {task:<9} {s['calls']:>3} calls  input≈{s['input_tokens']:,} tok  output typical≈{s['typical_output_tokens']:,} "
            f"/ worst {s['worst_case_output_tokens']:,}  ${s['typical_usd']:.2f} typical / ${s['worst_case_usd']:.2f} worst"
        )
    t = est["total"]
    print(f"  total     {t['calls']:>3} calls  input≈{t['input_tokens']:,} tok  ${t['typical_usd']:.2f} typical / ${t['worst_case_usd']:.2f} worst")

    if args.dry_run:
        for i, p in enumerate(pending, start=1):
            extra = f"numbers={len(p['numbers'])}" if p["task"] == "rubric" else f"A={p['a_rung']} B={p['b_rung']}"
            print(f"  {i:>3}. {p['call_id']:<62} in≈{estimate_input_tokens(p, cpt):,} {extra}")
        print("Dry run: no API calls made.")
        return 0
    if not pending:
        print("Nothing to do.")
        return 0

    from app.config import get_settings

    api_key = get_settings().anthropic_api_key
    if not api_key:
        print("ANTHROPIC_API_KEY must be set (env or .env) for the judge phase.", file=sys.stderr)
        return 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    judge_call = make_anthropic_judge_call(api_key)

    def on_record(rec: dict[str, Any]) -> None:
        write_record(out_path, rec)
        print(_call_line(rec), flush=True)

    res = await run_judge_plan(
        pending, judge_call=judge_call, guard=guard, on_record=on_record, concurrency=args.concurrency,
        max_tokens=args.max_tokens, chars_per_token=cpt,
    )
    print(
        f"Finished: {res['ok']} ok, {res['error']} error of {res['launched']} launched; billed total "
        f"${res['spent_usd']:.4f} (cap ${args.max_usd:.2f})."
    )
    if res["budget_stopped"]:
        print(
            f"BUDGET STOP: {res['skipped_budget']} calls not launched because their worst case could exceed "
            f"--max-usd ${args.max_usd:.2f}. Re-run with a higher cap to resume."
        )
        return BUDGET_EXIT_CODE
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replays", default=str(REPLAYS_PATH))
    ap.add_argument("--keys", default=str(KEYS_PATH))
    ap.add_argument("--deterministic-out", default=str(DETERMINISTIC_PATH))
    ap.add_argument("--judge", action="store_true", help="also run (or with --dry-run, plan) the live judge phase")
    ap.add_argument("--dry-run", action="store_true", help="print planned judge calls and the estimate; no API calls")
    ap.add_argument("--tasks", default="rubric,pairwise", help="comma list: rubric,pairwise")
    ap.add_argument("--repeats", type=int, default=RUBRIC_REPEATS, help="rubric repeats per draft (default 3)")
    ap.add_argument("--max-usd", type=float, default=13.0, help="billed judge-cost cap incl. existing records")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--max-tokens", type=int, default=JUDGE_MAX_TOKENS)
    ap.add_argument("--out", default=str(JUDGEMENTS_PATH), help="append-only JSONL")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    replays = load_replays(args.replays)
    keys = load_quality_keys(args.keys)
    det = run_deterministic(replays, keys)
    out = Path(args.deterministic_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(det, indent=2, ensure_ascii=False), encoding="utf-8")
    print_deterministic(det)
    print(f"Wrote {out}")
    if args.judge or args.dry_run:
        print()
        return asyncio.run(judge_phase(args, det, replays))
    return 0


if __name__ == "__main__":
    sys.exit(main())
