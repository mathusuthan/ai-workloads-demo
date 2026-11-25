import { ShieldCheck } from 'lucide-react'
import type {
  Cat2Count,
  Cat2Dimension,
  Cat2QualityPortfolio,
  Cat2RungId,
  Cat2RungQuality,
  Cat2RungResult,
} from '../types'

interface Cat2QualityPanelProps {
  results: Cat2RungResult[]
  portfolio: Cat2QualityPortfolio | null | undefined
}

const RUNG_SHORT: Record<Cat2RungId, string> = {
  sonnet_unbounded: 'Rung 1 · Unbounded Sonnet 5.5',
  sonnet_templated: 'Rung 2 · Sonnet 5.5 + template',
  haiku_templated: 'Rung 3 · Haiku 5.5 + template',
}

const RUNG_NAME: Record<Cat2RungId, string> = {
  sonnet_unbounded: 'Unbounded',
  sonnet_templated: 'Sonnet template',
  haiku_templated: 'Haiku template',
}

const RUNG_BAR: Record<Cat2RungId, string> = {
  sonnet_unbounded: 'bg-rose-500',
  sonnet_templated: 'bg-amber-500',
  haiku_templated: 'bg-emerald-600',
}

const DIMENSIONS: { key: Cat2Dimension; label: string }[] = [
  { key: 'factual_accuracy', label: 'Accuracy' },
  { key: 'coverage', label: 'Coverage' },
  { key: 'clarity', label: 'Clarity' },
  { key: 'actionability', label: 'Actionability' },
  { key: 'concision', label: 'Concision' },
]

const PAIRS: [Cat2RungId, Cat2RungId][] = [
  ['sonnet_unbounded', 'sonnet_templated'],
  ['sonnet_unbounded', 'haiku_templated'],
  ['sonnet_templated', 'haiku_templated'],
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
              Reported in {e.passes_reporting} of {q.passes ?? 3} grading passes
            </div>
          </li>
        ))}
      </ul>
    </details>
  )
}

export function Cat2QualityPanel({ results, portfolio }: Cat2QualityPanelProps) {
  const ok = results.filter((r) => r.status === 'ok')
  const scored = ok.filter((r) => r.quality)
  const graded = scored.filter((r) => r.quality?.rubric)
  const maxCost = Math.max(0, ...ok.map((r) => r.finops.cost_per_1k_usd))
  const reason = scored.find((r) => r.quality?.judge_unavailable_reason)?.quality?.judge_unavailable_reason
  const byId = Object.fromEntries(ok.map((r) => [r.rung_id, r])) as Partial<Record<Cat2RungId, Cat2RungResult>>
  const pooledWins = portfolio?.pairwise?.overall?.wins
  const nDocs = portfolio?.documents.length ?? 0

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      <div className="border-b border-slate-200 pb-3">
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-emerald-700">
          <ShieldCheck className="h-4 w-4" />
          Draft Quality vs Cost · Graded Blind
        </div>
        <h2 className="mt-0.5 text-lg font-extrabold text-slate-900">What the Cheaper Drafts Gave Up</h2>
        <p className="mt-1 max-w-4xl text-xs leading-relaxed text-slate-600">
          Graded blind by a model that was not one of those under test (Claude Opus 5.5), three passes per draft; one
          draft per version per source document. Key facts are checked against a fixed answer key.
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
                  <Stat label="Cost / 1k docs" value={`$${r.finops.cost_per_1k_usd.toFixed(2)}`} />
                  <div className="mt-1 h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-slate-500"
                      style={{ width: `${maxCost > 0 ? (r.finops.cost_per_1k_usd / maxCost) * 100 : 0}%` }}
                    />
                  </div>
                </div>
                {q ? (
                  <>
                    <div className="space-y-1">
                      {q.rubric ? (
                        DIMENSIONS.map((d) => (
                          <GradeBar
                            key={d.key}
                            label={d.label}
                            value={q.rubric?.[d.key]?.mean}
                            barClass={RUNG_BAR[r.rung_id]}
                          />
                        ))
                      ) : (
                        <div className="rounded bg-slate-100 px-2 py-1 text-[10px] text-slate-500">
                          Grades (1–5): {q.judge_unavailable_reason ?? 'not graded'}
                        </div>
                      )}
                      {q.rubric && <div className="text-right text-[9px] text-slate-400">grade out of 5</div>}
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
                    {q.numbers && (
                      <Stat label="Numbers not found in the source" value={String(q.numbers.not_in_source)} />
                    )}
                    {q.action_items && q.action_items.total > 0 && (
                      <p className="rounded bg-amber-50 px-2 py-1 text-[10px] leading-snug text-amber-900 ring-1 ring-amber-200">
                        The template requires an owner and a time window for every action item. Here the grader flagged
                        an owner or deadline the source does not support in {q.action_items.flagged} of{' '}
                        {q.action_items.total} action items.
                      </p>
                    )}
                    <SeriousErrors q={q} />
                  </>
                ) : (
                  <p className="text-[11px] text-slate-500">Not scored for this version.</p>
                )}
                <div className="border-t border-slate-200 pt-2 text-[10px] leading-snug text-slate-600">
                  {pf && nDocs ? (
                    <>
                      <strong className="text-slate-700">Across all {nDocs} documents:</strong> accuracy{' '}
                      {pf.rubric.factual_accuracy?.mean?.toFixed(2) ?? '—'} · coverage{' '}
                      {pf.rubric.coverage?.mean?.toFixed(2) ?? '—'} · serious errors {pf.serious_errors} · core facts{' '}
                      {frac(pf.core_facts)}
                      {pf.cost_per_1k_docs_usd != null && ` · $${pf.cost_per_1k_docs_usd.toFixed(2)}/1k docs`}
                    </>
                  ) : (
                    'Results across all documents are not available.'
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
            Head-to-Head: Which Draft the Grader Preferred
          </h3>
          <p className="mt-1 text-[10px] text-slate-500">
            Each pair was shown twice, once in each order, so a preference for whichever draft comes first shows up.
          </p>
          <div className="mt-2 grid gap-2 md:grid-cols-3">
            {PAIRS.filter(([x, y]) => byId[x] || byId[y]).map(([x, y]) => {
              const h = (byId[x]?.quality?.head_to_head ?? []).find((e) => e.opponent === y)
                ?? (byId[y]?.quality?.head_to_head ?? []).find((e) => e.opponent === x)
              const xWins = pooledWins?.[x]?.[y]
              const yWins = pooledWins?.[y]?.[x]
              return (
                <div key={`${x}-${y}`} className="rounded-lg bg-slate-50 p-2.5 text-[11px] ring-1 ring-slate-200">
                  <div className="font-extrabold text-slate-900">
                    {RUNG_NAME[x]} vs {RUNG_NAME[y]}
                  </div>
                  {h && graded.length > 0 ? (
                    <ul className="mt-1 space-y-0.5 text-slate-700">
                      {h.results.map((o, i) => (
                        <li key={i}>
                          {RUNG_NAME[o.shown_first]} shown first →{' '}
                          <strong className="text-slate-900">{winnerName(o.winner)}</strong>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-1 text-slate-500">{reason ?? 'Not compared on this run.'}</p>
                  )}
                  {xWins != null && yWins != null && (
                    <div className="mt-1.5 border-t border-slate-200 pt-1 text-[10px] text-slate-600">
                      All {nDocs} documents: {RUNG_NAME[x]} {xWins} – {yWins} {RUNG_NAME[y]}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </section>
  )
}
