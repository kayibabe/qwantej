import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../../auth";
import type { DailyTickets, Leg, MatchFixture, SelectionSummary, Ticket } from "../../lib/api";
import {
  fetchDailyTickets,
  fetchMatchFixtures,
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
import "./DailyOverview.css";
import {
  reasonLabel,
  TODAY,
  withRejectionEvidence,
} from "./helpers";
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
  const [matchesTotal, setMatchesTotal] = useState(0);
  const [pickedMatchTotal, setPickedMatchTotal] = useState(0);
  const [loadingMoreMatches, setLoadingMoreMatches] = useState(false);
  const [marketRoi, setMarketRoi] = useState<MarketRoiDailyData | null>(null);
  const [marketRoiError, setMarketRoiError] = useState<string | null>(null);
  const [fixtures, setFixtures] = useState<MatchFixture[]>([]);
  const [candidatesLoaded, setCandidatesLoaded] = useState(false);
  const [rejectedLoaded, setRejectedLoaded] = useState(false);
  const [tab, setTab] = useState<DailyTab>(initialTab);
  const [loading, setLoading] = useState(false);
  const firstLoad = useRef(true);
  const loadedKey = useRef<string | null>(null);
  const requestVersion = useRef(0);
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

  // A shared link may name a tab this role cannot see; fall back to the
  // start of the funnel rather than rendering an empty workspace.
  useEffect(() => {
    if (authLoading || mode !== "overview") return;
    if (tab === "passed" && !isAdmin) {
      setTab("fixtures");
      onTabChange?.("fixtures");
    }
  }, [authLoading, isAdmin, mode, onTabChange, tab]);

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
      ? `${mode}:${targetDate}:${roleKey}`
      : `${mode}:${targetDate}:${tab}:${roleKey}`;
    if (!force && loadedKey.current === requestedKey) return;
    const request = ++requestVersion.current;
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
      const marketRoiPromise = wantsMarketRoi
        ? import("./MarketRoiDaily").then(({ fetchDailyMarketRoi }) => fetchDailyMarketRoi(targetDate)).catch((cause) => {
          const message = cause instanceof Error ? cause.message : "Daily market ROI is unavailable";
          if (request === requestVersion.current) setMarketRoiError(message);
          return null;
        })
        : Promise.resolve(null);
      const [tickets, fixtureRows, allRows, rejectedRows, marketRoiRows] = await Promise.all([
        wantsTickets ? fetchDailyTickets(targetDate) : Promise.resolve(null),
        wantsFixtures ? fetchMatchFixtures(targetDate) : Promise.resolve(null),
        wantsCandidates ? fetchQualifiedSelections(targetDate) : Promise.resolve(null),
        wantsRejected ? fetchRejectedSelections(targetDate) : Promise.resolve(null),
        marketRoiPromise,
      ]);
      if (request !== requestVersion.current) return;
      setError(null);
      if (tickets) setData(tickets);
      if (fixtureRows) setFixtures(fixtureRows);
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
      }
      loadedKey.current = requestedKey;
      setDataCheckedAt(new Date());
    } catch (e) {
      if (request !== requestVersion.current) return;
      setError(
        e instanceof Error ? e.message : isAdmin ? "Failed to load research ledger" : "Failed to load recommendations",
      );
    } finally {
      if (request === requestVersion.current) {
        setLoading(false);
        firstLoad.current = false;
      }
    }
  }, [canExploreMarkets, isAdmin, mode, tab]);

  const loadMoreMatches = async () => {
    if (loadingMoreMatches || matches.length >= matchesTotal) return;
    setLoadingMoreMatches(true);
    try {
      const page = await fetchQualifiedSelections(date, 75, matches.length);
      setMatches((current) => withRejectionEvidence(
        [...current, ...page.rows.filter((row) => !current.some((existing) => existing.prediction_id === row.prediction_id))],
        rejected,
      ));
      setMatchesTotal(page.total);
      setPickedMatchTotal(page.matchTotal);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "More candidate selections could not be loaded");
    } finally {
      setLoadingMoreMatches(false);
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

  // Describe each tier by the rules its generation actually applied.
  const fairPriced = data?.pricing === "market";
  const publicTiers = [
    {
      key: "conservative" as const,
      name: "Conservative",
      desc: fairPriced ? "3 legs · 2.00–2.60× · review first" : "Q ≥85 · 3–6 legs · 3–5×",
      color: "var(--conservative)",
    },
    {
      key: "balanced" as const,
      name: "Balanced",
      desc: fairPriced ? "3 legs · 3.00–4.00× · secondary option" : "Q ≥80 · 60% Grade A/A+",
      color: "var(--balanced)",
    },
  ];

  const matchGroups = Object.entries(matches.reduce<Record<number, SelectionSummary[]>>((groups, row) => {
    (groups[row.match_id] ??= []).push(row);
    return groups;
  }, {})).map(([id, rows]) => [Number(id), rows] as [number, SelectionSummary[]]);

  return (
    <>
      <div className="meta-bar">
        <div>
          <h1 className="meta-date">
            {mode === "overview"
              ? date === TODAY ? "Today" : formatDate(date)
              : formatDate(data ? data.target_date : date)}
          </h1>
          {mode === "overview" && <p className="overview-date">
            {date === TODAY && <span className="event-date">{data ? formatDate(data.target_date) : formatDate(date)}</span>}
            {dataCheckedAt && <span className="overview-updated-at" title="Time when recommendation data was last checked">
              Data checked {dataCheckedAt.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Africa/Blantyre" })} CAT
            </span>}
          </p>}
          <p className="research-disclaimer">
            {isAdmin
              ? "Internal research and paper trading only. No ticket is a promise of profit."
              : "Recommendations are informational. Football outcomes are uncertain; no result is guaranteed."}
          </p>
        </div>
        {isAdmin && mode === "overview" && data && (
          <div className="meta-context" aria-label="Publication context">
            <span className="meta-pool" title="Candidates that passed the strict publication quality gate before ticket construction">
              {data.qualified_pool} strict publication candidates
            </span>
            {(data.horizon_pool ?? 0) > 0 && <span title="Additional candidates admitted by the bounded rolling-horizon fallback">+{data.horizon_pool} rolling-horizon</span>}
            {Object.keys(data.relaxed_ticket_types ?? {}).length > 0 && <span title="One or more tiers used the bounded relaxation policy">Bounded relaxation</span>}
            {latestPublication && (
              <span>
                Published{" "}
                {new Date(latestPublication).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            )}
            {modelVersions.length > 0 && (
              <span>Model {modelVersions.join(", ")}</span>
            )}
          </div>
        )}
      </div>

      {mode === "overview" && data && (
        <>
          <section className="today-brief" aria-label="Today decision brief">
            <div className="today-brief-copy">
              <strong>{briefTitle}</strong>
              <p>{briefBody}</p>
            </div>
            <div className="today-brief-facts">
              <div className={`today-brief-fact${publishedCount > 0 ? "" : " attention"}`}>
                <span>Publication</span>
                <b>{latestPublicationTime ? `${latestPublicationTime} CAT` : pipelineStateBadge}</b>
              </div>
              {dataCheckedAt && (
                <div className="today-brief-fact">
                  <span>Checked</span>
                  <b>{dataCheckedAt.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Africa/Blantyre" })} CAT</b>
                </div>
              )}
              <div className="today-brief-fact">
                <span>Pricing</span>
                <b>{data ? (fairPriced ? "Fair price" : "Model price") : "—"}</b>
              </div>
              {isAdmin && modelVersions.length > 0 && (
                <div className="today-brief-fact">
                  <span>Model</span>
                  <b>{modelVersions.join(", ")}</b>
                </div>
              )}
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
        <div className="error-bar" role="alert">
          <div>
            <strong>{data && mode === "overview"
              ? "Showing the last loaded recommendations"
              : isAdmin ? "Internal research ledger unavailable" : "Recommendations unavailable"}</strong>
            <span>{data && mode === "overview"
              ? `The latest refresh failed${dataCheckedAt ? `; this view was loaded at ${dataCheckedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : ""}. ${error}`
              : error}</span>
          </div>
          <button onClick={async () => { setRetrying(true); try { await load(date, true); } finally { setRetrying(false); } }} disabled={retrying}>
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
          {!isOverviewWithRibbon && dailyTabs.length > 1 && <nav className="daily-tabs" aria-label="Daily ticket workspace">
            {dailyTabs.map(([key, label]) => (
              <button
                key={key}
                className={tab === key ? "active" : ""}
                onClick={() => { setTab(key); onTabChange?.(key); }}
              >
                {label}
                {tabCounts[key] != null && <span className="daily-tab-count">{tabCounts[key]}</span>}
              </button>
            ))}
          </nav>}
          {tab === "fixtures" && <div className="view-intro"><span className="eyebrow">Fixtures</span><h2 className="section-title">All fixtures for this date</h2><p>Every fixture scheduled for this date, with competition, kickoff time, and current status.</p></div>}
          {tab === "picks" && canExploreMarkets && <div className="view-intro"><span className="eyebrow">System picks</span><h2 className="section-title">System picks for this date</h2><p>Every Q ≥75 selection the model qualified for this date, grouped by match. A pick appearing here does not mean it made a published accumulator.</p></div>}
          {tab === "tickets" && <div className="view-intro"><span className="eyebrow">Accumulator tickets</span><h2 className="section-title">Tickets assembled from this date&rsquo;s picks</h2><p>{canExploreMarkets ? "Each published tier is a fixed combination of the system’s qualified picks. Expand a leg to inspect its evidence; the stake field is a what-if calculation only." : "Each published tier is a fixed combination of the system’s qualified picks. On Free you can review every match leg and its settlement status; Pro opens the selections and their evidence."}</p></div>}
          {tab === "fixtures" && <Suspense fallback={<div className="route-loading">Loading fixtures…</div>}><FixtureExplorer fixtures={fixtures} /></Suspense>}
          {tab === "picks" && canExploreMarkets && <Suspense fallback={<div className="route-loading">Loading system picks…</div>}><AllMatches rows={matchGroups} totalSelections={matchesTotal} loadedSelections={matches.length} loadingMore={loadingMoreMatches} onLoadMore={loadMoreMatches} onSelect={openSelection} /></Suspense>}
          {tab === "picks" && !canExploreMarkets && (
            <section className="plan-locked-panel" aria-labelledby="plan-locked-picks-title">
              <div className="plan-locked-copy">
                <span className="plan-locked-kicker">Pro workspace</span>
                <h2 id="plan-locked-picks-title">See every qualified selection, not just the ticket</h2>
                <p>System picks list each Q ≥75 selection behind this date’s tickets. Pro opens the full ledger for every match, with the evidence recorded when the pick qualified.</p>
                <ul className="plan-locked-features">
                  <li><strong>Market and selection</strong><span>Exactly what the model qualified, grouped by match.</span></li>
                  <li><strong>Price and model chance</strong><span>Captured bookmaker odds next to the model’s probability.</span></li>
                  <li><strong>Spread and edge</strong><span>How far the models disagreed and where the price sat above fair.</span></li>
                </ul>
                <div className="plan-locked-actions">
                  {onUpgrade && <button className="btn-primary" onClick={onUpgrade}>Upgrade to Pro</button>}
                  <button className="btn-ghost" onClick={() => { setTab("tickets"); onTabChange?.("tickets"); }}>View published tickets</button>
                </div>
                <p className="plan-locked-note">Recommendations are informational. Football outcomes are uncertain; no result is guaranteed.</p>
              </div>
            </section>
          )}
          {isAdmin && tab === "odds-policy" && (
            <Suspense fallback={<div className="route-loading">Loading policy review…</div>}><ParameterSweepPicks
              date={date}
              onSelect={openSelection}
            /></Suspense>
          )}
          {isAdmin && tab === "market-roi" && <Suspense fallback={<div className="route-loading">Loading market report…</div>}><MarketRoiDaily data={marketRoi} error={marketRoiError} /></Suspense>}
          {isAdmin && tab === "passed" && (
            <PassedMatches rows={rejected} onSelect={openSelection} />
          )}
          {tab === "tickets" && (
            <>
              {isAdmin && generationUnavailable && (
                <section className="publication-diagnostics" role="status" aria-label="Pipeline diagnostics">
                  <div className="publication-diagnostics-heading">
                    <div>
                      <span className="generation-status-badge">{pipelineStateBadge}</span>
                      <h3>{pipelineStateTitle}</h3>
                    </div>
                    {data?.pipeline_run_id != null && <span>Run {data.pipeline_run_id}</span>}
                  </div>
                  <p>
                    {pipelineActive
                      ? `Current stage: ${formatStage(data?.pipeline_current_stage ?? "starting")}. This page refreshes automatically while the persisted run advances.`
                      : data?.pipeline_run_id != null
                        ? `No generation record exists. Last stage: ${formatStage(data?.pipeline_current_stage ?? "unknown")}.${data?.pipeline_error ? ` ${data.pipeline_error}` : " The automation watchdog will retry a stale incomplete run within its bounded safety limit."}`
                        : date === TODAY
                          ? "QwanEj checks the latest due 00:15 or 05:00 CAT window on startup and every five minutes. If it was missed, it queues one full catch-up automatically."
                          : "The ticket cards are intentionally hidden because there is no evidence that candidate generation or publication ran for this date."}
                  </p>
                </section>
              )}
              {isAdmin && generationFinishedWithoutTickets && (
                <section className="publication-diagnostics" role="status" aria-label="Publication diagnostics">
                  <div className="publication-diagnostics-heading">
                    <div>
                      <span className="generation-status-badge">Partial · no ticket published</span>
                      <h3>Candidates were found, but none passed every publication gate.</h3>
                    </div>
                    <span>Generation {data?.generation_id}</span>
                  </div>
                  <div className="publication-funnel" aria-label="Candidate publication funnel">
                    <span><b>{data?.qualified_pool ?? 0}</b><small>model candidates</small></span>
                    <i aria-hidden="true">→</i>
                    <span><b>{matches.length}</b><small>Q ≥75 selections</small></span>
                    <i aria-hidden="true">→</i>
                    <span><b>{qScoreMatchCount}</b><small>distinct matches</small></span>
                    <i aria-hidden="true">→</i>
                    <span><b>{q85Count}</b><small>Q ≥85 selections</small></span>
                    <i aria-hidden="true">→</i>
                    <span className="blocked"><b>0</b><small>published tickets</small></span>
                  </div>
                  {leadingRejectionReasons.length > 0 && (
                    <div className="publication-reasons">
                      <strong>Leading gate failures</strong>
                      {leadingRejectionReasons.map(([reason, count]) => (
                        <span key={reason}><b>{count}</b> {reasonLabel(reason)}</span>
                      ))}
                    </div>
                  )}
                </section>
              )}
              {isAdmin && (data?.superseded_versions?.length ?? 0) > 0 && (
                <div className="ticket-version-notice">
                  <strong>Latest versions shown.</strong> Earlier published tickets remain immutable in history; regenerated tickets may have different legs.
                </div>
              )}

              {publicPublishedTickets.length > 0 && <section className="published-ticket-tiers">
                <header className="published-ticket-tiers-heading"><span><strong>Published accumulator tickets</strong><small>{canExploreMarkets ? `Combined odds, estimated chance, and full legs for ${publicPublishedTickets.length} published tier${publicPublishedTickets.length === 1 ? "" : "s"}.` : `Match legs and settlement status for ${publicPublishedTickets.length} published tier${publicPublishedTickets.length === 1 ? "" : "s"}. Pro reveals the selections, odds and model evidence.`}</small></span></header>
                {!canExploreMarkets && (
                  <div className="plan-upsell" role="note">
                    <div>
                      <strong>Unlock the published selections</strong>
                      <span>Pro shows each leg’s market, captured odds, model chance and evidence—plus every System pick behind these tickets.</span>
                    </div>
                    {onUpgrade && <button className="btn-primary" onClick={onUpgrade}>Upgrade to Pro</button>}
                  </div>
                )}
                {canExploreMarkets && <div className="stake-planner-controls">
                  <label className="bankroll-input">
                    Stake per ticket
                    <input
                      type="number"
                      min="0.01"
                      step="0.01"
                      value={stakePerTicket}
                      onChange={(event) => setStakePerTicket(event.target.value)}
                      placeholder="e.g. 100"
                    />
                  </label>
                  <span>Potential return includes the stake; potential profit excludes it. This is a what-if calculation and does not place a bet.</span>
                </div>}
                <div className="ticket-grid public-ticket-grid">
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
              </section>}
            </>
          )}

          {!isAdmin && tab === "tickets" && !error && data && publicPublishedTickets.length === 0 && (
            <section className="publication-diagnostics" role="status">
              <div className="publication-diagnostics-heading"><h3>No published recommendations for this date</h3></div>
              <p>Recommendations appear here only when the publication process has produced a ticket for the selected date.</p>
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
    </>
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

  return <section className="passed-matches-panel" aria-labelledby="passed-matches-title">
    <div className="section-heading">
      <div><span className="eyebrow">Transparent rejection ledger</span><h2 id="passed-matches-title">Rejected opportunities and why</h2><span className="section-note">A rejection marked Passed avoided a losing result; one marked Failed excluded a winning result.</span></div>
      <span className="section-note"><b>{rows.length}</b> reviewed</span>
    </div>
    <div className="passed-matches-tools" aria-label="Filter rejection ledger and summary">
      <div className="passed-matches-filters">
        <label>Selection<select value={filters.selection} onChange={event => setFilters(current => ({ ...current, selection: event.target.value }))}><option value="all">All selections</option>{Array.from(new Set(rows.map(row => row.selection))).sort().map(selection => <option key={selection} value={selection}>{formatSelection(selection)}</option>)}</select></label>
        <label>Q-score<select value={filters.qScore} onChange={event => setFilters(current => ({ ...current, qScore: event.target.value }))}><option value="all">Any score</option><option value="under-50">Under 50</option><option value="50-59">50–59.9</option><option value="60-69">60–69.9</option><option value="70-plus">70+</option></select></label>
        <label>Odds<select value={filters.odds} onChange={event => setFilters(current => ({ ...current, odds: event.target.value }))}><option value="all">Any odds</option><option value="unavailable">Unavailable</option><option value="under-1-5">Under 1.50</option><option value="1-5-2">1.50–1.99</option><option value="2-3">2.00–2.99</option><option value="3-plus">3.00+</option></select></label>
      </div>
      <div className="passed-matches-summary" aria-label="Filtered record summary">
        <div><span>W–L</span><strong>{wins}–{losses}</strong></div>
        <div><span>Hit rate</span><strong>{hitRate}</strong></div>
        <div><span>ROI</span><strong>{roi}</strong></div>
        <div><span>Saved</span><strong>{roiRows.length ? fmtUnits(unitsSaved) : "—"}</strong></div>
        <div><span>Forfeited</span><strong>{roiRows.length ? fmtUnits(-unitsForfeited) : "—"}</strong></div>
        <div><span>Weighted net</span><strong>{roiRows.length ? fmtUnits(weightedNet) : "—"}</strong></div>
        <small>{filteredRows.length} shown · {settledRows.length} settled · {roiRows.length} priced · weighted in flat stakes: +1 per Passed rejection, −(odds − 1) per Failed</small>
      </div>
    </div>
    <div className="odds-band-audit" aria-label="Rejection audit by odds band">
      <span className="odds-band-audit-title">Rejection audit by odds band</span>
      <div className="odds-band-audit-grid">
        {bandStats.map(band => <div key={band.label} className="odds-band-audit-card">
          <strong>{band.label}</strong>
          <span>{band.priced} priced · {band.settled} settled</span>
          <span>W–L {band.wins}–{band.losses} · Pass {band.passRate}</span>
          <span>ROI {band.roi} · Weighted net {band.weighted}</span>
        </div>)}
      </div>
    </div>
    {rows.length === 0 ? <div className="decision-empty"><strong>No rejected candidates recorded</strong><span>When the candidate ledger is empty, there is no pass explanation to display.</span></div> : filteredRows.length === 0 ? <div className="decision-empty"><strong>No records match these filters</strong><span>Adjust one or more filters to show rejection ledger records.</span></div> : <div className="decision-table-wrap passed-matches-table-wrap">
      <table className="decision-table passed-matches-table">
        <thead><tr><th>Match</th><th>Selection</th><th>Q-score</th><th>Odds</th><th data-sort-default-direction="descending">Edge</th><th>Rejection reason</th><th>Match result</th><th>Rejection check</th></tr></thead>
        <tbody>{filteredRows.map(row => {
          const outcome = rejectionOutcome(row.result);
          const score = row.home_goals != null && row.away_goals != null
            ? `${row.home_goals}–${row.away_goals}`
            : null;
          const resultLabel = row.result
            ? `${row.result.charAt(0).toUpperCase()}${row.result.slice(1)}`
            : (row.match_status?.toLowerCase() === "finished" ? "Unavailable" : "Pending");
          return <tr key={row.prediction_id}>
            <td><button className="decision-match" onClick={() => onSelect(row)}>{row.home_team} vs {row.away_team}<small>{row.competition} · <span className="match-date">{formatDate(row.kickoff_at)}</span> · <span className="match-kickoff">{formatKickoff(row.kickoff_at)}</span></small></button></td>
            <td>{!selectionRepeatsMarket(row.market, row.selection) && <span className="decision-market">{formatMarket(row.market)}</span>}<span className={`market-pick ${selectionTone(row.selection)}`}>{formatSelection(row.selection)}</span></td>
            <td className="passed-match-metric">{row.q_score.toFixed(1)}</td>
            <td className="passed-match-metric">{row.best_odds == null ? "Unavailable" : row.best_odds.toFixed(2)}</td>
            <td className="passed-match-metric">{row.edge == null ? "Unavailable" : `${(row.edge * 100).toFixed(1)}%`}</td>
            <td className="passed-match-reason-cell"><RejectionReasons reasons={row.reason_codes ?? []} /></td>
            <td><span className={`result-pill ${row.result ?? "pending"}`}>{resultLabel}</span>{score && <small className="result-score">{score}</small>}</td>
            <td><span className={`rejection-outcome-pill ${outcome.tone}`}>{outcome.label}</span></td>
          </tr>;
        })}</tbody>
      </table>
    </div>}
  </section>
}
