# Football market framework for Qwantej

## Purpose

This document turns the supplied football-market catalogue into an extensible
analytics design for Qwantej. It is an architecture and readiness assessment,
not a claim that every listed market is available, modelled, calibrated, or
profitable. Market availability, terminology, and settlement can differ by
bookmaker and competition, so the catalogue must describe contracts rather
than assume a universal sportsbook definition.

## Framework 1: canonical market contract

Represent each offered selection as a versioned market definition. Keep the
market family, individual market, selection, event scope, and settlement rule
separate. A stable identifier should not encode display wording that may vary
between providers.

| Contract field | Meaning |
| --- | --- |
| `market_id` / `version` | Stable canonical identifier and definition version |
| `family` | Analytical grouping such as `match_result`, `total_goals`, `corners`, or `player_stats` |
| `selection_id` | Outcome within the market, such as `home`, `over_2_5`, or `yes` |
| `scope` | Match, half, extra time, shootout, player, team, or season; includes the time boundary |
| `parameters` | Line, handicap, player/team ID, interval, or combined conditions |
| `settlement_contract` | Win/loss/push/void rules, official statistic source, abandoned/postponed treatment, and extra-time treatment |
| `required_events` | Inputs needed to construct and settle the outcome |
| `probability_source` | Named distribution/model artifact and version that produced the probability |
| `evidence_policy` | Calibration, sample-size, context, price, and risk gates for use in decisions |
| `availability` | Provider/competition/time coverage and any exclusions |

Every assessment should retain the definition version, event scope, source
snapshot IDs, as-of time, model/distribution version, probability, price and
odds timestamp, calibration profile, and decision reasons. A missing required
field should remain missing and block qualification when the policy requires
it. Never infer provider settlement rules from a market label.

### Contract lifecycle

1. **Register** a definition and explicit settlement contract.
2. **Check data readiness** for point-in-time inputs and reliable outcome labels.
3. **Generate probability** from an appropriate event distribution.
4. **Validate and calibrate** on chronological, untouched samples for this
   market, competition coverage, and price availability.
5. **Qualify** using a versioned market policy; keep model probability,
   calibration, price/EV, and contextual risk as distinct evidence.
6. **Capture and settle** append-only decision snapshots using the declared
   settlement contract.
7. **Monitor** calibration, log loss/Brier, sample coverage, price movement,
   and outcome metrics by market, provider, competition, and time period.

Promotion is explicit and time-effective. A new policy or model must not
silently change the meaning of prior assessments, tickets, or settlements.

## Framework 2: shared event distributions and market adapters

Model the underlying event state once where the data supports it, then derive
related market probabilities from that same distribution. Keep the adapter
that converts a distribution into a market probability separate from the
market's qualification policy.

| Event representation | Markets it can derive when fully specified |
| --- | --- |
| Joint home/away score distribution by period | 1X2, double chance, DNB, totals, team totals, BTTS, correct score, winning margin, goal handicaps, and half comparisons |
| Goal-time / scoring hazard distribution | First/last goal, time bands, and selected in-play goal markets |
| Team/player shot event distribution | Shots, shots on target, player shot thresholds, and related combinations |
| Corner event/count distribution | Total/team/period corners, races, handicap, and corner intervals |
| Card/foul/offside event distribution | Corresponding team, player, period, count, and next-event markets when event timestamps and definitions exist |
| Season simulation distribution | Standings, qualification, relegation, and outright markets |

One marginal total-goals distribution cannot by itself produce 1X2, BTTS,
correct score, or home/away goal probabilities. Those require a joint score
distribution or another explicitly validated joint model. Combined markets
must be computed from a joint distribution or a validated dependence model;
do not multiply marginal probabilities as if correlated events were
independent. In-play markets also need state-conditioned, timestamped event
updates rather than pre-match probabilities relabelled as live.

