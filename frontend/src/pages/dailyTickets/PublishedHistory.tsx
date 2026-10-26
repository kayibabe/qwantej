import { useEffect, useMemo, useState } from "react";
import { fetchTicketHistory, formatDate, formatTicketType, type TicketHistoryItem } from "../../lib/api";
import { fmtPnl } from "../../utils/currency";
import { localDateString } from "./helpers";

const PUBLIC_TICKET_TIERS = [
  { key: "safe", label: "Conservative" },
  { key: "balanced", label: "Balanced" },
] as const;

function latestCohorts(rows: TicketHistoryItem[]): TicketHistoryItem[] {
  const latest = new Map<string, TicketHistoryItem>();
  for (const row of rows) {
    if (row.ticket_type === "best_value" || row.ticket_type === "high_odds" || row.internal_only) continue;
    const key = `${row.target_date}:${row.ticket_type}`;
    const current = latest.get(key);
    if (!current || row.version > current.version || (row.version === current.version && row.ticket_id > current.ticket_id)) {
      latest.set(key, row);
    }
  }
  const tierOrder = new Map<string, number>(PUBLIC_TICKET_TIERS.map((tier, index) => [tier.key, index]));
  return [...latest.values()].sort((a, b) => b.target_date.localeCompare(a.target_date) || (tierOrder.get(a.ticket_type) ?? 99) - (tierOrder.get(b.ticket_type) ?? 99));
}

interface HistoryDateGroup {
  date: string;
  rows: TicketHistoryItem[];
}

interface HistoryMonthGroup {
  key: string;
  label: string;
  dates: HistoryDateGroup[];
}

interface HistoryYearGroup {
  year: string;
  months: HistoryMonthGroup[];
}

function groupHistoryRows(rows: TicketHistoryItem[]): HistoryYearGroup[] {
  const years = new Map<string, Map<string, Map<string, TicketHistoryItem[]>>>();
  for (const row of rows) {
    const year = row.target_date.slice(0, 4);
    const month = row.target_date.slice(5, 7);
    let months = years.get(year);
    if (!months) years.set(year, (months = new Map()));
    let dates = months.get(month);
    if (!dates) months.set(month, (dates = new Map()));
    const dateRows = dates.get(row.target_date) ?? [];
    dateRows.push(row);
    dates.set(row.target_date, dateRows);
  }

  return [...years].map(([year, months]) => ({
    year,
    months: [...months].map(([month, dates]) => ({
      key: `${year}-${month}`,
      label: new Date(Number(year), Number(month) - 1, 1).toLocaleDateString(undefined, { month: "long" }),
      dates: [...dates].map(([date, dateRows]) => ({ date, rows: dateRows })),
    })),
  }));
}

function PublishedTicketRow({ row }: { row: TicketHistoryItem }) {
  return <article className="paper-ledger-row published-history-row">
    <div className="paper-ticket-summary published-history-summary">
      <div className="paper-ticket-identity"><span className={`portfolio-tier ${row.ticket_type}`}>{formatTicketType(row.ticket_type)}</span><small>v{row.version} · model {row.model_version} · {row.pricing === "market" ? "market-priced" : "model-priced"}</small></div>
      <div><span>Date</span><strong>{formatDate(row.target_date)}</strong></div>
      <div><span>Legs</span><strong>{row.leg_count}</strong></div>
      <div><span>Odds</span><strong>{row.combined_odds == null ? "—" : `${row.combined_odds.toFixed(2)}×`}</strong></div>
      <div><span>Result</span><strong className={`settlement-pill ${row.result ?? "pending"}`}>{row.result ?? "pending"}</strong></div>
      <div><span>Paper P&amp;L</span><strong className={row.profit_loss == null ? "" : row.profit_loss >= 0 ? "positive" : "negative"}>{row.profit_loss == null ? "—" : `${row.profit_loss >= 0 ? "+" : ""}${row.profit_loss.toFixed(2)}`}</strong></div>
    </div>
    <details className="published-history-details"><summary>Publication details · {row.publication_timing === "pre_kickoff" ? "before kickoff" : row.publication_timing === "post_kickoff" ? "after kickoff" : "timing unknown"}</summary><p>Published {new Date(row.published_at).toLocaleString()} · {row.relaxed_tier ? "bounded relaxation applied" : "full-strength tier"} · hash {row.publication_hash}</p></details>
  </article>;
}

