export type SubTaskType = 'support_triage' | 'sku_tagging'
export type RungId = 'sonnet_naive' | 'haiku_naive' | 'haiku_calibrated' | 'gemini_decision'
export type ExecutionMode = 'replay' | 'live'

export interface ArchetypeSpec {
  id: number
  slug: string
  category_label: string
  title: string
  novamart_product_name: string
  autonomy_tier: number
  autonomy_tier_label: string
  token_band: string
  matrix_x_band: number
  matrix_y_tier: number
  input_profile: string
  output_profile: string
  dynamics: string
  color_hex: string
  deck_use_cases: string[]
  architectural_lever: string
  novamart_story: string
  status: 'live' | 'coming_soon'
  blog_post_number: number
}

export interface AutonomyTierSpec {
  tier: number
  short: string
  label: string
}

export interface TokenBandSpec {
  band: number
  code: string
  range: string
  subtitle: string
}

export interface FinOpsRule {
  rule_number: number
  tiers: string
  title: string
  bullets: string[]
  impact: string
  accent: string
}

export interface ArchetypesCatalogResponse {
  enterprise: {
    company_name: string
    tagline: string
    series_title: string
    deck_attribution: string
  }
  autonomy_tiers: AutonomyTierSpec[]
  token_bands: TokenBandSpec[]
  archetypes: ArchetypeSpec[]
  finops_rules: FinOpsRule[]
}

export interface RateCardEntry {
  model_id: string
  label: string
  provider: string
  input_per_1m_usd: number
  output_per_1m_usd: number
  cache_read_per_1m_usd: number
  output_rate_multiplier: string
  notes: string
}

export interface SystemStatusResponse {
  default_mode: ExecutionMode
  server_keys: {
    anthropic_configured: boolean
    gemini_configured: boolean
  }
  author_passcode_required: boolean
  daily_budget_usd: number
  daily_spend_usd: number
  daily_remaining_usd: number
  rate_card: RateCardEntry[]
}

export interface Cat1Preset {
  id: string
  sub_task: SubTaskType
  title: string
  subtitle: string
  channel: string
  approx_tokens: number
  payload: string
}

export interface Cat1PresetsResponse {
  presets: Cat1Preset[]
  schemas: Record<SubTaskType, Record<string, unknown>>
  decision_questions: Record<SubTaskType, Record<string, unknown>>
  code_snippets: Record<RungId, string>
}

export interface FinOpsBreakdown {
  model_id: string
  model_label: string
  provider: string
  input_tokens: number
  output_tokens: number
  cache_creation_tokens: number
  cache_read_tokens: number
  total_tokens: number
  input_cost_usd: number
  output_cost_usd: number
  total_cost_usd: number
  cost_per_1k_usd: number
  monthly_cost_at_100k_usd: number
  annual_cost_at_1m_per_mo_usd: number
  io_ratio: number | null
  io_ratio_label: string
  output_cost_share_pct: number
  output_rate_multiplier: string
}

export interface DecisionProbEntry {
  type: 'choice' | 'score' | 'noul'
  value: string | number | boolean
  confidence: number
  p_true?: number
  probabilities?: Record<string, number>
  legend?: Record<string, string>
}

export interface FieldCheckResult {
  field: string
  expected: unknown
  actual: unknown
  matched: boolean
}

export interface RungAccuracyEvaluation {
  schema_valid: boolean
  matched_count: number
  total_fields: number
  field_accuracy_pct: number
  exact_match: boolean
  field_checks: FieldCheckResult[]
}

export interface ModelAccuracyRollup {
  rung_id: string
  label: string
  model_id: string
  schema_compliance_pct: number
  fields_matched: number
  fields_total: number
  field_accuracy_pct: number
  exact_items_matched: number
  items_total: number
  exact_match_pct: number
  cost_per_1k_usd: number
  notes: string
}

export interface RungExecutionResult {
  rung_id: RungId
  rung_title: string
  badge_text: string
  model_id: string
  provider: string
  status: 'ok' | 'error'
  error_message: string | null
  latency_ms: number
  structured_output: Record<string, unknown>
  raw_text_preview: string | null
  decision_probabilities: Record<string, DecisionProbEntry> | null
  finops: FinOpsBreakdown
  savings_vs_naive_pct: number
  architectural_notes: string[]
  accuracy?: RungAccuracyEvaluation | null
}

export interface PiiRedactionResult {
  contains_pii: boolean
  counts_by_type: Record<string, number>
  total_redactions: number
  masked_preview: string
}

export interface JevReferenceComparison {
  model_id: string
  model_label: string
  input_rate_per_1m_usd: number
  output_rate_per_1m_usd: number
  estimated_input_tokens: number
  estimated_cost_usd: number
  cost_per_1k_usd: number
  monthly_cost_at_100k_usd: number
  savings_vs_naive_pct: number
  note: string
}

export interface Cat1RunResponse {
  mode_used: ExecutionMode
  preset_id: string | null
  sub_task: SubTaskType
  input_char_count: number
  estimated_input_tokens: number
  results: RungExecutionResult[]
  haiku_batch_comparator: FinOpsBreakdown | null
  jev_comparator: JevReferenceComparison | null
  pii_redaction: PiiRedactionResult
  system1_boundary_note: string
  ground_truth?: Record<string, unknown> | null
}

