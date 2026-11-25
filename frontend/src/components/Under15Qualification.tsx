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
const inputClass = 'w-full h-11 px-3 text-sm font-mono font-semibold text-slate-900 bg-white border border-slate-200 rounded-lg tabular-nums placeholder:font-sans placeholder:font-normal placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-emerald-700/20 focus:border-emerald-700'

export default function Under15Qualification({ assessment }: { assessment?: Assessment | null }) {
  const [home, setHome] = useState('0.5')
  const [away, setAway] = useState('0.5')
  const [odds, setOdds] = useState('1.65')
  const illustration = under15Illustration(home, away, odds)
  return <section className="rounded-xl border border-slate-200 bg-white overflow-hidden" aria-label="Under 1.5 qualification">
    <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 px-4 py-3">
      <h3 className="text-base font-bold tracking-tight text-slate-900">Under 1.5 qualification</h3>
      <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-sm font-semibold text-slate-600">Provisional · separate low-score calibration</span>
    </div>
    <div className="space-y-4 px-4 py-4 text-base leading-relaxed text-slate-700">
      <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"><strong className="text-slate-900">Winning scores:</strong> Only 0–0, 1–0 and 0–1 win in 90 minutes plus stoppage time. 1–1, 2–0, 0–2 and every other two-or-more-goal score lose. Extra time and penalties do not count.</p>
      {assessment ? <>
        <p><strong className="text-slate-900">{assessment.status} · Probability grade {assessment.grade ?? 'unavailable'} · {assessment.selection_pool} pool</strong> · {assessment.calibrated ? 'Calibrated estimate' : assessment.shared_goals_forecast?.calibrated ? 'Shared calibrated forecast (market gates remain)' : assessment.probability_source === 'shared_goals_forecast' ? 'Shared Poisson forecast (not calibrated)' : 'Unvalidated estimate'}</p>
        <p>Under 1.5: <span className="font-mono tabular-nums">{percent(assessment.probability)}</span> · Two or more goals: <span className="font-mono tabular-nums">{percent(assessment.two_plus_probability)}</span> · Fair odds: <span className="font-mono tabular-nums">{assessment.fair_odds?.toFixed(2) ?? 'Unavailable'}</span> · Estimated EV: <span className="font-mono tabular-nums">{percent(assessment.expected_value)}</span></p>
        {assessment.low_score_model && <p>Uncalibrated Poisson/Dixon–Coles component: 0–0 <span className="font-mono tabular-nums">{percent(assessment.low_score_model.zero_goals)}</span> · Exactly one goal <span className="font-mono tabular-nums">{percent(assessment.low_score_model.exactly_one_goal)}</span>. These are separate from the ensemble estimate above.</p>}
        <p>Recent sample: <span className="font-mono tabular-nums">{assessment.sample_sizes.home ?? 0}</span> home / <span className="font-mono tabular-nums">{assessment.sample_sizes.away ?? 0}</span> away. Require 8–12 comparable recent games per team, longer-term data and league shrinkage.</p>
        <div className="overflow-x-auto rounded-lg border border-slate-200"><table className="w-full min-w-[640px] border-collapse text-left text-sm"><thead className="border-b border-slate-200 bg-slate-50 text-sm uppercase tracking-wide text-slate-600"><tr><th className="px-3 py-2">Indicator</th><th className="px-3 py-2">Evidence</th><th className="px-3 py-2">Threshold</th><th className="px-3 py-2">Screen</th></tr></thead><tbody className="divide-y divide-slate-100">
          {assessment.checks.map(check => <tr key={check.key} className="hover:bg-slate-50/70"><td className="px-3 py-2 text-slate-700">{labels[check.key] ?? check.key}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-900">{format(check.key, check.value)}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-700">{check.direction === 'max' ? '≤' : '≥'} {format(check.key, check.threshold)}</td><td className="px-3 py-2 text-slate-700">{check.status} · {check.required ? 'required' : 'advisory'}</td></tr>)}
        </tbody></table></div>
        {assessment.reasons.length > 0 && <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3"><summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Qualification blockers ({assessment.reasons.length})</summary><ul className="mt-2 list-disc space-y-1 pl-5 text-slate-700">{assessment.reasons.map(item => <li key={item}>{reason(item)}</li>)}</ul></details>}
        {assessment.warnings.length > 0 && <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3"><summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Supporting indicators to review ({assessment.warnings.length})</summary><ul className="mt-2 list-disc space-y-1 pl-5 text-slate-700">{assessment.warnings.map(item => <li key={item}>{reason(item)}</li>)}</ul></details>}
        <TotalGoalsBaseline distribution={assessment.shared_goals_forecast} />
      </> : <p>No qualification evidence was captured. This selection cannot qualify under the new policy.</p>}
      <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3">
        <summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Market rules and thresholds</summary>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-slate-600">
          <li>A+ ≥80%; A ≥70%; B ≥60% only with a compelling-value review; C ≥45% generally excluded; D below 45% rejected. A/A+ form the primary pool. Every release requires positive EV, calibrated probabilities and verified context.</li>
          <li>Combined projected goals ≤1.2, preferably ≤1.0 and ideally ≤0.9. The individual 0.7 home and 0.6 away limits are advisory: 0.9–0.2 may still pass the combined screen.</li>
          <li>Prioritise low chance creation, compact defences and measured low tempo. A defensive favourite must also have a low scoring projection: 2–0 loses. Review early goals, missing defenders or goalkeepers, pressing, transitions, weak-opponent samples, market disagreement and aggressive lineups. Penalties, red cards and tactical surprises remain uncertain. No daily minimum is forced.</li>
        </ul>
      </details>
      <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3">
        <summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Illustrative Poisson calculator</summary>
        <div className="mt-3 space-y-3">
          <p className="text-base text-slate-700">Independent-Poisson illustration only, not a calibrated live signal. Inputs do not change the selection or qualification decision and do not capture uncertainty in projected goals.</p>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="block text-sm font-medium text-slate-600">Home projected goals <input className={inputClass} type="number" min="0" max="20" step="0.1" value={home} onChange={event => setHome(event.target.value)} /></label>
            <label className="block text-sm font-medium text-slate-600">Away projected goals <input className={inputClass} type="number" min="0" max="20" step="0.1" value={away} onChange={event => setAway(event.target.value)} /></label>
            <label className="block text-sm font-medium text-slate-600">Bookmaker decimal odds <input className={inputClass} type="number" min="1.01" step="0.01" value={odds} onChange={event => setOdds(event.target.value)} /></label>
          </div>
          <div aria-live="polite" className="text-base text-slate-700">{illustration ? <>
            <p>Under 1.5: <span className="font-mono tabular-nums">{percent(illustration.probability)}</span> · Two or more: <span className="font-mono tabular-nums">{percent(illustration.twoPlus)}</span> · Fair odds: <span className="font-mono tabular-nums">{illustration.fairOdds.toFixed(2)}</span> · Grade {illustration.grade} · Theoretical EV: <span className="font-mono tabular-nums">{percent(illustration.ev)}</span></p>
            <p>0–0: <span className="font-mono tabular-nums">{percent(illustration.zero)}</span> · 1–0: <span className="font-mono tabular-nums">{percent(illustration.homeOnly)}</span> · 0–1: <span className="font-mono tabular-nums">{percent(illustration.awayOnly)}</span> · Exactly one goal: <span className="font-mono tabular-nums">{percent(illustration.exactlyOne)}</span></p>
          </> : <p>Enter both projected goals between 0 and 20.</p>}</div>
          <p className="text-sm text-slate-600">At 1.2 projected goals, the Poisson chance is only 66.3%. At a calibrated 75%, odds of 1.50 give +12.5% theoretical EV; 1.25 gives −6.25%. These are calculations, not observed returns.</p>
        </div>
      </details>
    </div>
  </section>
}
