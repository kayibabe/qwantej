# Under 0.5 qualification v1 — provisional

Only regulation-time 0–0 wins, including stoppage time; any goal loses.
Under 0.5 remains in TARGET_MARKETS with its own ensemble output, while
qualification now reads the exact-zero event from the shared eight-market
forecast. The current Poisson forecast is uncalibrated and the shared and
exact-zero calibration gates block release. Future model runs retain rejected forecasts and reasons;
refreshing the app does not run models or publish new selections.

Primary shortlist: A >=30%, A+ >=40%. B >=22% requires explicit conditional
value review; C >=15% and D <15% are excluded. At 40%, loss risk is still 60%.
Every release needs valid odds, positive ordinary EV and positive stressed EV.

The initial stress test subtracts **five absolute percentage points**, floored
at zero. This is a transparent provisional scenario, not a confidence bound or
empirically calibrated uncertainty allowance. Validation is required before
releasing signals. At p=.35 and odds=3.20, EV is +12% but stressed EV is -4%:
reject. At odds=3.50 the stressed EV is +5%. Repricing in accumulator analysis
rechecks stressed EV using the displayed quote, not the original snapshot price.

All numeric indicators are advisory: projected total <=1.2 (ideal <=.9), home
and away <=.7, contextualised 0–0 >=20%, Under 1.5 >=55%, Under 2.5 >=80%, shots
on target <=5, big chances <=2, BTTS <=25%, first-half 0–0 >=45%. Do not sum
overlapping indicators or require every threshold to pass. A .8–.2 projection
can pass. Supplied component projections must agree with their total.

Use 10–15 recent comparable venue matches per team, separate from the other
engines' 8–12 samples, plus long-term context, opponent adjustment and shrinkage.
Require both-team clean-sheet evidence, limited chance creation, defensive
stability, measured low-event tactics, lineup and uncertainty review. Flagged
or missing reviews of attacking favourites, absences, finishing slumps, early
goals/penalties/set pieces, transitions, exceptional goalkeeping, attacking
incentives and unreliable samples block release. Head-to-head 0–0 is not a
major model feature. No forced daily minimum or relaxation bypass.

## Current limits and required validation

Venue history is stored descriptively; verified adjusted features, exact-zero
calibration, risk/context evidence and uncertainty validation are not yet
integrated. Qualification therefore remains blocked. The existing Poisson/DC,
Bayesian, xG and conditional ZINB components remain; this change does not invent
or validate new bivariate/zero-inflated/hierarchical/ML experiments.

The independent-Poisson calculator is illustrative, cannot change a prediction
or qualification, and shows p(0–0), p(1+), fair odds, quoted implied probability,
edge, EV and stressed EV. Quoted implied probability includes bookmaker margin.

Before release, run chronological train/validation/unseen-test experiments,
validate exact-zero reliability against de-vigged market baselines, and record
predicted versus actual 0–0, Brier/log loss, ROI, closing-line value, drawdown and
league/season performance. Closing-line metrics require actual recorded closing
quotes. Expanded performance monitoring and new challenger comparisons remain
unimplemented research; no historical profitability or external study claim is
asserted here. Existing saved tickets and settlements are not rewritten.
