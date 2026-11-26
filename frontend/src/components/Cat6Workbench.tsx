import { useEffect, useMemo, useState, type CSSProperties, type KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertCircle,
  ArrowLeft,
  Bot,
  CheckCircle2,
  Code2,
  Cpu,
  DollarSign,
  GitBranch,
  Play,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  TrendingDown,
  Users,
  XCircle,
  Zap,
} from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { runCat6Arena } from '../api'
import type {
  ArchetypeSpec,
  Cat6PresetsResponse,
  Cat6RungId,
  Cat6RunResponse,
  CreditShieldCredentials,
} from '../types'
import { NativeModal } from './NativeModal'
import { ReplayStatus, RevealPlaceholder, useStagedReveal } from './StagedReveal'
import { DesignMark } from './DesignMark'
import { WrappedAxisTick } from './ChartTicks'

interface Cat6WorkbenchProps {
  archetype: ArchetypeSpec
  presetsData: Cat6PresetsResponse
  creds: CreditShieldCredentials
  onRefreshSystemStatus: () => void
}

// Display order: the two versions without the lever (shared bus) first, then the two with it (isolated + cached);
// Sonnet before Haiku agents + Sonnet patch author in each pair. Rung ids are internal; the numbers follow this order.
const CAT6_RUNGS: Cat6RungId[] = [
  'unisolated_broadcast_swarm',
  'unisolated_tiered_swarm',
  'isolated_cached_sonnet_swarm',
  'tiered_hybrid_cpo_swarm',
]

const RUNG_SHORT_LABEL: Record<Cat6RungId, string> = {
  unisolated_broadcast_swarm: '1. Shared-Bus Sonnet',
  unisolated_tiered_swarm: '2. Shared-Bus Haiku + Sonnet',
  isolated_cached_sonnet_swarm: '3. Isolated Sonnet',
  tiered_hybrid_cpo_swarm: '4. Isolated Haiku + Sonnet',
}

const RUNG_PENDING_TITLE: Record<Cat6RungId, string> = {
  unisolated_broadcast_swarm: '1. Shared-Bus Swarm + Sandbox Gate (Sonnet 5.5)',
  unisolated_tiered_swarm: '2. Shared-Bus Swarm + Sandbox Gate (Haiku agents + Sonnet Author)',
  isolated_cached_sonnet_swarm: '3. Isolated + Cached Prefix + Sandbox (Sonnet 5.5)',
  tiered_hybrid_cpo_swarm: '4. Isolated + Cached Prefix + Sandbox (Haiku agents + Sonnet Author)',
}

const SHARED_BUS_RUNGS: ReadonlySet<Cat6RungId> = new Set<Cat6RungId>([
  'unisolated_broadcast_swarm',
  'unisolated_tiered_swarm',
])
const TIERED_RUNGS: ReadonlySet<Cat6RungId> = new Set<Cat6RungId>([
  'tiered_hybrid_cpo_swarm',
  'unisolated_tiered_swarm',
])

// The design: the deck's lever (rows) x the model set-up (columns), one app rung per cell.
const CAT6_DESIGN_COLUMNS = ['Sonnet 5.5', 'Haiku agents + Sonnet patch author'] as const
const CAT6_DESIGN_ROWS: { label: string; rungs: [Cat6RungId, Cat6RungId] }[] = [
  {
    label: 'Without: shared bus, same instructions, sandbox check with one retry',
    rungs: ['unisolated_broadcast_swarm', 'unisolated_tiered_swarm'],
  },
  {
    label: 'With: isolated agents + cached repo prefix, sandbox check with one retry',
    rungs: ['isolated_cached_sonnet_swarm', 'tiered_hybrid_cpo_swarm'],
  },
]

// Without the lever = red (rose), with it = green (emerald), as on the other screens; the model is told apart by
// label, with a darker / lighter shade of the same hue only where two series must be distinguished in a chart.
const RUNG_COLOR: Record<Cat6RungId, string> = {
  unisolated_broadcast_swarm: '#e11d48', // rose-600
  unisolated_tiered_swarm: '#fb7185', // rose-400
  isolated_cached_sonnet_swarm: '#047857', // emerald-700
  tiered_hybrid_cpo_swarm: '#10b981', // emerald-500
}

// Card / tab theme per design row, the same classes the Archetype 3 cards use.
const isWithoutLever = (rid: Cat6RungId): boolean => SHARED_BUS_RUNGS.has(rid)

const ORG_SIZES = [
  { label: '10 Devs (Pod)', value: 10 },
  { label: '50 Devs (Core)', value: 50 },
  { label: '100 Devs (Org)', value: 100 },
  { label: '250 Devs (Enterprise)', value: 250 },
]

type CacheEntryMode = 'cold_repo_write' | 'warm_repo_cache'

