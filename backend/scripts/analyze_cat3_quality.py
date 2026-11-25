"""Score Category 3 quality-rerun records and the original golden capture against the answer key.

Usage (from backend/):
    .venv/bin/python scripts/analyze_cat3_quality.py
    .venv/bin/python scripts/analyze_cat3_quality.py --in path/to/runs.jsonl --repeats 3

Works with zero rerun records (the "original capture" tables come from replays/cat3_golden_replays.json).
Writes <project>/analysis/cat3_quality_rerun.md and .json. Factual tables only.
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

from app.archetypes.cat3_assistants.quality_rerun import (  # noqa: E402
    CALL_TIMEOUT_S,
    CONTEXT_TURNS,
    KEYS_PATH,
    PROBE_CONCURRENCY,
    PROBE_MAX_TOKENS,
    SUMMARIZER_MAX_TOKENS,
    TURN_MAX_TOKENS,
    load_quality_keys,
    summarise,
)

DEFAULT_IN = BACKEND_DIR / "experiments" / "cat3_quality" / "runs.jsonl"
DEFAULT_GOLDEN = BACKEND_DIR / "replays" / "cat3_golden_replays.json"
DEFAULT_OUT_MD = PROJECT_DIR / "analysis" / "cat3_quality_rerun.md"


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


def _p(x: dict[str, Any]) -> str:
    """hits/total (rate) [Wilson 95%]."""
    if not x["total"]:
        return "n/a"
    lo, hi = x["wilson95"]
    return f"{x['hits']}/{x['total']} ({x['rate'] * 100:.1f}%) [{lo * 100:.1f}–{hi * 100:.1f}]"


def _usd(d: dict[str, Any], digits: int = 4) -> str:
    if d["mean"] is None:
        return "n/a"
    return f"${d['mean']:.{digits}f} (${d['min']:.{digits}f}–${d['max']:.{digits}f})"


def _tok(d: dict[str, Any]) -> str:
    if d["mean"] is None:
        return "n/a"
    return f"{d['mean']:,.0f} ({d['min']:,.0f}–{d['max']:,.0f})"


def _quality_tables(lines: list[str], groups: list[tuple[str, dict[str, Any]]], *, probes: bool) -> None:
    add = lines.append
    add("Turn-fact recall (turns 1–9; each reply scored against its own turn's facts):")
    add("")
    add("| Group | Sessions | Turns 1–9 | Turns 1–4 | Turns 5–9 |")
    add("|---|---|---|---|---|")
    for label, q in groups:
        t = q["turn_recall"]
        add(f"| {label} | {q['sessions']} | {_p(t['turns_1_9'])} | {_p(t['turns_1_4'])} | {_p(t['turns_5_9'])} |")
    add("")
    add("Ledger recall (turn-10 reply scored against ledger facts):")
    add("")
    add("| Group | Overall | Origin 1–3 | Origin 4–6 | Origin 7–9 | Source handbook | Source session |")
    add("|---|---|---|---|---|---|---|")
    for label, q in groups:
        led = q["ledger_recall"]
        add(
            f"| {label} | {_p(led['overall'])} | {_p(led['by_origin']['origin_1_3'])} | "
            f"{_p(led['by_origin']['origin_4_6'])} | {_p(led['by_origin']['origin_7_9'])} | "
            f"{_p(led['by_source']['handbook'])} | {_p(led['by_source']['session'])} |"
        )
    add("")
    if probes:
        add("Probe accuracy (independent turn-11 questions after turn 10):")
        add("")
        add("| Group | Overall | Origin 1–6 | Origin 7–9 |")
        add("|---|---|---|---|")
        for label, q in groups:
            pr = q["probe_accuracy"]
            add(
                f"| {label} | {_p(pr['overall'])} | {_p(pr['by_origin']['origin_1_6'])} | "
                f"{_p(pr['by_origin']['origin_7_9'])} |"
            )
        add("")


def render_markdown(s: dict[str, Any], *, in_path: Path, golden_path: Path) -> str:
    lines: list[str] = []
    add = lines.append
    rr = s["rerun"]
    rungs = s["rung_ids"]
    presets = s["preset_ids"]

    add("# Category 3 quality rerun — results")
    add("")
    add(f"Generated: {s['generated_at']} · answer key `{s['keys_version']}` (`{KEYS_PATH.name}`)")
    add("")
    add(
        f"Rerun records: {rr['record_count']} read from `{in_path}` · ok runs used (latest ok per key): "
        f"{rr['ok_runs_used']} · superseded ok: {rr['superseded_ok_records']} · error records: {rr['error_records']}. "
        f"Original capture: `{golden_path.name}` ({len(s['original_capture']['cells'])} rung × session cells, n=1 each)."
    )
    add("")
    add(
        f"Run settings: turns max_tokens {TURN_MAX_TOKENS}, summariser max_tokens {SUMMARIZER_MAX_TOKENS}, probes "
        f"max_tokens {PROBE_MAX_TOKENS} (≤{PROBE_CONCURRENCY} concurrent per run), per-call client timeout "
        f"{CALL_TIMEOUT_S:.0f}s, per-run nonce prepended to the system text on every rung. Values: hits/total "
        "(rate) [Wilson 95% interval, %]."
    )
    add("")

    add("## Answer key")
    add("")
    add("| Session | turn/handbook | turn/session | ledger/handbook | ledger/session | probe/session |")
    add("|---|---|---|---|---|---|")
    for pid, c in sorted(s["key_counts"].items()):
        add(
            f"| {pid} | {c.get('turn|handbook', 0)} | {c.get('turn|session', 0)} | {c.get('ledger|handbook', 0)} | "
            f"{c.get('ledger|session', 0)} | {c.get('probe|session', 0)} |"
        )
    add("")

    add("## Fresh reruns — quality per rung (pooled over sessions and repeats)")
    add("")
    if rr["ok_runs_used"] == 0:
        add(f"No ok rerun records found in `{in_path}`.")
        add("")
    else:
        m = rr["matrix"]
        add(
            f"Matrix: {len(rungs)} rungs × {len(presets)} sessions × {rr['expected_repeats']} repeats = "
            f"{m['expected_runs']} runs ({'complete' if m['complete'] else 'INCOMPLETE'}, "
            f"{'balanced' if m['balanced'] else 'UNBALANCED'})."
        )
        add("")
        _quality_tables(lines, [(f"`{r}`", rr["rungs"][r]["quality"]) for r in rungs], probes=True)
        add("### Per rung × session")
        add("")
        _quality_tables(
            lines,
            [(f"`{r}` {p}", rr["rungs"][r]["by_preset"][p]["quality"]) for r in rungs for p in presets],
            probes=True,
        )

    add("## Original capture (golden replays, n=1 per cell) — quality")
    add("")
    oc = s["original_capture"]["rungs"]
    _quality_tables(lines, [(f"`{r}`", oc[r]["quality"]) for r in rungs], probes=False)
    add("### Per rung × session")
    add("")
    _quality_tables(
        lines,
        [(f"`{r}` {p}", oc[r]["by_preset"][p]["quality"]) for r in rungs for p in presets if p in oc[r]["by_preset"]],
        probes=False,
    )
    add("The original capture has no probes (they were not asked at capture time).")
    add("")

    if rr["ok_runs_used"]:
        add("## Fresh reruns — cost, tokens and context")
        add("")
        add(
            "| Rung | Runs | Session billed $/session | Session warm $/session | Session billed $/1k | "
            "Session warm $/1k | Probe-phase billed $/run | Probe-phase warm $/run |"
        )
        add("|---|---|---|---|---|---|---|---|")
        for r in rungs:
            c = rr["rungs"][r]["cost"]
            b1k, w1k = c["session_billed_per_1k_sessions_usd"], c["session_warm_per_1k_sessions_usd"]
            add(
                f"| `{r}` | {c['runs']} | {_usd(c['session_billed_usd'])} | {_usd(c['session_warm_usd'])} | "
                f"{'n/a' if b1k is None else f'${b1k:,.2f}'} | {'n/a' if w1k is None else f'${w1k:,.2f}'} | "
                f"{_usd(c['probe_billed_usd'])} | {_usd(c['probe_warm_usd'])} |"
            )
        add("")
        add(
            "| Rung | Turn prompt tok/session | Turn output tok/session | Compaction prompt tok | Compaction output tok | "
            "Probe-phase prompt tok | Probe-phase output tok | Thinking tok (all calls) | Compactions (session) | "
            "Probe-phase compactions |"
        )
        add("|---|---|---|---|---|---|---|---|---|---|")
        for r in rungs:
            c = rr["rungs"][r]["cost"]
            t = c["tokens_per_session"]
            add(
                f"| `{r}` | {_tok(t['turn_prompt'])} | {_tok(t['turn_output'])} | {_tok(t['compaction_prompt'])} | "
                f"{_tok(t['compaction_output'])} | {_tok(t['probe_phase_prompt'])} | {_tok(t['probe_phase_output'])} | "
                f"{_tok(t['thinking'])} | {_tok(c['session_compactions'])} | {_tok(c['probe_phase_compactions'])} |"
            )
        add("")
        add("Context size (prompt tokens = uncached input + cache write + cache read) at selected turns:")
        add("")
        add("| Rung | " + " | ".join(f"Turn {n}" for n in CONTEXT_TURNS) + " |")
        add("|---|" + "---|" * len(CONTEXT_TURNS))
        for r in rungs:
            ctx = rr["rungs"][r]["cost"]["context_prompt_tokens_at_turn"]
            add(f"| `{r}` | " + " | ".join(_tok(ctx[str(n)]) for n in CONTEXT_TURNS) + " |")
        add("")
        add("Per rung × session (session billed / warm $ per session, mean):")
        add("")
        add("| Rung | Session | Runs | Errors | Session billed | Session warm | Probe-phase billed |")
        add("|---|---|---|---|---|---|---|")
        for r in rungs:
            for p in presets:
                bp = rr["rungs"][r]["by_preset"][p]
                c = bp["cost"]
                add(
                    f"| `{r}` | {p} | {c['runs']} | {bp['error_records']} | {_usd(c['session_billed_usd'])} | "
                    f"{_usd(c['session_warm_usd'])} | {_usd(c['probe_billed_usd'])} |"
                )
        add("")
        add(
            "Billed = recorded tokens priced at the returned model's rates (`app/core/pricing.py`). Warm = "
            "`runner.compute_warm_turn_cost` per turn/probe call (cache writes priced as cache reads); "
            "summariser calls count at billed cost in both views, as in the runner. Session = turns 1–10 plus the "
            "compactions before turns; probe phase = the probe-phase compaction plus all probe calls."
        )
        add("")

    add("## Per-fact hit rates")
    add("")
    add(
        "Rerun columns: hits/n over ok runs. Original columns: ✓/✗ per golden cell (– = not scored). "
        "`never` = observed but hit by no rung in any run or capture."
    )
    add("")
    add("| Fact | Session | Kind | Turn | Source | " + " | ".join(f"rerun `{r}`" for r in rungs) + " | "
        + " | ".join(f"orig `{r}`" for r in rungs) + " | Flag |")
    add("|---|---|---|---|---|" + "---|" * (2 * len(rungs) + 1))
    for f in s["per_fact"]:
        rcells = [f"{f['rerun'][r]['hits']}/{f['rerun'][r]['n']}" if f["rerun"][r]["n"] else "–" for r in rungs]
        ocells = ["–" if f["original"][r] is None else ("✓" if f["original"][r] else "✗") for r in rungs]
        add(
            f"| `{f['fact_id']}` | {f['preset_id']} | {f['kind']} | {f['turn']} | {f['source']} | "
            + " | ".join(rcells) + " | " + " | ".join(ocells) + f" | {'never' if f['never_hit'] else ''} |"
        )
    add("")
    by_id = {f["fact_id"]: f for f in s["per_fact"]}
    add(f"### Facts hit by no rung in any run ({len(s['never_hit_facts'])})")
    add("")
    for fid in s["never_hit_facts"]:
        f = by_id[fid]
        add(f"- `{fid}` ({f['kind']}, turn {f['turn']}, {f['source']}): {f['description']} — any_of {f['any_of']}")
    add("")
    add(f"### Largest spread between rungs (top {len(s['largest_spread_facts'])})")
    add("")
    add("| Fact | Kind | Turn | Source | Spread | Basis | Per-rung |")
    add("|---|---|---|---|---|---|---|")
    for fid in s["largest_spread_facts"]:
        f = by_id[fid]
        if f["spread_basis"] == "rerun":
            per = ", ".join(f"{r} {f['rerun'][r]['hits']}/{f['rerun'][r]['n']}" for r in rungs if f["rerun"][r]["n"])
        else:
            per = ", ".join(f"{r} {'✓' if f['original'][r] else '✗'}" for r in rungs if f["original"][r] is not None)
        add(f"| `{fid}` | {f['kind']} | {f['turn']} | {f['source']} | {f['spread'] * 100:.0f} pp | {f['spread_basis']} | {per} |")
    add("")

    add("## Data quality")
    add("")
    add(f"- Rerun error records: {rr['error_records']} (billed ${rr['error_spend_usd']:.4f}).")
    for e in rr["errors"]:
        add(
            f"  - `{e['rung_id']}` {e['preset_id']} r{e['repeat_index']} — {e['completed_turns']} turns, "
            f"{e['completed_probes']} probes, ${e['billed_usd']:.4f}: {str(e['error_message'])[:300]}"
        )
    if rr["ok_runs_used"] or rr["record_count"]:
        for k in rr["matrix"]["missing_keys"]:
            add(f"  - missing `{k[0]}` {k[1]} r{k[2]}")
    stops = rr["non_end_turn_calls"]
    add(f"- Rerun calls not ending in `end_turn`: {len(stops)}.")
    for x in stops:
        add(f"  - `{x['rung_id']}` {x['preset_id']} r{x['repeat_index']} {x['call']}: {x['stop_reason']} ({x['output_tokens']} out)")
    mm = rr["model_mismatches"]
    add(f"- Rerun calls whose returned model is not `claude-sonnet-5-5`: {len(mm)}.")
    for x in mm:
        add(f"  - `{x['rung_id']}` {x['preset_id']} r{x['repeat_index']} {x['call']}: `{x['model_id']}`")
    gq = s["original_capture"]["data_quality"]
    add(
        f"- Original capture: turns not ending in `end_turn`: {len(gq['non_end_turn_turns'])}; "
        f"model mismatches: {len(gq['model_mismatches'])}."
    )
    for x in [*gq["non_end_turn_turns"], *gq["model_mismatches"]]:
        add(f"  - {x}")
    add("")

    add(f"## Misses for review — probe answers that missed ({len(s['misses_for_review'])})")
    add("")
    if not s["misses_for_review"]:
        add("None (or no probe answers recorded yet).")
        add("")
    for x in s["misses_for_review"]:
        add(
            f"### `{x['rung_id']}` · {x['preset_id']} · r{x['repeat_index']} · `{x['probe_id']}` (origin turn {x['origin_turn']})"
        )
        add("")
        add(f"Expected any of: {x['expected_any_of']}")
        add("")
        add("```text")
        add(x["answer_excerpt"].replace("```", "'''"))
        add("```")
        add("")

    add("## Scoring rules")
    add("")
    add("Both the reply and every `any_of` alternative are normalised the same way before matching:")
    add("")
    for rule in s["normalisation_rules"]:
        add(rule if rule[:1].isdigit() else f"\n{rule}")
    add("")
    add(
        "Turn facts are scored against the reply of their own turn; ledger facts against the turn-10 reply; "
        "probes against each probe's answer. Items whose reply was not recorded are omitted, not counted as misses. "
        "Rerun statistics use the latest ok record per (rung, session, repeat)."
    )
    add("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="in_path", default=str(DEFAULT_IN))
    ap.add_argument("--golden", default=str(DEFAULT_GOLDEN))
    ap.add_argument("--keys", default=str(KEYS_PATH))
    ap.add_argument("--out-md", default=str(DEFAULT_OUT_MD))
    ap.add_argument("--out-json", default=None, help="default: --out-md with a .json suffix")
    ap.add_argument("--repeats", type=int, default=None, help="expected repeats (default: inferred from records)")
    args = ap.parse_args(argv)

    in_path, golden_path = Path(args.in_path), Path(args.golden)
    records = load_records(in_path)
    golden = json.loads(golden_path.read_text(encoding="utf-8")) if golden_path.is_file() else {"presets": {}}
    keys = load_quality_keys(args.keys)
    summary = summarise(records, keys=keys, golden=golden, expected_repeats=args.repeats)

    out_md = Path(args.out_md)
    out_json = Path(args.out_json) if args.out_json else out_md.with_suffix(".json")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_markdown(summary, in_path=in_path, golden_path=golden_path), encoding="utf-8")
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"Wrote {out_md} and {out_json} ({summary['rerun']['ok_runs_used']} ok rerun runs, "
        f"{summary['rerun']['error_records']} errors, {len(summary['original_capture']['cells'])} original cells)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
