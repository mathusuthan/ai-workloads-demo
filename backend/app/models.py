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


class Cat2Count(BaseModel):
    hits: int
    total: int


class Cat2MissedFact(BaseModel):
    description: str
    tier: Literal["core", "detail"]


class Cat2NumberItem(BaseModel):
    text: str
    context: str
    # Judge's majority verdict (derived_correct / derived_incorrect / not_in_source_unverifiable / not_a_claim /
    # no_majority); None when not graded (live mode).
    verdict: str | None = None


class Cat2Numbers(BaseModel):
    numeric_tokens: int
    not_in_source: int
    verdicts: dict[str, int] | None = None
    items: list[Cat2NumberItem] = Field(default_factory=list)


class Cat2DimensionScore(BaseModel):
    mean: float
    scores: list[int] = Field(default_factory=list)


class Cat2DraftError(BaseModel):
    claim_quote: str
    problem: str
    source_quote: str | None = None  # None = the judge found nothing in the source supporting the claim
    severity: Literal["material", "minor"]
    passes_reporting: int


class Cat2ActionItemCheck(BaseModel):
    """Templated action items whose owner or time window the judge reported as an error."""

    total: int
    flagged: int
    flagged_serious: int


class Cat2HeadToHeadOrder(BaseModel):
    shown_first: Cat2RungId
    winner: str | None = None  # a rung id, "tie", or None when the call is missing


class Cat2HeadToHead(BaseModel):
    opponent: Cat2RungId
    results: list[Cat2HeadToHeadOrder] = Field(default_factory=list)


class Cat2RungQuality(BaseModel):
    source: Literal["replay_judged", "live_deterministic"]
    preset_id: str | None = None
    keys_version: str | None = None
    core_facts: Cat2Count | None = None
    detail_facts: Cat2Count | None = None
    missed_facts: list[Cat2MissedFact] = Field(default_factory=list)
    numbers: Cat2Numbers | None = None
    rubric: dict[str, Cat2DimensionScore] | None = None
    serious_errors: int | None = None
    minor_errors: int | None = None
    errors: list[Cat2DraftError] | None = None
    action_items: Cat2ActionItemCheck | None = None
    head_to_head: list[Cat2HeadToHead] | None = None
    judge_model: str | None = None
    passes: int | None = None
    judge_unavailable_reason: str | None = None


class Cat2PooledDimension(BaseModel):
    mean: float | None = None
    min: float | None = None
    max: float | None = None
    n: int = 0


class Cat2WinRecord(BaseModel):
    wins: int
    losses: int
    ties: int


class Cat2PortfolioRung(BaseModel):
    rung_id: Cat2RungId
    drafts: int
    core_facts: Cat2Count
    detail_facts: Cat2Count
    rubric: dict[str, Cat2PooledDimension]
    serious_errors: int
    minor_errors: int
    numbers: Cat2Numbers
    action_items: Cat2ActionItemCheck | None = None
    cost_per_1k_docs_usd: float | None = None
    output_tokens_mean: float | None = None
    head_to_head: dict[str, Cat2WinRecord] = Field(default_factory=dict)


class Cat2PairwiseBlock(BaseModel):
    wins: dict[str, dict[str, int]]
    ties: dict[str, int]
    position_consistency: dict[str, int]


class Cat2QualityPortfolio(BaseModel):
    schema_version: int
    source: str
    keys_version: str | None = None
    judge_model: str
    passes_per_draft: int
    drafts_per_cell: int
    documents: list[str]
    calls: dict[str, int]
    dimensions: list[str]
    rungs: list[Cat2PortfolioRung]
    pairwise: dict[str, Cat2PairwiseBlock]


class Cat2FieldClasses(BaseModel):
    supported: int
    not_stated: int
    unsupported: int


