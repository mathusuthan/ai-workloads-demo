"""Category 4 quality rerun: scaled-corpus sessions, deterministic answer-key scoring, blind judge, summaries.

Importable without an API key; nothing here changes `runner.py` behaviour. A SESSION is one rung answering
all 8 audit questions in order (audit-01 q1–q4, then audit-02 q1–q4) on one corpus scale (1 = the app's
7-document deal room, 3 = + two deterministic distractor suppliers, see `scaled_corpus.py`).

Rungs (the first three exactly as the app runs them, through the app's builders and call wrappers):
  naive_full_corpus             all documents as uncached plain text, no citations
  cached_full_corpus_citations  document blocks, cache_control on the last, native citations; a per-session
                                nonce line opens the first document block so each session writes its own cache
  hybrid_rag_rerank_citations   BM25 over the session corpus -> top 10 -> Haiku rerank -> top 5 -> Sonnet + citations
  cached_rerank_hybrid (NEW)    Haiku reranker reads the FULL corpus as one cached block (per-session nonce) +
                                the question and returns the top-5 chunk ids (same schema); Sonnet synthesises
                                over exactly those chunks with citations as rung 3 does. No BM25 stage.

Every rerun question is asked as `scoped_question(q)`: one fixed supplier-scope line built from DEAL_ROOM_PROFILE,
a blank line, then the original text (same for all rungs and scales; the golden capture was asked without it).
Records hold raw tokens only (never dollars); costs come from `app.core.pricing.compute_run_finops` at
analysis time. Every answer is kept — zero-citation answers, truncations and contamination are data.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import statistics
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.archetypes.cat3_assistants.scoring import normalise_text
from app.archetypes.cat4_rag.prompts import (
    get_cat4_haiku_reranker_system_prompt,
    get_cat4_synthesis_system_prompt,
)
from app.archetypes.cat4_rag.retriever import (
    BM25_TOP_K,
    RERANK_TOP_K,
    build_reranker_payload,
    merge_rerank_funnel,
    rank_chunks_bm25,
)
from app.archetypes.cat4_rag.runner import (
    build_rung2_doc_blocks,
    build_rung3_chunk_blocks,
    build_uncached_corpus_text,
)
from app.archetypes.cat4_rag.scaled_corpus import (  # noqa: F401 — re-exported
    BASE_SUPPLIER,
    DISTRACTOR_SUPPLIERS,
    DOCUMENT_ORDER,
    SCALES,
    SUPPLIERS,
    ScaledCorpus,
    build_scaled_corpus,
    corpus_size,
    transform_text,
)
from app.archetypes.cat4_rag.schemas import RERANK_JSON_SCHEMA
from app.archetypes.cat6_swarms.fair_rerun import wilson_interval
from app.core.anthropic_service import AnthropicRawResult
from app.core.pricing import MODEL_RATES, compute_run_finops
from app.data.cat4_fixtures import CAT4_PRESETS, DEAL_ROOM_PROFILE

SCHEMA_VERSION = 1
BACKEND_DIR = Path(__file__).resolve().parents[3]
KEYS_PATH = BACKEND_DIR / "app" / "data" / "cat4_quality_keys.json"
GOLDEN_PATH = BACKEND_DIR / "replays" / "cat4_golden_replays.json"
EXPERIMENT_DIR = BACKEND_DIR / "experiments" / "cat4_quality"
RUNS_PATH = EXPERIMENT_DIR / "runs.jsonl"
JUDGEMENTS_PATH = EXPERIMENT_DIR / "judgements.jsonl"

APP_RUNG_IDS: tuple[str, ...] = ("naive_full_corpus", "cached_full_corpus_citations", "hybrid_rag_rerank_citations")
NEW_RUNG = "cached_rerank_hybrid"
RUNG_IDS: tuple[str, ...] = (*APP_RUNG_IDS, NEW_RUNG)
CITATION_RUNGS = frozenset(RUNG_IDS[1:])
RETRIEVAL_RUNGS = frozenset({"hybrid_rag_rerank_citations", NEW_RUNG})
CACHED_CALL: dict[str, str] = {"cached_full_corpus_citations": "synthesis", NEW_RUNG: "rerank"}

SONNET_MODEL_ID = "claude-sonnet-5-5"
HAIKU_MODEL_ID = "claude-haiku-5-5"
INTENDED_MODEL = {"synthesis": SONNET_MODEL_ID, "rerank": HAIKU_MODEL_ID}
# Synthesis cap is 4,096, NOT the app's 2,048: the live pilot (8 sessions) had 3/64 answers stop on max_tokens at 2,048.
# The app's live path raises on truncation and the original capture rejected non-end_turn answers, so the original
# data holds no truncated answer; the rerun must not either. Same cap for all four rungs and both scales.
# Sessions recorded at another cap are superseded (re-run on resume, excluded from analysis).
SYNTH_MAX_TOKENS = 4096
# Rerank cap as in the app (runner._run_live_cat4_query_for_rung). Explicit timeouts (the app uses 90 s / 45 s).
RERANK_MAX_TOKENS = 800
SYNTH_TIMEOUT_S = 300.0
RERANK_TIMEOUT_S = 180.0
DEFAULT_MAX_RETRIES = 0  # nothing silently re-billed; a failed call is an error record and the session is retried
HAIKU_LONG_PROMPT_TOKENS = 100_000


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def session_questions() -> list[tuple[str, dict[str, Any]]]:
    """The 8 questions of a session in order: audit-01 q1..q4, then audit-02 q1..q4."""
    return [(p["id"], q) for p in CAT4_PRESETS for q in p["questions"]]


def question_key(preset_id: str, question_id: str) -> str:
    return f"{preset_id}/{question_id}"


SCOPE_LINE_TEMPLATE = "Deal room under audit: {deal_room_id} (supplier: {supplier_legal_name}). Answer for this supplier's contracts only."


def scope_line() -> str:
    """The fixed supplier-scope line prepended to every rerun question (all rungs, both scales)."""
    return SCOPE_LINE_TEMPLATE.format(deal_room_id=DEAL_ROOM_PROFILE["deal_room_id"],
                                      supplier_legal_name=DEAL_ROOM_PROFILE["supplier_legal_name"])


def scoped_question(question: str) -> str:
    """Scope line, a blank line, then the original question text. The golden capture was asked without it."""
    return f"{scope_line()}\n\n{question}"


# --------------------------------------------------------------------------------------------------
# Matching (Category 3 normaliser + boundary guard, plus a decimal guard)
# --------------------------------------------------------------------------------------------------


def contains_alternative(normalised_text: str, alternative: str) -> bool:
    """Category 3 boundary-guarded containment, plus: a digit-initial alternative must not follow
    '<digit>.' and a digit-final one must not be followed by '.<digit>' ('25 crore' does not hit '33.25 crore')."""
    alt = normalise_text(alternative)
    if not alt:
        return False
    t, start = normalised_text, 0
    while True:
        i = t.find(alt, start)
        if i < 0:
            return False
        j = i + len(alt)
        ok = not (alt[0].isalnum() and i > 0 and t[i - 1].isalnum())
        ok = ok and not (alt[0].isdigit() and i >= 2 and t[i - 1] == "." and t[i - 2].isdigit())
        ok = ok and not (alt[-1].isdigit() and j < len(t) and t[j].isdigit())
        ok = ok and not (alt[-1].isdigit() and j + 1 < len(t) and t[j] == "." and t[j + 1].isdigit())
        if ok:
            return True
        start = i + 1


def text_matches(text: str | None, alternatives: Sequence[str]) -> bool:
    nt = normalise_text(text)
    return any(contains_alternative(nt, a) for a in alternatives)


# --------------------------------------------------------------------------------------------------
# Answer key
# --------------------------------------------------------------------------------------------------


def load_quality_keys(path: Path | str | None = None) -> dict[str, Any]:
    return json.loads(Path(path or KEYS_PATH).read_text(encoding="utf-8"))


@lru_cache(maxsize=4)
def _cached_keys(path: str) -> dict[str, Any]:
    return load_quality_keys(path)


def facts_for(keys: dict[str, Any], preset_id: str, question_id: str) -> list[dict[str, Any]]:
    return [f for f in keys["facts"] if f["preset_id"] == preset_id and f["question_id"] == question_id]


def fact_alternatives(fact: dict[str, Any]) -> list[str]:
    return [*fact["any_of"], *(x["alt"] for x in fact.get("also_in_corpus") or []), *(fact.get("format_variants") or [])]


def chunk_search_text(chunk: dict[str, Any]) -> str:
    """What an alternative is tested against: block text (header + body), section heading and keywords."""
    return f"{chunk['full_block_text']}\n{chunk['section_heading']}\n{' | '.join(chunk.get('keywords') or [])}"


def key_counts(keys: dict[str, Any]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for f in keys["facts"]:
        c = out.setdefault(question_key(f["preset_id"], f["question_id"]), {"facts": 0, "supplier_specific": 0})
        c["facts"] += 1
        c["supplier_specific"] += int(bool(f["supplier_specific"]))
        c[f["category"]] = c.get(f["category"], 0) + 1
    return out


def _distractor_chunk_id(chunk_id: str, supplier: str) -> str:
    doc, part = chunk_id.split("#")
    return f"DOC-{int(doc.split('-')[1]) + SUPPLIERS[supplier].doc_id_offset:02d}#{part}"


@lru_cache(maxsize=4)
def _contamination_index(keys_path: str) -> dict[str, dict[str, list[str]]]:
    return build_contamination_index(_cached_keys(keys_path))


def build_contamination_index(keys: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    """fact_id -> {supplier: [that supplier's value for the fact]} for every supplier-specific fact.

    Each alternative goes through the supplier transform; an alternative the transform leaves alone on its own
    (a bare number such as "1,250") takes the distractor value recorded for it in the supplier's corresponding
    chunk(s). Values that also occur anywhere in the Deccan corpus are dropped (they cannot mark contamination).
    """
    c3 = build_scaled_corpus(3)
    base_texts = [normalise_text(chunk_search_text(c)) for c in build_scaled_corpus(1).flat_chunks]
    out: dict[str, dict[str, list[str]]] = {}
    for f in keys["facts"]:
        if not f["supplier_specific"]:
            continue
        own_chunks = [f["chunk_id"], *(x["chunk_id"] for x in f.get("also_in_corpus") or [])]
        entry: dict[str, list[str]] = {}
        for s in DISTRACTOR_SUPPLIERS:
            targets = {_distractor_chunk_id(c, s) for c in own_chunks}
            recs = [r for r in c3.mapping[s] if r["where"].split(".")[0] in targets]
            vals: list[str] = []
            for alt in fact_alternatives(f):
                new, _ = transform_text(alt, s)
                cands = [new] if normalise_text(new) != normalise_text(alt) else []
                if not cands:
                    na = normalise_text(alt)
                    for r in recs:
                        if r.get("original_number") and normalise_text(r["original_number"]) == na:
                            cands.append(r["distractor_number"])
                        elif contains_alternative(normalise_text(r["original"]), alt):
                            cands.append(r["distractor"])
                for v in cands:
                    if v not in vals and not any(contains_alternative(bt, v) for bt in base_texts):
                        vals.append(v)
            entry[s] = vals
        out[f["id"]] = entry
    return out


# --------------------------------------------------------------------------------------------------
# Citations -> chunks
# --------------------------------------------------------------------------------------------------


def resolve_chunk_id(corpus: ScaledCorpus, doc_id: str, start: int, end: int) -> str | None:
    """Chunk of `doc_id` with the largest overlap with [start, end) (document-relative offsets)."""
    doc = corpus.doc_by_id.get(doc_id)
    if not doc:
        return None
    best, best_ov = None, 0
    for ch in doc["chunks"]:
        ov = min(end, ch["doc_char_end"]) - max(start, ch["doc_char_start"])
        if ov > best_ov:
            best, best_ov = ch["chunk_id"], ov
    if best is None:  # zero-width span: the chunk containing `start`
        for ch in doc["chunks"]:
            if ch["doc_char_start"] <= start <= ch["doc_char_end"]:
                return ch["chunk_id"]
    return best


def resolve_citations(corpus: ScaledCorpus, citations: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for c in citations:
        cid = resolve_chunk_id(corpus, str(c.get("doc_id") or ""), int(c.get("start_char_index") or 0),
                               int(c.get("end_char_index") or 0))
        out.append({**c, "chunk_id": cid, "supplier": corpus.supplier_of_chunk(cid) if cid else None})
    return out


# --------------------------------------------------------------------------------------------------
# Prompt / block builders for the rerun
# --------------------------------------------------------------------------------------------------

_APP_RERANK_LINE = "From the 10 BM25 candidate contract chunks, select the EXACT 5 most decisive chunks needed to answer the query completely."
_FULL_CORPUS_RERANK_LINE = "From all deal-room contract chunks provided above the query, select the EXACT 5 most decisive chunks needed to answer the query completely."


def get_full_corpus_reranker_system_prompt() -> str:
    """The app's reranker prompt with only its candidate-set sentence changed (rules 1–3 identical)."""
    base = get_cat4_haiku_reranker_system_prompt()
    if _APP_RERANK_LINE not in base:
        raise RuntimeError("App reranker prompt changed; update the full-corpus variant")
    return base.replace(_APP_RERANK_LINE, _FULL_CORPUS_RERANK_LINE)


def nonce_line(nonce: str) -> str:
    return f"[deal-room session {nonce}]\n"


def build_rung2_session_blocks(corpus: ScaledCorpus, nonce: str) -> list[dict[str, Any]]:
    """App document blocks with the session nonce opening the first block (offset shifted so citations stay
    relative to the original document text)."""
    blocks = build_rung2_doc_blocks(corpus.hydrated_docs)
    line = nonce_line(nonce)
    blocks[0] = {**blocks[0], "data": line + blocks[0]["data"], "doc_char_offset": -len(line)}
    return blocks


def format_full_corpus_for_reranker(corpus: ScaledCorpus) -> str:
    """Every chunk in the reranker's candidate format (same fields as `build_reranker_payload`, minus BM25 rank)."""
    blocks = [
        f"CHUNK_ID: {ch['chunk_id']} | DOC: {ch['doc_code']} — {ch['doc_title']} | CLAUSE: {ch['clause_ref']}\n"
        f"HEADING: {ch['section_heading']}\n"
        f"EXCERPT:\n{ch['text']}"
        for ch in corpus.flat_chunks
    ]
    return (f"=== DEAL-ROOM CHUNKS (full corpus: {len(blocks)} chunks) ===\n\n" + "\n\n---\n\n".join(blocks))


def build_full_corpus_rerank_content(corpus: ScaledCorpus, question: str, nonce: str) -> list[dict[str, Any]]:
    return [
        {"type": "text", "text": nonce_line(nonce) + format_full_corpus_for_reranker(corpus),
         "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": (f"=== DUE-DILIGENCE QUERY ===\n{question}\n\n"
                                  f"Select the exact {RERANK_TOP_K} most decisive chunks from the deal-room chunks above.")},
    ]


def select_full_corpus_chunks(corpus: ScaledCorpus, structured: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[str]]:
    """Valid, de-duplicated reranker picks in order (at most 5; no backfill) and the invalid ids returned."""
    by_id = corpus.chunk_by_id
    picked: list[dict[str, Any]] = []
    invalid: list[str] = []
    for entry in (structured or {}).get("selected_chunks") or []:
        cid = str(entry.get("chunk_id") or "").strip()
        if cid not in by_id:
            invalid.append(cid)
            continue
        if any(p["chunk_id"] == cid for p in picked):
            continue
        picked.append(by_id[cid])
        if len(picked) >= RERANK_TOP_K:
            break
    return picked, invalid


# --------------------------------------------------------------------------------------------------
# Session execution (injectable call wrappers)
# --------------------------------------------------------------------------------------------------

SynthCall = Callable[..., Awaitable[AnthropicRawResult]]
RerankCall = Callable[..., Awaitable[AnthropicRawResult]]


def _call_record(role: str, raw: AnthropicRawResult, *, max_tokens: int, timeout_s: float, cached: bool) -> dict[str, Any]:
    return {
        "role": role,
        "model_id": raw.model_id,
        "intended_model_id": INTENDED_MODEL[role],
        "stop_reason": raw.stop_reason,
        "input_tokens": int(raw.input_tokens),
        "output_tokens": int(raw.output_tokens),
        "thinking_tokens": int(raw.thinking_tokens or 0),
        "cache_creation_tokens": int(raw.cache_creation_tokens),
        "cache_read_tokens": int(raw.cache_read_tokens),
        "latency_ms": int(raw.latency_ms),
        "max_tokens": max_tokens,
        "timeout_s": timeout_s,
        "cache_control": cached,
        "request_params": raw.request_params,
    }


def _recall(expected: Sequence[str], got: Iterable[str]) -> dict[str, int]:
    exp = set(expected)
    return {"hits": len(exp & set(got)), "total": len(exp)}


async def run_question(
    *,
    rung_id: str,
    corpus: ScaledCorpus,
    q_spec: dict[str, Any],
    nonce: str,
    api_key: str,
    synth_call: SynthCall,
    rerank_call: RerankCall,
    max_retries: int | None = DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    """One question on one rung; raises on API failure (the session loop records it)."""
    q = scoped_question(str(q_spec["question"]))  # BM25 query, reranker query and synthesis user message
    expected = list(q_spec.get("expected_chunk_ids") or [])
    calls: list[dict[str, Any]] = []
    retrieval: dict[str, Any] | None = None
    doc_blocks: list[dict[str, Any]] | None = None
    uncached_text: str | None = None
    use_cache = False
    sent: dict[str, Any]

    if rung_id == "naive_full_corpus":
        uncached_text = build_uncached_corpus_text(corpus.hydrated_docs)
        sent = {"mode": "full_corpus", "documents": len(corpus.hydrated_docs), "chunk_ids": None}
    elif rung_id == "cached_full_corpus_citations":
        doc_blocks = build_rung2_session_blocks(corpus, nonce)
        use_cache = True
        sent = {"mode": "full_corpus", "documents": len(corpus.hydrated_docs), "chunk_ids": None}
    elif rung_id == "hybrid_rag_rerank_citations":
        ranked = rank_chunks_bm25(q, corpus.flat_chunks, top_k=BM25_TOP_K)
        candidates = [c for c in ranked if c["is_bm25_candidate"]]
        payload = build_reranker_payload(q, candidates)
        raw = await rerank_call(
            rerank_payload=payload,
            system_prompt=get_cat4_haiku_reranker_system_prompt(),
            schema=RERANK_JSON_SCHEMA,
            api_key=api_key,
            max_tokens=RERANK_MAX_TOKENS,
            timeout_s=RERANK_TIMEOUT_S,
            max_retries=max_retries,
        )
        calls.append(_call_record("rerank", raw, max_tokens=RERANK_MAX_TOKENS, timeout_s=RERANK_TIMEOUT_S, cached=False))
        selected, _funnel, bm25_recall, rerank_recall = merge_rerank_funnel(
            bm25_ranked=ranked, reranker_structured=raw.structured, expected_chunk_ids=expected, top_k_rerank=RERANK_TOP_K
        )
        valid_picks = [str(e.get("chunk_id") or "").strip() for e in (raw.structured or {}).get("selected_chunks") or []]
        cand_ids = {c["chunk_id"] for c in candidates}
        rank_of = {c["chunk_id"]: c["bm25_rank"] for c in ranked}
        retrieval = {
            "bm25_top": [{"chunk_id": c["chunk_id"], "rank": c["bm25_rank"], "score": c["bm25_score"],
                          "supplier": corpus.supplier_of_chunk(c["chunk_id"])} for c in candidates],
            "expected_bm25_ranks": {cid: rank_of.get(cid) for cid in expected},
            "reranker_raw": raw.structured,
            "selected_chunk_ids": [c["chunk_id"] for c in selected],
            "backfilled_chunk_ids": [c["chunk_id"] for c in selected if c["chunk_id"] not in valid_picks],
            "invalid_picks": [p for p in valid_picks if p not in cand_ids],
            "recall_after_bm25": _recall(expected, cand_ids),
            "recall_after_rerank": _recall(expected, [c["chunk_id"] for c in selected]),
            "app_recall_pct": {"bm25": bm25_recall, "rerank": rerank_recall},
        }
        doc_blocks = build_rung3_chunk_blocks(selected)
        sent = {"mode": "chunks", "chunk_ids": [c["chunk_id"] for c in selected]}
    elif rung_id == NEW_RUNG:
        raw = await rerank_call(
            rerank_payload="",
            system_prompt=get_full_corpus_reranker_system_prompt(),
            schema=RERANK_JSON_SCHEMA,
            api_key=api_key,
            max_tokens=RERANK_MAX_TOKENS,
            timeout_s=RERANK_TIMEOUT_S,
            max_retries=max_retries,
            user_content=build_full_corpus_rerank_content(corpus, q, nonce),
        )
        calls.append(_call_record("rerank", raw, max_tokens=RERANK_MAX_TOKENS, timeout_s=RERANK_TIMEOUT_S, cached=True))
        selected, invalid = select_full_corpus_chunks(corpus, raw.structured)
        retrieval = {
            "reranker_raw": raw.structured,
            "selected_chunk_ids": [c["chunk_id"] for c in selected],
            "backfilled_chunk_ids": [],
            "invalid_picks": invalid,
            "recall_after_rerank": _recall(expected, [c["chunk_id"] for c in selected]),
            "shortfall": RERANK_TOP_K - len(selected),
        }
        doc_blocks = build_rung3_chunk_blocks(selected)
        sent = {"mode": "chunks", "chunk_ids": [c["chunk_id"] for c in selected]}
    else:
        raise ValueError(f"unknown rung {rung_id}")

    synth = await synth_call(
        system_prompt=get_cat4_synthesis_system_prompt(with_citations=doc_blocks is not None),
        user_question=q,
        documents_for_blocks=doc_blocks,
        uncached_corpus_text=uncached_text,
        use_prefix_cache=use_cache,
        api_key=api_key,
        max_tokens=SYNTH_MAX_TOKENS,
        timeout_s=SYNTH_TIMEOUT_S,
        max_retries=max_retries,
        raise_on_max_tokens=False,
    )
    calls.append(_call_record("synthesis", synth, max_tokens=SYNTH_MAX_TOKENS, timeout_s=SYNTH_TIMEOUT_S, cached=use_cache))
    structured = synth.structured or {}
    return {
        "status": "ok",
        "question_as_asked": q,
        "answer_markdown": synth.raw_text,
        "segments": structured.get("segments") or [],
        "citations": resolve_citations(corpus, structured.get("citations") or []),
        "chunks_sent": sent,
        "retrieval": retrieval,
        "calls": calls,
    }


def corpus_fingerprint(corpus: ScaledCorpus) -> str:
    h = hashlib.sha256()
    for d in corpus.hydrated_docs:
        h.update(d["doc_id"].encode())
        h.update(d["full_text"].encode("utf-8"))
    return h.hexdigest()[:16]


async def execute_session(
    *,
    rung_id: str,
    scale: int,
    repeat_index: int,
    api_key: str,
    synth_call: SynthCall | None = None,
    rerank_call: RerankCall | None = None,
    max_retries: int | None = DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    """One session (8 questions, sequential); never raises. Stops at the first failed question."""
    if synth_call is None or rerank_call is None:
        from app.core.anthropic_service import run_cat4_haiku_reranker, run_cat4_rag_synthesis

        synth_call = synth_call or run_cat4_rag_synthesis
        rerank_call = rerank_call or run_cat4_haiku_reranker
    corpus = build_scaled_corpus(scale)
    nonce = uuid4().hex
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": str(uuid4()),
        "rung_id": rung_id,
        "scale": scale,
        "repeat_index": repeat_index,
        "session_nonce": nonce,
        "started_at": _utc_now_iso(),
        "status": "ok",
        "error_message": None,
        "corpus": {**corpus_size(corpus), "fingerprint": corpus_fingerprint(corpus), "document_order": DOCUMENT_ORDER},
        "settings": {"synth_max_tokens": SYNTH_MAX_TOKENS, "rerank_max_tokens": RERANK_MAX_TOKENS,
                     "synth_timeout_s": SYNTH_TIMEOUT_S, "rerank_timeout_s": RERANK_TIMEOUT_S,
                     "max_retries": max_retries, "bm25_top_k": BM25_TOP_K, "rerank_top_k": RERANK_TOP_K,
                     "question_scope_line": scope_line()},
        "answers": [],
    }
    t0 = time.perf_counter()
    for q_index, (preset_id, q_spec) in enumerate(session_questions()):
        base = {"q_index": q_index, "preset_id": preset_id, "question_id": q_spec["question_id"],
                "question": q_spec["question"], "question_as_asked": scoped_question(str(q_spec["question"])),
                "expected_chunk_ids": list(q_spec.get("expected_chunk_ids") or [])}
        try:
            ans = await run_question(rung_id=rung_id, corpus=corpus, q_spec=q_spec, nonce=nonce, api_key=api_key,
                                     synth_call=synth_call, rerank_call=rerank_call, max_retries=max_retries)
            record["answers"].append({**base, **ans})
        except Exception as exc:  # noqa: BLE001 — recorded, never raised
            record["answers"].append({**base, "status": "error", "error_message": f"{type(exc).__name__}: {exc}"[:1000],
                                      "calls": []})
            record["status"] = "error"
            record["error_message"] = f"q{q_index + 1} ({preset_id}/{q_spec['question_id']}): {type(exc).__name__}: {exc}"[:1000]
            break
    record["finished_at"] = _utc_now_iso()
    record["wall_s"] = round(time.perf_counter() - t0, 3)
    return record


RunKey = tuple[str, int, int]  # (rung, scale, repeat)


def record_key(record: dict[str, Any]) -> RunKey:
    return (str(record["rung_id"]), int(record["scale"]), int(record["repeat_index"]))


def plan_matrix(rungs: Sequence[str], scales: Sequence[int], repeats: int) -> list[RunKey]:
    """Ordered by repeat, then scale, then rung."""
    return [(r, s, i) for i in range(repeats) for s in scales for r in rungs]


def is_current_settings(record: dict[str, Any]) -> bool:
    """False for a session recorded at a different synthesis output cap than SYNTH_MAX_TOKENS (or with no settings)."""
    return (record.get("settings") or {}).get("synth_max_tokens") == SYNTH_MAX_TOKENS


def superseded_sessions(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"rung_id": r.get("rung_id"), "scale": r.get("scale"), "repeat_index": r.get("repeat_index"), "run_id": r.get("run_id"),
             "status": r.get("status"), "synth_max_tokens": (r.get("settings") or {}).get("synth_max_tokens"),
             "current_synth_max_tokens": SYNTH_MAX_TOKENS}
            for r in records if not is_current_settings(r)]


def select_pending(planned: Iterable[RunKey], existing: Iterable[dict[str, Any]]) -> list[RunKey]:
    """A key is done only with an ok record at the current settings; superseded records leave it pending."""
    done = {record_key(r) for r in existing if r.get("status") == "ok" and is_current_settings(r)}
    return [k for k in planned if k not in done]


def latest_ok_sessions(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Latest ok record per key at the current settings (superseded sessions are never used)."""
    latest: dict[RunKey, dict[str, Any]] = {}
    for r in records:
        if r.get("status") == "ok" and is_current_settings(r):
            latest[record_key(r)] = r
    return [latest[k] for k in sorted(latest, key=lambda k: (RUNG_IDS.index(k[0]) if k[0] in RUNG_IDS else 99, k[1], k[2]))]


def load_jsonl(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


# --------------------------------------------------------------------------------------------------
# Cost (from tokens; three views)
# --------------------------------------------------------------------------------------------------


def _finops(model_id: str, intended: str, inp: int, out: int, cw: int, cr: int):
    mid = model_id if model_id in MODEL_RATES else intended
    return compute_run_finops(model_id=mid, input_tokens=inp, output_tokens=out, cache_creation_tokens=cw, cache_read_tokens=cr)


def call_cost_usd(call: dict[str, Any], *, view: str = "billed", first_question: bool = False) -> float:
    """billed: as recorded. cold: a cache_control call writes its whole prefix on the session's first question and
    reads it after. warm: every cached-prefix token is a read. Calls without cache_control are the same in all views."""
    inp, out = int(call.get("input_tokens") or 0), int(call.get("output_tokens") or 0)
    cw, cr = int(call.get("cache_creation_tokens") or 0), int(call.get("cache_read_tokens") or 0)
    if view != "billed" and call.get("cache_control"):
        prefix = cw + cr
        cw, cr = (prefix, 0) if (view == "cold" and first_question) else (0, prefix)
    return _finops(str(call.get("model_id") or ""), str(call.get("intended_model_id") or SONNET_MODEL_ID), inp, out, cw, cr).total_cost_usd


def answer_cost(answer: dict[str, Any], *, view: str = "billed") -> dict[str, float]:
    first = int(answer.get("q_index") or 0) == 0
    by = {"sonnet": 0.0, "haiku": 0.0}
    for c in answer.get("calls") or []:
        k = "haiku" if c.get("role") == "rerank" else "sonnet"
        by[k] += call_cost_usd(c, view=view, first_question=first)
    by["total"] = by["sonnet"] + by["haiku"]
    return by


def session_billed_usd(record: dict[str, Any]) -> float:
    return sum(answer_cost(a)["total"] for a in record.get("answers") or [])


def prompt_tokens(call: dict[str, Any]) -> int:
    return int(call.get("input_tokens") or 0) + int(call.get("cache_creation_tokens") or 0) + int(call.get("cache_read_tokens") or 0)


def cache_write_premium_usd(answer: dict[str, Any]) -> float:
    """One-off premium of writing the cached prefix: prefix tokens x (write - read) rate of the cached call's model."""
    total = 0.0
    for c in answer.get("calls") or []:
        if not c.get("cache_control"):
            continue
        prefix = int(c.get("cache_creation_tokens") or 0) + int(c.get("cache_read_tokens") or 0)
        mid = c.get("model_id") if c.get("model_id") in MODEL_RATES else c.get("intended_model_id")
        rate = MODEL_RATES[mid]
        total += prefix * (rate.cache_write_per_1m_usd - rate.cache_read_per_1m_usd) / 1e6
    return total


def break_even_questions(premium_a: float, per_q_a: float, premium_b: float, per_q_b: float) -> dict[str, Any]:
    """Questions sharing one cache write at which A (cost P_a + N·c_a) becomes cheaper than B (P_b + N·c_b)."""
    inputs = {"premium_a_usd": premium_a, "per_question_a_usd": per_q_a, "premium_b_usd": premium_b, "per_question_b_usd": per_q_b}
    if per_q_a < per_q_b:
        n = (premium_a - premium_b) / (per_q_b - per_q_a)
        if n < 1:
            return {**inputs, "n_star": n, "verdict": "A cheaper from question 1", "questions": 1}
        return {**inputs, "n_star": n, "verdict": f"A cheaper from question {math.floor(n) + 1}", "questions": math.floor(n) + 1}
    if premium_a <= premium_b and per_q_a == per_q_b:
        return {**inputs, "n_star": None, "verdict": "A never more expensive", "questions": 1}
    if premium_a < premium_b:
        n = (premium_b - premium_a) / (per_q_a - per_q_b)
        return {**inputs, "n_star": n, "verdict": f"A cheaper only below {n:.1f} questions", "questions": None}
    return {**inputs, "n_star": None, "verdict": "A never cheaper", "questions": None}


# --------------------------------------------------------------------------------------------------
# Deterministic scoring (per answer)
# --------------------------------------------------------------------------------------------------


def _fact_supported_by_citations(fact: dict[str, Any], citations: Sequence[dict[str, Any]]) -> bool:
    alts = fact_alternatives(fact)
    return any(text_matches(c.get("cited_text"), alts) for c in citations)


ATTRIBUTION_WINDOW_CHARS = 150


def _value_span(text: str, value: str) -> tuple[int, int] | None:
    """Raw-text span of a value the normalised matcher found (tolerates markdown, commas, spacing, case)."""
    parts = [re.escape(ch) for ch in normalise_text(value).replace(",", "")]
    gap = r"[\s,*_`₹]*"
    rx = gap.join(p if p != r"\ " else r"\s+" for p in parts)
    m = re.search(rx, text, re.I) or re.search(re.escape(value), text, re.I)
    return (m.start(), m.end()) if m else None


def answer_excerpt(text: str, value: str, width: int = 120) -> str | None:
    span = _value_span(text, value)
    return text[max(0, span[0] - width):span[1] + width] if span else None


def _names_distractor(window: str, supplier: str) -> bool:
    spec = SUPPLIERS[supplier]
    lo = window.lower()
    if spec.short_name.lower() in lo or spec.legal_name.lower() in lo:
        return True
    ids = {f"DOC-{i + spec.doc_id_offset:02d}" for i in range(1, 8)}
    return any(i in window for i in ids)


def distractor_value_hit(fact_id: str, supplier: str, value: str, text: str = "") -> dict[str, Any]:
    """The one shape of a `contamination.distractor_values` entry (produced by score_answer, read by the review).

    `attributed_to_distractor`: the other supplier's name or one of its document ids appears within
    ATTRIBUTION_WINDOW_CHARS of the value — typically an answer saying it is excluding that supplier's figure.
    It is reported alongside, not subtracted from, the contamination count."""
    span = _value_span(text, value) if text else None
    window = text[max(0, span[0] - ATTRIBUTION_WINDOW_CHARS):span[1] + ATTRIBUTION_WINDOW_CHARS] if span else ""
    return {"fact_id": fact_id, "supplier": supplier, "value": value,
            "attributed_to_distractor": bool(window) and _names_distractor(window, supplier)}


def score_answer(
    answer: dict[str, Any],
    *,
    rung_id: str,
    corpus: ScaledCorpus,
    keys: dict[str, Any],
    contamination: dict[str, dict[str, list[str]]] | None = None,
) -> dict[str, Any]:
    """Every deterministic measure for one answer. Citation measures are None for the naive rung (not requested)."""
    preset_id, qid = answer["preset_id"], answer["question_id"]
    facts = facts_for(keys, preset_id, qid)
    text = str(answer.get("answer_markdown") or "")
    nt = normalise_text(text)
    citations = list(answer.get("citations") or [])
    cited_chunks = [c.get("chunk_id") for c in citations if c.get("chunk_id")]
    expected = list(answer.get("expected_chunk_ids") or [])

    fact_rows = []
    for f in facts:
        hit = any(contains_alternative(nt, a) for a in fact_alternatives(f))
        fact_rows.append({"fact_id": f["id"], "hit": hit, "supplier_specific": bool(f["supplier_specific"]),
                          "category": f["category"],
                          "cited_support": (_fact_supported_by_citations(f, citations) if hit and rung_id in CITATION_RUNGS else None)})

    def cnt(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
        return {"hits": sum(1 for r in rows if r["hit"]), "total": len(rows)}

    out: dict[str, Any] = {
        "preset_id": preset_id,
        "question_id": qid,
        "facts": fact_rows,
        "fact_recall": cnt(fact_rows),
        "fact_recall_supplier_specific": cnt([r for r in fact_rows if r["supplier_specific"]]),
        "fact_recall_non_specific": cnt([r for r in fact_rows if not r["supplier_specific"]]),
        "fact_recall_statutory": cnt([r for r in fact_rows if r["category"] == "statutory"]),
        "answer_chars": len(text),
        "citations_requested": rung_id in CITATION_RUNGS,
    }
    if rung_id in CITATION_RUNGS:
        hits = [r for r in fact_rows if r["hit"]]
        out.update({
            "citation_count": len(citations),
            "zero_citations": len(citations) == 0,
            "expected_chunk_recall": {"hits": len(set(expected) & set(cited_chunks)), "total": len(set(expected))},
            "citations_at_expected": {"hits": sum(1 for c in cited_chunks if c in expected), "total": len(citations)},
            "citations_at_deccan": {"hits": sum(1 for c in citations if c.get("supplier") == BASE_SUPPLIER), "total": len(citations)},
            "citations_at_distractor": {"hits": sum(1 for c in citations if c.get("supplier") in DISTRACTOR_SUPPLIERS), "total": len(citations)},
            "cited_support": {"hits": sum(1 for r in hits if r["cited_support"]), "total": len(hits)},
        })
    else:
        out.update({"citation_count": None, "zero_citations": None, "expected_chunk_recall": None,
                    "citations_at_expected": None, "citations_at_deccan": None, "citations_at_distractor": None,
                    "cited_support": None})

    # contamination (meaningful at scale 3; at scale 1 no distractor exists)
    value_hits = []
    if corpus.scale > 1 and contamination:
        for f in facts:
            for s, vals in (contamination.get(f["id"]) or {}).items():
                for v in vals:
                    if contains_alternative(nt, v):
                        value_hits.append(distractor_value_hit(f["id"], s, v, text))
    distractor_cited = sorted({c["chunk_id"] for c in citations if c.get("supplier") in DISTRACTOR_SUPPLIERS})
    sent_ids = ((answer.get("chunks_sent") or {}).get("chunk_ids")) or []
    distractor_sent = [c for c in sent_ids if corpus.supplier_of_chunk(c) in DISTRACTOR_SUPPLIERS]
    out["contamination"] = {
        "distractor_values": value_hits,
        "distractor_chunks_cited": distractor_cited,
        "distractor_chunks_sent": distractor_sent,
        # exposure, not contamination: the synthesis prompt contained distractor text (full corpus at scale > 1, or
        # >= 1 distractor chunk selected)
        "synthesis_saw_distractor_text": bool(distractor_sent) or ((answer.get("chunks_sent") or {}).get("mode") == "full_corpus" and corpus.scale > 1),
        "contaminated": bool(value_hits or distractor_cited),
    }
    # retrieval (rungs 3, 4)
    ret = answer.get("retrieval")
    if rung_id in RETRIEVAL_RUNGS and ret:
        sel = ret.get("selected_chunk_ids") or []
        out["retrieval"] = {
            "recall_after_bm25": ret.get("recall_after_bm25"),
            "recall_after_rerank": ret.get("recall_after_rerank") or _recall(expected, sel),
            "selected": len(sel),
            "distractors_selected": sum(1 for c in sel if corpus.supplier_of_chunk(c) in DISTRACTOR_SUPPLIERS),
            "backfilled": len(ret.get("backfilled_chunk_ids") or []),
            "invalid_picks": len(ret.get("invalid_picks") or []),
        }
    else:
        out["retrieval"] = None
    return out


# --------------------------------------------------------------------------------------------------
# Golden replays as the "original capture" group (scale 1, n = 1 per rung x question)
# --------------------------------------------------------------------------------------------------


def golden_answers(golden: dict[str, Any]) -> list[dict[str, Any]]:
    """The 24 golden answers in the rerun answer shape (citations resolved to chunks; calls rebuilt from tokens)."""
    corpus = build_scaled_corpus(1)
    q_specs = {(p["id"], q["question_id"]): q for p in CAT4_PRESETS for q in p["questions"]}
    out = []
    for pid, pdata in (golden.get("presets") or {}).items():
        for rung_id, qs in (pdata.get("rungs") or {}).items():
            for i, rq in enumerate(qs):
                spec = q_specs.get((pid, rq["question_id"])) or {}
                calls = []
                if int(rq.get("reranker_input_tokens") or 0) > 0:
                    calls.append({"role": "rerank", "model_id": rq.get("reranker_model_id") or HAIKU_MODEL_ID,
                                  "intended_model_id": HAIKU_MODEL_ID, "stop_reason": None,
                                  "input_tokens": int(rq["reranker_input_tokens"]), "output_tokens": int(rq.get("reranker_output_tokens") or 0),
                                  "cache_creation_tokens": 0, "cache_read_tokens": 0, "thinking_tokens": 0, "cache_control": False})
                calls.append({"role": "synthesis", "model_id": rq.get("model_id") or SONNET_MODEL_ID, "intended_model_id": SONNET_MODEL_ID,
                              "stop_reason": rq.get("stop_reason"), "input_tokens": int(rq["input_tokens"]),
                              "output_tokens": int(rq["output_tokens"]), "cache_creation_tokens": int(rq.get("cache_creation_tokens") or 0),
                              "cache_read_tokens": int(rq.get("cache_read_tokens") or 0), "thinking_tokens": 0,
                              "cache_control": rung_id == "cached_full_corpus_citations"})
                funnel = rq.get("retrieval_funnel") or []
                retrieval = None
                if funnel:
                    expected = list(spec.get("expected_chunk_ids") or [])
                    cands = [f["chunk_id"] for f in funnel if f.get("stage") in ("selected_by_reranker", "pruned_by_reranker")]
                    sel = [f["chunk_id"] for f in funnel if f.get("stage") == "selected_by_reranker"]
                    retrieval = {"selected_chunk_ids": sel, "recall_after_bm25": _recall(expected, cands),
                                 "recall_after_rerank": _recall(expected, sel), "backfilled_chunk_ids": [], "invalid_picks": []}
                out.append({
                    "source": "golden", "rung_id": rung_id, "scale": 1, "repeat_index": 0, "q_index": i if pid == "audit-01" else 4 + i,
                    "preset_id": pid, "question_id": rq["question_id"], "question": rq["question"],
                    "expected_chunk_ids": list(spec.get("expected_chunk_ids") or []),
                    "status": "ok", "answer_markdown": rq["answer_markdown"], "segments": rq.get("segments") or [],
                    "citations": resolve_citations(corpus, rq.get("citations") or []),
                    "chunks_sent": {"mode": "chunks", "chunk_ids": sel} if funnel else {"mode": "full_corpus", "chunk_ids": None},
                    "retrieval": retrieval, "calls": calls,
                })
    return out


def load_golden(path: Path | str | None = None) -> dict[str, Any]:
    p = Path(path or GOLDEN_PATH)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"presets": {}}


# --------------------------------------------------------------------------------------------------
# Rerun budget guard + estimates
# --------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CharsPerToken:
    plain: float = 2.1  # naive synthesis: system + plain corpus + question
    doc_blocks: float = 1.8  # document blocks (citations add per-block overhead)
    rerank: float = 2.2


def calibrate_chars_per_token(golden: dict[str, Any]) -> CharsPerToken:
    """From the golden capture: prompt chars / recorded prompt tokens per call type (scale 1)."""
    corpus = build_scaled_corpus(1)
    plain_chars = len(build_uncached_corpus_text(corpus.hydrated_docs))
    block_chars = sum(len(b["data"]) + len(b["block_title"]) + len(b["block_context"]) for b in build_rung2_doc_blocks(corpus.hydrated_docs))
    sys_plain = len(get_cat4_synthesis_system_prompt(with_citations=False))
    sys_cite = len(get_cat4_synthesis_system_prompt(with_citations=True))
    plain, blocks, rerank = [], [], []
    for pdata in (golden.get("presets") or {}).values():
        for rq in (pdata.get("rungs") or {}).get("naive_full_corpus") or []:
            plain.append((plain_chars + sys_plain + len(rq["question"])) / max(1, int(rq["input_tokens"])))
        for rq in (pdata.get("rungs") or {}).get("cached_full_corpus_citations") or []:
            tok = int(rq["input_tokens"]) + int(rq.get("cache_creation_tokens") or 0) + int(rq.get("cache_read_tokens") or 0)
            blocks.append((block_chars + sys_cite + len(rq["question"])) / max(1, tok))
        for rq in (pdata.get("rungs") or {}).get("hybrid_rag_rerank_citations") or []:
            if rq.get("reranker_payload") and int(rq.get("reranker_input_tokens") or 0):
                rerank.append((len(rq["reranker_payload"]) + len(get_cat4_haiku_reranker_system_prompt())) / int(rq["reranker_input_tokens"]))
    d = CharsPerToken()
    return CharsPerToken(
        plain=statistics.fmean(plain) if plain else d.plain,
        doc_blocks=statistics.fmean(blocks) if blocks else d.doc_blocks,
        rerank=statistics.fmean(rerank) if rerank else d.rerank,
    )


def _rate(mid: str):
    return MODEL_RATES[mid]


def estimate_session(rung_id: str, scale: int, cpt: CharsPerToken, *, typical_out: dict[str, int] | None = None) -> dict[str, Any]:
    """Estimated prompt tokens and $ for one session (typical output and worst case = max_tokens)."""
    typical_out = typical_out or {"synthesis": 1050, "rerank": 450}
    corpus = build_scaled_corpus(scale)
    son, hai = _rate(SONNET_MODEL_ID), _rate(HAIKU_MODEL_ID)
    scope = len(scope_line()) + 2  # the golden calibration questions had no scope line
    plain_tok = (len(build_uncached_corpus_text(corpus.hydrated_docs)) + 1200 + scope) / cpt.plain
    block_tok = sum(len(b["data"]) + len(b["block_title"]) + len(b["block_context"]) for b in build_rung2_doc_blocks(corpus.hydrated_docs)) / cpt.doc_blocks
    chunk_tok = statistics.fmean(c["char_count"] for c in corpus.flat_chunks) * RERANK_TOP_K / cpt.doc_blocks + (1200 + scope) / cpt.doc_blocks
    rerank10_tok = (statistics.fmean(c["char_count"] for c in corpus.flat_chunks) * BM25_TOP_K + 900 + scope) / cpt.rerank
    rerank_full_tok = (len(format_full_corpus_for_reranker(corpus)) + 900) / cpt.rerank
    n = len(session_questions())
    calls: list[tuple[str, float, float, float, int]] = []  # (model, uncached, write, read, max_out)
    for i in range(n):
        if rung_id == "naive_full_corpus":
            calls.append((SONNET_MODEL_ID, plain_tok, 0, 0, SYNTH_MAX_TOKENS))
        elif rung_id == "cached_full_corpus_citations":
            calls.append((SONNET_MODEL_ID, 120 + scope / cpt.doc_blocks, block_tok if i == 0 else 0, 0 if i == 0 else block_tok, SYNTH_MAX_TOKENS))
        elif rung_id == "hybrid_rag_rerank_citations":
            calls.append((HAIKU_MODEL_ID, rerank10_tok, 0, 0, RERANK_MAX_TOKENS))
            calls.append((SONNET_MODEL_ID, chunk_tok, 0, 0, SYNTH_MAX_TOKENS))
        else:
            calls.append((HAIKU_MODEL_ID, 150 + scope / cpt.rerank, rerank_full_tok if i == 0 else 0, 0 if i == 0 else rerank_full_tok, RERANK_MAX_TOKENS))
            calls.append((SONNET_MODEL_ID, chunk_tok, 0, 0, SYNTH_MAX_TOKENS))

    def usd(out_of: Callable[[str, int], float]) -> float:
        tot = 0.0
        for mid, u, w, r, mx in calls:
            rt = son if mid == SONNET_MODEL_ID else hai
            tot += (u * rt.input_per_1m_usd + w * rt.cache_write_per_1m_usd + r * rt.cache_read_per_1m_usd + out_of(mid, mx) * rt.output_per_1m_usd) / 1e6
        return tot

    return {
        "prompt_tokens": round(sum(u + w + r for _, u, w, r, _ in calls)),
        "max_rerank_prompt_tokens": round(max([u + w + r for m, u, w, r, _ in calls if m == HAIKU_MODEL_ID], default=0)),
        "typical_usd": usd(lambda mid, mx: typical_out["synthesis" if mid == SONNET_MODEL_ID else "rerank"]),
        "worst_case_usd": usd(lambda mid, mx: mx),
    }


class BudgetGuard:
    """Billed spend of existing records (ok AND error) + reservations; refuse a session whose worst case would cross the cap."""

    def __init__(self, max_usd: float, existing: Iterable[dict[str, Any]] = ()) -> None:
        self.max_usd = float(max_usd)
        self.spent_usd = sum(session_billed_usd(r) for r in existing)
        self.reserved_usd = 0.0

    def try_reserve(self, worst_case_usd: float) -> bool:
        if self.spent_usd + self.reserved_usd + worst_case_usd > self.max_usd:
            return False
        self.reserved_usd += worst_case_usd
        return True

    def settle(self, reserved_usd: float, record: dict[str, Any]) -> float:
        cost = session_billed_usd(record)
        self.reserved_usd = max(0.0, self.reserved_usd - reserved_usd)
        self.spent_usd += cost
        return cost


async def run_sessions(
    pending: Sequence[RunKey],
    *,
    api_key: str,
    guard: BudgetGuard,
    worst_case_usd: Callable[[RunKey], float],
    on_record: Callable[[dict[str, Any]], None],
    concurrency: int = 3,
    synth_call: SynthCall | None = None,
    rerank_call: RerankCall | None = None,
    max_retries: int | None = DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    """Sessions concurrently (questions inside a session sequentially); stop launching at the budget cap."""
    sem = asyncio.Semaphore(max(1, concurrency))
    counts = {"ok": 0, "error": 0, "launched": 0, "skipped_budget": 0}
    budget_stopped = False
    tasks: list[asyncio.Task[None]] = []

    async def one(key: RunKey, reserved: float) -> None:
        try:
            rec = await execute_session(rung_id=key[0], scale=key[1], repeat_index=key[2], api_key=api_key,
                                        synth_call=synth_call, rerank_call=rerank_call, max_retries=max_retries)
            guard.settle(reserved, rec)
            counts["ok" if rec["status"] == "ok" else "error"] += 1
            on_record(rec)
        finally:
            sem.release()

    for i, key in enumerate(pending):
        await sem.acquire()
        worst = worst_case_usd(key)
        if not guard.try_reserve(worst):
            sem.release()
            budget_stopped = True
            counts["skipped_budget"] = len(pending) - i
            break
        counts["launched"] += 1
        tasks.append(asyncio.create_task(one(key, worst)))
    if tasks:
        await asyncio.gather(*tasks)
    return {**counts, "budget_stopped": budget_stopped, "spent_usd": guard.spent_usd}


# --------------------------------------------------------------------------------------------------
# Blind judge (Opus 5.5)
# --------------------------------------------------------------------------------------------------
# ASSUMPTION — LEAD MUST CONFIRM: Claude Opus 5.5 list price $4.00 / 1M input, $20.00 / 1M output, cache write
# $5.00, cache read $0.20 — the same constants as app/archetypes/cat2_drafting/quality_scoring.py (source: the
# bundled claude-api skill's model table, cached 2026-11-03); app/core/pricing.py has no Opus rate. Output tokens
# include adaptive-thinking tokens.

JUDGE_MODEL = "claude-opus-5-5"
OPUS_INPUT_PER_1M_USD = 4.00
OPUS_OUTPUT_PER_1M_USD = 20.00
OPUS_CACHE_WRITE_PER_1M_USD = 5.00
OPUS_CACHE_READ_PER_1M_USD = 0.20
JUDGE_MAX_TOKENS = 8000
JUDGE_TIMEOUT_S = 300.0
JUDGE_THINKING: dict[str, str] = {"type": "adaptive"}
JUDGE_EFFORT = "medium"
JUDGE_REPEATS = 1
JUDGE_CHARS_PER_TOKEN = 2.1
JUDGE_TYPICAL_OUTPUT_TOKENS = 2200

JUDGE_INSTRUCTIONS = """You are an exacting senior reviewer of supplier due-diligence work. The question you will be given concerns the supplier deal room of Deccan Smart Appliances & Energy Pvt. Ltd. Its seven documents follow these instructions; they are the complete and only ground truth. Judge the answer against these documents alone: do not use outside knowledge to fill gaps or to correct them.

Read the whole answer before scoring. Judge substance only: do not reward or penalise length, headings, bullets, or whether the answer names its sources. Correct arithmetic derived from figures in the documents (sums, differences, percentages, unit conversions such as Crore to rupees, reasonable roundings) is not an error; check it before reporting it. A figure, party, date or term that belongs to a different supplier or does not appear in these documents is an error.

correctness — does everything the answer states agree with the documents? Integer 1 to 5 (2 and 4 lie between the anchors) and a one-sentence justification.
  5: Every amount, percentage, date, duration, party, clause and obligation matches the documents, including which instrument overrides which; nothing is invented.
  3: Mostly correct, with a few minor misstatements or loose paraphrases that would not change a diligence decision.
  1: Material errors or invented terms (wrong amounts, caps, deadlines, parties, conditions or precedence) that would mislead a reviewer.

completeness — does it answer every part of the question with the specifics the documents provide? Integer 1 to 5 and a one-sentence justification.
  5: Every part of the question is answered with the specific figures, clauses, conditions and deadlines the documents give.
  3: The main parts are answered, but one or two requested specifics are missing or only implied.
  1: Most of what was asked is missing.

factual_errors — list every statement in the answer that contradicts the documents or is not supported by them. For each entry:
  - claim_quote: the exact words from the answer, copied verbatim. Quote, do not paraphrase. Use the shortest span that contains the problem.
  - problem: one sentence saying what is wrong.
  - source_quote_or_absent: the exact words from the documents that the claim conflicts with, copied verbatim; or the single word ABSENT if nothing in the documents supports the claim.
  - severity: "material" if it misstates an amount, percentage, date, duration, party, cap, condition, obligation or which document prevails; otherwise "minor".
Return an empty list if there are no errors.

answers_the_question — "yes", "partly" or "no".

Return only the JSON object required by the response schema."""

JUDGE_USER_TEMPLATE = """<question>
{question}
</question>

<answer>
{answer}
</answer>

Evaluate the answer as instructed and return the JSON object."""


def _judge_score_obj() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"score": {"type": "integer", "enum": [1, 2, 3, 4, 5]}, "justification": {"type": "string"}},
        "required": ["score", "justification"],
        "additionalProperties": False,
    }


JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "correctness": _judge_score_obj(),
        "completeness": _judge_score_obj(),
        "factual_errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_quote": {"type": "string"},
                    "problem": {"type": "string"},
                    "source_quote_or_absent": {"type": "string"},
                    "severity": {"type": "string", "enum": ["minor", "material"]},
                },
                "required": ["claim_quote", "problem", "source_quote_or_absent", "severity"],
                "additionalProperties": False,
            },
        },
        "answers_the_question": {"type": "string", "enum": ["yes", "partly", "no"]},
    },
    "required": ["correctness", "completeness", "factual_errors", "answers_the_question"],
    "additionalProperties": False,
}

