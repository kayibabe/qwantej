# Joint score distribution: first detached replay

**Run date:** 2026-10-24
**Purpose:** Diagnose the raw Poisson-Dixon-Coles score component before
considering any new market qualification behavior.
**Decision:** Research only. No model, market, or qualification policy is
promoted by this report.

## What was evaluated

The shared distribution code builds one regulation-time home/away score
matrix per fixture, then adapts that matrix to the existing score-derived
markets. The first replay scored raw `Prediction.poisson_prob`. A follow-up
also scores the stored historical-backfill `Prediction.model_probability`
field, without changing the market or qualification policy.

Two detached datasets were read from the local Qwantej database:

| Capture source | Unique matches | Unique market forecasts | Date range | Duplicate snapshots removed |
| --- | ---: | ---: | --- | ---: |
| `model_run`, model version 0.3.0 | 1,111 | 17,254 | 2026-09-20 to 2026-10-24 | 32,550 |
| `historical_backfill`, model version 0.3.0 | 16,471 | 214,123 | 2025-07-17 to 2026-10-19 | 0 |

The model-run replay retained the latest pre-kickoff forecast for each
match/market pair. Both datasets were filtered to finished, non-excluded
matches with known scores and a forecast timestamp before kickoff. Evaluation
reports Brier score and log loss. A smoothed market-wide outcome-rate baseline
and a competition-specific outcome-rate baseline each use only earlier UTC
kickoff dates, with at least 30 earlier outcomes before scoring a baseline
forecast. The report also includes fixed-width probability reliability
deciles, expected calibration error, and competition-level segments to expose
miscalibration and heterogeneity. A segment comparison is summarized only
when it contains at least 30 scored forecasts and 30 paired baseline forecasts.

## Preliminary result

All 16 market selections present in the recent model-run replay had negative Brier skill score against
the global expanding prior-outcome baseline in the recent model-run dataset.
The same pooled markets were also negative against the competition-specific
expanding baseline except Draw, which was slightly positive. Against that
competition-specific baseline, Under 2.5 / Over 2.5 and Under 3.5 / Over 3.5
were close to the baseline but still negative.

| Market | Brier skill vs global baseline | Brier skill vs competition baseline | 10-bin expected calibration error |
| --- | ---: | ---: | ---: |
| Home win | -0.0890 | -0.1011 | 0.1494 |
| Draw | -0.0205 | +0.0256 | 0.0516 |
| Away win | -0.0819 | -0.1503 | 0.1257 |
| BTTS yes / no | -0.1516 | -0.1880 | 0.1609 |
| Double chance 1X | -0.0819 | -0.1503 | 0.1257 |
| Double chance X2 | -0.0890 | -0.1011 | 0.1494 |
| DNB (each side) | -0.1139 | -0.0444 | 0.1783 |
| Over 1.5 | -0.2398 | -0.2458 | 0.1538 |
| Over / Under 2.5 | -0.1316 | -0.0150 | 0.1645 |
| Over / Under 3.5 | -0.1240 | -0.0407 | 0.1502 |
| Over / Under 4.5 | -0.1227 | -0.0981 | 0.1119 |

The replay has no eligible predictions for two of the 18 scored catalog
selections (`under_0.5` and `under_1.5`), so they are not in the comparison.
For example, the raw home-win forecast had Brier score 0.2713, observed home
win rate 0.4572, and mean forecast probability 0.3683. The raw away-win
forecast mean probability was 0.3797 against an observed rate of 0.3078. This
indicates a home/away probability mismatch in this replay; it does not identify
the cause or establish that the complete model has the same behavior.
The fixed-decile calibration error ranges from 0.0516 for Draw to 0.1783 for
DNB. Over 3.5 has nearly equal overall mean probability and outcome rate, but
still has 0.1502 decile calibration error; the aggregate rates therefore hide
substantial probability-bin mismatch.

The longer historical-backfill replay also had negative Brier skill for its
scored markets against both expanding baselines. Its model is a global-fit
backfill and is not identical to the current production model-run path, so it
is supporting diagnostic evidence rather than a direct production comparison.

