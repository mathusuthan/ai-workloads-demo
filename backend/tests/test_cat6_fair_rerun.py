"""Offline tests for the Category 6 fair-rerun harness (no network, no API key)."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat6_swarms import fair_rerun as fr  # noqa: E402
from app.archetypes.cat6_swarms.prompts import (  # noqa: E402
    build_cat6_isolated_payload,
    build_cat6_shared_bus_turn_message,
    get_cat6_agent_system_prompt,
)
from app.core.anthropic_service import AnthropicRawResult  # noqa: E402
from app.core.pricing import compute_run_finops  # noqa: E402
from app.data.cat6_fixtures import (  # noqa: E402
    CAT6_PRESETS,
    SHARED_REPO_PREFIX_MARKDOWN,
    UNFILTERED_REPO_AND_TELEMETRY_NOISE,
)

PRESET = CAT6_PRESETS[0]
GOOD_PATCH = "```python\nVALUE = 1\n```"


# --------------------------------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------------------------------


class FakeAgent:
    """Records every call; returns a deterministic AnthropicRawResult per role/attempt."""

    def __init__(
        self,
        *,
        fail_on_call: int | None = None,
        texts: dict[str, str] | None = None,
        stop_reasons: dict[str, str] | None = None,
        model_override: dict[str, str] | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail_on_call = fail_on_call
        self.texts = texts or {}
        self.stop_reasons = stop_reasons or {}
        self.model_override = model_override or {}

    async def __call__(self, **kwargs: Any) -> AnthropicRawResult:
        self.calls.append(kwargs)
        n = len(self.calls)
        if self.fail_on_call == n:
            raise TimeoutError("simulated API timeout")
        role = self._role_of(kwargs["role_instructions"])
        text = self.texts.get(role, GOOD_PATCH if role == "patch_author" else f"{role} output #{n} " + "x" * 50)
        return AnthropicRawResult(
            model_id=self.model_override.get(role, kwargs["model_tier"]),
            latency_ms=100 * n,
            input_tokens=1000 + n,
            output_tokens=200 + n,
            cache_creation_tokens=6000 if kwargs["use_prefix_cache"] and n == 1 else 0,
            cache_read_tokens=6000 if kwargs["use_prefix_cache"] and n > 1 else 0,
            raw_text=text,
            structured={},
            system_prompt=kwargs["role_instructions"],
            request_params={"max_tokens": kwargs["max_tokens"]},
            stop_reason=self.stop_reasons.get(role, "end_turn"),
            thinking_tokens=0,
        )

    @staticmethod
    def _role_of(system_prompt: str) -> str:
        for rung in ("unisolated_broadcast_swarm", "isolated_cached_sonnet_swarm"):
            for role in fr.ROLE_SEQUENCE:
                if get_cat6_agent_system_prompt(rung, role) == system_prompt:
                    return role
        raise AssertionError("unrecognised system prompt")


def make_sbx(verified: bool, failing: tuple[str, ...] = ("ADV-02",)) -> dict[str, Any]:
    ids = [
        ("CI-UNIT-01", "ci_unit"),
        ("CI-UNIT-02", "ci_unit"),
        ("CI-UNIT-03", "ci_unit"),
        ("CI-UNIT-04", "ci_unit"),
        ("ADV-01", "adversarial"),
        ("ADV-02", "adversarial"),
        ("ADV-03", "adversarial"),
        ("ADV-04", "adversarial"),
        ("AST-SAFE-02", "ast"),
        ("AST-SEC-01", "ast"),
    ]
    checks = [
        {
            "check_id": cid,
            "category": cat,
            "name": f"check {cid}",
            "passed": verified or cid not in failing,
            "detail": f"detail for {cid}",
        }
        for cid, cat in ids
    ]
    passed = sum(1 for c in checks if c["passed"])
    return {
        "total_checks": 10,
        "passed_checks": passed,
        "ci_unit_passed": sum(1 for c in checks if c["category"] == "ci_unit" and c["passed"]),
        "adversarial_passed": sum(1 for c in checks if c["category"] == "adversarial" and c["passed"]),
        "ast_passed": sum(1 for c in checks if c["category"] == "ast" and c["passed"]),
        "verified_outcome": passed == 10,
        "execution_ms": 5,
        "checks": checks,
        "unified_diff": "",
    }


class FakeSandbox:
    def __init__(self, verdicts: list[bool]) -> None:
        self.verdicts = list(verdicts)
        self.calls: list[tuple[str, str]] = []

    def __call__(self, preset_id: str, code: str) -> dict[str, Any]:
        self.calls.append((preset_id, code))
        verified = self.verdicts.pop(0) if self.verdicts else True
        return make_sbx(verified)


def run(arm_id: str, agent: FakeAgent, sandbox: Any = None, preset: dict[str, Any] = PRESET) -> dict[str, Any]:
    return asyncio.run(
        fr.execute_run(
            arm_id=arm_id,
            preset=preset,
            repeat_index=0,
            api_key="test-key",
            agent_call=agent,
            sandbox=sandbox or FakeSandbox([True]),
        )
    )


# --------------------------------------------------------------------------------------------------
# 1. Role / model / cap / cache-flag sequences
# --------------------------------------------------------------------------------------------------

S, H = "claude-sonnet-5-5", "claude-haiku-5-5"
GOV_CAPS = [4000, 4000, 16000, 4000, 4000]


@pytest.mark.parametrize(
    ("arm_id", "models", "caps", "cached"),
    [
        ("shared_bus_matched_gate", [S] * 5, GOV_CAPS, False),
        ("isolated_cached_gate", [S] * 5, GOV_CAPS, True),
        ("tiered_gate", [H, H, S, H, H], GOV_CAPS, True),
        ("shared_bus_tiered_gate", [H, H, S, H, H], GOV_CAPS, False),
    ],
)
def test_arm_call_sequence(arm_id: str, models: list[str], caps: list[int], cached: bool) -> None:
    agent = FakeAgent()
    rec = run(arm_id, agent)
    assert rec["status"] == "ok"
    assert [t["agent_role"] for t in rec["turns"]] == list(fr.ROLE_SEQUENCE)
    assert [c["model_tier"] for c in agent.calls] == models
    assert [c["max_tokens"] for c in agent.calls] == caps
    assert all(c["use_prefix_cache"] is cached for c in agent.calls)
    assert all(c["timeout_s"] == 600 for c in agent.calls)
    assert [t["intended_model_id"] for t in rec["turns"]] == models
    assert [t["max_tokens"] for t in rec["turns"]] == caps
    assert [t["step_number"] for t in rec["turns"]] == [1, 2, 3, 4, 5]
    assert rec["gate_enabled"] is True
    assert rec["final"]["sandbox"]["verified_outcome"] is True
    assert rec["final_signoff_memo"].startswith("orchestrator_merge output")


# --------------------------------------------------------------------------------------------------
# 2. Prompt identity
# --------------------------------------------------------------------------------------------------


def test_matched_bus_system_prompts_identical_to_isolated_arm() -> None:
    matched, iso = FakeAgent(), FakeAgent()
    run("shared_bus_matched_gate", matched)
    run("isolated_cached_gate", iso)
    m_prompts = [c["role_instructions"] for c in matched.calls]
    i_prompts = [c["role_instructions"] for c in iso.calls]
    assert m_prompts == i_prompts
    for role, prompt in zip(fr.ROLE_SEQUENCE, m_prompts, strict=True):
        assert prompt == get_cat6_agent_system_prompt("isolated_cached_sonnet_swarm", role)
        assert prompt.encode() == get_cat6_agent_system_prompt("tiered_hybrid_cpo_swarm", role).encode()


def test_matched_bus_first_message_has_noise_prefix_and_governed_ask() -> None:
    agent = FakeAgent()
    run("shared_bus_matched_gate", agent)
    first = agent.calls[0]["messages"][0]["content"]
    assert UNFILTERED_REPO_AND_TELEMETRY_NOISE in first
    assert SHARED_REPO_PREFIX_MARKDOWN in first
    assert PRESET["buggy_code"] in first and PRESET["ci_failure_log"] in first
    assert first.endswith("Produce your concise 4-bullet remediation order.")
    assert first == build_cat6_shared_bus_turn_message(PRESET, "orchestrator_plan")


def test_matched_bus_later_turns_reuse_isolated_asks_and_sandbox_blocks() -> None:
    sbx = make_sbx(False, ("ADV-01", "CI-UNIT-03"))
    critic_iso = build_cat6_isolated_payload(preset=PRESET, role_key="security_critic", sandbox_report=sbx)
    merge_iso = build_cat6_isolated_payload(preset=PRESET, role_key="orchestrator_merge", sandbox_report=sbx)
    critic = fr.build_matched_bus_turn_message(PRESET, "security_critic", sandbox_report=sbx)
    merge = fr.build_matched_bus_turn_message(PRESET, "orchestrator_merge", sandbox_report=sbx)
    assert critic.startswith("[TURN 4 — SECURITY & TEST CRITIC]")
    sandbox_section = critic.split(":\n\n", 1)[1].split("\n\nConfirm")[0]
    assert sandbox_section in critic_iso and "[FAIL]" in sandbox_section and "[PASS]" in sandbox_section
    assert critic.endswith(critic_iso.rsplit("\n\n", 1)[1])
    status_line = merge.split(":\n\n", 1)[1].split("\n\n")[0]
    assert status_line in merge_iso
    assert merge.endswith(merge_iso.rsplit("\n\n", 1)[1])
    triage = fr.build_matched_bus_turn_message(PRESET, "ci_triager")
    iso_triage = build_cat6_isolated_payload(preset=PRESET, role_key="ci_triager")
    assert triage.startswith("[TURN 2 — CI/CD & RUNTIME TRIAGER]") and triage.endswith(iso_triage.rsplit("\n\n", 1)[1])
    author = fr.build_matched_bus_turn_message(PRESET, "patch_author")
    iso_author = build_cat6_isolated_payload(preset=PRESET, role_key="patch_author")
    assert author.endswith(iso_author.rsplit("\n\n", 1)[1])


@pytest.mark.parametrize("verdicts", [[True], [False, True], [False, False]])
def test_shared_bus_tiered_sends_exactly_what_matched_bus_sends_except_model(verdicts: list[bool]) -> None:
    """`shared_bus_tiered_gate` = `shared_bus_matched_gate` with tiered_gate's models: byte-identical text, caps and flags."""
    matched, tiered = FakeAgent(), FakeAgent()
    rec_m = run("shared_bus_matched_gate", matched, FakeSandbox(list(verdicts)))
    rec_t = run("shared_bus_tiered_gate", tiered, FakeSandbox(list(verdicts)))
    assert len(matched.calls) == len(tiered.calls) == (5 if verdicts == [True] else 6)
    for cm, ct in zip(matched.calls, tiered.calls, strict=True):
        assert set(cm) == set(ct)
        for key in cm:
            if key == "model_tier":
                continue
            assert cm[key] == ct[key], key
        assert cm["role_instructions"].encode() == ct["role_instructions"].encode()
        assert [m["content"].encode() for m in cm["messages"]] == [m["content"].encode() for m in ct["messages"]]
    roles = [t["agent_role"] for t in rec_t["turns"]]
    assert [c["model_tier"] for c in matched.calls] == [S] * len(roles)
    assert [c["model_tier"] for c in tiered.calls] == [S if r == "patch_author" else H for r in roles]
    assert [t["intended_model_id"] for t in rec_t["turns"]] == [S if r == "patch_author" else H for r in roles]
    for tm, tt in zip(rec_m["turns"], rec_t["turns"], strict=True):
        assert tm["system_prompt"].encode() == tt["system_prompt"].encode()
        assert tm["user_message"].encode() == tt["user_message"].encode()
    assert rec_t["run_nonce"] is None and all(c["use_prefix_cache"] is False for c in tiered.calls)
    spec = fr.ARMS["shared_bus_tiered_gate"]
    assert spec.context == fr.ARMS["shared_bus_matched_gate"].context and spec.tiered and spec.gate_enabled
    assert fr.DESIGN_CELLS[("without", "tiered")] == "shared_bus_tiered_gate"