export interface BatchItemResult {
  item_id: string
  title: string
  sub_task: SubTaskType
  input_tokens: number
  haiku_output_tokens: number
  haiku_decision: Record<string, unknown>
  gemini_decision: Record<string, unknown>
  gemini_confidence: number
  pii_redactions: number
  haiku_latency_ms: number
  gemini_latency_ms: number
  ground_truth?: Record<string, unknown>
  sonnet_accuracy_pct?: number
  haiku_naive_accuracy_pct?: number
  haiku_accuracy_pct?: number
  gemini_accuracy_pct?: number
  sonnet_exact?: boolean
  haiku_naive_exact?: boolean
  haiku_exact?: boolean
  gemini_exact?: boolean
}

export interface CfoScaleRow {
  tier_id: string
  label: string
  model_id: string
  avg_input_tokens: number
  avg_output_tokens: number
  cost_per_1k_usd: number
  monthly_100k_usd: number
  monthly_1m_usd: number
  annual_12m_usd: number
  savings_vs_naive_pct: number
  scope_note: string
  field_accuracy_pct?: number | null
  exact_match_pct?: number | null
  schema_compliance_label?: string
}

export interface Cat1BatchResponse {
  mode_used: ExecutionMode
  total_items: number
  avg_input_tokens: number
  items: BatchItemResult[]
  cfo_comparison: CfoScaleRow[]
  summary_callout: string
  accuracy_rollup?: ModelAccuracyRollup[]
}

export interface CreditShieldCredentials {
  mode: ExecutionMode
  anthropicKey: string
  geminiKey: string
  authorPasscode: string
}

// --- Category 2: Generative Synthesis & Drafting ---

export type Cat2SubTaskType = 'exec_synthesis' | 'regulatory_filing'
export type Cat2RungId = 'sonnet_unbounded' | 'sonnet_templated' | 'haiku_templated'
export type Cat2SectionKey =
  | 'executive_summary'
  | 'key_findings'
  | 'risk_and_compliance_matrix'
  | 'action_plan'
export type Cat2ModelTier = 'claude-sonnet-5-5' | 'claude-haiku-5-5'

export interface Cat2Preset {
  id: string
  sub_task: Cat2SubTaskType
  title: string
  subtitle: string
  channel: string
  approx_tokens: number
  payload: string
}

export interface Cat2ReviewerPreset {
  label: string
  instruction: string
}

export interface Cat2PresetsResponse {
  presets: Cat2Preset[]
  schema: Record<string, unknown>
  reviewer_presets: Record<Cat2SectionKey, Cat2ReviewerPreset>
  code_snippets: Record<string, string>
}

export interface StructuredDraftExecutiveSummary {
  headline: string
  narrative: string
  bottom_line_impact: string
}

export interface StructuredDraftFinding {
  id: string
  theme: string
  quantified_evidence: string
  source_anchor: string
}

export interface StructuredDraftRiskRow {
  domain: string
  severity: 'CRITICAL' | 'HIGH' | 'MODERATE'
  exposure_summary: string
  mitigation_control: string
}

export interface StructuredDraftActionItem {
  owner: string
  milestone: string
  target_window: string
  verification_metric: string
}

export interface StructuredDraft {
  document_title: string
  document_type: string
  executive_summary: StructuredDraftExecutiveSummary
  key_findings: StructuredDraftFinding[]
  risk_and_compliance_matrix: StructuredDraftRiskRow[]
  action_plan: StructuredDraftActionItem[]
}

export interface Cat2Count {
  hits: number
  total: number
}

export interface Cat2NumberItem {
  text: string
  context: string
  verdict: string | null
}

export interface Cat2Numbers {
  numeric_tokens: number
  not_in_source: number
  verdicts?: Record<string, number> | null
  items: Cat2NumberItem[]
}

export interface Cat2DraftError {
  claim_quote: string
  problem: string
  source_quote: string | null
  severity: 'material' | 'minor'
  passes_reporting: number
}

export interface Cat2ActionItemCheck {
  total: number
  flagged: number
  flagged_serious: number
}

export interface Cat2HeadToHead {
  opponent: Cat2RungId
  results: { shown_first: Cat2RungId; winner: string | null }[]
}

export type Cat2Dimension = 'factual_accuracy' | 'coverage' | 'clarity' | 'actionability' | 'concision'

export interface Cat2RungQuality {
  source: 'replay_judged' | 'live_deterministic'
  preset_id: string | null
  keys_version: string | null
  core_facts: Cat2Count | null
  detail_facts: Cat2Count | null
  missed_facts: { description: string; tier: 'core' | 'detail' }[]
  numbers: Cat2Numbers | null
  rubric: Partial<Record<Cat2Dimension, { mean: number; scores: number[] }>> | null
  serious_errors: number | null
  minor_errors: number | null
  errors: Cat2DraftError[] | null
  action_items: Cat2ActionItemCheck | null
  head_to_head: Cat2HeadToHead[] | null
  judge_model: string | null
  passes: number | null
  judge_unavailable_reason: string | null
}