## Competition variation

The historical-backfill report contains 40 competition segments; in the
markets inspected here, 38 met the minimum paired-sample rule. The segment
results are mixed. For example, home-win Brier skill was
+0.065 in Portugal's Primeira Liga (368 forecasts, 336 paired baseline
forecasts), but -0.218 in the League Cup (137 forecasts, 106 paired baseline
forecasts). Away-win skill was +0.160 in the Saudi Pro League (375 / 345) and
-0.258 in the 2. Bundesliga (368 / 335). The pooled recent model-run dataset
has 37 competitions, but none has 30 forecasts with 30 paired baseline rows;
its competition-specific pooled comparison is therefore more informative
than individual recent segments.

The segment variation argues against treating one pooled score as evidence
that the component behaves uniformly. However, historical-backfill predictions
come from a global-fit replay, not the current per-competition production
path, and the segment estimates have no uncertainty intervals. They identify
where further research may be useful; they do not justify league-specific
promotion.

## Retrospective chronological calibration check

To test whether simple recalibration could explain the raw component's weak
scores, a per-market logistic intercept and positive slope were fitted to the
historical-backfill rows through 2026-06-30. The later period, 2026-07-01 to
2026-10-19, was scored after fitting. Each market had 12,658 training rows and
3,813 holdout rows; 3,807 holdout rows per market had both global and
competition-specific baselines available. Each baseline used only earlier
kickoff dates, with at least 30 earlier outcomes.

| Selection | Raw Brier skill vs global baseline | Calibrated skill vs global | Calibrated skill vs competition baseline |
| --- | ---: | ---: | ---: |
| Home win | -0.1055 | +0.0190 | +0.0202 |
| Draw | -0.0528 | +0.0026 | -0.0012 |
| Away win | -0.1312 | +0.0225 | +0.0220 |
| BTTS yes / no | -0.1859 | +0.0031 | -0.0047 |
| Over / Under 1.5 | -0.2100 | +0.0064 | -0.0037 |
| Over / Under 2.5 | -0.1524 | +0.0113 | -0.0069 |
| Over / Under 3.5 | -0.1337 | +0.0126 | -0.0100 |
| Over / Under 4.5 | -0.2143 | +0.0077 | -0.0147 |
| Under 0.5 | -0.2634 | +0.0032 | +0.0038 |

All available markets improved versus the raw probabilities after fitting, but
the calibrated Brier skill versus the global baseline was small, from +0.0026
to +0.0225. Most calibrated totals and BTTS selections remained slightly
behind the competition-specific baseline. The fitted probability slopes were
about 0.08–0.24, far below 1.0, which means the raw probabilities were strongly
compressed toward each market's average outcome rate. This points to severe
overconfidence or weak probability ranking; the check does not distinguish
between them by itself.

ROC AUC helps separate these effects. Because the fitted slope is constrained
positive, the recalibration preserves probability ranking (the observed AUC is
unchanged up to floating-point ties). Raw AUC was moderate for 1X2—0.589 for
home wins and 0.598 for away wins—against competition-prior AUCs of 0.507 and
0.518. For goals and BTTS, raw AUC was 0.537–0.577 and generally below the
competition-prior comparator; Over 4.5 was 0.575 versus 0.612. This suggests
some match-result ranking signal, while the goals-market rankings are weaker
than the already simple competition-and-time baseline in this holdout.

| Market | Raw AUC | Competition-prior AUC |
| --- | ---: | ---: |
| Home win | 0.589 | 0.507 |
| Draw | 0.532 | 0.534 |
| Away win | 0.598 | 0.518 |
| BTTS yes / no | 0.537 | 0.549 |
| Over / Under 1.5 | 0.552 | 0.571 |
| Over / Under 2.5 | 0.566 | 0.579 |
| Over / Under 3.5 | 0.577 | 0.586 |
| Over / Under 4.5 | 0.575 | 0.612 |
| Under 0.5 | 0.553 | 0.561 |

