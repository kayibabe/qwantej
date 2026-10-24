import { useState } from 'react'
import type { Under35Qualification as Assessment } from '../lib/api'
import TotalGoalsBaseline from './TotalGoalsBaseline'

export function under35Illustration(home: string, away: string, price: string) {
  const h = home.trim() ? Number(home) : NaN
  const a = away.trim() ? Number(away) : NaN
  const odds = price.trim() ? Number(price) : NaN
  if (![h, a].every(value => Number.isFinite(value) && value >= 0 && value <= 20)) return null
  const total = h + a
  const probability = Math.exp(-total) * (1 + total + total ** 2 / 2 + total ** 3 / 6)
  const grade = probability >= .9 ? 'A+' : probability >= .82 ? 'A' : probability >= .75 ? 'B' : probability >= .65 ? 'C' : 'D'
  return { probability, fourPlus: 1 - probability, grade, fairOdds: 1 / probability,
    ev: Number.isFinite(odds) && odds > 1 ? probability * odds - 1 : null }
}

const labels: Record<string, string> = {
  projected_goals: 'Projected total goals', historical_goals_profile: 'Matchup-adjusted historical goals',
  combined_shots_on_target: 'Combined shots on target', under25_frequency: 'Under 2.5 frequency',
  under35_frequency: 'Under 3.5 frequency', under45_frequency: 'Under 4.5 frequency',
  over35_frequency: 'Over 3.5 frequency', over45_frequency: 'Over 4.5 frequency',
  btts_frequency: 'BTTS Yes (optional)', first_half_under15_frequency: 'First-half Under 1.5 frequency',
}
const format = (key: string, value: number | null) => value == null ? 'Unavailable' :
  key.endsWith('frequency') ? `${(value * 100).toFixed(0)}%` : value.toFixed(2)
const percent = (value: number | null) => value == null ? 'Unavailable' : `${(value * 100).toFixed(1)}%`
const reason = (value: string) => value.replace(/^UNDER35_/, '').replace(/_/g, ' ').toLowerCase()

export default function Under35Qualification({ assessment }: { assessment?: Assessment | null }) {
  const [home, setHome] = useState('1.2')
  const [away, setAway] = useState('1.0')
  const [odds, setOdds] = useState('1.35')
  const illustration = under35Illustration(home, away, odds)
  return <section className="explainability-card" aria-label="Under 3.5 qualification">
    <div className="evidence-title"><h3>Under 3.5 qualification</h3><span>Provisional · separate market calibration</span></div>
    <p>Zero to three total goals in 90 minutes plus stoppage time. Extra time and penalties do not count. 2–1, 1–2, 3–0 and 0–3 win; 2–2, 3–1 and 4–0 lose.</p>
    {assessment ? <>
      <p><strong>{assessment.status} · Grade {assessment.grade ?? 'unavailable'} · {assessment.selection_pool} pool</strong> · {assessment.calibrated ? 'Calibrated estimate' : assessment.shared_goals_forecast?.calibrated ? 'Shared calibrated forecast (market gates remain)' : assessment.probability_source === 'shared_goals_forecast' ? 'Shared Poisson forecast (not calibrated)' : 'Unvalidated estimate'}</p>
      <p>Under 3.5: {percent(assessment.probability)} · Four or more goals: {percent(assessment.four_plus_probability)} · Fair odds: {assessment.fair_odds?.toFixed(2) ?? 'Unavailable'} · Estimated EV: {percent(assessment.expected_value)}</p>
      <p>Recent sample: {assessment.sample_sizes.home ?? 0} home / {assessment.sample_sizes.away ?? 0} away matches. Require 8–12 per team plus longer-term league context and sample-size shrinkage.</p>
      <div className="table-wrap"><table><thead><tr><th>Indicator</th><th>Evidence</th><th>Preferred threshold</th><th>Screen</th></tr></thead><tbody>
        {assessment.checks.map(check => <tr key={check.key}><td>{labels[check.key] ?? check.key}</td><td>{format(check.key, check.value)}</td><td>{check.direction === 'max' ? '≤' : '≥'} {format(check.key, check.threshold)}</td><td>{check.status} · {check.required ? 'core' : 'advisory'}</td></tr>)}
      </tbody></table></div>
      {assessment.reasons.length > 0 && <details><summary>Qualification blockers ({assessment.reasons.length})</summary><ul>{assessment.reasons.map(item => <li key={item}>{reason(item)}</li>)}</ul></details>}
      {assessment.warnings.length > 0 && <details><summary>Supporting indicators to review ({assessment.warnings.length})</summary><ul>{assessment.warnings.map(item => <li key={item}>{reason(item)}</li>)}</ul></details>}
      <TotalGoalsBaseline distribution={assessment.shared_goals_forecast} />
    </> : <p>No qualification evidence was captured. This selection cannot qualify under the new policy.</p>}
    <p>A+ ≥90%; A ≥82%; B ≥75% only with strong supporting evidence and an attractive-price review; C ≥65% normally excluded; D below 65% rejected. A/A+ form the primary pool. All releases require positive EV and validated Under 3.5 calibration.</p>
    <p>Projected goals ≤2.5 is the initial core screen, ideally ≤2.2. Other indicators support a documented review rather than acting as overlapping hard rules. BTTS is optional; no additive indicator score or forced daily minimum is used.</p>
    <p>Prioritise disciplined defences, moderate attacks, favourites with defensive control and cautious tactical profiles. Review big chances, dominant attacks against weak defences, absences, fortunate finishing, dangerous transitions, lineup changes and unexplained market disagreement. A favourite scoring four goals is still a losing outcome.</p>
    <details><summary>Illustrative Poisson calculator</summary>
      <p>Independent-Poisson illustration only, without lineups, correlated scoring, uncertainty or live prices. Inputs do not change the selection or qualification decision.</p>
      <div className="form-row">
        <label>Home projected goals <input type="number" min="0" max="20" step="0.1" value={home} onChange={event => setHome(event.target.value)} /></label>
        <label>Away projected goals <input type="number" min="0" max="20" step="0.1" value={away} onChange={event => setAway(event.target.value)} /></label>
        <label>Bookmaker decimal odds <input type="number" min="1.01" step="0.01" value={odds} onChange={event => setOdds(event.target.value)} /></label>
      </div>
      <div aria-live="polite">{illustration ? <p>Under 3.5: {percent(illustration.probability)} · Four or more: {percent(illustration.fourPlus)} · Fair odds: {illustration.fairOdds.toFixed(2)} · Grade {illustration.grade} · Theoretical EV: {percent(illustration.ev)}</p> : <p>Enter both projected goals between 0 and 20.</p>}</div>
      <p>At 85%, odds of 1.25 give +6.25% theoretical EV; 1.10 gives −6.5%. A high probability alone is not a betting recommendation.</p>
    </details>
  </section>
}