export interface Cat2PortfolioRung {
  rung_id: Cat2RungId
  drafts: number
  core_facts: Cat2Count
  detail_facts: Cat2Count
  rubric: Partial<Record<Cat2Dimension, { mean: number | null; min: number | null; max: number | null; n: number }>>
  serious_errors: number
  minor_errors: number
  numbers: Cat2Numbers
  action_items: Cat2ActionItemCheck | null
  cost_per_1k_docs_usd: number | null
  output_tokens_mean: number | null
  head_to_head: Partial<Record<Cat2RungId, { wins: number; losses: number; ties: number }>>
}

export interface Cat2QualityPortfolio {
  schema_version: number
  source: string
  keys_version: string | null
  judge_model: string
  passes_per_draft: number
  drafts_per_cell: number
  documents: string[]
  calls: Record<string, number>
  dimensions: string[]
  rungs: Cat2PortfolioRung[]
  pairwise: Record<
    string,
    { wins: Record<string, Record<string, number>>; ties: Record<string, number>; position_consistency: Record<string, number> }
  >
}

export interface Cat2FieldClasses {
  supported: number
  not_stated: number
  unsupported: number
}

export type Cat2FixArm = 'template_original' | 'template_not_stated'

export interface Cat2TemplateFixCell {
  arm: Cat2FixArm
  model_key: 'sonnet' | 'haiku'
  drafts: number
  action_items: number
  owner: Cat2FieldClasses
  time_window: Cat2FieldClasses
  owner_not_stated_by_preset: Record<string, number>
  owner_supported_by_preset: Record<string, number>
  serious_per_draft: number | null
  minor_per_draft: number | null
  serious_total: number | null
  flagged_items_total: number | null
  rubric: Partial<Record<Cat2Dimension, number | null>>
  core_facts: Cat2Count
  detail_facts: Cat2Count
  cost_per_1k_docs_usd: number | null
  output_tokens_mean: number | null
  truncated: number
}

export interface Cat2FixRecord {
  wins: number
  losses: number
  ties: number
}

export interface Cat2FixHeadToHead {
  overall: Cat2FixRecord
  accuracy: Cat2FixRecord
  usefulness_to_reader: Cat2FixRecord
  calls: number
  position_consistency: Record<string, number>
}

export interface Cat2FixActionItem {
  milestone: string | null
  owner: string | null
  time_window: string | null
  owner_class: string
  window_class: string
}

export interface Cat2TemplateFix {
  schema_version: number
  source: string
  app_template: string
  added_instruction: string
  not_stated_literal: string
  keys_version: string | null
  judge_model: string
  judge_passes_per_draft: number
  counts: Record<string, number>
  field_rules: string[]
  cells: Cat2TemplateFixCell[]
  head_to_head: Record<string, { all: Cat2FixHeadToHead | null; by_model: Record<string, Cat2FixHeadToHead> }>
  example: {
    rule: string
    preset_id: string
    model_key: string
    repeat_index: number
    items: { slot: number; original: Cat2FixActionItem; not_stated: Cat2FixActionItem }[]
  } | null
}

export interface Cat2RungResult {
  rung_id: Cat2RungId
  rung_title: string
  badge_text: string
  model_id: string
  provider: string
  status: 'ok' | 'error'
  error_message: string | null
  latency_ms: number
  structured_draft: Partial<StructuredDraft> & Record<string, unknown>
  raw_markdown: string | null
  thinking_tokens: number
  finops: FinOpsBreakdown
  savings_vs_unbounded_pct: number
  architectural_notes: string[]
  stop_reason?: string | null
  quality?: Cat2RungQuality | null
}

export interface Cat2RunResponse {
  mode_used: ExecutionMode
  preset_id: string | null
  sub_task: Cat2SubTaskType
  input_char_count: number
  estimated_input_tokens: number
  results: Cat2RungResult[]
  haiku_batch_comparator: FinOpsBreakdown | null
  output_tax_callout: string
  quality_portfolio?: Cat2QualityPortfolio | null
  template_fix?: Cat2TemplateFix | null
}

export interface HitlCostComparison {
  surgical_finops: FinOpsBreakdown
  naive_full_reprompt_finops: FinOpsBreakdown
  revision_savings_pct: number
  tokens_avoided: number
  explanation: string
}

export interface Cat2SectionRegenResponse {
  mode_used: ExecutionMode
  preset_id: string | null
  section_key: Cat2SectionKey
  model_used: string
  latency_ms: number
  updated_section: unknown
  finops_comparison: HitlCostComparison
}

// --- Category 3: Multi-Turn Conversational Assistants (IT & HR Service Desk) ---

export type Cat3UseCaseType = 'it_hr_service_desk'
export type Cat3RungId =
  | 'naive_full_history'
  | 'prefix_cached_history'
  | 'prefix_cached_summarized'

export interface Cat3PresetTurnSpec {
  turn_number: number
  topic_tag: string
  user_message: string
}

export interface Cat3Preset {
  id: string
  use_case: Cat3UseCaseType
  title: string
  subtitle: string
  employee_profile: Record<string, string>
  approx_handbook_tokens: number
  suggested_followups: string[]
  turns: Cat3PresetTurnSpec[]
}

export interface Cat3PresetsResponse {
  presets: Cat3Preset[]
  handbook_preview: string
  handbook_char_count: number
  memory_schema: Record<string, unknown>
  code_snippets: Record<string, string>
}

