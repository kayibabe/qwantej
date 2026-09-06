# Calibration and Uncertainty (Phase 4)

Canonical reference: [`QWANTEJ_FRAMEWORK.md`](../QWANTEJ_FRAMEWORK.md) §18–19,
§41 and Phase 4. This document defines the exact `P_raw → P_cal → P_cons`
contract implemented in `src/qwantej/calibration/`.

## Scope and production boundary

Phase 4 supplies calibrator fitting, selection, monitoring, persistence and a
versioned conservative-probability policy. These are research components. No
calibrator or haircut policy is approved for live decisions until Phase 5 runs
time-ordered walk-forward comparisons against the raw model and de-vigged
market baseline. A fitted artifact starts in `development` or `challenger`;
only governance promotion may mark it `champion`.

## Point-in-time fitting

Each binary observation contains `raw_probability`, `outcome`, `predicted_at`
and `outcome_observed_at`. Given cutoff `trained_as_of`, fitting includes only
rows whose `outcome_observed_at <= trained_as_of`. The result records how many
future outcomes were excluded. Timestamps must be timezone-aware, and an
outcome timestamp cannot precede its prediction.

Two deterministic baselines are available:

- **Platt scaling** fits `P_cal = sigmoid(intercept + slope × logit(P_raw))`
  by binary log loss.
- **Isotonic regression** fits a monotone piecewise-linear mapping, clipped to
  its endpoint probabilities outside the fitted range.

Both require two outcome classes and a configured minimum sample size. The
code default of 30 is a numerical fit floor, not promotion evidence; the model
governance target of 500+ broad predictions still applies where practical.

Calibration is applied at the market boundary. For binary markets, the
calibrator transforms the positive outcome and the negative outcome is its
exact complement. For 1X2, all three one-vs-rest calibrators are applied and
the resulting exhaustive vector is renormalized to sum to one; double chance
must then be derived from that calibrated 1X2 vector. This prevents calibration
from creating contradictions inside one market. Cross-market calibration is
still evaluated by Phase 5 and must not be represented as a calibrated
scoreline distribution unless that stronger method is implemented.

## Segment fallback

Segments may specify market, competition and model family. Calibration
selection first excludes artifacts trained after `decision_as_of`, then picks
the eligible matching artifact with the greatest number of specified segment
dimensions. If a local artifact is sparse or unavailable, callers provide an
approved broader parent candidate. If none is eligible, selection returns
`None` and the Value Gate records `CALIBRATION_UNAVAILABLE`.

## Monitoring

`calibration_report` produces Brier score, binary log loss, equal-width-bin
expected calibration error, calibration intercept/slope, reliability-curve
bins and optional Brier Skill Score against aligned reference probabilities.
Degenerate samples report no intercept/slope rather than inventing a fit.
Monitoring results are archived in append-only `calibration_snapshots` rows.

## Conservative probability policy v1

The initial auditable research policy uses:

```text
SE = sqrt(P_cal × (1 - P_cal) / n_eff)

haircut = 1.2815515655 × SE
        + 0.50 × population_std(model probabilities)
        + 0.05 × (1 - DQS / 100)
        + 0.50 × ECE
        + 0.05 × drift_score

P_cons = max(0, P_cal - haircut)
```

`drift_score` and ECE are in `[0, 1]`; DQS is in `[0, 100]`; `n_eff` is
positive. The result includes every penalty term, total uncertainty measure
and policy version so an archived decision can explain its haircut. More
uncertainty can only reduce `P_cons`, and `P_cons` can never exceed `P_cal`.

The constants are declared research defaults. Phase 5 must freeze them before
each holdout window and compare calibration, Brier/log loss, value and risk
before any promotion.

## Reproducibility

Predictions identify the concrete model run, the matching model version, a
retrievable input snapshot reference and its content hash. The database rejects
a run/version mismatch. Metadata completeness means **replay-ready**; only an
external replay that regenerates and compares the output earns
`reproducible=True`. Phase 5 owns that verification.
