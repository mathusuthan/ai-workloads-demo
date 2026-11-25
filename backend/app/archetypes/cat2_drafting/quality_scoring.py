"""Category 2 quality scoring: uniform draft rendering, deterministic scoring, blind-judge orchestration, aggregation.

Scores the 12 stored drafts in `replays/cat2_golden_replays.json` (4 source bundles x 3 rungs). Nothing is
re-drafted. Importable without an API key; the only network code is `make_anthropic_judge_call`, which the
CLI injects (tests inject a fake).

Deterministic measures (offline):
  A. `render_draft` — every draft scored as the same kind of plain Markdown text.
  B. fact coverage against `app/data/cat2_quality_keys.json` (Cat 3 normaliser + boundary-guarded matcher).
  C. unsupported numbers — every numeric token in the draft classified `in_source` / `not_in_source`, with
     explicit, tested ignore rules for non-claims.
Judge (live, run by the lead): rubric (5 dims + factual errors + review of measure-C numbers) and pairwise
preference, both blind.
"""

from __future__ import annotations

import asyncio
import hashlib
import itertools
import json
import math
import re
import statistics
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

# Pure Category 3 helpers, reused rather than copied (normaliser + boundary-guarded matcher).
from app.archetypes.cat3_assistants.scoring import (
    NORMALISATION_RULES,
    contains_alternative,
    normalise_text,
)
from app.archetypes.cat6_swarms.fair_rerun import wilson_interval
from app.core.pricing import LEGACY_MODEL_RATES, MODEL_RATES, compute_run_finops
from app.data.cat2_fixtures import CAT2_PRESETS

SCHEMA_VERSION = 1
BACKEND_DIR = Path(__file__).resolve().parents[3]
KEYS_PATH = BACKEND_DIR / "app" / "data" / "cat2_quality_keys.json"
REPLAYS_PATH = BACKEND_DIR / "replays" / "cat2_golden_replays.json"
EXPERIMENT_DIR = BACKEND_DIR / "experiments" / "cat2_quality"
DETERMINISTIC_PATH = EXPERIMENT_DIR / "deterministic.json"
JUDGEMENTS_PATH = EXPERIMENT_DIR / "judgements.jsonl"

RUNG_IDS: tuple[str, ...] = ("sonnet_unbounded", "sonnet_templated", "haiku_templated")
PRESET_IDS: tuple[str, ...] = tuple(p["id"] for p in CAT2_PRESETS)
FACT_TIERS: tuple[str, ...] = ("core", "detail")
FACT_CATEGORIES: tuple[str, ...] = ("metric", "money", "deadline", "owner", "decision", "cause")

# --------------------------------------------------------------------------------------------------
# Judge settings.
# ASSUMPTION — LEAD MUST CONFIRM: Claude Opus 5.5 list price $4.00 / 1M input, $20.00 / 1M output
# (cache write $5.00, cache read $0.20). Source: the bundled claude-api skill's model table
# ("Current Models (cached: 2026-11-03)"); `app/core/pricing.py` has no Opus rate. Output tokens include
# adaptive-thinking tokens (billed as output).
# --------------------------------------------------------------------------------------------------
JUDGE_MODEL = "claude-opus-5-5"
OPUS_INPUT_PER_1M_USD = 4.00
OPUS_OUTPUT_PER_1M_USD = 20.00
OPUS_CACHE_WRITE_PER_1M_USD = 5.00
OPUS_CACHE_READ_PER_1M_USD = 0.20
JUDGE_MAX_TOKENS = 8000
JUDGE_TIMEOUT_S = 300.0
JUDGE_THINKING: dict[str, str] = {"type": "adaptive"}
# Explicit, and equal to the API default for Opus 5.5 (medium), so the setting is recorded rather than implied.
JUDGE_EFFORT = "medium"
RUBRIC_REPEATS = 3
DIMENSIONS: tuple[str, ...] = ("factual_accuracy", "coverage", "clarity", "actionability", "concision")
NUMBER_VERDICTS: tuple[str, ...] = (
    "derived_correct",
    "derived_incorrect",
    "not_in_source_unverifiable",
    "not_a_claim",
)
PAIR_DIMENSIONS: tuple[str, ...] = ("accuracy", "usefulness_to_reader")
# Calibrated on the stored unbounded rung (system prompt + payload chars / recorded input tokens, no schema):
# see `calibrate_chars_per_token`. Used only for the dry-run estimate and the budget guard's next-call check.
DEFAULT_CHARS_PER_TOKEN = 2.25

# Target deliverable and reader per bundle. Each value is a verbatim substring of that bundle's payload (tested).
TARGETS: dict[str, dict[str, str]] = {
    "brief-01": {
        "deliverable": "Executive Operational Readout & Board Action Memo",
        "reader": "the CEO and CFO readout tonight",
    },
    "brief-02": {
        "deliverable": (
            "Synthesize these commercial terms, margin tradeoffs (175bps commission concession + $0.75/unit FBO "
            "subsidy vs. $480k guaranteed Co-Op spend + $18M Year-1 exclusive launch allocation), operational "
            "safeguards, and contractual closure gates for AetherSonic Executive Sign-Off."
        ),
        "reader": "AetherSonic Executive Sign-Off",
    },
    "reg-01": {
        "deliverable": "MARKETPLACE SAFETY & DGCA/BUREAU COMPLIANCE FILING",
        "reader": "Marketplace Safety Regulator & Board Audit Committee",
    },
    "reg-02": {
        "deliverable": (
            "Synthesize the exact cohort metrics (1,850 audited sellers, 68.2% false-positive 409 rate vs 68 genuine "
            "compliance gaps totaling $1.41M), SLA slippage (83.5h observed vs 48h contractual cap), PII gate remediation "
            "(194 pre-gate vs 0 post-gate), AML shell-ring prevention ($286k synthetic GMV blocked), and time-bound "
            "engineering/Treasury remediation milestones."
        ),
        "reader": "Board Risk & Audit Committee + Payments Nodal Regulator",
    },
}

# The bundle's own document ID line (numbers inside it are not claims).
_DOC_ID_RE = re.compile(r"^(?:meeting_id|opportunity_id|filing_reference|audit_id):\s*(\S+)", re.M)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def preset_map() -> dict[str, dict[str, Any]]:
    return {p["id"]: p for p in CAT2_PRESETS}


def document_ids(payload: str) -> list[str]:
    return _DOC_ID_RE.findall(payload)


# --------------------------------------------------------------------------------------------------
# A. Uniform rendering
# --------------------------------------------------------------------------------------------------


def _humanise_enum(value: str) -> str:
    return " ".join(w.capitalize() for w in str(value).replace("_", " ").split())


def _txt(value: Any) -> str:
    return " ".join(str(value or "").split())


def render_structured_draft(draft: dict[str, Any]) -> str:
    """Render a templated `structured_draft` as readable Markdown (headings + prose/bullets, no JSON keys)."""
    out: list[str] = []
    add = out.append
    title = _txt(draft.get("document_title"))
    if title:
        add(f"# {title}")
        add("")
    if draft.get("document_type"):
        add(f"*{_humanise_enum(draft['document_type'])}*")
        add("")

    es = draft.get("executive_summary") or {}
    if es:
        add("## Executive Summary")
        add("")
        if es.get("headline"):
            add(f"**{_txt(es['headline'])}**")
            add("")
        if es.get("narrative"):
            add(_txt(es["narrative"]))
            add("")
        if es.get("bottom_line_impact"):
            add(f"**Bottom line:** {_txt(es['bottom_line_impact'])}")
            add("")

    findings = draft.get("key_findings") or []
    if findings:
        add("## Key Findings")
        add("")
        for f in findings:
            head = " · ".join(x for x in (_txt(f.get("id")), _txt(f.get("theme"))) if x)
            add(f"### {head}" if head else "###")
            add("")
            if f.get("quantified_evidence"):
                add(_txt(f["quantified_evidence"]))
                add("")
            if f.get("source_anchor"):
                add(f"*Source: {_txt(f['source_anchor'])}*")
                add("")

    risks = draft.get("risk_and_compliance_matrix") or []
    if risks:
        add("## Risk & Compliance Matrix")
        add("")
        for r in risks:
            head = _txt(r.get("domain"))
            if r.get("severity"):
                head = f"{head} (severity: {_txt(r['severity'])})" if head else f"Severity: {_txt(r['severity'])}"
            add(f"### {head}")
            add("")
            if r.get("exposure_summary"):
                add(f"- **Exposure:** {_txt(r['exposure_summary'])}")
            if r.get("mitigation_control"):
                add(f"- **Mitigation:** {_txt(r['mitigation_control'])}")
            add("")

    actions = draft.get("action_plan") or []
    if actions:
        add("## Action Plan")
        add("")
        for a in actions:
            head = " — ".join(x for x in (_txt(a.get("owner")), _txt(a.get("target_window"))) if x)
            add(f"### {head}" if head else "###")
            add("")
            if a.get("milestone"):
                add(f"- **Milestone:** {_txt(a['milestone'])}")
            if a.get("verification_metric"):
                add(f"- **Verification:** {_txt(a['verification_metric'])}")
            add("")
    return "\n".join(out).rstrip() + "\n"


def render_draft(rung_data: dict[str, Any]) -> str:
    """Plain text for one stored rung: unbounded = raw_markdown as is; templated = rendered structured_draft."""
    sd = rung_data.get("structured_draft") or {}
    if isinstance(sd, dict) and "executive_summary" in sd:
        return render_structured_draft(sd)
    return str(rung_data.get("raw_markdown") or "")


def load_replays(path: Path | str | None = None) -> dict[str, Any]:
    return json.loads(Path(path or REPLAYS_PATH).read_text(encoding="utf-8"))


def iter_drafts(replays: dict[str, Any]) -> list[dict[str, Any]]:
    """[{preset_id, rung_id, model_id, input_tokens, output_tokens, stop_reason, text}] in PRESET x RUNG order."""
    out: list[dict[str, Any]] = []
    presets = replays.get("presets") or {}
    for pid in PRESET_IDS:
        rungs = (presets.get(pid) or {}).get("rungs") or {}
        for rid in RUNG_IDS:
            if rid not in rungs:
                continue
            r = rungs[rid]
            out.append(
                {
                    "preset_id": pid,
                    "rung_id": rid,
                    "model_id": r.get("model_id"),
                    "input_tokens": int(r.get("input_tokens") or 0),
                    "output_tokens": int(r.get("output_tokens") or 0),
                    "thinking_tokens": int(r.get("thinking_tokens") or 0),
                    "stop_reason": r.get("stop_reason"),
                    "text": render_draft(r),
                }
            )
    return out


