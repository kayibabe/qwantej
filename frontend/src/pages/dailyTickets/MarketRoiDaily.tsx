import { useMemo, useState } from "react";
import { useSortableRows } from "../../components/SortableTable";
import "./MarketRoiDaily.css";

interface MarketRoiRow {
  market: string;
  sample_size: number;
  wins: number;
  losses: number;
  hit_rate: number;
  flat_stake_pnl: number;
  roi: number;
  average_odds: number;
  qualifies: boolean;
  evidence_label: string;
}

interface MarketCandidate {
  prediction_id: number;
  match_id: number;
  home_team: string;
  away_team: string;
  competition: string;
  kickoff_at: string;
  match_status: string;
  home_goals: number | null;
  away_goals: number | null;
  result: "won" | "lost" | "void" | null;
  market: string;
  selection: string;
  odds: number;
  model_probability: number;
  q_score: number;
  q_grade: string;
  recommendation_status: string;
  market_roi: number;
  market_hit_rate: number;
  market_sample_size: number;
  quote_at: string;
  quote_age_minutes: number;
  bookmaker: string;
}

export interface MarketRoiDailyData {
  target_date: string;
  refreshed_at: string;
  hit_rate_threshold: number;
  roi_threshold: number;
  min_q_score: number;
  min_decimal_odds: number;
  max_decimal_odds_exclusive: number;
  max_quote_age_hours: number;
  historical_through: string;
  historical_unique_selections: number;
  historical_fixture_summary: { unique_fixtures: number; all_won: number; all_lost: number; mixed: number };
  historical_markets: MarketRoiRow[];
  qualifying_markets: string[];
  candidate_count: number;
  candidate_fixture_count: number;
  candidates: MarketCandidate[];
  unsupported_outcomes_excluded: number;
  method: string;
  research_only: boolean;
}

export async function fetchDailyMarketRoi(date: string): Promise<MarketRoiDailyData> {
  const response = await fetch(`/api/v1/performance/market-roi-daily?date=${encodeURIComponent(date)}`);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json() as Promise<MarketRoiDailyData>;
}

const pct = (value: number) => `${(value * 100).toFixed(1)}%`;
const title = (value: string) => value
  .replace(/_(\d+)_(\d+)/g, " $1.$2")
  .replace(/_/g, " ")
  .replace(/\b\w/g, (letter: string) => letter.toUpperCase());
const localDateTime = (value: string) => new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium", timeStyle: "short",
}).format(new Date(value));
const ageAtRefresh = (minutes: number) => minutes < 60
  ? `${minutes.toFixed(0)} min old`
  : minutes < 24 * 60
    ? `${(minutes / 60).toFixed(1)} hr old`
    : `${(minutes / (24 * 60)).toFixed(1)} days old`;

type CandidateSortKey = "kickoff" | "match" | "market" | "odds" | "q_score" | "hit_rate" | "roi" | "sample_size";

