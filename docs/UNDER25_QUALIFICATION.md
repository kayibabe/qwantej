# Under 2.5 qualification v1 — provisional

Regulation time plus stoppage time, zero to two goals. Three or more loses;
extra time/shootouts are excluded by the existing settlement convention.

Primary pool: probability >=72% (A >=72%, A+ >=80%). B >=65% is conditional
research only; C >=55% and D <55% are excluded. All candidates need strictly
positive EV, valid decimal odds, approved calibration and complete evidence.

Required screens: projected xG <=2.0 (preferred <=1.8, ideal <=1.7), adjusted
scored <=2.2, conceded <=2.0, Under 2.5 >=70%, Under 3.5 >=85%, Over 3.5 <=15%,
shots on target <=7, BTTS Yes <=40%, first-half Under 1.5 >=80%. Use 8–12 recent
games per team with venue weighting. Frequency and goal inputs must have
opponent/sample weighting and matchup adjustment; raw sums are not substitutes.
Under/Over 3.5 screens are complementary checks, never independent score boosts.

Require reviewed defensive stability, chance quality, controlled tempo,
league validation and adjustment provenance. Flagged or unreviewed defensive
absences, finishing slumps, attacking mismatches, transitions, aggressive
lineups, unexplained market disagreement and second-half escalation block
release. No arbitrary numerical probability haircut is invented for risks.

The policy is enforced on model recommendations, both automatic pricing modes,
relaxation tiers and custom accumulator additions. Existing tickets/results
are not rewritten. Legacy predictions without evidence fail closed. The UI
shows the evidence and a separate interactive Poisson calculator, which cannot
change qualification or create a signal.

## Current evidence limitation

The existing venue history is retained descriptively. This change does not
pretend it is matchup-adjusted, opponent-weighted data. The pipeline currently
has no verified adjusted-feature/context/risk-review source, so new Under 2.5
signals remain blocked. An active promoted Platt profile with all existing
promotion checks is required but does not replace league-specific validation.
The current ensemble, including Poisson/Dixon–Coles, remains stored for
prediction/Q-score analysis. Qualification now reads Under 2.5 from the shared
eight-market forecast. Its independent-Poisson probabilities are uncalibrated;
a shared calibration and the existing Under 2.5 validation gate must both pass
before a selection can qualify.

## Validation work still required

Integrate point-in-time adjusted features and measured tactical/lineup risks.
Compare Poisson/DC, bivariate Poisson, negative-binomial, xG regression and ML
challengers using chronological rolling splits across leagues/seasons; fit
calibration on earlier windows only, freeze policy before final holdout.

Monitor Brier/log loss, reliability, grade hit rate, ROI, closing-line value,
margin, maximum drawdown and losing streaks by league, grade, month, season
and model version. Closing-price metrics require recorded closing quotes;
never substitute current or original quotes for missing closes. This change
does not implement those new model comparisons or a closing-price monitoring
pipeline, nor claim a successful historical backtest. Zero qualifiers is valid.
