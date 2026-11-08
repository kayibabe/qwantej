import { Component, lazy, Suspense, useEffect, useState, type ErrorInfo, type MouseEvent as ReactMouseEvent, type ReactNode } from 'react'
import './App.css'
import './WorkspaceNavigation.css'
import './shell.css'
import { TODAY } from './pages/dailyTickets/helpers'
import { addDays } from './utils'
import { useAuth } from './auth'
import { fetchMarketCatalog, installMarketCatalog } from './lib/api'
import AccountMenu, { type ThemePreference } from './components/AccountMenu'
import CommandPalette, { type CommandAction } from './components/CommandPalette'

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
const AccountRecoveryPage = lazy(() => import('./pages/AccountRecovery'))

function PageLoading() {
  return <div className="route-loading" role="status" aria-live="polite">Loading page…</div>
}

type ModulePage = 'tickets' | 'live' | 'insights' | 'research' | 'tracker' | 'analytics' | 'tools' | 'admin'
type Page = ModulePage | 'home' | 'match' | 'upgrade' | 'login' | 'reset-password' | 'verify-email'
type Workspace = 'football' | 'research'
type ResearchTab = 'picks' | 'odds-policy' | 'market-roi' | 'daily-match-picks' | 'passed'
const RESEARCH_TABS: ResearchTab[] = ['picks', 'odds-policy', 'market-roi', 'daily-match-picks', 'passed']
type OverviewTab = 'fixtures' | 'picks' | 'tickets' | 'passed'
const OVERVIEW_TABS: OverviewTab[] = ['fixtures', 'picks', 'tickets', 'passed']
const MATCH_RETURN_ROUTES = new Set(['/tickets', '/matches', '/research', '/live', '/insights'])
const THEME_KEY = 'qwantej-theme'

interface ShellNavItem {
  id: ModulePage
  label: string
  group: 'Decide' | 'Research' | 'System'
  adminOnly?: boolean
}

const SHELL_NAV: ShellNavItem[] = [
  { id: 'tickets', label: 'Today', group: 'Decide' },
  { id: 'live', label: 'Live', group: 'Decide' },
  { id: 'insights', label: 'Stats & trends', group: 'Decide' },
  { id: 'research', label: 'Research', group: 'Research', adminOnly: true },
  { id: 'tracker', label: 'Track', group: 'Research', adminOnly: true },
  { id: 'analytics', label: 'Validate', group: 'Research', adminOnly: true },
  { id: 'tools', label: 'Tools', group: 'System', adminOnly: true },
  { id: 'admin', label: 'Admin', group: 'System', adminOnly: true },
]
const NAV_GROUP_ORDER: ShellNavItem['group'][] = ['Decide', 'Research', 'System']

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

function readStoredTheme(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_KEY)
    return stored === 'dark' || stored === 'light' ? stored : 'system'
  } catch {
    return 'system'
  }
}

function pageTitle(page: Page): string {
  switch (page) {
    case 'tickets': return 'Today'
    case 'live': return 'Live'
    case 'insights': return 'Stats & trends'
    case 'research': return 'Research'
    case 'tracker': return 'Track'
    case 'analytics': return 'Validate'
    case 'tools': return 'Tools'
    case 'admin': return 'Admin'
    case 'match': return 'Match intelligence'
    case 'upgrade': return 'Plans'
    default: return 'Workspace'
  }
}

function displayDate(value: string): string {
  return new Date(`${value}T12:00:00`).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
}

