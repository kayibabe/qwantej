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

export default function UpgradePage({ onBack }: { onBack: () => void }) {
  const { user } = useAuth()
  const hasProAccess = user?.plan === 'pro' || user?.role === 'admin'
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
    if (url.searchParams.get('billing') === 'return' && returnedRef) {
      setTxRef(returnedRef)
      for (const key of ['billing', 'tx_ref', 'transaction_id', 'status']) url.searchParams.delete(key)
      window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`)
      void checkPayment(returnedRef)
    }
    return () => { active = false }
  }, [])

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

  return (
    <section className="auth-page" aria-labelledby="upgrade-title">
      <div className="auth-card upgrade-card">
        <span className="eyebrow">Qwantej Pro · monthly access</span>
        <h1 id="upgrade-title">{hasProAccess ? 'Your Pro access is active' : 'Unlock the full research workspace'}</h1>
        <p>{hasProAccess ? `Your ${user?.plan === 'pro' ? 'Pro' : 'admin'} account includes Pro features.` : 'Move from the daily published slate to deeper odds, complete ticket history and league context.'}</p>

        {!hasProAccess && <>
          <div className="upgrade-price" aria-label={`${formatPrice(offer?.price)} per month`}>
            <strong>{formatPrice(offer?.price)}</strong><span>/ month</span>
          </div>
          <ul className="upgrade-features">
            <li>Detailed odds and market selections</li>
            <li>Expanded published ticket history</li>
            <li>Stats &amp; Trends with league context</li>
          </ul>
          <p className="upgrade-billing-note">Recurring monthly card payment. You can manage or cancel the subscription through Flutterwave’s subscription emails.</p>
          <button className="btn-primary upgrade-checkout" onClick={beginCheckout} disabled={busy || !offer?.checkout_enabled}>
            {busy ? 'Please wait…' : offer?.checkout_enabled ? 'Continue to secure checkout' : 'Checkout is being configured'}
          </button>
          {txRef && <button className="btn-ghost upgrade-check-status" onClick={() => void checkPayment(txRef)} disabled={busy}>Check payment status</button>}
          {!offer?.checkout_enabled && !notice && <p className="upgrade-setup-note">Checkout will be available when this server’s payment settings are complete.</p>}
          {notice && <p className="upgrade-notice" role="status" aria-live="polite">{notice}</p>}
        </>}

        <button className={hasProAccess ? 'btn-primary' : 'btn-ghost upgrade-back'} onClick={onBack}>{hasProAccess ? 'Return to tickets' : 'Not now'}</button>
      </div>
    </section>
  )
}
