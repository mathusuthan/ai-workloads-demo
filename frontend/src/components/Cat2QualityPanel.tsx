import { ShieldCheck } from 'lucide-react'
import type {
  Cat2Arm,
  Cat2Cell,
  Cat2Count,
  Cat2Dimension,
  Cat2HeadToHeadBlock,
  Cat2QualityPortfolio,
  Cat2RungId,
  Cat2RungQuality,
  Cat2RungResult,
} from '../types'
import { DesignMark } from './DesignMark'

interface Cat2QualityPanelProps {
  results: Cat2RungResult[]
  portfolio: Cat2QualityPortfolio | null | undefined
}

const RUNG_NAME: Record<Cat2RungId, string> = {
  sonnet_unbounded: 'Sonnet unbounded',
  haiku_unbounded: 'Haiku unbounded',
  sonnet_templated: 'Sonnet template',
  haiku_templated: 'Haiku template',
}

const RUNG_BAR: Record<Cat2RungId, string> = {
  // red family without the lever, green family with it; two shades tell the models apart
  sonnet_unbounded: 'bg-rose-600',
  haiku_unbounded: 'bg-rose-400',
  sonnet_templated: 'bg-emerald-700',
  haiku_templated: 'bg-emerald-500',
}

const ROWS: { arm: Cat2Arm; label: string }[] = [
  { arm: 'unbounded', label: 'Without the lever: unbounded long-form draft' },
  { arm: 'template_not_stated', label: 'With the lever: section template with length caps' },
]
const COLS: { key: 'sonnet' | 'haiku'; label: string }[] = [
  { key: 'sonnet', label: 'Sonnet 5.5' },
  { key: 'haiku', label: 'Haiku 5.5' },
]

const DIMENSIONS: { key: Cat2Dimension; label: string }[] = [
  { key: 'factual_accuracy', label: 'Accuracy' },
  { key: 'coverage', label: 'Coverage' },
  { key: 'clarity', label: 'Clarity' },
  { key: 'actionability', label: 'Actionability' },
  { key: 'concision', label: 'Concision' },
]

function frac(m: Cat2Count | null | undefined): string {
  return m && m.total > 0 ? `${m.hits}/${m.total}` : 'n/a'
}

function winnerName(w: string | null | undefined): string {
  if (!w) return 'no result'
  if (w === 'tie') return 'tie'
  return RUNG_NAME[w as Cat2RungId] ?? w
}

function GradeBar({ label, value, barClass }: { label: string; value: number | null | undefined; barClass: string }) {
  return (
    <div className="grid grid-cols-[88px_1fr_34px] items-center gap-2">
      <span className="text-[10px] font-bold uppercase text-slate-500">{label}</span>
      <div
        className="h-2 w-full overflow-hidden rounded-full bg-slate-100"
        role="img"
        aria-label={`${label}: ${value == null ? 'not graded' : `${value.toFixed(1)} of 5`}`}
      >
        {value != null && (
          <div className={`h-full rounded-full ${barClass}`} style={{ width: `${Math.max((value / 5) * 100, 2)}%` }} />
        )}
      </div>
      <span className="text-right font-mono text-[11px] text-slate-900">{value == null ? '—' : value.toFixed(1)}</span>
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2 text-[10px] font-bold uppercase text-slate-500">
      <span>{label}</span>
      <span className={`font-mono text-[11px] normal-case ${tone ?? 'text-slate-900'}`}>{value}</span>
    </div>
  )
}

function SeriousErrors({ q }: { q: Cat2RungQuality }) {
  const serious = (q.errors ?? []).filter((e) => e.severity === 'material')
  if (q.errors == null) return null
  if (serious.length === 0) {
    return <p className="text-[10px] text-slate-500">No serious errors reported on this document.</p>
  }
  return (
    <details className="group rounded-lg bg-white ring-1 ring-slate-200">
      <summary className="cursor-pointer list-none px-2.5 py-1.5 text-[11px] font-bold text-rose-800">
        Serious errors on this document ({serious.length})
        <span className="ml-1 font-normal text-slate-400 group-open:hidden">show</span>
      </summary>
      <ul className="space-y-2 border-t border-slate-100 px-2.5 py-2">
        {serious.map((e, i) => (
          <li key={i} className="space-y-0.5 text-[10px] leading-snug">
            <div>
              <span className="font-bold text-slate-500">Draft says: </span>
              <span className="text-slate-900">“{e.claim_quote}”</span>
            </div>
            <div>
              <span className="font-bold text-slate-500">Problem: </span>
              <span className="text-slate-700">{e.problem}</span>
            </div>
            <div>
              <span className="font-bold text-slate-500">Source says: </span>
              {e.source_quote ? (
                <span className="text-slate-700">“{e.source_quote}”</span>
              ) : (
                <span className="italic text-slate-500">not in the source</span>
              )}
            </div>
            <div className="text-slate-400">
              Reported in {e.passes_reporting} of {q.passes ?? 1} grading passes
            </div>
          </li>
        ))}
      </ul>
    </details>
  )
}

