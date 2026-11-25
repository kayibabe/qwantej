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
  return <section className="rounded-xl border border-slate-200 bg-white overflow-hidden" aria-label={`${config.title} qualification`}>
    <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 px-4 py-3">
      <h3 className="text-base font-bold tracking-tight text-slate-900">{config.title} qualification</h3>
      <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-sm font-semibold text-slate-600">Provisional screening rules</span>
    </div>
    <div className="space-y-4 px-4 py-4 text-base leading-relaxed text-slate-700">
      <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"><strong className="text-slate-900">Winning scores:</strong> {config.goals} in regulation time plus stoppage time. Extra time and penalties do not count.</p>
      {assessment ? <>
        <p><strong className="text-slate-900">{assessment.status} · Grade {assessment.grade ?? 'unavailable'} · {assessment.selection_pool} pool</strong> · {assessment.calibrated ? 'Calibrated estimate' : assessment.shared_goals_forecast?.calibrated ? 'Shared calibrated forecast (market gates remain)' : assessment.probability_source === 'shared_goals_forecast' ? 'Shared Poisson forecast (not calibrated)' : 'Unvalidated estimate'}: <span className="font-mono tabular-nums">{assessment.probability == null ? 'Unavailable' : `${(assessment.probability * 100).toFixed(1)}%`}</span></p>
        <p>Fair odds: <span className="font-mono tabular-nums">{assessment.fair_odds?.toFixed(2) ?? 'Unavailable'}</span> · Estimated EV: <span className="font-mono tabular-nums">{assessment.expected_value == null ? 'Unavailable' : `${(assessment.expected_value * 100).toFixed(1)}%`}</span> · Recent sample: <span className="font-mono tabular-nums">{assessment.sample_sizes.home ?? 0}</span> home / <span className="font-mono tabular-nums">{assessment.sample_sizes.away ?? 0}</span> away matches.</p>
        <div className="overflow-x-auto rounded-lg border border-slate-200"><table className="w-full min-w-[640px] border-collapse text-left text-sm"><thead className="border-b border-slate-200 bg-slate-50 text-sm uppercase tracking-wide text-slate-600"><tr><th className="px-3 py-2">Indicator</th><th className="px-3 py-2">Adjusted evidence</th><th className="px-3 py-2">Recent historical evidence</th><th className="px-3 py-2">Screen</th><th className="px-3 py-2">Role</th></tr></thead><tbody className="divide-y divide-slate-100">
          {assessment.checks.map(check => <tr key={check.key} className="hover:bg-slate-50/70"><td className="px-3 py-2 text-slate-700">{metricLabels[check.key] ?? check.key}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-900">{format(check.key, check.value)}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-700">{format(check.key, assessment.descriptive_metrics?.[check.key] ?? null)}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-700">{check.threshold == null ? 'Descriptive' : `≥ ${format(check.key, check.threshold)}`}</td><td className="px-3 py-2 text-slate-700">{check.required ? 'Core' : 'Supporting'}</td></tr>)}
        </tbody></table></div>
        {assessment.reasons.length > 0 && <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3"><summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Qualification blockers ({assessment.reasons.length})</summary><ul className="mt-2 list-disc space-y-1 pl-5 text-slate-700">{assessment.reasons.map(reason => <li key={reason}>{reason.replace(/^OVER\d+_/, '').replace(/_/g, ' ').toLowerCase()}</li>)}</ul></details>}
        {assessment.warnings.length > 0 && <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3"><summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Supporting indicators to review ({assessment.warnings.length})</summary><ul className="mt-2 list-disc space-y-1 pl-5 text-slate-700">{assessment.warnings.map(reason => <li key={reason}>{reason.replace(/^OVER\d+_/, '').replace(/_/g, ' ').toLowerCase()}</li>)}</ul></details>}
        <TotalGoalsBaseline distribution={assessment.shared_distribution} />
      </> : <p>No qualification evidence was captured. This selection cannot qualify under the new policy.</p>}
      <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3">
        <summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Market rules and thresholds</summary>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-slate-600">
          <li>{config.grade}. Current primary pool: A/A+. Over 2.5 grade B can be considered only with verified strong supporting value. Every qualified selection still requires positive expected value, market-specific calibration, context and risk review. Zero qualifiers is valid.</li>
          <li>Preferred projected total: {config.preferred.toFixed(1)} goals. Recent historical values are descriptive venue splits; they are not opponent-adjusted projections. These grade cutoffs and screening values are hypotheses for calibration and unseen-fixture validation, not validated hit-rate guarantees. {assessment?.poisson_baseline != null ? `The independent-Poisson baseline is ${(assessment.poisson_baseline * 100).toFixed(1)}%; it is diagnostic only.` : 'Poisson estimates are diagnostic only and cannot qualify a selection.'}</li>
        </ul>
      </details>
    </div>
  </section>
}
