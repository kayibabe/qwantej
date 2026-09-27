import type { Metadata } from "next"
import Link from "next/link"
import { Suspense } from "react"
import { fetchAccumulatorResults, fetchAccumulators } from "@/lib/api"
import { fmtDatetime, fmtUnits } from "@/lib/format"
import type { AccumulatorOut, ResultsGranularity } from "@/lib/types"
import {
  RESULT_LABEL,
  parsePeriod,
  periodLabel,
  periodWindow,
  productColor,
  productLabel,
  resultClass,
  summarisePeriod,
} from "@/lib/tickets"
import Pagination from "@/components/Pagination"
import LiveMatchRefresh from "@/components/LiveMatchRefresh"

export const metadata: Metadata = { title: "Tickets" }

const DAY_LIMIT = 50

type Level =
  | { kind: "years" }
  | { kind: "months"; year: string }
  | { kind: "days"; month: string }
  | { kind: "tickets"; date: string }

function resolveLevel(sp: Record<string, string | string[] | undefined>): Level {
  const str = (k: string) => (typeof sp[k] === "string" ? (sp[k] as string) : undefined)
  const date = parsePeriod(str("date"), "day")
  if (date) return { kind: "tickets", date }
  const month = parsePeriod(str("month"), "month")
  if (month) return { kind: "days", month }
  const year = parsePeriod(str("year"), "year")
  if (year) return { kind: "months", year }
  return { kind: "years" }
}

function Breadcrumbs({ level }: { level: Level }) {
  const crumbs: { href: string; label: string }[] = [{ href: "/accumulators", label: "All years" }]
  const year = level.kind === "months" ? level.year : level.kind === "days" ? level.month.slice(0, 4) : level.kind === "tickets" ? level.date.slice(0, 4) : undefined
  const month = level.kind === "days" ? level.month : level.kind === "tickets" ? level.date.slice(0, 7) : undefined
  if (year) crumbs.push({ href: `/accumulators?year=${year}`, label: year })
  if (month) crumbs.push({ href: `/accumulators?month=${month}`, label: periodLabel(month, "month") })
  if (level.kind === "tickets") crumbs.push({ href: `/accumulators?date=${level.date}`, label: periodLabel(level.date, "day") })
  return (
    <nav aria-label="Ticket archive location" className="flex flex-wrap items-center gap-1.5 text-sm">
      {crumbs.map((c, i) => {
        const last = i === crumbs.length - 1
        return (
          <span key={c.href} className="flex items-center gap-1.5">
            {i > 0 && <span aria-hidden="true" className="text-[var(--text-muted)]">›</span>}
            {last
              ? <span aria-current="page" className="font-semibold text-[var(--text-primary)]">{c.label}</span>
              : <Link href={c.href} className="text-[var(--accent)] hover:underline">{c.label}</Link>}
          </span>
        )
      })}
    </nav>
  )
}

function Unavailable() {
  return (
    <section className="rounded-lg border border-[var(--loss)]/60 bg-[var(--bg-surface)] p-5" aria-live="polite">
      <h2 className="font-semibold text-[var(--loss)]">The ticket archive is temporarily unavailable</h2>
      <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">We could not load archived tickets. Refresh this page in a moment.</p>
    </section>
  )
}

const CHILD: Record<"years" | "months" | "days", { granularity: ResultsGranularity; param: string; heading: string }> = {
  years: { granularity: "year", param: "year", heading: "Year" },
  months: { granularity: "month", param: "month", heading: "Month" },
  days: { granularity: "day", param: "date", heading: "Day" },
}

