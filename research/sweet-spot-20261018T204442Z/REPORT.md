# Match and market sweet-spot audit

**Finding: no validated sweet spot.** Away win / Q >=65 / odds [1.80,3.00) / quote age <=3h remains a historical paper-test hypothesis. This audit does not discover an independently validated new policy.

Snapshot: 2026-10-18T20:44:42.797544+00:00. Completed CAT days only: ['2026-09-14', '2026-10-15'].
Raw rows: 46,400. Eligible market observations: 6,272; distinct fixtures: 448.

## Candidate

| Group | Earlier N | Earlier ROI | Later N | Later win rate | Later ROI |
|---|---:|---:|---:|---:|---:|
| Frozen historical candidate | 39 | +44.59% | 12 | +58.33% | +56.33% |
| Candidate with explicit decision + stored features | 0 | n/a | 0 | n/a | n/a |

Later ROI day-cluster descriptive 95% interval: [13.399999999999999, 153.0]. Later ROI with 5% reduction of winnings: +51.43%. This haircut is a scenario, not measured execution cost.

## What the comparison means

- Earlier = before 2026-10-11; later = 2026-10-11 onwards, excluding today's incomplete day. These historical periods have already been examined in the existing rejection-ledger study. Neither is an untouched holdout. No new ranking or tuning on later results.
- First stored prediction per match/market/selection only; no replacing missing prices with later prices. Prices and captures must precede kickoff; quote <= decision <= capture. Replay/fallback odds are excluded. Read-only database transaction; source hash in analysis.json.
- Flat one-unit singles, using recorded entry odds. Wins pay odds minus one, losses minus one, DNB draws refund. Postponed/cancelled games are excluded, not assumed refunded. No accumulators. Counts across markets overlap and must not be added as independent matches.
- Only 0/6,272 eligible observations have both explicit decision timestamps and nonempty stored features. Missing provider labels: 0. Timestamp checks do not certify upstream training data, feature completeness, bookmaker execution, or recovered legacy-data integrity.
- Match conditions here are limited to recorded pre-match Q, market, price, quote age, league and model version. Historical injuries, lineups or form cannot be recreated safely from today's values. Q is not a probability.
- Candidate uncertainty resamples whole matchdays, 5,000 draws, fixed seed. Few days, historical search bias and cross-day dependence limit interpretation; it is not a guarantee or a multiple-testing-adjusted interval.

## Markets

| Group | Earlier N | Earlier ROI | Later N | Later win rate | Later ROI |
|---|---:|---:|---:|---:|---:|
| away_win | 330 | -4.15% | 118 | +27.97% | -1.15% |
| btts_no | 330 | -4.39% | 118 | +40.68% | -11.59% |
| btts_yes | 330 | -2.58% | 118 | +59.32% | +4.39% |
| double_chance_1x | 330 | -6.52% | 118 | +72.03% | +5.81% |
| double_chance_x2 | 330 | -8.89% | 118 | +53.39% | -8.14% |
| draw | 330 | -14.45% | 118 | +25.42% | +3.22% |
| home_win | 330 | -3.03% | 118 | +46.61% | +1.74% |
| over_1.5 | 330 | -1.25% | 118 | +77.97% | -0.51% |
| over_2.5 | 330 | -1.84% | 118 | +52.54% | -4.09% |
| over_3.5 | 330 | -9.04% | 118 | +36.44% | +11.76% |
| over_4.5 | 330 | -20.45% | 118 | +20.34% | +17.45% |
| under_2.5 | 330 | -2.79% | 118 | +47.46% | -3.01% |
| under_3.5 | 330 | -0.25% | 118 | +63.56% | -9.64% |
| under_4.5 | 330 | +0.89% | 118 | +79.66% | -7.45% |

## Market and odds bands

Fixed broad bins, descriptive only. Small cells are not recommendations.

