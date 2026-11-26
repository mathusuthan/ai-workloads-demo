"""Synthesis answer formats for Category 4 — the single source of truth for which prompt each rung uses.

"original"        the legacy synthesis prompt, byte for byte (`prompts.get_cat4_synthesis_system_prompt`). Every
                  session recorded before 2026-11-26 used it; it stays here so those sessions remain reproducible,
                  and the two versions that see the whole corpus still use it (the change was not measured there).
"scoped_absence"  the same prompt with ONLY absence handling changed: the sign-off-gate bullet is reworded so a
                  missing gate is reported as "None stated in the text provided" instead of "the documents contain
                  no such gate", and one rule is added after the other rules saying the model may have been given
                  only part of the deal room. A rung that sees the whole corpus still states a real gate: the first
                  sentence of the bullet is unchanged apart from "as stated in the text provided to you".

The variant is composed from the app prompt by exact line replacement and insertion, so a unified diff of the two
shows exactly the changed and added lines (tests pin this).

Adopted 2026-11-26 for the retrieval versions only (user decision after the targeted rerun: 2 retrieval rungs x 2
corpus sizes x 3 sessions in each format). `ADOPTED_ANSWER_FORMAT` maps every rung to its format; the app runner,
the golden builder, the app portfolio and the validation report all read it.
"""

from __future__ import annotations

import difflib

from app.archetypes.cat4_rag.prompts import get_cat4_synthesis_system_prompt

ORIGINAL = "original"
SCOPED_ABSENCE = "scoped_absence"
ANSWER_FORMATS: tuple[str, ...] = (ORIGINAL, SCOPED_ABSENCE)
DEFAULT_ANSWER_FORMAT = ORIGINAL  # what a record without `settings.answer_format` used (the legacy prompt)
LEGACY_ANSWER_FORMAT = ORIGINAL
ADOPTED_ON = "2026-11-26"
# Per-rung format in use from ADOPTED_ON: retrieval versions (the answering model sees only 5 chunks) report a
# missing term as "not in the text provided"; full-corpus versions keep the legacy prompt (change not measured there).
ADOPTED_ANSWER_FORMAT: dict[str, str] = {
    "naive_full_corpus": ORIGINAL,
    "cached_full_corpus_citations": ORIGINAL,
    "hybrid_rag_rerank_citations": SCOPED_ABSENCE,
    "cached_rerank_hybrid": SCOPED_ABSENCE,
}

ORIGINAL_GATE_LINE = "- **Required Sign-Off Gate**: Concrete operational, banking NOC, escrow, or delisting gate before execution."
SCOPED_GATE_LINE = (
    "- **Required Sign-Off Gate**: Concrete operational, banking NOC, escrow, or delisting gate before execution, as "
    "stated in the text provided to you. If that text states none, write \"None stated in the text provided\" — never "
    "state that the deal room or the contracts contain no such gate, because you may not have been given every clause."
)
LAST_RULE_LINE = "- Never invent figures, clauses, or dates not explicitly present in the provided deal-room text."
PARTIAL_CONTEXT_RULE = (
    "- You may have been given only part of the deal room. When something is not in the text provided, say it is not "
    "in the text provided; do not say the documents or the deal room lack it."
)


def _replace_line(lines: list[str], old: str, new: list[str]) -> list[str]:
    hits = [i for i, line in enumerate(lines) if line == old]
    if len(hits) != 1:
        raise RuntimeError(f"App synthesis prompt changed: expected exactly one line {old[:60]!r}; update answer_formats.py")
    i = hits[0]
    return [*lines[:i], *new, *lines[i + 1:]]


def synthesis_system_prompt(*, with_citations: bool, answer_format: str = DEFAULT_ANSWER_FORMAT) -> str:
    """The synthesis system prompt for an answer format ("original" is the app prompt unchanged)."""
    base = get_cat4_synthesis_system_prompt(with_citations=with_citations)
    if answer_format == ORIGINAL:
        return base
    if answer_format != SCOPED_ABSENCE:
        raise ValueError(f"unknown answer_format {answer_format!r}; expected one of {ANSWER_FORMATS}")
    lines = base.split("\n")
    lines = _replace_line(lines, ORIGINAL_GATE_LINE, [SCOPED_GATE_LINE])
    lines = _replace_line(lines, LAST_RULE_LINE, [LAST_RULE_LINE, PARTIAL_CONTEXT_RULE])
    return "\n".join(lines)


def adopted_answer_format(rung_id: str) -> str:
    """The answer format a rung uses now (unknown rungs: the legacy prompt)."""
    return ADOPTED_ANSWER_FORMAT.get(rung_id, LEGACY_ANSWER_FORMAT)


def rung_synthesis_system_prompt(rung_id: str, *, with_citations: bool) -> str:
    """The synthesis system prompt a rung uses now (app live path and seeded traces)."""
    return synthesis_system_prompt(with_citations=with_citations, answer_format=adopted_answer_format(rung_id))


def instruction_changes(answer_format: str = SCOPED_ABSENCE) -> dict[str, list[str]]:
    """The exact lines a format removes from and adds to the legacy prompt (for reports and the app panel)."""
    if answer_format == ORIGINAL:
        return {"removed": [], "added": []}
    return {"removed": [ORIGINAL_GATE_LINE], "added": [SCOPED_GATE_LINE, PARTIAL_CONTEXT_RULE]}


def prompt_diff(*, with_citations: bool, answer_format: str = SCOPED_ABSENCE) -> str:
    """Unified diff from the app prompt to the variant (line-based)."""
    a = synthesis_system_prompt(with_citations=with_citations).split("\n")
    b = synthesis_system_prompt(with_citations=with_citations, answer_format=answer_format).split("\n")
    return "\n".join(difflib.unified_diff(a, b, fromfile="original", tofile=answer_format, lineterm=""))
