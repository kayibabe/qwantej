"use client"

import { useRouter, usePathname, useSearchParams } from "next/navigation"

interface SortableHeaderProps {
  label: string
  sortKey: string
  align?: "left" | "right"
}

export default function SortableHeader({ label, sortKey, align = "left" }: SortableHeaderProps) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const activeSort = searchParams.get("sort")
  const activeDir = searchParams.get("dir") === "asc" ? "asc" : "desc"
  const isActive = activeSort === sortKey
  const nextDir: "asc" | "desc" = isActive && activeDir === "asc" ? "desc" : "asc"

  function handleClick() {
    const params = new URLSearchParams(searchParams.toString())
    params.set("sort", sortKey)
    params.set("dir", nextDir)
    params.set("offset", "0")
    router.push(`${pathname}?${params.toString()}`)
  }

  return (
    <th className={`px-4 py-2 font-medium ${align === "right" ? "text-right" : "text-left"}`}>
      <button
        type="button"
        onClick={handleClick}
        aria-label={`Sort by ${label}${isActive ? `, currently ${activeDir === "asc" ? "ascending" : "descending"}` : ""}`}
        className={[
          "inline-flex items-center gap-1 transition-colors hover:text-[var(--text-primary)] focus-visible:outline-2 focus-visible:outline-[var(--accent)]",
          align === "right" ? "flex-row-reverse" : "",
          isActive ? "text-[var(--accent)]" : "",
        ].join(" ")}
      >
        <span>{label}</span>
        <span className="w-2.5 text-[9px] leading-none" aria-hidden="true">
          {isActive ? (activeDir === "asc" ? "▲" : "▼") : ""}
        </span>
      </button>
    </th>
  )
}
