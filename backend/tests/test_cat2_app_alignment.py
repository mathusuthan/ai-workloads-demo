"""App ↔ Category 2 experiment summary: the four versions (without / with the section template x Sonnet / Haiku),
pending replays, quality block (replay + live), portfolio, measured copy, stop reasons, section regeneration."""

from __future__ import annotations

import asyncio
import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat2_drafting import runner  # noqa: E402
from app.archetypes.cat2_drafting.quality_scoring import LIVE_JUDGE_REASON  # noqa: E402
from app.core import credit_shield as cs  # noqa: E402
from app.core.anthropic_service import AnthropicRawResult  # noqa: E402
from app.data.cat2_fixtures import CAT2_PRESETS  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Cat2RunRequest  # noqa: E402

client = TestClient(app)
SUMMARY = json.loads((BACKEND_DIR / "replays" / "cat2_quality_summary.json").read_text(encoding="utf-8"))
GOLDEN = json.loads((BACKEND_DIR / "replays" / "cat2_golden_replays.json").read_text(encoding="utf-8"))
PRESET_IDS = [p["id"] for p in CAT2_PRESETS]
CELLS = {c["rung_id"]: c for c in SUMMARY["cells"]}
ALL_RUNGS = ["sonnet_unbounded", "haiku_unbounded", "sonnet_templated", "haiku_templated"]


@pytest.fixture(autouse=True)
def isolated_traces_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "traces"
    monkeypatch.setenv("NOVAMART_TRACES_DIR", str(d))
    return d


def _replay(pid: str, **body: Any) -> dict[str, Any]:
    r = client.post("/api/cat2/run", json={"mode": "replay", "preset_id": pid, **body})
    assert r.status_code == 200, r.text
    return r.json()


def _notes(r: dict[str, Any]) -> str:
    return " ".join(r["architectural_notes"])


def test_four_versions_in_order_and_the_golden_matches_the_summary() -> None:
    assert list(runner.RUNG_ORDER) == ALL_RUNGS and Cat2RunRequest().rungs == ALL_RUNGS
    assert GOLDEN["provenance"]["source"] == "cat2_experiment_repeat0" and GOLDEN["provenance"]["repeat_index"] == 0
    for pid in PRESET_IDS:
        golden_rungs = GOLDEN["presets"][pid]["rungs"]
        assert set(golden_rungs) == set(SUMMARY["presets"][pid]["rungs"])
        for rung in golden_rungs:
            assert GOLDEN["presets"][pid]["provenance"][rung]["repeat_index"] == 0
    pending = {r for r in ALL_RUNGS if CELLS[r]["status"] == "pending"}
    assert sorted(pending) == GOLDEN["provenance"]["pending_rungs"]


@pytest.mark.parametrize("pid", PRESET_IDS)
def test_replay_serves_measured_rungs_and_marks_missing_ones_pending(pid: str) -> None:
    data = _replay(pid)
    assert [r["rung_id"] for r in data["results"]] == ALL_RUNGS and data["quality_portfolio"] is not None
    for res in data["results"]:
        rid = res["rung_id"]
        golden = GOLDEN["presets"][pid]["rungs"].get(rid)
        if golden is None:
            assert res["status"] == "pending" and res["error_message"] == runner.REPLAY_PENDING_MESSAGE
            assert res["quality"] is None and res["finops"]["total_cost_usd"] == 0 and res["savings_vs_unbounded_pct"] == 0
            assert runner.REPLAY_PENDING_MESSAGE in res["architectural_notes"]
            continue
        assert res["status"] == "ok" and res["finops"]["output_tokens"] == golden["output_tokens"]
        assert res["stop_reason"] == golden["stop_reason"]
        q, cell = res["quality"], SUMMARY["presets"][pid]["rungs"][rid]
        assert q["source"] == "replay_judged" and q["judge_unavailable_reason"] is None
        assert q["judge_model"] == SUMMARY["judge_model"] and q["passes"] == 1
        assert q["serious_errors"] == cell["serious_errors"] and q["core_facts"] == cell["core_facts"]
        assert {d: v["mean"] for d, v in q["rubric"].items()} == {d: v["mean"] for d, v in cell["rubric"].items()}
        assert len(q["errors"]) == len(cell["errors"]) and q["head_to_head"] == cell["head_to_head"]
        assert q["action_items"] == cell["action_items"]


