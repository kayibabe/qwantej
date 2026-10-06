# Individual-Leg Analysis Excluding `daily_bold`

**Scope:** production PostgreSQL, `daily_safe` and `daily_balanced` only.
**Snapshot:** queried 2026-10-06; latest persisted settlement was
2026-10-06 17:19:57 UTC. All queries were read-only.

## Executive finding

The remaining individual legs look positive on this small paper sample, but the
evidence quality is not strong enough for a staking decision. The central risks
are price provenance, quote freshness, model lineage, and extreme market
concentration:

- 34 published leg occurrences: 31 settled and 3 pending.
- Settled legs: 22 wins and 9 losses; 70.97% hit rate.
- Flat one-unit leg P/L: +5.950 units.
- All 34 legs are `1X2 / home`; there is no cross-market validation.
- 22/34 legs were more than three hours old at ticket publication, despite the
  Daily Picks code and policy defining a three-hour maximum quote age.
- 21/34 legs have no bookmaker recorded.
- Only 13/34 legs have prediction-level executable odds and fair-market
  probability fields.
- 0/31 settled legs have closing odds or CLV.
- All 31 settled legs use model version `1.0.0-shadow-unknown`; the three
  pending legs use `1.0.0`.
- LRS and MRS are missing for all 34 legs. QSS and DQS are present but only
  occupy the 50–79 range.

The positive result is therefore **Verified as a paper settlement calculation**
but **Untested as executable betting evidence**.

## Product and ticket inventory

| Product | Tickets | Legs | Settled wins | Settled losses | Pending legs | Flat leg P/L |
|---|---:|---:|---:|---:|---:|---:|
| `daily_safe` | 7 | 14 | 12 | 2 | 0 | +3.090 |
| `daily_balanced` | 8 | 20 | 10 | 7 | 3 | +2.860 |
| **Total** | **15** | **34** | **22** | **9** | **3** | **+5.950** |

At ticket level, the non-Bold products have 8 wins and 6 losses across 14
settled tickets. Flat ticket P/L is +10.946 units. This remains paper-only and
is heavily sensitive to the few high-price winning tickets.

## Predictive quality and calibration

| Metric | Settled legs |
|---|---:|
| Sample | 31 |
| Wins / losses | 22 / 9 |
| Hit rate | 70.97% |
| Mean conservative probability | 61.92% |
| Actual rate minus mean probability | +8.05 pp |
| Brier score | 0.1925 |
| Log loss | 0.5709 |
| Mean stored edge | 6.21 pp |

The positive calibration gap is not enough to claim under-confidence: the sample
has only 31 settled legs, is selected, and is entirely one market/selection.

### Probability bands

The `n` column includes pending legs; rates use settled legs only.

| Conservative probability | n | Wins | Losses | Pending | Mean p | Actual rate | Brier |
|---|---:|---:|---:|---:|---:|---:|---:|
| `<55%` | 6 | 3 | 2 | 1 | 49.94% | 60.00% | 0.2038 |
| `55–60%` | 10 | 6 | 3 | 1 | 57.34% | 66.67% | 0.2353 |
| `60–65%` | 9 | 5 | 3 | 1 | 62.00% | 62.50% | 0.2280 |
| `65%+` | 9 | 8 | 1 | 0 | 72.87% | 88.89% | 0.1117 |

The 65%+ band is the most promising, but it has only nine observations. It
should be monitored prospectively rather than used to increase stakes now.

## Price and value analysis

### Odds bands

| Decimal odds | n | Wins | Losses | Pending | Break-even rate | Flat P/L |
|---|---:|---:|---:|---:|---:|---:|
| `<1.60` | 11 | 10 | 1 | 0 | 79.22% | +1.690 |
| `1.60–1.99` | 14 | 6 | 6 | 2 | 56.73% | -1.260 |
| `2.00–2.49` | 7 | 5 | 1 | 1 | 45.88% | +4.970 |
| `2.50+` | 2 | 1 | 1 | 0 | 39.61% | +0.550 |

The 1.60–1.99 band is the only negative price band and contains six losses.
The 2.00–2.49 result is attractive but has only seven observations.

