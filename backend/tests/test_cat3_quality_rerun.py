"""Offline tests for the Category 3 quality-rerun harness and answer key (no network, no API key)."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat3_assistants import quality_rerun as qr  # noqa: E402
from app.archetypes.cat3_assistants.prompts import (  # noqa: E402
    build_cat3_system_handbook,
    get_memory_summarizer_system_prompt,
)
from app.archetypes.cat3_assistants.runner import (  # noqa: E402
    KEEP_RECENT_TURNS,
    MAX_VERBATIM_TURNS,
    assemble_cat3_messages,
    build_compaction_payload,
    compute_warm_turn_cost,
)
from app.archetypes.cat6_swarms.fair_rerun import wilson_interval  # noqa: E402
from app.core.anthropic_service import AnthropicRawResult  # noqa: E402
from app.core.pricing import compute_run_finops  # noqa: E402
from app.data.cat3_fixtures import CAT3_PRESETS, IT_HR_HANDBOOK_MARKDOWN  # noqa: E402
from app.models import Cat3ChatTurnEntry  # noqa: E402

PRESETS = {p["id"]: p for p in CAT3_PRESETS}
KEYS = qr.load_quality_keys()


def run(coro: Any) -> Any:
    return asyncio.run(coro)


# --------------------------------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------------------------------


class FakeTurn:
    """Fake run_cat3_service_desk_turn: records kwargs, replies with a deterministic text per call."""

    def __init__(self, *, fail_on_call: int | None = None, model_id: str = qr.SONNET_MODEL_ID) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail_on_call = fail_on_call
        self.model_id = model_id

    async def __call__(self, **kwargs: Any) -> AnthropicRawResult:
        self.calls.append(kwargs)
        n = len(self.calls)
        if self.fail_on_call == n:
            raise TimeoutError("simulated API timeout")
        last = kwargs["messages"][-1]["content"]
        cached = kwargs["use_prefix_cache"]
        return AnthropicRawResult(
            model_id=self.model_id,
            latency_ms=10 * n,
            input_tokens=1000 + n,
            output_tokens=200 + n,
            cache_creation_tokens=9800 if cached and n == 1 else 0,
            cache_read_tokens=9800 if cached and n > 1 else 0,
            raw_text=f"REPLY#{n} to: {last[:40]} " + "é" * 5,
            structured={},
            system_prompt=kwargs["system_text"],
            request_params={"max_tokens": kwargs["max_tokens"]},
            stop_reason="end_turn",
            thinking_tokens=0,
        )


class FakeSummarizer:
    def __init__(self, *, fail_on_call: int | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail_on_call = fail_on_call

    async def __call__(self, **kwargs: Any) -> AnthropicRawResult:
        self.calls.append(kwargs)
        n = len(self.calls)
        if self.fail_on_call == n:
            raise RuntimeError("simulated summarizer failure")
        evicted = json.loads(kwargs["compaction_payload"])["newly_evicted_turns"]
        structured = {
            "compacted_through_turn": 0,  # the harness must overwrite this with the last evicted turn
            "employee_and_device_anchors": [f"memo{n}"],
            "resolved_issues": [f"turn {t['turn_number']}" for t in evicted],
            "active_open_items": [],
            "key_numeric_facts": [],
        }
        return AnthropicRawResult(
            model_id=qr.SONNET_MODEL_ID,
            latency_ms=5,
            input_tokens=3000 + n,
            output_tokens=300 + n,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            raw_text=json.dumps(structured),
            structured=structured,
            stop_reason="end_turn",
        )


def execute(rung_id: str, preset_id: str = "desk-01", **kw: Any) -> tuple[dict[str, Any], FakeTurn, FakeSummarizer]:
    turn = kw.pop("turn_call", FakeTurn())
    summ = kw.pop("summarizer_call", FakeSummarizer())
    record = run(
        qr.execute_session_run(
            preset=PRESETS[preset_id],
            rung_id=rung_id,
            repeat_index=kw.pop("repeat_index", 0),
            api_key="test-key",
            probes=kw.pop("probes", qr.probes_for(KEYS, preset_id)),
            turn_call=turn,
            summarizer_call=summ,
        )
    )
    return record, turn, summ


def expected_message_plan(rung_id: str, n_turns: int = 10) -> list[tuple[list[int], int]]:
    """(verbatim turn numbers, compacted_through) the runner's rule gives before each turn 1..n."""
    verbatim: list[int] = []
    through = 0
    plan = []
    for t in range(1, n_turns + 1):
        if rung_id == "prefix_cached_summarized" and len(verbatim) >= MAX_VERBATIM_TURNS:
            through = verbatim[-KEEP_RECENT_TURNS - 1]
            verbatim = verbatim[-KEEP_RECENT_TURNS:]
        plan.append((list(verbatim), through))
        verbatim.append(t)
    return plan


