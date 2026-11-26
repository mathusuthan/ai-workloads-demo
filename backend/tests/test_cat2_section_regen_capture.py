"""Category 2 section-regeneration capture: plan, resume, guard, golden build, and (after the live run) provenance."""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from app.archetypes.cat2_drafting import quality_scoring as qs
from app.archetypes.cat2_drafting import runner
from app.archetypes.cat2_drafting import section_regen_capture as rc
from app.core.anthropic_service import AnthropicRawResult
from app.data.cat2_fixtures import CAT2_REVIEWER_PRESETS

BACKEND = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, BACKEND / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def golden() -> dict[str, Any]:
    return json.loads(qs.REPLAYS_PATH.read_text(encoding="utf-8"))


class FakeRegen:
    def __init__(self, *, truncate: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.truncate = truncate

    async def __call__(self, *, system: str, payload: str, schema: dict[str, Any], model_tier: str, max_tokens: int) -> AnthropicRawResult:
        sk = next(iter(schema["properties"])) if "properties" in schema else "x"
        self.calls.append({"system": system, "payload": payload, "model_tier": model_tier, "max_tokens": max_tokens, "section": sk})
        sd = {sk: {"rewritten": True}} if not self.truncate else {}
        return AnthropicRawResult(model_tier, 700, 4400, 500, 0, 0, json.dumps(sd), sd,
                                  request_params={"max_tokens": max_tokens}, stop_reason="max_tokens" if self.truncate else "end_turn")


def test_plan_is_32_app_requests_on_the_same_models_templated_draft(golden):
    plan = rc.plan_regens(golden)
    assert len(plan) == 32 and len({p["regen_key"] for p in plan}) == 32
    presets = qs.preset_map()
    for p in plan:
        rung = golden["presets"][p["preset_id"]]["rungs"][f"{p['model_key']}_templated"]
        assert p["prior_section"] == rung["structured_draft"][p["section_key"]]
        assert p["base_draft_id"] == golden["presets"][p["preset_id"]]["provenance"][f"{p['model_key']}_templated"]["draft_id"]
        assert p["base_draft_id"].endswith(":r0")
        assert p["max_tokens"] == runner.SECTION_REGEN_MAX_TOKENS == 1800
        assert p["reviewer_instruction"] == CAT2_REVIEWER_PRESETS[p["section_key"]]["instruction"]
        assert p["system"] == runner.get_section_regen_system_prompt(presets[p["preset_id"]]["sub_task"], p["section_key"])
        assert p["schema"] == runner.get_single_section_schema(p["section_key"])
        assert p["payload"] == runner.build_section_regen_payload(source_text=presets[p["preset_id"]]["payload"], section_key=p["section_key"],
                                                                  current_section=p["prior_section"], reviewer_instruction=p["reviewer_instruction"])


def test_dry_run_makes_no_calls(tmp_path, capsys):
    script = _load_script("capture_cat2_section_regens")
    fake = FakeRegen()
    assert script.main(["--dry-run", "--out", str(tmp_path / "r.jsonl")], regen_call=fake) == 0
    out = capsys.readouterr().out
    assert fake.calls == [] and not (tmp_path / "r.jsonl").exists()
    assert "Planned 32 regenerations" in out and "worst = 1,800 output tokens" in out and "Dry run: no API calls made." in out


def test_capture_resume_errors_and_guard(tmp_path, capsys):
    script = _load_script("capture_cat2_section_regens")
    out = tmp_path / "r.jsonl"

    async def call(**kw):  # every Haiku action_plan call fails
        if "(`action_plan`)" in kw["payload"] and "haiku" in kw["model_tier"]:
            raise RuntimeError("simulated 529")
        return await FakeRegen()(**kw)

    assert script.main(["--out", str(out), "--max-usd", "5", "--concurrency", "3"], regen_call=call) == 0
    recs = rc.load_records(out)
    assert len(recs) == 32
    assert sum(r["status"] == "error" for r in recs) == 4
    assert all("cost_usd" not in r and "cost_per_1k_docs_usd" not in r for r in recs)
    assert all(r["payload"] and r["system"] and r["schema"] for r in recs)
    capsys.readouterr()
    # resume: only the 4 error keys are sent again; error records stay in the file
    again = FakeRegen()
    assert script.main(["--out", str(out), "--max-usd", "5"], regen_call=again) == 0
    assert len(again.calls) == 4 and len(rc.load_records(out)) == 36
    assert "Error records in the file: 4" in capsys.readouterr().out
    # nothing left
    third = FakeRegen()
    assert script.main(["--out", str(out), "--max-usd", "5"], regen_call=third) == 0
    assert third.calls == []


def test_guard_refuses_over_cap(tmp_path):
    script = _load_script("capture_cat2_section_regens")
    fake = FakeRegen()
    assert script.main(["--out", str(tmp_path / "r.jsonl"), "--max-usd", "0.05", "--concurrency", "1"], regen_call=fake) == 0
    assert 0 < len(fake.calls) < 32


def test_truncation_is_recorded_not_retried(tmp_path):
    script = _load_script("capture_cat2_section_regens")
    out = tmp_path / "r.jsonl"
    assert script.main(["--out", str(out), "--max-usd", "5"], regen_call=FakeRegen(truncate=True)) == 0
    recs = rc.load_records(out)
    assert all(r["status"] == "ok" and r["truncated"] and r["stop_reason"] == "max_tokens" and not r["parse_ok"] for r in recs)
    again = FakeRegen()
    assert script.main(["--out", str(out), "--max-usd", "5"], regen_call=again) == 0
    assert again.calls == []


def test_golden_build_writes_block_from_records_and_refuses_partial(tmp_path, golden):
    cap = _load_script("capture_cat2_section_regens")
    build = _load_script("build_cat2_golden_from_experiment")
    regens = tmp_path / "r.jsonl"
    assert cap.main(["--out", str(regens), "--max-usd", "5"], regen_call=FakeRegen()) == 0
    lines = regens.read_text(encoding="utf-8").splitlines()
    partial = tmp_path / "partial.jsonl"
    partial.write_text("\n".join(lines[:31]) + "\n", encoding="utf-8")
    out_g, out_s = tmp_path / "g.json", tmp_path / "s.json"
    out_g.write_text(json.dumps(golden), encoding="utf-8")
    assert build.main(["--out", str(out_g), "--summary-out", str(out_s), "--regens", str(partial)]) == 1
    assert json.loads(out_g.read_text(encoding="utf-8")) == golden  # untouched
    assert build.main(["--out", str(out_g), "--summary-out", str(out_s), "--regens", str(regens)]) == 0
    g = json.loads(out_g.read_text(encoding="utf-8"))
    assert g["presets"] == golden["presets"]
    block = g["section_regens"]
    assert sum(len(m) for secs in block.values() for m in secs.values()) == 32
    for pid, secs in block.items():
        for sk, by_model in secs.items():
            for tier, r in by_model.items():
                rung = "sonnet_templated" if "sonnet" in tier else "haiku_templated"
                assert r["prior_section"] == golden["presets"][pid]["rungs"][rung]["structured_draft"][sk]
                assert r["updated_section"] == {"rewritten": True} and r["stop_reason"] == "end_turn"
                assert r["provenance"]["base_draft_id"] == golden["presets"][pid]["provenance"][rung]["draft_id"]
    # deterministic
    first = out_g.read_text(encoding="utf-8")
    assert build.main(["--out", str(out_g), "--summary-out", str(out_s), "--regens", str(regens)]) == 0
    assert out_g.read_text(encoding="utf-8") == first


def test_stale_when_base_draft_changes(golden):
    plan = rc.plan_regens(golden)
    recs = [asyncio.run(rc.execute_regen(p, regen_call=FakeRegen())) for p in plan]
    g2 = copy.deepcopy(golden)
    g2["presets"]["brief-01"]["rungs"]["haiku_templated"]["structured_draft"]["executive_summary"] = {"changed": 1}
    plan2 = rc.plan_regens(g2)
    assert rc.stale_keys(plan2, recs) == ["regen:brief-01:executive_summary:haiku"]
    assert [p["regen_key"] for p in rc.select_pending(plan2, recs)] == ["regen:brief-01:executive_summary:haiku"]
    with pytest.raises(ValueError):
        rc.build_section_regens_block(plan2, recs)


def test_comparison_is_against_the_same_models_full_template_draft(golden):
    for tier, rung in (("claude-sonnet-5-5", "sonnet_templated"), ("claude-haiku-5-5", "haiku_templated")):
        d = golden["presets"]["brief-01"]["rungs"][rung]
        c = runner.build_hitl_cost_comparison(model_id=tier, surgical_in_tokens=4400, surgical_out_tokens=500,
                                              section_key="action_plan", preset_id="brief-01", replays=golden)
        assert c.naive_full_reprompt_finops.model_id == tier
        assert (c.naive_full_reprompt_finops.input_tokens, c.naive_full_reprompt_finops.output_tokens) == (d["input_tokens"], d["output_tokens"])
        custom = runner.build_hitl_cost_comparison(model_id=tier, surgical_in_tokens=4400, surgical_out_tokens=500,
                                                   section_key="action_plan", preset_id=None, replays=golden)
        outs = [golden["presets"][p]["rungs"][rung]["output_tokens"] for p in qs.PRESET_IDS]
        assert custom.naive_full_reprompt_finops.output_tokens == round(sum(outs) / len(outs))
        assert "full" in custom.explanation and "template draft" in custom.explanation


def test_validator_compares_each_regeneration_with_its_own_models_template_draft(tmp_path, monkeypatch, golden):
    v = _load_script("validate_deck_claims")
    path = tmp_path / "r.jsonl"

    async def call(*, system, payload, schema, model_tier, max_tokens):
        sk = next(iter(schema["properties"]))
        return AnthropicRawResult(model_tier, 700, 4500, 480 if "sonnet" in model_tier else 590, 0, 0, "{}", {sk: {"x": 1}}, stop_reason="end_turn")

    recs = [asyncio.run(rc.execute_regen(p, regen_call=call)) for p in rc.plan_regens(golden)]
    path.write_text("".join(json.dumps(r) + "\n" for r in recs[:31]), encoding="utf-8")
    monkeypatch.setattr(v, "CAT2_REGENS", path)
    assert v.cat2_units()[1] == {}  # incomplete -> nothing shown
    path.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    regens = v.cat2_units()[1]
    assert {m: len(x) for m, x in regens.items()} == {v.SONNET: 16, v.HAIKU: 16}
    for m, rung in ((v.SONNET, "sonnet_templated"), (v.HAIKU, "haiku_templated")):
        bases = {(x["item"], x["base_call"]["in"], x["base_call"]["out"]) for x in regens[m]}
        assert bases == {(pid, golden["presets"][pid]["rungs"][rung]["input_tokens"], golden["presets"][pid]["rungs"][rung]["output_tokens"]) for pid in qs.PRESET_IDS}
    res = v.analyse()
    claim = next(c for c in res["claims"] if c["claim"] == "Section templates + length bounds control output cost")
    assert "one-section regeneration vs the full template draft it was made on, same model: Sonnet −" in claim["measured"]
    assert ", Haiku −" in claim["measured"] and "(n=16 regenerations per model on the 4 repeat-0 template drafts)" in claim["measured"]
    md = "\n".join(v._render_cat2(res["categories"]["cat2"]))
    assert "for the full Sonnet template draft" in md and "for the full Haiku template draft" in md and "0 truncated." in md
    # a record made on a different base draft is not counted
    stale = [dict(r, base_section_sha256="0" * 64) if i == 0 else r for i, r in enumerate(recs)]
    path.write_text("".join(json.dumps(r) + "\n" for r in stale), encoding="utf-8")
    assert v.cat2_units()[1] == {}


def test_live_regen_uses_the_requested_models_template_draft_and_records_the_stop_reason(monkeypatch, golden, tmp_path):
    from types import SimpleNamespace

    from app.models import Cat2SectionRegenRequest

    sent: dict[str, Any] = {}

    async def fake_draft(payload, system, schema, model_tier, api_key, max_tokens=3000, **kw):
        sent.update(payload=payload, system=system, schema=schema, model_tier=model_tier, max_tokens=max_tokens)
        return AnthropicRawResult(model_tier, 650, 4400, 520, 0, 0, "{}", {"action_plan": [{"x": 1}]}, stop_reason="end_turn", thinking_tokens=0)

    monkeypatch.setattr(runner, "run_cat2_structured_draft", fake_draft)
    monkeypatch.setattr(runner.credit_shield, "resolve_live_credentials",
                        lambda *a, **k: SimpleNamespace(anthropic_api_key="k", uses_server_budget=False))
    monkeypatch.setattr(runner, "persist_cat2_trace", lambda **kw: sent.setdefault("trace", kw))
    req = Cat2SectionRegenRequest(preset_id="reg-01", sub_task="regulatory_filing", section_key="action_plan", reviewer_instruction="",
                                  model_tier="claude-haiku-5-5", mode="live")
    resp = asyncio.run(runner.execute_cat2_section_regen(req))
    plan = {p["regen_key"]: p for p in rc.plan_regens(golden)}["regen:reg-01:action_plan:haiku"]
    assert (sent["payload"], sent["system"], sent["schema"], sent["max_tokens"]) == (plan["payload"], plan["system"], plan["schema"], 1800)
    assert sent["trace"]["stop_reason"] == "end_turn"
    full = resp.finops_comparison.naive_full_reprompt_finops
    assert full.model_id == "claude-haiku-5-5" and full.output_tokens == golden["presets"]["reg-01"]["rungs"]["haiku_templated"]["output_tokens"]


_CAPTURED = rc.REGENS_PATH.is_file() and bool(rc.load_records())


@pytest.mark.skipif(not _CAPTURED, reason="passes only after scripts/capture_cat2_section_regens.py has been run live and the golden file rebuilt")
def test_golden_section_regens_come_from_the_current_capture(golden):
    plan = rc.plan_regens(golden)
    assert golden["section_regens"] == rc.build_section_regens_block(plan, rc.load_records())
    assert golden["provenance"].get("section_regens_file") == rc.REGENS_FILE_LABEL
