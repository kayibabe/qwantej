import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../../auth";
import type { DailyTickets, Leg, MatchFixture, SelectionSummary, Ticket } from "../../lib/api";
import {
  fetchDailyTickets,
  fetchMatchFixtures,
  fetchQualifiedPickCounts,
  fetchQualifiedSelections,
  fetchRejectedSelections,
  formatDate,
  formatKickoff,
  formatMarket,
  formatSelection,
  selectionRepeatsMarket,
  selectionTone,
  formatStage,
} from "../../lib/api";
import TicketCard from "../../components/TicketCard";
import RejectionReasons from "../../components/RejectionReasons";
import SelectionDetail, {
  type DetailSelection,
} from "../../components/SelectionDetail";
import type { MarketRoiDailyData } from "./MarketRoiDaily";
import { TicketGridSkeleton } from "./TicketGridSkeleton";
import PipelineRibbon, { type PipelineStep } from "./PipelineRibbon";
import {
  reasonLabel,
  TODAY,
  withRejectionEvidence,
} from "./helpers";
import { parseBandMixPairs } from "./bandMix";
import type { DailyTab, DailyTicketsPageProps } from "./types";

const ParameterSweepPicks = lazy(() => import("./ParameterSweepPicks").then((module) => ({ default: module.ParameterSweepPicks })));
const MarketRoiDaily = lazy(() => import("./MarketRoiDaily").then((module) => ({ default: module.MarketRoiDaily })));
const AllMatches = lazy(() => import("./AllMatches").then((module) => ({ default: module.AllMatches })));
const FixtureExplorer = lazy(() => import("./FixtureExplorer").then((module) => ({ default: module.FixtureExplorer })));

