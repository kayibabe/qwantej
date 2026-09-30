export interface PredictionOut {
  id: string
  fixture_id: string
  prediction_timestamp: string
  decision_as_of: string
  market: string
  selection: string
  line: number | null
  conservative_probability: number | null
  executable_odds: number | null
  edge_pp: number | null
  expected_value: number | null
  qss: number | null
  dqs: number | null
  created_at: string
  bookmaker?: string | null
  home_team?: string | null
  away_team?: string | null
  kickoff_utc?: string | null
  competition_name?: string | null
  /** Effective settlement outcome once settled: win / loss / void / push. */
  outcome?: string | null
  /** Archived audit boundary: research rows cannot be treated as live signals. */
  research_mode: boolean
  gate_passed: boolean
  model_version_label: string | null
  /** Kickoff passed without an effective settlement; requires data refresh. */
  settlement_overdue: boolean
}

export interface PredictionPage {
  items: PredictionOut[]
  total: number
  limit: number
  offset: number
}

export interface SettlementOut {
  id: string
  subject_type: string
  subject_id: string
  outcome: string
  settled_at: string
  result_source: string | null
  taken_odds: number | null
  closing_odds: number | null
  clv: number | null
  taken_probability: number | null
  brier_contribution: number | null
  calibration_bin: string | null
  supersedes_id: string | null
  closing_quote_id: string | null
  created_at: string
}

export interface SettlementSummary {
  n_settled: number
  n_wins: number
  n_losses: number
  n_voids: number
  win_rate: number | null
  avg_clv: number | null
  avg_brier: number | null
}

export interface SettlementPage {
  items: SettlementOut[]
  total: number
  limit: number
  offset: number
}

export interface AccumulatorLegOut {
  id: string
  leg_index: number
  prediction_id: string
  fixture_id: string
  league_id: string
  market_family: string
  selection: string
  decimal_odds: number
  conservative_probability: number
  edge: number
  qss: number
  bookmaker: string | null
  home_team: string | null
  away_team: string | null
  kickoff_utc: string | null
  competition_name: string | null
  match_state: "pending" | "live" | "won" | "lost" | "void" | string
  fixture_status: string
  score: string | null
  live_phase: string | null
  elapsed_minutes: number | null
  settlement_outcome: string | null
  quote_captured_at: string | null
  match_evidence?: MatchEvidence | null
}

export interface DailyCandidateOut {
  id: string
  run_id: string
  product_day: string
  captured_at_run: string
  prediction_id: string
  fixture_id: string
  home_team: string | null
  away_team: string | null
  competition_name: string | null
  kickoff_utc: string
  market: string
  selection: string
  model_probability: number
  market_probability: number
  decimal_odds: number
  quote_captured_at: string
  dqs: number
  bookmaker: string | null
  candidate_status: "selected" | "not_selected" | string
  exclusion_reason: string | null
  selected_product: string | null
  accumulator_id: string | null
  fixture_status: string
  score: string | null
  outcome: string | null
}

export interface DailyCandidatePage {
  product_day: string
  run_id: string | null
  items: DailyCandidateOut[]
  total: number
  limit: number
  offset: number
}

export interface MatchEvidenceRow {
  date: string | null
  opponent: string
  venue: "home" | "away"
  result: "W" | "D" | "L"
  score: string
}

export interface MatchEvidence {
  as_of: string
  home_form: MatchEvidenceRow[]
  away_form: MatchEvidenceRow[]
  home_summary: { played: number; wins: number; draws: number; losses: number; goals_for: number; goals_against: number; points_per_game: number | null }
  away_summary: { played: number; wins: number; draws: number; losses: number; goals_for: number; goals_against: number; points_per_game: number | null }
  h2h: Array<{ date: string | null; home_team: string; away_team: string; home_score: number | null; away_score: number | null }>
  prediction: {
    market: string; selection: string; line: number | null
    ensemble_probability: number | null; calibrated_probability: number | null; conservative_probability: number | null
    fair_market_probability: number | null; edge_pp: number | null; qss: number | null; dqs: number | null
    model_probabilities: Record<string, number>; decision_as_of: string; model_version_id: string | null
    feature_version: string | null; calibration_version: string | null
  } | null
}

