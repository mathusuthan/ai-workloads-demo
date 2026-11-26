"""Score the Category 4 quality-rerun sessions (without vs with the deck's lever); write the analysis report.

Without = full corpus, no cache, no citations (`naive_full_corpus`); with = hybrid retrieval paired with context
caching: Haiku picks 5 clauses from the cached corpus and Sonnet answers with citations (`cached_rerank_hybrid`).

Usage (from backend/):
    .venv/bin/python scripts/analyze_cat4_quality.py
    .venv/bin/python scripts/analyze_cat4_quality.py --runs path/runs.jsonl --judgements path/judgements.jsonl

Works with zero rerun records and without judgements. Writes <project>/analysis/cat4_quality_rerun.md and .json.
Factual tables only.
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

from app.archetypes.cat4_rag.quality_rerun import (  # noqa: E402
    JUDGE_MODEL,
    JUDGEMENTS_PATH,
    RERANK_MAX_TOKENS,
    RERANK_TIMEOUT_S,
    RUNS_PATH,
    SYNTH_MAX_TOKENS,
    SYNTH_TIMEOUT_S,
    load_jsonl,
    load_quality_keys,
    scope_line,
    session_questions,
    summarise,
)

DEFAULT_OUT_MD = PROJECT_DIR / "analysis" / "cat4_quality_rerun.md"

SHORT = {
    "naive_full_corpus": "Without",
    "cached_rerank_hybrid": "With",
}


def _p(x: dict[str, Any] | None) -> str:
    if not x or not x.get("total"):
        return "n/a"
    return f"{x['hits']}/{x['total']} ({x['rate'] * 100:.0f}%) [{x['ci_low'] * 100:.0f}–{x['ci_high'] * 100:.0f}]"


def _f(x: float | None, nd: int = 2) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def _usd(x: float | None) -> str:
    return "n/a" if x is None else f"${x:.4f}"


def _table(head: list[str], rows: list[list[str]]) -> list[str]:
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head), *("| " + " | ".join(r) + " |" for r in rows), ""]


def _quality_rows(groups: list[tuple[str, dict[str, Any]]]) -> list[list[str]]:
    rows = []
    for label, g in groups:
        cit = g["citations_requested"]
        rows.append([label, str(g["answers"]), _p(g["fact_recall"]), _p(g["fact_recall_supplier_specific"]),
                     _p(g["fact_recall_non_specific"]),
                     _f(g["citations_per_answer_mean"], 1) if cit else "not requested",
                     _p(g["zero_citation_answers"]) if cit else "—",
                     _p(g["expected_chunk_recall"]) if cit else "—", _p(g["citations_at_expected"]) if cit else "—",
                     _p(g["cited_support"]) if cit else "—"])
    return rows


QUALITY_HEAD = ["group", "answers", "key-fact recall", "supplier-specific", "statutory/mechanism/structure",
                "citations/answer", "zero-citation answers", "expected-chunk recall (cited)", "citations at expected chunks",
                "cited support of hit facts"]


def _contam_rows(groups: list[tuple[str, dict[str, Any]]]) -> list[list[str]]:
    rows = []
    for label, g in groups:
        r = g.get("retrieval") or {}
        cit = g["citations_requested"]
        rows.append([label, _p(g["contaminated_answers"]), _p(g["value_contaminated_answers"]),
                     _p(g.get("value_contaminated_unattributed_answers")), _p(g["citation_contaminated_answers"]),
                     _p(g.get("answers_whose_synthesis_saw_distractor_text")),
                     _p(g["citations_at_deccan"]) if cit else "—", _p(g["citations_at_distractor"]) if cit else "—",
                     _p(r["recall_after_rerank"]) if r.get("recall_after_rerank") else "—",
                     _p(r.get("distractors_selected")) if r else "—",
                     f"{r.get('backfilled', 0)} / {r.get('invalid_picks', 0)}" if r else "—"])
    return rows


CONTAM_HEAD = ["group", "contaminated answers", "…distractor value stated", "…value stated without naming the other supplier",
               "…distractor chunk cited", "synthesis saw distractor text (exposure)", "citations at Deccan",
               "citations at distractors", "expected clauses among Haiku's picks",
               "distractor chunks selected", "backfilled / invalid picks"]


def _cost_rows(groups: list[tuple[str, dict[str, Any]]]) -> list[list[str]]:
    rows = []
    for label, g in groups:
        c = g["cost_per_question"]
        row = [label]
        for view in ("billed", "cold", "warm"):
            row += [_usd(c[view]["sonnet"]), _usd(c[view]["haiku"]), _usd(c[view]["total"])]
        row.append(_usd(g["cache_write_premium_usd"]))
        rows.append(row)
    return rows


COST_HEAD = ["group", "billed Sonnet", "billed Haiku", "billed total", "cold Sonnet", "cold Haiku", "cold total",
             "warm Sonnet", "warm Haiku", "warm total", "cache-write premium (one-off)"]


def _token_rows(groups: list[tuple[str, dict[str, Any]]]) -> list[list[str]]:
    rows = []
    for label, g in groups:
        for role, t in sorted(g["tokens"].items()):
            rows.append([label, role, _f(t["prompt"]["mean"], 0), f"{t['prompt']['min']}–{t['prompt']['max']}",
                         _f(t["output"]["mean"], 0), f"{t['output']['min']}–{t['output']['max']}",
                         _f(t["cache_write"]["mean"], 0), _f(t["cache_read"]["mean"], 0), _f(t["thinking"]["mean"], 0)])
    return rows


TOKEN_HEAD = ["group", "call", "prompt tok mean", "prompt range", "output mean", "output range", "cache write mean",
              "cache read mean", "thinking mean"]


def _judge_rows(groups: list[tuple[str, dict[str, Any]]]) -> list[list[str]]:
    rows = []
    for label, g in groups:
        j = g.get("judge")
        if not j:
            rows.append([label, "0", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a"])
            continue
        rows.append([label, str(j["judgements"]), _f(j["correctness_mean"]), _f(j["completeness_mean"]),
                     str(j["material_errors"]), str(j["minor_errors"]), _p(j["answers_with_material_error"]),
                     ", ".join(f"{k} {v}" for k, v in sorted(j["answers_the_question"].items()))])
    return rows


JUDGE_HEAD = ["group", "judged", "correctness mean (1–5)", "completeness mean (1–5)", "material errors", "minor errors",
              "answers with ≥1 material error", "answers the question"]


def _glabel(g: dict[str, Any]) -> str:
    return f"{SHORT[g['rung_id']]} · {CORPUS_LABEL.get(int(g['scale']), g['scale'])}"


CORPUS_LABEL = {1: "corpus 1× (7 docs)", 3: "corpus 3× (21 docs)"}


def _absence_rows(groups: list[tuple[str, dict[str, Any]]]) -> list[list[str]]:
    rows = []
    for label, g in groups:
        a = g.get("absence") or {}
        j = g.get("judge") or {}
        by = a.get("judged_absence_errors_by_form")
        rows.append([label, str(g["answers"]), _p(a.get("answers_with_corpus_form_claim")), _p(a.get("answers_with_scoped_form_claim")),
                     f"{a.get('corpus_form_claims', 0)} / {a.get('scoped_form_claims', 0)}",
                     str(a.get("answers_saying_none_stated_in_text_provided", 0)),
                     _p(a.get("judged_answers_with_unsupported_absence_claim")),
                     "n/a" if by is None else f"{by.get('corpus', 0)} / {by.get('scoped', 0)}",
                     _p(j.get("answers_with_material_error")), _f(j.get("correctness_mean")), _p(g["fact_recall"])])
    return rows


ABSENCE_HEAD = ["group", "answers", "answers saying the documents lack something (detector)",
                "answers saying it is not in the text provided (detector)", "claims: documents-lack / not-in-text-provided",
                "answers writing \"None stated in the text provided\"",
                "judged answers with an unsupported absence claim (judge material error)",
                "those judge errors: documents-lack / not-in-text-provided", "answers with ≥1 material error",
                "correctness mean", "key-fact recall"]


def render(summary: dict[str, Any], args: argparse.Namespace, n_judgements: int) -> str:
    rr = summary["rerun"]
    L: list[str] = ["# Category 4 — without vs with hybrid retrieval paired with context caching", ""]
    L += ["Without: the whole corpus as uncached plain text, no citations; Sonnet 5.5 answers. With: Haiku 5.5 picks 5 "
          "clauses from the cached corpus and Sonnet 5.5 answers over them with native citations. Both corpus sizes: 1× "
          "(the app's 7-document deal room) and 3× (21 documents: two other suppliers' look-alike contracts added).", ""]
    L += [f"Generated {summary['generated_at']} · answer key `{summary['keys_version']}` · sessions {rr['ok_sessions_used']} · "
          f"judgements {n_judgements} (judge {JUDGE_MODEL}, spend ${summary['judge']['spend_usd']:.4f})", ""]
    L += ["Sources: `" + str(args.runs) + "`, `" + str(args.judgements) + "`, "
          "`app/data/cat4_quality_keys.json`. Every answer is scored; zero-citation, truncated and contaminated answers are "
          "reported, never dropped. Rates show hits/total (rate) [Wilson 95%]. Costs come from recorded tokens via "
          "`compute_run_finops` (billed = as recorded; cold = the cached call writes its whole prefix on question 1 of the "
          "session and reads after; warm = every cached-prefix token read).", ""]
    L += [f"Question scope line: every question is asked as `{scope_line()}` followed by a blank line and the question "
          "— identically for both versions and both corpus sizes, in the synthesis message and Haiku's clause-pick query. "
          "The judge sees each answer's question as asked.", ""]
    L += ["Synthesis prompts: without the lever (whole corpus) the app prompt; with it (picked clauses only) the same "
          "prompt with two lines telling the model to say when something is not in the text provided "
          "(`app/archetypes/cat4_rag/answer_formats.py`).", ""]
    L += [f"Settings: synthesis max_tokens {SYNTH_MAX_TOKENS} (timeout {SYNTH_TIMEOUT_S:.0f} s), rerank max_tokens "
          f"{RERANK_MAX_TOKENS} (timeout {RERANK_TIMEOUT_S:.0f} s), max_retries 0. Session = 8 questions in order: "
          + ", ".join(f"{p}/{q['question_id']}" for p, q in session_questions()) + ".", ""]

    L += ["## Answer key and corpus", ""]
    kc = summary["key_counts"]
    L += _table(["question", "facts", "supplier-specific", "commercial", "statutory", "mechanism", "structure"],
                [[k, str(v["facts"]), str(v["supplier_specific"]), str(v.get("commercial", 0)), str(v.get("statutory", 0)),
                  str(v.get("mechanism", 0)), str(v.get("structure", 0))] for k, v in kc.items()])
    L += _table(["scale", "documents", "chunks", "chars", "est. tokens (chars/2.4)", "ratio to base"],
                [[s, str(c["documents"]), str(c["chunks"]), f"{c['chars']:,}", f"{c['estimated_tokens']:,}", str(c["ratio_to_base_chars"])]
                 for s, c in summary["corpus"].items()])

    L += ["## Without vs with (version × corpus size)", ""]
    groups = [(_glabel(g), g) for g in rr["groups"].values()]
    if not groups:
        L += ["No ok rerun sessions yet (`scripts/cat4_quality_rerun.py` has not been run, or every session errored).", ""]
    else:
        L += ["### Quality", ""] + _table(QUALITY_HEAD, _quality_rows(groups))
        L += ["### Contamination and clause picks", ""]
        L += ["Contaminated = the answer states a distractor supplier's value for a keyed fact, or cites a distractor chunk. "
              "'Without naming the other supplier' drops values whose 150-char neighbourhood names that supplier or one of "
              "its document ids (typically an explicit exclusion). Exposure = the synthesis prompt contained distractor "
              "text (the whole corpus at scale 3, or ≥ 1 distractor chunk selected); it is not counted as contamination.", ""]
        L += _table(CONTAM_HEAD, _contam_rows(groups))
        L += ["### Judge", ""] + _table(JUDGE_HEAD, _judge_rows(groups))
        L += ["### Absence claims", ""]
        L += ["Deterministic detector over each answer: a sentence saying the documents / deal room / contracts / text "
              "contain, specify or state no X (documents-lack form), or that X is not in the text provided / the excerpts "
              "(not-in-text-provided form). The judge column counts answers whose material errors include such a "
              "claim about a term the documents do contain.", ""]
        L += _table(ABSENCE_HEAD, _absence_rows(groups))
        L += ["### Cost per question (USD, mean over answers)", ""] + _table(COST_HEAD, _cost_rows(groups))
        L += ["### Tokens per call", ""] + _table(TOKEN_HEAD, _token_rows(groups))
        L += ["### Per question", ""]
        prow = []
        for v in rr["per_question"].values():
            prow.append([_glabel(v), v["question"], _p(v["fact_recall"]), _p(v["fact_recall_supplier_specific"]),
                         _f(v["citations_per_answer_mean"], 1) if v["citations_requested"] else "—",
                         _p(v["zero_citation_answers"]) if v["citations_requested"] else "—",
                         _p(v["contaminated_answers"]),
                         _f((v.get("judge") or {}).get("correctness_mean")), _f((v.get("judge") or {}).get("completeness_mean")),
                         _usd(v["cost_per_question"]["billed"]["total"])])
        L += _table(["group", "question", "key-fact recall", "supplier-specific", "citations/answer", "zero-citation",
                     "contaminated", "judge correctness", "judge completeness", "billed $/question"], prow)

    L += ["## Zero-citation and contaminated answers", ""]
    zero = []
    for v in rr["per_question"].values():
        z = v.get("zero_citation_answers")
        if z and z["hits"]:
            zero.append([_glabel(v), v["question"], f"{z['hits']}/{z['total']}"])
    L += _table(["group", "question", "zero-citation answers"], zero) if zero else ["No zero-citation answers with the lever.", ""]
    ca = summary["for_lead_review"]["contaminated_answers"]
    if ca:
        L += _table(["source", "group", "question", "distractor values", "distractor chunks cited"],
                    [[c["source"], f"{SHORT[c['rung_id']]} · {CORPUS_LABEL.get(int(c['scale']), c['scale'])} r{c['repeat_index']}", c["question"],
                      "; ".join(f"{v['value']} ({v['supplier']}, {v['fact_id']}"
                                + (", other supplier named nearby" if v.get("attributed_to_distractor") else "") + ")"
                                for v in c["distractor_values"]) or "—",
                      ", ".join(c["distractor_chunks_cited"]) or "—"] for c in ca])
    else:
        L += ["No contaminated answers.", ""]

    L += ["## For lead review", ""]
    L += ["Items a person should read before quoting any number from this file.", ""]
    me = summary["for_lead_review"]["material_errors"]
    if me:
        L += ["### Material errors reported by the judge", ""]
        L += _table(["source", "group", "question", "claim", "problem", "source quote"],
                    [[m["source"], f"{_glabel(m)} r{m['repeat_index']}", m["question"],
                      m["claim_quote"].replace("|", "\\|")[:200], m["problem"].replace("|", "\\|")[:200],
                      m["source_quote_or_absent"].replace("|", "\\|")[:200]] for m in me])
    else:
        L += ["- No judge material errors (no judgements yet, or none reported).", ""]
    if ca:
        L += ["### Contaminated-answer excerpts", ""]
        for c in ca:
            for v in c["distractor_values"]:
                tag = " — other supplier named within 150 chars" if v.get("attributed_to_distractor") else ""
                L.append(f"- {c['source']} {SHORT[c['rung_id']]} · {CORPUS_LABEL.get(int(c['scale']), c['scale'])} r{c['repeat_index']} {c['question']}: "
                         f"`{v['value']}` ({v['supplier']}{tag}) — …{(v.get('answer_excerpt') or '(not located in raw text)').replace(chr(10), ' ')}…")
        L.append("")
    L += ["- The answer key was written from the question texts and Deccan chunks only; one dry pass over recorded "
          "answers added format variants (see key `meta.format_variants_added`).",
          "- The chunk boundaries and headings Haiku picks from were written for these documents; the share of expected "
          "clauses among its picks may be lower for unseen questions.",
          "- Four questions (audit-01/q2, q3; audit-02/q3, q4) do not name the supplier; the scope line names it.",
          "- The contamination detector cannot flag a distractor value that also occurs in Deccan's own documents; such values are excluded.",
          ""]

    L += ["## Data quality", ""]
    dq = rr["data_quality"]
    counts = {name.replace("_", " "): (len(v) if isinstance(v, list) else v) for name, v in dq.items()}
    L += ["Counts over the sessions and judgements above: " + "; ".join(f"{k} {'n/a' if v is None else v}" for k, v in counts.items()) + ".", ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", default=str(RUNS_PATH))
    ap.add_argument("--judgements", default=str(JUDGEMENTS_PATH))
    ap.add_argument("--out-md", default=str(DEFAULT_OUT_MD))
    args = ap.parse_args(argv)
    records = load_jsonl(args.runs)
    judgements = load_jsonl(args.judgements)
    summary = summarise(records, keys=load_quality_keys(), judgements=judgements)
    out_md = Path(args.out_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render(summary, args, len(judgements)), encoding="utf-8")
    out_md.with_suffix(".json").write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"Wrote {out_md} and {out_md.with_suffix('.json')} (rerun records {len(records)}, judgements {len(judgements)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
