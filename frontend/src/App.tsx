import { Component, lazy, Suspense, useEffect, useRef, useState, type ErrorInfo, type MouseEvent as ReactMouseEvent, type ReactNode } from 'react'
import { Menu, RefreshCw, Search, X } from 'lucide-react'
import { TODAY } from './pages/dailyTickets/helpers'
import { addDays } from './utils'
import { useAuth } from './auth'
import { fetchMarketCatalog, installMarketCatalog } from './lib/api'
import AccountMenu from './components/AccountMenu'
import CommandPalette, { type CommandAction } from './components/CommandPalette'
import { NAV_META, bottomNavItems, visibleNavItems, type ModulePage } from './shellNav'

const DailyTicketsPage = lazy(() => import('./pages/DailyTickets'))
const TrackerPage = lazy(() => import('./pages/Tracker'))
const AnalyticsPage = lazy(() => import('./pages/Analytics'))
const AdminPage = lazy(() => import('./pages/Admin'))
const UpgradePage = lazy(() => import('./pages/Upgrade'))
const MatchIntelligencePage = lazy(() => import('./pages/MatchIntelligencePage'))
const LoginPage = lazy(() => import('./pages/Login'))
const InsightsPage = lazy(() => import('./pages/Insights'))
const LiveMonitorPage = lazy(() => import('./pages/LiveMonitor'))
const PublicHome = lazy(() => import('./pages/PublicHome'))
const AccountRecoveryPage = lazy(() => import('./pages/AccountRecovery'))

function PageLoading() {
  return <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-base leading-relaxed text-slate-600 animate-pulse" role="status" aria-live="polite">Loading page…</div>
}

type Page = ModulePage | 'home' | 'match' | 'upgrade' | 'login' | 'reset-password' | 'verify-email'
type Workspace = 'football' | 'research'
type ResearchTab = 'picks' | 'odds-policy' | 'market-roi' | 'passed'
const RESEARCH_TABS: ResearchTab[] = ['picks', 'odds-policy', 'market-roi', 'passed']
type OverviewTab = 'fixtures' | 'picks' | 'tickets' | 'passed'
const OVERVIEW_TABS: OverviewTab[] = ['fixtures', 'picks', 'tickets', 'passed']
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
      return <section className="rounded-xl border border-red-200 bg-red-50 p-8 text-center space-y-3" role="alert">
        <h1 className="text-xl font-bold tracking-tight text-slate-900">This page could not be displayed</h1>
        <p className="text-base leading-relaxed text-slate-600">Your navigation is still available. Try this page again or open another section.</p>
        <button className="inline-flex min-h-11 items-center justify-center rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 cursor-pointer" onClick={this.props.onRetry}>Try this page again</button>
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

function pageTitle(page: Page): string {
  switch (page) {
    case 'tickets': return 'Today'
    case 'live': return 'Live'
    case 'insights': return 'Stats & trends'
    case 'research': return 'Research'
    case 'tracker': return 'Track'
    case 'analytics': return 'Validate'
    case 'admin': return 'Admin'
    case 'match': return 'Match intelligence'
    case 'upgrade': return 'Plans'
    default: return 'Workspace'
  }
}

function displayDate(value: string): string {
  return new Date(`${value}T12:00:00`).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
}