class Cat2TemplateFixCell(BaseModel):
    arm: Literal["template_original", "template_not_stated"]
    model_key: Literal["sonnet", "haiku"]
    drafts: int
    action_items: int
    owner: Cat2FieldClasses
    time_window: Cat2FieldClasses
    owner_not_stated_by_preset: dict[str, int] = Field(default_factory=dict)
    owner_supported_by_preset: dict[str, int] = Field(default_factory=dict)
    serious_per_draft: float | None = None
    minor_per_draft: float | None = None
    serious_total: int | None = None
    flagged_items_total: int | None = None
    rubric: dict[str, float | None] = Field(default_factory=dict)
    core_facts: Cat2Count
    detail_facts: Cat2Count
    cost_per_1k_docs_usd: float | None = None
    output_tokens_mean: float | None = None
    truncated: int = 0


class Cat2FixRecord(BaseModel):
    wins: int
    losses: int
    ties: int


class Cat2FixHeadToHead(BaseModel):
    overall: Cat2FixRecord
    accuracy: Cat2FixRecord
    usefulness_to_reader: Cat2FixRecord
    calls: int
    position_consistency: dict[str, int] = Field(default_factory=dict)


class Cat2FixComparison(BaseModel):
    all: Cat2FixHeadToHead | None = None
    by_model: dict[str, Cat2FixHeadToHead] = Field(default_factory=dict)


class Cat2FixActionItem(BaseModel):
    milestone: str | None = None
    owner: str | None = None
    time_window: str | None = None
    owner_class: str
    window_class: str


class Cat2FixExampleSlot(BaseModel):
    slot: int
    original: Cat2FixActionItem
    not_stated: Cat2FixActionItem


class Cat2FixExample(BaseModel):
    rule: str
    preset_id: str
    model_key: str
    repeat_index: int
    items: list[Cat2FixExampleSlot] = Field(default_factory=list)


class Cat2TemplateFix(BaseModel):
    """Measured follow-up (replays/cat2_not_stated_summary.json): the template plus one sentence permitting
    "Not stated in source". Shown beside the app's rungs; the app itself still uses the original template."""

    schema_version: int
    source: str
    app_template: str
    added_instruction: str
    not_stated_literal: str
    keys_version: str | None = None
    judge_model: str
    judge_passes_per_draft: int
    counts: dict[str, int]
    field_rules: list[str] = Field(default_factory=list)
    cells: list[Cat2TemplateFixCell]
    head_to_head: dict[str, Cat2FixComparison]
    example: Cat2FixExample | None = None


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
    stop_reason: str | None = None  # live: the API's value; replay: the stored value
    quality: Cat2RungQuality | None = None


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
    quality_portfolio: Cat2QualityPortfolio | None = None
    template_fix: Cat2TemplateFix | None = None


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


class Cat3Measure(BaseModel):
    """hits/total with an optional rate and Wilson 95% interval (None when total == 0 or not computed)."""

    hits: int
    total: int
    rate: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None


class Cat3ProbeResult(BaseModel):
    probe_id: str
    origin_turn: int
    question: str
    expected: str
    answer: str
    hit: bool
    outcome: Literal["correct", "declined", "wrong"]


class Cat3RungQuality(BaseModel):
    """Deterministic answer-key scores for one session on one rung (app/data/cat3_quality_keys.json)."""

    keys_version: str | None = None
    turn_recall: Cat3Measure
    ledger_recall: Cat3Measure
    ledger_by_origin: dict[str, Cat3Measure] = Field(default_factory=dict)
    probe_accuracy: Cat3Measure | None = None
    probes: list[Cat3ProbeResult] | None = None
    probes_unavailable_reason: str | None = None


class Cat3PortfolioCell(BaseModel):
    runs: int
    turn_recall: Cat3Measure
    ledger_recall: Cat3Measure
    ledger_by_origin: dict[str, Cat3Measure] = Field(default_factory=dict)
    probe_accuracy: Cat3Measure
    session_billed_usd_mean: float | None = None
    session_warm_usd_mean: float | None = None
    session_billed_per_1k_usd: float | None = None
    session_warm_per_1k_usd: float | None = None
    probe_phase_billed_usd_mean: float | None = None


class Cat3PortfolioRung(Cat3PortfolioCell):
    rung_id: Cat3RungId
    by_preset: dict[str, Cat3PortfolioCell] = Field(default_factory=dict)


