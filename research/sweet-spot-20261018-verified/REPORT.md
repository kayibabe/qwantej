# Match and market sweet-spot audit

**Finding: no validated sweet spot.** Away win / Q >=65 / odds [1.80,3.00) / quote age <=3h remains a historical paper-test hypothesis. This audit does not discover an independently validated new policy.

Snapshot: 2026-10-18T20:44:42+00:00. Completed CAT days only: ['2026-09-14', '2026-10-17'].
Raw rows: 46,400. Eligible market observations: 8,820; distinct fixtures: 630.

## Candidate

| Group | Earlier N | Earlier ROI | Later N | Later win rate | Later ROI |
|---|---:|---:|---:|---:|---:|
| Frozen historical candidate | 39 | +44.59% | 33 | +51.52% | +32.52% |
| Candidate with explicit decision + stored features | 0 | n/a | 21 | +47.62% | +18.90% |

Later ROI day-cluster descriptive 95% interval: [11.91304347826087, 87.38888888888889]. Later ROI with 5% reduction of winnings: +28.47%. This haircut is a scenario, not measured execution cost.

## What the comparison means

- Earlier = before 2026-10-11; later = 2026-10-11 onwards, excluding today's incomplete day. These historical periods have already been examined in the existing rejection-ledger study. Neither is an untouched holdout. No new ranking or tuning on later results.
- First stored prediction per match/market/selection only; no replacing missing prices with later prices. Prices, decisions and captures must precede kickoff; quote <= decision. The database creation timestamp may represent transaction start and precede the decision timestamp. Replay/fallback odds are excluded. Read-only database transaction; source hash in analysis.json.
- Flat one-unit singles, using recorded entry odds. Wins pay odds minus one, losses minus one, DNB draws refund. Postponed/cancelled games are excluded, not assumed refunded. No accumulators. Counts across markets overlap and must not be added as independent matches.
- Only 2,548/8,820 eligible observations have both explicit decision timestamps and nonempty stored features. Missing provider labels: 0. Timestamp checks do not certify upstream training data, feature completeness, bookmaker execution, or recovered legacy-data integrity.
- Match conditions here are limited to recorded pre-match Q, market, price, quote age, league and model version. Historical injuries, lineups or form cannot be recreated safely from today's values. Q is not a probability.
- Candidate uncertainty resamples whole matchdays, 5,000 draws, fixed seed. Few days, historical search bias and cross-day dependence limit interpretation; it is not a guarantee or a multiple-testing-adjusted interval.

## Markets

| Group | Earlier N | Earlier ROI | Later N | Later win rate | Later ROI |
|---|---:|---:|---:|---:|---:|
| away_win | 330 | -4.15% | 300 | +30.33% | -10.35% |
| btts_no | 330 | -4.39% | 300 | +43.33% | -4.91% |
| btts_yes | 330 | -2.58% | 300 | +56.67% | -3.13% |
| double_chance_1x | 330 | -6.52% | 300 | +69.67% | -0.25% |
| double_chance_x2 | 330 | -8.89% | 300 | +54.67% | -9.19% |
| draw | 330 | -14.45% | 300 | +24.33% | -2.65% |
| home_win | 330 | -3.03% | 300 | +45.33% | +0.94% |
| over_1.5 | 330 | -1.25% | 300 | +77.33% | -3.26% |
| over_2.5 | 330 | -1.84% | 300 | +52.67% | -8.04% |
| over_3.5 | 330 | -9.04% | 300 | +34.67% | -0.50% |
| over_4.5 | 330 | -20.45% | 300 | +20.67% | +7.98% |
| under_2.5 | 330 | -2.79% | 300 | +47.33% | +0.31% |
| under_3.5 | 330 | -0.25% | 300 | +65.33% | -4.42% |
| under_4.5 | 330 | +0.89% | 300 | +79.33% | -6.36% |

## Market and odds bands

Fixed broad bins, descriptive only. Small cells are not recommendations.

