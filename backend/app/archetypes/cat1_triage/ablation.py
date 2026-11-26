"""Category 1 seven-arm ablation: separate "ask for less", "schema" and "model" with sound accuracy scoring.

Arms (same 12 items: 6 presets + 6 batch items, 3 repeats -> 252 runs):
  sonnet_report        Sonnet 5.5 · today's naive four-part write-up (system prompt unchanged) · free text
  sonnet_classify_text Sonnet 5.5 · classification only (neutral prompt built from the schema)  · free text
  sonnet_schema        Sonnet 5.5 · today's calibrated prompt + the sub-task's JSON schema          · strict JSON
  haiku_report         Haiku 5.5  · today's naive write-up                                          · free text
  haiku_classify_text  Haiku 5.5  · classification only                                             · free text
  haiku_schema         Haiku 5.5  · today's calibrated rung                                         · strict JSON
  gemini_decision      Gemini Decision 1 · today's decisions call                                  · decisions API

Each Anthropic arm goes through the app's own wrapper (run_sonnet_naive / run_haiku_naive / run_haiku_calibrated)
with keyword overrides only (cap, prompt, model, timeout, max_retries=0, no silent tool fallback). Thinking stays
as the app configures it per model: Sonnet {"type": "between_tools"}, Haiku {"type": "disabled"}.

Scoring: schema and Gemini arms field-by-field with the app's `evaluate_rung_accuracy`; free-text arms by a blind
extraction judge (Opus 5.5, the Category 2 judge settings), whose values are compared by the same code. The app's
regex extractor (`extract_prose_predictions`) is run beside it on the same texts, and both are applied to the 24
stored prose responses of the original capture.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import random
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Sequence

from app.archetypes.cat1_triage.accuracy import evaluate_rung_accuracy  # its prose path is extract_prose_predictions
from app.archetypes.cat1_triage.prompts import get_haiku_calibrated_system_prompt, get_sonnet_naive_system_prompt
from app.archetypes.cat1_triage.schemas import get_questions_for_subtask, get_schema_for_subtask
from app.archetypes.cat2_drafting import quality_scoring as qs
from app.archetypes.cat6_swarms.fair_rerun import wilson_interval
from app.core.pricing import LEGACY_MODEL_RATES, MODEL_RATES, compute_run_finops
from app.data.cat1_fixtures import CAT1_EXTRA_BATCH_ITEMS, CAT1_PRESETS

SCHEMA_VERSION = 1
BACKEND_DIR = Path(__file__).resolve().parents[3]
EXPERIMENT_DIR = BACKEND_DIR / "experiments" / "cat1_ablation"
RUNS_PATH = EXPERIMENT_DIR / "runs.jsonl"
EXTRACTIONS_PATH = EXPERIMENT_DIR / "extractions.jsonl"
GOLDEN_PATH = BACKEND_DIR / "replays" / "cat1_golden_replays.json"
# Verbatim copy of the golden replays as first captured (2,048-token prose cap, 256-token schema cap). Written once by
# scripts/build_cat1_golden_from_ablation.py before it replaces the golden file with repeat 0 of the ablation, so the
# "original capture" group and its extraction prompts stay the same after the rebuild.
ORIGINAL_CAPTURE_PATH = BACKEND_DIR / "replays" / "cat1_original_capture.json"
ABLATION_GOLDEN_SOURCE = "cat1_ablation_repeat0"
SUMMARY_PATH = BACKEND_DIR / "replays" / "cat1_ablation_summary.json"

SONNET, HAIKU, GEMINI = "claude-sonnet-5-5", "claude-haiku-5-5", "gemini-decision-1"
REPEATS = 3
DEFAULT_RUN_MAX_USD = 6.0
DEFAULT_EXTRACT_MAX_USD = 8.0
SCHEMA_CHECK_SAMPLE = 20
SCHEMA_CHECK_SEED = 20261126

CAPS = {"report": 8192, "classify_text": 1024, "schema": 512}
TIMEOUTS_S = {"report": 300.0, "classify_text": 120.0, "schema": 60.0}
MAX_RETRIES = 0  # nothing silently re-billed by the SDK
THINKING = {"sonnet": {"type": "between_tools"}, "haiku": {"type": "disabled"}}  # as the app configures each model
APP_SCHEMA_CAP = 256  # today's calibrated rung
STORED_PROSE_CAP = 2048  # today's naive rungs (original capture)

DECK_PROFILE = {"input_tokens": (500, 1500), "output_tokens": (10, 100), "io_ratio": (20, 50)}


@dataclass(frozen=True)
class Arm:
    arm_id: str
    model_key: str  # sonnet | haiku | gemini
    task: str  # report | classify_text | schema | decision
    output_format: str  # free_text | json_schema | decisions_api


ARMS: tuple[Arm, ...] = (
    Arm("sonnet_report", "sonnet", "report", "free_text"),
    Arm("sonnet_classify_text", "sonnet", "classify_text", "free_text"),
    Arm("sonnet_schema", "sonnet", "schema", "json_schema"),
    Arm("haiku_report", "haiku", "report", "free_text"),
    Arm("haiku_classify_text", "haiku", "classify_text", "free_text"),
    Arm("haiku_schema", "haiku", "schema", "json_schema"),
    Arm("gemini_decision", "gemini", "decision", "decisions_api"),
)
ARM_IDS: tuple[str, ...] = tuple(a.arm_id for a in ARMS)
ARM_BY_ID = {a.arm_id: a for a in ARMS}
FREE_TEXT_ARMS = tuple(a.arm_id for a in ARMS if a.output_format == "free_text")
STRUCTURED_ARMS = ("sonnet_schema", "haiku_schema", "gemini_decision")
MODEL_ID = {"sonnet": SONNET, "haiku": HAIKU, "gemini": GEMINI}

ITEMS: tuple[dict[str, Any], ...] = tuple(
    [{**p, "group": "preset"} for p in CAT1_PRESETS] + [{**p, "group": "batch"} for p in CAT1_EXTRA_BATCH_ITEMS]
)
ITEM_BY_ID = {i["id"]: i for i in ITEMS}
ITEM_IDS: tuple[str, ...] = tuple(i["id"] for i in ITEMS)
SUB_TASKS = ("support_triage", "sku_tagging")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _jsha(obj: Any) -> str:
    return _sha(json.dumps(obj, sort_keys=True))


def _utc_now_iso() -> str:
    return qs._utc_now_iso()


# --------------------------------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------------------------------


def report_system_prompt(sub_task: str) -> str:
    """Today's naive four-part write-up prompt, verbatim (the app uses it for both models)."""
    return get_sonnet_naive_system_prompt(sub_task)


def schema_system_prompt(sub_task: str) -> str:
    return get_haiku_calibrated_system_prompt(sub_task)


def scalar_fields(sub_task: str) -> list[str]:
    """Schema fields with one value (enum or boolean); array fields are not extracted."""
    props = get_schema_for_subtask(sub_task)["properties"]
    return [f for f, spec in props.items() if spec.get("type") in ("string", "boolean")]


def _allowed_values(spec: dict[str, Any]) -> list[str]:
    if spec.get("type") == "boolean":
        return ["true", "false"]
    if spec.get("type") == "array":
        return list(spec["items"].get("enum") or [])
    return list(spec.get("enum") or [])


def field_definition_lines(sub_task: str, *, include_arrays: bool = True) -> list[str]:
    """One line per schema field, built mechanically from the schema (it has no descriptions, so none are shown)."""
    lines = []
    for f, spec in get_schema_for_subtask(sub_task)["properties"].items():
        t = spec.get("type")
        if t == "boolean":
            lines.append(f"- {f}: true or false")
        elif t == "array":
            if include_arrays:
                lines.append(f"- {f}: a comma-separated list of zero or more of {', '.join(_allowed_values(spec))} (write none if empty)")
        else:
            lines.append(f"- {f}: one of {', '.join(_allowed_values(spec))}")
    return lines


CLASSIFY_TEXT_INSTRUCTION = "Answer with one line per field, `field: value`, using only the allowed values. Do not explain."


def classify_text_system_prompt(sub_task: str) -> str:
    """Neutral classification-only prompt, identical for both models: the calibrated prompt's first sentence, the
    schema's fields with allowed values, then the answer format. No schema is enforced."""
    first = schema_system_prompt(sub_task).split(". ", 1)[0].rstrip(".") + "."
    return "\n".join([first, "", "Fields:", *field_definition_lines(sub_task), "", CLASSIFY_TEXT_INSTRUCTION])


def system_prompt_for(arm_id: str, sub_task: str) -> str | None:
    task = ARM_BY_ID[arm_id].task
    if task == "report":
        return report_system_prompt(sub_task)
    if task == "classify_text":
        return classify_text_system_prompt(sub_task)
    if task == "schema":
        return schema_system_prompt(sub_task)
    return None


# --------------------------------------------------------------------------------------------------
# Settings, planning, resume, superseded handling
# --------------------------------------------------------------------------------------------------


def current_settings(arm_id: str, sub_task: str) -> dict[str, Any]:
    arm = ARM_BY_ID[arm_id]
    if arm.task == "decision":
        q = get_questions_for_subtask(sub_task)
        return {"arm_id": arm_id, "model_intended": GEMINI, "call_path": "gemini_decision_service.run_gemini_decision",
                "questions_sha256": _jsha(q), "timeouts": "app defaults (SDK; REST fallback 30 s)", "max_retries": "app/SDK default"}
    system = system_prompt_for(arm_id, sub_task) or ""
    s: dict[str, Any] = {
        "arm_id": arm_id,
        "model_intended": MODEL_ID[arm.model_key],
        "call_path": ("anthropic_service.run_haiku_calibrated" if arm.task == "schema"
                      else f"anthropic_service.run_{arm.model_key}_naive"),
        "max_tokens": CAPS[arm.task],
        "thinking": THINKING[arm.model_key],
        "timeout_s": TIMEOUTS_S[arm.task],
        "max_retries": MAX_RETRIES,
        "system_prompt_sha256": _sha(system),
        "output_format": arm.output_format,
    }
    if arm.task == "schema":
        s["schema_sha256"] = _jsha(get_schema_for_subtask(sub_task))
        s["allow_tool_fallback"] = False
    return s


def settings_sha(settings: dict[str, Any]) -> str:
    return _jsha(settings)


def run_id(arm_id: str, item_id: str, repeat_index: int) -> str:
    return f"{arm_id}:{item_id}:r{repeat_index}"


def plan_runs(repeats: int = REPEATS, arm_ids: Sequence[str] = ARM_IDS, item_ids: Sequence[str] = ITEM_IDS) -> list[dict[str, Any]]:
    """Order: repeat -> item -> arm (so a stopped run stays balanced across arms)."""
    plan = []
    for k in range(repeats):
        for iid in item_ids:
            item = ITEM_BY_ID[iid]
            for a in arm_ids:
                st = current_settings(a, item["sub_task"])
                plan.append({"run_id": run_id(a, iid, k), "arm_id": a, "item_id": iid, "sub_task": item["sub_task"],
                             "item_group": item["group"], "repeat_index": k, "settings": st, "settings_sha256": settings_sha(st)})
    return plan


def load_jsonl(path: Path | str) -> list[dict[str, Any]]:
    return qs.load_judgements(path)


def is_superseded(rec: dict[str, Any]) -> bool:
    item = ITEM_BY_ID.get(rec.get("item_id"))
    if item is None or rec.get("arm_id") not in ARM_BY_ID:
        return True
    return rec.get("settings_sha256") != settings_sha(current_settings(rec["arm_id"], item["sub_task"]))


def superseded_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in records if r.get("status") == "ok" and is_superseded(r)]


