"""Seed backend/traces/ from the golden replays.

Default: clears every prior `live_captured_seed` trace (all categories) and re-seeds Categories 1-6 from the current
golden replays, so the store holds one seed trace per recorded call. Replay requests in the app do not write traces
(`app.core.trace_store.record_trace`); live requests do.
`--cat1-only` / `--cat3-only` / `--cat4-only` / `--cat5-only` / `--cat6-only`: appends that category's seeds only, without
deleting or rewriting any other trace (run the default afterwards to drop that category's older seeds).
`backend/traces/_backups/` is never read or changed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat1_triage.pii import scrub_pii_deterministic  # noqa: E402
from app.archetypes.cat1_triage.runner import (  # noqa: E402
    RUNG_ORDER,
    load_cat1_ablation_portfolio,
    load_golden_replays,
    persist_cat1_trace,
    rung_result_from_replay,
    score_rung,
)
from app.archetypes.cat2_drafting.runner import (  # noqa: E402
    RUNG_ORDER as CAT2_RUNG_ORDER,
    WITHOUT_FOR as CAT2_WITHOUT_FOR,
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
from app.archetypes.cat3_assistants.scoring import (  # noqa: E402
    cached_quality_keys,
    classify_probe_answer,
    fact_hit,
    probes_for,
)
from app.archetypes.cat4_rag.answer_formats import rung_answer_format as cat4_rung_answer_format  # noqa: E402
from app.archetypes.cat4_rag.answer_formats import rung_synthesis_system_prompt as cat4_rung_synthesis_system_prompt  # noqa: E402
from app.archetypes.cat4_rag.paired import PAIRED_RUNG as CAT4_PAIRED_RUNG  # noqa: E402
from app.archetypes.cat4_rag.paired import get_full_corpus_reranker_system_prompt  # noqa: E402
from app.archetypes.cat4_rag.runner import (  # noqa: E402
    CAT4_RERANK_MAX_TOKENS,
    CAT4_RUNG_TO_PATTERN,
    CAT4_SYNTH_MAX_TOKENS,
    RERANKER_PATTERN as CAT4_RERANKER_PATTERN,
    load_cat4_replays,
    persist_cat4_trace,
)
from app.archetypes.cat4_rag.schemas import RERANK_JSON_SCHEMA  # noqa: E402
from app.archetypes.cat5_orchestration.prompts import (  # noqa: E402
    build_cat5_user_task_prompt,
    get_cat5_system_prompt,
)
from app.archetypes.cat5_orchestration.runner import (  # noqa: E402
    CAT5_BUDGETS,
    CAT5_MAX_TOKENS,
    CAT5_RUNG_TO_PATTERN,
    _build_cat5_result_from_replay,
    load_cat5_replays,
    persist_cat5_trace,
)
from app.archetypes.cat6_swarms.caps import CALL_TIMEOUT_S, cat6_caps_by_role  # noqa: E402
from app.archetypes.cat6_swarms.prompts import (  # noqa: E402
    get_cat6_agent_system_prompt,
)
from app.archetypes.cat6_swarms.runner import (  # noqa: E402
    CAT6_RUNG_IDS,
    CAT6_RUNG_TO_PATTERN,
    CAT6_SHARED_BUS_RUNGS,
    _build_cat6_result_from_replay,
    cat6_trace_model_id,
    load_cat6_replays,
    persist_cat6_trace,
)
from app.config import get_settings  # noqa: E402
from app.core.pricing import compute_run_finops, rollup_multi_call_finops  # noqa: E402
from app.data.cat1_fixtures import CAT1_EXTRA_BATCH_ITEMS, CAT1_PRESETS  # noqa: E402
from app.data.cat2_fixtures import CAT2_PRESETS, CAT2_REVIEWER_PRESETS  # noqa: E402
from app.data.cat3_fixtures import CAT3_PRESETS  # noqa: E402
from app.data.cat4_fixtures import CAT4_PRESETS  # noqa: E402
from app.data.cat5_fixtures import CAT5_PRESETS  # noqa: E402
from app.data.cat6_fixtures import CAT6_PRESETS  # noqa: E402


def _clear_prior_seeds(traces_dir: Path) -> int:
    removed = 0
    if not traces_dir.is_dir():
        return removed
    for json_file in list(traces_dir.rglob("*.json")):
        if "_backups" in json_file.relative_to(traces_dir).parts:
            continue
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


def seed_cat1() -> int:
    """Seed Category 1 traces (one per item x rung) from cat1_golden_replays.json; appends only.

    The golden replays are repeat 0 of the four-cell experiment (scripts/build_cat1_golden_from_ablation.py): the
    traces carry the real stop reason, thinking tokens, the cap the run used, the experiment provenance and, for
    write-ups, the reader model's accuracy."""
    replays = load_golden_replays()
    portfolio = load_cat1_ablation_portfolio()
    preset_replays = replays.get("presets") or {}
    extra_replays = replays.get("batch_items") or {}
    written = 0
    for item in list(CAT1_PRESETS) + list(CAT1_EXTRA_BATCH_ITEMS):
        iid, sub_task, payload = item["id"], item["sub_task"], item["payload"]
        src = preset_replays.get(iid) or extra_replays.get(iid)
        if not src:
            continue
        stored = src["rungs"]
        prov = src.get("provenance") or {}
        pii = scrub_pii_deterministic(payload)
        run_group = f"seed-cat1-ablation-{iid}"
        gt = dict(item.get("ground_truth") or {})
        naive_cost = rung_result_from_replay("sonnet_naive", stored["sonnet_naive"]).finops.total_cost_usd
        for rung_id in RUNG_ORDER:
            if rung_id not in stored:
                continue
            r_data = stored[rung_id]
            res = rung_result_from_replay(rung_id, r_data)
            if naive_cost > 0:
                res.savings_vs_naive_pct = round(((naive_cost - res.finops.total_cost_usd) / naive_cost) * 100, 2)
            meta: dict[str, object] = {"source_endpoint": "build_cat1_golden_from_ablation.py", "savings_vs_naive_pct": res.savings_vs_naive_pct}
            if gt:
                score_rung(res, sub_task, gt, reader_extraction=r_data.get("reader_extraction"), portfolio=portfolio)
                if res.accuracy is not None:
                    meta["accuracy"] = res.accuracy.model_dump()
                if res.accuracy_note:
                    meta["accuracy_note"] = res.accuracy_note
            p = prov.get(rung_id) or {}
            meta.update({"ablation_arm_id": p.get("arm_id"), "ablation_run_id": p.get("run_id"), "repeat_index": p.get("repeat_index"),
                         "max_tokens": r_data.get("max_tokens"), "truncated": r_data.get("truncated")})
            persist_cat1_trace(
                source_mode="live_captured_seed",
                run_group_id=run_group,
                item_id=iid,
                item_title=item["title"],
                sub_task=sub_task,
                payload_text=payload,
                rung_res=res,
                pii_result=pii,
                request_params_override=r_data.get("request_params"),
                stop_reason=r_data.get("stop_reason"),
                thinking_tokens=int(r_data.get("thinking_tokens") or 0),
                extra_metadata=meta,
            )
            written += 1
    return written


