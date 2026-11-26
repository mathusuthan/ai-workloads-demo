"""Category 4 gap fixes (offline, no network): the supplier-scope line in the app's live and ad-hoc paths, the
`scoped_absence` answer-format variant in the quality-rerun harness, and the absence-claim detector."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat4_rag import answer_formats as af  # noqa: E402
from app.archetypes.cat4_rag import quality_rerun as qr  # noqa: E402
from app.archetypes.cat4_rag import runner  # noqa: E402
from app.archetypes.cat4_rag import scope  # noqa: E402
from app.archetypes.cat4_rag.prompts import get_cat4_haiku_reranker_system_prompt, get_cat4_synthesis_system_prompt  # noqa: E402
from app.core.anthropic_service import AnthropicRawResult  # noqa: E402
from app.core.credit_shield import ResolvedCredentials, credit_shield  # noqa: E402
from app.data.cat4_fixtures import CAT4_PRESETS, hydrate_deal_room_index  # noqa: E402
from app.main import app  # noqa: E402

REAL_RUNS = BACKEND_DIR / "experiments" / "cat4_quality" / "runs.jsonl"
REAL_JUDGEMENTS = BACKEND_DIR / "experiments" / "cat4_quality" / "judgements.jsonl"
HAVE_REAL = REAL_RUNS.is_file() and REAL_JUDGEMENTS.is_file()
APP_RUNGS = ("naive_full_corpus", "cached_full_corpus_citations", "hybrid_rag_rerank_citations")
SCOPE = ("Deal room under audit: DR-NM-DECCAN-2026-Q4 (supplier: Deccan Smart Appliances & Energy Pvt. Ltd.). "
         "Answer for this supplier's contracts only.")
GOLDEN = qr.load_golden()


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, BACKEND_DIR / "scripts" / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Calls:
    """Fake call wrappers: record every input; the reranker keeps the first 5 candidates it is shown."""

    def __init__(self, answer: str = "The documents specify no banking NOC or escrow gate.") -> None:
        self.synth: list[dict[str, Any]] = []
        self.rerank: list[dict[str, Any]] = []
        self.answer = answer

    async def synth_call(self, **kw: Any) -> AnthropicRawResult:
        self.synth.append(kw)
        return AnthropicRawResult("claude-sonnet-5-5", 5, 1000, 400, 0, 0, self.answer, {"segments": [], "citations": []},
                                  stop_reason="end_turn")

    async def rerank_call(self, **kw: Any) -> AnthropicRawResult:
        self.rerank.append(kw)
        text = kw.get("rerank_payload") or kw["user_content"][0]["text"]
        ids = re.findall(r"CHUNK_ID: (\S+)", text)[:5]
        return AnthropicRawResult("claude-haiku-5-5", 5, 900, 100, 0, 0, "{}",
                                  {"selected_chunks": [{"chunk_id": i, "relevance_score": 90, "rationale": "x"} for i in ids]},
                                  stop_reason="end_turn")


# ------------------------------------------------------------------------ Gap 1: scope line in the app


@pytest.fixture()
def fake_app_calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Calls, list[str]]:
    monkeypatch.setenv("NOVAMART_TRACES_DIR", str(tmp_path / "traces"))
    c = Calls()
    bm25: list[str] = []
    real = runner.rank_chunks_bm25

    def spy(query: str, chunks: Any, top_k: int):
        bm25.append(query)
        return real(query, chunks, top_k=top_k)

    monkeypatch.setattr(runner, "run_cat4_rag_synthesis", c.synth_call)
    monkeypatch.setattr(runner, "run_cat4_haiku_reranker", c.rerank_call)
    monkeypatch.setattr(runner, "rank_chunks_bm25", spy)
    monkeypatch.setattr(credit_shield, "resolve_live_credentials",
                        lambda *a, **k: ResolvedCredentials("k", None, "byok", "none", False))
    return c, bm25


@pytest.mark.parametrize("rung", APP_RUNGS)
def test_live_question_is_scoped_in_every_input(rung: str, fake_app_calls: tuple[Calls, list[str]]) -> None:
    c, bm25 = fake_app_calls
    docs, chunks, total = hydrate_deal_room_index()
    q = CAT4_PRESETS[0]["questions"][1]
    scoped = SCOPE + "\n\n" + q["question"]
    q_res, raw = asyncio.run(runner._run_live_cat4_query_for_rung(q_idx=0, q_spec=q, rung_id=rung, hydrated_docs=docs,
                                                                  flat_chunks=chunks, total_corpus_chars=total, api_key="k"))
    assert [kw["user_question"] for kw in c.synth] == [scoped]  # synthesis message
    assert q_res.question == q["question"] and q_res.question_as_asked == scoped == raw["question_as_asked"]
    if rung == "hybrid_rag_rerank_citations":
        assert bm25 == [scoped]  # BM25 query
        assert len(c.rerank) == 1 and c.rerank[0]["rerank_payload"].count(scoped) == 1  # reranker query
    else:
        assert bm25 == [] and c.rerank == []


def test_live_audit_and_adhoc_endpoints_send_the_scoped_question(fake_app_calls: tuple[Calls, list[str]]) -> None:
    c, bm25 = fake_app_calls
    client = TestClient(app)
    resp = client.post("/api/cat4/run", json={"preset_id": "audit-02", "mode": "live"})
    assert resp.status_code == 200, resp.text
    qs = [q["question"] for q in CAT4_PRESETS[1]["questions"]]
    expected = [SCOPE + "\n\n" + q for q in qs]
    assert sorted(kw["user_question"] for kw in c.synth) == sorted(expected * 3)  # 3 rungs x 4 questions
    assert bm25 == expected and [kw["rerank_payload"].count(e) for kw, e in zip(c.rerank, expected)] == [1] * 4
    for r in resp.json()["results"]:
        assert [q["question_as_asked"] for q in r["queries"]] == expected and [q["question"] for q in r["queries"]] == qs

    c.synth.clear(), c.rerank.clear(), bm25.clear()
    ask = "Which clause controls the liability cap for Deccan?"
    resp = client.post("/api/cat4/query", json={"preset_id": "audit-01", "question": ask, "mode": "live"})
    assert resp.status_code == 200, resp.text
    assert [kw["user_question"] for kw in c.synth] == [SCOPE + "\n\n" + ask] * 3
    assert bm25 == [SCOPE + "\n\n" + ask] and c.rerank[0]["rerank_payload"].count(SCOPE + "\n\n" + ask) == 1
    assert {r["queries"][0]["question_as_asked"] for r in resp.json()["results"]} == {SCOPE + "\n\n" + ask}
    assert resp.json()["question"] == ask


def test_live_and_adhoc_prompt_per_rung(fake_app_calls: tuple[Calls, list[str]], monkeypatch: pytest.MonkeyPatch) -> None:
    """Rung 3 gets the scoped_absence prompt; rungs 1-2 the legacy prompt byte for byte (preset and ad-hoc)."""
    c, _ = fake_app_calls
    variant = af.synthesis_system_prompt(with_citations=True, answer_format="scoped_absence")
    legacy = {True: get_cat4_synthesis_system_prompt(with_citations=True), False: get_cat4_synthesis_system_prompt(with_citations=False)}
    assert _sha(legacy[True]) == PINNED["synth_cit"] and _sha(legacy[False]) == PINNED["synth_nocit"]
    seen: dict[str, set[str]] = {}
    real = runner.rung_synthesis_system_prompt

    def spy(rung_id: str, *, with_citations: bool) -> str:
        out = real(rung_id, with_citations=with_citations)
        seen.setdefault(rung_id, set()).add(out)
        return out

    monkeypatch.setattr(runner, "rung_synthesis_system_prompt", spy)
    client = TestClient(app)
    for body, path in (({"preset_id": "audit-01", "mode": "live"}, "/api/cat4/run"),
                       ({"preset_id": "audit-01", "question": "Which clause controls the cap?", "mode": "live"}, "/api/cat4/query")):
        seen.clear(), c.synth.clear()
        resp = client.post(path, json=body)
        assert resp.status_code == 200, resp.text
        assert seen["naive_full_corpus"] == {legacy[False]}
        assert seen["cached_full_corpus_citations"] == {legacy[True]}
        assert seen["hybrid_rag_rerank_citations"] == {variant}
        assert {kw["system_prompt"] for kw in c.synth} == {legacy[False], legacy[True], variant}
        fmts = {r["rung_id"]: r["answer_format"] for r in resp.json()["results"]}
        assert fmts == {"naive_full_corpus": "original", "cached_full_corpus_citations": "original",
                        "hybrid_rag_rerank_citations": "scoped_absence"}
    assert af.ADOPTED_ANSWER_FORMAT["cached_rerank_hybrid"] == "scoped_absence"
    assert af.LEGACY_ANSWER_FORMAT == "original"


def test_replay_notes_state_before_and_after(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NOVAMART_TRACES_DIR", str(tmp_path / "traces"))
    data = TestClient(app).post("/api/cat4/run", json={"preset_id": "audit-02", "mode": "replay"}).json()
    by = {r["rung_id"]: r for r in data["results"]}
    pf = data["quality_portfolio"]
    before = next(c for c in pf["cells"] if c["rung_id"] == "hybrid_rag_rerank_citations" and c["scale"] == 3 and not c["adopted"])
    now = next(c for c in pf["cells"] if c["rung_id"] == "hybrid_rag_rerank_citations" and c["scale"] == 3 and c["adopted"])
    note = by["hybrid_rag_rerank_citations"]["architectural_notes"][3]
    assert "not in the text provided" in note and "not changed or re-measured" in note
    assert (f"{before['answers_with_material_error']['hits']} → {now['answers_with_material_error']['hits']}" in note
            and f"{before['correctness_mean']:.2f} → {now['correctness_mean']:.2f}" in note)
    for rid in ("naive_full_corpus", "cached_full_corpus_citations"):
        assert by[rid]["architectural_notes"][3].startswith("Prompt not changed")
    assert f"— {before['answers_with_material_error']['hits']}/24 before the retrieval version's answer format changed" in data["rag_callout"]
    assert by["hybrid_rag_rerank_citations"]["answer_format"] == "scoped_absence"


def test_replay_mode_does_not_use_the_live_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NOVAMART_TRACES_DIR", str(tmp_path / "traces"))

    async def boom(**kw: Any) -> AnthropicRawResult:
        raise AssertionError("replay must not call the API")

    monkeypatch.setattr(runner, "run_cat4_rag_synthesis", boom)
    golden = runner.load_cat4_replays()["presets"]["audit-01"]["rungs"]
    data = TestClient(app).post("/api/cat4/run", json={"preset_id": "audit-01", "mode": "replay"}).json()
    for r in data["results"]:
        assert [q["question_as_asked"] for q in r["queries"]] == [q["question_as_asked"] for q in golden[r["rung_id"]]]


# ------------------------------------------------------------------------ Gap 1: the harness is unchanged

# sha256 of the harness's model-facing text, taken before the scope line moved to scope.py
PINNED = {
    "synth_cit": "90aa83317ff7814463c8ad7c18469af3b7e5b63eefaf79ec11f7093b37e059b0",
    "synth_nocit": "026c3fa599de955a880de26253a86a88e7c533265f4f80daef311a0d7806617b",
    "rerank": "64d257ca208ef68319cbaacb75c393cf6c0ae6eb5edfbc0b3dba06cde8bb4d0c",
    "rerank_full": "afefea44b097d92c1e07779ee8b72a704a49d58e72879149f604c11d1a9a12c3",
    "scoped_qs": "39f1b2d3eafbd488a6ade4dda5a839f14685473fc886f864394bade5541ebcdf",
}


def test_harness_prompts_and_scope_line_unchanged_byte_for_byte() -> None:
    assert qr.scope_line is scope.scope_line and qr.scoped_question is scope.scoped_question
    assert scope.scope_line() == SCOPE
    assert _sha(get_cat4_synthesis_system_prompt(with_citations=True)) == PINNED["synth_cit"]
    assert _sha(get_cat4_synthesis_system_prompt(with_citations=False)) == PINNED["synth_nocit"]
    for cit in (True, False):
        assert af.synthesis_system_prompt(with_citations=cit) == get_cat4_synthesis_system_prompt(with_citations=cit)
    assert _sha(get_cat4_haiku_reranker_system_prompt()) == PINNED["rerank"]
    assert _sha(qr.get_full_corpus_reranker_system_prompt()) == PINNED["rerank_full"]
    assert _sha("\x00".join(qr.scoped_question(q["question"]) for _, q in qr.session_questions())) == PINNED["scoped_qs"]


@pytest.mark.skipif(not HAVE_REAL, reason="no Category 4 rerun data")
def test_existing_records_match_the_shared_scope_line_and_stay_current() -> None:
    recs = qr.load_jsonl(REAL_RUNS)
    ok = [r for r in recs if r.get("status") == "ok"]
    assert len(ok) == 36  # 24 original (4 rungs x 2 sizes x 3) + 12 scoped_absence (2 retrieval rungs x 2 x 3)
    assert sorted(qr.answer_format_of(r) for r in ok).count("scoped_absence") == 12
    assert {r["rung_id"] for r in ok if qr.answer_format_of(r) == "scoped_absence"} == {"hybrid_rag_rerank_citations", "cached_rerank_hybrid"}
    for r in ok:
        assert qr.is_current_settings(r)
        if qr.answer_format_of(r) == "original":
            assert "answer_format" not in r["settings"]  # recorded before formats existed
        assert r["settings"]["question_scope_line"] == scope.scope_line()
        assert all(a["question_as_asked"] == scope.scoped_question(a["question"]) for a in r["answers"])
        assert r["corpus"]["fingerprint"] == qr.corpus_fingerprint(qr.build_scaled_corpus(int(r["scale"])))
    assert qr.select_pending(qr.plan_matrix(qr.RUNG_IDS, qr.SCALES, 3), recs) == []
    retr = ["hybrid_rag_rerank_citations", "cached_rerank_hybrid"]
    assert qr.select_pending(qr.plan_matrix(retr, qr.SCALES, 3, "scoped_absence"), recs) == []
    assert len(qr.select_pending(qr.plan_matrix(qr.RUNG_IDS, qr.SCALES, 3, "scoped_absence"), recs)) == 12
    # judge ids: original answers keep the old ids; every answer of the 36 sessions is judged, nothing pending
    plan = qr.plan_judge_calls(qr.judge_items("rerun", records=recs))
    assert len(plan) == 288 and qr.select_pending_judgements(plan, qr.load_jsonl(REAL_JUDGEMENTS)) == []
    assert sum(":scoped_absence:" in p["call_id"] for p in plan) == 96


# ------------------------------------------------------------------------ Gap 2: the prompt variant


@pytest.mark.parametrize("cit", [True, False])
def test_variant_differs_only_in_absence_handling(cit: bool) -> None:
    diff = af.prompt_diff(with_citations=cit).split("\n")
    removed = [line[1:] for line in diff if line.startswith("-") and not line.startswith("---")]
    added = [line[1:] for line in diff if line.startswith("+") and not line.startswith("+++")]
    assert removed == [af.ORIGINAL_GATE_LINE]
    assert added == [af.SCOPED_GATE_LINE, af.PARTIAL_CONTEXT_RULE]
    a = af.synthesis_system_prompt(with_citations=cit).split("\n")
    b = af.synthesis_system_prompt(with_citations=cit, answer_format="scoped_absence").split("\n")
    assert [x for x in b if x not in (af.SCOPED_GATE_LINE, af.PARTIAL_CONTEXT_RULE)] == [x for x in a if x != af.ORIGINAL_GATE_LINE]
    assert b.index(af.PARTIAL_CONTEXT_RULE) == len(b) - 1 and b[-2] == af.LAST_RULE_LINE  # with the other rules
    assert b.index(af.SCOPED_GATE_LINE) == a.index(af.ORIGINAL_GATE_LINE)
    assert '"None stated in the text provided"' in af.SCOPED_GATE_LINE
    assert af.SCOPED_GATE_LINE.startswith("- **Required Sign-Off Gate**: Concrete operational, banking NOC, escrow, or delisting gate before execution")
    with pytest.raises(ValueError):
        af.synthesis_system_prompt(with_citations=cit, answer_format="other")


def _session(rung: str, fmt: str, scale: int = 1, answer: str = "The documents specify no banking NOC or escrow gate.") -> tuple[dict[str, Any], Calls]:
    c = Calls(answer)
    rec = asyncio.run(qr.execute_session(rung_id=rung, scale=scale, repeat_index=0, api_key="k", synth_call=c.synth_call,
                                         rerank_call=c.rerank_call, answer_format=fmt))
    return rec, c


@pytest.mark.parametrize("rung", qr.RUNG_IDS)
def test_variant_session_uses_variant_prompt_and_is_recorded_and_keyed(rung: str) -> None:
    rec, c = _session(rung, "scoped_absence")
    assert rec["status"] == "ok" and rec["settings"]["answer_format"] == "scoped_absence"
    assert rec["settings"]["question_scope_line"] == SCOPE  # the scope line stays as is
    cit = rung != "naive_full_corpus"
    assert {kw["system_prompt"] for kw in c.synth} == {af.synthesis_system_prompt(with_citations=cit, answer_format="scoped_absence")}
    orig, c0 = _session(rung, "original")
    assert {kw["system_prompt"] for kw in c0.synth} == {get_cat4_synthesis_system_prompt(with_citations=cit)}
    assert orig["settings"]["answer_format"] == "original"
    assert [kw["user_question"] for kw in c.synth] == [kw["user_question"] for kw in c0.synth]
    assert qr.record_key(rec) == (rung, 1, 0, "scoped_absence") and qr.record_key(orig) == (rung, 1, 0, "original")
    assert qr.select_pending([(rung, 1, 0, "original")], [rec]) == [(rung, 1, 0, "original")]  # separate keys
    assert qr.select_pending([(rung, 1, 0, "scoped_absence")], [orig]) == [(rung, 1, 0, "scoped_absence")]
    assert qr.select_pending([(rung, 1, 0)], [orig]) == []  # legacy 3-tuple key = original
    assert qr.select_pending([(rung, 1, 0, "scoped_absence")], [rec]) == []
    assert qr.latest_ok_sessions([orig, rec], answer_format="original") == [orig]
    assert qr.latest_ok_sessions([rec, orig]) == [orig, rec]  # original first, then the variant


def test_unknown_format_is_superseded_and_cli_flag() -> None:
    rec, _ = _session("naive_full_corpus", "scoped_absence")
    odd = json.loads(json.dumps(rec))
    odd["settings"]["answer_format"] = "future_format"
    assert not qr.is_current_settings(odd) and qr.is_current_settings(rec)
    assert qr.superseded_sessions([odd])[0]["answer_format"] == "future_format"
    with pytest.raises(ValueError):
        asyncio.run(qr.execute_session(rung_id="naive_full_corpus", scale=1, repeat_index=0, api_key="k", answer_format="x",
                                       synth_call=Calls().synth_call, rerank_call=Calls().rerank_call))
    mod = _load_script("cat4_quality_rerun")
    assert mod.parse_args([]).answer_format == "original"
    assert mod.parse_args(["--answer-format", "scoped_absence"]).answer_format == "scoped_absence"
    with pytest.raises(SystemExit):
        mod.parse_args(["--answer-format", "nope"])


def test_run_sessions_passes_the_format_through() -> None:
    c = Calls()
    seen: list[dict[str, Any]] = []
    plan = qr.plan_matrix(["naive_full_corpus"], (1,), 2, "scoped_absence")
    asyncio.run(qr.run_sessions(plan, api_key="k", guard=qr.BudgetGuard(100), worst_case_usd=lambda k: 0.1,
                                on_record=seen.append, synth_call=c.synth_call, rerank_call=c.rerank_call))
    assert sorted(qr.record_key(r) for r in seen) == sorted(plan)
    assert {r["settings"]["answer_format"] for r in seen} == {"scoped_absence"}


def _judge_all(recs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    plan = qr.plan_judge_calls(qr.judge_items("rerun", records=recs))
    out: list[dict[str, Any]] = []
    good = {"correctness": {"score": 3, "justification": "x"}, "completeness": {"score": 4, "justification": "y"},
            "factual_errors": [{"claim_quote": "The documents specify no banking NOC or escrow gate.", "problem": "SL.1 has one",
                                "source_quote_or_absent": "certified copy of State Bank of India's written No Objection",
                                "severity": "material"}],
            "answers_the_question": "partly"}

    async def call(*, system: Any, user: str, schema: Any, max_tokens: int) -> qr.JudgeResponse:
        return qr.JudgeResponse(model_id=qr.JUDGE_MODEL, stop_reason="end_turn", input_tokens=10, output_tokens=10, thinking_tokens=0,
                                cache_creation_tokens=0, cache_read_tokens=5, latency_ms=1, raw_text=json.dumps(good))

    asyncio.run(qr.run_judge_plan(plan, judge_call=call, guard=qr.JudgeBudgetGuard(100), on_record=out.append))
    return plan, out


def test_variant_judged_on_same_path_with_format_in_id_and_grouped_separately() -> None:
    orig, _ = _session("hybrid_rag_rerank_citations", "original")
    var, _ = _session("hybrid_rag_rerank_citations", "scoped_absence", answer="Required Sign-Off Gate: None stated in the text provided.")
    plan, judged = _judge_all([orig, var])
    ids = {f: [p["call_id"] for p in plan if p["answer_format"] == f] for f in ("original", "scoped_absence")}
    assert len(ids["original"]) == len(ids["scoped_absence"]) == 8
    assert all(":scoped_absence:" in i for i in ids["scoped_absence"]) and all(":scoped_absence:" not in i for i in ids["original"])
    assert ids["original"][0] == "judge:rerun:hybrid_rag_rerank_citations:s1:r0:audit-01:q1:j0"  # unchanged id format
    p0 = next(p for p in plan if p["answer_format"] == "scoped_absence")
    po = next(p for p in plan if p["answer_format"] == "original" and p["question_id"] == p0["question_id"] and p["preset_id"] == p0["preset_id"])
    assert p0["system"] == po["system"]  # same judge prompt
    assert {j["answer_format"] for j in judged} == {"original", "scoped_absence"}
    s = qr.summarise([orig, var], keys=qr.load_quality_keys(), golden={"presets": {}}, judgements=judged)
    g = s["rerun"]["groups"]
    assert set(g) == {"hybrid_rag_rerank_citations|1", "hybrid_rag_rerank_citations|1|scoped_absence"}
    go, gv = g["hybrid_rag_rerank_citations|1"], g["hybrid_rag_rerank_citations|1|scoped_absence"]
    assert go["judge"]["judgements"] == gv["judge"]["judgements"] == 8
    assert go["absence"]["answers_with_corpus_form_claim"]["hits"] == 8 and gv["absence"]["answers_with_corpus_form_claim"]["hits"] == 0
    assert gv["absence"]["answers_with_scoped_form_claim"]["hits"] == 8 and gv["absence"]["answers_saying_none_stated_in_text_provided"] == 8
    assert go["absence"]["judged_answers_with_unsupported_absence_claim"]["hits"] == 8
    assert go["absence"]["judged_absence_errors_by_form"] == {"corpus": 8}
    assert s["answer_formats"] == ["original", "scoped_absence"]
    assert s["rerun"]["break_even"]["1"] == []  # break-even pairs use original-format groups only


def test_portfolio_shows_retrieval_before_and_now_and_golden_maps_adopted_formats() -> None:
    orig = [_session(r, "original")[0] for r in qr.RUNG_IDS]
    var = [_session(r, "scoped_absence", answer="Gate: None stated in the text provided.")[0] for r in qr.RUNG_IDS]
    keys = qr.load_quality_keys()
    pf = qr.build_quality_portfolio(orig + var, [], keys=keys)
    cells = {(c["rung_id"], c["answer_format"]): c for c in pf["cells"]}
    # full-corpus rungs once (original); retrieval rungs twice (scoped_absence = now, original = before)
    assert set(cells) == {("naive_full_corpus", "original"), ("cached_full_corpus_citations", "original"),
                          ("hybrid_rag_rerank_citations", "scoped_absence"), ("hybrid_rag_rerank_citations", "original"),
                          ("cached_rerank_hybrid", "scoped_absence"), ("cached_rerank_hybrid", "original")}
    assert [c["adopted"] for c in pf["cells"] if c["rung_id"] == "hybrid_rag_rerank_citations"] == [True, False]
    assert cells[("hybrid_rag_rerank_citations", "scoped_absence")]["answers_with_documents_lack_claim"]["hits"] == 0
    assert cells[("hybrid_rag_rerank_citations", "original")]["answers_with_documents_lack_claim"]["hits"] == 8
    assert pf["format_change"]["added"] == [af.SCOPED_GATE_LINE, af.PARTIAL_CONTEXT_RULE]
    assert pf["format_change"]["removed"] == [af.ORIGINAL_GATE_LINE]
    assert "adopted answer format" in pf["break_even_basis"]
    assert pf["golden_mapped"]["answer_formats"]["hybrid_rag_rerank_citations"] == "scoped_absence"
    assert pf["golden_mapped"]["answer_formats"]["naive_full_corpus"] == "original"
    mod = _load_script("build_cat4_golden_from_rerun")
    for rid in qr.APP_RUNG_IDS:
        assert mod.select_session(orig + var, rid)["settings"]["answer_format"] == af.adopted_answer_format(rid)
    with pytest.raises(ValueError, match="scoped_absence"):
        mod.select_session(orig, "hybrid_rag_rerank_citations")  # never falls back to the legacy recording


def test_break_even_uses_adopted_cells(monkeypatch: pytest.MonkeyPatch) -> None:
    g = {"cached_full_corpus_citations|1": {"cost_per_question": {"warm": {"total": 0.01}}, "cache_write_premium_usd": 0.05},
         "hybrid_rag_rerank_citations|1": {"cost_per_question": {"warm": {"total": 0.02}}, "cache_write_premium_usd": 0.0},
         "hybrid_rag_rerank_citations|1|scoped_absence": {"cost_per_question": {"warm": {"total": 0.015}}, "cache_write_premium_usd": 0.0}}
    orig = qr.break_even_tables(g)["1"][0]
    adopted = qr.break_even_tables(g, adopted=True)["1"][0]
    assert orig["per_question_b_usd"] == 0.02 and adopted["per_question_b_usd"] == 0.015
    assert adopted["questions"] > orig["questions"]


def test_validator_ignores_variant_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_script("validate_deck_claims")
    orig, _ = _session("naive_full_corpus", "original")
    var, _ = _session("naive_full_corpus", "scoped_absence", answer="different")
    p = tmp_path / "runs.jsonl"
    p.write_text(json.dumps(orig) + "\n" + json.dumps(var) + "\n")
    monkeypatch.setattr(mod, "CAT4_RERUN", p)
    got = mod.cat4_rerun_records()
    assert got is not None and len(got) == 1 and got[0]["run_id"] == orig["run_id"]


def test_validator_uses_adopted_format_per_rung_and_keeps_before_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_script("validate_deck_claims")
    # the stdlib-only validator carries a copy of the app's map; it must not drift
    assert mod.CAT4_ADOPTED_FORMAT_DEFAULT == af.ADOPTED_ANSWER_FORMAT
    monkeypatch.setattr(mod, "CAT4_QUALITY_SUMMARY", tmp_path / "missing.json")
    assert mod.cat4_adopted_formats() == af.ADOPTED_ANSWER_FORMAT
    orig, _ = _session("hybrid_rag_rerank_citations", "original")
    var, _ = _session("hybrid_rag_rerank_citations", "scoped_absence", answer="different")
    p = tmp_path / "runs.jsonl"
    p.write_text(json.dumps(orig) + "\n" + json.dumps(var) + "\n")
    monkeypatch.setattr(mod, "CAT4_RERUN", p)
    now, before = mod.cat4_rerun_records(), mod.cat4_rerun_records(before=True)
    assert now is not None and [r["run_id"] for r in now] == [var["run_id"]]
    assert before is not None and [r["run_id"] for r in before] == [orig["run_id"]]
    assert mod._cat4_label(mod._cat4_key("hybrid_rag_rerank_citations", 1, True)).endswith("before (original instructions)")


# ------------------------------------------------------------------------ Gap 2: absence-claim detector


@pytest.mark.parametrize(("text", "form"), [
    ("The documents specify no banking NOC or escrow gate.", "corpus"),
    ("- **Required Sign-Off Gate**: The deal room does not specify a banking NOC or escrow gate.", "corpus"),
    ("The documents do not specify any banking NOC or escrow gate.", "corpus"),
    ("The contracts contain no delisting gate.", "corpus"),
    ("The text names the CMK owner and rotation cycle but does not state a KMS key region.", "corpus"),
    ("No INR/Crore exposure figure appears in the documents.", "corpus"),
    ("The reserve disclosure is currently missing from the record.", "corpus"),
    ("Required Sign-Off Gate: None stated in the text provided.", "scoped"),
    ("The SBI NOC is not in the text provided.", "scoped"),
    ("No banking NOC or escrow gate appears in these excerpts.", "scoped"),
    ("The supplied text specifies no banking NOC or escrow gate.", "scoped"),
    ("The MSA baseline cap is not in the excerpts, so that contrast cannot be quantified.", "scoped"),
    ("Legal must obtain the full Addendum A, which is missing here.", "scoped"),
])
def test_detector_flags_absence_claims_with_form(text: str, form: str) -> None:
    claims = qr.absence_claims(text)
    assert len(claims) == 1 and claims[0]["form"] == form


@pytest.mark.parametrize("text", [
    "- **Required Sign-Off Gate**: Deccan must deliver SBI's written NOC 5 business days before allotment (SL.1(1)).",
    "The MSA cap does not apply to Schedule B, C or D liabilities.",
    "No uncapped liability applies to Deccan under Clause 9.1.",
    "The documents require an SBI NOC and an escrow of 18% of the disputed ITC.",
    "Deccan does not need consent for the 25% threshold below 26%.",
    "The MSA does not specify a separate escrow bank.",  # a named document, not the source as a whole
    "Not applicable.",
])
def test_detector_ignores_real_statements(text: str) -> None:
    assert qr.absence_claims(text) == []


def test_detector_multi_sentence_and_markup() -> None:
    text = ("- **Verdict**: Cap INR 4.50 Cr [1].\n- **Gate**: The documents state no other gates [2]. "
            "Banking NOC and escrow gates are not in these excerpts.")
    claims = qr.absence_claims(text)
    assert [c["form"] for c in claims] == ["corpus", "scoped"]
    assert claims[0]["sentence"] == "Gate: The documents state no other gates."
    j = {"parsed": {"factual_errors": [
        {"claim_quote": "The documents state no other gates.", "problem": "p", "source_quote_or_absent": "SBI NOC ...", "severity": "material"},
        {"claim_quote": "The documents state no other gates.", "problem": "p", "source_quote_or_absent": "ABSENT", "severity": "material"},
        {"claim_quote": "The documents state no other gates.", "problem": "p", "source_quote_or_absent": "x", "severity": "minor"},
        {"claim_quote": "Cap is INR 5 Cr.", "problem": "p", "source_quote_or_absent": "4.50", "severity": "material"}]}}
    assert [e["form"] for e in qr.judge_absence_errors(j)] == ["corpus"]


@pytest.mark.skipif(not HAVE_REAL, reason="no Category 4 rerun data")
def test_detector_validation_on_real_records() -> None:
    v = qr.validate_absence_detector(qr.load_jsonl(REAL_RUNS), qr.load_jsonl(REAL_JUDGEMENTS))
    assert v["known_claims"] == 18 and v["detected"] == 18 and v["missed"] == []
    assert v["detected_by_form"] == {"corpus": 10, "scoped": 8}
    hits = v["cached_full_corpus_corpus_form_hits"]
    assert len(hits) == 8 and all(h["judge_material_errors"] == 0 for h in hits)


# ------------------------------------------------------------------------ analysis renders the new columns


def _absence_section(text: str) -> list[str]:
    return text.split("### Absence claims", 1)[1].split("\n###", 1)[0].splitlines()


def test_analysis_renders_absence_columns_with_and_without_variant(tmp_path: Path) -> None:
    mod = _load_script("analyze_cat4_quality")
    orig = [_session(r, "original")[0] for r in ("hybrid_rag_rerank_citations", "cached_full_corpus_citations")]
    runs = tmp_path / "runs.jsonl"
    runs.write_text("".join(json.dumps(r) + "\n" for r in orig))
    md = tmp_path / "a.md"
    assert mod.main(["--runs", str(runs), "--judgements", str(tmp_path / "none.jsonl"), "--out-md", str(md)]) == 0
    text = md.read_text()
    assert "### Absence claims" in text and "## Absence-claim detector validation" in text and "scoped_absence" not in text
    row = next(line for line in _absence_section(text) if line.startswith("| R3 BM25+rerank · s1 | 8 |"))
    assert "8/8 (100%)" in row  # every fake answer says the documents specify no gate
    var = _session("hybrid_rag_rerank_citations", "scoped_absence", answer="Gate: None stated in the text provided.")[0]
    runs.write_text("".join(json.dumps(r) + "\n" for r in [*orig, var]))
    assert mod.main(["--runs", str(runs), "--judgements", str(tmp_path / "none.jsonl"), "--out-md", str(md)]) == 0
    text = md.read_text()
    vrow = next(line for line in _absence_section(text) if line.startswith("| R3 BM25+rerank · s1 · scoped_absence | 8 |"))
    assert vrow.split("|")[3].strip().startswith("0/8") and vrow.split("|")[4].strip().startswith("8/8")
    s = json.loads(md.with_suffix(".json").read_text())
    assert "hybrid_rag_rerank_citations|1|scoped_absence" in s["rerun"]["groups"] and s["answer_formats"] == ["original", "scoped_absence"]


def test_rerun_cli_dry_run_variant_with_judge_estimate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mod = _load_script("cat4_quality_rerun")
    out = tmp_path / "runs.jsonl"
    orig = _session("hybrid_rag_rerank_citations", "original")[0]
    out.write_text(json.dumps(orig) + "\n")
    rc = asyncio.run(mod.main(mod.parse_args(["--dry-run", "--out", str(out), "--answer-format", "scoped_absence",
                                              "--rungs", "hybrid_rag_rerank_citations", "--scales", "1", "--repeats", "2"])))
    text = capsys.readouterr().out
    assert rc == 0 and "answer format scoped_absence; 0 already ok, 2 pending" in text
    assert "Judging the 16 answers" in text and "no API calls" in text
    assert out.read_text() == json.dumps(orig) + "\n"  # dry run writes nothing