export interface AccumulatorOut {
  id: string
  product: string
  policy_version?: string | null
  status: string
  combined_odds: number
  conservative_joint_probability: number
  stressed_joint_probability: number
  objective_score: number
  published_at: string
  locked_at: string | null
  stake: number | null
  risk_policy_version: string | null
  legs: AccumulatorLegOut[]
  created_at: string
  /** Derived from leg settlements with the same rule the settlement worker uses. */
  result?: TicketResult
  /** Decimal odds the decided ticket settles at (void legs drop out of a win). */
  settlement_odds?: number | null
  /** Profit on a flat one-unit stake: odds − 1 won, −1 lost, 0 void. */
  profit_units?: number | null
}

export type TicketResult = "won" | "lost" | "void" | "pending"

export interface AccumulatorPage {
  items: AccumulatorOut[]
  total: number
  limit: number
  offset: number
}

export interface TodayStatus {
  status: "qualified" | "no_qualifying_combination" | "collecting" | "stale" | "no_upcoming_data" | "no_ticket_recorded"
  label: string
  detail: string
  date: string
  data_freshness_utc: string | null
  checked_leagues: string[]
  observed_leagues: string[]
  observed_fixture_count: number
  next_run_utc: string | null
  tickets_available: number
}

export interface CalibrationBinOut {
  predicted_probability: number
  observed_frequency: number
  count: number
}

export interface KPIReportOut {
  // Counts
  n_total: number
  n_settled: number
  n_wins: number
  n_losses: number
  n_voids: number
  n_pushes: number
  // Betting
  hit_rate: number | null
  average_odds: number | null
  break_even_hit_rate: number | null
  // Predictive
  brier_score: number | null
  brier_skill_score: number | null
  log_loss: number | null
  ece: number | null
  calibration_slope: number | null
  calibration_intercept: number | null
  // Market quality
  mean_clv: number | null
  n_clv: number
  // Financial
  roi: number | null
  total_stake: number | null
  total_profit: number | null
  // Risk
  max_drawdown: number | null // stake units, not a fraction
  volatility: number | null
  // Reliability diagram
  calibration_bins: CalibrationBinOut[] | null
  /** "real" = recorded stakes; "flat_unit" = 1 unit per priced bet; null = nothing priced settled. */
  stake_basis?: "real" | "flat_unit" | null
  /** Kicked off but not settled yet (only on /performance/report). */
  n_awaiting?: number | null
}

export interface PerformanceSegmentsOut {
  by: string
  segments: Record<string, KPIReportOut>
}

export interface ModelRunOut {
  id: string
  model_id: string
  kind: string
  status: string
  started_at: string
  finished_at: string | null
  data_as_of: string | null
  data_snapshot_ref: string | null
  code_commit: string | null
  parameters: Record<string, unknown> | null
  metrics: Record<string, unknown> | null
  log_uri: string | null
  created_at: string
  updated_at: string
}

export interface ModelRegistryOut {
  id: string
  family: string
  name: string
  version: string
  status: string
  training_window_start: string | null
  training_window_end: string | null
  code_commit: string | null
  artefact_hash: string | null
  artefact_uri: string | null
  hyperparameters: Record<string, unknown> | null
  description: string | null
  promoted_at: string | null
  retired_at: string | null
  created_at: string
  updated_at: string
}

export interface ModelRegistryDetailOut extends ModelRegistryOut {
  runs: ModelRunOut[]
}

export interface ModelRegistryPage {
  items: ModelRegistryOut[]
  total: number
  limit: number
  offset: number
}

// Real money: amounts are exact decimal strings from the API.
export interface BankrollSummaryOut {
  account: string
  currency: string
  balance: string
  open_exposure: string
  available: string
  open_bets: number
}

export interface RealBetResultsOut {
  currency: string
  n_bets: number
  n_open: number
  n_won: number
  n_lost: number
  n_void: number
  n_cashed_out: number
  settled_stake: string
  settled_profit: string
  roi: string | null
}

export type ResultsGranularity = "year" | "month" | "day"

export interface AccumulatorProductResultOut {
  product: string
  daily_pick: boolean
  won: number
  lost: number
  void: number
  pending: number
  total: number
  win_rate: number | null
  /** Summed flat one-unit profit of the decided tickets. */
  profit_units?: number
}

export interface AccumulatorPeriodResultOut {
  period: string
  products: AccumulatorProductResultOut[]
}

export interface AccumulatorResultsOut {
  granularity: ResultsGranularity
  periods: AccumulatorPeriodResultOut[]
  total_periods: number
}