_MARKER_RES = (
    re.compile(r"\[\^?\d+(?:\s*[,;–-]\s*\^?\d+)*\]"),
    re.compile(r"【[^】]*】"),
    re.compile(r"<cite[^>]*>|</cite>", re.I),
)
_SOURCES_TAIL_RE = re.compile(r"\n\s*(?:#+\s*)?(?:\*\*)?(?:sources|citations|references)\s*:?\s*(?:\*\*)?\s*:?\s*\n.*\Z", re.I | re.S)


def strip_citation_markup(text: str) -> str:
    """Remove citation markers and any trailing Sources/Citations block, so format does not reveal the rung."""
    t = _SOURCES_TAIL_RE.sub("", text or "")
    for rx in _MARKER_RES:
        t = rx.sub("", t)
    t = re.sub(r"[ \t]+([.,;:])", r"\1", t)
    return re.sub(r"(?<=\S)[ \t]{2,}", " ", t).strip()  # keeps markdown list indentation


@lru_cache(maxsize=1)
def judge_documents_text() -> str:
    """Deccan's seven documents only (scale 1), as the cached prefix."""
    docs = build_scaled_corpus(1).hydrated_docs
    return "\n\n".join(
        f'<document index="{i + 1}" title="{d["block_title"]}" effective="{d["effective_date"]}">\n{d["full_text"]}\n</document>'
        for i, d in enumerate(docs)
    )


