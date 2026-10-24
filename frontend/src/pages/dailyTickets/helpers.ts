import type { CustomAccumulator as ApiCustomAccumulator, SelectionSummary } from "../../lib/api";
import { dateStringInProductTimeZone } from "../../utils";
import type {
  CustomAccumulator,
  MatchDisplayState,
  SelectionDisplayState,
} from "./types";

export function localDateString(d = new Date()): string {
  return dateStringInProductTimeZone(d);
}

export const TODAY = localDateString();

export function spreadLabel(value: number | null | undefined) {
  if (value == null) return "Unavailable";
  if (value <= 0.05) return "Strong alignment";
  if (value <= 0.1) return "Acceptable";
  if (value <= 0.15) return "Caution";
  return "High disagreement";
}

export function spreadTone(value: number | null | undefined) {
  if (value == null) return "unknown";
  if (value <= 0.05) return "strong";
  if (value <= 0.1) return "acceptable";
  if (value <= 0.15) return "caution";
  return "high";
}

export function gradeTone(grade: string | undefined) {
  return grade ? grade.toLowerCase().replace("+", "-plus") : "unknown";
}

export function phaseLabel(phase?: string | null) {
  return ({ '1st_half': '1st Half', half_time: 'Half Time', '2nd_half': '2nd Half', extra_time: 'Extra Time', penalties: 'Penalties', suspended: 'Suspended', interrupted: 'Interrupted', live: 'Live' } as Record<string, string>)[phase ?? ''] ?? null;
}

export function matchDisplayState(row: SelectionSummary): MatchDisplayState {
  const status = row.match_status?.toLowerCase();
  if (status === "finished") return "finished";
  if (status === "live") return "live";
  if (status === "postponed") return "postponed";
  if (status === "cancelled") return "cancelled";
  return "scheduled";
}

export function matchStatusText(row: SelectionSummary): string {
  const state = matchDisplayState(row);
  const score = row.home_goals != null && row.away_goals != null
    ? `${row.home_goals}–${row.away_goals}`
    : null;
  if (state === "finished") return score ? `Finished · ${score}` : "Finished";
  if (state === "live") {
    const phase = phaseLabel(row.live_phase) ?? "Live";
    const elapsed = row.elapsed_minutes != null ? ` · ${row.elapsed_minutes}'` : "";
    return `${phase}${elapsed}${score ? ` · ${score}` : ""}`;
  }
  if (state === "postponed") return "Postponed";
  if (state === "cancelled") return "Cancelled";
  return "Upcoming";
}

export function selectionDisplayState(row: SelectionSummary): SelectionDisplayState {
  if (matchDisplayState(row) === "live") return "inplay";
  if (row.result === "won" || row.result === "lost" || row.result === "void") {
    return row.result;
  }
  return "pending";
}

export function selectionStatusLabel(state: SelectionDisplayState): string {
  return {
    won: "Won",
    lost: "Lost",
    void: "Void",
    inplay: "In play",
    pending: "Pending",
  }[state];
}

const HARD_ACCUMULATOR_BLOCKERS = new Set([
  "MISSING_ODDS",
  "LEG_ODDS_OUT_OF_RANGE",
  "MISSING_EDGE",
  "EDGE_BELOW_NO_BET_THRESHOLD",
  "INSUFFICIENT_MODEL_SET",
  "DATA_QUALITY_BELOW_THRESHOLD",
  "MISSING_ODDS_TIMESTAMP",
  "STALE_ODDS",
  "LEAGUE_CALIBRATION_BELOW_THRESHOLD",
  "MARKET_CALIBRATION_UNRELIABLE",
  "EDGE_BAND_CALIBRATION_UNRELIABLE",
]);

