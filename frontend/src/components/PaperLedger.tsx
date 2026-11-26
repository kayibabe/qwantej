import { useEffect, useMemo, useState } from 'react'
import { fetchTicket, fetchTicketHistory, formatDate, formatKickoff, formatMarket, formatResult, formatSelection, formatTicketType, type Ticket, type TicketHistoryItem } from '../lib/api'
import GradeBadge from './GradeBadge'
import { fmtPnl } from '../utils/currency'
import { localDateString } from '../pages/dailyTickets/helpers'

interface TrackerMeta {
  current_model_version: string
  observation_only?: { ticket_types?: string[] }
}

const pct = (value: number) => `${(value * 100).toFixed(1)}%`
const cohortKey = (row: TicketHistoryItem) => `${row.target_date}:${row.ticket_type}`

export function latestTicketCohorts(rows: TicketHistoryItem[]) {
  const latest = new Map<string, TicketHistoryItem>()
  for (const row of rows) {
    const key = cohortKey(row)
    const current = latest.get(key)
    if (!current || row.version > current.version || (row.version === current.version && row.ticket_id > current.ticket_id)) latest.set(key, row)
  }
  return [...latest.values()].sort((a, b) => b.target_date.localeCompare(a.target_date) || a.ticket_type.localeCompare(b.ticket_type))
}

