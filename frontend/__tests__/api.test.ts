import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

// Mock fetch globally
const mockFetch = vi.fn()
vi.stubGlobal("fetch", mockFetch)

// Import after stubbing so the module uses the mock
const { fetchPredictions, fetchSettlements, fetchSettlementSummary, fetchAccumulators } =
  await import("@/lib/api")

function makeResponse(data: unknown, ok = true, status = 200) {
  return Promise.resolve({
    ok,
    status,
    statusText: ok ? "OK" : "Internal Server Error",
    json: () => Promise.resolve(data),
  })
}

beforeEach(() => {
  mockFetch.mockReset()
})

describe("fetchPredictions", () => {
  it("calls /predictions with no params", async () => {
    const page = { items: [], total: 0, limit: 50, offset: 0 }
    mockFetch.mockReturnValueOnce(makeResponse(page))
    const result = await fetchPredictions({})
    expect(result).toEqual(page)
    const url: string = mockFetch.mock.calls[0][0]
    expect(url).toContain("/predictions")
  })

  it("passes market filter in query string", async () => {
    mockFetch.mockReturnValueOnce(makeResponse({ items: [], total: 0, limit: 50, offset: 0 }))
    await fetchPredictions({ market: "1X2", limit: 10 })
    const url: string = mockFetch.mock.calls[0][0]
    expect(url).toContain("market=1X2")
    expect(url).toContain("limit=10")
  })

  it("throws on non-ok response", async () => {
    mockFetch.mockReturnValueOnce(makeResponse(null, false, 500))
    await expect(fetchPredictions({})).rejects.toThrow("/predictions failed")
  })
})

describe("fetchSettlementSummary", () => {
  it("calls /settlements/summary", async () => {
    const summary = { n_settled: 10, n_wins: 6, n_losses: 4, n_voids: 0, win_rate: 0.6, avg_clv: 0.02, avg_brier: 0.18 }
    mockFetch.mockReturnValueOnce(makeResponse(summary))
    const result = await fetchSettlementSummary()
    expect(result.win_rate).toBe(0.6)
    const url: string = mockFetch.mock.calls[0][0]
    expect(url).toContain("/settlements/summary")
  })
})

describe("fetchSettlements", () => {
  it("passes outcome filter", async () => {
    mockFetch.mockReturnValueOnce(makeResponse({ items: [], total: 0, limit: 50, offset: 0 }))
    await fetchSettlements({ outcome: "win" })
    const url: string = mockFetch.mock.calls[0][0]
    expect(url).toContain("outcome=win")
  })
})

describe("fetchAccumulators", () => {
  it("passes status filter", async () => {
    mockFetch.mockReturnValueOnce(makeResponse({ items: [], total: 0, limit: 10, offset: 0 }))
    await fetchAccumulators({ status: "pending", limit: 10 })
    const url: string = mockFetch.mock.calls[0][0]
    expect(url).toContain("status=pending")
    expect(url).toContain("limit=10")
  })
})
