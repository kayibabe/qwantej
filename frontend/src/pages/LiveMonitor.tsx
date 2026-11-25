import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchMatchFixtures, formatDate, formatKickoff, type MatchFixture } from '../lib/api'
import { useFavoriteMatches } from './dailyTickets/useFavoriteMatches'
import { TODAY } from './dailyTickets/helpers'

const REFRESH_MS = 60_000

type StatusCounts = { live: number; pending: number; finished: number; other: number }
const EMPTY_COUNTS: StatusCounts = { live: 0, pending: 0, finished: 0, other: 0 }

function countStatuses(rows: MatchFixture[]): StatusCounts {
  const counts: StatusCounts = { ...EMPTY_COUNTS }
  for (const row of rows) {
    if (row.status === 'live') counts.live += 1
    else if (row.status === 'scheduled') counts.pending += 1
    else if (row.status === 'finished') counts.finished += 1
    else counts.other += 1
  }
  return counts
}

const phaseLabel = (fixture: MatchFixture) =>
  `${fixture.status === 'live' ? 'Live now' : fixture.status === 'scheduled' ? 'Pending' : fixture.status === 'finished' ? 'Finished' : fixture.status.replace(/_/g, ' ')} · ${fixture.live_phase?.replace(/_/g, ' ') ?? 'no phase reported'}`

