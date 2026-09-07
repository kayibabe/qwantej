# Value and Walk-Forward Backtesting (Phase 5)

Canonical reference: [`QWANTEJ_FRAMEWORK.md`](../QWANTEJ_FRAMEWORK.md) §20–22,
§41 and Phase 5. This document defines the research-only value decision and
historical evaluation contract implemented in `src/qwantej/value/` and
`src/qwantej/performance/backtest.py`.

## Value calculation

Bookmaker prices enter the decision layer as timestamped executable decimal
odds and de-vigged fair-market probabilities. Raw implied probabilities are
never treated as fair prices. For a selection:

```text
Edge_pp = P_cons - P_market_fair
EV      = P_cons * executable_decimal_odds - 1
CLV     = executable_decimal_odds / closing_decimal_odds - 1
```

Closing odds are evaluation data only. They cannot enter a candidate decision.
All inputs must be finite; probabilities are constrained to `[0, 1]` and
decimal odds must exceed 1.

## Explicit Value Gate

`ValueGatePolicy` is immutable and versioned. A candidate passes only when all
configured calibration, uncertainty, price freshness, edge, EV, data quality,
reliability, stability, anomaly and risk checks pass. The gate returns every
failure as a stable machine-readable code. The exact inputs, policy version,
calculated edge/EV and reason codes belong in the append-only
`selection_candidates` table linked to the immutable prediction.

The reliability exception exists only for research segments without enough
history. It does not bypass any other gate and must never be interpreted as a
production approval.

## Walk-forward evaluation

`walk_forward_backtest` sorts observations by `decision_as_of`, freezes one
model version and uses expanding training windows followed by ordered test
windows. At each fold, the calibrator sees only outcomes whose observation
timestamp is at or before that fold's training cutoff. Features and executable
quotes timestamped after the simulated decision are rejected and counted.

Historical rows without usable market prices may train calibration once their
outcomes are known, but they never enter market comparison or value selection.
Rows without a settled binary outcome, including voided or invalidated bets,
are excluded from calibration, ROI and hit-rate denominators and counted in the
report rather than scored as losses.
Closing prices are optional evaluation evidence and missing coverage is
reported explicitly.

Every report includes the evaluated date range and sample, fold sizes, rejected
leakage and model-version rows, raw/calibrated/market calibration metrics, Brier
Skill Score against the market, selected ROI with a seeded bootstrap interval,
hit and break-even rates, average odds, CLV coverage and maximum drawdown.

## Reproducible experiment registry

`backend.services.experiments` inserts and flushes the complete configuration
before evaluation, then finalizes that row once with JSON-safe metrics and a
SHA-256 content hash. The registry stores the code commit, input snapshot,
model/calibrator/policy versions, seed, baseline and train/test windows.
PostgreSQL triggers freeze configuration immediately, freeze the entire row
after completion, and forbid delete/truncate. Successful rows require a finish
timestamp, sample size, metrics and result hash.

This phase supplies evaluation machinery and audit storage. It does not claim
profitability or promote a model. Promotion still requires an adequately sized
real point-in-time dataset, market-baseline results, stability review and the
governance checklist.
