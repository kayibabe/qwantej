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
KPIs. **No value ticket is mandatory** — `NO QUALIFIED ACCA` is an expected
operational result, not a failure. The daily minimum is met by the separate
Daily Picks line below, not by these products.

## Daily Picks — guaranteed minimum (separate product line)

Owner decision (2026-09-23): the platform publishes **at least three tickets
per UTC day**. The value products above stay exactly as strict as before —
their thresholds are never relaxed to fill the quota. Instead, a separate
**Daily Picks** line (`daily_safe`, `daily_balanced`, `daily_bold`;
`src/qwantej/accumulator/daily.py`, `backend/services/daily_tickets.py`)
tops the day up:

| Product | Preferred shape (rung 0) | Relaxed (rung 1) | Last resort (rung 2) |
| --- | --- | --- | --- |
| DAILY SAFE | 2–3 legs, 1.80–3.50, legs 1.15–1.80, maximise hit probability | 2–3 legs, 1.60–4.50 | 2–5 legs, 1.25–30.00, any leg 1.03–6.00 |
| DAILY BALANCED | 3–4 legs, 3.00–6.00, legs 1.25–2.30, maximise expected return | 2–4 legs, 2.50–8.00 | same shared last resort |
| DAILY BOLD | 4–5 legs, 6.00–15.00, legs 1.35–3.20, maximise expected return | 3–5 legs, 4.50–20.00 | same shared last resort |
| Max quote age | 3 h | 8 h | 26 h |

- **Not value-qualified**, labelled as such in the UI; the system recommends
  **no stake** for them (real money you choose to place is recorded separately
  as a real bet). Leg probability is the model's calibrated probability shrunk 50/50
  towards the de-vigged market (`MODEL_WEIGHT`, research default).
- Legs come only from **archived** forecasts (production preferred, research
  stream otherwise — so unvalidated leagues *can* appear here, never on a
  value ticket), re-priced against the freshest coherent bookmaker snapshot.
  The pull accepts archived 1X2 home/draw/away and BTTS yes/no forecasts with
  complete same-bookmaker quotes. It does not synthesize missing forecasts or
  force market diversity; the live signal pipeline currently archives home 1X2.
  Totals remain excluded because the ticket leg does not retain a totals line.
  DQS < 60 (framework REJECT band) is never used. One leg per fixture across
  all tickets; a prediction backs at most one ticket.
- Built once per UTC day from `DAILY_TICKET_BUILD_HOUR_UTC` (default 06),
  idempotently topped up hourly; 30 h lookahead, 72 h fallback. Earlier
  products never take legs a later product needs to exist.
- Every ticket records the rung it was built at (`policy_version`). A day the
  slate cannot support even the last resort is a logged **SHORTFALL** with a
  Telegram alert — never a silently invented ticket.
- Daily Picks must be excluded from value-product KPIs and from
  ticket-settlement ROI claims for CORE/GROWTH/ALPHA (filter `daily_*`); the
  Performance page reports every product on its own row for this reason.

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

### Match result visibility and recovery

- Accumulator legs show each fixture's pending, live, won, lost, or void
  state alongside the latest available score. For live fixtures, retain the
  provider's period and elapsed-minute fields when present.
- Ticket fixtures continue refreshing for three days after kickoff. Live and
  near-kickoff fixtures refresh every two minutes; scheduled fixtures more
  than three hours overdue back off to fifteen minutes while unresolved.
- If the canonical fixture remains scheduled and the latest provider snapshot
  still reports `NS`/`TBD` at least three hours after kickoff, show
  `RESULT DATA STALE`; do not infer a score or settle a ticket from elapsed
  time alone.
- A human-reviewed external result can be ingested only with a public HTTPS
  evidence URL. The application appends its source snapshot and audit event,
  then uses the normal settlement worker. Existing settled history is never
  rewritten; a conflicting settled result requires the governed correction
  path.

## Ticket settlement and results by product and period

A ticket's result is always derived from its legs' effective
(non-superseded) settlements with one rule,
`derive_ticket_result` in `src/qwantej/performance/accumulator_results.py`,
shared by the settlement worker, the ticket archive
(`GET /accumulators` → `result`) and the results calendar
(`GET /performance/accumulator-results`; UI: *Tickets* and
*Performance → By period*):

- any leg lost → **lost** (even while other legs are still open);
- otherwise any leg unsettled → **pending**;
- otherwise every leg void/push → **void**; else → **won** (void/push legs
  drop out, the standard bookmaker treatment);
- a ticket whose own status is `void` is **void**.

Both also report the flat one-unit P&L from `flat_unit_profit` (same
module): settlement odds − 1 for a win, −1 for a loss, 0 for a void, nothing
while pending. The results calendar sums it per product and period
(`profit_units`), which is the P&L shown on each year, month and day heading
of the *Tickets* page.

**Automatic ticket settlement** (`backend/services/ticket_settlement.py`,
run by the settlement worker every pass). The moment a ticket's result is
decided — the first lost leg, or every leg settled — the worker appends an
`accumulator` `Settlement` row and moves the ticket's status to `settled`:

- settlement price: a won ticket pays the product of its **winning** legs'
  odds (void/push legs drop out); a lost ticket is recorded at its full
  published odds; a void ticket has no price;
- `taken_probability` is the ticket's conservative joint probability, so
  ticket Brier scores are measurable;
- settlements stay append-only: if a leg settlement is later corrected and
  the derived result or price changes (within 30 days of publication), a
  correcting row supersedes the previous ticket settlement
  (`LEG_SETTLEMENT_CORRECTED`);
- status `void` stays reserved for administratively voided tickets; a
  ticket whose legs all voided is `settled` with a `void` outcome.

Legs on **cancelled or abandoned** fixtures settle as void
(`FIXTURE_CANCELLED`) so their tickets can close. The worker settles any
finished fixture up to 30 days back, and open tickets' fixtures are polled
for results for up to 60 days (every 2 min live, every 15 min once overdue,
every 6 h after a day), so a late result from the feed is never stranded.

**ROI.** With no recorded stakes, KPIs use a **flat one-unit stake** per
priced ticket or selection (`stake_basis: "flat_unit"`): win = odds − 1,
loss = −1, void = 0 and excluded from turnover. ROI, P&L, drawdown and
volatility all use that one series. Unpriced rows are excluded from every
financial figure. Real money placed on tickets is tracked separately in
the bankroll currency (`/real-bets`, `/real-bets/summary`) and shown on
the Performance page beside the 1-unit figures.

Results are counted per product and grouped by the ticket's publication
date in the **Africa/Blantyre product day** — the same calendar as the
Today page and `/accumulators?date=` — at year / month / day granularity.
Win rate is won ÷ (won + lost). Daily Picks are reported as their own
products (`daily_pick: true`) and never merged into the value products'
counts.

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
