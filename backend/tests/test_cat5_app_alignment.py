"""App <-> Category 5 ablation alignment: live loop, rung-1 prompt, golden builder, ablation portfolio, capture
validation, trace seeding and the validation report's Category 5 section. No live API calls."""

from __future__ import annotations

import asyncio
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

from app.archetypes.cat5_orchestration import ablation, runner  # noqa: E402
from app.archetypes.cat5_orchestration.prompts import CAT5_FREE_CHOICE_PROTOCOL, get_cat5_system_prompt  # noqa: E402
from app.core.anthropic_service import AnthropicRawResult  # noqa: E402
from app.data.cat5_fixtures import AP_POLICY_MANUAL_MARKDOWN, CAT5_PRESETS  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Cat5AblationPortfolio  # noqa: E402

RUNS = BACKEND_DIR / "experiments" / "cat5_ablation" / "runs.jsonl"
HAVE_ABLATION = RUNS.is_file()
APP_RUNGS = ("unbounded_sonnet_loop", "bounded_sonnet_cached_gate", "hybrid_haiku_sonnet_governed")
PRESET = CAT5_PRESETS[0]


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


# ------------------------------------------------------------------------ 1. live loop (fake model step)


def _tu(i: int, name: str, **inp: Any) -> dict[str, Any]:
    return {"type": "tool_use", "id": f"tu_{i}", "name": name, "input": inp}


def _step(model: str, tool_uses: list[dict[str, Any]], stop: str, *, text: str = "") -> AnthropicRawResult:
    blocks = ([{"type": "text", "text": text}] if text else []) + tool_uses
    return AnthropicRawResult(model, 5, 1000, 200, 0, 0, text, {"assistant_blocks": blocks, "tool_uses": tool_uses},
                              stop_reason=stop, thinking_tokens=7)


def _commit(i: int, **over: Any) -> dict[str, Any]:
    gt = PRESET["ground_truth"]
    inp = {"invoice_id": PRESET["invoice_id"], "po_id": PRESET["po_id"], "decision": gt["decision"],
           "authorized_net_principal_inr": gt["authorized_net_principal_inr"],
           "authorized_gst_payout_inr": gt["authorized_gst_payout_inr"],
           "gst_escrow_holdback_inr": gt["gst_escrow_holdback_inr"],
           "debit_note_deduction_inr": gt["debit_note_deduction_inr"], "audit_summary": "ok", **over}
    return _tu(i, "commit_reconciliation_voucher", **inp)