| Group | Earlier N | Earlier ROI | Later N | Later win rate | Later ROI |
|---|---:|---:|---:|---:|---:|
| away_win; odds [1, 1.5) | 11 | -1.64% | 10 | +70.00% | -4.10% |
| away_win; odds [1.5, 2) | 28 | +1.93% | 26 | +46.15% | -18.92% |
| away_win; odds [2, 3) | 95 | +21.56% | 87 | +43.68% | +8.72% |
| away_win; odds [3, inf) | 196 | -17.63% | 177 | +19.21% | -18.82% |
| btts_no; odds [1, 1.5) | 0 | n/a | 0 | n/a | n/a |
| btts_no; odds [1.5, 2) | 96 | -5.61% | 84 | +50.00% | -7.65% |
| btts_no; odds [2, 3) | 217 | -8.58% | 206 | +40.29% | -6.79% |
| btts_no; odds [3, inf) | 17 | +56.00% | 10 | +50.00% | +57.00% |
| btts_yes; odds [1, 1.5) | 37 | -31.78% | 32 | +71.88% | +2.00% |
| btts_yes; odds [1.5, 2) | 235 | +2.36% | 236 | +55.93% | -3.81% |
| btts_yes; odds [2, 3) | 58 | -3.98% | 32 | +46.88% | -3.22% |
| btts_yes; odds [3, inf) | 0 | n/a | 0 | n/a | n/a |
| double_chance_1x; odds [1, 1.5) | 212 | -3.00% | 199 | +77.89% | -1.86% |
| double_chance_1x; odds [1.5, 2) | 88 | -17.31% | 73 | +57.53% | -5.68% |
| double_chance_1x; odds [2, 3) | 20 | -10.95% | 19 | +47.37% | +3.11% |
| double_chance_1x; odds [3, inf) | 10 | +22.50% | 9 | +33.33% | +72.22% |
| double_chance_x2; odds [1, 1.5) | 102 | +4.33% | 89 | +74.16% | -3.54% |
| double_chance_x2; odds [1.5, 2) | 117 | -14.63% | 134 | +56.72% | -3.90% |
| double_chance_x2; odds [2, 3) | 77 | +5.00% | 58 | +31.03% | -27.69% |
| double_chance_x2; odds [3, inf) | 34 | -60.29% | 19 | +21.05% | -16.53% |
| draw; odds [1, 1.5) | 0 | n/a | 0 | n/a | n/a |
| draw; odds [1.5, 2) | 0 | n/a | 0 | n/a | n/a |
| draw; odds [2, 3) | 1 | -100.00% | 3 | +33.33% | -1.67% |
| draw; odds [3, inf) | 329 | -14.19% | 297 | +24.24% | -2.66% |
| home_win; odds [1, 1.5) | 45 | +7.09% | 24 | +75.00% | -0.87% |
| home_win; odds [1.5, 2) | 82 | -4.67% | 75 | +64.00% | +10.53% |
| home_win; odds [2, 3) | 121 | +2.89% | 134 | +38.81% | -8.72% |
| home_win; odds [3, inf) | 82 | -15.68% | 67 | +26.87% | +10.18% |
| over_1.5; odds [1, 1.5) | 314 | -1.23% | 293 | +77.82% | -3.05% |
| over_1.5; odds [1.5, 2) | 16 | -1.56% | 7 | +57.14% | -11.71% |
| over_1.5; odds [2, 3) | 0 | n/a | 0 | n/a | n/a |
| over_1.5; odds [3, inf) | 0 | n/a | 0 | n/a | n/a |
| over_2.5; odds [1, 1.5) | 58 | -7.86% | 45 | +73.33% | +1.42% |
| over_2.5; odds [1.5, 2) | 184 | -2.30% | 178 | +52.25% | -9.51% |
| over_2.5; odds [2, 3) | 86 | +1.97% | 76 | +42.11% | -9.01% |
| over_2.5; odds [3, inf) | 2 | +51.50% | 1 | +0.00% | -100.00% |
| over_3.5; odds [1, 1.5) | 2 | -30.00% | 2 | +100.00% | +39.50% |
| over_3.5; odds [1.5, 2) | 29 | -19.28% | 15 | +46.67% | -16.47% |
| over_3.5; odds [2, 3) | 156 | -3.13% | 149 | +36.24% | -9.43% |
| over_3.5; odds [3, inf) | 143 | -13.10% | 134 | +30.60% | +10.61% |
| over_4.5; odds [1, 1.5) | 0 | n/a | 0 | n/a | n/a |
| over_4.5; odds [1.5, 2) | 2 | -100.00% | 2 | +100.00% | +96.50% |
| over_4.5; odds [2, 3) | 17 | -24.71% | 8 | +50.00% | +29.25% |
| over_4.5; odds [3, inf) | 311 | -19.71% | 290 | +19.31% | +6.79% |
| under_2.5; odds [1, 1.5) | 4 | -30.00% | 3 | +100.00% | +42.00% |
| under_2.5; odds [1.5, 2) | 112 | -2.96% | 105 | +56.19% | +0.57% |
| under_2.5; odds [2, 3) | 175 | -4.25% | 167 | +44.31% | +2.97% |
| under_2.5; odds [3, inf) | 39 | +7.00% | 25 | +24.00% | -23.60% |
| under_3.5; odds [1, 1.5) | 188 | -1.37% | 180 | +70.56% | -5.51% |
| under_3.5; odds [1.5, 2) | 124 | -2.23% | 107 | +60.75% | +1.07% |
| under_3.5; odds [2, 3) | 16 | +21.88% | 11 | +36.36% | -22.64% |
| under_3.5; odds [3, inf) | 2 | +50.00% | 2 | +0.00% | -100.00% |
| under_4.5; odds [1, 1.5) | 317 | +0.32% | 295 | +80.34% | -5.32% |
| under_4.5; odds [1.5, 2) | 13 | +14.85% | 4 | +25.00% | -59.75% |
| under_4.5; odds [2, 3) | 0 | n/a | 1 | +0.00% | -100.00% |
| under_4.5; odds [3, inf) | 0 | n/a | 0 | n/a | n/a |