def seed_all() -> None:
    settings = get_settings()
    removed = _clear_prior_seeds(settings.traces_dir)
    if removed:
        print(f"Cleared {removed} prior seed trace(s).")

    written = 0

    written += seed_cat1()

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

        prov = cat2_presets_replays[pid].get("provenance") or {}
        built = {}
        for rung_id in CAT2_RUNG_ORDER:  # rungs whose experiment drafts do not exist yet are absent and not seeded
            if rung_id not in rungs:
                continue
            r_data = rungs[rung_id]
            built[rung_id] = (r_data, build_cat2_rung_result(
                rung_id=rung_id,
                model_id=r_data["model_id"],
                provider=r_data["provider"],
                latency_ms=int(r_data["latency_ms"]),
                input_tokens=int(r_data["input_tokens"]),
                output_tokens=int(r_data["output_tokens"]),
                structured_draft=r_data.get("structured_draft") or {},
                raw_markdown=r_data.get("raw_markdown"),
                thinking_tokens=int(r_data.get("thinking_tokens") or 0),
            ))
        for rung_id, (r_data, res) in built.items():
            without = built.get(CAT2_WITHOUT_FOR.get(rung_id, ""))
            base = without[1].finops.total_cost_usd if without else 0.0
            if base > 0:
                res.savings_vs_unbounded_pct = round(((base - res.finops.total_cost_usd) / base) * 100, 2)
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
                request_params_override=r_data.get("request_params"),
                stop_reason=r_data.get("stop_reason"),
                thinking_tokens=res.thinking_tokens,
                extra_metadata={
                    "source_endpoint": "build_cat2_golden_from_experiment.py",
                    "rung_id": rung_id,
                    "experiment_draft_id": (prov.get(rung_id) or {}).get("draft_id"),
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
                    preset_id=pid,
                    replays=cat2_replays,
                )
                req_payload = r_data.get("request_payload") or build_section_regen_payload(
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
                    raw_text=r_data.get("raw_text") or json.dumps({sec: r_data["updated_section"]}, indent=2),
                    structured_output={sec: r_data["updated_section"]},
                    section_key=sec,
                    request_params_override=r_data.get("request_params"),
                    stop_reason=r_data.get("stop_reason"),
                    thinking_tokens=int(r_data.get("thinking_tokens") or 0),
                    extra_metadata={
                        "source_endpoint": "cat2_golden_replays.json section_regens",
                        "section_key": sec,
                        "reviewer_instruction": instruction,
                        "revision_savings_pct": comp.revision_savings_pct,
                        "regen_key": (r_data.get("provenance") or {}).get("regen_key"),
                        "base_draft_id": (r_data.get("provenance") or {}).get("base_draft_id"),
                    },
                )
                written += 1

    written += seed_cat3()

    written += seed_cat4()

    written += seed_cat5()

    written += seed_cat6()

    print(f"Seeded {written} partitioned trace files into {settings.traces_dir}")


