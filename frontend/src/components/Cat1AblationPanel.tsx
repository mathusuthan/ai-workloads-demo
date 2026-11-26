import { FlaskConical } from 'lucide-react'
import type { Cat1AblationArm, Cat1AblationMiss, Cat1AblationPortfolio } from '../types'
import { DesignMark } from './DesignMark'

interface Cat1AblationPanelProps {
  portfolio: Cat1AblationPortfolio | null | undefined
}

// The deck's lever (rows) x model (columns): one experiment arm per cell.
const ROWS: Array<{ key: 'report' | 'schema'; label: string }> = [
  { key: 'report', label: 'Without the lever: four-part write-up, free text' },
  { key: 'schema', label: 'With the lever: classification with strict JSON schema' },
]
const COLS: Array<{ key: 'sonnet' | 'haiku'; label: string }> = [
  { key: 'sonnet', label: 'Sonnet 5.5' },
  { key: 'haiku', label: 'Haiku 5.5' },
]

function money(x: number | null | undefined): string {
  if (x == null) return '—'
  return x < 1 ? `$${x.toFixed(3)}` : `$${x.toFixed(2)}`
}

function tok(x: number | null | undefined): string {
  return x == null ? '—' : Math.round(x).toLocaleString()
}

function seconds(ms: number | null | undefined): string {
  return ms == null ? '—' : `${(ms / 1000).toFixed(1)} s`
}

function plain(v: unknown): string {
  if (typeof v === 'boolean') return v ? 'yes' : 'no'
  if (v == null) return 'no answer'
  return String(v).replace(/_/g, ' ').replace(/\b([A-Z]{2,})\b/g, (m) => m.toLowerCase())
}

function Cell({ arm }: { arm: Cat1AblationArm | undefined }) {
  if (!arm || arm.runs === 0) {
    return <span className="text-slate-400">(not run)</span>
  }
  const writeUp = arm.task === 'report'
  const ci = arm.wilson95
  return (
    <div className="space-y-0.5">
      <div className="font-mono text-sm font-extrabold text-slate-900">
        {arm.fields_correct ?? '—'}/{arm.fields_total ?? '—'} fields
        {writeUp && <span className="text-amber-700">*</span>}
        {ci && ci.length === 2 && (
          <span className="ml-1 text-[10px] font-normal text-slate-500">
            ({ci[0].toFixed(0)}–{ci[1].toFixed(0)}%)
          </span>
        )}
      </div>
      <div className="font-mono text-[11px] text-slate-700">
        {arm.items_fully_correct ?? '—'}/{arm.items} items fully correct
      </div>
      <div className="font-mono text-[11px] text-slate-900">
        {money(arm.cost_per_1k_items_usd)} / 1k items
        {arm.batch_cost_per_1k_items_usd_computed != null && (
          <span className="text-slate-500"> · Batch API (computed) {money(arm.batch_cost_per_1k_items_usd_computed)}</span>
        )}
      </div>
      <div className="font-mono text-[11px] text-slate-600">
        prompt {tok(arm.input_tokens_median)} / output {tok(arm.output_tokens_median)} tokens
        <span className="text-slate-400">
          {' '}
          (output {tok(arm.output_tokens_min)}–{tok(arm.output_tokens_max)})
        </span>
      </div>
      <div className="font-mono text-[11px] text-slate-600">{seconds(arm.latency_ms_median)} median response time</div>
    </div>
  )
}