# --------------------------------------------------------------------------------------------------
# B. Fact coverage
# --------------------------------------------------------------------------------------------------


def load_quality_keys(path: Path | str | None = None) -> dict[str, Any]:
    return json.loads(Path(path or KEYS_PATH).read_text(encoding="utf-8"))


def facts_for(keys: dict[str, Any], preset_id: str) -> list[dict[str, Any]]:
    return [f for f in keys["facts"] if f["preset_id"] == preset_id]


def key_counts(keys: dict[str, Any]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for f in keys["facts"]:
        slot = out.setdefault(f["preset_id"], {})
        for k in ("total", f"tier:{f['tier']}", f"category:{f['category']}"):
            slot[k] = slot.get(k, 0) + 1
    return out


def score_facts(text: str, facts: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """[{fact_id, tier, category, hit, matched}] — `matched` = the first any_of alternative found (or None)."""
    norm = normalise_text(text)
    rows = []
    for f in facts:
        matched = next((a for a in f["any_of"] if contains_alternative(norm, a)), None)
        rows.append(
            {"fact_id": f["id"], "tier": f["tier"], "category": f["category"], "hit": matched is not None, "matched": matched}
        )
    return rows


def proportion(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    k = sum(1 for r in rows if r["hit"])
    n = len(rows)
    return {"hits": k, "total": n, "rate": (k / n) if n else None, "wilson95": wilson_interval(k, n)}


def coverage_summary(rows: Sequence[dict[str, Any]], output_tokens: int) -> dict[str, Any]:
    hits = sum(1 for r in rows if r["hit"])
    return {
        "overall": proportion(rows),
        "core": proportion(r for r in rows if r["tier"] == "core"),
        "detail": proportion(r for r in rows if r["tier"] == "detail"),
        "by_category": {c: proportion(r for r in rows if r["category"] == c) for c in FACT_CATEGORIES},
        "facts_per_1k_output_tokens": (hits / output_tokens * 1000) if output_tokens else None,
    }


# --------------------------------------------------------------------------------------------------
# C. Numeric tokens
# --------------------------------------------------------------------------------------------------

_MONTHS: dict[str, int] = {
    "Jan": 1, "January": 1, "Feb": 2, "February": 2, "Mar": 3, "March": 3, "Apr": 4, "April": 4, "May": 5,
    "Jun": 6, "June": 6, "Jul": 7, "July": 7, "Aug": 8, "August": 8, "Sep": 9, "Sept": 9, "September": 9,
    "Oct": 10, "October": 10, "Nov": 11, "November": 11, "Dec": 12, "December": 12,
}
_MON = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Sept|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
_NUM = r"\d{1,3}(?:,\d{2})*(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_MAG_WORD = r"million|billion|thousand|lakhs?|crores?|mn|bn"
_TOKEN_RE = re.compile(
    "|".join(
        [
            # ISO date / datetime (2026-08-29, 2026-11-16T15:30:00Z, 2026-08-29T04:18:00+05:30)
            r"(?P<iso>(?<!\d)(?P<iso_y>\d{4})-(?P<iso_m>\d{2})-(?P<iso_d>\d{2})"
            r"(?:T(?P<iso_hh>\d{2}):(?P<iso_mm>\d{2})(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?)?(?!\d))",
            # Month YYYY (September 2026)
            rf"(?P<my>\b(?P<my_m>{_MON})\.?\s+(?P<my_y>(?:19|20)\d{{2}})(?!\d))",
            # Month D[, YYYY] (November 15, 2026 · Nov 30 · Feb 15th)
            rf"(?P<md>\b(?P<md_m>{_MON})\.?\s+(?P<md_d>\d{{1,2}})(?:st|nd|rd|th)?(?!\d)(?:,?\s+(?P<md_y>(?:19|20)\d{{2}})(?!\d))?)",
            # D Month[ YYYY] (15 November 2026)
            rf"(?P<dm>(?<![\d.,])(?P<dm_d>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<dm_m>{_MON})\b\.?(?:,?\s+(?P<dm_y>(?:19|20)\d{{2}})(?!\d))?)",
            # Time of day (13:30Z, 04:18 IST, [15:31:04])
            r"(?P<time>(?<![\d:.])(?P<t_hh>[01]?\d|2[0-3]):(?P<t_mm>[0-5]\d)(?::[0-5]\d)?(?!\d)(?:Z|\s?(?:UTC|IST|GMT)\b)?)",
            # A lowercase English word hyphenated onto a number/code ("sub-4.2x", "trailing-60-day", "post-12:00Z",
            # "pre-T+7"): consume only the word and hyphen so the rest is tokenised on its own.
            r"(?P<wprefix>(?<![A-Za-z0-9])[a-z]{2,}-(?=[\d$₹A-Z]))",
            # Letter-initial word / identifier (consumes words so numbers are never matched inside them):
            # Q3, FY2027, UN38.3, T+1, KF-1, Tier-1, SLR-77401, ESCROW_HOLD_409, INC-2026-08-29-PNQ2
            r"(?P<ident>(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9]*(?:(?:[-_+#][A-Za-z0-9]+)|(?:\.(?=\d)\d+[A-Za-z0-9]*))*)",
            # Number with optional currency and unit/magnitude
            rf"(?P<number>(?P<cur>\$|₹)?(?P<num>{_NUM})"
            rf"(?P<unit>\s(?:{_MAG_WORD})\b|%|[A-Za-z×µ]+(?:/[A-Za-z]+)?|-(?=[A-Za-z])[A-Za-z]+)?)",
        ]
    )
)
_MAGNITUDE_EXACT: dict[str, float] = {"k": 1e3, "K": 1e3, "M": 1e6, "MM": 1e6, "mn": 1e6, "Mn": 1e6, "B": 1e9, "bn": 1e9, "Bn": 1e9}
_MAGNITUDE_WORDS: dict[str, float] = {
    "thousand": 1e3, "million": 1e6, "billion": 1e9, "lakh": 1e5, "lakhs": 1e5, "crore": 1e7, "crores": 1e7,
    "mn": 1e6, "bn": 1e9,
}
_RANGE_SEP_RE = re.compile(r"^\s*(?:[-–—]|to)\s*$")
_LABEL_WORDS = (
    "finding", "risk", "action", "step", "phase", "milestone", "recommendation", "table", "exhibit", "appendix",
    "option", "workstream", "item", "section", "priority", "part", "figure",
)
_LABEL_WORD_RE = re.compile(rf"\b(?P<word>{'|'.join(_LABEL_WORDS)})\s*#?\s*$", re.I)
_OWN_LABEL_IDENT_RE = re.compile(r"^(?:[A-Z]{1,3}-\d{1,2}|(?:KF|RF|RC|RM|AP|AC|F|R|A)\d{1,2})$")
_LIST_NUMBER_RE = re.compile(r"^[ \t]*(?:#{1,6}[ \t]+)?(?:\*\*)?(?P<n>\d{1,2})[.)](?:\*\*)?[ \t]")
_HEADING_NUMBER_RE = re.compile(r"^#{1,6}[ \t]+(?:\*\*)?(?P<n>\d{1,2}(?:\.\d{1,2})+)\.?(?:\*\*)?[ \t]")
_TABLE_RANK_RE = re.compile(r"^[ \t]*\|[ \t]*(?P<n>\d{1,2})[ \t]*\|")
_YEAR_ANY_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")

IGNORE_RULES: tuple[tuple[str, str], ...] = (
    ("list_numbering", "Integer 1–99 that opens a line as a list/heading number ('1.', '2)', '## 3.', '## 3.2 ...') "
     "or is the whole first cell of a table row ('| 1 |')."),
    ("own_label", "The draft's own ordinal label, when not present in the source: a short code (KF-1, KF-03, R-2, "
     "F2), or a small integer / dotted section number / section code directly after a label word (Finding 1, Risk 2, "
     "Section 4, Section 2.4, Section A.1, Table 1, ...)."),
    ("in_title", "Any number on the document title line (the first '# ' heading)."),
    ("document_id", "The source bundle's own document ID (its meeting_id / opportunity_id / filing_reference / "
     "audit_id value) quoted in the draft."),
    ("date_in_source", "A calendar date (ISO, 'Month D[, YYYY]', 'D Month', 'Month YYYY') whose month/day (and year, "
     "when given) also appears in the source in any date format."),
    ("year_in_source", "A bare year 1900–2099 (no currency/unit/separators) that appears anywhere in the source "
     "(also inside IDs/dates such as FY2027 or 2026-08-29)."),
)
CLASSIFICATION_RULES: tuple[str, ...] = (
    "Numbers: value = digits without thousands separators (western 1,234,567 and Indian 1,48,000), times a "
    "magnitude for k/K, M/MM/mn, B/bn, 'm'/'b' only after a currency sign, and the words thousand/million/billion/"
    "lakh/crore. %, x, bps, h, ms, -day etc. are kept as the unit but do not change the value. Sign is recorded but "
    "matching uses the absolute value. In a range 'A–B' where only B carries a magnitude ($115–180K), A is also "
    "tried with B's magnitude.",
    "in_source: the value (rounded to 6 decimals) equals the value of any numeric token extracted from the payload "
    "the same way, or a digit run inside a payload identifier; times (HH:MM) match a payload time; identifiers "
    "match the payload case-insensitively with '-', '_' and spaces treated alike.",
    "not_in_source: everything else not covered by an ignore rule — including rounded or derived figures, which "
    "measure C does not try to judge.",
    "Not extracted: numbers written as words (three, zero); digits glued to a preceding letter are part of an "
    "identifier (Q3, FY2027, UN38.3, p99) and classified as identifiers.",
)


def _round_value(v: float) -> float:
    return round(float(v), 6)


def _magnitude(unit: str, has_currency: bool) -> float:
    base = unit.strip().split("/")[0]
    if not base:
        return 1.0
    if base in _MAGNITUDE_EXACT:
        return _MAGNITUDE_EXACT[base]
    if base.lower() in _MAGNITUDE_WORDS:
        return _MAGNITUDE_WORDS[base.lower()]
    if has_currency and base == "m":
        return 1e6
    if has_currency and base == "b":
        return 1e9
    return 1.0


def _norm_ident(s: str) -> str:
    return re.sub(r"[\s_\-]+", "-", s.lower())


def _line_bounds(text: str, pos: int) -> tuple[int, int]:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return start, (len(text) if end < 0 else end)


def extract_tokens(text: str) -> list[dict[str, Any]]:
    """Every numeric-bearing token in `text`, in order. Words without digits are consumed but not returned.

    Each token: {kind: number|time|date|identifier, text, start, end, ...kind fields}. Number tokens carry
    `values` (candidate canonical values), `unit`, `currency`, `sign`. A lowercase English prefix hyphenated
    onto a number ("sub-4.2x", "trailing-60-day", "post-12:00Z") is split off and the rest tokenised again.
    """
    full = text
    tokens: list[dict[str, Any]] = []
    for m in _TOKEN_RE.finditer(text):
        start, end = m.start(), m.end()
        if m.group("wprefix"):
            continue
        if m.group("iso"):
            y, mo, d = int(m.group("iso_y")), int(m.group("iso_m")), int(m.group("iso_d"))
            tok: dict[str, Any] = {"kind": "date", "y": y, "m": mo, "d": d}
            if m.group("iso_hh"):
                tok["time"] = f"{int(m.group('iso_hh')):02d}:{m.group('iso_mm')}"
        elif m.group("my"):
            tok = {"kind": "date", "y": int(m.group("my_y")), "m": _MONTHS[m.group("my_m")], "d": None}
        elif m.group("md"):
            tok = {
                "kind": "date",
                "y": int(m.group("md_y")) if m.group("md_y") else None,
                "m": _MONTHS[m.group("md_m")],
                "d": int(m.group("md_d")),
            }
        elif m.group("dm"):
            tok = {
                "kind": "date",
                "y": int(m.group("dm_y")) if m.group("dm_y") else None,
                "m": _MONTHS[m.group("dm_m")],
                "d": int(m.group("dm_d")),
            }
        elif m.group("time"):
            tok = {"kind": "time", "time": f"{int(m.group('t_hh')):02d}:{m.group('t_mm')}"}
        elif m.group("ident"):
            raw = m.group("ident")
            if not any(ch.isdigit() for ch in raw):
                continue
            tok = {"kind": "identifier", "digit_runs": [float(x) for x in re.findall(r"\d+(?:\.\d+)?", raw)]}
        else:
            num = m.group("num")
            # "3.2.1" section numbers: the trailing ".1" is not a number of its own.
            if start >= 2 and full[start - 1] == "." and full[start - 2].isdigit():
                continue
            cur = (m.group("cur") or "").strip()
            unit = m.group("unit") or ""
            base = float(num.replace(",", ""))
            mag = _magnitude(unit, bool(cur))
            sign = ""
            if start >= 1 and full[start - 1] in "-−+" and (start < 2 or full[start - 2] in " \t\n([|"):
                sign = "-" if full[start - 1] in "-−" else "+"
            tok = {
                "kind": "number",
                "num": num,
                "currency": cur,
                "unit": unit.strip(),
                "magnitude": mag,
                "sign": sign,
                "values": [_round_value(base * mag)],
                "is_plain_integer": cur == "" and unit == "" and "," not in num and "." not in num,
            }
        tok.update({"text": full[start:end], "start": start, "end": end})
        tokens.append(tok)

    # Range propagation: "A–B" where A has no magnitude and B does -> A also tried at B's magnitude.
    for a, b in zip(tokens, tokens[1:]):
        if a["kind"] == b["kind"] == "number" and a["magnitude"] == 1.0 and b["magnitude"] != 1.0:
            gap = text[a["end"] : b["start"]]
            if _RANGE_SEP_RE.match(gap.replace("$", "").replace("₹", "")):
                base = float(a["num"].replace(",", ""))
                a["values"] = sorted({*a["values"], _round_value(base * b["magnitude"])})
    return tokens


@dataclass(frozen=True)
class SourceIndex:
    values: frozenset[float]
    times: frozenset[str]
    dates_md: frozenset[tuple[int, int]]
    dates_ymd: frozenset[tuple[int | None, int, int]]
    dates_ym: frozenset[tuple[int, int]]
    years: frozenset[int]
    ident_text: str
    doc_ids: frozenset[str]
    norm_text: str


def build_source_index(payload: str) -> SourceIndex:
    values: set[float] = set()
    times: set[str] = set()
    md: set[tuple[int, int]] = set()
    ymd: set[tuple[int | None, int, int]] = set()
    ym: set[tuple[int, int]] = set()
    for t in extract_tokens(payload):
        if t["kind"] == "number":
            values.update(t["values"])
        elif t["kind"] == "identifier":
            values.update(_round_value(v) for v in t["digit_runs"])
        elif t["kind"] == "time":
            times.add(t["time"])
        elif t["kind"] == "date":
            if t.get("time"):
                times.add(t["time"])
            if t["d"] is not None:
                md.add((t["m"], t["d"]))
                ymd.add((t["y"], t["m"], t["d"]))
            if t["y"] is not None:
                ym.add((t["y"], t["m"]))
    years = {int(y) for y in _YEAR_ANY_RE.findall(payload)}
    return SourceIndex(
        values=frozenset(values),
        times=frozenset(times),
        dates_md=frozenset(md),
        dates_ymd=frozenset(ymd),
        dates_ym=frozenset(ym),
        years=frozenset(years),
        ident_text=_norm_ident(payload),
        doc_ids=frozenset(_norm_ident(d) for d in document_ids(payload)),
        norm_text=normalise_text(payload),
    )


def _ident_in_source(raw: str, idx: SourceIndex) -> bool:
    needle = _norm_ident(raw)
    hay = idx.ident_text
    i = hay.find(needle)
    while i >= 0:
        j = i + len(needle)
        if (i == 0 or not hay[i - 1].isalnum()) and (j >= len(hay) or not hay[j].isalnum()):
            return True
        i = hay.find(needle, i + 1)
    return False


def _date_in_source(t: dict[str, Any], idx: SourceIndex) -> bool:
    y, m, d = t["y"], t["m"], t["d"]
    if d is None:
        return y is not None and (y, m) in idx.dates_ym
    if y is None:
        return (m, d) in idx.dates_md
    return (y, m, d) in idx.dates_ymd or ((None, m, d) in idx.dates_ymd and y in idx.years)


def _snippet(text: str, start: int, end: int, width: int = 80) -> str:
    a, b = max(0, start - width), min(len(text), end + width)
    return ("…" if a > 0 else "") + " ".join(text[a:b].split()) + ("…" if b < len(text) else "")


def _ignore_reason(text: str, t: dict[str, Any], idx: SourceIndex, title_span: tuple[int, int] | None) -> str | None:
    start = t["start"]
    if title_span and title_span[0] <= start < title_span[1]:
        return "in_title"
    ls, le = _line_bounds(text, start)
    line = text[ls:le]
    col = start - ls
    if t["kind"] == "number":
        for rx in (_LIST_NUMBER_RE, _HEADING_NUMBER_RE, _TABLE_RANK_RE):
            mm = rx.match(line)
            if mm and mm.start("n") == col and mm.end("n") == col + len(t["num"]):
                return "list_numbering"
        mlabel = _LABEL_WORD_RE.search(text[max(0, start - 40) : start])
        label_like = (t["is_plain_integer"] and int(t["num"]) < 100) or (
            not t["unit"] and not t["currency"] and re.fullmatch(r"\d{1,2}(?:\.\d{1,2})+", t["num"]) is not None
        )
        if mlabel and label_like:
            phrase = normalise_text(f"{mlabel.group('word')} {t['num']}")
            if not contains_alternative(idx.norm_text, phrase):
                return "own_label"
        if t["is_plain_integer"] and len(t["num"]) == 4 and 1900 <= int(t["num"]) <= 2099:
            if int(t["num"]) in idx.years:
                return "year_in_source"
    elif t["kind"] == "identifier":
        if _norm_ident(t["text"]) in idx.doc_ids:
            return "document_id"
        if not _ident_in_source(t["text"], idx):
            if _OWN_LABEL_IDENT_RE.match(t["text"]):
                return "own_label"
            mlabel = _LABEL_WORD_RE.search(text[max(0, start - 40) : start])
            if mlabel and re.fullmatch(r"[A-Z]{1,2}(?:\.\d{1,2})+", t["text"]):
                return "own_label"  # a section reference such as "Section A.1"
    elif t["kind"] == "date":
        if _date_in_source(t, idx):
            return "date_in_source"
    return None


def _in_source(t: dict[str, Any], idx: SourceIndex) -> bool:
    if t["kind"] == "number":
        return any(v in idx.values for v in t["values"])
    if t["kind"] == "time":
        return t["time"] in idx.times
    if t["kind"] == "identifier":
        return _ident_in_source(t["text"], idx)
    return False  # dates in source are ignored before this point


def _title_span(text: str) -> tuple[int, int] | None:
    m = re.search(r"^# [^\n]*", text, re.M)
    return (m.start(), m.end()) if m else None


def classify_numbers(draft_text: str, payload: str, *, source_index: SourceIndex | None = None) -> list[dict[str, Any]]:
    """Every numeric token of the draft with classification `in_source` | `not_in_source` | `ignored`."""
    idx = source_index or build_source_index(payload)
    title = _title_span(draft_text)
    rows: list[dict[str, Any]] = []
    for t in extract_tokens(draft_text):
        reason = _ignore_reason(draft_text, t, idx, title)
        cls = "ignored" if reason else ("in_source" if _in_source(t, idx) else "not_in_source")
        row = {
            "text": t["text"],
            "kind": t["kind"],
            "start": t["start"],
            "classification": cls,
            "ignore_reason": reason,
            "snippet": _snippet(draft_text, t["start"], t["end"]),
        }
        if t["kind"] == "number":
            row.update({"values": t["values"], "unit": t["unit"], "currency": t["currency"], "sign": t["sign"]})
        rows.append(row)
    return rows


def numbers_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    considered = [r for r in rows if r["classification"] != "ignored"]
    nis = [r for r in considered if r["classification"] == "not_in_source"]
    return {
        "tokens_extracted": len(rows),
        "ignored": len(rows) - len(considered),
        "ignored_by_reason": dict(Counter(r["ignore_reason"] for r in rows if r["ignore_reason"])),
        "numeric_tokens": len(considered),
        "in_source": len(considered) - len(nis),
        "not_in_source": len(nis),
        "not_in_source_share": (len(nis) / len(considered)) if considered else None,
    }


def not_in_source_list(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """The measure-C list passed to the judge, with deterministic per-draft ids N01, N02, ..."""
    out = []
    for i, r in enumerate((r for r in rows if r["classification"] == "not_in_source"), start=1):
        out.append({"id": f"N{i:02d}", "text": r["text"], "kind": r["kind"], "snippet": r["snippet"]})
    return out


# --------------------------------------------------------------------------------------------------
# Deterministic phase
# --------------------------------------------------------------------------------------------------


def _finops(model_id: str | None, input_tokens: int, output_tokens: int):
    mid = model_id if (model_id in MODEL_RATES or model_id in LEGACY_MODEL_RATES) else "claude-sonnet-5-5"
    return compute_run_finops(model_id=mid, input_tokens=input_tokens, output_tokens=output_tokens)


def score_draft(draft: dict[str, Any], payload: str, facts: Sequence[dict[str, Any]]) -> dict[str, Any]:
    fact_rows = score_facts(draft["text"], facts)
    num_rows = classify_numbers(draft["text"], payload)
    fin = _finops(draft.get("model_id"), draft["input_tokens"], draft["output_tokens"])
    return {
        "preset_id": draft["preset_id"],
        "rung_id": draft["rung_id"],
        "model_id": draft.get("model_id"),
        "input_tokens": draft["input_tokens"],
        "output_tokens": draft["output_tokens"],
        "thinking_tokens": draft.get("thinking_tokens", 0),
        "recorded_stop_reason": draft.get("stop_reason"),
        "cost_usd": fin.total_cost_usd,
        "cost_per_1k_docs_usd": fin.cost_per_1k_usd,
        "rendered_chars": len(draft["text"]),
        "rendered_words": len(draft["text"].split()),
        "text_sha256": hashlib.sha256(draft["text"].encode("utf-8")).hexdigest(),
        "text": draft["text"],
        "facts": fact_rows,
        "coverage": coverage_summary(fact_rows, draft["output_tokens"]),
        "numbers": num_rows,
        "numbers_summary": numbers_summary(num_rows),
        "not_in_source": not_in_source_list(num_rows),
    }


def _pool_numbers(cells: Sequence[dict[str, Any]]) -> dict[str, Any]:
    tot = Counter()
    by_reason: Counter[str] = Counter()
    for c in cells:
        s = c["numbers_summary"]
        for k in ("tokens_extracted", "ignored", "numeric_tokens", "in_source", "not_in_source"):
            tot[k] += s[k]
        by_reason.update(s["ignored_by_reason"])
    out = dict(tot)
    out["ignored_by_reason"] = dict(by_reason)
    out["not_in_source_share"] = (tot["not_in_source"] / tot["numeric_tokens"]) if tot["numeric_tokens"] else None
    return out


def pool_cells(cells: Sequence[dict[str, Any]]) -> dict[str, Any]:
    rows = [r for c in cells for r in c["facts"]]
    out_tok = sum(c["output_tokens"] for c in cells)
    return {
        "drafts": len(cells),
        "coverage": coverage_summary(rows, out_tok),
        "output_tokens": {"total": out_tok, "mean": (out_tok / len(cells)) if cells else None},
        "cost_per_1k_docs_usd": statistics.fmean(c["cost_per_1k_docs_usd"] for c in cells) if cells else None,
        "numbers": _pool_numbers(cells),
    }


def run_deterministic(replays: dict[str, Any], keys: dict[str, Any]) -> dict[str, Any]:
    presets = preset_map()
    cells = [score_draft(d, presets[d["preset_id"]]["payload"], facts_for(keys, d["preset_id"])) for d in iter_drafts(replays)]
    by = {(c["preset_id"], c["rung_id"]): c for c in cells}
    rungs = {}
    for rid in RUNG_IDS:
        rc = [c for c in cells if c["rung_id"] == rid]
        rungs[rid] = {**pool_cells(rc), "by_preset": {c["preset_id"]: pool_cells([c]) for c in rc}}
    per_fact = []
    for f in keys["facts"]:
        hits = {}
        for rid in RUNG_IDS:
            c = by.get((f["preset_id"], rid))
            row = next((r for r in c["facts"] if r["fact_id"] == f["id"]), None) if c else None
            hits[rid] = None if row is None else row["hit"]
        per_fact.append(
            {
                "fact_id": f["id"],
                "preset_id": f["preset_id"],
                "tier": f["tier"],
                "category": f["category"],
                "description": f["description"],
                "any_of": f["any_of"],
                "hits": hits,
                "covered_by_no_draft": all(v is False for v in hits.values()),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "keys_version": (keys.get("meta") or {}).get("keys_version"),
        "key_counts": key_counts(keys),
        "normalisation_rules": list(NORMALISATION_RULES),
        "number_rules": {"ignore": [{"rule": r, "description": d} for r, d in IGNORE_RULES],
                         "classification": list(CLASSIFICATION_RULES)},
        "rung_ids": list(RUNG_IDS),
        "preset_ids": list(PRESET_IDS),
        "drafts": cells,
        "rungs": rungs,
        "per_fact": per_fact,
        "facts_covered_by_no_draft": [p["fact_id"] for p in per_fact if p["covered_by_no_draft"]],
    }


# --------------------------------------------------------------------------------------------------
# D. Judge prompts and schemas
# --------------------------------------------------------------------------------------------------

LAYOUT_NEUTRAL_INSTRUCTION = (
    "The source may list required section names. Treat that as a content requirement (the draft must contain that content somewhere), not as a formatting requirement. "
    "Do not reward or penalise section titles, section order, layout, or whether the draft is prose, bullets or a table."
)

RUBRIC_SYSTEM_PROMPT = """You are an exacting senior reviewer of business and regulatory documents. You will receive a SOURCE BUNDLE, the deliverable it calls for and its intended reader, and one DRAFT written from that source.

The source bundle is the complete and only ground truth. Judge the draft against it alone: do not use outside knowledge to fill gaps or to correct the source. Read the whole draft before scoring. Score each dimension independently, and do not let the draft's length or format influence any dimension other than clarity and concision. The source may list required section names. Treat that as a content requirement (the draft must contain that content somewhere), not as a formatting requirement. Do not reward or penalise section titles, section order, layout, or whether the draft is prose, bullets or a table.

Score five dimensions, each with an integer from 1 to 5 and a one-sentence justification. Scores 2 and 4 lie between the anchors.

factual_accuracy — does everything the draft states agree with the source?
  5: Every figure, name, date, cause and commitment matches the source or is correct arithmetic on source figures; nothing is invented.
  3: Mostly faithful, with a few minor misstatements, loose roundings presented as exact, or small unsupported embellishments that would not change the reader's decision.
  1: Material errors or invented facts (wrong amounts, deadlines, owners, counts or obligations) that would mislead the reader.

coverage — does it carry what this reader needs to decide or act?
  5: Everything decision-critical in the source is present: headline metrics, the size of the exposure, the decisions or asks, hard deadlines, accountable owners and the key causes.
  3: Most decision-critical items are present, but one or two important ones are missing or only implied.
  1: Several decision-critical items are missing; the reader could not act on this draft.

clarity — structure and readability for this reader.
  5: Well organised for the reader; the main point comes first; easy to scan; terminology is consistent.
  3: Understandable, but the reader has to work to find key points; some structural or wording problems.
  1: Disorganised or confusing; key points are buried or contradict each other.

actionability — owners, deadlines and concrete next steps.
  5: Every next step has a named owner, a deadline or time window, and a concrete, checkable completion criterion, all consistent with the source.
  3: Next steps exist, but several lack an owner, a deadline or a concrete criterion.
  1: Few or no concrete next steps.

concision — no padding or repetition; length appropriate to the reader.
  5: No padding or repetition; the length suits the stated reader and purpose.
  3: Noticeable repetition, filler or unnecessary detail (it could be much shorter without loss), or so compressed that explanation the reader needs is missing.
  1: Heavily padded or repetitive, or a length plainly inappropriate for the reader.

factual_errors — list every statement in the draft that contradicts the source or is not supported by it. For each entry:
  - claim_quote: the exact words from the draft, copied verbatim. Quote, do not paraphrase. Use the shortest span that contains the problem.
  - problem: one sentence saying what is wrong.
  - source_quote_or_absent: the exact words from the source that the claim conflicts with, copied verbatim; or the single word ABSENT if nothing in the source supports the claim.
  - severity: "material" if it could change the reader's decision or misstates an amount, count, deadline, owner, obligation or regulatory fact; otherwise "minor".
Correct arithmetic derived from source figures (sums, differences, ratios, percentages, unit conversions, reasonable roundings) is NOT an error; check the arithmetic before reporting it. Interpretation or recommendation clearly framed as such is not an error unless it contradicts the source. Return an empty list if there are no errors.

unsupported_numbers_review — the user message lists numbers taken from the draft that do not appear verbatim in the source, each with an id and a context snippet. Return exactly one entry per listed id, with a verdict:
  - derived_correct: correctly computed or rounded from source figures; show the arithmetic.
  - derived_incorrect: an attempted derivation that is wrong; show the correct arithmetic.
  - not_in_source_unverifiable: cannot be derived from the source.
  - not_a_claim: not a factual claim (a label, a heading or list number, part of a name, a structural count of the draft itself).
Keep each reason short. If the list is empty, return an empty array.

Return only the JSON object required by the response schema."""

PAIRWISE_SYSTEM_PROMPT = """You are an exacting senior reviewer of business and regulatory documents. You will receive a SOURCE BUNDLE, the deliverable it calls for and its intended reader, and two drafts written from that source, labelled Draft A and Draft B.

Decide which draft should be sent to the stated reader as is, with no further editing. The source bundle is the complete and only ground truth: judge both drafts against it alone and do not use outside knowledge.

Weigh, in this order: factual accuracy against the source (an error that could mislead the reader outweighs any stylistic advantage); whether the draft gives this reader what they need to decide or act (metrics, size of exposure, decisions, deadlines, owners); then clarity, and length appropriate to the reader. Do not prefer a draft because it is longer, shorter or differently formatted except insofar as that serves the reader. The source may list required section names. Treat that as a content requirement (the draft must contain that content somewhere), not as a formatting requirement. Do not reward or penalise section titles, section order, layout, or whether the draft is prose, bullets or a table. The order in which the drafts are presented is arbitrary and carries no information. Answer "tie" only if neither draft is meaningfully better to send.

Return:
  - dimension_preferences.accuracy: which draft is more factually faithful to the source ("A", "B" or "tie").
  - dimension_preferences.usefulness_to_reader: which draft better serves the stated reader's need to decide or act ("A", "B" or "tie").
  - preferred: which draft should be sent as is ("A", "B" or "tie").
  - reason: one sentence explaining the overall preference.

Return only the JSON object required by the response schema."""

RUBRIC_USER_TEMPLATE = """<source_bundle>
{source}
</source_bundle>

<deliverable>
Deliverable the source calls for: {deliverable}
Intended reader: {reader}
</deliverable>

<draft>
{draft}
</draft>

<numbers_to_review>
{numbers}
</numbers_to_review>

Evaluate the draft as instructed and return the JSON object."""

PAIRWISE_USER_TEMPLATE = """<source_bundle>
{source}
</source_bundle>

<deliverable>
Deliverable the source calls for: {deliverable}
Intended reader: {reader}
</deliverable>

<draft_a>
{draft_a}
</draft_a>

<draft_b>
{draft_b}
</draft_b>

Which draft should be sent to the stated reader as is? Return the JSON object."""


def _score_obj() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
            "justification": {"type": "string"},
        },
        "required": ["score", "justification"],
        "additionalProperties": False,
    }


RUBRIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "factual_errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_quote": {"type": "string"},
                    "problem": {"type": "string"},
                    "source_quote_or_absent": {"type": "string"},
                    "severity": {"type": "string", "enum": ["minor", "material"]},
                },
                "required": ["claim_quote", "problem", "source_quote_or_absent", "severity"],
                "additionalProperties": False,
            },
        },
        "unsupported_numbers_review": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "verdict": {"type": "string", "enum": list(NUMBER_VERDICTS)},
                    "reason": {"type": "string"},
                },
                "required": ["id", "verdict", "reason"],
                "additionalProperties": False,
            },
        },
        "scores": {
            "type": "object",
            "properties": {d: _score_obj() for d in DIMENSIONS},
            "required": list(DIMENSIONS),
            "additionalProperties": False,
        },
    },
    "required": ["factual_errors", "unsupported_numbers_review", "scores"],
    "additionalProperties": False,
}

