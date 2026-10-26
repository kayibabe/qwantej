import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../../auth";
import type { CustomAccumulator as ApiCustomAccumulator, DailyTickets, Leg, MatchFixture, SelectionSummary, Ticket } from "../../lib/api";
import {
  createCustomAccumulator,
  fetchDailyTickets,
  fetchMatchFixtures,
  fetchQualifiedSelections,
  fetchRejectedSelections,
  fetchCustomAccumulators,
  formatDate,
  formatKickoff,
  formatMarket,
  formatSelection,
  selectionRepeatsMarket,
  selectionTone,
  updateCustomAccumulator,
  formatStage,
} from "../../lib/api";
import TicketCard from "../../components/TicketCard";
import RejectionReasons from "../../components/RejectionReasons";
import SelectionDetail, {
  type DetailSelection,
} from "../../components/SelectionDetail";
import type { MarketRoiDailyData } from "./MarketRoiDaily";
import { TicketGridSkeleton } from "./TicketGridSkeleton";
import "./DailyOverview.css";
import {
  accumulatorBlockers,
  apiAccumulatorToUi,
  reasonLabel,
  TODAY,
  withRejectionEvidence,
} from "./helpers";
import type { CustomAccumulator, DailyTab, DailyTicketsPageProps } from "./types";

const ParameterSweepPicks = lazy(() => import("./ParameterSweepPicks").then((module) => ({ default: module.ParameterSweepPicks })));
const DailyMatchPicks = lazy(() => import("./MarketRoiDaily").then((module) => ({ default: module.DailyMatchPicks })));
const MarketRoiDaily = lazy(() => import("./MarketRoiDaily").then((module) => ({ default: module.MarketRoiDaily })));
const AllMatches = lazy(() => import("./AllMatches").then((module) => ({ default: module.AllMatches })));
const FixtureExplorer = lazy(() => import("./FixtureExplorer").then((module) => ({ default: module.FixtureExplorer })));
const PublishedSelections = lazy(() => import("./PublishedSelections"));
const PublishedHistory = lazy(() => import("./PublishedHistory"));
const PersonalJournal = lazy(() => import("../Tracker"));

