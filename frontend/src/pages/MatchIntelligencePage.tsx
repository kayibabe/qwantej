import { useEffect, useMemo, useState } from 'react'
import { formatDate, formatKickoff, formatMarket, formatSentence, formatSelection, selectionRepeatsMarket, type MatchIntelligence } from '../lib/api'
import Over45Qualification from '../components/Over45Qualification'
import OverGoalsQualification from '../components/OverGoalsQualification'
import Under25Qualification from '../components/Under25Qualification'
import Under35Qualification from '../components/Under35Qualification'
import Under15Qualification from '../components/Under15Qualification'
import Under05Qualification from '../components/Under05Qualification'
import GoalsEvidence from '../components/GoalsEvidence'

interface Props {
  matchId: number
  selectedPredictionId?: number | null
  onBack: () => void
  returnLabel?: string
}

const pct = (value: number | null | undefined, signed = false) => {
  if (value == null) return 'Unavailable'
  return `${signed && value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`
}

function statusLabel(status: string) {
  return formatSentence(status)
}

function recommendationClass(status: string) {
  const key = status.toLowerCase()
  if (key === 'bet') return 'bg-emerald-50 text-emerald-700 border-emerald-200'
  if (key === 'watch') return 'bg-amber-50 text-amber-700 border-amber-200'
  return 'bg-red-50 text-red-700 border-red-200'
}

