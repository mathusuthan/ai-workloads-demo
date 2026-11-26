"""Score Category 4 quality-rerun sessions and the original golden capture; write the analysis report.

Usage (from backend/):
    .venv/bin/python scripts/analyze_cat4_quality.py
    .venv/bin/python scripts/analyze_cat4_quality.py --runs path/runs.jsonl --judgements path/judgements.jsonl

Works with zero rerun records and without judgements (the "original capture" tables come from
replays/cat4_golden_replays.json). Writes <project>/analysis/cat4_quality_rerun.md and .json. Factual tables only.
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
    RUNG_IDS,
    RUNS_PATH,
    SYNTH_MAX_TOKENS,
    SYNTH_TIMEOUT_S,
    load_golden,
    load_jsonl,
    load_quality_keys,
    scope_line,
    session_questions,
    summarise,
)

DEFAULT_OUT_MD = PROJECT_DIR / "analysis" / "cat4_quality_rerun.md"

SHORT = {
    "naive_full_corpus": "R1 naive",
    "cached_full_corpus_citations": "R2 cached+cite",
    "hybrid_rag_rerank_citations": "R3 BM25+rerank",
    "cached_rerank_hybrid": "R4 cached-rerank",
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
                     _p(r["recall_after_bm25"]) if r.get("recall_after_bm25") else "—",
                     _p(r["recall_after_rerank"]) if r.get("recall_after_rerank") else "—",
                     _p(r.get("distractors_selected")) if r else "—",
                     f"{r.get('backfilled', 0)} / {r.get('invalid_picks', 0)}" if r else "—"])
    return rows


CONTAM_HEAD = ["group", "contaminated answers", "…distractor value stated", "…value stated without naming the other supplier",
               "…distractor chunk cited", "synthesis saw distractor text (exposure)", "citations at Deccan",
               "citations at distractors", "expected recall after BM25", "expected recall after rerank",
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
    """Group label; a non-original answer format is named (original-format labels are unchanged)."""
    fmt = g.get("answer_format") or "original"
    return f"{SHORT[g['rung_id']]} · s{g['scale']}" + ("" if fmt == "original" else f" · {fmt}")


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


def _detector_validation_lines(v: dict[str, Any] | None) -> list[str]:
    if not v:
        return ["No rerun records to validate the detector on.", ""]
    L = [f"Known absence claims: the judge's material errors on the two retrieval rungs (original answer format) whose "
         f"quoted claim matches the validation report's keyword rule — {v['known_claims']}. Detector flags "
         f"{v['detected']}/{v['known_claims']}" + (f" ({v['recall'] * 100:.0f}%)" if v["recall"] is not None else "")
         + f"; by form: {', '.join(f'{k} {n}' for k, n in sorted(v['detected_by_form'].items())) or '—'}.", ""]
    if v["missed"]:
        L += ["Missed:", ""] + [f"- {m['rung_id']} s{m['scale']} r{m['repeat_index']} {m['question']}: {m['claim_quote']}" for m in v["missed"]] + [""]
    hits = v["cached_full_corpus_corpus_form_hits"]
    L += [f"Documents-lack claims the detector finds in cached full-corpus answers (that rung saw every clause; the judge "
          f"reported a material error on {sum(1 for h in hits if h['judge_material_errors'])} of these answers): {len(hits)}.", ""]
    L += [f"- s{h['scale']} r{h['repeat_index']} {h['question']}: {h['sentence']}" for h in hits] + [""]
    return L


def _break_even_rows(rows: list[dict[str, Any]]) -> list[list[str]]:
    return [[f"{SHORT[r['a']]} vs {SHORT[r['b']]}", _usd(r["premium_a_usd"]), _usd(r["per_question_a_usd"]),
             _usd(r["premium_b_usd"]), _usd(r["per_question_b_usd"]),
             "—" if r["n_star"] is None else f"{r['n_star']:.2f}", r["verdict"]] for r in rows]


BE_HEAD = ["A vs B", "A one-off cache-write premium", "A warm $/question", "B premium", "B warm $/question", "N*", "result"]


def render(summary: dict[str, Any], args: argparse.Namespace, n_judgements: int) -> str:
    rr, oc = summary["rerun"], summary["original_capture"]
    L: list[str] = ["# Category 4 quality rerun — multi-document RAG", ""]
    L += [f"Generated {summary['generated_at']} · answer key `{summary['keys_version']}` · rerun records {rr['record_count']} "
          f"(ok sessions used {rr['ok_sessions_used']}, superseded {rr['superseded_record_count']}) · judgements {n_judgements} ({summary['judge']['ok']} ok, judge {JUDGE_MODEL}, "
          f"spend ${summary['judge']['spend_usd']:.4f})", ""]
    L += ["Sources: `" + str(args.runs) + "`, `" + str(args.judgements) + "`, `replays/cat4_golden_replays.json`, "
          "`app/data/cat4_quality_keys.json`. Every answer is scored; zero-citation, truncated and contaminated answers are "
          "reported, never dropped. Rates show hits/total (rate) [Wilson 95%]. Costs come from recorded tokens via "
          "`compute_run_finops` (billed = as recorded; cold = the cached call writes its whole prefix on question 1 of the "
          "session and reads after; warm = every cached-prefix token read).", ""]
    L += [f"Question scope line (rerun only): every rerun question is asked as `{scope_line()}` followed by a blank "
          "line and the original question — identically for all four rungs and both scales, in the synthesis message, the "
          "reranker query (rungs 3 and 4) and the BM25 query (rung 3). The original capture (golden replays) was asked "
          "WITHOUT it, so original-capture vs rerun differences include this change. The judge sees each answer's question "
          "as asked.", ""]
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

    g_groups = [(SHORT[r], oc["groups"][r]) for r in RUNG_IDS if r in oc["groups"]]
    L += ["## Original capture (golden replays, scale 1, n = 1 per rung × question)", ""]
    L += ["One answer per rung and question, captured once; audit-02's cached prefix was already warm from audit-01. "
          "Small n: read the intervals.", ""]
    L += _table(QUALITY_HEAD, _quality_rows(g_groups))
    L += ["### Original capture per question (key-fact hits / facts; citations)", ""]
    qrows = []
    for pid, q in session_questions():
        key = f"{pid}/{q['question_id']}"
        row = [key]
        for r in RUNG_IDS:
            if r not in oc["groups"]:
                continue
            s = oc["groups"][r]["per_question"].get(key)
            if not s:
                row.append("—")
                continue
            fr = s["fact_recall"]
            cit = "" if s["citation_count"] is None else f"; {s['citation_count']} cites, cited-chunk recall {s['expected_chunk_recall']['hits']}/{s['expected_chunk_recall']['total']}"
            missed = [f["fact_id"] for f in s["facts"] if not f["hit"]]
            row.append(f"{fr['hits']}/{fr['total']}{cit}" + (f"; missed {', '.join(missed)}" if missed else ""))
        qrows.append(row)
    L += _table(["question", *[SHORT[r] for r in RUNG_IDS if r in oc["groups"]]], qrows)
    L += ["### Original capture cost per question (USD)", ""]
    L += _table(COST_HEAD, _cost_rows(g_groups))
    L += _table(TOKEN_HEAD, _token_rows(g_groups))
    L += ["### Original capture break-even (warm $/question + one-off cache-write premium)", ""]
    L += _table(BE_HEAD, _break_even_rows(oc["break_even"])) if oc["break_even"] else ["No comparable pairs.", ""]
    L += ["### Original capture judge", ""]
    L += _table(JUDGE_HEAD, _judge_rows(g_groups))

    L += ["## Rerun (rung × scale)", ""]
    groups = [(_glabel(g), g) for g in rr["groups"].values()]
    if not groups:
        L += ["No ok rerun sessions yet (`scripts/cat4_quality_rerun.py` has not been run, or every session errored).", ""]
    else:
        L += ["### Quality", ""] + _table(QUALITY_HEAD, _quality_rows(groups))
        L += ["### Contamination and retrieval", ""]
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
              "claim about a term the documents do contain. Answer formats: "
              + ", ".join(f"`{f}`" for f in summary.get("answer_formats") or ["original"]) + ".", ""]
        L += _table(ABSENCE_HEAD, _absence_rows(groups))
        L += ["### Cost per question (USD, mean over answers)", ""] + _table(COST_HEAD, _cost_rows(groups))
        L += ["### Tokens per call", ""] + _table(TOKEN_HEAD, _token_rows(groups))
        L += ["### Break-even (questions sharing one cache write)", ""]
        L += ["cost_r(N) = P_r + N·c_r with P_r = measured one-off premium of writing the cached prefix (prefix tokens × "
              "(write − read) rate) and c_r = measured warm cost per question. N* = (P_a − P_b) / (c_b − c_a).", ""]
        for scale, rows in rr["break_even"].items():
            L += [f"Scale {scale}:", ""] + (_table(BE_HEAD, _break_even_rows(rows)) if rows else ["No comparable pairs yet.", ""])
        has_variant = any((g.get("answer_format") or "original") != "original" for _, g in groups)
        if has_variant and rr.get("break_even_adopted") and rr["break_even_adopted"] != rr["break_even"]:
            L += ["Adopted answer formats (what the app and its portfolio use: retrieval versions on their scoped_absence "
                  "sessions, full-corpus versions on the original):", ""]
            for scale, rows in rr["break_even_adopted"].items():
                L += [f"Scale {scale} (adopted):", ""] + (_table(BE_HEAD, _break_even_rows(rows)) if rows else ["No comparable pairs yet.", ""])
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
    for r, g in oc["groups"].items():
        for qk, s in g["per_question"].items():
            if s["zero_citations"]:
                zero.append([f"{SHORT[r]} · golden", qk, "1/1"])
    L += _table(["group", "question", "zero-citation answers"], zero) if zero else ["No zero-citation answers on a citation rung.", ""]
    ca = summary["for_lead_review"]["contaminated_answers"]
    if ca:
        L += _table(["source", "group", "question", "distractor values", "distractor chunks cited"],
                    [[c["source"], f"{SHORT[c['rung_id']]} · s{c['scale']} r{c['repeat_index']}", c["question"],
                      "; ".join(f"{v['value']} ({v['supplier']}, {v['fact_id']}"
                                + (", other supplier named nearby" if v.get("attributed_to_distractor") else "") + ")"
                                for v in c["distractor_values"]) or "—",
                      ", ".join(c["distractor_chunks_cited"]) or "—"] for c in ca])
    else:
        L += ["No contaminated answers.", ""]

    L += ["## Absence-claim detector validation", ""] + _detector_validation_lines(summary.get("absence_detector_validation"))
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
                L.append(f"- {c['source']} {SHORT[c['rung_id']]} s{c['scale']} r{c['repeat_index']} {c['question']}: "
                         f"`{v['value']}` ({v['supplier']}{tag}) — …{(v.get('answer_excerpt') or '(not located in raw text)').replace(chr(10), ' ')}…")
        L.append("")
    L += ["- The answer key was written from the question texts and Deccan chunks only; one dry pass over the golden "
          "answers added format variants (see key `meta.format_variants_added`).",
          "- Golden capture: audit-02 questions read a cache written by audit-01 (no write), n = 1 per cell.",
          "- BM25 phrase bonuses and chunk keywords in `retriever.py` / fixtures were tuned on these questions and Deccan values; "
          "rung 3 retrieval recall is optimistic for unseen questions.",
          "- Four original questions (audit-01/q2, q3; audit-02/q3, q4) do not name the supplier; the rerun's scope line names it. "
          "Golden answers were scored on the unscoped questions.",
          "- The contamination detector cannot flag a distractor value that also occurs in Deccan's own documents; such values are excluded.",
          ""]

    L += ["## Data quality", ""]
    dq = rr["data_quality"]
    labels = {"superseded_sessions": "superseded: recorded at a different output cap (excluded from every table)"}
    for name, items in dq.items():
        if not isinstance(items, list):
            L.append(f"- {labels.get(name, name.replace('_', ' '))}: {'n/a (no judgements)' if items is None else items}")
            continue
        L.append(f"- {labels.get(name, name.replace('_', ' '))}: {len(items)}")
        for it in items[:15]:
            L.append(f"  - {json.dumps(it, ensure_ascii=False)}")
        if len(items) > 15:
            L.append(f"  - … {len(items) - 15} more (see JSON)")
    L.append("")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", default=str(RUNS_PATH))
    ap.add_argument("--judgements", default=str(JUDGEMENTS_PATH))
    ap.add_argument("--golden", default=str(BACKEND_DIR / "replays" / "cat4_golden_replays.json"))
    ap.add_argument("--out-md", default=str(DEFAULT_OUT_MD))
    args = ap.parse_args(argv)
    records = load_jsonl(args.runs)
    judgements = load_jsonl(args.judgements)
    summary = summarise(records, keys=load_quality_keys(), golden=load_golden(args.golden), judgements=judgements)
    out_md = Path(args.out_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render(summary, args, len(judgements)), encoding="utf-8")
    out_md.with_suffix(".json").write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"Wrote {out_md} and {out_md.with_suffix('.json')} (rerun records {len(records)}, judgements {len(judgements)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
