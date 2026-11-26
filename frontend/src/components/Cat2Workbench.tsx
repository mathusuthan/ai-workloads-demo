import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Code2,
  DollarSign,
  Edit3,
  FileText,
  Lock,
  Play,
  RefreshCw,
  Scissors,
  Sparkles,
  TrendingDown,
  Unlock,
  Zap,
} from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { regenerateCat2Section, runCat2Arena } from '../api'
import type {
  ArchetypeSpec,
  Cat2ModelTier,
  Cat2PresetsResponse,
  Cat2RungId,
  Cat2RungResult,
  Cat2RunResponse,
  Cat2SectionKey,
  Cat2SectionRegenResponse,
  Cat2SubTaskType,
  CreditShieldCredentials,
  StructuredDraft,
  StructuredDraftActionItem,
  StructuredDraftExecutiveSummary,
  StructuredDraftFinding,
  StructuredDraftRiskRow,
} from '../types'
import { Cat2QualityPanel } from './Cat2QualityPanel'
import { NativeModal } from './NativeModal'
import { WrappedAxisTick } from './ChartTicks'
import { DESIGN_SERIES, DESIGN_THEME, DesignMark } from './DesignMark'
import { ReplayStatus, RevealPlaceholder, useStagedReveal } from './StagedReveal'

interface Cat2WorkbenchProps {
  archetype: ArchetypeSpec
  presetsData: Cat2PresetsResponse
  creds: CreditShieldCredentials
  onRefreshSystemStatus: () => void
}

const CAT2_RUNGS: Cat2RungId[] = ['sonnet_unbounded', 'haiku_unbounded', 'sonnet_templated', 'haiku_templated']

const VOLUME_STEPS = [
  { label: '1k / mo (Exec Pilot)', value: 1_000 },
  { label: '10k / mo (Ops + Compliance)', value: 10_000 },
  { label: '50k / mo (NovaMart Steady)', value: 50_000 },
  { label: '250k / mo (Enterprise Scale)', value: 250_000 },
  { label: '1M / mo (Peak Marketplace)', value: 1_000_000 },
]

const SECTION_META: Array<{ key: Cat2SectionKey; title: string; subtitle: string }> = [
  {
    key: 'executive_summary',
    title: '1. Executive Summary',
    subtitle: 'Board headline, compressed synthesis narrative & bottom-line financial impact',
  },
  {
    key: 'key_findings',
    title: '2. Quantified Key Findings',
    subtitle: 'Three quantified findings, each with a source anchor',
  },
  {
    key: 'risk_and_compliance_matrix',
    title: '3. Risk & Compliance Matrix',
    subtitle: 'Severity-ranked financial, statutory, and SLA exposure + concrete controls',
  },
  {
    key: 'action_plan',
    title: '4. Owned Action Plan',
    subtitle: 'Time-bound execution gates with owning team & verification metric (check owners and deadlines against the source)',
  },
]

function normalizeDraft(raw: Record<string, unknown> | undefined): StructuredDraft {
  const exec = (raw?.executive_summary ?? {}) as Partial<StructuredDraftExecutiveSummary>
  return {
    document_title: String(raw?.document_title ?? 'NovaMart Executive & Compliance Draft'),
    document_type: String(raw?.document_type ?? 'EXECUTIVE_OPS_READOUT'),
    executive_summary: {
      headline: String(exec.headline ?? ''),
      narrative: String(exec.narrative ?? ''),
      bottom_line_impact: String(exec.bottom_line_impact ?? ''),
    },
    key_findings: Array.isArray(raw?.key_findings)
      ? (raw.key_findings as StructuredDraftFinding[])
      : [],
    risk_and_compliance_matrix: Array.isArray(raw?.risk_and_compliance_matrix)
      ? (raw.risk_and_compliance_matrix as StructuredDraftRiskRow[])
      : [],
    action_plan: Array.isArray(raw?.action_plan)
      ? (raw.action_plan as StructuredDraftActionItem[])
      : [],
  }
}