# --------------------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("rung_id", qr.RUNG_IDS)
def test_turn_and_compaction_sequence_matches_runner_rule(rung_id: str) -> None:
    record, turn, summ = execute(rung_id)
    assert record["status"] == "ok", record["error_message"]
    assert [t["turn_number"] for t in record["turns"]] == list(range(1, 11))
    compacted_before = [t["turn_number"] for t in record["turns"] if t["compaction"]]
    if rung_id == "prefix_cached_summarized":
        assert compacted_before == [5, 8]
        assert record["turns"][4]["compaction"]["evicted_turns"] == [1, 2, 3]
        assert record["turns"][7]["compaction"]["evicted_turns"] == [4, 5, 6]
        assert record["probe_compaction"]["evicted_turns"] == [7, 8, 9]
        assert record["probe_compaction"]["kept_turns"] == [10]
        assert len(summ.calls) == 3
        assert all(c["max_tokens"] == 1600 for c in summ.calls)
        assert all(c["system_prompt"] == get_memory_summarizer_system_prompt() for c in summ.calls)
    else:
        assert compacted_before == []
        assert record["probe_compaction"] is None
        assert summ.calls == []
    session_calls = turn.calls[:10]
    assert all(c["max_tokens"] == 4096 for c in turn.calls)
    assert all(c["use_prefix_cache"] is (rung_id != "naive_full_history") for c in turn.calls)
    assert len(session_calls) == 10 and len(turn.calls) == 10 + 6


@pytest.mark.parametrize("rung_id", qr.RUNG_IDS)
def test_message_assembly_per_turn_matches_runner_helpers(rung_id: str) -> None:
    record, turn, _ = execute(rung_id)
    preset = PRESETS["desk-01"]
    by_num = {t["turn_number"]: t for t in record["turns"]}
    plan = expected_message_plan(rung_id)
    for idx, (verbatim_nums, through) in enumerate(plan):
        t_num = idx + 1
        memory = by_num[t_num]["memory_summary_snapshot"]
        assert by_num[t_num]["verbatim_turn_numbers"] == verbatim_nums
        assert by_num[t_num]["active_history_turns"] == len(verbatim_nums)
        assert by_num[t_num]["compacted_through_turn"] == through
        if through:
            assert memory["compacted_through_turn"] == through
        else:
            assert memory is None
        entries = [
            Cat3ChatTurnEntry(
                turn_number=n,
                user_message=preset["turns"][n - 1]["user_message"],
                assistant_message=by_num[n]["assistant_message"],
            )
            for n in verbatim_nums
        ]
        expected = assemble_cat3_messages(
            verbatim_turns=entries,
            memory_summary=memory,
            current_user_message=preset["turns"][idx]["user_message"],
        )
        assert turn.calls[idx]["messages"] == expected


def test_compaction_payload_uses_runner_builder() -> None:
    record, _, summ = execute("prefix_cached_summarized")
    preset = PRESETS["desk-01"]
    by_num = {t["turn_number"]: t for t in record["turns"]}

    def entries(nums: list[int]) -> list[Cat3ChatTurnEntry]:
        return [
            Cat3ChatTurnEntry(
                turn_number=n,
                user_message=preset["turns"][n - 1]["user_message"],
                assistant_message=by_num[n]["assistant_message"],
            )
            for n in nums
        ]

    assert summ.calls[0]["compaction_payload"] == build_compaction_payload(None, entries([1, 2, 3]))
    mem3 = by_num[5]["memory_summary_snapshot"]
    assert summ.calls[1]["compaction_payload"] == build_compaction_payload(mem3, entries([4, 5, 6]))
    assert record["turns"][4]["compaction"]["payload"] == summ.calls[0]["compaction_payload"]
    assert record["turns"][7]["compaction"]["memory_after"]["compacted_through_turn"] == 6


