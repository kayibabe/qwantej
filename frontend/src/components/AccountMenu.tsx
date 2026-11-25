import { Fragment, useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { ChevronDown } from 'lucide-react'
import { requestEmailVerification } from '../lib/api'
import { useAuth } from '../auth'

interface Props {
  onRefresh: () => void
  onOpenPalette: () => void
  onUpgrade: () => void
  onSignIn?: () => void
  onSignedOut?: () => void
}

interface MenuItem {
  key: string
  label: string
  onSelect: () => void
  className?: string
  hint?: string
  keepOpen?: boolean
  separatorBefore?: boolean
}

export default function AccountMenu({ onRefresh, onOpenPalette, onUpgrade, onSignIn, onSignedOut }: Props) {
  const { user, loading, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const [verificationSent, setVerificationSent] = useState(false)
  const [activeItem, setActiveItem] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const popoverRef = useRef<HTMLDivElement>(null)
  const menuId = useId()

  useEffect(() => {
    if (!open) return
    setActiveItem(0)
    const onPointerDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false)
    }
    const onEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      setOpen(false)
      triggerRef.current?.focus()
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onEscape)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onEscape)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    popoverRef.current?.querySelector<HTMLElement>('[role^="menuitem"]')?.focus()
  }, [open])

  if (loading) return <span className="text-sm leading-relaxed text-slate-600" role="status">Checking session…</span>
  if (!user) return <button type="button" className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-800 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={onSignIn}>Sign in</button>

  const name = user.username?.trim() || user.email
  const initials = name.slice(0, 1).toUpperCase()

  const itemClass = 'flex min-h-11 w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm leading-5 text-slate-700 transition-colors hover:bg-slate-50 hover:text-slate-900 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700'
  const strongItemClass = 'flex min-h-11 w-full items-center rounded-lg px-3 py-2 text-left text-sm font-semibold leading-5 text-emerald-700 transition-colors hover:bg-emerald-50 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700'
  const signOutClass = 'flex min-h-11 w-full items-center rounded-lg px-3 py-2 text-left text-sm font-medium leading-5 text-red-600 transition-colors hover:bg-red-50 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700'

  const closeAndRun = (action: () => void) => {
    setOpen(false)
    triggerRef.current?.focus()
    action()
  }

  const items: MenuItem[] = []
  if (user.email_verified === false) {
    items.push({
      key: 'verify',
      label: verificationSent ? 'Verification email sent' : 'Send verification email',
      keepOpen: true,
      onSelect: () => { void requestEmailVerification().then(() => setVerificationSent(true)) },
    })
  }
  if (user.plan !== 'pro') {
    items.push({ key: 'upgrade', label: 'Go Premium', className: strongItemClass, onSelect: () => closeAndRun(onUpgrade) })
  }
  items.push({ key: 'palette', label: 'Search or jump to…', hint: '⌘K', separatorBefore: true, onSelect: () => closeAndRun(onOpenPalette) })
  items.push({ key: 'refresh', label: 'Refresh this view', onSelect: () => closeAndRun(onRefresh) })
  items.push({
    key: 'signout',
    label: 'Sign out',
    className: signOutClass,
    separatorBefore: true,
    onSelect: () => { void (async () => { await logout(); onSignedOut?.() })() },
  })

  const safeActive = Math.min(activeItem, items.length - 1)

  const onPopoverKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
    const elements = Array.from(popoverRef.current?.querySelectorAll<HTMLElement>('[role^="menuitem"]') ?? [])
    if (elements.length === 0) return
    event.preventDefault()
    const current = elements.indexOf(document.activeElement as HTMLElement)
    const next = event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? elements.length - 1
        : event.key === 'ArrowDown'
          ? (current + 1 + elements.length) % elements.length
          : (current - 1 + elements.length) % elements.length
    setActiveItem(next)
    elements[next]?.focus()
  }

  return (
    <div className="relative" ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-left transition-colors hover:bg-slate-50 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={`Account menu: ${name}`}
        onClick={() => setOpen(current => !current)}
      >
        <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-emerald-100 text-sm font-bold text-emerald-800" aria-hidden="true">{initials}</span>
        <span className="hidden min-w-0 sm:flex sm:flex-col">
          <strong className="max-w-[10rem] truncate text-sm leading-5 font-semibold text-slate-900">{name}</strong>
          <small className="text-sm leading-5 text-slate-600">{user.plan === 'pro' ? 'Pro plan' : 'Free plan'}{user.role === 'admin' ? ' · Admin' : ''}</small>
        </span>
        <ChevronDown className={`h-4 w-4 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>

      {open && (
        <div ref={popoverRef} id={menuId} className="absolute right-0 top-full z-50 mt-2 w-72 rounded-xl border border-slate-200 bg-white p-2 shadow-lg" role="menu" aria-label="Account and workspace actions" onKeyDown={onPopoverKeyDown}>
          <div className="px-3 py-2" role="group" aria-label="Account details">
            <strong className="block truncate text-sm leading-6 font-semibold text-slate-900">{name}</strong>
            <span className="block truncate text-sm leading-5 text-slate-600">{user.email}</span>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-sm leading-5 font-semibold ${user.plan === 'pro' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-slate-200 bg-slate-50 text-slate-600'}`}>{user.plan === 'pro' ? 'Pro' : 'Free'}</span>
              {user.email_verified === false && <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-sm leading-5 font-semibold text-amber-700">Email unverified</span>}
            </div>
          </div>

          {items.map((item, index) => (
            <Fragment key={item.key}>
              {item.separatorBefore && <div className="my-2 h-px bg-slate-200" role="separator" />}
              <button
                type="button"
                role="menuitem"
                tabIndex={index === safeActive ? 0 : -1}
                className={item.className ?? itemClass}
                onClick={() => {
                  if (item.keepOpen) item.onSelect()
                  else closeAndRun(item.onSelect)
                }}
              >
                <span>{item.label}</span>
                {item.hint && <kbd className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-sm text-slate-600">{item.hint}</kbd>}
              </button>
            </Fragment>
          ))}
        </div>
      )}
    </div>
  )
}
