import { useState, useEffect } from 'react'
import AppShell from './components/layout/AppShell'
import SignalsPage from './pages/SignalsPage'
import MatchIntelligencePage from './pages/MatchIntelligencePage'
import TrackerPage from './pages/TrackerPage'
import ForecastArchivePage from './pages/ForecastArchivePage'
import ModelPerformancePage from './pages/ModelPerformancePage'
import DataSourcePage from './pages/DataSourcePage'
import ToolsPage from './pages/ToolsPage'
import PricingPage from './pages/PricingPage'
import AdminPage from './pages/AdminPage'
import AccountPage from './pages/AccountPage'
import LandingPage from './pages/LandingPage'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import ResetPasswordPage from './pages/ResetPasswordPage'
import PaymentCallbackPage from './pages/PaymentCallbackPage'
import { useSettings } from './store/useSettings'
import { useAuth } from './context/AuthContext'

const PAGES = new Set(['signals', 'tracker', 'archive', 'performance', 'sources', 'tools', 'account', 'pricing', 'admin'])

function pageFromPath() {
  const slug = window.location.pathname.replace(/^\//, '')
  return slug && PAGES.has(slug) ? slug : 'signals'
}

export default function App() {
  const [activePage, setActivePage] = useState(pageFromPath)
  const [matchFixtureId, setMatchFixtureId] = useState(null)
  const [authMode, setAuthMode] = useState('login')
  const [pendingSignalFilter, setPendingSignalFilter] = useState(null)
  const { settings, update } = useSettings()
  const { user, loading } = useAuth()

  // Handle Paystack callback redirect (/payment/callback?reference=...)
  const isPaymentCallback = window.location.pathname === '/payment/callback'

  useEffect(() => {
    // After payment callback resolves, reload user and go to pricing
    if (isPaymentCallback && user) {
      setActivePage('pricing')
    }
  }, [isPaymentCallback, user])

  useEffect(() => {
    function handler(e) { setActivePage(e.detail) }
    window.addEventListener('Qwantej:navigate', handler)
    return () => window.removeEventListener('Qwantej:navigate', handler)
  }, [])

  // Keep URL in sync with activePage so /tracker, /analytics etc. are bookmarkable
  useEffect(() => {
    if (!PAGES.has(activePage)) return
    const target = activePage === 'signals' ? '/' : `/${activePage}`
    if (window.location.pathname !== target) {
      window.history.pushState({}, '', target)
    }
  }, [activePage])

  // Handle browser back/forward
  useEffect(() => {
    function handlePopState() { setActivePage(pageFromPath()) }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--bg-page)]">
        <div className="text-[var(--text)] opacity-80 text-sm animate-pulse">Loading…</div>
      </div>
    )
  }

  // Handle /reset-password?token= URL
  const resetToken = !user && window.location.pathname === '/reset-password'
    ? new URLSearchParams(window.location.search).get('token')
    : null

  if (!user) {
    if (resetToken) return <ResetPasswordPage token={resetToken} onDone={() => { window.history.replaceState({}, '', '/'); setAuthMode('landing') }} />
    if (authMode === 'forgot') return <ForgotPasswordPage onBack={() => setAuthMode('login')} />
    if (authMode === 'register') return <RegisterPage onSwitch={() => setAuthMode('login')} onBack={() => setAuthMode('login')} />
    // Unauthenticated users can view the tracker (system picks only — enforced by the API)
    if (activePage === 'tracker') {
      return (
        <AppShell activePage={activePage} onNavigate={(p) => {
          setActivePage(p)
          if (p !== 'tracker') setAuthMode('login')
        }}>
          <TrackerPage user={null} settings={settings} onUpgrade={() => { setActivePage('signals'); setAuthMode('login') }} />
        </AppShell>
      )
    }
    if (authMode === 'login') return <LoginPage onSwitch={() => setAuthMode('register')} onForgot={() => setAuthMode('forgot')} onBack={null} />
    return <LandingPage onSignIn={() => setAuthMode('login')} onSignUp={() => setAuthMode('register')} />
  }

  if (isPaymentCallback) {
    return (
      <PaymentCallbackPage onDone={() => {
        window.history.replaceState({}, '', '/')
        setActivePage('pricing')
        // Force a page reload to refresh user context from /auth/me
        window.location.href = '/'
      }} />
    )
  }

  function handleMatchIntelligence(fixtureId) {
    setMatchFixtureId(fixtureId)
    setActivePage('match')
  }

  function handleBackFromMatch() {
    setActivePage('signals')
    setMatchFixtureId(null)
  }

  const goToPricing = () => setActivePage('pricing')

  function handleApplySignalFilter(filter) {
    setPendingSignalFilter(filter)
    setActivePage('signals')
  }

  function renderPage() {
    switch (activePage) {
      case 'signals':
        return <SignalsPage
          settings={settings}
          onMatchIntelligence={handleMatchIntelligence}
          onUpgrade={goToPricing}
          onNavigateToTracker={() => setActivePage('tracker')}
          initialFilter={pendingSignalFilter}
          onFilterConsumed={() => setPendingSignalFilter(null)}
        />
      case 'match':
        return <MatchIntelligencePage fixtureId={matchFixtureId} settings={settings} onBack={handleBackFromMatch} />
      case 'tracker':
        return <TrackerPage user={user} settings={settings} onUpgrade={goToPricing} />
      case 'archive':
        return <ForecastArchivePage onMatchIntelligence={handleMatchIntelligence} />
      case 'performance':
        return <ModelPerformancePage />
      case 'sources':
        return <DataSourcePage />
      case 'tools':
        return <ToolsPage settings={settings} onUpgrade={goToPricing} onUpdate={update} />
      case 'account':
        return <AccountPage onUpgrade={goToPricing} />
      case 'pricing':
        return <PricingPage />
      case 'admin':
        return user?.is_admin ? <AdminPage /> : null
      default:
        return null
    }
  }

  return (
    <AppShell activePage={activePage} onNavigate={setActivePage}>
      {renderPage()}
    </AppShell>
  )
}
