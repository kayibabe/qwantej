import { useEffect, useState } from "react";
import { formatDate, formatKickoff, formatSelection, selectionTone } from "../../lib/api";
import { fmt } from "../../utils/currency";
import type { CustomAccumulator, DailyTab } from "./types";

const sourceTicketLabel = (type?: string | null) => ({ safe: "Conservative", balanced: "Balanced", high_odds: "High Odds" }[type ?? ""] ?? "Source ticket");

function latestAccumulatorKickoff(ticket: CustomAccumulator): string {
  return ticket.legs.reduce(
    (latest, leg) => new Date(leg.kickoff_at).getTime() > new Date(latest).getTime() ? leg.kickoff_at : latest,
    ticket.date,
  );
}

function groupedAccumulatorHistory(tickets: CustomAccumulator[]) {
  const years = new Map<string, Map<string, Map<string, CustomAccumulator[]>>>();
  for (const ticket of tickets) {
    const [year, month] = ticket.date.split("-");
    const yearGroup = years.get(year) ?? new Map<string, Map<string, CustomAccumulator[]>>();
    const monthGroup = yearGroup.get(month) ?? new Map<string, CustomAccumulator[]>();
    const dayGroup = monthGroup.get(ticket.date) ?? [];
    dayGroup.push(ticket);
    monthGroup.set(ticket.date, dayGroup);
    yearGroup.set(month, monthGroup);
    years.set(year, yearGroup);
  }
  return [...years.entries()].sort(([left], [right]) => right.localeCompare(left)).map(([year, months]) => ({
    year,
    months: [...months.entries()].sort(([left], [right]) => right.localeCompare(left)).map(([month, dates]) => ({
      month: new Date(`${year}-${month}-01T00:00:00Z`).toLocaleDateString("en-GB", { month: "long", timeZone: "UTC" }),
      dates: [...dates.entries()].sort(([left], [right]) => right.localeCompare(left)),
    })),
  }));
}

