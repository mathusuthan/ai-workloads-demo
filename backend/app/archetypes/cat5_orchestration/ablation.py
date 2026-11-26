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
# Recorded only (not compared for superseding): tool_use blocks run unless the turn hit max_tokens.
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
        # raw_free_sonnet on Haiku: same tools, neutral protocol, no cache, no policy tool, 12-turn cap. With no policy
        # tool nothing can flag escalation, so the run stays on Haiku. App rung 4 (unbounded_haiku_loop) runs the same.
        ArmSpec("raw_free_haiku", "raw", False, HAIKU_MODEL_ID, False, False, "neutral",
                "unbounded_haiku_loop", NEUTRAL_TURN_CAP, NEUTRAL_TURN_CAP, "model",
                "5 raw SELECT * tools + commit; no cache; Haiku; neutral protocol"),
    )
}
# The deck's improvement, without and with, on two model set-ups (the 2x2 every display shows): rows without / with
# (the free-choice raw-table loop; the 4-step budget + deterministic policy tool, with one narrow query and the cached
# policy manual), columns Sonnet / Haiku (Haiku alone without the lever; Haiku-first escalating to Sonnet with it).
ARM_IDS: tuple[str, ...] = ("raw_free_sonnet", "raw_free_haiku", "bundle_gate_sonnet_cached", "bundle_gate_haiku_escalate")
# Single levers tried on the way (valid runs kept in experiments/cat5_ablation/other_levers/, not displayed).
OTHER_LEVER_ARM_IDS: tuple[str, ...] = ("raw_free_sonnet_cached", "bundle_sonnet_cached", "bundle_haiku_cached")

