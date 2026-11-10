# Calibration and policy decision — 2026-11-10

## Question

At Q ≥ 75 the model is badly overconfident (predicted 77.0%, observed 57.4%).
Should the whole model be overhauled?

## Short answer

**No — not yet.** The evidence says the model has no demonstrated information
beyond the bookmaker's price, and that is not something a new model design
fixes by assertion. Overhauling now would spend effort on an unvalidated
premise. Fix the measurement and decision layers first, freeze a policy, and
only rebuild base models against a market-relative benchmark.

## Evidence

Two audits, both reproduced in this repository:

1. `research/market-sweet-spot-2026-11-10/first/` — Q ≥ 75 market/filter grid,
   3,080 first pre-kickoff picks over 45 matchdays.
   - Overall ROI -1.6%; no cell survived a within-market permutation test
     (best cell +45.4% vs null median +113.5%, p = 0.97).
   - Double chance was the reproducible loser (`x2` -7.8% over 491 picks,
     `1x` -12.9% over 151).
   - No cell was positive in both train and test with a bootstrap lower bound
     above zero.

2. `research/calibration-audit-2026-11-10/` — expanding-window walk-forward on
   25,095 out-of-sample picks, refitting Platt/isotonic every matchday.
   - All picks: raw 48.0%, observed 47.9%, ECE 6.0pp. Isotonic cuts ECE to
     1.1pp and Brier by 4.7%, but the bookmaker is still better (0.199 vs
     0.208).
   - Q ≥ 75: raw 77.0%, observed 57.4%, isotonic 65.7%, implied 60.0%.
     Isotonic improves Brier 0.257 → 0.230, but implied is 0.212.
   - `outcome ~ logit(implied) + logit(model)`, days clustered: model
     coefficient **0.003** (95% CI -0.107 to 0.110) on all picks and
     **-0.104** (-0.459 to 0.232) at Q ≥ 75. No positive information beyond
     price.
   - Calibrated edge remains anti-predictive: at Q ≥ 75, calibrated edge
     20pp+ returned -6.0% ROI; edge ≤ 0 returned 0.0%.

Interpretation:

- The level problem is real and partly fixable (isotonic).
- The ordering problem is not fixed by calibration: the model is still worse
  than the price after recalibration. That is a model-information problem, not
  a formatting problem.
- Q ≥ 75 selects on a score that is 25% raw probability and 20% clipped raw
  edge. Both inputs are miscalibrated/anti-predictive, so Q amplifies the
  error rather than measuring value.

## Decision

Three layers, in order. Do not skip ahead.

### 1. Decision layer (now, reversible)

- Q and `edge` are **not** value or ranking signals.
- Exclude double chance (`double_chance_1x`, `double_chance_12`,
  `double_chance_x2`) and the high overs (`over_3.5`, `over_4.5`), plus
  `under_0.5` / `under_1.5` on sample-size grounds.
- Rank by bookmaker-implied probability, not model edge.
- One pick per fixture.
- CLV is a forward validation gate, never a live filter.

Implemented as a frozen paper rule, not a live change:
`policy-q75-nodc-v1` in `backend/app/services/paper_rules.py`.

Protocol:

| Field | Value |
| --- | --- |
| markets | away_win, btts_no, over_1.5, under_2.5, under_3.5 |
| excluded | double_chance_1x/12/x2, over_3.5, over_4.5, under_0.5, under_1.5 |
| Q | ≥ 75, universe filter only |
| odds | 1.50 ≤ odds < 8.00 |
| selection | highest implied probability, then earliest prediction, one per fixture |
| quote | pre-kickoff, ≤ 3 hours old, provenance required |
| stake | flat 1 unit, paper only |
| start | 2026-11-11 |
| review | ≥ 300 settled, ≥ 30 matchdays, and CLV gate (mean CLV > 0, beat-close > 50%) |

The ledger stores closing odds and CLV on settlement, and `review_due` now
requires the CLV gate for rules that declare `requires_positive_clv`.

### 2. Calibration layer (next, still research)

- The per-market Platt calibrator exists but has never been applied: **0
  predictions have a learning_profile_id**, and every stored profile is
  `insufficient_evidence` or `validation_rejected` (32 training rows).
- Rebuild the learning loop so it fits walk-forward, not on the evaluation
  window, and gate promotion on out-of-sample Brier/log-loss versus the
  bookmaker, not just versus the raw model.
- Do not promote isotonic on the same rows it was fitted on. The audit shows
  the honest gain is real but modest, and does not create an edge.

### 3. Model layer (only if it earns it)

A rebuild is justified only when a challenger clears all of:

1. Out-of-sample log-loss/Brier **better than bookmaker implied** on the same
   fixtures and entry prices, by market and pooled.
2. Positive coefficient on `logit(model)` in the market-relative regression,
   with a day-cluster interval excluding zero.
3. Positive mean CLV and beat-close > 50% in a frozen prospective window.
4. The improvement survives excluding double chance and the high overs.

Until then, new features/models are research, not a production justification.

## What not to do

- Do not remove the probability weight from Q and call it a fix. Q still
  selects on an uncalibrated score; the audit tests information, not cosmetics.
- Do not promote any market because its raw ROI is positive in this sample.
- Do not use isotonic fitted on the full history as if it were prospective
  evidence.
- Do not treat the page's "Settled picks in this view" as a strategy backtest.

## Reproduction

```
# market/filter grid
python /tmp/market_sweet_spot_backtest.py --selection first --output <dir> --permutations 200

# calibration walk-forward
python /tmp/calibration_walk_forward.py --output <dir>
```

Both scripts live in `backend/scripts/` and are read-only against the database.
