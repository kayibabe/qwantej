# Under 1.5 qualification v1 — provisional

Only 0–0, 1–0 and 0–1 win in regulation time including stoppage time.
Two goals, including 1–1 or 2–0, lose. Extra time/shootouts are excluded.

Under 1.5 is now in TARGET_MARKETS; existing Poisson/DC, Bayesian, xG and
conditional ZINB paths support total-goal scoring. New runs retain predictions
and rejection reasons even when no selection qualifies. No historical
prediction is fabricated or filled retrospectively.

Primary grades: A >=70%, A+ >=80%. B >=60% needs a verified compelling-value
review; C >=45% and D <45% are excluded. All releases require strictly positive
EV, valid prices and market-specific promoted calibration. No extra numerical
EV margin is invented for B, and high probability does not imply profitability.

Required provisional screens: projected total <=1.2 (preferred <=1.0, ideal
<=0.9), contextualised Under 1.5/2.5/3.5 >=55%/80%/90%, combined shots on target
<=5, BTTS <=25%, first-half Under 0.5 >=45%, first-half Under 1.5 >=85%.
Home <=0.7 and away <=0.6 are advisory, not independent hard limits. A 0.9–0.2
projection can pass; supplied components must agree with their combined total.

Use 8–12 recent comparable venue matches per team plus longer-term context,
opponent assessment and league shrinkage. Require low chance creation,
compact defence, measured tempo, lineup/conditions review and explicit
penalty/red-card/tactical uncertainty assessment. Unreviewed or flagged high
scoring rates, high xG despite low scores, absences, early concessions,
transitions/box entries, weak samples, market disagreement or aggressive
lineups block release. No daily minimum or relaxation bypass is allowed.

## Probability sources

Qualification reads Under 1.5 from the shared eight-market total-goals
forecast. Over 1.5 is its exact complement, and every supported Over/Under
pair is derived from the same stored forecast. The current shared Poisson
forecast is uncalibrated and cannot qualify a selection. A shared distribution
calibration must pass before release; the existing ensemble output remains
stored for prediction and Q-score analysis. The fitted
Poisson/DC component's P(0–0) and P(exactly one goal) are recorded separately
where available, explicitly uncalibrated; they are not forced to sum to the
calibrated ensemble output. The UI's independent-Poisson calculator additionally
shows P(1–0) and P(0–1), clearly illustrative, and cannot change qualification.

## Evidence and research still needed

Current venue history is retained descriptively. Verified adjusted metrics,
context/risk reviews, shrinkage and low-score calibration validation are not
yet integrated, so qualification stays blocked rather than assuming evidence.
The existing ensemble remains in use; this change does not add or validate
bivariate Poisson, hierarchical/gradient-boosting challengers or new regressions.

Before releasing signals, use chronological train/validation/unseen-test periods,
compare against de-vigged bookmaker baselines, validate 0–0 versus exactly-one
probabilities and monitor Brier/log loss, probability-band calibration, ROI,
closing-line value and league/venue performance. Closing-line metrics require
actual closing quotes, not replacements. Rejected predictions are retained for
policy evaluation. New model comparisons and expanded monitoring remain work
to implement; no historical profitability or published study claim is asserted.

The policy gates selection API views, automatic pricing/relaxation paths and
custom additions. Existing saved tickets/results are not rewritten. The app
refresh alone does not run the scoring pipeline or publish new selections.