def test_nonce_prefix_same_within_run_and_different_across_runs() -> None:
    rec_a, turn_a, _ = execute("prefix_cached_history")
    rec_b, turn_b, _ = execute("prefix_cached_history")
    systems_a = {c["system_text"] for c in turn_a.calls}
    systems_b = {c["system_text"] for c in turn_b.calls}
    assert len(systems_a) == 1 and len(systems_b) == 1
    sys_a, sys_b = systems_a.pop(), systems_b.pop()
    assert rec_a["run_nonce"] != rec_b["run_nonce"]
    assert sys_a != sys_b
    base = build_cat3_system_handbook("prefix_cached_history", PRESETS["desk-01"]["employee_profile"])
    assert sys_a == f"<!-- run:{rec_a['run_nonce']} -->\n" + base
    # naive rung gets the identical treatment
    rec_n, turn_n, _ = execute("naive_full_history")
    base_n = build_cat3_system_handbook("naive_full_history", PRESETS["desk-01"]["employee_profile"])
    assert {c["system_text"] for c in turn_n.calls} == {f"<!-- run:{rec_n['run_nonce']} -->\n" + base_n}


@pytest.mark.parametrize("rung_id", qr.RUNG_IDS)
def test_probes_branch_from_end_of_turn_10(rung_id: str) -> None:
    probes = qr.probes_for(KEYS, "desk-01")
    record, turn, summ = execute(rung_id)
    probe_calls = turn.calls[10:]
    questions = [p["question"] for p in probes]
    assert sorted(c["messages"][-1]["content"] for c in probe_calls) == sorted(questions)
    by_num = {t["turn_number"]: t for t in record["turns"]}
    preset = PRESETS["desk-01"]
    for c in probe_calls:
        msgs = c["messages"]
        # Only this probe's own question appears; no other probe leaks into the branch.
        contents = [m["content"] for m in msgs]
        assert sum(1 for q in questions if q in contents) == 1
        assert msgs[-1]["role"] == "user" and msgs[-1]["content"] in questions
        if rung_id == "prefix_cached_summarized":
            assert len(msgs) == 2 + 2 + 1
            assert msgs[0]["content"].startswith("=== COMPACTED SESSION MEMORY STATE (Turns 1–9) ===")
            assert msgs[2]["content"] == preset["turns"][9]["user_message"]
            assert msgs[3]["content"] == by_num[10]["assistant_message"]
        else:
            assert len(msgs) == 21
            assert msgs[-2]["content"] == by_num[10]["assistant_message"]
            assert [m["content"] for m in msgs[0:20:2]] == [t["user_message"] for t in preset["turns"]]
            assert [m["content"] for m in msgs[1:20:2]] == [by_num[n]["assistant_message"] for n in range(1, 11)]
    assert [p["probe_id"] for p in record["probes"]] == [p["probe_id"] for p in probes]
    for p in record["probes"]:
        if rung_id == "prefix_cached_summarized":
            assert p["compacted_through_turn"] == 9 and p["verbatim_turn_numbers"] == [10]
        else:
            assert p["compacted_through_turn"] == 0 and p["verbatim_turn_numbers"] == list(range(1, 11))
    expected_summ = 3 if rung_id == "prefix_cached_summarized" else 0
    assert len(summ.calls) == expected_summ


def test_summarized_probe_phase_runs_exactly_one_compaction() -> None:
    record, _, summ = execute("prefix_cached_summarized")
    assert len(summ.calls) == 3
    pc = record["probe_compaction"]
    assert pc["memory_after"]["compacted_through_turn"] == 9
    prior = record["turns"][9]["memory_summary_snapshot"]
    evicted = json.loads(pc["payload"])
    assert evicted["prior_session_memory"] == prior
    assert [t["turn_number"] for t in evicted["newly_evicted_turns"]] == [7, 8, 9]


def test_error_mid_session_is_recorded_not_raised() -> None:
    record, turn, _ = execute("prefix_cached_history", turn_call=FakeTurn(fail_on_call=4))
    assert record["status"] == "error"
    assert "TimeoutError" in record["error_message"]
    assert [t["turn_number"] for t in record["turns"]] == [1, 2, 3]
    assert record["probes"] == []
    assert record["finished_at"]


