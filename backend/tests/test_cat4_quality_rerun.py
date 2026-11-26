"""Offline tests for the Category 4 quality-rerun harness, answer key and scaled corpus (no network, no API key)."""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat4_rag import quality_rerun as qr  # noqa: E402
from app.archetypes.cat4_rag import scaled_corpus as sc  # noqa: E402
from app.archetypes.cat4_rag.prompts import get_cat4_haiku_reranker_system_prompt  # noqa: E402
from app.archetypes.cat4_rag.runner import build_rung2_doc_blocks  # noqa: E402
from app.archetypes.cat6_swarms.fair_rerun import wilson_interval  # noqa: E402
from app.core import anthropic_service  # noqa: E402
from app.core.anthropic_service import AnthropicRawResult  # noqa: E402
from app.core.pricing import compute_run_finops  # noqa: E402
from app.data.cat4_fixtures import CAT4_PRESETS, hydrate_deal_room_index  # noqa: E402

KEYS = qr.load_quality_keys()
C1 = qr.build_scaled_corpus(1)
C3 = qr.build_scaled_corpus(3)
GOLDEN = qr.load_golden()
FACTS = {f["id"]: f for f in KEYS["facts"]}
Q_SPECS = {(p["id"], q["question_id"]): q for p in CAT4_PRESETS for q in p["questions"]}


def run(coro):
    return asyncio.run(coro)


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, BACKEND_DIR / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------------------------------


class Fakes:
    """Records every call; synthesis cites the first 40 chars of the first document's own text."""

    def __init__(self, *, fail_at: int | None = None, rerank_ids: list[str] | None = None, cache: bool = True,
                 synth_stop: str = "end_turn") -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_at = fail_at
        self.rerank_ids = rerank_ids
        self.cache = cache
        self.synth_stop = synth_stop
        self.n_synth = 0
        self.seen_prefix: set[str] = set()
        self.active = 0
        self.max_active = 0

    def _cache_tokens(self, key: str, size: int) -> tuple[int, int]:
        if not self.cache:
            return 0, 0
        if key in self.seen_prefix:
            return 0, size
        self.seen_prefix.add(key)
        return size, 0

    async def rerank(self, **kw: Any) -> AnthropicRawResult:
        self.calls.append(("rerank", kw))
        await asyncio.sleep(0)
        if kw.get("user_content"):
            ids = self.rerank_ids or ["DOC-01#c03", "DOC-07#c02", "DOC-02#c01", "DOC-03#c04", "DOC-05#c02"]
            cw, cr = self._cache_tokens(kw["user_content"][0]["text"], 20000)
            inp = 150
        else:
            ids = re.findall(r"CHUNK_ID: (\S+)", kw["rerank_payload"])[:5]
            cw, cr, inp = 0, 0, 9000
        return AnthropicRawResult(model_id=qr.HAIKU_MODEL_ID, latency_ms=10, input_tokens=inp, output_tokens=300,
                                  cache_creation_tokens=cw, cache_read_tokens=cr, raw_text="{}",
                                  structured={"selected_chunks": [{"chunk_id": i, "relevance_score": 0.9, "rationale": "x"} for i in ids]},
                                  stop_reason="end_turn")

    async def synth(self, **kw: Any) -> AnthropicRawResult:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            self.calls.append(("synthesis", kw))
            await asyncio.sleep(0.001)
            self.n_synth += 1
            if self.fail_at is not None and self.n_synth == self.fail_at:
                raise RuntimeError("boom")
            citations = []
            cw = cr = 0
            blocks = kw.get("documents_for_blocks")
            if blocks:
                b = blocks[0]
                off = int(b.get("doc_char_offset") or 0)
                s_raw = len(qr.nonce_line("x" * 32)) if off < 0 else 0
                citations.append({"cite_number": 1, "doc_id": b["doc_id"], "document_title": b["block_title"], "clause_ref": "",
                                  "cited_text": b["data"][s_raw:s_raw + 40], "start_char_index": off + s_raw,
                                  "end_char_index": off + s_raw + 40})
                if kw.get("use_prefix_cache"):
                    cw, cr = self._cache_tokens(blocks[0]["data"][:80], 21000)
            return AnthropicRawResult(model_id=qr.SONNET_MODEL_ID, latency_ms=20, input_tokens=100 if cw or cr else 18000,
                                      output_tokens=900, cache_creation_tokens=cw, cache_read_tokens=cr,
                                      raw_text="Liability cap INR 4.50 Crore [1].",
                                      structured={"segments": [], "citations": citations}, stop_reason=self.synth_stop,
                                      thinking_tokens=0)
        finally:
            self.active -= 1


def _session(rung: str, scale: int = 1, fakes: Fakes | None = None) -> tuple[dict[str, Any], Fakes]:
    f = fakes or Fakes()
    rec = run(qr.execute_session(rung_id=rung, scale=scale, repeat_index=0, api_key="k", synth_call=f.synth, rerank_call=f.rerank))
    return rec, f


# --------------------------------------------------------------------------------------------------
# Answer key invariants
# --------------------------------------------------------------------------------------------------


def test_key_counts_and_required_fields() -> None:
    by_q: dict[tuple[str, str], int] = {}
    for f in KEYS["facts"]:
        for k in ("id", "preset_id", "question_id", "description", "any_of", "chunk_id", "evidence", "supplier_specific", "category"):
            assert k in f, (f.get("id"), k)
        assert isinstance(f["supplier_specific"], bool)
        assert f["supplier_specific"] == (f["category"] == "commercial")
        assert f["any_of"] and all(isinstance(a, str) and a for a in f["any_of"])
        by_q[(f["preset_id"], f["question_id"])] = by_q.get((f["preset_id"], f["question_id"]), 0) + 1
    assert set(by_q) == set(Q_SPECS)
    assert all(4 <= n <= 7 for n in by_q.values()), by_q
    assert len({f["id"] for f in KEYS["facts"]}) == len(KEYS["facts"])


def test_key_evidence_quotes_are_verbatim_in_named_chunk() -> None:
    for f in KEYS["facts"]:
        ch = C1.chunk_by_id[f["chunk_id"]]
        assert f["evidence"]["quote"] in ch["full_block_text"], f["id"]


def test_key_alternatives_match_their_chunk_and_not_the_question() -> None:
    for f in KEYS["facts"]:
        text = qr.normalise_text(qr.chunk_search_text(C1.chunk_by_id[f["chunk_id"]]))
        for a in f["any_of"]:
            assert qr.contains_alternative(text, a), (f["id"], a)
        for x in f.get("also_in_corpus") or []:
            assert qr.text_matches(qr.chunk_search_text(C1.chunk_by_id[x["chunk_id"]]), [x["alt"]]), (f["id"], x)
        q = Q_SPECS[(f["preset_id"], f["question_id"])]["question"]
        assert not qr.text_matches(q, qr.fact_alternatives(f)), f["id"]


def test_format_variants_recorded_in_meta() -> None:
    added = {x["fact_id"]: x["added"] for x in KEYS["meta"]["format_variants_added"]}
    for f in KEYS["facts"]:
        assert (f.get("format_variants") or []) == added.get(f["id"], []), f["id"]


def test_supplier_specific_alternatives_never_match_distractor_chunks() -> None:
    distractor = [c for c in C3.flat_chunks if C3.supplier_of_chunk(c["chunk_id"]) != sc.BASE_SUPPLIER]
    texts = [qr.normalise_text(qr.chunk_search_text(c)) for c in distractor]
    for f in KEYS["facts"]:
        if not f["supplier_specific"]:
            continue
        for a in qr.fact_alternatives(f):
            assert not any(qr.contains_alternative(t, a) for t in texts), (f["id"], a)