def test_portfolio_is_the_summary() -> None:
    pf = _replay("brief-01")["quality_portfolio"]
    assert [c["rung_id"] for c in pf["cells"]] == [c["rung_id"] for c in SUMMARY["cells"]]
    for c in pf["cells"]:
        s = CELLS[c["rung_id"]]
        for k in ("status", "drafts", "drafts_planned", "judged_drafts", "serious_per_draft", "core_facts", "detail_facts", "owner", "time_window"):
            assert c[k] == s[k], (c["rung_id"], k)
    assert pf["head_to_head"]["status"] == SUMMARY["head_to_head"]["status"]
    assert pf["passes_per_draft"] == 1 and pf["drafts_per_cell"] == 12 and pf["documents"] == PRESET_IDS


def test_replay_notes_and_callout_state_measured_values() -> None:
    data = _replay("reg-02")
    by = {r["rung_id"]: r for r in data["results"]}
    for rid in ("sonnet_templated", "haiku_templated"):
        r = by[rid]
        q = r["quality"]
        assert f"accuracy {q['rubric']['factual_accuracy']['mean']:.1f}, coverage {q['rubric']['coverage']['mean']:.1f}" in _notes(r)
        assert f"Writes {r['finops']['output_tokens']:,} output tokens" in _notes(r)
        name = "Sonnet 5.5" if rid.startswith("sonnet") else "Haiku 5.5"
        assert f"on {name} the section template writes {r['finops']['output_tokens']:,} output tokens" in data["output_tax_callout"]
    if SUMMARY["head_to_head"]["status"] == "pending":
        assert "quality comparison is pending" in data["output_tax_callout"]
        assert "the unbounded draft is pending" in data["output_tax_callout"]
    joined = " ".join(_notes(r) for r in data["results"]) + data["output_tax_callout"]
    for stale in ("Rung", "Anti-Pattern", "original template", "Same frontier Sonnet 5.5 quality", "complete auditable first draft",
                  "stored documents", "16 of 16"):
        assert stale not in joined, stale


def _complete_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    """Golden + summary with both unbounded rungs present and the head-to-head done (synthetic values)."""
    golden = copy.deepcopy(GOLDEN)
    for p in golden["presets"].values():
        for m in ("sonnet", "haiku"):
            t = p["rungs"][f"{m}_templated"]
            p["rungs"][f"{m}_unbounded"] = {**t, "output_tokens": 4800, "max_tokens": 8000, "raw_markdown": "Long draft. " * 400,
                                            "structured_draft": {"mode": "unbounded_longform_prose", "char_length": 4800}}
    summary = copy.deepcopy(SUMMARY)
    win = {"template_wins": 30, "unbounded_wins": 14, "ties": 4}
    block = {"overall": win, "accuracy": win, "usefulness_to_reader": win, "calls": 48, "position_consistency": {"pairs": 24, "consistent": 20}}
    summary["head_to_head"] = {"status": "ok", "all": block, "by_model": {"sonnet": {**block, "calls": 24}, "haiku": {**block, "calls": 24}}}
    for c in summary["cells"]:
        if c["arm"] == "unbounded":  # set the unbounded cells to known values whether or not the real run is recorded
            c.update({"status": "ok", "drafts": 12, "judged_drafts": 12, "serious_per_draft": 0.5, "minor_per_draft": 1.0,
                      "rubric": {d: 4.0 for d in summary["dimensions"]}})
    return golden, summary


