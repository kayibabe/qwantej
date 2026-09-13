import type { AccumulatorLegOut, AccumulatorOut } from "@/lib/types"
import { CURRENCY_SYMBOL, fmtDate, fmtDatetime } from "@/lib/format"

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

export default function AccumulatorCard({ acc }: { acc: AccumulatorOut }) {
  const product = acc.product.toUpperCase()
  const accentColor = PRODUCT_COLOR[product] ?? "var(--border)"
  const labelClass = PRODUCT_LABEL_CLASS[product] ?? "text-[var(--text-secondary)]"
  const statusStyle = STATUS_STYLE[acc.status] ?? "status-badge status-badge-development"

  return (
    <article
      className="rounded-lg bg-[var(--bg-surface)] border border-[var(--border)] overflow-hidden shadow-[var(--surface-shadow)]"
      style={{ borderLeftWidth: "4px", borderLeftStyle: "solid", borderLeftColor: accentColor }}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--border)] bg-[var(--bg-raised)] px-5 py-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className={`text-xs font-bold uppercase tracking-widest shrink-0 ${labelClass}`}>
            {product} ACCA
          </span>
          <span className="text-[var(--text-muted)] text-xs shrink-0">·</span>
          <span className="text-lg font-bold font-mono text-[var(--text-primary)] shrink-0">
            {acc.combined_odds.toFixed(2)}
          </span>
          <span className="text-xs text-[var(--text-secondary)] shrink-0">
            {acc.legs.length} leg{acc.legs.length !== 1 ? "s" : ""}
          </span>
        </div>
        <span className={`shrink-0 ml-3 ${statusStyle}`}>
          {acc.status.toUpperCase()}
        </span>
      </div>

      {/* Legs — fixture context first */}
      <ul className="divide-y divide-[var(--border)]">
        {acc.legs.map((leg) => {
          const kickoff = kickoffLabel(leg)
          return (
            <li key={leg.id} className="px-5 py-3">
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
                      {pct(leg.conservative_probability)} model prob
                    </span>
                  </div>
                </div>
              </div>
            </li>
          )
        })}
      </ul>

      {/* KPI row — responsive 2-col on mobile, 4-col on sm+ */}
      <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-y sm:divide-y-0 divide-[var(--border)] border-t border-[var(--border)]">
        {[
          { label: "Joint prob.", value: pct(acc.conservative_joint_probability) },
          { label: "Stressed", value: pct(acc.stressed_joint_probability) },
          { label: "Stake", value: acc.stake !== null ? `${CURRENCY_SYMBOL}${fmt(acc.stake)}` : "—" },
          { label: "Published", value: fmtDate(acc.published_at) },
        ].map(({ label, value }) => (
          <div key={label} className="px-4 py-2">
            <p className="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">{label}</p>
            <p className="text-sm font-mono font-medium text-[var(--text-primary)]">{value}</p>
          </div>
        ))}
      </div>

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
    </article>
  )
}