class Cat3QualityPortfolio(BaseModel):
    """Pooled quality-rerun picture (replays/cat3_quality_summary.json)."""

    schema_version: int = 1
    source: str
    source_file: str | None = None
    keys_version: str | None = None
    runs: int
    error_records: int = 0
    repeats: int
    sessions: list[str] = Field(default_factory=list)
    probes_per_session: dict[str, int] = Field(default_factory=dict)
    matrix_complete: bool = True
    rungs: list[Cat3PortfolioRung] = Field(default_factory=list)


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
    quality: Cat3RungQuality | None = None


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
    quality_portfolio: Cat3QualityPortfolio | None = None


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


# --- Category 4: Multi-Doc RAG & Deep Ingestion (Supplier Deal-Room Due Diligence) ---

Cat4UseCaseType = Literal["supplier_msa_due_diligence"]
Cat4RungId = Literal[
    "naive_full_corpus",
    "cached_full_corpus_citations",
    "hybrid_rag_rerank_citations",
]


class Cat4CitationSpan(BaseModel):
    cite_number: int
    doc_id: str
    document_title: str
    clause_ref: str = ""
    cited_text: str
    start_char_index: int
    end_char_index: int


class Cat4AnswerSegment(BaseModel):
    text: str
    cite_numbers: list[int] = Field(default_factory=list)


class Cat4RetrievalChunkTrace(BaseModel):
    chunk_id: str
    doc_id: str
    doc_title: str
    clause_ref: str
    section_heading: str
    char_count: int
    approx_tokens: int
    bm25_score: float
    bm25_rank: int
    stage: Literal["selected_by_reranker", "pruned_by_reranker", "pruned_by_bm25"]
    reranker_score: int | None = None
    reranker_rationale: str | None = None
    is_expected_gold: bool = False


class Cat4Measure(BaseModel):
    """hits/total with an optional rate and Wilson 95% interval (None when total == 0 or not computed)."""

    hits: int
    total: int
    rate: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None


class Cat4GraderError(BaseModel):
    claim_quote: str
    problem: str
    source_quote: str


class Cat4GraderVerdict(BaseModel):
    """Blind grader's verdict on this exact answer (recorded in the quality rerun; never run live)."""

    grader_model: str
    correctness: int
    completeness: int
    correctness_justification: str = ""
    completeness_justification: str = ""
    answers_the_question: Literal["yes", "partly", "no"]
    material_errors: list[Cat4GraderError] = Field(default_factory=list)
    minor_error_count: int = 0


class Cat4QuestionQuality(BaseModel):
    question_id: str
    question_number: int
    key_facts: Cat4Measure
    missed_facts: list[str] = Field(default_factory=list)
    citations_requested: bool
    citation_count: int | None = None
    zero_citations: bool | None = None
    citations_at_expected: Cat4Measure | None = None
    expected_clause_recall: Cat4Measure | None = None
    retrieval_recall: Cat4Measure | None = None
    stop_reason: str | None = None
    grader: Cat4GraderVerdict | None = None


class Cat4AuditQuality(BaseModel):
    questions: int
    key_facts: Cat4Measure
    key_facts_supplier_specific: Cat4Measure
    citations_requested: bool
    citations_at_expected: Cat4Measure | None = None
    expected_clause_recall: Cat4Measure | None = None
    zero_citation_answers: int | None = None
    retrieval_recall: Cat4Measure | None = None
    judged: int = 0
    correctness_mean: float | None = None
    completeness_mean: float | None = None
    material_errors: int | None = None
    answers_with_material_error: int | None = None


class Cat4RungQuality(BaseModel):
    """Deterministic answer-key scores (app/data/cat4_quality_keys.json) + the recorded blind grade per question."""

    keys_version: str | None = None
    audit: Cat4AuditQuality
    questions: list[Cat4QuestionQuality] = Field(default_factory=list)
    grader_unavailable_reason: str | None = None


