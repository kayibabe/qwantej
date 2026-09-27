import type { Metadata } from "next"
import Link from "next/link"
import { notFound } from "next/navigation"
import { fetchAccumulator } from "@/lib/api"
import { fmtDatetime, fmtUnits } from "@/lib/format"
import { RESULT_LABEL, periodLabel, productLabel, resultClass } from "@/lib/tickets"
import AccumulatorCard from "@/components/AccumulatorCard"
import LiveMatchRefresh from "@/components/LiveMatchRefresh"

export const metadata: Metadata = { title: "Ticket" }

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** Product day (Africa/Blantyre) a ticket was published on, YYYY-MM-DD. */
function productDay(iso: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Blantyre" }).format(new Date(iso))
}

export default async function TicketPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  if (!UUID.test(id)) notFound()
  const acc = await fetchAccumulator(id).catch((err: Error) => (String(err.message).includes(" 404 ") ? undefined : null))
  if (acc === undefined) notFound()

  if (acc === null) {
    return (
      <div className="mx-auto w-full max-w-4xl p-4 sm:p-8">
        <section className="rounded-lg border border-[var(--loss)]/60 bg-[var(--bg-surface)] p-5" aria-live="polite">
          <h1 className="font-semibold text-[var(--loss)]">This ticket could not be loaded</h1>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">The ticket archive is temporarily unavailable. Refresh in a moment, or <Link href="/accumulators" className="text-[var(--accent)] hover:underline">return to the archive</Link>.</p>
        </section>
      </div>
    )
  }

  const day = productDay(acc.published_at)
  const result = acc.result ?? "pending"

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-5 p-4 sm:p-8">
      <LiveMatchRefresh />
      <nav aria-label="Ticket archive location" className="flex flex-wrap items-center gap-1.5 text-sm">
        <Link href="/accumulators" className="text-[var(--accent)] hover:underline">All years</Link>
        <span aria-hidden="true" className="text-[var(--text-muted)]">›</span>
        <Link href={`/accumulators?year=${day.slice(0, 4)}`} className="text-[var(--accent)] hover:underline">{day.slice(0, 4)}</Link>
        <span aria-hidden="true" className="text-[var(--text-muted)]">›</span>
        <Link href={`/accumulators?month=${day.slice(0, 7)}`} className="text-[var(--accent)] hover:underline">{periodLabel(day.slice(0, 7), "month")}</Link>
        <span aria-hidden="true" className="text-[var(--text-muted)]">›</span>
        <Link href={`/accumulators?date=${day}`} className="text-[var(--accent)] hover:underline">{periodLabel(day, "day")}</Link>
        <span aria-hidden="true" className="text-[var(--text-muted)]">›</span>
        <span aria-current="page" className="font-semibold text-[var(--text-primary)]">{productLabel(acc.product)} ticket</span>
      </nav>

      <section aria-label="Ticket result" className="grid gap-3 sm:grid-cols-4">
        {[
          { label: "Result", value: <span className={`inline-flex rounded border px-2 py-0.5 text-sm font-bold ${resultClass(result)}`}>{RESULT_LABEL[result]}</span> },
          { label: "Published odds", value: `${acc.combined_odds.toFixed(2)}×` },
          { label: "Settled at odds", value: acc.settlement_odds == null ? "—" : `${acc.settlement_odds.toFixed(2)}×` },
          { label: "P&L (1-unit stake)", value: fmtUnits(acc.profit_units) },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] px-4 py-3 shadow-[var(--surface-shadow)]">
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">{label}</p>
            <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">{value}</p>
          </div>
        ))}
      </section>
      <p className="-mt-2 text-xs text-[var(--text-muted)]">Published {fmtDatetime(acc.published_at)} (Africa/Blantyre). Void legs drop out of a winning ticket&apos;s odds.</p>

      <AccumulatorCard acc={acc} />
    </div>
  )
}