export default function DailyTicketsPage({ date, initialTab = "tickets", onOpenMatch, onOpenTracker, onTabChange }: DailyTicketsPageProps & { onOpenMatch?: (matchId: number, predictionId?: number) => void }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const canExploreMarkets = isAdmin || user?.plan === "pro";
  const canAccessDailyPicks = isAdmin || user?.plan === "pro";
  const [data, setData] = useState<DailyTickets | null>(null);
  const [rejected, setRejected] = useState<SelectionSummary[]>([]);
  const [matches, setMatches] = useState<SelectionSummary[]>([]);
  const [matchesTotal, setMatchesTotal] = useState(0);
  const [loadingMoreMatches, setLoadingMoreMatches] = useState(false);
  const [marketRoi, setMarketRoi] = useState<MarketRoiDailyData | null>(null);
  const [marketRoiError, setMarketRoiError] = useState<string | null>(null);
  const [marketRoiLoading, setMarketRoiLoading] = useState(false);
  const [fixtures, setFixtures] = useState<MatchFixture[]>([]);
  const [tab, setTab] = useState<DailyTab>(initialTab);
  const [custom, setCustom] = useState<CustomAccumulator[]>(() => {
    return [];
  });
  const [loading, setLoading] = useState(false);
  const firstLoad = useRef(true);
  const requestVersion = useRef(0);
  const marketRoiResolved = useRef(false);
  const [dataCheckedAt, setDataCheckedAt] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [detail, setDetail] = useState<{
    selection: DetailSelection;
    modelVersion?: string;
    pricing?: "market" | "model";
    publishedAt?: string;
  } | null>(null);
  const [selectionMessage, setSelectionMessage] = useState<string | null>(null);
  const [stakePerTicket, setStakePerTicket] = useState("");

  useEffect(() => { setTab(initialTab); }, [initialTab]);

  const flatStakeForTicket = (ticket: Ticket | null) => {
    const stake = Number(stakePerTicket);
    if (!ticket || !Number.isFinite(stake) || stake <= 0 || ticket.combined_odds == null || ticket.combined_odds <= 1) return null;
    return stake;
  };

  const load = useCallback(async (targetDate: string) => {
    const request = ++requestVersion.current;
    if (firstLoad.current) setLoading(true);
    try {
      const wantsTickets = initialTab === "tickets";
      const wantsFixtures = initialTab === "matches" && !canExploreMarkets;
      const wantsCandidates = canExploreMarkets && tab === "matches";
      const wantsRejected = isAdmin && tab === "passed";
      const wantsCustom = isAdmin && tab === "matches";
      const wantsMarketRoi = (isAdmin && (tab === "matches" || tab === "market-roi")) || (canAccessDailyPicks && tab === "daily-match-picks");
      const backgroundMarketRoi = wantsMarketRoi && tab === "matches";
      if (backgroundMarketRoi) {
        setMarketRoiLoading(!marketRoiResolved.current);
        setMarketRoiError(null);
      }
      const marketRoiPromise = wantsMarketRoi
        ? import("./MarketRoiDaily").then(({ fetchDailyMarketRoi }) => fetchDailyMarketRoi(targetDate)).catch((cause) => {
          const message = cause instanceof Error ? cause.message : "Daily market ROI is unavailable";
          if (request === requestVersion.current) setMarketRoiError(message);
          return null;
        })
        : Promise.resolve(null);
      if (backgroundMarketRoi) {
        void marketRoiPromise.then((rows) => {
          if (request !== requestVersion.current) return;
          setMarketRoi(rows);
          if (rows) setMarketRoiError(null);
        }).finally(() => {
          if (request === requestVersion.current) {
            marketRoiResolved.current = true;
            setMarketRoiLoading(false);
          }
        });
      }
      const [tickets, fixtureRows, allRows, rejectedRows, customRows, marketRoiRows] = await Promise.all([
        wantsTickets ? fetchDailyTickets(targetDate) : Promise.resolve(null),
        wantsFixtures ? fetchMatchFixtures(targetDate) : Promise.resolve(null),
        wantsCandidates ? fetchQualifiedSelections(targetDate) : Promise.resolve(null),
        wantsRejected ? fetchRejectedSelections(targetDate) : Promise.resolve(null),
        wantsCustom ? fetchCustomAccumulators(targetDate) : Promise.resolve(null),
        wantsMarketRoi && !backgroundMarketRoi ? marketRoiPromise : Promise.resolve(null),
      ]);
      if (request !== requestVersion.current) return;
      setError(null);
      if (tickets) setData(tickets);
      if (fixtureRows) setFixtures(fixtureRows);
      if (allRows) {
        setMatches(withRejectionEvidence(allRows.rows, rejectedRows ?? []));
        setMatchesTotal(allRows.total);
      }
      if (rejectedRows) setRejected(rejectedRows);
      if (customRows) setCustom(customRows.map(apiAccumulatorToUi));
      if (wantsMarketRoi && !backgroundMarketRoi) {
        setMarketRoi(marketRoiRows);
        if (marketRoiRows) setMarketRoiError(null);
      }
      setDataCheckedAt(new Date());
    } catch (e) {
      if (request !== requestVersion.current) return;
      setError(
        e instanceof Error ? e.message : "Failed to load research ledger",
      );
    } finally {
      if (request === requestVersion.current) {
        setLoading(false);
        firstLoad.current = false;
      }
    }
  }, [canAccessDailyPicks, canExploreMarkets, initialTab, isAdmin, tab]);

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
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "More candidate selections could not be loaded");
    } finally {
      setLoadingMoreMatches(false);
    }
  };

  useEffect(() => {
    let active = true;
    const refresh = () => { if (active && document.visibilityState === "visible") void load(date); };
    // Always start the initial request. A background tab must still leave its
    // skeleton state; visibility only gates follow-up polling.
    void load(date);
    const timer = window.setInterval(refresh, 300_000);
    const onVisibility = () => { if (document.visibilityState === "visible") refresh(); };
    document.addEventListener("visibilitychange", onVisibility);
    return () => { active = false; requestVersion.current += 1; window.clearInterval(timer); document.removeEventListener("visibilitychange", onVisibility); };
  }, [date, load]);
  const replaceCustom = (row: ApiCustomAccumulator) => {
    const uiRow = apiAccumulatorToUi(row);
    setCustom((current) => [...current.filter((item) => item.id !== uiRow.id), uiRow]);
  };

  const addOrUpdateCustom = async (
    ticket: CustomAccumulator | null,
    name: string,
    legs: SelectionSummary[],
    stake: number | null,
    status: "draft" | "placed",
  ) => {
    const payload = {
      name,
      target_date: date,
      prediction_ids: legs.map((leg) => leg.prediction_id),
      stake,
      status,
    } as const;
    const saved = ticket
      ? await updateCustomAccumulator(ticket.id, payload)
      : await createCustomAccumulator(payload);
    replaceCustom(saved);
    return apiAccumulatorToUi(saved);
  };

  const addToAccumulator = async (row: SelectionSummary) => {
    const blockers = accumulatorBlockers(row);
    if (blockers.length > 0) {
      setSelectionMessage(`Selection not added: ${blockers.map(reasonLabel).join(", ")}`);
      return;
    }
    const current = custom.find(
      (ticket) => ticket.date === date && ticket.status === "draft" && !ticket.automatic,
    );
    let saved: CustomAccumulator;
    if (current) {
      if (current.legs.some((leg) => leg.match_id === row.match_id)) return;
      saved = await addOrUpdateCustom(current, current.name, [...current.legs, row], current.stake, "draft");
    } else {
      saved = await addOrUpdateCustom(null, `${formatDate(date)} accumulator`, [row], null, "draft");
    }
    setSelectionMessage(null);
    onOpenTracker?.(saved.id);
  };

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
  const dailyTabs: [DailyTab, string][] = [
    ...(initialTab === "tickets" ? [["tickets", "Recommendations"] as [DailyTab, string]] : []),
    ...(initialTab === "tickets" && (user?.plan === "pro" || isAdmin) ? [["published-history", "Ticket History"] as [DailyTab, string]] : []),
    ...(initialTab === "tickets" && (user?.plan === "pro" || isAdmin) ? [["personal-journal", "My Journal"] as [DailyTab, string]] : []),
    ...(initialTab === "matches" && !isAdmin ? [["matches", "Match explorer"] as [DailyTab, string]] : []),
    ...(isAdmin && ["matches", "odds-policy", "market-roi", "daily-match-picks", "passed"].includes(initialTab) ? [
      ["matches", "Candidates"],
      ["market-roi", "Market ROI"],
      ["passed", "Passed/Why"],
      ["odds-policy", "Research Policy"],
    ] as [DailyTab, string][] : []),
    ...(canAccessDailyPicks && ["matches", "daily-match-picks"].includes(initialTab)
      ? [["daily-match-picks", "Daily Match Picks"] as [DailyTab, string]]
      : []),
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
  const addableCount = matches.filter((row) => accumulatorBlockers(row).length === 0).length;
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

  // Describe each tier by the rules its generation actually applied.
  const fairPriced = data?.pricing === "market";
  const publicTiers = [
    {
      key: "conservative" as const,
      name: "Conservative",
      desc: fairPriced ? "2–3 legs · 2.00–3.49× · review first" : "Q ≥85 · 3–6 legs · 3–5×",
      color: "var(--conservative)",
    },
    {
      key: "balanced" as const,
      name: "Balanced",
      desc: fairPriced ? "3 legs · 3.50–5.00× · secondary option" : "Q ≥80 · 60% Grade A/A+",
      color: "var(--balanced)",
    },
  ];

  const roiCandidateKeys = new Set((marketRoi?.candidates ?? []).map((row) => `${row.match_id}|${row.market}|${row.selection}`));
  const roiGatedMatches = isAdmin
    ? matches.filter((row) => roiCandidateKeys.has(`${row.match_id}|${row.market}|${row.selection}`))
    : matches;
  const matchGroups = Object.entries(roiGatedMatches.reduce<Record<number, SelectionSummary[]>>((groups, row) => {
    (groups[row.match_id] ??= []).push(row);
    return groups;
  }, {})).map(([id, rows]) => [Number(id), rows] as [number, SelectionSummary[]]);

  return (
    <>
      <div className="meta-bar">
        <div>
          <h1 className="meta-date">
            {initialTab === "tickets" ? "Daily overview" : formatDate(data ? data.target_date : date)}
          </h1>
          {initialTab === "tickets" && <p className="overview-date">
            <span className="event-date">{data ? formatDate(data.target_date) : formatDate(date)}</span>
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
        {isAdmin && initialTab === "tickets" && data && (
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

      {error && (
        <div className="error-bar" role="alert">
          <div>
            <strong>{data && initialTab === "tickets"
              ? "Showing the last loaded recommendations"
              : isAdmin ? "Internal research ledger unavailable" : "Recommendations unavailable"}</strong>
            <span>{data && initialTab === "tickets"
              ? `The latest refresh failed${dataCheckedAt ? `; this view was loaded at ${dataCheckedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : ""}. ${error}`
              : error}</span>
          </div>
          <button onClick={async () => { setRetrying(true); try { await load(date); } finally { setRetrying(false); } }} disabled={retrying}>
            {retrying ? "Retrying…" : data && initialTab === "tickets" ? "Refresh now" : "Try again"}
          </button>
        </div>
      )}

      {loading ? (
        <TicketGridSkeleton />
      ) : (
        <>
          {dailyTabs.length > 1 && <nav className="daily-tabs" aria-label="Daily ticket workspace">
            {dailyTabs.map(([key, label]) => (
              <button
                key={key}
                className={tab === key ? "active" : ""}
                onClick={() => { setTab(key); onTabChange?.(key); }}
              >
                {label}
              </button>
            ))}
          </nav>}
          {tab === "matches" && selectionMessage && (
            <p className="pipeline-banner-message tickets-operation-message negative" role="status">
              {selectionMessage}
            </p>
          )}
          {tab === "matches" && canExploreMarkets && <div className="view-intro"><div><span className="eyebrow">Research candidates</span><h2 className="section-title">Qualified match markets</h2></div><p>These candidate signals are for inspection. A match appearing here does not mean it was selected for a published ticket.</p></div>}
          {isAdmin && tab === "matches" && marketRoi && (
            <div className="market-roi-match-gate" role="status">
              <b>Daily market report screen</b>
              <span>
                This admin list intersects the daily ROI market set with the paged Q-score candidate feed (Q ≥ 75). It loads 100 candidates at a time; the ROI report may include lower-Q selections that are not in this candidate list.
              </span>
            </div>
          )}
          {isAdmin && tab === "matches" && marketRoiError && (
            <div className="market-roi-match-error" role="alert">
              Daily ROI gate unavailable ({marketRoiError}); no market-qualified matches are shown until it refreshes.
            </div>
          )}
          {tab === "matches" && isAdmin && marketRoiLoading && <div className="route-loading" role="status" aria-live="polite">Loading the daily market screen before showing admin candidates…</div>}
          {tab === "matches" && canExploreMarkets && !marketRoiLoading && !marketRoiError && <Suspense fallback={<div className="route-loading">Loading candidates…</div>}><AllMatches rows={matchGroups} totalSelections={matchesTotal} loadedSelections={matches.length} loadingMore={loadingMoreMatches} onLoadMore={loadMoreMatches} onSelect={openSelection} onAdd={addToAccumulator} allowAdd={isAdmin} /></Suspense>}
          {tab === "matches" && !canExploreMarkets && <Suspense fallback={<div className="route-loading">Loading fixtures…</div>}><FixtureExplorer fixtures={fixtures} /></Suspense>}
          {isAdmin && tab === "odds-policy" && (
            <Suspense fallback={<div className="route-loading">Loading policy review…</div>}><ParameterSweepPicks
              date={date}
              onSelect={openSelection}
              onAdd={addToAccumulator}
            /></Suspense>
          )}
          {isAdmin && tab === "market-roi" && <Suspense fallback={<div className="route-loading">Loading market report…</div>}><MarketRoiDaily data={marketRoi} error={marketRoiError} /></Suspense>}
          {canAccessDailyPicks && tab === "daily-match-picks" && <Suspense fallback={<div className="route-loading">Loading match report…</div>}><DailyMatchPicks data={marketRoi} error={marketRoiError} /></Suspense>}
          {isAdmin && tab === "passed" && (
            <PassedMatches rows={rejected} onSelect={openSelection} />
          )}
          {tab === "published-history" && (user?.plan === "pro" || isAdmin) && <Suspense fallback={<div className="route-loading">Loading published history…</div>}><PublishedHistory /></Suspense>}
          {tab === "personal-journal" && (user?.plan === "pro" || isAdmin) && <Suspense fallback={<div className="route-loading">Loading your journal…</div>}><PersonalJournal personalOnly /></Suspense>}
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
                    <span className={addableCount === 0 ? "blocked" : ""}><b>{addableCount}</b><small>conservative draft legs</small></span>
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
                  <p>Personal drafts cannot accept stale, invalid, or already-started selections.</p>
                </section>
              )}
              {isAdmin && (data?.superseded_versions?.length ?? 0) > 0 && (
                <div className="ticket-version-notice">
                  <strong>Latest versions shown.</strong> Earlier published tickets remain immutable in history; regenerated tickets may have different legs.
                </div>
              )}

              {publicPublishedTickets.length > 0 && (
                <Suspense fallback={<div className="route-loading">Loading published selections…</div>}><PublishedSelections tickets={publicTiers.flatMap((tier) => {
                  const ticket = data?.[tier.key] ?? null;
                  return ticket ? [{ tierKey: tier.key, tierName: tier.name, ticket }] : [];
                })} onSelect={openTicketLeg} canViewSelections={user?.plan === "pro" || isAdmin} /></Suspense>
              )}
              {publicPublishedTickets.length > 0 && <section className="published-ticket-tiers">
                <header className="published-ticket-tiers-heading"><span><strong>Ticket tiers and full legs</strong><small>Combined odds, estimated chance, and immutable legs for {publicPublishedTickets.length} published tier{publicPublishedTickets.length === 1 ? "" : "s"}.</small></span></header>
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
                  onSelectLeg={canExploreMarkets ? openTicketLeg : undefined}
                  flatStake={flatStakeForTicket(data?.[tier.key] ?? null)}
                  showMarketSelections={user?.plan === "pro" || isAdmin}
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
          onClose={() => setDetail(null)}
          onOpenMatch={isAdmin ? onOpenMatch : undefined}
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

  return <section className="passed-matches-panel" aria-labelledby="passed-matches-title">
    <div className="section-heading">
      <div><span className="eyebrow">Transparent rejection ledger</span><h2 id="passed-matches-title">Rejected opportunities and why</h2><span className="section-note">A passed rejection avoided a losing selection; a failed rejection excluded a winning selection.</span></div>
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
        <small>{filteredRows.length} shown · {settledRows.length} settled · {roiRows.length} priced</small>
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
