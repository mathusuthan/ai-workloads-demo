"""Category 2 follow-up experiment: may the section template say "Not stated in source"?

The baseline scoring (quality_scoring.py) found that the templated drafts fill the required `owner` and
`target_window` fields of every action item even when the source names no owner or date. This module tests the
untested fix: the same template and schema plus one instruction that permits the literal `Not stated in source`.

Arms (same 4 source bundles, same section template, word budgets and schema):
  template_original    — get_templated_draft_system_prompt(sub_task), unchanged
  template_not_stated  — the same string with ADDED_LINE inserted after the `action_plan` rule (composed, not copied)
Models: Sonnet 5.5 and Haiku 5.5 through the app's own `run_cat2_structured_draft` (same call settings).
Repeats: 3 per (bundle x model x arm) -> 48 drafts, every one kept (truncation is flagged, not dropped).

Phases (all I/O is injectable; nothing here calls the network on import or in tests):
  1. drafting   -> experiments/cat2_not_stated/drafts.jsonl (append-only, deterministic ids, resume, budget guard)
  2. scoring    -> deterministic: fact coverage, unsupported numbers, action-item field classes
  3. judging    -> experiments/cat2_not_stated/judgements.jsonl, the baseline judge (model, settings, prompts and
                   schemas imported from quality_scoring): rubric x48, matched pairwise x48, vs stored unbounded x16
  4. analysis   -> analyse() + render_markdown() (scripts/analyze_cat2_not_stated.py)
"""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import math
import re
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Sequence

from app.archetypes.cat2_drafting import quality_scoring as qs
from app.archetypes.cat2_drafting.prompts import get_templated_draft_system_prompt
from app.archetypes.cat2_drafting.schemas import STRUCTURED_DRAFT_JSON_SCHEMA
from app.core.pricing import compute_run_finops

SCHEMA_VERSION = 1
EXPERIMENT_DIR = qs.BACKEND_DIR / "experiments" / "cat2_not_stated"
DRAFTS_PATH = EXPERIMENT_DIR / "drafts.jsonl"
JUDGEMENTS_PATH = EXPERIMENT_DIR / "judgements.jsonl"
BASELINE_SUMMARY_PATH = qs.BACKEND_DIR / "replays" / "cat2_quality_summary.json"

ARM_ORIGINAL = "template_original"
ARM_NOT_STATED = "template_not_stated"
ARMS: tuple[str, ...] = (ARM_ORIGINAL, ARM_NOT_STATED)
STORED_UNBOUNDED = "stored_unbounded"
# model key -> model_tier passed to run_cat2_structured_draft (exactly what runner.execute_cat2_run passes)
MODELS: dict[str, str] = {"sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5"}
MODEL_KEYS: tuple[str, ...] = tuple(MODELS)
STORED_RUNG_FOR_MODEL = {"sonnet": "sonnet_templated", "haiku": "haiku_templated"}
REPEATS = 3
DRAFT_MAX_TOKENS = 3000  # runner.execute_cat2_run uses max_tokens=3000 for both templated rungs
DEFAULT_DRAFT_MAX_USD = 2.0
DEFAULT_JUDGE_MAX_USD = 12.0

NOT_STATED = "Not stated in source"
ADDED_INSTRUCTION = (
    "For each action-plan item, give the owner and the time window only if the source states them. "
    "If the source does not name an owner, or gives no date or time window, write exactly `Not stated in source` "
    "in that field. Never supply an owner, team, date or deadline the source does not give."
)
# Placed with the other rules, as one more bullet directly after the `action_plan` rule.
ADDED_LINE = f"- {ADDED_INSTRUCTION}\n"
ANCHOR_PREFIX = "- `action_plan`:"

FIELD_CLASSES: tuple[str, ...] = ("supported", "not_stated", "unsupported")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    return qs._utc_now_iso()


# --------------------------------------------------------------------------------------------------
# Prompts (variant composed from the app's prompt function; schema shared)
# --------------------------------------------------------------------------------------------------


def original_system_prompt(sub_task: str) -> str:
    return get_templated_draft_system_prompt(sub_task)


def not_stated_system_prompt(sub_task: str) -> str:
    """The original prompt with ADDED_LINE inserted after the single `action_plan` rule line; nothing else changes."""
    base = original_system_prompt(sub_task)
    lines = base.splitlines(keepends=True)
    idx = [i for i, line in enumerate(lines) if line.startswith(ANCHOR_PREFIX)]
    if len(idx) != 1 or not lines[idx[0]].endswith("\n"):
        raise ValueError("expected exactly one `action_plan` rule line followed by more text in the templated prompt")
    i = idx[0]
    return "".join(lines[: i + 1] + [ADDED_LINE] + lines[i + 1 :])


def system_prompt_for(arm: str, sub_task: str) -> str:
    if arm == ARM_ORIGINAL:
        return original_system_prompt(sub_task)
    if arm == ARM_NOT_STATED:
        return not_stated_system_prompt(sub_task)
    raise ValueError(f"unknown arm {arm!r}")


def schema_for(arm: str) -> dict[str, Any]:
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    return STRUCTURED_DRAFT_JSON_SCHEMA


def prompt_diff(sub_task: str) -> list[str]:
    """Unified diff original -> not_stated system prompt."""
    return list(
        difflib.unified_diff(
            original_system_prompt(sub_task).splitlines(keepends=True),
            not_stated_system_prompt(sub_task).splitlines(keepends=True),
            fromfile=f"{ARM_ORIGINAL}/{sub_task}",
            tofile=f"{ARM_NOT_STATED}/{sub_task}",
        )
    )


# --------------------------------------------------------------------------------------------------
# Draft planning, estimate, budget guard, execution
# --------------------------------------------------------------------------------------------------


def draft_key(preset_id: str, model_key: str, arm: str, repeat_index: int) -> str:
    return f"{preset_id}:{model_key}:{arm}:r{repeat_index}"


def draft_id(preset_id: str, model_key: str, arm: str, repeat_index: int) -> str:
    return f"draft:{draft_key(preset_id, model_key, arm, repeat_index)}"


def plan_drafts(repeats: int = REPEATS) -> list[dict[str, Any]]:
    """Repeat-major order (repeat -> bundle -> model -> arm), so a run stopped early stays balanced across arms."""
    presets = qs.preset_map()
    schema_sha = _sha(json.dumps(STRUCTURED_DRAFT_JSON_SCHEMA, sort_keys=True))
    plan = []
    for k in range(repeats):
        for pid in qs.PRESET_IDS:
            p = presets[pid]
            for m in MODEL_KEYS:
                for arm in ARMS:
                    system = system_prompt_for(arm, p["sub_task"])
                    plan.append(
                        {
                            "draft_id": draft_id(pid, m, arm, k),
                            "draft_key": draft_key(pid, m, arm, k),
                            "preset_id": pid,
                            "sub_task": p["sub_task"],
                            "model_key": m,
                            "model_tier": MODELS[m],
                            "arm": arm,
                            "repeat_index": k,
                            "system": system,
                            "payload": p["payload"],
                            "schema": schema_for(arm),
                            "max_tokens": DRAFT_MAX_TOKENS,
                            "system_sha256": _sha(system),
                            "schema_sha256": schema_sha,
                        }
                    )
    return plan


def _finops(model_id: str | None, input_tokens: int, output_tokens: int):
    return qs._finops(model_id, input_tokens, output_tokens)


def draft_record_cost_usd(rec: dict[str, Any]) -> float:
    return _finops(rec.get("model_id") or rec.get("model_tier"), int(rec.get("input_tokens") or 0), int(rec.get("output_tokens") or 0)).total_cost_usd


def estimate_draft(planned: dict[str, Any], replays: dict[str, Any], chars_per_token: float = qs.DEFAULT_CHARS_PER_TOKEN) -> dict[str, Any]:
    """Input = the stored templated rung's measured input tokens for this bundle and model (same prompt + schema)
    plus the added instruction's characters / chars_per_token; typical output = that rung's stored output."""
    stored = replays["presets"][planned["preset_id"]]["rungs"][STORED_RUNG_FOR_MODEL[planned["model_key"]]]
    extra_chars = len(planned["system"]) - len(original_system_prompt(planned["sub_task"]))
    in_tok = int(stored["input_tokens"]) + int(math.ceil(max(0, extra_chars) / chars_per_token))
    model = planned["model_tier"]
    return {
        "input_tokens": in_tok,
        "typical_output_tokens": int(stored["output_tokens"]),
        "typical_usd": _finops(model, in_tok, int(stored["output_tokens"])).total_cost_usd,
        "worst_case_usd": _finops(model, in_tok, int(planned["max_tokens"])).total_cost_usd,
    }


