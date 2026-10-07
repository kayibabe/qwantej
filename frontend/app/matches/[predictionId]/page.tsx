import type { Metadata } from "next"
import Link from "next/link"
import { notFound } from "next/navigation"
import { fetchPrediction, fetchPredictionEvidence } from "@/lib/api"
import { fmtDatetime } from "@/lib/format"

export const metadata: Metadata = { title: "Match intelligence" }

function pct(value: number | null | undefined) {
  return value == null ? "Unavailable" : `${(value * 100).toFixed(1)}%`
}

function signedPp(value: number | null | undefined) {
  return value == null ? "Unavailable" : `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)} pp`
}

function reasonList(prediction: Awaited<ReturnType<typeof fetchPrediction>>, evidence: Awaited<ReturnType<typeof fetchPredictionEvidence>>) {
  const reasons: string[] = []
  if (prediction.edge_pp != null && prediction.edge_pp > 0) reasons.push(`Stored model edge is ${signedPp(prediction.edge_pp)} against the archived market probability.`)
  if (prediction.executable_odds != null) reasons.push(`An executable price of ${prediction.executable_odds.toFixed(2)} was archived at decision time.`)
  if (prediction.model_version_label) reasons.push(`The forecast is linked to model lineage: ${prediction.model_version_label}.`)
  if (evidence.home_summary.played || evidence.away_summary.played) reasons.push(`Pre-kickoff form evidence covers ${evidence.home_summary.played} home-team and ${evidence.away_summary.played} away-team fixtures.`)
  return reasons.length ? reasons : ["No positive explanatory factor is available in the archived record."]
}

function riskList(prediction: Awaited<ReturnType<typeof fetchPrediction>>, evidence: Awaited<ReturnType<typeof fetchPredictionEvidence>>) {
  const risks: string[] = []
  if (prediction.research_mode) risks.push("Research-only forecast: it is not a production/value-qualified signal.")
  if (prediction.executable_odds == null) risks.push("No executable bookmaker price was archived.")
  if (prediction.dqs == null) risks.push("Data-quality score is unavailable.")
  if (evidence.home_summary.played < 5 || evidence.away_summary.played < 5) risks.push("One or both teams have fewer than five archived pre-kickoff form matches in this view.")
  if (prediction.settlement_overdue) risks.push("Kickoff has passed without an effective settlement record; outcome status requires investigation.")
  return risks.length ? risks : ["No additional risk flag is recorded in this view. This is not a guarantee of outcome."]
}

