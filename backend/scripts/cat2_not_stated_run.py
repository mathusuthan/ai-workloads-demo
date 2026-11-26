"""Category 2 follow-up experiment runner: "Not stated in source" template variant.

Usage (from backend/):
    .venv/bin/python scripts/cat2_not_stated_run.py draft --dry-run         # 48 planned drafts + cost estimate, no calls
    .venv/bin/python scripts/cat2_not_stated_run.py draft --max-usd 2 --concurrency 4
    .venv/bin/python scripts/cat2_not_stated_run.py judge --dry-run         # 112 planned judge calls + estimate + blinding check
    .venv/bin/python scripts/cat2_not_stated_run.py judge --max-usd 12 --concurrency 4

draft: Sonnet 5.5 and Haiku 5.5 through the app's `run_cat2_structured_draft` (same settings as the app's templated
rungs), 2 arms x 4 bundles x 3 repeats. Appends one record per call to experiments/cat2_not_stated/drafts.jsonl;
an ok record (including a truncated one, which is flagged) is never redone; error records stay and are retried.
--max-usd counts every recorded draft at the app's rate card and refuses a draft whose worst case (estimated input +
max_tokens output) could cross the cap.

judge: the baseline blind judge (model, settings, prompts, schemas imported from quality_scoring.py): one rubric pass
per draft (48), matched pairwise not_stated vs original on bundle/model/repeat in both orders (48), and not_stated
repeat 0 vs the stored unbounded draft in both orders per model (16). A live run needs all 48 drafts; --dry-run
without them estimates with the stored templated drafts standing in. Every planned prompt is checked for blinding
before anything is sent. The baseline files (judgements, deterministic, replays, summary) are only read.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat2_drafting import not_stated_experiment as ns  # noqa: E402
from app.archetypes.cat2_drafting import quality_scoring as qs  # noqa: E402


def append_record(path: Path, rec: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _api_key() -> str | None:
    from app.config import get_settings

    try:
        return get_settings().anthropic_api_key or None
    except Exception:  # noqa: BLE001
        return None


async def draft_phase(args: argparse.Namespace, *, draft_call: Any = None) -> int:
    replays = qs.load_replays(args.replays)
    out = Path(args.out)
    existing = ns.load_jsonl(out)
    plan = ns.plan_drafts(args.repeats)
    pending = ns.select_pending_drafts(plan, existing)
    stale = ns.stale_draft_records(plan, existing)
    est = ns.estimate_draft_plan(pending, replays)
    guard = ns.CostGuard(args.max_usd, existing)
    print(f"Planned {len(plan)} drafts ({len(ns.ARMS)} arms x {len(ns.MODEL_KEYS)} models x {len(qs.PRESET_IDS)} bundles x {args.repeats} repeats); "
          f"{len(plan) - len(pending)} already ok in {out.name}, {len(pending)} pending.")
    if stale:
        print(f"WARNING: {len(stale)} ok drafts were made from a different prompt/schema than the current plan: {stale[:6]}")
    print("Estimate for pending drafts (input = stored templated rung's measured input + added instruction; typical output = stored output):")
    for m, s in est["by_model"].items():
        print(f"  {m:<7} {s['drafts']:>3} drafts  input≈{s['input_tokens']:,} tok  ${s['typical_usd']:.3f} typical / ${s['worst_case_usd']:.3f} worst (max_tokens {ns.DRAFT_MAX_TOKENS})")
    t = est["total"]
    print(f"  total   {t['drafts']:>3} drafts  input≈{t['input_tokens']:,} tok  ${t['typical_usd']:.3f} typical / ${t['worst_case_usd']:.3f} worst")
    print(f"Budget: --max-usd ${args.max_usd:.2f}; already recorded ${guard.spent_usd:.4f}.")
    if args.dry_run:
        for i, p in enumerate(pending[: args.show], 1):
            e = ns.estimate_draft(p, replays)
            print(f"  {i:>3}. {p['draft_id']:<52} in≈{e['input_tokens']:,} worst ${e['worst_case_usd']:.4f}")
        if len(pending) > args.show:
            print(f"  ... {len(pending) - args.show} more")
        print("Dry run: no API calls made.")
        return 0
    if not pending:
        print("Nothing to do.")
        return 0
    if draft_call is None:
        key = _api_key()
        if not key:
            print("ANTHROPIC_API_KEY must be set (env or .env) for the draft phase.", file=sys.stderr)
            return 2
        draft_call = ns.make_app_draft_call(key)

    def on_record(rec: dict[str, Any]) -> None:
        append_record(out, rec)
        flag = " TRUNCATED" if rec.get("truncated") else "" if rec.get("parse_ok") or rec["status"] != "ok" else " JSON-NOT-PARSED"
        print(f"  {rec['status']:<5} {rec['draft_id']:<52} {rec.get('model_id')} stop={rec.get('stop_reason')} "
              f"in={rec.get('input_tokens')} out={rec.get('output_tokens')}{flag}{' ' + str(rec.get('error_message'))[:120] if rec['status'] != 'ok' else ''}", flush=True)

    res = await ns.run_draft_plan(pending, draft_call=draft_call, guard=guard, on_record=on_record, replays=replays, concurrency=args.concurrency)
    print(f"Done: {res['ok']} ok ({res['truncated']} truncated), {res['error']} error, {res['skipped_budget']} not launched (budget); "
          f"recorded spend ${res['spent_usd']:.4f}.")
    if res["budget_stopped"]:
        print(f"Stopped launching: the next draft's worst case could exceed --max-usd ${args.max_usd:.2f}. Re-run with a higher cap to resume.")
    return 0


async def judge_phase(args: argparse.Namespace, *, judge_call: Any = None) -> int:
    replays = qs.load_replays(args.replays)
    keys = qs.load_quality_keys()
    drafts = ns.load_jsonl(Path(args.drafts))
    scored = ns.score_drafts(drafts, keys)
    planned_keys = [p["draft_key"] for p in ns.plan_drafts(args.repeats)]
    missing = [k for k in planned_keys if k not in scored]
    standins = 0
    if missing:
        if not args.dry_run:
            print(f"{len(missing)} of {len(planned_keys)} drafts are missing from {Path(args.drafts).name}; run the draft phase first.", file=sys.stderr)
            return 2
        stand = ns.standin_drafts(replays, keys)
        for k in missing:
            scored[k] = stand[k]
        standins = len(missing)
    plan = ns.plan_judge_calls(scored, replays, repeats=args.repeats)
    bad = ns.blinding_report(plan, scored, replays)
    counts = {t: sum(1 for p in plan if p["meta"]["comparison"] == t) for t in ("rubric", "matched", "vs_unbounded")}
    out = Path(args.out)
    existing = qs.load_judgements(out)
    pending = qs.select_pending(plan, existing)
    stale = qs.stale_ok_records(plan, existing)
    cal = ns.calibrate_judge_estimate(args.baseline_judgements)
    est = qs.estimate_plan(pending, chars_per_token=cal["chars_per_token"], max_tokens=args.max_tokens, typical_output_tokens=cal["typical_output_tokens"])
    print(f"Planned {len(plan)} judge calls (rubric: {counts['rubric']}, matched pairwise: {counts['matched']}, vs stored unbounded: {counts['vs_unbounded']}); "
          f"{len(plan) - len(pending)} already ok in {out.name}, {len(pending)} pending. Judge {qs.JUDGE_MODEL}, max_tokens {args.max_tokens}.")
    if standins:
        print(f"NOTE: {standins} drafts not yet drafted; the estimate uses the stored templated drafts as stand-ins (prompt sizes approximate).")
    print(f"Blinding: {len(plan) - len(bad)}/{len(plan)} planned prompts clean." + (f" VIOLATIONS: {dict(list(bad.items())[:5])}" if bad else ""))
    if stale:
        print(f"WARNING: {len(stale)} ok records were made from a different prompt than the current plan: {stale[:6]}")
    print(f"Estimate for pending calls (chars/token {cal['chars_per_token']:.2f}; typical output {cal['typical_output_tokens']}; from {cal['source']}):")
    for task, s in est["by_task"].items():
        print(f"  {task:<9} {s['calls']:>3} calls  input≈{s['input_tokens']:,} tok  ${s['typical_usd']:.2f} typical / ${s['worst_case_usd']:.2f} worst")
    t = est["total"]
    print(f"  total     {t['calls']:>3} calls  input≈{t['input_tokens']:,} tok  ${t['typical_usd']:.2f} typical / ${t['worst_case_usd']:.2f} worst")
    guard = qs.BudgetGuard(args.max_usd, existing)
    print(f"Budget: --max-usd ${args.max_usd:.2f}; already recorded ${guard.spent_usd:.2f}. Rates are the ASSUMED Opus 5.5 rates in quality_scoring.py.")
    if bad:
        print("Refusing to judge: blinding violations.", file=sys.stderr)
        return 3
    if args.dry_run:
        print("Dry run: no API calls made.")
        return 0
    if not pending:
        print("Nothing to do.")
        return 0
    if judge_call is None:
        key = _api_key()
        if not key:
            print("ANTHROPIC_API_KEY must be set (env or .env) for the judge phase.", file=sys.stderr)
            return 2
        judge_call = qs.make_anthropic_judge_call(key)
    meta = {p["call_id"]: p["meta"] for p in plan}

    def on_record(rec: dict[str, Any]) -> None:
        rec["meta"] = meta[rec["call_id"]]
        rec["experiment"] = "cat2_not_stated"
        append_record(out, rec)
        print(f"  {rec['status']:<5} {rec['call_id']:<62} stop={rec.get('stop_reason')} in={rec.get('input_tokens')} out={rec.get('output_tokens')}"
              f"{' ' + str(rec.get('error_type')) if rec['status'] != 'ok' else ''}", flush=True)

    res = await qs.run_judge_plan(pending, judge_call=judge_call, guard=guard, on_record=on_record, concurrency=args.concurrency,
                                  max_tokens=args.max_tokens, chars_per_token=cal["chars_per_token"])
    print(f"Done: {res['ok']} ok, {res['error']} error, {res['skipped_budget']} not launched (budget); recorded spend ${res['spent_usd']:.2f}.")
    if res["budget_stopped"]:
        print(f"Stopped launching: the next call's worst case could exceed --max-usd ${args.max_usd:.2f}. Re-run with a higher cap to resume.")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="phase", required=True)
    d = sub.add_parser("draft")
    d.add_argument("--dry-run", action="store_true")
    d.add_argument("--max-usd", type=float, default=ns.DEFAULT_DRAFT_MAX_USD)
    d.add_argument("--concurrency", type=int, default=4)
    d.add_argument("--repeats", type=int, default=ns.REPEATS)
    d.add_argument("--out", default=str(ns.DRAFTS_PATH))
    d.add_argument("--replays", default=str(qs.REPLAYS_PATH))
    d.add_argument("--show", type=int, default=48, help="dry run: planned drafts to list")
    j = sub.add_parser("judge")
    j.add_argument("--dry-run", action="store_true")
    j.add_argument("--max-usd", type=float, default=ns.DEFAULT_JUDGE_MAX_USD)
    j.add_argument("--concurrency", type=int, default=4)
    j.add_argument("--repeats", type=int, default=ns.REPEATS)
    j.add_argument("--max-tokens", type=int, default=qs.JUDGE_MAX_TOKENS)
    j.add_argument("--drafts", default=str(ns.DRAFTS_PATH))
    j.add_argument("--out", default=str(ns.JUDGEMENTS_PATH))
    j.add_argument("--replays", default=str(qs.REPLAYS_PATH))
    j.add_argument("--baseline-judgements", default=str(qs.JUDGEMENTS_PATH), help="read-only; calibrates the estimate")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None, *, draft_call: Any = None, judge_call: Any = None) -> int:
    args = parse_args(argv)
    if args.phase == "draft":
        return asyncio.run(draft_phase(args, draft_call=draft_call))
    return asyncio.run(judge_phase(args, judge_call=judge_call))


if __name__ == "__main__":
    raise SystemExit(main())