def test_statutory_and_mechanism_facts_still_match_distractor_chunks() -> None:
    for f in KEYS["facts"]:
        if f["supplier_specific"]:
            continue
        for s in sc.DISTRACTOR_SUPPLIERS:
            cid = qr._distractor_chunk_id(f["chunk_id"], s)
            assert qr.text_matches(qr.chunk_search_text(C3.chunk_by_id[cid]), f["any_of"]), (f["id"], s)


# --------------------------------------------------------------------------------------------------
# Matcher
# --------------------------------------------------------------------------------------------------


def test_matcher_boundary_and_decimal_guards() -> None:
    n = qr.normalise_text
    assert qr.contains_alternative(n("cap of INR 25 Crore per event"), "25 Crore")
    assert not qr.contains_alternative(n("cap of INR 33.25 Crore"), "25 Crore")
    assert not qr.contains_alternative(n("INR 4.505"), "4.50")
    assert not qr.contains_alternative(n("98.85%"), "98.8")
    assert not qr.contains_alternative(n("125 days"), "25 days")
    assert qr.contains_alternative(n("**INR 4,50,00,000**"), "45000000")
    assert qr.contains_alternative(n("the 2.0% cap."), "2.0%")


# --------------------------------------------------------------------------------------------------
# Scaled corpus
# --------------------------------------------------------------------------------------------------


def test_scale1_is_exactly_the_app_corpus() -> None:
    docs, flat, total = hydrate_deal_room_index()
    assert C1.hydrated_docs == docs and C1.flat_chunks == flat and C1.total_chars == total
    assert set(C1.supplier_by_doc.values()) == {sc.BASE_SUPPLIER}


def test_scale3_shape_determinism_and_base_unchanged() -> None:
    again = qr.build_scaled_corpus(3)
    assert [d["full_text"] for d in again.hydrated_docs] == [d["full_text"] for d in C3.hydrated_docs]
    assert again.mapping == C3.mapping
    assert len(C3.hydrated_docs) == 21 and len(C3.flat_chunks) == 84
    ids = sorted(d["doc_id"] for d in C3.hydrated_docs)
    assert ids == [f"DOC-{i:02d}" for i in range(1, 22)]
    base = {d["doc_id"]: d for d in C1.hydrated_docs}
    for d in C3.hydrated_docs:
        if d["doc_id"] in base:
            assert d["full_text"] == base[d["doc_id"]]["full_text"]
            assert [c["chunk_id"] for c in d["chunks"]] == [c["chunk_id"] for c in base[d["doc_id"]]["chunks"]]
    # mutation of a returned copy does not leak
    again.hydrated_docs[0]["full_text"] = "x"
    assert qr.build_scaled_corpus(3).hydrated_docs[0]["full_text"] != "x"


def test_distractors_have_no_deccan_and_explicit_mapping() -> None:
    for d in C3.hydrated_docs:
        if C3.supplier_by_doc[d["doc_id"]] == sc.BASE_SUPPLIER:
            continue
        blob = d["full_text"] + json.dumps([c.get("keywords") for c in d["chunks"]])
        assert "deccan" not in blob.lower(), d["doc_id"]
        assert "DSA" not in d["doc_code"], d["doc_code"]
    for s in sc.DISTRACTOR_SUPPLIERS:
        recs = C3.mapping[s]
        assert recs and all({"kind", "original", "distractor", "where"} <= set(r) for r in recs)
        assert all(r["original"] != r["distractor"] or r["kind"] == "protect" for r in recs)


def test_corpus_size_reported_and_under_budget() -> None:
    s1, s3 = qr.corpus_size(C1), qr.corpus_size(C3)
    assert s1["documents"] == 7 and s3["documents"] == 21
    assert 2.9 <= s3["ratio_to_base_chars"] <= 3.1
    cpt = qr.calibrate_chars_per_token(GOLDEN)
    est = qr.estimate_session("cached_full_corpus_citations", 3, cpt)
    assert est["prompt_tokens"] / 8 < 90_000
    est4 = qr.estimate_session(qr.NEW_RUNG, 3, cpt)
    assert est4["max_rerank_prompt_tokens"] < qr.HAIKU_LONG_PROMPT_TOKENS


# --------------------------------------------------------------------------------------------------
# Contamination detector
# --------------------------------------------------------------------------------------------------


def test_contamination_index_values_belong_to_distractor_not_deccan() -> None:
    idx = qr.build_contamination_index(KEYS)
    assert set(idx) == {f["id"] for f in KEYS["facts"] if f["supplier_specific"]}
    base_texts = [qr.normalise_text(qr.chunk_search_text(c)) for c in C1.flat_chunks]
    for fid, per in idx.items():
        for s, vals in per.items():
            sup_text = qr.normalise_text("\n".join(qr.chunk_search_text(c) for c in C3.flat_chunks if C3.supplier_of_chunk(c["chunk_id"]) == s))
            standalone = {qr.transform_text(a, s)[0] for a in qr.fact_alternatives(FACTS[fid])}
            for v in vals:
                # either the value is in that supplier's text, or it is the supplier transform of a keyed format variant
                assert qr.contains_alternative(sup_text, v) or v in standalone, (fid, s, v)
                assert not any(qr.contains_alternative(t, v) for t in base_texts), (fid, s, v)
    assert "3,60,00,000" in idx["a1q1-cap-4-50-cr"]["kaveri"]
    assert sum(1 for per in idx.values() for v in per.values() if v) >= 60


def _answer(text: str, citations: list[dict[str, Any]] | None = None, sent: list[str] | None = None,
            pid: str = "audit-01", qid: str = "q1") -> dict[str, Any]:
    return {"preset_id": pid, "question_id": qid, "q_index": 0, "answer_markdown": text, "citations": citations or [],
            "expected_chunk_ids": Q_SPECS[(pid, qid)]["expected_chunk_ids"],
            "chunks_sent": {"chunk_ids": sent}, "retrieval": None, "calls": []}


def test_contamination_detector_flags_value_cited_and_sent() -> None:
    idx = qr.build_contamination_index(KEYS)
    clean = qr.score_answer(_answer("Cap INR 4.50 Crore."), rung_id="cached_full_corpus_citations", corpus=C3, keys=KEYS, contamination=idx)
    assert not clean["contamination"]["contaminated"]
    dirty = qr.score_answer(_answer("Cap INR 3,60,00,000.", citations=[{"chunk_id": "DOC-08#c03", "supplier": "kaveri", "cited_text": "x"}],
                                    sent=["DOC-15#c01", "DOC-01#c03"]),
                            rung_id="hybrid_rag_rerank_citations", corpus=C3, keys=KEYS, contamination=idx)
    c = dirty["contamination"]
    assert c["contaminated"] and c["distractor_values"][0]["supplier"] == "kaveri"
    assert c["distractor_chunks_cited"] == ["DOC-08#c03"] and c["distractor_chunks_sent"] == ["DOC-15#c01"]
    # at scale 1 values are not checked (no distractor exists)
    s1 = qr.score_answer(_answer("Cap INR 3,60,00,000."), rung_id="naive_full_corpus", corpus=C1, keys=KEYS, contamination=idx)
    assert not s1["contamination"]["contaminated"]


# --------------------------------------------------------------------------------------------------
# Per-rung call sequences, cache flags, nonce, ordering
# --------------------------------------------------------------------------------------------------


