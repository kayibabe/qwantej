# Bookmaker price audit (Q>=75 first picks)

Generated: 2026-11-11T14:51:07.567796+00:00

Question: at the moment the entry price was recorded, was it already the best price available across the tracked bookmakers?

## Coverage
```json
{
  "q_min": 75.0,
  "eligible_q75_picks": 3080,
  "prepare_exclusions": {
    "missing_or_invalid_odds": 211775,
    "later_repeat": 50248,
    "replay_snapshot": 1851
  },
  "picks_with_entry_quote": 3080,
  "avg_books_per_pick": 6.571103896103896,
  "picks_with_3plus_books": 3068,
  "recorded_price_equals_best_pct": 100.0,
  "recorded_price_below_best_pct": 0.0,
  "bookmakers_in_snapshots": [
    "1xBet",
    "Bet365",
    "BetVictor",
    "Betano",
    "Betfair",
    "Dafabet",
    "Marathonbet",
    "Pinnacle",
    "SBO",
    "William Hill"
  ]
}
```

## Each book vs the recorded entry price, same picks
| bookmaker | picks | avg_price_vs_source_pct | share_better_than_source_pct | roi_at_book_pct | roi_vs_source_pp | roi_vs_source_ci_pp |
|---|---|---|---|---|---|---|
| Pinnacle | 1791 | -1.37 | 0.00 | -1.49 | -1.59 | [-2.15, -1.20] |
| Betano | 2151 | -1.77 | 0.00 | 0.13 | -1.71 | [-2.06, -1.42] |
| Bet365 | 3060 | -2.74 | 0.00 | -4.08 | -2.66 | [-3.04, -2.28] |
| Betfair | 2045 | -2.98 | 0.00 | -1.81 | -2.93 | [-3.27, -2.67] |
| Dafabet | 175 | -3.27 | 0.00 | 21.27 | -5.21 | [-10.04, -2.18] |
| 1xBet | 2988 | -3.36 | 0.00 | -4.54 | -3.28 | [-3.64, -2.94] |
| William Hill | 1340 | -3.89 | 0.00 | -5.14 | -4.05 | [-5.14, -3.28] |
| Marathonbet | 3058 | -4.13 | 0.00 | -5.55 | -4.10 | [-4.45, -3.72] |
| BetVictor | 2879 | -4.39 | 0.00 | -5.69 | -4.25 | [-4.63, -3.88] |
| SBO | 752 | -6.69 | 0.00 | -5.07 | -7.20 | [-10.03, -5.30] |

## Pricing policy comparison
| policy | n | avg_price | roi_pct | roi_ci_pct | roi_vs_recorded_pp | roi_vs_recorded_ci_pp |
|---|---|---|---|---|---|---|
| recorded entry price | 3080 | 2.03 | -1.57 | [-6.96, 3.65] | 0.00 | [0.00, 0.00] |
| best quoted at entry | 3080 | 2.03 | -1.57 | [-6.96, 3.65] | 0.00 | [0.00, 0.00] |
| median quoted at entry | 3080 | 1.95 | -4.69 | [-9.84, 0.30] | -3.13 | [-3.41, -2.89] |

## Caveats
- Quotes are the last snapshot per bookmaker at or before the recorded entry timestamp, within 3h. This is a pre-entry comparison, not a closing-line measure.
- `odds_snapshots` is not one capture per combo: 64,520 of 341,218 combos have two or more captures, so a bounded lookback is available.
- Best-quoted-price assumes the same stake is placeable at the best book; stake limits, account restrictions and live availability are not modelled.
- Betway is absent from both `odds` and `odds_snapshots`, so it cannot be benchmarked. The comparison is best-available vs recorded across the 10 tracked books.
- The sample is the sweet-spot first-pick universe, which is already negative ROI at the recorded price; this measures price capture, not edge.
