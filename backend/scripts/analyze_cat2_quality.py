"""Category 2 quality tables: deterministic scores of the 12 stored drafts, plus judge tables when judgements exist.

Usage (from backend/):
    .venv/bin/python scripts/analyze_cat2_quality.py
    .venv/bin/python scripts/analyze_cat2_quality.py --judgements experiments/cat2_quality/judgements.jsonl

Recomputes the deterministic measures from replays + answer key (offline), reads the judge JSONL if present,
and writes <project>/analysis/cat2_quality.md and .json. Factual tables only; no interpretation.
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

from app.archetypes.cat2_drafting.quality_scoring import (  # noqa: E402
    DIMENSIONS,
    FACT_CATEGORIES,
    JUDGE_EFFORT,
    JUDGE_MAX_TOKENS,
    JUDGE_MODEL,
    JUDGEMENTS_PATH,
    KEYS_PATH,
    NUMBER_VERDICTS,
    PAIR_DIMENSIONS,
    PRESET_IDS,
    REPLAYS_PATH,
    RUNG_IDS,
    load_judgements,
    load_quality_keys,
    load_replays,
    rung_pairs,
    run_deterministic,
    summarise,
)

DEFAULT_OUT_MD = PROJECT_DIR / "analysis" / "cat2_quality.md"

METHOD_NOTES: tuple[str, ...] = (
    "The stored drafts' `stop_reason` was written as a constant (`end_turn`) by `scripts/capture_cat2_replays.py`, "
    "so normal completion is inferred from the text ending cleanly and output tokens being below the cap, not observed.",
    "There is one draft per rung per source bundle, so the judge repeats measure judge noise, not drafting variance.",
)


def _p(x: dict[str, Any]) -> str:
    if not x["total"]:
        return "n/a"
    lo, hi = x["wilson95"]
    return f"{x['hits']}/{x['total']} ({x['rate'] * 100:.1f}%) [{lo * 100:.1f}–{hi * 100:.1f}]"


def _f(v: float | None, digits: int = 2) -> str:
    return "n/a" if v is None else f"{v:.{digits}f}"


def _dist(d: dict[str, Any]) -> str:
    if not d.get("n"):
        return "n/a"
    return f"{d['mean']:.2f} ({d['min']:g}–{d['max']:g})"


def _cell(s: str | None) -> str:
    return " ".join(str(s or "").split()).replace("|", "\\|")


def _coverage_rows(add, groups: list[tuple[str, dict[str, Any]]]) -> None:
    add("| Group | Drafts | Overall | Core | Detail | Facts / 1k output tok | Output tokens | $ / 1k docs |")
    add("|---|---|---|---|---|---|---|---|")
    for label, g in groups:
        c = g["coverage"]
        add(
            f"| {label} | {g['drafts']} | {_p(c['overall'])} | {_p(c['core'])} | {_p(c['detail'])} | "
            f"{_f(c['facts_per_1k_output_tokens'])} | {g['output_tokens']['total']:,} | ${_f(g['cost_per_1k_docs_usd'])} |"
        )
    add("")


def _numbers_rows(add, groups: list[tuple[str, dict[str, Any]]]) -> None:
    add("| Group | Tokens extracted | Ignored | Numeric tokens | In source | Not in source | Share not in source | Ignored by rule |")
    add("|---|---|---|---|---|---|---|---|")
    for label, g in groups:
        n = g["numbers"]
        rules = ", ".join(f"{k} {v}" for k, v in sorted(n["ignored_by_reason"].items()))
        share = "n/a" if n["not_in_source_share"] is None else f"{n['not_in_source_share'] * 100:.1f}%"
        add(
            f"| {label} | {n['tokens_extracted']} | {n['ignored']} | {n['numeric_tokens']} | {n['in_source']} | "
            f"{n['not_in_source']} | {share} | {rules} |"
        )
    add("")


def render_markdown(s: dict[str, Any], *, judgements_path: Path) -> str:
    det = s["deterministic"]
    j = s["judge"]
    lines: list[str] = []
    add = lines.append
    add("# Category 2 quality scoring — results")
    add("")
    add(
        f"Generated: {s['generated_at']} · answer key `{det['keys_version']}` (`{KEYS_PATH.name}`) · drafts: "
        f"`{REPLAYS_PATH.name}` ({len(det['drafts'])} = {len(PRESET_IDS)} bundles × {len(RUNG_IDS)} rungs, n=1 per cell, no rerun)."
    )
    add("")
    add(
        "Templated drafts are scored on their `structured_draft` rendered to Markdown by "
        "`quality_scoring.render_structured_draft`; unbounded drafts on `raw_markdown` as is. Coverage values: "
        "hits/total (rate) [Wilson 95%, %]. Cost per 1k documents = recorded input/output tokens priced by "
        "`compute_run_finops`."
    )
    add("")
    add(
        f"Judge: {'`' + judgements_path.name + '` — ' + str(j['data_quality']['ok_calls']) + ' ok calls' if j else 'no judgements file (deterministic tables only)'}."
    )
    add("")

    add("## Answer key")
    add("")
    add("| Bundle | Facts | Core | Detail | " + " | ".join(FACT_CATEGORIES) + " |")
    add("|---|---|---|---|" + "---|" * len(FACT_CATEGORIES))
    for pid in PRESET_IDS:
        c = det["key_counts"].get(pid, {})
        add(
            f"| {pid} | {c.get('total', 0)} | {c.get('tier:core', 0)} | {c.get('tier:detail', 0)} | "
            + " | ".join(str(c.get(f"category:{k}", 0)) for k in FACT_CATEGORIES) + " |"
        )
    add("")

    add("## Fact coverage — per rung (pooled over the 4 bundles)")
    add("")
    _coverage_rows(add, [(f"`{r}`", det["rungs"][r]) for r in RUNG_IDS])
    add("By category (pooled):")
    add("")
    add("| Rung | " + " | ".join(FACT_CATEGORIES) + " |")
    add("|---|" + "---|" * len(FACT_CATEGORIES))
    for r in RUNG_IDS:
        bc = det["rungs"][r]["coverage"]["by_category"]
        add(f"| `{r}` | " + " | ".join(f"{bc[k]['hits']}/{bc[k]['total']}" for k in FACT_CATEGORIES) + " |")
    add("")
    add("### Per rung × bundle")
    add("")
    _coverage_rows(add, [(f"`{r}` {p}", det["rungs"][r]["by_preset"][p]) for r in RUNG_IDS for p in PRESET_IDS if p in det["rungs"][r]["by_preset"]])

    add("## Unsupported numbers (measure C) — per rung")
    add("")
    _numbers_rows(add, [(f"`{r}`", det["rungs"][r]) for r in RUNG_IDS])
    add("### Per rung × bundle")
    add("")
    _numbers_rows(add, [(f"`{r}` {p}", det["rungs"][r]["by_preset"][p]) for r in RUNG_IDS for p in PRESET_IDS if p in det["rungs"][r]["by_preset"]])
    if j:
        nr = j["numbers"]
        add("### Judge review of not-in-source numbers (majority of the rubric repeats)")
        add("")
        add("| Group | Reviewed | " + " | ".join(NUMBER_VERDICTS) + " | no_majority | Not unanimous |")
        add("|---|---|" + "---|" * (len(NUMBER_VERDICTS) + 2))
        for r in RUNG_IDS:
            x = nr["rungs"][r]
            add(f"| `{r}` | {x['reviewed']} | " + " | ".join(str(x["majority_counts"][v]) for v in (*NUMBER_VERDICTS, "no_majority")) + f" | {x['disagreements']} |")
        for key, x in nr["per_draft"].items():
            add(f"| {key} | {x['reviewed']} | " + " | ".join(str(x["majority_counts"][v]) for v in (*NUMBER_VERDICTS, "no_majority")) + f" | {x['disagreements']} |")
        add("")
        dis = [(k, i) for k, x in nr["per_draft"].items() for i in x["items"] if not i["unanimous"]]
        add(f"Numbers on which the repeats disagree ({len(dis)}):")
        add("")
        if dis:
            add("| Draft | Id | Number | Verdicts (by repeat) | Majority |")
            add("|---|---|---|---|---|")
            for k, i in dis:
                add(f"| {k} | {i['id']} | `{_cell(i['text'])}` | {', '.join(f'r{r}:{v}' for r, v in zip(i['repeats'], i['verdicts']))} | {i['majority']} |")
        add("")
    add("Per-draft list of not-in-source numbers (id · number · context):")
    add("")
    for c in det["drafts"]:
        add(f"- **{c['preset_id']} · `{c['rung_id']}`** — {len(c['not_in_source'])}")
        for n in c["not_in_source"]:
            add(f"  - {n['id']} · `{_cell(n['text'])}` ({n['kind']}) · {_cell(n['snippet'])}")
    add("")

    if j:
        rb = j["rubric"]
        add("## Rubric scores (judge)")
        add("")
        add("Mean (min–max) over repeats × bundles. Agreement = share of draft × dimension cells whose 3 repeat scores are all within 1 point.")
        add("")
        add("| Rung | " + " | ".join(DIMENSIONS) + " | Agreement (within 1) |")
        add("|---|" + "---|" * (len(DIMENSIONS) + 1))
        for r in RUNG_IDS:
            x = rb["rungs"][r]
            ag = x["agreement_within_1"]
            add(f"| `{r}` | " + " | ".join(_dist(x[d]) for d in DIMENSIONS) + f" | {ag['within_1']}/{ag['cells']} |")
        ag = rb["agreement_within_1_overall"]
        add("")
        add(f"Overall inter-repeat agreement: {ag['within_1']}/{ag['cells']} cells ({_f((ag['share'] or 0) * 100, 1)}%).")
        add("")
        add("### Per draft (scores by repeat)")
        add("")
        add("| Draft | " + " | ".join(DIMENSIONS) + " |")
        add("|---|" + "---|" * len(DIMENSIONS))
        for key, x in rb["per_draft"].items():
            add(f"| {key} | " + " | ".join(f"{x['dimensions'][d]['mean']:.2f} [{','.join(map(str, x['dimensions'][d]['scores']))}]" for d in DIMENSIONS) + " |")
        add("")

        er = j["errors"]
        add("## Factual errors (judge; de-duplicated across repeats by claim-quote similarity)")
        add("")
        add("| Rung | Drafts | Distinct errors | Material | Minor | Raw reports |")
        add("|---|---|---|---|---|---|")
        for r in RUNG_IDS:
            x = er["rungs"][r]
            add(f"| `{r}` | {x['drafts']} | {x['distinct_errors']} | {x['material']} | {x['minor']} | {x['raw_reports']} |")
        add("")
        add("| Draft | Repeats | Distinct | Material | Minor | Reported by 1 / 2 / 3 repeats |")
        add("|---|---|---|---|---|---|")
        for key, x in er["per_draft"].items():
            rep = [sum(1 for e in x["errors"] if e["repeats_reporting"] == n) for n in (1, 2, 3)]
            add(f"| {key} | {x['rubric_repeats']} | {x['distinct_errors']} | {x['material']} | {x['minor']} | {rep[0]} / {rep[1]} / {rep[2]} |")
        add("")
        for key, x in er["per_draft"].items():
            if not x["errors"]:
                continue
            add(f"**{key}**")
            add("")
            add("| Severity (material votes / reports) | Repeats | Claim (draft) | Problem | Source quote | Quote found in draft / source |")
            add("|---|---|---|---|---|---|")
            for e in x["errors"]:
                add(
                    f"| {e['severity']} ({e['material_votes']}/{e['reports']}) | {e['repeats_reporting']} | {_cell(e['claim_quote'])} | "
                    f"{_cell(e['problem'])} | {_cell(e['source_quote_or_absent'])} | {e['claim_quote_found_in_draft']} / {e['source_quote_found_in_source']} |"
                )
            add("")

        pw = j["pairwise"]
        add("## Pairwise preference (judge)")
        add("")
        add(f"{pw['calls']} ok calls. Each cell = wins of the row rung over the column rung, counting both presentation orders.")
        add("")
        for key in ("overall", *PAIR_DIMENSIONS):
            x = pw[key]
            add(f"### {key}")
            add("")
            add("| Row beats column | " + " | ".join(f"`{c}`" for c in RUNG_IDS) + " |")
            add("|---|" + "---|" * len(RUNG_IDS))
            for r in RUNG_IDS:
                add(f"| `{r}` | " + " | ".join("–" if c == r else str(x["wins"][r][c]) for c in RUNG_IDS) + " |")
            add("")
            add("Ties: " + ", ".join(f"{k.replace('|', ' vs ')} {v}" for k, v in x["ties"].items()))
            pc = x["position_consistency"]
            add("")
            add(
                f"Position consistency: {pc['consistent']}/{pc['pairs_with_both_orders']} bundle × pair cells pick the same "
                f"rung (or tie) in both orders ({_f((pc['share'] or 0) * 100, 1)}%). Decisive calls choosing position A: "
                f"{_f((x['share_decisive_choosing_position_a'] or 0) * 100, 1)}% of {x['decisive_calls']}."
            )
            for inc in pc["inconsistent"]:
                add(f"- inconsistent: {inc['preset_id']} {inc['pair'][0]} vs {inc['pair'][1]} — fwd → {inc.get('fwd')}, rev → {inc.get('rev')}")
            add("")
            add("| Bundle | " + " | ".join(f"{a} vs {b}" for a, b in rung_pairs()) + " |")
            add("|---|" + "---|" * len(rung_pairs()))
            for pid in PRESET_IDS:
                cells = x["by_preset"][pid]
                add(f"| {pid} | " + " | ".join(
                    f"fwd {cells.get(f'{a}|{b}', {}).get('fwd', '–')} · rev {cells.get(f'{a}|{b}', {}).get('rev', '–')}" for a, b in rung_pairs()
                ) + " |")
            add("")

    add("## For lead review")
    add("")
    if not j:
        add("Requires judge results (none yet). Every not-in-source number is listed above.")
        add("")
    else:
        mats = [(k, e) for k, x in j["errors"]["per_draft"].items() for e in x["errors"] if e["severity"] == "material"]
        add(f"### Material factual errors ({len(mats)})")
        add("")
        for k, e in mats:
            add(f"- **{k}** (reported by {e['repeats_reporting']} repeat(s), material {e['material_votes']}/{e['reports']})")
            add(f"  - Draft: \"{_cell(e['claim_quote'])}\" (found in draft: {e['claim_quote_found_in_draft']})")
            add(f"  - Problem: {_cell(e['problem'])}")
            add(f"  - Source: \"{_cell(e['source_quote_or_absent'])}\" (found in source: {e['source_quote_found_in_source']})")
        add("")
        flagged = [
            (k, i) for k, x in j["numbers"]["per_draft"].items() for i in x["items"]
            if i["majority"] in ("derived_incorrect", "not_in_source_unverifiable") or any(v in ("derived_incorrect", "not_in_source_unverifiable") for v in i["verdicts"])
        ]
        add(f"### Numbers judged derived_incorrect / not_in_source_unverifiable by any repeat ({len(flagged)})")
        add("")
        for k, i in flagged:
            add(f"- **{k}** {i['id']} `{_cell(i['text'])}` — majority {i['majority']}; verdicts {i['verdicts']}")
            add(f"  - Context: {_cell(i['snippet'])}")
            for r, reason in zip(i["repeats"], i["reasons"]):
                add(f"  - r{r}: {_cell(reason)}")
        add("")

    add("## Per-fact hits across rungs")
    add("")
    add("| Fact | Bundle | Tier | Category | " + " | ".join(f"`{r}`" for r in RUNG_IDS) + " | Flag |")
    add("|---|---|---|---|" + "---|" * (len(RUNG_IDS) + 1))
    for f in det["per_fact"]:
        add(
            f"| `{f['fact_id']}` | {f['preset_id']} | {f['tier']} | {f['category']} | "
            + " | ".join("–" if f["hits"][r] is None else ("✓" if f["hits"][r] else "✗") for r in RUNG_IDS)
            + f" | {'no draft' if f['covered_by_no_draft'] else ''} |"
        )
    add("")
    add(f"Facts covered by no draft: {len(det['facts_covered_by_no_draft'])} {det['facts_covered_by_no_draft']}")
    add("")

    add("## Data quality")
    add("")
    for c in det["drafts"]:
        if c["recorded_stop_reason"] != "end_turn":
            add(f"- {c['preset_id']} `{c['rung_id']}` recorded stop_reason {c['recorded_stop_reason']}")
    for note in METHOD_NOTES:
        add(f"- {note}")
    if j:
        dq = j["data_quality"]
        add(
            f"- Judge: {dq['records']} records, {dq['ok_calls']} ok calls, {dq['error_records']} error records "
            f"({dq['errors_by_type']}); returned models {dq['model_ids_returned']}; ok stop reasons {dq['stop_reasons_ok']}; "
            f"tokens in {dq['tokens']['input']:,} / out {dq['tokens']['output']:,} (thinking {dq['tokens']['thinking']:,}); "
            f"billed ${dq['billed_usd_all_records']:.4f} at the assumed rate (error records ${dq['billed_usd_error_records']:.4f}); "
            f"latency {_dist(dq['latency_ms'])} ms."
        )
        for e in dq["errors"]:
            add(f"  - `{e['call_id']}` {e['error_type']} (stop {e['stop_reason']}, out {e['output_tokens']}): {_cell(e['error_message'])}")
        add(f"- Judge settings: `{JUDGE_MODEL}`, thinking adaptive, effort {JUDGE_EFFORT}, max_tokens {JUDGE_MAX_TOKENS}; drafts labelled only Draft / Draft A / Draft B.")
    add("")

    add("## Scoring rules")
    add("")
    add("Fact coverage — both texts normalised identically (Category 3 normaliser):")
    add("")
    for rule in det["normalisation_rules"]:
        add(rule if rule[:1].isdigit() else f"\n{rule}")
    add("")
    add("Unsupported numbers — ignore rules (not counted as numeric tokens):")
    add("")
    for r in det["number_rules"]["ignore"]:
        add(f"- `{r['rule']}`: {r['description']}")
    add("")
    for r in det["number_rules"]["classification"]:
        add(f"- {r}")
    add("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replays", default=str(REPLAYS_PATH))
    ap.add_argument("--keys", default=str(KEYS_PATH))
    ap.add_argument("--judgements", default=str(JUDGEMENTS_PATH))
    ap.add_argument("--out-md", default=str(DEFAULT_OUT_MD))
    ap.add_argument("--out-json", default=None, help="default: --out-md with a .json suffix")
    args = ap.parse_args(argv)

    det = run_deterministic(load_replays(args.replays), load_quality_keys(args.keys))
    jpath = Path(args.judgements)
    judgements = load_judgements(jpath)
    summary = summarise(det, judgements or None)
    out_md = Path(args.out_md)
    out_json = Path(args.out_json) if args.out_json else out_md.with_suffix(".json")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_markdown(summary, judgements_path=jpath), encoding="utf-8")
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out_md} and {out_json} ({len(det['drafts'])} drafts, {len(judgements)} judge records).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
