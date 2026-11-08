import { useEffect, useState } from "react";
import type { SelectionSummary } from "../../lib/api";
import {
  formatKickoff,
  formatMarket,
  selectionRepeatsMarket,
  formatSelection,
} from "../../lib/api";
import {
  gradeTone,
  matchDisplayState,
  matchStatusText,
  selectionStatusLabel,
  spreadLabel,
  spreadTone,
} from "./helpers";
import type { MatchDisplayState } from "./types";

type MatchSortKey = "match" | "kickoff" | "league" | "q" | "markets" | "spread" | "edge";
const MATCH_STATUSES: MatchDisplayState[] = ["finished", "live", "scheduled", "postponed", "cancelled", "abandoned", "awarded"];
const MATCH_SORT_KEYS: MatchSortKey[] = ["match", "kickoff", "league", "q", "markets", "spread", "edge"];

function matchUrlParam(name: string) {
  return new URLSearchParams(window.location.search).get(`match_${name}`);
}

function quoteFreshness(row: SelectionSummary) {
  if (!row.source_odds_at) return { label: "Quote time unavailable", state: "unknown" };
  const capturedAt = Date.parse(row.source_odds_at);
  const kickoffAt = Date.parse(row.kickoff_at);
  if (!Number.isFinite(capturedAt)) return { label: "Quote time invalid", state: "unknown" };
  if (Number.isFinite(kickoffAt) && capturedAt >= kickoffAt) return { label: "After kickoff", state: "blocked" };
  const ageHours = (Date.now() - capturedAt) / 3_600_000;
  if (ageHours < 0) return { label: "Future timestamp", state: "unknown" };
  if (ageHours <= 2) return { label: "Fresh", state: "fresh" };
  if (ageHours <= 8) return { label: "Aging", state: "aging" };
  return { label: "Historical", state: "stale" };
}

function percent(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? "Unavailable" : `${(value * 100).toFixed(1)}%`;
}

function quoteTime(value: string | null | undefined) {
  if (!value) return "Time unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Time unavailable" : date.toLocaleString();
}

