import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { fetchPublicMatchFixtures, fetchPublicProof, formatMarket, formatSelection, selectionRepeatsMarket } from '../lib/api'
import type { MatchFixture, PublicProof, PublicProofEquityPoint } from '../lib/api'
import { TODAY } from './dailyTickets/helpers'
import './PublicHome.css'

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
  if (value == null || Math.abs(value) < 0.005) return 'is-flat'
  return value > 0 ? 'is-positive' : 'is-negative'
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
    return <p className="public-proof-spark-empty">The equity line appears once this range has two settled matchdays.</p>
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
    <figure className="public-proof-spark">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${label} cumulative paper result across ${points.length} settled matchdays`}>
        <line className="public-proof-spark-zero" x1={padX} x2={width - padX} y1={yFor(0)} y2={yFor(0)} />
        <path className="public-proof-spark-line" d={line} fill="none" />
        <circle className="public-proof-spark-dot" cx={width - padX} cy={yFor(last.cumulative_units)} r="3.2" />
      </svg>
      <figcaption><span>{formatProofDate(points[0].date)}</span><span>{formatProofDate(last.date)}</span></figcaption>
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

  const sortHeader = (key: FixtureSortKey, label: string) => {
    const active = sortKey === key
    const ariaSort = active ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'
    return <th scope="col" aria-sort={ariaSort}><button className="public-fixture-sort-button" onClick={() => {
      if (active) setSortDirection(current => current === 'asc' ? 'desc' : 'asc')
      else { setSortKey(key); setSortDirection('asc') }
    }}>{label}<span aria-hidden="true">{active ? (sortDirection === 'asc' ? '↑' : '↓') : '↕'}</span></button></th>
  }

  return (
    <main className="public-home">
      <header className="public-topbar">
        <a className="public-brand" href="/" aria-label="QwanEj home">
          <picture className="public-brand-icon">
            <source media="(prefers-color-scheme: dark)" srcSet="/dark/icon-128.png?v=qwanej-1" />
            <img src="/light/icon-128.png?v=qwanej-1" alt="" />
          </picture>
          <span><strong>QwanEj</strong><small>FOOTBALL INTELLIGENCE</small></span>
        </a>
        <nav className="public-top-actions" aria-label="Account">
          <button className="public-link-button public-pro-link" onClick={onViewPro}>Pro plan</button>
          <button className="public-link-button" onClick={onSignIn}>Sign in</button>
          <button className="public-cta" onClick={onCreateAccount}>Create free account <span aria-hidden="true">→</span></button>
        </nav>
      </header>

      <section className="public-hero" aria-labelledby="public-hero-title">
        <div className="public-hero-copy">
          <span className="public-eyebrow">EVIDENCE-LED FOOTBALL RESEARCH</span>
          <h1 id="public-hero-title">Football picks, <em>with a record.</em></h1>
          <p>Free accounts follow dated published tickets: the matches, kickoff and final settlement. Pro adds each selection, the captured odds and the model chance behind it.</p>
          <div className="public-hero-actions">
            <button className="public-cta public-cta-large" onClick={onCreateAccount}>Follow the daily slate</button>
            <a className="public-quiet-button" href="#public-matches">Browse fixtures</a>
          </div>
          <div className="public-hero-promises">
            <span>Dated published tickets</span>
            <span>Final scores and settlements</span>
            <span>Pro adds selections, odds and model chance</span>
          </div>
        </div>
        <aside className="public-hero-card" aria-label="How a published ticket moves from pick to result">
          <div className="public-hero-card-head"><span>FOLLOW THE RECORD</span><span>From pick to result</span></div>
          <ol className="public-evidence-flow">
            <li><span>01</span><div><strong>Published ticket</strong><small>Match legs and publication time</small></div></li>
            <li><span>02</span><div><strong>Price and evidence</strong><small>Captured odds and model chance in Pro</small></div></li>
            <li><span>03</span><div><strong>Settled result</strong><small>Final score and pick outcome</small></div></li>
          </ol>
          <div className="public-hero-card-foot">Past outcomes describe their sample; they do not predict the next match.</div>
        </aside>
      </section>

      <section className="public-proof" id="public-record" aria-labelledby="public-record-title">
        <div className="public-proof-heading">
          <div>
            <span className="public-section-kicker">PUBLIC SETTLED RECORD</span>
            <h2 id="public-record-title">The record, before you sign up.</h2>
            <p>Choose a tier and a window to see how its published paper tickets settled — the latest tickets and the cumulative result behind them.</p>
          </div>
          <div className="public-proof-range" role="group" aria-label="Record date range">
            {PROOF_RANGES.map((range) => (
              <button key={range.label} type="button" className={proofDays === range.value ? 'is-active' : ''} onClick={() => selectProofRange(range.value)} aria-pressed={proofDays === range.value}>{range.label}</button>
            ))}
            {proofRefreshing && proofStatus === 'ready' && <span className="public-proof-updating" role="status">Updating…</span>}
          </div>
        </div>
        {proofStatus === 'loading' && <div className="public-proof-state" role="status">Loading the published record…</div>}
        {proofStatus === 'unavailable' && (
          <div className="public-proof-state" role="status">
            <strong>The public record is temporarily unavailable.</strong>
            <span>Fixtures and scores remain available below.</span>
            <button type="button" className="public-link-button" onClick={() => setProofAttempt(attempt => attempt + 1)}>Try again</button>
          </div>
        )}
        {proofStatus === 'ready' && proof && <>
          <div className={`public-proof-grid${activeTicket ? '' : ' is-solo'}`}>
            <div className="public-proof-summary">
              <div className="public-proof-stats">
                <div><strong>{proof.sample_size}</strong><span>settled public tickets</span></div>
                <div><strong>{formatProofDate(proof.first_settled_date)} – {formatProofDate(proof.last_settled_date)}</strong><span>{proof.days ? `last ${proof.days} days` : 'full published history'}</span></div>
              </div>
              {activeTier ? <>
                <div className="public-proof-tiers" role="group" aria-label="Choose a ticket tier">
                  {proof.tiers.map((tier) => {
                    const selected = tier.ticket_type === activeTier.ticket_type
                    return (
                      <button key={tier.ticket_type} type="button" className={`public-proof-tier${selected ? ' is-active' : ''}`} onClick={() => selectProofTier(tier.ticket_type)} aria-pressed={selected}>
                        <div className="public-proof-tier-name"><strong>{tier.name}</strong><span>{tier.settled} settled</span></div>
                        <div className="public-proof-tier-record"><b>{tier.won}W</b><b>{tier.lost}L</b>{tier.void > 0 && <b>{tier.void}V</b>}</div>
                        <span className="public-proof-rate">{proofPercent(tier.win_rate)}<small>hit rate</small></span>
                      </button>
                    )
                  })}
                </div>
                <div className="public-proof-metrics" aria-live="polite">
                  <div><span>Hit rate</span><strong>{proofPercent(activeTier.win_rate)}</strong><small>{activeTier.won}W · {activeTier.lost}L{activeTier.void > 0 ? ` · ${activeTier.void}V` : ''}</small></div>
                  <div><span>Paper P&amp;L</span><strong className={profitTone(activeTier.profit_units)}>{formatUnits(activeTier.profit_units)}</strong><small>{activeTier.staked_units.toLocaleString('en-GB', { maximumFractionDigits: 0 })} decided stakes</small></div>
                  <div><span>ROI</span><strong className={profitTone(activeTier.roi)}>{formatRoi(activeTier.roi)}</strong><small>P&amp;L ÷ staked</small></div>
                </div>
                <div className="public-proof-trend">
                  <div className="public-proof-trend-head"><strong>Equity, cumulative units</strong><span>{activeTier.name}</span></div>
                  <EquitySparkline points={activeTier.equity} label={activeTier.name} />
                </div>
              </> : <p className="public-proof-empty">No settled tickets in this window yet. Try a wider range.</p>}
              <p className="public-proof-note">Hit rate counts decided tickets only; void stakes are returned and add 0 units. Paper P&amp;L uses a flat 1-unit stake at the published combined odds, and ROI divides it by decided stakes — not a bankroll or staking plan. Past results describe this sample and do not predict the next match.</p>
            </div>
            {activeTicket && (
              <article className="public-proof-ticket" aria-labelledby="public-proof-ticket-title">
                <header>
                  <div>
                    <span className="public-proof-ticket-kicker">{activeTicketCursor === 0 ? 'MOST RECENT' : 'EARLIER'} {activeTicket.name.toUpperCase()} TICKET</span>
                    <h3 id="public-proof-ticket-title">{activeTicket.name} · {formatProofDate(activeTicket.target_date)}</h3>
                  </div>
                  <div className="public-proof-ticket-status">
                    {activeTicket.profit_units != null && <span className={`public-proof-pnl ${profitTone(activeTicket.profit_units)}`}>{formatUnits(activeTicket.profit_units)}</span>}
                    <span className={`public-proof-result is-${activeTicket.result ?? 'pending'}`}>{proofResult(activeTicket.result)}</span>
                  </div>
                </header>
                {activeTickets.length > 1 && (
                  <div className="public-proof-ticket-nav">
                    <button type="button" onClick={() => setTicketCursor(Math.max(0, activeTicketCursor - 1))} disabled={activeTicketCursor === 0} aria-label={`Newer ${activeTicket.name} ticket`}>‹ Newer</button>
                    <span>{activeTicketCursor + 1} of {activeTickets.length} recent</span>
                    <button type="button" onClick={() => setTicketCursor(Math.min(activeTickets.length - 1, activeTicketCursor + 1))} disabled={activeTicketCursor >= activeTickets.length - 1} aria-label={`Older ${activeTicket.name} ticket`}>Older ›</button>
                  </div>
                )}
                <div className="public-proof-ticket-meta">
                  <span>Published {formatProofDateTime(activeTicket.published_at)}</span>
                  <span>{activeTicket.publication_timing === 'pre_kickoff' ? 'Before kickoff' : activeTicket.publication_timing === 'post_kickoff' ? 'After kickoff' : 'Timing unknown'}</span>
                  <span>{activeTicket.combined_odds.toFixed(2)}× combined</span>
                </div>
                <ul className="public-proof-legs">
                  {activeTicket.legs.map((leg) => (
                    <li key={leg.position}>
                      <div className="public-proof-leg-match">
                        <strong>{leg.home_team} vs {leg.away_team}</strong>
                        <small>{leg.competition} · {legMarketLabel(leg.market, leg.selection)}</small>
                      </div>
                      <div className="public-proof-leg-result">
                        <span className={`public-proof-leg-state is-${leg.result}`}>{proofResult(leg.result)}</span>
                        {leg.home_goals != null && leg.away_goals != null && <b>{leg.home_goals}–{leg.away_goals}</b>}
                      </div>
                    </li>
                  ))}
                </ul>
                <footer>Paper record: flat 1-unit stake, settled at the published combined odds. Per-leg odds, model chance and every Q ≥75 pick sit behind Pro.</footer>
              </article>
            )}
          </div>
          <div className="public-proof-cta">
            <span>Follow the next slate as it is published.</span>
            <button className="public-cta" onClick={onCreateAccount}>Create a free account <span aria-hidden="true">→</span></button>
          </div>
        </>}
      </section>

      <nav className="public-section-nav" aria-label="Page sections">
        {([['public-record', 'Record'], ['public-matches', 'Matches'], ['public-product', 'How QwanEj works'], ['public-access', 'Plans'], ['public-faq', 'FAQs']] as const).map(([id, label]) => (
          <a key={id} className={activeSection === id ? 'is-active' : ''} href={`#${id}`} aria-current={activeSection === id ? 'location' : undefined}>{label}</a>
        ))}
      </nav>

      <div className="public-dashboard" id="public-matches">
        <section className="public-content" aria-labelledby="public-matches-title">
          <div className="public-dashboard-heading">
            <div><span className="public-section-kicker">MATCH CENTRE</span><h2 id="public-matches-title">Fixtures &amp; scores</h2><p>Browse public fixtures and follow the matchday as it unfolds.</p></div>
            <div className="public-match-controls">
              <div className="public-date-strip" aria-label="Choose fixture date">
                {[-2, -1, 0, 1, 2].map((offset) => {
                  const tabDate = offset === 0 ? date : shiftDate(date, offset)
                  const value = new Date(`${tabDate}T12:00:00`)
                  return <button key={offset} className={`public-date-tab ${offset === 0 ? 'is-selected' : ''}`} onClick={() => selectDate(tabDate)} aria-current={offset === 0 ? 'date' : undefined}><span>{value.toLocaleDateString('en-GB', { weekday: 'short' })}</span><strong>{value.getDate()}</strong>{tabDate === today && <small>TODAY</small>}</button>
                })}
              </div>
              <div className="public-status-filters" role="group" aria-label="Filter matches by status">
                {([['all', 'All matches', statusCounts.all], ['live', 'Live', statusCounts.live], ['scheduled', 'Upcoming', statusCounts.scheduled], ['finished', 'Finished', statusCounts.finished]] as const).map(([status, label, count]) => <button key={status} className={`public-filter-chip ${activeStatus === status ? 'is-active' : ''}`} onClick={() => selectStatus(status)} aria-pressed={activeStatus === status}>{status === 'live' && <span className="public-live-dot" />}{label}<span>{loading ? '—' : count}</span></button>)}
              </div>
            </div>
            <aside className="public-league-overview" aria-label="Filter fixtures by league">
              <div className="public-league-overview-heading"><strong>{date === today ? 'Leagues today' : 'Leagues on this date'}</strong><span>{loading ? '—' : matchCountLabel(leagueScopeTotal)}</span></div>
              <div className="public-league-overview-list">
                <button className={`public-league-overview-row${selectedLeague === '' ? ' is-selected' : ''}`} onClick={() => setSelectedLeague('')} aria-pressed={selectedLeague === ''}><span>All leagues</span><b>{loading ? '—' : leagueScopeTotal}</b></button>
                {leagueMatchCounts.map(([league, count]) => <button key={league} className={`public-league-overview-row${selectedLeague === league ? ' is-selected' : ''}`} onClick={() => setSelectedLeague(current => current === league ? '' : league)} aria-pressed={selectedLeague === league}><span title={league}>{league}</span><b>{loading ? '—' : count}</b></button>)}
                {!loading && leagueMatchCounts.length === 0 && <span className="public-league-overview-empty">No league fixtures for this date</span>}
              </div>
            </aside>
          </div>

          <div className="public-fixture-toolbar">
            <label className="public-search-box"><span aria-hidden="true">⌕</span><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search team or league" aria-label="Search teams and leagues" /></label>
            <span className="public-fixture-count">{loading ? 'Updating…' : `${matchCountLabel(visibleMatches.length)}${refreshedAt ? ` · updated ${refreshedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : ''}`}</span>
          </div>

          <div className="public-match-panel">
            {error ? <div className="public-empty"><strong>Fixture data is temporarily unavailable</strong><span>Please try again shortly.</span></div>
              : loading ? <div className="public-empty"><span>Loading fixtures…</span></div>
                : visibleMatches.length === 0 ? <div className="public-empty"><strong>No matches match these filters</strong><span>Try another date, league or search.</span></div>
                  : <div className="public-fixture-table-wrap"><table className="public-fixture-table">
                    <thead><tr>{sortHeader('kickoff', 'Kickoff Time')}{sortHeader('league', 'League')}{sortHeader('match', 'Match')}{sortHeader('statusScore', 'Status/Score')}</tr></thead>
                    <tbody>{displayedMatches.map((match) => {
                      const status = match.status.toLowerCase()
                      const hasScore = match.home_goals != null && match.away_goals != null
                      return <tr className="public-fixture-table-row" key={match.match_id}>
                        <td className="public-fixture-time"><time dateTime={match.kickoff_at}>{kickoffLabel(match.kickoff_at)}</time></td>
                        <td className="public-fixture-league" title={match.competition}>{match.competition}</td>
                        <td><div className="public-fixture-match" title={`${match.home_team} vs ${match.away_team}`}><span>{match.home_team}</span><small className="public-fixture-matchup-vs">vs</small><span>{match.away_team}</span><small className="public-fixture-competition">{match.competition}</small></div></td>
                        <td><div className="public-fixture-status-score"><span className={`public-fixture-state ${status === 'live' ? 'is-live' : ''}`}>{matchStatus(match)}</span>{hasScore && <strong>{match.home_goals} : {match.away_goals}</strong>}</div></td>
                      </tr>
                    })}</tbody>
                  </table></div>}
            <div className="public-match-panel-foot">Scores and match states are shown when available. Live fixtures refresh automatically. No outcome is guaranteed.</div>
          </div>
          {!loading && !error && visibleMatches.length > 5 && (
            <button className="public-show-matches" onClick={() => setShowAllMatches(current => !current)} aria-expanded={showAllMatches}>
              {showAllMatches ? 'Show fewer fixtures' : `Show all ${visibleMatches.length} fixtures`}
              <span aria-hidden="true">{showAllMatches ? '−' : '+'}</span>
            </button>
          )}
        </section>
      </div>

      <section className="public-product" id="public-product" aria-labelledby="public-product-title">
        <div className="public-product-heading">
          <span className="public-section-kicker">THE QwanEj APPROACH</span>
          <h2 id="public-product-title">From fixture list to final result.</h2>
          <p>Useful football research should show its work—and leave room for uncertainty.</p>
        </div>
        <div className="public-product-grid">
          <article className="public-product-card">
            <span className="public-product-number">01</span>
            <h3>Start with the match</h3>
            <p>Browse fixtures by date, competition, kickoff, live status and score. Sort the slate to find the games you want to follow.</p>
            <a href="#public-matches">Browse fixtures <span aria-hidden="true">→</span></a>
          </article>
          <article className="public-product-card">
            <span className="public-product-number">02</span>
            <h3>Read the recommendation in context</h3>
            <p>A free account shows the published ticket, its match legs and how it settled. Pro opens each selection, the captured odds, model chance and Q score.</p>
            <span className="public-product-note">Recommendations are opinions, not guarantees.</span>
          </article>
          <article className="public-product-card">
            <span className="public-product-number">03</span>
            <h3>Review the result honestly</h3>
            <p>When a match is complete, its score and settled selection outcome can be reviewed against the original published record.</p>
            <span className="public-product-note">Historical results describe the sample shown; they do not predict future results.</span>
          </article>
        </div>
      </section>

      <section className="public-access" id="public-access" aria-label="QwanEj account access">
        <div className="public-access-heading">
          <span className="public-section-kicker">START FREE, GO DEEPER WHEN YOU NEED TO</span>
          <h2>Choose how you want to explore.</h2>
          <p>You can look around before creating an account. Your workspace adds more ways to follow the game.</p>
        </div>
        <div className="public-access-grid">
          <article className="public-access-card">
            <div><span className="public-access-label">PUBLIC</span><h3>Take a look around</h3></div>
            <ul className="public-access-list">
              <li>Fixtures by date and competition</li>
              <li>Live status and completed scores</li>
              <li>No account required</li>
            </ul>
            <a href="#public-matches">Open the match centre <span aria-hidden="true">→</span></a>
          </article>
          <article className="public-access-card is-featured">
            <div><span className="public-access-label">FREE ACCOUNT</span><h3>Follow the daily slate</h3></div>
            <ul className="public-access-list">
              <li>Published Conservative and Balanced tickets</li>
              <li>Match legs, kickoff and settlement</li>
              <li>One workspace for each matchday</li>
            </ul>
            <button onClick={onCreateAccount}>Create a free account <span aria-hidden="true">→</span></button>
          </article>
          <article className="public-access-card">
            <div>
              <span className="public-access-label">PRO</span>
              <h3>Open the evidence</h3>
              <span className="public-access-price">{formatProPrice(offer?.price)}<small>/ month</small></span>
              <small className="public-access-price-note">Create a free account before checkout.</small>
            </div>
            <ul className="public-access-list">
              <li>Every Q ≥75 system pick, grouped by match</li>
              <li>Selections, captured odds and model chance</li>
              <li>Expanded published ticket history</li>
              <li>Stats &amp; trends with league context</li>
            </ul>
            <p className="public-access-card-note">Q is a 0–100 evidence score; 75+ marks a qualified pick.</p>
            <button onClick={onViewPro}>View the Pro plan <span aria-hidden="true">→</span></button>
          </article>
        </div>
        <p className="public-access-note">Pro is a recurring monthly card payment. You can manage or cancel it through Flutterwave’s subscription emails.</p>
      </section>

      <section className="public-faq" id="public-faq" aria-labelledby="public-faq-title">
        <div className="public-faq-heading"><span className="public-section-kicker">GOOD TO KNOW</span><h2 id="public-faq-title">A few quick answers.</h2></div>
        <div className="public-faq-list">
          <details><summary>What can I see without an account?</summary><p>Public fixtures include the competition, teams, kickoff or live status, and scores when available. Personal account information and workspace tools stay behind sign-in.</p></details>
          <details><summary>What does QwanEj do with recommendations?</summary><p>Each ticket is dated and published before kickoff when possible, then settled against the final score. Free accounts see the match legs and settlement; Pro adds the selection, captured odds and model chance for every leg. A recommendation is never a promise of a result.</p></details>
          <details><summary>What does Q ≥75 mean?</summary><p>Q is a 0–100 evidence score for a selection. It combines the model’s probability, the value at the captured price, recent form, expected goals, market agreement and data quality. A pick needs 75 or more to qualify as a system pick. It is a screening score, not a guarantee.</p></details>
          <details><summary>Where do fixtures, scores and prices come from?</summary><p>Fixtures, live scores and results come from a third-party football data provider. Captured prices are recorded when a ticket is published, so they can differ from your bookmaker or move before kickoff. If a feed is delayed or unavailable, QwanEj shows the last record it holds rather than inventing a result.</p></details>
          <details><summary>Does QwanEj guarantee wins or profit?</summary><p>No. Football outcomes are uncertain. Any historical result is a record of completed matches, not a guarantee or forecast of future performance.</p></details>
        </div>
        <div className="public-faq-cta"><div><strong>Ready to follow the next matchday?</strong><span>Create a free account to open your QwanEj workspace.</span></div><button className="public-cta" onClick={onCreateAccount}>Get started for free <span aria-hidden="true">→</span></button></div>
      </section>

      <footer className="public-footer"><span>QwanEj · Intelligence beyond numbers</span><span>Information only. Football outcomes are uncertain; no result is guaranteed.</span></footer>
    </main>
  )
}