def test_rung1_naive_sequence() -> None:
    rec, f = _session("naive_full_corpus")
    assert rec["status"] == "ok" and len(rec["answers"]) == 8
    assert [r for r, _ in f.calls] == ["synthesis"] * 8
    kw = f.calls[0][1]
    assert kw["documents_for_blocks"] is None and kw["uncached_corpus_text"] and kw["use_prefix_cache"] is False
    assert kw["max_tokens"] == 4096 and kw["timeout_s"] == qr.SYNTH_TIMEOUT_S and kw["raise_on_max_tokens"] is False
    assert kw["max_retries"] == 0
    assert all(a["citations"] == [] for a in rec["answers"])


def test_rung2_cached_sequence_and_nonce_offset() -> None:
    rec, f = _session("cached_full_corpus_citations")
    assert [r for r, _ in f.calls] == ["synthesis"] * 8
    first_data = {kw["documents_for_blocks"][0]["data"][:60] for _, kw in f.calls}
    assert len(first_data) == 1 and rec["session_nonce"] in next(iter(first_data))
    for _, kw in f.calls:
        assert kw["use_prefix_cache"] is True and len(kw["documents_for_blocks"]) == 7
    app_blocks = build_rung2_doc_blocks(C1.hydrated_docs)
    sent = f.calls[0][1]["documents_for_blocks"]
    assert sent[0]["data"].endswith(app_blocks[0]["data"]) and sent[1:] == app_blocks[1:]
    # the citation at the first real character resolves to the first chunk of DOC-01
    cit = rec["answers"][0]["citations"][0]
    assert cit["start_char_index"] == 0 and cit["chunk_id"] == "DOC-01#c01" and cit["supplier"] == "deccan"
    calls = [c for a in rec["answers"] for c in a["calls"]]
    assert calls[0]["cache_creation_tokens"] > 0 and all(c["cache_read_tokens"] > 0 for c in calls[1:])
    assert all(c["cache_control"] for c in calls)


def test_nonce_same_within_session_and_different_across_sessions() -> None:
    f = Fakes()
    r1, _ = _session("cached_full_corpus_citations", fakes=f)
    r2, _ = _session("cached_full_corpus_citations", fakes=f)
    assert r1["session_nonce"] != r2["session_nonce"]
    assert len(f.seen_prefix) == 2
    calls = [c for r in (r1, r2) for a in r["answers"] for c in a["calls"]]
    assert sum(1 for c in calls if c["cache_creation_tokens"]) == 2  # each session writes its own cache once
    f4 = Fakes()
    a, _ = _session(qr.NEW_RUNG, fakes=f4)
    b, _ = _session(qr.NEW_RUNG, fakes=f4)
    texts = [kw["user_content"][0]["text"] for r, kw in f4.calls if r == "rerank"]
    assert len(set(texts[:8])) == 1 and len(set(texts[8:])) == 1 and texts[0] != texts[8]
    assert a["session_nonce"] in texts[0] and b["session_nonce"] in texts[8]


def test_rung3_hybrid_sequence_bm25_over_session_corpus() -> None:
    rec, f = _session("hybrid_rag_rerank_citations", scale=3)
    assert [r for r, _ in f.calls] == ["rerank", "synthesis"] * 8
    rr = f.calls[0][1]
    assert rr["system_prompt"] == get_cat4_haiku_reranker_system_prompt() and "user_content" not in rr
    assert rr["max_tokens"] == 800 and rr["timeout_s"] == qr.RERANK_TIMEOUT_S
    ans = rec["answers"][0]
    assert len(ans["retrieval"]["bm25_top"]) == 10
    assert ans["retrieval"]["recall_after_bm25"]["total"] == len(ans["expected_chunk_ids"])
    syn = f.calls[1][1]
    assert syn["use_prefix_cache"] is False and len(syn["documents_for_blocks"]) == 5
    assert [b["doc_id"] + "#" for b in syn["documents_for_blocks"]]
    assert ans["chunks_sent"]["chunk_ids"] == ans["retrieval"]["selected_chunk_ids"]
    assert ans["citations"][0]["chunk_id"] == ans["chunks_sent"]["chunk_ids"][0]
    assert all(not c["cache_control"] for c in ans["calls"])


def test_rung4_cached_rerank_sequence() -> None:
    picks = ["DOC-01#c03", "DOC-99#c01", "DOC-08#c03", "DOC-01#c03", "DOC-03#c04"]
    rec, f = _session(qr.NEW_RUNG, scale=3, fakes=Fakes(rerank_ids=picks))
    assert [r for r, _ in f.calls] == ["rerank", "synthesis"] * 8
    rr = f.calls[0][1]
    assert rr["system_prompt"] == qr.get_full_corpus_reranker_system_prompt()
    uc = rr["user_content"]
    assert uc[0]["cache_control"] == {"type": "ephemeral"} and "cache_control" not in uc[1]
    assert uc[0]["text"].count("CHUNK_ID: ") == 84 and Q_SPECS[("audit-01", "q1")]["question"] in uc[1]["text"]
    ans = rec["answers"][0]
    ret = ans["retrieval"]
    assert ret["selected_chunk_ids"] == ["DOC-01#c03", "DOC-08#c03", "DOC-03#c04"]
    assert ret["invalid_picks"] == ["DOC-99#c01"] and ret["shortfall"] == 2 and ret["backfilled_chunk_ids"] == []
    syn = f.calls[1][1]
    assert syn["use_prefix_cache"] is False and len(syn["documents_for_blocks"]) == 3
    assert [c["cache_control"] for c in ans["calls"]] == [True, False]
    rerank_calls = [a["calls"][0] for a in rec["answers"]]
    assert rerank_calls[0]["cache_creation_tokens"] > 0 and all(c["cache_read_tokens"] > 0 for c in rerank_calls[1:])


def test_full_corpus_reranker_prompt_changes_only_candidate_sentence() -> None:
    a = get_cat4_haiku_reranker_system_prompt().splitlines()
    b = qr.get_full_corpus_reranker_system_prompt().splitlines()
    diff = [(x, y) for x, y in zip(a, b) if x != y]
    assert len(a) == len(b) and len(diff) == 1 and "10 BM25" in diff[0][0] and "all deal-room" in diff[0][1]


def test_questions_run_sequentially_in_session_order() -> None:
    rec, f = _session("naive_full_corpus")
    assert f.max_active == 1
    order = [(a["preset_id"], a["question_id"]) for a in rec["answers"]]
    assert order == [(p["id"], q["question_id"]) for p in CAT4_PRESETS for q in p["questions"]]
    assert [a["q_index"] for a in rec["answers"]] == list(range(8))
    assert [kw["user_question"] for _, kw in f.calls] == [qr.scoped_question(Q_SPECS[k]["question"]) for k in order]


def test_mid_session_error_recorded_not_raised() -> None:
    rec, f = _session("cached_full_corpus_citations", fakes=Fakes(fail_at=3))
    assert rec["status"] == "error" and "q3" in rec["error_message"] and "boom" in rec["error_message"]
    assert [a["status"] for a in rec["answers"]] == ["ok", "ok", "error"]
    assert len(f.calls) == 3


def test_truncated_answer_kept_and_flagged() -> None:
    rec, _ = _session("naive_full_corpus", fakes=Fakes(synth_stop="max_tokens"))
    assert rec["status"] == "ok" and len(rec["answers"]) == 8
    dq = qr.data_quality([rec])
    assert len(dq["non_end_turn_calls"]) == 8


