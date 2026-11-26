"""The fixed supplier-scope line put in front of every Category 4 question.

Shared by the app runner (live and ad-hoc questions) and the quality-rerun harness, which recorded every rerun
question with it. Depends only on the deal-room fixture, so both can import it without a circular import.
"""

from __future__ import annotations

from app.data.cat4_fixtures import DEAL_ROOM_PROFILE

SCOPE_LINE_TEMPLATE = "Deal room under audit: {deal_room_id} (supplier: {supplier_legal_name}). Answer for this supplier's contracts only."


def scope_line() -> str:
    """The fixed supplier-scope line prepended to every question (all rungs, both scales, app and rerun)."""
    return SCOPE_LINE_TEMPLATE.format(deal_room_id=DEAL_ROOM_PROFILE["deal_room_id"],
                                      supplier_legal_name=DEAL_ROOM_PROFILE["supplier_legal_name"])


def scoped_question(question: str) -> str:
    """Scope line, a blank line, then the original question text. The golden capture was asked without it."""
    return f"{scope_line()}\n\n{question}"
