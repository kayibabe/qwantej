import { useState } from "react";
import type { BlockPerformance, BlockPerformanceCell } from "../../lib/api";
import { formatMarket } from "../../lib/api";

const BLOCKS = [20, 30, 40, 50, 60, 70, 80, 90];
const DAYS_OPTIONS = [30, 60, 90];
const LOW_SAMPLE_PRICED = 5;

type Kind = "chance" | "implied";

function roiToneClass(roi: number | null): string {
  if (roi == null || roi === 0) return "bg-white text-slate-700 border-slate-200";
  const magnitude = Math.abs(roi);
  if (roi > 0) {
    if (magnitude >= 0.2) return "bg-emerald-200 text-emerald-900 border-emerald-300";
    if (magnitude >= 0.1) return "bg-emerald-100 text-emerald-900 border-emerald-200";
    return "bg-emerald-50 text-emerald-800 border-emerald-200";
  }
  if (magnitude >= 0.2) return "bg-red-200 text-red-900 border-red-300";
  if (magnitude >= 0.1) return "bg-red-100 text-red-900 border-red-200";
  return "bg-red-50 text-red-800 border-red-200";
}

function hitRateLabel(cell: BlockPerformanceCell) {
  return cell.hit_rate != null ? `${Math.round(cell.hit_rate * 100)}%` : "—";
}

function cellTooltip(cell: BlockPerformanceCell) {
  const parts = [
    `${formatMarket(cell.market)} · ${cell.kind === "chance" ? "model chance" : "bookmaker implied"} ≥ ${cell.block}%`,
    `Won ${cell.won} · Lost ${cell.lost}` + (cell.void ? ` · Void ${cell.void}` : ""),
    `Hit rate ${hitRateLabel(cell)}`,
    cell.roi != null ? `ROI ${(cell.roi * 100).toFixed(1)}% over ${cell.priced} priced picks` : "No priced picks",
    `${cell.picks} system picks in window`,
  ];
  return parts.filter(Boolean).join("\n");
}

