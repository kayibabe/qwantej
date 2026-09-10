import { describe, it, expect, vi, beforeEach } from "vitest"

// Mock fetch globally
const mockFetch = vi.fn()
vi.stubGlobal("fetch", mockFetch)

// Import after stubbing so the module uses the mock
const {
  fetchPredictions,
  fetchSettlements,
  fetchSettlementSummary,
  fetchAccumulators,
  fetchPerformanceReport,
  fetchModels,
} = await import("@/lib/api")

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

describe("fetchPerformanceReport", () => {
  it("calls /performance/report with no params", async () => {
    const report = { n_total: 100, n_settled: 80 }
    mockFetch.mockReturnValueOnce(makeResponse(report))
    const result = await fetchPerformanceReport()
    expect(result).toEqual(report)
    const url: string = mockFetch.mock.calls[0][0]
    expect(url).toContain("/performance/report")
  })

  it("does not send model_version param (not supported by backend)", async () => {
    mockFetch.mockReturnValueOnce(makeResponse({}))
    // Call with only supported params — ensure model_version cannot be passed
    await fetchPerformanceReport({ subject_type: "prediction", market: "1X2" })
    const url: string = mockFetch.mock.calls[0][0]
    expect(url).not.toContain("model_version")
    expect(url).toContain("subject_type=prediction")
    expect(url).toContain("market=1X2")
  })

  it("throws on non-ok response", async () => {
    mockFetch.mockReturnValueOnce(makeResponse(null, false, 503))
    await expect(fetchPerformanceReport()).rejects.toThrow("/performance/report failed")
  })
})

describe("fetchModels", () => {
  it("calls /models with no params", async () => {
    const page = { items: [], total: 0, limit: 20, offset: 0 }
    mockFetch.mockReturnValueOnce(makeResponse(page))
    const result = await fetchModels()
    expect(result).toEqual(page)
    const url: string = mockFetch.mock.calls[0][0]
    expect(url).toContain("/models")
  })

  it("passes status=development (not shadow)", async () => {
    mockFetch.mockReturnValueOnce(makeResponse({ items: [], total: 0, limit: 20, offset: 0 }))
    await fetchModels({ status: "development" })
    const url: string = mockFetch.mock.calls[0][0]
    expect(url).toContain("status=development")
    expect(url).not.toContain("shadow")
  })

  it("passes family filter for all seven families", async () => {
    const families = ["poisson", "dixon_coles", "zinb", "elo", "bayesian_hierarchical", "market", "ensemble"]
    for (const family of families) {
      mockFetch.mockReturnValueOnce(makeResponse({ items: [], total: 0, limit: 20, offset: 0 }))
      await fetchModels({ family })
      const url: string = mockFetch.mock.calls[mockFetch.mock.calls.length - 1][0]
      expect(url).toContain(`family=${family}`)
    }
  })
})
