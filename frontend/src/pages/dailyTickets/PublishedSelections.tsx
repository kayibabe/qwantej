import { useSortableRows } from "../../components/SortableTable";
import type { Leg, Ticket } from "../../lib/api";
import { formatDate, formatKickoff, formatMarket, formatSelection, selectionRepeatsMarket, selectionTone, ticketTierBadgeClass } from "../../lib/api";

interface PublishedTicket {
  tierKey: string;
  tierName: string;
  ticket: Ticket;
}

interface PublishedSelection {
  leg: Leg;
  ticket: Ticket;
  tiers: Map<string, string>;
}

interface Props {
  tickets: PublishedTicket[];
  onSelect: (leg: Leg, ticket: Ticket) => void;
  canViewSelections: boolean;
}

function matchStatus(leg: Leg): string {
  const score = leg.home_goals != null && leg.away_goals != null ? ` (${leg.home_goals}-${leg.away_goals})` : "";
  if (leg.result === "won") return `Won${score}`;
  if (leg.result === "lost") return `Lost${score}`;
  if (leg.result === "void") return "Void";
  return "Pending";
}

export default function PublishedSelections({ tickets, onSelect, canViewSelections }: Props) {
  const selections = new Map<string, PublishedSelection>();

  for (const { tierKey, tierName, ticket } of tickets) {
    for (const leg of ticket.legs) {
      const key = leg.prediction_id != null
        ? `prediction:${leg.prediction_id}`
        : `${leg.match_id}|${leg.market}|${leg.selection}`;
      const existing = selections.get(key);
      if (existing) {
        existing.tiers.set(tierKey, tierName);
      } else {
        selections.set(key, { leg, ticket, tiers: new Map([[tierKey, tierName]]) });
      }
    }
  }

  const rows = [...selections.values()].sort((a, b) => Date.parse(a.leg.kickoff_at) - Date.parse(b.leg.kickoff_at));
  const { sorted: sortedRows, sort, toggle } = useSortableRows(rows, {
    fixture: ({ leg }) => `${leg.home_team} vs ${leg.away_team} ${leg.competition}`,
    marketPick: ({ leg }) => selectionRepeatsMarket(leg.market, leg.selection)
      ? formatSelection(leg.selection)
      : `${formatMarket(leg.market)} ${formatSelection(leg.selection)}`,
    matchStatus: ({ leg }) => matchStatus(leg),
    ticketOdds: ({ leg }) => leg.best_odds,
  });
  const sortHeader = (key: NonNullable<typeof sort>["key"], label: string) => {
    const direction = sort?.key === key ? sort.direction : null;
    const action = direction ? `Currently ${direction === "asc" ? "ascending" : "descending"}; activate to reverse` : "Activate to sort";
    return <button className="published-selection-sort" type="button" aria-label={`Sort by ${label}. ${action}`} aria-pressed={direction != null} onClick={() => toggle(key)}>
      {label}<span aria-hidden="true">{direction === "asc" ? " ↑" : direction === "desc" ? " ↓" : " ↕"}</span>
    </button>;
  };

  return (
    <section className="published-selections" aria-labelledby="published-selections-title">
      <div className="published-selections-heading">
        <div>
          <span className="eyebrow">Today’s published picks</span>
          <h2 id="published-selections-title">Published selections</h2>
        </div>
        <span className="published-selection-count">{rows.length} unique {rows.length === 1 ? "selection" : "selections"}</span>
      </div>
      <p className="published-selections-note">Each match pick appears once. Review the Conservative ticket first, then Balanced if its legs still fit your decision. Tier names and odds describe construction rules, not a promise of profit. The tiers that include each pick are shown here; each full published record is below.</p>
      {!canViewSelections ? (
        <p className="published-selections-empty">Selection details are available on Pro. Published ticket summaries remain below.</p>
      ) : rows.length === 0 ? (
        <p className="published-selections-empty">No match selections are available in the published tickets for this date.</p>
      ) : (
        <ul className="published-selection-list">
          <li className="published-selection-header">
            {sortHeader("fixture", "Fixture")}
            {sortHeader("marketPick", "Market pick")}
            {sortHeader("matchStatus", "Match Status")}
            {sortHeader("ticketOdds", "Ticket tier and odds")}
            <span />
          </li>
          {sortedRows.map(({ leg, ticket, tiers }) => {
            const selection = selectionRepeatsMarket(leg.market, leg.selection)
              ? formatSelection(leg.selection)
              : `${formatMarket(leg.market)} · ${formatSelection(leg.selection)}`;
            return (
              <li className="published-selection-item" key={leg.prediction_id ?? `${leg.match_id}|${leg.market}|${leg.selection}`}>
                <button className="published-selection-button" type="button" onClick={() => onSelect(leg, ticket)}>
                  <span className="published-selection-main">
                    <span className="published-selection-match">{leg.home_team} <span>vs</span> {leg.away_team}</span>
                    <span className="published-selection-meta">{leg.competition} · {formatDate(leg.kickoff_at)} · {formatKickoff(leg.kickoff_at)}</span>
                  </span>
                  <span className="published-selection-pick">
                    <span className={`leg-market market-pick ${selectionTone(leg.selection)}`}>{selection}</span>
                  </span>
                  <span className={`published-selection-status ${leg.result ?? "pending"}`}>{matchStatus(leg)}</span>
                  <span className="published-selection-details">
                    <span className="published-selection-tiers"><span>In</span>{Array.from(tiers, ([key, name]) => <span className={ticketTierBadgeClass(key)} key={key}>{name}</span>)}</span>
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
