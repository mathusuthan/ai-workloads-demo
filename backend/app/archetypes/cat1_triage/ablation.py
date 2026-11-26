"""Category 1 experiment: without and with the deck's lever (classification with a strict JSON schema), on both models.

Arms (same 12 items: 6 presets + 6 batch items, 3 repeats -> 144 runs):
  sonnet_report        Sonnet 5.5 · the app's four-part write-up prompt                · free text
  sonnet_schema        Sonnet 5.5 · the app's classification prompt + JSON schema        · strict JSON
  haiku_report         Haiku 5.5  · the app's four-part write-up prompt                 · free text
  haiku_schema         Haiku 5.5  · the app's classification prompt + JSON schema        · strict JSON
The harness can also run the plain-text classification lever (`OTHER_LEVER_ARMS`); its records are kept in
experiments/cat1_ablation/other_levers/ and are not part of the analysis.

Each Anthropic arm goes through the app's own wrapper (run_sonnet_naive / run_haiku_naive / run_haiku_calibrated)
with keyword overrides only (cap, prompt, model, timeout, max_retries=0, no silent tool fallback). Thinking stays
as the app configures it per model: Sonnet {"type": "between_tools"}, Haiku {"type": "disabled"}.

Scoring: schema arms field-by-field with the app's `evaluate_rung_accuracy`; free-text arms by a blind
reader model (Opus 5.5, the Category 2 judge settings, one pass) whose extracted values are compared by the same code.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Sequence

from app.archetypes.cat1_triage.accuracy import evaluate_rung_accuracy
from app.archetypes.cat1_triage.prompts import get_haiku_calibrated_system_prompt, get_sonnet_naive_system_prompt
from app.archetypes.cat1_triage.schemas import get_schema_for_subtask
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
ABLATION_GOLDEN_SOURCE = "cat1_ablation_repeat0"
SUMMARY_PATH = BACKEND_DIR / "replays" / "cat1_ablation_summary.json"

SONNET, HAIKU = "claude-sonnet-5-5", "claude-haiku-5-5"
REPEATS = 3
DEFAULT_RUN_MAX_USD = 6.0
DEFAULT_EXTRACT_MAX_USD = 8.0

CAPS = {"report": 8192, "classify_text": 1024, "schema": 512}
TIMEOUTS_S = {"report": 300.0, "classify_text": 120.0, "schema": 60.0}
MAX_RETRIES = 0  # nothing silently re-billed by the SDK
THINKING = {"sonnet": {"type": "between_tools"}, "haiku": {"type": "disabled"}}  # as the app configures each model

DECK_PROFILE = {"input_tokens": (500, 1500), "output_tokens": (10, 100), "io_ratio": (20, 50)}


@dataclass(frozen=True)
class Arm:
    arm_id: str
    model_key: str  # sonnet | haiku
    task: str  # report | classify_text | schema
    output_format: str  # free_text | json_schema | decisions_api


ARMS: tuple[Arm, ...] = (
    Arm("sonnet_report", "sonnet", "report", "free_text"),
    Arm("sonnet_schema", "sonnet", "schema", "json_schema"),
    Arm("haiku_report", "haiku", "report", "free_text"),
    Arm("haiku_schema", "haiku", "schema", "json_schema"),
)
# Other lever tried (valid runs kept in experiments/cat1_ablation/other_levers/, not analysed or shown).
OTHER_LEVER_ARMS: tuple[Arm, ...] = (
    Arm("sonnet_classify_text", "sonnet", "classify_text", "free_text"),
    Arm("haiku_classify_text", "haiku", "classify_text", "free_text"),
)
OTHER_LEVERS_DIR = EXPERIMENT_DIR / "other_levers"
ARM_IDS: tuple[str, ...] = tuple(a.arm_id for a in ARMS)
ARM_BY_ID = {a.arm_id: a for a in (*ARMS, *OTHER_LEVER_ARMS)}
FREE_TEXT_ARMS = tuple(a.arm_id for a in ARMS if a.output_format == "free_text")
STRUCTURED_ARMS = ("sonnet_schema", "haiku_schema")
MODEL_ID = {"sonnet": SONNET, "haiku": HAIKU}

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


def latest_ok_current(records: Iterable[dict[str, Any]], arm_ids: Sequence[str] = ARM_IDS) -> dict[str, dict[str, Any]]:
    """run_id -> latest ok record at the current settings, for the analysed arms (`ARM_IDS` by default)."""
    out: dict[str, dict[str, Any]] = {}
    for r in records:
        if r.get("status") == "ok" and r.get("arm_id") in arm_ids and not is_superseded(r):
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
        mid = SONNET if "sonnet" in mid else HAIKU
    return compute_run_finops(mid, int(rec.get("input_tokens") or 0), int(rec.get("output_tokens") or 0)).total_cost_usd


def is_ablation_golden(doc: dict[str, Any]) -> bool:
    return (doc.get("provenance") or {}).get("source") == ABLATION_GOLDEN_SOURCE


def _golden() -> dict[str, Any]:
    """The app's golden replays (replays/cat1_golden_replays.json): token sizes for dry-run estimates."""
    if GOLDEN_PATH.is_file():
        return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    return {"presets": {}, "batch_items": {}}


