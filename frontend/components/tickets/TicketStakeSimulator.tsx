"use client"

import { useEffect, useId, useState } from "react"
import { loadSimulationTickets } from "@/app/accumulators/actions"
import { CURRENCY_SYMBOL, fmtSignedPct } from "@/lib/format"
import { periodLabel, simulateTicketRows } from "@/lib/tickets"
import type { AccumulatorOut, AccumulatorPeriodResultOut, ResultsGranularity } from "@/lib/types"

const GRANULARITIES: { value: ResultsGranularity; label: string }[] = [
  { value: "year", label: "Year" },
  { value: "month", label: "Month" },
  { value: "day", label: "Day" },
]

function money(value: number, signed = true): string {
  const sign = signed && value > 0 ? "+" : value < 0 ? "−" : ""
  return `${sign}${CURRENCY_SYMBOL}${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

type Props = {
  periods: Record<ResultsGranularity, readonly AccumulatorPeriodResultOut[]>
  initialScope?: { granularity: ResultsGranularity; period: string }
  initialTickets?: AccumulatorOut[] | null
}

/** Browser-only historical replay; it never records or recommends a stake. */
export default function TicketStakeSimulator({ periods, initialScope, initialTickets = null }: Props) {
  const inputId = useId()
  const defaultGranularity = initialScope?.granularity ?? "year"
  const [granularity, setGranularity] = useState<ResultsGranularity>(defaultGranularity)
  const [period, setPeriod] = useState(initialScope?.period ?? periods[defaultGranularity][0]?.period ?? "")
  const [ticketId, setTicketId] = useState("all")
  const [value, setValue] = useState("1")
  const [tickets, setTickets] = useState<AccumulatorOut[] | null>(initialTickets)
  const [loading, setLoading] = useState(initialTickets === null)

  const options = periods[granularity]
  const selectedTickets = tickets?.filter((ticket) =>
    ticketId === "all" || ticket.product === ticketId
  ) ?? []
  const selectedResults = selectedTickets.reduce(
    (counts, ticket) => {
      if (ticket.result === "won") counts.won += 1
      if (ticket.result === "lost") counts.lost += 1
      if (ticket.result === "void") counts.void += 1
      return counts
    },
    { won: 0, lost: 0, void: 0 },
  )
  const stake = value === "" ? null : Number(value)
  const simulation = stake === null || tickets === null ? null : simulateTicketRows(selectedTickets, stake)
  const invalid = value !== "" && simulation === null && tickets !== null
  const totalStake = simulation && stake !== null ? simulation.settledTickets * stake : null
  const totalReturned = simulation && stake !== null ? simulation.returnedUnits * stake : null
  const profit = simulation && stake !== null ? simulation.flatUnitProfit * stake : null

  useEffect(() => {
    if (!period) return
    if (initialScope?.granularity === granularity && initialScope.period === period && initialTickets !== null) return
    let active = true
    loadSimulationTickets(granularity, period).then((loaded) => {
      if (!active) return
      setTickets(loaded)
      setLoading(false)
    })
    return () => { active = false }
  }, [granularity, period, initialScope, initialTickets])

  function changeGranularity(next: ResultsGranularity) {
    setLoading(true)
    setGranularity(next)
    const nextPeriod = periods[next][0]?.period ?? ""
    setPeriod(nextPeriod)
    if (initialScope?.granularity === next && initialScope.period === nextPeriod && initialTickets !== null) {
      setTickets(initialTickets)
      setLoading(false)
    }
    setTicketId("all")
  }

  function changePeriod(next: string) {
    setLoading(true)
    setPeriod(next)
    if (initialScope?.granularity === granularity && initialScope.period === next && initialTickets !== null) {
      setTickets(initialTickets)
      setLoading(false)
    }
    setTicketId("all")
  }

  return (
    <section className="min-w-0 max-w-full overflow-hidden rounded-xl border border-[var(--accent)]/30 bg-[var(--accent-soft)] p-4 sm:p-5" aria-labelledby="stake-simulator-heading">
      <div className="flex min-w-0 flex-col gap-4">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[.14em] text-[var(--accent)]">Historical simulation</p>
          <h2 id="stake-simulator-heading" className="mt-1 break-words text-lg font-semibold text-[var(--text-primary)]">What if every selected ticket used the same stake?</h2>
        </div>
        <div className="grid min-w-0 gap-3 sm:grid-cols-3">
          <Select label="Section" value={granularity} onChange={(next) => changeGranularity(next as ResultsGranularity)} options={GRANULARITIES} />
          <Select label={granularity === "day" ? "Day" : granularity === "month" ? "Month" : "Year"} value={period} onChange={changePeriod} options={options.map((item) => ({ value: item.period, label: periodLabel(item.period, granularity) }))} />
          <div className="grid min-w-0 gap-1 text-sm font-semibold text-[var(--text-secondary)]">
            <label htmlFor={`${inputId}-ticket-type`}>Tickets</label>
            <select id={`${inputId}-ticket-type`} value={ticketId} onChange={(event) => setTicketId(event.target.value)} disabled={loading || tickets === null} className="h-10 min-w-0 max-w-full rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] px-3 font-normal text-[var(--text-primary)] focus-visible:outline-2 focus-visible:outline-[var(--accent)]">
              <option value="all">All ACCA tickets</option>
              <option value="daily_balanced">Daily Balanced ACCA</option>
              <option value="daily_safe">Daily Safe ACCA</option>
              <option value="daily_bold">Daily Bold ACCA</option>
            </select>
            {!loading && tickets !== null && <div className="flex flex-wrap gap-1.5 pt-0.5 text-xs font-semibold" aria-live="polite" aria-label="Ticket results">
              <span className="rounded-full border border-[var(--win)]/30 bg-[var(--win)]/10 px-2 py-0.5 text-[var(--win)]">{selectedResults.won} won</span>
              <span className="rounded-full border border-[var(--loss)]/30 bg-[var(--loss)]/10 px-2 py-0.5 text-[var(--loss)]">{selectedResults.lost} lost</span>
              <span className="rounded-full border border-[var(--void)]/40 bg-[var(--void)]/10 px-2 py-0.5 text-[var(--void)]">{selectedResults.void} void</span>
            </div>}
          </div>
        </div>
        <label htmlFor={inputId} className="grid min-w-0 gap-1 text-sm font-semibold text-[var(--text-secondary)] sm:max-w-xs">
          Simulated stake per ticket
          <span className="flex min-w-0 max-w-full items-center overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] px-3 focus-within:outline-2 focus-within:outline-[var(--accent)]">
            <span className="shrink-0 text-sm text-[var(--text-muted)]">{CURRENCY_SYMBOL}</span>
            <input id={inputId} type="number" inputMode="decimal" min="0.01" step="0.01" value={value} onChange={(event) => setValue(event.target.value)} placeholder="e.g. 100" className="h-10 min-w-0 flex-1 bg-transparent px-2 font-mono text-[var(--text-primary)] outline-none" aria-label="Simulated stake per ticket" aria-describedby={`${inputId}-help`} />
          </span>
        </label>
      </div>
      <p id={`${inputId}-help`} className="mt-3 break-words text-xs leading-5 text-[var(--text-secondary)]">Replays archived prices and corrected outcomes only. Void tickets are refunded; pending tickets are excluded. This is not a recommended stake and is not saved.</p>
      {loading ? <p className="mt-3 text-sm text-[var(--text-secondary)]" aria-live="polite">Loading selected tickets…</p> : invalid ? <p className="mt-3 text-sm font-medium text-[var(--loss)]" role="alert">Enter a positive, finite stake to see the simulation.</p> : simulation && totalStake !== null && totalReturned !== null && profit !== null ? simulation.settledTickets ? <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-5" aria-live="polite"><Metric label="Settled tickets" value={simulation.settledTickets.toLocaleString()} /><Metric label="Total staked" value={money(totalStake, false)} /><Metric label="Total returned" value={money(totalReturned, false)} /><Metric label="P&amp;L" value={money(profit)} tone={profit} /><Metric label="ROI / yield" value={fmtSignedPct(simulation.roi)} tone={simulation.roi ?? 0} /></dl> : <p className="mt-3 text-sm text-[var(--text-secondary)]" aria-live="polite">No settled priced tickets are available to simulate yet.</p> : tickets === null ? <p className="mt-3 text-sm text-[var(--loss)]" role="alert">The selected ticket section could not be loaded.</p> : null}
    </section>
  )
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: { value: string; label: string }[] }) {
  return <label className="grid min-w-0 gap-1 text-sm font-semibold text-[var(--text-secondary)]">{label}<select value={value} onChange={(event) => onChange(event.target.value)} className="h-10 min-w-0 max-w-full rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] px-3 font-normal text-[var(--text-primary)] focus-visible:outline-2 focus-visible:outline-[var(--accent)]">{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
}

function Metric({ label, value, tone = 0 }: { label: string; value: string; tone?: number }) {
  const color = tone > 0 ? "text-[var(--win)]" : tone < 0 ? "text-[var(--loss)]" : "text-[var(--text-primary)]"
  return <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] p-3"><dt className="text-xs text-[var(--text-muted)]">{label}</dt><dd className={`mt-1 font-mono text-base font-semibold ${color}`}>{value}</dd></div>
}
