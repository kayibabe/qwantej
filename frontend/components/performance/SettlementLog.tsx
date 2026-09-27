import { Suspense } from "react"
import { fetchSettlements, fetchSettlementSummary } from "@/lib/api"
import { fmtDate } from "@/lib/format"
import type { SettlementOut } from "@/lib/types"
import StatTile from "@/components/StatTile"
import Pagination from "@/components/Pagination"
import SortableHeader from "@/components/SortableHeader"

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

const COLUMNS: { label: string; sortKey: string; align: "left" | "right" }[] = [
  { label: "Date", sortKey: "settled_at", align: "left" },
  { label: "Outcome", sortKey: "outcome", align: "left" },
  { label: "Taken odds", sortKey: "taken_odds", align: "right" },
  { label: "Closing odds", sortKey: "closing_odds", align: "right" },
  { label: "CLV", sortKey: "clv", align: "right" },
  { label: "Brier", sortKey: "brier_contribution", align: "right" },
  { label: "Cal. bin", sortKey: "calibration_bin", align: "left" },
]

async function SettlementsTable({
  outcome,
  subjectType,
  sort,
  dir,
  offset,
}: {
  outcome: string | undefined
  subjectType: string
  sort: string | undefined
  dir: "asc" | "desc" | undefined
  offset: number
}) {
  const page = await fetchSettlements({
    subject_type: subjectType,
    outcome,
    sort,
    dir,
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
          <caption className="sr-only">Effective settlement records, {subjectType} evidence</caption>
          <thead className="bg-[var(--bg-surface)] text-[10px] uppercase tracking-wider text-[var(--text-muted)]">
            <tr>
              {COLUMNS.map((c) => (
                <SortableHeader key={c.sortKey} label={c.label} sortKey={c.sortKey} align={c.align} />
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

function FilterLink({ href, active, children }: { href: string; active: boolean; children: React.ReactNode }) {
  return (
    <a
      href={href}
      aria-current={active ? "true" : undefined}
      className={[
        "rounded px-3 py-1 text-xs font-medium border transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
        active
          ? "bg-[var(--accent)] border-[var(--accent)] text-white"
          : "border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-raised)]",
      ].join(" ")}
    >
      {children}
    </a>
  )
}

/** "Settlement log" tab of the Performance page: the raw, effective settlement records. */
export default async function SettlementLog({ sp }: { sp: Record<string, string | string[] | undefined> }) {
  const outcome = typeof sp.outcome === "string" ? sp.outcome : undefined
  const subjectType = typeof sp.type === "string" ? sp.type : "prediction"
  const sort = typeof sp.sort === "string" ? sp.sort : undefined
  const dir = sp.dir === "asc" ? "asc" : sp.dir === "desc" ? "desc" : undefined
  const offset = Number(sp.offset ?? 0)
  const sortQuery = sort ? `&sort=${encodeURIComponent(sort)}&dir=${dir ?? "desc"}` : ""

  const summary = await fetchSettlementSummary({ subject_type: subjectType }).catch(() => null)

  const outcomes = ["", "win", "loss", "void", "push"]

  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-[var(--text-secondary)]">
        Effective (non-superseded) settlement records, one row per settled selection or ticket.
      </p>

      <nav aria-label="Settlement evidence type" className="flex gap-2">
        {["prediction", "accumulator"].map((t) => (
          <FilterLink key={t} href={`?tab=settlements&type=${t}&offset=0${sortQuery}`} active={subjectType === t}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </FilterLink>
        ))}
      </nav>

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

      <nav aria-label="Filter by outcome" className="flex gap-2 flex-wrap">
        {outcomes.map((o) => (
          <FilterLink
            key={o}
            href={`?tab=settlements&type=${subjectType}${o ? `&outcome=${o}` : ""}&offset=0${sortQuery}`}
            active={(outcome ?? "") === o}
          >
            {o === "" ? "All outcomes" : o.charAt(0).toUpperCase() + o.slice(1)}
          </FilterLink>
        ))}
      </nav>

      <Suspense
        key={`${subjectType}-${outcome}-${sort}-${dir}-${offset}`}
        fallback={<p className="text-sm text-[var(--text-muted)] animate-pulse">Loading…</p>}
      >
        <SettlementsTable outcome={outcome} subjectType={subjectType} sort={sort} dir={dir} offset={offset} />
      </Suspense>
    </div>
  )
}
