"""Capture the Category 2 single-section regenerations on the current golden template drafts.

Usage (from backend/):
    .venv/bin/python scripts/capture_cat2_section_regens.py --dry-run          # 32 planned calls + cost estimate, no calls
    .venv/bin/python scripts/capture_cat2_section_regens.py --max-usd 0.5 --concurrency 4
    .venv/bin/python scripts/build_cat2_golden_from_experiment.py              # writes the golden section_regens block

4 presets x 2 templated models (Sonnet 5.5, Haiku 5.5) x 4 sections = 32 calls, each the app's own regenerate-section
request (system prompt, single-section schema, payload, canonical reviewer instruction, max_tokens 1,800, thinking
settings) against that preset's current repeat-0 templated draft of the same model in replays/cat2_golden_replays.json.
Run it after the golden file has been rebuilt from the current drafts.

Appends one record per call to experiments/cat2_not_stated/section_regens.jsonl (full prompt and response, no
dollars). An ok record, truncated or not, is never redone. An error record stays in the file, is listed here, and its
key is sent again on the next run. --max-usd counts every recorded call at the app's rate card and refuses a call whose
worst case (estimated input + 1,800 output tokens) could cross the cap.
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
from app.archetypes.cat2_drafting import section_regen_capture as rc  # noqa: E402


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


async def run(args: argparse.Namespace, *, regen_call: Any = None) -> int:
    golden_path = Path(args.golden)
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    src = (golden.get("provenance") or {}).get("source")
    if src != "cat2_experiment_repeat0":
        print(f"{golden_path.name} provenance.source is {src!r}, not 'cat2_experiment_repeat0'; rebuild it first "
              "(scripts/build_cat2_golden_from_experiment.py).", file=sys.stderr)
        return 2
    try:
        plan = rc.plan_regens(golden)
    except rc.BaseDraftMissing as exc:
        print(f"Cannot plan: {exc}", file=sys.stderr)
        return 2
    out = Path(args.out)
    existing = rc.load_records(out)
    pending = rc.select_pending(plan, existing)
    stale = rc.stale_keys(plan, existing)
    errors = rc.error_records(existing)
    cpt = rc.chars_per_token(golden, existing)
    typical = rc.typical_output_tokens(existing)
    guard = ns.CostGuard(args.max_usd, existing)
    print(f"Planned {len(plan)} regenerations ({len(qs.PRESET_IDS)} presets x {len(rc.MODEL_KEYS)} models x {len(rc.SECTION_KEYS)} sections) "
          f"on the repeat-0 templated drafts in {golden_path.name}; {len(plan) - len(pending)} current ok in {out.name}, {len(pending)} pending.")
    if stale:
        print(f"Stale: {len(stale)} keys have ok records made on a different prompt, base draft or schema (kept in the file, "
              f"not used): {stale[:6]}")
    if errors:
        print(f"Error records in the file: {len(errors)} (kept; their keys are pending again):")
        for r in errors[:10]:
            print(f"  {r.get('regen_key')}: {str(r.get('error_message'))[:140]}")
    by: dict[str, dict[str, Any]] = {}
    for p in pending:
        e = rc.estimate(p, cpt, typical)
        s = by.setdefault(p["model_key"], {"calls": 0, "input_tokens": 0, "typical_usd": 0.0, "worst_case_usd": 0.0})
        s["calls"] += 1
        s["input_tokens"] += e["input_tokens"]
        s["typical_usd"] += e["typical_usd"]
        s["worst_case_usd"] += e["worst_case_usd"]
    print(f"Estimate for pending calls (input = prompt chars / {cpt:.3f} chars per token; typical output = "
          f"{', '.join(f'{m} {typical[m]}' for m in rc.MODEL_KEYS)} tokens; worst = {rc.SECTION_REGEN_MAX_TOKENS:,} output tokens):")
    for m, s in by.items():
        print(f"  {m:<8} {s['calls']:>3} calls  input≈{s['input_tokens']:,} tok  ${s['typical_usd']:.3f} typical / ${s['worst_case_usd']:.3f} worst")
    tot = {k: sum(s[k] for s in by.values()) for k in ("calls", "input_tokens", "typical_usd", "worst_case_usd")}
    print(f"  {'total':<8} {tot['calls']:>3} calls  input≈{tot['input_tokens']:,} tok  ${tot['typical_usd']:.3f} typical / ${tot['worst_case_usd']:.3f} worst")
    print(f"Budget: --max-usd ${args.max_usd:.2f}; already recorded ${guard.spent_usd:.4f}.")
    if args.dry_run:
        for i, p in enumerate(pending[: args.show], 1):
            e = rc.estimate(p, cpt, typical)
            print(f"  {i:>3}. {p['regen_key']:<52} base {p['base_draft_id']}  in≈{e['input_tokens']:,} worst ${e['worst_case_usd']:.4f}")
        if len(pending) > args.show:
            print(f"  ... {len(pending) - args.show} more")
        print("Dry run: no API calls made.")
        return 0
    if not pending:
        print("Nothing to do.")
        return 0
    if regen_call is None:
        key = _api_key()
        if not key:
            print("ANTHROPIC_API_KEY must be set (env or .env).", file=sys.stderr)
            return 2
        regen_call = rc.make_app_regen_call(key)

    def on_record(rec: dict[str, Any]) -> None:
        append_record(out, rec)
        flag = " TRUNCATED" if rec.get("truncated") else "" if rec.get("parse_ok") or rec["status"] != "ok" else " SECTION-NOT-PARSED"
        print(f"  {rec['status']:<5} {rec['regen_key']:<52} {rec.get('model_id')} stop={rec.get('stop_reason')} "
              f"in={rec.get('input_tokens')} out={rec.get('output_tokens')}{flag}"
              f"{' ' + str(rec.get('error_message'))[:120] if rec['status'] != 'ok' else ''}", flush=True)

    res = await rc.run_plan(pending, regen_call=regen_call, guard=guard, on_record=on_record, cpt=cpt, typical=typical, concurrency=args.concurrency)
    print(f"Done: {res['ok']} ok ({res['truncated']} truncated, {res['not_parsed']} section not parsed), {res['error']} error, "
          f"{res['skipped_budget']} not launched (budget); recorded spend ${res['spent_usd']:.4f}.")
    if res["error"]:
        print("Error records were written; re-run to send those keys again.")
    if res["budget_stopped"]:
        print(f"Stopped launching: the next call's worst case could exceed --max-usd ${args.max_usd:.2f}. Re-run with a higher cap to resume.")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-usd", type=float, default=rc.DEFAULT_MAX_USD)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--golden", default=str(qs.REPLAYS_PATH))
    ap.add_argument("--out", default=str(rc.REGENS_PATH))
    ap.add_argument("--show", type=int, default=32, help="dry run: planned calls to list")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None, *, regen_call: Any = None) -> int:
    return asyncio.run(run(parse_args(argv), regen_call=regen_call))


if __name__ == "__main__":
    raise SystemExit(main())