| Group | Earlier N | Earlier ROI | Later N | Later win rate | Later ROI |
|---|---:|---:|---:|---:|---:|
| away_win; odds [1, 1.5) | 11 | -1.64% | 2 | +50.00% | -35.00% |
| away_win; odds [1.5, 2) | 28 | +1.93% | 6 | +33.33% | -40.00% |
| away_win; odds [2, 3) | 95 | +21.56% | 33 | +36.36% | -7.06% |
| away_win; odds [3, inf) | 196 | -17.63% | 77 | +23.38% | +5.29% |
| btts_no; odds [1, 1.5) | 0 | n/a | 0 | n/a | n/a |
| btts_no; odds [1.5, 2) | 96 | -5.61% | 43 | +46.51% | -15.07% |
| btts_no; odds [2, 3) | 217 | -8.58% | 73 | +35.62% | -15.62% |
| btts_no; odds [3, inf) | 17 | +56.00% | 2 | +100.00% | +210.00% |
| btts_yes; odds [1, 1.5) | 37 | -31.78% | 9 | +66.67% | -2.89% |
| btts_yes; odds [1.5, 2) | 235 | +2.36% | 92 | +63.04% | +10.73% |
| btts_yes; odds [2, 3) | 58 | -3.98% | 17 | +35.29% | -26.06% |
| btts_yes; odds [3, inf) | 0 | n/a | 0 | n/a | n/a |
| double_chance_1x; odds [1, 1.5) | 212 | -3.00% | 87 | +73.56% | -5.91% |
| double_chance_1x; odds [1.5, 2) | 88 | -17.31% | 24 | +66.67% | +7.17% |
| double_chance_1x; odds [2, 3) | 20 | -10.95% | 5 | +80.00% | +73.60% |
| double_chance_1x; odds [3, inf) | 10 | +22.50% | 2 | +50.00% | +330.00% |
| double_chance_x2; odds [1, 1.5) | 102 | +4.33% | 25 | +72.00% | -5.00% |
| double_chance_x2; odds [1.5, 2) | 117 | -14.63% | 62 | +59.68% | +0.24% |
| double_chance_x2; odds [2, 3) | 77 | +5.00% | 27 | +22.22% | -47.48% |
| double_chance_x2; odds [3, inf) | 34 | -60.29% | 4 | +50.00% | +107.75% |
| draw; odds [1, 1.5) | 0 | n/a | 0 | n/a | n/a |
| draw; odds [1.5, 2) | 0 | n/a | 0 | n/a | n/a |
| draw; odds [2, 3) | 1 | -100.00% | 2 | +50.00% | +47.50% |
| draw; odds [3, inf) | 329 | -14.19% | 116 | +25.00% | +2.46% |
| home_win; odds [1, 1.5) | 45 | +7.09% | 7 | +57.14% | -22.57% |
| home_win; odds [1.5, 2) | 82 | -4.67% | 30 | +63.33% | +5.07% |
| home_win; odds [2, 3) | 121 | +2.89% | 63 | +42.86% | +0.30% |
| home_win; odds [3, inf) | 82 | -15.68% | 18 | +27.78% | +10.67% |
| over_1.5; odds [1, 1.5) | 314 | -1.23% | 114 | +78.95% | +0.20% |
| over_1.5; odds [1.5, 2) | 16 | -1.56% | 4 | +50.00% | -20.75% |
| over_1.5; odds [2, 3) | 0 | n/a | 0 | n/a | n/a |
| over_1.5; odds [3, inf) | 0 | n/a | 0 | n/a | n/a |
| over_2.5; odds [1, 1.5) | 58 | -7.86% | 7 | +57.14% | -25.57% |
| over_2.5; odds [1.5, 2) | 184 | -2.30% | 65 | +60.00% | +3.20% |
| over_2.5; odds [2, 3) | 86 | +1.97% | 45 | +42.22% | -9.16% |
| over_2.5; odds [3, inf) | 2 | +51.50% | 1 | +0.00% | -100.00% |
| over_3.5; odds [1, 1.5) | 2 | -30.00% | 1 | +100.00% | +42.00% |
| over_3.5; odds [1.5, 2) | 29 | -19.28% | 3 | +33.33% | -47.67% |
| over_3.5; odds [2, 3) | 156 | -3.13% | 51 | +39.22% | +0.88% |
| over_3.5; odds [3, inf) | 143 | -13.10% | 63 | +33.33% | +22.92% |
| over_4.5; odds [1, 1.5) | 0 | n/a | 0 | n/a | n/a |
| over_4.5; odds [1.5, 2) | 2 | -100.00% | 1 | +100.00% | +99.00% |
| over_4.5; odds [2, 3) | 17 | -24.71% | 2 | +50.00% | +11.00% |
| over_4.5; odds [3, inf) | 311 | -19.71% | 115 | +19.13% | +16.85% |
| under_2.5; odds [1, 1.5) | 4 | -30.00% | 2 | +100.00% | +42.50% |
| under_2.5; odds [1.5, 2) | 112 | -2.96% | 54 | +55.56% | -1.56% |
| under_2.5; odds [2, 3) | 175 | -4.25% | 56 | +39.29% | -7.25% |
| under_2.5; odds [3, inf) | 39 | +7.00% | 6 | +33.33% | +8.33% |
| under_3.5; odds [1, 1.5) | 188 | -1.37% | 78 | +66.67% | -12.42% |
| under_3.5; odds [1.5, 2) | 124 | -2.23% | 37 | +59.46% | -2.05% |
| under_3.5; odds [2, 3) | 16 | +21.88% | 2 | +50.00% | +4.00% |
| under_3.5; odds [3, inf) | 2 | +50.00% | 1 | +0.00% | -100.00% |
| under_4.5; odds [1, 1.5) | 317 | +0.32% | 116 | +81.03% | -5.85% |
| under_4.5; odds [1.5, 2) | 13 | +14.85% | 2 | +0.00% | -100.00% |
| under_4.5; odds [2, 3) | 0 | n/a | 0 | n/a | n/a |
| under_4.5; odds [3, inf) | 0 | n/a | 0 | n/a | n/a |

