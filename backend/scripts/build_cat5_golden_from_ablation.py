"""Rebuild replays/cat5_golden_replays.json and replays/cat5_ablation_summary.json from the Category 5 ablation.

Golden replays — fixed, pre-declared mapping (never chosen by outcome): repeat_index 0 of the three ablation arms
that match the app's runnable rungs, on the three original invoices (inv-01..03):

    raw_free_sonnet             -> unbounded_sonnet_loop         (free-choice raw-table loop, no cache, no gate)
    bundle_gate_sonnet_cached   -> bounded_sonnet_cached_gate
    bundle_gate_haiku_escalate  -> hybrid_haiku_sonnet_governed

Each rung keeps the schema `runner._build_cat5_result_from_replay` reads, with real stop reasons, thinking tokens
and provenance. SQL text, tables touched, optimal-call flags and gate snapshots are rebuilt by replaying the
recorded tool calls, in order, on a fresh ERP session of the same kind; every replayed tool output must hash to
the recorded `result_sha256` and the replayed voucher must equal the recorded one, or the build fails.

Summary — the six arms pooled (11 gate-agreed invoices x 3 repeats), by tier and by invoice, the lever table,
tool use, the baseline comparison, the inv-06 gate-disagreement section and data quality, from the same
`ablation.summarise()` path as scripts/analyze_cat5_ablation.py. The original scripted naive captures (the old
7-step `unbounded_sonnet_loop` prompt) are kept verbatim in the summary as `original_scripted_captures` — shown
as a baseline, not runnable. They are read from the golden file while it still holds them, afterwards from the
existing summary, so the build is idempotent.

Inputs are only read. A file whose content is unchanged (ignoring `provenance.rebuilt_at`) is not rewritten.

Usage (from backend/):
    .venv/bin/python scripts/build_cat5_golden_from_ablation.py [--in runs.jsonl]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat5_orchestration.ablation import (  # noqa: E402
    ABLATION_GOLDEN_SOURCE,
    APP_RUNG_FOR_ARM,
    ARMS,
    GOLDEN_REPEAT_INDEX,
    AblationErpSession,
    _sha,
    build_ablation_portfolio,
    latest_ok_current,
    load_jsonl,
    original_scripted_golden,
)
from app.data.cat5_ablation_fixtures import CAT5_ABLATION_PRESETS_BY_ID  # noqa: E402

DEFAULT_IN = BACKEND_DIR / "experiments" / "cat5_ablation" / "runs.jsonl"
DEFAULT_OUT = BACKEND_DIR / "replays" / "cat5_golden_replays.json"
DEFAULT_SUMMARY_OUT = BACKEND_DIR / "replays" / "cat5_ablation_summary.json"
ORIGINAL_INVOICES = ("inv-01", "inv-02", "inv-03")
USE_CASE = "invoice_3way_reconciliation"
RESULT_PREVIEW_CHARS = 2200  # as runner._run_live_cat5_for_rung
PRIMARY_MODEL = {
    "unbounded_sonnet_loop": "claude-sonnet-5-5",
    "bounded_sonnet_cached_gate": "claude-sonnet-5-5",
    "hybrid_haiku_sonnet_governed": "claude-haiku-5-5 -> claude-sonnet-5-5 (conditional)",
}


class ReplayMismatch(ValueError):
    pass


def select_record(records: list[dict[str, Any]], arm_id: str, preset_id: str) -> dict[str, Any]:
    """Latest ok record at the current settings for (arm, invoice, repeat 0) — the analysis' rule."""
    rec = latest_ok_current(records).get((arm_id, preset_id, GOLDEN_REPEAT_INDEX))
    if rec is None:
        raise ValueError(f"no current ok record for {arm_id} / {preset_id} / r{GOLDEN_REPEAT_INDEX}")
    return rec


