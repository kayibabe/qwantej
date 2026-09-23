import { fireEvent, render, screen } from "@testing-library/react"
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
      bookmaker: "Bet365",
      home_team: "Home FC",
      away_team: "Away FC",
      kickoff_utc: "2026-09-07T20:00:00Z",
      competition_name: "Premier League",
      match_state: "pending",
      fixture_status: "scheduled",
      score: null,
      live_phase: null,
      elapsed_minutes: null,
      settlement_outcome: null,
      quote_captured_at: "2026-09-07T17:30:00Z",
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
      bookmaker: "Betway",
      home_team: "Away FC",
      away_team: "Home FC",
      kickoff_utc: "2026-09-07T20:00:00Z",
      competition_name: "Bundesliga",
      match_state: "pending",
      fixture_status: "scheduled",
      score: null,
      live_phase: null,
      elapsed_minutes: null,
      settlement_outcome: null,
      quote_captured_at: "2026-09-07T17:30:00Z",
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
    expect(screen.getByText("4.12×")).toBeInTheDocument()
  })

  it("renders all legs", () => {
    render(<AccumulatorCard acc={BASE} />)
    // "Over 2.5" appears as both selection and market_family in the test data
    expect(screen.getAllByText("Over 2.5").length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText("BTTS Yes")).toBeInTheDocument()
  })

  it("renders status badge", () => {
    render(<AccumulatorCard acc={BASE} />)
    expect(screen.getAllByText("PENDING")).toHaveLength(3)
  })

  it("renders leg count", () => {
    render(<AccumulatorCard acc={BASE} />)
    expect(screen.getByText(/2 legs/)).toBeInTheDocument()
  })

  it("renders stake", () => {
    render(<AccumulatorCard acc={BASE} />)
    expect(screen.getByText(/£10\.00/)).toBeInTheDocument()
  })

  it("renders fixture identity and executable price source", () => {
    render(<AccumulatorCard acc={BASE} />)
    expect(screen.getByText("Home FC vs Away FC")).toBeInTheDocument()
    expect(screen.getByText(/Bet365/)).toBeInTheDocument()
    expect(screen.getAllByText(/Price as of/)).toHaveLength(2)
  })

  it("shows live phase, elapsed minutes, and score for a live match", () => {
    const live = {
      ...BASE,
      legs: [{
        ...BASE.legs[0], match_state: "live", fixture_status: "live",
        score: "1–0", live_phase: "2nd half", elapsed_minutes: 67,
      }, BASE.legs[1]],
    }
    render(<AccumulatorCard acc={live} />)
    expect(screen.getByText("LIVE · 2nd half · 67′")).toBeInTheDocument()
    expect(screen.getByLabelText("Score 1–0")).toBeInTheDocument()
  })

  it("flags a stale provider result instead of showing PENDING", () => {
    const stale = {
      ...BASE,
      legs: [{
        ...BASE.legs[0], match_state: "awaiting_result", fixture_status: "scheduled",
        score: null,
      }, BASE.legs[1]],
    }
    render(<AccumulatorCard acc={stale} />)
    expect(screen.getByText("RESULT DATA STALE")).toBeInTheDocument()
    expect(screen.getByTitle(/provider still reports Not Started/)).toBeInTheDocument()
  })

  it("shows a settled leg outcome separately from ticket status", () => {
    const settledLeg = {
      ...BASE,
      legs: [{
        ...BASE.legs[0], match_state: "won", fixture_status: "finished",
        score: "2–1", settlement_outcome: "win",
      }, BASE.legs[1]],
    }
    render(<AccumulatorCard acc={settledLeg} />)
    expect(screen.getByText("WON")).toBeInTheDocument()
    expect(screen.getByLabelText("Score 2–1")).toBeInTheDocument()
    expect(screen.getAllByText("PENDING")).toHaveLength(2)
  })

  it("renders GROWTH product with correct label", () => {
    const growth = { ...BASE, product: "Growth", combined_odds: 7.5 }
    render(<AccumulatorCard acc={growth} />)
    expect(screen.getByText(/GROWTH ACCA/i)).toBeInTheDocument()
  })

  it("labels a Daily Pick as not value-qualified and shows no stake", () => {
    const daily = { ...BASE, product: "daily_safe", stake: null, combined_odds: 2.05 }
    render(<AccumulatorCard acc={daily} />)
    expect(screen.getByText("DAILY SAFE ACCA")).toBeInTheDocument()
    expect(screen.getByText(/not value-qualified/i)).toBeInTheDocument()
    expect(screen.getAllByText(/est\. prob/)).toHaveLength(2)
    expect(screen.queryByText(/£/)).not.toBeInTheDocument()
  })

  it("flags a last-resort Daily Pick as a fallback build", () => {
    const fallback = {
      ...BASE, product: "daily_safe", stake: null, policy_version: "daily-last-resort-v1",
    }
    render(<AccumulatorCard acc={fallback} />)
    expect(screen.getByText(/fallback build/i)).toBeInTheDocument()
  })

  it("does not flag a preferred-rung Daily Pick as fallback", () => {
    const preferred = { ...BASE, product: "daily_safe", stake: null, policy_version: "daily-safe-v1" }
    render(<AccumulatorCard acc={preferred} />)
    expect(screen.queryByText(/fallback build/i)).not.toBeInTheDocument()
  })

  it("does not badge value products as Daily Picks", () => {
    render(<AccumulatorCard acc={BASE} />)
    expect(screen.queryByText(/not value-qualified/i)).not.toBeInTheDocument()
    expect(screen.getAllByText(/model prob/)).toHaveLength(2)
  })

  it("opens archived selection evidence and closes with Escape", () => {
    render(<AccumulatorCard acc={BASE} />)
    fireEvent.click(screen.getByRole("button", { name: /View evidence for Home FC vs Away FC/ }))
    expect(screen.getByRole("dialog", { name: "Home FC vs Away FC" })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("tab", { name: "Probability" }))
    expect(screen.getByText("Stored conservative model probability:")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("tab", { name: "Odds" }))
    expect(screen.getByText(/Archived snapshot:/)).toBeInTheDocument()
    fireEvent.keyDown(document, { key: "Escape" })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("does not invent missing match statistics", () => {
    render(<AccumulatorCard acc={BASE} />)
    fireEvent.click(screen.getByRole("button", { name: /View evidence for Home FC vs Away FC/ }))
    fireEvent.click(screen.getByRole("tab", { name: "Stats" }))
    expect(screen.getByText("Match statistics are not included in the published ticket archive.")).toBeInTheDocument()
  })
})
