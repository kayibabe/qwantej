import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { fetchLeagueInsights, searchCompletedMatches, type CompletedMatchSearchResult, type LeagueInsights } from '../lib/api'

function percent(value: number | null | undefined) {
  return value == null ? 'Unavailable' : `${value.toFixed(1)}%`
}

function RecentForm({ form }: { form: string }) {
  if (!form) return <>—</>

  return (
    <span className="inline-flex items-center gap-1">
      {[...form].map((result, index) => (
        <Fragment key={`${result}-${index}`}>
          {index > 0 && <span className="px-0.5 text-slate-600" aria-hidden="true">-</span>}
          <span className={`inline-flex h-7 min-w-7 items-center justify-center rounded px-1 text-sm font-bold ${
            result === 'W' ? 'bg-emerald-50 text-emerald-700' : result === 'D' ? 'bg-amber-50 text-amber-700' : result === 'L' ? 'bg-rose-50 text-rose-700' : 'bg-slate-100 text-slate-700'
          }`}>{result}</span>
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
  const requestId = useRef(0)

  // The first response already carries the default scope. Applying it to the
  // selects must not trigger a duplicate request with the same parameters.
  const load = useCallback(async (nextCompetitionId?: number, nextSeason?: string) => {
    const id = ++requestId.current
    setLoading(true)
    setError('')
    try {
      const result = await fetchLeagueInsights(nextCompetitionId, nextSeason)
      if (id !== requestId.current) return
      setData(result)
      if (nextCompetitionId == null && result.competitions.length) {
        setCompetitionId(String(result.competition_id ?? result.competitions[0].id))
        setSeason(result.season ?? result.competitions[0].seasons[0] ?? '')
      }
    } catch {
      if (id === requestId.current) setError('League insights are temporarily unavailable. Showing the last loaded scope, if any.')
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
    return () => { requestId.current += 1 }
  }, [load])

  const selectCompetition = (value: string) => {
    const next = data?.competitions.find(item => String(item.id) === value)
    setCompetitionId(value)
    setSeason(next?.seasons[0] ?? '')
    void load(value ? Number(value) : undefined, next?.seasons[0])
  }

  const selectSeason = (value: string) => {
    setSeason(value)
    void load(competitionId ? Number(competitionId) : undefined, value)
  }

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

  const selectedCompetition = data?.competitions.find(item => String(item.id) === String(data.competition_id ?? competitionId))
  const appliedSeason = data?.season ?? season
  const summary = data?.summary
  const isStale = Boolean(error && data)

  return (
    <section className="page-content space-y-4">
      <div>
        <span className="text-sm font-semibold text-slate-600">Stats &amp; trends</span>
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Stats &amp; trends</h1>
        <p className="mt-1 max-w-3xl text-base leading-relaxed text-slate-600">League results and team form, calculated from completed matches in QwantEj’s database.</p>
      </div>
      <section className="rounded-xl border border-slate-200 bg-white overflow-hidden" aria-labelledby="insights-search-title">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <div><h2 id="insights-search-title" className="text-sm font-bold text-slate-600">Search completed matches</h2><p className="mt-1 text-base leading-relaxed text-slate-600">Search across all competitions and seasons using complete words from either team name.</p></div>
          {matchSearch.trim().length >= 2 && !searchingMatches && !matchSearchError && <span className="text-sm font-semibold text-slate-700 font-mono tabular-nums">{matchResults.length}{matchResults.length === 100 ? '+' : ''} {matchResults.length === 1 ? 'match' : 'matches'} found</span>}
        </div>
        <div className="px-4 py-4 space-y-3">
          <label className="block">
            <span className="sr-only">Search by team name</span>
            <input className="h-11 w-full px-3 text-base text-slate-900 bg-white border border-slate-200 rounded-lg placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-emerald-700/20 focus:border-emerald-700" value={matchSearch} onChange={(event) => setMatchSearch(event.target.value)} placeholder="For example, Bayern or Dortmund" type="search" />
          </label>
          <div aria-live="polite">
            {matchSearch.trim().length === 1 && <p className="text-base text-slate-700" role="status">Enter at least 2 characters to search all competitions.</p>}
            {searchingMatches && <p className="text-base text-slate-700" role="status">Searching all completed matches…</p>}
            {matchSearchError && <p className="text-base text-red-700" role="alert">{matchSearchError}</p>}
          </div>
          {matchSearch.trim().length >= 2 && !searchingMatches && !matchSearchError && (matchResults.length ? (
            <div className="divide-y divide-slate-100 rounded-lg border border-slate-200" aria-live="polite">
              {matchResults.map((match) => (
                <article className="flex flex-wrap items-center justify-between gap-2 px-3 py-3 text-base text-slate-700" key={match.match_id}>
                  <div className="flex flex-wrap items-center gap-2 text-slate-600"><time dateTime={match.kickoff_at} className="font-mono tabular-nums">{new Date(match.kickoff_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}</time><span>{match.competition} · {match.season}</span></div>
                  <strong className="text-slate-900">{match.home_team} <span className="font-mono tabular-nums text-slate-800">{match.home_goals}–{match.away_goals}</span> {match.away_team}</strong>
                </article>
              ))}
            </div>
          ) : <p className="text-base text-slate-700" role="status">No completed matches found for “{matchSearch}”. Check the spelling and enter a complete team word.</p>)}
        </div>
      </section>
      <section className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4" aria-label="League insights scope">
        <label className="flex flex-col gap-1 text-sm font-semibold text-slate-600">Competition
          <select className="h-11 min-w-[240px] rounded-lg border border-slate-200 bg-white px-3 text-base font-medium normal-case tracking-normal text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-700/20 focus:border-emerald-700" value={competitionId} onChange={(event) => selectCompetition(event.target.value)}>
            <option value="">Choose a competition</option>
            {data?.competitions.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.country}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm font-semibold text-slate-600">Season
          <select className="h-11 min-w-[160px] rounded-lg border border-slate-200 bg-white px-3 text-base font-medium normal-case tracking-normal text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-700/20 focus:border-emerald-700 disabled:opacity-50" value={season} onChange={(event) => selectSeason(event.target.value)} disabled={!selectedCompetition}>
            {selectedCompetition?.seasons.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
      </section>
      <div aria-live="polite">
        {error && <p className={`rounded-xl border px-4 py-3 text-base leading-relaxed ${isStale ? 'border-amber-200 bg-amber-50 text-amber-900' : 'border-red-200 bg-red-50 text-red-700'}`} role="alert">{error}</p>}
        {loading && data && <p className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-base text-slate-700" role="status">Updating results for the selected scope…</p>}
      </div>
      {loading && !data && <p className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-base text-slate-700" role="status">Loading results…</p>}
      {!loading && !error && data?.competitions.length === 0 && <p className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-base text-slate-700">No completed match results are available yet.</p>}
      {summary && data && (
        <>
          <p className="text-base text-slate-700" role="status"><strong>Applied scope:</strong> {selectedCompetition?.name ?? 'All competitions'} · {appliedSeason ?? 'all seasons'} · <span className="font-mono tabular-nums font-semibold text-slate-900">{summary.played}</span> completed matches in this scope.</p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-7">
            {[['Average goals', summary.average_goals?.toFixed(2) ?? 'Unavailable'], ['Home wins', percent(summary.home_win_pct)], ['Draws', percent(summary.draw_pct)], ['Away wins', percent(summary.away_win_pct)], ['Both teams scored', percent(summary.btts_pct)], ['Over 2.5 goals', percent(summary.over_2_5_pct)], ['xG coverage', percent(summary.xg_coverage_pct)]].map(([label, value]) => (
              <article key={label} className="rounded-xl border border-slate-200 bg-white px-4 py-3"><span className="block text-sm font-medium text-slate-600">{label}</span><strong className="mt-1 block font-mono text-xl font-bold tabular-nums text-slate-900">{value}</strong></article>
            ))}
          </div>
          <section className="rounded-xl border border-slate-200 bg-white overflow-hidden" aria-labelledby="insights-team-table-title">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3"><h2 id="insights-team-table-title" className="text-sm font-bold text-slate-600">Team table</h2><span className="text-sm text-slate-600">Sorted by points, goal difference, then goals scored</span></div>
            <div className="overflow-x-auto"><table className="w-full min-w-[960px] border-collapse text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-sm text-slate-600"><tr><th scope="col" className="px-3 py-3">#</th><th scope="col" className="px-3 py-3">Team</th><th scope="col" className="px-3 py-3">Pl</th><th scope="col" className="px-3 py-3">W</th><th scope="col" className="px-3 py-3">D</th><th scope="col" className="px-3 py-3">L</th><th scope="col" className="px-3 py-3">GF</th><th scope="col" className="px-3 py-3">GA</th><th scope="col" className="px-3 py-3">GD</th><th scope="col" className="px-3 py-3">Pts</th><th scope="col" className="px-3 py-3">Form</th><th scope="col" className="px-3 py-3">Avg xG</th></tr></thead>
              <tbody className="divide-y divide-slate-100">{data.teams.map((team, index) => <tr key={team.team_id} className="hover:bg-slate-50/70">
                <td className="px-3 py-3 font-mono tabular-nums text-slate-600">{index + 1}</td><th scope="row" className="px-3 py-3 text-left font-semibold text-slate-900">{team.team}</th><td className="px-3 py-3 font-mono tabular-nums">{team.played}</td><td className="px-3 py-3 font-mono tabular-nums">{team.won}</td><td className="px-3 py-3 font-mono tabular-nums">{team.drawn}</td><td className="px-3 py-3 font-mono tabular-nums">{team.lost}</td><td className="px-3 py-3 font-mono tabular-nums">{team.goals_for}</td><td className="px-3 py-3 font-mono tabular-nums">{team.goals_against}</td><td className="px-3 py-3 font-mono tabular-nums">{team.goal_difference > 0 ? `+${team.goal_difference}` : team.goal_difference}</td><td className="px-3 py-3 font-mono tabular-nums font-bold text-slate-900">{team.points}</td><td className="px-3 py-3" aria-label={`Recent form ${team.recent_form ? [...team.recent_form].join('-') : 'unavailable'}`}><RecentForm form={team.recent_form} /></td><td className="px-3 py-3"><span className="block font-mono tabular-nums text-slate-900">{team.avg_xg == null ? '—' : team.avg_xg.toFixed(2)}</span><span className="block text-sm text-slate-600">{team.xg_matches}/{team.played} matches</span></td>
              </tr>)}</tbody>
            </table></div>
          </section>
          <p className="text-base leading-relaxed text-slate-600">Avg xG uses only matches where the provider recorded xG; the count beside each average shows its sample size. Percentages describe this completed-match sample and are not forecasts.</p>
        </>
      )}
    </section>
  )
}