def _cat3_compaction_trace(
    *,
    preset: dict,
    run_group: str,
    item_id: str,
    item_title: str,
    comp: dict,
    memory: dict,
    extra: dict,
) -> None:
    model_id = str(comp.get("model_id") or "claude-sonnet-5-5")
    fin = compute_run_finops(
        model_id=model_id,
        input_tokens=int(comp.get("input_tokens") or 0),
        output_tokens=int(comp.get("output_tokens") or 0),
        cache_creation_tokens=int(comp.get("cache_creation_tokens") or 0),
        cache_read_tokens=int(comp.get("cache_read_tokens") or 0),
    )
    persist_cat3_trace(
        source_mode="live_captured_seed",
        run_group_id=run_group,
        item_id=item_id,
        item_title=item_title,
        model_id=model_id,
        pattern=SUMMARIZER_PATTERN,
        system_instruction=get_memory_summarizer_system_prompt(),
        payload_text=str(comp["payload"]),
        status="ok",
        latency_ms=int(comp.get("latency_ms") or 0),
        finops_dict=fin.model_dump(),
        raw_text=json.dumps(memory, indent=2),
        structured_output=memory,
        request_params={
            "max_tokens": 1600,
            "endpoint": "messages.create",
            "thinking": {"type": "between_tools"},
            "output_config": {"format": {"type": "json_schema"}},
        },
        json_schema=SESSION_MEMORY_JSON_SCHEMA,
        stop_reason=comp.get("stop_reason"),
        extra_metadata={**extra, "thinking_tokens": int(comp.get("thinking_tokens") or 0)},
    )


