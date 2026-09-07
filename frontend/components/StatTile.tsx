interface StatTileProps {
  label: string
  value: string | number | null
  sub?: string
  valueClass?: string
}

export default function StatTile({ label, value, sub, valueClass }: StatTileProps) {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] px-5 py-4">
      <p className="text-xs font-medium uppercase tracking-wider text-[var(--text-secondary)]">
        {label}
      </p>
      <p className={`mt-1 text-2xl font-semibold font-mono ${valueClass ?? "text-[var(--text-primary)]"}`}>
        {value ?? "—"}
      </p>
      {sub && (
        <p className="mt-1 text-xs text-[var(--text-muted)]">{sub}</p>
      )}
    </div>
  )
}
