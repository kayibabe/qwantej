import { render, screen } from "@testing-library/react"
import StatTile from "@/components/StatTile"

describe("StatTile", () => {
  it("renders label and value", () => {
    render(<StatTile label="Win rate" value="52.3%" />)
    expect(screen.getByText("Win rate")).toBeInTheDocument()
    expect(screen.getByText("52.3%")).toBeInTheDocument()
  })

  it("renders — when value is null", () => {
    render(<StatTile label="Avg CLV" value={null} />)
    expect(screen.getByText("—")).toBeInTheDocument()
  })

  it("renders sub text when provided", () => {
    render(<StatTile label="Settled" value={42} sub="total effective" />)
    expect(screen.getByText("total effective")).toBeInTheDocument()
  })

  it("applies custom valueClass", () => {
    render(<StatTile label="Win rate" value="60%" valueClass="text-green-500" />)
    const valueEl = screen.getByText("60%")
    expect(valueEl.className).toContain("text-green-500")
  })
})