def seed_cat3() -> int:
    """Seed Category 3 traces from cat3_golden_replays.json; appends only.

    Per rung and session: 10 turns, the summariser calls before turns 5 and 8 (compacted rung), and — when the
    golden replays come from the quality rerun (scripts/build_cat3_golden_from_rerun.py) — the probe-phase
    compaction and the six recall probes, each scored with the answer key. Both versions are seeded: without and
    with the improvement.
    """
    written = 0
    cat3_replays = load_cat3_replays()
    file_prov = cat3_replays.get("provenance") or {}
    from_rerun = bool(file_prov)
    source_endpoint = "build_cat3_golden_from_rerun.py" if from_rerun else "capture_cat3_replays.py"
    keys = cached_quality_keys()
    cat3_presets_replays = cat3_replays.get("presets") or {}
    for preset in CAT3_PRESETS:
        pid = preset["id"]
        if pid not in cat3_presets_replays:
            continue
        preset_trace = cat3_presets_replays[pid]
        rungs_map = preset_trace.get("rungs") or {}
        for rung_id in ("naive_full_history", "prefix_cached_summarized"):
            raw_turns = rungs_map.get(rung_id) or []
            if not raw_turns:
                continue
            sys_inst = build_cat3_system_handbook(rung_id, preset["employee_profile"])
            run_group = f"seed-cat3-rerun-{pid}-{rung_id}" if from_rerun else f"seed-cat3-{pid}-{rung_id}"
            prov = (preset_trace.get("provenance") or {}).get(rung_id)
            base_meta = {
                "source_endpoint": source_endpoint,
                "rung_id": rung_id,
                "provenance": prov,
                "golden_rebuilt_at": file_prov.get("rebuilt_at"),
            }
            for rt in raw_turns:
                t_num = int(rt["turn_number"])
                model_id = str(rt.get("model_id") or "claude-sonnet-5-5")
                if rt.get("compaction_triggered_before_turn") and rt.get("compaction_payload"):
                    _cat3_compaction_trace(
                        preset=preset,
                        run_group=run_group,
                        item_id=f"{pid}__t{t_num:02d}_compact",
                        item_title=f"{preset['title']} · Compaction Before Turn {t_num}",
                        comp={
                            "model_id": rt.get("compaction_model_id") or model_id,
                            "payload": rt["compaction_payload"],
                            "latency_ms": rt.get("compaction_latency_ms"),
                            "input_tokens": rt.get("compaction_input_tokens"),
                            "output_tokens": rt.get("compaction_output_tokens"),
                            "thinking_tokens": rt.get("compaction_thinking_tokens"),
                            "cache_creation_tokens": rt.get("compaction_cache_creation_tokens"),
                            "cache_read_tokens": rt.get("compaction_cache_read_tokens"),
                            "stop_reason": rt.get("compaction_stop_reason"),
                        },
                        memory=rt.get("memory_summary_snapshot") or {},
                        extra={**base_meta, "turn_number": t_num},
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
                    stop_reason=rt.get("stop_reason"),
                    extra_metadata={
                        **base_meta,
                        "turn_number": t_num,
                        "thinking_tokens": int(rt.get("thinking_tokens") or 0),
                    },
                )
                written += 1

            phase = (preset_trace.get("probe_phase") or {}).get(rung_id)
            if not phase:
                continue
            if phase.get("compaction"):
                pc = phase["compaction"]
                _cat3_compaction_trace(
                    preset=preset,
                    run_group=run_group,
                    item_id=f"{pid}__probe_compact",
                    item_title=f"{preset['title']} · Compaction Before Recall Probes",
                    comp=pc,
                    memory=pc.get("memory_after") or {},
                    extra={
                        **base_meta,
                        "phase": "recall_probes",
                        "evicted_turns": pc.get("evicted_turns"),
                        "kept_turns": pc.get("kept_turns"),
                    },
                )
                written += 1
            key_by_id = {k["probe_id"]: k for k in probes_for(keys, pid)}
            for pr in phase.get("probes") or []:
                key = key_by_id.get(pr["probe_id"])
                hit = fact_hit(str(pr.get("answer") or ""), key["any_of"]) if key else None
                model_id = str(pr.get("model_id") or "claude-sonnet-5-5")
                p_fin = compute_run_finops(
                    model_id=model_id,
                    input_tokens=int(pr.get("input_tokens") or 0),
                    output_tokens=int(pr.get("output_tokens") or 0),
                    cache_creation_tokens=int(pr.get("cache_creation_tokens") or 0),
                    cache_read_tokens=int(pr.get("cache_read_tokens") or 0),
                )
                persist_cat3_trace(
                    source_mode="live_captured_seed",
                    run_group_id=run_group,
                    item_id=f"{pid}__probe_t{int(pr['origin_turn']):02d}",
                    item_title=f"{preset['title']} · Recall Probe (detail from Turn {pr['origin_turn']})",
                    model_id=model_id,
                    pattern=CAT3_RUNG_TO_PATTERN[rung_id],
                    system_instruction=sys_inst,
                    payload_text=str(pr["question"]),
                    status="ok",
                    latency_ms=int(pr.get("latency_ms") or 0),
                    finops_dict=p_fin.model_dump(),
                    raw_text=str(pr.get("answer") or ""),
                    structured_output={
                        "probe_id": pr["probe_id"],
                        "origin_turn": int(pr["origin_turn"]),
                        "expected": (key or {}).get("expected_display"),
                        "hit": hit,
                        "outcome": classify_probe_answer(str(pr.get("answer") or ""), bool(hit)) if key else None,
                        "keys_version": (keys.get("meta") or {}).get("keys_version"),
                        "active_history_turns": pr.get("active_history_turns"),
                        "compacted_through_turn": pr.get("compacted_through_turn"),
                    },
                    request_params={
                        "max_tokens": 4096,
                        "endpoint": "messages.create",
                        "thinking": {"type": "between_tools"},
                        "prefix_cache_enabled": rung_id != "naive_full_history",
                    },
                    stop_reason=pr.get("stop_reason"),
                    extra_metadata={
                        **base_meta,
                        "phase": "recall_probes",
                        "thinking_tokens": int(pr.get("thinking_tokens") or 0),
                    },
                )
                written += 1
    return written


