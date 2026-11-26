"""AST-SEC-01 (inc-02) heuristic: module-level literal constants count as constants; nothing else does."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat6_swarms import sandbox_verifier as sv  # noqa: E402
from app.data.cat6_fixtures import CAT6_PRESETS  # noqa: E402

INC02 = next(p for p in CAT6_PRESETS if p["id"] == "inc-02")


def _sec01(code: str) -> dict[str, Any]:
    _, checks = sv.verify_ast_policies(textwrap.dedent(code), "inc-02")
    return next(c for c in checks if c["check_id"] == "AST-SEC-01")


SAFE_PREFIX_MODULE = """
import hmac

_SIG_PREFIX = "sha256="

def verify(header_sig: str, expected: str) -> bool:
    text = header_sig.strip()
    if text[: len(_SIG_PREFIX)].lower() == _SIG_PREFIX:
        text = text[len(_SIG_PREFIX):]
    return hmac.compare_digest(text, expected)
"""


def test_module_level_literal_prefix_passes() -> None:
    c = _sec01(SAFE_PREFIX_MODULE)
    assert c["passed"] is True
    assert c["detail"] == "Confirmed constant-time hmac.compare_digest() with zero direct signature == comparisons."


def test_annotated_module_constant_passes() -> None:
    code = SAFE_PREFIX_MODULE.replace('_SIG_PREFIX = "sha256="', '_SIG_PREFIX: str = "sha256="')
    assert _sec01(code)["passed"] is True


_COMPARE_DIGEST = "\nimport hmac\n\ndef ok(a, b):\n    return hmac.compare_digest(a, b)\n"


@pytest.mark.parametrize(
    "body",
    [
        # direct comparisons between two signature-ish variables
        "def f(expected_sig, provided_sig):\n    if expected_sig == provided_sig:\n        return True\n",
        "def f(computed_digest, header_sig):\n    if computed_digest != header_sig:\n        return False\n",
        # module-level name reassigned later at module level
        '_SIG = "sha256="\n_SIG = "sha512="\n\ndef f(header_sig):\n    return header_sig == _SIG\n',
        # module-level name rebound inside a function via `global`
        '_SIG = "sha256="\n\ndef reset():\n    global _SIG\n    _SIG = "x"\n\ndef f(header_sig):\n    return header_sig == _SIG\n',
        # augmented assignment
        '_SIG = "sha256="\n_SIG += "x"\n\ndef f(header_sig):\n    return header_sig == _SIG\n',
        # shadowed by a parameter of the same name
        '_SIG = "sha256="\n\ndef f(header_sig, _SIG):\n    return header_sig == _SIG\n',
        # module-level name bound to a non-literal
        'def make():\n    return "sha256="\n\n_SIG = make()\n\ndef f(header_sig):\n    return header_sig == _SIG\n',
        # function-local name bound to a literal (locals are NOT exempt)
        'def f(provided_sig):\n    sig_prefix = "sha256="\n    return provided_sig[:7] == sig_prefix\n',
    ],
)
def test_unsafe_comparisons_still_fail(body: str) -> None:
    c = _sec01(_COMPARE_DIGEST + "\n" + body)
    assert c["passed"] is False
    assert c["detail"] == "Violation (compare_digest=True, non_const_sig_eq=True)."


def test_buggy_baseline_unaffected_by_constant_exemption(monkeypatch: pytest.MonkeyPatch) -> None:
    new = sv.evaluate_patch_in_sandbox("inc-02", INC02["buggy_code"])
    monkeypatch.setattr(sv, "_module_literal_constant_names", lambda tree: set())  # no constant exemption
    old = sv.evaluate_patch_in_sandbox("inc-02", INC02["buggy_code"])
    assert new["verified_outcome"] is False
    strip = lambda d: {k: v for k, v in d.items() if k != "execution_ms"}  # noqa: E731
    assert strip(new) == strip(old)
    sec = next(c for c in new["checks"] if c["check_id"] == "AST-SEC-01")
    assert sec["passed"] is False
