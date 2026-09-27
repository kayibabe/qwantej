import Link from "next/link"
import { Suspense } from "react"
import { fetchAccumulatorResults } from "@/lib/api"
import type { AccumulatorPeriodResultOut, AccumulatorProductResultOut, ResultsGranularity } from "@/lib/types"

const VIEWS: { value: ResultsGranularity; label: string; limit: number; caption: string }[] = [
  { value: "day", label: "Day", limit: 31, caption: "last 31 days with tickets" },
  { value: "month", label: "Month", limit: 24, caption: "last 24 months with tickets" },
  { value: "year", label: "Year", limit: 10, caption: "last 10 years with tickets" },
]

// Value products first, then the separate Daily Picks line, then anything new.
const PRODUCT_ORDER = ["core", "growth", "alpha", "daily_safe", "daily_balanced", "daily_bold"]

function productRank(product: string): number {
  const i = PRODUCT_ORDER.indexOf(product.toLowerCase())
  return i === -1 ? PRODUCT_ORDER.length : i
}

function productLabel(product: string): string {
  return product
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ")
}

function productColor(product: string): string {
  const p = product.toLowerCase()
  if (p.startsWith("daily_")) return "var(--daily)"
  if (p === "core" || p === "growth" || p === "alpha") return `var(--${p})`
  return "var(--text-secondary)"
}

function periodLabel(period: string, granularity: ResultsGranularity): string {
  if (granularity === "year") return period
  const [y, m, d] = period.split("-").map(Number)
  const date = new Date(Date.UTC(y, m - 1, d ?? 1))
  return date.toLocaleDateString("en-GB", {
    timeZone: "UTC",
    ...(granularity === "day" ? { weekday: "short", day: "numeric" } : {}),
    month: "short",
    year: "numeric",
  })
}

function pct(v: number | null): string {
  return v === null ? "—" : `${(v * 100).toFixed(0)}%`
}

function sumTallies(product: string, tallies: AccumulatorProductResultOut[]): AccumulatorProductResultOut {
  const t = tallies.reduce(
    (acc, x) => ({ won: acc.won + x.won, lost: acc.lost + x.lost, void: acc.void + x.void, pending: acc.pending + x.pending }),
    { won: 0, lost: 0, void: 0, pending: 0 },
  )
  const decided = t.won + t.lost
  return {
    product,
    daily_pick: product.toLowerCase().startsWith("daily_"),
    ...t,
    total: t.won + t.lost + t.void + t.pending,
    win_rate: decided ? t.won / decided : null,
  }
}

function ResultCell({ t }: { t: AccumulatorProductResultOut | undefined }) {
  if (!t) return <span className="text-[var(--text-muted)]" aria-label="No tickets">—</span>
  const extras = [t.pending ? `${t.pending} pending` : null, t.void ? `${t.void} void` : null].filter(Boolean)
  return (
    <div className="flex flex-col items-end gap-0.5">
      <span className="font-mono text-xs">
        <span className={t.won ? "font-bold text-[var(--win)]" : "text-[var(--text-secondary)]"}>{t.won}W</span>
        <span className="text-[var(--text-muted)]"> · </span>
        <span className={t.lost ? "text-[var(--loss)]" : "text-[var(--text-secondary)]"}>{t.lost}L</span>
        {t.win_rate !== null && <span className="ml-1.5 text-[var(--text-muted)]">{pct(t.win_rate)}</span>}
      </span>
      {extras.length > 0 && <span className="text-[10px] text-[var(--text-muted)]">{extras.join(" · ")}</span>}
    </div>
  )
}

function WinnerChips({ period }: { period: AccumulatorPeriodResultOut }) {
  const winners = period.products.filter((p) => p.won > 0).sort((a, b) => productRank(a.product) - productRank(b.product))
  if (winners.length === 0) {
    const open = period.products.some((p) => p.pending > 0)
    return <span className="text-xs text-[var(--text-muted)]">{open ? "Awaiting results" : "No winners"}</span>
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {winners.map((p) => (
        <span
          key={p.product}
          className="whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide"
          style={{ color: productColor(p.product), borderColor: `color-mix(in srgb, ${productColor(p.product)} 45%, transparent)` }}
        >
          {productLabel(p.product)}{p.won > 1 ? ` ×${p.won}` : ""}
        </span>
      ))}
    </div>
  )
}

