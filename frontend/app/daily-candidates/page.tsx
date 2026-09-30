import type { Metadata } from "next"
import Link from "next/link"
import { fetchDailyCandidates } from "@/lib/api"
import { addDaysIso, fmtDatetime, fmtIsoDate, isValidIsoDate, todayIsoDate } from "@/lib/format"

export const metadata: Metadata = { title: "Daily candidates" }

function pct(value: number) { return `${(value * 100).toFixed(1)}%` }

export default async function DailyCandidatesPage({
  searchParams,
}: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams
  const today = todayIsoDate()
  const requested = typeof sp.date === "string" ? sp.date : today
  const date = isValidIsoDate(requested) ? requested : today
  const page = await fetchDailyCandidates(date).catch(() => null)

  return <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 p-4 sm:p-8">
    <div>
      <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Daily candidate pool</h1>
      <p className="mt-1 max-w-4xl text-sm leading-6 text-[var(--text-secondary)]">The latest Daily Pick build snapshot for {fmtIsoDate(date)}. Selected candidates are linked to their ticket; the rest were considered but not used. Results update from the stored fixture and settlement records.</p>
    </div>
    <nav className="flex flex-wrap items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-3" aria-label="Choose candidate date">
      <Link href={`?date=${addDaysIso(date, -1)}`} className="rounded border border-[var(--border)] px-3 py-1 text-xs text-[var(--text-secondary)]">← Previous day</Link>
      <span className="text-sm font-medium text-[var(--text-primary)]">{fmtIsoDate(date)}</span>
      <Link href={`?date=${addDaysIso(date, 1)}`} className="rounded border border-[var(--border)] px-3 py-1 text-xs text-[var(--text-secondary)]">Next day →</Link>
      {date !== today && <Link href="/daily-candidates" className="rounded border border-[var(--accent)] px-3 py-1 text-xs text-[var(--accent)]">Today</Link>}
    </nav>
    {!page ? <p className="rounded-lg border border-[var(--loss)] p-5 text-sm text-[var(--loss)]">Candidate snapshot unavailable.</p>
      : !page.items.length ? <p className="rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg-surface)] p-6 text-sm text-[var(--text-secondary)]">No Daily Pick candidate snapshot was recorded for this date.</p>
      : <section className="overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] shadow-[var(--surface-shadow)]">
        <table className="w-full text-sm">
          <caption className="sr-only">Daily Pick candidate pool and outcomes</caption>
          <thead className="border-b border-[var(--border)] text-left text-[10px] uppercase tracking-wider text-[var(--text-muted)]"><tr>
            <th className="px-4 py-3">Match</th><th className="px-4 py-3">Pick</th><th className="px-4 py-3">Pool decision</th><th className="px-4 py-3">Price / quality</th><th className="px-4 py-3">Result</th>
          </tr></thead>
          <tbody>{page.items.map((item) => <tr key={item.id} className="border-b border-[var(--border-subtle)] align-top last:border-0">
            <td className="px-4 py-3"><div className="font-medium text-[var(--text-primary)]">{item.home_team ?? item.fixture_id} v {item.away_team ?? "—"}</div><div className="mt-1 text-xs text-[var(--text-muted)]">{item.competition_name ?? "Competition unavailable"} · {fmtDatetime(item.kickoff_utc)}</div></td>
            <td className="px-4 py-3"><div className="font-medium text-[var(--text-primary)]">{item.market} · {item.selection}</div><div className="mt-1 text-xs text-[var(--text-secondary)]">Model {pct(item.model_probability)} · Market {pct(item.market_probability)}</div></td>
            <td className="px-4 py-3"><span className={`rounded border px-2 py-1 text-xs font-semibold ${item.candidate_status === "selected" ? "border-[var(--win)]/40 text-[var(--win)]" : "border-[var(--border)] text-[var(--text-secondary)]"}`}>{item.candidate_status === "selected" ? `Selected · ${item.selected_product?.replace("daily_", "Daily ")}` : "Considered · not selected"}</span>{item.exclusion_reason && <div className="mt-2 max-w-48 text-xs text-[var(--text-muted)]">{item.exclusion_reason.replaceAll("_", " ")}</div>}</td>
            <td className="px-4 py-3"><div className="font-mono text-[var(--text-primary)]">{item.decimal_odds.toFixed(2)}</div><div className="mt-1 text-xs text-[var(--text-secondary)]">DQS {item.dqs.toFixed(1)} · {item.bookmaker ?? "bookmaker n/a"}</div></td>
            <td className="px-4 py-3"><div className="font-semibold text-[var(--text-primary)]">{item.score ?? "Pending"}</div><div className="mt-1 text-xs text-[var(--text-secondary)]">{item.outcome ?? item.fixture_status}</div>{item.accumulator_id && <Link href={`/accumulators/${item.accumulator_id}`} className="mt-1 inline-block text-xs text-[var(--accent)] hover:underline">Open ticket</Link>}</td>
          </tr>)}</tbody>
        </table>
      </section>}
  </div>
}
