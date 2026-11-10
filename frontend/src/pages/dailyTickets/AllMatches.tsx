import { useEffect, useRef, useState } from "react";
import type { SelectionSummary, BlockPerformance } from "../../lib/api";
import {
  formatKickoff,
  formatMarket,
  selectionRepeatsMarket,
  formatSelection,
  fetchBlockPerformance,
} from "../../lib/api";
import {
  gradeTone,
  matchDisplayState,
  matchStatusText,
  selectionStatusLabel,
  spreadLabel,
  spreadTone,
} from "./helpers";
import { BlockHeatmap } from "./BlockHeatmap";
import type { MatchDisplayState } from "./types";

type MatchSortKey = "match" | "kickoff" | "league" | "q" | "markets" | "spread" | "edge";
type OutcomeFilter = "" | "won" | "lost" | "void" | "pending";
type RecommendationFilter = "" | "BET" | "WATCH" | "PASS";

type SavedPreset = {
  id: string;
  name: string;
  saved_at: string;
  filters: Record<string, string>;
};

const PRESETS_STORAGE_KEY = "qwantej_picks_presets";

function loadSavedPresets(): SavedPreset[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(PRESETS_STORAGE_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((preset) => preset && preset.id && preset.name) : [];
  } catch {
    return [];
  }
}

function saveSavedPresets(presets: SavedPreset[]) {
  try {
    localStorage.setItem(PRESETS_STORAGE_KEY, JSON.stringify(presets));
  } catch {
    /* storage unavailable; presets just don't persist */
  }
}
const MATCH_STATUSES: MatchDisplayState[] = ["finished", "live", "scheduled", "postponed", "cancelled", "abandoned", "awarded"];
const MATCH_SORT_KEYS: MatchSortKey[] = ["match", "kickoff", "league", "q", "markets", "spread", "edge"];
const CHANCE_BLOCKS = [20, 30, 40, 50, 60, 70, 80, 90];

/** Bookmaker implied probability (margin included), as displayed per pick. */
function impliedProbability(row: SelectionSummary) {
  return row.source_implied_probability ?? row.avg_implied ?? Number.NaN;
}

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

type FilterDropdownOption = {
  value: string;
  text: string;
  /** Pick count shown as a coloured badge; 0 renders as a muted "no picks" and disables the option. */
  count?: number;
  disabled?: boolean;
};

function CountBadge({ count }: { count: number }) {
  if (count === 0) return <b className="picks-combo-count zero">no picks</b>;
  return <b className="picks-combo-count">{count} picks</b>;
}