def test_summarizer_error_is_recorded() -> None:
    record, _, _ = execute("prefix_cached_summarized", summarizer_call=FakeSummarizer(fail_on_call=2))
    assert record["status"] == "error" and "RuntimeError" in record["error_message"]
    assert [t["turn_number"] for t in record["turns"]] == [1, 2, 3, 4, 5, 6, 7]


def test_probe_error_keeps_completed_probes() -> None:
    record, _, _ = execute("naive_full_history", turn_call=FakeTurn(fail_on_call=12))
    assert record["status"] == "error"
    assert len(record["turns"]) == 10
    assert len(record["probes"]) == 5


def test_record_json_serialisable_with_full_texts() -> None:
    record, turn, _ = execute("prefix_cached_summarized")
    round_trip = json.loads(json.dumps(record, ensure_ascii=False))
    assert round_trip == record
    assert record["schema_version"] == 1
    for t in record["turns"]:
        assert t["assistant_message"].startswith("REPLY#") and t["assistant_message"].endswith("é" * 5)
        assert t["user_message"] == PRESETS["desk-01"]["turns"][t["turn_number"] - 1]["user_message"]
        for field in (
            "model_id", "stop_reason", "latency_ms", "input_tokens", "output_tokens", "thinking_tokens",
            "cache_creation_tokens", "cache_read_tokens", "active_history_turns", "compacted_through_turn",
            "memory_summary_snapshot", "topic_tag",
        ):
            assert field in t
    for p in record["probes"]:
        assert p["answer"].startswith("REPLY#") and p["question"]

    def keys_of(obj: Any) -> list[str]:
        if isinstance(obj, dict):
            return [k for k in obj] + [x for v in obj.values() for x in keys_of(v)]
        if isinstance(obj, list):
            return [x for v in obj for x in keys_of(v)]
        return []

    # no dollars in the record (the compaction payload / memory are strings or model-shaped dicts)
    assert not [k for k in keys_of({k: v for k, v in record.items()}) if "usd" in k.lower() or "cost" in k.lower()]


# --------------------------------------------------------------------------------------------------
# Normalisation + scoring
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Hello   World", "hello world"),
        ("**bold** and `code` ~~gone~~", "bold and code gone"),
        ("UNPAID_LOA_HOLD", "unpaid_loa_hold"),
        ("a–b—c−d", "a-b-c-d"),
        ("“quote” ‘single’", "\"quote\" 'single'"),
        ("₹64,200", "64200"),
        ("INR 64200", "64200"),
        ("64,200 INR", "64200"),
        ("Rs. 2,50,000", "250000"),
        ("$2,500 USD", "2500"),
        ("₹1,48,000 (~$1,775 USD)", "148000 (~1775)"),
        ("turns 1,2,3", "turns 1,2,3"),
        ("hrs 5", "hrs 5"),
        ("line1\n line2", "line1 line2"),
    ],
)
def test_normalisation_rules(raw: str, expected: str) -> None:
    assert qr.normalise_text(raw) == expected


def test_boundary_guard() -> None:
    assert qr.fact_hit("Account XXXX-4419.", ["4419"])
    assert not qr.fact_hit("ref 44190", ["4419"])
    assert not qr.fact_hit("ref 14419", ["4419"])
    assert not qr.fact_hit("lasts 124h", ["24h"])
    assert qr.fact_hit("lasts 24h.", ["24h"])
    assert qr.fact_hit("30 minutes", ["30 min"])
    assert not qr.fact_hit("₹2,50,000", ["2500"])
    assert qr.fact_hit("up to $2,500", ["2500"])


def test_score_reply_on_hand_built_replies() -> None:
    facts = [
        {"id": "a", "any_of": ["₹64,200"]},
        {"id": "b", "any_of": ["hr-pay-retro"]},
        {"id": "c", "any_of": ["48 business hour", "48-hour"]},
        {"id": "d", "any_of": ["dec 16", "december 16"]},
    ]
    reply = "| **HR-PAY-RETRO** | INR 64200 wired within 48–hour window |"
    assert qr.score_reply(reply, facts) == [
        {"fact_id": "a", "hit": True},
        {"fact_id": "b", "hit": True},
        {"fact_id": "c", "hit": True},
        {"fact_id": "d", "hit": False},
    ]
    assert qr.score_reply("December 16th", facts)[3]["hit"]
    assert qr.score_reply("", facts) == [{"fact_id": k, "hit": False} for k in "abcd"]