export default function PaperLedger({ isInternal, onOpenValidation }: { isInternal: boolean; onOpenValidation?: () => void }) {
  const [allVersions, setAllVersions] = useState<TicketHistoryItem[]>([])
  const [trackerMeta, setTrackerMeta] = useState<TrackerMeta | null>(null)
  const [observationTiers, setObservationTiers] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')
  const [resultFilter, setResultFilter] = useState('all')
  const [modelFilter, setModelFilter] = useState('current')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [ticket, setTicket] = useState<Ticket | null>(null)
  const [compareTicket, setCompareTicket] = useState<Ticket | null>(null)
  const [selectedVersion, setSelectedVersion] = useState<TicketHistoryItem | null>(null)
  const [ticketLoading, setTicketLoading] = useState(false)
  const today = localDateString()
  const hasDateFilter = Boolean(dateFrom || dateTo)
  useEffect(() => {
    Promise.all([
      fetchTicketHistory(true),
      fetch('/api/v1/tickets/tracker-meta').then(async response => {
        if (!response.ok) throw new Error(`Tracker settings failed (${response.status})`)
        return response.json() as Promise<TrackerMeta>
      }).catch(() => null),
    ]).then(([history, meta]) => {
      setAllVersions(history.filter(row => row.ticket_type !== 'high_odds'))
      setTrackerMeta(meta)
      setObservationTiers(new Set(meta?.observation_only?.ticket_types ?? []))
    })
      .catch((reason: Error) => setError(reason.message || 'Paper portfolio unavailable'))
      .finally(() => setLoading(false))
  }, [])

  const latestRows = useMemo(() => latestTicketCohorts(allVersions), [allVersions])
  const modelVersions = useMemo(() => [...new Set(latestRows.map(row => row.model_version))].sort().reverse(), [latestRows])
  const currentModel = trackerMeta?.current_model_version ?? modelVersions[0]
  const scopeRows = useMemo(() => latestRows.filter(row =>
    (modelFilter === 'all' || row.model_version === (modelFilter === 'current' ? currentModel : modelFilter))
    && (!dateFrom || row.target_date >= dateFrom) && (!dateTo || row.target_date <= dateTo)
  ), [latestRows, modelFilter, currentModel, dateFrom, dateTo])
  const filtered = useMemo(() => scopeRows.filter(row =>
    (typeFilter === 'all' || row.ticket_type === typeFilter)
    && (resultFilter === 'all' || (row.result ?? 'pending') === resultFilter)
  ), [scopeRows, typeFilter, resultFilter])
  const summaryRows = useMemo(
    () => typeFilter === 'all' ? filtered.filter(row => !observationTiers.has(row.ticket_type)) : filtered,
    [filtered, typeFilter, observationTiers],
  )
  const settledRows = summaryRows.filter(row => row.result === 'won' || row.result === 'lost' || row.result === 'void')
  const settledPnl = settledRows.reduce((total, row) => total + (row.profit_loss ?? 0), 0)
  const wonCount = settledRows.filter(row => row.result === 'won').length
  const lostCount = settledRows.filter(row => row.result === 'lost').length
  const decidedCount = wonCount + lostCount
  const hitRate = decidedCount > 0 ? wonCount / decidedCount : null
  const settledStake = settledRows.reduce((total, row) => total + (row.stake ?? 0), 0)
  const roi = settledRows.length > 0 && settledRows.every(row => row.stake != null) && settledStake > 0
    ? settledPnl / settledStake
    : null
  const publishedBeforeKickoff = summaryRows.filter(row => row.publication_timing === 'pre_kickoff').length
  const hasObservationRows = scopeRows.some(row => observationTiers.has(row.ticket_type))

  const groupedRows = useMemo(() => {
    const years = new Map<string, Map<string, Map<string, TicketHistoryItem[]>>>()
    for (const row of filtered) {
      const [year, month, day] = row.target_date.split('-')
      if (!year || !month || !day) continue
      const months = years.get(year) ?? new Map<string, Map<string, TicketHistoryItem[]>>()
      const dates = months.get(month) ?? new Map<string, TicketHistoryItem[]>()
      dates.set(day, [...(dates.get(day) ?? []), row])
      months.set(month, dates)
      years.set(year, months)
    }
    return [...years.entries()].sort(([a], [b]) => b.localeCompare(a)).map(([year, months]) => {
      const monthGroups = [...months.entries()].sort(([a], [b]) => b.localeCompare(a)).map(([month, dates]) => {
        const dateGroups = [...dates.entries()].sort(([a], [b]) => b.localeCompare(a)).map(([day, rows]) => {
          const date = `${year}-${month}-${day}`
          return { date, label: new Date(`${date}T00:00:00`).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'short' }), rows }
        })
        return { month, monthLabel: new Date(`${year}-${month}-01T00:00:00`).toLocaleDateString(undefined, { month: 'long' }), dates: dateGroups }
      })
      return { year, months: monthGroups }
    })
  }, [filtered])

  async function loadVersion(row: TicketHistoryItem) {
    setSelectedVersion(row); setTicket(null); setCompareTicket(null); setTicketLoading(true)
    try {
      const versions = allVersions.filter(item => cohortKey(item) === cohortKey(row))
      const previous = versions.find(item => item.version === row.version - 1)
      const [active, comparison] = await Promise.all([fetchTicket(row.ticket_id), previous ? fetchTicket(previous.ticket_id) : Promise.resolve(null)])
      setTicket(active); setCompareTicket(comparison)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Ticket version unavailable')
    } finally { setTicketLoading(false) }
  }

  async function toggleTicket(row: TicketHistoryItem) {
    if (expandedId === row.ticket_id) { setExpandedId(null); setTicket(null); setCompareTicket(null); setSelectedVersion(null); return }
    setExpandedId(row.ticket_id); await loadVersion(row)
  }

  if (loading) return <div className="rounded-xl border border-slate-200 bg-white p-6 text-base text-slate-600" aria-busy="true">Loading immutable paper portfolio…</div>
  if (error && !allVersions.length) return <div className="rounded-xl border border-slate-200 bg-white p-8 sm:p-12 text-center space-y-2"><strong className="block text-slate-900">Paper portfolio unavailable</strong><span className="text-base text-slate-600">{error}</span></div>

  const inputClass = 'h-11 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-700/20 focus:border-emerald-700'
  const labelClass = 'flex flex-col gap-1 text-sm font-medium text-slate-600'
  const resultTone = (result?: string | null) => result === 'won' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : result === 'lost' ? 'border-red-200 bg-red-50 text-red-700' : result === 'void' ? 'border-amber-200 bg-amber-50 text-amber-700' : 'border-slate-200 bg-slate-50 text-slate-600'

  return <>
    {error && <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{error}</div>}
    <div className="flex flex-wrap items-end justify-between gap-4 rounded-xl border border-slate-200 bg-white px-4 py-4">
      <div><span className="text-sm font-semibold text-slate-600">Track · paper history</span><strong className="mt-1 block text-lg font-bold tracking-tight text-slate-900">Published ticket history</strong><p className="mt-1 text-base text-slate-600">Expand a cohort to inspect its saved versions, outcomes and publication provenance.</p></div>
      {isInternal && onOpenValidation && <button className="inline-flex min-h-11 items-center gap-1.5 px-3 py-2 text-sm font-semibold text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 rounded-lg transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={onOpenValidation}>Open validation</button>}
    </div>
    <div className="mt-4 flex flex-wrap gap-3 rounded-xl border border-slate-200 bg-white p-4" aria-label="Ledger filters">
      {isInternal && <>
        <label className={labelClass}>Tier<select aria-label="Ticket type filter" className={inputClass} value={typeFilter} onChange={event => setTypeFilter(event.target.value)}><option value="all">Portfolio tiers</option>{['safe', 'balanced'].map(value => <option key={value} value={value}>{observationTiers.has(value) ? `${formatTicketType(value)} (observation only)` : formatTicketType(value)}</option>)}</select></label>
        <label className={labelClass}>Outcome<select aria-label="Settlement filter" className={inputClass} value={resultFilter} onChange={event => setResultFilter(event.target.value)}><option value="all">All outcomes</option><option value="pending">Pending</option><option value="won">Won</option><option value="lost">Lost</option><option value="void">Void</option></select></label>
        <label className={labelClass}>Model<select aria-label="Model version filter" className={inputClass} value={modelFilter} onChange={event => setModelFilter(event.target.value)}><option value="current">Current · {currentModel ?? 'loading'}</option><option value="all">All model versions</option>{modelVersions.filter(version => version !== currentModel).map(version => <option key={version} value={version}>{version}</option>)}</select></label>
      </>}
      <label className={labelClass}>From<input aria-label="Tickets from date" className={inputClass} type="date" value={dateFrom} onChange={event => setDateFrom(event.target.value)} /></label>
      <label className={labelClass}>To<input aria-label="Tickets to date" className={inputClass} type="date" value={dateTo} onChange={event => setDateTo(event.target.value)} /></label>
    </div>

    {isInternal && hasObservationRows && typeFilter === 'all' && <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800" role="note">Balanced is an administrator-only observation cohort: its rows remain visible below, but are excluded from the portfolio P&amp;L, ROI, hit rate and stake summary until it is restored. Select the Balanced tier to inspect its standalone record.</div>}
    <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-6" aria-label="Current ledger summary">
      {[
        ['Latest ticket cohorts (after current filters)', String(filtered.length), 'text-slate-900'],
        ['Settled (win, lost, or void)', String(settledRows.length), 'text-slate-900'],
        ['Hit rate (wins / decided tickets)', hitRate == null ? '—' : `${(hitRate * 100).toFixed(1)}%`, 'text-slate-900'],
        ['Paper P&L (latest settled cohorts only)', fmtPnl(settledPnl), settledPnl >= 0 ? 'text-emerald-700' : 'text-red-600'],
        ['ROI (paper P&L / settled stake)', roi == null ? '—' : `${roi >= 0 ? '+' : ''}${(roi * 100).toFixed(2)}%`, roi == null || roi >= 0 ? 'text-emerald-700' : 'text-red-600'],
        ['Published before kickoff (unknown timing is not counted)', String(publishedBeforeKickoff), 'text-slate-900'],
      ].map(([label, value, tone]) => <div key={label} className="rounded-xl border border-slate-200 bg-white p-4"><span className="block text-sm font-medium text-slate-600">{label}</span><strong className={`mt-1 block font-mono text-xl font-bold tabular-nums ${tone}`}>{value}</strong></div>)}
    </div>

    {filtered.length === 0 ? <div className="mt-4 rounded-xl border border-slate-200 bg-white p-8 sm:p-12 text-center space-y-2"><strong className="block text-slate-900">{isInternal ? 'No tickets match these filters' : hasDateFilter ? 'No tickets in this date range' : 'No published ticket history'}</strong><span className="text-base text-slate-600">{isInternal ? 'Try another tier, outcome, model version or date range.' : hasDateFilter ? 'Try a different from/to date range.' : 'Published paper tickets will appear here once available.'}</span></div> : <div className="mt-4 space-y-4">{groupedRows.map(yearGroup => <details className="rounded-xl border border-slate-200 bg-white overflow-hidden" key={yearGroup.year} open={yearGroup.year === today.slice(0, 4) && filtered.some(row => row.target_date === today)}>
      <summary className="flex min-h-11 cursor-pointer items-center px-4 py-3 text-sm font-bold text-slate-600 bg-slate-50/70 border-b border-slate-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">{yearGroup.year}</summary>
      <div className="p-4 space-y-3">{yearGroup.months.map(monthGroup => <details className="rounded-lg border border-slate-200 overflow-hidden" key={`${yearGroup.year}-${monthGroup.month}`} open={monthGroup.month === today.slice(5, 7) && filtered.some(row => row.target_date === today)}>
        <summary className="flex min-h-11 cursor-pointer items-center px-4 py-2 text-sm font-semibold text-slate-600 bg-slate-50/50 border-b border-slate-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">{monthGroup.monthLabel}</summary>
        <div className="p-3 space-y-3">{monthGroup.dates.map(dayGroup => <details className="rounded-lg border border-slate-200 overflow-hidden" key={dayGroup.date} open={dayGroup.date === today}>
          <summary className="flex min-h-11 cursor-pointer items-center justify-between gap-2 px-4 py-2 text-sm bg-white border-b border-slate-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"><strong className="font-semibold text-slate-900">{dayGroup.label}</strong><span className="text-sm text-slate-600 font-mono tabular-nums">{dayGroup.rows.length} latest cohort{dayGroup.rows.length === 1 ? '' : 's'}</span></summary>
          <div className="divide-y divide-slate-100">
          {dayGroup.rows.map(row => {
        const versions = allVersions.filter(item => cohortKey(item) === cohortKey(row)).sort((a, b) => b.version - a.version)
        return <article key={row.ticket_id} className={expandedId === row.ticket_id ? 'bg-slate-50/30' : ''}>
          <button className="grid w-full min-h-11 gap-3 px-4 py-3 text-left transition-colors hover:bg-slate-50/70 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-emerald-700 sm:grid-cols-[minmax(0,1.3fr)_repeat(4,minmax(0,0.7fr))_minmax(0,1fr)_auto]" onClick={() => toggleTicket(row)} aria-expanded={expandedId === row.ticket_id} aria-controls={`ticket-version-${row.ticket_id}`} aria-label={`${row.name} ticket for ${dayGroup.label}`}>
            <div className="min-w-0"><span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-sm font-semibold ${row.ticket_type === 'safe' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : row.ticket_type === 'balanced' ? 'border-sky-200 bg-sky-50 text-sky-700' : 'border-slate-200 bg-slate-50 text-slate-600'}`}>{row.name}</span><small className="mt-1 block text-sm text-slate-600">latest v{row.version} · model {row.model_version}{row.internal_only ? ' · internal' : ''}</small></div>
            <div><span className="block text-sm text-slate-600">Odds</span><strong className="font-mono text-sm tabular-nums text-slate-900">{row.combined_odds == null ? '—' : `${row.combined_odds.toFixed(2)}×`}</strong></div>
            <div><span className="block text-sm text-slate-600">Legs</span><strong className="font-mono text-sm tabular-nums text-slate-900">{row.leg_count}</strong></div>
            <div><span className="block text-sm text-slate-600">Adjusted P</span><strong className="font-mono text-sm tabular-nums text-slate-900">{pct(row.adjusted_probability)}</strong></div>
            <div><span className="block text-sm text-slate-600">Risk</span><strong className="font-mono text-sm tabular-nums text-slate-900">{row.risk_score == null ? '—' : `${row.risk_score.toFixed(0)}/100`}</strong></div>
            <div><span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-sm font-semibold ${resultTone(row.result)}`}>{formatResult(row.result)}</span>{row.profit_loss != null && <strong className={`ml-2 font-mono text-sm tabular-nums ${row.profit_loss >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>{fmtPnl(row.profit_loss)}</strong>}</div>
            <span className="self-center text-slate-600" aria-hidden="true">{expandedId === row.ticket_id ? '⌃' : '⌄'}</span>
          </button>
          {expandedId === row.ticket_id && <div id={`ticket-version-${row.ticket_id}`} className="border-t border-slate-200 px-4 py-4 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3"><div><strong className="block text-sm font-semibold text-slate-900">Immutable versions</strong><span className="text-base text-slate-600">Select a version to inspect and compare with its predecessor.</span></div><div className="flex flex-wrap gap-1.5">{versions.map(version => <button key={version.ticket_id} className={`inline-flex min-h-11 min-w-11 items-center justify-center rounded-md px-3 py-2 text-sm font-semibold transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 ${selectedVersion?.ticket_id === version.ticket_id ? 'bg-emerald-700 text-white' : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'}`} onClick={() => loadVersion(version)}>v{version.version}</button>)}</div></div>
            {ticketLoading && <div className="text-base text-slate-600"><span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-700 align-middle mr-2" />Loading published selections…</div>}
            {ticket && <><ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">{ticket.legs.map(leg => <li key={leg.selection_id} className="flex flex-wrap items-start justify-between gap-3 px-4 py-3"><div><strong className="block text-sm font-semibold text-slate-900">{leg.home_team} <span className="font-normal text-slate-600">vs</span> {leg.away_team}</strong><small className="mt-1 block text-sm text-slate-600"><span className="font-mono tabular-nums">{formatDate(leg.kickoff_at)}</span> · <span className="font-mono tabular-nums">{formatKickoff(leg.kickoff_at)}</span></small><b className="mt-1 inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-sm font-semibold text-slate-600">{leg.market.startsWith('double_chance_') ? formatSelection(leg.selection) : formatMarket(leg.market)}</b></div><div className="text-right"><strong className="block font-mono text-sm tabular-nums text-slate-900">{leg.best_odds == null ? '—' : leg.best_odds.toFixed(2)}</strong><small className="mt-1 block text-sm text-slate-600">Q {leg.q_score == null ? '—' : leg.q_score.toFixed(1)} · {leg.q_grade && <GradeBadge grade={leg.q_grade} />} · {leg.home_goals != null && leg.away_goals != null && <><b className="font-mono font-semibold tabular-nums text-slate-900">{leg.home_goals}–{leg.away_goals}</b> · </>}<b className={`font-semibold ${leg.result === 'won' ? 'text-emerald-700' : leg.result === 'lost' ? 'text-red-600' : leg.result === 'void' ? 'text-amber-700' : 'text-slate-600'}`}>{formatResult(leg.result)}</b></small></div></li>)}</ul><div className="flex flex-wrap gap-3 text-base text-slate-600"><code className="font-mono" title={ticket.publication_hash}>Hash {ticket.publication_hash}</code><span>Published {new Date(ticket.published_at).toLocaleString()}</span></div>{compareTicket ? <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-base leading-relaxed text-slate-700"><strong>Compared with v{compareTicket.version}:</strong> {ticket.legs.filter(a => !compareTicket.legs.some(b => b.match_id === a.match_id && b.market === a.market && b.selection === a.selection)).length} added · {compareTicket.legs.filter(a => !ticket.legs.some(b => b.match_id === a.match_id && b.market === a.market && b.selection === a.selection)).length} removed</div> : <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-base leading-relaxed text-slate-700"><strong>Original publication:</strong> no predecessor exists for this cohort.</div>}</>}
          </div>}
        </article>
          })}
          </div>
        </details>)}</div>
      </details>)}</div>
    </details>)}</div>}
  </>
}