class Cat4PortfolioCell(BaseModel):
    rung_id: str
    runnable_in_app: bool
    scale: int
    sessions: int
    answers: int
    fact_recall: Cat4Measure
    fact_recall_supplier_specific: Cat4Measure
    fact_recall_non_specific: Cat4Measure
    citations_requested: bool
    citations_per_answer_mean: float | None = None
    zero_citation_answers: Cat4Measure | None = None
    expected_chunk_recall: Cat4Measure | None = None
    citations_at_expected: Cat4Measure | None = None
    cited_support: Cat4Measure | None = None
    contaminated_answers: Cat4Measure
    value_contaminated_answers: Cat4Measure
    value_contaminated_unattributed_answers: Cat4Measure | None = None
    citation_contaminated_answers: Cat4Measure
    exposure_answers: Cat4Measure | None = None
    recall_after_bm25: Cat4Measure | None = None
    recall_after_rerank: Cat4Measure | None = None
    distractors_selected: Cat4Measure | None = None
    backfilled: int | None = None
    invalid_picks: int | None = None
    judged: int = 0
    correctness_mean: float | None = None
    completeness_mean: float | None = None
    material_errors: int | None = None
    minor_errors: int | None = None
    answers_with_material_error: Cat4Measure | None = None
    answers_the_question: dict[str, int] = Field(default_factory=dict)
    cost_per_question_billed_usd: float | None = None
    cost_per_question_cold_usd: float | None = None
    cost_per_question_warm_usd: float | None = None
    cost_per_question_billed_sonnet_usd: float | None = None
    cost_per_question_billed_haiku_usd: float | None = None
    cache_write_premium_usd: float = 0.0


class Cat4BreakEven(BaseModel):
    a: str
    b: str
    premium_a_usd: float
    per_question_a_usd: float
    premium_b_usd: float
    per_question_b_usd: float
    n_star: float | None = None
    questions: int | None = None
    verdict: str


class Cat4PortfolioQuestion(BaseModel):
    rung_id: str
    scale: int
    question: str
    answers: int
    fact_recall: Cat4Measure
    citations_per_answer_mean: float | None = None
    zero_citation_answers: Cat4Measure | None = None
    citations_at_expected: Cat4Measure | None = None
    expected_chunk_recall: Cat4Measure | None = None
    recall_after_rerank: Cat4Measure | None = None
    correctness_mean: float | None = None
    completeness_mean: float | None = None
    material_errors: int | None = None
    cost_per_question_billed_usd: float | None = None


class Cat4GoldenMapped(BaseModel):
    selection_rule: str
    run_ids: dict[str, str] = Field(default_factory=dict)
    questions: list[Cat4PortfolioQuestion] = Field(default_factory=list)


class Cat4QualityPortfolio(BaseModel):
    """Pooled quality-rerun picture (replays/cat4_quality_summary.json): 4 versions x 2 corpus sizes."""

    schema_version: int = 1
    source: str
    source_file: str | None = None
    judgements_file: str | None = None
    keys_version: str | None = None
    judge_model: str | None = None
    judge_passes: int = 1
    scope_line: str | None = None
    record_count: int
    ok_sessions: int
    error_records: int = 0
    superseded_records: int = 0
    answers_scored: int
    answers_judged: int
    sessions_per_cell: int | None = None
    questions_per_session: int
    scales: list[int] = Field(default_factory=list)
    corpus: dict[str, dict[str, int]] = Field(default_factory=dict)
    synth_max_tokens: int | None = None
    matrix_complete: bool = True
    cells: list[Cat4PortfolioCell] = Field(default_factory=list)
    break_even: dict[str, list[Cat4BreakEven]] = Field(default_factory=dict)
    golden_mapped: Cat4GoldenMapped | None = None


class Cat4QueryResult(BaseModel):
    question_id: str
    question_number: int
    topic_tag: str
    question: str
    question_as_asked: str | None = None
    stop_reason: str | None = None
    expected_doc_ids: list[str] = Field(default_factory=list)
    expected_chunk_ids: list[str] = Field(default_factory=list)
    answer_markdown: str
    segments: list[Cat4AnswerSegment] = Field(default_factory=list)
    citations: list[Cat4CitationSpan] = Field(default_factory=list)
    cited_doc_ids: list[str] = Field(default_factory=list)
    doc_citation_coverage_pct: float = 0.0
    latency_ms: int
    finops: FinOpsBreakdown
    cold_query_cost_usd: float
    warm_query_cost_usd: float
    reranker_finops: FinOpsBreakdown | None = None
    reranker_latency_ms: int = 0
    reranker_stop_reason: str | None = None
    retrieval_funnel: list[Cat4RetrievalChunkTrace] = Field(default_factory=list)
    bm25_recall_pct: float | None = None
    reranker_recall_pct: float | None = None
    context_tokens_sent: int = 0
    context_reduction_pct: float = 0.0


