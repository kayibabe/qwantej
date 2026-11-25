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

const inputClass = 'w-full h-11 px-3 text-sm font-mono font-semibold text-slate-900 bg-white border border-slate-200 rounded-lg tabular-nums placeholder:font-sans placeholder:font-normal placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-emerald-700/20 focus:border-emerald-700'

export default function Under05Qualification({ assessment }: { assessment?: Assessment | null }) {
  const [home, setHome] = useState('0.50')
  const [away, setAway] = useState('0.50')
  const [odds, setOdds] = useState('3.50')
  const illustration = under05Illustration(home, away, odds)
  return <section className="rounded-xl border border-slate-200 bg-white overflow-hidden" aria-label="Under 0.5 qualification">
    <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 px-4 py-3">
      <h3 className="text-base font-bold tracking-tight text-slate-900">Under 0.5 qualification</h3>
      <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-sm font-semibold text-slate-600">Provisional · exact 0–0 calibration</span>
    </div>
    <div className="space-y-4 px-4 py-4 text-base leading-relaxed text-slate-700">
      <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"><strong className="text-slate-900">Winning scores:</strong> Only 0–0 wins after 90 minutes plus stoppage time. Any goal loses. Extra time and shootouts do not count.</p>
      {assessment ? <>
        <p><strong className="text-slate-900">{assessment.status} · Probability grade {assessment.grade ?? 'unavailable'} · {assessment.selection_pool} pool</strong> · {assessment.calibrated ? 'Calibrated estimate' : assessment.shared_goals_forecast?.calibrated ? 'Shared calibrated forecast (market gates remain)' : assessment.probability_source === 'shared_goals_forecast' ? 'Shared Poisson forecast (not calibrated)' : 'Unvalidated estimate'}</p>
        <p>0–0: <span className="font-mono tabular-nums">{percent(assessment.probability)}</span> · At least one goal: <span className="font-mono tabular-nums">{percent(assessment.one_plus_probability)}</span> · Fair odds: <span className="font-mono tabular-nums">{assessment.fair_odds?.toFixed(2) ?? 'Unavailable'}</span> · EV: <span className="font-mono tabular-nums">{percent(assessment.expected_value)}</span></p>
        <p>Bookmaker implied probability: <span className="font-mono tabular-nums">{percent(assessment.implied_probability)}</span> · Model edge: <span className="font-mono tabular-nums">{points(assessment.edge)}</span>. Implied probability includes bookmaker margin.</p>
        <p>Stress test: reduce probability by <span className="font-mono tabular-nums">{points(assessment.probability_haircut)}</span> → <span className="font-mono tabular-nums">{percent(assessment.stressed_probability)}</span>; stressed EV: <span className="font-mono tabular-nums">{percent(assessment.stressed_expected_value)}</span>. Both ordinary and stressed EV must be strictly positive.</p>
        <p>Recent sample: <span className="font-mono tabular-nums">{assessment.sample_sizes.home ?? 0}</span> home / <span className="font-mono tabular-nums">{assessment.sample_sizes.away ?? 0}</span> away. Require 10–15 comparable matches per team, longer-term context and sample-size adjustment.</p>
        <div className="overflow-x-auto rounded-lg border border-slate-200"><table className="w-full min-w-[640px] border-collapse text-left text-sm"><thead className="border-b border-slate-200 bg-slate-50 text-sm uppercase tracking-wide text-slate-600"><tr><th className="px-3 py-2">Indicator</th><th className="px-3 py-2">Evidence</th><th className="px-3 py-2">Preferred threshold</th><th className="px-3 py-2">Advisory screen</th></tr></thead><tbody className="divide-y divide-slate-100">
          {assessment.checks.map(check => <tr key={check.key} className="hover:bg-slate-50/70"><td className="px-3 py-2 text-slate-700">{labels[check.key] ?? check.key}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-900">{format(check.key, check.value)}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-700">{check.direction === 'max' ? '≤' : '≥'} {format(check.key, check.threshold)}</td><td className="px-3 py-2 text-slate-700">{check.status}</td></tr>)}
        </tbody></table></div>
        {assessment.reasons.length > 0 && <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3"><summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Qualification blockers ({assessment.reasons.length})</summary><ul className="mt-2 list-disc space-y-1 pl-5 text-slate-700">{assessment.reasons.map(item => <li key={item}>{reason(item)}</li>)}</ul></details>}
        {assessment.warnings.length > 0 && <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3"><summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Supporting indicators to review ({assessment.warnings.length})</summary><ul className="mt-2 list-disc space-y-1 pl-5 text-slate-700">{assessment.warnings.map(item => <li key={item}>{reason(item)}</li>)}</ul></details>}
        <TotalGoalsBaseline distribution={assessment.shared_goals_forecast} />
      </> : <p>No qualification evidence was captured. This selection cannot qualify under the new policy.</p>}
      <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3">
        <summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Market rules and thresholds</summary>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-slate-600">
          <li>A+ ≥40%; A ≥30%; B ≥22% conditional; C ≥15% generally reject; D below 15% reject. A/A+ are the primary shortlist, not betting guarantees. An A+ estimate of 40% still means a 60% loss probability.</li>
          <li>Projected goals ≤1.2, ideally ≤0.9. The indicators are preferences, not an all-pass checklist: 0.8–0.2 can remain suitable. A recent 0–0 rate is not the next match’s probability, and head-to-head history is not a major selection factor.</li>
          <li>Require measured low chance creation, strong defences, both teams’ clean-sheet evidence and sustained low-event tactics. Review attacking favourites, absences, finishing slumps, early goals, penalties, set pieces, transitions, unsustainable goalkeeping and attacking tactical risks. No daily minimum is forced.</li>
        </ul>
      </details>
      <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3">
        <summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Illustrative Poisson calculator</summary>
        <div className="mt-3 space-y-3">
          <p className="text-base text-slate-700">Independent-Poisson illustration only, not a calibrated live signal. Inputs do not change the selection or qualification decision.</p>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="block text-sm font-medium text-slate-600">Home projected goals <input className={inputClass} type="number" min="0" max="20" step="0.05" value={home} onChange={event => setHome(event.target.value)} /></label>
            <label className="block text-sm font-medium text-slate-600">Away projected goals <input className={inputClass} type="number" min="0" max="20" step="0.05" value={away} onChange={event => setAway(event.target.value)} /></label>
            <label className="block text-sm font-medium text-slate-600">Bookmaker decimal odds <input className={inputClass} type="number" min="1.01" step="0.01" value={odds} onChange={event => setOdds(event.target.value)} /></label>
          </div>
          <div aria-live="polite" className="text-base text-slate-700">{illustration ? <>
            <p>0–0: <span className="font-mono tabular-nums">{percent(illustration.probability)}</span> · At least one goal: <span className="font-mono tabular-nums">{percent(illustration.onePlus)}</span> · Fair odds: <span className="font-mono tabular-nums">{illustration.fairOdds.toFixed(2)}</span> · Grade {illustration.grade}</p>
            <p>Theoretical EV: <span className="font-mono tabular-nums">{percent(illustration.ev)}</span> · Bookmaker implied: <span className="font-mono tabular-nums">{percent(illustration.implied)}</span> · Edge: <span className="font-mono tabular-nums">{points(illustration.edge)}</span> · Stressed EV: <span className="font-mono tabular-nums">{percent(illustration.stressedEv)}</span></p>
          </> : <p>Enter both projected goals between 0 and 20.</p>}</div>
          <p className="text-sm text-slate-600">The five-percentage-point reduction is an initial stress scenario, not a validated uncertainty bound. At 1.2 projected goals, at least one goal has a 69.9% Poisson probability. A 50% chance of 0–0 needs total projected goals near 0.69 or lower.</p>
          <p className="text-sm text-slate-600">At 35%, odds of 3.20 give +12% ordinary EV but −4% after the five-point reduction, so this price fails the robustness gate.</p>
        </div>
      </details>
    </div>
  </section>
}
