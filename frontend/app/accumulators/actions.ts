"use server"

import { fetchAllAccumulators } from "@/lib/api"
import { parsePeriod } from "@/lib/tickets"
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