def _fake(monkeypatch: pytest.MonkeyPatch, script: list[AnthropicRawResult]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def fake_step(**kw: Any) -> AnthropicRawResult:
        calls.append(kw)
        if len(calls) > len(script):
            raise AssertionError("loop asked for more turns than scripted")
        return script[len(calls) - 1]

    monkeypatch.setattr(runner, "run_cat5_tool_loop_step", fake_step)
    return calls


def _live(rung: str) -> tuple[Any, dict[str, Any]]:
    return asyncio.run(runner._run_live_cat5_for_rung(preset=PRESET, rung_id=rung, api_key="k"))  # type: ignore[arg-type]


def test_end_turn_with_tool_use_is_executed_and_loop_continues(monkeypatch: pytest.MonkeyPatch) -> None:
    inv, po = PRESET["invoice_id"], PRESET["po_id"]
    calls = _fake(monkeypatch, [
        # end_turn *with* tool_use blocks: both calls must run and the loop must continue
        _step("claude-sonnet-5-5", [_tu(1, "query_invoice_raw", invoice_id=inv), _tu(2, "query_po_raw", po_id=po)], "end_turn"),
        _step("claude-sonnet-5-5", [_commit(3)], "tool_use"),
        _step("claude-sonnet-5-5", [], "end_turn", text="Committed."),
    ])
    res, raw = _live("unbounded_sonnet_loop")
    assert len(calls) == 3 and res.steps_used == 3
    assert [len(s.tool_calls) for s in res.steps] == [2, 1, 0]  # several calls per turn allowed on rung 1
    assert [s["stop_reason"] for s in raw["steps"]] == ["end_turn", "tool_use", "end_turn"]  # real stop reasons
    assert raw["committed_voucher"] is not None and res.evaluation.exact_match
    # the second request carries the tool results of the end_turn turn
    assert calls[1]["messages"][-1]["role"] == "user"
    assert [b["tool_use_id"] for b in calls[1]["messages"][-1]["content"]] == ["tu_1", "tu_2"]
    for kw in calls:
        assert kw["max_tokens"] == runner.CAT5_MAX_TOKENS == 4096 and kw["use_prefix_cache"] is False
    assert all(s["max_tokens"] == 4096 and s["thinking_tokens"] == 7 for s in raw["steps"])


def test_truncated_turn_is_recorded_not_executed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake(monkeypatch, [_step("claude-sonnet-5-5", [_commit(1)], "max_tokens")])
    res, raw = _live("unbounded_sonnet_loop")
    assert len(calls) == 1 and res.steps_used == 1
    assert res.steps[0].tool_calls == [] and res.steps[0].tool_calls_not_executed[0]["name"] == "commit_reconciliation_voucher"
    assert raw["steps"][0]["stop_reason"] == "max_tokens" and raw["committed_voucher"] is None
    assert raw["total_tool_calls"] == 0


def test_rung1_safety_cap_is_12_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    inv = PRESET["invoice_id"]
    calls = _fake(monkeypatch, [_step("claude-sonnet-5-5", [_tu(i, "query_invoice_raw", invoice_id=inv)], "tool_use") for i in range(20)])
    res, _ = _live("unbounded_sonnet_loop")
    assert runner.CAT5_BUDGETS["unbounded_sonnet_loop"] == 12
    assert len(calls) == 12 and res.steps_used == 12 and res.max_step_budget == 12


@pytest.mark.parametrize("rung", ["bounded_sonnet_cached_gate", "hybrid_haiku_sonnet_governed"])
def test_governed_rungs_keep_budget_4_plus_wrap_up(monkeypatch: pytest.MonkeyPatch, rung: str) -> None:
    inv = PRESET["invoice_id"]
    model = "claude-haiku-5-5" if rung.startswith("hybrid") else "claude-sonnet-5-5"
    calls = _fake(monkeypatch, [_step(model, [_tu(i, "fetch_3way_match_bundle", invoice_id=inv)], "tool_use") for i in range(20)])
    res, _ = _live(rung)
    assert runner.CAT5_BUDGETS[rung] == 4 and res.max_step_budget == 4
    assert len(calls) == 5  # budget 4 + one wrap-up turn, unchanged
    assert all(kw["use_prefix_cache"] is True and kw["max_tokens"] == 4096 for kw in calls)


# ------------------------------------------------------------------------ 2. rung-1 prompt


def test_rung1_prompt_is_the_ablation_neutral_text() -> None:
    sys1 = get_cat5_system_prompt("unbounded_sonnet_loop")
    assert sys1 == f"{AP_POLICY_MANUAL_MARKDOWN.strip()}\n\n{CAT5_FREE_CHOICE_PROTOCOL}"
    assert ablation.NEUTRAL_PROTOCOL == CAT5_FREE_CHOICE_PROTOCOL
    assert ablation.system_text_for("raw_free_sonnet", None) == sys1  # uncached arm: no nonce line
    assert "Step 1" not in CAT5_FREE_CHOICE_PROTOCOL and "Step 7" not in sys1
    # governed rungs keep their contracts
    assert "max_step_budget = 4" in get_cat5_system_prompt("bounded_sonnet_cached_gate")


# ------------------------------------------------------------------------ 3. golden builder


@pytest.mark.skipif(not HAVE_ABLATION, reason="ablation records not present")
def test_golden_builder_fixed_mapping_and_idempotent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("build_cat5_golden_from_ablation", monkeypatch, tmp_path)
    assert ablation.APP_RUNG_FOR_ARM == {
        "raw_free_sonnet": "unbounded_sonnet_loop",
        "bundle_gate_sonnet_cached": "bounded_sonnet_cached_gate",
        "bundle_gate_haiku_escalate": "hybrid_haiku_sonnet_governed",
    }
    out, summ = tmp_path / "golden.json", tmp_path / "summary.json"
    committed_summary = BACKEND_DIR / "replays" / "cat5_ablation_summary.json"
    summ.write_text(committed_summary.read_text(encoding="utf-8"), encoding="utf-8")
    argv = ["--in", str(RUNS), "--out", str(out), "--summary-out", str(summ)]
    assert mod.main(argv) == 0
    first_g, first_s = out.read_text(), summ.read_text()
    assert mod.main(argv) == 0
    assert out.read_text() == first_g and summ.read_text() == first_s  # unchanged content is not rewritten
    g = json.loads(first_g)
    assert g["provenance"]["source"] == ablation.ABLATION_GOLDEN_SOURCE
    for pid in ("inv-01", "inv-02", "inv-03"):
        for rid in APP_RUNGS:
            prov = g["presets"][pid]["provenance"][rid]
            assert prov["repeat_index"] == 0 and ablation.APP_RUNG_FOR_ARM[prov["arm_id"]] == rid
            assert all(s["max_tokens"] == 4096 and s["stop_reason"] for s in g["presets"][pid]["rungs"][rid]["steps"])
    # the committed files equal a fresh build
    assert mod._comparable(g) == mod._comparable(json.loads((BACKEND_DIR / "replays" / "cat5_golden_replays.json").read_text()))
    assert json.loads(first_s) == json.loads(committed_summary.read_text())


def test_golden_builder_raises_on_replay_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    if not HAVE_ABLATION:
        pytest.skip("ablation records not present")
    mod = _load_script("build_cat5_golden_from_ablation", monkeypatch, tmp_path)
    recs = ablation.load_jsonl(RUNS)
    rec = json.loads(json.dumps(mod.select_record(recs, "raw_free_sonnet", "inv-01")))
    first_call = next(c for t in rec["turns"] for c in t.get("tool_calls") or [])
    first_call["result_sha256"] = "0" * 64
    with pytest.raises(mod.ReplayMismatch):
        mod.convert_record(rec)


# ------------------------------------------------------------------------ 4. portfolio + API


def test_portfolio_loads_and_matches_headline() -> None:
    p = runner.load_cat5_ablation_portfolio()
    assert p is not None and isinstance(p, Cat5AblationPortfolio)
    assert p.pooled_runs == 198 and p.runs_per_arm == 33 and len(p.arms) == 6
    exact = {a.arm_id: a.exact for a in p.arms}
    assert exact["raw_free_sonnet_cached"] == 32 and sum(v == 33 for v in exact.values()) == 5
    assert sum(a.cap_hits for a in p.arms) == 0
    gd = p.gate_disagreement[0]
    assert (gd.no_gate_match_manual, gd.no_gate_runs, gd.gate_match_gate_output, gd.gate_runs) == (12, 12, 6, 6)


def test_portfolio_falls_back_to_none_and_copy_is_number_free(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _S:
        replays_dir = str(tmp_path)

    monkeypatch.setattr(runner, "get_settings", lambda: _S())
    assert runner.load_cat5_ablation_portfolio() is None
    (tmp_path / "cat5_ablation_summary.json").write_text("{not json")
    assert runner.load_cat5_ablation_portfolio() is None
    for rid in APP_RUNGS:
        title, badge, notes = runner._rung_metadata(rid)
        blob = badge + " ".join(notes)
        assert not any(ch.isdigit() for ch in blob.replace("AP-POL-GATE-01", "").replace("5.5", "").replace("Rung 2", "")), rid
    callout = runner._orchestration_callout(PRESET, [], None)
    assert not any(ch.isdigit() for ch in callout.replace("SQLite 3-way", "").replace("Category 5", ""))


@pytest.mark.parametrize("pid", ["inv-01", "inv-02", "inv-03"])
def test_replay_api_returns_ablation_portfolio(client: TestClient, pid: str) -> None:
    resp = client.post("/api/cat5/run", json={"mode": "replay", "preset_id": pid})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    port = data["ablation_portfolio"]
    assert port is not None and port["pooled_runs"] == 198 and "original_scripted_captures" not in port
    rungs = {r["rung_id"]: r for r in data["results"]}
    assert rungs["unbounded_sonnet_loop"]["max_step_budget"] == 12
    assert rungs["unbounded_sonnet_loop"]["rung_title"].startswith("1. Free-Choice")
    blob = json.dumps([r["architectural_notes"] for r in data["results"]]) + data["orchestration_callout"]
    for banned in ("-92%", "quadratic", "runaway", "prevents"):
        assert banned not in blob
    assert "198 ablation runs" in data["orchestration_callout"]


def test_replay_api_without_portfolio(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "load_cat5_ablation_portfolio", lambda: None)
    data = client.post("/api/cat5/run", json={"mode": "replay", "preset_id": "inv-01"}).json()
    assert data["ablation_portfolio"] is None
    assert "ablation" not in data["orchestration_callout"]


# ------------------------------------------------------------------------ 5. capture script


def _raw_rung(rid: str, *, stops: list[str], cached: bool) -> dict[str, Any]:
    steps = []
    for i, st in enumerate(stops):
        steps.append({"step_number": i + 1, "stop_reason": st, "model_id": "claude-sonnet-5-5", "input_tokens": 500,
                      "output_tokens": 100, "cache_creation_tokens": (5000 if cached and i == 0 else 0),
                      "cache_read_tokens": (5000 if cached and i > 0 else 0), "tool_calls": []})
    return {"rung_id": rid, "steps": steps, "committed_voucher": None}


def test_capture_accepts_governed_run_with_wrong_voucher(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("capture_cat5_replays", monkeypatch, tmp_path)
    golden = runner.load_cat5_replays()["presets"]["inv-01"]["rungs"]["bounded_sonnet_cached_gate"]
    wrong = json.loads(json.dumps(golden))
    wrong["committed_voucher"]["authorized_net_principal_inr"] += 1000.0
    wrong["committed_voucher"]["decision"] = "BLOCK_EXCEPTION_HOLD"
    built = runner._build_cat5_result_from_replay(rung_id="bounded_sonnet_cached_gate", preset=PRESET, raw_rung=wrong)
    assert built.evaluation is not None and not built.evaluation.exact_match
    assert mod._validate_rung(PRESET, "bounded_sonnet_cached_gate", built, wrong) is None
    # a cheap naive run (well under the old 25k floor) and a missed escalation are accepted too
    naive = _raw_rung("unbounded_sonnet_loop", stops=["tool_use", "end_turn"], cached=False)
    built_n = runner._build_cat5_result_from_replay(rung_id="unbounded_sonnet_loop", preset=PRESET, raw_rung=naive)
    assert mod._validate_rung(PRESET, "unbounded_sonnet_loop", built_n, naive) is None
    hyb = _raw_rung("hybrid_haiku_sonnet_governed", stops=["tool_use", "end_turn"], cached=True)
    built_h = runner._build_cat5_result_from_replay(rung_id="hybrid_haiku_sonnet_governed", preset=CAT5_PRESETS[2], raw_rung=hyb)
    assert mod._validate_rung(CAT5_PRESETS[2], "hybrid_haiku_sonnet_governed", built_h, hyb) is None


def test_capture_keeps_infrastructure_checks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("capture_cat5_replays", monkeypatch, tmp_path)
    trunc = _raw_rung("unbounded_sonnet_loop", stops=["tool_use", "max_tokens"], cached=False)
    b = runner._build_cat5_result_from_replay(rung_id="unbounded_sonnet_loop", preset=PRESET, raw_rung=trunc)
    assert "truncated" in (mod._validate_rung(PRESET, "unbounded_sonnet_loop", b, trunc) or "")
    nocache = _raw_rung("bounded_sonnet_cached_gate", stops=["tool_use", "end_turn"], cached=False)
    b = runner._build_cat5_result_from_replay(rung_id="bounded_sonnet_cached_gate", preset=PRESET, raw_rung=nocache)
    assert "cache" in (mod._validate_rung(PRESET, "bounded_sonnet_cached_gate", b, nocache) or "")
    errored = b.model_copy(update={"status": "error", "error_message": "boom"})
    assert "status=error" in (mod._validate_rung(PRESET, "bounded_sonnet_cached_gate", errored, nocache) or "")


# ------------------------------------------------------------------------ 6. trace seeding


@pytest.mark.skipif(not HAVE_ABLATION, reason="ablation records not present")
def test_seed_cat5_writes_ablation_traces_with_real_stop_reasons(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("seed_traces_from_replays", monkeypatch, tmp_path)
    n = mod.seed_cat5()
    files = list((tmp_path / "traces").rglob("*.json"))
    assert n == len(files) == 9
    golden = runner.load_cat5_replays()["presets"]
    idx = [json.loads(line) for line in (tmp_path / "traces" / "index.jsonl").read_text().splitlines()]
    assert len(idx) == 9 and {e["relative_path"] for e in idx} == {str(p.relative_to(tmp_path / "traces")) for p in files}
    for p in files:
        r = json.loads(p.read_text())
        rung = r["extra_metadata"]["rung_id"]
        steps = golden[r["item_id"]]["rungs"][rung]["steps"]
        assert r["response"]["stop_reason"] == steps[-1]["stop_reason"]
        assert r["request"]["parameters"]["max_tokens"] == 4096
        assert r["extra_metadata"]["source_endpoint"] == "build_cat5_golden_from_ablation.py"
        prov = golden[r["item_id"]]["provenance"][rung]
        assert r["extra_metadata"]["ablation_run_id"] == prov["run_id"]
        assert ablation._sha(r["request"]["system_instruction"]) == prov["system_text_sha256"]  # the text the run received


# ------------------------------------------------------------------------ 7. validation report


@pytest.mark.skipif(not HAVE_ABLATION, reason="ablation records not present")
def test_validator_cat5_uses_ablation_and_judges_lever_parts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("validate_deck_claims", monkeypatch, tmp_path)
    info, src = mod.cat5_ablation_info()
    assert src == "backend/replays/cat5_ablation_summary.json" and info is not None
    pooled, gd = mod.cat5_ablation_units(info["run_ids"])
    assert sum(len(v) for v in pooled.values()) == 198 and {len(v) for v in pooled.values()} == {33}
    assert sum(len(v) for v in gd.values()) == 18
    res = mod.analyse()
    c5 = res["categories"]["cat5"]
    assert c5["source"] == "ablation" and c5["max_cost_diff_vs_summary_per_1k"] < 0.01
    assert c5["lever_parts"] == {"max_step_budgets": "NOT SHOWN", "deterministic_guardrails": "NOT SUPPORTED", "small_model_routing": "SUPPORTED"}
    rows = {c["claim"]: c for c in res["claims"] if c["category"] == "Cat 5"}
    assert rows["Max-step budgets + deterministic guardrails + small-model routing for routine tool calls"]["verdict"] == "PARTLY SUPPORTED"
    assert rows["…without losing accuracy (implicit)"]["verdict"] == "PARTLY SUPPORTED"
    md = mod.render_markdown(res)
    assert "Source: the Category 5 ablation, 198 pooled runs" in md and "When the policy gate is wrong" in md
    assert mod.render_markdown(mod.analyse()) == md  # deterministic


def test_validator_cat5_falls_back(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("validate_deck_claims", monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "CAT5_ABLATION_SUMMARY", tmp_path / "missing.json")
    info, src = mod.cat5_ablation_info()
    if (BACKEND_DIR.parent / "analysis" / "cat5_ablation.json").is_file():
        assert src == "analysis/cat5_ablation.json" and info is not None and len(info["arms"]) == 6
    monkeypatch.setattr(mod, "CAT5_ABLATION_ANALYSIS", tmp_path / "missing2.json")
    info, src = mod.cat5_ablation_info()
    assert info is None and "could be read" in src
    res = mod.analyse()
    c5 = res["categories"]["cat5"]
    assert c5["source"] == "golden replays" and set(c5["rungs"]) == set(APP_RUNGS)
    rows = {c["claim"]: c["verdict"] for c in res["claims"] if c["category"] == "Cat 5"}
    assert rows["…without losing accuracy (implicit)"] == "NOT TESTABLE"
    assert "Source: the Category 5 golden replays" in mod.render_markdown(res)
