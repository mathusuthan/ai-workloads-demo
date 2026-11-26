"""App ↔ Category 2 blind-judge quality summary: quality block (replay + live), portfolio, measured copy, stop reasons."""

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
from app.archetypes.cat2_drafting.quality_scoring import LIVE_JUDGE_REASON, RUNG_IDS  # noqa: E402
from app.core import credit_shield as cs  # noqa: E402
from app.core.anthropic_service import AnthropicRawResult  # noqa: E402
from app.data.cat2_fixtures import CAT2_PRESETS  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Cat2RunRequest  # noqa: E402

client = TestClient(app)
SUMMARY = json.loads((BACKEND_DIR / "replays" / "cat2_quality_summary.json").read_text(encoding="utf-8"))
PRESET_IDS = [p["id"] for p in CAT2_PRESETS]


@pytest.fixture(autouse=True)
def isolated_traces_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "traces"
    monkeypatch.setenv("NOVAMART_TRACES_DIR", str(d))
    return d


def _replay(pid: str, **body: Any) -> dict[str, Any]:
    r = client.post("/api/cat2/run", json={"mode": "replay", "preset_id": pid, **body})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("pid", PRESET_IDS)
def test_replay_quality_block_matches_summary(pid: str) -> None:
    data = _replay(pid)
    assert data["quality_portfolio"] is not None
    for res in data["results"]:
        q, cell = res["quality"], SUMMARY["presets"][pid]["rungs"][res["rung_id"]]
        assert q["source"] == "replay_judged" and q["judge_unavailable_reason"] is None
        assert q["judge_model"] == SUMMARY["judge_model"] and q["passes"] == 3
        assert q["serious_errors"] == cell["serious_errors"] and q["core_facts"] == cell["core_facts"]
        assert {d: v["mean"] for d, v in q["rubric"].items()} == {d: v["mean"] for d, v in cell["rubric"].items()}
        assert len(q["errors"]) == len(cell["errors"]) and len(q["head_to_head"]) == 2
        assert all(len(h["results"]) == 2 for h in q["head_to_head"])
        assert (q["action_items"] is None) == (res["rung_id"] == "sonnet_unbounded")


def test_portfolio_matches_lead_numbers() -> None:
    pf = _replay("brief-01")["quality_portfolio"]
    rungs = {r["rung_id"]: r for r in pf["rungs"]}
    assert [rungs[r]["serious_errors"] for r in RUNG_IDS] == [1, 6, 10]
    assert all(rungs[r]["core_facts"] == {"hits": 32, "total": 32} for r in RUNG_IDS)
    means = {r: {d: round(v["mean"], 2) for d, v in rungs[r]["rubric"].items()} for r in RUNG_IDS}
    assert means["sonnet_unbounded"] == {"factual_accuracy": 3.92, "coverage": 4.92, "clarity": 4.0, "actionability": 3.75, "concision": 2.83}
    assert means["sonnet_templated"]["factual_accuracy"] == 3.08 and means["haiku_templated"]["coverage"] == 3.5
    w = pf["pairwise"]["overall"]["wins"]
    assert w["sonnet_unbounded"] == {"sonnet_templated": 8, "haiku_templated": 8}
    assert w["sonnet_templated"]["haiku_templated"] == 7 and w["haiku_templated"]["sonnet_templated"] == 1
    assert pf["calls"] == {"rubric_ok": 36, "pairwise_ok": 24, "error_records": 0}
    assert [round(rungs[r]["cost_per_1k_docs_usd"], 2) for r in RUNG_IDS] == [58.92, 27.25, 1.39]


