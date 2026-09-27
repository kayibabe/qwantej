import type { AccumulatorPeriodResultOut, ResultsGranularity, TicketResult } from "./types"

/**
 * Shared ticket vocabulary so Today, Tickets and Performance describe the
 * same ticket the same way. Periods are the Africa/Blantyre product day
 * (UTC+2, no daylight saving) — the calendar the API groups by.
 */

const PRODUCT_DAY_OFFSET = "+02:00"

// Value products first, then the separate Daily Picks line, then anything new.
const PRODUCT_ORDER = ["core", "growth", "alpha", "daily_safe", "daily_balanced", "daily_bold"]

export function productRank(product: string): number {
  const i = PRODUCT_ORDER.indexOf(product.toLowerCase())
  return i === -1 ? PRODUCT_ORDER.length : i
}

/** "daily_safe" → "Daily Safe". */
export function productLabel(product: string): string {
  return product
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ")
}

export function isDailyPick(product: string): boolean {
  return product.toLowerCase().startsWith("daily_")
}

export function productColor(product: string): string {
  const p = product.toLowerCase()
  if (isDailyPick(p)) return "var(--daily)"
  if (p === "core" || p === "growth" || p === "alpha") return `var(--${p})`
  return "var(--text-secondary)"
}

export const RESULT_LABEL: Record<TicketResult, string> = {
  won: "WON",
  lost: "LOST",
  void: "VOID",
  pending: "PENDING",
}

export function resultClass(result: string | undefined): string {
  if (result === "won") return "text-[var(--win)] border-[var(--win)]/40 bg-[var(--win)]/10"
  if (result === "lost") return "text-[var(--loss)] border-[var(--loss)]/40 bg-[var(--loss)]/10"
  if (result === "void") return "text-[var(--void)] border-[var(--void)]/40 bg-[var(--void)]/10"
  return "text-[var(--text-secondary)] border-[var(--border)] bg-[var(--bg-raised)]"
}

/** Start/end (exclusive) of a product-day period as ISO-8601 with offset. */
export function periodWindow(period: string): { since: string; until: string } {
  const parts = period.split("-").map(Number)
  const [y, m, d] = parts
  let start: [number, number, number]
  let end: [number, number, number]
  if (parts.length === 1) {
    start = [y, 1, 1]
    end = [y + 1, 1, 1]
  } else if (parts.length === 2) {
    start = [y, m, 1]
    end = m === 12 ? [y + 1, 1, 1] : [y, m + 1, 1]
  } else {
    const next = new Date(Date.UTC(y, m - 1, d + 1))
    start = [y, m, d]
    end = [next.getUTCFullYear(), next.getUTCMonth() + 1, next.getUTCDate()]
  }
  const iso = ([yy, mm, dd]: [number, number, number]) =>
    `${String(yy).padStart(4, "0")}-${String(mm).padStart(2, "0")}-${String(dd).padStart(2, "0")}T00:00:00${PRODUCT_DAY_OFFSET}`
  return { since: iso(start), until: iso(end) }
}

/** "2026" / "Sep 2026" / "Wed 23 Sep 2026". */
export function periodLabel(period: string, granularity: ResultsGranularity): string {
  if (granularity === "year") return period
  const [y, m, d] = period.split("-").map(Number)
  return new Date(Date.UTC(y, m - 1, d ?? 1)).toLocaleDateString("en-GB", {
    timeZone: "UTC",
    ...(granularity === "day" ? { weekday: "short", day: "numeric" } : {}),
    month: granularity === "month" ? "long" : "short",
    year: "numeric",
  })
}

export interface PeriodSummary {
  period: string
  won: number
  lost: number
  void: number
  pending: number
  total: number
  /** Won over decided (won + lost); null until one is decided. */
  winRate: number | null
}

/** Collapse a period's per-product tallies into one row. */
export function summarisePeriod(period: AccumulatorPeriodResultOut): PeriodSummary {
  const t = period.products.reduce(
    (acc, p) => ({
      won: acc.won + p.won,
      lost: acc.lost + p.lost,
      void: acc.void + p.void,
      pending: acc.pending + p.pending,
    }),
    { won: 0, lost: 0, void: 0, pending: 0 },
  )
  const decided = t.won + t.lost
  return {
    period: period.period,
    ...t,
    total: t.won + t.lost + t.void + t.pending,
    winRate: decided ? t.won / decided : null,
  }
}

/** Validates the drill-down query: "2026", "2026-09" or "2026-09-23". */
export function parsePeriod(value: string | undefined, granularity: ResultsGranularity): string | undefined {
  if (!value) return undefined
  const pattern = granularity === "year" ? /^\d{4}$/ : granularity === "month" ? /^\d{4}-(0[1-9]|1[0-2])$/ : /^\d{4}-\d{2}-\d{2}$/
  if (!pattern.test(value)) return undefined
  if (granularity === "day") {
    const [y, m, d] = value.split("-").map(Number)
    const dt = new Date(Date.UTC(y, m - 1, d))
    if (dt.getUTCMonth() !== m - 1 || dt.getUTCDate() !== d) return undefined
  }
  return value
}