This split is chronological and the calibrator did not see holdout outcomes
during fitting. It is still retrospective rather than an untouched
confirmation holdout because full-period aggregate performance had already
been examined. The results use the global-fit historical-backfill source, not
the live ensemble or a per-competition production model. Calibration reduced
the measured error but did not establish a promotion candidate; no fitted
parameters were activated or written to Qwantej.

## Rate-level diagnostic coverage

The evaluator can reconstruct truncated-matrix expected home and away goals
from the saved Poisson-Dixon-Coles parameters, then compare those means with
finished scores overall and by competition. The current stored model-run and
historical-backfill rows contain no `joint_score_distributions` parameter
snapshots (0 of 1,111 and 0 of 16,471 matches respectively), so the rate-level
diagnostic is currently unavailable. Newly produced forecasts will carry
these parameters in their feature snapshots; this report did not trigger a
new operational model run or write forecasts to the database.

## Limits and next research

- The chronological split is retrospective: full-period aggregate performance
  was examined before the split was frozen. The holdout is chronological, but
  it is not an untouched confirmatory sample.
- Multiple fixtures can share a competition and date; the baseline correctly
  excludes same-day outcomes, but this does not address every source of
  dependence or selection bias.
- The competition baseline is an outcome-rate comparator, not a complete
  market-specific model or an odds-based benchmark.
- Neither score-component nor historical-backfill ensemble results establish
  current live-model performance, qualification eligibility, saved tickets,
  placed bets, settlement records, or profitability.
- The backfill and model-run sources have different capture and fitting
  processes and should not be pooled.

## Historical-backfill ensemble on the paired holdout

The follow-up replays stored `Prediction.model_probability` using the same
training cutoff (through 2026-06-30) and holdout (from 2026-07-01) as the
Poisson-component calibration research. For a fair field-to-field comparison,
each market below uses the 3,807 holdout forecasts for which the selected
historical-backfill probability, raw `Prediction.poisson_prob`, and expanding
baselines are all available. The expanding global and competition baselines
are calculated from earlier outcome dates only. The probability field is taken
from the saved historical-backfill record; this does not represent a fresh
live-ensemble run.

| Market | Backfill ensemble Brier | Poisson Brier | Competition baseline Brier | Ensemble AUC | Poisson AUC |
| --- | ---: | ---: | ---: | ---: | ---: |
| Away win | 0.2228 | 0.2398 | 0.2118 | 0.6040 | 0.5979 |
| BTTS no / yes | 0.2723 | 0.2928 | 0.2449 | 0.5403 | 0.5369 |
| Draw | 0.1971 | 0.2021 | 0.1913 | 0.5330 | 0.5318 |
| Home win | 0.2557 | 0.2719 | 0.2462 | 0.5945 | 0.5886 |
| Over / Under 1.5 | 0.1924 | 0.2191 | 0.1792 | 0.5555 | 0.5518 |
| Over / Under 2.5 | 0.2566 | 0.2874 | 0.2449 | 0.5705 | 0.5663 |
| Over / Under 3.5 | 0.2248 | 0.2487 | 0.2144 | 0.5812 | 0.5766 |
| Over / Under 4.5 | 0.1483 | 0.1659 | 0.1336 | 0.5839 | 0.5751 |
| Under 0.5 | 0.0717 | 0.0816 | 0.0646 | 0.5547 | 0.5526 |

For all listed markets, the ensemble field has lower Brier score and slightly
higher AUC than its paired Poisson component. Yet its Brier score remains
worse than both the expanding global and competition outcome-rate baselines
on this matched sample (competition values are shown above; the global values
are also worse than the ensemble in every row). The ensemble therefore
improves on this Poisson component in the replay, but does not demonstrate
incremental forecast value over the simple historical baselines. The repeated
Over/Under rows represent complementary outcomes from the same match forecasts,
not independent samples.

Keep this as a research result. Next, gather rate-level diagnostics from
naturally produced forecasts and obtain an untouched forward holdout; do not
change the current qualification gates based on these retrospective results.