_AB = {"type": "string", "enum": ["A", "B", "tie"]}
PAIRWISE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "dimension_preferences": {
            "type": "object",
            "properties": {d: dict(_AB) for d in PAIR_DIMENSIONS},
            "required": list(PAIR_DIMENSIONS),
            "additionalProperties": False,
        },
        "preferred": dict(_AB),
        "reason": {"type": "string"},
    },
    "required": ["dimension_preferences", "preferred", "reason"],
    "additionalProperties": False,
}


def format_numbers_block(numbers: Sequence[dict[str, Any]]) -> str:
    if not numbers:
        return "(none)"
    return "\n".join(f'{n["id"]}: "{n["text"]}" — context: "{n["snippet"]}"' for n in numbers)


def build_rubric_prompt(preset_id: str, draft_text: str, numbers: Sequence[dict[str, Any]]) -> tuple[str, str]:
    p = preset_map()[preset_id]
    t = TARGETS[preset_id]
    user = RUBRIC_USER_TEMPLATE.format(
        source=p["payload"], deliverable=t["deliverable"], reader=t["reader"], draft=draft_text.strip(),
        numbers=format_numbers_block(numbers),
    )
    return RUBRIC_SYSTEM_PROMPT, user


def build_pairwise_prompt(preset_id: str, draft_a: str, draft_b: str) -> tuple[str, str]:
    p = preset_map()[preset_id]
    t = TARGETS[preset_id]
    user = PAIRWISE_USER_TEMPLATE.format(
        source=p["payload"], deliverable=t["deliverable"], reader=t["reader"], draft_a=draft_a.strip(), draft_b=draft_b.strip()
    )
    return PAIRWISE_SYSTEM_PROMPT, user


