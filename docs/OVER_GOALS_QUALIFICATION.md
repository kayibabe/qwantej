# Over-goals qualification v1 (provisional)

This policy set covers regulation-time Over 1.5, 2.5, 3.5 and 4.5. Its
probability grades and statistical cutoffs are design hypotheses, not validated
hit-rate guarantees. No daily selection minimum is used. Each recommendation
must have positive expected value at its available price.

## Grades and initial profile screens

| Market | Goal total | Probability grades (A+, A, B, C) | Primary probability | Preferred projected total |
| --- | ---: | --- | ---: | ---: |
| Over 1.5 | 2+ | 95%, 90%, 85%, 75% | 90% | 3.2 |
| Over 2.5 | 3+ | 80%, 70%, 60%, 50% | 70% | 3.8 |
| Over 3.5 | 4+ | 65%, 55%, 45%, 35% | 55% | 4.2 |
| Over 4.5 | 5+ | 45%, 35%, 25%, 15% | 35% | 4.5 |

The table lists grade floors; values below C are D. Over 2.5 grade B is a
conditional pool only when strong supporting value review is verified. Other
markets use A/A+ as the primary pool. Market screens are supporting evidence,
not an additive score. Model probability, calibration, price, context, sample
quality and risk review remain separate.

The initial supporting indicators follow the supplied framework: Over 1.5
historical frequencies (Over 1.5/2.5/3.5: 85/60/35%), 8 shots on target, 3 big
chances, and first-half Over 0.5 at 70%; Over 2.5 frequencies (Over 1.5/2.5/
3.5/4.5: 85/65/40/20%), 9 shots, 3.5 big chances and first-half Over 1.5 at
40%; Over 3.5 frequencies (Over 2.5/3.5/4.5: 75/45/25%), 10 shots, 4 big
chances, 3.5 combined historical goals, and first-half Over 1.5 at 50%; Over
4.5 frequencies (Over 2.5/3.5/4.5: 80/60/35%), 11 shots, 5 big chances,
4.0 combined historical goals, and first-half Over 1.5 at 55%. BTTS is
descriptive and optional, including in one-sided attacking mismatches.

## Operational controls and current limits

- New Over 1.5/2.5/3.5 predictions capture versioned market-specific
  qualification evidence. Daily ticket construction and custom accumulator
  editing reject selections without a passing assessment.
- Over 4.5 now uses the supplied probability grades and supporting indicator
  thresholds. As with the other Over markets, secondary indicators are shown
  for review and are not counted as independent hard gates.
- Every market still fails closed without market-specific promoted
  calibration and a promoted shared-distribution calibration, sufficient
  point-in-time samples, verified context/risk review, a qualifying probability
  grade and positive EV. Legacy predictions without a shared forecast cannot
  pass.
- Raw venue history is exposed only as descriptive evidence. Opponent-adjusted
  qualification projections, big-chance counts and tactical/lineup reviews
  are not yet captured by the current pipeline. A shared independent-Poisson
  comparison now reports all four probabilities from one expected-goals
  baseline, but it is uncalibrated and is not qualification evidence.
- Every total-goal assessment now reads its event probability from the same
  forecast snapshot. Current predictions use an independent-Poisson baseline
  from the shared expected-goals projection, which is explicitly uncalibrated;
  the assessment blocks release until a shared calibrated distribution passes
  chronological validation. The existing ensemble output remains available in
  prediction records and Q-score evidence, but is not used as the total-market
  qualification probability.
- Do not call the framework validated until league/season holdouts and
  probability calibration, Brier/log loss, closing-line value and priced
  performance with uncertainty have been assessed.

The intended result today is more explicit market-specific rejection and
review evidence. Calibration/context gates may correctly leave every market
without a qualifying selection.
