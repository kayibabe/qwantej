import { useState } from "react";
import type { CSSProperties } from "react";
import type { BlockPerformance, BlockPerformanceCell } from "../../lib/api";
import { formatMarket } from "../../lib/api";

const BLOCKS = [20, 30, 40, 50, 60, 70, 80, 90];
const DAYS_OPTIONS = [30, 60, 90];

type Kind = "chance" | "implied";

function cellStyle(roi: number | null): CSSProperties | undefined {
  if (roi == null || roi === 0) return undefined;
  const amount = Math.min(75, Math.max(10, Math.round(Math.abs(roi) * 260)));
  return {
    background: `color-mix(in srgb, ${roi > 0 ? "var(--positive)" : "var(--negative)"} ${amount}%, var(--surface))`,
  };
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
  return (
    <div className="block-heatmap">
      <div className="block-heatmap-controls">
        <div className="match-status-filters" aria-label="Heat map dimension">
          <button className={kind === "chance" ? "active" : ""} onClick={() => setKind("chance")}>Model chance blocks</button>
          <button className={kind === "implied" ? "active" : ""} onClick={() => setKind("implied")}>Bookmaker implied blocks</button>
        </div>
        <div className="match-status-filters" aria-label="History window">
          {DAYS_OPTIONS.map((option) => (
            <button key={option} className={days === option ? "active" : ""} onClick={() => onDaysChange(option)}>{option}&nbsp;days</button>
          ))}
        </div>
      </div>
      {loading && !performance && <p className="block-heatmap-status">Loading settled pick history…</p>}
      {error && <p className="block-heatmap-status">Heat map unavailable: {error}</p>}
      {!loading && !error && performance && cells.length === 0 && <p className="block-heatmap-status">No settled system picks in the last {days} days yet.</p>}
      {markets.length > 0 && (
        <div className="block-heatmap-table-wrap">
          <table className="block-heatmap-table">
            <thead>
              <tr>
                <th scope="col">{kind === "chance" ? "Model chance" : "Bookmaker implied"} →</th>
                {BLOCKS.map((block) => <th scope="col" key={block}>≥{block}%</th>)}
              </tr>
            </thead>
            <tbody>
              {markets.map((market) => {
                const row = marketOfCell.get(market)!;
                return (
                  <tr key={market}>
                    <th scope="row">{formatMarket(market)}</th>
                    {BLOCKS.map((block) => {
                      const cell = row.get(block);
                      if (!cell) return <td key={block} className="block-cell empty" />;
                      const lowSample = cell.priced < 5;
                      return (
                        <td key={block}>
                          <button
                            type="button"
                            className={`block-cell ${lowSample ? "low-sample" : ""}`}
                            style={cellStyle(cell.roi)}
                            title={cellTooltip(cell)}
                            onClick={() => onCell(market, kind, block)}
                          >
                            <b>{hitRateLabel(cell)}</b>
                            <small>{cell.picks} picks</small>
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
              <tr className="block-heatmap-totals">
                <th scope="row">All markets</th>
                {totals.map((total) => (
                  <td key={total.block}>
                    {total.picks === 0 ? (
                      <span className="block-cell empty" />
                    ) : (
                      <span className="block-cell static" style={cellStyle(total.roi)} title={total.roi != null ? `ROI ${(total.roi * 100).toFixed(1)}%` : undefined}>
                        <b>{total.hitRate != null ? `${Math.round(total.hitRate * 100)}%` : "—"}</b>
                        <small>{total.picks} picks</small>
                      </span>
                    )}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}
      <p className="block-heatmap-note">
        Aggregate hit rate and one-unit ROI over the settled window, grouped into cumulative “≥ block%” rows.
        Click a block to run today's search with that market and block.
      </p>
    </div>
  );
}
