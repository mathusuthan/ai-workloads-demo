"""Category 2 single-section regenerations, captured on the current golden template drafts.

One call per preset x templated model (Sonnet, Haiku) x section the app can regenerate (4 x 2 x 4 = 32). Each call is
the app's own regenerate-section request (`runner.section_regen_request`: the app's system prompt, single-section
schema, payload layout, the canonical reviewer instruction and max_tokens 1,800) through `run_cat2_structured_draft`
(the app's thinking settings and timeout), sent against that preset's CURRENT repeat-0 templated draft of the SAME
model (the `{model}_templated` rung of `replays/cat2_golden_replays.json`).

Records are appended to experiments/cat2_not_stated/section_regens.jsonl with the full prompt and response and no
dollar amounts. Nothing is chosen by outcome: an ok record (truncated or not) is never redone; an error record stays in
the file, is reported, and its key is sent again on the next run. A record is current only if its system prompt,
payload and schema hashes match today's plan, so a rebuilt base draft makes the old record stale.

`build_section_regens_block()` turns the current records into the golden `section_regens` block (deterministic).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Sequence

from app.archetypes.cat2_drafting import not_stated_experiment as ns
from app.archetypes.cat2_drafting import quality_scoring as qs
from app.archetypes.cat2_drafting.runner import SECTION_REGEN_MAX_TOKENS, section_regen_request
from app.data.cat2_fixtures import CAT2_REVIEWER_PRESETS

SCHEMA_VERSION = 1
REGENS_PATH = ns.EXPERIMENT_DIR / "section_regens.jsonl"
REGENS_FILE_LABEL = "experiments/cat2_not_stated/section_regens.jsonl"
SECTION_KEYS: tuple[str, ...] = ("executive_summary", "key_findings", "risk_and_compliance_matrix", "action_plan")
MODEL_KEYS: tuple[str, ...] = ("sonnet", "haiku")
DEFAULT_MAX_USD = 0.5
# Estimate basis only (never used in results): mean output tokens of the 16 per-model regenerations captured before
# this harness existed. Replaced by the mean of this file's own ok records once there are any.
TYPICAL_OUTPUT_TOKENS = {"sonnet": 483, "haiku": 588}

RegenCall = Callable[..., Awaitable[Any]]


def regen_key(preset_id: str, section_key: str, model_key: str) -> str:
    return f"regen:{preset_id}:{section_key}:{model_key}"


def _section_sha(section: Any) -> str:
    return ns._sha(json.dumps(section, sort_keys=True, ensure_ascii=False))


class BaseDraftMissing(ValueError):
    pass


def plan_regens(golden: dict[str, Any]) -> list[dict[str, Any]]:
    """The 32 planned calls, built from the golden templated drafts. Raises BaseDraftMissing if a base is absent."""
    presets = qs.preset_map()
    plan: list[dict[str, Any]] = []
    missing: list[str] = []
    for pid in qs.PRESET_IDS:
        pdata = (golden.get("presets") or {}).get(pid) or {}
        for sk in SECTION_KEYS:
            for m in MODEL_KEYS:
                rung = f"{m}_templated"
                draft = (pdata.get("rungs") or {}).get(rung)
                section = ((draft or {}).get("structured_draft") or {}).get(sk)
                if section is None:
                    missing.append(f"{pid}/{rung}/{sk}")
                    continue
                preset = presets[pid]
                instruction = CAT2_REVIEWER_PRESETS[sk]["instruction"]
                rq = section_regen_request(sub_task=preset["sub_task"], section_key=sk, source_text=preset["payload"],
                                           current_section=section, reviewer_instruction=instruction)
                plan.append({
                    "regen_key": regen_key(pid, sk, m),
                    "preset_id": pid,
                    "sub_task": preset["sub_task"],
                    "section_key": sk,
                    "model_key": m,
                    "model_tier": ns.MODELS[m],
                    "reviewer_instruction": instruction,
                    "base_rung": rung,
                    "base_draft_id": ((pdata.get("provenance") or {}).get(rung) or {}).get("draft_id"),
                    "base_section_sha256": _section_sha(section),
                    "prior_section": section,
                    "system": rq["system"],
                    "payload": rq["payload"],
                    "schema": rq["schema"],
                    "max_tokens": rq["max_tokens"],
                    "system_sha256": ns._sha(rq["system"]),
                    "payload_sha256": ns._sha(rq["payload"]),
                    "schema_sha256": ns._sha(json.dumps(rq["schema"], sort_keys=True)),
                })
    if missing:
        raise BaseDraftMissing(f"golden templated drafts missing for {len(missing)} sections: {missing[:6]}")
    return plan


def _hashes(r: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (r.get("system_sha256"), r.get("payload_sha256"), r.get("schema_sha256"))


def current_records(plan: Sequence[dict[str, Any]], records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Latest ok record per planned key whose prompt hashes match the plan."""
    cur = {p["regen_key"]: _hashes(p) for p in plan}
    out: dict[str, dict[str, Any]] = {}
    for r in records:
        k = r.get("regen_key")
        if r.get("status") == "ok" and k in cur and _hashes(r) == cur[k]:
            out[k] = r  # file order: later wins
    return out


