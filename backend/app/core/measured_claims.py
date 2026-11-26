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

    Range of per-item cost reduction of the deck's lever vs the same model without it: Cat 1 classification
    with a strict JSON schema vs the four-part write-up (Sonnet and Haiku); Cat 2 section template with length caps vs
    the unbounded draft (Sonnet and Haiku, where both rungs are in the replays).
    """
    cuts: list[float] = []
    items = 0

    def cost(r: dict[str, Any]) -> float:
        return compute_run_finops(r["model_id"], int(r.get("input_tokens") or 0), int(r.get("output_tokens") or 0)).total_cost_usd

    pairs = {
        "cat1_golden_replays.json": (("sonnet_naive", "sonnet_calibrated"), ("haiku_naive", "haiku_calibrated")),
        "cat2_golden_replays.json": (("sonnet_unbounded", "sonnet_templated"), ("haiku_unbounded", "haiku_templated")),
    }
    for name, rung_pairs in pairs.items():
        data = _load_replays(name)
        for p in [*(data.get("presets") or {}).values(), *(data.get("batch_items") or {}).values()]:
            r = p.get("rungs") or {}
            counted = False
            for without, with_ in rung_pairs:
                if without in r and with_ in r:
                    c = pct_cut(cost(r[without]), cost(r[with_]))
                    if c is not None:
                        cuts.append(c)
                        counted = True
            items += 1 if counted else 0

    if not cuts:
        return None
    lo, hi = min(cuts), max(cuts)
    return f"Impact: {fmt_pct(lo).rstrip('%')}–{fmt_pct(hi)} lower unit inference cost (measured on {items} golden-replay items)"