class Cat4RungSummary(BaseModel):
    rung_id: Cat4RungId
    rung_title: str
    badge_text: str
    pattern: str
    model_id: str
    reranker_model_id: str | None = None
    provider: str = "Anthropic"
    status: Literal["ok", "error"] = "ok"
    error_message: str | None = None
    queries: list[Cat4QueryResult] = Field(default_factory=list)
    total_uncached_input_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_output_tokens: int = 0
    reranker_calls: int = 0
    reranker_input_tokens: int = 0
    reranker_output_tokens: int = 0
    reranker_cost_usd: float = 0.0
    cold_audit_cost_usd: float = 0.0
    warm_audit_cost_usd: float = 0.0
    cost_per_1k_audits_cold_usd: float = 0.0
    cost_per_1k_audits_warm_usd: float = 0.0
    single_query_cold_per_1k_usd: float = 0.0
    savings_vs_naive_cold_pct: float = 0.0
    savings_vs_naive_warm_pct: float = 0.0
    avg_citations_per_query: float = 0.0
    avg_doc_coverage_pct: float = 0.0
    avg_reranker_recall_pct: float | None = None
    total_latency_ms: int = 0
    architectural_notes: list[str] = Field(default_factory=list)
    quality: Cat4RungQuality | None = None
    quality_unavailable_reason: str | None = None


class Cat4RunRequest(BaseModel):
    preset_id: str = "audit-01"
    use_case: Cat4UseCaseType = "supplier_msa_due_diligence"
    rungs: list[Cat4RungId] = Field(
        default_factory=lambda: [
            "naive_full_corpus",
            "cached_full_corpus_citations",
            "hybrid_rag_rerank_citations",
        ]
    )
    mode: ExecutionMode = "replay"


class Cat4RunResponse(BaseModel):
    mode_used: ExecutionMode
    preset_id: str
    use_case: Cat4UseCaseType = "supplier_msa_due_diligence"
    title: str
    deal_room_profile: dict[str, Any]
    total_docs: int
    total_chunks: int
    corpus_char_count: int
    approx_corpus_tokens: int
    results: list[Cat4RungSummary]
    rag_callout: str
    billing_note: str | None = None
    quality_portfolio: Cat4QualityPortfolio | None = None


class Cat4AdhocQueryRequest(BaseModel):
    preset_id: str = "audit-01"
    question: str
    rungs: list[Cat4RungId] = Field(
        default_factory=lambda: [
            "naive_full_corpus",
            "cached_full_corpus_citations",
            "hybrid_rag_rerank_citations",
        ]
    )
    mode: ExecutionMode = "live"


class Cat4AdhocQueryResponse(BaseModel):
    mode_used: ExecutionMode
    preset_id: str
    question: str
    results: list[Cat4RungSummary]
    quality_portfolio: Cat4QualityPortfolio | None = None


# --- Category 5: Autonomous Process Orchestration (3-Way ERP Invoice Agent) ---

Cat5UseCaseType = Literal["invoice_3way_reconciliation"]
Cat5RungId = Literal[
    "unbounded_sonnet_loop",
    "bounded_sonnet_cached_gate",
    "hybrid_haiku_sonnet_governed",
]


class Cat5ToolCallTrace(BaseModel):
    tool_use_id: str
    tool_name: str
    tool_input: dict[str, Any] = Field(default_factory=dict)
    sql_executed: str = ""
    tables_touched: list[str] = Field(default_factory=list)
    is_optimal_call: bool = True
    result_preview: str = ""
    gate_snapshot: dict[str, Any] | None = None


