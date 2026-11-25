import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertCircle,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  Code2,
  Cpu,
  Database,
  DollarSign,
  FileText,
  Filter,
  Play,
  Quote,
  Search,
  Send,
  Sparkles,
  TrendingDown,
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
import { runCat4Arena, runCat4CustomQuery } from '../api'
import type {
  ArchetypeSpec,
  Cat4CitationSpan,
  Cat4PresetsResponse,
  Cat4QueryResult,
  Cat4RungId,
  Cat4RungSummary,
  Cat4RunResponse,
  CreditShieldCredentials,
} from '../types'
import { NativeModal } from './NativeModal'

interface Cat4WorkbenchProps {
  archetype: ArchetypeSpec
  presetsData: Cat4PresetsResponse
  creds: CreditShieldCredentials
  onRefreshSystemStatus: () => void
}

const CAT4_RUNGS: Cat4RungId[] = [
  'naive_full_corpus',
  'cached_full_corpus_citations',
  'hybrid_rag_rerank_citations',
]

const VOLUME_STEPS = [
  { label: '500 / mo (Boutique Legal)', value: 500 },
  { label: '5k / mo (NovaMart Vendor Desk)', value: 5_000 },
  { label: '25k / mo (Catalog + Compliance)', value: 25_000 },
  { label: '50k / mo (Peak Onboarding)', value: 50_000 },
  { label: '100k / mo (Marketplace Scale)', value: 100_000 },
]

type CacheEntryMode = 'cold_deal_room' | 'warm_shared_corpus'

function renderHighlightedDocument(
  fullText: string,
  highlight: { start: number; end: number } | null
) {
  if (
    !highlight ||
    highlight.start < 0 ||
    highlight.end <= highlight.start ||
    highlight.start >= fullText.length
  ) {
    return <span>{fullText}</span>
  }
  const safeEnd = Math.min(fullText.length, highlight.end)
  const before = fullText.slice(0, highlight.start)
  const target = fullText.slice(highlight.start, safeEnd)
  const after = fullText.slice(safeEnd)
  return (
    <>
      <span>{before}</span>
      <mark
        data-cat4-highlight="active"
        className="rounded bg-amber-200 px-0.5 font-semibold text-slate-950 ring-2 ring-amber-500"
      >
        {target}
      </mark>
      <span>{after}</span>
    </>
  )
}

