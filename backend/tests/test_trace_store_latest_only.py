"""Trace store: replay requests write nothing by default; backups are never read as traces."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.trace_store import (  # noqa: E402
    RECORD_REPLAY_ENV,
    TracePartition,
    TraceRecord,
    TraceRequestEnvelope,
    TraceResponseEnvelope,
    load_all_traces,
    record_trace,
    summarize_traces,
)
from app.main import app  # noqa: E402


def _record(mode: str) -> TraceRecord:
    return TraceRecord(
        source_mode=mode,  # type: ignore[arg-type]
        partition=TracePartition(category="c", use_case="u", model="m", pattern="p"),
        request=TraceRequestEnvelope(provider="Anthropic", endpoint="messages.create", input_payload="x"),
        response=TraceResponseEnvelope(latency_ms=1),
    )


def _files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.json")] if root.exists() else []


def test_replay_is_not_written_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(RECORD_REPLAY_ENV, raising=False)
    path = record_trace(_record("replay"), traces_dir=tmp_path)
    assert not path.exists() and _files(tmp_path) == [] and not (tmp_path / "index.jsonl").exists()
    for mode in ("live", "live_captured_seed"):
        assert record_trace(_record(mode), traces_dir=tmp_path).is_file()
    assert len(_files(tmp_path)) == 2
    assert len((tmp_path / "index.jsonl").read_text().splitlines()) == 2


def test_replay_is_written_when_opted_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RECORD_REPLAY_ENV, "1")
    assert record_trace(_record("replay"), traces_dir=tmp_path).is_file()


@pytest.mark.parametrize(("path", "body"), [
    ("/api/cat3/run", {"preset_id": "desk-01", "mode": "replay"}),
    ("/api/cat4/run", {"preset_id": "audit-01", "mode": "replay"}),
])
def test_replay_requests_leave_the_store_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str, body: dict) -> None:
    monkeypatch.delenv(RECORD_REPLAY_ENV, raising=False)
    monkeypatch.setenv("NOVAMART_TRACES_DIR", str(tmp_path))
    r = TestClient(app).post(path, json=body)
    assert r.status_code == 200 and r.json()["mode_used"] == "replay"
    assert _files(tmp_path) == []


def test_backups_are_not_read_as_traces(tmp_path: Path) -> None:
    rec = _record("live")
    record_trace(rec, traces_dir=tmp_path)
    stray = tmp_path / "_backups" / "category=c" / "x.json"
    stray.parent.mkdir(parents=True)
    stray.write_text(json.dumps(rec.model_dump()), encoding="utf-8")
    assert len(load_all_traces(tmp_path)) == 1
    assert summarize_traces(tmp_path)["total_traces"] == 1