def test_every_rung_and_arm_uses_the_same_role_instructions() -> None:
    for role in fr.ROLE_SEQUENCE:
        prompts = {get_cat6_agent_system_prompt(r, role) for r in
                   ("unisolated_broadcast_swarm", "isolated_cached_sonnet_swarm", "tiered_hybrid_cpo_swarm", "unisolated_tiered_swarm")}
        prompts |= {fr.system_prompt_for(a, role) for a in fr.ARM_IDS}
        assert len(prompts) == 1
        assert "exhaustive" not in next(iter(prompts))


# --------------------------------------------------------------------------------------------------
# 3. Growing shared thread vs single isolated message
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("arm_id", ["shared_bus_matched_gate", "shared_bus_tiered_gate"])
def test_shared_bus_sends_growing_thread(arm_id: str) -> None:
    agent = FakeAgent()
    rec = run(arm_id, agent)
    for k, call in enumerate(agent.calls):
        msgs = call["messages"]
        assert len(msgs) == 2 * k + 1
        assert [m["role"] for m in msgs] == ["user", "assistant"] * k + ["user"]
        for j in range(k):
            assert msgs[2 * j]["content"] == rec["turns"][j]["user_message"]
            assert msgs[2 * j + 1]["content"] == rec["turns"][j]["raw_text"]