def latest_ok_current(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in records:
        if r.get("status") == "ok" and not is_superseded(r):
            out[r["run_id"]] = r
    return out


def select_pending(plan: Iterable[dict[str, Any]], existing: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Planned runs without a current-settings ok record. Errors and superseded records leave the key pending."""
    done = set(latest_ok_current(existing))
    return [p for p in plan if p["run_id"] not in done]


# --------------------------------------------------------------------------------------------------
# Cost (estimates and analysis only — records hold no dollars)
# --------------------------------------------------------------------------------------------------


def run_cost_usd(rec: dict[str, Any]) -> float:
    if rec.get("status") != "ok" and not rec.get("input_tokens"):
        return 0.0
    mid = rec.get("model_returned") or (rec.get("settings") or {}).get("model_intended") or HAIKU
    if mid not in MODEL_RATES and mid not in LEGACY_MODEL_RATES:
        mid = SONNET if "sonnet" in mid else HAIKU if "haiku" in mid else GEMINI
    return compute_run_finops(mid, int(rec.get("input_tokens") or 0), int(rec.get("output_tokens") or 0)).total_cost_usd


def is_ablation_golden(doc: dict[str, Any]) -> bool:
    return (doc.get("provenance") or {}).get("source") == ABLATION_GOLDEN_SOURCE


def _golden() -> dict[str, Any]:
    """The ORIGINAL capture: replays/cat1_original_capture.json, else the golden file while it still holds it."""
    for path in (ORIGINAL_CAPTURE_PATH, GOLDEN_PATH):
        if path.is_file():
            doc = json.loads(path.read_text(encoding="utf-8"))
            if not is_ablation_golden(doc):
                return doc
    return {"presets": {}, "batch_items": {}}


def stored_input_tokens(item_id: str, golden: dict[str, Any] | None = None) -> dict[str, int]:
    """Measured input tokens of the original capture: naive prose (sonnet/haiku), calibrated schema, gemini."""
    g = golden or _golden()
    if item_id in (g.get("presets") or {}):
        r = g["presets"][item_id]["rungs"]
        return {"prose_sonnet": r["sonnet_naive"]["input_tokens"], "prose_haiku": r["haiku_naive"]["input_tokens"],
                "schema": r["haiku_calibrated"]["input_tokens"], "gemini": r["gemini_decision"]["input_tokens"]}
    b = g["batch_items"][item_id]
    return {"prose_sonnet": b["sonnet_input_tokens"], "prose_haiku": b["haiku_naive_input_tokens"],
            "schema": b["input_tokens"], "gemini": b["gemini_input_tokens"]}


TYPICAL_OUTPUT = {"report": 3500, "classify_text": 80, "schema": 110, "decision": 0}  # assumption, labelled in the dry run


def estimate_run(planned: dict[str, Any], golden: dict[str, Any] | None = None, chars_per_token: float = 3.0) -> dict[str, Any]:
    arm = ARM_BY_ID[planned["arm_id"]]
    st = stored_input_tokens(planned["item_id"], golden)
    if arm.task == "decision":
        return {"input_tokens": st["gemini"], "typical_usd": compute_run_finops(GEMINI, st["gemini"], 0).total_cost_usd,
                "worst_case_usd": compute_run_finops(GEMINI, st["gemini"], 0).total_cost_usd}
    model = MODEL_ID[arm.model_key]
    if arm.task == "schema":
        in_tok = st["schema"]
    else:
        base = st[f"prose_{arm.model_key}"]
        extra = len(system_prompt_for(arm.arm_id, planned["sub_task"]) or "") - len(report_system_prompt(planned["sub_task"]))
        in_tok = max(1, base + int(math.ceil(extra / chars_per_token)))
    typ = min(CAPS[arm.task], TYPICAL_OUTPUT[arm.task])
    return {"input_tokens": in_tok, "typical_usd": compute_run_finops(model, in_tok, typ).total_cost_usd,
            "worst_case_usd": compute_run_finops(model, in_tok, CAPS[arm.task]).total_cost_usd}


def estimate_run_plan(plan: Sequence[dict[str, Any]], golden: dict[str, Any] | None = None) -> dict[str, Any]:
    g = golden or _golden()
    by: dict[str, dict[str, Any]] = {}
    for p in plan:
        e = estimate_run(p, g)
        s = by.setdefault(p["arm_id"], {"runs": 0, "input_tokens": 0, "typical_usd": 0.0, "worst_case_usd": 0.0})
        s["runs"] += 1
        for k in ("input_tokens", "typical_usd", "worst_case_usd"):
            s[k] += e[k]
    tot = {k: sum(s[k] for s in by.values()) for k in ("runs", "input_tokens", "typical_usd", "worst_case_usd")}
    return {"by_arm": by, "total": tot, "typical_output_assumed": dict(TYPICAL_OUTPUT)}


class CostGuard:
    def __init__(self, max_usd: float, existing: Iterable[dict[str, Any]] = (), *, cost_fn: Callable[[dict[str, Any]], float] = run_cost_usd) -> None:
        self.max_usd = float(max_usd)
        self.cost_fn = cost_fn
        self.spent_usd = sum(cost_fn(r) for r in existing)
        self.reserved_usd = 0.0

    def try_reserve(self, worst: float) -> bool:
        if self.spent_usd + self.reserved_usd + worst > self.max_usd:
            return False
        self.reserved_usd += worst
        return True

    def settle(self, reserved: float, rec: dict[str, Any]) -> None:
        self.reserved_usd = max(0.0, self.reserved_usd - reserved)
        self.spent_usd += self.cost_fn(rec)


# --------------------------------------------------------------------------------------------------
# Execution (injectable call paths)
# --------------------------------------------------------------------------------------------------


@dataclass
class CallPaths:
    """prose(arm, item, system_prompt, max_tokens, timeout_s, max_retries) -> AnthropicRawResult-like
    schema(arm, item, schema, model, fallback_models, max_tokens, thinking, timeout_s, max_retries) -> same
    gemini(item, questions) -> GeminiDecisionRawResult-like (raises on error)"""

    prose: Callable[..., Awaitable[Any]]
    schema: Callable[..., Awaitable[Any]]
    gemini: Callable[..., Awaitable[Any]]


def make_app_call_paths(anthropic_key: str | None, gemini_key: str | None) -> CallPaths:
    from app.core.anthropic_service import run_haiku_calibrated, run_haiku_naive, run_sonnet_naive
    from app.core.gemini_decision_service import run_gemini_decision

    async def prose(*, model_key: str, payload: str, sub_task: str, system_prompt: str, max_tokens: int, timeout_s: float, max_retries: int):
        if not anthropic_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        fn = run_sonnet_naive if model_key == "sonnet" else run_haiku_naive
        return await fn(payload, sub_task, anthropic_key, system_prompt=system_prompt, max_tokens=max_tokens,
                        timeout_s=timeout_s, max_retries=max_retries)

    async def schema(*, model_key: str, payload: str, sub_task: str, schema: dict[str, Any], max_tokens: int, thinking: dict[str, str],
                     timeout_s: float, max_retries: int):
        if not anthropic_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        from app.config import get_settings

        st = get_settings()
        model = st.anthropic_sonnet_model if model_key == "sonnet" else st.anthropic_haiku_model
        fallbacks = ["claude-sonnet-5-5", "claude-sonnet-4-6"] if model_key == "sonnet" else ["claude-haiku-5-5", "claude-haiku-4-5"]
        return await run_haiku_calibrated(payload, sub_task, schema, anthropic_key, model=model, fallback_models=fallbacks,
                                          max_tokens=max_tokens, thinking=thinking, timeout_s=timeout_s, max_retries=max_retries,
                                          allow_tool_fallback=False)

    async def gemini(*, payload: str, questions: dict[str, Any]):
        if not gemini_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        return await run_gemini_decision(payload, questions, gemini_key)

    return CallPaths(prose=prose, schema=schema, gemini=gemini)


def _base_run_record(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        **{k: p[k] for k in ("run_id", "arm_id", "item_id", "sub_task", "item_group", "repeat_index", "settings", "settings_sha256")},
        "status": "error",
        "error_type": None,
        "error_message": None,
        "started_at": _utc_now_iso(),
        "model_intended": p["settings"]["model_intended"],
        "model_returned": None,
        "model_matches": None,
        "stop_reason": None,
        "truncated": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "thinking_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "latency_ms": None,
        "raw_text": None,
        "structured_output": None,
        "request_params": None,
        "decision": None,
    }


async def execute_run(p: dict[str, Any], *, calls: CallPaths) -> dict[str, Any]:
    """One run -> one record. Never raises; failures (incl. a missing Gemini key) are error records."""
    rec = _base_run_record(p)
    arm = ARM_BY_ID[p["arm_id"]]
    item = ITEM_BY_ID[p["item_id"]]
    st = p["settings"]
    try:
        if arm.task == "decision":
            g = await calls.gemini(payload=item["payload"], questions=get_questions_for_subtask(item["sub_task"]))
            approx = int(g.input_tokens) == max(1, round(len(item["payload"]) / 3.8))
            rec.update({
                "status": "ok", "model_returned": g.model_id, "model_matches": g.model_id == GEMINI, "stop_reason": None, "truncated": False,
                "input_tokens": int(g.input_tokens), "output_tokens": int(g.output_tokens), "latency_ms": int(g.latency_ms),
                "structured_output": dict(g.structured_summary),
                "decision": {"structured_summary": dict(g.structured_summary), "decision_probabilities": dict(g.decision_probabilities),
                             "endpoint": getattr(g, "endpoint", None), "input_tokens_possibly_estimated": approx},
            })
        else:
            if arm.task == "schema":
                raw = await calls.schema(model_key=arm.model_key, payload=item["payload"], sub_task=item["sub_task"],
                                         schema=get_schema_for_subtask(item["sub_task"]), max_tokens=st["max_tokens"],
                                         thinking=st["thinking"], timeout_s=st["timeout_s"], max_retries=st["max_retries"])
                structured = raw.structured if isinstance(raw.structured, dict) else {}
            else:
                raw = await calls.prose(model_key=arm.model_key, payload=item["payload"], sub_task=item["sub_task"],
                                        system_prompt=system_prompt_for(arm.arm_id, item["sub_task"]), max_tokens=st["max_tokens"],
                                        timeout_s=st["timeout_s"], max_retries=st["max_retries"])
                structured = None
            rec.update({
                "status": "ok", "model_returned": raw.model_id, "model_matches": raw.model_id == st["model_intended"],
                "stop_reason": raw.stop_reason, "truncated": raw.stop_reason == "max_tokens",
                "input_tokens": int(raw.input_tokens), "output_tokens": int(raw.output_tokens),
                "thinking_tokens": int(getattr(raw, "thinking_tokens", 0) or 0),
                "cache_creation_tokens": int(getattr(raw, "cache_creation_tokens", 0) or 0),
                "cache_read_tokens": int(getattr(raw, "cache_read_tokens", 0) or 0),
                "latency_ms": int(raw.latency_ms), "raw_text": raw.raw_text, "structured_output": structured,
                "request_params": getattr(raw, "request_params", None),
                "system_prompt_sent_sha256": _sha(getattr(raw, "system_prompt", "") or ""),
            })
            if arm.task == "schema":
                rec["schema_parse_ok"] = bool(structured) and all(k in structured for k in get_schema_for_subtask(item["sub_task"])["required"])
    except Exception as exc:  # noqa: BLE001 — recorded, never raised or substituted
        rec["error_type"] = "api_error"
        rec["error_message"] = f"{type(exc).__name__}: {exc}"[:2000]
    rec["finished_at"] = _utc_now_iso()
    return rec


async def run_plan(pending: Sequence[dict[str, Any]], *, calls: CallPaths, guard: CostGuard, on_record: Callable[[dict[str, Any]], None],
                   concurrency: int = 4, golden: dict[str, Any] | None = None) -> dict[str, Any]:
    g = golden or _golden()
    sem = asyncio.Semaphore(max(1, concurrency))
    tasks: list[asyncio.Task[None]] = []
    counts = {"ok": 0, "error": 0, "launched": 0, "skipped_budget": 0, "truncated": 0}
    stopped = False

    async def one(p: dict[str, Any], reserved: float) -> None:
        try:
            rec = await execute_run(p, calls=calls)
            guard.settle(reserved, rec)
            counts["ok" if rec["status"] == "ok" else "error"] += 1
            counts["truncated"] += bool(rec.get("truncated"))
            on_record(rec)
        finally:
            sem.release()

    for i, p in enumerate(pending):
        await sem.acquire()
        worst = estimate_run(p, g)["worst_case_usd"]
        if not guard.try_reserve(worst):
            sem.release()
            stopped = True
            counts["skipped_budget"] = len(pending) - i
            break
        counts["launched"] += 1
        tasks.append(asyncio.create_task(one(p, worst)))
    if tasks:
        await asyncio.gather(*tasks)
    return {**counts, "budget_stopped": stopped, "spent_usd": guard.spent_usd}


# --------------------------------------------------------------------------------------------------
# Extraction judge (blind)
# --------------------------------------------------------------------------------------------------

NOT_STATED, AMBIGUOUS = "not_stated", "ambiguous"

EXTRACTION_SYSTEM_PROMPT = """You read a RESPONSE that an assistant wrote about one NovaMart item (a customer or seller support ticket, or a catalog listing) and record what the RESPONSE says for each listed field. You will receive the field definitions with their allowed values, the ITEM the response was written about, and the RESPONSE.

Report what the RESPONSE says, not what you think the right answer is. The ITEM is given only so that you can understand what the RESPONSE refers to; never take a value from the ITEM, and never fill a gap with your own judgement.

For each field return exactly one of:
  - an allowed value: when the RESPONSE states or clearly commits to exactly one allowed value, in the same words or in an unambiguous paraphrase (for example "Priority: P1 - High" is P1_HIGH; "route it to the replacements team" is replacements; "the ticket contains a card number and a phone number" is true for a field that asks whether personal data is present). Give evidence: the shortest verbatim quote from the RESPONSE that states the value, copied exactly.
  - not_stated: the RESPONSE does not address the field at all. Evidence is an empty string.
  - ambiguous: the RESPONSE addresses the field but gives several values without committing to one, contradicts itself, hedges between options, or uses wording that cannot be mapped to a single allowed value. Evidence is the verbatim quote that shows the problem.

A RESPONSE that stops mid-sentence is judged only on what it contains. Do not reward or penalise length, tone, formatting or quality; you are recording answers, not grading them."""

EXTRACTION_USER_TEMPLATE = """<fields>
{fields}
</fields>

<item>
{item}
</item>

<response>
{response}
</response>

Return one entry per field listed above."""


def extraction_schema(sub_task: str) -> dict[str, Any]:
    props = get_schema_for_subtask(sub_task)["properties"]
    fields = {}
    for f in scalar_fields(sub_task):
        fields[f] = {
            "type": "object",
            "properties": {
                "value": {"type": "string", "enum": [*_allowed_values(props[f]), NOT_STATED, AMBIGUOUS]},
                "evidence": {"type": "string"},
            },
            "required": ["value", "evidence"],
            "additionalProperties": False,
        }
    return {"type": "object", "properties": {"fields": {"type": "object", "properties": fields, "required": list(fields),
                                                         "additionalProperties": False}},
            "required": ["fields"], "additionalProperties": False}


def extraction_fields_block(sub_task: str) -> str:
    return "\n".join(field_definition_lines(sub_task, include_arrays=False))


def build_extraction_prompt(sub_task: str, item_payload: str, response_text: str) -> tuple[str, str]:
    user = EXTRACTION_USER_TEMPLATE.format(fields=extraction_fields_block(sub_task), item=item_payload.strip(), response=(response_text or "").strip())
    return EXTRACTION_SYSTEM_PROMPT, user


def render_structured_as_text(structured: dict[str, Any], sub_task: str) -> str:
    """A schema output as plain `field: value` lines (the judge check); booleans lower-case, lists comma-joined."""
    lines = []
    for f in get_schema_for_subtask(sub_task)["properties"]:
        v = structured.get(f)
        if isinstance(v, bool):
            v = "true" if v else "false"
        elif isinstance(v, list):
            v = ", ".join(map(str, v)) or "none"
        lines.append(f"{f}: {v}")
    return "\n".join(lines)


def golden_prose_responses(golden: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The 24 stored prose responses of the original capture (12 items x Sonnet/Haiku naive), with truncation
    inferred from output tokens at the 2048 cap (the capture did not store stop reasons)."""
    g = golden or _golden()
    out = []
    for iid in ITEM_IDS:
        item = ITEM_BY_ID[iid]
        for m, rung in (("sonnet", "sonnet_naive"), ("haiku", "haiku_naive")):
            if iid in (g.get("presets") or {}):
                r = g["presets"][iid]["rungs"].get(rung)
                if not r:
                    continue
                text, in_tok, out_tok, lat, mid = r.get("raw_text_preview") or "", r["input_tokens"], r["output_tokens"], r.get("latency_ms"), r.get("model_id")
            else:
                b = (g.get("batch_items") or {}).get(iid)
                if not b:
                    continue
                pre = "sonnet" if m == "sonnet" else "haiku_naive"
                text, in_tok, out_tok, lat, mid = b.get(f"{pre}_raw_text") or "", b[f"{pre}_input_tokens"], b[f"{pre}_output_tokens"], b.get(f"{pre}_latency_ms"), MODEL_ID[m]
            out.append({"golden_id": f"golden:{m}_report:{iid}", "arm_id": f"{m}_report", "item_id": iid, "sub_task": item["sub_task"],
                        "item_group": item["group"], "raw_text": text, "input_tokens": in_tok, "output_tokens": out_tok,
                        "latency_ms": lat, "model_returned": mid, "truncated": out_tok >= STORED_PROSE_CAP})
    return out


def golden_structured(golden: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Stored haiku_calibrated and gemini_decision outputs of the original capture."""
    g = golden or _golden()
    out = []
    for iid in ITEM_IDS:
        item = ITEM_BY_ID[iid]
        if iid in (g.get("presets") or {}):
            r = g["presets"][iid]["rungs"]
            pairs = [("haiku_schema", r.get("haiku_calibrated"), r.get("haiku_calibrated", {}).get("structured_output"), "input_tokens", "output_tokens"),
                     ("gemini_decision", r.get("gemini_decision"), r.get("gemini_decision", {}).get("structured_output"), "input_tokens", "output_tokens")]
            for arm, src, so, ik, ok in pairs:
                if src:
                    out.append({"arm_id": arm, "item_id": iid, "sub_task": item["sub_task"], "structured_output": so or {},
                                "input_tokens": src[ik], "output_tokens": src[ok], "latency_ms": src.get("latency_ms"), "model_returned": src.get("model_id")})
        else:
            b = (g.get("batch_items") or {}).get(iid)
            if not b:
                continue
            out.append({"arm_id": "haiku_schema", "item_id": iid, "sub_task": item["sub_task"], "structured_output": b.get("haiku_decision") or {},
                        "input_tokens": b["input_tokens"], "output_tokens": b["haiku_output_tokens"], "latency_ms": b.get("haiku_latency_ms"), "model_returned": HAIKU})
            out.append({"arm_id": "gemini_decision", "item_id": iid, "sub_task": item["sub_task"], "structured_output": b.get("gemini_decision") or {},
                        "input_tokens": b["gemini_input_tokens"], "output_tokens": 0, "latency_ms": b.get("gemini_latency_ms"), "model_returned": GEMINI})
    return out


def schema_check_sample(run_records: dict[str, dict[str, Any]], n: int = SCHEMA_CHECK_SAMPLE, seed: int = SCHEMA_CHECK_SEED) -> list[dict[str, Any]]:
    eligible = sorted((r for r in run_records.values() if r["arm_id"] in ("sonnet_schema", "haiku_schema") and r.get("schema_parse_ok")),
                      key=lambda r: r["run_id"])
    if len(eligible) <= n:
        return eligible
    return sorted(random.Random(seed).sample(eligible, n), key=lambda r: r["run_id"])


def extraction_targets(run_records: dict[str, dict[str, Any]], golden: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """(source, id, sub_task, item_id, text) for every free-text run, the 24 stored prose responses, and the seeded
    schema-check sample."""
    t = []
    for r in sorted(run_records.values(), key=lambda r: r["run_id"]):
        if r["arm_id"] in FREE_TEXT_ARMS:
            t.append({"source": "run", "target_id": r["run_id"], "sub_task": r["sub_task"], "item_id": r["item_id"], "text": r.get("raw_text") or ""})
    for gr in golden_prose_responses(golden):
        t.append({"source": "golden", "target_id": gr["golden_id"], "sub_task": gr["sub_task"], "item_id": gr["item_id"], "text": gr["raw_text"]})
    for r in schema_check_sample(run_records):
        t.append({"source": "schema_check", "target_id": r["run_id"], "sub_task": r["sub_task"], "item_id": r["item_id"],
                  "text": render_structured_as_text(r["structured_output"], r["sub_task"])})
    return t


def extraction_call_id(source: str, target_id: str) -> str:
    return f"extract:{source}:{target_id}"


def plan_extractions(targets: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    plan = []
    for t in targets:
        system, user = build_extraction_prompt(t["sub_task"], ITEM_BY_ID[t["item_id"]]["payload"], t["text"])
        plan.append({"call_id": extraction_call_id(t["source"], t["target_id"]), "task": "extraction", **t, "system": system, "user": user,
                     "schema": extraction_schema(t["sub_task"]), "text_sha256": _sha(t["text"]), "prompt_sha256": qs._sha(system, user)})
    return plan


EXTRA_BLINDING_TERMS: tuple[str, ...] = (*ARM_IDS, "gemini", "schema", "thinking", "report_arm", "classify_text", "schema_check", "ground_truth", "ground truth",
                                         "expected", "golden", "repeat")


def extraction_blinding_violations(planned: dict[str, Any], forbidden_numbers: Sequence[str] = ()) -> list[str]:
    """Baseline (Category 2) blinding terms plus arm/source labels, looked for only in what WE add: the item payload
    and the response are cut out first."""
    embedded = [ITEM_BY_ID[planned["item_id"]]["payload"], planned["text"]]
    prompt = planned["system"] + "\n" + planned["user"]
    hits = qs.blinding_violations(prompt, embedded)
    rest = prompt
    for t in sorted((t.strip() for t in embedded if t and t.strip()), key=len, reverse=True):
        rest = rest.replace(t, "")
    low = rest.lower()
    hits += [w for w in EXTRA_BLINDING_TERMS if w.lower() in low and w not in hits]
    for n in forbidden_numbers:
        if n and re.search(rf"(?<![\d,]){re.escape(n)}(?![\d,])", rest):
            hits.append(f"number:{n}")
    return hits


def blinding_report(plan: Sequence[dict[str, Any]], run_records: dict[str, dict[str, Any]] | None = None) -> dict[str, list[str]]:
    bad = {}
    for p in plan:
        nums: list[str] = []
        r = (run_records or {}).get(p["target_id"]) if p["source"] != "golden" else None
        if r:
            for f in ("input_tokens", "output_tokens", "thinking_tokens"):
                if r.get(f):
                    nums += [str(r[f]), f"{r[f]:,}"]
        v = extraction_blinding_violations(p, nums)
        if v:
            bad[p["call_id"]] = v
    return bad


class ExtractionError(ValueError):
    def __init__(self, error_type: str, message: str) -> None:
        super().__init__(message)
        self.error_type = error_type


def parse_extraction(raw_text: str, sub_task: str) -> dict[str, Any]:
    import jsonschema

    try:
        obj = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ExtractionError("invalid_json", str(exc)) from exc
    try:
        jsonschema.validate(obj, extraction_schema(sub_task))
    except jsonschema.ValidationError as exc:
        raise ExtractionError("schema_violation", exc.message[:500]) from exc
    return obj


def _norm_ws(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip().lower()


def evidence_not_verbatim(parsed: dict[str, Any], response_text: str) -> list[str]:
    """Fields with a stated or ambiguous value whose evidence is not a quote of the response (whitespace/case-insensitive)."""
    body = _norm_ws(response_text)
    return [f for f, e in parsed["fields"].items() if e["value"] != NOT_STATED and _norm_ws(e.get("evidence", "")) not in body]


def extracted_values(parsed: dict[str, Any], sub_task: str) -> dict[str, Any]:
    """Judge values as the app's types: booleans as bool; not_stated / ambiguous as None."""
    props = get_schema_for_subtask(sub_task)["properties"]
    out = {}
    for f, e in parsed["fields"].items():
        v = e["value"]
        if v in (NOT_STATED, AMBIGUOUS):
            out[f] = None
        elif props[f].get("type") == "boolean":
            out[f] = v == "true"
        else:
            out[f] = v
    return out


def _base_extraction_record(p: dict[str, Any], max_tokens: int) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION, "call_id": p["call_id"], "task": "extraction", "source": p["source"], "target_id": p["target_id"],
        "item_id": p["item_id"], "sub_task": p["sub_task"], "status": "error", "error_type": None, "error_message": None,
        "judge_model_requested": qs.JUDGE_MODEL,
        "settings": {"max_tokens": max_tokens, "thinking": dict(qs.JUDGE_THINKING), "effort": qs.JUDGE_EFFORT, "timeout_s": qs.JUDGE_TIMEOUT_S, "max_retries": 0},
        "text_sha256": p["text_sha256"], "prompt_sha256": p["prompt_sha256"], "model_id": None, "stop_reason": None,
        "input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0, "cache_creation_tokens": 0, "cache_read_tokens": 0,
        "latency_ms": None, "raw_text": None, "parsed": None,
    }


async def execute_extraction(p: dict[str, Any], *, judge_call: qs.JudgeCall, max_tokens: int = qs.JUDGE_MAX_TOKENS) -> dict[str, Any]:
    rec = _base_extraction_record(p, max_tokens)
    rec["started_at"] = _utc_now_iso()
    try:
        resp = await judge_call(system=p["system"], user=p["user"], schema=p["schema"], max_tokens=max_tokens)
    except Exception as exc:  # noqa: BLE001
        rec["error_type"] = "api_error"
        rec["error_message"] = f"{type(exc).__name__}: {exc}"[:2000]
        rec["finished_at"] = _utc_now_iso()
        return rec
    rec.update({"model_id": resp.model_id, "stop_reason": resp.stop_reason, "input_tokens": int(resp.input_tokens),
                "output_tokens": int(resp.output_tokens), "thinking_tokens": int(resp.thinking_tokens or 0),
                "cache_creation_tokens": int(resp.cache_creation_tokens or 0), "cache_read_tokens": int(resp.cache_read_tokens or 0),
                "latency_ms": int(resp.latency_ms), "request_id": resp.request_id, "raw_text": resp.raw_text})
    try:
        if resp.stop_reason != "end_turn":
            raise ExtractionError("stop_reason", f"stop_reason={resp.stop_reason}")
        rec["parsed"] = parse_extraction(resp.raw_text, p["sub_task"])
        rec["evidence_not_verbatim"] = evidence_not_verbatim(rec["parsed"], p["text"])
        rec["status"] = "ok"
    except ExtractionError as exc:
        rec["error_type"] = exc.error_type
        rec["error_message"] = str(exc)[:2000]
    rec["finished_at"] = _utc_now_iso()
    return rec


async def run_extraction_plan(pending: Sequence[dict[str, Any]], *, judge_call: qs.JudgeCall, guard: qs.BudgetGuard,
                              on_record: Callable[[dict[str, Any]], None], concurrency: int = 4, max_tokens: int = qs.JUDGE_MAX_TOKENS,
                              chars_per_token: float = qs.DEFAULT_CHARS_PER_TOKEN) -> dict[str, Any]:
    sem = asyncio.Semaphore(max(1, concurrency))
    tasks: list[asyncio.Task[None]] = []
    counts = {"ok": 0, "error": 0, "launched": 0, "skipped_budget": 0}
    stopped = False

    async def one(p: dict[str, Any], reserved: float) -> None:
        try:
            rec = await execute_extraction(p, judge_call=judge_call, max_tokens=max_tokens)
            guard.settle(reserved, rec)
            counts["ok" if rec["status"] == "ok" else "error"] += 1
            on_record(rec)
        finally:
            sem.release()

    for i, p in enumerate(pending):
        await sem.acquire()
        worst = qs.judge_cost_usd(qs.estimate_input_tokens(p, chars_per_token), max_tokens)
        if not guard.try_reserve(worst):
            sem.release()
            stopped = True
            counts["skipped_budget"] = len(pending) - i
            break
        counts["launched"] += 1
        tasks.append(asyncio.create_task(one(p, worst)))
    if tasks:
        await asyncio.gather(*tasks)
    return {**counts, "budget_stopped": stopped, "spent_usd": guard.spent_usd}


def latest_ok_extractions(records: Iterable[dict[str, Any]], plan: Sequence[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    """call_id -> latest ok record; with a plan, only records made from the current prompt (text) count."""
    cur = {p["call_id"]: p["prompt_sha256"] for p in plan} if plan is not None else None
    out: dict[str, dict[str, Any]] = {}
    for r in records:
        if r.get("status") == "ok" and (cur is None or cur.get(r["call_id"]) == r.get("prompt_sha256")):
            out[r["call_id"]] = r
    return out


def select_pending_extractions(plan: Sequence[dict[str, Any]], existing: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    done = set(latest_ok_extractions(existing, plan))
    return [p for p in plan if p["call_id"] not in done]


def calibrate_judge_estimate() -> dict[str, Any]:
    from app.archetypes.cat2_drafting import not_stated_experiment as ns

    cal = ns.calibrate_judge_estimate()
    typ = (cal.get("typical_output_tokens") or {}).get("pairwise")
    return {"chars_per_token": cal["chars_per_token"], "typical_output_tokens": {"extraction": typ or 800},
            "source": f"{cal['source']}; extraction output assumed ≈ the Category 2 pairwise call's"}


# --------------------------------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------------------------------


def ground_truth(item_id: str) -> dict[str, Any]:
    return dict(ITEM_BY_ID[item_id]["ground_truth"])


def score_values(item_id: str, sub_task: str, predicted: dict[str, Any]) -> dict[str, Any]:
    """Deterministic comparison through the app's own evaluator (schema path)."""
    ev = evaluate_rung_accuracy(rung_id="haiku_calibrated", sub_task=sub_task, ground_truth=ground_truth(item_id),
                                structured_output=predicted, raw_text=None)
    return {"matched": ev.matched_count, "total": ev.total_fields, "exact": ev.exact_match,
            "fields": {c.field: {"expected": c.expected, "actual": c.actual, "matched": c.matched} for c in ev.field_checks}}


def score_gemini(item_id: str, sub_task: str, structured: dict[str, Any]) -> dict[str, Any]:
    ev = evaluate_rung_accuracy(rung_id="gemini_decision", sub_task=sub_task, ground_truth=ground_truth(item_id),
                                structured_output=structured, raw_text=None)
    return {"matched": ev.matched_count, "total": ev.total_fields, "exact": ev.exact_match,
            "fields": {c.field: {"expected": c.expected, "actual": c.actual, "matched": c.matched} for c in ev.field_checks}}


def score_regex(item_id: str, sub_task: str, text: str) -> dict[str, Any]:
    ev = evaluate_rung_accuracy(rung_id="sonnet_naive", sub_task=sub_task, ground_truth=ground_truth(item_id),
                                structured_output={}, raw_text=text)
    return {"matched": ev.matched_count, "total": ev.total_fields, "exact": ev.exact_match,
            "fields": {c.field: {"expected": c.expected, "actual": c.actual, "matched": c.matched} for c in ev.field_checks}}


def extractor_agreement(regex_vals: dict[str, Any], judge_vals: dict[str, Any], fields: Sequence[str]) -> dict[str, int]:
    """Per field: both name the same value / both name different values / only one names a value / neither."""
    c = Counter()
    for f in fields:
        a, b = regex_vals.get(f), judge_vals.get(f)
        if a is None and b is None:
            c["neither"] += 1
        elif a is None:
            c["judge_only"] += 1
        elif b is None:
            c["regex_only"] += 1
        elif a == b:
            c["same_value"] += 1
        else:
            c["different_value"] += 1
    c["fields"] = len(fields)
    c["agree"] = c["same_value"] + c["neither"]
    return {k: c.get(k, 0) for k in ("fields", "agree", "same_value", "different_value", "regex_only", "judge_only", "neither")}


def _prop(hits: int, total: int) -> dict[str, Any]:
    ci = wilson_interval(hits, total) if total else None
    return {"hits": hits, "total": total, "rate": hits / total if total else None, "wilson95": list(ci) if ci else None}


def _dist(vals: Sequence[float]) -> dict[str, Any]:
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"n": 0, "median": None, "min": None, "max": None, "mean": None}
    return {"n": len(vals), "median": statistics.median(vals), "min": min(vals), "max": max(vals), "mean": statistics.fmean(vals)}


def _pool_scores(scores: Sequence[dict[str, Any]]) -> dict[str, Any]:
    hits = sum(s["matched"] for s in scores)
    total = sum(s["total"] for s in scores)
    by_field: dict[str, list[bool]] = {}
    for s in scores:
        for f, v in s["fields"].items():
            by_field.setdefault(f, []).append(v["matched"])
    return {"field_accuracy": _prop(hits, total), "items_fully_correct": sum(1 for s in scores if s["exact"]), "items": len(scores),
            "by_field": {f: _prop(sum(v), len(v)) for f, v in by_field.items()}}


def _cost_per_1k(rec: dict[str, Any]) -> float:
    return run_cost_usd(rec) * 1000


def scored_runs(run_records: Sequence[dict[str, Any]], extraction_records: Sequence[dict[str, Any]], golden: dict[str, Any] | None = None) -> dict[str, Any]:
    """Every current ok run with its judge-based (or structured) score and, for free text, the regex score."""
    runs = latest_ok_current(run_records)
    plan = plan_extractions(extraction_targets(runs, golden))
    ext = latest_ok_extractions(extraction_records, plan)
    out = {}
    for rid, r in runs.items():
        item, sub = r["item_id"], r["sub_task"]
        row: dict[str, Any] = {"run": r, "scores": None, "regex": None, "extraction": None, "agreement": None}
        gt_fields = list(ground_truth(item))
        if r["arm_id"] == "gemini_decision":
            row["scores"] = score_gemini(item, sub, r.get("structured_output") or {})
        elif r["arm_id"] in ("sonnet_schema", "haiku_schema"):
            row["scores"] = score_values(item, sub, r.get("structured_output") or {})
        else:
            row["regex"] = score_regex(item, sub, r.get("raw_text") or "")
            e = ext.get(extraction_call_id("run", rid))
            if e:
                vals = extracted_values(e["parsed"], sub)
                row["extraction"] = {"values": vals, "raw": e["parsed"]["fields"]}
                row["scores"] = score_values(item, sub, vals)
                row["agreement"] = extractor_agreement({f: v["actual"] for f, v in row["regex"]["fields"].items()}, vals, gt_fields)
        out[rid] = row
    return {"runs": out, "extractions": ext, "plan": plan}


def analyse(run_records: Sequence[dict[str, Any]], extraction_records: Sequence[dict[str, Any]] | None = None, *,
            golden: dict[str, Any] | None = None) -> dict[str, Any]:
    g = golden or _golden()
    extraction_records = list(extraction_records or [])
    sr = scored_runs(run_records, extraction_records, g)
    rows = sr["runs"]

    def arm_block(sel: list[dict[str, Any]]) -> dict[str, Any]:
        recs = [x["run"] for x in sel]
        scored = [x["scores"] for x in sel if x["scores"]]
        b: dict[str, Any] = {
            "runs": len(sel),
            "scored_runs": len(scored),
            "accuracy": _pool_scores(scored) if scored else None,
            "truncated": sum(1 for r in recs if r.get("truncated")),
            "stop_reasons": dict(Counter(str(r.get("stop_reason")) for r in recs)),
            "input_tokens": _dist([r["input_tokens"] for r in recs]),
            "output_tokens": _dist([r["output_tokens"] for r in recs]),
            "thinking_tokens": _dist([r.get("thinking_tokens") or 0 for r in recs]),
            "io_ratio": _dist([r["input_tokens"] / r["output_tokens"] for r in recs if r.get("output_tokens")]),
            "cost_per_1k_items_usd": statistics.fmean(_cost_per_1k(r) for r in recs) if recs else None,
            "latency_ms": _dist([r.get("latency_ms") for r in recs]),
            "model_mismatches": sum(1 for r in recs if r.get("model_matches") is False),
        }
        if sel and sel[0]["run"]["arm_id"] in FREE_TEXT_ARMS:
            regex = [x["regex"] for x in sel if x["regex"]]
            b["regex_accuracy"] = _pool_scores(regex) if regex else None
            vals = [(x["extraction"]["values"], list(ground_truth(x["run"]["item_id"]))) for x in sel if x["extraction"]]
            b["extracted_runs"] = len(vals)
            b["judge_value_counts"] = _value_class_counts(sel)
            ag = Counter()
            for x in sel:
                if x["agreement"]:
                    ag.update(x["agreement"])
            b["extractor_agreement"] = dict(ag) if ag else None
        if sel and sel[0]["run"]["arm_id"] in ("sonnet_schema", "haiku_schema"):
            b["schema_parse_failures"] = sum(1 for r in recs if not r.get("schema_parse_ok"))
            b["batch_cost_per_1k_items_usd_computed"] = b["cost_per_1k_items_usd"] * 0.5 if b["cost_per_1k_items_usd"] is not None else None
            b["output_tokens_max_vs_app_cap"] = {"max_output_tokens": b["output_tokens"]["max"], "app_cap": APP_SCHEMA_CAP, "rerun_cap": CAPS["schema"]}
        if sel and sel[0]["run"]["arm_id"] == "gemini_decision":
            b["input_tokens_possibly_estimated"] = sum(1 for r in recs if (r.get("decision") or {}).get("input_tokens_possibly_estimated"))
        return b

    arms: dict[str, Any] = {}
    for a in ARM_IDS:
        sel = [x for x in rows.values() if x["run"]["arm_id"] == a]
        arms[a] = {**arm_block(sel), "by_sub_task": {s: arm_block([x for x in sel if x["run"]["sub_task"] == s]) for s in SUB_TASKS},
                   "by_group": {gname: arm_block([x for x in sel if x["run"]["item_group"] == gname]) for gname in ("preset", "batch")}}

    # Levers
    def acc(a: str) -> dict[str, Any] | None:
        return (arms[a].get("accuracy") or {}).get("field_accuracy")

    def lever(name: str, a: str, b: str) -> dict[str, Any]:
        ca, cb = arms[a]["cost_per_1k_items_usd"], arms[b]["cost_per_1k_items_usd"]
        aa, ab = acc(a), acc(b)
        return {"lever": name, "from": a, "to": b, "cost_from": ca, "cost_to": cb,
                "cost_change_pct": ((cb / ca - 1) * 100) if ca and cb is not None else None,
                "accuracy_from": aa, "accuracy_to": ab,
                "accuracy_change_pp": ((ab["rate"] - aa["rate"]) * 100) if aa and ab and aa["rate"] is not None and ab["rate"] is not None else None}

    levers = []
    for m in ("sonnet", "haiku"):
        levers.append(lever(f"write-up → classification-only text ({m})", f"{m}_report", f"{m}_classify_text"))
        levers.append(lever(f"text → schema ({m})", f"{m}_classify_text", f"{m}_schema"))
    for t in ("report", "classify_text", "schema"):
        levers.append(lever(f"Sonnet → Haiku ({t})", f"sonnet_{t}", f"haiku_{t}"))
    levers.append(lever("Haiku schema → Gemini decision", "haiku_schema", "gemini_decision"))
    levers.append(lever("whole stack: Sonnet write-up → Haiku schema", "sonnet_report", "haiku_schema"))

    # Original capture
    gold_ext = sr["extractions"]
    golden_rows = []
    for gr in golden_prose_responses(g):
        e = gold_ext.get(extraction_call_id("golden", gr["golden_id"]))
        regex = score_regex(gr["item_id"], gr["sub_task"], gr["raw_text"])
        judge = score_values(gr["item_id"], gr["sub_task"], extracted_values(e["parsed"], gr["sub_task"])) if e else None
        agreement = extractor_agreement({f: v["actual"] for f, v in regex["fields"].items()}, extracted_values(e["parsed"], gr["sub_task"]),
                                        list(ground_truth(gr["item_id"]))) if e else None
        golden_rows.append({**{k: gr[k] for k in ("golden_id", "arm_id", "item_id", "sub_task", "item_group", "input_tokens", "output_tokens", "truncated")},
                            "regex": regex, "judge": judge, "agreement": agreement, "evidence": (e["parsed"]["fields"] if e else None),
                            "text_tail": gr["raw_text"][-120:]})
    gs_rows = []
    for gs in golden_structured(g):
        sc = score_gemini(gs["item_id"], gs["sub_task"], gs["structured_output"]) if gs["arm_id"] == "gemini_decision" else score_values(gs["item_id"], gs["sub_task"], gs["structured_output"])
        gs_rows.append({**{k: gs[k] for k in ("arm_id", "item_id", "sub_task", "input_tokens", "output_tokens")}, "scores": sc})
    original = {}
    for a in ("sonnet_report", "haiku_report"):
        sel = [x for x in golden_rows if x["arm_id"] == a]
        judged = [x["judge"] for x in sel if x["judge"]]
        ag = Counter()
        for x in sel:
            if x["agreement"]:
                ag.update(x["agreement"])
        original[a] = {"responses": len(sel), "truncated_at_2048": sum(1 for x in sel if x["truncated"]),
                       "regex_accuracy": _pool_scores([x["regex"] for x in sel]) if sel else None,
                       "judge_accuracy": _pool_scores(judged) if judged else None, "judged": len(judged),
                       "extractor_agreement": dict(ag) if ag else None,
                       "input_tokens": _dist([x["input_tokens"] for x in sel]), "output_tokens": _dist([x["output_tokens"] for x in sel]),
                       "cost_per_1k_items_usd": statistics.fmean(compute_run_finops(MODEL_ID[a.split("_")[0]], x["input_tokens"], x["output_tokens"]).total_cost_usd * 1000 for x in sel) if sel else None}
    for a in ("haiku_schema", "gemini_decision"):
        sel = [x for x in gs_rows if x["arm_id"] == a]
        original[a] = {"responses": len(sel), "accuracy": _pool_scores([x["scores"] for x in sel]) if sel else None,
                       "input_tokens": _dist([x["input_tokens"] for x in sel]), "output_tokens": _dist([x["output_tokens"] for x in sel]),
                       "max_output_tokens_vs_cap": {"max": max((x["output_tokens"] for x in sel), default=None), "cap": APP_SCHEMA_CAP} if a == "haiku_schema" else None,
                       "cost_per_1k_items_usd": statistics.fmean(compute_run_finops(HAIKU if a == "haiku_schema" else GEMINI, x["input_tokens"], x["output_tokens"]).total_cost_usd * 1000 for x in sel) if sel else None}

    # Schema-as-text judge check
    checks = []
    runs_by_id = latest_ok_current(run_records)
    for p in sr["plan"]:
        if p["source"] != "schema_check":
            continue
        e = gold_ext.get(p["call_id"])
        r = runs_by_id.get(p["target_id"])
        if not e or not r:
            continue
        vals = extracted_values(e["parsed"], r["sub_task"])
        so = r["structured_output"]
        for f in scalar_fields(r["sub_task"]):
            checks.append({"run_id": r["run_id"], "field": f, "structured": so.get(f), "extracted": vals.get(f), "agree": so.get(f) == vals.get(f)})
    schema_check = {"planned": sum(1 for p in sr["plan"] if p["source"] == "schema_check"), "judged": len({c["run_id"] for c in checks}),
                    "fields": len(checks), "agree": sum(1 for c in checks if c["agree"]), "disagreements": [c for c in checks if not c["agree"]]}

    # Deck profile: payload tokens from a per-arm linear fit input_tokens = overhead + slope * payload_chars
    def fit(points: list[tuple[int, int]]) -> dict[str, Any] | None:
        if len({x for x, _ in points}) < 2:
            return None
        n = len(points)
        mx, my = sum(x for x, _ in points) / n, sum(y for _, y in points) / n
        sxx = sum((x - mx) ** 2 for x, _ in points)
        slope = sum((x - mx) * (y - my) for x, y in points) / sxx
        return {"tokens_per_char": slope, "overhead_tokens": my - slope * mx}

    pts = [(len(ITEM_BY_ID[x["run"]["item_id"]]["payload"]), x["run"]["input_tokens"]) for x in rows.values() if x["run"]["arm_id"] == "sonnet_report"]
    src = "sonnet_report runs"
    if len(pts) < 2:
        pts = [(len(ITEM_BY_ID[gr["item_id"]]["payload"]), gr["input_tokens"]) for gr in golden_prose_responses(g) if gr["arm_id"] == "sonnet_report"]
        src = "original capture (Sonnet naive)"
    f_ = fit(pts)
    payload_tokens = {iid: (f_["tokens_per_char"] * len(ITEM_BY_ID[iid]["payload"]) if f_ else None) for iid in ITEM_IDS}
    deck = {"fit": f_, "fit_source": src, "payload_tokens": payload_tokens,
            "payload_tokens_dist": _dist([v for v in payload_tokens.values() if v is not None]),
            "per_arm": {a: {"input_tokens": arms[a]["input_tokens"], "output_tokens": arms[a]["output_tokens"], "io_ratio": arms[a]["io_ratio"]} for a in ARM_IDS},
            "deck_bands": DECK_PROFILE}

    # For lead review
    misses, ambiguous, disagreements = [], [], []
    for rid, x in sorted(rows.items()):
        r = x["run"]
        if r["arm_id"] in STRUCTURED_ARMS and x["scores"]:
            for f, v in x["scores"]["fields"].items():
                if not v["matched"]:
                    misses.append({"run_id": rid, "field": f, "expected": v["expected"], "returned": v["actual"]})
        if x["extraction"]:
            gt_fields = list(ground_truth(r["item_id"]))
            for f in gt_fields:
                raw = x["extraction"]["raw"].get(f, {})
                if raw.get("value") == AMBIGUOUS:
                    ambiguous.append({"run_id": rid, "field": f, "evidence": raw.get("evidence")})
                rv = x["regex"]["fields"][f]["actual"]
                jv = x["extraction"]["values"].get(f)
                if rv != jv:
                    disagreements.append({"run_id": rid, "field": f, "regex": rv, "judge": jv, "judge_raw": raw.get("value"),
                                          "evidence": raw.get("evidence"), "expected": ground_truth(r["item_id"])[f]})
    for x in golden_rows:
        if not x["agreement"]:
            continue
        for f in ground_truth(x["item_id"]):
            raw = (x["evidence"] or {}).get(f, {})
            rv, jv = x["regex"]["fields"][f]["actual"], None if raw.get("value") in (NOT_STATED, AMBIGUOUS, None) else extracted_values({"fields": {f: raw}}, x["sub_task"])[f]
            if raw.get("value") == AMBIGUOUS:
                ambiguous.append({"run_id": x["golden_id"], "field": f, "evidence": raw.get("evidence")})
            if rv != jv:
                disagreements.append({"run_id": x["golden_id"], "field": f, "regex": rv, "judge": jv, "judge_raw": raw.get("value"),
                                      "evidence": raw.get("evidence"), "expected": ground_truth(x["item_id"])[f]})

    all_runs = list(run_records)
    gem = [r for r in all_runs if r.get("arm_id") == "gemini_decision"]
    return {
        "schema_version": SCHEMA_VERSION,
        "design": {"arms": [a.__dict__ for a in ARMS], "items": list(ITEM_IDS), "repeats": REPEATS, "planned_runs": len(plan_runs()),
                   "caps": dict(CAPS), "timeouts_s": dict(TIMEOUTS_S), "max_retries": MAX_RETRIES, "thinking": dict(THINKING),
                   "judge_model": qs.JUDGE_MODEL, "judge_passes": 1, "ground_truth_fields": sum(len(i["ground_truth"]) for i in ITEMS)},
        "data_quality": {
            "run_records": len(all_runs), "ok_current_runs": len(rows), "error_records": sum(1 for r in all_runs if r.get("status") != "ok"),
            "errors_by_arm": dict(Counter(r.get("arm_id") for r in all_runs if r.get("status") != "ok")),
            "error_messages": sorted({(r.get("arm_id"), (r.get("error_message") or "")[:160]) for r in all_runs if r.get("status") != "ok"}),
            "superseded_records": len(superseded_records(all_runs)),
            "missing_runs": sorted(p["run_id"] for p in plan_runs() if p["run_id"] not in rows),
            "gemini": {"records": len(gem), "ok": sum(1 for r in gem if r.get("status") == "ok"), "planned": len(ITEMS) * REPEATS},
            "truncated": sum(1 for x in rows.values() if x["run"].get("truncated")),
            "model_mismatches": sorted(rid for rid, x in rows.items() if x["run"].get("model_matches") is False),
            "extraction_records": len(extraction_records), "extraction_ok_current": len(sr["extractions"]),
            "extraction_errors": sum(1 for r in extraction_records if r.get("status") != "ok"),
            "extraction_error_history": _extraction_error_history(extraction_records, sr["extractions"]),
            "extractions_planned": len(sr["plan"]),
            "extraction_evidence_not_verbatim": sorted((cid, f) for cid, e in sr["extractions"].items() for f in (e.get("evidence_not_verbatim") or [])),
        },
        "arms": arms,
        "levers": levers,
        "original_capture": original,
        "original_capture_responses": golden_rows,
        "schema_check": schema_check,
        "deck_profile": deck,
        "review": {"structured_misses": misses, "ambiguous": ambiguous, "extractor_disagreements": disagreements},
    }


def _value_class_counts(sel: list[dict[str, Any]]) -> dict[str, int] | None:
    c = Counter()
    any_ = False
    for x in sel:
        if not x["extraction"]:
            continue
        any_ = True
        for f in ground_truth(x["run"]["item_id"]):
            v = x["extraction"]["raw"].get(f, {}).get("value")
            c["not_stated" if v == NOT_STATED else "ambiguous" if v == AMBIGUOUS else "stated"] += 1
    return {k: c.get(k, 0) for k in ("stated", "not_stated", "ambiguous")} if any_ else None



# --------------------------------------------------------------------------------------------------
# Dry-run stand-ins (estimate only; never written, never scored)
# --------------------------------------------------------------------------------------------------


def standin_run_records(golden: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """For a judge dry run before the runs exist: report arms -> the stored prose of the same model and item;
    classify-text arms -> the stored Haiku schema output rendered as `field: value` lines; schema arms -> the stored
    Haiku schema output. Prompt sizes are therefore approximate."""
    g = golden or _golden()
    prose = {(x["arm_id"], x["item_id"]): x for x in golden_prose_responses(g)}
    struct = {x["item_id"]: x["structured_output"] for x in golden_structured(g) if x["arm_id"] == "haiku_schema"}
    out = {}
    for p in plan_runs():
        arm = ARM_BY_ID[p["arm_id"]]
        rec = {**_base_run_record(p), "status": "ok", "standin": True}
        so = struct.get(p["item_id"]) or {}
        if arm.task == "report":
            rec["raw_text"] = prose[(p["arm_id"], p["item_id"])]["raw_text"]
        elif arm.task == "classify_text":
            rec["raw_text"] = render_structured_as_text(so, p["sub_task"])
        elif arm.task == "schema":
            rec["structured_output"], rec["schema_parse_ok"] = dict(so), bool(so)
        out[p["run_id"]] = rec
    return out


# --------------------------------------------------------------------------------------------------
# Markdown (factual tables)
# --------------------------------------------------------------------------------------------------


def _pct(p: dict[str, Any] | None) -> str:
    if not p or p.get("rate") is None:
        return "—"
    lo, hi = p["wilson95"]
    return f"{p['rate'] * 100:.1f}% ({p['hits']}/{p['total']}; {lo * 100:.0f}–{hi * 100:.0f}%)"


def _num(v: Any, fmt: str = "{:,.0f}") -> str:
    return "—" if v is None else fmt.format(v)


def _rng(d: dict[str, Any] | None, fmt: str = "{:,.0f}") -> str:
    if not d or not d.get("n"):
        return "—"
    return f"{fmt.format(d['median'])} ({fmt.format(d['min'])}–{fmt.format(d['max'])})"


def _ratio(v: float | None) -> str:
    return "—" if v is None else f"{v:,.1f}:1"


def _usd(v: float | None) -> str:
    return "—" if v is None else f"${v:,.3f}"


def _clip(s: Any, n: int = 140) -> str:
    s = "" if s is None else str(s)
    s = s.replace("\n", " ⏎ ").replace("|", "\\|")
    return s if len(s) <= n else s[: n - 1] + "…"


def render_markdown(r: dict[str, Any]) -> str:
    L: list[str] = []
    d, dq = r["design"], r["data_quality"]
    L += ["# Category 1 seven-arm ablation", "",
          "Factual tables. Generated by `backend/scripts/analyze_cat1_ablation.py` from `backend/experiments/cat1_ablation/runs.jsonl` "
          "and `extractions.jsonl`. Accuracy is field-level against the fixtures' ground truth (the same fields the app scores: "
          f"support queue/priority/auto_action/contains_pii, SKU leaf_category/compliance_status/contradiction_detected; {d['ground_truth_fields']} fields over 12 items). "
          "Intervals are Wilson 95%. Costs use the app's rate card (`app/core/pricing.py`); records hold no dollars.", ""]
    L += ["## Design", "", "| arm | model | task | output | max_tokens | thinking |", "|---|---|---|---|---|---|"]
    for a in ARMS:
        cap = CAPS.get(a.task, "—")
        th = THINKING.get(a.model_key, "—")
        L.append(f"| `{a.arm_id}` | {MODEL_ID[a.model_key]} | {a.task} | {a.output_format} | {cap} | {th if isinstance(th, str) else th['type']} |")
    L += ["", f"Items: {len(d['items'])} (6 presets, 6 batch items) × {d['repeats']} repeats = {d['planned_runs']} planned runs. "
          f"Anthropic calls: explicit timeouts {d['timeouts_s']}, max_retries {d['max_retries']}, no caching. Free-text arms are read by a blind "
          f"extraction judge ({d['judge_model']}, {d['judge_passes']} pass) and by the app's regex extractor.", ""]

    L += ["## Data quality", "",
          f"- Run records: {dq['run_records']} (current ok: {dq['ok_current_runs']} of {d['planned_runs']} planned; error records: {dq['error_records']}; "
          f"superseded ok records: {dq['superseded_records']}).",
          f"- Gemini: {dq['gemini']['ok']} of {dq['gemini']['planned']} planned runs succeeded ({dq['gemini']['records']} records).",
          f"- Truncated (stop_reason max_tokens) among current ok runs: {dq['truncated']}. Model mismatches (returned ≠ intended): {len(dq['model_mismatches'])}"
          + (f" — {', '.join(dq['model_mismatches'][:10])}" if dq["model_mismatches"] else "") + ".",
          f"- Extractions: {dq['extraction_ok_current']} current ok of {dq['extractions_planned']} planned ({dq['extraction_records']} records, {dq['extraction_errors']} errors).",
          *([f"- Issue: the first extraction pass was interrupted — {h['usage_limit']} calls failed because the API usage limit was reached "
             f"({', '.join(h['dates'])}); {h['retried_to_ok']} of the {h['calls']} failed calls were retried and completed. The error records stay in "
             "`extractions.jsonl` as history; only the latest ok record per call is used."]
            if (h := dq.get("extraction_error_history") or {}).get("usage_limit") else []),
          f"- Extracted fields whose evidence is not a verbatim quote of the response: {len(dq['extraction_evidence_not_verbatim'])}"
          + (f" — {', '.join(f'{c} {f}' for c, f in dq['extraction_evidence_not_verbatim'][:8])}" if dq["extraction_evidence_not_verbatim"] else "") + ".",
          f"- Missing planned runs: {len(dq['missing_runs'])}." + (f" First: {', '.join(dq['missing_runs'][:6])}" if dq["missing_runs"] else "")]
    if dq["errors_by_arm"]:
        L.append(f"- Errors by arm: {dq['errors_by_arm']}")
        for arm, msg in dq["error_messages"][:12]:
            L.append(f"  - `{arm}`: {_clip(msg, 160)}")
    L.append("")

    L += ["## Per arm", "", "| arm | runs | field accuracy | items fully correct | truncated | stop reasons | output tok median (range) | thinking tok median | in:out median | cost / 1k items | latency ms median |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for a in ARM_IDS:
        b = r["arms"][a]
        acc = b.get("accuracy") or {}
        L.append(f"| `{a}` | {b['runs']} | {_pct(acc.get('field_accuracy'))} | {acc.get('items_fully_correct', '—')}/{acc.get('items', 0)} | {b['truncated']} | "
                 f"{', '.join(f'{k}: {v}' for k, v in b['stop_reasons'].items()) or '—'} | {_rng(b['output_tokens'])} | {_num(b['thinking_tokens']['median'])} | "
                 f"{_ratio(b['io_ratio']['median'])} | {_usd(b['cost_per_1k_items_usd'])} | {_num(b['latency_ms']['median'])} |")
    L += ["", "Free-text arms are scored from the judge's extraction; schema and Gemini arms from the structured output, as the app does it.", ""]
    L += ["| schema arm | cost / 1k items | Batch API (50%, computed) | schema parse failures | max output tok (rerun cap / app cap) |", "|---|---|---|---|---|"]
    for a in ("sonnet_schema", "haiku_schema"):
        b = r["arms"][a]
        cap = b.get("output_tokens_max_vs_app_cap") or {}
        L.append(f"| `{a}` | {_usd(b['cost_per_1k_items_usd'])} | {_usd(b.get('batch_cost_per_1k_items_usd_computed'))} | {b.get('schema_parse_failures', '—')} | "
                 f"{_num(cap.get('max_output_tokens'))} ({cap.get('rerun_cap')} / {cap.get('app_cap')}) |")
    g = r["arms"]["gemini_decision"]
    L += ["", f"Gemini input tokens possibly estimated by the app (len/3.8 when usage is missing): {g.get('input_tokens_possibly_estimated', 0)} runs.", ""]

    L += ["### Free-text arms: judge vs regex", "", "| arm | judge accuracy | regex accuracy | stated / not_stated / ambiguous | extractors agree (fields) |", "|---|---|---|---|---|"]
    for a in FREE_TEXT_ARMS:
        b = r["arms"][a]
        vc = b.get("judge_value_counts") or {}
        ag = b.get("extractor_agreement") or {}
        L.append(f"| `{a}` | {_pct((b.get('accuracy') or {}).get('field_accuracy'))} | {_pct((b.get('regex_accuracy') or {}).get('field_accuracy'))} | "
                 f"{vc.get('stated', '—')} / {vc.get('not_stated', '—')} / {vc.get('ambiguous', '—')} | "
                 + (f"{ag['agree']}/{ag['fields']} (same {ag['same_value']}, different {ag['different_value']}, regex only {ag['regex_only']}, judge only {ag['judge_only']}, neither {ag['neither']})" if ag else "—") + " |")
    L.append("")

    L += ["## Per arm × sub-task", "", "| arm | sub-task | runs | field accuracy | items fully correct | truncated | output tok median (range) | in:out median | cost / 1k items |", "|---|---|---|---|---|---|---|---|---|"]
    for a in ARM_IDS:
        for s in SUB_TASKS:
            b = r["arms"][a]["by_sub_task"][s]
            acc = b.get("accuracy") or {}
            L.append(f"| `{a}` | {s} | {b['runs']} | {_pct(acc.get('field_accuracy'))} | {acc.get('items_fully_correct', '—')}/{acc.get('items', 0)} | {b['truncated']} | "
                     f"{_rng(b['output_tokens'])} | {_ratio(b['io_ratio']['median'])} | {_usd(b['cost_per_1k_items_usd'])} |")
    L.append("")
    L += ["### By field", "", "| arm | " + " | ".join(f for s in SUB_TASKS for f in ground_truth(next(i['id'] for i in ITEMS if i['sub_task'] == s))) + " |"]
    fields = [f for s in SUB_TASKS for f in ground_truth(next(i["id"] for i in ITEMS if i["sub_task"] == s))]
    L.append("|---|" + "---|" * len(fields))
    for a in ARM_IDS:
        bf = (r["arms"][a].get("accuracy") or {}).get("by_field") or {}
        L.append(f"| `{a}` | " + " | ".join((f"{bf[f]['hits']}/{bf[f]['total']}" if f in bf else "—") for f in fields) + " |")
    L += ["", "### Presets vs batch items", "", "| arm | preset accuracy | batch accuracy | preset input tok median | batch input tok median |", "|---|---|---|---|---|"]
    for a in ARM_IDS:
        bg = r["arms"][a]["by_group"]
        L.append(f"| `{a}` | {_pct((bg['preset'].get('accuracy') or {}).get('field_accuracy'))} | {_pct((bg['batch'].get('accuracy') or {}).get('field_accuracy'))} | "
                 f"{_num(bg['preset']['input_tokens']['median'])} | {_num(bg['batch']['input_tokens']['median'])} |")
    L.append("")

    L += ["## Levers", "", "| lever | from → to | cost / 1k items | cost change | field accuracy | accuracy change |", "|---|---|---|---|---|---|"]
    for lv in r["levers"]:
        L.append(f"| {lv['lever']} | `{lv['from']}` → `{lv['to']}` | {_usd(lv['cost_from'])} → {_usd(lv['cost_to'])} | {_num(lv['cost_change_pct'], '{:+.1f}%')} | "
                 f"{_pct(lv['accuracy_from'])} → {_pct(lv['accuracy_to'])} | {_num(lv['accuracy_change_pp'], '{:+.1f} pp')} |")
    L.append("")

    oc = r["original_capture"]
    L += ["## Old vs new scoring, original capture beside the rerun", "",
          "Original capture = the 24 stored prose responses of the first capture (`replays/cat1_original_capture.json`, a verbatim copy of the golden replays before they were rebuilt from this experiment; presets `raw_text_preview`, batch `sonnet_raw_text` / "
          f"`haiku_naive_raw_text`), captured at max_tokens {STORED_PROSE_CAP}; truncation is inferred from output tokens ≥ {STORED_PROSE_CAP} (no stop reason was stored). "
          "Old scoring = the app's regex extractor; new scoring = the blind extraction judge.", "",
          "| arm | source | responses | truncated | regex (old) accuracy | judge (new) accuracy | output tok median (range) | cost / 1k items |", "|---|---|---|---|---|---|---|---|"]
    for a in ("sonnet_report", "haiku_report"):
        o = oc[a]
        b = r["arms"][a]
        L.append(f"| `{a}` | original capture | {o['responses']} | {o['truncated_at_2048']} | {_pct((o.get('regex_accuracy') or {}).get('field_accuracy'))} | "
                 f"{_pct((o.get('judge_accuracy') or {}).get('field_accuracy'))} | {_rng(o['output_tokens'])} | {_usd(o['cost_per_1k_items_usd'])} |")
        L.append(f"| `{a}` | rerun | {b['runs']} | {b['truncated']} | {_pct((b.get('regex_accuracy') or {}).get('field_accuracy'))} | "
                 f"{_pct((b.get('accuracy') or {}).get('field_accuracy'))} | {_rng(b['output_tokens'])} | {_usd(b['cost_per_1k_items_usd'])} |")
    for a in ("haiku_schema", "gemini_decision"):
        o = oc[a]
        b = r["arms"][a]
        L.append(f"| `{a}` | original capture | {o['responses']} | — | n/a (structured) | {_pct((o.get('accuracy') or {}).get('field_accuracy'))} | {_rng(o['output_tokens'])} | {_usd(o['cost_per_1k_items_usd'])} |")
        L.append(f"| `{a}` | rerun | {b['runs']} | {b['truncated']} | n/a (structured) | {_pct((b.get('accuracy') or {}).get('field_accuracy'))} | {_rng(b['output_tokens'])} | {_usd(b['cost_per_1k_items_usd'])} |")
    hc = oc["haiku_schema"].get("max_output_tokens_vs_cap") or {}
    L += ["", f"Original capture, `haiku_schema`: max output {hc.get('max')} tokens vs the app's cap {hc.get('cap')}.", ""]
    for a in ("sonnet_report", "haiku_report"):
        ag = oc[a].get("extractor_agreement")
        if ag:
            L.append(f"- Original capture `{a}`: extractors agree on {ag['agree']}/{ag['fields']} fields (same {ag['same_value']}, different {ag['different_value']}, "
                     f"regex only {ag['regex_only']}, judge only {ag['judge_only']}, neither {ag['neither']}).")
    L.append("")

    sc = r["schema_check"]
    L += ["## Judge check: schema outputs rendered as text", "",
          f"Seeded sample (seed {SCHEMA_CHECK_SEED}) of {sc['planned']} `*_schema` outputs rendered as `field: value` lines and extracted by the judge: "
          f"{sc['judged']} judged, {sc['agree']}/{sc['fields']} fields agree with the structured values."]
    for c in sc["disagreements"][:20]:
        L.append(f"- `{c['run_id']}` {c['field']}: structured {c['structured']!r}, extracted {c['extracted']!r}")
    L.append("")

    dp = r["deck_profile"]
    bands = dp["deck_bands"]
    L += ["## Deck profile", "",
          f"Deck: {bands['input_tokens'][0]:,}–{bands['input_tokens'][1]:,} input tokens, {bands['output_tokens'][0]}–{bands['output_tokens'][1]} output tokens, "
          f"{bands['io_ratio'][0]}:1–{bands['io_ratio'][1]}:1.", ""]
    if dp["fit"]:
        L.append(f"Raw payload tokens estimated from a linear fit of input tokens on payload characters ({dp['fit_source']}): "
                 f"{dp['fit']['tokens_per_char']:.3f} tokens/char, prompt overhead ≈ {dp['fit']['overhead_tokens']:,.0f} tokens. Payload tokens: {_rng(dp['payload_tokens_dist'])}.")
        L.append("")
        L.append("| item | payload chars | payload tokens (fit) |")
        L.append("|---|---|---|")
        for iid in ITEM_IDS:
            L.append(f"| {iid} | {len(ITEM_BY_ID[iid]['payload']):,} | {_num(dp['payload_tokens'][iid])} |")
    L += ["", "| arm | input tok median (range) | output tok median (range) | in:out median (range) |", "|---|---|---|---|"]
    for a in ARM_IDS:
        pa = dp["per_arm"][a]
        L.append(f"| `{a}` | {_rng(pa['input_tokens'])} | {_rng(pa['output_tokens'])} | {_rng(pa['io_ratio'], '{:,.1f}')} |")
    L.append("")

    rv = r["review"]
    L += ["## For lead review", "", f"### Schema and Gemini fields that did not match ({len(rv['structured_misses'])})", ""]
    if rv["structured_misses"]:
        L += ["| run | field | expected | returned |", "|---|---|---|---|"]
        L += [f"| `{m['run_id']}` | {m['field']} | {m['expected']} | {m['returned']} |" for m in rv["structured_misses"]]
    else:
        L.append("None.")
    L += ["", f"### Judge `ambiguous` fields ({len(rv['ambiguous'])})", ""]
    if rv["ambiguous"]:
        L += ["| response | field | evidence |", "|---|---|---|"]
        L += [f"| `{x['run_id']}` | {x['field']} | {_clip(x['evidence'])} |" for x in rv["ambiguous"]]
    else:
        L.append("None.")
    L += ["", f"### Extractor disagreements, regex vs judge ({len(rv['extractor_disagreements'])})", ""]
    if rv["extractor_disagreements"]:
        L += ["| response | field | expected | regex | judge | judge evidence |", "|---|---|---|---|---|---|"]
        L += [f"| `{x['run_id']}` | {x['field']} | {x['expected']} | {x['regex']} | {x['judge'] if x['judge'] is not None else x['judge_raw']} | {_clip(x['evidence'])} |"
              for x in rv["extractor_disagreements"]]
    else:
        L.append("None.")
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------------------------------
# App-facing portfolio (replays/cat1_ablation_summary.json)
# --------------------------------------------------------------------------------------------------

summarise = analyse  # the analysis path shared by analyze_cat1_ablation.py and the app summary

PORTFOLIO_SCHEMA_VERSION = 1
GOLDEN_REPEAT_INDEX = 0
# Fixed, pre-declared mapping arm -> app rung for the golden replays (never chosen by outcome).
APP_RUNG_FOR_ARM: dict[str, str] = {
    "sonnet_report": "sonnet_naive",
    "haiku_report": "haiku_naive",
    "haiku_schema": "haiku_calibrated",
    "gemini_decision": "gemini_decision",
}
ARM_PLAIN: dict[str, tuple[str, str]] = {
    "sonnet_report": ("Sonnet write-up", "Large model writes today's four-part analysis in free text"),
    "sonnet_classify_text": ("Sonnet classification, plain text", "Large model answers only the fields, one `field: value` line each"),
    "sonnet_schema": ("Sonnet classification, JSON schema", "Large model answers only the fields through the enforced JSON schema"),
    "haiku_report": ("Haiku write-up", "Small model writes the same four-part analysis in free text"),
    "haiku_classify_text": ("Haiku classification, plain text", "Small model answers only the fields, one `field: value` line each"),
    "haiku_schema": ("Haiku classification, JSON schema", "Small model answers only the fields through the enforced JSON schema"),
    "gemini_decision": ("Gemini decision", "Decision model answers fixed questions; no text is generated"),
}
LEVER_PLAIN: dict[str, tuple[str, str]] = {
    "write-up → classification-only text (sonnet)": ("ask_less", "Ask for the classification instead of a write-up (Sonnet)"),
    "write-up → classification-only text (haiku)": ("ask_less", "Ask for the classification instead of a write-up (Haiku)"),
    "text → schema (sonnet)": ("schema", "Enforce a JSON schema instead of plain-text lines (Sonnet)"),
    "text → schema (haiku)": ("schema", "Enforce a JSON schema instead of plain-text lines (Haiku)"),
    "Sonnet → Haiku (report)": ("model", "Switch Sonnet → Haiku (write-up)"),
    "Sonnet → Haiku (classify_text)": ("model", "Switch Sonnet → Haiku (classification, plain text)"),
    "Sonnet → Haiku (schema)": ("model", "Switch Sonnet → Haiku (classification, JSON schema)"),
    "Haiku schema → Gemini decision": ("gemini", "Switch Haiku JSON schema → Gemini decision"),
    "whole stack: Sonnet write-up → Haiku schema": ("whole_stack", "All of it: Sonnet write-up → Haiku JSON schema"),
}
FIELD_PLAIN: dict[str, str] = {
    "queue": "queue", "priority": "priority", "auto_action": "action", "contains_pii": "contains personal data",
    "leaf_category": "category", "compliance_status": "publishing status", "contradiction_detected": "contradiction found",
}
USAGE_LIMIT_MARKER = "usage limits"


def _extraction_error_history(extraction_records: Sequence[dict[str, Any]], ok_by_call: dict[str, Any]) -> dict[str, Any]:
    """Failed extraction calls: how many hit the API usage limit, on which days, and how many were later retried to ok."""
    errs = [r for r in extraction_records if r.get("status") != "ok"]
    limited = [r for r in errs if USAGE_LIMIT_MARKER in (r.get("error_message") or "")]
    calls = sorted({r["call_id"] for r in errs})
    return {"records": len(errs), "calls": len(calls), "usage_limit": len(limited),
            "dates": sorted({(r.get("started_at") or "")[:10] for r in limited if r.get("started_at")}),
            "retried_to_ok": sum(1 for c in calls if c in ok_by_call)}


def _pending_reason(errors: Sequence[dict[str, Any]]) -> str | None:
    """Why extraction calls are still pending, read from their error records."""
    if not errors:
        return None
    limited = [e for e in errors if USAGE_LIMIT_MARKER in (e.get("error_message") or "")]
    if limited:
        day = max((e.get("started_at") or "")[:10] for e in limited)
        return f"pending: API usage limit reached on {day}"
    return "pending: the extraction call failed and will be retried"


def _acc_cell(acc: dict[str, Any] | None) -> dict[str, Any]:
    if not acc:
        return {"fields_correct": None, "fields_total": None, "field_accuracy_pct": None, "wilson95": None, "items_fully_correct": None, "items": 0}
    fa = acc["field_accuracy"]
    return {"fields_correct": fa["hits"], "fields_total": fa["total"], "field_accuracy_pct": fa["rate"] * 100 if fa["rate"] is not None else None,
            "wilson95": [x * 100 for x in fa["wilson95"]] if fa["wilson95"] else None,
            "items_fully_correct": acc["items_fully_correct"], "items": acc["items"]}


def build_ablation_portfolio(run_records: Sequence[dict[str, Any]], extraction_records: Sequence[dict[str, Any]], *,
                             golden: dict[str, Any] | None = None, source_files: dict[str, str] | None = None,
                             golden_run_ids: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    """Compact app-facing summary built from `summarise()` (the path analyze_cat1_ablation.py uses)."""
    g = golden or _golden()
    s = summarise(run_records, extraction_records, golden=g)
    extraction_records = list(extraction_records)
    plan = plan_extractions(extraction_targets(latest_ok_current(run_records), g))
    ok_ext = latest_ok_extractions(extraction_records, plan)
    ext_errors = {r["call_id"]: r for r in extraction_records if r.get("status") != "ok"}

    def pending_for(source: str) -> dict[str, Any]:
        calls = [p["call_id"] for p in plan if p["source"] == source]
        done = [c for c in calls if c in ok_ext]
        errs = [ext_errors[c] for c in calls if c not in ok_ext and c in ext_errors]
        pend = len(calls) - len(done)
        return {"planned": len(calls), "done": len(done), "pending": pend,
                "status": "complete" if pend == 0 else (_pending_reason(errs) or "pending: not yet run")}

    arms = []
    for a in ARMS:
        b = s["arms"][a.arm_id]
        label, what = ARM_PLAIN[a.arm_id]
        cell = {
            "arm_id": a.arm_id, "label": label, "what": what,
            "model": {"sonnet": "Sonnet 5.5", "haiku": "Haiku 5.5", "gemini": "Gemini Decision 1"}[a.model_key],
            "task": a.task, "output_format": a.output_format,
            "runnable_in_app": a.arm_id in APP_RUNG_FOR_ARM, "app_rung_id": APP_RUNG_FOR_ARM.get(a.arm_id),
            "given_allowed_labels": a.task != "report",
            "scored_by": "reader_model" if a.arm_id in FREE_TEXT_ARMS else "structured_output",
            "max_tokens": CAPS.get(a.task), "thinking": (THINKING.get(a.model_key) or {}).get("type"),
            "runs": b["runs"], "scored_runs": b["scored_runs"],
            **_acc_cell(b.get("accuracy")),
            "by_field": {f: {"hits": v["hits"], "total": v["total"]} for f, v in ((b.get("accuracy") or {}).get("by_field") or {}).items()},
            "by_sub_task": {st: _acc_cell(x.get("accuracy")) for st, x in b["by_sub_task"].items()},
            "by_group": {gr: {**_acc_cell(x.get("accuracy")), "input_tokens_median": x["input_tokens"]["median"]} for gr, x in b["by_group"].items()},
            "cost_per_1k_items_usd": b["cost_per_1k_items_usd"],
            "batch_cost_per_1k_items_usd_computed": b.get("batch_cost_per_1k_items_usd_computed"),
            "input_tokens_median": b["input_tokens"]["median"], "input_tokens_min": b["input_tokens"]["min"], "input_tokens_max": b["input_tokens"]["max"],
            "output_tokens_median": b["output_tokens"]["median"], "output_tokens_min": b["output_tokens"]["min"], "output_tokens_max": b["output_tokens"]["max"],
            "thinking_tokens_total": sum(int(x["run"].get("thinking_tokens") or 0) for x in s_runs_for(run_records, a.arm_id)),
            "io_ratio_median": b["io_ratio"]["median"],
            "latency_ms_median": b["latency_ms"]["median"],
            "truncated": b["truncated"], "stop_reasons": b["stop_reasons"], "model_mismatches": b["model_mismatches"],
            "schema_parse_failures": b.get("schema_parse_failures"),
        }
        if a.arm_id in FREE_TEXT_ARMS:
            ra = _acc_cell(b.get("regex_accuracy"))
            cell["keyword_fields_correct"] = ra["fields_correct"]
            cell["keyword_field_accuracy_pct"] = ra["field_accuracy_pct"]
            cell["reader_value_counts"] = b.get("judge_value_counts")
            cell["extractor_agreement"] = b.get("extractor_agreement")
        arms.append(cell)
    by_id = {c["arm_id"]: c for c in arms}

    levers = []
    for lv in s["levers"]:
        kind, label = LEVER_PLAIN.get(lv["lever"], ("other", lv["lever"]))
        fa, fb = by_id[lv["from"]], by_id[lv["to"]]
        levers.append({"lever": lv["lever"], "kind": kind, "label": label, "from_arm": lv["from"], "to_arm": lv["to"],
                       "cost_from": lv["cost_from"], "cost_to": lv["cost_to"], "cost_change_pct": lv["cost_change_pct"],
                       "fields_from": fa["fields_correct"], "fields_to": fb["fields_correct"], "fields_total": fb["fields_total"],
                       "accuracy_change_pp": lv["accuracy_change_pp"],
                       "comparable_accuracy": ARM_BY_ID[lv["from"]].task != "report" and ARM_BY_ID[lv["to"]].task != "report"})

    # Where the structured and classification versions missed (grouped over repeats)
    misses: dict[tuple, dict[str, Any]] = {}
    sr = scored_runs(run_records, extraction_records, g)
    for rid, x in sr["runs"].items():
        r = x["run"]
        if ARM_BY_ID[r["arm_id"]].task == "report" or not x["scores"]:
            continue
        for f, v in x["scores"]["fields"].items():
            if v["matched"]:
                continue
            key = (r["arm_id"], r["item_id"], f, json.dumps(v["expected"]), json.dumps(v["actual"]))
            m = misses.setdefault(key, {"arm_id": r["arm_id"], "item_id": r["item_id"], "item_title": ITEM_BY_ID[r["item_id"]]["title"],
                                        "sub_task": r["sub_task"], "field": f, "field_label": FIELD_PLAIN.get(f, f),
                                        "expected": v["expected"], "returned": v["actual"], "repeats": []})
            m["repeats"].append(r["repeat_index"])
    miss_list = sorted(misses.values(), key=lambda m: (ARM_IDS.index(m["arm_id"]), m["item_id"], m["field"]))
    for m in miss_list:
        m["repeats"] = sorted(m["repeats"])
        m["runs_missed"] = len(m["repeats"])
        m["runs_total"] = sum(1 for x in sr["runs"].values() if x["run"]["arm_id"] == m["arm_id"] and x["run"]["item_id"] == m["item_id"])

    oc = s["original_capture"]
    gold_pending = pending_for("golden")
    check_pending = pending_for("schema_check")
    original = []
    for a in ("sonnet_report", "haiku_report"):
        o = oc[a]
        ra = _acc_cell(o.get("regex_accuracy"))
        ja = _acc_cell(o.get("judge_accuracy")) if gold_pending["pending"] == 0 else _acc_cell(None)
        original.append({"arm_id": a, "app_rung_id": APP_RUNG_FOR_ARM[a], "responses": o["responses"], "truncated_at_cap": o["truncated_at_2048"],
                         "cap": STORED_PROSE_CAP, "output_tokens_median": o["output_tokens"]["median"], "cost_per_1k_items_usd": o["cost_per_1k_items_usd"],
                         "keyword_fields_correct": ra["fields_correct"], "fields_total": ra["fields_total"],
                         "keyword_field_accuracy_pct": ra["field_accuracy_pct"],
                         "reader_fields_correct": ja["fields_correct"], "reader_field_accuracy_pct": ja["field_accuracy_pct"],
                         "reader_status": gold_pending["status"] if gold_pending["pending"] else "complete",
                         "extractor_agreement": o.get("extractor_agreement") if gold_pending["pending"] == 0 else None})
    for a in ("haiku_schema", "gemini_decision"):
        o = oc[a]
        ac = _acc_cell(o.get("accuracy"))
        original.append({"arm_id": a, "app_rung_id": APP_RUNG_FOR_ARM[a], "responses": o["responses"], "truncated_at_cap": None,
                         "cap": APP_SCHEMA_CAP if a == "haiku_schema" else None, "output_tokens_median": o["output_tokens"]["median"],
                         "output_tokens_max": o["output_tokens"]["max"], "cost_per_1k_items_usd": o["cost_per_1k_items_usd"],
                         "fields_correct": ac["fields_correct"], "fields_total": ac["fields_total"], "field_accuracy_pct": ac["field_accuracy_pct"]})

    scoring = []
    for a in FREE_TEXT_ARMS:
        c = by_id[a]
        scoring.append({"arm_id": a, "label": c["label"], "fields_total": c["fields_total"], "keyword_fields_correct": c["keyword_fields_correct"],
                        "keyword_field_accuracy_pct": c["keyword_field_accuracy_pct"], "reader_fields_correct": c["fields_correct"],
                        "reader_field_accuracy_pct": c["field_accuracy_pct"],
                        "difference_pp": (c["keyword_field_accuracy_pct"] - c["field_accuracy_pct"])
                        if c["keyword_field_accuracy_pct"] is not None and c["field_accuracy_pct"] is not None else None,
                        "extractor_agreement": c["extractor_agreement"], "reader_value_counts": c["reader_value_counts"]})

    sc = s["schema_check"]
    dq = s["data_quality"]
    dp = s["deck_profile"]
    report_counts = [by_id[a]["reader_value_counts"] or {} for a in ("sonnet_report", "haiku_report")]
    classify_texts = [x for x in sr["runs"].values() if ARM_BY_ID[x["run"]["arm_id"]].task == "classify_text"]
    return {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "source": "cat1 ablation (ablation.summarise)",
        "source_files": source_files or {},
        "items": len(ITEMS), "presets": sum(1 for i in ITEMS if i["group"] == "preset"), "batch_items": sum(1 for i in ITEMS if i["group"] == "batch"),
        "repeats": REPEATS, "runs_per_arm": len(ITEMS) * REPEATS, "planned_runs": s["design"]["planned_runs"], "ok_runs": dq["ok_current_runs"],
        "ground_truth_fields_per_repeat": s["design"]["ground_truth_fields"],
        "fields_per_arm": s["design"]["ground_truth_fields"] * REPEATS,
        "reader_model": qs.JUDGE_MODEL, "reader_passes": 1,
        "settings": {"caps": dict(CAPS), "timeouts_s": dict(TIMEOUTS_S), "max_retries": MAX_RETRIES, "thinking": dict(THINKING),
                     "app_caps_before": {"prose": STORED_PROSE_CAP, "schema": APP_SCHEMA_CAP}},
        "arms": arms,
        "levers": levers,
        "scoring_comparison": scoring,
        "write_up_note": {
            "never_given_allowed_labels": True,
            "ambiguous_fields": sum(c.get("ambiguous", 0) for c in report_counts),
            "not_stated_fields": sum(c.get("not_stated", 0) for c in report_counts),
            "fields_read": sum(sum(c.values()) for c in report_counts),
            "ambiguous_fields_per_arm": {a: (by_id[a]["reader_value_counts"] or {}).get("ambiguous") for a in ("sonnet_report", "haiku_report")},
            "example_ambiguous": next((x["evidence"] for x in s["review"]["ambiguous"] if x["evidence"]), None),
        },
        "classification_text_readable": {"answers": len(classify_texts),
                                         "every_field_stated": sum(1 for x in classify_texts if x["extraction"] and all(
                                             x["extraction"]["raw"][f]["value"] not in (NOT_STATED, AMBIGUOUS) for f in ground_truth(x["run"]["item_id"])))},
        "misses": miss_list,
        "original_capture": original,
        "original_capture_note": (f"First capture, kept in replays/cat1_original_capture.json: prose capped at {STORED_PROSE_CAP} output tokens, "
                                  f"schema at {APP_SCHEMA_CAP}; stop reasons were not stored, so truncation is inferred from output at the cap."),
        "pending": {
            "original_capture_reader": {**gold_pending, "what": "reader-model scoring of the 24 stored write-ups of the original capture"},
            "schema_as_text_check": {**check_pending, "what": "reader-model check on 20 JSON-schema answers rendered as plain text",
                                      "fields_agree": sc["agree"] if check_pending["pending"] == 0 else None,
                                      "fields": sc["fields"] if check_pending["pending"] == 0 else None},
        },
        "deck_profile": {
            "bands": {k: list(v) for k, v in DECK_PROFILE.items()},
            "payload_tokens_median": dp["payload_tokens_dist"]["median"], "payload_tokens_min": dp["payload_tokens_dist"]["min"],
            "payload_tokens_max": dp["payload_tokens_dist"]["max"], "fit": dp["fit"], "fit_source": dp["fit_source"],
            "per_arm": {a: {"input_tokens_median": v["input_tokens"]["median"], "output_tokens_median": v["output_tokens"]["median"],
                            "io_ratio_median": v["io_ratio"]["median"]} for a, v in dp["per_arm"].items()},
        },
        "data_quality": {
            "run_records": dq["run_records"], "ok_current_runs": dq["ok_current_runs"], "error_records": dq["error_records"],
            "superseded_records": dq["superseded_records"], "truncated": dq["truncated"], "model_mismatches": len(dq["model_mismatches"]),
            "gemini_ok": dq["gemini"]["ok"], "gemini_planned": dq["gemini"]["planned"],
            "gemini_input_tokens_possibly_estimated": s["arms"]["gemini_decision"].get("input_tokens_possibly_estimated", 0),
            "extraction_records": dq["extraction_records"], "extraction_ok_current": dq["extraction_ok_current"],
            "extractions_planned": dq["extractions_planned"], "extraction_errors": dq["extraction_errors"],
            "evidence_not_verbatim": len(dq["extraction_evidence_not_verbatim"]),
            "missing_runs": len(dq["missing_runs"]),
        },
        "run_ids": {a: sorted(r["run_id"] for r in latest_ok_current(run_records).values() if r["arm_id"] == a) for a in ARM_IDS},
        "extraction_history": {
            "error_records": len(extraction_records) - sum(1 for r in extraction_records if r.get("status") == "ok"),
            "error_reasons": sorted({(_pending_reason([r]) or "").removeprefix("pending: ") for r in extraction_records if r.get("status") != "ok"}),
            "retried_to_ok": sum(1 for cid in {r["call_id"] for r in extraction_records if r.get("status") != "ok"} if cid in ok_ext),
        },
        "golden_mapping": {
            "selection_rule": (f"fixed pre-declared mapping: repeat_index {GOLDEN_REPEAT_INDEX} of "
                               + ", ".join(f"{a} -> {r}" for a, r in APP_RUNG_FOR_ARM.items()) + " on all 12 items (not selected by outcome)"),
            "arm_to_rung": dict(APP_RUNG_FOR_ARM), "run_ids": golden_run_ids or {},
        },
    }


def s_runs_for(run_records: Sequence[dict[str, Any]], arm_id: str) -> list[dict[str, Any]]:
    return [{"run": r} for r in latest_ok_current(run_records).values() if r["arm_id"] == arm_id]
