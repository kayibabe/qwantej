import type { Over45Qualification as Assessment } from '../lib/api'
import TotalGoalsBaseline from './TotalGoalsBaseline'

const labels: Record<string, string> = {
  projected_xg: 'Projected match xG', combined_scored: 'Combined goals scored / match',
  combined_conceded: 'Combined goals conceded / match', over25_frequency: 'Over 2.5 frequency',
  over35_frequency: 'Over 3.5 frequency', over45_frequency: 'Over 4.5 frequency',
  combined_shots_on_target: 'Combined shots on target', btts_frequency: 'BTTS (optional)',
  expected_first_half_goals: 'Expected first-half goals',
  combined_big_chances: 'Combined big chances (supporting)',
  max_team_projected_goals: 'Higher team projection (supporting)',
  first_half_over15_frequency: 'First-half Over 1.5 frequency',
}
const display = (key: string, value: number | null) => value == null ? 'Unavailable' :
  key.endsWith('frequency') ? `${(value * 100).toFixed(0)}%` : value.toFixed(1)

export default function Over45Qualification({ assessment }: { assessment?: Assessment | null }) {
  return <section className="explainability-card" aria-label="Over 4.5 qualification">
    <div className="evidence-title"><h3>Over 4.5 qualification</h3><span>Provisional screening rules</span></div>
    <p>Five or more goals in 90 minutes plus stoppage time. Extra time and penalties do not count. 3–2, 4–1 and 5–0 all win; BTTS is optional.</p>
    {assessment ? <>
      <p><strong>{assessment.status} · Probability grade {assessment.grade ?? 'unavailable'}</strong> · {assessment.calibrated ? 'Calibrated estimate' : assessment.shared_goals_forecast?.calibrated ? 'Shared calibrated forecast (market gates remain)' : assessment.probability_source === 'shared_goals_forecast' ? 'Shared Poisson forecast (not calibrated)' : 'Unvalidated estimate'}: {assessment.probability == null ? 'Unavailable' : `${(assessment.probability * 100).toFixed(1)}%`}</p>
      <p>Fair odds: {assessment.fair_odds?.toFixed(2) ?? 'Unavailable'} · Estimated EV: {assessment.expected_value == null ? 'Unavailable' : `${(assessment.expected_value * 100).toFixed(1)}%`} · Recent sample: {assessment.sample_sizes.home ?? 0} home / {assessment.sample_sizes.away ?? 0} away matches (8–12 required per team).</p>
      <div className="table-wrap"><table><thead><tr><th>Indicator</th><th>Observed / projected</th><th>Preferred minimum</th><th>Screen</th></tr></thead><tbody>
        {assessment.checks.map(check => <tr key={check.key}><td>{labels[check.key] ?? check.key}</td><td>{display(check.key, check.value)}</td><td>{display(check.key, check.threshold)}</td><td>{check.status}{!check.required ? ' · optional' : ''}</td></tr>)}
      </tbody></table></div>
      {assessment.reasons.length > 0 && <ul>{assessment.reasons.map(reason => <li key={reason}>{reason.replace(/^OVER45_/, '').replace(/_/g, ' ').toLowerCase()}</li>)}</ul>}
      {(assessment.warnings ?? []).length > 0 && <details><summary>Supporting indicators to review ({assessment.warnings?.length})</summary><ul>{assessment.warnings?.map(reason => <li key={reason}>{reason.replace(/^OVER45_/, '').replace(/_/g, ' ').toLowerCase()}</li>)}</ul></details>}
      <TotalGoalsBaseline distribution={assessment.shared_distribution} />
    </> : <p>No qualification evidence was captured for this selection. It cannot qualify under the new policy.</p>}
    <p>A+ ≥45%; A ≥35%; B ≥25% with positive value; C ≥15% normally excluded; D below 15% rejected. These grades are separate from Q-score. Even A+ can be below a 50% chance.</p>
    <p>Prioritise open attacking matches, a dominant attack against a weak defence, and high-tempo transitions. Tactical, opponent-strength and lineup evidence must be reviewed; these profiles are not inferred from BTTS.</p>
    <p>A projected total of 3.8 gives about 33% for five or more goals under Poisson. Indicators are checked individually, not added into a score. Missing evidence, unvalidated calibration or non-positive value means no qualification. Zero qualifiers is a valid result.</p>
  </section>
}
