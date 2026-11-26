import { FlaskConical } from 'lucide-react'
import type { Cat2FixActionItem, Cat2FixHeadToHead, Cat2TemplateFix, Cat2TemplateFixCell } from '../types'

interface Cat2TemplateFixPanelProps {
  fix: Cat2TemplateFix | null | undefined
}

const MODEL_NAME: Record<string, string> = { sonnet: 'Sonnet 5.5', haiku: 'Haiku 5.5' }

const DOC_NAME: Record<string, string> = {
  'brief-01': 'the Diwali war-room readout',
  'brief-02': 'the brand-onboarding brief',
  'reg-01': 'the hazmat safety filing',
  'reg-02': 'the cross-border KYC and escrow audit',
}

function n2(v: number | null | undefined): string {
  return v == null ? '—' : v.toFixed(2)
}

function FieldCell({ item, kind }: { item: Cat2FixActionItem; kind: 'owner' | 'window' }) {
  const value = kind === 'owner' ? item.owner : item.time_window
  const cls = kind === 'owner' ? item.owner_class : item.window_class
  const tone =
    cls === 'unsupported' ? 'text-rose-700' : cls === 'not_stated' ? 'italic text-slate-500' : 'text-slate-900'
  const tag = cls === 'unsupported' ? 'not in the source' : cls === 'supported' ? 'in the source' : null
  return (
    <span className={tone}>
      {value || '—'}
      {tag && <span className="ml-1 text-[9px] font-bold uppercase text-slate-400">({tag})</span>}
    </span>
  )
}

function h2hLine(h: Cat2FixHeadToHead): string {
  const a = h.accuracy
  const u = h.usefulness_to_reader
  const ties = (r: { ties: number }) => (r.ties ? ` with ${r.ties} tie${r.ties === 1 ? '' : 's'}` : '')
  return (
    `preferred in ${h.overall.wins} of ${h.calls} comparisons ` +
    `(accuracy ${a.wins}–${a.losses}${ties(a)}; usefulness to the reader ${u.wins}–${u.losses}${ties(u)})`
  )
}

