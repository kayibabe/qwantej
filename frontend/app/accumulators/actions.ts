"use server"

import { fetchAllAccumulators } from "@/lib/api"
import { parsePeriod, periodWindow } from "@/lib/tickets"
import type { AccumulatorOut } from "@/lib/types"

/**
 * Tickets published on one product day, for a day group the reader expands
 * on the Tickets page. Returns the same read-only data the page itself
 * renders; null when the day is malformed or the API is unavailable.
 */
export async function loadDayTickets(date: unknown): Promise<AccumulatorOut[] | null> {
  const day = parsePeriod(typeof date === "string" ? date : undefined, "day")
  if (!day) return null
  try {
    return (await fetchAllAccumulators({ date: day })).items
  } catch {
    return null
  }
}

/** Load immutable ticket rows for a simulator year/month/day scope. */
export async function loadSimulationTickets(
  granularity: unknown,
  period: unknown,
): Promise<AccumulatorOut[] | null> {
  const kind = granularity === "year" || granularity === "month" || granularity === "day" ? granularity : undefined
  if (!kind) return null
  const parsed = parsePeriod(typeof period === "string" ? period : undefined, kind)
  if (!parsed) return null
  try {
    const { since, until } = periodWindow(parsed)
    return (await fetchAllAccumulators({ since, until })).items
  } catch {
    return null
  }
}
