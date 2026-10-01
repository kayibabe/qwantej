import type { Metadata } from "next"
import Link from "next/link"
import {
  fetchBankroll,
  fetchPerformanceReport,
  fetchPerformanceSegments,
  fetchRealBetResults,
} from "@/lib/api"
import { fmtSignedPct, fmtUnits } from "@/lib/format"
import { productColor, productLabel, productRank } from "@/lib/tickets"
import CalibrationCurveChart from "@/components/CalibrationCurveChart"
import ResultsByPeriod from "@/components/performance/ResultsByPeriod"
import SettlementLog from "@/components/performance/SettlementLog"
import SortableTable, { type SortableColumn } from "@/components/SortableTable"
import type { BankrollSummaryOut, KPIReportOut, RealBetResultsOut } from "@/lib/types"

export const metadata: Metadata = { title: "Performance" }

function pct(value: number | null | undefined, decimals = 1) {
  return value === null || value === undefined ? "—" : `${(value * 100).toFixed(decimals)}%`
}

function tone(value: number | null | undefined) {
  if (value === null || value === undefined || value === 0) return "text-[var(--text-primary)]"
  return value > 0 ? "text-[var(--win)]" : "text-[var(--loss)]"
}

function money(value: string, currency: string) {
  const n = Number(value)
  const sign = n > 0 ? "+" : n < 0 ? "−" : ""
  return `${sign}${currency} ${Math.abs(n).toLocaleString("en-GB", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`
}

function MetricCard({ label, value, sub, valueTone }: { label: string; value: string; sub: string; valueTone?: string }) {
  return <article className="rounded-xl border border-[var(--border)] border-l-[3px] border-l-[var(--accent)] bg-[var(--bg-surface)] px-5 py-4 shadow-[var(--surface-shadow)]">
    <p className="text-xs font-semibold uppercase tracking-[.12em] text-[var(--text-muted)]">{label}</p>
    <p className={`mt-2 text-2xl font-semibold tracking-tight ${valueTone ?? "text-[var(--text-primary)]"}`}>{value}</p>
    <p className="mt-1 text-xs text-[var(--text-secondary)]">{sub}</p>
  </article>
}

type SearchParams = Record<string, string | string[] | undefined>
type PerformanceScope = "all" | "production" | "research"

// The former Ticket results and Settlements pages live here as tabs; their old
// URLs redirect to these tabs (see next.config.ts).
const TABS = [
  { value: "overview", label: "Overview" },
  { value: "periods", label: "By period" },
  { value: "settlements", label: "Settlement log" },
] as const

function PerformanceTabs({ active }: { active: (typeof TABS)[number]["value"] }) {
  return <nav aria-label="Performance views" className="flex flex-wrap gap-1 border-b border-[var(--border)]">
    {TABS.map((t) => {
      const current = t.value === active
      return <Link
        key={t.value}
        href={t.value === "overview" ? "/performance" : `/performance?tab=${t.value}`}
        aria-current={current ? "page" : undefined}
        className={[
          "-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
          current
            ? "border-[var(--accent)] text-[var(--accent)]"
            : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
        ].join(" ")}
      >{t.label}</Link>
    })}
  </nav>
}

export default async function PerformancePage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams
  const tab = TABS.find((t) => t.value === params.tab)?.value ?? "overview"

  return <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 p-5 sm:p-8">
    <PerformanceTabs active={tab} />
    {tab === "periods" ? <ResultsByPeriod by={typeof params.by === "string" ? params.by : undefined} />
      : tab === "settlements" ? <SettlementLog sp={params} />
      : <Overview params={params} />}
  </div>
}

function isDate(value: string | undefined) {
  return Boolean(value && /^\d{4}-\d{2}-\d{2}$/.test(value))
}

function scopeLabel(scope: PerformanceScope) {
  return scope === "production" ? "Production forecasts" : scope === "research" ? "Research forecasts" : "All forecasts"
}

