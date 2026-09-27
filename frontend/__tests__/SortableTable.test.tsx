import { fireEvent, render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import SortableTable from "@/components/SortableTable"

const COLUMNS = [
  { key: "name", label: "Ticket type" },
  { key: "roi", label: "ROI", align: "right" as const },
]

const ROWS = [
  { key: "core", name: "Core", roi: 0.1 },
  { key: "alpha", name: "Alpha", roi: null },
  { key: "growth", name: "Growth", roi: -0.2 },
].map((r) => ({
  key: r.key,
  values: [r.name, r.roi],
  cells: <><th scope="row">{r.name}</th><td>{r.roi === null ? "—" : r.roi}</td></>,
}))

function rowNames() {
  return within(screen.getAllByRole("rowgroup")[1]).getAllByRole("rowheader").map((c) => c.textContent)
}

describe("SortableTable", () => {
  it("keeps the given order until a header is clicked", () => {
    render(<SortableTable caption="Results by type" columns={COLUMNS} rows={ROWS} />)
    expect(rowNames()).toEqual(["Core", "Alpha", "Growth"])
    for (const header of screen.getAllByRole("columnheader")) expect(header).toHaveAttribute("aria-sort", "none")
  })

  it("sorts ascending, then descending, then restores the original order", () => {
    render(<SortableTable caption="Results by type" columns={COLUMNS} rows={ROWS} />)
    const roi = screen.getByRole("button", { name: "ROI" })

    fireEvent.click(roi)
    expect(rowNames()).toEqual(["Growth", "Core", "Alpha"]) // missing ROI last
    expect(screen.getByRole("columnheader", { name: "ROI" })).toHaveAttribute("aria-sort", "ascending")

    fireEvent.click(roi)
    expect(rowNames()).toEqual(["Core", "Growth", "Alpha"]) // still last when descending
    expect(screen.getByRole("columnheader", { name: "ROI" })).toHaveAttribute("aria-sort", "descending")

    fireEvent.click(roi)
    expect(rowNames()).toEqual(["Core", "Alpha", "Growth"])
    expect(screen.getByRole("columnheader", { name: "ROI" })).toHaveAttribute("aria-sort", "none")
  })

  it("sorts text columns and moves the sort between columns", () => {
    render(<SortableTable caption="Results by type" columns={COLUMNS} rows={ROWS} />)
    fireEvent.click(screen.getByRole("button", { name: "ROI" }))
    fireEvent.click(screen.getByRole("button", { name: "Ticket type" }))
    expect(rowNames()).toEqual(["Alpha", "Core", "Growth"])
    expect(screen.getByRole("columnheader", { name: "ROI" })).toHaveAttribute("aria-sort", "none")
  })

  it("sorts from the keyboard: headers are real buttons", () => {
    render(<SortableTable caption="Results by type" columns={COLUMNS} rows={ROWS} />)
    const button = screen.getByRole("button", { name: "Ticket type" })
    expect(button.tagName).toBe("BUTTON")
    button.focus()
    expect(button).toHaveFocus()
  })
})
