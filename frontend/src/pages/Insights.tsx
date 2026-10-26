import { Fragment, useEffect, useState } from 'react'
import { fetchLeagueInsights, searchCompletedMatches, type CompletedMatchSearchResult, type LeagueInsights } from '../lib/api'

function percent(value: number | null | undefined) {
  return value == null ? 'Unavailable' : `${value.toFixed(1)}%`
}

function RecentForm({ form }: { form: string }) {
  if (!form) return <>—</>

  return (
    <span className="insights-form-sequence">
      {[...form].map((result, index) => (
        <Fragment key={`${result}-${index}`}>
          {index > 0 && <span className="insights-form-separator" aria-hidden="true">-</span>}
          <span className={`form-pill ${result.toLowerCase()}`}>{result}</span>
        </Fragment>
      ))}
    </span>
  )
}

export default function InsightsPage() {
  const [data, setData] = useState<LeagueInsights | null>(null)
  const [competitionId, setCompetitionId] = useState('')
  const [season, setSeason] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [matchSearch, setMatchSearch] = useState('')
  const [matchResults, setMatchResults] = useState<CompletedMatchSearchResult[]>([])
  const [searchingMatches, setSearchingMatches] = useState(false)
  const [matchSearchError, setMatchSearchError] = useState('')

  useEffect(() => {
    let current = true
    setLoading(true)
    setError('')
    fetchLeagueInsights(competitionId ? Number(competitionId) : undefined, season || undefined)
      .then((result) => {
        if (!current) return
        setData(result)
        if (!competitionId && result.competitions.length) {
          setCompetitionId(String(result.competitions[0].id))
          setSeason(result.competitions[0].seasons[0] ?? '')
        }
      })
      .catch(() => { if (current) setError('League insights are temporarily unavailable. Please try again.') })
      .finally(() => { if (current) setLoading(false) })
    return () => { current = false }
  }, [competitionId, season])

  useEffect(() => {
    const query = matchSearch.trim()
    if (query.length < 2) {
      setMatchResults([])
      setSearchingMatches(false)
      setMatchSearchError('')
      return
    }

    let current = true
    setSearchingMatches(true)
    setMatchSearchError('')
    const timer = window.setTimeout(() => {
      searchCompletedMatches(query)
        .then((results) => { if (current) setMatchResults(results) })
        .catch(() => { if (current) setMatchSearchError('Match search is temporarily unavailable. Please try again.') })
        .finally(() => { if (current) setSearchingMatches(false) })
    }, 250)
    return () => {
      current = false
      window.clearTimeout(timer)
    }
  }, [matchSearch])

  const selectedCompetition = data?.competitions.find((item) => String(item.id) === competitionId)
  const summary = data?.summary

  return (
    <section className="league-insights-page">
      <div className="section-heading">
        <div><h1>Stats &amp; trends</h1><p>League results and team form, calculated from completed matches in QwanEj’s database.</p></div>
      </div>
      <section className="insights-search-card" aria-labelledby="insights-search-title">
        <div className="insights-search-heading">
          <div><h2 id="insights-search-title">Search completed matches</h2><p>Search across all competitions and seasons using complete words from either team name.</p></div>
          {matchSearch.trim().length >= 2 && !searchingMatches && !matchSearchError && <span>{matchResults.length}{matchResults.length === 100 ? '+' : ''} {matchResults.length === 1 ? 'match' : 'matches'} found</span>}
        </div>
        <label className="insights-search-field">
          <span className="sr-only">Search by team name</span>
          <input value={matchSearch} onChange={(event) => setMatchSearch(event.target.value)} placeholder="For example, Bayern or Dortmund" type="search" />
        </label>
        {matchSearch.trim().length === 1 && <p className="insights-search-empty" role="status">Enter at least 2 characters to search all competitions.</p>}
        {searchingMatches && <p className="insights-search-empty" role="status">Searching all completed matches…</p>}
        {matchSearchError && <p className="insights-search-empty" role="alert">{matchSearchError}</p>}
        {matchSearch.trim().length >= 2 && !searchingMatches && !matchSearchError && (matchResults.length ? (
          <div className="insights-search-results" aria-live="polite">
            {matchResults.map((match) => (
              <article className="insights-search-result" key={match.match_id}>
                <div><time dateTime={match.kickoff_at}>{new Date(match.kickoff_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}</time><span className="insights-search-competition">{match.competition} · {match.season}</span></div>
                <strong>{match.home_team} <span>{match.home_goals}–{match.away_goals}</span> {match.away_team}</strong>
              </article>
            ))}
          </div>
        ) : <p className="insights-search-empty" role="status">No completed matches found for “{matchSearch}”. Check the spelling and enter a complete team word.</p>)}
      </section>
      <div className="insights-controls">
        <label>Competition
          <select value={competitionId} onChange={(event) => {
            const next = data?.competitions.find((item) => String(item.id) === event.target.value)
            setCompetitionId(event.target.value)
            setSeason(next?.seasons[0] ?? '')
          }}>
            <option value="">Choose a competition</option>
            {data?.competitions.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.country}</option>)}
          </select>
        </label>
        <label>Season
          <select value={season} onChange={(event) => setSeason(event.target.value)} disabled={!selectedCompetition}>
            {selectedCompetition?.seasons.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        {selectedCompetition && <span>{selectedCompetition.completed_matches} completed matches across seasons</span>}
      </div>
      {error && <p className="insights-notice" role="alert">{error}</p>}
      {loading && <p className="insights-notice" role="status">Loading results…</p>}
      {!loading && !error && data?.competitions.length === 0 && <p className="insights-notice">No completed match results are available yet.</p>}
      {!loading && !error && summary && (
        <>
          <div className="insights-sample-note">Based on {summary.played} completed matches · {selectedCompetition?.name} · {season}</div>
          <div className="insights-metric-grid">
            <article><span>Average goals</span><strong>{summary.average_goals?.toFixed(2) ?? 'Unavailable'}</strong></article>
            <article><span>Home wins</span><strong>{percent(summary.home_win_pct)}</strong></article>
            <article><span>Draws</span><strong>{percent(summary.draw_pct)}</strong></article>
            <article><span>Away wins</span><strong>{percent(summary.away_win_pct)}</strong></article>
            <article><span>Both teams scored</span><strong>{percent(summary.btts_pct)}</strong></article>
            <article><span>Over 2.5 goals</span><strong>{percent(summary.over_2_5_pct)}</strong></article>
            <article><span>xG coverage</span><strong>{percent(summary.xg_coverage_pct)}</strong></article>
          </div>
          <section className="insights-table-card">
            <div className="insights-table-heading"><h2>Team table</h2><span>Sorted by points, goal difference, then goals scored</span></div>
            <div className="insights-table-scroll"><table>
              <thead><tr><th>#</th><th>Team</th><th>Pl</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th><th>GD</th><th>Pts</th><th>Form</th><th>Avg xG</th></tr></thead>
              <tbody>{data.teams.map((team, index) => <tr key={team.team_id}>
                <td>{index + 1}</td><th scope="row">{team.team}</th><td>{team.played}</td><td>{team.won}</td><td>{team.drawn}</td><td>{team.lost}</td><td>{team.goals_for}</td><td>{team.goals_against}</td><td>{team.goal_difference > 0 ? `+${team.goal_difference}` : team.goal_difference}</td><td><strong>{team.points}</strong></td><td aria-label={`Recent form ${team.recent_form ? [...team.recent_form].join('-') : 'unavailable'}`}><RecentForm form={team.recent_form} /></td><td><span className="insights-xg-value">{team.avg_xg == null ? '—' : team.avg_xg.toFixed(2)}</span><span className="insights-xg-coverage">{team.xg_matches}/{team.played} matches</span></td>
              </tr>)}</tbody>
            </table></div>
          </section>
          <p className="insights-footnote">Avg xG uses only matches where the provider recorded xG; the count beside each average shows its sample size. Percentages describe this completed-match sample and are not forecasts.</p>
        </>
      )}
    </section>
  )
}
