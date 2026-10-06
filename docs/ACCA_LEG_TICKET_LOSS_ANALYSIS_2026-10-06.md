# ACCA Leg and Ticket Loss Analysis

**Snapshot:** 2026-10-06 production database, latest persisted settlement
2026-10-06 17:19:57 UTC. All database queries in this report were read-only.

## Executive conclusion

The current losses are not primarily explained by the settlement worker. The
production flow is running and is settling prediction rows. The main evidence
points to product and selection quality:

- `daily_bold` is the weakest ACCA product: 1 win and 8 losses.
- All 64 published legs are `1X2 / home`, so the current sample cannot establish
  whether other markets are better or worse.
- Selected legs have no CLV evidence: 0 of 58 settled selected predictions have
  a closing odds or CLV value.
- Six of the 14 lost tickets first fail at leg index 0, five at index 1, and
  three at index 2. Losses are therefore not concentrated only in the final
  leg.
- The ACCA sample is paper-only and small. Its positive flat-unit result must
  not be treated as evidence of production profitability.

## Verified production inventory

| Area | Result |
|---|---:|
| Predictions | 8,880 |
| Accumulator tickets | 24 |
| Accumulator legs | 64 |
| Effective prediction settlements | 7,809 binary/void rows in the archive query set |
| Prediction outcomes | 4,202 wins, 3,598 losses, 9 voids |
| Settled ACCA tickets | 23 |
| ACCA outcomes | 9 wins, 14 losses |
| Pending ACCA tickets | 1 (`daily_balanced`, three unsettled legs) |
| Selected fixtures | 64 unique fixtures |
| Selected predictions | 64 unique predictions |
| Selected market mix | 64 `1X2 / home` |
| Selected legs with executable prediction odds | 24/64 |
| Selected legs with fair-market probability | 24/64 |
| Selected legs with closing odds | 0/58 settled legs |
| Selected legs with CLV | 0/58 settled legs |

The 7,809 figure includes 7,800 settled win/loss rows and 9 void rows; the
settlement table also contains historical/correction rows, so all attribution
queries exclude superseded rows.

## Scheduler and settlement-flow verification

Railway production showed all three services online. The scheduler log confirms:

1. Settlement runs are executing every 15 minutes.
2. At 17:19:57 UTC, the worker processed five finished fixtures and settled
   two predictions per fixture, with zero errors.
3. The ACCA pass reported `settled=0 corrected=0 reopened=0 pending=1`.
4. The one pending ticket is consistent with the database: it is the newly
   published `daily_balanced` ticket whose three legs remain unsettled.
5. The scheduler also reports calibration drift, with MCE approximately 0.1365
   against a 0.0500 threshold.
6. The same run reports the broad prediction KPI snapshot as approximately
   53.87% hit rate, Brier 0.2461, ROI -7.90%, and mean CLV 0.0025.

The production scheduler therefore appears operational. The pending ACCA is an
open-ticket state, not evidence that a decided ticket was lost by settlement.
There is, however, a separate reliability warning in the same run: the
reliability rebuild failed because competition names are ambiguous. That can
affect segment/reliability features and should be repaired separately from the
loss analysis.

## Leg-level results

The following uses settled leg occurrences, so a prediction repeated across
products is counted once per published ticket occurrence.

| Product | Legs | Wins | Losses | Hit rate | Mean predicted p | Actual rate | Brier | Flat leg P/L |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `daily_safe` | 14 | 12 | 2 | 85.71% | 65.44% | 85.71% | 0.1624 | +3.090 |
| `daily_balanced` | 17 | 10 | 7 | 58.82% | 61.22% | 58.82% | 0.2183 | +2.860 |
| `daily_bold` | 27 | 14 | 13 | 51.85% | 50.35% | 51.85% | 0.2768 | +1.870 |

The safe result is encouraging but has only 14 legs and two losses. Bold has the
worst Brier score and the weakest hit rate. Balanced is slightly below its
average predicted probability. These are directional findings, not promotion
evidence.

## Probability calibration