def estimate_draft_plan(plan: Sequence[dict[str, Any]], replays: dict[str, Any]) -> dict[str, Any]:
    by: dict[str, dict[str, Any]] = {}
    for p in plan:
        e = estimate_draft(p, replays)
        s = by.setdefault(p["model_key"], {"drafts": 0, "input_tokens": 0, "typical_output_tokens": 0, "typical_usd": 0.0, "worst_case_usd": 0.0})
        s["drafts"] += 1
        for k in ("input_tokens", "typical_output_tokens", "typical_usd", "worst_case_usd"):
            s[k] += e[k]
    tot = {k: sum(s[k] for s in by.values()) for k in ("drafts", "input_tokens", "typical_output_tokens", "typical_usd", "worst_case_usd")}
    return {"by_model": by, "total": tot}


class CostGuard:
    """Billed spend of existing records + reserved worst cases vs `max_usd`; refuses a call that could cross the cap."""

    def __init__(self, max_usd: float, existing: Iterable[dict[str, Any]] = (), *, cost_fn: Callable[[dict[str, Any]], float] = draft_record_cost_usd) -> None:
        self.max_usd = float(max_usd)
        self.cost_fn = cost_fn
        self.spent_usd = sum(cost_fn(r) for r in existing)
        self.reserved_usd = 0.0

    def try_reserve(self, worst_case_usd: float) -> bool:
        if self.spent_usd + self.reserved_usd + worst_case_usd > self.max_usd:
            return False
        self.reserved_usd += worst_case_usd
        return True

    def settle(self, reserved_usd: float, record: dict[str, Any]) -> float:
        cost = self.cost_fn(record)
        self.reserved_usd = max(0.0, self.reserved_usd - reserved_usd)
        self.spent_usd += cost
        return cost


DraftCall = Callable[..., Awaitable[Any]]


def make_app_draft_call(api_key: str) -> DraftCall:
    """The app's own templated call (`run_cat2_structured_draft`: same model resolution, thinking, output_config,
    client timeout), with raise_on_max_tokens=False so a truncated draft is returned and recorded, not raised."""
    from app.core.anthropic_service import run_cat2_structured_draft

    async def call(*, system: str, payload: str, schema: dict[str, Any], model_tier: str, max_tokens: int) -> Any:
        return await run_cat2_structured_draft(payload, system, schema, model_tier, api_key, max_tokens=max_tokens, raise_on_max_tokens=False)

    return call


def is_complete_structure(sd: Any) -> bool:
    return isinstance(sd, dict) and all(k in sd for k in ("executive_summary", "key_findings", "risk_and_compliance_matrix", "action_plan"))


async def execute_draft(planned: dict[str, Any], *, draft_call: DraftCall) -> dict[str, Any]:
    """One draft -> one record. Never raises; an API failure is a `status: error` record (retried on resume)."""
    rec: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        **{k: planned[k] for k in ("draft_id", "draft_key", "preset_id", "sub_task", "model_key", "model_tier", "arm", "repeat_index",
                                   "max_tokens", "system_sha256", "schema_sha256")},
        "status": "error",
        "error_type": None,
        "error_message": None,
        "started_at": _utc_now_iso(),
        "model_id": None,
        "model_matches_requested": None,
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
        "structured_draft": None,
    }
    try:
        raw = await draft_call(system=planned["system"], payload=planned["payload"], schema=planned["schema"],
                               model_tier=planned["model_tier"], max_tokens=planned["max_tokens"])
    except Exception as exc:  # noqa: BLE001 — recorded, never raised
        rec["error_type"] = "api_error"
        rec["error_message"] = f"{type(exc).__name__}: {exc}"[:2000]
        rec["finished_at"] = _utc_now_iso()
        return rec
    sd = raw.structured if isinstance(raw.structured, dict) else {}
    rec.update(
        {
            "status": "ok",
            "model_id": raw.model_id,
            "model_matches_requested": raw.model_id == planned["model_tier"],
            "stop_reason": raw.stop_reason,
            "truncated": raw.stop_reason == "max_tokens",
            "parse_ok": is_complete_structure(sd),
            "input_tokens": int(raw.input_tokens),
            "output_tokens": int(raw.output_tokens),
            "thinking_tokens": int(getattr(raw, "thinking_tokens", 0) or 0),
            "cache_creation_tokens": int(getattr(raw, "cache_creation_tokens", 0) or 0),
            "cache_read_tokens": int(getattr(raw, "cache_read_tokens", 0) or 0),
            "latency_ms": int(raw.latency_ms),
            "request_params": getattr(raw, "request_params", None),
            "raw_text": raw.raw_text,
            "structured_draft": sd,
        }
    )
    fin = _finops(raw.model_id, rec["input_tokens"], rec["output_tokens"])
    rec["cost_usd"] = fin.total_cost_usd
    rec["cost_per_1k_docs_usd"] = fin.cost_per_1k_usd
    rec["finished_at"] = _utc_now_iso()
    return rec


async def run_draft_plan(
    pending: Sequence[dict[str, Any]],
    *,
    draft_call: DraftCall,
    guard: CostGuard,
    on_record: Callable[[dict[str, Any]], None],
    replays: dict[str, Any],
    concurrency: int = 4,
) -> dict[str, Any]:
    sem = asyncio.Semaphore(max(1, concurrency))
    tasks: list[asyncio.Task[None]] = []
    counts = {"ok": 0, "error": 0, "launched": 0, "skipped_budget": 0, "truncated": 0}
    budget_stopped = False

    async def one(p: dict[str, Any], reserved: float) -> None:
        try:
            rec = await execute_draft(p, draft_call=draft_call)
            guard.settle(reserved, rec)
            counts["ok" if rec["status"] == "ok" else "error"] += 1
            counts["truncated"] += bool(rec.get("truncated"))
            on_record(rec)
        finally:
            sem.release()

    for i, p in enumerate(pending):
        await sem.acquire()
        worst = estimate_draft(p, replays)["worst_case_usd"]
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


def load_jsonl(path: Path | str) -> list[dict[str, Any]]:
    return qs.load_judgements(path)