def test_complete_inputs_give_same_model_savings_and_the_head_to_head(monkeypatch: pytest.MonkeyPatch) -> None:
    golden, summary = _complete_inputs()
    monkeypatch.setattr(runner, "load_cat2_replays", lambda: golden)
    monkeypatch.setattr(runner, "load_cat2_quality_summary", lambda: summary)
    data = _replay("brief-02")
    by = {r["rung_id"]: r for r in data["results"]}
    assert all(r["status"] == "ok" for r in data["results"])
    for m in ("sonnet", "haiku"):
        t, u = by[f"{m}_templated"], by[f"{m}_unbounded"]
        assert u["model_id"] == t["model_id"] and u["savings_vs_unbounded_pct"] == 0
        expect = (u["finops"]["total_cost_usd"] - t["finops"]["total_cost_usd"]) / u["finops"]["total_cost_usd"] * 100
        assert t["savings_vs_unbounded_pct"] == pytest.approx(expect, abs=0.01)
        assert f"vs 4,800 for the unbounded draft on the same model" in _notes(t)
        assert f"Writes 4,800 output tokens on this document; output is" in _notes(u)
    assert ("the template draft was preferred in 30 and the unbounded draft in 14 of 48 comparisons (4 ties)" in data["output_tax_callout"])
    # unbounded replays are not graded (no per-draft cell): the version-level note quotes the cell
    assert "the version's 12 experiment drafts averaged accuracy 4.00" in _notes(by["haiku_unbounded"])


def test_quality_absent_without_summary_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "load_cat2_quality_summary", lambda: None)
    data = _replay("brief-02")
    assert data["quality_portfolio"] is None
    assert data["output_tax_callout"].endswith(" Draft quality is not graded on this run.")
    for r in data["results"]:
        if r["status"] == "ok":
            assert r["quality"]["source"] == "live_deterministic" and r["quality"]["rubric"] is None
            assert not any("Measured quality" in n for n in r["architectural_notes"])


