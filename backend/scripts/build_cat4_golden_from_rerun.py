"""Rebuild replays/cat4_golden_replays.json and replays/cat4_quality_summary.json from the Category 4 quality rerun.

Golden replays — fixed, pre-declared mapping (never chosen by outcome): repeat_index 0, corpus scale 1 (the app's
7-document deal room), of both versions the app runs: without the improvement (`naive_full_corpus`) and with it
(`cached_rerank_hybrid`). Each rerun session asked all 8 questions in one session (audit-01 q1-q4, then audit-02
q1-q4); the session is split by audit preset here. Each question keeps the schema
`runner._build_cat4_summary_from_replay` reads, plus: real `stop_reason`s for synthesis and clause-pick calls,
`question_as_asked` (every question is prefixed with a supplier-scope line; `question` is the question text),
thinking tokens, the session question index and the blind grader's judgement of that exact answer. The clauses Haiku
picked are rebuilt from the recorded pick output and checked against the recorded selection.

Billing note (also in provenance): the paired version wrote its clause cache once per session, on audit-01 q1;
audit-02 q1 was billed as a cache READ. The app's cold-audit cost still models a fresh cache write per audit — that
is a model, not what audit-02 was billed.

Quality summary — both versions x both corpus sizes from the same `quality_rerun.summarise()` path as
scripts/analyze_cat4_quality.py. The app reads both files at runtime (analysis/ and experiments/ are not in the
Docker image).

Inputs are only read. Idempotent: a file whose content is unchanged (ignoring `provenance.rebuilt_at`) is not
rewritten.

Usage (from backend/):
    .venv/bin/python scripts/build_cat4_golden_from_rerun.py [--in runs.jsonl] [--judgements judgements.jsonl]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat4_rag.quality_rerun import (  # noqa: E402
    APP_RUNG_IDS,
    GOLDEN_REPEAT_INDEX,
    GOLDEN_SCALE,
    JUDGE_MODEL,
    build_quality_portfolio,
    build_scaled_corpus,
    is_current_settings,
    load_jsonl,
    load_quality_keys,
    scope_line,
    _sha,
    answer_format_of,
)
from app.archetypes.cat4_rag.answer_formats import rung_answer_format  # noqa: E402
from app.archetypes.cat4_rag.paired import PAIRED_RUNG, picked_funnel, select_picked_chunks  # noqa: E402
from app.archetypes.cat4_rag.runner import build_rung3_chunk_blocks  # noqa: E402
from app.data.cat4_fixtures import CAT4_PRESETS  # noqa: E402

DEFAULT_IN = BACKEND_DIR / "experiments" / "cat4_quality" / "runs.jsonl"
DEFAULT_JUDGEMENTS = BACKEND_DIR / "experiments" / "cat4_quality" / "judgements.jsonl"
DEFAULT_OUT = BACKEND_DIR / "replays" / "cat4_golden_replays.json"
DEFAULT_SUMMARY_OUT = BACKEND_DIR / "replays" / "cat4_quality_summary.json"
USE_CASE = "supplier_msa_due_diligence"
CITATION_FIELDS = ("cite_number", "doc_id", "document_title", "clause_ref", "cited_text", "start_char_index", "end_char_index")
BILLING_NOTE = (
    "Each rerun session asked all 8 questions in order (audit-01 q1-q4, then audit-02 q1-q4). The paired version wrote "
    "its clause cache once, on audit-01 q1; audit-02 q1 was billed as a cache read, not a write. The app's cold-audit "
    "cost models a fresh cache write for each audit; for audit-02 that is a model, not what was billed."
)


def select_session(records: Iterable[dict[str, Any]], rung_id: str) -> dict[str, Any]:
    """Latest ok record at the current settings for (rung, scale 1, repeat 0) — the analysis' rule. Fixed in advance,
    never chosen by outcome."""
    chosen = None
    for r in records:
        if (r.get("status") == "ok" and is_current_settings(r) and r.get("rung_id") == rung_id
                and int(r.get("scale", -1)) == GOLDEN_SCALE and int(r.get("repeat_index", -1)) == GOLDEN_REPEAT_INDEX):
            chosen = r
    if chosen is None:
        raise ValueError(f"No ok rerun record for {rung_id} / scale {GOLDEN_SCALE} / repeat {GOLDEN_REPEAT_INDEX}")
    return chosen


def judgement_index(judgements: Iterable[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """(run_id, answer sha) -> latest ok judgement."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for j in judgements:
        if j.get("status") == "ok" and j.get("source") == "rerun" and j.get("parsed"):
            out[(str(j.get("run_id")), str(j.get("answer_sha256")))] = j
    return out


