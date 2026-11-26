"""Category 1 seven-arm ablation runner.

Usage (from backend/):
    .venv/bin/python scripts/cat1_ablation.py run --dry-run          # 252 planned runs + cost estimate, no calls
    .venv/bin/python scripts/cat1_ablation.py run --max-usd 6 --concurrency 4
    .venv/bin/python scripts/cat1_ablation.py extract --dry-run      # planned extraction-judge calls + estimate + blinding check
    .venv/bin/python scripts/cat1_ablation.py extract --max-usd 8 --concurrency 4

run: 7 arms x 12 items (6 presets, 6 batch items) x 3 repeats, ordered repeat -> item -> arm, through the app's own call
wrappers (keyword overrides only: cap, prompt, model, timeout, max_retries=0, no silent tool fallback). Appends one
record per call to experiments/cat1_ablation/runs.jsonl. An ok record made with the current settings (including a
truncated one, which is flagged) is never redone; error records stay and are retried; an ok record made with different
settings is reported as superseded and its run is pending again. A missing GEMINI_API_KEY or a Gemini failure is an
error record for that run only (never substituted). --max-usd counts every recorded run at the app's rate card and
refuses a run whose worst case (estimated input + max_tokens output) could cross the cap.

extract: one blind extraction-judge pass (the Category 2 judge: model and settings from quality_scoring.py) over every
free-text run, the 24 stored prose responses of the original capture, and a seeded sample of 20 schema outputs
rendered as text. Every planned prompt is checked for blinding before anything is sent. A dry run before the runs
exist estimates with stand-ins (stored prose / stored schema output).
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

from app.archetypes.cat1_triage import ablation as ab  # noqa: E402
from app.archetypes.cat2_drafting import quality_scoring as qs  # noqa: E402


def append_record(path: Path, rec: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _keys() -> tuple[str | None, str | None]:
    try:
        from app.config import get_settings

        s = get_settings()
        return (s.anthropic_api_key or None), (s.gemini_api_key or None)
    except Exception:  # noqa: BLE001
        return None, None


async def run_phase(args: argparse.Namespace, *, calls: ab.CallPaths | None = None) -> int:
    golden = ab._golden()
    out = Path(args.out)
    existing = ab.load_jsonl(out)
    plan = ab.plan_runs(args.repeats)
    pending = ab.select_pending(plan, existing)
    sup = ab.superseded_records(existing)
    est = ab.estimate_run_plan(pending, golden)
    guard = ab.CostGuard(args.max_usd, existing)
    print(f"Planned {len(plan)} runs ({len(ab.ARM_IDS)} arms x {len(ab.ITEM_IDS)} items x {args.repeats} repeats, order repeat -> item -> arm); "
          f"{len(plan) - len(pending)} current ok in {out.name}, {len(pending)} pending.")
    if sup:
        print(f"NOTE: {len(sup)} ok records were made with different settings (superseded; pending again, excluded from analysis): "
              f"{sorted({r['run_id'] for r in sup})[:6]}")
    print("Estimate for pending runs (input = the original capture's measured input for that item and call path, adjusted for the "
          f"prompt-length difference at 3 chars/token; typical output ASSUMED {est['typical_output_assumed']}; worst = max_tokens output):")
    for a, s in est["by_arm"].items():
        cap = ab.CAPS.get(ab.ARM_BY_ID[a].task, 0)
        print(f"  {a:<21} {s['runs']:>3} runs  input≈{s['input_tokens']:,} tok  ${s['typical_usd']:.3f} typical / ${s['worst_case_usd']:.3f} worst (max_tokens {cap or '—'})")
    t = est["total"]
    print(f"  {'total':<21} {t['runs']:>3} runs  input≈{t['input_tokens']:,} tok  ${t['typical_usd']:.3f} typical / ${t['worst_case_usd']:.3f} worst")
    print(f"Budget: --max-usd ${args.max_usd:.2f}; already recorded ${guard.spent_usd:.4f}.")
    anth, gem = _keys()
    if not gem:
        print("NOTE: GEMINI_API_KEY is not set; every gemini_decision run will be recorded as status=error (no substitution).")
    if args.dry_run:
        for i, p in enumerate(pending[: args.show], 1):
            e = ab.estimate_run(p, golden)
            print(f"  {i:>3}. {p['run_id']:<34} in≈{e['input_tokens']:,} worst ${e['worst_case_usd']:.4f}")
        if args.show and len(pending) > args.show:
            print(f"  ... {len(pending) - args.show} more")
        print("Dry run: no API calls made.")
        return 0
    if not pending:
        print("Nothing to do.")
        return 0
    if calls is None:
        if not anth:
            print("ANTHROPIC_API_KEY must be set (env or .env) for the run phase.", file=sys.stderr)
            return 2
        calls = ab.make_app_call_paths(anth, gem)

    def on_record(rec: dict[str, Any]) -> None:
        append_record(out, rec)
        flag = " TRUNCATED" if rec.get("truncated") else ""
        if rec.get("model_matches") is False:
            flag += f" MODEL-MISMATCH({rec.get('model_returned')})"
        if rec["arm_id"].endswith("_schema") and rec["status"] == "ok" and not rec.get("schema_parse_ok"):
            flag += " JSON-NOT-PARSED"
        print(f"  {rec['status']:<5} {rec['run_id']:<34} stop={rec.get('stop_reason')} in={rec.get('input_tokens')} out={rec.get('output_tokens')} "
              f"think={rec.get('thinking_tokens')}{flag}{' ' + str(rec.get('error_message'))[:140] if rec['status'] != 'ok' else ''}", flush=True)

    res = await ab.run_plan(pending, calls=calls, guard=guard, on_record=on_record, concurrency=args.concurrency, golden=golden)
    print(f"Done: {res['ok']} ok ({res['truncated']} truncated), {res['error']} error, {res['skipped_budget']} not launched (budget); "
          f"recorded spend ${res['spent_usd']:.4f}.")
    if res["budget_stopped"]:
        print(f"Stopped launching: the next run's worst case could exceed --max-usd ${args.max_usd:.2f}. Re-run with a higher cap to resume.")
    return 0


async def extract_phase(args: argparse.Namespace, *, judge_call: Any = None) -> int:
    golden = ab._golden()
    runs = ab.latest_ok_current(ab.load_jsonl(Path(args.runs)))
    planned_free = [p["run_id"] for p in ab.plan_runs(args.repeats) if p["arm_id"] in ab.FREE_TEXT_ARMS]
    missing = [k for k in planned_free if k not in runs]
    standins = 0
    if missing or not any(r["arm_id"].endswith("_schema") for r in runs.values()):
        if not args.dry_run and missing:
            print(f"NOTE: {len(missing)} of {len(planned_free)} free-text runs have no current ok record; only existing runs are extracted "
                  "(re-run extract after the run phase completes to fill the rest).")
        if args.dry_run:
            stand = ab.standin_run_records(golden)
            for k, v in stand.items():
                if k not in runs:
                    runs[k] = v
                    standins += 1
    targets = ab.extraction_targets(runs, golden)
    plan = ab.plan_extractions(targets)
    bad = ab.blinding_report(plan, runs)
    counts = {s: sum(1 for p in plan if p["source"] == s) for s in ("run", "golden", "schema_check")}
    out = Path(args.out)
    existing = ab.load_jsonl(out)
    pending = ab.select_pending_extractions(plan, existing)
    stale = qs.stale_ok_records(plan, existing)
    cal = ab.calibrate_judge_estimate()
    est = qs.estimate_plan(pending, chars_per_token=cal["chars_per_token"], max_tokens=args.max_tokens, typical_output_tokens=cal["typical_output_tokens"])
    print(f"Planned {len(plan)} extraction calls (free-text runs: {counts['run']}, original capture: {counts['golden']}, schema-as-text check: "
          f"{counts['schema_check']}); {len(plan) - len(pending)} already ok in {out.name}, {len(pending)} pending. Judge {qs.JUDGE_MODEL}, "
          f"max_tokens {args.max_tokens}, thinking {qs.JUDGE_THINKING}, effort {qs.JUDGE_EFFORT}, one pass.")
    if standins:
        print(f"NOTE: {standins} runs do not exist yet; the estimate uses stand-ins (stored prose for report arms, stored schema output rendered as "
              "text for classify-text arms and the schema check). Prompt sizes are approximate.")
    print(f"Blinding: {len(plan) - len(bad)}/{len(plan)} planned prompts clean." + (f" VIOLATIONS: {dict(list(bad.items())[:5])}" if bad else ""))
    if stale:
        print(f"NOTE: {len(stale)} ok records were made from a different prompt/text than the current plan (pending again): {stale[:6]}")
    print(f"Estimate for pending calls (chars/token {cal['chars_per_token']:.2f}; typical output {cal['typical_output_tokens']}; {cal['source']}):")
    for task, s in est["by_task"].items():
        print(f"  {task:<10} {s['calls']:>3} calls  input≈{s['input_tokens']:,} tok  ${s['typical_usd']:.2f} typical / ${s['worst_case_usd']:.2f} worst")
    guard = qs.BudgetGuard(args.max_usd, existing)
    print(f"Budget: --max-usd ${args.max_usd:.2f}; already recorded ${guard.spent_usd:.2f}. Rates are the ASSUMED Opus 5.5 rates in quality_scoring.py.")
    if bad:
        print("Refusing to extract: blinding violations.", file=sys.stderr)
        return 3
    if args.dry_run:
        print("Dry run: no API calls made.")
        return 0
    if not pending:
        print("Nothing to do.")
        return 0
    if judge_call is None:
        anth, _ = _keys()
        if not anth:
            print("ANTHROPIC_API_KEY must be set (env or .env) for the extract phase.", file=sys.stderr)
            return 2
        judge_call = qs.make_anthropic_judge_call(anth)

    def on_record(rec: dict[str, Any]) -> None:
        rec["experiment"] = "cat1_ablation"
        append_record(out, rec)
        print(f"  {rec['status']:<5} {rec['call_id']:<52} stop={rec.get('stop_reason')} in={rec.get('input_tokens')} out={rec.get('output_tokens')}"
              f"{' ' + str(rec.get('error_type')) + ': ' + str(rec.get('error_message'))[:100] if rec['status'] != 'ok' else ''}", flush=True)

    res = await ab.run_extraction_plan(pending, judge_call=judge_call, guard=guard, on_record=on_record, concurrency=args.concurrency,
                                       max_tokens=args.max_tokens, chars_per_token=cal["chars_per_token"])
    print(f"Done: {res['ok']} ok, {res['error']} error, {res['skipped_budget']} not launched (budget); recorded spend ${res['spent_usd']:.2f}.")
    if res["budget_stopped"]:
        print(f"Stopped launching: the next call's worst case could exceed --max-usd ${args.max_usd:.2f}. Re-run with a higher cap to resume.")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="phase", required=True)
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--max-usd", type=float, default=ab.DEFAULT_RUN_MAX_USD)
    r.add_argument("--concurrency", type=int, default=4)
    r.add_argument("--repeats", type=int, default=ab.REPEATS)
    r.add_argument("--out", default=str(ab.RUNS_PATH))
    r.add_argument("--show", type=int, default=0, help="dry run: planned runs to list")
    e = sub.add_parser("extract")
    e.add_argument("--dry-run", action="store_true")
    e.add_argument("--max-usd", type=float, default=ab.DEFAULT_EXTRACT_MAX_USD)
    e.add_argument("--concurrency", type=int, default=4)
    e.add_argument("--repeats", type=int, default=ab.REPEATS)
    e.add_argument("--max-tokens", type=int, default=qs.JUDGE_MAX_TOKENS)
    e.add_argument("--runs", default=str(ab.RUNS_PATH))
    e.add_argument("--out", default=str(ab.EXTRACTIONS_PATH))
    return ap.parse_args(argv)


def main(argv: list[str] | None = None, *, calls: ab.CallPaths | None = None, judge_call: Any = None) -> int:
    args = parse_args(argv)
    if args.phase == "run":
        return asyncio.run(run_phase(args, calls=calls))
    return asyncio.run(extract_phase(args, judge_call=judge_call))


if __name__ == "__main__":
    raise SystemExit(main())
