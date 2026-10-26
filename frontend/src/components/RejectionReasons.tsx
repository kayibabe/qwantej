import { useEffect, useId, useRef, useState } from 'react'
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
    <button ref={triggerRef} type="button" className="rejection-reasons-trigger" aria-haspopup="dialog" onClick={() => setOpen(true)}>
      {label} <span>({items.length})</span>
    </button>
    {open && <div className="modal-overlay rejection-reasons-overlay" onMouseDown={event => { if (event.target === event.currentTarget) setOpen(false) }}>
      <section ref={dialogRef} tabIndex={-1} className="modal rejection-reasons-modal" role="dialog" aria-modal="true" aria-labelledby={titleId} onKeyDown={event => {
        if (event.key !== 'Tab') return
        const controls = dialogRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])')
        if (!controls?.length) { event.preventDefault(); dialogRef.current?.focus(); return }
        const first = controls[0]
        const last = controls[controls.length - 1]
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
      }}>
        <div className="rejection-reasons-heading"><div><h2 className="modal-title" id={titleId}>Why this selection was rejected</h2><p>These checks did not pass for this match.</p></div><button type="button" className="detail-close" onClick={() => setOpen(false)} aria-label="Close rejection reasons">×</button></div>
        <ul className="rejection-reasons-list">{items.map((code, index) => <li key={`${code}-${index}`}>{reasonLabel(code)}</li>)}</ul>
      </section>
    </div>}
  </>
}