def seed_cat4() -> int:
    """Seed Category 4 traces from cat4_golden_replays.json; appends only.

    Both versions are seeded: without the improvement (full corpus, no cache) and with it (Haiku clause pick from
    the cached corpus + Sonnet answer with citations). When the golden replays come from the quality rerun
    (scripts/build_cat4_golden_from_rerun.py) the traces carry the real stop reasons, the question as the model
    received it and the rerun provenance."""
    written = 0
    cat4_replays = load_cat4_replays()
    file_prov = cat4_replays.get("provenance") or {}
    from_rerun = file_prov.get("source") == "cat4 quality rerun"
    source_endpoint = "build_cat4_golden_from_rerun.py" if from_rerun else "capture_cat4_replays.py"
    cat4_presets_replays = cat4_replays.get("presets") or {}
    for preset in CAT4_PRESETS:
        pid = preset["id"]
        if pid not in cat4_presets_replays:
            continue
        rungs_map = cat4_presets_replays[pid].get("rungs") or {}
        rung_prov = cat4_presets_replays[pid].get("provenance") or {}
        for rung_id in ("naive_full_corpus", CAT4_PAIRED_RUNG):
            raw_queries = rungs_map.get(rung_id) or []
            # the rung's synthesis prompt (answer_formats.RUNG_ANSWER_FORMAT)
            fmt = cat4_rung_answer_format(rung_id)
            sys_inst = cat4_rung_synthesis_system_prompt(rung_id, with_citations=(rung_id != "naive_full_corpus"))
            run_group = f"seed-cat4-rerun-{pid}-{rung_id}" if from_rerun else f"seed-cat4-{pid}-{rung_id}"
            prov = rung_prov.get(rung_id) or {}
            for rq in raw_queries:
                qid = str(rq["question_id"])
                qnum = int(rq["question_number"])
                model_id = str(rq.get("model_id") or "claude-sonnet-5-5")
                asked = str(rq.get("question_as_asked") or rq["question"])
                meta = {"source_endpoint": source_endpoint, "question_id": qid, "answer_format": fmt}
                if from_rerun:
                    meta.update({"rerun_run_id": prov.get("run_id"), "repeat_index": prov.get("repeat_index"),
                                 "scale": prov.get("scale"), "session_q_index": rq.get("session_q_index")})
                if rq.get("reranker_model_id"):
                    rerank_fin = compute_run_finops(
                        model_id=str(rq.get("reranker_model_id") or "claude-haiku-5-5"),
                        input_tokens=int(rq.get("reranker_input_tokens") or 0),
                        output_tokens=int(rq.get("reranker_output_tokens") or 0),
                        cache_creation_tokens=int(rq.get("reranker_cache_creation_tokens") or 0),
                        cache_read_tokens=int(rq.get("reranker_cache_read_tokens") or 0),
                    )
                    rerank_struct = rq.get("reranker_structured") or {}
                    persist_cat4_trace(
                        source_mode="live_captured_seed",
                        run_group_id=run_group,
                        item_id=f"{pid}__{qid}_rerank",
                        item_title=f"{preset['title']} · Haiku Clause Pick Q{qnum}",
                        model_id=str(rq.get("reranker_model_id") or "claude-haiku-5-5"),
                        pattern=CAT4_RERANKER_PATTERN,
                        system_instruction=get_full_corpus_reranker_system_prompt(),
                        payload_text=str(rq.get("reranker_payload") or asked),
                        status="ok",
                        latency_ms=int(rq.get("reranker_latency_ms") or 0),
                        finops_dict=rerank_fin.model_dump(),
                        raw_text=json.dumps(rerank_struct, indent=2),
                        structured_output=rerank_struct,
                        request_params={
                            "max_tokens": CAT4_RERANK_MAX_TOKENS,
                            "endpoint": "messages.create",
                            "thinking": {"type": "disabled"},
                            "output_config": {"format": {"type": "json_schema"}},
                            "cached_clause_block": True,
                        },
                        json_schema=RERANK_JSON_SCHEMA,
                        stop_reason=rq.get("reranker_stop_reason") if from_rerun else "end_turn",
                        extra_metadata=dict(meta),
                    )
                    written += 1

                q_fin = compute_run_finops(
                    model_id=model_id,
                    input_tokens=int(rq["input_tokens"]),
                    output_tokens=int(rq["output_tokens"]),
                    cache_creation_tokens=int(rq.get("cache_creation_tokens") or 0),
                    cache_read_tokens=int(rq.get("cache_read_tokens") or 0),
                )
                judgement = rq.get("judgement") or None
                persist_cat4_trace(
                    source_mode="live_captured_seed",
                    run_group_id=run_group,
                    item_id=f"{pid}__{qid}",
                    item_title=f"{preset['title']} · Q{qnum} ({rq['topic_tag']})",
                    model_id=model_id,
                    pattern=CAT4_RUNG_TO_PATTERN[rung_id],
                    system_instruction=sys_inst,
                    payload_text=asked,
                    status="ok",
                    latency_ms=int(rq["latency_ms"]),
                    finops_dict=q_fin.model_dump(),
                    raw_text=str(rq["answer_markdown"]),
                    structured_output={
                        "question_id": qid,
                        "topic_tag": rq["topic_tag"],
                        "citations_count": len(rq.get("citations") or []),
                        "citations": rq.get("citations") or [],
                        "context_reduction_pct": rq.get("context_reduction_pct", 0.0),
                        "reranker_recall_pct": rq.get("reranker_recall_pct"),
                        "grader": (
                            {
                                "correctness": judgement["correctness"]["score"],
                                "completeness": judgement["completeness"]["score"],
                                "material_errors": sum(1 for e in judgement["factual_errors"] if e["severity"] == "material"),
                            }
                            if judgement
                            else None
                        ),
                    },
                    request_params={
                        "max_tokens": int(rq.get("max_tokens") or CAT4_SYNTH_MAX_TOKENS),
                        "endpoint": "messages.create",
                        "thinking": {"type": "between_tools"},
                        "prefix_cache_enabled": False,
                        "native_document_citations": rung_id != "naive_full_corpus",
                    },
                    stop_reason=rq.get("stop_reason") if from_rerun else (rq.get("stop_reason") or "end_turn"),
                    extra_metadata={**meta, "rung_id": rung_id},
                )
                written += 1
    return written