export interface Cat3SessionMemorySnapshot {
  compacted_through_turn: number
  employee_and_device_anchors: string[]
  resolved_issues: string[]
  active_open_items: string[]
  key_numeric_facts: string[]
}

export interface Cat3TurnResult {
  turn_number: number
  topic_tag: string
  user_message: string
  assistant_message: string
  latency_ms: number
  finops: FinOpsBreakdown
  cumulative_cost_usd: number
  cumulative_warm_cost_usd: number
  active_history_turns: number
  compacted_turns_count: number
  memory_summary_snapshot: (Partial<Cat3SessionMemorySnapshot> & Record<string, unknown>) | null
  compaction_triggered_before_turn: boolean
  compaction_finops: FinOpsBreakdown | null
  compaction_latency_ms: number
  estimated_active_context_tokens: number
}

export interface Cat3Measure {
  hits: number
  total: number
  rate: number | null
  ci_low: number | null
  ci_high: number | null
}

export type Cat3LedgerWindow = '1-3' | '4-6' | '7-9'

export interface Cat3ProbeResult {
  probe_id: string
  origin_turn: number
  question: string
  expected: string
  answer: string
  hit: boolean
  outcome: 'correct' | 'declined' | 'wrong'
}

export interface Cat3RungQuality {
  keys_version: string | null
  turn_recall: Cat3Measure
  ledger_recall: Cat3Measure
  ledger_by_origin: Partial<Record<Cat3LedgerWindow, Cat3Measure>>
  probe_accuracy: Cat3Measure | null
  probes: Cat3ProbeResult[] | null
  probes_unavailable_reason: string | null
}

export interface Cat3PortfolioCell {
  runs: number
  turn_recall: Cat3Measure
  ledger_recall: Cat3Measure
  ledger_by_origin: Partial<Record<Cat3LedgerWindow, Cat3Measure>>
  probe_accuracy: Cat3Measure
  session_billed_usd_mean: number | null
  session_warm_usd_mean: number | null
  session_billed_per_1k_usd: number | null
  session_warm_per_1k_usd: number | null
  probe_phase_billed_usd_mean: number | null
}

export interface Cat3PortfolioRung extends Cat3PortfolioCell {
  rung_id: Cat3RungId
  by_preset: Record<string, Cat3PortfolioCell>
}

export interface Cat3QualityPortfolio {
  schema_version: number
  source: string
  source_file: string | null
  keys_version: string | null
  runs: number
  error_records: number
  repeats: number
  sessions: string[]
  probes_per_session: Record<string, number>
  matrix_complete: boolean
  rungs: Cat3PortfolioRung[]
}

export interface Cat3RungSummary {
  rung_id: Cat3RungId
  rung_title: string
  badge_text: string
  pattern: string
  model_id: string
  provider: string
  status: 'ok' | 'error'
  error_message: string | null
  turns: Cat3TurnResult[]
  total_uncached_input_tokens: number
  total_cache_creation_tokens: number
  total_cache_read_tokens: number
  total_output_tokens: number
  summarizer_calls: number
  summarizer_input_tokens: number
  summarizer_output_tokens: number
  summarizer_cost_usd: number
  total_session_cost_usd: number
  warm_fleet_session_cost_usd: number
  cost_per_1k_sessions_usd: number
  warm_cost_per_1k_sessions_usd: number
  savings_vs_naive_pct: number
  warm_savings_vs_naive_pct: number
  savings_vs_cached_history_pct: number
  warm_savings_vs_cached_history_pct: number
  total_latency_ms: number
  architectural_notes: string[]
  quality?: Cat3RungQuality | null
}

export interface Cat3RunResponse {
  mode_used: ExecutionMode
  preset_id: string
  use_case: Cat3UseCaseType
  title: string
  employee_profile: Record<string, string>
  handbook_char_count: number
  approx_handbook_tokens: number
  results: Cat3RungSummary[]
  session_callout: string
  quality_portfolio?: Cat3QualityPortfolio | null
}

export interface Cat3ChatTurnEntry {
  turn_number: number
  user_message: string
  assistant_message: string
}

export interface Cat3ChatTurnResponse {
  mode_used: ExecutionMode
  preset_id: string
  rung_id: Cat3RungId
  turn_result: Cat3TurnResult
  updated_verbatim_turns: Cat3ChatTurnEntry[]
  updated_memory_summary: (Partial<Cat3SessionMemorySnapshot> & Record<string, unknown>) | null
}

// --- Category 4: Multi-Doc RAG & Deep Ingestion (Supplier Deal-Room) ---

export type Cat4UseCaseType = 'supplier_msa_due_diligence'
export type Cat4RungId =
  | 'naive_full_corpus'
  | 'cached_full_corpus_citations'
  | 'hybrid_rag_rerank_citations'

export interface Cat4DealRoomChunkSpec {
  chunk_id: string
  clause_ref: string
  section_heading: string
  doc_char_start: number
  doc_char_end: number
  char_count: number
  approx_tokens: number
}

export interface Cat4DealRoomDoc {
  doc_index: number
  doc_id: string
  doc_code: string
  title: string
  doc_type: string
  effective_date: string
  summary: string
  char_count: number
  approx_tokens: number
  full_text: string
  chunks: Cat4DealRoomChunkSpec[]
}

