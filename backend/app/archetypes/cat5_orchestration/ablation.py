"""Category 5 six-arm ablation harness: arms, prompts, one-run orchestration, scoring and summary.

Importable without an API key. Nothing here changes the app's Category 5 runner, prompts, tools,
ERP seed, fixtures or golden replays:

* tools are the app's own `NAIVE_TOOLS` / `GOVERNED_TOOLS` dicts (the bundle arms use the bundle tool
  plus the naive arm's commit tool, which carries no gate requirement);
* the gate arms use `get_cat5_system_prompt(...)` byte for byte (after a per-run nonce line);
* each run gets a fresh in-memory ERP: `create_seeded_erp_connection()` (via `Cat5ErpSession`) and then
  the extra ablation rows inserted on top.

Records hold raw tokens only (never dollars); cost is derived at analysis time with
`app.core.pricing.compute_run_finops` and the app's `_compute_step_cold_warm` rule.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import statistics
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.archetypes.cat5_orchestration.accuracy import evaluate_cat5_adjudication
from app.archetypes.cat5_orchestration.erp_db import (
    GOVERNED_TOOLS,
    NAIVE_TOOLS,
    Cat5ErpSession,
    evaluate_deterministic_policy_gate,
)
from app.archetypes.cat5_orchestration.prompts import (
    CAT5_FREE_CHOICE_PROTOCOL,
    build_cat5_user_task_prompt,
    get_cat5_system_prompt,
)
from app.archetypes.cat5_orchestration.runner import _compute_step_cold_warm
from app.core.anthropic_service import AnthropicRawResult, run_cat5_tool_loop_step
from app.core.pricing import LEGACY_MODEL_RATES, MODEL_RATES, compute_run_finops
from app.data.cat5_ablation_fixtures import (
    ANALYSIS_TIERS,
    CAT5_ABLATION_ALL_INVOICE_IDS,
    CAT5_ABLATION_DEFAULT_INVOICE_IDS,
    CAT5_ABLATION_ERP_ROWS,
    CAT5_ABLATION_EXCLUDED_PENDING_REVIEW,
    CAT5_ABLATION_GATE_DISAGREEMENT,
    CAT5_ABLATION_GATE_DISAGREEMENT_IDS,
    CAT5_ABLATION_FIXTURE_VERSION,
    CAT5_ABLATION_PRESETS,
    CAT5_ABLATION_PRESETS_BY_ID,
    ERP_TABLE_ORDER,
    invoice_fingerprint,
)
from app.data.cat5_fixtures import AP_POLICY_MANUAL_MARKDOWN

SCHEMA_VERSION = 1

SONNET_MODEL_ID = "claude-sonnet-5-5"
HAIKU_MODEL_ID = "claude-haiku-5-5"

MAX_TOKENS_PER_TURN = 4096
GATE_STEP_BUDGET = 4  # CAT5_BUDGETS for both governed rungs
GATE_TURN_CAP = GATE_STEP_BUDGET + 1  # as runner: governed hard_loop_cap = max_budget + 1 (wrap-up turn)
NEUTRAL_TURN_CAP = 12
CALL_TIMEOUT_S = 180.0
TOOL_RESULT_HEAD_CHARS = 1500
# Recorded only (not compared for superseding). v2: tool_use blocks run unless the turn hit max_tokens.
LOOP_RULE = "v2-execute-tool-use-unless-truncated"

# The app's rung 1 now uses this same text (prompts.CAT5_FREE_CHOICE_PROTOCOL); one definition for both.
NEUTRAL_PROTOCOL = CAT5_FREE_CHOICE_PROTOCOL

VOUCHER_FIELDS: tuple[str, ...] = (
    "decision",
    "authorized_net_principal_inr",
    "authorized_gst_payout_inr",
    "gst_escrow_holdback_inr",
    "debit_note_deduction_inr",
)

# --------------------------------------------------------------------------------------------------
# Arms
# --------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ArmSpec:
    arm_id: str
    tool_set: str  # "raw" | "bundle" | "governed"
    cached: bool
    start_model: str
    escalate: bool  # Haiku -> Sonnet when a gate snapshot says escalation_required (as runner's hybrid rung)
    gate: bool  # commit requires run_policy_tolerance_gate first (Cat5ErpSession governed mode)
    prompt: str  # "neutral" or the app rung id whose system prompt is used unchanged
    session_rung_id: str  # Cat5ErpSession rung_id: "unbounded_sonnet_loop" disables the gate requirement
    turn_cap: int
    step_budget: int
    voucher_computed_by: str
    summary: str


ARMS: dict[str, ArmSpec] = {
    a.arm_id: a
    for a in (
        ArmSpec("raw_free_sonnet", "raw", False, SONNET_MODEL_ID, False, False, "neutral",
                "unbounded_sonnet_loop", NEUTRAL_TURN_CAP, NEUTRAL_TURN_CAP, "model",
                "5 raw SELECT * tools + commit; no cache; Sonnet; neutral protocol"),
        ArmSpec("raw_free_sonnet_cached", "raw", True, SONNET_MODEL_ID, False, False, "neutral",
                "unbounded_sonnet_loop", NEUTRAL_TURN_CAP, NEUTRAL_TURN_CAP, "model",
                "5 raw SELECT * tools + commit; policy manual cached; Sonnet; neutral protocol"),
        ArmSpec("bundle_sonnet_cached", "bundle", True, SONNET_MODEL_ID, False, False, "neutral",
                "unbounded_sonnet_loop", NEUTRAL_TURN_CAP, NEUTRAL_TURN_CAP, "model",
                "fetch_3way_match_bundle + commit (no gate); cached; Sonnet; neutral protocol"),
        ArmSpec("bundle_gate_sonnet_cached", "governed", True, SONNET_MODEL_ID, False, True,
                "bounded_sonnet_cached_gate", "bounded_sonnet_cached_gate", GATE_TURN_CAP, GATE_STEP_BUDGET, "gate",
                "GOVERNED_TOOLS; cached; Sonnet; today's bounded_sonnet_cached_gate prompt"),
        ArmSpec("bundle_haiku_cached", "bundle", True, HAIKU_MODEL_ID, False, False, "neutral",
                "unbounded_sonnet_loop", NEUTRAL_TURN_CAP, NEUTRAL_TURN_CAP, "model",
                "fetch_3way_match_bundle + commit (no gate); cached; Haiku; neutral protocol"),
        ArmSpec("bundle_gate_haiku_escalate", "governed", True, HAIKU_MODEL_ID, True, True,
                "hybrid_haiku_sonnet_governed", "hybrid_haiku_sonnet_governed", GATE_TURN_CAP, GATE_STEP_BUDGET, "gate",
                "GOVERNED_TOOLS; cached; Haiku -> Sonnet on gate escalation; today's hybrid prompt"),
    )
}
ARM_IDS: tuple[str, ...] = tuple(ARMS)

LEVERS: tuple[tuple[str, str, str], ...] = (
    ("caching alone", "raw_free_sonnet", "raw_free_sonnet_cached"),
    ("narrow query", "raw_free_sonnet_cached", "bundle_sonnet_cached"),
    ("deterministic gate", "bundle_sonnet_cached", "bundle_gate_sonnet_cached"),
    ("model swap without gate", "bundle_sonnet_cached", "bundle_haiku_cached"),
    ("gate + tiering", "bundle_haiku_cached", "bundle_gate_haiku_escalate"),
    ("gate Sonnet -> gate Haiku escalate", "bundle_gate_sonnet_cached", "bundle_gate_haiku_escalate"),
)

_ARM_DIFF_FIELDS: tuple[str, ...] = ("tool_set", "cached", "start_model", "escalate", "gate", "prompt", "turn_cap")


def _arm(arm_id: str) -> ArmSpec:
    try:
        return ARMS[arm_id]
    except KeyError:
        raise ValueError(f"Unknown Cat 5 ablation arm `{arm_id}`; expected one of {list(ARMS)}") from None


def arm_differences(a: str, b: str) -> list[str]:
    """Attributes that differ between two arms, e.g. ['cached: False -> True']."""
    sa, sb = _arm(a), _arm(b)
    return [f"{f}: {getattr(sa, f)} -> {getattr(sb, f)}" for f in _ARM_DIFF_FIELDS if getattr(sa, f) != getattr(sb, f)]


def _commit_tool(tools: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return next(t for t in tools if t["name"] == "commit_reconciliation_voucher")


def tools_for(arm_id: str) -> list[dict[str, Any]]:
    """The arm's tool list, built from the app's own tool dicts (never edited)."""
    ts = _arm(arm_id).tool_set
    if ts == "raw":
        return list(NAIVE_TOOLS)
    if ts == "bundle":
        bundle = next(t for t in GOVERNED_TOOLS if t["name"] == "fetch_3way_match_bundle")
        return [bundle, _commit_tool(NAIVE_TOOLS)]
    return list(GOVERNED_TOOLS)


def neutral_system_text() -> str:
    return f"{AP_POLICY_MANUAL_MARKDOWN.strip()}\n\n{NEUTRAL_PROTOCOL}"


def base_system_text(arm_id: str) -> str:
    """System text without the nonce: the neutral protocol, or today's rung prompt unchanged."""
    arm = _arm(arm_id)
    return neutral_system_text() if arm.prompt == "neutral" else get_cat5_system_prompt(arm.prompt)


def nonce_line(nonce: str) -> str:
    return f"[run-nonce: {nonce}]\n"


def system_text_for(arm_id: str, nonce: str | None) -> str:
    """Cached arms get a per-run nonce line first so every run writes (then reads) its own cache."""
    base = base_system_text(arm_id)
    return f"{nonce_line(nonce)}{base}" if nonce else base


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def arm_fingerprint(arm_id: str) -> str:
    arm = _arm(arm_id)
    payload = {
        "arm": asdict(arm),
        "tools": tools_for(arm_id),
        "system_template": system_text_for(arm_id, "<nonce>" if arm.cached else None),
        "max_tokens_per_turn": MAX_TOKENS_PER_TURN,
    }
    return _sha(json.dumps(payload, sort_keys=True, ensure_ascii=False))[:16]


def current_settings(arm_id: str, preset_id: str) -> dict[str, Any]:
    arm = _arm(arm_id)
    return {
        "schema_version": SCHEMA_VERSION,
        "max_tokens_per_turn": MAX_TOKENS_PER_TURN,
        "turn_cap": arm.turn_cap,
        "step_budget": arm.step_budget,
        "timeout_s": CALL_TIMEOUT_S,
        "fixture_version": CAT5_ABLATION_FIXTURE_VERSION,
        "loop_rule": LOOP_RULE,
        "invoice_fingerprint": invoice_fingerprint(preset_id),
        "arm_fingerprint": arm_fingerprint(arm_id),
    }


# A record is superseded when any of these differ from the current values (re-run on resume, excluded).
_SETTINGS_COMPARED: tuple[str, ...] = (
    "max_tokens_per_turn",
    "turn_cap",
    "step_budget",
    "invoice_fingerprint",
    "arm_fingerprint",
)


# --------------------------------------------------------------------------------------------------
# ERP isolation
# --------------------------------------------------------------------------------------------------


def insert_ablation_rows(conn: sqlite3.Connection, rows: dict[str, list[dict[str, Any]]] = CAT5_ABLATION_ERP_ROWS) -> None:
    for table in ERP_TABLE_ORDER:
        batch = rows.get(table) or []
        if not batch:
            continue
        cols = list(batch[0].keys())
        conn.executemany(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})",
            batch,
        )
    conn.commit()


