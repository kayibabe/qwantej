# Pre-entry line movement audit

**Question: does the price move into our entry price carry information the entry price does not already contain?**

## Method

- Population: the same strict no-lookahead first-pick universe as the
  sweet-spot report (settled fixtures only, first stored pre-kickoff
  prediction, valid non-fallback odds).
- Prior quote: the last capture per bookmaker at least 1 hour and at most 48
  hours before the recorded entry timestamp, then the best price across books.
- Move: `logit(1/entry_odds) - logit(1/prior_odds)`. Positive means the price
  shortened into our entry; negative means it drifted out.
- Test: `won ~ logit(1/entry_odds) + move`, with matchdays resampled as
  clusters. If the move coefficient interval includes zero, the movement adds
  nothing once the price is known.

## Coverage

- Eligible Q-universe picks with settled results: **17,595**
- Picks with a usable prior quote: **1,310**
  (7.4% of eligible)
- Median books behind the prior quote: **5.0**

## Result

| Metric | Value |
| --- | --- |
| N | 1310 |
| Move coefficient | -0.897 |
| 95% CI | [-2.015, 0.864] |
| p(coefficient <= 0) | 0.788 |
| Verdict | no information beyond the entry price |

## ROI by movement quintile

| band | move_low | move_high | n | hit_rate_pct | avg_odds | roi_pct | roi_ci_pct |
|---|---|---|---|---|---|---|---|
| 0 | -0.693 | -0.054 | 266 | 62.030 | 1.918 | -2.402 | [-29.69, 11.04] |
| 1 | -0.054 | 0.000 | 853 | 59.086 | 2.158 | -0.136 | [-5.54, 6.34] |
| 2 | 0.006 | 0.511 | 191 | 53.403 | 2.148 | -7.618 | [-17.86, 16.48] |

## Caveats

- **Structural coverage limit.** Predictions are created a median of ~9 hours
  before kickoff and the first stored pick coincides with the first snapshot,
  so a first pick has no pre-entry price history by construction.  Only later
  pre-kickoff predictions have a measurable prior quote, which is why the
  sample is a pilot rather than a powered test.
- Snapshot coverage is sparse before 2026-09-14 and uneven afterwards.
- The prior quote is "best price across books", so part of the measured move
  can be a change in which bookmaker is best rather than a genuine market move.
- Capture cadence is not fixed; a 1-hour minimum gap is used to avoid comparing
  two near-simultaneous fetches.
- This is a retrospective test on a sample that was not pre-registered. A
  positive result would justify a frozen prospective test, not a live rule.
- Promotion would still require the market-relative and CLV gates in
  `docs/CALIBRATION_AND_POLICY_2026-11-10.md`.