function NavIcon({ name }: { name: string }) {
  const paths: Record<string, ReactNode> = {
    sparkles: <><path d="m12 3-1.2 4.1L7 8.3l3.8 1.2L12 13l1.2-3.5L17 8.3l-3.8-1.2L12 3Z" /><path d="m5 14-.7 2.3L2 17l2.3.7L5 20l.7-2.3L8 17l-2.3-.7L5 14Z" /></>,
    list: <><path d="m4 6 1.5 1.5L8 5" /><path d="M11 6h9M11 12h9M11 18h9" /><path d="m4 12 1.5 1.5L8 11" /><path d="m4 18 1.5 1.5L8 17" /></>,
    chart: <><path d="M5 20V10M12 20V4M19 20v-7" /></>,
    activity: <><path d="M3 12h4l3-8 4 16 3-8h4" /></>,
    search: <><circle cx="10.8" cy="10.8" r="6.6" /><path d="m16 16 4.5 4.5" /></>,
    flask: <><path d="M9 3h6M10 3v6l-5.2 8.5A2.3 2.3 0 0 0 6.8 21h10.4a2.3 2.3 0 0 0 2-3.5L14 9V3" /><path d="M7.7 15h8.6" /></>,
    shield: <><path d="M12 3 20 6v5c0 5-3.4 8.6-8 10-4.6-1.4-8-5-8-10V6l8-3Z" /><path d="m9 12 2 2 4-4" /></>,
  }
  return <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>
}

function BrandMark({ className = '', showTagline = true }: { className?: string; showTagline?: boolean }) {
  return <span className={`inline-flex items-center gap-2 ${className}`.trim()}>
    <img src="/icons/light/icon-128.png" alt="" className="h-8 w-8 rounded-lg" />
    <span className="flex flex-col">
      <strong className="font-display text-base leading-6 font-bold tracking-tight text-slate-900">QwantEj</strong>
      {showTagline && <small className="text-sm leading-5 font-medium text-slate-600">Built on evidence, not hunches.</small>}
    </span>
  </span>
}

/**
 * The desktop and mobile headers each render their own copy. Distinct group
 * names keep the two copies unambiguous without hiding either from assistive
 * technology; only the inactive breakpoint is removed from layout/display.
 */
