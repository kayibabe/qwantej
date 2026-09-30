import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import TicketStakeSimulator from "@/components/tickets/TicketStakeSimulator"
import type { AccumulatorOut } from "@/lib/types"

const period = {
  period: "2026",
  products: [{ product: "core", daily_pick: false, won: 2, lost: 1, void: 1, pending: 2, total: 6, win_rate: 2 / 3, profit_units: 1.5 }],
}
const tickets = [
  { id: "won", product: "core", combined_odds: 3.5, result: "won", profit_units: 2.5 },
  { id: "won-2", product: "core", combined_odds: 2, result: "won", profit_units: 0 },
  { id: "lost", product: "core", combined_odds: 2, result: "lost", profit_units: -1 },
  { id: "void", product: "core", combined_odds: 2, result: "void", profit_units: 0 },
] as AccumulatorOut[]

describe("TicketStakeSimulator", () => {
  it("shows an archived flat-stake P&L replay without including void or pending tickets", () => {
    render(<TicketStakeSimulator periods={{ year: [period], month: [period], day: [period] }} initialScope={{ granularity: "year", period: "2026" }} initialTickets={tickets} />)
    fireEvent.change(screen.getByLabelText("Simulated stake per ticket"), { target: { value: "100" } })

    expect(screen.getByText("Settled tickets")).toBeInTheDocument()
    expect(screen.getByText("2 won")).toBeInTheDocument()
    expect(screen.getByText("1 lost")).toBeInTheDocument()
    expect(screen.getByText("1 void")).toBeInTheDocument()
    expect(screen.getByText("3")).toBeInTheDocument()
    expect(screen.getByText("MWK 300")).toBeInTheDocument()
    expect(screen.getByText("Total returned")).toBeInTheDocument()
    expect(screen.getByText("MWK 450")).toBeInTheDocument()
    expect(screen.getByText("+MWK 150")).toBeInTheDocument()
    expect(screen.getByText("+50.0%")).toBeInTheDocument()
    expect(screen.getByText(/not a recommended stake and is not saved/i)).toBeInTheDocument()

  })

  it("offers Daily Bold ACCA and filters the replay to bold tickets", () => {
    const boldTickets = [
      ...tickets,
      { id: "bold-won", product: "daily_bold", combined_odds: 4, result: "won", profit_units: 3 },
    ] as AccumulatorOut[]
    render(<TicketStakeSimulator periods={{ year: [period], month: [period], day: [period] }} initialScope={{ granularity: "year", period: "2026" }} initialTickets={boldTickets} />)

    const selector = screen.getByLabelText("Tickets")
    expect(screen.getByRole("option", { name: "Daily Bold ACCA" })).toBeInTheDocument()
    fireEvent.change(selector, { target: { value: "daily_bold" } })
    fireEvent.change(screen.getByLabelText("Simulated stake per ticket"), { target: { value: "100" } })

    expect(screen.getByText("Settled tickets")).toBeInTheDocument()
    expect(screen.getByText("1 won")).toBeInTheDocument()
    expect(screen.getByText("0 lost")).toBeInTheDocument()
    expect(screen.getByText("0 void")).toBeInTheDocument()
    expect(screen.getByText("MWK 100")).toBeInTheDocument()
    expect(screen.getByText("MWK 400")).toBeInTheDocument()
    expect(screen.getByText("+MWK 300")).toBeInTheDocument()
  })
})