export function Cat2Workbench({
  archetype,
  presetsData,
  creds,
  onRefreshSystemStatus,
}: Cat2WorkbenchProps) {
  const [activeView, setActiveView] = useState<'arena' | 'studio'>('arena')
  const [subTask, setSubTask] = useState<Cat2SubTaskType>('exec_synthesis')

  const filteredPresets = useMemo(
    () => presetsData.presets.filter((p) => p.sub_task === subTask),
    [presetsData.presets, subTask]
  )

  const [selectedPresetId, setSelectedPresetId] = useState<string>(
    presetsData.presets.find((p) => p.sub_task === 'exec_synthesis')?.id ?? 'brief-01'
  )
  const [payloadText, setPayloadText] = useState<string>(
    presetsData.presets.find((p) => p.sub_task === 'exec_synthesis')?.payload ?? ''
  )

  const [runResponse, setRunResponse] = useState<Cat2RunResponse | null>(null)
  const [loadingArena, setLoadingArena] = useState(false)
  const reveal = useStagedReveal('versions')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [expandedRungs, setExpandedRungs] = useState<Record<string, boolean>>({})

  // FinOps HUD controls
  const [volumeIdx, setVolumeIdx] = useState(2) // Default 50k / mo
  const [scaleMode, setScaleMode] = useState<'linear' | 'log'>('linear')

  // Interactive HITL Section Studio state
  const [studioSourceRung, setStudioSourceRung] = useState<'sonnet_templated' | 'haiku_templated'>(
    'sonnet_templated'
  )
  const [workingDraft, setWorkingDraft] = useState<StructuredDraft | null>(null)
  const [lockedSections, setLockedSections] = useState<Record<Cat2SectionKey, boolean>>({
    executive_summary: false,
    key_findings: false,
    risk_and_compliance_matrix: false,
    action_plan: false,
  })
  const [editingSections, setEditingSections] = useState<Record<Cat2SectionKey, boolean>>({
    executive_summary: false,
    key_findings: false,
    risk_and_compliance_matrix: false,
    action_plan: false,
  })
  const [sectionDraftJson, setSectionDraftJson] = useState<Record<Cat2SectionKey, string>>({
    executive_summary: '',
    key_findings: '',
    risk_and_compliance_matrix: '',
    action_plan: '',
  })
  const [regenInstructions, setRegenInstructions] = useState<Record<Cat2SectionKey, string>>({
    executive_summary: presetsData.reviewer_presets.executive_summary.instruction,
    key_findings: presetsData.reviewer_presets.key_findings.instruction,
    risk_and_compliance_matrix: presetsData.reviewer_presets.risk_and_compliance_matrix.instruction,
    action_plan: presetsData.reviewer_presets.action_plan.instruction,
  })
  const [regenModels, setRegenModels] = useState<Record<Cat2SectionKey, Cat2ModelTier>>({
    executive_summary: 'claude-sonnet-5-5',
    key_findings: 'claude-haiku-5-5',
    risk_and_compliance_matrix: 'claude-sonnet-5-5',
    action_plan: 'claude-haiku-5-5',
  })
  const [regenLoading, setRegenLoading] = useState<Cat2SectionKey | null>(null)
  const [lastRegenBySection, setLastRegenBySection] = useState<
    Partial<Record<Cat2SectionKey, Cat2SectionRegenResponse>>
  >({})
  const [regenHistory, setRegenHistory] = useState<Cat2SectionRegenResponse[]>([])

  // Inspector Modal
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [inspectorTab, setInspectorTab] = useState<'code' | 'schema'>('code')

  const selectedPreset = useMemo(
    () => presetsData.presets.find((p) => p.id === selectedPresetId) ?? filteredPresets[0],
    [presetsData.presets, selectedPresetId, filteredPresets]
  )

  const isPayloadModified =
    selectedPreset !== undefined && payloadText.trim() !== selectedPreset.payload.trim()

  const syncStudioFromRun = (
    resp: Cat2RunResponse,
    preferredRung: 'sonnet_templated' | 'haiku_templated' = studioSourceRung
  ) => {
    const picked =
      resp.results.find((r) => r.rung_id === preferredRung && r.status === 'ok') ??
      resp.results.find((r) => r.rung_id === 'sonnet_templated' && r.status === 'ok') ??
      resp.results.find((r) => r.rung_id === 'haiku_templated' && r.status === 'ok')
    if (picked) {
      const normalized = normalizeDraft(picked.structured_draft)
      setWorkingDraft(normalized)
      setLockedSections({
        executive_summary: false,
        key_findings: false,
        risk_and_compliance_matrix: false,
        action_plan: false,
      })
      setEditingSections({
        executive_summary: false,
        key_findings: false,
        risk_and_compliance_matrix: false,
        action_plan: false,
      })
      setLastRegenBySection({})
    }
  }

  const executeArena = async (
    overridePresetId?: string,
    overrideSubTask?: Cat2SubTaskType,
    opts?: { staged?: boolean }
  ) => {
    // a replay click clears the cards and reveals them in card order (the mount load and preset picks stay instant)
    const staged = Boolean(opts?.staged) && creds.mode !== 'live'
    const targetSub = overrideSubTask ?? subTask
    const targetPresetId = overridePresetId ?? selectedPresetId
    const targetPreset = presetsData.presets.find((p) => p.id === targetPresetId)
    const modified =
      !overridePresetId &&
      targetPreset !== undefined &&
      payloadText.trim() !== targetPreset.payload.trim()

    setLoadingArena(true)
    setErrorMsg(null)
    if (staged) reveal.begin()
    try {
      const resp = await runCat2Arena(
        {
          preset_id: modified ? undefined : targetPresetId,
          custom_input: modified ? payloadText : undefined,
          sub_task: targetSub,
          rungs: CAT2_RUNGS,
          mode: creds.mode,
        },
        creds
      )
      setRunResponse(resp)
      syncStudioFromRun(resp, studioSourceRung)
      setRegenHistory([])
      if (resp.mode_used === 'live') {
        onRefreshSystemStatus()
      }
      if (staged) reveal.run(resp.results.map((r) => r.rung_id))
    } catch (err) {
      if (staged) reveal.reset()
      setErrorMsg(err instanceof Error ? err.message : 'Failed to run Category 2 Synthesis Arena.')
    } finally {
      setLoadingArena(false)
    }
  }

  useEffect(() => {
    void executeArena('brief-01', 'exec_synthesis')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleSelectSubTask = (nextSubTask: Cat2SubTaskType) => {
    setSubTask(nextSubTask)
    const first = presetsData.presets.find((p) => p.sub_task === nextSubTask)
    if (first) {
      setSelectedPresetId(first.id)
      setPayloadText(first.payload)
      void executeArena(first.id, nextSubTask)
    }
    setErrorMsg(null)
  }

  const handleSelectPreset = (presetId: string) => {
    const found = presetsData.presets.find((p) => p.id === presetId)
    if (found) {
      setSelectedPresetId(found.id)
      setPayloadText(found.payload)
      void executeArena(found.id, found.sub_task)
    }
  }

  const handleOpenInStudio = (rungId: 'sonnet_templated' | 'haiku_templated') => {
    setStudioSourceRung(rungId)
    if (runResponse) {
      syncStudioFromRun(runResponse, rungId)
    }
    setActiveView('studio')
  }

  const toggleSectionEdit = (sec: Cat2SectionKey) => {
    if (!workingDraft) return
    const nextEditing = !editingSections[sec]
    if (nextEditing) {
      setSectionDraftJson((prev) => ({
        ...prev,
        [sec]: JSON.stringify(workingDraft[sec], null, 2),
      }))
    }
    setEditingSections((prev) => ({ ...prev, [sec]: nextEditing }))
  }

  const saveInlineSectionEdit = (sec: Cat2SectionKey) => {
    if (!workingDraft) return
    try {
      const parsed = JSON.parse(sectionDraftJson[sec]) as unknown
      setWorkingDraft({ ...workingDraft, [sec]: parsed } as StructuredDraft)
      setEditingSections((prev) => ({ ...prev, [sec]: false }))
      setErrorMsg(null)
    } catch {
      setErrorMsg(`Invalid JSON syntax in inline edit for ${sec}. Please check quotes/brackets.`)
    }
  }

  const handleSurgicalRegen = async (sec: Cat2SectionKey) => {
    if (!workingDraft || lockedSections[sec]) return
    setRegenLoading(sec)
    setErrorMsg(null)
    try {
      const modified =
        selectedPreset !== undefined && payloadText.trim() !== selectedPreset.payload.trim()
      const resp = await regenerateCat2Section(
        {
          preset_id: modified ? undefined : selectedPresetId,
          custom_input: modified ? payloadText : undefined,
          sub_task: subTask,
          section_key: sec,
          current_section: workingDraft[sec],
          reviewer_instruction: regenInstructions[sec],
          model_tier: regenModels[sec],
          mode: creds.mode,
        },
        creds
      )
      setWorkingDraft((prev) => (prev ? ({ ...prev, [sec]: resp.updated_section } as StructuredDraft) : prev))
      setLastRegenBySection((prev) => ({ ...prev, [sec]: resp }))
      setRegenHistory((prev) => [...prev, resp])
      if (resp.mode_used === 'live') {
        onRefreshSystemStatus()
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : `Failed to regenerate ${sec}.`)
    } finally {
      setRegenLoading(null)
    }
  }

  const handleViewTabKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault()
      const next = activeView === 'arena' ? 'studio' : 'arena'
      setActiveView(next)
      document.getElementById(next === 'arena' ? 'cat2-tab-arena' : 'cat2-tab-studio')?.focus()
    }
  }

  const handleInspectorTabKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault()
      const next = inspectorTab === 'code' ? 'schema' : 'code'
      setInspectorTab(next)
      document.getElementById(`cat2-insp-tab-${next}`)?.focus()
    }
  }

  // Compute FinOps chart rows for Arena
  const monthlyVol = VOLUME_STEPS[volumeIdx].value
  // intro figures computed from what the page loaded (no hard-coded results):
  // output share of the unbounded drafts on this document; templated cost as a share of unbounded, per model
  const introFacts = useMemo(() => {
    const pct = (x: number) => `${Math.round(x)}%`
    const range = (xs: number[]) => {
      if (xs.length === 0) return null
      const lo = Math.min(...xs)
      const hi = Math.max(...xs)
      return Math.round(lo) === Math.round(hi) ? pct(lo) : `${pct(lo)}–${pct(hi)}`
    }
    const shares = (runResponse?.results ?? [])
      .filter((r) => r.status === 'ok' && r.rung_id.endsWith('_unbounded'))
      .map((r) => r.finops.output_cost_share_pct)
    const cells = runResponse?.quality_portfolio?.cells ?? []
    const ratios: number[] = []
    const fewer: boolean[] = []
    for (const model of ['sonnet', 'haiku'] as const) {
      const u = cells.find((c) => c.model_key === model && c.arm === 'unbounded')
      const t = cells.find((c) => c.model_key === model && c.arm !== 'unbounded')
      if (u?.cost_per_1k_docs_usd && t?.cost_per_1k_docs_usd != null) {
        ratios.push((t.cost_per_1k_docs_usd / u.cost_per_1k_docs_usd) * 100)
      }
      if (u?.detail_facts?.total && t?.detail_facts?.total) {
        fewer.push(t.detail_facts.hits / t.detail_facts.total < u.detail_facts.hits / u.detail_facts.total)
      }
    }
    return {
      outputShare: range(shares),
      templateCostShare: ratios.length === 2 ? range(ratios) : null,
      // stated only when the graded summary shows it on both models
      fewerDetails: fewer.length === 2 && fewer.every(Boolean),
    }
  }, [runResponse])

  const finopsRows = useMemo(() => {
    if (!runResponse) return []
    const byId = Object.fromEntries(runResponse.results.map((r) => [r.rung_id, r]))
    const rows: Array<{
      id: string
      name: string
      shortLabel: string
      costPer1k: number
      chartValue: number
      inputCost1k: number
      outputCost1k: number
      monthlyUsd: number
      annualUsd: number
      color: string
    }> = []

    const pushRow = (id: string, name: string, shortLabel: string, color: string, f: Cat2RungResult['finops']) => {
      const c1k = f.cost_per_1k_usd
      rows.push({
        id,
        name,
        shortLabel,
        costPer1k: c1k,
        chartValue: scaleMode === 'log' ? Math.max(0.05, c1k) : c1k,
        inputCost1k: Number((f.input_cost_usd * 1000).toFixed(4)),
        outputCost1k: Number((f.output_cost_usd * 1000).toFixed(4)),
        monthlyUsd: f.total_cost_usd * monthlyVol,
        annualUsd: f.total_cost_usd * monthlyVol * 12,
        color,
      })
    }

    const versions: Array<[Cat2RungId, string, string, string]> = [
      // red family without the lever, green family with it; two shades tell the models apart
      ['sonnet_unbounded', 'Sonnet 5.5 · without template (unbounded)', 'Sonnet unbounded', DESIGN_SERIES.withoutSonnet],
      ['haiku_unbounded', 'Haiku 5.5 · without template (unbounded)', 'Haiku unbounded', DESIGN_SERIES.withoutHaiku],
      ['sonnet_templated', 'Sonnet 5.5 · with section template', 'Sonnet template', DESIGN_SERIES.withSonnet],
      ['haiku_templated', 'Haiku 5.5 · with section template', 'Haiku template', DESIGN_SERIES.withHaiku],
    ]
    for (const [id, name, shortLabel, color] of versions) {
      const r = byId[id]
      if (r?.status === 'ok') pushRow(id, name, shortLabel, color, r.finops)
    }
    if (runResponse.haiku_batch_comparator) {
      pushRow(
        'haiku_batch',
        'Haiku 5.5 · with section template, Batch (-50%)',
        'Haiku Batch (computed)',
        // computed (not run), a "with" configuration: hatched light green, drawn from the pattern below
        'url(#cat2-batch-hatch)',
        runResponse.haiku_batch_comparator
      )
    }
    return rows
  }, [runResponse, monthlyVol, scaleMode])

  const unboundedMonthly = finopsRows.find((r) => r.id === 'sonnet_unbounded')?.monthlyUsd ?? 0
  const templatedMonthly = finopsRows.find((r) => r.id === 'sonnet_templated')?.monthlyUsd ?? 0
  const annualTemplateSaved = Math.max(0, (unboundedMonthly - templatedMonthly) * 12)

  // Cumulative HITL ledger totals
  const hitlTotals = useMemo(() => {
    const surgicalTotal = regenHistory.reduce(
      (acc, r) => acc + r.finops_comparison.surgical_finops.total_cost_usd,
      0
    )
    const naiveTotal = regenHistory.reduce(
      (acc, r) => acc + r.finops_comparison.naive_full_reprompt_finops.total_cost_usd,
      0
    )
    const tokensAvoided = regenHistory.reduce(
      (acc, r) => acc + r.finops_comparison.tokens_avoided,
      0
    )
    const savedPct = naiveTotal > 0 ? ((naiveTotal - surgicalTotal) / naiveTotal) * 100 : 0
    return {
      count: regenHistory.length,
      surgicalTotal,
      naiveTotal,
      tokensAvoided,
      savedPct,
    }
  }, [regenHistory])

  const lockedCount = Object.values(lockedSections).filter(Boolean).length

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
      {/* Top Breadcrumb + Inspector Trigger */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Matrix Overview
        </Link>

        <button
          type="button"
          onClick={() => setInspectorOpen(true)}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3.5 py-1.5 text-xs font-bold text-slate-800 shadow-2xs transition hover:bg-slate-50"
        >
          <Code2 className="h-4 w-4 text-red-600" />
          Architecture &amp; Code Inspector
        </button>
      </div>

      {/* Category 2 Banner (#DC2626 Crimson) */}
      <section className="overflow-hidden rounded-2xl border border-red-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 bg-red-600 px-6 py-2.5 text-white">
          <div className="flex flex-wrap items-center gap-2 text-xs font-extrabold uppercase tracking-wider">
            <span>{archetype.category_label}</span>
            <span>·</span>
            <span>{archetype.autonomy_tier_label}</span>
            <span className="rounded bg-white/20 px-2 py-0.5 font-mono text-[11px]">
              {archetype.token_band}
            </span>
          </div>
          <span className="font-mono text-xs font-bold text-red-100">{archetype.dynamics}</span>
        </div>

        <div className="flex flex-col justify-between gap-4 px-6 py-5 lg:flex-row lg:items-center">
          <div>
            <h1 className="text-xl font-extrabold tracking-tight text-slate-900 sm:text-2xl">
              {archetype.title} — {archetype.novamart_product_name}
            </h1>
            <p className="mt-1 max-w-3xl text-xs leading-relaxed text-slate-600 sm:text-sm">
              Because Anthropic output tokens cost <strong>5x input tokens</strong> ($10.00/M vs $2.00/M on{' '}
              <strong>Sonnet 5.5</strong>), output {introFacts.outputShare
                ? `is ${introFacts.outputShare} of an unbounded draft's cost on this document`
                : "is most of an unbounded draft's cost"}
              . <strong>Section-Templated Bounds</strong> (on <strong>Sonnet 5.5</strong> and{' '}
              <strong>Haiku 5.5</strong>){' '}
              {introFacts.templateCostShare
                ? `cost ${introFacts.templateCostShare} of the unbounded drafts on the same model across the graded documents`
                : 'cost less than the unbounded drafts on the same model'}
              {introFacts.fewerDetails ? ' and carry fewer of the supporting details in the answer key' : ''}; the grades
              and serious-error counts per version are in the quality panel below. <strong>Surgical HITL Section Regen</strong> regenerates one section instead of re-prompting the
              entire document.
            </p>
          </div>

          <div className="flex shrink-0 flex-wrap gap-2">
            <button
              type="button"
              onClick={() => handleSelectSubTask('exec_synthesis')}
              className={`rounded-xl border px-3.5 py-2 text-left text-xs font-bold transition ${
                subTask === 'exec_synthesis'
                  ? 'border-red-600 bg-red-50 text-red-950 ring-1 ring-red-600'
                  : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
              }`}
            >
              <div>2A · Executive &amp; Proposal Synthesis</div>
              <div className="mt-0.5 text-[10px] font-normal text-slate-500">
                War-room readouts &amp; B2B collateral
              </div>
            </button>

            <button
              type="button"
              onClick={() => handleSelectSubTask('regulatory_filing')}
              className={`rounded-xl border px-3.5 py-2 text-left text-xs font-bold transition ${
                subTask === 'regulatory_filing'
                  ? 'border-red-600 bg-red-50 text-red-950 ring-1 ring-red-600'
                  : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
              }`}
            >
              <div>2B · Regulatory &amp; Safety Filings</div>
              <div className="mt-0.5 text-[10px] font-normal text-slate-500">
                UN38.3 hazmat &amp; KYC escrow audits
              </div>
            </button>
          </div>
        </div>

        {/* Accessible Tablist (tabs guide: no wrapping, aria-selected underline indicator) */}
        <div
          role="tablist"
          aria-label="Category 2 workbench views"
          onKeyDown={handleViewTabKeyDown}
          className="mwg-tablist border-t border-slate-200 bg-slate-50 px-6"
        >
          <button
            type="button"
            role="tab"
            id="cat2-tab-arena"
            aria-selected={activeView === 'arena'}
            tabIndex={activeView === 'arena' ? 0 : -1}
            onClick={() => setActiveView('arena')}
            className={`mwg-tab inline-flex items-center gap-2 px-4 py-3 text-xs font-bold transition ${
              activeView === 'arena' ? 'text-red-700' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Sparkles className="h-3.5 w-3.5" />
            Without vs With Section Template · Output-Tax Arena
          </button>

          <button
            type="button"
            role="tab"
            id="cat2-tab-studio"
            aria-selected={activeView === 'studio'}
            tabIndex={activeView === 'studio' ? 0 : -1}
            onClick={() => setActiveView('studio')}
            className={`mwg-tab inline-flex items-center gap-2 px-4 py-3 text-xs font-bold transition ${
              activeView === 'studio' ? 'text-red-700' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Scissors className="h-3.5 w-3.5" />
            Interactive HITL Section Studio (Lock, Edit &amp; Surgical Regen)
          </button>
        </div>
      </section>

      {errorMsg && (
        <div
          role="alert"
          className="flex items-start gap-2.5 rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-xs text-rose-900"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />
          <div>
            <span className="font-bold">Execution notice:</span> {errorMsg}
          </div>
        </div>
      )}

      {/* TAB PANEL 1: WITHOUT VS WITH TEMPLATE ARENA (zero padding/border directly on tabpanel) */}
      <div role="tabpanel" aria-labelledby="cat2-tab-arena" hidden={activeView !== 'arena'}>
        <div className="space-y-6">
          {/* Preset Picker + Source Bundle Editor */}
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-extrabold text-slate-900">
                Select NovaMart {subTask === 'exec_synthesis' ? 'Executive / B2B Brief' : 'Regulatory Audit'} Source Bundle
              </h2>
              <span className="font-mono text-[11px] text-slate-500">
                {payloadText.length.toLocaleString()} chars (~
                {(
                  !isPayloadModified && selectedPreset
                    ? selectedPreset.approx_tokens
                    : Math.max(1, Math.round(payloadText.length / 2.15))
                ).toLocaleString()}{' '}
                tokens)
              </span>
            </div>

            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {filteredPresets.map((p) => {
                const active = p.id === selectedPresetId && !isPayloadModified
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => handleSelectPreset(p.id)}
                    className={`rounded-xl border p-3.5 text-left transition ${
                      active
                        ? 'border-red-600 bg-red-50/70 ring-1 ring-red-600'
                        : 'border-slate-200 bg-slate-50/50 hover:border-slate-300 hover:bg-white'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[10px] font-bold uppercase text-red-700">
                        {p.id} · {p.channel}
                      </span>
                      <span className="rounded bg-slate-200/80 px-1.5 py-0.5 font-mono text-[10px] font-bold text-slate-700">
                        ~{p.approx_tokens.toLocaleString()} tok
                      </span>
                    </div>
                    <div className="mt-1.5 text-xs font-extrabold leading-snug text-slate-900">
                      {p.title}
                    </div>
                    <div className="mt-1 text-[11px] text-slate-500">{p.subtitle}</div>
                  </button>
                )
              })}
            </div>

            <div className="mt-4">
              <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
                <label htmlFor="cat2-payload-input" className="text-xs font-bold text-slate-700">
                  Multi-Source Input Bundle{' '}
                  {creds.mode === 'replay'
                    ? '(Select a preset above for $0 Verified Replay; switch to Live API to customize)'
                    : '(Live API Mode active — edit freely to synthesize custom briefs)'}
                </label>
                {isPayloadModified && selectedPreset && (
                  <button
                    type="button"
                    onClick={() => setPayloadText(selectedPreset.payload)}
                    className="text-[11px] font-bold text-red-700 hover:underline"
                  >
                    Reset to Preset ({selectedPreset.id})
                  </button>
                )}
              </div>
              <textarea
                id="cat2-payload-input"
                rows={6}
                value={payloadText}
                onChange={(e) => setPayloadText(e.target.value)}
                className="w-full rounded-xl border border-slate-300 bg-slate-950 p-3.5 font-mono text-xs leading-relaxed text-slate-100 focus:border-red-500 focus:outline-none"
              />
            </div>

            <div className="mt-4 flex flex-wrap items-center justify-end gap-3">
              <ReplayStatus status={reveal.status} />
              <button
                type="button"
                aria-disabled={loadingArena || reveal.replaying}
                aria-busy={loadingArena || reveal.replaying}
                onClick={() => {
                  if (loadingArena || reveal.replaying) return
                  void executeArena(undefined, undefined, { staged: true })
                }}
                className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-5 py-2.5 text-xs font-extrabold text-white shadow-sm transition hover:bg-red-700 aria-disabled:cursor-not-allowed aria-disabled:opacity-50"
              >
                {creds.mode === 'live' ? (
                  <Zap className="h-4 w-4 text-amber-300" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
                <span>
                  {reveal.replaying
                    ? 'Replaying…'
                    : loadingArena
                    ? 'Drafting 4 versions...'
                    : creds.mode === 'live'
                      ? 'Run Live: Without vs With Template'
                      : 'Run: Without vs With Template'}
                </span>
              </button>
            </div>
          </section>

          {runResponse && (
            <>
              {/* Output-Tax Callout Banner */}
              <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-semibold text-red-950">
                {runResponse.output_tax_callout}
              </div>

              {/* Without / with template cards, Sonnet and Haiku */}
              <div ref={reveal.resultsRef} className="grid scroll-mt-24 gap-4 md:grid-cols-2 xl:grid-cols-4">
                {runResponse.results.map((res) => {
                  if (!reveal.isVisible(res.rung_id)) {
                    return (
                      <RevealPlaceholder
                        key={res.rung_id}
                        title={res.rung_title}
                        withLever={!res.rung_id.endsWith('_unbounded')}
                      />
                    )
                  }
                  const f = res.finops
                  const isUnbounded = res.rung_id.endsWith('_unbounded')
                  const isTemplatedSonnet = res.rung_id === 'sonnet_templated'
                  const isPending = res.status === 'pending'
                  // red (rose) for both versions without the lever, green (emerald) for both with it
                  const d = isUnbounded ? DESIGN_THEME.without : DESIGN_THEME.with
                  const borderTheme = isPending ? 'border-slate-200 border-dashed' : d.border
                  const headerBg = d.headerBg
                  const badgeBg = d.badge
                  const expanded = Boolean(expandedRungs[res.rung_id])
                  const draft = normalizeDraft(res.structured_draft)

                  return (
                    <div
                      key={res.rung_id}
                      className={`flex flex-col justify-between rounded-2xl border bg-white shadow-sm ${borderTheme}`}
                    >
                      <div>
                        <div className={`rounded-t-2xl border-b border-slate-200/80 px-4 py-3 ${headerBg}`}>
                          <div className="flex items-center justify-between gap-2">
                            <span className={`rounded-md px-2 py-0.5 text-[10px] font-extrabold uppercase ${badgeBg}`}>
                              {res.badge_text}
                            </span>
                            <span className="font-mono text-xs font-bold text-slate-700">
                              {(res.latency_ms / 1000).toFixed(1)}s
                            </span>
                          </div>
                          <div className="mt-2 flex items-center gap-1.5">
                            <DesignMark withLever={!isUnbounded} />
                            <h3 className="text-sm font-extrabold text-slate-900">{res.rung_title}</h3>
                          </div>
                          <div className="mt-0.5 font-mono text-[11px] text-slate-600">
                            Anthropic · <strong>{res.model_id}</strong>
                          </div>
                        </div>

                        {isPending ? (
                          <div className="p-4 text-xs text-slate-600">
                            <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-500 ring-1 ring-slate-200">
                              run pending
                            </span>
                            <p className="mt-2 leading-relaxed">{res.error_message}</p>
                          </div>
                        ) : res.status === 'error' ? (
                          <div className="p-4 text-xs text-rose-700">{res.error_message}</div>
                        ) : (
                          <div className="space-y-4 p-4">
                            <div className="grid grid-cols-2 gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3">
                              <div>
                                <div className="text-[10px] font-bold uppercase text-slate-500">
                                  Cost / 1,000 Drafts
                                </div>
                                <div className="mt-0.5 font-mono text-xl font-extrabold tabular-nums text-slate-900">
                                  ${f.cost_per_1k_usd.toFixed(2)}
                                </div>
                                <div
                                  className={`text-[11px] font-bold ${
                                    isUnbounded ? 'text-rose-700' : 'text-emerald-700'
                                  }`}
                                >
                                  {isUnbounded
                                    ? 'Without template (baseline)'
                                    : res.savings_vs_unbounded_pct > 0
                                      ? `-${res.savings_vs_unbounded_pct.toFixed(1)}% vs unbounded (same model)`
                                      : 'unbounded draft pending'}
                                </div>
                              </div>
                              <div>
                                <div className="text-[10px] font-bold uppercase text-slate-500">
                                  Monthly @ 100k/mo
                                </div>
                                <div className="mt-0.5 font-mono text-xl font-extrabold tabular-nums text-slate-900">
                                  ${f.monthly_cost_at_100k_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                                </div>
                                <div className="font-mono text-[11px] text-slate-500">
                                  In/Out: <strong>{f.io_ratio_label}</strong>
                                </div>
                              </div>
                            </div>

                            {/* Token & Output Share Strip */}
                            <div className="grid grid-cols-3 gap-1.5 text-center font-mono text-[11px]">
                              <div className="rounded-lg bg-slate-100 px-2 py-1.5">
                                <div className="text-[9px] font-bold text-slate-500">IN TOKENS</div>
                                <div className="font-bold text-slate-900">{f.input_tokens.toLocaleString()}</div>
                              </div>
                              <div className="rounded-lg bg-slate-100 px-2 py-1.5">
                                <div className="text-[9px] font-bold text-slate-500">OUT TOKENS</div>
                                <div className={`font-bold ${isUnbounded ? 'text-rose-700' : 'text-slate-900'}`}>
                                  {f.output_tokens.toLocaleString()}
                                </div>
                              </div>
                              <div
                                className={`rounded-lg px-2 py-1.5 ${
                                  f.output_cost_share_pct >= 75 ? 'bg-rose-100' : 'bg-slate-100'
                                }`}
                              >
                                <div className="text-[9px] font-bold text-slate-600">OUT COST %</div>
                                <div
                                  className={`font-bold ${
                                    f.output_cost_share_pct >= 75 ? 'text-rose-800' : 'text-slate-900'
                                  }`}
                                >
                                  {f.output_cost_share_pct}%
                                </div>
                              </div>
                            </div>

                            {isUnbounded && res.raw_markdown ? (
                              <div className="rounded-xl border border-rose-200 bg-rose-50/40 p-3">
                                <div className="flex items-center justify-between gap-2">
                                  <span className="text-[11px] font-bold text-rose-900">
                                    Unbounded long-form draft ({f.output_tokens} out tok)
                                  </span>
                                  <button
                                    type="button"
                                    onClick={() =>
                                      setExpandedRungs((prev) => ({
                                        ...prev,
                                        [res.rung_id]: !prev[res.rung_id],
                                      }))
                                    }
                                    className="inline-flex items-center gap-1 text-[11px] font-bold text-rose-700 hover:underline"
                                  >
                                    {expanded ? (
                                      <>
                                        Collapse <ChevronUp className="h-3 w-3" />
                                      </>
                                    ) : (
                                      <>
                                        Inspect Prose <ChevronDown className="h-3 w-3" />
                                      </>
                                    )}
                                  </button>
                                </div>
                                <pre
                                  className={`mt-2 whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-slate-700 ${
                                    expanded ? 'max-h-72 overflow-y-auto' : 'line-clamp-5'
                                  }`}
                                >
                                  {res.raw_markdown}
                                </pre>
                              </div>
                            ) : (
                              <div className="space-y-2.5 rounded-xl border border-slate-200 bg-slate-50/70 p-3">
                                <div className="text-[11px] font-extrabold text-slate-900">
                                  {draft.executive_summary.headline}
                                </div>
                                <p className="line-clamp-3 text-[11px] leading-relaxed text-slate-600">
                                  {draft.executive_summary.narrative}
                                </p>
                                <div className="flex flex-wrap gap-1.5 font-mono text-[10px]">
                                  <span className="rounded bg-white px-2 py-0.5 ring-1 ring-slate-200">
                                    {draft.key_findings.length} Findings
                                  </span>
                                  <span className="rounded bg-white px-2 py-0.5 ring-1 ring-slate-200">
                                    {draft.risk_and_compliance_matrix.length} Risks
                                  </span>
                                  <span className="rounded bg-white px-2 py-0.5 ring-1 ring-slate-200">
                                    {draft.action_plan.length} Actions
                                  </span>
                                </div>
                                <button
                                  type="button"
                                  onClick={() =>
                                    handleOpenInStudio(
                                      res.rung_id === 'haiku_templated'
                                        ? 'haiku_templated'
                                        : 'sonnet_templated'
                                    )
                                  }
                                  className={`mt-1 inline-flex w-full items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-extrabold text-white transition ${
                                    isTemplatedSonnet
                                      ? 'bg-emerald-700 hover:bg-emerald-800'
                                      : 'bg-emerald-600 hover:bg-emerald-700'
                                  }`}
                                >
                                  <Scissors className="h-3.5 w-3.5" />
                                  Open in HITL Section Studio →
                                </button>
                              </div>
                            )}
                          </div>
                        )}
                      </div>

                      <div className="border-t border-slate-100 px-4 py-3 text-[11px] text-slate-600">
                        <ul className="space-y-1">
                          {res.architectural_notes.map((n, idx) => (
                            <li key={idx} className="flex gap-1.5">
                              <span className="font-bold text-slate-400">•</span>
                              <span>{n}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Draft quality vs cost (blind-judge summary in replay mode; free checks only in live mode) */}
              <Cat2QualityPanel results={runResponse.results} portfolio={runResponse.quality_portfolio} />

              {/* Category 2 FinOps HUD: Input vs 5x Output Weight */}
              <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
                <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-200 pb-4">
                  <div>
                    <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-red-700">
                      <DollarSign className="h-4 w-4" />
                      Category 2 FinOps HUD · Output-Dominated Cost Mechanics
                    </div>
                    <h2 className="mt-0.5 text-lg font-extrabold text-slate-900">
                      Output Is Priced at 5x Input: Where Each Version's Cost Goes
                    </h2>
                  </div>

                  <div className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-0.5 text-xs">
                    <button
                      type="button"
                      onClick={() => setScaleMode('linear')}
                      className={`rounded-md px-2.5 py-1 font-semibold transition ${
                        scaleMode === 'linear' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600'
                      }`}
                    >
                      Linear Scale
                    </button>
                    <button
                      type="button"
                      onClick={() => setScaleMode('log')}
                      className={`rounded-md px-2.5 py-1 font-semibold transition ${
                        scaleMode === 'log' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600'
                      }`}
                    >
                      Log Scale
                    </button>
                  </div>
                </div>

                {/* Volume Slider */}
                <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <label htmlFor="cat2-volume-slider" className="text-xs font-bold text-slate-700">
                      Projected Monthly Drafting Volume:{' '}
                      <span className="font-mono text-red-700">{VOLUME_STEPS[volumeIdx].label}</span>
                    </label>
                    {annualTemplateSaved > 0 && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-3 py-1 font-mono text-xs font-bold text-emerald-900">
                        <TrendingDown className="h-3.5 w-3.5" />
                        Annualized Savings (Sonnet 5.5 + Templates, cost only): $
                        {annualTemplateSaved.toLocaleString(undefined, { maximumFractionDigits: 0 })}/yr
                      </span>
                    )}
                  </div>
                  <input
                    id="cat2-volume-slider"
                    type="range"
                    min={0}
                    max={VOLUME_STEPS.length - 1}
                    step={1}
                    value={volumeIdx}
                    onChange={(e) => setVolumeIdx(Number(e.target.value))}
                    className="mt-3 w-full accent-red-600"
                  />
                  <div className="mt-1 flex justify-between font-mono text-[10px] text-slate-500">
                    {VOLUME_STEPS.map((s, idx) => (
                      <span key={s.value} className={idx === volumeIdx ? 'font-bold text-red-700' : ''}>
                        {s.label.split(' ')[0]}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Charts Grid */}
                <div className="mt-5 grid gap-6 lg:grid-cols-2">
                  <div className="rounded-xl border border-slate-200 p-4">
                    <h3 className="mb-2 text-xs font-extrabold uppercase tracking-wider text-slate-700">
                      Unit Cost per 1,000 Drafts (USD · {scaleMode === 'log' ? 'Log10' : 'Linear'})
                    </h3>
                    <div className="h-64 w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={finopsRows}
                          layout="vertical"
                          margin={{ top: 8, right: 64, left: 12, bottom: 8 }}
                        >
                          <defs>
                            <pattern id="cat2-batch-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                              <rect width="6" height="6" fill="#a7f3d0" />
                              <line x1="0" y1="0" x2="0" y2="6" stroke="#10b981" strokeWidth="2.5" />
                            </pattern>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
                          <XAxis
                            type="number"
                            scale={scaleMode}
                            domain={scaleMode === 'log' ? [0.05, 'auto'] : [0, 'auto']}
                            tickFormatter={(v: number) => `$${v}`}
                            tick={{ fontSize: 11, fill: '#475569' }}
                          />
                          <YAxis
                            type="category"
                            dataKey="shortLabel"
                            interval={0}
                            width={118}
                            tick={{ fontSize: 11, fill: '#0f172a', fontWeight: 600 }}
                          />
                          <Tooltip
                            formatter={(_val: unknown, _name: unknown, props: { payload?: { costPer1k: number } }) => [
                              `$${props.payload?.costPer1k.toFixed(2)} / 1k drafts`,
                              'Unit Cost',
                            ]}
                          />
                          <Bar dataKey="chartValue" radius={[0, 6, 6, 0]}>
                            {finopsRows.map((entry) => (
                              <Cell key={entry.id} fill={entry.color} />
                            ))}
                            <LabelList
                              dataKey="costPer1k"
                              position="right"
                              formatter={(v: number) => `$${v.toFixed(2)}`}
                              style={{ fontSize: 11, fontFamily: 'monospace', fontWeight: 700, fill: '#0f172a' }}
                            />
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  <div className="rounded-xl border border-slate-200 p-4">
                    <h3 className="mb-2 text-xs font-extrabold uppercase tracking-wider text-slate-700">
                      Input Cost (1x) vs. Output Cost (5x Multiplier) per 1,000 Drafts
                    </h3>
                    <div className="h-64 w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={finopsRows} margin={{ top: 10, right: 20, left: 0, bottom: 8 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                          {/* interval 0: every bar keeps its label; labels wrap to two lines instead of being thinned */}
                          <XAxis
                            dataKey="shortLabel"
                            interval={0}
                            height={48}
                            tick={<WrappedAxisTick maxChars={9} maxLines={3} fill="#0f172a" />}
                          />
                          <YAxis tickFormatter={(v: number) => `$${v}`} tick={{ fontSize: 11, fill: '#475569' }} />
                          <Tooltip formatter={(val: number) => `$${val.toFixed(2)} / 1k`} />
                          <Legend wrapperStyle={{ fontSize: 11 }} />
                          {/* series are cost parts, not versions: neutral greys so red/green keep meaning without/with */}
                          <Bar dataKey="inputCost1k" name="Input Cost / 1k (1x)" stackId="a" fill="#94a3b8" />
                          <Bar
                            dataKey="outputCost1k"
                            name="Output Cost / 1k (5x Rate)"
                            stackId="a"
                            fill="#334155"
                            radius={[6, 6, 0, 0]}
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </div>

                {/* Projected Monthly Spend Strip */}
                <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {finopsRows.map((c) => (
                    <div
                      key={c.id}
                      className="rounded-xl border border-slate-200 bg-slate-50/70 p-3"
                      style={{
                        borderTopWidth: '3px',
                        // the computed Batch row is drawn hatched in the chart; its strip uses the pale green of that hatch
                        borderTopStyle: c.color.startsWith('url(') ? 'dashed' : 'solid',
                        borderTopColor: c.color.startsWith('url(') ? '#34d399' : c.color,
                      }}
                    >
                      <div className="truncate text-[11px] font-bold text-slate-700">{c.name}</div>
                      <div className="mt-1 font-mono text-base font-extrabold tabular-nums text-slate-900">
                        ${c.monthlyUsd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        <span className="text-[11px] font-normal text-slate-500"> /mo</span>
                      </div>
                      <div className="font-mono text-[10px] text-slate-500">
                        ${c.annualUsd.toLocaleString(undefined, { maximumFractionDigits: 0 })} /yr
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            </>
          )}
        </div>
      </div>

      {/* TAB PANEL 2: INTERACTIVE HITL SECTION STUDIO */}
      <div role="tabpanel" aria-labelledby="cat2-tab-studio" hidden={activeView !== 'studio'}>
        <div className="space-y-5">
          {/* Studio Top Controls + HITL Revision Ledger */}
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-extrabold text-slate-900">
                  Interactive HITL Section Studio · Side-by-Side Grounding &amp; Surgical Revisions
                </h2>
                <p className="mt-0.5 text-xs text-slate-600">
                  Approve &amp; lock verified sections, inline-edit copy directly, or regenerate{' '}
                  <strong>only one unlocked section</strong> instead of paying for a full template re-draft.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => handleOpenInStudio('sonnet_templated')}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-bold transition ${
                    studioSourceRung === 'sonnet_templated'
                      ? 'border-emerald-700 bg-emerald-50 text-emerald-900'
                      : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  Load Sonnet 5.5 template draft
                </button>
                <button
                  type="button"
                  onClick={() => handleOpenInStudio('haiku_templated')}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-bold transition ${
                    studioSourceRung === 'haiku_templated'
                      ? 'border-emerald-600 bg-emerald-50 text-emerald-900'
                      : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  Load Haiku 5.5 template draft
                </button>
              </div>
            </div>

            {/* Live HITL Revision FinOps Ledger */}
            <div className="mt-4 grid gap-3 rounded-xl border border-slate-200 bg-slate-950 p-4 text-white sm:grid-cols-4">
              <div>
                <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Sections Approved &amp; Locked
                </div>
                <div className="mt-0.5 font-mono text-lg font-extrabold text-emerald-400">
                  {lockedCount} / 4
                </div>
                <div className="text-[10px] text-slate-400">Protected from LLM regressions</div>
              </div>
              <div>
                <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Surgical Section Edits Run
                </div>
                <div className="mt-0.5 font-mono text-lg font-extrabold text-white">
                  {hitlTotals.count}
                </div>
                <div className="text-[10px] text-slate-400">
                  {hitlTotals.tokensAvoided.toLocaleString()} output/history tokens avoided
                </div>
              </div>
              <div>
                <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Cumulative Surgical Spend
                </div>
                <div className="mt-0.5 font-mono text-lg font-extrabold text-sky-300">
                  ${hitlTotals.surgicalTotal.toFixed(4)}
                </div>
                <div className="text-[10px] text-slate-400">
                  Section regeneration calls (input + output)
                </div>
              </div>
              <div>
                <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  vs. Full Template Re-Drafts (same model)
                </div>
                <div className="mt-0.5 font-mono text-lg font-extrabold text-rose-300">
                  {hitlTotals.count > 0 ? `$${hitlTotals.naiveTotal.toFixed(4)}` : '$0.0000'}
                </div>
                <div className="text-[10px] font-bold text-emerald-300">
                  {hitlTotals.count > 0
                    ? `-${hitlTotals.savedPct.toFixed(1)}% revision spend saved`
                    : 'Click "Regenerate Only This Section" below'}
                </div>
              </div>
            </div>
          </section>

          {workingDraft && (
            <div className="grid gap-5 lg:grid-cols-[360px_minmax(0,1fr)]">
              {/* Left Sticky Grounding Source */}
              <aside className="lg:sticky lg:top-20 lg:self-start">
                <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex items-center justify-between gap-2 border-b border-slate-200 pb-2.5">
                    <div className="flex items-center gap-1.5 text-xs font-extrabold text-slate-900">
                      <FileText className="h-4 w-4 text-red-600" />
                      Grounding Source ({selectedPresetId})
                    </div>
                    <span className="font-mono text-[10px] text-slate-500">
                      {payloadText.length.toLocaleString()} chars
                    </span>
                  </div>
                  <pre className="mt-3 max-h-[600px] overflow-y-auto whitespace-pre-wrap break-words rounded-xl bg-slate-950 p-3 font-mono text-[11px] leading-relaxed text-slate-200">
                    {payloadText}
                  </pre>
                </div>
              </aside>

              {/* Right Column: 4 Template Section Cards */}
              <div className="space-y-4">
                <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-2xs">
                  <div className="font-mono text-[10px] font-bold uppercase text-slate-500">
                    {workingDraft.document_type} · Active Studio Draft ({studioSourceRung})
                  </div>
                  <div className="mt-0.5 text-base font-extrabold text-slate-900">
                    {workingDraft.document_title}
                  </div>
                </div>

                {SECTION_META.map((secMeta) => {
                  const secKey = secMeta.key
                  const isLocked = lockedSections[secKey]
                  const isEditing = editingSections[secKey]
                  const isLoading = regenLoading === secKey
                  const latestRegen = lastRegenBySection[secKey]
                  const presetInstr = presetsData.reviewer_presets[secKey]

                  return (
                    <section
                      key={secKey}
                      className={`rounded-2xl border bg-white p-5 shadow-sm transition ${
                        isLocked ? 'border-emerald-300 ring-1 ring-emerald-200' : 'border-slate-200'
                      }`}
                    >
                      {/* Section Header + Lock/Edit Controls */}
                      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <h3 className="text-sm font-extrabold text-slate-900">{secMeta.title}</h3>
                            {isLocked && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                                <CheckCircle2 className="h-3 w-3" />
                                Locked &amp; Approved
                              </span>
                            )}
                          </div>
                          <p className="mt-0.5 text-[11px] text-slate-500">{secMeta.subtitle}</p>
                        </div>

                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            disabled={isLocked}
                            onClick={() => toggleSectionEdit(secKey)}
                            className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-[11px] font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                          >
                            <Edit3 className="h-3.5 w-3.5" />
                            {isEditing ? 'Cancel Edit' : 'Edit Inline ($0)'}
                          </button>

                          <button
                            type="button"
                            onClick={() => {
                              setEditingSections((prev) => ({ ...prev, [secKey]: false }))
                              setLockedSections((prev) => ({ ...prev, [secKey]: !prev[secKey] }))
                            }}
                            className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-bold transition ${
                              isLocked
                                ? 'bg-emerald-600 text-white hover:bg-emerald-700'
                                : 'border border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100'
                            }`}
                          >
                            {isLocked ? (
                              <>
                                <Lock className="h-3.5 w-3.5" />
                                Unlock Section
                              </>
                            ) : (
                              <>
                                <Unlock className="h-3.5 w-3.5" />
                                Approve &amp; Lock
                              </>
                            )}
                          </button>
                        </div>
                      </div>

                      {/* Section Body (or Inline JSON Editor with auto-sizing textarea) */}
                      <div className="mt-3">
                        {isEditing ? (
                          <div className="space-y-2">
                            <label
                              htmlFor={`edit-${secKey}`}
                              className="block text-[11px] font-bold text-slate-700"
                            >
                              Direct Human Inline Edit (Structured Section JSON · $0 API Spend)
                            </label>
                            <textarea
                              id={`edit-${secKey}`}
                              rows={6}
                              value={sectionDraftJson[secKey]}
                              onChange={(e) =>
                                setSectionDraftJson((prev) => ({
                                  ...prev,
                                  [secKey]: e.target.value,
                                }))
                              }
                              className="mwg-auto-textarea rounded-xl border border-slate-300 bg-slate-950 p-3 font-mono text-xs leading-relaxed text-emerald-300 focus:border-red-500 focus:outline-none"
                            />
                            <div className="flex justify-end">
                              <button
                                type="button"
                                onClick={() => saveInlineSectionEdit(secKey)}
                                className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-bold text-white hover:bg-slate-800"
                              >
                                Save Inline Changes
                              </button>
                            </div>
                          </div>
                        ) : (
                          <>
                            {secKey === 'executive_summary' && (
                              <div className="space-y-2.5 rounded-xl bg-slate-50 p-4">
                                <div className="text-sm font-extrabold text-slate-900">
                                  {workingDraft.executive_summary.headline}
                                </div>
                                <p className="text-xs leading-relaxed text-slate-700">
                                  {workingDraft.executive_summary.narrative}
                                </p>
                                <div className="rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-semibold text-red-950">
                                  <span className="font-bold">Bottom Line:</span>{' '}
                                  {workingDraft.executive_summary.bottom_line_impact}
                                </div>
                              </div>
                            )}

                            {secKey === 'key_findings' && (
                              <div className="grid gap-2.5 sm:grid-cols-2">
                                {workingDraft.key_findings.map((fItem, i) => (
                                  <div
                                    key={`${fItem.id}-${i}`}
                                    className="rounded-xl border border-slate-200 bg-slate-50/70 p-3"
                                  >
                                    <div className="flex items-center justify-between gap-2">
                                      <span className="font-mono text-[10px] font-bold text-red-700">
                                        {fItem.id}
                                      </span>
                                      <span className="rounded bg-white px-1.5 py-0.5 font-mono text-[10px] text-slate-500 ring-1 ring-slate-200">
                                        {fItem.source_anchor}
                                      </span>
                                    </div>
                                    <div className="mt-1 text-xs font-extrabold text-slate-900">
                                      {fItem.theme}
                                    </div>
                                    <p className="mt-1 text-[11px] leading-relaxed text-slate-700">
                                      {fItem.quantified_evidence}
                                    </p>
                                  </div>
                                ))}
                              </div>
                            )}

                            {secKey === 'risk_and_compliance_matrix' && (
                              <div
                                tabIndex={0}
                                role="region"
                                aria-labelledby="cat2-risk-matrix-heading"
                                className="table-wrapper rounded-xl border border-slate-200"
                              >
                                <h4 id="cat2-risk-matrix-heading" className="sr-only">
                                  Risk and Compliance Matrix
                                </h4>
                                <table
                                  className="mwg-table text-left text-xs"
                                  data-table="cat2-risks"
                                  style={
                                    {
                                      '--label-2': '"Severity"',
                                      '--label-3': '"Exposure"',
                                      '--label-4': '"Mitigation"',
                                    } as React.CSSProperties
                                  }
                                >
                                  <caption className="sr-only">
                                    Structured risk domains, severity ratings, financial/regulatory exposure, and mitigation controls.
                                  </caption>
                                  <thead className="bg-slate-900 text-[11px] font-bold uppercase tracking-wider text-slate-200">
                                    <tr>
                                      <th className="px-3.5 py-2.5">Domain</th>
                                      <th className="px-3.5 py-2.5">Severity</th>
                                      <th className="px-3.5 py-2.5">Exposure Summary</th>
                                      <th className="px-3.5 py-2.5">Mitigation Control</th>
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-slate-200 bg-white">
                                    {workingDraft.risk_and_compliance_matrix.map((row, idx) => (
                                      <tr key={`${row.domain}-${idx}`} className="hover:bg-slate-50">
                                        <th scope="row" className="px-3.5 py-2.5 text-left font-bold text-slate-900">
                                          {row.domain}
                                        </th>
                                        <td className="px-3.5 py-2.5 font-mono text-[11px] font-bold">
                                          <span
                                            className={`rounded px-2 py-0.5 ${
                                              row.severity === 'CRITICAL'
                                                ? 'bg-rose-100 text-rose-800'
                                                : row.severity === 'HIGH'
                                                  ? 'bg-amber-100 text-amber-900'
                                                  : 'bg-slate-100 text-slate-700'
                                            }`}
                                          >
                                            {row.severity}
                                          </span>
                                        </td>
                                        <td className="px-3.5 py-2.5 text-[11px] leading-relaxed text-slate-700">
                                          {row.exposure_summary}
                                        </td>
                                        <td className="px-3.5 py-2.5 text-[11px] leading-relaxed text-slate-700">
                                          {row.mitigation_control}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            )}

                            {secKey === 'action_plan' && (
                              <div className="space-y-2">
                                {workingDraft.action_plan.map((act, idx) => (
                                  <div
                                    key={`${act.owner}-${idx}`}
                                    className="rounded-xl border border-slate-200 bg-slate-50/70 p-3 text-xs"
                                  >
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                      <span className="font-extrabold text-slate-900">{act.owner}</span>
                                      <span className="rounded bg-blue-100 px-2 py-0.5 font-mono text-[10px] font-bold text-blue-900">
                                        {act.target_window}
                                      </span>
                                    </div>
                                    <p className="mt-1 text-[11px] text-slate-700">{act.milestone}</p>
                                    <div className="mt-1 font-mono text-[10px] text-slate-500">
                                      Exit Metric: {act.verification_metric}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </>
                        )}
                      </div>

                      {/* Surgical HITL Section Regenerator Controls */}
                      <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="text-[11px] font-extrabold text-slate-800">
                            Surgical Section Regeneration (Regenerate ONLY `{secKey}`)
                          </span>
                          <button
                            type="button"
                            disabled={isLocked}
                            onClick={() =>
                              setRegenInstructions((prev) => ({
                                ...prev,
                                [secKey]: presetInstr.instruction,
                              }))
                            }
                            className="rounded-md bg-white px-2 py-0.5 text-[10px] font-bold text-red-700 ring-1 ring-red-200 hover:bg-red-50 disabled:opacity-40"
                          >
                            Apply Preset: {presetInstr.label}
                          </button>
                        </div>

                        <div className="mt-2 grid gap-2 sm:grid-cols-[1fr_auto_auto]">
                          <textarea
                            aria-label={`Reviewer instruction for ${secMeta.title}`}
                            rows={2}
                            disabled={isLocked}
                            value={regenInstructions[secKey]}
                            onChange={(e) =>
                              setRegenInstructions((prev) => ({
                                ...prev,
                                [secKey]: e.target.value,
                              }))
                            }
                            className="mwg-auto-textarea rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-800 focus:border-red-500 focus:outline-none disabled:bg-slate-100"
                          />

                          <select
                            aria-label={`Model tier for ${secMeta.title}`}
                            disabled={isLocked}
                            value={regenModels[secKey]}
                            onChange={(e) =>
                              setRegenModels((prev) => ({
                                ...prev,
                                [secKey]: e.target.value as Cat2ModelTier,
                              }))
                            }
                            className="self-start rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-xs font-semibold text-slate-800 disabled:bg-slate-100"
                          >
                            <option value="claude-sonnet-5-5">Sonnet 5.5 (higher cost)</option>
                            <option value="claude-haiku-5-5">Haiku 5.5 (lower cost)</option>
                          </select>

                          <button
                            type="button"
                            disabled={isLocked || isLoading}
                            onClick={() => void handleSurgicalRegen(secKey)}
                            className="inline-flex items-center justify-center gap-1.5 self-start rounded-lg bg-red-600 px-3.5 py-2 text-xs font-extrabold text-white shadow-xs transition hover:bg-red-700 disabled:opacity-40"
                          >
                            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
                            {isLoading ? 'Regenerating...' : 'Regenerate Only This Section'}
                          </button>
                        </div>

                        {latestRegen && (
                          <div className="mt-2.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[11px] font-medium text-emerald-950">
                            <strong>Surgical Edit Captured ({latestRegen.model_used}):</strong>{' '}
                            {latestRegen.finops_comparison.explanation}
                          </div>
                        )}
                      </div>
                    </section>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Architecture & SDK Inspector Modal */}
      <NativeModal
        open={inspectorOpen}
        onClose={() => setInspectorOpen(false)}
        title="Category 2 Architecture & SDK Inspector"
        subtitle="Inspect Anthropic SDK prompts, Section-Bounded JSON Schema, and Surgical HITL Edit pattern"
        maxWidthClass="max-w-3xl"
      >
        <div className="space-y-4">
          <div
            role="tablist"
            aria-label="Category 2 inspector sections"
            onKeyDown={handleInspectorTabKeyDown}
            className="mwg-tablist border-b border-slate-200"
          >
            {(
              [
                ['code', 'Python SDK Comparison'],
                ['schema', 'Section-Templated JSON Schema'],
              ] as const
            ).map(([tid, label]) => (
              <button
                key={tid}
                type="button"
                role="tab"
                id={`cat2-insp-tab-${tid}`}
                aria-selected={inspectorTab === tid}
                tabIndex={inspectorTab === tid ? 0 : -1}
                onClick={() => setInspectorTab(tid)}
                className={`mwg-tab px-4 py-2 text-xs font-bold ${
                  inspectorTab === tid ? 'text-red-700' : 'text-slate-500 hover:text-slate-900'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div role="tabpanel" aria-labelledby="cat2-insp-tab-code" hidden={inspectorTab !== 'code'}>
            <div className="space-y-3">
              {Object.entries(presetsData.code_snippets).map(([key, snippet]) => (
                <div key={key} className="rounded-xl border border-slate-200 bg-slate-950 p-3.5">
                  <pre className="overflow-x-auto font-mono text-[11px] leading-relaxed text-slate-100">
                    {snippet}
                  </pre>
                </div>
              ))}
            </div>
          </div>

          <div role="tabpanel" aria-labelledby="cat2-insp-tab-schema" hidden={inspectorTab !== 'schema'}>
            <pre className="max-h-96 overflow-auto rounded-xl bg-slate-950 p-3.5 font-mono text-[11px] leading-relaxed text-emerald-300">
              {JSON.stringify(presetsData.schema, null, 2)}
            </pre>
          </div>
        </div>
      </NativeModal>
    </div>
  )
}