Qwantej now has two related goal-distribution paths. The existing scaled
independent-Poisson total-goals forecast remains the source used by its current
totals path. Separately, the Poisson-Dixon-Coles component constructs one
regulation-time joint home/away score matrix per fixture and adapts it into
currently supported 1X2, double-chance, DNB, totals, and BTTS probabilities.
Compact distribution parameters and tail policy are stored in the prediction
feature snapshot. This is not yet a validated source for new qualification
policies or player, event-time, corner, card, or live-state markets.

## Framework 3: evidence and release maturity

Use the following states per market definition and competition/data scope:

| State | Meaning | Permitted use |
| --- | --- | --- |
| `catalogued` | Definition and settlement contract recorded | Catalogue/display only |
| `data_ready` | Required inputs and outcome labels have measured coverage and provenance | Offline research |
| `shadow_scored` | Point-in-time forecasts are captured without decision use | Monitoring and evaluation |
| `validated` | Frozen chronological evaluation passes the predeclared gates | Candidate for explicit promotion |
| `promoted` | Versioned profile/policy activated with an effective date | May enter the market's decision policy |
| `suspended` | Coverage, calibration, settlement, or drift gate fails | No new qualification until revalidated |

These are market-specific states: evidence for one market or league does not
automatically qualify another. Research/backfill rows must remain distinguishable
from prospective forecasts. At minimum, evaluation should report sample size,
coverage, Brier and log loss, reliability, uncertainty intervals, odds/price
availability, and ROI/closing-price metrics only where their required source
data exists. Freeze thresholds before the final holdout; zero qualifiers is a
valid result.

## Application to Qwantej today

The repository already has several useful building blocks:

- `Prediction` stores a market/selection, probability outputs, model and
  decision provenance, odds snapshots, feature snapshots, and append-only
  recommendation status.
- `MarketLearningProfile` and explicit promotion records provide per-market
  calibration/evaluation and activation concepts.
- `TARGET_MARKETS` currently scores selected goal totals, BTTS, 1X2, double
  chance (1X and X2), and draw-no-bet selections.
- A shared total-goals distribution feeds the supported totals, while five
  separate provisional qualification engines cover Over 4.5 and Under 2.5,
  Under 3.5, Under 1.5, and Under 0.5. Their blockers remain meaningful: shared
  and market-specific calibration, contextual evidence, and validation must
  pass before a selection can qualify.
- Settlement currently evaluates goals-derived selections against match
  scores, including totals, BTTS, 1X2, double chance, and DNB. The presence of
  an odds market key or UI component alone does not establish scoring,
  qualification, or settlement support.

The initial catalogue is now implemented at
`backend/app/services/market_catalog.py`. Each contract separates the canonical
market ID, selection ID, and legacy key used in existing database rows. The
model runner derives its scored targets from this registry, settlement dispatch
reads the registered settlement rule, and `GET /api/v1/markets/catalog`
exposes the machine-readable contracts. The catalog keeps 18 scored selections
distinct from additional registered settlement-only goal lines and
`double_chance_12`. It now describes the API-Football bet IDs and selection
labels used by the existing odds importer for 1X2, total goals, BTTS, and
double chance; the importer delegates those mappings to the registry. DNB is
registered for scoring and settlement, but has no odds mapping in this current
provider path. Qualification policies, display logic, and historical odds
storage still contain market-specific behavior, so the registry remains a
shared contract layer, not yet a single engine. The catalogue also reports
qualification coverage: eight scored total-goal selections point to their
market-specific provisional policy versions, ten other scored selections are
marked `generic_recommendation_only`, and settlement-only contracts are marked
`settlement_only`. These are descriptive labels; provisional policy IDs do not
mean the policy is calibrated, promoted, or eligible to select a pick.

The UI now fetches this read-only catalogue at app startup and uses its
`display_name` for recognized legacy market and selection keys through the
shared formatter. Existing local labels remain the fallback if the catalogue
request fails, and no stored keys or qualification rules change. Historical/API
quote rows store the legacy market and selection keys, bookmaker, price, and
timestamp; the mutable live
quote row also stores a source type. Immutable odds snapshots do not currently
store provider market ID, raw source label, or catalogue/mapping version.
Historical CSV imports populate the quote table as fallbacks and do not create
API quote snapshots. Richer historical provenance needs a separate additive
schema and backfill proposal before it is used for point-in-time comparisons.

