import { useState } from 'react'
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, Cpu, Timer } from 'lucide-react'
import type { RungExecutionResult } from '../types'

interface RungResultCardProps {
  result: RungExecutionResult
  visible: boolean
}

export function RungResultCard({ result, visible }: RungResultCardProps) {
  const [showRawProse, setShowRawProse] = useState(false)

  if (!visible) {
    return (
      <div className="flex min-h-[360px] flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white/70 p-6 text-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-300 border-t-blue-600" />
        <div className="mt-3 text-xs font-bold text-slate-700">{result.rung_title}</div>
        <div className="mt-1 text-[11px] text-slate-500">
          Simulating {result.latency_ms}ms model response...
        </div>
      </div>
    )
  }

  const theme =
    result.rung_id === 'sonnet_naive'
      ? {
          border: 'border-rose-200',
          headerBg: 'bg-rose-50',
          badge: 'bg-rose-600 text-white',
          savingsColor: 'text-rose-700',
          icon: <AlertTriangle className="h-4 w-4 text-rose-600" />,
        }
      : result.rung_id === 'haiku_naive'
        ? {
            border: 'border-amber-300',
            headerBg: 'bg-amber-50/80',
            badge: 'bg-amber-600 text-white',
            savingsColor: 'text-amber-800',
            icon: <AlertTriangle className="h-4 w-4 text-amber-600" />,
          }
        : result.rung_id === 'haiku_calibrated'
          ? {
              border: 'border-blue-300',
              headerBg: 'bg-blue-50/80',
              badge: 'bg-blue-600 text-white',
              savingsColor: 'text-blue-700',
              icon: <CheckCircle2 className="h-4 w-4 text-blue-600" />,
            }
          : {
              border: 'border-indigo-300',
              headerBg: 'bg-indigo-50/80',
              badge: 'bg-indigo-600 text-white',
              savingsColor: 'text-indigo-700',
              icon: <CheckCircle2 className="h-4 w-4 text-indigo-600" />,
            }
  const isSchemaRung = result.rung_id === 'sonnet_calibrated' || result.rung_id === 'haiku_calibrated'

  const f = result.finops

  return (
    <div className={`flex flex-col justify-between rounded-2xl border bg-white shadow-sm ${theme.border}`}>
      <div>
        {/* Card Header */}
        <div className={`rounded-t-2xl border-b border-slate-200/80 px-4 py-3 ${theme.headerBg}`}>
          <div className="flex items-center justify-between gap-2">
            <span className={`rounded-md px-2 py-0.5 text-[10px] font-extrabold uppercase ${theme.badge}`}>
              {result.badge_text}
            </span>
            <span className="inline-flex items-center gap-1 font-mono text-xs font-bold text-slate-700">
              <Timer className="h-3.5 w-3.5 text-slate-400" />
              {result.latency_ms.toLocaleString()} ms
            </span>
          </div>
          <div className="mt-2 flex items-center gap-1.5">
            {theme.icon}
            <h3 className="text-sm font-extrabold text-slate-900">{result.rung_title}</h3>
          </div>
          <div className="mt-0.5 flex items-center gap-1.5 font-mono text-[11px] text-slate-600">
            <Cpu className="h-3 w-3" />
            <span>
              {result.provider} · <strong>{result.model_id}</strong>
            </span>
          </div>
        </div>

        {result.status === 'error' ? (
          <div className="p-4 text-xs text-rose-700">
            <div className="font-bold">Live execution error:</div>
            <p className="mt-1 font-mono text-[11px]">{result.error_message}</p>
          </div>
        ) : (
          <div className="space-y-4 p-4">
            {/* Unit Cost Headline */}
            <div className="grid grid-cols-2 gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3">
              <div>
                <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  Cost / 1,000 Runs
                </div>
                <div className="mt-0.5 font-mono text-xl font-extrabold tabular-nums text-slate-900">
                  ${f.cost_per_1k_usd < 1 ? f.cost_per_1k_usd.toFixed(4) : f.cost_per_1k_usd.toFixed(2)}
                </div>
                <div className={`text-[11px] font-bold ${theme.savingsColor}`}>
                  {result.rung_id === 'sonnet_naive'
                    ? 'Baseline (1.0x)'
                    : `-${result.savings_vs_naive_pct.toFixed(1)}% vs. Sonnet write-up`}
                </div>
              </div>

              <div>
                <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  Monthly @ 100k/mo
                </div>
                <div className="mt-0.5 font-mono text-xl font-extrabold tabular-nums text-slate-900">
                  ${f.monthly_cost_at_100k_usd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <div className="font-mono text-[11px] text-slate-500">
                  In/Out: <strong>{f.io_ratio_label}</strong>
                </div>
              </div>
            </div>

            {/* Token Telemetry Row */}
            <div className="grid grid-cols-3 gap-1.5 text-center font-mono text-[11px]">
              <div className="rounded-lg bg-slate-100 px-2 py-1.5">
                <div className="text-[9px] font-bold text-slate-500">IN TOKENS</div>
                <div className="font-bold tabular-nums text-slate-900">
                  {f.input_tokens.toLocaleString()}
                </div>
              </div>
              <div className="rounded-lg bg-slate-100 px-2 py-1.5">
                <div className="text-[9px] font-bold text-slate-500">OUT TOKENS</div>
                <div
                  className={`font-bold tabular-nums ${
                    f.output_tokens > 200
                      ? 'text-rose-700'
                      : f.output_tokens === 0
                        ? 'text-emerald-700'
                        : 'text-blue-700'
                  }`}
                >
                  {f.output_tokens.toLocaleString()}
                </div>
              </div>
              <div className="rounded-lg bg-slate-100 px-2 py-1.5">
                <div className="text-[9px] font-bold text-slate-500">OUT COST %</div>
                <div className="font-bold tabular-nums text-slate-900">
                  {f.output_cost_share_pct}%
                </div>
              </div>
            </div>

            {/* Ground-Truth Accuracy Evaluation */}
            {result.accuracy && (
              <div className="rounded-xl border border-slate-200 bg-slate-50/90 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-600">
                      Accuracy vs. Ground Truth
                    </span>
                    <span
                      className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-bold ${
                        result.accuracy.schema_valid
                          ? 'bg-emerald-100 text-emerald-800'
                          : 'bg-amber-100 text-amber-900'
                      }`}
                    >
                      {result.accuracy.method === 'reader_model'
                        ? 'Write-up · read by reader model'
                        : 'JSON schema'}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 font-mono text-xs font-extrabold">
                    <span
                      className={
                        result.accuracy.field_accuracy_pct >= 99
                          ? 'text-emerald-700'
                          : result.accuracy.field_accuracy_pct >= 70
                            ? 'text-amber-700'
                            : 'text-rose-700'
                      }
                    >
                      {result.accuracy.matched_count}/{result.accuracy.total_fields} (
                      {result.accuracy.field_accuracy_pct.toFixed(0)}%)
                    </span>
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5 font-mono text-[10px]">
                  {result.accuracy.field_checks.map((fc) => (
                    <span
                      key={fc.field}
                      title={
                        fc.matched
                          ? `${fc.field} matched ground truth (${String(fc.expected)})`
                          : `${fc.field}: predicted ${String(fc.actual ?? 'none')}, expected ${String(fc.expected)}`
                      }
                      className={`rounded px-1.5 py-0.5 font-semibold ${
                        fc.matched
                          ? 'bg-emerald-100/80 text-emerald-900'
                          : 'bg-rose-100 text-rose-900'
                      }`}
                    >
                      {fc.matched ? '✓' : '✗'} {fc.field}: {String(fc.actual ?? 'missing')}
                      {!fc.matched ? ` ≠ ${String(fc.expected)}` : ''}
                    </span>
                  ))}
                </div>
                {result.accuracy.method === 'reader_model' && result.accuracy.method_note && (
                  <p className="mt-2 text-[10px] leading-snug text-slate-500">{result.accuracy.method_note}</p>
                )}
              </div>
            )}
            {!result.accuracy && result.accuracy_note && (
              <div className="rounded-xl border border-slate-200 bg-slate-50/90 p-3 text-[11px] leading-snug text-slate-600">
                <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-600">
                  Accuracy vs. Ground Truth:{' '}
                </span>
                {result.accuracy_note}
              </div>
            )}

            {/* Rung-Specific Payload View */}
            {(result.rung_id === 'sonnet_naive' || result.rung_id === 'haiku_naive') &&
              result.raw_text_preview && (
                <div
                  className={`rounded-xl border p-3 ${
                    result.rung_id === 'sonnet_naive'
                      ? 'border-rose-200 bg-rose-50/40'
                      : 'border-amber-200 bg-amber-50/40'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className={`text-[11px] font-bold ${
                        result.rung_id === 'sonnet_naive' ? 'text-rose-900' : 'text-amber-950'
                      }`}
                    >
                      Write-Up Output ({f.output_tokens.toLocaleString()} tok @{' '}
                      {result.rung_id === 'sonnet_naive' ? '$10/M' : '$0.50/M'} out
                      {result.stop_reason ? ` · stopped: ${result.stop_reason === 'max_tokens' ? 'cut off at the cap' : result.stop_reason}` : ''})
                    </span>
                    <button
                      type="button"
                      onClick={() => setShowRawProse((v) => !v)}
                      className={`inline-flex items-center gap-1 text-[11px] font-bold hover:underline ${
                        result.rung_id === 'sonnet_naive' ? 'text-rose-700' : 'text-amber-800'
                      }`}
                    >
                      {showRawProse ? (
                        <>
                          Hide <ChevronUp className="h-3 w-3" />
                        </>
                      ) : (
                        <>
                          Inspect Write-Up <ChevronDown className="h-3 w-3" />
                        </>
                      )}
                    </button>
                  </div>
                  <pre
                    className={`mt-2 whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-slate-700 ${
                      showRawProse ? 'max-h-72 overflow-y-auto' : 'line-clamp-5'
                    }`}
                  >
                    {result.raw_text_preview}
                  </pre>
                </div>
              )}

            {isSchemaRung && (
              <div className="rounded-xl border border-blue-200 bg-blue-50/30 p-3">
                <div className="text-[11px] font-bold text-blue-900">
                  JSON Schema Output ({f.output_tokens} tok
                  {result.stop_reason ? ` · stopped: ${result.stop_reason === 'max_tokens' ? 'cut off at the cap' : result.stop_reason}` : ''})
                </div>
                <pre className="mt-1.5 overflow-x-auto rounded-lg bg-slate-950 p-2.5 font-mono text-[11px] leading-relaxed text-emerald-300">
                  {JSON.stringify(result.structured_output, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer Notes */}
      <div className="border-t border-slate-100 px-4 py-3 text-[11px] text-slate-600">
        <ul className="space-y-1">
          {result.architectural_notes.map((n, idx) => (
            <li key={idx} className="flex gap-1.5">
              <span className="font-bold text-slate-400">•</span>
              <span>{n}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