class AblationErpSession(Cat5ErpSession):
    """`Cat5ErpSession` on a fresh app-seeded in-memory ERP plus the ablation rows."""

    def __init__(self, *, rung_id: str, extra_rows: dict[str, list[dict[str, Any]]] | None = None) -> None:
        super().__init__(rung_id=rung_id)  # self.conn = create_seeded_erp_connection()
        insert_ablation_rows(self.conn, CAT5_ABLATION_ERP_ROWS if extra_rows is None else extra_rows)

    def all_vouchers(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM reconciliation_vouchers ORDER BY voucher_id")]


def gate_output_for(preset_id: str) -> dict[str, Any]:
    """Run the app's deterministic gate on a fresh extended ERP for one invoice."""
    s = AblationErpSession(rung_id="bounded_sonnet_cached_gate")
    try:
        return evaluate_deterministic_policy_gate(s.conn, CAT5_ABLATION_PRESETS_BY_ID[preset_id]["invoice_id"])
    finally:
        s.close()


def compare_with_gate(preset_id: str) -> dict[str, Any]:
    """Hand-derived ground truth vs the gate: per-field differences (rupees within 0.005) + escalation."""
    gt = CAT5_ABLATION_PRESETS_BY_ID[preset_id]["ground_truth"]
    g = gate_output_for(preset_id)
    gate_vals = {"decision": g.get("recommended_decision"), **{f: g.get(f) for f in VOUCHER_FIELDS[1:]}}
    diffs: dict[str, dict[str, Any]] = {}
    for f in VOUCHER_FIELDS:
        exp, got = gt[f], gate_vals[f]
        same = exp == got if f == "decision" else (got is not None and abs(float(exp) - float(got)) <= 0.005)
        if not same:
            diffs[f] = {"derivation": exp, "gate": got}
    if bool(gt["expected_escalation"]) != bool(g.get("escalation_required")):
        diffs["expected_escalation"] = {"derivation": gt["expected_escalation"], "gate": g.get("escalation_required")}
    return {"preset_id": preset_id, "agree": not diffs, "differences": diffs, "gate_output": g}


# --------------------------------------------------------------------------------------------------
# One run -> one record
# --------------------------------------------------------------------------------------------------

AgentCall = Callable[..., Awaitable[AnthropicRawResult]]
BlobSink = Callable[[str, str], None]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tool_call_entry(tu: dict[str, Any]) -> dict[str, Any]:
    return {"tool_use_id": str(tu.get("id") or ""), "name": str(tu.get("name") or ""), "input": dict(tu.get("input") or {})}


async def execute_run(
    *,
    arm_id: str,
    preset: dict[str, Any],
    repeat_index: int,
    api_key: str,
    agent_call: AgentCall = run_cat5_tool_loop_step,
    blob_sink: BlobSink | None = None,
    timeout_s: float = CALL_TIMEOUT_S,
) -> dict[str, Any]:
    """Execute ONE live run of `arm_id` on `preset`. Never raises for API/runtime errors."""
    arm = _arm(arm_id)
    nonce = uuid4().hex if arm.cached else None
    system_text = system_text_for(arm_id, nonce)
    tools = tools_for(arm_id)
    allowed = {t["name"] for t in tools}
    user_task = build_cat5_user_task_prompt(preset)
    turns: list[dict[str, Any]] = []
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": str(uuid4()),
        "arm_id": arm_id,
        "preset_id": preset["id"],
        "invoice_id": preset["invoice_id"],
        "repeat_index": repeat_index,
        "started_at": _utc_now_iso(),
        "finished_at": None,
        "status": "ok",
        "error_message": None,
        "settings": current_settings(arm_id, preset["id"]),
        "arm": asdict(arm),
        "run_nonce": nonce,
        "system_text_sha256": _sha(system_text),
        "user_task": user_task,
        "turns": turns,
        "turns_used": 0,
        "cap_hit": False,
        "ended_with_stop_reason": None,
        "escalation_fired": False,
        "gate_escalation_flagged": False,
        "circuit_breaker_triggered": False,
        "committed_voucher": None,
        "all_vouchers": [],
        "tables_touched": [],
        "total_tool_calls": 0,
        "optimal_tool_calls": 0,
        "final_message": "",
        "evaluation": None,
    }
    session: AblationErpSession | None = None
    try:
        session = AblationErpSession(rung_id=arm.session_rung_id)
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_task}]
        active_model = arm.start_model
        escalate_next = False
        natural_end = False
        for turn_number in range(1, arm.turn_cap + 1):
            escalated_turn = escalate_next
            escalate_next = False
            raw = await agent_call(
                model_tier=active_model,
                system_text=system_text,
                tools=tools,
                messages=list(messages),
                use_prefix_cache=arm.cached,
                api_key=api_key,
                max_tokens=MAX_TOKENS_PER_TURN,
                timeout_s=timeout_s,
            )
            structured = raw.structured or {}
            blocks = structured.get("assistant_blocks") or []
            tool_uses = structured.get("tool_uses") or []
            turn: dict[str, Any] = {
                "turn_number": turn_number,
                "intended_model_id": active_model,
                "model_id": raw.model_id,
                "escalated_turn": escalated_turn,
                "max_tokens": MAX_TOKENS_PER_TURN,
                "use_prefix_cache": arm.cached,
                "stop_reason": raw.stop_reason,
                "truncated": raw.stop_reason == "max_tokens",
                "latency_ms": int(raw.latency_ms),
                "input_tokens": int(raw.input_tokens),
                "output_tokens": int(raw.output_tokens),
                "thinking_tokens": int(raw.thinking_tokens or 0),
                "cache_creation_tokens": int(raw.cache_creation_tokens),
                "cache_read_tokens": int(raw.cache_read_tokens),
                "request_params": dict(raw.request_params or {}),
                "raw_text": raw.raw_text,
                "thinking_text": str(structured.get("thinking_text") or ""),
                "tool_calls": [],
                "tool_calls_not_executed": [],
            }
            turns.append(turn)
            record["turns_used"] = turn_number
            messages.append({"role": "assistant", "content": blocks})

            if raw.stop_reason == "max_tokens":
                # Truncated turn: its tool_use blocks may be cut off, so they are recorded, not executed; run ends.
                turn["tool_calls_not_executed"] = [_tool_call_entry(tu) for tu in tool_uses]
                record["final_message"] = raw.raw_text
                record["ended_with_stop_reason"] = raw.stop_reason
                natural_end = True
                break
            if not tool_uses:
                # Only a (non-truncated) turn with no tool calls ends the run.
                record["final_message"] = raw.raw_text
                record["ended_with_stop_reason"] = raw.stop_reason
                natural_end = True
                break
            # tool_use blocks are executed whatever the stop_reason (the API has returned end_turn with tool_use
            # blocks); the mismatch is flagged on the turn.
            turn["tool_use_with_stop_reason"] = raw.stop_reason if raw.stop_reason != "tool_use" else None

            results: list[dict[str, Any]] = []
            for tu in tool_uses:
                entry = _tool_call_entry(tu)
                if entry["name"] in allowed:
                    out, _sql, touched, is_opt, gate_snap = session.execute_tool(entry["name"], entry["input"])
                    entry.update({"executed": True, "rejected_reason": None, "tables_touched": list(touched), "is_optimal_call": bool(is_opt)})
                else:
                    session.total_tool_calls += 1  # the app's session counts unknown tools as calls too
                    out = json.dumps({"error": f"Unknown tool `{entry['name']}`"})
                    gate_snap = None
                    entry.update({"executed": False, "rejected_reason": "not_in_arm_toolset", "tables_touched": [], "is_optimal_call": False})
                digest = _sha(out)
                entry.update({"result_chars": len(out), "result_sha256": digest, "result_head": out[:TOOL_RESULT_HEAD_CHARS]})
                if gate_snap:
                    entry["gate_flags"] = {
                        "hard_block": bool(gate_snap.get("hard_block")),
                        "escalation_required": bool(gate_snap.get("escalation_required")),
                        "recommended_decision": gate_snap.get("recommended_decision"),
                    }
                    if gate_snap.get("circuit_breaker_halt"):
                        record["circuit_breaker_triggered"] = True
                    if gate_snap.get("escalation_required"):
                        record["gate_escalation_flagged"] = True
                    if arm.escalate and "haiku" in active_model and gate_snap.get("escalation_required"):
                        active_model = SONNET_MODEL_ID
                        escalate_next = True
                        record["escalation_fired"] = True
                if blob_sink is not None:
                    blob_sink(digest, out)
                turn["tool_calls"].append(entry)
                results.append({"type": "tool_result", "tool_use_id": entry["tool_use_id"], "content": out})

            messages.append({"role": "user", "content": results})

        if not natural_end:
            record["cap_hit"] = True
            record["final_message"] = turns[-1]["raw_text"] if turns else ""
            record["ended_with_stop_reason"] = turns[-1]["stop_reason"] if turns else None
    except Exception as exc:  # noqa: BLE001 — an error is recorded, never raised
        record["status"] = "error"
        record["error_message"] = f"{type(exc).__name__}: {exc}"[:2000]
    finally:
        if session is not None:
            try:
                record["committed_voucher"] = session.get_committed_voucher(preset["invoice_id"])
                record["all_vouchers"] = session.all_vouchers()
                record["tables_touched"] = sorted(session.tables_touched)
                record["total_tool_calls"] = session.total_tool_calls
                record["optimal_tool_calls"] = session.optimal_tool_calls
            finally:
                session.close()
    record["evaluation"] = evaluate_record(record, preset)
    record["finished_at"] = _utc_now_iso()
    return record


def evaluate_record(record: dict[str, Any], preset: dict[str, Any] | None = None) -> dict[str, Any]:
    """The app's `evaluate_cat5_adjudication` on the record's committed voucher and trajectory."""
    preset = preset or CAT5_ABLATION_PRESETS_BY_ID[str(record["preset_id"])]
    budget = int((record.get("settings") or {}).get("step_budget") or _arm(record["arm_id"]).step_budget)
    ev = evaluate_cat5_adjudication(
        committed_voucher=record.get("committed_voucher"),
        ground_truth=preset["ground_truth"],
        tables_touched=record.get("tables_touched") or [],
        total_tool_calls=int(record.get("total_tool_calls") or 0),
        optimal_tool_calls=int(record.get("optimal_tool_calls") or 0),
        steps_used=int(record.get("turns_used") or 0),
        max_step_budget=budget,
    )
    return ev.model_dump()


# --------------------------------------------------------------------------------------------------
# Matrix planning, resume, superseded settings
# --------------------------------------------------------------------------------------------------

RunKey = tuple[str, str, int]  # (arm_id, preset_id, repeat_index)


def record_key(record: dict[str, Any]) -> RunKey:
    return (str(record["arm_id"]), str(record["preset_id"]), int(record["repeat_index"]))


def plan_matrix(arm_ids: Sequence[str], preset_ids: Sequence[str], repeats: int) -> list[RunKey]:
    """Order repeat -> invoice -> arm so a partial run stays balanced."""
    return [(a, p, r) for r in range(repeats) for p in preset_ids for a in arm_ids]


ARTIFACT_REASON = "harness ended the run with tool calls not executed"


def harness_artifact(record: dict[str, Any]) -> bool:
    """True for a run the v1 loop ended on a non-truncated turn that still had tool_use blocks (never executed).
    Such a record is not an outcome: it is superseded and its key is re-run."""
    return any(
        t.get("tool_calls_not_executed") and t.get("stop_reason") != "max_tokens" for t in record.get("turns") or []
    )