def test_score_session_routes_turn_ledger_and_probe_items() -> None:
    texts = {n: "" for n in range(1, 11)}
    texts[1] = "Queue IT-IAM-FASTPASS"
    texts[10] = "| ledger | IT-IAM-FASTPASS |"
    rows = qr.score_session(preset_id="desk-01", turn_texts=texts, probe_answers={"d1-p4-bank-account-last4": "XXXX-4419"}, keys=KEYS)
    by_id = {r["fact_id"]: r for r in rows}
    assert by_id["d1-t1-queue-it-iam-fastpass"]["hit"]
    assert by_id["d1-l1-queue-it-iam-fastpass"]["hit"] and by_id["d1-l1-queue-it-iam-fastpass"]["turn"] == 1
    assert not by_id["d1-t2-profiles-renew"]["hit"]
    assert by_id["d1-p4-bank-account-last4"]["hit"]
    assert "d1-p1-device-serial" not in by_id  # unanswered probe omitted, not a miss
    rows_partial = qr.score_session(preset_id="desk-01", turn_texts={1: "x"}, probe_answers=None, keys=KEYS)
    assert {r["kind"] for r in rows_partial} == {"turn"}
    assert all(r["turn"] == 1 for r in rows_partial)


# --------------------------------------------------------------------------------------------------
# Summary maths
# --------------------------------------------------------------------------------------------------


def _row(kind: str, turn: int, hit: bool, source: str = "handbook") -> dict[str, Any]:
    return {"fact_id": f"{kind}{turn}{hit}{source}", "kind": kind, "turn": turn, "source": source, "hit": hit}


def test_quality_metrics_windows_and_wilson() -> None:
    run_a = [
        _row("turn", 1, True), _row("turn", 4, False), _row("turn", 5, True), _row("turn", 9, True),
        _row("ledger", 2, True), _row("ledger", 5, False, "session"), _row("ledger", 8, True, "session"),
        _row("probe", 3, True), _row("probe", 7, False),
    ]
    run_b = [_row("turn", 2, True), _row("ledger", 9, False), _row("probe", 6, False)]
    m = qr.quality_metrics([run_a, run_b])
    assert m["sessions"] == 2
    t = m["turn_recall"]
    assert (t["turns_1_9"]["hits"], t["turns_1_9"]["total"]) == (4, 5)
    assert (t["turns_1_4"]["hits"], t["turns_1_4"]["total"]) == (2, 3)
    assert (t["turns_5_9"]["hits"], t["turns_5_9"]["total"]) == (2, 2)
    assert t["turns_1_9"]["rate"] == pytest.approx(0.8)
    assert t["turns_1_9"]["wilson95"] == pytest.approx(wilson_interval(4, 5))
    lo, hi = wilson_interval(4, 5)
    assert lo == pytest.approx(0.3755, abs=1e-3) and hi == pytest.approx(0.9638, abs=1e-3)
    led = m["ledger_recall"]
    assert (led["overall"]["hits"], led["overall"]["total"]) == (2, 4)
    assert (led["by_origin"]["origin_1_3"]["hits"], led["by_origin"]["origin_1_3"]["total"]) == (1, 1)
    assert (led["by_origin"]["origin_4_6"]["hits"], led["by_origin"]["origin_4_6"]["total"]) == (0, 1)
    assert (led["by_origin"]["origin_7_9"]["hits"], led["by_origin"]["origin_7_9"]["total"]) == (1, 2)
    assert (led["by_source"]["session"]["hits"], led["by_source"]["session"]["total"]) == (1, 2)
    assert (led["by_source"]["handbook"]["hits"], led["by_source"]["handbook"]["total"]) == (1, 2)
    pr = m["probe_accuracy"]
    assert (pr["overall"]["hits"], pr["overall"]["total"]) == (1, 3)
    assert (pr["by_origin"]["origin_1_6"]["hits"], pr["by_origin"]["origin_1_6"]["total"]) == (1, 2)
    assert (pr["by_origin"]["origin_7_9"]["hits"], pr["by_origin"]["origin_7_9"]["total"]) == (0, 1)
    empty = qr.quality_metrics([])
    assert empty["probe_accuracy"]["overall"] == {"hits": 0, "total": 0, "rate": None, "wilson95": None}