### Stored edge bands

| Edge band | n | Wins | Losses | Pending | Flat P/L |
|---|---:|---:|---:|---:|---:|
| Negative | 7 | 7 | 0 | 0 | +1.080 |
| 0–3 pp | 2 | 1 | 1 | 0 | -0.450 |
| 3–6 pp | 3 | 1 | 1 | 1 | -0.250 |
| 6 pp+ | 22 | 13 | 7 | 2 | +5.570 |

The seven negative-edge legs all won, which is a small-sample warning that the
stored edge is not yet a reliable ranking signal. It should not be inverted
automatically; first verify the edge definition, timing, and market-probability
lineage.

## Quality-score analysis

QSS and DQS have identical values in this slice:

| Score band | n | Wins | Losses | Settled hit rate |
|---|---:|---:|---:|---:|
| 50–64 | 29 | 18 | 8 | 69.23% |
| 65–79 | 5 | 4 | 1 | 80.00% |

There are no selected legs at 80+ and no LRS/MRS values. Consequently, the
current quality scores provide weak discrimination and cannot support a robust
league/reliability conclusion.

## Quote and execution provenance

### Quote age at publication

| Age at publication | Legs | Wins | Losses | Pending |
|---|---:|---:|---:|---:|
| `<1h` | 2 | 2 | 0 | 0 |
| `1–3h` | 10 | 4 | 3 | 3 |
| `3–6h` | 14 | 9 | 5 | 0 |
| `6–24h` | 8 | 7 | 1 | 0 |

Twenty-two of 34 legs were older than the documented three-hour maximum. This
is the highest-priority individual-leg control issue. Before interpreting model
performance, verify whether these tickets were created by historical relaxed
policy versions, whether publication time or candidate-build time is the
authoritative cutoff, and why stale candidates were persisted.

### Bookmaker and market-price coverage

| Bookmaker | Legs | Wins | Losses | Pending |
|---|---:|---:|---:|---:|
| Missing | 21 | 16 | 5 | 0 |
| 1xBet | 3 | 1 | 2 | 0 |
| Bet365 | 3 | 0 | 0 | 3 |
| Betano | 3 | 1 | 2 | 0 |
| William Hill | 2 | 2 | 0 | 0 |
| Betfair | 1 | 1 | 0 | 0 |
| SBO | 1 | 1 | 0 | 0 |

There is no reliable bookmaker-level conclusion because most settled legs lack
bookmaker identity and the named-bookmaker samples are tiny.

Prediction-level coverage is 13/34 for executable odds and fair-market
probability. The accumulator leg retains a decimal price for every leg, but
that is not a substitute for full executable quote provenance.

## League segmentation

The sample is too fragmented for promotion decisions. The most important small
cells are:

| League | Legs | Wins | Losses | Pending | Actual rate | Mean edge |
|---|---:|---:|---:|---:|---:|---:|
| Primera Division | 3 | 0 | 3 | 0 | 0.00% | 6.95 pp |
| Prva Liga | 3 | 2 | 1 | 0 | 66.67% | 13.46 pp |
| Asian Games Women | 3 | 3 | 0 | 0 | 100.00% | -5.62 pp |
| FA Cup | 2 | 0 | 1 | 1 | 0.00% | 8.51 pp |
| First League | 2 | 1 | 1 | 0 | 50.00% | 6.86 pp |
| Liga Leumit | 2 | 1 | 1 | 0 | 50.00% | 5.19 pp |
| Premier League | 2 | 2 | 0 | 0 | 100.00% | 2.01 pp |

The remaining leagues have one or two observations each. `Primera Division`
deserves a watchlist flag, but three losses cannot establish a league effect.

## Model lineage and ticket construction

- All 31 settled legs use `1.0.0-shadow-unknown`.
- The three pending legs use model version `1.0.0`.
- All tickets are `paper_only=true`.
- Dependence penalty is zero on every remaining ticket.
- The stored policy versions include `daily-balanced-relaxed-v1`,
  `daily-safe-relaxed-v1`, `daily-last-resort-v1`, and the normal `v1` policies.
