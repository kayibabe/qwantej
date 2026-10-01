import type { Metadata } from "next"
import { Suspense } from "react"
import { fetchPredictions, fetchPredictionMarketSummary, fetchPricedMarkets } from "@/lib/api"
import { fmtDatetime } from "@/lib/format"
import { marketLabel, selectionLabel } from "@/lib/forecasts"
import type { PredictionOut } from "@/lib/types"
import Pagination from "@/components/Pagination"
import SortableHeader from "@/components/SortableHeader"

export const metadata: Metadata = { title: "Forecasts" }

const LIMIT = 50
type Scope = "all" | "production" | "research" | "awaiting" | "overdue"

function summaryLabel(summary: { total: number; won: number; lost: number; void: number; unsettled: number } | undefined): string {
  if (!summary) return "0 total"
  return `${summary.total} total · ${summary.won}W · ${summary.lost}L · ${summary.void}V · ${summary.unsettled}U`
}

const SCOPE_OPTIONS: { value: Scope; label: string; description: string }[] = [
  { value: "production", label: "Published production", description: "Gate-passed forecasts used for production signals" },
  { value: "awaiting", label: "Awaiting settlement", description: "Future fixtures without an effective result" },
  { value: "overdue", label: "Settlement overdue", description: "Past kickoffs without an effective result" },
  { value: "research", label: "Research", description: "Research-mode forecasts kept outside production" },
  { value: "all", label: "All archived", description: "Every priced forecast, including rejected rows" },
]

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

