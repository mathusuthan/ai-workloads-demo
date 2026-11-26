import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertCircle,
  ArrowLeft,
  Code2,
  Database,
  Play,
  ShieldCheck,
  Sparkles,
  Zap,
} from 'lucide-react'
import { runCat1Arena, runCat1Batch } from '../api'
import type {
  ArchetypeSpec,
  Cat1BatchResponse,
  Cat1PresetsResponse,
  Cat1RunResponse,
  CreditShieldCredentials,
  RungId,
  SubTaskType,
} from '../types'
import { Cat1AblationPanel } from './Cat1AblationPanel'
import { FinOpsHud } from './FinOpsHud'
import { NativeModal } from './NativeModal'
import { RungResultCard } from './RungResultCard'

interface Cat1WorkbenchProps {
  archetype: ArchetypeSpec
  presetsData: Cat1PresetsResponse
  creds: CreditShieldCredentials
  onRefreshSystemStatus: () => void
}

const ALL_RUNGS: RungId[] = ['sonnet_naive', 'haiku_naive', 'sonnet_calibrated', 'haiku_calibrated']
const ALL_VISIBLE: Record<RungId, boolean> = {
  sonnet_naive: true,
  haiku_naive: true,
  sonnet_calibrated: true,
  haiku_calibrated: true,
}
const NONE_VISIBLE: Record<RungId, boolean> = {
  sonnet_naive: false,
  haiku_naive: false,
  sonnet_calibrated: false,
  haiku_calibrated: false,
}
// Replay reveal order: the fast classification rungs arrive first, the long write-ups last.
const REVEAL_SCHEDULE: Array<[RungId, number]> = [
  ['haiku_calibrated', 200],
  ['sonnet_calibrated', 450],
  ['haiku_naive', 950],
  ['sonnet_naive', 1450],
]

function fmtUsd(x: number): string {
  return `$${x < 1 ? x.toFixed(4) : x.toFixed(2)}`
}

function fmtPct(x: number | null | undefined): string {
  return x == null ? '—' : `${x.toFixed(0)}%`
}

