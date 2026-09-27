import { fmtUnits } from "@/lib/format"
import type { PeriodSummary } from "@/lib/tickets"

function tone(profit: number | null) {
  if (profit === null || profit === 0) return "text-[var(--text-secondary)]"
  return profit > 0 ? "text-[var(--win)]" : "text-[var(--loss)]"
}

/** Right-hand side of a year/month/day heading: count, record and 1-unit P&L. */
export default function GroupSummary({ s }: { s: PeriodSummary }) {
  const record = [
    `${s.won}W`,
    `${s.lost}L`,
    s.winRate === null ? null : `${Math.round(s.winRate * 100)}% won`,
    s.void ? `${s.void} void` : null,
    s.pending ? `${s.pending} pending` : null,
  ]
    .filter(Boolean)
    .join(" · ")
  return (
    <span className="flex flex-wrap items-baseline justify-end gap-x-3 gap-y-0.5 text-sm font-normal normal-case tracking-normal">
      <span className="text-[var(--text-muted)]">{s.total} ticket{s.total === 1 ? "" : "s"}</span>
      <span className="hidden font-mono text-xs text-[var(--text-secondary)] sm:inline">{record}</span>
      {s.profit !== null && (
        <span className={`font-mono font-semibold ${tone(s.profit)}`} title="Flat 1-unit P&L of decided tickets">
          {fmtUnits(s.profit)}
        </span>
      )}
    </span>
  )
}

/** Disclosure chevron that flips when its <details> group opens. */
export function Chevron({ group }: { group: "year" | "month" | "day" }) {
  const rotate = { year: "group-open/year:rotate-180", month: "group-open/month:rotate-180", day: "group-open/day:rotate-180" }[group]
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className={`h-4 w-4 shrink-0 text-[var(--text-muted)] transition-transform ${rotate}`}>
      <path d="M5 8l5 5 5-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
