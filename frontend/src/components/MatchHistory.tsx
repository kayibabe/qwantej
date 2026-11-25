import { useEffect, useMemo, useState } from 'react'
import { formatMarket, formatSelection, formatTicketType, selectionRepeatsMarket, selectionTone, ticketTierBadgeClass } from '../lib/api'
import { groupMatchHistory, type MatchHistoryRow } from '../lib/trackerGrouping'

const livePhaseLabels: Record<string, string> = { '1st_half': '1st Half', half_time: 'Half Time', '2nd_half': '2nd Half', extra_time: 'Extra Time', penalties: 'Penalties', suspended: 'Suspended', interrupted: 'Interrupted', live: 'Live' }
const toneClass = (tone: string) => tone === 'home' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : tone === 'away' ? 'border-sky-200 bg-sky-50 text-sky-700' : tone === 'draw' ? 'border-amber-200 bg-amber-50 text-amber-700' : 'border-slate-200 bg-slate-50 text-slate-600'
const resultClass = (result: string) => result === 'won' ? 'text-emerald-700' : result === 'lost' ? 'text-red-600' : result === 'void' ? 'text-amber-700' : 'text-slate-600'
const statusText = (result: string) => result.charAt(0).toUpperCase() + result.slice(1)

export default function MatchHistory({ isInternal }: { isInternal: boolean }) {
  const [rows, setRows] = useState<MatchHistoryRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [outcome, setOutcome] = useState('all')
  const [market, setMarket] = useState('all')
  const [selection, setSelection] = useState('all')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  useEffect(() => {
    fetch('/api/v1/tickets/matches/history')
      .then(async response => {
        if (!response.ok) throw new Error(`Match history failed (${response.status})`)
        return response.json()
      })
      .then(setRows)
      .catch((reason: Error) => setError(reason.message || 'Match history unavailable'))
      .finally(() => setLoading(false))
  }, [])

  const markets = useMemo(() => [...new Set(rows.flatMap(row => row.selection_evidence.map(item => item.market)))].sort(), [rows])
  const selections = useMemo(() => [...new Set(rows.flatMap(row => row.selection_evidence.map(item => item.selection)))].sort(), [rows])
  const visible = useMemo(() => rows.filter(row =>
    (outcome === 'all' || (row.outcome ?? 'pending') === outcome)
    && (market === 'all' || row.selection_evidence.some(item => item.market === market))
    && (selection === 'all' || row.selection_evidence.some(item => item.selection === selection))
    && (!dateFrom || row.target_date >= dateFrom)
    && (!dateTo || row.target_date <= dateTo)
  ), [rows, outcome, market, selection, dateFrom, dateTo])
  const groups = useMemo(() => groupMatchHistory(visible), [visible])
  const hasDateFilter = Boolean(dateFrom || dateTo)

  if (loading) return <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600" aria-busy="true">Loading published match evidence…</div>
  if (error) return <div className="rounded-xl border border-slate-200 bg-white p-8 sm:p-12 text-center space-y-2"><strong className="block text-slate-900">Match history unavailable</strong><span className="text-sm text-slate-600">{error}</span></div>
  if (!rows.length) return <div className="rounded-xl border border-slate-200 bg-white p-8 sm:p-12 text-center space-y-2"><strong className="block text-slate-900">No published match history</strong><span className="text-sm text-slate-600">Matches will appear after tickets are published.</span></div>

  const inputClass = 'h-11 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-700/20 focus:border-emerald-700'
  const labelClass = 'flex flex-col gap-1 text-sm font-medium uppercase tracking-wide text-slate-600'

  return <>
    <div className="flex flex-wrap items-end justify-between gap-4 rounded-xl border border-slate-200 bg-white px-4 py-4">
      <div><span className="text-sm font-semibold uppercase tracking-wide text-slate-600">Selection-level audit</span><strong className="mt-1 block text-lg font-bold tracking-tight text-slate-900">Published match evidence</strong><p className="mt-1 text-base text-slate-600">Market describes the model category; pick describes the exact selection that was published.</p></div>
      <span className="text-sm font-medium text-slate-600 font-mono tabular-nums">{visible.length} of {rows.length} matches</span>
    </div>
    <div className="mt-4 flex flex-wrap gap-3 rounded-xl border border-slate-200 bg-white p-4">
      {isInternal && <>
        <label className={labelClass}>Outcome<select className={inputClass} value={outcome} onChange={event => setOutcome(event.target.value)}><option value="all">All outcomes</option><option value="won">Won</option><option value="lost">Lost</option><option value="void">Void</option><option value="pending">Pending</option><option value="mixed">Mixed</option></select></label>
        <label className={labelClass}>Market<select className={inputClass} value={market} onChange={event => setMarket(event.target.value)}><option value="all">All markets</option>{markets.map(value => <option key={value} value={value}>{formatMarket(value)}</option>)}</select></label>
        <label className={labelClass}>Pick<select className={inputClass} value={selection} onChange={event => setSelection(event.target.value)}><option value="all">All picks</option>{selections.map(value => <option key={value} value={value}>{formatSelection(value)}</option>)}</select></label>
      </>}
      <label className={labelClass}>From<input className={inputClass} type="date" value={dateFrom} onChange={event => setDateFrom(event.target.value)} /></label>
      <label className={labelClass}>To<input className={inputClass} type="date" value={dateTo} onChange={event => setDateTo(event.target.value)} /></label>
    </div>

    {!visible.length ? <div className="mt-4 rounded-xl border border-slate-200 bg-white p-8 sm:p-12 text-center space-y-2"><strong className="block text-slate-900">{isInternal ? 'No matches meet these filters' : hasDateFilter ? 'No matches in this date range' : 'No published match history'}</strong><span className="text-sm text-slate-600">{isInternal ? 'Try another outcome, market, pick or date range.' : hasDateFilter ? 'Try a different from/to date range.' : 'Published match evidence will appear here once available.'}</span></div> : <div className="mt-4 space-y-6">{groups.map(year => <section key={year.year} className="space-y-4">
      <h2 className="text-sm font-bold uppercase tracking-wide text-slate-600">{year.year}</h2>
      {year.months.map(month => <section key={`${year.year}-${month.label}`} className="space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-600">{month.label}</h3>
        {month.matchesByDate.map(group => <section key={group.date} className="rounded-xl border border-slate-200 bg-white overflow-hidden">
          <div className="flex items-center justify-between gap-2 border-b border-slate-200 bg-slate-50/70 px-4 py-3"><strong className="text-sm font-semibold text-slate-900">{group.label}</strong><span className="text-sm text-slate-600 font-mono tabular-nums">{group.matches.length} match{group.matches.length === 1 ? '' : 'es'}</span></div>
          <div className="divide-y divide-slate-100">{group.matches.map(match => <article className="grid gap-4 px-4 py-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1.5fr)_auto]" key={match.match_id}>
            <div><strong className="block text-sm font-semibold text-slate-900">{match.home_team} <span className="text-slate-600">vs</span> {match.away_team}</strong><small className={`mt-1 block text-sm ${match.live_phase ? 'font-semibold text-emerald-700' : 'text-slate-600'}`}>{match.live_phase ? `${livePhaseLabels[match.live_phase] ?? 'Live'}${match.elapsed_minutes != null ? ` · ${match.elapsed_minutes}'` : ''}` : 'Kickoff · '}{new Date(match.kickoff_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</small><small className="mt-0.5 block text-sm text-slate-600">{match.competition}</small></div>
            <div className="space-y-2"><span className="flex flex-wrap gap-1.5">{match.ticket_types.map(type => <span className={`inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-sm font-semibold text-slate-600 ${ticketTierBadgeClass(type)}`} key={type}>{formatTicketType(type)}</span>)}</span><small className="flex flex-wrap gap-1.5">{match.selections.map(value => <b className={`inline-flex items-center rounded-full border px-2 py-0.5 text-sm font-semibold ${toneClass(selectionTone(value))}`} key={value}>{formatSelection(value)}</b>)}</small></div>
            <div className="space-y-2"><span className="text-sm font-semibold uppercase tracking-wide text-slate-600">Projected advisory</span>{match.selection_evidence.map(item => <div key={`${item.market}:${item.selection}`} className="rounded-lg border border-slate-200 bg-slate-50/70 p-3">
              <strong className="flex flex-wrap items-center gap-1.5 text-sm font-medium text-slate-700">{!selectionRepeatsMarket(item.market, item.selection) && <span>{formatMarket(item.market)}</span>} <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-sm font-semibold ${toneClass(selectionTone(item.selection))}`}>{formatSelection(item.selection)}</span> <b className="font-mono text-sm font-semibold tabular-nums text-slate-600">Odds {item.odds == null ? '—' : item.odds.toFixed(2)}</b></strong>
              <span className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-sm text-slate-600"><b className="font-mono font-semibold tabular-nums text-slate-700">Q {item.q_score.toFixed(1)}</b><b className="font-mono font-semibold tabular-nums text-slate-700">{(item.model_probability * 100).toFixed(1)}% model</b><b className="font-mono font-semibold tabular-nums text-slate-700">{item.model_spread == null ? '—' : `${(item.model_spread * 100).toFixed(1)} pp`} spread</b><b className={`font-mono font-semibold tabular-nums ${item.edge != null && item.edge > 0 ? 'text-emerald-700' : 'text-slate-600'}`}>{item.edge == null ? '—' : `${(item.edge * 100).toFixed(1)}%`} edge</b></span>
              <small className={`mt-1 block text-sm font-semibold uppercase tracking-wide ${resultClass(item.result)}`}>{statusText(item.result)}</small>
            </div>)}</div>
            <div className="text-right"><div className="font-mono text-lg font-bold tabular-nums text-slate-900">{match.home_goals == null ? '—' : `${match.home_goals} - ${match.away_goals}`}</div><small className={`mt-1 block text-sm font-semibold uppercase tracking-wide ${resultClass(match.outcome ?? 'pending')}`}>{statusText(match.outcome ?? 'pending')}</small></div>
          </article>)}</div>
        </section>)}
      </section>)}
    </section>)}</div>}
  </>
}