def convert_record(record: dict[str, Any]) -> dict[str, Any]:
    """One ablation run -> one golden rung, with tool traces rebuilt by deterministic replay."""
    arm = ARMS[record["arm_id"]]
    rung_id = APP_RUNG_FOR_ARM[record["arm_id"]]
    session = AblationErpSession(rung_id=arm.session_rung_id)
    steps: list[dict[str, Any]] = []
    circuit = False
    try:
        for t in record["turns"]:
            traces = []
            for c in t.get("tool_calls") or []:
                if c.get("executed"):
                    out, sql, touched, is_opt, gate = session.execute_tool(c["name"], dict(c.get("input") or {}))
                else:
                    session.total_tool_calls += 1
                    out, sql, touched, is_opt, gate = json.dumps({"error": f"Unknown tool `{c['name']}`"}), "-- NOT IN TOOLSET", [], False, None
                if _sha(out) != c["result_sha256"]:
                    raise ReplayMismatch(f"{record['run_id']} turn {t['turn_number']} {c['name']}: replayed output differs")
                if gate and gate.get("circuit_breaker_halt"):
                    circuit = True
                traces.append({
                    "tool_use_id": c["tool_use_id"],
                    "tool_name": c["name"],
                    "tool_input": dict(c.get("input") or {}),
                    "sql_executed": sql,
                    "tables_touched": list(touched),
                    "is_optimal_call": bool(is_opt),
                    "result_preview": out[:RESULT_PREVIEW_CHARS],
                    "gate_snapshot": gate,
                })
            steps.append({
                "step_number": int(t["turn_number"]),
                "model_id": t["model_id"],
                "escalated_from_haiku": bool(t.get("escalated_turn")),
                "stop_reason": t.get("stop_reason"),
                "assistant_thought": str(t.get("thinking_text") or t.get("raw_text") or "").strip()[:1200],
                "tool_calls": traces,
                "tool_calls_not_executed": list(t.get("tool_calls_not_executed") or []),
                "latency_ms": int(t.get("latency_ms") or 0),
                "input_tokens": int(t.get("input_tokens") or 0),
                "output_tokens": int(t.get("output_tokens") or 0),
                "thinking_tokens": int(t.get("thinking_tokens") or 0),
                "cache_creation_tokens": int(t.get("cache_creation_tokens") or 0),
                "cache_read_tokens": int(t.get("cache_read_tokens") or 0),
                "max_tokens": int(t.get("max_tokens") or 0),
            })
        voucher = session.get_committed_voucher(record["invoice_id"])
        if voucher != record.get("committed_voucher"):
            raise ReplayMismatch(f"{record['run_id']}: replayed voucher differs from the recorded one")
        tables = sorted(session.tables_touched)
        total, optimal = session.total_tool_calls, session.optimal_tool_calls
    finally:
        session.close()
    if (tables, total, optimal) != (sorted(record.get("tables_touched") or []), record.get("total_tool_calls"), record.get("optimal_tool_calls")):
        raise ReplayMismatch(f"{record['run_id']}: replayed trajectory counters differ")
    return {
        "rung_id": rung_id,
        "primary_model_id": PRIMARY_MODEL[rung_id],
        "steps": steps,
        "final_readout": record.get("final_message") or "",
        "circuit_breaker_triggered": circuit,
        "committed_voucher": ({**voucher, "gate_verified": bool(voucher["gate_verified"])} if voucher else None),
        "tables_touched": tables,
        "total_tool_calls": total,
        "optimal_tool_calls": optimal,
    }


