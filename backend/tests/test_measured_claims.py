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
    for model in ("sonnet", "haiku"):
        prose, schema = r[f"{model}_naive"], r[f"{model}_calibrated"]
        same_model_cut = (1 - schema["finops"]["total_cost_usd"] / prose["finops"]["total_cost_usd"]) * 100
        assert f"classification-only answer is {schema['finops']['output_tokens']:,} output tokens" in _notes(schema)
        assert f"vs {prose['finops']['output_tokens']:,} for the write-up on the same model, cutting cost {fmt_pct(same_model_cut)}" in _notes(schema)
        assert f"Writes {prose['finops']['output_tokens']:,} output tokens on this item" in _notes(prose)
    for x in r.values():
        if isinstance(x, dict) and "architectural_notes" in x:
            low = _notes(x).lower()
            assert "gemini" not in low and "plain text" not in low and "default thinking" not in low


def test_cat1_live_write_up_is_not_scored_and_says_why() -> None:
    from app.archetypes.cat1_triage.runner import live_prose_accuracy_note, load_cat1_ablation_portfolio

    note = live_prose_accuracy_note(load_cat1_ablation_portfolio())
    assert note == "Not scored live: reading a write-up needs a reader model, which the app does not call."
    assert live_prose_accuracy_note(None) == note


def test_cat2_badges_and_notes_quote_measured_values() -> None:
    from app.archetypes.cat2_drafting.runner import REPLAY_PENDING_MESSAGE

    r = _run("cat2", preset_id="brief-02", sub_task="exec_synthesis")
    for rid in ("sonnet_unbounded", "haiku_unbounded", "sonnet_templated", "haiku_templated"):
        x, name = r[rid], ("Sonnet" if rid.startswith("sonnet") else "Haiku")
        assert x["badge_text"] == f"{'Without' if rid.endswith('_unbounded') else 'With'} the Improvement · {name}"
        if x["status"] == "pending":
            assert REPLAY_PENDING_MESSAGE in x["architectural_notes"]
            continue
        f = x["finops"]
        if rid.endswith("_unbounded"):
            assert f"Writes {f['output_tokens']:,} output tokens on this document; output is {fmt_pct(f['output_cost_share_pct'])} of its cost." in _notes(x)
            continue
        w = r[rid.replace("_templated", "_unbounded")]
        if w["status"] == "ok":
            assert f"vs {w['finops']['output_tokens']:,} for the unbounded draft on the same model" in _notes(x)
            assert f"cutting cost {fmt_pct(x['savings_vs_unbounded_pct'])}" in _notes(x)
        else:
            assert f"Writes {f['output_tokens']:,} output tokens (${f['total_cost_usd']:.4f} for this draft)." in _notes(x)
        q = x["quality"]
        assert f"accuracy {q['rubric']['factual_accuracy']['mean']:.1f}, coverage {q['rubric']['coverage']['mean']:.1f}" in _notes(x)


def test_cat2_template_rung_alone_states_its_own_output_only() -> None:
    r = _run("cat2", preset_id="brief-02", sub_task="exec_synthesis", rungs=["haiku_templated"])
    x = r["haiku_templated"]
    assert x["badge_text"] == "With the Improvement · Haiku" and x["savings_vs_unbounded_pct"] == 0
    assert f"Writes {x['finops']['output_tokens']:,} output tokens (${x['finops']['total_cost_usd']:.4f} for this draft)." in _notes(x)
    assert "for the unbounded draft" not in _notes(x)
    assert "the unbounded draft was not run" in r["_response"]["output_tax_callout"]


def test_cat3_notes_quote_measured_prefix_and_final_context() -> None:
    r = _run("cat3", preset_id="desk-01")
    assert set(k for k in r if not k.startswith("_")) == {"naive_full_history", "prefix_cached_summarized"}
    first = r["prefix_cached_summarized"]["turns"][0]["finops"]
    prefix = first["cache_creation_tokens"] + first["cache_read_tokens"]
    assert f"~{prefix:,}-tok IT/HR Handbook prefix" in _notes(r["naive_full_history"])
    last = r["prefix_cached_summarized"]["turns"][-1]["finops"]
    ctx = last["input_tokens"] + last["cache_creation_tokens"] + last["cache_read_tokens"]
    assert f"it holds Turn 10 context to {ctx:,} tok" in _notes(r["prefix_cached_summarized"])
    assert "without the improvement" in _notes(r["prefix_cached_summarized"])
    assert f"~{prefix:,}-tok handbook prefix" in r["_response"]["session_callout"]


