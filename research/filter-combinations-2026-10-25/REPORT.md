# Match explorer filter analysis: 1–25 October 2026

Snapshot: 2026-10-25 18:42:01.706278+00:00 UTC (20:42 CAT on 25 October). Today is incomplete.

The broad Q ≥75 candidate pool lost **2.10%** at one unit per selection. The best observed combination with at least 50 selections, 30 distinct matches and seven active dates returned **24.90%**, but its uncertainty interval includes a loss. No reliable future winner has been established.

## Coverage and audit

- 1,776 feed rows; 107 exact duplicate rows removed; zero conflicting duplicates.
- 1,669 unique match/market/selection candidates across 591 matches.
- 1,609 selections across 572 finished matches. All-settled hit rate: 57.55%.
- 123 finished selections excluded from the priced analysis because captured bookmaker provenance was insufficient. They are not treated as losses.
- Main priced sample: 1,486 selections, 531 matches, 20 active dates; 864 wins, 622 losses, no settled voids.
- Unfinished: 24 live selections (six matches), 17 scheduled (seven matches), and 19 postponed (six matches). Postponed rows are outside this played-match study.
- No eligible page candidates were found for 2–6 October. This is the retained candidate feed, not all football fixtures in those dates.
- All included prediction insertion times, run completion times and quote times precede kickoff; quotes must also precede the recorded decision/information time, have decimal odds >1, an odds-source ID, a named bookmaker and explicit non-fallback provenance.
- 60 otherwise valid prices were older than three hours at decision time. Excluding them leaves 1426 selections, 58.20% hit rate and -1.92% ROI.

## Calculation

One unit on every qualifying **single selection**, using its stored source decimal odds. Win profit = odds −1; loss = −1; a settled void returns the stake and has zero profit. ROI = total net profit / total stakes ×100; hit rate = wins / (wins + losses) ×100. These are hypothetical gross returns before tax, commission, rejected bets or price availability, not placed-bet accounting and not accumulator returns. Multiple selections on a match are separate stakes and can be correlated.

## Best combinations with minimum sample coverage

Every row below already includes Q ≥75. Probability and edge values are percentages. Threshold endpoints are inclusive. Minimum coverage is a screening rule, not proof of statistical reliability.

| Filter | Selections | Matches | Wins–losses | Hit rate | Profit (units) | ROI |
|---|---:|---:|---:|---:|---:|---:|
| away_win; q_score ≤ 80; model_probability ≤ 70; odds ≤ 5 | 59 | 59 | 25–34 | 42.37% | 14.69 | 24.90% |
| away_win; q_score ≤ 80; odds ≥ 2, odds ≤ 5 | 66 | 66 | 27–39 | 40.91% | 14.82 | 22.45% |
| btts_no; model_probability ≤ 70 | 63 | 63 | 34–29 | 53.97% | 12.71 | 20.17% |
| All markets / competitions; q_score ≥ 85, q_score ≤ 90; odds ≤ 2; edge ≥ 20% | 58 | 55 | 41–17 | 70.69% | 11.54 | 19.90% |
| All markets / competitions; q_score ≤ 80; model_probability ≤ 60; edge ≥ 20% | 52 | 51 | 17–35 | 32.69% | 10.13 | 19.48% |
| btts_no; model_probability ≤ 70; edge ≥ 10% | 62 | 62 | 33–29 | 53.23% | 11.96 | 19.29% |
| under_2.5; q_score ≥ 80, q_score ≤ 90; model_probability ≥ 70 | 52 | 52 | 34–18 | 65.38% | 9.92 | 19.08% |
| under_2.5; q_score ≥ 80; model_probability ≥ 70 | 55 | 55 | 36–19 | 65.45% | 10.46 | 19.02% |


The leading away-win combination has 59 selections, 25 wins and 34 losses, +14.69 units. Its 95% fixture-cluster bootstrap ROI interval is **−13.29% to +65.98%**. The bootstrap resamples whole matches (5,000 replications, fixed seed) to preserve within-match dependence. Intervals are descriptive and **not corrected for searching millions of combinations**, league/day dependence or model drift.

The unrestricted maximum is +700% from a single winning selection. It is not a useful strategy ranking.

## Combinations with at least 100 selections, 30 matches and seven dates

