"""`scripts/prune_cat6_records.py`: other designs move out of the main file, records carry the current sandbox's
verdicts, and the script is idempotent."""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat6_swarms.sandbox_verifier import evaluate_patch_in_sandbox  # noqa: E402

RUNS_JSONL = BACKEND_DIR / "experiments" / "cat6_fair_rerun" / "runs.jsonl"
OTHER_JSONL = BACKEND_DIR / "experiments" / "cat6_fair_rerun" / "other_designs" / "runs.jsonl"
SHOWN_ARMS = {"shared_bus_matched_gate", "isolated_cached_gate", "tiered_gate"}


def _load():
    spec = importlib.util.spec_from_file_location("prune_cat6_records", BACKEND_DIR / "scripts" / "prune_cat6_records.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sbx(passed: int, ms: int = 30) -> dict[str, Any]:
    checks = [
        {"check_id": f"C{i}", "name": f"c{i}", "category": "ast", "passed": i < passed, "detail": "ok" if i < passed else "bad"}
        for i in range(10)
    ]
    return {"total_checks": 10, "passed_checks": passed, "verified_outcome": passed == 10, "execution_ms": ms, "checks": checks}


def _record(run_id: str, code: str, passed: int, arm_id: str = "shared_bus_matched_gate") -> dict[str, Any]:
    return {
        "run_id": run_id,
        "arm_id": arm_id,
        "preset_id": "inc-02",
        "repeat_index": 0,
        "status": "ok",
        "turns": [{"agent_role": "patch_author", "raw_text": "naïve ✓"}],
        "first_attempt": {"patch_extracted": True, "patch_author_stop_reason": "end_turn", "sandbox": _sbx(passed, 11)},
        "final": {"patch_extracted": True, "patch_author_stop_reason": "end_turn", "sandbox": _sbx(passed, 12)},
        "patched_code_first": code,
        "patched_code_final": code,
    }


def _fake_sandbox(calls: list[tuple[str, str]]):
    def fake(preset_id: str, code: str) -> dict[str, Any]:
        calls.append((preset_id, code))
        return _sbx(10, ms=999)  # every patch passes; a different wall-clock time on every call

    return fake


def test_prune_replaces_only_differing_reports_and_keeps_everything_else() -> None:
    mod = _load()
    flagged, fine = _record("a", "FLAGGED", 9), _record("b", "FINE", 10)
    snapshot = copy.deepcopy([flagged, fine])
    calls: list[tuple[str, str]] = []
    fake = _fake_sandbox(calls)

    new_flagged, changes = mod.prune_record(flagged, fake)
    new_fine, no_changes = mod.prune_record(fine, fake)

    assert [flagged, fine] == snapshot  # inputs never mutated
    assert no_changes == [] and new_fine == fine
    assert [c["attempt"] for c in changes] == ["first_attempt", "final"]
    assert changes[0]["flipped_checks"] == ["C9"]
    for key, ms in (("first_attempt", 11), ("final", 12)):
        rep = new_flagged[key]["sandbox"]
        assert rep["passed_checks"] == 10 and rep["verified_outcome"] is True
        assert rep["execution_ms"] == ms  # recorded wall-clock time kept
        assert new_flagged[key]["patch_extracted"] is True
    assert {k: v for k, v in new_flagged.items() if k not in ("first_attempt", "final")} == {
        k: v for k, v in flagged.items() if k not in ("first_attempt", "final")
    }


def test_prune_file_is_idempotent_and_dry_run_writes_nothing(tmp_path: Path) -> None:
    mod = _load()
    path = tmp_path / "runs.jsonl"
    lines = [json.dumps(_record("a", "FLAGGED", 9), ensure_ascii=False), json.dumps(_record("b", "FINE", 10), ensure_ascii=False)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    original = path.read_text(encoding="utf-8")
    calls: list[tuple[str, str]] = []
    fake = _fake_sandbox(calls)

    assert len(mod.prune_file(path, dry_run=True, sandbox=fake)) == 2
    assert path.read_text(encoding="utf-8") == original

    assert len(mod.prune_file(path, sandbox=fake)) == 2
    once = path.read_text(encoding="utf-8")
    assert once.splitlines()[1] == lines[1]  # unchanged record keeps its exact line
    assert once.endswith("\n") and "naïve ✓" in once

    assert mod.prune_file(path, sandbox=fake) == []
    assert path.read_text(encoding="utf-8") == once


def test_move_other_designs_is_deterministic_and_idempotent(tmp_path: Path) -> None:
    mod = _load()
    main, other = tmp_path / "runs.jsonl", tmp_path / "other_designs" / "runs.jsonl"
    recs = [_record("a", "X", 10), _record("b", "Y", 10, "shared_bus_original"), _record("c", "Z", 10, "tiered_gate"),
            _record("d", "W", 10, "shared_bus_original")]
    lines = [json.dumps(r, ensure_ascii=False) for r in recs]
    main.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert [m["run_id"] for m in mod.move_other_designs(main, other, dry_run=True)] == ["b", "d"]
    assert not other.exists() and main.read_text(encoding="utf-8").count("\n") == 4

    assert [m["run_id"] for m in mod.move_other_designs(main, other)] == ["b", "d"]
    assert main.read_text(encoding="utf-8").splitlines() == [lines[0], lines[2]]  # order and bytes kept
    assert other.read_text(encoding="utf-8").splitlines() == [lines[1], lines[3]]
    snap = (main.read_bytes(), other.read_bytes())
    assert mod.move_other_designs(main, other) == []
    assert (main.read_bytes(), other.read_bytes()) == snap

    # a record already in `other` (e.g. an interrupted earlier move) is not duplicated
    main.write_text(lines[1] + "\n" + lines[0] + "\n", encoding="utf-8")
    assert [m["run_id"] for m in mod.move_other_designs(main, other)] == ["b"]
    assert other.read_text(encoding="utf-8").splitlines() == [lines[1], lines[3]]
    assert main.read_text(encoding="utf-8").splitlines() == [lines[0]]


@pytest.mark.skipif(not RUNS_JSONL.is_file(), reason="fair-rerun records not present")
def test_real_records_already_pruned_on_a_temp_copy(tmp_path: Path) -> None:
    mod = _load()
    main, other = tmp_path / "runs.jsonl", tmp_path / "other_designs" / "runs.jsonl"
    shutil.copyfile(RUNS_JSONL, main)
    if OTHER_JSONL.is_file():
        other.parent.mkdir(parents=True)
        shutil.copyfile(OTHER_JSONL, other)
    before = (main.read_bytes(), other.read_bytes() if other.is_file() else b"")
    assert mod.move_other_designs(main, other) == []  # nothing left to move
    assert mod.prune_file(main) == [] and mod.prune_file(other) == []  # current sandbox's verdicts already stored
    assert (main.read_bytes(), other.read_bytes() if other.is_file() else b"") == before


@pytest.mark.skipif(not RUNS_JSONL.is_file(), reason="fair-rerun records not present")
def test_main_file_holds_exactly_the_displayed_cells() -> None:
    recs = [json.loads(x) for x in RUNS_JSONL.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(recs) == 45 and {r["arm_id"] for r in recs} == SHOWN_ARMS
    if OTHER_JSONL.is_file():
        others = [json.loads(x) for x in OTHER_JSONL.read_text(encoding="utf-8").splitlines() if x.strip()]
        assert {r["arm_id"] for r in others}.isdisjoint(SHOWN_ARMS)
        assert {r["run_id"] for r in others}.isdisjoint({r["run_id"] for r in recs})


@pytest.mark.skipif(not RUNS_JSONL.is_file(), reason="fair-rerun records not present")
def test_golden_replays_match_their_records() -> None:
    golden = json.loads((BACKEND_DIR / "replays" / "cat6_golden_replays.json").read_text(encoding="utf-8"))
    by_id = {r["run_id"]: r for r in map(json.loads, filter(str.strip, RUNS_JSONL.read_text(encoding="utf-8").splitlines()))}
    for preset in golden["presets"].values():
        for rung in preset["rungs"].values():
            rec = by_id[rung["provenance"]["run_id"]]
            assert rung["sandbox_report"] == rec["final"]["sandbox"]
            assert rung["sandbox_report"]["verified_outcome"] == evaluate_patch_in_sandbox(rec["preset_id"], rec["patched_code_final"])["verified_outcome"]