def is_current_settings(record: dict[str, Any]) -> bool:
    if harness_artifact(record):
        return False
    try:
        cur = current_settings(str(record["arm_id"]), str(record["preset_id"]))
    except (KeyError, ValueError):
        return False
    got = record.get("settings") or {}
    return all(got.get(k) == cur[k] for k in _SETTINGS_COMPARED)


def superseded_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in records:
        if is_current_settings(r):
            continue
        s = r.get("settings") or {}
        out.append(
            {
                "reason": ARTIFACT_REASON if harness_artifact(r) else "settings changed",
                "run_id": r.get("run_id"),
                "arm_id": r.get("arm_id"),
                "preset_id": r.get("preset_id"),
                "repeat_index": r.get("repeat_index"),
                "status": r.get("status"),
                "recorded": {k: s.get(k) for k in _SETTINGS_COMPARED},
            }
        )
    return out


def select_pending(planned: Iterable[RunKey], existing: Iterable[dict[str, Any]]) -> list[RunKey]:
    """A key is done only with an `ok` record at the current settings; errors and superseded records leave it pending."""
    done = {record_key(r) for r in existing if r.get("status") == "ok" and is_current_settings(r)}
    return [k for k in planned if k not in done]


def latest_ok_current(records: Iterable[dict[str, Any]]) -> dict[RunKey, dict[str, Any]]:
    out: dict[RunKey, dict[str, Any]] = {}
    for r in records:
        if r.get("status") == "ok" and is_current_settings(r):
            out[record_key(r)] = r  # file order: later wins
    return out


def load_jsonl(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


# --------------------------------------------------------------------------------------------------
# Cost (derived from tokens at analysis time)
# --------------------------------------------------------------------------------------------------


def _priced_model(turn: dict[str, Any]) -> str:
    mid = str(turn.get("model_id") or "")
    return mid if (mid in MODEL_RATES or mid in LEGACY_MODEL_RATES) else str(turn.get("intended_model_id") or SONNET_MODEL_ID)


def turn_finops(turn: dict[str, Any]):
    return compute_run_finops(
        model_id=_priced_model(turn),
        input_tokens=int(turn.get("input_tokens") or 0),
        output_tokens=int(turn.get("output_tokens") or 0),
        cache_creation_tokens=int(turn.get("cache_creation_tokens") or 0),
        cache_read_tokens=int(turn.get("cache_read_tokens") or 0),
    )


def record_costs_usd(record: dict[str, Any]) -> dict[str, float]:
    """Billed / cold / warm run cost. Cold & warm use the app's `_compute_step_cold_warm` rule
    (uncached arm, or a turn with no prefix tokens, costs the same as billed)."""
    cached = bool((record.get("arm") or {}).get("cached", _arm(record["arm_id"]).cached))
    rung_like = "unbounded_sonnet_loop" if not cached else str(record["arm_id"])
    seen: set[str] = set()
    billed = cold = warm = 0.0
    for t in record.get("turns") or []:
        fin = turn_finops(t)
        billed += fin.total_cost_usd
        c, w = _compute_step_cold_warm(rung_id=rung_like, finops=fin, seen_cache_models=seen)
        cold += c
        warm += w
    return {"billed": round(billed, 8), "cold": round(cold, 8), "warm": round(warm, 8)}


def record_billed_usd(record: dict[str, Any]) -> float:
    return record_costs_usd(record)["billed"]


# --------------------------------------------------------------------------------------------------
# Dry-run estimates calibrated on the golden replays, and the budget guard
# --------------------------------------------------------------------------------------------------

GOLDEN_PATH = Path(__file__).resolve().parents[3] / "replays" / "cat5_golden_replays.json"


SUMMARY_PATH = GOLDEN_PATH.parent / "cat5_ablation_summary.json"
ABLATION_GOLDEN_SOURCE = "cat5 ablation"


def original_scripted_golden(golden_path: Path | str | None = None, summary_path: Path | str | None = None) -> dict[str, Any]:
    """The original scripted naive captures (the old `unbounded_sonnet_loop` prompt), as a golden-shaped dict.

    Until the golden file is rebuilt from the ablation it holds them itself; afterwards they live in
    replays/cat5_ablation_summary.json (`original_scripted_captures`)."""
    golden = load_golden(golden_path)
    if (golden.get("provenance") or {}).get("source") != ABLATION_GOLDEN_SOURCE:
        held = {pid: {"rungs": {"unbounded_sonnet_loop": p["rungs"]["unbounded_sonnet_loop"]}}
                for pid, p in (golden.get("presets") or {}).items()
                if "unbounded_sonnet_loop" in (p.get("rungs") or {})}
        if held:
            return {"presets": held}
    sp = Path(summary_path or SUMMARY_PATH)
    caps = (json.loads(sp.read_text(encoding="utf-8")).get("original_scripted_captures") or {}) if sp.is_file() else {}
    return {"presets": {pid: {"rungs": {"unbounded_sonnet_loop": c}} for pid, c in caps.items()}}


def load_golden(path: Path | str | None = None) -> dict[str, Any]:
    p = Path(path or GOLDEN_PATH)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"presets": {}}


def _prompt_tok(step: dict[str, Any]) -> int:
    return int(step.get("input_tokens") or 0) + int(step.get("cache_creation_tokens") or 0) + int(step.get("cache_read_tokens") or 0)


def _prefix_chars(system_text: str, tools: Sequence[dict[str, Any]]) -> int:
    return len(system_text) + len(json.dumps(list(tools)))


@dataclass(frozen=True)
class Calibration:
    chars_per_token: dict[str, float]  # model -> chars per prompt token on turn 1
    ref_steps: dict[str, dict[str, list[dict[str, Any]]]]  # ref rung -> preset -> steps
    source: str


_DEFAULT_CPT = {SONNET_MODEL_ID: 2.9, HAIKU_MODEL_ID: 2.9}


def calibrate(golden: dict[str, Any] | None = None) -> Calibration:
    """Chars/token from each golden rung's turn 1 (prefix + task), and the per-turn token pattern to replay."""
    golden = golden if golden is not None else load_golden()
    presets = golden.get("presets") or {}
    ratios: dict[str, list[float]] = {SONNET_MODEL_ID: [], HAIKU_MODEL_ID: []}
    ref: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for pid, pdata in presets.items():
        if pid not in CAT5_ABLATION_PRESETS_BY_ID:
            continue
        task_len = len(build_cat5_user_task_prompt(CAT5_ABLATION_PRESETS_BY_ID[pid]))
        for rid, rung in (pdata.get("rungs") or {}).items():
            steps = rung.get("steps") or []
            if not steps:
                continue
            ref.setdefault(rid, {})[pid] = steps
            tools = NAIVE_TOOLS if rid == "unbounded_sonnet_loop" else GOVERNED_TOOLS
            chars = _prefix_chars(get_cat5_system_prompt(rid), tools) + task_len
            mid = str(steps[0].get("model_id") or "")
            if mid in ratios and _prompt_tok(steps[0]) > 0:
                ratios[mid].append(chars / _prompt_tok(steps[0]))
    cpt = {m: (statistics.fmean(v) if v else _DEFAULT_CPT[m]) for m, v in ratios.items()}
    return Calibration(chars_per_token=cpt, ref_steps=ref, source="replays/cat5_golden_replays.json" if ref else "defaults")


def _reference_steps(arm: ArmSpec, preset: dict[str, Any], cal: Calibration) -> list[list[dict[str, Any]]]:
    """Golden runs whose turn pattern stands in for this arm on this invoice."""
    if arm.tool_set == "raw":
        rid = "unbounded_sonnet_loop"
    elif arm.escalate:
        rid = "hybrid_haiku_sonnet_governed"
    elif arm.start_model == HAIKU_MODEL_ID:
        rid = "hybrid_haiku_sonnet_governed"
    else:
        rid = "bounded_sonnet_cached_gate"
    by_preset = cal.ref_steps.get(rid) or {}
    if preset["id"] in by_preset:
        return [by_preset[preset["id"]]]
    if arm.escalate:
        same = [
            s for pid, s in by_preset.items()
            if bool(CAT5_ABLATION_PRESETS_BY_ID[pid]["ground_truth"]["expected_escalation"])
            == bool(preset["ground_truth"]["expected_escalation"])
        ]
        if same:
            return same
    # New invoices: the full-length (non-hard-stop) golden runs.
    full = [s for pid, s in by_preset.items() if pid != "inv-03"]
    return full or list(by_preset.values())


def estimate_run(arm_id: str, preset: dict[str, Any], cal: Calibration) -> dict[str, Any]:
    """Typical and worst-case $ for one run. Typical replays the golden turn pattern with this arm's prefix,
    cache flag and models; worst case = turn_cap turns at the largest golden history with max_tokens output."""
    arm = _arm(arm_id)
    tools = tools_for(arm_id)
    sys_chars = _prefix_chars(system_text_for(arm_id, "0" * 32 if arm.cached else None), tools)
    task_chars = len(build_cat5_user_task_prompt(preset))

    def price(calls: list[tuple[str, float, float, float, float]]) -> float:
        tot = 0.0
        for mid, unc, cw, cr, out in calls:
            r = MODEL_RATES[mid]
            tot += (unc * r.input_per_1m_usd + cw * r.cache_write_per_1m_usd + cr * r.cache_read_per_1m_usd + out * r.output_per_1m_usd) / 1e6
        return tot

    typical_runs: list[tuple[float, float, int]] = []
    max_hist = 0.0
    for steps in _reference_steps(arm, preset, cal) or [[]]:
        if not steps:
            continue
        base = _prompt_tok(steps[0])
        seen: set[str] = set()
        calls = []
        for s in steps:
            mid = str(s.get("model_id") or arm.start_model)
            if mid not in MODEL_RATES:
                mid = arm.start_model
            if not arm.escalate:
                mid = arm.start_model
            prefix = sys_chars / cal.chars_per_token[mid]
            hist = max(0.0, _prompt_tok(s) - base)
            max_hist = max(max_hist, hist)
            unc = task_chars / cal.chars_per_token[mid] + hist
            if arm.cached:
                first = mid not in seen
                seen.add(mid)
                calls.append((mid, unc, prefix if first else 0.0, 0.0 if first else prefix, float(s.get("output_tokens") or 0)))
            else:
                calls.append((mid, unc + prefix, 0.0, 0.0, float(s.get("output_tokens") or 0)))
        typical_runs.append((price(calls), sum(c[1] + c[2] + c[3] for c in calls), len(steps)))

    worst_model = SONNET_MODEL_ID if (arm.escalate or arm.start_model == SONNET_MODEL_ID) else arm.start_model
    prefix_w = sys_chars / cal.chars_per_token[worst_model]
    unc_w = task_chars / cal.chars_per_token[worst_model] + max(max_hist, 15000.0 if arm.tool_set == "raw" else 3000.0)
    worst_calls = []
    for i in range(arm.turn_cap):
        if arm.cached:
            worst_calls.append((worst_model, unc_w, prefix_w if i == 0 else 0.0, 0.0 if i == 0 else prefix_w, float(MAX_TOKENS_PER_TURN)))
        else:
            worst_calls.append((worst_model, unc_w + prefix_w, 0.0, 0.0, float(MAX_TOKENS_PER_TURN)))
    if arm.escalate:  # Haiku turns first, Sonnet writes its own prefix once
        worst_calls[0] = (HAIKU_MODEL_ID, unc_w, prefix_w, 0.0, float(MAX_TOKENS_PER_TURN))
        worst_calls[1] = (SONNET_MODEL_ID, unc_w, prefix_w, 0.0, float(MAX_TOKENS_PER_TURN))
    typical = statistics.fmean(t[0] for t in typical_runs) if typical_runs else price(worst_calls)
    return {
        "typical_usd": typical,
        "typical_prompt_tokens": statistics.fmean(t[1] for t in typical_runs) if typical_runs else None,
        "typical_turns": statistics.fmean(t[2] for t in typical_runs) if typical_runs else None,
        "worst_case_usd": price(worst_calls),
    }