function CellBox({ c }: { c: Cat2Cell | undefined }) {
  if (!c) return <td className="p-2.5 align-top text-[11px] text-slate-500">not available</td>
  if (c.status === 'pending') {
    return (
      <td className="p-2.5 align-top">
        <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-500 ring-1 ring-slate-200">run pending</span>
        <div className="mt-1 text-[10px] text-slate-500">{c.drafts_planned} drafts planned (3 per document)</div>
      </td>
    )
  }
  const r = c.rubric ?? {}
  return (
    <td className="space-y-1 p-2.5 align-top text-[11px] text-slate-700">
      <div className="font-bold text-slate-900">
        {c.drafts} drafts · {c.judged_drafts} graded ({c.passes_per_draft} pass each)
        {c.status === 'partial' && ` · ${c.drafts} of ${c.drafts_planned}`}
      </div>
      <div>
        {c.cost_per_1k_docs_usd != null && `$${c.cost_per_1k_docs_usd.toFixed(2)} / 1k docs · `}
        output {c.output_tokens_mean != null ? Math.round(c.output_tokens_mean).toLocaleString() : '—'} tok
        {c.output_tokens_min != null &&
          c.output_tokens_max != null &&
          ` (${c.output_tokens_min.toLocaleString()}–${c.output_tokens_max.toLocaleString()})`}
      </div>
      <div>
        accuracy {r.factual_accuracy?.toFixed(2) ?? '—'} · coverage {r.coverage?.toFixed(2) ?? '—'} · clarity{' '}
        {r.clarity?.toFixed(2) ?? '—'} · actionability {r.actionability?.toFixed(2) ?? '—'} · concision{' '}
        {r.concision?.toFixed(2) ?? '—'} <span className="text-slate-400">(1–5)</span>
      </div>
      <div>
        serious errors {c.serious_per_draft?.toFixed(2) ?? '—'} / draft · minor {c.minor_per_draft?.toFixed(2) ?? '—'} / draft
      </div>
      <div>
        core facts {frac(c.core_facts)} · detail facts {frac(c.detail_facts)} · numbers not in source {c.not_in_source_numbers}
      </div>
      {c.owner && c.time_window && (
        <div className="text-[10px] text-slate-600">
          Action-plan owners: {c.owner.supported} in source / {c.owner.not_stated} “not stated” / {c.owner.unsupported} not in
          source; time windows: {c.time_window.supported} / {c.time_window.not_stated} / {c.time_window.unsupported}
        </div>
      )}
      {c.truncated > 0 && <div className="text-rose-700">{c.truncated} truncated</div>}
    </td>
  )
}

function h2hText(b: Cat2HeadToHeadBlock | undefined | null): string {
  if (!b) return 'run pending'
  const o = b.overall
  const pc = b.position_consistency
  return `template ${o.template_wins} – unbounded ${o.unbounded_wins} (ties ${o.ties}; ${b.calls} calls; position-consistent ${pc.consistent ?? 0}/${pc.pairs ?? 0})`
}