export function CustomAccumulatorPanel({
  date,
  tickets,
  onCreate,
  onUpdate,
  onDelete,
  onNavigate,
  onOpenPicks,
  focusTicketId,
}: {
  date: string;
  tickets: CustomAccumulator[];
  onCreate: (name: string) => Promise<void>;
  onUpdate: (ticket: CustomAccumulator, update: Partial<CustomAccumulator>) => Promise<void>;
  onDelete: (ticket: CustomAccumulator) => Promise<void>;
  onNavigate?: (tab: DailyTab) => void;
  onOpenPicks?: () => void;
  focusTicketId?: number | null;
}) {
  const openPicks = () => onOpenPicks ? onOpenPicks() : onNavigate?.("daily-match-picks");
  const [name, setName] = useState("");
  const [stakeDrafts, setStakeDrafts] = useState<Record<number, string>>({});
  const history = groupedAccumulatorHistory(tickets);
  useEffect(() => {
    if (focusTicketId == null || !tickets.some((ticket) => ticket.id === focusTicketId)) return;
    const target = document.getElementById(`custom-accumulator-${focusTicketId}`);
    target?.scrollIntoView?.({ block: "center" });
    target?.focus({ preventScroll: true });
  }, [focusTicketId, tickets]);
  const create = async () => {
    const title = name.trim() || `${formatDate(date)} accumulator`;
    try {
      await onCreate(title);
      setName("");
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Unable to save draft");
    }
  };
  const updateTicket = async (ticket: CustomAccumulator, update: Partial<CustomAccumulator>): Promise<boolean> => {
    try {
      await onUpdate(ticket, update);
      return true;
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Unable to save accumulator");
      return false;
    }
  };
  const commitStake = async (ticket: CustomAccumulator, value: string) => {
    const stake = value.trim() === "" ? null : Number(value);
    if (stake !== null && (!Number.isFinite(stake) || stake <= 0)) return;
    await updateTicket(ticket, { stake });
    setStakeDrafts((current) => {
      const next = { ...current };
      delete next[ticket.id];
      return next;
    });
  };
  const clearTicket = (ticket: CustomAccumulator) => {
    if (ticket.status === "placed" || ticket.legs.length === 0) return;
    if (!window.confirm(`Clear all selections from “${ticket.name}”?`)) return;
    void updateTicket(ticket, { legs: [], stake: null });
  };
  const deleteTicket = async (ticket: CustomAccumulator) => {
    if (!window.confirm(`Delete “${ticket.name}”? This removes the saved draft.`)) return;
    try {
      await onDelete(ticket);
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Unable to delete draft");
    }
  };
  return (
    <section className="selection-panel custom-accumulators">
      <div className="section-heading">
        <div>
          <h2>My accumulators</h2>
          <span className="section-note">
            Personal accumulators are persisted with immutable selection snapshots and settle automatically after placement
          </span>
        </div>
        <form className="custom-create-form" onSubmit={(event) => { event.preventDefault(); create(); }}>
          <label htmlFor="new-accumulator-name">New draft</label>
          <input
            id="new-accumulator-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Name (optional)"
            aria-label="New accumulator name"
          />
          <button className="btn-primary btn-sm" type="submit">
            + Create draft
          </button>
        </form>
      </div>
      {tickets.length === 0 ? (
        <div className="custom-empty-state">
          <strong>No accumulators yet</strong>
          <p>Create a draft for the selected date, then review the qualifying Daily Match Picks.</p>
          <div className="custom-empty-actions">
            <button className="btn-ghost btn-sm" onClick={openPicks}>{onOpenPicks ? "Open Research" : "View Daily Match Picks"}</button>
          </div>
        </div>
      ) : (
        <div className="custom-accumulator-history">
          {history.map(({ year, months }) => <section className="custom-accumulator-year" key={year}>
            <h3>{year}</h3>
            {months.map(({ month, dates }) => <section className="custom-accumulator-month" key={`${year}-${month}`}>
              <h4>{month} {year}</h4>
              {dates.map(([day, dayTickets]) => <section className="custom-accumulator-day" key={day}>
                <h5><span>{formatDate(day)}</span><small>{dayTickets.length} ticket{dayTickets.length === 1 ? "" : "s"}</small></h5>
                <div className="custom-ticket-list">
                  {dayTickets.map((ticket) => {
            const odds = ticket.legs.reduce(
              (total, leg) => total * (leg.best_odds ?? 1),
              1,
            );
            const potentialReturn = ticket.stake != null ? ticket.stake * odds : null;
            const hasStakeDraft = Object.prototype.hasOwnProperty.call(stakeDrafts, ticket.id);
            const stakeText = hasStakeDraft ? stakeDrafts[ticket.id] : ticket.stake != null ? String(ticket.stake) : "";
            const parsedStake = stakeText.trim() === "" ? null : Number(stakeText);
            const canPlace = ticket.legs.length >= 2 && parsedStake != null && Number.isFinite(parsedStake) && parsedStake > 0;
            const pendingLegs = ticket.legs.filter((leg) => !leg.result).length;
            const statusLabel = ticket.status === "draft" ? "Draft" : ticket.status === "placed" && pendingLegs > 0 ? `Open · ${pendingLegs} pending` : ticket.status === "placed" ? "Placed" : `Settled · ${ticket.status}`;
            const isLocked = ticket.status !== "draft";
            const legsLocked = isLocked || ticket.automatic;
            const probabilities = ticket.legs.map((leg) => leg.model_probability).filter((value): value is number => value != null);
            const chanceToWin = probabilities.length === ticket.legs.length && probabilities.length > 0 ? probabilities.reduce((total, value) => total * value, 1) : null;
            const competitionCounts = ticket.legs.reduce<Record<string, number>>((counts, leg) => ({ ...counts, [leg.competition]: (counts[leg.competition] ?? 0) + 1 }), {});
            const concentration = ticket.legs.length ? Math.max(...Object.values(competitionCounts)) / ticket.legs.length : 0;
            const riskScore = chanceToWin == null ? null : Math.max(0, Math.min(100, (1 - chanceToWin) * 70 + concentration * 10));
            const expectedReturn = chanceToWin == null ? null : chanceToWin * odds - 1;
            const sourceSnapshots = Object.values(ticket.source_ticket_snapshots ?? {});
            const latestKickoff = latestAccumulatorKickoff(ticket);
            return (
              <article id={`custom-accumulator-${ticket.id}`} tabIndex={-1} className={`custom-ticket ${ticket.status}${ticket.automatic ? " automatic-ticket" : ""}`} key={ticket.id}>
                <div className="custom-ticket-header">
                  <div>
                    <strong>{ticket.name}</strong>
                    {ticket.automatic && <div className="automatic-ticket-badges"><span className="custom-status-badge automatic">My accumulator</span><span className="relaxed-badge">Includes games to <span className="event-date">{formatDate(latestKickoff)}</span></span></div>}
                    <span><span className="event-date">{formatDate(ticket.date)}</span> · {ticket.legs.length} leg{ticket.legs.length === 1 ? "" : "s"}</span>
                  </div>
                  <span className={`custom-status-badge ${ticket.status}`}>{statusLabel}</span>
                </div>
                {ticket.automatic ? <>
                  <p className="automatic-ticket-note"><strong>Longer combined ticket:</strong> this merges legs from Conservative and Balanced without fresh joint optimisation. Its chance and return use multiplied leg snapshots and do not apply the official correlation model; treat them as illustrative only.</p>
                  <div className="custom-ticket-metrics automatic-ticket-metrics">
                    <span><small>Combined odds</small><b>{ticket.legs.length ? `${odds.toFixed(2)}×` : "—"}</b></span>
                    <span><small>Illustrative chance</small><b>{chanceToWin == null ? "—" : `${(chanceToWin * 100).toFixed(1)}%`}<em>{chanceToWin ? `about 1 in ${Math.max(1, Math.round(1 / chanceToWin))}` : "snapshot unavailable"}</em></b></span>
                    <span><small>Risk indicator</small><b>{riskScore == null ? "—" : `${riskScore.toFixed(0)}/100`}</b></span>
                    <span><small>Illustrative return</small><b>{expectedReturn == null ? "—" : `${expectedReturn >= 0 ? "+" : ""}${(expectedReturn * 100).toFixed(1)}%`}</b></span>
                  </div>
                  {sourceSnapshots.length > 0 && <p className="automatic-ticket-note">Source versions: {sourceSnapshots.map((source) => `${source.ticket_type ?? "ticket"} v${source.version ?? "—"}${source.publication_hash ? ` · ${source.publication_hash.slice(0, 10)}…` : ""}`).join(" · ")}</p>}
                  <div className="ticket-summary automatic-ticket-summary"><strong>{ticket.legs.length} legs</strong><span className="ticket-result-chip pending"><b>{pendingLegs}</b> pending</span></div>
                </> : <div className="custom-ticket-metrics">
                  <span><small>Combined odds</small><b>{ticket.legs.length ? `${odds.toFixed(2)}×` : "—"}</b></span>
                  <span><small>Stake</small><b>{ticket.stake != null ? fmt(ticket.stake) : "—"}</b></span>
                  <span><small>Potential return</small><b>{potentialReturn != null ? fmt(potentialReturn) : "—"}</b></span>
                  <span><small>Potential P&amp;L</small><b className={potentialReturn != null && ticket.stake != null && potentialReturn > ticket.stake ? "positive" : ""}>{potentialReturn != null && ticket.stake != null ? fmt(potentialReturn - ticket.stake) : "—"}</b></span>
                </div>}
                {ticket.legs.length === 0 ? (
                  <div className="custom-ticket-empty">
                    <strong>No selections yet</strong>
                    <span>Add at least two selections before marking this accumulator placed.</span>
                    <div className="custom-empty-actions">
                      <button className="btn-ghost btn-sm" onClick={openPicks}>{onOpenPicks ? "Open Research" : "Add qualifying picks"}</button>
                    </div>
                  </div>
                ) : (
                  <div className="custom-ticket-legs">
                    {ticket.legs.map((leg) => (
                      <div className="custom-ticket-leg" key={leg.prediction_id}>
                        <div className="custom-ticket-leg-main">
                          <strong>{leg.home_team} <span>vs</span> {leg.away_team}</strong>
                          <small className="custom-ticket-leg-meta">
                            <span className="custom-leg-competition">{leg.competition}</span>
                            <span className="custom-leg-date" aria-label={`Match date ${formatDate(leg.kickoff_at)}`}>{formatDate(leg.kickoff_at)}</span>
                            <span className="custom-leg-time" aria-label={`Kickoff time ${formatKickoff(leg.kickoff_at)}`}>{formatKickoff(leg.kickoff_at)}</span>
                            <span className={`custom-leg-market market-pick ${selectionTone(leg.selection)}`}>{formatSelection(leg.selection)}</span>
                          </small>
                        </div>
                        <div className="custom-ticket-leg-evidence">
                          <span className="custom-leg-odds">{leg.best_odds != null ? `${leg.best_odds.toFixed(2)}×` : "—"}</span>
                          <span>Q {leg.q_score.toFixed(1)}</span>
                          <span>{leg.model_agreement != null ? `${(leg.model_agreement * 100).toFixed(1)} pp` : "—"}</span>
                          {ticket.automatic && leg.source_ticket_type && <span className={`source-ticket-badge ${leg.source_conflict ? "safe" : leg.source_ticket_type}`}>{leg.source_conflict ? "Conservative priority" : sourceTicketLabel(leg.source_ticket_type)}{leg.source_ticket_version ? ` · v${leg.source_ticket_version}` : ""}</span>}
                          <button
                            type="button"
                            disabled={legsLocked}
                            title={legsLocked ? "Generated legs cannot be changed" : "Remove selection"}
                            aria-label={`Remove ${leg.home_team} versus ${leg.away_team}`}
                            onClick={() => void updateTicket(ticket, { legs: ticket.legs.filter((row) => row.prediction_id !== leg.prediction_id) })}
                          >
                            ×
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                <div className="custom-ticket-controls">
                  <label htmlFor={`stake-${ticket.id}`}>
                    <span>Stake amount</span>
                    <input
                      id={`stake-${ticket.id}`}
                      type="number"
                      min="0.01"
                      step="0.01"
                      inputMode="decimal"
                      value={stakeText}
                      disabled={isLocked}
                      placeholder="0.00"
                      onChange={(event) => setStakeDrafts((current) => ({ ...current, [ticket.id]: event.target.value }))}
                      onBlur={(event) => void commitStake(ticket, event.currentTarget.value)}
                    />
                  </label>
                  <div className="custom-ticket-actions">
                    <button
                      type="button"
                      className="btn-primary btn-sm"
                      disabled={isLocked || (ticket.status === "draft" && !canPlace)}
                      title={ticket.status === "draft" && !canPlace ? "Add at least two selections and enter a stake" : undefined}
                      onClick={async () => {
                        if (ticket.status !== "draft" || parsedStake == null) return;
                        const saved = await updateTicket(ticket, { stake: parsedStake, status: "placed" });
                        if (saved) {
                          setStakeDrafts((current) => {
                            const next = { ...current };
                            delete next[ticket.id];
                            return next;
                          });
                        }
                      }}
                    >
                      {ticket.status === "draft" ? "Mark placed" : ticket.status === "placed" ? "Placed" : `Settled · ${ticket.status}`}
                    </button>
                    <button className="btn-ghost btn-sm" disabled={legsLocked || ticket.legs.length === 0} onClick={() => clearTicket(ticket)}>
                      Clear selections
                    </button>
                    {!ticket.automatic && <button className="btn-ghost btn-sm danger-action" onClick={() => deleteTicket(ticket)}>
                      Delete draft
                    </button>}
                  </div>
                </div>
                {ticket.status === "draft" && !canPlace && ticket.legs.length > 0 && (
                  <p className="custom-ticket-validation">Add at least one more selection and enter a stake before marking placed.</p>
                )}
                {isLocked && <p className="custom-ticket-locked">Placed accumulator locked · settlement will happen automatically when all matches finish.</p>}
              </article>
                  );
                  })}
                </div>
              </section>)}
            </section>)}
          </section>)}
        </div>
      )}
    </section>
  );
}
