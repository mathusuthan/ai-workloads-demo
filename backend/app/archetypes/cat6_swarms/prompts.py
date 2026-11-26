"""Agent role prompts and code-inspector snippets for Category 6 Multi-Agent Swarms."""

from __future__ import annotations

from typing import Any

from app.data.cat6_fixtures import (
    SHARED_REPO_PREFIX_MARKDOWN,
    UNFILTERED_REPO_AND_TELEMETRY_NOISE,
)

AGENT_ROLE_LABELS: dict[str, str] = {
    "orchestrator_plan": "1. Lead Orchestrator (Plan & Triage Dispatch)",
    "ci_triager": "2. Swarm Agent: CI / Runtime Triager",
    "patch_author": "3. Swarm Agent: Code & Patch Author",
    "security_critic": "4. Swarm Agent: Security & Test Critic",
    "orchestrator_merge": "5. Lead Orchestrator (Merge Gate Sign-Off)",
}


def get_cat6_agent_system_prompt(rung_id: str, role_key: str) -> str:
    """Role-specific instructions; the same on every rung, so the rungs differ only in context design and models.

    On the isolated rungs they follow the cached SHARED_REPO_PREFIX_MARKDOWN; on the shared-bus rung the repo
    manual travels in the bus itself. `rung_id` is accepted for call-site symmetry.
    """
    role_directives = {
        "orchestrator_plan": (
            "Role: Lead Orchestrator (Plan Step). Read the incident summary & failing log, identify "
            "which Engineering Standard applies (`ENG-STD-04`, `SEC-STD-02`, or `CONC-STD-07`), and output "
            "a crisp 4-bullet work order for the CI Triager and Patch Author (<=130 words)."
        ),
        "ci_triager": (
            "Role: Swarm CI/CD & Runtime Triager. Map the exact failing assertions or exploit paths to the "
            "defects in the target Python file and list exact contractual invariants the Patch Author must satisfy "
            "(<=160 words). Do not emit full code."
        ),
        "patch_author": (
            "Role: Swarm Code & Patch Author. Rewrite ONLY the target Python module to satisfy 100% of the "
            "referenced standard (`ENG-STD-04`, `SEC-STD-02`, or `CONC-STD-07`) and ALL edge cases in the repo prefix. "
            "Preserve EVERY dataclass name, field name, exception class, and function/method signature verbatim. "
            "Strictly depend ONLY on safe Python stdlib modules (`dataclasses`, `decimal`, `hashlib`, `hmac`, `threading`, `time`, `typing`, `re` — NEVER import `os`, `sys`, `pathlib`, `subprocess`, `socket`, `shutil`, `urllib`, `http`, or call `open`/`eval`/`exec`). "
            "NEVER call built-in `round()` in pricing, NEVER use `==`/`!=` between HMAC/signature variables, "
            "and ALWAYS use `sorted(...)` lock keys in reservation/release. "
            "Return the FULL self-contained repaired Python file inside ONE fenced ```python block."
        ),
        "security_critic": (
            "Role: Swarm Security & Test Critic. Review the diff and deterministic `PR-SANDBOX-GATE-01` "
            "(10 checks: 4 CI Unit + 4 Adversarial + 2 Static AST). Confirm there are no DPDP PII leaks, "
            "timing side channels, paise rounding leaks, or lock-order deadlocks (<=150 words)."
        ),
        "orchestrator_merge": (
            "Role: Lead Orchestrator (Final Merge Gate). Summarize the verified patch, `10/10` sandbox outcome, "
            "and readiness for green PR auto-merge in 3 crisp bullet points (<=110 words)."
        ),
    }
    return role_directives.get(role_key, "Follow NovaMart Engineering Standards strictly.")


_BUS_TURN_LABELS: dict[str, str] = {
    "orchestrator_plan": "[TURN 1 — LEAD ORCHESTRATOR]",
    "ci_triager": "[TURN 2 — CI/CD & RUNTIME TRIAGER]",
    "patch_author": "[TURN 3 — CODE & PATCH AUTHOR]",
    "security_critic": "[TURN 4 — SECURITY & TEST CRITIC]",
    "orchestrator_merge": "[TURN 5 — LEAD ORCHESTRATOR MERGE GATE]",
}


def _patch_author_ask(preset: dict[str, Any]) -> str:
    return (
        f"Write the COMPLETE repaired `{preset['module_filename']}` strictly conforming to "
        f"`{preset['standard_ref']}` in one fenced ```python block."
    )


def format_cat6_failing_checks(sandbox_report: dict[str, Any]) -> str:
    """Failing-check lines sent back to the patch author on the one gate retry (every rung)."""
    return "\n".join(
        f"- FAIL {c['check_id']} ({c['name']}): {c['detail']}"
        for c in sandbox_report.get("checks") or []
        if not c["passed"]
    )


