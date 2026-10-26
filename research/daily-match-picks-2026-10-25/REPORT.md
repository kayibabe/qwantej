# Daily Match Picks: 1–25 October 2026

Data snapshot: 2026-10-25 20:15:07.150681+00:00 UTC (2026-10-25 20:15:07.150681+00:00). The 25 October slate was still underway when captured.

## Finding

The replayed Daily Match Picks produced **90 selections over 18 active dates**. Of these, 85 had settled: **42 wins and 43 losses**, a 49.4% hit rate. One unit staked on each settled pick returned **+14.69 units / 17.3% ROI**. Five of the picks from 25 October were unresolved at extraction and are excluded from this settled-pick result.

The highest full-sample combination passing the screening rule (at least 30 settled picks, 25 distinct matches and five active dates) was **all historically qualifying markets, Q 75–80, odds ≤2.75**: 37 picks, 21 wins and 16 losses; ROI 32.8%. The fixture-resampled 95% interval is -6.0% to 69.4%, so this small-sample edge is uncertain. Searching thousands of overlapping filters makes the strongest observed result more likely to be a chance winner.

## Daily Match Picks rules reconstructed

For each target date, the API looks only at prior settled matches to qualify each market. Historical selections require Q ≥70, captured odds from 2.00 up to (but not including) 3.00, a named bookmaker and non-fallback source, a valid pre-kickoff quote, and a prediction timestamp before kickoff. Quote freshness at the decision must be within the configured two hours; the route also applies a three-hour maximum. A market qualifies only if historical hit rate is **strictly greater than 50%** and flat-stake ROI is **strictly greater than 30%**. Daily candidates use those qualifying markets, the same Q and odds bounds, and valid captured pre-kickoff bookmaker prices. In the screenshot the visible controls were Minimum Q = 70 and Grade = All; this analysis uses that view.

I replayed this process date by date, so a future result cannot qualify an earlier day’s market. For each date and match/market/selection, I used the latest valid prediction, then settled it against the score in the local database. I counted single selections with a flat one-unit stake: a win returns odds −1 net units; a loss −1 unit. ROI is total net units / settled stakes. These are reconstructed paper results, not confirmed placed wagers or executable-price accounting.

## Market performance within the reconstructed daily picks

| Market / filter | Selections | Won | Lost | Hit rate | Net units | ROI | Earlier ROI | Later ROI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| over_4.5 | 5 | 4 | 1 | 80.0% | +5.02 | 100.4% | — | — |
| over_2.5 | 23 | 14 | 9 | 60.9% | +7.18 | 31.2% | — | — |
| double_chance_1x | 10 | 5 | 5 | 50.0% | +1.63 | 16.3% | — | — |
| away_win | 46 | 19 | 27 | 41.3% | +1.86 | 4.0% | — | — |
| double_chance_x2 | 1 | 0 | 1 | 0.0% | -1.00 | -100.0% | — | — |


Over 4.5 leads at +100.4%, but it has only five picks (four wins). Its 95% match-resampled interval spans -1.8% to 172.0%. Over 2.5 has 23 picks and +31.2% ROI, with an interval of -13.6% to 74.0%. The intervals are broad; neither establishes a dependable market edge. (Rows are sorted by full-period ROI.)

## Best Q-score / odds filters across historically qualifying markets

This sweep varies Q lower/upper bounds and odds bands inside the page’s existing Q ≥70 and 2.00–<3.00 base range, across all qualifying markets or one market at a time. The default screen requires 30 settled selections, 25 distinct matches and five active dates. Table columns “Earlier” and “Later” show performance before 20 October and from 20–25 October.