def estimate_matrix(keys: Sequence[RunKey], cal: Calibration | None = None) -> dict[str, Any]:
    cal = cal or calibrate()
    per_arm: dict[str, dict[str, Any]] = {}
    for a, p, _r in keys:
        est = estimate_run(a, CAT5_ABLATION_PRESETS_BY_ID[p], cal)
        slot = per_arm.setdefault(a, {"runs": 0, "typical_usd": 0.0, "worst_case_usd": 0.0})
        slot["runs"] += 1
        slot["typical_usd"] += est["typical_usd"]
        slot["worst_case_usd"] += est["worst_case_usd"]
    for slot in per_arm.values():
        slot["typical_usd_per_run"] = slot["typical_usd"] / slot["runs"]
        slot["typical_usd_per_1k_invoices"] = slot["typical_usd_per_run"] * 1000
        slot["worst_case_usd_per_run"] = slot["worst_case_usd"] / slot["runs"]
    return {
        "calibration": {"chars_per_token": cal.chars_per_token, "source": cal.source},
        "per_arm": per_arm,
        "total_typical_usd": sum(s["typical_usd"] for s in per_arm.values()),
        "total_worst_case_usd": sum(s["worst_case_usd"] for s in per_arm.values()),
    }


class BudgetGuard:
    """Billed spend of existing records (ok, error and superseded) + in-flight reservations; refuse a run
    whose worst-case estimate would cross the cap."""

    def __init__(self, max_usd: float, existing: Iterable[dict[str, Any]] = ()) -> None:
        self.max_usd = float(max_usd)
        self.spent_usd = sum(record_billed_usd(r) for r in existing)
        self.reserved_usd = 0.0

    def try_reserve(self, worst_case_usd: float) -> bool:
        if self.spent_usd + self.reserved_usd + worst_case_usd > self.max_usd:
            return False
        self.reserved_usd += worst_case_usd
        return True

    def settle(self, reserved_usd: float, record: dict[str, Any]) -> float:
        cost = record_billed_usd(record)
        self.reserved_usd = max(0.0, self.reserved_usd - reserved_usd)
        self.spent_usd += cost
        return cost


# --------------------------------------------------------------------------------------------------
# Scoring (pure)
# --------------------------------------------------------------------------------------------------


def wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, centre - half), min(1.0, centre + half)


def _all_tool_calls(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for t in record.get("turns") or [] for c in t.get("tool_calls") or []]


def score_record(record: dict[str, Any]) -> dict[str, Any]:
    """Per-run scorecard (re-evaluated from the recorded voucher and trajectory)."""
    preset = CAT5_ABLATION_PRESETS_BY_ID[str(record["preset_id"])]
    ev = evaluate_record(record, preset)
    fields = {fc["field"]: bool(fc["matched"]) for fc in ev["field_checks"]}
    turns = record.get("turns") or []
    calls = _all_tool_calls(record)
    return {
        "run_id": record.get("run_id"),
        "arm_id": record["arm_id"],
        "preset_id": record["preset_id"],
        "repeat_index": record.get("repeat_index"),
        "analysis_tier": preset.get("analysis_tier"),
        "committed": bool(ev["voucher_committed"]),
        "exact": bool(ev["exact_match"]),
        "decision_correct": fields.get("decision", False),
        "fields": fields,
        "field_accuracy_pct": float(ev["field_accuracy_pct"]),
        "evidence_recall_pct": float(ev["evidence_recall_pct"]),
        "tool_precision_pct": float(ev["tool_precision_pct"]),
        "within_step_budget": bool(ev["within_step_budget"]),
        "tool_calls_by_name": dict(Counter(c.get("name") for c in calls)),
        "tool_calls_total": len(calls),
        "disallowed_tool_calls": sum(1 for c in calls if c.get("rejected_reason") == "not_in_arm_toolset"),
        "disallowed_by_name": dict(Counter(c.get("name") for c in calls if c.get("rejected_reason") == "not_in_arm_toolset")),
        "turns": len(turns),
        "cap_hit": bool(record.get("cap_hit")),
        "truncated_turns": sum(1 for t in turns if t.get("stop_reason") == "max_tokens"),
        "escalation_expected": bool(preset["ground_truth"].get("expected_escalation")),
        "escalation_fired": bool(record.get("escalation_fired")),
        "gate_escalation_flagged": bool(record.get("gate_escalation_flagged")),
        "tokens": {
            k: sum(int(t.get(f) or 0) for t in turns)
            for k, f in (
                ("uncached_input", "input_tokens"),
                ("cache_write", "cache_creation_tokens"),
                ("cache_read", "cache_read_tokens"),
                ("output", "output_tokens"),
                ("thinking", "thinking_tokens"),
            )
        },
        "cost_usd": record_costs_usd(record),
    }


