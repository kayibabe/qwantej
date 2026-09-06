# Data Dictionary

Canonical reference: [`QWANTEJ_FRAMEWORK.md`](QWANTEJ_FRAMEWORK.md) §§11–13
and Appendix C. This document is the concrete schema-level companion — when
adding a column or table, update this file in the same PR (per
`DEVELOPMENT.md`'s definition of done).

## Canonical entities

Provider-specific identifiers must never leak into modelling code. Every
provider fixture/team/competition/market is mapped into these canonical
entities, each carrying a mapping confidence and provenance:

- `fixture_id`, `team_id`, `competition_id`, `season_id`
- Provider mapping tables: source identifiers + mapping confidence
- All timestamps stored in **UTC**; converted to user timezone only at
  presentation
- Every odds quote carries: `bookmaker`, `market`, `selection`,
  `decimal_odds`, `captured_at`, `source`
- Every feature value carries: `feature_version`, `as_of_timestamp`
- Missing data is explicit — never silently imputed without recording the
  imputation policy
- Duplicate/conflicting fixtures require reconciliation rules + an
  `audit_events` entry

## Core tables (institutional memory)

| Table | Minimum responsibility |
| --- | --- |
| `fixtures` | Canonical fixture identity, competition, teams, kickoff, status |
| `providers` / `source_mappings` | Provider metadata and canonical mappings |
| `odds_quotes` | Every timestamped bookmaker quote used or observed |
| `stats_snapshots` | Point-in-time team/fixture statistics |
| `feature_snapshots` | Versioned model-ready features and as-of timestamp |
| `model_registry` | Model family/version, training window, code/artefact hashes, status |
| `model_runs` | Execution metadata, data snapshot, parameters, outputs |
| `predictions` | Raw/ensemble/calibrated/conservative probabilities by market/selection |
| `calibration_models` | Calibrator version, segment, training sample and diagnostics |
| `reliability_snapshots` | LRS/MRS and posterior uncertainty at a point in time |
| `selection_candidates` | QSS, Value Gate result and rejection/pass reasons |
| `accumulators` / `accumulator_legs` | Ticket product, odds, probability, EV, legs and optimiser version |
| `settlements` | Outcomes, P/L, voids and settlement timestamps |
| `bankroll_ledger` | Deposits, withdrawals, stakes, returns and bankroll state |
| `experiments` | Backtests, challenger runs and evaluation metrics |
| `audit_events` | Material system and human actions |

## Point-in-time integrity (framework §13)

- Every prediction stores `prediction_timestamp` and `decision_as_of`.
- Only data with source timestamps `<= decision_as_of` may enter its
  features.
- Closing odds may be stored later for CLV evaluation but must never leak
  into an earlier prediction's feature set.
- Historical corrections create a **new data revision** — they never
  silently rewrite the decision-time snapshot a published prediction used.
- Every prediction links to `model_version`, `feature_version`,
  `calibration_version`, `reliability_snapshot`, and
  `optimiser/risk_policy_version`.
- Where practical, store input snapshot identifiers/hashes and the code
  commit SHA for full reproduction.

## Minimum prediction record (Appendix C)

```
prediction_id, fixture_id, prediction_timestamp, decision_as_of
competition_id, season_id, home_team_id, away_team_id
market, selection, line (where applicable)
poisson_probability, dixon_coles_probability, zinb_probability,
    elo_probability, market_model_probability (where used)
ensemble_probability, calibrated_probability, conservative_probability
bookmaker, executable_odds, quote_timestamp, fair_market_probability
edge_pp, expected_value, uncertainty_measure
DQS, QSS, LRS, MRS, dynamic reliability states
model_version, feature_version, calibration_version, risk_policy_version,
    optimiser_version, code_commit
accumulator_id / product (where applicable)
result, settlement_status, stake, return, profit_loss
closing_odds, CLV, Brier contribution, log-loss contribution
created_at, audit/reason codes
```

## Rejection reason taxonomy (Appendix D)

| Code | Meaning |
| --- | --- |
| `DATA_LOW_DQS` | Data Quality Score below policy |
| `DATA_STALE` | Required data snapshot too old |
| `MODEL_UNSTABLE` | Excessive model disagreement or sensitivity |
| `CALIBRATION_UNAVAILABLE` | No approved calibrator/fallback |
| `UNCERTAINTY_TOO_HIGH` | Conservative probability falls below threshold |
| `MARKET_STALE` | Odds too old to support value claim |
| `EDGE_TOO_LOW` | Probability edge below minimum |
| `EV_NON_POSITIVE` | Conservative EV not positive / below minimum |
| `RELIABILITY_LOW` | LRS/MRS or state below product policy |
| `QSS_LOW` | Selection quality below threshold |
| `CORRELATION_CONCENTRATION` | Dependence or diversification constraint violated |
| `PRODUCT_ODDS_OUT_OF_RANGE` | Ticket cannot satisfy odds band without quality dilution |
| `RISK_STATE_BLOCK` | Current drawdown/operating state blocks product |
| `EXPOSURE_CAP` | Bankroll exposure limit reached |
| `ANOMALY_REVIEW` | Extreme edge, mapping or model-market anomaly unresolved |

These codes are stored, not just logged — they power the "Why selected /
Why rejected" capability (framework §22) and must never be replaced by a
free-text reason as the primary record.

## Key formulas (Appendix B)

| Concept | Definition |
| --- | --- |
| Raw implied probability | `p_raw_market = 1 / decimal_odds` |
| Fair market probability | de-vigged bookmaker/consensus probability |
| Probability edge | `Edge_pp = P_cons - p_market_fair` |
| Selection EV | `EV = P_cons * decimal_odds - 1` |
| Independent ticket baseline | `P_ticket_ind = Π P_cons,i` |
| Ticket EV baseline | `EV_ticket = P_ticket * combined_odds - 1` |
| Shrinkage weight | `w = n_eff / (n_eff + k)` |
| Shrunk reliability estimate | `R_post = w * R_segment + (1-w) * R_parent_or_global` |
| Fractional Kelly | `stake_fraction = kelly_fraction * configured_multiplier`, then hard caps apply |
| CLV | price taken vs. closing market, consistent odds/probability convention |
