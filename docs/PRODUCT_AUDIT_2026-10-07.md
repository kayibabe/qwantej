# Qwantej Product Audit

## Purpose

This audit translates the supplied betting-intelligence brief into an implementation plan grounded in the current Qwantej repository. Qwantej is an evidence-first forecasting and paper-ticket system. The redesign therefore improves the decision workflow without turning research output into a staking claim or replacing archived historical records.

## Current system flow

The repository contains the following implemented path:

`provider ingestion -> fixture and odds records -> feature snapshots -> model and calibration outputs -> prediction archive -> value and risk gates -> daily candidate snapshots -> accumulator tickets -> settlement -> performance and calibration analytics`

The backend is a FastAPI shell over SQLAlchemy/PostgreSQL models. The domain package under `src/qwantej` owns model, market, value, accumulator, bankroll, settlement, calibration, and audit logic. The frontend is a server-rendered Next.js application that consumes authenticated API contracts.

The strongest existing controls are immutable forecast and quote lineage, candidate-pool snapshots, validated-league publication gates, settlement correction lineage, accumulator leg attribution, calibration metrics, and append-only bankroll/risk structures.

## Findings

### What was confusing

- The home page led with published tickets and system availability rather than the complete decision context.
- Navigation used implementation terms such as Tickets, Forecasts, and Daily candidates without grouping them around the bettor workflow.
- Candidate-level model probability, market probability, price, data quality, and exclusion reason were available in the product but separated from the primary decision surface.
- The system has evidence and calibration views, but the relationship between a selection and its supporting evidence was not the first thing users saw.

### What was missing from the current product surface

- A single decision-oriented opportunity table combining match, selection, price, probability comparison, data quality, and policy decision.
- A clear distinction between selected candidates, explicitly rejected candidates, and unavailable or unknown state.
- A formal match-intelligence route that combines executive summary, evidence, market probabilities, model lineage, and risk explanations.
- Shared date-range semantics across the analytics pages.
- Dedicated market, league, odds-band, correlation, exposure, and drawdown drill-downs.

### Analytical risks to preserve against

- Candidate snapshots are immutable evidence and must not be rewritten when current odds or results change.
- Research forecasts must remain visibly separate from production/value-qualified forecasts.
- Missing quote provenance must remain unavailable, never silently converted to zero or neutral value.
- Historical performance must use the archived probability and executable price available at the original decision boundary.
- Small samples must be labelled as insufficient evidence rather than presented as durable profitability.

## Keep improve merge remove new

| Classification | Current capability | Direction |
| --- | --- | --- |
| Keep | Forecast archive, model registry, calibration, settlement, accumulator provenance, risk and bankroll services | Preserve as evidence and control foundations |
| Improve | Today dashboard, candidate pool, performance views, navigation, empty/error states | Make decision-first and progressively disclose detail |
| Merge | Ticket status, candidate selection, and evidence links | Present one opportunity-to-ticket workflow while retaining source pages |
| Remove | No current feature is removed in this phase | Avoid deleting evidence or historical records without a reviewed replacement |
| New | Match intelligence, explicit watchlist state, shared analytics filters, market/league/odds-band analysis, correlation/exposure views | Add only where the data contract can support an auditable result |

## Implemented in phase one

The primary dashboard now shows:

- candidate coverage for the selected product day;
- BET count from candidates explicitly selected by the stored Daily Pick run;
- WATCH count for new candidates that passed upstream gates but fell outside the target-band optimizer;
- legacy NOT SELECTED count for older persisted rows; this is not treated as an explicit PASS;
- REVIEW for any future or unknown candidate state rather than inferring a decision;
- model probability, market probability, derived probability difference, odds, DQS, exclusion reason, and ticket link;
- published tickets below the opportunity surface;
- navigation grouped as Betting desk, Analytics, and Evidence & models.

New candidate snapshots now persist WATCH for gated candidates outside the target-band optimizer. Historical `not_selected` rows remain unchanged and are rendered as legacy NOT SELECTED. An explicit PASS state for upstream gate failures still requires retaining those rejected candidates in an append-only snapshot; they are currently filtered before the Daily Pick candidate pool is built.

## Next implementation phases

1. Add an auditable match-intelligence endpoint and route, reusing existing evidence services and archived prediction lineage.
2. Add a shared analytics date-range contract and use it for performance, market, league, odds-band, and model comparisons.
3. Add sample-size and reliability annotations to analytics cards and charts.
4. Add explicit watchlist state only after defining its policy, persistence, audit, and expiry semantics.
5. Add correlation and exposure diagnostics to accumulator construction and display.
6. Add visual regression coverage for responsive dashboard, opportunity table, empty, stale, unavailable, and partial-data states.
7. Validate performance on large archives with query counts, pagination, aggregation strategy, and realistic PostgreSQL data.

## Definition of success for the product surface

A user opening Qwantej should be able to identify what was selected, see why it was selected or rejected, compare model and market probability, inspect data quality and provenance, open the archived ticket, and reach historical performance without treating an unverified result as a promise. The model engine remains complex; the primary surface remains concise and decision-oriented.