def _cat5_system_text(rung_id: str, prov: dict) -> str:
    """The system text the recorded run actually received: the ablation's (nonce line + base) when it matches the
    recorded sha256, else today's rung prompt."""
    from app.archetypes.cat5_orchestration.ablation import _sha, system_text_for

    arm_id, nonce, want = prov.get("arm_id"), prov.get("run_nonce"), prov.get("system_text_sha256")
    if arm_id and want:
        text = system_text_for(str(arm_id), nonce)
        if _sha(text) == want:
            return text
    return get_cat5_system_prompt(rung_id)


def seed_cat5() -> int:
    """Seed Category 5 traces (one orchestration rollup per invoice x rung) from cat5_golden_replays.json; appends only.

    When the golden replays come from the ablation (scripts/build_cat5_golden_from_ablation.py) the traces carry the
    real stop reason of the last turn, the per-turn max_tokens, the system text the run received and the ablation
    provenance; older Category 5 seeds stay on disk and are superseded by these (newest seed per
    category/model/pattern/item)."""
    from app.archetypes.cat5_orchestration.ablation import ABLATION_GOLDEN_SOURCE

    written = 0
    cat5_replays = load_cat5_replays()
    from_ablation = (cat5_replays.get("provenance") or {}).get("source") == ABLATION_GOLDEN_SOURCE
    source_endpoint = "build_cat5_golden_from_ablation.py" if from_ablation else "capture_cat5_replays.py"
    cat5_presets_replays = cat5_replays.get("presets") or {}
    for preset in CAT5_PRESETS:
        pid = preset["id"]
        if pid not in cat5_presets_replays:
            continue
        rungs_map = cat5_presets_replays[pid].get("rungs") or {}
        rung_prov = cat5_presets_replays[pid].get("provenance") or {}
        run_group = f"seed-cat5-ablation-{pid}" if from_ablation else f"seed-cat5-{pid}"
        for rung_id in (
            "unbounded_sonnet_loop",
            "bounded_sonnet_cached_gate",
            "hybrid_haiku_sonnet_governed",
            "unbounded_haiku_loop",  # seeded once its runs are recorded (absent from the golden file until then)
        ):
            if rung_id not in rungs_map:
                continue
            raw_rung = rungs_map[rung_id]
            prov = rung_prov.get(rung_id) or {}
            res = _build_cat5_result_from_replay(
                rung_id=rung_id,
                preset=preset,
                raw_rung=raw_rung,
            )
            fin_model = (
                "claude-haiku-5-5"
                if (rung_id == "hybrid_haiku_sonnet_governed" and not res.escalated_to_sonnet)
                or rung_id == "unbounded_haiku_loop"
                else "claude-sonnet-5-5"
            )
            rollup_fin = rollup_multi_call_finops(
                calls=[s.finops for s in res.steps],
                total_cost_usd=res.cold_run_cost_usd,
                model_id=fin_model,
                model_label=res.primary_model_id,
            ).model_dump()
            steps = raw_rung.get("steps") or []
            last_stop = (steps[-1].get("stop_reason") if steps else None) if from_ablation else "end_turn"
            request_params = {
                "endpoint": "messages.create",
                "max_step_budget": CAT5_BUDGETS[rung_id],
                "prefix_cache_enabled": rung_id not in ("unbounded_sonnet_loop", "unbounded_haiku_loop"),
            }
            meta = {"source_endpoint": source_endpoint, "rung_id": rung_id}
            if from_ablation:
                request_params["max_tokens"] = max((int(st.get("max_tokens") or 0) for st in steps), default=CAT5_MAX_TOKENS)
                meta.update({
                    "ablation_arm_id": prov.get("arm_id"),
                    "ablation_run_id": prov.get("run_id"),
                    "repeat_index": prov.get("repeat_index"),
                    "turn_stop_reasons": [st.get("stop_reason") for st in steps],
                })
            persist_cat5_trace(
                source_mode="live_captured_seed",
                run_group_id=run_group,
                item_id=pid,
                item_title=preset["title"],
                model_id=fin_model,
                pattern=CAT5_RUNG_TO_PATTERN[rung_id],
                system_instruction=_cat5_system_text(rung_id, prov) if from_ablation else get_cat5_system_prompt(rung_id),
                payload_text=build_cat5_user_task_prompt(preset),
                status="ok",
                latency_ms=res.total_latency_ms,
                finops_dict=rollup_fin,
                raw_text=res.final_readout,
                structured_output={
                    "steps_used": res.steps_used,
                    "haiku_steps": res.haiku_steps,
                    "sonnet_steps": res.sonnet_steps,
                    "escalated_to_sonnet": res.escalated_to_sonnet,
                    "committed_voucher": res.committed_voucher.model_dump()
                    if res.committed_voucher
                    else None,
                    "evaluation": res.evaluation.model_dump() if res.evaluation else None,
                },
                request_params=request_params,
                stop_reason=last_stop,
                extra_metadata=meta,
            )
            written += 1
    return written


