# System Picks market and filter backtest

**Bottom line: the historical data does not contain a statistically validated profitable sweet spot.** The page's Q ≥ 75 universe is close to break-even before costs, and the apparently strong cells are small, unstable or use closing-line information that was not knowable when the bet was placed. The useful findings are exclusion rules and a short watchlist, not a proven betting system.

Snapshot: 2026-11-10T04:16:29.764111+00:00 · mode: `first` prediction per match/market/selection · completed CAT days only.

## Scope and method

- Universe: every stored prediction with `Q >= 75`, joined to a finished match; the daily page's own threshold.
- A pick is counted once per match/market/selection. The `first` stored pre-kickoff prediction is used; later repeats are discarded.
- No replay snapshots (`as_of_at`), no fallback prices, no post-kickoff updates, no current-day results.
- Flat one-unit singles at the captured entry price. Wins pay `odds - 1`; losses pay `-1`; DNB draws are void and excluded.
- Train/test split at **2026-10-20**. Train is used for ranking, test is reported out of sample.
- The grid sweeps market × odds band × model-chance block × bookmaker-implied block × three pre-bet signals × recommendation. Chance and implied blocks are cumulative (`>=`), matching the page.
- `Beat the close` and outcome are **not** in the actionable grid. Closing odds are future information, and the outcome is the thing being predicted. CLV is reported only as a diagnostic.

## What survived inspection

- Eligible picks: **3,080** across **1,071 fixtures** and **45 matchdays** (2026-09-14 to 2026-11-09).
- Overall: hit rate **57.2%**, ROI **-1.6%**, profit **-48.24 units**, average odds **2.03**.
- Best market by raw ROI (at least 30 picks): **away_win** (216 picks, 7.6% ROI, 95% day-cluster interval [-17.5%, 42.2%]).
- Worst: **over_4.5** (33 picks, -15.2% ROI).
- Valid grid cells with at least 30 picks: **2,824**. Best full-sample ROI: **45.4%**.
- Within-market permutation test for the best cell: observed max ROI 45.4%, null median 113.5%, null 95th percentile 206.3%, **p = 0.970**.
- Train/test cells (positive in both halves, n ≥ 40): **15**; of those, cells whose day-cluster bootstrap lower bound clears zero: **0**.

## Market baseline (Q >= 75)

| Market | Picks | Matches | Hit % | ROI % | Net units | Avg odds |
|---|---|---|---|---|---|---|
| double_chance_x2 | 491 | 491 | 51.9 | -7.8 | -38.3 | 2.0 |
| under_3.5 | 432 | 432 | 69.4 | 0.5 | 2.0 | 1.5 |
| under_2.5 | 341 | 341 | 50.1 | 0.6 | 2.1 | 2.1 |
| under_4.5 | 327 | 327 | 82.6 | -1.4 | -4.6 | 1.2 |
| btts_no | 303 | 303 | 49.8 | 4.0 | 12.1 | 2.1 |
| over_2.5 | 225 | 225 | 58.7 | -2.2 | -4.8 | 1.7 |
| away_win | 216 | 216 | 31.0 | 7.6 | 16.5 | 4.0 |
| over_1.5 | 180 | 180 | 83.9 | 3.1 | 5.5 | 1.2 |
| double_chance_1x | 151 | 151 | 57.6 | -12.9 | -19.5 | 1.7 |
| over_3.5 | 135 | 135 | 39.3 | -9.3 | -12.5 | 2.4 |
| btts_yes | 115 | 115 | 62.6 | 2.7 | 3.1 | 1.7 |
| home_win | 90 | 90 | 34.4 | -5.0 | -4.5 | 3.7 |
| over_4.5 | 33 | 33 | 27.3 | -15.2 | -5.0 | 3.7 |
| under_1.5 | 33 | 33 | 30.3 | 3.3 | 1.1 | 3.9 |
| draw | 7 | 7 | 28.6 | -5.7 | -0.4 | 4.9 |
| under_0.5 | 1 | 1 | 0.0 | -100.0 | -1.0 | 15.0 |


Positive-ROI markets: away_win (7.6%), btts_no (4.0%), under_1.5 (3.3%), over_1.5 (3.1%), btts_yes (2.7%), under_2.5 (0.6%), under_3.5 (0.5%).