def test_costs_split_session_and_probe_phase() -> None:
    record, _, _ = execute("prefix_cached_summarized")
    costs = qr.record_costs(record)

    def fin(c: dict[str, Any]):
        return compute_run_finops(
            model_id=c["model_id"], input_tokens=c["input_tokens"], output_tokens=c["output_tokens"],
            cache_creation_tokens=c["cache_creation_tokens"], cache_read_tokens=c["cache_read_tokens"],
        )

    turns = record["turns"]
    comps = [t["compaction"] for t in turns if t["compaction"]]
    exp_session = sum(fin(t).total_cost_usd for t in turns) + sum(fin(c).total_cost_usd for c in comps)
    exp_warm = sum(compute_warm_turn_cost(fin(t)) for t in turns) + sum(fin(c).total_cost_usd for c in comps)
    exp_probe = sum(fin(p).total_cost_usd for p in record["probes"]) + fin(record["probe_compaction"]).total_cost_usd
    assert costs["session_billed_usd"] == pytest.approx(exp_session, abs=1e-8)
    assert costs["session_warm_usd"] == pytest.approx(exp_warm, abs=1e-8)
    assert costs["probe_billed_usd"] == pytest.approx(exp_probe, abs=1e-8)
    assert costs["session_warm_usd"] < costs["session_billed_usd"]  # turn 1 cache write priced as read
    m = qr.cost_metrics([record])
    assert m["session_compactions"]["mean"] == 2 and m["probe_phase_compactions"]["mean"] == 1
    assert m["context_prompt_tokens_at_turn"]["10"]["mean"] == qr.prompt_tokens(turns[9])


def test_summarise_end_to_end_with_fake_records() -> None:
    recs = []
    for rid in qr.RUNG_IDS:
        for pid in PRESETS:
            r, _, _ = execute(rid, pid)
            recs.append(r)
    err, _, _ = execute("naive_full_history", "desk-01", turn_call=FakeTurn(fail_on_call=2), repeat_index=1)
    recs.append(err)
    other, _, _ = execute("prefix_cached_history", "desk-01")  # another lever: ignored by the summary
    recs.append(other)
    s = qr.summarise(recs, keys=KEYS)
    assert s["rerun"]["ok_runs_used"] == 4 and s["rerun"]["error_records"] == 1
    assert s["rung_ids"] == ["naive_full_history", "prefix_cached_summarized"] and "original_capture" not in s
    assert s["rerun"]["expected_repeats"] == 2
    assert not s["rerun"]["matrix"]["complete"]
    assert len(s["misses_for_review"]) == 12 * 2  # fake answers never contain the expected values
    miss = s["misses_for_review"][0]
    assert set(miss) >= {"rung_id", "preset_id", "repeat_index", "probe_id", "expected_any_of", "answer_excerpt"}
    q = s["rerun"]["rungs"]["naive_full_history"]["quality"]
    assert q["probe_accuracy"]["overall"]["total"] == 12
    assert q["sessions"] == 2
    json.dumps(s)


def test_model_mismatch_and_non_end_turn_detection() -> None:
    record, _, _ = execute("naive_full_history", turn_call=FakeTurn(model_id="claude-sonnet-4-6"))
    mism = qr.model_mismatches([record])
    assert len(mism) == 16
    record["turns"][2]["stop_reason"] = "max_tokens"
    stops = qr.non_end_turn_calls([record])
    assert [s["call"] for s in stops] == ["turn 3"]


# --------------------------------------------------------------------------------------------------
# Golden replays
# --------------------------------------------------------------------------------------------------


def test_summarise_runs_with_zero_records() -> None:
    s = qr.summarise([], keys=KEYS)
    assert s["rerun"]["ok_runs_used"] == 0 and "original_capture" not in s
    for rid in qr.RUNG_IDS:
        assert s["rerun"]["rungs"][rid]["quality"]["sessions"] == 0


