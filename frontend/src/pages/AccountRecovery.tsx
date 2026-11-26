import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  confirmEmailVerification,
  confirmPasswordReset,
  requestPasswordReset,
} from '../lib/api'

type Props = { mode: 'reset' | 'verify' }

export default function AccountRecoveryPage({ mode }: Props) {
  const token = new URLSearchParams(window.location.search).get('token') ?? ''
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const verificationStarted = useRef(false)

  useEffect(() => {
    if (mode !== 'verify' || !token || verificationStarted.current) return
    verificationStarted.current = true
    setBusy(true)
    confirmEmailVerification(token)
      .then(() => {
        setMessage('Your email address is verified. You can close this page or sign in.')
        window.history.replaceState({}, '', window.location.pathname)
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : 'Unable to verify the email address')
      })
      .finally(() => setBusy(false))
  }, [mode, token])

  async function requestReset(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      await requestPasswordReset(email)
      setMessage('If an account exists for that email, a reset link has been sent. Check your inbox.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to request a password reset')
    } finally {
      setBusy(false)
    }
  }

  async function resetPassword(event: FormEvent) {
    event.preventDefault()
    if (password !== confirmation) {
      setError('The two passwords do not match.')
      return
    }
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      await confirmPasswordReset(token, password)
      setMessage('Your password has been updated. You can now sign in with the new password.')
      window.history.replaceState({}, '', window.location.pathname)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to reset the password')
    } finally {
      setBusy(false)
    }
  }

  const errorId = 'recovery-error'
  const statusId = 'recovery-status'
  const passwordHintId = 'recovery-password-hint'
  const errorDescription = error ? errorId : undefined
  const statusDescription = message ? statusId : undefined
  const passwordDescription = [errorDescription, statusDescription, passwordHintId].filter(Boolean).join(' ')
  const inputClassName = 'min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base leading-normal text-slate-900 placeholder:text-slate-600 focus:border-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-700/20 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700'
  const labelClassName = 'grid gap-1.5 text-sm font-medium leading-normal text-slate-700'
  const primaryButtonClassName = 'inline-flex min-h-11 items-center justify-center rounded-lg bg-emerald-700 px-4 py-2.5 text-base font-semibold leading-normal text-white transition-colors hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700'
  const textLinkClassName = 'inline-flex min-h-11 w-full items-center justify-center rounded px-2 text-center text-base font-medium leading-normal transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700'

  return (
    <section className="min-h-screen bg-slate-50 px-4 py-10 sm:py-16" aria-labelledby="account-recovery-title">
      <div className="mx-auto w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <a className="inline-flex min-h-11 flex-col justify-center text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" href="/" aria-label="QwantEj home">
          <span className="text-xl font-bold tracking-tight font-display">QwantEj</span>
          <span className="text-sm font-medium leading-normal text-slate-600">Built on evidence, not hunches.</span>
        </a>
        <h2 id="account-recovery-title" className="mt-6 text-2xl font-bold tracking-tight text-slate-900 font-display">
          {mode === 'verify' ? 'Verify your email' : token ? 'Choose a new password' : 'Reset your password'}
        </h2>

        {mode === 'verify' && !token && (
          <p className="mt-2 text-base leading-relaxed text-slate-700">Open the verification link from your email to confirm this address.</p>
        )}

        {mode === 'reset' && !token && (
          <>
            <p className="mt-2 text-base leading-relaxed text-slate-700">Enter the email address for your account and we will send a reset link.</p>
            <form className="mt-6 grid gap-4" onSubmit={requestReset}>
              <label className={labelClassName}>Email<input className={inputClassName} type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} aria-describedby={[errorDescription, statusDescription].filter(Boolean).join(' ') || undefined} required /></label>
              <button className={primaryButtonClassName} type="submit" disabled={busy}>{busy ? 'Sending…' : 'Send reset link'}</button>
            </form>
          </>
        )}

        {mode === 'reset' && token && !message && (
          <form className="mt-6 grid gap-4" onSubmit={resetPassword}>
            <label className={labelClassName}>New password<input className={inputClassName} type="password" autoComplete="new-password" minLength={8} value={password} onChange={event => setPassword(event.target.value)} aria-describedby={passwordDescription} required /></label>
            <label className={labelClassName}>Confirm new password<input className={inputClassName} type="password" autoComplete="new-password" minLength={8} value={confirmation} onChange={event => setConfirmation(event.target.value)} aria-describedby={passwordDescription} required /></label>
            <p id={passwordHintId} className="text-base leading-relaxed text-slate-700">Use at least eight characters in both fields.</p>
            <button className={primaryButtonClassName} type="submit" disabled={busy}>{busy ? 'Updating…' : 'Update password'}</button>
          </form>
        )}

        {error && <div id={errorId} className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-base leading-relaxed text-red-700" role="alert" aria-live="assertive">{error}</div>}
        {message && <div id={statusId} className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-base leading-relaxed text-emerald-800" role="status" aria-live="polite">{message}</div>}
        {message && <a className={`${primaryButtonClassName} mt-4 w-full`} href="/login">Sign in</a>}
        <a className={`${textLinkClassName} mt-2 text-slate-700 hover:text-slate-900`} href="/">Back to home</a>
      </div>
    </section>
  )
}
