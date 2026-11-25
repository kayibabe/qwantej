import { useEffect, useId, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { reasonLabel } from '../pages/dailyTickets/helpers'

export default function RejectionReasons({ reasons, label = 'View reasons' }: { reasons: string[]; label?: string }) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const dialogRef = useRef<HTMLElement>(null)
  const titleId = useId()
  useEffect(() => {
    if (!open) return
    dialogRef.current?.focus()
    const dismiss = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', dismiss)
    return () => {
      document.removeEventListener('keydown', dismiss)
      triggerRef.current?.focus()
    }
  }, [open])
  const items = reasons.length ? reasons : ['Publication gate did not pass']
  return <>
    <button ref={triggerRef} type="button" className="rejection-reasons-trigger inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-amber-700 hover:text-amber-800 transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}>
      {label} <span className="font-mono tabular-nums">({items.length})</span>
    </button>
    {open && <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-900/60 px-4" onMouseDown={event => { if (event.target === event.currentTarget) setOpen(false) }}>
      <section ref={dialogRef} tabIndex={-1} className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl focus:outline-none" role="dialog" aria-modal="true" aria-labelledby={titleId} onKeyDown={event => {
        if (event.key !== 'Tab') return
        const controls = dialogRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])')
        if (!controls?.length) { event.preventDefault(); dialogRef.current?.focus(); return }
        const first = controls[0]
        const last = controls[controls.length - 1]
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
      }}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-bold tracking-tight text-slate-900" id={titleId}>Why this selection was rejected</h2>
            <p className="mt-1 text-base text-slate-600">These checks did not pass for this match.</p>
          </div>
          <button type="button" className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={() => setOpen(false)} aria-label="Close rejection reasons"><X className="h-5 w-5" aria-hidden="true" /></button>
        </div>
        <ul className="mt-4 space-y-2">{items.map((code, index) => <li key={`${code}-${index}`} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-base leading-relaxed text-slate-700">{reasonLabel(code)}</li>)}</ul>
      </section>
    </div>}
  </>
}
