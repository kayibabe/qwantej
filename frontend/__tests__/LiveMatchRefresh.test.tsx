import { act, render } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import LiveMatchRefresh from "@/components/LiveMatchRefresh"

const { mockRefresh } = vi.hoisted(() => ({ mockRefresh: vi.fn() }))

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: mockRefresh }),
}))

describe("LiveMatchRefresh", () => {
  beforeEach(() => mockRefresh.mockClear())
  afterEach(() => vi.useRealTimers())

  it("refreshes server-rendered match data once per minute", () => {
    vi.useFakeTimers()
    render(<LiveMatchRefresh />)

    act(() => vi.advanceTimersByTime(60_000))
    expect(mockRefresh).toHaveBeenCalledTimes(1)
    act(() => vi.advanceTimersByTime(60_000))
    expect(mockRefresh).toHaveBeenCalledTimes(2)
  })
})