def _judgement_for(jidx: dict[tuple[str, str], dict[str, Any]], run_id: str, answer: str) -> dict[str, Any] | None:
    j = jidx.get((run_id, _sha(answer)))
    if not j:
        return None
    p = j["parsed"]
    return {
        "judge_model": j.get("model_id") or JUDGE_MODEL,
        "call_id": j["call_id"],
        "correctness": p["correctness"],
        "completeness": p["completeness"],
        "factual_errors": p["factual_errors"],
        "answers_the_question": p["answers_the_question"],
    }


def convert_answer(answer: dict[str, Any], *, rung_id: str, run_id: str, q_spec: dict[str, Any],
                   jidx: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    """One rerun answer -> one golden question (runner replay schema + provenance detail)."""
    corpus = build_scaled_corpus(GOLDEN_SCALE)
    total_chars = corpus.total_chars
    synth = next(c for c in answer["calls"] if c["role"] == "synthesis")
    rerank = next((c for c in answer["calls"] if c["role"] == "rerank"), None)
    funnel: list[dict[str, Any]] = []
    payload = None
    rerank_recall = None
    ctx_chars = total_chars
    if rung_id == PAIRED_RUNG:
        ret = answer["retrieval"]
        selected, _invalid = select_picked_chunks(corpus.chunk_by_id, ret["reranker_raw"])
        if [c["chunk_id"] for c in selected] != ret["selected_chunk_ids"]:
            raise ValueError(f"Clause picks do not reproduce for {run_id} {answer['preset_id']}/{answer['question_id']}")
        funnel, rerank_recall = picked_funnel(selected, ret["reranker_raw"], list(q_spec.get("expected_chunk_ids") or []))
        payload = answer["question_as_asked"]
        ctx_chars = sum(len(b["data"]) for b in build_rung3_chunk_blocks(selected))
    reduction = round(((total_chars - ctx_chars) / total_chars) * 100, 1) if rung_id == PAIRED_RUNG else 0.0
    return {
        "question_id": q_spec["question_id"],
        "question_number": int(q_spec["question_number"]),
        "topic_tag": q_spec["topic_tag"],
        "question": answer["question"],
        "question_as_asked": answer["question_as_asked"],
        "session_q_index": int(answer["q_index"]),
        "model_id": synth["model_id"],
        "latency_ms": int(synth["latency_ms"]),
        "stop_reason": synth.get("stop_reason"),
        "max_tokens": int(synth.get("max_tokens") or 0),
        "input_tokens": int(synth["input_tokens"]),
        "output_tokens": int(synth["output_tokens"]),
        "thinking_tokens": int(synth.get("thinking_tokens") or 0),
        "cache_creation_tokens": int(synth.get("cache_creation_tokens") or 0),
        "cache_read_tokens": int(synth.get("cache_read_tokens") or 0),
        "answer_markdown": answer["answer_markdown"],
        "segments": [{"text": s["text"], "cite_numbers": list(s.get("cite_numbers") or [])} for s in answer.get("segments") or []],
        "citations": [{k: c[k] for k in CITATION_FIELDS} for c in answer.get("citations") or []],
        "context_chars_sent": ctx_chars,
        "context_reduction_pct": reduction,
        "reranker_model_id": rerank["model_id"] if rerank else None,
        "reranker_stop_reason": rerank.get("stop_reason") if rerank else None,
        "reranker_latency_ms": int(rerank["latency_ms"]) if rerank else 0,
        "reranker_input_tokens": int(rerank["input_tokens"]) if rerank else 0,
        "reranker_output_tokens": int(rerank["output_tokens"]) if rerank else 0,
        "reranker_cache_creation_tokens": int(rerank.get("cache_creation_tokens") or 0) if rerank else 0,
        "reranker_cache_read_tokens": int(rerank.get("cache_read_tokens") or 0) if rerank else 0,
        "reranker_payload": payload,
        "reranker_structured": (answer.get("retrieval") or {}).get("reranker_raw") if rerank else None,
        "retrieval_funnel": funnel,
        "reranker_recall_pct": rerank_recall,
        "judgement": _judgement_for(jidx, run_id, answer["answer_markdown"]),
    }


def build_golden(records: list[dict[str, Any]], judgements: list[dict[str, Any]], *, source_file: str,
                 judgements_file: str, keys_version: str | None) -> dict[str, Any]:
    """Golden-replay document without the rebuild timestamp (added by `write_if_changed`)."""
    jidx = judgement_index(judgements)
    sessions = {rid: select_session(records, rid) for rid in APP_RUNG_IDS}
    presets: dict[str, Any] = {}
    for preset in CAT4_PRESETS:
        pid = preset["id"]
        specs = {q["question_id"]: q for q in preset["questions"]}
        rungs: dict[str, list[dict[str, Any]]] = {}
        prov: dict[str, Any] = {}
        for rid, rec in sessions.items():
            answers = [a for a in rec["answers"] if a["preset_id"] == pid]
            if len(answers) != len(preset["questions"]) or any(a.get("status") != "ok" for a in answers):
                raise ValueError(f"{rid} session {rec['run_id']} is incomplete for {pid}")
            rungs[rid] = [convert_answer(a, rung_id=rid, run_id=rec["run_id"], q_spec=specs[a["question_id"]], jidx=jidx)
                          for a in answers]
            prov[rid] = {
                "run_id": rec["run_id"],
                "answer_format": answer_format_of(rec),
                "repeat_index": int(rec["repeat_index"]),
                "scale": int(rec["scale"]),
                "session_nonce": rec.get("session_nonce"),
                "started_at": rec.get("started_at"),
                "session_questions": [f"{a['preset_id']}/{a['question_id']}" for a in rec["answers"]],
                "questions_in_this_preset_at_session_index": [int(a["q_index"]) for a in answers],
                "settings": rec.get("settings"),
                "keys_version_at_capture": rec.get("keys_version"),
            }
        presets[pid] = {"use_case": USE_CASE, "rungs": rungs, "provenance": prov}
    return {
        "provenance": {
            "source": "cat4 quality rerun",
            "source_file": source_file,
            "judgements_file": judgements_file,
            "selection_rule": (f"fixed pre-declared mapping: repeat_index {GOLDEN_REPEAT_INDEX}, corpus scale {GOLDEN_SCALE}, "
                               "both versions the app runs; the session's 8 questions split by audit preset (not selected "
                               "by outcome)"),
            "answer_formats": {rid: rung_answer_format(rid) for rid in APP_RUNG_IDS},
            "keys_version": keys_version,
            "question_scope_line": scope_line(),
            "question_note": "`question` is the text shown in the app; `question_as_asked` is what the model received.",
            "billing_note": BILLING_NOTE,
        },
        "presets": presets,
    }


def _comparable(doc: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(doc))
    (out.get("provenance") or {}).pop("rebuilt_at", None)
    return out


def write_if_changed(doc: dict[str, Any], out_path: Path, *, stamp: bool) -> bool:
    if out_path.is_file():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = None
        if existing is not None and _comparable(existing) == _comparable(doc):
            return False
    out_doc = dict(doc)
    if stamp:
        out_doc["provenance"] = {**doc["provenance"], "rebuilt_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(BACKEND_DIR))
    except ValueError:
        return str(p)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="in_path", default=str(DEFAULT_IN))
    ap.add_argument("--judgements", default=str(DEFAULT_JUDGEMENTS))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--summary-out", default=str(DEFAULT_SUMMARY_OUT))
    args = ap.parse_args(argv)
    in_path, j_path = Path(args.in_path), Path(args.judgements)
    records, judgements = load_jsonl(in_path), load_jsonl(j_path)
    keys = load_quality_keys()

    golden = build_golden(records, judgements, source_file=_rel(in_path), judgements_file=_rel(j_path),
                          keys_version=keys["meta"].get("keys_version"))
    changed = write_if_changed(golden, Path(args.out), stamp=True)
    for pid, p in golden["presets"].items():
        for rid, qs in p["rungs"].items():
            prov = p["provenance"][rid]
            print(f"{pid} {rid:<30} <- r{prov['repeat_index']} s{prov['scale']} {prov['run_id'][:8]} | questions={len(qs)} "
                  f"stops={sorted({q['stop_reason'] for q in qs})} judged={sum(1 for q in qs if q['judgement'])} "
                  f"clause cache w/r={[(q['reranker_cache_creation_tokens'] > 0, q['reranker_cache_read_tokens'] > 0) for q in qs] if rid == PAIRED_RUNG else '-'}")
    print(f"{'Wrote' if changed else 'Unchanged:'} {args.out}")

    portfolio = build_quality_portfolio(records, judgements, keys=keys, source_file=_rel(in_path), judgements_file=_rel(j_path))
    changed = write_if_changed(portfolio, Path(args.summary_out), stamp=False)
    for c in portfolio["cells"]:
        print(f"  {c['rung_id']:<30} s{c['scale']} n={c['answers']} facts {c['fact_recall']['hits']}/{c['fact_recall']['total']} "
              f"correctness {c['correctness_mean']:.2f} material {c['answers_with_material_error']['hits']}/{c['judged']} "
              f"${c['cost_per_question_billed_usd']:.4f}/q billed")
    print(f"{'Wrote' if changed else 'Unchanged:'} {args.summary_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
