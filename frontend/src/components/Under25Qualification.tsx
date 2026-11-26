import { useState } from 'react'
import { formatSentence } from '../lib/api'
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
const inputClass = 'w-full h-11 px-3 text-sm font-mono font-semibold text-slate-900 bg-white border border-slate-200 rounded-lg tabular-nums placeholder:font-sans placeholder:font-normal placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-emerald-700/20 focus:border-emerald-700'

export default function Under25Qualification({ assessment }: { assessment?: Assessment | null }) {
  const [home, setHome] = useState('0.9')
  const [away, setAway] = useState('0.8')
  const [odds, setOdds] = useState('1.55')
  const illustration = under25Illustration(home, away, odds)
  return <section className="rounded-xl border border-slate-200 bg-white overflow-hidden" aria-label="Under 2.5 qualification">
    <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 px-4 py-3">
      <h3 className="text-base font-bold tracking-tight text-slate-900">Under 2.5 qualification</h3>
      <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-sm font-semibold text-slate-600">Provisional · league validation required</span>
    </div>
    <div className="space-y-4 px-4 py-4 text-base leading-relaxed text-slate-700">
      <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"><strong className="text-slate-900">Winning scores:</strong> Zero, one or two total goals in 90 minutes plus stoppage time. Extra time and penalties do not count. 0–0, 1–0, 0–1, 1–1, 2–0 and 0–2 win; 2–1 and 3–0 lose.</p>
      {assessment ? <>
        <p><strong className="text-slate-900">{formatSentence(assessment.status)} · Probability grade {assessment.grade ?? 'unavailable'}</strong> · {assessment.calibrated ? 'Calibrated estimate' : assessment.shared_goals_forecast?.calibrated ? 'Shared calibrated forecast (market gates remain)' : assessment.probability_source === 'shared_goals_forecast' ? 'Shared Poisson forecast (not calibrated)' : 'Unvalidated estimate'}: <span className="font-mono tabular-nums">{assessment.probability == null ? 'Unavailable' : `${(assessment.probability * 100).toFixed(1)}%`}</span></p>
        <p>Fair odds: <span className="font-mono tabular-nums">{assessment.fair_odds?.toFixed(2) ?? 'Unavailable'}</span> · Estimated EV: <span className="font-mono tabular-nums">{assessment.expected_value == null ? 'Unavailable' : `${(assessment.expected_value * 100).toFixed(1)}%`}</span> · Recent sample: <span className="font-mono tabular-nums">{assessment.sample_sizes.home ?? 0}</span> home / <span className="font-mono tabular-nums">{assessment.sample_sizes.away ?? 0}</span> away (8–12 per team).</p>
        <div className="overflow-x-auto rounded-lg border border-slate-200"><table className="w-full min-w-[640px] border-collapse text-left text-sm"><thead className="border-b border-slate-200 bg-slate-50 text-sm text-slate-600"><tr><th className="px-3 py-2">Indicator</th><th className="px-3 py-2">Adjusted evidence</th><th className="px-3 py-2">Threshold</th><th className="px-3 py-2">Screen</th></tr></thead><tbody className="divide-y divide-slate-100">
          {assessment.checks.map(check => <tr key={check.key} className="hover:bg-slate-50/70"><td className="px-3 py-2 text-slate-700">{labels[check.key] ?? check.key}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-900">{format(check.key, check.value)}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-700">{check.direction === 'max' ? '≤' : '≥'} {format(check.key, check.threshold)}</td><td className="px-3 py-2 text-slate-700">{formatSentence(check.status)}</td></tr>)}
        </tbody></table></div>
        {assessment.reasons.length > 0 && <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3"><summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Qualification blockers ({assessment.reasons.length})</summary><ul className="mt-2 list-disc space-y-1 pl-5 text-slate-700">{assessment.reasons.map(reason => <li key={reason}>{reason.replace(/^UNDER25_/, '').replace(/_/g, ' ').toLowerCase()}</li>)}</ul></details>}
        <TotalGoalsBaseline distribution={assessment.shared_goals_forecast} />
      </> : <p>No qualification evidence was captured. This selection cannot qualify under the new policy.</p>}
      <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3">
        <summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Market rules and thresholds</summary>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-slate-600">
          <li>A+ ≥80%; A ≥72%; B ≥65% watch only; C ≥55% generally avoid; D below 55% reject. Primary selections require A/A+, validated calibration and positive EV. Preferred projected goals ≤1.8, ideally ≤1.7; the initial maximum is 2.0.</li>
          <li>Review defensive absences, chance quality and finishing slumps, attacking mismatches, open transitions, aggressive lineups, unexplained market disagreement and second-half escalation. Low recent scores alone are insufficient. No daily minimum is forced.</li>
        </ul>
      </details>
      <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3">
        <summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Illustrative Poisson calculator</summary>
        <div className="mt-3 space-y-3">
          <p className="text-base text-slate-700">Independent-Poisson illustration only. These inputs do not alter the selection, calibration or qualification decision.</p>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="block text-sm font-medium text-slate-600">Home projected goals <input className={inputClass} type="number" min="0" max="20" step="0.1" value={home} onChange={event => setHome(event.target.value)} /></label>
            <label className="block text-sm font-medium text-slate-600">Away projected goals <input className={inputClass} type="number" min="0" max="20" step="0.1" value={away} onChange={event => setAway(event.target.value)} /></label>
            <label className="block text-sm font-medium text-slate-600">Bookmaker decimal odds <input className={inputClass} type="number" min="1.01" step="0.01" value={odds} onChange={event => setOdds(event.target.value)} /></label>
          </div>
          <div aria-live="polite" className="text-base text-slate-700">{illustration ? <p>Under 2.5: <span className="font-mono tabular-nums">{(illustration.probability * 100).toFixed(1)}%</span> · Fair odds: <span className="font-mono tabular-nums">{illustration.fairOdds.toFixed(2)}</span> · Grade {illustration.grade} · Theoretical EV: <span className="font-mono tabular-nums">{illustration.ev == null ? 'Enter valid odds above 1' : `${illustration.ev > 0 ? '+' : ''}${(illustration.ev * 100).toFixed(1)}%`}</span></p> : <p>Enter both projected goals between 0 and 20.</p>}</div>
          <p className="text-sm text-slate-600">At 80%, fair odds are 1.25; a quote of 1.18 has negative expected value. Probability is not a betting recommendation.</p>
        </div>
      </details>
    </div>
  </section>
}
