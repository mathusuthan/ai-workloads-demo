"""Canonical FinOps rate card and tokenomics math for NovaMart AI Archetypes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from app.models import FinOpsBreakdown


@dataclass(frozen=True)
class ModelRateSpec:
    model_id: str
    label: str
    provider: str
    input_per_1m_usd: float
    output_per_1m_usd: float
    cache_write_per_1m_usd: float
    cache_read_per_1m_usd: float
    output_rate_multiplier: str
    notes: str


MODEL_RATES: dict[str, ModelRateSpec] = {
    "claude-sonnet-5-5": ModelRateSpec(
        model_id="claude-sonnet-5-5",
        label="Claude Sonnet 5.5",
        provider="Anthropic",
        input_per_1m_usd=2.00,
        output_per_1m_usd=10.00,
        cache_write_per_1m_usd=2.50,
        cache_read_per_1m_usd=0.10,
        output_rate_multiplier="5x output weight",
        notes="Frontier coding & reasoning tier; 5x output token multiplier; cache reads $0.10/M (-95%).",
    ),
    "claude-haiku-5-5": ModelRateSpec(
        model_id="claude-haiku-5-5",
        label="Claude Haiku 5.5",
        provider="Anthropic",
        input_per_1m_usd=0.10,
        output_per_1m_usd=0.50,
        cache_write_per_1m_usd=0.125,
        cache_read_per_1m_usd=0.01,
        output_rate_multiplier="5x output weight",
        notes="Low-latency Tier-1 extraction & schema classification (<=100k prompt tier).",
    ),
    "claude-haiku-5-5-batch": ModelRateSpec(
        model_id="claude-haiku-5-5-batch",
        label="Claude Haiku 5.5 (Message Batch -50%)",
        provider="Anthropic Batch API",
        input_per_1m_usd=0.05,
        output_per_1m_usd=0.25,
        cache_write_per_1m_usd=0.0625,
        cache_read_per_1m_usd=0.005,
        output_rate_multiplier="5x output weight · 50% async batch discount",
        notes="Asynchronous 50% discount for bulk catalog & backlog pipelines.",
    ),
    "claude-sonnet-5-5-batch": ModelRateSpec(
        model_id="claude-sonnet-5-5-batch",
        label="Claude Sonnet 5.5 (Message Batch -50%)",
        provider="Anthropic Batch API",
        input_per_1m_usd=1.00,
        output_per_1m_usd=5.00,
        cache_write_per_1m_usd=1.25,
        cache_read_per_1m_usd=0.05,
        output_rate_multiplier="5x output weight · 50% async batch discount",
        notes="Asynchronous 50% discount for bulk catalog & backlog pipelines.",
    ),
}

# Fallback rates if a live API call ever falls back to an older 4.x model ID
LEGACY_MODEL_RATES: dict[str, ModelRateSpec] = {
    "claude-sonnet-4-6": ModelRateSpec(
        model_id="claude-sonnet-4-6",
        label="Claude Sonnet 4.6",
        provider="Anthropic",
        input_per_1m_usd=3.00,
        output_per_1m_usd=15.00,
        cache_write_per_1m_usd=3.75,
        cache_read_per_1m_usd=0.30,
        output_rate_multiplier="5x output weight",
        notes="Previous-gen Sonnet fallback.",
    ),
    "claude-haiku-4-5": ModelRateSpec(
        model_id="claude-haiku-4-5",
        label="Claude Haiku 4.5",
        provider="Anthropic",
        input_per_1m_usd=1.00,
        output_per_1m_usd=5.00,
        cache_write_per_1m_usd=1.25,
        cache_read_per_1m_usd=0.10,
        output_rate_multiplier="5x output weight",
        notes="Previous-gen Haiku fallback.",
    ),
}


def compute_run_finops(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> FinOpsBreakdown:
    """Compute per-run, per-1k, 100k/mo, and 1M/mo unit economics for any model."""
    rate = MODEL_RATES.get(model_id) or LEGACY_MODEL_RATES[model_id]
    input_cost = (
        (input_tokens / 1_000_000) * rate.input_per_1m_usd
        + (cache_creation_tokens / 1_000_000) * rate.cache_write_per_1m_usd
        + (cache_read_tokens / 1_000_000) * rate.cache_read_per_1m_usd
    )
    output_cost = (output_tokens / 1_000_000) * rate.output_per_1m_usd
    total_cost = input_cost + output_cost
    prompt_tokens = input_tokens + cache_creation_tokens + cache_read_tokens
    total_tokens = prompt_tokens + output_tokens

    if output_tokens > 0:
        io_ratio = round(prompt_tokens / output_tokens, 1)
        io_ratio_label = f"{io_ratio}:1"
    else:
        io_ratio = None
        io_ratio_label = "∞ (0 out)"

    output_share = round((output_cost / total_cost) * 100, 1) if total_cost > 0 else 0.0

    return FinOpsBreakdown(
        model_id=rate.model_id,
        model_label=rate.label,
        provider=rate.provider,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_tokens=cache_creation_tokens,
        cache_read_tokens=cache_read_tokens,
        total_tokens=total_tokens,
        input_cost_usd=round(input_cost, 8),
        output_cost_usd=round(output_cost, 8),
        total_cost_usd=round(total_cost, 8),
        cost_per_1k_usd=round(total_cost * 1_000, 4),
        monthly_cost_at_100k_usd=round(total_cost * 100_000, 2),
        annual_cost_at_1m_per_mo_usd=round(total_cost * 12_000_000, 2),
        io_ratio=io_ratio,
        io_ratio_label=io_ratio_label,
        output_cost_share_pct=output_share,
        output_rate_multiplier=rate.output_rate_multiplier,
    )


def rollup_multi_call_finops(
    *,
    calls: Sequence[FinOpsBreakdown],
    total_cost_usd: float,
    model_id: str,
    model_label: str,
) -> FinOpsBreakdown:
    """Roll per-call breakdowns of a multi-step / multi-model run into one consistent FinOpsBreakdown.

    `total_cost_usd` is the run's headline cost (e.g. the cold-cache figure), which may differ from the
    sum of the per-call billed costs. Output cost is summed per call at each call's own model rate; input
    cost is the remainder, so input_cost_usd + output_cost_usd == total_cost_usd always holds.
    """
    in_tok = sum(c.input_tokens for c in calls)
    out_tok = sum(c.output_tokens for c in calls)
    cw_tok = sum(c.cache_creation_tokens for c in calls)
    cr_tok = sum(c.cache_read_tokens for c in calls)
    prompt_tok = in_tok + cw_tok + cr_tok
    output_cost = min(sum(c.output_cost_usd for c in calls), total_cost_usd)
    input_cost = max(0.0, total_cost_usd - output_cost)
    if out_tok > 0:
        io_ratio: float | None = round(prompt_tok / out_tok, 1)
        io_ratio_label = f"{io_ratio}:1"
    else:
        io_ratio, io_ratio_label = None, "∞ (0 out)"
    return FinOpsBreakdown(
        model_id=model_id,
        model_label=model_label,
        provider="Anthropic",
        input_tokens=in_tok,
        output_tokens=out_tok,
        cache_creation_tokens=cw_tok,
        cache_read_tokens=cr_tok,
        total_tokens=prompt_tok + out_tok,
        input_cost_usd=round(input_cost, 8),
        output_cost_usd=round(output_cost, 8),
        total_cost_usd=round(total_cost_usd, 8),
        cost_per_1k_usd=round(total_cost_usd * 1_000, 4),
        monthly_cost_at_100k_usd=round(total_cost_usd * 100_000, 2),
        annual_cost_at_1m_per_mo_usd=round(total_cost_usd * 12_000_000, 2),
        io_ratio=io_ratio,
        io_ratio_label=io_ratio_label,
        output_cost_share_pct=round(output_cost / total_cost_usd * 100, 1) if total_cost_usd > 0 else 0.0,
        output_rate_multiplier="5x output weight",
    )


def rate_card_payload() -> list[dict[str, object]]:
    """Serialize rate card for /api/system/status."""
    return [
        {
            "model_id": r.model_id,
            "label": r.label,
            "provider": r.provider,
            "input_per_1m_usd": r.input_per_1m_usd,
            "output_per_1m_usd": r.output_per_1m_usd,
            "cache_write_per_1m_usd": r.cache_write_per_1m_usd,
            "cache_read_per_1m_usd": r.cache_read_per_1m_usd,
            "output_rate_multiplier": r.output_rate_multiplier,
            "notes": r.notes,
        }
        for r in MODEL_RATES.values()
    ]
