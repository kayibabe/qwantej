import type { AccumulatorOut } from "@/lib/types"

const PRODUCT_STYLE: Record<string, string> = {
  CORE: "border-[var(--core)] text-[var(--core)]",
  GROWTH: "border-[var(--growth)] text-[var(--growth)]",
  ALPHA: "border-[var(--alpha)] text-[var(--alpha)]",
}

const STATUS_STYLE: Record<string, string> = {
  pending: "bg-[#1e2d1e] text-[var(--win)]",
  locked: "bg-[#1a2035] text-[var(--accent)]",
  settled: "bg-[var(--bg-raised)] text-[var(--text-secondary)]",
  void: "bg-[#2d251a] text-[var(--void)]",
}

function pct(v: number) {
  return `${(v * 100).toFixed(1)}%`
}

function fmt(v: number | null | undefined, decimals = 2) {
  if (v === null || v === undefined) return "—"
  return v.toFixed(decimals)
}

export default function AccumulatorCard({ acc }: { acc: AccumulatorOut }) {
  const productStyle = PRODUCT_STYLE[acc.product] ?? "border-[var(--border)] text-[var(--text-secondary)]"
  const statusStyle = STATUS_STYLE[acc.status] ?? "bg-[var(--bg-raised)] text-[var(--text-secondary)]"

  return (
    <article
      className={`rounded-lg border-l-4 ${productStyle.split(" ")[0]} bg-[var(--bg-surface)] border border-[var(--border)] border-l-0 overflow-hidden`}
      style={{ borderLeftWidth: "4px", borderLeftStyle: "solid", borderLeftColor: acc.product === "CORE" ? "var(--core)" : acc.product === "GROWTH" ? "var(--growth)" : "var(--alpha)" }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--border)]">
        <div className="flex items-center gap-3">
          <span className={`text-xs font-bold uppercase tracking-widest ${productStyle.split(" ")[1]}`}>
            {acc.product} ACCA
          </span>
          <span className="text-[var(--text-muted)] text-xs">·</span>
          <span className="text-lg font-bold font-mono text-[var(--text-primary)]">
            {acc.combined_odds.toFixed(2)}
          </span>
          <span className="text-xs text-[var(--text-secondary)]">
            {acc.legs.length} leg{acc.legs.length !== 1 ? "s" : ""}
          </span>
        </div>
        <span className={`rounded px-2 py-0.5 text-xs font-medium ${statusStyle}`}>
          {acc.status.toUpperCase()}
        </span>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-4 divide-x divide-[var(--border)] border-b border-[var(--border)]">
        {[
          { label: "Cons. prob.", value: pct(acc.conservative_joint_probability) },
          { label: "Stressed prob.", value: pct(acc.stressed_joint_probability) },
          { label: "Objective score", value: fmt(acc.objective_score) },
          { label: "Stake", value: acc.stake !== null ? `£${fmt(acc.stake)}` : "—" },
        ].map(({ label, value }) => (
          <div key={label} className="px-4 py-2">
            <p className="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">{label}</p>
            <p className="text-sm font-mono font-medium text-[var(--text-primary)]">{value}</p>
          </div>
        ))}
      </div>

      {/* Legs */}
      <ul className="divide-y divide-[var(--border)]">
        {acc.legs.map((leg) => (
          <li key={leg.id} className="flex items-center justify-between px-5 py-2 text-sm">
            <div className="flex items-center gap-3 min-w-0">
              <span className="shrink-0 w-5 h-5 rounded-full bg-[var(--bg-raised)] flex items-center justify-center text-[10px] font-mono text-[var(--text-muted)]">
                {leg.leg_index + 1}
              </span>
              <span className="truncate text-[var(--text-secondary)] text-xs">{leg.league_id}</span>
              <span className="truncate font-medium">{leg.selection}</span>
              <span className="text-[var(--text-muted)] text-xs">{leg.market_family}</span>
            </div>
            <div className="flex items-center gap-4 shrink-0 font-mono text-xs text-right">
              <span className="text-[var(--text-secondary)]">{leg.decimal_odds.toFixed(2)}</span>
              <span className="text-[var(--text-muted)]">{pct(leg.conservative_probability)}</span>
              <span className={leg.edge >= 0 ? "text-[var(--win)]" : "text-[var(--loss)]"}>
                {leg.edge >= 0 ? "+" : ""}{(leg.edge * 100).toFixed(1)}pp
              </span>
              <span className="text-[var(--text-muted)]">QSS {leg.qss.toFixed(0)}</span>
            </div>
          </li>
        ))}
      </ul>

      {/* Footer */}
      <div className="px-5 py-2 text-[10px] text-[var(--text-muted)] flex gap-4">
        <span>Published {new Date(acc.published_at).toLocaleString()}</span>
        {acc.locked_at && <span>Locked {new Date(acc.locked_at).toLocaleString()}</span>}
        {acc.risk_policy_version && <span>Risk v{acc.risk_policy_version}</span>}
      </div>
    </article>
  )
}
