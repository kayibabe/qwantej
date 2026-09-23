"use client"

import { useEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import type { AccumulatorLegOut } from "@/lib/types"
import { fmtDatetime } from "@/lib/format"

type Tab = "Overview" | "Stats" | "Probability" | "H2H" | "Signals" | "Odds"
const TABS: Tab[] = ["Overview", "Stats", "Probability", "H2H", "Signals", "Odds"]

function percent(value: number) {
  return `${(value * 100).toFixed(1)}%`
}

export default function SelectionEvidenceDialog({
  leg,
  ticketStatus,
  daily,
  onClose,
}: {
  leg: AccumulatorLegOut
  ticketStatus: string
  daily: boolean
  onClose: () => void
}) {
  const [tab, setTab] = useState<Tab>("Overview")
  const closeRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"
    closeRef.current?.focus()
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose()
      if (event.key !== "Tab" || !panelRef.current) return
      const focusable = [...panelRef.current.querySelectorAll<HTMLElement>("button:not([disabled]), a[href]")]
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener("keydown", onKeyDown)
    return () => {
      document.removeEventListener("keydown", onKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [onClose])

  const match = leg.home_team && leg.away_team
    ? `${leg.home_team} vs ${leg.away_team}`
    : `Fixture ${leg.fixture_id.slice(0, 8)}`
  const source = leg.bookmaker ?? "Bookmaker not recorded"

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#071626]/65 p-2 sm:p-6" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <div ref={panelRef} role="dialog" aria-modal="true" aria-labelledby={`selection-${leg.id}`} className="max-h-[95vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-5 shadow-2xl sm:p-7">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[var(--accent)]">Selection evidence</p>
            <h2 id={`selection-${leg.id}`} className="mt-2 text-2xl font-semibold leading-tight text-[var(--text-primary)]">{match}</h2>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">{leg.competition_name ?? leg.league_id}{leg.kickoff_utc ? ` · ${fmtDatetime(leg.kickoff_utc)} (Africa/Blantyre)` : ""}</p>
          </div>
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Close selection details" className="shrink-0 rounded-full border border-[var(--border)] px-3 py-2 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-raised)]">✕</button>
        </div>

        <div className="mt-5 flex flex-wrap gap-2 text-xs font-semibold">
          <span className="rounded-full border border-[var(--border)] bg-[var(--bg-raised)] px-3 py-1 text-[var(--text-secondary)]">Ticket {ticketStatus}</span>
          <span className="rounded-full border border-[var(--border)] bg-[var(--bg-raised)] px-3 py-1 text-[var(--text-secondary)]">{daily ? "Daily Pick · not value-qualified" : "Value ticket"}</span>
          {!leg.quote_captured_at && <span className="rounded-full border border-[var(--void)] px-3 py-1 text-[var(--void)]">Price timestamp unavailable</span>}
        </div>

        <div className="mt-5 grid grid-cols-2 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--bg-raised)] sm:grid-cols-3">
          {[
            ["Selection", leg.selection],
            ["Market", leg.market_family],
            ["Snapshot odds", leg.decimal_odds.toFixed(2)],
            [daily ? "Stored estimate" : "Stored model probability", percent(leg.conservative_probability)],
            ["Stored edge", `${leg.edge >= 0 ? "+" : ""}${(leg.edge * 100).toFixed(1)} pp`],
            ["Q-score", leg.qss.toFixed(1)],
          ].map(([label, value]) => (
            <div key={label} className="border-b border-r border-[var(--border)] p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">{label}</p>
              <p className="mt-1 font-semibold text-[var(--text-primary)]">{value}</p>
            </div>
          ))}
        </div>

        <div className="mt-5 flex gap-1 overflow-x-auto border-b border-[var(--border)]" role="tablist" aria-label="Selection details">
          {TABS.map((item) => <button key={item} type="button" role="tab" aria-selected={tab === item} onClick={() => setTab(item)} className={`shrink-0 border-b-2 px-3 py-2 text-sm ${tab === item ? "border-[var(--accent)] font-semibold text-[var(--accent)]" : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]"}`}>{item}</button>)}
        </div>

        <div className="min-h-32 py-5 text-sm leading-6 text-[var(--text-secondary)]" role="tabpanel">
          {tab === "Overview" && <div className="space-y-2"><p><strong className="text-[var(--text-primary)]">Archived selection:</strong> {leg.selection} at {leg.decimal_odds.toFixed(2)} with {source}.</p><p>Match result and leg settlement are not included in this ticket record. The ticket status above applies to the full accumulator.</p></div>}
          {tab === "Stats" && <p>Match statistics are not included in the published ticket archive.</p>}
          {tab === "Probability" && <div className="space-y-2"><p><strong className="text-[var(--text-primary)]">{daily ? "Stored probability estimate" : "Stored conservative model probability"}:</strong> {percent(leg.conservative_probability)}</p><p><strong className="text-[var(--text-primary)]">Price-implied probability:</strong> {percent(1 / leg.decimal_odds)} at the archived snapshot odds.</p><p>These figures describe the published selection; they are not an individual-match guarantee.</p></div>}
          {tab === "H2H" && <p>Head-to-head history is not included in the published ticket archive.</p>}
          {tab === "Signals" && <div className="space-y-2"><p><strong className="text-[var(--text-primary)]">Stored edge:</strong> {leg.edge >= 0 ? "+" : ""}{(leg.edge * 100).toFixed(1)} percentage points.</p><p><strong className="text-[var(--text-primary)]">Q-score:</strong> {leg.qss.toFixed(1)}. This is the archived score, not a new grade or recommendation.</p>{daily && <p>This Daily Pick did not pass through the Value Gate.</p>}</div>}
          {tab === "Odds" && <div className="space-y-2"><p><strong className="text-[var(--text-primary)]">Archived snapshot:</strong> {leg.decimal_odds.toFixed(2)} decimal odds from {source}.</p><p><strong className="text-[var(--text-primary)]">Captured:</strong> {leg.quote_captured_at ? `${fmtDatetime(leg.quote_captured_at)} (Africa/Blantyre)` : "Timestamp not recorded"}.</p><p>Check current bookmaker prices before treating this as an available price.</p></div>}
        </div>
      </div>
    </div>, document.body
  )
}