@pytest.mark.parametrize("arm_id", ["isolated_cached_gate", "tiered_gate"])
def test_isolated_arms_send_single_user_message(arm_id: str) -> None:
    agent = FakeAgent()
    run(arm_id, agent)
    for call in agent.calls:
        assert len(call["messages"]) == 1 and call["messages"][0]["role"] == "user"
        assert UNFILTERED_REPO_AND_TELEMETRY_NOISE not in call["messages"][0]["content"]


# --------------------------------------------------------------------------------------------------
# 4. Sandbox gate
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("arm_id", ["shared_bus_matched_gate", "isolated_cached_gate", "tiered_gate", "shared_bus_tiered_gate"])
def test_gate_fail_then_pass(arm_id: str) -> None:
    agent = FakeAgent()
    rec = run(arm_id, agent, FakeSandbox([False, True]))
    assert rec["status"] == "ok"
    assert rec["retries_used"] == 1
    assert rec["first_attempt"]["sandbox"]["verified_outcome"] is False
    assert rec["final"]["sandbox"]["verified_outcome"] is True
    authors = [t for t in rec["turns"] if t["agent_role"] == "patch_author"]
    assert [t["attempt"] for t in authors] == [1, 2]
    assert all(t["max_tokens"] == 16000 for t in authors)
    assert [t["agent_role"] for t in rec["turns"]] == [
        "orchestrator_plan",
        "ci_triager",
        "patch_author",
        "patch_author",
        "security_critic",
        "orchestrator_merge",
    ]
    retry_msg = authors[1]["user_message"]
    assert "SANDBOX RETRY FEEDBACK" in retry_msg
    assert "- FAIL ADV-02 (check ADV-02): detail for ADV-02" in retry_msg
    # critic & merge see the final (passing) verdict
    assert "(10/10)" in rec["turns"][4]["user_message"]
    assert "Verified Outcome: `True`" in rec["turns"][5]["user_message"]


def test_gate_fail_twice_is_ok_outcome_with_one_retry() -> None:
    rec = run("isolated_cached_gate", FakeAgent(), FakeSandbox([False, False]))
    assert rec["status"] == "ok"
    assert rec["retries_used"] == 1
    assert rec["final"]["sandbox"]["verified_outcome"] is False
    assert sum(1 for t in rec["turns"] if t["agent_role"] == "patch_author") == 2
    assert len(rec["turns"]) == 6


