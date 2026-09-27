import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import DayGroup from "@/components/tickets/DayGroup"
import { loadDayTickets } from "@/app/accumulators/actions"
import type { AccumulatorOut } from "@/lib/types"

vi.mock("@/app/accumulators/actions", () => ({ loadDayTickets: vi.fn() }))
vi.mock("@/components/tickets/TicketRow", () => ({
  default: ({ acc }: { acc: AccumulatorOut }) => <li>{acc.result}</li>,
}))
const summary = { period: "2026-08-31", won: 0, lost: 0, void: 0, pending: 1, total: 1, winRate: null, profit: 0 }
const pending = [{ id: "ticket", result: "pending" }] as AccumulatorOut[]
const won = [{ id: "ticket", result: "won" }] as AccumulatorOut[]
const props = { summary, initialTickets: null, defaultOpen: true }

beforeEach(() => vi.resetAllMocks())

describe("DayGroup refresh", () => {
  it("reloads an expanded lazy day on a new page revision even with unchanged totals", async () => {
    vi.mocked(loadDayTickets).mockResolvedValueOnce(pending).mockResolvedValueOnce(won)
    const { rerender } = render(<DayGroup {...props} refreshToken="one" />)
    expect(await screen.findByText("pending", { selector: "li" })).toBeInTheDocument()
    rerender(<DayGroup {...props} refreshToken="two" />)
    expect(await screen.findByText("won", { selector: "li" })).toBeInTheDocument()
    expect(loadDayTickets).toHaveBeenCalledTimes(2)
    expect(screen.getByText("won", { selector: "li" }).closest("details")).toHaveAttribute("open")
  })

  it("discards a response from a previous page revision", async () => {
    let resolveOld!: (value: AccumulatorOut[]) => void
    vi.mocked(loadDayTickets)
      .mockReturnValueOnce(new Promise((resolve) => { resolveOld = resolve }))
      .mockResolvedValueOnce(won)
    const { rerender } = render(<DayGroup {...props} refreshToken="one" />)
    await waitFor(() => expect(loadDayTickets).toHaveBeenCalledTimes(1))
    rerender(<DayGroup {...props} refreshToken="two" />)
    await screen.findByText("won", { selector: "li" })
    await act(async () => resolveOld(pending))
    expect(screen.queryByText("pending", { selector: "li" })).not.toBeInTheDocument()
  })

  it("shows refresh failures instead of old results and permits retry", async () => {
    vi.mocked(loadDayTickets).mockResolvedValueOnce(pending).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(won)
    const { rerender } = render(<DayGroup {...props} refreshToken="one" />)
    await screen.findByText("pending", { selector: "li" })
    rerender(<DayGroup {...props} refreshToken="two" />)
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }))
    expect(await screen.findByText("won", { selector: "li" })).toBeInTheDocument()
  })

  it("does not fetch closed days or server-provided tickets", async () => {
    const { rerender } = render(<DayGroup {...props} defaultOpen={false} refreshToken="one" />)
    expect(loadDayTickets).not.toHaveBeenCalled()
    rerender(<DayGroup {...props} initialTickets={won} refreshToken="two" />)
    expect(screen.getByText("won", { selector: "li" })).toBeInTheDocument()
    expect(loadDayTickets).not.toHaveBeenCalled()
  })

  it("loads the latest revision when a previously closed day is expanded", async () => {
    vi.mocked(loadDayTickets).mockResolvedValue(won)
    const { container, rerender } = render(<DayGroup {...props} defaultOpen={false} refreshToken="one" />)
    rerender(<DayGroup {...props} defaultOpen={false} refreshToken="two" />)
    const details = container.querySelector("details")!
    details.open = true
    fireEvent(details, new Event("toggle"))
    expect(await screen.findByText("won", { selector: "li" })).toBeInTheDocument()
    expect(loadDayTickets).toHaveBeenCalledTimes(1)
  })
})
