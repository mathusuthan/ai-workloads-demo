import { useEffect, useId, useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'

interface NativeModalProps {
  open: boolean
  onClose: () => void
  title: string
  subtitle?: string
  maxWidthClass?: string
  children: ReactNode
}

/**
 * Accessible modal backed by native <dialog> + showModal() + closedby="any" + Safari pointer fallback.
 * Deliberately omits manual role="dialog" / aria-modal per modern-web-guidance `dialog`.
 */
export function NativeModal({
  open,
  onClose,
  title,
  subtitle,
  maxWidthClass = 'max-w-2xl',
  children,
}: NativeModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const titleId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return

    if (open && !dialog.open) {
      dialog.showModal()
    } else if (!open && dialog.open) {
      dialog.close()
    }
  }, [open])

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return

    const handleClose = () => {
      dialog.returnValue = ''
      onClose()
    }

    dialog.addEventListener('close', handleClose)

    // Fallback for browsers (e.g. Safari) lacking <dialog closedby="any">
    let pressedOutside = false
    const isOutside = (e: PointerEvent) => {
      const r = dialog.getBoundingClientRect()
      return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom
    }
    const onPointerDown = (e: PointerEvent) => {
      if ('closedBy' in HTMLDialogElement.prototype) return
      pressedOutside = isOutside(e)
    }
    const onPointerUp = (e: PointerEvent) => {
      if ('closedBy' in HTMLDialogElement.prototype) return
      if (pressedOutside && isOutside(e)) {
        dialog.close()
      }
      pressedOutside = false
    }

    dialog.addEventListener('pointerdown', onPointerDown)
    dialog.addEventListener('pointerup', onPointerUp)
    return () => {
      dialog.removeEventListener('close', handleClose)
      dialog.removeEventListener('pointerdown', onPointerDown)
      dialog.removeEventListener('pointerup', onPointerUp)
    }
  }, [onClose])

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      {...({ closedby: 'any' } as Record<string, string>)}
      className={`m-auto w-[calc(100%-2rem)] ${maxWidthClass} rounded-2xl border border-slate-200 bg-white p-0 text-slate-900 shadow-2xl`}
    >
      <div className="flex items-start justify-between gap-4 border-b border-slate-200 bg-slate-950 px-6 py-4 text-white">
        <div>
          <h2 id={titleId} className="text-base font-bold tracking-tight">
            {title}
          </h2>
          {subtitle && <p className="mt-0.5 text-xs text-slate-300">{subtitle}</p>}
        </div>
        <button
          type="button"
          onClick={() => dialogRef.current?.close()}
          aria-label="Close modal"
          className="rounded-lg border border-slate-700 bg-slate-900 p-1.5 text-slate-300 transition hover:bg-slate-800 hover:text-white"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="max-h-[78vh] overflow-y-auto px-6 py-5">{children}</div>
    </dialog>
  )
}