def test_no_retry_first_equals_final() -> None:
    rec = run("tiered_gate", FakeAgent(), FakeSandbox([True]))
    assert rec["retries_used"] == 0
    assert rec["first_attempt"] == rec["final"]
    assert rec["patched_code_first"] == rec["patched_code_final"] == "VALUE = 1"


def test_real_sandbox_flags_buggy_code_through_gate() -> None:
    """The real offline sandbox judges the unchanged buggy module as failing; the retry then runs."""
    for preset in CAT6_PRESETS:
        buggy = f"```python\n{preset['buggy_code']}\n```"
        rec = asyncio.run(
            fr.execute_run(
                arm_id="isolated_cached_gate",
                preset=preset,
                repeat_index=0,
                api_key="k",
                agent_call=FakeAgent(texts={"patch_author": buggy}),
            )
        )
        assert rec["status"] == "ok", rec["error_message"]
        first = rec["first_attempt"]["sandbox"]
        assert first["verified_outcome"] is False
        assert first["total_checks"] == 10 and first["passed_checks"] < 10
        assert rec["first_attempt"]["patch_extracted"] is True
        assert rec["retries_used"] == 1
        assert rec["final"]["sandbox"]["verified_outcome"] is False
        failing = [c["check_id"] for c in first["checks"] if not c["passed"]]
        retry_msg = [t for t in rec["turns"] if t["attempt"] == 2][0]["user_message"]
        assert all(f"FAIL {cid} " in retry_msg for cid in failing)


def test_truncated_patch_is_not_extracted() -> None:
    agent = FakeAgent(
        texts={"patch_author": "Here you go:\n```python\ndef f(:\n    pass"},
        stop_reasons={"patch_author": "max_tokens"},
    )
    rec = run("shared_bus_matched_gate", agent, FakeSandbox([False, False]))
    assert rec["first_attempt"]["patch_extracted"] is False
    assert rec["first_attempt"]["patch_author_stop_reason"] == "max_tokens"


# --------------------------------------------------------------------------------------------------
# 5. Cold-cache nonce isolation
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("arm_id", ["isolated_cached_gate", "tiered_gate"])
def test_cached_arms_use_per_run_nonce_prefix(arm_id: str) -> None:
    a1, a2 = FakeAgent(), FakeAgent()
    r1 = run(arm_id, a1, FakeSandbox([False, True]))
    r2 = run(arm_id, a2)
    p1 = {c["shared_repo_prefix"] for c in a1.calls}
    p2 = {c["shared_repo_prefix"] for c in a2.calls}
    assert len(p1) == 1 and len(p2) == 1 and p1 != p2
    assert r1["run_nonce"] and r2["run_nonce"] and r1["run_nonce"] != r2["run_nonce"]
    (prefix1,) = p1
    assert prefix1 == f"<!-- run:{r1['run_nonce']} -->\n" + SHARED_REPO_PREFIX_MARKDOWN


@pytest.mark.parametrize("arm_id", ["shared_bus_matched_gate", "shared_bus_tiered_gate"])
def test_shared_bus_arms_pass_empty_prefix(arm_id: str) -> None:
    agent = FakeAgent()
    rec = run(arm_id, agent)
    assert all(c["shared_repo_prefix"] == "" for c in agent.calls)
    assert rec["run_nonce"] is None


# --------------------------------------------------------------------------------------------------
# 6-7. Errors and serialisation
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("arm_id", list(fr.ARM_IDS))
def test_exception_on_turn_three_is_recorded_not_raised(arm_id: str) -> None:
    rec = run(arm_id, FakeAgent(fail_on_call=3))
    assert rec["status"] == "error"
    assert "TimeoutError" in rec["error_message"]
    assert len(rec["turns"]) == 2
    assert rec["first_attempt"] is None and rec["final"] is None
    assert rec["finished_at"]
    json.dumps(rec)


def test_record_is_json_serialisable_with_full_text() -> None:
    long_text = "```python\n" + "X = 1\n" * 5000 + "```"
    rec = run("shared_bus_matched_gate", FakeAgent(texts={"patch_author": long_text}), FakeSandbox([False, True]))
    back = json.loads(json.dumps(rec))
    assert back == rec
    for key in ("schema_version", "run_id", "arm_id", "preset_id", "repeat_index", "started_at", "finished_at"):
        assert key in back
    assert back["schema_version"] == 1
    author = [t for t in back["turns"] if t["agent_role"] == "patch_author"][0]
    assert author["raw_text"] == long_text
    assert UNFILTERED_REPO_AND_TELEMETRY_NOISE in back["turns"][0]["user_message"]
    for t in back["turns"]:
        for field in (
            "step_number", "agent_role", "attempt", "model_id", "intended_model_id", "max_tokens", "stop_reason",
            "latency_ms", "input_tokens", "output_tokens", "thinking_tokens", "cache_creation_tokens",
            "cache_read_tokens", "system_prompt", "user_message", "raw_text",
        ):
            assert field in t
    assert not any("cost" in k or "usd" in k for k in back)


# --------------------------------------------------------------------------------------------------
# 8. Resume / selection
# --------------------------------------------------------------------------------------------------


