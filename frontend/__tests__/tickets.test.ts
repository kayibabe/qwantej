import { describe, expect, it } from "vitest"
import { marketLabel, selectionLabel } from "@/lib/forecasts"
import { fmtSignedPct, fmtUnits } from "@/lib/format"
import {
  focusMonth,
  longDayLabel,
  parsePeriod,
  periodLabel,
  periodWindow,
  productDay,
  productLabel,
  productRank,
  simulateTicketStake,
  summarisePeriod,
  ticketArchiveHref,
} from "@/lib/tickets"

describe("periodWindow (Africa/Blantyre product day)", () => {
  it("spans a whole year", () => {
    expect(periodWindow("2026")).toEqual({ since: "2026-01-01T00:00:00+02:00", until: "2027-01-01T00:00:00+02:00" })
  })

  it("rolls December into the next year", () => {
    expect(periodWindow("2026-12")).toEqual({ since: "2026-12-01T00:00:00+02:00", until: "2027-01-01T00:00:00+02:00" })
  })

  it("rolls the last day of a month into the next month", () => {
    expect(periodWindow("2026-02-28")).toEqual({ since: "2026-02-28T00:00:00+02:00", until: "2026-03-01T00:00:00+02:00" })
  })
})

describe("parsePeriod", () => {
  it("accepts well-formed periods", () => {
    expect(parsePeriod("2026", "year")).toBe("2026")
    expect(parsePeriod("2026-09", "month")).toBe("2026-09")
    expect(parsePeriod("2026-09-23", "day")).toBe("2026-09-23")
  })

  it("rejects malformed or impossible periods", () => {
    expect(parsePeriod("2026-13", "month")).toBeUndefined()
    expect(parsePeriod("2026-02-30", "day")).toBeUndefined()
    expect(parsePeriod("26", "year")).toBeUndefined()
    expect(parsePeriod("2026-09-23'--", "day")).toBeUndefined()
    expect(parsePeriod(undefined, "day")).toBeUndefined()
  })
})

describe("summarisePeriod", () => {
  it("adds up every product and computes win rate over decided tickets", () => {
    const s = summarisePeriod({
      period: "2026-09-23",
      products: [
        { product: "core", daily_pick: false, won: 1, lost: 1, void: 0, pending: 2, total: 4, win_rate: 0.5 },
        { product: "daily_safe", daily_pick: true, won: 2, lost: 0, void: 1, pending: 0, total: 3, win_rate: 1 },
      ],
    })
    // No profit_units from the API (older backend) → no P&L shown, never a fake 0.
    expect(s).toEqual({ period: "2026-09-23", won: 3, lost: 1, void: 1, pending: 2, total: 7, winRate: 0.75, profit: null })
  })

  it("sums every product's flat 1-unit P&L", () => {
    const s = summarisePeriod({
      period: "2026-09",
      products: [
        { product: "core", daily_pick: false, won: 1, lost: 1, void: 0, pending: 0, total: 2, win_rate: 0.5, profit_units: 1.5 },
        { product: "alpha", daily_pick: false, won: 0, lost: 2, void: 0, pending: 1, total: 3, win_rate: 0, profit_units: -2 },
      ],
    })
    expect(s.profit).toBeCloseTo(-0.5)
  })

  it("has no win rate until something is decided", () => {
    const s = summarisePeriod({ period: "2026", products: [{ product: "core", daily_pick: false, won: 0, lost: 0, void: 0, pending: 3, total: 3, win_rate: null }] })
    expect(s.winRate).toBeNull()
  })
})

describe("simulateTicketStake", () => {
  const periods = [{
    period: "2026",
    products: [
      { product: "core", daily_pick: false, won: 2, lost: 1, void: 1, pending: 3, total: 7, win_rate: 2 / 3, profit_units: 1.5 },
      { product: "daily_safe", daily_pick: true, won: 0, lost: 1, void: 0, pending: 0, total: 1, win_rate: 0, profit_units: -1 },
    ],
  }]

  it("uses one hypothetical stake for every priced win/loss, excluding voids and pending tickets", () => {
    expect(simulateTicketStake(periods, 100)).toEqual({ settledTickets: 4, flatUnitProfit: 0.5, returnedUnits: 4.5, roi: 0.125 })
  })

  it("rejects non-positive stakes and incomplete historical P&L", () => {
    expect(simulateTicketStake(periods, 0)).toBeNull()
    expect(simulateTicketStake([{ ...periods[0], products: [{ ...periods[0].products[0], profit_units: undefined }] }], 100)).toBeNull()
  })
})

