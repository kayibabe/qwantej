import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import TicketRow from "@/components/tickets/TicketRow"
import type { AccumulatorLegOut, AccumulatorOut } from "@/lib/types"

const LEG: AccumulatorLegOut = {
  id: "leg-1",
  leg_index: 0,
  prediction_id: "p-1",
  fixture_id: "f-1",
  league_id: "39",
  market_family: "TOTALS",
  selection: "Over 2.5",
  decimal_odds: 1.8,
  conservative_probability: 0.62,
  edge: 0.05,
  qss: 88,
  bookmaker: "Bet365",
  home_team: "Norway",
  away_team: "Denmark",
  kickoff_utc: "2026-09-24T18:45:00Z",
  competition_name: "UEFA Nations League",
  match_state: "won",
  fixture_status: "finished",
  score: "3–1",
  live_phase: null,
  elapsed_minutes: null,
  settlement_outcome: "win",
  quote_captured_at: null,
}

function ticket(overrides: Partial<AccumulatorOut>): AccumulatorOut {
  return {
    id: "aaaaaaaa-0000-0000-0000-000000000001",
    product: "core",
    status: "settled",
    combined_odds: 3.24,
    conservative_joint_probability: 0.35,
    stressed_joint_probability: 0.3,
    objective_score: 0.8,
    published_at: "2026-09-24T08:00:00Z",
    locked_at: null,
    stake: null,
    risk_policy_version: null,
    created_at: "2026-09-24T08:00:00Z",
    legs: [LEG, { ...LEG, id: "leg-2", leg_index: 1, home_team: "Home FC", away_team: "Away FC", market_family: "1X2", selection: "home", score: "2–0" }],
    result: "won",
    settlement_odds: 3.24,
    profit_units: 2.24,
    ...overrides,
  }
}

describe("TicketRow", () => {
  it("shows the product, price, readable legs with scores and a won result box", () => {
    render(<ul><TicketRow acc={ticket({})} /></ul>)
    expect(screen.getByRole("link")).toHaveAttribute("href", "/accumulators/aaaaaaaa-0000-0000-0000-000000000001")
    expect(screen.getByText("Core ACCA")).toBeInTheDocument()
    expect(screen.getByText("(3.24)")).toBeInTheDocument()
    expect(screen.getByText("Norway vs Denmark")).toBeInTheDocument()
    expect(screen.getByText("Home FC to win")).toBeInTheDocument() // 1X2 "home" made readable
    expect(screen.getByLabelText("Score 3–1")).toBeInTheDocument()
    expect(screen.getByText("Won", { selector: "span.text-sm" })).toBeInTheDocument()
    expect(screen.getByText("+2.24 u")).toBeInTheDocument()
  })

  it("shows a lost ticket's −1 unit and a pending ticket without P&L", () => {
    const { unmount } = render(<ul><TicketRow acc={ticket({ result: "lost", profit_units: -1 })} /></ul>)
    expect(screen.getByText("−1.00 u")).toBeInTheDocument()
    unmount()
    render(<ul><TicketRow acc={ticket({ result: "pending", profit_units: null })} /></ul>)
    expect(screen.getByText("Pending")).toBeInTheDocument()
    expect(screen.getByText("–")).toBeInTheDocument()
  })

  it("reads an administratively voided ticket as void whatever its legs say", () => {
    render(<ul><TicketRow acc={ticket({ status: "void", result: "won", profit_units: 0 })} /></ul>)
    expect(screen.getByText("Void")).toBeInTheDocument()
  })
})
