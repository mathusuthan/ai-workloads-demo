import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertCircle,
  ArrowLeft,
  Bot,
  Code2,
  Cpu,
  Database,
  DollarSign,
  Layers,
  Play,
  Send,
  SkipForward,
  Sparkles,
  TrendingDown,
  User,
  Zap,
} from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { runCat3Arena, sendCat3ChatTurn } from '../api'
import type {
  ArchetypeSpec,
  Cat3ChatTurnEntry,
  Cat3PresetsResponse,
  Cat3RungId,
  Cat3RungSummary,
  Cat3RunResponse,
  Cat3TurnResult,
  CreditShieldCredentials,
} from '../types'
import { NativeModal } from './NativeModal'

interface Cat3WorkbenchProps {
  archetype: ArchetypeSpec
  presetsData: Cat3PresetsResponse
  creds: CreditShieldCredentials
  onRefreshSystemStatus: () => void
}

const CAT3_RUNGS: Cat3RungId[] = [
  'naive_full_history',
  'prefix_cached_history',
  'prefix_cached_summarized',
]

const VOLUME_STEPS = [
  { label: '5k / mo (Pilot Desk)', value: 5_000 },
  { label: '25k / mo (Mid-Size Ops)', value: 25_000 },
  { label: '100k / mo (NovaMart Steady)', value: 100_000 },
  { label: '250k / mo (Peak Season)', value: 250_000 },
  { label: '1M / mo (Enterprise Scale)', value: 1_000_000 },
]

// Canonical Sonnet 5.5 rates ($/1M tok) matching backend/app/core/pricing.py
const SONNET_RATE = {
  inPer1M: 2.0,
  outPer1M: 10.0,
  writePer1M: 2.5,
  readPer1M: 0.2,
} as const

type CacheEntryMode = 'cold_first_turn' | 'warm_fleet_prefix'
type LineChartMetricMode = 'per_turn_cents' | 'cumulative_1k'

interface SlicedRungMetrics {
  rungId: Cat3RungId
  rungTitle: string
  badgeText: string
  modelId: string
  sessionCostUsd: number
  costPer1kSessionsUsd: number
  uncachedInTokens: number
  cacheWriteTokens: number
  cacheReadTokens: number
  outputTokens: number
  summarizerCalls: number
  summarizerInTokens: number
  summarizerOutTokens: number
  summarizerCostUsd: number
  uncachedInputCost1k: number
  cacheCost1k: number
  outputCost1k: number
  summarizerCost1k: number
  turnsSlice: Cat3TurnResult[]
}

function sliceRungMetrics(
  rung: Cat3RungSummary,
  maxTurn: number,
  cacheMode: CacheEntryMode
): SlicedRungMetrics {
  const slice = rung.turns.slice(0, maxTurn)
  const uncachedInTokens = slice.reduce((acc, t) => acc + t.finops.input_tokens, 0)
  const rawWriteTokens = slice.reduce((acc, t) => acc + t.finops.cache_creation_tokens, 0)
  const rawReadTokens = slice.reduce((acc, t) => acc + t.finops.cache_read_tokens, 0)
  const outputTokens = slice.reduce((acc, t) => acc + t.finops.output_tokens, 0)

  const cacheWriteTokens = cacheMode === 'warm_fleet_prefix' ? 0 : rawWriteTokens
  const cacheReadTokens =
    cacheMode === 'warm_fleet_prefix' ? rawReadTokens + rawWriteTokens : rawReadTokens

  const summarizerTurns = slice.filter((t) => t.compaction_finops !== null)
  const summarizerCalls = summarizerTurns.length
  const summarizerInTokens = summarizerTurns.reduce(
    (acc, t) => acc + (t.compaction_finops?.input_tokens ?? 0),
    0
  )
  const summarizerOutTokens = summarizerTurns.reduce(
    (acc, t) => acc + (t.compaction_finops?.output_tokens ?? 0),
    0
  )
  const summarizerCostUsd = summarizerTurns.reduce(
    (acc, t) => acc + (t.compaction_finops?.total_cost_usd ?? 0),
    0
  )

  const uncachedInputCost = (uncachedInTokens / 1_000_000) * SONNET_RATE.inPer1M
  const cacheCost =
    (cacheWriteTokens / 1_000_000) * SONNET_RATE.writePer1M +
    (cacheReadTokens / 1_000_000) * SONNET_RATE.readPer1M
  const outputCost = (outputTokens / 1_000_000) * SONNET_RATE.outPer1M

  const lastTurn = slice[slice.length - 1]
  const sessionCostUsd = lastTurn
    ? cacheMode === 'warm_fleet_prefix'
      ? lastTurn.cumulative_warm_cost_usd
      : lastTurn.cumulative_cost_usd
    : 0

  return {
    rungId: rung.rung_id,
    rungTitle: rung.rung_title,
    badgeText: rung.badge_text,
    modelId: rung.model_id,
    sessionCostUsd,
    costPer1kSessionsUsd: Number((sessionCostUsd * 1000).toFixed(2)),
    uncachedInTokens,
    cacheWriteTokens,
    cacheReadTokens,
    outputTokens,
    summarizerCalls,
    summarizerInTokens,
    summarizerOutTokens,
    summarizerCostUsd,
    uncachedInputCost1k: Number((uncachedInputCost * 1000).toFixed(2)),
    cacheCost1k: Number((cacheCost * 1000).toFixed(2)),
    outputCost1k: Number((outputCost * 1000).toFixed(2)),
    summarizerCost1k: Number((summarizerCostUsd * 1000).toFixed(2)),
    turnsSlice: slice,
  }
}

function splitUserTurnTelemetry(rawUserMessage: string): {
  promptText: string
  telemetryBlock: string | null
  telemetryHeading: string | null
} {
  const markerIdx = rawUserMessage.indexOf('\n=== ')
  if (markerIdx === -1) {
    return { promptText: rawUserMessage, telemetryBlock: null, telemetryHeading: null }
  }
  const promptText = rawUserMessage.slice(0, markerIdx).trim()
  const rest = rawUserMessage.slice(markerIdx).trim()
  const firstLineEnd = rest.indexOf('\n')
  const telemetryHeading =
    firstLineEnd !== -1
      ? rest.slice(0, firstLineEnd).replace(/^===\s*/, '').replace(/\s*===$/, '')
      : 'Attached Telemetry & Logs'
  const telemetryBlock = firstLineEnd !== -1 ? rest.slice(firstLineEnd + 1).trim() : rest
  return { promptText, telemetryBlock, telemetryHeading }
}

