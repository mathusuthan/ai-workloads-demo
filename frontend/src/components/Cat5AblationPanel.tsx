import { FlaskConical } from 'lucide-react'
import type {
  Cat5AblationArm,
  Cat5AblationBaselineRow,
  Cat5AblationLever,
  Cat5AblationPortfolio,
  Cat5GateDisagreement,
  Cat5RungId,
} from '../types'

interface Cat5AblationPanelProps {
  portfolio: Cat5AblationPortfolio | null | undefined
  /** preset id -> printed invoice number, for the baseline table */
  invoiceNumbers: Record<string, string>
}

const RUNG_LABEL: Record<Cat5RungId, string> = {
  unbounded_sonnet_loop: 'Rung 1',
  bounded_sonnet_cached_gate: 'Rung 2',
  hybrid_haiku_sonnet_governed: 'Rung 3',
}

// Adjacent steps of the ablation, in reading order (the summary may hold more comparisons).
const LEVER_ORDER = ['caching alone', 'narrow query', 'deterministic gate', 'model swap without gate', 'gate + tiering']

const RAW_TOOL_LABEL: Record<string, string> = {
  query_invoice_raw: 'Invoice and invoice lines',
  query_po_raw: 'Purchase order and PO lines',
  query_grn_wms_telemetry: 'Goods receipts with raw warehouse scans',
  query_vendor_audit_history: 'Vendor record and compliance history',
  query_contract_amendments_and_dock_logs: 'Contract amendments and dock logs',
}

const DECISION_LABEL: Record<string, string> = {
  APPROVE_CLEAN: 'approve in full',
  APPROVE_WITH_GST_ESCROW: 'approve, hold the GST in escrow',
  APPROVE_PARTIAL_DEBIT_NOTE: 'approve with a debit note',
  BLOCK_EXCEPTION_HOLD: 'block the payment',
}

function money(x: number | null | undefined): string {
  return x == null ? '—' : `$${x.toFixed(2)}`
}

