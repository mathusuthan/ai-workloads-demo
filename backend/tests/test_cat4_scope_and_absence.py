"""Category 4 (offline, no network): the supplier-scope line in the app's live and ad-hoc paths, and the answer
instructions of the version with the lever (it sees only the picked clauses, so it says when a term is not in
the text provided)."""

from __future__ import annotations

import asyncio
import difflib
import hashlib
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
from app.archetypes.cat4_rag.prompts import get_cat4_synthesis_system_prompt  # noqa: E402
from app.core.anthropic_service import AnthropicRawResult  # noqa: E402
from app.core.credit_shield import ResolvedCredentials, credit_shield  # noqa: E402
from app.data.cat4_fixtures import CAT4_PRESETS, hydrate_deal_room_index  # noqa: E402
from app.main import app  # noqa: E402

REAL_RUNS = BACKEND_DIR / "experiments" / "cat4_quality" / "runs.jsonl"
REAL_JUDGEMENTS = BACKEND_DIR / "experiments" / "cat4_quality" / "judgements.jsonl"
HAVE_REAL = REAL_RUNS.is_file() and REAL_JUDGEMENTS.is_file()
NAIVE, PAIRED = "naive_full_corpus", "cached_rerank_hybrid"
APP_RUNGS = (NAIVE, PAIRED)
SCOPE = ("Deal room under audit: DR-NM-DECCAN-2026-Q4 (supplier: Deccan Smart Appliances & Energy Pvt. Ltd.). "
         "Answer for this supplier's contracts only.")


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def _rerank_query(kw: dict[str, Any]) -> str:
    """The clause-pick query block (the block after the cached clause block)."""
    return kw["user_content"][1]["text"]


class Calls:
    """Fake call wrappers: record every input; the clause pick keeps the first 5 clauses it is shown."""

    def __init__(self, answer: str = "Required Sign-Off Gate: None stated in the text provided.") -> None:
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


# ------------------------------------------------------------------------ the scope line in the app


@pytest.fixture()
def fake_app_calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Calls:
    monkeypatch.setenv("NOVAMART_TRACES_DIR", str(tmp_path / "traces"))
    c = Calls()
    monkeypatch.setattr(runner, "run_cat4_rag_synthesis", c.synth_call)
    monkeypatch.setattr(runner, "run_cat4_haiku_reranker", c.rerank_call)
    monkeypatch.setattr(credit_shield, "resolve_live_credentials",
                        lambda *a, **k: ResolvedCredentials("k", "byok", False))
    return c


@pytest.mark.parametrize("rung", APP_RUNGS)
def test_live_question_is_scoped_in_every_input(rung: str, fake_app_calls: Calls) -> None:
    c = fake_app_calls
    docs, chunks, total = hydrate_deal_room_index()
    q = CAT4_PRESETS[0]["questions"][1]
    scoped = SCOPE + "\n\n" + q["question"]
    q_res, raw = asyncio.run(runner._run_live_cat4_query_for_rung(q_idx=0, q_spec=q, rung_id=rung, hydrated_docs=docs,
                                                                  flat_chunks=chunks, total_corpus_chars=total, api_key="k"))
    assert [kw["user_question"] for kw in c.synth] == [scoped]  # synthesis message
    assert q_res.question == q["question"] and q_res.question_as_asked == scoped == raw["question_as_asked"]
    if rung == PAIRED:
        assert len(c.rerank) == 1 and _rerank_query(c.rerank[0]).count(scoped) == 1  # clause-pick query
        assert scoped not in c.rerank[0]["user_content"][0]["text"]  # the cached clause block does not change per question
    else:
        assert c.rerank == []


