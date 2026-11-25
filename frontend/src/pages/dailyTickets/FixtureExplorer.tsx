import { useMemo, useState, type MouseEvent } from 'react'
import { formatDate, formatKickoff, type MatchFixture } from '../../lib/api'
import { useFavoriteMatches } from './useFavoriteMatches'

type FixtureStatus = MatchFixture['status'] | 'all'
type FixtureSort = 'kickoff' | 'match' | 'league'

export function fixtureScore(fixture: MatchFixture): string | null {
  return fixture.home_goals != null && fixture.away_goals != null
    ? `${fixture.home_goals}–${fixture.away_goals}`
    : null
}

export function fixturePickLabel(picks: number): string {
  return picks === 1 ? '1 pick' : `${picks} picks`
}

export function fixtureStatusLabel(status: FixtureStatus): string {
  return ({
    all: 'All',
    live: 'In play',
    scheduled: 'Upcoming',
    finished: 'Finished',
    postponed: 'Postponed',
    cancelled: 'Cancelled',
    abandoned: 'Abandoned · review',
    awarded: 'Awarded · review',
  } as Record<FixtureStatus, string>)[status]
}

const chipBase = 'inline-flex min-h-11 items-center justify-center rounded-md px-3 py-1.5 text-sm font-medium leading-normal transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed'
const chipInactive = 'bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-900'
const chipActive = 'bg-emerald-700 text-white'