| Filter | Selections | Matches | Wins–losses | Hit rate | Profit (units) | ROI |
|---|---:|---:|---:|---:|---:|---:|
| All markets / competitions; q_score ≤ 80; model_probability ≥ 60, model_probability ≤ 70; odds ≥ 2, odds ≤ 3 | 111 | 101 | 57–54 | 51.35% | 17.77 | 16.01% |
| All markets / competitions; q_score ≤ 80; model_probability ≥ 60, model_probability ≤ 70; odds ≥ 2 | 116 | 105 | 58–58 | 50.00% | 15.87 | 13.68% |
| All markets / competitions; q_score ≤ 80; model_probability ≤ 70; odds ≥ 2, odds ≤ 3 | 169 | 149 | 80–89 | 47.34% | 18.84 | 11.15% |
| All markets / competitions; q_score ≤ 80; model_probability ≥ 60, model_probability ≤ 70; odds ≤ 3; edge ≥ 10% | 158 | 142 | 82–76 | 51.90% | 17.49 | 11.07% |
| All markets / competitions; q_score ≤ 85; model_probability ≤ 70; odds ≥ 2, odds ≤ 3 | 227 | 196 | 107–120 | 47.14% | 25.07 | 11.04% |


## Market-only comparison

| Filter | Selections | Matches | Wins–losses | Hit rate | Profit (units) | ROI |
|---|---:|---:|---:|---:|---:|---:|
| under_1.5 | 4 | 4 | 2–2 | 50.00% | 1.64 | 41.00% |
| draw | 5 | 5 | 2–3 | 40.00% | 1.57 | 31.40% |
| btts_no | 152 | 152 | 80–72 | 52.63% | 12.69 | 8.35% |
| btts_yes | 40 | 40 | 26–14 | 65.00% | 2.50 | 6.25% |
| under_3.5 | 224 | 224 | 162–62 | 72.32% | 9.59 | 4.28% |
| home_win | 46 | 46 | 18–28 | 39.13% | 1.70 | 3.70% |
| under_2.5 | 179 | 179 | 93–86 | 51.96% | 5.03 | 2.81% |
| over_1.5 | 74 | 74 | 62–12 | 83.78% | 1.93 | 2.61% |
| under_4.5 | 157 | 157 | 132–25 | 84.08% | 1.24 | 0.79% |
| double_chance_1x | 75 | 75 | 49–26 | 65.33% | -2.09 | -2.79% |
| over_2.5 | 97 | 97 | 53–44 | 54.64% | -8.52 | -8.78% |
| away_win | 110 | 110 | 32–78 | 29.09% | -12.91 | -11.74% |
| double_chance_x2 | 256 | 256 | 131–125 | 51.17% | -30.98 | -12.10% |
| over_3.5 | 56 | 56 | 19–37 | 33.93% | -11.53 | -20.59% |
| over_4.5 | 11 | 11 | 3–8 | 27.27% | -3.11 | -28.27% |


Under 1.5 and draw have the largest market-only ROI but only four and five selections respectively. Among markets with at least 50 selections, BTTS No leads at +8.35% (152 selections); its 95% fixture-cluster interval is −8.15% to +25.01%. Under 4.5 has an 84.08% hit rate but only +0.79% ROI, demonstrating why hit rate alone is insufficient.

## Later-date diagnostic

The first 70% of eligible active dates are 1–19 October; later dates are 20–25 October. Rank on the earlier segment with at least 50 selections, 30 matches and seven dates. Later results below were not used as the ranking score. This is a retrospective diagnostic, not an untouched prospective validation: all records already exist, the grid is exploratory, and equivalent filters are deduplicated using full-period membership.

| Filter | Earlier n | Earlier ROI | Later n | Later ROI |
|---|---:|---:|---:|---:|
| All markets / competitions; q_score ≥ 80, q_score ≤ 85; model_probability ≤ 80; odds ≥ 2, odds ≤ 3 | 59 | 28.90% | 33 | -17.88% |
| All markets / competitions; q_score ≤ 80; model_probability ≤ 70; edge ≥ 20% | 60 | 24.70% | 46 | -8.72% |
| All markets / competitions; q_score ≥ 80; model_probability ≤ 80; odds ≥ 2, odds ≤ 3; edge ≥ 20% | 52 | 23.06% | 27 | -17.70% |
| All markets / competitions; q_score ≤ 80; model_probability ≤ 70; odds ≤ 5; edge ≥ 20% | 50 | 22.84% | 41 | 2.41% |
| All markets / competitions; q_score ≤ 80; model_probability ≥ 60, model_probability ≤ 70; odds ≥ 2, odds ≤ 3 | 62 | 22.77% | 49 | 7.45% |
| btts_no; model_probability ≤ 80 | 79 | 22.59% | 49 | -8.18% |

## What was searched