BLINDING_FORBIDDEN: tuple[str, ...] = (
    "claude", "sonnet", "haiku", "opus", "anthropic", "unbounded", "templated", "template", "rung", "token",
    "cost", "price", "pricing", "cheap", "expensive", "$/", "usd", "model",
    *RUNG_IDS,
)


def blinding_violations(prompt_text: str, embedded_texts: Sequence[str], forbidden_numbers: Sequence[str] = ()) -> list[str]:
    """Forbidden terms present in the prompt once the embedded source/draft texts are cut out.

    Source bundles and drafts are allowed to say anything (reg-01's source itself mentions a "Haiku" gate);
    the check is that nothing WE add reveals model, rung, token count or cost.
    """
    rest = prompt_text
    for t in sorted((t.strip() for t in embedded_texts if t and t.strip()), key=len, reverse=True):
        rest = rest.replace(t, "")
    low = rest.lower()
    hits = [w for w in BLINDING_FORBIDDEN if w.lower() in low]
    for n in forbidden_numbers:
        if n and re.search(rf"(?<![\d,]){re.escape(n)}(?![\d,])", prompt_text):
            hits.append(f"number:{n}")
    return hits


# --------------------------------------------------------------------------------------------------
# Call planning
# --------------------------------------------------------------------------------------------------


