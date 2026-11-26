"""Rung badges/notes and the FinOps rule impact must quote numbers measured on the run, not fixed text."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.core.measured_claims import fmt_pct  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_traces_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    test_traces = tmp_path / "traces"
    monkeypatch.setenv("NOVAMART_TRACES_DIR", str(test_traces))
    return test_traces


def _run(cat: str, **body: object) -> dict[str, dict]:
    resp = client.post(f"/api/{cat}/run", json={"mode": "replay", **body})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return {"_response": data, **{r["rung_id"]: r for r in data["results"]}}


def _notes(rung: dict) -> str:
    return " ".join(rung["architectural_notes"])


def test_finops_rule1_impact_is_measured_from_golden_replays() -> None:
    impact = client.get("/api/archetypes").json()["finops_rules"][0]["impact"]
    assert "measured on" in impact
    assert "60–97%" not in impact


@pytest.mark.parametrize(("preset", "sub_task"), [("tkt-02", "support_triage"), ("sku-01", "sku_tagging")])
def test_cat1_notes_quote_measured_output_and_savings(preset: str, sub_task: str) -> None:
    r = _run("cat1", preset_id=preset, sub_task=sub_task)
    prose, schema = r["haiku_naive"], r["haiku_calibrated"]
    same_model_cut = (1 - schema["finops"]["total_cost_usd"] / prose["finops"]["total_cost_usd"]) * 100
    assert f"classification-only answer is {schema['finops']['output_tokens']:,} output tokens" in _notes(schema)
    assert f"cutting cost {fmt_pct(same_model_cut)} on the same model" in _notes(schema)
    assert f"cuts {fmt_pct(prose['savings_vs_naive_pct'])} vs the Sonnet 5.5 write-up" in _notes(prose)
    # The saving is attributed as measured in the ablation: asking for less and the smaller model, not the schema.
    pf = r["_response"]["ablation_portfolio"]
    lev = {lv["lever"]: lv for lv in pf["levers"]}
    ask = lev["write-up → classification-only text (haiku)"]["cost_change_pct"]
    sch = lev["text → schema (haiku)"]["cost_change_pct"]
    assert f"asking for the classification instead of a write-up (−{fmt_pct(-ask)} on Haiku" in _notes(schema)
    assert f"The JSON schema itself cost +{fmt_pct(sch)} over the same classification asked as plain text" in _notes(schema)
    assert "compresses output" not in _notes(schema) and "Strict JSON schema caps" not in _notes(schema)
    assert "default thinking" not in _notes(prose)


def test_cat1_live_write_up_is_not_scored_and_says_why() -> None:
    from app.archetypes.cat1_triage.runner import live_prose_accuracy_note, load_cat1_ablation_portfolio

    note = live_prose_accuracy_note(load_cat1_ablation_portfolio())
    assert note.startswith("Not scored live") and "under-scored plain-text classifications by about 14 points" in note
    assert "over-scored write-ups by 4–17 points" in note
    assert live_prose_accuracy_note(None).startswith("Not scored live")


def test_cat2_badge_and_notes_quote_measured_values() -> None:
    r = _run("cat2", preset_id="brief-02", sub_task="exec_synthesis")
    unb, tmpl, haiku = r["sonnet_unbounded"], r["sonnet_templated"], r["haiku_templated"]
    assert haiku["badge_text"] == f"Tier-Routed Draft (-{fmt_pct(haiku['savings_vs_unbounded_pct'])} Cost)"
    assert f"Drafts all four sections for ${haiku['finops']['total_cost_usd']:.4f}" in _notes(haiku)
    assert "complete auditable" not in _notes(haiku) and "Same frontier Sonnet 5.5 quality" not in _notes(tmpl)
    # Quality notes quote the blind-judge summary for this document (replays/cat2_quality_summary.json).
    for rung in (unb, tmpl, haiku):
        q = rung["quality"]
        assert f"accuracy {q['rubric']['factual_accuracy']['mean']:.1f}, coverage {q['rubric']['coverage']['mean']:.1f}" in _notes(rung)
    assert f"action items ({tmpl['quality']['action_items']['flagged_serious']} serious)" in _notes(tmpl)
    assert f"drive {fmt_pct(unb['finops']['output_cost_share_pct'])} of this draft" in _notes(unb)
    out_cut = (1 - tmpl["finops"]["output_tokens"] / unb["finops"]["output_tokens"]) * 100
    assert f"Cuts output tokens {fmt_pct(out_cut)}" in _notes(tmpl)


def test_cat2_falls_back_to_number_free_text_without_baseline_rung() -> None:
    r = _run("cat2", preset_id="brief-02", sub_task="exec_synthesis", rungs=["haiku_templated"])
    assert r["haiku_templated"]["badge_text"] == "Tier-Routed Draft"
    # Without the unbounded rung the quality note omits the comparison instead of inventing one.
    notes = _notes(r["haiku_templated"])
    assert "Measured quality on this document" in notes and "(unbounded:" not in notes


def test_cat3_notes_quote_measured_prefix_and_final_context() -> None:
    r = _run("cat3", preset_id="desk-01")
    first = r["prefix_cached_history"]["turns"][0]["finops"]
    prefix = first["cache_creation_tokens"] + first["cache_read_tokens"]
    assert f"~{prefix:,} tok" in _notes(r["prefix_cached_history"])
    last = r["prefix_cached_summarized"]["turns"][-1]["finops"]
    ctx = last["input_tokens"] + last["cache_creation_tokens"] + last["cache_read_tokens"]
    assert f"while holding Turn 10 context to {ctx:,} tok" in _notes(r["prefix_cached_summarized"])
    assert f"~{prefix:,}-tok handbook prefix" in r["_response"]["session_callout"]


def _frac(m: dict) -> str:
    return f"{m['hits']}/{m['total']}"


@pytest.mark.parametrize("preset", ["desk-01", "desk-02"])
def test_cat3_notes_and_callout_quote_measured_quality(preset: str) -> None:
    r = _run("cat3", preset_id=preset)
    cq, sq = r["prefix_cached_history"]["quality"], r["prefix_cached_summarized"]["quality"]
    assert cq and sq and sq["probes"] and len(sq["probes"]) == 6
    summ_note = r["prefix_cached_summarized"]["architectural_notes"][2]
    assert summ_note.startswith("Quality trade-off on this session:")
    assert f"answered {_frac(sq['probe_accuracy'])} recall questions vs {_frac(cq['probe_accuracy'])}" in summ_note
    assert f"kept {_frac(sq['ledger_by_origin']['1-3'])} turn 1–3 details" in summ_note
    pf = {x["rung_id"]: x for x in r["_response"]["quality_portfolio"]["rungs"]}
    assert f"{_frac(pf['prefix_cached_summarized']['probe_accuracy'])} recall questions vs" in summ_note
    cached_note = r["prefix_cached_history"]["architectural_notes"][2]
    assert f"answered {_frac(cq['probe_accuracy'])} recall questions" in cached_note
    callout = r["_response"]["session_callout"]
    assert "Quality trade-off:" in callout and f"{_frac(sq['probe_accuracy'])} recall questions" in callout
    assert "lossless" not in callout


def test_cat3_quality_notes_fall_back_number_free_without_scores() -> None:
    from app.archetypes.cat3_assistants import runner

    r = _run("cat3", preset_id="desk-01")
    results = [runner.Cat3RungSummary.model_validate(r[k]) for k in ("naive_full_history", "prefix_cached_history", "prefix_cached_summarized")]
    defaults = {rid: runner._rung_metadata(rid)[2] for rid in r if not rid.startswith("_")}
    for res in results:
        res.quality = None
        res.architectural_notes = list(defaults[res.rung_id])
    runner._apply_measured_claims(results, None)
    summ = results[2].architectural_notes[2]
    assert summ.startswith("Quality trade-off:") and not any(ch.isdigit() for ch in summ)
    assert not any(ch.isdigit() for ch in results[1].architectural_notes[2])
    assert "not free of quality cost" in runner._quality_callout(results[2], results[1], None)


def test_cat4_badge_and_notes_quote_measured_values() -> None:
    r = _run("cat4", preset_id="audit-01")
    naive, hybrid = r["naive_full_corpus"], r["hybrid_rag_rerank_citations"]
    avg_red = sum(q["context_reduction_pct"] for q in hybrid["queries"]) / len(hybrid["queries"])
    assert hybrid["badge_text"] == f"Lever 2: ~{fmt_pct(avg_red)} of Corpus Not Sent + Citations"
    cut = (1 - hybrid["single_query_cold_per_1k_usd"] / naive["single_query_cold_per_1k_usd"]) * 100
    assert f"cuts single cold-query cost {fmt_pct(cut)} vs Rung 1" in _notes(hybrid)
    cached = r["cached_full_corpus_citations"]
    prompt = cached["total_uncached_input_tokens"] + cached["total_cache_creation_tokens"] + cached["total_cache_read_tokens"]
    share = fmt_pct(cached["total_cache_read_tokens"] / prompt * 100)
    assert cached["badge_text"] == f"Lever 1: {share} of Prompt Tokens from Cache + Citations"
    for rung in (naive, cached, hybrid):  # note 3: this audit's measured quality
        q = rung["quality"]["audit"]
        kf = q["key_facts"]
        assert f"stated {kf['hits']}/{kf['total']} key contract facts" in rung["architectural_notes"][2]
        assert f"{q['correctness_mean']:.2f}/5" in rung["architectural_notes"][2]


def test_cat4_fallback_copy_is_number_free_and_makes_no_unsupported_claims() -> None:
    from app.archetypes.cat4_rag import runner as cat4_runner

    blob = []
    for rid in ("naive_full_corpus", "cached_full_corpus_citations", "hybrid_rag_rerank_citations"):
        title, badge, _, notes = cat4_runner._rung_metadata(rid)
        blob += [badge, *notes]
        assert not any(ch.isdigit() for ch in notes[2])
        # note 3: the 2026-11-26 answer-format change (retrieval rung) / "not changed" (full-corpus rungs); no measured numbers
        assert ("not in the text provided" in notes[3]) == (rid == "hybrid_rag_rerank_citations")
        assert notes[3].startswith("Prompt not changed") == (rid != "hybrid_rag_rerank_citations")
        assert not any(ch.isdigit() for ch in notes[3].replace("2026-11-26", ""))
    text = " ".join(blob).lower()
    for banned in ("95%", "zero-hallucination", "without chunking or missing", "linearly", "decisive"):
        assert banned not in text
    summ = cat4_runner.finalize_cat4_rung_summary(rung_id="cached_full_corpus_citations", model_id="m", queries=[])
    cat4_runner._apply_measured_claims([summ], None)  # no ok rung -> fallback copy stays
    assert summ.badge_text == "Lever 1: Cache Reads + Citations"


@pytest.mark.parametrize("preset", ["inv-01", "inv-02", "inv-03"])
def test_cat5_badge_and_notes_quote_measured_values(preset: str) -> None:
    from app.archetypes.cat5_orchestration.runner import load_cat5_ablation_portfolio

    r = _run("cat5", preset_id=preset)
    naive, bounded, hybrid = r["unbounded_sonnet_loop"], r["bounded_sonnet_cached_gate"], r["hybrid_haiku_sonnet_governed"]
    # badges name the levers; no fixed cost claim in a badge
    assert naive["badge_text"] == "Baseline: Raw Tables, No Cache"
    assert bounded["badge_text"] == "Narrow Query + Cache + Policy Gate"
    assert hybrid["badge_text"] == "Tiered Routing + Policy Gate"
    prompt = naive["total_uncached_input_tokens"] + naive["total_cache_creation_tokens"] + naive["total_cache_read_tokens"]
    assert f"{prompt:,} prompt tokens this run; {naive['steps_used']} of a {naive['max_step_budget']}-turn safety cap used" in _notes(naive)
    assert f"uncached prompt tokens {naive['total_uncached_input_tokens']:,} → {bounded['total_uncached_input_tokens']:,} vs rung 1" in _notes(bounded)
    ev = bounded["evaluation"]
    assert f"rupee fields {ev['matched_fields']}/{ev['total_fields']} on this invoice" in _notes(bounded)
    assert f"Haiku 5.5 ran {hybrid['haiku_steps']} turn" in _notes(hybrid)
    # ablation numbers are quoted from the summary, not fixed text
    port = load_cat5_ablation_portfolio()
    assert port is not None
    gated = next(a for a in port.arms if a.arm_id == "bundle_gate_sonnet_cached")
    tiered = next(a for a in port.arms if a.arm_id == "bundle_gate_haiku_escalate")
    assert f"{gated.turns_mean:.1f}" in _notes(bounded) and f"{gated.exact}/{gated.runs}" in _notes(bounded)
    assert f"${tiered.cost_per_1k_billed_usd:.2f}" in _notes(hybrid)
    assert f"{tiered.escalation_fired}/{tiered.runs}" in _notes(hybrid)
    for banned in ("-92%", "Cost)", "quadratic", "runaway"):
        assert banned not in json.dumps([naive, bounded, hybrid])


def test_cat6_badge_and_notes_quote_measured_portfolio() -> None:
    r = _run("cat6", preset_id="inc-01")
    row = next(x for x in r["_response"]["portfolio_scorecard"] if x["rung_id"] == "tiered_hybrid_cpo_swarm")
    hybrid = r["tiered_hybrid_cpo_swarm"]
    assert hybrid["badge_text"] == f"Lever 2: CpO Optimized Tier Routing (-{fmt_pct(row['cpo_savings_vs_naive_cold_pct'])} Portfolio CpO)"
    assert f"{row['verified_outcomes_count']}/{row['prs_evaluated']} verified outcomes" in _notes(hybrid)
    naive = r["unisolated_broadcast_swarm"]
    prompt = naive["total_uncached_input_tokens"] + naive["total_cache_creation_tokens"] + naive["total_cache_read_tokens"]
    assert f"({prompt:,} prompt tok this run)" in _notes(naive)
    naive_row = next(x for x in r["_response"]["portfolio_scorecard"] if x["rung_id"] == "unisolated_broadcast_swarm")
    assert (
        "Signs off the patch with no PR-SANDBOX-GATE-01 check or retry before merge; scored afterwards, "
        f"{naive_row['verified_outcomes_count']}/{naive_row['prs_evaluated']} of its {naive_row['prs_evaluated']}-incident "
        f"portfolio patches verified ({naive_row['checks_passed_total']}/{naive_row['checks_total']} sandbox checks)."
    ) in _notes(naive)
    # No copy asserting that the shared bus causes regressions or failed patches
    assert "regression" not in _notes(naive).lower()


def test_cat6_naive_note_falls_back_number_free_without_scorecard() -> None:
    from app.archetypes.cat6_swarms.runner import _rung_metadata

    _, _, notes = _rung_metadata("unisolated_broadcast_swarm")
    assert notes[1] == (
        "Signs off the patch with no PR-SANDBOX-GATE-01 check or retry before merge; the sandbox scores it only afterwards."
    )
    assert not any(ch.isdigit() for ch in notes[1].replace("PR-SANDBOX-GATE-01", ""))
