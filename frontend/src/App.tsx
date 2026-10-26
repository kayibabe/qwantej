import { Component, lazy, Suspense, useEffect, useState, type ErrorInfo, type ReactNode } from 'react'
import './App.css'
import './WorkspaceNavigation.css'
import { TODAY } from './pages/dailyTickets/helpers'
import { addDays } from './utils'
import { AuthControls, useAuth } from './auth'
import { fetchMarketCatalog, installMarketCatalog } from './lib/api'

const DailyTicketsPage = lazy(() => import('./pages/DailyTickets'))
const TrackerPage = lazy(() => import('./pages/Tracker'))
const AnalyticsPage = lazy(() => import('./pages/Analytics'))
const ToolsPage = lazy(() => import('./pages/Tools'))
const AdminPage = lazy(() => import('./pages/Admin'))
const UpgradePage = lazy(() => import('./pages/Upgrade'))
const MatchIntelligencePage = lazy(() => import('./pages/MatchIntelligencePage'))
const LoginPage = lazy(() => import('./pages/Login'))
const InsightsPage = lazy(() => import('./pages/Insights'))
const LiveMonitorPage = lazy(() => import('./pages/LiveMonitor'))
const PublicHome = lazy(() => import('./pages/PublicHome'))

function PageLoading() {
  return <div className="route-loading" role="status" aria-live="polite">Loading page…</div>
}

type Theme = 'dark' | 'light' | 'system'
type ModulePage = 'tickets' | 'matches' | 'live' | 'insights' | 'research' | 'tracker' | 'analytics' | 'tools' | 'admin'
type Page = ModulePage | 'home' | 'match' | 'upgrade' | 'login'
type Workspace = 'football' | 'research'
type ResearchTab = 'matches' | 'odds-policy' | 'market-roi' | 'daily-match-picks' | 'passed'
const RESEARCH_TABS: ResearchTab[] = ['matches', 'odds-policy', 'market-roi', 'daily-match-picks', 'passed']
const MATCH_RETURN_ROUTES = new Set(['/tickets', '/matches', '/research', '/live', '/insights'])

class RouteErrorBoundary extends Component<{ children: ReactNode; onRetry: () => void }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Route content failed to render', error, info.componentStack)
  }

  render() {
    if (this.state.failed) {
      return <section className="route-error" role="alert">
        <h1>This page could not be displayed</h1>
        <p>Your navigation is still available. Try this page again or open another section.</p>
        <button className="btn-primary" onClick={this.props.onRetry}>Try this page again</button>
      </section>
    }
    return this.props.children
  }
}

function dateFromSearch(search: string): string {
  const value = new URLSearchParams(search).get('date')
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return TODAY
  const [year, month, day] = value.split('-').map(Number)
  const parsed = new Date(year, month - 1, day)
  return parsed.getFullYear() === year && parsed.getMonth() === month - 1 && parsed.getDate() === day
    ? value
    : TODAY
}

function datePath(path: string, date: string, extra?: Record<string, string>): string {
  const params = new URLSearchParams(extra)
  if (date !== TODAY) params.set('date', date)
  const query = params.toString()
  return query ? `${path}?${query}` : path
}

const NAV: { id: ModulePage; label: string }[] = [
  { id: 'tickets', label: 'Today' },
  { id: 'matches', label: 'Matches' },
  { id: 'live', label: 'Live' },
  { id: 'insights', label: 'Stats & trends' },
]
const INTERNAL_NAV: { id: ModulePage; label: string }[] = [
  { id: 'research', label: 'Research' },
  { id: 'tracker', label: 'Track' },
  { id: 'analytics', label: 'Validate' },
  { id: 'tools', label: 'Tools' },
  { id: 'admin', label: 'Admin' },
]