export function Cat3Workbench({
  archetype,
  presetsData,
  creds,
  onRefreshSystemStatus,
}: Cat3WorkbenchProps) {
  const [activeView, setActiveView] = useState<'arena' | 'simulator'>('arena')
  const [selectedPresetId, setSelectedPresetId] = useState<string>(
    presetsData.presets[0]?.id ?? 'desk-01'
  )
  const [runResponse, setRunResponse] = useState<Cat3RunResponse | null>(null)
  const [loadingArena, setLoadingArena] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // Arena HUD controls
  const [selectedMaxTurn, setSelectedMaxTurn] = useState<number>(10)
  const [cacheMode, setCacheMode] = useState<CacheEntryMode>('cold_first_turn')
  const [lineMetricMode, setLineMetricMode] = useState<LineChartMetricMode>('per_turn_cents')
  const [volumeIdx, setVolumeIdx] = useState<number>(2) // 100k/mo default
  const [tableRungId, setTableRungId] = useState<Cat3RungId>('prefix_cached_summarized')

  // Interactive Service Desk Simulator & X-Ray state
  const [simRungId, setSimRungId] = useState<Cat3RungId>('prefix_cached_summarized')
  const [simTurnCount, setSimTurnCount] = useState<number>(10)
  const [liveExtraTurns, setLiveExtraTurns] = useState<Cat3TurnResult[]>([])
  const [liveVerbatimWindow, setLiveVerbatimWindow] = useState<Cat3ChatTurnEntry[] | null>(null)
  const [liveMemorySummary, setLiveMemorySummary] = useState<Record<string, unknown> | null>(null)
  const [followUpText, setFollowUpText] = useState<string>('')
  const [sendingFollowUp, setSendingFollowUp] = useState<boolean>(false)

  // Inspector Modal
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [inspectorTab, setInspectorTab] = useState<'code' | 'schema'>('code')

  const selectedPreset = useMemo(
    () => presetsData.presets.find((p) => p.id === selectedPresetId) ?? presetsData.presets[0],
    [presetsData.presets, selectedPresetId]
  )

  const executeArena = async (presetId: string = selectedPresetId) => {
    setLoadingArena(true)
    setErrorMsg(null)
    try {
      const resp = await runCat3Arena(
        {
          preset_id: presetId,
          use_case: 'it_hr_service_desk',
          rungs: CAT3_RUNGS,
          mode: creds.mode,
        },
        creds
      )
      setRunResponse(resp)
      setLiveExtraTurns([])
      setLiveVerbatimWindow(null)
      setLiveMemorySummary(null)
      if (resp.mode_used === 'live') {
        onRefreshSystemStatus()
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to run Category 3 Session Arena.')
    } finally {
      setLoadingArena(false)
    }
  }

  useEffect(() => {
    void executeArena(selectedPresetId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleSelectPreset = (presetId: string) => {
    setSelectedPresetId(presetId)
    setSimTurnCount(10)
    setFollowUpText('')
    void executeArena(presetId)
  }

  const handleViewTabKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault()
      const next = activeView === 'arena' ? 'simulator' : 'arena'
      setActiveView(next)
      document.getElementById(next === 'arena' ? 'cat3-tab-arena' : 'cat3-tab-simulator')?.focus()
    }
  }

  const handleInspectorTabKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault()
      const next = inspectorTab === 'code' ? 'schema' : 'code'
      setInspectorTab(next)
      document.getElementById(`cat3-insp-tab-${next}`)?.focus()
    }
  }

  // Sliced FinOps across all 3 rungs for Arena
  const slicedByRung = useMemo(() => {
    if (!runResponse) return []
    return runResponse.results
      .filter((r) => r.status === 'ok' && r.turns.length > 0)
      .map((r) => sliceRungMetrics(r, selectedMaxTurn, cacheMode))
  }, [runResponse, selectedMaxTurn, cacheMode])

  const naiveSlice = slicedByRung.find((s) => s.rungId === 'naive_full_history')
  const cachedSlice = slicedByRung.find((s) => s.rungId === 'prefix_cached_history')
  const compactSlice = slicedByRung.find((s) => s.rungId === 'prefix_cached_summarized')

  // Line Chart data: Per-Turn Cost (cents/turn) & Cumulative $/1k sessions
  const lineChartData = useMemo(() => {
    if (!runResponse) return []
    const byId = Object.fromEntries(runResponse.results.map((r) => [r.rung_id, r]))
    const rows: Array<Record<string, number | string>> = []
    for (let i = 0; i < selectedMaxTurn; i++) {
      const tNum = i + 1
      const r1 = byId.naive_full_history?.turns[i]
      const r2 = byId.prefix_cached_history?.turns[i]
      const r3 = byId.prefix_cached_summarized?.turns[i]

      const costFor = (t: Cat3TurnResult | undefined): number => {
        if (!t) return 0
        const turnBase =
          cacheMode === 'warm_fleet_prefix' && t.finops.cache_creation_tokens > 0
            ? ((t.finops.input_tokens * SONNET_RATE.inPer1M +
                (t.finops.cache_creation_tokens + t.finops.cache_read_tokens) *
                  SONNET_RATE.readPer1M +
                t.finops.output_tokens * SONNET_RATE.outPer1M) /
                1_000_000)
            : t.finops.total_cost_usd
        const sumCost = t.compaction_finops?.total_cost_usd ?? 0
        return turnBase + sumCost
      }

      const cumFor = (t: Cat3TurnResult | undefined): number => {
        if (!t) return 0
        return cacheMode === 'warm_fleet_prefix'
          ? t.cumulative_warm_cost_usd
          : t.cumulative_cost_usd
      }

      rows.push({
        turnLabel: `T${tNum}`,
        naiveValue:
          lineMetricMode === 'per_turn_cents'
            ? Number((costFor(r1) * 100).toFixed(3))
            : Number((cumFor(r1) * 1000).toFixed(2)),
        cachedValue:
          lineMetricMode === 'per_turn_cents'
            ? Number((costFor(r2) * 100).toFixed(3))
            : Number((cumFor(r2) * 1000).toFixed(2)),
        compactValue:
          lineMetricMode === 'per_turn_cents'
            ? Number((costFor(r3) * 100).toFixed(3))
            : Number((cumFor(r3) * 1000).toFixed(2)),
      })
    }
    return rows
  }, [runResponse, selectedMaxTurn, cacheMode, lineMetricMode])

  // Stacked bar chart data
  const stackedCostData = useMemo(() => {
    return slicedByRung.map((s) => ({
      name:
        s.rungId === 'naive_full_history'
          ? '1. Uncached Full'
          : s.rungId === 'prefix_cached_history'
            ? '2. Prefix Cache Only'
            : '3. Cache + Summary',
      uncachedIn1k: s.uncachedInputCost1k,
      cache1k: s.cacheCost1k,
      output1k: s.outputCost1k,
      summarizer1k: s.summarizerCost1k,
    }))
  }, [slicedByRung])

  const monthlyVol = VOLUME_STEPS[volumeIdx].value
  const annualSavingsUsd =
    naiveSlice && compactSlice
      ? Math.max(0, (naiveSlice.sessionCostUsd - compactSlice.sessionCostUsd) * monthlyVol * 12)
      : 0

  const inspectedTableRung =
    slicedByRung.find((s) => s.rungId === tableRungId) ?? compactSlice ?? slicedByRung[0]

  // Active Simulator data
  const activeSimSummary = runResponse?.results.find((r) => r.rung_id === simRungId)
  const simBaseTurns = useMemo(
    () => (activeSimSummary?.turns ?? []).slice(0, simTurnCount),
    [activeSimSummary, simTurnCount]
  )
  const combinedSimTurns = useMemo(
    () => (simTurnCount >= 10 ? [...simBaseTurns, ...liveExtraTurns] : simBaseTurns),
    [simBaseTurns, liveExtraTurns, simTurnCount]
  )
  const activeFocusTurn = combinedSimTurns[combinedSimTurns.length - 1]

  // X-Ray proportions on activeFocusTurn
  const xRayStats = useMemo(() => {
    const handbookTokens = runResponse?.approx_handbook_tokens ?? 9680
    const isUncached = simRungId === 'naive_full_history'
    const rawFocus = activeFocusTurn
    if (!rawFocus) {
      return {
        handbookCached: 0,
        handbookUncached: 0,
        memorySummaryTok: 0,
        verbatimTailTok: 0,
        evictedSavedTok: 0,
        memorySnapshot: null as Record<string, unknown> | null,
        verbatimRangeLabel: 'None',
      }
    }
    const promptTotal =
      rawFocus.finops.input_tokens +
      rawFocus.finops.cache_creation_tokens +
      rawFocus.finops.cache_read_tokens
    const handbookCached = isUncached
      ? 0
      : rawFocus.finops.cache_creation_tokens + rawFocus.finops.cache_read_tokens
    const memSnap = rawFocus.memory_summary_snapshot ?? null
    const memTok = memSnap ? Math.max(120, Math.round(JSON.stringify(memSnap).length / 1.85)) : 0
    const uncachedNonPrefix = isUncached
      ? Math.max(0, promptTotal - handbookTokens)
      : Math.max(0, rawFocus.finops.input_tokens - memTok)
    const handbookUncached = isUncached ? handbookTokens : 0

    // Counterfactual Rung 1 prompt size at same turn index (up to Turn 10) for evicted savings
    const naiveMatchTurn =
      runResponse?.results
        .find((r) => r.rung_id === 'naive_full_history')
        ?.turns.find((t) => t.turn_number === rawFocus.turn_number)
    const naivePromptTokens = naiveMatchTurn
      ? naiveMatchTurn.finops.input_tokens
      : promptTotal
    const evictedSavedTok =
      simRungId === 'prefix_cached_summarized' ? Math.max(0, naivePromptTokens - promptTotal) : 0

    const firstVerbatimTurn = Math.max(1, rawFocus.turn_number - rawFocus.active_history_turns)
    const verbatimRangeLabel =
      rawFocus.active_history_turns === 0
        ? `Turn ${rawFocus.turn_number} (current prompt)`
        : `Turns ${firstVerbatimTurn}–${rawFocus.turn_number} (${rawFocus.active_history_turns} prior + current)`

    return {
      handbookCached,
      handbookUncached,
      memorySummaryTok: memTok,
      verbatimTailTok: uncachedNonPrefix,
      evictedSavedTok,
      memorySnapshot: memSnap,
      verbatimRangeLabel,
    }
  }, [runResponse, activeFocusTurn, simRungId])

  const handleSendFollowUp = async (customText?: string) => {
    const text = (customText ?? followUpText).trim()
    if (!text || !selectedPreset) return
    setSendingFollowUp(true)
    setErrorMsg(null)
    try {
      const priorWindow: Cat3ChatTurnEntry[] =
        liveVerbatimWindow ??
        (() => {
          const allBase = activeSimSummary?.turns ?? []
          if (simRungId === 'prefix_cached_summarized') {
            // Match compacted window state at end of Turn 10: Turns 7..10 stay verbatim (len = 4)
            return allBase.slice(-4).map((t) => ({
              turn_number: t.turn_number,
              user_message: t.user_message,
              assistant_message: t.assistant_message,
            }))
          }
          return allBase.map((t) => ({
            turn_number: t.turn_number,
            user_message: t.user_message,
            assistant_message: t.assistant_message,
          }))
        })()

      const memSummary: Record<string, unknown> | null =
        liveMemorySummary ??
        (simRungId === 'prefix_cached_summarized'
          ? ((activeSimSummary?.turns[activeSimSummary.turns.length - 1]
              ?.memory_summary_snapshot as Record<string, unknown> | null) ?? null)
          : null)

      const resp = await sendCat3ChatTurn(
        {
          preset_id: selectedPreset.id,
          rung_id: simRungId,
          user_message: text,
          prior_turns: priorWindow,
          memory_summary: memSummary,
          mode: creds.mode,
        },
        creds
      )
      setSimTurnCount(10)
      setLiveExtraTurns((prev) => [...prev, resp.turn_result])
      setLiveVerbatimWindow(resp.updated_verbatim_turns)
      setLiveMemorySummary(resp.updated_memory_summary)
      setFollowUpText('')
      onRefreshSystemStatus()
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to send live Turn-11+ follow-up.')
    } finally {
      setSendingFollowUp(false)
    }
  }

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
          <Code2 className="h-4 w-4 text-emerald-700" />
          Architecture &amp; Code Inspector
        </button>
      </div>

      {/* Category 3 Banner (#15803D Forest Emerald) */}
      <section className="overflow-hidden rounded-2xl border border-emerald-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 bg-emerald-700 px-6 py-2.5 text-white">
          <div className="flex flex-wrap items-center gap-2 text-xs font-extrabold uppercase tracking-wider">
            <span>{archetype.category_label}</span>
            <span>·</span>
            <span>{archetype.autonomy_tier_label}</span>
            <span className="rounded bg-white/20 px-2 py-0.5 font-mono text-[11px]">
              {archetype.token_band}
            </span>
            <span>·</span>
            <span>IT &amp; HR Service Desk</span>
          </div>
          <span className="font-mono text-xs font-bold text-emerald-100">
            Claude Sonnet 5.5 · {archetype.dynamics}
          </span>
        </div>

        <div className="flex flex-col justify-between gap-4 px-6 py-5 lg:flex-row lg:items-center">
          <div>
            <h1 className="text-xl font-extrabold tracking-tight text-slate-900 sm:text-2xl">
              {archetype.title} — {archetype.novamart_product_name}
            </h1>
            <p className="mt-1 max-w-3xl text-xs leading-relaxed text-slate-600 sm:text-sm">
              Hold <strong>Claude Sonnet 5.5</strong> ($2.00/M in · $10.00/M out) constant across a 10-turn IT &amp; HR
              Service Desk escalation: measure how <strong>Prefix Context Caching</strong> ($0.20/M reads, -90%) and{' '}
              <strong>Sliding-Window Memory Summarization</strong> eliminate quadratic <strong>O(N²)</strong> session cost bloat.
            </p>
          </div>

          <div className="flex shrink-0 flex-col items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50/70 px-4 py-3 text-xs">
            <div className="font-mono text-[10px] font-extrabold uppercase tracking-wider text-emerald-800">
              Single Controlled Variable
            </div>
            <div className="font-bold text-slate-900">Use Case: IT &amp; HR Service Desk</div>
            <div className="font-mono text-[11px] text-slate-600">
              Same Model · 3 Context Architectures
            </div>
          </div>
        </div>

        {/* Accessible Tablist following tabs guide */}
        <div
          role="tablist"
          aria-label="Category 3 workbench views"
          onKeyDown={handleViewTabKeyDown}
          className="mwg-tablist border-t border-slate-200 bg-slate-50 px-6"
        >
          <button
            type="button"
            role="tab"
            id="cat3-tab-arena"
            aria-selected={activeView === 'arena'}
            tabIndex={activeView === 'arena' ? 0 : -1}
            onClick={() => setActiveView('arena')}
            className={`mwg-tab inline-flex items-center gap-2 px-4 py-3 text-xs font-bold transition ${
              activeView === 'arena' ? 'text-emerald-700' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Sparkles className="h-3.5 w-3.5" />
            3-Pattern Session Cost Arena (Turn 1 → Turn 10)
          </button>

          <button
            type="button"
            role="tab"
            id="cat3-tab-simulator"
            aria-selected={activeView === 'simulator'}
            tabIndex={activeView === 'simulator' ? 0 : -1}
            onClick={() => setActiveView('simulator')}
            className={`mwg-tab inline-flex items-center gap-2 px-4 py-3 text-xs font-bold transition ${
              activeView === 'simulator' ? 'text-emerald-700' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Layers className="h-3.5 w-3.5" />
            Interactive Service Desk Simulator &amp; Context Window X-Ray
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

      {/* TAB PANEL 1: 3-PATTERN SESSION COST ARENA (zero padding/border directly on tabpanel) */}
      <div role="tabpanel" aria-labelledby="cat3-tab-arena" hidden={activeView !== 'arena'}>
        <div className="space-y-6">
          {/* Scenario Picker & Session Controls */}
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-sm font-extrabold text-slate-900">
                  Select 10-Turn NovaMart IT &amp; HR Service Desk Escalation Scenario
                </h2>
                <p className="mt-0.5 text-xs text-slate-500">
                  Every scenario pins the full{' '}
                  <strong className="text-slate-700">
                    {(runResponse?.approx_handbook_tokens ?? selectedPreset.approx_handbook_tokens).toLocaleString()}
                    -token
                  </strong>{' '}
                  Unified IT/HR SOP Handbook + Employee Profile before Turn 1 and steps through 10 realistic log-heavy turns.
                </p>
              </div>

              <button
                type="button"
                disabled={loadingArena}
                onClick={() => void executeArena(selectedPresetId)}
                className="inline-flex items-center gap-2 rounded-xl bg-emerald-700 px-4 py-2 text-xs font-extrabold text-white shadow-sm transition hover:bg-emerald-800 disabled:opacity-50"
              >
                {creds.mode === 'live' ? (
                  <Zap className="h-4 w-4 text-amber-300" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
                <span>
                  {loadingArena
                    ? 'Running 10-Turn Arena...'
                    : creds.mode === 'live'
                      ? 'Run Live 3-Pattern Session'
                      : 'Replay Verified 10-Turn Arena'}
                </span>
              </button>
            </div>

            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {presetsData.presets.map((p) => {
                const active = p.id === selectedPresetId
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => handleSelectPreset(p.id)}
                    className={`rounded-xl border p-4 text-left transition ${
                      active
                        ? 'border-emerald-700 bg-emerald-50/70 ring-1 ring-emerald-700'
                        : 'border-slate-200 bg-slate-50/50 hover:border-slate-300 hover:bg-white'
                    }`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-mono text-[10px] font-bold uppercase text-emerald-800">
                        {p.id} · {p.employee_profile.employee_id} · {p.employee_profile.device_tag}
                      </span>
                      <span className="rounded bg-slate-200/80 px-2 py-0.5 font-mono text-[10px] font-bold text-slate-700">
                        ~{p.approx_handbook_tokens.toLocaleString()} tok prefix
                      </span>
                    </div>
                    <div className="mt-1.5 text-xs font-extrabold leading-snug text-slate-900">
                      {p.title}
                    </div>
                    <div className="mt-1 text-[11px] text-slate-600">{p.subtitle}</div>
                    <div className="mt-2 font-mono text-[10px] text-slate-500">
                      Employee: {p.employee_profile.name} ({p.employee_profile.role})
                    </div>
                  </button>
                )
              })}
            </div>

            {/* Session Depth Scrubber & Cold vs Warm Fleet Toggle */}
            <div className="mt-4 grid gap-4 rounded-xl border border-slate-200 bg-slate-50 p-4 lg:grid-cols-2">
              <div>
                <div className="flex items-center justify-between gap-2">
                  <label htmlFor="cat3-turn-scrubber" className="text-xs font-bold text-slate-800">
                    Session Length Scrubber:{' '}
                    <span className="font-mono text-emerald-700">
                      Turns 1 – {selectedMaxTurn}
                    </span>
                  </label>
                  <span className="font-mono text-[10px] text-slate-500">
                    Compaction triggers at Turn 5 &amp; Turn 8
                  </span>
                </div>
                <input
                  id="cat3-turn-scrubber"
                  type="range"
                  min={1}
                  max={10}
                  step={1}
                  value={selectedMaxTurn}
                  onChange={(e) => setSelectedMaxTurn(Number(e.target.value))}
                  className="mt-2.5 w-full accent-emerald-700"
                />
                <div className="mt-1 flex justify-between font-mono text-[10px] text-slate-500">
                  {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setSelectedMaxTurn(t)}
                      className={`px-1 ${
                        t === selectedMaxTurn
                          ? 'font-extrabold text-emerald-700 underline'
                          : t === 5 || t === 8
                            ? 'font-bold text-amber-700'
                            : ''
                      }`}
                    >
                      T{t}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex flex-col justify-between gap-2">
                <div className="text-xs font-bold text-slate-800">
                  Prefix Cache Entry Pricing Perspective
                </div>
                <div className="inline-flex rounded-xl border border-slate-300 bg-white p-1 text-xs">
                  <button
                    type="button"
                    onClick={() => setCacheMode('cold_first_turn')}
                    className={`flex-1 rounded-lg px-3 py-1.5 font-bold transition ${
                      cacheMode === 'cold_first_turn'
                        ? 'bg-emerald-700 text-white shadow-xs'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    Cold Turn-1 Write ($2.50/M)
                  </button>
                  <button
                    type="button"
                    onClick={() => setCacheMode('warm_fleet_prefix')}
                    className={`flex-1 rounded-lg px-3 py-1.5 font-bold transition ${
                      cacheMode === 'warm_fleet_prefix'
                        ? 'bg-emerald-700 text-white shadow-xs'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    Warm Shared Prefix Fleet ($0.20/M)
                  </button>
                </div>
                <p className="text-[11px] text-slate-500">
                  {cacheMode === 'cold_first_turn'
                    ? 'Single-session view: Turn 1 pays 1.25x ($2.50/M) ephemeral write before Turns 2–10 read at -90% ($0.20/M).'
                    : 'Production fleet view: handbook prefix stays warm across 18,000 employees, so Turn 1 also reads at $0.20/M.'}
                </p>
              </div>
            </div>
          </section>

          {runResponse && slicedByRung.length > 0 && (
            <>
              {/* Callout Banner */}
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs font-semibold text-emerald-950">
                {runResponse.session_callout}
              </div>

              {/* 3 Rung Comparison Cards */}
              <div className="grid gap-4 lg:grid-cols-3">
                {slicedByRung.map((s) => {
                  const fullRung = runResponse.results.find((r) => r.rung_id === s.rungId)!
                  const isNaive = s.rungId === 'naive_full_history'
                  const isCachedOnly = s.rungId === 'prefix_cached_history'
                  const isCompact = s.rungId === 'prefix_cached_summarized'

                  const borderTheme = isNaive
                    ? 'border-rose-300'
                    : isCachedOnly
                      ? 'border-amber-300'
                      : 'border-emerald-400 ring-1 ring-emerald-200'
                  const headerBg = isNaive
                    ? 'bg-rose-50'
                    : isCachedOnly
                      ? 'bg-amber-50/70'
                      : 'bg-emerald-50/90'
                  const badgeBg = isNaive
                    ? 'bg-rose-600 text-white'
                    : isCachedOnly
                      ? 'bg-amber-600 text-white'
                      : 'bg-emerald-700 text-white'

                  const naiveCost = naiveSlice?.sessionCostUsd ?? 0
                  const cachedCost = cachedSlice?.sessionCostUsd ?? 0
                  const vsNaivePct =
                    naiveCost > 0 ? ((naiveCost - s.sessionCostUsd) / naiveCost) * 100 : 0
                  const vsCachedPct =
                    cachedCost > 0 ? ((cachedCost - s.sessionCostUsd) / cachedCost) * 100 : 0

                  return (
                    <div
                      key={s.rungId}
                      className={`flex flex-col justify-between rounded-2xl border bg-white shadow-sm ${borderTheme}`}
                    >
                      <div>
                        <div className={`rounded-t-2xl border-b border-slate-200/80 px-4 py-3 ${headerBg}`}>
                          <div className="flex items-center justify-between gap-2">
                            <span className={`rounded-md px-2 py-0.5 text-[10px] font-extrabold uppercase ${badgeBg}`}>
                              {s.badgeText}
                            </span>
                            <span className="font-mono text-[11px] font-bold text-slate-700">
                              {selectedMaxTurn} Turn{selectedMaxTurn > 1 ? 's' : ''}
                            </span>
                          </div>
                          <h3 className="mt-2 text-sm font-extrabold text-slate-900">{s.rungTitle}</h3>
                          <div className="mt-0.5 font-mono text-[11px] text-slate-600">
                            Anthropic · <strong>{s.modelId}</strong>
                          </div>
                        </div>

                        <div className="space-y-3.5 p-4">
                          <div className="grid grid-cols-2 gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3">
                            <div>
                              <div className="text-[10px] font-bold uppercase text-slate-500">
                                Cost / 1k Sessions
                              </div>
                              <div className="mt-0.5 font-mono text-xl font-extrabold tabular-nums text-slate-900">
                                ${s.costPer1kSessionsUsd.toFixed(2)}
                              </div>
                              <div
                                className={`text-[11px] font-bold ${
                                  isNaive ? 'text-rose-700' : 'text-emerald-700'
                                }`}
                              >
                                {isNaive
                                  ? 'Baseline O(N²)'
                                  : `-${vsNaivePct.toFixed(1)}% vs Rung 1`}
                              </div>
                            </div>
                            <div>
                              <div className="text-[10px] font-bold uppercase text-slate-500">
                                Single Session ({selectedMaxTurn}T)
                              </div>
                              <div className="mt-0.5 font-mono text-xl font-extrabold tabular-nums text-slate-900">
                                ${s.sessionCostUsd.toFixed(4)}
                              </div>
                              <div className="font-mono text-[10px] text-slate-600">
                                {isCompact && s.summarizerCalls > 0
                                  ? `Incl. ${s.summarizerCalls} sum calls (-${vsCachedPct.toFixed(1)}% vs R2)`
                                  : isCachedOnly
                                    ? 'Handbook cached only'
                                    : 'No cache · full history'}
                              </div>
                            </div>
                          </div>

                          {/* Tokenomics Strip */}
                          <div className="grid grid-cols-4 gap-1.5 text-center font-mono text-[10px]">
                            <div className="rounded-lg bg-slate-100 px-1.5 py-1.5">
                              <div className="font-bold text-slate-500">UNCACHED IN</div>
                              <div className="mt-0.5 text-xs font-extrabold text-slate-900">
                                {s.uncachedInTokens.toLocaleString()}
                              </div>
                            </div>
                            <div className="rounded-lg bg-slate-100 px-1.5 py-1.5">
                              <div className="font-bold text-slate-500">CACHE WRITE</div>
                              <div className="mt-0.5 text-xs font-extrabold text-amber-700">
                                {s.cacheWriteTokens.toLocaleString()}
                              </div>
                            </div>
                            <div className="rounded-lg bg-emerald-50 px-1.5 py-1.5">
                              <div className="font-bold text-emerald-700">CACHE READ</div>
                              <div className="mt-0.5 text-xs font-extrabold text-emerald-900">
                                {s.cacheReadTokens.toLocaleString()}
                              </div>
                            </div>
                            <div className="rounded-lg bg-slate-100 px-1.5 py-1.5">
                              <div className="font-bold text-slate-500">OUT TOK</div>
                              <div className="mt-0.5 text-xs font-extrabold text-slate-900">
                                {s.outputTokens.toLocaleString()}
                              </div>
                            </div>
                          </div>

                          {/* Transparent Summarizer Cost Accountability Box on Rung 3 */}
                          {isCompact && (
                            <div className="rounded-xl border border-emerald-200 bg-emerald-50/70 px-3 py-2 text-[11px] text-emerald-950">
                              <strong>Honest Compactor Accounting:</strong>{' '}
                              {s.summarizerCalls > 0
                                ? `${s.summarizerCalls} Sonnet 5.5 JSON summarizer calls (${s.summarizerInTokens.toLocaleString()} in / ${s.summarizerOutTokens.toLocaleString()} out = $${(s.summarizerCostUsd * 1000).toFixed(2)}/1k sessions) included inside the $${s.costPer1kSessionsUsd.toFixed(2)}/1k total.`
                                : 'Compaction fires starting at Turn 5 (window >= 4 turns). Scrub past T4 to inspect.'}
                            </div>
                          )}

                          <button
                            type="button"
                            onClick={() => {
                              setSimRungId(s.rungId)
                              setSimTurnCount(selectedMaxTurn)
                              setActiveView('simulator')
                            }}
                            className={`inline-flex w-full items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-extrabold text-white transition ${
                              isNaive
                                ? 'bg-rose-600 hover:bg-rose-700'
                                : isCachedOnly
                                  ? 'bg-amber-600 hover:bg-amber-700'
                                  : 'bg-emerald-700 hover:bg-emerald-800'
                            }`}
                          >
                            <Layers className="h-3.5 w-3.5" />
                            Inspect Turns &amp; X-Ray in Simulator →
                          </button>
                        </div>
                      </div>

                      <div className="border-t border-slate-100 px-4 py-3 text-[11px] text-slate-600">
                        <ul className="space-y-1">
                          {fullRung.architectural_notes.map((n, idx) => (
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

              {/* FinOps HUD & Charts */}
              <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
                <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-200 pb-4">
                  <div>
                    <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-emerald-700">
                      <DollarSign className="h-4 w-4" />
                      Category 3 FinOps HUD · Prefix Caching &amp; Memory Compaction Economics
                    </div>
                    <h2 className="mt-0.5 text-lg font-extrabold text-slate-900">
                      Eliminating Quadratic O(N²) Session Cost Across 10 Service Desk Turns
                    </h2>
                  </div>

                  <div className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-0.5 text-xs">
                    <button
                      type="button"
                      onClick={() => setLineMetricMode('per_turn_cents')}
                      className={`rounded-md px-2.5 py-1 font-semibold transition ${
                        lineMetricMode === 'per_turn_cents'
                          ? 'bg-white text-slate-900 shadow-xs'
                          : 'text-slate-600'
                      }`}
                    >
                      Per-Turn Sawtooth (¢)
                    </button>
                    <button
                      type="button"
                      onClick={() => setLineMetricMode('cumulative_1k')}
                      className={`rounded-md px-2.5 py-1 font-semibold transition ${
                        lineMetricMode === 'cumulative_1k'
                          ? 'bg-white text-slate-900 shadow-xs'
                          : 'text-slate-600'
                      }`}
                    >
                      Cumulative O(N²) ($/1k)
                    </button>
                  </div>
                </div>

                {/* Volume Slider */}
                <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <label htmlFor="cat3-volume-slider" className="text-xs font-bold text-slate-700">
                      Projected Monthly 10-Turn Service Desk Sessions:{' '}
                      <span className="font-mono text-emerald-700">{VOLUME_STEPS[volumeIdx].label}</span>
                    </label>
                    {annualSavingsUsd > 0 && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-3 py-1 font-mono text-xs font-bold text-emerald-900">
                        <TrendingDown className="h-3.5 w-3.5" />
                        Annualized Savings (Rung 3 vs Rung 1): $
                        {annualSavingsUsd.toLocaleString(undefined, { maximumFractionDigits: 0 })}/yr
                      </span>
                    )}
                  </div>
                  <input
                    id="cat3-volume-slider"
                    type="range"
                    min={0}
                    max={VOLUME_STEPS.length - 1}
                    step={1}
                    value={volumeIdx}
                    onChange={(e) => setVolumeIdx(Number(e.target.value))}
                    className="mt-3 w-full accent-emerald-700"
                  />
                  <div className="mt-1 flex justify-between font-mono text-[10px] text-slate-500">
                    {VOLUME_STEPS.map((s, idx) => (
                      <span key={s.value} className={idx === volumeIdx ? 'font-bold text-emerald-700' : ''}>
                        {s.label.split(' ')[0]}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Charts Grid */}
                <div className="mt-5 grid gap-6 lg:grid-cols-2">
                  <div className="rounded-xl border border-slate-200 p-4">
                    <h3 className="mb-2 text-xs font-extrabold uppercase tracking-wider text-slate-700">
                      {lineMetricMode === 'per_turn_cents'
                        ? 'Per-Turn Total Spend (¢ · Note Rung 3 Compaction Sawtooth After T5 & T8)'
                        : 'Cumulative Session Spend ($ per 1,000 Sessions)'}
                    </h3>
                    <div className="h-64 w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={lineChartData} margin={{ top: 10, right: 20, left: 0, bottom: 8 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                          <XAxis dataKey="turnLabel" tick={{ fontSize: 11, fill: '#0f172a', fontWeight: 600 }} />
                          <YAxis
                            tickFormatter={(v: number) =>
                              lineMetricMode === 'per_turn_cents' ? `${v}¢` : `$${v}`
                            }
                            tick={{ fontSize: 11, fill: '#475569' }}
                          />
                          <Tooltip
                            formatter={(val: number) =>
                              lineMetricMode === 'per_turn_cents'
                                ? `${val.toFixed(3)}¢ / turn`
                                : `$${val.toFixed(2)} / 1k`
                            }
                          />
                          <Legend wrapperStyle={{ fontSize: 11 }} />
                          <Line
                            type="monotone"
                            dataKey="naiveValue"
                            name="1. Uncached Full"
                            stroke="#dc2626"
                            strokeWidth={2.5}
                            dot={{ r: 3 }}
                          />
                          <Line
                            type="monotone"
                            dataKey="cachedValue"
                            name="2. Prefix Cache Only"
                            stroke="#d97706"
                            strokeWidth={2.5}
                            dot={{ r: 3 }}
                          />
                          <Line
                            type="monotone"
                            dataKey="compactValue"
                            name="3. Cache + Summary"
                            stroke="#15803d"
                            strokeWidth={3}
                            dot={{ r: 4 }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  <div className="rounded-xl border border-slate-200 p-4">
                    <h3 className="mb-2 text-xs font-extrabold uppercase tracking-wider text-slate-700">
                      Cost Breakdown per 1,000 Sessions ({selectedMaxTurn} Turns · Includes Summarizer)
                    </h3>
                    <div className="h-64 w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={stackedCostData} margin={{ top: 10, right: 20, left: 0, bottom: 8 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                          <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#0f172a', fontWeight: 600 }} />
                          <YAxis tickFormatter={(v: number) => `$${v}`} tick={{ fontSize: 11, fill: '#475569' }} />
                          <Tooltip formatter={(val: number) => `$${val.toFixed(2)} / 1k`} />
                          <Legend wrapperStyle={{ fontSize: 11 }} />
                          <Bar dataKey="uncachedIn1k" name="Uncached In ($2/M)" stackId="s" fill="#dc2626" />
                          <Bar dataKey="cache1k" name="Cache W/R ($2.5/$0.2)" stackId="s" fill="#15803d" />
                          <Bar dataKey="output1k" name="Output ($10/M)" stackId="s" fill="#475569" />
                          <Bar
                            dataKey="summarizer1k"
                            name="Memory Summarizer"
                            stackId="s"
                            fill="#f59e0b"
                            radius={[6, 6, 0, 0]}
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </div>

                {/* Monthly & Annual Projected Spend Cards */}
                <div className="mt-5 grid gap-3 sm:grid-cols-3">
                  {slicedByRung.map((s) => {
                    const color =
                      s.rungId === 'naive_full_history'
                        ? '#dc2626'
                        : s.rungId === 'prefix_cached_history'
                          ? '#d97706'
                          : '#15803d'
                    const mSpend = s.sessionCostUsd * monthlyVol
                    const aSpend = mSpend * 12
                    return (
                      <div
                        key={s.rungId}
                        className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5"
                        style={{ borderTopWidth: '3px', borderTopColor: color }}
                      >
                        <div className="text-[11px] font-bold text-slate-700">{s.rungTitle}</div>
                        <div className="mt-1 font-mono text-lg font-extrabold tabular-nums text-slate-900">
                          ${mSpend.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          <span className="text-xs font-normal text-slate-500"> /mo</span>
                        </div>
                        <div className="font-mono text-[11px] text-slate-500">
                          ${aSpend.toLocaleString(undefined, { maximumFractionDigits: 0 })} /yr
                        </div>
                      </div>
                    )
                  })}
                </div>
              </section>

              {/* Turn-by-Turn Tokenomics & Cache Ledger Table (responsive-table guide) */}
              {inspectedTableRung && (
                <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h2 id="cat3-turns-heading" className="text-sm font-extrabold text-slate-900">
                        Turn-by-Turn Tokenomics &amp; Prefix Cache Ledger ({inspectedTableRung.rungTitle})
                      </h2>
                      <p className="text-xs text-slate-500">
                        Switch patterns to audit how `cache_read_input_tokens` and `Compaction` affect every single API call.
                      </p>
                    </div>

                    <div className="inline-flex flex-wrap gap-1.5">
                      {(
                        [
                          ['prefix_cached_summarized', '3. Cache + Summary'],
                          ['prefix_cached_history', '2. Prefix Cache Only'],
                          ['naive_full_history', '1. Uncached Full'],
                        ] as const
                      ).map(([rid, lbl]) => (
                        <button
                          key={rid}
                          type="button"
                          onClick={() => setTableRungId(rid)}
                          className={`rounded-lg border px-2.5 py-1 text-xs font-bold transition ${
                            tableRungId === rid
                              ? 'border-emerald-700 bg-emerald-50 text-emerald-900'
                              : 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50'
                          }`}
                        >
                          {lbl}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div
                    tabIndex={0}
                    role="region"
                    aria-labelledby="cat3-turns-heading"
                    className="table-wrapper rounded-xl border border-slate-200"
                  >
                    <table
                      className="mwg-table text-left text-xs"
                      data-table="cat3-turns"
                      style={
                        {
                          '--label-2': '"Window"',
                          '--label-3': '"Uncached In"',
                          '--label-4': '"Cache W / R"',
                          '--label-5': '"Out / Sum"',
                          '--label-6': '"Turn Cost"',
                          '--label-7': '"Cum. Cost"',
                        } as React.CSSProperties
                      }
                    >
                      <caption className="sr-only">
                        Per-turn Anthropic Sonnet 5.5 token counts, cache writes/reads, summarizer overhead, and cumulative session cost.
                      </caption>
                      <thead className="bg-slate-900 text-[11px] font-bold uppercase tracking-wider text-slate-200">
                        <tr>
                          <th scope="col" className="px-3.5 py-2.5">Turn / Topic</th>
                          <th scope="col" className="px-3.5 py-2.5">Memory Window</th>
                          <th scope="col" className="px-3.5 py-2.5 text-right">Uncached In</th>
                          <th scope="col" className="px-3.5 py-2.5 text-right">Cache Write / Read</th>
                          <th scope="col" className="px-3.5 py-2.5 text-right">Out + Sum</th>
                          <th scope="col" className="px-3.5 py-2.5 text-right">Turn Cost</th>
                          <th scope="col" className="px-3.5 py-2.5 text-right">Cumulative</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-200 bg-white">
                        {inspectedTableRung.turnsSlice.map((t) => {
                          const cw =
                            cacheMode === 'warm_fleet_prefix' ? 0 : t.finops.cache_creation_tokens
                          const cr =
                            cacheMode === 'warm_fleet_prefix'
                              ? t.finops.cache_creation_tokens + t.finops.cache_read_tokens
                              : t.finops.cache_read_tokens
                          const turnCost =
                            ((t.finops.input_tokens * SONNET_RATE.inPer1M +
                              cw * SONNET_RATE.writePer1M +
                              cr * SONNET_RATE.readPer1M +
                              t.finops.output_tokens * SONNET_RATE.outPer1M) /
                              1_000_000) +
                            (t.compaction_finops?.total_cost_usd ?? 0)
                          const cumCost =
                            cacheMode === 'warm_fleet_prefix'
                              ? t.cumulative_warm_cost_usd
                              : t.cumulative_cost_usd
                          return (
                            <tr
                              key={t.turn_number}
                              className={t.compaction_triggered_before_turn ? 'bg-amber-50/50' : 'hover:bg-slate-50'}
                            >
                              <th scope="row" className="px-3.5 py-2.5 text-left font-bold text-slate-900">
                                <span className="font-mono text-emerald-800">T{t.turn_number}</span> · {t.topic_tag}
                              </th>
                              <td className="px-3.5 py-2.5 text-[11px] text-slate-700">
                                {t.compaction_triggered_before_turn && (
                                  <span className="mr-1.5 rounded bg-amber-100 px-1.5 py-0.5 font-mono text-[10px] font-bold text-amber-900">
                                    COMPACTED ≤T{t.compacted_turns_count}
                                  </span>
                                )}
                                <span>{t.active_history_turns} prior verbatim</span>
                              </td>
                              <td className="px-3.5 py-2.5 text-right font-mono tabular-nums text-slate-900">
                                {t.finops.input_tokens.toLocaleString()}
                              </td>
                              <td className="px-3.5 py-2.5 text-right font-mono tabular-nums">
                                {cw > 0 ? (
                                  <span className="font-bold text-amber-700">{cw.toLocaleString()} W</span>
                                ) : (
                                  <span className="text-slate-400">0 W</span>
                                )}{' '}
                                /{' '}
                                {cr > 0 ? (
                                  <span className="font-bold text-emerald-700">{cr.toLocaleString()} R</span>
                                ) : (
                                  <span className="text-slate-400">0 R</span>
                                )}
                              </td>
                              <td className="px-3.5 py-2.5 text-right font-mono tabular-nums text-slate-700">
                                {t.finops.output_tokens.toLocaleString()}
                                {t.compaction_finops && (
                                  <span className="ml-1 text-[10px] font-bold text-amber-700">
                                    (+{t.compaction_finops.output_tokens}s)
                                  </span>
                                )}
                              </td>
                              <td className="px-3.5 py-2.5 text-right font-mono font-bold tabular-nums text-slate-900">
                                ${(turnCost * 100).toFixed(2)}¢
                              </td>
                              <td className="px-3.5 py-2.5 text-right font-mono font-bold tabular-nums text-emerald-900">
                                ${cumCost.toFixed(4)}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </>
          )}
        </div>
      </div>

      {/* TAB PANEL 2: INTERACTIVE SERVICE DESK SIMULATOR & CONTEXT WINDOW X-RAY */}
      <div role="tabpanel" aria-labelledby="cat3-tab-simulator" hidden={activeView !== 'simulator'}>
        <div className="space-y-5">
          {/* Simulator Controls Bar */}
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="text-base font-extrabold text-slate-900">
                  Interactive Service Desk Simulator &amp; Context Window X-Ray
                </h2>
                <p className="mt-0.5 text-xs text-slate-600">
                  Step turn-by-turn across {selectedPreset.id} ({selectedPreset.employee_profile.name}) to watch the{' '}
                  <strong>Context Window X-Ray</strong> update live at Turn 5 &amp; Turn 8 compaction boundaries.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {(
                  [
                    ['prefix_cached_summarized', 'Rung 3: Cache + Summary'],
                    ['prefix_cached_history', 'Rung 2: Cache Only'],
                    ['naive_full_history', 'Rung 1: Uncached Full'],
                  ] as const
                ).map(([rid, lbl]) => (
                  <button
                    key={rid}
                    type="button"
                    onClick={() => {
                      setSimRungId(rid)
                      setLiveExtraTurns([])
                      setLiveVerbatimWindow(null)
                      setLiveMemorySummary(null)
                    }}
                    className={`rounded-lg border px-3 py-1.5 text-xs font-bold transition ${
                      simRungId === rid
                        ? 'border-emerald-700 bg-emerald-50 text-emerald-950 ring-1 ring-emerald-700'
                        : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
                    }`}
                  >
                    {lbl}
                  </button>
                ))}
              </div>
            </div>

            {/* Turn Stepper */}
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="mr-1 text-xs font-bold text-slate-700">Inspect Turn:</span>
                {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setSimTurnCount(t)}
                    className={`rounded-md px-2.5 py-1 font-mono text-xs font-bold transition ${
                      simTurnCount === t
                        ? 'bg-emerald-700 text-white'
                        : t <= simTurnCount
                          ? 'bg-emerald-100 text-emerald-900 hover:bg-emerald-200'
                          : 'bg-white text-slate-500 ring-1 ring-slate-200 hover:bg-slate-100'
                    }`}
                  >
                    T{t}
                  </button>
                ))}
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={simTurnCount >= 10}
                  onClick={() => setSimTurnCount((c) => Math.min(10, c + 1))}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-bold text-white hover:bg-slate-800 disabled:opacity-40"
                >
                  <SkipForward className="h-3.5 w-3.5" />
                  Step Next Turn
                </button>
                <button
                  type="button"
                  onClick={() => setSimTurnCount(10)}
                  className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 hover:bg-slate-50"
                >
                  Jump to Turn 10
                </button>
              </div>
            </div>
          </section>

          {activeFocusTurn && (
            <div className="grid gap-5 lg:grid-cols-[380px_minmax(0,1fr)]">
              {/* Left Sticky Column: Context Window X-Ray */}
              <aside className="lg:sticky lg:top-20 lg:self-start">
                <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex items-center justify-between gap-2 border-b border-slate-200 pb-2.5">
                    <div className="flex items-center gap-1.5 text-xs font-extrabold text-slate-900">
                      <Cpu className="h-4 w-4 text-emerald-700" />
                      <span>Context Window X-Ray (Turn {activeFocusTurn.turn_number})</span>
                    </div>
                    <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-[10px] font-bold text-slate-700">
                      {(
                        activeFocusTurn.finops.input_tokens +
                        activeFocusTurn.finops.cache_creation_tokens +
                        activeFocusTurn.finops.cache_read_tokens
                      ).toLocaleString()}{' '}
                      prompt tok
                    </span>
                  </div>

                  {/* Proportional Stacked Context Bar */}
                  <div className="mt-3 space-y-1.5">
                    <div className="text-[11px] font-bold text-slate-700">
                      Prompt Token Anatomy at Turn {activeFocusTurn.turn_number}
                    </div>
                    <div className="flex h-4 w-full overflow-hidden rounded-full bg-slate-100 ring-1 ring-slate-200">
                      {xRayStats.handbookCached > 0 && (
                        <div
                          title={`Cached Prefix: ${xRayStats.handbookCached.toLocaleString()} tok`}
                          className="bg-emerald-600"
                          style={{
                            width: `${Math.max(
                              12,
                              Math.round(
                                (xRayStats.handbookCached /
                                  Math.max(
                                    1,
                                    xRayStats.handbookCached +
                                      xRayStats.handbookUncached +
                                      xRayStats.memorySummaryTok +
                                      xRayStats.verbatimTailTok
                                  )) *
                                  100
                              )
                            )}%`,
                          }}
                        />
                      )}
                      {xRayStats.handbookUncached > 0 && (
                        <div
                          title={`Uncached Handbook: ${xRayStats.handbookUncached.toLocaleString()} tok`}
                          className="bg-rose-500"
                          style={{
                            width: `${Math.max(
                              15,
                              Math.round(
                                (xRayStats.handbookUncached /
                                  Math.max(
                                    1,
                                    xRayStats.handbookUncached + xRayStats.verbatimTailTok
                                  )) *
                                  100
                              )
                            )}%`,
                          }}
                        />
                      )}
                      {xRayStats.memorySummaryTok > 0 && (
                        <div
                          title={`Memory Summary JSON: ~${xRayStats.memorySummaryTok.toLocaleString()} tok`}
                          className="bg-amber-500"
                          style={{ width: '8%' }}
                        />
                      )}
                      <div
                        title={`Uncached Active Window: ${xRayStats.verbatimTailTok.toLocaleString()} tok`}
                        className="flex-1 bg-slate-700"
                      />
                    </div>
                    <div className="flex flex-wrap gap-2 text-[10px] font-semibold text-slate-600">
                      {xRayStats.handbookCached > 0 ? (
                        <span className="inline-flex items-center gap-1">
                          <span className="h-2 w-2 rounded-full bg-emerald-600" />
                          Cached Prefix ({xRayStats.handbookCached.toLocaleString()})
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1">
                          <span className="h-2 w-2 rounded-full bg-rose-500" />
                          Uncached Handbook ({xRayStats.handbookUncached.toLocaleString()})
                        </span>
                      )}
                      {xRayStats.memorySummaryTok > 0 && (
                        <span className="inline-flex items-center gap-1">
                          <span className="h-2 w-2 rounded-full bg-amber-500" />
                          Memory JSON (~{xRayStats.memorySummaryTok})
                        </span>
                      )}
                      <span className="inline-flex items-center gap-1">
                        <span className="h-2 w-2 rounded-full bg-slate-700" />
                        Active Tail ({xRayStats.verbatimTailTok.toLocaleString()})
                      </span>
                    </div>
                  </div>

                  {/* Evicted Savings Callout */}
                  {xRayStats.evictedSavedTok > 0 && (
                    <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-[11px] font-semibold text-emerald-950">
                      <strong>Compaction Yield at Turn {activeFocusTurn.turn_number}:</strong>{' '}
                      {xRayStats.evictedSavedTok.toLocaleString()} raw history tokens evicted from this single turn&apos;s prompt (Turns 1–{activeFocusTurn.compacted_turns_count} compressed).
                    </div>
                  )}

                  {/* Native <details> Accordion following modern-web-guidance accordion guide */}
                  <section
                    className="mwg-accordion mt-4 space-y-2.5"
                    aria-labelledby="cat3-xray-layers-heading"
                  >
                    <h3
                      id="cat3-xray-layers-heading"
                      className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500"
                    >
                      3-Layer Context Memory Inspector
                    </h3>

                    <details
                      open
                      className="rounded-xl border border-slate-200 bg-slate-50/70 p-3 text-xs"
                    >
                      <summary className="font-bold text-slate-900">
                        <span>
                          Layer 1 · IT &amp; HR Prefix (
                          {simRungId === 'naive_full_history' ? 'Uncached $2.00/M' : 'Cached -90% $0.20/M'})
                        </span>
                      </summary>
                      <div className="mt-2 space-y-1.5 text-[11px] text-slate-600">
                        <div>
                          Handbook Size: <strong>{presetsData.handbook_char_count.toLocaleString()} chars</strong> (~
                          {selectedPreset.approx_handbook_tokens.toLocaleString()} Sonnet 5.5 tokens) + Profile Header.
                        </div>
                        <pre className="max-h-36 overflow-y-auto whitespace-pre-wrap rounded-lg bg-slate-950 p-2 font-mono text-[10px] text-slate-200">
                          {presetsData.handbook_preview.slice(0, 700)}...
                        </pre>
                      </div>
                    </details>

                    <details
                      open
                      className="rounded-xl border border-slate-200 bg-slate-50/70 p-3 text-xs"
                    >
                      <summary className="font-bold text-slate-900">
                        <span>
                          Layer 2 · Rolling Memory JSON (
                          {activeFocusTurn.compacted_turns_count > 0
                            ? `Turns 1–${activeFocusTurn.compacted_turns_count}`
                            : 'Empty before Turn 5'}
                          )
                        </span>
                      </summary>
                      <div className="mt-2 text-[11px] text-slate-600">
                        {xRayStats.memorySnapshot ? (
                          <pre className="max-h-60 overflow-y-auto whitespace-pre-wrap rounded-lg bg-slate-950 p-2.5 font-mono text-[10px] text-emerald-300">
                            {JSON.stringify(xRayStats.memorySnapshot, null, 2)}
                          </pre>
                        ) : (
                          <p className="rounded-lg bg-white p-2.5 text-[11px] text-slate-500 ring-1 ring-slate-200">
                            {simRungId === 'prefix_cached_summarized'
                              ? 'Turns 1–4 stay raw in the active window. Compaction first triggers before Turn 5.'
                              : 'Memory summarization is disabled in this rung — all prior turns stay verbatim.'}
                          </p>
                        )}
                      </div>
                    </details>

                    <details className="rounded-xl border border-slate-200 bg-slate-50/70 p-3 text-xs">
                      <summary className="font-bold text-slate-900">
                        <span>Layer 3 · Active Verbatim Tail ({xRayStats.verbatimRangeLabel})</span>
                      </summary>
                      <div className="mt-2 space-y-1.5 text-[11px] text-slate-600">
                        <div>
                          Uncached active prompt tokens:{' '}
                          <strong className="font-mono text-slate-900">
                            {activeFocusTurn.finops.input_tokens.toLocaleString()} tok
                          </strong>{' '}
                          @ $2.00/M.
                        </div>
                        <div className="space-y-1.5 text-[11px] leading-relaxed text-slate-500">
                          <p>
                            For chat conversations, keeping recent turns raw preserves natural conversational flow, pronouns and anaphora (such as &ldquo;that option&rdquo; or &ldquo;the second policy&rdquo;), user tone, and immediate follow-up nuance without stiff summary artifacts.
                          </p>
                          <p>
                            <strong className="text-slate-700">During coding sessions</strong> — keeping recent turns raw avoids lossy paraphrasing of exact CLI flags or error codes you are actively debugging right now.
                          </p>
                        </div>
                      </div>
                    </details>
                  </section>
                </div>
              </aside>

              {/* Right Column: Service Desk Conversation & Live Turn-11+ Composer */}
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-2xs">
                  <div>
                    <div className="font-mono text-[10px] font-bold uppercase text-emerald-800">
                      {selectedPreset.employee_profile.employee_id} · {selectedPreset.employee_profile.hub}
                    </div>
                    <div className="text-sm font-extrabold text-slate-900">
                      {selectedPreset.employee_profile.name} — {selectedPreset.employee_profile.role}
                    </div>
                  </div>
                  <div className="rounded-lg bg-slate-100 px-3 py-1.5 font-mono text-[11px] font-bold text-slate-800">
                    Cumulative Session ({simRungId}): $
                    {(cacheMode === 'warm_fleet_prefix'
                      ? activeFocusTurn.cumulative_warm_cost_usd
                      : activeFocusTurn.cumulative_cost_usd
                    ).toFixed(4)}
                  </div>
                </div>

                {/* Conversation Turns */}
                <div className="space-y-4">
                  {combinedSimTurns.map((turn) => {
                    const parsedUser = splitUserTurnTelemetry(turn.user_message)
                    const cw =
                      cacheMode === 'warm_fleet_prefix' ? 0 : turn.finops.cache_creation_tokens
                    const cr =
                      cacheMode === 'warm_fleet_prefix'
                        ? turn.finops.cache_creation_tokens + turn.finops.cache_read_tokens
                        : turn.finops.cache_read_tokens
                    return (
                      <div key={turn.turn_number} className="space-y-3">
                        {/* Inline Compaction Checkpoint Banner */}
                        {turn.compaction_triggered_before_turn && turn.compaction_finops && (
                          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-2.5 text-xs text-amber-950 shadow-2xs">
                            <div className="flex items-center gap-2">
                              <Database className="h-4 w-4 shrink-0 text-amber-700" />
                              <div>
                                <strong>Sliding-Window Compaction Triggered Before Turn {turn.turn_number}:</strong>{' '}
                                Compacted Turns 1–{turn.compacted_turns_count} via Sonnet 5.5 JSON Schema (kept T
                                {turn.turn_number - 1} raw).
                              </div>
                            </div>
                            <span className="rounded bg-white px-2 py-0.5 font-mono text-[10px] font-bold text-amber-900 ring-1 ring-amber-200">
                              {turn.compaction_finops.input_tokens.toLocaleString()} in /{' '}
                              {turn.compaction_finops.output_tokens.toLocaleString()} out · $
                              {turn.compaction_finops.total_cost_usd.toFixed(4)} ·{' '}
                              {(turn.compaction_latency_ms / 1000).toFixed(1)}s
                            </span>
                          </div>
                        )}

                        {/* Employee Turn */}
                        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-2xs">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex items-center gap-2 text-xs font-extrabold text-slate-900">
                              <User className="h-4 w-4 text-slate-600" />
                              <span>
                                Turn {turn.turn_number} · Employee ({selectedPreset.employee_profile.name})
                              </span>
                            </div>
                            <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-[10px] font-bold text-slate-700">
                              {turn.topic_tag}
                            </span>
                          </div>
                          <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-slate-700">
                            {parsedUser.promptText}
                          </p>

                          {parsedUser.telemetryBlock && (
                            <div className="mwg-accordion mt-2.5">
                              <details className="rounded-xl border border-slate-200 bg-slate-950 p-2.5 text-slate-100">
                                <summary className="font-mono text-[11px] font-bold text-emerald-300">
                                  <span>{parsedUser.telemetryHeading ?? 'Attached Pasted Telemetry'}</span>
                                </summary>
                                <pre className="mt-2 max-h-60 overflow-x-auto overflow-y-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-slate-200">
                                  {parsedUser.telemetryBlock}
                                </pre>
                              </details>
                            </div>
                          )}
                        </div>

                        {/* Service Desk Assistant Turn */}
                        <div className="rounded-2xl border border-emerald-200 bg-emerald-50/40 p-4 shadow-2xs">
                          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-emerald-100 pb-2">
                            <div className="flex items-center gap-2 text-xs font-extrabold text-emerald-950">
                              <Bot className="h-4 w-4 text-emerald-700" />
                              <span>NovaMart Service Desk AI · {turn.finops.model_id}</span>
                            </div>
                            <div className="flex flex-wrap items-center gap-1.5 font-mono text-[10px]">
                              <span className="rounded bg-white px-2 py-0.5 font-bold text-slate-700 ring-1 ring-slate-200">
                                {(turn.latency_ms / 1000).toFixed(1)}s
                              </span>
                              <span className="rounded bg-white px-2 py-0.5 font-bold text-slate-700 ring-1 ring-slate-200">
                                {turn.finops.input_tokens.toLocaleString()} in
                              </span>
                              {cw > 0 && (
                                <span className="rounded bg-amber-100 px-2 py-0.5 font-bold text-amber-900">
                                  {cw.toLocaleString()} cw
                                </span>
                              )}
                              {cr > 0 && (
                                <span className="rounded bg-emerald-100 px-2 py-0.5 font-bold text-emerald-900">
                                  {cr.toLocaleString()} cr
                                </span>
                              )}
                              <span className="rounded bg-white px-2 py-0.5 font-bold text-slate-700 ring-1 ring-slate-200">
                                {turn.finops.output_tokens.toLocaleString()} out
                              </span>
                              <span className="rounded bg-slate-900 px-2 py-0.5 font-bold text-white">
                                ${(turn.finops.total_cost_usd * 100).toFixed(2)}¢
                              </span>
                            </div>
                          </div>

                          <div className="mt-2.5 whitespace-pre-wrap text-xs leading-relaxed text-slate-800">
                            {turn.assistant_message}
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>

                {/* Live Turn-11+ Composer following accessibility guide (hint placed above input) */}
                <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="space-y-2">
                    <label
                      htmlFor="cat3-followup-input"
                      className="block text-xs font-extrabold text-slate-900"
                    >
                      Live Turn-11+ Service Desk Follow-Up ({simRungId})
                    </label>
                    <p id="cat3-followup-hint" className="text-[11px] text-slate-600">
                      {creds.mode === 'live'
                        ? 'Live API Mode active: sends a real follow-up turn to Sonnet 5.5 on top of the active context window (triggering compaction on Rung 3 after every 4 uncompacted turns).'
                        : 'Verified Replay Mode ($0) covers pre-captured Turns 1–10. Switch Credit Shield in the top bar to Live API Mode to send custom Turn-11+ follow-ups.'}
                    </p>

                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {selectedPreset.suggested_followups.map((q, idx) => (
                        <button
                          key={idx}
                          type="button"
                          onClick={() => setFollowUpText(q)}
                          className="rounded-lg border border-emerald-200 bg-emerald-50/70 px-2.5 py-1 text-left text-[11px] font-semibold text-emerald-900 transition hover:bg-emerald-100"
                        >
                          Try Follow-Up #{idx + 1}
                        </button>
                      ))}
                    </div>

                    <textarea
                      id="cat3-followup-input"
                      aria-describedby="cat3-followup-hint"
                      rows={2}
                      value={followUpText}
                      onChange={(e) => setFollowUpText(e.target.value)}
                      placeholder="Ask a Turn-11+ IT/HR follow-up (e.g., clawback calculation, Form 16 TDS timing, or split-tunnel DNS flags)..."
                      className="mwg-auto-textarea rounded-xl border border-slate-300 bg-slate-50 px-3 py-2.5 text-xs text-slate-900 focus:border-emerald-600 focus:bg-white focus:outline-none"
                    />

                    <div className="flex items-center justify-end">
                      <button
                        type="button"
                        disabled={sendingFollowUp || !followUpText.trim()}
                        onClick={() => void handleSendFollowUp()}
                        className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-700 px-4 py-2 text-xs font-extrabold text-white shadow-xs transition hover:bg-emerald-800 disabled:opacity-40"
                      >
                        <Send className="h-3.5 w-3.5" />
                        <span>{sendingFollowUp ? 'Sending Turn...' : 'Send Follow-Up Turn'}</span>
                      </button>
                    </div>
                  </div>
                </section>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Architecture & SDK Inspector Modal */}
      <NativeModal
        open={inspectorOpen}
        onClose={() => setInspectorOpen(false)}
        title="Category 3 Architecture & SDK Inspector"
        subtitle="Inspect Anthropic Sonnet 5.5 Prefix Caching & Sliding-Window Compaction implementation"
        maxWidthClass="max-w-3xl"
      >
        <div className="space-y-4">
          <div
            role="tablist"
            aria-label="Category 3 inspector sections"
            onKeyDown={handleInspectorTabKeyDown}
            className="mwg-tablist border-b border-slate-200"
          >
            {(
              [
                ['code', 'Python SDK Comparison'],
                ['schema', 'Session Memory JSON Schema'],
              ] as const
            ).map(([tid, label]) => (
              <button
                key={tid}
                type="button"
                role="tab"
                id={`cat3-insp-tab-${tid}`}
                aria-selected={inspectorTab === tid}
                tabIndex={inspectorTab === tid ? 0 : -1}
                onClick={() => setInspectorTab(tid)}
                className={`mwg-tab px-4 py-2 text-xs font-bold ${
                  inspectorTab === tid ? 'text-emerald-700' : 'text-slate-500 hover:text-slate-900'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div role="tabpanel" aria-labelledby="cat3-insp-tab-code" hidden={inspectorTab !== 'code'}>
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

          <div role="tabpanel" aria-labelledby="cat3-insp-tab-schema" hidden={inspectorTab !== 'schema'}>
            <pre className="max-h-96 overflow-auto rounded-xl bg-slate-950 p-3.5 font-mono text-[11px] leading-relaxed text-emerald-300">
              {JSON.stringify(presetsData.memory_schema, null, 2)}
            </pre>
          </div>
        </div>
      </NativeModal>
    </div>
  )
}