function DateNav({ date, onChange, context }: { date: string; onChange: (value: string) => void; context: 'desktop' | 'mobile' }) {
  return <div className="flex items-center gap-1.5 overflow-x-auto" role="group" aria-label={`${context === 'desktop' ? 'Desktop' : 'Mobile'} date controls`}>
    <button className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-xl text-slate-600 transition-colors hover:bg-slate-50 hover:text-slate-900 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={() => onChange(addDays(date, -1))} title="Previous day" aria-label="Previous day">‹</button>
    <div className="inline-flex max-w-full items-center gap-0.5 overflow-x-auto rounded-xl border border-slate-200 bg-white p-1" role="group" aria-label="Choose match date">
      {[-2, -1, 0, 1, 2].map(offset => {
        const value = addDays(date, offset)
        const localDate = new Date(`${value}T12:00:00`)
        const label = localDate.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
        const active = date === value
        return <button
          key={value}
          className={`flex min-h-11 min-w-11 flex-col items-center justify-center rounded-lg px-2 py-1.5 text-sm leading-5 transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 ${active ? 'bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-700' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'}`}
          onClick={() => onChange(value)}
          aria-label={label}
          aria-pressed={active}
        >
          <span className="font-medium">{value === TODAY ? 'Today' : localDate.toLocaleDateString('en-GB', { weekday: 'short' })}</span>
          <b className="font-mono tabular-nums text-base leading-5">{localDate.getDate()}</b>
        </button>
      })}
    </div>
    <div className="flex items-center gap-1.5">
      {date !== TODAY && <button className="inline-flex min-h-11 items-center justify-center whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold uppercase tracking-wide text-emerald-700 transition-colors hover:border-emerald-700 hover:bg-emerald-50 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={() => onChange(TODAY)} aria-label="Jump to today">Today</button>}
      <label className="relative inline-flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 transition-colors hover:border-emerald-700 hover:text-emerald-700 focus-within:border-emerald-700 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-emerald-700" title="Choose any date">
        <span aria-hidden="true" className="text-base">▦</span>
        <input
          className="date-input-overlay"
          type="date"
          value={date}
          aria-label="Choose any date"
          onChange={event => onChange(event.target.value)}
        />
      </label>
    </div>
    <button className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-xl text-slate-600 transition-colors hover:bg-slate-50 hover:text-slate-900 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={() => onChange(addDays(date, 1))} title="Next day" aria-label="Next day">›</button>
  </div>
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
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [, setMarketCatalogLoaded] = useState(false)
  const mobileMenuButtonRef = useRef<HTMLButtonElement>(null)
  const mobileNavRef = useRef<HTMLDivElement>(null)

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
    if (!mobileNavOpen) return
    const onDrawerKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setMobileNavOpen(false)
        return
      }
      if (event.key !== 'Tab') return
      const focusable = Array.from(mobileNavRef.current?.querySelectorAll<HTMLElement>('a[href], button:not([disabled])') ?? [])
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onDrawerKeyDown)
    mobileNavRef.current?.querySelector<HTMLElement>('nav a')?.focus()
    return () => {
      document.removeEventListener('keydown', onDrawerKeyDown)
      mobileMenuButtonRef.current?.focus()
    }
  }, [mobileNavOpen])

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
  }, [authLoading, isInternal, page, user])

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
    setMobileNavOpen(false)
    navigate(next)
  }

  function navigateResearch(tab: ResearchTab, replace = false) {
    setResearchTab(tab)
    setPage('research')
    const method = replace ? 'replaceState' : 'pushState'
    window.history[method]({}, '', datePath('/research', date, { tab }))
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

  const navPage = page === 'match' ? routePage(new URL(matchReturnTo || '/tickets', window.location.origin).pathname) : page
  const workspace: Workspace = page === 'match'
    ? workspaceForPage(routePage(new URL(matchReturnTo || '/tickets', window.location.origin).pathname)) ?? 'football'
    : workspaceForPage(page) ?? 'football'

  if (authLoading) {
    return <div className="flex min-h-screen items-center justify-center bg-slate-50 text-base leading-relaxed text-slate-600" role="status" aria-live="polite">Checking your session…</div>
  }

  if (page === 'reset-password' || page === 'verify-email') {
    return (
      <div className="min-h-screen bg-slate-50">
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
      return <div className="min-h-screen bg-slate-50"><Suspense fallback={<PageLoading />}><UpgradePage
        anonymous
        onBack={() => navigate('home')}
        onSignIn={() => { setPage('login'); window.history.pushState({}, '', '/login?next=upgrade') }}
        onCreateAccount={() => { setPage('login'); window.history.pushState({}, '', '/login?mode=register&next=upgrade') }}
      /></Suspense></div>
    }
    return <div className="min-h-screen bg-slate-50"><Suspense fallback={<PageLoading />}><LoginPage onSuccess={() => {
      const next = new URLSearchParams(window.location.search).get('next')
      navigate(next === 'upgrade' ? 'upgrade' : 'tickets', undefined, true)
    }} /></Suspense></div>
  }

  if (page === 'home' || page === 'login') {
    return <div className="flex min-h-screen items-center justify-center bg-slate-50 text-base leading-relaxed text-slate-600" role="status" aria-live="polite">Opening your workspace...</div>
  }

  const visibleNav = visibleNavItems(isInternal)

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

  const bottomItems = bottomNavItems(isInternal, navPage)

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
    { id: 'refresh-view', label: 'Refresh this view', group: 'Workspace', hint: 'Reload data without leaving the page', keywords: 'reload retry sync', onRun: refreshWorkspace },
    ...(isInternal ? [
      { id: 'today-picks', label: 'Open system picks', group: 'Today', hint: 'Qualified selections for the selected date', keywords: 'today candidates', onRun: () => openOverviewTab('picks') },
      { id: 'today-tickets', label: 'Open accumulator tickets', group: 'Today', hint: 'Published tiers for the selected date', keywords: 'today acca', onRun: () => openOverviewTab('tickets') },
      { id: 'today-rejected', label: 'Open rejection ledger', group: 'Today', hint: 'Why candidates were passed', keywords: 'today passed why', onRun: () => openOverviewTab('passed') },
    ] : []),
  ]

  const navLinkClass = (active: boolean) => `flex min-h-11 items-center gap-2.5 rounded-lg px-3 py-2 text-sm leading-6 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 ${active ? 'bg-emerald-50 font-semibold text-emerald-800' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'}`

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <a href="#main-content" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:inline-flex focus:min-h-11 focus:items-center focus:rounded-lg focus:bg-emerald-700 focus:px-3 focus:text-sm focus:font-semibold focus:text-white focus:outline-2 focus:outline-offset-2 focus:outline-emerald-700">Skip to content</a>

      <aside className="fixed top-0 bottom-0 left-0 z-30 hidden page-menu flex-col border-r border-slate-200 bg-white sm:flex">
        <a className="flex h-16 items-center border-b border-slate-200 px-4" href={moduleHref('tickets')} aria-label="QwantEj home" onClick={navClick('tickets')}>
          <BrandMark />
        </a>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4" aria-label="Primary navigation">
          {visibleNav.map(item => (
            <a
              key={item.id}
              className={navLinkClass(navPage === item.id)}
              href={moduleHref(item.id)}
              title={NAV_META[item.id].hint}
              aria-current={navPage === item.id ? 'page' : undefined}
              onClick={navClick(item.id)}
            >
              <span aria-hidden="true" className={navPage === item.id ? 'text-emerald-700' : 'text-slate-400'}><NavIcon name={NAV_META[item.id].icon} /></span>
              <span>{item.label}</span>
            </a>
          ))}
        </nav>

        <div className="border-t border-slate-200 px-4 py-4 space-y-3">
          <span className="inline-flex items-center gap-2 text-sm leading-5 font-semibold uppercase tracking-wide text-slate-600"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden="true" />{isInternal ? 'Paper-trading workspace' : 'Dated publishing record'}</span>
          <p className="text-sm leading-relaxed text-slate-600">{isInternal || user?.plan === 'pro' ? 'Evidence stays with every published pick.' : 'Pro adds prices and leg evidence.'}</p>
          <button type="button" className="flex min-h-11 w-full items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium leading-5 text-slate-600 transition-colors hover:bg-white hover:text-slate-900 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={() => setPaletteOpen(true)}>
            <span>Search or jump</span><kbd className="rounded border border-slate-200 bg-white px-1.5 py-0.5 font-mono text-sm text-slate-600">⌘K</kbd>
          </button>
        </div>
      </aside>

      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white sm:ml-[var(--page-menu-width)] lg:ml-[var(--page-menu-width-lg)]">
        <div className="flex h-16 items-center gap-3 px-3 sm:px-4">
          <button ref={mobileMenuButtonRef} type="button" className="inline-flex h-11 w-11 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 transition-colors hover:bg-slate-50 sm:hidden cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={() => setMobileNavOpen(true)} aria-label="Open navigation" aria-expanded={mobileNavOpen} aria-controls={mobileNavOpen ? 'mobile-workspace-navigation' : undefined}>
            <Menu className="h-5 w-5" aria-hidden="true" />
          </button>
          <a className="flex items-center sm:hidden" href={moduleHref('tickets')} aria-label="QwantEj home" onClick={navClick('tickets')}>
            <img src="/icons/light/icon-128.png" alt="" className="h-8 w-8 rounded-lg" />
          </a>

          <div className="min-w-0 flex-1">
            <div className="hidden text-sm leading-5 font-semibold uppercase tracking-wide text-slate-600 sm:block">{workspace === 'research' ? 'Research workspace' : 'Football workspace'}</div>
            <div className="text-base leading-6 font-bold tracking-tight text-slate-900">{pageTitle(page)}</div>
          </div>

          {showDateNav && <div className="hidden lg:block"><DateNav date={date} onChange={setDate} context="desktop" /></div>}

          <div className="flex items-center gap-2">
            <button
              type="button"
              className="hidden min-h-11 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium leading-5 text-slate-600 transition-colors hover:bg-slate-50 hover:text-slate-900 sm:inline-flex cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
              onClick={() => setPaletteOpen(true)}
              aria-haspopup="dialog"
              aria-expanded={paletteOpen}
              aria-label="Open command palette"
            >
              <Search className="h-5 w-5" aria-hidden="true" />
              <span>Search</span>
              <kbd className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-sm text-slate-600">⌘K</kbd>
            </button>
            <button type="button" className="inline-flex h-11 w-11 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 transition-colors hover:bg-slate-50 hover:text-slate-900 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={refreshWorkspace} title="Refresh this view" aria-label="Refresh this view">
              <RefreshCw className="h-5 w-5" aria-hidden="true" />
            </button>
            <AccountMenu
              onRefresh={refreshWorkspace}
              onOpenPalette={() => setPaletteOpen(true)}
              onUpgrade={() => navigate('upgrade')}
              onSignIn={() => navigate('login')}
              onSignedOut={() => navigate('login', undefined, true)}
            />
          </div>
        </div>
        {showDateNav && <div className="border-t border-slate-200 px-3 py-2 lg:hidden sm:px-4"><DateNav date={date} onChange={setDate} context="mobile" /></div>}
      </header>

      {mobileNavOpen && (
        <div className="fixed inset-0 z-50 sm:hidden">
          <button type="button" className="absolute inset-0 bg-slate-900/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)} />
          <div ref={mobileNavRef} id="mobile-workspace-navigation" className="absolute inset-y-0 left-0 flex w-[min(18rem,85vw)] flex-col border-r border-slate-200 bg-white shadow-2xl">
            <div className="flex h-16 items-center justify-between border-b border-slate-200 px-4">
              <BrandMark showTagline={false} />
              <button type="button" className="inline-flex h-11 w-11 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={() => setMobileNavOpen(false)} aria-label="Close navigation"><X className="h-5 w-5" aria-hidden="true" /></button>
            </div>
            <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4" aria-label="Mobile navigation">
              {visibleNav.map(item => (
                <a key={item.id} className={navLinkClass(navPage === item.id)} href={moduleHref(item.id)} aria-current={navPage === item.id ? 'page' : undefined} onClick={navClick(item.id)}>
                  <span aria-hidden="true" className={navPage === item.id ? 'text-emerald-700' : 'text-slate-400'}><NavIcon name={NAV_META[item.id].icon} /></span>
                  <span>{item.label}</span>
                </a>
              ))}
            </nav>
          </div>
        </div>
      )}

      <main className="page-inset-app py-6 pb-24 sm:py-8 sm:pb-8" id="main-content" tabIndex={-1}>
        <RouteErrorBoundary key={`${page}-${routeAttempt}`} onRetry={() => setRouteAttempt(attempt => attempt + 1)}>
        <Suspense fallback={<PageLoading />}>
        {page === 'upgrade' && <UpgradePage onBack={() => goTo('tickets')} />}
        {page === 'tickets' && <DailyTicketsPage key={`${date}-${page}`} date={date} initialTab={overviewTab} mode="overview" onTabChange={tab => updateOverviewTab(tab as OverviewTab)} onOpenMatch={navigateToMatch} onUpgrade={() => navigate('upgrade')} />}
        {page === 'live' && <LiveMonitorPage />}
        {page === 'insights' && (user.plan === 'pro' || isInternal
          ? <InsightsPage />
          : <section className="mx-auto max-w-2xl rounded-xl border border-slate-200 bg-white p-8 text-center space-y-3" aria-labelledby="insights-pro-gate-title">
              <span className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-sm leading-5 font-semibold uppercase tracking-wide text-emerald-700">Pro</span>
              <h1 id="insights-pro-gate-title" className="text-2xl font-bold tracking-tight text-slate-900">Stats &amp; trends is part of Pro</h1>
              <p className="text-base leading-relaxed text-slate-600">Review league results, team form and historical performance alongside the picks and tickets they came from.</p>
              <div className="flex flex-wrap items-center justify-center gap-2 pt-2">
                <button className="inline-flex min-h-11 items-center justify-center rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-800 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={() => navigate('upgrade')}>Upgrade to Pro</button>
                <button className="inline-flex min-h-11 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={() => navigate('tickets')}>Back to Today</button>
              </div>
            </section>)}
        {isInternal && page === 'research' && <DailyTicketsPage key={`${date}-${page}`} date={date} initialTab={researchTab} mode="research" onTabChange={tab => navigateResearch(tab as ResearchTab)} onOpenMatch={navigateToMatch} />}
        {page === 'match' && matchId != null && (user?.plan === 'pro' || isInternal) && <MatchIntelligencePage matchId={matchId} selectedPredictionId={predictionId} onBack={returnFromMatch} returnLabel={matchReturnLabel(matchReturnTo)} />}
        {page === 'match' && matchId != null && user?.plan !== 'pro' && !isInternal && (
          <section className="mx-auto max-w-2xl rounded-xl border border-slate-200 bg-white p-8 text-center space-y-3" aria-labelledby="match-pro-gate-title">
            <span className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-sm leading-5 font-semibold uppercase tracking-wide text-emerald-700">Pro</span>
            <h1 id="match-pro-gate-title" className="text-2xl font-bold tracking-tight text-slate-900">Match intelligence is part of Pro</h1>
            <p className="text-base leading-relaxed text-slate-600">Open every qualified selection for this match with its captured price, model chance, spread and recorded evidence.</p>
            <div className="flex flex-wrap items-center justify-center gap-2 pt-2">
              <button className="inline-flex min-h-11 items-center justify-center rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-800 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={() => navigate('upgrade')}>Upgrade to Pro</button>
              <button className="inline-flex min-h-11 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={returnFromMatch}>Back to {matchReturnLabel(matchReturnTo)}</button>
            </div>
          </section>
        )}
        {page === 'tracker' && <TrackerPage isInternal={isInternal} onOpenValidation={isInternal ? () => goTo('analytics') : undefined} />}
        {isInternal && page === 'analytics' && <AnalyticsPage />}
        {isInternal && page === 'admin' && <AdminPage />}
        </Suspense>
        </RouteErrorBoundary>
      </main>

      <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white/95 px-2 pb-[env(safe-area-inset-bottom)] backdrop-blur sm:hidden" aria-label="Primary navigation">
        <div className="mx-auto grid max-w-lg grid-cols-4 gap-1 py-2">
          {bottomItems.map(item => {
            const active = navPage === item.id
            return <a
              key={item.id}
              className={`flex min-h-11 min-w-11 flex-col items-center justify-center gap-0.5 rounded-lg px-2 py-1.5 text-sm leading-5 font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 ${active ? 'bg-emerald-50 text-emerald-700' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'}`}
              href={moduleHref(item.id)}
              aria-current={active ? 'page' : undefined}
              onClick={navClick(item.id)}
            >
              <span aria-hidden="true"><NavIcon name={NAV_META[item.id].icon} /></span>
              {item.label}
            </a>
          })}
          <button type="button" className="flex min-h-11 min-w-11 flex-col items-center justify-center gap-0.5 rounded-lg px-2 py-1.5 text-sm leading-5 font-medium text-slate-600 transition-colors hover:bg-slate-50 hover:text-slate-900 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={() => setPaletteOpen(true)} aria-haspopup="dialog" aria-expanded={paletteOpen} aria-label="More commands">
            <span aria-hidden="true" className="font-mono text-sm leading-5">⌘</span>
            More
          </button>
        </div>
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
  if (path === '/tracker' || path === '/analytics' || path === '/admin') return path.slice(1) as ModulePage
  return 'tickets'
}

function isInternalPage(page: Page): boolean {
  return page === 'research' || page === 'analytics' || page === 'admin' || page === 'match'
}

function workspaceForPage(page: Page): Workspace | null {
  // Tracker is readable by everyone but keeps the research workspace styling.
  if (isInternalPage(page) || page === 'tracker') return 'research'
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
  if (rawValue === 'daily-match-picks') return 'market-roi'
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