export function Cat4Workbench({
  archetype,
  presetsData,
  creds,
  onRefreshSystemStatus,
}: Cat4WorkbenchProps) {
  const [selectedPresetId, setSelectedPresetId] = useState<string>(
    presetsData.presets[0]?.id ?? 'audit-01'
  )
  const [cacheMode, setCacheMode] = useState<CacheEntryMode>('cold_deal_room')
  const [loadingArena, setLoadingArena] = useState(false)
  const [arenaError, setArenaError] = useState<string | null>(null)
  const [runResponse, setRunResponse] = useState<Cat4RunResponse | null>(null)

  const [selectedQuestionIdx, setSelectedQuestionIdx] = useState<number>(0)
  const [activeRungView, setActiveRungView] = useState<Cat4RungId>(
    'hybrid_rag_rerank_citations'
  )
  const [openDocId, setOpenDocId] = useState<string>(
    presetsData.documents[0]?.doc_id ?? 'DOC-01'
  )
  const [activeCitation, setActiveCitation] = useState<Cat4CitationSpan | null>(null)

  const [adhocInput, setAdhocInput] = useState('')
  const [loadingAdhoc, setLoadingAdhoc] = useState(false)
  const [adhocError, setAdhocError] = useState<string | null>(null)
  const [adhocResult, setAdhocResult] = useState<Cat4RungSummary[] | null>(null)
  const [adhocQuestionAsked, setAdhocQuestionAsked] = useState<string | null>(null)

  const [monthlyAudits, setMonthlyAudits] = useState<number>(5_000)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [inspectorTab, setInspectorTab] = useState<'code' | 'schema'>('code')

  const docViewerRef = useRef<HTMLDivElement | null>(null)

  const selectedPreset = useMemo(
    () => presetsData.presets.find((p) => p.id === selectedPresetId) ?? presetsData.presets[0],
    [presetsData.presets, selectedPresetId]
  )

  const executeArena = async (presetIdToRun: string) => {
    setLoadingArena(true)
    setArenaError(null)
    setActiveCitation(null)
    setAdhocResult(null)
    setAdhocQuestionAsked(null)
    try {
      const data = await runCat4Arena(
        {
          preset_id: presetIdToRun,
          use_case: 'supplier_msa_due_diligence',
          rungs: CAT4_RUNGS,
          mode: creds.mode,
        },
        creds
      )
      setRunResponse(data)
      setSelectedQuestionIdx(0)
      onRefreshSystemStatus()
    } catch (err) {
      setArenaError(err instanceof Error ? err.message : 'Failed to execute Category 4 audit.')
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

  // Smoothly scroll highlighted <mark> inside source contract viewer when user clicks a citation badge
  useEffect(() => {
    if (!activeCitation || !docViewerRef.current) return
    const timer = window.setTimeout(() => {
      const mark = docViewerRef.current?.querySelector('mark[data-cat4-highlight="active"]')
      if (mark && typeof (mark as HTMLElement).scrollIntoView === 'function') {
        ;(mark as HTMLElement).scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    }, 60)
    return () => window.clearTimeout(timer)
  }, [activeCitation, openDocId])

  const naiveSummary = useMemo(
    () => runResponse?.results.find((r) => r.rung_id === 'naive_full_corpus'),
    [runResponse]
  )
  const cachedSummary = useMemo(
    () => runResponse?.results.find((r) => r.rung_id === 'cached_full_corpus_citations'),
    [runResponse]
  )
  const hybridSummary = useMemo(
    () => runResponse?.results.find((r) => r.rung_id === 'hybrid_rag_rerank_citations'),
    [runResponse]
  )

  // Query-count crossover chart (N = 1 .. 12 queries per Deal Room, $/1k Deal Rooms)
  const crossoverData = useMemo(() => {
    if (!naiveSummary || !cachedSummary || !hybridSummary) return []
    const nQueries = Math.max(1, naiveSummary.queries.length)
    const naiveAvg = naiveSummary.cold_audit_cost_usd / nQueries
    const cachedQ1Cold = cachedSummary.queries[0]?.cold_query_cost_usd ?? 0
    const cachedWarmTail =
      nQueries > 1
        ? cachedSummary.queries
            .slice(1)
            .reduce((acc, q) => acc + q.warm_query_cost_usd, 0) /
          (nQueries - 1)
        : cachedSummary.warm_audit_cost_usd / nQueries
    const cachedWarmAvg = cachedSummary.warm_audit_cost_usd / nQueries
    const hybridAvg = hybridSummary.cold_audit_cost_usd / nQueries

    const rows = []
    for (let n = 1; n <= 12; n += 1) {
      const coldR2 = cachedQ1Cold + Math.max(0, n - 1) * cachedWarmTail
      rows.push({
        label: `${n}Q`,
        queryCount: n,
        naive1k: Number((n * naiveAvg * 1000).toFixed(2)),
        cachedCold1k: Number((coldR2 * 1000).toFixed(2)),
        cachedWarm1k: Number((n * cachedWarmAvg * 1000).toFixed(2)),
        hybrid1k: Number((n * hybridAvg * 1000).toFixed(2)),
      })
    }
    return rows
  }, [naiveSummary, cachedSummary, hybridSummary])

  // Component cost breakdown bar chart ($ per 1,000 4-query Deal-Room audits)
  const componentBarData = useMemo(() => {
    if (!runResponse) return []
    return runResponse.results
      .filter((r) => r.status === 'ok')
      .map((r) => {
        const uncachedInCost = (r.total_uncached_input_tokens / 1_000_000) * 2.0 * 1000
        const rawWriteCost = (r.total_cache_creation_tokens / 1_000_000) * 2.5 * 1000
        const rawReadCost = (r.total_cache_read_tokens / 1_000_000) * 0.1 * 1000
        const totAudit1k =
          cacheMode === 'warm_shared_corpus'
            ? r.cost_per_1k_audits_warm_usd
            : r.cost_per_1k_audits_cold_usd
        const outCost1k = (r.total_output_tokens / 1_000_000) * 10.0 * 1000
        const rerankCost1k = r.reranker_cost_usd * 1000
        const normalizedPrefix = Math.max(0, totAudit1k - uncachedInCost - outCost1k - rerankCost1k)
        return {
          name:
            r.rung_id === 'naive_full_corpus'
              ? '1. Naive Stuffing'
              : r.rung_id === 'cached_full_corpus_citations'
                ? '2. Cached Full Corpus'
                : '3. Hybrid BM25 + Haiku',
          'Uncached Input': Number(uncachedInCost.toFixed(2)),
          'Prefix Cache W/R': Number(
            (r.rung_id === 'cached_full_corpus_citations'
              ? normalizedPrefix
              : rawWriteCost + rawReadCost
            ).toFixed(2)
          ),
          'Synthesis Output (5x)': Number(outCost1k.toFixed(2)),
          'Haiku Reranker': Number(rerankCost1k.toFixed(2)),
        }
      })
  }, [runResponse, cacheMode])

  const activeSourceSummaryList = adhocResult ?? runResponse?.results ?? []
  const activeRungObj =
    activeSourceSummaryList.find((r) => r.rung_id === activeRungView) ??
    activeSourceSummaryList[0] ??
    null
  const activeQueryResult: Cat4QueryResult | null = adhocResult
    ? activeRungObj?.queries[0] ?? null
    : activeRungObj?.queries[selectedQuestionIdx] ?? activeRungObj?.queries[0] ?? null

  const handleCitationClick = (cit: Cat4CitationSpan) => {
    setActiveCitation(cit)
    setOpenDocId(cit.doc_id)
  }

  const handleRunAdhocQuery = async () => {
    const q = adhocInput.trim()
    if (q.length < 8) return
    setLoadingAdhoc(true)
    setAdhocError(null)
    setActiveCitation(null)
    try {
      const resp = await runCat4CustomQuery(
        {
          preset_id: selectedPresetId,
          question: q,
          rungs: CAT4_RUNGS,
          mode: creds.mode,
        },
        creds
      )
      setAdhocResult(resp.results)
      setAdhocQuestionAsked(resp.question)
      setActiveRungView('hybrid_rag_rerank_citations')
      onRefreshSystemStatus()
    } catch (err) {
      setAdhocError(err instanceof Error ? err.message : 'Failed to run custom query.')
    } finally {
      setLoadingAdhoc(false)
    }
  }

  const handleInspectorTabKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const order: ('code' | 'schema')[] = ['code', 'schema']
    const idx = order.indexOf(inspectorTab)
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      setInspectorTab(order[(idx + 1) % order.length])
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      setInspectorTab(order[(idx - 1 + order.length) % order.length])
    }
  }

  const profile = presetsData.deal_room_profile as Record<string, unknown>

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
            {presetsData.total_docs} Agreements · {presetsData.total_chunks} Indexed Clauses ·{' '}
            {presetsData.approx_corpus_tokens.toLocaleString()} est. tokens
          </span>
          <button
            type="button"
            onClick={() => setInspectorOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 shadow-2xs transition hover:bg-slate-50"
          >
            <Code2 className="h-3.5 w-3.5 text-amber-600" />
            Architecture &amp; Code Inspector
          </button>
        </div>
      </div>

      {/* Category 4 Header Banner */}
      <section className="overflow-hidden rounded-2xl border border-amber-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 bg-amber-600 px-6 py-2.5 text-white">
          <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider">
            <span>
              {archetype.category_label} · {archetype.autonomy_tier_label}
            </span>
            <span className="rounded bg-white/20 px-2 py-0.5 font-mono text-[11px]">
              {archetype.token_band}
            </span>
          </div>
          <span className="font-mono text-xs font-bold text-amber-100">
            {archetype.dynamics}
          </span>
        </div>

        <div className="space-y-4 px-6 py-5">
          <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
            <div className="max-w-3xl">
              <h1 className="text-xl font-extrabold tracking-tight text-slate-900 sm:text-2xl">
                {archetype.title} — {archetype.novamart_product_name}
              </h1>
              <p className="mt-1 text-xs leading-relaxed text-slate-600 sm:text-sm">
                Compare <strong>Uncached Full-Corpus Stuffing</strong> vs.{' '}
                <strong>Anthropic DocumentBlock Prefix Caching + Native Citations</strong> vs.{' '}
                <strong>Hybrid BM25 + Haiku 5.5 Reranking + Native Citations</strong> over a 7-document,
                ~16k–21k-token Indian supplier deal room (Wholesale MSA, Diwali Peak SLA, DPDP Act 2023,
                BIS/EPR Hazmat, CGST Sec 16(2)(aa) / MSMED 45-Day Rider, MCA Form AOC-4 / CARO 2020 &amp; Side Letter #2).
              </p>
            </div>

            <div className="shrink-0 rounded-xl border border-amber-200 bg-amber-50/70 px-3.5 py-2.5 text-xs">
              <div className="font-mono text-[10px] font-bold uppercase tracking-wider text-amber-900">
                Active Deal Room · {String(profile.deal_room_id ?? 'DR-NM-DECCAN-2026-Q4')}
              </div>
              <div className="mt-0.5 font-extrabold text-slate-900">
                {String(profile.supplier_legal_name ?? '')}
              </div>
              <div className="mt-0.5 font-mono text-[10px] text-slate-600">
                CIN: {String(profile.cin ?? '')} · GSTIN: {String(profile.gstin ?? '')}
              </div>
            </div>
          </div>

          {/* Preset Audit Pack Selector + Controls */}
          <div className="grid gap-3 md:grid-cols-2">
            {presetsData.presets.map((p) => {
              const active = p.id === selectedPresetId
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => handleSelectPreset(p.id)}
                  className={`rounded-xl border p-4 text-left transition ${
                    active
                      ? 'border-amber-600 bg-amber-50/80 ring-1 ring-amber-600'
                      : 'border-slate-200 bg-slate-50/60 hover:border-slate-300 hover:bg-white'
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-mono text-[10px] font-bold uppercase text-amber-800">
                      {p.id} · {p.reviewer_role}
                    </span>
                    <span className="rounded bg-slate-200/80 px-2 py-0.5 font-mono text-[10px] font-bold text-slate-700">
                      {p.questions.length} Cross-Doc Questions
                    </span>
                  </div>
                  <div className="mt-1 text-xs font-extrabold text-slate-900">{p.title}</div>
                  <div className="mt-1 text-[11px] text-slate-600">{p.subtitle}</div>
                </button>
              )
            })}
          </div>

          {/* Action Bar + Cold vs Warm Cache Mode */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3.5">
            <div className="inline-flex rounded-xl border border-slate-300 bg-white p-1 text-xs">
              <button
                type="button"
                onClick={() => setCacheMode('cold_deal_room')}
                className={`rounded-lg px-3 py-1.5 font-bold transition ${
                  cacheMode === 'cold_deal_room'
                    ? 'bg-amber-600 text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Cold Deal-Room Entry (Q1 Cache Write)
              </button>
              <button
                type="button"
                onClick={() => setCacheMode('warm_shared_corpus')}
                className={`rounded-lg px-3 py-1.5 font-bold transition ${
                  cacheMode === 'warm_shared_corpus'
                    ? 'bg-amber-600 text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Warm Shared Corpus (All Cache Reads)
              </button>
            </div>

            <button
              type="button"
              disabled={loadingArena}
              onClick={() => void executeArena(selectedPresetId)}
              className="inline-flex items-center gap-2 rounded-xl bg-amber-600 px-4 py-2 text-xs font-extrabold text-white shadow-sm transition hover:bg-amber-700 disabled:opacity-50"
            >
              {creds.mode === 'live' ? (
                <Zap className="h-4 w-4 text-amber-200" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              <span>
                {loadingArena
                  ? 'Running 4-Query Audit...'
                  : creds.mode === 'live'
                    ? 'Run Live 3-Rung Deal-Room Audit'
                    : 'Replay Verified 4-Query Audit'}
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
          {/* RAG Callout Banner */}
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs font-semibold text-amber-950">
            {runResponse.rag_callout}
          </div>

          {/* 3-Rung Deal-Room Arena Cards */}
          <section className="grid gap-4 lg:grid-cols-3">
            {runResponse.results.map((res) => {
              const isNaive = res.rung_id === 'naive_full_corpus'
              const isCached = res.rung_id === 'cached_full_corpus_citations'
              const isHybrid = res.rung_id === 'hybrid_rag_rerank_citations'

              const borderTheme = isNaive
                ? 'border-rose-300'
                : isCached
                  ? 'border-blue-300'
                  : 'border-amber-400 ring-1 ring-amber-200'
              const headerBg = isNaive
                ? 'bg-rose-50'
                : isCached
                  ? 'bg-blue-50/80'
                  : 'bg-amber-50/90'
              const badgeBg = isNaive
                ? 'bg-rose-600 text-white'
                : isCached
                  ? 'bg-blue-600 text-white'
                  : 'bg-amber-600 text-white'

              const cost1kAudits =
                cacheMode === 'warm_shared_corpus'
                  ? res.cost_per_1k_audits_warm_usd
                  : res.cost_per_1k_audits_cold_usd
              const savingsPct =
                cacheMode === 'warm_shared_corpus'
                  ? res.savings_vs_naive_warm_pct
                  : res.savings_vs_naive_cold_pct

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
                          {res.queries.length} Queries
                        </span>
                      </div>
                      <h2 className="mt-2 text-sm font-extrabold text-slate-900">{res.rung_title}</h2>
                      <div className="mt-0.5 font-mono text-[11px] text-slate-600">
                        Anthropic · <strong>{res.model_id}</strong>
                        {res.reranker_model_id && ` + ${res.reranker_model_id} rerank`}
                      </div>
                    </div>

                    <div className="space-y-3 p-4">
                      {/* Primary FinOps Metric */}
                      <div className="flex items-baseline justify-between gap-2">
                        <div>
                          <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                            Cost / 1,000 4-Query Audits ({cacheMode === 'warm_shared_corpus' ? 'Warm' : 'Cold'})
                          </div>
                          <div className="font-mono text-2xl font-extrabold text-slate-900">
                            ${cost1kAudits.toFixed(2)}
                          </div>
                        </div>
                        {!isNaive && savingsPct > 0 && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-1 font-mono text-xs font-extrabold text-emerald-800">
                            <TrendingDown className="h-3.5 w-3.5" />-{savingsPct.toFixed(1)}%
                          </span>
                        )}
                      </div>

                      {/* Cold Single Query Comparator */}
                      <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[11px]">
                        <span className="font-semibold text-slate-600">Single Cold Query / 1k:</span>
                        <span className="font-mono font-extrabold text-slate-900">
                          ${res.single_query_cold_per_1k_usd.toFixed(2)} / 1k queries
                        </span>
                      </div>

                      {/* Token Grid */}
                      <div className="grid grid-cols-2 gap-2 rounded-xl bg-slate-50 p-2.5 font-mono text-[11px]">
                        <div>
                          <span className="block text-[10px] text-slate-500">UNCACHED IN</span>
                          <span className="font-bold text-slate-900">
                            {res.total_uncached_input_tokens.toLocaleString()} tok
                          </span>
                        </div>
                        <div>
                          <span className="block text-[10px] text-slate-500">CACHE W / R</span>
                          <span className="font-bold text-slate-900">
                            {cacheMode === 'warm_shared_corpus'
                              ? `0 / ${(res.total_cache_creation_tokens + res.total_cache_read_tokens).toLocaleString()}`
                              : `${res.total_cache_creation_tokens.toLocaleString()} / ${res.total_cache_read_tokens.toLocaleString()}`}
                          </span>
                        </div>
                        <div>
                          <span className="block text-[10px] text-slate-500">SYNTHESIS OUT</span>
                          <span className="font-bold text-slate-900">
                            {res.total_output_tokens.toLocaleString()} tok
                          </span>
                        </div>
                        <div>
                          <span className="block text-[10px] text-slate-500">
                            {isHybrid ? 'HAIKU RERANKER' : 'NATIVE CITATIONS'}
                          </span>
                          <span className="font-bold text-slate-900">
                            {isHybrid
                              ? `${res.reranker_calls} calls ($${(res.reranker_cost_usd * 1000).toFixed(2)}/1k)`
                              : `${res.avg_citations_per_query.toFixed(1)} spans / q`}
                          </span>
                        </div>
                      </div>

                      {/* Citation & Recall Verification Badges */}
                      <div className="flex flex-wrap items-center gap-2 text-[11px]">
                        <span
                          className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 font-bold ${
                            res.avg_citations_per_query > 0
                              ? 'bg-emerald-100 text-emerald-900'
                              : 'bg-slate-100 text-slate-600'
                          }`}
                        >
                          <Quote className="h-3 w-3" />
                          {res.avg_citations_per_query > 0
                            ? `${res.avg_citations_per_query} Native Spans/Q`
                            : '0 Verifiable Citations'}
                        </span>
                        {res.avg_doc_coverage_pct > 0 && (
                          <span className="rounded-md bg-blue-100 px-2 py-0.5 font-bold text-blue-900">
                            {res.avg_doc_coverage_pct}% Gold-Doc Coverage
                          </span>
                        )}
                        {res.avg_reranker_recall_pct !== null && (
                          <span className="rounded-md bg-amber-100 px-2 py-0.5 font-bold text-amber-950">
                            {res.avg_reranker_recall_pct}% Reranker Recall
                          </span>
                        )}
                      </div>

                      {/* Architectural Bullets */}
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
          </section>

          {/* Charts: Query-Count Crossover & Cost Component Breakdown */}
          <section className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-sm font-extrabold text-slate-900">
                    Queries per Deal Room Crossover ($ / 1,000 Deal Rooms)
                  </h2>
                  <p className="text-[11px] text-slate-500">
                    Why Hybrid RAG (Rung 3) wins on 1–4 cold queries &amp; huge corpora while Prefix Caching (Rung 2) wins at high query reuse
                  </p>
                </div>
              </div>
              <div className="h-72 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={crossoverData} margin={{ top: 10, right: 16, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
                    <Tooltip formatter={(val: number) => `$${val.toFixed(2)}`} />
                    <Legend wrapperStyle={{ fontSize: '11px' }} />
                    <Line
                      type="monotone"
                      dataKey="naive1k"
                      name="1. Naive Stuffing"
                      stroke="#dc2626"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="cachedCold1k"
                      name="2. Cached Corpus (Cold Q1)"
                      stroke="#2563eb"
                      strokeWidth={2.5}
                      dot={{ r: 3 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="cachedWarm1k"
                      name="2. Cached Corpus (Warm Fleet)"
                      stroke="#0ea5e9"
                      strokeDasharray="4 4"
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="hybrid1k"
                      name="3. Hybrid BM25 + Haiku"
                      stroke="#d97706"
                      strokeWidth={2.5}
                      dot={{ r: 3 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-3">
                <h2 className="text-sm font-extrabold text-slate-900">
                  4-Query Audit Cost Attribution ($ / 1,000 Audits)
                </h2>
                <p className="text-[11px] text-slate-500">
                  Shows exact Uncached Input vs. Prefix Cache W/R vs. 5x Output vs. On-Ledger Haiku Reranker spend
                </p>
              </div>
              <div className="h-72 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={componentBarData} margin={{ top: 10, right: 16, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
                    <Tooltip formatter={(val: number) => `$${val.toFixed(2)}`} />
                    <Legend wrapperStyle={{ fontSize: '11px' }} />
                    <Bar dataKey="Uncached Input" stackId="a" fill="#f97316" />
                    <Bar dataKey="Prefix Cache W/R" stackId="a" fill="#3b82f6" />
                    <Bar dataKey="Synthesis Output (5x)" stackId="a" fill="#1e293b" />
                    <Bar dataKey="Haiku Reranker" stackId="a" fill="#10b981" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </section>

          {/* Interactive Grounded Answer, Inline Citations & Deal-Room Document Explorer */}
          <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-slate-950 px-5 py-4 text-white">
              <div>
                <div className="text-[11px] font-bold uppercase tracking-wider text-amber-300">
                  Interactive Clause Citation Verifier &amp; 3-Stage Retrieval Funnel X-Ray
                </div>
                <h2 className="text-base font-extrabold">
                  Click any inline citation badge [1], [2] to verify the exact character-offset clause in the 7-doc Deal Room
                </h2>
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                {CAT4_RUNGS.map((rid) => (
                  <button
                    key={rid}
                    type="button"
                    onClick={() => {
                      setActiveRungView(rid)
                      setActiveCitation(null)
                    }}
                    className={`rounded-lg px-2.5 py-1.5 text-xs font-bold transition ${
                      activeRungView === rid
                        ? 'bg-amber-500 text-slate-950'
                        : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                    }`}
                  >
                    {rid === 'naive_full_corpus'
                      ? 'Rung 1: Naive'
                      : rid === 'cached_full_corpus_citations'
                        ? 'Rung 2: Cached + Cite'
                        : 'Rung 3: Hybrid RAG'}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-5 p-5">
              {/* Question Tabs or Active Custom Query Banner */}
              {adhocResult && adhocQuestionAsked ? (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-xs">
                  <div>
                    <span className="font-bold uppercase text-amber-900">Live Ad-Hoc Query Result: </span>
                    <span className="font-semibold text-slate-900">{adhocQuestionAsked}</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setAdhocResult(null)
                      setAdhocQuestionAsked(null)
                      setActiveCitation(null)
                    }}
                    className="rounded-lg bg-white px-2.5 py-1 font-bold text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50"
                  >
                    Return to 4-Query Audit Pack
                  </button>
                </div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {selectedPreset.questions.map((q, idx) => {
                    const active = idx === selectedQuestionIdx
                    return (
                      <button
                        key={q.question_id}
                        type="button"
                        onClick={() => {
                          setSelectedQuestionIdx(idx)
                          setActiveCitation(null)
                        }}
                        className={`rounded-xl border px-3 py-2 text-left text-xs transition ${
                          active
                            ? 'border-amber-600 bg-amber-50 font-extrabold text-amber-950 ring-1 ring-amber-600'
                            : 'border-slate-200 bg-slate-50 font-semibold text-slate-700 hover:bg-white'
                        }`}
                      >
                        <span className="font-mono text-[10px] text-amber-700">Q{q.question_number} · </span>
                        {q.topic_tag}
                      </button>
                    )
                  })}
                </div>
              )}

              {activeQueryResult && (
                <div className="grid gap-5 lg:grid-cols-12">
                  {/* Left 6 cols: Question + Grounded Answer with Inline Clickable Citation Badges */}
                  <div className="space-y-4 lg:col-span-6">
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                      <div className="flex items-center justify-between gap-2 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                        <span>Diligence Query · {activeQueryResult.topic_tag}</span>
                        <span className="font-mono text-slate-700">
                          {activeQueryResult.context_tokens_sent.toLocaleString()} ctx tok ·{' '}
                          {activeQueryResult.finops.output_tokens.toLocaleString()} out · $
                          {(activeQueryResult.cold_query_cost_usd * 1000).toFixed(2)}/1k
                        </span>
                      </div>
                      <p className="mt-1.5 text-xs font-bold leading-relaxed text-slate-900 sm:text-sm">
                        {activeQueryResult.question}
                      </p>
                    </div>

                    {/* Rendered Grounded Readout + Clickable Inline Citation Spans */}
                    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs">
                      <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2">
                        <span className="inline-flex items-center gap-1.5 text-xs font-extrabold text-slate-900">
                          <Sparkles className="h-3.5 w-3.5 text-amber-600" />
                          {activeRungObj?.rung_title} Readout
                        </span>
                        {activeQueryResult.citations.length > 0 ? (
                          <span className="rounded bg-emerald-100 px-2 py-0.5 font-mono text-[10px] font-bold text-emerald-900">
                            {activeQueryResult.citations.length} Verifiable Citations (
                            {activeQueryResult.doc_citation_coverage_pct}% Gold Docs)
                          </span>
                        ) : (
                          <span className="rounded bg-rose-100 px-2 py-0.5 font-mono text-[10px] font-bold text-rose-800">
                            Uncited Plain Text (No DocumentBlock Grounding)
                          </span>
                        )}
                      </div>

                      <div className="whitespace-pre-wrap text-xs leading-relaxed text-slate-800">
                        {activeQueryResult.segments.length > 0 ? (
                          activeQueryResult.segments.map((seg, sIdx) => (
                            <span key={sIdx}>
                              <span>{seg.text}</span>
                              {seg.cite_numbers.map((cnum) => {
                                const citObj = activeQueryResult.citations.find(
                                  (c) => c.cite_number === cnum
                                )
                                if (!citObj) return null
                                const isSel =
                                  activeCitation?.cite_number === citObj.cite_number &&
                                  activeCitation?.doc_id === citObj.doc_id
                                return (
                                  <button
                                    key={cnum}
                                    type="button"
                                    onClick={() => handleCitationClick(citObj)}
                                    title={`${citObj.doc_id}: ${citObj.clause_ref}`}
                                    className={`mx-0.5 inline-flex items-center rounded px-1.5 py-0.2 align-baseline font-mono text-[10px] font-extrabold transition ${
                                      isSel
                                        ? 'bg-amber-600 text-white ring-2 ring-amber-300'
                                        : 'bg-amber-100 text-amber-900 hover:bg-amber-200'
                                    }`}
                                  >
                                    [{cnum}]
                                  </button>
                                )
                              })}
                            </span>
                          ))
                        ) : (
                          <span>{activeQueryResult.answer_markdown}</span>
                        )}
                      </div>
                    </div>

                    {/* Citation Chips Tray */}
                    {activeQueryResult.citations.length > 0 && (
                      <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5">
                        <div className="mb-2 text-[11px] font-bold uppercase tracking-wider text-slate-600">
                          Verified Citation Spans ({activeQueryResult.citations.length})
                        </div>
                        <div className="flex max-h-52 flex-col gap-1.5 overflow-y-auto pr-1">
                          {activeQueryResult.citations.map((cit) => {
                            const isSel =
                              activeCitation?.cite_number === cit.cite_number &&
                              activeCitation?.doc_id === cit.doc_id
                            return (
                              <button
                                key={`${cit.cite_number}-${cit.doc_id}-${cit.start_char_index}`}
                                type="button"
                                onClick={() => handleCitationClick(cit)}
                                className={`rounded-lg border px-3 py-2 text-left text-[11px] transition ${
                                  isSel
                                    ? 'border-amber-600 bg-amber-100/80 ring-1 ring-amber-500'
                                    : 'border-slate-200 bg-white hover:border-amber-300'
                                }`}
                              >
                                <div className="flex items-center justify-between gap-2 font-mono text-[10px] font-bold">
                                  <span className="text-amber-800">
                                    [{cit.cite_number}] {cit.doc_id} · {cit.clause_ref || cit.document_title}
                                  </span>
                                  <span className="text-slate-500">
                                    chars {cit.start_char_index}–{cit.end_char_index}
                                  </span>
                                </div>
                                <div className="mt-1 line-clamp-2 italic text-slate-700">
                                  “{cit.cited_text}”
                                </div>
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Right 6 cols: Native <details> 7-Doc Source Explorer (search-hidden-content compliant) */}
                  <div className="space-y-3 lg:col-span-6" ref={docViewerRef}>
                    <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5">
                      <div className="flex items-center gap-1.5 text-xs font-extrabold text-slate-900">
                        <BookOpen className="h-4 w-4 text-amber-600" />
                        <span>7-Document Deal-Room Source Explorer (Cmd+F Searchable)</span>
                      </div>
                      {activeCitation && (
                        <span className="rounded bg-amber-200 px-2 py-0.5 font-mono text-[10px] font-extrabold text-amber-950">
                          Highlighting [{activeCitation.cite_number}] in {activeCitation.doc_id}
                        </span>
                      )}
                    </div>

                    <div className="mwg-accordion space-y-2">
                      {presetsData.documents.map((doc) => {
                        const isOpen = openDocId === doc.doc_id
                        const hasCiteMatch = activeQueryResult.cited_doc_ids.includes(doc.doc_id)
                        const highlightSpan =
                          activeCitation && activeCitation.doc_id === doc.doc_id
                            ? {
                                start: activeCitation.start_char_index,
                                end: activeCitation.end_char_index,
                              }
                            : null

                        return (
                          <details
                            key={doc.doc_id}
                            name="cat4-deal-room-doc"
                            open={isOpen}
                            onToggle={(e) => {
                              if (e.currentTarget.open) {
                                setOpenDocId(doc.doc_id)
                              }
                            }}
                            className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xs"
                          >
                            <summary className="justify-between bg-slate-50/80 px-3.5 py-2.5 text-xs font-bold text-slate-900 hover:bg-slate-100/80">
                              <span className="flex min-w-0 flex-1 items-center gap-2">
                                <FileText className="h-3.5 w-3.5 shrink-0 text-amber-600" />
                                <span className="shrink-0 whitespace-nowrap font-mono text-[11px] text-amber-800">{doc.doc_id}</span>
                                <span className="truncate">{doc.doc_code} — {doc.title}</span>
                              </span>
                              <span className="ml-2 flex shrink-0 items-center gap-1.5 font-mono text-[10px]">
                                {hasCiteMatch && (
                                  <span className="rounded bg-emerald-100 px-1.5 py-0.5 font-bold text-emerald-800">
                                    Cited
                                  </span>
                                )}
                                <span className="text-slate-500">{doc.approx_tokens.toLocaleString()} tok</span>
                              </span>
                            </summary>
                            <div className="border-t border-slate-100 p-3.5">
                              <div className="mb-2 text-[11px] text-slate-600">{doc.summary}</div>
                              <pre className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-[11px] leading-relaxed text-slate-800">
                                {renderHighlightedDocument(doc.full_text, highlightSpan)}
                              </pre>
                            </div>
                          </details>
                        )
                      })}
                    </div>
                  </div>
                </div>
              )}

              {/* Rung 3: 3-Stage Hybrid Retrieval Funnel X-Ray (always shown from Hybrid Rung result) */}
              {(() => {
                const hybridSource =
                  activeSourceSummaryList.find((r) => r.rung_id === 'hybrid_rag_rerank_citations') ??
                  null
                const hybridQ = adhocResult
                  ? hybridSource?.queries[0] ?? null
                  : hybridSource?.queries[selectedQuestionIdx] ?? hybridSource?.queries[0] ?? null
                if (!hybridQ || hybridQ.retrieval_funnel.length === 0) return null

                const selectedCount = hybridQ.retrieval_funnel.filter(
                  (f) => f.stage === 'selected_by_reranker'
                ).length
                const prunedRerankCount = hybridQ.retrieval_funnel.filter(
                  (f) => f.stage === 'pruned_by_reranker'
                ).length
                const prunedBm25Count = hybridQ.retrieval_funnel.filter(
                  (f) => f.stage === 'pruned_by_bm25'
                ).length

                return (
                  <div className="space-y-3 border-t border-slate-200 pt-5">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Filter className="h-4 w-4 text-amber-600" />
                        <div>
                          <h3 className="text-sm font-extrabold text-slate-900">
                            Rung 3 Hybrid Retrieval Funnel X-Ray (28 Chunks → 10 BM25 → {selectedCount} Haiku-Reranked → Sonnet Synthesis)
                          </h3>
                          <p className="text-[11px] text-slate-500">
                            Pruned <strong>{hybridQ.context_reduction_pct.toFixed(1)}%</strong> of corpus chars ·{' '}
                            {hybridQ.reranker_recall_pct !== null && (
                              <>
                                Gold-Clause Recall: <strong>{hybridQ.reranker_recall_pct}%</strong> ·{' '}
                              </>
                            )}
                            Haiku Rerank Cost:{' '}
                            <strong>
                              ${((hybridQ.reranker_finops?.total_cost_usd ?? 0) * 1000).toFixed(2)} / 1k queries
                            </strong>{' '}
                            ({selectedCount} selected, {prunedRerankCount} pruned at rerank, {prunedBm25Count} pruned at BM25)
                          </p>
                        </div>
                      </div>
                    </div>

                    <div
                      tabIndex={0}
                      role="region"
                      aria-labelledby="cat4-funnel-caption"
                      className="table-wrapper rounded-xl border border-slate-200"
                    >
                      <table
                        className="mwg-table min-w-full divide-y divide-slate-200 text-xs"
                        data-table="cat4-funnel"
                      >
                        <caption id="cat4-funnel-caption" className="sr-only">
                          Category 4 Rung 3 28-chunk retrieval and Haiku 5.5 reranking funnel
                        </caption>
                        <thead className="bg-slate-100 text-[11px] font-bold uppercase tracking-wider text-slate-600">
                          <tr>
                            <th scope="col" className="px-3 py-2.5 text-left">Chunk ID</th>
                            <th scope="col" className="px-3 py-2.5 text-left">Document &amp; Clause</th>
                            <th scope="col" className="px-3 py-2.5 text-right">BM25 Score</th>
                            <th scope="col" className="px-3 py-2.5 text-left">Stage &amp; Haiku Rationale</th>
                            <th scope="col" className="px-3 py-2.5 text-right">Gold / Est. Tok</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 bg-white">
                          {hybridQ.retrieval_funnel.map((row) => {
                            const isSel = row.stage === 'selected_by_reranker'
                            const isMid = row.stage === 'pruned_by_reranker'
                            return (
                              <tr
                                key={row.chunk_id}
                                className={
                                  isSel
                                    ? 'bg-emerald-50/40'
                                    : isMid
                                      ? 'bg-amber-50/30'
                                      : 'opacity-70'
                                }
                              >
                                <th scope="row" className="whitespace-nowrap px-3 py-2 text-left font-mono text-[11px] font-bold text-slate-900">
                                  #{row.bm25_rank} · {row.chunk_id}
                                </th>
                                <td className="px-3 py-2 text-[11px] text-slate-700">
                                  <div className="font-bold text-slate-900">{row.doc_title}</div>
                                  <div className="text-[10px] text-slate-500">{row.clause_ref}</div>
                                </td>
                                <td className="whitespace-nowrap px-3 py-2 text-right font-mono text-[11px] font-semibold text-slate-700">
                                  {row.bm25_score.toFixed(2)}
                                </td>
                                <td className="px-3 py-2 text-[11px]">
                                  <div className="flex flex-wrap items-center gap-1.5">
                                    <span
                                      className={`rounded px-2 py-0.5 font-mono text-[10px] font-bold ${
                                        isSel
                                          ? 'bg-emerald-100 text-emerald-900'
                                          : isMid
                                            ? 'bg-amber-100 text-amber-900'
                                            : 'bg-slate-100 text-slate-600'
                                      }`}
                                    >
                                      {isSel
                                        ? `SELECTED (${row.reranker_score}/100)`
                                        : isMid
                                          ? 'PRUNED AT RERANK'
                                          : 'PRUNED AT BM25'}
                                    </span>
                                    {row.reranker_rationale && (
                                      <span className="text-slate-600">{row.reranker_rationale}</span>
                                    )}
                                  </div>
                                </td>
                                <td className="whitespace-nowrap px-3 py-2 text-right font-mono text-[11px]">
                                  {row.is_expected_gold && (
                                    <span className="mr-1.5 inline-flex items-center gap-0.5 rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-bold text-blue-900">
                                      <CheckCircle2 className="h-3 w-3" /> Gold
                                    </span>
                                  )}
                                  <span className="text-slate-600">~{row.approx_tokens} tok</span>
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )
              })()}

              {/* Custom Live Due-Diligence Query Composer */}
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <label
                  htmlFor="cat4-adhoc-input"
                  className="flex items-center gap-1.5 text-xs font-extrabold text-slate-900"
                >
                  <Search className="h-3.5 w-3.5 text-amber-600" />
                  <span>Ask Custom Multi-Doc Deal-Room Question (Live API Mode)</span>
                </label>
                <p id="cat4-adhoc-hint" className="mt-1 text-[11px] text-slate-600">
                  {creds.mode === 'live'
                    ? 'Live API Mode active: runs your custom question simultaneously across Naive Stuffing, Cached DocumentBlocks, and Hybrid BM25 + Haiku Reranking.'
                    : 'Verified Replay Mode ($0) serves the 8 pre-captured golden diligence audits. Switch Credit Shield to Live API Mode in the header to test ad-hoc questions.'}
                </p>

                <div className="mt-2 flex flex-wrap gap-1.5">
                  {selectedPreset.suggested_custom_queries.map((sq, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => setAdhocInput(sq)}
                      className="rounded-lg border border-amber-200 bg-white px-2.5 py-1 text-left text-[11px] font-semibold text-amber-900 hover:bg-amber-50"
                    >
                      Try Custom Prompt #{idx + 1}
                    </button>
                  ))}
                </div>

                <textarea
                  id="cat4-adhoc-input"
                  aria-describedby="cat4-adhoc-hint"
                  rows={2}
                  value={adhocInput}
                  onChange={(e) => setAdhocInput(e.target.value)}
                  placeholder="Ask any cross-document question across MSA-NM-DSA-2026, Addendum A, Schedules B–D, MCA AOC-4, or Side Letter #2..."
                  className="mwg-auto-textarea mt-2.5 rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-xs text-slate-900 focus:border-amber-600 focus:outline-none"
                />

                {adhocError && (
                  <div className="mt-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800">
                    {adhocError}
                  </div>
                )}

                <div className="mt-2 flex justify-end">
                  <button
                    type="button"
                    disabled={loadingAdhoc || adhocInput.trim().length < 8}
                    onClick={() => void handleRunAdhocQuery()}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-amber-600 px-4 py-2 text-xs font-extrabold text-white shadow-xs transition hover:bg-amber-700 disabled:opacity-40"
                  >
                    <Send className="h-3.5 w-3.5" />
                    <span>{loadingAdhoc ? 'Querying 3 Rungs...' : 'Run Across 3 RAG Rungs'}</span>
                  </button>
                </div>
              </div>
            </div>
          </section>

          {/* CFO Deal-Room Scale Simulator */}
          {naiveSummary && cachedSummary && hybridSummary && (
            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <DollarSign className="h-4 w-4 text-amber-600" />
                  <div>
                    <h2 className="text-sm font-extrabold text-slate-900">
                      CFO Deal-Room Scale Simulator ({monthlyAudits.toLocaleString()} 4-Query Audits / Month)
                    </h2>
                    <p className="text-[11px] text-slate-500">
                      Monthly &amp; Annualized spend projection across NovaMart supplier onboarding, M&amp;A, and quarterly tax audits
                    </p>
                  </div>
                </div>
                <span className="rounded-full bg-slate-100 px-3 py-1 font-mono text-xs font-bold text-slate-700">
                  Mode: {cacheMode === 'warm_shared_corpus' ? 'Warm Corpus' : 'Cold Entry'}
                </span>
              </div>

              <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-bold text-slate-700">
                  <label htmlFor="cat4-volume-slider">Monthly 4-Query Audits Volume</label>
                  <div className="flex flex-wrap gap-1.5">
                    {VOLUME_STEPS.map((st) => (
                      <button
                        key={st.value}
                        type="button"
                        onClick={() => setMonthlyAudits(st.value)}
                        className={`rounded-lg px-2.5 py-1 font-mono text-[11px] font-bold transition ${
                          monthlyAudits === st.value
                            ? 'bg-amber-600 text-white'
                            : 'bg-white text-slate-600 ring-1 ring-slate-200 hover:text-slate-900'
                        }`}
                      >
                        {st.label}
                      </button>
                    ))}
                  </div>
                </div>
                <input
                  id="cat4-volume-slider"
                  type="range"
                  min={500}
                  max={100_000}
                  step={500}
                  value={monthlyAudits}
                  onChange={(e) => setMonthlyAudits(Number(e.target.value))}
                  className="mt-3 w-full accent-amber-600"
                />
              </div>

              <div className="mt-4 grid gap-3 md:grid-cols-3">
                {[naiveSummary, cachedSummary, hybridSummary].map((r) => {
                  const perAudit =
                    cacheMode === 'warm_shared_corpus'
                      ? r.warm_audit_cost_usd
                      : r.cold_audit_cost_usd
                  const monthly = perAudit * monthlyAudits
                  const annual = monthly * 12
                  return (
                    <div
                      key={r.rung_id}
                      className="rounded-xl border border-slate-200 bg-slate-50/70 p-4"
                    >
                      <div className="flex items-center gap-1.5 text-xs font-extrabold text-slate-900">
                        {r.rung_id === 'naive_full_corpus' ? (
                          <Database className="h-3.5 w-3.5 text-rose-600" />
                        ) : r.rung_id === 'cached_full_corpus_citations' ? (
                          <Cpu className="h-3.5 w-3.5 text-blue-600" />
                        ) : (
                          <Filter className="h-3.5 w-3.5 text-amber-600" />
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

      {/* Architecture & SDK Code Inspector Modal */}
      <NativeModal
        open={inspectorOpen}
        onClose={() => setInspectorOpen(false)}
        title="Category 4 Architecture & SDK Inspector"
        subtitle="Inspect Anthropic DocumentBlock Caching, Native Citations & Haiku 5.5 Cross-Chunk Reranker"
        maxWidthClass="max-w-3xl"
      >
        <div className="space-y-4">
          <div
            role="tablist"
            aria-label="Category 4 inspector sections"
            onKeyDown={handleInspectorTabKeyDown}
            className="mwg-tablist border-b border-slate-200"
          >
            {(
              [
                ['code', 'Python SDK Comparison'],
                ['schema', 'Haiku Reranker JSON Schema'],
              ] as const
            ).map(([tid, label]) => (
              <button
                key={tid}
                type="button"
                role="tab"
                id={`cat4-insp-tab-${tid}`}
                aria-selected={inspectorTab === tid}
                tabIndex={inspectorTab === tid ? 0 : -1}
                onClick={() => setInspectorTab(tid)}
                className={`mwg-tab px-4 py-2 text-xs font-bold ${
                  inspectorTab === tid ? 'text-amber-700' : 'text-slate-500 hover:text-slate-900'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div role="tabpanel" aria-labelledby="cat4-insp-tab-code" hidden={inspectorTab !== 'code'}>
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

          <div role="tabpanel" aria-labelledby="cat4-insp-tab-schema" hidden={inspectorTab !== 'schema'}>
            <pre className="max-h-96 overflow-auto rounded-xl bg-slate-950 p-3.5 font-mono text-[11px] leading-relaxed text-amber-300">
              {JSON.stringify(presetsData.rerank_schema, null, 2)}
            </pre>
          </div>
        </div>
      </NativeModal>
    </div>
  )
}
