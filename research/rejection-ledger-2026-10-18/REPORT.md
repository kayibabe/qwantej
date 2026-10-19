# Transparent rejection ledger: combination analysis

Snapshot: 18 October 2026. Status: historical simulation; no validated live selection policy.

## Finding

The strongest training-period candidate with at least 40 selections was away win, Q-score >=65, decimal odds >=1.80 and <3.00, with no minimum edge requirement. Quotes were no more than 3 hours old at prediction time. The later-period return was positive, but the sample is small, uncertainty spans losses, and nearby thresholds do not perform consistently. There is no demonstrated dependable sweet spot yet.

## The six requested fields

| Field | How it was used |
|---|---|
| Selection | Separate market/selection types, plus an all-market strategy |
| Q-score | Thresholds and score bands; it is not a calibrated win probability |
| Odds | Entry decimal odds ranges and actual winning payouts |
| Edge | Multiple thresholds; ledger market edge and stored model edge analysed separately |
| Match result | Final score determines won, lost or void |
| Rejection check | Lost = passed rejection; won = failed rejection; void is neutral |

Match result and rejection check evaluate the combinations. They are not pre-match filters and are not two independent predictive signals.

## Data and simulation method

- Read-only database transaction; no application policy, stored prediction, ticket or database record was changed. Research scripts and local artifacts were added only.
- Source export: 46,400 prediction rows, including repeated runs. First-capture comparator: 14,256 distinct match/market pairs; 32,144 later repeats removed. Missing first-capture odds were not replaced using later prices.
- Current-rule ledger reconstruction: 17,008 rows before duplicate and eligibility filtering. After filtering: 9,408 priced resolved/void market selections across 672 distinct fixtures. This is more than the 500-row UI cap and spans multiple dates.
- Ledger reconstruction uses the latest completed model run for each target date, as the endpoint does, then keeps the earliest occurrence of each match/market in that reconstructed set. It is NOT an immutable record of what was rejected on the original decision day.
- First-capture comparator uses all predictions, independent of current ledger membership: 9,646 priced resolved/void selections across 689 fixtures.
- Eligible predictions and quotes have pre-kickoff timestamps, quote time no later than decision time, no replay as_of marker, no flagged fallback odds, decimal odds >1, and known results. Timestamp checks do not independently certify the original provider data or exclude every possible upstream model-training leak.
- Dates: 14 September through 18 October 2026, CAT. Earlier period: before 11 October; later period: 11–18 October. This split was determined from available dates before ranking strategies. 18 October remains a partial day; unresolved games are excluded.
- Every strategy takes at most one selection per fixture, choosing highest Q, then earlier capture, then prediction ID. Single-market strategies naturally have one selection per fixture. Separate strategy tables can overlap and must not be added together.
- Flat one-unit singles. Win profit = odds minus one; loss = minus one; void = zero. Hit rate = wins/(wins+losses). ROI = net profit/all staked units, including refunded void stakes in the denominator. No compounding, accumulators, tax, bookmaker limits or execution guarantees.
- Grid per cohort: 15 selection scopes (14 priced markets plus all-market), 9 Q thresholds, 7 odds ranges, 8 edge floors including no filter, and 3 quote-age caps = 22,680 parameter settings. Many settings select identical rows, so this is not 22,680 independent tests. DNB markets had no eligible priced first-capture rows.
- Training eligibility: at least 40 selections; 3,654 ledger settings qualified. Ranking used earlier-period ROI only. Later-period results and sensitivity checks remain exploratory, not a prospective experiment.

## Main results

| Combination / period | Selections | Wins / rejection failed | Losses / rejection passed | Void | Hit rate | ROI | Profit (units) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Highest Q per match; all dates | 672 | 416 | 251 | 5 | 62.37% | -7.91% | -53.16 |
| Over 1.5; all dates | 672 | 520 | 147 | 5 | 77.96% | -2.57% | -17.28 |
| Under 4.5; all dates | 672 | 539 | 128 | 5 | 80.81% | -4.15% | -27.86 |
| Away win, Q>=65, 1.80<=odds<3; earlier period | 42 | 25 | 16 | 1 | 60.98% | +44.24% | +18.58 |
| Same combination; later period | 36 | 15 | 21 | 0 | 41.67% | +7.00% | +2.52 |

