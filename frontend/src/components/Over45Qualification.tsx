import { formatSentence } from '../lib/api'
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
  return <section className="rounded-xl border border-slate-200 bg-white overflow-hidden" aria-label="Over 4.5 qualification">
    <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 px-4 py-3">
      <h3 className="text-base font-bold tracking-tight text-slate-900">Over 4.5 qualification</h3>
      <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-sm font-semibold text-slate-600">Provisional screening rules</span>
    </div>
    <div className="space-y-4 px-4 py-4 text-base leading-relaxed text-slate-700">
      <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"><strong className="text-slate-900">Winning scores:</strong> Five or more goals in 90 minutes plus stoppage time. Extra time and penalties do not count. 3–2, 4–1 and 5–0 all win; BTTS is optional.</p>
      {assessment ? <>
        <p><strong className="text-slate-900">{formatSentence(assessment.status)} · Probability grade {assessment.grade ?? 'unavailable'}</strong> · {assessment.calibrated ? 'Calibrated estimate' : assessment.shared_goals_forecast?.calibrated ? 'Shared calibrated forecast (market gates remain)' : assessment.probability_source === 'shared_goals_forecast' ? 'Shared Poisson forecast (not calibrated)' : 'Unvalidated estimate'}: <span className="font-mono tabular-nums">{assessment.probability == null ? 'Unavailable' : `${(assessment.probability * 100).toFixed(1)}%`}</span></p>
        <p>Fair odds: <span className="font-mono tabular-nums">{assessment.fair_odds?.toFixed(2) ?? 'Unavailable'}</span> · Estimated EV: <span className="font-mono tabular-nums">{assessment.expected_value == null ? 'Unavailable' : `${(assessment.expected_value * 100).toFixed(1)}%`}</span> · Recent sample: <span className="font-mono tabular-nums">{assessment.sample_sizes.home ?? 0}</span> home / <span className="font-mono tabular-nums">{assessment.sample_sizes.away ?? 0}</span> away matches (8–12 required per team).</p>
        <div className="overflow-x-auto rounded-lg border border-slate-200"><table className="w-full min-w-[640px] border-collapse text-left text-sm"><thead className="border-b border-slate-200 bg-slate-50 text-sm text-slate-600"><tr><th className="px-3 py-2">Indicator</th><th className="px-3 py-2">Observed / projected</th><th className="px-3 py-2">Preferred minimum</th><th className="px-3 py-2">Screen</th></tr></thead><tbody className="divide-y divide-slate-100">
          {assessment.checks.map(check => <tr key={check.key} className="hover:bg-slate-50/70"><td className="px-3 py-2 text-slate-700">{labels[check.key] ?? check.key}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-900">{display(check.key, check.value)}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-700">{display(check.key, check.threshold)}</td><td className="px-3 py-2 text-slate-700">{formatSentence(check.status)}{!check.required ? ' · optional' : ''}</td></tr>)}
        </tbody></table></div>
        {assessment.reasons.length > 0 && <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3"><summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Qualification blockers ({assessment.reasons.length})</summary><ul className="mt-2 list-disc space-y-1 pl-5 text-slate-700">{assessment.reasons.map(reason => <li key={reason}>{reason.replace(/^OVER45_/, '').replace(/_/g, ' ').toLowerCase()}</li>)}</ul></details>}
        {(assessment.warnings ?? []).length > 0 && <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3"><summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Supporting indicators to review ({assessment.warnings?.length})</summary><ul className="mt-2 list-disc space-y-1 pl-5 text-slate-700">{assessment.warnings?.map(reason => <li key={reason}>{reason.replace(/^OVER45_/, '').replace(/_/g, ' ').toLowerCase()}</li>)}</ul></details>}
        <TotalGoalsBaseline distribution={assessment.shared_distribution} />
      </> : <p>No qualification evidence was captured for this selection. It cannot qualify under the new policy.</p>}
      <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3">
        <summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Market rules and thresholds</summary>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-slate-600">
          <li>A+ ≥45%; A ≥35%; B ≥25% with positive value; C ≥15% normally excluded; D below 15% rejected. These grades are separate from Q-score. Even A+ can be below a 50% chance.</li>
          <li>Prioritise open attacking matches, a dominant attack against a weak defence, and high-tempo transitions. Tactical, opponent-strength and lineup evidence must be reviewed; these profiles are not inferred from BTTS.</li>
          <li>A projected total of 3.8 gives about 33% for five or more goals under Poisson. Indicators are checked individually, not added into a score. Missing evidence, unvalidated calibration or non-positive value means no qualification. Zero qualifiers is a valid result.</li>
        </ul>
      </details>
    </div>
  </section>
}