def test_replay_notes_and_callout_state_measured_quality() -> None:
    data = _replay("reg-02")
    by = {r["rung_id"]: r for r in data["results"]}
    tmpl, haiku, unb = by["sonnet_templated"], by["haiku_templated"], by["sonnet_unbounded"]
    tq = tmpl["quality"]
    assert any(
        f"accuracy {tq['rubric']['factual_accuracy']['mean']:.1f}, coverage {tq['rubric']['coverage']['mean']:.1f}" in n
        and f"{tq['serious_errors']} serious errors" in n
        for n in tmpl["architectural_notes"]
    )
    ai = tq["action_items"]
    owner_note = (
        "The template requires an owner and a time window for every action item; on this document the grader flagged "
        f"an owner or deadline the source does not support in {ai['flagged']} of {ai['total']} action items"
    )
    assert any(owner_note in n for n in tmpl["architectural_notes"])
    assert any("preferred over the unbounded draft in 0 of 2 head-to-head comparisons" in n for n in haiku["architectural_notes"])
    assert any("preferred over the templated drafts in 4 of 4" in n for n in unb["architectural_notes"])
    assert "preferred the unbounded draft in 4 of 4 head-to-head comparisons" in data["output_tax_callout"]
    joined = " ".join(n for r in data["results"] for n in r["architectural_notes"]) + data["output_tax_callout"]
    for stale in ("Same frontier Sonnet 5.5 quality", "complete auditable first draft", "Exposed", "entire invoice!",
                  "disabled thinking", "with selective HITL escalation"):
        assert stale not in joined, stale


def test_brief01_owner_note_reports_zero_when_source_gives_owners() -> None:
    by = {r["rung_id"]: r for r in _replay("brief-01")["results"]}
    for rid in ("sonnet_templated", "haiku_templated"):
        assert by[rid]["quality"]["action_items"] == {"total": 3, "flagged": 0, "flagged_serious": 0}
        assert any("in 0 of 3 action items" in n for n in by[rid]["architectural_notes"])


def test_quality_absent_without_summary_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner, "load_cat2_quality_summary", lambda: None)
    data = _replay("brief-02")
    assert data["quality_portfolio"] is None
    # The baseline grades are gone; the separately measured template fix (independent file) may still follow.
    assert " Draft quality is not graded on this run." in data["output_tax_callout"]
    for r in data["results"]:
        # Without the summary the replay falls back to the free checks with the judge fields empty.
        assert r["quality"]["source"] == "live_deterministic" and r["quality"]["rubric"] is None
        assert not any("Measured quality" in n or "stored documents" in n for n in r["architectural_notes"])


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


def _fake_live(monkeypatch: pytest.MonkeyPatch, replay_rungs: dict[str, Any]) -> None:
    def raw(rid: str, stop: str) -> AnthropicRawResult:
        r = replay_rungs[rid]
        return AnthropicRawResult(
            r["model_id"], 5, r["input_tokens"], r["output_tokens"], 0, 0, r.get("raw_markdown") or "",
            r.get("structured_draft") or {}, stop_reason=stop,
        )

    async def fake_unbounded(*a: Any, **k: Any) -> AnthropicRawResult:
        return raw("sonnet_unbounded", "max_tokens")

    async def fake_structured(payload: str, system: str, schema: Any, model_tier: str, *a: Any, **k: Any) -> AnthropicRawResult:
        return raw("sonnet_templated" if "sonnet" in model_tier else "haiku_templated", "end_turn")

    monkeypatch.setattr(runner, "run_cat2_unbounded_sonnet", fake_unbounded)
    monkeypatch.setattr(runner, "run_cat2_structured_draft", fake_structured)
    monkeypatch.setattr(
        runner.credit_shield,
        "resolve_live_credentials",
        lambda *a, **k: cs.ResolvedCredentials("k", None, "byok", "none", False),
    )


def test_live_mode_computes_free_checks_and_records_real_stop_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    pid = "reg-02"
    _fake_live(monkeypatch, runner.load_cat2_replays()["presets"][pid]["rungs"])
    resp = asyncio.run(runner.execute_cat2_run(Cat2RunRequest(preset_id=pid, mode="live")))
    by = {r.rung_id: r for r in resp.results}
    assert by["sonnet_unbounded"].stop_reason == "max_tokens" and by["haiku_templated"].stop_reason == "end_turn"
    for rid, r in by.items():
        q = r.quality
        assert q is not None and q.source == "live_deterministic" and q.judge_unavailable_reason == LIVE_JUDGE_REASON
        assert q.rubric is None and q.serious_errors is None and q.errors is None and q.head_to_head is None
        cell = SUMMARY["presets"][pid]["rungs"][rid]
        assert q.core_facts.model_dump() == cell["core_facts"] and q.detail_facts.model_dump() == cell["detail_facts"]
        assert q.numbers.not_in_source == cell["numbers"]["not_in_source"]
        assert all(i.verdict is None for i in q.numbers.items)
        assert any("Quality is not graded on this run; on the 4 stored documents" in n for n in r.architectural_notes)
    assert "Quality is not graded on this run; on the 4 stored documents the blind grader preferred the unbounded draft in 16 of 16" in resp.output_tax_callout
    assert resp.quality_portfolio is not None