# --------------------------------------------------------------------------------------------------
# Resume + budget guard
# --------------------------------------------------------------------------------------------------


def test_plan_order_and_resume_selection() -> None:
    planned = qr.plan_matrix(list(qr.RUNG_IDS), ["desk-01", "desk-02"], 2)
    assert len(planned) == 8
    assert planned[:3] == [
        ("naive_full_history", "desk-01", 0),
        ("prefix_cached_summarized", "desk-01", 0),
        ("naive_full_history", "desk-02", 0),
    ]
    existing = [
        {"rung_id": "naive_full_history", "preset_id": "desk-01", "repeat_index": 0, "status": "ok"},
        {"rung_id": "prefix_cached_summarized", "preset_id": "desk-01", "repeat_index": 0, "status": "error"},
    ]
    pending = qr.select_pending(planned, existing)
    assert ("naive_full_history", "desk-01", 0) not in pending
    assert ("prefix_cached_summarized", "desk-01", 0) in pending
    assert len(pending) == 7


def test_budget_guard_counts_session_and_probe_phase() -> None:
    record, _, _ = execute("prefix_cached_summarized")
    total = qr.record_costs(record)["total_billed_usd"]
    assert total == pytest.approx(
        qr.record_costs(record)["session_billed_usd"] + qr.record_costs(record)["probe_billed_usd"], abs=1e-8
    )
    guard = qr.BudgetGuard(total * 1.5, [record])
    assert guard.spent_usd == pytest.approx(total)
    assert not guard.exhausted
    assert guard.add(record) == pytest.approx(total)
    assert guard.exhausted


