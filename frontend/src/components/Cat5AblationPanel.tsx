import { FlaskConical } from 'lucide-react'
import type { Cat5AblationArm, Cat5AblationPortfolio, Cat5RungId } from '../types'

interface Cat5AblationPanelProps {
  portfolio: Cat5AblationPortfolio | null | undefined
  /** preset id -> printed invoice number (kept for the caller's signature) */
  invoiceNumbers?: Record<string, string>
}

const RUNG_LABEL: Record<Cat5RungId, string> = {
  unbounded_sonnet_loop: 'Rung 1',
  bounded_sonnet_cached_gate: 'Rung 2',
  hybrid_haiku_sonnet_governed: 'Rung 3',
  unbounded_haiku_loop: 'Rung 4',
}

const ROWS: { design: Cat5AblationArm['design']; title: string; detail: string }[] = [
  {
    design: 'without',
    title: 'Without',
    detail:
      'Free-choice loop over raw ERP tables; no step budget, no policy tool. On Haiku there is no escalation path: only the policy tool can flag one.',
  },
  {
    design: 'with',
    title: 'With',
    detail:
      '4-step budget + deterministic policy tool. This design also uses one narrow query in place of the raw tables and sends the policy manual as a cached prefix.',
  },
]

const COLUMNS: { key: Cat5AblationArm['model_column']; title: string }[] = [
  { key: 'sonnet', title: 'Sonnet 5.5' },
  { key: 'haiku', title: 'Haiku 5.5' },
]

// Each cell's own model set-up, shown under its numbers.
const CELL_MODEL: Record<string, string> = {
  'without|sonnet': 'Without · Sonnet 5.5',
  'without|haiku': 'Without · Haiku 5.5 (no escalation path)',
  'with|sonnet': 'With · Sonnet 5.5',
  'with|haiku': 'With · Haiku 5.5 first (Sonnet on escalation)',
}

function money(x: number | null | undefined): string {
  return x == null ? '—' : `$${x.toFixed(2)}`
}

function num(x: number | null | undefined, digits = 1): string {
  return x == null ? '—' : x.toFixed(digits)
}

function Cell({ arm }: { arm: Cat5AblationArm | undefined }) {
  if (!arm) {
    return <td className="py-2 pr-3 align-top text-[11px] text-slate-400">—</td>
  }
  const expected = arm.expected_runs || arm.runs
  const model = CELL_MODEL[`${arm.design}|${arm.model_column}`]
  if (arm.runs === 0) {
    return (
      <td className="py-2 pr-3 align-top">
        <div className="text-[10px] font-bold text-slate-500">{model}</div>
        <span className="mt-1 inline-block rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-bold uppercase text-amber-800">
          run pending · {expected} runs
        </span>
      </td>
    )
  }
  return (
    <td className="py-2 pr-3 align-top">
      <div className="text-[10px] font-bold text-slate-500">{model}</div>
      <div className="font-mono text-[11px] text-slate-900">
        <div>
          <span className="font-bold">{arm.exact}</span> of {arm.runs} correct vouchers
          {arm.pending_runs > 0 && (
            <span className="ml-1 rounded bg-amber-100 px-1 py-0.5 text-[9px] font-bold uppercase text-amber-800">
              {arm.pending_runs} of {expected} pending
            </span>
          )}
        </div>
        <div>
          {money(arm.cost_per_1k_cold_usd)} cold · {money(arm.cost_per_1k_warm_usd)} warm per 1,000 invoices
        </div>
        <div>{num(arm.turns_mean)} model turns</div>
        {arm.escalate && (
          <div>
            escalations fired {arm.escalation_fired} of {arm.runs}
          </div>
        )}
      </div>
      {arm.runnable_in_app && arm.app_rung_id && (
        <span className="mt-1 inline-block rounded bg-teal-100 px-1.5 py-0.5 text-[9px] font-bold uppercase text-teal-800">
          runnable here · {RUNG_LABEL[arm.app_rung_id]}
        </span>
      )}
    </td>
  )
}

export function Cat5AblationPanel({ portfolio }: Cat5AblationPanelProps) {
  const header = (
    <div className="border-b border-slate-200 pb-3">
      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-indigo-700">
        <FlaskConical className="h-4 w-4" />
        Experiment · Without and With
      </div>
      <h2 className="mt-0.5 text-lg font-extrabold text-slate-900">Step Budget + Deterministic Policy Tool</h2>
      <p className="mt-1 max-w-4xl text-xs leading-relaxed text-slate-600">
        The deck's improvement for this archetype: a maximum step budget, a deterministic guardrail that computes the
        voucher, and routing to the small model first. Each design ran on Sonnet and on Haiku, on the same invoices.
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
  const arms = portfolio.arms
  const find = (design: Cat5AblationArm['design'], col: Cat5AblationArm['model_column']) =>
    arms.find((a) => a.design === design && a.model_column === col)
  const caps = arms.reduce((s, a) => s + a.cap_hits, 0)
  const pending = arms.reduce((s, a) => s + (a.pending_runs ?? 0), 0)
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      {header}
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-left text-[11px]">
          <thead>
            <tr className="border-b border-slate-200 text-[10px] uppercase text-slate-500">
              <th className="py-1.5 pr-3 font-bold">Design</th>
              {COLUMNS.map((c) => (
                <th key={c.key} className="py-1.5 pr-3 font-bold">
                  {c.title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROWS.map((r) => (
              <tr key={r.design} className="border-b border-slate-100">
                <td className="max-w-[260px] py-2 pr-3 align-top">
                  <div className="font-bold text-slate-900">{r.title}</div>
                  <div className="text-[10px] leading-relaxed text-slate-600">{r.detail}</div>
                </td>
                {COLUMNS.map((c) => (
                  <Cell key={c.key} arm={find(r.design, c.key)} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-[10px] leading-relaxed text-slate-500">
        Method: {portfolio.invoice_count_pooled} invoices × {portfolio.repeats} runs per version; vouchers scored field by
        field against a hand-derived answer. “Cold” counts writing the cached policy manual on every invoice; “warm”
        assumes it is already cached. With the lever, the Haiku-first version switches to Sonnet when the policy tool
        flags a multi-factor dispute; without it, the Haiku version has no policy tool and so no escalation path. {caps === 0 ? 'No run reached its turn cap.' : `${caps} run${caps === 1 ? '' : 's'} reached a turn cap.`}
        {pending > 0 && ` ${pending} runs are not recorded yet; those cells show the runs recorded so far.`}
      </p>
    </section>
  )
}