def select_pending(plan: Sequence[dict[str, Any]], records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    done = current_records(plan, records)
    return [p for p in plan if p["regen_key"] not in done]


def stale_keys(plan: Sequence[dict[str, Any]], records: Iterable[dict[str, Any]]) -> list[str]:
    """Keys with an ok record made from a different prompt, payload (base draft) or schema, and no current one."""
    records = list(records)
    cur = current_records(plan, records)
    keys = {p["regen_key"] for p in plan}
    return sorted({r["regen_key"] for r in records if r.get("status") == "ok" and r.get("regen_key") in keys} - set(cur))


def error_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in records if r.get("status") != "ok"]


def chars_per_token(golden: dict[str, Any], records: Iterable[dict[str, Any]] = ()) -> float:
    """chars (system + payload + schema) / input tokens over this file's ok records, else over the golden block's
    earlier regenerations (rebuilt payloads), else the unbounded-draft calibration."""
    ratios = [(len(r["system"]) + len(r["payload"]) + len(json.dumps(r["schema"]))) / int(r["input_tokens"])
              for r in records if r.get("status") == "ok" and r.get("input_tokens") and r.get("schema") is not None]
    if not ratios:
        presets = qs.preset_map()
        for pid, secs in (golden.get("section_regens") or {}).items():
            for sk, by_model in (secs or {}).items():
                for r in (by_model or {}).values():
                    if pid not in presets or not r.get("input_tokens") or sk not in CAT2_REVIEWER_PRESETS:
                        continue
                    rq = section_regen_request(sub_task=presets[pid]["sub_task"], section_key=sk, source_text=presets[pid]["payload"],
                                               current_section=r.get("prior_section") or {}, reviewer_instruction=CAT2_REVIEWER_PRESETS[sk]["instruction"])
                    ratios.append((len(rq["system"]) + len(rq["payload"]) + len(json.dumps(rq["schema"]))) / int(r["input_tokens"]))
    return sum(ratios) / len(ratios) if ratios else qs.calibrate_chars_per_token(golden)


