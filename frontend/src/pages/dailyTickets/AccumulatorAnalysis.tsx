import { useEffect, useMemo, useRef, useState } from "react";
import { fetchAccaPrices, type AccaPrice, type SelectionSummary } from "../../lib/api";
import "./AccumulatorAnalysis.css";
import { selectionStatusLabel } from "./helpers";

type TicketBand = { key: string; title: string; min: number; max: number; hint: string };
type ScoredPick = { row: SelectionSummary; score: number; reasons: string[]; risks: string[] };
type Combo = { picks: ScoredPick[]; odds: number; score: number };

const BANDS: TicketBand[] = [
  { key: "steady", title: "5–10 odds", min: 5, max: 10, hint: "Moderate combined odds" },
  { key: "higher", title: "10–20 odds", min: 10, max: 20, hint: "Higher combined risk" },
  { key: "longshot", title: "20+ odds", min: 20, max: Number.POSITIVE_INFINITY, hint: "Longshot range" },
];

function ageHours(value?: string | null): number | null {
  if (!value) return null;
  const time = Date.parse(value);
  return Number.isFinite(time) ? Math.max(0, (Date.now() - time) / 3_600_000) : null;
}

function scoredPick(row: SelectionSummary): ScoredPick {
  const probability = row.model_probability;
  const odds = row.best_odds;
  const implied = odds && odds > 1 ? 1 / odds : null;
  const edge = row.edge;
  const age = ageHours(row.source_odds_at);
  const reasons: string[] = [];
  const risks: string[] = [];
  if (probability != null && implied != null) {
    const gap = probability - implied;
    reasons.push(`Model estimate ${(probability * 100).toFixed(1)}% vs quoted-price break-even ${(implied * 100).toFixed(1)}% (${gap >= 0 ? "+" : ""}${(gap * 100).toFixed(1)} percentage points).`);
  } else {
    reasons.push("A model probability or valid odds quote is missing, so the price comparison is incomplete.");
  }
  reasons.push(`Recommendation: ${row.recommendation_status ?? "unrated"}; Q-score ${Math.round(row.q_score)}/100${row.q_grade ? ` (${row.q_grade})` : ""}.`);
  if (row.model_agreement != null) reasons.push(`Model agreement ${(row.model_agreement * 100).toFixed(0)}%.`);
  if (row.source_bookmaker) reasons.push(`Odds source: ${row.source_bookmaker}${row.bookmaker_count ? `; ${row.bookmaker_count} bookmaker${row.bookmaker_count === 1 ? "" : "s"} recorded` : ""}.`);
  if (age != null) reasons.push(`Quote age: ${age < 1 ? `${Math.round(age * 60)} minutes` : `${age.toFixed(1)} hours`}.`);
  if (row.recommendation_risks?.length) risks.push(...row.recommendation_risks);
  if (row.recommendation_reasons?.length) reasons.push(...row.recommendation_reasons);
  if (row.data_quality_status && row.data_quality_status !== "good") risks.push(`Data quality is ${row.data_quality_status}${row.data_quality_score != null ? ` (${Math.round(row.data_quality_score)}/100)` : ""}.`);
  if (age == null) risks.push("Odds quote time is unavailable.");
  else if (age > 2) risks.push("Odds quote is older than two hours.");
  if ((row.model_agreement ?? 0) < 0.6) risks.push("Model agreement is below 60% or unavailable.");
  if (row.match_status && row.match_status.toLowerCase() !== "scheduled") risks.push(`Fixture status is ${row.match_status}.`);
  if (edge != null && edge <= 0) risks.push("No positive model edge is recorded against the quoted price.");
  const score = Math.max(0, Math.min(100,
    (row.recommendation_status === "BET" ? 35 : row.recommendation_status === "WATCH" ? 18 : 0) +
    Math.max(0, Math.min(20, row.q_score / 5)) +
    Math.max(0, Math.min(20, (edge ?? 0) * 200)) +
    Math.max(0, Math.min(10, (row.model_agreement ?? 0) * 10)) +
    (row.data_quality_status === "good" ? 10 : 0) +
    (age != null && age <= 2 ? 5 : 0),
  ));
  return { row, score, reasons, risks: [...new Set(risks)] };
}