def rubric_call_id(preset_id: str, rung_id: str, repeat_index: int) -> str:
    return f"rubric:{preset_id}:{rung_id}:r{repeat_index}"


def pairwise_call_id(preset_id: str, first: str, second: str, order: str) -> str:
    return f"pairwise:{preset_id}:{first}__{second}:{order}"


def rung_pairs() -> list[tuple[str, str]]:
    return list(itertools.combinations(RUNG_IDS, 2))


def _sha(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def plan_judge_calls(
    deterministic: dict[str, Any], *, repeats: int = RUBRIC_REPEATS, tasks: Sequence[str] = ("rubric", "pairwise")
) -> list[dict[str, Any]]:
    """Deterministic call list. Rubric: repeat-major (balanced if stopped early); pairwise: both orders per pair."""
    cells = {(c["preset_id"], c["rung_id"]): c for c in deterministic["drafts"]}
    plan: list[dict[str, Any]] = []
    if "rubric" in tasks:
        for r in range(repeats):
            for pid in PRESET_IDS:
                for rid in RUNG_IDS:
                    c = cells.get((pid, rid))
                    if c is None:
                        continue
                    numbers = list(c["not_in_source"])
                    system, user = build_rubric_prompt(pid, c["text"], numbers)
                    plan.append(
                        {
                            "call_id": rubric_call_id(pid, rid, r),
                            "task": "rubric",
                            "preset_id": pid,
                            "rung_id": rid,
                            "repeat_index": r,
                            "system": system,
                            "user": user,
                            "schema": RUBRIC_SCHEMA,
                            "numbers": numbers,
                            "draft_sha256": c["text_sha256"],
                            "prompt_sha256": _sha(system, user),
                        }
                    )
    if "pairwise" in tasks:
        for pid in PRESET_IDS:
            for x, y in rung_pairs():
                if (pid, x) not in cells or (pid, y) not in cells:
                    continue
                for order, (a, b) in (("fwd", (x, y)), ("rev", (y, x))):
                    system, user = build_pairwise_prompt(pid, cells[(pid, a)]["text"], cells[(pid, b)]["text"])
                    plan.append(
                        {
                            "call_id": pairwise_call_id(pid, x, y, order),
                            "task": "pairwise",
                            "preset_id": pid,
                            "pair": [x, y],
                            "order": order,
                            "a_rung": a,
                            "b_rung": b,
                            "system": system,
                            "user": user,
                            "schema": PAIRWISE_SCHEMA,
                            "prompt_sha256": _sha(system, user),
                        }
                    )
    return plan


def select_pending(planned: Iterable[dict[str, Any]], existing: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Planned calls without an `ok` record (error records stay in the file and their call is retried)."""
    done = {r["call_id"] for r in existing if r.get("status") == "ok"}
    return [p for p in planned if p["call_id"] not in done]


def stale_ok_records(planned: Iterable[dict[str, Any]], existing: Iterable[dict[str, Any]]) -> list[str]:
    """call_ids whose latest ok record was made from a different prompt than the current plan's."""
    cur = {p["call_id"]: p["prompt_sha256"] for p in planned}
    latest: dict[str, dict[str, Any]] = {}
    for r in existing:
        if r.get("status") == "ok":
            latest[r["call_id"]] = r
    return sorted(cid for cid, r in latest.items() if cid in cur and r.get("prompt_sha256") != cur[cid])


# --------------------------------------------------------------------------------------------------
# Cost, estimate, budget guard
# --------------------------------------------------------------------------------------------------


def judge_cost_usd(input_tokens: int, output_tokens: int, cache_creation_tokens: int = 0, cache_read_tokens: int = 0) -> float:
    return (
        input_tokens * OPUS_INPUT_PER_1M_USD
        + output_tokens * OPUS_OUTPUT_PER_1M_USD
        + cache_creation_tokens * OPUS_CACHE_WRITE_PER_1M_USD
        + cache_read_tokens * OPUS_CACHE_READ_PER_1M_USD
    ) / 1_000_000


def record_cost_usd(record: dict[str, Any]) -> float:
    return judge_cost_usd(
        int(record.get("input_tokens") or 0),
        int(record.get("output_tokens") or 0),
        int(record.get("cache_creation_tokens") or 0),
        int(record.get("cache_read_tokens") or 0),
    )


def calibrate_chars_per_token(replays: dict[str, Any]) -> float:
    """chars / input_tokens over the stored unbounded rung (system prompt + payload, no output schema)."""
    from app.archetypes.cat2_drafting.prompts import get_unbounded_draft_system_prompt

    presets = preset_map()
    ratios = []
    for pid, pdata in (replays.get("presets") or {}).items():
        r = (pdata.get("rungs") or {}).get("sonnet_unbounded")
        if not r or pid not in presets or not r.get("input_tokens"):
            continue
        chars = len(get_unbounded_draft_system_prompt(presets[pid]["sub_task"])) + len(presets[pid]["payload"])
        ratios.append(chars / int(r["input_tokens"]))
    return statistics.fmean(ratios) if ratios else DEFAULT_CHARS_PER_TOKEN


def estimate_input_tokens(planned: dict[str, Any], chars_per_token: float = DEFAULT_CHARS_PER_TOKEN) -> int:
    chars = len(planned["system"]) + len(planned["user"]) + len(json.dumps(planned["schema"]))
    return int(math.ceil(chars / chars_per_token))


def estimate_plan(
    plan: Sequence[dict[str, Any]], *, chars_per_token: float = DEFAULT_CHARS_PER_TOKEN, max_tokens: int = JUDGE_MAX_TOKENS,
    typical_output_tokens: dict[str, int] | None = None,
) -> dict[str, Any]:
    typical = typical_output_tokens or {"rubric": 2500, "pairwise": 1200}
    by_task: dict[str, dict[str, Any]] = {}
    for p in plan:
        s = by_task.setdefault(p["task"], {"calls": 0, "input_tokens": 0})
        s["calls"] += 1
        s["input_tokens"] += estimate_input_tokens(p, chars_per_token)
    for task, s in by_task.items():
        s["typical_output_tokens"] = s["calls"] * typical.get(task, max_tokens)
        s["worst_case_output_tokens"] = s["calls"] * max_tokens
        s["typical_usd"] = judge_cost_usd(s["input_tokens"], s["typical_output_tokens"])
        s["worst_case_usd"] = judge_cost_usd(s["input_tokens"], s["worst_case_output_tokens"])
    tot = {k: sum(s[k] for s in by_task.values()) for k in ("calls", "input_tokens", "typical_output_tokens",
                                                             "worst_case_output_tokens", "typical_usd", "worst_case_usd")}
    return {"chars_per_token": chars_per_token, "max_tokens": max_tokens, "by_task": by_task, "total": tot}


class BudgetGuard:
    """Billed judge spend (ok AND error records) vs `max_usd`; refuse a call whose worst case would cross the cap."""

    def __init__(self, max_usd: float, existing: Iterable[dict[str, Any]] = ()) -> None:
        self.max_usd = float(max_usd)
        self.spent_usd = sum(record_cost_usd(r) for r in existing)
        self.reserved_usd = 0.0

    def try_reserve(self, worst_case_usd: float) -> bool:
        if self.spent_usd + self.reserved_usd + worst_case_usd > self.max_usd:
            return False
        self.reserved_usd += worst_case_usd
        return True

    def settle(self, reserved_usd: float, record: dict[str, Any]) -> float:
        cost = record_cost_usd(record)
        self.reserved_usd = max(0.0, self.reserved_usd - reserved_usd)
        self.spent_usd += cost
        return cost


# --------------------------------------------------------------------------------------------------
# Judge execution (injectable)
# --------------------------------------------------------------------------------------------------


@dataclass
class JudgeResponse:
    model_id: str
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    thinking_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    latency_ms: int
    raw_text: str
    request_id: str | None = None


JudgeCall = Callable[..., Awaitable[JudgeResponse]]


def make_anthropic_judge_call(
    api_key: str, *, timeout_s: float = JUDGE_TIMEOUT_S, model: str = JUDGE_MODEL, effort: str | None = JUDGE_EFFORT
) -> JudgeCall:
    """Real judge call: one AsyncAnthropic client, explicit timeout, max_retries=0 (nothing silently re-billed)."""
    import anthropic

    from app.core.anthropic_service import _extract_usage_tokens

    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_s, max_retries=0)

    async def call(*, system: str, user: str, schema: dict[str, Any], max_tokens: int) -> JudgeResponse:
        output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": schema}}
        if effort:
            output_config["effort"] = effort
        t0 = time.perf_counter()
        resp = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            thinking=dict(JUDGE_THINKING),
            output_config=output_config,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        in_tok, out_tok, c_write, c_read, think_tok = _extract_usage_tokens(resp.usage)
        raw = "\n".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        return JudgeResponse(
            model_id=str(getattr(resp, "model", model)),
            stop_reason=getattr(resp, "stop_reason", None),
            input_tokens=in_tok,
            output_tokens=out_tok,
            thinking_tokens=think_tok,
            cache_creation_tokens=c_write,
            cache_read_tokens=c_read,
            latency_ms=latency_ms,
            raw_text=raw,
            request_id=getattr(resp, "_request_id", None),
        )

    return call


class JudgeOutputError(ValueError):
    def __init__(self, error_type: str, message: str) -> None:
        super().__init__(message)
        self.error_type = error_type


def parse_judge_output(task: str, raw_text: str, numbers: Sequence[dict[str, Any]] = ()) -> dict[str, Any]:
    """json.loads + JSON-schema validation + (rubric) one review entry per passed number id. Raises JudgeOutputError."""
    import jsonschema

    try:
        obj = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise JudgeOutputError("invalid_json", f"{exc}") from exc
    schema = RUBRIC_SCHEMA if task == "rubric" else PAIRWISE_SCHEMA
    try:
        jsonschema.validate(obj, schema)
    except jsonschema.ValidationError as exc:
        raise JudgeOutputError("schema_violation", exc.message[:500]) from exc
    if task == "rubric":
        got = [e["id"] for e in obj["unsupported_numbers_review"]]
        want = [n["id"] for n in numbers]
        if len(got) != len(set(got)) or set(got) != set(want):
            missing = sorted(set(want) - set(got))
            extra = sorted(set(got) - set(want))
            dup = sorted(k for k, v in Counter(got).items() if v > 1)
            raise JudgeOutputError(
                "schema_violation", f"unsupported_numbers_review ids mismatch: missing={missing} extra={extra} dup={dup}"
            )
    return obj


def _base_record(planned: dict[str, Any], max_tokens: int) -> dict[str, Any]:
    rec = {
        "schema_version": SCHEMA_VERSION,
        "call_id": planned["call_id"],
        "task": planned["task"],
        "preset_id": planned["preset_id"],
        "status": "error",
        "error_type": None,
        "error_message": None,
        "judge_model_requested": JUDGE_MODEL,
        "settings": {
            "max_tokens": max_tokens,
            "thinking": dict(JUDGE_THINKING),
            "effort": JUDGE_EFFORT,
            "timeout_s": JUDGE_TIMEOUT_S,
            "max_retries": 0,
        },
        "prompt_sha256": planned["prompt_sha256"],
        "model_id": None,
        "stop_reason": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "thinking_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "latency_ms": None,
        "request_id": None,
        "raw_text": None,
        "parsed": None,
    }
    if planned["task"] == "rubric":
        rec.update(
            {
                "rung_id": planned["rung_id"],
                "repeat_index": planned["repeat_index"],
                "draft_sha256": planned.get("draft_sha256"),
                "numbers_reviewed": list(planned["numbers"]),
            }
        )
    else:
        rec.update({k: planned[k] for k in ("pair", "order", "a_rung", "b_rung")})
    return rec


async def execute_judge_call(planned: dict[str, Any], *, judge_call: JudgeCall, max_tokens: int = JUDGE_MAX_TOKENS) -> dict[str, Any]:
    """One judge call -> one record. Never raises; failures are `status: error` records with whatever was billed."""
    rec = _base_record(planned, max_tokens)
    rec["started_at"] = _utc_now_iso()
    try:
        resp = await judge_call(system=planned["system"], user=planned["user"], schema=planned["schema"], max_tokens=max_tokens)
    except Exception as exc:  # noqa: BLE001 — recorded, never raised
        rec["error_type"] = "api_error"
        rec["error_message"] = f"{type(exc).__name__}: {exc}"[:2000]
        rec["finished_at"] = _utc_now_iso()
        return rec
    rec.update(
        {
            "model_id": resp.model_id,
            "stop_reason": resp.stop_reason,
            "input_tokens": int(resp.input_tokens),
            "output_tokens": int(resp.output_tokens),
            "thinking_tokens": int(resp.thinking_tokens or 0),
            "cache_creation_tokens": int(resp.cache_creation_tokens or 0),
            "cache_read_tokens": int(resp.cache_read_tokens or 0),
            "latency_ms": int(resp.latency_ms),
            "request_id": resp.request_id,
            "raw_text": resp.raw_text,
        }
    )
    try:
        if resp.stop_reason != "end_turn":
            raise JudgeOutputError("stop_reason", f"stop_reason={resp.stop_reason}")
        rec["parsed"] = parse_judge_output(planned["task"], resp.raw_text, planned.get("numbers") or ())
        rec["status"] = "ok"
    except JudgeOutputError as exc:
        rec["error_type"] = exc.error_type
        rec["error_message"] = str(exc)[:2000]
    rec["finished_at"] = _utc_now_iso()
    return rec


async def run_judge_plan(
    pending: Sequence[dict[str, Any]],
    *,
    judge_call: JudgeCall,
    guard: BudgetGuard,
    on_record: Callable[[dict[str, Any]], None],
    concurrency: int = 4,
    max_tokens: int = JUDGE_MAX_TOKENS,
    chars_per_token: float = DEFAULT_CHARS_PER_TOKEN,
) -> dict[str, Any]:
    """Launch pending calls with a concurrency cap; stop launching once the next call's worst case could exceed the cap."""
    sem = asyncio.Semaphore(max(1, concurrency))
    tasks: list[asyncio.Task[None]] = []
    counts = {"ok": 0, "error": 0, "launched": 0, "skipped_budget": 0}
    budget_stopped = False

    async def one(p: dict[str, Any], reserved: float) -> None:
        try:
            rec = await execute_judge_call(p, judge_call=judge_call, max_tokens=max_tokens)
            guard.settle(reserved, rec)
            counts["ok" if rec["status"] == "ok" else "error"] += 1
            on_record(rec)
        finally:
            sem.release()

    for i, p in enumerate(pending):
        await sem.acquire()
        worst = judge_cost_usd(estimate_input_tokens(p, chars_per_token), max_tokens)
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


def load_judgements(path: Path | str | None = None) -> list[dict[str, Any]]:
    p = Path(path or JUDGEMENTS_PATH)
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


# --------------------------------------------------------------------------------------------------
# Aggregation (pure)
# --------------------------------------------------------------------------------------------------


def latest_ok(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in records:
        if r.get("status") == "ok":
            out[r["call_id"]] = r  # file order: later wins
    return out


def _dist(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "min": None, "max": None}
    return {"n": len(values), "mean": statistics.fmean(values), "min": min(values), "max": max(values)}


def majority(values: Sequence[str]) -> str | None:
    """Most common value when it holds a strict majority of the votes, else None."""
    if not values:
        return None
    (top, n), *rest = Counter(values).most_common()
    return top if n * 2 > len(values) else None


def aggregate_rubric(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rub = [r for r in latest_ok(records).values() if r["task"] == "rubric"]
    cells: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rub:
        cells.setdefault((r["preset_id"], r["rung_id"]), []).append(r)
    per_draft: dict[str, Any] = {}
    for (pid, rid), rs in sorted(cells.items()):
        rs = sorted(rs, key=lambda r: r["repeat_index"])
        dims = {}
        for d in DIMENSIONS:
            scores = [int(r["parsed"]["scores"][d]["score"]) for r in rs]
            dims[d] = {**_dist(scores), "scores": scores, "within_1": (max(scores) - min(scores) <= 1) if len(scores) >= 2 else None}
        per_draft[f"{pid}|{rid}"] = {"preset_id": pid, "rung_id": rid, "repeats": [r["repeat_index"] for r in rs], "dimensions": dims}

    def pooled(rid: str, pid: str | None = None) -> dict[str, Any]:
        sel = [v for v in per_draft.values() if v["rung_id"] == rid and (pid is None or v["preset_id"] == pid)]
        out = {}
        for d in DIMENSIONS:
            vals = [s for v in sel for s in v["dimensions"][d]["scores"]]
            out[d] = _dist(vals)
        full = [v["dimensions"][d] for v in sel for d in DIMENSIONS if len(v["dimensions"][d]["scores"]) == RUBRIC_REPEATS]
        out["agreement_within_1"] = {
            "cells": len(full),
            "within_1": sum(1 for c in full if c["within_1"]),
            "share": (sum(1 for c in full if c["within_1"]) / len(full)) if full else None,
        }
        return out

    all_full = [v["dimensions"][d] for v in per_draft.values() for d in DIMENSIONS if len(v["dimensions"][d]["scores"]) == RUBRIC_REPEATS]
    return {
        "per_draft": per_draft,
        "rungs": {rid: {**pooled(rid), "by_preset": {pid: pooled(rid, pid) for pid in PRESET_IDS}} for rid in RUNG_IDS},
        "agreement_within_1_overall": {
            "cells": len(all_full),
            "within_1": sum(1 for c in all_full if c["within_1"]),
            "share": (sum(1 for c in all_full if c["within_1"]) / len(all_full)) if all_full else None,
        },
    }


def _quote_similar(a: str, b: str, threshold: float) -> bool:
    na, nb = normalise_text(a), normalise_text(b)
    if not na or not nb:
        return False
    if (len(na) >= 12 and na in nb) or (len(nb) >= 12 and nb in na):
        return True
    return SequenceMatcher(None, na, nb).ratio() >= threshold


def dedupe_errors(reports: Sequence[dict[str, Any]], *, threshold: float = 0.6) -> list[dict[str, Any]]:
    """Greedy clustering of factual-error reports (each with `repeat_index`) by claim_quote similarity."""
    clusters: list[dict[str, Any]] = []
    for e in reports:
        for c in clusters:
            if any(_quote_similar(e["claim_quote"], q, threshold) for q in c["claim_quotes"]):
                break
        else:
            c = {"claim_quotes": [], "problems": [], "source_quotes": [], "severities": [], "repeats": []}
            clusters.append(c)
        c["claim_quotes"].append(e["claim_quote"])
        c["problems"].append(e["problem"])
        c["source_quotes"].append(e["source_quote_or_absent"])
        c["severities"].append(e["severity"])
        c["repeats"].append(e["repeat_index"])
    out = []
    for c in clusters:
        mat = sum(1 for s in c["severities"] if s == "material")
        out.append(
            {
                "claim_quote": c["claim_quotes"][0],
                "claim_quotes": c["claim_quotes"],
                "problem": c["problems"][0],
                "problems": c["problems"],
                "source_quote_or_absent": c["source_quotes"][0],
                "source_quotes": c["source_quotes"],
                "reports": len(c["severities"]),
                "repeats_reporting": len(set(c["repeats"])),
                "material_votes": mat,
                # Majority of the reports; a tie counts as material (conservative for review).
                "severity": "material" if mat * 2 >= len(c["severities"]) else "minor",
            }
        )
    return out


def aggregate_errors(records: Iterable[dict[str, Any]], drafts_text: dict[tuple[str, str], str] | None = None) -> dict[str, Any]:
    rub = [r for r in latest_ok(records).values() if r["task"] == "rubric"]
    by: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rub:
        by.setdefault((r["preset_id"], r["rung_id"]), [])
        for e in r["parsed"]["factual_errors"]:
            by[(r["preset_id"], r["rung_id"])].append({**e, "repeat_index": r["repeat_index"]})
    presets = preset_map()
    per_draft = {}
    for (pid, rid), reps in sorted(by.items()):
        clusters = dedupe_errors(reps)
        text_norm = normalise_text((drafts_text or {}).get((pid, rid), ""))
        src_norm = normalise_text(presets[pid]["payload"]) if pid in presets else ""
        for c in clusters:
            c["claim_quote_found_in_draft"] = (normalise_text(c["claim_quote"]) in text_norm) if drafts_text else None
            sq = c["source_quote_or_absent"].strip()
            c["source_quote_found_in_source"] = None if sq.upper() == "ABSENT" else (normalise_text(sq) in src_norm)
        n_rep = len({r["repeat_index"] for r in rub if r["preset_id"] == pid and r["rung_id"] == rid})
        per_draft[f"{pid}|{rid}"] = {
            "preset_id": pid,
            "rung_id": rid,
            "rubric_repeats": n_rep,
            "distinct_errors": len(clusters),
            "material": sum(1 for c in clusters if c["severity"] == "material"),
            "minor": sum(1 for c in clusters if c["severity"] == "minor"),
            "raw_reports": len(reps),
            "errors": clusters,
        }
    rungs = {}
    for rid in RUNG_IDS:
        sel = [v for v in per_draft.values() if v["rung_id"] == rid]
        rungs[rid] = {k: sum(v[k] for v in sel) for k in ("distinct_errors", "material", "minor", "raw_reports")}
        rungs[rid]["drafts"] = len(sel)
    return {"per_draft": per_draft, "rungs": rungs}


def aggregate_number_reviews(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rub = [r for r in latest_ok(records).values() if r["task"] == "rubric"]
    by: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for r in rub:
        slot = by.setdefault((r["preset_id"], r["rung_id"]), {})
        meta = {n["id"]: n for n in r.get("numbers_reviewed") or []}
        for e in r["parsed"]["unsupported_numbers_review"]:
            row = slot.setdefault(
                e["id"], {"id": e["id"], "text": meta.get(e["id"], {}).get("text"), "snippet": meta.get(e["id"], {}).get("snippet"),
                          "verdicts": [], "reasons": [], "repeats": []}
            )
            row["verdicts"].append(e["verdict"])
            row["reasons"].append(e["reason"])
            row["repeats"].append(r["repeat_index"])
    per_draft = {}
    for (pid, rid), rows in sorted(by.items()):
        items = []
        for nid in sorted(rows):
            row = rows[nid]
            maj = majority(row["verdicts"])
            items.append({**row, "majority": maj or "no_majority", "unanimous": len(set(row["verdicts"])) == 1})
        counts = Counter(i["majority"] for i in items)
        per_draft[f"{pid}|{rid}"] = {
            "preset_id": pid,
            "rung_id": rid,
            "reviewed": len(items),
            "majority_counts": {v: counts.get(v, 0) for v in (*NUMBER_VERDICTS, "no_majority")},
            "disagreements": sum(1 for i in items if not i["unanimous"]),
            "items": items,
        }
    rungs = {}
    for rid in RUNG_IDS:
        sel = [v for v in per_draft.values() if v["rung_id"] == rid]
        c = Counter()
        for v in sel:
            c.update(v["majority_counts"])
        rungs[rid] = {
            "reviewed": sum(v["reviewed"] for v in sel),
            "majority_counts": {v: c.get(v, 0) for v in (*NUMBER_VERDICTS, "no_majority")},
            "disagreements": sum(v["disagreements"] for v in sel),
        }
    return {"per_draft": per_draft, "rungs": rungs}


def _winner(rec: dict[str, Any], choice: str) -> str | None:
    return rec["a_rung"] if choice == "A" else rec["b_rung"] if choice == "B" else None


def aggregate_pairwise(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    pw = [r for r in latest_ok(records).values() if r["task"] == "pairwise"]
    keys = ("overall", *PAIR_DIMENSIONS)

    def choice(r: dict[str, Any], key: str) -> str:
        return r["parsed"]["preferred"] if key == "overall" else r["parsed"]["dimension_preferences"][key]

    out: dict[str, Any] = {"calls": len(pw)}
    for key in keys:
        wins = {x: {y: 0 for y in RUNG_IDS if y != x} for x in RUNG_IDS}
        ties = {f"{x}|{y}": 0 for x, y in rung_pairs()}
        a_pos = 0
        decisive = 0
        for r in pw:
            c = choice(r, key)
            w = _winner(r, c)
            x, y = r["pair"]
            if w is None:
                ties[f"{x}|{y}"] += 1
            else:
                decisive += 1
                a_pos += c == "A"
                wins[w][y if w == x else x] += 1
        # Position consistency: per (bundle, pair) with both orders recorded, do both pick the same rung (or both tie)?
        pairs: dict[tuple[str, str, str], dict[str, str | None]] = {}
        for r in pw:
            x, y = r["pair"]
            pairs.setdefault((r["preset_id"], x, y), {})[r["order"]] = _winner(r, choice(r, key)) or "tie"
        both = {k: v for k, v in pairs.items() if "fwd" in v and "rev" in v}
        consistent = [k for k, v in both.items() if v["fwd"] == v["rev"]]
        out[key] = {
            "wins": wins,
            "ties": ties,
            "position_consistency": {
                "pairs_with_both_orders": len(both),
                "consistent": len(consistent),
                "share": (len(consistent) / len(both)) if both else None,
                "inconsistent": [{"preset_id": k[0], "pair": [k[1], k[2]], **v} for k, v in sorted(both.items()) if v["fwd"] != v["rev"]],
            },
            "decisive_calls": decisive,
            "share_decisive_choosing_position_a": (a_pos / decisive) if decisive else None,
            "by_preset": {
                pid: {f"{x}|{y}": pairs.get((pid, x, y), {}) for x, y in rung_pairs()} for pid in PRESET_IDS
            },
        }
    return out


def judge_data_quality(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    records = list(records)
    ok = latest_ok(records)
    errors = [r for r in records if r.get("status") != "ok"]
    return {
        "records": len(records),
        "ok_calls": len(ok),
        "error_records": len(errors),
        "errors_by_type": dict(Counter(r.get("error_type") for r in errors)),
        "errors": [
            {"call_id": r["call_id"], "error_type": r.get("error_type"), "error_message": (r.get("error_message") or "")[:300],
             "stop_reason": r.get("stop_reason"), "output_tokens": r.get("output_tokens")}
            for r in errors
        ],
        "model_ids_returned": dict(Counter(r.get("model_id") for r in ok.values())),
        "stop_reasons_ok": dict(Counter(r.get("stop_reason") for r in ok.values())),
        "billed_usd_all_records": sum(record_cost_usd(r) for r in records),
        "billed_usd_error_records": sum(record_cost_usd(r) for r in errors),
        "tokens": {
            "input": sum(int(r.get("input_tokens") or 0) for r in records),
            "output": sum(int(r.get("output_tokens") or 0) for r in records),
            "thinking": sum(int(r.get("thinking_tokens") or 0) for r in records),
        },
        "latency_ms": _dist([float(r["latency_ms"]) for r in ok.values() if r.get("latency_ms") is not None]),
    }


def summarise(deterministic: dict[str, Any], judgements: Sequence[dict[str, Any]] | None) -> dict[str, Any]:
    out: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "generated_at": _utc_now_iso(), "deterministic": deterministic}
    if judgements:
        texts = {(c["preset_id"], c["rung_id"]): c["text"] for c in deterministic["drafts"]}
        out["judge"] = {
            "model_requested": JUDGE_MODEL,
            "rates_assumed": {"input_per_1m_usd": OPUS_INPUT_PER_1M_USD, "output_per_1m_usd": OPUS_OUTPUT_PER_1M_USD},
            "data_quality": judge_data_quality(judgements),
            "rubric": aggregate_rubric(judgements),
            "errors": aggregate_errors(judgements, texts),
            "numbers": aggregate_number_reviews(judgements),
            "pairwise": aggregate_pairwise(judgements),
        }
    else:
        out["judge"] = None
    return out


# --------------------------------------------------------------------------------------------------
# Compact app summary (replays/cat2_quality_summary.json)
# --------------------------------------------------------------------------------------------------

APP_SUMMARY_SCHEMA_VERSION = 1
LIVE_JUDGE_REASON = "Blind grading is not run in live mode; it adds paid calls."


def _ab_norm(s: str | None) -> str:
    return normalise_text(s).strip(" *")


def action_item_flags(structured_draft: dict[str, Any] | None, errors: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """Templated action items whose owner or time window the judge reported as an error.

    An error belongs to an action item's owner/time-window fields when one of its claim quotes (normalised) lies
    inside the rendered "owner — time window" heading, or contains the item's owner or time window (>= 8 chars).
    Returns None for drafts without an action plan.
    """
    items = (structured_draft or {}).get("action_plan") if isinstance(structured_draft, dict) else None
    if not items:
        return None
    flagged, serious = 0, 0
    rows = []
    for a in items:
        owner, window = _ab_norm(a.get("owner")), _ab_norm(a.get("target_window"))
        head = f"{owner} - {window}"
        hits = []
        for e in errors:
            quotes = [_ab_norm(q) for q in (e.get("claim_quotes") or [e.get("claim_quote")])]
            if any(q and (q in head or (len(owner) >= 8 and owner in q) or (len(window) >= 8 and window in q)) for q in quotes):
                hits.append(e)
        is_serious = any(e.get("severity") == "material" for e in hits)
        flagged += bool(hits)
        serious += is_serious
        rows.append({"owner": a.get("owner"), "time_window": a.get("target_window"), "flagged": bool(hits), "serious": is_serious})
    return {"total": len(items), "flagged": flagged, "flagged_serious": serious, "items": rows}


def _count(p: dict[str, Any]) -> dict[str, int]:
    return {"hits": int(p["hits"]), "total": int(p["total"])}


def _verdict_counts(counts: dict[str, int] | None) -> dict[str, int]:
    return {v: int((counts or {}).get(v, 0)) for v in (*NUMBER_VERDICTS, "no_majority")}


def build_app_summary(
    deterministic: dict[str, Any],
    judgements: Sequence[dict[str, Any]],
    replays: dict[str, Any],
    *,
    source_files: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Timestamp-free per-draft and pooled quality picture for the app, built from `summarise()`."""
    keys = load_quality_keys()
    fact_desc = {f["id"]: f for f in keys["facts"]}
    s = summarise(deterministic, judgements)
    j = s["judge"]
    if j is None:
        raise ValueError("No judge records: the app summary needs the blind-judge results.")
    rub, errs, nums, pw = j["rubric"], j["errors"], j["numbers"], j["pairwise"]
    cells_det = {(c["preset_id"], c["rung_id"]): c for c in deterministic["drafts"]}
    overall = pw["overall"]

    presets: dict[str, Any] = {}
    action_pool: dict[str, list[dict[str, Any]]] = {r: [] for r in RUNG_IDS}
    for pid in PRESET_IDS:
        rungs_out: dict[str, Any] = {}
        h2h_doc = []
        by_pair = overall["by_preset"].get(pid, {})
        for x, y in rung_pairs():
            orders = by_pair.get(f"{x}|{y}", {})
            h2h_doc.append(
                {
                    "pair": [x, y],
                    "orders": [
                        {"shown_first": x, "winner": orders.get("fwd")},
                        {"shown_first": y, "winner": orders.get("rev")},
                    ],
                }
            )
        for rid in RUNG_IDS:
            c = cells_det.get((pid, rid))
            if c is None:
                continue
            key = f"{pid}|{rid}"
            rd = rub["per_draft"].get(key)
            ed = errs["per_draft"].get(key, {"errors": [], "material": 0, "minor": 0})
            nd = nums["per_draft"].get(key)
            verdict_by_id = {i["id"]: i["majority"] for i in (nd or {}).get("items", [])}
            errors = sorted(
                ed["errors"], key=lambda e: (e["severity"] != "material", -e["repeats_reporting"], e["claim_quote"])
            )
            sd = ((replays.get("presets") or {}).get(pid, {}).get("rungs", {}).get(rid, {}) or {}).get("structured_draft")
            ai = action_item_flags(sd, ed["errors"]) if rid != "sonnet_unbounded" else None
            if ai:
                action_pool[rid].append(ai)
            cov = c["coverage"]
            rungs_out[rid] = {
                "rung_id": rid,
                "text_sha256": c["text_sha256"],
                "output_tokens": c["output_tokens"],
                "cost_per_1k_docs_usd": c["cost_per_1k_docs_usd"],
                "core_facts": _count(cov["core"]),
                "detail_facts": _count(cov["detail"]),
                "missed_facts": [
                    {"description": fact_desc[r["fact_id"]]["description"], "tier": r["tier"]} for r in c["facts"] if not r["hit"]
                ],
                "numbers": {
                    "numeric_tokens": c["numbers_summary"]["numeric_tokens"],
                    "not_in_source": c["numbers_summary"]["not_in_source"],
                    "verdicts": _verdict_counts((nd or {}).get("majority_counts")),
                    "items": [
                        {"text": n["text"], "context": n["snippet"], "verdict": verdict_by_id.get(n["id"])}
                        for n in c["not_in_source"]
                    ],
                },
                "rubric": (
                    {d: {"mean": rd["dimensions"][d]["mean"], "scores": rd["dimensions"][d]["scores"]} for d in DIMENSIONS}
                    if rd
                    else None
                ),
                "serious_errors": ed["material"],
                "minor_errors": ed["minor"],
                "errors": [
                    {
                        "claim_quote": e["claim_quote"],
                        "problem": e["problem"],
                        "source_quote": None if e["source_quote_or_absent"].strip().upper() == "ABSENT" else e["source_quote_or_absent"],
                        "severity": e["severity"],
                        "passes_reporting": e["repeats_reporting"],
                    }
                    for e in errors
                ],
                "action_items": ({k: ai[k] for k in ("total", "flagged", "flagged_serious")} if ai else None),
                "head_to_head": [
                    {
                        "opponent": y if x == rid else x,
                        "results": [o for o in h["orders"]],
                    }
                    for h in h2h_doc
                    for x, y in [h["pair"]]
                    if rid in (x, y)
                ],
            }
        presets[pid] = {"rungs": rungs_out, "head_to_head": h2h_doc}

    rungs_pooled = []
    for rid in RUNG_IDS:
        d = deterministic["rungs"][rid]
        r_rub = rub["rungs"][rid]
        h2h = {}
        for opp in RUNG_IDS:
            if opp == rid:
                continue
            pair_key = f"{rid}|{opp}" if f"{rid}|{opp}" in overall["ties"] else f"{opp}|{rid}"
            h2h[opp] = {"wins": overall["wins"][rid][opp], "losses": overall["wins"][opp][rid], "ties": overall["ties"][pair_key]}
        ai = action_pool[rid]
        rungs_pooled.append(
            {
                "rung_id": rid,
                "drafts": d["drafts"],
                "core_facts": _count(d["coverage"]["core"]),
                "detail_facts": _count(d["coverage"]["detail"]),
                "rubric": {dim: {k: r_rub[dim][k] for k in ("mean", "min", "max", "n")} for dim in DIMENSIONS},
                "serious_errors": errs["rungs"][rid]["material"],
                "minor_errors": errs["rungs"][rid]["minor"],
                "numbers": {
                    "numeric_tokens": d["numbers"]["numeric_tokens"],
                    "not_in_source": d["numbers"]["not_in_source"],
                    "verdicts": _verdict_counts(nums["rungs"][rid]["majority_counts"]),
                },
                "action_items": (
                    {k: sum(a[k] for a in ai) for k in ("total", "flagged", "flagged_serious")} if ai else None
                ),
                "cost_per_1k_docs_usd": d["cost_per_1k_docs_usd"],
                "output_tokens_mean": d["output_tokens"]["mean"],
                "head_to_head": h2h,
            }
        )

    def pw_block(key: str) -> dict[str, Any]:
        x = pw[key]
        return {
            "wins": x["wins"],
            "ties": x["ties"],
            "position_consistency": {
                "pairs": x["position_consistency"]["pairs_with_both_orders"],
                "consistent": x["position_consistency"]["consistent"],
            },
        }

    dq = j["data_quality"]
    ok = latest_ok(judgements)
    return {
        "schema_version": APP_SUMMARY_SCHEMA_VERSION,
        "source": "cat2 blind-judge quality scoring",
        "source_files": dict(source_files or {}),
        "keys_version": deterministic.get("keys_version"),
        "judge_model": JUDGE_MODEL,
        "judge_models_returned": sorted(m for m in dq["model_ids_returned"] if m),
        "passes_per_draft": RUBRIC_REPEATS,
        "drafts_per_cell": 1,
        "documents": list(PRESET_IDS),
        "calls": {
            "rubric_ok": sum(1 for r in ok.values() if r["task"] == "rubric"),
            "pairwise_ok": sum(1 for r in ok.values() if r["task"] == "pairwise"),
            "error_records": dq["error_records"],
        },
        "dimensions": list(DIMENSIONS),
        "rungs": rungs_pooled,
        "pairwise": {k: pw_block(k) for k in ("overall", *PAIR_DIMENSIONS)},
        "presets": presets,
    }


def deterministic_quality_for_text(
    text: str, payload: str, preset_id: str | None, keys: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Free (no-API) measures for a freshly drafted text: fact coverage (presets only) and unsupported numbers."""
    facts = None
    if preset_id and preset_id in PRESET_IDS:
        keys = keys or load_quality_keys()
        rows = score_facts(text, facts_for(keys, preset_id))
        fd = {f["id"]: f for f in keys["facts"]}
        facts = {
            "core_facts": _count(proportion(r for r in rows if r["tier"] == "core")),
            "detail_facts": _count(proportion(r for r in rows if r["tier"] == "detail")),
            "missed_facts": [{"description": fd[r["fact_id"]]["description"], "tier": r["tier"]} for r in rows if not r["hit"]],
            "keys_version": (keys.get("meta") or {}).get("keys_version"),
        }
    num_rows = classify_numbers(text, payload)
    s = numbers_summary(num_rows)
    return {
        "facts": facts,
        "numbers": {
            "numeric_tokens": s["numeric_tokens"],
            "not_in_source": s["not_in_source"],
            "items": [{"text": n["text"], "context": n["snippet"], "verdict": None} for n in not_in_source_list(num_rows)],
        },
    }