def test_zero_citation_answers_kept_as_data() -> None:
    class NoCite(Fakes):
        async def synth(self, **kw: Any) -> AnthropicRawResult:
            r = await super().synth(**kw)
            r.structured = {"segments": [], "citations": []}
            return r

    rec, _ = _session("cached_full_corpus_citations", fakes=NoCite())
    assert rec["status"] == "ok" and len(rec["answers"]) == 8
    s = qr.score_answer(rec["answers"][0], rung_id=rec["rung_id"], corpus=C1, keys=KEYS)
    assert s["zero_citations"] is True and s["citation_count"] == 0


# --------------------------------------------------------------------------------------------------
# Citation -> chunk resolution
# --------------------------------------------------------------------------------------------------


def test_resolve_chunk_by_max_overlap() -> None:
    doc = C3.doc_by_id["DOC-08"]
    c1, c2 = doc["chunks"][0], doc["chunks"][1]
    assert qr.resolve_chunk_id(C3, "DOC-08", c1["doc_char_start"] + 5, c1["doc_char_start"] + 20) == c1["chunk_id"]
    span = (c1["doc_char_end"] - 10, c2["doc_char_start"] + 50)
    assert qr.resolve_chunk_id(C3, "DOC-08", *span) == c2["chunk_id"]
    assert qr.resolve_chunk_id(C3, "DOC-08", c2["doc_char_start"], c2["doc_char_start"]) == c2["chunk_id"]
    assert qr.resolve_chunk_id(C3, "DOC-99", 0, 10) is None
    out = qr.resolve_citations(C3, [{"doc_id": "DOC-15", "start_char_index": 0, "end_char_index": 30}])
    assert out[0]["chunk_id"] == "DOC-15#c01" and out[0]["supplier"] == "narmada"


def test_golden_citations_resolve_to_chunks_containing_cited_text() -> None:
    ga = qr.golden_answers(GOLDEN)
    n = 0
    for a in ga:
        for c in a["citations"]:
            assert c["chunk_id"], c
            ch = C1.chunk_by_id[c["chunk_id"]]
            head = c["cited_text"].strip()[:30]
            if head:
                doc = C1.doc_by_id[c["doc_id"]]["full_text"]
                assert doc[c["start_char_index"]:c["end_char_index"]].strip()[:30] == head
                assert ch["doc_char_start"] <= c["start_char_index"] < ch["doc_char_end"] or head in ch["text"]
            n += 1
    assert n > 100


# --------------------------------------------------------------------------------------------------
# Scoring maths, cost, break-even
# --------------------------------------------------------------------------------------------------


def test_score_answer_fact_and_citation_measures() -> None:
    a = _answer("Cap INR 4.50 Crore; product liability INR 25 Crore.",
                citations=[{"chunk_id": "DOC-01#c03", "supplier": "deccan", "cited_text": "INR 4,50,00,000"},
                           {"chunk_id": "DOC-08#c01", "supplier": "kaveri", "cited_text": "irrelevant"}])
    s = qr.score_answer(a, rung_id="cached_full_corpus_citations", corpus=C3, keys=KEYS)
    hit = {r["fact_id"] for r in s["facts"] if r["hit"]}
    assert "a1q1-cap-4-50-cr" in hit
    assert s["fact_recall"]["total"] == 7
    assert s["fact_recall_supplier_specific"]["total"] + s["fact_recall_non_specific"]["total"] == 7
    assert s["citation_count"] == 2 and s["zero_citations"] is False
    exp = Q_SPECS[("audit-01", "q1")]["expected_chunk_ids"]
    assert s["expected_chunk_recall"] == {"hits": int("DOC-01#c03" in exp), "total": len(set(exp))}
    assert s["citations_at_deccan"] == {"hits": 1, "total": 2} and s["citations_at_distractor"] == {"hits": 1, "total": 2}
    cap = next(r for r in s["facts"] if r["fact_id"] == "a1q1-cap-4-50-cr")
    assert cap["cited_support"] is True
    naive = qr.score_answer(a, rung_id="naive_full_corpus", corpus=C3, keys=KEYS)
    assert naive["citation_count"] is None and naive["cited_support"] is None


def test_pool_and_wilson() -> None:
    m = qr.measure(3, 4)
    lo, hi = wilson_interval(3, 4)
    assert m["rate"] == 0.75 and m["ci_low"] == lo and m["ci_high"] == hi
    assert qr.measure(0, 0)["rate"] is None


def test_cost_views_match_compute_run_finops() -> None:
    first = {"q_index": 0, "calls": [{"role": "synthesis", "model_id": qr.SONNET_MODEL_ID, "intended_model_id": qr.SONNET_MODEL_ID,
                                      "input_tokens": 100, "output_tokens": 1000, "cache_creation_tokens": 0,
                                      "cache_read_tokens": 20000, "cache_control": True}]}
    billed = qr.answer_cost(first)["total"]
    assert billed == pytest.approx(compute_run_finops(model_id=qr.SONNET_MODEL_ID, input_tokens=100, output_tokens=1000,
                                                      cache_creation_tokens=0, cache_read_tokens=20000).total_cost_usd)
    cold = qr.answer_cost(first, view="cold")["total"]
    assert cold == pytest.approx(compute_run_finops(model_id=qr.SONNET_MODEL_ID, input_tokens=100, output_tokens=1000,
                                                    cache_creation_tokens=20000, cache_read_tokens=0).total_cost_usd)
    assert qr.answer_cost(first, view="warm")["total"] == pytest.approx(billed)
    hai = {"q_index": 3, "calls": [{"role": "rerank", "model_id": "unknown-model", "intended_model_id": qr.HAIKU_MODEL_ID,
                                    "input_tokens": 9000, "output_tokens": 300, "cache_control": False}]}
    c = qr.answer_cost(hai)
    assert c["sonnet"] == 0 and c["haiku"] == pytest.approx(compute_run_finops(model_id=qr.HAIKU_MODEL_ID, input_tokens=9000,
                                                                                output_tokens=300).total_cost_usd)
    assert qr.cache_write_premium_usd(first) == pytest.approx(20000 * (2.50 - 0.10) / 1e6)


def test_break_even_hand_case() -> None:
    # A: premium $0.05, $0.01/question; B: no premium, $0.02/question -> N* = 5, A cheaper from question 6
    r = qr.break_even_questions(0.05, 0.01, 0.0, 0.02)
    assert r["n_star"] == pytest.approx(5.0) and r["questions"] == 6
    assert qr.break_even_questions(0.0, 0.01, 0.01, 0.02)["verdict"] == "A cheaper from question 1"
    assert qr.break_even_questions(0.05, 0.03, 0.0, 0.02)["verdict"] == "A never cheaper"
    low = qr.break_even_questions(0.0, 0.03, 0.05, 0.02)
    assert low["questions"] is None and low["n_star"] == pytest.approx(5.0)
    assert {"premium_a_usd", "per_question_a_usd", "premium_b_usd", "per_question_b_usd"} <= set(r)


# --------------------------------------------------------------------------------------------------
# Resume + budget guard
# --------------------------------------------------------------------------------------------------