/** One row per segment: record, hit rate vs break-even, average odds, ROI, P&L. */
function SegmentTable({ caption, rows, nameHeader, colorFor, labelFor }: {
  caption: string
  rows: [string, KPIReportOut][]
  nameHeader: string
  colorFor?: (name: string) => string
  labelFor?: (name: string) => string
}) {
  const columns: SortableColumn[] = [
    { key: "name", label: nameHeader, className: "py-2 pr-4 font-semibold" },
    { key: "record", label: "Won–lost", align: "right", className: "px-3 py-2 font-semibold" },
    { key: "hit", label: "Hit rate", align: "right", className: "px-3 py-2 font-semibold" },
    { key: "break_even", label: "Break-even", align: "right", className: "hidden px-3 py-2 font-semibold md:table-cell" },
    { key: "odds", label: "Avg odds", align: "right", className: "hidden px-3 py-2 font-semibold sm:table-cell" },
    { key: "roi", label: "ROI", align: "right", className: "px-3 py-2 font-semibold" },
    { key: "pnl", label: "P&L", align: "right", className: "py-2 pl-3 font-semibold" },
  ]
  return <div className="overflow-x-auto">
    <SortableTable
      caption={caption}
      columns={columns}
      theadClassName="border-b border-[var(--border)] text-xs uppercase tracking-wider text-[var(--text-muted)]"
      rows={rows.map(([name, r]) => {
        const label = labelFor ? labelFor(name) : name
        return {
          key: name,
          className: "border-t border-[var(--border-subtle)]",
          // Won–lost sorts by wins; ties keep the table's own order.
          values: [label, r.n_wins, r.hit_rate, r.break_even_hit_rate, r.average_odds, r.roi, r.total_profit],
          cells: <>
            <th scope="row" className="py-3 pr-4 text-left font-semibold" style={colorFor ? { color: colorFor(name) } : undefined}>{label}</th>
            <td className="px-3 py-3 text-right font-mono">{r.n_wins}–{r.n_losses}{r.n_voids + r.n_pushes ? <span className="text-[var(--text-muted)]"> ({r.n_voids + r.n_pushes} void)</span> : null}</td>
            <td className="px-3 py-3 text-right font-mono">{pct(r.hit_rate)}</td>
            <td className="hidden px-3 py-3 text-right font-mono text-[var(--text-muted)] md:table-cell">{pct(r.break_even_hit_rate)}</td>
            <td className="hidden px-3 py-3 text-right font-mono sm:table-cell">{r.average_odds?.toFixed(2) ?? "—"}</td>
            <td className={`px-3 py-3 text-right font-mono font-semibold ${tone(r.roi)}`}>{fmtSignedPct(r.roi)}</td>
            <td className={`py-3 pl-3 text-right font-mono ${tone(r.total_profit)}`}>{fmtUnits(r.total_profit)}</td>
          </>,
        }
      })}
    />
  </div>
}

function RealMoney({ bankroll, results }: { bankroll: BankrollSummaryOut | null; results: RealBetResultsOut | null }) {
  if (!bankroll && !results) return null
  const currency = results?.currency ?? bankroll?.currency ?? "MWK"
  const roi = results?.roi == null ? null : Number(results.roi)
  const profit = results ? Number(results.settled_profit) : null
  return <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--surface-shadow)]" aria-labelledby="real-money-heading">
    <p className="text-xs font-semibold uppercase tracking-[.14em] text-[var(--accent)]">Real money</p>
    <div className="mt-2 flex flex-wrap items-baseline justify-between gap-3">
      <h2 id="real-money-heading" className="text-lg font-semibold text-[var(--text-primary)]">Bets you placed, in {currency}</h2>
      <span className="text-xs text-[var(--text-muted)]">Bookmaker payouts are authoritative</span>
    </div>
    {results && results.n_bets === 0
      ? <p className="mt-4 rounded-lg bg-[var(--bg-raised)] p-4 text-sm text-[var(--text-secondary)]">No real-money bets are recorded yet. Once you record a bet on a published ticket and settle it, its actual profit and ROI appear here next to the model&apos;s 1-unit figures.</p>
      : <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {bankroll && <div><p className="text-xs text-[var(--text-muted)]">Bankroll balance</p><p className="mt-1 text-xl font-semibold text-[var(--text-primary)]">{money(bankroll.balance, currency).replace(/^\+/, "")}</p><p className="text-xs text-[var(--text-secondary)]">{money(bankroll.available, currency).replace(/^\+/, "")} available · {bankroll.open_bets} open</p></div>}
        {results && <div><p className="text-xs text-[var(--text-muted)]">Net profit</p><p className={`mt-1 text-xl font-semibold ${tone(profit)}`}>{money(results.settled_profit, currency)}</p><p className="text-xs text-[var(--text-secondary)]">on {money(results.settled_stake, currency).replace(/^\+/, "")} settled stakes</p></div>}
        {results && <div><p className="text-xs text-[var(--text-muted)]">ROI</p><p className={`mt-1 text-xl font-semibold ${tone(roi)}`}>{fmtSignedPct(roi)}</p><p className="text-xs text-[var(--text-secondary)]">Voids excluded from turnover</p></div>}
        {results && <div><p className="text-xs text-[var(--text-muted)]">Record</p><p className="mt-1 text-xl font-semibold text-[var(--text-primary)]">{results.n_won}W – {results.n_lost}L</p><p className="text-xs text-[var(--text-secondary)]">{results.n_void} void{results.n_cashed_out ? ` · ${results.n_cashed_out} cashed out` : ""} · {results.n_open} open</p></div>}
      </div>}
  </section>
}