def _sandbox_checks_block(sandbox_report: dict[str, Any]) -> str:
    sbx = sandbox_report or {}
    sbx_summary = "\n".join(
        f"- {c['check_id']} [{'PASS' if c['passed'] else 'FAIL'}]: {c['name']} -> {c['detail']}"
        for c in (sbx.get("checks") or [])
    )
    return (
        f"#### Deterministic PR-SANDBOX-GATE-01 ({sbx.get('passed_checks', 0)}/{sbx.get('total_checks', 10)})\n"
        f"{sbx_summary}"
    )


def _sandbox_status_line(sandbox_report: dict[str, Any]) -> str:
    sbx = sandbox_report or {}
    return (
        f"#### PR-SANDBOX-GATE-01 Status: `{sbx.get('passed_checks', 0)}/{sbx.get('total_checks', 10)}` "
        f"(Verified Outcome: `{sbx.get('verified_outcome', False)}`)"
    )


def build_cat6_shared_bus_turn_message(
    preset: dict[str, Any],
    role_key: str,
    *,
    sandbox_report: dict[str, Any] | None = None,
) -> str:
    """User message for one shared-bus turn (the shared-bus versions, 1 and 2): the same asks as the isolated rungs, on one growing thread.

    Turn 1 carries the incident, the buggy source, the full repo manual and the unrelated neighbour services and
    OTel spans; later turns append only their ask, so every agent reads everything said before it.
    """
    label = _BUS_TURN_LABELS[role_key]
    if role_key == "orchestrator_plan":
        return (
            f"### INCIDENT / PR TICKET: {preset['pr_id']} ({preset['use_case_tag']})\n"
            f"- Service: `{preset['service_name']}`\n"
            f"- Target File: `{preset['target_file']}`\n"
            f"- Severity: `{preset['severity']}` · Standard: `{preset['standard_ref']}`\n"
            f"- Summary: {preset['title']} — {preset['subtitle']}\n\n"
            f"#### Failing CI / Exploit Output\n```text\n{preset['ci_failure_log']}\n```\n\n"
            f"#### Buggy Target Source (`{preset['target_file']}`)\n```python\n{preset['buggy_code']}\n```\n\n"
            f"#### Monorepo Architecture & Standards Manual\n{SHARED_REPO_PREFIX_MARKDOWN}\n\n"
            f"{UNFILTERED_REPO_AND_TELEMETRY_NOISE}\n\n"
            f"{label}: Produce your concise 4-bullet remediation order."
        )
    if role_key == "ci_triager":
        return f"{label}: Pinpoint the exact broken lines and mandatory contracts for the Patch Author."
    if role_key == "patch_author":
        return f"{label}: {_patch_author_ask(preset)}"
    if sandbox_report is None:
        raise ValueError(f"`{role_key}` turn requires the sandbox report.")
    if role_key == "security_critic":
        return (
            f"{label}:\n\n{_sandbox_checks_block(sandbox_report)}\n\n"
            f"Confirm `{preset['standard_ref']}` and all AST security/privacy invariants hold."
        )
    if role_key == "orchestrator_merge":
        return f"{label}:\n\n{_sandbox_status_line(sandbox_report)}\n\nEmit your final PR merge readiness sign-off."
    raise ValueError(f"Unknown role_key `{role_key}`")


def build_cat6_shared_bus_retry_message(preset: dict[str, Any], failing_lines: str) -> str:
    """The single gate-retry user message appended to the shared bus after a failed sandbox run."""
    return (
        f"{_BUS_TURN_LABELS['patch_author']} — SANDBOX RETRY:\n\n"
        f"#### SANDBOX RETRY FEEDBACK (Fix All Failing Checks Below)\n{failing_lines}\n\n"
        f"{_patch_author_ask(preset)}"
    )