export function Cat2QualityPanel({ results, portfolio }: Cat2QualityPanelProps) {
  const ok = results.filter((r) => r.status === 'ok')
  const scored = ok.filter((r) => r.quality)
  const cell = (arm: Cat2Arm, m: 'sonnet' | 'haiku') => portfolio?.cells.find((c) => c.arm === arm && c.model_key === m)
  const h2h = portfolio?.head_to_head

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      <div className="border-b border-slate-200 pb-3">
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-emerald-700">
          <ShieldCheck className="h-4 w-4" />
          Draft Quality vs Cost · Graded Blind
        </div>
        <h2 className="mt-0.5 text-lg font-extrabold text-slate-900">Without and With the Section Template, on Both Models</h2>
        <p className="mt-1 max-w-4xl text-xs leading-relaxed text-slate-600">
          Three drafts per version, model and source document ({portfolio?.documents.length ?? 4} documents), graded blind
          by a model that was not one of those under test ({portfolio?.judge_model ?? 'claude-opus-5-5'}), one pass per
          draft. Key facts are checked against a fixed answer key.
        </p>
      </div>

      {portfolio ? (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-left">
            <thead>
              <tr className="border-b border-slate-200 text-[10px] font-bold uppercase text-slate-500">
                <th className="p-2.5" />
                {COLS.map((c) => (
                  <th key={c.key} className="p-2.5">
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row) => (
                <tr key={row.arm} className="border-b border-slate-100">
                  <th
                    className={`w-48 border-l-4 p-2.5 align-top text-xs font-extrabold ${
                      row.arm === 'unbounded' ? 'border-l-rose-500 text-rose-900' : 'border-l-emerald-600 text-emerald-900'
                    }`}
                  >
                    <span className="inline-flex items-start gap-1.5">
                      <DesignMark withLever={row.arm !== 'unbounded'} className="mt-0.5" />
                      {row.label}
                    </span>
                  </th>
                  {COLS.map((c) => (
                    <CellBox key={c.key} c={cell(row.arm, c.key)} />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3 rounded-lg bg-slate-50 p-2.5 text-[11px] text-slate-700 ring-1 ring-slate-200">
            <strong className="text-slate-900">Head-to-head (same document, model and repeat, both orders):</strong>{' '}
            {h2h?.status === 'pending' || !h2h?.all ? (
              'run pending'
            ) : (
              <>
                all {h2hText(h2h.all)}
                {COLS.map((c) => (
                  <span key={c.key}>
                    {' '}
                    · {c.label}: {h2hText(h2h.by_model[c.key])}
                  </span>
                ))}
              </>
            )}
          </div>
        </div>
      ) : (
        <p className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-500 ring-1 ring-slate-200">
          The experiment summary is not available.
        </p>
      )}

      {scored.length > 0 && (
        <div className="mt-5">
          <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">This Document</h3>
          <div className="mt-2 grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
            {scored.map((r) => {
              const q = r.quality as Cat2RungQuality
              return (
                <div
                  key={r.rung_id}
                  className={`space-y-2.5 rounded-xl border border-t-4 border-slate-200 bg-slate-50/60 p-3.5 ${
                    r.rung_id.endsWith('_unbounded') ? 'border-t-rose-500' : 'border-t-emerald-600'
                  }`}
                >
                  <div className="inline-flex items-center gap-1.5 text-xs font-extrabold text-slate-900">
                    <DesignMark withLever={!r.rung_id.endsWith('_unbounded')} />
                    {RUNG_NAME[r.rung_id]}
                  </div>
                  <Stat label="Cost / 1k docs" value={`$${r.finops.cost_per_1k_usd.toFixed(2)}`} />
                  <div className="space-y-1">
                    {q.rubric ? (
                      DIMENSIONS.map((d) => (
                        <GradeBar key={d.key} label={d.label} value={q.rubric?.[d.key]?.mean} barClass={RUNG_BAR[r.rung_id]} />
                      ))
                    ) : (
                      <div className="rounded bg-slate-100 px-2 py-1 text-[10px] text-slate-500">
                        Grades (1–5): {q.judge_unavailable_reason ?? 'not graded'}
                      </div>
                    )}
                  </div>
                  <Stat
                    label="Core facts"
                    value={q.core_facts ? frac(q.core_facts) : 'no answer key'}
                    tone={q.core_facts && q.core_facts.hits < q.core_facts.total ? 'text-rose-700' : undefined}
                  />
                  <Stat
                    label="Serious errors"
                    value={q.serious_errors == null ? 'not graded' : String(q.serious_errors)}
                    tone={q.serious_errors ? 'text-rose-700' : undefined}
                  />
                  {q.numbers && <Stat label="Numbers not found in the source" value={String(q.numbers.not_in_source)} />}
                  {(q.head_to_head ?? []).map((h) => (
                    <ul key={h.opponent} className="space-y-0.5 text-[10px] text-slate-700">
                      {h.results.map((o, i) => (
                        <li key={i}>
                          vs {RUNG_NAME[h.opponent]}, {RUNG_NAME[o.shown_first]} shown first →{' '}
                          <strong className="text-slate-900">{winnerName(o.winner)}</strong>
                        </li>
                      ))}
                    </ul>
                  ))}
                  <SeriousErrors q={q} />
                </div>
              )
            })}
          </div>
        </div>
      )}
    </section>
  )
}