class Cat5LoopStep(BaseModel):
    step_number: int
    model_id: str
    escalated_from_haiku: bool = False
    stop_reason: str
    assistant_thought: str = ""
    tool_calls: list[Cat5ToolCallTrace] = Field(default_factory=list)
    latency_ms: int
    finops: FinOpsBreakdown
    cumulative_cold_cost_usd: float
    cumulative_warm_cost_usd: float


class Cat5CommittedVoucher(BaseModel):
    voucher_id: str
    invoice_id: str
    po_id: str
    decision: str
    authorized_net_principal_inr: float
    authorized_gst_payout_inr: float
    gst_escrow_holdback_inr: float
    debit_note_deduction_inr: float
    gate_verified: bool = False
    audit_summary: str = ""


class Cat5EvaluationResult(BaseModel):
    voucher_committed: bool
    matched_fields: int
    total_fields: int
    field_accuracy_pct: float
    exact_match: bool
    evidence_recall_pct: float
    tool_precision_pct: float
    within_step_budget: bool
    gate_verified: bool
    field_checks: list[FieldCheckResult] = Field(default_factory=list)


class Cat5RungResult(BaseModel):
    rung_id: Cat5RungId
    rung_title: str
    badge_text: str
    pattern: str
    primary_model_id: str
    status: Literal["ok", "error"] = "ok"
    error_message: str | None = None
    max_step_budget: int
    steps_used: int
    haiku_steps: int = 0
    sonnet_steps: int = 0
    escalated_to_sonnet: bool = False
    circuit_breaker_triggered: bool = False
    steps: list[Cat5LoopStep] = Field(default_factory=list)
    total_uncached_input_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_output_tokens: int = 0
    cold_run_cost_usd: float = 0.0
    warm_run_cost_usd: float = 0.0
    cost_per_1k_invoices_cold_usd: float = 0.0
    cost_per_1k_invoices_warm_usd: float = 0.0
    savings_vs_naive_cold_pct: float = 0.0
    savings_vs_naive_warm_pct: float = 0.0
    total_latency_ms: int = 0
    final_readout: str = ""
    committed_voucher: Cat5CommittedVoucher | None = None
    evaluation: Cat5EvaluationResult | None = None
    architectural_notes: list[str] = Field(default_factory=list)


class Cat5PortfolioRungRollup(BaseModel):
    rung_id: Cat5RungId
    label: str
    model_routing_summary: str
    invoices_evaluated: int
    avg_steps: float
    avg_prompt_tokens: int
    avg_output_tokens: int
    fields_matched: int
    fields_total: int
    adjudication_accuracy_pct: float
    exact_vouchers_matched: int
    avg_evidence_recall_pct: float
    avg_tool_precision_pct: float
    avg_cost_per_1k_cold_usd: float
    avg_cost_per_1k_warm_usd: float
    savings_vs_naive_cold_pct: float


class Cat5RunRequest(BaseModel):
    preset_id: str = "inv-01"
    use_case: Cat5UseCaseType = "invoice_3way_reconciliation"
    rungs: list[Cat5RungId] = Field(
        default_factory=lambda: [
            "unbounded_sonnet_loop",
            "bounded_sonnet_cached_gate",
            "hybrid_haiku_sonnet_governed",
        ]
    )
    mode: ExecutionMode = "replay"


class Cat5RunResponse(BaseModel):
    mode_used: ExecutionMode
    preset_id: str
    use_case: Cat5UseCaseType = "invoice_3way_reconciliation"
    title: str
    invoice_id: str
    po_id: str
    vendor_name: str
    fc_hub: str
    policy_char_count: int
    approx_policy_tokens: int
    ground_truth: dict[str, Any]
    results: list[Cat5RungResult]
    portfolio_scorecard: list[Cat5PortfolioRungRollup] = Field(default_factory=list)
    orchestration_callout: str


# --- Category 6: Multi-Agent Swarms & Auto Eng (Checkout CI Swarm + CpO) ---

