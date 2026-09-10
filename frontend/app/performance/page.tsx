import type { Metadata } from "next"
import { fetchPerformanceReport } from "@/lib/api"
import StatTile from "@/components/StatTile"

export const metadata: Metadata = { title: "Performance" }

function pct(v: number | null, decimals = 1) {
  if (v === null) return null
  return `${(v * 100).toFixed(decimals)}%`
}

function num(v: number | null, decimals = 3) {
  if (v === null) return null
  return v.toFixed(decimals)
}

function signed(v: number | null, decimals = 1) {
  if (v === null) return null
  const s = (v * 100).toFixed(decimals)
  return v >= 0 ? `+${s}%` : `${s}%`
}

function colourRoi(v: number | null) {
  if (v === null) return undefined
  return v > 0 ? "text-[var(--win)]" : v < 0 ? "text-[var(--loss)]" : undefined
}

function colourClv(v: number | null) {
  if (v === null) return undefined
  return v > 0 ? "text-[var(--win)]" : undefined
}

export default async function PerformancePage() {
  const report = await fetchPerformanceReport().catch(() => null)

  return (
    <div className="flex flex-col gap-8 p-8">
      <div>
        <h1 className="text-xl font-semibold text-[var(--text-primary)]">Performance</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          All-time KPI report across settled predictions
        </p>
      </div>

      {report === null ? (
        <p className="text-sm text-[var(--loss)]">
          Could not load performance report — is the backend running?
        </p>
      ) : (
        <>
          {/* Counts */}
          <section aria-label="Settlement counts">
            <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
              Settlements
            </h2>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
              <StatTile label="Total" value={report.n_total} />
              <StatTile label="Settled" value={report.n_settled} />
              <StatTile
                label="Wins"
                value={report.n_wins}
                valueClass="text-[var(--win)]"
              />
              <StatTile
                label="Losses"
                value={report.n_losses}
                valueClass="text-[var(--loss)]"
              />
              <StatTile label="Voids" value={report.n_voids} />
              <StatTile label="Pushes" value={report.n_pushes} />
            </div>
          </section>

          {/* Financial */}
          <section aria-label="Financial performance">
            <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
              Financial
            </h2>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <StatTile
                label="ROI"
                value={signed(report.roi)}
                sub="return on investment"
                valueClass={colourRoi(report.roi)}
              />
              <StatTile
                label="Total profit"
                value={num(report.total_profit, 2)}
                sub="units"
                valueClass={colourRoi(report.total_profit)}
              />
              <StatTile label="Total staked" value={num(report.total_stake, 2)} sub="units" />
              <StatTile
                label="Max drawdown"
                value={report.max_drawdown !== null ? `-${(report.max_drawdown * 100).toFixed(1)}%` : null}
                sub="peak-to-trough"
                valueClass={
                  report.max_drawdown !== null && report.max_drawdown > 0.15
                    ? "text-[var(--loss)]"
                    : undefined
                }
              />
            </div>
          </section>

          {/* Betting */}
          <section aria-label="Betting quality">
            <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
              Betting
            </h2>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <StatTile
                label="Hit rate"
                value={pct(report.hit_rate)}
                sub={
                  report.break_even_hit_rate !== null
                    ? `break-even ${(report.break_even_hit_rate * 100).toFixed(1)}%`
                    : undefined
                }
                valueClass={
                  report.hit_rate !== null &&
                  report.break_even_hit_rate !== null &&
                  report.hit_rate >= report.break_even_hit_rate
                    ? "text-[var(--win)]"
                    : undefined
                }
              />
              <StatTile label="Avg odds" value={num(report.average_odds, 2)} sub="decimal" />
              <StatTile
                label="Mean CLV"
                value={signed(report.mean_clv)}
                sub={`n = ${report.n_clv}`}
                valueClass={colourClv(report.mean_clv)}
              />
              <StatTile
                label="Volatility"
                value={pct(report.volatility)}
                sub="std dev of returns"
              />
            </div>
          </section>

          {/* Predictive quality */}
          <section aria-label="Predictive quality">
            <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
              Predictive quality
            </h2>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
              <StatTile label="Brier score" value={num(report.brier_score)} sub="lower is better" />
              <StatTile
                label="Brier skill"
                value={num(report.brier_skill_score)}
                sub="vs market baseline"
                valueClass={
                  report.brier_skill_score !== null && report.brier_skill_score > 0
                    ? "text-[var(--win)]"
                    : undefined
                }
              />
              <StatTile label="Log loss" value={num(report.log_loss)} sub="lower is better" />
              <StatTile label="ECE" value={num(report.ece)} sub="expected calibration error" />
              <StatTile
                label="Calibration"
                value={
                  report.calibration_slope !== null && report.calibration_intercept !== null
                    ? `${report.calibration_slope.toFixed(2)}x + ${report.calibration_intercept.toFixed(3)}`
                    : null
                }
                sub="slope × p + intercept"
              />
            </div>
          </section>
        </>
      )}
    </div>
  )
}
