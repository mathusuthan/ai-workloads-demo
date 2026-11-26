"""App <-> Category 4 quality-rerun alignment: golden builder, billing note, quality block, portfolio, capture, seeding,
synthesis cap and the validation report's Category 4 section. No live API calls."""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat4_rag import quality as cat4_quality  # noqa: E402
from app.archetypes.cat4_rag import runner  # noqa: E402
from app.core.anthropic_service import AnthropicRawResult  # noqa: E402
from app.data.cat4_fixtures import CAT4_PRESETS, hydrate_deal_room_index  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Cat4QualityPortfolio  # noqa: E402

RUNS = BACKEND_DIR / "experiments" / "cat4_quality" / "runs.jsonl"
JUDGEMENTS = BACKEND_DIR / "experiments" / "cat4_quality" / "judgements.jsonl"
APP_RUNGS = ("naive_full_corpus", "cached_full_corpus_citations", "hybrid_rag_rerank_citations")
HAVE_RERUN = RUNS.is_file() and JUDGEMENTS.is_file()


def _load_script(name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    monkeypatch.setenv("NOVAMART_TRACES_DIR", str(tmp_path / "traces"))
    spec = importlib.util.spec_from_file_location(name, BACKEND_DIR / "scripts" / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("NOVAMART_TRACES_DIR", str(tmp_path / "traces"))
    return TestClient(app)


# ------------------------------------------------------------------------ 1. golden from quality rerun


def _rec(rung_id: str, repeat: int, scale: int, *, answer: str, run_id: str) -> dict[str, Any]:
    answers = []
    for i, (pid, qid) in enumerate((p["id"], q["question_id"]) for p in CAT4_PRESETS for q in p["questions"]):
        cw, cr = (9000, 0) if (rung_id.startswith("cached") and i == 0) else ((0, 9000) if rung_id.startswith("cached") else (0, 0))
        calls = [{"role": "synthesis", "model_id": "claude-sonnet-5-5", "latency_ms": 10, "stop_reason": "end_turn", "max_tokens": 4096,
                  "input_tokens": 100, "output_tokens": 50, "thinking_tokens": 0, "cache_creation_tokens": cw, "cache_read_tokens": cr}]
        answers.append({"preset_id": pid, "question_id": qid, "q_index": i, "status": "ok", "question": f"Q {qid}",
                        "question_as_asked": f"scope\n\nQ {qid}", "answer_markdown": f"{answer} {pid} {qid}",
                        "segments": [{"text": f"{answer} {pid} {qid}", "cite_numbers": []}], "citations": [], "calls": calls})
    return {"status": "ok", "run_id": run_id, "rung_id": rung_id, "scale": scale, "repeat_index": repeat,
            "settings": {"synth_max_tokens": 4096}, "answers": answers}


def test_golden_builder_uses_fixed_mapping_and_is_idempotent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("build_cat4_golden_from_rerun", monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "is_current_settings", lambda r: True)
    records = []
    for rid in ("naive_full_corpus", "cached_full_corpus_citations"):
        # repeat 0 / scale 1 answers badly; other cells answer well. The fixed mapping must still take repeat 0, scale 1.
        records += [_rec(rid, 0, 1, answer="bad", run_id=f"{rid}-r0s1"), _rec(rid, 1, 1, answer="good", run_id=f"{rid}-r1s1"),
                    _rec(rid, 0, 3, answer="good", run_id=f"{rid}-r0s3")]
    monkeypatch.setattr(mod, "APP_RUNG_IDS", ("naive_full_corpus", "cached_full_corpus_citations"))
    doc = mod.build_golden(records, [], source_file="x.jsonl", judgements_file="j.jsonl", keys_version="k")
    for pid, p in doc["presets"].items():
        for rid, qs in p["rungs"].items():
            assert p["provenance"][rid]["run_id"] == f"{rid}-r0s1"
            assert p["provenance"][rid]["repeat_index"] == 0 and p["provenance"][rid]["scale"] == 1
            assert len(p["provenance"][rid]["session_questions"]) == 8
            assert all(q["answer_markdown"].startswith("bad") and q["stop_reason"] == "end_turn" for q in qs)
            assert all(q["question_as_asked"].startswith("scope") and q["question"].startswith("Q ") for q in qs)
            summary = runner._build_cat4_summary_from_replay(rung_id=rid, preset=next(x for x in CAT4_PRESETS if x["id"] == pid),
                                                             raw_queries=qs, total_corpus_chars=1000)
            assert len(summary.queries) == 4 and summary.queries[0].stop_reason == "end_turn"
    cached2 = doc["presets"]["audit-02"]["rungs"]["cached_full_corpus_citations"][0]
    assert cached2["cache_creation_tokens"] == 0 and cached2["cache_read_tokens"] > 0  # not re-labelled as a write
    out = tmp_path / "golden.json"
    assert mod.write_if_changed(doc, out, stamp=True) is True
    first = out.read_text()
    again = mod.build_golden(copy.deepcopy(records), [], source_file="x.jsonl", judgements_file="j.jsonl", keys_version="k")
    assert mod.write_if_changed(again, out, stamp=True) is False and out.read_text() == first


def test_golden_builder_raises_without_repeat_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("build_cat4_golden_from_rerun", monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "is_current_settings", lambda r: True)
    with pytest.raises(ValueError, match="repeat 0"):
        mod.build_golden([_rec("naive_full_corpus", 1, 1, answer="x", run_id="r")], [], source_file="x",
                         judgements_file="j", keys_version="k")


@pytest.mark.skipif(not HAVE_RERUN, reason="quality rerun records not present")
def test_committed_golden_and_summary_match_the_rerun(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("build_cat4_golden_from_rerun", monkeypatch, tmp_path)
    records, judgements = mod.load_jsonl(RUNS), mod.load_jsonl(JUDGEMENTS)
    keys = mod.load_quality_keys()
    golden = mod.build_golden(records, judgements, source_file="experiments/cat4_quality/runs.jsonl",
                              judgements_file="experiments/cat4_quality/judgements.jsonl", keys_version=keys["meta"]["keys_version"])
    committed = json.loads(mod.DEFAULT_OUT.read_text(encoding="utf-8"))
    assert mod._comparable(committed) == mod._comparable(golden)
    portfolio = mod.build_quality_portfolio(records, judgements, keys=keys, source_file="experiments/cat4_quality/runs.jsonl",
                                            judgements_file="experiments/cat4_quality/judgements.jsonl")
    summary = json.loads(mod.DEFAULT_SUMMARY_OUT.read_text(encoding="utf-8"))
    assert summary == json.loads(json.dumps(portfolio))
    Cat4QualityPortfolio.model_validate(summary)  # the schema the API serves


def test_committed_golden_provenance_and_billing() -> None:
    g = runner.load_cat4_replays()
    prov = g["provenance"]
    assert prov["source"] == "cat4 quality rerun" and "repeat_index 0" in prov["selection_rule"]
    assert "audit-02 q1 was billed as a cache read" in prov["billing_note"]
    assert "cached_rerank_hybrid" in prov["not_mapped"]
    assert prov["answer_formats"] == {"naive_full_corpus": "original", "cached_full_corpus_citations": "original",
                                      "hybrid_rag_rerank_citations": "scoped_absence"}
    for pid, p in g["presets"].items():
        assert set(p["rungs"]) == set(APP_RUNGS)
        assert {rid: v["answer_format"] for rid, v in p["provenance"].items()} == prov["answer_formats"]
        for rid, qs in p["rungs"].items():
            assert all(q["stop_reason"] and q["judgement"] for q in qs)
            assert all(q["max_tokens"] == runner.CAT4_SYNTH_MAX_TOKENS for q in qs)
    c1 = g["presets"]["audit-01"]["rungs"]["cached_full_corpus_citations"][0]
    c2 = g["presets"]["audit-02"]["rungs"]["cached_full_corpus_citations"][0]
    assert c1["cache_creation_tokens"] > 0
    assert c2["cache_creation_tokens"] == 0 and c2["cache_read_tokens"] > 0
    assert runner._replay_billing_note(g["presets"]["audit-01"]) is None
    note = runner._replay_billing_note(g["presets"]["audit-02"])
    assert note and "no cache write was billed here" in note


# ------------------------------------------------------------------------ 2. API: quality + portfolio


@pytest.mark.parametrize("pid", ["audit-01", "audit-02"])
def test_replay_api_includes_quality_and_portfolio(client: TestClient, pid: str) -> None:
    resp = client.post("/api/cat4/run", json={"preset_id": pid, "mode": "replay"})
    assert resp.status_code == 200
    data = resp.json()
    assert (data["billing_note"] is None) == (pid == "audit-01")
    pf = data["quality_portfolio"]
    # 4 versions x 2 sizes in their adopted format + the 2 retrieval versions' "before" (original) cells = 12 x 24 answers
    assert pf and pf["answers_scored"] == 288 and pf["matrix_complete"] is True and len(pf["cells"]) == 12
    assert {c["rung_id"] for c in pf["cells"]} == set(APP_RUNGS) | {"cached_rerank_hybrid"}
    assert {(c["rung_id"], c["answer_format"]) for c in pf["cells"] if c["adopted"]} == {
        ("naive_full_corpus", "original"), ("cached_full_corpus_citations", "original"),
        ("hybrid_rag_rerank_citations", "scoped_absence"), ("cached_rerank_hybrid", "scoped_absence")}
    assert {c["rung_id"] for c in pf["cells"] if not c["adopted"]} == {"hybrid_rag_rerank_citations", "cached_rerank_hybrid"}
    assert pf["format_change"]["rungs"] == ["hybrid_rag_rerank_citations", "cached_rerank_hybrid"]
    assert {r["rung_id"]: r["answer_format"] for r in data["results"]}["hybrid_rag_rerank_citations"] == "scoped_absence"
    assert {c["runnable_in_app"] for c in pf["cells"] if c["rung_id"] == "cached_rerank_hybrid"} == {False}
    golden = runner.load_cat4_replays()["presets"][pid]["rungs"]
    for r in data["results"]:
        q = r["quality"]
        assert q is not None and r["quality_unavailable_reason"] is None
        assert q["audit"]["questions"] == 4 and q["audit"]["judged"] == 4 and q["grader_unavailable_reason"] is None
        assert q["audit"]["key_facts"]["total"] > 0
        assert (q["audit"]["citations_at_expected"] is None) == (r["rung_id"] == "naive_full_corpus")
        assert (q["audit"]["retrieval_recall"] is not None) == (r["rung_id"] == "hybrid_rag_rerank_citations")
        for qq, rq in zip(q["questions"], golden[r["rung_id"]]):
            j = rq["judgement"]
            assert qq["grader"]["correctness"] == j["correctness"]["score"]
            assert len(qq["grader"]["material_errors"]) == sum(1 for e in j["factual_errors"] if e["severity"] == "material")
            assert qq["stop_reason"] == rq["stop_reason"]
        assert sum(x["grader"]["material_errors"] != [] for x in q["questions"]) == q["audit"]["answers_with_material_error"]
    assert "Answer quality on this audit" in data["rag_callout"]


def test_portfolio_falls_back_to_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _S:
        replays_dir = str(tmp_path)

    monkeypatch.setattr(cat4_quality, "get_settings", lambda: _S())
    assert cat4_quality.load_cat4_quality_portfolio() is None
    (tmp_path / "cat4_quality_summary.json").write_text("{not json")
    assert cat4_quality.load_cat4_quality_portfolio() is None
    res = [runner.finalize_cat4_rung_summary(rung_id=r, model_id="claude-sonnet-5-5", queries=[]) for r in APP_RUNGS]
    runner._apply_measured_claims(res, None)  # number-free fallbacks, no crash without the portfolio
    assert res[1].badge_text == "Lever 1: Cache Reads + Citations"


def test_live_and_adhoc_quality_reasons() -> None:
    g = runner.load_cat4_replays()["presets"]["audit-01"]["rungs"]["cached_full_corpus_citations"]
    preset = next(p for p in CAT4_PRESETS if p["id"] == "audit-01")
    summary = runner._build_cat4_summary_from_replay(rung_id="cached_full_corpus_citations", preset=preset, raw_queries=g,
                                                     total_corpus_chars=1000)
    q, reason = cat4_quality.build_rung_quality(summary.queries, rung_id="cached_full_corpus_citations", preset_id="audit-01",
                                                judgements=None, grader_unavailable_reason=runner.LIVE_GRADER_REASON)
    assert reason is None and q is not None
    assert q.audit.judged == 0 and q.audit.correctness_mean is None and q.grader_unavailable_reason == runner.LIVE_GRADER_REASON
    assert q.audit.key_facts.total > 0 and q.audit.citations_at_expected is not None  # deterministic measures still run
    # an ad-hoc question has no answer key: no quality block, with the reason
    adhoc = summary.queries[0].model_copy(update={"question_id": "adhoc"})
    q2, reason2 = cat4_quality.build_rung_quality([adhoc], rung_id="cached_full_corpus_citations", preset_id="audit-01",
                                                  judgements=None, grader_unavailable_reason=runner.LIVE_GRADER_REASON)
    assert q2 is None and reason2 == cat4_quality.NO_KEY_REASON


# ------------------------------------------------------------------------ 3. live path: cap + stop reasons


def test_live_path_uses_4096_cap_and_records_real_stop_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    async def fake_synth(**kw: Any) -> AnthropicRawResult:
        seen.update(kw)
        return AnthropicRawResult("claude-sonnet-5-5", 5, 100, 4096, 0, 0, "cut off", {"segments": [], "citations": []},
                                  stop_reason="max_tokens")

    monkeypatch.setattr(runner, "run_cat4_rag_synthesis", fake_synth)
    docs, chunks, total = hydrate_deal_room_index()
    q_res, raw = asyncio.run(runner._run_live_cat4_query_for_rung(
        q_idx=0, q_spec=CAT4_PRESETS[0]["questions"][0], rung_id="naive_full_corpus", hydrated_docs=docs,
        flat_chunks=chunks, total_corpus_chars=total, api_key="k"))
    assert runner.CAT4_SYNTH_MAX_TOKENS == 4096 and seen["max_tokens"] == 4096 and raw["max_tokens"] == 4096
    assert q_res.stop_reason == raw["stop_reason"] == "max_tokens"  # recorded, not defaulted to end_turn


# ------------------------------------------------------------------------ 4. capture + seeding


def test_capture_accepts_zero_citation_answers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("capture_cat4_replays", monkeypatch, tmp_path)
    base = {"stop_reason": "end_turn", "citations": [], "question_number": 1}
    cached = [{**base, "cache_creation_tokens": 15000, "cache_read_tokens": 0}, {**base, "cache_creation_tokens": 0, "cache_read_tokens": 15000}]
    hybrid = [{**base, "reranker_input_tokens": 900}, {**base, "reranker_input_tokens": 900}]
    assert mod._validate_rung("cached_full_corpus_citations", cached, 2) is None
    assert mod._validate_rung("hybrid_rag_rerank_citations", hybrid, 2) is None
    assert mod._validate_rung("naive_full_corpus", [{**base, "stop_reason": "max_tokens"}], 1) is not None  # infra checks stay


def test_seed_cat4_writes_rerun_traces_with_real_stop_reasons(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("seed_traces_from_replays", monkeypatch, tmp_path)
    n = mod.seed_cat4()
    files = [p for p in (tmp_path / "traces").rglob("*.json")]
    assert n == len(files) == 32  # 2 audits x (3 rungs x 4 synthesis + 4 rerank)
    recs = [json.loads(p.read_text()) for p in files]
    blob = json.dumps(recs)
    assert "build_cat4_golden_from_rerun.py" in blob and "Deal room under audit" in blob  # payload = question as asked
    for r in recs:
        assert r["response"]["stop_reason"] == "end_turn"
        assert r["request"]["parameters"]["max_tokens"] in (runner.CAT4_SYNTH_MAX_TOKENS, runner.CAT4_RERANK_MAX_TOKENS)


# ------------------------------------------------------------------------ 5. validation report


def test_validator_cat4_uses_rerun_and_falls_back(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("validate_deck_claims", monkeypatch, tmp_path)
    if HAVE_RERUN:
        units, source, stats = mod.cat4_units()
        assert source == "quality rerun" and stats["answers"] == 192
        assert len(units) == 8 and {len(v) for v in units.values()} == {6}  # 3 sessions x 2 audits per cell
    monkeypatch.setattr(mod, "CAT4_RERUN", tmp_path / "missing.jsonl")
    units, source, stats = mod.cat4_units()
    assert source == "golden replays" and stats is None and set(units) == {f"{r}|1" for r in APP_RUNGS}
    monkeypatch.setattr(mod, "CAT4_QUALITY_SUMMARY", tmp_path / "missing.json")
    monkeypatch.setattr(mod, "CAT4_QUALITY_ANALYSIS", tmp_path / "missing2.json")
    cells, be, src = mod.cat4_quality()
    assert cells is None and be is None and src


@pytest.mark.skipif(not HAVE_RERUN, reason="quality rerun records not present")
def test_validator_cat4_lever_and_implicit_rows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("validate_deck_claims", monkeypatch, tmp_path)
    res = mod.analyse()
    c4 = {c["claim"]: c for c in res["claims"] if c["category"] == "Cat 4"}
    assert res["categories"]["cat4"]["source"] == "quality rerun"
    lever = c4["Pair hybrid retrieval (reranking + chunk filtering) with context caching"]
    implicit = c4["…without losing answer quality (implicit)"]
    # Re-evaluated on each version's adopted answer format (retrieval versions: scoped_absence). Lever row: its written
    # Wilson rule (the note reports the original-format sessions give the same verdict). Implicit row: the shared
    # implicit-row rule (IMPLICIT_RULE): no clear loss, but lower point estimates -> PARTLY.
    assert lever["verdict"] == "SUPPORTED" and implicit["verdict"] == "PARTLY SUPPORTED"
    assert "Implicit-row rule: no clear loss is detected, but point estimates are lower" in implicit["note"]
    assert "paired rung" in lever["measured"] and "Wilson" in implicit["note"] and "Wilson" in lever["note"]
    assert "before the 2026-11-26 answer-format change" in lever["measured"] and "original-format sessions gives SUPPORTED" in lever["note"]
    assert "Before the retrieval versions' 2026-11-26 answer-format change it did" in implicit["note"]
    assert set(res["categories"]["cat4"]["per_question_before"]) == {
        f"{r}|{s}|original" for r in ("hybrid_rag_rerank_citations", "cached_rerank_hybrid") for s in (1, 3)}
    md = mod.render_markdown(res)
    assert "Source: the quality rerun, " in md and "golden replays (the quality-rerun records could not be read)" not in md