def build_judge_prompt(question: str, answer_text: str) -> tuple[list[dict[str, Any]], str]:
    system = [
        {"type": "text", "text": JUDGE_INSTRUCTIONS},
        {"type": "text", "text": "<deal_room_documents>\n" + judge_documents_text() + "\n</deal_room_documents>",
         "cache_control": {"type": "ephemeral"}},
    ]
    return system, JUDGE_USER_TEMPLATE.format(question=question.strip(), answer=strip_citation_markup(answer_text))


BLINDING_FORBIDDEN: tuple[str, ...] = (
    "claude", "sonnet", "haiku", "opus", "anthropic", "rung", "token", "cost", "price", "usd", "model",
    "cache", "cached", "naive", "hybrid", "rerank", "bm25", "scale", "distractor", "kaveri", "narmada", "corpus",
    "golden", "replay", "session", "repeat", *RUNG_IDS,
)


def blinding_violations(system: Sequence[dict[str, Any]], user: str, embedded_texts: Sequence[str]) -> list[str]:
    """Forbidden terms in what WE add to the prompt (Deccan's documents, the question and the answer are cut out first)."""
    rest = "\n".join(b["text"] for b in system) + "\n" + user
    texts = [judge_documents_text(), *embedded_texts]
    for t in sorted((t.strip() for t in texts if t and t.strip()), key=len, reverse=True):
        rest = rest.replace(t, "")
    low = rest.lower()
    return [w for w in BLINDING_FORBIDDEN if re.search(rf"(?<![a-z]){re.escape(w.lower())}(?![a-z])", low)]


