import { describe, it, expect, vi, beforeEach } from "vitest"

const mockFetch = vi.fn()
vi.stubGlobal("fetch", mockFetch)

const { fetchAccumulatorResults } = await import("@/lib/api")

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

describe("fetchAccumulatorResults", () => {
  it("calls /performance/accumulator-results with granularity and limit", async () => {
    const body = { granularity: "month", periods: [], total_periods: 0 }
    mockFetch.mockReturnValueOnce(makeResponse(body))
    const result = await fetchAccumulatorResults({ granularity: "month", limit: 24 })
    expect(result).toEqual(body)
    const url = new URL(mockFetch.mock.calls[0][0])
    expect(url.pathname).toBe("/performance/accumulator-results")
    expect(url.searchParams.get("granularity")).toBe("month")
    expect(url.searchParams.get("limit")).toBe("24")
    expect(url.searchParams.has("product")).toBe(false)
  })

  it("throws on a non-OK response so the page can show its error state", async () => {
    mockFetch.mockReturnValueOnce(makeResponse({}, false, 500))
    await expect(fetchAccumulatorResults({ granularity: "day" })).rejects.toThrow(
      "API /performance/accumulator-results failed: 500",
    )
  })
})