function FilterDropdown({
  value,
  options,
  onChange,
  ariaLabel,
}: {
  value: string;
  options: FilterDropdownOption[];
  onChange: (value: string) => void;
  ariaLabel: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLUListElement>(null);
  const selected = options.find((option) => option.value === value) ?? options[0];
  useEffect(() => {
    if (!open) return;
    const handlePointer = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);
  const moveFocus = (current: HTMLElement, direction: 1 | -1) => {
    const items = [...(menuRef.current?.querySelectorAll<HTMLElement>("li") ?? [])];
    let index = items.indexOf(current) + direction;
    while (index >= 0 && index < items.length && items[index].getAttribute("aria-disabled") === "true") {
      index += direction;
    }
    items[Math.min(Math.max(index, 0), items.length - 1)]?.focus();
  };
  const selectOption = (option: FilterDropdownOption) => {
    if (option.disabled) return;
    onChange(option.value);
    setOpen(false);
    rootRef.current?.querySelector<HTMLButtonElement>(".picks-combo-toggle")?.focus();
  };
  const openMenu = () => {
    setOpen(true);
    requestAnimationFrame(() => {
      menuRef.current?.querySelector<HTMLElement>("li[aria-selected='true']")?.focus();
    });
  };
  return (
    <div className="picks-combo" ref={rootRef}>
      <button
        type="button"
        className="picks-combo-toggle"
        onClick={() => (open ? setOpen(false) : openMenu())}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={ariaLabel}
      >
        <span className="picks-combo-text"><b>{selected?.text}</b>{selected?.count != null && <CountBadge count={selected.count} />}</span>
        <span className="picks-combo-caret" aria-hidden="true">▾</span>
      </button>
      {open && (
        <ul className="picks-combo-menu" role="listbox" aria-label={ariaLabel} ref={menuRef}>
          {options.map((option) => (
            <li
              key={option.value}
              role="option"
              tabIndex={-1}
              aria-selected={option.value === value}
              aria-disabled={option.disabled || undefined}
              className={`${option.value === value ? "selected" : ""} ${option.disabled ? "disabled" : ""}`}
              onClick={() => selectOption(option)}
              onKeyDown={(event) => {
                if (event.key === "ArrowDown") { event.preventDefault(); moveFocus(event.currentTarget, 1); }
                else if (event.key === "ArrowUp") { event.preventDefault(); moveFocus(event.currentTarget, -1); }
                else if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectOption(option); }
              }}
            >
              <b>{option.text}</b>
              {option.count != null && <CountBadge count={option.count} />}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
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
  const [chanceMin, setChanceMin] = useState(() => matchUrlParam("chance") ?? "");
  const [impliedMin, setImpliedMin] = useState(() => matchUrlParam("implied") ?? "");
  const [edgeOnly, setEdgeOnly] = useState(() => matchUrlParam("sig_edge") === "1");
  const [freshOnly, setFreshOnly] = useState(() => matchUrlParam("sig_fresh") === "1");
  const [tightSpread, setTightSpread] = useState(() => matchUrlParam("sig_tight") === "1");
  const [clvOnly, setClvOnly] = useState(() => matchUrlParam("sig_clv") === "1");
  const [recFilter, setRecFilter] = useState(() => matchUrlParam("rec") ?? "");
  const [outcomeFilter, setOutcomeFilter] = useState<OutcomeFilter>(() => {
    const value = matchUrlParam("outcome") ?? "";
    return (["", "won", "lost", "void", "pending"].includes(value) ? value : "") as OutcomeFilter;
  });
  const [presets, setPresets] = useState<SavedPreset[]>(loadSavedPresets);
  const [presetName, setPresetName] = useState("");
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
      match_chance: chanceMin || null,
      match_implied: impliedMin || null,
      match_sig_edge: edgeOnly ? "1" : null,
      match_sig_fresh: freshOnly ? "1" : null,
      match_sig_tight: tightSpread ? "1" : null,
      match_sig_clv: clvOnly ? "1" : null,
      match_rec: recFilter || null,
      match_outcome: outcomeFilter || null,
      match_status: statusFilter === "all" ? null : statusFilter,
      match_sort: sort.key === "kickoff" && sort.direction === "asc" ? null : sort.key,
      match_order: sort.key === "kickoff" && sort.direction === "asc" ? null : sort.direction,
    };
    for (const [key, value] of Object.entries(params)) {
      if (value) url.searchParams.set(key, value);
      else url.searchParams.delete(key);
    }
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  }, [query, leagueFilter, marketFilter, chanceMin, impliedMin, edgeOnly, freshOnly, tightSpread, clvOnly, recFilter, outcomeFilter, statusFilter, sort]);
  const leagues = [...new Set(rows.map(([, selections]) => selections[0]?.competition).filter(Boolean))].sort();
  const markets = [...new Set(rows.flatMap(([, selections]) => selections.map((row) => formatMarket(row.market))))].sort();
  const marketCounts = rows.reduce<Record<string, number>>((counts, [, selections]) => {
    for (const market of new Set(selections.map((row) => formatMarket(row.market)))) {
      counts[market] = (counts[market] ?? 0) + 1;
    }
    return counts;
  }, {});
  const queryText = query.trim().toLocaleLowerCase();
  const chanceMinValue = chanceMin === "" ? null : Number(chanceMin);
  const impliedMinValue = impliedMin === "" ? null : Number(impliedMin);
  // A pick qualifies when it satisfies the market filter AND every active
  // chance/implied block AND every active signal toggle.
  const signalsPass = (row: SelectionSummary) => {
    if (edgeOnly && !(row.edge != null && Number.isFinite(row.edge) && row.edge > 0)) return false;
    if (freshOnly) {
      const state = quoteFreshness(row).state;
      if (state !== "fresh" && state !== "aging") return false;
    }
    if (tightSpread && !(row.model_agreement != null && Number.isFinite(row.model_agreement) && row.model_agreement <= 0.05)) return false;
    if (clvOnly && !(row.clv_percentage != null && Number.isFinite(row.clv_percentage) && row.clv_percentage > 0)) return false;
    if (recFilter && (row.recommendation_status ?? "WATCH") !== recFilter) return false;
    return true;
  };
  const rowMeetsFilters = (row: SelectionSummary) => {
    if (marketFilter !== "all" && formatMarket(row.market) !== marketFilter) return false;
    if (chanceMinValue != null && !(row.model_probability != null && Number.isFinite(row.model_probability) && row.model_probability >= chanceMinValue / 100)) return false;
    if (impliedMinValue != null) {
      const implied = impliedProbability(row);
      if (!(Number.isFinite(implied) && implied >= impliedMinValue / 100)) return false;
    }
    if (!signalsPass(row)) return false;
    return true;
  };
  const outcomeMatchesFilter = (row: SelectionSummary) => {
    if (!outcomeFilter) return true;
    if (outcomeFilter === "pending") return row.result == null;
    return row.result === outcomeFilter;
  };
  // Option counts for each block dropdown: picks matching the market filter
  // and the other active block, cumulative at each threshold.
  const chanceCounts: Record<number, number> = {};
  const impliedCounts: Record<number, number> = {};
  const recCounts: Record<string, number> = {};
  const outcomeCounts: Record<string, number> = {};
  for (const [, selections] of rows) {
    for (const row of selections) {
      if (marketFilter !== "all" && formatMarket(row.market) !== marketFilter) continue;
      const chance = row.model_probability;
      const chancePasses = chance != null && Number.isFinite(chance)
        && (chanceMinValue == null || chance >= chanceMinValue / 100);
      const implied = impliedProbability(row);
      const impliedPasses = Number.isFinite(implied)
        && (impliedMinValue == null || implied >= impliedMinValue / 100);
      if (chancePasses && impliedPasses) {
        for (const block of CHANCE_BLOCKS) {
          if (chance >= block / 100) chanceCounts[block] = (chanceCounts[block] ?? 0) + 1;
        }
      }
      if (impliedPasses && chancePasses) {
        for (const block of CHANCE_BLOCKS) {
          if (implied >= block / 100) impliedCounts[block] = (impliedCounts[block] ?? 0) + 1;
        }
      }
      if (chancePasses && impliedPasses && signalsPass(row)) {
        const recKey = row.recommendation_status ?? "WATCH";
        recCounts[recKey] = (recCounts[recKey] ?? 0) + 1;
        const outcomeKey = row.result ?? "pending";
        outcomeCounts[outcomeKey] = (outcomeCounts[outcomeKey] ?? 0) + 1;
      }
    }
  }
  const marketOptions: FilterDropdownOption[] = [
    { value: "all", text: "All markets" },
    ...markets.map((market) => ({ value: market, text: market, count: marketCounts[market] ?? 0 })),
  ];
  const chanceOptions: FilterDropdownOption[] = [
    { value: "", text: "Any" },
    ...CHANCE_BLOCKS.map((block) => ({ value: String(block), text: `≥ ${block}%`, count: chanceCounts[block] ?? 0, disabled: !chanceCounts[block] })),
  ];
  const impliedOptions: FilterDropdownOption[] = [
    { value: "", text: "Any" },
    ...CHANCE_BLOCKS.map((block) => ({ value: String(block), text: `≥ ${block}%`, count: impliedCounts[block] ?? 0, disabled: !impliedCounts[block] })),
  ];
  const discoveredRows = rows.flatMap(([id, selections]) => {
    const first = selections[0];
    const matchesText = !queryText || `${first.home_team} ${first.away_team} ${first.competition}`.toLocaleLowerCase().includes(queryText);
    const marketRows = selections.filter((row) => rowMeetsFilters(row) && outcomeMatchesFilter(row));
    if (!matchesText || (leagueFilter !== "all" && first.competition !== leagueFilter) || marketRows.length === 0) return [];
    return [[id, marketRows] as [number, SelectionSummary[]]];
  });
  const filteredRows = statusFilter === "all"
    ? discoveredRows
    : discoveredRows.filter(([, selections]) => matchDisplayState(selections[0]) === statusFilter);
  const activeFilterCount = Number(Boolean(query.trim()))
    + Number(leagueFilter !== "all")
    + Number(marketFilter !== "all")
    + Number(chanceMin !== "")
    + Number(impliedMin !== "")
    + Number(edgeOnly)
    + Number(freshOnly)
    + Number(tightSpread)
    + Number(clvOnly)
    + Number(recFilter !== "")
    + Number(outcomeFilter !== "")
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
  const matchedPickCount = filteredRows.reduce((sum, [, selections]) => sum + selections.length, 0);
  const netUnitsTone = filteredResultCounts.priced === 0 ? "muted"
    : filteredResultCounts.netUnits > 0 ? "won"
    : filteredResultCounts.netUnits < 0 ? "lost"
    : "";
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
    setChanceMin("");
    setImpliedMin("");
    setEdgeOnly(false);
    setFreshOnly(false);
    setTightSpread(false);
    setClvOnly(false);
    setRecFilter("");
    setOutcomeFilter("");
  };
  const applyPresetFilters = (filters: Record<string, string>) => {
    setQuery(filters.q ?? "");
    setLeagueFilter(filters.league ?? "all");
    setMarketFilter(filters.market ?? "all");
    setChanceMin(filters.chance ?? "");
    setImpliedMin(filters.implied ?? "");
    setEdgeOnly(filters.sig_edge === "1");
    setFreshOnly(filters.sig_fresh === "1");
    setTightSpread(filters.sig_tight === "1");
    setClvOnly(filters.sig_clv === "1");
    setRecFilter((["", "BET", "WATCH", "PASS"].includes(filters.rec ?? "") ? filters.rec : "") as RecommendationFilter);
    setOutcomeFilter((["", "won", "lost", "void", "pending"].includes(filters.outcome ?? "") ? filters.outcome : "") as OutcomeFilter);
    setStatusFilter((filters.status && MATCH_STATUSES.includes(filters.status as MatchDisplayState) ? filters.status : "all") as "all" | MatchDisplayState);
  };
  const savePreset = (name: string) => {
    const preset: SavedPreset = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      name,
      saved_at: new Date().toISOString(),
      filters: {
        q: query.trim(),
        league: leagueFilter,
        market: marketFilter,
        chance: chanceMin,
        implied: impliedMin,
        status: statusFilter,
        sig_edge: edgeOnly ? "1" : "",
        sig_fresh: freshOnly ? "1" : "",
        sig_tight: tightSpread ? "1" : "",
        sig_clv: clvOnly ? "1" : "",
        rec: recFilter,
        outcome: outcomeFilter,
      },
    };
    const next = [...presets, preset];
    setPresets(next);
    saveSavedPresets(next);
    setPresetName("");
  };
  const deletePreset = (id: string) => {
    const next = presets.filter((preset) => preset.id !== id);
    setPresets(next);
    saveSavedPresets(next);
  };
  const [perfOpen, setPerfOpen] = useState(false);
  const [perfDays, setPerfDays] = useState(60);
  const [performance, setPerformance] = useState<BlockPerformance | null>(null);
  const [perfLoading, setPerfLoading] = useState(false);
  const [perfError, setPerfError] = useState<string | null>(null);
  useEffect(() => {
    if (!perfOpen) return;
    if (performance && performance.window_days === perfDays) return;
    setPerfLoading(true);
    setPerfError(null);
    let cancelled = false;
    fetchBlockPerformance(perfDays)
      .then((data) => { if (!cancelled) setPerformance(data); })
      .catch((error) => { if (!cancelled) setPerfError(error.message ?? "Failed to load"); })
      .finally(() => { if (!cancelled) setPerfLoading(false); });
    return () => { cancelled = true; };
  }, [perfOpen, perfDays, performance]);
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
                <details className="picks-presets">
                  <summary className="picks-presets-toggle">
                    Presets{presets.length > 0 ? ` · ${presets.length}` : ""}
                  </summary>
                  <div className="picks-presets-menu">
                    <form
                      className="picks-presets-save"
                      onSubmit={(event) => {
                        event.preventDefault();
                        if (presetName.trim()) savePreset(presetName.trim());
                      }}
                    >
                      <input
                        value={presetName}
                        onChange={(event) => setPresetName(event.target.value)}
                        placeholder="Name this search…"
                        maxLength={40}
                        aria-label="Name for the current search filters"
                      />
                      <button type="submit" disabled={!presetName.trim()}>Save</button>
                    </form>
                    {presets.length === 0 ? (
                      <p className="picks-presets-empty">Save your best block combos to re-run them in one click.</p>
                    ) : presets.map((preset) => (
                      <div className="picks-presets-item" key={preset.id}>
                        <button
                          className="picks-presets-load"
                          onClick={(event) => {
                            event.preventDefault();
                            applyPresetFilters(preset.filters);
                            (event.currentTarget.closest("details.picks-presets") as HTMLDetailsElement | null)?.open && ((event.currentTarget.closest("details.picks-presets") as HTMLDetailsElement).open = false);
                          }}
                        >
                          {preset.name}
                        </button>
                        <button className="picks-presets-delete" aria-label={`Delete preset ${preset.name}`} onClick={() => deletePreset(preset.id)}>✕</button>
                      </div>
                    ))}
                  </div>
                </details>
                <button className="match-clear-filters" onClick={clearFilters} disabled={activeFilterCount === 0}>
                  Clear filters{activeFilterCount > 0 ? ` · ${activeFilterCount}` : ""}
                </button>
              </div>
            </div>
            <div className="picks-search-blocks-row">
              <span className="picks-row-label">Search blocks</span>
              <div className="picks-search-blocks-content">
                <span className="picks-block-caption" aria-hidden="true">Market</span>
                <FilterDropdown
                  value={marketFilter}
                  options={marketOptions}
                  onChange={setMarketFilter}
                  ariaLabel="Filter by market"
                />
                <span className="picks-block-caption" aria-hidden="true">Model chance</span>
                <FilterDropdown
                  value={chanceMin}
                  options={chanceOptions}
                  onChange={setChanceMin}
                  ariaLabel="Minimum model chance for picks"
                />
                <span className="picks-block-caption" aria-hidden="true">Bookmaker implied</span>
                <FilterDropdown
                  value={impliedMin}
                  options={impliedOptions}
                  onChange={setImpliedMin}
                  ariaLabel="Minimum bookmaker implied probability for picks"
                />
              </div>
            </div>
            <div className="picks-controls-row picks-signal-row">
              <span className="picks-row-label">Signals</span>
              <div className="match-status-filters" aria-label="Signal filters">
                <button className={edgeOnly ? "active" : ""} aria-pressed={edgeOnly} onClick={() => setEdgeOnly((value) => !value)}>
                  Positive edge
                </button>
                <button className={tightSpread ? "active" : ""} aria-pressed={tightSpread} onClick={() => setTightSpread((value) => !value)}>
                  Model aligned ≤5 pp
                </button>
                <button className={freshOnly ? "active" : ""} aria-pressed={freshOnly} onClick={() => setFreshOnly((value) => !value)}>
                  Fresh quotes ≤8 h
                </button>
                <button className={clvOnly ? "active" : ""} aria-pressed={clvOnly} onClick={() => setClvOnly((value) => !value)}>
                  Beat the close
                </button>
                <span className="picks-signal-divider" aria-hidden="true">|</span>
                <button className={`policy ${recFilter === "BET" ? "active" : ""}`} aria-pressed={recFilter === "BET"} onClick={() => setRecFilter((value) => (value === "BET" ? "" : "BET"))}>
                  BET <b>{recCounts.BET ?? 0}</b>
                </button>
                <button className={`policy ${recFilter === "WATCH" ? "active" : ""}`} aria-pressed={recFilter === "WATCH"} onClick={() => setRecFilter((value) => (value === "WATCH" ? "" : "WATCH"))}>
                  WATCH <b>{recCounts.WATCH ?? 0}</b>
                </button>
              </div>
            </div>
            <div className="picks-controls-row picks-outcome-row">
              <span className="picks-row-label">Outcome</span>
              <div className="match-status-filters" aria-label="Filter by settled outcome">
                <button className={outcomeFilter === "" ? "active" : ""} onClick={() => setOutcomeFilter("")}>
                  Any outcome <b>{Object.values(outcomeCounts).reduce((sum, count) => sum + count, 0)}</b>
                </button>
                <button className={`${outcomeFilter === "won" ? "active" : ""} finished`} disabled={!outcomeCounts.won} onClick={() => setOutcomeFilter("won")}>
                  Won <b>{outcomeCounts.won ?? 0}</b>
                </button>
                <button className={`${outcomeFilter === "lost" ? "active" : ""} live`} disabled={!outcomeCounts.lost} onClick={() => setOutcomeFilter("lost")}>
                  Lost <b>{outcomeCounts.lost ?? 0}</b>
                </button>
                <button className={outcomeFilter === "pending" ? "active" : ""} disabled={!outcomeCounts.pending} onClick={() => setOutcomeFilter("pending")}>
                  Pending <b>{outcomeCounts.pending ?? 0}</b>
                </button>
                <button className={outcomeFilter === "void" ? "active" : ""} disabled={!outcomeCounts.void} onClick={() => setOutcomeFilter("void")}>
                  Void <b>{outcomeCounts.void ?? 0}</b>
                </button>
              </div>
            </div>
          </div>

          <div className="picks-query-results" aria-live="polite">
            <div className="picks-overview-counts">
              <span><b>{sortedRows.length}</b> of <b>{rows.length}</b> matches shown</span>
              <span><b>{matchedPickCount}</b> of <b>{loadedSelections}</b> picks matched</span>
              <span><b>{loadedSelections}</b> of <b>{totalSelections}</b> picks loaded</span>
            </div>
            {filteredResults.length > 0 && (
              <div className="picks-outcome-strip" aria-label="Settled picks summary for this query">
                <strong>Settled picks in this view</strong>
                <span className="outcome"><small>Selections</small><b>{filteredResults.length}</b></span>
                <span className="outcome won"><small>Won</small><b>{filteredResultCounts.won}</b></span>
                <span className="outcome lost"><small>Lost</small><b>{filteredResultCounts.lost}</b></span>
                <span className="outcome"><small>Hit rate</small><b>{decidedCount > 0 ? `${((filteredResultCounts.won / decidedCount) * 100).toFixed(1)}%` : "—"}</b></span>
                <span className={`outcome ${netUnitsTone}`}><small>Net units</small><b>{filteredResultCounts.priced > 0 ? `${filteredResultCounts.netUnits >= 0 ? "+" : ""}${filteredResultCounts.netUnits.toFixed(2)}` : "—"}</b></span>
                <span className={`outcome ${netUnitsTone}`}><small>ROI</small><b>{filteredResultCounts.priced > 0 ? `${((filteredResultCounts.netUnits / filteredResultCounts.priced) * 100).toFixed(1)}%` : "—"}</b></span>
                <span className="outcome note"><small>{filteredResultCounts.matches.size} matches with settled picks · selected date only</small></span>
              </div>
            )}
            <p className="picks-overview-note">
              Q ≥75 selections only. Publication also applies price, edge, freshness, quality, and diversification gates.
            </p>
            {filteredResults.length > 0 && (
              <details className="picks-results-terms">
                <summary>How the settled numbers are computed</summary>
                <p>{filteredResultCounts.void} void picks excluded from hit rate and ROI. ROI assumes one unit per settled non-void pick with captured odds; priced picks: {filteredResultCounts.priced} of {decidedCount}. Net units and ROI exclude picks without valid captured odds. This one-date summary is not a strategy backtest or a profitability claim.</p>
              </details>
            )}
          </div>

          <details
            className="picks-heatmap"
            open={perfOpen}
            onToggle={(event) => setPerfOpen(event.currentTarget.open)}
          >
            <summary>Where winners came from · block performance, last {perfDays} days</summary>
            <BlockHeatmap
              performance={performance}
              loading={perfLoading}
              error={perfError}
              days={perfDays}
              onDaysChange={setPerfDays}
              onCell={(market, kind, block) => {
                setMarketFilter(formatMarket(market));
                if (kind === "chance") setChanceMin(String(block));
                else setImpliedMin(String(block));
              }}
            />
          </details>
          <div className="picks-list-head" aria-hidden="true">
            <span>Match</span>
            <span className="picks-list-stats"><span>Kickoff</span><span>Q-score</span><span>Markets</span><span>Odds</span><span>Spread</span></span>
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
          <span title={`Top pick: ${formatMarket(best.market)} · ${formatSelection(best.selection)}${best.source_bookmaker ? ` · ${best.source_bookmaker}` : ""}`}><small>Odds</small><b className="match-row-odds">{best.best_odds ? `${best.best_odds.toFixed(2)}×` : "—"}</b></span>
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
              <div className={row.clv_percentage != null && row.clv_percentage > 0 ? "positive" : undefined}>
                <dt>CLV</dt>
                <dd>{row.clv_percentage != null ? `${(row.clv_percentage * 100).toFixed(1)}%` : "—"}</dd>
                <small className="market-quote-meta">{row.closing_decimal_odds ? `Close ${row.closing_decimal_odds.toFixed(2)}×` : "No closing price yet"}</small>
              </div>
            </dl>
          </div>;
        })}
      </div>
    </details>
  );
}