export default function MatchIntelligencePage({ matchId, selectedPredictionId, onBack, returnLabel = 'Today' }: Props) {
  const [data, setData] = useState<MatchIntelligence | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    fetch(`/api/v1/selections/match-intelligence/${matchId}`)
      .then(response => response.ok ? response.json() : response.json().then(body => Promise.reject(new Error(body.detail ?? `API error ${response.status}`))))
      .then(body => { if (active) setData(body) })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : 'Could not load match intelligence') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [matchId])

  const selectedPrediction = useMemo(
    () => data?.predictions.find(row => row.prediction_id === selectedPredictionId) ?? null,
    [data, selectedPredictionId],
  )
  const lead = selectedPrediction ?? data?.predictions[0] ?? null

  if (loading) return <section className="page-content" aria-busy="true" aria-live="polite"><div className="rounded-xl border border-slate-200 bg-white p-8 text-center space-y-2"><strong className="block text-lg font-semibold text-slate-900">Loading match intelligence</strong><span className="block text-base leading-relaxed text-slate-600">Reading the stored prediction, price, and pre-match context.</span></div></section>
  if (error || !data) return <section className="page-content" aria-live="polite"><div className="rounded-xl border border-slate-200 bg-white p-8 text-center space-y-3"><strong className="block text-lg font-semibold text-slate-900">{error ? 'Match intelligence could not be loaded' : 'No match intelligence on record'}</strong><span className="block text-base leading-relaxed text-slate-600" role={error ? 'alert' : undefined}>{error ?? 'No persisted intelligence was found for this match. This is an empty record, not a failed request.'}</span><button type="button" className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={onBack}>Back to {returnLabel}</button></div></section>

  const score = data.home_goals == null || data.away_goals == null ? 'Unplayed' : `${data.home_goals}–${data.away_goals}`
  const matchStatus = `Status: ${statusLabel(data.status)}`

  return (
    <section className="page-content space-y-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div><button type="button" className="mb-2 inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-emerald-700 hover:text-emerald-800 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={onBack}>← Back to {returnLabel}</button><span className="block text-sm font-semibold text-slate-600">Match intelligence</span><h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{data.home_team} <span className="text-slate-600 font-normal">vs</span> {data.away_team}</h1><p className="mt-1 text-base leading-relaxed text-slate-600">{data.competition} · <span className="event-date font-mono tabular-nums">{formatDate(data.kickoff_at)}</span> · <span className="kickoff-time font-mono tabular-nums">{formatKickoff(data.kickoff_at)}</span> · <strong className="text-slate-800">{matchStatus}</strong></p></div>
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-left lg:text-right space-y-1"><span className="block text-sm font-semibold text-slate-600">{selectedPrediction ? 'Selected market evidence' : 'Top stored market'}</span><strong className={`inline-flex items-center rounded-full border px-2.5 py-1 text-sm font-semibold ${recommendationClass(lead?.recommendation_status ?? 'WATCH')}`}>{statusLabel(lead?.recommendation_status ?? 'WATCH')}</strong><small className="block text-sm text-slate-600">{lead ? (selectionRepeatsMarket(lead.market, lead.selection) ? formatSelection(lead.selection) : <>{formatMarket(lead.market)} · {formatSelection(lead.selection)}</>) : 'No prediction snapshot'}</small>{selectedPrediction && <small className="block text-sm text-slate-600">Selected prediction {selectedPrediction.prediction_id} · odds captured {selectedPrediction.source_odds_at ? new Date(selectedPrediction.source_odds_at).toLocaleString() : 'timestamp unavailable'}</small>}{selectedPredictionId != null && !selectedPrediction && <small className="block text-sm text-slate-600">The selected snapshot is unavailable; showing the top stored market.</small>}</div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Metric label="Model probability" value={pct(lead?.model_probability)} />
        <Metric label="Best captured odds" value={lead?.best_odds?.toFixed(2) ?? 'Unavailable'} />
        <Metric label="Edge" value={pct(lead?.edge, true)} />
        <Metric label="Q score" value={lead?.q_score.toFixed(1) ?? 'Unavailable'} />
        <Metric label="Data quality" value={`${data.data_quality_score.toFixed(0)}/100`} note={statusLabel(data.data_quality_status)} />
        <Metric label="Score" value={score} />
      </div>

      <GoalsEvidence current={data.goals_evidence} prediction={lead} />
      <details className="rounded-xl border border-slate-200 bg-white overflow-hidden">
        <summary className="flex min-h-11 cursor-pointer items-center justify-between gap-3 px-4 py-3 text-left list-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"><span><strong className="block text-base font-semibold text-slate-900">Market qualification details</strong><small className="text-sm text-slate-600">Provisional goal-market screens · expand for thresholds, evidence and blockers</small></span></summary>
        <div className="grid gap-3 border-t border-slate-200 px-4 py-4">
          {data.predictions.filter(row => row.market === 'over_1.5').map(row => <OverGoalsQualification key={row.prediction_id} market="over_1.5" assessment={row.over15_qualification} />)}
          {data.predictions.filter(row => row.market === 'over_2.5').map(row => <OverGoalsQualification key={row.prediction_id} market="over_2.5" assessment={row.over25_qualification} />)}
          {data.predictions.filter(row => row.market === 'over_3.5').map(row => <OverGoalsQualification key={row.prediction_id} market="over_3.5" assessment={row.over35_qualification} />)}
          {data.predictions.filter(row => row.market === 'over_4.5').map(row => <Over45Qualification key={row.prediction_id} assessment={row.over45_qualification} />)}
          {data.predictions.filter(row => row.market === 'under_2.5').map(row => <Under25Qualification key={row.prediction_id} assessment={row.under25_qualification} />)}
          {data.predictions.filter(row => row.market === 'under_3.5').map(row => <Under35Qualification key={row.prediction_id} assessment={row.under35_qualification} />)}
          {data.predictions.filter(row => row.market === 'under_1.5').map(row => <Under15Qualification key={row.prediction_id} assessment={row.under15_qualification} />)}
          {data.predictions.filter(row => row.market === 'under_0.5').map(row => <Under05Qualification key={row.prediction_id} assessment={row.under05_qualification} />)}
        </div>
      </details>

      <section className="rounded-xl border border-slate-200 bg-white overflow-hidden"><div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3"><h2 className="text-sm font-bold text-slate-600">Executive decision summary</h2><span className="text-sm text-slate-600">Snapshot-backed · no recalculation</span></div><div className="grid gap-4 px-4 py-4 md:grid-cols-2 text-base leading-relaxed text-slate-700"><div><strong className="block mb-2 text-slate-900">Why consider it</strong>{lead?.recommendation_reasons.length ? <ul className="space-y-2 list-disc pl-5">{lead.recommendation_reasons.slice(0, 5).map(reason => <li key={reason}>{statusLabel(reason)}</li>)}</ul> : <span className="text-slate-600">No positive reason was persisted.</span>}</div><div><strong className="block mb-2 text-slate-900">Risks and unknowns</strong>{lead?.recommendation_risks.length ? <ul className="space-y-2 list-disc pl-5">{lead.recommendation_risks.slice(0, 5).map(risk => <li key={risk}>{statusLabel(risk)}</li>)}</ul> : <span className="text-slate-600">No additional risk code was persisted.</span>}</div></div></section>

      <section className="rounded-xl border border-slate-200 bg-white overflow-hidden"><div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3"><h2 className="text-sm font-bold text-slate-600">Ranked market probabilities</h2><span className="text-sm text-slate-600">{data.predictions.length} stored market snapshots</span></div>{data.predictions.length === 0 ? <div className="px-4 py-6 text-base text-slate-600">No prediction snapshot exists for this match.</div> : <div className="overflow-x-auto"><table className="w-full min-w-[760px] border-collapse text-left text-sm"><thead className="border-b border-slate-200 bg-slate-50 text-sm text-slate-600"><tr><th scope="col" className="px-3 py-3">Market</th><th scope="col" className="px-3 py-3">Probability</th><th scope="col" className="px-3 py-3">Odds</th><th scope="col" className="px-3 py-3">Edge</th><th scope="col" className="px-3 py-3">Q</th><th scope="col" className="px-3 py-3">Decision</th><th scope="col" className="px-3 py-3">Evidence</th></tr></thead><tbody className="divide-y divide-slate-100">{data.predictions.map(row => <tr className={row.prediction_id === selectedPredictionId ? 'bg-emerald-50/40' : 'hover:bg-slate-50/70'} key={row.prediction_id}><td className="px-3 py-3">{!selectionRepeatsMarket(row.market, row.selection) && <strong className="block text-slate-900">{formatMarket(row.market)}</strong>}<small className="block text-sm text-slate-600">{formatSelection(row.selection)}</small></td><td className="px-3 py-3 font-mono tabular-nums">{pct(row.model_probability)}</td><td className="px-3 py-3 font-mono tabular-nums">{row.best_odds?.toFixed(2) ?? 'Unavailable'}</td><td className="px-3 py-3 font-mono tabular-nums">{pct(row.edge, true)}</td><td className="px-3 py-3 font-mono tabular-nums">{row.q_score.toFixed(1)} · {row.q_grade}</td><td className="px-3 py-3"><span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-sm font-semibold ${recommendationClass(row.recommendation_status)}`}>{row.recommendation_status}</span></td><td className="px-3 py-3"><small className="text-sm text-slate-600">{row.active_models.length ? `${row.active_models.length} active models` : 'Model set unavailable'}</small></td></tr>)}</tbody></table></div>}</section>

      <div className="grid gap-4 lg:grid-cols-2"><section className="rounded-xl border border-slate-200 bg-white overflow-hidden"><div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3"><h2 className="text-sm font-bold text-slate-600">Pre-match form</h2><span className="text-sm text-slate-600">Finished matches before kickoff</span></div><div className="px-4 py-4"><div className="grid gap-4 sm:grid-cols-[1fr_auto_1fr] sm:items-start"><TeamForm team={data.context.home} /><span className="self-center text-center text-sm font-semibold text-slate-600">vs</span><TeamForm team={data.context.away} /></div></div></section><section className="rounded-xl border border-slate-200 bg-white overflow-hidden"><div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3"><h2 className="text-sm font-bold text-slate-600">Traceability</h2><span className="text-sm text-slate-600">Reproducibility fields</span></div><div className="px-4 py-4 space-y-3"><div className="grid gap-2 text-sm">{[['Match ID', String(data.match_id)], ['Kickoff', `${formatDate(data.kickoff_at)} ${formatKickoff(data.kickoff_at)}`], ['Information set', lead?.as_of_at ? new Date(lead.as_of_at).toLocaleString() : 'Unavailable'], ['Odds timestamp', lead?.source_odds_at ? new Date(lead.source_odds_at).toLocaleString() : 'Unavailable']].map(([label, value]) => <div key={label} className="flex items-center justify-between gap-3 border-b border-slate-100 pb-2 last:border-0 last:pb-0"><span className="text-slate-600">{label}</span><code className="font-mono text-sm tabular-nums text-slate-800">{value}</code></div>)}</div><p className="text-base leading-relaxed text-slate-600">{data.evidence_note}</p></div></section></div>

      <section className="rounded-xl border border-slate-200 bg-white overflow-hidden"><div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3"><h2 className="text-sm font-bold text-slate-600">Head-to-head</h2><span className="text-sm text-slate-600">Persisted finished meetings</span></div>{data.context.h2h.length ? <div className="divide-y divide-slate-100">{data.context.h2h.map(game => <div key={game.date + game.score} className="flex items-center justify-between gap-3 px-4 py-3 text-base"><span className="font-mono tabular-nums text-slate-600">{game.date}</span><strong className="text-slate-900">{game.home_team} <span className="font-mono tabular-nums">{game.score}</span> {game.away_team}</strong></div>)}</div> : <div className="px-4 py-6 text-base text-slate-600">No previous meetings found in the persisted data.</div>}</section>
    </section>
  )
}

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return <div className="rounded-xl border border-slate-200 bg-white px-4 py-3"><span className="block text-sm font-medium text-slate-600">{label}</span><strong className="mt-1 block font-mono text-xl font-bold tabular-nums text-slate-900">{value}</strong>{note && <small className="mt-1 block text-sm text-slate-700">{note}</small>}</div>
}

function TeamForm({ team }: { team: MatchIntelligence['context']['home'] }) {
  const formClass = (result: string) => result === 'W' ? 'bg-emerald-50 text-emerald-700' : result === 'D' ? 'bg-amber-50 text-amber-700' : result === 'L' ? 'bg-rose-50 text-rose-700' : 'bg-slate-100 text-slate-600'
  return <div className="space-y-2"><strong className="block text-base font-semibold text-slate-900">{team.team}</strong><div className="flex flex-wrap gap-1">{team.results.length ? team.results.map((result, index) => <span key={`${result}-${index}`} className={`inline-flex h-7 min-w-7 items-center justify-center rounded px-1.5 text-sm font-bold ${formClass(result)}`} aria-label={`Result ${result}`}>{result}</span>) : <span className="text-base text-slate-600">No history</span>}</div><small className="block text-sm text-slate-600 font-mono tabular-nums">{team.matches} matches · {team.points_per_game.toFixed(2)} points/game · {team.goals_for}–{team.goals_against}</small></div>
}