def _rec(arm: str, preset: str, rep: int, status: str = "ok", verified: bool = True) -> dict[str, Any]:
    sbx = make_sbx(verified)
    return {
        "arm_id": arm,
        "preset_id": preset,
        "repeat_index": rep,
        "status": status,
        "turns": [],
        "first_attempt": {"sandbox": sbx},
        "final": {"sandbox": sbx},
    }


def test_plan_matrix_interleaves_repeat_preset_arm() -> None:
    plan = fr.plan_matrix(["a1", "a2"], ["p1", "p2"], 2)
    assert plan[:4] == [("a1", "p1", 0), ("a2", "p1", 0), ("a1", "p2", 0), ("a2", "p2", 0)]
    assert len(plan) == 8 and plan[4] == ("a1", "p1", 1)


def test_select_pending_skips_ok_retries_errors_keeps_sandbox_failures() -> None:
    planned = fr.plan_matrix(["a1"], ["p1"], 4)
    existing = [
        _rec("a1", "p1", 0, "ok"),
        _rec("a1", "p1", 1, "error"),
        _rec("a1", "p1", 2, "ok", verified=False),
        _rec("a1", "p1", 3, "error"),
        _rec("a1", "p1", 3, "ok"),
    ]
    assert fr.select_pending(planned, existing) == [("a1", "p1", 1)]


# --------------------------------------------------------------------------------------------------
# 9. Summary maths
# --------------------------------------------------------------------------------------------------


def _turn(
    role: str,
    model: str = S,
    *,
    inp: int = 1000,
    out: int = 100,
    cw: int = 0,
    cr: int = 0,
    stop: str = "end_turn",
    intended: str | None = None,
    attempt: int = 1,
    latency: int = 1000,
) -> dict[str, Any]:
    return {
        "agent_role": role,
        "attempt": attempt,
        "model_id": model,
        "intended_model_id": intended or model,
        "input_tokens": inp,
        "output_tokens": out,
        "cache_creation_tokens": cw,
        "cache_read_tokens": cr,
        "thinking_tokens": 0,
        "stop_reason": stop,
        "latency_ms": latency,
    }


def _full(
    arm: str, preset: str, rep: int, first_ok: bool, final_ok: bool, turns: list[dict[str, Any]], **kw: Any
) -> dict[str, Any]:
    r = {
        "run_id": f"{arm}-{preset}-{rep}",
        "arm_id": arm,
        "preset_id": preset,
        "repeat_index": rep,
        "status": kw.get("status", "ok"),
        "turns": turns,
        "first_attempt": {
            "patch_extracted": True,
            "patch_author_stop_reason": "end_turn",
            "sandbox": make_sbx(first_ok, ("ADV-01", "AST-SEC-01")),
        },
        "final": {
            "patch_extracted": kw.get("final_extracted", True),
            "patch_author_stop_reason": kw.get("final_stop", "end_turn"),
            "sandbox": make_sbx(final_ok, ("ADV-01", "AST-SEC-01")),
        },
        "retries_used": kw.get("retries", 0),
        "error_message": kw.get("error_message"),
    }
    return r


def test_cold_warm_rule_matches_runner() -> None:
    from app.archetypes.cat6_swarms.runner import _compute_step_cold_warm

    turns = [
        _turn("orchestrator_plan", H, cr=6000),  # billed as a read (warmed elsewhere) -> cold prices a write
        _turn("ci_triager", H, cr=6000),
        _turn("patch_author", S, cw=6000),
        _turn("security_critic", H, cw=6000),  # billed as a write -> warm prices a read
        _turn("orchestrator_merge", H, inp=500),  # no prefix tokens -> billed in both views
    ]
    cold, warm = fr.cold_warm_costs_usd(turns, cached_arm=True)
    seen: set[str] = set()
    exp_cold = exp_warm = 0.0
    for t in turns:
        fin = compute_run_finops(
            t["model_id"], t["input_tokens"], t["output_tokens"], t["cache_creation_tokens"], t["cache_read_tokens"]
        )
        c, w = _compute_step_cold_warm(rung_id="tiered_hybrid_cpo_swarm", finops=fin, seen_cache_models=seen)
        exp_cold += c
        exp_warm += w
    assert cold == pytest.approx(exp_cold, abs=1e-8)
    assert warm == pytest.approx(exp_warm, abs=1e-8)
    hw = compute_run_finops(H, 1000, 100, 6000, 0).total_cost_usd
    hr = compute_run_finops(H, 1000, 100, 0, 6000).total_cost_usd
    sw = compute_run_finops(S, 1000, 100, 6000, 0).total_cost_usd
    sr = compute_run_finops(S, 1000, 100, 0, 6000).total_cost_usd
    plain = compute_run_finops(H, 500, 100).total_cost_usd
    assert cold == pytest.approx(hw + hr + sw + hr + plain, abs=1e-8)
    assert warm == pytest.approx(hr + hr + sr + hr + plain, abs=1e-8)
    # uncached arm: both views equal billed
    billed = sum(fr.turn_billed_cost_usd(t) for t in turns)
    assert fr.cold_warm_costs_usd(turns, cached_arm=False) == (pytest.approx(billed), pytest.approx(billed))


