import { describe, expect, it } from "vitest"
import { compareSortValues, nextSortState, sortRows } from "@/lib/sort"

describe("compareSortValues", () => {
  it("orders numbers numerically and text naturally, case-insensitively", () => {
    expect(sortRows([10, 9, 100], (v) => v, "asc")).toEqual([9, 10, 100])
    expect(sortRows(["b", "A", "c"], (v) => v, "asc")).toEqual(["A", "b", "c"])
    // Natural order: "Model 2" before "Model 10".
    expect(sortRows(["Model 10", "Model 2"], (v) => v, "asc")).toEqual(["Model 2", "Model 10"])
    expect(sortRows([1, 3, 2], (v) => v, "desc")).toEqual([3, 2, 1])
  })

  it("puts missing values last in both directions", () => {
    const rows = [null, 2, undefined, Number.NaN, 5]
    expect(sortRows(rows, (v) => v, "asc").slice(0, 2)).toEqual([2, 5])
    expect(sortRows(rows, (v) => v, "desc").slice(0, 2)).toEqual([5, 2])
    expect(compareSortValues(null, undefined, "asc")).toBe(0)
  })

  it("keeps the original order of ties (stable)", () => {
    const rows = [{ id: "a", v: 1 }, { id: "b", v: 0 }, { id: "c", v: 1 }]
    expect(sortRows(rows, (r) => r.v, "desc").map((r) => r.id)).toEqual(["a", "c", "b"])
  })

  it("does not mutate its input", () => {
    const rows = [3, 1, 2]
    sortRows(rows, (v) => v, "asc")
    expect(rows).toEqual([3, 1, 2])
  })
})

describe("nextSortState", () => {
  it("cycles ascending → descending → original order", () => {
    const first = nextSortState(null, "odds")
    expect(first).toEqual({ key: "odds", dir: "asc" })
    const second = nextSortState(first, "odds")
    expect(second).toEqual({ key: "odds", dir: "desc" })
    expect(nextSortState(second, "odds")).toBeNull()
  })

  it("starts ascending when switching to another column", () => {
    expect(nextSortState({ key: "odds", dir: "desc" }, "roi")).toEqual({ key: "roi", dir: "asc" })
  })
})
