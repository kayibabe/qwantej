import { useCallback, useEffect, useState } from 'react'
import './SweetSpotTracker.css'

type Metrics = { picks: number; settled: number; pending: number; wins: number; profit: number; roi: number | null; drawdown: number; matchdays: number; haircut_roi: number | null }
type Pick = { match_id: number; home_team: string; away_team: string; competition: string; kickoff_at: string; q_score: number; odds: number; result: string; profit: number | null; model_version: string }
type Report = {
  enabled: boolean; collection_status: string; last_run: { at: string } | null; review_due: boolean;
  summary: Metrics; observed_opportunities: number; missing_results: number; exclusions: Record<string, number>;
  protocol: { minimum_review_date: string; earliest_kickoff_date: string; required_settled: number; required_matchdays: number };
  roi_interval_95: number[] | null; interval_note: string; by_league: Record<string, Metrics>; by_model: Record<string, Metrics>;
  picks: Pick[]; days: ({ day: string; collection_observed: boolean } & Metrics)[]; limitations: string[];
}
const percent = (n: number | null) => n == null ? '—' : `${n.toFixed(2)}%`
const when = (s: string) => new Date(s).toLocaleString('en-GB', { timeZone: 'Africa/Blantyre', dateStyle: 'medium', timeStyle: 'short' })

export default function SweetSpotTracker() {
  const [data, setData] = useState<Report | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const response = await fetch('/api/v1/sweet-spot')
      if (!response.ok) throw new Error(`Paper tracker unavailable (${response.status}). Sign in and try again.`)
      setData(await response.json())
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to load tracker') }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { void load(); const id = setInterval(() => void load(), 60000); return () => clearInterval(id) }, [load])
  return <section className="sweet-spot">
    <div className="sweet-heading"><div><span className="eyebrow">Prospective experiment · Paper only</span><h2>Sweet-spot tracker</h2><p>Away win · Q ≥65 · odds 1.80–below 3.00 · quote age ≤3 hours</p></div><button className="btn-ghost" onClick={() => void load()} disabled={loading}>Refresh</button></div>
    {error && <p role="alert">{error}</p>}
    {!data ? <p>{loading ? 'Loading paper evidence…' : 'No report available.'}</p> : <>
      <p className="journal-note"><strong>{!data.enabled ? 'Collection disabled' : data.collection_status === 'current' ? 'Collection running' : data.collection_status === 'stale' ? 'Collection needs attention' : 'Waiting for first capture'}</strong><span>{data.last_run ? `Last completed check: ${when(data.last_run.at)} CAT. Checks run every five minutes while the local server is running.` : 'No successful collection run recorded yet.'}</span></p>
      <p>First prediction per fixture, frozen before kickoff. No threshold changes during this test. Results below are simulated one-unit singles.</p>
      <div className="sweet-metrics">
        <div><span>Settled picks</span><strong>{data.summary.settled} / {data.protocol.required_settled}</strong><small>{data.summary.pending} pending</small></div>
        <div><span>Settled matchdays</span><strong>{data.summary.matchdays} / {data.protocol.required_matchdays}</strong><small>Collection begins {data.protocol.earliest_kickoff_date}</small></div>
        <div><span>Paper profit</span><strong>{data.summary.profit.toFixed(2)} units</strong><small>{data.summary.wins} wins / {data.summary.settled - data.summary.wins} losses</small></div>
        <div><span>Paper ROI</span><strong>{percent(data.summary.roi)}</strong><small>5% winnings reduction: {percent(data.summary.haircut_roi)}</small></div>
        <div><span>Maximum drawdown</span><strong>{data.summary.drawdown.toFixed(2)} units</strong><small>Historical observation, not a future bound</small></div>
      </div>
      <p><strong>{data.review_due ? 'Review requirements reached' : 'Collecting evidence'}</strong> — review no earlier than {data.protocol.minimum_review_date}, with at least 300 settled picks across 30 matchdays. Meeting these requirements does not establish profitability.</p>
      <p>{data.roi_interval_95 ? `Descriptive ROI interval: ${percent(data.roi_interval_95[0])} to ${percent(data.roi_interval_95[1])}.` : 'Not enough settled matchdays for an uncertainty interval.'} {data.interval_note}</p>
      <h3>Coverage and exclusions</h3><p>{data.observed_opportunities} opportunities recorded · {data.missing_results} picks awaiting results more than six hours after kickoff.</p>
      {Object.keys(data.exclusions).length ? <ul>{Object.entries(data.exclusions).map(([reason, count]) => <li key={reason}>{reason.replace(/_/g, ' ')}: {count}</li>)}</ul> : <p>No exclusions recorded yet.</p>}
      <h3>Frozen picks</h3>
      {!data.picks.length ? <p className="empty-state">No qualifying picks captured yet. A day with no picks is a valid outcome.</p> : <div className="sweet-table"><table><thead><tr><th>Kickoff (CAT)</th><th>Match / league</th><th>Q</th><th>Odds</th><th>Result</th><th>Profit (units)</th></tr></thead><tbody>{data.picks.map(p => <tr key={p.match_id}><td>{when(p.kickoff_at)}</td><td>{p.home_team} vs {p.away_team}<small>{p.competition} · model {p.model_version}</small></td><td>{p.q_score.toFixed(1)}</td><td>{p.odds.toFixed(2)}</td><td>{p.result}</td><td>{p.profit == null ? '—' : p.profit.toFixed(2)}</td></tr>)}</tbody></table></div>}
      {(['by_league', 'by_model'] as const).map(key => <details key={key}><summary>{key === 'by_league' ? 'Performance by league' : 'Performance by model version'}</summary><div className="sweet-table"><table><thead><tr><th>Group</th><th>Settled</th><th>ROI</th><th>Profit</th></tr></thead><tbody>{Object.entries(data[key]).map(([name,m]) => <tr key={name}><td>{name}</td><td>{m.settled}</td><td>{percent(m.roi)}</td><td>{m.profit.toFixed(2)}</td></tr>)}</tbody></table></div></details>)}
      <details><summary>Daily collection history</summary><div className="sweet-table"><table><thead><tr><th>Day</th><th>Collection observed</th><th>Picks</th><th>Settled</th><th>Profit</th></tr></thead><tbody>{data.days.map(d => <tr key={d.day}><td>{d.day}</td><td>{d.collection_observed ? 'Yes' : 'Missing'}</td><td>{d.picks}</td><td>{d.settled}</td><td>{d.profit.toFixed(2)}</td></tr>)}</tbody></table></div><p>A recorded check does not prove uninterrupted coverage throughout that day.</p></details>
      <details><summary>Evidence limitations</summary><ul>{data.limitations.map(s => <li key={s}>{s}</li>)}</ul></details>
    </>}
  </section>
}