def test_wilson_interval_known_values() -> None:
    lo, hi = fr.wilson_interval(1, 15)
    assert lo == pytest.approx(0.0119, abs=1e-4) and hi == pytest.approx(0.2982, abs=1e-4)
    lo, hi = fr.wilson_interval(15, 15)
    assert lo == pytest.approx(0.7961, abs=1e-4) and hi == pytest.approx(1.0)
    lo, hi = fr.wilson_interval(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-4) and hi == pytest.approx(0.7634, abs=1e-4)
    assert fr.wilson_interval(0, 0) is None


def test_summary_maths_on_hand_built_records() -> None:
    arm, other = "isolated_cached_gate", "shared_bus_matched_gate"
    t_ok = [_turn("patch_author", cw=100), _turn("security_critic", stop="max_tokens")]
    t_fail = [
        _turn("patch_author", stop="max_tokens"),
        _turn("patch_author", attempt=2, stop="max_tokens"),
        _turn("orchestrator_merge", H, intended=S),  # silent fallback
    ]
    records = [
        _full(arm, "inc-01", 0, True, True, t_ok),
        _full(arm, "inc-02", 0, False, True, t_ok, retries=1),
        _full(arm, "inc-03", 0, False, False, t_fail, retries=1, final_stop="max_tokens"),
        _full(arm, "inc-03", 0, False, False, [_turn("orchestrator_plan")], status="error", error_message="boom"),
        _full(other, "inc-01", 0, False, False, [_turn("patch_author")]),
    ]
    s = fr.summarise(records, arm_ids=[arm, other], preset_ids=["inc-01", "inc-02", "inc-03"])
    a = s["arms"][arm]
    assert a["runs"] == 3 and a["error_records"] == 1
    assert a["first_attempt_verified"] == 1 and a["final_verified"] == 2
    assert a["first_attempt_verified_rate"] == pytest.approx(1 / 3)
    assert a["final_verified_rate"] == pytest.approx(2 / 3)
    assert a["final_checks_passed"] == 10 + 10 + 8 and a["final_checks_total"] == 30
    assert a["first_attempt_checks_passed"] == 10 + 8 + 8
    assert a["retries_used"] == 2 and a["retries_fail_to_pass"] == 1
    fb = a["failure_breakdown"]
    assert fb["final_failed_runs"] == 1
    assert fb["runs_with_failing_category"] == {"ci_unit": 0, "adversarial": 1, "ast": 1}
    assert fb["patch_author_stopped_on_max_tokens"] == 1
    mt = a["max_tokens_stops"]
    assert mt["turns"] == 4 and mt["total_turns"] == 7
    assert mt["by_role"]["patch_author"] == {"max_tokens": 2, "total": 4}
    assert mt["by_role"]["security_critic"] == {"max_tokens": 2, "total": 2}
    stopped = {(x["arm_id"], x["preset_id"], x["repeat_index"], x["agent_role"], x["attempt"]) for x in s["max_tokens_stopped_turns"]}
    assert stopped == {
        (arm, "inc-01", 0, "security_critic", 1),
        (arm, "inc-02", 0, "security_critic", 1),
        (arm, "inc-03", 0, "patch_author", 1),
        (arm, "inc-03", 0, "patch_author", 2),
    }

    billed = [fr.record_billed_cost_usd(r) for r in records[:3]]
    assert a["total_spend_usd"]["billed"] == pytest.approx(sum(billed))
    assert a["cost_per_verified_outcome_usd"]["billed"] == pytest.approx(sum(billed) / 2)
    assert a["cost_per_first_attempt_verified_outcome_usd"]["billed"] == pytest.approx(sum(billed) / 1)
    assert a["cost_per_run_usd"]["billed"]["mean"] == pytest.approx(sum(billed) / 3)
    assert a["cost_per_1k_runs_usd"]["billed"] == pytest.approx(sum(billed) / 3 * 1000)
    assert a["model_latency_ms_per_run"]["mean"] == pytest.approx((2000 + 2000 + 3000) / 3)
    assert a["tokens_per_run"]["output"] == {"mean": pytest.approx(700 / 3), "min": 200, "max": 300}

    o = s["arms"][other]
    assert o["final_verified"] == 0
    assert o["cost_per_verified_outcome_usd"] == {"billed": None, "cold": None, "warm": None}

    assert s["error_records"] == 1 and s["errors"][0]["error_message"] == "boom"
    assert [(f["arm_id"], f["agent_role"], f["model_id"]) for f in s["model_fallbacks"]] == [
        (arm, "orchestrator_merge", H)
    ]
    assert s["matrix"]["complete"] is False and s["matrix"]["balanced"] is False
    assert ["shared_bus_matched_gate", "inc-02", 0] in s["matrix"]["missing_keys"]
    assert s["arms"][arm]["by_preset"]["inc-03"]["error_records"] == 1
    json.dumps(s)


def test_summary_uses_latest_ok_record_per_key() -> None:
    arm = "tiered_gate"
    records = [
        _full(arm, "inc-01", 0, False, False, [_turn("patch_author")]),
        _full(arm, "inc-01", 0, True, True, [_turn("patch_author")]),
    ]
    s = fr.summarise(records, arm_ids=[arm], preset_ids=["inc-01"])
    assert s["arms"][arm]["runs"] == 1 and s["arms"][arm]["final_verified"] == 1
    assert s["superseded_ok_records"] == 1
    assert s["matrix"]["complete"] is True and s["matrix"]["balanced"] is True


