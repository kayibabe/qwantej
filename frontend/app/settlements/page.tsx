import type { Metadata } from "next"
import { Suspense } from "react"
import { fetchSettlements, fetchSettlementSummary } from "@/lib/api"
import { fmtDate } from "@/lib/format"
import type { SettlementOut } from "@/lib/types"
import StatTile from "@/components/StatTile"
import Pagination from "@/components/Pagination"

export const metadata: Metadata = { title: "Settlements" }

const LIMIT = 50

const OUTCOME_STYLE: Record<string, string> = {
  win: "text-[var(--win)]",
  loss: "text-[var(--loss)]",
  void: "text-[var(--void)]",
  push: "text-[var(--text-secondary)]",
}

function SettlementRow({ s }: { s: SettlementOut }) {
  const outcomeStyle = OUTCOME_STYLE[s.outcome] ?? "text-[var(--text-secondary)]"
  const clvPositive = s.clv !== null && s.clv > 0

  return (
    <tr className="border-b border-[var(--border)] hover:bg-[var(--bg-raised)] transition-colors">
      <td className="px-4 py-2 text-xs text-[var(--text-muted)] font-mono">
        {fmtDate(s.settled_at)}
      </td>
      <td className={`px-4 py-2 text-xs font-semibold uppercase ${outcomeStyle}`}>
        {s.outcome}
      </td>
      <td className="px-4 py-2 text-xs font-mono text-right text-[var(--text-secondary)]">
        {s.taken_odds?.toFixed(2) ?? "—"}
      </td>
      <td className="px-4 py-2 text-xs font-mono text-right text-[var(--text-secondary)]">
        {s.closing_odds?.toFixed(2) ?? "—"}
      </td>
      <td className={`px-4 py-2 text-xs font-mono text-right ${clvPositive ? "text-[var(--win)]" : "text-[var(--loss)]"}`}>
        {s.clv !== null ? s.clv.toFixed(3) : "—"}
      </td>
      <td className="px-4 py-2 text-xs font-mono text-right text-[var(--text-secondary)]">
        {s.brier_contribution !== null ? s.brier_contribution.toFixed(4) : "—"}
      </td>
      <td className="px-4 py-2 text-xs text-[var(--text-muted)]">
        {s.calibration_bin ?? "—"}
      </td>
    </tr>
  )
}

async function SettlementsTable({
  outcome,
  subjectType,
  offset,
}: {
  outcome: string | undefined
  subjectType: string
  offset: number
}) {
  const page = await fetchSettlements({
    subject_type: subjectType,
    outcome,
    limit: LIMIT,
    offset,
  }).catch(() => null)

  if (!page) {
    return <p className="text-sm text-[var(--loss)]">Could not load settlements.</p>
  }

  if (page.items.length === 0) {
    return <p className="text-sm text-[var(--text-muted)]">No settlements match this filter.</p>
  }

  return (
    <>
      <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
        <table className="w-full text-sm">
          <thead className="bg-[var(--bg-surface)] text-[10px] uppercase tracking-wider text-[var(--text-muted)]">
            <tr>
              {["Date", "Outcome", "Taken odds", "Closing odds", "CLV", "Brier", "Cal. bin"].map((h) => (
                <th key={h} className="px-4 py-2 text-left font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-[var(--bg)]">
            {page.items.map((s) => (
              <SettlementRow key={s.id} s={s} />
            ))}
          </tbody>
        </table>
      </div>
      <Pagination total={page.total} limit={page.limit} offset={page.offset} />
    </>
  )
}

export default async function SettlementsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const sp = await searchParams
  const outcome = typeof sp.outcome === "string" ? sp.outcome : undefined
  const subjectType = typeof sp.type === "string" ? sp.type : "prediction"
  const offset = Number(sp.offset ?? 0)

  const summary = await fetchSettlementSummary({ subject_type: subjectType }).catch(() => null)

  const outcomes = ["", "win", "loss", "void", "push"]

  return (
    <div className="flex flex-col gap-6 p-8">
      <div>
        <h1 className="text-xl font-semibold text-[var(--text-primary)]">Settlements</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Effective (non-superseded) settlement records
        </p>
      </div>

      {/* Subject type toggle */}
      <div className="flex gap-2">
        {["prediction", "accumulator"].map((t) => (
          <a
            key={t}
            href={`?type=${t}&offset=0`}
            className={[
              "rounded px-3 py-1 text-xs font-medium border transition-colors capitalize",
              subjectType === t
                ? "bg-[var(--accent)] border-[var(--accent)] text-white"
                : "border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-raised)]",
            ].join(" ")}
          >
            {t}
          </a>
        ))}
      </div>

      {/* Summary tiles */}
      {summary && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatTile
            label="Win rate"
            value={summary.win_rate !== null ? `${(summary.win_rate * 100).toFixed(1)}%` : null}
            sub={`${summary.n_wins}W / ${summary.n_losses}L / ${summary.n_voids}V`}
            valueClass={
              summary.win_rate !== null && summary.win_rate >= 0.5
                ? "text-[var(--win)]"
                : "text-[var(--text-primary)]"
            }
          />
          <StatTile label="Settled" value={summary.n_settled} sub="total" />
          <StatTile
            label="Avg CLV"
            value={summary.avg_clv !== null ? summary.avg_clv.toFixed(3) : null}
            valueClass={
              summary.avg_clv !== null && summary.avg_clv > 0
                ? "text-[var(--win)]"
                : "text-[var(--text-primary)]"
            }
          />
          <StatTile
            label="Avg Brier"
            value={summary.avg_brier !== null ? summary.avg_brier.toFixed(4) : null}
            sub="lower is better"
          />
        </div>
      )}

      {/* Outcome filter */}
      <div className="flex gap-2 flex-wrap">
        {outcomes.map((o) => {
          const label = o === "" ? "All outcomes" : o.charAt(0).toUpperCase() + o.slice(1)
          const active = (outcome ?? "") === o
          return (
            <a
              key={o}
              href={o ? `?type=${subjectType}&outcome=${o}&offset=0` : `?type=${subjectType}&offset=0`}
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
        key={`${subjectType}-${outcome}-${offset}`}
        fallback={<p className="text-sm text-[var(--text-muted)] animate-pulse">Loading…</p>}
      >
        <SettlementsTable outcome={outcome} subjectType={subjectType} offset={offset} />
      </Suspense>
    </div>
  )
}