- All legs are one-per-fixture, but all are the same market family and selection.

The use of relaxed/last-resort policy versions and the zero dependence penalty
should be treated as important segmentation fields. The 31 settled legs do not
represent one stable policy/model cohort.

## Loss ledger: every settled non-Bold losing leg

| Product | Leg | League | Fixture | Odds | p | Edge | QSS/DQS | Bookmaker | Quote age | Model |
|---|---:|---|---|---:|---:|---:|---:|---|---:|---|
| Balanced | 0 | Primera Division | Firpo–Cacahuatique | 1.61 | 62.92% | 6.91 pp | 63.89/63.89 | 1xBet | 18.82h | shadow |
| Balanced | 1 | Liga Leumit | Maccabi Herzliya–Kiryat Yam SC | 2.50 | 39.03% | 3.36 pp | 62.50/62.50 | missing | 3.62h | shadow |
| Safe | 0 | Primera Division | Alianza–Fuerte San Francisco | 1.50 | 66.22% | 6.13 pp | 62.50/62.50 | missing | 18.82h | shadow |
| Balanced | 0 | FA Cup | Saham–Al Musannah | 1.87 | 58.73% | 10.53 pp | 61.11/61.11 | missing | 20.82h | shadow |
| Balanced | 1 | Primera División Femenina | FC Levante Badalona W–Granada | 1.81 | 58.46% | 8.63 pp | 63.89/63.89 | missing | 2.07h | shadow |
| Balanced | 0 | Primera B | Tigres FC–Real Santander | 1.63 | 56.63% | 1.10 pp | 63.89/63.89 | Betano | 21.20h | shadow |
| Safe | 1 | First League | Volga Ulyanovsk–Leningradets | 1.76 | 60.52% | 6.32 pp | 63.89/63.89 | 1xBet | 28.04h | shadow |
| Balanced | 0 | Prva Liga | FK Vozdovac–Napredak | 1.97 | 60.36% | 13.89 pp | 63.89/63.89 | Betano | 20.06h | shadow |
| Balanced | 1 | Primera Division | Atletico Balboa–Cacahuatique | 2.20 | 48.82% | 7.82 pp | 66.67/66.67 | missing | 18.55h | shadow |

Seven of the nine individual losses occurred with quotes older than six hours.
This makes stale-price exposure a stronger immediate mitigation target than
raising or lowering the probability threshold based on this sample alone.

## Recommended mitigation order

1. **Fail closed on stale legs.** Reconcile persisted ticket publication with
   `MAX_DAILY_QUOTE_AGE=3h`; prevent relaxed/last-resort levels from silently
   bypassing the same freshness rule.
2. **Require executable provenance.** A publishable leg should carry bookmaker,
   quote timestamp, executable odds, fair-market probability, and later closing
   quote eligibility. Missing fields should be reported as unavailable, not
   treated as neutral.
3. **Freeze cohort definitions.** Report model version, calibration version,
   feature version, policy version, and optimiser version in every leg cohort.
4. **Investigate edge semantics.** The all-win negative-edge subset is not a
   reason to reverse the edge; verify market probability, de-vigging, and timing
   first.
5. **Increase market breadth.** Do not infer system-wide leg quality from 34
   `1X2/home` legs. Require prospective evidence across multiple approved
   market/selection cells.
6. **Add uncertainty gates.** Use minimum sample sizes and confidence intervals
   before changing thresholds or granting stake authority.
7. **Repair missing reliability inputs.** LRS/MRS are absent in this slice and
   the production reliability rebuild has reported ambiguous competition names.
8. **Keep paper-only status.** The positive flat P/L is not executable-money
   evidence because CLV is unavailable and price provenance is incomplete.

## Evidence status

- **Verified:** production row counts, outcomes, ticket/leg linkage, stored
  prices, probability bands, score fields, quote ages, model lineage, and
  scheduler settlement state.
- **Inferred:** stale-price exposure and cohort mixing are likely contributors
  to weak reproducibility and value claims.
- **Untested:** whether freshness repair, bookmaker completeness, recalibration,
  or alternative market selection improves prospective performance.
- **No production or application data was modified.**
