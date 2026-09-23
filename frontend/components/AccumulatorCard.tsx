"use client"

import { useRef, useState } from "react"
import type { AccumulatorLegOut, AccumulatorOut } from "@/lib/types"
import { CURRENCY_SYMBOL, fmtDate, fmtDatetime } from "@/lib/format"
import SelectionEvidenceDialog from "@/components/SelectionEvidenceDialog"

const PRODUCT_COLOR: Record<string, string> = {
  CORE: "var(--core)",
  GROWTH: "var(--growth)",
  ALPHA: "var(--alpha)",
}

const PRODUCT_LABEL_CLASS: Record<string, string> = {
  CORE: "text-[var(--core)]",
  GROWTH: "text-[var(--growth)]",
  ALPHA: "text-[var(--alpha)]",
}

const STATUS_STYLE: Record<string, string> = {
  pending: "status-badge status-badge-pending",
  locked: "status-badge status-badge-locked",
  settled: "status-badge status-badge-settled",
  void: "status-badge status-badge-void",
}

function pct(v: number) {
  return `${(v * 100).toFixed(1)}%`
}

function fmt(v: number | null | undefined, decimals = 2) {
  if (v === null || v === undefined) return "—"
  return v.toFixed(decimals)
}

function matchLabel(leg: AccumulatorLegOut): string {
  if (leg.home_team && leg.away_team) return `${leg.home_team} vs ${leg.away_team}`
  return leg.league_id
}

function kickoffLabel(leg: AccumulatorLegOut): string | null {
  if (!leg.kickoff_utc) return null
  return fmtDatetime(leg.kickoff_utc)
}

function quoteAgeLabel(leg: AccumulatorLegOut): string | null {
  if (!leg.quote_captured_at) return null
  return `Price as of ${fmtDatetime(leg.quote_captured_at)}`
}

function priceSourceLabel(leg: AccumulatorLegOut): string {
  if (leg.bookmaker && leg.quote_captured_at) {
    return `${leg.bookmaker} · ${quoteAgeLabel(leg)}`
  }
  if (leg.bookmaker) return leg.bookmaker
  if (leg.quote_captured_at) return quoteAgeLabel(leg) ?? "Price source unavailable"
  return "Price source unavailable"
}

function matchStateLabel(leg: AccumulatorLegOut): string {
  if (leg.match_state === "live") {
    const timing = leg.live_phase
      ? `${leg.live_phase}${leg.elapsed_minutes !== null ? ` · ${leg.elapsed_minutes}′` : ""}`
      : leg.elapsed_minutes !== null
        ? `${leg.elapsed_minutes}′`
        : null
    return timing ? `LIVE · ${timing}` : "LIVE"
  }
  if (leg.match_state === "won") return "WON"
  if (leg.match_state === "lost") return "LOST"
  if (leg.match_state === "void") return "VOID"
  if (leg.fixture_status === "finished") return "FINISHED · AWAITING SETTLEMENT"
  if (leg.fixture_status === "postponed") return "POSTPONED"
  if (leg.fixture_status === "cancelled") return "CANCELLED"
  return "PENDING"
}

function matchStateClass(state: string): string {
  if (state === "won") return "text-[var(--win)] border-[var(--win)]/40 bg-[var(--win)]/10"
  if (state === "lost") return "text-[var(--loss)] border-[var(--loss)]/40 bg-[var(--loss)]/10"
  if (state === "live") return "text-[var(--accent)] border-[var(--accent)]/40 bg-[var(--accent)]/10"
  if (state === "void") return "text-[var(--text-muted)] border-[var(--border)] bg-[var(--bg-raised)]"
  return "text-[var(--text-secondary)] border-[var(--border)] bg-[var(--bg-raised)]"
}

// Daily Picks ("daily_safe" etc.) are a guaranteed daily product line built
// without the Value Gate; they must never be presented as value tickets.
function isDailyPick(product: string): boolean {
  return product.toLowerCase().startsWith("daily_")
}

