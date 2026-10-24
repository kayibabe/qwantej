import { useState } from 'react'
import type { Under25Qualification as Assessment } from '../lib/api'
import TotalGoalsBaseline from './TotalGoalsBaseline'

export function under25Illustration(home: string, away: string, price: string) {
  const h = home.trim() ? Number(home) : NaN
  const a = away.trim() ? Number(away) : NaN
  const odds = price.trim() ? Number(price) : NaN
  if (![h, a].every(value => Number.isFinite(value) && value >= 0 && value <= 20)) return null
  const total = h + a
  const probability = Math.exp(-total) * (1 + total + total * total / 2)
  const grade = probability >= .8 ? 'A+' : probability >= .72 ? 'A' : probability >= .65 ? 'B' : probability >= .55 ? 'C' : 'D'
  return { probability, grade, fairOdds: 1 / probability,
    ev: Number.isFinite(odds) && odds > 1 ? probability * odds - 1 : null }
}

const labels: Record<string, string> = {
  projected_xg: 'Projected match xG', combined_scored: 'Matchup-adjusted goals scored',
  combined_conceded: 'Matchup-adjusted goals conceded', under25_frequency: 'Under 2.5 frequency',
  under35_frequency: 'Under 3.5 frequency', over35_frequency: 'Over 3.5 frequency',
  combined_shots_on_target: 'Combined shots on target', btts_frequency: 'BTTS Yes frequency',
  first_half_under15_frequency: 'First-half Under 1.5 frequency',
}
const format = (key: string, value: number | null) => value == null ? 'Unavailable' :
  key.endsWith('frequency') ? `${(value * 100).toFixed(0)}%` : value.toFixed(2)

export default function Under25Qualification({ assessment }: { assessment?: Assessment | null }) {
  const [home, setHome] = useState('0.9')
  const [away, setAway] = useState('0.8')
  const [odds, setOdds] = useState('1.55')
  const illustration = under25Illustration(home, away, odds)
  return <section className="explainability-card" aria-label="Under 2.5 qualification">
    <div className="evidence-title"><h3>Under 2.5 qualification</h3><span>Provisional · league validation required</span></div>
    <p>Zero, one or two total goals in 90 minutes plus stoppage time. Extra time and penalties do not count. 0–0, 1–0, 0–1, 1–1, 2–0 and 0–2 win; 2–1 and 3–0 lose.</p>
    {assessment ? <>
      <p><strong>{assessment.status} · Probability grade {assessment.grade ?? 'unavailable'}</strong> · {assessment.calibrated ? 'Calibrated estimate' : assessment.shared_goals_forecast?.calibrated ? 'Shared calibrated forecast (market gates remain)' : assessment.probability_source === 'shared_goals_forecast' ? 'Shared Poisson forecast (not calibrated)' : 'Unvalidated estimate'}: {assessment.probability == null ? 'Unavailable' : `${(assessment.probability * 100).toFixed(1)}%`}</p>
      <p>Fair odds: {assessment.fair_odds?.toFixed(2) ?? 'Unavailable'} · Estimated EV: {assessment.expected_value == null ? 'Unavailable' : `${(assessment.expected_value * 100).toFixed(1)}%`} · Recent sample: {assessment.sample_sizes.home ?? 0} home / {assessment.sample_sizes.away ?? 0} away (8–12 per team).</p>
      <div className="table-wrap"><table><thead><tr><th>Indicator</th><th>Adjusted evidence</th><th>Threshold</th><th>Screen</th></tr></thead><tbody>
        {assessment.checks.map(check => <tr key={check.key}><td>{labels[check.key] ?? check.key}</td><td>{format(check.key, check.value)}</td><td>{check.direction === 'max' ? '≤' : '≥'} {format(check.key, check.threshold)}</td><td>{check.status}</td></tr>)}
      </tbody></table></div>
      {assessment.reasons.length > 0 && <details><summary>Qualification blockers ({assessment.reasons.length})</summary><ul>{assessment.reasons.map(reason => <li key={reason}>{reason.replace(/^UNDER25_/, '').replace(/_/g, ' ').toLowerCase()}</li>)}</ul></details>}
      <TotalGoalsBaseline distribution={assessment.shared_goals_forecast} />
    </> : <p>No qualification evidence was captured. This selection cannot qualify under the new policy.</p>}
    <p>A+ ≥80%; A ≥72%; B ≥65% conditional research only; C ≥55% generally avoid; D below 55% reject. Primary selections require A/A+, validated calibration and positive EV. Preferred projected goals ≤1.8, ideally ≤1.7; the initial maximum is 2.0.</p>
    <p>Review defensive absences, chance quality and finishing slumps, attacking mismatches, open transitions, aggressive lineups, unexplained market disagreement and second-half escalation. Low recent scores alone are insufficient. No daily minimum is forced.</p>
    <details><summary>Illustrative Poisson calculator</summary>
      <p>Independent-Poisson illustration only. These inputs do not alter the selection, calibration or qualification decision.</p>
      <div className="form-row">
        <label>Home projected goals <input type="number" min="0" max="20" step="0.1" value={home} onChange={event => setHome(event.target.value)} /></label>
        <label>Away projected goals <input type="number" min="0" max="20" step="0.1" value={away} onChange={event => setAway(event.target.value)} /></label>
        <label>Bookmaker decimal odds <input type="number" min="1.01" step="0.01" value={odds} onChange={event => setOdds(event.target.value)} /></label>
      </div>
      <div aria-live="polite">{illustration ? <p>Under 2.5: {(illustration.probability * 100).toFixed(1)}% · Fair odds: {illustration.fairOdds.toFixed(2)} · Grade {illustration.grade} · Theoretical EV: {illustration.ev == null ? 'Enter valid odds above 1' : `${illustration.ev > 0 ? '+' : ''}${(illustration.ev * 100).toFixed(1)}%`}</p> : <p>Enter both projected goals between 0 and 20.</p>}</div>
      <p>At 80%, fair odds are 1.25; a quote of 1.18 has negative expected value. Probability is not a betting recommendation.</p>
    </details>
  </section>
}