const REJECTION_REASON_LABELS: Record<string, string> = {
  INSUFFICIENT_RECENT_SAMPLE: "There are not enough recent home and away matches to assess this fixture.",
  CALIBRATION_UNVALIDATED: "This market's probability model has not passed its validation checks.",
  PROJECTED_XG: "Projected match xG",
  PROJECTED_GOALS: "Projected total goals",
  COMBINED_SCORED: "Combined goals scored",
  COMBINED_CONCEDED: "Combined goals conceded",
  COMBINED_SHOTS_ON_TARGET: "Combined shots on target",
  EXPECTED_FIRST_HALF_GOALS: "Expected first-half goals",
  UNDER25_FREQUENCY: "Under 2.5 frequency",
  UNDER35_FREQUENCY: "Under 3.5 frequency",
  UNDER45_FREQUENCY: "Under 4.5 frequency",
  OVER25_FREQUENCY: "Over 2.5 frequency",
  OVER35_FREQUENCY: "Over 3.5 frequency",
  OVER45_FREQUENCY: "Over 4.5 frequency",
  BTTS_FREQUENCY: "Both teams to score frequency",
  FIRST_HALF_UNDER05_FREQUENCY: "First-half Under 0.5 frequency",
  FIRST_HALF_UNDER15_FREQUENCY: "First-half Under 1.5 frequency",
  ZERO_ZERO_FREQUENCY: "Historical 0–0 frequency",
  DEFENSIVE_ABSENCES: "Defender or goalkeeper absences",
  OPPONENT_STRENGTH: "Opponent-strength adjustment",
  TACTICS_LINEUPS: "Tactical and lineup review",
  TACTICALS_LINEUPS: "Tactical and lineup review",
  MATCHUP_ADJUSTMENT: "Matchup adjustment",
  OPPONENT_SAMPLE_WEIGHTING: "Opponent and sample weighting",
  LEAGUE_VALIDATION: "League-specific validation",
  CHANCE_QUALITY: "Chance-quality review",
  DEFENSIVE_STABILITY: "Defensive-stability review",
  CONTROLLED_TEMPO: "Match-tempo review",
  STRONG_SUPPORTING_EVIDENCE: "Supporting evidence for a conditional Grade B pick",
  ATTRACTIVE_PRICE_REVIEW: "Price review for a conditional Grade B pick",
  COMPELLING_VALUE_REVIEW: "Value review for a conditional Grade B pick",
  HIGH_SCORING_RATE: "One team has a high scoring rate",
  EXCEPTIONAL_CHANCE_CREATION: "Both teams create many high-quality chances",
  DOMINANT_ATTACK_VULNERABLE_DEFENCE: "A strong attack faces a vulnerable defence",
  DEFENDER_GOALKEEPER_ABSENCES: "Important defenders or a first-choice goalkeeper may be missing",
  ATTACKING_FAVOURITE: "A strong attacking favourite increases the chance of a goal",
  NO_POSITIVE_EXPECTED_VALUE: "The available odds do not offer positive expected value",
  NO_POSITIVE_STRESSED_VALUE: "Expected value is not positive after allowing for probability uncertainty",
  PROBABILITY_BELOW_THRESHOLD: "The model probability is below the required minimum",
  PROBABILITY_MISSING: "A model probability is unavailable",
  PRIMARY_PROBABILITY_BELOW_72: "The model probability is below the 72% primary-pool minimum",
  CALIBRATION_UNRELIABLE: "Historical model performance is not reliable enough",
  CALIBRATION_BELOW_THRESHOLD: "Calibration is below the required standard",
  INSUFFICIENT_MODEL_SET: "Too few models contributed to this prediction",
  DATA_QUALITY_BELOW_THRESHOLD: "The fixture data quality is below the required standard",
  MISSING_ODDS: "A valid bookmaker price is unavailable",
  MISSING_ODDS_TIMESTAMP: "The bookmaker price has no recorded timestamp",
  STALE_ODDS: "The bookmaker price is out of date",
  MISSING_EDGE: "A price comparison could not be calculated",
  EDGE_BELOW_NO_BET_THRESHOLD: "The price advantage is below the minimum required",
  MODEL_PROBABILITY_ABOVE_CALIBRATION_CAP: "The probability exceeds the range supported by calibration",
  Q_SCORE_BELOW_TIER: "The quality score is below this ticket's minimum",
  LEAGUE_CALIBRATION_BELOW_THRESHOLD: "This league has not met the calibration standard",
  MARKET_CALIBRATION_UNRELIABLE: "This market's historical calibration is unreliable",
  EDGE_BAND_CALIBRATION_UNRELIABLE: "Predictions with this price advantage have not calibrated reliably",
  LEG_ODDS_OUT_OF_RANGE: "The price is outside the allowed range",
  LEG_ODDS_OUT_OF_TIER_BAND: "The price is outside this ticket's allowed range",
  MARGIN_TOO_HIGH: "The bookmaker margin is too high",
  PRICE_OUT_OF_LINE: "The price is unusually far from the market consensus",
  MISSING_FAIR_PRICE: "There is not enough market data to calculate a fair price",
  POST_KICKOFF_ODDS: "The odds were recorded after the match started",
  QUOTE_AFTER_DECISION_TIME: "The odds were recorded after the prediction was made",
  MARKET_POLICY_SHADOW_EXCLUDED: "A market-policy review excluded this selection",
  MARKET_RESTRICTED_FOR_RESEARCH: "This market is restricted from research tickets",
  INCONSISTENT_GOAL_PROJECTIONS: "The home and away goal projections do not add up to the match total",
  INDEPENDENT_DEFAULT: "No specific relationship between these selections was identified",
  SAME_MATCH: "Another selection already uses this match",
  SAME_LEAGUE: "The ticket already includes another match from this league",
  SAME_KICKOFF_SLOT: "This match starts at the same time as another selection",
  SAME_MARKET_FAMILY: "This selection is in the same market group as another leg",
  SHARED_TEAM: "The match shares a team with another selection",
};