def latest_ok_by(records: Iterable[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in records:
        if r.get("status") == "ok":
            out[r[key]] = r  # file order: later wins
    return out


def select_pending_drafts(plan: Iterable[dict[str, Any]], existing: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    done = {r["draft_id"] for r in existing if r.get("status") == "ok"}
    return [p for p in plan if p["draft_id"] not in done]


def stale_draft_records(plan: Iterable[dict[str, Any]], existing: Iterable[dict[str, Any]]) -> list[str]:
    cur = {p["draft_id"]: (p["system_sha256"], p["schema_sha256"]) for p in plan}
    latest = latest_ok_by(existing, "draft_id")
    return sorted(d for d, r in latest.items() if d in cur and (r.get("system_sha256"), r.get("schema_sha256")) != cur[d])


# --------------------------------------------------------------------------------------------------
# Action-item field classifier (deterministic, conservative)
# --------------------------------------------------------------------------------------------------

FIELD_RULES: tuple[str, ...] = (
    "not_stated: the field, lowercased with every non-letter run collapsed to one space, is exactly "
    "'not stated in source' (so case, backticks, quotes, hyphens and a trailing period do not matter); anything "
    "longer that merely contains the phrase is not 'not_stated'.",
    "Owner supported: the whole owner string occurs in the source, or after splitting it on , ; / ( ) [ ] + and ' - ', "
    "every piece (leading 'the' dropped) contains a capital letter and occurs verbatim, case-sensitive, as a whole-word "
    "phrase in the source. A piece joined by 'and' / '&' / 'or' is split further only if every part has at least two "
    "words (two names or two teams); otherwise it must occur whole, with 'and' and '&' interchangeable. A piece without "
    "a capital letter, or not found, makes the owner unsupported.",
    "Time window supported: the whole window string occurs in the source (case-insensitive), or every date/time "
    "expression in it is found in the source after canonicalisation — dates as (month, day, year; a missing year on "
    "either side matches), month names, quarters/halves/fiscal years (Q1 FY2027 != Q1 2027), durations ('30 days' = "
    "'30-day'), clock times (hh:mm, zone ignored), T+N, week numbers, years, and any other token containing a digit "
    "verbatim. A window with no such expression ('Ongoing', 'Pre-launch') is unsupported.",
    "'supported' only means the name or date occurs in the source; it does not check that the source assigns this "
    "action to that owner or date (the judge's errors cover attribution). When unsure the rule says unsupported.",
)

_LIGHT_MAP = str.maketrans({**{c: "-" for c in "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"}, "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u00a0": " "})
_EMPH_RE = re.compile(r"[*`~]")
_WS = re.compile(r"\s+")


def _light(s: str | None) -> str:
    """Dashes/quotes unified, emphasis/backticks removed, whitespace collapsed. Case is kept."""
    s = (s or "").translate(_LIGHT_MAP)
    s = _EMPH_RE.sub("", s)
    return _WS.sub(" ", s).strip()


def _has_phrase(hay: str, phrase: str, *, case_sensitive: bool) -> bool:
    if not phrase:
        return False
    flags = 0 if case_sensitive else re.I
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(phrase)}(?![A-Za-z0-9])", hay, flags) is not None


def is_not_stated(value: str | None) -> bool:
    return re.sub(r"[^a-z]+", " ", (value or "").lower()).strip() == "not stated in source"


_OWNER_SPLIT_RE = re.compile(r"\s*(?:[,;/()\[\]+]|\s-\s)\s*")
_CONJ_SPLIT_RE = re.compile(r"\s*(?:&|\band\b|\bor\b)\s*")
_LEADING_ARTICLE_RE = re.compile(r"^(?:the|The)\s+")


def _clean_piece(raw: str) -> str:
    return _LEADING_ARTICLE_RE.sub("", raw.strip(" .:-'\""))


def _owner_pieces(v: str) -> list[str]:
    pieces: list[str] = []
    for raw in _OWNER_SPLIT_RE.split(v):
        piece = _clean_piece(raw)
        if not piece:
            continue
        parts = [_clean_piece(x) for x in _CONJ_SPLIT_RE.split(piece)]
        parts = [x for x in parts if x]
        if len(parts) > 1 and all(len(x.split()) >= 2 for x in parts):
            pieces += parts
        else:
            pieces.append(piece)
    return pieces


def _piece_found(src: str, piece: str) -> bool:
    if not any(ch.isupper() for ch in piece):
        return False
    variants = {piece, re.sub(r"\s+and\s+", " & ", piece), re.sub(r"\s*&\s*", " and ", piece)}
    return any(_has_phrase(src, x, case_sensitive=True) for x in variants)


def classify_owner(value: str | None, payload: str) -> dict[str, Any]:
    if is_not_stated(value):
        return {"class": "not_stated", "pieces": [], "reason": None}
    v = _light(value)
    src = _light(payload)
    if not v:
        return {"class": "unsupported", "pieces": [], "reason": "empty"}
    if _has_phrase(src, v, case_sensitive=True):
        return {"class": "supported", "pieces": [{"text": v, "found": True}], "reason": "whole owner found"}
    pieces = []
    for piece in _owner_pieces(v):
        entry: dict[str, Any] = {"text": piece, "found": _piece_found(src, piece)}
        if not any(ch.isupper() for ch in piece):
            entry["note"] = "no capitalised name"
        pieces.append(entry)
    if pieces and all(p["found"] for p in pieces):
        return {"class": "supported", "pieces": pieces, "reason": "every piece found"}
    missing = [p["text"] for p in pieces if not p["found"]]
    return {"class": "unsupported", "pieces": pieces, "reason": f"not found in source: {missing}" if missing else "no name pieces"}


_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6,
    "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9, "october": 10, "oct": 10,
    "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_MON = "|".join(sorted(_MONTHS, key=len, reverse=True))
_UNITS = {
    "minute": "minute", "minutes": "minute", "min": "minute", "mins": "minute",
    "hour": "hour", "hours": "hour", "hr": "hour", "hrs": "hour", "h": "hour",
    "day": "day", "days": "day", "week": "week", "weeks": "week", "wk": "week", "wks": "week",
    "month": "month", "months": "month", "quarter": "quarter", "quarters": "quarter",
    "year": "year", "years": "year", "yr": "year", "yrs": "year",
}
_UNIT = "|".join(sorted(_UNITS, key=len, reverse=True))
_NUMV = r"\d+(?:\.\d+)?"
_TIME_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("iso_date", re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")),
    ("clock", re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?![\d])(?:\s*(?:z|utc|ist|gmt)\b)?")),
    ("t_plus", re.compile(r"\bt\s*\+\s*(\d+)\b")),
    ("quarter", re.compile(r"\b(q[1-4]|h[12])\s*(fy)?\s*'?(\d{4}|\d{2})?\b|\b(fy)\s*'?(\d{4}|\d{2})\b")),
    ("mdy", re.compile(rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}})\b)?")),
    ("dmy", re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MON})\b\.?(?:,?\s+(\d{{4}})\b)?")),
    ("duration", re.compile(rf"(?<![\d.])({_NUMV})(?:\s*(?:-|to)\s*({_NUMV}))?\s*-?\s*(business\s+|calendar\s+|working\s+)?({_UNIT})\b")),
    ("week", re.compile(r"\b(?:week|wk)\s*-?\s*(\d{1,2})\b|\bw(\d{1,2})\b")),
    ("month", re.compile(rf"\b({_MON})\b\.?(?:\s+(\d{{4}})\b)?")),
    ("year", re.compile(r"(?<![\d])((?:19|20)\d{2})(?![\d])")),
    ("other", re.compile(r"[a-z0-9]*\d[a-z0-9/.:+-]*")),
)


def _y4(y: str | None) -> int | None:
    if not y:
        return None
    return int(y) if len(y) == 4 else 2000 + int(y)


def _canon(kind: str, m: re.Match[str]) -> list[tuple]:
    """Canonical keys for one match. A range duration also yields its two endpoints (used on the source side)."""
    g = m.groups()
    if kind == "iso_date":
        return [("date", int(g[1]), int(g[2]), int(g[0]))]
    if kind == "clock":
        return [("clock", int(g[0]), int(g[1]))]
    if kind == "t_plus":
        return [("tplus", int(g[0]))]
    if kind == "quarter":
        if g[0]:
            return [("quarter", g[0], bool(g[1]), _y4(g[2]))]
        return [("fy", _y4(g[4]))]
    if kind == "mdy":
        return [("date", _MONTHS[g[0]], int(g[1]), _y4(g[2]))]
    if kind == "dmy":
        return [("date", _MONTHS[g[1]], int(g[0]), _y4(g[2]))]
    if kind == "duration":
        qual = (g[2] or "").strip()
        unit = _UNITS[g[3]]
        a = float(g[0])
        if g[1]:
            b = float(g[1])
            return [("duration_range", a, b, qual, unit), ("duration", a, qual, unit), ("duration", b, qual, unit)]
        return [("duration", a, qual, unit)]
    if kind == "week":
        return [("week", int(g[0] or g[1]))]
    if kind == "month":
        return [("month", _MONTHS[g[0]], _y4(g[1]))]
    if kind == "year":
        return [("year", int(g[0]))]
    return [("text", m.group(0).strip(".:/-+"))]


def time_expressions(text: str) -> list[dict[str, Any]]:
    """Date/time expressions in priority order; each match's span is blanked before the next pattern runs."""
    s = _light(text).lower()
    out = []
    for kind, rx in _TIME_PATTERNS:
        def take(m: re.Match[str]) -> str:
            keys = _canon(kind, m)
            if not (kind == "other" and not keys[0][1]):
                out.append({"kind": kind, "text": m.group(0).strip(), "key": keys[0], "all_keys": keys})
            return " " * len(m.group(0))
        s = rx.sub(take, s)
    return out


def source_time_index(payload: str) -> dict[str, Any]:
    keys: set[tuple] = set()
    for e in time_expressions(payload):
        keys.update(e["all_keys"])
    dates = {k for k in keys if k[0] == "date"}
    return {"keys": keys, "dates": dates, "text": _light(payload).lower()}


