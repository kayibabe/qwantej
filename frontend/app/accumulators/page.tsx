import type { Metadata } from "next"
import { Suspense } from "react"
import { fetchAccumulators } from "@/lib/api"
import AccumulatorCard from "@/components/AccumulatorCard"
import Pagination from "@/components/Pagination"

export const metadata: Metadata = { title: "Accumulators" }

const LIMIT = 10

async function AccumulatorList({
  status,
  offset,
}: {
  status: string | undefined
  offset: number
}) {
  const page = await fetchAccumulators({ status, limit: LIMIT, offset }).catch(() => null)

  if (!page) {
    return (
      <p className="text-sm text-[var(--loss)]">Could not load accumulators — is the API running?</p>
    )
  }

  if (page.items.length === 0) {
    return <p className="text-sm text-[var(--text-muted)]">No accumulators match this filter.</p>
  }

  return (
    <>
      <div className="flex flex-col gap-4">
        {page.items.map((acc) => (
          <AccumulatorCard key={acc.id} acc={acc} />
        ))}
      </div>
      <Pagination total={page.total} limit={page.limit} offset={page.offset} />
    </>
  )
}

export default async function AccumulatorsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const sp = await searchParams
  const status = typeof sp.status === "string" ? sp.status : undefined
  const offset = Number(sp.offset ?? 0)

  const statuses = ["", "pending", "locked", "settled", "void"]

  return (
    <div className="flex flex-col gap-8 p-8">
      <div>
        <h1 className="text-xl font-semibold text-[var(--text-primary)]">Accumulators</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Core, Growth and Alpha accumulator tickets
        </p>
      </div>

      {/* Status filter */}
      <div className="flex gap-2 flex-wrap">
        {statuses.map((s) => {
          const label = s === "" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)
          const active = (status ?? "") === s
          return (
            <a
              key={s}
              href={s ? `?status=${s}&offset=0` : `?offset=0`}
              className={[
                "rounded px-3 py-1 text-xs font-medium border transition-colors",
                active
                  ? "bg-[var(--accent)] border-[var(--accent)] text-white"
                  : "border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-raised)]",
              ].join(" ")}
            >
              {label}
            </a>
          )
        })}
      </div>

      <Suspense
        key={`${status}-${offset}`}
        fallback={<p className="text-sm text-[var(--text-muted)] animate-pulse">Loading…</p>}
      >
        <AccumulatorList status={status} offset={offset} />
      </Suspense>
    </div>
  )
}