| Market / filter | Selections | Won | Lost | Hit rate | Net units | ROI | Earlier ROI | Later ROI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| All qualifying markets; Q 75–80; odds ≤2.75 | 37 | 21 | 16 | 56.8% | +12.15 | 32.8% | 37.2% | 22.6% |
| All qualifying markets; Q 75–80 | 42 | 23 | 19 | 54.8% | +13.12 | 31.2% | 43.6% | 3.8% |
| All qualifying markets; Q 75–80; odds ≤3 | 42 | 23 | 19 | 54.8% | +13.12 | 31.2% | 43.6% | 3.8% |
| All qualifying markets; Q 75–80; odds ≥2.1–≤2.75 | 31 | 16 | 15 | 51.6% | +7.93 | 25.6% | 30.7% | 14.8% |
| All qualifying markets; Q 70–80; odds ≥2.25–≤2.75 | 34 | 17 | 17 | 50.0% | +8.62 | 25.4% | 31.5% | 12.5% |
| All qualifying markets; Q 75–80; odds ≥2.1 | 36 | 18 | 18 | 50.0% | +8.90 | 24.7% | 39.2% | -4.3% |
| All qualifying markets; Q 75–80; odds ≥2.1–≤3 | 36 | 18 | 18 | 50.0% | +8.90 | 24.7% | 39.2% | -4.3% |
| All qualifying markets; Q 75–85; odds ≥2.25 | 32 | 15 | 17 | 46.9% | +7.66 | 23.9% | 50.6% | -44.2% |
| All qualifying markets; Q 75–85; odds ≥2.25–≤3 | 32 | 15 | 17 | 46.9% | +7.66 | 23.9% | 50.6% | -44.2% |
| All qualifying markets; Q 70–80; odds ≥2.25 | 44 | 21 | 23 | 47.7% | +10.47 | 23.8% | 34.9% | 2.3% |
| All qualifying markets; Q 70–80; odds ≥2.25–≤3 | 44 | 21 | 23 | 47.7% | +10.47 | 23.8% | 34.9% | 2.3% |
| All qualifying markets; Q 70+; odds ≤2.25 | 36 | 21 | 15 | 58.3% | +8.19 | 22.8% | 29.3% | 13.5% |


The period split is descriptive, not a clean prospective test: filters are searched retrospectively over the whole data set. For example, a rule’s later ROI may change sharply when the last few results settle. Keep these filters in research until frozen and checked against genuinely new picks.

## Small sample leaders

| Market / filter | Selections | Won | Lost | Hit rate | Net units | ROI | Earlier ROI | Later ROI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| over_4.5; Q 70+; odds ≥2.75 | 1 | 1 | 0 | 100.0% | +1.96 | 196.0% | — | 196.0% |
| over_4.5; Q 70+; odds ≥2.75–≤3 | 1 | 1 | 0 | 100.0% | +1.96 | 196.0% | — | 196.0% |
| over_4.5; Q 70–80; odds ≥2.75 | 1 | 1 | 0 | 100.0% | +1.96 | 196.0% | — | 196.0% |
| over_4.5; Q 70–80; odds ≥2.75–≤3 | 1 | 1 | 0 | 100.0% | +1.96 | 196.0% | — | 196.0% |
| over_4.5; Q 70–85; odds ≥2.75 | 1 | 1 | 0 | 100.0% | +1.96 | 196.0% | — | 196.0% |
| over_4.5; Q 70–85; odds ≥2.75–≤3 | 1 | 1 | 0 | 100.0% | +1.96 | 196.0% | — | 196.0% |
| over_4.5; Q 70–90; odds ≥2.75 | 1 | 1 | 0 | 100.0% | +1.96 | 196.0% | — | 196.0% |
| over_4.5; Q 70–90; odds ≥2.75–≤3 | 1 | 1 | 0 | 100.0% | +1.96 | 196.0% | — | 196.0% |


Raw rankings can put a market with one or five selections first. Treat the sample screen as a guard against the most extreme cases, not as a guarantee of statistical reliability. Confidence intervals here resample whole matches (5,000 replicates, fixed seed); they do not account for the extensive filter search, date clustering, model updates or price execution.

## Coverage and limits

- The database snapshot contained 1757 Q ≥70 predictions with prices in the Daily Match Picks odds band, over historical rows available before 25 October CAT end of day. Historical rows were deduplicated per fixture, market and selection using the latest valid pre-match prediction, mirroring the route.
- The reconstructed daily feed yielded 90 picks on 18 dates. Dates without picks are not missing losses; they had no market/prediction satisfying the reconstructed gates.
- The 25 October view had 15 picks; 11 were settled at snapshot time. The other five remain open and are not scored as losses.
- Results use the locally stored match scores, prediction timestamps and captured odds. I did not independently verify scores or bookmaker execution outside this database.
- Markets and filters overlap; do not add their returns together. Search results are exploratory and do not justify changing qualification thresholds or publication rules.

## Reproduction

`export_snapshot.py` makes a read-only repeatable-read database extract; `analyse.py` performs the as-of-date replay and filter sweep; `build_report.py` creates this report and `report.html`. `snapshot.json` is the raw extract, `daily_picks.json` contains the reconstructed candidates, `summary.json` has the audit metrics, and `combinations.json` contains the full nonempty grid. SHA-256: `9392edd1a19aa29f3e3b381382a9f0a5a2b3c677c9bd6bb11068812d4b3b2228`.