export default function AccumulatorCard({ acc }: { acc: AccumulatorOut }) {
  const [selectedLeg, setSelectedLeg] = useState<AccumulatorLegOut | null>(null)
  const triggerRef = useRef<HTMLButtonElement | null>(null)
  const daily = isDailyPick(acc.product)
  // Built at the last-resort rung on a thin slate: the product name alone
  // (e.g. "SAFE") would overstate it, so say so explicitly.
  const fallback = daily && (acc.policy_version ?? "").startsWith("daily-last-resort")
  const product = acc.product.toUpperCase().replace(/_/g, " ")
  const accentColor = daily ? "var(--daily)" : PRODUCT_COLOR[product] ?? "var(--border)"
  const labelClass = daily
    ? "text-[var(--daily)]"
    : PRODUCT_LABEL_CLASS[product] ?? "text-[var(--text-secondary)]"
  const statusStyle = STATUS_STYLE[acc.status] ?? "status-badge status-badge-development"

  return (
    <article
      className="rounded-xl bg-[var(--bg-surface)] border border-[var(--border)] overflow-hidden shadow-[var(--surface-shadow)]"
      style={{ borderLeftWidth: "4px", borderLeftStyle: "solid", borderLeftColor: accentColor }}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 border-b border-[var(--border)] bg-[var(--bg-raised)] px-5 py-4">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 min-w-0">
          <span className={`text-xs font-bold uppercase tracking-widest shrink-0 ${labelClass}`}>
            {product} ACCA
          </span>
          {daily && (
            <span
              className="shrink-0 rounded border border-[var(--border)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)]"
              title={
                fallback
                  ? "Thin slate: built with the widest fallback rules, so it may not match its usual risk profile. Not value-qualified; paper only; no stake is recommended."
                  : "Built from the day's strongest forecasts without the Value Gate. Paper only; no stake is recommended."
              }
            >
              Daily pick · {fallback ? "fallback build · " : ""}not value-qualified
            </span>
          )}
        </div>
        <span className={`shrink-0 ml-3 ${statusStyle}`}>
          {acc.status.toUpperCase()}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 p-4 sm:grid-cols-4">
        {[
          { label: "Ticket odds", value: `${acc.combined_odds.toFixed(2)}×` },
          { label: "Joint probability", value: pct(acc.conservative_joint_probability) },
          { label: "Stressed probability", value: pct(acc.stressed_joint_probability) },
          { label: "Stake", value: acc.stake !== null ? `${CURRENCY_SYMBOL}${fmt(acc.stake)}` : "—" },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] p-2.5">
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">{label}</p>
            <p className="mt-1 text-sm font-bold text-[var(--text-primary)]">{value}</p>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between border-t border-[var(--border)] bg-[var(--bg-raised)] px-5 py-2 text-xs font-semibold text-[var(--text-secondary)]">
        <span>{acc.legs.length} leg{acc.legs.length !== 1 ? "s" : ""} · Published {fmtDate(acc.published_at)}</span>
        <span>Open a match for evidence</span>
      </div>

      {/* Legs — fixture context first */}
      <ul className="divide-y divide-[var(--border)]">
        {acc.legs.map((leg) => {
          const kickoff = kickoffLabel(leg)
          return (
            <li key={leg.id}>
              <button type="button" onClick={(event) => { triggerRef.current = event.currentTarget; setSelectedLeg(leg) }} aria-label={`View evidence for ${matchLabel(leg)}`} className="w-full px-5 py-4 text-left transition-colors hover:bg-[var(--bg-raised)] focus-visible:outline-2 focus-visible:outline-[var(--accent)]">
              {/* Row 1: index + match + competition/kickoff */}
              <div className="flex items-start gap-3 min-w-0">
                <span className="shrink-0 mt-0.5 w-5 h-5 rounded-full bg-[var(--bg-raised)] flex items-center justify-center text-[10px] font-mono text-[var(--text-muted)]">
                  {leg.leg_index + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <span className="font-semibold text-sm text-[var(--text-primary)] truncate">
                      {matchLabel(leg)}
                    </span>
                    {leg.competition_name && (
                      <span className="text-[10px] uppercase tracking-wide text-[var(--text-muted)] shrink-0">
                        {leg.competition_name}
                      </span>
                    )}
                    {kickoff && (
                      <span className="text-[10px] text-[var(--text-muted)] shrink-0 font-mono">
                        {kickoff}
                      </span>
                    )}
                  </div>
                  {/* Row 2: selection + market + odds + edge */}
                  <div className="mt-1 flex items-center gap-3 flex-wrap">
                    <span
                      className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-bold tracking-wide ${matchStateClass(leg.match_state)}`}
                    >
                      {matchStateLabel(leg)}
                    </span>
                    {leg.score !== null && (
                      <span
                        className="font-mono text-xs font-bold text-[var(--text-primary)]"
                        aria-label={`Score ${leg.score}`}
                      >
                        {leg.score}
                      </span>
                    )}
                    <span className="text-xs text-[var(--text-secondary)]">
                      {leg.selection}
                      <span className="text-[var(--text-muted)] ml-1">({leg.market_family})</span>
                    </span>
                    <span className="font-mono text-xs font-semibold text-[var(--text-primary)]" title="Executable decimal price">
                      @{leg.decimal_odds.toFixed(2)}
                    </span>
                    <span className="text-[10px] text-[var(--text-secondary)]" title="Bookmaker and quote timestamp">
                      {priceSourceLabel(leg)}
                    </span>
                    <span className={`font-mono text-xs ${leg.edge >= 0 ? "text-[var(--win)]" : "text-[var(--loss)]"}`}>
                      {leg.edge >= 0 ? "+" : ""}{(leg.edge * 100).toFixed(1)}pp
                    </span>
                    <span className="text-[10px] text-[var(--text-muted)]">
                      {pct(leg.conservative_probability)} {daily ? "est. prob" : "model prob"}
                    </span>
                  </div>
                </div>
                <span aria-hidden="true" className="self-center text-lg text-[var(--accent)]">›</span>
              </div>
              </button>
            </li>
          )
        })}
      </ul>

      {/* Model diagnostics — behind a disclosure */}
      <details className="border-t border-[var(--border)]">
        <summary className="px-5 py-2 text-[10px] text-[var(--text-muted)] cursor-pointer select-none hover:text-[var(--text-secondary)] list-none flex items-center gap-1">
          <span>Why this ticket?</span>
          <span className="opacity-50">›</span>
        </summary>
        <div className="px-5 pb-3 flex flex-wrap gap-4">
          <span className="text-[10px] text-[var(--text-muted)]">
            Objective score <span className="font-mono text-[var(--text-secondary)]">{fmt(acc.objective_score)}</span>
          </span>
          {acc.locked_at && (
            <span className="text-[10px] text-[var(--text-muted)]">
              Locked <span className="font-mono text-[var(--text-secondary)]">{fmtDatetime(acc.locked_at)}</span>
            </span>
          )}
          {acc.risk_policy_version && (
            <span className="text-[10px] text-[var(--text-muted)]">
              Risk v<span className="font-mono text-[var(--text-secondary)]">{acc.risk_policy_version}</span>
            </span>
          )}
        </div>
      </details>
      {selectedLeg && <SelectionEvidenceDialog leg={selectedLeg} ticketStatus={acc.status} daily={daily} onClose={() => { setSelectedLeg(null); triggerRef.current?.focus() }} />}
    </article>
  )
}