export function FixtureExplorer({ fixtures, pickCounts, onOpenPicks, countsStale = false }: {
  fixtures: MatchFixture[]
  /** Q≥75 pick count per match. `null`/omitted means the count request has not succeeded. */
  pickCounts?: Record<number, number> | null
  /** Pro/admin only. Free accounts still see the count, but not the picks. */
  onOpenPicks?: (matchId: number) => void
  /** Previous counts are visible while a count refresh is in flight or failed. */
  countsStale?: boolean
}) {
  const [query, setQuery] = useState('')
  const [league, setLeague] = useState('all')
  const [status, setStatus] = useState<FixtureStatus>('all')
  const [favoriteOnly, setFavoriteOnly] = useState(false)
  const [sort, setSort] = useState<{ key: FixtureSort; direction: 'asc' | 'desc' }>({ key: 'kickoff', direction: 'asc' })
  const [collapsedCompetitions, setCollapsedCompetitions] = useState<string[]>([])
  const { favorites, favoriteIds, toggleFavorite } = useFavoriteMatches()
  const leagues = useMemo(() => [...new Set(fixtures.map(fixture => fixture.competition))].sort(), [fixtures])
  // Status chips count the same scope as the rows, excluding the status chip
  // itself. Without this, a chip can claim picks that the other filters hide.
  const baseFixtures = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase()
    return fixtures.filter(fixture => {
      const matchesQuery = !normalized || `${fixture.home_team} ${fixture.away_team} ${fixture.competition}`.toLocaleLowerCase().includes(normalized)
      return matchesQuery && (league === 'all' || fixture.competition === league) && (!favoriteOnly || favoriteIds.has(fixture.match_id))
    })
  }, [favoriteIds, favoriteOnly, fixtures, league, query])
  const statusCounts = useMemo(() => baseFixtures.reduce<Record<FixtureStatus, number>>((counts, fixture) => {
    counts.all += 1
    counts[fixture.status] = (counts[fixture.status] ?? 0) + 1
    return counts
  }, { all: 0, live: 0, scheduled: 0, finished: 0, postponed: 0, cancelled: 0, abandoned: 0, awarded: 0 }), [baseFixtures])
  const filtered = useMemo(() => {
    const matches = baseFixtures.filter(fixture => status === 'all' || fixture.status === status)
    return matches.sort((left, right) => {
      const result = sort.key === 'kickoff'
        ? Date.parse(left.kickoff_at) - Date.parse(right.kickoff_at)
        : sort.key === 'league'
          ? left.competition.localeCompare(right.competition) || Date.parse(left.kickoff_at) - Date.parse(right.kickoff_at)
          : left.home_team.localeCompare(right.home_team) || left.away_team.localeCompare(right.away_team)
      return sort.direction === 'asc' ? result : -result
    })
  }, [baseFixtures, sort, status])
  const competitionGroups = useMemo(() => {
    const groups = new Map<string, MatchFixture[]>()
    for (const fixture of filtered) {
      const group = groups.get(fixture.competition) ?? []
      group.push(fixture)
      groups.set(fixture.competition, group)
    }
    return [...groups.entries()]
  }, [filtered])
  const changeSort = (key: FixtureSort) => setSort(current => ({
    key,
    direction: current.key === key ? (current.direction === 'asc' ? 'desc' : 'asc') : 'asc',
  }))
  const activeFilterCount = Number(Boolean(query.trim())) + Number(league !== 'all') + Number(status !== 'all') + Number(favoriteOnly)
  const activeFilterLabels = [
    query.trim() && `Search “${query.trim()}”`,
    league !== 'all' && `Competition: ${league}`,
    status !== 'all' && `Status: ${status === 'scheduled' ? 'upcoming' : status === 'live' ? 'in play' : status}`,
    favoriteOnly && 'Favourites only',
  ].filter((label): label is string => Boolean(label))
  const clearFilters = () => {
    setQuery('')
    setLeague('all')
    setStatus('all')
    setFavoriteOnly(false)
  }
  const toggleCompetition = (competition: string) => setCollapsedCompetitions(current =>
    current.includes(competition) ? current.filter(item => item !== competition) : [...current, competition],
  )

  return (
    <section className="selection-panel fixture-explorer rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden" aria-labelledby="fixture-explorer-title">
      <div className="section-heading flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3 sm:px-5">
        <div>
          <h2 id="fixture-explorer-title" className="text-base font-bold text-slate-900">Fixture list</h2>
          <span className="section-note block text-base leading-relaxed text-slate-600">Search, filter, and sort every fixture loaded for this date.</span>
        </div>
        <div className="space-y-1 text-base text-slate-600">
          <span className="section-note block"><b className="font-mono tabular-nums text-slate-900">{filtered.length}</b> of <span className="font-mono tabular-nums">{fixtures.length}</span> fixtures shown</span>
          {!pickCounts
            ? <span className="block text-sm text-slate-600" role="status">Pick counts unavailable for this refresh.</span>
            : countsStale && <span className="block text-sm text-amber-800" role="status">Pick counts may be stale; refreshing.</span>}
        </div>
      </div>
      <div className="match-toolbar fixture-toolbar space-y-3 border-b border-slate-200 bg-slate-50/70 px-4 py-3 sm:px-5">
        <div className="match-explorer-controls flex flex-col gap-3 sm:flex-row">
          <label className="match-search relative flex-1">
            <span className="sr-only">Search teams or competition</span>
            <input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Team, league or country" className="h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 placeholder:text-slate-600 focus:border-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-700" />
          </label>
          <label className="sm:w-64">
            <span className="sr-only">Filter by competition</span>
            <select value={league} onChange={event => setLeague(event.target.value)} className="h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 focus:border-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-700">
              <option value="all">All competitions</option>
              {leagues.map(item => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
        </div>
        <div className="match-sort-controls fixture-sort-controls flex flex-wrap items-center gap-1.5" aria-label="Sort fixtures">
          <span className="text-sm font-semibold uppercase tracking-wide text-slate-600">Sort</span>
          {(['kickoff', 'match', 'league'] as FixtureSort[]).map(key => (
            <button key={key} className={`${chipBase} ${sort.key === key ? chipActive : chipInactive}`} onClick={() => changeSort(key)} aria-pressed={sort.key === key}>
              {key === 'kickoff' ? 'Kickoff' : key === 'match' ? 'Match' : 'Competition'}
              {sort.key === key && <span aria-hidden="true"> {sort.direction === 'asc' ? '↑' : '↓'}</span>}
            </button>
          ))}
        </div>
        <div className="match-status-filters flex flex-wrap items-center gap-1.5" aria-label="Filter fixtures by status">
          {(['all', 'live', 'scheduled', 'finished', 'postponed', 'cancelled', 'abandoned', 'awarded'] as FixtureStatus[]).map(key => {
            const count = statusCounts[key] ?? 0
            if (key !== 'all' && count === 0 && status !== key) return null
            const label = fixtureStatusLabel(key)
            return <button key={key} className={`${chipBase} ${status === key ? chipActive : chipInactive}`} onClick={() => setStatus(key)} aria-pressed={status === key} disabled={key !== 'all' && count === 0 && status !== key}>{label} <b className="font-mono tabular-nums">{count}</b></button>
          })}
          <button className={`fixture-favorites-filter ${chipBase} ${favoriteOnly ? 'bg-amber-600 text-white hover:bg-amber-700' : chipInactive}`} onClick={() => setFavoriteOnly(current => !current)} aria-pressed={favoriteOnly} title="Favourites are saved in this browser">
            <span aria-hidden="true">★</span> Favourites <b className="font-mono tabular-nums">{favorites.length}</b>
          </button>
          <button className={`match-clear-filters ml-auto inline-flex min-h-11 items-center text-sm font-semibold text-emerald-800 underline underline-offset-2 hover:text-emerald-900 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed disabled:no-underline`} onClick={clearFilters} disabled={activeFilterCount === 0}>
            Clear filters{activeFilterCount > 0 ? ` · ${activeFilterCount}` : ''}
          </button>
        </div>
        {activeFilterLabels.length > 0 && (
          <p className="fixture-active-filters text-base leading-relaxed text-slate-600">
            <b className="font-semibold text-slate-900">Active filters ({activeFilterLabels.length}):</b> {activeFilterLabels.join(' · ')}
          </p>
        )}
      </div>
      {filtered.length === 0 ? <p className="panel-empty px-4 py-10 text-center text-base text-slate-600 sm:px-5">{favoriteOnly && favorites.length === 0 ? 'No favourites yet. Select a star beside a match to save it here.' : 'No fixtures match these filters.'}</p> : (
        <div className="fixture-list divide-y divide-slate-200">
          {competitionGroups.map(([competition, groupFixtures]) => {
            const collapsed = collapsedCompetitions.includes(competition)
            return <section className="fixture-league-group" key={competition} aria-label={competition}>
              <h3 className="fixture-league-title m-0">
                <button className="fixture-league-heading inline-flex min-h-11 w-full items-center gap-2 bg-slate-50/70 px-4 py-2.5 text-left text-sm font-semibold text-slate-700 hover:bg-slate-100 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 sm:px-5" onClick={() => toggleCompetition(competition)} aria-expanded={!collapsed}>
                  <span className="min-w-0 flex-1 truncate">{competition}</span>
                  <b className="font-mono text-sm font-semibold tabular-nums text-slate-600">{groupFixtures.length} {groupFixtures.length === 1 ? 'match' : 'matches'}</b>
                  <span className="fixture-group-chevron text-slate-600" aria-hidden="true">{collapsed ? '›' : '⌄'}</span>
                </button>
              </h3>
              {!collapsed && <div className="fixture-league-rows divide-y divide-slate-100">{groupFixtures.map(fixture => {
                const score = fixtureScore(fixture)
                const countsKnown = pickCounts != null
                const picks = pickCounts?.[fixture.match_id] ?? 0
                const picksLabel = fixturePickLabel(picks)
                const openPicks = (event: MouseEvent<HTMLButtonElement>) => {
                  event.preventDefault()
                  event.stopPropagation()
                  onOpenPicks?.(fixture.match_id)
                }
                const statusLabel = fixtureStatusLabel(fixture.status)
                const statusClass = fixture.status === 'finished' ? 'text-slate-700 bg-slate-100 border-slate-200'
                  : fixture.status === 'live' ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                  : fixture.status === 'scheduled' ? 'text-sky-700 bg-sky-50 border-sky-200'
                  : 'text-amber-800 bg-amber-50 border-amber-200'
                return (
                <div className="fixture-row-wrap flex items-stretch" key={fixture.match_id}>
                  <button
                    className={`fixture-favorite inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center px-3 text-lg transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-emerald-700 sm:px-4 ${favoriteIds.has(fixture.match_id) ? 'active text-amber-600 hover:text-amber-700' : 'text-slate-600 hover:text-amber-600'}`}
                    onClick={() => toggleFavorite(fixture.match_id)}
                    aria-label={`${favoriteIds.has(fixture.match_id) ? 'Remove' : 'Add'} ${fixture.home_team} vs ${fixture.away_team} ${favoriteIds.has(fixture.match_id) ? 'from' : 'to'} favourites`}
                    aria-pressed={favoriteIds.has(fixture.match_id)}
                    title={favoriteIds.has(fixture.match_id) ? 'Remove from favourites' : 'Add to favourites'}
                  >★</button>
                  <details className={`fixture-row group min-w-0 flex-1 ${fixture.status}`}>
                    <summary className="grid cursor-pointer list-none items-center gap-x-3 gap-y-1 px-2 py-3 pr-4 text-base hover:bg-slate-50/70 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 sm:grid-cols-[minmax(0,1fr)_auto_auto_auto_auto] sm:px-3 sm:pr-5 [&::-webkit-details-marker]:hidden">
                      <strong className="min-w-0 truncate font-semibold text-slate-900">{fixture.home_team} <span className="leg-match-vs font-normal text-slate-600">vs</span> {fixture.away_team}</strong>
                      <span className={`summary-match-status inline-flex w-fit items-center rounded-full border px-2 py-0.5 text-sm font-semibold ${statusClass} ${fixture.status}`}>{statusLabel}</span>
                      {countsKnown && picks > 0 && onOpenPicks
                        ? <button
                            type="button"
                            className="fixture-picks has-picks inline-flex min-h-11 items-center rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-sm font-semibold text-emerald-700 hover:bg-emerald-100 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
                            onClick={openPicks}
                            title={`Open the ${picksLabel} Q≥75 system picks for this fixture`}
                            aria-label={`Open ${picksLabel} for ${fixture.home_team} vs ${fixture.away_team}`}
                          >{picksLabel}</button>
                        : <span
                            className={`fixture-picks inline-flex items-center rounded-full border px-2 py-0.5 text-sm font-semibold ${!countsKnown ? 'empty border-slate-200 bg-slate-50 text-slate-600' : picks > 0 ? 'has-picks border-emerald-200 bg-emerald-50 text-emerald-700' : 'empty border-slate-200 bg-slate-50 text-slate-600'}`}
                            title={!countsKnown ? 'Pick counts unavailable for this refresh' : picks > 0 ? `${picksLabel} · open with Pro` : 'No Q≥75 system picks'}
                            aria-label={!countsKnown ? 'Pick count unavailable' : undefined}
                          >{countsKnown && picks > 0 ? picksLabel : '—'}</span>}
                      <span
                        className={`fixture-score font-mono text-sm font-semibold tabular-nums ${score ? 'text-slate-900' : 'empty text-slate-600'}`}
                        aria-label={score ? `Result ${score}` : 'Result not available'}
                      >{score ?? '—'}</span>
                      <span className="fixture-kickoff kickoff-time font-mono text-sm tabular-nums text-slate-600">{formatKickoff(fixture.kickoff_at)}</span>
                    </summary>
                    <div className="fixture-drilldown grid gap-3 border-t border-slate-100 bg-slate-50/50 px-4 py-3 text-base leading-relaxed sm:grid-cols-2 lg:grid-cols-4 sm:px-5">
                      <span className="flex flex-col gap-0.5"><small className="text-sm font-semibold uppercase tracking-wide text-slate-600">Competition</small><b className="font-medium text-slate-900">{fixture.competition}</b></span>
                      <span className="flex flex-col gap-0.5"><small className="text-sm font-semibold uppercase tracking-wide text-slate-600">Kickoff</small><b className="font-medium text-slate-900"><span className="event-date">{formatDate(fixture.kickoff_at)}</span> <span className="kickoff-time font-mono tabular-nums">{formatKickoff(fixture.kickoff_at)}</span></b></span>
                      <span className="flex flex-col gap-0.5"><small className="text-sm font-semibold uppercase tracking-wide text-slate-600">Status</small><b className="font-medium text-slate-900">{fixture.status === 'live' && fixture.elapsed_minutes != null ? `In play · ${fixture.elapsed_minutes}'` : fixture.status === 'live' && fixture.live_phase ? `In play · ${fixture.live_phase}` : fixtureStatusLabel(fixture.status)}</b></span>
                      {score && <span className="flex flex-col gap-0.5"><small className="text-sm font-semibold uppercase tracking-wide text-slate-600">Result</small><b className="font-mono font-semibold tabular-nums text-slate-900">{score}</b></span>}
                      <span className="fixture-pro-note col-span-full text-base leading-relaxed text-slate-600">Market selections and model analysis are available with Pro.</span>
                    </div>
                  </details>
                </div>
                )
              })}</div>}
            </section>
          })}
        </div>
      )}
    </section>
  )
}
