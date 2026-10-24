import { useState } from 'react'
import type { Under15Qualification as Assessment } from '../lib/api'
import TotalGoalsBaseline from './TotalGoalsBaseline'

export function under15Illustration(home: string, away: string, price: string) {
  const h = home.trim() ? Number(home) : NaN
  const a = away.trim() ? Number(away) : NaN
  const odds = price.trim() ? Number(price) : NaN
  if (![h, a].every(value => Number.isFinite(value) && value >= 0 && value <= 20)) return null
  const total = h + a
  const zero = Math.exp(-total)
  const probability = zero * (1 + total)
  const grade = probability >= .8 ? 'A+' : probability >= .7 ? 'A' : probability >= .6 ? 'B' : probability >= .45 ? 'C' : 'D'
  return { probability, twoPlus: 1 - probability, zero, homeOnly: h * zero, awayOnly: a * zero,
    exactlyOne: total * zero, grade, fairOdds: 1 / probability,
    ev: Number.isFinite(odds) && odds > 1 ? probability * odds - 1 : null }
}

const labels: Record<string, string> = {
  projected_goals: 'Combined projected goals', home_projected_goals: 'Home projected goals (preferred)',
  away_projected_goals: 'Away projected goals (preferred)', under15_frequency: 'Under 1.5 frequency',
  under25_frequency: 'Under 2.5 frequency', under35_frequency: 'Under 3.5 frequency',
  combined_shots_on_target: 'Combined shots on target', btts_frequency: 'BTTS Yes frequency',
  first_half_under05_frequency: 'First-half Under 0.5 frequency', first_half_under15_frequency: 'First-half Under 1.5 frequency',
}
const percent = (value: number | null) => value == null ? 'Unavailable' : `${(value * 100).toFixed(1)}%`
const format = (key: string, value: number | null) => value == null ? 'Unavailable' :
  key.endsWith('frequency') ? `${(value * 100).toFixed(0)}%` : value.toFixed(2)
const reason = (value: string) => value.replace(/^UNDER15_/, '').replace(/_/g, ' ').toLowerCase()

export default function Under15Qualification({ assessment }: { assessment?: Assessment | null }) {
  const [home, setHome] = useState('0.5')
  const [away, setAway] = useState('0.5')
  const [odds, setOdds] = useState('1.65')
  const illustration = under15Illustration(home, away, odds)
  return <section className="explainability-card" aria-label="Under 1.5 qualification">
    <div className="evidence-title"><h3>Under 1.5 qualification</h3><span>Provisional · separate low-score calibration</span></div>
    <p>Only 0–0, 1–0 and 0–1 win in 90 minutes plus stoppage time. 1–1, 2–0, 0–2 and every other two-or-more-goal score lose. Extra time and penalties do not count.</p>
    {assessment ? <>
      <p><strong>{assessment.status} · Grade {assessment.grade ?? 'unavailable'} · {assessment.selection_pool} pool</strong> · {assessment.calibrated ? 'Calibrated estimate' : assessment.shared_goals_forecast?.calibrated ? 'Shared calibrated forecast (market gates remain)' : assessment.probability_source === 'shared_goals_forecast' ? 'Shared Poisson forecast (not calibrated)' : 'Unvalidated estimate'}</p>
      <p>Under 1.5: {percent(assessment.probability)} · Two or more goals: {percent(assessment.two_plus_probability)} · Fair odds: {assessment.fair_odds?.toFixed(2) ?? 'Unavailable'} · Estimated EV: {percent(assessment.expected_value)}</p>
      {assessment.low_score_model && <p>Uncalibrated Poisson/Dixon–Coles component: 0–0 {percent(assessment.low_score_model.zero_goals)} · Exactly one goal {percent(assessment.low_score_model.exactly_one_goal)}. These are separate from the ensemble estimate above.</p>}
      <p>Recent sample: {assessment.sample_sizes.home ?? 0} home / {assessment.sample_sizes.away ?? 0} away. Require 8–12 comparable recent games per team, longer-term data and league shrinkage.</p>
      <div className="table-wrap"><table><thead><tr><th>Indicator</th><th>Evidence</th><th>Threshold</th><th>Screen</th></tr></thead><tbody>
        {assessment.checks.map(check => <tr key={check.key}><td>{labels[check.key] ?? check.key}</td><td>{format(check.key, check.value)}</td><td>{check.direction === 'max' ? '≤' : '≥'} {format(check.key, check.threshold)}</td><td>{check.status} · {check.required ? 'required' : 'advisory'}</td></tr>)}
      </tbody></table></div>
      {assessment.reasons.length > 0 && <details><summary>Qualification blockers ({assessment.reasons.length})</summary><ul>{assessment.reasons.map(item => <li key={item}>{reason(item)}</li>)}</ul></details>}
      <TotalGoalsBaseline distribution={assessment.shared_goals_forecast} />
      {assessment.warnings.length > 0 && <details><summary>Advisory indicators ({assessment.warnings.length})</summary><ul>{assessment.warnings.map(item => <li key={item}>{reason(item)}</li>)}</ul></details>}
    </> : <p>No qualification evidence was captured. This selection cannot qualify under the new policy.</p>}
    <p>A+ ≥80%; A ≥70%; B ≥60% only with a compelling-value review; C ≥45% generally excluded; D below 45% rejected. A/A+ form the primary pool. Every release requires positive EV, calibrated probabilities and verified context.</p>
    <p>Combined projected goals ≤1.2, preferably ≤1.0 and ideally ≤0.9. The individual 0.7 home and 0.6 away limits are advisory: 0.9–0.2 may still pass the combined screen.</p>
    <p>Prioritise low chance creation, compact defences and measured low tempo. A defensive favourite must also have a low scoring projection: 2–0 loses. Review early goals, missing defenders or goalkeepers, pressing, transitions, weak-opponent samples, market disagreement and aggressive lineups. Penalties, red cards and tactical surprises remain uncertain. No daily minimum is forced.</p>
    <details><summary>Illustrative Poisson calculator</summary>
      <p>Independent-Poisson illustration only, not a calibrated live signal. Inputs do not change the selection or qualification decision and do not capture uncertainty in projected goals.</p>
      <div className="form-row">
        <label>Home projected goals <input type="number" min="0" max="20" step="0.1" value={home} onChange={event => setHome(event.target.value)} /></label>
        <label>Away projected goals <input type="number" min="0" max="20" step="0.1" value={away} onChange={event => setAway(event.target.value)} /></label>
        <label>Bookmaker decimal odds <input type="number" min="1.01" step="0.01" value={odds} onChange={event => setOdds(event.target.value)} /></label>
      </div>
      <div aria-live="polite">{illustration ? <>
        <p>Under 1.5: {percent(illustration.probability)} · Two or more: {percent(illustration.twoPlus)} · Fair odds: {illustration.fairOdds.toFixed(2)} · Grade {illustration.grade} · Theoretical EV: {percent(illustration.ev)}</p>
        <p>0–0: {percent(illustration.zero)} · 1–0: {percent(illustration.homeOnly)} · 0–1: {percent(illustration.awayOnly)} · Exactly one goal: {percent(illustration.exactlyOne)}</p>
      </> : <p>Enter both projected goals between 0 and 20.</p>}</div>
      <p>At 1.2 projected goals, the Poisson chance is only 66.3%. At a calibrated 75%, odds of 1.50 give +12.5% theoretical EV; 1.25 gives −6.25%. These are calculations, not observed returns.</p>
    </details>
  </section>
}
