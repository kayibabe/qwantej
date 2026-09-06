# Risk Policy

Canonical reference: [`QWANTEJ_FRAMEWORK.md`](QWANTEJ_FRAMEWORK.md) Part
VIII. Governs `src/qwantej/bankroll/`.

## Principle

A profitable predictive process can still destroy capital if staking is
uncontrolled. The risk engine operates **independently** from the selection
engine and may veto an otherwise qualified ticket. It never escalates
stakes to recover losses (no Martingale, no doubling, no loss-chasing).

## Tracked metrics

| Metric | Required tracking |
| --- | --- |
| Current bankroll | Settled capital base |
| Available bankroll | Bankroll less committed unsettled exposure |
| Daily exposure | Total stakes at risk today |
| Ticket exposure | Stake and maximum loss by product |
| Maximum drawdown | Peak-to-trough bankroll decline |
| Rolling volatility | P/L variability over defined windows |
| Kelly fraction | Theoretical stake fraction from edge and odds |
| Recommended stake | Fractional Kelly after caps and state adjustment |
| Risk of ruin proxy | Simulation/analytical estimate where feasible |

## Fractional Kelly and exposure caps (framework §35)

Full Kelly is too aggressive under uncertain model probabilities. Initial
policy (research defaults, must be validated under realistic historical
drawdowns):

| Control | Initial policy |
| --- | --- |
| Single accumulator ticket | Normally ≤2% of bankroll |
| Total daily accumulator exposure | Normally ≤4–5% of bankroll |
| Kelly multiplier | ~1/5 to 1/4 Kelly |
| Core allocation | Highest relative allocation |
| Growth allocation | Medium allocation |
| Alpha allocation | Lowest allocation |
| Loss recovery | **No** Martingale, doubling or stake-chasing logic |

## Drawdown-aware operating state (framework §36)

| State | Illustrative trigger | System response |
| --- | --- | --- |
| NORMAL | Healthy calibration/performance; drawdown modest | Normal thresholds and approved fractional-Kelly stake |
| CAUTION | ~10% drawdown or statistically meaningful soft deterioration | Reduce stake; increase monitoring; possibly tighten marginal selections |
| DEFENSIVE | ~15% drawdown or clear drift | Strongest selections only; raise qualification thresholds; restrict products |
| REVIEW | ~20% drawdown, calibration failure or severe drift | Suspend live accumulator generation; investigate and revalidate |

These percentages are initial policy anchors, not immutable truths — the
transition logic should also weigh expected drawdown distributions, sample
size, calibration drift, and whether losses are statistically consistent
with the model's predicted variance.

## Versioned policy `risk-v1` (implemented defaults)

`RiskPolicy` in `src/qwantej/bankroll/state.py` is the enforced,
version-stamped policy object; `risk-v1` is its default instance. All values
are research defaults per framework §35 and must be revalidated under realistic
historical drawdowns before promotion.

| Parameter | `risk-v1` value | Meaning |
| --- | --- | --- |
| `kelly_multiplier` | 0.25 | Quarter-Kelly scaling of the full-Kelly fraction |
| `single_ticket_cap` | 0.02 | Max stake per ticket, fraction of bankroll |
| `daily_exposure_cap` | 0.05 | Max total daily stakes, fraction of bankroll |
| `caution_drawdown` | 0.10 | Drawdown entering CAUTION |
| `defensive_drawdown` | 0.15 | Drawdown entering DEFENSIVE |
| `review_drawdown` | 0.20 | Drawdown entering REVIEW |
| `minimum_stake_fraction` | 0.001 | Below this fraction a stake is not placed |
| `stake_rounding` | 2 | Stakes floored to 2 dp (never rounded above a cap) |
| State multipliers | NORMAL 1.0, CAUTION 0.50, DEFENSIVE 0.25, REVIEW 0.0 | Stake scaling by state (non-increasing; REVIEW suspends) |
| Product allocations | Core 1.0, Growth 0.60, Alpha 0.30 | Stake scaling by product tier |

Invariants enforced at construction: `single_ticket_cap ≤ daily_exposure_cap`;
drawdown thresholds strictly ascending; state multipliers non-increasing from
NORMAL to REVIEW with REVIEW = 0. The policy object is deeply immutable (its
multiplier/allocation mappings are read-only), so a stamped `policy_version`
uniquely identifies the exact numbers used.

## Responsible-use controls (framework §37)

- Bankroll limits and exposure caps must be visible and enforceable, not
  merely advisory.
- Never present recovery staking, guaranteed returns, or certainty
  language, anywhere in the product.
- Performance reporting must show losing periods, drawdown and uncertainty
  alongside wins and ROI — never wins/ROI in isolation.
- If external users are added: configurable deposit/stake limits,
  cooling-off, or suspension options as appropriate to product and
  jurisdiction.
