import { useCallback, useEffect, useState } from 'react'

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
  const cardClass = 'rounded-xl border border-slate-200 bg-white p-4'
  const metricLabel = 'block text-sm font-medium uppercase tracking-wide text-slate-600'
  const metricValue = 'mt-1 block font-mono text-xl font-bold tabular-nums text-slate-900'
  const metricSmall = 'mt-1 block text-sm text-slate-600'
  return <section className="space-y-5 text-slate-700">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div><span className="text-sm font-semibold uppercase tracking-wide text-slate-600">Prospective experiment · Paper only</span><h2 className="mt-1 text-2xl font-bold tracking-tight text-slate-900">Sweet-spot tracker</h2><p className="mt-1 text-sm text-slate-600">Away win · Q ≥65 · odds 1.80–below 3.00 · quote age ≤3 hours</p></div>
      <button className="inline-flex min-h-11 items-center gap-1.5 px-3 py-2 text-sm font-semibold text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 rounded-lg transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed" onClick={() => void load()} disabled={loading}>Refresh</button>
    </div>
    {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
    {!data ? <p className="text-base text-slate-600">{loading ? 'Loading paper evidence…' : 'No report available.'}</p> : <>
      <p className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-base leading-relaxed"><strong className="block text-slate-900">{!data.enabled ? 'Collection disabled' : data.collection_status === 'current' ? 'Collection running' : data.collection_status === 'stale' ? 'Collection needs attention' : 'Waiting for first capture'}</strong><span className="mt-1 block text-slate-600">{data.last_run ? `Last completed check: ${when(data.last_run.at)} CAT. Checks run every five minutes while the local server is running.` : 'No successful collection run recorded yet.'}</span></p>
      <p className="text-base leading-relaxed text-slate-600">First prediction per fixture, frozen before kickoff. No threshold changes during this test. Results below are simulated one-unit singles.</p>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <div className={cardClass}><span className={metricLabel}>Settled picks</span><strong className={metricValue}>{data.summary.settled} / {data.protocol.required_settled}</strong><small className={metricSmall}>{data.summary.pending} pending</small></div>
        <div className={cardClass}><span className={metricLabel}>Settled matchdays</span><strong className={metricValue}>{data.summary.matchdays} / {data.protocol.required_matchdays}</strong><small className={metricSmall}>Collection begins {data.protocol.earliest_kickoff_date}</small></div>
        <div className={cardClass}><span className={metricLabel}>Paper profit</span><strong className={metricValue}>{data.summary.profit.toFixed(2)} units</strong><small className={metricSmall}>{data.summary.wins} wins / {data.summary.settled - data.summary.wins} losses</small></div>
        <div className={cardClass}><span className={metricLabel}>Paper ROI</span><strong className={metricValue}>{percent(data.summary.roi)}</strong><small className={metricSmall}>5% winnings reduction: {percent(data.summary.haircut_roi)}</small></div>
        <div className={cardClass}><span className={metricLabel}>Maximum drawdown</span><strong className={metricValue}>{data.summary.drawdown.toFixed(2)} units</strong><small className={metricSmall}>Historical observation, not a future bound</small></div>
      </div>
      <p className="text-base leading-relaxed text-slate-600"><strong className="text-slate-900">{data.review_due ? 'Review requirements reached' : 'Collecting evidence'}</strong> — review no earlier than {data.protocol.minimum_review_date}, with at least 300 settled picks across 30 matchdays. Meeting these requirements does not establish profitability.</p>
      <p className="text-base leading-relaxed text-slate-600">{data.roi_interval_95 ? `Descriptive ROI interval: ${percent(data.roi_interval_95[0])} to ${percent(data.roi_interval_95[1])}.` : 'Not enough settled matchdays for an uncertainty interval.'} {data.interval_note}</p>
      <h3 className="text-base font-semibold text-slate-900">Coverage and exclusions</h3><p className="text-base leading-relaxed text-slate-600">{data.observed_opportunities} opportunities recorded · {data.missing_results} picks awaiting results more than six hours after kickoff.</p>
      {Object.keys(data.exclusions).length ? <ul className="list-disc space-y-1 pl-5 text-base text-slate-600">{Object.entries(data.exclusions).map(([reason, count]) => <li key={reason}>{reason.replace(/_/g, ' ')}: <span className="font-mono tabular-nums">{count}</span></li>)}</ul> : <p className="text-base text-slate-600">No exclusions recorded yet.</p>}
      <h3 className="text-base font-semibold text-slate-900">Frozen picks</h3>
      {!data.picks.length ? <p className="rounded-xl border border-slate-200 bg-white p-6 text-center text-base text-slate-600">No qualifying picks captured yet. A day with no picks is a valid outcome.</p> : <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white"><table className="w-full min-w-[720px] border-collapse text-left text-sm"><thead className="border-b border-slate-200 bg-slate-50 text-sm uppercase tracking-wide text-slate-600"><tr><th className="px-3 py-2">Kickoff (CAT)</th><th className="px-3 py-2">Match / league</th><th className="px-3 py-2">Q</th><th className="px-3 py-2">Odds</th><th className="px-3 py-2">Result</th><th className="px-3 py-2">Profit (units)</th></tr></thead><tbody className="divide-y divide-slate-100">{data.picks.map(p => <tr key={p.match_id} className="hover:bg-slate-50/70"><td className="px-3 py-2 font-mono tabular-nums text-slate-700">{when(p.kickoff_at)}</td><td className="px-3 py-2 text-slate-700">{p.home_team} vs {p.away_team}<small className="mt-0.5 block text-sm text-slate-600">{p.competition} · model {p.model_version}</small></td><td className="px-3 py-2 font-mono tabular-nums text-slate-900">{p.q_score.toFixed(1)}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-900">{p.odds.toFixed(2)}</td><td className="px-3 py-2 text-slate-700">{p.result}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-900">{p.profit == null ? '—' : p.profit.toFixed(2)}</td></tr>)}</tbody></table></div>}
      {(['by_league', 'by_model'] as const).map(key => <details key={key} className="rounded-xl border border-slate-200 bg-white px-4 py-3"><summary className="min-h-11 cursor-pointer text-base font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">{key === 'by_league' ? 'Performance by league' : 'Performance by model version'}</summary><div className="mt-3 overflow-x-auto rounded-lg border border-slate-200"><table className="w-full border-collapse text-left text-sm"><thead className="border-b border-slate-200 bg-slate-50 text-sm uppercase tracking-wide text-slate-600"><tr><th className="px-3 py-2">Group</th><th className="px-3 py-2">Settled</th><th className="px-3 py-2">ROI</th><th className="px-3 py-2">Profit</th></tr></thead><tbody className="divide-y divide-slate-100">{Object.entries(data[key]).map(([name,m]) => <tr key={name} className="hover:bg-slate-50/70"><td className="px-3 py-2 text-slate-700">{name}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-900">{m.settled}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-900">{percent(m.roi)}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-900">{m.profit.toFixed(2)}</td></tr>)}</tbody></table></div></details>)}
      <details className="rounded-xl border border-slate-200 bg-white px-4 py-3"><summary className="min-h-11 cursor-pointer text-base font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Daily collection history</summary><div className="mt-3 overflow-x-auto rounded-lg border border-slate-200"><table className="w-full border-collapse text-left text-sm"><thead className="border-b border-slate-200 bg-slate-50 text-sm uppercase tracking-wide text-slate-600"><tr><th className="px-3 py-2">Day</th><th className="px-3 py-2">Collection observed</th><th className="px-3 py-2">Picks</th><th className="px-3 py-2">Settled</th><th className="px-3 py-2">Profit</th></tr></thead><tbody className="divide-y divide-slate-100">{data.days.map(d => <tr key={d.day} className="hover:bg-slate-50/70"><td className="px-3 py-2 font-mono tabular-nums text-slate-700">{d.day}</td><td className="px-3 py-2 text-slate-700">{d.collection_observed ? 'Yes' : 'Missing'}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-900">{d.picks}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-900">{d.settled}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-900">{d.profit.toFixed(2)}</td></tr>)}</tbody></table></div><p className="mt-3 text-base text-slate-600">A recorded check does not prove uninterrupted coverage throughout that day.</p></details>
      <details className="rounded-xl border border-slate-200 bg-white px-4 py-3"><summary className="min-h-11 cursor-pointer text-base font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Evidence limitations</summary><ul className="mt-3 list-disc space-y-1 pl-5 text-base text-slate-600">{data.limitations.map(s => <li key={s}>{s}</li>)}</ul></details>
    </>}
  </section>
}
