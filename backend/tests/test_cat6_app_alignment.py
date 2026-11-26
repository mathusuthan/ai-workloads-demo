"""App ↔ fair-rerun alignment: live-path caps, golden-replay converter, capture script never selects on outcome."""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat6_swarms import runner  # noqa: E402
from app.archetypes.cat6_swarms.caps import (  # noqa: E402
    CALL_TIMEOUT_S,
    GOVERNED_ROLE_MAX_TOKENS,
    PATCH_AUTHOR_MAX_TOKENS,
)
from app.archetypes.cat6_swarms import fair_rerun  # noqa: E402
from app.archetypes.cat6_swarms.sandbox_verifier import evaluate_patch_in_sandbox  # noqa: E402
from app.core.anthropic_service import AnthropicRawResult  # noqa: E402
from app.data.cat6_fixtures import CAT6_PRESETS  # noqa: E402

PRESET = CAT6_PRESETS[0]


def _load_script(name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    # Scripts setdefault NOVAMART_TRACES_DIR at import; pin it so nothing leaks into later tests.
    monkeypatch.setenv("NOVAMART_TRACES_DIR", str(tmp_path / "traces"))
    spec = importlib.util.spec_from_file_location(name, BACKEND_DIR / "scripts" / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------------- 1. live-path caps


def test_fair_rerun_and_runner_share_one_cap_definition() -> None:
    assert fair_rerun.PATCH_AUTHOR_MAX_TOKENS is PATCH_AUTHOR_MAX_TOKENS
    assert fair_rerun.GOVERNED_ROLE_MAX_TOKENS is GOVERNED_ROLE_MAX_TOKENS
    assert fair_rerun.ARM_IDS == ("shared_bus_matched_gate", "isolated_cached_gate", "tiered_gate")
    assert set(GOVERNED_ROLE_MAX_TOKENS.values()) == {4000}
    assert CALL_TIMEOUT_S == 600


@pytest.mark.parametrize(
    ("rung_id", "caps"),
    [
        # every rung: the fake patch fails the sandbox, so the patch author runs twice
        ("unisolated_broadcast_swarm", [4000, 4000, 16000, 16000, 4000, 4000]),
        ("isolated_cached_sonnet_swarm", [4000, 4000, 16000, 16000, 4000, 4000]),
        ("tiered_hybrid_cpo_swarm", [4000, 4000, 16000, 16000, 4000, 4000]),
    ],
)
def test_live_path_uses_fair_rerun_caps_and_records_stop_reason(
    monkeypatch: pytest.MonkeyPatch, rung_id: str, caps: list[int]
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_call(**kw: Any) -> AnthropicRawResult:
        calls.append(kw)
        return AnthropicRawResult(
            model_id=kw["model_tier"],
            latency_ms=10,
            input_tokens=100,
            output_tokens=50,
            cache_creation_tokens=5000 if kw["use_prefix_cache"] and len(calls) == 1 else 0,
            cache_read_tokens=5000 if kw["use_prefix_cache"] and len(calls) > 1 else 0,
            raw_text="```python\nVALUE = 1\n```",
            structured={},
            stop_reason="end_turn",
        )

    monkeypatch.setattr(runner, "run_cat6_swarm_agent_call", fake_call)
    _, raw = asyncio.run(runner._run_live_cat6_for_rung(preset=PRESET, rung_id=rung_id, api_key="k"))
    assert [c["max_tokens"] for c in calls] == caps
    assert all(c["timeout_s"] == 600 for c in calls)
    assert [t["stop_reason"] for t in raw["agent_turns"]] == ["end_turn"] * len(caps)
    assert [t["max_tokens"] for t in raw["agent_turns"]] == caps


def _fake_raw(kw: dict[str, Any], n: int) -> AnthropicRawResult:
    return AnthropicRawResult(
        model_id=kw["model_tier"],
        latency_ms=10,
        input_tokens=100,
        output_tokens=50,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        raw_text=f"```python\nVALUE = {n}\n```",
        structured={},
        stop_reason="end_turn",
    )


def test_app_rung1_sends_exactly_what_the_matched_shared_bus_arm_sends(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rung 1 of the app is the `shared_bus_matched_gate` design: same messages, system prompts, caps, gate and retry."""
    app_calls: list[dict[str, Any]] = []
    arm_calls: list[dict[str, Any]] = []

    async def app_fake(**kw: Any) -> AnthropicRawResult:
        app_calls.append(copy.deepcopy(kw))
        return _fake_raw(kw, len(app_calls))

    async def arm_fake(**kw: Any) -> AnthropicRawResult:
        arm_calls.append(copy.deepcopy(kw))
        return _fake_raw(kw, len(arm_calls))

    failing = evaluate_patch_in_sandbox("inc-01", "")  # a real failing report, frozen so both paths see the same text
    passing = copy.deepcopy(failing)
    passing.update(passed_checks=10, verified_outcome=True, checks=[{**c, "passed": True} for c in failing["checks"]])

    def frozen_sandbox(preset_id: str, code: str) -> dict[str, Any]:
        return copy.deepcopy(failing if code.strip().endswith("= 3") else passing)

    monkeypatch.setattr(runner, "run_cat6_swarm_agent_call", app_fake)
    monkeypatch.setattr(runner, "evaluate_patch_in_sandbox", frozen_sandbox)
    _, raw = asyncio.run(runner._run_live_cat6_for_rung(preset=PRESET, rung_id="unisolated_broadcast_swarm", api_key="k"))
    rec = asyncio.run(
        fair_rerun.execute_run(
            arm_id="shared_bus_matched_gate", preset=PRESET, repeat_index=0, api_key="k", agent_call=arm_fake, sandbox=frozen_sandbox
        )
    )
    assert rec["status"] == "ok" and rec["retries_used"] == raw["retries_used"] == 1
    keys = ("model_tier", "shared_repo_prefix", "role_instructions", "messages", "use_prefix_cache", "max_tokens", "timeout_s")
    assert [{k: c[k] for k in keys} for c in app_calls] == [{k: c[k] for k in keys} for c in arm_calls]
    assert [t["attempt"] for t in raw["agent_turns"]] == [1, 1, 1, 2, 1, 1]


@pytest.mark.skipif(not (BACKEND_DIR / "experiments" / "cat6_fair_rerun" / "runs.jsonl").is_file(), reason="records not present")
def test_recorded_shared_bus_prompts_match_todays_rung1_builders() -> None:
    from app.archetypes.cat6_swarms.prompts import build_cat6_shared_bus_turn_message, get_cat6_agent_system_prompt

    presets = {p["id"]: p for p in CAT6_PRESETS}
    records = [
        json.loads(x)
        for x in (BACKEND_DIR / "experiments" / "cat6_fair_rerun" / "runs.jsonl").read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    bus = [r for r in records if r["arm_id"] == "shared_bus_matched_gate"]
    assert len(bus) == 15
    for r in bus:
        for t in r["turns"]:
            assert t["attempt"] == 1  # no retries were recorded, so every turn has a plain builder message
            assert t["system_prompt"] == get_cat6_agent_system_prompt("unisolated_broadcast_swarm", t["agent_role"])
            msg = build_cat6_shared_bus_turn_message(presets[r["preset_id"]], t["agent_role"], sandbox_report=r["final"]["sandbox"])
            assert t["user_message"] == msg


def test_trace_default_request_params_state_real_caps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVAMART_TRACES_DIR", str(tmp_path))
    monkeypatch.setenv("NOVAMART_RECORD_REPLAY_TRACES", "1")  # replay traces are off by default
    path = runner.persist_cat6_trace(
        source_mode="replay",
        run_group_id="t",
        item_id="inc-01",
        item_title="t",
        model_id="claude-sonnet-5-5",
        pattern="isolated_repo_cached_swarm",
        system_instruction="s",
        payload_text="p",
        status="ok",
        latency_ms=1,
        finops_dict={},
        raw_text="r",
        structured_output={},
    )
    params = json.loads(path.read_text())["request"]["parameters"]
    assert "max_tokens" not in params
    assert params["max_tokens_by_role"]["patch_author"] == 16000
    assert params["max_tokens_by_role"]["security_critic"] == 4000
    assert params["timeout_s"] == 600


# ------------------------------------------------------------------------ 2. golden from fair rerun


def _synthetic_record(arm_id: str, repeat_index: int, *, recorded_verified: bool) -> dict[str, Any]:
    turns = []
    for i, role in enumerate(fair_rerun.ROLE_SEQUENCE, start=1):
        turns.append(
            {
                "step_number": i,
                "agent_role": role,
                "attempt": 1,
                "model_id": fair_rerun.intended_model_id(arm_id, role),
                "intended_model_id": fair_rerun.intended_model_id(arm_id, role),
                "max_tokens": fair_rerun.max_tokens_for(arm_id, role),
                "stop_reason": "end_turn",
                "latency_ms": 100 * i,
                "input_tokens": 1000,
                "output_tokens": 200,
                "thinking_tokens": 0,
                "cache_creation_tokens": 9000 if i == 1 and arm_id != "shared_bus_matched_gate" else 0,
                "cache_read_tokens": 9000 if i > 1 and arm_id != "shared_bus_matched_gate" else 0,
                "system_prompt": "sys",
                "user_message": "U" * 1000,
                "raw_text": "R" * 5000,
            }
        )
    return {
        "run_id": f"{arm_id}-{repeat_index}",
        "arm_id": arm_id,
        "preset_id": "inc-01",
        "repeat_index": repeat_index,
        "status": "ok",
        "started_at": "2026-11-25T00:00:00+00:00",
        "turns": turns,
        "retries_used": 0,
        "final": {"sandbox": {"verified_outcome": recorded_verified}},
        "patched_code_final": f"CODE_{arm_id}_{repeat_index}",
        "final_signoff_memo": "memo",
    }


def test_golden_converter_on_synthetic_records(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("build_cat6_golden_from_rerun", monkeypatch, tmp_path)
    good = evaluate_patch_in_sandbox("inc-01", "")  # any real report shape
    judged: list[tuple[str, str]] = []

    def fake_sandbox(pid: str, code: str) -> dict[str, Any]:
        judged.append((pid, code))
        return copy.deepcopy(good)

    records = []
    for arm in ("shared_bus_matched_gate", "isolated_cached_gate", "tiered_gate"):
        # repeat 0 recorded as failed, repeat 1 as passed: the fixed mapping must still take repeat 0
        records += [_synthetic_record(arm, 0, recorded_verified=False), _synthetic_record(arm, 1, recorded_verified=True)]
    doc = mod.build_golden(records, source_file="x.jsonl", preset_ids=["inc-01"], sandbox=fake_sandbox)

    rungs = doc["presets"]["inc-01"]["rungs"]
    assert set(rungs) == set(mod.GOLDEN_MAPPING)
    for rung_id, arm in mod.GOLDEN_MAPPING.items():
        r = rungs[rung_id]
        assert r["provenance"]["arm_id"] == arm and r["provenance"]["repeat_index"] == 0
        assert r["patched_code"] == f"CODE_{arm}_0"
        assert r["sandbox_report"] == good  # the sandbox's verdict on the patch
        t = r["agent_turns"][0]
        assert len(t["prompt_preview"]) == 450 and len(t["output_preview"]) == 2000
        assert t["stop_reason"] == "end_turn"
        assert t["context_mode"] == ("shared_omnibus_bus" if rung_id == "unisolated_broadcast_swarm" else "isolated_prefix_cached")
        # loadable by the app's replay path
        res = runner._build_cat6_result_from_replay(rung_id=rung_id, preset=PRESET, raw_rung=r)
        assert len(res.agent_turns) == 5
    assert sorted(judged) == sorted(("inc-01", f"CODE_{arm}_0") for arm in mod.GOLDEN_MAPPING.values())  # repeat 0 only
    assert doc["provenance"]["mapping"]["unisolated_broadcast_swarm"] == {"arm_id": "shared_bus_matched_gate", "repeat_index": 0}
    assert doc["provenance"]["mapping"]["tiered_hybrid_cpo_swarm"] == {"arm_id": "tiered_gate", "repeat_index": 0}

    out = tmp_path / "golden.json"
    assert mod.write_golden(doc, out) is True
    first = out.read_text()
    assert mod.write_golden(mod.build_golden(records, source_file="x.jsonl", preset_ids=["inc-01"], sandbox=fake_sandbox), out) is False
    assert out.read_text() == first  # idempotent
    assert "rebuilt_at" in json.loads(first)["provenance"]


def test_golden_converter_raises_when_mapped_record_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("build_cat6_golden_from_rerun", monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="repeat 0"):
        mod.build_golden([_synthetic_record("tiered_gate", 1, recorded_verified=True)], source_file="x", preset_ids=["inc-01"])


# ------------------------------------------------------------------ 3. capture script: no selection


def _golden_rung(rung_id: str) -> dict[str, Any]:
    return copy.deepcopy(runner.load_cat6_replays()["presets"]["inc-01"]["rungs"][rung_id])


@pytest.mark.parametrize("rung_id", ["isolated_cached_sonnet_swarm", "tiered_hybrid_cpo_swarm", "unisolated_broadcast_swarm"])
def test_capture_accepts_run_with_failing_sandbox(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, rung_id: str) -> None:
    mod = _load_script("capture_cat6_replays", monkeypatch, tmp_path)
    raw = _golden_rung(rung_id)
    raw["patched_code"] = PRESET["buggy_code"]
    raw["sandbox_report"] = evaluate_patch_in_sandbox("inc-01", PRESET["buggy_code"])
    res = runner._build_cat6_result_from_replay(rung_id=rung_id, preset=PRESET, raw_rung=raw)
    assert res.sandbox_report is not None and res.sandbox_report.verified_outcome is False
    assert mod._validate_rung(PRESET, rung_id, res, raw) is None


def test_capture_still_rejects_infrastructure_failures(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("capture_cat6_replays", monkeypatch, tmp_path)
    raw = _golden_rung("isolated_cached_sonnet_swarm")
    raw["agent_turns"][1]["cache_read_tokens"] = 0
    res = runner._build_cat6_result_from_replay(rung_id="isolated_cached_sonnet_swarm", preset=PRESET, raw_rung=raw)
    assert "Turn 2 missed prefix cache hit" in (mod._validate_rung(PRESET, "isolated_cached_sonnet_swarm", res, raw) or "")
    short = _golden_rung("unisolated_broadcast_swarm")
    short["agent_turns"] = short["agent_turns"][:3]
    res = runner._build_cat6_result_from_replay(rung_id="unisolated_broadcast_swarm", preset=PRESET, raw_rung=short)
    assert "Expected >= 5 agent turns" in (mod._validate_rung(PRESET, "unisolated_broadcast_swarm", res, short) or "")
