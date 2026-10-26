# High Odds recommendation pause — 2026-10-26

## Decision

High Odds is paused as an active recommendation. The Conservative and Balanced
tiers remain the active daily slate. High Odds continues to be generated,
published to the immutable paper ledger, and settled as internal shadow data so
its performance can be reviewed later.

## Evidence at the decision point

The local latest-version ticket ledger showed 2 wins and 15 losses among 17
settled High Odds cohorts, with −6.93 simulated units and −40.76% ROI at one
paper unit per ticket. The latest 12 settled cohorts were 2–10 and −1.93 units.
Conservative was 16–11 and +6.00 units; Balanced was 10–18 and +3.99 units.
These are system paper results, not bets placed at a bookmaker. The 26 October
Conservative and Balanced cohorts were still pending when reviewed.

## Runtime behavior

- Only Conservative and Balanced count toward the active publication floor and
  appear on the daily recommendations slate.
- High Odds remains generated under its existing market-priced specification
  and remains in the immutable ticket and settlement tables.
- High Odds does not fill the active publication floor and is not relaxed to
  create a shadow ticket.
- High Odds is omitted from all history screens and production performance
  summaries. Stored cohorts remain available to the background generation and
  settlement pipeline, but are not surfaced in user-facing history or metrics.
- Legacy ticket and result rows are not rewritten. No existing ticket is
  regenerated or settled by this change.

This pause is reversible after a deliberate review of the accumulated shadow
record; it does not claim that the tier is permanently unviable.
