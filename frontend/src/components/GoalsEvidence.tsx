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
  return <section className="evidence-card">
    <div className="evidence-title"><h2>Goals market evidence</h2><span>{prediction?.goals_evidence ? 'Stored decision evidence' : 'Current history · not decision-time evidence'}</span></div>
    <p>Latest 12 home fixtures for the home team and 12 away fixtures for the away team, completed before the target kickoff and evidence cutoff. Samples: home {evidence?.sample_sizes.home ?? 0}, away {evidence?.sample_sizes.away ?? 0}. Frequencies weight both teams equally. xG averages attacking xG with opposing xG conceded; first-half goals average both samples. Missing observations remain unavailable.</p>
    {evidence?.cutoff_at && <p>Evidence cutoff: {new Date(evidence.cutoff_at).toLocaleString()}</p>}
    <div className="detail-metrics">{Object.entries(labels).map(([key, label]) => <div className="metric" key={key}><span>{label}</span><strong>{value(key)}</strong></div>)}</div>
    <table className="match-intelligence-table"><thead><tr><th>Goals line</th><th>Over frequency</th><th>Under frequency</th></tr></thead><tbody>{[0, 1, 2, 3, 4].map(n => <tr key={n}><td>{n}.5</td><td>{value(`over${n}5_frequency`, true)}</td><td>{value(`under${n}5_frequency`, true)}</td></tr>)}</tbody></table>
    <h3>Market probability model</h3>
    <p>{prediction ? `${prediction.market}: ${(prediction.model_probability * 100).toFixed(1)}%` : 'No stored prediction'}. Model version: {model?.model?.model_version ?? 'Unavailable'}.</p>
    <p>{Object.entries(model?.model_inputs ?? {}).map(([name, p]) => `${name}: ${p == null ? 'Unavailable' : `${(p * 100).toFixed(1)}%`}`).join(' · ') || 'Model components unavailable'}</p>
    <h3>Opponent-strength adjustment</h3>
    <p>{evidence?.context_review?.opponent_strength ?? 'Unverified'} · Stored Elo inputs: home {model?.context?.home_elo ?? 'Unavailable'}, away {model?.context?.away_elo ?? 'Unavailable'}, home advantage {model?.context?.home_advantage_elo ?? 'Unavailable'}. Elo inputs alone do not verify an adjustment to these historical metrics.</p>
    <h3>Tactical and lineup review</h3><p>{evidence?.context_review?.tactics_lineups ?? 'Unverified — no reviewed tactical or lineup evidence attached.'}</p>
    <div className="match-intelligence-columns">{['home', 'away'].map(side => <div key={side}><h3>Recent {side} matches</h3>{evidence?.recent_matches?.[side]?.length ? evidence.recent_matches[side].map(game => <p key={game.id}>{game.kickoff_at?.slice(0, 10)} · {game.home_team} {game.home_goals}–{game.away_goals} {game.away_team}</p>) : <p>No recent matches available.</p>}</div>)}</div>
  </section>
}
