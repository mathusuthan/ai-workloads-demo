import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Code2,
  Cpu,
  Database,
  DollarSign,
  GitBranch,
  Play,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  TrendingDown,
  XCircle,
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
import { runCat5Arena } from '../api'
import type {
  ArchetypeSpec,
  Cat5PresetsResponse,
  Cat5RungId,
  Cat5RungResult,
  Cat5RunResponse,
  CreditShieldCredentials,
} from '../types'
import { Cat5AblationPanel } from './Cat5AblationPanel'
import { NativeModal } from './NativeModal'

interface Cat5WorkbenchProps {
  archetype: ArchetypeSpec
  presetsData: Cat5PresetsResponse
  creds: CreditShieldCredentials
  onRefreshSystemStatus: () => void
}

const CAT5_RUNGS: Cat5RungId[] = [
  'unbounded_sonnet_loop',
  'bounded_sonnet_cached_gate',
  'hybrid_haiku_sonnet_governed',
  'unbounded_haiku_loop',
]

const CAT5_RUNG_TAB: Record<Cat5RungId, string> = {
  unbounded_sonnet_loop: 'Rung 1: Raw Tables',
  bounded_sonnet_cached_gate: 'Rung 2: Narrow + Gate',
  hybrid_haiku_sonnet_governed: 'Rung 3: Haiku + Gate',
  unbounded_haiku_loop: 'Rung 4: Raw Tables (Haiku)',
}

const CAT5_PENDING_TITLE: Record<Cat5RungId, string> = {
  unbounded_sonnet_loop: '1. Free-Choice Raw-Table Loop (Sonnet 5.5)',
  bounded_sonnet_cached_gate: '2. Narrow Query + Cached Policy + Policy Gate',
  hybrid_haiku_sonnet_governed: '3. Haiku + Policy Gate + Sonnet Escalation',
  unbounded_haiku_loop: '4. Free-Choice Raw-Table Loop (Haiku 5.5)',
}

const VOLUME_STEPS = [
  { label: '1k / mo (Pilot Queue)', value: 1_000 },
  { label: '10k / mo (Regional AP)', value: 10_000 },
  { label: '50k / mo (NovaMart Steady)', value: 50_000 },
  { label: '100k / mo (Festive Peak)', value: 100_000 },
  { label: '250k / mo (Enterprise Scale)', value: 250_000 },
]

type CacheEntryMode = 'cold_first_invoice' | 'warm_shared_sop'