def test_stale_summary_cell_is_not_served(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = copy.deepcopy(SUMMARY)
    bad["presets"]["brief-02"]["rungs"]["haiku_templated"]["text_sha256"] = "0" * 64
    monkeypatch.setattr(runner, "load_cat2_quality_summary", lambda: bad)
    by = {r["rung_id"]: r for r in _replay("brief-02")["results"]}
    q = by["haiku_templated"]["quality"]
    assert q["source"] == "live_deterministic" and q["serious_errors"] is None
    assert q["judge_unavailable_reason"] == runner.REPLAY_GRADES_STALE_REASON
    assert by["sonnet_templated"]["quality"]["source"] == "replay_judged"


def test_portfolio_loader_falls_back_to_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _S:
        replays_dir = str(tmp_path)

    monkeypatch.setattr(runner, "get_settings", lambda: _S())
    assert runner.load_cat2_quality_summary() is None and runner.load_cat2_quality_portfolio() is None
    (tmp_path / "cat2_quality_summary.json").write_text("{not json")
    assert runner.load_cat2_quality_summary() is None
    (tmp_path / "cat2_quality_summary.json").write_text('{"schema_version": 1}')
    assert runner.load_cat2_quality_portfolio() is None


def _fake_live(monkeypatch: pytest.MonkeyPatch, replay_rungs: dict[str, Any], seen: list | None = None) -> None:
    def raw(rid: str, stop: str, model: str) -> AnthropicRawResult:
        r = replay_rungs[rid]
        return AnthropicRawResult(model, 5, r["input_tokens"], r["output_tokens"], 0, 0, r.get("raw_markdown") or "",
                                  r.get("structured_draft") or {}, stop_reason=stop)

    async def fake_unbounded(payload: str, system: str, key: str, max_tokens: int = 8000, *, model_tier: str = "claude-sonnet-5-5") -> AnthropicRawResult:
        if seen is not None:
            seen.append(("unbounded", model_tier, max_tokens))
        m = "sonnet" if "sonnet" in model_tier else "haiku"
        r = raw(f"{m}_templated", "max_tokens", model_tier)
        r.raw_text, r.output_tokens, r.structured = "Long draft. " * 400, 8000, {"mode": "unbounded_longform_prose"}
        return r

    async def fake_structured(payload: str, system: str, schema: Any, model_tier: str, *a: Any, **k: Any) -> AnthropicRawResult:
        if seen is not None:
            seen.append(("template", model_tier, k.get("max_tokens")))
        return raw("sonnet_templated" if "sonnet" in model_tier else "haiku_templated", "end_turn", model_tier)

    monkeypatch.setattr(runner, "run_cat2_unbounded_sonnet", fake_unbounded)
    monkeypatch.setattr(runner, "run_cat2_structured_draft", fake_structured)
    monkeypatch.setattr(runner.credit_shield, "resolve_live_credentials", lambda *a, **k: cs.ResolvedCredentials("k", "byok", False))


def test_live_mode_runs_all_four_versions_with_free_checks_and_real_stop_reasons(monkeypatch: pytest.MonkeyPatch) -> None:
    pid = "reg-02"
    seen: list = []
    _fake_live(monkeypatch, runner.load_cat2_replays()["presets"][pid]["rungs"], seen)
    resp = asyncio.run(runner.execute_cat2_run(Cat2RunRequest(preset_id=pid, mode="live")))
    assert sorted(seen) == sorted([("unbounded", "claude-sonnet-5-5", 8000), ("unbounded", "claude-haiku-5-5", 8000),
                                   ("template", "claude-sonnet-5-5", 3000), ("template", "claude-haiku-5-5", 3000)])
    by = {r.rung_id: r for r in resp.results}
    assert [r.rung_id for r in resp.results] == ALL_RUNGS and all(r.status == "ok" for r in resp.results)
    assert by["haiku_unbounded"].model_id == "claude-haiku-5-5" and by["haiku_unbounded"].stop_reason == "max_tokens"
    assert by["haiku_templated"].stop_reason == "end_turn" and by["haiku_templated"].savings_vs_unbounded_pct > 0
    for rid, r in by.items():
        q = r.quality
        assert q is not None and q.source == "live_deterministic" and q.judge_unavailable_reason == LIVE_JUDGE_REASON
        assert q.rubric is None and q.serious_errors is None and q.errors is None and q.head_to_head is None
        if rid.endswith("_templated"):
            cell = SUMMARY["presets"][pid]["rungs"][rid]
            assert q.core_facts.model_dump() == cell["core_facts"] and q.numbers.not_in_source == cell["numbers"]["not_in_source"]
            if CELLS[rid]["rubric"]:
                assert any(f"the version's {CELLS[rid]['drafts']} experiment drafts averaged" in n for n in r.architectural_notes)
    assert "for the unbounded draft" in resp.output_tax_callout and resp.quality_portfolio is not None


def test_live_custom_input_has_numbers_but_no_fact_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_live(monkeypatch, runner.load_cat2_replays()["presets"]["brief-01"]["rungs"])
    resp = asyncio.run(runner.execute_cat2_run(Cat2RunRequest(custom_input="Revenue rose 12% in Q3.", mode="live")))
    for r in resp.results:
        assert r.quality is not None and r.quality.core_facts is None and r.quality.numbers is not None


def test_section_regen_replays_and_has_no_quality_block() -> None:
    from app.data.cat2_fixtures import CAT2_REVIEWER_PRESETS

    pid, sec = "brief-01", "key_findings"
    cur = runner.load_cat2_replays()["presets"][pid]["rungs"]["sonnet_templated"]["structured_draft"][sec]
    for tier in ("claude-haiku-5-5", "claude-sonnet-5-5"):
        r = client.post(
            "/api/cat2/regenerate-section",
            json={"mode": "replay", "preset_id": pid, "section_key": sec, "current_section": cur,
                  "reviewer_instruction": CAT2_REVIEWER_PRESETS[sec]["instruction"], "model_tier": tier},
        )
        assert r.status_code == 200, r.text
        assert "quality" not in r.json() and "quality_portfolio" not in r.json()


# ---------------------------------------------------------------- deck-claims validator, Category 2 section


def _validator():
    import importlib.util

    spec = importlib.util.spec_from_file_location("validate_deck_claims_cat2", BACKEND_DIR / "scripts" / "validate_deck_claims.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cat2_claims(res: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["claim"]: c for c in res["claims"] if c["category"] in ("Cat 2", "Tiers 1–2 rule")}


def test_validator_cat2_reads_the_experiment_cells() -> None:
    v = _validator()
    units, regens = v.cat2_units()
    measured = [r for r in ALL_RUNGS if CELLS[r]["drafts"]]
    assert sorted(units) == sorted(measured) and all(len(units[r]) == CELLS[r]["drafts"] for r in measured)
    res = v.analyse()
    c2 = res["categories"]["cat2"]
    assert c2["pending_rungs"] == [r for r in ALL_RUNGS if r not in measured]
    assert c2["max_cost_diff_vs_summary_per_1k"] < 0.01 and c2["draft_count_mismatch_vs_summary"] == []
    claims = _cat2_claims(res)
    assert claims["Output tokens cost 3–5× input"]["verdict"] == "SUPPORTED"
    if c2["pending_rungs"]:
        for k in ("Input 1,500–4,000 tokens", "Output 800–3,000+ tokens", "Input:output ≈ 1:1 to 1:2 and output-dominated cost",
                  "Section templates + length bounds control output cost", "…without losing draft quality (implicit)"):
            assert claims[k]["verdict"] == "NOT TESTABLE" and "Run pending" in claims[k]["note"], k
        assert "Cat 2 section template vs unbounded draft: run pending" in claims["60–80% lower unit inference cost (Cat 1 & 2)"]["measured"]
    md = "\n".join(v._render_cat2(c2))
    assert "| Without: unbounded long-form draft |" in md and "| With: section template with length caps |" in md
    assert ("run pending" in md) == bool(c2["pending_rungs"]) and "Single-section regeneration" in md
    assert any(t.startswith("**Category 2 owner and time-window check.**") for t in v._known_limits(res))


def test_validator_cat2_with_every_cell_measured(monkeypatch: pytest.MonkeyPatch) -> None:
    v = _validator()
    units, regens = v.cat2_units()
    q, src = v.cat2_quality()
    golden, summary = _complete_inputs()
    for m in ("sonnet", "haiku"):
        units[f"{m}_unbounded"] = [{**u, "calls": [{**u["calls"][0], "in": u["calls"][0]["in"] - 1200, "out": 4800}]} for u in units[f"{m}_templated"]]
    cells = {c["rung_id"]: c for c in summary["cells"]}
    for m in ("sonnet", "haiku"):
        cells[f"{m}_unbounded"].update({"core_facts": {"hits": 95, "total": 96}, "detail_facts": {"hits": 110, "total": 120}, "minor_per_draft": 1.0})
    monkeypatch.setattr(v, "cat2_units", lambda: (units, regens))
    monkeypatch.setattr(v, "cat2_quality", lambda: ({"cells": cells, "h2h": summary["head_to_head"], "counts": summary["counts"]}, src))
    res = v.analyse()
    claims = _cat2_claims(res)
    assert res["categories"]["cat2"]["pending_rungs"] == []
    assert claims["Section templates + length bounds control output cost"]["verdict"] == "SUPPORTED"
    assert claims["Output 800–3,000+ tokens"]["verdict"] == "SUPPORTED"
    assert claims["Input:output ≈ 1:1 to 1:2 and output-dominated cost"]["verdict"] in ("SUPPORTED", "PARTLY SUPPORTED")
    implicit = claims["…without losing draft quality (implicit)"]
    assert implicit["verdict"] in ("SUPPORTED", "PARTLY SUPPORTED", "NOT SUPPORTED") and "template 30 – unbounded 14 – ties 4" in implicit["measured"]
    tiers = claims["60–80% lower unit inference cost (Cat 1 & 2)"]
    assert "(Sonnet) / −" in tiers["measured"] and tiers["verdict"] in ("SUPPORTED", "PARTLY SUPPORTED")
    md = "\n".join(v._render_cat2(res["categories"]["cat2"]))
    assert "run pending" not in md and "template 30 – unbounded 14 – ties 4" in md and "Single-section regeneration" in md
