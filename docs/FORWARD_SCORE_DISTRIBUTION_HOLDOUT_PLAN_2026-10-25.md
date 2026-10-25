# Forward score-distribution holdout plan

**Registered:** 2026-10-25 (Africa/Blantyre)
**Purpose:** Evaluate naturally captured, pre-kickoff forecasts prospectively,
including the stored joint score-rate parameters.
**Decision:** Holdout not started. Current capture coverage does not pass the
readiness gate below. This plan authorizes no model, qualification, betting, or
publication change.

## Readiness audit

The read-only capture audit checked saved `model_run` forecasts for model
version `0.3.0` at 2026-10-25 04:27 UTC. It does not use match outcomes. It
retains the latest strictly pre-kickoff forecast per fixture and market.

| CAT kickoff date | Fixtures with forecasts | Fixture-market forecasts | Complete saved score-rate snapshots | Coverage |
| --- | ---: | ---: | ---: | ---: |
| 2026-10-25 | 106 | 1,908 | 1,332 across 74 fixtures | 69.8% |
| 2026-10-26 | 19 | 342 | 0 | 0% |

Across all saved model-run dates, the audit found 1,275 fixtures and 20,650
latest fixture-market forecasts, with 1,332 complete score-rate snapshots
(6.45% of forecast rows). The 74 snapshot-bearing fixtures in the 2026-10-25
CAT cohort were still scheduled at audit time. Separately, the completed-match
rate diagnostic found no usable saved snapshots among 1,167 scored fixtures.
All 1,908 latest fixture-market rows in the 2026-10-25 CAT cohort also lacked
the new scorer build ID; the build-ID field is available to future captures,
but existing rows remain immutable and cannot be retroactively tagged.

Forecast code in the current capture path writes the rate parameters, but the
persisted cohort is incomplete. Therefore the current rows cannot be treated as
a continuous, version-frozen prospective sample. Missing snapshots are a
capture-integrity failure; they must remain visible in the denominator rather
than being silently dropped.

## Start gate

Begin the holdout only after all of the following are recorded:

1. A stable model version and immutable scoring-code/build identifier stored
   with each forecast. New captures write a content-addressed scorer ID into
   `feature_snapshot.forecast_build_id`; records without it cannot join the
   prospective cohort. Any scoring change starts a separate cohort.
2. Seven consecutive CAT capture days with at least 95% complete, valid
   snapshots among eligible fixture-market forecasts overall and at least 95%
   for every registered market.
3. Every forecast timestamp is strictly before kickoff. The audit selects the
   latest such forecast per fixture and market and reports missing or invalid
   snapshots.
4. The start date, model/build identifiers, market list, snapshot schema, and
   analysis code revision are written down before outcomes are examined.

The holdout begins on the first CAT date after the seven-day gate passes. If
the model version, scoring code, or snapshot schema changes, close that cohort
and start a separately identified one. Do not backfill historical forecasts
into the prospective cohort.

## Frozen analysis

- Observe 180 CAT days from the registered start date. Do not inspect aggregate
  outcome scores during collection, retune the model, or change the market list
  based on interim results.
- Score each registered market on the latest immutable pre-kickoff forecast
  using Brier score and log loss. Report ROC AUC and reliability by decile as
  supporting diagnostics.
- Compare against expanding global and competition outcome-rate baselines
  computed from strictly earlier UTC kickoff dates. Report paired Brier skill
  and fixture-cluster bootstrap 95% intervals.
- For the joint score model, compare saved expected home and away goals with
  observed goals, reporting bias and MAE; also report snapshot coverage and
  missingness by competition and market.
- Require at least 500 scored fixtures for a market before drawing a market
  level conclusion. If the threshold is not reached in 180 days, report the
  sample as insufficient and do not extend the window after seeing results.
- Keep paired/complementary selections (such as Over and Under for the same
  line) identified as dependent outcomes. Do not count them as independent
  evidence.

The first eligible report after collection will remain research-only. Any
calibration fit, qualification proposal, or deployment decision requires a
separate later cohort and review; this holdout cannot also serve as the tuning
sample.

## Audit command

Run the capture audit without reading match outcomes:

```powershell
docker exec -w /app qwantej-backend-1 python -m app.services.score_distribution_evaluation `
  --model-version 0.3.0 --capture-source model_run --snapshot-audit-only
```

Use `--start YYYY-MM-DD --end YYYY-MM-DD` to audit an inclusive CAT kickoff
date range. Save the JSON output with the registered holdout records.
