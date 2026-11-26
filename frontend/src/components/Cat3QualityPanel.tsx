import { ShieldCheck } from 'lucide-react'
import type {
  Cat3Measure,
  Cat3ProbeResult,
  Cat3QualityPortfolio,
  Cat3RungId,
  Cat3RungSummary,
} from '../types'

interface Cat3QualityPanelProps {
  results: Cat3RungSummary[]
  portfolio: Cat3QualityPortfolio | null | undefined
}

const RUNG_SHORT: Record<Cat3RungId, string> = {
  naive_full_history: 'Rung 1 · Full history',
  prefix_cached_history: 'Rung 2 · Cached full history',
  prefix_cached_summarized: 'Rung 3 · Cached + compacted memory',
}

const RUNG_BAR: Record<Cat3RungId, string> = {
  naive_full_history: 'bg-rose-500',
  prefix_cached_history: 'bg-amber-500',
  prefix_cached_summarized: 'bg-emerald-600',
}

function pct(m: Cat3Measure | null | undefined): number | null {
  if (!m || m.total <= 0) return null
  return (m.hits / m.total) * 100
}

function frac(m: Cat3Measure | null | undefined): string {
  return m && m.total > 0 ? `${m.hits}/${m.total}` : 'n/a'
}

function MeasureBar({
  label,
  measure,
  barClass,
  emptyText,
}: {
  label: string
  measure: Cat3Measure | null | undefined
  barClass: string
  emptyText?: string
}) {
  const p = pct(measure)
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 text-[10px] font-bold uppercase text-slate-500">
        <span>{label}</span>
        <span className="font-mono text-[11px] normal-case text-slate-900">
          {p === null ? '—' : `${frac(measure)} · ${p.toFixed(0)}%`}
        </span>
      </div>
      {p === null ? (
        <div className="mt-1 rounded bg-slate-100 px-2 py-1 text-[10px] text-slate-500">
          {emptyText ?? 'Not measured'}
        </div>
      ) : (
        <div
          className="mt-1 h-2.5 w-full overflow-hidden rounded-full bg-slate-100"
          role="img"
          aria-label={`${label}: ${frac(measure)}`}
        >
          <div className={`h-full rounded-full ${barClass}`} style={{ width: `${Math.max(p, 1.5)}%` }} />
        </div>
      )}
    </div>
  )
}

function ProbeCell({ probe }: { probe: Cat3ProbeResult | undefined }) {
  if (!probe) return <span className="text-slate-400">—</span>
  const tone =
    probe.outcome === 'correct'
      ? 'text-emerald-700'
      : probe.outcome === 'declined'
        ? 'text-slate-500'
        : 'text-rose-700'
  const mark = probe.outcome === 'correct' ? '✓' : probe.outcome === 'declined' ? '✗ declined' : '✗ wrong'
  return (
    <details className="group" title={probe.answer}>
      <summary className={`cursor-pointer list-none font-mono text-[11px] font-extrabold ${tone}`}>
        {mark}
        <span className="ml-1 font-sans text-[10px] font-semibold text-slate-400 group-open:hidden">answer</span>
      </summary>
      <p className="mt-1 max-w-xs whitespace-pre-wrap rounded bg-slate-50 p-1.5 text-[10px] leading-snug text-slate-700 ring-1 ring-slate-200">
        {probe.answer || '(empty answer)'}
      </p>
    </details>
  )
}