export default async function MatchIntelligencePage({
  params,
}: { params: Promise<{ predictionId: string }> }) {
  const { predictionId } = await params
  const [prediction, evidence] = await Promise.all([
    fetchPrediction(predictionId).catch(() => null),
    fetchPredictionEvidence(predictionId).catch(() => null),
  ])
  if (!prediction || !evidence) notFound()

  const match = `${prediction.home_team ?? prediction.fixture_id} v ${prediction.away_team ?? "Unknown opponent"}`
  const reasons = reasonList(prediction, evidence)
  const risks = riskList(prediction, evidence)

  return <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-4 sm:p-8">
    <div>
      <Link href="/" className="text-xs font-medium text-[var(--accent)] hover:underline">← Back to today&apos;s intelligence</Link>
      <p className="mt-5 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent)]">Match intelligence</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[var(--text-primary)] sm:text-4xl">{match}</h1>
      <p className="mt-2 text-sm text-[var(--text-secondary)]">{prediction.competition_name ?? "Competition unavailable"} · {prediction.kickoff_utc ? `${fmtDatetime(prediction.kickoff_utc)} (Africa/Blantyre)` : "Kickoff unavailable"}</p>
    </div>

    <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-5 shadow-[var(--surface-shadow)] sm:p-6" aria-labelledby="executive-heading">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Executive forecast summary</p><h2 id="executive-heading" className="mt-2 text-xl font-semibold text-[var(--text-primary)]">{prediction.market} · {prediction.selection}</h2></div>
        <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${prediction.research_mode ? "border-[var(--void)]/40 text-[var(--void)]" : prediction.gate_passed ? "border-[var(--win)]/40 text-[var(--win)]" : "border-[var(--border)] text-[var(--text-secondary)]"}`}>{prediction.research_mode ? "RESEARCH" : prediction.gate_passed ? "QUALIFIED" : "REJECTED"}</span>
      </div>
      <div className="mt-5 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--border)] sm:grid-cols-4">
        {[["Model probability", pct(prediction.conservative_probability)], ["Archived odds", prediction.executable_odds?.toFixed(2) ?? "Unavailable"], ["Edge", signedPp(prediction.edge_pp)], ["Expected value", prediction.expected_value == null ? "Unavailable" : `${(prediction.expected_value * 100).toFixed(2)}%`], ["DQS", prediction.dqs?.toFixed(1) ?? "Unavailable"], ["QSS", prediction.qss?.toFixed(1) ?? "Unavailable"], ["Bookmaker", prediction.bookmaker ?? "Unavailable"], ["Outcome", prediction.outcome ?? "Pending"]].map(([label, value]) => <div key={label} className="bg-[var(--bg-surface)] p-3"><p className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">{label}</p><p className="mt-1 font-semibold text-[var(--text-primary)]">{value}</p></div>)}
      </div>
      <p className="mt-4 text-xs leading-5 text-[var(--text-muted)]">All values above are archived decision-time fields. Current bookmaker prices and newly calculated probabilities are intentionally not substituted here.</p>
    </section>

    <div className="grid gap-6 lg:grid-cols-2">
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-5 shadow-[var(--surface-shadow)]" aria-labelledby="why-heading"><h2 id="why-heading" className="text-lg font-semibold text-[var(--text-primary)]">Why this forecast was considered</h2><ul className="mt-4 space-y-3 text-sm leading-6 text-[var(--text-secondary)]">{reasons.map((reason) => <li key={reason} className="flex gap-2"><span className="text-[var(--win)]" aria-hidden="true">+</span><span>{reason}</span></li>)}</ul></section>
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-5 shadow-[var(--surface-shadow)]" aria-labelledby="risk-heading"><h2 id="risk-heading" className="text-lg font-semibold text-[var(--text-primary)]">Risks and limitations</h2><ul className="mt-4 space-y-3 text-sm leading-6 text-[var(--text-secondary)]">{risks.map((risk) => <li key={risk} className="flex gap-2"><span className="text-[var(--void)]" aria-hidden="true">!</span><span>{risk}</span></li>)}</ul></section>
    </div>

    <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-5 shadow-[var(--surface-shadow)]" aria-labelledby="form-heading"><div className="flex flex-wrap items-end justify-between gap-3"><div><h2 id="form-heading" className="text-lg font-semibold text-[var(--text-primary)]">Pre-kickoff form evidence</h2><p className="mt-1 text-xs text-[var(--text-muted)]">Completed fixtures strictly before kickoff; evidence cutoff {fmtDatetime(evidence.as_of)}.</p></div><span className="text-xs text-[var(--text-muted)]">{evidence.h2h.length} archived H2H fixture{evidence.h2h.length === 1 ? "" : "s"}</span></div><div className="mt-5 grid gap-5 sm:grid-cols-2">{[[prediction.home_team ?? "Home", evidence.home_summary, evidence.home_form], [prediction.away_team ?? "Away", evidence.away_summary, evidence.away_form]].map(([team, summary, form]) => <div key={team as string} className="rounded-xl border border-[var(--border-subtle)] p-4"><h3 className="font-semibold text-[var(--text-primary)]">{team as string}</h3><p className="mt-2 text-xs text-[var(--text-secondary)]">{(summary as typeof evidence.home_summary).played} played · {(summary as typeof evidence.home_summary).wins}W {(summary as typeof evidence.home_summary).draws}D {(summary as typeof evidence.home_summary).losses}L · {(summary as typeof evidence.home_summary).goals_for}–{(summary as typeof evidence.home_summary).goals_against} goals · {(summary as typeof evidence.home_summary).points_per_game?.toFixed(2) ?? "—"} PPG</p><div className="mt-3 space-y-1 text-xs text-[var(--text-muted)]">{(form as typeof evidence.home_form).slice(0, 5).map((row) => <p key={`${row.date}-${row.opponent}-${row.score}`}>{row.date ?? "Date unavailable"} · {row.opponent} · <strong className="text-[var(--text-primary)]">{row.result} {row.score}</strong></p>)}{!(form as typeof evidence.home_form).length && <p>No pre-kickoff form evidence archived.</p>}</div></div>)}</div></section>

    <details className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-5 shadow-[var(--surface-shadow)]"><summary className="cursor-pointer font-semibold text-[var(--text-primary)]">Model lineage and reproducibility</summary><dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2"><div><dt className="text-xs uppercase tracking-wide text-[var(--text-muted)]">Decision as of</dt><dd className="mt-1 text-[var(--text-secondary)]">{fmtDatetime(prediction.decision_as_of)}</dd></div><div><dt className="text-xs uppercase tracking-wide text-[var(--text-muted)]">Model version</dt><dd className="mt-1 text-[var(--text-secondary)]">{prediction.model_version_label ?? "Unavailable"}</dd></div><div><dt className="text-xs uppercase tracking-wide text-[var(--text-muted)]">Research mode</dt><dd className="mt-1 text-[var(--text-secondary)]">{prediction.research_mode ? "Yes — evidence only" : "No"}</dd></div><div><dt className="text-xs uppercase tracking-wide text-[var(--text-muted)]">Prediction ID</dt><dd className="mt-1 break-all font-mono text-xs text-[var(--text-secondary)]">{prediction.id}</dd></div></dl></details>
  </div>
}