def typical_output_tokens(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    out = dict(TYPICAL_OUTPUT_TOKENS)
    for m in MODEL_KEYS:
        vals = [int(r["output_tokens"]) for r in records if r.get("status") == "ok" and r.get("model_key") == m]
        if vals:
            out[m] = round(sum(vals) / len(vals))
    return out


def estimate(p: dict[str, Any], cpt: float, typical: dict[str, int]) -> dict[str, Any]:
    in_tok = int(-(-(len(p["system"]) + len(p["payload"]) + len(json.dumps(p["schema"]))) // cpt))
    typ_out = min(typical[p["model_key"]], int(p["max_tokens"]))
    return {
        "input_tokens": in_tok,
        "typical_output_tokens": typ_out,
        "typical_usd": ns._finops(p["model_tier"], in_tok, typ_out).total_cost_usd,
        "worst_case_usd": ns._finops(p["model_tier"], in_tok, int(p["max_tokens"])).total_cost_usd,
    }


def make_app_regen_call(api_key: str) -> RegenCall:
    """The app's call (`run_cat2_structured_draft`), raise_on_max_tokens=False so truncation is recorded, not raised."""
    from app.core.anthropic_service import run_cat2_structured_draft

    async def call(*, system: str, payload: str, schema: dict[str, Any], model_tier: str, max_tokens: int) -> Any:
        return await run_cat2_structured_draft(payload, system, schema, model_tier, api_key, max_tokens=max_tokens, raise_on_max_tokens=False)

    return call


_PLAN_FIELDS = ("regen_key", "preset_id", "sub_task", "section_key", "model_key", "model_tier", "reviewer_instruction", "base_rung",
                "base_draft_id", "base_section_sha256", "prior_section", "system", "payload", "schema", "max_tokens",
                "system_sha256", "payload_sha256", "schema_sha256")


async def execute_regen(p: dict[str, Any], *, regen_call: RegenCall) -> dict[str, Any]:
    """One call -> one record. Never raises; an API failure is a `status: error` record."""
    rec: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        **{k: p[k] for k in _PLAN_FIELDS},
        "status": "error",
        "error_type": None,
        "error_message": None,
        "started_at": ns._utc_now_iso(),
        "model_id": None,
        "stop_reason": None,
        "truncated": None,
        "parse_ok": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "thinking_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "latency_ms": None,
        "request_params": None,
        "raw_text": None,
        "structured": None,
        "updated_section": None,
    }
    try:
        raw = await regen_call(system=p["system"], payload=p["payload"], schema=p["schema"], model_tier=p["model_tier"], max_tokens=p["max_tokens"])
    except Exception as exc:  # noqa: BLE001 — recorded, never raised
        rec["error_type"] = "api_error"
        rec["error_message"] = f"{type(exc).__name__}: {exc}"[:2000]
        rec["finished_at"] = ns._utc_now_iso()
        return rec
    sd = raw.structured if isinstance(raw.structured, dict) else {}
    sk = p["section_key"]
    rec.update({
        "status": "ok",
        "model_id": raw.model_id,
        "stop_reason": raw.stop_reason,
        "truncated": raw.stop_reason == "max_tokens",
        "parse_ok": sk in sd,
        "input_tokens": int(raw.input_tokens),
        "output_tokens": int(raw.output_tokens),
        "thinking_tokens": int(getattr(raw, "thinking_tokens", 0) or 0),
        "cache_creation_tokens": int(getattr(raw, "cache_creation_tokens", 0) or 0),
        "cache_read_tokens": int(getattr(raw, "cache_read_tokens", 0) or 0),
        "latency_ms": int(raw.latency_ms),
        "request_params": getattr(raw, "request_params", None),
        "raw_text": raw.raw_text,
        "structured": sd,
        "updated_section": sd.get(sk, sd),  # the app's own extraction (runner.execute_cat2_section_regen)
        "finished_at": ns._utc_now_iso(),
    })
    return rec


async def run_plan(pending: Sequence[dict[str, Any]], *, regen_call: RegenCall, guard: ns.CostGuard,
                   on_record: Callable[[dict[str, Any]], None], cpt: float, typical: dict[str, int], concurrency: int = 4) -> dict[str, Any]:
    sem = asyncio.Semaphore(max(1, concurrency))
    tasks: list[asyncio.Task[None]] = []
    counts = {"ok": 0, "error": 0, "launched": 0, "skipped_budget": 0, "truncated": 0, "not_parsed": 0}
    budget_stopped = False

    async def one(p: dict[str, Any], reserved: float) -> None:
        try:
            rec = await execute_regen(p, regen_call=regen_call)
            guard.settle(reserved, rec)
            counts["ok" if rec["status"] == "ok" else "error"] += 1
            counts["truncated"] += bool(rec.get("truncated"))
            counts["not_parsed"] += rec["status"] == "ok" and not rec.get("parse_ok")
            on_record(rec)
        finally:
            sem.release()

    for i, p in enumerate(pending):
        await sem.acquire()
        worst = estimate(p, cpt, typical)["worst_case_usd"]
        if not guard.try_reserve(worst):
            sem.release()
            budget_stopped = True
            counts["skipped_budget"] = len(pending) - i
            break
        counts["launched"] += 1
        tasks.append(asyncio.create_task(one(p, worst)))
    if tasks:
        await asyncio.gather(*tasks)
    return {**counts, "budget_stopped": budget_stopped, "spent_usd": guard.spent_usd}


def build_section_regens_block(plan: Sequence[dict[str, Any]], records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """The golden `section_regens` block from the current records: {preset: {section: {model_id: {...}}}}.
    Requires a current ok record for every planned key (raises ValueError otherwise)."""
    cur = current_records(plan, records)
    missing = [p["regen_key"] for p in plan if p["regen_key"] not in cur]
    if missing:
        raise ValueError(f"{len(missing)} of {len(plan)} section regenerations have no current record: {missing[:6]}")
    block: dict[str, Any] = {}
    for p in plan:
        r = cur[p["regen_key"]]
        block.setdefault(p["preset_id"], {}).setdefault(p["section_key"], {})[p["model_tier"]] = {
            "model_id": r["model_id"],
            "latency_ms": int(r.get("latency_ms") or 0),
            "input_tokens": int(r["input_tokens"]),
            "output_tokens": int(r["output_tokens"]),
            "thinking_tokens": int(r.get("thinking_tokens") or 0),
            "stop_reason": r.get("stop_reason"),
            "truncated": bool(r.get("truncated")),
            "parse_ok": bool(r.get("parse_ok")),
            "max_tokens": int(r["max_tokens"]),
            "request_params": r.get("request_params"),
            "request_payload": r["payload"],
            "raw_text": r.get("raw_text"),
            "prior_section": r["prior_section"],
            "updated_section": r.get("updated_section"),
            "provenance": {"regen_key": r["regen_key"], "base_draft_id": r.get("base_draft_id"), "base_rung": r.get("base_rung"),
                           "records_file": REGENS_FILE_LABEL, "started_at": r.get("started_at")},
        }
    return block


def load_records(path: Path | str = REGENS_PATH) -> list[dict[str, Any]]:
    return ns.load_jsonl(path)
