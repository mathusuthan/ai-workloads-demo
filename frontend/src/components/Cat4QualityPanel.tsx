import { ShieldCheck } from 'lucide-react'
import type {
  Cat4GraderError,
  Cat4Measure,
  Cat4PortfolioCell,
  Cat4QualityPortfolio,
  Cat4RungId,
  Cat4RungSummary,
} from '../types'

interface Cat4QualityPanelProps {
  results: Cat4RungSummary[]
  portfolio: Cat4QualityPortfolio | null | undefined
  cacheMode: 'cold_deal_room' | 'warm_shared_corpus'
}

const RUNG_SHORT: Record<Cat4RungId, string> = {
  naive_full_corpus: 'Without · Whole corpus, no cache, no citations',
  cached_rerank_hybrid: 'With · Retrieval paired with caching + citations',
}

// Without and with the deck improvement
const VERSIONS: Cat4RungId[] = ['naive_full_corpus', 'cached_rerank_hybrid']

const VERSION_HEAD: Record<Cat4RungId, string> = {
  naive_full_corpus: 'Without',
  cached_rerank_hybrid: 'With',
}

const RUNG_BAR: Record<Cat4RungId, string> = {
  naive_full_corpus: 'bg-rose-500',
  cached_rerank_hybrid: 'bg-emerald-600',
}

function pct(m: Cat4Measure | null | undefined): number | null {
  if (!m || m.total <= 0) return null
  return (m.hits / m.total) * 100
}

function frac(m: Cat4Measure | null | undefined): string {
  return m && m.total > 0 ? `${m.hits}/${m.total}` : '—'
}

function money(x: number | null | undefined, digits = 4): string {
  return x == null ? '—' : `$${x.toFixed(digits)}`
}

function sizeLabel(portfolio: Cat4QualityPortfolio, scale: number): string {
  const docs = portfolio.corpus[String(scale)]?.documents
  return docs ? `${docs} documents` : `corpus ×${scale}`
}

