"""Blind Opus 5.5 judge for the Category 4 quality-rerun answers.

Usage (from backend/):
    .venv/bin/python scripts/cat4_quality_judge.py --dry-run
    .venv/bin/python scripts/cat4_quality_judge.py --max-usd 16

The judge sees the question as it was asked (with the scope line), Deccan's seven documents (cached system prefix) and the answer with citation
markers stripped; never the rung, model, scale, cost or citations. The first call runs alone to write the
cache, then the rest fan out. Append-only; deterministic call ids; ok judgements of an unchanged answer are
skipped on resume.
ASSUMPTION — LEAD MUST CONFIRM: Opus 5.5 rates $4 / $20 / $5 write / $0.20 read per 1M (as in Category 2).
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

from app.archetypes.cat4_rag.quality_rerun import (  # noqa: E402
    JUDGE_MAX_TOKENS,
    JUDGE_MODEL,
    JUDGEMENTS_PATH,
    RUNS_PATH,
    JudgeBudgetGuard,
    blinding_violations,
    estimate_judge_plan,
    judge_items,
    judgement_cost_usd,
    load_jsonl,
    make_anthropic_judge_call,
    plan_judge_calls,
    run_judge_plan,
    select_pending_judgements,
)

BUDGET_EXIT_CODE = 2


async def main(args: argparse.Namespace) -> int:
    records = load_jsonl(args.runs)
    items = judge_items(records)
    plan = plan_judge_calls(items, repeats=args.judge_repeats)
    violations = {p["call_id"]: v for p in plan
                  if (v := blinding_violations(p["system"], p["user"], [p["question"], p["answer_for_judge"]]))}
    if violations:
        print(f"BLINDING VIOLATION in {len(violations)} prompts, e.g. {next(iter(violations.items()))}", file=sys.stderr)
        return 1
    existing = load_jsonl(args.out)
    pending = select_pending_judgements(plan, existing)
    guard = JudgeBudgetGuard(args.max_usd, existing)
    est = estimate_judge_plan(pending)
    print(f"Judge {JUDGE_MODEL} · {len(items)} answers x {args.judge_repeats} = {len(plan)} calls; "
          f"{len(plan) - len(pending)} already ok, {len(pending)} pending. Blinding check passed on all {len(plan)} prompts.")
    print(f"Existing judgements {len(existing)}; spent ${guard.spent_usd:.4f} of ${args.max_usd:.2f} cap.")
    print(f"Estimate for pending: cached prefix ≈{est.get('prefix_tokens_est', 0):,} tok, user ≈{est.get('user_tokens_est', 0):,} tok total; "
          f"typical ≈ ${est['typical_usd']:.2f} ({est.get('typical_output_tokens_per_call', 0)} out/call incl. thinking), "
          f"worst ≈ ${est['worst_case_usd']:.2f} (every call writes the prefix and hits max_tokens {JUDGE_MAX_TOKENS}).")
    if args.dry_run:
        for i, p in enumerate(pending[:10], 1):
            print(f"  {i:>3}. {p['call_id']}")
        if len(pending) > 10:
            print(f"  ... {len(pending) - 10} more")
        print("Dry run: no API calls made.")
        return 0
    if not pending:
        print("Nothing to do.")
        return 0
    from app.config import get_settings

    api_key = get_settings().anthropic_api_key
    if not api_key:
        print("ANTHROPIC_API_KEY must be set for a live run.", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    def on_record(rec: dict[str, Any]) -> None:
        with out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        p = rec.get("parsed") or {}
        print(f"{rec['call_id']} {rec['status']} stop={rec['stop_reason']} cw={rec['cache_creation_tokens']} cr={rec['cache_read_tokens']} "
              f"corr={(p.get('correctness') or {}).get('score')} comp={(p.get('completeness') or {}).get('score')} "
              f"errors={len(p.get('factual_errors') or [])} ${judgement_cost_usd(rec):.4f} {rec.get('error_message') or ''}", flush=True)

    result = await run_judge_plan(pending, judge_call=make_anthropic_judge_call(api_key), guard=guard,
                                  on_record=on_record, concurrency=args.concurrency)
    print(f"Finished {result['ok']} ok + {result['error']} error; spent ${result['spent_usd']:.4f} (cap ${args.max_usd:.2f}).")
    if result["budget_stopped"]:
        print(f"BUDGET STOP: {result['skipped_budget']} calls not launched. Re-run with a higher cap to resume.")
        return BUDGET_EXIT_CODE
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--judge-repeats", type=int, default=1)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--max-usd", type=float, default=16.0, help="judge spend cap incl. existing judgements (default 16)")
    ap.add_argument("--runs", default=str(RUNS_PATH))
    ap.add_argument("--out", default=str(JUDGEMENTS_PATH))
    ap.add_argument("--dry-run", action="store_true")
    return ap.parse_args(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