The page permits continuously variable numeric bounds, so literally every input combination is unbounded. This report exhaustively scans a declared grid, not every possible decimal threshold:

- Market: all, or each available market.
- Competition: all, or each available competition; also crossed with market.
- Q-score: underlying minimum 75; optional lower and upper cutoffs at 80, 85, 90.
- Model probability: optional lower and upper cutoffs at 60%, 70%, 80%, 90%.
- Odds: optional lower and upper cutoffs at 1.5, 2, 3, 5.
- Minimum edge: unset, 0%, 5%, 10%, 20%.
- All valid interval pairs use inclusive bounds. Equal lower/upper point intervals are omitted. Unset bounds are included.
- Finished status is fixed. Sorting changes order, not returns. Search text and favourites are not swept: there is no preserved pre-match favourite/search history, and arbitrary team-name subsets invite hindsight selection.

There are **4,882,500 grid combinations** across 434 nonempty market/competition scopes, producing **20,176 distinct nonempty selection sets**. Equivalent filters are represented by the simplest encountered expression. The interactive table exposes all distinct sets, including small samples; its default screen requires 50 selections, 30 matches and seven dates. Rows overlap, so their profits must never be added together.

## Critical page findings and suggested changes

1. **Incomplete loading:** the screenshot shows 100 of 188 candidates. Filters and summaries run on loaded rows. Fetch the full server-side filtered universe before showing historical performance.
2. **Duplicate inflation:** the feed's latest-run join can return duplicate predictions for the same match/market/selection. Deduplicate deterministically before counts and performance calculations.
3. **Ambiguous qualification:** Q ≥75 is a research threshold, not evidence that an accumulator leg passed calibration, odds freshness, context or other publication gates. Label this pool “Q-score candidates”.
4. **Different admin universe:** current source intersects the admin list with a daily ROI shortlist. This report uses the full candidate feed matching the screenshot's Q ≥75 description, not a retrospective application of the admin screen. Show the active universe explicitly.
5. **Missing date-range performance:** add date range, selection count, unique match count, won/lost/void, priced coverage, hit rate, net units and ROI to the page. Separate unsettled rows and expose excluded-price reasons.
6. **Avoid automatic promotion:** retain the present qualification gates. Freeze a short list of simple hypotheses (such as BTTS No and the away-win subset) and evaluate new matches at captured pre-match odds before considering a policy change. Do not choose another threshold every time a later batch loses.
7. **Selection counts are not match counts:** display both. Multiple bets on one match can make a sample look larger and more diversified than it is.

## Scope limitations and reproducibility

This reproduces the current historical `/selections/qualified` feed: latest completed model run per match/market, run target date equal to the Malawi kickoff date, Q ≥75, non-excluded fixtures. It does not reconstruct every candidate that might have appeared and later disappeared in a prior refresh, user-specific favourites, historic admin screens, or exact historical UI loading order. Archived created-at timestamps do not independently prove end-user visibility or executable bookmaker prices. Results use the database's recorded final scores without external re-verification. Matches on 25 October were still in progress at extraction.

The raw database transaction is repeatable-read and read-only. No results, odds, selections, strategy settings, app source or qualification gates were changed. Reproduction: copy `export_snapshot.py` to the backend container, run with `PYTHONPATH=/app`, copy `/tmp/filter_snapshot.json` back as `snapshot.json`, then run `analyse.py` and `build_report.py`. The export snapshot also contains earlier dates for audit, but analysis is explicitly limited to 1–25 October.

Files: `snapshot.json` (raw evidence), `eligible_selections.json` (priced analysis rows), `summary.json`, `combinations.json`, `report.html` (interactive table), and the three Python scripts. The summary records the raw snapshot SHA-256. Dependencies: existing backend SQLAlchemy/settlement modules for export; Python and NumPy for analysis.

## Numeric filters in isolation

Every row retains the baseline Q ≥75 and all markets/competitions.