function findCombo(pool: ScoredPick[], band: TicketBand, usedMatches: Set<number>): Combo | null {
  const candidates = pool.filter(({ row }) => !usedMatches.has(row.match_id)).slice(0, 36);
  let beam: ScoredPick[][] = [[]];
  let best: Combo | null = null;
  for (let size = 1; size <= 8; size += 1) {
    const next: ScoredPick[][] = [];
    for (const partial of beam) {
      const start = partial.length ? candidates.indexOf(partial[partial.length - 1]) + 1 : 0;
      for (let i = start; i < candidates.length; i += 1) {
        const pick = candidates[i];
        if (partial.some((item) => item.row.match_id === pick.row.match_id)) continue;
        const combo = [...partial, pick];
        const odds = combo.reduce((product, item) => product * (item.row.best_odds ?? 1), 1);
        if (odds > band.max) continue;
        next.push(combo);
      }
    }
    next.sort((a, b) => b.reduce((sum, item) => sum + item.score, 0) / b.length - a.reduce((sum, item) => sum + item.score, 0) / a.length);
    beam = next.slice(0, 500);
    for (const picks of beam) {
      const odds = picks.reduce((product, item) => product * (item.row.best_odds ?? 1), 1);
      if (odds < band.min) continue;
      const average = picks.reduce((sum, item) => sum + item.score, 0) / picks.length;
      const score = average - (picks.length - 1) * 0.2;
      if (!best || score > best.score) best = { picks, odds, score };
    }
    if (beam.length === 0) break;
  }
  return best;
}

