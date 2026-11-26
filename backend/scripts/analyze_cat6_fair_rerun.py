"""Summarise Category 6 fair-rerun records into a markdown report + JSON summary.

Usage (from backend/):
    .venv/bin/python scripts/analyze_cat6_fair_rerun.py
    .venv/bin/python scripts/analyze_cat6_fair_rerun.py --in path/to/runs.jsonl --repeats 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat6_swarms.fair_rerun import (  # noqa: E402
    ARMS,
    GOVERNED_ROLE_MAX_TOKENS,
    PATCH_AUTHOR_MAX_TOKENS,
    SHARED_BUS_ORIGINAL_MAX_TOKENS,
    summarise,
)
from app.archetypes.cat6_swarms.sandbox_verifier import evaluate_patch_in_sandbox  # noqa: E402

DEFAULT_IN = BACKEND_DIR / "experiments" / "cat6_fair_rerun" / "runs.jsonl"
DEFAULT_OUT_MD = PROJECT_DIR / "analysis" / "cat6_fair_rerun.md"


def load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.is_file():
        return records
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"WARNING: skipping malformed JSONL line {lineno} in {path}", file=sys.stderr)
    return records


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _ci(ci: tuple[float, float] | list[float] | None) -> str:
    return "n/a" if not ci else f"{ci[0] * 100:.1f}–{ci[1] * 100:.1f}%"


def _usd(x: float | None, digits: int = 4) -> str:
    return "n/a" if x is None else f"${x:,.{digits}f}"


def _tok(d: dict[str, float | None]) -> str:
    if d["mean"] is None:
        return "n/a"
    return f"{d['mean']:,.0f} ({d['min']:,.0f}–{d['max']:,.0f})"


def render_markdown(summary: dict[str, Any]) -> str:
    arms = summary["arms"]
    m = summary["matrix"]
    lines: list[str] = []
    add = lines.append

    add("# Category 6 fair rerun — results")
    add("")
    add(f"Generated: {summary['generated_at']}")
    add("")
    add(
        f"Records read: {summary['record_count']} · ok runs used (latest ok per key): {summary['ok_runs_used']} · "
        f"superseded ok records: {summary['superseded_ok_records']} · error records: {summary['error_records']} · "
        f"expected matrix: {len(summary['arm_ids'])} arms × {len(summary['preset_ids'])} presets × "
        f"{summary['expected_repeats']} repeats = {m['expected_runs']} runs "
        f"({'complete' if m['complete'] else 'INCOMPLETE'}, {'balanced' if m['balanced'] else 'UNBALANCED'})."
    )
    add("")
    add("## Arms")
    add("")
    add("| Arm | Context | Role instructions | Models | Sandbox gate + 1 retry | Output caps |")
    add("|---|---|---|---|---|---|")
    governed_caps = ", ".join(f"{k} {v}" for k, v in GOVERNED_ROLE_MAX_TOKENS.items())
    for arm_id in summary["arm_ids"]:
        spec = ARMS[arm_id]
        caps = (
            f"all roles {SHARED_BUS_ORIGINAL_MAX_TOKENS}"
            if arm_id == "shared_bus_original"
            else f"patch_author {PATCH_AUTHOR_MAX_TOKENS}; {governed_caps}"
        )
        add(
            f"| `{arm_id}` | {spec.context_summary} | {spec.instructions_summary} | {spec.models_summary} | "
            f"{'yes' if spec.gate_enabled else 'no (scored once, no retry)'} | {caps} |"
        )
    add("")

    add("## Main results (per arm)")
    add("")
    add(
        "| Arm | Runs (ok) | Errors | First-attempt verified | 95% CI | Final verified | 95% CI | "
        "Checks first | Checks final | Retries (fail→pass) | Billed $/1k runs | Cold $/1k runs | Warm $/1k runs | "
        "CpO billed | CpO cold | CpO warm | Mean model latency (s) |"
    )
    add("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for arm_id in summary["arm_ids"]:
        a = arms[arm_id]
        cpo = a["cost_per_verified_outcome_usd"]
        lat = a["model_latency_ms_per_run"]["mean"]
        add(
            f"| `{arm_id}` | {a['runs']} | {a['error_records']} | "
            f"{a['first_attempt_verified']}/{a['runs']} ({_pct(a['first_attempt_verified_rate'])}) | "
            f"{_ci(a['first_attempt_verified_wilson95'])} | "
            f"{a['final_verified']}/{a['runs']} ({_pct(a['final_verified_rate'])}) | {_ci(a['final_verified_wilson95'])} | "
            f"{a['first_attempt_checks_passed']}/{a['first_attempt_checks_total']} | "
            f"{a['final_checks_passed']}/{a['final_checks_total']} | "
            f"{a['retries_used']} ({a['retries_fail_to_pass']}) | "
            f"{_usd(a['cost_per_1k_runs_usd']['billed'], 2)} | "
            f"{_usd(a['cost_per_1k_runs_usd']['cold'], 2)} | {_usd(a['cost_per_1k_runs_usd']['warm'], 2)} | "
            f"{_usd(cpo['billed'])} | {_usd(cpo['cold'])} | {_usd(cpo['warm'])} | "
            f"{'n/a' if lat is None else f'{lat / 1000:.1f}'} |"
        )
    add("")
    add("CpO = total spend across all ok runs in the arm ÷ final-verified runs (n/a when zero verified).")
    add("CpO using first-attempt verification instead:")
    add("")
    add("| Arm | CpO billed (first attempt) | CpO cold (first attempt) | CpO warm (first attempt) |")
    add("|---|---|---|---|")
    for arm_id in summary["arm_ids"]:
        c = arms[arm_id]["cost_per_first_attempt_verified_outcome_usd"]
        add(f"| `{arm_id}` | {_usd(c['billed'])} | {_usd(c['cold'])} | {_usd(c['warm'])} |")
    add("")

    add("### Tokens per run (mean, min–max)")
    add("")
    add("| Arm | Uncached input | Cache write | Cache read | Output | Thinking |")
    add("|---|---|---|---|---|---|")
    for arm_id in summary["arm_ids"]:
        t = arms[arm_id]["tokens_per_run"]
        add(
            f"| `{arm_id}` | {_tok(t['uncached_input'])} | {_tok(t['cache_write'])} | {_tok(t['cache_read'])} | "
            f"{_tok(t['output'])} | {_tok(t['thinking'])} |"
        )
    add("")

    add("## Per incident")
    add("")
    add(
        "| Arm | Preset | Runs (ok) | Errors | First-attempt verified | Final verified | Checks first | "
        "Checks final | Retries (fail→pass) | Billed $/1k runs | Cold $/1k runs | Warm $/1k runs | CpO billed |"
    )
    add("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for arm_id in summary["arm_ids"]:
        for pid in summary["preset_ids"]:
            p = arms[arm_id]["by_preset"][pid]
            add(
                f"| `{arm_id}` | {pid} | {p['runs']} | {p['error_records']} | "
                f"{p['first_attempt_verified']}/{p['runs']} | {p['final_verified']}/{p['runs']} | "
                f"{p['first_attempt_checks_passed']}/{p['first_attempt_checks_total']} | "
                f"{p['final_checks_passed']}/{p['final_checks_total']} | "
                f"{p['retries_used']} ({p['retries_fail_to_pass']}) | "
                f"{_usd(p['cost_per_1k_runs_usd']['billed'], 2)} | "
                f"{_usd(p['cost_per_1k_runs_usd']['cold'], 2)} | {_usd(p['cost_per_1k_runs_usd']['warm'], 2)} | "
                f"{_usd(p['cost_per_verified_outcome_usd']['billed'])} |"
            )
    add("")

    add("## Runs whose final patch was not verified")
    add("")
    add(
        "| Arm | Final-failed runs | Runs failing ci_unit | Runs failing adversarial | Runs failing ast | "
        "Failing checks ci_unit / adversarial / ast | Patch author stopped on max_tokens | No fenced patch |"
    )
    add("|---|---|---|---|---|---|---|---|")
    for arm_id in summary["arm_ids"]:
        f = arms[arm_id]["failure_breakdown"]
        rc = f["runs_with_failing_category"]
        cc = f["failing_checks_by_category"]
        add(
            f"| `{arm_id}` | {f['final_failed_runs']} | {rc.get('ci_unit', 0)} | {rc.get('adversarial', 0)} | "
            f"{rc.get('ast', 0)} | {cc.get('ci_unit', 0)} / {cc.get('adversarial', 0)} / {cc.get('ast', 0)} | "
            f"{f['patch_author_stopped_on_max_tokens']} | {f['no_fenced_patch_extracted']} |"
        )
    add("")

    add("## Data quality")
    add("")
    add(f"- Error records: {summary['error_records']} (billed ${summary['error_spend_usd']:.4f}, excluded from CpO).")
    for e in summary["errors"]:
        add(
            f"  - `{e['arm_id']}` {e['preset_id']} r{e['repeat_index']} — {e['completed_turns']} turns completed, "
            f"${e['billed_usd']:.4f}: {str(e['error_message'])[:300]}"
        )
    add(
        f"- Matrix: {'complete' if m['complete'] else 'incomplete'}, {'balanced' if m['balanced'] else 'unbalanced'} "
        f"({len(m['missing_keys'])} missing keys)."
    )
    for k in m["missing_keys"]:
        add(f"  - missing `{k[0]}` {k[1]} r{k[2]}")
    add("- Turns stopped on `max_tokens` (ok runs):")
    add("")
    add("| Arm | Stopped / total turns | By role (stopped/total) |")
    add("|---|---|---|")
    for arm_id in summary["arm_ids"]:
        s = arms[arm_id]["max_tokens_stops"]
        roles = ", ".join(f"{r} {v['max_tokens']}/{v['total']}" for r, v in s["by_role"].items())
        add(f"| `{arm_id}` | {s['turns']}/{s['total_turns']} | {roles or 'n/a'} |")
    add("")
    mt = summary["max_tokens_stopped_turns"]
    add(f"- Individual turns stopped on `max_tokens` (ok runs used + error records): {len(mt)}.")
    for x in mt:
        add(
            f"  - `{x['arm_id']}` {x['preset_id']} r{x['repeat_index']} ({x['status']}) step {x['step_number']} "
            f"`{x['agent_role']}` attempt {x['attempt']}: cap {x['max_tokens']}, output {x['output_tokens']}"
        )
    add("")
    fb = summary["model_fallbacks"]
    add(f"- Turns where the returned model differs from the intended model: {len(fb)}.")
    for x in fb:
        add(
            f"  - `{x['arm_id']}` {x['preset_id']} r{x['repeat_index']} ({x['status']}) step {x['step_number']} "
            f"`{x['agent_role']}`: intended `{x['intended_model_id']}`, got `{x['model_id']}`"
        )
    add("")

    rs = summary.get("rescored")
    if rs is not None:
        lines.extend(render_rescored_section(rs, summary["arm_ids"]))

    add("## How to read the cost views")
    add("")
    add(
        "- **Billed**: each turn priced from the tokens the API reported (uncached input, cache write, cache read, "
        "output) at the returned model's rates in `app/core/pricing.py`. Output tokens include any thinking tokens."
    )
    add(
        "- **Cold**: for the cached arms, the repo prefix on a turn is cache_creation + cache_read tokens; the first "
        "call per model in a run is priced as writing the whole prefix and later calls as reading it. This is the "
        "same rule as `runner._compute_step_cold_warm`. Uncached arms: cold = billed."
    )
    add(
        "- **Warm**: every call in a cached arm is priced as reading the prefix (a cache already warmed by earlier "
        "traffic). Uncached arms: warm = billed."
    )
    add(
        "- Each cached-arm run uses a fresh nonce in its prefix, so billed should be close to cold; any difference "
        "comes from how the API reported cache writes/reads within the run."
    )
    add("- $/1k runs = mean cost per run × 1,000. CpO is in $ per verified outcome.")
    add("")
    return "\n".join(lines)


def render_rescored_section(rs: dict[str, Any], arm_ids: list[str]) -> list[str]:
    lines: list[str] = []
    add = lines.append
    add("## Re-scored with the current sandbox")
    add("")
    add(f"{rs['note']} The as-recorded tables above are unchanged.")
    add("")
    add(
        "| Arm | Runs | First-attempt verified (recorded → re-scored) | Final verified (recorded → re-scored) | "
        "Final checks re-scored | CpO billed | CpO cold | CpO warm |"
    )
    add("|---|---|---|---|---|---|---|---|")
    for arm_id in arm_ids:
        a = rs["arms"][arm_id]
        cpo = a["cost_per_verified_outcome_usd_rescored"]
        add(
            f"| `{arm_id}` | {a['runs']} | {a['first_attempt_verified_recorded']} → {a['first_attempt_verified_rescored']} | "
            f"{a['final_verified_recorded']} → {a['final_verified_rescored']} | "
            f"{a['final_checks_passed_rescored']}/{a['final_checks_total']} | "
            f"{_usd(cpo['billed'])} | {_usd(cpo['cold'])} | {_usd(cpo['warm'])} |"
        )
    add("")
    changes = rs["changes"]
    add(f"Records whose verdict or passed-check count changed: {len(changes)}.")
    for c in changes:
        flips = ", ".join(
            f"{f['check_id']} {'PASS' if f['recorded_passed'] else 'FAIL'}→{'PASS' if f['rescored_passed'] else 'FAIL'}"
            for f in c["flipped_checks"]
        )
        add(
            f"- `{c['arm_id']}` {c['preset_id']} r{c['repeat_index']} ({c['attempt']}): "
            f"{c['recorded_passed_checks']}/{c['recorded_total_checks']} (verified={c['recorded_verified']}) → "
            f"{c['rescored_passed_checks']}/{c['rescored_total_checks']} (verified={c['rescored_verified']}); "
            f"flipped: {flips or 'none'}"
        )
    add("")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="in_path", default=str(DEFAULT_IN))
    ap.add_argument("--out-md", default=str(DEFAULT_OUT_MD))
    ap.add_argument("--out-json", default=None, help="default: --out-md with a .json suffix")
    ap.add_argument("--repeats", type=int, default=None, help="expected repeats (default: inferred from records)")
    ap.add_argument(
        "--rescore",
        action="store_true",
        help="also re-run the current sandbox offline on each used record's recorded patches (records untouched)",
    )
    args = ap.parse_args(argv)

    records = load_records(Path(args.in_path))
    if not records:
        print(f"No records found in {args.in_path}", file=sys.stderr)
        return 1
    summary = summarise(
        records,
        expected_repeats=args.repeats,
        rescore_sandbox=evaluate_patch_in_sandbox if args.rescore else None,
    )
    out_md = Path(args.out_md)
    out_json = Path(args.out_json) if args.out_json else out_md.with_suffix(".json")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_markdown(summary), encoding="utf-8")
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {out_md} and {out_json} ({summary['ok_runs_used']} ok runs, {summary['error_records']} errors).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
