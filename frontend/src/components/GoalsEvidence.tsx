import type { GoalsEvidence as Evidence, MatchIntelligencePrediction } from '../lib/api'

export default function GoalsEvidence({ current, prediction }: { current?: Evidence; prediction: MatchIntelligencePrediction | null }) {
  const evidence = prediction?.goals_evidence ?? current
  const model = prediction?.probability_model
  const metrics = evidence?.metrics ?? {}
  const labels: Record<string, string> = {
    projected_xg: 'Projected match xG', combined_scored: 'Combined goals scored / match',
    combined_conceded: 'Combined goals conceded / match', combined_shots_on_target: 'Combined shots on target / match',
    expected_first_half_goals: 'Expected first-half goals',
  }
  const value = (key: string, percent = false) => metrics[key] == null ? 'Unavailable' : percent ? `${(metrics[key]! * 100).toFixed(1)}%` : metrics[key]!.toFixed(2)
  return <section className="rounded-xl border border-slate-200 bg-white overflow-hidden">
    <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 px-4 py-3">
      <h2 className="text-base font-bold tracking-tight text-slate-900">Goals market evidence</h2>
      <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-sm font-semibold text-slate-600">{prediction?.goals_evidence ? 'Stored decision evidence' : 'Current history · not decision-time evidence'}</span>
    </div>
    <div className="space-y-4 px-4 py-4 text-base leading-relaxed text-slate-700">
      <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3">
        <summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">How this evidence is built</summary>
        <p className="mt-3">Latest 12 home fixtures for the home team and 12 away fixtures for the away team, completed before the target kickoff and evidence cutoff. Samples: home <span className="font-mono tabular-nums">{evidence?.sample_sizes.home ?? 0}</span>, away <span className="font-mono tabular-nums">{evidence?.sample_sizes.away ?? 0}</span>. Frequencies weight both teams equally. xG averages attacking xG with opposing xG conceded; first-half goals average both samples. Missing observations remain unavailable.</p>
      </details>
      {evidence?.cutoff_at && <p>Evidence cutoff: <span className="font-mono tabular-nums">{new Date(evidence.cutoff_at).toLocaleString()}</span></p>}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{Object.entries(labels).map(([key, label]) => <div className="rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2" key={key}><span className="block text-sm font-medium uppercase tracking-wide text-slate-600">{label}</span><strong className="mt-1 block font-mono text-sm tabular-nums text-slate-900">{value(key)}</strong></div>)}</div>
      <div className="overflow-x-auto rounded-lg border border-slate-200"><table className="w-full min-w-[320px] border-collapse text-left text-sm"><thead className="border-b border-slate-200 bg-slate-50 text-sm uppercase tracking-wide text-slate-600"><tr><th className="px-3 py-2">Goals line</th><th className="px-3 py-2">Over frequency</th><th className="px-3 py-2">Under frequency</th></tr></thead><tbody className="divide-y divide-slate-100">{[0, 1, 2, 3, 4].map(n => <tr key={n} className="hover:bg-slate-50/70"><td className="px-3 py-2 font-mono tabular-nums text-slate-700">{n}.5</td><td className="px-3 py-2 font-mono tabular-nums text-slate-900">{value(`over${n}5_frequency`, true)}</td><td className="px-3 py-2 font-mono tabular-nums text-slate-900">{value(`under${n}5_frequency`, true)}</td></tr>)}</tbody></table></div>
      <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3">
        <summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Model and context provenance</summary>
        <div className="mt-3 space-y-3">
          <h3 className="text-base font-semibold text-slate-900">Market probability model</h3>
          <p>{prediction ? <><span className="font-medium text-slate-900">{prediction.market}:</span> <span className="font-mono tabular-nums">{(prediction.model_probability * 100).toFixed(1)}%</span></> : 'No stored prediction'}. Model version: <span className="font-mono tabular-nums">{model?.model?.model_version ?? 'Unavailable'}</span>.</p>
          <p className="text-sm text-slate-600">{Object.entries(model?.model_inputs ?? {}).map(([name, p]) => `${name}: ${p == null ? 'Unavailable' : `${(p * 100).toFixed(1)}%`}`).join(' · ') || 'Model components unavailable'}</p>
          <h3 className="text-base font-semibold text-slate-900">Opponent-strength adjustment</h3>
          <p>{evidence?.context_review?.opponent_strength ?? 'Unverified'} · Stored Elo inputs: home <span className="font-mono tabular-nums">{model?.context?.home_elo ?? 'Unavailable'}</span>, away <span className="font-mono tabular-nums">{model?.context?.away_elo ?? 'Unavailable'}</span>, home advantage <span className="font-mono tabular-nums">{model?.context?.home_advantage_elo ?? 'Unavailable'}</span>. Elo inputs alone do not verify an adjustment to these historical metrics.</p>
          <h3 className="text-base font-semibold text-slate-900">Tactical and lineup review</h3>
          <p>{evidence?.context_review?.tactics_lineups ?? 'Unverified — no reviewed tactical or lineup evidence attached.'}</p>
        </div>
      </details>
      <div className="grid gap-4 sm:grid-cols-2">{['home', 'away'].map(side => <div key={side} className="rounded-lg border border-slate-200 bg-slate-50/70 p-3"><h3 className="text-sm font-semibold text-slate-900">Recent {side} matches</h3><div className="mt-2 space-y-1 text-sm text-slate-600">{evidence?.recent_matches?.[side]?.length ? evidence.recent_matches[side].map(game => <p key={game.id}><span className="font-mono tabular-nums">{game.kickoff_at?.slice(0, 10)}</span> · {game.home_team} <span className="font-mono tabular-nums font-semibold text-slate-900">{game.home_goals}–{game.away_goals}</span> {game.away_team}</p>) : <p>No recent matches available.</p>}</div></div>)}</div>
    </div>
  </section>
}
