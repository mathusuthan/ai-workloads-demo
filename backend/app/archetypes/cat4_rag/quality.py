"""Category 4 answer quality for the app: deterministic answer-key scores per question + the recorded blind grade.

Deterministic measures (key facts stated, citations at the expected clauses, expected-clause recall, zero-citation
flag, retrieval recall) are free and run in every mode where the answer key covers the question. The grader's
verdict exists only for recorded answers (the quality rerun graded each one once); it is never run live.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.archetypes.cat4_rag.quality_rerun import (
    RETRIEVAL_RUNGS,
    build_scaled_corpus,
    facts_for,
    load_quality_keys,
    resolve_citations,
    score_answer,
)
from app.config import get_settings
from app.models import (
    Cat4AuditQuality,
    Cat4GraderError,
    Cat4GraderVerdict,
    Cat4Measure,
    Cat4QualityPortfolio,
    Cat4QueryResult,
    Cat4QuestionQuality,
    Cat4RungQuality,
)

LIVE_GRADER_REASON = (
    "The blind grader is not run live (each grade is a paid call); recorded runs carry one grade per answer."
)
NO_KEY_REASON = "No answer key covers this question, so key facts and expected clauses can't be scored."
NOT_SCORED_REASON = "The answer key could not be loaded."


def load_cat4_quality_portfolio() -> Cat4QualityPortfolio | None:
    """Pooled quality-rerun summary (replays/cat4_quality_summary.json); None if absent or unreadable."""
    path = Path(get_settings().replays_dir) / "cat4_quality_summary.json"
    if not path.is_file():
        return None
    try:
        return Cat4QualityPortfolio.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, OSError):
        return None


@lru_cache(maxsize=1)
def cached_quality_keys() -> dict[str, Any]:
    return load_quality_keys()


def _m(d: dict[str, int] | None) -> Cat4Measure | None:
    if d is None:
        return None
    hits, total = int(d["hits"]), int(d["total"])
    return Cat4Measure(hits=hits, total=total, rate=(hits / total) if total else None)


def _sum(ms: list[Cat4Measure | None]) -> Cat4Measure | None:
    ms = [m for m in ms if m is not None]
    if not ms:
        return None
    hits, total = sum(m.hits for m in ms), sum(m.total for m in ms)
    return Cat4Measure(hits=hits, total=total, rate=(hits / total) if total else None)


def grader_verdict(judgement: dict[str, Any] | None) -> Cat4GraderVerdict | None:
    if not judgement:
        return None
    errs = judgement.get("factual_errors") or []
    return Cat4GraderVerdict(
        grader_model=str(judgement.get("judge_model") or ""),
        correctness=int(judgement["correctness"]["score"]),
        completeness=int(judgement["completeness"]["score"]),
        correctness_justification=str(judgement["correctness"].get("justification") or ""),
        completeness_justification=str(judgement["completeness"].get("justification") or ""),
        answers_the_question=judgement["answers_the_question"],
        material_errors=[Cat4GraderError(claim_quote=e["claim_quote"], problem=e["problem"],
                                         source_quote=e["source_quote_or_absent"])
                         for e in errs if e.get("severity") == "material"],
        minor_error_count=sum(1 for e in errs if e.get("severity") == "minor"),
    )


def score_query(
    q: Cat4QueryResult,
    *,
    rung_id: str,
    preset_id: str,
    judgement: dict[str, Any] | None,
) -> Cat4QuestionQuality | None:
    """Score one answer against the key; None when the key does not cover (preset, question)."""
    out = _score_query(q, rung_id=rung_id, preset_id=preset_id, judgement=judgement)
    return out[0] if out else None


def _score_query(
    q: Cat4QueryResult,
    *,
    rung_id: str,
    preset_id: str,
    judgement: dict[str, Any] | None,
) -> tuple[Cat4QuestionQuality, dict[str, Any]] | None:
    keys = cached_quality_keys()
    if not facts_for(keys, preset_id, q.question_id):
        return None
    corpus = build_scaled_corpus(1)
    selected = [f.chunk_id for f in q.retrieval_funnel if f.stage == "selected_by_reranker"]
    expected = list(q.expected_chunk_ids)
    retrieval = None
    if rung_id in RETRIEVAL_RUNGS and q.retrieval_funnel:
        retrieval = {
            "selected_chunk_ids": selected,
            "recall_after_rerank": {"hits": len(set(expected) & set(selected)), "total": len(set(expected))},
            "backfilled_chunk_ids": [], "invalid_picks": [],
        }
    answer = {
        "preset_id": preset_id,
        "question_id": q.question_id,
        "answer_markdown": q.answer_markdown,
        "citations": resolve_citations(corpus, [c.model_dump() for c in q.citations]),
        "expected_chunk_ids": expected,
        "chunks_sent": {"mode": "chunks" if retrieval else "full_corpus", "chunk_ids": selected if retrieval else None},
        "retrieval": retrieval,
    }
    s = score_answer(answer, rung_id=rung_id, corpus=corpus, keys=keys, contamination=None)
    desc = {f["id"]: f["description"] for f in facts_for(keys, preset_id, q.question_id)}
    cit = bool(s["citations_requested"])
    return Cat4QuestionQuality(
        question_id=q.question_id,
        question_number=q.question_number,
        key_facts=_m(s["fact_recall"]),
        missed_facts=[desc[r["fact_id"]] for r in s["facts"] if not r["hit"]],
        citations_requested=cit,
        citation_count=s["citation_count"],
        zero_citations=s["zero_citations"],
        citations_at_expected=_m(s["citations_at_expected"]) if cit else None,
        expected_clause_recall=_m(s["expected_chunk_recall"]) if cit else None,
        retrieval_recall=_m((s["retrieval"] or {}).get("recall_after_rerank")) if s["retrieval"] else None,
        stop_reason=q.stop_reason,
        grader=grader_verdict(judgement),
    ), s


def build_rung_quality(
    queries: list[Cat4QueryResult],
    *,
    rung_id: str,
    preset_id: str,
    judgements: list[dict[str, Any] | None] | None,
    grader_unavailable_reason: str | None = None,
) -> tuple[Cat4RungQuality | None, str | None]:
    """(quality, reason-if-None). `judgements` aligns with `queries` (None entries = not graded)."""
    try:
        keys = cached_quality_keys()
    except (OSError, ValueError):
        return None, NOT_SCORED_REASON
    js = judgements or [None] * len(queries)
    rows = [_score_query(q, rung_id=rung_id, preset_id=preset_id, judgement=j) for q, j in zip(queries, js)]
    if not queries or any(r is None for r in rows):
        return None, NO_KEY_REASON
    qs: list[Cat4QuestionQuality] = [r[0] for r in rows if r is not None]
    raw = [r[1] for r in rows if r is not None]
    graded = [r.grader for r in qs if r.grader is not None]
    spec = _sum([_m(x["fact_recall_supplier_specific"]) for x in raw])
    spec_hits, spec_total = (spec.hits, spec.total) if spec else (0, 0)
    cit = qs[0].citations_requested
    audit = Cat4AuditQuality(
        questions=len(qs),
        key_facts=_sum([r.key_facts for r in qs]),
        key_facts_supplier_specific=Cat4Measure(hits=spec_hits, total=spec_total, rate=(spec_hits / spec_total) if spec_total else None),
        citations_requested=cit,
        citations_at_expected=_sum([r.citations_at_expected for r in qs]) if cit else None,
        expected_clause_recall=_sum([r.expected_clause_recall for r in qs]) if cit else None,
        zero_citation_answers=sum(1 for r in qs if r.zero_citations) if cit else None,
        retrieval_recall=_sum([r.retrieval_recall for r in qs]),
        judged=len(graded),
        correctness_mean=(sum(g.correctness for g in graded) / len(graded)) if graded else None,
        completeness_mean=(sum(g.completeness for g in graded) / len(graded)) if graded else None,
        material_errors=sum(len(g.material_errors) for g in graded) if graded else None,
        answers_with_material_error=sum(1 for g in graded if g.material_errors) if graded else None,
    )
    return (
        Cat4RungQuality(
            keys_version=keys["meta"].get("keys_version"),
            audit=audit,
            questions=qs,
            grader_unavailable_reason=None if graded else (grader_unavailable_reason or LIVE_GRADER_REASON),
        ),
        None,
    )