Cat6UseCaseType = Literal["checkout_ci_self_healing_swarm"]
Cat6RungId = Literal[
    "unisolated_broadcast_swarm",
    "isolated_cached_sonnet_swarm",
    "tiered_hybrid_cpo_swarm",
]


class Cat6AgentTurnTrace(BaseModel):
    step_number: int
    agent_role: str
    agent_label: str
    model_id: str
    context_mode: Literal["shared_omnibus_bus", "isolated_prefix_cached"]
    attempt: int = 1
    latency_ms: int
    finops: FinOpsBreakdown
    cumulative_cold_cost_usd: float
    cumulative_warm_cost_usd: float
    prompt_preview: str = ""
    output_preview: str = ""


class Cat6SandboxCheckResult(BaseModel):
    check_id: str
    category: Literal["ci_unit", "adversarial", "ast"]
    name: str
    passed: bool
    detail: str


class Cat6SandboxReport(BaseModel):
    total_checks: int
    passed_checks: int
    ci_unit_passed: int
    adversarial_passed: int
    ast_passed: int
    verified_outcome: bool
    execution_ms: int
    checks: list[Cat6SandboxCheckResult] = Field(default_factory=list)
    unified_diff: str = ""


class Cat6RungResult(BaseModel):
    rung_id: Cat6RungId
    rung_title: str
    badge_text: str
    pattern: str
    primary_model_id: str
    status: Literal["ok", "error"] = "ok"
    error_message: str | None = None
    agent_turns: list[Cat6AgentTurnTrace] = Field(default_factory=list)
    retries_used: int = 0
    haiku_turns: int = 0
    sonnet_turns: int = 0
    total_uncached_input_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_output_tokens: int = 0
    cold_run_cost_usd: float = 0.0
    warm_run_cost_usd: float = 0.0
    cost_per_1k_runs_cold_usd: float = 0.0
    cost_per_1k_runs_warm_usd: float = 0.0
    # Cost per Verified Outcome; None when the run produced no verified outcome (CpO is undefined, not $0).
    cpo_cold_per_1k_usd: float | None = None
    cpo_warm_per_1k_usd: float | None = None
    savings_vs_naive_cold_pct: float = 0.0
    savings_vs_naive_warm_pct: float = 0.0
    total_latency_ms: int = 0
    patched_code: str = ""
    final_signoff_memo: str = ""
    sandbox_report: Cat6SandboxReport | None = None
    architectural_notes: list[str] = Field(default_factory=list)


class Cat6PortfolioRungRollup(BaseModel):
    rung_id: Cat6RungId
    label: str
    routing_summary: str
    prs_evaluated: int
    verified_outcomes_count: int
    verified_outcome_rate_pct: float
    checks_passed_total: int
    checks_total: int
    avg_prompt_tokens: int
    avg_output_tokens: int
    daily_tokens_per_dev_at_25_runs: int
    avg_cpr_cold_per_1k_usd: float
    avg_cpr_warm_per_1k_usd: float
    # None when the rung has zero verified outcomes (CpO undefined) or, for savings, when either side is undefined.
    portfolio_cpo_cold_per_1k_usd: float | None
    portfolio_cpo_warm_per_1k_usd: float | None
    cpo_savings_vs_naive_cold_pct: float | None


class Cat6RunRequest(BaseModel):
    preset_id: str = "inc-01"
    use_case: Cat6UseCaseType = "checkout_ci_self_healing_swarm"
    rungs: list[Cat6RungId] = Field(
        default_factory=lambda: [
            "unisolated_broadcast_swarm",
            "isolated_cached_sonnet_swarm",
            "tiered_hybrid_cpo_swarm",
        ]
    )
    mode: ExecutionMode = "replay"


class Cat6RunResponse(BaseModel):
    mode_used: ExecutionMode
    preset_id: str
    use_case: Cat6UseCaseType = "checkout_ci_self_healing_swarm"
    title: str
    pr_id: str
    service_name: str
    target_file: str
    use_case_tag: str
    shared_repo_char_count: int
    approx_shared_repo_tokens: int
    results: list[Cat6RungResult]
    portfolio_scorecard: list[Cat6PortfolioRungRollup] = Field(default_factory=list)
    swarm_callout: str