def test_analysis_markdown_renders() -> None:
    spec = importlib.util.spec_from_file_location("analyze_cat6_fair_rerun", BACKEND_DIR / "scripts" / "analyze_cat6_fair_rerun.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    records = [
        _full("isolated_cached_gate", "inc-01", 0, False, True, [_turn("patch_author", cw=6000)], retries=1),
        _full("shared_bus_matched_gate", "inc-01", 0, False, False, [_turn("patch_author", stop="max_tokens")]),
        _full("tiered_gate", "inc-01", 0, False, False, [_turn("ci_triager", H)], status="error", error_message="x"),
    ]
    md = mod.render_markdown(fr.summarise(records))
    assert "## Main results (per arm)" in md and "## Data quality" in md and "How to read the cost views" in md
    assert "`shared_bus_matched_gate`" in md
    assert "Individual turns stopped on `max_tokens` (ok runs used + error records): 1." in md
    assert "`shared_bus_matched_gate` inc-01 r0 (ok) step None `patch_author` attempt 1: cap None" in md
    assert "## Design: with and without the deck's lever" in md and "`shared_bus_tiered_gate`: run pending" in md
    assert "(not run)" not in md
    assert "shared_bus_original" not in md


# --------------------------------------------------------------------------------------------------
# 10. Budget guard + CLI dry run
# --------------------------------------------------------------------------------------------------


def test_budget_guard_stops_at_cap() -> None:
    turn = _turn("patch_author", inp=1_000_000, out=0)  # $2.00 at Sonnet input rate
    rec = {"turns": [turn]}
    assert fr.record_billed_cost_usd(rec) == pytest.approx(2.0)
    guard = fr.BudgetGuard(5.0, [rec])
    assert guard.spent_usd == pytest.approx(2.0) and not guard.exhausted
    guard.add(rec)
    assert not guard.exhausted
    guard.add(rec)
    assert guard.exhausted  # 6.0 >= 5.0
    assert fr.BudgetGuard(2.0, [rec]).exhausted  # reaching the cap exactly also stops


def test_runner_dry_run_makes_no_calls(tmp_path: Path) -> None:
    out = tmp_path / "runs.jsonl"
    out.write_text(json.dumps(_rec("tiered_gate", "inc-01", 0)) + "\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(BACKEND_DIR / "scripts" / "cat6_fair_rerun.py"), "--dry-run", "--repeats", "2", "--out", str(out)],
        capture_output=True,
        text=True,
        timeout=60,
        env={"PATH": "/usr/bin:/bin", "NOVAMART_TRACES_DIR": str(tmp_path / "traces")},
    )
    assert proc.returncode == 0, proc.stderr
    assert "24 runs; 1 already ok, 23 pending" in proc.stdout
    assert "Dry run: no API calls made." in proc.stdout
    assert out.read_text(encoding="utf-8").count("\n") == 1


# --------------------------------------------------------------------------------------------------
# 11. Run-pending arms, Haiku long-prompt pricing, dry-run cost estimate
# --------------------------------------------------------------------------------------------------

RECORDS_PATH = BACKEND_DIR / "experiments" / "cat6_fair_rerun" / "runs.jsonl"