function inr(x: unknown): string {
  return typeof x === 'number' ? `INR ${x.toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : '—'
}

function signedPct(ratio: number | null | undefined): string {
  if (ratio == null) return '—'
  const p = (ratio - 1) * 100
  if (ratio >= 2) return `×${ratio.toFixed(1)} (+${p.toFixed(0)}%)`
  return `${p > 0 ? '+' : p < 0 ? '−' : '±'}${Math.abs(p).toFixed(0)}%`
}

function num(x: number | null | undefined, digits = 1): string {
  return x == null ? '—' : x.toFixed(digits)
}

function tok(x: number | null | undefined): string {
  return x == null ? '—' : Math.round(x).toLocaleString()
}

function decision(d: unknown): string {
  return typeof d === 'string' ? (DECISION_LABEL[d] ?? d.toLowerCase().replace(/_/g, ' ')) : '—'
}

function VersionsTable({ portfolio }: { portfolio: Cat5AblationPortfolio }) {
  return (
    <div className="mt-2 overflow-x-auto">
      <table className="w-full min-w-[820px] border-collapse text-left text-[11px]">
        <thead>
          <tr className="border-b border-slate-200 text-[10px] uppercase text-slate-500">
            <th className="py-1.5 pr-3 font-bold">Version</th>
            <th className="py-1.5 pr-3 font-bold">What it adds</th>
            <th className="py-1.5 pr-3 text-right font-bold">Correct vouchers</th>
            <th className="py-1.5 pr-3 text-right font-bold">Cost / 1,000 invoices (cold · warm)</th>
            <th className="py-1.5 pr-3 text-right font-bold">Model turns</th>
          </tr>
        </thead>
        <tbody>
          {portfolio.arms.map((a, i) => (
            <tr key={a.arm_id} className="border-b border-slate-100 align-top">
              <td className="py-1.5 pr-3 text-slate-900">
                <span className="font-mono text-slate-400">{i + 1}.</span> <span className="font-bold">{a.label}</span>
                {a.runnable_in_app && a.app_rung_id && (
                  <span className="ml-1.5 rounded bg-teal-100 px-1.5 py-0.5 text-[9px] font-bold uppercase text-teal-800">
                    runnable here · {RUNG_LABEL[a.app_rung_id]}
                  </span>
                )}
              </td>
              <td className="py-1.5 pr-3 text-slate-600">{a.adds}</td>
              <td className={`py-1.5 pr-3 text-right font-mono ${a.exact < a.runs ? 'font-bold text-rose-700' : 'text-slate-900'}`}>
                {a.exact} of {a.runs}
              </td>
              <td className="py-1.5 pr-3 text-right font-mono text-slate-900">
                {money(a.cost_per_1k_cold_usd)} · {money(a.cost_per_1k_warm_usd)}
              </td>
              <td className="py-1.5 pr-3 text-right font-mono text-slate-900">{num(a.turns_mean)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function nonExactSentence(portfolio: Cat5AblationPortfolio, arms: Cat5AblationArm[]): string | null {
  const misses = portfolio.non_exact_runs
  if (misses.length === 0) return 'Every pooled run committed a voucher that matched exactly.'
  const byArm = new Map(arms.map((a) => [a.arm_id, a.label]))
  const parts = misses.map((m) => {
    const label = byArm.get(String(m.arm_id)) ?? 'one version'
    const fields = Array.isArray(m.mismatched_fields) ? m.mismatched_fields.length : 0
    const exp = (m.expected ?? {}) as Record<string, unknown>
    const got = (m.committed ?? {}) as Record<string, unknown>
    const diff =
      typeof exp.authorized_net_principal_inr === 'number' && typeof got.authorized_net_principal_inr === 'number'
        ? `, net principal off by ${inr(Math.abs(exp.authorized_net_principal_inr - got.authorized_net_principal_inr))}`
        : ''
    return `“${label}”: ${fields} amount${fields === 1 ? '' : 's'} did not match on one run${diff}`
  })
  return `Vouchers that did not match: ${parts.join('; ')}.`
}

function LeverTable({ portfolio }: { portfolio: Cat5AblationPortfolio }) {
  const arm = (id: string) => portfolio.arms.find((a) => a.arm_id === id)
  const levers = LEVER_ORDER.map((name) => portfolio.levers.find((l) => l.lever === name && l.available)).filter(
    (l): l is Cat5AblationLever => Boolean(l)
  )
  if (levers.length === 0) return null
  return (
    <div className="mt-5">
      <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">What Each Step Saved</h3>
      <p className="mt-1 max-w-4xl text-[11px] leading-relaxed text-slate-600">
        Each row changes one thing (or one bundle of things) between two of the versions above, on the same invoices.
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[820px] border-collapse text-left text-[11px]">
          <thead>
            <tr className="border-b border-slate-200 text-[10px] uppercase text-slate-500">
              <th className="py-1.5 pr-3 font-bold">Step</th>
              <th className="py-1.5 pr-3 font-bold">From → to</th>
              <th className="py-1.5 pr-3 text-right font-bold">Cost change (cold · warm)</th>
              <th className="py-1.5 pr-3 text-right font-bold">Correct vouchers</th>
              <th className="py-1.5 pr-3 text-right font-bold">Model turns</th>
            </tr>
          </thead>
          <tbody>
            {levers.map((l) => {
              const a = arm(l.from_arm)
              const b = arm(l.to_arm)
              const up = (l.cost_cold_ratio ?? 1) > 1
              return (
                <tr key={l.lever} className="border-b border-slate-100 align-top">
                  <td className="py-1.5 pr-3 font-bold text-slate-900">{l.label}</td>
                  <td className="py-1.5 pr-3 text-slate-600">
                    {a?.label ?? '—'} → {b?.label ?? '—'}
                  </td>
                  <td className={`py-1.5 pr-3 text-right font-mono ${up ? 'font-bold text-rose-700' : 'text-emerald-800'}`}>
                    {signedPct(l.cost_cold_ratio)} · {signedPct(l.cost_warm_ratio)}
                  </td>
                  <td className="py-1.5 pr-3 text-right font-mono text-slate-900">
                    {a && b ? `${a.exact} → ${b.exact} of ${b.runs}` : '—'}
                  </td>
                  <td className="py-1.5 pr-3 text-right font-mono text-slate-900">
                    {a && b ? `${num(a.turns_mean)} → ${num(b.turns_mean)}` : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function GateWrongBox({ gd, arms }: { gd: Cat5GateDisagreement; arms: Cat5AblationArm[] }) {
  const m = gd.manual_truth
  const g = gd.gate_output_truth
  const line = gd.line1 as { qty?: number; po_rate?: number; billed_rate?: number }
  const overNet =
    typeof g.authorized_net_principal_inr === 'number' && typeof m.authorized_net_principal_inr === 'number'
      ? g.authorized_net_principal_inr - m.authorized_net_principal_inr
      : null
  const overGst =
    typeof g.authorized_gst_payout_inr === 'number' && typeof m.authorized_gst_payout_inr === 'number'
      ? g.authorized_gst_payout_inr - m.authorized_gst_payout_inr
      : null
  const bundleNoGate = gd.per_arm.filter((p) => !p.gate_arm && arms.find((a) => a.arm_id === p.arm_id)?.tool_set === 'bundle')
  const bundleAtPo = bundleNoGate.reduce((s, p) => s + (p.line1_rate.po_rate ?? 0), 0)
  const bundleRuns = bundleNoGate.reduce((s, p) => s + p.runs, 0)
  const pctOver =
    line.po_rate && line.billed_rate ? (((line.billed_rate - line.po_rate) / line.po_rate) * 100).toFixed(2) : null
  const fixed = Boolean(gd.gate_fixed_on)
  const afterRuns = gd.after_fix_gate_runs ?? 0
  const afterMatch = gd.after_fix_gate_match_manual ?? 0
  return (
    <div className="mt-5 rounded-xl border border-amber-300 bg-amber-50/60 p-4">
      <h3 className="text-xs font-extrabold uppercase tracking-wider text-amber-900">
        When the Policy Tool {fixed ? 'Was' : 'Is'} Wrong
      </h3>
      <p className="mt-1 text-[11px] leading-relaxed text-slate-800">
        Invoice <span className="font-mono">{gd.invoice_id}</span> bills line 1 at{' '}
        {line.billed_rate != null ? inr(line.billed_rate) : '—'} against a PO rate of{' '}
        {line.po_rate != null ? inr(line.po_rate) : '—'}
        {pctOver ? ` (+${pctOver}%)` : ''}
        {line.qty != null ? ` on ${line.qty.toLocaleString('en-IN')} units` : ''}. The policy manual allows a 1.5% band only
        when the PO says its price floats with an index; this PO does not, so line 1 should be paid at the PO rate.{' '}
        {fixed
          ? 'When the experiment ran, the deterministic policy tool applied the band anyway.'
          : 'The deterministic policy tool applies the band anyway.'}{' '}
        This invoice is kept out of the totals above and reported here.
      </p>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <div className="rounded-lg bg-white p-3 ring-1 ring-slate-200">
          <div className="text-[10px] font-bold uppercase text-slate-500">The manual's answer</div>
          <div className="mt-1 text-[11px] text-slate-800">
            {decision(m.decision)}: net {inr(m.authorized_net_principal_inr)}, GST {inr(m.authorized_gst_payout_inr)}, debit
            note {inr(m.debit_note_deduction_inr)}
          </div>
          <div className="mt-2 font-mono text-[11px] font-bold text-emerald-800">
            Versions without the tool: {gd.no_gate_match_manual} of {gd.no_gate_runs} runs matched it
          </div>
        </div>
        <div className="rounded-lg bg-white p-3 ring-1 ring-rose-200">
          <div className="text-[10px] font-bold uppercase text-slate-500">
            The policy tool's answer{fixed ? ', as recorded before the fix' : ''}
          </div>
          <div className="mt-1 text-[11px] text-slate-800">
            {decision(g.decision)}: net {inr(g.authorized_net_principal_inr)}, GST {inr(g.authorized_gst_payout_inr)}, debit
            note {inr(g.debit_note_deduction_inr)}
          </div>
          <div className="mt-2 font-mono text-[11px] font-bold text-rose-700">
            Versions with the tool: {gd.gate_match_manual} of {gd.gate_runs} matched the manual; {gd.gate_match_gate_output} of{' '}
            {gd.gate_runs} committed the tool's figures
          </div>
        </div>
      </div>
      {overNet != null && overNet > 0 && (
        <p className="mt-2 text-[11px] text-slate-800">
          Following the tool overpays this invoice by {inr(overNet)} of principal
          {overGst != null && overGst > 0 ? ` and ${inr(overGst)} of GST` : ''}.
        </p>
      )}
      {bundleRuns > 0 && (
        <p className="mt-1 text-[10px] leading-relaxed text-slate-600">
          {fixed ? 'When the experiment ran, the narrow query did not return' : 'The narrow query does not return'} the PO's
          currency notes, so versions using it could not read that condition from the data; without the tool they still
          paid line 1 at the PO rate in {bundleAtPo} of {bundleRuns} runs.
        </p>
      )}
      {fixed && (
        <div className="mt-3 rounded-lg bg-white p-3 ring-1 ring-emerald-200">
          <div className="text-[10px] font-bold uppercase text-emerald-800">Fixed since the experiment</div>
          <p className="mt-1 text-[11px] leading-relaxed text-slate-800">
            On {gd.gate_fixed_on} the policy tool was changed to apply the 1.5% band only to index-linked POs, and the
            narrow query now returns the PO's currency notes. Three other gaps the manual covers were fixed at the same
            time (approved freight waivers, GST at each line's own rate, and blocking a duplicate invoice or a frozen
            vendor); none of the recorded invoices touches them.{' '}
            {gd.current_gate_matches_manual
              ? "On this invoice the tool now gives the manual's answer."
              : "On this invoice the tool's answer still differs from the manual's."}{' '}
            {afterRuns > 0
              ? `Re-run with the fixed tool, ${afterMatch} of ${afterRuns} runs of the versions with the tool matched the manual.`
              : 'The versions with the tool have not been re-run on the fixed tool yet; the results above are from before the fix.'}
          </p>
        </div>
      )}
    </div>
  )
}

function BaselineTable({
  rows,
  invoiceNumbers,
}: {
  rows: Cat5AblationBaselineRow[]
  invoiceNumbers: Record<string, string>
}) {
  const ids = Array.from(new Set(rows.map((r) => r.preset_id))).sort()
  const get = (id: string, src: Cat5AblationBaselineRow['source']) => rows.find((r) => r.preset_id === id && r.source === src)
  const cheaper = ids.filter((id) => {
    const s = get(id, 'original_scripted')?.cost_per_1k_billed_usd
    const f = get(id, 'free_choice')?.cost_per_1k_billed_usd
    return s != null && f != null && f < s
  }).length
  if (ids.length === 0) return null
  return (
    <div className="mt-5">
      <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">Old Scripted Rung 1 vs Free-Choice Rung 1</h3>
      <p className="mt-1 max-w-4xl text-[11px] leading-relaxed text-slate-600">
        Rung 1 used to tell the model to run one raw query per turn in a fixed order. It now lets the model choose which
        queries to run, several per turn allowed, exactly as in the experiment. The free-choice loop was cheaper on{' '}
        {cheaper} of {ids.length} invoices.
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left text-[11px]">
          <thead>
            <tr className="border-b border-slate-200 text-[10px] uppercase text-slate-500">
              <th className="py-1.5 pr-3 font-bold">Invoice</th>
              <th className="py-1.5 pr-3 font-bold">Rung 1 version</th>
              <th className="py-1.5 pr-3 text-right font-bold">Runs</th>
              <th className="py-1.5 pr-3 text-right font-bold">Correct</th>
              <th className="py-1.5 pr-3 text-right font-bold">Model turns</th>
              <th className="py-1.5 pr-3 text-right font-bold">Prompt tokens</th>
              <th className="py-1.5 pr-3 text-right font-bold">Cost / 1,000 invoices</th>
            </tr>
          </thead>
          <tbody>
            {ids.flatMap((id) =>
              (['original_scripted', 'free_choice'] as const).map((src, i) => {
                const r = get(id, src)
                if (!r) return null
                return (
                  <tr key={`${id}-${src}`} className={`align-top ${i === 1 ? 'border-b border-slate-200' : ''}`}>
                    <td className="py-1.5 pr-3 font-mono text-slate-800">{i === 0 ? (invoiceNumbers[id] ?? id) : ''}</td>
                    <td className="py-1.5 pr-3 text-slate-700">
                      {src === 'original_scripted' ? 'Scripted, one query per turn' : 'Free choice'}
                    </td>
                    <td className="py-1.5 pr-3 text-right font-mono">{r.runs}</td>
                    <td className="py-1.5 pr-3 text-right font-mono">
                      {r.exact} of {r.runs}
                    </td>
                    <td className="py-1.5 pr-3 text-right font-mono">{num(r.turns_mean)}</td>
                    <td className="py-1.5 pr-3 text-right font-mono">{tok(r.prompt_tokens_mean)}</td>
                    <td className="py-1.5 pr-3 text-right font-mono">{money(r.cost_per_1k_billed_usd)}</td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function RawToolUse({ arms }: { arms: Cat5AblationArm[] }) {
  const raw = arms.filter((a) => a.tool_set === 'raw' && a.runs > 0)
  if (raw.length === 0) return null
  const tools = Object.keys(RAW_TOOL_LABEL).filter((t) => raw.some((a) => t in a.runs_calling_tool))
  const skipped = tools.filter((t) => raw.some((a) => (a.runs_calling_tool[t] ?? 0) < a.runs))
  return (
    <div className="mt-5">
      <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">Which Raw Tables the Model Chose to Read</h3>
      <p className="mt-1 max-w-4xl text-[11px] leading-relaxed text-slate-600">
        In the two raw-table versions the model picks its own lookups.{' '}
        {skipped.length === 0
          ? 'It read every table on every run.'
          : `It skipped only ${skipped.map((t) => RAW_TOOL_LABEL[t].toLowerCase()).join(' and ')} on some runs.`}
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[620px] border-collapse text-left text-[11px]">
          <thead>
            <tr className="border-b border-slate-200 text-[10px] uppercase text-slate-500">
              <th className="py-1.5 pr-3 font-bold">Lookup</th>
              {raw.map((a) => (
                <th key={a.arm_id} className="py-1.5 pr-3 text-right font-bold">
                  {a.label}: runs using it · calls per run
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tools.map((t) => (
              <tr key={t} className="border-b border-slate-100">
                <td className="py-1.5 pr-3 text-slate-800">{RAW_TOOL_LABEL[t]}</td>
                {raw.map((a) => (
                  <td key={a.arm_id} className="py-1.5 pr-3 text-right font-mono">
                    {a.runs_calling_tool[t] ?? 0} of {a.runs} · {num(a.tool_calls_per_run[t], 2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function Cat5AblationPanel({ portfolio, invoiceNumbers }: Cat5AblationPanelProps) {
  const header = (
    <div className="border-b border-slate-200 pb-3">
      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-indigo-700">
        <FlaskConical className="h-4 w-4" />
        Six-Version Experiment · Every Run Kept
      </div>
      <h2 className="mt-0.5 text-lg font-extrabold text-slate-900">Which Change Saved the Money?</h2>
      <p className="mt-1 max-w-4xl text-xs leading-relaxed text-slate-600">
        The three rungs above bundle several changes. The experiment adds them one at a time, from the large model reading
        raw tables to the small model with the policy tool and escalation, and runs each version on the same invoices.
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
  const caps = arms.reduce((s, a) => s + a.cap_hits, 0)
  const gd = portfolio.gate_disagreement.find((g) => g.gate_runs > 0 || g.no_gate_runs > 0)
  const other = portfolio.invoice_count_total - portfolio.invoice_count_pooled
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      {header}

      <div className="mt-4">
        <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">The Six Versions</h3>
        <p className="mt-1 max-w-4xl text-[11px] leading-relaxed text-slate-600">
          {portfolio.runs_per_arm} runs each: {portfolio.invoice_count_pooled} invoices × {portfolio.repeats} runs. “Cold”
          counts writing the cached policy manual on every invoice; “warm” assumes it is already cached. {caps === 0
            ? 'No run reached its turn cap.'
            : `${caps} run${caps === 1 ? '' : 's'} reached a turn cap.`}
        </p>
        <VersionsTable portfolio={portfolio} />
        <p className="mt-1.5 text-[11px] text-slate-700">{nonExactSentence(portfolio, arms)}</p>
      </div>

      <LeverTable portfolio={portfolio} />

      {gd && <GateWrongBox gd={gd} arms={arms} />}

      <BaselineTable rows={portfolio.baseline} invoiceNumbers={invoiceNumbers} />

      <RawToolUse arms={arms} />

      <p className="mt-5 text-[10px] leading-relaxed text-slate-500">
        Method: {portfolio.live_runs_used} live runs: {arms.length} versions × {portfolio.invoice_count_total} invoices ×{' '}
        {portfolio.repeats} runs; vouchers scored field by field against a hand-derived answer; every run kept.
        {other > 0 && ` The totals pool ${portfolio.invoice_count_pooled} invoices; the invoice where the policy tool disagrees with the manual is shown on its own.`}
        {portfolio.superseded_records > 0 &&
          ` ${portfolio.superseded_records} record${portfolio.superseded_records === 1 ? ' was' : 's were'} replaced after a fix to the test harness.`}{' '}
        Every version scored at or near 100%, so these runs cannot show small accuracy differences between them.
      </p>
    </section>
  )
}