async function Overview({ params }: { params: SearchParams }) {
  const requestedSince = typeof params.since === "string" && isDate(params.since) ? params.since : undefined
  const requestedUntil = typeof params.until === "string" && isDate(params.until) ? params.until : undefined
  const dateFrom = typeof params.date_from === "string" && isDate(params.date_from) ? params.date_from : undefined
  const dateTo = typeof params.date_to === "string" && isDate(params.date_to) ? params.date_to : undefined
  const market = typeof params.market === "string" ? params.market : undefined
  const selection = typeof params.selection === "string" ? params.selection : undefined
  const minProbabilityPercent = typeof params.min_probability === "string" ? params.min_probability : undefined
  const minProbability = minProbabilityPercent && Number.isFinite(Number(minProbabilityPercent))
    ? String(Number(minProbabilityPercent) / 100)
    : undefined
  const minOdds = typeof params.min_odds === "string" ? params.min_odds : undefined
  // Tickets are what gets published and bet on, so they are the default lens.
  // Match filters are individual-forecast filters. This also makes URLs copied
  // from research screens work when they omit the optional subject_type.
  const hasMatchFilters = [params.market, params.selection, params.min_probability, params.min_odds, params.date_from, params.date_to]
    .some((value) => value !== undefined)
  const subjectType = params.subject_type === "accumulator"
    ? "accumulator"
    : params.subject_type === "prediction" || hasMatchFilters
      ? "prediction"
      : "accumulator"
  const tickets = subjectType === "accumulator"
  const scope: PerformanceScope = params.scope === "research" || params.scope === "all" ? params.scope : "production"
  const since = requestedSince ? `${requestedSince}T00:00:00+02:00` : undefined
  const [report, primarySegments, modelSegments, bankroll, realResults] = await Promise.all([
    fetchPerformanceReport({ subject_type: subjectType, since, until: requestedUntil ? `${requestedUntil}T00:00:00+02:00` : undefined, market, selection, min_probability: minProbability, min_odds: minOdds, date_from: dateFrom, date_to: dateTo, scope }).catch(() => null),
    fetchPerformanceSegments({ by: tickets ? "product" : "market", subject_type: subjectType, since, until: requestedUntil ? `${requestedUntil}T00:00:00+02:00` : undefined, market, selection, min_probability: minProbability, min_odds: minOdds, date_from: dateFrom, date_to: dateTo, scope }).catch(() => null),
    tickets ? Promise.resolve(null) : fetchPerformanceSegments({ by: "model_version", subject_type: subjectType, since, until: requestedUntil ? `${requestedUntil}T00:00:00+02:00` : undefined, market, selection, min_probability: minProbability, min_odds: minOdds, date_from: dateFrom, date_to: dateTo, scope }).catch(() => null),
    fetchBankroll().catch(() => null),
    fetchRealBetResults().catch(() => null),
  ])

  if (!report) return <section className="rounded-xl border border-[var(--loss)] bg-[var(--bg-surface)] p-5 text-sm text-[var(--loss)]">Performance evidence is temporarily unavailable. No result is inferred while the report cannot be loaded.</section>

  const noun = tickets ? "ticket" : "selection"
  const decided = report.n_wins + report.n_losses
  const voids = report.n_voids + report.n_pushes
  const awaiting = report.n_awaiting ?? 0
  const flat = report.stake_basis === "flat_unit"
  const segmentRows = Object.entries(primarySegments?.segments ?? {}).sort(([a, ra], [b, rb]) =>
    tickets ? productRank(a) - productRank(b) || a.localeCompare(b) : rb.n_settled - ra.n_settled)
  const modelRows = Object.entries(modelSegments?.segments ?? {}).sort(([, a], [, b]) => b.n_settled - a.n_settled)
  const calibrationCount = report.calibration_bins?.reduce((total, bin) => total + bin.count, 0) ?? 0

  return <>
    <form method="get" className="flex flex-wrap items-end gap-3 border-b border-[var(--border)] pb-4" aria-label="Performance scope">
      <label className="grid gap-1 text-xs font-semibold text-[var(--text-secondary)]">Show<select name="subject_type" defaultValue={subjectType} className="h-11 min-w-48 rounded-lg border border-[var(--border)] bg-[var(--bg-raised)] px-3 text-sm font-normal text-[var(--text-primary)]"><option value="accumulator">Accumulator tickets</option><option value="prediction">Individual forecasts</option></select></label>
      {subjectType === "prediction" && <label className="grid gap-1 text-xs font-semibold text-[var(--text-secondary)]">Evidence<select name="scope" defaultValue={scope} className="h-11 min-w-48 rounded-lg border border-[var(--border)] bg-[var(--bg-raised)] px-3 text-sm font-normal text-[var(--text-primary)]"><option value="production">Production forecasts</option><option value="research">Research forecasts</option><option value="all">All forecasts</option></select></label>}
      <label className="grid gap-1 text-xs font-semibold text-[var(--text-secondary)]">Settled from<input type="date" name="since" defaultValue={requestedSince} className="h-11 rounded-lg border border-[var(--border)] bg-[var(--bg-raised)] px-3 text-sm font-normal text-[var(--text-primary)]" /></label>
      <label className="grid gap-1 text-xs font-semibold text-[var(--text-secondary)]">Settled before<input type="date" name="until" defaultValue={requestedUntil} className="h-11 rounded-lg border border-[var(--border)] bg-[var(--bg-raised)] px-3 text-sm font-normal text-[var(--text-primary)]" /></label>
      {subjectType === "prediction" && <>
        <label className="grid gap-1 text-xs font-semibold text-[var(--text-secondary)]">Match date from<input type="date" name="date_from" defaultValue={dateFrom} className="h-11 rounded-lg border border-[var(--border)] bg-[var(--bg-raised)] px-3 text-sm font-normal text-[var(--text-primary)]" /></label>
        <label className="grid gap-1 text-xs font-semibold text-[var(--text-secondary)]">Match date to<input type="date" name="date_to" defaultValue={dateTo} className="h-11 rounded-lg border border-[var(--border)] bg-[var(--bg-raised)] px-3 text-sm font-normal text-[var(--text-primary)]" /></label>
        <label className="grid gap-1 text-xs font-semibold text-[var(--text-secondary)]">Market<input name="market" defaultValue={market} placeholder="TOTAL_GOALS" className="h-11 w-40 rounded-lg border border-[var(--border)] bg-[var(--bg-raised)] px-3 text-sm font-normal text-[var(--text-primary)]" /></label>
        <label className="grid gap-1 text-xs font-semibold text-[var(--text-secondary)]">Selection<input name="selection" defaultValue={selection} placeholder="UNDER_2_5" className="h-11 w-40 rounded-lg border border-[var(--border)] bg-[var(--bg-raised)] px-3 text-sm font-normal text-[var(--text-primary)]" /></label>
        <label className="grid gap-1 text-xs font-semibold text-[var(--text-secondary)]">Min probability<input type="number" min="0" max="100" step="1" name="min_probability" defaultValue={minProbabilityPercent ?? ""} placeholder="60" className="h-11 w-32 rounded-lg border border-[var(--border)] bg-[var(--bg-raised)] px-3 text-sm font-normal text-[var(--text-primary)]" /></label>
        <label className="grid gap-1 text-xs font-semibold text-[var(--text-secondary)]">Min odds<input type="number" min="1.01" step="0.01" name="min_odds" defaultValue={minOdds} placeholder="1.80" className="h-11 w-32 rounded-lg border border-[var(--border)] bg-[var(--bg-raised)] px-3 text-sm font-normal text-[var(--text-primary)]" /></label>
      </>}
      <button type="submit" className="h-11 rounded-lg border border-[var(--accent)] bg-[var(--accent)] px-4 text-sm font-semibold text-[var(--bg-surface)] hover:bg-[var(--accent-hover)]">Apply</button>
    </form>

    <section
      className={`flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-3 text-sm ${awaiting > 0 ? "border-[var(--void)]/50 bg-[var(--void)]/10" : "border-[var(--border)] bg-[var(--bg-surface)]"} text-[var(--text-primary)]`}
      aria-label="Settlement status"
    >
      <span className="font-semibold">
        <span className={`mr-2 inline-block h-2.5 w-2.5 rounded-full ${decided ? "bg-[var(--win)]" : "bg-[var(--text-muted)]"}`} aria-hidden="true" />
        {decided || voids ? `${decided} ${noun}${decided === 1 ? "" : "s"} decided (${report.n_wins} won, ${report.n_losses} lost)${voids ? ` · ${voids} void` : ""}` : `No settled ${noun}s yet`}
      </span>
      <span className="text-[var(--text-secondary)]">
        {awaiting > 0 ? `${awaiting} ${noun}${awaiting === 1 ? "" : "s"} kicked off and awaiting a result` : "Nothing is waiting for a result"}
      </span>
    </section>

    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-7" aria-label="Headline results">
      <MetricCard label="Returns" value={fmtUnits(report.total_return)} sub="Gross returned from priced settled bets" valueTone={tone(report.total_return)} />
      <MetricCard label="Net P&amp;L" value={fmtUnits(report.total_profit)} sub={report.total_stake === null ? `No priced ${noun} settled yet` : `${report.total_stake.toFixed(0)} unit${report.total_stake === 1 ? "" : "s"} staked · ${report.n_priced} priced settled`} valueTone={tone(report.total_profit)} />
      <MetricCard label="ROI / yield" value={fmtSignedPct(report.roi)} sub="Priced settled selections only; voids refunded" valueTone={tone(report.roi)} />
      <MetricCard label="Hit rate" value={pct(report.hit_rate)} sub={report.break_even_hit_rate === null ? "Break-even unavailable" : `Break-even ${pct(report.break_even_hit_rate)} at these odds`} valueTone={report.hit_rate !== null && report.break_even_hit_rate !== null ? tone(report.hit_rate - report.break_even_hit_rate) : undefined} />
      <MetricCard label="Average odds" value={report.average_odds?.toFixed(2) ?? "—"} sub={`${report.n_priced} priced settled ${noun}${report.n_priced === 1 ? "" : "s"}`} />
      <MetricCard label="Max drawdown" value={report.max_drawdown === null ? "—" : `${report.max_drawdown.toFixed(2)} u`} sub="Worst peak-to-trough run" />
      <MetricCard label="Brier score" value={report.brier_score?.toFixed(3) ?? "—"} sub={calibrationCount ? `Lower is better · ${calibrationCount} scored` : "Lower is better"} />
    </section>

    <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--surface-shadow)]" aria-labelledby="segment-heading">
      <p className="text-xs font-semibold uppercase tracking-[.14em] text-[var(--accent)]">{tickets ? "By ticket type" : "By market"}</p>
      <div className="mt-2 flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="segment-heading" className="text-lg font-semibold text-[var(--text-primary)]">{tickets ? "Which accumulator types are making money" : "Which markets the forecasts beat"}</h2>
        <span className="text-xs text-[var(--text-muted)]">{flat ? `Flat 1-unit stake on ${report.n_priced} priced settled ${noun}${report.n_priced === 1 ? "" : "s"}` : "Recorded stakes"}</span>
      </div>
      {segmentRows.length
        ? <div className="mt-4"><SegmentTable caption={tickets ? "Results by accumulator type" : "Results by market"} nameHeader={tickets ? "Ticket type" : "Market"} rows={segmentRows} colorFor={tickets ? productColor : undefined} labelFor={tickets ? (p) => productLabel(p) : undefined} /></div>
        : <p className="mt-4 rounded-lg bg-[var(--bg-raised)] p-4 text-sm text-[var(--text-secondary)]">No {noun} has been settled in this scope yet{awaiting ? `; ${awaiting} ${awaiting === 1 ? "is" : "are"} awaiting a result` : ""}.</p>}
      {tickets && <p className="mt-4 text-xs text-[var(--text-muted)]">Daily Picks are built without the value gate; compare them with Core, Growth and Alpha rather than adding them together. <Link href="/performance?tab=periods" className="font-semibold text-[var(--accent)] hover:underline">See results by day, month and year →</Link></p>}
    </section>

    {!tickets && modelRows.length > 0 && <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--surface-shadow)]" aria-labelledby="model-heading">
      <p className="text-xs font-semibold uppercase tracking-[.14em] text-[var(--accent)]">By model version</p>
      <h2 id="model-heading" className="mt-2 text-lg font-semibold text-[var(--text-primary)]">Which model version produced these forecasts</h2>
      <div className="mt-4"><SegmentTable caption="Results by model version" nameHeader="Model version" rows={modelRows} /></div>
      <p className="mt-4 text-xs text-[var(--text-muted)]">Versions are listed on the <Link href="/models" className="font-semibold text-[var(--accent)] hover:underline">Models</Link> page.</p>
    </section>}

    <RealMoney bankroll={bankroll} results={realResults} />

    <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--surface-shadow)]" aria-labelledby="reading-heading">
      <h2 id="reading-heading" className="text-base font-semibold text-[var(--text-primary)]">How to read these numbers</h2>
      <ul className="mt-3 grid gap-2 text-sm leading-6 text-[var(--text-secondary)] md:grid-cols-2">
        <li><strong className="text-[var(--text-primary)]">Evidence scope:</strong> {scopeLabel(scope)}. Research rows are excluded from the production view and must not be used as live-model promotion evidence.</li>
        <li><strong className="text-[var(--text-primary)]">Priced denominator:</strong> hit rate and predictive metrics cover all settled forecasts in scope; ROI, P&amp;L and drawdown cover only the {report.n_priced} settled forecasts with usable odds.</li>
        <li><strong className="text-[var(--text-primary)]">1-unit figures</strong> assume the same stake on every priced {noun} at the archived price, so types can be compared fairly. Your actual money is in the Real money panel.</li>
        <li><strong className="text-[var(--text-primary)]">Hit rate vs break-even:</strong> a type is profitable when it wins more often than its odds require.</li>
        <li><strong className="text-[var(--text-primary)]">Tickets settle automatically</strong> as soon as the result is certain: one lost leg loses the ticket immediately; a win needs every leg settled.</li>
        <li><strong className="text-[var(--text-primary)]">Sample size:</strong> {report.n_priced < 30 ? `only ${report.n_priced} priced settled so far, so ROI and hit rate can still swing a lot.` : `${report.n_priced} priced settled; keep watching drawdown alongside ROI.`}</li>
      </ul>
    </section>

    {report.calibration_bins && report.calibration_bins.length > 0 && <section aria-label="Calibration curve"><p className="mb-3 text-xs font-semibold uppercase tracking-[.14em] text-[var(--accent)]">Reliability diagram · predicted vs actual win rate</p><CalibrationCurveChart bins={report.calibration_bins} /></section>}
  </>
}