export function Cat3QualityPanel({ results, portfolio }: Cat3QualityPanelProps) {
  const ok = results.filter((r) => r.status === 'ok')
  const scored = ok.filter((r) => r.quality)
  const maxCost = Math.max(0, ...ok.map((r) => r.cost_per_1k_sessions_usd))

  // Probe rows: union of every rung's probes, in answer-key order of the first rung that has them.
  const probeRows: { key: string; question: string; expected: string; originTurn: number }[] = []
  for (const r of scored) {
    for (const p of r.quality?.probes ?? []) {
      if (!probeRows.some((row) => row.key === p.probe_id)) {
        probeRows.push({ key: p.probe_id, question: p.question, expected: p.expected, originTurn: p.origin_turn })
      }
    }
  }
  const probeReason = scored.find((r) => r.quality?.probes_unavailable_reason)?.quality?.probes_unavailable_reason

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      <div className="border-b border-slate-200 pb-3">
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-emerald-700">
          <ShieldCheck className="h-4 w-4" />
          Answer Quality vs Cost · Scored Against a Fixed Answer Key
        </div>
        <h2 className="mt-0.5 text-lg font-extrabold text-slate-900">What Each Context Strategy Keeps — and What It Leaves Out</h2>
        <p className="mt-1 max-w-4xl text-xs leading-relaxed text-slate-600">
          Every reply is checked for the specific IDs, amounts and dates the answer key expects. After Turn 10, each rung
          is asked six short questions about details from earlier turns. Cost is the full 10-turn session.
        </p>
      </div>

      {scored.length === 0 ? (
        <p className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-500 ring-1 ring-slate-200">
          Quality scores are not available for this run.
        </p>
      ) : (
        <div className="mt-4 grid gap-4 lg:grid-cols-3">
          {ok.map((r) => {
            const q = r.quality
            const pf = portfolio?.rungs.find((x) => x.rung_id === r.rung_id)
            return (
              <div key={r.rung_id} className="space-y-2.5 rounded-xl border border-slate-200 bg-slate-50/60 p-3.5">
                <div className="text-xs font-extrabold text-slate-900">{RUNG_SHORT[r.rung_id]}</div>
                <div>
                  <div className="flex items-baseline justify-between gap-2 text-[10px] font-bold uppercase text-slate-500">
                    <span>Cost / 1k sessions</span>
                    <span className="font-mono text-[11px] text-slate-900">${r.cost_per_1k_sessions_usd.toFixed(2)}</span>
                  </div>
                  <div className="mt-1 h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-slate-500"
                      style={{ width: `${maxCost > 0 ? (r.cost_per_1k_sessions_usd / maxCost) * 100 : 0}%` }}
                    />
                  </div>
                </div>
                {q ? (
                  <>
                    <MeasureBar label="Answers grounded (turns 1–9)" measure={q.turn_recall} barClass={RUNG_BAR[r.rung_id]} />
                    <MeasureBar
                      label="Early details kept in the final summary"
                      measure={q.ledger_by_origin['1-3']}
                      barClass={RUNG_BAR[r.rung_id]}
                    />
                    <MeasureBar
                      label="Recall questions answered"
                      measure={q.probe_accuracy}
                      barClass={RUNG_BAR[r.rung_id]}
                      emptyText={q.probes_unavailable_reason ?? 'Not measured'}
                    />
                    <div className="font-mono text-[10px] text-slate-500">
                      All final-summary details: {frac(q.ledger_recall)}
                    </div>
                  </>
                ) : (
                  <p className="text-[11px] text-slate-500">Not scored for this rung.</p>
                )}
                <div className="border-t border-slate-200 pt-2 text-[10px] leading-snug text-slate-600">
                  {pf && portfolio ? (
                    <>
                      <strong className="text-slate-700">
                        Across all {portfolio.runs} rerun sessions ({pf.runs} on this rung):
                      </strong>{' '}
                      grounded {frac(pf.turn_recall)} · early details {frac(pf.ledger_by_origin['1-3'])} · recall{' '}
                      {frac(pf.probe_accuracy)}
                      {pf.session_billed_per_1k_usd != null && ` · $${pf.session_billed_per_1k_usd.toFixed(2)}/1k sessions`}
                    </>
                  ) : (
                    'Pooled rerun results are not available.'
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {scored.length > 0 && (
        <div className="mt-5">
          <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">
            Recall Questions About Earlier Turns
          </h3>
          {probeRows.length === 0 ? (
            <p className="mt-2 rounded-lg bg-slate-50 p-3 text-xs text-slate-500 ring-1 ring-slate-200">
              {probeReason ?? 'No recall questions were recorded for this run.'}
            </p>
          ) : (
            <div className="mt-2 overflow-x-auto">
              <table className="w-full min-w-[640px] border-collapse text-left text-[11px]">
                <thead>
                  <tr className="border-b border-slate-200 text-[10px] uppercase text-slate-500">
                    <th className="py-1.5 pr-3 font-bold">Question</th>
                    <th className="py-1.5 pr-3 font-bold">Expected</th>
                    {ok.map((r) => (
                      <th key={r.rung_id} className="py-1.5 pr-3 font-bold">
                        {RUNG_SHORT[r.rung_id]}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {probeRows.map((row) => (
                    <tr key={row.key} className="border-b border-slate-100 align-top">
                      <td className="py-2 pr-3 text-slate-800">
                        {row.question}
                        <div className="mt-0.5 font-mono text-[10px] text-slate-400">From turn {row.originTurn}</div>
                      </td>
                      <td className="py-2 pr-3 font-mono text-slate-700">{row.expected}</td>
                      {ok.map((r) => (
                        <td key={r.rung_id} className="py-2 pr-3">
                          {r.quality?.probes ? (
                            <ProbeCell probe={r.quality.probes.find((p) => p.probe_id === row.key)} />
                          ) : (
                            <span className="text-[10px] text-slate-400">Not run</span>
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-1.5 text-[10px] text-slate-500">
                ✓ answered with the expected detail · ✗ declined: the reply said the detail was not available · ✗ wrong:
                the reply gave a different value. Open a cell to read the answer.
              </p>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
