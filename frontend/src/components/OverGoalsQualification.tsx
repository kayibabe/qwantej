import type { OverGoalsQualification as Assessment } from '../lib/api'
import TotalGoalsBaseline from './TotalGoalsBaseline'

const settings = {
  'over_1.5': { title: 'Over 1.5', goals: 'Two or more goals', grade: 'A+ ≥95% · A ≥90% · B ≥85%', preferred: 3.2 },
  'over_2.5': { title: 'Over 2.5', goals: 'Three or more goals', grade: 'A+ ≥80% · A ≥70% · B ≥60%', preferred: 3.8 },
  'over_3.5': { title: 'Over 3.5', goals: 'Four or more goals', grade: 'A+ ≥65% · A ≥55% · B ≥45%', preferred: 4.2 },
} as const

type Market = keyof typeof settings
const metricLabels: Record<string, string> = {
  projected_goals: 'Projected match goals', over15_frequency: 'Historical Over 1.5',
  over25_frequency: 'Historical Over 2.5', over35_frequency: 'Historical Over 3.5',
  over45_frequency: 'Historical Over 4.5', combined_shots_on_target: 'Combined shots on target',
  combined_big_chances: 'Combined big chances', max_team_projected_goals: 'Higher team projection',
  historical_goals_profile: 'Combined historical goals', first_half_over05_frequency: 'First-half Over 0.5',
  first_half_over15_frequency: 'First-half Over 1.5', btts_frequency: 'BTTS Yes (optional)',
}
const format = (key: string, value: number | null) => value == null ? 'Unavailable' :
  key.endsWith('frequency') ? `${(value * 100).toFixed(0)}%` : value.toFixed(2)

export default function OverGoalsQualification({ market, assessment }: { market: Market; assessment?: Assessment | null }) {
  const config = settings[market]
  return <section className="explainability-card" aria-label={`${config.title} qualification`}>
    <div className="evidence-title"><h3>{config.title} qualification</h3><span>Provisional screening rules</span></div>
    <p>{config.goals} in regulation time plus stoppage time. Extra time and penalties do not count.</p>
    {assessment ? <>
      <p><strong>{assessment.status} · Grade {assessment.grade ?? 'unavailable'} · {assessment.selection_pool} pool</strong> · {assessment.calibrated ? 'Calibrated estimate' : assessment.shared_goals_forecast?.calibrated ? 'Shared calibrated forecast (market gates remain)' : assessment.probability_source === 'shared_goals_forecast' ? 'Shared Poisson forecast (not calibrated)' : 'Unvalidated estimate'}: {assessment.probability == null ? 'Unavailable' : `${(assessment.probability * 100).toFixed(1)}%`}</p>
      <p>Fair odds: {assessment.fair_odds?.toFixed(2) ?? 'Unavailable'} · Estimated EV: {assessment.expected_value == null ? 'Unavailable' : `${(assessment.expected_value * 100).toFixed(1)}%`} · Recent sample: {assessment.sample_sizes.home ?? 0} home / {assessment.sample_sizes.away ?? 0} away matches.</p>
      <div className="table-wrap"><table><thead><tr><th>Indicator</th><th>Adjusted evidence</th><th>Recent historical evidence</th><th>Screen</th><th>Role</th></tr></thead><tbody>
        {assessment.checks.map(check => <tr key={check.key}><td>{metricLabels[check.key] ?? check.key}</td><td>{format(check.key, check.value)}</td><td>{format(check.key, assessment.descriptive_metrics?.[check.key] ?? null)}</td><td>{check.threshold == null ? 'Descriptive' : `≥ ${format(check.key, check.threshold)}`}</td><td>{check.required ? 'Core' : 'Supporting'}</td></tr>)}
      </tbody></table></div>
      {assessment.reasons.length > 0 && <details><summary>Qualification blockers ({assessment.reasons.length})</summary><ul>{assessment.reasons.map(reason => <li key={reason}>{reason.replace(/^OVER\d+_/, '').replace(/_/g, ' ').toLowerCase()}</li>)}</ul></details>}
      {assessment.warnings.length > 0 && <details><summary>Supporting indicators to review ({assessment.warnings.length})</summary><ul>{assessment.warnings.map(reason => <li key={reason}>{reason.replace(/^OVER\d+_/, '').replace(/_/g, ' ').toLowerCase()}</li>)}</ul></details>}
      <TotalGoalsBaseline distribution={assessment.shared_distribution} />
    </> : <p>No qualification evidence was captured. This selection cannot qualify under the new policy.</p>}
    <p>{config.grade}. Current primary pool: A/A+. Over 2.5 grade B can be considered only with verified strong supporting value. Every qualified selection still requires positive expected value, market-specific calibration, context and risk review. Zero qualifiers is valid.</p>
    <p>Preferred projected total: {config.preferred.toFixed(1)} goals. Recent historical values are descriptive venue splits; they are not opponent-adjusted projections. These grade cutoffs and screening values are hypotheses for calibration and unseen-fixture validation, not validated hit-rate guarantees. {assessment?.poisson_baseline != null ? `The independent-Poisson baseline is ${(assessment.poisson_baseline * 100).toFixed(1)}%; it is diagnostic only.` : 'Poisson estimates are diagnostic only and cannot qualify a selection.'}</p>
  </section>
}