def test_plan_order_and_resume() -> None:
    plan = qr.plan_matrix(qr.RUNG_IDS, (1, 3), 3)
    assert len(plan) == 24 and plan[:5] == [(r, 1, 0) for r in qr.RUNG_IDS] + [("naive_full_corpus", 3, 0)]
    cur = {"settings": {"synth_max_tokens": qr.SYNTH_MAX_TOKENS}}
    existing = [{"rung_id": "naive_full_corpus", "scale": 1, "repeat_index": 0, "status": "ok", **cur},
                {"rung_id": "cached_full_corpus_citations", "scale": 1, "repeat_index": 0, "status": "error", **cur}]
    pending = qr.select_pending(plan, existing)
    assert ("naive_full_corpus", 1, 0) not in pending and ("cached_full_corpus_citations", 1, 0) in pending
    assert len(pending) == 23


def test_budget_guard_counts_error_spend_and_refuses() -> None:
    rec, _ = _session("naive_full_corpus")
    spend = qr.session_billed_usd(rec)
    assert spend > 0
    g = qr.BudgetGuard(spend + 0.10, [rec, {**rec, "status": "error"}])
    assert g.spent_usd == pytest.approx(2 * spend)
    assert not g.try_reserve(0.01)
    g2 = qr.BudgetGuard(1.0)
    assert g2.try_reserve(0.6) and not g2.try_reserve(0.6)
    g2.settle(0.6, rec)
    assert g2.reserved_usd == 0 and g2.spent_usd == pytest.approx(spend)


def test_run_sessions_stops_at_budget_and_runs_concurrently() -> None:
    f = Fakes()
    seen: list[dict[str, Any]] = []
    plan = qr.plan_matrix(["naive_full_corpus"], (1,), 5)
    res = run(qr.run_sessions(plan, api_key="k", guard=qr.BudgetGuard(1.0), worst_case_usd=lambda k: 0.4,
                              on_record=seen.append, concurrency=3, synth_call=f.synth, rerank_call=f.rerank))
    assert res["launched"] == 2 and res["budget_stopped"] and res["skipped_budget"] == 3
    assert len(seen) == 2 and all(r["status"] == "ok" for r in seen)
    f2 = Fakes()
    res2 = run(qr.run_sessions(qr.plan_matrix(["naive_full_corpus"], (1,), 3), api_key="k", guard=qr.BudgetGuard(100),
                               worst_case_usd=lambda k: 0.1, on_record=lambda r: None, concurrency=3,
                               synth_call=f2.synth, rerank_call=f2.rerank))
    assert res2["ok"] == 3 and f2.max_active > 1


def test_rerun_cli_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mod = _load_script("cat4_quality_rerun")
    out = tmp_path / "runs.jsonl"
    rc = run(mod.main(mod.parse_args(["--dry-run", "--out", str(out)])))
    text = capsys.readouterr().out
    assert rc == 0 and "24 sessions" in text and "worst case" in text and not out.exists()
    out.write_text(json.dumps({"rung_id": "naive_full_corpus", "scale": 1, "repeat_index": 0, "status": "ok", "answers": [],
                               "settings": {"synth_max_tokens": qr.SYNTH_MAX_TOKENS}}) + "\n")
    run(mod.main(mod.parse_args(["--dry-run", "--out", str(out), "--rungs", "naive_full_corpus", "--scales", "1"])))
    assert "1 already ok, 2 pending" in capsys.readouterr().out


def test_wrapper_defaults_preserved() -> None:
    syn = inspect.signature(anthropic_service.run_cat4_rag_synthesis).parameters
    rr = inspect.signature(anthropic_service.run_cat4_haiku_reranker).parameters
    assert syn["max_tokens"].default == 2048 and syn["timeout_s"].default == 90.0 and syn["raise_on_max_tokens"].default is True
    assert syn["max_retries"].default is None
    assert rr["max_tokens"].default == 800 and rr["timeout_s"].default == 45.0 and rr["user_content"].default is None


# --------------------------------------------------------------------------------------------------
# Judge
# --------------------------------------------------------------------------------------------------


def test_strip_citation_markup() -> None:
    t = "Cap INR 4.50 Cr [1][2], see [3, 4].\n\n**Sources:**\n[1] DOC-01 clause 9"
    assert qr.strip_citation_markup(t) == "Cap INR 4.50 Cr, see."
    assert qr.strip_citation_markup("A 【DOC-01†L3】 b <cite index='1'>c</cite>.") == "A b c."
    assert qr.strip_citation_markup("No markers here.") == "No markers here."
    nested = "- **A**:\n  - (i) one\n    - deep"
    assert qr.strip_citation_markup(nested) == nested
    for a in qr.golden_answers(GOLDEN):  # golden answers carry no inline markers: stripping is a no-op
        assert qr.strip_citation_markup(a["answer_markdown"]) == a["answer_markdown"].strip()


def test_judge_prompt_blind_over_every_planned_prompt() -> None:
    rec, _ = _session(qr.NEW_RUNG, scale=3)
    items = qr.judge_items("all", golden=GOLDEN, records=[rec])
    assert len(items) == 24 + 8
    plan = qr.plan_judge_calls(items)
    docs = qr.judge_documents_text()
    for d in C1.hydrated_docs:
        assert d["full_text"] in docs
    for name in ("Kaveri", "Narmada", "DOC-08", "DOC-15"):
        assert name not in docs
    for p in plan:
        assert qr.blinding_violations(p["system"], p["user"], [p["question"], p["answer_for_judge"]]) == []
        assert p["system"][1]["cache_control"] == {"type": "ephemeral"} and "cache_control" not in p["system"][0]
        assert not re.search(r"\[\d+\]", p["user"])
        assert p["rung_id"] not in json.dumps([p["system"], p["user"]])
    assert len({p["call_id"] for p in plan}) == len(plan)
    assert len({json.dumps(p["system"]) for p in plan}) == 1  # one shared cached prefix
    bad = qr.blinding_violations(p["system"], p["user"] + " from the hybrid rung", [p["question"], p["answer_for_judge"]])
    assert "hybrid" in bad and "rung" in bad


def test_judge_schema_and_parse() -> None:
    good = {"correctness": {"score": 4, "justification": "x"}, "completeness": {"score": 5, "justification": "y"},
            "factual_errors": [{"claim_quote": "a", "problem": "b", "source_quote_or_absent": "ABSENT", "severity": "material"}],
            "answers_the_question": "yes"}
    assert qr.parse_judge_output(json.dumps(good)) == good
    with pytest.raises(qr.JudgeOutputError):
        qr.parse_judge_output(json.dumps({**good, "correctness": {"score": 6, "justification": "x"}}))
    with pytest.raises(qr.JudgeOutputError):
        qr.parse_judge_output("not json")
    assert qr.JUDGE_SCHEMA["properties"]["answers_the_question"]["enum"] == ["yes", "partly", "no"]


def _judge_fake(order: list[str], *, fail: bool = False, stop: str = "end_turn"):
    good = {"correctness": {"score": 4, "justification": "x"}, "completeness": {"score": 3, "justification": "y"},
            "factual_errors": [], "answers_the_question": "partly"}
    state = {"n": 0}

    async def call(*, system: list[dict[str, Any]], user: str, schema: dict[str, Any], max_tokens: int) -> qr.JudgeResponse:
        state["n"] += 1
        order.append(f"start{state['n']}")
        await asyncio.sleep(0.001)
        order.append(f"end{state['n']}")
        if fail:
            raise RuntimeError("judge down")
        first = state["n"] == 1
        return qr.JudgeResponse(model_id=qr.JUDGE_MODEL, stop_reason=stop, input_tokens=800, output_tokens=1500, thinking_tokens=900,
                                cache_creation_tokens=21000 if first else 0, cache_read_tokens=0 if first else 21000,
                                latency_ms=5, raw_text=json.dumps(good))

    return call