function MarketRoiDailyContent({ data, error, view }: { data: MarketRoiDailyData | null; error: string | null; view: "market-roi" | "daily-match-picks" }) {
  const [minimumQuality, setMinimumQuality] = useState("70");
  const [grade, setGrade] = useState("all");
  const fixtures = useMemo(() => {
    const grouped = new Map<number, MarketCandidate[]>();
    for (const candidate of data?.candidates ?? []) {
      const rows = grouped.get(candidate.match_id) ?? [];
      rows.push(candidate);
      grouped.set(candidate.match_id, rows);
    }
    return [...grouped.values()];
  }, [data?.candidates]);
  const filteredFixtures = useMemo(() => fixtures
    .map((rows) => rows.filter((row) =>
      (minimumQuality === "all" || row.q_score >= Number(minimumQuality)) &&
      (grade === "all" || row.q_grade.trim().toUpperCase() === grade)))
    .filter((rows) => rows.length > 0), [fixtures, minimumQuality, grade]);
  const filteredCandidates = useMemo(() => filteredFixtures.flat(), [filteredFixtures]);
  const sortAccessors = {
    kickoff: (row: MarketCandidate) => row.kickoff_at,
    match: (row: MarketCandidate) => `${row.home_team} ${row.away_team}`,
    market: (row: MarketCandidate) => `${title(row.market)} ${title(row.selection)}`,
    odds: (row: MarketCandidate) => row.odds,
    q_score: (row: MarketCandidate) => row.q_score,
    hit_rate: (row: MarketCandidate) => row.market_hit_rate,
    roi: (row: MarketCandidate) => row.market_roi,
    sample_size: (row: MarketCandidate) => row.market_sample_size,
  } satisfies Record<CandidateSortKey, (row: MarketCandidate) => string | number>;
  const { sorted: sortedCandidates, header } = useSortableRows(
    filteredCandidates,
    sortAccessors,
    { key: "kickoff", direction: "asc" },
  );

  return (
    <section className="market-roi-panel">
      <header className="market-roi-heading">
        <div>
          <span className="eyebrow">Daily market scan · research only</span>
          <h2 className="section-title">{view === "market-roi" ? "Hit rate and ROI by market" : `Daily Match Picks · ${data?.target_date ?? "selected date"}`}</h2>
          <p>{view === "market-roi"
            ? `Markets qualify from all settled matches before ${data?.target_date ?? "the selected day"} when historical hit rate is above 50% and flat-stake ROI is above 30%. This view ranks those markets. Daily Match Picks lists every match in qualifying markets that meets Q ≥ 70 and odds from 2.00 to below 3.00. It refreshes automatically every five minutes.`
            : `All matches on ${data?.target_date ?? "the selected date"} in markets that pass the historical hit rate and ROI gates, with Q ≥ 70 and decimal odds from 2.00 to below 3.00. It refreshes automatically every five minutes.`}</p>
        </div>
        <div className="market-roi-refresh">
          <span>Auto refresh · 5 min</span>
          {data && <small>Updated {localDateTime(data.refreshed_at)}</small>}
        </div>
      </header>

      {error && <div className="market-roi-error" role="alert"><b>Market scan unavailable</b><span>{error}</span></div>}
      {!data && !error && <p className="panel-empty">Loading daily market performance…</p>}

      {data && <>
        {view === "market-roi" && <div className="market-roi-kpis">
          <span><small>Historical window through</small><b>{data.historical_through}</b></span>
          <span><small>Historical selections</small><b>{data.historical_unique_selections}</b></span>
          <span><small>Unique fixtures</small><b>{data.historical_fixture_summary.unique_fixtures}</b></span>
          <span><small>Markets meeting both gates</small><b>{data.qualifying_markets.length}</b></span>
          <span><small>Selected-day matches</small><b>{fixtures.length}</b></span>
          <span><small>Eligible market selections</small><b>{fixtures.reduce((count, rows) => count + rows.length, 0)}</b></span>
        </div>}

        {view === "market-roi" && <div className="market-roi-fixture-summary" aria-label="Historical results grouped by unique fixture">
          <b>Historical fixture outcomes</b>
          <span>{data.historical_fixture_summary.all_won} all selections won</span>
          <span>{data.historical_fixture_summary.all_lost} all selections lost</span>
          <span>{data.historical_fixture_summary.mixed} mixed outcomes</span>
        </div>}

        {view === "market-roi" && <div className="market-roi-note" role="note">
          Historical performance uses the latest valid pre-kickoff prediction per fixture, market and selection, across all stored predictions. A market qualifies only when hit rate &gt; {pct(data.hit_rate_threshold)} and ROI &gt; {pct(data.roi_threshold)}. Daily picks require Q ≥ {data.min_q_score}, odds ≥ {data.min_decimal_odds.toFixed(2)} and &lt; {data.max_decimal_odds_exclusive.toFixed(2)}, and a bookmaker quote captured before kickoff and within {data.max_quote_age_hours} hours of the prediction decision. Quote age at refresh is shown for context. These are historical research results, not a profitability claim.
        </div>}

        {view === "market-roi" && <div className="market-roi-table-wrap">
          <h3>Historical market ranking</h3>
          {data.historical_markets.length === 0 ? <p className="panel-empty">No settled historical picks are available for Q ≥ {data.min_q_score}, odds {data.min_decimal_odds.toFixed(2)} to below {data.max_decimal_odds_exclusive.toFixed(2)}, and quote age ≤ {data.max_quote_age_hours} hours.</p> : (
            <table className="market-roi-table">
              <thead><tr><th>Rank</th><th>Market</th><th>ROI</th><th>W–L</th><th>Hit rate</th><th>Flat P&amp;L</th><th>Picks</th><th>Evidence</th><th>Status</th></tr></thead>
              <tbody>{data.historical_markets.map((row, index) => <tr key={row.market}>
                <td>{index + 1}</td><td><span className={`market-roi-selection-chip ${row.qualifies ? "qualifies" : ""}`}>{title(row.market)}</span></td>
                <td className={row.roi >= 0 ? "roi-positive" : "roi-negative"}>{pct(row.roi)}</td>
                <td>{row.wins}–{row.losses}</td><td>{pct(row.hit_rate)}</td>
                <td className={row.flat_stake_pnl >= 0 ? "roi-positive" : "roi-negative"}>{row.flat_stake_pnl >= 0 ? "+" : ""}{row.flat_stake_pnl.toFixed(2)}</td>
                <td>{row.sample_size}</td><td>{row.evidence_label}</td>
                <td><span className={`market-roi-badge ${row.qualifies ? "qualifies" : ""}`}>{row.qualifies ? "Meets both gates" : "Below one or both gates"}</span></td>
              </tr>)}</tbody>
            </table>
          )}
        </div>}

        {view === "daily-match-picks" && <div className="market-roi-table-wrap market-roi-candidates">
          <h3>Matches qualifying today · {data.target_date}</h3>
          <div className="market-roi-filters">
            <label>Minimum Q
              <select value={minimumQuality} onChange={(event) => setMinimumQuality(event.target.value)}>
                {[70, 80, 90].map((score) => <option key={score} value={score}>{score} and above</option>)}
              </select>
            </label>
            <label>Grade
              <select value={grade} onChange={(event) => setGrade(event.target.value)}>
                <option value="all">All</option>
                {["A+", "A", "B+", "B", "C"].map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </label>
            <span role="status">Showing {filteredFixtures.length} of {fixtures.length} matches · {filteredCandidates.length} market picks</span>
          </div>
          {fixtures.length === 0 ? <p className="panel-empty">No matches on {data.target_date} currently meet Q ≥ {data.min_q_score} and odds {data.min_decimal_odds.toFixed(2)} to below {data.max_decimal_odds_exclusive.toFixed(2)} in a market with historical hit rate above {pct(data.hit_rate_threshold)} and ROI above {pct(data.roi_threshold)}.</p> : (
            filteredFixtures.length === 0 ? <p className="panel-empty">No selections match these filters. Choose All or lower the Quality Score threshold.</p> :
            <div className="market-roi-daily-table-wrap">
            <table className="market-roi-table market-roi-picks-table">
              <thead><tr>
                {header("kickoff", "Kickoff")}
                {header("match", "Match")}
                <th>Competition</th>
                {header("market", "Market pick")}
                {header("odds", "Odds")}
                {header("q_score", "Q-score")}
                {header("hit_rate", "Historical hit rate")}
                {header("roi", "Historical ROI")}
                {header("sample_size", "History")}
                <th>Bookmaker quote</th>
                <th>Result</th>
              </tr></thead>
              <tbody>{sortedCandidates.map((row) => {
                const resultLabel = row.result
                  ? title(row.result)
                  : row.match_status === "finished" ? "Finished" : title(row.match_status);
                const score = row.home_goals != null && row.away_goals != null
                  ? `${row.home_goals}–${row.away_goals}`
                  : null;
                return <tr key={row.prediction_id}>
                  <td data-label="Kickoff"><time dateTime={row.kickoff_at}>{localDateTime(row.kickoff_at)}</time></td>
                  <td data-label="Match"><b>{row.home_team} vs {row.away_team}</b></td>
                  <td data-label="Competition">{row.competition || "—"}</td>
                  <td data-label="Market pick"><span className="market-roi-selection-chip qualifies">{title(row.market)}</span><small className="market-roi-cell-subtitle">{title(row.selection)}</small></td>
                  <td data-label="Odds"><b>{row.odds.toFixed(2)}</b><small className="market-roi-cell-subtitle">{row.bookmaker || "Bookmaker unavailable"}</small></td>
                  <td data-label="Q-score"><b>{row.q_score.toFixed(1)}</b><small className="market-roi-cell-subtitle">{row.q_grade}</small></td>
                  <td data-label="Historical hit rate"><b>{pct(row.market_hit_rate)}</b></td>
                  <td data-label="Historical ROI" className={row.market_roi >= 0 ? "roi-positive" : "roi-negative"}><b>{pct(row.market_roi)}</b></td>
                  <td data-label="History">{row.market_sample_size} picks</td>
                  <td data-label="Bookmaker quote"><time dateTime={row.quote_at}>{localDateTime(row.quote_at)}</time><small className="market-roi-cell-subtitle">{ageAtRefresh(row.quote_age_minutes)} at refresh</small></td>
                  <td data-label="Result"><span className={`market-roi-result ${row.result ?? "pending"}`}>{resultLabel}</span>{score && <small className="market-roi-cell-subtitle">{score}</small>}</td>
                </tr>;
              })}</tbody>
            </table>
            </div>
          )}
        </div>}
      </>}
    </section>
  );
}

export function MarketRoiDaily({ data, error }: { data: MarketRoiDailyData | null; error: string | null }) {
  return <MarketRoiDailyContent data={data} error={error} view="market-roi" />;
}

export function DailyMatchPicks({ data, error }: { data: MarketRoiDailyData | null; error: string | null }) {
  return <MarketRoiDailyContent data={data} error={error} view="daily-match-picks" />;
}
