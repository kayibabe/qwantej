import { useEffect, useMemo, useState } from 'react'
import type { MatchFixture } from '../lib/api'
import { fetchPublicMatchFixtures } from '../lib/api'
import { TODAY } from './dailyTickets/helpers'
import './PublicHome.css'
import './PublicHome.brand.css'

interface PublicHomeProps {
  date: string
  onDateChange: (date: string) => void
  onSignIn: () => void
  onCreateAccount: () => void
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

function matchStatus(match: MatchFixture) {
  const status = match.status.toLowerCase()
  if (status === 'live') return match.elapsed_minutes != null ? `${match.elapsed_minutes}\u2032` : match.live_phase || 'Live'
  if (status === 'finished') return 'FT'
  if (status === 'postponed') return 'Postponed'
  if (status === 'cancelled') return 'Cancelled'
  if (status === 'abandoned') return 'Abandoned \u00b7 review'
  if (status === 'awarded') return 'Awarded \u00b7 review'
  return 'Upcoming'
}

export default function PublicHome({ date, onDateChange, onSignIn, onCreateAccount }: PublicHomeProps) {
  const [matches, setMatches] = useState<MatchFixture[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [activeStatus, setActiveStatus] = useState<'all' | 'live' | 'scheduled' | 'finished'>('all')
  const [search, setSearch] = useState('')
  const [selectedLeague, setSelectedLeague] = useState('')
  const [showAllMatches, setShowAllMatches] = useState(false)
  const [sortKey, setSortKey] = useState<FixtureSortKey>('kickoff')
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(false)
    fetchPublicMatchFixtures(date)
      .then((rows) => { if (active) setMatches(rows) })
      .catch(() => { if (active) { setMatches([]); setError(true) } })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [date])

  const counts = useMemo(() => ({
    live: matches.filter((match) => match.status.toLowerCase() === 'live').length,
    finished: matches.filter((match) => match.status.toLowerCase() === 'finished').length,
    upcoming: matches.filter((match) => match.status.toLowerCase() === 'scheduled').length,
  }), [matches])
  const today = TODAY
  const availableLeagues = useMemo(() => [...new Set(matches.map((match) => match.competition))].sort((a, b) => a.localeCompare(b)), [matches])
  const leagueMatchCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const match of matches) counts.set(match.competition, (counts.get(match.competition) ?? 0) + 1)
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  }, [matches])
  const visibleMatches = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase()
    const filtered = matches.filter((match) => {
      const status = match.status.toLowerCase()
      const statusMatch = activeStatus === 'all' || status === activeStatus
      const leagueMatch = !selectedLeague || match.competition === selectedLeague
      const searchMatch = !needle || `${match.home_team} ${match.away_team} ${match.competition}`.toLocaleLowerCase().includes(needle)
      return statusMatch && leagueMatch && searchMatch
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
  }, [matches, activeStatus, selectedLeague, search, sortKey, sortDirection])
  const displayedMatches = showAllMatches ? visibleMatches : visibleMatches.slice(0, 10)

  useEffect(() => {
    setShowAllMatches(false)
  }, [date, activeStatus, search, selectedLeague])

  const sortHeader = (key: FixtureSortKey, label: string) => {
    const active = sortKey === key
    const ariaSort = active ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'
    return <th scope="col" aria-sort={ariaSort}><button className="public-fixture-sort-button" onClick={() => {
      if (active) setSortDirection(current => current === 'asc' ? 'desc' : 'asc')
      else { setSortKey(key); setSortDirection('asc') }
    }}>{label}<span aria-hidden="true">{active ? (sortDirection === 'asc' ? '\u2191' : '\u2193') : '\u2195'}</span></button></th>
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
          <button className="public-link-button" onClick={onSignIn}>Sign in</button>
          <button className="public-cta" onClick={onCreateAccount}>Create free account <span aria-hidden="true">\u2192</span></button>
        </nav>
      </header>

      <section className="public-hero" aria-labelledby="public-hero-title">
        <div className="public-hero-copy">
          <span className="public-eyebrow">EVIDENCE-LED FOOTBALL RESEARCH</span>
          <h1 id="public-hero-title">The markets the model rates, <em>with the evidence attached.</em></h1>
          <p>QwanEj scores the football markets it can settle, publishes only the selections that clear its gates, and keeps the price, the reasoning and the result with every pick. When nothing qualifies, nothing goes out.</p>
          <div className="public-hero-actions">
            <button className="public-cta public-cta-large" onClick={onCreateAccount}>Start free <span aria-hidden="true">\u2192</span></button>
            <a className="public-quiet-button" href="#public-coverage">See what it covers</a>
          </div>
          <div className="public-hero-promises">
            <span>Dated published selections</span>
            <span>Price and reasoning kept with each pick</span>
            <span>Results settled from the scoreline</span>
          </div>
        </div>
        <aside className="public-hero-card" aria-label="How a published selection is reviewed">
          <div className="public-hero-card-head"><span>THE RECORD</span><span>From pick to result</span></div>
          <ol className="public-evidence-flow">
            <li><span>01</span><div><strong>Published selection</strong><small>What was selected, and when</small></div></li>
            <li><span>02</span><div><strong>Price context</strong><small>Bookmaker, odds and quote time</small></div></li>
            <li><span>03</span><div><strong>Settled outcome</strong><small>Final score and pick result</small></div></li>
          </ol>
          <div className="public-hero-card-foot">Past outcomes describe their sample. They do not predict the next match.</div>
        </aside>
      </section>

      <nav className="public-section-nav" aria-label="Page sections">
        <a href="#public-coverage">What it covers</a>
        <a href="#public-gates">How it works</a>
        <a className="is-active" href="#public-matches" aria-current="page">Matches</a>
        <a href="#public-faq">FAQs</a>
      </nav>

      <section className="public-coverage" id="public-coverage" aria-labelledby="public-coverage-title">
        <div className="public-coverage-heading">
          <span className="public-section-kicker">WHAT THE ANALYSIS COVERS</span>
          <h2 id="public-coverage-title">Five market families, scored from the scoreline.</h2>
          <p>Every selection QwanEj scores settles from regulation-time match scores. Inside that boundary the work is deliberate: one contract per market, one gate per market, and no family added until its evidence is there.</p>
        </div>
        <ul className="public-coverage-grid">
          <li className="public-coverage-card">
            <span className="public-coverage-tag">1X2</span>
            <h3>Match result</h3>
            <p>Home win, away win or draw, read from a joint home and away score distribution built for the fixture.</p>
          </li>
          <li className="public-coverage-card">
            <span className="public-coverage-tag">1X / X2</span>
            <h3>Double chance</h3>
            <p>Two outcomes covered in one selection, scored and settled from the same score distribution.</p>
          </li>
          <li className="public-coverage-card">
            <span className="public-coverage-tag">DNB</span>
            <h3>Draw no bet</h3>
            <p>Your side to win, with a draw pushing the selection instead of losing it.</p>
          </li>
          <li className="public-coverage-card">
            <span className="public-coverage-tag">TOTALS</span>
            <h3>Total goals</h3>
            <p>Selected half-goal lines on the totals path, each with its own qualification policy and blockers.</p>
          </li>
          <li className="public-coverage-card">
            <span className="public-coverage-tag">BTTS</span>
            <h3>Both teams to score</h3>
            <p>Full-match yes and no, settled on the final score at the end of regulation time.</p>
          </li>
        </ul>
        <div className="public-coverage-scope">
          <div>
            <strong>18 scored selections</strong>
            <span>in the market catalogue, kept separate from settlement-only lines that are registered but never scored.</span>
          </div>
          <div>
            <strong>Regulation time only</strong>
            <span>settlement reads the 90-minute score. Extra time, shootouts and season outrights sit outside the surface.</span>
          </div>
        </div>
        <aside className="public-coverage-limit" aria-label="What the analysis does not cover">
          <h3>What it does not cover yet</h3>
          <p>Corners, cards, shots, player markets, goal timing, in-play, and combined bet-builder markets are not scored. Each one is logged in the market register as research, blocked on data or blocked on a dependency, and none of them can produce a published selection. A market label in a sportsbook does not mean QwanEj has the data behind it.</p>
        </aside>
      </section>

      <section className="public-gates" id="public-gates" aria-labelledby="public-gates-title">
        <div className="public-gates-heading">
          <span className="public-section-kicker">HOW A SELECTION IS PUBLISHED</span>
          <h2 id="public-gates-title">Nothing goes out until it clears its gates.</h2>
          <p>A market earns the right to publish. The path is the same for every family, and it can stop at any step.</p>
        </div>
        <ol className="public-gates-rail">
          <li><span>01</span><strong>Contract registered</strong><small>Settlement rule written down before a probability is attached to it.</small></li>
          <li><span>02</span><strong>Data ready</strong><small>Point-in-time inputs and outcome labels measured for coverage and provenance.</small></li>
          <li><span>03</span><strong>Shadow scored</strong><small>Forecasts captured without being used for a decision.</small></li>
          <li><span>04</span><strong>Validated</strong><small>Frozen chronological evaluation against gates set in advance.</small></li>
          <li><span>05</span><strong>Promoted</strong><small>A versioned profile switches on, with an effective date on the record.</small></li>
        </ol>
        <div className="public-gates-cards">
          <article>
            <h3>No edge, no pick</h3>
            <p>Qualification fails closed. A missing quote, bookmaker, feature snapshot or pre-kickoff odds timestamp blocks the selection, and a day with zero qualifiers is a normal result rather than a reason to lower the bar.</p>
          </article>
          <article>
            <h3>Every pick keeps its evidence</h3>
            <p>A published selection stores its model version, probability, bookmaker, odds and quote timestamp, the reasons behind the decision, and a hash of the snapshot, so an earlier call can be read back exactly as it was made.</p>
          </article>
          <article>
            <h3>Promotion, never drift</h3>
            <p>A profile that misses its coverage, calibration or settlement checks is suspended. No new selection qualifies from it until it has been validated again.</p>
          </article>
        </div>
      </section>

      <div className="public-dashboard" id="public-matches">
        <section className="public-content" aria-labelledby="public-matches-title">
          <div className="public-dashboard-heading">
            <div><span className="public-section-kicker">MATCH CENTRE</span><h2 id="public-matches-title">Fixtures &amp; scores</h2><p>Browse public fixtures and follow the matchday as it unfolds.</p></div>
            <div className="public-match-controls">
              <div className="public-date-strip" aria-label="Choose fixture date">
                <button className={`public-date-live ${activeStatus === 'live' ? 'is-active' : ''}`} onClick={() => setActiveStatus(current => current === 'live' ? 'all' : 'live')} aria-pressed={activeStatus === 'live'}><span className="public-live-dot" />Live <b>{counts.live}</b></button>
                {[-2, -1, 0, 1, 2].map((offset) => {
                  const tabDate = offset === 0 ? date : shiftDate(date, offset)
                  const value = new Date(`${tabDate}T12:00:00`)
                  return <button key={offset} className={`public-date-tab ${offset === 0 ? 'is-selected' : ''}`} onClick={() => onDateChange(tabDate)} aria-current={offset === 0 ? 'date' : undefined}><span>{value.toLocaleDateString('en-GB', { weekday: 'short' })}</span><strong>{value.getDate()}</strong>{tabDate === today && <small>TODAY</small>}</button>
                })}
              </div>
              <div className="public-status-filters" role="group" aria-label="Filter matches by status">
                {([['all', 'All matches', matches.length], ['scheduled', 'Upcoming', counts.upcoming], ['finished', 'Finished', counts.finished]] as const).map(([status, label, count]) => <button key={status} className={`public-filter-chip ${activeStatus === status ? 'is-active' : ''}`} onClick={() => setActiveStatus(status)} aria-pressed={activeStatus === status}>{label}<span>{loading ? '\u2014' : count}</span></button>)}
              </div>
            </div>
            <aside className="public-league-overview" aria-label="Filter fixtures by league">
              <div className="public-league-overview-heading"><strong>{date === today ? 'Leagues today' : 'Leagues on this date'}</strong><span>{loading ? '\u2014' : `${matches.length} matches`}</span></div>
              <div className="public-league-overview-list">
                <button className={`public-league-overview-row${selectedLeague === '' ? ' is-selected' : ''}`} onClick={() => setSelectedLeague('')} aria-pressed={selectedLeague === ''}><span>All leagues</span><b>{loading ? '\u2014' : matches.length}</b></button>
                {leagueMatchCounts.map(([league, count]) => <button key={league} className={`public-league-overview-row${selectedLeague === league ? ' is-selected' : ''}`} onClick={() => setSelectedLeague(current => current === league ? '' : league)} aria-pressed={selectedLeague === league}><span title={league}>{league}</span><b>{loading ? '\u2014' : count}</b></button>)}
                {!loading && leagueMatchCounts.length === 0 && <span className="public-league-overview-empty">No league fixtures for this date</span>}
              </div>
            </aside>
          </div>

          <div className="public-fixture-toolbar">
            <label className="public-search-box"><span aria-hidden="true">\u2315</span><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Team, league or country" aria-label="Search teams and leagues" /></label>
            <label className="public-league-select"><span className="public-select-icon" aria-hidden="true">\u2637</span><select value={selectedLeague} onChange={(event) => setSelectedLeague(event.target.value)} aria-label="Filter by league"><option value="">All leagues</option>{availableLeagues.map((league) => <option key={league} value={league}>{league}</option>)}</select></label>
            <span className="public-fixture-count">{loading ? 'Updating\u2026' : `${visibleMatches.length} matches`}</span>
          </div>

          <div className="public-match-panel">
            {error ? <div className="public-empty"><strong>Fixture data is temporarily unavailable</strong><span>Please try again shortly.</span></div>
              : loading ? <div className="public-empty"><span>Loading fixtures\u2026</span></div>
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
            <div className="public-match-panel-foot">Scores and match states are shown when available. No outcome is guaranteed.</div>
          </div>
          {!loading && !error && visibleMatches.length > 10 && (
            <button className="public-show-matches" onClick={() => setShowAllMatches(current => !current)} aria-expanded={showAllMatches}>
              {showAllMatches ? 'Show fewer fixtures' : `Show all ${visibleMatches.length} fixtures`}
              <span aria-hidden="true">{showAllMatches ? '\u2212' : '+'}</span>
            </button>
          )}
        </section>
      </div>

      <section className="public-product" id="public-workspace" aria-labelledby="public-product-title">
        <div className="public-product-heading">
          <span className="public-section-kicker">INSIDE THE WORKSPACE</span>
          <h2 id="public-product-title">A record you can read back, match by match.</h2>
          <p>The public page shows the matchday. An account opens the part that keeps score.</p>
        </div>
        <div className="public-product-grid">
          <article className="public-product-card">
            <span className="public-product-number">01</span>
            <h3>Start on the published slate</h3>
            <p>Your workspace opens on the day’s published selections, each with its price context and, once the match is done, its settled result.</p>
            <a href="#public-matches">Browse fixtures <span aria-hidden="true">→</span></a>
          </article>
          <article className="public-product-card">
            <span className="public-product-number">02</span>
            <h3>Follow the whole matchday</h3>
            <p>Fixtures by date, league, kickoff, live phase and score, for today, tomorrow and the days either side of them.</p>
            <span className="public-product-note">Live status and phase are read from the fixture feed as the match runs.</span>
          </article>
          <article className="public-product-card">
            <span className="public-product-number">03</span>
            <h3>Check the work</h3>
            <p>Track your own journal against the published record, and read league results and team trends from completed matches in Stats and trends.</p>
            <span className="public-product-note">A recommendation is an opinion with evidence attached, never a promise.</span>
          </article>
        </div>
      </section>

      <section className="public-access" aria-label="QwanEj account access">
        <div className="public-access-heading">
          <span className="public-section-kicker">START FREE, GO DEEPER WHEN YOU NEED TO</span>
          <h2>Choose how you want to explore.</h2>
          <p>You can look around before creating an account. Your workspace adds more ways to follow the game.</p>
        </div>
        <div className="public-access-grid">
          <article className="public-access-card">
            <div><span className="public-access-label">PUBLIC</span><h3>Take a look around</h3></div>
            <p>Explore public fixtures, competition names, live status and completed scores, without signing in.</p>
            <a href="#public-matches">Open the match centre <span aria-hidden="true">→</span></a>
          </article>
          <article className="public-access-card is-featured">
            <div><span className="public-access-label">FREE ACCOUNT</span><h3>Follow the daily slate</h3></div>
            <p>Open your QwanEj workspace for daily published selections, match browsing and live scores.</p>
            <button onClick={onCreateAccount}>Create a free account <span aria-hidden="true">→</span></button>
          </article>
          <article className="public-access-card">
            <div><span className="public-access-label">PRO</span><h3>Explore more detail</h3></div>
            <p>Pro adds detailed odds and expanded ticket history. Stats and trends gives league context from completed matches.</p>
            <button onClick={onCreateAccount}>See what’s inside <span aria-hidden="true">→</span></button>
          </article>
        </div>
      </section>

      <section className="public-faq" id="public-faq" aria-labelledby="public-faq-title">
        <div className="public-faq-heading"><span className="public-section-kicker">GOOD TO KNOW</span><h2 id="public-faq-title">A few quick answers.</h2></div>
        <div className="public-faq-list">
          <details><summary>What can I see without an account?</summary><p>Public fixtures include the competition, teams, kickoff or live status, and scores when available. Personal account information and workspace tools stay behind sign-in.</p></details>
          <details><summary>Which markets does QwanEj score?</summary><p>Match result, double chance, draw no bet, selected total-goals lines and both teams to score. Each one has its own registered contract, its own qualification gate and settlement from regulation-time scores. The market catalogue holds 18 scored selections.</p></details>
          <details><summary>Does it cover corners, cards or player markets?</summary><p>Not yet. Corners, cards, shots, player markets, goal timing, in-play and combined markets are logged in the market register as research or blocked on data. Nothing is published from a market until the data behind it and its validation are in place.</p></details>
          <details><summary>What does QwanEj do with a recommendation?</summary><p>It publishes the selection with the price context it captured and keeps that record separate from research candidates. Where a quote exists, it can be read back alongside the selection. A recommendation is never a promise of a result.</p></details>
          <details><summary>Does QwanEj guarantee wins or profit?</summary><p>No. Football outcomes are uncertain. Any historical result is a record of completed matches, not a guarantee or a forecast of future performance, and QwanEj does not publish a hit rate, a return or a profit claim.</p></details>
        </div>
        <div className="public-faq-cta"><div><strong>Ready to follow the next matchday?</strong><span>Create a free account to open your QwanEj workspace.</span></div><button className="public-cta" onClick={onCreateAccount}>Get started free <span aria-hidden="true">→</span></button></div>
      </section>

      <footer className="public-footer"><span>QwanEj · Intelligence beyond numbers</span><span>Information only. Football outcomes are uncertain. No result is guaranteed.</span></footer>
    </main>
  )
}