export function Cat6Workbench({
  archetype,
  presetsData,
  creds,
  onRefreshSystemStatus,
}: Cat6WorkbenchProps) {
  const [selectedPresetId, setSelectedPresetId] = useState<string>(
    presetsData.presets[0]?.id ?? 'inc-01'
  )
  const [cacheMode, setCacheMode] = useState<CacheEntryMode>('cold_repo_write')
  const [loadingArena, setLoadingArena] = useState(false)
  const [arenaError, setArenaError] = useState<string | null>(null)
  const [runResponse, setRunResponse] = useState<Cat6RunResponse | null>(null)

  const [activeRungView, setActiveRungView] = useState<Cat6RungId>('tiered_hybrid_cpo_swarm')
  const [runsPerDevPerDay, setRunsPerDevPerDay] = useState<number>(25)
  const [orgDevs, setOrgDevs] = useState<number>(50)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [inspectorTab, setInspectorTab] = useState<'code' | 'buggy' | 'sandbox'>('code')

  const selectedPreset = useMemo(
    () => presetsData.presets.find((p) => p.id === selectedPresetId) ?? presetsData.presets[0],
    [presetsData.presets, selectedPresetId]
  )

  const reveal = useStagedReveal('swarm versions')

  // `staged`: a replay *click* clears the cards and reveals them one by one (the first load on mount stays instant).
  const executeArena = async (presetIdToRun: string, staged = false) => {
    const stage = staged && creds.mode === 'replay'
    setLoadingArena(true)
    setArenaError(null)
    if (stage) reveal.begin()
    try {
      const data = await runCat6Arena(
        {
          preset_id: presetIdToRun,
          use_case: 'checkout_ci_self_healing_swarm',
          rungs: CAT6_RUNGS,
          mode: creds.mode,
        },
        creds
      )
      setRunResponse(data)
      onRefreshSystemStatus()
      if (stage) reveal.run(CAT6_RUNGS.filter((rid) => data.results.some((r) => r.rung_id === rid)))
    } catch (err) {
      if (stage) reveal.reset()
      setArenaError(err instanceof Error ? err.message : 'Failed to run Category 6 swarm arena.')
    } finally {
      setLoadingArena(false)
    }
  }

  useEffect(() => {
    void executeArena(selectedPresetId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const arenaBusy = loadingArena || reveal.replaying

  const handleSelectPreset = (presetId: string) => {
    setSelectedPresetId(presetId)
    void executeArena(presetId)
  }

  const naiveRes = useMemo(
    () => runResponse?.results.find((r) => r.rung_id === 'unisolated_broadcast_swarm') ?? null,
    [runResponse]
  )
  const isoRes = useMemo(
    () => runResponse?.results.find((r) => r.rung_id === 'isolated_cached_sonnet_swarm') ?? null,
    [runResponse]
  )
  const hybridRes = useMemo(
    () => runResponse?.results.find((r) => r.rung_id === 'tiered_hybrid_cpo_swarm') ?? null,
    [runResponse]
  )
  const busTieredRes = useMemo(
    () => runResponse?.results.find((r) => r.rung_id === 'unisolated_tiered_swarm') ?? null,
    [runResponse]
  )
  // Rungs requested but with no recorded run yet (replay only): shown as "run pending".
  const pendingRungs = useMemo(() => runResponse?.pending_rungs ?? [], [runResponse])
  // Rungs with a result, in rung order: the tab list and its keyboard navigation use these.
  const shownRungs = useMemo(
    () => CAT6_RUNGS.filter((rid) => runResponse?.results.some((r) => r.rung_id === rid)),
    [runResponse]
  )

  // Agent-by-Agent Prompt Context Bloat LineChart data
  const turnContextCurveData = useMemo(() => {
    if (!runResponse) return []
    const steps = ['Agent 1', 'Agent 2', 'Agent 3', 'Agent 4', 'Agent 5', 'Agent 6']
    const getPromptTok = (
      turns: typeof naiveRes extends null ? never : NonNullable<typeof naiveRes>['agent_turns'] | undefined,
      idx: number
    ): number | null => {
      const t = turns?.[idx]
      if (!t) return null
      return (
        t.finops.input_tokens +
        t.finops.cache_creation_tokens +
        t.finops.cache_read_tokens
      )
    }
    const maxLen = Math.max(
      naiveRes?.agent_turns.length ?? 0,
      isoRes?.agent_turns.length ?? 0,
      hybridRes?.agent_turns.length ?? 0,
      busTieredRes?.agent_turns.length ?? 0
    )
    const rows = []
    for (let i = 0; i < maxLen; i += 1) {
      const label =
        naiveRes?.agent_turns[i]?.agent_role ??
        isoRes?.agent_turns[i]?.agent_role ??
        steps[i] ??
        `Agent ${i + 1}`
      rows.push({
        agent: label.replace('orchestrator_', 'orch_'),
        naiveTok: getPromptTok(naiveRes?.agent_turns, i),
        isoTok: getPromptTok(isoRes?.agent_turns, i),
        hybridTok: getPromptTok(hybridRes?.agent_turns, i),
        busTieredTok: getPromptTok(busTieredRes?.agent_turns, i),
      })
    }
    return rows
  }, [runResponse, naiveRes, isoRes, hybridRes, busTieredRes])

  // Shared scale for the per-rung prompt-load meters: the largest rung in this response
  const promptMeterMax = useMemo(() => {
    if (!runResponse) return 1
    return Math.max(
      1,
      ...runResponse.results.map(
        (r) => r.total_uncached_input_tokens + r.total_cache_creation_tokens + r.total_cache_read_tokens
      )
    )
  }, [runResponse])

  // Scorecard rows and results in display order (whatever order the API returned them in)
  const orderedScorecard = useMemo(
    () =>
      [...(runResponse?.portfolio_scorecard ?? [])].sort(
        (a, b) => CAT6_RUNGS.indexOf(a.rung_id) - CAT6_RUNGS.indexOf(b.rung_id)
      ),
    [runResponse]
  )
  const orderedResults = useMemo(
    () => [...(runResponse?.results ?? [])].sort((a, b) => CAT6_RUNGS.indexOf(a.rung_id) - CAT6_RUNGS.indexOf(b.rung_id)),
    [runResponse]
  )

  // Portfolio CpR vs CpO BarChart data ($ / 1,000 PRs)
  const portfolioBarData = useMemo(() => {
    if (!runResponse?.portfolio_scorecard) return []
    return orderedScorecard.map((row) => ({
      rungId: row.rung_id,
      name: RUNG_SHORT_LABEL[row.rung_id],
      CpR:
        cacheMode === 'warm_repo_cache' ? row.avg_cpr_warm_per_1k_usd : row.avg_cpr_cold_per_1k_usd,
      CpO:
        cacheMode === 'warm_repo_cache'
          ? row.portfolio_cpo_warm_per_1k_usd
          : row.portfolio_cpo_cold_per_1k_usd,
    }))
  }, [runResponse, orderedScorecard, cacheMode])

  const handleRungTabKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (shownRungs.length === 0) return
    const idx = Math.max(0, shownRungs.indexOf(activeRungView))
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      const next = shownRungs[(idx + 1) % shownRungs.length]
      setActiveRungView(next)
      document.getElementById(`cat6-xray-tab-${next}`)?.focus()
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      const prev = shownRungs[(idx - 1 + shownRungs.length) % shownRungs.length]
      setActiveRungView(prev)
      document.getElementById(`cat6-xray-tab-${prev}`)?.focus()
    } else if (e.key === 'Home') {
      e.preventDefault()
      setActiveRungView(shownRungs[0])
      document.getElementById(`cat6-xray-tab-${shownRungs[0]}`)?.focus()
    } else if (e.key === 'End') {
      e.preventDefault()
      const last = shownRungs[shownRungs.length - 1]
      setActiveRungView(last)
      document.getElementById(`cat6-xray-tab-${last}`)?.focus()
    }
  }

  const handleInspectorTabKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const order: Array<'code' | 'buggy' | 'sandbox'> = ['code', 'buggy', 'sandbox']
    const idx = order.indexOf(inspectorTab)
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      const next = order[(idx + 1) % order.length]
      setInspectorTab(next)
      document.getElementById(`cat6-insp-tab-${next}`)?.focus()
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      const prev = order[(idx - 1 + order.length) % order.length]
      setInspectorTab(prev)
      document.getElementById(`cat6-insp-tab-${prev}`)?.focus()
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-7 sm:px-6">
      {/* Top Breadcrumb & Inspector Trigger */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Matrix Overview
        </Link>

        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-lg bg-slate-100 px-2.5 py-1 font-mono text-[11px] font-semibold text-slate-700">
            PR-SANDBOX-GATE-01 · 10 Checks · ~{presetsData.approx_shared_repo_tokens.toLocaleString()} tok Shared Repo
          </span>
          <button
            type="button"
            onClick={() => setInspectorOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 shadow-xs transition hover:border-slate-400 hover:text-slate-900"
          >
            <Code2 className="h-3.5 w-3.5 text-violet-700" />
            Swarm Code &amp; Sandbox Inspector
          </button>
        </div>
      </div>

      {/* Category 6 Header Banner & Incident Selector */}
      <section className="overflow-hidden rounded-2xl border border-violet-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 bg-violet-700 px-6 py-2.5 text-white">
          <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider">
            <span>
              {archetype.category_label} · {archetype.autonomy_tier_label}
            </span>
            <span className="rounded bg-white/20 px-2 py-0.5 font-mono text-[11px]">
              {archetype.token_band}
            </span>
          </div>
          <span className="font-mono text-xs font-bold text-violet-100">{archetype.dynamics}</span>
        </div>

        <div className="space-y-4 px-6 py-5">
          <div>
            <h1 className="text-xl font-extrabold tracking-tight text-slate-900 sm:text-2xl">
              {archetype.title} — {archetype.novamart_product_name}
            </h1>
            <p className="mt-1 text-sm leading-relaxed text-slate-600">
              One swarm with and without the deck&apos;s lever,{' '}
              <strong className="text-slate-900">
                Isolated Sub-Agent Contexts + Byte-Identical Repo Prefix Cache
              </strong>
              : a <strong className="text-slate-900">Shared-Bus Swarm</strong> against the isolated
              swarm, each on Sonnet 5.5 and on{' '}
              <strong className="text-slate-900">Haiku agents + a Sonnet Patch Author</strong>. Every
              version has the same role instructions and PR-SANDBOX-GATE-01 with one retry, graded by{' '}
              <strong className="text-violet-800">Cost per Verified Outcome (CpO)</strong>.
            </p>
          </div>

          {/* 3 Incident / Feature Cards */}
          <div className="grid gap-3 md:grid-cols-3">
            {presetsData.presets.map((p) => {
              const active = p.id === selectedPresetId
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => handleSelectPreset(p.id)}
                  className={`flex flex-col justify-between rounded-xl border p-3.5 text-left transition ${
                    active
                      ? 'border-violet-600 bg-violet-50/70 ring-2 ring-violet-500/20'
                      : 'border-slate-200 bg-slate-50/60 hover:border-slate-300'
                  }`}
                >
                  <div>
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[11px] font-bold text-slate-500">
                        {p.pr_id} · {p.service_name}
                      </span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                          p.id === 'inc-01'
                            ? 'bg-rose-100 text-rose-800'
                            : p.id === 'inc-02'
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-indigo-100 text-indigo-800'
                        }`}
                      >
                        {p.use_case_tag}
                      </span>
                    </div>
                    <div className="mt-1.5 text-xs font-extrabold text-slate-900">{p.title}</div>
                    <p className="mt-1 text-[11px] leading-snug text-slate-600">{p.subtitle}</p>
                  </div>
                  <div className="mt-2.5 border-t border-slate-200/70 pt-2 font-mono text-[11px] font-bold text-slate-800">
                    {p.standard_ref} · {p.module_filename}
                  </div>
                </button>
              )
            })}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <div className="inline-flex rounded-lg bg-slate-200/80 p-1">
                <button
                  type="button"
                  onClick={() => setCacheMode('cold_repo_write')}
                  className={`rounded-md px-3 py-1.5 text-xs font-bold transition ${
                    cacheMode === 'cold_repo_write'
                      ? 'bg-slate-900 text-white shadow-xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Cold Repo Cache Write ($2.50/$0.125M)
                </button>
                <button
                  type="button"
                  onClick={() => setCacheMode('warm_repo_cache')}
                  className={`rounded-md px-3 py-1.5 text-xs font-bold transition ${
                    cacheMode === 'warm_repo_cache'
                      ? 'bg-violet-700 text-white shadow-xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Warm Repo Prefix Cache ($0.10/$0.01M)
                </button>
              </div>
            </div>

            <div className="flex flex-col items-end gap-1">
              <button
                type="button"
                aria-disabled={arenaBusy}
                aria-busy={arenaBusy}
                onClick={() => {
                  if (arenaBusy) return
                  void executeArena(selectedPresetId, true)
                }}
                className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-bold text-white shadow-sm transition ${
                  arenaBusy
                    ? 'cursor-not-allowed bg-slate-400'
                    : creds.mode === 'live'
                      ? 'bg-amber-600 hover:bg-amber-700'
                      : 'bg-violet-700 hover:bg-violet-800'
                }`}
              >
                {creds.mode === 'live' ? (
                  <Zap className="h-3.5 w-3.5" />
                ) : (
                  <Play className="h-3.5 w-3.5" />
                )}
                {creds.mode === 'live'
                  ? loadingArena
                    ? 'Running Multi-Agent Swarm...'
                    : 'Run Live Claude 5.5 Swarm (4 Versions)'
                  : arenaBusy
                    ? 'Replaying…'
                    : 'Replay Verified Swarm & Sandbox'}
              </button>
              <ReplayStatus status={reveal.status} />
            </div>
          </div>
        </div>
      </section>

      {arenaError && (
        <div className="flex items-start gap-2.5 rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-xs text-rose-900">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />
          <div>
            <div className="font-bold">Swarm Execution Halted</div>
            <p className="mt-0.5">{arenaError}</p>
          </div>
        </div>
      )}

      {runResponse && (
        <>
          {/* FinOps Banner */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-violet-300 bg-violet-50 px-5 py-3.5 text-xs text-violet-950">
            <div className="flex items-center gap-2.5 font-semibold">
              <TrendingDown className="h-4 w-4 shrink-0 text-violet-700" />
              <span>{runResponse.swarm_callout}</span>
            </div>
          </div>

          {/* Design: with / without the lever x model set-up (portfolio of the 3 incidents) */}
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
            <h2 id="cat6-design-caption" className="text-sm font-extrabold text-slate-900">
              With and Without the Lever, by Model Set-Up (3-Incident Portfolio)
            </h2>
            <p className="text-[11px] text-slate-500">
              Each cell: app version (numbered as the cards below), verified PRs, portfolio CpO per 1,000 verified (
              {cacheMode === 'warm_repo_cache' ? 'warm' : 'cold'} cache).
            </p>
            <div
              tabIndex={0}
              role="region"
              aria-labelledby="cat6-design-caption"
              className="table-wrapper mt-3 rounded-xl border border-slate-200"
            >
              <table className="mwg-table text-xs" data-table="cat6-design">
                <thead className="bg-slate-900 text-left text-[11px] uppercase tracking-wider text-slate-200">
                  <tr>
                    <th scope="col" className="px-4 py-2.5">
                      Design
                    </th>
                    {CAT6_DESIGN_COLUMNS.map((c) => (
                      <th key={c} scope="col" className="px-4 py-2.5">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {CAT6_DESIGN_ROWS.map((row) => (
                    <tr key={row.label}>
                      <th
                        scope="row"
                        className={`border-l-4 px-4 py-3 text-left font-bold ${
                          isWithoutLever(row.rungs[0])
                            ? 'border-l-rose-500 bg-rose-50 text-rose-900'
                            : 'border-l-emerald-600 bg-emerald-50/90 text-emerald-900'
                        }`}
                      >
                        {row.label}
                      </th>
                      {row.rungs.map((rid) => {
                        const sc = runResponse.portfolio_scorecard.find((x) => x.rung_id === rid)
                        if (!sc || pendingRungs.includes(rid)) {
                          return (
                            <td key={rid} className="px-4 py-3 font-mono text-slate-500">
                              {RUNG_SHORT_LABEL[rid]} · run pending
                            </td>
                          )
                        }
                        const cpo =
                          cacheMode === 'warm_repo_cache'
                            ? sc.portfolio_cpo_warm_per_1k_usd
                            : sc.portfolio_cpo_cold_per_1k_usd
                        return (
                          <td key={rid} className="px-4 py-3 font-mono text-slate-800">
                            <div className="font-bold">{RUNG_SHORT_LABEL[rid]}</div>
                            <div>
                              {sc.verified_outcomes_count}/{sc.prs_evaluated} verified · CpO{' '}
                              {cpo != null && cpo > 0 ? `$${cpo.toFixed(2)}` : 'Unverified (∞)'} / 1k
                            </div>
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* Swarm Arena Cards in display order (without: Sonnet, Haiku agents; with: Sonnet, Haiku agents);
              pending rungs shown as placeholders in their place */}
          <section
            ref={reveal.resultsRef}
            aria-busy={reveal.replaying}
            className="grid scroll-mt-24 gap-4 md:grid-cols-2 xl:grid-cols-4"
          >
            {CAT6_RUNGS.map((rid) => {
              const r = runResponse.results.find((x) => x.rung_id === rid)
              if (!r) {
                if (!pendingRungs.includes(rid)) return null
                return (
                  <article
                    key={rid}
                    className="flex flex-col rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-5"
                  >
                    <span className="w-fit rounded-md bg-slate-200 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wider text-slate-700">
                      Run pending
                    </span>
                    <h2 className="mt-2.5 text-sm font-extrabold text-slate-900">{RUNG_PENDING_TITLE[rid]}</h2>
                    <p className="mt-2 text-[11px] leading-relaxed text-slate-600">
                      {SHARED_BUS_RUNGS.has(rid) ? 'Shared growing thread, uncached' : 'Isolated agents, cached repo prefix'}
                      {TIERED_RUNGS.has(rid) ? '; Haiku agents + Sonnet patch author' : '; Sonnet 5.5'}. No recorded run to
                      replay yet; a live run executes it.
                    </p>
                  </article>
                )
              }
              if (!reveal.isVisible(r.rung_id)) {
                return (
                  <RevealPlaceholder
                    key={r.rung_id}
                    title={r.rung_title}
                    withLever={!isWithoutLever(r.rung_id)}
                    className="min-h-[420px]"
                  />
                )
              }
              const isNaive = r.rung_id === 'unisolated_broadcast_swarm'
              const without = isWithoutLever(r.rung_id)
              // the same classes as the Archetype 3 cards: red (rose) without the lever, green (emerald) with it
              const borderTheme = without ? 'border-rose-300' : 'border-emerald-400 ring-1 ring-emerald-200'
              const headerBg = without ? 'bg-rose-50' : 'bg-emerald-50/90'
              const badgeBg = without ? 'bg-rose-600 text-white' : 'bg-emerald-700 text-white'
              const cpr1k =
                cacheMode === 'warm_repo_cache'
                  ? r.cost_per_1k_runs_warm_usd
                  : r.cost_per_1k_runs_cold_usd
              const savings =
                cacheMode === 'warm_repo_cache'
                  ? r.savings_vs_naive_warm_pct
                  : r.savings_vs_naive_cold_pct
              const totPrompt =
                r.total_uncached_input_tokens +
                r.total_cache_creation_tokens +
                r.total_cache_read_tokens
              const sbx = r.sandbox_report
              const verified = Boolean(sbx?.verified_outcome)

              return (
                <article
                  key={r.rung_id}
                  className={`flex flex-col justify-between overflow-hidden rounded-2xl border bg-white shadow-xs ${borderTheme}`}
                >
                  <div>
                    <div className={`border-b border-slate-100 px-5 pb-3 pt-4 ${headerBg}`}>
                      <div className="flex items-center justify-between gap-2">
                        <span
                          className={`rounded-md px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wider ${badgeBg}`}
                        >
                          {r.badge_text}
                        </span>
                        <span className="shrink-0 font-mono text-[11px] font-bold text-slate-600">
                          {r.agent_turns.length} calls
                        </span>
                      </div>

                      <div className="mt-2.5 flex items-center gap-1.5">
                        <DesignMark withLever={!without} />
                        <h2 className="text-sm font-extrabold text-slate-900">{r.rung_title}</h2>
                      </div>
                      <div className="mt-0.5 font-mono text-[11px] text-slate-500">
                        {TIERED_RUNGS.has(r.rung_id)
                          ? `Haiku calls: ${r.haiku_turns} · Sonnet calls: ${r.sonnet_turns} · Retries: ${r.retries_used}`
                          : `Anthropic · ${r.primary_model_id} · Retries: ${r.retries_used}`}
                      </div>
                    </div>
                    <div className="px-5">

                    <div className="mt-4 flex items-baseline justify-between gap-2 border-t border-slate-100 pt-3">
                      <div>
                        <div className="text-[10px] font-bold uppercase text-slate-400">
                          {verified
                            ? `CpO / 1,000 VERIFIED (${cacheMode === 'warm_repo_cache' ? 'WARM' : 'COLD'})`
                            : `CpR / 1,000 RUNS (${verified ? 'VERIFIED' : 'UNVERIFIED'})`}
                        </div>
                        <div className="font-mono text-2xl font-extrabold text-slate-900">
                          ${cpr1k.toFixed(2)}
                        </div>
                      </div>
                      {!isNaive && savings > 0 && (
                        <span
                          className={`rounded-full px-2.5 py-0.5 text-right font-mono text-xs font-extrabold ${
                            without ? 'bg-rose-100 text-rose-800' : 'bg-emerald-100 text-emerald-800'
                          }`}
                        >
                          -{savings.toFixed(1)}%
                          <span className="block text-[9px] font-bold">vs shared-bus Sonnet</span>
                        </span>
                      )}
                    </div>

                    {/* Native <progress> Band 5 Context Consumption Meter (empty element per progress guide) */}
                    <div className="mt-3 rounded-lg border border-slate-100 bg-slate-50 p-2.5">
                      <div className="mb-1 flex items-center justify-between text-[10px] font-bold text-slate-600">
                        <span>Prompt Tokens / Run (vs. largest version)</span>
                        <span className="font-mono">
                          {totPrompt.toLocaleString()} / {promptMeterMax.toLocaleString()} tok
                        </span>
                      </div>
                      <progress
                        className="mwg-progress"
                        max={promptMeterMax}
                        value={Math.min(promptMeterMax, totPrompt)}
                        aria-label={`${r.rung_title} prompt token load`}
                        style={
                          {
                            '--progress-bar-fill': RUNG_COLOR[r.rung_id],
                            '--progress-bar-track': '#e2e8f0',
                          } as CSSProperties
                        }
                      />
                    </div>

                    <div className="mt-3 grid grid-cols-2 gap-2 rounded-xl bg-slate-50 p-3 font-mono text-[11px]">
                      <div>
                        <span className="block text-[9px] text-slate-400">UNCACHED IN</span>
                        <span className="font-bold text-slate-900">
                          {r.total_uncached_input_tokens.toLocaleString()} tok
                        </span>
                      </div>
                      <div>
                        <span className="block text-[9px] text-slate-400">CACHE W / R</span>
                        <span className="font-bold text-slate-900">
                          {r.total_cache_creation_tokens.toLocaleString()} /{' '}
                          {r.total_cache_read_tokens.toLocaleString()}
                        </span>
                      </div>
                      <div>
                        <span className="block text-[9px] text-slate-400">OUTPUT TOKENS</span>
                        <span className="font-bold text-slate-900">
                          {r.total_output_tokens.toLocaleString()} tok
                        </span>
                      </div>
                      <div>
                        <span className="block text-[9px] text-slate-400">LATENCY</span>
                        <span className="font-bold text-slate-900">
                          {(r.total_latency_ms / 1000).toFixed(1)}s
                        </span>
                      </div>
                    </div>

                    {/* Sandbox 10-Check Breakdown Badges */}
                    {sbx && (
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        <span
                          className={`rounded-md px-2 py-0.5 font-mono text-[10px] font-bold ${
                            verified
                              ? 'bg-emerald-100 text-emerald-800'
                              : 'bg-rose-100 text-rose-800'
                          }`}
                        >
                          Sandbox: {sbx.passed_checks}/{sbx.total_checks}{' '}
                          {verified ? '(VERIFIED)' : '(FAIL)'}
                        </span>
                        <span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[10px] font-bold text-slate-700">
                          CI {sbx.ci_unit_passed}/4 · Adv {sbx.adversarial_passed}/4 · AST{' '}
                          {sbx.ast_passed}/2
                        </span>
                      </div>
                    )}
                    </div>
                  </div>

                  <ul className="mx-5 mb-5 mt-3 space-y-1 border-t border-slate-100 pt-2.5 text-[11px] leading-relaxed text-slate-600">
                    {r.architectural_notes.map((n, i) => (
                      <li key={i}>• {n}</li>
                    ))}
                  </ul>
                </article>
              )
            })}
          </section>

          {/* 2-Up Charts: Agent Context Bloat & Portfolio CpR vs CpO */}
          <section className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-extrabold text-slate-900">
                    Prompt Tokens per Turn: With and Without Context Isolation
                  </h2>
                  <p className="text-[11px] text-slate-500">
                    Prompt tokens per swarm handoff step (O(N) bus accumulation vs. flat isolated prefixes)
                  </p>
                </div>
                <Bot className="h-4 w-4 text-violet-700" />
              </div>
              <div className="mt-4 h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={turnContextCurveData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    {/* interval 0: every agent turn keeps its label (security_critic was thinned out at 1024 px) */}
                    <XAxis dataKey="agent" interval={0} height={28} tick={<WrappedAxisTick fontSize={9} maxChars={16} maxLines={1} />} />
                    <YAxis
                      tick={{ fontSize: 11 }}
                      tickFormatter={(v) => `${Math.round(Number(v) / 1000)}k`}
                    />
                    <Tooltip
                      formatter={(val: unknown) => `${Number(val).toLocaleString()} prompt tok`}
                    />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Line
                      type="monotone"
                      dataKey="naiveTok"
                      name={RUNG_SHORT_LABEL.unisolated_broadcast_swarm}
                      stroke={RUNG_COLOR.unisolated_broadcast_swarm}
                      strokeWidth={2.5}
                    />
                    {busTieredRes && (
                      <Line
                        type="monotone"
                        dataKey="busTieredTok"
                        name={RUNG_SHORT_LABEL.unisolated_tiered_swarm}
                        stroke={RUNG_COLOR.unisolated_tiered_swarm}
                        strokeWidth={2}
                        strokeDasharray="5 3"
                      />
                    )}
                    <Line
                      type="monotone"
                      dataKey="isoTok"
                      name={RUNG_SHORT_LABEL.isolated_cached_sonnet_swarm}
                      stroke={RUNG_COLOR.isolated_cached_sonnet_swarm}
                      strokeWidth={2.5}
                    />
                    <Line
                      type="monotone"
                      dataKey="hybridTok"
                      name={RUNG_SHORT_LABEL.tiered_hybrid_cpo_swarm}
                      stroke={RUNG_COLOR.tiered_hybrid_cpo_swarm}
                      strokeWidth={2}
                      strokeDasharray="5 3"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-extrabold text-slate-900">
                    Cost per Run (CpR) vs. Cost per Verified Outcome (CpO)
                  </h2>
                  <p className="text-[11px] text-slate-500">
                    3-PR Portfolio ($ per 1,000 runs vs. $ per 1,000 sandbox-verified PRs; equal when every run verifies)
                  </p>
                </div>
                <GitBranch className="h-4 w-4 text-violet-700" />
              </div>
              <div className="mt-4 h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={portfolioBarData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    {/* interval 0: every bar keeps its label; labels wrap to two lines instead of overlapping */}
                    <XAxis dataKey="name" interval={0} height={36} tick={<WrappedAxisTick maxChars={14} />} />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
                    <Tooltip formatter={(val: unknown) => `$${Number(val).toFixed(2)} / 1k`} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Bar dataKey="CpR" name="Avg CpR ($/1k runs)" fill="#94a3b8" radius={[4, 4, 0, 0]} />
                    <Bar
                      dataKey="CpO"
                      name="Portfolio CpO ($/1k Verified; red = without the lever, green = with)"
                      fill="#047857"
                      radius={[4, 4, 0, 0]}
                    >
                      {portfolioBarData.map((d) => (
                        <Cell key={d.rungId} fill={RUNG_COLOR[d.rungId]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </section>

          {/* 3-PR Portfolio CpO & Verification Scorecard */}
          {runResponse.portfolio_scorecard.length > 0 && (
            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 id="cat6-cpo-caption" className="text-sm font-extrabold text-slate-900">
                    3-Incident Swarm Portfolio Scorecard (CpO · Verified Outcomes · Daily Band 5 Load)
                  </h2>
                  <p className="text-[11px] text-slate-500">
                    Aggregates CI/CD Failure Triage (PR-4812), Security Threat Hunt (SEC-772) &amp;
                    Split-Cart Concurrency Feature (FEAT-619)
                  </p>
                </div>
                <ShieldCheck className="h-4 w-4 text-violet-700" />
              </div>

              <div
                tabIndex={0}
                role="region"
                aria-labelledby="cat6-cpo-caption"
                className="table-wrapper mt-4 rounded-xl border border-slate-200"
              >
                <table className="mwg-table text-xs" data-table="cat6-cpo">
                  <thead className="bg-slate-900 text-left text-[11px] uppercase tracking-wider text-slate-200">
                    <tr>
                      <th scope="col" className="px-4 py-2.5">
                        Swarm Version
                      </th>
                      <th scope="col" className="px-4 py-2.5">
                        Verified PRs
                      </th>
                      <th scope="col" className="px-4 py-2.5">
                        Sandbox Checks
                      </th>
                      <th scope="col" className="px-4 py-2.5">
                        Avg Tok / Run · /Dev/Day (25x)
                      </th>
                      <th scope="col" className="px-4 py-2.5 text-right">
                        CpR / 1k ({cacheMode === 'warm_repo_cache' ? 'Warm' : 'Cold'})
                      </th>
                      <th scope="col" className="px-4 py-2.5 text-right">
                        Portfolio CpO / 1k
                      </th>
                      <th scope="col" className="px-4 py-2.5 text-right">
                        CpO Savings (vs Shared-Bus Sonnet)
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {orderedScorecard.map((row) => {
                      const cpr =
                        cacheMode === 'warm_repo_cache'
                          ? row.avg_cpr_warm_per_1k_usd
                          : row.avg_cpr_cold_per_1k_usd
                      const cpo =
                        cacheMode === 'warm_repo_cache'
                          ? row.portfolio_cpo_warm_per_1k_usd
                          : row.portfolio_cpo_cold_per_1k_usd
                      return (
                        <tr key={row.rung_id}>
                          <th
                            scope="row"
                            className={`border-l-4 px-4 py-3 text-left font-bold text-slate-900 ${
                              isWithoutLever(row.rung_id) ? 'border-l-rose-500' : 'border-l-emerald-600'
                            }`}
                          >
                            <div>{row.label}</div>
                            <div className="mt-0.5 font-mono text-[10px] font-normal text-slate-500">
                              {row.routing_summary}
                            </div>
                          </th>
                          <td className="px-4 py-3 font-mono font-bold text-slate-800">
                            {row.verified_outcomes_count}/{row.prs_evaluated} ({row.verified_outcome_rate_pct}%)
                          </td>
                          <td className="px-4 py-3 font-mono font-bold text-slate-800">
                            {row.checks_passed_total}/{row.checks_total} passed
                          </td>
                          <td className="px-4 py-3 font-mono text-slate-700">
                            {(row.avg_prompt_tokens + row.avg_output_tokens).toLocaleString()} ·{' '}
                            {(row.daily_tokens_per_dev_at_25_runs / 1_000_000).toFixed(2)}M/day
                          </td>
                          <td className="px-4 py-3 text-right font-mono font-semibold text-slate-800">
                            ${cpr.toFixed(2)}
                          </td>
                          <td className="px-4 py-3 text-right font-mono font-extrabold text-violet-900">
                            {cpo != null && cpo > 0 ? `$${cpo.toFixed(2)}` : 'Unverified (∞)'}
                          </td>
                          <td className="px-4 py-3 text-right font-mono font-bold text-violet-800">
                            {row.rung_id === 'unisolated_broadcast_swarm'
                              ? 'Baseline'
                              : row.cpo_savings_vs_naive_cold_pct == null
                                ? 'n/a (no verified baseline)'
                                : row.cpo_savings_vs_naive_cold_pct >= 0
                                  ? `-${row.cpo_savings_vs_naive_cold_pct.toFixed(1)}%`
                                  : `+${(-row.cpo_savings_vs_naive_cold_pct).toFixed(1)}%`}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* Interactive Swarm Handoff Trajectory, Sandbox Gate & Unified Diff X-Ray */}
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-extrabold text-slate-900">
                  Interactive Sub-Agent Trajectory, PR-SANDBOX-GATE-01 &amp; Unified Patch Diff
                </h2>
                <p className="text-[11px] text-slate-500">
                  Inspect the context each specialist agent receives (one shared bus, or isolated threads), the 10
                  deterministic sandbox checks, and the module patch each version produced
                </p>
              </div>

              <div
                role="tablist"
                aria-label="Inspect swarm rung trajectory"
                onKeyDown={handleRungTabKeyDown}
                className="mwg-tablist rounded-lg border border-slate-200 bg-slate-50 p-1"
              >
                {orderedResults.map((r) => {
                  const selected = r.rung_id === activeRungView
                  return (
                    <button
                      key={r.rung_id}
                      type="button"
                      role="tab"
                      id={`cat6-xray-tab-${r.rung_id}`}
                      aria-selected={selected}
                      tabIndex={selected ? 0 : -1}
                      onClick={() => setActiveRungView(r.rung_id)}
                      className={`mwg-tab rounded-md px-3 py-1.5 text-xs font-bold transition ${
                        selected
                          ? `bg-white shadow-xs ${isWithoutLever(r.rung_id) ? 'text-rose-700' : 'text-emerald-700'}`
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      <span
                        aria-hidden="true"
                        className={`mr-1.5 inline-block h-2 w-2 rounded-full ${
                          isWithoutLever(r.rung_id) ? 'bg-rose-500' : 'bg-emerald-600'
                        }`}
                      />
                      {RUNG_SHORT_LABEL[r.rung_id]}
                    </button>
                  )
                })}
              </div>
            </div>

            {orderedResults.map((rungObj) => {
              const visible = rungObj.rung_id === activeRungView
              return (
                <div
                  key={rungObj.rung_id}
                  role="tabpanel"
                  aria-labelledby={`cat6-xray-tab-${rungObj.rung_id}`}
                  hidden={!visible}
                >
                  <div className="mt-5 grid gap-5 lg:grid-cols-12">
                    {/* Left 7 cols: Non-exclusive Accordion of Sub-Agent Handoffs */}
                    <div className="space-y-2.5 lg:col-span-7">
                      <section
                        className="mwg-accordion space-y-2.5"
                        aria-label={`Swarm agent calls for ${rungObj.rung_title}`}
                      >
                        {rungObj.agent_turns.map((turn) => {
                          const turnTok =
                            turn.finops.input_tokens +
                            turn.finops.cache_creation_tokens +
                            turn.finops.cache_read_tokens
                          return (
                            <details
                              key={turn.step_number}
                              className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5"
                            >
                              <summary className="justify-between text-xs font-bold text-slate-900">
                                <span className="flex flex-wrap items-center gap-1.5">
                                  <span className="font-mono text-violet-800">
                                    Call #{turn.step_number} · {turn.agent_label}
                                  </span>
                                  <span
                                    className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${
                                      turn.model_id.includes('haiku')
                                        ? 'bg-violet-100 text-violet-900'
                                        : 'bg-slate-800 text-white'
                                    }`}
                                  >
                                    {turn.model_id}
                                  </span>
                                  {turn.attempt > 1 && (
                                    <span className="rounded bg-amber-100 px-1.5 py-0.5 font-mono text-[10px] text-amber-900">
                                      SELF-HEAL RETRY #{turn.attempt}
                                    </span>
                                  )}
                                </span>
                                <span className="ml-auto font-mono text-[11px] text-slate-600">
                                  {turnTok.toLocaleString()} in · {turn.finops.output_tokens} out
                                  {turn.finops.cache_read_tokens > 0
                                    ? ` · CR ${turn.finops.cache_read_tokens.toLocaleString()}`
                                    : turn.finops.cache_creation_tokens > 0
                                      ? ` · CW ${turn.finops.cache_creation_tokens.toLocaleString()}`
                                      : ''}
                                </span>
                              </summary>
                              <div className="mt-3 space-y-2 border-t border-slate-200 pt-2.5">
                                <div className="text-[10px] font-bold uppercase text-slate-500">
                                  Context Mode: {turn.context_mode} · Latency {turn.latency_ms} ms
                                </div>
                                <pre className="max-h-32 overflow-y-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-white p-2.5 font-mono text-[10px] text-slate-700">
                                  {turn.prompt_preview}
                                </pre>
                                <pre className="max-h-56 overflow-y-auto whitespace-pre-wrap rounded-lg bg-slate-950 p-2.5 font-mono text-[10px] text-slate-100">
                                  {turn.output_preview}
                                </pre>
                              </div>
                            </details>
                          )
                        })}
                      </section>
                    </div>

                    {/* Right 5 cols: PR-SANDBOX-GATE-01 + Unified Patch Diff */}
                    <div className="space-y-4 lg:col-span-5">
                      {rungObj.sandbox_report && (
                        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                          <div className="flex items-center justify-between gap-2">
                            <span className="inline-flex items-center gap-1.5 text-xs font-extrabold text-slate-900">
                              {rungObj.sandbox_report.verified_outcome ? (
                                <ShieldCheck className="h-4 w-4 text-emerald-700" />
                              ) : (
                                <ShieldAlert className="h-4 w-4 text-rose-600" />
                              )}
                              PR-SANDBOX-GATE-01 ({rungObj.sandbox_report.passed_checks}/
                              {rungObj.sandbox_report.total_checks} Passed)
                            </span>
                            <span className="font-mono text-[10px] text-slate-500">
                              {rungObj.sandbox_report.execution_ms} ms
                            </span>
                          </div>

                          <div className="mt-2.5 space-y-1.5">
                            {rungObj.sandbox_report.checks.map((chk) => (
                              <div
                                key={chk.check_id}
                                className="flex items-start justify-between gap-2 rounded-lg border border-slate-200/80 bg-white px-2.5 py-1.5 text-[11px]"
                              >
                                <div className="min-w-0">
                                  <div className="flex items-center gap-1.5 font-mono font-bold text-slate-800">
                                    {chk.passed ? (
                                      <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-700" />
                                    ) : (
                                      <XCircle className="h-3.5 w-3.5 shrink-0 text-rose-600" />
                                    )}
                                    <span>{chk.check_id}</span>
                                    <span className="rounded bg-slate-100 px-1 py-0.2 text-[9px] uppercase text-slate-600">
                                      {chk.category}
                                    </span>
                                  </div>
                                  <div className="mt-0.5 text-[10px] text-slate-600">{chk.name}</div>
                                  <div className="mt-0.5 break-all font-mono text-[10px] text-slate-500">
                                    {chk.detail}
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {rungObj.sandbox_report?.unified_diff && (
                        <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                          <div className="flex items-center gap-1.5 text-xs font-extrabold text-violet-300">
                            <Terminal className="h-3.5 w-3.5" />
                            Unified Patch Diff ({selectedPreset?.module_filename})
                          </div>
                          <pre className="mt-2 max-h-72 overflow-auto font-mono text-[10px] leading-relaxed text-slate-200">
                            {rungObj.sandbox_report.unified_diff}
                          </pre>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </section>

          {/* Per-Developer Daily Token & Org Cost Simulator (projected from this incident's measured runs) */}
          {naiveRes && isoRes && hybridRes && (
            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <DollarSign className="h-4 w-4 text-violet-700" />
                  <div>
                    <h2 className="text-sm font-extrabold text-slate-900">
                      Band 5 Engineering Org Simulator ({orgDevs} Engineers × {runsPerDevPerDay}{' '}
                      Swarm Runs / Dev / Day)
                    </h2>
                    <p className="text-[11px] text-slate-500">
                      Projects per-developer daily tokens and monthly org cost from each version&apos;s
                      measured tokens and cost per run on this incident
                    </p>
                  </div>
                </div>
                <Users className="h-4 w-4 text-slate-400" />
              </div>

              <div className="mt-4 grid gap-4 rounded-xl border border-slate-200 bg-slate-50 p-4 lg:grid-cols-2">
                <div>
                  <div className="flex items-center justify-between text-xs font-bold text-slate-700">
                    <label htmlFor="cat6-runs-slider">Swarm CI Tasks / Dev / Day</label>
                    <span className="font-mono text-violet-800">{runsPerDevPerDay} runs / day</span>
                  </div>
                  <input
                    id="cat6-runs-slider"
                    type="range"
                    min={5}
                    max={80}
                    step={5}
                    value={runsPerDevPerDay}
                    onChange={(e) => setRunsPerDevPerDay(Number(e.target.value))}
                    className="mt-2.5 w-full accent-violet-700"
                  />
                </div>

                <div>
                  <div className="text-xs font-bold text-slate-700">Engineering Org Size</div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {ORG_SIZES.map((sz) => (
                      <button
                        key={sz.value}
                        type="button"
                        onClick={() => setOrgDevs(sz.value)}
                        className={`rounded-lg px-2.5 py-1 font-mono text-[11px] font-bold transition ${
                          orgDevs === sz.value
                            ? 'bg-violet-700 text-white'
                            : 'bg-white text-slate-600 ring-1 ring-slate-200 hover:text-slate-900'
                        }`}
                      >
                        {sz.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className={`mt-4 grid gap-3 ${busTieredRes ? 'md:grid-cols-2 xl:grid-cols-4' : 'md:grid-cols-3'}`}>
                {[naiveRes, ...(busTieredRes ? [busTieredRes] : []), isoRes, hybridRes].map((r) => {
                  const perRun =
                    cacheMode === 'warm_repo_cache' ? r.warm_run_cost_usd : r.cold_run_cost_usd
                  const tokPerRun =
                    r.total_uncached_input_tokens +
                    r.total_cache_creation_tokens +
                    r.total_cache_read_tokens +
                    r.total_output_tokens
                  const dailyTokPerDev = tokPerRun * runsPerDevPerDay
                  const monthlyOrgCost = perRun * runsPerDevPerDay * 22 * orgDevs
                  const portfolioRow = runResponse.portfolio_scorecard.find(
                    (row) => row.rung_id === r.rung_id
                  )
                  const cpo1k =
                    cacheMode === 'warm_repo_cache'
                      ? portfolioRow?.portfolio_cpo_warm_per_1k_usd ?? 0
                      : portfolioRow?.portfolio_cpo_cold_per_1k_usd ?? 0

                  return (
                    <div
                      key={r.rung_id}
                      className={`rounded-xl border bg-slate-50/70 p-4 ${
                        isWithoutLever(r.rung_id) ? 'border-rose-200' : 'border-emerald-200'
                      }`}
                    >
                      <div className="flex items-center gap-1.5 text-xs font-extrabold text-slate-900">
                        {isWithoutLever(r.rung_id) ? (
                          <Bot className="h-3.5 w-3.5 shrink-0 text-rose-600" />
                        ) : r.rung_id === 'isolated_cached_sonnet_swarm' ? (
                          <Cpu className="h-3.5 w-3.5 shrink-0 text-emerald-700" />
                        ) : (
                          <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-emerald-700" />
                        )}
                        <span>{r.rung_title}</span>
                      </div>
                      <div className="mt-2 font-mono text-xl font-extrabold text-slate-900">
                        ${monthlyOrgCost.toLocaleString(undefined, { maximumFractionDigits: 0 })} / mo
                      </div>
                      <div className="mt-1 font-mono text-[11px] text-slate-600">
                        Per Dev / Day: {(dailyTokPerDev / 1_000_000).toFixed(2)}M tokens
                      </div>
                      <div className="mt-0.5 font-mono text-[11px] font-bold text-violet-800">
                        Portfolio CpO: {cpo1k > 0 ? `$${cpo1k.toFixed(2)} / 1k verified` : 'Unverified (∞)'}
                      </div>
                    </div>
                  )
                })}
              </div>
            </section>
          )}
        </>
      )}

      {/* 3-Tab Swarm & Sandbox Inspector Modal */}
      <NativeModal
        open={inspectorOpen}
        onClose={() => setInspectorOpen(false)}
        title="Category 6 Swarm & PR Sandbox Inspector"
        subtitle="Inspect Context-Isolated Orchestrator Code, Target Buggy Sources & Deterministic 10-Check Suite"
        maxWidthClass="max-w-3xl"
      >
        <div className="space-y-4">
          <div
            role="tablist"
            aria-label="Category 6 inspector sections"
            onKeyDown={handleInspectorTabKeyDown}
            className="mwg-tablist border-b border-slate-200"
          >
            {(
              [
                ['code', 'Swarm Orchestrator & CpO Python'],
                ['buggy', 'Buggy Microservice Source'],
                ['sandbox', 'Pytest + Adversarial + AST Suite'],
              ] as const
            ).map(([tid, label]) => (
              <button
                key={tid}
                type="button"
                role="tab"
                id={`cat6-insp-tab-${tid}`}
                aria-selected={inspectorTab === tid}
                tabIndex={inspectorTab === tid ? 0 : -1}
                onClick={() => setInspectorTab(tid)}
                className={`mwg-tab px-4 py-2 text-xs font-bold ${
                  inspectorTab === tid ? 'text-violet-800' : 'text-slate-500 hover:text-slate-900'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div
            role="tabpanel"
            aria-labelledby="cat6-insp-tab-code"
            tabIndex={inspectorTab === 'code' ? 0 : undefined}
            hidden={inspectorTab !== 'code'}
          >
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

          <div
            role="tabpanel"
            aria-labelledby="cat6-insp-tab-buggy"
            tabIndex={inspectorTab === 'buggy' ? 0 : undefined}
            hidden={inspectorTab !== 'buggy'}
          >
            <pre className="max-h-96 overflow-auto rounded-xl bg-slate-950 p-3.5 font-mono text-[11px] leading-relaxed text-amber-200">
              {selectedPreset?.buggy_code ?? ''}
            </pre>
          </div>

          <div
            role="tabpanel"
            aria-labelledby="cat6-insp-tab-sandbox"
            tabIndex={inspectorTab === 'sandbox' ? 0 : undefined}
            hidden={inspectorTab !== 'sandbox'}
          >
            <pre className="max-h-96 overflow-auto rounded-xl bg-slate-950 p-3.5 font-mono text-[11px] leading-relaxed text-emerald-200">
              {presetsData.sandbox_suite_source}
            </pre>
          </div>
        </div>
      </NativeModal>
    </div>
  )
}