def build_golden(records: list[dict[str, Any]], *, source_file: str) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    presets: dict[str, Any] = {}
    run_ids: dict[str, dict[str, str]] = {}
    for pid in ORIGINAL_INVOICES:
        rungs: dict[str, Any] = {}
        prov: dict[str, Any] = {}
        for arm_id, rung_id in APP_RUNG_FOR_ARM.items():
            rec = select_record(records, arm_id, pid)
            rungs[rung_id] = convert_record(rec)
            prov[rung_id] = {
                "arm_id": arm_id,
                "run_id": rec["run_id"],
                "repeat_index": int(rec["repeat_index"]),
                "started_at": rec.get("started_at"),
                "run_nonce": rec.get("run_nonce"),
                "system_text_sha256": rec.get("system_text_sha256"),
                "settings": rec.get("settings"),
                "ended_with_stop_reason": rec.get("ended_with_stop_reason"),
                "cap_hit": bool(rec.get("cap_hit")),
            }
            run_ids.setdefault(pid, {})[rung_id] = rec["run_id"]
        presets[pid] = {"use_case": USE_CASE, "rungs": rungs, "provenance": prov}
    doc = {
        "provenance": {
            "source": ABLATION_GOLDEN_SOURCE,
            "source_file": source_file,
            "selection_rule": (f"fixed pre-declared mapping: repeat_index {GOLDEN_REPEAT_INDEX} of "
                               + ", ".join(f"{a} -> {r}" for a, r in APP_RUNG_FOR_ARM.items())
                               + " on inv-01..03 (not selected by outcome)"),
            "rung_1_note": ("unbounded_sonnet_loop now runs the free-choice protocol (the ablation's neutral text): the "
                            "model chooses among the raw SELECT * tools, several per turn allowed; no cache; no gate. "
                            "The original scripted 7-step captures are kept in replays/cat5_ablation_summary.json "
                            "(original_scripted_captures) as a baseline, not as a runnable rung."),
            "trace_note": ("SQL text, tables touched, optimal-call flags and gate snapshots were rebuilt by replaying the "
                           "recorded tool calls on a fresh ERP session; every output matched the recorded sha256."),
            "settings_note": "Every turn ran with max_tokens 4096; stop_reason values are as returned by the API.",
        },
        "presets": presets,
    }
    return doc, run_ids


def _comparable(doc: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(doc))
    (out.get("provenance") or {}).pop("rebuilt_at", None)
    return out


def write_if_changed(doc: dict[str, Any], out_path: Path, *, stamp: bool) -> bool:
    if out_path.is_file():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = None
        if existing is not None and _comparable(existing) == _comparable(doc):
            return False
    out_doc = dict(doc)
    if stamp:
        out_doc["provenance"] = {**doc["provenance"], "rebuilt_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(BACKEND_DIR))
    except ValueError:
        return str(p)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="in_path", default=str(DEFAULT_IN))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--summary-out", default=str(DEFAULT_SUMMARY_OUT))
    args = ap.parse_args(argv)
    in_path, out_path, summary_path = Path(args.in_path), Path(args.out), Path(args.summary_out)
    records = load_jsonl(in_path)

    scripted = original_scripted_golden(out_path, summary_path)
    original = {pid: (scripted["presets"].get(pid) or {}).get("rungs", {}).get("unbounded_sonnet_loop") for pid in ORIGINAL_INVOICES}
    missing = [pid for pid, c in original.items() if not c]
    if missing:
        raise SystemExit(f"original scripted captures not found for {missing} (neither in {out_path} nor in {summary_path})")

    golden, run_ids = build_golden(records, source_file=_rel(in_path))
    portfolio = build_ablation_portfolio(records, original_scripted=original, source_file=_rel(in_path), golden_run_ids=run_ids)
    # Write the summary first so the scripted captures are safe before the golden file stops holding them.
    changed_s = write_if_changed(portfolio, summary_path, stamp=False)
    changed_g = write_if_changed(golden, out_path, stamp=True)
    for pid, p in golden["presets"].items():
        for rid, rung in p["rungs"].items():
            prov = p["provenance"][rid]
            v = rung["committed_voucher"] or {}
            print(f"{pid} {rid:<30} <- {prov['arm_id']:<27} r{prov['repeat_index']} {prov['run_id'][:8]} | steps={len(rung['steps'])} "
                  f"stops={[s['stop_reason'] for s in rung['steps']]} calls={rung['total_tool_calls']} {v.get('decision', '-')}")
    print(f"{'Wrote' if changed_g else 'Unchanged:'} {out_path}")
    for a in portfolio["arms"]:
        print(f"  {a['arm_id']:<27} exact {a['exact']}/{a['runs']} ${a['cost_per_1k_billed_usd']:.2f}/1k billed "
              f"${a['cost_per_1k_warm_usd']:.2f} warm turns {a['turns_mean']:.2f}")
    print(f"{'Wrote' if changed_s else 'Unchanged:'} {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