| Conservative probability band | Legs | Wins | Losses | Mean p | Actual rate | Actual minus p | Brier |
|---|---:|---:|---:|---:|---:|---:|---:|
| `<55%` | 27 | 13 | 14 | 49.40% | 48.15% | -1.26 pp | 0.2678 |
| `55–60%` | 13 | 9 | 4 | 62.25% | 69.23% | +6.98 pp | 0.2114 |
| `60–65%` | 9 | 6 | 3 | 64.09% | 66.67% | +2.57 pp | 0.2332 |
| `65%+` | 9 | 8 | 1 | 66.26% | 88.89% | +22.62 pp | 0.1534 |

The apparent high-band outperformance is based on only nine legs. It should not
be used to increase confidence thresholds or stakes without a larger
prospective sample. The broad scheduler drift warning is more important than
this small selected-leg slice.

## Ticket-level loss attribution

| Product | Won | Lost | Pending | Flat ticket P/L |
|---|---:|---:|---:|---:|
| `daily_safe` | 5 | 2 | 0 | +2.929 |
| `daily_balanced` | 3 | 4 | 0 | +8.017 |
| `daily_bold` | 1 | 8 | 0 | +4.070 |
| **Total settled** | **9** | **14** | **0** | **+15.016** |

The flat ticket result is +15.016 units over 23 paper tickets, or +65.29% on a
one-unit flat basis. This is dominated by long winning ticket prices and is not
an executable-money result: tickets are paper-only, and the selected legs have
no CLV evidence. It should not override the weak hit rate, calibration drift,
or missing price provenance.

### First losing leg

Leg indices are zero-based and refer to the immutable published ticket order.

| Product | Leg 0 | Leg 1 | Leg 2 | Leg 3 |
|---|---:|---:|---:|---:|
| `daily_safe` | 1 | 1 | 0 | 0 |
| `daily_balanced` | 4 | 0 | 0 | 0 |
| `daily_bold` | 1 | 4 | 3 | 0 |
| **Total** | **6** | **5** | **3** | **0** |

Eight of the 14 lost tickets are `daily_bold`; its losses are also distributed
across positions 0–2. This supports reducing or quarantining Bold while its
leg-level evidence is rebuilt, rather than blaming only the last leg of an
ACCA.

## Mitigation plan

### Immediate safety controls

1. Keep all products paper-only until selected-leg price provenance and
   prospective evidence are complete.
2. Quarantine `daily_bold` from any stake-authority path and continue it only as
   a labelled research/shadow product.
3. Do not publish a value claim for a selected leg unless executable odds,
   bookmaker, quote timestamp, and fair-market probability are present.
4. Treat missing CLV as unavailable evidence, not as neutral CLV.
5. Keep the one pending ticket open; do not force-settle it or infer a loss.

### Measurement improvements

1. Add a durable leg-attribution report keyed by prediction ID and ticket ID,
   including first losing leg, all losing legs, ticket size, product, market,
   league, bookmaker, odds age, CLV, model version, and calibration band.
2. Report unique prediction performance separately from ticket-occurrence
   performance so repeated legs across products cannot inflate evidence.
3. Add minimum sample gates and uncertainty intervals before product promotion.
4. Compare selected legs with eligible-but-not-selected legs using the same
   prospective price and settlement evidence.
5. Repair the ambiguous competition-name reliability rebuild failure before
   relying on league/reliability segmentation.

### Modelling and construction changes

1. Recalibrate the broad model after the observed MCE drift is investigated.
2. Require a conservative edge buffer above zero; the current system should not
   treat marginal edge as robust value.
3. Replace the independence product as the sole joint-probability basis with
   an empirically validated dependence model or a stricter haircut calibrated
   on prospective tickets.
4. Cap exposure and leg count for products with weak or missing CLV evidence.
5. Keep `NO QUALIFIED ACCA` as a valid output when no combination clears the
   evidence, value, calibration, and dependence gates.

## Limits of this report

- The settled ACCA sample is only 23 tickets and 58 settled leg occurrences.
- The selected sample is entirely `1X2 / home`; it cannot compare market
  families.
- CLV is unavailable for every settled selected leg.
- Flat-unit P/L is a paper diagnostic, not a record of placed financial bets.
- The broad -7.90% ROI is for the overall settled prediction archive, not an
  ACCA-only financial result.
- No application code or production data was modified while producing this
  report.