const NAV_META: Record<ModulePage, { icon: string; hint: string }> = {
  tickets: { icon: 'sparkles', hint: 'Published recommendations' },
  matches: { icon: 'search', hint: 'Browse fixtures and qualified match markets' },
  live: { icon: 'activity', hint: 'Live scores and match phases' },
  insights: { icon: 'chart', hint: 'League results and team trends' },
  research: { icon: 'flask', hint: 'Research models and selection policies' },
  tracker: { icon: 'list', hint: 'Evidence and personal journal' },
  analytics: { icon: 'chart', hint: 'Performance and model validation' },
  tools: { icon: 'wrench', hint: 'Calculators and research utilities' },
  admin: { icon: 'shield', hint: 'System administration' },
}

function NavIcon({ name }: { name: string }) {
  const paths: Record<string, ReactNode> = {
    sparkles: <><path d="m12 3-1.2 4.1L7 8.3l3.8 1.2L12 13l1.2-3.5L17 8.3l-3.8-1.2L12 3Z" /><path d="m5 14-.7 2.3L2 17l2.3.7L5 20l.7-2.3L8 17l-2.3-.7L5 14Z" /></>,
    list: <><path d="m4 6 1.5 1.5L8 5" /><path d="M11 6h9M11 12h9M11 18h9" /><path d="m4 12 1.5 1.5L8 11" /><path d="m4 18 1.5 1.5L8 17" /></>,
    chart: <><path d="M5 20V10M12 20V4M19 20v-7" /></>,
    activity: <><path d="M3 12h4l3-8 4 16 3-8h4" /></>,
    search: <><circle cx="10.8" cy="10.8" r="6.6" /><path d="m16 16 4.5 4.5" /></>,
    flask: <><path d="M9 3h6M10 3v6l-5.2 8.5A2.3 2.3 0 0 0 6.8 21h10.4a2.3 2.3 0 0 0 2-3.5L14 9V3" /><path d="M7.7 15h8.6" /></>,
    wrench: <><path d="m14.7 6.3 3-3a5 5 0 0 0-6.4 6.4L3 18a2 2 0 1 0 3 3l8.3-8.3a5 5 0 0 0 6.4-6.4l-3 3-3-3Z" /></>,
    shield: <><path d="M12 3 20 6v5c0 5-3.4 8.6-8 10-4.6-1.4-8-5-8-10V6l8-3Z" /><path d="m9 12 2 2 4-4" /></>,
  }
  return <svg className="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>
}

