"""Partitioned LLM & Decision trace capture store (category / use_case / model / pattern)."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4
from pydantic import BaseModel, Field

from app.config import get_settings


def _sanitize_segment(value: str) -> str:
    """Keep partition directory names clean, safe, and filesystem-friendly."""
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip())
    return cleaned.strip("_.") or "unknown"


class TracePartition(BaseModel):
    category: str
    use_case: str
    model: str
    pattern: str


class TraceRequestEnvelope(BaseModel):
    provider: str
    endpoint: str
    system_instruction: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    json_schema: dict[str, Any] | None = None
    decision_questions: dict[str, Any] | None = None
    input_payload: str


class TraceResponseEnvelope(BaseModel):
    status: Literal["ok", "error"] = "ok"
    error_message: str | None = None
    stop_reason: str | None = None
    latency_ms: int
    raw_text: str | None = None
    structured_output: dict[str, Any] = Field(default_factory=dict)
    decision_probabilities: dict[str, Any] | None = None
    pii_redaction: dict[str, Any] | None = None


class TraceRecord(BaseModel):
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    run_group_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp_utc: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    source_mode: Literal["live", "replay", "live_captured_seed"] = "live"
    item_id: str = "custom"
    item_title: str = "Custom Payload"
    partition: TracePartition
    request: TraceRequestEnvelope
    response: TraceResponseEnvelope
    finops: dict[str, Any] = Field(default_factory=dict)
    extra_metadata: dict[str, Any] = Field(default_factory=dict)


def partition_directory(traces_dir: Path, partition: TracePartition) -> Path:
    return (
        traces_dir
        / f"category={_sanitize_segment(partition.category)}"
        / f"use_case={_sanitize_segment(partition.use_case)}"
        / f"model={_sanitize_segment(partition.model)}"
        / f"pattern={_sanitize_segment(partition.pattern)}"
    )


def record_trace(record: TraceRecord, traces_dir: Path | None = None) -> Path:
    """Persist one trace JSON file into category/use_case/model/pattern partition + index.jsonl."""
    root = traces_dir or get_settings().traces_dir
    part_dir = partition_directory(root, record.partition)
    part_dir.mkdir(parents=True, exist_ok=True)

    compact_ts = re.sub(r"[^0-9TZ]", "", record.timestamp_utc)
    safe_item = _sanitize_segment(record.item_id)
    filename = f"{compact_ts}_{safe_item}_{record.trace_id[:8]}.json"
    file_path = part_dir / filename

    payload = record.model_dump()
    payload["partition_relative_path"] = str(file_path.relative_to(root))
    file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Append lightweight index entry for quick programmatic lookup
    index_path = root / "index.jsonl"
    summary_entry = {
        "trace_id": record.trace_id,
        "run_group_id": record.run_group_id,
        "timestamp_utc": record.timestamp_utc,
        "source_mode": record.source_mode,
        "item_id": record.item_id,
        "category": record.partition.category,
        "use_case": record.partition.use_case,
        "model": record.partition.model,
        "pattern": record.partition.pattern,
        "status": record.response.status,
        "latency_ms": record.response.latency_ms,
        "input_tokens": record.finops.get("input_tokens", 0),
        "output_tokens": record.finops.get("output_tokens", 0),
        "cost_per_1k_usd": record.finops.get("cost_per_1k_usd", 0.0),
        "relative_path": payload["partition_relative_path"],
    }
    with index_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary_entry) + "\n")

    return file_path


def load_all_traces(traces_dir: Path | None = None) -> list[dict[str, Any]]:
    """Scan all partitioned trace JSON files on disk, sorted newest-first."""
    root = traces_dir or get_settings().traces_dir
    if not root.is_dir():
        return []

    records: list[dict[str, Any]] = []
    for json_file in root.rglob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "partition" in data and "request" in data:
                data.setdefault("partition_relative_path", str(json_file.relative_to(root)))
                data["file_path"] = str(json_file)
                records.append(data)
        except Exception:
            continue

    records.sort(key=lambda r: (r.get("timestamp_utc", ""), r.get("trace_id", "")), reverse=True)
    return records


def summarize_traces(traces_dir: Path | None = None) -> dict[str, Any]:
    """Return trace count and rollup grouped by (category, use_case, model, pattern)."""
    root = traces_dir or get_settings().traces_dir
    records = load_all_traces(root)

    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "live_count": 0,
            "replay_count": 0,
            "seed_count": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_per_1k_usd": 0.0,
        }
    )

    for rec in records:
        p = rec.get("partition") or {}
        key = (
            str(p.get("category", "unknown")),
            str(p.get("use_case", "unknown")),
            str(p.get("model", "unknown")),
            str(p.get("pattern", "unknown")),
        )
        bucket = grouped[key]
        bucket["count"] += 1
        src = rec.get("source_mode")
        if src == "live":
            bucket["live_count"] += 1
        elif src == "live_captured_seed":
            bucket["seed_count"] += 1
        else:
            bucket["replay_count"] += 1

        fin = rec.get("finops") or {}
        bucket["total_input_tokens"] += int(fin.get("input_tokens") or 0)
        bucket["total_output_tokens"] += int(fin.get("output_tokens") or 0)
        bucket["total_cost_per_1k_usd"] += float(fin.get("cost_per_1k_usd") or 0.0)

    partitions_list: list[dict[str, Any]] = []
    for (cat, uc, mod, pat), stats in sorted(grouped.items()):
        cnt = max(1, stats["count"])
        partitions_list.append(
            {
                "category": cat,
                "use_case": uc,
                "model": mod,
                "pattern": pat,
                "count": stats["count"],
                "live_count": stats["live_count"],
                "seed_count": stats["seed_count"],
                "replay_count": stats["replay_count"],
                "avg_input_tokens": round(stats["total_input_tokens"] / cnt),
                "avg_output_tokens": round(stats["total_output_tokens"] / cnt),
                "avg_cost_per_1k_usd": round(stats["total_cost_per_1k_usd"] / cnt, 4),
            }
        )

    return {
        "traces_dir": str(root),
        "total_traces": len(records),
        "partitions": partitions_list,
    }
