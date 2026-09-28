"use client"

import { useId, useState } from "react"
import { CURRENCY_SYMBOL, fmtSignedPct } from "@/lib/format"
import { simulateTicketStake } from "@/lib/tickets"
import type { AccumulatorPeriodResultOut } from "@/lib/types"

function money(value: number, signed = true): string {
  const sign = signed && value > 0 ? "+" : value < 0 ? "−" : ""
  return `${sign}${CURRENCY_SYMBOL}${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

/** A browser-only historical stake replay; it never records or recommends a stake. */
export default function TicketStakeSimulator({ periods }: { periods: readonly AccumulatorPeriodResultOut[] }) {
  const inputId = useId()
  const [value, setValue] = useState("")
  const stake = value === "" ? null : Number(value)
  const simulation = stake === null ? null : simulateTicketStake(periods, stake)
  const invalid = value !== "" && simulation === null
  const totalStake = simulation && stake !== null ? simulation.settledTickets * stake : null
  const profit = simulation && stake !== null ? simulation.flatUnitProfit * stake : null

  return (
    <section className="rounded-xl border border-[var(--accent)]/30 bg-[var(--accent-soft)] p-4 sm:p-5" aria-labelledby="stake-simulator-heading">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[.14em] text-[var(--accent)]">Historical simulation</p>
          <h2 id="stake-simulator-heading" className="mt-1 text-lg font-semibold text-[var(--text-primary)]">What if every settled ticket used the same stake?</h2>
        </div>
        <label htmlFor={inputId} className="grid gap-1 text-sm font-semibold text-[var(--text-secondary)] sm:w-56">
          Simulated stake per ticket
          <span className="flex items-center rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] px-3 focus-within:outline-2 focus-within:outline-[var(--accent)]">
            <span className="text-sm text-[var(--text-muted)]">{CURRENCY_SYMBOL}</span>
            <input id={inputId} type="number" inputMode="decimal" min="0.01" step="0.01" value={value} onChange={(event) => setValue(event.target.value)} placeholder="e.g. 100" className="h-10 min-w-0 flex-1 bg-transparent px-2 font-mono text-[var(--text-primary)] outline-none" aria-label="Simulated stake per ticket" aria-describedby={`${inputId}-help`} />
          </span>
        </label>
      </div>
      <p id={`${inputId}-help`} className="mt-3 text-xs leading-5 text-[var(--text-secondary)]">
        Replays archived prices and corrected outcomes only. Void tickets are refunded; pending tickets are excluded. This is not a recommended stake and is not saved.
      </p>
      {invalid ? (
        <p className="mt-3 text-sm font-medium text-[var(--loss)]" role="alert">Enter a positive, finite stake to see the simulation.</p>
      ) : simulation && totalStake !== null && profit !== null ? (
        simulation.settledTickets ? (
          <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4" aria-live="polite">
            <Metric label="Settled tickets" value={simulation.settledTickets.toLocaleString()} />
            <Metric label="Total staked" value={money(totalStake, false)} />
            <Metric label="P&amp;L" value={money(profit)} tone={profit} />
            <Metric label="ROI / yield" value={fmtSignedPct(simulation.roi)} tone={simulation.roi ?? 0} />
          </dl>
        ) : (
          <p className="mt-3 text-sm text-[var(--text-secondary)]" aria-live="polite">No settled priced tickets are available to simulate yet.</p>
        )
      ) : null}
    </section>
  )
}

function Metric({ label, value, tone = 0 }: { label: string; value: string; tone?: number }) {
  const color = tone > 0 ? "text-[var(--win)]" : tone < 0 ? "text-[var(--loss)]" : "text-[var(--text-primary)]"
  return <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] p-3"><dt className="text-xs text-[var(--text-muted)]">{label}</dt><dd className={`mt-1 font-mono text-base font-semibold ${color}`}>{value}</dd></div>
}