def test_judge_warm_first_then_fan_out_and_resume() -> None:
    plan = qr.plan_judge_calls(qr.judge_items("golden", golden=GOLDEN))[:6]
    order: list[str] = []
    recs: list[dict[str, Any]] = []
    res = run(qr.run_judge_plan(plan, judge_call=_judge_fake(order), guard=qr.JudgeBudgetGuard(100), on_record=recs.append, concurrency=4))
    assert order[:2] == ["start1", "end1"] and res["ok"] == 6
    assert recs[0]["cache_creation_tokens"] == 21000 and all(r["cache_read_tokens"] for r in recs[1:])
    assert qr.select_pending_judgements(plan, recs) == []
    changed = [{**p, "answer_sha256": "different"} if i == 0 else p for i, p in enumerate(plan)]
    assert len(qr.select_pending_judgements(changed, recs)) == 1


def test_judge_errors_and_budget() -> None:
    plan = qr.plan_judge_calls(qr.judge_items("golden", golden=GOLDEN))[:3]
    recs: list[dict[str, Any]] = []
    run(qr.run_judge_plan(plan, judge_call=_judge_fake([], fail=True), guard=qr.JudgeBudgetGuard(100), on_record=recs.append))
    assert all(r["status"] == "error" and r["error_type"] == "api_error" for r in recs)
    recs2: list[dict[str, Any]] = []
    run(qr.run_judge_plan(plan[:1], judge_call=_judge_fake([], stop="max_tokens"), guard=qr.JudgeBudgetGuard(100), on_record=recs2.append))
    assert recs2[0]["status"] == "error" and recs2[0]["error_type"] == "stop_reason"
    res = run(qr.run_judge_plan(plan, judge_call=_judge_fake([]), guard=qr.JudgeBudgetGuard(0.01), on_record=lambda r: None))
    assert res["budget_stopped"] and res["launched"] == 0
    est = qr.estimate_judge_plan(plan)
    assert est["worst_case_usd"] > est["typical_usd"] > 0
    assert qr.judge_cost_usd(1_000_000, 0) == pytest.approx(4.0) and qr.judge_cost_usd(0, 1_000_000) == pytest.approx(20.0)


def test_judge_cli_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mod = _load_script("cat4_quality_judge")
    rc = run(mod.main(mod.parse_args(["--scope", "golden", "--dry-run", "--runs", str(tmp_path / "r.jsonl"),
                                      "--out", str(tmp_path / "j.jsonl")])))
    text = capsys.readouterr().out
    assert rc == 0 and "Blinding check passed on all 24 prompts" in text and "typical" in text


# --------------------------------------------------------------------------------------------------
# Golden scoring + analysis
# --------------------------------------------------------------------------------------------------


def test_golden_answers_shape_and_scores() -> None:
    ga = qr.golden_answers(GOLDEN)
    assert len(ga) == 24
    assert {a["rung_id"] for a in ga} == set(qr.APP_RUNG_IDS)
    hyb = [a for a in ga if a["rung_id"] == "hybrid_rag_rerank_citations"]
    assert all(len(a["retrieval"]["selected_chunk_ids"]) == 5 and a["calls"][0]["role"] == "rerank" for a in hyb)
    s = qr.summarise([], keys=KEYS, golden=GOLDEN)
    g = s["original_capture"]["groups"]
    assert g["naive_full_corpus"]["fact_recall"]["total"] == len(KEYS["facts"])
    assert g["naive_full_corpus"]["citations_requested"] is False
    assert g["cached_full_corpus_citations"]["zero_citation_answers"]["hits"] == 0
    assert g["cached_full_corpus_citations"]["cache_write_premium_usd"] > 0
    assert s["original_capture"]["break_even"][0]["a"] == "cached_full_corpus_citations"
    assert s["rerun"]["groups"] == {}


def _write_runs(path: Path) -> list[dict[str, Any]]:
    recs = []
    for rung in qr.RUNG_IDS:
        for scale in (1, 3):
            r, _ = _session(rung, scale=scale)
            recs.append(r)
    err, _ = _session("naive_full_corpus", scale=3, fakes=Fakes(fail_at=2))
    recs.append(err)
    path.write_text("".join(json.dumps(r) + "\n" for r in recs))
    return recs


def test_analysis_without_and_with_rerun_and_judgements(tmp_path: Path) -> None:
    mod = _load_script("analyze_cat4_quality")
    md = tmp_path / "out.md"
    assert mod.main(["--runs", str(tmp_path / "none.jsonl"), "--judgements", str(tmp_path / "none2.jsonl"), "--out-md", str(md)]) == 0
    text = md.read_text()
    assert "Original capture" in text and "No ok rerun sessions yet" in text and "For lead review" in text and "Data quality" in text
    assert json.loads(md.with_suffix(".json").read_text())["rerun"]["ok_sessions_used"] == 0

    runs = tmp_path / "runs.jsonl"
    recs = _write_runs(runs)
    items = qr.judge_items("all", golden=GOLDEN, records=recs)
    plan = qr.plan_judge_calls(items)
    jrecs: list[dict[str, Any]] = []
    run(qr.run_judge_plan(plan, judge_call=_judge_fake([]), guard=qr.JudgeBudgetGuard(1000), on_record=jrecs.append))
    jpath = tmp_path / "j.jsonl"
    jpath.write_text("".join(json.dumps(r) + "\n" for r in jrecs))
    assert mod.main(["--runs", str(runs), "--judgements", str(jpath), "--out-md", str(md)]) == 0
    s = json.loads(md.with_suffix(".json").read_text())
    assert s["rerun"]["ok_sessions_used"] == 8 and len(s["rerun"]["groups"]) == 8
    assert len(s["rerun"]["data_quality"]["error_sessions"]) == 1
    g = s["rerun"]["groups"]["cached_rerank_hybrid|3"]
    assert g["judge"]["judgements"] == 8 and g["judge"]["correctness_mean"] == 4
    assert g["cost_per_question"]["billed"]["haiku"] > 0 and g["cost_per_question"]["billed"]["sonnet"] > 0
    assert {r["a"] for r in s["rerun"]["break_even"]["3"]} == {"cached_full_corpus_citations", "cached_rerank_hybrid"}
    assert len(s["rerun"]["break_even"]["3"]) == 3
    assert s["original_capture"]["groups"]["naive_full_corpus"]["judge"]["judgements"] == 8
    text = md.read_text()
    assert "R4 cached-rerank · s3" in text and "Break-even" in text
    assert not re.search(r'"[a-z_]*(usd|cost)[a-z_]*":', json.dumps(recs))  # records hold tokens, never dollars


# --------------------------------------------------------------------------------------------------
# Supplier scope line
# --------------------------------------------------------------------------------------------------

from app.data.cat4_fixtures import DEAL_ROOM_PROFILE  # noqa: E402

EXPECTED_SCOPE = (f"Deal room under audit: {DEAL_ROOM_PROFILE['deal_room_id']} (supplier: "
                  f"{DEAL_ROOM_PROFILE['supplier_legal_name']}). Answer for this supplier's contracts only.")


def test_scope_line_built_from_profile() -> None:
    assert qr.scope_line() == EXPECTED_SCOPE
    assert qr.scope_line() == ("Deal room under audit: DR-NM-DECCAN-2026-Q4 (supplier: Deccan Smart Appliances & Energy "
                               "Pvt. Ltd.). Answer for this supplier's contracts only.")
    assert qr.scoped_question("Q?") == EXPECTED_SCOPE + "\n\nQ?"
    for f in KEYS["facts"]:  # the scope line itself never satisfies a key fact
        assert not qr.text_matches(qr.scope_line(), qr.fact_alternatives(f)), f["id"]


