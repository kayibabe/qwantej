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
| `calibration_snapshots` | Immutable out-of-sample calibration monitoring windows |
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

## Phase 2 concrete columns (model registry, prediction archive, audit)

Implemented in `backend/models/{registry,predictions,audit}.py`, migration
`e461c24386f2`. Column-level companion to the core-table summaries above.

### `model_registry` (mutable lifecycle entity)

`id`, `family` (enum `model_family`: poisson, dixon_coles, zinb, elo,
bayesian_hierarchical, market, ensemble), `name`, `version`
(`uq_model_registry_name_version`), `status` (enum `model_status`:
development, challenger, champion, retired),
`training_window_start`/`training_window_end`, `code_commit`,
`artefact_hash`, `artefact_uri`, `hyperparameters` (JSON), `description`,
`promoted_at`, `retired_at`, `created_at`, `updated_at`. **No model is live
without a registry row** (`MODEL_GOVERNANCE.md`).

### `model_runs` (mutable: running → succeeded/failed)

`id`, `model_id` → `model_registry`, `kind` (enum `model_run_kind`:
training, backtest, inference, evaluation), `status` (enum
`model_run_status`: running, succeeded, failed), `started_at`,
`finished_at`, `data_as_of` (point-in-time cutoff), `data_snapshot_ref`,
`code_commit`, `parameters` (JSON), `metrics` (JSON), `log_uri`,
`created_at`, `updated_at`.

### `predictions` (immutable, append-only — framework §13)

Decision-time fields only; a correction is a new row. Post-fixture data
(`result`, settlement, stake/return/PL, closing odds, CLV, Brier/log-loss
contributions from Appendix C) lives in the separate `settlements` table so
it can never leak into the decision record — Appendix C is the union view.

Immutability is **enforced in the database** (migrations `da3a07d4e74e` and
`c84f2d19a6b1`): a trigger raises on any UPDATE, DELETE or TRUNCATE of
`predictions`, `audit_events` and `calibration_snapshots`. Calibration-model
artifact fields are frozen after insertion while lifecycle status remains mutable.

- **Identity/PIT**: `id`, `fixture_id` → `fixtures` (competition/season/team
  ids reached via the fixture, not duplicated), `prediction_timestamp`,
  `decision_as_of`.
- **Market**: `market`, `selection`, `line`.
- **Probabilities**: `model_probabilities` (JSON map family→probability —
  one column per family would force a migration per new model, so this
  follows the `stats_snapshots.payload` precedent), plus explicit
  `ensemble_probability`, `calibrated_probability`,
  `conservative_probability` (each `CHECK` in `[0, 1]` when set).
- **Price/value**: `bookmaker`, `executable_odds`, `quote_timestamp`,
  `fair_market_probability` (`[0, 1]`), `edge_pp`, `expected_value`,
  `uncertainty_measure`.
- **Quality/reliability**: `dqs`, `qss`, `lrs`, `mrs` (0–100),
  `dynamic_states` (JSON).
- **Version spine (attribution)**: `model_version_id` → `model_registry`,
  `feature_version`, `calibration_version`, `risk_policy_version`,
  `optimiser_version`, `code_commit` — which versions were in force.
- **Execution/input lineage (replay)**: `model_run_id` → `model_runs` (the
  concrete run that supplied the parameters), `input_snapshot_ref` (retrievable
  canonical inputs) and `input_snapshot_hash` (content verification). The
  database requires the run to belong to `model_version_id`.
- **Calibration lineage**: `calibration_model_id` → `calibration_models`, plus
  the denormalized `calibration_version` written into the immutable record.
- **Linkage/diagnostics**: `accumulator_id` (polymorphic UUID, no FK until
  the accumulators table lands), `reason_codes` (JSON; Appendix D), `created_at`.

### `calibration_models` (versioned lifecycle entity — Phase 4)

`id`, unique `version`, `method` (`platt` or `isotonic`), lifecycle `status`,
optional `parent_id`, nullable segment dimensions (`market`, `competition`,
`model_family`), `trained_as_of`, training window, `sample_size`,
`minimum_sample_size`, serializable `parameters`, validation `diagnostics`,
`artefact_hash`, `code_commit`, promotion/retirement and row timestamps.
Database checks enforce the training cutoff and minimum sample contract.

### `calibration_snapshots` (immutable monitoring archive — Phase 4)

`calibration_model_id`, evaluation cutoff/window, `sample_size`, Brier score,
log loss, ECE, calibration intercept/slope, optional Brier Skill Score,
reliability-curve bins and `created_at`. Database triggers forbid UPDATE,
DELETE and TRUNCATE.

### `experiments` (configuration frozen; completed rows immutable — Phase 5)

`id`, unique (`name`, `version`), `kind`, lifecycle `status`, model,
calibration, Value Gate and conservative-policy versions, `code_commit`,
`data_snapshot_ref`, comparison `baseline`, deterministic `random_seed`, full
JSON `configuration`, start/finish timestamps, training/test windows,
`sample_size`, rejected leakage count, JSON `metrics`, `result_hash` and row
timestamps. Configuration cannot change after insertion. A successful result
requires its completion time, sample size, metrics and content hash; after
completion no field may change. DELETE and TRUNCATE are forbidden.

### `selection_candidates` (immutable Value Gate archive — Phase 5)

`prediction_id` → `predictions`, `evaluated_at`, `policy_version`, `passed`,
calculated `edge`, `expected_value`, ordered JSON `reason_codes`, complete JSON
`gate_inputs` and `created_at`. Database triggers forbid UPDATE, DELETE and
TRUNCATE so later policy changes cannot rewrite why a historical candidate
passed or failed.

### `reliability_snapshots` (immutable league-market matrix — Phase 6)

`competition_id` → `competitions`, `competition_class`, `market_family`,
evaluation cutoff and evidence window, `policy_version`, raw/effective sample
sizes, shrinkage weight, LRS, MRS, segment posterior, posterior standard
deviation, conservative lower bound, dynamic status, grade, JSON components
and diagnostics, future-row exclusion count, input snapshot reference/hash,
`code_commit` and `created_at`. A unique segment/cutoff/policy key prevents
ambiguous duplicates. Database triggers forbid UPDATE, DELETE and TRUNCATE.

`predictions.reliability_snapshot_id` optionally links a new immutable decision
to the exact matrix snapshot used. Existing archived predictions remain null
rather than being rewritten with hindsight.

### `audit_events` (immutable, append-only)

`id`, `event_type` (enum `audit_event_type`: model_promoted, model_retired,
policy_change, config_change, override, data_revision, job_failure,
governance, other), `actor` (enum `audit_actor`: system, human), `actor_ref`,
`action`, `summary`, `entity_type` + `entity_id` (polymorphic target, no FK,
mirroring `source_mappings.canonical_id`), `payload` (JSON, e.g. before/after),
`occurred_at` (when the action happened — may precede the row-write
`created_at`).

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