export function reasonLabel(code: string): string {
  const normalized = code.toUpperCase();
  const marketCode = normalized.match(/^(OVER45|UNDER05|UNDER15|UNDER25|UNDER35)_(.+)$/);
  if (marketCode) {
    const [, market, remainder] = marketCode;
    const marketLabel = ({ OVER45: "Over 4.5", UNDER05: "Under 0.5", UNDER15: "Under 1.5", UNDER25: "Under 2.5", UNDER35: "Under 3.5" } as Record<string, string>)[market];
    const suffix = ["MISSING", "OUTSIDE", "UNVERIFIED", "FLAGGED", "UNREVIEWED"].find(value => remainder.endsWith(`_${value}`));
    const metric = suffix ? remainder.slice(0, -(suffix.length + 1)) : remainder;
    const description = REJECTION_REASON_LABELS[metric] ?? metric.toLowerCase().replace(/_/g, " ");
    if (suffix === "MISSING") return `${marketLabel}: ${description} is unavailable.`;
    if (suffix === "OUTSIDE") return `${marketLabel}: ${description} is outside the preferred threshold.`;
    if (suffix === "UNVERIFIED") return `${marketLabel}: ${description} has not been verified.`;
    if (suffix === "FLAGGED") return `${marketLabel}: review flagged a risk with ${description.toLowerCase()}.`;
    if (suffix === "UNREVIEWED") return `${marketLabel}: ${description} has not been reviewed.`;
    return `${marketLabel}: ${description}.`;
  }
  return REJECTION_REASON_LABELS[normalized] ?? normalized.toLowerCase().replace(/_/g, " ").replace(/^./, char => char.toUpperCase());
}

export function accumulatorBlockers(row: SelectionSummary): string[] {
  const blockers = (row.reason_codes ?? []).filter((code) =>
    HARD_ACCUMULATOR_BLOCKERS.has(code),
  );
  if (matchDisplayState(row) !== "scheduled") blockers.push("MATCH_NOT_UPCOMING");
  if (row.best_odds == null || row.best_odds <= 0) blockers.push("MISSING_ODDS");
  if (row.edge == null) blockers.push("MISSING_EDGE");
  if (row.market === "over_4.5" && row.over45_qualification?.status !== "QUALIFY") blockers.push("OVER45_NOT_QUALIFIED");
  if (row.market === "over_1.5" && row.over15_qualification?.status !== "QUALIFY") blockers.push("OVER15_NOT_QUALIFIED");
  if (row.market === "over_2.5" && row.over25_qualification?.status !== "QUALIFY") blockers.push("OVER25_NOT_QUALIFIED");
  if (row.market === "over_3.5" && row.over35_qualification?.status !== "QUALIFY") blockers.push("OVER35_NOT_QUALIFIED");
  if (row.market === "under_2.5" && row.under25_qualification?.status !== "QUALIFY") blockers.push("UNDER25_NOT_QUALIFIED");
  if (row.market === "under_3.5" && row.under35_qualification?.status !== "QUALIFY") blockers.push("UNDER35_NOT_QUALIFIED");
  if (row.market === "under_1.5" && row.under15_qualification?.status !== "QUALIFY") blockers.push("UNDER15_NOT_QUALIFIED");
  if (row.market === "under_0.5" && row.under05_qualification?.status !== "QUALIFY") blockers.push("UNDER05_NOT_QUALIFIED");
  if (!passesUnder05Value(row)) blockers.push("UNDER05_NO_POSITIVE_STRESSED_VALUE");
  return [...new Set(blockers)];
}

export function passesUnder05Value(row: SelectionSummary): boolean {
  return row.market !== "under_0.5" ||
    (row.under05_qualification?.status === "QUALIFY" &&
      (row.under05_qualification.stressed_probability ?? 0) * (row.best_odds ?? 0) > 1);
}

export function withRejectionEvidence(
  rows: SelectionSummary[],
  rejectedRows: SelectionSummary[],
): SelectionSummary[] {
  const reasons = new Map(
    rejectedRows.map((row) => [row.prediction_id, row.reason_codes ?? []]),
  );
  return rows.map((row) => ({
    ...row,
    reason_codes: reasons.get(row.prediction_id) ?? row.reason_codes,
  }));
}

export function apiAccumulatorToUi(row: ApiCustomAccumulator): CustomAccumulator {
  return {
    id: row.id,
    name: row.name,
    date: row.target_date,
    legs: row.legs.map((leg) => ({
      prediction_id: leg.prediction_id,
      match_id: leg.match_id,
      home_team: leg.home_team,
      away_team: leg.away_team,
      competition: leg.competition,
      kickoff_at: leg.kickoff_at,
      market: leg.market,
      selection: leg.selection,
      model_probability: leg.probability_snapshot ?? undefined,
      q_score: leg.q_score_snapshot ?? 0,
      edge: leg.edge_snapshot,
      source_ticket_id: leg.source_ticket_id,
      source_ticket_type: leg.source_ticket_type,
      source_ticket_version: leg.source_ticket_version,
      source_conflict: leg.source_conflict,
      best_odds: leg.odds_snapshot,
      result: leg.result === "pending" ? null : leg.result,
    })),
    stake: row.stake,
    status: row.status,
    automatic: row.automatic,
    source_ticket_snapshots: row.source_ticket_snapshots,
  };
}