def _sha(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def judge_items(scope: str, *, golden: dict[str, Any] | None = None, records: Sequence[dict[str, Any]] = ()) -> list[dict[str, Any]]:
    """Answers to judge: golden (24), rerun (every answer of the latest ok sessions), or all."""
    items: list[dict[str, Any]] = []
    if scope in ("golden", "all"):
        for a in golden_answers(golden or load_golden()):
            items.append({**a, "source": "golden"})
    if scope in ("rerun", "all"):
        for r in latest_ok_sessions(records):
            for a in r.get("answers") or []:
                if a.get("status") == "ok":
                    items.append({**a, "source": "rerun", "rung_id": r["rung_id"], "scale": r["scale"],
                                  "repeat_index": r["repeat_index"], "run_id": r["run_id"]})
    return items


def judge_question(item: dict[str, Any]) -> str:
    """What the answer was actually asked: the scoped question for rerun answers, the original for golden ones."""
    if item.get("source") == "rerun":
        return str(item.get("question_as_asked") or scoped_question(item["question"]))
    return str(item["question"])


def judge_call_id(item: dict[str, Any], judge_repeat: int) -> str:
    return (f"judge:{item['source']}:{item['rung_id']}:s{item['scale']}:r{item['repeat_index']}:"
            f"{item['preset_id']}:{item['question_id']}:j{judge_repeat}")


def plan_judge_calls(items: Sequence[dict[str, Any]], *, repeats: int = JUDGE_REPEATS) -> list[dict[str, Any]]:
    plan = []
    for it in items:
        question = judge_question(it)
        system, user = build_judge_prompt(question, it.get("answer_markdown") or "")
        for j in range(repeats):
            plan.append({
                "call_id": judge_call_id(it, j), "judge_repeat": j, "source": it["source"], "rung_id": it["rung_id"],
                "scale": it["scale"], "repeat_index": it["repeat_index"], "preset_id": it["preset_id"],
                "question_id": it["question_id"], "run_id": it.get("run_id"),
                "answer_sha256": _sha(it.get("answer_markdown") or ""),
                "prompt_sha256": _sha(*(b["text"] for b in system), user),
                "system": system, "user": user, "question": question,
                "answer_for_judge": strip_citation_markup(it.get("answer_markdown") or ""),
            })
    return plan


def select_pending_judgements(planned: Iterable[dict[str, Any]], existing: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    done = {(r["call_id"], r.get("answer_sha256")) for r in existing if r.get("status") == "ok"}
    return [p for p in planned if (p["call_id"], p["answer_sha256"]) not in done]


def judge_cost_usd(input_tokens: int, output_tokens: int, cache_creation_tokens: int = 0, cache_read_tokens: int = 0) -> float:
    return (input_tokens * OPUS_INPUT_PER_1M_USD + output_tokens * OPUS_OUTPUT_PER_1M_USD
            + cache_creation_tokens * OPUS_CACHE_WRITE_PER_1M_USD + cache_read_tokens * OPUS_CACHE_READ_PER_1M_USD) / 1e6


def judgement_cost_usd(rec: dict[str, Any]) -> float:
    return judge_cost_usd(int(rec.get("input_tokens") or 0), int(rec.get("output_tokens") or 0),
                          int(rec.get("cache_creation_tokens") or 0), int(rec.get("cache_read_tokens") or 0))


def estimate_judge_tokens(planned: dict[str, Any], cpt: float = JUDGE_CHARS_PER_TOKEN) -> dict[str, int]:
    prefix = sum(len(b["text"]) for b in planned["system"]) + len(json.dumps(JUDGE_SCHEMA))
    return {"prefix": int(math.ceil(prefix / cpt)), "user": int(math.ceil(len(planned["user"]) / cpt))}


def estimate_judge_plan(plan: Sequence[dict[str, Any]], *, cpt: float = JUDGE_CHARS_PER_TOKEN) -> dict[str, Any]:
    """First call writes the cached documents prefix; the rest read it (worst case: every call writes it)."""
    if not plan:
        return {"calls": 0, "typical_usd": 0.0, "worst_case_usd": 0.0}
    est = [estimate_judge_tokens(p, cpt) for p in plan]
    user_tok = sum(e["user"] for e in est)
    prefix = est[0]["prefix"]
    typical = judge_cost_usd(user_tok, JUDGE_TYPICAL_OUTPUT_TOKENS * len(plan), prefix, prefix * (len(plan) - 1))
    worst = judge_cost_usd(user_tok, JUDGE_MAX_TOKENS * len(plan), prefix * len(plan), 0)
    return {"calls": len(plan), "prefix_tokens_est": prefix, "user_tokens_est": user_tok, "chars_per_token": cpt,
            "typical_output_tokens_per_call": JUDGE_TYPICAL_OUTPUT_TOKENS, "max_tokens": JUDGE_MAX_TOKENS,
            "typical_usd": typical, "worst_case_usd": worst}


@dataclass
class JudgeResponse:
    model_id: str
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    thinking_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    latency_ms: int
    raw_text: str
    request_id: str | None = None


JudgeCall = Callable[..., Awaitable[JudgeResponse]]


def make_anthropic_judge_call(api_key: str, *, timeout_s: float = JUDGE_TIMEOUT_S, model: str = JUDGE_MODEL,
                              effort: str | None = JUDGE_EFFORT) -> JudgeCall:
    """Real judge call: one client, explicit timeout, max_retries=0 (nothing silently re-billed)."""
    import anthropic

    from app.core.anthropic_service import _extract_usage_tokens

    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_s, max_retries=0)

    async def call(*, system: list[dict[str, Any]], user: str, schema: dict[str, Any], max_tokens: int) -> JudgeResponse:
        output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": schema}}
        if effort:
            output_config["effort"] = effort
        t0 = time.perf_counter()
        resp = await client.messages.create(
            model=model, max_tokens=max_tokens, thinking=dict(JUDGE_THINKING), output_config=output_config,
            system=system, messages=[{"role": "user", "content": user}],
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        in_tok, out_tok, c_write, c_read, think_tok = _extract_usage_tokens(resp.usage)
        raw = "\n".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        return JudgeResponse(model_id=str(getattr(resp, "model", model)), stop_reason=getattr(resp, "stop_reason", None),
                             input_tokens=in_tok, output_tokens=out_tok, thinking_tokens=think_tok,
                             cache_creation_tokens=c_write, cache_read_tokens=c_read, latency_ms=latency_ms,
                             raw_text=raw, request_id=getattr(resp, "_request_id", None))

    return call


class JudgeOutputError(ValueError):
    def __init__(self, error_type: str, message: str) -> None:
        super().__init__(message)
        self.error_type = error_type


def parse_judge_output(raw_text: str) -> dict[str, Any]:
    import jsonschema

    try:
        obj = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise JudgeOutputError("invalid_json", str(exc)) from exc
    try:
        jsonschema.validate(obj, JUDGE_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise JudgeOutputError("schema_violation", exc.message[:500]) from exc
    return obj


async def execute_judge_call(planned: dict[str, Any], *, judge_call: JudgeCall, max_tokens: int = JUDGE_MAX_TOKENS) -> dict[str, Any]:
    """One judge call -> one record. Never raises."""
    rec: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        **{k: planned[k] for k in ("call_id", "judge_repeat", "source", "rung_id", "scale", "repeat_index",
                                   "preset_id", "question_id", "run_id", "answer_sha256", "prompt_sha256")},
        "status": "error", "error_type": None, "error_message": None, "judge_model_requested": JUDGE_MODEL,
        "settings": {"max_tokens": max_tokens, "thinking": dict(JUDGE_THINKING), "effort": JUDGE_EFFORT,
                     "timeout_s": JUDGE_TIMEOUT_S, "max_retries": 0},
        "model_id": None, "stop_reason": None, "input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0,
        "cache_creation_tokens": 0, "cache_read_tokens": 0, "latency_ms": None, "request_id": None,
        "raw_text": None, "parsed": None, "started_at": _utc_now_iso(),
    }
    try:
        resp = await judge_call(system=planned["system"], user=planned["user"], schema=JUDGE_SCHEMA, max_tokens=max_tokens)
    except Exception as exc:  # noqa: BLE001
        rec.update({"error_type": "api_error", "error_message": f"{type(exc).__name__}: {exc}"[:2000], "finished_at": _utc_now_iso()})
        return rec
    rec.update({"model_id": resp.model_id, "stop_reason": resp.stop_reason, "input_tokens": int(resp.input_tokens),
                "output_tokens": int(resp.output_tokens), "thinking_tokens": int(resp.thinking_tokens or 0),
                "cache_creation_tokens": int(resp.cache_creation_tokens or 0), "cache_read_tokens": int(resp.cache_read_tokens or 0),
                "latency_ms": int(resp.latency_ms), "request_id": resp.request_id, "raw_text": resp.raw_text})
    try:
        if resp.stop_reason != "end_turn":
            raise JudgeOutputError("stop_reason", f"stop_reason={resp.stop_reason}")
        rec["parsed"] = parse_judge_output(resp.raw_text)
        rec["status"] = "ok"
    except JudgeOutputError as exc:
        rec["error_type"], rec["error_message"] = exc.error_type, str(exc)[:2000]
    rec["finished_at"] = _utc_now_iso()
    return rec


class JudgeBudgetGuard:
    def __init__(self, max_usd: float, existing: Iterable[dict[str, Any]] = ()) -> None:
        self.max_usd = float(max_usd)
        self.spent_usd = sum(judgement_cost_usd(r) for r in existing)
        self.reserved_usd = 0.0

    def try_reserve(self, worst: float) -> bool:
        if self.spent_usd + self.reserved_usd + worst > self.max_usd:
            return False
        self.reserved_usd += worst
        return True

    def settle(self, reserved: float, rec: dict[str, Any]) -> float:
        cost = judgement_cost_usd(rec)
        self.reserved_usd = max(0.0, self.reserved_usd - reserved)
        self.spent_usd += cost
        return cost


async def run_judge_plan(
    pending: Sequence[dict[str, Any]],
    *,
    judge_call: JudgeCall,
    guard: JudgeBudgetGuard,
    on_record: Callable[[dict[str, Any]], None],
    concurrency: int = 4,
    max_tokens: int = JUDGE_MAX_TOKENS,
) -> dict[str, Any]:
    """The first call runs alone (it writes the cached documents prefix); the rest then fan out."""
    counts = {"ok": 0, "error": 0, "launched": 0, "skipped_budget": 0}
    budget_stopped = False

    def worst(p: dict[str, Any]) -> float:
        e = estimate_judge_tokens(p)
        return judge_cost_usd(e["user"], max_tokens, e["prefix"], 0)

    async def one(p: dict[str, Any], reserved: float) -> None:
        rec = await execute_judge_call(p, judge_call=judge_call, max_tokens=max_tokens)
        guard.settle(reserved, rec)
        counts["ok" if rec["status"] == "ok" else "error"] += 1
        on_record(rec)

    queue = list(pending)
    if queue:
        first = queue.pop(0)
        w = worst(first)
        if guard.try_reserve(w):
            counts["launched"] += 1
            await one(first, w)
        else:
            return {**counts, "skipped_budget": len(pending), "budget_stopped": True, "spent_usd": guard.spent_usd}
    sem = asyncio.Semaphore(max(1, concurrency))
    tasks: list[asyncio.Task[None]] = []

    async def guarded(p: dict[str, Any], reserved: float) -> None:
        try:
            await one(p, reserved)
        finally:
            sem.release()

    for i, p in enumerate(queue):
        await sem.acquire()
        w = worst(p)
        if not guard.try_reserve(w):
            sem.release()
            budget_stopped = True
            counts["skipped_budget"] = len(queue) - i
            break
        counts["launched"] += 1
        tasks.append(asyncio.create_task(guarded(p, w)))
    if tasks:
        await asyncio.gather(*tasks)
    return {**counts, "budget_stopped": budget_stopped, "spent_usd": guard.spent_usd}


# --------------------------------------------------------------------------------------------------
# Summary (pure)
# --------------------------------------------------------------------------------------------------


def measure(hits: int, total: int) -> dict[str, Any]:
    ci = wilson_interval(hits, total)
    return {"hits": hits, "total": total, "rate": (hits / total) if total else None,
            "ci_low": ci[0] if ci else None, "ci_high": ci[1] if ci else None}


def _pool(rows: Sequence[dict[str, Any] | None]) -> dict[str, Any]:
    rows = [r for r in rows if r]
    return measure(sum(r["hits"] for r in rows), sum(r["total"] for r in rows))


def _mean(xs: Sequence[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None


def pool_scores(scores: Sequence[dict[str, Any]]) -> dict[str, Any]:
    cit = [s for s in scores if s.get("citations_requested")]
    ret = [s["retrieval"] for s in scores if s.get("retrieval")]
    return {
        "answers": len(scores),
        "fact_recall": _pool([s["fact_recall"] for s in scores]),
        "fact_recall_supplier_specific": _pool([s["fact_recall_supplier_specific"] for s in scores]),
        "fact_recall_non_specific": _pool([s["fact_recall_non_specific"] for s in scores]),
        "fact_recall_statutory": _pool([s["fact_recall_statutory"] for s in scores]),
        "citations_requested": bool(cit),
        "citations_per_answer_mean": _mean([s["citation_count"] for s in cit]) if cit else None,
        "zero_citation_answers": measure(sum(1 for s in cit if s["zero_citations"]), len(cit)) if cit else None,
        "expected_chunk_recall": _pool([s["expected_chunk_recall"] for s in cit]) if cit else None,
        "citations_at_expected": _pool([s["citations_at_expected"] for s in cit]) if cit else None,
        "citations_at_deccan": _pool([s["citations_at_deccan"] for s in cit]) if cit else None,
        "citations_at_distractor": _pool([s["citations_at_distractor"] for s in cit]) if cit else None,
        "cited_support": _pool([s["cited_support"] for s in cit]) if cit else None,
        "contaminated_answers": measure(sum(1 for s in scores if s["contamination"]["contaminated"]), len(scores)),
        "value_contaminated_answers": measure(sum(1 for s in scores if s["contamination"]["distractor_values"]), len(scores)),
        "value_contaminated_unattributed_answers": measure(
            sum(1 for s in scores if any(not h["attributed_to_distractor"] for h in s["contamination"]["distractor_values"])), len(scores)),
        "answers_whose_synthesis_saw_distractor_text": measure(
            sum(1 for s in scores if s["contamination"].get("synthesis_saw_distractor_text")), len(scores)),
        "citation_contaminated_answers": measure(sum(1 for s in scores if s["contamination"]["distractor_chunks_cited"]), len(scores)),
        "retrieval": {
            "recall_after_bm25": _pool([r.get("recall_after_bm25") for r in ret]) if any(r.get("recall_after_bm25") for r in ret) else None,
            "recall_after_rerank": _pool([r.get("recall_after_rerank") for r in ret]),
            "distractors_selected": measure(sum(r["distractors_selected"] for r in ret), sum(r["selected"] for r in ret)),
            "backfilled": sum(r["backfilled"] for r in ret),
            "invalid_picks": sum(r["invalid_picks"] for r in ret),
        } if ret else None,
    }


def pool_judgements(recs: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    ok = [r for r in recs if r.get("status") == "ok" and r.get("parsed")]
    if not ok:
        return None
    errs = [e for r in ok for e in r["parsed"]["factual_errors"]]
    return {
        "judgements": len(ok),
        "correctness_mean": _mean([r["parsed"]["correctness"]["score"] for r in ok]),
        "completeness_mean": _mean([r["parsed"]["completeness"]["score"] for r in ok]),
        "material_errors": sum(1 for e in errs if e["severity"] == "material"),
        "minor_errors": sum(1 for e in errs if e["severity"] == "minor"),
        "answers_with_material_error": measure(sum(1 for r in ok if any(e["severity"] == "material" for e in r["parsed"]["factual_errors"])), len(ok)),
        "answers_the_question": dict(Counter(r["parsed"]["answers_the_question"] for r in ok)),
    }


def _answer_cost_views(answers: Sequence[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for view in ("billed", "cold", "warm"):
        costs = [answer_cost(a, view=view) for a in answers]
        out[view] = {k: _mean([c[k] for c in costs]) for k in ("sonnet", "haiku", "total")}
    return out


def _tokens(answers: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_role: dict[str, dict[str, list[int]]] = {}
    for a in answers:
        for c in a.get("calls") or []:
            d = by_role.setdefault(c["role"], {"prompt": [], "output": [], "cache_write": [], "cache_read": [], "thinking": []})
            d["prompt"].append(prompt_tokens(c))
            d["output"].append(int(c.get("output_tokens") or 0))
            d["cache_write"].append(int(c.get("cache_creation_tokens") or 0))
            d["cache_read"].append(int(c.get("cache_read_tokens") or 0))
            d["thinking"].append(int(c.get("thinking_tokens") or 0))
    return {role: {k: {"mean": _mean(v), "min": min(v) if v else None, "max": max(v) if v else None} for k, v in d.items()}
            for role, d in by_role.items()}


def summarise_group(answers: Sequence[dict[str, Any]], scores: Sequence[dict[str, Any]], sessions: int,
                    judgements: Sequence[dict[str, Any]] = ()) -> dict[str, Any]:
    per_q_costs = _answer_cost_views(answers)
    session_costs = {view: {k: (v * len(session_questions()) if v is not None else None) for k, v in per_q_costs[view].items()}
                     for view in per_q_costs}
    premiums = [cache_write_premium_usd(a) for a in answers if int(a.get("q_index") or 0) == 0]
    return {
        "sessions": sessions,
        **pool_scores(scores),
        "cost_per_question": per_q_costs,
        "cost_per_session_8q": session_costs,
        "cache_write_premium_usd": _mean(premiums) if premiums else 0.0,
        "tokens": _tokens(answers),
        "judge": pool_judgements(judgements),
    }


def _judgement_index(judgements: Sequence[dict[str, Any]]) -> dict[tuple, list[dict[str, Any]]]:
    idx: dict[tuple, list[dict[str, Any]]] = {}
    latest: dict[str, dict[str, Any]] = {}
    for r in judgements:
        if r.get("status") == "ok":
            latest[r["call_id"]] = r
    for r in latest.values():
        idx.setdefault((r["source"], r["rung_id"], int(r["scale"]), int(r["repeat_index"]), r["preset_id"], r["question_id"]), []).append(r)
    return idx


def judge_data_quality(judgements: Sequence[dict[str, Any]], used_call_ids: set[str], *, expected: int) -> dict[str, Any]:
    """Judge-side checks: failed calls, non-end_turn, model mismatch, cache pattern, judgements not matching a used answer."""
    latest: dict[str, dict[str, Any]] = {}
    for j in judgements:
        latest[j["call_id"]] = j if j.get("status") == "ok" or j["call_id"] not in latest else latest[j["call_id"]]
    def brief(j: dict[str, Any], **extra: Any) -> dict[str, Any]:
        return {"call_id": j.get("call_id"), "status": j.get("status"), **extra}
    return {
        "judge_failed_calls": [brief(j, error_type=j.get("error_type"), error_message=j.get("error_message"))
                               for j in judgements if j.get("status") != "ok"],
        "judge_non_end_turn": [brief(j, stop_reason=j.get("stop_reason")) for j in judgements
                               if j.get("status") == "ok" and j.get("stop_reason") != "end_turn"],
        "judge_model_mismatches": [brief(j, model_id=j.get("model_id")) for j in judgements
                                   if j.get("model_id") and j.get("model_id") != JUDGE_MODEL],
        "judge_cache_misses": [brief(j, cache_write=j.get("cache_creation_tokens"), cache_read=j.get("cache_read_tokens"))
                               for j in judgements if j.get("status") == "ok"
                               and not (j.get("cache_creation_tokens") or j.get("cache_read_tokens"))],
        "judgements_not_matching_a_scored_answer": [brief(j, source=j.get("source"), run_id=j.get("run_id"))
                                                    for cid, j in latest.items() if j.get("status") == "ok" and cid not in used_call_ids],
        "scored_answers_without_judgement": max(0, expected - len(used_call_ids)) if judgements else None,
    }


def data_quality(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    errors, stops, mismatches, cache_issues, haiku_over = [], [], [], [], []
    for r in records:
        if r.get("status") != "ok":
            errors.append({"rung_id": r.get("rung_id"), "scale": r.get("scale"), "repeat_index": r.get("repeat_index"),
                           "run_id": r.get("run_id"), "error_message": r.get("error_message")})
        for a in r.get("answers") or []:
            for c in a.get("calls") or []:
                where = {"rung_id": r.get("rung_id"), "scale": r.get("scale"), "repeat_index": r.get("repeat_index"),
                         "q_index": a.get("q_index"), "role": c.get("role")}
                if c.get("stop_reason") != "end_turn":
                    stops.append({**where, "stop_reason": c.get("stop_reason")})
                if c.get("model_id") != c.get("intended_model_id"):
                    mismatches.append({**where, "model_id": c.get("model_id"), "intended": c.get("intended_model_id")})
                if c.get("role") == "rerank" and prompt_tokens(c) > HAIKU_LONG_PROMPT_TOKENS:
                    haiku_over.append({**where, "prompt_tokens": prompt_tokens(c)})
                cw, cr = int(c.get("cache_creation_tokens") or 0), int(c.get("cache_read_tokens") or 0)
                if c.get("cache_control"):
                    first = int(a.get("q_index") or 0) == 0
                    if first and (cw == 0 or cr > 0):
                        cache_issues.append({**where, "issue": "first question did not write the cache", "cache_write": cw, "cache_read": cr})
                    if not first and (cr == 0 or cw > 0):
                        cache_issues.append({**where, "issue": "later question did not read the cache", "cache_write": cw, "cache_read": cr})
                elif cw or cr:
                    cache_issues.append({**where, "issue": "cache tokens on a call without cache_control", "cache_write": cw, "cache_read": cr})
    return {"error_sessions": errors, "non_end_turn_calls": stops, "model_mismatches": mismatches,
            "cache_anomalies": cache_issues, "haiku_calls_over_100k_prompt": haiku_over}


def summarise(
    records: Sequence[dict[str, Any]],
    *,
    keys: dict[str, Any] | None = None,
    golden: dict[str, Any] | None = None,
    judgements: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    keys = keys or load_quality_keys()
    contamination = build_contamination_index(keys)
    corpora = {s: build_scaled_corpus(s) for s in SCALES}
    jidx = _judgement_index(judgements)
    current = [r for r in records if is_current_settings(r)]
    ok = latest_ok_sessions(current)

    used_judgements: set[str] = set()

    def judged(src: str, a: dict[str, Any], rung: str, scale: int, rep: int, run_id: str | None = None) -> list[dict[str, Any]]:
        """Judgements of exactly this answer (same answer text; same session for rerun answers)."""
        sha = _sha(a.get("answer_markdown") or "")
        out = [j for j in jidx.get((src, rung, scale, rep, a["preset_id"], a["question_id"]), [])
               if j.get("answer_sha256") == sha and (src == "golden" or j.get("run_id") == run_id)]
        used_judgements.update(j["call_id"] for j in out)
        return out

    groups: dict[str, Any] = {}
    per_question: dict[str, Any] = {}
    review: dict[str, list[dict[str, Any]]] = {"material_errors": [], "contaminated_answers": []}
    for rung in RUNG_IDS:
        for scale in SCALES:
            sess = [r for r in ok if r["rung_id"] == rung and int(r["scale"]) == scale]
            if not sess:
                continue
            answers, scores, js = [], [], []
            for r in sess:
                for a in r["answers"]:
                    s = score_answer(a, rung_id=rung, corpus=corpora[scale], keys=keys, contamination=contamination)
                    answers.append(a)
                    scores.append(s)
                    jj = judged("rerun", a, rung, scale, int(r["repeat_index"]), r.get("run_id"))
                    js += jj
                    _collect_review(review, "rerun", rung, scale, int(r["repeat_index"]), a, s, jj)
            groups[f"{rung}|{scale}"] = {"rung_id": rung, "scale": scale, **summarise_group(answers, scores, len(sess), js)}
            for pid, q in session_questions():
                qa = [(a, s) for a, s in zip(answers, scores) if a["preset_id"] == pid and a["question_id"] == q["question_id"]]
                qj = [j for a, _ in qa for j in js if j["preset_id"] == pid and j["question_id"] == q["question_id"]]
                per_question[f"{rung}|{scale}|{pid}/{q['question_id']}"] = {
                    "rung_id": rung, "scale": scale, "question": question_key(pid, q["question_id"]),
                    **summarise_group([a for a, _ in qa], [s for _, s in qa], len(sess), qj)}
    # original capture (golden, scale 1, n = 1)
    golden = golden if golden is not None else load_golden()
    g_groups: dict[str, Any] = {}
    g_answers = golden_answers(golden)
    for rung in RUNG_IDS:
        ga = [a for a in g_answers if a["rung_id"] == rung]
        if not ga:
            continue
        gs, gj = [], []
        for a in ga:
            s = score_answer(a, rung_id=rung, corpus=corpora[1], keys=keys, contamination=contamination)
            gs.append(s)
            jj = judged("golden", a, rung, 1, 0)
            gj += jj
            _collect_review(review, "golden", rung, 1, 0, a, s, jj)
        g_groups[rung] = {"rung_id": rung, "scale": 1, **summarise_group(ga, gs, 1, gj),
                          "per_question": {question_key(a["preset_id"], a["question_id"]): s for a, s in zip(ga, gs)}}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "keys_version": keys["meta"].get("keys_version"),
        "key_counts": key_counts(keys),
        "rung_ids": list(RUNG_IDS),
        "scales": list(SCALES),
        "corpus": {str(s): corpus_size(corpora[s]) for s in SCALES},
        "rerun": {
            "record_count": len(records),
            "ok_sessions_used": len(ok),
            "superseded_record_count": len(records) - len(current),
            "groups": groups,
            "per_question": per_question,
            "break_even": break_even_tables(groups),
            "data_quality": {**data_quality(current), "superseded_sessions": superseded_sessions(records),
                             **judge_data_quality(judgements, used_judgements,
                                                  expected=sum(len(r["answers"]) for r in ok) + len(g_answers))},
        },
        "original_capture": {"groups": g_groups,
                             "break_even": break_even_tables({f"{r}|1": g for r, g in g_groups.items()})["1"]},
        "judge": {"records": len(judgements), "ok": sum(1 for j in judgements if j.get("status") == "ok"),
                  "spend_usd": sum(judgement_cost_usd(j) for j in judgements)},
        "for_lead_review": review,
    }


def _collect_review(review: dict[str, list[dict[str, Any]]], source: str, rung: str, scale: int, rep: int,
                    a: dict[str, Any], s: dict[str, Any], judged: Sequence[dict[str, Any]]) -> None:
    where = {"source": source, "rung_id": rung, "scale": scale, "repeat_index": rep, "question": question_key(a["preset_id"], a["question_id"])}
    if s["contamination"]["contaminated"]:
        text = str(a.get("answer_markdown") or "")
        quotes = []
        for hit in s["contamination"]["distractor_values"]:
            quotes.append({**hit, "answer_excerpt": answer_excerpt(text, hit["value"])})
        review["contaminated_answers"].append({**where, "distractor_values": quotes,
                                               "distractor_chunks_cited": s["contamination"]["distractor_chunks_cited"],
                                               "cited_text": [c.get("cited_text") for c in a.get("citations") or []
                                                              if c.get("chunk_id") in s["contamination"]["distractor_chunks_cited"]]})
    for j in judged:
        for e in j["parsed"]["factual_errors"]:
            if e["severity"] == "material":
                review["material_errors"].append({**where, "judge_call_id": j["call_id"], **e})


def break_even_tables(groups: dict[str, Any]) -> dict[str, Any]:
    """Per scale: questions sharing one cache write at which A becomes cheaper than B (warm per-question cost +
    one-off cache-write premium, both measured)."""
    out: dict[str, Any] = {}
    pairs = [("cached_full_corpus_citations", "hybrid_rag_rerank_citations"),
             (NEW_RUNG, "hybrid_rag_rerank_citations"),
             ("cached_full_corpus_citations", NEW_RUNG)]
    for scale in SCALES:
        rows = []
        for a, b in pairs:
            ga, gb = groups.get(f"{a}|{scale}"), groups.get(f"{b}|{scale}")
            if not ga or not gb:
                continue
            ca, cb = ga["cost_per_question"]["warm"]["total"], gb["cost_per_question"]["warm"]["total"]
            if ca is None or cb is None:
                continue
            rows.append({"a": a, "b": b, **break_even_questions(ga["cache_write_premium_usd"] or 0.0, ca,
                                                                gb["cache_write_premium_usd"] or 0.0, cb)})
        out[str(scale)] = rows
    return out


# --------------------------------------------------------------------------------------------------
# App-facing portfolio (replays/cat4_quality_summary.json)
# --------------------------------------------------------------------------------------------------

PORTFOLIO_SCHEMA_VERSION = 1
GOLDEN_REPEAT_INDEX = 0
GOLDEN_SCALE = 1


def _cell_from_group(g: dict[str, Any]) -> dict[str, Any]:
    ret = g.get("retrieval") or {}
    j = g.get("judge") or {}
    cost = g["cost_per_question"]
    return {
        "rung_id": g["rung_id"],
        "runnable_in_app": g["rung_id"] in APP_RUNG_IDS,
        "scale": int(g["scale"]),
        "sessions": int(g["sessions"]),
        "answers": int(g["answers"]),
        "fact_recall": g["fact_recall"],
        "fact_recall_supplier_specific": g["fact_recall_supplier_specific"],
        "fact_recall_non_specific": g["fact_recall_non_specific"],
        "citations_requested": bool(g["citations_requested"]),
        "citations_per_answer_mean": g["citations_per_answer_mean"],
        "zero_citation_answers": g["zero_citation_answers"],
        "expected_chunk_recall": g["expected_chunk_recall"],
        "citations_at_expected": g["citations_at_expected"],
        "cited_support": g["cited_support"],
        "contaminated_answers": g["contaminated_answers"],
        "value_contaminated_answers": g["value_contaminated_answers"],
        "value_contaminated_unattributed_answers": g.get("value_contaminated_unattributed_answers"),
        "citation_contaminated_answers": g["citation_contaminated_answers"],
        "exposure_answers": g.get("answers_whose_synthesis_saw_distractor_text"),
        "recall_after_bm25": ret.get("recall_after_bm25"),
        "recall_after_rerank": ret.get("recall_after_rerank"),
        "distractors_selected": ret.get("distractors_selected"),
        "backfilled": ret.get("backfilled"),
        "invalid_picks": ret.get("invalid_picks"),
        "judged": int(j.get("judgements") or 0),
        "correctness_mean": j.get("correctness_mean"),
        "completeness_mean": j.get("completeness_mean"),
        "material_errors": j.get("material_errors"),
        "minor_errors": j.get("minor_errors"),
        "answers_with_material_error": j.get("answers_with_material_error"),
        "answers_the_question": j.get("answers_the_question") or {},
        "cost_per_question_billed_usd": cost["billed"]["total"],
        "cost_per_question_cold_usd": cost["cold"]["total"],
        "cost_per_question_warm_usd": cost["warm"]["total"],
        "cost_per_question_billed_sonnet_usd": cost["billed"]["sonnet"],
        "cost_per_question_billed_haiku_usd": cost["billed"]["haiku"],
        "cache_write_premium_usd": g.get("cache_write_premium_usd") or 0.0,
    }


def _question_row(v: dict[str, Any]) -> dict[str, Any]:
    j = v.get("judge") or {}
    return {
        "rung_id": v["rung_id"], "scale": int(v["scale"]), "question": v["question"], "answers": int(v["answers"]),
        "fact_recall": v["fact_recall"], "citations_per_answer_mean": v["citations_per_answer_mean"],
        "zero_citation_answers": v["zero_citation_answers"], "citations_at_expected": v["citations_at_expected"],
        "expected_chunk_recall": v["expected_chunk_recall"],
        "recall_after_rerank": (v.get("retrieval") or {}).get("recall_after_rerank"),
        "correctness_mean": j.get("correctness_mean"), "completeness_mean": j.get("completeness_mean"),
        "material_errors": j.get("material_errors"),
        "cost_per_question_billed_usd": v["cost_per_question"]["billed"]["total"],
    }


def build_quality_portfolio(
    records: Sequence[dict[str, Any]],
    judgements: Sequence[dict[str, Any]],
    *,
    keys: dict[str, Any] | None = None,
    golden: dict[str, Any] | None = None,
    source_file: str | None = None,
    judgements_file: str | None = None,
) -> dict[str, Any]:
    """Pooled rerun picture for the app, from the same `summarise()` path as scripts/analyze_cat4_quality.py.

    `cells`: every rung x scale (n = sessions x 8 answers). `golden_mapped`: per rung x question for the sessions the
    app's recorded runs come from (repeat 0, scale 1). Deterministic: no timestamps."""
    keys = keys or load_quality_keys()
    full = summarise(records, keys=keys, golden=golden if golden is not None else {"presets": {}}, judgements=judgements)
    mapped_records = [r for r in latest_ok_sessions(records)
                      if int(r["repeat_index"]) == GOLDEN_REPEAT_INDEX and int(r["scale"]) == GOLDEN_SCALE]
    mapped = summarise(mapped_records, keys=keys, golden={"presets": {}}, judgements=judgements)
    rr = full["rerun"]
    dq = rr["data_quality"]
    cells = [_cell_from_group(g) for g in rr["groups"].values()]
    sessions = sorted({c["sessions"] for c in cells})
    return {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "source": "cat4 quality rerun",
        "source_file": source_file,
        "judgements_file": judgements_file,
        "keys_version": full["keys_version"],
        "judge_model": JUDGE_MODEL,
        "judge_passes": JUDGE_REPEATS,
        "scope_line": scope_line(),
        "record_count": rr["record_count"],
        "ok_sessions": rr["ok_sessions_used"],
        "error_records": len(dq["error_sessions"]),
        "superseded_records": rr.get("superseded_record_count", 0),
        "answers_scored": sum(c["answers"] for c in cells),
        "answers_judged": sum(c["judged"] for c in cells),
        "sessions_per_cell": sessions[0] if len(sessions) == 1 else None,
        "questions_per_session": len(session_questions()),
        "scales": list(SCALES),
        "corpus": {k: {"documents": v["documents"], "chunks": v["chunks"], "chars": v["chars"]} for k, v in full["corpus"].items()},
        "synth_max_tokens": SYNTH_MAX_TOKENS,
        "matrix_complete": len(cells) == len(RUNG_IDS) * len(SCALES) and len(sessions) == 1,
        "cells": cells,
        "break_even": {scale: [{k: r[k] for k in ("a", "b", "premium_a_usd", "per_question_a_usd", "premium_b_usd",
                                                    "per_question_b_usd", "n_star", "questions", "verdict")} for r in rows]
                       for scale, rows in rr["break_even"].items()},
        "golden_mapped": {
            "selection_rule": f"repeat_index {GOLDEN_REPEAT_INDEX}, corpus scale {GOLDEN_SCALE}, every rung",
            "run_ids": {r["rung_id"]: r["run_id"] for r in mapped_records},
            "questions": [_question_row(v) for v in mapped["rerun"]["per_question"].values()],
        },
    }
