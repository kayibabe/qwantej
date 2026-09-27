"use client"

import type { CSSProperties } from "react"
import { useRouter, usePathname, useSearchParams } from "next/navigation"
import { nextSortState, type SortDir } from "@/lib/sort"

interface SortHeaderCellProps {
  label: string
  align?: "left" | "right"
  /** Direction this column is currently sorted in, or null. */
  dir: SortDir | null
  onSort: () => void
  /** Padding/weight/visibility classes; defaults suit most tables. */
  className?: string
  style?: CSSProperties
}

/** A column header that sorts its table when clicked (shared look and a11y). */
export function SortHeaderCell({ label, align = "left", dir, onSort, className = "px-4 py-2 font-medium", style }: SortHeaderCellProps) {
  return (
    <th
      scope="col"
      aria-sort={dir === "asc" ? "ascending" : dir === "desc" ? "descending" : "none"}
      className={`${align === "right" ? "text-right" : "text-left"} ${className}`}
      style={style}
    >
      <button
        type="button"
        onClick={onSort}
        title={`Sort by ${label}`}
        className={[
          "group inline-flex items-center gap-1 uppercase tracking-wider transition-colors hover:text-[var(--text-primary)] focus-visible:rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
          align === "right" ? "flex-row-reverse" : "",
          dir ? "text-[var(--accent)]" : "",
        ].join(" ")}
      >
        <span>{label}</span>
        <span
          aria-hidden="true"
          className={`w-2.5 text-[9px] leading-none ${dir ? "" : "opacity-40 group-hover:opacity-80"}`}
        >
          {dir === "asc" ? "▲" : dir === "desc" ? "▼" : "↕"}
        </span>
      </button>
    </th>
  )
}

interface SortableHeaderProps {
  label: string
  sortKey: string
  align?: "left" | "right"
  className?: string
}

/** Header for a server-sorted table: the sort lives in ?sort=&dir= and resets paging. */
export default function SortableHeader({ label, sortKey, align = "left", className }: SortableHeaderProps) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const activeDir: SortDir = searchParams.get("dir") === "asc" ? "asc" : "desc"
  const current = searchParams.get("sort") ? { key: searchParams.get("sort") as string, dir: activeDir } : null
  const dir = current?.key === sortKey ? current.dir : null

  function handleSort() {
    const next = nextSortState(current, sortKey)
    const params = new URLSearchParams(searchParams.toString())
    if (next) {
      params.set("sort", next.key)
      params.set("dir", next.dir)
    } else {
      params.delete("sort")
      params.delete("dir")
    }
    params.set("offset", "0")
    router.push(`${pathname}?${params.toString()}`)
  }

  return <SortHeaderCell label={label} align={align} dir={dir} onSort={handleSort} className={className} />
}