def _expr_found(e: dict[str, Any], idx: dict[str, Any]) -> bool:
    k = e["key"]
    kind = k[0]
    if kind == "date":
        _, mo, d, y = k
        return any(x[1] == mo and x[2] == d and (y is None or x[3] is None or x[3] == y) for x in idx["dates"])
    if kind == "month":
        _, mo, y = k
        return any(x[1] == mo and (y is None or x[3] is None or x[3] == y) for x in idx["dates"]) or any(
            x[0] == "month" and x[1] == mo and (y is None or x[2] is None or x[2] == y) for x in idx["keys"]
        )
    if kind == "duration_range":
        _, a, b, qual, unit = k
        return k in idx["keys"] or (("duration", a, qual, unit) in idx["keys"] and ("duration", b, qual, unit) in idx["keys"])
    if kind == "text":
        return _has_phrase(idx["text"], k[1], case_sensitive=False)
    if kind == "year":
        return _has_phrase(idx["text"], str(k[1]), case_sensitive=False)
    return k in idx["keys"]


def classify_window(value: str | None, payload: str, *, index: dict[str, Any] | None = None) -> dict[str, Any]:
    if is_not_stated(value):
        return {"class": "not_stated", "expressions": [], "reason": None}
    v = _light(value)
    if not v:
        return {"class": "unsupported", "expressions": [], "reason": "empty"}
    if _has_phrase(_light(payload), v, case_sensitive=False):
        return {"class": "supported", "expressions": [], "reason": "whole window found"}
    idx = index or source_time_index(payload)
    exprs = [{"text": e["text"], "kind": e["kind"], "found": _expr_found(e, idx)} for e in time_expressions(v)]
    if not exprs:
        return {"class": "unsupported", "expressions": [], "reason": "no date or duration found"}
    if all(e["found"] for e in exprs):
        return {"class": "supported", "expressions": exprs, "reason": "every date/time expression found"}
    return {"class": "unsupported", "expressions": exprs, "reason": f"not found in source: {[e['text'] for e in exprs if not e['found']]}"}


_STOP = {"the", "and", "for", "with", "from", "that", "this", "within", "before", "after", "into", "all", "any", "our", "per", "via", "are", "was", "will", "not", "source"}


def nearest_source_text(value: str | None, payload: str, width: int = 240) -> str | None:
    """Payload line (long lines split into sentences) sharing the most words/numbers with `value`; None if none share any."""
    want = {w for w in re.findall(r"[a-z0-9]+", _light(value).lower()) if (len(w) >= 3 or w.isdigit()) and w not in _STOP}
    if not want:
        return None
    best, best_score = None, 0
    for line in payload.splitlines():
        segs = re.split(r"(?<=[.;])\s+", line) if len(line) > width else [line]
        for seg in segs:
            have = set(re.findall(r"[a-z0-9]+", _light(seg).lower()))
            score = len(want & have)
            if score > best_score:
                best, best_score = seg.strip(), score
    if best is None:
        return None
    return best if len(best) <= width else best[: width - 1] + "…"


def classify_action_items(structured_draft: Any, payload: str) -> list[dict[str, Any]]:
    items = structured_draft.get("action_plan") if isinstance(structured_draft, dict) else None
    if not isinstance(items, list):
        return []
    idx = source_time_index(payload)
    out = []
    for i, a in enumerate(items):
        a = a if isinstance(a, dict) else {}
        owner, window = a.get("owner"), a.get("target_window")
        oc, wc = classify_owner(owner, payload), classify_window(window, payload, index=idx)
        out.append(
            {
                "index": i,
                "owner": owner,
                "time_window": window,
                "owner_class": oc["class"],
                "owner_detail": oc,
                "window_class": wc["class"],
                "window_detail": wc,
                "owner_nearest_source": nearest_source_text(owner, payload) if oc["class"] == "unsupported" else None,
                "window_nearest_source": nearest_source_text(window, payload) if wc["class"] == "unsupported" else None,
            }
        )
    return out


# --------------------------------------------------------------------------------------------------
# Deterministic scoring of drafts
# --------------------------------------------------------------------------------------------------


def draft_text(rec: dict[str, Any]) -> str:
    """Rendered exactly like the baseline templated drafts; raw text when the JSON did not parse (flagged)."""
    sd = rec.get("structured_draft")
    if is_complete_structure(sd):
        try:
            return qs.render_structured_draft(sd)
        except (KeyError, TypeError, AttributeError):
            pass
    return str(rec.get("raw_text") or "")


def score_experiment_draft(rec: dict[str, Any], keys: dict[str, Any]) -> dict[str, Any]:
    pid = rec["preset_id"]
    payload = qs.preset_map()[pid]["payload"]
    text = draft_text(rec)
    facts = qs.score_facts(text, qs.facts_for(keys, pid))
    num_rows = qs.classify_numbers(text, payload)
    fin = _finops(rec.get("model_id") or rec.get("model_tier"), int(rec.get("input_tokens") or 0), int(rec.get("output_tokens") or 0))
    return {
        **{k: rec.get(k) for k in ("draft_id", "draft_key", "preset_id", "model_key", "arm", "repeat_index", "model_id",
                                   "model_matches_requested", "stop_reason", "truncated", "parse_ok", "input_tokens",
                                   "output_tokens", "thinking_tokens")},
        "cost_per_1k_docs_usd": fin.cost_per_1k_usd,
        "text": text,
        "text_sha256": _sha(text),
        "core_facts": qs.proportion(r for r in facts if r["tier"] == "core"),
        "detail_facts": qs.proportion(r for r in facts if r["tier"] == "detail"),
        "missed_facts": [r["fact_id"] for r in facts if not r["hit"]],
        "numbers_summary": qs.numbers_summary(num_rows),
        "not_in_source": qs.not_in_source_list(num_rows),
        "action_items": classify_action_items(rec.get("structured_draft"), payload),
        "structured_draft": rec.get("structured_draft"),
    }