export function AllMatches({
  rows,
  totalSelections = rows.reduce((sum, [, selections]) => sum + selections.length, 0),
  loadedSelections = totalSelections,
  loadingMore = false,
  onLoadMore,
  onSelect,
}: {
  rows: [number, SelectionSummary[]][];
  totalSelections?: number;
  loadedSelections?: number;
  loadingMore?: boolean;
  onLoadMore?: () => void;
  onSelect: (row: SelectionSummary) => void;
}) {
  const [statusFilter, setStatusFilter] = useState<"all" | MatchDisplayState>(() => {
    const value = matchUrlParam("status");
    return value && MATCH_STATUSES.includes(value as MatchDisplayState) ? value as MatchDisplayState : "all";
  });
  const [query, setQuery] = useState(() => matchUrlParam("q") ?? "");
  const [leagueFilter, setLeagueFilter] = useState(() => matchUrlParam("league") ?? "all");
  const [marketFilter, setMarketFilter] = useState(() => matchUrlParam("market") ?? "all");
  const [sort, setSort] = useState<{ key: MatchSortKey; direction: "asc" | "desc" }>(() => {
    const key = matchUrlParam("sort");
    const direction = matchUrlParam("order");
    return {
      key: key && MATCH_SORT_KEYS.includes(key as MatchSortKey) ? key as MatchSortKey : "kickoff",
      direction: direction === "desc" ? "desc" : "asc",
    };
  });
  useEffect(() => {
    const url = new URL(window.location.href);
    const params: Record<string, string | null> = {
      match_q: query.trim() || null,
      match_league: leagueFilter === "all" ? null : leagueFilter,
      match_market: marketFilter === "all" ? null : marketFilter,
      match_status: statusFilter === "all" ? null : statusFilter,
      match_sort: sort.key === "kickoff" && sort.direction === "asc" ? null : sort.key,
      match_order: sort.key === "kickoff" && sort.direction === "asc" ? null : sort.direction,
    };
    for (const [key, value] of Object.entries(params)) {
      if (value) url.searchParams.set(key, value);
      else url.searchParams.delete(key);
    }
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  }, [query, leagueFilter, marketFilter, statusFilter, sort]);
  const leagues = [...new Set(rows.map(([, selections]) => selections[0]?.competition).filter(Boolean))].sort();
  const markets = [...new Set(rows.flatMap(([, selections]) => selections.map((row) => formatMarket(row.market))))].sort();
  const marketCounts = rows.reduce<Record<string, number>>((counts, [, selections]) => {
    for (const market of new Set(selections.map((row) => formatMarket(row.market)))) {
      counts[market] = (counts[market] ?? 0) + 1;
    }
    return counts;
  }, {});
  const quickMarkets = Object.entries(marketCounts)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 4)
    .map(([market]) => market);
  const queryText = query.trim().toLocaleLowerCase();
  const discoveredRows = rows.flatMap(([id, selections]) => {
    const first = selections[0];
    const matchesText = !queryText || `${first.home_team} ${first.away_team} ${first.competition}`.toLocaleLowerCase().includes(queryText);
    const marketRows = marketFilter === "all" ? selections : selections.filter((row) => formatMarket(row.market) === marketFilter);
    if (!matchesText || (leagueFilter !== "all" && first.competition !== leagueFilter) || marketRows.length === 0) return [];
    return [[id, marketRows] as [number, SelectionSummary[]]];
  });
  const filteredRows = statusFilter === "all"
    ? discoveredRows
    : discoveredRows.filter(([, selections]) => matchDisplayState(selections[0]) === statusFilter);
  const activeFilterCount = Number(Boolean(query.trim()))
    + Number(leagueFilter !== "all")
    + Number(marketFilter !== "all")
    + Number(statusFilter !== "all");
  const sortedRows = [...filteredRows].sort(([, a], [, b]) => {
    const left = a[0];
    const right = b[0];
    const values: Record<typeof sort.key, [string | number, string | number]> =
      {
        match: [
          `${left.home_team} ${left.away_team}`,
          `${right.home_team} ${right.away_team}`,
        ],
        kickoff: [left.kickoff_at, right.kickoff_at],
        league: [left.competition, right.competition],
        q: [
          Math.max(...a.map((row) => row.q_score)),
          Math.max(...b.map((row) => row.q_score)),
        ],
        markets: [a.length, b.length],
        spread: [a[0].model_agreement ?? 999, b[0].model_agreement ?? 999],
        edge: [Math.max(...a.map((row) => row.edge ?? -999)), Math.max(...b.map((row) => row.edge ?? -999))],
      };
    const [first, second] = values[sort.key];
    const result = first < second ? -1 : first > second ? 1 : 0;
    return sort.direction === "asc" ? result : -result;
  });
  const filteredResults = filteredRows.flatMap(([matchId, selections]) =>
    selections
      .filter((row) => row.result === "won" || row.result === "lost" || row.result === "void")
      .map((row) => ({ matchId, result: row.result as "won" | "lost" | "void", odds: row.best_odds })),
  );
  const filteredResultCounts = filteredResults.reduce(
    (counts, row) => {
      counts[row.result] += 1;
      counts.matches.add(row.matchId);
      if (row.result !== "void" && row.odds != null && Number.isFinite(row.odds) && row.odds > 1) {
        counts.priced += 1;
        counts.netUnits += row.result === "won" ? row.odds - 1 : -1;
      }
      return counts;
    },
    { won: 0, lost: 0, void: 0, priced: 0, netUnits: 0, matches: new Set<number>() },
  );
  const decidedCount = filteredResultCounts.won + filteredResultCounts.lost;
  const changeSort = (key: MatchSortKey) =>
    setSort((current) =>
      current.key === key
        ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
        : { key, direction: key === "kickoff" ? "asc" : "desc" },
    );
  const clearFilters = () => {
    setStatusFilter("all");
    setQuery("");
    setLeagueFilter("all");
    setMarketFilter("all");
  };
  const statusCounts = discoveredRows.reduce<Record<MatchDisplayState, number>>(
    (counts, [, selections]) => {
      counts[matchDisplayState(selections[0])] += 1;
      return counts;
    },
    { finished: 0, live: 0, scheduled: 0, postponed: 0, cancelled: 0, abandoned: 0, awarded: 0 },
  );
  const filterButton = (
    key: "all" | MatchDisplayState,
    label: string,
    count: number,
  ) => (
    <button
      className={`${statusFilter === key ? "active" : ""} ${key}`}
      onClick={() => setStatusFilter(key)}
      aria-pressed={statusFilter === key}
      disabled={count === 0}
    >
      {label} <b>{count}</b>
    </button>
  );
  return (
    <section className="selection-panel all-matches-panel system-picks-panel">
      {rows.length === 0 ? (
        <p className="panel-empty">
          No Q ≥75 system picks are available for this date.
        </p>
      ) : (
        <>
          <div className="picks-overview">
            <div className="picks-overview-counts">
              <span><b>{sortedRows.length}</b> of <b>{rows.length}</b> matches shown</span>
              <span><b>{loadedSelections}</b> of <b>{totalSelections}</b> picks loaded</span>
            </div>
            <div className="picks-overview-statuses" aria-label="Match status totals">
              {statusCounts.finished > 0 && <span className="finished"><b>{statusCounts.finished}</b> finished</span>}
              {statusCounts.live > 0 && <span className="live"><b>{statusCounts.live}</b> in play</span>}
              {statusCounts.scheduled > 0 && <span className="scheduled"><b>{statusCounts.scheduled}</b> upcoming</span>}
              {statusCounts.postponed > 0 && <span><b>{statusCounts.postponed}</b> postponed</span>}
              {statusCounts.cancelled > 0 && <span><b>{statusCounts.cancelled}</b> cancelled</span>}
              {(statusCounts.abandoned > 0 || statusCounts.awarded > 0) && <span><b>{statusCounts.abandoned + statusCounts.awarded}</b> needing review</span>}
            </div>
            <p className="picks-overview-note">
              Q ≥75 selections only. Publication also applies price, edge, freshness, quality, and diversification gates.
            </p>
          </div>

          <div className="picks-controls">
            <div className="picks-controls-row picks-controls-search">
              <label className="picks-field picks-search">
                <span>Search</span>
                <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Team or competition" />
              </label>
              <label className="picks-field">
                <span>Competition</span>
                <select value={leagueFilter} onChange={(event) => setLeagueFilter(event.target.value)}>
                  <option value="all">All competitions</option>
                  {leagues.map((league) => <option key={league} value={league}>{league}</option>)}
                </select>
              </label>
              <div className="picks-sort-group">
                <label className="picks-field">
                  <span>Sort by</span>
                  <select aria-label="Sort matches" value={sort.key} onChange={(event) => changeSort(event.target.value as MatchSortKey)}>
                    <option value="kickoff">Kickoff</option><option value="match">Match</option><option value="league">Competition</option>
                    <option value="q">Q-score</option><option value="markets">Markets</option><option value="spread">Model agreement</option><option value="edge">Model edge</option>
                  </select>
                </label>
                <button
                  className="picks-sort-direction"
                  type="button"
                  onClick={() => setSort((current) => ({ ...current, direction: current.direction === "asc" ? "desc" : "asc" }))}
                  title={`Sort ${sort.direction === "asc" ? "descending" : "ascending"}`}
                >
                  {sort.direction === "asc" ? "Asc ↑" : "Desc ↓"}
                </button>
              </div>
            </div>
            <div className="picks-controls-row picks-controls-filter">
              <div className="match-status-filters" aria-label="Filter matches by status">
                {filterButton("all", "All", discoveredRows.length)}
                {statusCounts.finished > 0 && filterButton("finished", "Finished", statusCounts.finished)}
                {statusCounts.live > 0 && filterButton("live", "In play", statusCounts.live)}
                {statusCounts.scheduled > 0 && filterButton("scheduled", "Upcoming", statusCounts.scheduled)}
                {statusCounts.postponed > 0 && filterButton("postponed", "Postponed", statusCounts.postponed)}
                {statusCounts.cancelled > 0 && filterButton("cancelled", "Cancelled", statusCounts.cancelled)}
                {statusCounts.abandoned > 0 && filterButton("abandoned", "Abandoned · review", statusCounts.abandoned)}
                {statusCounts.awarded > 0 && filterButton("awarded", "Awarded · review", statusCounts.awarded)}
              </div>
              <div className="picks-controls-actions">
                <button className="match-clear-filters" onClick={clearFilters} disabled={activeFilterCount === 0}>
                  Clear filters{activeFilterCount > 0 ? ` · ${activeFilterCount}` : ""}
                </button>
              </div>
            </div>
            <div className="picks-controls-row picks-controls-market">
              <span className="picks-row-label">Market</span>
              <div className="market-quick-filters" role="group" aria-label="Quick market filters">
                <button className={marketFilter === "all" ? "active" : ""} onClick={() => setMarketFilter("all")} aria-pressed={marketFilter === "all"}>All markets</button>
                {quickMarkets.map((market) => (
                  <button key={market} className={marketFilter === market ? "active" : ""} onClick={() => setMarketFilter(market)} aria-pressed={marketFilter === market}>
                    {market}<span>{marketCounts[market]}</span>
                  </button>
                ))}
              </div>
              {markets.some((market) => !quickMarkets.includes(market)) && (
                <label className="picks-more-markets">
                  <span className="sr-only">Filter by another market</span>
                  <select value={quickMarkets.includes(marketFilter) || marketFilter === "all" ? "" : marketFilter} onChange={(event) => { if (event.target.value) setMarketFilter(event.target.value); }}>
                    <option value="">More markets…</option>{markets.filter((market) => !quickMarkets.includes(market)).map((market) => <option key={market} value={market}>{market}</option>)}
                  </select>
                </label>
              )}
            </div>
          </div>

          {filteredResults.length > 0 && <section className="match-scan-outcomes" aria-label="Settled results for this filtered match date">
            <div className="match-scan-outcomes-heading"><strong>Settled picks in this view</strong><span>{filteredResultCounts.matches.size} matches with settled picks · selected date only</span></div>
            <div className="match-scan-outcomes-table-wrap">
              <table className="match-scan-outcomes-table">
                <thead className="sr-only"><tr><th scope="col">Selections</th><th scope="col">Won</th><th scope="col">Lost</th><th scope="col">Hit rate</th><th scope="col">Net units</th><th scope="col">ROI</th></tr></thead>
                <tbody><tr>
                  <td><span>Selections</span><b>{filteredResults.length}</b></td>
                  <td><span>Won</span><b>{filteredResultCounts.won}</b></td>
                  <td><span>Lost</span><b>{filteredResultCounts.lost}</b></td>
                  <td><span>Hit rate</span><b>{decidedCount > 0 ? `${((filteredResultCounts.won / decidedCount) * 100).toFixed(1)}%` : "—"}</b></td>
                  <td><span>Net units</span><b>{filteredResultCounts.priced > 0 ? `${filteredResultCounts.netUnits >= 0 ? "+" : ""}${filteredResultCounts.netUnits.toFixed(2)}` : "—"}</b></td>
                  <td><span>ROI</span><b>{filteredResultCounts.priced > 0 ? `${((filteredResultCounts.netUnits / filteredResultCounts.priced) * 100).toFixed(1)}%` : "—"}</b></td>
                </tr></tbody>
              </table>
            </div>
            <p>{filteredResultCounts.void} void picks excluded from hit rate and ROI. ROI assumes one unit per settled non-void pick with captured odds; priced picks: {filteredResultCounts.priced} of {decidedCount}. Net units and ROI exclude picks without valid captured odds. This one-date summary is not a strategy backtest or a profitability claim.</p>
          </section>}
          <div className="picks-list-head" aria-hidden="true">
            <span>Match</span>
            <span className="picks-list-stats"><span>Kickoff</span><span>Q-score</span><span>Markets</span><span>Spread</span></span>
            <span>Pick result</span>
            <span>Status</span>
            <span />
          </div>
          {sortedRows.length === 0 ? (
            <p className="panel-empty">No qualified matches match these filters.</p>
          ) : (
            <div className="match-card-grid">
              {sortedRows.map(([matchId, selections]) => (
                <MatchMarketGroup
                  key={matchId}
                  selections={selections}
                  onSelect={onSelect}
                />
              ))}
            </div>
          )}
          {onLoadMore && loadedSelections < totalSelections && <button className="btn-ghost btn-sm" type="button" onClick={onLoadMore} disabled={loadingMore}>
            {loadingMore ? "Loading more candidates…" : `Load next 100 candidates (${totalSelections - loadedSelections} remaining)`}
          </button>}
        </>
      )}
    </section>
  );
}