@pytest.mark.parametrize("rung", qr.RUNG_IDS)
@pytest.mark.parametrize("scale", qr.SCALES)
def test_scoped_question_in_every_input(rung: str, scale: int, monkeypatch: pytest.MonkeyPatch) -> None:
    bm25_queries: list[str] = []
    real_bm25 = qr.rank_chunks_bm25

    def spy(query: str, chunks: Any, top_k: int):
        bm25_queries.append(query)
        return real_bm25(query, chunks, top_k=top_k)

    monkeypatch.setattr(qr, "rank_chunks_bm25", spy)
    rec, f = _session(rung, scale=scale)
    order = [(p["id"], q) for p in CAT4_PRESETS for q in p["questions"]]
    expected = [EXPECTED_SCOPE + "\n\n" + q["question"] for _, q in order]
    assert rec["settings"]["question_scope_line"] == EXPECTED_SCOPE
    assert [a["question"] for a in rec["answers"]] == [q["question"] for _, q in order]
    assert [a["question_as_asked"] for a in rec["answers"]] == expected
    assert [kw["user_question"] for r, kw in f.calls if r == "synthesis"] == expected
    reranks = [kw for r, kw in f.calls if r == "rerank"]
    if rung == "hybrid_rag_rerank_citations":
        assert bm25_queries == expected
        assert all(kw["rerank_payload"].count(e) == 1 for kw, e in zip(reranks, expected))
    elif rung == qr.NEW_RUNG:
        assert bm25_queries == []
        assert all(e in kw["user_content"][1]["text"] and EXPECTED_SCOPE not in kw["user_content"][0]["text"]
                   for kw, e in zip(reranks, expected))
    else:
        assert bm25_queries == [] and reranks == []


def test_golden_path_unscoped_and_judge_question_as_asked() -> None:
    ga = qr.golden_answers(GOLDEN)
    assert all(EXPECTED_SCOPE not in a["question"] and "question_as_asked" not in a for a in ga)
    rec, _ = _session("hybrid_rag_rerank_citations", scale=3)
    plan = qr.plan_judge_calls(qr.judge_items("all", golden=GOLDEN, records=[rec]))
    gold = [p for p in plan if p["source"] == "golden"]
    rer = [p for p in plan if p["source"] == "rerun"]
    assert len(gold) == 24 and len(rer) == 8
    assert all(EXPECTED_SCOPE not in p["user"] and p["question"] == Q_SPECS[(p["preset_id"], p["question_id"])]["question"] for p in gold)
    assert all(p["user"].startswith("<question>\n" + EXPECTED_SCOPE + "\n\n") for p in rer)
    for p in plan:
        assert qr.blinding_violations(p["system"], p["user"], [p["question"], p["answer_for_judge"]]) == []
    # the scope line adds no forbidden term even when not cut out
    assert qr.blinding_violations([{"text": ""}], EXPECTED_SCOPE, []) == []
    # golden scoring unchanged by the scope line
    s = qr.summarise([], keys=KEYS, golden=GOLDEN)["original_capture"]["groups"]
    assert s["naive_full_corpus"]["fact_recall"]["hits"] == 52 and s["hybrid_rag_rerank_citations"]["fact_recall"]["hits"] == 51


def test_judge_cli_default_cap_16() -> None:
    assert _load_script("cat4_quality_judge").parse_args([]).max_usd == 16.0


# --------------------------------------------------------------------------------------------------
# Synthesis output cap 4096 + superseded sessions
# --------------------------------------------------------------------------------------------------


def _at_cap(rec: dict[str, Any], cap: int) -> dict[str, Any]:
    out = json.loads(json.dumps(rec))
    out["settings"]["synth_max_tokens"] = cap
    for a in out["answers"]:
        for c in a["calls"]:
            if c["role"] == "synthesis":
                c["max_tokens"] = cap
    return out


@pytest.mark.parametrize("rung", qr.RUNG_IDS)
@pytest.mark.parametrize("scale", qr.SCALES)
def test_synthesis_cap_4096_every_rung_and_scale_rerank_unchanged(rung: str, scale: int) -> None:
    assert qr.SYNTH_MAX_TOKENS == 4096 and qr.RERANK_MAX_TOKENS == 800
    rec, f = _session(rung, scale=scale)
    assert rec["settings"]["synth_max_tokens"] == 4096 and rec["settings"]["rerank_max_tokens"] == 800
    assert all(kw["max_tokens"] == 4096 for r, kw in f.calls if r == "synthesis")
    assert all(kw["max_tokens"] == 800 for r, kw in f.calls if r == "rerank")
    assert all(c["max_tokens"] == (4096 if c["role"] == "synthesis" else 800) for a in rec["answers"] for c in a["calls"])


def test_superseded_cap_key_is_pending_again() -> None:
    rec, _ = _session("naive_full_corpus")
    old = _at_cap(rec, 2048)
    key = ("naive_full_corpus", 1, 0)
    assert not qr.is_current_settings(old) and qr.is_current_settings(rec)
    assert qr.select_pending([key], [old]) == [key]
    assert qr.select_pending([key], [old, rec]) == []
    assert qr.select_pending([key], [{k: v for k, v in rec.items() if k != "settings"}]) == [key]  # no settings = superseded
    assert qr.latest_ok_sessions([rec, old]) == [rec]  # a later superseded record never replaces a current one
    assert qr.judge_items("rerun", golden=GOLDEN, records=[old]) == []


