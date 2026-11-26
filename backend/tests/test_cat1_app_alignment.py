"""App <-> Category 1 ablation alignment: golden builder, ablation portfolio (incl. pending extractions), replay and
live scoring of write-ups, live caps, trace seeding and the validation report's Category 1 section. No live API calls."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat1_triage import ablation, runner  # noqa: E402
from app.core import anthropic_service  # noqa: E402
from app.core.anthropic_service import AnthropicRawResult  # noqa: E402
from app.core.credit_shield import ResolvedCredentials  # noqa: E402
from app.core.gemini_decision_service import GeminiDecisionRawResult  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Cat1AblationPortfolio, Cat1RunRequest  # noqa: E402

RUNS = ablation.RUNS_PATH
EXTRACTIONS = ablation.EXTRACTIONS_PATH
HAVE_ABLATION = RUNS.is_file() and EXTRACTIONS.is_file() and ablation.ORIGINAL_CAPTURE_PATH.is_file()
needs_ablation = pytest.mark.skipif(not HAVE_ABLATION, reason="ablation records not present")
APP_RUNGS = ("sonnet_naive", "haiku_naive", "haiku_calibrated", "gemini_decision")
MAPPING = {"sonnet_report": "sonnet_naive", "haiku_report": "haiku_naive", "haiku_schema": "haiku_calibrated",
           "gemini_decision": "gemini_decision"}


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


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


# ------------------------------------------------------------------------ 1. golden builder


@needs_ablation
def test_golden_builder_fixed_mapping_and_idempotent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("build_cat1_golden_from_ablation", monkeypatch, tmp_path)
    before = (_md5(RUNS), _md5(EXTRACTIONS))
    original = tmp_path / "original.json"
    shutil.copy(ablation.ORIGINAL_CAPTURE_PATH, original)
    out, summ = tmp_path / "golden.json", tmp_path / "summary.json"
    args = ["--out", str(out), "--summary-out", str(summ), "--original", str(original)]
    assert mod.main(args) == 0
    g1, s1 = out.read_text(), summ.read_text()
    doc = json.loads(g1)
    assert doc["provenance"]["source"] == ablation.ABLATION_GOLDEN_SOURCE
    assert set(doc["presets"]) == {"tkt-01", "tkt-02", "tkt-03", "sku-01", "sku-02", "sku-03"}
    assert set(doc["batch_items"]) == {"tkt-04", "tkt-05", "tkt-06", "sku-04", "sku-05", "sku-06"}
    for group in ("presets", "batch_items"):
        for iid, item in doc[group].items():
            assert set(item["rungs"]) == set(APP_RUNGS)
            for arm, rung in MAPPING.items():
                assert item["provenance"][rung]["run_id"] == f"{arm}:{iid}:r0"  # fixed mapping, repeat 0
                r = item["rungs"][rung]
                assert "stop_reason" in r and "thinking_tokens" in r and "max_tokens" in r
            assert item["rungs"]["sonnet_naive"]["max_tokens"] == 8192
            assert item["rungs"]["haiku_calibrated"]["max_tokens"] == 512
            assert item["rungs"]["sonnet_naive"]["reader_extraction"] is not None
            assert item["rungs"]["haiku_calibrated"].get("reader_extraction") is None
        for iid, item in doc["batch_items"].items():  # legacy flat keys stay for the old reader
            assert "sonnet_raw_text" in item and "input_tokens" in item
    # second run: byte-identical, nothing rewritten
    assert mod.main(args) == 0
    assert out.read_text() == g1 and summ.read_text() == s1
    built, stored = json.loads(s1), json.loads((BACKEND_DIR / "replays" / "cat1_ablation_summary.json").read_text())
    built.pop("source_files"), stored.pop("source_files")  # only the temp path of the original capture differs
    assert built == stored
    assert (_md5(RUNS), _md5(EXTRACTIONS)) == before


# ------------------------------------------------------------------------ 2. summary, incl. pending extractions


@needs_ablation
def test_portfolio_complete_matches_headline() -> None:
    p = runner.load_cat1_ablation_portfolio()
    assert isinstance(p, Cat1AblationPortfolio)
    arms = {a.arm_id: a for a in p.arms}
    assert len(arms) == 7
    assert (arms["haiku_schema"].fields_correct, arms["sonnet_schema"].fields_correct, arms["gemini_decision"].fields_correct) == (120, 126, 123)
    assert all(v.pending == 0 and v.status == "complete" for v in p.pending.values())
    assert p.pending["schema_as_text_check"].fields_agree == p.pending["schema_as_text_check"].fields == 100
    lev = {lv.lever: lv for lv in p.levers}
    assert any(lv.cost_change_pct > 0 for k, lv in lev.items() if "schema" in k)  # the schema costs more


@needs_ablation
def test_portfolio_marks_interrupted_extractions_pending_never_zero() -> None:
    runs = ablation.load_jsonl(RUNS)
    ext = ablation.load_jsonl(EXTRACTIONS)
    failed = {r["call_id"] for r in ext if r.get("status") != "ok"}
    assert failed, "the file keeps the interrupted first pass"
    before_retry = [r for r in ext if r.get("status") != "ok" or r["call_id"] not in failed]
    golden = json.loads(ablation.ORIGINAL_CAPTURE_PATH.read_text())
    port = ablation.build_ablation_portfolio(runs, before_retry, golden=golden)
    Cat1AblationPortfolio.model_validate(port)
    pend = port["pending"]
    assert pend["original_capture_reader"]["pending"] > 0 and pend["schema_as_text_check"]["pending"] > 0
    for v in pend.values():
        assert v["status"].startswith("pending: API usage limit")
    assert pend["schema_as_text_check"]["fields_agree"] is None
    for row in port["original_capture"]:
        if row["arm_id"] in ("sonnet_report", "haiku_report"):
            assert row["reader_fields_correct"] is None and row["reader_status"] != "complete"
    # the 252 runs are unaffected
    assert [a["fields_correct"] for a in port["arms"]] == [a.fields_correct for a in runner.load_cat1_ablation_portfolio().arms]


def test_portfolio_missing_or_broken_is_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _S:
        replays_dir = str(tmp_path)

    monkeypatch.setattr(runner, "get_settings", lambda: _S())
    assert runner.load_cat1_ablation_portfolio() is None
    (tmp_path / "cat1_ablation_summary.json").write_text("{not json")
    assert runner.load_cat1_ablation_portfolio() is None
    assert runner.live_prose_accuracy_note(None).startswith("Not scored live")


# ------------------------------------------------------------------------ 3. replay API


@needs_ablation
@pytest.mark.parametrize("pid", ["tkt-02", "sku-01"])
def test_replay_scores_write_ups_from_reader_model(client: TestClient, pid: str) -> None:
    r = client.post("/api/cat1/run", json={"preset_id": pid, "mode": "replay"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ablation_portfolio"] and len(body["ablation_portfolio"]["arms"]) == 7
    res = {x["rung_id"]: x for x in body["results"]}
    for rung in ("sonnet_naive", "haiku_naive"):
        acc = res[rung]["accuracy"]
        assert acc["method"] == "reader_model" and acc["schema_valid"] is False and "reader model" in acc["method_note"]
        assert res[rung]["max_tokens"] == 8192 and res[rung]["stop_reason"] and res[rung]["truncated"] is False
    assert res["haiku_calibrated"]["accuracy"]["method"] == "structured_output"
    assert res["haiku_calibrated"]["max_tokens"] == 512
    assert res["gemini_decision"]["stop_reason"] is None
    notes = " ".join(" ".join(x.get("architectural_notes") or []) for x in body["results"])
    assert "schema" in notes.lower()


@needs_ablation
def test_replay_batch_carries_portfolio_and_reader_scores(client: TestClient) -> None:
    r = client.post("/api/cat1/batch", json={"sub_task": "mixed", "mode": "replay"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_items"] == 12 and body["ablation_portfolio"]
    roll = {x["rung_id"]: x for x in body["accuracy_rollup"]}
    assert roll["sonnet_naive"]["scoring_method"] == "reader_model"
    assert "computed" in " ".join(row["label"] for row in body["cfo_comparison"]).lower()


def test_replay_without_portfolio_still_works(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "load_cat1_ablation_portfolio", lambda: None)
    r = client.post("/api/cat1/run", json={"preset_id": "tkt-01", "mode": "replay"})
    assert r.status_code == 200 and r.json()["ablation_portfolio"] is None


# ------------------------------------------------------------------------ 4. live path (fake calls / fake SDK)


def _fake_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner.credit_shield, "resolve_live_credentials",
                        lambda *a, **k: ResolvedCredentials("sk-test", "gm-test", "byok", "byok", False))


def _raw(model: str, text: str, out: int, stop: str, structured: dict[str, Any] | None = None) -> AnthropicRawResult:
    return AnthropicRawResult(model, 10, 1300, out, 0, 0, text, structured or {"mode": "unstructured_chat_prose"},
                              request_params={"max_tokens": 0}, stop_reason=stop, thinking_tokens=3)


def test_live_write_up_not_scored_and_caps_passed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NOVAMART_TRACES_DIR", str(tmp_path / "traces"))
    _fake_creds(monkeypatch)
    seen: dict[str, dict[str, Any]] = {}
    gt = runner._preset_map()["tkt-01"]["ground_truth"]

    async def sonnet(payload, sub_task, key, **kw):
        seen["sonnet_naive"] = kw
        return _raw("claude-sonnet-5-5", "queue: replacements\npriority: P1", 8192, "max_tokens")

    async def haiku(payload, sub_task, key, **kw):
        seen["haiku_naive"] = kw
        return _raw("claude-haiku-5-5", "A write-up.", 1500, "end_turn")

    async def calibrated(payload, sub_task, schema, key, **kw):
        seen["haiku_calibrated"] = kw
        return _raw("claude-haiku-5-5", json.dumps(gt), 98, "end_turn", structured=dict(gt))

    async def gemini(payload, questions, key):
        return GeminiDecisionRawResult("gemini-decision-1", 5, 1400, 0, {}, {})

    monkeypatch.setattr(runner, "run_sonnet_naive", sonnet)
    monkeypatch.setattr(runner, "run_haiku_naive", haiku)
    monkeypatch.setattr(runner, "run_haiku_calibrated", calibrated)
    monkeypatch.setattr(runner, "run_gemini_decision", gemini)
    resp = asyncio.run(runner.execute_cat1_run(Cat1RunRequest(preset_id="tkt-01", mode="live")))
    assert seen["sonnet_naive"]["max_tokens"] == seen["haiku_naive"]["max_tokens"] == 8192
    assert seen["haiku_calibrated"]["max_tokens"] == 512 and seen["haiku_calibrated"]["allow_tool_fallback"] is False
    assert seen["sonnet_naive"]["max_retries"] == 0
    res = {r.rung_id: r for r in resp.results}
    for rung in ("sonnet_naive", "haiku_naive"):
        assert res[rung].accuracy is None and res[rung].accuracy_note and res[rung].accuracy_note.startswith("Not scored live")
    assert res["sonnet_naive"].truncated is True and res["sonnet_naive"].stop_reason == "max_tokens"
    assert res["haiku_naive"].truncated is False and res["haiku_naive"].thinking_tokens == 3
    assert res["haiku_calibrated"].accuracy is not None and res["haiku_calibrated"].accuracy.exact_match
    assert res["gemini_decision"].stop_reason is None
    if HAVE_ABLATION:
        assert resp.ablation_portfolio is not None
    traces = [json.loads(p.read_text()) for p in (tmp_path / "traces").rglob("*.json")]
    by_rung = {t["extra_metadata"].get("rung_id") or t["partition"]["pattern"]: t for t in traces}
    assert len(traces) == 4
    assert any(t["response"].get("stop_reason") == "max_tokens" for t in by_rung.values())


class _FakeMessages:
    def __init__(self, calls: list[dict[str, Any]], text: str, stop: str) -> None:
        self.calls, self.text, self.stop = calls, text, stop

    async def create(self, **kw: Any) -> Any:
        self.calls.append(kw)
        usage = SimpleNamespace(input_tokens=1000, output_tokens=50, cache_creation_input_tokens=0, cache_read_input_tokens=0,
                                output_tokens_details=SimpleNamespace(thinking_tokens=7))
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.text)], usage=usage, stop_reason=self.stop)


@pytest.mark.parametrize("rung,cap", [("sonnet_naive", 8192), ("haiku_naive", 8192), ("haiku_calibrated", 512)])
def test_live_caps_reach_the_sdk(monkeypatch: pytest.MonkeyPatch, rung: str, cap: int) -> None:
    calls: list[dict[str, Any]] = []
    client_kw: list[dict[str, Any]] = []
    text = '{"queue": "replacements"}' if rung == "haiku_calibrated" else "write-up"

    class _Client:
        def __init__(self, **kw: Any) -> None:
            client_kw.append(kw)
            self.messages = _FakeMessages(calls, text, "end_turn")

    monkeypatch.setattr(anthropic_service.anthropic, "AsyncAnthropic", _Client)
    res, (params, stop, think) = asyncio.run(runner._live_rung(rung, "payload", "support_triage", ("sk-test", None)))
    assert res.status == "ok", res.error_message
    assert calls[0]["max_tokens"] == cap and params["max_tokens"] == cap
    assert client_kw[0]["max_retries"] == 0
    assert stop == "end_turn" and think == 7 and res.thinking_tokens == 7 and res.max_tokens == cap


# ------------------------------------------------------------------------ 5. trace seeding


@needs_ablation
def test_seed_cat1_only_appends(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    traces = tmp_path / "traces"
    old = traces / "category=cat1_classification_routing" / "old.json"
    old.parent.mkdir(parents=True)
    old.write_text("{}")
    (traces / "index.jsonl").write_text('{"trace_id": "old", "relative_path": "category=cat1_classification_routing/old.json"}\n')
    mod = _load_script("seed_traces_from_replays", monkeypatch, tmp_path)
    mod.main(["--cat1-only"])
    files = [p for p in traces.rglob("*.json") if p != old]
    assert old.read_text() == "{}" and len(files) == 48
    idx = [json.loads(line) for line in (traces / "index.jsonl").read_text().splitlines()]
    assert len(idx) == 49 and idx[0]["trace_id"] == "old"
    assert {e["relative_path"] for e in idx[1:]} == {str(p.relative_to(traces)) for p in files}
    golden = runner.load_golden_replays()
    for p in files:
        r = json.loads(p.read_text())
        assert r["run_group_id"].startswith("seed-cat1-ablation-") if "run_group_id" in r else True
        rung = MAPPING[r["extra_metadata"]["ablation_arm_id"]]
        src = golden["presets"].get(r["item_id"]) or golden["batch_items"][r["item_id"]]
        assert r["extra_metadata"]["ablation_run_id"] == src["provenance"][rung]["run_id"]
        assert r["response"]["stop_reason"] == src["rungs"][rung]["stop_reason"]
        if rung in ("sonnet_naive", "haiku_naive"):
            assert r["request"]["parameters"]["max_tokens"] == 8192
            assert r["extra_metadata"]["accuracy"]["method"] == "reader_model"


# ------------------------------------------------------------------------ 6. validation report


@needs_ablation
def test_validator_cat1_uses_ablation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("validate_deck_claims", monkeypatch, tmp_path)
    info, src = mod.cat1_ablation_info()
    assert src == "backend/replays/cat1_ablation_summary.json" and info is not None
    res = mod.analyse()
    c1 = res["categories"]["cat1"]
    assert c1["source"] == "ablation" and c1["records"] == 252 and c1["max_cost_diff_vs_summary_per_1k"] < 0.01
    assert sum(c1["truncated_runs"].values()) == 0
    rows = {c["claim"]: c for c in res["claims"] if c["category"] == "Cat 1"}
    lever = rows["Small model + strict JSON schema + batching cuts unit cost by >80%"]
    assert lever["verdict"] == "PARTLY SUPPORTED" and "comes from" in lever["note"]
    assert rows["…without losing accuracy (implicit)"]["verdict"] == "PARTLY SUPPORTED"
    md = mod.render_markdown(res)
    assert "Source: the Category 1 ablation, all 252 runs" in md
    assert "first extraction pass hit the API usage limit" in md and "100/100 fields matched" in md
    assert "pending: API usage limit" not in md
    assert mod.render_markdown(mod.analyse()) == md  # deterministic


@needs_ablation
def test_validator_cat1_falls_back(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("validate_deck_claims", monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "CAT1_ABLATION_SUMMARY", tmp_path / "missing.json")
    info, src = mod.cat1_ablation_info()
    if (BACKEND_DIR.parent / "analysis" / "cat1_ablation.json").is_file():
        assert src == "analysis/cat1_ablation.json" and info is not None
    monkeypatch.setattr(mod, "CAT1_ABLATION_ANALYSIS", tmp_path / "missing2.json")
    info, src = mod.cat1_ablation_info()
    assert info is None
    res = mod.analyse()
    assert res["categories"]["cat1"]["source"] == "golden"
    md = mod.render_markdown(res)
    assert "### 1." in md and "Source: the Category 1 ablation" not in md
