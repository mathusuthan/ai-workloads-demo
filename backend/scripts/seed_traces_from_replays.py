"""Seed backend/traces/ from the 30 real live-captured traces in cat1_golden_replays.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat1_triage.accuracy import evaluate_rung_accuracy  # noqa: E402
from app.archetypes.cat1_triage.pii import scrub_pii_deterministic  # noqa: E402
from app.archetypes.cat1_triage.runner import (  # noqa: E402
    _build_rung_result,
    load_golden_replays,
    persist_cat1_trace,
)
from app.archetypes.cat2_drafting.runner import (  # noqa: E402
    CAT2_RUNG_TO_PATTERN,
    HITL_REGEN_PATTERN,
    build_cat2_rung_result,
    build_hitl_cost_comparison,
    build_section_regen_payload,
    load_cat2_replays,
    persist_cat2_trace,
)
from app.archetypes.cat3_assistants.prompts import (  # noqa: E402
    build_cat3_system_handbook,
    get_memory_summarizer_system_prompt,
)
from app.archetypes.cat3_assistants.runner import (  # noqa: E402
    CAT3_RUNG_TO_PATTERN,
    SUMMARIZER_PATTERN,
    load_cat3_replays,
    persist_cat3_trace,
)
from app.archetypes.cat3_assistants.schemas import SESSION_MEMORY_JSON_SCHEMA  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.core.pricing import compute_run_finops  # noqa: E402
from app.data.cat1_fixtures import CAT1_EXTRA_BATCH_ITEMS, CAT1_PRESETS  # noqa: E402
from app.data.cat2_fixtures import CAT2_PRESETS, CAT2_REVIEWER_PRESETS  # noqa: E402
from app.data.cat3_fixtures import CAT3_PRESETS  # noqa: E402


def _clear_prior_seeds(traces_dir: Path) -> int:
    removed = 0
    if not traces_dir.is_dir():
        return removed
    for json_file in list(traces_dir.rglob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if data.get("source_mode") == "live_captured_seed":
                json_file.unlink()
                removed += 1
        except Exception:
            continue
    index_file = traces_dir / "index.jsonl"
    if index_file.is_file():
        kept_lines = []
        for line in index_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                if json.loads(line).get("source_mode") != "live_captured_seed":
                    kept_lines.append(line)
            except Exception:
                continue
        index_file.write_text("\n".join(kept_lines) + ("\n" if kept_lines else ""), encoding="utf-8")
    return removed


def seed_all() -> None:
    settings = get_settings()
    removed = _clear_prior_seeds(settings.traces_dir)
    if removed:
        print(f"Cleared {removed} prior seed trace(s).")

    replays = load_golden_replays()
    preset_replays = replays.get("presets") or {}
    extra_replays = replays.get("batch_items") or {}

    written = 0

    for preset in CAT1_PRESETS:
        pid = preset["id"]
        sub_task = preset["sub_task"]
        payload = preset["payload"]
        pii = scrub_pii_deterministic(payload)
        rungs = preset_replays[pid]["rungs"]
        run_group = f"seed-{pid}"

        naive_cost = _build_rung_result(
            rung_id="sonnet_naive",
            model_id=rungs["sonnet_naive"]["model_id"],
            provider=rungs["sonnet_naive"]["provider"],
            latency_ms=int(rungs["sonnet_naive"]["latency_ms"]),
            input_tokens=int(rungs["sonnet_naive"]["input_tokens"]),
            output_tokens=int(rungs["sonnet_naive"]["output_tokens"]),
            structured_output=rungs["sonnet_naive"].get("structured_output") or {},
            raw_text_preview=rungs["sonnet_naive"].get("raw_text_preview"),
        ).finops.total_cost_usd

        for rung_id in ("sonnet_naive", "haiku_naive", "haiku_calibrated", "gemini_decision"):
            if rung_id not in rungs:
                continue
            r_data = rungs[rung_id]
            res = _build_rung_result(
                rung_id=rung_id,
                model_id=r_data["model_id"],
                provider=r_data["provider"],
                latency_ms=int(r_data["latency_ms"]),
                input_tokens=int(r_data["input_tokens"]),
                output_tokens=int(r_data["output_tokens"]),
                structured_output=r_data.get("structured_output") or {},
                raw_text_preview=r_data.get("raw_text_preview"),
                decision_probabilities=r_data.get("decision_probabilities"),
            )
            if naive_cost > 0:
                res.savings_vs_naive_pct = round(
                    ((naive_cost - res.finops.total_cost_usd) / naive_cost) * 100, 2
                )
            gt = dict(preset.get("ground_truth") or {})
            extra_meta: dict[str, object] = {
                "source_endpoint": "capture_live_replays.py",
                "savings_vs_naive_pct": res.savings_vs_naive_pct,
            }
            if gt:
                res.accuracy = evaluate_rung_accuracy(
                    rung_id=rung_id,
                    sub_task=sub_task,
                    ground_truth=gt,
                    structured_output=res.structured_output,
                    raw_text=res.raw_text_preview,
                )
                extra_meta["accuracy"] = res.accuracy.model_dump()
            persist_cat1_trace(
                source_mode="live_captured_seed",
                run_group_id=run_group,
                item_id=pid,
                item_title=preset["title"],
                sub_task=sub_task,
                payload_text=payload,
                rung_res=res,
                pii_result=pii,
                extra_metadata=extra_meta,
            )
            written += 1

    for item in CAT1_EXTRA_BATCH_ITEMS:
        iid = item["id"]
        sub_task = item["sub_task"]
        payload = item["payload"]
        pii = scrub_pii_deterministic(payload)
        b = extra_replays[iid]
        run_group = f"seed-{iid}"
        gt = dict(item.get("ground_truth") or {})

        s_raw = b.get("sonnet_raw_text") or ""
        hn_raw = b.get("haiku_naive_raw_text") or ""
        s_res = _build_rung_result(
            rung_id="sonnet_naive",
            model_id="claude-sonnet-5-5",
            provider="Anthropic",
            latency_ms=int(b.get("sonnet_latency_ms", 4200)),
            input_tokens=int(b.get("sonnet_input_tokens", b["input_tokens"])),
            output_tokens=int(b.get("sonnet_output_tokens", 285)),
            structured_output={"mode": "unstructured_chat_prose", "char_length": len(s_raw)},
            raw_text_preview=s_raw,
        )
        hn_res = _build_rung_result(
            rung_id="haiku_naive",
            model_id="claude-haiku-5-5",
            provider="Anthropic",
            latency_ms=int(b.get("haiku_naive_latency_ms", 2600)),
            input_tokens=int(b.get("haiku_naive_input_tokens", b["input_tokens"])),
            output_tokens=int(b.get("haiku_naive_output_tokens", 285)),
            structured_output={"mode": "unstructured_chat_prose", "char_length": len(hn_raw)},
            raw_text_preview=hn_raw,
        )
        h_res = _build_rung_result(
            rung_id="haiku_calibrated",
            model_id="claude-haiku-5-5",
            provider="Anthropic",
            latency_ms=int(b["haiku_latency_ms"]),
            input_tokens=int(b["input_tokens"]),
            output_tokens=int(b["haiku_output_tokens"]),
            structured_output=b["haiku_decision"],
            raw_text_preview=json.dumps(b["haiku_decision"]),
        )
        g_res = _build_rung_result(
            rung_id="gemini_decision",
            model_id="gemini-decision-1",
            provider="Google Gemini Decisions API",
            latency_ms=int(b["gemini_latency_ms"]),
            input_tokens=int(b.get("gemini_input_tokens", b["input_tokens"])),
            output_tokens=0,
            structured_output=b["gemini_decision"],
            decision_probabilities=None,
        )

        for rung_res in (s_res, hn_res, h_res, g_res):
            extra_meta_b: dict[str, object] = {"source_endpoint": "capture_live_replays.py"}
            if gt:
                rung_res.accuracy = evaluate_rung_accuracy(
                    rung_id=rung_res.rung_id,
                    sub_task=sub_task,
                    ground_truth=gt,
                    structured_output=rung_res.structured_output,
                    raw_text=rung_res.raw_text_preview,
                )
                extra_meta_b["accuracy"] = rung_res.accuracy.model_dump()
            persist_cat1_trace(
                source_mode="live_captured_seed",
                run_group_id=run_group,
                item_id=iid,
                item_title=item["title"],
                sub_task=sub_task,
                payload_text=payload,
                rung_res=rung_res,
                pii_result=pii,
                extra_metadata=extra_meta_b,
            )
            written += 1

    # Seed Category 2 traces from cat2_golden_replays.json
    cat2_replays = load_cat2_replays()
    cat2_presets_replays = cat2_replays.get("presets") or {}
    cat2_regen_replays = cat2_replays.get("section_regens") or {}

    for preset in CAT2_PRESETS:
        pid = preset["id"]
        if pid not in cat2_presets_replays:
            continue
        sub_task = preset["sub_task"]
        payload = preset["payload"]
        rungs = cat2_presets_replays[pid]["rungs"]
        run_group = f"seed-cat2-{pid}"

        unbounded_res = build_cat2_rung_result(
            rung_id="sonnet_unbounded",
            model_id=rungs["sonnet_unbounded"]["model_id"],
            provider=rungs["sonnet_unbounded"]["provider"],
            latency_ms=int(rungs["sonnet_unbounded"]["latency_ms"]),
            input_tokens=int(rungs["sonnet_unbounded"]["input_tokens"]),
            output_tokens=int(rungs["sonnet_unbounded"]["output_tokens"]),
            structured_draft=rungs["sonnet_unbounded"].get("structured_draft") or {},
            raw_markdown=rungs["sonnet_unbounded"].get("raw_markdown"),
            thinking_tokens=int(rungs["sonnet_unbounded"].get("thinking_tokens") or 0),
        )
        unbounded_cost = unbounded_res.finops.total_cost_usd

        for rung_id in ("sonnet_unbounded", "sonnet_templated", "haiku_templated"):
            if rung_id not in rungs:
                continue
            r_data = rungs[rung_id]
            res = build_cat2_rung_result(
                rung_id=rung_id,
                model_id=r_data["model_id"],
                provider=r_data["provider"],
                latency_ms=int(r_data["latency_ms"]),
                input_tokens=int(r_data["input_tokens"]),
                output_tokens=int(r_data["output_tokens"]),
                structured_draft=r_data.get("structured_draft") or {},
                raw_markdown=r_data.get("raw_markdown"),
                thinking_tokens=int(r_data.get("thinking_tokens") or 0),
            )
            if unbounded_cost > 0:
                res.savings_vs_unbounded_pct = round(
                    ((unbounded_cost - res.finops.total_cost_usd) / unbounded_cost) * 100, 2
                )
            persist_cat2_trace(
                source_mode="live_captured_seed",
                run_group_id=run_group,
                item_id=pid,
                item_title=preset["title"],
                sub_task=sub_task,
                model_id=res.model_id,
                pattern=CAT2_RUNG_TO_PATTERN[rung_id],
                payload_text=payload,
                status="ok",
                latency_ms=res.latency_ms,
                finops_dict=res.finops.model_dump(),
                raw_text=res.raw_markdown,
                structured_output=res.structured_draft,
                stop_reason=r_data.get("stop_reason") or "end_turn",
                thinking_tokens=res.thinking_tokens,
                extra_metadata={
                    "source_endpoint": "capture_cat2_replays.py",
                    "savings_vs_unbounded_pct": res.savings_vs_unbounded_pct,
                },
            )
            written += 1

        # Seed surgical HITL section regenerations for this preset
        for sec, tiers_map in (cat2_regen_replays.get(pid) or {}).items():
            instruction = (CAT2_REVIEWER_PRESETS.get(sec) or {}).get("instruction", "")
            for tier, r_data in tiers_map.items():
                comp = build_hitl_cost_comparison(
                    model_id=r_data["model_id"],
                    surgical_in_tokens=int(r_data["input_tokens"]),
                    surgical_out_tokens=int(r_data["output_tokens"]),
                    section_key=sec,
                )
                req_payload = build_section_regen_payload(
                    source_text=payload,
                    section_key=sec,
                    current_section=r_data.get("prior_section") or {},
                    reviewer_instruction=instruction,
                )
                persist_cat2_trace(
                    source_mode="live_captured_seed",
                    run_group_id=f"seed-cat2-regen-{pid}-{sec}",
                    item_id=f"{pid}__{sec}",
                    item_title=f"{preset['title']} · Section `{sec}`",
                    sub_task=sub_task,
                    model_id=r_data["model_id"],
                    pattern=HITL_REGEN_PATTERN,
                    payload_text=req_payload,
                    status="ok",
                    latency_ms=int(r_data["latency_ms"]),
                    finops_dict=comp.surgical_finops.model_dump(),
                    raw_text=json.dumps({sec: r_data["updated_section"]}, indent=2),
                    structured_output={sec: r_data["updated_section"]},
                    section_key=sec,
                    stop_reason=r_data.get("stop_reason") or "end_turn",
                    extra_metadata={
                        "source_endpoint": "capture_cat2_replays.py",
                        "section_key": sec,
                        "reviewer_instruction": instruction,
                        "revision_savings_pct": comp.revision_savings_pct,
                    },
                )
                written += 1

    # Seed Category 3 traces (60 multi-turn assistant turns + 4 sliding-window summarizer calls)
    cat3_replays = load_cat3_replays()
    cat3_presets_replays = cat3_replays.get("presets") or {}
    for preset in CAT3_PRESETS:
        pid = preset["id"]
        if pid not in cat3_presets_replays:
            continue
        rungs_map = cat3_presets_replays[pid].get("rungs") or {}
        for rung_id in ("naive_full_history", "prefix_cached_history", "prefix_cached_summarized"):
            raw_turns = rungs_map.get(rung_id) or []
            sys_inst = build_cat3_system_handbook(rung_id, preset["employee_profile"])
            run_group = f"seed-cat3-{pid}-{rung_id}"
            for rt in raw_turns:
                t_num = int(rt["turn_number"])
                model_id = str(rt.get("model_id") or "claude-sonnet-5-5")
                if rt.get("compaction_triggered_before_turn") and rt.get("compaction_payload"):
                    comp_fin = compute_run_finops(
                        model_id=str(rt.get("compaction_model_id") or model_id),
                        input_tokens=int(rt.get("compaction_input_tokens") or 0),
                        output_tokens=int(rt.get("compaction_output_tokens") or 0),
                    )
                    mem_snap = rt.get("memory_summary_snapshot") or {}
                    persist_cat3_trace(
                        source_mode="live_captured_seed",
                        run_group_id=run_group,
                        item_id=f"{pid}__t{t_num:02d}_compact",
                        item_title=f"{preset['title']} · Compaction Before Turn {t_num}",
                        model_id=str(rt.get("compaction_model_id") or model_id),
                        pattern=SUMMARIZER_PATTERN,
                        system_instruction=get_memory_summarizer_system_prompt(),
                        payload_text=str(rt["compaction_payload"]),
                        status="ok",
                        latency_ms=int(rt.get("compaction_latency_ms") or 0),
                        finops_dict=comp_fin.model_dump(),
                        raw_text=json.dumps(mem_snap, indent=2),
                        structured_output=mem_snap,
                        request_params={
                            "max_tokens": 1600,
                            "endpoint": "messages.create",
                            "thinking": {"type": "between_tools"},
                            "output_config": {"format": {"type": "json_schema"}},
                        },
                        json_schema=SESSION_MEMORY_JSON_SCHEMA,
                        stop_reason=rt.get("compaction_stop_reason") or "end_turn",
                        extra_metadata={
                            "source_endpoint": "capture_cat3_replays.py",
                            "turn_number": t_num,
                        },
                    )
                    written += 1

                t_fin = compute_run_finops(
                    model_id=model_id,
                    input_tokens=int(rt["input_tokens"]),
                    output_tokens=int(rt["output_tokens"]),
                    cache_creation_tokens=int(rt.get("cache_creation_tokens") or 0),
                    cache_read_tokens=int(rt.get("cache_read_tokens") or 0),
                )
                persist_cat3_trace(
                    source_mode="live_captured_seed",
                    run_group_id=run_group,
                    item_id=f"{pid}__t{t_num:02d}",
                    item_title=f"{preset['title']} · Turn {t_num} ({rt['topic_tag']})",
                    model_id=model_id,
                    pattern=CAT3_RUNG_TO_PATTERN[rung_id],
                    system_instruction=sys_inst,
                    payload_text=str(rt["user_message"]),
                    status="ok",
                    latency_ms=int(rt["latency_ms"]),
                    finops_dict=t_fin.model_dump(),
                    raw_text=str(rt["assistant_message"]),
                    structured_output={
                        "turn_number": t_num,
                        "topic_tag": rt["topic_tag"],
                        "active_history_turns": rt["active_history_turns"],
                        "compacted_turns_count": rt["compacted_turns_count"],
                    },
                    request_params={
                        "max_tokens": 4096,
                        "endpoint": "messages.create",
                        "thinking": {"type": "between_tools"},
                        "prefix_cache_enabled": rung_id != "naive_full_history",
                    },
                    stop_reason=rt.get("stop_reason") or "end_turn",
                    extra_metadata={
                        "source_endpoint": "capture_cat3_replays.py",
                        "turn_number": t_num,
                        "rung_id": rung_id,
                    },
                )
                written += 1

    print(f"Seeded {written} partitioned trace files into {settings.traces_dir}")


if __name__ == "__main__":
    seed_all()
