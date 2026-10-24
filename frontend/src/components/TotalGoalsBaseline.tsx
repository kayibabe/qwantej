import type { TotalGoalsBaseline as Distribution } from '../lib/api'

const markets = ['under_0.5', 'over_1.5', 'under_1.5', 'over_2.5', 'under_2.5', 'over_3.5', 'under_3.5', 'over_4.5'] as const

export default function TotalGoalsBaseline({ distribution }: { distribution?: Distribution | null }) {
  if (!distribution) return null
  const calibrated = distribution.calibrated && distribution.calibration?.status === 'promoted'
  return <details><summary>Shared eight-market forecast</summary>
    <p>One independent-Poisson total-goals forecast from projected home/away goals ({distribution.home_projected_goals.toFixed(2)} + {distribution.away_projected_goals.toFixed(2)} = {distribution.combined_projected_goals.toFixed(2)}). Over and Under probabilities are complements at the same goal line. {calibrated ? `Shared calibration profile ${distribution.calibration?.profile_id} passed its chronological holdout (rate scale ${distribution.calibration?.scale?.toFixed(3) ?? 'unavailable'}); each market still requires its own evidence gates.` : 'This is an uncalibrated diagnostic and cannot qualify a selection.'}</p>
    {distribution.raw_combined_projected_goals != null && <p>Raw combined projection: {distribution.raw_combined_projected_goals.toFixed(2)} goals.</p>}
    {distribution.forecast_id && <p><small>Forecast {distribution.forecast_id} · model {distribution.model_version ?? 'unknown'} · captured {distribution.created_at ?? 'timestamp unavailable'}</small></p>}
    <div className="table-wrap"><table><thead><tr><th>Market</th><th>Shared baseline</th></tr></thead><tbody>
      {markets.map(market => <tr key={market}><td>{market.replace('_', ' ')}</td><td>{(distribution.markets[market] * 100).toFixed(1)}%</td></tr>)}
    </tbody></table></div>
  </details>
}
