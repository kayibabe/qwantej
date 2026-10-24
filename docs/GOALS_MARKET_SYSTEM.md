# Shared total-goals forecast and qualification policies

## Design

The eight supported Over/Under markets consume one point-in-time forecast per
match: Under 0.5, Over/Under 1.5, Over/Under 2.5, Over/Under 3.5 and Over 4.5.
The forecast carries a shared ID, match/model-run identity, version, timestamp,
the projected home/away goals, all eight event probabilities and probability
coherence checks. Every qualification assessment embeds this same object.

For each available pair, Over and Under probabilities are exact complements.
Over probabilities decrease as the line rises; Under probabilities increase.
The markets retain separate grade cutoffs, indicator screens, risk reviews,
odds and expected-value calculations. They do not re-fit or silently adjust
their own probability inside qualification.

## Current probability source and release state

The shared object starts from the saved, pre-match expected-goals proxy and
derives an independent-Poisson event vector. The model-learning run now also
fits a single total-goals rate scale from earlier finished fixtures, using only
their saved pre-match expected-goals snapshots. It evaluates that scale on a
later untouched period. Every event probability is regenerated from the same
scaled distribution, so complements and line ordering remain intact. This is
an initial calibration layer; it does not establish opponent-adjusted team
rates, overdispersion, home/away score correlation, or a joint scoreline model.

The existing Poisson/Dixon-Coles, ZINB, Bayesian and xG ensemble outputs remain
stored for model and Q-score evidence. The shared forecast supplies the
qualification probability. Qualification requires both the market's existing
promoted calibration evidence and a shared forecast calibration artifact with
all of these checks true:

- `brier_improved`
- `calibration_not_worse`
- `enough_priced_bets`
- `probability_ordering`
- `positive_roi_evidence`
- `roi_not_worse`
- `chronological_holdout_passed`
- `market_brier_not_worse` for every shared event
- `market_calibration_not_worse` for every shared event

The normal model-learning run writes a `MarketLearningProfile` with market
`shared_total_goals`. It records the fitted mean scale, train/holdout metrics,
sample counts, and all shared checks. The profile becomes usable only after the
learning run passes its holdout and receives the existing explicit promotion.
When activated, the shared calibration is applied once before the eight market
assessments. A missing/insufficient/rejected profile leaves the forecast
uncalibrated and every policy rejects. Each market's independent promoted
profile and evidence gates still apply after shared calibration.

The historical data currently available in the local database is not enough to
release selections: as of 2026-10-24, 535 finished fixtures have saved
pre-match expected-goals snapshots across roughly 11 days, none has a persisted
shared-forecast snapshot, and existing Over/Under market-learning profiles are
`insufficient_evidence` or `validation_rejected`. There is no historical
Under 0.5 market profile. Training a shared candidate from these records can
produce a holdout report, but it must not be treated as qualification or
promoted unless all checks pass; the separate market gates may still block it.

A read-only dry run on model version `0.3.0` used 2026-10-13–19 for training
(296 fixtures) and 2026-10-20–24 for validation (239 fixtures). The fitted rate
scale was `1.07261594`. Holdout Brier changed from `0.177625` to `0.175885`,
short of the required `0.0025` improvement; calibration worsened for at least
one event; and the candidate ROI was `0.018932` with a 95% cluster-bootstrap
interval of `[-0.180732, 0.216412]`. The profile therefore failed promotion.
This dry run did not write a learning record or activate a profile. Since this
holdout has now been inspected, use a later untouched period for any release
decision rather than tuning against these dates.

## Next validation work

Keep collecting point-in-time forecast snapshots and settled results. Compare
the calibrated Poisson candidate against Poisson/Dixon-Coles and suitable
overdispersed or correlated goal models on longer chronological league/season
splits. Retain the full probability mass over goals (and later a joint scoreline
distribution for BTTS/scoreline features). Expand validation to include
reliability by league/season, de-vigged market comparisons and closing-line
value on frozen holdouts.

Promote the shared calibration only after its checks pass. Continue to apply
the separate market policy and price gates after promotion. Rejected forecasts
should remain available for evaluation, and no minimum number of daily picks
should be introduced.