def test_live_custom_input_has_numbers_but_no_fact_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_live(monkeypatch, runner.load_cat2_replays()["presets"]["brief-01"]["rungs"])
    resp = asyncio.run(runner.execute_cat2_run(Cat2RunRequest(custom_input="Revenue rose 12% in Q3.", mode="live")))
    for r in resp.results:
        assert r.quality is not None and r.quality.core_facts is None and r.quality.numbers is not None
        assert r.quality.numbers.not_in_source > 0


def test_section_regen_has_no_quality_block() -> None:
    from app.data.cat2_fixtures import CAT2_REVIEWER_PRESETS

    pid = "brief-01"
    sec = "key_findings"
    cur = runner.load_cat2_replays()["presets"][pid]["rungs"]["sonnet_templated"]["structured_draft"][sec]
    r = client.post(
        "/api/cat2/regenerate-section",
        json={"mode": "replay", "preset_id": pid, "section_key": sec, "current_section": cur,
              "reviewer_instruction": CAT2_REVIEWER_PRESETS[sec]["instruction"], "model_tier": "claude-haiku-5-5"},
    )
    assert r.status_code == 200, r.text
    assert "quality" not in r.json() and "quality_portfolio" not in r.json()


# ---------------------------------------------------------------- template fix (not_stated follow-up)

FIX = json.loads((BACKEND_DIR / "replays" / "cat2_not_stated_summary.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("pid", PRESET_IDS)
def test_template_fix_block_on_every_replay(pid: str) -> None:
    data = _replay(pid)
    tf = data["template_fix"]
    assert tf is not None and tf["app_template"] == "template_original"
    assert tf["added_instruction"] == FIX["added_instruction"] and len(tf["cells"]) == 4
    assert tf["head_to_head"]["vs_unbounded"]["all"]["overall"] == {"wins": 1, "losses": 15, "ties": 0}


def test_template_fix_notes_and_callout_quote_the_summary() -> None:
    data = _replay("reg-02")
    by = {r["rung_id"]: r for r in data["results"]}
    cell = {(c["arm"], c["model_key"]): c for c in FIX["cells"]}
    for rid, m in (("sonnet_templated", "sonnet"), ("haiku_templated", "haiku")):
        o, n = cell[("template_original", m)], cell[("template_not_stated", m)]
        note = by[rid]["architectural_notes"][3]
        assert note.startswith("The template requires an owner and a time window")
        assert f"cut serious errors per draft from {o['serious_per_draft']:.2f} to {n['serious_per_draft']:.2f}" in note
        assert "not used by the app" in note
    assert not any("Measured fix" in n for n in by["sonnet_unbounded"]["architectural_notes"])
    assert "the long draft was still preferred in 15 of 16 comparisons; the app keeps the original template." in data["output_tax_callout"]


def test_template_fix_absent_gives_none_and_number_free_pointer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "load_cat2_template_fix", lambda: None)
    data = _replay("reg-02")
    assert data["template_fix"] is None and "Measured fix" not in data["output_tax_callout"]
    note = {r["rung_id"]: r for r in data["results"]}["sonnet_templated"]["architectural_notes"][3]
    assert note.endswith(runner.FIX_POINTER_FALLBACK) and not any(ch.isdigit() for ch in runner.FIX_POINTER_FALLBACK)


def test_template_fix_loader_falls_back_to_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _S:
        replays_dir = str(tmp_path)

    monkeypatch.setattr(runner, "get_settings", lambda: _S())
    assert runner.load_cat2_template_fix() is None
    (tmp_path / "cat2_not_stated_summary.json").write_text("{not json")
    assert runner.load_cat2_template_fix() is None


def test_template_fix_present_in_live_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_live(monkeypatch, runner.load_cat2_replays()["presets"]["brief-01"]["rungs"])
    resp = asyncio.run(runner.execute_cat2_run(Cat2RunRequest(custom_input="Revenue rose 12% in Q3.", mode="live")))
    assert resp.template_fix is not None and resp.template_fix.counts["drafts"] == 48