## Quality bands within away wins

| Group | Earlier N | Earlier ROI | Later N | Later win rate | Later ROI |
|---|---:|---:|---:|---:|---:|
| away_win; Q [0, 50) | 38 | +21.34% | 19 | +15.79% | -36.63% |
| away_win; Q [50, 60) | 129 | -16.00% | 47 | +29.79% | -2.47% |
| away_win; Q [60, 70) | 103 | +2.01% | 30 | +30.00% | -19.07% |
| away_win; Q [70, 80) | 48 | +11.35% | 20 | +35.00% | +72.40% |
| away_win; Q [80, 101) | 12 | -72.50% | 2 | +0.00% | -100.00% |

## Sensitivity of the existing hypothesis

| Group | Earlier N | Earlier ROI | Later N | Later win rate | Later ROI |
|---|---:|---:|---:|---:|---:|
| away_win; Q>=60; odds [1.8,3); quote <=3h | 67 | +26.06% | 18 | +44.44% | +20.22% |
| away_win; Q>=65; odds [1.8,3); quote <=3h | 39 | +44.59% | 12 | +58.33% | +56.33% |
| away_win; Q>=70; odds [1.8,3); quote <=3h | 20 | +45.35% | 6 | +66.67% | +77.17% |
| away_win; Q>=65; odds [1.8,4); quote <=3h | 58 | +33.48% | 23 | +34.78% | -3.00% |

## Calibration and fixture evidence

analysis.json contains later-period predicted versus observed win rates in fixed 10-point probability bins, separately by market; per-day, per-league and model-version candidate results; and exclusion counts. Small bins cannot establish calibration. candidate-picks.json contains the exact fixture names, input timestamps, prices, scores and outcomes for independent review.

## Frozen future test

paper-protocol.json records the fixed rule and start boundary (2026-10-19, CAT). The planned review is no earlier than 2027-01-16 and only after 300 settled fixtures across 30 matchdays. Those are planning floors, not evidence of profitability. Do not change thresholds in response to interim results. No automated collection or application policy was changed by this audit.

Exclusions: {"current_or_future_day": 28, "later_repeat": 32144, "missing_or_invalid_odds": 4218, "no_final_result": 28, "timing_or_replay": 3710}.

## Reproduction

Run `rtk proxy python backend/scripts/sweet_spot_audit.py` from the repository root for a fresh read-only snapshot. To reproduce this exact audit, use `--snapshot <this-folder>/raw.json --as-at 2026-10-18T20:44:42.797544+00:00 --output <new-folder>`. Output folders must not already exist.
