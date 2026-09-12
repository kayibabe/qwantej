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
  quote_captured_at: string | null
}

export interface AccumulatorOut {
  id: string
  product: string
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
}

export interface AccumulatorPage {
  items: AccumulatorOut[]
  total: number
  limit: number
  offset: number
}

export interface TodayStatus {
  status: "qualified" | "no_qualifying_combination" | "collecting" | "stale" | "no_upcoming_data"
  label: string
  detail: string
  date: string
  data_freshness_utc: string | null
  checked_leagues: string[]
  next_run_utc: string | null
  tickets_available: number
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
  max_drawdown: number | null
  volatility: number | null
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