export default function DailyTicketsPage({ date, initialTab = "fixtures", mode = "overview", onOpenMatch, onTabChange, onUpgrade }: DailyTicketsPageProps & { onOpenMatch?: (matchId: number, predictionId?: number) => void }) {
  const { user, loading: authLoading } = useAuth();
  const isAdmin = user?.role === "admin";
  const canExploreMarkets = isAdmin || user?.plan === "pro";
  const [data, setData] = useState<DailyTickets | null>(null);
  const [rejected, setRejected] = useState<SelectionSummary[]>([]);
  const [matches, setMatches] = useState<SelectionSummary[]>([]);
  // Band mix deliberately searches every stored prediction; without it the
  // System picks list stays on the existing Q >=75 universe.
  const [bandMixPairs, setBandMixPairs] = useState<number[]>(() => parseBandMixPairs(
    typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("match_band_mix"),
  ));
  const minQScore = bandMixPairs.length > 0 ? 0 : 75;
  const lastMinQScore = useRef(minQScore);
  const [matchesTotal, setMatchesTotal] = useState(0);
  const [pickedMatchTotal, setPickedMatchTotal] = useState(0);
  const [loadingMoreMatches, setLoadingMoreMatches] = useState(false);
  const [marketRoi, setMarketRoi] = useState<MarketRoiDailyData | null>(null);
  const [marketRoiError, setMarketRoiError] = useState<string | null>(null);
  const [fixtures, setFixtures] = useState<MatchFixture[]>([]);
  // null means the counts are unknown (request failed); {} means "loaded, no
  // fixture has a pick", which the list renders as a muted dash.
  const [pickCounts, setPickCounts] = useState<Record<number, number> | null>(null);
  const [pickCountsStale, setPickCountsStale] = useState(false);
  const [marketRoiRefreshing, setMarketRoiRefreshing] = useState(false);
  const [marketRoiRequestDate, setMarketRoiRequestDate] = useState<string | null>(null);
  const [focusMatchId, setFocusMatchId] = useState<number | null>(null);
  const [candidatesLoaded, setCandidatesLoaded] = useState(false);
  const [rejectedLoaded, setRejectedLoaded] = useState(false);
  const [tab, setTab] = useState<DailyTab>(initialTab);
  const [loading, setLoading] = useState(false);
  const firstLoad = useRef(true);
  const loadedKey = useRef<string | null>(null);
  const requestVersion = useRef(0);
  const loadScope = useRef({ date, minQScore });
  const [dataCheckedAt, setDataCheckedAt] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [detail, setDetail] = useState<{
    selection: DetailSelection;
    modelVersion?: string;
    pricing?: "market" | "model";
    publishedAt?: string;
  } | null>(null);
  const [stakePerTicket, setStakePerTicket] = useState("");

  useEffect(() => { setTab(initialTab); }, [initialTab, mode]);
  useEffect(() => { loadScope.current = { date, minQScore }; }, [date, minQScore]);

  // A shared link may name a tab this role cannot see; fall back to the
  // start of the funnel rather than rendering an empty workspace.
  useEffect(() => {
    if (authLoading || mode !== "overview") return;
    if (tab === "passed" && !isAdmin) {
      setTab("fixtures");
      onTabChange?.("fixtures");
    }
  }, [authLoading, isAdmin, mode, onTabChange, tab]);

  // Fixture focus is slate-specific: drop it when the date changes, and when
  // the user leaves System picks, so a stale filter never hides a new slate.
  useEffect(() => {
    setFocusMatchId(null);
    // Keep the last counts visible, but never present them as the new date's.
    setPickCountsStale(true);
  }, [date]);
  useEffect(() => {
    if (tab !== "picks") setFocusMatchId(null);
  }, [tab]);

  const openFixturePicks = (matchId: number) => {
    setFocusMatchId(matchId);
    setTab("picks");
    onTabChange?.("picks");
  };

  const flatStakeForTicket = (ticket: Ticket | null) => {
    const stake = Number(stakePerTicket);
    if (!ticket || !Number.isFinite(stake) || stake <= 0 || ticket.combined_odds == null || ticket.combined_odds <= 1) return null;
    return stake;
  };

  const load = useCallback(async (targetDate: string, force = false) => {
    const roleKey = isAdmin ? "admin" : canExploreMarkets ? "pro" : "free";
    // The overview already preloads every headline tab, so switching tabs must
    // not re-issue the same requests. The research workspace loads per tab.
    const requestedKey = mode === "overview"
      ? `${mode}:${targetDate}:${roleKey}:q${minQScore}`
      : `${mode}:${targetDate}:${tab}:${roleKey}:q${minQScore}`;
    if (!force && loadedKey.current === requestedKey) return;
    const request = ++requestVersion.current;
    if (lastMinQScore.current !== minQScore) {
      // Never mix Q>=75 rows with the un-gated band-mix universe.
      lastMinQScore.current = minQScore;
      setMatches([]);
      setMatchesTotal(0);
      setPickedMatchTotal(0);
      setCandidatesLoaded(false);
      // Counts belong to the old gate; label them stale until refreshed.
      setPickCounts(null);
      setPickCountsStale(true);
    }
    if (firstLoad.current) setLoading(true);
    try {
      const overview = mode === "overview";
      // The overview preloads its headline tabs so the summary counts and tab
      // switches are instant. The research workspace loads only the active tab.
      const wantsTickets = overview || tab === "tickets";
      const wantsFixtures = overview || tab === "fixtures";
      const wantsCandidates = canExploreMarkets && (overview || tab === "picks" || tab === "passed");
      const wantsRejected = isAdmin && (overview || tab === "passed");
      const wantsMarketRoi = isAdmin && tab === "market-roi";
      if (wantsMarketRoi) {
        setMarketRoiRefreshing(true);
        setMarketRoiRequestDate(targetDate);
        setMarketRoiError(null);
      }
      const marketRoiPromise = wantsMarketRoi
        ? import("./MarketRoiDaily").then(({ fetchDailyMarketRoi }) => fetchDailyMarketRoi(targetDate)).catch((cause) => {
          const message = cause instanceof Error ? cause.message : "Daily market ROI is unavailable";
          if (request === requestVersion.current) setMarketRoiError(message);
          return null;
        })
        : Promise.resolve(null);
      // Coverage counts are public to signed-in accounts, so every role gets
      // them alongside the fixture list. A failure must not hide fixtures: a
      // null result leaves the badge out rather than claiming "no picks".
      const pickCountsPromise = wantsFixtures
        ? fetchQualifiedPickCounts(targetDate, minQScore).catch(() => null)
        : Promise.resolve(null);
      const [tickets, fixtureRows, countRows, allRows, rejectedRows, marketRoiRows] = await Promise.all([
        wantsTickets ? fetchDailyTickets(targetDate) : Promise.resolve(null),
        wantsFixtures ? fetchMatchFixtures(targetDate) : Promise.resolve(null),
        pickCountsPromise,
        wantsCandidates ? fetchQualifiedSelections(targetDate, minQScore) : Promise.resolve(null),
        wantsRejected ? fetchRejectedSelections(targetDate) : Promise.resolve(null),
        marketRoiPromise,
      ]);
      if (request !== requestVersion.current) return;
      setError(null);
      if (tickets) setData(tickets);
      if (fixtureRows) setFixtures(fixtureRows);
      if (wantsFixtures) {
        // A failed count request keeps the last successful map visible, with
        // an explicit stale badge, instead of claiming "no picks".
        if (countRows) {
          setPickCounts(Object.fromEntries(countRows.map((row) => [row.match_id, row.picks])));
          setPickCountsStale(false);
        } else {
          setPickCountsStale(true);
        }
      }
      if (allRows) {
        setMatches(withRejectionEvidence(allRows.rows, rejectedRows ?? []));
        setMatchesTotal(allRows.total);
        setPickedMatchTotal(allRows.matchTotal);
        setCandidatesLoaded(true);
      }
      if (rejectedRows) {
        setRejected(rejectedRows);
        setRejectedLoaded(true);
      }
      if (wantsMarketRoi) {
        setMarketRoi(marketRoiRows);
        if (marketRoiRows) setMarketRoiError(null);
        setMarketRoiRefreshing(false);
      }
      loadedKey.current = requestedKey;
      setDataCheckedAt(new Date());
    } catch (e) {
      if (request !== requestVersion.current) return;
      setError(
        e instanceof Error ? e.message : isAdmin ? "Failed to load research ledger" : "Failed to load recommendations",
      );
      setPickCountsStale(true);
      if (isAdmin && tab === "market-roi") setMarketRoiRefreshing(false);
    } finally {
      if (request === requestVersion.current) {
        setLoading(false);
        firstLoad.current = false;
      }
    }
  }, [canExploreMarkets, isAdmin, minQScore, mode, tab]);

  const loadMoreMatches = async () => {
    if (loadingMoreMatches || matches.length >= matchesTotal) return;
    const requestedDate = date;
    const requestedMinQ = minQScore;
    const request = requestVersion.current;
    const offset = matches.length;
    setLoadingMoreMatches(true);
    try {
      const page = await fetchQualifiedSelections(requestedDate, requestedMinQ, offset);
      // A date or Q-gate change starts a new load and invalidates this page.
      // Never append an older scope's picks to the new slate.
      const scopeChanged = request !== requestVersion.current
        || loadScope.current.date !== requestedDate
        || loadScope.current.minQScore !== requestedMinQ;
      if (scopeChanged) return;
      setMatches((current) => withRejectionEvidence(
        [...current, ...page.rows.filter((row) => !current.some((existing) => existing.prediction_id === row.prediction_id))],
        rejected,
      ));
      setMatchesTotal(page.total);
      setPickedMatchTotal(page.matchTotal);
    } catch (cause) {
      if (request === requestVersion.current
        && loadScope.current.date === requestedDate
        && loadScope.current.minQScore === requestedMinQ) {
        setError(cause instanceof Error ? cause.message : "More candidate selections could not be loaded");
      }
    } finally {
      if (request === requestVersion.current) setLoadingMoreMatches(false);
    }
  };

  useEffect(() => {
    let active = true;
    const refresh = () => { if (active && document.visibilityState === "visible") void load(date, true); };
    // Always start the initial request. A background tab must still leave its
    // skeleton state; visibility only gates follow-up polling.
    void load(date);
    const timer = window.setInterval(refresh, 300_000);
    const onVisibility = () => { if (document.visibilityState === "visible") refresh(); };
    document.addEventListener("visibilitychange", onVisibility);
    return () => { active = false; requestVersion.current += 1; window.clearInterval(timer); document.removeEventListener("visibilitychange", onVisibility); };
  }, [date, load]);

  // The shell asks pages to refresh in place; cancelable so the shell knows the
  // request was handled and does not remount the route.
  useEffect(() => {
    const onRefresh = (event: Event) => {
      if (authLoading) return;
      event.preventDefault();
      void load(date, true);
    };
    window.addEventListener("qwantej:refresh", onRefresh);
    return () => window.removeEventListener("qwantej:refresh", onRefresh);
  }, [authLoading, date, load]);
  const openTicketLeg = (leg: Leg, ticket: Ticket) => {
    setDetail({
      selection: leg,
      modelVersion: ticket.model_version,
      publishedAt: ticket.published_at,
      pricing: ticket.pricing,
    });
  };

  const openSelection = (selection: SelectionSummary) => {
    setDetail({
      selection: {
        ...selection,
        source_odds_at: selection.source_odds_at ?? null,
        result: selection.result ?? undefined,
      },
    });
  };

  // Keep all public-page status and publication metadata scoped to active
  // release tiers.
  const publicPublishedTickets = data
    ? [
        data.conservative,
        data.balanced,
      ].filter((ticket): ticket is Ticket => ticket != null)
    : [];
  // Read the overview as a funnel: the fixture universe, then the system's
  // qualified picks, then the tickets those picks produced, then rejections.
  const dailyTabs: [DailyTab, string][] = mode === "overview"
    ? [
        ["fixtures", "All fixtures"],
        ["picks", "System picks"],
        ["tickets", "Accumulator tickets"],
        ...(isAdmin ? [["passed", "Rejected / why"] as [DailyTab, string]] : []),
      ]
    : [
        ["picks", "System picks"],
        ["market-roi", "Market edge"],
        ["passed", "Rejected / why"],
        ["odds-policy", "Policy"],
      ];
  const publicationTimes = publicPublishedTickets
    .map((ticket) => ticket.published_at)
    .filter(Boolean)
    .sort();
  const latestPublication = publicationTimes[publicationTimes.length - 1];
  const modelVersions = [
    ...new Set(publicPublishedTickets.map((ticket) => ticket.model_version)),
  ];
  const qScoreMatchCount = new Set(matches.map((row) => row.match_id)).size;
  const q85Count = matches.filter((row) => row.q_score >= 85).length;
  const rejectionReasonCounts = matches.reduce<Record<string, number>>((counts, row) => {
    for (const reason of row.reason_codes ?? []) counts[reason] = (counts[reason] ?? 0) + 1;
    return counts;
  }, {});
  const leadingRejectionReasons = Object.entries(rejectionReasonCounts)
    .sort(([, left], [, right]) => right - left)
    .slice(0, 4);
  const generationFinishedWithoutTickets = Boolean(
    data?.generation_id != null &&
      ["completed", "partial", "failed"].includes(
        data.generation_status ?? "",
      ) &&
      data.generated_ticket_count === 0,
  );
  const generationUnavailable = Boolean(
    data && data.generation_id == null && publicPublishedTickets.length === 0,
  );
  const pipelineActive = Boolean(
    data?.pipeline_run_id != null &&
      ["pending", "running"].includes(data.pipeline_status ?? ""),
  );
  const pipelineStateTitle = pipelineActive
    ? "The full ticket pipeline is running automatically."
    : data?.pipeline_run_id != null
      ? "The latest full pipeline stopped before ticket generation."
      : date === TODAY
        ? "No full pipeline has run yet; automatic recovery is enabled."
        : "No full pipeline was recorded for this date.";
  const pipelineStateBadge = pipelineActive
    ? "Pipeline running"
    : data?.pipeline_run_id != null
      ? "Pipeline incomplete"
      : "Pipeline not run";

  const pickCount = canExploreMarkets && candidatesLoaded ? pickedMatchTotal || qScoreMatchCount : null;
  const publishedCount = publicPublishedTickets.length;
  const latestPublicationTime = latestPublication
    ? new Date(latestPublication).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Africa/Blantyre" })
    : null;
  const briefTitle = publishedCount > 0
    ? `${publishedCount} ${publishedCount === 1 ? "ticket is" : "tickets are"} published for ${formatDate(data?.target_date ?? date)}.`
    : generationFinishedWithoutTickets
      ? "No ticket cleared every publication gate for this date."
      : pipelineActive
        ? "The ticket pipeline is running; publications may still appear."
        : "No accumulator ticket is published for this date.";
  const briefBody = publishedCount > 0
    ? canExploreMarkets
      ? `${pickCount != null ? `Built from ${pickCount} qualified ${pickCount === 1 ? "match" : "matches"}. ` : ""}Open a leg to review its captured quote, model, and settlement evidence before using the what-if stake.`
      : "The published tiers are shown below with their match legs and settlement status. Pro reveals each selection, its captured price, model chance and evidence."
    : generationFinishedWithoutTickets
      ? "Candidates were evaluated, but no combination met the active tier rules. Zero tickets is a valid, evidence-backed outcome."
      : pipelineActive
        ? `Current stage: ${formatStage(data?.pipeline_current_stage ?? "starting")}. The workspace refreshes while the persisted run advances.`
        : "Ticket cards stay hidden when there is no evidence that publication ran for this date.";
  const isOverviewWithRibbon = mode === "overview" && !!data;
  const pipelineSteps: PipelineStep[] = mode === "overview"
    ? [
        { key: "fixtures", label: "All fixtures", value: fixtures.length, note: "scheduled for this date" },
        {
          key: "picks",
          label: "System picks",
          value: pickCount ?? "—",
          note: canExploreMarkets ? "matches with a qualified pick" : "Pro · open to preview",
        },
        {
          key: "tickets",
          label: "Accumulator tickets",
          value: publishedCount,
          note: publishedCount ? "published tiers" : "none published",
        },
        ...(isAdmin ? [{
          key: "passed" as DailyTab,
          label: "Rejected / why",
          value: rejectedLoaded ? rejected.length : "—",
          note: rejectedLoaded ? "rejected with reasons" : "open the ledger",
        }] : []),
      ]
    : [];
  const tabCounts: Partial<Record<DailyTab, number>> = {
    fixtures: fixtures.length,
    ...(pickCount != null ? { picks: pickCount } : {}),
    ...(data ? { tickets: publishedCount } : {}),
    ...(isAdmin && rejectedLoaded ? { passed: rejected.length } : {}),
  };

  // Describe each tier by the rules its generation actually applied. The
  // backend omits observation-only tickets from non-admin payloads, so card
  // visibility follows the returned data rather than a hardcoded role check.
  const fairPriced = data?.pricing === "market";
  const balancedIsObservation = (data?.observation_only_ticket_types ?? []).includes("balanced");
  const showBalanced = isAdmin || (data ? data.balanced != null : false);
  const balancedRules = fairPriced ? "3 legs · 3.00–4.00×" : "Q ≥80 · 60% Grade A/A+";
  const publicTiers = [
    {
      key: "conservative" as const,
      name: "Conservative",
      desc: fairPriced ? "3 legs · 2.00–2.60× · review first" : "Q ≥85 · 3–6 legs · 3–5×",
      color: "#047857",
    },
    ...(showBalanced ? [{
      key: "balanced" as const,
      name: "Balanced",
      desc: `${balancedRules}${balancedIsObservation ? " · observation only, not counted" : ""}`,
      color: "#0284c7",
    }] : []),
  ];

  const matchGroups = Object.entries(matches.reduce<Record<number, SelectionSummary[]>>((groups, row) => {
    (groups[row.match_id] ??= []).push(row);
    return groups;
  }, {})).map(([id, rows]) => [Number(id), rows] as [number, SelectionSummary[]]);
  const focusFixture = focusMatchId == null ? null : fixtures.find((fixture) => fixture.match_id === focusMatchId) ?? null;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-2">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
            {mode === "overview"
              ? date === TODAY ? "Today" : formatDate(date)
              : formatDate(data ? data.target_date : date)}
          </h1>
          {mode === "overview" && (
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-600">
              {date === TODAY && <span className="font-medium text-slate-700">{data ? formatDate(data.target_date) : formatDate(date)}</span>}
              {dataCheckedAt && (
                <span className="font-mono text-sm tabular-nums text-slate-600" title="Time when recommendation data was last checked">
                  Data checked {dataCheckedAt.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Africa/Blantyre" })} CAT
                </span>
              )}
              {error && data && (
                <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-sm font-semibold text-amber-900" role="status">
                  Stale · last successful load shown
                </span>
              )}
            </p>
          )}
          <p className="text-base leading-relaxed text-slate-600 max-w-3xl">
            {isAdmin
              ? "Internal research and paper trading only. No ticket is a promise of profit."
              : "Recommendations are informational. Football outcomes are uncertain; no result is guaranteed."}
          </p>
        </div>
        {isAdmin && mode === "overview" && data && (
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600" aria-label="Publication context">
            <span className="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 font-medium text-slate-600" title="Candidates that passed the strict publication quality gate before ticket construction">
              {data.qualified_pool} strict publication candidates
            </span>
            {(data.horizon_pool ?? 0) > 0 && <span title="Additional candidates admitted by the bounded rolling-horizon fallback">+{data.horizon_pool} rolling-horizon</span>}
            {Object.keys(data.relaxed_ticket_types ?? {}).length > 0 && <span title="One or more tiers used the bounded relaxation policy">Bounded relaxation</span>}
            {latestPublication && (
              <span className="font-mono tabular-nums">
                Published{" "}
                {new Date(latestPublication).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            )}
            {modelVersions.length > 0 && (
              <span className="font-mono tabular-nums">Model {modelVersions.join(", ")}</span>
            )}
          </div>
        )}
      </div>

      {mode === "overview" && data && (
        <>
          <section className="rounded-xl border border-slate-200 bg-white overflow-hidden" aria-label="Today decision brief">
            <div className="flex flex-col gap-4 p-4 sm:p-5 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0 space-y-1">
                <strong className="block text-base font-bold text-slate-900">{briefTitle}</strong>
                <p className="text-base leading-relaxed text-slate-600 max-w-3xl">{briefBody}</p>
              </div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:w-auto lg:min-w-[420px]">
                <BriefFact label="Publication" value={latestPublicationTime ? `${latestPublicationTime} CAT` : pipelineStateBadge} attention={publishedCount === 0} />
                {dataCheckedAt && <BriefFact label="Checked" value={`${dataCheckedAt.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Africa/Blantyre" })} CAT`} />}
                <BriefFact label="Pricing" value={data ? (fairPriced ? "Fair price" : "Model price") : "—"} />
                {isAdmin && modelVersions.length > 0 && <BriefFact label="Model" value={modelVersions.join(", ")} />}
              </div>
            </div>
          </section>
          <PipelineRibbon
            steps={pipelineSteps}
            active={tab}
            onSelect={(key) => { setTab(key); onTabChange?.(key); }}
          />
        </>
      )}

      {error && (
        <div className="flex flex-col gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 sm:flex-row sm:items-start sm:justify-between" role="alert">
          <div className="min-w-0">
            <strong className="block text-red-800">{data && mode === "overview"
              ? "Showing the last loaded recommendations"
              : isAdmin ? "Internal research ledger unavailable" : "Recommendations unavailable"}</strong>
            <span className="block mt-0.5 leading-relaxed">{data && mode === "overview"
              ? `The latest refresh failed${dataCheckedAt ? `; this view was loaded at ${dataCheckedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : ""}. ${error}`
              : error}</span>
          </div>
          <button
            type="button"
            className="inline-flex min-h-11 shrink-0 items-center justify-center gap-1.5 px-3 py-2 text-sm font-semibold text-white bg-red-600 hover:bg-red-700 disabled:opacity-60 rounded-lg transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-700"
            onClick={async () => { setRetrying(true); try { await load(date, true); } finally { setRetrying(false); } }}
            disabled={retrying}
          >
            {retrying ? "Retrying…" : data && mode === "overview" ? "Refresh now" : "Try again"}
          </button>
        </div>
      )}

      {loading ? (
        <TicketGridSkeleton />
      ) : (
        <>
          {/* Overview navigation lives in the PipelineRibbon cards above; keep the tab bar
              for the research workspace and as a fallback before any data has loaded. */}
          {!isOverviewWithRibbon && dailyTabs.length > 1 && (
            <nav className="flex flex-wrap gap-2" aria-label="Daily ticket workspace">
              {dailyTabs.map(([key, label]) => {
                const active = tab === key;
                return (
                  <button
                    key={key}
                    type="button"
                    className={`inline-flex min-h-11 items-center gap-2 rounded-lg border px-3 py-2 text-sm font-semibold transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 ${
                      active
                        ? "bg-emerald-700 border-emerald-700 text-white"
                        : "bg-white border-slate-200 text-slate-600 hover:text-slate-900 hover:border-slate-300 hover:bg-slate-50"
                    }`}
                    onClick={() => { setTab(key); onTabChange?.(key); }}
                  >
                    {label}
                    {tabCounts[key] != null && (
                      <span className={`inline-flex min-w-5 items-center justify-center rounded-full px-1.5 py-0.5 text-sm font-bold tabular-nums ${active ? "bg-white/20 text-white" : "bg-slate-100 text-slate-600"}`}>
                        {tabCounts[key]}
                      </span>
                    )}
                  </button>
                );
              })}
            </nav>
          )}

          {tab === "fixtures" && <ViewIntro eyebrow="Fixtures" title="All fixtures for this date" body="Every fixture scheduled for this date, with competition, kickoff time, and current status." />}
          {tab === "picks" && canExploreMarkets && <ViewIntro eyebrow="System picks" title="System picks for this date" body="Grouped by match. The active search scope, filters and result counts are stated above the list; a pick appearing here does not mean it made a published accumulator." />}
          {tab === "tickets" && <ViewIntro eyebrow="Accumulator tickets" title="Tickets assembled from this date’s picks" body={canExploreMarkets ? "Each published tier is a fixed combination of the system’s qualified picks. Expand a leg to inspect its evidence; the stake field is a what-if calculation only." : "Each published tier is a fixed combination of the system’s qualified picks. On Free you can review every match leg and its settlement status; Pro opens the selections and their evidence."} />}

          {tab === "fixtures" && <Suspense fallback={<RouteLoading label="Loading fixtures…" />}><FixtureExplorer fixtures={fixtures} pickCounts={pickCounts} countsStale={pickCountsStale || Boolean(error)} onOpenPicks={canExploreMarkets ? openFixturePicks : undefined} /></Suspense>}
          {tab === "picks" && canExploreMarkets && <Suspense fallback={<RouteLoading label="Loading system picks…" />}><AllMatches rows={matchGroups} totalSelections={matchesTotal} loadedSelections={matches.length} loadingMore={loadingMoreMatches} onLoadMore={loadMoreMatches} onSelect={openSelection} focusMatchId={focusMatchId} focusLabel={focusFixture ? `${focusFixture.home_team} vs ${focusFixture.away_team}` : null} onClearFocus={() => setFocusMatchId(null)} onBandMixChange={setBandMixPairs} /></Suspense>}
          {tab === "picks" && !canExploreMarkets && (
            <section className="rounded-xl border border-slate-200 bg-white overflow-hidden" aria-labelledby="plan-locked-picks-title">
              <div className="p-5 sm:p-6 space-y-5">
                <div className="space-y-2 max-w-3xl">
                  <span className="inline-flex items-center rounded-full border border-sky-200 bg-sky-50 px-2.5 py-1 text-sm font-semibold text-sky-700">Pro workspace</span>
                  <h2 id="plan-locked-picks-title" className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">See every qualified selection, not just the ticket</h2>
                  <p className="text-base leading-relaxed text-slate-600">System picks list each Q ≥75 selection behind this date’s tickets. Pro opens the full ledger for every match, with the evidence recorded when the pick qualified.</p>
                </div>
                <ul className="grid gap-3 sm:grid-cols-3">
                  <LockedFeature title="Market and selection" body="Exactly what the model qualified, grouped by match." />
                  <LockedFeature title="Price and model chance" body="Captured bookmaker odds next to the model’s probability." />
                  <LockedFeature title="Spread and edge" body="How far the models disagreed and where the price sat above fair." />
                </ul>
                <div className="flex flex-wrap gap-2">
                  {onUpgrade && <button type="button" className="inline-flex min-h-11 items-center gap-1.5 px-4 py-2.5 text-sm font-semibold text-white bg-emerald-700 hover:bg-emerald-800 rounded-lg transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={onUpgrade}>Upgrade to Pro</button>}
                  <button type="button" className="inline-flex min-h-11 items-center gap-1.5 px-4 py-2.5 text-sm font-semibold text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 rounded-lg transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={() => { setTab("tickets"); onTabChange?.("tickets"); }}>View published tickets</button>
                </div>
                <p className="text-sm text-slate-600">Recommendations are informational. Football outcomes are uncertain; no result is guaranteed.</p>
              </div>
            </section>
          )}
          {isAdmin && tab === "odds-policy" && (
            <Suspense fallback={<RouteLoading label="Loading policy review…" />}><ParameterSweepPicks
              date={date}
              onSelect={openSelection}
            /></Suspense>
          )}
          {tab === "market-roi" && !isAdmin && (
            <section className="rounded-xl border border-slate-200 bg-white px-4 py-6 text-base leading-relaxed text-slate-600" role="status" aria-label="Market edge access">
              <h2 className="text-lg font-bold text-slate-900">Market edge is an admin report</h2>
              <p className="mt-1">The market scan and its publication evidence are available to administrators only. No result is hidden from a report you can open.</p>
            </section>
          )}
          {isAdmin && tab === "market-roi" && (
            <>
              {(marketRoiRefreshing || (marketRoi && marketRoi.target_date !== (marketRoiRequestDate ?? date))) && (
                <p className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-base leading-relaxed text-amber-900" role="status">
                  {marketRoiRefreshing ? `Refreshing market scan for ${marketRoiRequestDate ?? date}… ` : ""}
                  {marketRoi && marketRoi.target_date !== (marketRoiRequestDate ?? date)
                    ? `Showing the captured scan for ${marketRoi.target_date} until the ${marketRoiRequestDate ?? date} scan completes.`
                    : "The market report may briefly show the last captured scan."}
                </p>
              )}
              <Suspense fallback={<RouteLoading label="Loading market report…" />}><MarketRoiDaily data={marketRoi} error={marketRoiError} /></Suspense>
            </>
          )}
          {isAdmin && tab === "passed" && (
            <PassedMatches rows={rejected} onSelect={openSelection} />
          )}
          {tab === "passed" && !isAdmin && (
            <section className="rounded-xl border border-slate-200 bg-white px-4 py-6 text-base leading-relaxed text-slate-600" role="status" aria-label="Rejection ledger access">
              <h2 className="text-lg font-bold text-slate-900">Rejection ledger is an admin report</h2>
              <p className="mt-1">The full rejection audit is available to administrators only.</p>
            </section>
          )}
          {tab === "tickets" && (
            <>
              {isAdmin && generationUnavailable && (
                <section className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-4 space-y-3" role="status" aria-label="Pipeline diagnostics">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="space-y-1">
                      <span className="inline-flex items-center rounded-full border border-amber-200 bg-white px-2.5 py-1 text-sm font-semibold text-amber-800">{pipelineStateBadge}</span>
                      <h3 className="text-sm font-bold text-slate-900">{pipelineStateTitle}</h3>
                    </div>
                    {data?.pipeline_run_id != null && <span className="font-mono text-sm tabular-nums text-slate-600">Run {data.pipeline_run_id}</span>}
                  </div>
                  <p className="text-sm leading-relaxed text-amber-900">
                    {pipelineActive
                      ? `Current stage: ${formatStage(data?.pipeline_current_stage ?? "starting")}. This page refreshes automatically while the persisted run advances.`
                      : data?.pipeline_run_id != null
                        ? `No generation record exists. Last stage: ${formatStage(data?.pipeline_current_stage ?? "unknown")}.${data?.pipeline_error ? ` ${data.pipeline_error}` : " The automation watchdog will retry a stale incomplete run within its bounded safety limit."}`
                        : date === TODAY
                          ? "MatchSlip checks the latest due 00:15 or 05:00 CAT window on startup and every five minutes. If it was missed, it queues one full catch-up automatically."
                          : "The ticket cards are intentionally hidden because there is no evidence that candidate generation or publication ran for this date."}
                  </p>
                </section>
              )}
              {isAdmin && generationFinishedWithoutTickets && (
                <section className="rounded-xl border border-slate-200 bg-white overflow-hidden" role="status" aria-label="Publication diagnostics">
                  <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 px-4 py-4">
                    <div className="space-y-1">
                      <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-sm font-semibold text-amber-800">Partial · no ticket published</span>
                      <h3 className="text-sm font-bold text-slate-900">Candidates were found, but none passed every publication gate.</h3>
                    </div>
                    <span className="font-mono text-sm tabular-nums text-slate-600">Generation {data?.generation_id}</span>
                  </div>
                  <div className="px-4 py-4 space-y-4">
                    <div className="grid gap-2 sm:grid-cols-5" aria-label="Candidate publication funnel">
                      <FunnelStep value={data?.qualified_pool ?? 0} label="model candidates" />
                      <FunnelStep value={matches.length} label="Q ≥75 selections" />
                      <FunnelStep value={qScoreMatchCount} label="distinct matches" />
                      <FunnelStep value={q85Count} label="Q ≥85 selections" />
                      <FunnelStep value={0} label="published tickets" blocked />
                    </div>
                    {leadingRejectionReasons.length > 0 && (
                      <div className="space-y-2">
                        <strong className="block text-sm font-semibold uppercase tracking-wide text-slate-600">Leading gate failures</strong>
                        <div className="flex flex-wrap gap-2">
                          {leadingRejectionReasons.map(([reason, count]) => (
                            <span key={reason} className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-sm text-slate-600"><b className="font-mono tabular-nums text-slate-900">{count}</b> {reasonLabel(reason)}</span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </section>
              )}
              {isAdmin && (data?.superseded_versions?.length ?? 0) > 0 && (
                <div className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-800">
                  <strong className="text-sky-900">Latest versions shown.</strong> Earlier published tickets remain immutable in history; regenerated tickets may have different legs.
                </div>
              )}

              {publicPublishedTickets.length > 0 && (
                <section className="rounded-xl border border-slate-200 bg-white overflow-hidden">
                  <header className="flex flex-col gap-1 border-b border-slate-200 px-4 py-4 sm:flex-row sm:items-end sm:justify-between">
                    <div>
                      <strong className="block text-sm font-bold uppercase tracking-wide text-slate-600">Published accumulator tickets</strong>
                      <small className="block mt-1 text-sm text-slate-600">{canExploreMarkets ? `Combined odds, estimated chance, and full legs for ${publicPublishedTickets.length} published tier${publicPublishedTickets.length === 1 ? "" : "s"}.` : `Match legs and settlement status for ${publicPublishedTickets.length} published tier${publicPublishedTickets.length === 1 ? "" : "s"}. Pro reveals the selections, odds and model evidence.`}</small>
                    </div>
                  </header>
                  <div className="p-4 space-y-4">
                    {!canExploreMarkets && (
                      <div className="flex flex-col gap-3 rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between" role="note">
                        <div className="min-w-0">
                          <strong className="block text-sm text-sky-900">Unlock the published selections</strong>
                          <span className="block text-sm text-sky-800">Pro shows each leg’s market, captured odds, model chance and evidence—plus every System pick behind these tickets.</span>
                        </div>
                        {onUpgrade && <button type="button" className="inline-flex shrink-0 items-center justify-center gap-1.5 px-4 py-2.5 text-sm font-semibold text-white bg-emerald-700 hover:bg-emerald-800 rounded-lg transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700" onClick={onUpgrade}>Upgrade to Pro</button>}
                      </div>
                    )}
                    {canExploreMarkets && (
                      <div className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 sm:flex-row sm:items-end sm:justify-between">
                        <label className="grid gap-1 text-sm font-medium text-slate-600">
                          Stake per ticket
                          <input
                            type="number"
                            min="0.01"
                            step="0.01"
                            value={stakePerTicket}
                            onChange={(event) => setStakePerTicket(event.target.value)}
                            placeholder="e.g. 100"
                            className="h-11 w-full max-w-[180px] rounded-lg border border-slate-200 bg-white px-3 text-sm font-mono font-semibold tabular-nums text-slate-900 placeholder:font-sans placeholder:font-normal placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-emerald-700 focus:border-emerald-700"
                          />
                        </label>
                        <span className="text-base leading-relaxed text-slate-600 max-w-xl">Potential return includes the stake; potential profit excludes it. This is a what-if calculation and does not place a bet.</span>
                      </div>
                    )}
                    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                      {publicTiers.map((tier) => (
                        <TicketCard
                          key={tier.key}
                          ticket={data?.[tier.key] ?? null}
                          tierName={tier.name}
                          tierDesc={tier.desc}
                          color={tier.color}
                          internal={isAdmin}
                          locked={!canExploreMarkets}
                          onSelectLeg={canExploreMarkets ? openTicketLeg : undefined}
                          flatStake={flatStakeForTicket(data?.[tier.key] ?? null)}
                          showMarketSelections={canExploreMarkets}
                        />
                      ))}
                    </div>
                  </div>
                </section>
              )}
            </>
          )}

          {!isAdmin && tab === "tickets" && !error && data && publicPublishedTickets.length === 0 && (
            <section className="rounded-xl border border-slate-200 bg-white px-4 py-8 text-center space-y-2" role="status">
              <h3 className="text-sm font-bold text-slate-900">No published recommendations for this date</h3>
              <p className="text-base leading-relaxed text-slate-600 max-w-xl mx-auto">Recommendations appear here only when the publication process has produced a ticket for the selected date.</p>
            </section>
          )}
        </>
      )}
      {detail && (
        <SelectionDetail
          selection={detail.selection}
          modelVersion={detail.modelVersion}
          publishedAt={detail.publishedAt}
          pricing={detail.pricing}
          canViewMarketPrices={canExploreMarkets}
          internal={isAdmin}
          onClose={() => setDetail(null)}
          onOpenMatch={canExploreMarkets ? onOpenMatch : undefined}
        />
      )}
    </div>
  );
}

function ViewIntro({ eyebrow, title, body }: { eyebrow: string; title: string; body: string }) {
  return (
    <div className="space-y-1">
      <span className="text-sm font-bold uppercase tracking-wide text-emerald-700">{eyebrow}</span>
      <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">{title}</h2>
      <p className="text-base leading-relaxed text-slate-600 max-w-3xl">{body}</p>
    </div>
  );
}

function BriefFact({ label, value, attention = false }: { label: string; value: string; attention?: boolean }) {
  return (
    <div className={`rounded-lg border px-3 py-2 ${attention ? "border-amber-200 bg-amber-50" : "border-slate-200 bg-slate-50"}`}>
      <span className="block text-sm font-medium text-slate-600">{label}</span>
      <b className={`mt-0.5 block text-sm font-semibold ${attention ? "text-amber-900" : "text-slate-900"}`}>{value}</b>
    </div>
  );
}

function RouteLoading({ label }: { label: string }) {
  return <div className="rounded-xl border border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-600">{label}</div>;
}

function LockedFeature({ title, body }: { title: string; body: string }) {
  return (
    <li className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
      <strong className="block text-sm text-slate-900">{title}</strong>
      <span className="mt-1 block text-base leading-relaxed text-slate-600">{body}</span>
    </li>
  );
}

function FunnelStep({ value, label, blocked = false }: { value: number; label: string; blocked?: boolean }) {
  return (
    <div className={`rounded-lg border px-3 py-3 text-center ${blocked ? "border-amber-200 bg-amber-50" : "border-slate-200 bg-slate-50"}`}>
      <b className={`block font-mono text-xl font-bold tabular-nums ${blocked ? "text-amber-900" : "text-slate-900"}`}>{value}</b>
      <small className={`mt-1 block text-sm ${blocked ? "text-amber-800" : "text-slate-600"}`}>{label}</small>
    </div>
  );
}

function PassedMatches({ rows, onSelect }: { rows: SelectionSummary[]; onSelect: (row: SelectionSummary) => void }) {
  const [filters, setFilters] = useState({ selection: "all", qScore: "all", odds: "all" });
  const rejectionOutcome = (result: SelectionSummary["result"]) => {
    if (result === "lost") return { label: "Passed", tone: "passed" };
    if (result === "won") return { label: "Failed", tone: "failed" };
    if (result === "void") return { label: "Void", tone: "void" };
    return { label: "Pending", tone: "pending" };
  };

  const filteredRows = rows.filter(row => {
    const qScoreMatches = filters.qScore === "all"
      || (filters.qScore === "under-50" && row.q_score < 50)
      || (filters.qScore === "50-59" && row.q_score >= 50 && row.q_score < 60)
      || (filters.qScore === "60-69" && row.q_score >= 60 && row.q_score < 70)
      || (filters.qScore === "70-plus" && row.q_score >= 70);
    const oddsMatches = filters.odds === "all"
      || (filters.odds === "unavailable" && row.best_odds == null)
      || (filters.odds === "under-1-5" && row.best_odds != null && row.best_odds < 1.5)
      || (filters.odds === "1-5-2" && row.best_odds != null && row.best_odds >= 1.5 && row.best_odds < 2)
      || (filters.odds === "2-3" && row.best_odds != null && row.best_odds >= 2 && row.best_odds < 3)
      || (filters.odds === "3-plus" && row.best_odds != null && row.best_odds >= 3);
    return (filters.selection === "all" || row.selection === filters.selection)
      && qScoreMatches && oddsMatches;
  });
  const settledRows = filteredRows.filter(row => row.result === "won" || row.result === "lost" || row.result === "void");
  const wins = settledRows.filter(row => row.result === "won").length;
  const losses = settledRows.filter(row => row.result === "lost").length;
  const roiRows = settledRows.filter(row => row.best_odds != null && row.best_odds > 1);
  const netUnits = roiRows.reduce((total, row) => total + (row.result === "won" ? (row.best_odds ?? 1) - 1 : row.result === "lost" ? -1 : 0), 0);
  const hitRate = wins + losses > 0 ? `${((wins / (wins + losses)) * 100).toFixed(1)}%` : "—";
  const roi = roiRows.length ? `${((netUnits / roiRows.length) * 100).toFixed(1)}%` : "—";
  const fmtUnits = (value: number) => `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(1)}`;
  const unitsSaved = roiRows.filter(row => row.result === "lost").length;
  const unitsForfeited = roiRows.reduce((total, row) => total + (row.result === "won" ? (row.best_odds ?? 1) - 1 : 0), 0);
  const weightedNet = unitsSaved - unitsForfeited;
  const oddsBands = [
    { label: "Under 1.50", test: (odds: number) => odds < 1.5 },
    { label: "1.50–1.99", test: (odds: number) => odds >= 1.5 && odds < 2 },
    { label: "2.00–2.99", test: (odds: number) => odds >= 2 && odds < 3 },
    { label: "3.00–5.99", test: (odds: number) => odds >= 3 && odds < 6 },
    { label: "6.00+", test: (odds: number) => odds >= 6 },
  ];
  const bandStats = oddsBands.map(band => {
    const bandPriced = filteredRows.filter(row => row.best_odds != null && row.best_odds > 1 && band.test(row.best_odds));
    const bandSettled = bandPriced.filter(row => row.result === "won" || row.result === "lost");
    const bandWins = bandSettled.filter(row => row.result === "won").length;
    const bandLosses = bandSettled.length - bandWins;
    const bandNet = bandPriced.reduce((total, row) => total + (row.result === "won" ? (row.best_odds ?? 1) - 1 : row.result === "lost" ? -1 : 0), 0);
    const bandWeighted = bandSettled.reduce((total, row) => total + (row.result === "won" ? -((row.best_odds ?? 1) - 1) : 1), 0);
    return {
      label: band.label,
      priced: bandPriced.length,
      settled: bandSettled.length,
      wins: bandWins,
      losses: bandLosses,
      passRate: bandSettled.length ? `${((bandLosses / bandSettled.length) * 100).toFixed(1)}%` : "—",
      roi: bandSettled.length ? `${((bandNet / bandPriced.length) * 100).toFixed(1)}%` : "—",
      weighted: bandSettled.length ? fmtUnits(bandWeighted) : "—",
    };
  });

  const outcomeTone = (tone: string) => {
    if (tone === "passed") return "border-emerald-200 bg-emerald-50 text-emerald-700";
    if (tone === "failed") return "border-red-200 bg-red-50 text-red-700";
    if (tone === "void") return "border-amber-200 bg-amber-50 text-amber-700";
    return "border-slate-200 bg-slate-50 text-slate-600";
  };
  const resultTone = (result: SelectionSummary["result"]) => {
    if (result === "won") return "border-emerald-200 bg-emerald-50 text-emerald-700";
    if (result === "lost") return "border-red-200 bg-red-50 text-red-700";
    if (result === "void") return "border-amber-200 bg-amber-50 text-amber-700";
    return "border-slate-200 bg-slate-50 text-slate-600";
  };

  return (
    <section className="rounded-xl border border-slate-200 bg-white overflow-hidden" aria-labelledby="passed-matches-title">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 px-4 py-4">
        <div className="space-y-1">
          <span className="text-sm font-bold uppercase tracking-wide text-slate-600">Transparent rejection ledger</span>
          <h2 id="passed-matches-title" className="text-xl font-bold tracking-tight text-slate-900">Rejected opportunities and why</h2>
          <p className="text-base leading-relaxed text-slate-600">A rejection marked Passed avoided a losing result; one marked Failed excluded a winning result.</p>
        </div>
        <span className="text-sm text-slate-600"><b className="font-mono tabular-nums text-slate-900">{rows.length}</b> reviewed</span>
      </div>

      <div className="px-4 py-4 space-y-4">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between" aria-label="Filter rejection ledger and summary">
          <div className="flex flex-wrap gap-3">
            <FilterSelect label="Selection" value={filters.selection} onChange={(value) => setFilters(current => ({ ...current, selection: value }))}>
              <option value="all">All selections</option>
              {Array.from(new Set(rows.map(row => row.selection))).sort().map(selection => <option key={selection} value={selection}>{formatSelection(selection)}</option>)}
            </FilterSelect>
            <FilterSelect label="Q-score" value={filters.qScore} onChange={(value) => setFilters(current => ({ ...current, qScore: value }))}>
              <option value="all">Any score</option>
              <option value="under-50">Under 50</option>
              <option value="50-59">50–59.9</option>
              <option value="60-69">60–69.9</option>
              <option value="70-plus">70+</option>
            </FilterSelect>
            <FilterSelect label="Odds" value={filters.odds} onChange={(value) => setFilters(current => ({ ...current, odds: value }))}>
              <option value="all">Any odds</option>
              <option value="unavailable">Unavailable</option>
              <option value="under-1-5">Under 1.50</option>
              <option value="1-5-2">1.50–1.99</option>
              <option value="2-3">2.00–2.99</option>
              <option value="3-plus">3.00+</option>
            </FilterSelect>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6" aria-label="Filtered record summary">
            <SummaryStat label="W–L" value={`${wins}–${losses}`} />
            <SummaryStat label="Hit rate" value={hitRate} />
            <SummaryStat label="ROI" value={roi} />
            <SummaryStat label="Saved" value={roiRows.length ? fmtUnits(unitsSaved) : "—"} />
            <SummaryStat label="Forfeited" value={roiRows.length ? fmtUnits(-unitsForfeited) : "—"} />
            <SummaryStat label="Weighted net" value={roiRows.length ? fmtUnits(weightedNet) : "—"} />
            <small className="col-span-2 sm:col-span-3 lg:col-span-6 text-sm text-slate-600">{filteredRows.length} shown · {settledRows.length} settled · {roiRows.length} priced · weighted in flat stakes: +1 per Passed rejection, −(odds − 1) per Failed</small>
          </div>
        </div>

        <div className="space-y-2" aria-label="Rejection audit by odds band">
          <span className="text-sm font-bold uppercase tracking-wide text-slate-600">Rejection audit by odds band</span>
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
            {bandStats.map(band => (
              <div key={band.label} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600 space-y-0.5">
                <strong className="block text-slate-900">{band.label}</strong>
                <span className="block">{band.priced} priced · {band.settled} settled</span>
                <span className="block font-mono tabular-nums">W–L {band.wins}–{band.losses} · Pass {band.passRate}</span>
                <span className="block font-mono tabular-nums">ROI {band.roi} · Weighted net {band.weighted}</span>
              </div>
            ))}
          </div>
        </div>

        {rows.length === 0 ? (
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-8 text-center space-y-1">
            <strong className="block text-sm text-slate-900">No rejected candidates recorded</strong>
            <span className="block text-sm text-slate-600">When the candidate ledger is empty, there is no pass explanation to display.</span>
          </div>
        ) : filteredRows.length === 0 ? (
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-8 text-center space-y-1">
            <strong className="block text-sm text-slate-900">No records match these filters</strong>
            <span className="block text-sm text-slate-600">Adjust one or more filters to show rejection ledger records.</span>
          </div>
        ) : (
          <div className="relative overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="w-full min-w-[980px] border-collapse text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-sm uppercase tracking-wide text-slate-600">
                <tr>
                  <th className="px-3 py-2 font-semibold">Match</th>
                  <th className="px-3 py-2 font-semibold">Selection</th>
                  <th className="px-3 py-2 font-semibold">Q-score</th>
                  <th className="px-3 py-2 font-semibold">Odds</th>
                  <th className="px-3 py-2 font-semibold" data-sort-default-direction="descending">Edge</th>
                  <th className="px-3 py-2 font-semibold">Rejection reason</th>
                  <th className="px-3 py-2 font-semibold">Match result</th>
                  <th className="px-3 py-2 font-semibold">Rejection check</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredRows.map(row => {
                  const outcome = rejectionOutcome(row.result);
                  const score = row.home_goals != null && row.away_goals != null
                    ? `${row.home_goals}–${row.away_goals}`
                    : null;
                  const resultLabel = row.result
                    ? `${row.result.charAt(0).toUpperCase()}${row.result.slice(1)}`
                    : (row.match_status?.toLowerCase() === "finished" ? "Unavailable" : "Pending");
                  return (
                    <tr key={row.prediction_id} className="hover:bg-slate-50/70 align-top">
                      <td className="px-3 py-2">
                        <button type="button" className="text-left cursor-pointer hover:text-emerald-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 rounded" onClick={() => onSelect(row)}>
                          <span className="block font-semibold text-slate-900">{row.home_team} vs {row.away_team}</span>
                          <small className="block text-sm text-slate-600">{row.competition} · <span className="font-mono tabular-nums">{formatDate(row.kickoff_at)}</span> · <span className="font-mono tabular-nums">{formatKickoff(row.kickoff_at)}</span></small>
                        </button>
                      </td>
                      <td className="px-3 py-2">
                        {!selectionRepeatsMarket(row.market, row.selection) && <span className="block text-sm text-slate-600">{formatMarket(row.market)}</span>}
                        <span className={`inline-flex rounded-full border px-2 py-0.5 text-sm font-semibold ${selectionToneClass(row.selection)}`}>{formatSelection(row.selection)}</span>
                      </td>
                      <td className="px-3 py-2 font-mono font-semibold tabular-nums text-slate-900">{row.q_score.toFixed(1)}</td>
                      <td className="px-3 py-2 font-mono font-semibold tabular-nums text-slate-900">{row.best_odds == null ? "Unavailable" : row.best_odds.toFixed(2)}</td>
                      <td className="px-3 py-2 font-mono font-semibold tabular-nums text-slate-900">{row.edge == null ? "Unavailable" : `${(row.edge * 100).toFixed(1)}%`}</td>
                      <td className="px-3 py-2"><RejectionReasons reasons={row.reason_codes ?? []} /></td>
                      <td className="px-3 py-2">
                        <span className={`inline-flex rounded-full border px-2 py-0.5 text-sm font-semibold ${resultTone(row.result)}`}>{resultLabel}</span>
                        {score && <small className="block mt-1 font-mono text-sm tabular-nums text-slate-600">{score}</small>}
                      </td>
                      <td className="px-3 py-2"><span className={`inline-flex rounded-full border px-2 py-0.5 text-sm font-semibold ${outcomeTone(outcome.tone)}`}>{outcome.label}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

function FilterSelect({ label, value, onChange, children }: { label: string; value: string; onChange: (value: string) => void; children: import("react").ReactNode }) {
  return (
    <label className="grid gap-1 text-sm font-medium text-slate-600">
      {label}
      <select
        value={value}
        onChange={event => onChange(event.target.value)}
        className="h-11 min-w-[160px] rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-700 focus:border-emerald-700"
      >
        {children}
      </select>
    </label>
  );
}

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <span className="block text-sm font-medium text-slate-600">{label}</span>
      <strong className="block font-mono text-sm font-bold tabular-nums text-slate-900">{value}</strong>
    </div>
  );
}

function selectionToneClass(selection: string) {
  const tone = selectionTone(selection);
  if (tone === "positive" || tone === "home" || tone === "over" || tone === "yes") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (tone === "negative" || tone === "away" || tone === "under" || tone === "no") return "border-red-200 bg-red-50 text-red-700";
  if (tone === "draw" || tone === "neutral") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-slate-200 bg-slate-50 text-slate-700";
}
