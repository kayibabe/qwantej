import type { Leg, Ticket } from "../../lib/api";
import { formatDate, formatKickoff, formatMarket, formatSelection, selectionRepeatsMarket, selectionTone } from "../../lib/api";

interface PublishedTicket {
  tierName: string;
  ticket: Ticket;
}

interface PublishedSelection {
  leg: Leg;
  ticket: Ticket;
  tiers: Set<string>;
}

interface Props {
  tickets: PublishedTicket[];
  onSelect: (leg: Leg, ticket: Ticket) => void;
  canViewSelections: boolean;
}

function resultLabel(leg: Leg): string {
  if (leg.result === "won") return "Pick won";
  if (leg.result === "lost") return "Pick lost";
  if (leg.result === "void") return "Pick void";
  return leg.home_goals != null && leg.away_goals != null ? "Settlement pending" : "Pending";
}

export default function PublishedSelections({ tickets, onSelect, canViewSelections }: Props) {
  const selections = new Map<string, PublishedSelection>();

  for (const { tierName, ticket } of tickets) {
    for (const leg of ticket.legs) {
      const key = leg.prediction_id != null
        ? `prediction:${leg.prediction_id}`
        : `${leg.match_id}|${leg.market}|${leg.selection}`;
      const existing = selections.get(key);
      if (existing) {
        existing.tiers.add(tierName);
      } else {
        selections.set(key, { leg, ticket, tiers: new Set([tierName]) });
      }
    }
  }

  const rows = [...selections.values()].sort((a, b) => Date.parse(a.leg.kickoff_at) - Date.parse(b.leg.kickoff_at));

  return (
    <section className="published-selections" aria-labelledby="published-selections-title">
      <div className="published-selections-heading">
        <div>
          <span className="eyebrow">Today’s published picks</span>
          <h2 id="published-selections-title">Published selections</h2>
        </div>
        <span className="published-selection-count">{rows.length} unique {rows.length === 1 ? "selection" : "selections"}</span>
      </div>
      <p className="published-selections-note">Each match pick appears once. Ticket tiers that include it are shown on the pick; each tier’s full published record is below.</p>
      {!canViewSelections ? (
        <p className="published-selections-empty">Selection details are available on Pro. Published ticket summaries remain below.</p>
      ) : rows.length === 0 ? (
        <p className="published-selections-empty">No match selections are available in the published tickets for this date.</p>
      ) : (
        <ul className="published-selection-list">
          {rows.map(({ leg, ticket, tiers }) => {
            const selection = selectionRepeatsMarket(leg.market, leg.selection)
              ? formatSelection(leg.selection)
              : `${formatMarket(leg.market)} · ${formatSelection(leg.selection)}`;
            const score = leg.home_goals != null && leg.away_goals != null ? `${leg.home_goals}–${leg.away_goals}` : null;
            return (
              <li className="published-selection-item" key={leg.prediction_id ?? `${leg.match_id}|${leg.market}|${leg.selection}`}>
                <button className="published-selection-button" type="button" onClick={() => onSelect(leg, ticket)}>
                  <span className="published-selection-main">
                    <span className="published-selection-match">{leg.home_team} <span>vs</span> {leg.away_team}</span>
                    <span className="published-selection-meta">{leg.competition} · {formatDate(leg.kickoff_at)} · {formatKickoff(leg.kickoff_at)}</span>
                  </span>
                  <span className="published-selection-pick">
                    <span className={`leg-market market-pick ${selectionTone(leg.selection)}`}>{selection}</span>
                    <span className={`published-selection-result ${leg.result ?? "pending"}`}>{score && <b>{score}</b>}{resultLabel(leg)}</span>
                  </span>
                  <span className="published-selection-details">
                    <span className="published-selection-tiers">In {Array.from(tiers).join(" · ")}</span>
                    <span className="published-selection-odds">{leg.best_odds == null ? "Odds unavailable" : `${leg.best_odds.toFixed(2)} odds`}</span>
                  </span>
                  <span className="published-selection-open" aria-hidden="true">›</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
