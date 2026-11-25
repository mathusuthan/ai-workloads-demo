"""Helpers for UI claims that must be computed from run results instead of hard-coded.

Rung badges and architectural notes used to carry fixed numbers ("-97% Cost", "~115k–130k prompt
tok/run") that drifted from the data. Each runner now writes number-free fallback text in its
`_rung_metadata` and calls `apply_*_claims` after results and savings are known, replacing the
result-dependent sentences with values measured on that run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from app.config import get_settings
from app.core.pricing import compute_run_finops


class _HasNotes(Protocol):
    architectural_notes: list[str]


def set_note(result: _HasNotes, index: int, text: str) -> None:
    """Replace note `index` (or append if the list is shorter) without mutating a shared list."""
    notes = list(result.architectural_notes)
    if index < len(notes):
        notes[index] = text
    else:
        notes.append(text)
    result.architectural_notes = notes


def pct_cut(base: float, new: float) -> float | None:
    """Percent reduction from `base` to `new`; None when there is no positive baseline."""
    return (1 - new / base) * 100 if base > 0 else None


def fmt_pct(value: float) -> str:
    """Whole-number percent; keeps one decimal only when rounding would show 100% or 0%."""
    rounded = round(value)
    if rounded in (0, 100) and abs(value - rounded) > 0.05:
        return f"{value:.1f}%"
    return f"{rounded:.0f}%"


def _load_replays(name: str) -> dict[str, Any]:
    path = Path(get_settings().replays_dir) / name
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def rule1_measured_impact() -> str | None:
    """Impact line for FinOps rule 1 (Cat 1 & 2), measured on the golden replays.

    Range of per-item cost reduction for every rule-1 lever vs its naive baseline:
    Cat 1 Haiku + strict JSON and Gemini Decision vs Sonnet prose; Cat 2 Sonnet section template and
    Haiku section template vs unbounded Sonnet.
    """
    cuts: list[float] = []
    items = 0

    def cost(model: str, tin: int, tout: int) -> float:
        return compute_run_finops(model, int(tin or 0), int(tout or 0)).total_cost_usd

    cat1 = _load_replays("cat1_golden_replays.json")
    for p in (cat1.get("presets") or {}).values():
        r = p.get("rungs") or {}
        if "sonnet_naive" not in r:
            continue
        base = cost(r["sonnet_naive"]["model_id"], r["sonnet_naive"]["input_tokens"], r["sonnet_naive"]["output_tokens"])
        items += 1
        for rid in ("haiku_calibrated", "gemini_decision"):
            if rid in r:
                c = pct_cut(base, cost(r[rid]["model_id"], r[rid]["input_tokens"], r[rid]["output_tokens"]))
                if c is not None:
                    cuts.append(c)
    for b in (cat1.get("batch_items") or {}).values():
        base = cost("claude-sonnet-5-5", b.get("sonnet_input_tokens"), b.get("sonnet_output_tokens"))
        items += 1
        for c in (
            pct_cut(base, cost("claude-haiku-5-5", b.get("input_tokens"), b.get("haiku_output_tokens"))),
            pct_cut(base, cost("gemini-decision-1", b.get("gemini_input_tokens"), 0)),
        ):
            if c is not None:
                cuts.append(c)

    cat2 = _load_replays("cat2_golden_replays.json")
    for p in (cat2.get("presets") or {}).values():
        r = p.get("rungs") or {}
        if "sonnet_unbounded" not in r:
            continue
        base = cost(r["sonnet_unbounded"]["model_id"], r["sonnet_unbounded"]["input_tokens"], r["sonnet_unbounded"]["output_tokens"])
        items += 1
        for rid in ("sonnet_templated", "haiku_templated"):
            if rid in r:
                c = pct_cut(base, cost(r[rid]["model_id"], r[rid]["input_tokens"], r[rid]["output_tokens"]))
                if c is not None:
                    cuts.append(c)

    if not cuts:
        return None
    lo, hi = min(cuts), max(cuts)
    return f"Impact: {fmt_pct(lo).rstrip('%')}–{fmt_pct(hi)} lower unit inference cost (measured on {items} golden-replay items)"
