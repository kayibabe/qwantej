import { render, screen } from "@testing-library/react"
import AccumulatorCard from "@/components/AccumulatorCard"
import type { AccumulatorOut } from "@/lib/types"

const BASE: AccumulatorOut = {
  id: "aaaaaaaa-0000-0000-0000-000000000001",
  product: "Core",
  status: "pending",
  combined_odds: 4.12,
  conservative_joint_probability: 0.318,
  stressed_joint_probability: 0.280,
  objective_score: 0.74,
  published_at: "2026-09-07T08:00:00Z",
  locked_at: null,
  stake: 10.0,
  risk_policy_version: "1.0",
  legs: [
    {
      id: "bbbbbbbb-0000-0000-0000-000000000001",
      leg_index: 0,
      prediction_id: "cccccccc-0000-0000-0000-000000000001",
      fixture_id: "dddddddd-0000-0000-0000-000000000001",
      league_id: "EPL",
      market_family: "Over 2.5",
      selection: "Over 2.5",
      decimal_odds: 1.80,
      conservative_probability: 0.62,
      edge: 0.083,
      qss: 88,
    },
    {
      id: "bbbbbbbb-0000-0000-0000-000000000002",
      leg_index: 1,
      prediction_id: "cccccccc-0000-0000-0000-000000000002",
      fixture_id: "dddddddd-0000-0000-0000-000000000002",
      league_id: "Bundesliga",
      market_family: "BTTS",
      selection: "BTTS Yes",
      decimal_odds: 1.70,
      conservative_probability: 0.68,
      edge: 0.092,
      qss: 91,
    },
  ],
  created_at: "2026-09-07T07:55:00Z",
}

describe("AccumulatorCard", () => {
  it("renders the product label", () => {
    render(<AccumulatorCard acc={BASE} />)
    expect(screen.getByText(/CORE ACCA/i)).toBeInTheDocument()
  })

  it("renders combined odds", () => {
    render(<AccumulatorCard acc={BASE} />)
    expect(screen.getByText("4.12")).toBeInTheDocument()
  })

  it("renders all legs", () => {
    render(<AccumulatorCard acc={BASE} />)
    // "Over 2.5" appears as both selection and market_family in the test data
    expect(screen.getAllByText("Over 2.5").length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText("BTTS Yes")).toBeInTheDocument()
  })

  it("renders status badge", () => {
    render(<AccumulatorCard acc={BASE} />)
    expect(screen.getByText("PENDING")).toBeInTheDocument()
  })

  it("renders leg count", () => {
    render(<AccumulatorCard acc={BASE} />)
    expect(screen.getByText("2 legs")).toBeInTheDocument()
  })

  it("renders stake", () => {
    render(<AccumulatorCard acc={BASE} />)
    expect(screen.getByText(/£10\.00/)).toBeInTheDocument()
  })

  it("renders GROWTH product with correct label", () => {
    const growth = { ...BASE, product: "Growth", combined_odds: 7.5 }
    render(<AccumulatorCard acc={growth} />)
    expect(screen.getByText(/GROWTH ACCA/i)).toBeInTheDocument()
  })
})
