"use client"

import { useMemo, useState, type CSSProperties, type ReactNode } from "react"
import { SortHeaderCell } from "@/components/SortableHeader"
import { nextSortState, sortRows, type SortState, type SortValue } from "@/lib/sort"

export interface SortableColumn {
  key: string
  label: string
  align?: "left" | "right"
  /** Header padding/weight/visibility classes (e.g. "hidden sm:table-cell px-3 py-2"). */
  className?: string
  style?: CSSProperties
}

export interface SortableRow {
  key: string
  /** One sort value per column, in column order. */
  values: SortValue[]
  /** The row's cells (<th>/<td> elements), rendered on the server. */
  cells: ReactNode
  className?: string
}

/**
 * A table whose rows are already loaded, sorted in the browser when a header
 * is clicked — no refetch. Paginated, API-backed tables use SortableHeader.
 */
export default function SortableTable({
  columns,
  rows,
  caption,
  className = "w-full text-sm",
  theadClassName,
  tbodyClassName,
}: {
  columns: SortableColumn[]
  rows: SortableRow[]
  caption: string
  className?: string
  theadClassName?: string
  tbodyClassName?: string
}) {
  const [sort, setSort] = useState<SortState | null>(null)

  const ordered = useMemo(() => {
    if (!sort) return rows
    const index = columns.findIndex((c) => c.key === sort.key)
    return index === -1 ? rows : sortRows(rows, (r) => r.values[index], sort.dir)
  }, [rows, columns, sort])

  return (
    <table className={className}>
      <caption className="sr-only">{caption}. Column headers sort the table.</caption>
      <thead className={theadClassName}>
        <tr>
          {columns.map((c) => (
            <SortHeaderCell
              key={c.key}
              label={c.label}
              align={c.align}
              dir={sort?.key === c.key ? sort.dir : null}
              onSort={() => setSort((s) => nextSortState(s, c.key))}
              className={c.className}
              style={c.style}
            />
          ))}
        </tr>
      </thead>
      <tbody className={tbodyClassName}>
        {ordered.map((r) => (
          <tr key={r.key} className={r.className}>{r.cells}</tr>
        ))}
      </tbody>
    </table>
  )
}