export function Cat1Workbench({
  archetype,
  presetsData,
  creds,
  onRefreshSystemStatus,
}: Cat1WorkbenchProps) {
  const [activeView, setActiveView] = useState<'arena' | 'batch'>('arena')
  const [subTask, setSubTask] = useState<SubTaskType>('support_triage')

  const filteredPresets = useMemo(
    () => presetsData.presets.filter((p) => p.sub_task === subTask),
    [presetsData.presets, subTask]
  )

  const [selectedPresetId, setSelectedPresetId] = useState<string>(
    presetsData.presets.find((p) => p.sub_task === 'support_triage')?.id ?? 'tkt-01'
  )
  const [payloadText, setPayloadText] = useState<string>(
    presetsData.presets.find((p) => p.sub_task === 'support_triage')?.payload ?? ''
  )
  const [simulateTiming, setSimulateTiming] = useState<boolean>(true)
  const [visibleRungs, setVisibleRungs] = useState<Record<RungId, boolean>>(ALL_VISIBLE)

  const [runResponse, setRunResponse] = useState<Cat1RunResponse | null>(null)
  const [batchResponse, setBatchResponse] = useState<Cat1BatchResponse | null>(null)
  const [batchScope, setBatchScope] = useState<'mixed' | SubTaskType>('mixed')
  const [loadingArena, setLoadingArena] = useState(false)
  const [loadingBatch, setLoadingBatch] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [inspectorTab, setInspectorTab] = useState<'code' | 'schema'>('code')

  const selectedPreset = useMemo(
    () => presetsData.presets.find((p) => p.id === selectedPresetId) ?? filteredPresets[0],
    [presetsData.presets, selectedPresetId, filteredPresets]
  )

  const isPayloadModified =
    selectedPreset !== undefined && payloadText.trim() !== selectedPreset.payload.trim()

  const handleSelectSubTask = (nextSubTask: SubTaskType) => {
    setSubTask(nextSubTask)
    const first = presetsData.presets.find((p) => p.sub_task === nextSubTask)
    if (first) {
      setSelectedPresetId(first.id)
      setPayloadText(first.payload)
    }
    setErrorMsg(null)
  }

  const handleSelectPreset = (presetId: string) => {
    const found = presetsData.presets.find((p) => p.id === presetId)
    if (found) {
      setSelectedPresetId(found.id)
      setPayloadText(found.payload)
      setErrorMsg(null)
    }
  }

  const executeArena = async (overridePresetId?: string, overrideSubTask?: SubTaskType) => {
    const targetSub = overrideSubTask ?? subTask
    const targetPresetId = overridePresetId ?? selectedPresetId
    const targetPreset = presetsData.presets.find((p) => p.id === targetPresetId)
    const modified =
      !overridePresetId &&
      targetPreset !== undefined &&
      payloadText.trim() !== targetPreset.payload.trim()

    setLoadingArena(true)
    setErrorMsg(null)
    try {
      const resp = await runCat1Arena(
        {
          preset_id: modified ? undefined : targetPresetId,
          custom_input: modified ? payloadText : undefined,
          sub_task: targetSub,
          rungs: ALL_RUNGS,
          mode: creds.mode,
        },
        creds
      )
      setRunResponse(resp)

      if (resp.mode_used === 'live') {
        onRefreshSystemStatus()
      }

      if (resp.mode_used === 'replay' && simulateTiming) {
        setVisibleRungs(NONE_VISIBLE)
        for (const [rung, delay] of REVEAL_SCHEDULE) {
          window.setTimeout(() => setVisibleRungs((prev) => ({ ...prev, [rung]: true })), delay)
        }
      } else {
        setVisibleRungs(ALL_VISIBLE)
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to run the 4-rung arena.')
    } finally {
      setLoadingArena(false)
    }
  }

  const executeBatch = async (scopeOverride?: 'mixed' | SubTaskType) => {
    const scope = scopeOverride ?? batchScope
    setLoadingBatch(true)
    setErrorMsg(null)
    try {
      const resp = await runCat1Batch(
        {
          sub_task: scope,
          mode: creds.mode,
        },
        creds
      )
      setBatchResponse(resp)
      if (resp.mode_used === 'live') {
        onRefreshSystemStatus()
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to run 12-Item Batch simulator.')
    } finally {
      setLoadingBatch(false)
    }
  }

  // Auto-load initial Verified Replay on mount so visitors see live charts immediately
  useEffect(() => {
    void executeArena('tkt-01', 'support_triage')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleViewTabKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault()
      const next = activeView === 'arena' ? 'batch' : 'arena'
      setActiveView(next)
      if (next === 'batch' && !batchResponse) {
        void executeBatch()
      }
      document.getElementById(next === 'arena' ? 'tab-arena' : 'tab-batch')?.focus()
    }
  }

  const handleInspectorTabKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const order: Array<'code' | 'schema'> = ['code', 'schema']
    const idx = order.indexOf(inspectorTab)
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      const next = order[(idx + 1) % order.length]
      setInspectorTab(next)
      document.getElementById(`insp-tab-${next}`)?.focus()
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      const next = order[(idx - 1 + order.length) % order.length]
      setInspectorTab(next)
      document.getElementById(`insp-tab-${next}`)?.focus()
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
      {/* Top Breadcrumb + Archetype Header */}
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
          <Code2 className="h-4 w-4 text-blue-600" />
          Architecture &amp; Code Inspector
        </button>
      </div>

      <section className="overflow-hidden rounded-2xl border border-blue-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 bg-blue-600 px-6 py-2.5 text-white">
          <div className="flex flex-wrap items-center gap-2 text-xs font-extrabold uppercase tracking-wider">
            <span>{archetype.category_label}</span>
            <span>·</span>
            <span>{archetype.autonomy_tier_label}</span>
            <span className="rounded bg-white/20 px-2 py-0.5 font-mono text-[11px]">
              {archetype.token_band}
            </span>
          </div>
          <span className="font-mono text-xs font-bold text-blue-100">
            {archetype.dynamics}
          </span>
        </div>

        <div className="flex flex-col justify-between gap-4 px-6 py-5 lg:flex-row lg:items-center">
          <div>
            <h1 className="text-xl font-extrabold tracking-tight text-slate-900 sm:text-2xl">
              {archetype.title} — {archetype.novamart_product_name}
            </h1>
            <p className="mt-1 max-w-3xl text-xs leading-relaxed text-slate-600 sm:text-sm">
              The same ticket or SKU on <strong>Sonnet 5.5</strong> and <strong>Haiku 5.5</strong>, without the
              improvement (a <strong>four-part write-up</strong> in free text) and with it (the{' '}
              <strong>classification with a strict JSON schema</strong>). The experiment below the rungs shows the
              four cells over 12 items and 3 repeats.
            </p>
          </div>

          {/* Sub-Task Selector */}
          <div className="flex shrink-0 flex-wrap gap-2">
            <button
              type="button"
              onClick={() => handleSelectSubTask('support_triage')}
              className={`rounded-xl border px-3.5 py-2 text-left text-xs font-bold transition ${
                subTask === 'support_triage'
                  ? 'border-blue-600 bg-blue-50 text-blue-900 ring-1 ring-blue-600'
                  : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
              }`}
            >
              <div>1A · Support Triage &amp; PII</div>
              <div className="mt-0.5 text-[10px] font-normal text-slate-500">
                Escalations, fraud &amp; redaction
              </div>
            </button>

            <button
              type="button"
              onClick={() => handleSelectSubTask('sku_tagging')}
              className={`rounded-xl border px-3.5 py-2 text-left text-xs font-bold transition ${
                subTask === 'sku_tagging'
                  ? 'border-blue-600 bg-blue-50 text-blue-900 ring-1 ring-blue-600'
                  : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
              }`}
            >
              <div>1B · Cold-Start SKU Gate</div>
              <div className="mt-0.5 text-[10px] font-normal text-slate-500">
                Contradiction OCR &amp; hazmat check
              </div>
            </button>
          </div>
        </div>

        {/* Accessible Tablist for Arena vs Batch */}
        <div
          role="tablist"
          aria-label="Category 1 workbench modes"
          onKeyDown={handleViewTabKeyDown}
          className="mwg-tablist border-t border-slate-200 bg-slate-50 px-6"
        >
          <button
            type="button"
            role="tab"
            id="tab-arena"
            aria-selected={activeView === 'arena'}
            tabIndex={activeView === 'arena' ? 0 : -1}
            onClick={() => setActiveView('arena')}
            className={`mwg-tab inline-flex items-center gap-2 px-4 py-3 text-xs font-bold transition ${
              activeView === 'arena' ? 'text-blue-700' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Sparkles className="h-3.5 w-3.5" />
            4-Rung Ablation Arena (Single Payload)
          </button>

          <button
            type="button"
            role="tab"
            id="tab-batch"
            aria-selected={activeView === 'batch'}
            tabIndex={activeView === 'batch' ? 0 : -1}
            onClick={() => {
              setActiveView('batch')
              if (!batchResponse) {
                void executeBatch()
              }
            }}
            className={`mwg-tab inline-flex items-center gap-2 px-4 py-3 text-xs font-bold transition ${
              activeView === 'batch' ? 'text-blue-700' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Database className="h-3.5 w-3.5" />
            12-Item Batch &amp; CFO Scale Simulator
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

      {/* TAB PANEL 1: 4-RUNG ARENA (no padding/border directly on tabpanel per tabs guide) */}
      <div role="tabpanel" aria-labelledby="tab-arena" hidden={activeView !== 'arena'}>
        <div className="space-y-6">
          {/* Preset Picker & Input Envelope */}
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-extrabold text-slate-900">
                Select NovaMart {subTask === 'support_triage' ? 'Support Escalation' : 'Cold-Start SKU'} Payload
              </h2>
              <span className="font-mono text-[11px] text-slate-500">
                {payloadText.length.toLocaleString()} chars (~
                {Math.max(1, Math.round(payloadText.length / 3.8)).toLocaleString()} tokens)
              </span>
            </div>

            <div className="mt-3 grid gap-3 md:grid-cols-3">
              {filteredPresets.map((p) => {
                const active = p.id === selectedPresetId && !isPayloadModified
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => handleSelectPreset(p.id)}
                    className={`rounded-xl border p-3.5 text-left transition ${
                      active
                        ? 'border-blue-600 bg-blue-50/70 ring-1 ring-blue-600'
                        : 'border-slate-200 bg-slate-50/50 hover:border-slate-300 hover:bg-white'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[10px] font-bold uppercase text-blue-700">
                        {p.id} · {p.channel}
                      </span>
                      <span className="rounded bg-slate-200/80 px-1.5 py-0.5 font-mono text-[10px] font-bold text-slate-700">
                        ~{p.approx_tokens} tok
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
                <label htmlFor="cat1-payload-input" className="text-xs font-bold text-slate-700">
                  Raw Unstructured Input Payload{' '}
                  {creds.mode === 'replay'
                    ? '(Select a preset above for $0 Verified Replay; switch to Live API to edit freely)'
                    : '(Live API Mode active — edit freely to test custom payloads)'}
                </label>
                {isPayloadModified && selectedPreset && (
                  <button
                    type="button"
                    onClick={() => setPayloadText(selectedPreset.payload)}
                    className="text-[11px] font-bold text-blue-700 hover:underline"
                  >
                    Reset to Preset ({selectedPreset.id})
                  </button>
                )}
              </div>
              <textarea
                id="cat1-payload-input"
                rows={7}
                value={payloadText}
                onChange={(e) => setPayloadText(e.target.value)}
                className="w-full rounded-xl border border-slate-300 bg-slate-950 p-3.5 font-mono text-xs leading-relaxed text-slate-100 focus:border-blue-500 focus:outline-none"
              />
            </div>

            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <label className="inline-flex cursor-pointer items-center gap-2 text-xs font-medium text-slate-700">
                <input
                  type="checkbox"
                  checked={simulateTiming}
                  onChange={(e) => setSimulateTiming(e.target.checked)}
                  className="accent-blue-600"
                />
                <span>Simulate staggered latency arrival in Replay mode (classification answers arrive first)</span>
              </label>

              <button
                type="button"
                disabled={loadingArena}
                onClick={() => void executeArena()}
                className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-5 py-2.5 text-xs font-extrabold text-white shadow-sm transition hover:bg-blue-700 disabled:opacity-50"
              >
                {creds.mode === 'live' ? (
                  <Zap className="h-4 w-4 text-amber-300" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
                <span>
                  {loadingArena
                    ? 'Running 4-Rung Arena...'
                    : creds.mode === 'live'
                      ? 'Run Live 4-Rung API Arena'
                      : 'Run 4-Rung Ablation Arena'}
                </span>
              </button>
            </div>
          </section>

          {/* 4-Rung Ablation Grid */}
          {runResponse && (
            <>
              {runResponse.ground_truth && (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-slate-950 px-4 py-2.5 text-xs text-white">
                  <span className="font-bold uppercase tracking-wider text-slate-300">
                    Ground Truth Labels ({runResponse.preset_id}):
                  </span>
                  <div className="flex flex-wrap gap-1.5 font-mono text-[11px]">
                    {Object.entries(runResponse.ground_truth).map(([k, v]) => (
                      <span
                        key={k}
                        className="rounded bg-slate-800 px-2 py-0.5 text-emerald-300 ring-1 ring-slate-700"
                      >
                        {k}: <strong>{String(v)}</strong>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div className="grid gap-4 md:grid-cols-2">
                {runResponse.results.map((res) => (
                  <RungResultCard
                    key={res.rung_id}
                    result={res}
                    visible={visibleRungs[res.rung_id]}
                  />
                ))}
              </div>

              {/* Boundary note + Deterministic PII Masking Panel */}
              <section className="rounded-2xl border border-indigo-200 bg-indigo-50/50 p-5 shadow-xs">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="max-w-3xl space-y-1.5">
                    <div className="inline-flex items-center gap-1.5 text-xs font-extrabold uppercase tracking-wider text-indigo-900">
                      <ShieldCheck className="h-4 w-4 text-indigo-700" />
                      Boundary &amp; Companion Deterministic PII Gate
                    </div>
                    <p className="text-xs leading-relaxed text-slate-700">
                      {runResponse.system1_boundary_note}
                    </p>
                  </div>

                </div>

                <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs font-extrabold text-slate-900">
                      Deterministic &lt;1ms Regex PII Redaction Output (
                      {runResponse.pii_redaction.total_redactions} sensitive tokens scrubbed)
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(runResponse.pii_redaction.counts_by_type).length > 0 ? (
                        Object.entries(runResponse.pii_redaction.counts_by_type).map(
                          ([ptype, count]) => (
                            <span
                              key={ptype}
                              className="rounded-md bg-amber-100 px-2 py-0.5 font-mono text-[10px] font-bold text-amber-900"
                            >
                              {ptype}: {count}
                            </span>
                          )
                        )
                      ) : (
                        <span className="rounded-md bg-emerald-100 px-2 py-0.5 font-mono text-[10px] font-bold text-emerald-800">
                          Zero raw PII detected
                        </span>
                      )}
                    </div>
                  </div>
                  <pre className="mt-2.5 max-h-44 overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-slate-950 p-3 font-mono text-[11px] leading-relaxed text-slate-200">
                    {runResponse.pii_redaction.masked_preview}
                  </pre>
                </div>
              </section>

              {/* FinOps HUD */}
              <FinOpsHud runResponse={runResponse} />

              <Cat1AblationPanel portfolio={runResponse.ablation_portfolio} />
            </>
          )}
        </div>
      </div>

      {/* TAB PANEL 2: 12-ITEM BATCH & CFO SCALE SIMULATOR */}
      <div role="tabpanel" aria-labelledby="tab-batch" hidden={activeView !== 'batch'}>
        <div className="space-y-6">
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-extrabold text-slate-900">
                  12-Item Queue Benchmark &amp; CFO Scale Projection
                </h2>
                <p className="mt-0.5 text-xs text-slate-600">
                  Runs the mixed Support Escalations + Cold-Start SKU feed through the four rungs: Sonnet 5.5 and
                  Haiku 5.5, without the improvement (four-part write-up) and with it (classification with a strict
                  JSON schema). The two "with" rows also show the Batch API price (computed at 50%, not run).
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <select
                  aria-label="Filter batch workload"
                  value={batchScope}
                  onChange={(e) => {
                    const val = e.target.value as 'mixed' | SubTaskType
                    setBatchScope(val)
                    void executeBatch(val)
                  }}
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-800"
                >
                  <option value="mixed">Mixed NovaMart Queue (12 items)</option>
                  <option value="support_triage">Support Triage Only (6 items)</option>
                  <option value="sku_tagging">SKU Catalog Gate Only (6 items)</option>
                </select>

                <button
                  type="button"
                  disabled={loadingBatch}
                  onClick={() => void executeBatch()}
                  className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-xs font-extrabold text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  <Play className="h-3.5 w-3.5" />
                  <span>{loadingBatch ? 'Running Batch...' : 'Re-Run Batch Simulation'}</span>
                </button>
              </div>
            </div>

            {batchResponse && (
              <div className="mt-4 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-xs font-semibold text-blue-950">
                {batchResponse.summary_callout}
              </div>
            )}
          </section>

          {batchResponse && (
            <>
              {/* 4-Model Accuracy vs Cost Scorecard */}
              {batchResponse.accuracy_rollup && batchResponse.accuracy_rollup.length > 0 && (
                <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className="text-sm font-extrabold text-slate-900">
                      Model Accuracy vs. Cost Benchmark ({batchResponse.total_items} Ground-Truth Items)
                    </h3>
                    <span className="text-[11px] text-slate-500">
                      Fields correct vs. ground truth · write-ups read by a reader model
                    </span>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    {batchResponse.accuracy_rollup.map((m) => (
                      <div
                        key={m.rung_id}
                        className="rounded-xl border border-slate-200 bg-slate-50/80 p-3.5"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-extrabold text-slate-900">{m.label}</span>
                          <span
                            className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-bold ${
                              m.schema_compliance_pct === 100
                                ? 'bg-emerald-100 text-emerald-800'
                                : 'bg-amber-100 text-amber-900'
                            }`}
                          >
                            {m.schema_compliance_pct === 100 ? 'Structured answer' : 'Free-text write-up'}
                          </span>
                        </div>
                        <div className="mt-2 flex items-baseline justify-between">
                          <div>
                            <div className="text-[10px] font-bold uppercase text-slate-400">
                              {m.schema_compliance_pct === 100 ? 'Fields Correct' : 'Usable & Correct'}
                            </div>
                            <div className="font-mono text-xl font-extrabold tabular-nums text-slate-900">
                              {m.field_accuracy_pct == null ? 'not scored' : `${m.field_accuracy_pct.toFixed(1)}%`}
                            </div>
                            {m.field_accuracy_pct != null && (
                              <div className="font-mono text-[10px] text-slate-500">
                                {m.fields_matched}/{m.fields_total} fields · {m.exact_items_matched}/
                                {m.items_total} exact
                              </div>
                            )}
                          </div>
                          <div className="text-right">
                            <div className="text-[10px] font-bold uppercase text-slate-400">
                              Unit Cost
                            </div>
                            <div className="font-mono text-sm font-extrabold text-blue-700">
                              {fmtUsd(m.cost_per_1k_usd)}
                            </div>
                            <div className="text-[10px] text-slate-500">per 1k</div>
                          </div>
                        </div>
                        <p className="mt-2 text-[11px] leading-snug text-slate-600">{m.notes}</p>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* CFO Comparison Table of the four rungs (Responsive Table Pattern) */}
              <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <h3 id="cfo-table-heading" className="mb-3 text-sm font-extrabold text-slate-900">
                  FinOps Comparison of the Four Rungs ({batchResponse.total_items}-Item Mean)
                </h3>

                <div
                  tabIndex={0}
                  role="region"
                  aria-labelledby="cfo-table-heading"
                  className="table-wrapper rounded-xl border border-slate-200"
                >
                  <table
                    className="mwg-table text-left text-xs"
                    data-table="cfo"
                    style={
                      {
                        '--label-2': '"Avg In / Out"',
                        '--label-3': '"Field Accuracy"',
                        '--label-4': '"Cost / 1k"',
                        '--label-5': '"100k / mo"',
                        '--label-6': '"1M / mo"',
                        '--label-7': '"Batch API (computed)"',
                        '--label-8': '"Savings vs Sonnet write-up"',
                      } as React.CSSProperties
                    }
                  >
                    <caption className="sr-only">
                      Unit economics and accuracy of Sonnet 5.5 and Haiku 5.5, without the improvement (four-part
                      write-up) and with it (classification with a strict JSON schema); the Batch API price of the two
                      "with" rows is computed, not run.
                    </caption>
                    <thead className="bg-slate-900 text-[11px] font-bold uppercase tracking-wider text-slate-200">
                      <tr>
                        <th className="px-4 py-3">Rung</th>
                        <th className="px-4 py-3 font-mono">Avg In / Out Tok</th>
                        <th className="px-4 py-3 font-mono">Field Accuracy</th>
                        <th className="px-4 py-3 text-right font-mono">Cost / 1k</th>
                        <th className="px-4 py-3 text-right font-mono">100k / mo</th>
                        <th className="px-4 py-3 text-right font-mono">1M / mo</th>
                        <th className="px-4 py-3 text-right font-mono">Batch API (computed)</th>
                        <th className="px-4 py-3 text-right font-mono">Savings</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 bg-white">
                      {batchResponse.cfo_comparison.map((row) => (
                        <tr key={row.tier_id} className="hover:bg-slate-50">
                          <th scope="row" className="px-4 py-3 text-left font-bold text-slate-900">
                            <div>{row.label}</div>
                            <div className="text-[11px] font-normal text-slate-500">
                              {row.scope_note}
                            </div>
                          </th>
                          <td className="px-4 py-3 font-mono text-slate-700">
                            {row.avg_input_tokens} in / {row.avg_output_tokens} out
                          </td>
                          <td className="px-4 py-3 font-mono text-xs">
                            {row.field_accuracy_pct !== null && row.field_accuracy_pct !== undefined ? (
                              <div>
                                <span
                                  className={`font-bold ${
                                    row.field_accuracy_pct >= 90
                                      ? 'text-emerald-700'
                                      : 'text-amber-800'
                                  }`}
                                >
                                  {row.field_accuracy_pct.toFixed(1)}%
                                </span>
                                <span className="ml-1 text-[10px] text-slate-500">
                                  ({row.exact_match_pct?.toFixed(0)}% exact)
                                </span>
                                <div className="text-[10px] text-slate-500">
                                  {row.schema_compliance_label}
                                </div>
                              </div>
                            ) : (
                              <span className="text-[11px] text-slate-400">
                                {row.schema_compliance_label || 'not scored'}
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-right font-mono font-bold tabular-nums text-slate-900">
                            {fmtUsd(row.cost_per_1k_usd)}
                          </td>
                          <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-800">
                            ${row.monthly_100k_usd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </td>
                          <td className="px-4 py-3 text-right font-mono font-bold tabular-nums text-slate-900">
                            ${row.monthly_1m_usd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </td>
                          <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-700">
                            {row.batch_cost_per_1k_usd != null ? (
                              <div>
                                <div>{fmtUsd(row.batch_cost_per_1k_usd)} / 1k</div>
                                {row.batch_monthly_1m_usd != null && (
                                  <div className="text-[10px] text-slate-500">
                                    ${row.batch_monthly_1m_usd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} / 1M mo
                                  </div>
                                )}
                              </div>
                            ) : (
                              <span className="text-slate-400">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-right font-mono font-bold tabular-nums">
                            {row.savings_vs_naive_pct > 0 ? (
                              <span className="rounded bg-emerald-100 px-2 py-0.5 text-emerald-800">
                                -{row.savings_vs_naive_pct.toFixed(1)}%
                              </span>
                            ) : (
                              <span className="text-slate-400">Baseline</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              {/* 12-Item Queue Table */}
              <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <h3 id="batch-items-heading" className="mb-3 text-sm font-extrabold text-slate-900">
                  Per-Item Classification &amp; Parity Log ({batchResponse.total_items} Items)
                </h3>

                <div
                  tabIndex={0}
                  role="region"
                  aria-labelledby="batch-items-heading"
                  className="table-wrapper rounded-xl border border-slate-200"
                >
                  <table
                    className="mwg-table text-left text-xs"
                    data-table="batch-items"
                    style={
                      {
                        '--label-2': '"Sub-task"',
                        '--label-3': '"Tokens"',
                        '--label-4': '"Haiku 5.5 schema"',
                        '--label-5': '"Sonnet 5.5 schema"',
                        '--label-6': '"Accuracy (SW/HW/SS/HS)"',
                        '--label-7': '"Regex PII"',
                      } as React.CSSProperties
                    }
                  >
                    <caption className="sr-only">
                      Item-level classification outputs and ground-truth accuracy for the Sonnet and Haiku write-ups and the Sonnet and Haiku JSON-schema classifications.
                    </caption>
                    <thead className="bg-slate-900 text-[11px] font-bold uppercase tracking-wider text-slate-200">
                      <tr>
                        <th className="px-4 py-3">Item</th>
                        <th className="px-4 py-3">Track</th>
                        <th className="px-4 py-3 font-mono">In / Haiku Out</th>
                        <th className="px-4 py-3">Haiku 5.5 Verdict</th>
                        <th className="px-4 py-3">Sonnet 5.5 Verdict</th>
                        <th className="px-4 py-3 font-mono">Accuracy (vs GT)</th>
                        <th className="px-4 py-3 text-right font-mono">PII Masked</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 bg-white">
                      {batchResponse.items.map((item) => (
                        <tr key={item.item_id} className="hover:bg-slate-50">
                          <th scope="row" className="px-4 py-3 text-left font-bold text-slate-900">
                            <span className="mr-1.5 font-mono text-[10px] text-blue-700">
                              {item.item_id}
                            </span>
                            <span className="font-semibold">{item.title}</span>
                          </th>
                          <td className="px-4 py-3 font-mono text-[11px] text-slate-600">
                            {item.sub_task === 'support_triage' ? '1A Support' : '1B Catalog'}
                          </td>
                          <td className="px-4 py-3 font-mono text-[11px] text-slate-700">
                            {item.input_tokens} / {item.haiku_output_tokens}
                          </td>
                          <td className="px-4 py-3 font-mono text-[11px] text-blue-800">
                            {String(
                              item.haiku_decision.queue ??
                                item.haiku_decision.compliance_status ??
                                ''
                            )}{' '}
                            <span className="text-slate-400">
                              (
                              {String(
                                item.haiku_decision.priority ??
                                  item.haiku_decision.leaf_category ??
                                  ''
                              )}
                              )
                            </span>
                          </td>
                          <td className="px-4 py-3 font-mono text-[11px] text-indigo-800">
                            {String(
                              item.sonnet_schema_decision.queue ??
                                item.sonnet_schema_decision.compliance_status ??
                                ''
                            )}{' '}
                            <span className="text-slate-400">
                              (
                              {String(
                                item.sonnet_schema_decision.priority ??
                                  item.sonnet_schema_decision.leaf_category ??
                                  ''
                              )}
                              )
                            </span>
                          </td>
                          <td className="px-4 py-3 font-mono text-[10px]">
                            <div className="flex flex-wrap gap-1">
                              <span className="rounded bg-rose-50 px-1.5 py-0.5 text-rose-800 ring-1 ring-rose-200" title="Sonnet write-up (usable as a classification)">
                                SW:{fmtPct(item.sonnet_accuracy_pct)}
                              </span>
                              <span className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-900 ring-1 ring-amber-200" title="Haiku write-up (usable as a classification)">
                                HW:{fmtPct(item.haiku_naive_accuracy_pct)}
                              </span>
                              <span className="rounded bg-indigo-50 px-1.5 py-0.5 font-bold text-indigo-800 ring-1 ring-indigo-200" title="Sonnet classification with JSON schema">
                                SS:{fmtPct(item.sonnet_schema_accuracy_pct)}
                              </span>
                              <span className="rounded bg-blue-50 px-1.5 py-0.5 font-bold text-blue-800 ring-1 ring-blue-200" title="Haiku classification with JSON schema">
                                HS:{fmtPct(item.haiku_accuracy_pct)}
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-right font-mono font-bold text-slate-800">
                            {item.pii_redactions > 0 ? (
                              <span className="rounded bg-amber-100 px-2 py-0.5 text-amber-900">
                                {item.pii_redactions} scrubbed
                              </span>
                            ) : (
                              <span className="text-slate-400">0</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <Cat1AblationPanel portfolio={batchResponse.ablation_portfolio} />
            </>
          )}
        </div>
      </div>

      {/* Architecture & Code Inspector Modal */}
      <NativeModal
        open={inspectorOpen}
        onClose={() => setInspectorOpen(false)}
        title="Category 1 Architecture & SDK Inspector"
        subtitle="Inspect the call settings of the four rungs and the JSON schema of the classification rungs"
        maxWidthClass="max-w-3xl"
      >
        <div className="space-y-4">
          <div
            role="tablist"
            aria-label="Architecture inspector sections"
            onKeyDown={handleInspectorTabKeyDown}
            className="mwg-tablist border-b border-slate-200"
          >
            {(
              [
                ['code', 'Python SDK Comparison'],
                ['schema', 'Classification JSON Schema'],
              ] as const
            ).map(([tid, label]) => (
              <button
                key={tid}
                type="button"
                role="tab"
                id={`insp-tab-${tid}`}
                aria-selected={inspectorTab === tid}
                tabIndex={inspectorTab === tid ? 0 : -1}
                onClick={() => setInspectorTab(tid)}
                className={`mwg-tab px-3.5 py-2.5 text-xs font-bold ${
                  inspectorTab === tid ? 'text-blue-700' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div role="tabpanel" aria-labelledby="insp-tab-code" hidden={inspectorTab !== 'code'}>
            <div className="space-y-3">
              {ALL_RUNGS.map((rId) => (
                <pre
                  key={rId}
                  className="overflow-x-auto rounded-xl bg-slate-950 p-3.5 font-mono text-[11px] leading-relaxed text-slate-100"
                >
                  {presetsData.code_snippets[rId]}
                </pre>
              ))}
            </div>
          </div>

          <div role="tabpanel" aria-labelledby="insp-tab-schema" hidden={inspectorTab !== 'schema'}>
            <pre className="overflow-x-auto rounded-xl bg-slate-950 p-4 font-mono text-[11px] leading-relaxed text-emerald-300">
              {JSON.stringify(presetsData.schemas[subTask], null, 2)}
            </pre>
          </div>

        </div>
      </NativeModal>
    </div>
  )
}
