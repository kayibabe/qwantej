import type { Metadata } from "next"
import { fetchAccumulators, fetchTodayStatus } from "@/lib/api"
import { addDaysIso, fmtDate, fmtDatetime, fmtIsoDate, isValidIsoDate, todayIsoDate } from "@/lib/format"
import AccumulatorCard from "@/components/AccumulatorCard"
import DateJumpForm from "@/components/DateJumpForm"
import LiveMatchRefresh from "@/components/LiveMatchRefresh"

export const metadata: Metadata = { title: "Today" }

const STATUS_STYLES: Record<string, string> = {
  qualified: "status-panel status-qualified",
  no_qualifying_combination: "status-panel status-no-qualifying-combination",
  collecting: "status-panel status-collecting",
  stale: "status-panel status-stale",
  no_upcoming_data: "status-panel status-no-upcoming-data",
  no_ticket_recorded: "status-panel status-no-upcoming-data",
}

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const sp = await searchParams
  const requestedDate = typeof sp.date === "string" ? sp.date : undefined
  const todayIso = todayIsoDate()
  const selectedDate = requestedDate && isValidIsoDate(requestedDate) ? requestedDate : todayIso
  const isToday = selectedDate === todayIso

  const [today, accPage] = await Promise.all([
    fetchTodayStatus(selectedDate).catch(() => null),
    fetchAccumulators({ limit: 100 }).catch(() => null),
  ])
  const dateAccumulators = accPage
    ? accPage.items.filter((acc) => fmtDate(acc.published_at) === fmtIsoDate(selectedDate))
    : []
  const statusClass = STATUS_STYLES[today?.status ?? ""] ?? STATUS_STYLES.collecting
  const observedLeagueCount = today ? new Set(today.observed_leagues).size : 0

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-4 sm:p-8">
      <LiveMatchRefresh />
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent)]">Qwantej / {isToday ? "Today" : fmtIsoDate(selectedDate)}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[var(--text-primary)] sm:text-4xl">{isToday ? "Today's paper tickets" : `Paper tickets for ${fmtIsoDate(selectedDate)}`}</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-secondary)]">Ticket availability and the data behind it, shown in Africa/Blantyre time.</p>
      </div>

      <nav aria-label="Choose dashboard date" className="flex flex-wrap items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-3 shadow-[var(--surface-shadow)]">
        <a
          href={`?date=${addDaysIso(selectedDate, -1)}`}
          className="rounded px-3 py-1 text-xs font-medium border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-raised)]"
        >
          ← Previous day
        </a>
        <span className="text-sm font-medium text-[var(--text-primary)]">{fmtIsoDate(selectedDate)}</span>
        <a
          href={`?date=${addDaysIso(selectedDate, 1)}`}
          className="rounded px-3 py-1 text-xs font-medium border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-raised)]"
        >
          Next day →
        </a>
        {!isToday && (
          <a
            href="?"
            className="rounded px-3 py-1 text-xs font-medium border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--bg-raised)]"
          >
            Jump to today
          </a>
        )}
        <div className="w-full sm:ml-auto sm:w-auto"><DateJumpForm selectedDate={selectedDate} /></div>
      </nav>

      {!today ? (
        <section className="status-panel status-stale rounded-lg border p-5" aria-live="polite">
          <h2 className="font-semibold text-[var(--status-primary)]">Today&apos;s status is temporarily unavailable</h2>
          <p className="status-secondary mt-2 text-sm leading-6">The dashboard could not read the status service. Check that the API is running, then refresh. No ticket availability is inferred while this check is unavailable.</p>
        </section>
      ) : (
        <>
          <section className={`rounded-xl border p-5 sm:p-6 ${statusClass}`} aria-labelledby="today-status-heading">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="status-muted text-xs font-semibold uppercase tracking-wider">{today.date} · Africa/Blantyre</p>
                <h2 id="today-status-heading" className="mt-2 text-2xl font-semibold tracking-tight">{today.label}</h2>
                <p className="status-secondary mt-2 text-sm leading-6">{today.detail}</p>
              </div>
              <span className="rounded-full border border-current px-3 py-1 text-xs font-semibold uppercase tracking-wider">{today.status.replaceAll("_", " ")}</span>
            </div>
          </section>

          <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-5 shadow-[var(--surface-shadow)] sm:p-6" aria-label="Run details">
            <h2 className="text-base font-semibold text-[var(--text-primary)]">Run details</h2>
            <div className="mt-4 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              <div><p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Latest validated-league price observation</p><p className="mt-1 text-sm text-[var(--text-primary)]">{today.data_freshness_utc ? fmtDatetime(today.data_freshness_utc) : "None recorded for this date"}</p></div>
              <div><p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Next scheduled run</p><p className="mt-1 text-sm text-[var(--text-primary)]">{today.next_run_utc ? fmtDatetime(today.next_run_utc) : "Not currently reported"}</p></div>
              <div><p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Validated leagues configured</p><p className="mt-1 text-sm text-[var(--text-primary)]">{today.checked_leagues.length ? today.checked_leagues.join(", ") : "No validated leagues configured"}</p></div>
            </div>
            <div className="mt-5 border-t border-[var(--border-subtle)] pt-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Research coverage</p>
              <p className="mt-1 text-sm text-[var(--text-primary)]">{today.observed_fixture_count ? `${today.observed_fixture_count} scheduled fixtures observed across ${observedLeagueCount} ${observedLeagueCount === 1 ? "league" : "leagues"}` : "No scheduled fixtures observed"}</p>
              {observedLeagueCount > 0 && <details className="mt-2 text-sm text-[var(--text-secondary)]"><summary className="w-fit cursor-pointer font-medium text-[var(--accent)] hover:underline">View observed leagues</summary><p className="mt-2 max-w-3xl leading-6">{today.observed_leagues.join(", ")}</p></details>}
            </div>
          </section>

          <section aria-label="Paper tickets for this date">
            <div className="mb-4 flex items-end justify-between gap-4">
              <div><h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--text-secondary)]">{isToday ? "Today's" : fmtIsoDate(selectedDate)} paper tickets</h2><p className="mt-1 text-xs text-[var(--text-muted)]">Exact prices and sources are shown on every leg when archived.</p></div>
              <a href="/accumulators" className="text-xs font-medium text-[var(--accent)] hover:underline">View archive</a>
            </div>
            {dateAccumulators.length ? <div className="flex flex-col gap-4">{dateAccumulators.map((acc) => <AccumulatorCard key={acc.id} acc={acc} />)}</div> : <div className="rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg-surface)] p-6 text-sm text-[var(--text-secondary)] shadow-[var(--surface-shadow)]">No ticket is available to display for this date. The status above explains whether the system is still collecting or no combination qualified.</div>}
          </section>
        </>
      )}

      {accPage === null && <p className="text-xs text-[var(--text-muted)]">The ticket archive could not be loaded; availability is still governed by the status check above.</p>}
    </div>
  )
}