export interface Cat4PresetQuestion {
  question_id: string
  question_number: number
  topic_tag: string
  question: string
  expected_doc_ids: string[]
  expected_chunk_ids: string[]
}

export interface Cat4Preset {
  id: string
  use_case: Cat4UseCaseType
  title: string
  subtitle: string
  reviewer_role: string
  suggested_custom_queries: string[]
  questions: Cat4PresetQuestion[]
}

export interface Cat4PresetsResponse {
  deal_room_profile: Record<string, unknown>
  documents: Cat4DealRoomDoc[]
  total_docs: number
  total_chunks: number
  corpus_char_count: number
  approx_corpus_tokens: number
  presets: Cat4Preset[]
  rerank_schema: Record<string, unknown>
  code_snippets: Record<string, string>
}

export interface Cat4CitationSpan {
  cite_number: number
  doc_id: string
  document_title: string
  clause_ref: string
  cited_text: string
  start_char_index: number
  end_char_index: number
}

export interface Cat4AnswerSegment {
  text: string
  cite_numbers: number[]
}

export interface Cat4RetrievalChunkTrace {
  chunk_id: string
  doc_id: string
  doc_title: string
  clause_ref: string
  section_heading: string
  char_count: number
  approx_tokens: number
  bm25_score: number
  bm25_rank: number
  stage: 'selected_by_reranker' | 'pruned_by_reranker' | 'pruned_by_bm25'
  reranker_score: number | null
  reranker_rationale: string | null
  is_expected_gold: boolean
}

export interface Cat4Measure {
  hits: number
  total: number
  rate?: number | null
  ci_low?: number | null
  ci_high?: number | null
}

export interface Cat4GraderError {
  claim_quote: string
  problem: string
  source_quote: string
}

export interface Cat4GraderVerdict {
  grader_model: string
  correctness: number
  completeness: number
  correctness_justification: string
  completeness_justification: string
  answers_the_question: 'yes' | 'partly' | 'no'
  material_errors: Cat4GraderError[]
  minor_error_count: number
}

export interface Cat4QuestionQuality {
  question_id: string
  question_number: number
  key_facts: Cat4Measure
  missed_facts: string[]
  citations_requested: boolean
  citation_count: number | null
  zero_citations: boolean | null
  citations_at_expected: Cat4Measure | null
  expected_clause_recall: Cat4Measure | null
  retrieval_recall: Cat4Measure | null
  stop_reason: string | null
  grader: Cat4GraderVerdict | null
}

export interface Cat4AuditQuality {
  questions: number
  key_facts: Cat4Measure
  key_facts_supplier_specific: Cat4Measure
  citations_requested: boolean
  citations_at_expected: Cat4Measure | null
  expected_clause_recall: Cat4Measure | null
  zero_citation_answers: number | null
  retrieval_recall: Cat4Measure | null
  judged: number
  correctness_mean: number | null
  completeness_mean: number | null
  material_errors: number | null
  answers_with_material_error: number | null
}

export interface Cat4RungQuality {
  keys_version: string | null
  audit: Cat4AuditQuality
  questions: Cat4QuestionQuality[]
  grader_unavailable_reason: string | null
}

export interface Cat4PortfolioCell {
  rung_id: string
  runnable_in_app: boolean
  scale: number
  sessions: number
  answers: number
  fact_recall: Cat4Measure
  fact_recall_supplier_specific: Cat4Measure
  fact_recall_non_specific: Cat4Measure
  citations_requested: boolean
  citations_per_answer_mean: number | null
  zero_citation_answers: Cat4Measure | null
  expected_chunk_recall: Cat4Measure | null
  citations_at_expected: Cat4Measure | null
  cited_support: Cat4Measure | null
  contaminated_answers: Cat4Measure
  value_contaminated_answers: Cat4Measure
  value_contaminated_unattributed_answers: Cat4Measure | null
  citation_contaminated_answers: Cat4Measure
  exposure_answers: Cat4Measure | null
  recall_after_bm25: Cat4Measure | null
  recall_after_rerank: Cat4Measure | null
  distractors_selected: Cat4Measure | null
  backfilled: number | null
  invalid_picks: number | null
  judged: number
  correctness_mean: number | null
  completeness_mean: number | null
  material_errors: number | null
  minor_errors: number | null
  answers_with_material_error: Cat4Measure | null
  answers_the_question: Record<string, number>
  cost_per_question_billed_usd: number | null
  cost_per_question_cold_usd: number | null
  cost_per_question_warm_usd: number | null
  cost_per_question_billed_sonnet_usd: number | null
  cost_per_question_billed_haiku_usd: number | null
  cache_write_premium_usd: number
}

export interface Cat4BreakEven {
  a: string
  b: string
  premium_a_usd: number
  per_question_a_usd: number
  premium_b_usd: number
  per_question_b_usd: number
  n_star: number | null
  questions: number | null
  verdict: string
}

export interface Cat4QualityPortfolio {
  schema_version: number
  source: string
  source_file: string | null
  judgements_file: string | null
  keys_version: string | null
  judge_model: string | null
  judge_passes: number
  scope_line: string | null
  record_count: number
  ok_sessions: number
  error_records: number
  superseded_records: number
  answers_scored: number
  answers_judged: number
  sessions_per_cell: number | null
  questions_per_session: number
  scales: number[]
  corpus: Record<string, Record<string, number>>
  synth_max_tokens: number | null
  matrix_complete: boolean
  cells: Cat4PortfolioCell[]
  break_even: Record<string, Cat4BreakEven[]>
}

