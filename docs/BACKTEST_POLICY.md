# Backtest Policy

Canonical reference: [`QWANTEJ_FRAMEWORK.md`](QWANTEJ_FRAMEWORK.md) §41 and
§13. This is a **governance process**, not merely a historical simulation —
treat every rule below as non-negotiable, matching `DEVELOPMENT.md`'s
"no data leakage in backtesting" rule.

## Non-negotiable rules

- Use time-ordered train/validation/test or rolling walk-forward windows.
  **Never** randomly shuffle football time series for final evaluation.
- Features must be reconstructed as they were knowable at the prediction
  timestamp — not recomputed with the benefit of hindsight.
- Calibration must be trained only on observations available before each
  evaluation period.
- League/market reliability scores used in a historical decision must be
  the scores available *then*, not today's revised scores.
- Use the odds actually observable at the simulated decision time; closing
  odds are evaluation data (for CLV), never early-decision inputs.
- Account for voids, postponed matches, missing prices and ticket
  invalidation rules.
- Freeze threshold sets before evaluating a hold-out period, to reduce data
  snooping.
- Compare against de-vigged market probabilities and simple statistical
  baselines — not only raw win rate.
- Report confidence intervals or bootstrap uncertainty for ROI, calibration
  and product performance where feasible.
- Preserve every backtest configuration, code version and result in the
  experiment registry (`experiments` table).

The Phase 5 implementation is specified in
[`modelling/VALUE_BACKTESTING.md`](modelling/VALUE_BACKTESTING.md). It enforces
these cutoffs in `walk_forward_backtest` and archives completed reports through
`backend.services.experiments`.

## Point-in-time integrity (framework §13, restated for backtests)

A backtested "prediction" for a historical fixture must only use data whose
source timestamp is `<= decision_as_of` for that fixture. If a feature,
reliability score, or calibrator used in a backtest could not have existed
at that point in real time, the backtest is invalid — this is the single
most common way a backtest silently overstates performance.

## Required leakage test (ties to `MODEL_GOVERNANCE.md`'s Definition of Done)

Every new feature, model, or calibrator ships with an explicit leakage test
that asserts future data cannot enter the computation for a given
`decision_as_of`. A green test suite without this test is not sufficient
sign-off for a modelling change.

## What a backtest result must report

At minimum: sample size and date range, walk-forward window configuration,
Brier score / Brier Skill Score / log loss, calibration slope/intercept,
ROI/yield vs. break-even hit rate, CLV, maximum drawdown, and the
comparison baseline used (market-implied probability and/or a simple
statistical baseline). "It should be more accurate" is never an acceptable
substitute for these numbers (see `DEVELOPMENT.md` §4).
