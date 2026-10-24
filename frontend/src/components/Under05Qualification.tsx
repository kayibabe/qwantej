import { useState } from 'react'
import type { Under05Qualification as Assessment } from '../lib/api'
import TotalGoalsBaseline from './TotalGoalsBaseline'

export function under05Illustration(home: string, away: string, price: string) {
  const h = home.trim() ? Number(home) : NaN
  const a = away.trim() ? Number(away) : NaN
  const odds = price.trim() ? Number(price) : NaN
  if (![h, a].every(value => Number.isFinite(value) && value >= 0 && value <= 20)) return null
  const probability = Math.exp(-(h + a))
  const grade = probability >= .4 ? 'A+' : probability >= .3 ? 'A' : probability >= .22 ? 'B' : probability >= .15 ? 'C' : 'D'
  const validOdds = Number.isFinite(odds) && odds > 1
  const stressed = Math.max(0, probability - .05)
  return { probability, onePlus: 1 - probability, grade, fairOdds: 1 / probability, stressed,
    implied: validOdds ? 1 / odds : null, edge: validOdds ? probability - 1 / odds : null,
    ev: validOdds ? probability * odds - 1 : null, stressedEv: validOdds ? stressed * odds - 1 : null }
}

const labels: Record<string, string> = {
  projected_goals: 'Combined projected goals', home_projected_goals: 'Home projected goals',
  away_projected_goals: 'Away projected goals', zero_zero_frequency: 'Historical 0–0 frequency',
  under15_frequency: 'Under 1.5 frequency', under25_frequency: 'Under 2.5 frequency',
  combined_shots_on_target: 'Combined shots on target', combined_big_chances: 'Combined big chances',
  btts_frequency: 'BTTS Yes frequency', first_half_zero_zero_frequency: 'First-half 0–0 frequency',
}
const percent = (value: number | null) => value == null ? 'Unavailable' : `${(value * 100).toFixed(1)}%`
const points = (value: number | null) => value == null ? 'Unavailable' : `${(value * 100).toFixed(1)} pp`
const format = (key: string, value: number | null) => value == null ? 'Unavailable' :
  key.endsWith('frequency') ? percent(value) : value.toFixed(2)
const reason = (value: string) => value.replace(/^UNDER05_/, '').replace(/_/g, ' ').toLowerCase()

