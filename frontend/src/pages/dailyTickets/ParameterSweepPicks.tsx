import { useEffect, useState } from "react";
import type { ParameterSweepPick, ParameterSweepSelections, SelectionSummary } from "../../lib/api";
import { fetchParameterSweepSelections, formatKickoff, formatMarket, formatSelection, selectionRepeatsMarket } from "../../lib/api";
import { useSortableRows } from "../../components/SortableTable";
import { gradeTone } from "./helpers";

const pct = (value: number | null | undefined) => value == null ? "—" : `${(value * 100).toFixed(1)}%`;

function toSelection(row: ParameterSweepPick): SelectionSummary {
  return {
    prediction_id: row.prediction_id,
    match_id: row.match_id,
    home_team: row.home_team,
    away_team: row.away_team,
    competition: row.competition,
    kickoff_at: row.kickoff_at,
    market: row.market,
    selection: row.selection,
    model_probability: row.model_probability,
    q_score: row.q_score,
    q_grade: row.q_grade,
    edge: row.edge,
    best_odds: row.odds,
    match_status: "scheduled",
    result: row.result === "win" ? "won" : row.result === "loss" ? "lost" : row.result,
  };
}

function gradeBadgeClass(grade: string | undefined) {
  const tone = gradeTone(grade);
  if (tone.startsWith("a")) return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (tone.startsWith("b")) return "bg-amber-50 text-amber-700 border-amber-200";
  if (tone.startsWith("c")) return "bg-sky-50 text-sky-700 border-sky-200";
  return "bg-slate-100 text-slate-600 border-slate-200";
}

function asOfLabel(value: string | null | undefined) {
  if (!value) return "capture time unavailable";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "capture time unavailable"
    : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(parsed);
}