def _frac(m: dict) -> str:
    return f"{m['hits']}/{m['total']}"


@pytest.mark.parametrize("preset", ["desk-01", "desk-02"])
def test_cat3_notes_and_callout_quote_measured_quality(preset: str) -> None:
    r = _run("cat3", preset_id=preset)
    nq, sq = r["naive_full_history"]["quality"], r["prefix_cached_summarized"]["quality"]
    assert nq and sq and sq["probes"] and len(sq["probes"]) == 6
    summ_note = r["prefix_cached_summarized"]["architectural_notes"][2]
    assert summ_note.startswith("Quality trade-off on this session:")
    assert f"answered {_frac(sq['probe_accuracy'])} recall questions vs {_frac(nq['probe_accuracy'])} without the improvement" in summ_note
    assert f"kept {_frac(sq['ledger_by_origin']['1-3'])} turn 1–3 details" in summ_note
    pf = {x["rung_id"]: x for x in r["_response"]["quality_portfolio"]["rungs"]}
    assert set(pf) == {"naive_full_history", "prefix_cached_summarized"}
    assert (f"{_frac(pf['prefix_cached_summarized']['probe_accuracy'])} recall questions vs "
            f"{_frac(pf['naive_full_history']['probe_accuracy'])}") in summ_note
    callout = r["_response"]["session_callout"]
    assert "Quality trade-off:" in callout and f"{_frac(sq['probe_accuracy'])} recall" in callout
    assert "Rung" not in callout and "lossless" not in callout


def test_cat3_quality_notes_fall_back_number_free_without_scores() -> None:
    from app.archetypes.cat3_assistants import runner

    r = _run("cat3", preset_id="desk-01")
    results = [runner.Cat3RungSummary.model_validate(r[k]) for k in ("naive_full_history", "prefix_cached_summarized")]
    defaults = {rid: runner._rung_metadata(rid)[2] for rid in r if not rid.startswith("_")}
    for res in results:
        res.quality = None
        res.architectural_notes = list(defaults[res.rung_id])
    runner._apply_measured_claims(results, None)
    summ = results[1].architectural_notes[2]
    assert summ.startswith("Quality trade-off:") and not any(ch.isdigit() for ch in summ)
    assert "not free of quality cost" in runner._quality_callout(results[1], results[0], None)


def test_cat4_badge_and_notes_quote_measured_values() -> None:
    r = _run("cat4", preset_id="audit-01")
    assert set(k for k in r if not k.startswith("_")) == {"naive_full_corpus", "cached_rerank_hybrid"}
    naive, paired = r["naive_full_corpus"], r["cached_rerank_hybrid"]
    avg_red = sum(q["context_reduction_pct"] for q in paired["queries"]) / len(paired["queries"])
    assert paired["badge_text"] == f"With the improvement: ~{fmt_pct(avg_red)} of Corpus Not Sent to Sonnet + Citations"
    cut = (1 - paired["single_query_cold_per_1k_usd"] / naive["single_query_cold_per_1k_usd"]) * 100
    assert f"a single cold question costs {fmt_pct(cut)} less than without the improvement" in _notes(paired)
    block = paired["queries"][0]["reranker_finops"]
    assert f"one cached ~{block['cache_creation_tokens'] + block['cache_read_tokens']:,}-tok block" in _notes(paired)
    for rung in (naive, paired):  # note 3: this audit's measured quality
        q = rung["quality"]["audit"]
        kf = q["key_facts"]
        assert f"stated {kf['hits']}/{kf['total']} key contract facts" in rung["architectural_notes"][2]
        assert f"{q['correctness_mean']:.2f}/5" in rung["architectural_notes"][2]
    assert "Rung" not in r["_response"]["rag_callout"]


def test_cat4_fallback_copy_is_number_free_and_makes_no_unsupported_claims() -> None:
    from app.archetypes.cat4_rag import runner as cat4_runner

    blob = []
    for rid in ("naive_full_corpus", "cached_rerank_hybrid"):
        title, badge, _, notes = cat4_runner._rung_metadata(rid)
        blob += [badge, *notes]
        assert not any(ch.isdigit() for ch in notes[2])
    paired_notes = cat4_runner._rung_metadata("cached_rerank_hybrid")[3]
    assert "not in the text provided" in paired_notes[3]
    assert len(cat4_runner._rung_metadata("naive_full_corpus")[3]) == 3
    text = " ".join(blob).lower()
    for banned in ("95%", "zero-hallucination", "without chunking or missing", "linearly", "decisive", "rung"):
        assert banned not in text
    summ = cat4_runner.finalize_cat4_rung_summary(rung_id="cached_rerank_hybrid", model_id="m", queries=[])
    cat4_runner._apply_measured_claims([summ], None)  # no ok rung -> fallback copy stays
    assert summ.badge_text == "With the improvement"