| Filter | Selections | Matches | Wins–losses | Hit rate | Profit (units) | ROI |
|---|---:|---:|---:|---:|---:|---:|
| q_score ≤ 80 | 933 | 479 | 544–389 | 58.31% | -13.91 | -1.49% |
| q_score ≤ 85 | 1335 | 530 | 768–567 | 57.53% | -37.57 | -2.81% |
| q_score ≤ 90 | 1466 | 531 | 854–612 | 58.25% | -26.81 | -1.83% |
| q_score ≥ 80, q_score ≤ 85 | 402 | 268 | 224–178 | 55.72% | -23.66 | -5.89% |
| q_score ≥ 80, q_score ≤ 90 | 533 | 301 | 310–223 | 58.16% | -12.90 | -2.42% |
| q_score ≥ 80 | 553 | 304 | 320–233 | 57.87% | -17.34 | -3.14% |
| q_score ≥ 85, q_score ≤ 90 | 131 | 113 | 86–45 | 65.65% | 10.76 | 8.21% |
| q_score ≥ 85 | 151 | 121 | 96–55 | 63.58% | 6.32 | 4.19% |
| q_score ≥ 90 | 20 | 18 | 10–10 | 50.00% | -4.44 | -22.20% |
| model_probability ≤ 60 | 167 | 148 | 49–118 | 29.34% | -11.81 | -7.07% |
| model_probability ≤ 70 | 401 | 314 | 161–240 | 40.15% | -2.74 | -0.68% |
| model_probability ≤ 80 | 782 | 466 | 358–424 | 45.78% | -20.20 | -2.58% |
| model_probability ≤ 90 | 1206 | 527 | 634–572 | 52.57% | -32.32 | -2.68% |
| model_probability ≥ 60, model_probability ≤ 70 | 234 | 200 | 112–122 | 47.86% | 9.07 | 3.88% |
| model_probability ≥ 60, model_probability ≤ 80 | 615 | 431 | 309–306 | 50.24% | -8.39 | -1.36% |
| model_probability ≥ 60, model_probability ≤ 90 | 1039 | 516 | 585–454 | 56.30% | -20.51 | -1.97% |
| model_probability ≥ 60 | 1319 | 520 | 815–504 | 61.79% | -19.44 | -1.47% |
| model_probability ≥ 70, model_probability ≤ 80 | 381 | 306 | 197–184 | 51.71% | -17.46 | -4.58% |
| model_probability ≥ 70, model_probability ≤ 90 | 805 | 485 | 473–332 | 58.76% | -29.58 | -3.67% |
| model_probability ≥ 70 | 1085 | 493 | 703–382 | 64.79% | -28.51 | -2.63% |
| model_probability ≥ 80, model_probability ≤ 90 | 424 | 344 | 276–148 | 65.09% | -12.12 | -2.86% |
| model_probability ≥ 80 | 704 | 403 | 506–198 | 71.88% | -11.05 | -1.57% |
| model_probability ≥ 90 | 280 | 217 | 230–50 | 82.14% | 1.07 | 0.38% |
| odds ≤ 1.5 | 536 | 375 | 418–118 | 77.99% | 1.21 | 0.23% |
| odds ≤ 2 | 1016 | 489 | 683–333 | 67.22% | -17.61 | -1.73% |
| odds ≤ 3 | 1363 | 530 | 840–523 | 61.63% | -0.73 | -0.05% |
| odds ≤ 5 | 1460 | 531 | 861–599 | 58.97% | -23.88 | -1.64% |
| odds ≥ 1.5, odds ≤ 2 | 505 | 383 | 281–224 | 55.64% | -19.82 | -3.92% |
| odds ≥ 1.5, odds ≤ 3 | 852 | 488 | 438–414 | 51.41% | -2.94 | -0.35% |
| odds ≥ 1.5, odds ≤ 5 | 949 | 489 | 459–490 | 48.37% | -26.09 | -2.75% |
| odds ≥ 1.5 | 975 | 489 | 462–513 | 47.38% | -33.46 | -3.43% |
| odds ≥ 2, odds ≤ 3 | 370 | 286 | 168–202 | 45.41% | 15.88 | 4.29% |
| odds ≥ 2, odds ≤ 5 | 467 | 337 | 189–278 | 40.47% | -7.27 | -1.56% |
| odds ≥ 2 | 493 | 337 | 192–301 | 38.95% | -14.64 | -2.97% |
| odds ≥ 3, odds ≤ 5 | 100 | 97 | 21–79 | 21.00% | -26.15 | -26.15% |
| odds ≥ 3 | 126 | 112 | 24–102 | 19.05% | -33.52 | -26.60% |
| odds ≥ 5 | 26 | 25 | 3–23 | 11.54% | -7.37 | -28.35% |
| edge ≥ 0% | 1479 | 527 | 857–622 | 57.94% | -31.63 | -2.14% |
| edge ≥ 5% | 1398 | 526 | 788–610 | 56.37% | -28.87 | -2.07% |
| edge ≥ 10% | 1152 | 482 | 594–558 | 51.56% | -35.72 | -3.10% |
| edge ≥ 20% | 486 | 269 | 216–270 | 44.44% | -18.55 | -3.82% |
