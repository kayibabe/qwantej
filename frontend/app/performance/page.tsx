import type { Metadata } from "next"
import { fetchPerformanceReport, fetchPerformanceSegments } from "@/lib/api"
import CalibrationCurveChart from "@/components/CalibrationCurveChart"
import type { KPIReportOut } from "@/lib/types"

export const metadata: Metadata = { title: "Performance" }

function pct(value: number | null, decimals = 1) {
  return value === null ? "—" : `${(value * 100).toFixed(decimals)}%`
}

function units(value: number | null) {
  if (value === null) return "—"
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)} units`
}

function metricTone(value: number | null) {
  if (value === null || value === 0) return "text-[var(--text-primary)]"
  return value > 0 ? "text-[var(--win)]" : "text-[var(--loss)]"
}

function MetricCard({ label, value, sub, tone }: { label: string; value: string; sub: string; tone?: string }) {
  return <article className="rounded-xl border border-[var(--border)] border-l-[3px] border-l-[var(--accent)] bg-[var(--bg-surface)] px-5 py-4 shadow-[var(--surface-shadow)]">
    <p className="text-xs font-semibold uppercase tracking-[.12em] text-[var(--text-muted)]">{label}</p>
    <p className={`mt-2 text-2xl font-semibold tracking-tight ${tone ?? "text-[var(--text-primary)]"}`}>{value}</p>
    <p className="mt-1 text-xs text-[var(--text-secondary)]">{sub}</p>
  </article>
}

function EvidenceValue({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return <div><p className="text-xs text-[var(--text-muted)]">{label}</p><p className={`mt-1 text-sm font-semibold ${tone ?? "text-[var(--text-primary)]"}`}>{value}</p></div>
}

function SegmentRow({ name, report }: { name: string; report: KPIReportOut }) {
  return <div className="grid gap-3 border-t border-[var(--border-subtle)] py-4 sm:grid-cols-[minmax(180px,1.7fr)_repeat(3,minmax(90px,1fr))] sm:items-center">
    <div><span className="inline-flex rounded bg-[var(--accent-soft)] px-2 py-1 text-xs font-semibold text-[var(--accent)]">{name}</span><p className="mt-1 text-xs text-[var(--text-secondary)]">{report.n_wins}/{report.n_settled} won</p></div>
    <EvidenceValue label="Hit rate" value={pct(report.hit_rate)} />
    <EvidenceValue label="ROI" value={pct(report.roi)} tone={metricTone(report.roi)} />
    <EvidenceValue label="P&amp;L" value={units(report.total_profit)} tone={metricTone(report.total_profit)} />
  </div>
}

function isDate(value: string | undefined) {
  return Boolean(value && /^\d{4}-\d{2}-\d{2}$/.test(value))
}

function EvidenceLine({ label, detail, value }: { label: string; detail: string; value: string }) {
  return <div className="flex items-start justify-between gap-4 border-b border-[var(--border-subtle)] pb-4 last:border-0 last:pb-0"><div><p className="text-sm font-semibold text-[var(--text-primary)]">{label}</p><p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">{detail}</p></div><strong className="shrink-0 text-sm text-[var(--accent)]">{value}</strong></div>
}

export default async function PerformancePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams
  const requestedSince = typeof params.since === "string" && isDate(params.since) ? params.since : undefined
  const subjectType = params.subject_type === "accumulator" ? "accumulator" : "prediction"
  const since = requestedSince ? `${requestedSince}T00:00:00Z` : undefined
  const [report, segmentResponse] = await Promise.all([
    fetchPerformanceReport({ subject_type: subjectType, since }).catch(() => null),
    subjectType === "prediction" ? fetchPerformanceSegments({ by: "model_version", subject_type: subjectType, since }).catch(() => null) : Promise.resolve(null),
  ])

  if (!report) return <div className="mx-auto w-full max-w-7xl p-5 sm:p-8"><section className="rounded-xl border border-[var(--loss)] bg-[var(--bg-surface)] p-5 text-sm text-[var(--loss)]">Performance evidence is temporarily unavailable. No result is inferred while the report cannot be loaded.</section></div>

  const segmentRows = Object.entries(segmentResponse?.segments ?? {}).sort(([, a], [, b]) => b.n_settled - a.n_settled)
  const coverage = report.n_total > 0 ? report.n_settled / report.n_total : null
  const calibrationCount = report.calibration_bins?.reduce((total, bin) => total + bin.count, 0) ?? 0

  return <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 p-5 sm:p-8">
    <form method="get" className="flex flex-wrap items-end gap-3 border-b border-[var(--border)] pb-4" aria-label="Performance evidence scope">
      <div className="mr-1"><p className="text-lg font-medium text-[var(--text-primary)]">Scope</p></div>
      <label className="grid gap-1 text-xs font-semibold text-[var(--text-secondary)]">From<input type="date" name="since" defaultValue={requestedSince} className="h-11 rounded-lg border border-[var(--border)] bg-[var(--bg-raised)] px-3 text-sm font-normal text-[var(--text-primary)]" /></label>
      <label className="grid gap-1 text-xs font-semibold text-[var(--text-secondary)]">Evidence<select name="subject_type" defaultValue={subjectType} className="h-11 min-w-44 rounded-lg border border-[var(--border)] bg-[var(--bg-raised)] px-3 text-sm font-normal text-[var(--text-primary)]"><option value="prediction">Prediction selections</option><option value="accumulator">Accumulator tickets</option></select></label>
      <button type="submit" className="h-11 rounded-lg border border-[var(--accent)] bg-[var(--accent)] px-4 text-sm font-semibold text-white hover:bg-[var(--accent-hover)]">Apply</button>
      <p className="mb-2 text-sm text-[var(--text-secondary)] sm:ml-auto">Applies to effective, immutable settlement records.</p>
    </form>

    <section className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#9ecfbd] bg-[#f2fbf7] px-4 py-3 text-sm text-[#176044]" aria-label="Evidence status">
      <span className="font-semibold"><span className="mr-2 inline-block h-2.5 w-2.5 rounded-full bg-[var(--win)]" />Settlement evidence available</span>
      <span>{report.n_settled} of {report.n_total} records settled{coverage !== null ? ` · ${(coverage * 100).toFixed(1)}% coverage` : ""}</span>
    </section>

    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6" aria-label="Headline performance evidence">
      <MetricCard label="Net P&amp;L" value={units(report.total_profit)} sub={`${report.total_stake?.toFixed(2) ?? "—"} units staked`} tone={metricTone(report.total_profit)} />
      <MetricCard label="ROI / yield" value={pct(report.roi)} sub="Settled stakes only" tone={metricTone(report.roi)} />
      <MetricCard label="Hit rate" value={pct(report.hit_rate)} sub={report.break_even_hit_rate === null ? "Break-even unavailable" : `Break-even ${pct(report.break_even_hit_rate)}`} />
      <MetricCard label="Max drawdown" value={pct(report.max_drawdown)} sub="Peak-to-trough of settled returns" tone={report.max_drawdown && report.max_drawdown > 0.15 ? "text-[var(--loss)]" : undefined} />
      <MetricCard label="Brier score" value={report.brier_score?.toFixed(3) ?? "—"} sub="Lower is better" />
      <MetricCard label="Calibration error" value={report.ece?.toFixed(3) ?? "—"} sub={`${calibrationCount} settled selections`} />
    </section>

    <section className="grid gap-5 xl:grid-cols-[minmax(0,1.8fr)_minmax(300px,.9fr)]">
      <article className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--surface-shadow)]"><p className="text-xs font-semibold uppercase tracking-[.14em] text-[var(--accent)]">Portfolio lens</p><div className="mt-2 flex items-baseline justify-between gap-3"><h2 className="text-lg font-semibold text-[var(--text-primary)]">{subjectType === "prediction" ? "By model version" : "Ticket evidence"}</h2><span className="text-xs text-[var(--text-muted)]">Latest effective settlement version</span></div>{segmentRows.length ? <div className="mt-5">{segmentRows.map(([name, row]) => <SegmentRow key={name} name={name} report={row} />)}</div> : <p className="mt-5 rounded-lg bg-[var(--bg-raised)] p-4 text-sm text-[var(--text-secondary)]">No model-version breakdown is available for this evidence scope.</p>}</article>
      <aside className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--surface-shadow)]"><p className="text-xs font-semibold uppercase tracking-[.14em] text-[var(--accent)]">Interpretation</p><h2 className="mt-2 text-lg font-semibold text-[var(--text-primary)]">Evidence quality</h2><div className="mt-5 space-y-4"><EvidenceLine label="Settlement coverage" detail="Effective records with a settled outcome." value={coverage === null ? "—" : pct(coverage)} /><EvidenceLine label="Calibration sample" detail="Settled selections used for scoring." value={String(calibrationCount)} /><EvidenceLine label="Uncertainty" detail="Small samples make ROI and hit rate unstable." value={report.n_settled < 30 ? "High" : "Monitor"} /></div><p className="mt-5 border-t border-[var(--border-subtle)] pt-4 text-sm leading-6 text-[var(--text-secondary)]">Read calibration, settlement coverage, and drawdown alongside headline returns. This report describes historical evidence; it does not promise future outcomes.</p></aside>
    </section>

    {report.calibration_bins && report.calibration_bins.length > 0 && <section aria-label="Calibration curve"><p className="mb-3 text-xs font-semibold uppercase tracking-[.14em] text-[var(--accent)]">Reliability diagram</p><CalibrationCurveChart bins={report.calibration_bins} /></section>}
  </div>
}
