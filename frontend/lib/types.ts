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