def test_live_audit_and_adhoc_endpoints_send_the_scoped_question(fake_app_calls: Calls) -> None:
    c = fake_app_calls
    client = TestClient(app)
    resp = client.post("/api/cat4/run", json={"preset_id": "audit-02", "mode": "live"})
    assert resp.status_code == 200, resp.text
    qs = [q["question"] for q in CAT4_PRESETS[1]["questions"]]
    expected = [SCOPE + "\n\n" + q for q in qs]
    assert sorted(kw["user_question"] for kw in c.synth) == sorted(expected * 2)  # 2 versions x 4 questions
    assert [_rerank_query(kw).count(e) for kw, e in zip(c.rerank, expected)] == [1] * 4
    for r in resp.json()["results"]:
        assert [q["question_as_asked"] for q in r["queries"]] == expected and [q["question"] for q in r["queries"]] == qs

    c.synth.clear(), c.rerank.clear()
    ask = "Which clause controls the liability cap for Deccan?"
    resp = client.post("/api/cat4/query", json={"preset_id": "audit-01", "question": ask, "mode": "live"})
    assert resp.status_code == 200, resp.text
    assert [kw["user_question"] for kw in c.synth] == [SCOPE + "\n\n" + ask] * 2
    assert len(c.rerank) == 1 and _rerank_query(c.rerank[0]).count(SCOPE + "\n\n" + ask) == 1
    assert {r["queries"][0]["question_as_asked"] for r in resp.json()["results"]} == {SCOPE + "\n\n" + ask}
    assert resp.json()["question"] == ask


