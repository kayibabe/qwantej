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
import {
  ALL_BAND_MIX_PAIRS,
  BAND_MIX_LABEL,
  BAND_MIX_PAIRS,
  bandMixPairLabel,
  encodeBandMixPairs,
  impliedProbability,
  matchesBandMix,
  parseBandMixPairs,
} from "./bandMix";

// Re-exported so existing filter links/tests keep importing from this module.
export { encodeBandMixPairs, matchesBandMix, parseBandMixPairs } from "./bandMix";

type MatchSortKey = "match" | "kickoff" | "league" | "q" | "fair" | "markets" | "spread" | "edge";
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
const MATCH_SORT_KEYS: MatchSortKey[] = ["match", "kickoff", "league", "q", "fair", "markets", "spread", "edge"];
const CHANCE_BLOCKS = [20, 30, 40, 50, 60, 70, 80, 90];

const chipBase = "inline-flex min-h-11 items-center justify-center rounded-md px-3 py-1.5 text-sm font-medium leading-normal transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed";
const chipInactive = "bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-900";
const chipActive = "bg-emerald-700 text-white";
const inputBase = "h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 placeholder:text-slate-600 focus:border-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-700";

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
  if (count === 0) return <b className="picks-combo-count zero ml-auto rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-sm font-semibold text-slate-600">no picks</b>;
  return <b className="picks-combo-count ml-auto rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-sm font-semibold font-mono tabular-nums text-emerald-700">{count} picks</b>;
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
    <div className="picks-combo relative" ref={rootRef}>
      <button
        type="button"
        className="picks-combo-toggle inline-flex h-11 min-w-[11rem] items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-left text-sm text-slate-900 hover:bg-slate-50 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
        onClick={() => (open ? setOpen(false) : openMenu())}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={ariaLabel}
      >
        <span className="picks-combo-text flex min-w-0 flex-1 items-center gap-2"><b className="truncate font-medium">{selected?.text}</b>{selected?.count != null && <CountBadge count={selected.count} />}</span>
        <span className="picks-combo-caret text-slate-600" aria-hidden="true">▾</span>
      </button>
      {open && (
        <ul className="picks-combo-menu absolute z-30 mt-1 max-h-72 w-full min-w-[14rem] overflow-auto rounded-lg border border-slate-200 bg-white p-1 shadow-lg" role="listbox" aria-label={ariaLabel} ref={menuRef}>
          {options.map((option) => (
            <li
              key={option.value}
              role="option"
              tabIndex={-1}
              aria-selected={option.value === value}
              aria-disabled={option.disabled || undefined}
              className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-sm leading-normal text-slate-700 hover:bg-slate-50 focus:bg-slate-50 focus:outline-2 focus:outline-offset-2 focus:outline-emerald-700 ${option.value === value ? "selected bg-emerald-50 text-emerald-800" : ""} ${option.disabled ? "disabled cursor-not-allowed opacity-50" : ""}`}
              onClick={() => selectOption(option)}
              onKeyDown={(event) => {
                if (event.key === "ArrowDown") { event.preventDefault(); moveFocus(event.currentTarget, 1); }
                else if (event.key === "ArrowUp") { event.preventDefault(); moveFocus(event.currentTarget, -1); }
                else if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectOption(option); }
              }}
            >
              <b className="font-medium">{option.text}</b>
              {option.count != null && <CountBadge count={option.count} />}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** One-click on/off plus an independent checkbox for each of the five pairs. */
function BandMixPicker({
  selectedPairs,
  count,
  label,
  onToggleAll,
  onTogglePair,
  onSelectAll,
  onClearAll,
}: {
  selectedPairs: number[];
  count: number;
  label: string;
  onToggleAll: () => void;
  onTogglePair: (index: number) => void;
  onSelectAll: () => void;
  onClearAll: () => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const on = selectedPairs.length > 0;
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
  return (
    <div className="picks-band-mix-control relative inline-flex" ref={rootRef}>
      <button
        type="button"
        className={`picks-band-mix inline-flex min-h-11 items-center gap-1.5 rounded-l-lg border px-3 py-2 text-sm font-semibold transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 ${on ? "active border-emerald-700 bg-emerald-700 text-white" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"}`}
        aria-pressed={on}
        title={`One-click daily filter — any selected pair: ${label}`}
        onClick={onToggleAll}
      >
        ⚡ Band mix <b className={`font-mono tabular-nums ${on ? "text-emerald-100" : "text-slate-900"}`}>{count}</b>
      </button>
      <button
        type="button"
        className={`picks-band-mix-caret inline-flex min-h-11 min-w-11 items-center justify-center rounded-r-lg border border-l-0 px-2 py-2 text-sm transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 ${on ? "border-emerald-700 bg-emerald-700 text-white hover:bg-emerald-800" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"}`}
        aria-label="Choose band mix pairs"
        aria-expanded={open}
        title="Choose band mix pairs"
        onClick={() => setOpen((value) => !value)}
      >
        ▾
      </button>
      {open && (
        <div className="picks-band-mix-options absolute right-0 top-full z-30 mt-1 w-64 rounded-xl border border-slate-200 bg-white p-3 shadow-lg" role="group" aria-label="Band mix pairs">
          <p className="picks-band-mix-options-title mb-2 text-sm leading-relaxed text-slate-600">Show matches with <b className="font-semibold text-slate-700">any</b> selected pair</p>
          {BAND_MIX_PAIRS.map(([model, market], index) => (
            <label className="picks-band-mix-option flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-1.5 py-1.5 text-sm text-slate-700 hover:bg-slate-50" key={`${model}-${market}`}>
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-slate-300 text-emerald-700 focus:ring-emerald-700/30"
                checked={selectedPairs.includes(index)}
                onChange={() => onTogglePair(index)}
              />
              <span className="font-mono tabular-nums">{model}% × {market}%</span>
            </label>
          ))}
          <div className="picks-band-mix-actions mt-2 flex gap-2 border-t border-slate-100 pt-2">
            <button type="button" className="inline-flex min-h-11 items-center rounded-md px-2 text-sm font-semibold text-emerald-800 hover:bg-emerald-50 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={onSelectAll}>All</button>
            <button type="button" className="inline-flex min-h-11 items-center rounded-md px-2 text-sm font-semibold text-slate-600 hover:bg-slate-100 hover:text-slate-900 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={onClearAll}>None</button>
          </div>
        </div>
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
  focusMatchId = null,
  focusLabel = null,
  onClearFocus,
  onBandMixChange,
}: {
  rows: [number, SelectionSummary[]][];
  totalSelections?: number;
  loadedSelections?: number;
  loadingMore?: boolean;
  onLoadMore?: () => void;
  onSelect: (row: SelectionSummary) => void;
  /** Set from a fixture badge; narrows the list to that one fixture. */
  focusMatchId?: number | null;
  /** Team names for the focused fixture, so the chip shows even before its picks load. */
  focusLabel?: string | null;
  onClearFocus?: () => void;
  /** Notifies the page so it can reload picks without the Q>=75 gate while band mix is on. */
  onBandMixChange?: (pairs: number[]) => void;
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
  const [bandMixPairs, setBandMixPairs] = useState<number[]>(() => parseBandMixPairs(matchUrlParam("band_mix")));
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
  const bandMixOn = bandMixPairs.length > 0;
  const selectedBandMixLabel = bandMixPairs.map(bandMixPairLabel).join(" · ");
  const setBandMixSelection = (pairs: number[]) => {
    // Thresholds would silently exclude the low-probability pairs.
    if (pairs.length > 0) {
      setChanceMin("");
      setImpliedMin("");
    }
    setBandMixPairs(pairs);
    onBandMixChange?.(pairs);
  };
  const toggleBandMixPair = (index: number) => {
    const next = bandMixPairs.includes(index)
      ? bandMixPairs.filter((item) => item !== index)
      : [...bandMixPairs, index].sort((left, right) => left - right);
    setBandMixSelection(next);
  };
  useEffect(() => {
    const url = new URL(window.location.href);
    const params: Record<string, string | null> = {
      match_q: query.trim() || null,
      match_league: leagueFilter === "all" ? null : leagueFilter,
      match_market: marketFilter === "all" ? null : marketFilter,
      match_chance: chanceMin || null,
      match_implied: impliedMin || null,
      match_band_mix: bandMixOn ? encodeBandMixPairs(bandMixPairs) : null,
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
  }, [query, leagueFilter, marketFilter, chanceMin, impliedMin, bandMixPairs, edgeOnly, freshOnly, tightSpread, clvOnly, recFilter, outcomeFilter, statusFilter, sort]);
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
    if (bandMixOn && !matchesBandMix(row, bandMixPairs)) return false;
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
    if (focusMatchId != null && id !== focusMatchId) return [];
    const first = selections[0];
    const matchesText = !queryText || `${first.home_team} ${first.away_team} ${first.competition}`.toLocaleLowerCase().includes(queryText);
    const marketRows = selections.filter((row) => rowMeetsFilters(row) && outcomeMatchesFilter(row));
    if (!matchesText || (leagueFilter !== "all" && first.competition !== leagueFilter) || marketRows.length === 0) return [];
    return [[id, marketRows] as [number, SelectionSummary[]]];
  });
  const filteredRows = statusFilter === "all"
    ? discoveredRows
    : discoveredRows.filter(([, selections]) => matchDisplayState(selections[0]) === statusFilter);
  const bandMixMatchCount = rows.filter(([, selections]) => selections.some((row) => matchesBandMix(row, bandMixOn ? bandMixPairs : ALL_BAND_MIX_PAIRS))).length;
  const activeFilterCount = Number(focusMatchId != null)
    + Number(Boolean(query.trim()))
    + Number(leagueFilter !== "all")
    + Number(marketFilter !== "all")
    + Number(chanceMin !== "")
    + Number(impliedMin !== "")
    + Number(bandMixOn)
    + Number(edgeOnly)
    + Number(freshOnly)
    + Number(tightSpread)
    + Number(clvOnly)
    + Number(recFilter !== "")
    + Number(outcomeFilter !== "")
    + Number(statusFilter !== "all");
  const activeFilterLabels = [
    focusMatchId != null && "Fixture focus",
    query.trim() && `Search “${query.trim()}”`,
    leagueFilter !== "all" && `Competition: ${leagueFilter}`,
    marketFilter !== "all" && `Market: ${marketFilter}`,
    chanceMin && `Model chance ≥ ${chanceMin}%`,
    impliedMin && `Implied probability ≥ ${impliedMin}%`,
    bandMixOn && `Band mix: ${selectedBandMixLabel}`,
    edgeOnly && "Positive edge",
    freshOnly && "Fresh quotes ≤8 h",
    tightSpread && "Model aligned ≤5 pp",
    clvOnly && "Beat the close",
    recFilter && `Recommendation: ${recFilter}`,
    outcomeFilter && `Outcome: ${outcomeFilter}`,
    statusFilter !== "all" && `Status: ${statusFilter}`,
  ].filter((label): label is string => Boolean(label));
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
        // Opt-in market order: de-vigged (fair) probability, not the default.
        fair: [
          Math.max(...a.map((row) => row.source_fair_probability ?? -1)),
          Math.max(...b.map((row) => row.source_fair_probability ?? -1)),
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
  const netUnitsTone = filteredResultCounts.priced === 0 ? "text-slate-600"
    : filteredResultCounts.netUnits > 0 ? "text-emerald-700"
    : filteredResultCounts.netUnits < 0 ? "text-red-600"
    : "text-slate-600";
  const changeSort = (key: MatchSortKey) =>
    setSort((current) =>
      current.key === key
        ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
        : { key, direction: key === "kickoff" ? "asc" : "desc" },
    );
  const clearFilters = () => {
    onClearFocus?.();
    setStatusFilter("all");
    setQuery("");
    setLeagueFilter("all");
    setMarketFilter("all");
    setChanceMin("");
    setImpliedMin("");
    setBandMixSelection([]);
    setEdgeOnly(false);
    setFreshOnly(false);
    setTightSpread(false);
    setClvOnly(false);
    setRecFilter("");
    setOutcomeFilter("");
  };
  const applyPresetFilters = (filters: Record<string, string>) => {
    const presetPairs = parseBandMixPairs(filters.band_mix_pairs ?? (filters.band_mix === "1" ? "1" : ""));
    setQuery(filters.q ?? "");
    setLeagueFilter(filters.league ?? "all");
    setMarketFilter(filters.market ?? "all");
    setChanceMin(presetPairs.length > 0 ? "" : (filters.chance ?? ""));
    setImpliedMin(presetPairs.length > 0 ? "" : (filters.implied ?? ""));
    setBandMixSelection(presetPairs);
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
        band_mix: bandMixOn ? "1" : "",
        band_mix_pairs: bandMixOn ? encodeBandMixPairs(bandMixPairs) : "",
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
      type="button"
      className={`${chipBase} ${statusFilter === key ? chipActive : chipInactive} ${key}`}
      onClick={() => setStatusFilter(key)}
      aria-pressed={statusFilter === key}
      disabled={count === 0 && statusFilter !== key}
    >
      {label} <b className="font-mono tabular-nums">{count}</b>
    </button>
  );

   return (
    <section className="selection-panel all-matches-panel system-picks-panel rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      {rows.length === 0 ? (
        <p className="panel-empty px-4 py-10 text-center text-sm text-slate-600 sm:px-5">
          {bandMixOn
            ? "No band-mix selections are available for this date (Q gate off)."
            : "No Q ≥75 system picks are available for this date."}
        </p>
      ) : (
        <>
          {focusMatchId != null && focusLabel && (
            <div className="picks-focus-chip flex flex-wrap items-center justify-between gap-2 border-b border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm text-emerald-900 sm:px-5" role="status">
              <span>Showing picks for <b className="font-semibold">{focusLabel}</b></span>
              <button type="button" className="inline-flex min-h-11 items-center gap-1 rounded-lg border border-emerald-200 bg-white px-2.5 py-1 text-sm font-semibold text-emerald-800 hover:bg-emerald-100 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={() => onClearFocus?.()} aria-label="Clear the fixture focus">✕ Clear</button>
            </div>
          )}
          <div className="picks-controls space-y-4 border-b border-slate-200 bg-slate-50/70 px-4 py-4 sm:px-5">
            <div className="picks-controls-row picks-controls-search grid gap-3 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto]">
              <label className="picks-field picks-search block">
                <span className="mb-1.5 block text-sm font-semibold text-slate-600">Search</span>
                <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Team or competition" className={inputBase} />
              </label>
              <label className="picks-field block">
                <span className="mb-1.5 block text-sm font-semibold text-slate-600">Competition</span>
                <select value={leagueFilter} onChange={(event) => setLeagueFilter(event.target.value)} className={inputBase}>
                  <option value="all">All competitions</option>
                  {leagues.map((league) => <option key={league} value={league}>{league}</option>)}
                </select>
              </label>
              <div className="picks-sort-group flex items-end gap-2">
                <label className="picks-field block flex-1">
                  <span className="mb-1.5 block text-sm font-semibold text-slate-600">Sort by</span>
                  <select aria-label="Sort matches" value={sort.key} onChange={(event) => changeSort(event.target.value as MatchSortKey)} className={inputBase}>
                    <option value="kickoff">Kickoff</option><option value="match">Match</option><option value="league">Competition</option>
                    <option value="q">Q-score</option><option value="fair">Market probability (no-vig)</option><option value="markets">Markets</option><option value="spread">Model agreement</option><option value="edge">Model edge</option>
                  </select>
                </label>
                <button
                  className="picks-sort-direction h-11 shrink-0 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
                  type="button"
                  onClick={() => setSort((current) => ({ ...current, direction: current.direction === "asc" ? "desc" : "asc" }))}
                  title={`Sort ${sort.direction === "asc" ? "descending" : "ascending"}`}
                >
                  {sort.direction === "asc" ? "Asc ↑" : "Desc ↓"}
                </button>
              </div>
            </div>

            <div className="picks-controls-row picks-controls-filter flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
              <div className="match-status-filters flex flex-wrap gap-1.5" aria-label="Filter matches by status">
                {filterButton("all", "All", discoveredRows.length)}
                {(statusCounts.finished > 0 || statusFilter === "finished") && filterButton("finished", "Finished", statusCounts.finished)}
                {(statusCounts.live > 0 || statusFilter === "live") && filterButton("live", "In play", statusCounts.live)}
                {(statusCounts.scheduled > 0 || statusFilter === "scheduled") && filterButton("scheduled", "Upcoming", statusCounts.scheduled)}
                {(statusCounts.postponed > 0 || statusFilter === "postponed") && filterButton("postponed", "Postponed", statusCounts.postponed)}
                {(statusCounts.cancelled > 0 || statusFilter === "cancelled") && filterButton("cancelled", "Cancelled", statusCounts.cancelled)}
                {(statusCounts.abandoned > 0 || statusFilter === "abandoned") && filterButton("abandoned", "Abandoned · review", statusCounts.abandoned)}
                {(statusCounts.awarded > 0 || statusFilter === "awarded") && filterButton("awarded", "Awarded · review", statusCounts.awarded)}
              </div>
              <div className="picks-controls-actions flex flex-wrap items-center gap-2">
                <BandMixPicker
                  selectedPairs={bandMixPairs}
                  count={bandMixMatchCount}
                  label={bandMixOn ? selectedBandMixLabel : BAND_MIX_LABEL}
                  onToggleAll={() => setBandMixSelection(bandMixOn ? [] : [...ALL_BAND_MIX_PAIRS])}
                  onTogglePair={toggleBandMixPair}
                  onSelectAll={() => setBandMixSelection([...ALL_BAND_MIX_PAIRS])}
                  onClearAll={() => setBandMixSelection([])}
                />
                <details className="picks-presets relative">
                  <summary className="picks-presets-toggle list-none inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 [&::-webkit-details-marker]:hidden">
                    Presets{presets.length > 0 ? ` · ${presets.length}` : ""}
                  </summary>
                  <div className="picks-presets-menu absolute right-0 top-full z-30 mt-1 w-72 rounded-xl border border-slate-200 bg-white p-3 shadow-lg">
                    <form
                      className="picks-presets-save flex gap-2"
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
                        className="h-11 min-w-0 flex-1 rounded-lg border border-slate-200 px-2.5 text-sm text-slate-900 placeholder:text-slate-600 focus:border-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-700"
                      />
                      <button type="submit" disabled={!presetName.trim()} className="inline-flex min-h-11 items-center rounded-lg bg-emerald-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-50 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Save</button>
                    </form>
                    {presets.length === 0 ? (
                      <p className="picks-presets-empty mt-2 text-sm leading-relaxed text-slate-600">Save your best block combos to re-run them in one click.</p>
                    ) : <div className="mt-2 space-y-1">{presets.map((preset) => (
                      <div className="picks-presets-item flex items-center gap-1" key={preset.id}>
                        <button
                          type="button"
                          className="picks-presets-load inline-flex min-h-11 min-w-0 flex-1 items-center rounded-md px-2 py-1.5 text-left text-sm text-slate-700 hover:bg-slate-50 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
                          onClick={(event) => {
                            event.preventDefault();
                            applyPresetFilters(preset.filters);
                            (event.currentTarget.closest("details.picks-presets") as HTMLDetailsElement | null)?.open && ((event.currentTarget.closest("details.picks-presets") as HTMLDetailsElement).open = false);
                          }}
                        >
                          {preset.name}
                        </button>
                        <button type="button" className="picks-presets-delete inline-flex min-h-11 min-w-11 items-center justify-center rounded-md text-slate-600 hover:bg-red-50 hover:text-red-600 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" aria-label={`Delete preset ${preset.name}`} onClick={() => deletePreset(preset.id)}>✕</button>
                      </div>
                    ))}</div>}
                  </div>
                </details>
                <button type="button" className="match-clear-filters inline-flex min-h-11 items-center text-sm font-semibold text-emerald-800 underline underline-offset-2 hover:text-emerald-900 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed disabled:no-underline" onClick={clearFilters} disabled={activeFilterCount === 0}>
                  Clear filters{activeFilterCount > 0 ? ` · ${activeFilterCount}` : ""}
                </button>
              </div>
            </div>

            <div className="picks-search-blocks-row flex flex-col gap-2 lg:flex-row lg:items-center">
              <span className="picks-row-label shrink-0 text-sm font-semibold text-slate-600 lg:w-28">Search blocks</span>
              <div className="picks-search-blocks-content flex flex-wrap items-center gap-2">
                <span className="picks-block-caption text-sm font-medium text-slate-600" aria-hidden="true">Market</span>
                <FilterDropdown value={marketFilter} options={marketOptions} onChange={setMarketFilter} ariaLabel="Filter by market" />
                <span className="picks-block-caption text-sm font-medium text-slate-600" aria-hidden="true">Model chance</span>
                <FilterDropdown value={chanceMin} options={chanceOptions} onChange={(value) => { setChanceMin(value); if (value && bandMixOn) setBandMixSelection([]); }} ariaLabel="Minimum model chance for picks" />
                <span className="picks-block-caption text-sm font-medium text-slate-600" aria-hidden="true">Bookmaker implied</span>
                <FilterDropdown value={impliedMin} options={impliedOptions} onChange={(value) => { setImpliedMin(value); if (value && bandMixOn) setBandMixSelection([]); }} ariaLabel="Minimum bookmaker implied probability for picks" />
              </div>
            </div>

            <div className="picks-controls-row picks-signal-row flex flex-col gap-2 lg:flex-row lg:items-center">
              <span className="picks-row-label shrink-0 text-sm font-semibold text-slate-600 lg:w-28">Signals</span>
              <div className="match-status-filters flex flex-wrap items-center gap-1.5" aria-label="Signal filters">
                <button type="button" className={`${chipBase} ${edgeOnly ? chipActive : chipInactive}`} aria-pressed={edgeOnly} onClick={() => setEdgeOnly((value) => !value)}>Positive edge</button>
                <button type="button" className={`${chipBase} ${tightSpread ? chipActive : chipInactive}`} aria-pressed={tightSpread} onClick={() => setTightSpread((value) => !value)}>Model aligned ≤5 pp</button>
                <button type="button" className={`${chipBase} ${freshOnly ? chipActive : chipInactive}`} aria-pressed={freshOnly} onClick={() => setFreshOnly((value) => !value)}>Fresh quotes ≤8 h</button>
                <button type="button" className={`${chipBase} ${clvOnly ? chipActive : chipInactive}`} aria-pressed={clvOnly} onClick={() => setClvOnly((value) => !value)}>Beat the close</button>
                <span className="picks-signal-divider px-1 text-slate-600" aria-hidden="true">|</span>
                <button type="button" className={`policy ${chipBase} ${recFilter === "BET" ? "bg-sky-700 text-white" : chipInactive}`} aria-pressed={recFilter === "BET"} onClick={() => setRecFilter((value) => (value === "BET" ? "" : "BET"))}>
                  Bet <b className="font-mono tabular-nums">{recCounts.BET ?? 0}</b>
                </button>
                <button type="button" className={`policy ${chipBase} ${recFilter === "WATCH" ? "bg-slate-900 text-white" : chipInactive}`} aria-pressed={recFilter === "WATCH"} onClick={() => setRecFilter((value) => (value === "WATCH" ? "" : "WATCH"))}>
                  Watch <b className="font-mono tabular-nums">{recCounts.WATCH ?? 0}</b>
                </button>
              </div>
            </div>

            <div className="picks-controls-row picks-outcome-row flex flex-col gap-2 lg:flex-row lg:items-center">
              <span className="picks-row-label shrink-0 text-sm font-semibold text-slate-600 lg:w-28">Outcome</span>
              <div className="match-status-filters flex flex-wrap gap-1.5" aria-label="Filter by settled outcome">
                <button type="button" className={`${chipBase} ${outcomeFilter === "" ? chipActive : chipInactive}`} onClick={() => setOutcomeFilter("")}>
                  Any outcome <b className="font-mono tabular-nums">{Object.values(outcomeCounts).reduce((sum, count) => sum + count, 0)}</b>
                </button>
                <button type="button" className={`${chipBase} ${outcomeFilter === "won" ? "bg-emerald-700 text-white" : chipInactive} finished`} disabled={!outcomeCounts.won} onClick={() => setOutcomeFilter("won")}>
                  Won <b className="font-mono tabular-nums">{outcomeCounts.won ?? 0}</b>
                </button>
                <button type="button" className={`${chipBase} ${outcomeFilter === "lost" ? "bg-red-600 text-white" : chipInactive} live`} disabled={!outcomeCounts.lost} onClick={() => setOutcomeFilter("lost")}>
                  Lost <b className="font-mono tabular-nums">{outcomeCounts.lost ?? 0}</b>
                </button>
                <button type="button" className={`${chipBase} ${outcomeFilter === "pending" ? "bg-slate-900 text-white" : chipInactive}`} disabled={!outcomeCounts.pending} onClick={() => setOutcomeFilter("pending")}>
                  Pending <b className="font-mono tabular-nums">{outcomeCounts.pending ?? 0}</b>
                </button>
                <button type="button" className={`${chipBase} ${outcomeFilter === "void" ? "bg-amber-600 text-white" : chipInactive}`} disabled={!outcomeCounts.void} onClick={() => setOutcomeFilter("void")}>
                  Void <b className="font-mono tabular-nums">{outcomeCounts.void ?? 0}</b>
                </button>
              </div>
            </div>
          </div>

          {bandMixOn && (
            <p className="picks-band-mix-note border-b border-amber-200 bg-amber-50 px-4 py-3 text-base leading-relaxed text-amber-900 sm:px-5" role="status">
              <b className="font-semibold">Band mix on:</b> showing matches with <b className="font-semibold">any</b> of {selectedBandMixLabel} · exact model × market pairs only. <b className="font-semibold">The Q ≥75 gate is off</b> while band mix is on, so lower-Q predictions can match. Stays on as you change date — bookmark the link to reuse it daily.
            </p>
          )}

          <div className="picks-query-results space-y-3 px-4 py-4 sm:px-5" aria-live="polite">
            <div className="picks-overview-counts flex flex-wrap gap-x-4 gap-y-1 text-base leading-normal text-slate-600">
              <span><b className="font-mono tabular-nums text-slate-900">{sortedRows.length}</b> of <b className="font-mono tabular-nums text-slate-900">{rows.length}</b> loaded matches shown</span>
              <span><b className="font-mono tabular-nums text-slate-900">{matchedPickCount}</b> of <b className="font-mono tabular-nums text-slate-900">{loadedSelections}</b> loaded picks matched</span>
              <span><b className="font-mono tabular-nums text-slate-900">{loadedSelections}</b> of <b className="font-mono tabular-nums text-slate-900">{totalSelections}</b> candidates loaded</span>
            </div>
            {activeFilterLabels.length > 0 && (
              <p className="picks-active-filters text-base leading-relaxed text-slate-600">
                <b className="font-semibold text-slate-900">Active filters ({activeFilterLabels.length}):</b> {activeFilterLabels.join(" · ")}
              </p>
            )}
            {loadedSelections < totalSelections && (
              <p className="picks-truncated-note rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-base leading-relaxed text-amber-900" role="status">
                Filters and counts cover only the {loadedSelections} loaded picks. Load more candidates to search the remaining {totalSelections - loadedSelections}.
              </p>
            )}
            {filteredResults.length > 0 && (
              <div className="picks-outcome-strip grid gap-2 rounded-xl border border-slate-200 bg-slate-50/70 p-3 sm:grid-cols-2 lg:grid-cols-8" aria-label="Settled picks summary for this query">
                <strong className="text-base font-semibold text-slate-900 lg:col-span-2">Settled picks in this view</strong>
                <span className="outcome flex flex-col"><small className="text-sm text-slate-600">Selections</small><b className="font-mono text-sm tabular-nums text-slate-900">{filteredResults.length}</b></span>
                <span className="outcome won flex flex-col"><small className="text-sm text-slate-600">Won</small><b className="font-mono text-sm tabular-nums text-emerald-700">{filteredResultCounts.won}</b></span>
                <span className="outcome lost flex flex-col"><small className="text-sm text-slate-600">Lost</small><b className="font-mono text-sm tabular-nums text-red-600">{filteredResultCounts.lost}</b></span>
                <span className="outcome flex flex-col"><small className="text-sm text-slate-600">Hit rate</small><b className="font-mono text-sm tabular-nums text-slate-900">{decidedCount > 0 ? `${((filteredResultCounts.won / decidedCount) * 100).toFixed(1)}%` : "—"}</b></span>
                <span className={`outcome flex flex-col ${netUnitsTone}`}><small className="text-sm text-slate-600">Net units</small><b className="font-mono text-sm tabular-nums">{filteredResultCounts.priced > 0 ? `${filteredResultCounts.netUnits >= 0 ? "+" : ""}${filteredResultCounts.netUnits.toFixed(2)}` : "—"}</b></span>
                <span className={`outcome flex flex-col ${netUnitsTone}`}><small className="text-sm text-slate-600">ROI</small><b className="font-mono text-sm tabular-nums">{filteredResultCounts.priced > 0 ? `${((filteredResultCounts.netUnits / filteredResultCounts.priced) * 100).toFixed(1)}%` : "—"}</b></span>
                <span className="outcome note flex flex-col lg:col-span-8"><small className="text-base leading-relaxed text-slate-600">{filteredResultCounts.matches.size} matches with settled picks · selected date only</small></span>
              </div>
            )}
            <p className="picks-overview-note text-base leading-relaxed text-slate-600">
              {bandMixOn
                ? "Band mix searches the un-gated pool (Q ≥75 off). Publication still applies price, edge, freshness, quality, and diversification gates."
                : "Q ≥75 selections only. Publication also applies price, edge, freshness, quality, and diversification gates."}
            </p>
            {filteredResults.length > 0 && (
              <details className="picks-results-terms rounded-lg border border-slate-200 bg-white">
                <summary className="inline-flex min-h-11 cursor-pointer items-center px-3 py-2 text-base font-semibold text-slate-700 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 [&::-webkit-details-marker]:hidden">How the settled numbers are computed</summary>
                <p className="border-t border-slate-100 px-3 py-2 text-base leading-relaxed text-slate-600">{filteredResultCounts.void} void picks excluded from hit rate and ROI. ROI assumes one unit per settled non-void pick with captured odds; priced picks: {filteredResultCounts.priced} of {decidedCount}. Net units and ROI exclude picks without valid captured odds. This one-date summary is not a strategy backtest or a profitability claim.</p>
              </details>
            )}
          </div>

          <details
            className="picks-heatmap border-t border-slate-200"
            open={perfOpen}
            onToggle={(event) => setPerfOpen(event.currentTarget.open)}
          >
            <summary className="inline-flex min-h-11 cursor-pointer items-center px-4 py-3 text-base font-semibold text-slate-800 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 sm:px-5 [&::-webkit-details-marker]:hidden">Where winners came from · block performance, last {perfDays} days</summary>
            <div className="border-t border-slate-100 px-4 py-4 sm:px-5">
              {perfError && performance && (
                <p className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-base leading-relaxed text-amber-900" role="status">
                  <b className="font-semibold">Refresh failed; showing the last loaded {performance.window_days}-day heat map.</b> {perfError}
                </p>
              )}
              {perfLoading && performance && !perfError && (
                <p className="mb-3 text-base leading-relaxed text-slate-600" role="status">Refreshing the heat map… showing the last loaded {performance.window_days}-day result.</p>
              )}
              <BlockHeatmap
                performance={performance}
                loading={perfLoading}
                error={perfError}
                days={perfDays}
                onDaysChange={setPerfDays}
                onCell={(market, kind, block) => {
                  setMarketFilter(formatMarket(market));
                  // A threshold filters out low-probability band pairs; clear
                  // band mix through the same path so the page restores Q≥75.
                  if (bandMixOn) setBandMixSelection([]);
                  if (kind === "chance") setChanceMin(String(block));
                  else setImpliedMin(String(block));
                }}
              />
            </div>
          </details>

          <div className="picks-list-head hidden border-t border-slate-200 bg-slate-50 px-4 py-2 text-sm font-semibold text-slate-600 lg:grid lg:grid-cols-[minmax(0,1.5fr)_minmax(0,2fr)_minmax(0,0.8fr)_auto_auto] lg:gap-3 sm:px-5" aria-hidden="true">
            <span>Match</span>
            <span className="picks-list-stats grid grid-cols-5 gap-2"><span>Kickoff</span><span>Q-score</span><span>Markets</span><span>Odds</span><span>Spread</span></span>
            <span>Pick result</span>
            <span>Status</span>
            <span />
          </div>

          {sortedRows.length === 0 ? (
            <p className="panel-empty px-4 py-10 text-center text-sm text-slate-600 sm:px-5">
              {focusMatchId != null
                ? `No loaded picks for ${focusLabel ?? "this fixture"}. Load the next 100 candidates, or clear the focus.`
                : "No qualified matches match these filters."}
            </p>
          ) : (
            <div className="match-card-grid divide-y divide-slate-200 border-t border-slate-200">
              {sortedRows.map(([matchId, selections]) => (
                <MatchMarketGroup
                  key={matchId}
                  selections={selections}
                  onSelect={onSelect}
                />
              ))}
            </div>
          )}
          {onLoadMore && loadedSelections < totalSelections && (
            <div className="border-t border-slate-200 px-4 py-4 sm:px-5">
              <button className="btn-ghost btn-sm inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 disabled:opacity-50" type="button" onClick={onLoadMore} disabled={loadingMore} aria-busy={loadingMore}>
                {loadingMore ? "Loading more candidates…" : `Load next 100 candidates (${totalSelections - loadedSelections} remaining)`}
              </button>
            </div>
          )}
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
  const statusTone = displayState === "live" ? "text-emerald-700 bg-emerald-50 border-emerald-200"
    : displayState === "finished" ? "text-slate-700 bg-slate-100 border-slate-200"
    : displayState === "scheduled" ? "text-sky-700 bg-sky-50 border-sky-200"
    : displayState === "postponed" || displayState === "cancelled" ? "text-amber-700 bg-amber-50 border-amber-200"
    : "text-slate-600 bg-slate-100 border-slate-200";
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
      type="button"
      className={`inline-flex min-h-11 items-center rounded-md px-2 py-1 text-sm font-semibold transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 ${sort.key === key ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-900"}`}
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

  const outcomeClass = (outcome: "won" | "lost" | "void" | "pending") =>
    outcome === "won" ? "bg-emerald-50 text-emerald-700 border-emerald-200"
    : outcome === "lost" ? "bg-red-50 text-red-700 border-red-200"
    : outcome === "void" ? "bg-amber-50 text-amber-700 border-amber-200"
    : "bg-slate-100 text-slate-600 border-slate-200";

  return (
    <details className={`match-accordion match-card group ${displayState}`}>
      <summary className="match-card-summary match-row-summary grid cursor-pointer list-none gap-3 px-4 py-4 hover:bg-slate-50/70 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,2fr)_minmax(0,0.8fr)_auto_auto] lg:items-center sm:px-5 [&::-webkit-details-marker]:hidden">
        <div className="match-row-match min-w-0">
          <span className="match-row-league block text-sm font-semibold text-slate-600">{first.competition}</span>
          <strong className="match-row-teams block truncate text-sm font-semibold text-slate-900 sm:text-base" title={`${first.home_team} vs ${first.away_team}`}>
            {first.home_team} <span className="leg-match-vs font-normal text-slate-600">vs</span>{" "}
            {first.away_team}
          </strong>
        </div>
        <div className="match-row-stats grid grid-cols-2 gap-2 text-sm sm:grid-cols-5">
          <span className="flex flex-col"><small className="text-sm text-slate-600">Kickoff</small><b className="kickoff-time font-mono font-semibold tabular-nums text-slate-800">{formatKickoff(first.kickoff_at)}</b></span>
          <span className="flex flex-col"><small className="text-sm text-slate-600">Q-score</small><b className="font-mono font-semibold tabular-nums text-slate-900">Q {best.q_score.toFixed(1)}</b></span>
          <span className="flex flex-col"><small className="text-sm text-slate-600">Markets</small><b className="font-mono font-semibold tabular-nums text-slate-900">{selections.length}</b></span>
          <span className="flex flex-col" title={`Top pick: ${formatMarket(best.market)} · ${formatSelection(best.selection)}${best.source_bookmaker ? ` · ${best.source_bookmaker}` : ""}`}><small className="text-sm text-slate-600">Odds</small><b className="match-row-odds font-mono font-semibold tabular-nums text-slate-900">{best.best_odds ? `${best.best_odds.toFixed(2)}×` : "—"}</b></span>
          <span className="flex flex-col"><small className="text-sm text-slate-600">Spread</small><b className={`spread-badge inline-flex w-fit rounded-full border px-2 py-0.5 text-sm font-semibold ${(() => { const tone = spreadTone(best.model_agreement); return tone === "strong" || tone === "acceptable" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : tone === "caution" || tone === "high" ? "border-amber-200 bg-amber-50 text-amber-700" : "border-slate-200 bg-slate-50 text-slate-600"; })()}`}>{best.model_agreement == null ? "—" : `${(best.model_agreement * 100).toFixed(1)} pp`}</b></span>
        </div>
        <div className="match-row-picks">
          <small className="block text-sm text-slate-600">Pick result</small>
          <span className="match-row-picks-badges mt-1 flex flex-wrap gap-1">
            {(["won", "lost", "void", "pending"] as const)
              .filter((outcome) => pickOutcomes[outcome] > 0)
              .map((outcome) => (
                <b key={outcome} className={`market-result inline-flex items-center rounded-full border px-2 py-0.5 text-sm font-semibold ${outcomeClass(outcome)} ${outcome}`}>
                  {selectionStatusLabel(outcome)}
                  {pickOutcomes[outcome] > 1 ? ` ×${pickOutcomes[outcome]}` : ""}
                </b>
              ))}
          </span>
        </div>
        <div className="match-row-status">
          <b className={`match-result-badge inline-flex items-center rounded-full border px-2 py-0.5 text-sm font-semibold ${statusTone} ${statusTone}`}>{matchStatusText(first)}</b>
        </div>
        <div className="match-row-actions">
          <span className="match-card-expand inline-flex items-center gap-1 text-sm font-semibold text-emerald-800">View markets <b aria-hidden="true" className="transition-transform group-open:rotate-180">⌄</b></span>
        </div>
      </summary>
      <div className="market-table border-t border-slate-200 bg-slate-50/40 px-4 py-4 sm:px-5">
        <div className="market-table-head mb-3 flex flex-wrap items-center gap-1.5">
          <span className="market-sort-label mr-1 text-sm font-semibold text-slate-600">Sort markets</span>
          {button("market", "Market")}
          {button("q", "Q-score")}
          {button("odds", "Captured odds")}
          {button("spread", "Spread")}
          {button("edge", "Edge")}
        </div>
        <div className="space-y-3">
          {sorted.map((row) => {
            const freshness = quoteFreshness(row);
            const freshnessTone = freshness.state === "fresh" ? "text-emerald-700" : freshness.state === "aging" ? "text-amber-700" : freshness.state === "blocked" || freshness.state === "stale" ? "text-red-600" : "text-slate-600";
            return <div className="market-row rounded-xl border border-slate-200 bg-white p-3 shadow-sm sm:p-4" key={row.prediction_id}>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="market-row-identity min-w-0">
                  {!selectionRepeatsMarket(row.market, row.selection) && <span className="market-row-market block text-sm font-semibold text-slate-600">{formatMarket(row.market)}</span>}
                  <strong className="market-row-selection block text-sm font-semibold text-slate-900">{formatSelection(row.selection)}</strong>
                  <span className="market-row-badges mt-1.5 flex flex-wrap gap-1.5">
                    <b className={`grade-badge inline-flex items-center rounded-full border px-2 py-0.5 text-sm font-semibold ${gradeTone(row.q_grade) === "A" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : gradeTone(row.q_grade) === "B" ? "border-amber-200 bg-amber-50 text-amber-700" : "border-slate-200 bg-slate-100 text-slate-700"} grade-${gradeTone(row.q_grade)}`}>
                      {row.q_grade ?? "Qualified"}
                    </b>
                    <b className={`market-result inline-flex items-center rounded-full border px-2 py-0.5 text-sm font-semibold ${outcomeClass((row.result as "won" | "lost" | "void" | null) ?? "pending")} ${row.result ?? "pending"}`}>{row.result === "won" ? "Won" : row.result === "lost" ? "Lost" : row.result === "void" ? "Void" : "Pending"}</b>
                  </span>
                  <div className="market-chance-evidence mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-600">
                    <span>Model chance <b className="font-mono font-semibold tabular-nums text-slate-900">{percent(row.model_probability)}</b></span>
                    <span>Bookmaker implied <b className="font-mono font-semibold tabular-nums text-slate-900">{percent(row.source_implied_probability ?? row.avg_implied)}</b> <em className="not-italic text-slate-600">margin included</em></span>
                  </div>
                </div>
                <div className="market-row-actions shrink-0">
                  <button type="button" className="btn-ghost btn-sm inline-flex min-h-11 items-center rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={() => onSelect(row)}>
                    Details
                  </button>
                </div>
              </div>
              <dl className="market-row-facts mt-3 grid gap-3 border-t border-slate-100 pt-3 text-sm sm:grid-cols-2 lg:grid-cols-5">
                <div>
                  <dt className="text-sm font-semibold text-slate-600">Q-score</dt>
                  <dd className="font-mono font-semibold tabular-nums text-slate-900">Q {row.q_score.toFixed(1)}</dd>
                </div>
                <div>
                  <dt className="text-sm font-semibold text-slate-600">Captured odds</dt>
                  <dd className="font-mono font-semibold tabular-nums text-slate-900">{row.best_odds ? `${row.best_odds.toFixed(2)}×` : "—"}</dd>
                  <small className="market-quote-meta block text-sm text-slate-600">{row.source_bookmaker ?? "Bookmaker unavailable"} · <span className="font-mono tabular-nums">{quoteTime(row.source_odds_at)}</span> · <b className={freshnessTone}>{freshness.label}</b></small>
                </div>
                <div className={(() => { const tone = spreadTone(row.model_agreement); return tone === "strong" || tone === "acceptable" ? "text-emerald-700" : tone === "caution" || tone === "high" ? "text-amber-700" : undefined; })()} title={`Model spread: ${spreadLabel(row.model_agreement)}`}>
                  <dt className="text-sm font-semibold text-slate-600">Spread</dt>
                  <dd className="font-mono font-semibold tabular-nums">{row.model_agreement == null ? "—" : `${(row.model_agreement * 100).toFixed(1)} pp`}</dd>
                </div>
                <div className={row.edge != null && row.edge > 0 ? "positive text-emerald-700" : undefined}>
                  <dt className="text-sm font-semibold text-slate-600">Edge</dt>
                  <dd className="font-mono font-semibold tabular-nums">{row.edge != null ? `${(row.edge * 100).toFixed(1)}%` : "—"}</dd>
                </div>
                <div className={row.clv_percentage != null && row.clv_percentage > 0 ? "positive text-emerald-700" : undefined}>
                  <dt className="text-sm font-semibold text-slate-600">CLV</dt>
                  <dd className="font-mono font-semibold tabular-nums">{row.clv_percentage != null ? `${(row.clv_percentage * 100).toFixed(1)}%` : "—"}</dd>
                  <small className="market-quote-meta block text-sm text-slate-600">{row.closing_decimal_odds ? `Close ${row.closing_decimal_odds.toFixed(2)}×` : "No closing price yet"}</small>
                </div>
              </dl>
            </div>;
          })}
        </div>
      </div>
    </details>
  );
}