export default function PublishedHistory() {
  const [rows, setRows] = useState<TicketHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const today = localDateString();

  useEffect(() => {
    let active = true;
    fetchTicketHistory(true, false)
      .then((history) => { if (active) setRows(latestCohorts(history)); })
      .catch((cause: Error) => { if (active) setError(cause.message || "Published history is unavailable."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const settled = useMemo(() => rows.filter((row) => row.result === "won" || row.result === "lost" || row.result === "void"), [rows]);
  const summary = useMemo(() => {
    const pnl = settled.reduce((sum, row) => sum + (row.profit_loss ?? 0), 0);
    const wins = settled.filter((row) => row.result === "won").length;
    const losses = settled.filter((row) => row.result === "lost").length;
    const settledStake = settled.reduce((sum, row) => sum + (row.stake ?? 0), 0);
    const hitRate = wins + losses > 0 ? wins / (wins + losses) : null;
    const roi = settled.length > 0 && settled.every((row) => row.stake != null) && settledStake > 0
      ? pnl / settledStake
      : null;
    const preKickoff = rows.filter((row) => row.publication_timing === "pre_kickoff").length;
    return { pnl, wins, losses, hitRate, roi, preKickoff };
  }, [rows, settled]);
  const tierSummaries = useMemo(() => PUBLIC_TICKET_TIERS.map((tier) => {
    const cohorts = rows.filter((row) => row.ticket_type === tier.key);
    const tierSettled = cohorts.filter((row) => row.result === "won" || row.result === "lost" || row.result === "void");
    const wins = tierSettled.filter((row) => row.result === "won").length;
    const losses = tierSettled.filter((row) => row.result === "lost").length;
    const pnl = tierSettled.reduce((sum, row) => sum + (row.profit_loss ?? 0), 0);
    const settledStake = tierSettled.reduce((sum, row) => sum + (row.stake ?? 0), 0);
    const hitRate = wins + losses > 0 ? wins / (wins + losses) : null;
    const roi = tierSettled.length > 0 && tierSettled.every((row) => row.stake != null) && settledStake > 0
      ? pnl / settledStake
      : null;
    return {
      ...tier,
      cohorts: cohorts.length,
      awaiting: cohorts.length - tierSettled.length,
      settled: tierSettled.length,
      wins,
      losses,
      hitRate,
      pnl,
      roi,
      preKickoff: cohorts.filter((row) => row.publication_timing === "pre_kickoff").length,
    };
  }), [rows]);
  const groupedRows = useMemo(() => groupHistoryRows(rows), [rows]);
  const hasToday = rows.some((row) => row.target_date === today);

  if (loading) return <section className="publication-diagnostics" role="status">Loading published paper history…</section>;
  if (error) return <section className="publication-diagnostics" role="alert"><h2>Published history unavailable</h2><p>{error}</p></section>;

  return <section className="published-history" aria-labelledby="published-history-title">
    <header className="view-intro published-history-intro">
      <span className="eyebrow">Published record</span>
      <h2 id="published-history-title" className="section-title">Ticket history</h2>
      <p>Latest published version for each active tier. These are system paper results, not a record of bets placed in your bookmaker account.</p>
    </header>
    <div className="paper-ledger-summary published-history-kpis" aria-label="Published paper history summary">
      <div><span>Latest ticket cohorts (after current filters)</span><strong>{rows.length}</strong></div>
      <div><span>Settled (win, lost, or void)</span><strong>{settled.length}</strong></div>
      <div><span>Hit rate (wins / decided tickets)</span><strong>{summary.hitRate == null ? "—" : `${(summary.hitRate * 100).toFixed(1)}%`}</strong></div>
      <div><span>Paper P&amp;L (latest settled cohorts only)</span><strong className={summary.pnl >= 0 ? "positive" : "negative"}>{fmtPnl(summary.pnl)}</strong></div>
      <div><span>ROI (paper P&amp;L / settled stake)</span><strong className={summary.roi == null || summary.roi >= 0 ? "positive" : "negative"}>{summary.roi == null ? "—" : `${summary.roi >= 0 ? "+" : ""}${(summary.roi * 100).toFixed(2)}%`}</strong></div>
      <div><span>Published before kickoff (unknown timing is not counted)</span><strong>{summary.preKickoff}</strong></div>
    </div>
    <section className="published-tier-performance" aria-labelledby="published-tier-performance-title">
      <h3 id="published-tier-performance-title">Performance by ticket tier</h3>
      <div className="analytics-table-wrap published-tier-matrix-wrap">
        <table className="analytics-table published-tier-matrix">
          <colgroup><col className="tier-column" /><col className="cohort-column" /><col className="awaiting-column" /><col className="settled-column" /><col className="won-column" /><col className="lost-column" /><col className="hit-rate-column" /><col className="pnl-column" /><col className="roi-column" /><col className="kickoff-column" /></colgroup>
          <thead><tr><th scope="col">Ticket tier</th><th scope="col">Latest cohorts</th><th scope="col">Awaiting</th><th scope="col">Settled</th><th scope="col">Won</th><th scope="col">Lost</th><th scope="col">Hit rate</th><th scope="col">Paper P&amp;L</th><th scope="col">ROI</th><th scope="col">Before kickoff</th></tr></thead>
          <tbody>
            {tierSummaries.map((tier) => <tr key={tier.key} className={`published-tier-row ${tier.key}`}>
              <th scope="row">{tier.label}</th>
              <td>{tier.cohorts}</td>
              <td>{tier.awaiting}</td>
              <td>{tier.settled}</td>
              <td>{tier.wins}</td>
              <td>{tier.losses}</td>
              <td>{tier.hitRate == null ? "—" : `${(tier.hitRate * 100).toFixed(1)}%`}</td>
              <td className={tier.pnl >= 0 ? "positive" : "negative"}>{tier.settled === 0 ? "—" : `${tier.pnl >= 0 ? "+" : ""}${tier.pnl.toFixed(2)}`}</td>
              <td className={tier.roi == null || tier.roi >= 0 ? "positive" : "negative"}>{tier.roi == null ? "—" : `${tier.roi >= 0 ? "+" : ""}${(tier.roi * 100).toFixed(2)}%`}</td>
              <td>{tier.preKickoff}</td>
            </tr>)}
          </tbody>
        </table>
      </div>
    </section>
    {rows.length === 0 ? <p className="panel-empty">No published ticket history is available yet.</p> : <div className="paper-ledger-list published-history-periods">
      {groupedRows.map((yearGroup) => <details className="paper-year-group published-history-year" key={yearGroup.year} open={hasToday && yearGroup.year === today.slice(0, 4)}>
        <summary className="paper-year-heading">{yearGroup.year}</summary>
        <div className="paper-year-body">{yearGroup.months.map((monthGroup) => <details className="paper-month-group published-history-month" key={monthGroup.key} open={hasToday && monthGroup.key === today.slice(0, 7)}>
          <summary className="paper-month-heading">{monthGroup.label}</summary>
          <div className="paper-month-body">{monthGroup.dates.map((dateGroup) => <details className="published-history-date-group" key={dateGroup.date} open={hasToday && dateGroup.date === today}>
            <summary className="paper-date-heading"><strong>{formatDate(dateGroup.date)}</strong><span className="published-date-cohort-count">{dateGroup.rows.length} ticket {dateGroup.rows.length === 1 ? "cohort" : "cohorts"}</span><span className="published-date-result-summary" aria-label={`Ticket outcomes for ${formatDate(dateGroup.date)}`}>{PUBLIC_TICKET_TIERS.map((tier) => {
              const row = dateGroup.rows.find((ticket) => ticket.ticket_type === tier.key);
              return <span className="published-date-ticket-slot" key={tier.key}>{row && <span className="published-date-ticket-outcome"><span className={`portfolio-tier ${row.ticket_type}`}>{formatTicketType(row.ticket_type)}</span><span className={`settlement-pill ${row.result ?? "pending"}`}>{row.result ?? "pending"}</span></span>}</span>;
            })}</span></summary>
            <div className="published-history-date-body">{dateGroup.rows.map((row) => <PublishedTicketRow key={row.ticket_id} row={row} />)}</div>
          </details>)}</div>
        </details>)}</div>
      </details>)}
    </div>}
    {rows.length >= 200 && <p className="published-history-limit">Showing the latest 200 stored ticket versions. Older history is not included in this view.</p>}
  </section>;
}
