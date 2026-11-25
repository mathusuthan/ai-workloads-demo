"""System prompts, cached prefix builder, memory compactor prompt & SDK Inspector snippets for Cat 3."""

from __future__ import annotations

import json
from typing import Any

from app.data.cat3_fixtures import IT_HR_HANDBOOK_MARKDOWN

RUNG_RETENTION_FOOTERS: dict[str, str] = {
    "naive_full_history": (
        "[SESSION_RETENTION_POLICY: naive_full_history | mode=uncached_verbatim_append | "
        "Note: Static handbook + employee header + all prior verbatim messages are re-billed at full $2.00/M input rate each turn.]"
    ),
    "prefix_cached_history": (
        "[SESSION_RETENTION_POLICY: prefix_cached_history | mode=ephemeral_prefix_cache_full_tail | "
        "Note: Handbook prefix cached via cache_control=ephemeral (95% read discount), while full conversation history stays verbatim.]"
    ),
    "prefix_cached_summarized": (
        "[SESSION_RETENTION_POLICY: prefix_cached_summarized | mode=ephemeral_prefix_cache_sliding_summary | "
        "Note: Handbook prefix cached via cache_control=ephemeral; turns beyond recent window are compressed into structured memory JSON.]"
    ),
}


def build_cat3_system_handbook(
    rung_id: str,
    employee_profile: dict[str, Any],
) -> str:
    """Build the deterministic IT & HR Handbook prefix (~9.86k tokens measured) + employee context + rung policy tag."""
    profile_block = json.dumps(employee_profile, indent=2)
    footer = RUNG_RETENTION_FOOTERS.get(rung_id, RUNG_RETENTION_FOOTERS["prefix_cached_summarized"])
    return (
        f"{IT_HR_HANDBOOK_MARKDOWN.strip()}\n\n"
        f"=== ACTIVE EMPLOYEE SESSION HEADER ===\n"
        f"{profile_block}\n\n"
        f"=== SERVICE DESK RESPONSE CONTRACT ===\n"
        f"- Ground every answer strictly in the Policy IDs, CLI commands, SLA durations, and ticket queue names above.\n"
        f"- Perform exact INR/USD math when verifying payroll variances, ergonomic caps, relocation gross-ups, or clawbacks.\n"
        f"- STRICT LENGTH CAP: Keep Turns 1–9 strictly between 110 and 180 words (max 4 tight bullets, exact CLI commands, Policy IDs, and Queue IDs — zero conversational preamble); keep Turn-10 final summary checklists strictly <= 250 words as ONE compact Markdown table with zero prose before or after.\n"
        f"- NEVER ask the employee to paste raw unmasked Aadhaar IDs, card PANs, or private keys in chat.\n\n"
        f"{footer}\n"
        f"[HANDBOOK_BUILD: v2026.11.r3]"
    )


def get_memory_summarizer_system_prompt() -> str:
    """State compressor prompt for the compacted JSON memory.

    Compaction is lossy: the Category 3 quality rerun shows specifics from evicted turns are dropped, so the
    assistant can no longer recall them (replays/cat3_quality_summary.json).
    """
    return (
        "You are NovaMart Service Desk's Sliding-Window Memory Compactor.\n"
        "Merge prior session memory with newly evicted turns into a compact, single-line minified JSON state snapshot (no newlines or indentation).\n"
        "Strict rules to keep overhead tiny (~220-380 output tokens total):\n"
        "1. Zero duplication across arrays — put each ID, metric, or fact in ONE array only.\n"
        "2. Hard array limits:\n"
        "   - employee_and_device_anchors: <= 3 items (<= 6 words each)\n"
        "   - resolved_issues: <= 4 items (<= 10 words each, include exact Policy/Queue/Command)\n"
        "   - active_open_items: <= 3 items (<= 10 words each)\n"
        "   - key_numeric_facts: <= 4 items (<= 8 words each, exact INR/USD/dates/SLAs)\n"
        "3. Preserve critical unresolved blockers across compactions until resolved."
    )


CAT3_CODE_SNIPPETS: dict[str, str] = {
    "naive_full_history": """# RUNG 1 ANTI-PATTERN: Uncached Full History (Quadratic O(N^2) Bill on Sonnet 5.5)
# Re-sends ~9,860-tok IT/HR Handbook + growing verbatim chat history @ $2.00/M every turn
resp = await client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=4096,
    thinking={"type": "between_tools"},
    system=full_handbook_and_profile,  # NO cache_control! Billed $2.00/M every turn
    messages=all_verbatim_turns_1_to_k,  # Grows linearly -> cumulative cost scales O(N^2)
)""",
    "prefix_cached_history": """# RUNG 2 LEVER 1: Anthropic Prefix Context Caching (-95% Cache Read Discount)
# Pays 1.25x ($2.50/M) once on cold Turn 1 (or $0.10/M warm fleet), then $0.10/M on Turns 2..10
# Note: Raw multi-turn logs in `messages` still grow uncached at $2.00/M!
resp = await client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=4096,
    thinking={"type": "between_tools"},
    system=[{
        "type": "text",
        "text": full_handbook_and_profile,
        "cache_control": {"type": "ephemeral"},  # >= 4,096 tok cache floor satisfied (~9.86k tok measured)
    }],
    messages=all_verbatim_turns_1_to_k,
)""",
    "prefix_cached_summarized": """# RUNG 3 LEVER 1 + LEVER 2: Prefix Caching + Sliding-Window Memory Summarization
# Compacts older turns when uncompacted window hits 4 turns ([T1..T3] before Turn 5, +[T4..T6] before Turn 8)
# Keeps active tail flat while preserving cached handbook prefix — net savings INCLUDES 100% summarizer cost!
# Trade-off: compaction is lossy — specifics dropped from memory can't be recalled in later turns.
if len(verbatim_turns) >= 4:
    evict, keep = verbatim_turns[:-1], verbatim_turns[-1:]
    memory_summary = await summarize_memory(prior_summary=memory_summary, evicted_turns=evict)
    verbatim_turns = keep

resp = await client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=4096,
    thinking={"type": "between_tools"},
    system=[{"type": "text", "text": full_handbook_and_profile, "cache_control": {"type": "ephemeral"}}],
    messages=[memory_state_pair(memory_summary), *verbatim_turns, new_user_turn],
)""",
}