export function ParameterSweepPicks({
  date,
  onSelect,
}: {
  date: string;
  onSelect: (row: SelectionSummary) => void;
}) {
  const [data, setData] = useState<ParameterSweepSelections | null>(null);
  const [lastGood, setLastGood] = useState<ParameterSweepSelections | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    let controller: AbortController | undefined;
    setData(null);
    setError(null);
    // A result for a different date must never be presented as today's scan.
    setLastGood((current) => current?.scan?.target_date === date ? current : null);
    const load = async () => {
      const requestController = new AbortController();
      controller = requestController;
      const timeout = window.setTimeout(() => requestController.abort(), 20_000);
      let delay = 15_000;
      try {
        const value = await fetchParameterSweepSelections(date, requestController.signal);
        if (!active) return;
        setData(value);
        setError(null);
        if (value.scan) {
          setLastGood(value);
          delay = 300_000;
        }
      } catch (cause) {
        if (active) setError(controller?.signal.aborted ? "The request timed out. Retrying shortly." : cause instanceof Error ? cause.message : "Unable to load dynamic policy");
      } finally {
        window.clearTimeout(timeout);
        if (active) timer = window.setTimeout(load, delay);
      }
    };
    void load();
    return () => { active = false; controller?.abort(); if (timer !== undefined) window.clearTimeout(timer); };
  }, [date]);

  const currentScan = data?.scan ?? null;
  const scan = currentScan ?? lastGood?.scan ?? null;
  const source = currentScan ? data : lastGood;
  const rows = source?.rows ?? [];
  const stale = Boolean(lastGood?.scan && (error || (!currentScan && data?.status === "processing")));
  const policy = scan?.chosen_policy;

  return (
    <section className="rounded-xl border border-slate-200 bg-white overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 px-4 py-4">
        <div className="min-w-0 space-y-1">
          <h2 className="text-lg font-bold text-slate-900">Dynamic odds policy · research only</h2>
          <p className="text-base leading-relaxed text-slate-600">A daily parameter sweep of historical windows. All figures here are paper research.</p>
        </div>
        {scan && (
          <div className="space-y-1 text-sm text-slate-600 sm:text-right">
            <span className="block"><b className="font-mono tabular-nums text-slate-900">{rows.length}</b> qualifying matches</span>
            <span className="block">Target {scan.target_date} · evidence through {scan.evidence_through}</span>
          </div>
        )}
      </div>

      <div className="px-4 py-4 space-y-4">
        {(error || stale) && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm leading-relaxed text-red-800" role={error ? "alert" : "status"}>
            <strong className="block text-red-900">{error ? "Dynamic policy refresh unavailable" : "Refresh in progress"}</strong>
            <span>{error ?? data?.message}</span>
            {stale && lastGood?.scan && (
              <span className="block mt-1 text-red-900">
                Showing the last successful scan for {lastGood.scan.target_date}, captured {asOfLabel(lastGood.scan.captured_at)}.
              </span>
            )}
          </div>
        )}
        {!scan && !error && data?.status === "processing" && (
          <p className="text-base leading-relaxed text-slate-600" role="status">{data.message ?? "Processing the saved policy scan…"}</p>
        )}
        {!scan && !error && data?.status !== "processing" && (
          <p className="text-base leading-relaxed text-slate-600" role="status">Loading the saved policy scan…</p>
        )}
        {scan && (
          <>
            <div className={`rounded-lg border px-3 py-3 text-base leading-relaxed ${scan.provisional ? "border-amber-200 bg-amber-50 text-amber-900" : "border-slate-200 bg-slate-50 text-slate-700"}`} role="status">
              <strong className="block text-slate-900">{scan.reconstructed ? "Historical reconstruction" : scan.provisional ? "Provisional scan" : "Daily policy frozen"}</strong>
              <span>
                {scan.status === "qualified"
                  ? <>Odds ≥ <b className="font-mono tabular-nums">{policy?.min_odds.toFixed(2)}</b>, probability ≥ <b className="font-mono tabular-nums">{pct(policy?.min_probability)}</b>, validation ROI <b className="font-mono tabular-nums">{pct(scan.chosen_validation?.roi)}</b>.</>
                  : <>No policy currently clears the minimum 20% validation ROI and evidence gates, so no matches are listed.</>}
                {" "}Grid: {scan.rules.grid_size.toLocaleString()} combinations; evidence through {scan.evidence_through}.
              </span>
              {scan.captured_at && <span className="block mt-1">Captured {asOfLabel(scan.captured_at)}{scan.capture_source ? ` · ${scan.capture_source}` : ""}</span>}
            </div>

            {policy && scan.chosen_train && scan.chosen_validation && (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6" aria-label="Dynamic policy evidence">
                <Kpi label="Minimum odds" value={policy.min_odds.toFixed(2)} />
                <Kpi label="Probability floor" value={pct(policy.min_probability)} />
                <Kpi label="Train ROI / N" value={`${pct(scan.chosen_train.roi)} / ${scan.chosen_train.resolved}`} />
                <Kpi label="Validation ROI / N" value={`${pct(scan.chosen_validation.roi)} / ${scan.chosen_validation.resolved}`} tone="text-emerald-700" />
                <Kpi label="Quote age" value={`${policy.max_quote_age_hours}h`} />
                <Kpi label="Policy count" value={String(scan.qualifying_policy_count)} />
              </div>
            )}

            {rows.length > 0 && <SweepTable rows={rows} onSelect={onSelect} />}
            {scan.status === "qualified" && rows.length === 0 && <p className="text-base text-slate-600">The policy cleared historical gates, but no today selections passed its pre-kickoff filters.</p>}
          </>
        )}

        <details className="rounded-lg border border-slate-200 bg-white overflow-hidden">
          <summary className="cursor-pointer px-4 py-3 text-base font-semibold text-slate-800 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Method and limitations of this policy</summary>
          <div className="space-y-2 border-t border-slate-200 px-4 py-4 text-base leading-relaxed text-slate-700">
            <p>Matches appear only when a frozen pre-day validation window clears the 20% ROI research gate. A policy is not exposed when its evidence gate fails.</p>
            <p>Historical ROI is reconstructed paper performance, not recorded bookmaker bets or a promise of profit.</p>
            {scan && (
              <p>
                Grid: {scan.rules.grid_size.toLocaleString()} combinations; minimum validation ROI {pct(scan.rules.minimum_validation_roi)}; minimum train sample {scan.rules.minimum_train_sample}; minimum validation sample {scan.rules.minimum_validation_sample}; one selection per match: {scan.rules.one_selection_per_match ? "yes" : "no"}. Selection rule: {scan.rules.selection_rule}.
              </p>
            )}
            {scan && scan.limitations.length > 0 && (
              <ul className="list-disc space-y-1 pl-5">
                {scan.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
              </ul>
            )}
          </div>
        </details>
      </div>
    </section>
  );
}

