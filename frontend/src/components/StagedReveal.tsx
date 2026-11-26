import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import { DesignMark } from './DesignMark'

/**
 * Staged replay reveal shared by the workbenches (the Archetype 1 pattern: on a replay click the result cards are
 * cleared and then revealed one by one). A replay serves recorded runs only: no model call, no trace, no cost.
 *
 * Usage on a replay *click* (the automatic load on mount stays instant and does not call these):
 *   reveal.begin()                       // hide every card, show "Replaying…", mark the button busy
 *   const resp = await post(...)         // same request as before
 *   setResponse(resp)
 *   reveal.run(['rung_a', 'rung_b'])     // reveal in card order on a short schedule, then announce "done"
 *   (on error: reveal.reset())
 */

const FIRST_DELAY_MS = 250
const STEP_MS = 450
const MAX_TOTAL_MS = 2400

function prefersReducedMotion(): boolean {
  try {
    return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

export interface StagedReveal {
  /** True from the click until the last card is shown. */
  replaying: boolean
  /** Text for the polite live region ('' when idle). */
  status: string
  /** Whether a card (by key) is shown; every card is shown when no replay is in progress. */
  isVisible: (key: string) => boolean
  begin: () => void
  run: (keysInCardOrder: string[]) => void
  reset: () => void
  /** Attach to the results container; a replay click scrolls it into view if it is off screen. */
  resultsRef: RefObject<HTMLDivElement | null>
}

export function useStagedReveal(label = 'versions'): StagedReveal {
  const [hidden, setHidden] = useState<Set<string> | 'all' | null>(null)
  const [replaying, setReplaying] = useState(false)
  const [status, setStatus] = useState('')
  const timers = useRef<number[]>([])
  const resultsRef = useRef<HTMLDivElement | null>(null)

  const clearTimers = () => {
    timers.current.forEach((t) => window.clearTimeout(t))
    timers.current = []
  }
  useEffect(() => clearTimers, [])

  const scrollIntoViewIfNeeded = useCallback(() => {
    const el = resultsRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const vh = window.innerHeight || document.documentElement.clientHeight
    if (r.top < 0 || r.top > vh * 0.6) {
      el.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'start' })
    }
  }, [])

  const begin = useCallback(() => {
    clearTimers()
    setHidden('all')
    setReplaying(true)
    setStatus('Replaying the recorded runs ($0, no model call)…')
    window.setTimeout(scrollIntoViewIfNeeded, 0)
  }, [scrollIntoViewIfNeeded])

  const run = useCallback(
    (keys: string[]) => {
      clearTimers()
      const done = () => {
        setHidden(null)
        setReplaying(false)
        setStatus(`Replay complete: ${keys.length} ${label} shown from recorded runs ($0, no model call).`)
        timers.current.push(window.setTimeout(() => setStatus(''), 6000))
      }
      if (prefersReducedMotion() || keys.length === 0) {
        // no staged reveal; still a brief status
        done()
        window.setTimeout(scrollIntoViewIfNeeded, 0)
        return
      }
      setHidden(new Set(keys))
      window.setTimeout(scrollIntoViewIfNeeded, 0)
      const step = Math.min(STEP_MS, Math.floor((MAX_TOTAL_MS - FIRST_DELAY_MS) / Math.max(1, keys.length - 1)))
      keys.forEach((key, i) => {
        timers.current.push(
          window.setTimeout(() => {
            setHidden((prev) => {
              if (prev === null || prev === 'all') return prev
              const next = new Set(prev)
              next.delete(key)
              return next
            })
            setStatus(`Replaying the recorded runs: ${i + 1} of ${keys.length} ${label} shown…`)
            if (i === keys.length - 1) done()
          }, FIRST_DELAY_MS + i * step)
        )
      })
    },
    [label, scrollIntoViewIfNeeded]
  )

  const reset = useCallback(() => {
    clearTimers()
    setHidden(null)
    setReplaying(false)
    setStatus('')
  }, [])

  const isVisible = useCallback(
    (key: string) => hidden === null || (hidden !== 'all' && !hidden.has(key)),
    [hidden]
  )

  return { replaying, status, isVisible, begin, run, reset, resultsRef }
}

/** Placeholder shown in a card's place while a replay reveals the cards. */
export function RevealPlaceholder({
  title,
  withLever,
  className = '',
}: {
  title?: string
  /** when given, the card's without/with symbol is shown next to the title, as on the card itself */
  withLever?: boolean
  className?: string
}) {
  return (
    <div
      className={`flex min-h-[220px] flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white/70 p-6 text-center ${className}`}
    >
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-300 border-t-blue-600 motion-reduce:animate-none" />
      {title && (
        <div className="mt-3 inline-flex items-center gap-1.5 text-xs font-bold text-slate-700">
          {withLever !== undefined && <DesignMark withLever={withLever} />}
          {title}
        </div>
      )}
      <div className="mt-1 text-[11px] text-slate-500">Replaying the recorded run…</div>
    </div>
  )
}

/** Polite live region announcing the replay state (always rendered so screen readers pick up changes). */
export function ReplayStatus({ status, className = '' }: { status: string; className?: string }) {
  return (
    <p role="status" aria-live="polite" className={`min-h-[1rem] text-[11px] font-semibold text-blue-800 ${className}`}>
      {status}
    </p>
  )
}