function marketName(value: string) {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function marketSelectionLabel(market: string, selection: string) {
  const normalize = (value: string) => value.toLowerCase().replace(/[\s-]+/g, "_");
  const selectionKey = normalize(selection);
  const marketKey = normalize(market);
  const describeCode = (value: string) => {
    const known: Record<string, string> = {
      home_win: "Home win",
      away_win: "Away win",
      draw: "Draw",
      btts_yes: "Both teams to score: Yes",
      btts_no: "Both teams to score: No",
      double_chance_1x: "Double chance: Home or draw",
      double_chance_x2: "Double chance: Draw or away",
      double_chance_12: "Double chance: Home or away",
    };
    if (known[value]) return known[value];
    const totalGoals = value.match(/^(over|under)_?(\d+(?:[._]\d+)?)$/);
    if (totalGoals) return `${totalGoals[1] === "over" ? "Over" : "Under"} ${totalGoals[2].replace("_", ".")} goals`;
    return null;
  };
  const marketDescription = describeCode(marketKey);
  const selectionDescription = describeCode(selectionKey);
  if (marketDescription && (marketKey === selectionKey || selectionKey.startsWith(`${marketKey}_`))) return marketDescription;
  if (selectionDescription) return selectionDescription;
  const marketLabels: Record<string, string> = {
    btts: "Both teams to score",
    double_chance: "Double chance",
    match_result: "Match result",
    "1x2": "Match result",
    total_goals: "Total goals",
  };
  const readableMarket = marketLabels[marketKey] ?? marketName(market);
  if (selectionKey === marketKey) return readableMarket;
  if ((selectionKey === "yes" || selectionKey === "no") && (marketKey === "btts" || marketKey === "btts_yes" || marketKey === "btts_no")) {
    return `Both teams to score: ${selectionKey === "yes" || marketKey === "btts_yes" ? "Yes" : "No"}`;
  }
  return `${readableMarket}: ${marketName(selection)}`;
}

export function AccumulatorAnalysis({ rows, date }: { rows: SelectionSummary[]; date: string }) {
  const [pricing, setPricing] = useState<{ date: string; prices: AccaPrice[] } | null>(null);
  const [priceError, setPriceError] = useState<string | null>(null);
  const [activeAnalysis, setActiveAnalysis] = useState<ScoredPick | null>(null);
  const [marketFilter, setMarketFilter] = useState("all");
  const [modelFilter, setModelFilter] = useState("all");
  const [qScoreFilter, setQScoreFilter] = useState("all");
  const analysisDialogRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (activeAnalysis) analysisDialogRef.current?.focus();
  }, [activeAnalysis]);
  useEffect(() => {
    const controller = new AbortController();
    setPricing(null);
    setPriceError(null);
    fetchAccaPrices(date, controller.signal).then((prices) => {
      if (!controller.signal.aborted) setPricing({ date, prices });
    }).catch((error: Error) => {
      if (!controller.signal.aborted) setPriceError(error.message);
    });
    return () => controller.abort();
  }, [date, rows]);
  const picks = useMemo(() => rows.map((original) => {
    const quote = pricing?.date === date ? pricing.prices.find((price) =>
      price.match_id === original.match_id && price.market === original.market && price.selection === original.selection) : undefined;
    const row: SelectionSummary = {
      ...original,
      best_odds: quote?.decimal_odds ?? null,
      source_bookmaker: quote?.bookmaker ?? null,
      source_odds_at: quote?.fetched_at ?? null,
      bookmaker_count: null,
      edge: quote && original.model_probability != null ? original.model_probability - 1 / quote.decimal_odds : null,
      recommendation_reasons: original.recommendation_reasons?.map((reason) => `Original model assessment: ${reason}`),
    };
    const pick = scoredPick(row);
    if (quote?.pricing_mode === "closest_observed") {
      pick.reasons.push(`Betway unavailable: ${quote.bookmaker} is the closest observed alternative across ${quote.comparison_fixtures} other fixtures in this market (median price difference ${((quote.median_relative_gap ?? 0) * 100).toFixed(1)}%).`);
    } else if (quote?.pricing_mode === "market_reference") {
      pick.risks.push("Betway similarity is unverified: using the available quote nearest the market median.");
    } else if (!quote) {
      pick.risks.push("No fresh bookmaker quote is available.");
    }
    return pick;
  }).sort((a, b) => b.score - a.score), [rows, pricing, date]);
  const marketOptions = useMemo(() => [...new Map(picks.map(({ row }) => {
    const key = JSON.stringify([row.market, row.selection]);
    return [key, marketSelectionLabel(row.market, row.selection)] as const;
  })).entries()].sort((a, b) => a[1].localeCompare(b[1])), [picks]);
  const tablePicks = useMemo(() => picks.filter(({ row }) => {
    if (marketFilter !== "all" && JSON.stringify([row.market, row.selection]) !== marketFilter) return false;
    if (qScoreFilter !== "all" && Math.min(90, Math.floor(row.q_score / 10) * 10) !== Number(qScoreFilter)) return false;
    if (modelFilter !== "all" && (row.model_probability == null || row.model_probability * 100 < Number(modelFilter))) return false;
    return true;
  }), [picks, marketFilter, modelFilter, qScoreFilter]);
  const tickets = useMemo(() => {
    const used = new Set<number>();
    return BANDS.map((band) => {
      const eligible = picks.filter(({ row }) => {
        const age = ageHours(row.source_odds_at);
        return row.recommendation_status === "BET" && row.best_odds != null && row.best_odds > 1 &&
          row.data_quality_status === "good" && age != null && age <= 2 && (row.edge ?? 0) > 0 &&
          Date.parse(row.kickoff_at) > Date.now() &&
          row.match_status?.toLowerCase() === "scheduled" && !used.has(row.match_id);
      });
      const combo = findCombo(eligible, band, used);
      combo?.picks.forEach(({ row }) => used.add(row.match_id));
      return { band, combo };
    });
  }, [picks]);

  return <section className="acca-analysis">
    <header className="acca-analysis__heading">
      <div><span className="eyebrow">Evidence review</span><h2>Accumulator analysis</h2>
        <p>Review each candidate’s model estimate, quoted price, edge, model agreement and data risks. Ticket suggestions use current BET-rated picks with fresh odds and good data quality.</p>
      </div><span className="acca-analysis__date">{date} · {picks.length} candidate picks</span>
    </header>
    <div className="acca-analysis__notice">Betway first; otherwise the closest observed bookmaker across at least three comparable fixtures. Without enough Betway comparisons, use the available price nearest the market median and mark Betway similarity unverified. Original model ratings remain unchanged; displayed edge uses the selected price. Indicative research only: mixed-bookmaker combined odds may not be available as one ticket, and bookmaker margin remains.</div>
    {priceError ? <p role="alert">{priceError}</p> : pricing?.date !== date && <p role="status">Loading Betway and comparison prices…</p>}
    <div className="acca-analysis__tickets">
      {tickets.map(({ band, combo }) => <article className="acca-analysis__ticket" key={band.key}>
        <div className="acca-analysis__ticket-head"><div><h3>{band.title}</h3><span>{band.hint}</span></div>
          <strong>{combo ? `${combo.odds.toFixed(2)}×` : "No eligible ticket"}</strong></div>
        {combo ? <ol>{combo.picks.map(({ row, score, risks }) => <li key={row.prediction_id}>
          <div><b>{row.home_team} vs {row.away_team}</b><span>{marketName(row.market)} · {row.selection} · {row.best_odds?.toFixed(2)}</span></div>
          <small>{row.source_bookmaker} · Pick score {score.toFixed(0)}/100{risks.length ? ` · ${risks.length} risk flag${risks.length === 1 ? "" : "s"}` : " · no listed risk flags"}</small>
        </li>)}</ol> : <p className="acca-analysis__empty">There are not enough eligible picks in this odds band. The module leaves it empty rather than relaxing the evidence gates.</p>}
      </article>)}
    </div>
    <div className="acca-analysis__filters" aria-label="Filter analysis table">
      <label>Market selection
        <select value={marketFilter} onChange={(event) => setMarketFilter(event.target.value)}>
          <option value="all">All market selections</option>
          {marketOptions.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select>
      </label>
      <label>Model probability
        <select value={modelFilter} onChange={(event) => setModelFilter(event.target.value)}>
          <option value="all">All model probabilities</option>
          {Array.from({ length: 9 }, (_, index) => (index + 1) * 10).map((threshold) => <option key={`model:${threshold}`} value={threshold}>{`\u2265 ${threshold}%`}</option>)}
        </select>
      </label>
      <label>Q-Score
        <select value={qScoreFilter} onChange={(event) => setQScoreFilter(event.target.value)}>
          <option value="all">All Q-Scores</option>
          {Array.from({ length: 10 }, (_, index) => index * 10).map((lower) => <option key={`q-score:${lower}`} value={lower}>{lower}–{lower === 90 ? 100 : `${lower + 9}.9`} points</option>)}
        </select>
      </label>
      <span className="acca-analysis__filter-count" aria-live="polite">Showing {tablePicks.length} of {picks.length}</span>
    </div>
    <div className="acca-analysis__table-wrap"><table className="acca-analysis__table"><thead><tr><th>Fixture</th><th>Market selection</th><th>Price / implied</th><th>Model / edge</th><th>Quality</th><th>Match status</th><th>Analysis</th></tr></thead>
      <tbody>{tablePicks.map(({ row, score, reasons, risks }) => <tr key={row.prediction_id}>
        <td><b>{row.home_team} vs {row.away_team}</b><span>{row.competition}</span></td>
        <td><b>{marketName(row.market)}</b></td>
        <td>{row.best_odds?.toFixed(2) ?? "—"}<span>{row.best_odds && row.best_odds > 1 ? `${(100 / row.best_odds).toFixed(1)}% break-even` : "No valid price"}</span></td>
        <td>{row.model_probability != null ? `${(row.model_probability * 100).toFixed(1)}%` : "—"}<span>{row.edge != null ? `${row.edge >= 0 ? "+" : ""}${(row.edge * 100).toFixed(1)} pp edge` : "Edge unavailable"}</span></td>
        <td><b>{row.recommendation_status ?? "Unrated"}</b><span>Q {Math.round(row.q_score)} · score {score.toFixed(0)}</span></td>
        <td><span className={`acca-analysis__status acca-analysis__status--${row.result ?? "pending"}`}>
          {row.result
            ? `${selectionStatusLabel(row.result)}${row.home_goals != null && row.away_goals != null ? ` (${row.home_goals}-${row.away_goals})` : ""}`
            : "Pending"}
        </span></td>
        <td><button type="button" className="acca-analysis__details-button" onClick={() => setActiveAnalysis({ row, score, reasons, risks })}>View analysis</button></td>
      </tr>)}</tbody></table>
      {tablePicks.length === 0 && <p className="acca-analysis__empty">{picks.length === 0 ? "No candidate picks are available for this date." : "No rows match these filters. Adjust a filter to see more candidates."}</p>}
    </div>
    {activeAnalysis && <div className="acca-analysis__dialog-backdrop" onClick={(event) => { if (event.target === event.currentTarget) setActiveAnalysis(null); }}>
      <section ref={analysisDialogRef} className="acca-analysis__dialog" role="dialog" aria-modal="true" aria-labelledby="acca-analysis-dialog-title" onKeyDown={(event) => { if (event.key === "Escape") setActiveAnalysis(null); }} tabIndex={-1}>
        <header className="acca-analysis__dialog-header">
          <div><span className="eyebrow">Analysis and risks</span><h3 id="acca-analysis-dialog-title">{activeAnalysis.row.home_team} vs {activeAnalysis.row.away_team}</h3>
            <p>{activeAnalysis.row.competition} · {marketName(activeAnalysis.row.market)}: {activeAnalysis.row.selection}</p></div>
          <button type="button" className="acca-analysis__dialog-close" aria-label="Close analysis" onClick={() => setActiveAnalysis(null)}>×</button>
        </header>
        <div className="acca-analysis__dialog-content">
          <div><h4>Analysis</h4><p>{activeAnalysis.reasons.join(" ")}</p></div>
          <div><h4>Risks</h4>{activeAnalysis.risks.length ? <ul>{activeAnalysis.risks.map((risk) => <li key={risk}>{risk}</li>)}</ul> : <p>No listed risk flags.</p>}</div>
        </div>
        <footer className="acca-analysis__dialog-footer"><button type="button" className="acca-analysis__details-button" onClick={() => setActiveAnalysis(null)}>Close</button></footer>
      </section>
    </div>}
  </section>;
}