const NAV_META: Record<ModulePage, { icon: string; hint: string }> = {
  tickets: { icon: 'sparkles', hint: 'Today’s fixtures, system picks, and accumulator tickets' },
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
  const [overviewTab, setOverviewTab] = useState<OverviewTab>(() => overviewTabFromSearch(window.location.search))
  const [matchId, setMatchId] = useState<number | null>(() => routeMatchId(window.location.pathname))
  const [predictionId, setPredictionId] = useState<number | null>(() => routePredictionId(window.location.search))
  const [matchReturnTo, setMatchReturnTo] = useState<string>(() => matchReturnPath(window.location.search))
  const [date, setDate] = useState(() => dateFromSearch(window.location.search))
  const [theme, setTheme] = useState<ThemePreference>(readStoredTheme)
  const [paletteOpen, setPaletteOpen] = useState(false)
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
    if (theme === 'system') document.documentElement.removeAttribute('data-theme')
    else document.documentElement.setAttribute('data-theme', theme)
    try {
      window.localStorage.setItem(THEME_KEY, theme)
    } catch {
      // Private browsing can reject storage writes; the session still switches theme.
    }
  }, [theme])

  useEffect(() => {
    const url = new URL(window.location.href)
    // The former standalone /matches page now lives inside Today.
    if (url.pathname.replace(/\/$/, '') === '/matches') url.pathname = '/tickets'
    if (date === TODAY) url.searchParams.delete('date')
    else url.searchParams.set('date', date)
    window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`)
  }, [date])

  useEffect(() => {
    const onPopState = () => {
      const nextPage = routePage(window.location.pathname)
      setPage(nextPage)
      setMatchId(routeMatchId(window.location.pathname))
      setPredictionId(routePredictionId(window.location.search))
      setMatchReturnTo(matchReturnPath(window.location.search))
      setResearchTab(researchTabFromSearch(window.location.search))
      setOverviewTab(overviewTabFromSearch(window.location.search))
      setDate(dateFromSearch(window.location.search))
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  useEffect(() => {
    document.getElementById('main-content')?.focus()
  }, [page])

  useEffect(() => {
    const onShortcut = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== 'k') return
      event.preventDefault()
      setPaletteOpen(current => !current)
    }
    window.addEventListener('keydown', onShortcut)
    return () => window.removeEventListener('keydown', onShortcut)
  }, [])

  useEffect(() => {
    if (authLoading) return
    const path = window.location.pathname
    if (!user && !['/', '/login', '/reset-password', '/verify-email', '/upgrade'].includes(path)) {
      window.history.replaceState({}, '', '/login')
      setPage('login')
      setMatchId(null)
    } else if (user && (path === '/login' || path === '/')) {
      window.history.replaceState({}, '', '/tickets')
      setPage('tickets')
    }
  }, [authLoading, user])

  useEffect(() => {
    // Match intelligence stays reachable for free users so they see a Pro gate
    // instead of being bounced back to Today without an explanation.
    if (authLoading || !user || isInternal || page === 'match' || !isInternalPage(page)) return
    setPage('tickets')
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
    if (next === 'tickets') setOverviewTab('fixtures')
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
    setMatchId(null)
    setPredictionId(null)
    setDate(dateFromSearch(targetUrl.search))
    setOverviewTab(overviewTabFromSearch(targetUrl.search))
    window.history.pushState({}, '', `${targetUrl.pathname}${targetUrl.search}`)
  }

  function goTo(next: ModulePage) {
    navigate(next)
  }

  function navigateResearch(tab: ResearchTab, replace = false) {
    setResearchTab(tab)
    setPage('research')
    const method = replace ? 'replaceState' : 'pushState'
    window.history[method]({}, '', datePath('/research', date, { tab }))
  }

  function navigateTracker(ticketId?: number, targetDate?: string) {
    const nextDate = targetDate ?? date
    setDate(nextDate)
    setPage('tracker')
    const params = new URLSearchParams()
    params.set('view', 'accumulators')
    if (ticketId != null) params.set('ticket', String(ticketId))
    if (nextDate !== TODAY) params.set('date', nextDate)
    window.history.pushState({}, '', `/tracker?${params}`)
  }

  function updateOverviewTab(tab: OverviewTab) {
    setOverviewTab(tab)
    const url = new URL(window.location.href)
    if (tab === 'fixtures') url.searchParams.delete('tab')
    else url.searchParams.set('tab', tab)
    window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`)
  }

  function openOverviewTab(tab: OverviewTab) {
    setPage('tickets')
    setOverviewTab(tab)
    const params = new URLSearchParams()
    if (tab !== 'fixtures') params.set('tab', tab)
    if (date !== TODAY) params.set('date', date)
    const query = params.toString()
    window.history.pushState({}, '', query ? `/tickets?${query}` : '/tickets')
  }

  function refreshWorkspace() {
    const refreshEvent = new CustomEvent('qwantej:refresh', { cancelable: true })
    const handledByPage = window.dispatchEvent(refreshEvent) === false
    if (!handledByPage) setRouteAttempt(attempt => attempt + 1)
  }

  function navigateTicketSource(targetDate?: string) {
    const nextDate = targetDate ?? date
    setDate(nextDate)
    setOverviewTab('tickets')
    setPage('tickets')
    const params = new URLSearchParams({ tab: 'tickets' })
    if (nextDate !== TODAY) params.set('date', nextDate)
    window.history.pushState({}, '', `/tickets?${params}`)
  }

  const navPage = page === 'match' ? routePage(new URL(matchReturnTo || '/tickets', window.location.origin).pathname) : page
  const [openNavGroup, setOpenNavGroup] = useState<ShellNavItem['group'] | null>(
    () => SHELL_NAV.find(item => item.id === navPage)?.group ?? null
  )

  useEffect(() => {
    const activeGroup = SHELL_NAV.find(item => item.id === navPage)?.group
    if (activeGroup) setOpenNavGroup(activeGroup)
  }, [navPage])
  const workspace: Workspace = page === 'match'
    ? workspaceForPage(routePage(new URL(matchReturnTo || '/tickets', window.location.origin).pathname)) ?? 'football'
    : workspaceForPage(page) ?? 'football'

  if (authLoading) {
    return <div className="auth-standalone" role="status" aria-live="polite">Checking your session…</div>
  }

  if (page === 'reset-password' || page === 'verify-email') {
    return (
      <div className="auth-standalone">
        <Suspense fallback={<PageLoading />}>
          <AccountRecoveryPage mode={page === 'verify-email' ? 'verify' : 'reset'} />
        </Suspense>
      </div>
    )
  }

  if (!user) {
    if (page === 'home') {
      return <Suspense fallback={<PageLoading />}><PublicHome date={date} onDateChange={setDate} onSignIn={() => navigate('login')} onCreateAccount={() => { setPage('login'); window.history.pushState({}, '', '/login?mode=register') }} onViewPro={() => navigate('upgrade')} /></Suspense>
    }
    if (page === 'upgrade') {
      return <div className="auth-standalone"><Suspense fallback={<PageLoading />}><UpgradePage
        anonymous
        onBack={() => navigate('home')}
        onSignIn={() => { setPage('login'); window.history.pushState({}, '', '/login?next=upgrade') }}
        onCreateAccount={() => { setPage('login'); window.history.pushState({}, '', '/login?mode=register&next=upgrade') }}
      /></Suspense></div>
    }
    return <div className="auth-standalone"><Suspense fallback={<PageLoading />}><LoginPage onSuccess={() => {
      const next = new URLSearchParams(window.location.search).get('next')
      navigate(next === 'upgrade' ? 'upgrade' : 'tickets', undefined, true)
    }} /></Suspense></div>
  }

  if (page === 'home' || page === 'login') {
    return <div className="auth-standalone" role="status" aria-live="polite">Opening your workspace...</div>
  }

  const visibleNav = SHELL_NAV.filter(item => !item.adminOnly || isInternal)
  const navGroups = NAV_GROUP_ORDER
    .map(label => ({ label, items: visibleNav.filter(item => item.group === label) }))
    .filter(group => group.items.length > 0)

  function moduleHref(id: ModulePage): string {
    return id === 'research'
      ? datePath('/research', date, { tab: researchTab })
      : datePath(`/${id}`, date)
  }

  function navClick(id: ModulePage) {
    return (event: ReactMouseEvent<HTMLAnchorElement>) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
      event.preventDefault()
      goTo(id)
    }
  }

  const showDateNav = page === 'tickets' || (page === 'research' && isInternal)
  const dateNav = showDateNav ? (
    <div className="date-nav">
      <button className="date-btn" onClick={() => setDate(addDays(date, -1))} title="Previous day" aria-label="Previous day">‹</button>
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
            onChange={event => setDate(event.target.value)}
          />
        </label>
      </div>
      <button className="date-btn" onClick={() => setDate(addDays(date, 1))} title="Next day" aria-label="Next day">›</button>
    </div>
  ) : null

  const bottomBase: ModulePage[] = isInternal ? ['tickets', 'research', 'tracker'] : ['tickets', 'live', 'insights']
  const activeNavItem = visibleNav.find(item => item.id === navPage)
  const bottomItems = bottomBase
    .map(id => visibleNav.find(item => item.id === id))
    .filter((item): item is ShellNavItem => Boolean(item))
    .slice(0, 3)
  if (activeNavItem && !bottomItems.some(item => item.id === activeNavItem.id)) {
    bottomItems[bottomItems.length - 1] = activeNavItem
  }

  const commandActions: CommandAction[] = [
    ...visibleNav.map(item => ({
      id: `go-${item.id}`,
      label: item.label,
      group: 'Go to',
      hint: NAV_META[item.id].hint,
      keywords: ['navigate', 'page', item.id].join(' '),
      onRun: () => goTo(item.id),
    })),
    { id: 'date-previous', label: 'Previous day', group: 'Date', hint: displayDate(addDays(date, -1)), keywords: 'date yesterday', onRun: () => setDate(addDays(date, -1)) },
    { id: 'date-today', label: 'Jump to today', group: 'Date', hint: displayDate(TODAY), keywords: 'date now', onRun: () => setDate(TODAY) },
    { id: 'date-next', label: 'Next day', group: 'Date', hint: displayDate(addDays(date, 1)), keywords: 'date tomorrow', onRun: () => setDate(addDays(date, 1)) },
    { id: 'theme-system', label: 'Use system theme', group: 'Appearance', hint: 'Follow the operating system', keywords: 'theme auto', onRun: () => setTheme('system') },
    { id: 'theme-light', label: 'Use light theme', group: 'Appearance', keywords: 'theme appearance', onRun: () => setTheme('light') },
    { id: 'theme-dark', label: 'Use dark theme', group: 'Appearance', keywords: 'theme appearance', onRun: () => setTheme('dark') },
    { id: 'refresh-view', label: 'Refresh this view', group: 'Workspace', hint: 'Reload data without leaving the page', keywords: 'reload retry sync', onRun: refreshWorkspace },
    ...(isInternal ? [
      { id: 'today-picks', label: 'Open system picks', group: 'Today', hint: 'Qualified selections for the selected date', keywords: 'today candidates', onRun: () => openOverviewTab('picks') },
      { id: 'today-tickets', label: 'Open accumulator tickets', group: 'Today', hint: 'Published tiers for the selected date', keywords: 'today acca', onRun: () => openOverviewTab('tickets') },
      { id: 'today-rejected', label: 'Open rejection ledger', group: 'Today', hint: 'Why candidates were passed', keywords: 'today passed why', onRun: () => openOverviewTab('passed') },
    ] : []),
  ]

  return (
    <div className="app app-v2">
      <aside className="app-sidebar">
        <a className="shell-brand" href={moduleHref('tickets')} aria-label="QwanEj home" onClick={navClick('tickets')}>
          <img className="brand-logo brand-logo-light" src="/light/icon-128.png?v=qwanej-1" alt="" />
          <img className="brand-logo brand-logo-dark" src="/dark/icon-128.png?v=qwanej-1" alt="" />
          <span className="brand-copy"><strong className="brand-name">QwanEj</strong><small className="brand-tagline">Intelligence beyond numbers</small></span>
        </a>

        <nav className="shell-nav" aria-label="Primary navigation">
          {navGroups.map(group => {
            const expanded = openNavGroup === group.label
            const panelId = `shell-nav-${group.label.toLowerCase()}`
            const hasActive = group.items.some(item => item.id === navPage)
            return (
              <div className={`shell-nav-group${expanded ? ' expanded' : ''}`} key={group.label}>
                <button
                  type="button"
                  className={`shell-nav-label${hasActive ? ' has-active' : ''}`}
                  aria-expanded={expanded}
                  aria-controls={panelId}
                  onClick={() => setOpenNavGroup(current => current === group.label ? null : group.label)}
                >
                  <span>{group.label}</span>
                  <svg className="shell-nav-chevron" viewBox="0 0 16 16" aria-hidden="true">
                    <path d="M3.5 6 8 10.5 12.5 6" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
                <div className="shell-nav-items" id={panelId} hidden={!expanded}>
                  {group.items.map(item => (
                    <a
                      key={item.id}
                      className={`shell-nav-link${navPage === item.id ? ' active' : ''}`}
                      href={moduleHref(item.id)}
                      title={NAV_META[item.id].hint}
                      aria-current={navPage === item.id ? 'page' : undefined}
                      onClick={navClick(item.id)}
                    >
                      <span className="shell-nav-icon"><NavIcon name={NAV_META[item.id].icon} /></span>
                      <span>{item.label}</span>
                    </a>
                  ))}
                </div>
              </div>
            )
          })}
        </nav>

        <div className="shell-sidebar-footer">
          <span className="shell-status"><span className="shell-status-dot" aria-hidden="true" />{isInternal ? 'Paper-trading workspace' : 'Dated publishing record'}</span>
          <small>{isInternal || user?.plan === 'pro'
            ? 'Every published pick keeps its quote, model, and settlement evidence.'
            : 'Free keeps every published ticket, its match legs and settlement. Pro adds prices and leg evidence.'}</small>
          <button type="button" className="shell-shortcut" onClick={() => setPaletteOpen(true)}>
            <span>Search or jump</span><kbd>⌘K</kbd>
          </button>
        </div>
      </aside>
      <header className="app-header">
        <a className="shell-mobile-brand" href={moduleHref('tickets')} aria-label="QwanEj home" onClick={navClick('tickets')}>
          <img className="brand-logo brand-logo-light" src="/light/icon-128.png?v=qwanej-1" alt="" />
          <img className="brand-logo brand-logo-dark" src="/dark/icon-128.png?v=qwanej-1" alt="" />
          <strong>QwanEj</strong>
        </a>

        <div className="shell-context">
          <div className="shell-scope">
            <span>{workspace === 'research' ? 'Research workspace' : 'Football workspace'}</span>
            <strong>{pageTitle(page)}</strong>
          </div>
          {dateNav}
        </div>

        <div className="shell-actions">
          <button
            type="button"
            className="shell-search"
            onClick={() => setPaletteOpen(true)}
            aria-haspopup="dialog"
            aria-expanded={paletteOpen}
            aria-label="Open command palette"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" aria-hidden="true">
              <circle cx="10.8" cy="10.8" r="6.6" /><path d="m16 16 4.5 4.5" />
            </svg>
            <span>Search</span>
            <kbd>⌘K</kbd>
          </button>
          <button type="button" className="shell-icon-btn" onClick={refreshWorkspace} title="Refresh this view" aria-label="Refresh this view">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M20 11a8 8 0 1 0-2.3 5.7" /><path d="M20 5v6h-6" />
            </svg>
          </button>
          <AccountMenu
            theme={theme}
            onThemeChange={setTheme}
            onRefresh={refreshWorkspace}
            onOpenPalette={() => setPaletteOpen(true)}
            onUpgrade={() => navigate('upgrade')}
            onSignIn={() => navigate('login')}
            onSignedOut={() => navigate('login', undefined, true)}
          />
        </div>
      </header>

      <main className="main" id="main-content" tabIndex={-1}>
        <RouteErrorBoundary key={`${page}-${routeAttempt}`} onRetry={() => setRouteAttempt(attempt => attempt + 1)}>
        <Suspense fallback={<PageLoading />}>
        {page === 'upgrade' && <UpgradePage onBack={() => goTo('tickets')} />}
        {page === 'tickets' && <DailyTicketsPage key={`${date}-${page}`} date={date} initialTab={overviewTab} mode="overview" onTabChange={tab => updateOverviewTab(tab as OverviewTab)} onOpenMatch={navigateToMatch} onOpenTracker={ticketId => navigateTracker(ticketId, date)} onUpgrade={() => navigate('upgrade')} />}
        {page === 'live' && <LiveMonitorPage />}
        {page === 'insights' && (user.plan === 'pro' || isInternal
          ? <InsightsPage />
          : <section className="insights-access-card" aria-labelledby="insights-pro-gate-title">
              <span className="eyebrow">Pro</span>
              <h1 id="insights-pro-gate-title">Stats &amp; trends is part of Pro</h1>
              <p>Review league results, team form and historical performance alongside the picks and tickets they came from.</p>
              <div className="plan-locked-actions">
                <button className="btn-primary" onClick={() => navigate('upgrade')}>Upgrade to Pro</button>
                <button className="btn-ghost" onClick={() => navigate('tickets')}>Back to Today</button>
              </div>
            </section>)}
        {isInternal && page === 'research' && <DailyTicketsPage key={`${date}-${page}`} date={date} initialTab={researchTab} mode="research" onTabChange={tab => navigateResearch(tab as ResearchTab)} onOpenMatch={navigateToMatch} onOpenTracker={ticketId => navigateTracker(ticketId, date)} />}
        {page === 'match' && matchId != null && (user?.plan === 'pro' || isInternal) && <MatchIntelligencePage matchId={matchId} selectedPredictionId={predictionId} onBack={returnFromMatch} returnLabel={matchReturnLabel(matchReturnTo)} />}
        {page === 'match' && matchId != null && user?.plan !== 'pro' && !isInternal && (
          <section className="insights-access-card" aria-labelledby="match-pro-gate-title">
            <span className="eyebrow">Pro</span>
            <h1 id="match-pro-gate-title">Match intelligence is part of Pro</h1>
            <p>Open every qualified selection for this match with its captured price, model chance, spread and recorded evidence.</p>
            <div className="plan-locked-actions">
              <button className="btn-primary" onClick={() => navigate('upgrade')}>Upgrade to Pro</button>
              <button className="btn-ghost" onClick={returnFromMatch}>Back to {matchReturnLabel(matchReturnTo)}</button>
            </div>
          </section>
        )}
        {isInternal && page === 'tracker' && <TrackerPage onOpenTickets={navigateTicketSource} onOpenResearch={() => navigateResearch('picks')} onOpenValidation={() => goTo('analytics')} />}
        {isInternal && page === 'analytics' && <AnalyticsPage />}
        {isInternal && page === 'tools' && <ToolsPage />}
        {isInternal && page === 'admin' && <AdminPage />}
        </Suspense>
        </RouteErrorBoundary>
      </main>


      <nav className="bottom-nav" aria-label="Primary navigation">
        {bottomItems.map(item => (
          <a
            key={item.id}
            className={navPage === item.id ? 'active' : ''}
            href={moduleHref(item.id)}
            aria-current={navPage === item.id ? 'page' : undefined}
            onClick={navClick(item.id)}
          >
            <span aria-hidden="true"><NavIcon name={NAV_META[item.id].icon} /></span>
            {item.label}
          </a>
        ))}
        <button type="button" className="bottom-more" onClick={() => setPaletteOpen(true)} aria-haspopup="dialog" aria-expanded={paletteOpen}>
          <span aria-hidden="true">⌘</span>
          More
        </button>
      </nav>

      <CommandPalette open={paletteOpen} actions={commandActions} onClose={() => setPaletteOpen(false)} />
    </div>
  )
}