async function ResultsTable({ view }: { view: (typeof VIEWS)[number] }) {
  const data = await fetchAccumulatorResults({ granularity: view.value, limit: view.limit }).catch(() => null)

  if (!data) {
    return (
      <section className="rounded-lg border border-[var(--loss)]/60 p-5" aria-live="polite">
        <h2 className="font-semibold text-[var(--loss)]">Ticket results are temporarily unavailable</h2>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">We could not load the results history. Refresh this page in a moment.</p>
      </section>
    )
  }
  if (data.periods.length === 0) {
    return <p className="text-sm text-[var(--text-muted)]">No accumulator tickets have been published yet.</p>
  }

  const products = Array.from(new Set(data.periods.flatMap((p) => p.products.map((t) => t.product)))).sort(
    (a, b) => productRank(a) - productRank(b) || a.localeCompare(b),
  )
  const totals = products.map((product) =>
    sumTallies(product, data.periods.flatMap((p) => p.products.filter((t) => t.product === product))),
  )

  return (
    <>
      <section aria-labelledby="totals-heading" className="flex flex-col gap-3">
        <h2 id="totals-heading" className="text-sm font-semibold text-[var(--text-primary)]">
          Totals for the periods shown <span className="font-normal text-[var(--text-muted)]">({view.caption})</span>
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {totals.map((t) => (
            <div
              key={t.product}
              className="rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] px-4 py-3"
              style={{ borderTopWidth: "3px", borderTopColor: productColor(t.product) }}
            >
              <p className="text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">{productLabel(t.product)}</p>
              <p className="mt-1 font-mono text-xl font-semibold text-[var(--text-primary)]">
                {t.won}<span className="text-sm font-normal text-[var(--text-muted)]"> won</span>
              </p>
              <p className="mt-0.5 text-xs text-[var(--text-muted)]">
                {t.lost} lost · {pct(t.win_rate)} win rate{t.pending ? ` · ${t.pending} pending` : ""}
              </p>
            </div>
          ))}
        </div>
      </section>

      <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
        <table className="w-full text-sm">
          <caption className="sr-only">
            Accumulator tickets won and lost per product, grouped by {view.label.toLowerCase()} (UTC publication date)
          </caption>
          <thead className="bg-[var(--bg-surface)] text-[10px] uppercase tracking-wider text-[var(--text-muted)]">
            <tr>
              <th scope="col" className="px-4 py-2 text-left">{view.label}</th>
              <th scope="col" className="px-4 py-2 text-left">Won</th>
              {products.map((p) => (
                <th key={p} scope="col" className="whitespace-nowrap px-4 py-2 text-right" style={{ color: productColor(p) }}>
                  {productLabel(p)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-[var(--bg)]">
            {data.periods.map((period) => {
              const byProduct = new Map(period.products.map((t) => [t.product, t]))
              return (
                <tr key={period.period} className="border-t border-[var(--border)] hover:bg-[var(--bg-raised)]">
                  <th scope="row" className="whitespace-nowrap px-4 py-2 text-left font-mono text-xs font-medium text-[var(--text-primary)]">
                    <time dateTime={period.period}>{periodLabel(period.period, view.value)}</time>
                  </th>
                  <td className="min-w-[14rem] px-4 py-2"><WinnerChips period={period} /></td>
                  {products.map((p) => (
                    <td key={p} className="whitespace-nowrap px-4 py-2 text-right"><ResultCell t={byProduct.get(p)} /></td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {data.total_periods > data.periods.length && (
        <p className="text-xs text-[var(--text-muted)]">
          Showing the {data.periods.length} most recent of {data.total_periods} {view.label.toLowerCase()}s with tickets.
        </p>
      )}
    </>
  )
}

/** "By period" tab of the Performance page: which ticket types won, by day, month or year. */
export default function ResultsByPeriod({ by }: { by: string | undefined }) {
  const view = VIEWS.find((v) => v.value === by) ?? VIEWS[0]

  return (
    <div className="flex flex-col gap-6">
      <p className="max-w-3xl text-sm text-[var(--text-secondary)]">
        Which accumulator types won, by year, month and day. Tickets are grouped by UTC publication date. A ticket is
        lost as soon as any leg loses, and won once every leg is settled with no losses (void legs drop out). Daily
        Picks are a separate, paper-only line and are not value-qualified.
      </p>

      <nav aria-label="Group results by" className="flex flex-wrap gap-2">
        {VIEWS.map((v) => {
          const active = v.value === view.value
          return (
            <Link
              key={v.value}
              href={`?tab=periods&by=${v.value}`}
              aria-current={active ? "page" : undefined}
              className={[
                "rounded border px-3 py-1 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
                active
                  ? "border-[var(--accent)] bg-[var(--accent)] text-white"
                  : "border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-raised)]",
              ].join(" ")}
            >
              By {v.label.toLowerCase()}
            </Link>
          )
        })}
      </nav>

      <Suspense key={view.value} fallback={<p className="animate-pulse text-sm text-[var(--text-muted)]">Loading…</p>}>
        <ResultsTable view={view} />
      </Suspense>
    </div>
  )
}
