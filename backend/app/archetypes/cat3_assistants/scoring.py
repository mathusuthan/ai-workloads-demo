"""Category 3 answer-key scoring: normalisation, matching, key loading and recall maths (pure).

Shared by the quality-rerun harness (`quality_rerun.py`), the app runner (replay and live scoring) and the
analysis scripts, so every number shown anywhere comes from the same functions. No API calls, no app state.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.archetypes.cat6_swarms.fair_rerun import wilson_interval

KEYS_PATH = Path(__file__).resolve().parents[2] / "data" / "cat3_quality_keys.json"

TURN_WINDOWS: dict[str, tuple[int, int]] = {"turns_1_4": (1, 4), "turns_5_9": (5, 9)}
LEDGER_WINDOWS: dict[str, tuple[int, int]] = {"origin_1_3": (1, 3), "origin_4_6": (4, 6), "origin_7_9": (7, 9)}
PROBE_WINDOWS: dict[str, tuple[int, int]] = {"origin_1_6": (1, 6), "origin_7_9": (7, 9)}


# --------------------------------------------------------------------------------------------------
# Normalisation + scoring (pure)
# --------------------------------------------------------------------------------------------------

# Rule 2: markdown emphasis markers and code backticks are deleted (`**`, `*`, `~~`, backticks).
# Underscores are left alone because they are part of policy/error IDs (UNPAID_LOA_HOLD).
_EMPHASIS_RE = re.compile(r"\*+|~~|`+")
# Rule 3: every Unicode dash/minus becomes "-"; curly/prime quotes become straight quotes.
_CHAR_MAP = {
    **dict.fromkeys(map(ord, "‐‑‒–—―−﹘﹣－"), "-"),
    **dict.fromkeys(map(ord, "‘’‚‛′"), "'"),
    **dict.fromkeys(map(ord, "“”„‟″"), '"'),
}
_WS_RE = re.compile(r"\s+")
# Rule 5: a comma between digits is a thousands separator when exactly 2 or 3 digits follow it
# (western 64,200 and Indian 2,50,000 both collapse; "1,2,3" lists are untouched).
_THOUSANDS_RE = re.compile(r"(?<=\d),(?=\d{2,3}(?!\d))")
# Rule 6: currency symbols/words directly before a number (₹, $, inr, usd, rs, rs.) or a currency word
# directly after one (inr, usd) are deleted, so "₹64,200", "INR 64200" and "64,200 INR" all read "64200".
_CURRENCY_PREFIX_RE = re.compile(r"(?:[₹$]|\b(?:inr|usd|rs\.?))\s*(?=\d)")
_CURRENCY_SUFFIX_RE = re.compile(r"(?<=\d)\s*(?:inr|usd)\b")

NORMALISATION_RULES: tuple[str, ...] = (
    "1. Lowercase.",
    "2. Delete markdown emphasis markers and code backticks (`*`, `**`, `~~`, backticks); underscores are kept.",
    "3. Map Unicode dashes/minus signs (‐ ‑ ‒ – — ― −) to '-', curly quotes to straight quotes.",
    "4. Collapse all whitespace runs (incl. non-breaking spaces) to one space and trim.",
    "5. Remove a comma between digits when exactly 2 or 3 digits follow it (64,200 -> 64200; 2,50,000 -> 250000).",
    "6. Remove currency markers adjacent to a number: ₹, $, inr, usd, rs, rs. before it; inr, usd after it.",
    "Matching: an alternative is hit when it occurs in the normalised reply, with a boundary guard — an "
    "alternative starting with a letter/digit must not be preceded by a letter/digit, and one ending in a "
    "digit must not be followed by a digit.",
)


def normalise_text(text: str | None) -> str:
    """Conservative normalisation applied identically to replies and answer-key alternatives."""
    s = (text or "").lower()
    s = _EMPHASIS_RE.sub("", s)
    s = s.translate(_CHAR_MAP)
    s = _WS_RE.sub(" ", s).strip()
    s = _THOUSANDS_RE.sub("", s)
    s = _CURRENCY_PREFIX_RE.sub("", s)
    s = _CURRENCY_SUFFIX_RE.sub("", s)
    return _WS_RE.sub(" ", s).strip()


def contains_alternative(normalised_text: str, alternative: str) -> bool:
    """True when the normalised `alternative` occurs in `normalised_text` respecting the boundary guard."""
    alt = normalise_text(alternative)
    if not alt:
        return False
    start = 0
    while True:
        i = normalised_text.find(alt, start)
        if i < 0:
            return False
        j = i + len(alt)
        before_ok = not (alt[0].isalnum() and i > 0 and normalised_text[i - 1].isalnum())
        after_ok = not (alt[-1].isdigit() and j < len(normalised_text) and normalised_text[j].isdigit())
        if before_ok and after_ok:
            return True
        start = i + 1


def fact_hit(text: str | None, any_of: Sequence[str]) -> bool:
    norm = normalise_text(text)
    return any(contains_alternative(norm, alt) for alt in any_of)


def score_reply(text: str | None, facts: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """[{fact_id, hit}] for each fact (facts or probes; ids from `id` or `probe_id`)."""
    norm = normalise_text(text)
    return [
        {
            "fact_id": f.get("id") or f.get("probe_id"),
            "hit": any(contains_alternative(norm, alt) for alt in f["any_of"]),
        }
        for f in facts
    ]


# --------------------------------------------------------------------------------------------------
# Answer key
# --------------------------------------------------------------------------------------------------


def load_quality_keys(path: Path | str | None = None) -> dict[str, Any]:
    return json.loads(Path(path or KEYS_PATH).read_text(encoding="utf-8"))


def probes_for(keys: dict[str, Any], preset_id: str) -> list[dict[str, Any]]:
    return [p for p in keys["probes"] if p["preset_id"] == preset_id]


def all_scored_items(keys: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn facts, ledger facts and probes as uniform rows (probes appear as kind='probe', source='session')."""
    rows = [
        {
            "fact_id": f["id"],
            "preset_id": f["preset_id"],
            "kind": f["kind"],
            "turn": f.get("turn") if f["kind"] == "turn" else f.get("origin_turn"),
            "source": f["source"],
            "description": f["description"],
            "any_of": list(f["any_of"]),
        }
        for f in keys["facts"]
    ]
    rows += [
        {
            "fact_id": p["probe_id"],
            "preset_id": p["preset_id"],
            "kind": "probe",
            "turn": p["origin_turn"],
            "source": "session",
            "description": p["question"],
            "any_of": list(p["any_of"]),
        }
        for p in keys["probes"]
    ]
    return rows