function MissNote({ portfolio }: { portfolio: Cat1AblationPortfolio }) {
  const groups = new Map<string, Cat1AblationMiss[]>()
  for (const m of portfolio.misses) {
    const key = `${m.arm_id}|${m.item_id}`
    groups.set(key, [...(groups.get(key) ?? []), m])
  }
  if (groups.size === 0) return null
  const label = (id: string) => portfolio.arms.find((a) => a.arm_id === id)?.label ?? id
  return (
    <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50/70 p-3">
      <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">
        Where the Classification Versions Did Not Match
      </h3>
      <ul className="mt-1.5 space-y-1.5 text-[11px] leading-relaxed text-slate-800">
        {Array.from(groups.values()).map((g) => {
          const runs = Math.max(...g.map((m) => m.runs_missed))
          const fields = g.map((m) => `${m.field_label} “${plain(m.returned)}” instead of “${plain(m.expected)}”`).join('; ')
          return (
            <li key={`${g[0].arm_id}${g[0].item_id}`}>
              <span className="font-bold">{g[0].item_id}</span> {g[0].item_title}{' '}
              <span className="text-slate-500">({label(g[0].arm_id)})</span>: {fields} — {runs} of {g[0].runs_total} runs
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export function Cat1AblationPanel({ portfolio }: Cat1AblationPanelProps) {
  const header = (
    <div className="border-b border-slate-200 pb-3">
      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-indigo-700">
        <FlaskConical className="h-4 w-4" />
        Experiment · Without and With the Lever
      </div>
      <h2 className="mt-0.5 text-lg font-extrabold text-slate-900">Four Cells on the Same Twelve Items</h2>
      <p className="mt-1 max-w-4xl text-xs leading-relaxed text-slate-600">
        Rows: without the lever (today’s four-part write-up) and with it (only the classification fields, through a
        strict JSON schema). Columns: the model. The four rungs above are repeat 0 of these cells.
      </p>
    </div>
  )
  if (!portfolio || portfolio.arms.length === 0) {
    return (
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        {header}
        <p className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-500 ring-1 ring-slate-200">
          Experiment results are not available.
        </p>
      </section>
    )
  }
  const arm = (task: string, model: string) =>
    portfolio.arms.find((a) => a.task === task && a.model.toLowerCase().startsWith(model))
  const dq = portfolio.data_quality
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      {header}

      <p className="mt-4 max-w-4xl text-[11px] leading-relaxed text-slate-600">
        {portfolio.runs_per_arm} runs per cell ({portfolio.items} items × {portfolio.repeats} runs), {portfolio.fields_per_arm}{' '}
        scored fields per cell. Cost per 1,000 items at the app’s rate card; tokens and response time are medians.
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left text-[11px]">
          <thead>
            <tr className="border-b border-slate-200 text-[10px] uppercase text-slate-500">
              <th className="py-1.5 pr-3 font-bold" />
              {COLS.map((c) => (
                <th key={c.key} className="py-1.5 pr-3 font-bold">
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROWS.map((r) => (
              <tr key={r.key} className="border-b border-slate-100 align-top">
                <th
                  scope="row"
                  className={`border-l-4 py-2 pl-2 pr-3 text-left font-bold ${
                    r.key === 'schema' ? 'border-l-emerald-600 text-emerald-900' : 'border-l-rose-500 text-rose-900'
                  }`}
                >
                  <span className="inline-flex items-start gap-1.5">
                    <DesignMark withLever={r.key === 'schema'} className="mt-0.5" />
                    {r.label}
                  </span>
                </th>
                {COLS.map((c) => (
                  <td key={c.key} className="py-2 pr-3">
                    <Cell arm={arm(r.key, c.key)} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1.5 max-w-4xl text-[11px] leading-relaxed text-slate-700">
        <span className="font-bold text-amber-700">*</span> The write-up prompt asks for an analysis and does not list the
        allowed labels. For the write-ups, “fields correct” counts the fields where one allowed label could be read off the
        write-up and it matched the answer key: whether the write-up is usable as a classification, not a measure of the rest
        of the write-up.
      </p>

      <MissNote portfolio={portfolio} />

      <p className="mt-5 text-[10px] leading-relaxed text-slate-500">
        Method: {portfolio.ok_runs} live runs ({portfolio.arms.length} cells × {portfolio.items} items × {portfolio.repeats}{' '}
        runs). Free-text answers were read by a model that was not under test and never saw the right answer (
        {portfolio.reader_passes} pass), and compared with the ground truth like a JSON answer.{' '}
        {portfolio.reader_check_note ? `${portfolio.reader_check_note} ` : ''}
        {dq.truncated === 0 ? 'No answer was cut off.' : `${dq.truncated} answers were cut off at their cap and are kept.`}{' '}
        The Batch API price is computed at 50% of the live price, not run. With {portfolio.items} items, small differences
        between cells are indicative only.
      </p>
    </section>
  )
}