def _golden_rungs(g: dict[str, Any], item_id: str) -> dict[str, Any]:
    src = (g.get("presets") or {}).get(item_id) or (g.get("batch_items") or {}).get(item_id) or {}
    return src.get("rungs") or {}


def stored_input_tokens(item_id: str, golden: dict[str, Any] | None = None) -> dict[str, int]:
    """Measured input tokens of the golden replays: write-up (sonnet/haiku) and the schema rung."""
    r = _golden_rungs(golden or _golden(), item_id)
    return {"prose_sonnet": r["sonnet_naive"]["input_tokens"], "prose_haiku": r["haiku_naive"]["input_tokens"],
            "schema": r["haiku_calibrated"]["input_tokens"]}


TYPICAL_OUTPUT = {"report": 3500, "classify_text": 80, "schema": 110}  # assumption, labelled in the dry run


def estimate_run(planned: dict[str, Any], golden: dict[str, Any] | None = None, chars_per_token: float = 3.0) -> dict[str, Any]:
    arm = ARM_BY_ID[planned["arm_id"]]
    st = stored_input_tokens(planned["item_id"], golden)
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
    schema(arm, item, schema, model, fallback_models, max_tokens, thinking, timeout_s, max_retries) -> same"""

    prose: Callable[..., Awaitable[Any]]
    schema: Callable[..., Awaitable[Any]]


def make_app_call_paths(anthropic_key: str | None) -> CallPaths:
    from app.core.anthropic_service import run_haiku_calibrated, run_haiku_naive, run_sonnet_naive

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

    return CallPaths(prose=prose, schema=schema)


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
    """One run -> one record. Never raises; failures are error records."""
    rec = _base_run_record(p)
    arm = ARM_BY_ID[p["arm_id"]]
    item = ITEM_BY_ID[p["item_id"]]
    st = p["settings"]
    try:
        if True:
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


def extraction_targets(run_records: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """(source, id, sub_task, item_id, text) for every free-text run."""
    return [{"source": "run", "target_id": r["run_id"], "sub_task": r["sub_task"], "item_id": r["item_id"], "text": r.get("raw_text") or ""}
            for r in sorted(run_records.values(), key=lambda r: r["run_id"]) if r["arm_id"] in FREE_TEXT_ARMS]


def extraction_call_id(source: str, target_id: str) -> str:
    return f"extract:{source}:{target_id}"


def plan_extractions(targets: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    plan = []
    for t in targets:
        system, user = build_extraction_prompt(t["sub_task"], ITEM_BY_ID[t["item_id"]]["payload"], t["text"])
        plan.append({"call_id": extraction_call_id(t["source"], t["target_id"]), "task": "extraction", **t, "system": system, "user": user,
                     "schema": extraction_schema(t["sub_task"]), "text_sha256": _sha(t["text"]), "prompt_sha256": qs._sha(system, user)})
    return plan


EXTRA_BLINDING_TERMS: tuple[str, ...] = (*ARM_IDS, "schema", "thinking", "report_arm", "classify_text", "ground_truth", "ground truth",
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


def scored_runs(run_records: Sequence[dict[str, Any]], extraction_records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Every current ok run with its reader-model (free text) or structured score."""
    runs = latest_ok_current(run_records)
    plan = plan_extractions(extraction_targets(runs))
    ext = latest_ok_extractions(extraction_records, plan)
    out = {}
    for rid, r in runs.items():
        item, sub = r["item_id"], r["sub_task"]
        row: dict[str, Any] = {"run": r, "scores": None, "extraction": None}
        if r["arm_id"] in STRUCTURED_ARMS:
            row["scores"] = score_values(item, sub, r.get("structured_output") or {})
        else:
            e = ext.get(extraction_call_id("run", rid))
            if e:
                vals = extracted_values(e["parsed"], sub)
                row["extraction"] = {"values": vals, "raw": e["parsed"]["fields"]}
                row["scores"] = score_values(item, sub, vals)
        out[rid] = row
    return {"runs": out, "extractions": ext, "plan": plan}