export default function App() {
  const { user, loading: authLoading } = useAuth()
  const isInternal = user?.role === 'admin'
  const [page, setPage] = useState<Page>(() => routePage(window.location.pathname))
  const [routeAttempt, setRouteAttempt] = useState(0)
  const [researchTab, setResearchTab] = useState<ResearchTab>(() => researchTabFromSearch(window.location.search))
  const [workspace, setWorkspace] = useState<Workspace>(() => workspaceForLocation(routePage(window.location.pathname), window.location.search) ?? 'football')
  const [matchId, setMatchId] = useState<number | null>(() => routeMatchId(window.location.pathname))
  const [predictionId, setPredictionId] = useState<number | null>(() => routePredictionId(window.location.search))
  const [matchReturnTo, setMatchReturnTo] = useState<string>(() => matchReturnPath(window.location.search))
  const [date, setDate] = useState(() => dateFromSearch(window.location.search))
  const [theme, setTheme] = useState<Theme>('system')
  const [, setMarketCatalogLoaded] = useState(false)

  useEffect(() => {
    let active = true
    fetchMarketCatalog()
      .then(catalog => {
        if (!active) return
        installMarketCatalog(catalog.markets)
        setMarketCatalogLoaded(true)
      })
      .catch(() => {
        // Existing local formatters remain the fallback if the catalogue is unavailable.
      })
    return () => { active = false }
  }, [])

  useEffect(() => {
    const url = new URL(window.location.href)
    if (date === TODAY) url.searchParams.delete('date')
    else url.searchParams.set('date', date)
    window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`)
  }, [date])

  useEffect(() => {
    const onPopState = () => {
      const nextPage = routePage(window.location.pathname)
      setPage(nextPage)
      const nextWorkspace = workspaceForLocation(nextPage, window.location.search)
      if (nextWorkspace) setWorkspace(nextWorkspace)
      setMatchId(routeMatchId(window.location.pathname))
      setPredictionId(routePredictionId(window.location.search))
      setMatchReturnTo(matchReturnPath(window.location.search))
      setResearchTab(researchTabFromSearch(window.location.search))
      setDate(dateFromSearch(window.location.search))
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  useEffect(() => {
    document.getElementById('main-content')?.focus()
  }, [page])

  useEffect(() => {
    if (authLoading) return
    const path = window.location.pathname
    if (!user && path !== '/' && path !== '/login') {
      window.history.replaceState({}, '', '/login')
      setPage('login')
      setWorkspace('football')
      setMatchId(null)
    } else if (user && (path === '/login' || path === '/')) {
      window.history.replaceState({}, '', '/tickets')
      setPage('tickets')
      setWorkspace('football')
    }
  }, [authLoading, user])

  useEffect(() => {
    if (authLoading || !user || isInternal || !isInternalPage(page) || (page === 'match' && user.plan === 'pro')) return
    setPage('tickets')
    setWorkspace('football')
    setMatchId(null)
    window.history.replaceState({}, '', '/tickets')
  }, [authLoading, isInternal, page])

  useEffect(() => {
    const isPublicLanding = !authLoading && !user && page === 'home'
    document.documentElement.classList.toggle('public-page-scroll', isPublicLanding)
    return () => document.documentElement.classList.remove('public-page-scroll')
  }, [authLoading, page, user])

  function navigate(next: Page, _requested?: ModulePage, replace = false) {
    if (next === 'research') { navigateResearch(researchTab, replace); return }
    setPage(next)
    const nextWorkspace = workspaceForPage(next)
    if (nextWorkspace) setWorkspace(nextWorkspace)
    const path = next === 'home' ? '/' : next === 'upgrade' ? '/upgrade' : `/${next}`
    window.history[replace ? 'replaceState' : 'pushState']({}, '', datePath(path, date))
  }

  function navigateToMatch(nextMatchId: number, nextPredictionId?: number) {
    setMatchId(nextMatchId)
    setPredictionId(nextPredictionId ?? null)
    setPage('match')
    const currentPath = window.location.pathname
    const currentParams = new URLSearchParams(window.location.search)
    currentParams.delete('from')
    const from = `${currentPath}${currentParams.size ? `?${currentParams}` : ''}`
    setMatchReturnTo(from)
    const extra: Record<string, string> = { from }
    if (nextPredictionId != null) extra.prediction_id = String(nextPredictionId)
    window.history.pushState({ qwantejMatchReturn: true }, '', datePath(`/match/${nextMatchId}`, date, extra))
  }

  function returnFromMatch() {
    if (window.history.state?.qwantejMatchReturn) {
      window.history.back()
      return
    }
    const target = matchReturnPath(window.location.search) || matchReturnTo || '/tickets'
    const targetUrl = new URL(target, window.location.origin)
    const nextPage = routePage(targetUrl.pathname)
    setPage(nextPage)
    setWorkspace(workspaceForPage(nextPage) ?? 'football')
    setMatchId(null)
    setPredictionId(null)
    setDate(dateFromSearch(targetUrl.search))
    window.history.pushState({}, '', `${targetUrl.pathname}${targetUrl.search}`)
  }

  function goTo(next: ModulePage) {
    navigate(next)
  }

  function navigateResearch(tab: ResearchTab, replace = false) {
    setResearchTab(tab)
    setPage('research')
    setWorkspace('research')
    const method = replace ? 'replaceState' : 'pushState'
    window.history[method]({}, '', datePath('/research', date, { tab }))
  }

  function navigateTracker(ticketId?: number, targetDate?: string) {
    const nextDate = targetDate ?? date
    setDate(nextDate)
    setPage('tracker')
    setWorkspace('research')
    const params = new URLSearchParams()
    params.set('view', 'accumulators')
    if (ticketId != null) params.set('ticket', String(ticketId))
    if (nextDate !== TODAY) params.set('date', nextDate)
    window.history.pushState({}, '', `/tracker?${params}`)
  }

  function switchWorkspace(next: Workspace) {
    if (!isInternal || next === workspace) return
    if (next === 'football') goTo('tickets')
    else navigateResearch(researchTab)
  }

  const cycleTheme = () => {
    setTheme(t => {
      const next = t === 'system' ? 'dark' : t === 'dark' ? 'light' : 'system'
      if (next === 'system') {
        document.documentElement.removeAttribute('data-theme')
      } else {
        document.documentElement.setAttribute('data-theme', next)
      }
      return next
    })
  }

  const nav = (n: number) => setDate(d => addDays(d, n))
  const navPage = page === 'match' ? routePage(new URL(matchReturnTo || '/tickets', window.location.origin).pathname) : page

  if (authLoading) {
    return <div className="auth-standalone" role="status" aria-live="polite">Checking your session…</div>
  }

  if (!user) {
    if (page === 'home') {
      return <Suspense fallback={<PageLoading />}><PublicHome date={date} onDateChange={setDate} onSignIn={() => navigate('login')} onCreateAccount={() => { setPage('login'); window.history.pushState({}, '', '/login?mode=register') }} /></Suspense>
    }
    return <div className="auth-standalone"><Suspense fallback={<PageLoading />}><LoginPage onSuccess={() => navigate('tickets', undefined, true)} /></Suspense></div>
  }

  if (page === 'home' || page === 'login') {
    return <div className="auth-standalone" role="status" aria-live="polite">Opening your workspace...</div>
  }

  return (
    <div className="app">
      <aside className="app-sidebar">
        <a className="brand" href="/" aria-label="QwanEj home" onClick={(event) => { event.preventDefault(); goTo('tickets') }}>
          <img className="brand-logo brand-logo-light" src="/light/icon-128.png?v=qwanej-1" alt="" />
          <img className="brand-logo brand-logo-dark" src="/dark/icon-128.png?v=qwanej-1" alt="" />
          <span className="brand-copy"><strong className="brand-name">QwanEj</strong><small className="brand-tagline">Intelligence beyond numbers</small></span>
        </a>
        {isInternal && <WorkspaceSwitcher workspace={workspace} onChange={switchWorkspace} className="workspace-switcher-sidebar" />}
        <nav className="sidebar-nav" aria-label="Primary navigation">
          <span className="sidebar-label">{workspace === 'football' ? 'Football' : 'Research workspace'}</span>
          {(workspace === 'research' ? INTERNAL_NAV : NAV).map(n => (
            <button key={n.id} className={`nav-tab${navPage === n.id ? ' active' : ''}`} onClick={() => goTo(n.id)} title={NAV_META[n.id].hint} aria-current={navPage === n.id ? 'page' : undefined}>
              <span className="nav-icon"><NavIcon name={NAV_META[n.id].icon} /></span>{n.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-account">
          <AuthControls onSignIn={() => navigate('login')} onSignedOut={() => navigate('login', undefined, true)} />
        </div>
      </aside>
      <header className="app-header">
        <a className="topbar-brand" href="/tickets" aria-label="QwanEj home" onClick={(event) => { event.preventDefault(); goTo('tickets') }}>
          <img className="topbar-mark topbar-logo-light" src="/light/icon-128.png?v=qwanej-1" alt="" />
          <img className="topbar-mark topbar-logo-dark" src="/dark/icon-128.png?v=qwanej-1" alt="" />
          <span>QwanEj</span>
        </a>
        {isInternal && <WorkspaceSwitcher workspace={workspace} onChange={switchWorkspace} className="workspace-switcher-header" />}
        {(page === 'tickets' || page === 'matches' || (page === 'research' && isInternal)) && (
          <div className="date-nav">
            <button className="date-btn" onClick={() => nav(-1)} title="Previous day" aria-label="Previous day">‹</button>
            <div className="date-strip" role="group" aria-label="Choose match date">
              {[-2, -1, 0, 1, 2].map(offset => {
                const value = addDays(date, offset)
                const localDate = new Date(`${value}T12:00:00`)
                const label = localDate.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' })
                return <button
                  key={value}
                  className={`date-strip-day${date === value ? ' active' : ''}${value === TODAY ? ' today' : ''}`}
                  onClick={() => setDate(value)}
                  aria-label={label}
                  aria-pressed={date === value}
                >
                  <span>{value === TODAY ? 'Today' : localDate.toLocaleDateString('en-GB', { weekday: 'short' })}</span>
                  <b>{localDate.getDate()}</b>
                </button>
              })}
            </div>
            <div className="date-nav-tools">
              {date !== TODAY && <button className="today-btn" onClick={() => setDate(TODAY)}>Today</button>}
              <label className="date-picker-control" title="Choose any date">
                <span aria-hidden="true">▦</span>
              <input
                className="date-input"
                type="date"
                value={date}
                aria-label="Choose any date"
                onChange={e => setDate(e.target.value)}
              />
              </label>
            </div>
            <button className="date-btn" onClick={() => nav(1)} title="Next day" aria-label="Next day">›</button>
          </div>
        )}
        <div className="header-page-title">
        <span className="research-status"><span className="status-dot" /> {page === 'tickets' ? 'Decision workspace' : page === 'match' ? 'Match intelligence' : page === 'upgrade' ? 'System' : NAV_META[page].hint}</span>
          <button className="theme-btn" onClick={cycleTheme} title={`Theme: ${theme}`} aria-label={`Theme: ${theme}. Change theme`}>
            <span className="theme-auto">{theme === 'system' ? 'Auto' : theme}</span>
          </button>
        </div>
        <div className="header-refresh">
          <AuthControls onSignIn={() => navigate('login')} onSignedOut={() => navigate('login', undefined, true)} />
          {user?.plan !== 'pro' && <button className="premium-button" onClick={() => navigate('upgrade')}>Go Premium</button>}
          <button className="theme-btn settings-btn" onClick={cycleTheme} title={`Theme: ${theme}`} aria-label={`Theme: ${theme}. Change theme`}>⚙</button>
          <button className="global-refresh" onClick={() => window.location.reload()} title="Reload current page" aria-label="Reload current page">↻ <span>Reload</span></button>
        </div>
      </header>

      <main className="main" id="main-content" tabIndex={-1}>
        <RouteErrorBoundary key={`${page}-${routeAttempt}`} onRetry={() => setRouteAttempt(attempt => attempt + 1)}>
        <Suspense fallback={<PageLoading />}>
        {page === 'upgrade' && <UpgradePage onBack={() => goTo('tickets')} />}
        {page === 'tickets' && <DailyTicketsPage key={`${date}-${page}`} date={date} initialTab="tickets" onOpenMatch={navigateToMatch} />}
        {page === 'matches' && <DailyTicketsPage key={`${date}-${page}`} date={date} initialTab="matches" onOpenMatch={navigateToMatch} onOpenTracker={ticketId => navigateTracker(ticketId, date)} />}
        {page === 'live' && <LiveMonitorPage />}
        {page === 'insights' && (user.plan === 'pro' || isInternal
          ? <InsightsPage />
          : <section className="insights-access-card"><h1>Stats &amp; trends</h1><p>League results and team tables are available on Pro.</p><button className="btn-primary" onClick={() => navigate('upgrade')}>View Pro access</button></section>)}
        {isInternal && page === 'research' && <DailyTicketsPage key={`${date}-${page}`} date={date} initialTab={researchTab} onTabChange={tab => navigateResearch(tab as ResearchTab)} onOpenMatch={navigateToMatch} onOpenTracker={ticketId => navigateTracker(ticketId, date)} />}
        {page === 'match' && matchId != null && (user?.plan === 'pro' || isInternal) && <MatchIntelligencePage matchId={matchId} selectedPredictionId={predictionId} onBack={returnFromMatch} returnLabel={matchReturnLabel(matchReturnTo)} />}
        {isInternal && page === 'tracker' && <TrackerPage onOpenTickets={(targetDate) => { if (targetDate) setDate(targetDate); goTo('tickets') }} onOpenResearch={() => navigateResearch('matches')} onOpenValidation={() => goTo('analytics')} />}
        {isInternal && page === 'analytics' && <AnalyticsPage />}
        {isInternal && page === 'tools' && <ToolsPage />}
        {isInternal && page === 'admin' && <AdminPage />}
        </Suspense>
        </RouteErrorBoundary>
      </main>


      <nav className={`bottom-nav ${isInternal ? 'internal' : 'public'} ${workspace}`} aria-label="Primary navigation">
        {(isInternal && workspace === 'research' ? INTERNAL_NAV : NAV).map(item => (
          <button
            key={item.id}
            className={navPage === item.id ? 'active' : ''}
            onClick={() => goTo(item.id)}
            aria-current={navPage === item.id ? 'page' : undefined}
          >
            <span aria-hidden="true"><NavIcon name={NAV_META[item.id].icon} /></span>
            {item.label}
          </button>
        ))}
      </nav>
    </div>
  )
}

function WorkspaceSwitcher({ workspace, onChange, className }: { workspace: Workspace; onChange: (workspace: Workspace) => void; className: string }) {
  return (
    <div className={`workspace-switcher ${className}`} role="group" aria-label="Choose workspace">
      <button type="button" className={workspace === 'football' ? 'active' : ''} aria-pressed={workspace === 'football'} onClick={() => onChange('football')}>Football</button>
      <button type="button" className={workspace === 'research' ? 'active' : ''} aria-pressed={workspace === 'research'} onClick={() => onChange('research')}>Research</button>
    </div>
  )
}

function routePage(pathname: string): Page {
  const path = pathname.replace(/\/$/, '')
  if (!path) return 'home'
  if (path === '/login') return 'login'
  if (path === '/upgrade') return 'upgrade'
  if (/^\/match\/\d+$/.test(path)) return 'match'
  if (path === '/tickets' || path === '/matches' || path === '/live' || path === '/insights' || path === '/research') return path.slice(1) as ModulePage
  if (path === '/tracker' || path === '/analytics' || path === '/tools' || path === '/admin') return path.slice(1) as ModulePage
  return 'tickets'
}

function isInternalPage(page: Page): boolean {
  return page === 'research' || page === 'tracker' || page === 'analytics' || page === 'tools' || page === 'admin' || page === 'match'
}

function workspaceForPage(page: Page): Workspace | null {
  if (isInternalPage(page)) return 'research'
  if (page === 'tickets' || page === 'matches' || page === 'live' || page === 'insights') return 'football'
  return null
}

function workspaceForLocation(page: Page, search: string): Workspace | null {
  if (page !== 'match') return workspaceForPage(page)
  const target = matchReturnPath(search)
  return target ? workspaceForPage(routePage(new URL(target, window.location.origin).pathname)) : 'football'
}

function routeMatchId(pathname: string): number | null {
  const match = pathname.replace(/\/$/, '').match(/^\/match\/(\d+)$/)
  return match ? Number(match[1]) : null
}

function routePredictionId(search: string): number | null {
  const value = Number(new URLSearchParams(search).get('prediction_id'))
  return Number.isInteger(value) && value > 0 ? value : null
}

function researchTabFromSearch(search: string): ResearchTab {
  const rawValue = new URLSearchParams(search).get('tab')
  if (rawValue === 'acca-analysis') return 'matches'
  const value = rawValue as ResearchTab | null
  return value && RESEARCH_TABS.includes(value) ? value : 'market-roi'
}

function matchReturnPath(search: string): string {
  const value = new URLSearchParams(search).get('from')
  if (!value) return ''
  const target = new URL(value, window.location.origin)
  return target.origin === window.location.origin && MATCH_RETURN_ROUTES.has(target.pathname)
    ? `${target.pathname}${target.search}`
    : ''
}

function matchReturnLabel(path: string): string {
  const pathname = path ? new URL(path, window.location.origin).pathname : '/tickets'
  if (pathname === '/matches') return 'Matches'
  if (pathname === '/research') return 'Research'
  if (pathname === '/tracker') return 'Tracker'
  return 'Today'
}