describe("labels", () => {
  it("formats periods and products", () => {
    expect(periodLabel("2026-09", "month")).toBe("September 2026")
    expect(periodLabel("2026", "year")).toBe("2026")
    expect(productLabel("daily_balanced")).toBe("Daily Balanced")
  })

  it("orders value products before Daily Picks", () => {
    const sorted = ["daily_bold", "unknown", "core", "daily_safe", "alpha"].sort((a, b) => productRank(a) - productRank(b))
    expect(sorted).toEqual(["core", "alpha", "daily_safe", "daily_bold", "unknown"])
  })

  it("formats signed units and percentages", () => {
    expect(fmtUnits(1.846)).toBe("+1.85 u")
    expect(fmtUnits(-1)).toBe("−1.00 u")
    expect(fmtUnits(null)).toBe("—")
    expect(fmtSignedPct(0.125)).toBe("+12.5%")
    expect(fmtSignedPct(-0.3)).toBe("−30.0%")
  })
})

describe("ticket archive navigation", () => {
  const months = ["2026-09", "2026-08", "2025-12"]

  it("opens the requested day's or month's own month", () => {
    expect(focusMonth({ date: "2026-08-14" }, months)).toBe("2026-08")
    expect(focusMonth({ month: "2025-12" }, months)).toBe("2025-12")
  })

  it("opens a requested year's latest month, else the latest month overall", () => {
    expect(focusMonth({ year: "2025" }, months)).toBe("2025-12")
    expect(focusMonth({ year: "2024" }, months)).toBeUndefined()
    expect(focusMonth({}, months)).toBe("2026-09")
    expect(focusMonth({}, [])).toBeUndefined()
  })

  it("links to a period's group so the page opens and scrolls to it", () => {
    expect(ticketArchiveHref("day", "2026-09-24")).toBe("/accumulators?date=2026-09-24#day-2026-09-24")
    expect(ticketArchiveHref("month", "2026-09")).toBe("/accumulators?month=2026-09#month-2026-09")
    expect(ticketArchiveHref("year", "2026")).toBe("/accumulators?year=2026#year-2026")
  })

  it("names days in full and buckets timestamps by Blantyre day", () => {
    expect(longDayLabel("2026-09-24")).toBe("Thursday, 24 September 2026")
    expect(longDayLabel("2026-01-01")).toBe("Thursday, 1 January 2026")
    expect(longDayLabel("2028-02-29")).toBe("Tuesday, 29 February 2028")
    // 22:30 UTC is already the next day in Africa/Blantyre (UTC+2).
    expect(productDay("2026-09-23T22:30:00Z")).toBe("2026-09-24")
    expect(productDay("2026-09-23T21:59:00Z")).toBe("2026-09-23")
  })
})

describe("forecast labels", () => {
  const base = { line: null, home_team: "Arsenal", away_team: "Chelsea" }

  it("names the team for match-result and double-chance picks", () => {
    expect(selectionLabel({ ...base, market: "1X2", selection: "home" })).toBe("Arsenal to win")
    expect(selectionLabel({ ...base, market: "DOUBLE_CHANCE", selection: "X2" })).toBe("Draw or Chelsea")
  })

  it("includes the goal line for totals", () => {
    expect(selectionLabel({ ...base, market: "TOTALS", selection: "over", line: 2.5 })).toBe("Over 2.5")
  })

  it("falls back to the raw values for unknown markets", () => {
    expect(selectionLabel({ ...base, market: "CORNERS", selection: "over 9" })).toBe("over 9")
    expect(marketLabel("CORNERS")).toBe("CORNERS")
    expect(marketLabel("1X2")).toBe("Match result")
  })
})