def seed_cat6() -> int:
    """Seed Category 6 traces (one swarm rollup per incident x rung in cat6_golden_replays.json: 12 with all
    four rungs recorded, 9 while rung 4 is pending).

    Appends only; never deletes or rewrites other traces. The golden replays are rebuilt from the fair
    rerun (scripts/build_cat6_golden_from_rerun.py), so these seeds supersede older Category 6 seeds.
    """
    written = 0
    cat6_replays = load_cat6_replays()
    file_prov = cat6_replays.get("provenance") or {}
    cat6_presets_replays = cat6_replays.get("presets") or {}
    for preset in CAT6_PRESETS:
        pid = preset["id"]
        if pid not in cat6_presets_replays:
            continue
        rungs_map = cat6_presets_replays[pid].get("rungs") or {}
        run_group = f"seed-cat6-fair-rerun-{pid}" if file_prov else f"seed-cat6-{pid}"
        for rung_id in CAT6_RUNG_IDS:
            if rung_id not in rungs_map:
                continue
            raw_rung = rungs_map[rung_id]
            res = _build_cat6_result_from_replay(
                rung_id=rung_id,
                preset=preset,
                raw_rung=raw_rung,
            )
            fin_model = cat6_trace_model_id(res)
            rollup_fin = rollup_multi_call_finops(
                calls=[t.finops for t in res.agent_turns],
                total_cost_usd=res.cold_run_cost_usd,
                model_id=fin_model,
                model_label=res.primary_model_id,
            ).model_dump()
            stop_reasons = [t.get("stop_reason") for t in raw_rung.get("agent_turns") or []]
            persist_cat6_trace(
                source_mode="live_captured_seed",
                run_group_id=run_group,
                item_id=pid,
                item_title=preset["title"],
                model_id=fin_model,
                pattern=CAT6_RUNG_TO_PATTERN[rung_id],
                system_instruction=get_cat6_agent_system_prompt(rung_id, "patch_author"),
                payload_text=f"{preset['pr_id']} ({preset['target_file']})\n{preset['ci_failure_log']}",
                status="ok",
                latency_ms=res.total_latency_ms,
                finops_dict=rollup_fin,
                raw_text=res.final_signoff_memo or res.patched_code,
                structured_output={
                    "haiku_turns": res.haiku_turns,
                    "sonnet_turns": res.sonnet_turns,
                    "retries_used": res.retries_used,
                    "turn_stop_reasons": stop_reasons,
                    "sandbox_report": res.sandbox_report.model_dump()
                    if res.sandbox_report
                    else None,
                },
                request_params={
                    "endpoint": "messages.create",
                    "prefix_cache_enabled": rung_id not in CAT6_SHARED_BUS_RUNGS,
                    "max_tokens_by_role": cat6_caps_by_role(),
                    "timeout_s": CALL_TIMEOUT_S,
                },
                stop_reason="max_tokens" if "max_tokens" in stop_reasons else "end_turn",
                extra_metadata={
                    "source_endpoint": (
                        "build_cat6_golden_from_rerun.py" if file_prov else "capture_cat6_replays.py"
                    ),
                    "rung_id": rung_id,
                    "provenance": raw_rung.get("provenance"),
                    "golden_rebuilt_at": file_prov.get("rebuilt_at"),
                },
            )
            written += 1
    return written


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--cat1-only",
        action="store_true",
        help="append Category 1 seed traces only; no other trace is deleted or rewritten",
    )
    ap.add_argument(
        "--cat6-only",
        action="store_true",
        help="append Category 6 seed traces only; no other trace is deleted or rewritten",
    )
    ap.add_argument(
        "--cat3-only",
        action="store_true",
        help="append Category 3 seed traces only; no other trace is deleted or rewritten",
    )
    ap.add_argument(
        "--cat5-only",
        action="store_true",
        help="append Category 5 seed traces only; no other trace is deleted or rewritten",
    )
    ap.add_argument(
        "--cat4-only",
        action="store_true",
        help="append Category 4 seed traces only; no other trace is deleted or rewritten",
    )
    args = ap.parse_args(argv)
    if sum(map(bool, (args.cat1_only, args.cat3_only, args.cat4_only, args.cat5_only, args.cat6_only))) > 1:
        ap.error("--cat1-only, --cat3-only, --cat4-only, --cat5-only and --cat6-only are mutually exclusive")
    if args.cat1_only:
        n = seed_cat1()
        print(f"Seeded {n} Category 1 trace files into {get_settings().traces_dir} (append-only)")
        return
    if args.cat5_only:
        n = seed_cat5()
        print(f"Seeded {n} Category 5 trace files into {get_settings().traces_dir} (append-only)")
        return
    if args.cat4_only:
        n = seed_cat4()
        print(f"Seeded {n} Category 4 trace files into {get_settings().traces_dir} (append-only)")
        return
    if args.cat3_only:
        n = seed_cat3()
        print(f"Seeded {n} Category 3 trace files into {get_settings().traces_dir} (append-only)")
        return
    if args.cat6_only:
        n = seed_cat6()
        print(f"Seeded {n} Category 6 trace files into {get_settings().traces_dir} (append-only)")
        return
    seed_all()


if __name__ == "__main__":
    main()
