import { useState } from 'react'
import { useAuth } from '../auth'

export default function LoginPage({ onSuccess }: { onSuccess: () => void }) {
  const { login, register, error } = useAuth()
  const [mode, setMode] = useState<'login' | 'register'>(() => new URLSearchParams(window.location.search).get('mode') === 'register' ? 'register' : 'login')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    const success = mode === 'login' ? await login(email, password) : await register(username, email, password)
    setBusy(false)
    if (success) onSuccess()
  }

  const errorId = 'auth-error'
  const errorDescription = error ? errorId : undefined
  const inputClassName = 'min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base leading-normal text-slate-900 placeholder:text-slate-600 focus:border-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-700/20 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700'
  const labelClassName = 'grid gap-1.5 text-sm font-medium leading-normal text-slate-700'
  const textLinkClassName = 'inline-flex min-h-11 w-full items-center justify-center rounded px-2 text-center text-base font-medium leading-normal transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700'

  return (
    <section className="min-h-screen bg-slate-50 px-4 py-10 sm:py-16" aria-labelledby="auth-page-title">
      <div className="mx-auto w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <a className="inline-flex min-h-11 flex-col justify-center text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" href="/" aria-label="MatchSlip home">
          <span className="text-xl font-bold tracking-tight [font-family:'Plus_Jakarta_Sans',sans-serif]">MatchSlip</span>
          <span className="text-sm font-medium leading-normal text-slate-600">Built on evidence, not hunches.</span>
        </a>
        <h2 id="auth-page-title" className="mt-6 text-2xl font-bold tracking-tight text-slate-900 [font-family:'Plus_Jakarta_Sans',sans-serif]">{mode === 'login' ? 'Welcome back' : 'Create your account'}</h2>
        <p className="mt-2 text-base leading-relaxed text-slate-700">{mode === 'login' ? 'Sign in to your MatchSlip workspace.' : 'Create an account to get started with MatchSlip.'}</p>
        <form className="mt-6 grid gap-4" onSubmit={submit}>
          {mode === 'register' && <label className={labelClassName}>Username<input className={inputClassName} autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} aria-describedby={errorDescription} required /></label>}
          {mode === 'login'
            ? <label className={labelClassName}>Email or username<input className={inputClassName} type="text" autoComplete="username" autoCapitalize="none" spellCheck={false} value={email} onChange={event => setEmail(event.target.value)} aria-describedby={errorDescription} required /></label>
            : <label className={labelClassName}>Email<input className={inputClassName} type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} aria-describedby={errorDescription} required /></label>}
          <label className={labelClassName}>Password<input className={inputClassName} type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength={6} value={password} onChange={event => setPassword(event.target.value)} aria-describedby={errorDescription} required /></label>
          {error && <div id={errorId} className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-base leading-relaxed text-red-700" role="alert" aria-live="assertive">{error}</div>}
          <button className="inline-flex min-h-11 items-center justify-center rounded-lg bg-emerald-700 px-4 py-2.5 text-base font-semibold leading-normal text-white transition-colors hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" type="submit" disabled={busy}>{busy ? 'Working…' : mode === 'login' ? 'Sign in' : 'Create account'}</button>
        </form>
        <button className={`${textLinkClassName} mt-2 text-slate-700 hover:text-slate-900`} type="button" onClick={() => setMode(value => value === 'login' ? 'register' : 'login')}>
          {mode === 'login' ? 'Need an account? Create one' : 'Already have an account? Sign in'}
        </button>
        {mode === 'login' && <a className={`${textLinkClassName} text-emerald-700 hover:text-emerald-800`} href="/reset-password">Forgot your password?</a>}
        <a className={`${textLinkClassName} text-slate-700 hover:text-slate-900`} href="/">Back to home</a>
      </div>
    </section>
  )
}
