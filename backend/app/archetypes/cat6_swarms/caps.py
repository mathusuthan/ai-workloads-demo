"""Output caps and call timeout for every Category 6 sub-agent call (app live path and fair rerun).

Shared by `runner.py` (the three app rungs) and `fair_rerun.py` (the three experiment arms) so the app's
live path uses exactly the settings the fair rerun measured. The caps are the same on every rung and arm.
Imports nothing from either module.
"""

from __future__ import annotations

# The patch author gets the same generous cap on every rung, arm and attempt.
PATCH_AUTHOR_MAX_TOKENS = 16_000
# Non-author roles: a generous ceiling, not a length control; the word limits in the role prompts
# are the length control.
GOVERNED_ROLE_MAX_TOKENS: dict[str, int] = {
    "orchestrator_plan": 4000,
    "ci_triager": 4000,
    "security_critic": 4000,
    "orchestrator_merge": 4000,
}
CALL_TIMEOUT_S = 600.0


def cat6_max_tokens(*, role_key: str) -> int:
    """Output cap for one Category 6 call."""
    if role_key == "patch_author":
        return PATCH_AUTHOR_MAX_TOKENS
    return GOVERNED_ROLE_MAX_TOKENS[role_key]


def cat6_caps_by_role() -> dict[str, int]:
    """Per-role caps, as recorded in trace request parameters."""
    roles = ("orchestrator_plan", "ci_triager", "patch_author", "security_critic", "orchestrator_merge")
    return {r: cat6_max_tokens(role_key=r) for r in roles}
