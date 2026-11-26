"""Run the Category 4 quality-rerun matrix live and append one JSONL record per session.

Usage (from backend/):
    .venv/bin/python scripts/cat4_quality_rerun.py --dry-run
    .venv/bin/python scripts/cat4_quality_rerun.py --repeats 3 --max-usd 20

One session = one rung answering the 8 audit questions in order (audit-01 q1-q4, then audit-02 q1-q4) on one
corpus scale. Questions inside a session run sequentially; sessions run concurrently (--concurrency).
Append-only and resumable: a (rung, scale, repeat) key with an `ok` record at the current settings (synthesis cap and
the rung's synthesis prompt, `answer_formats.RUNG_ANSWER_FORMAT`) is skipped; `error` records stay in the file and their
key is retried. No answer is ever dropped for a quality reason (zero-citation answers, truncations and contamination
are data). Records hold tokens only; dollars are computed at analysis time.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("NOVAMART_TRACES_DIR", str(Path(tempfile.gettempdir()) / "novamart_cat4_quality_rerun"))

from app.archetypes.cat4_rag.quality_rerun import (  # noqa: E402
    HARNESS_RUNG_IDS,
    RUNG_IDS,
    RUNS_PATH,
    SCALES,
    SYNTH_MAX_TOKENS,
    BudgetGuard,
    build_scaled_corpus,
    calibrate_chars_per_token,
    corpus_size,
    answer_format_of,
    estimate_judge_plan,
    estimate_session,
    is_current_settings,
    latest_ok_sessions,
    load_golden,
    load_jsonl,
    load_quality_keys,
    plan_judge_calls,
    plan_matrix,
    prompt_tokens,
    run_sessions,
    select_pending,
    session_billed_usd,
)

BUDGET_EXIT_CODE = 2


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _session_line(rec: dict[str, Any]) -> str:
    answers = rec.get("answers") or []
    calls = [c for a in answers for c in a.get("calls") or []]
    cites = [len(a.get("citations") or []) for a in answers if a.get("status") == "ok"]
    stops = sorted({str(c.get("stop_reason")) for c in calls})
    line = (f"{rec['rung_id']:<30} scale={rec['scale']} r{rec['repeat_index']} {answer_format_of(rec)} | answers {len(answers)}/8 | "
            f"prompt={sum(prompt_tokens(c) for c in calls):,} out={sum(int(c.get('output_tokens') or 0) for c in calls):,} | "
            f"citations/answer={cites} | stop={','.join(stops)} | billed=${session_billed_usd(rec):.4f} | wall={rec.get('wall_s', 0):.1f}s")
    if rec.get("status") != "ok":
        line += f" | STATUS=error {rec.get('error_message')}"
    return line


async def main(args: argparse.Namespace) -> int:
    rungs = _csv(args.rungs) if args.rungs else list(RUNG_IDS)
    scales = [int(s) for s in _csv(args.scales)] if args.scales else list(SCALES)
    bad = [r for r in rungs if r not in HARNESS_RUNG_IDS] + [s for s in scales if s not in SCALES]
    if bad:
        print(f"Unknown rung/scale: {bad}", file=sys.stderr)
        return 1
    keys = load_quality_keys()
    out_path = Path(args.out)
    existing = load_jsonl(out_path)
    planned = plan_matrix(rungs, scales, args.repeats)
    pending = select_pending(planned, existing)
    guard = BudgetGuard(args.max_usd, existing)
    cpt = calibrate_chars_per_token(load_golden())
    est = {(r, s): estimate_session(r, s, cpt) for r in rungs for s in scales}

    print(f"Matrix: {len(rungs)} rungs x scales {scales} x {args.repeats} repeats = {len(planned)} sessions "
          f"({len(planned) * 8} answers); {len(planned) - len(pending)} already ok, {len(pending)} pending.")
    superseded = [r for r in existing if not is_current_settings(r)]
    if superseded:
        print(f"Records not at the current settings (synth_max_tokens {SYNTH_MAX_TOKENS}, rung prompt): {len(superseded)}; ignored.")
    print(f"Existing records: {len(existing)}; billed so far ${guard.spent_usd:.4f} of ${args.max_usd:.2f} cap.")
    print(f"Answer key {keys['meta'].get('keys_version')} · output {out_path}")
    for s in scales:
        print(f"Corpus scale {s}: {corpus_size(build_scaled_corpus(s))}")
    print(f"Chars/token calibrated on the golden replays: plain {cpt.plain:.2f}, doc blocks {cpt.doc_blocks:.2f}, rerank {cpt.rerank:.2f}")

    if args.dry_run:
        print("\nPer-session estimate (USD; typical output vs worst case = every call hits max_tokens):")
        for (r, s), e in est.items():
            print(f"  {r:<30} scale={s}  prompt≈{e['prompt_tokens']:>8,} tok  max rerank prompt≈{e['max_rerank_prompt_tokens']:>7,}"
                  f"  typical ${e['typical_usd']:.4f}  worst ${e['worst_case_usd']:.4f}")
        typ = sum(est[(k[0], k[1])]["typical_usd"] for k in pending)
        worst = sum(est[(k[0], k[1])]["worst_case_usd"] for k in pending)
        print(f"\nPending sessions ({len(pending)}): typical ≈ ${typ:.2f}, worst case ≈ ${worst:.2f} "
              f"(cap ${args.max_usd:.2f} includes the ${guard.spent_usd:.2f} already billed: a live run needs "
              f"--max-usd ≥ {guard.spent_usd + worst:.2f} to launch every pending session).")
        for i, k in enumerate(pending, 1):
            print(f"  {i:>3}. repeat={k[2]} scale={k[1]} {k[0]}")
        jest = judge_estimate_for(pending, existing)
        if jest:
            print(f"\nJudging the {jest['answers']} answers these sessions would produce (scripts/cat4_quality_judge.py, same "
                  f"prompt and path; proxy answers = the existing answers of the same rung x scale): "
                  f"typical ≈ ${jest['typical_usd']:.2f}, worst case ≈ ${jest['worst_case_usd']:.2f} "
                  f"(prefix ≈{jest['prefix_tokens_est']:,} tok, user ≈{jest['user_tokens_est']:,} tok).")
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

    def on_record(rec: dict[str, Any]) -> None:
        rec["keys_version"] = keys["meta"].get("keys_version")
        with out_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        print(_session_line(rec), flush=True)

    result = await run_sessions(pending, api_key=api_key, guard=guard,
                                worst_case_usd=lambda k: est[(k[0], k[1])]["worst_case_usd"],
                                on_record=on_record, concurrency=args.concurrency)
    print(f"Finished {result['ok']} ok + {result['error']} error sessions; billed total ${result['spent_usd']:.4f} (cap ${args.max_usd:.2f}).")
    if result["budget_stopped"]:
        print(f"BUDGET STOP: {result['skipped_budget']} sessions not launched because their worst case would cross "
              f"--max-usd ${args.max_usd:.2f}. Re-run with a higher cap to resume.")
        return BUDGET_EXIT_CODE
    return 0


def judge_estimate_for(pending: list[Any], existing: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Judge cost for the answers the pending sessions would produce, using the existing answers of the same
    rung x scale as stand-ins for their length (None when no stand-in exists)."""
    proxies = {(r["rung_id"], int(r["scale"])): r for r in latest_ok_sessions(existing)}
    items = []
    for k in pending:
        rec = proxies.get((k[0], k[1]))
        if rec is None:
            return None
        for a in rec["answers"]:
            items.append({**a, "source": "rerun", "rung_id": k[0], "scale": k[1], "repeat_index": k[2],
                          "run_id": "dry-run", "answer_format": answer_format_of(rec)})
    if not items:
        return None
    return {"answers": len(items), **estimate_judge_plan(plan_judge_calls(items))}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument(
        "--rungs",
        default="",
        help=f"comma list (default the two displayed versions: {','.join(RUNG_IDS)}; cached_full_corpus_citations is "
        "another lever — write it to experiments/cat4_quality/other_levers/ with --out)",
    )
    ap.add_argument("--scales", default="", help="comma list (default 1,3)")
    ap.add_argument("--concurrency", type=int, default=3, help="concurrent sessions (default 3)")
    ap.add_argument("--max-usd", type=float, default=20.0, help="billed-cost cap incl. existing records (default 20)")
    ap.add_argument("--out", default=str(RUNS_PATH), help="append-only JSONL path")
    ap.add_argument("--dry-run", action="store_true", help="print plan + cost estimate and exit")
    return ap.parse_args(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
