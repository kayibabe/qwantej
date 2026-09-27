import type { Metadata } from "next"
import Link from "next/link"
import { Suspense } from "react"
import { fetchAccumulatorResults, fetchAllAccumulators } from "@/lib/api"
import type { AccumulatorOut, AccumulatorPeriodResultOut } from "@/lib/types"
import {
  focusMonth,
  parsePeriod,
  periodAnchor,
  periodLabel,
  periodWindow,
  productDay,
  summarisePeriod,
  ticketArchiveHref,
} from "@/lib/tickets"
import LiveMatchRefresh from "@/components/LiveMatchRefresh"
import DayGroup from "@/components/tickets/DayGroup"
import GroupSummary, { Chevron } from "@/components/tickets/GroupSummary"
import ScrollToHash from "@/components/tickets/ScrollToHash"

export const metadata: Metadata = { title: "Tickets" }

// The API returns at most this many periods per granularity, newest first.
const PERIOD_LIMIT = 1000

type Request = { year?: string; month?: string; date?: string }

function Unavailable() {
  return (
    <section className="rounded-lg border border-[var(--loss)]/60 bg-[var(--bg-surface)] p-5" aria-live="polite">
      <h2 className="font-semibold text-[var(--loss)]">The ticket archive is temporarily unavailable</h2>
      <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">We could not load archived tickets. Refresh this page in a moment.</p>
    </section>
  )
}

function groupTicketsByDay(tickets: AccumulatorOut[]): Map<string, AccumulatorOut[]> {
  const byDay = new Map<string, AccumulatorOut[]>()
  for (const acc of tickets) {
    const day = productDay(acc.published_at)
    byDay.set(day, [...(byDay.get(day) ?? []), acc])
  }
  return byDay
}

async function TicketTree({ request }: { request: Request }) {
  const [years, months, days] = await Promise.all([
    fetchAccumulatorResults({ granularity: "year", limit: PERIOD_LIMIT }),
    fetchAccumulatorResults({ granularity: "month", limit: PERIOD_LIMIT }),
    fetchAccumulatorResults({ granularity: "day", limit: PERIOD_LIMIT }),
  ]).catch(() => [null, null, null] as const)
  if (!years || !months || !days) return <Unavailable />
  if (years.periods.length === 0) {
    return <p className="rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg-surface)] p-6 text-sm text-[var(--text-secondary)]">No tickets have been published yet.</p>
  }

  const focus = focusMonth(request, months.periods.map((m) => m.period))
  let dayPeriods: AccumulatorPeriodResultOut[] = days.periods
  // The day list is capped; make sure the month being opened has its days.
  if (focus && days.total_periods > days.periods.length && !dayPeriods.some((d) => d.period.startsWith(focus))) {
    const extra = await fetchAccumulatorResults({ granularity: "day", limit: 31, ...periodWindow(focus) }).catch(() => null)
    if (extra) dayPeriods = [...dayPeriods, ...extra.periods]
  }

  // The opened month's tickets load with the page (and refresh with it);
  // other days load when expanded. Only a complete load pre-opens its days.
  const focusTickets = focus ? await fetchAllAccumulators(periodWindow(focus)).catch(() => null) : null
  const complete = focusTickets !== null && focusTickets.items.length >= focusTickets.total
  const focusByDay = complete ? groupTicketsByDay(focusTickets.items) : null

  return (
    <div className="flex flex-col gap-4">
      <ScrollToHash />
      {years.periods.map((y) => {
        const yearMonths = months.periods.filter((m) => m.period.startsWith(`${y.period}-`))
        return (
          <details key={y.period} id={periodAnchor("year", y.period)} open={focus?.startsWith(`${y.period}-`)} className="group/year scroll-mt-4 rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] shadow-[var(--surface-shadow)]">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-xl bg-[var(--bg-raised)] px-5 py-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] group-open/year:rounded-b-none [&::-webkit-details-marker]:hidden">
              <span className="text-lg font-semibold text-[var(--text-primary)]">{y.period}</span>
              <span className="flex items-center gap-3"><GroupSummary s={summarisePeriod(y)} /><Chevron group="year" /></span>
            </summary>
            <div className="flex flex-col gap-3 p-3 sm:p-4">
              {yearMonths.map((m) => {
                const monthDays = dayPeriods.filter((d) => d.period.startsWith(`${m.period}-`))
                const isFocus = m.period === focus
                return (
                  <details key={m.period} id={periodAnchor("month", m.period)} open={isFocus} className="group/month scroll-mt-4">
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] px-4 py-3 transition-colors hover:border-[var(--text-muted)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] group-open/month:border-[var(--text-primary)] [&::-webkit-details-marker]:hidden">
                      <span className="text-sm font-semibold uppercase tracking-wider text-[var(--accent)]">{periodLabel(m.period, "month")}</span>
                      <span className="flex items-center gap-3"><GroupSummary s={summarisePeriod(m)} /><Chevron group="month" /></span>
                    </summary>
                    <div className="flex flex-col gap-3 pt-3 sm:pl-3">
                      {monthDays.length ? monthDays.map((d) => {
                        const initial = isFocus && focusByDay ? focusByDay.get(d.period) ?? [] : null
                        return <DayGroup key={d.period} summary={summarisePeriod(d)} initialTickets={initial} defaultOpen={initial !== null} />
                      }) : (
                        <p className="px-1 text-sm text-[var(--text-secondary)]">
                          <Link href={ticketArchiveHref("month", m.period)} className="font-semibold text-[var(--accent)] hover:underline">Open {periodLabel(m.period, "month")}</Link> to list its days.
                        </p>
                      )}
                    </div>
                  </details>
                )
              })}
            </div>
          </details>
        )
      })}
    </div>
  )
}

export default async function AccumulatorsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const sp = await searchParams
  const str = (k: string) => (typeof sp[k] === "string" ? (sp[k] as string) : undefined)
  const request: Request = {
    year: parsePeriod(str("year"), "year"),
    month: parsePeriod(str("month"), "month"),
    date: parsePeriod(str("date"), "day"),
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 p-4 sm:p-8">
      <LiveMatchRefresh />
      <div>
        <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Tickets</h1>
        <p className="mt-1 max-w-3xl text-sm text-[var(--text-secondary)]">
          Every published ticket by year, month and day (Africa/Blantyre publication time). A ticket is lost as soon as one leg
          loses and won once every leg is settled; void legs drop out. P&amp;L is a flat 1-unit stake per ticket. Open a ticket
          for its matches, prices, live scores and settlement.
        </p>
      </div>
      <Suspense key={JSON.stringify(request)} fallback={<p className="animate-pulse text-sm text-[var(--text-muted)]">Loading…</p>}>
        <TicketTree request={request} />
      </Suspense>
    </div>
  )
}
