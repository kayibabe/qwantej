import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import TicketStakeSimulator from "@/components/tickets/TicketStakeSimulator"

const periods = [{
  period: "2026",
  products: [{ product: "core", daily_pick: false, won: 2, lost: 1, void: 1, pending: 2, total: 6, win_rate: 2 / 3, profit_units: 1.5 }],
}]

describe("TicketStakeSimulator", () => {
  it("shows an archived flat-stake P&L replay without including void or pending tickets", () => {
    render(<TicketStakeSimulator periods={periods} />)
    fireEvent.change(screen.getByLabelText("Simulated stake per ticket"), { target: { value: "100" } })

    expect(screen.getByText("Settled tickets")).toBeInTheDocument()
    expect(screen.getByText("3")).toBeInTheDocument()
    expect(screen.getByText("MWK 300")).toBeInTheDocument()
    expect(screen.getByText("+MWK 150")).toBeInTheDocument()
    expect(screen.getByText("+50.0%")).toBeInTheDocument()
    expect(screen.getByText(/not a recommended stake and is not saved/i)).toBeInTheDocument()
  })
})
