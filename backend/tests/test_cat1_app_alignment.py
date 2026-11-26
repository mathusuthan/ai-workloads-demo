"""App <-> Category 1 experiment alignment: golden builder, experiment portfolio, replay and live scoring of write-ups,
live caps for all four rungs, trace seeding and the validation report's Category 1 section. No live API calls."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
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
from app.main import app  # noqa: E402
from app.models import Cat1AblationPortfolio, Cat1RunRequest  # noqa: E402

RUNS = ablation.RUNS_PATH
EXTRACTIONS = ablation.EXTRACTIONS_PATH
HAVE_ABLATION = RUNS.is_file() and EXTRACTIONS.is_file()
needs_ablation = pytest.mark.skipif(not HAVE_ABLATION, reason="ablation records not present")
APP_RUNGS = ("sonnet_naive", "haiku_naive", "sonnet_calibrated", "haiku_calibrated")
MAPPING = {"sonnet_report": "sonnet_naive", "haiku_report": "haiku_naive", "sonnet_schema": "sonnet_calibrated",
           "haiku_schema": "haiku_calibrated"}


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
    out, summ = tmp_path / "golden.json", tmp_path / "summary.json"
    args = ["--out", str(out), "--summary-out", str(summ)]
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
            assert item["rungs"]["haiku_calibrated"]["max_tokens"] == item["rungs"]["sonnet_calibrated"]["max_tokens"] == 512
            assert item["rungs"]["sonnet_calibrated"]["model_id"] == "claude-sonnet-5-5"
            assert item["rungs"]["sonnet_naive"]["reader_extraction"] is not None
            assert item["rungs"]["haiku_calibrated"].get("reader_extraction") is None
            assert "sonnet_raw_text" not in item and "gemini_decision" not in item
    # second run: byte-identical, nothing rewritten
    assert mod.main(args) == 0
    assert out.read_text() == g1 and summ.read_text() == s1
    built, stored = json.loads(s1), json.loads((BACKEND_DIR / "replays" / "cat1_ablation_summary.json").read_text())
    assert built == stored
    assert (_md5(RUNS), _md5(EXTRACTIONS)) == before


# ------------------------------------------------------------------------ 2. summary, incl. pending extractions


@needs_ablation
def test_portfolio_has_the_four_cells() -> None:
    p = runner.load_cat1_ablation_portfolio()
    assert isinstance(p, Cat1AblationPortfolio)
    arms = {a.arm_id: a for a in p.arms}
    assert list(arms) == ["sonnet_report", "sonnet_schema", "haiku_report", "haiku_schema"]
    assert {a: (x.fields_correct, x.fields_total, x.items_fully_correct) for a, x in arms.items()} == {
        "sonnet_report": (69, 126, 6), "sonnet_schema": (126, 126, 36), "haiku_report": (69, 126, 3), "haiku_schema": (120, 126, 33)}
    assert all(x.runs == 36 and x.truncated == 0 for x in arms.values())
    assert {a.app_rung_id for a in arms.values()} == set(APP_RUNGS)
    assert p.ok_runs == p.planned_runs == 144 and p.reader_check_note
    dumped = json.dumps(p.model_dump()).lower()
    assert "gemini" not in dumped and "classify_text" not in dumped


def test_other_lever_records_kept_apart() -> None:
    other = ablation.OTHER_LEVERS_DIR / "runs.jsonl"
    if not other.is_file():
        pytest.skip("no other-lever records")
    arms = {json.loads(line)["arm_id"] for line in other.read_text().splitlines() if line.strip()}
    assert arms and not arms & set(ablation.ARM_IDS)
    if RUNS.is_file():
        main_arms = {json.loads(line)["arm_id"] for line in RUNS.read_text().splitlines() if line.strip()}
        assert main_arms == set(ablation.ARM_IDS)


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
    assert body["ablation_portfolio"] and len(body["ablation_portfolio"]["arms"]) == 4
    assert [x["rung_id"] for x in body["results"]] == list(APP_RUNGS)
    res = {x["rung_id"]: x for x in body["results"]}
    for rung in ("sonnet_naive", "haiku_naive"):
        acc = res[rung]["accuracy"]
        assert acc["method"] == "reader_model" and acc["schema_valid"] is False and "reader model" in acc["method_note"]
        assert res[rung]["max_tokens"] == 8192 and res[rung]["stop_reason"] and res[rung]["truncated"] is False
    for rung in ("sonnet_calibrated", "haiku_calibrated"):
        assert res[rung]["accuracy"]["method"] == "structured_output" and res[rung]["max_tokens"] == 512
    assert res["sonnet_calibrated"]["model_id"] == "claude-sonnet-5-5"
    assert body["sonnet_batch_comparator"] and body["haiku_batch_comparator"] and "jev_comparator" not in body
    notes = " ".join(" ".join(x.get("architectural_notes") or []) for x in body["results"])
    assert "schema" in notes.lower()


@needs_ablation
def test_replay_batch_carries_portfolio_and_reader_scores(client: TestClient) -> None:
    r = client.post("/api/cat1/batch", json={"sub_task": "mixed", "mode": "replay"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_items"] == 12 and body["ablation_portfolio"]
    roll = {x["rung_id"]: x for x in body["accuracy_rollup"]}
    assert list(roll) == list(APP_RUNGS)
    assert roll["sonnet_naive"]["scoring_method"] == "reader_model"
    assert roll["sonnet_calibrated"]["fields_matched"] == roll["sonnet_calibrated"]["fields_total"] == 42
    rows = {row["tier_id"]: row for row in body["cfo_comparison"]}
    assert list(rows) == list(APP_RUNGS)
    for rid in ("sonnet_calibrated", "haiku_calibrated"):  # the Batch API price is a computed column on the "with" rows
        assert rows[rid]["batch_cost_per_1k_usd"] == pytest.approx(rows[rid]["cost_per_1k_usd"] / 2, rel=1e-3)
    assert rows["sonnet_naive"]["batch_cost_per_1k_usd"] is None
    assert "gemini" not in json.dumps(body).lower() and "jev" not in json.dumps(body).lower()


def test_replay_without_portfolio_still_works(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "load_cat1_ablation_portfolio", lambda: None)
    r = client.post("/api/cat1/run", json={"preset_id": "tkt-01", "mode": "replay"})
    assert r.status_code == 200 and r.json()["ablation_portfolio"] is None


# ------------------------------------------------------------------------ 4. live path (fake calls / fake SDK)


def _fake_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner.credit_shield, "resolve_live_credentials",
                        lambda *a, **k: ResolvedCredentials("sk-test", "byok", False))


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
        rung = "sonnet_calibrated" if "sonnet" in kw["model"] else "haiku_calibrated"
        seen[rung] = kw
        return _raw(kw["model"], json.dumps(gt), 98, "end_turn", structured=dict(gt))

    monkeypatch.setattr(runner, "run_sonnet_naive", sonnet)
    monkeypatch.setattr(runner, "run_haiku_naive", haiku)
    monkeypatch.setattr(runner, "run_haiku_calibrated", calibrated)
    resp = asyncio.run(runner.execute_cat1_run(Cat1RunRequest(preset_id="tkt-01", mode="live")))
    assert seen["sonnet_naive"]["max_tokens"] == seen["haiku_naive"]["max_tokens"] == 8192
    for rung in ("sonnet_calibrated", "haiku_calibrated"):
        assert seen[rung]["max_tokens"] == 512 and seen[rung]["allow_tool_fallback"] is False and seen[rung]["max_retries"] == 0
    assert seen["sonnet_calibrated"]["thinking"] == {"type": "between_tools"} and seen["haiku_calibrated"]["thinking"] == {"type": "disabled"}
    assert "sonnet" in seen["sonnet_calibrated"]["model"] and "haiku" in seen["haiku_calibrated"]["model"]
    assert seen["sonnet_naive"]["max_retries"] == 0
    res = {r.rung_id: r for r in resp.results}
    for rung in ("sonnet_naive", "haiku_naive"):
        assert res[rung].accuracy is None and res[rung].accuracy_note and res[rung].accuracy_note.startswith("Not scored live")
    assert res["sonnet_naive"].truncated is True and res["sonnet_naive"].stop_reason == "max_tokens"
    assert res["haiku_naive"].truncated is False and res["haiku_naive"].thinking_tokens == 3
    for rung in ("sonnet_calibrated", "haiku_calibrated"):
        assert res[rung].accuracy is not None and res[rung].accuracy.exact_match
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


@pytest.mark.parametrize("rung,cap", [("sonnet_naive", 8192), ("haiku_naive", 8192), ("sonnet_calibrated", 512), ("haiku_calibrated", 512)])
def test_live_caps_reach_the_sdk(monkeypatch: pytest.MonkeyPatch, rung: str, cap: int) -> None:
    calls: list[dict[str, Any]] = []
    client_kw: list[dict[str, Any]] = []
    text = '{"queue": "replacements"}' if rung.endswith("_calibrated") else "write-up"

    class _Client:
        def __init__(self, **kw: Any) -> None:
            client_kw.append(kw)
            self.messages = _FakeMessages(calls, text, "end_turn")

    monkeypatch.setattr(anthropic_service.anthropic, "AsyncAnthropic", _Client)
    res, (params, stop, think) = asyncio.run(runner._live_rung(rung, "payload", "support_triage", "sk-test"))
    assert res.status == "ok", res.error_message
    assert calls[0]["max_tokens"] == cap and params["max_tokens"] == cap
    assert client_kw[0]["max_retries"] == 0
    assert stop == "end_turn" and think == 7 and res.thinking_tokens == 7 and res.max_tokens == cap
    assert ("sonnet" in calls[0]["model"]) == rung.startswith("sonnet")


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
def test_validator_cat1_uses_the_four_cells(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("validate_deck_claims", monkeypatch, tmp_path)
    info, src = mod.cat1_ablation_info()
    assert src == "backend/replays/cat1_ablation_summary.json" and info is not None
    assert set(info["arms"]) == set(mod.CAT1_ARMS) == {"sonnet_report", "sonnet_schema", "haiku_report", "haiku_schema"}
    res = mod.analyse()
    c1 = res["categories"]["cat1"]
    assert c1["source"] == "ablation" and c1["records"] == 144 and c1["max_cost_diff_vs_summary_per_1k"] < 0.01
    assert sum(c1["truncated_runs"].values()) == 0
    rows = {c["claim"]: c for c in res["claims"] if c["category"] == "Cat 1"}
    lever = rows["Small model + strict JSON schema + batching cuts unit cost by >80%"]
    assert lever["verdict"] == "SUPPORTED" and "Sonnet write-up → Haiku schema" in lever["measured"]
    assert rows["…without losing accuracy (implicit)"]["verdict"] == "PARTLY SUPPORTED"
    assert "tkt-01, tkt-02" in rows["…without losing accuracy (implicit)"]["note"]
    for claim in ("Input 500–1,500 tokens", "Output 10–100 tokens", "Input:output ≈ 20:1 to 50:1"):
        assert rows[claim]["verdict"] == "PARTLY SUPPORTED"
    md = mod.render_markdown(res)
    assert "| Without: four-part write-up, free text |" in md and "| With: classification with strict JSON schema |" in md
    assert "usable as a classification" in md
    sec = md.split("### 1.", 1)[1].split("### 2.", 1)[0]
    for word in ("gemini", "plain text classification", "classify_text", "original capture", "pre-fix", "seven"):
        assert word not in sec.lower(), word
    assert mod.render_markdown(mod.analyse()) == md  # deterministic


@needs_ablation
def test_validator_cat1_falls_back(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("validate_deck_claims", monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "CAT1_ABLATION_SUMMARY", tmp_path / "missing.json")
    info, src = mod.cat1_ablation_info()
    assert src == "analysis/cat1_ablation.json" and info is not None
    assert set(info["arms"]) == set(mod.CAT1_ARMS)
    monkeypatch.setattr(mod, "CAT1_ABLATION_ANALYSIS", tmp_path / "missing2.json")
    info, src = mod.cat1_ablation_info()
    assert info is None
    res = mod.analyse()
    assert res["categories"]["cat1"]["source"] == "unavailable"
    rows = [c for c in res["claims"] if c["category"] == "Cat 1"]
    assert rows and all(c["verdict"] == "NOT TESTABLE" for c in rows)
    md = mod.render_markdown(res)
    assert "### 1." in md and "Not available:" in md
