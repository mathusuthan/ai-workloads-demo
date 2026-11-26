import { useMemo, useState } from 'react'
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
import { DollarSign, TrendingDown } from 'lucide-react'
import type { Cat1RunResponse, FinOpsBreakdown } from '../types'

interface FinOpsHudProps {
  runResponse: Cat1RunResponse
}

interface ComparisonRow {
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
}

const VOLUME_STEPS = [
  { label: '10k / mo (Pilot)', value: 10_000 },
  { label: '100k / mo (Mid-Market)', value: 100_000 },
  { label: '1M / mo (Growth)', value: 1_000_000 },
  { label: '5M / mo (NovaMart Steady)', value: 5_000_000 },
  { label: '20M / mo (Diwali Burst)', value: 20_000_000 },
]

export function FinOpsHud({ runResponse }: FinOpsHudProps) {
  const [volumeIdx, setVolumeIdx] = useState(2) // Default 1M / mo
  const [scaleMode, setScaleMode] = useState<'linear' | 'log'>('log')

  const monthlyVol = VOLUME_STEPS[volumeIdx].value

  const comparisons = useMemo(() => {
    const byId = Object.fromEntries(runResponse.results.map((r) => [r.rung_id, r]))
    const rows: ComparisonRow[] = []

    const push = (id: string, name: string, shortLabel: string, f: FinOpsBreakdown | null | undefined, color: string) => {
      if (!f) return
      const c1k = f.cost_per_1k_usd
      rows.push({
        id,
        name,
        shortLabel,
        costPer1k: c1k,
        chartValue: scaleMode === 'log' ? Math.max(0.01, c1k) : c1k,
        inputCost1k: Number((f.input_cost_usd * 1000).toFixed(4)),
        outputCost1k: Number((f.output_cost_usd * 1000).toFixed(4)),
        monthlyUsd: f.total_cost_usd * monthlyVol,
        annualUsd: f.total_cost_usd * monthlyVol * 12,
        color,
      })
    }
    const ok = (id: string) => (byId[id] && byId[id].status === 'ok' ? byId[id].finops : null)

    push('sonnet_naive', 'Without · Sonnet 5.5 write-up', 'Sonnet write-up', ok('sonnet_naive'), '#E11D48')
    push('haiku_naive', 'Without · Haiku 5.5 write-up', 'Haiku write-up', ok('haiku_naive'), '#D97706')
    push('sonnet_calibrated', 'With · Sonnet 5.5 JSON schema', 'Sonnet schema', ok('sonnet_calibrated'), '#4F46E5')
    push('sonnet_batch', 'With · Sonnet 5.5 Batch API (computed, not run)', 'Sonnet Batch*', runResponse.sonnet_batch_comparator, '#818CF8')
    push('haiku_calibrated', 'With · Haiku 5.5 JSON schema', 'Haiku schema', ok('haiku_calibrated'), '#2563EB')
    push('haiku_batch', 'With · Haiku 5.5 Batch API (computed, not run)', 'Haiku Batch*', runResponse.haiku_batch_comparator, '#0284C7')

    return rows
  }, [runResponse, monthlyVol, scaleMode])

  const naiveMonthly = comparisons.find((c) => c.id === 'sonnet_naive')?.monthlyUsd ?? 0
  const haikuSchemaMonthly = comparisons.find((c) => c.id === 'haiku_calibrated')?.monthlyUsd
  const annualSaved = haikuSchemaMonthly == null ? 0 : Math.max(0, (naiveMonthly - haikuSchemaMonthly) * 12)

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-blue-700">
            <DollarSign className="h-4 w-4" />
            Live FinOps &amp; CFO Unit Economics HUD
          </div>
          <h2 className="mt-0.5 text-lg font-extrabold text-slate-900">
            Scaling This Exact Payload Across NovaMart Enterprise Volume
          </h2>
          <p className="mt-0.5 text-[11px] text-slate-500">
            Costs come from this item’s measured tokens. *The Batch API prices of the two “with” rungs are computed at 50% of the live price, not run.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-0.5 text-xs">
            <button
              type="button"
              onClick={() => setScaleMode('log')}
              className={`rounded-md px-2.5 py-1 font-semibold transition ${
                scaleMode === 'log' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600'
              }`}
            >
              Log Scale
            </button>
            <button
              type="button"
              onClick={() => setScaleMode('linear')}
              className={`rounded-md px-2.5 py-1 font-semibold transition ${
                scaleMode === 'linear' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600'
              }`}
            >
              Linear Scale
            </button>
          </div>
        </div>
      </div>

      {/* Volume Slider */}
      <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label htmlFor="cfo-volume-slider" className="text-xs font-bold text-slate-700">
            Projected Monthly Workload Volume:{' '}
            <span className="font-mono text-blue-700">{VOLUME_STEPS[volumeIdx].label}</span>
          </label>
          {annualSaved > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-3 py-1 font-mono text-xs font-bold text-emerald-900">
              <TrendingDown className="h-3.5 w-3.5" />
              Annualized Savings (Sonnet write-up → Haiku schema): $
              {annualSaved.toLocaleString(undefined, { maximumFractionDigits: 0 })}/yr
            </span>
          )}
        </div>
        <input
          id="cfo-volume-slider"
          type="range"
          min={0}
          max={VOLUME_STEPS.length - 1}
          step={1}
          value={volumeIdx}
          onChange={(e) => setVolumeIdx(Number(e.target.value))}
          className="mt-3 w-full accent-blue-600"
        />
        <div className="mt-1 flex justify-between font-mono text-[10px] text-slate-500">
          {VOLUME_STEPS.map((s, idx) => (
            <span key={s.value} className={idx === volumeIdx ? 'font-bold text-blue-700' : ''}>
              {s.label.split(' ')[0]}
            </span>
          ))}
        </div>
      </div>

      {/* Charts Grid */}
      <div className="mt-5 grid gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 p-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">
              Unit Cost per 1,000 Executions (USD · {scaleMode === 'log' ? 'Log10' : 'Linear'})
            </h3>
          </div>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={comparisons}
                layout="vertical"
                margin={{ top: 8, right: 64, left: 10, bottom: 8 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
                <XAxis
                  type="number"
                  scale={scaleMode}
                  domain={scaleMode === 'log' ? [0.01, 'auto'] : [0, 'auto']}
                  tickFormatter={(v: number) => `$${v}`}
                  tick={{ fontSize: 11, fill: '#475569' }}
                />
                <YAxis
                  type="category"
                  dataKey="shortLabel"
                  width={95}
                  tick={{ fontSize: 11, fill: '#0f172a', fontWeight: 600 }}
                />
                <Tooltip
                  formatter={(_val: unknown, _name: unknown, props: { payload?: { costPer1k: number } }) => [
                    `$${props.payload?.costPer1k.toFixed(4)} / 1k runs`,
                    'Unit Cost',
                  ]}
                />
                <Bar dataKey="chartValue" radius={[0, 6, 6, 0]}>
                  {comparisons.map((entry) => (
                    <Cell key={entry.id} fill={entry.color} />
                  ))}
                  <LabelList
                    dataKey="costPer1k"
                    position="right"
                    formatter={(v: number) => (v < 1 ? `$${v.toFixed(3)}` : `$${v.toFixed(2)}`)}
                    style={{ fontSize: 11, fontFamily: 'monospace', fontWeight: 700, fill: '#0f172a' }}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 p-4">
          <h3 className="mb-2 text-xs font-extrabold uppercase tracking-wider text-slate-700">
            Why Output Tokens Kill Unit Economics ($ / 1k Runs Breakdown)
          </h3>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={comparisons}
                margin={{ top: 10, right: 20, left: 0, bottom: 8 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="shortLabel" tick={{ fontSize: 11, fill: '#0f172a', fontWeight: 600 }} />
                <YAxis tickFormatter={(v: number) => `$${v}`} tick={{ fontSize: 11, fill: '#475569' }} />
                <Tooltip formatter={(val: number) => `$${val.toFixed(4)} / 1k`} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="inputCost1k" name="Input Cost / 1k" stackId="a" fill="#64748b" />
                <Bar
                  dataKey="outputCost1k"
                  name="Output Cost / 1k (5x Rate)"
                  stackId="a"
                  fill="#e11d48"
                  radius={[6, 6, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Projected Monthly Spend Strip */}
      <div className="mt-5 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-6">
        {comparisons.map((c) => (
          <div
            key={c.id}
            className="rounded-xl border border-slate-200 bg-slate-50/70 p-3"
            style={{ borderTopWidth: '3px', borderTopColor: c.color }}
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
  )
}