export function BlockHeatmap({
  performance,
  loading,
  error,
  days,
  onDaysChange,
  onCell,
}: {
  performance: BlockPerformance | null;
  loading: boolean;
  error?: string | null;
  days: number;
  onDaysChange: (days: number) => void;
  /** Applies this historical market + winning block to today's search. */
  onCell: (market: string, kind: Kind, block: number) => void;
}) {
  const [kind, setKind] = useState<Kind>("chance");
  const cells = (performance?.cells ?? []).filter((cell) => cell.kind === kind);
  const marketOfCell = new Map<string, Map<number, BlockPerformanceCell>>();
  for (const cell of cells) {
    let row = marketOfCell.get(cell.market);
    if (!row) { row = new Map(); marketOfCell.set(cell.market, row); }
    row.set(cell.block, cell);
  }
  const markets = [...marketOfCell.keys()].sort();
  const totals = BLOCKS.map((block) => {
    const blockCells = cells.filter((cell) => cell.block === block);
    const won = blockCells.reduce((sum, cell) => sum + cell.won, 0);
    const lost = blockCells.reduce((sum, cell) => sum + cell.lost, 0);
    const priced = blockCells.reduce((sum, cell) => sum + cell.priced, 0);
    const net = blockCells.reduce((sum, cell) => sum + cell.net_units, 0);
    const decided = won + lost;
    return {
      block,
      hitRate: decided > 0 ? won / decided : null,
      roi: priced > 0 ? net / priced : null,
      picks: blockCells.reduce((sum, cell) => sum + cell.picks, 0),
    };
  });
  // A failed or slower refresh must not silently present the previous window
  // as if it were the selected one.
  const showingPrevious = Boolean(performance && (error || (loading && performance.window_days !== days)));
  const filterButtonClass = (active: boolean) =>
    `inline-flex min-h-11 items-center justify-center rounded-md border px-4 py-2.5 text-sm font-semibold transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 ${
      active
        ? "bg-emerald-700 border-emerald-700 text-white"
        : "bg-white border-slate-200 text-slate-700 hover:text-slate-900 hover:border-slate-300 hover:bg-slate-50"
    }`;

  return (
    <div className="space-y-4" aria-busy={loading}>
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap items-center gap-1.5" aria-label="Heat map dimension">
          <button type="button" className={filterButtonClass(kind === "chance")} aria-pressed={kind === "chance"} onClick={() => setKind("chance")}>Model chance blocks</button>
          <button type="button" className={filterButtonClass(kind === "implied")} aria-pressed={kind === "implied"} onClick={() => setKind("implied")}>Bookmaker implied blocks</button>
        </div>
        <div className="flex flex-wrap items-center gap-1.5" aria-label="History window">
          {DAYS_OPTIONS.map((option) => (
            <button type="button" key={option} className={filterButtonClass(days === option)} aria-pressed={days === option} onClick={() => onDaysChange(option)}>{option} days</button>
          ))}
        </div>
      </div>

      {performance && (
        <p className="text-sm leading-relaxed text-slate-600">
          Settled window {performance.start_date} to {performance.end_date} ({performance.window_days} days). Blocks are cumulative “≥” thresholds, so the same pick can appear in several block cells.
        </p>
      )}
      {showingPrevious && performance && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm leading-relaxed text-amber-900" role="status">
          <strong className="block text-amber-950">Showing the previously loaded {performance.window_days}-day window.</strong>
          <span>{error ? `Refresh failed: ${error}` : `Refreshing the ${days}-day window…`}</span>
        </div>
      )}
      {!showingPrevious && error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm leading-relaxed text-red-800" role="alert">
          Heat map unavailable: {error}
        </div>
      )}
      {loading && !performance && <HeatmapSkeleton />}
      {!loading && !error && !performance && (
        <p className="text-base text-slate-600" role="status">Settled pick history has not loaded yet.</p>
      )}
      {!loading && !error && performance && cells.length === 0 && (
        <p className="text-base text-slate-600">No settled system picks in the last {days} days for this dimension.</p>
      )}
      {markets.length > 0 && (
        <div
          className="relative overflow-x-auto rounded-xl border border-slate-200 bg-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
          role="region"
          aria-label="Block performance cells"
          tabIndex={0}
        >
          <table className="w-full min-w-[900px] border-collapse text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-sm font-semibold text-slate-700">
              <tr>
                <th scope="col" className="px-3 py-3 font-semibold">{kind === "chance" ? "Model chance" : "Bookmaker implied"} →</th>
                {BLOCKS.map((block) => <th scope="col" key={block} className="px-3 py-3 font-semibold text-center">≥{block}%</th>)}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {markets.map((market) => {
                const row = marketOfCell.get(market)!;
                return (
                  <tr key={market} className="hover:bg-slate-50/70">
                    <th scope="row" className="px-3 py-2 text-left font-semibold text-slate-700 whitespace-nowrap">{formatMarket(market)}</th>
                    {BLOCKS.map((block) => {
                      const cell = row.get(block);
                      if (!cell) {
                        return (
                          <td key={block} className="px-2 py-2">
                            <span className="flex min-h-12 min-w-[88px] items-center justify-center rounded-md border border-dashed border-slate-200 bg-slate-50/50 text-sm text-slate-600">—<span className="sr-only">No settled picks for this block</span></span>
                          </td>
                        );
                      }
                      const lowSample = cell.priced < LOW_SAMPLE_PRICED;
                      return (
                        <td key={block} className="px-2 py-2">
                          <button
                            type="button"
                            className={`flex min-h-12 min-w-[88px] flex-col items-center justify-center gap-0.5 rounded-md border px-2 py-2 transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 hover:brightness-[0.98] ${roiToneClass(cell.roi)} ${lowSample ? "opacity-75" : ""}`}
                            aria-label={`${cellTooltip(cell).replace(/\n/g, ". ")}${lowSample ? ". Fewer than five priced picks" : ""}. Apply to today's search`}
                            title={cellTooltip(cell)}
                            onClick={() => onCell(market, kind, block)}
                          >
                            <b className="font-mono text-sm font-bold tabular-nums">{hitRateLabel(cell)}</b>
                            <small className="text-sm leading-snug">{cell.picks} picks{lowSample ? " · low N" : ""}</small>
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
              <tr className="bg-slate-50/50">
                <th scope="row" className="px-3 py-2 text-left font-bold text-slate-800">All markets</th>
                {totals.map((total) => (
                  <td key={total.block} className="px-2 py-2">
                    {total.picks === 0 ? (
                      <span className="flex min-h-12 min-w-[88px] items-center justify-center rounded-md border border-dashed border-slate-200 bg-slate-50/50 text-sm text-slate-600">—<span className="sr-only">No settled picks for this block</span></span>
                    ) : (
                      <span
                        className={`flex min-h-12 min-w-[88px] flex-col items-center justify-center gap-0.5 rounded-md border px-2 py-2 ${roiToneClass(total.roi)}`}
                        title={total.roi != null ? `ROI ${(total.roi * 100).toFixed(1)}%` : undefined}
                      >
                        <b className="font-mono text-sm font-bold tabular-nums">{total.hitRate != null ? `${Math.round(total.hitRate * 100)}%` : "—"}</b>
                        <small className="text-sm leading-snug">{total.picks} picks</small>
                      </span>
                    )}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}
      <div className="space-y-2 text-sm leading-relaxed text-slate-600">
        <p>Each cell shows the settled hit rate and the number of system picks; its colour shows one-unit ROI direction. Select a cell to apply that market and block to today&apos;s search.</p>
        <div className="flex flex-wrap gap-x-5 gap-y-2">
          <LegendSwatch tone="border-emerald-300 bg-emerald-200" label="Positive ROI" />
          <LegendSwatch tone="border-red-300 bg-red-200" label="Negative ROI" />
          <LegendSwatch tone="border-slate-200 bg-white" label="No priced picks or break-even" />
          <span>Faded cell: fewer than {LOW_SAMPLE_PRICED} priced picks.</span>
        </div>
      </div>
    </div>
  );
}

function LegendSwatch({ tone, label }: { tone: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span aria-hidden="true" className={`inline-block h-4 w-4 rounded border ${tone}`} />
      {label}
    </span>
  );
}

function HeatmapSkeleton() {
  return (
    <div className="relative overflow-x-auto rounded-xl border border-slate-200 bg-white" aria-busy="true" role="status">
      <table className="w-full min-w-[900px] border-collapse text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50">
          <tr>
            <th scope="col" className="px-3 py-3"><span className="block h-4 w-28 rounded bg-slate-200" /></th>
            {BLOCKS.map((block) => (
              <th scope="col" key={block} className="px-3 py-3"><span className="mx-auto block h-4 w-10 rounded bg-slate-200" /></th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {[0, 1, 2, 3].map((row) => (
            <tr key={row}>
              <th scope="row" className="px-3 py-2"><span className="block h-4 w-24 rounded bg-slate-100" /></th>
              {BLOCKS.map((block) => (
                <td key={block} className="px-2 py-2"><span className="block min-h-12 min-w-[88px] rounded-md bg-slate-100" /></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <span className="sr-only">Loading settled pick history…</span>
    </div>
  );
}