function formatInr(amount: number): string {
  return `INR ${amount.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
}

export function Cat5Workbench({
  archetype,
  presetsData,
  creds,
  onRefreshSystemStatus,
}: Cat5WorkbenchProps) {
  const [selectedPresetId, setSelectedPresetId] = useState<string>(
    presetsData.presets[0]?.id ?? 'inv-01'
  )
  const [cacheMode, setCacheMode] = useState<CacheEntryMode>('cold_first_invoice')
  const [loadingArena, setLoadingArena] = useState(false)
  const [arenaError, setArenaError] = useState<string | null>(null)
  const [runResponse, setRunResponse] = useState<Cat5RunResponse | null>(null)

  const [activeRungView, setActiveRungView] = useState<Cat5RungId>(
    'hybrid_haiku_sonnet_governed'
  )
  const [monthlyInvoices, setMonthlyInvoices] = useState<number>(50_000)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [inspectorTab, setInspectorTab] = useState<'code' | 'ddl' | 'sop'>('code')

  const executeArena = async (presetIdToRun: string) => {
    setLoadingArena(true)
    setArenaError(null)
    try {
      const data = await runCat5Arena(
        {
          preset_id: presetIdToRun,
          use_case: 'invoice_3way_reconciliation',
          rungs: CAT5_RUNGS,
          mode: creds.mode,
        },
        creds
      )
      setRunResponse(data)
      onRefreshSystemStatus()
    } catch (err) {
      setArenaError(err instanceof Error ? err.message : 'Failed to run Category 5 agent loop.')
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
    void executeArena(presetId)
  }

  const activeRungObj: Cat5RungResult | null = useMemo(() => {
    if (!runResponse) return null
    return (
      runResponse.results.find((r) => r.rung_id === activeRungView) ??
      runResponse.results[0] ??
      null
    )
  }, [runResponse, activeRungView])

  const naiveRes = useMemo(
    () => runResponse?.results.find((r) => r.rung_id === 'unbounded_sonnet_loop') ?? null,
    [runResponse]
  )
  const boundedRes = useMemo(
    () => runResponse?.results.find((r) => r.rung_id === 'bounded_sonnet_cached_gate') ?? null,
    [runResponse]
  )
  const hybridRes = useMemo(
    () => runResponse?.results.find((r) => r.rung_id === 'hybrid_haiku_sonnet_governed') ?? null,
    [runResponse]
  )
  const naiveHaikuRes = useMemo(
    () => runResponse?.results.find((r) => r.rung_id === 'unbounded_haiku_loop') ?? null,
    [runResponse]
  )
  const availableRungs = useMemo(
    () => CAT5_RUNGS.filter((rid) => runResponse?.results.some((r) => r.rung_id === rid)),
    [runResponse]
  )

  // Step-by-step cumulative cost curve ($ / 1k invoices)
  const stepCurveData = useMemo(() => {
    if (!runResponse) return []
    const maxSteps = Math.max(...runResponse.results.map((r) => r.steps.length), 1)
    const getStepCum = (res: Cat5RungResult | null, stepNum: number): number | null => {
      if (!res || res.steps.length === 0) return null
      const match = res.steps.find((s) => s.step_number === stepNum)
      const val = match
        ? cacheMode === 'warm_shared_sop'
          ? match.cumulative_warm_cost_usd
          : match.cumulative_cold_cost_usd
        : cacheMode === 'warm_shared_sop'
          ? res.warm_run_cost_usd
          : res.cold_run_cost_usd
      return Number((val * 1000).toFixed(2))
    }

    const rows = []
    for (let s = 1; s <= maxSteps; s += 1) {
      rows.push({
        step: `Step ${s}`,
        naive1k: getStepCum(naiveRes, s),
        bounded1k: getStepCum(boundedRes, s),
        hybrid1k: getStepCum(hybridRes, s),
        naiveHaiku1k: getStepCum(naiveHaikuRes, s),
      })
    }
    return rows
  }, [runResponse, naiveRes, boundedRes, hybridRes, naiveHaikuRes, cacheMode])

  // Token consumption bar chart across rungs
  const tokenBarData = useMemo(() => {
    if (!runResponse) return []
    return runResponse.results
      .filter((r) => r.status === 'ok')
      .map((r) => ({
        name:
          r.rung_id === 'unbounded_sonnet_loop'
            ? '1. Raw tables'
            : r.rung_id === 'bounded_sonnet_cached_gate'
              ? '2. Narrow + gate'
              : r.rung_id === 'hybrid_haiku_sonnet_governed'
                ? '3. Haiku + gate'
                : '4. Raw tables (Haiku)',
        'Uncached Input': r.total_uncached_input_tokens,
        'Cache W + R': r.total_cache_creation_tokens + r.total_cache_read_tokens,
        'Tool/Plan Out': r.total_output_tokens,
      }))
  }, [runResponse])

  const handleInspectorTabKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const order: ('code' | 'ddl' | 'sop')[] = ['code', 'ddl', 'sop']
    const idx = order.indexOf(inspectorTab)
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      setInspectorTab(order[(idx + 1) % order.length])
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      setInspectorTab(order[(idx - 1 + order.length) % order.length])
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

        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-lg bg-slate-100 px-2.5 py-1 font-mono text-[11px] font-semibold text-slate-700">
            Live SQLite ERP · 8 Tables · ~{presetsData.approx_policy_tokens.toLocaleString()} tok SOP Manual
          </span>
          <button
            type="button"
            onClick={() => setInspectorOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 shadow-2xs transition hover:bg-slate-50"
          >
            <Code2 className="h-3.5 w-3.5 text-teal-700" />
            Architecture &amp; SQLite Schema Inspector
          </button>
        </div>
      </div>

      {/* Header & Invoice Selector */}
      <section className="overflow-hidden rounded-2xl border border-teal-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 bg-teal-700 px-6 py-2.5 text-white">
          <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider">
            <span>
              {archetype.category_label} · {archetype.autonomy_tier_label}
            </span>
            <span className="rounded bg-white/20 px-2 py-0.5 font-mono text-[11px]">
              {archetype.token_band}
            </span>
          </div>
          <span className="font-mono text-xs font-bold text-teal-100">
            {archetype.dynamics}
          </span>
        </div>

        <div className="space-y-4 px-6 py-5">
          <div>
            <h1 className="text-xl font-extrabold tracking-tight text-slate-900 sm:text-2xl">
              {archetype.title} — {archetype.novamart_product_name}
            </h1>
            <p className="mt-1 max-w-4xl text-xs leading-relaxed text-slate-600 sm:text-sm">
              Compare a <strong>free-choice loop over raw ERP tables</strong> on Sonnet 5.5 (rung 1) with{' '}
              <strong>one narrow query + a cached policy manual + a deterministic policy gate</strong> (rung 2), and the{' '}
              <strong>same on Haiku 5.5, switching to Sonnet when the gate flags the invoice</strong> (rung 3), reconciling
              Purchase Orders, Goods Receipts, GSTR-2B / MSMED 45-day rules and Contract Amendments in live SQLite. The
              experiment panel below separates what each change contributed.
            </p>
          </div>

          <div className="grid gap-3 lg:grid-cols-3">
            {presetsData.presets.map((p) => {
              const active = p.id === selectedPresetId
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => handleSelectPreset(p.id)}
                  className={`rounded-xl border p-4 text-left transition ${
                    active
                      ? 'border-teal-700 bg-teal-50/80 ring-1 ring-teal-700'
                      : 'border-slate-200 bg-slate-50/60 hover:border-slate-300 hover:bg-white'
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-1.5">
                    <span className="font-mono text-[10px] font-bold uppercase text-teal-800">
                      {p.invoice_id} · {p.fc_hub}
                    </span>
                    <span
                      className={`rounded px-2 py-0.5 font-mono text-[10px] font-bold ${
                        p.complexity_tier === 'hard_circuit_breaker'
                          ? 'bg-rose-100 text-rose-800'
                          : p.complexity_tier === 'multi_factor_dispute'
                            ? 'bg-amber-100 text-amber-900'
                            : 'bg-emerald-100 text-emerald-900'
                      }`}
                    >
                      {p.complexity_tier === 'hard_circuit_breaker'
                        ? 'Hard Block'
                        : p.complexity_tier === 'multi_factor_dispute'
                          ? 'Multi-Factor Dispute'
                          : 'Routine'}
                    </span>
                  </div>
                  <div className="mt-1.5 text-xs font-extrabold text-slate-900">{p.title}</div>
                  <div className="mt-1 text-[11px] leading-snug text-slate-600">{p.subtitle}</div>
                  <div className="mt-2 font-mono text-[10px] font-bold text-slate-700">
                    Claimed Total: {formatInr(p.invoice_grand_total_inr)}
                  </div>
                </button>
              )
            })}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3.5">
            <div className="inline-flex rounded-xl border border-slate-300 bg-white p-1 text-xs">
              <button
                type="button"
                onClick={() => setCacheMode('cold_first_invoice')}
                className={`rounded-lg px-3 py-1.5 font-bold transition ${
                  cacheMode === 'cold_first_invoice'
                    ? 'bg-teal-700 text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Cold Worker Write ($2.50/$0.125M)
              </button>
              <button
                type="button"
                onClick={() => setCacheMode('warm_shared_sop')}
                className={`rounded-lg px-3 py-1.5 font-bold transition ${
                  cacheMode === 'warm_shared_sop'
                    ? 'bg-teal-700 text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Warm AP Worker Queue ($0.10/$0.01M)
              </button>
            </div>

            <button
              type="button"
              disabled={loadingArena}
              onClick={() => void executeArena(selectedPresetId)}
              className="inline-flex items-center gap-2 rounded-xl bg-teal-700 px-4 py-2 text-xs font-extrabold text-white shadow-sm transition hover:bg-teal-800 disabled:opacity-50"
            >
              {creds.mode === 'live' ? (
                <Zap className="h-4 w-4 text-amber-300" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              <span>
                {loadingArena
                  ? 'Executing SQLite Loops...'
                  : creds.mode === 'live'
                    ? 'Run Live 3-Rung SQLite Agent'
                    : 'Replay Verified ERP Agent Loop'}
              </span>
            </button>
          </div>
        </div>
      </section>

      {arenaError && (
        <div className="flex items-start gap-2 rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-xs text-rose-900">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />
          <span>{arenaError}</span>
        </div>
      )}

      {runResponse && (
        <>
          <div className="rounded-xl border border-teal-200 bg-teal-50 px-4 py-3 text-xs font-semibold text-teal-950">
            {runResponse.orchestration_callout}
          </div>

          {/* Rung cards (rungs 1-4) with native <progress> step-budget bars */}
          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {runResponse.results.map((res) => {
              const isHaikuRaw = res.rung_id === 'unbounded_haiku_loop'
              const isNaive = res.rung_id === 'unbounded_sonnet_loop' || isHaikuRaw
              const isBounded = res.rung_id === 'bounded_sonnet_cached_gate'
              const isHybrid = res.rung_id === 'hybrid_haiku_sonnet_governed'

              const borderTheme = isHaikuRaw
                ? 'border-amber-300'
                : isNaive
                  ? 'border-rose-300'
                  : isBounded
                    ? 'border-blue-300'
                    : 'border-teal-400 ring-1 ring-teal-200'
              const headerBg = isHaikuRaw
                ? 'bg-amber-50'
                : isNaive
                  ? 'bg-rose-50'
                  : isBounded
                    ? 'bg-blue-50/80'
                    : 'bg-teal-50/90'
              const badgeBg = isHaikuRaw
                ? 'bg-amber-600 text-white'
                : isNaive
                  ? 'bg-rose-600 text-white'
                  : isBounded
                    ? 'bg-blue-600 text-white'
                    : 'bg-teal-700 text-white'

              const cost1k =
                cacheMode === 'warm_shared_sop'
                  ? res.cost_per_1k_invoices_warm_usd
                  : res.cost_per_1k_invoices_cold_usd
              const savingsPct =
                cacheMode === 'warm_shared_sop'
                  ? res.savings_vs_naive_warm_pct
                  : res.savings_vs_naive_cold_pct

              const totalPromptTok =
                res.total_uncached_input_tokens +
                res.total_cache_creation_tokens +
                res.total_cache_read_tokens
              const fillColor = isHaikuRaw ? '#d97706' : isNaive ? '#e11d48' : isBounded ? '#2563eb' : '#0f766e'
              const ev = res.evaluation

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
                        <span className="font-mono text-[11px] font-bold text-slate-700">
                          {res.steps_used} / {res.max_step_budget} steps
                        </span>
                      </div>
                      <h2 className="mt-2 text-sm font-extrabold text-slate-900">{res.rung_title}</h2>
                      <div className="mt-0.5 font-mono text-[11px] text-slate-600">
                        {isHybrid
                          ? `Haiku steps: ${res.haiku_steps} · Sonnet steps: ${res.sonnet_steps}${
                              res.escalated_to_sonnet ? ' (escalated)' : ' (no escalation)'
                            }`
                          : `Anthropic · ${res.primary_model_id}`}
                      </div>
                    </div>

                    <div className="space-y-3 p-4">
                      {/* Cost Metric */}
                      <div className="flex items-baseline justify-between gap-2">
                        <div>
                          <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                            Cost / 1,000 Invoices ({cacheMode === 'warm_shared_sop' ? 'Warm' : 'Cold'})
                          </div>
                          <div className="font-mono text-2xl font-extrabold text-slate-900">
                            ${cost1k.toFixed(2)}
                          </div>
                        </div>
                        {res.rung_id !== 'unbounded_sonnet_loop' && savingsPct > 0 && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-1 font-mono text-xs font-extrabold text-emerald-800">
                            <TrendingDown className="h-3.5 w-3.5" />-{savingsPct.toFixed(1)}%
                          </span>
                        )}
                      </div>

                      {/* Native <progress> Loop Step Budget Meter */}
                      <div className="space-y-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                        <div className="flex items-center justify-between text-[11px]">
                          <label
                            htmlFor={`cat5-budget-${res.rung_id}`}
                            className="font-bold text-slate-700"
                          >
                            {isNaive ? 'Turns Used (Safety Cap)' : 'Turns Used (Step Budget)'}
                          </label>
                          <span className="font-mono font-bold text-slate-800">
                            {res.steps_used} of {res.max_step_budget} turns
                          </span>
                        </div>
                        <progress
                          id={`cat5-budget-${res.rung_id}`}
                          max={res.max_step_budget}
                          value={Math.min(res.steps_used, res.max_step_budget)}
                          className="mwg-progress"
                          style={{ '--progress-bar-fill': fillColor } as React.CSSProperties}
                        />
                      </div>

                      {/* Token Grid */}
                      <div className="grid grid-cols-2 gap-2 rounded-xl bg-slate-50 p-2.5 font-mono text-[11px]">
                        <div>
                          <span className="block text-[10px] text-slate-500">TOTAL PROMPT</span>
                          <span className="font-bold text-slate-900">
                            {totalPromptTok.toLocaleString()} tok
                          </span>
                        </div>
                        <div>
                          <span className="block text-[10px] text-slate-500">CACHE W / R</span>
                          <span className="font-bold text-slate-900">
                            {res.total_cache_creation_tokens.toLocaleString()} /{' '}
                            {res.total_cache_read_tokens.toLocaleString()}
                          </span>
                        </div>
                        <div>
                          <span className="block text-[10px] text-slate-500">OUTPUT TOKENS</span>
                          <span className="font-bold text-slate-900">
                            {res.total_output_tokens.toLocaleString()} tok
                          </span>
                        </div>
                        <div>
                          <span className="block text-[10px] text-slate-500">GATE / LATENCY</span>
                          <span className="font-bold text-slate-900">
                            {ev?.gate_verified ? 'Verified' : 'Ungated'} · {(res.total_latency_ms / 1000).toFixed(1)}s
                          </span>
                        </div>
                      </div>

                      {/* Adjudication Accuracy / Evidence Recall / Tool Precision */}
                      {ev && (
                        <div className="flex flex-wrap gap-1.5 text-[11px]">
                          <span
                            className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 font-bold ${
                              ev.exact_match
                                ? 'bg-emerald-100 text-emerald-900'
                                : 'bg-rose-100 text-rose-800'
                            }`}
                          >
                            <CheckCircle2 className="h-3 w-3" />
                            Rupee Acc: {ev.matched_fields}/{ev.total_fields} ({ev.field_accuracy_pct}%)
                          </span>
                          <span
                            className={`rounded-md px-2 py-0.5 font-bold ${
                              ev.evidence_recall_pct >= 100
                                ? 'bg-blue-100 text-blue-900'
                                : 'bg-amber-100 text-amber-900'
                            }`}
                          >
                            Evidence Recall: {ev.evidence_recall_pct}%
                          </span>
                          <span
                            className={`rounded-md px-2 py-0.5 font-bold ${
                              ev.tool_precision_pct >= 90
                                ? 'bg-teal-100 text-teal-900'
                                : 'bg-rose-100 text-rose-800'
                            }`}
                          >
                            Tool Prec: {ev.tool_precision_pct}%
                          </span>
                        </div>
                      )}

                      <ul className="space-y-1.5 border-t border-slate-100 pt-2.5 text-[11px] leading-relaxed text-slate-600">
                        {res.architectural_notes.map((n, i) => (
                          <li key={i} className="flex gap-1.5">
                            <span className="font-bold text-slate-400">•</span>
                            <span>{n}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              )
            })}
            {(runResponse.pending_rungs ?? []).map((rid) => (
              <div
                key={rid}
                className="flex flex-col justify-center rounded-2xl border border-dashed border-amber-300 bg-amber-50/40 p-5 text-xs text-slate-600 shadow-sm"
              >
                <span className="w-fit rounded-md bg-amber-100 px-2 py-0.5 text-[10px] font-extrabold uppercase text-amber-800">
                  Run pending
                </span>
                <h2 className="mt-2 text-sm font-extrabold text-slate-900">{CAT5_PENDING_TITLE[rid]}</h2>
                <p className="mt-1 leading-relaxed">
                  No recorded run to replay yet. The first rung's raw-table loop on Haiku 5.5: no cache and no policy
                  tool, so there is no escalation path to Sonnet. Run it live to see this invoice.
                </p>
              </div>
            ))}
          </section>

          {/* Charts: Step-by-Step Cumulative Spend + Token Breakdown */}
          <section className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="text-sm font-extrabold text-slate-900">
                Cumulative Loop Cost by Step ($ / 1,000 Invoices)
              </h2>
              <p className="mb-3 text-[11px] text-slate-500">
                Running cost after each model turn on this invoice; each uncached turn resends the whole conversation
              </p>
              <div className="h-72 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={stepCurveData} margin={{ top: 10, right: 16, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="step" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
                    <Tooltip formatter={(val: number) => `$${val.toFixed(2)}`} />
                    <Legend wrapperStyle={{ fontSize: '11px' }} />
                    <Line
                      type="monotone"
                      dataKey="naive1k"
                      name="1. Raw tables, no cache"
                      stroke="#dc2626"
                      strokeWidth={2.5}
                      dot={{ r: 3 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="bounded1k"
                      name="2. Narrow query + cache + gate"
                      stroke="#2563eb"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="hybrid1k"
                      name="3. Haiku + gate + escalation"
                      stroke="#0f766e"
                      strokeWidth={2.5}
                      dot={{ r: 4 }}
                    />
                    {naiveHaikuRes && (
                      <Line
                        type="monotone"
                        dataKey="naiveHaiku1k"
                        name="4. Raw tables on Haiku, no cache"
                        stroke="#d97706"
                        strokeWidth={2}
                        strokeDasharray="5 3"
                        dot={{ r: 3 }}
                      />
                    )}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="text-sm font-extrabold text-slate-900">
                Total Loop Tokens by Architecture (Uncached In vs. Cached W+R vs. Output)
              </h2>
              <p className="mb-3 text-[11px] text-slate-500">
                Uncached input, cached prefix (written + read) and output tokens for this invoice
              </p>
              <div className="h-72 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={tokenBarData} margin={{ top: 10, right: 16, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Legend wrapperStyle={{ fontSize: '11px' }} />
                    <Bar dataKey="Uncached Input" stackId="a" fill="#f97316" />
                    <Bar dataKey="Cache W + R" stackId="a" fill="#14b8a6" />
                    <Bar dataKey="Tool/Plan Out" stackId="a" fill="#1e293b" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </section>

          {/* 3-Invoice Portfolio Evaluation Scorecard Table */}
          {runResponse.portfolio_scorecard.length > 0 && (
            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-sm font-extrabold text-slate-900">
                    Recorded Runs on the {runResponse.portfolio_scorecard[0]?.invoices_evaluated ?? 'Three'} Original Invoices (Voucher Checked Field by Field)
                  </h2>
                  <p className="text-[11px] text-slate-500">
                    {presetsData.presets.map((p) => p.title).join(' · ')}. One recorded run per rung and invoice; the
                    experiment panel below has repeated runs on more invoices.
                  </p>
                </div>
              </div>

              <div
                tabIndex={0}
                role="region"
                aria-labelledby="cat5-scorecard-caption"
                className="table-wrapper rounded-xl border border-slate-200"
              >
                <table
                  className="mwg-table min-w-full divide-y divide-slate-200 text-xs"
                  data-table="cat5-scorecard"
                >
                  <caption id="cat5-scorecard-caption" className="sr-only">
                    Voucher accuracy, evidence recall, tool precision and cost across the original invoices
                  </caption>
                  <thead className="bg-slate-100 text-[11px] font-bold uppercase tracking-wider text-slate-600">
                    <tr>
                      <th scope="col" className="px-3.5 py-2.5 text-left">Architecture Rung</th>
                      <th scope="col" className="px-3.5 py-2.5 text-right">Avg Steps / Prompt Tok</th>
                      <th scope="col" className="px-3.5 py-2.5 text-right">Rupee Accuracy</th>
                      <th scope="col" className="px-3.5 py-2.5 text-right">Ev. Recall / Tool Prec</th>
                      <th scope="col" className="px-3.5 py-2.5 text-right">Avg Cost / 1k (Cold / Warm)</th>
                      <th scope="col" className="px-3.5 py-2.5 text-right">Cold Savings vs R1</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 bg-white">
                    {runResponse.portfolio_scorecard.map((row) => (
                      <tr key={row.rung_id}>
                        <th scope="row" className="px-3.5 py-2.5 text-left font-bold text-slate-900">
                          <div>{row.label}</div>
                          <div className="font-mono text-[10px] font-normal text-slate-500">
                            {row.model_routing_summary}
                          </div>
                        </th>
                        <td className="px-3.5 py-2.5 text-right font-mono text-slate-700">
                          <div>{row.avg_steps} steps</div>
                          <div className="text-[10px] text-slate-500">
                            {row.avg_prompt_tokens.toLocaleString()} in · {row.avg_output_tokens.toLocaleString()} out
                          </div>
                        </td>
                        <td className="px-3.5 py-2.5 text-right font-mono font-bold text-emerald-800">
                          {row.fields_matched}/{row.fields_total} ({row.adjudication_accuracy_pct}%)
                          <div className="text-[10px] font-normal text-slate-500">
                            {row.exact_vouchers_matched}/{row.invoices_evaluated} exact vouchers
                          </div>
                        </td>
                        <td className="px-3.5 py-2.5 text-right font-mono text-slate-800">
                          <div>Recall: {row.avg_evidence_recall_pct}%</div>
                          <div className="text-[10px] text-slate-500">Tool Prec: {row.avg_tool_precision_pct}%</div>
                        </td>
                        <td className="px-3.5 py-2.5 text-right font-mono font-bold text-slate-900">
                          ${row.avg_cost_per_1k_cold_usd.toFixed(2)} / ${row.avg_cost_per_1k_warm_usd.toFixed(2)}
                        </td>
                        <td className="px-3.5 py-2.5 text-right font-mono font-extrabold text-teal-700">
                          {row.rung_id === 'unbounded_sonnet_loop'
                            ? 'Baseline'
                            : `-${row.savings_vs_naive_cold_pct.toFixed(1)}%`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <Cat5AblationPanel
            portfolio={runResponse.ablation_portfolio}
            invoiceNumbers={Object.fromEntries(presetsData.presets.map((p) => [p.id, p.invoice_id]))}
          />

          {/* Interactive Agent Loop Trajectory & SQLite Voucher Ledger Inspector */}
          {activeRungObj && (
            <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-slate-950 px-5 py-4 text-white">
                <div>
                  <div className="text-[11px] font-bold uppercase tracking-wider text-teal-300">
                    Interactive SQLite Agent Execution Trajectory &amp; Committed Voucher Ledger
                  </div>
                  <h2 className="text-base font-extrabold">
                    Inspect each model turn, its tool calls and SQL, and any Haiku -&gt; Sonnet switch for{' '}
                    {runResponse.invoice_id}
                  </h2>
                </div>

                <div className="flex flex-wrap items-center gap-1.5">
                  {availableRungs.map((rid) => (
                    <button
                      key={rid}
                      type="button"
                      onClick={() => setActiveRungView(rid)}
                      className={`rounded-lg px-2.5 py-1.5 text-xs font-bold transition ${
                        activeRungView === rid
                          ? 'bg-teal-500 text-slate-950'
                          : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                      }`}
                    >
                      {CAT5_RUNG_TAB[rid]}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid gap-5 p-5 lg:grid-cols-12">
                {/* Left 7 cols: Ordered Timeline + Expandable SQL Inspector */}
                <div className="space-y-3 lg:col-span-7">
                  <div className="flex items-center justify-between text-xs font-extrabold text-slate-900">
                    <span className="inline-flex items-center gap-1.5">
                      <GitBranch className="h-4 w-4 text-teal-700" />
                      Step-by-Step Orchestration Loop ({activeRungObj.steps.length} Turns)
                    </span>
                    <span className="font-mono text-[11px] text-slate-500">
                      Click any SQL block below to expand raw DB rows
                    </span>
                  </div>

                  <ol role="list" className="mwg-accordion space-y-3">
                    {activeRungObj.steps.map((st, idx) => {
                      const isHaiku = st.model_id.includes('haiku')
                      return (
                        <li
                          key={st.step_number}
                          className={`rounded-xl border p-3.5 ${
                            st.escalated_from_haiku
                              ? 'border-amber-300 bg-amber-50/40'
                              : 'border-slate-200 bg-slate-50/60'
                          }`}
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="rounded bg-slate-900 px-2 py-0.5 font-mono text-[10px] font-bold text-white">
                                Step {st.step_number}
                              </span>
                              <span
                                className={`rounded px-2 py-0.5 font-mono text-[10px] font-extrabold ${
                                  isHaiku
                                    ? 'bg-emerald-100 text-emerald-900'
                                    : 'bg-blue-100 text-blue-900'
                                }`}
                              >
                                {st.model_id}
                              </span>
                              {st.escalated_from_haiku && (
                                <span className="rounded bg-amber-200 px-2 py-0.5 font-mono text-[10px] font-extrabold text-amber-950">
                                  ESCALATED FROM HAIKU
                                </span>
                              )}
                              <span
                                className={`rounded px-2 py-0.5 font-mono text-[10px] font-bold ${
                                  st.stop_reason === 'max_tokens'
                                    ? 'bg-rose-100 text-rose-800'
                                    : 'bg-slate-200 text-slate-700'
                                }`}
                                title="stop_reason returned by the API for this turn"
                              >
                                stop: {st.stop_reason}
                              </span>
                            </div>
                            <span className="font-mono text-[10px] font-semibold text-slate-600">
                              {st.finops.input_tokens.toLocaleString()} in · {st.finops.cache_read_tokens.toLocaleString()} cr ·{' '}
                              {st.finops.output_tokens.toLocaleString()} out · $
                              {((cacheMode === 'warm_shared_sop'
                                ? st.cumulative_warm_cost_usd
                                : st.cumulative_cold_cost_usd) * 1000).toFixed(2)}/1k cum
                            </span>
                          </div>

                          {st.assistant_thought && (
                            <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-slate-700">
                              {st.assistant_thought}
                            </p>
                          )}

                          {st.tool_calls.map((tc, tIdx) => (
                            <div key={tc.tool_use_id} className="mt-2.5 space-y-2">
                              <div className="flex flex-wrap items-center gap-1.5 font-mono text-[11px]">
                                <Terminal className="h-3.5 w-3.5 text-teal-700" />
                                <span className="font-bold text-slate-900">{tc.tool_name}</span>
                                <span
                                  className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                                    tc.is_optimal_call
                                      ? 'bg-teal-100 text-teal-900'
                                      : 'bg-rose-100 text-rose-800'
                                  }`}
                                >
                                  {tc.is_optimal_call ? 'Narrow / gate tool' : 'Raw SELECT *'}
                                </span>
                                {tc.gate_snapshot && Boolean(tc.gate_snapshot.circuit_breaker_halt) && (
                                  <span className="rounded bg-rose-600 px-1.5 py-0.5 text-[10px] font-bold text-white">
                                    CIRCUIT-BREAKER HALT
                                  </span>
                                )}
                              </div>

                              <details
                                name="cat5-sql-step"
                                open={idx === 0 && tIdx === 0}
                                className="overflow-hidden rounded-lg border border-slate-200 bg-white"
                              >
                                <summary className="bg-slate-100/80 px-3 py-1.5 font-mono text-[11px] font-bold text-slate-700">
                                  <span>SQL Executed &amp; ERP Tool Output ({tc.tables_touched.join(', ') || 'gate'})</span>
                                </summary>
                                <div className="space-y-2 border-t border-slate-100 p-2.5">
                                  <pre className="overflow-x-auto rounded bg-slate-950 p-2 font-mono text-[10px] text-teal-300">
                                    {tc.sql_executed}
                                  </pre>
                                  <pre className="max-h-44 overflow-y-auto whitespace-pre-wrap rounded bg-slate-50 p-2 font-mono text-[10px] text-slate-800">
                                    {tc.result_preview}
                                  </pre>
                                </div>
                              </details>
                            </div>
                          ))}

                          {(st.tool_calls_not_executed?.length ?? 0) > 0 && (
                            <p className="mt-2 rounded bg-rose-50 px-2 py-1 font-mono text-[10px] text-rose-800 ring-1 ring-rose-200">
                              Turn cut off at the output limit: {st.tool_calls_not_executed?.length} tool call
                              {st.tool_calls_not_executed?.length === 1 ? '' : 's'} recorded but not executed (
                              {st.tool_calls_not_executed?.map((c) => String(c.name ?? '?')).join(', ')})
                            </p>
                          )}
                        </li>
                      )
                    })}
                  </ol>
                </div>

                {/* Right 5 cols: Committed SQLite Voucher vs Ground Truth Verification */}
                <div className="space-y-4 lg:col-span-5">
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                    <div className="flex items-center justify-between gap-2">
                      <span className="inline-flex items-center gap-1.5 text-xs font-extrabold text-slate-900">
                        {activeRungObj.circuit_breaker_triggered ? (
                          <ShieldAlert className="h-4 w-4 text-rose-600" />
                        ) : (
                          <ShieldCheck className="h-4 w-4 text-teal-700" />
                        )}
                        SQLite `reconciliation_vouchers` Committed Row
                      </span>
                      {activeRungObj.committed_voucher && (
                        <span className="rounded bg-slate-900 px-2 py-0.5 font-mono text-[10px] font-bold text-white">
                          {activeRungObj.committed_voucher.voucher_id}
                        </span>
                      )}
                    </div>

                    {activeRungObj.committed_voucher ? (
                      <div className="mt-3 space-y-2.5">
                        <div className="rounded-lg border border-slate-200 bg-white p-3">
                          <div className="text-[10px] font-bold uppercase text-slate-500">Decision</div>
                          <div className="mt-0.5 font-mono text-sm font-extrabold text-slate-900">
                            {activeRungObj.committed_voucher.decision}
                          </div>
                        </div>

                        <div className="grid grid-cols-2 gap-2 font-mono text-xs">
                          <div className="rounded-lg border border-slate-200 bg-white p-2.5">
                            <div className="text-[10px] text-slate-500">NET PRINCIPAL (T+43)</div>
                            <div className="mt-0.5 font-bold text-slate-900">
                              {formatInr(activeRungObj.committed_voucher.authorized_net_principal_inr)}
                            </div>
                          </div>
                          <div className="rounded-lg border border-slate-200 bg-white p-2.5">
                            <div className="text-[10px] text-slate-500">GST PAYOUT RELEASED</div>
                            <div className="mt-0.5 font-bold text-slate-900">
                              {formatInr(activeRungObj.committed_voucher.authorized_gst_payout_inr)}
                            </div>
                          </div>
                          <div className="rounded-lg border border-slate-200 bg-white p-2.5">
                            <div className="text-[10px] text-slate-500">GSTR-2B ESCROW HOLD</div>
                            <div className="mt-0.5 font-bold text-amber-800">
                              {formatInr(activeRungObj.committed_voucher.gst_escrow_holdback_inr)}
                            </div>
                          </div>
                          <div className="rounded-lg border border-slate-200 bg-white p-2.5">
                            <div className="text-[10px] text-slate-500">DEBIT NOTE DEDUCTED</div>
                            <div className="mt-0.5 font-bold text-rose-700">
                              {formatInr(activeRungObj.committed_voucher.debit_note_deduction_inr)}
                            </div>
                          </div>
                        </div>

                        <div className="rounded-lg border border-slate-200 bg-white p-3 text-[11px] leading-relaxed text-slate-700">
                          <span className="font-bold text-slate-900">Voucher Audit Memo: </span>
                          {activeRungObj.committed_voucher.audit_summary}
                        </div>
                      </div>
                    ) : (
                      <p className="mt-2 text-xs text-rose-700">No voucher committed in SQLite.</p>
                    )}
                  </div>

                  {/* Field-by-Field Ground-Truth Verification */}
                  {activeRungObj.evaluation && (
                    <div className="rounded-xl border border-slate-200 bg-white p-4">
                      <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">
                        Ground-Truth Verification ({activeRungObj.evaluation.matched_fields}/
                        {activeRungObj.evaluation.total_fields} Passed)
                      </h3>
                      <div className="mt-2.5 space-y-1.5">
                        {activeRungObj.evaluation.field_checks.map((fc) => (
                          <div
                            key={fc.field}
                            className="flex items-center justify-between gap-2 rounded-lg border border-slate-100 bg-slate-50/70 px-3 py-1.5 font-mono text-[11px]"
                          >
                            <span className="font-semibold text-slate-700">{fc.field}</span>
                            <span
                              className={`inline-flex items-center gap-1 font-bold ${
                                fc.matched ? 'text-emerald-700' : 'text-rose-700'
                              }`}
                            >
                              {fc.matched ? (
                                <CheckCircle2 className="h-3.5 w-3.5" />
                              ) : (
                                <XCircle className="h-3.5 w-3.5" />
                              )}
                              {typeof fc.actual === 'number'
                                ? formatInr(fc.actual)
                                : String(fc.actual ?? '—')}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Final Agent Controller Readout */}
                  {activeRungObj.final_readout && (
                    <div className="rounded-xl border border-teal-200 bg-teal-50/50 p-4">
                      <h3 className="text-xs font-extrabold uppercase tracking-wider text-teal-900">
                        Final Controller Readout
                      </h3>
                      <p className="mt-1.5 whitespace-pre-wrap text-xs leading-relaxed text-slate-800">
                        {activeRungObj.final_readout}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </section>
          )}

          {/* CFO Autonomous AP Volume Simulator */}
          {naiveRes && boundedRes && hybridRes && (
            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <DollarSign className="h-4 w-4 text-teal-700" />
                  <div>
                    <h2 className="text-sm font-extrabold text-slate-900">
                      CFO Autonomous AP Volume Simulator ({monthlyInvoices.toLocaleString()} Invoices / Month)
                    </h2>
                    <p className="text-[11px] text-slate-500">
                      This invoice's measured cost per run, multiplied out to a monthly and annual volume
                    </p>
                  </div>
                </div>
              </div>

              <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-bold text-slate-700">
                  <label htmlFor="cat5-volume-slider">Monthly Invoices Reconciled</label>
                  <div className="flex flex-wrap gap-1.5">
                    {VOLUME_STEPS.map((st) => (
                      <button
                        key={st.value}
                        type="button"
                        onClick={() => setMonthlyInvoices(st.value)}
                        className={`rounded-lg px-2.5 py-1 font-mono text-[11px] font-bold transition ${
                          monthlyInvoices === st.value
                            ? 'bg-teal-700 text-white'
                            : 'bg-white text-slate-600 ring-1 ring-slate-200 hover:text-slate-900'
                        }`}
                      >
                        {st.label}
                      </button>
                    ))}
                  </div>
                </div>
                <input
                  id="cat5-volume-slider"
                  type="range"
                  min={1_000}
                  max={250_000}
                  step={1_000}
                  value={monthlyInvoices}
                  onChange={(e) => setMonthlyInvoices(Number(e.target.value))}
                  className="mt-3 w-full accent-teal-700"
                />
              </div>

              <div className={`mt-4 grid gap-3 ${naiveHaikuRes ? 'md:grid-cols-4' : 'md:grid-cols-3'}`}>
                {[naiveRes, boundedRes, hybridRes, ...(naiveHaikuRes ? [naiveHaikuRes] : [])].map((r) => {
                  const perInv =
                    cacheMode === 'warm_shared_sop'
                      ? r.warm_run_cost_usd
                      : r.cold_run_cost_usd
                  const monthly = perInv * monthlyInvoices
                  const annual = monthly * 12
                  return (
                    <div key={r.rung_id} className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
                      <div className="flex items-center gap-1.5 text-xs font-extrabold text-slate-900">
                        {r.rung_id === 'unbounded_haiku_loop' ? (
                          <Database className="h-3.5 w-3.5 text-amber-600" />
                        ) : r.rung_id === 'unbounded_sonnet_loop' ? (
                          <Database className="h-3.5 w-3.5 text-rose-600" />
                        ) : r.rung_id === 'bounded_sonnet_cached_gate' ? (
                          <Cpu className="h-3.5 w-3.5 text-blue-600" />
                        ) : (
                          <ShieldCheck className="h-3.5 w-3.5 text-teal-700" />
                        )}
                        <span>{r.rung_title}</span>
                      </div>
                      <div className="mt-2 font-mono text-xl font-extrabold text-slate-900">
                        ${monthly.toLocaleString(undefined, { maximumFractionDigits: 0 })} / mo
                      </div>
                      <div className="mt-0.5 font-mono text-[11px] text-slate-500">
                        ${annual.toLocaleString(undefined, { maximumFractionDigits: 0 })} / yr annualized
                      </div>
                    </div>
                  )
                })}
              </div>
            </section>
          )}
        </>
      )}

      {/* Architecture & SQLite Schema Inspector Modal */}
      <NativeModal
        open={inspectorOpen}
        onClose={() => setInspectorOpen(false)}
        title="Category 5 Architecture & SQLite ERP Inspector"
        subtitle="Inspect Multi-Turn Tool Loops, SQLite 3-Way Match DDL Schema & AP Policy SOP Manual"
        maxWidthClass="max-w-3xl"
      >
        <div className="space-y-4">
          <div
            role="tablist"
            aria-label="Category 5 inspector sections"
            onKeyDown={handleInspectorTabKeyDown}
            className="mwg-tablist border-b border-slate-200"
          >
            {(
              [
                ['code', 'Python SDK Loop Comparison'],
                ['ddl', 'SQLite 8-Table ERP DDL'],
                ['sop', 'Cached AP SOP Manual'],
              ] as const
            ).map(([tid, label]) => (
              <button
                key={tid}
                type="button"
                role="tab"
                id={`cat5-insp-tab-${tid}`}
                aria-selected={inspectorTab === tid}
                tabIndex={inspectorTab === tid ? 0 : -1}
                onClick={() => setInspectorTab(tid)}
                className={`mwg-tab px-4 py-2 text-xs font-bold ${
                  inspectorTab === tid ? 'text-teal-700' : 'text-slate-500 hover:text-slate-900'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div role="tabpanel" aria-labelledby="cat5-insp-tab-code" hidden={inspectorTab !== 'code'}>
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

          <div role="tabpanel" aria-labelledby="cat5-insp-tab-ddl" hidden={inspectorTab !== 'ddl'}>
            <pre className="max-h-96 overflow-auto rounded-xl bg-slate-950 p-3.5 font-mono text-[11px] leading-relaxed text-teal-300">
              {presetsData.erp_ddl_schema}
            </pre>
          </div>

          <div role="tabpanel" aria-labelledby="cat5-insp-tab-sop" hidden={inspectorTab !== 'sop'}>
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-xl bg-slate-950 p-3.5 font-mono text-[11px] leading-relaxed text-slate-100">
              {presetsData.policy_manual_preview}
            </pre>
          </div>
        </div>
      </NativeModal>
    </div>
  )
}
