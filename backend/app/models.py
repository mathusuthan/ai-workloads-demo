"""Pydantic API models shared across NovaMart AI Archetypes endpoints."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


SubTaskType = Literal["support_triage", "sku_tagging"]
RungId = Literal["sonnet_naive", "haiku_naive", "haiku_calibrated", "gemini_decision"]
ExecutionMode = Literal["replay", "live"]


class FinOpsBreakdown(BaseModel):
    model_id: str
    model_label: str
    provider: str
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    total_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    cost_per_1k_usd: float
    monthly_cost_at_100k_usd: float
    annual_cost_at_1m_per_mo_usd: float
    io_ratio: float | None = None
    io_ratio_label: str
    output_cost_share_pct: float
    output_rate_multiplier: str


class FieldCheckResult(BaseModel):
    field: str
    expected: Any
    actual: Any = None
    matched: bool


class RungAccuracyEvaluation(BaseModel):
    schema_valid: bool
    matched_count: int
    total_fields: int
    field_accuracy_pct: float
    exact_match: bool
    field_checks: list[FieldCheckResult] = Field(default_factory=list)


class ModelAccuracyRollup(BaseModel):
    rung_id: str
    label: str
    model_id: str
    schema_compliance_pct: float
    fields_matched: int
    fields_total: int
    field_accuracy_pct: float
    exact_items_matched: int
    items_total: int
    exact_match_pct: float
    cost_per_1k_usd: float
    notes: str


class RungExecutionResult(BaseModel):
    rung_id: RungId
    rung_title: str
    badge_text: str
    model_id: str
    provider: str
    status: Literal["ok", "error"] = "ok"
    error_message: str | None = None
    latency_ms: int
    structured_output: dict[str, Any] = Field(default_factory=dict)
    raw_text_preview: str | None = None
    decision_probabilities: dict[str, Any] | None = None
    finops: FinOpsBreakdown
    savings_vs_naive_pct: float = 0.0
    architectural_notes: list[str] = Field(default_factory=list)
    accuracy: RungAccuracyEvaluation | None = None


class PiiRedactionResult(BaseModel):
    contains_pii: bool
    counts_by_type: dict[str, int]
    total_redactions: int
    masked_preview: str


class JevReferenceComparison(BaseModel):
    model_id: str
    model_label: str
    input_rate_per_1m_usd: float
    output_rate_per_1m_usd: float
    estimated_input_tokens: int
    estimated_cost_usd: float
    cost_per_1k_usd: float
    monthly_cost_at_100k_usd: float
    savings_vs_naive_pct: float
    note: str


class Cat1RunRequest(BaseModel):
    preset_id: str | None = None
    custom_input: str | None = None
    sub_task: SubTaskType = "support_triage"
    rungs: list[RungId] = Field(
        default_factory=lambda: ["sonnet_naive", "haiku_naive", "haiku_calibrated", "gemini_decision"]
    )
    mode: ExecutionMode = "replay"


class Cat1RunResponse(BaseModel):
    mode_used: ExecutionMode
    preset_id: str | None
    sub_task: SubTaskType
    input_char_count: int
    estimated_input_tokens: int
    results: list[RungExecutionResult]
    haiku_batch_comparator: FinOpsBreakdown | None = None
    jev_comparator: JevReferenceComparison | None = None
    pii_redaction: PiiRedactionResult
    system1_boundary_note: str
    ground_truth: dict[str, Any] | None = None


class Cat1BatchRequest(BaseModel):
    sub_task: Literal["mixed", "support_triage", "sku_tagging"] = "mixed"
    mode: ExecutionMode = "replay"


class BatchItemResult(BaseModel):
    item_id: str
    title: str
    sub_task: SubTaskType
    input_tokens: int
    haiku_output_tokens: int
    haiku_decision: dict[str, Any]
    gemini_decision: dict[str, Any]
    gemini_confidence: float
    pii_redactions: int
    haiku_latency_ms: int
    gemini_latency_ms: int
    ground_truth: dict[str, Any] = Field(default_factory=dict)
    sonnet_accuracy_pct: float = 0.0
    haiku_naive_accuracy_pct: float = 0.0
    haiku_accuracy_pct: float = 0.0
    gemini_accuracy_pct: float = 0.0
    sonnet_exact: bool = False
    haiku_naive_exact: bool = False
    haiku_exact: bool = False
    gemini_exact: bool = False


class CfoScaleRow(BaseModel):
    tier_id: str
    label: str
    model_id: str
    avg_input_tokens: int
    avg_output_tokens: int
    cost_per_1k_usd: float
    monthly_100k_usd: float
    monthly_1m_usd: float
    annual_12m_usd: float
    savings_vs_naive_pct: float
    scope_note: str
    field_accuracy_pct: float | None = None
    exact_match_pct: float | None = None
    schema_compliance_label: str = ""


class Cat1BatchResponse(BaseModel):
    mode_used: ExecutionMode
    total_items: int
    avg_input_tokens: int
    items: list[BatchItemResult]
    cfo_comparison: list[CfoScaleRow]
    summary_callout: str
    accuracy_rollup: list[ModelAccuracyRollup] = Field(default_factory=list)


# --- Category 2: Generative Synthesis & Drafting ---

Cat2SubTaskType = Literal["exec_synthesis", "regulatory_filing"]
Cat2RungId = Literal["sonnet_unbounded", "sonnet_templated", "haiku_templated"]
Cat2SectionKey = Literal[
    "executive_summary",
    "key_findings",
    "risk_and_compliance_matrix",
    "action_plan",
]
Cat2ModelTier = Literal["claude-sonnet-5-5", "claude-haiku-5-5"]


class Cat2RungResult(BaseModel):
    rung_id: Cat2RungId
    rung_title: str
    badge_text: str
    model_id: str
    provider: str
    status: Literal["ok", "error"] = "ok"
    error_message: str | None = None
    latency_ms: int
    structured_draft: dict[str, Any] = Field(default_factory=dict)
    raw_markdown: str | None = None
    thinking_tokens: int = 0
    finops: FinOpsBreakdown
    savings_vs_unbounded_pct: float = 0.0
    architectural_notes: list[str] = Field(default_factory=list)


class Cat2RunRequest(BaseModel):
    preset_id: str | None = None
    custom_input: str | None = None
    sub_task: Cat2SubTaskType = "exec_synthesis"
    rungs: list[Cat2RungId] = Field(
        default_factory=lambda: ["sonnet_unbounded", "sonnet_templated", "haiku_templated"]
    )
    mode: ExecutionMode = "replay"


class Cat2RunResponse(BaseModel):
    mode_used: ExecutionMode
    preset_id: str | None
    sub_task: Cat2SubTaskType
    input_char_count: int
    estimated_input_tokens: int
    results: list[Cat2RungResult]
    haiku_batch_comparator: FinOpsBreakdown | None = None
    output_tax_callout: str


class Cat2SectionRegenRequest(BaseModel):
    preset_id: str | None = None
    custom_input: str | None = None
    sub_task: Cat2SubTaskType = "exec_synthesis"
    section_key: Cat2SectionKey
    current_section: Any = None
    reviewer_instruction: str = ""
    model_tier: Cat2ModelTier = "claude-sonnet-5-5"
    mode: ExecutionMode = "replay"


class HitlCostComparison(BaseModel):
    surgical_finops: FinOpsBreakdown
    naive_full_reprompt_finops: FinOpsBreakdown
    revision_savings_pct: float
    tokens_avoided: int
    explanation: str


class Cat2SectionRegenResponse(BaseModel):
    mode_used: ExecutionMode
    preset_id: str | None
    section_key: Cat2SectionKey
    model_used: str
    latency_ms: int
    updated_section: Any
    finops_comparison: HitlCostComparison


# --- Category 3: Multi-Turn Conversational Assistants (IT & HR Service Desk) ---

Cat3UseCaseType = Literal["it_hr_service_desk"]
Cat3RungId = Literal["naive_full_history", "prefix_cached_history", "prefix_cached_summarized"]


class Cat3TurnResult(BaseModel):
    turn_number: int
    topic_tag: str
    user_message: str
    assistant_message: str
    latency_ms: int
    finops: FinOpsBreakdown
    cumulative_cost_usd: float
    cumulative_warm_cost_usd: float
    active_history_turns: int
    compacted_turns_count: int
    memory_summary_snapshot: dict[str, Any] | None = None
    compaction_triggered_before_turn: bool = False
    compaction_finops: FinOpsBreakdown | None = None
    compaction_latency_ms: int = 0
    estimated_active_context_tokens: int = 0


class Cat3RungSummary(BaseModel):
    rung_id: Cat3RungId
    rung_title: str
    badge_text: str
    pattern: str
    model_id: str
    provider: str = "Anthropic"
    status: Literal["ok", "error"] = "ok"
    error_message: str | None = None
    turns: list[Cat3TurnResult] = Field(default_factory=list)
    total_uncached_input_tokens: int
    total_cache_creation_tokens: int
    total_cache_read_tokens: int
    total_output_tokens: int
    summarizer_calls: int = 0
    summarizer_input_tokens: int = 0
    summarizer_output_tokens: int = 0
    summarizer_cost_usd: float = 0.0
    total_session_cost_usd: float
    warm_fleet_session_cost_usd: float
    cost_per_1k_sessions_usd: float
    warm_cost_per_1k_sessions_usd: float
    savings_vs_naive_pct: float = 0.0
    warm_savings_vs_naive_pct: float = 0.0
    savings_vs_cached_history_pct: float = 0.0
    warm_savings_vs_cached_history_pct: float = 0.0
    total_latency_ms: int = 0
    architectural_notes: list[str] = Field(default_factory=list)


class Cat3RunRequest(BaseModel):
    preset_id: str = "desk-01"
    use_case: Cat3UseCaseType = "it_hr_service_desk"
    rungs: list[Cat3RungId] = Field(
        default_factory=lambda: [
            "naive_full_history",
            "prefix_cached_history",
            "prefix_cached_summarized",
        ]
    )
    mode: ExecutionMode = "replay"


class Cat3RunResponse(BaseModel):
    mode_used: ExecutionMode
    preset_id: str
    use_case: Cat3UseCaseType = "it_hr_service_desk"
    title: str
    employee_profile: dict[str, Any]
    handbook_char_count: int
    approx_handbook_tokens: int
    results: list[Cat3RungSummary]
    session_callout: str


class Cat3ChatTurnEntry(BaseModel):
    turn_number: int
    user_message: str
    assistant_message: str


class Cat3ChatTurnRequest(BaseModel):
    preset_id: str = "desk-01"
    rung_id: Cat3RungId = "prefix_cached_summarized"
    user_message: str
    prior_turns: list[Cat3ChatTurnEntry] = Field(default_factory=list)
    memory_summary: dict[str, Any] | None = None
    mode: ExecutionMode = "live"


class Cat3ChatTurnResponse(BaseModel):
    mode_used: ExecutionMode
    preset_id: str
    rung_id: Cat3RungId
    turn_result: Cat3TurnResult
    updated_verbatim_turns: list[Cat3ChatTurnEntry] = Field(default_factory=list)
    updated_memory_summary: dict[str, Any] | None = None