function AuditBadges({ p }: { p: PredictionOut }) {
  return (
    <div className="flex flex-wrap justify-end gap-1 text-[10px] font-semibold tracking-wide">
      <span className={p.research_mode
        ? "rounded border border-[var(--void)]/40 bg-[var(--void)]/10 px-1.5 py-0.5 text-[var(--void)]"
        : "rounded border border-[var(--accent)]/40 bg-[var(--accent)]/10 px-1.5 py-0.5 text-[var(--accent)]"}
      >
        {p.research_mode ? "RESEARCH" : "PRODUCTION"}
      </span>
      <span className={p.gate_passed
        ? "rounded border border-[var(--win)]/40 bg-[var(--win)]/10 px-1.5 py-0.5 text-[var(--win)]"
        : "rounded border border-[var(--loss)]/40 bg-[var(--loss)]/10 px-1.5 py-0.5 text-[var(--loss)]"}
      >
        {p.gate_passed ? "GATE PASSED" : "GATE REJECTED"}
      </span>
    </div>
  )
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
      <td className="hidden px-4 py-3 lg:table-cell">
        <p className="max-w-48 truncate text-xs text-[var(--text-secondary)]" title={p.model_version_label ?? undefined}>
          {p.model_version_label ?? "Model lineage unavailable"}
        </p>
      </td>
      <td className="px-4 py-3 text-right font-mono text-sm text-[var(--text-primary)]">{p.executable_odds?.toFixed(2) ?? "—"}</td>
      <td className="px-4 py-3 text-right font-mono text-xs text-[var(--text-secondary)]">
        {p.conservative_probability !== null ? `${(p.conservative_probability * 100).toFixed(1)}%` : "—"}
      </td>
      <td className={`px-4 py-3 text-right font-mono text-xs ${evTone(p.expected_value)}`}>
        {p.expected_value !== null ? `${p.expected_value > 0 ? "+" : ""}${(p.expected_value * 100).toFixed(1)}%` : "—"}
      </td>
      <td className="hidden px-4 py-3 text-right font-mono text-xs text-[var(--text-secondary)] md:table-cell">{p.qss?.toFixed(0) ?? "—"}</td>
      <td className="hidden px-4 py-3 text-right md:table-cell"><AuditBadges p={p} /></td>
      <td className="px-4 py-3 text-right">
        {outcome
          ? <span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-bold tracking-wide ${outcome.cls}`}>{outcome.label}</span>
          : p.settlement_overdue
            ? <span title="Kickoff has passed but no effective settlement is recorded." className="inline-flex rounded border border-[var(--loss)]/40 bg-[var(--loss)]/10 px-1.5 py-0.5 text-[10px] font-bold tracking-wide text-[var(--loss)]">SETTLEMENT OVERDUE</span>
            : <span className="text-xs text-[var(--text-muted)]">Open</span>}
      </td>
    </tr>
  )
}

async function PredictionsTable({
  market,
  scope,
  sort,
  dir,
  offset,
}: {
  market: string | undefined
  scope: Scope
  sort: string | undefined
  dir: "asc" | "desc" | undefined
  offset: number
}) {
  // Research forecasts may be probability-only while their market odds are
  // being reconstructed. Production and other operational views remain
  // restricted to priced forecasts.
  const page = await fetchPredictions({
    market,
    scope,
    sort,
    dir,
    limit: LIMIT,
    offset,
    priced_only: scope !== "research",
  }).catch(() => null)

  if (!page) {
    return <p className="text-sm text-[var(--loss)]">Could not load forecasts.</p>
  }

  if (page.items.length === 0) {
    return <p className="rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg-surface)] p-6 text-sm text-[var(--text-secondary)]">No {scope === "research" ? "research" : "priced"} forecasts match this filter.</p>
  }

  return (
    <>
      <div className="overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] shadow-[var(--surface-shadow)]">
        <table className="w-full text-sm">
          <caption className="sr-only">{scope === "research" ? "Research forecasts" : "Priced forecasts"}, newest first unless sorted. Column headers sort the table; Match sorts by kickoff time.</caption>
          <thead className="border-b border-[var(--border)] text-[10px] uppercase tracking-wider text-[var(--text-muted)]">
            <tr>
              <SortableHeader label="Match" sortKey="kickoff_utc" />
              <SortableHeader label="Pick" sortKey="selection" />
              <SortableHeader label="Model version" sortKey="model_version" className="hidden px-4 py-2 font-medium lg:table-cell" />
              <SortableHeader label="Odds" sortKey="executable_odds" align="right" />
              <SortableHeader label="Model prob." sortKey="conservative_probability" align="right" />
              <SortableHeader label="EV" sortKey="expected_value" align="right" />
              <SortableHeader label="QSS" sortKey="qss" align="right" className="hidden px-4 py-2 font-medium md:table-cell" />
              <SortableHeader label="Audit" sortKey="audit" align="right" className="hidden px-4 py-2 font-medium md:table-cell" />
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
  const requestedScope = typeof sp.scope === "string" ? sp.scope : undefined
  const scope: Scope = SCOPE_OPTIONS.some((option) => option.value === requestedScope)
    ? requestedScope as Scope
    : "production"
  const sort = typeof sp.sort === "string" ? sp.sort : undefined
  const dir = sp.dir === "asc" ? "asc" : sp.dir === "desc" ? "desc" : undefined
  const offset = Math.max(0, Number(sp.offset ?? 0) || 0)
  const markets = await fetchPricedMarkets().catch(() => [] as string[])
  const marketSummaries = await fetchPredictionMarketSummary(scope).catch(() => [])
  const summaryByMarket = new Map(marketSummaries.map((summary) => [summary.market, summary]))
  const allSummary = marketSummaries.reduce(
    (total, summary) => ({
      total: total.total + summary.total,
      won: total.won + summary.won,
      lost: total.lost + summary.lost,
      void: total.void + summary.void,
      unsettled: total.unsettled + summary.unsettled,
    }),
    { total: 0, won: 0, lost: 0, void: 0, unsettled: 0 },
  )
  const visibleMarkets = scope === "research"
    ? Array.from(new Set([...markets, "TEAM_TOTALS"]))
    : markets

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 p-4 sm:p-8">
      <div>
        <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Forecasts</h1>
        <p className="mt-1 max-w-3xl text-sm text-[var(--text-secondary)]">
          Archived forecasts with bookmaker prices, separated by operational purpose. Start with production forecasts,
          then open the research or full archive views when you need audit evidence. Forecasts without odds remain hidden because they could not have been bet.
        </p>
      </div>

      <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-4 shadow-[var(--surface-shadow)]" aria-labelledby="forecast-scope-heading">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h2 id="forecast-scope-heading" className="text-sm font-semibold text-[var(--text-primary)]">Choose a forecast view</h2>
            <p className="mt-1 text-xs text-[var(--text-muted)]">{SCOPE_OPTIONS.find((option) => option.value === scope)?.description}</p>
          </div>
          <span className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">{scope === "all" ? "Audit archive" : scope}</span>
        </div>
        <nav aria-label="Forecast scope" className="mt-3 flex flex-wrap gap-2">
          {SCOPE_OPTIONS.map((option) => {
            const active = scope === option.value
            const params = new URLSearchParams({ scope: option.value, offset: "0" })
            if (market) params.set("market", market)
            if (sort) { params.set("sort", sort); params.set("dir", dir ?? "desc") }
            return <a key={option.value} href={`?${params.toString()}`} aria-current={active ? "page" : undefined} className={["rounded border px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]", active ? "border-[var(--accent)] bg-[var(--accent)] text-[var(--bg-surface)]" : "border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-raised)]"].join(" ")}>{option.label}</a>
          })}
        </nav>
      </section>

      <nav aria-label="Filter by market" className="flex flex-wrap items-center gap-2">
        <span className="mr-1 text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Market</span>
        {["", ...visibleMarkets].map((m) => {
          const active = (market ?? "") === m
          const params = new URLSearchParams({ scope, offset: "0" })
          if (m) params.set("market", m)
          if (sort) { params.set("sort", sort); params.set("dir", dir ?? "desc") }
          return (
            <a
              key={m || "all"}
              href={`?${params.toString()}`}
              aria-current={active ? "page" : undefined}
              className={[
                "rounded border px-3 py-1 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
                active
                  ? "border-[var(--accent)] bg-[var(--accent)] text-[var(--bg-surface)]"
                  : "border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-raised)]",
              ].join(" ")}
            >
              <span>{m ? marketLabel(m) : "All markets"}</span>
              <span className="ml-1 text-[10px] opacity-80">
                {summaryLabel(m ? summaryByMarket.get(m) : allSummary)}
              </span>
            </a>
          )
        })}
      </nav>

      <Suspense
        key={`${market}-${scope}-${sort}-${dir}-${offset}`}
        fallback={<p className="animate-pulse text-sm text-[var(--text-muted)]">Loading…</p>}
      >
        <PredictionsTable market={market} scope={scope} sort={sort} dir={dir} offset={offset} />
      </Suspense>
    </div>
  )
}