export interface Cat4QueryResult {
  question_id: string
  question_number: number
  topic_tag: string
  question: string
  question_as_asked?: string | null
  stop_reason?: string | null
  expected_doc_ids: string[]
  expected_chunk_ids: string[]
  answer_markdown: string
  segments: Cat4AnswerSegment[]
  citations: Cat4CitationSpan[]
  cited_doc_ids: string[]
  doc_citation_coverage_pct: number
  latency_ms: number
  finops: FinOpsBreakdown
  cold_query_cost_usd: number
  warm_query_cost_usd: number
  reranker_finops: FinOpsBreakdown | null
  reranker_latency_ms: number
  reranker_stop_reason?: string | null
  retrieval_funnel: Cat4RetrievalChunkTrace[]
  bm25_recall_pct: number | null
  reranker_recall_pct: number | null
  context_tokens_sent: number
  context_reduction_pct: number
}

export interface Cat4RungSummary {
  rung_id: Cat4RungId
  rung_title: string
  badge_text: string
  pattern: string
  model_id: string
  reranker_model_id: string | null
  provider: string
  status: 'ok' | 'error'
  error_message: string | null
  queries: Cat4QueryResult[]
  total_uncached_input_tokens: number
  total_cache_creation_tokens: number
  total_cache_read_tokens: number
  total_output_tokens: number
  reranker_calls: number
  reranker_input_tokens: number
  reranker_output_tokens: number
  reranker_cost_usd: number
  cold_audit_cost_usd: number
  warm_audit_cost_usd: number
  cost_per_1k_audits_cold_usd: number
  cost_per_1k_audits_warm_usd: number
  single_query_cold_per_1k_usd: number
  savings_vs_naive_cold_pct: number
  savings_vs_naive_warm_pct: number
  avg_citations_per_query: number
  avg_doc_coverage_pct: number
  avg_reranker_recall_pct: number | null
  total_latency_ms: number
  architectural_notes: string[]
  quality?: Cat4RungQuality | null
  quality_unavailable_reason?: string | null
}

export interface Cat4RunResponse {
  mode_used: ExecutionMode
  preset_id: string
  use_case: Cat4UseCaseType
  title: string
  deal_room_profile: Record<string, unknown>
  total_docs: number
  total_chunks: number
  corpus_char_count: number
  approx_corpus_tokens: number
  results: Cat4RungSummary[]
  rag_callout: string
  billing_note?: string | null
  quality_portfolio?: Cat4QualityPortfolio | null
}

export interface Cat4AdhocQueryResponse {
  mode_used: ExecutionMode
  preset_id: string
  question: string
  results: Cat4RungSummary[]
  quality_portfolio?: Cat4QualityPortfolio | null
}

// --- Category 5: Autonomous Process Orchestration (3-Way ERP Invoice Agent) ---

export type Cat5UseCaseType = 'invoice_3way_reconciliation'
export type Cat5RungId =
  | 'unbounded_sonnet_loop'
  | 'bounded_sonnet_cached_gate'
  | 'hybrid_haiku_sonnet_governed'

export interface Cat5Preset {
  id: string
  invoice_id: string
  po_id: string
  vendor_name: string
  fc_hub: string
  title: string
  subtitle: string
  complexity_tier: string
  invoice_grand_total_inr: number
  ground_truth: Record<string, unknown>
}

export interface Cat5PresetsResponse {
  presets: Cat5Preset[]
  policy_char_count: number
  approx_policy_tokens: number
  policy_manual_preview: string
  erp_ddl_schema: string
  code_snippets: Record<string, string>
}

export interface Cat5ToolCallTrace {
  tool_use_id: string
  tool_name: string
  tool_input: Record<string, unknown>
  sql_executed: string
  tables_touched: string[]
  is_optimal_call: boolean
  result_preview: string
  gate_snapshot: Record<string, unknown> | null
}

export interface Cat5LoopStep {
  step_number: number
  model_id: string
  escalated_from_haiku: boolean
  stop_reason: string
  assistant_thought: string
  tool_calls: Cat5ToolCallTrace[]
  /** tool_use blocks of a turn cut off by max_tokens: recorded, never executed */
  tool_calls_not_executed?: Record<string, unknown>[]
  latency_ms: number
  finops: FinOpsBreakdown
  cumulative_cold_cost_usd: number
  cumulative_warm_cost_usd: number
}

export interface Cat5CommittedVoucher {
  voucher_id: string
  invoice_id: string
  po_id: string
  decision: string
  authorized_net_principal_inr: number
  authorized_gst_payout_inr: number
  gst_escrow_holdback_inr: number
  debit_note_deduction_inr: number
  gate_verified: boolean
  audit_summary: string
}

export interface Cat5EvaluationResult {
  voucher_committed: boolean
  matched_fields: number
  total_fields: number
  field_accuracy_pct: number
  exact_match: boolean
  evidence_recall_pct: number
  tool_precision_pct: number
  within_step_budget: boolean
  gate_verified: boolean
  field_checks: FieldCheckResult[]
}