def score_drafts(draft_records: Iterable[dict[str, Any]], keys: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    keys = keys or qs.load_quality_keys()
    return {k: score_experiment_draft(r, keys) for k, r in sorted(latest_ok_by(draft_records, "draft_key").items())}


# --------------------------------------------------------------------------------------------------
# Judge planning (baseline judge: prompts, schemas, model and settings imported from quality_scoring)
# --------------------------------------------------------------------------------------------------


def stored_unbounded_text(replays: dict[str, Any], preset_id: str) -> str:
    return qs.render_draft(replays["presets"][preset_id]["rungs"]["sonnet_unbounded"])


def standin_drafts(replays: dict[str, Any], keys: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Stored templated drafts used in place of every planned draft (dry-run estimates before drafting only)."""
    keys = keys or qs.load_quality_keys()
    out = {}
    for p in plan_drafts():
        r = replays["presets"][p["preset_id"]]["rungs"][STORED_RUNG_FOR_MODEL[p["model_key"]]]
        rec = {**{k: p[k] for k in ("draft_id", "draft_key", "preset_id", "model_key", "arm", "repeat_index")}, "model_id": r["model_id"],
               "input_tokens": r["input_tokens"], "output_tokens": r["output_tokens"], "structured_draft": r["structured_draft"],
               "raw_text": r.get("raw_markdown"), "stop_reason": r.get("stop_reason"), "truncated": False, "parse_ok": True}
        out[p["draft_key"]] = {**score_experiment_draft(rec, keys), "standin": True}
    return out


def rubric_call_id(key: str) -> str:
    return f"rubric:{key}"


def pairwise_call_id(comparison: str, preset_id: str, model_key: str, repeat_index: int, order: str) -> str:
    return f"pairwise:{comparison}:{preset_id}:{model_key}:r{repeat_index}:{order}"


def plan_judge_calls(scored: dict[str, dict[str, Any]], replays: dict[str, Any], *, repeats: int = REPEATS) -> list[dict[str, Any]]:
    """Rubric (one pass per draft), matched pairwise (not_stated vs original, same bundle/model/repeat, both orders),
    and not_stated repeat 0 vs the stored unbounded draft (both orders, per model). Calls whose drafts are missing are
    left out."""
    plan: list[dict[str, Any]] = []
    for k in range(repeats):
        for pid in qs.PRESET_IDS:
            for m in MODEL_KEYS:
                for arm in ARMS:
                    key = draft_key(pid, m, arm, k)
                    d = scored.get(key)
                    if d is None:
                        continue
                    numbers = list(d["not_in_source"])
                    system, user = qs.build_rubric_prompt(pid, d["text"], numbers)
                    plan.append(
                        {
                            "call_id": rubric_call_id(key),
                            "task": "rubric",
                            "preset_id": pid,
                            "rung_id": f"{m}:{arm}:r{k}",
                            "repeat_index": 0,  # judge pass index (one pass per draft)
                            "system": system,
                            "user": user,
                            "schema": qs.RUBRIC_SCHEMA,
                            "numbers": numbers,
                            "draft_sha256": d["text_sha256"],
                            "prompt_sha256": qs._sha(system, user),
                            "meta": {"comparison": "rubric", "draft_key": key, "model_key": m, "arm": arm, "draft_repeat": k,
                                     "draft_keys": [key]},
                        }
                    )

    def pair_calls(comparison: str, pid: str, m: str, k: int, ns: dict[str, Any], other_label: str, other_text: str,
                   other_key: str, other_sha: str) -> None:
        for order, (a_lab, a_txt, b_lab, b_txt) in (
            ("fwd", (ARM_NOT_STATED, ns["text"], other_label, other_text)),
            ("rev", (other_label, other_text, ARM_NOT_STATED, ns["text"])),
        ):
            system, user = qs.build_pairwise_prompt(pid, a_txt, b_txt)
            plan.append(
                {
                    "call_id": pairwise_call_id(comparison, pid, m, k, order),
                    "task": "pairwise",
                    "preset_id": pid,
                    "pair": [ARM_NOT_STATED, other_label],
                    "order": order,
                    "a_rung": a_lab,
                    "b_rung": b_lab,
                    "system": system,
                    "user": user,
                    "schema": qs.PAIRWISE_SCHEMA,
                    "prompt_sha256": qs._sha(system, user),
                    "meta": {"comparison": comparison, "model_key": m, "draft_repeat": k,
                             "draft_keys": [ns["draft_key"], other_key], "draft_sha256": [ns["text_sha256"], other_sha]},
                }
            )

    for k in range(repeats):
        for pid in qs.PRESET_IDS:
            for m in MODEL_KEYS:
                ns, og = scored.get(draft_key(pid, m, ARM_NOT_STATED, k)), scored.get(draft_key(pid, m, ARM_ORIGINAL, k))
                if ns and og:
                    pair_calls("matched", pid, m, k, ns, ARM_ORIGINAL, og["text"], og["draft_key"], og["text_sha256"])
    for pid in qs.PRESET_IDS:
        ub = stored_unbounded_text(replays, pid)
        for m in MODEL_KEYS:
            ns = scored.get(draft_key(pid, m, ARM_NOT_STATED, 0))
            if ns:
                pair_calls("vs_unbounded", pid, m, 0, ns, STORED_UNBOUNDED, ub, f"{pid}:{STORED_UNBOUNDED}", _sha(ub))
    return plan


EXTRA_BLINDING_TERMS: tuple[str, ...] = (*ARMS, "not_stated", STORED_UNBOUNDED, "draft:", *MODEL_KEYS, *MODELS.values())


def experiment_blinding_violations(prompt_text: str, embedded_texts: Sequence[str], forbidden_numbers: Sequence[str] = ()) -> list[str]:
    """Baseline blinding check plus arm/model labels and draft token/cost numbers, all looked for only in what WE add
    (source and draft texts are cut out first; the drafts may say anything, including "Not stated in source")."""
    hits = qs.blinding_violations(prompt_text, embedded_texts)
    rest = prompt_text
    for t in sorted((t.strip() for t in embedded_texts if t and t.strip()), key=len, reverse=True):
        rest = rest.replace(t, "")
    low = rest.lower()
    hits += [w for w in EXTRA_BLINDING_TERMS if w.lower() in low and w not in hits]
    for n in forbidden_numbers:
        if n and re.search(rf"(?<![\d,]){re.escape(n)}(?![\d,])", rest):
            hits.append(f"number:{n}")
    return hits


def blinding_report(plan: Sequence[dict[str, Any]], scored: dict[str, dict[str, Any]], replays: dict[str, Any]) -> dict[str, list[str]]:
    """call_id -> violations, for every planned prompt with any."""
    presets = qs.preset_map()
    bad = {}
    for p in plan:
        texts = [presets[p["preset_id"]]["payload"]] + [n["snippet"] for n in p.get("numbers") or []]  # draft-derived context
        nums: list[str] = []
        for key in p["meta"]["draft_keys"]:
            if key.endswith(STORED_UNBOUNDED):
                texts.append(stored_unbounded_text(replays, p["preset_id"]))
                continue
            d = scored[key]
            texts.append(d["text"])
            for f in ("input_tokens", "output_tokens"):
                if d.get(f):
                    nums += [str(d[f]), f"{d[f]:,}"]
            nums.append(f"{d['cost_per_1k_docs_usd']:.2f}")
        v = experiment_blinding_violations(p["system"] + "\n" + p["user"], texts, nums)
        if v:
            bad[p["call_id"]] = v
    return bad


def calibrate_judge_estimate(baseline_judgements_path: Path | str | None = None) -> dict[str, Any]:
    """chars/token and typical output tokens per task measured on the baseline judge run (read-only)."""
    recs = qs.load_judgements(baseline_judgements_path or qs.JUDGEMENTS_PATH)
    ok = [r for r in qs.latest_ok(recs).values()]
    if not ok:
        return {"chars_per_token": qs.DEFAULT_CHARS_PER_TOKEN, "typical_output_tokens": None, "source": "defaults"}
    det = qs.run_deterministic(qs.load_replays(), qs.load_quality_keys())
    plan = {p["call_id"]: p for p in qs.plan_judge_calls(det)}
    ratios = [
        (len(plan[r["call_id"]]["system"]) + len(plan[r["call_id"]]["user"]) + len(json.dumps(plan[r["call_id"]]["schema"]))) / r["input_tokens"]
        for r in ok
        if r["call_id"] in plan and r.get("input_tokens") and r.get("prompt_sha256") == plan[r["call_id"]]["prompt_sha256"]
    ]
    typical = {t: int(round(statistics.fmean(r["output_tokens"] for r in ok if r["task"] == t))) for t in ("rubric", "pairwise")
               if any(r["task"] == t for r in ok)}
    return {
        "chars_per_token": statistics.fmean(ratios) if ratios else qs.DEFAULT_CHARS_PER_TOKEN,
        "typical_output_tokens": typical or None,
        "source": f"baseline judge run ({len(ratios)} calls matched for chars/token, {len(ok)} ok calls for output)",
    }


# --------------------------------------------------------------------------------------------------
# Analysis (pure)
# --------------------------------------------------------------------------------------------------


def _dist(values: Sequence[float]) -> dict[str, Any]:
    vals = [v for v in values if v is not None]
    if not vals:
        return {"n": 0, "mean": None, "min": None, "max": None}
    return {"n": len(vals), "mean": statistics.fmean(vals), "min": min(vals), "max": max(vals)}


def _sum_prop(props: Iterable[dict[str, Any]]) -> dict[str, int]:
    props = list(props)
    return {"hits": sum(p["hits"] for p in props), "total": sum(p["total"] for p in props)}


def judged_draft(rubric_rec: dict[str, Any] | None, scored_draft: dict[str, Any]) -> dict[str, Any] | None:
    if rubric_rec is None:
        return None
    parsed = rubric_rec["parsed"]
    errors = qs.dedupe_errors([{**e, "repeat_index": 0} for e in parsed["factual_errors"]])
    flags = qs.action_item_flags(scored_draft.get("structured_draft"), errors)
    verdict = {e["id"]: e["verdict"] for e in parsed["unsupported_numbers_review"]}
    return {
        "scores": {d: int(parsed["scores"][d]["score"]) for d in qs.DIMENSIONS},
        "errors": errors,
        "serious": sum(1 for e in errors if e["severity"] == "material"),
        "minor": sum(1 for e in errors if e["severity"] == "minor"),
        "flagged_items": flags["flagged"] if flags else 0,
        "flagged_items_serious": flags["flagged_serious"] if flags else 0,
        "flag_rows": flags["items"] if flags else [],
        "number_verdicts": verdict,
    }


def _group_stats(drafts: Sequence[dict[str, Any]]) -> dict[str, Any]:
    owner = Counter(i["owner_class"] for d in drafts for i in d["action_items"])
    window = Counter(i["window_class"] for d in drafts for i in d["action_items"])
    judged = [d for d in drafts if d.get("judge")]
    verdicts = Counter(v for d in judged for v in d["judge"]["number_verdicts"].values())
    return {
        "drafts": len(drafts),
        "truncated": sum(1 for d in drafts if d.get("truncated")),
        "parse_failures": sum(1 for d in drafts if not d.get("parse_ok")),
        "action_items": sum(len(d["action_items"]) for d in drafts),
        "owner": {c: owner.get(c, 0) for c in FIELD_CLASSES},
        "time_window": {c: window.get(c, 0) for c in FIELD_CLASSES},
        "core_facts": _sum_prop(d["core_facts"] for d in drafts),
        "detail_facts": _sum_prop(d["detail_facts"] for d in drafts),
        "not_in_source_numbers": sum(d["numbers_summary"]["not_in_source"] for d in drafts),
        "number_verdicts": {v: verdicts.get(v, 0) for v in qs.NUMBER_VERDICTS} if judged else None,
        "output_tokens": _dist([d["output_tokens"] for d in drafts]),
        "cost_per_1k_docs_usd": _dist([d["cost_per_1k_docs_usd"] for d in drafts]),
        "judged_drafts": len(judged),
        "rubric": {dim: _dist([d["judge"]["scores"][dim] for d in judged]) for dim in qs.DIMENSIONS} if judged else None,
        "serious_per_draft": _dist([d["judge"]["serious"] for d in judged]) if judged else None,
        "minor_per_draft": _dist([d["judge"]["minor"] for d in judged]) if judged else None,
        "flagged_items_per_draft": _dist([d["judge"]["flagged_items"] for d in judged]) if judged else None,
        "serious_total": sum(d["judge"]["serious"] for d in judged) if judged else None,
        "flagged_items_total": sum(d["judge"]["flagged_items"] for d in judged) if judged else None,
    }


def _pair_block(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"calls": len(records)}
    for key in ("overall", *qs.PAIR_DIMENSIONS):
        def choice(r: dict[str, Any]) -> str:
            return r["parsed"]["preferred"] if key == "overall" else r["parsed"]["dimension_preferences"][key]

        wins = Counter()
        units: dict[tuple, dict[str, str]] = {}
        a_pos = decisive = 0
        for r in records:
            c = choice(r)
            w = qs._winner(r, c) or "tie"
            wins[w] += 1
            if w != "tie":
                decisive += 1
                a_pos += c == "A"
            m = r.get("meta") or {}
            units.setdefault((r["preset_id"], m.get("model_key"), m.get("draft_repeat")), {})[r["order"]] = w
        both = {k: v for k, v in units.items() if "fwd" in v and "rev" in v}
        other = next((x for r in records for x in r["pair"] if x != ARM_NOT_STATED), None)
        out[key] = {
            "not_stated_wins": wins.get(ARM_NOT_STATED, 0),
            "other_wins": wins.get(other, 0) if other else 0,
            "ties": wins.get("tie", 0),
            "other": other,
            "position_consistency": {"units_with_both_orders": len(both), "consistent": sum(1 for v in both.values() if v["fwd"] == v["rev"])},
            "share_decisive_choosing_position_a": (a_pos / decisive) if decisive else None,
        }
    return out


def load_baseline_summary(path: Path | str | None = None) -> dict[str, Any] | None:
    p = Path(path or BASELINE_SUMMARY_PATH)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def baseline_table(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    """Stored baseline (one draft per rung per bundle, 3 judge passes), for context only."""
    if not summary:
        return None
    rungs = []
    for r in summary["rungs"]:
        rungs.append(
            {
                "rung_id": r["rung_id"],
                "drafts": r["drafts"],
                "core_facts": r["core_facts"],
                "detail_facts": r["detail_facts"],
                "rubric": {d: r["rubric"][d]["mean"] for d in qs.DIMENSIONS},
                "serious_errors": r["serious_errors"],
                "minor_errors": r["minor_errors"],
                "action_items": r.get("action_items"),
                "cost_per_1k_docs_usd": r.get("cost_per_1k_docs_usd"),
                "output_tokens_mean": r.get("output_tokens_mean"),
            }
        )
    return {"judge_model": summary.get("judge_model"), "passes_per_draft": summary.get("passes_per_draft"),
            "drafts_per_cell": summary.get("drafts_per_cell"), "keys_version": summary.get("keys_version"), "rungs": rungs}


def analyse(
    draft_records: Sequence[dict[str, Any]],
    judgements: Sequence[dict[str, Any]] | None,
    *,
    keys: dict[str, Any] | None = None,
    baseline_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    keys = keys or qs.load_quality_keys()
    scored = score_drafts(draft_records, keys)
    ok_j = qs.latest_ok(judgements or [])
    for key, d in scored.items():
        d["judge"] = judged_draft(ok_j.get(rubric_call_id(key)), d)

    groups: dict[str, Any] = {}
    for arm in ARMS:
        for m in MODEL_KEYS:
            sel = [d for d in scored.values() if d["arm"] == arm and d["model_key"] == m]
            groups[f"{arm}|{m}"] = {
                "arm": arm,
                "model_key": m,
                **_group_stats(sel),
                "by_preset": {pid: _group_stats([d for d in sel if d["preset_id"] == pid]) for pid in qs.PRESET_IDS},
            }

    pw = [r for r in ok_j.values() if r["task"] == "pairwise"]
    pairwise: dict[str, Any] = {}
    for comp in ("matched", "vs_unbounded"):
        recs = [r for r in pw if (r.get("meta") or {}).get("comparison") == comp]
        pairwise[comp] = {
            "all": _pair_block(recs) if recs else None,
            "by_model": {m: _pair_block([r for r in recs if r["meta"]["model_key"] == m]) for m in MODEL_KEYS
                         if any(r["meta"]["model_key"] == m for r in recs)},
            "by_model_preset": {f"{m}|{pid}": _pair_block(sel) for m in MODEL_KEYS for pid in qs.PRESET_IDS
                                if (sel := [r for r in recs if r["meta"]["model_key"] == m and r["preset_id"] == pid])},
        }

    review_errors, review_fields = [], []
    for key, d in scored.items():
        label = f"{d['preset_id']} · {d['model_key']} · {d['arm']} · repeat {d['repeat_index']}"
        for e in (d["judge"] or {}).get("errors", []):
            if e["severity"] == "material":
                sq = e["source_quote_or_absent"]
                review_errors.append({"draft": label, "draft_key": key, "claim_quote": e["claim_quote"], "problem": e["problem"],
                                      "source_quote": None if sq.strip().upper() == "ABSENT" else sq})
        for it in d["action_items"]:
            for field, cls, val, near, det in (
                ("owner", it["owner_class"], it["owner"], it["owner_nearest_source"], it["owner_detail"]),
                ("time_window", it["window_class"], it["time_window"], it["window_nearest_source"], it["window_detail"]),
            ):
                if cls == "unsupported":
                    review_fields.append({"draft": label, "draft_key": key, "item": it["index"] + 1, "field": field, "value": val,
                                          "reason": det.get("reason"), "nearest_source": near})

    drafts_all = list(draft_records)
    return {
        "schema_version": SCHEMA_VERSION,
        "design": {"arms": list(ARMS), "models": dict(MODELS), "presets": list(qs.PRESET_IDS), "repeats": REPEATS,
                   "planned_drafts": len(plan_drafts()), "added_instruction": ADDED_INSTRUCTION, "field_rules": list(FIELD_RULES),
                   "judge_model": qs.JUDGE_MODEL, "judge_passes_per_draft": 1, "keys_version": (keys.get("meta") or {}).get("keys_version")},
        "drafts_data_quality": {
            "records": len(drafts_all),
            "ok_drafts": len(scored),
            "error_records": sum(1 for r in drafts_all if r.get("status") != "ok"),
            "truncated": sum(1 for d in scored.values() if d.get("truncated")),
            "parse_failures": sum(1 for d in scored.values() if not d.get("parse_ok")),
            "stop_reasons": dict(Counter(d.get("stop_reason") for d in scored.values())),
            "model_ids": dict(Counter(d.get("model_id") for d in scored.values())),
            "model_mismatches": sorted(k for k, d in scored.items() if d.get("model_matches_requested") is False),
            "missing_drafts": sorted(p["draft_key"] for p in plan_drafts() if p["draft_key"] not in scored),
        },
        "judge_data_quality": qs.judge_data_quality(judgements) if judgements else None,
        "groups": groups,
        "pairwise": pairwise if judgements else None,
        "baseline": baseline_table(baseline_summary),
        "review": {"serious_errors": review_errors, "unsupported_fields": review_fields},
        "drafts": [{k: v for k, v in d.items() if k not in ("text", "structured_draft")} for d in scored.values()],
    }


# --------------------------------------------------------------------------------------------------
# Markdown (factual tables only)
# --------------------------------------------------------------------------------------------------

DIM_LABEL = {"factual_accuracy": "Accuracy", "coverage": "Coverage", "clarity": "Clarity", "actionability": "Actionability", "concision": "Concision"}


def _f(v: float | None, digits: int = 2) -> str:
    return "—" if v is None else f"{v:.{digits}f}"


def _d(x: dict[str, Any] | None, digits: int = 2) -> str:
    if not x or not x.get("n"):
        return "—"
    if x["min"] == x["max"]:
        return _f(x["mean"], digits)
    return f"{_f(x['mean'], digits)} ({_f(x['min'], 0 if float(x['min']).is_integer() else digits)}–{_f(x['max'], 0 if float(x['max']).is_integer() else digits)})"


def _cell(s: Any) -> str:
    return str(s if s is not None else "—").replace("|", "\\|").replace("\n", " ")


def _classes(c: dict[str, int]) -> str:
    return f"{c['supported']} / {c['not_stated']} / {c['unsupported']}"


def render_markdown(s: dict[str, Any]) -> str:
    L: list[str] = []
    add = L.append
    dq = s["drafts_data_quality"]
    des = s["design"]
    add("# Category 2 follow-up: may the template say \"Not stated in source\"?")
    add("")
    add(f"Arms: `{ARM_ORIGINAL}` (the app's templated prompt and schema) vs `{ARM_NOT_STATED}` (the same prompt plus one instruction; "
        f"schema unchanged). Models: Sonnet 5.5 and Haiku 5.5 via the app's templated call. {des['repeats']} drafts per bundle × model × arm.")
    add("")
    add(f"Added instruction: \"{des['added_instruction']}\"")
    add("")
    add(f"Drafts: {dq['ok_drafts']} of {des['planned_drafts']} planned ({dq['error_records']} error records); truncated (stop_reason "
        f"`max_tokens`): {dq['truncated']}; JSON not parsed: {dq['parse_failures']}; stop reasons {dq['stop_reasons']}; models returned {dq['model_ids']}"
        + (f"; model differs from requested: {dq['model_mismatches']}" if dq["model_mismatches"] else "") + ".")
    if dq["missing_drafts"]:
        add(f"Missing drafts: {', '.join(dq['missing_drafts'])}.")
    jdq = s["judge_data_quality"]
    add("")
    add(f"Judge: `{des['judge_model']}` with the baseline rubric and pairwise prompts and settings, one rubric pass per draft. "
        + (f"{jdq['ok_calls']} ok calls, {jdq['error_records']} error records, models returned {jdq['model_ids_returned']}, "
           f"billed ≈ ${jdq['billed_usd_all_records']:.2f} at the assumed rate." if jdq else "No judgements file: judge tables are empty."))
    add("")
    add("## Action-item fields (deterministic)")
    add("")
    add("Counts are supported / not stated / unsupported over all action items. Rules:")
    for r in des["field_rules"]:
        add(f"- {r}")
    add("")
    add("| Arm | Model | Drafts | Items | Owner (sup / not stated / unsup) | Time window (sup / not stated / unsup) | Grader-flagged items per draft | Serious errors per draft | Minor errors per draft |")
    add("|---|---|---:|---:|---|---|---:|---:|---:|")
    for g in s["groups"].values():
        add(f"| {g['arm']} | {g['model_key']} | {g['drafts']} | {g['action_items']} | {_classes(g['owner'])} | {_classes(g['time_window'])} | "
            f"{_d(g['flagged_items_per_draft'])} | {_d(g['serious_per_draft'])} | {_d(g['minor_per_draft'])} |")
    add("")
    add("Per bundle (mean over repeats, range in brackets):")
    add("")
    add("| Arm | Model | Bundle | Drafts | Owner (sup / ns / unsup) | Window (sup / ns / unsup) | Flagged items | Serious | Minor |")
    add("|---|---|---|---:|---|---|---:|---:|---:|")
    for g in s["groups"].values():
        for pid, b in g["by_preset"].items():
            add(f"| {g['arm']} | {g['model_key']} | {pid} | {b['drafts']} | {_classes(b['owner'])} | {_classes(b['time_window'])} | "
                f"{_d(b['flagged_items_per_draft'])} | {_d(b['serious_per_draft'])} | {_d(b['minor_per_draft'])} |")
    add("")
    add("## Rubric (blind judge, 1–5; mean over drafts, range in brackets)")
    add("")
    add("| Arm | Model | Judged | " + " | ".join(DIM_LABEL[d] for d in qs.DIMENSIONS) + " |")
    add("|---|---|---:|" + "---:|" * len(qs.DIMENSIONS))
    for g in s["groups"].values():
        rub = g["rubric"] or {}
        add(f"| {g['arm']} | {g['model_key']} | {g['judged_drafts']} | " + " | ".join(_d(rub.get(d)) for d in qs.DIMENSIONS) + " |")
    add("")
    add("Per bundle:")
    add("")
    add("| Arm | Model | Bundle | " + " | ".join(DIM_LABEL[d] for d in qs.DIMENSIONS) + " |")
    add("|---|---|---|" + "---:|" * len(qs.DIMENSIONS))
    for g in s["groups"].values():
        for pid, b in g["by_preset"].items():
            rub = b["rubric"] or {}
            add(f"| {g['arm']} | {g['model_key']} | {pid} | " + " | ".join(_d(rub.get(d)) for d in qs.DIMENSIONS) + " |")
    add("")
    add("## Facts, numbers, tokens and cost")
    add("")
    add("| Arm | Model | Core facts | Detail facts | Numbers not in source | …judge verdicts (derived correct / derived wrong / unverifiable / not a claim) | Output tokens | $ / 1k docs | Truncated | JSON not parsed |")
    add("|---|---|---:|---:|---:|---|---:|---:|---:|---:|")
    for g in s["groups"].values():
        v = g["number_verdicts"]
        vt = " / ".join(str(v[k]) for k in qs.NUMBER_VERDICTS) if v else "—"
        add(f"| {g['arm']} | {g['model_key']} | {g['core_facts']['hits']}/{g['core_facts']['total']} | {g['detail_facts']['hits']}/{g['detail_facts']['total']} | "
            f"{g['not_in_source_numbers']} | {vt} | {_d(g['output_tokens'], 0)} | {_d(g['cost_per_1k_docs_usd'])} | {g['truncated']} | {g['parse_failures']} |")
    add("")
    add("## Head-to-head (blind judge, both presentation orders)")
    add("")
    pw = s["pairwise"]
    if not pw:
        add("No judgements file.")
    else:
        add("| Comparison | Scope | Calls | Overall: not stated – other – tie | Accuracy | Usefulness to reader | Position-consistent units | Share of decisive picks for position A |")
        add("|---|---|---:|---|---|---|---:|---:|")

        def row(label: str, scope: str, b: dict[str, Any] | None) -> None:
            if not b:
                return
            o = b["overall"]
            add(f"| {label} | {scope} | {b['calls']} | {o['not_stated_wins']} – {o['other_wins']} – {o['ties']} | "
                + " | ".join(f"{b[k]['not_stated_wins']} – {b[k]['other_wins']} – {b[k]['ties']}" for k in qs.PAIR_DIMENSIONS)
                + f" | {o['position_consistency']['consistent']}/{o['position_consistency']['units_with_both_orders']} | {_f(o['share_decisive_choosing_position_a'])} |")

        for comp, label in (("matched", f"{ARM_NOT_STATED} vs {ARM_ORIGINAL} (same bundle, model, repeat)"),
                            ("vs_unbounded", f"{ARM_NOT_STATED} (repeat 0) vs stored unbounded draft")):
            row(label, "all", pw[comp]["all"])
            for m, b in pw[comp]["by_model"].items():
                row(label, m, b)
            for mp, b in pw[comp]["by_model_preset"].items():
                row(label, mp.replace("|", " · "), b)
    add("")
    add("## Stored baseline, for context (different drafts: n=1 per cell, 3 judge passes)")
    add("")
    bl = s["baseline"]
    if not bl:
        add("Baseline summary not found.")
    else:
        add(f"Read from `backend/replays/cat2_quality_summary.json` (keys version `{bl['keys_version']}`, judge `{bl['judge_model']}`, "
            f"{bl['passes_per_draft']} passes per draft, {bl['drafts_per_cell']} draft per rung per bundle). Not comparable draft-for-draft with the tables above.")
        add("")
        add("| Rung | Drafts | Core facts | Detail facts | " + " | ".join(DIM_LABEL[d] for d in qs.DIMENSIONS) + " | Serious / minor errors | Grader-flagged action items | $ / 1k docs |")
        add("|---|---:|---:|---:|" + "---:|" * len(qs.DIMENSIONS) + "---:|---:|---:|")
        for r in bl["rungs"]:
            ai = r["action_items"]
            add(f"| {r['rung_id']} | {r['drafts']} | {r['core_facts']['hits']}/{r['core_facts']['total']} | {r['detail_facts']['hits']}/{r['detail_facts']['total']} | "
                + " | ".join(_f(r["rubric"][d]) for d in qs.DIMENSIONS)
                + f" | {r['serious_errors']} / {r['minor_errors']} | {('—' if not ai else str(ai['flagged']) + '/' + str(ai['total']))} | {_f(r['cost_per_1k_docs_usd'])} |")
    add("")
    add("## For lead review")
    add("")
    rv = s["review"]
    add(f"### Serious errors reported by the judge ({len(rv['serious_errors'])})")
    add("")
    if rv["serious_errors"]:
        add("| Draft | Draft words | Problem | Source words |")
        add("|---|---|---|---|")
        for e in rv["serious_errors"]:
            add(f"| {e['draft']} | {_cell(e['claim_quote'])} | {_cell(e['problem'])} | {_cell(e['source_quote'] or 'ABSENT')} |")
    else:
        add("None (or no judgements).")
    add("")
    add(f"### Owner / time-window fields classified unsupported ({len(rv['unsupported_fields'])})")
    add("")
    if rv["unsupported_fields"]:
        add("| Draft | Item | Field | Draft words | Rule result | Nearest source text |")
        add("|---|---:|---|---|---|---|")
        for f in rv["unsupported_fields"]:
            add(f"| {f['draft']} | {f['item']} | {f['field']} | {_cell(f['value'])} | {_cell(f['reason'])} | {_cell(f['nearest_source'])} |")
    else:
        add("None.")
    add("")
    return "\n".join(L)


# --------------------------------------------------------------------------------------------------
# Compact app summary (replays/cat2_not_stated_summary.json)
# --------------------------------------------------------------------------------------------------

APP_SUMMARY_SCHEMA_VERSION = 1
APP_SUMMARY_PATH = qs.BACKEND_DIR / "replays" / "cat2_not_stated_summary.json"
# Fixed example rule (not chosen by outcome): this bundle, this model, this repeat, action items in order.
EXAMPLE_RULE = {"preset_id": "reg-02", "model_key": "sonnet", "repeat_index": 0}


def _h2h(block: dict[str, Any] | None) -> dict[str, Any] | None:
    if not block:
        return None
    out = {k: {"wins": block[k]["not_stated_wins"], "losses": block[k]["other_wins"], "ties": block[k]["ties"]}
           for k in ("overall", *qs.PAIR_DIMENSIONS)}
    pc = block["overall"]["position_consistency"]
    return {**out, "calls": block["calls"], "position_consistency": {"pairs": pc["units_with_both_orders"], "consistent": pc["consistent"]}}


def _example(draft_records: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    latest = latest_ok_by(draft_records, "draft_key")
    pid, m, k = EXAMPLE_RULE["preset_id"], EXAMPLE_RULE["model_key"], EXAMPLE_RULE["repeat_index"]
    o, n = latest.get(draft_key(pid, m, ARM_ORIGINAL, k)), latest.get(draft_key(pid, m, ARM_NOT_STATED, k))
    if not o or not n:
        return None
    payload = qs.preset_map()[pid]["payload"]

    def side(rec: dict[str, Any]) -> list[dict[str, Any]]:
        plan = (rec.get("structured_draft") or {}).get("action_plan") or []
        cls = classify_action_items(rec.get("structured_draft"), payload)
        return [{"milestone": a.get("milestone"), "owner": a.get("owner"), "time_window": a.get("target_window"),
                 "owner_class": c["owner_class"], "window_class": c["window_class"]} for a, c in zip(plan, cls)]

    so, sn = side(o), side(n)
    return {
        "rule": f"{pid}, {m}, repeat {k}, action items in order (fixed in advance, not chosen by outcome)",
        **EXAMPLE_RULE,
        "items": [{"slot": i + 1, "original": a, "not_stated": b} for i, (a, b) in enumerate(zip(so, sn))],
    }


def build_app_summary(
    draft_records: Sequence[dict[str, Any]],
    judgements: Sequence[dict[str, Any]],
    *,
    keys: dict[str, Any] | None = None,
    source_files: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Timestamp-free view of the follow-up for the app, built from `analyse()` (the analysis code path)."""
    if not judgements:
        raise ValueError("No judge records: the app summary needs the blind-judge results.")
    s = analyse(draft_records, judgements, keys=keys, baseline_summary=None)
    cells = []
    for g in s["groups"].values():
        owners_ns_by_preset = {pid: b["owner"]["not_stated"] for pid, b in g["by_preset"].items()}
        cells.append(
            {
                "arm": g["arm"],
                "model_key": g["model_key"],
                "drafts": g["drafts"],
                "action_items": g["action_items"],
                "owner": g["owner"],
                "time_window": g["time_window"],
                "owner_not_stated_by_preset": owners_ns_by_preset,
                "owner_supported_by_preset": {pid: b["owner"]["supported"] for pid, b in g["by_preset"].items()},
                "serious_per_draft": g["serious_per_draft"]["mean"],
                "minor_per_draft": g["minor_per_draft"]["mean"],
                "serious_total": g["serious_total"],
                "flagged_items_total": g["flagged_items_total"],
                "rubric": {d: g["rubric"][d]["mean"] for d in qs.DIMENSIONS},
                "core_facts": g["core_facts"],
                "detail_facts": g["detail_facts"],
                "cost_per_1k_docs_usd": g["cost_per_1k_docs_usd"]["mean"],
                "output_tokens_mean": g["output_tokens"]["mean"],
                "truncated": g["truncated"],
            }
        )
    pw = s["pairwise"]
    comps = Counter((r.get("meta") or {}).get("comparison") for r in qs.latest_ok(judgements).values())
    dq, jdq = s["drafts_data_quality"], s["judge_data_quality"]
    return {
        "schema_version": APP_SUMMARY_SCHEMA_VERSION,
        "source": "cat2 not-stated follow-up (blind judge)",
        "source_files": dict(source_files or {}),
        "app_template": ARM_ORIGINAL,
        "added_instruction": ADDED_INSTRUCTION,
        "not_stated_literal": NOT_STATED,
        "keys_version": s["design"]["keys_version"],
        "judge_model": qs.JUDGE_MODEL,
        "judge_models_returned": sorted(m for m in jdq["model_ids_returned"] if m),
        "judge_passes_per_draft": 1,
        "counts": {
            "drafts": dq["ok_drafts"],
            "drafts_planned": s["design"]["planned_drafts"],
            "drafts_per_cell": REPEATS * len(qs.PRESET_IDS),
            "drafts_per_document_model_template": REPEATS,
            "documents": len(qs.PRESET_IDS),
            "truncated": dq["truncated"],
            "judge_ok_calls": jdq["ok_calls"],
            "judge_error_records": jdq["error_records"],
            "rubric_calls": comps.get("rubric", 0),
            "pairwise_vs_original_calls": comps.get("matched", 0),
            "pairwise_vs_unbounded_calls": comps.get("vs_unbounded", 0),
        },
        "field_rules": list(FIELD_RULES),
        "cells": cells,
        "head_to_head": {
            "vs_original": {"all": _h2h(pw["matched"]["all"]), "by_model": {m: _h2h(b) for m, b in pw["matched"]["by_model"].items()}},
            "vs_unbounded": {"all": _h2h(pw["vs_unbounded"]["all"]), "by_model": {m: _h2h(b) for m, b in pw["vs_unbounded"]["by_model"].items()}},
        },
        "example": _example(draft_records),
    }