Negative-ROI markets: over_4.5 (-15.2%), double_chance_1x (-12.9%), over_3.5 (-9.3%), double_chance_x2 (-7.8%), home_win (-5.0%), over_2.5 (-2.2%), under_4.5 (-1.4%).

### Market selection verdict

Bootstrap intervals are day-cluster intervals. `watchlist` means positive ROI worth tracking, not a validated edge; `exclusion candidate` is a market the data says to stop betting before any model work.

| Market | Picks | Hit % | ROI % | 95% interval | Verdict |
|---|---|---|---|---|---|
| double_chance_x2 | 491 | 51.9 | -7.8 | [-15.9%, 0.6%] | exclusion candidate |
| under_3.5 | 432 | 69.4 | 0.5 | [-8.4%, 8.0%] | neutral |
| under_2.5 | 341 | 50.1 | 0.6 | [-14.1%, 14.4%] | neutral |
| under_4.5 | 327 | 82.6 | -1.4 | [-7.0%, 3.4%] | neutral |
| btts_no | 303 | 49.8 | 4.0 | [-8.0%, 15.4%] | watchlist |
| over_2.5 | 225 | 58.7 | -2.2 | [-14.4%, 10.7%] | neutral |
| away_win | 216 | 31.0 | 7.6 | [-17.5%, 42.2%] | watchlist |
| over_1.5 | 180 | 83.9 | 3.1 | [-5.0%, 11.2%] | watchlist |
| double_chance_1x | 151 | 57.6 | -12.9 | [-26.0%, -2.2%] | exclusion candidate |
| over_3.5 | 135 | 39.3 | -9.3 | [-25.8%, 11.9%] | exclusion candidate |
| btts_yes | 115 | 62.6 | 2.7 | [-6.6%, 12.1%] | watchlist |
| home_win | 90 | 34.4 | -5.0 | [-36.5%, 25.9%] | neutral |
| over_4.5 | 33 | 27.3 | -15.2 | [-61.8%, 39.3%] | exclusion candidate |
| under_1.5 | 33 | 30.3 | 3.3 | [-65.0%, 83.3%] | watchlist |
| draw | 7 | 28.6 | -5.7 | [-100.0%, 164.0%] | too few picks |
| under_0.5 | 1 | 0.0 | -100.0 | — | too few picks |


## Odds bands (all markets)

| Odds band | Picks | Hit % | ROI % | Net units |
|---|---|---|---|---|
| 1.00-1.49 | 1040 | 77.9 | -1.1 | -11.2 |
| 1.50-1.79 | 619 | 59.8 | -2.6 | -16.2 |
| 1.80-2.19 | 645 | 49.3 | -2.6 | -16.9 |
| 2.20-2.99 | 468 | 41.0 | 1.7 | 7.9 |
| 3.00-3.99 | 173 | 27.7 | -7.6 | -13.1 |
| 4.00+ | 135 | 17.0 | 1.0 | 1.3 |


## Quality bands

| Q band | Picks | Hit % | ROI % |
|---|---|---|---|
| 75-80 | 1933 | 58.3 | 1.0 |
| 80-85 | 830 | 53.7 | -7.5 |
| 85-90 | 265 | 60.8 | 1.7 |
| 90-+ | 52 | 51.9 | -18.3 |


## Model chance and bookmaker implied blocks

| Model chance | Picks | Hit % | ROI % |
|---|---|---|---|
| 0-50% | 121 | 14.0 | -26.4 |
| 50-60% | 253 | 34.8 | 11.6 |
| 60-70% | 503 | 45.1 | 0.5 |
| 70-80% | 773 | 53.0 | -1.3 |
| 80-101% | 1430 | 71.3 | -2.7 |


| Bookmaker implied | Picks | Hit % | ROI % |
|---|---|---|---|
| 0-40% | 451 | 28.8 | 1.8 |
| 40-50% | 504 | 44.4 | 0.4 |
| 50-60% | 608 | 51.8 | -3.2 |
| 60-70% | 505 | 59.6 | -5.6 |
| 70-80% | 491 | 72.3 | -0.9 |
| 80-101% | 521 | 83.7 | -1.3 |


## Signals and recommendation status