def build_cat6_isolated_payload(
    *,
    preset: dict[str, Any],
    role_key: str,
    orchestrator_brief: str = "",
    triage_brief: str = "",
    patched_code: str = "",
    sandbox_report: dict[str, Any] | None = None,
    critic_verdict: str = "",
    retry_feedback: str = "",
) -> str:
    """Narrow, isolated context handoff for the isolated versions' (3 and 4) sub-agents (NO sibling noise)."""
    header = (
        f"Ticket `{preset['pr_id']}` · `{preset['use_case_tag']}` · `{preset['service_name']}`\n"
        f"Target File: `{preset['target_file']}` · Standard: `{preset['standard_ref']}`\n"
        f"Issue: {preset['title']} — {preset['subtitle']}"
    )

    if role_key == "orchestrator_plan":
        return (
            f"{header}\n\n"
            f"#### CI Failure / Exploit Output\n```text\n{preset['ci_failure_log']}\n```\n\n"
            "Produce your concise 4-bullet remediation order."
        )

    if role_key == "ci_triager":
        return (
            f"{header}\n\n"
            f"#### Orchestrator Plan\n{orchestrator_brief}\n\n"
            f"#### Buggy Source (`{preset['module_filename']}`)\n```python\n{preset['buggy_code']}\n```\n\n"
            f"#### CI Failure Log\n```text\n{preset['ci_failure_log']}\n```\n\n"
            "Pinpoint the exact broken lines and mandatory contracts for the Patch Author."
        )

    if role_key == "patch_author":
        retry_block = (
            f"\n\n#### SANDBOX RETRY FEEDBACK (Fix All Failing Checks Below)\n{retry_feedback}"
            if retry_feedback
            else ""
        )
        return (
            f"{header}\n\n"
            f"#### CI Triager Handoff\n{triage_brief}\n\n"
            f"#### Current Source (`{preset['module_filename']}`)\n```python\n{preset['buggy_code']}\n```"
            f"{retry_block}\n\n"
            f"Write the COMPLETE repaired `{preset['module_filename']}` strictly conforming to "
            f"`{preset['standard_ref']}` in one fenced ```python block."
        )

    if role_key == "security_critic":
        sbx = sandbox_report or {}
        sbx_summary = "\n".join(
            f"- {c['check_id']} [{'PASS' if c['passed'] else 'FAIL'}]: {c['name']} -> {c['detail']}"
            for c in (sbx.get("checks") or [])
        )
        return (
            f"{header}\n\n"
            f"#### Deterministic PR-SANDBOX-GATE-01 ({sbx.get('passed_checks', 0)}/{sbx.get('total_checks', 10)})\n"
            f"{sbx_summary}\n\n"
            f"#### Candidate Patched Module\n```python\n{patched_code}\n```\n\n"
            f"Confirm `{preset['standard_ref']}` and all AST security/privacy invariants hold."
        )

    # orchestrator_merge
    sbx = sandbox_report or {}
    return (
        f"{header}\n\n"
        f"#### PR-SANDBOX-GATE-01 Status: `{sbx.get('passed_checks', 0)}/{sbx.get('total_checks', 10)}` "
        f"(Verified Outcome: `{sbx.get('verified_outcome', False)}`)\n\n"
        f"#### Security & Test Critic Verdict\n{critic_verdict}\n\n"
        "Emit your final PR merge readiness sign-off."
    )


CAT6_CODE_SNIPPETS: dict[str, str] = {
    "isolated_swarm_orchestrator": '''# Tier-Routed Context-Isolated Swarm (Haiku Orchestration + Sonnet Patch + Shared Cached Prefix)
shared_repo_block = {
    "type": "text",
    "text": SHARED_REPO_PREFIX_MARKDOWN,  # shared repo standards, byte-identical across sub-agents
    "cache_control": {"type": "ephemeral"},
}

# 1) Lead Orchestrator & 2) CI Triager run on Claude Haiku 5.5 ($0.10/M in, $0.01/M cache read)
plan = await run_swarm_agent("claude-haiku-5-5", shared_repo_block, ORCH_PROMPT, ticket_plus_ci_log)
triage = await run_swarm_agent("claude-haiku-5-5", shared_repo_block, TRIAGER_PROMPT, plan + buggy_file)

# 3) Code & Patch Author runs on Claude Sonnet 5.5 (patch authoring only, no OTel spans in its context)
patch = await run_swarm_agent("claude-sonnet-5-5", shared_repo_block, AUTHOR_PROMPT, triage + buggy_file)

# 4) Deterministic PR-SANDBOX-GATE-01 runs offline in Python -I subprocess (0 LLM tokens)
sandbox_report = evaluate_patch_in_sandbox(preset_id, extract_python_code(patch.raw_text))
if not sandbox_report["verified_outcome"]:
    patch = await run_swarm_agent("claude-sonnet-5-5", shared_repo_block, AUTHOR_PROMPT, failing_tracebacks)
    sandbox_report = evaluate_patch_in_sandbox(preset_id, extract_python_code(patch.raw_text))

# 5) Security Critic & Merge Gate verify diff + 10/10 sandbox output on Claude Haiku 5.5
critic = await run_swarm_agent("claude-haiku-5-5", shared_repo_block, CRITIC_PROMPT, patch + sandbox_report)
merge = await run_swarm_agent("claude-haiku-5-5", shared_repo_block, MERGE_PROMPT, sandbox_report + critic)
''',
    "sandbox_cpo_gate": '''# Cost per Verified Outcome (CpO) vs Cost per Run (CpR)
def compute_cpo(runs: list[SwarmRun]) -> dict[str, float | None]:
    total_spend_1k = sum(r.cost_per_1k_runs_usd for r in runs)
    verified = sum(1 for r in runs if r.sandbox_report.verified_outcome)
    # CpO charges all spend (failed runs included) to the verified outcomes; it equals CpR when every run verifies.
    return {
        "cpr_per_1k": round(total_spend_1k / len(runs), 2),
        "verified_outcome_rate_pct": round(verified / len(runs) * 100, 1),
        "cpo_per_1k": round(total_spend_1k / verified, 2) if verified else None,  # undefined, never "free"
    }
''',
}
