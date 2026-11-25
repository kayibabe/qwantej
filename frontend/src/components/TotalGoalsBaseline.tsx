import type { TotalGoalsBaseline as Distribution } from '../lib/api'

const markets = ['under_0.5', 'over_1.5', 'under_1.5', 'over_2.5', 'under_2.5', 'over_3.5', 'under_3.5', 'over_4.5'] as const

export default function TotalGoalsBaseline({ distribution }: { distribution?: Distribution | null }) {
  if (!distribution) return null
  const calibrated = distribution.calibrated && distribution.calibration?.status === 'promoted'
  return <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3 text-sm text-slate-700">
    <summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Shared eight-market forecast</summary>
    <div className="mt-3 space-y-3 leading-relaxed">
      <p>One independent-Poisson total-goals forecast from projected home/away goals ({distribution.home_projected_goals.toFixed(2)} + {distribution.away_projected_goals.toFixed(2)} = {distribution.combined_projected_goals.toFixed(2)}). Over and Under probabilities are complements at the same goal line. {calibrated ? `Shared calibration profile ${distribution.calibration?.profile_id} passed its chronological holdout (rate scale ${distribution.calibration?.scale?.toFixed(3) ?? 'unavailable'}); each market still requires its own evidence gates.` : 'This is an uncalibrated diagnostic and cannot qualify a selection.'}</p>
      {distribution.raw_combined_projected_goals != null && <p>Raw combined projection: {distribution.raw_combined_projected_goals.toFixed(2)} goals.</p>}
      {distribution.forecast_id && <p className="text-sm text-slate-600"><small>Forecast {distribution.forecast_id} · model {distribution.model_version ?? 'unknown'} · captured {distribution.created_at ?? 'timestamp unavailable'}</small></p>}
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full border-collapse text-left text-sm"><thead className="border-b border-slate-200 bg-slate-50 text-sm font-semibold uppercase tracking-wide text-slate-600"><tr><th className="px-3 py-2">Market</th><th className="px-3 py-2">Shared baseline</th></tr></thead><tbody className="divide-y divide-slate-100">
          {markets.map(market => <tr key={market} className="hover:bg-slate-50/70"><td className="px-3 py-2 text-slate-700">{market.replace('_', ' ')}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-900">{(distribution.markets[market] * 100).toFixed(1)}%</td></tr>)}
        </tbody></table>
      </div>
    </div>
  </details>
}