def _dist(values: Sequence[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "min": None, "max": None}
    return {"mean": statistics.fmean(values), "min": min(values), "max": max(values)}


def _rate_block(k: int, n: int) -> dict[str, Any]:
    return {"k": k, "n": n, "rate": (k / n if n else None), "wilson95": wilson_interval(k, n)}


def group_metrics(scores: Sequence[dict[str, Any]], *, arm_id: str | None = None) -> dict[str, Any]:
    n = len(scores)
    arm_tools = [t["name"] for t in tools_for(arm_id)] if arm_id else []
    seen_names = {name for s in scores for name in s["tool_calls_by_name"]}
    tool_names = arm_tools + sorted(seen_names - set(arm_tools))  # the arm's own tools (incl. zero counts) first
    esc_exp = [s for s in scores if s["escalation_expected"]]
    return {
        "runs": n,
        "exact": _rate_block(sum(s["exact"] for s in scores), n),
        "decision_correct": _rate_block(sum(s["decision_correct"] for s in scores), n),
        "committed": _rate_block(sum(s["committed"] for s in scores), n),
        "field_match_rate": {f: (sum(s["fields"].get(f, False) for s in scores) / n if n else None) for f in VOUCHER_FIELDS},
        "field_accuracy_pct_mean": _dist([s["field_accuracy_pct"] for s in scores])["mean"],
        "evidence_recall_pct_mean": _dist([s["evidence_recall_pct"] for s in scores])["mean"],
        "tool_precision_pct_mean": _dist([s["tool_precision_pct"] for s in scores])["mean"],
        "tool_calls_per_run": {name: (sum(s["tool_calls_by_name"].get(name, 0) for s in scores) / n if n else None) for name in tool_names},
        "tool_calls_total_per_run": _dist([float(s["tool_calls_total"]) for s in scores]),
        "runs_calling_tool": {name: sum(1 for s in scores if s["tool_calls_by_name"].get(name)) for name in tool_names},
        "disallowed_tool_calls": {
            "total": sum(s["disallowed_tool_calls"] for s in scores),
            "per_run": (sum(s["disallowed_tool_calls"] for s in scores) / n if n else None),
            "by_name": dict(sum((Counter(s.get("disallowed_by_name") or {}) for s in scores), Counter())),
        },
        "turns": _dist([float(s["turns"]) for s in scores]),
        "cap_hits": sum(s["cap_hit"] for s in scores),
        "truncated_turns": sum(s["truncated_turns"] for s in scores),
        "runs_with_truncation": sum(1 for s in scores if s["truncated_turns"]),
        "escalation": {
            "expected": len(esc_exp),
            "fired": sum(s["escalation_fired"] for s in scores),
            "expected_and_fired": sum(s["escalation_fired"] for s in esc_exp),
            "fired_not_expected": sum(1 for s in scores if s["escalation_fired"] and not s["escalation_expected"]),
            "gate_flagged": sum(s["gate_escalation_flagged"] for s in scores),
        },
        "tokens_per_run_mean": {
            k: _dist([float(s["tokens"][k]) for s in scores])["mean"]
            for k in ("uncached_input", "cache_write", "cache_read", "output", "thinking")
        },
        "cost_per_1k_invoices_usd": {
            v: (statistics.fmean(s["cost_usd"][v] for s in scores) * 1000 if n else None) for v in ("billed", "cold", "warm")
        },
        "total_billed_usd": sum(s["cost_usd"]["billed"] for s in scores),
    }


def lever_table(arm_metrics: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for label, a, b in LEVERS:
        ma, mb = arm_metrics.get(a), arm_metrics.get(b)
        row: dict[str, Any] = {"lever": label, "from_arm": a, "to_arm": b, "changes": arm_differences(a, b)}
        if not ma or not mb or not ma["runs"] or not mb["runs"]:
            row.update({"available": False})
            rows.append(row)
            continue
        row["available"] = True
        row["runs"] = {"from": ma["runs"], "to": mb["runs"]}
        for metric in ("exact", "decision_correct"):
            ra, rb = ma[metric]["rate"], mb[metric]["rate"]
            row[metric] = {"from": ra, "to": rb, "delta_pp": (rb - ra) * 100}
        row["cost_per_1k_invoices_usd"] = {}
        for v in ("billed", "cold", "warm"):
            ca, cb = ma["cost_per_1k_invoices_usd"][v], mb["cost_per_1k_invoices_usd"][v]
            row["cost_per_1k_invoices_usd"][v] = {
                "from": ca,
                "to": cb,
                "delta": cb - ca,
                "ratio": (cb / ca) if ca else None,
            }
        rows.append(row)
    return rows


def golden_baseline(golden: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The stored scripted naive runs (unbounded_sonnet_loop, n=1 each) scored like ablation runs."""
    golden = golden if golden is not None else original_scripted_golden()
    out = []
    for pid, pdata in sorted((golden.get("presets") or {}).items()):
        rung = (pdata.get("rungs") or {}).get("unbounded_sonnet_loop")
        if not rung or pid not in CAT5_ABLATION_PRESETS_BY_ID:
            continue
        steps = rung.get("steps") or []
        pseudo = {
            "arm_id": "raw_free_sonnet",
            "preset_id": pid,
            "repeat_index": 0,
            "settings": {"step_budget": 10},
            "arm": {"cached": False},
            "committed_voucher": rung.get("committed_voucher"),
            "tables_touched": rung.get("tables_touched") or [],
            "total_tool_calls": rung.get("total_tool_calls") or 0,
            "optimal_tool_calls": rung.get("optimal_tool_calls") or 0,
            "turns_used": len(steps),
            "turns": [
                {
                    "model_id": s.get("model_id"),
                    "intended_model_id": SONNET_MODEL_ID,
                    "input_tokens": s.get("input_tokens"),
                    "output_tokens": s.get("output_tokens"),
                    "cache_creation_tokens": s.get("cache_creation_tokens"),
                    "cache_read_tokens": s.get("cache_read_tokens"),
                    "stop_reason": s.get("stop_reason"),
                    "tool_calls": [{"name": c.get("tool_name")} for c in s.get("tool_calls") or []],
                }
                for s in steps
            ],
        }
        sc = score_record(pseudo)
        sc.update({"label": "original scripted baseline (golden replay, n=1)", "run_id": None})
        out.append(sc)
    return out


def _review_entry(record: dict[str, Any], score: dict[str, Any]) -> dict[str, Any]:
    preset = CAT5_ABLATION_PRESETS_BY_ID[str(record["preset_id"])]
    gt = preset["ground_truth"]
    v = record.get("committed_voucher") or {}
    return {
        "run_id": record.get("run_id"),
        "arm_id": record["arm_id"],
        "preset_id": record["preset_id"],
        "repeat_index": record.get("repeat_index"),
        "expected": {f: gt[f] for f in VOUCHER_FIELDS},
        "committed": ({f: v.get(f) for f in VOUCHER_FIELDS} if record.get("committed_voucher") else None),
        "mismatched_fields": [f for f, ok in score["fields"].items() if not ok],
        "other_vouchers": [x for x in record.get("all_vouchers") or [] if x.get("invoice_id") != record.get("invoice_id")],
        "tools_called": [f"t{t.get('turn_number')}:{c.get('name')}" for t in record.get("turns") or [] for c in t.get("tool_calls") or []],
        "turns": score["turns"],
        "cap_hit": score["cap_hit"],
        "truncated_turns": score["truncated_turns"],
        "final_message": record.get("final_message") or "",
    }


def data_quality(records: Sequence[dict[str, Any]], used: Sequence[dict[str, Any]]) -> dict[str, Any]:
    def loc(r: dict[str, Any], **extra: Any) -> dict[str, Any]:
        return {"run_id": r.get("run_id"), "arm_id": r.get("arm_id"), "preset_id": r.get("preset_id"),
                "repeat_index": r.get("repeat_index"), "status": r.get("status"), **extra}

    current = [r for r in records if is_current_settings(r)]
    errors = [r for r in current if r.get("status") != "ok"]
    truncations, mismatches, cache_anoms, disallowed, stop_mismatch = [], [], [], [], []
    for r in current:
        cached = bool((r.get("arm") or {}).get("cached"))
        seen: set[str] = set()
        for t in r.get("turns") or []:
            n = t.get("turn_number")
            if t.get("stop_reason") == "max_tokens":
                truncations.append(loc(r, turn_number=n, output_tokens=t.get("output_tokens"),
                                       tool_calls_not_executed=len(t.get("tool_calls_not_executed") or [])))
            if t.get("model_id") != t.get("intended_model_id"):
                mismatches.append(loc(r, turn_number=n, intended_model_id=t.get("intended_model_id"), model_id=t.get("model_id")))
            cw, cr = int(t.get("cache_creation_tokens") or 0), int(t.get("cache_read_tokens") or 0)
            mid = str(t.get("model_id"))
            first = mid not in seen
            seen.add(mid)
            issue = None
            if not cached and (cw or cr):
                issue = "uncached arm reported cache tokens"
            elif cached and cw + cr == 0:
                issue = "cached arm turn with no cache write or read"
            elif cached and first and cr > 0:
                issue = "first turn on this model read the cache (nonce should force a write)"
            elif cached and not first and cr == 0:
                issue = "later turn on this model did not read the cache"
            if issue:
                cache_anoms.append(loc(r, turn_number=n, model_id=mid, cache_creation_tokens=cw, cache_read_tokens=cr, issue=issue))
            for c in t.get("tool_calls") or []:
                if c.get("rejected_reason"):
                    disallowed.append(loc(r, turn_number=n, tool=c.get("name"), reason=c.get("rejected_reason")))
            if t.get("tool_use_with_stop_reason"):
                stop_mismatch.append(loc(r, turn_number=n, stop_reason=t.get("tool_use_with_stop_reason"),
                                         tool_calls=len(t.get("tool_calls") or [])))
    return {
        "errors": [loc(r, error_message=r.get("error_message"), completed_turns=len(r.get("turns") or []),
                       billed_usd=record_billed_usd(r)) for r in errors],
        "truncated_turns": truncations,
        "model_mismatches": mismatches,
        "cache_anomalies": cache_anoms,
        "cap_hits": [loc(r, turns=len(r.get("turns") or []), committed=bool(r.get("committed_voucher"))) for r in used if r.get("cap_hit")],
        "no_voucher_committed": [loc(r) for r in used if not r.get("committed_voucher")],
        "disallowed_tool_calls": disallowed,
        "tool_use_blocks_with_other_stop_reason": stop_mismatch,
        "superseded_records": superseded_records(records),
        "error_spend_usd": sum(record_billed_usd(r) for r in errors),
        "superseded_spend_usd": sum(record_billed_usd(r) for r in records if not is_current_settings(r)),
    }


def fixture_table() -> list[dict[str, Any]]:
    rows = []
    for p in CAT5_ABLATION_PRESETS:
        cmp = compare_with_gate(p["id"])
        gt = p["ground_truth"]
        rows.append(
            {
                "preset_id": p["id"],
                "invoice_id": p["invoice_id"],
                "scenario": p.get("scenario"),
                "analysis_tier": p.get("analysis_tier"),
                "fc_hub": p["fc_hub"],
                "expected_decision": gt["decision"],
                "expected_escalation": gt["expected_escalation"],
                "invoice_grand_total_inr": p["invoice_grand_total_inr"],
                "source": p.get("source"),
                "derivation_agrees_with_gate": cmp["agree"],
                "differences": cmp["differences"],
                "in_default_matrix": p["id"] in CAT5_ABLATION_DEFAULT_INVOICE_IDS,
                "group": "gate_disagreement" if p["id"] in CAT5_ABLATION_GATE_DISAGREEMENT else "default",
            }
        )
    return rows


def _line1_rate(voucher: dict[str, Any] | None, dis: dict[str, Any]) -> str:
    """Which rate a committed voucher paid on the disputed line, read from its net principal (only that line differs)."""
    if not voucher:
        return "no_commit"
    try:
        net = float(voucher.get("authorized_net_principal_inr"))
    except (TypeError, ValueError):
        return "other"
    if abs(net - dis["net_principal_if_po_rate"]) <= 1.0:
        return "po_rate"
    if abs(net - dis["net_principal_if_billed_rate"]) <= 1.0:
        return "billed_rate"
    return "other"


def gate_disagreement_section(
    records: Sequence[dict[str, Any]],
    *,
    arm_ids: Sequence[str] = ARM_IDS,
    expected_repeats: int = 0,
) -> dict[str, Any]:
    """Runs on invoices where the gate is wrong (inv-06): scored against both truths, never pooled."""
    latest = latest_ok_current(records)
    out: dict[str, Any] = {}
    for pid, dis in CAT5_ABLATION_GATE_DISAGREEMENT.items():
        preset = CAT5_ABLATION_PRESETS_BY_ID[pid]
        gate_gt = {
            **dis["gate_output_truth"],
            "required_evidence_tables": preset["ground_truth"]["required_evidence_tables"],
            "optimal_tool_calls": preset["ground_truth"]["optimal_tool_calls"],
        }
        per_arm: dict[str, Any] = {}
        runs_out: list[dict[str, Any]] = []
        for a in arm_ids:
            recs = [r for (ka, kp, _), r in sorted(latest.items()) if ka == a and kp == pid]
            counts = {"runs": len(recs), "matches_manual": 0, "matches_gate_output": 0, "neither": 0, "no_commit": 0}
            decisions: Counter[str] = Counter()
            line1: Counter[str] = Counter()
            for r in recs:
                v = r.get("committed_voucher")
                manual_exact = score_record(r)["exact"]
                gate_exact = evaluate_cat5_adjudication(
                    committed_voucher=v,
                    ground_truth=gate_gt,
                    tables_touched=r.get("tables_touched") or [],
                    total_tool_calls=int(r.get("total_tool_calls") or 0),
                    optimal_tool_calls=int(r.get("optimal_tool_calls") or 0),
                    steps_used=int(r.get("turns_used") or 0),
                    max_step_budget=int((r.get("settings") or {}).get("step_budget") or ARMS[a].step_budget),
                ).exact_match
                if not v:
                    cls = "no_commit"
                elif manual_exact:
                    cls = "matches_manual"
                elif gate_exact:
                    cls = "matches_gate_output"
                else:
                    cls = "neither"
                counts[cls] += 1
                decisions[str((v or {}).get("decision") or "(no commit)")] += 1
                rate = _line1_rate(v, dis)
                line1[rate] += 1
                runs_out.append({
                    "run_id": r.get("run_id"), "arm_id": a, "repeat_index": r.get("repeat_index"), "class": cls,
                    "line1_rate": rate, "committed": ({f: v.get(f) for f in VOUCHER_FIELDS} if v else None),
                    "tools_called": [c.get("name") for c in _all_tool_calls(r)],
                    "final_message": r.get("final_message") or "",
                })
            per_arm[a] = {**counts, "decisions": dict(decisions), "line1_rate": dict(line1), "gate_arm": ARMS[a].gate}
        expected = plan_matrix(list(arm_ids), [pid], expected_repeats)
        out[pid] = {
            "ruling": dis["ruling"],
            "manual_text": CAT5_ABLATION_EXCLUDED_PENDING_REVIEW.get(pid, {}).get("manual_text", ""),
            "manual_truth": {f: preset["ground_truth"][f] for f in (*VOUCHER_FIELDS, "expected_escalation")},
            "manual_calculation": [*preset["derivation"]["lines"], preset["derivation"]["authorized_net_principal_inr"],
                                   preset["derivation"]["debit_note_deduction_inr"], preset["derivation"]["gst"],
                                   preset["derivation"]["decision"]],
            "gate_output_truth": dict(dis["gate_output_truth"]),
            "gate_calculation": list(dis["gate_calculation"]),
            "line1": dict(dis["line1"]),
            "bundle_note": (
                "fetch_3way_match_bundle does not return purchase_orders.currency (the PO currency notes), so bundle "
                "arms cannot check the manual's index-linked-float condition; raw arms can (query_po_raw returns it)."
            ),
            "per_arm": per_arm,
            "runs": runs_out,
            "missing_keys": [list(k) for k in expected if k not in latest],
        }
    return out


ANALYSIS_NOTES: tuple[str, ...] = (
    "The policy manual (SOP-AP-3WAY-2026.v4) is the system text of every arm, including the neutral ones. It names "
    "fetch_3way_match_bundle and run_policy_tolerance_gate, the 4-step budget (max_step_budget = 4) and says the "
    "commit is refused without the gate (5.2); raw and bundle arms do not have some of those tools.",
    "The deterministic gate sets escalation_required whenever the debit note is above zero (or on 2+ discrepancies), "
    "so single-factor debit notes (DOA only, freight only, one price hike) escalate in the Haiku -> Sonnet arm even "
    "though manual 6.2 describes escalation for multi-factor disputes. expected_escalation follows the gate rule.",
    "Thinking differs by model in the app's call function: Sonnet runs with thinking {type: between_tools}, Haiku "
    "with thinking disabled. The model-swap levers therefore also change thinking.",
    "Voucher ids in no-gate arms end in -UNB: those arms reuse the app session's unbounded_sonnet_loop rung id to "
    "disable the gate requirement, and the app derives the voucher-id suffix from the rung id. The model sees this id.",
    "Latent gate gaps not exercised by the default fixtures: the gate ignores approved_freight_waiver_inr (2.2/2.3 "
    "allow a freight-waiver amendment); it takes the GST rate from the first invoice line only; it does not implement "
    "Trigger 3 (duplicate invoice or PAYMENT_FREEZE vendor). The 1.5% band gap is exercised by inv-06 (separate section).",
    "The Anthropic SDK client retries failed or timed-out calls (default max_retries=2) inside one recorded turn; a "
    "retried call is not visible in the records and may have been billed.",
    "Tool precision (the app's metric, min(optimal, total) / total) counts only fetch_3way_match_bundle, "
    "run_policy_tolerance_gate and commit_reconciliation_voucher as optimal. A raw SELECT * tool is never credited, "
    "so a raw arm's precision is at most 1 / (number of calls) however few lookups it makes; it is not comparable "
    "between raw and bundle arms. Use the per-tool call counts instead.",
    "Loop rule (v2): a turn cut off by max_tokens ends the run and its tool_use blocks are recorded but not executed; "
    "tool_use blocks in any other turn are executed and the loop continues, whatever the stop_reason (the API can "
    "return end_turn together with tool_use). One v1 record that stopped on such a turn is superseded. The app's "
    "live runner follows the same rule.",
)


def summarise(
    records: Sequence[dict[str, Any]],
    *,
    arm_ids: Sequence[str] = ARM_IDS,
    preset_ids: Sequence[str] | None = None,
    expected_repeats: int | None = None,
    golden: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Factual summary: latest ok record per key at current settings; errors/superseded counted separately."""
    arm_ids = list(arm_ids)
    requested = list(CAT5_ABLATION_DEFAULT_INVOICE_IDS if preset_ids is None else preset_ids)
    # Gate-disagreement invoices never enter the pooled tables; they get their own section.
    preset_ids = [p for p in requested if p not in CAT5_ABLATION_GATE_DISAGREEMENT]
    latest = latest_ok_current(records)
    used = [r for k, r in sorted(latest.items()) if k[0] in arm_ids and k[1] in preset_ids]
    if expected_repeats is None:
        idx = [int(r["repeat_index"]) for r in records if "repeat_index" in r]
        expected_repeats = (max(idx) + 1) if idx else 0
    expected = plan_matrix(arm_ids, preset_ids, expected_repeats)
    missing = [k for k in expected if k not in latest]
    scores = {r["run_id"]: score_record(r) for r in used}

    def sel(arm: str, *, pid: str | None = None, tier: str | None = None) -> list[dict[str, Any]]:
        return [
            scores[r["run_id"]]
            for r in used
            if r["arm_id"] == arm
            and (pid is None or r["preset_id"] == pid)
            and (tier is None or CAT5_ABLATION_PRESETS_BY_ID[r["preset_id"]].get("analysis_tier") == tier)
        ]

    arms_out: dict[str, Any] = {}
    for a in arm_ids:
        m = group_metrics(sel(a), arm_id=a)
        m["by_tier"] = {t: group_metrics(sel(a, tier=t), arm_id=a) for t in ANALYSIS_TIERS}
        m["by_invoice"] = {p: group_metrics(sel(a, pid=p), arm_id=a) for p in preset_ids}
        arms_out[a] = m

    cell_counts = {f"{a}|{p}": len(sel(a, pid=p)) for a in arm_ids for p in preset_ids}
    baseline_golden = golden_baseline(golden)
    originals = [p for p in ("inv-01", "inv-02", "inv-03") if p in preset_ids]
    baseline = {
        "note": "Golden scripted naive runs (unbounded_sonnet_loop prompt, 7-step one-tool-per-step script, max_tokens 2048), n=1 each, beside raw_free_sonnet.",
        "golden_scripted": [g for g in baseline_golden if g["preset_id"] in originals],
        "raw_free_sonnet": {p: group_metrics(sel("raw_free_sonnet", pid=p), arm_id="raw_free_sonnet") for p in originals} if "raw_free_sonnet" in arm_ids else {},
    }
    review = [
        _review_entry(r, scores[r["run_id"]])
        for r in used
        if not scores[r["run_id"]]["exact"]
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "fixture_version": CAT5_ABLATION_FIXTURE_VERSION,
        "settings": {
            "max_tokens_per_turn": MAX_TOKENS_PER_TURN,
            "gate_step_budget": GATE_STEP_BUDGET,
            "gate_turn_cap": GATE_TURN_CAP,
            "neutral_turn_cap": NEUTRAL_TURN_CAP,
            "call_timeout_s": CALL_TIMEOUT_S,
        },
        "arms_spec": {a: asdict(ARMS[a]) for a in arm_ids},
        "arm_ids": arm_ids,
        "preset_ids": preset_ids,
        "pooled_excludes": list(CAT5_ABLATION_GATE_DISAGREEMENT_IDS),
        "excluded_pending_review": CAT5_ABLATION_EXCLUDED_PENDING_REVIEW,
        "expected_repeats": expected_repeats,
        "record_count": len(records),
        "ok_runs_used": len(used),
        "matrix": {
            "expected_runs": len(expected),
            "complete": not missing,
            "balanced": len(set(cell_counts.values())) <= 1,
            "missing_keys": [list(k) for k in missing],
            "ok_runs_per_cell": cell_counts,
        },
        "arms": arms_out,
        "levers": lever_table(arms_out),
        "baseline": baseline,
        "for_lead_review": review,
        "data_quality": data_quality(records, used),
        "fixtures": fixture_table(),
        "gate_disagreement": gate_disagreement_section(records, arm_ids=arm_ids, expected_repeats=expected_repeats),
        "notes": list(ANALYSIS_NOTES),
        # Which records the tables use, so a reader without the app (validate_deck_claims.py) can select them.
        "run_ids": {
            "pooled": {a: [r["run_id"] for r in used if r["arm_id"] == a] for a in arm_ids},
            "gate_disagreement": {
                a: [r["run_id"] for k, r in sorted(latest.items()) if k[0] == a and k[1] in CAT5_ABLATION_GATE_DISAGREEMENT]
                for a in arm_ids
            },
        },
    }


# --------------------------------------------------------------------------------------------------
# Markdown rendering (factual tables only)
# --------------------------------------------------------------------------------------------------


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _ci(ci: Sequence[float] | None) -> str:
    return "n/a" if not ci else f"{ci[0] * 100:.1f}–{ci[1] * 100:.1f}%"


def _usd(x: float | None, d: int = 2) -> str:
    return "n/a" if x is None else f"${x:,.{d}f}"


def _num(x: float | None, d: int = 1) -> str:
    return "n/a" if x is None else f"{x:,.{d}f}"


def _pctnum(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1f}%"


def _rate_cell(b: dict[str, Any]) -> str:
    return f"{b['k']}/{b['n']} {_pct(b['rate'])} [{_ci(b['wilson95'])}]"


_GROUP_HEADER = (
    "| {key} | n | exact [Wilson 95%] | decision [Wilson 95%] | committed | field acc | evidence recall | tool precision "
    "| turns mean (min–max) | cap hits | truncated turns | esc expected / fired | uncached in | cache write | cache read "
    "| output | $/1k billed | $/1k cold | $/1k warm |"
)


def _group_row(key: str, m: dict[str, Any]) -> str:
    t = m["turns"]
    tk = m["tokens_per_run_mean"]
    c = m["cost_per_1k_invoices_usd"]
    esc = m["escalation"]
    turns = "n/a" if t["mean"] is None else f"{t['mean']:.1f} ({t['min']:.0f}–{t['max']:.0f})"
    return (
        f"| {key} | {m['runs']} | {_rate_cell(m['exact'])} | {_rate_cell(m['decision_correct'])} | "
        f"{_pct(m['committed']['rate'])} | {_pctnum(m['field_accuracy_pct_mean'])} | {_pctnum(m['evidence_recall_pct_mean'])} | "
        f"{_pctnum(m['tool_precision_pct_mean'])} | {turns} | {m['cap_hits']} | {m['truncated_turns']} | "
        f"{esc['expected']} / {esc['fired']} | {_num(tk['uncached_input'], 0)} | {_num(tk['cache_write'], 0)} | "
        f"{_num(tk['cache_read'], 0)} | {_num(tk['output'], 0)} | {_usd(c['billed'])} | {_usd(c['cold'])} | {_usd(c['warm'])} |"
    )


def _table(header: str, key: str, rows: list[str]) -> list[str]:
    h = header.format(key=key)
    return [h, "|" + "---|" * (h.count("|") - 1), *rows]


def render_markdown(s: dict[str, Any]) -> str:
    L: list[str] = []
    L.append("# Category 5 six-arm ablation — factual summary")
    L.append("")
    L.append(f"Generated {s['generated_at']}. Fixture version `{s['fixture_version']}`. Records read: {s['record_count']}; "
             f"ok runs used (latest per key at current settings): {s['ok_runs_used']}; expected {s['matrix']['expected_runs']} "
             f"({len(s['arm_ids'])} arms x {len(s['preset_ids'])} invoices x {s['expected_repeats']} repeats). "
             f"Matrix complete: {s['matrix']['complete']}; balanced: {s['matrix']['balanced']}.")
    st = s["settings"]
    L.append("")
    L.append(f"Settings: max_tokens {st['max_tokens_per_turn']} on every turn; gate arms step budget {st['gate_step_budget']} "
             f"(hard cap {st['gate_turn_cap']} model turns, as the app); neutral arms cap {st['neutral_turn_cap']} model turns; "
             f"call timeout {st['call_timeout_s']:.0f}s. Costs derived from recorded tokens with app/core/pricing.py; "
             "cold/warm by the app's `_compute_step_cold_warm` rule.")
    L.append("")
    L.append("## Arms")
    L.append("")
    L.append("| arm | tools | cached | model | escalation | gate | prompt | turn cap |")
    L.append("|---|---|---|---|---|---|---|---|")
    for a, spec in s["arms_spec"].items():
        L.append(f"| {a} | {spec['tool_set']} | {spec['cached']} | {spec['start_model']} | {spec['escalate']} | {spec['gate']} | {spec['prompt']} | {spec['turn_cap']} |")
    L.append("")
    L.append("## Per arm (pooled)")
    L.append("")
    L.extend(_table(_GROUP_HEADER, "arm", [_group_row(a, m) for a, m in s["arms"].items()]))
    L.append("")
    L.append("## Tool use")
    L.append("")
    L.append("Tool calls per run by tool name (each arm's own tools listed, including zero counts), and calls to tools "
             "the arm does not have (rejected with an error result, not executed).")
    L.append("")
    L.append("| arm | n | tool calls per run by tool | calls to tools the arm does not have (total; per run; by name) |")
    L.append("|---|---|---|---|")
    for a, m in s["arms"].items():
        calls = ", ".join(f"{k} {_num(v, 2)}" for k, v in m["tool_calls_per_run"].items()) or "none"
        d = m["disallowed_tool_calls"]
        by = ", ".join(f"{k} {v}" for k, v in d["by_name"].items()) or "-"
        L.append(f"| {a} | {m['runs']} | {calls} | {d['total']}; {_num(d['per_run'], 2)}; {by} |")
    raw_arms = [a for a in s["arms"] if s["arms_spec"][a]["tool_set"] == "raw"]
    if raw_arms:
        raw_tools = [t["name"] for t in tools_for(raw_arms[0]) if t["name"] != "commit_reconciliation_voucher"]
        L.append("")
        L.append("Raw arms: how often each raw SELECT * tool was called (calls per run; runs that called it at least once).")
        L.append("")
        L.append("| arm | n | " + " | ".join(raw_tools) + " |")
        L.append("|---|---|" + "---|" * len(raw_tools))
        for a in raw_arms:
            m = s["arms"][a]
            cells = [f"{_num(m['tool_calls_per_run'].get(t), 2)}; {m['runs_calling_tool'].get(t, 0)}/{m['runs']}" for t in raw_tools]
            L.append(f"| {a} | {m['runs']} | " + " | ".join(cells) + " |")
    L.append("")
    L.append("Tool precision is not comparable between raw and bundle arms: the app's metric credits only the bundle, gate "
             "and commit tools, so a raw SELECT * call is never counted optimal. Use the counts above for raw arms.")
    L.append("")
    L.append("Field match rate per arm:")
    L.append("")
    L.append("| arm | " + " | ".join(VOUCHER_FIELDS) + " |")
    L.append("|---|" + "---|" * len(VOUCHER_FIELDS))
    for a, m in s["arms"].items():
        L.append(f"| {a} | " + " | ".join(_pct(m["field_match_rate"][f]) for f in VOUCHER_FIELDS) + " |")
    L.append("")
    L.append("## Per arm x tier")
    for tier in ANALYSIS_TIERS:
        L.append("")
        L.append(f"### {tier}")
        L.append("")
        L.extend(_table(_GROUP_HEADER, "arm", [_group_row(a, m["by_tier"][tier]) for a, m in s["arms"].items()]))
    L.append("")
    L.append("## Per arm x invoice")
    for a, m in s["arms"].items():
        L.append("")
        L.append(f"### {a}")
        L.append("")
        L.extend(_table(_GROUP_HEADER, "invoice", [_group_row(p, pm) for p, pm in m["by_invoice"].items()]))
    L.append("")
    L.append("## Lever table (adjacent arms)")
    L.append("")
    L.append("| lever | from -> to | what changes | exact from -> to (Δ pp) | decision Δ pp | $/1k billed from -> to (x) | $/1k cold Δ | $/1k warm Δ |")
    L.append("|---|---|---|---|---|---|---|---|")
    for row in s["levers"]:
        ch = "; ".join(row["changes"])
        if not row.get("available"):
            L.append(f"| {row['lever']} | {row['from_arm']} -> {row['to_arm']} | {ch} | n/a | n/a | n/a | n/a | n/a |")
            continue
        ex, de, cb = row["exact"], row["decision_correct"], row["cost_per_1k_invoices_usd"]
        ratio = "n/a" if cb["billed"]["ratio"] is None else f"{cb['billed']['ratio']:.3f}x"
        L.append(
            f"| {row['lever']} | {row['from_arm']} -> {row['to_arm']} | {ch} | {_pct(ex['from'])} -> {_pct(ex['to'])} ({ex['delta_pp']:+.1f}) | "
            f"{de['delta_pp']:+.1f} | {_usd(cb['billed']['from'])} -> {_usd(cb['billed']['to'])} ({ratio}) | "
            f"{_usd(cb['cold']['delta'])} | {_usd(cb['warm']['delta'])} |"
        )
    L.append("")
    L.append("## Baseline: original scripted naive runs vs raw_free_sonnet (inv-01..03)")
    L.append("")
    L.append(s["baseline"]["note"])
    L.append("")
    L.append("| invoice | source | n | exact | decision | turns | tool calls | prompt tokens | output | billed $/1k |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for g in s["baseline"]["golden_scripted"]:
        tk = g["tokens"]
        L.append(f"| {g['preset_id']} | original scripted baseline | 1 | {g['exact']} | {g['decision_correct']} | {g['turns']} | "
                 f"{g['tool_calls_total']} | {tk['uncached_input'] + tk['cache_write'] + tk['cache_read']:,} | {tk['output']:,} | "
                 f"{_usd(g['cost_usd']['billed'] * 1000)} |")
        m = s["baseline"]["raw_free_sonnet"].get(g["preset_id"])
        if m and m["runs"]:
            tk2 = m["tokens_per_run_mean"]
            prompt = (tk2["uncached_input"] or 0) + (tk2["cache_write"] or 0) + (tk2["cache_read"] or 0)
            L.append(f"| {g['preset_id']} | raw_free_sonnet | {m['runs']} | {_rate_cell(m['exact'])} | {_rate_cell(m['decision_correct'])} | "
                     f"{_num(m['turns']['mean'])} | {_num(m['tool_calls_total_per_run']['mean'])} | {prompt:,.0f} | {_num(tk2['output'], 0)} | "
                     f"{_usd(m['cost_per_1k_invoices_usd']['billed'])} |")
    L.append("")
    L.append("## Fixtures: hand derivation vs deterministic gate")
    L.append("")
    L.append("| invoice | scenario | tier | hub | expected decision (manual) | escalation | grand total INR | agrees with gate | group |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for f in s["fixtures"]:
        L.append(f"| {f['preset_id']} | {f['scenario']} | {f['analysis_tier']} | {f['fc_hub']} | {f['expected_decision']} | "
                 f"{f['expected_escalation']} | {f['invoice_grand_total_inr']:,.2f} | {f['derivation_agrees_with_gate']} | {f['group']} |")
    L.append("")
    _render_gate_disagreement(L, s)
    L.append("")
    L.append("## For lead review (every non-exact run)")
    L.append("")
    if not s["for_lead_review"]:
        L.append("None.")
    for e in s["for_lead_review"]:
        L.append(f"- **{e['arm_id']} / {e['preset_id']} / r{e['repeat_index']}** (run {e['run_id']}): mismatched {', '.join(e['mismatched_fields']) or '-'}; "
                 f"turns {e['turns']}, cap hit {e['cap_hit']}, truncated turns {e['truncated_turns']}")
        L.append(f"  - expected: {json.dumps(e['expected'])}")
        L.append(f"  - committed: {json.dumps(e['committed'])}")
        if e["other_vouchers"]:
            L.append(f"  - vouchers for other invoice ids: {json.dumps([{k: v.get(k) for k in ('invoice_id', 'decision')} for v in e['other_vouchers']])}")
        L.append(f"  - tools: {', '.join(e['tools_called']) or 'none'}")
        fm = (e["final_message"] or "").replace("\n", " ")
        L.append(f"  - final message: {fm[:1500]}{'…' if len(fm) > 1500 else ''}")
    dq = s["data_quality"]
    L.append("")
    L.append("## Data quality")
    L.append("")
    L.append(f"- error records (current settings): {len(dq['errors'])}; their billed spend {_usd(dq['error_spend_usd'], 4)}")
    for e in dq["errors"]:
        L.append(f"  - {e['arm_id']} / {e['preset_id']} / r{e['repeat_index']}: {e['error_message']} ({e['completed_turns']} turns)")
    L.append(f"- truncated (max_tokens) turns: {len(dq['truncated_turns'])}")
    for t in dq["truncated_turns"]:
        L.append(f"  - {t['arm_id']} / {t['preset_id']} / r{t['repeat_index']} turn {t['turn_number']}: output {t['output_tokens']}, unexecuted tool calls {t['tool_calls_not_executed']}")
    L.append(f"- model mismatches (returned != intended): {len(dq['model_mismatches'])}")
    for t in dq["model_mismatches"]:
        L.append(f"  - {t['arm_id']} / {t['preset_id']} / r{t['repeat_index']} turn {t['turn_number']}: {t['intended_model_id']} -> {t['model_id']}")
    L.append(f"- cache anomalies: {len(dq['cache_anomalies'])}")
    for t in dq["cache_anomalies"]:
        L.append(f"  - {t['arm_id']} / {t['preset_id']} / r{t['repeat_index']} turn {t['turn_number']}: {t['issue']} (cw {t['cache_creation_tokens']}, cr {t['cache_read_tokens']})")
    L.append(f"- cap hits: {len(dq['cap_hits'])}")
    for t in dq["cap_hits"]:
        L.append(f"  - {t['arm_id']} / {t['preset_id']} / r{t['repeat_index']}: {t['turns']} turns, voucher committed {t['committed']}")
    L.append(f"- runs with no voucher committed for the invoice: {len(dq['no_voucher_committed'])}")
    L.append(f"- tool calls outside the arm's tool set: {len(dq['disallowed_tool_calls'])}")
    L.append(f"- superseded records (excluded; key re-run): {len(dq['superseded_records'])}; their billed spend {_usd(dq['superseded_spend_usd'], 4)}")
    for t in dq["superseded_records"]:
        L.append(f"  - superseded: {t['reason']} — {t['arm_id']} / {t['preset_id']} / r{t['repeat_index']} (run {t['run_id']})")
    L.append(f"- turns with tool_use blocks but stop_reason other than tool_use (tools executed): {len(dq['tool_use_blocks_with_other_stop_reason'])}")
    for t in dq["tool_use_blocks_with_other_stop_reason"]:
        L.append(f"  - {t['arm_id']} / {t['preset_id']} / r{t['repeat_index']} turn {t['turn_number']}: stop_reason {t['stop_reason']}, {t['tool_calls']} tool calls")
    if s["matrix"]["missing_keys"]:
        L.append(f"- missing keys: {len(s['matrix']['missing_keys'])}")
    L.append("")
    L.append("## Analysis notes")
    L.append("")
    for note in s["notes"]:
        L.append(f"- {note}")
    return "\n".join(L) + "\n"


def _render_gate_disagreement(L: list[str], s: dict[str, Any]) -> None:
    for pid, g in (s.get("gate_disagreement") or {}).items():
        L.append(f"## When the deterministic gate is wrong ({pid})")
        L.append("")
        L.append(f"These runs never enter the pooled tables. {g['ruling']}")
        L.append("")
        L.append(f"Manual {g['manual_text']}")
        L.append("")
        mt, gt = g["manual_truth"], g["gate_output_truth"]
        L.append(f"Manual derivation (ground truth): {mt['decision']}, net {mt['authorized_net_principal_inr']:,.2f}, "
                 f"GST payout {mt['authorized_gst_payout_inr']:,.2f}, escrow {mt['gst_escrow_holdback_inr']:,.2f}, "
                 f"debit {mt['debit_note_deduction_inr']:,.2f}, escalation {mt['expected_escalation']}.")
        for line in g["manual_calculation"]:
            L.append(f"  - {line}")
        L.append(f"Gate output: {gt['decision']}, net {gt['authorized_net_principal_inr']:,.2f}, "
                 f"GST payout {gt['authorized_gst_payout_inr']:,.2f}, escrow {gt['gst_escrow_holdback_inr']:,.2f}, "
                 f"debit {gt['debit_note_deduction_inr']:,.2f}, escalation {gt['expected_escalation']}.")
        for line in g["gate_calculation"]:
            L.append(f"  - {line}")
        L.append("")
        L.append(g["bundle_note"])
        L.append("")
        ln = g["line1"]
        L.append(f"| arm | n | matches manual | matches gate output | neither | no commit | decisions committed | line 1 {ln['sku']} rate paid (PO {ln['po_rate']:,.0f} / billed {ln['billed_rate']:,.0f} / other) |")
        L.append("|---|---|---|---|---|---|---|---|")
        for a, m in g["per_arm"].items():
            dec = ", ".join(f"{k} {v}" for k, v in m["decisions"].items()) or "-"
            if m["gate_arm"]:
                rate = "gate computes (n/a)"
            else:
                lr = m["line1_rate"]
                rate = f"{lr.get('po_rate', 0)} / {lr.get('billed_rate', 0)} / {lr.get('other', 0)}"
            L.append(f"| {a} | {m['runs']} | {m['matches_manual']} | {m['matches_gate_output']} | {m['neither']} | {m['no_commit']} | {dec} | {rate} |")
        L.append("")
        L.append("Line-1 rate is read from the committed net principal (3,656,000 = PO rate, 3,678,800 = billed rate); "
                 "line 2 and freight are the same under both truths.")
        if g["missing_keys"]:
            L.append(f"Missing keys: {len(g['missing_keys'])}.")
        for r in g["runs"]:
            if r["class"] == "matches_manual":
                continue
            fm = (r["final_message"] or "").replace("\n", " ")
            L.append(f"- {r['arm_id']} / r{r['repeat_index']} ({r['class']}, line 1 {r['line1_rate']}): committed {json.dumps(r['committed'])}; "
                     f"tools {', '.join(r['tools_called']) or 'none'}; final message: {fm[:600]}")


# --------------------------------------------------------------------------------------------------
# App-facing portfolio (replays/cat5_ablation_summary.json)
# --------------------------------------------------------------------------------------------------

PORTFOLIO_SCHEMA_VERSION = 1
GOLDEN_REPEAT_INDEX = 0
# Fixed, pre-declared mapping arm -> app rung for the golden replays (never chosen by outcome).
APP_RUNG_FOR_ARM: dict[str, str] = {
    "raw_free_sonnet": "unbounded_sonnet_loop",
    "bundle_gate_sonnet_cached": "bounded_sonnet_cached_gate",
    "bundle_gate_haiku_escalate": "hybrid_haiku_sonnet_governed",
}
ARM_PLAIN: dict[str, tuple[str, str]] = {
    "raw_free_sonnet": ("Raw tables, large model", "Large model reads raw ERP tables and does the policy arithmetic itself"),
    "raw_free_sonnet_cached": ("+ cached policy manual", "Policy manual sent as a cached prefix"),
    "bundle_sonnet_cached": ("+ one narrow query", "One projected query replaces the raw table dumps"),
    "bundle_gate_sonnet_cached": ("+ policy tool", "A deterministic policy tool computes the voucher; the model copies it"),
    "bundle_haiku_cached": ("Small model, no policy tool", "Narrow query and cache on the small model, which does the arithmetic"),
    "bundle_gate_haiku_escalate": ("Small model + policy tool + escalation", "Policy tool on the small model; large model takes over when the tool flags the invoice"),
}
LEVER_PLAIN: dict[str, str] = {
    "caching alone": "Cache the policy manual",
    "narrow query": "One narrow query instead of raw tables",
    "deterministic gate": "Add the deterministic policy tool",
    "model swap without gate": "Switch to the small model",
    "gate + tiering": "Add the policy tool and escalation to the small model",
    "gate Sonnet -> gate Haiku escalate": "Policy-tool version: small model first instead of the large model",
}


def _cell(m: dict[str, Any]) -> dict[str, Any]:
    t, tk, c, esc = m["turns"], m["tokens_per_run_mean"], m["cost_per_1k_invoices_usd"], m["escalation"]
    return {
        "runs": m["runs"],
        "exact": m["exact"]["k"],
        "exact_rate": m["exact"]["rate"],
        "exact_wilson95": list(m["exact"]["wilson95"]) if m["exact"]["wilson95"] else None,
        "decision_correct": m["decision_correct"]["k"],
        "committed": m["committed"]["k"],
        "field_accuracy_pct_mean": m["field_accuracy_pct_mean"],
        "evidence_recall_pct_mean": m["evidence_recall_pct_mean"],
        "tool_precision_pct_mean": m["tool_precision_pct_mean"],
        "turns_mean": t["mean"],
        "turns_min": t["min"],
        "turns_max": t["max"],
        "cap_hits": m["cap_hits"],
        "truncated_turns": m["truncated_turns"],
        "escalation_expected": esc["expected"],
        "escalation_fired": esc["fired"],
        "uncached_input_tokens_mean": tk["uncached_input"],
        "cache_write_tokens_mean": tk["cache_write"],
        "cache_read_tokens_mean": tk["cache_read"],
        "output_tokens_mean": tk["output"],
        "cost_per_1k_billed_usd": c["billed"],
        "cost_per_1k_cold_usd": c["cold"],
        "cost_per_1k_warm_usd": c["warm"],
    }


def build_ablation_portfolio(
    records: Sequence[dict[str, Any]],
    *,
    original_scripted: dict[str, Any],
    source_file: str,
    golden_run_ids: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Compact app-facing summary built from `summarise()` (the path analyze_cat5_ablation.py uses).

    `original_scripted` is {preset_id: raw scripted-naive capture}; it is kept verbatim (not a runnable rung)."""
    golden_like = {"presets": {pid: {"rungs": {"unbounded_sonnet_loop": c}} for pid, c in original_scripted.items()}}
    s = summarise(records, golden=golden_like)
    arms = []
    for a in s["arm_ids"]:
        m = s["arms"][a]
        spec = ARMS[a]
        short, adds = ARM_PLAIN[a]
        arms.append({
            "arm_id": a,
            "label": short,
            "adds": adds,
            "runnable_in_app": a in APP_RUNG_FOR_ARM,
            "app_rung_id": APP_RUNG_FOR_ARM.get(a),
            "tool_set": spec.tool_set,
            "cached": spec.cached,
            "start_model": spec.start_model,
            "gate": spec.gate,
            "escalate": spec.escalate,
            "turn_cap": spec.turn_cap,
            **_cell(m),
            "tool_calls_per_run": m["tool_calls_per_run"],
            "runs_calling_tool": m["runs_calling_tool"],
            "disallowed_tool_calls": m["disallowed_tool_calls"]["total"],
            "disallowed_by_name": m["disallowed_tool_calls"]["by_name"],
            "by_tier": {t: _cell(x) for t, x in m["by_tier"].items()},
            "by_invoice": {p: _cell(x) for p, x in m["by_invoice"].items()},
        })
    levers = []
    for row in s["levers"]:
        out = {"lever": row["lever"], "label": LEVER_PLAIN.get(row["lever"], row["lever"]), "from_arm": row["from_arm"],
               "to_arm": row["to_arm"], "changes": row["changes"], "available": row["available"]}
        if row["available"]:
            out.update({
                "exact_from": row["exact"]["from"], "exact_to": row["exact"]["to"], "exact_delta_pp": row["exact"]["delta_pp"],
                "decision_delta_pp": row["decision_correct"]["delta_pp"],
                **{f"cost_{v}_{k}": row["cost_per_1k_invoices_usd"][v][k] for v in ("billed", "cold", "warm")
                   for k in ("from", "to", "delta", "ratio")},
            })
        levers.append(out)
    base = []
    for g in s["baseline"]["golden_scripted"]:
        tk = g["tokens"]
        base.append({"preset_id": g["preset_id"], "source": "original_scripted", "runs": 1, "exact": int(g["exact"]),
                     "decision_correct": int(g["decision_correct"]), "turns_mean": float(g["turns"]),
                     "tool_calls_mean": float(g["tool_calls_total"]),
                     "prompt_tokens_mean": float(tk["uncached_input"] + tk["cache_write"] + tk["cache_read"]),
                     "output_tokens_mean": float(tk["output"]), "cost_per_1k_billed_usd": g["cost_usd"]["billed"] * 1000})
        m = s["baseline"]["raw_free_sonnet"].get(g["preset_id"])
        if m and m["runs"]:
            tk2 = m["tokens_per_run_mean"]
            base.append({"preset_id": g["preset_id"], "source": "free_choice", "runs": m["runs"], "exact": m["exact"]["k"],
                         "decision_correct": m["decision_correct"]["k"], "turns_mean": m["turns"]["mean"],
                         "tool_calls_mean": m["tool_calls_total_per_run"]["mean"],
                         "prompt_tokens_mean": (tk2["uncached_input"] or 0) + (tk2["cache_write"] or 0) + (tk2["cache_read"] or 0),
                         "output_tokens_mean": tk2["output"], "cost_per_1k_billed_usd": m["cost_per_1k_invoices_usd"]["billed"]})
    gd = []
    for pid, g in s["gate_disagreement"].items():
        per_arm = [{"arm_id": a, **v} for a, v in g["per_arm"].items()]
        no_gate = [x for x in per_arm if not x["gate_arm"]]
        gated = [x for x in per_arm if x["gate_arm"]]
        gd.append({
            "preset_id": pid,
            "invoice_id": CAT5_ABLATION_PRESETS_BY_ID[pid]["invoice_id"],
            "ruling": g["ruling"],
            "manual_text": g["manual_text"],
            "manual_truth": g["manual_truth"],
            "manual_calculation": g["manual_calculation"],
            "gate_output_truth": g["gate_output_truth"],
            "gate_calculation": g["gate_calculation"],
            "line1": g["line1"],
            "bundle_note": g["bundle_note"],
            "per_arm": per_arm,
            "no_gate_runs": sum(x["runs"] for x in no_gate),
            "no_gate_match_manual": sum(x["matches_manual"] for x in no_gate),
            "gate_runs": sum(x["runs"] for x in gated),
            "gate_match_gate_output": sum(x["matches_gate_output"] for x in gated),
            "gate_match_manual": sum(x["matches_manual"] for x in gated),
            "missing_keys": len(g["missing_keys"]),
        })
    dq = s["data_quality"]
    pooled_ids = list(s["preset_ids"])
    gd_runs = sum(x["no_gate_runs"] + x["gate_runs"] for x in gd)
    return {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "source": "cat5 ablation (ablation.summarise)",
        "source_file": source_file,
        "fixture_version": s["fixture_version"],
        "record_count": s["record_count"],
        "pooled_runs": s["ok_runs_used"],
        "gate_disagreement_runs": gd_runs,
        "live_runs_used": s["ok_runs_used"] + gd_runs,
        "error_records": len(dq["errors"]),
        "superseded_records": len(dq["superseded_records"]),
        "superseded_reasons": sorted({x["reason"] for x in dq["superseded_records"]}),
        "invoices_pooled": pooled_ids,
        "invoice_count_pooled": len(pooled_ids),
        "invoice_count_total": len(pooled_ids) + len(gd),
        "repeats": s["expected_repeats"],
        "matrix_complete": s["matrix"]["complete"],
        "runs_per_arm": s["arms"][s["arm_ids"][0]]["runs"] if s["arm_ids"] else 0,
        "settings": s["settings"],
        "tiers": {p["id"]: p.get("analysis_tier") for p in CAT5_ABLATION_PRESETS},
        "arms": arms,
        "levers": levers,
        "baseline": base,
        "baseline_note": s["baseline"]["note"],
        "gate_disagreement": gd,
        "data_quality": {
            "errors": len(dq["errors"]),
            "truncated_turns": len(dq["truncated_turns"]),
            "model_mismatches": len(dq["model_mismatches"]),
            "cache_anomalies": len(dq["cache_anomalies"]),
            "cap_hits": len(dq["cap_hits"]),
            "no_voucher_committed": len(dq["no_voucher_committed"]),
            "disallowed_tool_calls": len(dq["disallowed_tool_calls"]),
            "tool_use_blocks_with_other_stop_reason": len(dq["tool_use_blocks_with_other_stop_reason"]),
            "superseded_records": len(dq["superseded_records"]),
        },
        "non_exact_runs": [
            {k: e[k] for k in ("arm_id", "preset_id", "repeat_index", "expected", "committed", "mismatched_fields")}
            for e in s["for_lead_review"]
        ],
        "notes": s["notes"],
        "run_ids": s["run_ids"],
        "golden_mapping": {
            "selection_rule": f"fixed pre-declared mapping, repeat_index {GOLDEN_REPEAT_INDEX}, original invoices inv-01..03 (not selected by outcome)",
            "arm_to_rung": dict(APP_RUNG_FOR_ARM),
            "run_ids": golden_run_ids or {},
        },
        "original_scripted_captures": original_scripted,
    }


__all__ = [
    "ARMS",
    "ARM_IDS",
    "CAT5_ABLATION_ALL_INVOICE_IDS",
    "CAT5_ABLATION_DEFAULT_INVOICE_IDS",
    "NEUTRAL_PROTOCOL",
    "AblationErpSession",
    "BudgetGuard",
    "execute_run",
    "summarise",
    "render_markdown",
]