def _main(by_task: dict[str, Any]) -> dict[str, Any]:
    """Settings of the displayed arms' tasks only (the other-lever task is not part of the analysis)."""
    tasks = {a.task for a in ARMS}
    return {k: v for k, v in by_task.items() if k in tasks}


def analyse(run_records: Sequence[dict[str, Any]], extraction_records: Sequence[dict[str, Any]] | None = None) -> dict[str, Any]:
    extraction_records = list(extraction_records or [])
    sr = scored_runs(run_records, extraction_records)
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
            b["extracted_runs"] = sum(1 for x in sel if x["extraction"])
            b["judge_value_counts"] = _value_class_counts(sel)
        if sel and sel[0]["run"]["arm_id"] in ("sonnet_schema", "haiku_schema"):
            b["schema_parse_failures"] = sum(1 for r in recs if not r.get("schema_parse_ok"))
            b["batch_cost_per_1k_items_usd_computed"] = b["cost_per_1k_items_usd"] * 0.5 if b["cost_per_1k_items_usd"] is not None else None
            b["output_tokens_max_vs_cap"] = {"max_output_tokens": b["output_tokens"]["max"], "cap": CAPS["schema"]}
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
        levers.append(lever(f"write-up → schema ({m})", f"{m}_report", f"{m}_schema"))
    for t in ("report", "schema"):
        levers.append(lever(f"Sonnet → Haiku ({t})", f"sonnet_{t}", f"haiku_{t}"))
    levers.append(lever("whole stack: Sonnet write-up → Haiku schema", "sonnet_report", "haiku_schema"))

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
    f_ = fit(pts)
    payload_tokens = {iid: (f_["tokens_per_char"] * len(ITEM_BY_ID[iid]["payload"]) if f_ else None) for iid in ITEM_IDS}
    deck = {"fit": f_, "fit_source": src, "payload_tokens": payload_tokens,
            "payload_tokens_dist": _dist([v for v in payload_tokens.values() if v is not None]),
            "per_arm": {a: {"input_tokens": arms[a]["input_tokens"], "output_tokens": arms[a]["output_tokens"], "io_ratio": arms[a]["io_ratio"]} for a in ARM_IDS},
            "deck_bands": DECK_PROFILE}

    # For lead review
    misses, ambiguous = [], []
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
    all_runs = list(run_records)
    return {
        "schema_version": SCHEMA_VERSION,
        "design": {"arms": [a.__dict__ for a in ARMS], "items": list(ITEM_IDS), "repeats": REPEATS, "planned_runs": len(plan_runs()),
                   "caps": _main(CAPS), "timeouts_s": _main(TIMEOUTS_S), "max_retries": MAX_RETRIES, "thinking": dict(THINKING),
                   "judge_model": qs.JUDGE_MODEL, "judge_passes": 1, "ground_truth_fields": sum(len(i["ground_truth"]) for i in ITEMS)},
        "data_quality": {
            "run_records": len(all_runs), "ok_current_runs": len(rows), "error_records": sum(1 for r in all_runs if r.get("status") != "ok"),
            "errors_by_arm": dict(Counter(r.get("arm_id") for r in all_runs if r.get("status") != "ok")),
            "error_messages": sorted({(r.get("arm_id"), (r.get("error_message") or "")[:160]) for r in all_runs if r.get("status") != "ok"}),
            "superseded_records": len(superseded_records(all_runs)),
            "missing_runs": sorted(p["run_id"] for p in plan_runs() if p["run_id"] not in rows),
            "truncated": sum(1 for x in rows.values() if x["run"].get("truncated")),
            "model_mismatches": sorted(rid for rid, x in rows.items() if x["run"].get("model_matches") is False),
            "extraction_records": len(extraction_records), "extraction_ok_current": len(sr["extractions"]),
            "extraction_errors": sum(1 for r in extraction_records if r.get("status") != "ok"),
            "extractions_planned": len(sr["plan"]),
            "extraction_evidence_not_verbatim": sorted((cid, f) for cid, e in sr["extractions"].items() for f in (e.get("evidence_not_verbatim") or [])),
        },
        "arms": arms,
        "levers": levers,
        "deck_profile": deck,
        "review": {"structured_misses": misses, "ambiguous": ambiguous},
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
    """For a judge dry run before the runs exist: report arms -> the golden replay's write-up of the same model and
    item; schema arms -> the golden Haiku schema output. Prompt sizes are therefore approximate."""
    g = golden or _golden()
    out = {}
    for p in plan_runs():
        arm = ARM_BY_ID[p["arm_id"]]
        rec = {**_base_run_record(p), "status": "ok", "standin": True}
        rungs = _golden_rungs(g, p["item_id"])
        so = (rungs.get("haiku_calibrated") or {}).get("structured_output") or {}
        if arm.task == "report":
            rung = "sonnet_naive" if arm.model_key == "sonnet" else "haiku_naive"
            rec["raw_text"] = (rungs.get(rung) or {}).get("raw_text_preview") or ""
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
    L += ["# Category 1: write-up vs classification with JSON schema, on Sonnet 5.5 and Haiku 5.5", "",
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
          f"reader model ({d['judge_model']}, {d['judge_passes']} pass). {READER_CHECK_NOTE}", ""]

    L += ["## Data quality", "",
          f"Runs: {dq['ok_current_runs']} of {d['planned_runs']} planned, all ok; {dq['truncated']} truncated; {len(dq['model_mismatches'])} model mismatches; "
          f"reader-model extractions: {dq['extraction_ok_current']} of {dq['extractions_planned']}; extracted fields whose evidence is not a verbatim quote: "
          f"{len(dq['extraction_evidence_not_verbatim'])}.", ""]

    L += ["## Per arm", "", "| arm | runs | field accuracy | items fully correct | truncated | stop reasons | output tok median (range) | thinking tok median | in:out median | cost / 1k items | latency ms median |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for a in ARM_IDS:
        b = r["arms"][a]
        acc = b.get("accuracy") or {}
        L.append(f"| `{a}` | {b['runs']} | {_pct(acc.get('field_accuracy'))} | {acc.get('items_fully_correct', '—')}/{acc.get('items', 0)} | {b['truncated']} | "
                 f"{', '.join(f'{k}: {v}' for k, v in b['stop_reasons'].items()) or '—'} | {_rng(b['output_tokens'])} | {_num(b['thinking_tokens']['median'])} | "
                 f"{_ratio(b['io_ratio']['median'])} | {_usd(b['cost_per_1k_items_usd'])} | {_num(b['latency_ms']['median'])} |")
    L += ["", "Free-text arms are scored from the judge's extraction; schema arms from the structured output, as the app does it.", ""]
    L += ["| schema arm | cost / 1k items | Batch API (50%, computed) | schema parse failures | max output tok (cap) |", "|---|---|---|---|---|"]
    for a in ("sonnet_schema", "haiku_schema"):
        b = r["arms"][a]
        cap = b.get("output_tokens_max_vs_cap") or {}
        L.append(f"| `{a}` | {_usd(b['cost_per_1k_items_usd'])} | {_usd(b.get('batch_cost_per_1k_items_usd_computed'))} | {b.get('schema_parse_failures', '—')} | "
                 f"{_num(cap.get('max_output_tokens'))} ({cap.get('cap')}) |")
    L.append("")

    L += ["### Free-text arms: what the reader model found", "", "| arm | field accuracy | stated / not_stated / ambiguous |", "|---|---|---|"]
    for a in FREE_TEXT_ARMS:
        b = r["arms"][a]
        vc = b.get("judge_value_counts") or {}
        L.append(f"| `{a}` | {_pct((b.get('accuracy') or {}).get('field_accuracy'))} | "
                 f"{vc.get('stated', '—')} / {vc.get('not_stated', '—')} / {vc.get('ambiguous', '—')} |")
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

    L += ["## Differences between the four cells", "", "| change | from → to | cost / 1k items | cost change | field accuracy | accuracy change |", "|---|---|---|---|---|---|"]
    for lv in r["levers"]:
        L.append(f"| {lv['lever']} | `{lv['from']}` → `{lv['to']}` | {_usd(lv['cost_from'])} → {_usd(lv['cost_to'])} | {_num(lv['cost_change_pct'], '{:+.1f}%')} | "
                 f"{_pct(lv['accuracy_from'])} → {_pct(lv['accuracy_to'])} | {_num(lv['accuracy_change_pp'], '{:+.1f} pp')} |")
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
    L += ["## For lead review", "", f"### Schema fields that did not match ({len(rv['structured_misses'])})", ""]
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
    "sonnet_schema": "sonnet_calibrated",
    "haiku_schema": "haiku_calibrated",
}
ARM_PLAIN: dict[str, tuple[str, str]] = {
    "sonnet_report": ("Sonnet write-up", "Large model writes today's four-part analysis in free text"),
    "sonnet_schema": ("Sonnet classification, JSON schema", "Large model answers only the fields through the enforced JSON schema"),
    "haiku_report": ("Haiku write-up", "Small model writes the same four-part analysis in free text"),
    "haiku_schema": ("Haiku classification, JSON schema", "Small model answers only the fields through the enforced JSON schema"),
}
LEVER_PLAIN: dict[str, tuple[str, str]] = {
    "write-up → schema (sonnet)": ("with_vs_without", "Write-up → classification with JSON schema (Sonnet)"),
    "write-up → schema (haiku)": ("with_vs_without", "Write-up → classification with JSON schema (Haiku)"),
    "Sonnet → Haiku (report)": ("model", "Sonnet → Haiku (write-up)"),
    "Sonnet → Haiku (schema)": ("model", "Sonnet → Haiku (classification with JSON schema)"),
    "whole stack: Sonnet write-up → Haiku schema": ("whole_stack", "Sonnet write-up → Haiku classification with JSON schema"),
}
FIELD_PLAIN: dict[str, str] = {
    "queue": "queue", "priority": "priority", "auto_action": "action", "contains_pii": "contains personal data",
    "leaf_category": "category", "compliance_status": "publishing status", "contradiction_detected": "contradiction found",
}
# Method note: the reader model was checked once on JSON-schema answers rewritten as `field: value` text (20 answers,
# 100 fields with known values) and read every field back correctly.
READER_CHECK_NOTE = ("The reader model was checked on 100 known fields (20 JSON answers rewritten as plain text) and read all of them correctly.")


def _acc_cell(acc: dict[str, Any] | None) -> dict[str, Any]:
    if not acc:
        return {"fields_correct": None, "fields_total": None, "field_accuracy_pct": None, "wilson95": None, "items_fully_correct": None, "items": 0}
    fa = acc["field_accuracy"]
    return {"fields_correct": fa["hits"], "fields_total": fa["total"], "field_accuracy_pct": fa["rate"] * 100 if fa["rate"] is not None else None,
            "wilson95": [x * 100 for x in fa["wilson95"]] if fa["wilson95"] else None,
            "items_fully_correct": acc["items_fully_correct"], "items": acc["items"]}


def build_ablation_portfolio(run_records: Sequence[dict[str, Any]], extraction_records: Sequence[dict[str, Any]], *,
                             source_files: dict[str, str] | None = None,
                             golden_run_ids: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    """Compact app-facing summary built from `summarise()` (the path analyze_cat1_ablation.py uses)."""
    s = summarise(run_records, extraction_records)
    extraction_records = list(extraction_records)

    arms = []
    for a in ARMS:
        b = s["arms"][a.arm_id]
        label, what = ARM_PLAIN[a.arm_id]
        cell = {
            "arm_id": a.arm_id, "label": label, "what": what,
            "model": {"sonnet": "Sonnet 5.5", "haiku": "Haiku 5.5"}[a.model_key],
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
            cell["reader_value_counts"] = b.get("judge_value_counts")
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
    sr = scored_runs(run_records, extraction_records)
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

    dq = s["data_quality"]
    dp = s["deck_profile"]
    report_counts = [by_id[a]["reader_value_counts"] or {} for a in ("sonnet_report", "haiku_report")]
    return {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "source": "cat1 ablation (ablation.summarise)",
        "source_files": source_files or {},
        "items": len(ITEMS), "presets": sum(1 for i in ITEMS if i["group"] == "preset"), "batch_items": sum(1 for i in ITEMS if i["group"] == "batch"),
        "repeats": REPEATS, "runs_per_arm": len(ITEMS) * REPEATS, "planned_runs": s["design"]["planned_runs"], "ok_runs": dq["ok_current_runs"],
        "ground_truth_fields_per_repeat": s["design"]["ground_truth_fields"],
        "fields_per_arm": s["design"]["ground_truth_fields"] * REPEATS,
        "reader_model": qs.JUDGE_MODEL, "reader_passes": 1,
        "settings": {"caps": _main(CAPS), "timeouts_s": _main(TIMEOUTS_S), "max_retries": MAX_RETRIES, "thinking": dict(THINKING)},
        "reader_check_note": READER_CHECK_NOTE,
        "arms": arms,
        "levers": levers,
        "write_up_note": {
            "never_given_allowed_labels": True,
            "ambiguous_fields": sum(c.get("ambiguous", 0) for c in report_counts),
            "not_stated_fields": sum(c.get("not_stated", 0) for c in report_counts),
            "fields_read": sum(sum(c.values()) for c in report_counts),
            "ambiguous_fields_per_arm": {a: (by_id[a]["reader_value_counts"] or {}).get("ambiguous") for a in ("sonnet_report", "haiku_report")},
            "example_ambiguous": next((x["evidence"] for x in s["review"]["ambiguous"] if x["evidence"]), None),
        },
        "misses": miss_list,
        "deck_profile": {
            "bands": {k: list(v) for k, v in DECK_PROFILE.items()},
            "payload_tokens_median": dp["payload_tokens_dist"]["median"], "payload_tokens_min": dp["payload_tokens_dist"]["min"],
            "payload_tokens_max": dp["payload_tokens_dist"]["max"], "fit": dp["fit"], "fit_source": dp["fit_source"],
            "per_arm": {a: {"input_tokens_median": v["input_tokens"]["median"], "output_tokens_median": v["output_tokens"]["median"],
                            "io_ratio_median": v["io_ratio"]["median"]} for a, v in dp["per_arm"].items()},
        },
        "data_quality": {
            "ok_current_runs": dq["ok_current_runs"], "planned_runs": s["design"]["planned_runs"], "truncated": dq["truncated"],
            "model_mismatches": len(dq["model_mismatches"]),
            "extractions": dq["extraction_ok_current"], "extractions_planned": dq["extractions_planned"],
            "evidence_not_verbatim": len(dq["extraction_evidence_not_verbatim"]),
        },
        "run_ids": {a: sorted(r["run_id"] for r in latest_ok_current(run_records).values() if r["arm_id"] == a) for a in ARM_IDS},
        "golden_mapping": {
            "selection_rule": (f"fixed pre-declared mapping: repeat_index {GOLDEN_REPEAT_INDEX} of "
                               + ", ".join(f"{a} -> {r}" for a, r in APP_RUNG_FOR_ARM.items()) + " on all 12 items (not selected by outcome)"),
            "arm_to_rung": dict(APP_RUNG_FOR_ARM), "run_ids": golden_run_ids or {},
        },
    }


def s_runs_for(run_records: Sequence[dict[str, Any]], arm_id: str) -> list[dict[str, Any]]:
    return [{"run": r} for r in latest_ok_current(run_records).values() if r["arm_id"] == arm_id]