export interface Cat5RungResult {
  rung_id: Cat5RungId
  rung_title: string
  badge_text: string
  pattern: string
  primary_model_id: string
  status: 'ok' | 'error'
  error_message: string | null
  max_step_budget: number
  steps_used: number
  haiku_steps: number
  sonnet_steps: number
  escalated_to_sonnet: boolean
  circuit_breaker_triggered: boolean
  steps: Cat5LoopStep[]
  total_uncached_input_tokens: number
  total_cache_creation_tokens: number
  total_cache_read_tokens: number
  total_output_tokens: number
  cold_run_cost_usd: number
  warm_run_cost_usd: number
  cost_per_1k_invoices_cold_usd: number
  cost_per_1k_invoices_warm_usd: number
  savings_vs_naive_cold_pct: number
  savings_vs_naive_warm_pct: number
  total_latency_ms: number
  final_readout: string
  committed_voucher: Cat5CommittedVoucher | null
  evaluation: Cat5EvaluationResult | null
  architectural_notes: string[]
}

export interface Cat5PortfolioRungRollup {
  rung_id: Cat5RungId
  label: string
  model_routing_summary: string
  invoices_evaluated: number
  avg_steps: number
  avg_prompt_tokens: number
  avg_output_tokens: number
  fields_matched: number
  fields_total: number
  adjudication_accuracy_pct: number
  exact_vouchers_matched: number
  avg_evidence_recall_pct: number
  avg_tool_precision_pct: number
  avg_cost_per_1k_cold_usd: number
  avg_cost_per_1k_warm_usd: number
  savings_vs_naive_cold_pct: number
}

export interface Cat5RunResponse {
  mode_used: ExecutionMode
  preset_id: string
  use_case: Cat5UseCaseType
  title: string
  invoice_id: string
  po_id: string
  vendor_name: string
  fc_hub: string
  policy_char_count: number
  approx_policy_tokens: number
  ground_truth: Record<string, unknown>
  results: Cat5RungResult[]
  portfolio_scorecard: Cat5PortfolioRungRollup[]
  orchestration_callout: string
  /** Six-version Category 5 ablation (replays/cat5_ablation_summary.json); null when absent */
  ablation_portfolio?: Cat5AblationPortfolio | null
}

export interface Cat5AblationCell {
  runs: number
  exact: number
  exact_rate: number | null
  exact_wilson95: number[] | null
  decision_correct: number
  committed: number
  field_accuracy_pct_mean: number | null
  evidence_recall_pct_mean: number | null
  tool_precision_pct_mean: number | null
  turns_mean: number | null
  turns_min: number | null
  turns_max: number | null
  cap_hits: number
  truncated_turns: number
  escalation_expected: number
  escalation_fired: number
  uncached_input_tokens_mean: number | null
  cache_write_tokens_mean: number | null
  cache_read_tokens_mean: number | null
  output_tokens_mean: number | null
  cost_per_1k_billed_usd: number | null
  cost_per_1k_cold_usd: number | null
  cost_per_1k_warm_usd: number | null
}

export interface Cat5AblationArm extends Cat5AblationCell {
  arm_id: string
  label: string
  adds: string
  runnable_in_app: boolean
  app_rung_id: Cat5RungId | null
  tool_set: string
  cached: boolean
  start_model: string
  gate: boolean
  escalate: boolean
  turn_cap: number
  tool_calls_per_run: Record<string, number | null>
  runs_calling_tool: Record<string, number>
  disallowed_tool_calls: number
  disallowed_by_name: Record<string, number>
  by_tier: Record<string, Cat5AblationCell>
  by_invoice: Record<string, Cat5AblationCell>
}

export interface Cat5AblationLever {
  lever: string
  label: string
  from_arm: string
  to_arm: string
  changes: string[]
  available: boolean
  exact_from: number | null
  exact_to: number | null
  exact_delta_pp: number | null
  decision_delta_pp: number | null
  cost_billed_from: number | null
  cost_billed_to: number | null
  cost_billed_delta: number | null
  cost_billed_ratio: number | null
  cost_cold_from: number | null
  cost_cold_to: number | null
  cost_cold_delta: number | null
  cost_cold_ratio: number | null
  cost_warm_from: number | null
  cost_warm_to: number | null
  cost_warm_delta: number | null
  cost_warm_ratio: number | null
}

export interface Cat5AblationBaselineRow {
  preset_id: string
  source: 'original_scripted' | 'free_choice'
  runs: number
  exact: number
  decision_correct: number
  turns_mean: number | null
  tool_calls_mean: number | null
  prompt_tokens_mean: number | null
  output_tokens_mean: number | null
  cost_per_1k_billed_usd: number | null
}

export interface Cat5GateDisagreementArm {
  arm_id: string
  gate_arm: boolean
  runs: number
  matches_manual: number
  matches_gate_output: number
  neither: number
  no_commit: number
  decisions: Record<string, number>
  line1_rate: Record<string, number>
}