async function PeriodList({ level }: { level: Exclude<Level, { kind: "tickets" }> }) {
  const child = CHILD[level.kind]
  const window = level.kind === "months" ? periodWindow(level.year) : level.kind === "days" ? periodWindow(level.month) : undefined
  const data = await fetchAccumulatorResults({ granularity: child.granularity, limit: 1000, ...window }).catch(() => null)
  if (!data) return <Unavailable />
  if (data.periods.length === 0) {
    return <p className="rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg-surface)] p-6 text-sm text-[var(--text-secondary)]">No tickets were published in this period.</p>
  }
  const rows = data.periods.map(summarisePeriod)
  return (
    <div className="overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] shadow-[var(--surface-shadow)]">
      <table className="w-full text-sm">
        <caption className="sr-only">Tickets per {child.heading.toLowerCase()}, newest first. Choose a {child.heading.toLowerCase()} to open it.</caption>
        <thead className="border-b border-[var(--border)] text-xs uppercase tracking-wider text-[var(--text-muted)]">
          <tr>
            <th scope="col" className="px-4 py-3 text-left font-semibold">{child.heading}</th>
            <th scope="col" className="px-4 py-3 text-right font-semibold">Tickets</th>
            <th scope="col" className="px-4 py-3 text-right font-semibold">Won</th>
            <th scope="col" className="px-4 py-3 text-right font-semibold">Lost</th>
            <th scope="col" className="hidden px-4 py-3 text-right font-semibold sm:table-cell">Void</th>
            <th scope="col" className="px-4 py-3 text-right font-semibold">Pending</th>
            <th scope="col" className="hidden px-4 py-3 text-right font-semibold sm:table-cell">Win rate</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.period} className="relative border-t border-[var(--border-subtle)] transition-colors hover:bg-[var(--bg-raised)] focus-within:bg-[var(--bg-raised)]">
              <th scope="row" className="px-4 py-3 text-left font-medium">
                {/* The link's ::after covers the row so the whole row is clickable. */}
                <Link href={`/accumulators?${child.param}=${r.period}`} className="text-[var(--accent)] after:absolute after:inset-0 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]">
                  <time dateTime={r.period}>{periodLabel(r.period, child.granularity)}</time>
                </Link>
              </th>
              <td className="px-4 py-3 text-right font-mono">{r.total}</td>
              <td className={`px-4 py-3 text-right font-mono ${r.won ? "font-semibold text-[var(--win)]" : "text-[var(--text-muted)]"}`}>{r.won}</td>
              <td className={`px-4 py-3 text-right font-mono ${r.lost ? "text-[var(--loss)]" : "text-[var(--text-muted)]"}`}>{r.lost}</td>
              <td className="hidden px-4 py-3 text-right font-mono text-[var(--text-muted)] sm:table-cell">{r.void}</td>
              <td className="px-4 py-3 text-right font-mono text-[var(--text-secondary)]">{r.pending}</td>
              <td className="hidden px-4 py-3 text-right font-mono text-[var(--text-secondary)] sm:table-cell">{r.winRate === null ? "—" : `${(r.winRate * 100).toFixed(0)}%`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function firstKickoff(acc: AccumulatorOut): string | null {
  const times = acc.legs.map((l) => l.kickoff_utc).filter((t): t is string => Boolean(t)).sort()
  return times[0] ?? null
}

async function DayTickets({ date, offset }: { date: string; offset: number }) {
  const page = await fetchAccumulators({ date, limit: DAY_LIMIT, offset }).catch(() => null)
  if (!page) return <Unavailable />
  if (page.items.length === 0) {
    return <p className="rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg-surface)] p-6 text-sm text-[var(--text-secondary)]">No tickets were published on this day.</p>
  }
  return (
    <>
      <ul className="flex flex-col gap-2" aria-label={`Tickets published ${periodLabel(date, "day")}`}>
        {page.items.map((acc) => {
          const result = acc.result ?? "pending"
          const kickoff = firstKickoff(acc)
          return (
            <li key={acc.id}>
              <Link
                href={`/accumulators/${acc.id}`}
                className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] px-4 py-3 shadow-[var(--surface-shadow)] transition-colors hover:bg-[var(--bg-raised)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] sm:grid-cols-[minmax(160px,1.2fr)_repeat(3,minmax(80px,1fr))_auto]"
                style={{ borderLeftWidth: "4px", borderLeftColor: productColor(acc.product) }}
              >
                <span className="min-w-0">
                  <span className="block text-sm font-bold uppercase tracking-wide" style={{ color: productColor(acc.product) }}>{productLabel(acc.product)} ACCA</span>
                  <span className="block text-xs text-[var(--text-muted)]">{acc.legs.length} leg{acc.legs.length === 1 ? "" : "s"}{kickoff ? ` · first kickoff ${fmtDatetime(kickoff)}` : ""}</span>
                </span>
                <span className={`justify-self-end rounded border px-2 py-0.5 text-xs font-bold tracking-wide sm:order-last ${resultClass(result)}`}>{RESULT_LABEL[result]}</span>
                <span className="text-xs text-[var(--text-muted)]">Odds <strong className="font-mono text-sm text-[var(--text-primary)]">{acc.combined_odds.toFixed(2)}</strong></span>
                <span className="hidden text-xs text-[var(--text-muted)] sm:block">Probability <strong className="font-mono text-sm text-[var(--text-primary)]">{(acc.conservative_joint_probability * 100).toFixed(1)}%</strong></span>
                <span className="text-xs text-[var(--text-muted)] max-sm:justify-self-end">1-unit P&amp;L <strong className={`font-mono text-sm ${acc.profit_units == null ? "text-[var(--text-secondary)]" : acc.profit_units > 0 ? "text-[var(--win)]" : acc.profit_units < 0 ? "text-[var(--loss)]" : "text-[var(--text-primary)]"}`}>{fmtUnits(acc.profit_units)}</strong></span>
              </Link>
            </li>
          )
        })}
      </ul>
      <Pagination total={page.total} limit={page.limit} offset={page.offset} />
    </>
  )
}

const TITLES: Record<Level["kind"], (l: Level) => string> = {
  years: () => "Tickets by year",
  months: (l) => `Tickets in ${(l as { year: string }).year}`,
  days: (l) => `Tickets in ${periodLabel((l as { month: string }).month, "month")}`,
  tickets: (l) => `Tickets published ${periodLabel((l as { date: string }).date, "day")}`,
}

export default async function AccumulatorsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const sp = await searchParams
  const level = resolveLevel(sp)
  const offset = Math.max(0, Number(sp.offset ?? 0) || 0)

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 p-4 sm:p-8">
      {level.kind === "tickets" && <LiveMatchRefresh />}
      <div className="flex flex-col gap-3">
        <Breadcrumbs level={level} />
        <div>
          <h1 className="text-2xl font-semibold text-[var(--text-primary)]">{TITLES[level.kind](level)}</h1>
          <p className="mt-1 max-w-3xl text-sm text-[var(--text-secondary)]">
            {level.kind === "tickets"
              ? "Open a ticket to see its matches, prices, live scores and settlement."
              : "Grouped by publication day in Africa/Blantyre time. A ticket is lost as soon as one leg loses and won once every leg is settled; void legs drop out."}
          </p>
        </div>
      </div>

      <Suspense key={JSON.stringify(level) + offset} fallback={<p className="animate-pulse text-sm text-[var(--text-muted)]">Loading…</p>}>
        {level.kind === "tickets" ? <DayTickets date={level.date} offset={offset} /> : <PeriodList level={level} />}
      </Suspense>
    </div>
  )
}