def test_live_and_adhoc_prompt_per_version(fake_app_calls: Calls, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the lever: the app synthesis prompt byte for byte. With it: the not-in-the-text-provided
    instructions, with citations (preset and ad-hoc)."""
    c = fake_app_calls
    scoped = af.synthesis_system_prompt(with_citations=True, answer_format=af.SCOPED_ABSENCE)
    full = get_cat4_synthesis_system_prompt(with_citations=False)
    assert _sha(full) == PINNED["synth_nocit"]
    client = TestClient(app)
    for body, path in (({"preset_id": "audit-01", "mode": "live"}, "/api/cat4/run"),
                       ({"preset_id": "audit-01", "question": "Which clause controls the cap?", "mode": "live"}, "/api/cat4/query")):
        c.synth.clear()
        resp = client.post(path, json=body)
        assert resp.status_code == 200, resp.text
        assert {kw["system_prompt"] for kw in c.synth} == {full, scoped}
        by = {kw["system_prompt"]: kw for kw in c.synth}
        assert by[full]["documents_for_blocks"] is None and len(by[scoped]["documents_for_blocks"]) == 5
    assert af.RUNG_ANSWER_FORMAT[PAIRED] == af.SCOPED_ABSENCE and af.RUNG_ANSWER_FORMAT[NAIVE] == af.FULL_CORPUS


def test_replay_mode_does_not_use_the_live_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NOVAMART_TRACES_DIR", str(tmp_path / "traces"))

    async def boom(**kw: Any) -> AnthropicRawResult:
        raise AssertionError("replay must not call the API")

    monkeypatch.setattr(runner, "run_cat4_rag_synthesis", boom)
    monkeypatch.setattr(runner, "run_cat4_haiku_reranker", boom)
    golden = runner.load_cat4_replays()["presets"]["audit-01"]["rungs"]
    data = TestClient(app).post("/api/cat4/run", json={"preset_id": "audit-01", "mode": "replay"}).json()
    assert [r["rung_id"] for r in data["results"]] == list(APP_RUNGS)
    for r in data["results"]:
        assert [q["question_as_asked"] for q in r["queries"]] == [q["question_as_asked"] for q in golden[r["rung_id"]]]


# ------------------------------------------------------------------------ the harness's model-facing text is unchanged

# sha256 of the harness's model-facing text, taken before the scope line moved to scope.py
PINNED = {
    "synth_cit": "90aa83317ff7814463c8ad7c18469af3b7e5b63eefaf79ec11f7093b37e059b0",
    "synth_nocit": "026c3fa599de955a880de26253a86a88e7c533265f4f80daef311a0d7806617b",
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
    assert _sha(qr.get_full_corpus_reranker_system_prompt()) == PINNED["rerank_full"]
    assert _sha("\x00".join(qr.scoped_question(q["question"]) for _, q in qr.session_questions())) == PINNED["scoped_qs"]


@pytest.mark.skipif(not HAVE_REAL, reason="no Category 4 rerun data")
def test_existing_records_match_the_shared_scope_line_and_stay_current() -> None:
    recs = qr.load_jsonl(REAL_RUNS)
    ok = [r for r in recs if r.get("status") == "ok"]
    assert len(ok) == len(recs) == 12  # 2 versions x 2 corpus sizes x 3 sessions
    assert {(r["rung_id"], qr.answer_format_of(r)) for r in ok} == {(NAIVE, af.FULL_CORPUS), (PAIRED, af.SCOPED_ABSENCE)}
    for r in ok:
        assert qr.is_current_settings(r)
        if r["rung_id"] == NAIVE:
            assert "answer_format" not in r["settings"]  # recorded before the field existed: the full-corpus prompt
        assert r["settings"]["question_scope_line"] == scope.scope_line()
        assert all(a["question_as_asked"] == scope.scoped_question(a["question"]) for a in r["answers"])
        assert r["corpus"]["fingerprint"] == qr.corpus_fingerprint(qr.build_scaled_corpus(int(r["scale"])))
    assert qr.select_pending(qr.plan_matrix(qr.RUNG_IDS, qr.SCALES, 3), recs) == []
    plan = qr.plan_judge_calls(qr.judge_items(records=recs))
    assert len(plan) == 96 and qr.select_pending_judgements(plan, qr.load_jsonl(REAL_JUDGEMENTS)) == []


# ------------------------------------------------------------------------ the with-the-lever answer instructions


@pytest.mark.parametrize("cit", [True, False])
def test_scoped_instructions_differ_only_in_absence_handling(cit: bool) -> None:
    a = af.synthesis_system_prompt(with_citations=cit).split("\n")
    b = af.synthesis_system_prompt(with_citations=cit, answer_format=af.SCOPED_ABSENCE).split("\n")
    diff = list(difflib.unified_diff(a, b, lineterm="", n=0))
    removed = [line[1:] for line in diff if line.startswith("-") and not line.startswith("---")]
    added = [line[1:] for line in diff if line.startswith("+") and not line.startswith("+++")]
    assert removed == [af.GATE_LINE] and added == [af.SCOPED_GATE_LINE, af.PARTIAL_CONTEXT_RULE]
    assert b.index(af.SCOPED_GATE_LINE) == a.index(af.GATE_LINE)
    assert b[b.index(af.PARTIAL_CONTEXT_RULE) - 1] == af.LAST_RULE_LINE  # with the other rules
    assert '"None stated in the text provided"' in af.SCOPED_GATE_LINE
    with pytest.raises(ValueError):
        af.synthesis_system_prompt(with_citations=cit, answer_format="other")


@pytest.mark.parametrize("rung", qr.RUNG_IDS)
def test_harness_session_uses_the_versions_prompt_and_records_it(rung: str) -> None:
    c = Calls()
    rec = asyncio.run(qr.execute_session(rung_id=rung, scale=1, repeat_index=0, api_key="k", synth_call=c.synth_call,
                                         rerank_call=c.rerank_call))
    assert rec["status"] == "ok" and rec["settings"]["answer_format"] == af.rung_answer_format(rung)
    assert rec["settings"]["question_scope_line"] == SCOPE
    assert {kw["system_prompt"] for kw in c.synth} == {af.rung_synthesis_system_prompt(rung, with_citations=rung == PAIRED)}
    assert qr.is_current_settings(rec)
    odd = json.loads(json.dumps(rec))
    odd["settings"]["answer_format"] = af.SCOPED_ABSENCE if rung == NAIVE else af.FULL_CORPUS
    assert not qr.is_current_settings(odd) and qr.select_pending([qr.record_key(rec)], [odd]) == [qr.record_key(rec)]


# ------------------------------------------------------------------------ absence-claim detector (analysis column)


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