| Filter | Picks | Hit % | ROI % | Net units |
|---|---|---|---|---|
| any | 3080 | 57.2 | -1.6 | -48.2 |
| positive edge | 3061 | 56.9 | -1.6 | -49.5 |
| aligned <=5pp | 495 | 66.9 | -4.4 | -21.6 |
| quote <=8h | 3074 | 57.2 | -1.6 | -47.9 |
| quote <=2h | 3074 | 57.2 | -1.6 | -47.9 |
| CLV > 0 (lookahead) | 329 | 59.0 | 7.3 | 23.9 |
| BET | 232 | 59.9 | 0.4 | 1.0 |
| WATCH | 2055 | 56.4 | -2.2 | -44.3 |


`CLV > 0` is included here only to show the lookahead effect. It cannot be used to choose a bet before kickoff.

## Best grid cells by bootstrap lower bound

The top 60 cells by shrunk ROI are re-measured with a day-cluster bootstrap and ordered here by the 2.5th percentile of the bootstrap ROI. `p(ROI<=0)` is the one-sided bootstrap p-value before any multiple-testing correction; with hundreds of overlapping cells, treat anything above roughly 0.01 as noise. A cell with a high ROI but a wide interval or a negative test result is noise, not a sweet spot.

| Market | Odds | Chance | Implied | Edge | Aligned | Fresh | Rec | N | ROI % | Shrunk ROI | Boot low | Boot high | p(ROI<=0) | Train ROI | Test ROI |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| under_2.5 | 1.50-1.79 | any | any | False | False | False | any | 31 | 24.5 | 8.4 | -6.3 | 32.5 | 0.1 | -2.0 | 37.1 |
| btts_no | 2.20-2.99 | any | >=40% | False | False | False | WATCH | 72 | 17.6 | 9.7 | -6.6 | 40.8 | 0.1 | 19.7 | 16.9 |
| btts_no | 2.20-2.99 | any | any | False | False | False | WATCH | 89 | 16.9 | 10.2 | -8.2 | 43.1 | 0.1 | 5.1 | 21.0 |
| btts_no | 2.20-2.99 | >=60% | >=40% | False | False | False | WATCH | 68 | 17.2 | 9.2 | -9.1 | 42.9 | 0.1 | 12.3 | 18.8 |
| btts_no | 2.20-2.99 | >=60% | any | False | False | False | WATCH | 73 | 16.4 | 9.1 | -9.5 | 39.7 | 0.1 | 0.5 | 22.1 |
| away_win | 2.20-2.99 | >=60% | any | False | False | False | WATCH | 37 | 22.5 | 8.7 | -19.9 | 65.9 | 0.1 | 41.5 | 12.3 |
| away_win | 4.00+ | >=40% | any | False | False | False | WATCH | 44 | 29.8 | 13.1 | -44.4 | 123.1 | 0.2 | -9.4 | 59.7 |
| away_win | 4.00+ | any | any | False | False | False | WATCH | 55 | 45.4 | 23.0 | -48.3 | 159.4 | 0.2 | 20.0 | 61.1 |


## Cells positive in both train and test

Requires n ≥ 40 and a positive ROI in each half. `Boot low` is the day-cluster bootstrap 2.5th percentile; a cell only counts as stable if that clears zero. If none do, the data does not support a stable market rule.

