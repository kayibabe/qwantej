import Link from "next/link"
import { fmtDatetime, fmtUnits } from "@/lib/format"
import { selectionLabel } from "@/lib/forecasts"
import { RESULT_LABEL, isDailyPick, productColor, productLabel } from "@/lib/tickets"
import type { AccumulatorLegOut, AccumulatorOut, TicketResult } from "@/lib/types"

const RESULT_BOX: Record<TicketResult, string> = {
  won: "border-transparent bg-[var(--result-won-bg)] text-[var(--result-won-fg)]",
  lost: "border-transparent bg-[var(--result-lost-bg)] text-[var(--result-lost-fg)]",
  void: "border-[var(--void)]/50 bg-[var(--void)]/10 text-[var(--text-primary)]",
  pending: "border-[var(--border)] bg-[var(--bg-raised)] text-[var(--text-primary)]",
}

/** The big result box on the right of a ticket row: "Won / +3.12 u". */
export function ResultBox({ result, profit }: { result: TicketResult; profit: number | null | undefined }) {
  const word = RESULT_LABEL[result].charAt(0) + RESULT_LABEL[result].slice(1).toLowerCase()
  return (
    <span className={`flex w-full flex-col items-center justify-center rounded-lg border px-3 py-2 text-center sm:w-32 ${RESULT_BOX[result]}`}>
      <span className="text-sm font-semibold">{word}</span>
      <span className="font-mono text-base font-bold">{result === "pending" ? "–" : fmtUnits(profit)}</span>
    </span>
  )
}

function legState(leg: AccumulatorLegOut): { label: string; cls: string } | null {
  if (leg.match_state === "won") return { label: "Won", cls: "text-[var(--win)] border-[var(--win)]/40" }
  if (leg.match_state === "lost") return { label: "Lost", cls: "text-[var(--loss)] border-[var(--loss)]/40" }
  if (leg.match_state === "void") return { label: "Void", cls: "text-[var(--void)] border-[var(--void)]/40" }
  if (leg.match_state === "live") {
    const minute = leg.elapsed_minutes !== null ? ` ${leg.elapsed_minutes}′` : ""
    return { label: `Live${minute}`, cls: "text-[var(--accent)] border-[var(--accent)]/40" }
  }
  if (leg.match_state === "awaiting_result") return { label: "Result stale", cls: "text-[var(--void)] border-[var(--void)]/40" }
  if (leg.fixture_status === "finished") return { label: "FT · settling", cls: "text-[var(--text-secondary)] border-[var(--border)]" }
  return null
}

function LegLine({ leg }: { leg: AccumulatorLegOut }) {
  const state = legState(leg)
  const match = leg.home_team && leg.away_team ? `${leg.home_team} vs ${leg.away_team}` : leg.competition_name ?? leg.league_id
  const pick = selectionLabel({ market: leg.market_family, selection: leg.selection, line: null, home_team: leg.home_team, away_team: leg.away_team })
  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
      <span className="min-w-0 font-medium text-[var(--text-primary)]">{match}</span>
      <span className="text-[var(--accent)]">{pick}</span>
      <span className="font-mono text-xs text-[var(--text-muted)]">@{leg.decimal_odds.toFixed(2)}</span>
      {leg.score !== null && (
        <span className="rounded bg-[var(--accent)] px-1.5 py-0.5 font-mono text-xs font-bold text-[var(--bg-surface)]" aria-label={`Score ${leg.score}`}>
          {leg.score}
        </span>
      )}
      {state
        ? <span className={`rounded border px-1.5 py-px text-[10px] font-bold uppercase tracking-wide ${state.cls}`}>{state.label}</span>
        : leg.kickoff_utc && <span className="text-xs text-[var(--text-muted)]">{fmtDatetime(leg.kickoff_utc)}</span>}
    </li>
  )
}

/** One ticket in the archive: product and price, its legs, and the result box. */
export default function TicketRow({ acc }: { acc: AccumulatorOut }) {
  const result: TicketResult = acc.status === "void" ? "void" : acc.result ?? "pending"
  const color = productColor(acc.product)
  const legs = acc.legs.length
  return (
    <li>
      <Link
        href={`/accumulators/${acc.id}`}
        className="grid items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] px-4 py-3 shadow-[var(--surface-shadow)] transition-colors hover:bg-[var(--bg-raised)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] sm:grid-cols-[1fr_auto] sm:px-5"
        style={{ borderLeftWidth: "4px", borderLeftColor: color }}
      >
        <span className="min-w-0">
          <span className="flex flex-wrap items-baseline gap-x-2">
            <span className="text-base font-semibold" style={{ color }}>{productLabel(acc.product)} ACCA</span>
            <span className="font-mono text-base font-semibold text-[var(--accent)]">({acc.combined_odds.toFixed(2)})</span>
          </span>
          <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-[var(--text-muted)]">
            {isDailyPick(acc.product) && (
              <span className="rounded border border-[var(--daily)]/40 px-1.5 py-px font-semibold text-[var(--daily)]">Daily pick</span>
            )}
            <span>{legs} leg{legs === 1 ? "" : "s"}</span>
            <span aria-hidden="true">·</span>
            <span>Probability {(acc.conservative_joint_probability * 100).toFixed(1)}%</span>
            <span aria-hidden="true">·</span>
            <span>Published {fmtDatetime(acc.published_at)}</span>
          </span>
          <ul className="mt-2 flex flex-col gap-1">
            {acc.legs.map((leg) => <LegLine key={leg.id} leg={leg} />)}
          </ul>
        </span>
        <ResultBox result={result} profit={acc.profit_units} />
      </Link>
    </li>
  )
}
