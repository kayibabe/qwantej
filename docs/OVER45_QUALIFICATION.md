# Over 4.5 qualification v1 (provisional)

Five regulation-time goals win, including stoppage time and excluding extra
time/shootouts. The policy applies to new model recommendations, automatic
tickets (including market-priced/relaxed tiers), and new custom accumulator
selections. Existing saved tickets and settlements are not rewritten.

The selection detail drawer shows the assessment. Legacy predictions missing
the new snapshot fail closed; a future model run captures new evidence.

## Current screening definitions

Use up to 12 latest finished home fixtures for the home team and away fixtures
for the away team, with at least 8 per team. All are earlier than the decision
and target kickoff. Store match IDs and sample sizes in the feature snapshot.

- Preferred projected total is >= 4.5 goals. The current required historical
  venue projection is >= 4.0, calculated as half the sum of both teams' venue-specific mean xG for
  and xG against. This simple historical projection is provisional, not an
  opponent-adjusted forecast or the target fixture's observed xG.
- Supporting indicators: combined goals scored >= 4.0; Over 2.5/3.5/4.5
  frequencies >= 80%/60%/35%;
  equal-weight
  average of each team's match frequency, not a sum of percentages.
- Combined mean shots on target >= 11; combined big chances >= 5; at least
  one team's projected goals >= 2.3; first-half Over 1.5 frequency >= 55%.
- BTTS >= 70% is descriptive only, never compulsory. These supporting
  indicators are not independent mandatory gates.

The projected-goals screen is required; supporting screens are reported for
review, without an overlapping-signal weighted sum.
Missing measurements remain missing (including incomplete shots/xG samples).
Probability grades are A+ >=45%, A >=35%, B >=25%, C >=15%, D <15%, separate
from Q grades. C/D are excluded. A+/A/B require positive EV = p * decimal odds
- 1, valid odds, and validated calibration. A+ can still be below 50%.

## Evidence limits and remaining research

Over 4.5 reads its qualification probability from the shared total-goals
forecast. A promoted Over 4.5 profile and a promoted shared-distribution
calibration are both required; the shared Poisson forecast alone cannot
qualify. The existing model ensemble remains recorded in the prediction and
Q-score evidence but is not the qualification probability source.
The pipeline does not yet capture a verified opponent-strength or tactical/
lineup review, so these remain explicit blockers. No matches qualify until
those evidence sources are integrated; no endpoint is provided to rubber-stamp
them. This is an implemented provisional screening gate, not a validated
five-goal prediction model. The current shared forecast is uncalibrated, so the
shared-calibration gate intentionally blocks selection.

Before enabling qualification, build point-in-time context evidence and run
rolling, chronological, multi-league/multi-season validation. Compare existing
Poisson/Dixon-Coles and ZINB with bivariate Poisson, negative-binomial and ML
challengers on held-out Brier/log loss, reliability, and priced EV/ROI with
uncertainty. Fit calibration only on earlier windows. Freeze thresholds before
the final holdout; do not tune against its outcomes. These new challengers and
rolling backtests have not been implemented or represented as validated by
this change. Zero qualifying matches is an intended outcome.
