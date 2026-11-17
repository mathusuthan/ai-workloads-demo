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
