"use client"

import { useRouter, usePathname, useSearchParams } from "next/navigation"
import { useCallback } from "react"

interface PaginationProps {
  total: number
  limit: number
  offset: number
}

export default function Pagination({ total, limit, offset }: PaginationProps) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const navigate = useCallback(
    (newOffset: number) => {
      const params = new URLSearchParams(searchParams.toString())
      params.set("offset", String(newOffset))
      router.push(`${pathname}?${params.toString()}`)
    },
    [router, pathname, searchParams],
  )

  const page = Math.floor(offset / limit) + 1
  const totalPages = Math.ceil(total / limit)
  const hasPrev = offset > 0
  const hasNext = offset + limit < total

  if (totalPages <= 1) return null

  return (
    <div className="flex items-center justify-between py-4 text-sm text-[var(--text-secondary)]">
      <span>
        {offset + 1}–{Math.min(offset + limit, total)} of {total}
      </span>
      <div className="flex gap-2">
        <button
          onClick={() => navigate(Math.max(0, offset - limit))}
          disabled={!hasPrev}
          className="rounded px-3 py-1 border border-[var(--border)] hover:bg-[var(--bg-raised)] disabled:opacity-40 disabled:cursor-not-allowed"
        >
          ← Prev
        </button>
        <span className="px-3 py-1">
          {page} / {totalPages}
        </span>
        <button
          onClick={() => navigate(offset + limit)}
          disabled={!hasNext}
          className="rounded px-3 py-1 border border-[var(--border)] hover:bg-[var(--bg-raised)] disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Next →
        </button>
      </div>
    </div>
  )
}
