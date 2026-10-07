import type { Metadata } from "next"
import { fetchAccumulators, fetchBankroll, fetchDailyCandidates, fetchTodayStatus } from "@/lib/api"
import { addDaysIso, fmtDatetime, fmtIsoDate, isValidIsoDate, todayIsoDate } from "@/lib/format"
import AccumulatorCard from "@/components/AccumulatorCard"
import DateJumpForm from "@/components/DateJumpForm"
import LiveMatchRefresh from "@/components/LiveMatchRefresh"
import { ticketArchiveHref } from "@/lib/tickets"

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

  const [today, accPage, candidates, bankroll] = await Promise.all([
    fetchTodayStatus(selectedDate).catch(() => null),
    fetchAccumulators({ date: selectedDate, limit: 100 }).catch(() => null),
    fetchDailyCandidates(selectedDate).catch(() => null),
    fetchBankroll().catch(() => null),
  ])
  const dateAccumulators = accPage?.items ?? []
  const candidateItems = candidates?.items ?? []
  const selectedCandidates = candidateItems.filter((item) => item.candidate_status === "selected")
  const watchCandidates = candidateItems.filter((item) => item.candidate_status === "watch")
  const notSelectedCandidates = candidateItems.filter((item) => item.candidate_status === "not_selected")
  const reviewCandidates = candidateItems.filter((item) => !["selected", "watch", "not_selected"].includes(item.candidate_status))
  const statusClass = STATUS_STYLES[today?.status ?? ""] ?? STATUS_STYLES.collecting
  const observedLeagueCount = today ? new Set(today.observed_leagues).size : 0

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-4 sm:p-8">
      <LiveMatchRefresh />
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent)]">Qwantej / {isToday ? "Today" : fmtIsoDate(selectedDate)}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[var(--text-primary)] sm:text-4xl">{isToday ? "Today's betting intelligence" : `Betting intelligence for ${fmtIsoDate(selectedDate)}`}</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-secondary)]">Actionable opportunities first, followed by the archived evidence behind them. All times are shown in Africa/Blantyre time.</p>
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

          <section aria-labelledby="decision-summary-heading">
            <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 id="decision-summary-heading" className="text-sm font-semibold uppercase tracking-wider text-[var(--text-secondary)]">Decision summary</h2>
                <p className="mt-1 text-xs text-[var(--text-muted)]">BET is reserved for the stored Daily Pick selection. WATCH means a candidate passed upstream gates but was outside the ticket target band.</p>
              </div>
              <a href={`/daily-candidates?date=${selectedDate}`} className="text-xs font-medium text-[var(--accent)] hover:underline">Inspect full candidate pool</a>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <DecisionTile label="Candidates reviewed" value={candidateItems.length} detail={candidates?.run_id ? "Latest recorded run" : "No snapshot recorded"} />
              <DecisionTile label="BET" value={selectedCandidates.length} detail="Selected for a Daily Pick product" tone="bet" />
              <DecisionTile label="WATCH" value={watchCandidates.length} detail="Passed gates, outside target band" tone="review" />
              <DecisionTile label="NOT SELECTED" value={notSelectedCandidates.length} detail="Excluded from the stored target-band build" tone="pass" />
              {reviewCandidates.length > 0 && <DecisionTile label="REVIEW" value={reviewCandidates.length} detail="Unknown source status; no decision inferred" tone="review" />}
            </div>
          </section>

          <section aria-labelledby="opportunities-heading">
            <div className="mb-4 flex items-end justify-between gap-4">
              <div><h2 id="opportunities-heading" className="text-sm font-semibold uppercase tracking-wider text-[var(--text-secondary)]">Today&apos;s opportunities</h2><p className="mt-1 text-xs text-[var(--text-muted)]">The decision is separated from confidence and data quality so the user can see both the action and its evidence.</p></div>
            </div>
            {!candidates ? <div className="rounded-lg border border-[var(--loss)] p-5 text-sm text-[var(--loss)]">The candidate snapshot could not be loaded. No decision is inferred from the unavailable data.</div>
              : !candidateItems.length ? <div className="rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg-surface)] p-6 text-sm text-[var(--text-secondary)]">No candidate snapshot was recorded for this date. This is not evidence that a bet was rejected.</div>
              : <div className="overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] shadow-[var(--surface-shadow)]">
                <table className="w-full min-w-[760px] text-sm">
                  <caption className="sr-only">Today&apos;s candidate decisions and evidence</caption>
                  <thead className="border-b border-[var(--border)] text-left text-[10px] uppercase tracking-wider text-[var(--text-muted)]"><tr>
                    <th className="px-4 py-3">Match</th><th className="px-4 py-3">Selection</th><th className="px-4 py-3 text-right">Model / market</th><th className="px-4 py-3 text-right">Odds</th><th className="px-4 py-3 text-right">DQS</th><th className="px-4 py-3">Decision</th>
                  </tr></thead>
                  <tbody>{candidateItems.map((item) => {
                    const selected = item.candidate_status === "selected"
                    const watch = item.candidate_status === "watch"
                    const notSelected = item.candidate_status === "not_selected"
                    const edge = item.model_probability - item.market_probability
                    return <tr key={item.id} className="border-b border-[var(--border-subtle)] align-top last:border-0">
                      <td className="px-4 py-3"><a href={`/matches/${item.prediction_id}`} className="font-medium text-[var(--accent)] hover:underline">{item.home_team ?? item.fixture_id} v {item.away_team ?? "—"}</a><div className="mt-1 text-xs text-[var(--text-muted)]">{item.competition_name ?? "Competition unavailable"} · {fmtDatetime(item.kickoff_utc)}</div></td>
                      <td className="px-4 py-3"><div className="font-medium text-[var(--text-primary)]">{item.market} · {item.selection}</div><div className="mt-1 text-xs text-[var(--text-secondary)]">{item.bookmaker ?? "Bookmaker unavailable"}</div></td>
                      <td className="px-4 py-3 text-right font-mono text-xs text-[var(--text-primary)]"><div>{(item.model_probability * 100).toFixed(1)}% / {(item.market_probability * 100).toFixed(1)}%</div><div className={edge >= 0 ? "mt-1 text-[var(--win)]" : "mt-1 text-[var(--loss)]"}>{edge >= 0 ? "+" : ""}{(edge * 100).toFixed(1)} pp</div></td>
                      <td className="px-4 py-3 text-right font-mono text-[var(--text-primary)]">{item.decimal_odds.toFixed(2)}</td>
                      <td className="px-4 py-3 text-right font-mono text-[var(--text-primary)]">{item.dqs.toFixed(1)}</td>
                      <td className="px-4 py-3"><span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${selected ? "border-[var(--win)]/40 bg-[var(--win)]/10 text-[var(--win)]" : watch ? "border-[var(--void)]/40 text-[var(--void)]" : notSelected ? "border-[var(--border)] text-[var(--text-secondary)]" : "border-[var(--loss)]/40 text-[var(--loss)]"}`}>{selected ? "BET" : watch ? "WATCH" : notSelected ? "NOT SELECTED" : "REVIEW"}</span>{!selected && item.exclusion_reason && <div className="mt-2 max-w-52 text-xs leading-5 text-[var(--text-muted)]">{item.exclusion_reason.replaceAll("_", " ")}</div>}{selected && item.accumulator_id && <a href={`/accumulators/${item.accumulator_id}`} className="mt-2 block text-xs text-[var(--accent)] hover:underline">Open published ticket</a>}</td>
                    </tr>
                  })}</tbody>
                </table>
              </div>}
          </section>

          {bankroll && <section aria-labelledby="exposure-heading"><div className="mb-4"><h2 id="exposure-heading" className="text-sm font-semibold uppercase tracking-wider text-[var(--text-secondary)]">Bankroll and exposure</h2><p className="mt-1 text-xs text-[var(--text-muted)]">Real-money account values are shown only when recorded by the bankroll ledger.</p></div><div className="grid gap-3 sm:grid-cols-4"><RiskTile label="Balance" value={`${bankroll.currency} ${Number(bankroll.balance).toLocaleString("en-GB", { maximumFractionDigits: 2 })}`} /><RiskTile label="Available" value={`${bankroll.currency} ${Number(bankroll.available).toLocaleString("en-GB", { maximumFractionDigits: 2 })}`} /><RiskTile label="Open exposure" value={`${bankroll.currency} ${Number(bankroll.open_exposure).toLocaleString("en-GB", { maximumFractionDigits: 2 })}`} tone={Number(bankroll.open_exposure) > 0 ? "risk" : undefined} /><RiskTile label="Open bets" value={String(bankroll.open_bets)} /></div></section>}

          <section aria-label="Tickets for this date">
            <div className="mb-4 flex items-end justify-between gap-4">
              <div><h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--text-secondary)]">Published tickets</h2><p className="mt-1 text-xs text-[var(--text-muted)]">Exact prices and sources are shown on every leg when archived.</p></div>
              <a href={ticketArchiveHref("day", selectedDate)} className="text-xs font-medium text-[var(--accent)] hover:underline">Open in ticket archive</a>
            </div>
            {dateAccumulators.length ? <div className="flex flex-col gap-4">{dateAccumulators.map((acc) => <AccumulatorCard key={acc.id} acc={acc} />)}</div> : <div className="rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg-surface)] p-6 text-sm text-[var(--text-secondary)] shadow-[var(--surface-shadow)]">No ticket is available to display for this date. The status above explains whether the system is still collecting or no combination qualified.</div>}
          </section>

          <details className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] shadow-[var(--surface-shadow)]">
            <summary className="cursor-pointer list-none p-5 text-base font-semibold text-[var(--text-primary)] focus-visible:outline-2 focus-visible:outline-[var(--accent)] sm:p-6">System details <span className="ml-2 text-xs font-normal text-[var(--text-muted)]">Freshness, schedule and research coverage</span></summary>
            <section className="border-t border-[var(--border-subtle)] p-5 sm:p-6" aria-label="Data freshness and run details">
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
          </details>
        </>
      )}

      {accPage === null && <p className="text-xs text-[var(--text-muted)]">The ticket archive could not be loaded; availability is still governed by the status check above.</p>}
    </div>
  )
}

function DecisionTile({ label, value, detail, tone }: { label: string; value: number; detail: string; tone?: "bet" | "pass" | "review" }) {
  const valueClass = tone === "bet" ? "text-[var(--win)]" : tone === "review" ? "text-[var(--void)]" : tone === "pass" ? "text-[var(--text-secondary)]" : "text-[var(--text-primary)]"
  return <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-4 shadow-[var(--surface-shadow)]"><p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">{label}</p><p className={`mt-2 text-2xl font-semibold ${valueClass}`}>{value}</p><p className="mt-1 text-xs text-[var(--text-muted)]">{detail}</p></div>
}

function RiskTile({ label, value, tone }: { label: string; value: string; tone?: "risk" }) {
  return <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-4 shadow-[var(--surface-shadow)]"><p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">{label}</p><p className={`mt-2 text-xl font-semibold ${tone === "risk" ? "text-[var(--void)]" : "text-[var(--text-primary)]"}`}>{value}</p></div>
}
