"""Regression tests: published cache-read rate, multi-model trace rollups, and CpO for unverified runs."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat6_swarms import runner as cat6_runner  # noqa: E402
from app.archetypes.cat6_swarms.runner import (  # noqa: E402
    _build_cat6_result_from_replay,
    _build_portfolio_scorecard,
    load_cat6_replays,
)
from app.archetypes.cat6_swarms.sandbox_verifier import evaluate_patch_in_sandbox  # noqa: E402
from app.core.pricing import MODEL_RATES, compute_run_finops  # noqa: E402
from app.data.cat6_fixtures import CAT6_PRESETS  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_traces_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    test_traces = tmp_path / "traces"
    monkeypatch.setenv("NOVAMART_TRACES_DIR", str(test_traces))
    return test_traces


def _trace_finops(traces_dir: Path, category: str) -> list[dict]:
    files = list((traces_dir / f"category={category}").rglob("*.json"))
    assert files, f"no traces written for {category}"
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


# --- pricing -----------------------------------------------------------------------------------


def test_sonnet_cache_read_matches_published_rate() -> None:
    assert MODEL_RATES["claude-sonnet-5-5"].cache_read_per_1m_usd == pytest.approx(0.10)
    fin = compute_run_finops("claude-sonnet-5-5", input_tokens=0, output_tokens=0, cache_read_tokens=1_000_000)
    assert fin.total_cost_usd == pytest.approx(0.10)


def test_rollup_prices_output_at_each_calls_own_model_rate() -> None:
    from app.core.pricing import rollup_multi_call_finops

    haiku = compute_run_finops("claude-haiku-5-5", input_tokens=1_000, output_tokens=1_000_000)
    sonnet = compute_run_finops("claude-sonnet-5-5", input_tokens=1_000, output_tokens=1_000_000)
    roll = rollup_multi_call_finops(
        calls=[haiku, sonnet], total_cost_usd=11.0, model_id="claude-sonnet-5-5", model_label="mixed"
    )
    assert roll.output_cost_usd == pytest.approx(0.50 + 10.00)  # not 2 x $10 Sonnet rate
    assert roll.input_cost_usd + roll.output_cost_usd == pytest.approx(roll.total_cost_usd)
    assert roll.output_tokens == 2_000_000
    assert roll.output_cost_share_pct == pytest.approx(95.5)


@pytest.mark.parametrize(
    ("endpoint", "preset", "category"),
    [
        ("/api/cat5/run", "inv-01", "cat5_process_orchestration"),
        ("/api/cat6/run", "inc-01", "cat6_multi_agent_swarms"),
    ],
)
def test_multi_step_trace_rollups_are_internally_consistent(
    isolated_traces_dir: Path, endpoint: str, preset: str, category: str
) -> None:
    resp = client.post(endpoint, json={"preset_id": preset, "mode": "replay"})
    assert resp.status_code == 200
    for trace in _trace_finops(isolated_traces_dir, category):
        fin = trace["finops"]
        assert fin["output_cost_usd"] <= fin["total_cost_usd"] + 1e-9
        assert fin["input_cost_usd"] + fin["output_cost_usd"] == pytest.approx(fin["total_cost_usd"], abs=1e-7)
        assert 0.0 < fin["output_cost_share_pct"] <= 100.0


def test_cat5_haiku_only_rollup_prices_output_at_haiku_rate(isolated_traces_dir: Path) -> None:
    # inv-01 never escalates, so every hybrid step runs on Haiku ($0.50/M output).
    resp = client.post("/api/cat5/run", json={"preset_id": "inv-01", "mode": "replay"})
    assert resp.status_code == 200
    hybrid = next(r for r in resp.json()["results"] if r["rung_id"] == "hybrid_haiku_sonnet_governed")
    assert hybrid["escalated_to_sonnet"] is False

    traces = [
        t for t in _trace_finops(isolated_traces_dir, "cat5_process_orchestration")
        if t["partition"]["pattern"] == "hybrid_haiku_sonnet_governed_loop"
    ]
    assert len(traces) == 1
    fin = traces[0]["finops"]
    assert fin["output_cost_usd"] == pytest.approx(fin["output_tokens"] * 0.50 / 1e6)


# --- Cost per Verified Outcome -----------------------------------------------------------------


def _replays_with_failing_naive(*preset_ids: str) -> dict:
    """Golden replays with the shared-bus patch on `preset_ids` replaced by the buggy baseline.

    The current golden replays verify every rung, so the unverified-run behaviour is tested on synthetic
    data: the buggy module is judged by the real sandbox, giving a genuine failing report.
    """
    replays = copy.deepcopy(load_cat6_replays())
    for pid in preset_ids:
        preset = next(p for p in CAT6_PRESETS if p["id"] == pid)
        rung = replays["presets"][pid]["rungs"]["unisolated_broadcast_swarm"]
        rung["patched_code"] = preset["buggy_code"]
        rung["sandbox_report"] = evaluate_patch_in_sandbox(pid, preset["buggy_code"])
        assert rung["sandbox_report"]["verified_outcome"] is False
    return replays


def test_cat6_cpo_is_undefined_not_zero_for_unverified_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cat6_runner, "load_cat6_replays", lambda: _replays_with_failing_naive("inc-01"))
    resp = client.post("/api/cat6/run", json={"preset_id": "inc-01", "mode": "replay"})
    assert resp.status_code == 200
    by_rung = {r["rung_id"]: r for r in resp.json()["results"]}

    naive = by_rung["unisolated_broadcast_swarm"]
    assert naive["sandbox_report"]["verified_outcome"] is False
    assert naive["cost_per_1k_runs_cold_usd"] > 0
    assert naive["cpo_cold_per_1k_usd"] is None
    assert naive["cpo_warm_per_1k_usd"] is None

    iso = by_rung["isolated_cached_sonnet_swarm"]
    assert iso["sandbox_report"]["verified_outcome"] is True
    assert iso["cpo_cold_per_1k_usd"] == pytest.approx(iso["cost_per_1k_runs_cold_usd"])


def test_cat6_portfolio_cpo_charges_failed_runs_to_verified_outcomes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cat6_runner, "load_cat6_replays", lambda: _replays_with_failing_naive("inc-01", "inc-02"))
    resp = client.post("/api/cat6/run", json={"preset_id": "inc-01", "mode": "replay"})
    assert resp.status_code == 200
    rows = {r["rung_id"]: r for r in resp.json()["portfolio_scorecard"]}
    naive = rows["unisolated_broadcast_swarm"]
    assert naive["verified_outcomes_count"] == 1
    # 3 runs of spend over 1 verified outcome
    assert naive["portfolio_cpo_cold_per_1k_usd"] == pytest.approx(naive["avg_cpr_cold_per_1k_usd"] * 3, rel=1e-3)
    assert rows["tiered_hybrid_cpo_swarm"]["cpo_savings_vs_naive_cold_pct"] > 0


def test_cat6_portfolio_cpo_equals_cpr_when_every_run_verifies() -> None:
    # The current golden replays (fair rerun, repeat 0) verify every rung on every incident.
    resp = client.post("/api/cat6/run", json={"preset_id": "inc-01", "mode": "replay"})
    assert resp.status_code == 200
    for row in resp.json()["portfolio_scorecard"]:
        assert row["verified_outcomes_count"] == row["prs_evaluated"] == 3
        assert row["portfolio_cpo_cold_per_1k_usd"] == pytest.approx(row["avg_cpr_cold_per_1k_usd"], rel=1e-3)


def test_cat6_portfolio_cpo_is_undefined_when_rung_has_zero_verified_outcomes() -> None:
    replays = _replays_with_failing_naive("inc-01")
    preset = next(p for p in CAT6_PRESETS if p["id"] == "inc-01")
    rungs = replays["presets"]["inc-01"]["rungs"]
    active = [
        _build_cat6_result_from_replay(rung_id=rid, preset=preset, raw_rung=rungs[rid])
        for rid in ("unisolated_broadcast_swarm", "isolated_cached_sonnet_swarm")
    ]
    # Empty replays => the portfolio holds only inc-01, where the shared-bus swarm verified 0/1.
    rows = {r.rung_id: r for r in _build_portfolio_scorecard(active_preset_id="inc-01", active_results=active, replays={})}

    naive = rows["unisolated_broadcast_swarm"]
    assert naive.verified_outcomes_count == 0
    assert naive.portfolio_cpo_cold_per_1k_usd is None
    assert naive.portfolio_cpo_warm_per_1k_usd is None
    assert naive.cpo_savings_vs_naive_cold_pct is None

    iso = rows["isolated_cached_sonnet_swarm"]
    assert iso.portfolio_cpo_cold_per_1k_usd is not None and iso.portfolio_cpo_cold_per_1k_usd > 0
    assert iso.cpo_savings_vs_naive_cold_pct is None  # no finite baseline to compare against