export interface Cat5GateDisagreement {
  preset_id: string
  invoice_id: string
  ruling: string
  manual_text: string
  manual_truth: Record<string, unknown>
  manual_calculation: string[]
  gate_output_truth: Record<string, unknown>
  gate_calculation: string[]
  line1: Record<string, unknown>
  bundle_note: string
  per_arm: Cat5GateDisagreementArm[]
  no_gate_runs: number
  no_gate_match_manual: number
  gate_runs: number
  gate_match_gate_output: number
  gate_match_manual: number
  missing_keys: number
}

export interface Cat5AblationPortfolio {
  schema_version: number
  source: string
  source_file: string | null
  fixture_version: string | null
  record_count: number
  pooled_runs: number
  gate_disagreement_runs: number
  live_runs_used: number
  error_records: number
  superseded_records: number
  superseded_reasons: string[]
  invoices_pooled: string[]
  invoice_count_pooled: number
  invoice_count_total: number
  repeats: number
  matrix_complete: boolean
  runs_per_arm: number
  settings: Record<string, unknown>
  tiers: Record<string, string | null>
  arms: Cat5AblationArm[]
  levers: Cat5AblationLever[]
  baseline: Cat5AblationBaselineRow[]
  baseline_note: string
  gate_disagreement: Cat5GateDisagreement[]
  data_quality: Record<string, number>
  non_exact_runs: Record<string, unknown>[]
  notes: string[]
  golden_mapping: Record<string, unknown>
}

// --- Category 6: Multi-Agent Swarms & Auto Eng (Checkout CI Swarm + CpO) ---

export type Cat6UseCaseType = 'checkout_ci_self_healing_swarm'
export type Cat6RungId =
  | 'unisolated_broadcast_swarm'
  | 'isolated_cached_sonnet_swarm'
  | 'tiered_hybrid_cpo_swarm'

export interface Cat6Preset {
  id: string
  use_case_tag: string
  pr_id: string
  service_name: string
  target_file: string
  module_filename: string
  title: string
  subtitle: string
  severity: string
  standard_ref: string
  buggy_code: string
  ci_failure_log: string
}

export interface Cat6PresetsResponse {
  presets: Cat6Preset[]
  shared_repo_char_count: number
  approx_shared_repo_tokens: number
  shared_repo_preview: string
  sandbox_suite_source: string
  code_snippets: Record<string, string>
}

export interface Cat6AgentTurnTrace {
  step_number: number
  agent_role: string
  agent_label: string
  model_id: string
  context_mode: 'shared_omnibus_bus' | 'isolated_prefix_cached'
  attempt: number
  latency_ms: number
  finops: FinOpsBreakdown
  cumulative_cold_cost_usd: number
  cumulative_warm_cost_usd: number
  prompt_preview: string
  output_preview: string
}

export interface Cat6SandboxCheckResult {
  check_id: string
  category: 'ci_unit' | 'adversarial' | 'ast'
  name: string
  passed: boolean
  detail: string
}

export interface Cat6SandboxReport {
  total_checks: number
  passed_checks: number
  ci_unit_passed: number
  adversarial_passed: number
  ast_passed: number
  verified_outcome: boolean
  execution_ms: number
  checks: Cat6SandboxCheckResult[]
  unified_diff: string
}

export interface Cat6RungResult {
  rung_id: Cat6RungId
  rung_title: string
  badge_text: string
  pattern: string
  primary_model_id: string
  status: 'ok' | 'error'
  error_message: string | null
  agent_turns: Cat6AgentTurnTrace[]
  retries_used: number
  haiku_turns: number
  sonnet_turns: number
  total_uncached_input_tokens: number
  total_cache_creation_tokens: number
  total_cache_read_tokens: number
  total_output_tokens: number
  cold_run_cost_usd: number
  warm_run_cost_usd: number
  cost_per_1k_runs_cold_usd: number
  cost_per_1k_runs_warm_usd: number
  /** null when the run has no verified outcome (CpO undefined) */
  cpo_cold_per_1k_usd: number | null
  cpo_warm_per_1k_usd: number | null
  savings_vs_naive_cold_pct: number
  savings_vs_naive_warm_pct: number
  total_latency_ms: number
  patched_code: string
  final_signoff_memo: string
  sandbox_report: Cat6SandboxReport | null
  architectural_notes: string[]
}

export interface Cat6PortfolioRungRollup {
  rung_id: Cat6RungId
  label: string
  routing_summary: string
  prs_evaluated: number
  verified_outcomes_count: number
  verified_outcome_rate_pct: number
  checks_passed_total: number
  checks_total: number
  avg_prompt_tokens: number
  avg_output_tokens: number
  daily_tokens_per_dev_at_25_runs: number
  avg_cpr_cold_per_1k_usd: number
  avg_cpr_warm_per_1k_usd: number
  /** null when the rung has zero verified outcomes; savings null when either side is undefined */
  portfolio_cpo_cold_per_1k_usd: number | null
  portfolio_cpo_warm_per_1k_usd: number | null
  cpo_savings_vs_naive_cold_pct: number | null
}

export interface Cat6RunResponse {
  mode_used: ExecutionMode
  preset_id: string
  use_case: Cat6UseCaseType
  title: string
  pr_id: string
  service_name: string
  target_file: string
  use_case_tag: string
  shared_repo_char_count: number
  approx_shared_repo_tokens: number
  results: Cat6RungResult[]
  portfolio_scorecard: Cat6PortfolioRungRollup[]
  swarm_callout: string
}