def key_counts(keys: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for row in all_scored_items(keys):
        slot = out.setdefault(row["preset_id"], {})
        k = f"{row['kind']}|{row['source']}"
        slot[k] = slot.get(k, 0) + 1
    return out


def score_session(
    *,
    preset_id: str,
    turn_texts: dict[int, str],
    probe_answers: dict[str, str] | None,
    keys: dict[str, Any],
) -> list[dict[str, Any]]:
    """Score one session: turn facts vs their turn's reply, ledger facts vs turn 10, probes vs their answers.

    Items whose reply is missing (turn not recorded, probe not asked) are omitted, not counted as misses.
    """
    rows: list[dict[str, Any]] = []
    for f in keys["facts"]:
        if f["preset_id"] != preset_id:
            continue
        turn = int(f["turn"]) if f["kind"] == "turn" else 10
        if turn not in turn_texts:
            continue
        rows.append(
            {
                "fact_id": f["id"],
                "kind": f["kind"],
                "turn": int(f.get("turn") or f.get("origin_turn")),
                "source": f["source"],
                "hit": fact_hit(turn_texts[turn], f["any_of"]),
            }
        )
    if probe_answers is not None:
        for p in probes_for(keys, preset_id):
            if p["probe_id"] not in probe_answers:
                continue
            rows.append(
                {
                    "fact_id": p["probe_id"],
                    "kind": "probe",
                    "turn": int(p["origin_turn"]),
                    "source": "session",
                    "hit": fact_hit(probe_answers[p["probe_id"]], p["any_of"]),
                }
            )
    return rows


# --------------------------------------------------------------------------------------------------
# Summary maths (pure)
# --------------------------------------------------------------------------------------------------


def _prop(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    k = sum(1 for r in rows if r["hit"])
    n = len(rows)
    return {"hits": k, "total": n, "rate": (k / n) if n else None, "wilson95": wilson_interval(k, n)}


def _in(window: tuple[int, int], turn: int) -> bool:
    return window[0] <= turn <= window[1]


def quality_metrics(scored_runs: Sequence[Sequence[dict[str, Any]]]) -> dict[str, Any]:
    """Pooled recall/accuracy with Wilson 95% intervals over a list of scored sessions."""
    rows = [r for run in scored_runs for r in run]
    turn = [r for r in rows if r["kind"] == "turn"]
    ledger = [r for r in rows if r["kind"] == "ledger"]
    probe = [r for r in rows if r["kind"] == "probe"]
    return {
        "sessions": len(scored_runs),
        "turn_recall": {
            "turns_1_9": _prop(turn),
            **{name: _prop(r for r in turn if _in(w, r["turn"])) for name, w in TURN_WINDOWS.items()},
        },
        "ledger_recall": {
            "overall": _prop(ledger),
            "by_origin": {name: _prop(r for r in ledger if _in(w, r["turn"])) for name, w in LEDGER_WINDOWS.items()},
            "by_source": {s: _prop(r for r in ledger if r["source"] == s) for s in ("handbook", "session")},
        },
        "probe_accuracy": {
            "overall": _prop(probe),
            "by_origin": {name: _prop(r for r in probe if _in(w, r["turn"])) for name, w in PROBE_WINDOWS.items()},
        },
    }




# --------------------------------------------------------------------------------------------------
# App-facing helpers (display only; never used to decide a hit)
# --------------------------------------------------------------------------------------------------

LEDGER_WINDOW_LABELS: dict[str, str] = {"origin_1_3": "1-3", "origin_4_6": "4-6", "origin_7_9": "7-9"}

# A missed probe answer that says the value is not available is shown as "declined", not as a wrong value.
# This only labels misses for display; scoring is decided by the answer key alone.
_DECLINE_RE = re.compile(
    r"\b(?:i (?:do not|don't|dont) have|i (?:can ?not|can't|cannot) (?:give|confirm|find|provide|recall|see)|"
    r"i won't guess|(?:isn't|is not|wasn't|was not|never) (?:in|recorded|captured|mentioned|stated|provided)|"
    r"(?:doesn't|does not|didn't|did not) (?:record|capture|include|contain|mention|have)|"
    r"not (?:recorded|captured|available) in|no record of)\b"
)


def classify_probe_answer(answer: str | None, hit: bool) -> str:
    """'correct' when the key matched; otherwise 'declined' if the answer says it lacks the value, else 'wrong'."""
    if hit:
        return "correct"
    return "declined" if _DECLINE_RE.search(normalise_text(answer)) else "wrong"


@lru_cache(maxsize=4)
def cached_quality_keys(path: str | None = None) -> dict[str, Any]:
    """Answer key loaded once per process (the app scores every replay/live run against it)."""
    return load_quality_keys(path)


def measure(prop: dict[str, Any]) -> dict[str, Any]:
    """{hits, total, rate, ci_low, ci_high} from a `_prop` result (the app/portfolio wire shape)."""
    ci = prop.get("wilson95")
    return {
        "hits": int(prop["hits"]),
        "total": int(prop["total"]),
        "rate": prop.get("rate"),
        "ci_low": ci[0] if ci else None,
        "ci_high": ci[1] if ci else None,
    }


def compact_quality(metrics: dict[str, Any]) -> dict[str, Any]:
    """The three app measures from `quality_metrics()` output."""
    led = metrics["ledger_recall"]
    return {
        "turn_recall": measure(metrics["turn_recall"]["turns_1_9"]),
        "ledger_recall": measure(led["overall"]),
        "ledger_by_origin": {LEDGER_WINDOW_LABELS[k]: measure(v) for k, v in led["by_origin"].items()},
        "probe_accuracy": measure(metrics["probe_accuracy"]["overall"]),
    }
