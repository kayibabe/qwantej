import type { Metadata } from "next"
import { fetchSettlementSummary, fetchAccumulators } from "@/lib/api"
import StatTile from "@/components/StatTile"
import AccumulatorCard from "@/components/AccumulatorCard"

export const metadata: Metadata = { title: "Dashboard" }

function fmtPct(v: number | null) {
  if (v === null) return null
  return `${(v * 100).toFixed(1)}%`
}

function fmtNum(v: number | null, decimals = 3) {
  if (v === null) return null
  return v.toFixed(decimals)
}

export default async function DashboardPage() {
  const [summary, accPage] = await Promise.all([
    fetchSettlementSummary().catch(() => null),
    fetchAccumulators({ limit: 5 }).catch(() => null),
  ])

  return (
    <div className="flex flex-col gap-8 p-8">
      <div>
        <h1 className="text-xl font-semibold text-[var(--text-primary)]">Dashboard</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Prediction settlement performance — all-time
        </p>
      </div>

      {/* KPI tiles */}
      <section aria-label="Key performance indicators">
        {summary === null ? (
          <p className="text-sm text-[var(--loss)]">
            Could not load settlement summary — is the backend running?
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatTile
              label="Win rate"
              value={fmtPct(summary.win_rate)}
              sub={`${summary.n_wins}W / ${summary.n_losses}L / ${summary.n_voids}V`}
              valueClass={
                summary.win_rate !== null && summary.win_rate >= 0.5
                  ? "text-[var(--win)]"
                  : "text-[var(--text-primary)]"
              }
            />
            <StatTile
              label="Settled"
              value={summary.n_settled}
              sub="total effective settlements"
            />
            <StatTile
              label="Avg CLV"
              value={fmtNum(summary.avg_clv)}
              sub="closing-line value"
              valueClass={
                summary.avg_clv !== null && summary.avg_clv > 0
                  ? "text-[var(--win)]"
                  : "text-[var(--text-primary)]"
              }
            />
            <StatTile
              label="Avg Brier"
              value={fmtNum(summary.avg_brier)}
              sub="lower is better"
            />
          </div>
        )}
      </section>

      {/* Recent accumulators */}
      <section aria-label="Recent accumulator tickets">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
          Recent accumulators
        </h2>
        {accPage === null ? (
          <p className="text-sm text-[var(--loss)]">
            Could not reach the API — is the backend running?
          </p>
        ) : accPage.items.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)]">No accumulators yet.</p>
        ) : (
          <div className="flex flex-col gap-4">
            {accPage.items.map((acc) => (
              <AccumulatorCard key={acc.id} acc={acc} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
