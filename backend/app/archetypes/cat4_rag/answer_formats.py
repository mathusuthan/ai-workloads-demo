"""Synthesis prompt per Category 4 rung — the single source of truth for which prompt each rung uses.

Two answer formats (ids as recorded in `settings.answer_format`; a record without the field is `full_corpus`):

"full_corpus"     the app synthesis prompt (`prompts.get_cat4_synthesis_system_prompt`), used by the versions that
                  see the whole corpus.
"scoped_absence"  the same prompt for the retrieval version, which sees only the picked clauses: the
                  sign-off-gate bullet asks for the gate "as stated in the text provided" and to write "None stated
                  in the text provided" when it states none, and one rule says that when something is not in the
                  text provided, the answer says so rather than say the documents lack it.

The retrieval format is composed from the app prompt by exact line replacement and insertion (tests pin this).
"""

from __future__ import annotations

from typing import Any

from app.archetypes.cat4_rag.prompts import get_cat4_synthesis_system_prompt

FULL_CORPUS = "full_corpus"
SCOPED_ABSENCE = "scoped_absence"
ANSWER_FORMATS: tuple[str, ...] = (FULL_CORPUS, SCOPED_ABSENCE)

RUNG_ANSWER_FORMAT: dict[str, str] = {
    "naive_full_corpus": FULL_CORPUS,
    "cached_full_corpus_citations": FULL_CORPUS,
    "cached_rerank_hybrid": SCOPED_ABSENCE,
}

GATE_LINE = "- **Required Sign-Off Gate**: Concrete operational, banking NOC, escrow, or delisting gate before execution."
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


def synthesis_system_prompt(*, with_citations: bool, answer_format: str = FULL_CORPUS) -> str:
    """The synthesis system prompt for an answer format."""
    base = get_cat4_synthesis_system_prompt(with_citations=with_citations)
    if answer_format == FULL_CORPUS:
        return base
    if answer_format != SCOPED_ABSENCE:
        raise ValueError(f"unknown answer_format {answer_format!r}; expected one of {ANSWER_FORMATS}")
    lines = base.split("\n")
    lines = _replace_line(lines, GATE_LINE, [SCOPED_GATE_LINE])
    lines = _replace_line(lines, LAST_RULE_LINE, [LAST_RULE_LINE, PARTIAL_CONTEXT_RULE])
    return "\n".join(lines)


def rung_answer_format(rung_id: str) -> str:
    """The answer format a rung uses (unknown rungs: the full-corpus prompt)."""
    return RUNG_ANSWER_FORMAT.get(rung_id, FULL_CORPUS)


def record_answer_format(record: dict[str, Any]) -> str:
    """The answer format a recorded session used (no `settings.answer_format`: the full-corpus prompt)."""
    fmt = (record.get("settings") or {}).get("answer_format")
    return str(fmt) if fmt else FULL_CORPUS


def rung_synthesis_system_prompt(rung_id: str, *, with_citations: bool) -> str:
    """The synthesis system prompt a rung uses (app live path, rerun harness and seeded traces)."""
    return synthesis_system_prompt(with_citations=with_citations, answer_format=rung_answer_format(rung_id))