@pytest.mark.parametrize("preset", ["inv-01", "inv-02", "inv-03"])
def test_cat5_badge_and_notes_quote_measured_values(preset: str) -> None:
    from app.archetypes.cat5_orchestration.runner import load_cat5_ablation_portfolio

    r = _run("cat5", preset_id=preset)
    naive, bounded, hybrid = r["unbounded_sonnet_loop"], r["bounded_sonnet_cached_gate"], r["hybrid_haiku_sonnet_governed"]
    # badges say without / with the deck's lever; no fixed cost claim in a badge
    assert naive["badge_text"] == "Without the Lever: Raw Tables, No Cache"
    assert bounded["badge_text"] == "With the Lever: Step Budget + Policy Tool"
    assert hybrid["badge_text"] == "With the Lever, Haiku-First"
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
    without = next(a for a in port.arms if a.arm_id == "raw_free_sonnet")
    assert f"{gated.exact}/{gated.runs}" in _notes(bounded) and f"${gated.cost_per_1k_cold_usd:.2f} cold" in _notes(bounded)
    assert f"{without.exact}/{without.runs}" in _notes(bounded) and f"${without.cost_per_1k_cold_usd:.2f}" in _notes(bounded)
    assert f"${tiered.cost_per_1k_cold_usd:.2f} cold" in _notes(hybrid) and f"${tiered.cost_per_1k_warm_usd:.2f} warm" in _notes(hybrid)
    assert f"{tiered.escalation_fired}/{tiered.runs}" in _notes(hybrid) and "multi-factor" in _notes(hybrid)
    for banned in ("-92%", "Cost)", "quadratic", "runaway", "every debit note", "before the fix"):
        assert banned not in json.dumps([naive, bounded, hybrid])


def test_cat6_badge_and_notes_quote_measured_portfolio() -> None:
    r = _run("cat6", preset_id="inc-01")
    row = next(x for x in r["_response"]["portfolio_scorecard"] if x["rung_id"] == "tiered_hybrid_cpo_swarm")
    hybrid = r["tiered_hybrid_cpo_swarm"]
    assert hybrid["badge_text"] == (
        f"With the lever, Haiku agents + Sonnet patch author (-{fmt_pct(row['cpo_savings_vs_naive_cold_pct'])} portfolio CpO vs rung 1)"
    )
    assert f"{row['verified_outcomes_count']}/{row['prs_evaluated']} of its" in _notes(hybrid)
    naive = r["unisolated_broadcast_swarm"]
    prompt = naive["total_uncached_input_tokens"] + naive["total_cache_creation_tokens"] + naive["total_cache_read_tokens"]
    assert f"({prompt:,} prompt tok this run)" in _notes(naive)
    naive_row = next(x for x in r["_response"]["portfolio_scorecard"] if x["rung_id"] == "unisolated_broadcast_swarm")
    assert (
        "Same role instructions, output caps, PR-SANDBOX-GATE-01 and one-retry limit as the isolated rungs; "
        f"{naive_row['verified_outcomes_count']}/{naive_row['prs_evaluated']} of its {naive_row['prs_evaluated']}-incident "
        f"portfolio patches verified ({naive_row['checks_passed_total']}/{naive_row['checks_total']} sandbox checks)."
    ) in _notes(naive)
    # No copy asserting that the shared bus causes regressions or failed patches
    assert "regression" not in _notes(naive).lower()


def test_cat6_naive_note_falls_back_number_free_without_scorecard() -> None:
    from app.archetypes.cat6_swarms.runner import _rung_metadata

    _, _, notes = _rung_metadata("unisolated_broadcast_swarm")
    assert notes[1] == (
        "Same role instructions, output caps, PR-SANDBOX-GATE-01 and one-retry limit as the isolated rungs; "
        "only the context design differs."
    )
    assert not any(ch.isdigit() for ch in notes[1].replace("PR-SANDBOX-GATE-01", ""))
