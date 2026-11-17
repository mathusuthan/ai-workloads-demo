import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { KeyRound, Layers, ShieldCheck, Zap } from 'lucide-react'
import type { ArchetypeSpec, CreditShieldCredentials, SystemStatusResponse } from '../types'
import { NativeModal } from './NativeModal'

interface TopNavBarProps {
  archetypes: ArchetypeSpec[]
  creds: CreditShieldCredentials
  onUpdateCreds: (next: CreditShieldCredentials) => void
  systemStatus: SystemStatusResponse | null
}

export function TopNavBar({
  archetypes,
  creds,
  onUpdateCreds,
  systemStatus,
}: TopNavBarProps) {
  const location = useLocation()
  const [shieldOpen, setShieldOpen] = useState(false)
  const [draftCreds, setDraftCreds] = useState<CreditShieldCredentials>(creds)

  const openModal = () => {
    setDraftCreds(creds)
    setShieldOpen(true)
  }

  const applyShield = (e: React.FormEvent) => {
    e.preventDefault()
    onUpdateCreds(draftCreds)
    setShieldOpen(false)
  }

  const hasLiveServerOrByok =
    Boolean(creds.anthropicKey || creds.geminiKey) ||
    Boolean(systemStatus?.server_keys.anthropic_configured && systemStatus?.server_keys.gemini_configured)

  return (
    <header className="sticky top-0 z-30 border-b border-slate-800 bg-slate-950 text-white shadow-sm">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-3">
          <Link to="/" className="flex items-center gap-2.5 text-white hover:opacity-90">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 font-mono text-xs font-bold tracking-tight">
              NM
            </span>
            <div>
              <div className="text-sm font-bold leading-tight tracking-tight">
                NovaMart AI Archetypes Lab
              </div>
              <div className="text-[11px] text-slate-400">
                Calibrated FinOps &amp; Architecture Playbook
              </div>
            </div>
          </Link>
        </div>

        {/* Page navigation uses <nav> + <Link aria-current="page">, never role="tablist" */}
        <nav aria-label="Archetype sections" className="flex items-center gap-1 overflow-x-auto py-0.5">
          <Link
            to="/"
            aria-current={location.pathname === '/' ? 'page' : undefined}
            className={`inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition ${
              location.pathname === '/'
                ? 'bg-slate-800 text-white ring-1 ring-slate-600'
                : 'text-slate-300 hover:bg-slate-900 hover:text-white'
            }`}
          >
            <Layers className="h-3.5 w-3.5" />
            Matrix Home
          </Link>

          {archetypes.map((arch) => {
            const path = `/archetype/${arch.id}`
            const active = location.pathname === path
            const isLive = arch.status === 'live'
            return (
              <Link
                key={arch.id}
                to={path}
                aria-current={active ? 'page' : undefined}
                className={`inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition ${
                  active
                    ? 'bg-blue-600 text-white shadow-sm'
                    : isLive
                      ? 'bg-slate-900 text-blue-300 ring-1 ring-blue-500/40 hover:bg-slate-800'
                      : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
                }`}
              >
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ backgroundColor: arch.color_hex }}
                />
                <span>Cat {arch.id}</span>
                {isLive && (
                  <span className="rounded bg-emerald-500/20 px-1 py-0.2 text-[10px] font-bold uppercase text-emerald-300">
                    Live
                  </span>
                )}
              </Link>
            )
          })}
        </nav>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={openModal}
            className={`inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
              creds.mode === 'live'
                ? 'bg-amber-500/20 text-amber-200 ring-1 ring-amber-400/50 hover:bg-amber-500/30'
                : 'bg-emerald-500/15 text-emerald-200 ring-1 ring-emerald-500/40 hover:bg-emerald-500/25'
            }`}
          >
            {creds.mode === 'live' ? (
              <>
                <Zap className="h-3.5 w-3.5 text-amber-300" />
                <span>Mode: Live API</span>
              </>
            ) : (
              <>
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-300" />
                <span>Verified Replay ($0)</span>
              </>
            )}
            <KeyRound className="h-3 w-3 opacity-75" />
          </button>
        </div>
      </div>

      <NativeModal
        open={shieldOpen}
        onClose={() => setShieldOpen(false)}
        title="Credit Shield & Execution Mode"
        subtitle="Protect your Anthropic & Gemini API budget with Verified Replay ($0) or BYOK"
      >
        <form onSubmit={applyShield} className="space-y-5">
          <fieldset className="space-y-2.5">
            <legend className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Execution Mode
            </legend>
            <div className="grid gap-3 sm:grid-cols-2">
              <label
                className={`cursor-pointer rounded-xl border p-3.5 transition ${
                  draftCreds.mode === 'replay'
                    ? 'border-emerald-500 bg-emerald-50/70 ring-1 ring-emerald-500'
                    : 'border-slate-200 hover:border-slate-300'
                }`}
              >
                <div className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="exec-mode"
                    value="replay"
                    checked={draftCreds.mode === 'replay'}
                    onChange={() => setDraftCreds({ ...draftCreds, mode: 'replay' })}
                    className="accent-emerald-600"
                  />
                  <span className="text-sm font-bold text-slate-900">Verified Replay ($0)</span>
                </div>
                <p className="mt-1.5 text-xs text-slate-600">
                  Plays real captured Anthropic &amp; Gemini Decision traces with exact token counts,
                  latencies, and FinOps math at zero API spend.
                </p>
              </label>

              <label
                className={`cursor-pointer rounded-xl border p-3.5 transition ${
                  draftCreds.mode === 'live'
                    ? 'border-amber-500 bg-amber-50/70 ring-1 ring-amber-500'
                    : 'border-slate-200 hover:border-slate-300'
                }`}
              >
                <div className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="exec-mode"
                    value="live"
                    checked={draftCreds.mode === 'live'}
                    onChange={() => setDraftCreds({ ...draftCreds, mode: 'live' })}
                    className="accent-amber-600"
                  />
                  <span className="text-sm font-bold text-slate-900">Live Provider APIs</span>
                </div>
                <p className="mt-1.5 text-xs text-slate-600">
                  Executes custom payloads live against Claude Sonnet 5.5, Haiku 5.5, and Gemini
                  Decision 1 using server <code>.env</code> keys or your BYOK keys below.
                </p>
              </label>
            </div>
          </fieldset>

          {systemStatus && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5 text-xs text-slate-700">
              <div className="flex flex-wrap items-center justify-between gap-2 font-semibold text-slate-900">
                <span>Server Credit Shield Status</span>
                <span className="font-mono">
                  ${systemStatus.daily_spend_usd.toFixed(4)} / ${systemStatus.daily_budget_usd.toFixed(2)} daily cap
                </span>
              </div>
              <div className="mt-2 flex flex-wrap gap-3">
                <span
                  className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 font-medium ${
                    systemStatus.server_keys.anthropic_configured
                      ? 'bg-emerald-100 text-emerald-800'
                      : 'bg-slate-200 text-slate-700'
                  }`}
                >
                  Anthropic Server Key:{' '}
                  {systemStatus.server_keys.anthropic_configured ? 'Configured (.env)' : 'Not Set'}
                </span>
                <span
                  className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 font-medium ${
                    systemStatus.server_keys.gemini_configured
                      ? 'bg-emerald-100 text-emerald-800'
                      : 'bg-slate-200 text-slate-700'
                  }`}
                >
                  Gemini Server Key:{' '}
                  {systemStatus.server_keys.gemini_configured ? 'Configured (.env)' : 'Not Set'}
                </span>
              </div>
            </div>
          )}

          <div className="space-y-3 border-t border-slate-200 pt-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Optional Browser BYOK Overrides (sessionStorage only)
              </span>
              {!hasLiveServerOrByok && (
                <span className="text-[11px] font-medium text-amber-700">
                  Required for Live API if server keys are absent
                </span>
              )}
            </div>

            <div>
              <label htmlFor="byok-anthropic" className="block text-xs font-semibold text-slate-700">
                Anthropic API Key (overrides server key when set)
              </label>
              <input
                id="byok-anthropic"
                type="password"
                autoComplete="off"
                placeholder="sk-ant-..."
                value={draftCreds.anthropicKey}
                onChange={(e) => setDraftCreds({ ...draftCreds, anthropicKey: e.target.value })}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-xs focus:border-blue-500 focus:outline-none"
              />
            </div>

            <div>
              <label htmlFor="byok-gemini" className="block text-xs font-semibold text-slate-700">
                Gemini API Key (for <code>gemini-decision-1</code>)
              </label>
              <input
                id="byok-gemini"
                type="password"
                autoComplete="off"
                placeholder="AIza..."
                value={draftCreds.geminiKey}
                onChange={(e) => setDraftCreds({ ...draftCreds, geminiKey: e.target.value })}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-xs focus:border-blue-500 focus:outline-none"
              />
            </div>

            {systemStatus?.author_passcode_required && (
              <div>
                <label htmlFor="author-passcode" className="block text-xs font-semibold text-slate-700">
                  Author Passcode (required to unlock server .env budget)
                </label>
                <input
                  id="author-passcode"
                  type="password"
                  autoComplete="off"
                  value={draftCreds.authorPasscode}
                  onChange={(e) => setDraftCreds({ ...draftCreds, authorPasscode: e.target.value })}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-xs focus:border-blue-500 focus:outline-none"
                />
              </div>
            )}
          </div>

          <div className="flex items-center justify-end gap-2.5 border-t border-slate-200 pt-4">
            <button
              type="button"
              onClick={() => setShieldOpen(false)}
              className="rounded-lg border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-blue-700"
            >
              Save Execution Settings
            </button>
          </div>
        </form>
      </NativeModal>
    </header>
  )
}
