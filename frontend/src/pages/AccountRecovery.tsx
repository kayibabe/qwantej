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

  return (
    <section className="auth-page" aria-labelledby="account-recovery-title">
      <div className="auth-card">
        <div className="auth-card-body">
          <div className="auth-form-panel">
            <a className="auth-card-brand" href="/" aria-label="QwanEj home">
              <picture>
                <source media="(prefers-color-scheme: dark)" srcSet="/dark/logo.png?v=qwanej-1" />
                <img src="/light/logo.png?v=qwanej-1" alt="QwanEj — Intelligence beyond numbers" />
              </picture>
            </a>
            <h2 id="account-recovery-title">
              {mode === 'verify' ? 'Verify your email' : token ? 'Choose a new password' : 'Reset your password'}
            </h2>

            {mode === 'verify' && !token && (
              <p>Open the verification link from your email to confirm this address.</p>
            )}

            {mode === 'reset' && !token && (
              <>
                <p>Enter the email address for your account and we will send a reset link.</p>
                <form onSubmit={requestReset}>
                  <label>Email<input type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} required /></label>
                  <button className="btn-primary" type="submit" disabled={busy}>{busy ? 'Sending…' : 'Send reset link'}</button>
                </form>
              </>
            )}

            {mode === 'reset' && token && !message && (
              <form onSubmit={resetPassword}>
                <label>New password<input type="password" autoComplete="new-password" minLength={8} value={password} onChange={event => setPassword(event.target.value)} required /></label>
                <label>Confirm new password<input type="password" autoComplete="new-password" minLength={8} value={confirmation} onChange={event => setConfirmation(event.target.value)} required /></label>
                <button className="btn-primary" type="submit" disabled={busy}>{busy ? 'Updating…' : 'Update password'}</button>
              </form>
            )}

            {error && <div className="auth-error" role="alert" aria-live="assertive">{error}</div>}
            {message && <div className="auth-status" role="status" aria-live="polite">{message}</div>}
            {message && <a className="btn-primary" href="/login">Sign in</a>}
            <a className="auth-home-link" href="/">Back to home</a>
          </div>
        </div>
      </div>
    </section>
  )
}
