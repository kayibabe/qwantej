import { useEffect, useState } from 'react'
import { useAuth } from '../auth'

interface ProOffer {
  price: string
  currency: string
  interval: string
  checkout_enabled: boolean
}

function formatPrice(price: string | undefined) {
  const amount = Number(price)
  if (!Number.isFinite(amount)) return 'K20,000.00'
  return `K${amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

interface UpgradePageProps {
  onBack: () => void
  anonymous?: boolean
  onSignIn?: () => void
  onCreateAccount?: () => void
}

export default function UpgradePage({ onBack, anonymous = false, onSignIn, onCreateAccount }: UpgradePageProps) {
  const { user } = useAuth()
  const hasProAccess = !anonymous && (user?.plan === 'pro' || user?.role === 'admin')
  const [offer, setOffer] = useState<ProOffer | null>(null)
  const [txRef, setTxRef] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')

  async function checkPayment(reference: string) {
    if (!reference) return
    setBusy(true)
    setNotice('Checking your payment with Flutterwave…')
    try {
      const response = await fetch(`/api/v1/billing/checkout/${encodeURIComponent(reference)}`)
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail ?? 'Unable to check this payment yet.')
      if (data.status === 'paid') {
        setNotice('Payment confirmed. Your Pro access is active.')
        window.location.replace('/tickets')
        return
      }
      if (data.status === 'failed') {
        setNotice('Payment was not completed. No Pro access was added.')
        return
      }
      setNotice('Payment is still processing. Check again in a moment.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to check this payment yet.')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    let active = true
    fetch('/api/v1/billing/offer')
      .then(response => response.ok ? response.json() : Promise.reject(new Error('Pro pricing is temporarily unavailable.')))
      .then(data => { if (active) setOffer(data) })
      .catch(error => { if (active) setNotice(error instanceof Error ? error.message : 'Pro pricing is temporarily unavailable.') })

    const url = new URL(window.location.href)
    const returnedRef = url.searchParams.get('tx_ref') ?? ''
    if (!anonymous && url.searchParams.get('billing') === 'return' && returnedRef) {
      setTxRef(returnedRef)
      for (const key of ['billing', 'tx_ref', 'transaction_id', 'status']) url.searchParams.delete(key)
      window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`)
      void checkPayment(returnedRef)
    }
    return () => { active = false }
  }, [anonymous])

  async function beginCheckout() {
    setBusy(true)
    setNotice('Opening secure checkout…')
    try {
      const response = await fetch('/api/v1/billing/checkout', { method: 'POST' })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail ?? 'Unable to start checkout.')
      setTxRef(data.tx_ref)
      window.location.assign(data.checkout_url)
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to start checkout.')
      setBusy(false)
    }
  }

  const primaryButtonClassName = 'inline-flex min-h-11 w-full items-center justify-center rounded-lg bg-emerald-700 px-4 py-2.5 text-base font-semibold leading-normal text-white transition-colors hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700'
  const secondaryButtonClassName = 'inline-flex min-h-11 w-full items-center justify-center rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-base font-semibold leading-normal text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700'
  const noticeId = 'upgrade-notice'
  const noticeDescription = notice ? noticeId : undefined
  const noticeIsError = /^(payment was not completed|unable to|pro pricing is temporarily unavailable)/i.test(notice)
  const noticeIsSuccess = notice.startsWith('Payment confirmed')
  const noticeClassName = noticeIsError
    ? 'border-red-200 bg-red-50 text-red-700'
    : noticeIsSuccess
      ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
      : 'border-slate-200 bg-slate-50 text-slate-700'

  return (
    <section className="min-h-screen bg-slate-50 px-4 py-10 sm:py-16" aria-labelledby="upgrade-title">
      <div className="mx-auto grid w-full max-w-xl gap-5 rounded-xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <span className="text-sm font-bold leading-normal text-emerald-700">QwantEj Pro · monthly access</span>
        <h1 id="upgrade-title" className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl font-display">{hasProAccess ? 'Your Pro access is active' : 'Unlock the full matchday workspace'}</h1>
        <p className="text-base leading-relaxed text-slate-700">{hasProAccess ? `Your ${user?.plan === 'pro' ? 'Pro' : 'admin'} account includes Pro features.` : 'Move from the daily published record to the exact selections, captured prices and model evidence behind each ticket.'}</p>

        {!hasProAccess && <>
          <div className="flex flex-wrap items-baseline gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3" aria-label={`${formatPrice(offer?.price)} per month`}>
            <strong className="font-mono text-3xl font-bold tabular-nums text-slate-900">{formatPrice(offer?.price)}</strong><span className="text-base font-medium text-slate-700">/ month</span>
          </div>
          <ul className="grid gap-2 text-base leading-normal text-slate-700">
            <li className="flex gap-2"><span className="text-emerald-700" aria-hidden="true">•</span><span>Every Q ≥75 System pick, grouped by match</span></li>
            <li className="flex gap-2"><span className="text-emerald-700" aria-hidden="true">•</span><span>Selections, captured odds and model chance</span></li>
            <li className="flex gap-2"><span className="text-emerald-700" aria-hidden="true">•</span><span>Expanded published ticket history</span></li>
            <li className="flex gap-2"><span className="text-emerald-700" aria-hidden="true">•</span><span>Stats &amp; Trends with league context</span></li>
          </ul>
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-base leading-relaxed text-slate-700">
            <strong className="font-semibold text-slate-900">Recurring monthly card payment.</strong> You can manage or cancel the subscription through Flutterwave’s subscription emails.
          </div>
          {anonymous ? <>
            <button className={primaryButtonClassName} onClick={onCreateAccount}>Create a free account</button>
            <button className={secondaryButtonClassName} onClick={onSignIn}>I already have an account</button>
            <p className="text-base leading-relaxed text-slate-700">Create your account first. Pro is activated after the monthly card payment is confirmed.</p>
          </> : <>
            <button className={primaryButtonClassName} onClick={beginCheckout} disabled={busy || !offer?.checkout_enabled} aria-describedby={noticeDescription}>
              {busy ? 'Please wait…' : offer?.checkout_enabled ? 'Continue to secure checkout' : 'Checkout is being configured'}
            </button>
            {txRef && <button className={secondaryButtonClassName} onClick={() => void checkPayment(txRef)} disabled={busy} aria-describedby={noticeDescription}>Check payment status</button>}
            {!offer?.checkout_enabled && !notice && <p className="text-base leading-relaxed text-slate-700">Checkout will be available when this server’s payment settings are complete.</p>}
            {notice && <p id={noticeId} className={`rounded-lg border px-3 py-2 text-base leading-relaxed ${noticeClassName}`} role={noticeIsError ? 'alert' : 'status'} aria-live={noticeIsError ? 'assertive' : 'polite'}>{notice}</p>}
          </>}
        </>}

        <button className={hasProAccess ? primaryButtonClassName : secondaryButtonClassName} onClick={onBack}>{hasProAccess ? 'Return to tickets' : anonymous ? 'Back to home' : 'Not now'}</button>
      </div>
    </section>
  )
}