| Market | Odds | Chance | Implied | Edge | Aligned | Fresh | Rec | N | ROI % | Boot low | Boot high | p(ROI<=0) | Train ROI | Test ROI |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| under_4.5 | 1.00-1.49 | >=90% | any | False | True | False | WATCH | 121 | 2.8 | -4.7 | 9.1 | 0.2 | 3.9 | 2.1 |
| under_4.5 | 1.00-1.49 | >=90% | >=80% | False | True | False | WATCH | 120 | 2.6 | -4.9 | 9.0 | 0.2 | 3.9 | 1.8 |
| under_4.5 | 1.00-1.49 | >=90% | any | True | True | False | WATCH | 115 | 2.7 | -5.3 | 9.3 | 0.2 | 3.8 | 1.9 |
| under_4.5 | 1.00-1.49 | >=90% | >=80% | True | True | False | WATCH | 114 | 2.4 | -5.5 | 9.1 | 0.2 | 3.8 | 1.5 |
| under_4.5 | 1.00-1.49 | any | >=80% | False | True | False | WATCH | 131 | 1.4 | -5.6 | 7.7 | 0.3 | 1.8 | 1.2 |
| under_4.5 | 1.00-1.49 | any | >=80% | True | True | False | WATCH | 125 | 1.2 | -6.1 | 7.8 | 0.4 | 1.5 | 0.9 |
| under_4.5 | 1.00-1.49 | any | any | False | True | False | WATCH | 144 | 0.7 | -6.5 | 7.2 | 0.4 | 1.0 | 0.5 |
| btts_no | 2.20-2.99 | any | >=40% | False | False | False | WATCH | 72 | 17.6 | -6.6 | 40.8 | 0.1 | 19.7 | 16.9 |
| under_4.5 | 1.00-1.49 | >=80% | any | False | True | False | WATCH | 143 | 0.4 | -6.7 | 7.2 | 0.5 | 1.0 | 0.0 |
| under_4.5 | 1.00-1.49 | any | any | True | True | False | WATCH | 138 | 0.4 | -7.0 | 7.3 | 0.4 | 0.7 | 0.3 |
| btts_no | 2.20-2.99 | any | any | False | False | False | WATCH | 89 | 16.9 | -8.2 | 43.1 | 0.1 | 5.1 | 21.0 |
| btts_no | 2.20-2.99 | >=60% | >=40% | False | False | False | WATCH | 68 | 17.2 | -9.1 | 42.9 | 0.1 | 12.3 | 18.8 |
| btts_no | 2.20-2.99 | >=60% | any | False | False | False | WATCH | 73 | 16.4 | -9.5 | 39.7 | 0.1 | 0.5 | 22.1 |
| under_3.5 | 1.00-1.49 | any | >=80% | False | False | False | WATCH | 45 | 3.7 | -11.3 | 17.2 | 0.3 | 3.8 | 3.6 |
| away_win | 4.00+ | any | any | False | False | False | WATCH | 55 | 45.4 | -48.3 | 159.4 | 0.2 | 20.0 | 61.1 |


## One pick per match: does the page's pick count overstate opportunity?

The page shows every qualified pick, so one fixture can contribute several correlated bets. Re-running the strongest cells with only the highest-Q pick per fixture gives a more realistic staking view.

| Cell | Picks | Matches | Hit % | ROI % | Per-pick ROI % |
|---|---|---|---|---|---|
| btts_no / 2.20-2.99 / chance any / implied any / edge False / aligned False / fresh False / rec WATCH | 89 | 89 | 48.3 | 16.9 | 16.9 |
| away_win / 4.00+ / chance any / implied any / edge False / aligned False / fresh False / rec WATCH | 55 | 55 | 20.0 | 45.4 | 45.4 |
| btts_no / 2.20-2.99 / chance >=60% / implied any / edge False / aligned False / fresh False / rec WATCH | 73 | 73 | 49.3 | 16.4 | 16.4 |
| btts_no / 2.20-2.99 / chance any / implied >=40% / edge False / aligned False / fresh False / rec WATCH | 72 | 72 | 50.0 | 17.6 | 17.6 |
| away_win / 4.00+ / chance >=40% / implied any / edge False / aligned False / fresh False / rec WATCH | 44 | 44 | 18.2 | 29.8 | 29.8 |
| btts_no / 2.20-2.99 / chance >=60% / implied >=40% / edge False / aligned False / fresh False / rec WATCH | 68 | 68 | 50.0 | 17.2 | 17.2 |


## Calibration and closing-line evidence

The model is overconfident at Q >= 75. The table compares the average model probability with the observed hit rate and with the bookmaker's implied probability. A positive `model minus observed` column means the model claimed more certainty than it delivered.