export function Cat2TemplateFixPanel({ fix }: Cat2TemplateFixPanelProps) {
  if (!fix) {
    return (
      <section className="rounded-2xl border border-slate-200 bg-white p-4 text-xs text-slate-500 shadow-sm">
        The measured template fix is not available.
      </section>
    )
  }
  const cell = (arm: string, m: string): Cat2TemplateFixCell | undefined =>
    fix.cells.find((c) => c.arm === arm && c.model_key === m)
  const models = ['sonnet', 'haiku'].filter((m) => cell('template_original', m) && cell('template_not_stated', m))
  const vsOrig = fix.head_to_head.vs_original?.all
  const vsLong = fix.head_to_head.vs_unbounded?.all
  const ex = fix.example
  const c = fix.counts

  // Trade-off 2, computed: documents where the original template's small-model owners were found in the source.
  const hOrig = cell('template_original', 'haiku')
  const hFix = cell('template_not_stated', 'haiku')
  const docsWithSourceOwners = hOrig
    ? Object.values(hOrig.owner_supported_by_preset).filter((v) => v > 0).length
    : 0

  return (
    <section className="rounded-2xl border border-indigo-200 bg-white p-5 shadow-sm sm:p-6">
      <div className="border-b border-slate-200 pb-3">
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-indigo-700">
          <FlaskConical className="h-4 w-4" />
          Measured Fix · Not Used by the App
        </div>
        <h2 className="mt-0.5 text-lg font-extrabold text-slate-900">
          Measured fix: let the template say &ldquo;not stated&rdquo;
        </h2>
        <p className="mt-1 max-w-4xl text-xs leading-relaxed text-slate-600">
          The templated rungs above use the app&rsquo;s original template, which requires an owner and a time window for
          every action item. This follow-up added one sentence to that template and changed nothing else:
        </p>
        <blockquote className="mt-2 max-w-4xl rounded-lg border-l-4 border-indigo-400 bg-indigo-50/60 px-3 py-2 text-xs italic leading-relaxed text-slate-800">
          {fix.added_instruction}
        </blockquote>
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left text-[11px]">
          <thead>
            <tr className="border-b border-slate-200 text-[10px] uppercase text-slate-500">
              <th className="py-1.5 pr-3 font-bold">Model</th>
              <th className="py-1.5 pr-3 font-bold">Template</th>
              <th className="py-1.5 pr-3 text-right font-bold">Serious errors / draft</th>
              <th className="py-1.5 pr-3 text-right font-bold">Accuracy (1–5)</th>
              <th className="py-1.5 pr-3 text-right font-bold">Actionability (1–5)</th>
              <th className="py-1.5 pr-3 text-right font-bold">Owners not in source</th>
              <th className="py-1.5 pr-3 text-right font-bold">Time windows not in source</th>
              <th className="py-1.5 pr-3 text-right font-bold">Cost / 1k docs</th>
            </tr>
          </thead>
          <tbody>
            {models.flatMap((m) =>
              (['template_original', 'template_not_stated'] as const).map((arm) => {
                const x = cell(arm, m)!
                const isFix = arm === 'template_not_stated'
                return (
                  <tr key={`${m}-${arm}`} className={`border-b border-slate-100 ${isFix ? 'bg-indigo-50/40' : ''}`}>
                    <td className="py-1.5 pr-3 font-semibold text-slate-800">{MODEL_NAME[m] ?? m}</td>
                    <td className="py-1.5 pr-3 text-slate-700">{isFix ? '+ the sentence' : 'Original (in the app)'}</td>
                    <td className="py-1.5 pr-3 text-right font-mono">{n2(x.serious_per_draft)}</td>
                    <td className="py-1.5 pr-3 text-right font-mono">{n2(x.rubric.factual_accuracy)}</td>
                    <td className="py-1.5 pr-3 text-right font-mono">{n2(x.rubric.actionability)}</td>
                    <td className="py-1.5 pr-3 text-right font-mono">
                      {x.owner.unsupported}/{x.action_items}
                      {x.owner.not_stated > 0 && (
                        <span className="ml-1 font-sans text-[10px] text-slate-500">({x.owner.not_stated} not stated)</span>
                      )}
                    </td>
                    <td className="py-1.5 pr-3 text-right font-mono">
                      {x.time_window.unsupported}/{x.action_items}
                      {x.time_window.not_stated > 0 && (
                        <span className="ml-1 font-sans text-[10px] text-slate-500">({x.time_window.not_stated} not stated)</span>
                      )}
                    </td>
                    <td className="py-1.5 pr-3 text-right font-mono">
                      {x.cost_per_1k_docs_usd == null ? '—' : `$${x.cost_per_1k_docs_usd.toFixed(2)}`}
                    </td>
                  </tr>
                )
              }),
            )}
          </tbody>
        </table>
      </div>

      <ul className="mt-3 space-y-1 text-xs leading-relaxed text-slate-700">
        {vsOrig && (
          <li>
            <strong className="text-slate-900">Against the original template</strong> (same document, model and draft,
            shown in both orders): the template with the sentence was {h2hLine(vsOrig)}.
          </li>
        )}
        {vsLong && (
          <li>
            <strong className="text-slate-900">Against the long unbounded draft</strong>: it was {h2hLine(vsLong)}. The
            long draft is still the one the grader prefers.
          </li>
        )}
      </ul>

      {ex && ex.items.length > 0 && (
        <div className="mt-4">
          <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">Before / After: Action-Item Owners and Deadlines</h3>
          <p className="mt-0.5 text-[10px] text-slate-500">
            {MODEL_NAME[ex.model_key] ?? ex.model_key}, first of three drafts on {DOC_NAME[ex.preset_id] ?? 'one document'},
            action items in order. Chosen by a fixed rule, not by outcome.
          </p>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-left text-[11px]">
              <thead>
                <tr className="border-b border-slate-200 text-[10px] uppercase text-slate-500">
                  <th className="py-1.5 pr-3 font-bold">Item</th>
                  <th className="py-1.5 pr-3 font-bold">Original template: owner · time window</th>
                  <th className="py-1.5 pr-3 font-bold">With the sentence: owner · time window</th>
                </tr>
              </thead>
              <tbody>
                {ex.items.map((it) => (
                  <tr key={it.slot} className="border-b border-slate-100 align-top">
                    <td className="py-1.5 pr-3 font-mono text-slate-500">{it.slot}</td>
                    <td className="py-1.5 pr-3">
                      <FieldCell item={it.original} kind="owner" /> · <FieldCell item={it.original} kind="window" />
                    </td>
                    <td className="py-1.5 pr-3">
                      <FieldCell item={it.not_stated} kind="owner" /> · <FieldCell item={it.not_stated} kind="window" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="mt-4 rounded-lg bg-amber-50 p-3 text-[11px] leading-relaxed text-amber-950 ring-1 ring-amber-200">
        <div className="font-extrabold uppercase tracking-wider text-amber-800">Trade-offs</div>
        <ul className="mt-1 list-disc space-y-0.5 pl-4">
          <li>
            An honest blank is graded as less actionable: actionability went from{' '}
            {models.map((m, i) => (
              <span key={m}>
                {i > 0 && '; '}
                {n2(cell('template_original', m)?.rubric.actionability)} to {n2(cell('template_not_stated', m)?.rubric.actionability)} (
                {MODEL_NAME[m]})
              </span>
            ))}
            , because the rubric rewards every step having an owner and a deadline.
          </li>
          {hFix && (
            <li>
              The small model wrote &ldquo;not stated&rdquo; for {hFix.owner.not_stated === hFix.action_items ? 'every' : hFix.owner.not_stated} owner
              {hFix.owner.not_stated === hFix.action_items ? '' : 's'} ({hFix.owner.not_stated} of {hFix.action_items}), including on{' '}
              {docsWithSourceOwners} of the {c.documents} documents where its original-template owners were names found in the source.
            </li>
          )}
          <li>
            Fewer source details were carried:{' '}
            {models.map((m, i) => {
              const o = cell('template_original', m)!
              const f = cell('template_not_stated', m)!
              return (
                <span key={m}>
                  {i > 0 && '; '}
                  {o.detail_facts.hits} → {f.detail_facts.hits} of {f.detail_facts.total} detail facts ({MODEL_NAME[m]})
                </span>
              )
            })}
            .
          </li>
        </ul>
      </div>

      <p className="mt-3 text-[10px] leading-relaxed text-slate-500">
        Method: {c.drafts} fresh drafts ({c.drafts_per_document_model_template} per document × model × template, {c.documents}{' '}
        documents), graded blind by a model that was not one of those under test, one pass per draft; owners and time windows
        checked against the source by a fixed rule. The app&rsquo;s own template is still the original one.
      </p>
    </section>
  )
}
