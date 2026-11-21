"""Capture real live Claude 5.5 Category 4 traces into replays/cat4_golden_replays.json."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "NOVAMART_TRACES_DIR",
    str(Path(tempfile.gettempdir()) / "novamart_cat4_capture"),
)

from app.archetypes.cat4_rag.runner import _run_live_cat4_audit_for_rung  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.data.cat4_fixtures import CAT4_PRESETS, hydrate_deal_room_index  # noqa: E402
from app.models import Cat4RungId  # noqa: E402

RUNGS: list[Cat4RungId] = [
    "naive_full_corpus",
    "cached_full_corpus_citations",
    "hybrid_rag_rerank_citations",
]


def _validate_rung(
    rid: Cat4RungId,
    raw_queries: list[dict[str, Any]],
    expected_count: int,
) -> str | None:
    if len(raw_queries) != expected_count:
        return f"expected {expected_count} queries, got {len(raw_queries)}"
    for idx, q in enumerate(raw_queries):
        if q.get("stop_reason") != "end_turn":
            return f"Q{q.get('question_number')} stop_reason={q.get('stop_reason')}"
        if rid == "cached_full_corpus_citations":
            cw = int(q.get("cache_creation_tokens") or 0)
            cr = int(q.get("cache_read_tokens") or 0)
            if cw + cr < 14000:
                return f"Q{q.get('question_number')} below 14k prefix cache (cw={cw}, cr={cr})"
            if idx >= 1 and cr < 14000:
                return f"Q{q.get('question_number')} missed prefix cache read (cw={cw}, cr={cr})"
            if not q.get("citations"):
                return f"Q{q.get('question_number')} returned 0 native citations"
        if rid == "hybrid_rag_rerank_citations":
            if int(q.get("reranker_input_tokens") or 0) <= 0:
                return f"Q{q.get('question_number')} missing Haiku reranker usage"
            if not q.get("citations"):
                return f"Q{q.get('question_number')} returned 0 native citations"
    return None


async def capture_cat4() -> None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY must be set in .env before capturing Cat 4 replays."
        )

    hydrated_docs, flat_chunks, total_chars = hydrate_deal_room_index()
    out_path = settings.replays_dir / "cat4_golden_replays.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(out_path.read_text(encoding="utf-8")) if out_path.is_file() else {}
    captured: dict[str, Any] = {"presets": dict(existing.get("presets") or {})}

    for preset in CAT4_PRESETS:
        pid = preset["id"]
        expected_q = len(preset["questions"])
        existing_rungs: dict[str, Any] = dict(
            ((captured["presets"].get(pid) or {}).get("rungs")) or {}
        )

        missing_rungs = [
            rid
            for rid in RUNGS
            if _validate_rung(rid, existing_rungs.get(rid) or [], expected_q) is not None
        ]
        if not missing_rungs:
            print(f"[Cat 4] Reusing valid 4-query captures for {pid}...")
            continue

        print(
            f"[Cat 4] Capturing {missing_rungs} x {expected_q} queries concurrently for {pid}..."
        )

        async def _cap_rung(rid: Cat4RungId) -> tuple[Cat4RungId, Any, list[dict[str, Any]]]:
            summary, raw_queries = await _run_live_cat4_audit_for_rung(
                preset=preset,
                rung_id=rid,
                hydrated_docs=hydrated_docs,
                flat_chunks=flat_chunks,
                total_corpus_chars=total_chars,
                api_key=settings.anthropic_api_key,
            )
            return rid, summary, raw_queries

        rung_outputs = await asyncio.gather(*(_cap_rung(r) for r in missing_rungs))
        rungs_payload: dict[str, list[dict[str, Any]]] = dict(existing_rungs)
        errors: list[str] = []

        for rid, summary, raw_queries in rung_outputs:
            print(
                f"  [{pid}/{rid}] model={summary.model_id} | in={summary.total_uncached_input_tokens:,} "
                f"| cw={summary.total_cache_creation_tokens:,} | cr={summary.total_cache_read_tokens:,} "
                f"| out={summary.total_output_tokens:,} | rerank={summary.reranker_calls} (${summary.reranker_cost_usd:.5f}) "
                f"| cold=${summary.cold_audit_cost_usd:.5f} (${summary.cost_per_1k_audits_cold_usd:.2f}/1k) "
                f"| warm=${summary.warm_audit_cost_usd:.5f} (${summary.cost_per_1k_audits_warm_usd:.2f}/1k) "
                f"| avg_cites={summary.avg_citations_per_query} | recall={summary.avg_reranker_recall_pct}"
            )
            err = _validate_rung(rid, raw_queries, expected_q)
            if err:
                errors.append(f"{pid}/{rid}: {err}")
            else:
                rungs_payload[rid] = raw_queries

        if rungs_payload:
            captured["presets"][pid] = {
                "use_case": preset["use_case"],
                "rungs": rungs_payload,
            }
            out_path.write_text(json.dumps(captured, indent=2), encoding="utf-8")
            print(
                f"Checkpointed valid rungs {list(rungs_payload.keys())} for {pid} to {out_path}"
            )

        if errors:
            raise RuntimeError(" ; ".join(errors))

    print(f"Saved live Category 4 golden replays to {out_path}")


if __name__ == "__main__":
    asyncio.run(capture_cat4())