The shared joint-score implementation and its first detached replay are
documented in
`docs/JOINT_SCORE_DISTRIBUTION_RESEARCH_2026-10-24.md`. Preliminary raw
Poisson-component metrics are below an expanding historical outcome baseline
across the scored markets. This diagnostic does not evaluate the full
ensemble or betting performance; it means the distribution needs further
diagnosis and validation before it can support new decisions.

## Family readiness and suggested order

| Catalogue families | Qwantej fit now | Next gate before use |
| --- | --- | --- |
| Match result, double chance, DNB | Partially scored and settled from match scores; not covered by the shared totals qualification design | Define canonical contracts, verify complete scoring and calibration/qualification coverage, and audit edge-case settlement |
| Match totals and team goals | Totals have the strongest shared-distribution foundation; a joint score matrix is available for current score-derived adapters, but its detached replay is weak | Preserve existing gates; diagnose and validate the joint score model before adding team-goal qualification or deriving further score-based markets |
| BTTS, correct score, winning margin, goal handicap, half comparison | BTTS is currently scored from the shared joint-score adapter; other outcomes can partly be settled from final/half-time scores | Validate market-specific probabilities from the joint distribution; add period-specific distributions and contract tests for pushes and line variants before expanding scoring |
| Corners, cards, shots, fouls, offsides, possession, passing | No evidence in the inspected target-market scoring contract that Qwantej currently captures the event data needed | Confirm provider coverage, statistic definitions, timestamped history, and result ingestion before modelling |
| Player goals/statistics and special events | Requires player identity, lineup/minutes, event-level labels, and provider-specific settlement | Establish identity and event data provenance, then validate player/rare-event models and void rules |
| Goal timing and in-play | No live-state scoring contract established | Build timestamped event state and live odds snapshots; validate state-conditioned forecasts independently |
| Combined / bet-builder | Shared marginal probabilities are insufficient where components are dependent | Require a validated joint model or dependence layer and bookmaker-specific bet-builder pricing/settlement contracts |
| Extra time, shootouts, tournament/season outrights | Outside the current 90-minute match-score target/settlement surface | Add separate competition-phase/season state models and explicit settlement contracts |

### Recommended implementation sequence

1. **Complete the current catalogue integration.** The 18 scored selections,
   settlement rules, and the currently used API-Football odds IDs now have
   machine-readable definitions, as does the current distinction between
   market-specific provisional and generic recommendation coverage. The UI
   consumes the catalogue labels with its existing fallback. Finish the
   historical-storage audit; keep current qualification behavior unchanged.
2. **Validate the goal event layer.** Diagnose the current regulation-time joint
   home/away score probabilities, freeze candidate comparisons, and evaluate
   them chronologically before deriving additional score-based markets. Add
   first-half distributions as a separate scope.
3. **Make settlement contracts explicit.** Cover pushes, quarter-goal lines,
   period boundaries, corrections, abandoned matches, extra time, and source
   statistic rules before enabling new definitions.
4. **Expand one event family at a time.** Add corners/cards/shots only after
   source coverage and settlement labels are proven. Keep each new family in
   shadow mode through a prospective validation window and explicit promotion.
5. **Add correlated, live, player, and season markets last.** These require
   richer data and dedicated joint/state models; they should not be synthesized
   from unrelated marginal forecasts.

## Decision

The frameworks can be applied in Qwantej, and its total-goals engine,
market-specific profiles, provenance, explicit promotions, and fail-closed
qualification are a sound starting base. The catalogue/contract layer and a
shared joint-score adapter now exist for the markets already scored. The first
detached replay does not support promoting or expanding that score component.
The 25 catalogue families should not be treated as 25 ready-to-enable
features: most require new data, settlement, and prospective validation before
they can influence picks.