def _recorded() -> list[dict[str, Any]]:
    return [json.loads(x) for x in RECORDS_PATH.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_summary_reports_arm_without_records_as_run_pending() -> None:
    records = [_full(a, p, 0, True, True, [_turn("patch_author")]) for a in ("shared_bus_matched_gate", "isolated_cached_gate", "tiered_gate")
               for p in ("inc-01", "inc-02", "inc-03")]
    s = fr.summarise(records)
    assert s["pending_arm_ids"] == ["shared_bus_tiered_gate"]
    assert "shared_bus_tiered_gate" not in s["arm_ids"] and "shared_bus_tiered_gate" not in s["arms"]
    assert s["matrix"]["complete"] is True and s["matrix"]["expected_runs"] == 9  # pending arm not counted as missing
    assert s["design"]["cell_status"]["without|tiered"] == fr.RUN_PENDING == "run pending"
    assert s["design"]["cells"]["without|tiered"] == "shared_bus_tiered_gate"
    # one recorded run makes it a normal (incomplete) arm
    s2 = fr.summarise([*records, _full("shared_bus_tiered_gate", "inc-01", 0, True, True, [_turn("patch_author")])])
    assert s2["pending_arm_ids"] == [] and s2["arms"]["shared_bus_tiered_gate"]["runs"] == 1
    assert s2["matrix"]["complete"] is False and ["shared_bus_tiered_gate", "inc-02", 0] in s2["matrix"]["missing_keys"]


def test_haiku_long_prompt_rate_applies_only_above_100k() -> None:
    from app.core.pricing import HAIKU_LONG_PROMPT_INPUT_OUTPUT_PER_1M_USD, HAIKU_LONG_PROMPT_THRESHOLD_TOKENS

    assert HAIKU_LONG_PROMPT_THRESHOLD_TOKENS == 100_000
    assert HAIKU_LONG_PROMPT_INPUT_OUTPUT_PER_1M_USD == {H: (0.50, 2.50)}
    at = fr.price_call_usd(H, uncached=100_000, cache_write=0, cache_read=0, output=1000)
    assert at == pytest.approx(compute_run_finops(H, 100_000, 1000).total_cost_usd)  # <=100K: standard card
    over = fr.price_call_usd(H, uncached=100_001, cache_write=0, cache_read=0, output=1000)
    assert over == pytest.approx((100_001 * 0.50 + 1000 * 2.50) / 1e6)
    son = fr.price_call_usd(S, uncached=150_000, cache_write=0, cache_read=0, output=1000)
    assert son == pytest.approx(compute_run_finops(S, 150_000, 1000).total_cost_usd)  # Sonnet unchanged
    turn = _turn("security_critic", H, inp=120_000, out=500)
    assert fr.turn_billed_cost_usd(turn) == pytest.approx((120_000 * 0.50 + 500 * 2.50) / 1e6)


def test_estimate_reprices_reference_runs_at_the_new_arms_models() -> None:
    ref = [_full("shared_bus_matched_gate", "inc-01", r, True, True, [
        _turn("orchestrator_plan", inp=40_000, out=500), _turn("ci_triager", inp=41_000, out=600),
        _turn("patch_author", inp=42_000, out=2000), _turn("security_critic", inp=45_000, out=500),
        _turn("orchestrator_merge", inp=46_000, out=400)]) for r in range(2)]
    est = fr.estimate_run("shared_bus_tiered_gate", "inc-01", ref)
    assert est["reference_arm_id"] == "shared_bus_matched_gate" and est["reference_runs"] == 2
    exp = sum(compute_run_finops(m, i, o).total_cost_usd for m, i, o in (
        (H, 40_000, 500), (H, 41_000, 600), (S, 42_000, 2000), (H, 45_000, 500), (H, 46_000, 400)))
    assert est["typical_usd"] == pytest.approx(exp)
    assert est["max_haiku_prompt_typical"] == {"prompt_tokens": 46_000, "role": "orchestrator_merge"}
    # worst: merge prompt = 46k + caps of the 5 earlier calls (4k+4k+16k+16k+4k) + the retry message allowance
    assert est["max_haiku_prompt_worst"] == {"prompt_tokens": 46_000 + 44_000 + fr.RETRY_MESSAGE_TOKEN_ALLOWANCE, "role": "orchestrator_merge"}
    assert est["haiku_long_prompt_calls_worst"] == 0 and est["worst_case_usd"] > est["typical_usd"]
    # a bigger recorded thread pushes the worst-case merge prompt over 100K: priced at the long-prompt rate
    big = [{**r, "turns": [{**t, "input_tokens": t["input_tokens"] + 20_000} for t in r["turns"]]} for r in ref]
    est_big = fr.estimate_run("shared_bus_tiered_gate", "inc-01", big)
    assert est_big["haiku_long_prompt_calls_worst"] >= 1
    m = fr.estimate_matrix([("shared_bus_tiered_gate", "inc-01", 0), ("shared_bus_tiered_gate", "inc-01", 1)], ref)
    assert m["per_arm"]["shared_bus_tiered_gate"]["runs"] == 2 and m["total_typical_usd"] == pytest.approx(2 * exp)
    with pytest.raises(ValueError, match="No ok records"):
        fr.estimate_run("shared_bus_tiered_gate", "inc-01", [])


@pytest.mark.skipif(not RECORDS_PATH.is_file(), reason="records not present")
def test_largest_haiku_prompt_of_the_new_arm_stays_under_the_long_prompt_tier() -> None:
    """On the recorded shared-bus runs, no Haiku-position call of the new arm reaches 100K prompt tokens, even in the worst case."""
    recs = _recorded()
    keys = fr.plan_matrix(["shared_bus_tiered_gate"], [p["id"] for p in CAT6_PRESETS], 5)
    m = fr.estimate_matrix(keys, recs)
    slot = m["per_arm"]["shared_bus_tiered_gate"]
    assert slot["haiku_long_prompt_calls_typical"] == 0 and slot["haiku_long_prompt_calls_worst"] == 0
    assert slot["max_haiku_prompt_worst"]["prompt_tokens"] < 100_000
    assert 0 < m["total_typical_usd"] < m["total_worst_case_usd"]


def test_dry_run_prints_cost_estimate_for_new_arm(tmp_path: Path) -> None:
    out = tmp_path / "runs.jsonl"
    ref = [_full("shared_bus_matched_gate", p, 0, True, True, [_turn(r, inp=40_000) for r in fr.ROLE_SEQUENCE])
           for p in ("inc-01", "inc-02", "inc-03")]
    out.write_text("".join(json.dumps(r) + "\n" for r in ref), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(BACKEND_DIR / "scripts" / "cat6_fair_rerun.py"), "--dry-run", "--arms", "shared_bus_tiered_gate",
         "--repeats", "5", "--out", str(out)],
        capture_output=True, text=True, timeout=60,
        env={"PATH": "/usr/bin:/bin", "NOVAMART_TRACES_DIR": str(tmp_path / "traces")},
    )
    assert proc.returncode == 0, proc.stderr
    assert "15 runs; 0 already ok, 15 pending" in proc.stdout
    assert "shared_bus_tiered_gate     15 shared_bus_matched_gate" in proc.stdout
    assert "Haiku calls over 100,000 prompt tokens (long-prompt rate): 0 typical, 0 worst case." in proc.stdout
    assert "TOTAL typical $" in proc.stdout and "Dry run: no API calls made." in proc.stdout
    assert out.read_text(encoding="utf-8").count("\n") == 3