The later-period candidate had 21 passed rejections and 15 failed rejections: rejection accuracy was 58.33%, yet selecting those matches earned 2.52 units. Rejecting all of them would therefore have sacrificed 2.52 simulated units. This illustrates why rejection accuracy alone is insufficient: the 15 winning prices outweighed 21 losses.

Conversely, selecting the highest-Q ledger option per match lost 53.16 units. Rejecting that particular strategy avoided that simulated loss, even though 416 individual winners were rejected.

## Confidence and fragility

- Candidate later period: 36 fixtures on only 7 active dates; +7.00% ROI. A 5,000-resample day-cluster bootstrap gives an approximate 95% ROI interval of -22.84% to +38.81%. This interval is descriptive, unstable with so few days, and not corrected for searching many strategies.
- Maximum observed later-period drawdown: 5 units; longest losing sequence: 5. Neither is a future worst-case bound.
- Reducing winnings by 5% lowers later-period ROI to +3.73%; this is a payout sensitivity scenario, not an estimate of actual costs.
- First-capture comparator independently recovers the same training-selected filter: earlier 40 selections, +43.48%; later 39 selections, +18.41%. Its later ROI interval is -13.45% to +65.80%. The cohorts overlap heavily, so this is a provenance sensitivity check, not independent confirmation.
- The apparent winner was selected from thousands of historical settings. Its training ROI is subject to selection bias. Even the later sample is too short to establish durable profitability.

## Nearby Q and odds settings

All rows below use away win, no edge floor, quote age <=3 hours. These are sensitivity diagnostics, not additional validated strategies.

| Q minimum | Odds range | Earlier N | Earlier ROI | Later N | Later ROI |
|---|---|---:|---:|---:|---:|
| Q>=60 | 1.5<=odds<3 | 81 | +22.90% | 67 | -17.00% |
| Q>=60 | 1.8<=odds<3 | 69 | +27.80% | 57 | -19.98% |
| Q>=60 | 2<=odds<3 | 59 | +26.85% | 52 | -15.88% |
| Q>=60 | 1.8<=odds<4 | 104 | +15.69% | 98 | -19.00% |
| Q>=65 | 1.5<=odds<3 | 49 | +40.51% | 37 | +4.11% |
| Q>=65 | 1.8<=odds<3 | 42 | +44.24% | 36 | +7.00% |
| Q>=65 | 2<=odds<3 | 36 | +47.17% | 33 | +16.73% |
| Q>=65 | 1.8<=odds<4 | 63 | +29.21% | 66 | -0.55% |
| Q>=70 | 1.5<=odds<3 | 27 | +41.52% | 26 | +18.50% |
| Q>=70 | 1.8<=odds<3 | 24 | +44.75% | 25 | +23.24% |
| Q>=70 | 2<=odds<3 | 22 | +49.09% | 22 | +40.05% |
| Q>=70 | 1.8<=odds<4 | 41 | +18.71% | 47 | +8.43% |

Lowering Q from 65 to 60 with the same 1.80–below 3.00 odds range changes later ROI from +7.00% to -19.98%. Widening the upper odds bound to below 4.00 at Q>=65 changes later ROI to -0.55%. Tightening to Q>=70 appears better, but has only 24 earlier and 25 later selections; it did not meet the 40-selection training minimum.

## Edge findings

The running ledger uses market-priced legs: its displayed edge is derived from a fair-market probability minus 1/odds. The original prediction model edge is a different quantity. In all 4,998 overlapping eligible first-capture rows with both edges available, these differed. Treating the displayed edge as the original model edge would invalidate the comparison.

For the candidate Q>=65 / away-win / odds 1.80–below 3.00 combination: no edge floor and a -5 percentage-point floor select the same 42 earlier / 36 later cases. Requiring nonnegative ledger edge leaves zero earlier cases and only two later cases (one win, one loss). Requiring +2 percentage points leaves none. There is insufficient evidence to recommend a positive-edge cutoff for this combination.

