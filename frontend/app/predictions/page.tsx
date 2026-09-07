import type { Metadata } from "next"
import { Suspense } from "react"
import { fetchPredictions } from "@/lib/api"
import { fmtDate } from "@/lib/format"
import type { PredictionOut } from "@/lib/types"
import Pagination from "@/components/Pagination"

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

async function PredictionsTable({
  market,
  offset,
}: {
  market: string | undefined
  offset: number
}) {
  const page = await fetchPredictions({ market, limit: LIMIT, offset }).catch(() => null)

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
              {["Date", "Market", "Selection", "Cons. prob.", "Odds", "EV", "QSS", "DQS"].map((h) => (
                <th key={h} className="px-4 py-2 text-left font-medium">
                  {h}
                </th>
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
          return (
            <a
              key={m}
              href={m ? `?market=${encodeURIComponent(m)}&offset=0` : `?offset=0`}
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
        key={`${market}-${offset}`}
        fallback={<p className="text-sm text-[var(--text-muted)] animate-pulse">Loading…</p>}
      >
        <PredictionsTable market={market} offset={offset} />
      </Suspense>
    </div>
  )
}