function MeasureBar({
  label,
  measure,
  barClass,
  emptyText,
}: {
  label: string
  measure: Cat4Measure | null | undefined
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
        <div className="mt-1 rounded bg-slate-100 px-2 py-1 text-[10px] text-slate-500">{emptyText ?? 'Not measured'}</div>
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

function SeriousError({ err, question }: { err: Cat4GraderError; question: number }) {
  const absent = err.source_quote.trim().toUpperCase() === 'ABSENT'
  return (
    <li className="rounded-lg bg-white p-2 ring-1 ring-rose-200">
      <div className="text-[10px] font-bold uppercase text-rose-700">Question {question}</div>
      <div className="mt-1 text-[11px] text-slate-800">
        <span className="font-bold text-slate-500">The answer said: </span>“{err.claim_quote}”
      </div>
      <div className="mt-1 text-[11px] text-slate-700">
        <span className="font-bold text-slate-500">Problem: </span>
        {err.problem}
      </div>
      <div className="mt-1 text-[11px] text-slate-700">
        <span className="font-bold text-slate-500">The contract says: </span>
        {absent ? <em>nothing that supports this claim</em> : `“${err.source_quote}”`}
      </div>
    </li>
  )
}

function supplierCell(c: Cat4PortfolioCell, portfolio: Cat4QualityPortfolio): string {
  if (c.distractors_selected) return `${frac(c.distractors_selected)} clauses`
  if (c.scale === 1) return 'none (no other supplier in this corpus)'
  return c.exposure_answers && c.exposure_answers.hits > 0
    ? `all of them (whole ${sizeLabel(portfolio, c.scale)} sent)`
    : '—'
}

function neededCell(c: Cat4PortfolioCell): string {
  if (c.recall_after_rerank) {
    const p = pct(c.recall_after_rerank)
    return `${frac(c.recall_after_rerank)}${p === null ? '' : ` · ${p.toFixed(0)}%`}`
  }
  return 'all (whole corpus sent)'
}

interface RerunRow {
  label: string
  note?: string
  render: (c: Cat4PortfolioCell, portfolio: Cat4QualityPortfolio) => { text: string; sub?: string; alert?: boolean }
}

const RERUN_ROWS: RerunRow[] = [
  {
    label: 'Cost / question',
    note: 'cold session · warm cache',
    render: (c) => ({ text: `${money(c.cost_per_question_billed_usd)} · ${money(c.cost_per_question_warm_usd)}` }),
  },
  { label: 'Key facts stated', render: (c) => ({ text: frac(c.fact_recall) }) },
  {
    label: 'Answers with a serious error',
    render: (c) => ({
      text: c.judged > 0 ? frac(c.answers_with_material_error) : '—',
      sub: c.correctness_mean != null ? `grade ${c.correctness_mean.toFixed(2)}/5` : undefined,
      alert: (c.answers_with_material_error?.hits ?? 0) > 0,
    }),
  },
  { label: 'Needed clauses sent to the answering model', render: (c) => ({ text: neededCell(c) }) },
  { label: "Other suppliers' clauses sent to the answering model", render: (c, p) => ({ text: supplierCell(c, p) }) },
]

export function Cat4QualityPanel({ results, portfolio, cacheMode }: Cat4QualityPanelProps) {
  const ok = results.filter((r) => r.status === 'ok')
  const scored = ok.filter((r) => r.quality)
  const warm = cacheMode === 'warm_shared_corpus'
  const auditCost = (r: Cat4RungSummary) => (warm ? r.cost_per_1k_audits_warm_usd : r.cost_per_1k_audits_cold_usd)
  const maxCost = Math.max(0, ...ok.map(auditCost))
  const questionNumbers = Array.from(
    new Set(scored.flatMap((r) => r.quality?.questions.map((q) => q.question_number) ?? []))
  ).sort((a, b) => a - b)

  const cells = portfolio?.cells ?? []
  const cell = (rung: string, scale: number) => cells.find((c) => c.rung_id === rung && c.scale === scale)
  const scales = portfolio?.scales ?? []
  const versions = VERSIONS.filter((v) => cells.some((c) => c.rung_id === v))

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      <div className="border-b border-slate-200 pb-3">
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-emerald-700">
          <ShieldCheck className="h-4 w-4" />
          Answer Quality vs Cost · Answer Key + Blind Grader
        </div>
        <h2 className="mt-0.5 text-lg font-extrabold text-slate-900">Without vs With: Answer Quality and Cost</h2>
        <p className="mt-1 max-w-4xl text-xs leading-relaxed text-slate-600">
          Each answer is checked for the specific amounts, dates, clauses and parties a fixed answer key expects, and its
          citations are checked against the clauses the question needs. A separate grader model, which never sees which
          version wrote the answer, scored each recorded answer against the contracts and listed any serious errors.
        </p>
      </div>

      {scored.length === 0 ? (
        <p className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-500 ring-1 ring-slate-200">
          {ok.find((r) => r.quality_unavailable_reason)?.quality_unavailable_reason ??
            'Quality scores are not available for this run.'}
        </p>
      ) : (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          {ok.map((r) => {
            const q = r.quality
            const errors = (q?.questions ?? []).flatMap((x) =>
              (x.grader?.material_errors ?? []).map((e) => ({ e, n: x.question_number }))
            )
            return (
              <div key={r.rung_id} className="space-y-2.5 rounded-xl border border-slate-200 bg-slate-50/60 p-3.5">
                <div className="text-xs font-extrabold text-slate-900">{RUNG_SHORT[r.rung_id]}</div>
                <div>
                  <div className="flex items-baseline justify-between gap-2 text-[10px] font-bold uppercase text-slate-500">
                    <span>Cost / 1k audits ({warm ? 'warm cache' : 'cold cache'})</span>
                    <span className="font-mono text-[11px] text-slate-900">${auditCost(r).toFixed(2)}</span>
                  </div>
                  <div className="mt-1 h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-slate-500"
                      style={{ width: `${maxCost > 0 ? (auditCost(r) / maxCost) * 100 : 0}%` }}
                    />
                  </div>
                </div>
                {q ? (
                  <>
                    <MeasureBar label="Key facts stated" measure={q.audit.key_facts} barClass={RUNG_BAR[r.rung_id]} />
                    <MeasureBar
                      label="Citations at the expected clauses"
                      measure={q.audit.citations_at_expected}
                      barClass={RUNG_BAR[r.rung_id]}
                      emptyText="This version is not asked for citations"
                    />
                    {q.audit.retrieval_recall && (
                      <MeasureBar
                        label="Needed clauses among Haiku's picks"
                        measure={q.audit.retrieval_recall}
                        barClass={RUNG_BAR[r.rung_id]}
                      />
                    )}
                    <div className="flex items-baseline justify-between gap-2 text-[10px] font-bold uppercase text-slate-500">
                      <span>Grader's correctness grade</span>
                      <span className="font-mono text-[11px] normal-case text-slate-900">
                        {q.audit.correctness_mean == null ? '—' : `${q.audit.correctness_mean.toFixed(2)} / 5`}
                      </span>
                    </div>
                    {q.audit.judged === 0 ? (
                      <p className="text-[10px] text-slate-500">{q.grader_unavailable_reason ?? 'Not graded.'}</p>
                    ) : errors.length === 0 ? (
                      <p className="text-[11px] font-semibold text-emerald-700">
                        No serious errors in {q.audit.judged} graded answers.
                      </p>
                    ) : (
                      <details className="group rounded-lg bg-rose-50 p-2 ring-1 ring-rose-200">
                        <summary className="cursor-pointer list-none text-[11px] font-extrabold text-rose-800">
                          {errors.length} serious error{errors.length === 1 ? '' : 's'} in {q.audit.answers_with_material_error}/
                          {q.audit.judged} answers
                          <span className="ml-1 font-semibold text-rose-500 group-open:hidden">· show</span>
                        </summary>
                        <ul className="mt-2 space-y-2">
                          {errors.map(({ e, n }, i) => (
                            <SeriousError key={i} err={e} question={n} />
                          ))}
                        </ul>
                      </details>
                    )}
                  </>
                ) : (
                  <p className="text-[11px] text-slate-500">{r.quality_unavailable_reason ?? 'Not scored for this version.'}</p>
                )}
              </div>
            )
          })}
        </div>
      )}

      {scored.length > 0 && questionNumbers.length > 0 && (
        <div className="mt-5 overflow-x-auto">
          <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">Question by Question</h3>
          <table className="mt-2 w-full min-w-[640px] border-collapse text-left text-[11px]">
            <thead>
              <tr className="border-b border-slate-200 text-[10px] uppercase text-slate-500">
                <th className="py-1.5 pr-3 font-bold">Question</th>
                {scored.map((r) => (
                  <th key={r.rung_id} className="py-1.5 pr-3 font-bold">
                    {RUNG_SHORT[r.rung_id]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {questionNumbers.map((n) => (
                <tr key={n} className="border-b border-slate-100 align-top">
                  <td className="py-2 pr-3 font-bold text-slate-800">Q{n}</td>
                  {scored.map((r) => {
                    const x = r.quality?.questions.find((qq) => qq.question_number === n)
                    if (!x) return <td key={r.rung_id} className="py-2 pr-3 text-slate-400">—</td>
                    const serious = x.grader?.material_errors.length ?? 0
                    return (
                      <td key={r.rung_id} className="py-2 pr-3" title={x.missed_facts.length ? `Missed: ${x.missed_facts.join('; ')}` : undefined}>
                        <span className="font-mono font-bold text-slate-900">{frac(x.key_facts)}</span>{' '}
                        <span className="text-slate-500">facts</span>
                        {x.grader && (
                          <span className="ml-2 font-mono text-slate-700">grade {x.grader.correctness}/5</span>
                        )}
                        {serious > 0 && (
                          <span className="ml-2 rounded bg-rose-100 px-1.5 py-0.5 font-bold text-rose-800">
                            {serious} serious
                          </span>
                        )}
                        {x.zero_citations && (
                          <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 font-bold text-slate-700">no citations</span>
                        )}
                        {x.stop_reason && x.stop_reason !== 'end_turn' && (
                          <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 font-bold text-amber-900">
                            stopped: {x.stop_reason}
                          </span>
                        )}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1.5 text-[10px] text-slate-500">Hover a cell to see which expected facts the answer left out.</p>
        </div>
      )}

      <div className="mt-6">
        <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">Rerun Across Corpus Sizes</h3>
        {!portfolio || cells.length === 0 ? (
          <p className="mt-2 rounded-lg bg-slate-50 p-3 text-xs text-slate-500 ring-1 ring-slate-200">
            Pooled rerun results are not available.
          </p>
        ) : (
          <>
            <p className="mt-1 max-w-4xl text-[11px] leading-relaxed text-slate-600">
              The same 8 questions, asked of the {sizeLabel(portfolio, 1)} deal room and of a {sizeLabel(portfolio, 3)}{' '}
              version with two other suppliers' look-alike contracts added. Cost per question is shown for an 8-question
              session that starts with a cold cache, and with the cache already warm.
            </p>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full min-w-[720px] border-collapse text-left text-[11px]">
                <thead>
                  <tr className="text-[10px] uppercase text-slate-500">
                    <th className="py-1.5 pr-3 font-bold" rowSpan={2}>
                      Measure
                    </th>
                    {scales.map((sc) => (
                      <th key={sc} colSpan={versions.length} className="border-l border-slate-200 py-1.5 pl-3 pr-3 text-center font-bold">
                        Corpus {sc}× · {sizeLabel(portfolio, sc)}
                      </th>
                    ))}
                  </tr>
                  <tr className="border-b border-slate-200 text-[10px] uppercase text-slate-500">
                    {scales.flatMap((sc) =>
                      versions.map((v, i) => (
                        <th
                          key={`${sc}-${v}`}
                          className={`py-1.5 pr-3 text-right font-bold ${i === 0 ? 'border-l border-slate-200 pl-3' : ''}`}
                        >
                          {VERSION_HEAD[v]}
                        </th>
                      ))
                    )}
                  </tr>
                </thead>
                <tbody>
                  {RERUN_ROWS.map((row) => (
                    <tr key={row.label} className="border-b border-slate-100 align-top">
                      <td className="py-1.5 pr-3 text-slate-800">
                        <span className="font-bold">{row.label}</span>
                        {row.note && <span className="block text-[10px] font-normal text-slate-500">{row.note}</span>}
                      </td>
                      {scales.flatMap((sc) =>
                        versions.map((v, i) => {
                          const c = cell(v, sc)
                          const out = c ? row.render(c, portfolio) : { text: '—' }
                          return (
                            <td
                              key={`${sc}-${v}`}
                              className={`py-1.5 pr-3 text-right font-mono ${i === 0 ? 'border-l border-slate-200 pl-3' : ''} ${
                                out.alert ? 'font-bold text-rose-700' : 'text-slate-900'
                              }`}
                            >
                              {out.text}
                              {out.sub && <span className="block text-[9px] font-normal text-slate-500">{out.sub}</span>}
                            </td>
                          )
                        })
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
              Without: Sonnet answers from the whole corpus, uncached, with no citations. With: Haiku picks 5 clauses from
              the cached corpus and Sonnet answers over them with citations; because it sees only those clauses, it is told
              to say when a term is not in the text provided.
            </p>
            <p className="mt-3 text-[10px] leading-relaxed text-slate-500">
              Method: {portfolio.answers_scored} answers — {versions.length} versions × {scales.length} corpus sizes ×{' '}
              {portfolio.sessions_per_cell ?? 'several'} sessions of {portfolio.questions_per_session} questions — each
              graded blind{portfolio.judge_passes === 1 ? ' once' : ` ${portfolio.judge_passes} times`} by a model
              not under test{portfolio.judge_model ? ` (${portfolio.judge_model})` : ''}, plus a fixed answer key. Every
              question carried a one-line note naming the supplier under audit.
            </p>
          </>
        )}
      </div>
    </section>
  )
}