export default function Under05Qualification({ assessment }: { assessment?: Assessment | null }) {
  const [home, setHome] = useState('0.50')
  const [away, setAway] = useState('0.50')
  const [odds, setOdds] = useState('3.50')
  const illustration = under05Illustration(home, away, odds)
  return <section className="explainability-card" aria-label="Under 0.5 qualification">
    <div className="evidence-title"><h3>Under 0.5 qualification</h3><span>Provisional · exact 0–0 calibration</span></div>
    <p>Only 0–0 wins after 90 minutes plus stoppage time. Any goal loses. Extra time and shootouts do not count.</p>
    {assessment ? <>
      <p><strong>{assessment.status} · Grade {assessment.grade ?? 'unavailable'} · {assessment.selection_pool} pool</strong> · {assessment.calibrated ? 'Calibrated estimate' : assessment.shared_goals_forecast?.calibrated ? 'Shared calibrated forecast (market gates remain)' : assessment.probability_source === 'shared_goals_forecast' ? 'Shared Poisson forecast (not calibrated)' : 'Unvalidated estimate'}</p>
      <p>0–0: {percent(assessment.probability)} · At least one goal: {percent(assessment.one_plus_probability)} · Fair odds: {assessment.fair_odds?.toFixed(2) ?? 'Unavailable'} · EV: {percent(assessment.expected_value)}</p>
      <p>Bookmaker implied probability: {percent(assessment.implied_probability)} · Model edge: {points(assessment.edge)}. Implied probability includes bookmaker margin.</p>
      <p>Stress test: reduce probability by {points(assessment.probability_haircut)} → {percent(assessment.stressed_probability)}; stressed EV: {percent(assessment.stressed_expected_value)}. Both ordinary and stressed EV must be strictly positive.</p>
      <p>Recent sample: {assessment.sample_sizes.home ?? 0} home / {assessment.sample_sizes.away ?? 0} away. Require 10–15 comparable matches per team, longer-term context and sample-size adjustment.</p>
      <div className="table-wrap"><table><thead><tr><th>Indicator</th><th>Evidence</th><th>Preferred threshold</th><th>Advisory screen</th></tr></thead><tbody>
        {assessment.checks.map(check => <tr key={check.key}><td>{labels[check.key] ?? check.key}</td><td>{format(check.key, check.value)}</td><td>{check.direction === 'max' ? '≤' : '≥'} {format(check.key, check.threshold)}</td><td>{check.status}</td></tr>)}
      </tbody></table></div>
      {assessment.reasons.length > 0 && <details><summary>Qualification blockers ({assessment.reasons.length})</summary><ul>{assessment.reasons.map(item => <li key={item}>{reason(item)}</li>)}</ul></details>}
      {assessment.warnings.length > 0 && <details><summary>Supporting indicators to review ({assessment.warnings.length})</summary><ul>{assessment.warnings.map(item => <li key={item}>{reason(item)}</li>)}</ul></details>}
      <TotalGoalsBaseline distribution={assessment.shared_goals_forecast} />
    </> : <p>No qualification evidence was captured. This selection cannot qualify under the new policy.</p>}
    <p>A+ ≥40%; A ≥30%; B ≥22% conditional; C ≥15% generally reject; D below 15% reject. A/A+ are the primary shortlist, not betting guarantees. An A+ estimate of 40% still means a 60% loss probability.</p>
    <p>Projected goals ≤1.2, ideally ≤0.9. The indicators are preferences, not an all-pass checklist: 0.8–0.2 can remain suitable. A recent 0–0 rate is not the next match’s probability, and head-to-head history is not a major selection factor.</p>
    <p>Require measured low chance creation, strong defences, both teams’ clean-sheet evidence and sustained low-event tactics. Review attacking favourites, absences, finishing slumps, early goals, penalties, set pieces, transitions, unsustainable goalkeeping and attacking tactical risks. No daily minimum is forced.</p>
    <details><summary>Illustrative Poisson calculator</summary>
      <p>Independent-Poisson illustration only, not a calibrated live signal. Inputs do not change the selection or qualification decision.</p>
      <div className="form-row">
        <label>Home projected goals <input type="number" min="0" max="20" step="0.05" value={home} onChange={event => setHome(event.target.value)} /></label>
        <label>Away projected goals <input type="number" min="0" max="20" step="0.05" value={away} onChange={event => setAway(event.target.value)} /></label>
        <label>Bookmaker decimal odds <input type="number" min="1.01" step="0.01" value={odds} onChange={event => setOdds(event.target.value)} /></label>
      </div>
      <div aria-live="polite">{illustration ? <>
        <p>0–0: {percent(illustration.probability)} · At least one goal: {percent(illustration.onePlus)} · Fair odds: {illustration.fairOdds.toFixed(2)} · Grade {illustration.grade}</p>
        <p>Theoretical EV: {percent(illustration.ev)} · Bookmaker implied: {percent(illustration.implied)} · Edge: {points(illustration.edge)} · Stressed EV: {percent(illustration.stressedEv)}</p>
      </> : <p>Enter both projected goals between 0 and 20.</p>}</div>
      <p>The five-percentage-point reduction is an initial stress scenario, not a validated uncertainty bound. At 1.2 projected goals, at least one goal has a 69.9% Poisson probability. A 50% chance of 0–0 needs total projected goals near 0.69 or lower.</p>
      <p>At 35%, odds of 3.20 give +12% ordinary EV but −4% after the five-point reduction, so this price fails the robustness gate.</p>
    </details>
  </section>
}
