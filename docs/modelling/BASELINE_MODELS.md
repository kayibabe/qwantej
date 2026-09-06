# Baseline Probability Models (Phase 3)

Canonical reference: [`QWANTEJ_FRAMEWORK.md`](../QWANTEJ_FRAMEWORK.md) §14-21,
§50 (Phase 3). Functional specification for the baseline prediction engine in
`src/qwantej/models/` and `src/qwantej/markets/`.

These four families are the **transparent anchors** every later model must
beat to prove incremental value (framework §15). They are pure functions of
their rate/rating/odds inputs — no data access — so a prediction is a
deterministic function of its inputs. Estimating those inputs from data
(attack/defence strengths, ρ, ratings) and the leakage-safety of that
estimation belong to the feature/backtesting layer (Phase 5); the leakage
surface here is therefore nil by construction.

All models emit the validated result types in `qwantej.models.probabilities`
(`MatchResultProbs`, `DoubleChanceProbs`, `BinaryProbs`) — raw model
probabilities (P_raw, framework §19). Calibration and the conservative haircut
are Phase 4.

## Coherent scoreline core — `models/scoreline.py`

`ScorelineDistribution` holds a full `P(home=i, away=j)` matrix (non-negative,
sums to 1). **Every** goal market is derived from this one distribution, so
1X2, double chance, totals, BTTS and team totals are internally coherent
(framework §15):

| Market | Derivation |
| --- | --- |
| 1X2 | home = Σ_{i>j}, draw = Σ_{i=j}, away = Σ_{i<j} |
| Double chance | unions of the 1X2 outcomes |
| Over/Under `L` | Σ over cells with `i + j > L` (half-lines only — a whole line allows a push) |
| BTTS | Σ over `i ≥ 1 and j ≥ 1` |
| Team over `L` | Σ over that team's goals `> L` |

## Poisson — `models/poisson/model.py`

Independent Poisson: `P(i,j) = Pois(i; home_xg) · Pois(j; away_xg)`, truncated at
`max_goals` (default 10) and renormalised to 1. The lost tail mass is retained
as `truncated_mass` for the §15 sanity check (< 1e-6 at default rates). This is
the diagnostic benchmark.

## Dixon–Coles — `models/poisson/model.py`

Poisson with the low-score dependence correction on the four lowest scorelines:

```
τ(0,0) = 1 − home_xg·away_xg·ρ    τ(0,1) = 1 + home_xg·ρ
τ(1,0) = 1 + away_xg·ρ            τ(1,1) = 1 − ρ
```

`P(i,j) = τ(i,j)·Pois(i)·Pois(j)`, renormalised. **`ρ = 0` recovers independent
Poisson exactly** (the incremental-value benchmark). A small negative ρ lifts
the 0-0 and overall draw probability. A ρ extreme enough to drive any adjusted
cell negative is rejected, not clamped. Default `ρ = −0.05` is a research
default and must be fitted per league/season.

## Elo — `models/elo/model.py`

- `expected_score`: classic Elo win expectation, `1 / (1 + 10^(−d/400))` with
  `d = home_rating + home_advantage − away_rating`.
- `result_probabilities`: 1X2 via an **ordered-logistic draw band**. With latent
  home strength `z = d / scale` and symmetric cutpoints `±draw_width`:
  `P(home) = σ(z − w)`, `P(away) = σ(−z − w)`, `P(draw) = 1 − P(home) − P(away)`.
  Always non-negative, always sums to 1, symmetric under swapping the teams.
- `update_ratings`: `R' = R ± K·(S − E)`, zero-sum. Margin-of-victory scaling is
  a documented later extension.

Research defaults: `K = 20`, `home_advantage = 65`, `scale = 400/ln 10`,
`draw_width = 0.55` (≈ 0.27 draw probability for even teams).

## Market baseline — `markets/devig.py` + `models/market.py`

Bookmaker odds de-vigged into a fair-probability benchmark (framework §20). Raw
implied `p = 1/odds` carries the margin (overround = Σ p); two documented
baseline methods remove it:

- **proportional** (default): `fair_i = p_i / overround` — always valid.
- **additive**: subtract `(overround − 1)/n` from each; refused (not clamped) if
  it drives any outcome non-positive.

`models/market.py` wraps this into `MatchResultProbs` / per-selection maps so the
ensemble consumes the market like any other model — used as a benchmark and,
under a governance policy that prevents simply reproducing the bookmaker
(framework §17), as a possible blend component. Shin, cross-book consensus, line
movement and CLV are deferred to Phase 5.

## Definition of Done status (framework §51)

Done: functional spec (this doc), I/O types, unit tests covering normal /
boundary / failure cases, numerical sanity vs closed-form baselines, coherence
(distributions sum to 1), `ρ = 0` identity. Deferred to their own phases:
calibration metrics (Phase 4); walk-forward backtest and the data-side leakage
test (Phase 5) — the models themselves are pure and data-free.