function routePage(pathname: string): Page {
  const path = pathname.replace(/\/$/, '')
  if (!path) return 'home'
  if (path === '/login') return 'login'
  if (path === '/reset-password') return 'reset-password'
  if (path === '/verify-email') return 'verify-email'
  if (path === '/upgrade') return 'upgrade'
  if (/^\/match\/\d+$/.test(path)) return 'match'
  // The former /matches page is now the "System picks" tab of Today.
  if (path === '/matches') return 'tickets'
  if (path === '/tickets' || path === '/live' || path === '/insights' || path === '/research') return path.slice(1) as ModulePage
  if (path === '/tracker' || path === '/analytics' || path === '/tools' || path === '/admin') return path.slice(1) as ModulePage
  return 'tickets'
}

function isInternalPage(page: Page): boolean {
  return page === 'research' || page === 'tracker' || page === 'analytics' || page === 'tools' || page === 'admin' || page === 'match'
}

function workspaceForPage(page: Page): Workspace | null {
  if (isInternalPage(page)) return 'research'
  if (page === 'tickets' || page === 'live' || page === 'insights') return 'football'
  return null
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
  // Keep old bookmarks working after the research tabs were consolidated.
  if (rawValue === 'acca-analysis' || rawValue === 'matches') return 'picks'
  const value = rawValue as ResearchTab | null
  return value && RESEARCH_TABS.includes(value) ? value : 'market-roi'
}

function overviewTabFromSearch(search: string): OverviewTab {
  const value = new URLSearchParams(search).get('tab')
  return value && OVERVIEW_TABS.includes(value as OverviewTab) ? value as OverviewTab : 'fixtures'
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
  if (pathname === '/matches') return 'Today'
  if (pathname === '/research') return 'Research'
  if (pathname === '/tracker') return 'Tracker'
  return 'Today'
}

