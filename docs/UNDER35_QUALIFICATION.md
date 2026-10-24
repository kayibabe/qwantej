# Under 3.5 qualification v1 — provisional

Under 3.5 wins with 0–3 regulation-time goals including stoppage time. Four or
more loses. This policy uses the Under 3.5 model output and its own promoted
calibration profile, never an Under 2.5 grade/probability/profile.

Primary pool: A >=82%, A+ >=90%. B >=75% requires both verified strong
supporting evidence and an attractive-price review, in addition to every
normal evidence/value gate. C >=65% and D below65% are excluded. There is no
invented extra numerical EV margin for B. Every release needs strictly
positive p * decimal odds - 1. Grades are hypotheses, not observed hit rates.

Projected total goals <=2.5 is the provisional core screen (preferred <=2.2).
The remaining indicators are advisory: matchup-adjusted historical total <=2.7,
shots on target <=9, Under 2.5 >=55%, Under 3.5 >=80%, Under 4.5 >=90%,
Over 3.5 <=20%, Over 4.5 <=10%, BTTS <=55%, first-half Under 1.5 >=70%.
No additive score or all-thresholds-must-pass requirement is used. Missing or
out-of-range advisory metrics are visible warnings, requiring a documented
supporting-indicator review; BTTS is not compulsory.

Require 8–12 recent matches per team plus matchup/opponent adjustment,
sample-size shrinkage, longer-term league context, league and upper-tail
validation, defensive stability, controlled transitions and lineup/conditions
review. Unreviewed or flagged exceptional chances, dominant attacks against
vulnerable defences, absences, fortunate finishing, dangerous transitions,
lineup projection increases and unexplained market disagreement block release.
No arbitrary probability discount is invented for risks.

The four-or-more-goal estimate is 1 - the Under 3.5 probability and carries the
same calibration label. The independent-Poisson calculator is illustrative;
it cannot update predictions, authorize a selection or substitute for calibration.

## Integration and remaining evidence work

Applied to new model decisions, selection API views, automatic model/market
ticket pools including relaxed tiers, custom additions and frontend suggestions.
Historical saved tickets and settlements remain intact. Missing legacy evidence
fails closed. Zero qualifying selections is valid.

The current pipeline stores raw venue history descriptively. It has no verified
matchup-adjusted feature source, shrinkage/context/risk review or separate
upper-tail validation artifact. Qualification reads Under 3.5 from the shared
eight-market forecast, but the current Poisson distribution is uncalibrated.
The shared and market-specific calibration gates intentionally keep selections
blocked. Existing ensemble outputs remain stored for prediction/Q-score
analysis. No synthetic evidence or calibrated-performance claim is introduced.

Before enabling releases, compare Poisson/DC, bivariate Poisson, negative-binomial,
xG regression and gradient-boosting challengers on chronological held-out
fixtures across leagues/seasons, fit calibration only on earlier windows,
and evaluate four/five-plus tail reliability, Brier/log loss and priced returns.
Freeze screening rules before the final holdout. These experiments and a new
performance-monitoring pipeline are not implemented by this policy change.
