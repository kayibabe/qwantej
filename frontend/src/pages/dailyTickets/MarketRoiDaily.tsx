import { useEffect, useMemo, useState } from "react";
import { useSortableRows } from "../../components/SortableTable";

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
  settled_daily_pick_market_performance: {
    date_from: string;
    calculated_at: string;
    completed_through: string | null;
    included_days: string[];
    waiting_for_settlement_days: string[];
    earlier_through: string;
    later_from: string;
    markets: Array<{
      market: string;
      selections: number;
      wins: number;
      losses: number;
      hit_rate: number | null;
      flat_stake_pnl: number;
      roi: number | null;
      earlier_roi: number | null;
      later_roi: number | null;
    }>;
  };
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
const localDateTime = (value: string) => {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "time unavailable"
    : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(parsed);
};
const ageAtRefresh = (minutes: number) => minutes < 60
  ? `${minutes.toFixed(0)} min old`
  : minutes < 24 * 60
    ? `${(minutes / 60).toFixed(1)} hr old`
    : `${(minutes / (24 * 60)).toFixed(1)} days old`;
const focusRing = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700";

type CandidateSortKey = "kickoff" | "match" | "market" | "odds" | "q_score" | "hit_rate" | "roi" | "sample_size";

function pnlClass(value: number | null | undefined) {
  if (value == null) return "text-slate-600";
  if (value > 0) return "text-emerald-700";
  if (value < 0) return "text-red-700";
  return "text-slate-700";
}