def _arm(arm_id: str) -> ArmSpec:
    try:
        return ARMS[arm_id]
    except KeyError:
        raise ValueError(f"Unknown Cat 5 ablation arm `{arm_id}`; expected one of {list(ARMS)}") from None


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

    def __init__(
        self,
        *,
        rung_id: str,
        extra_rows: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        super().__init__(rung_id=rung_id)
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


_REPLAY_CACHE: dict[str, bool] = {}


def record_tool_outputs_current(record: dict[str, Any]) -> bool:
    """Every executed tool call in the record, replayed in order on a fresh ERP session of the arm's kind, returns the
    bytes it returned when recorded (its result_sha256): the policy tool, the narrow query, the raw queries and the
    commit alike. A record made while any tool returned something else is stale. True for a run without tool calls."""
    arm = ARMS.get(str(record.get("arm_id")))
    if arm is None:
        return False
    calls = [
        (c.get("name"), c.get("input"), c.get("result_sha256"))
        for t in record.get("turns") or []
        for c in t.get("tool_calls") or []
        if c.get("executed")
    ]
    key = _sha(json.dumps([arm.session_rung_id, calls], sort_keys=True, default=str))
    if key not in _REPLAY_CACHE:
        session = AblationErpSession(rung_id=arm.session_rung_id)
        try:
            ok = True
            for name, inp, sha in calls:
                if _sha(session.execute_tool(str(name), dict(inp or {}))[0]) != sha:
                    ok = False
                    break
        finally:
            session.close()
        _REPLAY_CACHE[key] = ok
    return _REPLAY_CACHE[key]


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


def record_is_current(record: dict[str, Any]) -> bool:
    """An ok record valid under the current settings and loop rule whose every tool call returned what that tool
    returns now (`record_tool_outputs_current`)."""
    return record.get("status") == "ok" and is_current_settings(record) and record_tool_outputs_current(record)


def select_pending(planned: Iterable[RunKey], existing: Iterable[dict[str, Any]]) -> list[RunKey]:
    """A key is done only with a current record (see `record_is_current`)."""
    done = {record_key(r) for r in existing if record_is_current(r)}
    return [k for k in planned if k not in done]


def latest_ok_current(records: Iterable[dict[str, Any]]) -> dict[RunKey, dict[str, Any]]:
    out: dict[RunKey, dict[str, Any]] = {}
    for r in records:
        if record_is_current(r):
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
        hard_stop = preset.get("analysis_tier") == "hard_stop"
        same = [
            s for pid, s in by_preset.items()
            if bool(CAT5_ABLATION_PRESETS_BY_ID[pid]["ground_truth"]["expected_escalation"])
            == bool(preset["ground_truth"]["expected_escalation"])
            and (CAT5_ABLATION_PRESETS_BY_ID[pid].get("analysis_tier") == "hard_stop") == hard_stop
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
    esc_expected = bool(preset["ground_truth"].get("expected_escalation"))
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
        "escalation_expected": esc_expected,
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


def data_quality(used: Sequence[dict[str, Any]]) -> dict[str, int]:
    """Counts over the records the tables use."""
    truncated = mism = cache = disallowed = stop_other = 0
    for r in used:
        cached = bool((r.get("arm") or {}).get("cached"))
        seen: set[str] = set()
        for t in r.get("turns") or []:
            truncated += t.get("stop_reason") == "max_tokens"
            mism += t.get("model_id") != t.get("intended_model_id")
            cw, cr = int(t.get("cache_creation_tokens") or 0), int(t.get("cache_read_tokens") or 0)
            mid = str(t.get("model_id"))
            first = mid not in seen
            seen.add(mid)
            cache += bool((not cached and (cw or cr)) or (cached and cw + cr == 0) or (cached and first and cr > 0)
                          or (cached and not first and cr == 0))
            disallowed += sum(1 for c in t.get("tool_calls") or [] if c.get("rejected_reason"))
            stop_other += bool(t.get("tool_use_with_stop_reason"))
    return {
        "truncated_turns": truncated,
        "model_mismatches": mism,
        "cache_anomalies": cache,
        "cap_hits": sum(1 for r in used if r.get("cap_hit")),
        "no_voucher_committed": sum(1 for r in used if not r.get("committed_voucher")),
        "disallowed_tool_calls": disallowed,
        "tool_use_blocks_with_other_stop_reason": stop_other,
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
                "escalation_derivation": p.get("escalation_derivation"),
                "invoice_grand_total_inr": p["invoice_grand_total_inr"],
                "source": p.get("source"),
                "derivation_agrees_with_gate": cmp["agree"],
                "differences": cmp["differences"],
            }
        )
    return rows


ANALYSIS_NOTES: tuple[str, ...] = (
    "Without: the free-choice loop over the five raw SELECT * tools (no step budget beyond a 12-turn safety cap, no "
    "policy tool, no prompt cache), on Sonnet and on Haiku; the Haiku version has no escalation path, since only the "
    "policy tool can flag one. With: a 4-step budget and the deterministic policy tool "
    "(run_policy_tolerance_gate; the commit is refused until it has run), and the with-design also uses one narrow "
    "query (fetch_3way_match_bundle) in place of the raw tables and sends the policy manual as a cached prefix, so the "
    "difference is not the budget and the tool alone.",
    "The policy manual (SOP-AP-3WAY-2026.v4) is the system text of every version. Both without-versions run "
    "the free-choice protocol; the with-versions run the app's rung-2 and rung-3 prompts unchanged.",
    "Escalation (Haiku-first version): the run switches to Sonnet from the next turn when the policy tool sets "
    "escalation_required, which it does only for a multi-factor commercial dispute (two or more of: partial DOA or "
    "short receipt, signed contract amendment, unauthorized line price rise, disallowed freight; manual 6.2). "
    "Expected escalations: inv-02 and inv-12.",
    "Thinking differs by model in the app's call function: Sonnet runs with thinking {type: between_tools}, Haiku "
    "with thinking disabled.",
    "Each cached run starts with its own nonce line, so it writes the cache on its first turn and reads it after "
    "(cold cache per run). Costs are derived from recorded tokens with app/core/pricing.py; cold/warm by the app's "
    "_compute_step_cold_warm rule.",
    "Loop rule: a turn cut off by max_tokens ends the run and its tool_use blocks are recorded but not executed; "
    "tool_use blocks in any other turn are executed and the loop continues, whatever the stop_reason.",
    "Voucher ids in the without-versions end in -UNB: they use the app session's unbounded_sonnet_loop and "
    "unbounded_haiku_loop rung ids, from which the app derives the voucher-id suffix.",
    "Tool precision (the app's metric) credits only the narrow query, the policy tool and the commit, so a raw "
    "SELECT * call is never counted optimal; it is not comparable between the without- and with-versions.",
    "The Anthropic SDK client retries failed or timed-out calls (default max_retries=2) inside one recorded turn; a "
    "retried call is not visible in the records and may have been billed.",
    "Limits: 12 invoices x 3 runs per version; the invoices test simple arithmetic (quantities x rates, a GST split, "
    "a debit note).",
)


def summarise(
    records: Sequence[dict[str, Any]],
    *,
    arm_ids: Sequence[str] = ARM_IDS,
    preset_ids: Sequence[str] | None = None,
    expected_repeats: int | None = None,
) -> dict[str, Any]:
    """Factual summary: latest current record per key (see `record_is_current`); keys without one are pending."""
    arm_ids = list(arm_ids)
    preset_ids = list(CAT5_ABLATION_DEFAULT_INVOICE_IDS if preset_ids is None else preset_ids)
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
        pend = [k for k in missing if k[0] == a]
        m["pending"] = {"runs": len(pend), "invoices": sorted({k[1] for k in pend})}
        arms_out[a] = m

    cell_counts = {f"{a}|{p}": len(sel(a, pid=p)) for a in arm_ids for p in preset_ids}
    notes = list(ANALYSIS_NOTES)
    review = [_review_entry(r, scores[r["run_id"]]) for r in used if not scores[r["run_id"]]["exact"]]
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
        "expected_repeats": expected_repeats,
        "record_count": len(records),
        "ok_runs_used": len(used),
        "matrix": {
            "expected_runs": len(expected),
            "complete": not missing,
            "balanced": len(set(cell_counts.values())) <= 1,
            "pending_keys": [list(k) for k in missing],
            "ok_runs_per_cell": cell_counts,
        },
        "arms": arms_out,
        "non_exact_runs": review,
        "data_quality": data_quality(used),
        "fixtures": fixture_table(),
        "notes": notes,
        # Which records the tables use, so a reader without the app (validate_deck_claims.py) can select them.
        "run_ids": {"pooled": {a: [r["run_id"] for r in used if r["arm_id"] == a] for a in arm_ids}},
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
    if not m["runs"]:
        return f"| {key} | 0 | pending |" + " |" * (_GROUP_HEADER.count("|") - 4)
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
    L.append("# Category 5: 4-step budget + deterministic policy tool, without and with")
    L.append("")
    L.append(f"Generated {s['generated_at']}. Fixture version `{s['fixture_version']}`. Runs used: {s['ok_runs_used']} of "
             f"{s['matrix']['expected_runs']} ({len(s['arm_ids'])} versions x {len(s['preset_ids'])} invoices x "
             f"{s['expected_repeats']} runs).")
    pend = s["matrix"]["pending_keys"]
    if pend:
        by_arm: dict[str, list[str]] = {}
        for a, p, _r in pend:
            by_arm.setdefault(a, []).append(p)
        L.append("")
        L.append(f"Pending (not run yet): {len(pend)} runs — " + "; ".join(
            f"{a}: {', '.join(sorted(set(ps)))} ({len(ps)} runs)" for a, ps in by_arm.items()) + ".")
    st = s["settings"]
    L.append("")
    L.append(f"Settings: max_tokens {st['max_tokens_per_turn']} on every turn; with-versions step budget {st['gate_step_budget']} "
             f"(hard cap {st['gate_turn_cap']} model turns, as the app); without-version safety cap {st['neutral_turn_cap']} model turns; "
             f"call timeout {st['call_timeout_s']:.0f}s.")
    L.append("")
    L.append("## Versions")
    L.append("")
    L.append("| version | tools | cached | model | escalation | policy tool | prompt | turn cap |")
    L.append("|---|---|---|---|---|---|---|---|")
    for a, spec in s["arms_spec"].items():
        L.append(f"| {a} | {spec['tool_set']} | {spec['cached']} | {spec['start_model']} | {spec['escalate']} | {spec['gate']} | {spec['prompt']} | {spec['turn_cap']} |")
    L.append("")
    L.append("## Without and with (all invoices)")
    L.append("")
    L.extend(_table(_GROUP_HEADER, "version", [_group_row(a, m) for a, m in s["arms"].items()]))
    L.append("")
    L.append("Field match rate per version:")
    L.append("")
    L.append("| version | " + " | ".join(VOUCHER_FIELDS) + " |")
    L.append("|---|" + "---|" * len(VOUCHER_FIELDS))
    for a, m in s["arms"].items():
        L.append(f"| {a} | " + " | ".join(_pct(m["field_match_rate"][f]) for f in VOUCHER_FIELDS) + " |")
    L.append("")
    L.append("## By tier")
    for tier in ANALYSIS_TIERS:
        L.append("")
        L.append(f"### {tier}")
        L.append("")
        L.extend(_table(_GROUP_HEADER, "version", [_group_row(a, m["by_tier"][tier]) for a, m in s["arms"].items()]))
    L.append("")
    L.append("## By invoice")
    for a, m in s["arms"].items():
        L.append("")
        L.append(f"### {a}")
        L.append("")
        L.extend(_table(_GROUP_HEADER, "invoice", [_group_row(p, pm) for p, pm in m["by_invoice"].items()]))
    L.append("")
    L.append("## Invoices: hand derivation vs the deterministic policy tool")
    L.append("")
    L.append("| invoice | scenario | tier | hub | expected decision (manual) | escalation (manual 6.2) | grand total INR | policy tool agrees |")
    L.append("|---|---|---|---|---|---|---|---|")
    for f in s["fixtures"]:
        L.append(f"| {f['preset_id']} | {f['scenario']} | {f['analysis_tier']} | {f['fc_hub']} | {f['expected_decision']} | "
                 f"{f['expected_escalation']} | {f['invoice_grand_total_inr']:,.2f} | {f['derivation_agrees_with_gate']} |")
    L.append("")
    L.append("## Vouchers that did not match")
    L.append("")
    if not s["non_exact_runs"]:
        L.append("None.")
    for e in s["non_exact_runs"]:
        L.append(f"- **{e['arm_id']} / {e['preset_id']} / r{e['repeat_index']}** (run {e['run_id']}): fields {', '.join(e['mismatched_fields']) or '-'}; "
                 f"turns {e['turns']}")
        L.append(f"  - expected: {json.dumps(e['expected'])}")
        L.append(f"  - committed: {json.dumps(e['committed'])}")
        L.append(f"  - tools: {', '.join(e['tools_called']) or 'none'}")
    dq = s["data_quality"]
    L.append("")
    L.append("## Data quality (runs used)")
    L.append("")
    L.append(", ".join(f"{k.replace('_', ' ')} {v}" for k, v in dq.items()) + ".")
    L.append("")
    L.append("## Method notes")
    L.append("")
    for note in s["notes"]:
        L.append(f"- {note}")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------------------------------
# App-facing portfolio (replays/cat5_ablation_summary.json)
# --------------------------------------------------------------------------------------------------

PORTFOLIO_SCHEMA_VERSION = 2
GOLDEN_REPEAT_INDEX = 0
# Fixed, pre-declared mapping version -> app rung for the golden replays (never chosen by outcome).
APP_RUNG_FOR_ARM: dict[str, str] = {
    "raw_free_sonnet": "unbounded_sonnet_loop",
    "raw_free_haiku": "unbounded_haiku_loop",
    "bundle_gate_sonnet_cached": "bounded_sonnet_cached_gate",
    "bundle_gate_haiku_escalate": "hybrid_haiku_sonnet_governed",
}
ARM_PLAIN: dict[str, dict[str, str]] = {
    "raw_free_sonnet": {
        "design": "without", "model_column": "sonnet",
        "label": "Without: free-choice loop over raw tables (Sonnet)",
        "adds": "Sonnet chooses among raw ERP table queries and does the policy arithmetic itself; no step budget, no policy tool",
    },
    "raw_free_haiku": {
        "design": "without", "model_column": "haiku",
        "label": "Without: free-choice loop over raw tables (Haiku)",
        "adds": "The same loop on Haiku; with no policy tool nothing flags escalation, so there is no escalation path to Sonnet",
    },
    "bundle_gate_sonnet_cached": {
        "design": "with", "model_column": "sonnet",
        "label": "With: 4-step budget + policy tool (Sonnet)",
        "adds": "4-step budget and the deterministic policy tool, with one narrow query and the policy manual cached",
    },
    "bundle_gate_haiku_escalate": {
        "design": "with", "model_column": "haiku",
        "label": "With: 4-step budget + policy tool (Haiku-first)",
        "adds": "The same on Haiku; Sonnet takes over when the policy tool flags a multi-factor dispute",
    },
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
    source_file: str,
    golden_run_ids: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Compact app-facing summary built from `summarise()` (the path analyze_cat5_ablation.py uses)."""
    s = summarise(records)
    arms = []
    for a in s["arm_ids"]:
        m = s["arms"][a]
        spec = ARMS[a]
        plain = ARM_PLAIN[a]
        arms.append({
            "arm_id": a,
            "label": plain["label"],
            "adds": plain["adds"],
            "design": plain["design"],
            "model_column": plain["model_column"],
            "runnable_in_app": a in APP_RUNG_FOR_ARM,
            "app_rung_id": APP_RUNG_FOR_ARM.get(a),
            "tool_set": spec.tool_set,
            "cached": spec.cached,
            "start_model": spec.start_model,
            "gate": spec.gate,
            "escalate": spec.escalate,
            "turn_cap": spec.turn_cap,
            **_cell(m),
            "expected_runs": len(s["preset_ids"]) * s["expected_repeats"],
            "pending_runs": m["pending"]["runs"],
            "pending_invoices": m["pending"]["invoices"],
            "by_tier": {t: _cell(x) for t, x in m["by_tier"].items()},
            "by_invoice": {p: _cell(x) for p, x in m["by_invoice"].items()},
        })
    pooled_ids = list(s["preset_ids"])
    return {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "source": "cat5 ablation (ablation.summarise)",
        "source_file": source_file,
        "fixture_version": s["fixture_version"],
        "record_count": s["record_count"],
        "pooled_runs": s["ok_runs_used"],
        "expected_runs": s["matrix"]["expected_runs"],
        "pending_runs": len(s["matrix"]["pending_keys"]),
        "invoices_pooled": pooled_ids,
        "invoice_count_pooled": len(pooled_ids),
        "invoice_count_total": len(pooled_ids),
        "repeats": s["expected_repeats"],
        "matrix_complete": s["matrix"]["complete"],
        "runs_per_arm": len(pooled_ids) * s["expected_repeats"],
        "settings": s["settings"],
        "tiers": {p["id"]: p.get("analysis_tier") for p in CAT5_ABLATION_PRESETS},
        "arms": arms,
        "data_quality": s["data_quality"],
        "non_exact_runs": [
            {k: e[k] for k in ("arm_id", "preset_id", "repeat_index", "expected", "committed", "mismatched_fields")}
            for e in s["non_exact_runs"]
        ],
        "notes": s["notes"],
        "run_ids": s["run_ids"],
        "golden_mapping": {
            "selection_rule": f"fixed pre-declared mapping, repeat_index {GOLDEN_REPEAT_INDEX}, original invoices inv-01..03 (not selected by outcome)",
            "arm_to_rung": dict(APP_RUNG_FOR_ARM),
            "run_ids": golden_run_ids or {},
        },
    }


__all__ = [
    "ARMS",
    "ARM_IDS",
    "OTHER_LEVER_ARM_IDS",
    "CAT5_ABLATION_ALL_INVOICE_IDS",
    "CAT5_ABLATION_DEFAULT_INVOICE_IDS",
    "NEUTRAL_PROTOCOL",
    "AblationErpSession",
    "BudgetGuard",
    "execute_run",
    "summarise",
    "render_markdown",
]
