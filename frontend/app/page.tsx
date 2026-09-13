import type { Metadata } from "next"
import { fetchAccumulators, fetchTodayStatus } from "@/lib/api"
import { fmtDate, fmtDatetime } from "@/lib/format"
import AccumulatorCard from "@/components/AccumulatorCard"

export const metadata: Metadata = { title: "Today" }

const STATUS_STYLES: Record<string, string> = {
  qualified: "status-panel status-qualified",
  no_qualifying_combination: "status-panel status-no-qualifying-combination",
  collecting: "status-panel status-collecting",
  stale: "status-panel status-stale",
  no_upcoming_data: "status-panel status-no-upcoming-data",
}

export default async function DashboardPage() {
  const [today, accPage] = await Promise.all([
    fetchTodayStatus().catch(() => null),
    fetchAccumulators({ limit: 100 }).catch(() => null),
  ])
  const todayAccumulators = today && accPage
    ? accPage.items.filter((acc) => fmtDate(acc.published_at) === fmtDate(`${today.date}T00:00:00+02:00`))
    : []
  const statusClass = STATUS_STYLES[today?.status ?? ""] ?? STATUS_STYLES.collecting

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-4 sm:gap-8 sm:p-8">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent)]">Qwantej / Today</p>
        <h1 className="mt-2 text-2xl font-semibold text-[var(--text-primary)] sm:text-3xl">What is available today?</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-secondary)]">Paper-only ticket availability, data freshness, and the checks behind this run. Historical performance lives on the Performance page.</p>
      </div>

      {!today ? (
        <section className="status-panel status-stale rounded-lg border p-5" aria-live="polite">
          <h2 className="font-semibold text-[var(--status-primary)]">Today&apos;s status is temporarily unavailable</h2>
          <p className="status-secondary mt-2 text-sm leading-6">The dashboard could not read the status service. Check that the API is running, then refresh. No ticket availability is inferred while this check is unavailable.</p>
        </section>
      ) : (
        <>
          <section className={`rounded-lg border p-5 ${statusClass}`} aria-labelledby="today-status-heading">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="status-muted text-xs font-semibold uppercase tracking-wider">{today.date} · Africa/Blantyre</p>
                <h2 id="today-status-heading" className="mt-2 text-xl font-semibold">{today.label}</h2>
                <p className="status-secondary mt-2 text-sm leading-6">{today.detail}</p>
              </div>
              <span className="rounded-full border border-current px-3 py-1 text-xs font-semibold uppercase tracking-wider">{today.status.replaceAll("_", " ")}</span>
            </div>
            <div className="mt-5 grid grid-cols-1 gap-4 border-t border-[var(--status-border)]/50 pt-4 sm:grid-cols-3">
              <div><p className="status-muted text-xs uppercase tracking-wider">Data last checked</p><p className="mt-1 text-sm font-mono">{today.data_freshness_utc ? fmtDatetime(today.data_freshness_utc) : "Not available"}</p></div>
              <div><p className="status-muted text-xs uppercase tracking-wider">Next scheduled run</p><p className="mt-1 text-sm font-mono">{today.next_run_utc ? fmtDatetime(today.next_run_utc) : "Not currently reported"}</p></div>
              <div><p className="status-muted text-xs uppercase tracking-wider">Leagues checked</p><p className="mt-1 text-sm">{today.checked_leagues.length ? today.checked_leagues.join(", ") : "No validated leagues configured"}</p></div>
            </div>
          </section>

          <section aria-label="Today&apos;s paper tickets">
            <div className="mb-4 flex items-end justify-between gap-4">
              <div><h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--text-secondary)]">Today&apos;s paper tickets</h2><p className="mt-1 text-xs text-[var(--text-muted)]">Exact prices and sources are shown on every leg when archived.</p></div>
              <a href="/accumulators" className="text-xs font-medium text-[var(--accent)] hover:underline">View archive</a>
            </div>
            {todayAccumulators.length ? <div className="flex flex-col gap-4">{todayAccumulators.map((acc) => <AccumulatorCard key={acc.id} acc={acc} />)}</div> : <div className="rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg-surface)] p-6 text-sm text-[var(--text-secondary)] shadow-[var(--surface-shadow)]">No ticket is available to display for this date. The status above explains whether the system is still collecting or no combination qualified.</div>}
          </section>
        </>
      )}

      {accPage === null && <p className="text-xs text-[var(--text-muted)]">The ticket archive could not be loaded; availability is still governed by the status check above.</p>}
    </div>
  )
}
