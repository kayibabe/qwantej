"use client"

import { useEffect, useState } from "react"
import { loadDayTickets } from "@/app/accumulators/actions"
import { longDayLabel, periodAnchor, type PeriodSummary } from "@/lib/tickets"
import type { AccumulatorOut } from "@/lib/types"
import GroupSummary, { Chevron } from "@/components/tickets/GroupSummary"
import TicketRow from "@/components/tickets/TicketRow"

/**
 * One product day on the Tickets page. Days of the month the page opened on
 * arrive with their tickets (and refresh with the page); any other day loads
 * its tickets when expanded and on every server refresh while open.
 */
export default function DayGroup({
  summary,
  initialTickets,
  defaultOpen,
  refreshToken,
}: {
  summary: PeriodSummary
  initialTickets: AccumulatorOut[] | null
  defaultOpen: boolean
  refreshToken: string
}) {
  const day = summary.period
  const [open, setOpen] = useState(defaultOpen)
  const [retry, setRetry] = useState(0)
  const revision = `${day}:${refreshToken}:${retry}`
  const [loaded, setLoaded] = useState<{ revision: string; tickets: AccumulatorOut[] | null } | null>(null)
  const current = loaded?.revision === revision ? loaded : null
  const tickets = initialTickets ?? current?.tickets ?? null
  const status = tickets ? "idle" : current ? "error" : "loading"

  useEffect(() => {
    if (!open || initialTickets !== null) return
    let active = true
    loadDayTickets(day).then(
      (tickets) => { if (active) setLoaded({ revision, tickets }) },
      () => { if (active) setLoaded({ revision, tickets: null }) },
    )
    return () => { active = false }
  }, [day, revision, open, initialTickets])

  function onToggle(event: React.SyntheticEvent<HTMLDetailsElement>) {
    const nowOpen = event.currentTarget.open
    setOpen(nowOpen)
  }

  return (
    <details id={periodAnchor("day", day)} open={open} onToggle={onToggle} className="group/day scroll-mt-4">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-lg border border-[var(--accent)]/30 bg-[var(--accent-soft)] px-4 py-2.5 transition-colors hover:border-[var(--accent)]/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] [&::-webkit-details-marker]:hidden">
        <time dateTime={day} className="text-sm font-semibold uppercase tracking-wider text-[var(--accent)]">{longDayLabel(day)}</time>
        <span className="flex items-center gap-3"><GroupSummary s={summary} /><Chevron group="day" /></span>
      </summary>
      <div className="pt-2" aria-live="polite" aria-busy={status === "loading"}>
        {tickets ? (
          tickets.length ? (
            <ul className="flex flex-col gap-2" aria-label={`Tickets published ${longDayLabel(day)}`}>
              {tickets.map((acc) => <TicketRow key={acc.id} acc={acc} />)}
            </ul>
          ) : (
            <p className="rounded-lg border border-dashed border-[var(--border)] p-4 text-sm text-[var(--text-secondary)]">No tickets were published on this day.</p>
          )
        ) : status === "error" ? (
          <p className="flex flex-wrap items-center gap-3 rounded-lg border border-[var(--loss)]/50 p-4 text-sm text-[var(--text-secondary)]">
            <span>This day&apos;s tickets could not be loaded.</span>
            <button type="button" onClick={() => setRetry((value) => value + 1)} className="rounded border border-[var(--border)] px-3 py-1 font-medium text-[var(--accent)] hover:bg-[var(--bg-raised)] focus-visible:outline-2 focus-visible:outline-[var(--accent)]">Try again</button>
          </p>
        ) : (
          <p className="animate-pulse p-4 text-sm text-[var(--text-muted)]">Loading tickets…</p>
        )}
      </div>
    </details>
  )
}
