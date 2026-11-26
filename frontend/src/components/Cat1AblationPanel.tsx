import { FlaskConical } from 'lucide-react'
import type {
  Cat1AblationArm,
  Cat1AblationLever,
  Cat1AblationMiss,
  Cat1AblationPending,
  Cat1AblationPortfolio,
  RungId,
} from '../types'

interface Cat1AblationPanelProps {
  portfolio: Cat1AblationPortfolio | null | undefined
}

const RUNG_LABEL: Record<RungId, string> = {
  sonnet_naive: 'Rung 1A',
  haiku_naive: 'Rung 1B',
  haiku_calibrated: 'Rung 2',
  gemini_decision: 'Rung 3',
}

// Reading order of the comparisons (the summary holds them all).
const LEVER_ORDER = [
  'write-up → classification-only text (sonnet)',
  'write-up → classification-only text (haiku)',
  'text → schema (sonnet)',
  'text → schema (haiku)',
  'Sonnet → Haiku (classify_text)',
  'Sonnet → Haiku (schema)',
  'Haiku schema → Gemini decision',
  'whole stack: Sonnet write-up → Haiku schema',
]

function money(x: number | null | undefined): string {
  if (x == null) return '—'
  return x < 1 ? `$${x.toFixed(3)}` : `$${x.toFixed(2)}`
}