export function MarketRoiDaily({ data, error }: { data: MarketRoiDailyData | null; error: string | null }) {
  const [minimumQuality, setMinimumQuality] = useState("70");
  const [grade, setGrade] = useState("all");
  const [lastGood, setLastGood] = useState<MarketRoiDailyData | null>(null);

  // The parent clears its payload when a refresh fails. Keep the last
  // successful result locally and label it clearly instead of blanking the
  // whole report (or silently presenting stale numbers as current).
  useEffect(() => {
    if (data) setLastGood(data);
  }, [data]);

  const displayed = data ?? (error ? lastGood : null);
  const stale = displayed != null && (error || !data);
  const fixtures = useMemo(() => {
    const grouped = new Map<number, MarketCandidate[]>();
    for (const candidate of displayed?.candidates ?? []) {
      const rows = grouped.get(candidate.match_id) ?? [];
      rows.push(candidate);
      grouped.set(candidate.match_id, rows);
    }
    return [...grouped.values()];
  }, [displayed?.candidates]);
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
  const { sorted: sortedCandidates, header, sort, toggle } = useSortableRows(
    filteredCandidates,
    sortAccessors,
    { key: "kickoff", direction: "asc" },
  );

  const settled = displayed?.settled_daily_pick_market_performance;
  const earlierLabel = settled?.earlier_through ? `Through ${settled.earlier_through}` : "Earlier window";
  const laterLabel = settled?.later_from ? `From ${settled.later_from}` : "Later window";

  return (
    <section className="space-y-5 min-w-0">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-4">
          <div className="space-y-2">
            <span className="text-sm font-semibold text-slate-600">Daily market scan · research only</span>
            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">Hit rate and ROI by market</h2>
            <p className="text-base leading-relaxed text-slate-600 max-w-3xl">
              Compare historical market results, then inspect the selected date’s qualifying research candidates. Small samples remain exploratory; the <a href="#market-roi-method" className={`font-semibold text-emerald-800 underline underline-offset-2 hover:text-emerald-900 ${focusRing}`}>method and caveats</a> apply to every panel.
            </p>
          </div>
          {settled && displayed && (
            <section className="rounded-xl border border-slate-200 bg-white overflow-hidden" aria-label="Settled Daily Match Picks performance">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 px-4 py-3">
                <div className="min-w-0">
                  <h3 className="text-base font-bold text-slate-900">Settled Daily Match Picks performance</h3>
                  <p className="text-sm leading-relaxed text-slate-600 mt-1">
                    From {settled.date_from} · Q ≥ {displayed.min_q_score} · odds {displayed.min_decimal_odds.toFixed(2)} to below {displayed.max_decimal_odds_exclusive.toFixed(2)}
                  </p>
                </div>
                <div className="text-sm leading-relaxed text-slate-600">
                  <span className="block font-semibold text-slate-700">
                    {settled.completed_through
                      ? `Completed through ${settled.completed_through}`
                      : "Waiting for the first full day to settle"}
                  </span>
                  {settled.waiting_for_settlement_days.length > 0
                    ? <span className="block">Waiting: {settled.waiting_for_settlement_days.join(", ")}</span>
                    : null}
                  <span className="block">Calculated {localDateTime(settled.calculated_at)}</span>
                </div>
              </div>
              {settled.markets.length === 0
                ? <p className="px-4 py-4 text-base text-slate-600">No fully settled Daily Match Picks are available for this period yet.</p>
                : (
                  <div className="relative overflow-x-auto focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" role="region" aria-label="Settled market performance columns" tabIndex={0}>
                    <table className="w-full min-w-[1040px] border-collapse text-left text-sm">
                      <thead className="border-b border-slate-200 bg-slate-50 text-sm font-semibold text-slate-700">
                        <tr>
                          <th scope="col" className="px-4 py-3 font-semibold">Market</th>
                          <th scope="col" className="px-4 py-3 font-semibold">Selections</th>
                          <th scope="col" className="px-4 py-3 font-semibold">Won</th>
                          <th scope="col" className="px-4 py-3 font-semibold">Lost</th>
                          <th scope="col" className="px-4 py-3 font-semibold">Hit rate</th>
                          <th scope="col" className="px-4 py-3 font-semibold">Net units</th>
                          <th scope="col" className="px-4 py-3 font-semibold">ROI</th>
                          <th scope="col" className="px-4 py-3 font-semibold">
                            Earlier ROI<small className="block font-normal text-slate-600">{earlierLabel}</small>
                          </th>
                          <th scope="col" className="px-4 py-3 font-semibold">
                            Later ROI<small className="block font-normal text-slate-600">{laterLabel}</small>
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {settled.markets.map((row) => (
                          <tr key={row.market} className="hover:bg-slate-50/70">
                            <td className="px-4 py-2.5"><span className="inline-flex rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-sm font-semibold text-slate-700">{title(row.market)}</span></td>
                            <td className="px-4 py-2.5 font-mono tabular-nums text-slate-700">{row.selections}</td>
                            <td className="px-4 py-2.5 font-mono tabular-nums text-slate-700">{row.wins}</td>
                            <td className="px-4 py-2.5 font-mono tabular-nums text-slate-700">{row.losses}</td>
                            <td className="px-4 py-2.5 font-mono tabular-nums text-slate-700">{row.hit_rate == null ? "—" : pct(row.hit_rate)}</td>
                            <td className={`px-4 py-2.5 font-mono font-semibold tabular-nums ${pnlClass(row.flat_stake_pnl)}`}>{row.flat_stake_pnl >= 0 ? "+" : ""}{row.flat_stake_pnl.toFixed(2)}</td>
                            <td className={`px-4 py-2.5 font-mono font-semibold tabular-nums ${pnlClass(row.roi)}`}>{row.roi == null ? "—" : pct(row.roi)}</td>
                            <td className={`px-4 py-2.5 font-mono font-semibold tabular-nums ${pnlClass(row.earlier_roi)}`}>{row.earlier_roi == null ? "—" : pct(row.earlier_roi)}</td>
                            <td className={`px-4 py-2.5 font-mono font-semibold tabular-nums ${pnlClass(row.later_roi)}`}>{row.later_roi == null ? "—" : pct(row.later_roi)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              <p className="px-4 py-3 text-sm leading-relaxed text-slate-600 border-t border-slate-200">
                One unit per settled selection at its captured odds; void picks and dates awaiting settlement are excluded. Rows are ordered from highest ROI. <a href="#market-roi-method" className={`font-semibold text-emerald-800 underline underline-offset-2 hover:text-emerald-900 ${focusRing}`}>Method and caveats</a>.
              </p>
            </section>
          )}
        </div>
        <div className="shrink-0 space-y-1 text-sm leading-relaxed text-slate-600 lg:text-right">
          <span className="block font-semibold text-slate-700">Auto refresh · 5 min</span>
          {displayed && <span className="block">Updated {localDateTime(displayed.refreshed_at)}</span>}
          {displayed && <span className="block">Scan date {displayed.target_date}</span>}
        </div>
      </header>

      {stale && displayed && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-relaxed text-amber-900" role="status">
          <strong className="block text-amber-950">Showing the last successful scan.</strong>
          The latest refresh failed; figures below were captured {localDateTime(displayed.refreshed_at)} for {displayed.target_date}.
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm leading-relaxed text-red-800" role="alert">
          <b className="block font-bold text-red-900">Market scan unavailable</b>
          <span>{error}</span>
        </div>
      )}
      {!displayed && !error && <p className="text-base text-slate-600" role="status">Loading daily market performance…</p>}

      {displayed && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Kpi label={`History through ${displayed.historical_through}`} value={`${displayed.historical_unique_selections} selections`} />
            <Kpi label="Historical fixtures" value={String(displayed.historical_fixture_summary.unique_fixtures)} />
            <Kpi label="Markets meeting configured formula" value={String(displayed.qualifying_markets.length)} />
            <Kpi label={`${displayed.target_date} research set`} value={`${fixtures.length} matches · ${fixtures.reduce((count, rows) => count + rows.length, 0)} picks`} />
          </div>

          <details id="market-roi-method" className="rounded-xl border border-slate-200 bg-white overflow-hidden">
            <summary className={`cursor-pointer px-4 py-3 text-base font-semibold text-slate-800 hover:bg-slate-50 ${focusRing}`}>Method, qualification gates and sample caveats</summary>
            <div className="space-y-3 border-t border-slate-200 px-4 py-4 text-base leading-relaxed text-slate-700">
              <p>Historical performance uses the latest valid pre-kickoff prediction per fixture, market and selection. A market meets the configured formula when hit rate is above {pct(displayed.hit_rate_threshold)} and flat-stake ROI is above {pct(displayed.roi_threshold)}. This formula does not set a minimum sample size; check the evidence label and pick count before interpreting a result.</p>
              <p>Daily picks require Q ≥ {displayed.min_q_score}, odds ≥ {displayed.min_decimal_odds.toFixed(2)} and &lt; {displayed.max_decimal_odds_exclusive.toFixed(2)}, and a bookmaker quote captured before kickoff and within {displayed.max_quote_age_hours} hours of the prediction decision. Quote age at refresh describes how old that saved quote is now.</p>
              <p>One unit per settled selection at its captured odds; void picks and dates still awaiting settlement are excluded. The experimental shortlist applies the same historical rule with no minimum settled sample size. All figures are reconstructed paper results, not recorded bookmaker bets or a profitability guarantee.</p>
              <div className="flex flex-wrap gap-x-5 gap-y-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700" aria-label="Historical results grouped by unique fixture">
                <b className="text-slate-800">Historical fixture outcomes</b>
                <span>{displayed.historical_fixture_summary.all_won} all selections won</span>
                <span>{displayed.historical_fixture_summary.all_lost} all selections lost</span>
                <span>{displayed.historical_fixture_summary.mixed} mixed outcomes</span>
              </div>
            </div>
          </details>

          <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
            <h3 className="border-b border-slate-200 px-4 py-3 text-base font-bold text-slate-800">Historical market ranking</h3>
            {displayed.historical_markets.length === 0 ? (
              <p className="px-4 py-4 text-base text-slate-600">No settled historical picks are available for Q ≥ {displayed.min_q_score}, odds {displayed.min_decimal_odds.toFixed(2)} to below {displayed.max_decimal_odds_exclusive.toFixed(2)}, and quote age ≤ {displayed.max_quote_age_hours} hours.</p>
            ) : (
              <div className="relative overflow-x-auto focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" role="region" aria-label="Historical market ranking columns" tabIndex={0}>
                <table className="w-full min-w-[1080px] border-collapse text-left text-sm">
                  <thead className="border-b border-slate-200 bg-slate-50 text-sm font-semibold text-slate-700">
                    <tr>
                      <th scope="col" className="px-4 py-3 font-semibold">Rank</th>
                      <th scope="col" className="px-4 py-3 font-semibold">Market</th>
                      <th scope="col" className="px-4 py-3 font-semibold">ROI</th>
                      <th scope="col" className="px-4 py-3 font-semibold">W–L</th>
                      <th scope="col" className="px-4 py-3 font-semibold">Hit rate</th>
                      <th scope="col" className="px-4 py-3 font-semibold">Flat P&amp;L</th>
                      <th scope="col" className="px-4 py-3 font-semibold">Picks</th>
                      <th scope="col" className="px-4 py-3 font-semibold">Evidence</th>
                      <th scope="col" className="px-4 py-3 font-semibold">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {displayed.historical_markets.map((row, index) => (
                      <tr key={row.market} className="hover:bg-slate-50/70">
                        <td className="px-4 py-2.5 font-mono tabular-nums text-slate-700">{index + 1}</td>
                        <td className="px-4 py-2.5"><span className={`inline-flex rounded-md border px-2.5 py-1 text-sm font-semibold ${row.qualifies ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-slate-200 bg-slate-50 text-slate-700"}`}>{title(row.market)}</span></td>
                        <td className={`px-4 py-2.5 font-mono font-semibold tabular-nums ${pnlClass(row.roi)}`}>{pct(row.roi)}</td>
                        <td className="px-4 py-2.5 font-mono tabular-nums text-slate-700">{row.wins}–{row.losses}</td>
                        <td className="px-4 py-2.5 font-mono tabular-nums text-slate-700">{pct(row.hit_rate)}</td>
                        <td className={`px-4 py-2.5 font-mono font-semibold tabular-nums ${pnlClass(row.flat_stake_pnl)}`}>{row.flat_stake_pnl >= 0 ? "+" : ""}{row.flat_stake_pnl.toFixed(2)}</td>
                        <td className="px-4 py-2.5 font-mono tabular-nums text-slate-700">{row.sample_size}</td>
                        <td className="px-4 py-2.5 text-slate-700">{row.evidence_label}</td>
                        <td className="px-4 py-2.5">
                          <span className={`inline-flex rounded-full border px-2.5 py-1 text-sm font-semibold ${row.qualifies ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-slate-200 bg-slate-100 text-slate-700"}`}>
                            {row.qualifies ? "Meets configured gates" : "Below one or both gates"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
            <div className="border-b border-slate-200 px-4 py-3 space-y-3">
              <h3 className="text-base font-bold text-slate-800">Research candidates · {displayed.target_date}</h3>
              <p className="text-sm leading-relaxed text-slate-700" role="note">
                Experimental shortlist. See the <a href="#market-roi-method" className={`font-semibold text-emerald-800 underline underline-offset-2 hover:text-emerald-900 ${focusRing}`}>method and caveats</a>.
              </p>
              <div className="flex flex-wrap items-end gap-3">
                <label className="grid gap-1 text-sm font-medium text-slate-700">Minimum Q
                  <select value={minimumQuality} onChange={(event) => setMinimumQuality(event.target.value)} className={`h-11 min-w-[160px] rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-700 focus:border-emerald-700`}>
                    {[70, 80, 90].map((score) => <option key={score} value={score}>{score} and above</option>)}
                  </select>
                </label>
                <label className="grid gap-1 text-sm font-medium text-slate-700">Grade
                  <select value={grade} onChange={(event) => setGrade(event.target.value)} className={`h-11 min-w-[130px] rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-700 focus:border-emerald-700`}>
                    <option value="all">All</option>
                    {["A+", "A", "B+", "B", "C"].map((value) => <option key={value} value={value}>{value}</option>)}
                  </select>
                </label>
                <span role="status" className="pb-2 text-sm text-slate-700">Showing {filteredFixtures.length} of {fixtures.length} matches · {filteredCandidates.length} market picks</span>
              </div>
            </div>
            {fixtures.length === 0 ? (
              <p className="px-4 py-4 text-base text-slate-600">No matches on {displayed.target_date} currently meet Q ≥ {displayed.min_q_score} and odds {displayed.min_decimal_odds.toFixed(2)} to below {displayed.max_decimal_odds_exclusive.toFixed(2)} in a market with historical hit rate above {pct(displayed.hit_rate_threshold)} and ROI above {pct(displayed.roi_threshold)}.</p>
            ) : filteredFixtures.length === 0 ? (
              <p className="px-4 py-4 text-base text-slate-600">No selections match these filters. Choose All or lower the Quality Score threshold.</p>
            ) : (
              <div className="relative overflow-x-auto focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" role="region" aria-label="Research candidate columns" tabIndex={0}>
                <table className="w-full min-w-[1100px] border-collapse text-left text-sm">
                  <thead className="border-b border-slate-200 bg-slate-50 text-sm font-semibold text-slate-700">
                    <tr>
                      {header("kickoff", "Kickoff", "px-4 py-3")}
                      {header("match", "Match", "px-4 py-3")}
                      {header("market", "Market pick", "px-4 py-3")}
                      {header("odds", "Odds", "px-4 py-3")}
                      {header("q_score", "Q-score", "px-4 py-3")}
                      <th scope="col" className="px-4 py-3 font-semibold">
                        <details className="group">
                          <summary className={`inline-flex min-h-11 cursor-pointer items-center rounded-md px-2 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100 hover:text-slate-900 ${focusRing}`}>Historical and quote evidence</summary>
                          <div role="group" aria-label="Sort candidates by historical evidence" className="mt-2 flex flex-wrap gap-1 normal-case tracking-normal">
                            <SortBtn active={sort?.key === "hit_rate"} dir={sort?.key === "hit_rate" ? sort.direction : undefined} onClick={() => toggle("hit_rate")}>Hit rate</SortBtn>
                            <SortBtn active={sort?.key === "roi"} dir={sort?.key === "roi" ? sort.direction : undefined} onClick={() => toggle("roi")}>ROI</SortBtn>
                            <SortBtn active={sort?.key === "sample_size"} dir={sort?.key === "sample_size" ? sort.direction : undefined} onClick={() => toggle("sample_size")}>Sample</SortBtn>
                          </div>
                        </details>
                      </th>
                      <th scope="col" className="px-4 py-3 font-semibold">Result</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {sortedCandidates.map((row) => {
                      const resultLabel = row.result
                        ? title(row.result)
                        : row.match_status === "finished" ? "Finished" : title(row.match_status);
                      const score = row.home_goals != null && row.away_goals != null
                        ? `${row.home_goals}–${row.away_goals}`
                        : null;
                      return (
                        <tr key={row.prediction_id} className="hover:bg-slate-50/70 align-top">
                          <td data-label="Kickoff" className="px-4 py-2.5"><time dateTime={row.kickoff_at} className="font-mono text-sm tabular-nums text-slate-700 whitespace-nowrap">{localDateTime(row.kickoff_at)}</time></td>
                          <td data-label="Match" className="px-4 py-2.5"><b className="block text-slate-900">{row.home_team} vs {row.away_team}</b><small className="block text-sm text-slate-600">{row.competition || "Competition unavailable"}</small></td>
                          <td data-label="Market pick" className="px-4 py-2.5"><span className="inline-flex rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-sm font-semibold text-emerald-800">{title(row.market)}</span><small className="block mt-1 text-sm text-slate-600">{title(row.selection)}</small></td>
                          <td data-label="Odds" className="px-4 py-2.5"><b className="block font-mono font-bold tabular-nums text-slate-900">{row.odds.toFixed(2)}</b><small className="block text-sm text-slate-600">{row.bookmaker || "Bookmaker unavailable"}</small></td>
                          <td data-label="Q-score" className="px-4 py-2.5"><b className="block font-mono font-bold tabular-nums text-slate-900">{row.q_score.toFixed(1)}</b><small className="block text-sm text-slate-600">{row.q_grade}</small></td>
                          <td data-label="Historical and quote evidence" className="px-4 py-2.5">
                            <details>
                              <summary className={`inline-flex min-h-11 cursor-pointer items-center rounded-md px-2 py-2 text-sm font-semibold text-emerald-800 hover:bg-emerald-50 ${focusRing}`}>View evidence</summary>
                              <div className="mt-2 grid gap-1 text-sm leading-relaxed text-slate-700">
                                <span>Historical hit rate <b className="font-mono tabular-nums text-slate-900">{pct(row.market_hit_rate)}</b></span>
                                <span>Historical ROI <b className={`font-mono tabular-nums ${pnlClass(row.market_roi)}`}>{pct(row.market_roi)}</b></span>
                                <span>History <b className="font-mono tabular-nums text-slate-900">{row.market_sample_size} picks</b></span>
                                <span>Bookmaker <b className="text-slate-900">{row.bookmaker || "Unavailable"}</b></span>
                                <span>Quote saved <time dateTime={row.quote_at} className="font-mono tabular-nums text-slate-700">{localDateTime(row.quote_at)}</time></span>
                                <span>Quote age <b className="font-mono tabular-nums text-slate-900">{ageAtRefresh(row.quote_age_minutes)} at refresh</b></span>
                              </div>
                            </details>
                          </td>
                          <td data-label="Result" className="px-4 py-2.5">
                            <span className={`inline-flex rounded-full border px-2.5 py-1 text-sm font-semibold ${resultTone(row.result)}`}>{resultLabel}</span>
                            {score && <small className="block mt-1 font-mono text-sm tabular-nums text-slate-700">{score}</small>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
      <span className="block text-sm font-medium text-slate-600">{label}</span>
      <b className="mt-1 block font-mono text-lg font-bold tabular-nums text-slate-900">{value}</b>
    </div>
  );
}

function SortBtn({ active, dir, onClick, children }: { active: boolean; dir?: "asc" | "desc"; onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`inline-flex min-h-11 items-center rounded-md border px-3 py-2 text-sm font-semibold transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 ${active ? "border-emerald-300 bg-emerald-50 text-emerald-800" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"}`}
    >
      {children}{active ? (dir === "asc" ? " ↑" : " ↓") : ""}
    </button>
  );
}

function resultTone(result: "won" | "lost" | "void" | null) {
  if (result === "won") return "border-emerald-200 bg-emerald-50 text-emerald-800";
  if (result === "lost") return "border-red-200 bg-red-50 text-red-800";
  if (result === "void") return "border-amber-200 bg-amber-50 text-amber-900";
  return "border-slate-200 bg-slate-100 text-slate-700";
}
