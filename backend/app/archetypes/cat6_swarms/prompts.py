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
    """Role-specific instructions appended after cached SHARED_REPO_PREFIX_MARKDOWN."""
    if rung_id == "unisolated_broadcast_swarm":
        return (
            "You are operating inside a shared-bus engineering swarm where all agents append full prose "
            "and code to one cumulative thread.\n"
            f"Current Active Persona: {AGENT_ROLE_LABELS.get(role_key, role_key)}.\n"
            "Inspect all preceding messages carefully, provide exhaustive multi-section commentary, "
            "and when acting as Patch Author output a complete fenced ```python code block with the repaired module."
        )

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


def build_cat6_unisolated_turn_message(preset: dict[str, Any], role_key: str) -> str:
    """User message for Rung 1's shared-bus broadcast swarm (carries 100k+ bloated context)."""
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
            "[TURN 1 — LEAD ORCHESTRATOR]: Produce a thorough root-cause analysis and multi-agent "
            "execution plan covering all affected modules and CI runner traces."
        )
    if role_key == "ci_triager":
        return (
            "[TURN 2 — CI/CD & RUNTIME TRIAGER]: Correlate the failing assertions and OpenTelemetry traces above "
            "to every concrete bug in the target source file and list all edge cases that must be fixed."
        )
    if role_key == "patch_author":
        return (
            f"[TURN 3 — CODE & PATCH AUTHOR]: Implement the complete repaired `{preset['module_filename']}` module "
            f"following `{preset['standard_ref']}` exactly (preserve all public names/signatures and AST rules). "
            "Provide the full module inside one fenced ```python block."
        )
    if role_key == "security_critic":
        return (
            "[TURN 4 — SECURITY & TEST CRITIC]: Critically review the proposed patch against every unit, "
            "security, privacy, and concurrency invariant and document your findings."
        )
    return (
        "[TURN 5 — LEAD ORCHESTRATOR MERGE GATE]: Provide the final deployment readiness sign-off memo "
        "synthesizing all findings above."
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
    """Narrow, isolated context handoff for Rung 2 & Rung 3 sub-agents (NO sibling noise)."""
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
    "text": SHARED_REPO_PREFIX_MARKDOWN,  # ~6.2k tok, byte-identical across sub-agents
    "cache_control": {"type": "ephemeral"},
}

# 1) Lead Orchestrator & 2) CI Triager run on Claude Haiku 5.5 ($0.10/M in, $0.01/M cache read)
plan = await run_swarm_agent("claude-haiku-5-5", shared_repo_block, ORCH_PROMPT, ticket_plus_ci_log)
triage = await run_swarm_agent("claude-haiku-5-5", shared_repo_block, TRIAGER_PROMPT, plan + buggy_file)

# 3) Code & Patch Author runs on Claude Sonnet 5.5 (frontier coding only, no noisy OTel spans)
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
    "sandbox_cpo_gate": '''# Cost per Verified Outcome (CpO) vs Vanity Cost per Run (CpR)
def compute_cpo(runs: list[SwarmRun]) -> dict[str, float]:
    total_spend_1k = sum(r.cost_per_1k_runs_usd for r in runs)
    verified_rate = sum(1 for r in runs if r.sandbox_report.verified_outcome) / len(runs)
    # Anti-pattern traps look cheap per run, but non-verified patches blow up CpO!
    cpo_per_1k_usd = total_spend_1k / max(0.01, verified_rate * len(runs))
    return {
        "cpr_per_1k": round(total_spend_1k / len(runs), 2),
        "verified_outcome_rate_pct": round(verified_rate * 100, 1),
        "cpo_per_1k": round(cpo_per_1k_usd, 2),
    }
''',
}
