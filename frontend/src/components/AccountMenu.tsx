import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { requestEmailVerification } from '../lib/api'
import { useAuth } from '../auth'

export type ThemePreference = 'system' | 'light' | 'dark'

const THEMES: { value: ThemePreference; label: string }[] = [
  { value: 'system', label: 'Auto' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
]

interface Props {
  theme: ThemePreference
  onThemeChange: (theme: ThemePreference) => void
  onRefresh: () => void
  onOpenPalette: () => void
  onUpgrade: () => void
  onSignIn?: () => void
  onSignedOut?: () => void
}

export default function AccountMenu({ theme, onThemeChange, onRefresh, onOpenPalette, onUpgrade, onSignIn, onSignedOut }: Props) {
  const { user, loading, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const [verificationSent, setVerificationSent] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const popoverRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false)
    }
    const onEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== 'Escape') return
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

  if (loading) return <span className="shell-account-loading" role="status">Checking session…</span>
  if (!user) return <button type="button" className="shell-signin" onClick={onSignIn}>Sign in</button>

  const name = user.username?.trim() || user.email
  const initials = name.slice(0, 1).toUpperCase()

  const onPopoverKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
    const items = Array.from(popoverRef.current?.querySelectorAll<HTMLElement>('[role^="menuitem"]') ?? [])
    if (items.length === 0) return
    event.preventDefault()
    const current = items.indexOf(document.activeElement as HTMLElement)
    const next = event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? items.length - 1
        : event.key === 'ArrowDown'
          ? (current + 1 + items.length) % items.length
          : (current - 1 + items.length) % items.length
    items[next]?.focus()
  }

  const closeAndRun = (action: () => void) => {
    setOpen(false)
    action()
  }

  return (
    <div className="account-menu" ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className="account-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account menu: ${name}`}
        onClick={() => setOpen(current => !current)}
      >
        <span className="account-avatar" aria-hidden="true">{initials}</span>
        <span className="account-identity">
          <strong>{name}</strong>
          <small>{user.plan === 'pro' ? 'Pro plan' : 'Free plan'}{user.role === 'admin' ? ' · Admin' : ''}</small>
        </span>
        <span className="account-chevron" aria-hidden="true">⌄</span>
      </button>

      {open && (
        <div ref={popoverRef} className="account-popover" role="menu" aria-label="Account and workspace actions" onKeyDown={onPopoverKeyDown}>
          <div className="account-summary">
            <strong>{name}</strong>
            <span>{user.email}</span>
            <div className="account-badges">
              <span className={`account-plan account-plan-${user.plan}`}>{user.plan === 'pro' ? 'Pro' : 'Free'}</span>
              {user.email_verified === false && <span className="account-unverified">Email unverified</span>}
            </div>
          </div>

          {user.email_verified === false && (
            <button
              type="button"
              role="menuitem"
              className="account-item"
              onClick={async () => {
                await requestEmailVerification()
                setVerificationSent(true)
              }}
            >
              {verificationSent ? 'Verification email sent' : 'Send verification email'}
            </button>
          )}

          {user.plan !== 'pro' && (
            <button type="button" role="menuitem" className="account-item account-item-accent" onClick={() => closeAndRun(onUpgrade)}>
              Go Premium
            </button>
          )}

          <div className="account-theme" role="group" aria-label="Theme">
            <span className="account-theme-label">Theme</span>
            <div className="account-segmented">
              {THEMES.map(option => (
                <button
                  key={option.value}
                  type="button"
                  role="menuitemradio"
                  aria-checked={theme === option.value}
                  className={theme === option.value ? 'active' : ''}
                  onClick={() => onThemeChange(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <div className="account-divider" role="separator" />
          <button type="button" role="menuitem" className="account-item" onClick={() => closeAndRun(onOpenPalette)}>
            Search or jump to…
            <kbd>⌘K</kbd>
          </button>
          <button type="button" role="menuitem" className="account-item" onClick={() => closeAndRun(onRefresh)}>
            Refresh this view
          </button>
          <div className="account-divider" role="separator" />
          <button
            type="button"
            role="menuitem"
            className="account-item account-signout"
            onClick={async () => {
              setOpen(false)
              await logout()
              onSignedOut?.()
            }}
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}
