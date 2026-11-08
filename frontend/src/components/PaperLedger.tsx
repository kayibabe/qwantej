import { useEffect, useMemo, useState } from 'react'
import { fetchTicket, fetchTicketHistory, formatDate, formatKickoff, formatMarket, formatSelection, formatTicketType, type Ticket, type TicketHistoryItem } from '../lib/api'
import GradeBadge from './GradeBadge'
import { fmtPnl } from '../utils/currency'
import { localDateString } from '../pages/dailyTickets/helpers'

interface PerformanceSummary { current_model_version: string }

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

export default function PaperLedger({ onOpenValidation }: { onOpenValidation?: () => void }) {
  const [allVersions, setAllVersions] = useState<TicketHistoryItem[]>([])
  const [performance, setPerformance] = useState<PerformanceSummary | null>(null)
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
  useEffect(() => {
    Promise.all([
      fetchTicketHistory(true),
      fetch('/api/v1/performance/summary').then(async response => {
        if (!response.ok) throw new Error(`Performance summary failed (${response.status})`)
        return response.json()
      }),
    ]).then(([history, summary]) => {
      setAllVersions(history.filter(row => row.ticket_type !== 'high_odds'))
      setPerformance(summary)
    })
      .catch((reason: Error) => setError(reason.message || 'Paper portfolio unavailable'))
      .finally(() => setLoading(false))
  }, [])

  const latestRows = useMemo(() => latestTicketCohorts(allVersions), [allVersions])
  const modelVersions = useMemo(() => [...new Set(latestRows.map(row => row.model_version))].sort().reverse(), [latestRows])
  const currentModel = performance?.current_model_version
  const scopeRows = useMemo(() => latestRows.filter(row =>
    (modelFilter === 'all' || row.model_version === (modelFilter === 'current' ? currentModel : modelFilter))
    && (!dateFrom || row.target_date >= dateFrom) && (!dateTo || row.target_date <= dateTo)
  ), [latestRows, modelFilter, currentModel, dateFrom, dateTo])
  const filtered = useMemo(() => scopeRows.filter(row =>
    (typeFilter === 'all' || row.ticket_type === typeFilter)
    && (resultFilter === 'all' || (row.result ?? 'pending') === resultFilter)
  ), [scopeRows, typeFilter, resultFilter])
  const settledRows = filtered.filter(row => row.result === 'won' || row.result === 'lost' || row.result === 'void')
  const settledPnl = settledRows.reduce((total, row) => total + (row.profit_loss ?? 0), 0)
  const wonCount = settledRows.filter(row => row.result === 'won').length
  const lostCount = settledRows.filter(row => row.result === 'lost').length
  const decidedCount = wonCount + lostCount
  const hitRate = decidedCount > 0 ? wonCount / decidedCount : null
  const settledStake = settledRows.reduce((total, row) => total + (row.stake ?? 0), 0)
  const roi = settledRows.length > 0 && settledRows.every(row => row.stake != null) && settledStake > 0
    ? settledPnl / settledStake
    : null
  const publishedBeforeKickoff = filtered.filter(row => row.publication_timing === 'pre_kickoff').length

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

  if (loading) return <div className="paper-ledger-skeleton" aria-busy="true">Loading immutable paper portfolio…</div>
  if (error && !allVersions.length) return <div className="analytics-empty"><strong>Paper portfolio unavailable</strong><span>{error}</span></div>

  return <>
    {error && <div className="tracker-message error" role="alert">{error}</div>}
    <div className="paper-scope-heading paper-ledger-heading">
      <div><span className="eyebrow">Track · paper history</span><strong>Published ticket history</strong><p>Expand a cohort to inspect its saved versions, outcomes and publication provenance.</p></div>
      {onOpenValidation && <button className="btn-ghost btn-sm" onClick={onOpenValidation}>Open validation</button>}
    </div>
    <div className="paper-ledger-filters" aria-label="Ledger filters">
      <label>Tier<select aria-label="Ticket type filter" value={typeFilter} onChange={event => setTypeFilter(event.target.value)}><option value="all">All tiers</option>{['safe', 'balanced'].map(value => <option key={value} value={value}>{formatTicketType(value)}</option>)}</select></label>
      <label>Outcome<select aria-label="Settlement filter" value={resultFilter} onChange={event => setResultFilter(event.target.value)}><option value="all">All outcomes</option><option value="pending">Pending</option><option value="won">Won</option><option value="lost">Lost</option><option value="void">Void</option></select></label>
      <label>Model<select aria-label="Model version filter" value={modelFilter} onChange={event => setModelFilter(event.target.value)}><option value="current">Current · {currentModel ?? 'loading'}</option><option value="all">All model versions</option>{modelVersions.filter(version => version !== currentModel).map(version => <option key={version} value={version}>{version}</option>)}</select></label>
      <label>From<input aria-label="Tickets from date" type="date" value={dateFrom} onChange={event => setDateFrom(event.target.value)} /></label>
      <label>To<input aria-label="Tickets to date" type="date" value={dateTo} onChange={event => setDateTo(event.target.value)} /></label>
    </div>

    <div className="paper-ledger-summary published-history-kpis" aria-label="Current ledger summary">
      <div><span>Latest ticket cohorts (after current filters)</span><strong>{filtered.length}</strong></div>
      <div><span>Settled (win, lost, or void)</span><strong>{settledRows.length}</strong></div>
      <div><span>Hit rate (wins / decided tickets)</span><strong>{hitRate == null ? '—' : `${(hitRate * 100).toFixed(1)}%`}</strong></div>
      <div><span>Paper P&amp;L (latest settled cohorts only)</span><strong className={settledPnl >= 0 ? 'positive' : 'negative'}>{fmtPnl(settledPnl)}</strong></div>
      <div><span>ROI (paper P&amp;L / settled stake)</span><strong className={roi == null || roi >= 0 ? 'positive' : 'negative'}>{roi == null ? '—' : `${roi >= 0 ? '+' : ''}${(roi * 100).toFixed(2)}%`}</strong></div>
      <div><span>Published before kickoff (unknown timing is not counted)</span><strong>{publishedBeforeKickoff}</strong></div>
    </div>

    {filtered.length === 0 ? <div className="analytics-empty"><strong>No tickets match these filters</strong><span>Try another tier, outcome, model version or date range.</span></div> : <div className="paper-ledger-list">{groupedRows.map(yearGroup => <details className="paper-year-group" key={yearGroup.year} open={yearGroup.year === today.slice(0, 4) && filtered.some(row => row.target_date === today)}>
      <summary className="paper-year-heading">{yearGroup.year}</summary>
      <div className="paper-year-body">{yearGroup.months.map(monthGroup => <details className="paper-month-group" key={`${yearGroup.year}-${monthGroup.month}`} open={monthGroup.month === today.slice(5, 7) && filtered.some(row => row.target_date === today)}>
        <summary className="paper-month-heading">{monthGroup.monthLabel}</summary>
        <div className="paper-month-body">{monthGroup.dates.map(dayGroup => <details className="paper-date-group" key={dayGroup.date} open={dayGroup.date === today}>
          <summary className="paper-date-heading"><strong>{dayGroup.label}</strong><span>{dayGroup.rows.length} latest cohort{dayGroup.rows.length === 1 ? '' : 's'}</span></summary>
          <div className="paper-date-body">
          {dayGroup.rows.map(row => {
        const versions = allVersions.filter(item => cohortKey(item) === cohortKey(row)).sort((a, b) => b.version - a.version)
        return <article className={`paper-ledger-row${expandedId === row.ticket_id ? ' expanded' : ''}`} key={row.ticket_id}>
          <button className="paper-ticket-summary" onClick={() => toggleTicket(row)} aria-expanded={expandedId === row.ticket_id} aria-label={`${row.name} ticket for ${dayGroup.label}`}>
            <div className="paper-ticket-identity"><span className={`portfolio-tier ${row.ticket_type}`}>{row.name}</span><small>latest v{row.version} · model {row.model_version}{row.internal_only ? ' · internal' : ''}</small></div>
            <div><span>Odds</span><strong>{row.combined_odds == null ? '—' : `${row.combined_odds.toFixed(2)}×`}</strong></div><div><span>Legs</span><strong>{row.leg_count}</strong></div><div><span>Adjusted P</span><strong>{pct(row.adjusted_probability)}</strong></div><div><span>Risk</span><strong>{row.risk_score == null ? '—' : `${row.risk_score.toFixed(0)}/100`}</strong></div>
            <div className="paper-outcome"><span className={`settlement-pill ${row.result ?? 'pending'}`}>{row.result ?? 'pending'}</span>{row.profit_loss != null && <strong className={row.profit_loss >= 0 ? 'positive' : 'negative'}>{fmtPnl(row.profit_loss)}</strong>}</div><span className="paper-chevron" aria-hidden="true">{expandedId === row.ticket_id ? '⌃' : '⌄'}</span>
          </button>
          {expandedId === row.ticket_id && <div className="paper-ticket-detail"><div className="paper-version-toolbar"><div><strong>Immutable versions</strong><span>Select a version to inspect and compare with its predecessor.</span></div><div>{versions.map(version => <button key={version.ticket_id} className={selectedVersion?.ticket_id === version.ticket_id ? 'active' : ''} onClick={() => loadVersion(version)}>v{version.version}</button>)}</div></div>
            {ticketLoading && <div className="odds-state"><span className="spinner" />Loading published selections…</div>}
            {ticket && <><ul>{ticket.legs.map(leg => <li key={leg.selection_id}><div><strong>{leg.home_team} <span>vs</span> {leg.away_team}</strong><small><span className="paper-kickoff-date">{formatDate(leg.kickoff_at)}</span> · <span className="kickoff-time">{formatKickoff(leg.kickoff_at)}</span></small><b className="paper-market-badge">{leg.market.startsWith('double_chance_') ? formatSelection(leg.selection) : formatMarket(leg.market)}</b></div><div><strong>{leg.best_odds == null ? '—' : leg.best_odds.toFixed(2)}</strong><small>Q {leg.q_score == null ? '—' : leg.q_score.toFixed(1)} · {leg.q_grade && <GradeBadge grade={leg.q_grade} />} · {leg.home_goals != null && leg.away_goals != null && <><b className="paper-match-score">{leg.home_goals}–{leg.away_goals}</b> · </>}<b className={`paper-leg-result ${leg.result}`}>{leg.result}</b></small></div></li>)}</ul><div className="paper-audit"><code title={ticket.publication_hash}>Hash {ticket.publication_hash}</code><span>Published {new Date(ticket.published_at).toLocaleString()}</span></div>{compareTicket ? <div className="paper-version-compare"><strong>Compared with v{compareTicket.version}:</strong> {ticket.legs.filter(a => !compareTicket.legs.some(b => b.match_id === a.match_id && b.market === a.market && b.selection === a.selection)).length} added · {compareTicket.legs.filter(a => !ticket.legs.some(b => b.match_id === a.match_id && b.market === a.market && b.selection === a.selection)).length} removed</div> : <div className="paper-version-compare"><strong>Original publication:</strong> no predecessor exists for this cohort.</div>}</>}
          </div>}
        </article>
          })}
          </div>
        </details>)}</div>
      </details>)}</div>
    </details>)}</div>}
  </>
}