export default function LiveMonitorPage() {
  const [fixtures, setFixtures] = useState<MatchFixture[]>([])
  const [counts, setCounts] = useState<StatusCounts>(EMPTY_COUNTS)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [lastChecked, setLastChecked] = useState<Date | null>(null)
  const [competition, setCompetition] = useState('all')
  const [favoriteOnly, setFavoriteOnly] = useState(false)
  const [alertsEnabled, setAlertsEnabled] = useState(false)
  const [alertMessage, setAlertMessage] = useState('')
  const { favoriteIds } = useFavoriteMatches()
  const previousFixtures = useRef<Map<number, MatchFixture> | null>(null)
  const requestId = useRef(0)
  const lastCheckedRef = useRef<Date | null>(null)
  // Refs keep the polling callback stable: toggling alerts or a favourite must
  // not trigger a second initial fetch or replace the visible cards with a
  // loading state.
  const alertsRef = useRef(alertsEnabled)
  const favoritesRef = useRef(favoriteIds)
  alertsRef.current = alertsEnabled
  favoritesRef.current = favoriteIds

  const refresh = useCallback(async (initial = false) => {
    const id = ++requestId.current
    if (initial) setLoading(true)
    else setRefreshing(true)
    const announce = (message: string) => { if (id === requestId.current) setAlertMessage(message) }
    try {
      const rows = await fetchMatchFixtures(TODAY)
      if (id !== requestId.current) return
      const nextFixtures = new Map(rows.map((fixture) => [fixture.match_id, fixture]))
      const previous = previousFixtures.current
      if (alertsRef.current && previous && typeof Notification !== 'undefined' && Notification.permission === 'granted') {
        for (const fixture of rows) {
          const old = previous.get(fixture.match_id)
          if (!favoritesRef.current.has(fixture.match_id) || !old) continue
          const scoreChanged = old.home_goals !== fixture.home_goals || old.away_goals !== fixture.away_goals
          const statusChanged = old.status !== fixture.status
          if (!scoreChanged && !statusChanged) continue
          const score = fixture.home_goals == null || fixture.away_goals == null
            ? 'Score unavailable'
            : `${fixture.home_goals}–${fixture.away_goals}`
          const phase = fixture.live_phase?.replace(/_/g, ' ') || fixture.status
          try {
            const notification = new Notification(`${fixture.home_team} vs ${fixture.away_team}`, {
              body: `${score} · ${phase}${fixture.elapsed_minutes == null ? '' : ` · ${fixture.elapsed_minutes}′`}`,
              tag: `qwantej-match-${fixture.match_id}`,
            })
            notification.onclick = () => {
              window.focus()
              window.location.href = `/match/${fixture.match_id}`
            }
          } catch {
            announce('A score change was observed, but the browser could not show its notification.')
          }
        }
      }
      previousFixtures.current = nextFixtures
      setFixtures(rows.filter((fixture) => fixture.status === 'live').sort((a, b) =>
        a.competition.localeCompare(b.competition) || a.kickoff_at.localeCompare(b.kickoff_at),
      ))
      setCounts(countStatuses(rows))
      setError('')
      const checkedAt = new Date()
      lastCheckedRef.current = checkedAt
      setLastChecked(checkedAt)
    } catch {
      if (id === requestId.current) setError(lastCheckedRef.current
        ? 'Could not refresh live fixtures. Showing the last successful check; these scores are stale.'
        : 'Could not load live fixtures. No live data is available yet.')
    } finally {
      if (id === requestId.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [])

  const competitions = [...new Set(fixtures.map((fixture) => fixture.competition))].sort()
  const liveFavoriteCount = fixtures.filter((fixture) => favoritesRef.current.has(fixture.match_id)).length
  const visibleFixtures = fixtures.filter((fixture) =>
    (competition === 'all' || fixture.competition === competition)
    && (!favoriteOnly || favoriteIds.has(fixture.match_id)),
  )
  const hasFilters = competition !== 'all' || favoriteOnly
  const isStale = Boolean(error && lastChecked)

  const toggleAlerts = async () => {
    if (alertsEnabled) {
      setAlertsEnabled(false)
      setAlertMessage('Score alerts paused for this page.')
      return
    }
    if (typeof Notification === 'undefined') {
      setAlertMessage('This browser does not support desktop notifications.')
      return
    }
    if (!window.isSecureContext) {
      setAlertMessage('Browser notifications require a secure connection.')
      return
    }
    try {
      const permission = Notification.permission === 'granted'
        ? 'granted'
        : await Notification.requestPermission()
      if (permission === 'granted') {
        setAlertsEnabled(true)
        setAlertMessage('Alerts enabled for favourited matches while this page is open.')
      } else {
        setAlertMessage('Notification permission was not granted.')
      }
    } catch {
      setAlertMessage('Could not request browser notification permission.')
    }
  }

  useEffect(() => {
    void refresh(true)
    const timer = window.setInterval(() => void refresh(), REFRESH_MS)
    return () => {
      requestId.current += 1
      window.clearInterval(timer)
    }
  }, [refresh])

  const controlButton = (active = false, disabled = false) =>
    `inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-semibold transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 ${
      disabled ? 'cursor-not-allowed opacity-50' : active ? 'border-emerald-700 bg-emerald-700 text-white' : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
    }`

  return (
    <section className="page-content space-y-4">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <span className="inline-flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-red-700"><span className="h-2 w-2 rounded-full bg-red-500 shadow-[0_0_0_3px_rgba(239,68,68,0.15)]" aria-hidden="true" /> Live centre</span>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Matches in play</h1>
          <p className="mt-1 max-w-3xl text-base leading-relaxed text-slate-600">Live scores and match phases from MatchSlip’s stored fixture status. This view checks for updates every minute and lists only live matches.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 self-start">
          {lastChecked && <span className={`text-sm ${isStale ? 'font-semibold text-amber-800' : 'text-slate-600'}`}>{isStale ? 'Last successful check' : 'View checked'} {lastChecked.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>}
          <button type="button" className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-emerald-700 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={() => void refresh()} disabled={refreshing}>
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>

      <div aria-live="polite" aria-atomic="true">
        {error && <p className={`rounded-xl border px-4 py-3 text-base leading-relaxed ${isStale ? 'border-amber-200 bg-amber-50 text-amber-900' : 'border-red-200 bg-red-50 text-red-700'}`} role="alert">{error}</p>}
        {alertMessage && <p className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-base leading-relaxed text-slate-700">{alertMessage}</p>}
      </div>
      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4">
        <label className="flex flex-col gap-1 text-sm font-semibold uppercase tracking-wide text-slate-600">Competition
          <select className="h-11 min-w-[220px] rounded-lg border border-slate-200 bg-white px-3 text-base font-medium normal-case tracking-normal text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-700/20 focus:border-emerald-700" value={competition} onChange={(event) => setCompetition(event.target.value)}>
            <option value="all">All competitions</option>
            {competitions.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
        <button type="button" className={controlButton(favoriteOnly, liveFavoriteCount === 0)} aria-pressed={favoriteOnly} onClick={() => setFavoriteOnly((value) => !value)} disabled={liveFavoriteCount === 0}>
          <span aria-hidden="true">★</span> Favourites in play <b className="font-mono tabular-nums">{liveFavoriteCount}</b>
        </button>
        <button type="button" className={controlButton(alertsEnabled)} aria-pressed={alertsEnabled} onClick={() => void toggleAlerts()}>
          {alertsEnabled ? 'Pause score alerts' : 'Enable score alerts'}
        </button>
        {hasFilters && <button type="button" className={controlButton()} onClick={() => { setCompetition('all'); setFavoriteOnly(false) }}>Clear filters</button>}
      </div>
      <p className="text-base text-slate-700" aria-live="polite">
        Status counts for today: <strong className="font-mono tabular-nums text-slate-900">{counts.live} live</strong>, <strong className="font-mono tabular-nums text-slate-900">{counts.pending} pending</strong>, <strong className="font-mono tabular-nums text-slate-900">{counts.finished} finished</strong>{counts.other > 0 && <>, <strong className="font-mono tabular-nums text-slate-900">{counts.other} other</strong></>}. Only live matches are listed below.
      </p>
      <div className="text-base text-slate-600"><strong className="font-mono tabular-nums text-slate-900">{visibleFixtures.length}</strong> of <strong className="font-mono tabular-nums text-slate-900">{fixtures.length}</strong> live matches today</div>
      {loading && !lastChecked ? <p className="rounded-xl border border-slate-200 bg-white p-8 text-center text-base text-slate-600" role="status">Loading live fixtures…</p> : fixtures.length === 0 ? (
        <p className="rounded-xl border border-slate-200 bg-white p-8 text-center text-base text-slate-600">No live fixtures are currently available. Pending and finished matches are not shown here; this page will check again automatically.</p>
      ) : visibleFixtures.length === 0 ? (
        <p className="rounded-xl border border-slate-200 bg-white p-8 text-center text-base text-slate-600">No live matches match these filters.</p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {visibleFixtures.map((fixture) => (
            <article className="overflow-hidden rounded-xl border border-slate-200 border-t-4 border-t-red-500 bg-white p-4" key={fixture.match_id}>
              <div className="flex flex-wrap items-start justify-between gap-2 text-sm text-slate-600">
                <span className="font-semibold uppercase tracking-wide text-slate-700">{fixture.competition}</span>
                <div className="flex flex-wrap items-center gap-2">
                  <span>Kickoff <time className="event-date font-mono tabular-nums text-slate-800" dateTime={fixture.kickoff_at}>{formatDate(fixture.kickoff_at)}</time> · <time className="kickoff-time font-mono tabular-nums text-slate-800" dateTime={fixture.kickoff_at}>{formatKickoff(fixture.kickoff_at)}</time></span>
                  <span className="inline-flex items-center gap-1.5 font-semibold text-red-700"><span className="h-1.5 w-1.5 rounded-full bg-red-500" aria-hidden="true" />{phaseLabel(fixture)}{fixture.elapsed_minutes != null ? ` · ${fixture.elapsed_minutes}′` : ''}</span>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3">
                <strong className="min-w-0 text-base font-semibold text-slate-900">{fixture.home_team}</strong>
                <b className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 font-mono text-base font-bold tabular-nums text-slate-900" aria-label={`Score ${fixture.home_goals ?? 'unavailable'} to ${fixture.away_goals ?? 'unavailable'}`}>{fixture.home_goals ?? '—'} <span className="text-slate-600">:</span> {fixture.away_goals ?? '—'}</b>
                <strong className="min-w-0 text-right text-base font-semibold text-slate-900">{fixture.away_team}</strong>
              </div>
              <a className="mt-4 inline-flex min-h-11 items-center gap-1 text-base font-semibold text-emerald-700 hover:text-emerald-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" href={`/match/${fixture.match_id}`}>Open match analysis <span aria-hidden="true">→</span></a>
            </article>
          ))}
        </div>
      )}
      <p className="text-base leading-relaxed text-slate-600">“View checked” is when this page last fetched its data; it is not the upstream provider’s feed timestamp. Score alerts run only while this page is open and use changes observed between checks.</p>
    </section>
  )
}