Ledger edge is recalculated using stored bookmaker books whose query does not impose an original decision-time cutoff. It cannot be treated as a verified historical pre-match signal. The separate first-capture analysis tests persisted model edge instead. The leading candidate does not rely on either edge filter.

## Selection types: all eligible ledger fixtures

| Combination / period | Selections | Wins / rejection failed | Losses / rejection passed | Void | Hit rate | ROI | Profit (units) |
|---|---:|---:|---:|---:|---:|---:|---:|
| away_win | 672 | 213 | 454 | 5 | 31.93% | -8.83% | -59.32 |
| btts_no | 672 | 293 | 374 | 5 | 43.93% | -4.32% | -29.04 |
| btts_yes | 672 | 374 | 293 | 5 | 56.07% | -3.95% | -26.54 |
| double_chance_1x | 672 | 454 | 213 | 5 | 68.07% | -4.88% | -32.81 |
| double_chance_x2 | 672 | 361 | 306 | 5 | 54.12% | -10.41% | -69.93 |
| draw | 672 | 148 | 519 | 5 | 22.19% | -13.07% | -87.80 |
| home_win | 672 | 306 | 361 | 5 | 45.88% | -0.09% | -0.61 |
| over_1.5 | 672 | 520 | 147 | 5 | 77.96% | -2.57% | -17.28 |
| over_2.5 | 672 | 361 | 306 | 5 | 54.12% | -5.26% | -35.36 |
| over_3.5 | 672 | 225 | 442 | 5 | 33.73% | -4.34% | -29.17 |
| over_4.5 | 672 | 128 | 539 | 5 | 19.19% | +0.04% | +0.27 |
| under_2.5 | 672 | 306 | 361 | 5 | 45.88% | -2.16% | -14.50 |
| under_3.5 | 672 | 442 | 225 | 5 | 66.27% | -2.74% | -18.42 |
| under_4.5 | 672 | 539 | 128 | 5 | 80.81% | -4.15% | -27.86 |

High hit rate did not imply profit: under 4.5 won 80.81% of non-void selections but returned -4.15% ROI; over 1.5 won 77.96% but returned -2.57%. Evaluate payouts and losses together.

## Q-score bands

| Combination / period | Selections | Wins / rejection failed | Losses / rejection passed | Void | Hit rate | ROI | Profit (units) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Q below 40 | 1 | 1 | 0 | 0 | 100.00% | +75.00% | +0.75 |
| Q [40, 50) | 353 | 118 | 233 | 2 | 33.62% | +1.25% | +4.41 |
| Q [50, 60) | 668 | 332 | 331 | 5 | 50.08% | -2.23% | -14.89 |
| Q [60, 70) | 652 | 424 | 223 | 5 | 65.53% | -3.54% | -23.11 |
| Q [70, 80) | 580 | 338 | 237 | 5 | 58.78% | -8.60% | -49.89 |
| Q [80, 90) | 236 | 130 | 105 | 1 | 55.32% | -4.05% | -9.55 |
| Q [90, 100) | 21 | 11 | 10 | 0 | 52.38% | -19.52% | -4.10 |

Each band chooses its highest-Q qualifying selection per match. These are separate strategies, not disjoint fixture samples. Q-score alone does not show a monotonic profit relationship.

## Odds bands

| Combination / period | Selections | Wins / rejection failed | Losses / rejection passed | Void | Hit rate | ROI | Profit (units) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1-1.2 | 620 | 535 | 81 | 4 | 86.85% | -2.05% | -12.73 |
| 1.2-1.5 | 672 | 477 | 190 | 5 | 71.51% | -6.26% | -42.10 |
| 1.5-1.8 | 627 | 365 | 258 | 4 | 58.59% | -3.84% | -24.10 |
| 1.8-2 | 467 | 235 | 228 | 4 | 50.76% | -4.95% | -23.11 |
| 2-3 | 666 | 290 | 371 | 5 | 43.87% | +0.94% | +6.29 |
| 3-5 | 670 | 158 | 507 | 5 | 23.76% | -13.50% | -90.44 |
| 5-100 | 552 | 84 | 465 | 3 | 15.30% | -1.83% | -10.12 |