function Kpi({ label, value, tone = "text-slate-900" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <span className="block text-sm font-medium text-slate-600">{label}</span>
      <b className={`mt-0.5 block font-mono text-base font-bold tabular-nums ${tone}`}>{value}</b>
    </div>
  );
}

function SweepTable({ rows, onSelect }: { rows: ParameterSweepPick[]; onSelect: (row: SelectionSummary) => void }) {
  const { sorted, header } = useSortableRows(rows, {
    kickoff: row => new Date(row.kickoff_at).getTime(),
    match: row => `${row.home_team} ${row.away_team} ${row.competition}`,
    market: row => `${formatMarket(row.market)} ${formatSelection(row.selection)}`,
    probability: row => row.model_probability,
    odds: row => row.odds,
    qScore: row => row.q_score,
  });
  const thClass = "px-3 py-3";

  return (
    <div
      className="relative overflow-x-auto rounded-xl border border-slate-200 bg-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
      role="region"
      aria-label="Dynamic policy selections"
      tabIndex={0}
    >
      <table className="w-full min-w-[820px] border-collapse text-left text-sm">
        <caption className="sr-only">Matches selected by the dynamic odds policy</caption>
        <thead className="border-b border-slate-200 bg-slate-50 text-sm font-semibold text-slate-700">
          <tr>
            {header('kickoff', 'Kickoff', thClass)}
            {header('match', 'Match / league', thClass)}
            {header('market', 'Market', thClass)}
            {header('probability', 'Probability', thClass)}
            {header('odds', 'Odds', thClass)}
            {header('qScore', 'Q-score', thClass)}
            <th scope="col" className="px-3 py-3"><span className="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {sorted.map(row => {
            const selection = toSelection(row);
            return (
              <tr key={row.prediction_id} className="hover:bg-slate-50/70">
                <td className="px-3 py-2 align-top"><strong className="font-mono text-sm font-semibold text-slate-700 tabular-nums whitespace-nowrap">{formatKickoff(row.kickoff_at)}</strong></td>
                <td className="px-3 py-2 align-top">
                  <strong className="block text-slate-900">{row.home_team} <span className="text-slate-600 font-normal">vs</span> {row.away_team}</strong>
                  <small className="block text-sm text-slate-600">{row.competition}</small>
                </td>
                <td className="px-3 py-2 align-top">
                  {!selectionRepeatsMarket(row.market, row.selection) && <span className="block text-sm text-slate-600">{formatMarket(row.market)}</span>}
                  <strong className="text-slate-900">{formatSelection(row.selection)}</strong>
                </td>
                <td className="px-3 py-2 align-top font-mono tabular-nums text-slate-700">{pct(row.model_probability)}</td>
                <td className="px-3 py-2 align-top"><b className="font-mono font-bold tabular-nums text-slate-900">{row.odds.toFixed(2)}</b></td>
                <td className="px-3 py-2 align-top">
                  <div className="flex flex-wrap items-center gap-2">
                    <b className={`inline-flex items-center rounded-full border px-2 py-0.5 text-sm font-semibold ${gradeBadgeClass(row.q_grade)}`}>{row.q_grade}</b>
                    <span className="font-mono tabular-nums text-slate-700">{row.q_score.toFixed(1)}</span>
                  </div>
                </td>
                <td className="px-3 py-2 align-top">
                  <div className="flex justify-end">
                    <button
                      type="button"
                      className="inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
                      onClick={() => onSelect(selection)}
                      aria-label={`Details for ${row.home_team} versus ${row.away_team}, ${formatSelection(row.selection)}`}
                    >
                      Details
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
