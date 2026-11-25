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
const inputClass = 'w-full h-11 px-3 text-sm font-mono font-semibold text-slate-900 bg-white border border-slate-200 rounded-lg tabular-nums placeholder:font-sans placeholder:font-normal placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-emerald-700/20 focus:border-emerald-700'

export default function Under35Qualification({ assessment }: { assessment?: Assessment | null }) {
  const [home, setHome] = useState('1.2')
  const [away, setAway] = useState('1.0')
  const [odds, setOdds] = useState('1.35')
  const illustration = under35Illustration(home, away, odds)
  return <section className="rounded-xl border border-slate-200 bg-white overflow-hidden" aria-label="Under 3.5 qualification">
    <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 px-4 py-3">
      <h3 className="text-base font-bold tracking-tight text-slate-900">Under 3.5 qualification</h3>
      <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-sm font-semibold text-slate-600">Provisional · separate market calibration</span>
    </div>
    <div className="space-y-4 px-4 py-4 text-base leading-relaxed text-slate-700">
      <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"><strong className="text-slate-900">Winning scores:</strong> Zero to three total goals in 90 minutes plus stoppage time. Extra time and penalties do not count. 2–1, 1–2, 3–0 and 0–3 win; 2–2, 3–1 and 4–0 lose.</p>
      {assessment ? <>
        <p><strong className="text-slate-900">{assessment.status} · Probability grade {assessment.grade ?? 'unavailable'} · {assessment.selection_pool} pool</strong> · {assessment.calibrated ? 'Calibrated estimate' : assessment.shared_goals_forecast?.calibrated ? 'Shared calibrated forecast (market gates remain)' : assessment.probability_source === 'shared_goals_forecast' ? 'Shared Poisson forecast (not calibrated)' : 'Unvalidated estimate'}</p>
        <p>Under 3.5: <span className="font-mono tabular-nums">{percent(assessment.probability)}</span> · Four or more goals: <span className="font-mono tabular-nums">{percent(assessment.four_plus_probability)}</span> · Fair odds: <span className="font-mono tabular-nums">{assessment.fair_odds?.toFixed(2) ?? 'Unavailable'}</span> · Estimated EV: <span className="font-mono tabular-nums">{percent(assessment.expected_value)}</span></p>
        <p>Recent sample: <span className="font-mono tabular-nums">{assessment.sample_sizes.home ?? 0}</span> home / <span className="font-mono tabular-nums">{assessment.sample_sizes.away ?? 0}</span> away matches. Require 8–12 per team plus longer-term league context and sample-size shrinkage.</p>
        <div className="overflow-x-auto rounded-lg border border-slate-200"><table className="w-full min-w-[640px] border-collapse text-left text-sm"><thead className="border-b border-slate-200 bg-slate-50 text-sm uppercase tracking-wide text-slate-600"><tr><th className="px-3 py-2">Indicator</th><th className="px-3 py-2">Evidence</th><th className="px-3 py-2">Preferred threshold</th><th className="px-3 py-2">Screen</th></tr></thead><tbody className="divide-y divide-slate-100">
          {assessment.checks.map(check => <tr key={check.key} className="hover:bg-slate-50/70"><td className="px-3 py-2 text-slate-700">{labels[check.key] ?? check.key}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-900">{format(check.key, check.value)}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-700">{check.direction === 'max' ? '≤' : '≥'} {format(check.key, check.threshold)}</td><td className="px-3 py-2 text-slate-700">{check.status} · {check.required ? 'core' : 'advisory'}</td></tr>)}
        </tbody></table></div>
        {assessment.reasons.length > 0 && <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3"><summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Qualification blockers ({assessment.reasons.length})</summary><ul className="mt-2 list-disc space-y-1 pl-5 text-slate-700">{assessment.reasons.map(item => <li key={item}>{reason(item)}</li>)}</ul></details>}
        {assessment.warnings.length > 0 && <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3"><summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Supporting indicators to review ({assessment.warnings.length})</summary><ul className="mt-2 list-disc space-y-1 pl-5 text-slate-700">{assessment.warnings.map(item => <li key={item}>{reason(item)}</li>)}</ul></details>}
        <TotalGoalsBaseline distribution={assessment.shared_goals_forecast} />
      </> : <p>No qualification evidence was captured. This selection cannot qualify under the new policy.</p>}
      <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3">
        <summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Market rules and thresholds</summary>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-slate-600">
          <li>A+ ≥90%; A ≥82%; B ≥75% only with strong supporting evidence and an attractive-price review; C ≥65% normally excluded; D below 65% rejected. A/A+ form the primary pool. All releases require positive EV and validated Under 3.5 calibration.</li>
          <li>Projected goals ≤2.5 is the initial core screen, ideally ≤2.2. Other indicators support a documented review rather than acting as overlapping hard rules. BTTS is optional; no additive indicator score or forced daily minimum is used.</li>
          <li>Prioritise disciplined defences, moderate attacks, favourites with defensive control and cautious tactical profiles. Review big chances, dominant attacks against weak defences, absences, fortunate finishing, dangerous transitions, lineup changes and unexplained market disagreement. A favourite scoring four goals is still a losing outcome.</li>
        </ul>
      </details>
      <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3">
        <summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Illustrative Poisson calculator</summary>
        <div className="mt-3 space-y-3">
          <p className="text-base text-slate-700">Independent-Poisson illustration only, without lineups, correlated scoring, uncertainty or live prices. Inputs do not change the selection or qualification decision.</p>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="block text-sm font-medium text-slate-600">Home projected goals <input className={inputClass} type="number" min="0" max="20" step="0.1" value={home} onChange={event => setHome(event.target.value)} /></label>
            <label className="block text-sm font-medium text-slate-600">Away projected goals <input className={inputClass} type="number" min="0" max="20" step="0.1" value={away} onChange={event => setAway(event.target.value)} /></label>
            <label className="block text-sm font-medium text-slate-600">Bookmaker decimal odds <input className={inputClass} type="number" min="1.01" step="0.01" value={odds} onChange={event => setOdds(event.target.value)} /></label>
          </div>
          <div aria-live="polite" className="text-base text-slate-700">{illustration ? <p>Under 3.5: <span className="font-mono tabular-nums">{percent(illustration.probability)}</span> · Four or more: <span className="font-mono tabular-nums">{percent(illustration.fourPlus)}</span> · Fair odds: <span className="font-mono tabular-nums">{illustration.fairOdds.toFixed(2)}</span> · Grade {illustration.grade} · Theoretical EV: <span className="font-mono tabular-nums">{percent(illustration.ev)}</span></p> : <p>Enter both projected goals between 0 and 20.</p>}</div>
          <p className="text-sm text-slate-600">At 85%, odds of 1.25 give +6.25% theoretical EV; 1.10 gives −6.5%. A high probability alone is not a betting recommendation.</p>
        </div>
      </details>
    </div>
  </section>
}