## Ledger edge bands

| Combination / period | Selections | Wins / rejection failed | Losses / rejection passed | Void | Hit rate | ROI | Profit (units) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Edge lower bound -10 (see JSON for bands) | 130 | 101 | 29 | 0 | 77.69% | -3.36% | -4.37 |
| Edge lower bound -0.05 (see JSON for bands) | 672 | 417 | 250 | 5 | 62.52% | -7.28% | -48.92 |
| Edge lower bound 0 (see JSON for bands) | 552 | 120 | 428 | 4 | 21.90% | -6.37% | -35.17 |
| Edge lower bound 0.05 (see JSON for bands) | 3 | 2 | 1 | 0 | 66.67% | +102.67% | +3.08 |

Edge bands are [-10,-0.05), [-0.05,0), [0,0.05), [0.05,0.10), [0.10,0.20), [0.20,10). Values are probability differences; 0.05 means five percentage points. Very small positive cohorts are not evidence of an edge.

## Data limitations found

1. The UI cap is 500, which is not a full sample count.
2. Current rejection checks use current rule evaluations, including stale-odds checks against the current clock. Replaying an old date does not recover immutable historical rejection reasons.
3. Direct reconstruction encountered a division-by-zero in market pricing when odds were missing but fair probability existed. The read-only export bypassed repricing only for zero-odds rows so they could retain missing-odds rejection reasons; they are excluded from profit simulations. The application bug itself was not changed.
4. Model versions and leagues are mixed. Candidate breakdowns are included in analysis.json, but league samples are too small for reliable league-specific filters.
5. Same-day correlation is partly reflected by day-cluster resampling; dependence across days and model regimes remains. Actual bookmaker acceptance and achievable prices were not tested.

## Recommended next steps

1. Keep the away-win / Q>=65 / odds [1.80,3.00) combination as a frozen paper-testing hypothesis. Do not relax existing publication or quality gates on this evidence.
2. Log each qualifying future fixture before kickoff, with immutable selection, Q, model edge, market edge, quoted odds, quote timestamp, decision timestamp, model version and rule version. Log excluded opportunities too.
3. Collect a fresh period across several months and many independent matchdays. Set review dates and sample requirements before observing results; a few hundred observations is a starting point for planning, not an automatic proof threshold.
4. Require positive future net ROI after realistic costs, uncertainty narrow enough to rule out an unacceptable loss, and reasonably stable nearby thresholds before calling any combination dependable.
5. Report rejection precision alongside avoided loss and missed profit. A rejection can be correct more often than not while still discarding a profitable strategy.
6. Add clear labels for model edge versus market edge, immutable rejection snapshots, full export/pagination, sample size and outcome coverage to the ledger. These are recommendations, not implemented UI changes.

## Files and reproducibility

- `current-ledger/sweep.csv`: all grid settings meeting the earlier-period minimum, with both periods.
- `current-ledger/eligible-selections.csv`: row-level six-field evidence, final scores, returns and rejection checks.
- `comparison.csv`: headline strategies with explicit passed/failed rejection counts and financial effect.
- `current-ledger/analysis.json`: full ledger statistics, candidate picks, sensitivity and league/version breakdowns.
- `analysis.json` and `sweep.csv`: persisted first-capture model-edge comparator.
- `predictions.json` and `ledger.json`: local input snapshots.
- Scripts: `backend/scripts/rejection_ledger_export.py`, `analyze_rejection_ledger.py`, `report_rejection_ledger.py`. Export requires application database access; analysis/report run locally with NumPy.
- Checks: winner returns independently recomputed from final scores; candidate criteria and unique-match counts checked; wins+losses+voids and ROI arithmetic verified. No browser or UI change was made.

## Statistical reference

Searching many historical parameter settings can produce apparently strong winners by chance: [Bailey et al., The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf). The bootstrap intervals here do not remove this selection effect.
