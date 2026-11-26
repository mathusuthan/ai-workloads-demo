import { AlertTriangle, CheckCircle2 } from 'lucide-react'

/**
 * The without/with symbol shown next to every version card's title on all six screens: a warning triangle (rose)
 * for a version without the deck's lever, a tick (emerald) for a version with it. Decorative: the card's badge text
 * already states the design, so the icon is hidden from assistive technology.
 */
export function DesignMark({ withLever, className = '' }: { withLever: boolean; className?: string }) {
  return withLever ? (
    <CheckCircle2 aria-hidden="true" className={`h-4 w-4 shrink-0 text-emerald-600 ${className}`} />
  ) : (
    <AlertTriangle aria-hidden="true" className={`h-4 w-4 shrink-0 text-rose-600 ${className}`} />
  )
}

/** The shared red/green classes for a version card (the convention every screen uses). */
export const DESIGN_THEME = {
  without: {
    border: 'border-rose-300',
    headerBg: 'bg-rose-50',
    badge: 'bg-rose-600 text-white',
    text: 'text-rose-700',
  },
  with: {
    border: 'border-emerald-400 ring-1 ring-emerald-200',
    headerBg: 'bg-emerald-50/90',
    badge: 'bg-emerald-700 text-white',
    text: 'text-emerald-700',
  },
} as const

/** Chart series colours: two shades of one hue per design so the two models stay distinguishable. */
export const DESIGN_SERIES = {
  withoutSonnet: '#e11d48', // rose-600
  withoutHaiku: '#fb7185', // rose-400
  withSonnet: '#047857', // emerald-700
  withHaiku: '#10b981', // emerald-500
} as const