function MatchMarketGroup({
  selections,
  onSelect,
}: {
  selections: SelectionSummary[];
  onSelect: (row: SelectionSummary) => void;
}) {
  const [sort, setSort] = useState<{
    key: "market" | "q" | "odds" | "spread" | "edge";
    direction: "asc" | "desc";
  }>({ key: "q", direction: "desc" });
  const first = selections[0];
  const displayState = matchDisplayState(first);
  const best = selections.reduce((a, b) => (a.q_score > b.q_score ? a : b));
  const pickOutcomes = selections.reduce<Record<"won" | "lost" | "void" | "pending", number>>(
    (counts, row) => {
      const outcome = row.result === "won" || row.result === "lost" || row.result === "void" ? row.result : "pending";
      counts[outcome] += 1;
      return counts;
    },
    { won: 0, lost: 0, void: 0, pending: 0 },
  );
  const statusTone = displayState === "live" ? "inplay"
    : displayState === "finished" ? "finished"
    : displayState === "scheduled" ? "scheduled"
    : displayState === "postponed" || displayState === "cancelled" ? "void"
    : "pending";
  const sorted = [...selections].sort((a, b) => {
    const values: Record<typeof sort.key, [string | number, string | number]> =
      {
        market: [formatMarket(a.market), formatMarket(b.market)],
        q: [a.q_score, b.q_score],
        odds: [a.best_odds ?? 0, b.best_odds ?? 0],
        spread: [a.model_agreement ?? 999, b.model_agreement ?? 999],
        edge: [a.edge ?? -999, b.edge ?? -999],
      };
    const [left, right] = values[sort.key];
    const result = left < right ? -1 : left > right ? 1 : 0;
    return sort.direction === "asc" ? result : -result;
  });
  const changeSort = (key: typeof sort.key) =>
    setSort((current) =>
      current.key === key
        ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
        : { key, direction: key === "market" ? "asc" : "desc" },
    );
  const button = (key: typeof sort.key, label: string) => (
    <button
      className={sort.key === key ? "active" : ""}
      onClick={(event) => {
        event.preventDefault();
        changeSort(key);
      }}
    >
      {label}
      {sort.key === key && (
        <span aria-hidden="true"> {sort.direction === "asc" ? "↑" : "↓"}</span>
      )}
    </button>
  );
  return (
    <details className={`match-accordion match-card ${displayState}`}>
      <summary className="match-card-summary match-row-summary">
        <div className="match-row-match">
          <span className="match-row-league">{first.competition}</span>
          <strong className="match-row-teams" title={`${first.home_team} vs ${first.away_team}`}>
            {first.home_team} <span className="leg-match-vs">vs</span>{" "}
            {first.away_team}
          </strong>
        </div>
        <div className="match-row-stats">
          <span><small>Kickoff</small><b className="kickoff-time">{formatKickoff(first.kickoff_at)}</b></span>
          <span><small>Q-score</small><b>Q {best.q_score.toFixed(1)}</b></span>
          <span><small>Markets</small><b>{selections.length}</b></span>
          <span><small>Spread</small><b className={`spread-badge ${spreadTone(best.model_agreement)}`}>{best.model_agreement == null ? "—" : `${(best.model_agreement * 100).toFixed(1)} pp`}</b></span>
        </div>
        <div className="match-row-picks">
          <small>Pick result</small>
          <span className="match-row-picks-badges">
            {(["won", "lost", "void", "pending"] as const)
              .filter((outcome) => pickOutcomes[outcome] > 0)
              .map((outcome) => (
                <b key={outcome} className={`market-result ${outcome}`}>
                  {selectionStatusLabel(outcome)}
                  {pickOutcomes[outcome] > 1 ? ` ×${pickOutcomes[outcome]}` : ""}
                </b>
              ))}
          </span>
        </div>
        <div className="match-row-status">
          <b className={`match-result-badge ${statusTone}`}>{matchStatusText(first)}</b>
        </div>
        <div className="match-row-actions">
          <span className="match-card-expand">View markets <b aria-hidden="true">⌄</b></span>
        </div>
      </summary>
      <div className="market-table">
        <div className="market-table-head">
          <span className="market-sort-label">Sort markets</span>
          {button("market", "Market")}
          {button("q", "Q-score")}
          {button("odds", "Captured odds")}
          {button("spread", "Spread")}
          {button("edge", "Edge")}
        </div>
        {sorted.map((row) => {
          const freshness = quoteFreshness(row);
          return <div className="market-row" key={row.prediction_id}>
            <div className="market-row-identity">
              {!selectionRepeatsMarket(row.market, row.selection) && <span className="market-row-market">{formatMarket(row.market)}</span>}
              <strong className="market-row-selection">{formatSelection(row.selection)}</strong>
              <span className="market-row-badges">
                <b className={`grade-badge grade-${gradeTone(row.q_grade)}`}>
                  {row.q_grade ?? "Qualified"}
                </b>
                <b className={`market-result ${row.result ?? "pending"}`}>{row.result === "won" ? "Won" : row.result === "lost" ? "Lost" : row.result === "void" ? "Void" : "Pending"}</b>
              </span>
              <div className="market-chance-evidence">
                <span>Model chance <b>{percent(row.model_probability)}</b></span>
                <span>Bookmaker implied <b>{percent(row.source_implied_probability ?? row.avg_implied)}</b> <em>margin included</em></span>
              </div>
            </div>
            <div className="market-row-actions">
              <button className="btn-ghost btn-sm" onClick={() => onSelect(row)}>
                Details
              </button>
            </div>
            <dl className="market-row-facts">
              <div>
                <dt>Q-score</dt>
                <dd>Q {row.q_score.toFixed(1)}</dd>
              </div>
              <div>
                <dt>Captured odds</dt>
                <dd>{row.best_odds ? `${row.best_odds.toFixed(2)}×` : "—"}</dd>
                <small className="market-quote-meta">{row.source_bookmaker ?? "Bookmaker unavailable"} · {quoteTime(row.source_odds_at)} · <b className={freshness.state}>{freshness.label}</b></small>
              </div>
              <div className={spreadTone(row.model_agreement)} title={`Model spread: ${spreadLabel(row.model_agreement)}`}>
                <dt>Spread</dt>
                <dd>{row.model_agreement == null ? "—" : `${(row.model_agreement * 100).toFixed(1)} pp`}</dd>
              </div>
              <div className={row.edge != null && row.edge > 0 ? "positive" : undefined}>
                <dt>Edge</dt>
                <dd>{row.edge != null ? `${(row.edge * 100).toFixed(1)}%` : "—"}</dd>
              </div>
            </dl>
          </div>;
        })}
      </div>
    </details>
  );
}