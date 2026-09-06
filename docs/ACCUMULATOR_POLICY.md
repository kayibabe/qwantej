# Accumulator Policy

Canonical reference: [`QWANTEJ_FRAMEWORK.md`](QWANTEJ_FRAMEWORK.md) Part VII
and Appendix A. Governs `src/qwantej/accumulator/`.

## Products

| Product | Combined odds | Typical legs | Purpose | Default quality stance |
| --- | --- | --- | --- | --- |
| CORE | 3.00–5.00 | 3–4 | Flagship; highest-quality daily accumulator | Highest QSS/reliability, lower volatility |
| GROWTH | >5.00–10.00 | 4–6 | Balanced risk/reward | Strong screening; broader pool without quality dilution |
| ALPHA | >10.00–20.00 (operating band) | 5–7 | Higher-variance opportunity built from qualified legs | Higher odds mainly through more good legs, not weak markets |

The UI may display "10.0+" for Alpha, but the internal operating band is
capped around 20.00. Any 20+ entertainment product is a separate
Jackpot/experimental product, excluded from core investment-performance
KPIs. **No ticket is mandatory** — `NO QUALIFIED ACCA` is an expected
operational result, not a failure.

## Initial policy thresholds (research defaults — must be backtested)

| Policy | Core | Growth | Alpha |
| --- | --- | --- | --- |
| Combined odds | 3.00–5.00 | >5.00–10.00 | >10.00–20.00 |
| Typical legs | 3–4 | 4–6 | 5–7 |
| Preferred QSS | ≥87 | ≥85 | ≥82 |
| Hard QSS floor | ≥82 unless research-only | ≥82 | ≥82 |
| DQS | Prefer ≥80; hard floor 70 | Prefer ≥80; hard floor 70 | Prefer ≥80; hard floor 70 |
| League/market state | Qualified | Qualified; limited Watch only if policy explicitly allows | Qualified only initially |
| Same fixture | Max 1 leg | Max 1 leg | Max 1 leg |
| Same league | Max 2 initial | Max 2 initial | Max 2 initial |
| Same market family | Max 3 initial | Max 3 initial | Max 3 initial |
| Stake priority | Highest | Medium | Lowest |
| No-bet behaviour | Allowed / expected | Allowed / expected | Allowed / expected |

## Core constraints (framework §30)

- Maximum **one** selection from any fixture in a standard accumulator.
- Never add a leg solely to reach a target price.
- Never reduce QSS, DQS, EV or reliability thresholds because the daily
  ticket is otherwise unavailable.
- No blacklisted league-market segment.
- Maximum legs by product, unless a backtested policy revision approves
  otherwise.
- No more than two legs from one league (initial policy, subject to
  validation).
- No more than three legs from the same market family (initial policy,
  subject to validation).
- Enforce price freshness at lock time.
- Each ticket must remain positive under its conservative probability
  estimate and stress haircut.

## Dependence and covariance control (framework §31–32)

`P_ticket = Π P_i` (independence baseline) is a **benchmark only** — it is
not a claim of true joint probability. One-selection-per-fixture removes
direct same-match dependence but not systemic dependence across matches
(league style, weather systems, schedule effects, correlated model/provider
errors, common market factors).

| Stage | Method | Use |
| --- | --- | --- |
| Baseline | Independent product of conservative leg probabilities | Transparent benchmark only |
| Immediate production control | Concentration constraints + dependence penalty matrix | Block/penalise same league/market/time/weather clusters |
| Empirical upgrade | Residual outcome correlation/covariance matrix by market and competition group | Quantify shared forecast error after conditioning on predicted probabilities |
| Advanced research | Scenario simulation / copula / hierarchical latent-factor model | Portfolio/ticket joint risk once sample size supports it |

Until empirical covariance is stable, use conservative proxy penalties and
hard diversification limits — do not invent precise correlation
coefficients.

## Optimiser objective (framework §33)

Not "maximise combined odds." Approximately:

```
maximise: Robust EV + Quality + Reliability + Diversification
          − Uncertainty − Dependence − Execution Risk − Drawdown Risk
```

subject to product odds band, quality, value, diversification, dependence,
execution and drawdown constraints. Prefer an auditable exhaustive/beam
search over a sophisticated black-box solver for the initial
implementation.

## Ticket lifecycle (framework §47)

`Draft → Qualified → Published → Odds Changed → Requalified/Withdrawn →
Locked → Live → Won/Lost/Partial/Void → Settled → Learning Archive`

If a leg's odds move materially before lock, the optimiser re-evaluates
ticket EV and constraints. If the executable price falls below minimum
value, the leg is removed or the ticket withdrawn — the UI must never
preserve a stale "value" label.

## Candidate funnel (framework §28)

```
All markets analysed
  → Statistically valid markets
  → DQS pass
  → Calibrated and uncertainty-adjusted
  → Positive conservative value
  → Reliability pass
  → QSS pass
  → Dependence-compatible candidate pool
  → Optimised ticket or NO QUALIFIED ACCA
```

See `DATA_DICTIONARY.md` for the rejection reason taxonomy every failed gate
must record.