def test_runner_cli_dry_run(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("cat3_quality_rerun_cli", BACKEND_DIR / "scripts" / "cat3_quality_rerun.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = tmp_path / "runs.jsonl"
    code = run(mod.run_matrix(mod.parse_args(["--dry-run", "--repeats", "1", "--out", str(out)])))
    assert code == 0
    text = capsys.readouterr().out
    assert "4 pending" in text and "Dry run: no API calls made." in text
    assert not out.exists()


# --------------------------------------------------------------------------------------------------
# Answer-key structural invariants
# --------------------------------------------------------------------------------------------------


def _user_msg(preset_id: str, turn: int) -> str:
    return PRESETS[preset_id]["turns"][turn - 1]["user_message"]


def _profile_text(preset_id: str) -> str:
    return " | ".join(str(v) for v in PRESETS[preset_id]["employee_profile"].values())


def _source_text(preset_id: str, source: str) -> str:
    if source == "handbook":
        return IT_HR_HANDBOOK_MARKDOWN
    if source == "profile":
        return _profile_text(preset_id)
    assert source.startswith("user_turn:"), source
    return _user_msg(preset_id, int(source.split(":", 1)[1]))


def _any_in(text: str, alts: list[str]) -> list[str]:
    norm = qr.normalise_text(text)
    return [a for a in alts if qr.contains_alternative(norm, a)]


def test_key_ids_unique_and_shapes() -> None:
    ids = [f["id"] for f in KEYS["facts"]] + [p["probe_id"] for p in KEYS["probes"]]
    assert len(ids) == len(set(ids))
    for f in KEYS["facts"]:
        assert f["preset_id"] in PRESETS
        assert f["kind"] in ("turn", "ledger")
        assert f["source"] in ("handbook", "session")
        assert ("turn" in f) == (f["kind"] == "turn") and ("origin_turn" in f) == (f["kind"] == "ledger")
        assert f["description"] and f["any_of"] and all(isinstance(a, str) and a for a in f["any_of"])
        assert set(f) == {"id", "preset_id", "kind", "turn" if f["kind"] == "turn" else "origin_turn", "source", "description", "any_of", "evidence"}
    for p in KEYS["probes"]:
        assert set(p) == {"probe_id", "preset_id", "origin_turn", "question", "any_of", "evidence", "expected_display"}
        # the display string is a readable form of an accepted value
        assert qr.fact_hit(p["expected_display"], p["any_of"]), p["probe_id"]


def test_every_evidence_quote_occurs_in_its_source() -> None:
    for item in [*KEYS["facts"], *KEYS["probes"]]:
        ev = item["evidence"]
        assert ev["source"] in ("handbook", "profile") or ev["source"].startswith("user_turn:")
        assert 0 < len(ev["quote"]) <= 200, item.get("id") or item.get("probe_id")
        assert ev["quote"] in _source_text(item["preset_id"], ev["source"]), item.get("id") or item.get("probe_id")


def test_session_facts_cite_a_user_turn_and_handbook_facts_do_not() -> None:
    for f in KEYS["facts"]:
        ev_src = f["evidence"]["source"]
        if f["source"] == "session":
            assert ev_src.startswith("user_turn:"), f["id"]
        else:
            assert ev_src in ("handbook", "profile"), f["id"]


def test_handbook_source_values_occur_in_handbook_or_profile_or_are_computed() -> None:
    """Handbook facts: some alternative is present in handbook/profile, except listed computed values."""
    # "gate 2" is the second numbered item of the handbook's SRE-ONCALL-GATE checklist (derived, not literal).
    computed_ok = {"d2-t9-gate-2-blocks"}
    for f in KEYS["facts"]:
        if f["source"] != "handbook":
            continue
        hay = IT_HR_HANDBOOK_MARKDOWN + "\n" + _profile_text(f["preset_id"])
        assert _any_in(hay, f["any_of"]) or f["id"] in computed_ok, f["id"]


def test_turn_fact_counts_per_turn() -> None:
    for pid in PRESETS:
        counts = Counter(f["turn"] for f in KEYS["facts"] if f["preset_id"] == pid and f["kind"] == "turn")
        assert set(counts) == set(range(1, 10)), pid
        assert all(2 <= c <= 4 for c in counts.values()), (pid, counts)


def test_ledger_fact_counts_and_session_share() -> None:
    for pid in PRESETS:
        ledger = [f for f in KEYS["facts"] if f["preset_id"] == pid and f["kind"] == "ledger"]
        counts = Counter(f["origin_turn"] for f in ledger)
        assert set(counts) == set(range(1, 10)), pid
        assert all(2 <= c <= 3 for c in counts.values()), (pid, counts)
        session = [f for f in ledger if f["source"] == "session"]
        assert len(session) >= 5, (pid, len(session))


def test_ledger_and_probe_values_not_restated_in_turn_10_message() -> None:
    for item in [*[f for f in KEYS["facts"] if f["kind"] == "ledger"], *KEYS["probes"]]:
        t10 = _user_msg(item["preset_id"], 10)
        # Same matcher as scoring: nothing the model could copy from the turn-10 message scores the fact.
        assert not _any_in(t10, item["any_of"]), (item.get("id") or item.get("probe_id"), _any_in(t10, item["any_of"]))


def test_probe_constraints() -> None:
    for pid in PRESETS:
        probes = qr.probes_for(KEYS, pid)
        assert len(probes) == 6, pid
        origins = [p["origin_turn"] for p in probes]
        assert sum(1 for o in origins if 1 <= o <= 6) == 4
        assert sum(1 for o in origins if 7 <= o <= 9) == 2
        assert any(1 <= o <= 3 for o in origins) and any(4 <= o <= 6 for o in origins)
        for p in probes:
            o = p["origin_turn"]
            assert p["evidence"]["source"] == f"user_turn:{o}"
            # the answer is stated in the origin turn's user message
            assert _any_in(_user_msg(pid, o), p["any_of"]), p["probe_id"]
            # ... and nowhere it could be recovered from without the conversation history
            forbidden = [IT_HR_HANDBOOK_MARKDOWN, _profile_text(pid), _user_msg(pid, 10)]
            forbidden += [_user_msg(pid, t) for t in range(o + 1, 11)]
            for text in forbidden:
                norm = qr.normalise_text(text)
                assert not [a for a in p["any_of"] if qr.normalise_text(a) in norm], (p["probe_id"], text[:60])
            # the question neither contains the answer nor hands it over
            assert not _any_in(p["question"], p["any_of"]), p["probe_id"]
            assert p["question"].startswith("Remind me")
            assert all(len(a) <= 40 for a in p["any_of"])


def test_meta_records_variant_count() -> None:
    meta = KEYS["meta"]
    assert isinstance(meta["format_variants_added_from_golden_dry_pass"], int)
    assert meta["format_variants_added_from_golden_dry_pass"] == len(meta["format_variants_added_detail"])