function signed(x: number | null | undefined, unit: string, digits = 0): string {
  if (x == null) return '—'
  if (Math.abs(x) < 0.05) return `±0${unit}`
  return `${x > 0 ? '+' : '−'}${Math.abs(x).toFixed(digits)}${unit}`
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

function isDone(p: Cat1AblationPending | undefined): boolean {
  return Boolean(p && p.pending === 0)
}

function PendingNote({ p }: { p: Cat1AblationPending | undefined }) {
  if (!p || p.pending === 0) return null
  return (
    <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-900">
      {p.done} of {p.planned} done · {p.status}
    </span>
  )
}

function VersionsTable({ portfolio }: { portfolio: Cat1AblationPortfolio }) {
  return (
    <div className="mt-2 overflow-x-auto">
      <table className="w-full min-w-[900px] border-collapse text-left text-[11px]">
        <thead>
          <tr className="border-b border-slate-200 text-[10px] uppercase text-slate-500">
            <th className="py-1.5 pr-3 font-bold">Version</th>
            <th className="py-1.5 pr-3 font-bold">What it is</th>
            <th className="py-1.5 pr-3 text-right font-bold">Fields correct</th>
            <th className="py-1.5 pr-3 text-right font-bold">Items fully correct</th>
            <th className="py-1.5 pr-3 text-right font-bold">Cost / 1,000 items</th>
            <th className="py-1.5 pr-3 text-right font-bold">Output tokens</th>
            <th className="py-1.5 pr-3 text-right font-bold">Response time</th>
          </tr>
        </thead>
        <tbody>
          {portfolio.arms.map((a, i) => (
            <tr key={a.arm_id} className="border-b border-slate-100 align-top">
              <td className="py-1.5 pr-3 text-slate-900">
                <span className="font-mono text-slate-400">{i + 1}.</span> <span className="font-bold">{a.label}</span>
                {!a.given_allowed_labels && <span className="font-bold text-amber-700">*</span>}
                {a.runnable_in_app && a.app_rung_id && (
                  <span className="ml-1.5 rounded bg-teal-100 px-1.5 py-0.5 text-[9px] font-bold uppercase text-teal-800">
                    runnable here · {RUNG_LABEL[a.app_rung_id]}
                  </span>
                )}
              </td>
              <td className="py-1.5 pr-3 text-slate-600">{a.what.replace(/`/g, '')}</td>
              <td
                className={`py-1.5 pr-3 text-right font-mono ${
                  a.fields_correct != null && a.fields_total != null && a.fields_correct < a.fields_total
                    ? 'font-bold text-rose-700'
                    : 'text-slate-900'
                }`}
              >
                {a.fields_correct ?? '—'} of {a.fields_total ?? '—'}
              </td>
              <td className="py-1.5 pr-3 text-right font-mono text-slate-900">
                {a.items_fully_correct ?? '—'} of {a.items}
              </td>
              <td className="py-1.5 pr-3 text-right font-mono text-slate-900">
                {money(a.cost_per_1k_items_usd)}
                {a.batch_cost_per_1k_items_usd_computed != null && (
                  <div className="text-[10px] text-slate-500">
                    Batch API {money(a.batch_cost_per_1k_items_usd_computed)} (computed)
                  </div>
                )}
              </td>
              <td className="py-1.5 pr-3 text-right font-mono text-slate-900">{tok(a.output_tokens_median)}</td>
              <td className="py-1.5 pr-3 text-right font-mono text-slate-900">{seconds(a.latency_ms_median)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function WriteUpNote({ portfolio }: { portfolio: Cat1AblationPortfolio }) {
  const w = portfolio.write_up_note
  const perArm = Object.values(w.ambiguous_fields_per_arm ?? {}).filter((x): x is number => typeof x === 'number')
  const same = perArm.length > 1 && perArm.every((x) => x === perArm[0])
  return (
    <p className="mt-1.5 max-w-4xl text-[11px] leading-relaxed text-slate-700">
      <span className="font-bold text-amber-700">*</span> The write-up versions are today’s prompt, which asks for an
      analysis and never lists the allowed labels. For them, “fields correct” means the write-up is usable as a
      classification: one allowed label could be read off it, and it matched the answer key. It is not a measure of the rest of the
      write-up.{' '}
      {perArm.length > 0 &&
        (same
          ? `For each model, ${perArm[0]} of ${portfolio.fields_per_arm} fields gave several answers or wording that maps to no single label`
          : `${perArm.join(' and ')} of ${portfolio.fields_per_arm} fields gave several answers or wording that maps to no single label`)}
      {w.example_ambiguous ? `, for example “${w.example_ambiguous}”` : ''}
      {perArm.length > 0 ? '.' : ''}
    </p>
  )
}

function leverAccuracy(l: Cat1AblationLever): string {
  if (l.fields_from == null || l.fields_to == null) return '—'
  const base = `${l.fields_from} → ${l.fields_to} of ${l.fields_total}`
  if (!l.comparable_accuracy) return `${base} usable`
  return `${base} (${signed(l.accuracy_change_pp, ' pts', 1)})`
}

function LeverTable({ portfolio }: { portfolio: Cat1AblationPortfolio }) {
  const label = (id: string) => portfolio.arms.find((a) => a.arm_id === id)?.label ?? '—'
  const levers = LEVER_ORDER.map((name) => portfolio.levers.find((l) => l.lever === name)).filter(
    (l): l is Cat1AblationLever => Boolean(l)
  )
  if (levers.length === 0) return null
  return (
    <div className="mt-5">
      <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">What Each Change Did</h3>
      <p className="mt-1 max-w-4xl text-[11px] leading-relaxed text-slate-600">
        Each row changes one thing between two of the versions above, on the same items. Asking for the classification
        instead of a write-up and moving to the smaller model are where the money goes; enforcing the JSON schema costs a
        little more than asking for the same fields as plain text and changes no answer — what it buys is a guaranteed
        format.
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[820px] border-collapse text-left text-[11px]">
          <thead>
            <tr className="border-b border-slate-200 text-[10px] uppercase text-slate-500">
              <th className="py-1.5 pr-3 font-bold">Change</th>
              <th className="py-1.5 pr-3 font-bold">From → to</th>
              <th className="py-1.5 pr-3 text-right font-bold">Cost change</th>
              <th className="py-1.5 pr-3 text-right font-bold">Fields correct</th>
            </tr>
          </thead>
          <tbody>
            {levers.map((l) => {
              const up = (l.cost_change_pct ?? 0) > 0
              return (
                <tr key={l.lever} className={`border-b border-slate-100 align-top ${l.kind === 'whole_stack' ? 'bg-slate-50' : ''}`}>
                  <td className="py-1.5 pr-3 font-bold text-slate-900">{l.label}</td>
                  <td className="py-1.5 pr-3 text-slate-600">
                    {label(l.from_arm)} → {label(l.to_arm)}
                  </td>
                  <td className={`py-1.5 pr-3 text-right font-mono ${up ? 'font-bold text-rose-700' : 'text-emerald-800'}`}>
                    {signed(l.cost_change_pct, '%', 1)}
                  </td>
                  <td className="py-1.5 pr-3 text-right font-mono text-slate-900">{leverAccuracy(l)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-[10px] text-slate-500">
        “usable”: a write-up is on one side, so the two numbers measure different things (see the note above).
      </p>
    </div>
  )
}

function ScoringTable({ portfolio }: { portfolio: Cat1AblationPortfolio }) {
  const rows = portfolio.scoring_comparison
  const orig = portfolio.original_capture.filter((o) => o.keyword_fields_correct != null)
  const pend = portfolio.pending.original_capture_reader
  if (rows.length === 0 && orig.length === 0) return null
  const pct = (k: number | null | undefined, n: number | null | undefined) =>
    k == null || !n ? '—' : `${k} of ${n} (${((k / n) * 100).toFixed(1)}%)`
  return (
    <div className="mt-5">
      <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">How the Old Scoring Compared</h3>
      <p className="mt-1 max-w-4xl text-[11px] leading-relaxed text-slate-600">
        The app used to score free-text answers with a keyword matcher. Here the same answers are read both by that matcher
        and by a reader model. The matcher scored the plain-text classifications too low and the write-ups too high, so the
        app no longer uses it.
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left text-[11px]">
          <thead>
            <tr className="border-b border-slate-200 text-[10px] uppercase text-slate-500">
              <th className="py-1.5 pr-3 font-bold">Answers</th>
              <th className="py-1.5 pr-3 text-right font-bold">Keyword matcher</th>
              <th className="py-1.5 pr-3 text-right font-bold">Reader model</th>
              <th className="py-1.5 pr-3 text-right font-bold">Matcher off by</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.arm_id} className="border-b border-slate-100">
                <td className="py-1.5 pr-3 text-slate-800">{r.label} (this experiment)</td>
                <td className="py-1.5 pr-3 text-right font-mono">{pct(r.keyword_fields_correct, r.fields_total)}</td>
                <td className="py-1.5 pr-3 text-right font-mono">{pct(r.reader_fields_correct, r.fields_total)}</td>
                <td className="py-1.5 pr-3 text-right font-mono font-bold">{signed(r.difference_pp, ' pts', 1)}</td>
              </tr>
            ))}
            {orig.map((o) => {
              const done = isDone(pend)
              const diff =
                done && o.keyword_field_accuracy_pct != null && o.reader_field_accuracy_pct != null
                  ? o.keyword_field_accuracy_pct - o.reader_field_accuracy_pct
                  : null
              const label = portfolio.arms.find((a) => a.arm_id === o.arm_id)?.label ?? o.arm_id
              return (
                <tr key={o.arm_id} className="border-b border-slate-100">
                  <td className="py-1.5 pr-3 text-slate-800">
                    {label}, first capture ({o.responses} stored, {o.truncated_at_cap} cut off at {o.cap?.toLocaleString()} tokens)
                  </td>
                  <td className="py-1.5 pr-3 text-right font-mono">{pct(o.keyword_fields_correct, o.fields_total)}</td>
                  <td className="py-1.5 pr-3 text-right font-mono">
                    {done ? pct(o.reader_fields_correct, o.fields_total) : <PendingNote p={pend} />}
                  </td>
                  <td className="py-1.5 pr-3 text-right font-mono font-bold">{signed(diff, ' pts', 1)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function MissList({ portfolio }: { portfolio: Cat1AblationPortfolio }) {
  const arm = (id: string): Cat1AblationArm | undefined => portfolio.arms.find((a) => a.arm_id === id)
  const groups = new Map<string, Cat1AblationMiss[]>()
  for (const m of portfolio.misses) {
    const key = `${m.arm_id}|${m.item_id}`
    groups.set(key, [...(groups.get(key) ?? []), m])
  }
  const small = Array.from(groups.values()).filter((g) => arm(g[0].arm_id)?.model === 'Haiku 5.5')
  const gemini = Array.from(groups.values()).filter((g) => g[0].arm_id === 'gemini_decision')
  const sonnet = Array.from(groups.values()).filter((g) => arm(g[0].arm_id)?.model === 'Sonnet 5.5')
  const line = (g: Cat1AblationMiss[]) => {
    const runs = Math.max(...g.map((m) => m.runs_missed))
    const fields = g.map((m) => `${m.field_label} “${plain(m.returned)}” instead of “${plain(m.expected)}”`).join('; ')
    return `${fields} — ${runs} of ${g[0].runs_total} runs`
  }
  return (
    <div className="mt-5 grid gap-3 md:grid-cols-2">
      <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3">
        <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">Where the Haiku Versions Did Not Match</h3>
        {small.length === 0 ? (
          <p className="mt-1 text-[11px] text-slate-700">The Haiku versions matched every field.</p>
        ) : (
          <ul className="mt-1.5 space-y-1.5 text-[11px] leading-relaxed text-slate-800">
            {small.map((g) => (
              <li key={`${g[0].arm_id}${g[0].item_id}`}>
                <span className="font-bold">{g[0].item_title}</span>{' '}
                <span className="text-slate-500">({arm(g[0].arm_id)?.label})</span>: {line(g)}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-1.5 text-[10px] text-slate-500">
          {sonnet.length === 0
            ? 'The Sonnet classification versions matched every field on every run.'
            : `The Sonnet classification versions did not match on ${sonnet.length} item${sonnet.length === 1 ? '' : 's'}.`}
        </p>
      </div>
      <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3">
        <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">Gemini Decision</h3>
        {gemini.length === 0 ? (
          <p className="mt-1 text-[11px] text-slate-700">The Gemini version matched every field.</p>
        ) : (
          <ul className="mt-1.5 space-y-1.5 text-[11px] leading-relaxed text-slate-800">
            {gemini.map((g) => (
              <li key={g[0].item_id}>
                <span className="font-bold">{g[0].item_title}</span>: {line(g)}
                {g.every((m) => m.runs_missed === m.runs_total) ? ' (the same answer every time)' : ''}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-1.5 text-[10px] text-slate-500">
          The Gemini version answers its own fixed questions, which differ from the JSON schema: priority comes from a 0–3 severity score.
          Its price is the repo’s rate card, not a verified one.
        </p>
      </div>
    </div>
  )
}

export function Cat1AblationPanel({ portfolio }: Cat1AblationPanelProps) {
  const header = (
    <div className="border-b border-slate-200 pb-3">
      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-indigo-700">
        <FlaskConical className="h-4 w-4" />
        Seven-Version Experiment · Every Run Kept
      </div>
      <h2 className="mt-0.5 text-lg font-extrabold text-slate-900">Where Does the Saving Come From?</h2>
      <p className="mt-1 max-w-4xl text-xs leading-relaxed text-slate-600">
        The rungs above change several things at once: the model, the task (a write-up or just the classification) and the
        answer format. The experiment changes them one at a time on the same twelve items.
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
  const dq = portfolio.data_quality
  const check = portfolio.pending.schema_as_text_check
  const readable = portfolio.classification_text_readable
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      {header}

      <div className="mt-4">
        <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">The Seven Versions</h3>
        <p className="mt-1 max-w-4xl text-[11px] leading-relaxed text-slate-600">
          {portfolio.runs_per_arm} runs each ({portfolio.items} items × {portfolio.repeats} runs), {portfolio.fields_per_arm}{' '}
          scored fields per version. Cost per 1,000 items at the app’s rate card; output tokens and response time are medians.
        </p>
        <VersionsTable portfolio={portfolio} />
        <WriteUpNote portfolio={portfolio} />
        {readable.answers ? (
          <p className="mt-1 max-w-4xl text-[11px] text-slate-700">
            Plain-text classification answers: {readable.every_field_stated} of {readable.answers} stated every field with an
            allowed label.{' '}
            {check && isDone(check) && check.fields
              ? `Check on the reader model: ${check.done} JSON answers rewritten as plain text were read back with ${check.fields_agree} of ${check.fields} fields matching.`
              : null}
            {check && check.pending > 0 ? (
              <>
                Reader-model check on JSON answers rewritten as plain text: <PendingNote p={check} />
              </>
            ) : null}
          </p>
        ) : null}
      </div>

      <LeverTable portfolio={portfolio} />

      <ScoringTable portfolio={portfolio} />

      <MissList portfolio={portfolio} />

      <p className="mt-5 text-[10px] leading-relaxed text-slate-500">
        Method: {portfolio.ok_runs} live runs ({portfolio.arms.length} versions × {portfolio.items} items × {portfolio.repeats}{' '}
        runs); every run kept. Free-text answers were read by a model that was not under test and never saw the right answer
        ({portfolio.reader_passes} pass), and compared with the ground truth like a JSON answer.{' '}
        {dq.truncated === 0 ? 'No answer was cut off.' : `${dq.truncated} answers were cut off at their cap and are kept.`}{' '}
        {dq.gemini_ok != null && dq.gemini_planned != null && dq.gemini_ok < dq.gemini_planned
          ? `Gemini answered ${dq.gemini_ok} of ${dq.gemini_planned} runs. `
          : ''}
        The Batch API price is computed at 50% of the live price, not run. With twelve items, small differences between
        versions are indicative only.
      </p>
    </section>
  )
}
