import type { Metadata } from "next"
import { Suspense } from "react"
import { fetchPredictions } from "@/lib/api"
import { fmtDate } from "@/lib/format"
import type { PredictionOut } from "@/lib/types"
import Pagination from "@/components/Pagination"
import SortableHeader from "@/components/SortableHeader"

export const metadata: Metadata = { title: "Predictions" }

const LIMIT = 50

function outcomeColor(ev: number | null) {
  if (ev === null) return "text-[var(--text-muted)]"
  return ev > 0 ? "text-[var(--win)]" : "text-[var(--loss)]"
}

function PredictionRow({ p }: { p: PredictionOut }) {
  return (
    <tr className="border-b border-[var(--border)] hover:bg-[var(--bg-raised)] transition-colors">
      <td className="px-4 py-2 text-xs text-[var(--text-muted)] font-mono">
        {fmtDate(p.prediction_timestamp)}
      </td>
      <td className="px-4 py-2 text-sm font-medium">{p.market}</td>
      <td className="px-4 py-2 text-sm">{p.selection}</td>
      <td className="px-4 py-2 text-xs font-mono text-right text-[var(--text-secondary)]">
        {p.conservative_probability !== null ? `${(p.conservative_probability * 100).toFixed(1)}%` : "—"}
      </td>
      <td className="px-4 py-2 text-xs font-mono text-right text-[var(--text-secondary)]">
        {p.executable_odds?.toFixed(2) ?? "—"}
      </td>
      <td className={`px-4 py-2 text-xs font-mono text-right ${outcomeColor(p.expected_value)}`}>
        {p.expected_value !== null ? `${(p.expected_value * 100).toFixed(1)}%` : "—"}
      </td>
      <td className="px-4 py-2 text-xs font-mono text-right text-[var(--text-secondary)]">
        {p.qss?.toFixed(0) ?? "—"}
      </td>
      <td className="px-4 py-2 text-xs font-mono text-right text-[var(--text-secondary)]">
        {p.dqs?.toFixed(0) ?? "—"}
      </td>
    </tr>
  )
}

const COLUMNS: { label: string; sortKey: string; align: "left" | "right" }[] = [
  { label: "Date", sortKey: "prediction_timestamp", align: "left" },
  { label: "Market", sortKey: "market", align: "left" },
  { label: "Selection", sortKey: "selection", align: "left" },
  { label: "Cons. prob.", sortKey: "conservative_probability", align: "right" },
  { label: "Odds", sortKey: "executable_odds", align: "right" },
  { label: "EV", sortKey: "expected_value", align: "right" },
  { label: "QSS", sortKey: "qss", align: "right" },
  { label: "DQS", sortKey: "dqs", align: "right" },
]

async function PredictionsTable({
  market,
  sort,
  dir,
  offset,
}: {
  market: string | undefined
  sort: string | undefined
  dir: "asc" | "desc" | undefined
  offset: number
}) {
  const page = await fetchPredictions({ market, sort, dir, limit: LIMIT, offset }).catch(() => null)

  if (!page) {
    return <p className="text-sm text-[var(--loss)]">Could not load predictions.</p>
  }

  if (page.items.length === 0) {
    return <p className="text-sm text-[var(--text-muted)]">No predictions match this filter.</p>
  }

  return (
    <>
      <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
        <table className="w-full text-sm">
          <thead className="bg-[var(--bg-surface)] text-[10px] uppercase tracking-wider text-[var(--text-muted)]">
            <tr>
              {COLUMNS.map((c) => (
                <SortableHeader key={c.sortKey} label={c.label} sortKey={c.sortKey} align={c.align} />
              ))}
            </tr>
          </thead>
          <tbody className="bg-[var(--bg)]">
            {page.items.map((p) => (
              <PredictionRow key={p.id} p={p} />
            ))}
          </tbody>
        </table>
      </div>
      <Pagination total={page.total} limit={page.limit} offset={page.offset} />
    </>
  )
}

const MARKETS = ["", "1X2", "BTTS", "Over 1.5", "Over 2.5", "Under 2.5", "Under 3.5", "1X", "X2"]

export default async function PredictionsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const sp = await searchParams
  const market = typeof sp.market === "string" ? sp.market : undefined
  const sort = typeof sp.sort === "string" ? sp.sort : undefined
  const dir = sp.dir === "asc" ? "asc" : sp.dir === "desc" ? "desc" : undefined
  const offset = Number(sp.offset ?? 0)

  return (
    <div className="flex flex-col gap-6 p-8">
      <div>
        <h1 className="text-xl font-semibold text-[var(--text-primary)]">Predictions</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Immutable prediction archive, newest first
        </p>
      </div>

      {/* Market filter */}
      <div className="flex gap-2 flex-wrap">
        {MARKETS.map((m) => {
          const label = m === "" ? "All markets" : m
          const active = (market ?? "") === m
          const sortQuery = sort ? `&sort=${encodeURIComponent(sort)}&dir=${dir ?? "desc"}` : ""
          return (
            <a
              key={m}
              href={`?${m ? `market=${encodeURIComponent(m)}&` : ""}offset=0${sortQuery}`}
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
        key={`${market}-${sort}-${dir}-${offset}`}
        fallback={<p className="text-sm text-[var(--text-muted)] animate-pulse">Loading…</p>}
      >
        <PredictionsTable market={market} sort={sort} dir={dir} offset={offset} />
      </Suspense>
    </div>
  )
}
