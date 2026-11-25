import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { fetchPublicMatchFixtures, fetchPublicProof, formatMarket, formatSelection, selectionRepeatsMarket } from '../lib/api'
import type { MatchFixture, PublicProof, PublicProofEquityPoint } from '../lib/api'
import { TODAY } from './dailyTickets/helpers'

interface PublicHomeProps {
  date: string
  onDateChange: (date: string) => void
  onSignIn: () => void
  onCreateAccount: () => void
  onViewPro: () => void
}

interface ProOffer {
  price: string
  currency: string
  interval: string
  checkout_enabled: boolean
}

function formatProPrice(price: string | undefined) {
  const amount = Number(price)
  if (!Number.isFinite(amount)) return 'K20,000.00'
  return `K${amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

type FixtureSortKey = 'kickoff' | 'league' | 'match' | 'statusScore'
type SortDirection = 'asc' | 'desc'

function shiftDate(date: string, amount: number) {
  const value = new Date(`${date}T12:00:00`)
  value.setDate(value.getDate() + amount)
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
}

function kickoffLabel(value: string) {
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function formatProofDate(value: string | null) {
  if (!value) return '—'
  return new Date(`${value}T12:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

function formatProofDateTime(value: string) {
  return new Date(value).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

function proofPercent(value: number | null) {
  return value == null ? '—' : `${Math.round(value * 100)}%`
}

type ProofRange = 7 | 30 | 90 | null

const PROOF_RANGES: { value: ProofRange; label: string }[] = [
  { value: 7, label: '7D' },
  { value: 30, label: '30D' },
  { value: 90, label: '90D' },
  { value: null, label: 'All' },
]

function formatUnits(value: number) {
  const rounded = Math.abs(value) < 0.005 ? 0 : value
  const sign = rounded > 0 ? '+' : rounded < 0 ? '−' : ''
  return `${sign}${Math.abs(rounded).toFixed(2)}u`
}

function formatRoi(value: number | null) {
  if (value == null) return '—'
  const percent = value * 100
  const rounded = Math.abs(percent) < 0.05 ? 0 : percent
  const sign = rounded > 0 ? '+' : rounded < 0 ? '−' : ''
  return `${sign}${Math.abs(rounded).toFixed(1)}%`
}

function profitTone(value: number | null) {
  if (value == null || Math.abs(value) < 0.005) return 'text-slate-600'
  return value > 0 ? 'text-emerald-700' : 'text-red-600'
}

function matchCountLabel(count: number) {
  return `${count} ${count === 1 ? 'match' : 'matches'}`
}

function proofResult(value: string | null) {
  if (value === 'won') return 'Won'
  if (value === 'lost') return 'Lost'
  if (value === 'void') return 'Void'
  return 'Pending'
}

function legMarketLabel(market: string, selection: string) {
  if (market.startsWith('double_chance')) return formatSelection(selection)
  return selectionRepeatsMarket(market, selection)
    ? formatSelection(selection)
    : `${formatMarket(market)}: ${formatSelection(selection)}`
}

function EquitySparkline({ points, label }: { points: PublicProofEquityPoint[]; label: string }) {
  if (points.length < 2) {
    return <p className="rounded-lg border border-dashed border-slate-300 px-3 py-4 text-center text-base leading-relaxed text-slate-700">The equity line appears once this range has two settled matchdays.</p>
  }
  const width = 340
  const height = 76
  const padX = 4
  const padY = 9
  const values = points.map((point) => point.cumulative_units)
  const floor = Math.min(0, ...values)
  const ceiling = Math.max(0, ...values)
  const span = ceiling - floor || 1
  const stepX = (width - padX * 2) / (points.length - 1)
  const yFor = (value: number) => padY + (height - padY * 2) * (1 - (value - floor) / span)
  const line = points
    .map((point, index) => `${index === 0 ? 'M' : 'L'}${(padX + index * stepX).toFixed(1)},${yFor(point.cumulative_units).toFixed(1)}`)
    .join(' ')
  const last = points[points.length - 1]
  return (
    <figure className="m-0">
      <svg className="block h-auto w-full overflow-visible" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${label} cumulative paper result across ${points.length} settled matchdays`}>
        <line className="stroke-slate-200" strokeDasharray="3 4" x1={padX} x2={width - padX} y1={yFor(0)} y2={yFor(0)} />
        <path className="stroke-emerald-700" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d={line} fill="none" />
        <circle className="fill-emerald-700 stroke-white" strokeWidth="1.5" cx={width - padX} cy={yFor(last.cumulative_units)} r="3.2" />
      </svg>
      <figcaption className="mt-2 flex flex-wrap justify-between gap-2 text-sm leading-normal text-slate-600"><span>{formatProofDate(points[0].date)}</span><span>{formatProofDate(last.date)}</span></figcaption>
    </figure>
  )
}

function matchStatus(match: MatchFixture) {
  const status = match.status.toLowerCase()
  if (status === 'live') return match.elapsed_minutes != null ? `${match.elapsed_minutes}\u2032` : match.live_phase || 'Live'
  if (status === 'finished') return 'FT'
  if (status === 'postponed') return 'Postponed'
  if (status === 'cancelled') return 'Cancelled'
  if (status === 'abandoned') return 'Abandoned · review'
  if (status === 'awarded') return 'Awarded · review'
  return 'Upcoming'
}

export default function PublicHome({ date, onDateChange, onSignIn, onCreateAccount, onViewPro }: PublicHomeProps) {
  const [matches, setMatches] = useState<MatchFixture[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null)
  const [activeStatus, setActiveStatus] = useState<'all' | 'live' | 'scheduled' | 'finished'>('all')
  const [search, setSearch] = useState('')
  const [selectedLeague, setSelectedLeague] = useState('')
  const [showAllMatches, setShowAllMatches] = useState(false)
  const [sortKey, setSortKey] = useState<FixtureSortKey>('kickoff')
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')
  const [offer, setOffer] = useState<ProOffer | null>(null)
  const [proof, setProof] = useState<PublicProof | null>(null)
  const [proofStatus, setProofStatus] = useState<'loading' | 'ready' | 'unavailable'>('loading')
  const [proofAttempt, setProofAttempt] = useState(0)
  const [proofDays, setProofDays] = useState<ProofRange>(null)
  const [proofRefreshing, setProofRefreshing] = useState(false)
  const [preferredTier, setPreferredTier] = useState<string | null>(null)
  const [ticketCursor, setTicketCursor] = useState(0)
  const [activeSection, setActiveSection] = useState('public-record')

  useEffect(() => {
    let active = true
    fetch('/api/v1/billing/offer')
      .then(response => response.ok ? response.json() : Promise.reject())
      .then((data: ProOffer) => { if (active) setOffer(data) })
      .catch(() => { /* Pricing falls back to the published default. */ })
    return () => { active = false }
  }, [])

  const proofRef = useRef<PublicProof | null>(null)
  proofRef.current = proof

  useEffect(() => {
    let active = true
    if (!proofRef.current) setProofStatus('loading')
    setProofRefreshing(true)
    fetchPublicProof(proofDays)
      .then((data) => { if (active) { setProof(data); setProofStatus('ready') } })
      .catch(() => { if (active) { setProof(null); setProofStatus('unavailable') } })
      .finally(() => { if (active) setProofRefreshing(false) })
    return () => { active = false }
  }, [proofAttempt, proofDays])

  useEffect(() => {
    const ids = ['public-record', 'public-matches', 'public-product', 'public-access', 'public-faq']
    let frame = 0
    const update = () => {
      frame = 0
      const sections = ids
        .map(id => document.getElementById(id))
        .filter((section): section is HTMLElement => section != null)
      if (!sections.length) return
      let next = sections[0].id
      for (const section of sections) {
        if (section.getBoundingClientRect().top <= 160) next = section.id
      }
      if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) {
        next = sections[sections.length - 1].id
      }
      setActiveSection(next)
    }
    const onScroll = () => { if (!frame) frame = window.requestAnimationFrame(update) }
    update()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      if (frame) window.cancelAnimationFrame(frame)
    }
  }, [])

  const latestRequest = useRef(0)
  const requestDate = useRef(date)
  requestDate.current = date

  const loadFixtures = useCallback(async (silent = false) => {
    const request = latestRequest.current + 1
    latestRequest.current = request
    const requestedDate = requestDate.current
    if (!silent) {
      setLoading(true)
      setError(false)
    }
    try {
      const rows = await fetchPublicMatchFixtures(requestedDate)
      if (request !== latestRequest.current) return
      setMatches(rows)
      setError(false)
      setRefreshedAt(new Date())
    } catch {
      if (request !== latestRequest.current) return
      if (!silent) {
        setMatches([])
        setError(true)
      }
    } finally {
      if (request === latestRequest.current && !silent) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadFixtures()
  }, [date, loadFixtures])

  const today = TODAY
  const needle = search.trim().toLocaleLowerCase()
  const searchedMatches = useMemo(() => !needle ? matches : matches.filter((match) => `${match.home_team} ${match.away_team} ${match.competition}`.toLocaleLowerCase().includes(needle)), [matches, needle])
  const statusCounts = useMemo(() => {
    const scoped = searchedMatches.filter((match) => !selectedLeague || match.competition === selectedLeague)
    return {
      all: scoped.length,
      live: scoped.filter((match) => match.status.toLowerCase() === 'live').length,
      scheduled: scoped.filter((match) => match.status.toLowerCase() === 'scheduled').length,
      finished: scoped.filter((match) => match.status.toLowerCase() === 'finished').length,
    }
  }, [searchedMatches, selectedLeague])
  const leagueScopeTotal = useMemo(
    () => searchedMatches.filter((match) => activeStatus === 'all' || match.status.toLowerCase() === activeStatus).length,
    [searchedMatches, activeStatus],
  )
  const leagueMatchCounts = useMemo(() => {
    const scoped = searchedMatches.filter((match) => activeStatus === 'all' || match.status.toLowerCase() === activeStatus)
    const counts = new Map<string, number>()
    for (const match of scoped) counts.set(match.competition, (counts.get(match.competition) ?? 0) + 1)
    const rows = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    if (selectedLeague && !rows.some(([league]) => league === selectedLeague)) rows.unshift([selectedLeague, 0])
    return rows
  }, [searchedMatches, activeStatus, selectedLeague])
  const visibleMatches = useMemo(() => {
    const filtered = searchedMatches.filter((match) => {
      const status = match.status.toLowerCase()
      const statusMatch = activeStatus === 'all' || status === activeStatus
      const leagueMatch = !selectedLeague || match.competition === selectedLeague
      return statusMatch && leagueMatch
    })
    const direction = sortDirection === 'asc' ? 1 : -1
    return filtered.sort((a, b) => {
      let order = 0
      if (sortKey === 'kickoff') order = a.kickoff_at.localeCompare(b.kickoff_at)
      if (sortKey === 'league') order = a.competition.localeCompare(b.competition, undefined, { numeric: true, sensitivity: 'base' })
      if (sortKey === 'match') order = `${a.home_team} ${a.away_team}`.localeCompare(`${b.home_team} ${b.away_team}`, undefined, { numeric: true, sensitivity: 'base' })
      if (sortKey === 'statusScore') order = `${matchStatus(a)} ${a.home_goals ?? ''} ${a.away_goals ?? ''}`.localeCompare(`${matchStatus(b)} ${b.home_goals ?? ''} ${b.away_goals ?? ''}`, undefined, { numeric: true, sensitivity: 'base' })
      return order * direction || a.kickoff_at.localeCompare(b.kickoff_at)
    })
  }, [searchedMatches, activeStatus, selectedLeague, sortKey, sortDirection])
  const displayedMatches = showAllMatches ? visibleMatches : visibleMatches.slice(0, 5)

  useEffect(() => {
    setShowAllMatches(false)
  }, [date, activeStatus, search, selectedLeague])

  const shouldPoll = date === today || matches.some((match) => match.status.toLowerCase() === 'live')

  useEffect(() => {
    if (!shouldPoll) return
    const refresh = () => { void loadFixtures(true) }
    const interval = window.setInterval(refresh, 30000)
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') refresh()
    }
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => {
      window.clearInterval(interval)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [shouldPoll, loadFixtures])

  const activeTier = useMemo(() => {
    if (!proof) return null
    return proof.tiers.find((tier) => tier.ticket_type === preferredTier)
      ?? proof.tiers.find((tier) => tier.ticket_type === proof.latest_ticket?.ticket_type)
      ?? proof.tiers[0]
      ?? null
  }, [proof, preferredTier])
  const activeTickets = activeTier?.recent_tickets ?? []
  const activeTicketCursor = Math.min(ticketCursor, Math.max(activeTickets.length - 1, 0))
  const activeTicket = activeTickets[activeTicketCursor] ?? proof?.latest_ticket ?? null

  useEffect(() => {
    setTicketCursor(0)
  }, [activeTier?.ticket_type, proofDays])

  const selectProofRange = (value: ProofRange) => {
    setProofDays(value)
    setTicketCursor(0)
  }

  const selectProofTier = (value: string) => {
    setPreferredTier(value)
    setTicketCursor(0)
  }

  const selectStatus = (status: 'all' | 'live' | 'scheduled' | 'finished') => {
    if (status === 'live' && date !== today) onDateChange(today)
    setActiveStatus(status)
  }

  const selectDate = (nextDate: string) => {
    if (activeStatus === 'live' && nextDate !== today) setActiveStatus('all')
    onDateChange(nextDate)
  }

  const focusRingClass = 'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700'
  const sortHeader = (key: FixtureSortKey, label: string) => {
    const active = sortKey === key
    const ariaSort = active ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'
    return (
      <th scope="col" aria-sort={ariaSort} className="px-3 py-2 text-left">
        <button className={`inline-flex min-h-11 items-center gap-1.5 rounded px-2 text-sm font-semibold leading-normal text-slate-700 transition-colors hover:text-slate-900 cursor-pointer ${focusRingClass}`} onClick={() => {
          if (active) setSortDirection(current => current === 'asc' ? 'desc' : 'asc')
          else { setSortKey(key); setSortDirection('asc') }
        }}>{label}<span aria-hidden="true" className={active ? 'text-emerald-700' : 'text-slate-600'}>{active ? (sortDirection === 'asc' ? '↑' : '↓') : '↕'}</span></button>
      </th>
    )
  }

  const sectionKickerClass = 'text-sm font-bold uppercase leading-normal tracking-wide text-emerald-700'
  const sectionTitleClass = 'mt-2 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl [font-family:\'Plus_Jakarta_Sans\',sans-serif]'
  const sectionCopyClass = 'mt-3 max-w-3xl text-base leading-relaxed text-slate-700'
  const primaryButtonClass = `inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-emerald-700 px-4 py-2.5 text-base font-semibold leading-normal text-white transition-colors hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60 cursor-pointer ${focusRingClass}`
  const secondaryButtonClass = `inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-base font-semibold leading-normal text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 cursor-pointer ${focusRingClass}`
  const textLinkClass = `inline-flex min-h-11 items-center gap-1 rounded text-base font-semibold leading-normal text-emerald-700 hover:text-emerald-800 ${focusRingClass}`
  const chipClass = (active: boolean) => `inline-flex min-h-11 items-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold leading-normal transition-colors cursor-pointer ${focusRingClass} ${active ? 'border-emerald-700 bg-emerald-700 text-white' : 'border-slate-300 bg-white text-slate-700 hover:border-slate-400 hover:bg-slate-50 hover:text-slate-900'}`
  const resultPillClass = (result: string | null) => {
    if (result === 'won') return 'inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-sm font-semibold leading-normal text-emerald-700'
    if (result === 'lost') return 'inline-flex items-center rounded-full border border-red-200 bg-red-50 px-2.5 py-1 text-sm font-semibold leading-normal text-red-700'
    if (result === 'void') return 'inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-sm font-semibold leading-normal text-amber-700'
    return 'inline-flex items-center rounded-full border border-slate-300 bg-slate-50 px-2.5 py-1 text-sm font-semibold leading-normal text-slate-700'
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <a className={`inline-flex min-h-11 flex-col justify-center rounded text-slate-900 ${focusRingClass}`} href="/">
            <span className="text-xl font-bold tracking-tight [font-family:'Plus_Jakarta_Sans',sans-serif]">MatchSlip</span>
            <span className="text-sm font-medium leading-normal text-slate-600">Built on evidence, not hunches.</span>
            <span className="sr-only"> home</span>
          </a>
          <nav className="flex flex-wrap items-center gap-1 sm:gap-2" aria-label="Account">
            <button type="button" className={`inline-flex min-h-11 items-center rounded px-3 text-sm font-medium leading-normal text-slate-700 transition-colors hover:text-slate-900 cursor-pointer ${focusRingClass}`} onClick={onViewPro}>Pro plan</button>
            <button type="button" className={`inline-flex min-h-11 items-center rounded px-3 text-sm font-medium leading-normal text-slate-700 transition-colors hover:text-slate-900 cursor-pointer ${focusRingClass}`} onClick={onSignIn}>Sign in</button>
            <button type="button" className={secondaryButtonClass} onClick={onCreateAccount}>Create free account <span aria-hidden="true">→</span></button>
          </nav>
        </div>
      </header>

      <section className="border-b border-slate-200 bg-white" aria-labelledby="public-hero-title">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-12 sm:px-6 lg:grid-cols-[minmax(0,1fr)_360px] lg:items-center lg:py-16">
          <div>
            <span className={sectionKickerClass}>EVIDENCE-LED FOOTBALL RESEARCH</span>
            <h1 id="public-hero-title" className="mt-3 max-w-3xl text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl [font-family:'Plus_Jakarta_Sans',sans-serif]">Football picks, <em className="not-italic text-emerald-700">with a record.</em></h1>
            <p className="mt-4 max-w-2xl text-base leading-relaxed text-slate-700">Free accounts follow dated published tickets: the matches, kickoff and final settlement. Pro adds each selection, the captured odds and the model chance behind it.</p>
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <button type="button" className={primaryButtonClass} onClick={onCreateAccount}>Follow the daily slate</button>
              <a className={secondaryButtonClass} href="#public-matches">Browse fixtures</a>
            </div>
            <div className="mt-6 flex flex-wrap gap-x-5 gap-y-2 text-base leading-normal text-slate-700">
              <span className="inline-flex items-center gap-2"><span className="h-1.5 w-1.5 rounded-full bg-emerald-600" aria-hidden="true" />Dated published tickets</span>
              <span className="inline-flex items-center gap-2"><span className="h-1.5 w-1.5 rounded-full bg-emerald-600" aria-hidden="true" />Final scores and settlements</span>
              <span className="inline-flex items-center gap-2"><span className="h-1.5 w-1.5 rounded-full bg-emerald-600" aria-hidden="true" />Pro adds selections, odds and model chance</span>
            </div>
          </div>
          <aside className="rounded-xl border border-slate-200 bg-slate-50 p-5 shadow-sm" aria-labelledby="public-ticket-steps-title">
            <h2 id="public-ticket-steps-title" className="text-base font-semibold leading-normal text-slate-900">From pick to result</h2>
            <ol className="mt-4 space-y-3">
              {[
                ['01', 'Published ticket', 'Match legs and publication time'],
                ['02', 'Price and evidence', 'Captured odds and model chance in Pro'],
                ['03', 'Settled result', 'Final score and pick outcome'],
              ].map(([step, title, copy]) => (
                <li key={step} className="flex gap-3 rounded-lg border border-slate-200 bg-white px-3 py-3">
                  <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-sm font-bold text-emerald-700">{step}</span>
                  <div><strong className="block text-sm font-semibold leading-normal text-slate-900">{title}</strong><span className="block text-sm leading-normal text-slate-600">{copy}</span></div>
                </li>
              ))}
            </ol>
          </aside>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-12 sm:px-6" id="public-record" aria-labelledby="public-record-title">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <span className={sectionKickerClass}>PUBLIC SETTLED RECORD</span>
            <h2 id="public-record-title" className={sectionTitleClass}>The record, before you sign up.</h2>
            <p className={sectionCopyClass}>Choose a tier and a window to see how its published paper tickets settled — the latest tickets and the cumulative result behind them.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Record date range">
            {PROOF_RANGES.map((range) => (
              <button key={range.label} type="button" className={chipClass(proofDays === range.value)} onClick={() => selectProofRange(range.value)} aria-pressed={proofDays === range.value}>{range.label}</button>
            ))}
            {proofRefreshing && proofStatus === 'ready' && <span className="text-base font-medium leading-normal text-slate-700" role="status">Updating…</span>}
          </div>
        </div>
        {proofStatus === 'loading' && <div className="mt-6 rounded-xl border border-slate-200 bg-white px-4 py-8 text-center text-base leading-relaxed text-slate-700" role="status">Loading the published record…</div>}
        {proofStatus === 'unavailable' && (
          <div className="mt-6 rounded-xl border border-red-200 bg-red-50 px-4 py-6 text-base leading-relaxed text-red-700" role="status">
            <strong className="block font-semibold">The public record is temporarily unavailable.</strong>
            <span className="mt-1 block">Fixtures and scores remain available below.</span>
            <button type="button" className={`mt-3 inline-flex min-h-11 items-center rounded text-base font-semibold text-red-700 underline underline-offset-2 cursor-pointer ${focusRingClass}`} onClick={() => setProofAttempt(attempt => attempt + 1)}>Try again</button>
          </div>
        )}
        {proofStatus === 'ready' && proof && <>
          <div className={`mt-6 grid gap-6 ${activeTicket ? 'lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]' : ''}`}>
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
              <div className="grid gap-4 border-b border-slate-200 pb-4 sm:grid-cols-2">
                <div><strong className="block font-mono text-2xl font-bold tabular-nums text-slate-900">{proof.sample_size}</strong><span className="text-sm leading-normal text-slate-600">settled public tickets</span></div>
                <div><strong className="block text-sm font-semibold leading-normal text-slate-900">{formatProofDate(proof.first_settled_date)} – {formatProofDate(proof.last_settled_date)}</strong><span className="block text-sm leading-normal text-slate-600">{proof.days ? `last ${proof.days} days` : 'full published history'}</span></div>
              </div>
              {activeTier ? <>
                <div className="mt-4 space-y-2" role="group" aria-label="Choose a ticket tier">
                  {proof.tiers.map((tier) => {
                    const selected = tier.ticket_type === activeTier.ticket_type
                    return (
                      <button key={tier.ticket_type} type="button" className={`min-h-14 w-full rounded-lg border px-4 py-3 text-left transition-colors cursor-pointer ${focusRingClass} ${selected ? 'border-emerald-600 bg-emerald-50' : 'border-slate-300 bg-white hover:bg-slate-50'}`} onClick={() => selectProofTier(tier.ticket_type)} aria-pressed={selected} aria-label={`${tier.name}, ${tier.settled} settled, ${tier.won} won, ${tier.lost} lost${tier.void > 0 ? `, ${tier.void} void` : ''}, ${proofPercent(tier.win_rate)} hit rate`}>
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div><strong className="block text-sm font-semibold leading-normal text-slate-900">{tier.name}</strong><span className="text-sm leading-normal text-slate-600">{tier.settled} settled</span></div>
                          <div className="flex items-center gap-2 text-sm font-semibold leading-normal"><span className="text-emerald-700">{tier.won}W</span><span className="text-red-600">{tier.lost}L</span>{tier.void > 0 && <span className="text-amber-700">{tier.void}V</span>}</div>
                          <span className="text-right"><span className="block font-mono text-lg font-bold tabular-nums text-slate-900">{proofPercent(tier.win_rate)}</span><span className="text-sm leading-normal text-slate-600">hit rate</span></span>
                        </div>
                      </button>
                    )
                  })}
                </div>
                <div className="mt-4 grid gap-3 sm:grid-cols-3" aria-live="polite">
                  <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3"><span className="block text-sm font-semibold uppercase leading-normal tracking-wide text-slate-600">Hit rate</span><strong className="mt-1 block font-mono text-xl font-bold tabular-nums text-slate-900">{proofPercent(activeTier.win_rate)}</strong><span className="block text-sm leading-normal text-slate-600">{activeTier.won}W · {activeTier.lost}L{activeTier.void > 0 ? ` · ${activeTier.void}V` : ''}</span></div>
                  <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3"><span className="block text-sm font-semibold uppercase leading-normal tracking-wide text-slate-600">Paper P&amp;L</span><strong className={`mt-1 block font-mono text-xl font-bold tabular-nums ${profitTone(activeTier.profit_units)}`}>{formatUnits(activeTier.profit_units)}</strong><span className="block text-sm leading-normal text-slate-600">{activeTier.staked_units.toLocaleString('en-GB', { maximumFractionDigits: 0 })} decided stakes</span></div>
                  <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3"><span className="block text-sm font-semibold uppercase leading-normal tracking-wide text-slate-600">ROI</span><strong className={`mt-1 block font-mono text-xl font-bold tabular-nums ${profitTone(activeTier.roi)}`}>{formatRoi(activeTier.roi)}</strong><span className="block text-sm leading-normal text-slate-600">P&amp;L ÷ staked</span></div>
                </div>
                <div className="mt-5">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-3"><strong className="text-base font-semibold leading-normal text-slate-900">Equity, cumulative units</strong><span className="text-sm leading-normal text-slate-600">{activeTier.name}</span></div>
                  <EquitySparkline points={activeTier.equity} label={activeTier.name} />
                </div>
              </> : <p className="mt-4 text-base leading-relaxed text-slate-700">No settled tickets in this window yet. Try a wider range.</p>}
            </div>
            {activeTicket && (
              <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6" aria-labelledby="public-proof-ticket-title">
                <header className="flex flex-col gap-3 border-b border-slate-200 pb-4 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <span className="text-sm font-bold uppercase leading-normal tracking-wide text-emerald-700">{activeTicketCursor === 0 ? 'Most recent' : 'Earlier'} {activeTicket.name} ticket</span>
                    <h3 id="public-proof-ticket-title" className="mt-1 text-lg font-bold tracking-tight text-slate-900 [font-family:'Plus_Jakarta_Sans',sans-serif]">{activeTicket.name} · {formatProofDate(activeTicket.target_date)}</h3>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {activeTicket.profit_units != null && <span className={`inline-flex items-center rounded-full border border-slate-300 bg-slate-50 px-2.5 py-1 text-sm font-semibold leading-normal ${profitTone(activeTicket.profit_units)}`}>{formatUnits(activeTicket.profit_units)}</span>}
                    <span className={resultPillClass(activeTicket.result)}>{proofResult(activeTicket.result)}</span>
                  </div>
                </header>
                {activeTickets.length > 1 && (
                  <div className="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm leading-normal text-slate-700">
                    <button type="button" className={`inline-flex min-h-11 items-center rounded px-2 font-semibold hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-60 cursor-pointer ${focusRingClass}`} onClick={() => setTicketCursor(Math.max(0, activeTicketCursor - 1))} disabled={activeTicketCursor === 0} aria-label={`Newer ${activeTicket.name} ticket`}>‹ Newer</button>
                    <span>{activeTicketCursor + 1} of {activeTickets.length} recent</span>
                    <button type="button" className={`inline-flex min-h-11 items-center rounded px-2 font-semibold hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-60 cursor-pointer ${focusRingClass}`} onClick={() => setTicketCursor(Math.min(activeTickets.length - 1, activeTicketCursor + 1))} disabled={activeTicketCursor >= activeTickets.length - 1} aria-label={`Older ${activeTicket.name} ticket`}>Older ›</button>
                  </div>
                )}
                <div className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-sm leading-normal text-slate-600">
                  <span>Published {formatProofDateTime(activeTicket.published_at)}</span>
                  <span>{activeTicket.publication_timing === 'pre_kickoff' ? 'Before kickoff' : activeTicket.publication_timing === 'post_kickoff' ? 'After kickoff' : 'Timing unknown'}</span>
                  <span className="font-mono tabular-nums">{activeTicket.combined_odds.toFixed(2)}× combined</span>
                </div>
                <ul className="mt-4 divide-y divide-slate-200 rounded-lg border border-slate-200">
                  {activeTicket.legs.map((leg) => (
                    <li key={leg.position} className="flex flex-col gap-2 px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <strong className="block text-sm font-semibold leading-normal text-slate-900">{leg.home_team} vs {leg.away_team}</strong>
                        <span className="block text-sm leading-normal text-slate-600">{leg.competition} · {legMarketLabel(leg.market, leg.selection)}</span>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-sm leading-normal text-slate-700">
                        <span className={resultPillClass(leg.result)}>{proofResult(leg.result)}</span>
                        {leg.home_goals != null && leg.away_goals != null && <b className="font-mono text-base tabular-nums text-slate-900">{leg.home_goals}–{leg.away_goals}</b>}
                      </div>
                    </li>
                  ))}
                </ul>
              </article>
            )}
          </div>
          <div className="mt-6 rounded-xl border border-slate-200 bg-slate-50 px-5 py-4">
            <h3 className="text-base font-semibold leading-normal text-slate-900">How to read this record</h3>
            <p className="mt-2 text-base leading-relaxed text-slate-700">Hit rate counts decided tickets only; void stakes are returned and add 0 units. Paper P&amp;L uses a flat 1-unit stake at the published combined odds, and ROI divides it by decided stakes — not a bankroll or staking plan. These results describe this sample and do not predict the next match.</p>
            <p className="mt-2 text-base leading-relaxed text-slate-700">Free accounts see match legs, kickoff and settlement. Pro adds selections, captured odds, model chance and every Q ≥75 system pick. Q is a 0–100 evidence score; 75 or more marks a qualified pick.</p>
          </div>
          <div className="mt-6 flex flex-col gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
            <span className="text-base font-medium leading-normal text-emerald-900">Follow the next slate as it is published.</span>
            <button type="button" className={primaryButtonClass} onClick={onCreateAccount}>Create a free account <span aria-hidden="true">→</span></button>
          </div>
        </>}
      </section>

      <nav className="border-y border-slate-200 bg-white" aria-label="Page sections">
        <div className="mx-auto flex max-w-6xl gap-2 overflow-x-auto px-4 py-2 sm:px-6">
          {([['public-record', 'Record'], ['public-matches', 'Matches'], ['public-product', 'How MatchSlip works'], ['public-access', 'Plans'], ['public-faq', 'FAQs']] as const).map(([id, label]) => (
            <a key={id} className={`inline-flex min-h-11 shrink-0 items-center rounded-full px-4 text-sm font-semibold leading-normal transition-colors ${focusRingClass} ${activeSection === id ? 'bg-emerald-50 text-emerald-700' : 'text-slate-700 hover:bg-slate-50 hover:text-slate-900'}`} href={`#${id}`} aria-current={activeSection === id ? 'location' : undefined}>{label}</a>
          ))}
        </div>
      </nav>

      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6" id="public-matches">
        <section aria-labelledby="public-matches-title">
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
            <div>
              <span className={sectionKickerClass}>MATCH CENTRE</span>
              <h2 id="public-matches-title" className={sectionTitleClass}>Fixtures &amp; scores</h2>
              <p className={sectionCopyClass}>Browse public fixtures and follow the matchday as it unfolds.</p>
              <div className="mt-5 flex flex-wrap gap-2" role="group" aria-label="Choose fixture date">
                {[-2, -1, 0, 1, 2].map((offset) => {
                  const tabDate = offset === 0 ? date : shiftDate(date, offset)
                  const value = new Date(`${tabDate}T12:00:00`)
                  const selected = offset === 0
                  const fullDate = value.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
                  const shortDay = value.toLocaleDateString('en-GB', { weekday: 'short' }).toUpperCase()
                  return (
                    <button key={offset} type="button" className={`inline-flex min-h-14 flex-col items-center justify-center rounded-lg border px-3 py-2 text-left transition-colors cursor-pointer ${focusRingClass} ${selected ? 'border-emerald-600 bg-emerald-50 text-emerald-800' : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50 hover:text-slate-900'}`} onClick={() => selectDate(tabDate)} aria-current={selected ? 'date' : undefined}>
                      <span className="block text-sm font-semibold leading-normal uppercase tracking-wide">{shortDay}</span>
                      <strong className="block font-mono text-base font-bold tabular-nums">{value.getDate()}</strong>
                      {tabDate === today && <span className="block text-sm font-semibold leading-normal text-emerald-700">Today</span>}
                      <span className="sr-only"> — {fullDate}</span>
                    </button>
                  )
                })}
              </div>
              <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Filter matches by status">
                {([['all', 'All matches', statusCounts.all], ['live', 'Live', statusCounts.live], ['scheduled', 'Upcoming', statusCounts.scheduled], ['finished', 'Finished', statusCounts.finished]] as const).map(([status, label, count]) => (
                  <button key={status} type="button" className={chipClass(activeStatus === status)} onClick={() => selectStatus(status)} aria-pressed={activeStatus === status}>
                    {status === 'live' && <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />}
                    {label}<span className={`font-mono tabular-nums ${activeStatus === status ? 'text-white' : 'text-slate-600'}`}>{loading ? '—' : count}</span>
                  </button>
                ))}
              </div>
            </div>
            <aside className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm" aria-label="Filter fixtures by league">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3"><strong className="text-base font-semibold leading-normal text-slate-900">{date === today ? 'Leagues today' : 'Leagues on this date'}</strong><span className="text-sm leading-normal text-slate-600">{loading ? '—' : matchCountLabel(leagueScopeTotal)}</span></div>
              <div className="mt-2 max-h-72 space-y-1 overflow-y-auto">
                <button type="button" className={`flex min-h-11 w-full items-center justify-between gap-3 rounded-lg px-3 text-left text-sm leading-normal transition-colors cursor-pointer ${focusRingClass} ${selectedLeague === '' ? 'bg-emerald-50 text-emerald-800' : 'text-slate-700 hover:bg-slate-50 hover:text-slate-900'}`} onClick={() => setSelectedLeague('')} aria-pressed={selectedLeague === ''}><span>All leagues</span><b className={`font-mono text-sm tabular-nums ${selectedLeague === '' ? 'text-emerald-800' : 'text-slate-600'}`}>{loading ? '—' : leagueScopeTotal}</b></button>
                {leagueMatchCounts.map(([league, count]) => <button key={league} type="button" className={`flex min-h-11 w-full items-center justify-between gap-3 rounded-lg px-3 text-left text-sm leading-normal transition-colors cursor-pointer ${focusRingClass} ${selectedLeague === league ? 'bg-emerald-50 text-emerald-800' : 'text-slate-700 hover:bg-slate-50 hover:text-slate-900'}`} onClick={() => setSelectedLeague(current => current === league ? '' : league)} aria-pressed={selectedLeague === league}><span className="truncate" title={league}>{league}</span><b className={`font-mono text-sm tabular-nums ${selectedLeague === league ? 'text-emerald-800' : 'text-slate-600'}`}>{loading ? '—' : count}</b></button>)}
                {!loading && leagueMatchCounts.length === 0 && <span className="block px-3 py-2 text-base leading-relaxed text-slate-700">No league fixtures for this date</span>}
              </div>
            </aside>
          </div>

          <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <label className={`flex min-h-11 w-full max-w-md items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-700 focus-within:border-emerald-700 focus-within:ring-2 focus-within:ring-emerald-700/20 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-emerald-700`}>
              <span aria-hidden="true">⌕</span>
              <input className="w-full bg-transparent text-base leading-normal text-slate-900 outline-none placeholder:text-slate-600" type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search team or league" aria-label="Search teams and leagues" />
            </label>
            <span className="text-sm leading-normal text-slate-600">{loading ? 'Updating…' : `${matchCountLabel(visibleMatches.length)}${refreshedAt ? ` · updated ${refreshedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : ''}`}</span>
          </div>

          <div className="mt-4 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            {error ? <div className="px-4 py-10 text-center" role="status"><strong className="block text-base font-semibold text-slate-900">Fixture data is temporarily unavailable</strong><span className="mt-1 block text-base leading-relaxed text-slate-700">Please try again shortly.</span></div>
              : loading ? <div className="px-4 py-10 text-center text-base leading-relaxed text-slate-700" role="status">Loading fixtures…</div>
                : visibleMatches.length === 0 ? <div className="px-4 py-10 text-center" role="status"><strong className="block text-base font-semibold text-slate-900">No matches match these filters</strong><span className="mt-1 block text-base leading-relaxed text-slate-700">Try another date, league or search.</span></div>
                  : <>
                    <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-slate-50 px-3 py-2 sm:hidden">
                      <label htmlFor="public-fixture-sort" className="text-sm font-semibold leading-normal text-slate-700">Sort by</label>
                      <select id="public-fixture-sort" className={`min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-base text-slate-900 ${focusRingClass}`} value={sortKey} onChange={(event) => { setSortKey(event.target.value as FixtureSortKey); setSortDirection('asc') }}>
                        <option value="kickoff">Kickoff time</option>
                        <option value="league">League</option>
                        <option value="match">Match</option>
                        <option value="statusScore">Status / score</option>
                      </select>
                      <button type="button" className={secondaryButtonClass} onClick={() => setSortDirection(current => current === 'asc' ? 'desc' : 'asc')} aria-label={`Switch to ${sortDirection === 'asc' ? 'descending' : 'ascending'} order`}>{sortDirection === 'asc' ? 'Ascending ↑' : 'Descending ↓'}</button>
                    </div>
                    <div className="hidden overflow-x-auto sm:block"><table className="w-full min-w-[640px] border-collapse text-left text-sm">
                      <thead className="border-b border-slate-200 bg-slate-50"><tr>{sortHeader('kickoff', 'Kickoff Time')}{sortHeader('league', 'League')}{sortHeader('match', 'Match')}{sortHeader('statusScore', 'Status/Score')}</tr></thead>
                      <tbody className="divide-y divide-slate-200">{displayedMatches.map((match) => {
                        const status = match.status.toLowerCase()
                        const hasScore = match.home_goals != null && match.away_goals != null
                        return <tr className="hover:bg-slate-50" key={match.match_id}>
                          <td className="px-3 py-3 font-mono text-sm tabular-nums text-slate-600"><time dateTime={match.kickoff_at}>{kickoffLabel(match.kickoff_at)}</time></td>
                          <td className="px-3 py-3 text-sm leading-normal text-slate-600" title={match.competition}>{match.competition}</td>
                          <td className="px-3 py-3"><div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-sm text-slate-900" title={`${match.home_team} vs ${match.away_team}`}><span className="font-medium">{match.home_team}</span><span className="text-sm font-normal text-slate-600">vs</span><span className="font-medium">{match.away_team}</span></div></td>
                          <td className="px-3 py-3"><div className="flex flex-wrap items-center gap-3 text-sm leading-normal"><span className={`font-semibold ${status === 'live' ? 'text-emerald-700' : 'text-slate-600'}`}>{matchStatus(match)}</span>{hasScore && <strong className="font-mono tabular-nums text-slate-900">{match.home_goals} : {match.away_goals}</strong>}</div></td>
                        </tr>
                      })}</tbody>
                    </table></div>
                    <ul className="divide-y divide-slate-200 sm:hidden">
                      {displayedMatches.map((match) => {
                        const status = match.status.toLowerCase()
                        const hasScore = match.home_goals != null && match.away_goals != null
                        return <li key={match.match_id} className="px-4 py-4">
                          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                            <strong className="text-base font-semibold leading-normal text-slate-900">{match.home_team} vs {match.away_team}</strong>
                            <span className="font-mono text-sm tabular-nums text-slate-600"><time dateTime={match.kickoff_at}>{kickoffLabel(match.kickoff_at)}</time></span>
                          </div>
                          <p className="mt-1 text-sm leading-normal text-slate-600">{match.competition}</p>
                          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm leading-normal">
                            <span className={`font-semibold ${status === 'live' ? 'text-emerald-700' : 'text-slate-600'}`}>{matchStatus(match)}</span>
                            {hasScore && <strong className="font-mono text-base tabular-nums text-slate-900">{match.home_goals} : {match.away_goals}</strong>}
                          </div>
                        </li>
                      })}
                    </ul>
                  </>}
            <div className="border-t border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-normal text-slate-600">Scores and match states are shown when available. Live fixtures refresh automatically.</div>
          </div>
          {!loading && !error && visibleMatches.length > 5 && (
            <button type="button" className={`mt-4 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-base font-semibold text-slate-700 transition-colors hover:bg-slate-50 cursor-pointer ${focusRingClass}`} onClick={() => setShowAllMatches(current => !current)} aria-expanded={showAllMatches}>
              {showAllMatches ? 'Show fewer fixtures' : `Show all ${visibleMatches.length} fixtures`}
              <span aria-hidden="true">{showAllMatches ? '−' : '+'}</span>
            </button>
          )}
        </section>
      </div>

      <section className="border-t border-slate-200 bg-white" id="public-product" aria-labelledby="public-product-title">
        <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
          <div>
            <span className={sectionKickerClass}>THE MATCHSLIP APPROACH</span>
            <h2 id="public-product-title" className={sectionTitleClass}>From fixture list to final result.</h2>
            <p className={sectionCopyClass}>Useful football research should show its work—and leave room for uncertainty.</p>
          </div>
          <div className="mt-8 grid gap-4 md:grid-cols-3">
            {[
              { num: '01', title: 'Start with the match', copy: 'Browse fixtures by date, competition, kickoff, live status and score. Sort the slate to find the games you want to follow.', action: <a href="#public-matches" className={textLinkClass}>Browse fixtures <span aria-hidden="true">→</span></a> },
              { num: '02', title: 'Read the recommendation in context', copy: 'A free account shows the published ticket, its match legs and how it settled. Pro opens each selection, the captured odds, model chance and Q score.', action: null },
              { num: '03', title: 'Review the result honestly', copy: 'When a match is complete, its score and settled selection outcome can be reviewed against the original published record.', action: null },
            ].map(({ num, title, copy, action }) => (
              <article key={num} className="rounded-xl border border-slate-200 bg-slate-50 p-5">
                <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-emerald-50 text-sm font-bold text-emerald-700">{num}</span>
                <h3 className="mt-4 text-lg font-bold tracking-tight text-slate-900 [font-family:'Plus_Jakarta_Sans',sans-serif]">{title}</h3>
                <p className="mt-2 text-base leading-relaxed text-slate-700">{copy}</p>
                {action && <div className="mt-4">{action}</div>}
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-12 sm:px-6" id="public-access" aria-labelledby="public-access-title">
        <div>
          <span className={sectionKickerClass}>START FREE, GO DEEPER WHEN YOU NEED TO</span>
          <h2 id="public-access-title" className={sectionTitleClass}>Choose how you want to explore.</h2>
          <p className={sectionCopyClass}>You can look around before creating an account. Your workspace adds more ways to follow the game.</p>
        </div>
        <div className="mt-8 grid gap-4 lg:grid-cols-3">
          <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div><span className="text-sm font-bold uppercase leading-normal tracking-wide text-slate-600">Public</span><h3 className="mt-2 text-lg font-bold text-slate-900 [font-family:'Plus_Jakarta_Sans',sans-serif]">Take a look around</h3></div>
            <ul className="mt-4 space-y-2 text-base leading-normal text-slate-700">
              <li>Fixtures by date and competition</li>
              <li>Live status and completed scores</li>
              <li>No account required</li>
            </ul>
            <a href="#public-matches" className={`${textLinkClass} mt-5`}>Open the match centre <span aria-hidden="true">→</span></a>
          </article>
          <article className="rounded-xl border border-emerald-200 bg-emerald-50 p-5 shadow-sm">
            <div><span className="text-sm font-bold uppercase leading-normal tracking-wide text-emerald-700">Free account</span><h3 className="mt-2 text-lg font-bold text-slate-900 [font-family:'Plus_Jakarta_Sans',sans-serif]">Follow the daily slate</h3></div>
            <ul className="mt-4 space-y-2 text-base leading-normal text-slate-700">
              <li>Published Conservative tickets</li>
              <li>Match legs, kickoff and settlement</li>
              <li>One workspace for each matchday</li>
            </ul>
            <button type="button" onClick={onCreateAccount} className={`${textLinkClass} mt-5 cursor-pointer`}>Create a free account <span aria-hidden="true">→</span></button>
          </article>
          <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div>
              <span className="text-sm font-bold uppercase leading-normal tracking-wide text-slate-600">Pro</span>
              <h3 className="mt-2 text-lg font-bold text-slate-900 [font-family:'Plus_Jakarta_Sans',sans-serif]">Open the evidence</h3>
              <div className="mt-2 flex flex-wrap items-baseline gap-2"><span className="font-mono text-2xl font-bold tabular-nums text-slate-900">{formatProPrice(offer?.price)}</span><span className="text-base font-medium text-slate-700">/ month</span></div>
            </div>
            <ul className="mt-4 space-y-2 text-base leading-normal text-slate-700">
              <li>Every Q ≥75 system pick, grouped by match</li>
              <li>Selections, captured odds and model chance</li>
              <li>Expanded published ticket history</li>
              <li>Stats &amp; trends with league context</li>
            </ul>
            <button type="button" onClick={onViewPro} className={`${textLinkClass} mt-5 cursor-pointer`}>View the Pro plan <span aria-hidden="true">→</span></button>
          </article>
        </div>
        <p className="mt-4 text-base leading-relaxed text-slate-700">Create a free account before checkout. Pro is a recurring monthly card payment; you can manage or cancel it through Flutterwave’s subscription emails.</p>
      </section>

      <section className="border-t border-slate-200 bg-white" id="public-faq" aria-labelledby="public-faq-title">
        <div className="mx-auto max-w-4xl px-4 py-12 sm:px-6">
          <div><span className={sectionKickerClass}>GOOD TO KNOW</span><h2 id="public-faq-title" className={sectionTitleClass}>A few quick answers.</h2></div>
          <div className="mt-6 divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white">
            {[
              ['What can I see without an account?', 'Public fixtures include the competition, teams, kickoff or live status, and scores when available. Personal account information and workspace tools stay behind sign-in.'],
              ['What does MatchSlip do with recommendations?', 'Each ticket is dated and published before kickoff when possible, then settled against the final score. Free accounts see the match legs and settlement; Pro adds the selection, captured odds and model chance for every leg.'],
              ['What does Q ≥75 mean?', 'Q is a 0–100 evidence score for a selection. It combines the model’s probability, the value at the captured price, recent form, expected goals, market agreement and data quality. A pick needs 75 or more to qualify as a system pick. It is a screening score, not a guarantee.'],
              ['Where do fixtures, scores and prices come from?', 'Fixtures, live scores and results come from a third-party football data provider. Captured prices are recorded when a ticket is published, so they can differ from your bookmaker or move before kickoff. If a feed is delayed or unavailable, MatchSlip shows the last record it holds rather than inventing a result.'],
              ['Does MatchSlip guarantee wins or profit?', 'No. Football outcomes are uncertain. The published record above is a record of completed matches, not a forecast of future performance.'],
            ].map(([q, a]) => (
              <details key={q} className="group px-4 py-3">
                <summary className={`inline-flex min-h-11 cursor-pointer list-none items-center rounded py-1 text-base font-semibold leading-normal text-slate-900 ${focusRingClass}`}>{q}</summary>
                <p className="pb-2 pt-1 text-base leading-relaxed text-slate-700">{a}</p>
              </details>
            ))}
          </div>
          <div className="mt-6 flex flex-col gap-3 rounded-xl border border-slate-200 bg-slate-50 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div><strong className="block text-base font-semibold leading-normal text-slate-900">Ready to follow the next matchday?</strong><span className="block text-base leading-normal text-slate-700">Create a free account to open your MatchSlip workspace.</span></div>
            <button type="button" className={primaryButtonClass} onClick={onCreateAccount}>Get started for free <span aria-hidden="true">→</span></button>
          </div>
        </div>
      </section>

      <footer className="border-t border-slate-200 bg-slate-50">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 text-sm leading-normal text-slate-600 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <span>MatchSlip · Built on evidence, not hunches.</span>
          <span>Information only.</span>
        </div>
      </footer>
    </main>
  )
}
