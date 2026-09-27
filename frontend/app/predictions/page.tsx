import type { Metadata } from "next"
import { Suspense } from "react"
import { fetchPredictions, fetchPricedMarkets } from "@/lib/api"
import { fmtDatetime } from "@/lib/format"
import { marketLabel, selectionLabel } from "@/lib/forecasts"
import type { PredictionOut } from "@/lib/types"
import Pagination from "@/components/Pagination"
import SortableHeader from "@/components/SortableHeader"

export const metadata: Metadata = { title: "Forecasts" }

const LIMIT = 50

const OUTCOME: Record<string, { label: string; cls: string }> = {
  win: { label: "WON", cls: "text-[var(--win)] border-[var(--win)]/40 bg-[var(--win)]/10" },
  loss: { label: "LOST", cls: "text-[var(--loss)] border-[var(--loss)]/40 bg-[var(--loss)]/10" },
  void: { label: "VOID", cls: "text-[var(--void)] border-[var(--void)]/40 bg-[var(--void)]/10" },
  push: { label: "PUSH", cls: "text-[var(--void)] border-[var(--void)]/40 bg-[var(--void)]/10" },
}

function evTone(ev: number | null) {
  if (ev === null) return "text-[var(--text-muted)]"
  return ev > 0 ? "text-[var(--win)]" : "text-[var(--loss)]"
}

function PredictionRow({ p }: { p: PredictionOut }) {
  const outcome = p.outcome ? OUTCOME[p.outcome] : undefined
  return (
    <tr className="border-t border-[var(--border-subtle)] transition-colors hover:bg-[var(--bg-raised)]">
      <td className="px-4 py-3">
        <p className="text-sm font-semibold text-[var(--text-primary)]">{p.home_team && p.away_team ? `${p.home_team} vs ${p.away_team}` : "Match unavailable"}</p>
        <p className="text-xs text-[var(--text-muted)]">{[p.competition_name, p.kickoff_utc ? fmtDatetime(p.kickoff_utc) : null].filter(Boolean).join(" · ")}</p>
      </td>
      <td className="px-4 py-3">
        <p className="text-sm text-[var(--text-primary)]">{selectionLabel(p)}</p>
        <p className="text-xs text-[var(--text-muted)]">{marketLabel(p.market)}{p.bookmaker ? ` · ${p.bookmaker}` : ""}</p>
      </td>
      <td className="px-4 py-3 text-right font-mono text-sm text-[var(--text-primary)]">{p.executable_odds?.toFixed(2) ?? "—"}</td>
      <td className="px-4 py-3 text-right font-mono text-xs text-[var(--text-secondary)]">
        {p.conservative_probability !== null ? `${(p.conservative_probability * 100).toFixed(1)}%` : "—"}
      </td>
      <td className={`px-4 py-3 text-right font-mono text-xs ${evTone(p.expected_value)}`}>
        {p.expected_value !== null ? `${p.expected_value > 0 ? "+" : ""}${(p.expected_value * 100).toFixed(1)}%` : "—"}
      </td>
      <td className="hidden px-4 py-3 text-right font-mono text-xs text-[var(--text-secondary)] md:table-cell">{p.qss?.toFixed(0) ?? "—"}</td>
      <td className="px-4 py-3 text-right">
        {outcome
          ? <span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-bold tracking-wide ${outcome.cls}`}>{outcome.label}</span>
          : <span className="text-xs text-[var(--text-muted)]">Open</span>}
      </td>
    </tr>
  )
}

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
  const page = await fetchPredictions({ market, sort, dir, limit: LIMIT, offset, priced_only: true }).catch(() => null)

  if (!page) {
    return <p className="text-sm text-[var(--loss)]">Could not load forecasts.</p>
  }

  if (page.items.length === 0) {
    return <p className="rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg-surface)] p-6 text-sm text-[var(--text-secondary)]">No priced forecasts match this filter.</p>
  }

  return (
    <>
      <div className="overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] shadow-[var(--surface-shadow)]">
        <table className="w-full text-sm">
          <caption className="sr-only">Priced forecasts, newest first unless sorted. Column headers sort the table; Match sorts by kickoff time.</caption>
          <thead className="border-b border-[var(--border)] text-[10px] uppercase tracking-wider text-[var(--text-muted)]">
            <tr>
              <SortableHeader label="Match" sortKey="kickoff_utc" />
              <SortableHeader label="Pick" sortKey="selection" />
              <SortableHeader label="Odds" sortKey="executable_odds" align="right" />
              <SortableHeader label="Model prob." sortKey="conservative_probability" align="right" />
              <SortableHeader label="EV" sortKey="expected_value" align="right" />
              <SortableHeader label="QSS" sortKey="qss" align="right" className="hidden px-4 py-2 font-medium md:table-cell" />
              <SortableHeader label="Result" sortKey="outcome" align="right" />
            </tr>
          </thead>
          <tbody>
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

export default async function PredictionsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const sp = await searchParams
  const market = typeof sp.market === "string" ? sp.market : undefined
  const sort = typeof sp.sort === "string" ? sp.sort : undefined
  const dir = sp.dir === "asc" ? "asc" : sp.dir === "desc" ? "desc" : undefined
  const offset = Math.max(0, Number(sp.offset ?? 0) || 0)
  const markets = await fetchPricedMarkets().catch(() => [] as string[])

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 p-4 sm:p-8">
      <div>
        <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Forecasts</h1>
        <p className="mt-1 max-w-3xl text-sm text-[var(--text-secondary)]">
          Every archived forecast that had a bookmaker price, with the match it was for and how it settled.
          Forecasts without odds are hidden: they could not have been bet.
        </p>
      </div>

      <nav aria-label="Filter by market" className="flex flex-wrap gap-2">
        {["", ...markets].map((m) => {
          const active = (market ?? "") === m
          const sortQuery = sort ? `&sort=${encodeURIComponent(sort)}&dir=${dir ?? "desc"}` : ""
          return (
            <a
              key={m || "all"}
              href={`?${m ? `market=${encodeURIComponent(m)}&` : ""}offset=0${sortQuery}`}
              aria-current={active ? "page" : undefined}
              className={[
                "rounded border px-3 py-1 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
                active
                  ? "border-[var(--accent)] bg-[var(--accent)] text-[var(--bg-surface)]"
                  : "border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-raised)]",
              ].join(" ")}
            >
              {m ? marketLabel(m) : "All markets"}
            </a>
          )
        })}
      </nav>

      <Suspense
        key={`${market}-${sort}-${dir}-${offset}`}
        fallback={<p className="animate-pulse text-sm text-[var(--text-muted)]">Loading…</p>}
      >
        <PredictionsTable market={market} sort={sort} dir={dir} offset={offset} />
      </Suspense>
    </div>
  )
}
