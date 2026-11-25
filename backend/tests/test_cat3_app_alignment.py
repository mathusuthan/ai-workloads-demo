"""App ↔ Category 3 quality-rerun alignment: golden converter, live stop reasons, quality block, portfolio."""

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

from app.archetypes.cat3_assistants import runner  # noqa: E402
from app.archetypes.cat3_assistants.scoring import classify_probe_answer, load_quality_keys, probes_for  # noqa: E402
from app.core.anthropic_service import AnthropicRawResult  # noqa: E402
from app.data.cat3_fixtures import CAT3_PRESETS  # noqa: E402

PRESET = CAT3_PRESETS[0]
RUNS = BACKEND_DIR / "experiments" / "cat3_quality" / "runs.jsonl"


def _load_script(name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    monkeypatch.setenv("NOVAMART_TRACES_DIR", str(tmp_path / "traces"))
    spec = importlib.util.spec_from_file_location(name, BACKEND_DIR / "scripts" / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------------ 1. golden from quality rerun


def _usage(i: int) -> dict[str, int]:
    return {"input_tokens": 100 + i, "output_tokens": 50, "thinking_tokens": i % 2, "cache_creation_tokens": 0, "cache_read_tokens": 9000}


def _synthetic_record(rung_id: str, repeat_index: int, *, answer: str) -> dict[str, Any]:
    summarise = rung_id == "prefix_cached_summarized"
    turns = []
    for spec in PRESET["turns"]:
        n = int(spec["turn_number"])
        comp = None
        if summarise and n in (5, 8):
            comp = {"payload": f"P{n}", "model_id": "claude-sonnet-5-5", "latency_ms": 7, "stop_reason": "max_tokens", **_usage(n)}
        turns.append(
            {
                "turn_number": n,
                "topic_tag": spec["topic_tag"],
                "user_message": spec["user_message"],
                "assistant_message": f"{answer} turn {n}",
                "model_id": "claude-sonnet-5-5",
                "latency_ms": 10 * n,
                "stop_reason": "end_turn",
                **_usage(n),
                "active_history_turns": n - 1,
                "compacted_through_turn": (6 if n >= 8 else 3 if n >= 5 else 0) if summarise else 0,
                "memory_summary_snapshot": {"x": n} if summarise and n >= 5 else None,
                "compaction": comp,
            }
        )
    keys = load_quality_keys()
    return {
        "run_id": f"{rung_id}-{repeat_index}",
        "preset_id": PRESET["id"],
        "rung_id": rung_id,
        "repeat_index": repeat_index,
        "run_nonce": "n",
        "started_at": "2026-11-25T00:00:00+00:00",
        "status": "ok",
        "keys_version": keys["meta"]["keys_version"],
        "turns": turns,
        "probe_compaction": (
            {"evicted_turns": [7, 8, 9], "kept_turns": [10], "payload": "PP", "memory_after": {}, "model_id": "claude-sonnet-5-5",
             "stop_reason": "end_turn", "latency_ms": 5, **_usage(0)}
            if summarise
            else None
        ),
        "probes": [
            {"probe_id": p["probe_id"], "origin_turn": p["origin_turn"], "question": p["question"], "answer": answer,
             "model_id": "claude-sonnet-5-5", "stop_reason": "end_turn", "latency_ms": 3, **_usage(1),
             "active_history_turns": 1, "compacted_through_turn": 9 if summarise else 0}
            for p in probes_for(keys, PRESET["id"])
        ],
    }


def test_golden_converter_on_synthetic_records(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("build_cat3_golden_from_rerun", monkeypatch, tmp_path)
    records = []
    for rid in mod.RUNG_IDS:
        # repeat 0 answers badly, repeat 1 well: the fixed mapping must still take repeat 0
        records += [_synthetic_record(rid, 0, answer="I don't have that detail."), _synthetic_record(rid, 1, answer="perfect")]
    doc = mod.build_golden(records, source_file="x.jsonl", keys_version="k", preset_ids=[PRESET["id"]])
    p = doc["presets"][PRESET["id"]]
    assert set(p["rungs"]) == set(p["probe_phase"]) == set(p["provenance"]) == set(mod.RUNG_IDS)
    for rid in mod.RUNG_IDS:
        assert p["provenance"][rid]["repeat_index"] == 0 and p["provenance"][rid]["run_id"] == f"{rid}-0"
        turns = p["rungs"][rid]
        assert [t["stop_reason"] for t in turns] == ["end_turn"] * 10
        assert all(t["assistant_message"].startswith("I don't have") for t in turns)
        assert len(p["probe_phase"][rid]["probes"]) == 6
        summary = runner._build_cat3_summary_from_replay(rung_id=rid, raw_turns=turns)  # loadable by the app
        assert len(summary.turns) == 10
    summ = p["rungs"]["prefix_cached_summarized"]
    assert [t["turn_number"] for t in summ if t["compaction_triggered_before_turn"]] == [5, 8]
    assert {t["compaction_stop_reason"] for t in summ if t["compaction_triggered_before_turn"]} == {"max_tokens"}  # real, not hard-coded
    assert [t["compacted_turns_count"] for t in summ][4:8] == [3, 3, 3, 6]
    assert p["probe_phase"]["prefix_cached_summarized"]["compaction"]["kept_turns"] == [10]
    assert p["probe_phase"]["naive_full_history"]["compaction"] is None

    out = tmp_path / "golden.json"
    assert mod.write_if_changed(doc, out, stamp=True) is True
    first = out.read_text()
    again = mod.build_golden(copy.deepcopy(records), source_file="x.jsonl", keys_version="k", preset_ids=[PRESET["id"]])
    assert mod.write_if_changed(again, out, stamp=True) is False
    assert out.read_text() == first  # idempotent
    assert "rebuilt_at" in json.loads(first)["provenance"]


def test_golden_converter_raises_when_repeat_zero_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("build_cat3_golden_from_rerun", monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="repeat 0"):
        mod.build_golden([_synthetic_record("naive_full_history", 1, answer="x")], source_file="x", keys_version="k", preset_ids=[PRESET["id"]])


@pytest.mark.skipif(not RUNS.is_file(), reason="quality rerun records not present")
def test_committed_golden_and_summary_match_the_rerun(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load_script("build_cat3_golden_from_rerun", monkeypatch, tmp_path)
    records = mod.load_records(RUNS)
    keys = load_quality_keys()
    golden = mod.build_golden(records, source_file="experiments/cat3_quality/runs.jsonl", keys_version=keys["meta"]["keys_version"])
    committed = json.loads(mod.DEFAULT_OUT.read_text(encoding="utf-8"))
    assert mod._comparable(committed) == mod._comparable(golden)
    portfolio = mod.build_quality_portfolio(mod.summarise(records, keys=keys), source_file="experiments/cat3_quality/runs.jsonl")
    assert json.loads(mod.DEFAULT_SUMMARY_OUT.read_text(encoding="utf-8")) == json.loads(json.dumps(portfolio))


# ------------------------------------------------------------------------------- 2. live path


def test_live_path_records_real_compaction_stop_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_turn(**kw: Any) -> AnthropicRawResult:
        return AnthropicRawResult("claude-sonnet-5-5", 5, 100, 40, 0, 9000, "ok", {}, stop_reason="end_turn", thinking_tokens=12)

    async def fake_summ(**kw: Any) -> AnthropicRawResult:
        return AnthropicRawResult("claude-sonnet-5-5", 5, 500, 400, 0, 0, "{}", {"resolved_issues": []}, stop_reason="max_tokens")

    monkeypatch.setattr(runner, "run_cat3_service_desk_turn", fake_turn)
    monkeypatch.setattr(runner, "run_cat3_memory_summarizer", fake_summ)
    _, raw = asyncio.run(runner._run_live_cat3_session_for_rung(preset=PRESET, rung_id="prefix_cached_summarized", api_key="k"))
    comp = [t for t in raw if t["compaction_triggered_before_turn"]]
    assert [t["turn_number"] for t in comp] == [5, 8]  # MAX_VERBATIM_TURNS / KEEP_RECENT_TURNS unchanged
    assert {t["compaction_stop_reason"] for t in comp} == {"max_tokens"}
    assert {t["compaction_stop_reason"] for t in raw if not t["compaction_triggered_before_turn"]} == {None}
    assert all(t["thinking_tokens"] == 12 for t in raw)


# ---------------------------------------------------------------------------- 3. quality block


def test_live_quality_scores_turns_and_ledger_but_not_probes() -> None:
    texts = {t["turn_number"]: "nothing relevant" for t in PRESET["turns"]}
    q = runner.build_rung_quality(preset_id=PRESET["id"], turn_texts=texts, probe_phase=None, probes_unavailable_reason=runner.LIVE_PROBES_REASON)
    assert q is not None and q.probe_accuracy is None and q.probes is None
    assert q.probes_unavailable_reason == runner.LIVE_PROBES_REASON
    assert q.turn_recall.total > 0 and q.ledger_recall.total > 0
    assert set(q.ledger_by_origin) == {"1-3", "4-6", "7-9"}


def test_replay_quality_block_matches_golden_probe_phase() -> None:
    golden = runner.load_cat3_replays()["presets"][PRESET["id"]]
    for rid, phase in golden["probe_phase"].items():
        turns = golden["rungs"][rid]
        q = runner.build_rung_quality(
            preset_id=PRESET["id"],
            turn_texts={t["turn_number"]: t["assistant_message"] for t in turns},
            probe_phase=phase,
            probes_unavailable_reason=None,
        )
        assert q is not None and q.probes is not None and len(q.probes) == 6
        assert q.probe_accuracy is not None and q.probe_accuracy.hits == sum(p.hit for p in q.probes)
        assert all(p.expected and p.question for p in q.probes)
        assert all((p.outcome == "correct") == p.hit for p in q.probes)


@pytest.mark.parametrize(
    ("answer", "hit", "outcome"),
    [
        ("Your PRK is PRK-BLR-8841-992.", True, "correct"),
        ("I don't have that detail in our conversation.", False, "declined"),
        ("I can't give you that number from here.", False, "declined"),
        ("It was PRK-BLR-0000-000.", False, "wrong"),
    ],
)
def test_probe_answer_classification(answer: str, hit: bool, outcome: str) -> None:
    assert classify_probe_answer(answer, hit) == outcome


# -------------------------------------------------------------------------------- 4. portfolio


def test_portfolio_loads_and_falls_back_to_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pf = runner.load_cat3_quality_portfolio()
    assert pf is not None and pf.runs == 18 and {r.runs for r in pf.rungs} == {6}
    assert {r.rung_id for r in pf.rungs} == {"naive_full_history", "prefix_cached_history", "prefix_cached_summarized"}

    class _S:
        replays_dir = str(tmp_path)

    monkeypatch.setattr(runner, "get_settings", lambda: _S())
    assert runner.load_cat3_quality_portfolio() is None
    (tmp_path / "cat3_quality_summary.json").write_text("{not json")
    assert runner.load_cat3_quality_portfolio() is None