| Market | N | Observed % | Model % | Implied % | Model-obs pp | Model Brier | Implied Brier | Mean CLV % | Beat close % |
|---|---|---|---|---|---|---|---|---|---|
| double_chance_x2 | 491 | 51.9 | 76.4 | 58.0 | 24.4 | 0.3 | 0.2 | -0.1 | 27.0 |
| under_3.5 | 432 | 69.4 | 84.7 | 70.9 | 15.3 | 0.2 | 0.2 | -0.3 | 17.3 |
| under_2.5 | 341 | 50.1 | 72.3 | 50.7 | 22.2 | 0.3 | 0.2 | -0.3 | 20.0 |
| under_4.5 | 327 | 82.6 | 92.9 | 85.8 | 10.4 | 0.1 | 0.1 | -0.3 | 14.7 |
| btts_no | 303 | 49.8 | 71.6 | 50.0 | 21.8 | 0.3 | 0.3 | -0.1 | 18.8 |
| over_2.5 | 225 | 58.7 | 78.7 | 62.6 | 20.0 | 0.3 | 0.2 | 0.5 | 35.6 |
| away_win | 216 | 31.0 | 57.1 | 32.8 | 26.1 | 0.3 | 0.2 | -0.2 | 32.2 |
| over_1.5 | 180 | 83.9 | 91.0 | 84.0 | 7.1 | 0.1 | 0.1 | -0.0 | 22.9 |
| double_chance_1x | 151 | 57.6 | 81.0 | 66.0 | 23.4 | 0.3 | 0.2 | -0.2 | 21.7 |
| over_3.5 | 135 | 39.3 | 68.1 | 45.2 | 28.8 | 0.3 | 0.2 | 0.0 | 34.4 |
| btts_yes | 115 | 62.6 | 76.8 | 62.7 | 14.2 | 0.3 | 0.2 | 0.3 | 28.0 |
| home_win | 90 | 34.4 | 58.4 | 36.8 | 23.9 | 0.3 | 0.2 | 0.0 | 22.0 |
| over_4.5 | 33 | 27.3 | 57.1 | 31.1 | 29.8 | 0.3 | 0.2 | 2.6 | 50.0 |
| under_1.5 | 33 | 30.3 | 56.4 | 29.0 | 26.1 | 0.3 | 0.2 | -5.9 | 20.0 |


If the model had a genuine pre-bet edge, its picks should beat the closing line more often than not. Mean CLV near zero and a beat-close rate near 50% are evidence against a persistent edge, not proof of one.

## Exclusions and sample caveats

{
  "missing_or_invalid_odds": 211775,
  "later_repeat": 50248,
  "replay_snapshot": 1851
}

- Only 45 complete matchdays are available. That is enough to reject a large, stable edge; it is not enough to certify a small one.
- The model runs are recent and the sample contains one model regime. Earlier/later model versions can behave differently.
- Many stored predictions have no captured price, so the eligible sample is smaller than the raw prediction count.
- Prices are captured quotes, not proof of executable fills, limits or account availability.
- Cells overlap heavily: the same pick appears in many chance/implied/signal combinations. The bootstrap p-values and permutation test are screens, not formal family-wise guarantees.
- Postponed/cancelled fixtures are excluded rather than assumed refunded.

## Recommended way forward

1. **Do not promote a market because its raw ROI is positive.** Away win, BTTS no and over 1.5 look best here, but their day-cluster intervals include zero and their closing-line behaviour does not confirm an edge.
2. **Treat double chance as the first exclusion candidate.** `double_chance_x2` is the largest bucket and is consistently negative; `double_chance_1x` is worse. This is the most reproducible finding in the sample.
3. **Recalibrate probabilities before using edge or Q as a value signal.** At Q >= 75 the model's average probability is far above the observed hit rate. Until calibration is fixed, sort by market price and market-implied probability, not by model edge.
4. **Freeze a small candidate policy and paper-trade it forward.** Example: exclude double chance and over 3.5/4.5, keep away win / BTTS no / over 1.5 / under 2.5-3.5, require a pre-kickoff quote and one pick per fixture. Record the rule before the first bet and review only after 300 settled picks and 30 matchdays.
5. **Use CLV as a validation gate, never as a live filter.** A policy that cannot beat the close over a forward sample should not be promoted, regardless of its historical ROI.
6. **Keep one pick per fixture for staking.** The page's per-pick totals are useful for research, but correlated picks from the same match should not be treated as independent bets.

## Reproduction

```
python /tmp/market_sweet_spot_backtest.py --selection first --min-q 75 --min-sample 30 --output <folder>
```

Files: `analysis.json` (summary and settings), `cells.csv` (full grid), `picks.csv` (eligible picks), `REPORT.md`.
