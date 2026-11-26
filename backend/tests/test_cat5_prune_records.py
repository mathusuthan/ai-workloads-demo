"""prune_cat5_records.py on temporary copies: keep / move / delete, byte-identical kept lines, idempotent. No API calls."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType

import pytest

from app.archetypes.cat5_orchestration import ablation as ab

BACKEND = Path(__file__).resolve().parent.parent
EXP = BACKEND / "experiments" / "cat5_ablation"
HAVE = (EXP / "runs.jsonl").is_file() and (EXP / "other_levers" / "runs.jsonl").is_file()
pytestmark = pytest.mark.skipif(not HAVE, reason="experiment records not present")


def _mod() -> ModuleType:
    spec = importlib.util.spec_from_file_location("prune_cat5_records", BACKEND / "scripts" / "prune_cat5_records.py")
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _lines(p: Path) -> list[str]:
    return [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _copy(tmp: Path) -> Path:
    d = tmp / "cat5_ablation"
    (d / "other_levers").mkdir(parents=True)
    for rel in ("runs.jsonl", "tool_results.jsonl", "other_levers/runs.jsonl", "other_levers/tool_results.jsonl"):
        shutil.copyfile(EXP / rel, d / rel)
    return d


def _current_lines(lines: list[str]) -> list[str]:
    """Lines of the main file the prune keeps: the latest current record per key, in file order."""
    latest = {}
    for ln in lines:
        r = json.loads(ln)
        if r["arm_id"] in ab.ARM_IDS and ab.record_is_current(r):
            latest[ab.record_key(r)] = ln
    keep = set(latest.values())
    return [ln for ln in lines if ln in keep]


def test_prune_of_the_committed_files_keeps_exactly_the_current_runs_and_is_idempotent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    d = _copy(tmp_path)
    main_lines = _lines(d / "runs.jsonl")
    other_before = (d / "other_levers" / "runs.jsonl").read_bytes()
    m = _mod()
    assert m.main(["--dir", str(d)]) == 0
    capsys.readouterr()
    assert _lines(d / "runs.jsonl") == _current_lines(main_lines)  # stale runs (if any are still there) go, kept lines byte-identical
    assert (d / "other_levers" / "runs.jsonl").read_bytes() == other_before  # other levers are kept as recorded
    after = {p: p.read_bytes() for p in d.rglob("*.jsonl")}
    assert m.main(["--dir", str(d)]) == 0
    assert "Nothing to change." in capsys.readouterr().out
    assert {p: p.read_bytes() for p in d.rglob("*.jsonl")} == after


def test_prune_keeps_moves_deletes_and_is_idempotent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    d = _copy(tmp_path)
    all_main, other_lines = _lines(d / "runs.jsonl"), _lines(d / "other_levers" / "runs.jsonl")
    main_lines = _current_lines(all_main)
    n_stale = len(all_main) - len(main_lines)
    main_ids = [json.loads(x)["run_id"] for x in main_lines]
    other_ids = [json.loads(x)["run_id"] for x in other_lines]
    # a dirty main file: the other levers' runs back in it, plus an error record, a stale-settings record and an older
    # record of a kept key, all of which must go
    first = json.loads(main_lines[0])
    err = {**first, "run_id": "err-1", "status": "error"}
    stale = json.loads(main_lines[1])
    stale["run_id"], stale["settings"] = "stale-1", {**stale["settings"], "max_tokens_per_turn": 2048}
    older = {**first, "run_id": "older-1"}
    dirty = [json.dumps(older), *other_lines, json.dumps(err), *all_main, json.dumps(stale)]
    (d / "runs.jsonl").write_text("\n".join(dirty) + "\n", encoding="utf-8")
    shutil.copyfile(EXP / "other_levers" / "tool_results.jsonl", tmp_path / "o_blobs")
    (d / "tool_results.jsonl").write_text((EXP / "tool_results.jsonl").read_text() + (tmp_path / "o_blobs").read_text())
    (d / "other_levers" / "runs.jsonl").unlink()
    (d / "other_levers" / "tool_results.jsonl").unlink()

    m = _mod()
    snapshot = {p: p.read_bytes() for p in d.rglob("*.jsonl")}
    assert m.main(["--dir", str(d), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert f"keep {len(main_ids)}, move {len(other_ids)} to other_levers/, delete {3 + n_stale}" in out and "Dry run: nothing written." in out
    assert {p: p.read_bytes() for p in d.rglob("*.jsonl")} == snapshot

    assert m.main(["--dir", str(d)]) == 0
    capsys.readouterr()
    assert _lines(d / "runs.jsonl") == main_lines  # byte-identical, same order
    assert sorted(_lines(d / "other_levers" / "runs.jsonl")) == sorted(other_lines)
    kept = ab.load_jsonl(d / "runs.jsonl")
    refs = {c["result_sha256"] for r in kept for t in r["turns"] for c in t.get("tool_calls") or [] if c.get("result_sha256")}
    blobs = {json.loads(x)["sha256"] for x in _lines(d / "tool_results.jsonl")}
    assert blobs <= refs  # only referenced tool results stay

    after = {p: p.read_bytes() for p in d.rglob("*.jsonl")}
    assert m.main(["--dir", str(d)]) == 0
    assert "Nothing to change." in capsys.readouterr().out
    assert {p: p.read_bytes() for p in d.rglob("*.jsonl")} == after