## Quality bands within away wins

| Group | Earlier N | Earlier ROI | Later N | Later win rate | Later ROI |
|---|---:|---:|---:|---:|---:|
| away_win; Q [0, 50) | 38 | +21.34% | 46 | +17.39% | -42.26% |
| away_win; Q [50, 60) | 129 | -16.00% | 117 | +35.04% | -1.37% |
| away_win; Q [60, 70) | 103 | +2.01% | 75 | +25.33% | -41.03% |
| away_win; Q [70, 80) | 48 | +11.35% | 51 | +41.18% | +52.63% |
| away_win; Q [80, 101) | 12 | -72.50% | 11 | +18.18% | -55.27% |

## Sensitivity of the existing hypothesis

| Group | Earlier N | Earlier ROI | Later N | Later win rate | Later ROI |
|---|---:|---:|---:|---:|---:|
| away_win; Q>=60; odds [1.8,3); quote <=3h | 67 | +26.06% | 52 | +38.46% | -2.27% |
| away_win; Q>=65; odds [1.8,3); quote <=3h | 39 | +44.59% | 33 | +51.52% | +32.52% |
| away_win; Q>=70; odds [1.8,3); quote <=3h | 20 | +45.35% | 22 | +59.09% | +50.68% |
| away_win; Q>=65; odds [1.8,4); quote <=3h | 58 | +33.48% | 61 | +39.34% | +10.87% |

## Calibration and fixture evidence

analysis.json contains later-period predicted versus observed win rates in fixed 10-point probability bins, separately by market; per-day, per-league and model-version candidate results; and exclusion counts. Small bins cannot establish calibration. candidate-picks.json contains the exact fixture names, input timestamps, prices, scores and outcomes for independent review.

## Frozen future test

paper-protocol.json records the fixed rule and start boundary (2026-10-19, CAT). The planned review is no earlier than 2027-01-16 and only after 300 settled fixtures across 30 matchdays. Those are planning floors, not evidence of profitability. Do not change thresholds in response to interim results. No automated collection or application policy was changed by this audit.

Exclusions: {"current_or_future_day": 1134, "later_repeat": 32144, "missing_or_invalid_odds": 4218, "no_final_result": 84}.

## Reproduction

Run `rtk proxy python backend/scripts/sweet_spot_audit.py` from the repository root for a fresh read-only snapshot. To reproduce this exact audit, use `--snapshot <this-folder>/raw.json --as-at 2026-10-18T20:44:42+00:00 --output <new-folder>`. Output folders must not already exist.