def test_rerun_cli_treats_superseded_as_pending(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rec, _ = _session("naive_full_corpus")
    out = tmp_path / "runs.jsonl"
    out.write_text(json.dumps(_at_cap(rec, 2048)) + "\n")
    mod = _load_script("cat4_quality_rerun")
    run(mod.main(mod.parse_args(["--dry-run", "--out", str(out), "--rungs", "naive_full_corpus", "--scales", "1", "--repeats", "1"])))
    text = capsys.readouterr().out
    assert "0 already ok, 1 pending" in text and "Superseded records" in text


def test_analysis_excludes_superseded_and_lists_them(tmp_path: Path) -> None:
    runs = tmp_path / "runs.jsonl"
    cur, _ = _session("cached_full_corpus_citations")
    old = _at_cap(cur, 2048)
    for a in old["answers"]:  # make the superseded one distinguishable: truncated answers
        for c in a["calls"]:
            c["stop_reason"] = "max_tokens"
    old_only, _ = _session("naive_full_corpus", scale=3)
    old_only = _at_cap(old_only, 2048)
    runs.write_text("".join(json.dumps(r) + "\n" for r in (old, cur, old_only)))
    mod = _load_script("analyze_cat4_quality")
    md = tmp_path / "a.md"
    assert mod.main(["--runs", str(runs), "--judgements", str(tmp_path / "none.jsonl"), "--out-md", str(md)]) == 0
    s = json.loads(md.with_suffix(".json").read_text())
    rr = s["rerun"]
    assert rr["ok_sessions_used"] == 1 and rr["superseded_record_count"] == 2
    assert set(rr["groups"]) == {"cached_full_corpus_citations|1"}
    assert all(not k.startswith("naive_full_corpus|3") for k in rr["per_question"])
    assert rr["data_quality"]["non_end_turn_calls"] == []  # the superseded truncations are not counted as current data
    sup = rr["data_quality"]["superseded_sessions"]
    assert {(x["rung_id"], x["scale"], x["synth_max_tokens"]) for x in sup} == {("cached_full_corpus_citations", 1, 2048), ("naive_full_corpus", 3, 2048)}
    text = md.read_text()
    assert "superseded: recorded at a different output cap" in text and "superseded 2" in text


def test_worst_case_estimate_uses_new_cap() -> None:
    cpt = qr.calibrate_chars_per_token(GOLDEN)
    for rung in qr.RUNG_IDS:
        e = qr.estimate_session(rung, 1, cpt)
        assert e["worst_case_usd"] - e["typical_usd"] >= 8 * (4096 - 1050) * 10.0 / 1e6 - 1e-9


# --------------------------------------------------------------------------------------------------
# Regression: contamination produced by the real scorer flows through summarise() / review / render
# --------------------------------------------------------------------------------------------------

REAL_RUNS = BACKEND_DIR / "experiments" / "cat4_quality" / "runs.jsonl"
REAL_JUDGEMENTS = BACKEND_DIR / "experiments" / "cat4_quality" / "judgements.jsonl"


class ContaminatingFakes(Fakes):
    """Synthesis states Kaveri's cap for audit-01/q1 (once without and once with the supplier named)."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text

    async def synth(self, **kw: Any) -> AnthropicRawResult:
        r = await super().synth(**kw)
        r.raw_text = self.text
        return r


def test_summarise_with_contamination_from_real_scorer(tmp_path: Path) -> None:
    text = "Liability cap: **INR 3,60,00,000** per the MSA (Clause 9.1)."
    rec, _ = _session("cached_full_corpus_citations", scale=3, fakes=ContaminatingFakes(text))
    # the real scorer produces the hits; nothing here is hand-built
    s = qr.score_answer(rec["answers"][0], rung_id=rec["rung_id"], corpus=C3, keys=KEYS, contamination=qr.build_contamination_index(KEYS))
    hit = s["contamination"]["distractor_values"][0]
    assert set(hit) == {"fact_id", "supplier", "value", "attributed_to_distractor"} and hit["supplier"] == "kaveri"
    assert hit["attributed_to_distractor"] is False
    summary = qr.summarise([rec], keys=KEYS, golden=GOLDEN)
    rv = summary["for_lead_review"]["contaminated_answers"]
    assert rv and rv[0]["question"] == "audit-01/q1"
    assert "3,60,00,000" in rv[0]["distractor_values"][0]["answer_excerpt"]
    g = summary["rerun"]["groups"]["cached_full_corpus_citations|3"]
    assert g["value_contaminated_answers"]["hits"] >= 1 and g["value_contaminated_unattributed_answers"]["hits"] >= 1
    assert g["answers_whose_synthesis_saw_distractor_text"]["hits"] == 8
    runs = tmp_path / "runs.jsonl"
    runs.write_text(json.dumps(rec) + "\n")
    mod = _load_script("analyze_cat4_quality")
    md = tmp_path / "a.md"
    assert mod.main(["--runs", str(runs), "--judgements", str(tmp_path / "none.jsonl"), "--out-md", str(md)]) == 0
    out = md.read_text()
    assert "Contaminated-answer excerpts" in out and "`3,60,00,000` (kaveri)" in out


def test_attribution_when_answer_names_the_other_supplier() -> None:
    idx = qr.build_contamination_index(KEYS)
    a = _answer("DOC-08 (Kaveri) has a cap of INR 3,60,00,000, which is excluded; Deccan's cap is INR 4.50 Crore.")
    s = qr.score_answer(a, rung_id="naive_full_corpus", corpus=C3, keys=KEYS, contamination=idx)
    hits = s["contamination"]["distractor_values"]
    assert hits and all(h["attributed_to_distractor"] for h in hits)
    assert s["contamination"]["contaminated"]  # still counted; attribution is reported alongside
    pooled = qr.pool_scores([s])
    assert pooled["value_contaminated_answers"]["hits"] == 1 and pooled["value_contaminated_unattributed_answers"]["hits"] == 0
    assert s["contamination"]["synthesis_saw_distractor_text"] is False  # _answer has no full-corpus mode


def test_answer_excerpt_tolerates_markdown_and_spacing() -> None:
    assert qr.answer_excerpt("x **INR 3,60,00,000** y", "3,60,00,000")
    assert qr.answer_excerpt("rate 97.8 %", "97.8%")
    assert qr.answer_excerpt("nothing here", "97.8%") is None


def test_judgements_attach_only_to_the_same_answer() -> None:
    rec, _ = _session("naive_full_corpus")
    plan = qr.plan_judge_calls(qr.judge_items("rerun", golden=GOLDEN, records=[rec]))
    jrecs: list[dict[str, Any]] = []
    run(qr.run_judge_plan(plan, judge_call=_judge_fake([]), guard=qr.JudgeBudgetGuard(100), on_record=jrecs.append))
    rerun_of_same_key = json.loads(json.dumps(rec))
    rerun_of_same_key["run_id"] = "another-run"
    for a in rerun_of_same_key["answers"]:
        a["answer_markdown"] = "a different answer"
    s = qr.summarise([rerun_of_same_key], keys=KEYS, golden=GOLDEN, judgements=jrecs)
    assert s["rerun"]["groups"]["naive_full_corpus|1"]["judge"] is None
    dq = s["rerun"]["data_quality"]
    assert len(dq["judgements_not_matching_a_scored_answer"]) == 8 and dq["scored_answers_without_judgement"] == 32
    s2 = qr.summarise([rec], keys=KEYS, golden=GOLDEN, judgements=jrecs)
    assert s2["rerun"]["groups"]["naive_full_corpus|1"]["judge"]["judgements"] == 8
    assert s2["rerun"]["data_quality"]["judgements_not_matching_a_scored_answer"] == []


def test_not_requested_citation_columns_render_as_dash(tmp_path: Path) -> None:
    mod = _load_script("analyze_cat4_quality")
    md = tmp_path / "a.md"
    mod.main(["--runs", str(tmp_path / "none.jsonl"), "--judgements", str(tmp_path / "none.jsonl"), "--out-md", str(md)])
    row = next(line for line in md.read_text().splitlines() if line.startswith("| R1 naive | 8 |"))
    assert "n/a" not in row and row.count("—") >= 4


@pytest.mark.skipif(not REAL_RUNS.is_file(), reason="no live Category 4 rerun data")
def test_smoke_analysis_on_real_data(tmp_path: Path) -> None:
    before = {p: p.stat().st_mtime_ns for p in (REAL_RUNS, REAL_JUDGEMENTS) if p.is_file()}
    mod = _load_script("analyze_cat4_quality")
    md = tmp_path / "real.md"
    args = ["--runs", str(REAL_RUNS), "--out-md", str(md)]
    if REAL_JUDGEMENTS.is_file():
        args += ["--judgements", str(REAL_JUDGEMENTS)]
    else:
        args += ["--judgements", str(tmp_path / "none.jsonl")]
    assert mod.main(args) == 0
    s = json.loads(md.with_suffix(".json").read_text())
    assert s["rerun"]["ok_sessions_used"] >= 1 and s["rerun"]["groups"]
    text = md.read_text()
    cells = [c.strip() for line in text.splitlines() if line.startswith("|") for c in line.split("|")]
    assert not {"None", "nan", "$nan", "None/None"} & set(cells)
    assert not any(c.startswith("None") for c in cells)
    assert "## Data quality" in text and "Break-even" in text
    assert {p: p.stat().st_mtime_ns for p in before} == before  # inputs are read-only
