# Balanced tier: administrator-only observation cohort

**Date:** 2026-11-20
**Status:** Active

## Decision

Balanced has produced a materially negative record. It stays in the pipeline —
generated, published, settled and auditable — but it is no longer part of the
customer-facing portfolio or of any ROI/P&L aggregate. Administrators can
still monitor it. The decision is reversible without a code change.

## Switch

```dotenv
BALANCED_TIER_ADMIN_ONLY=true
```

- `true` (current): Balanced is an administrator-only observation cohort.
- `false`: Balanced returns to the normal public portfolio and resumes counting
  in every aggregate.

The default in `app/config.py` is `true`, so every deployment picks up the
policy without an env change.

## What changes while the flag is on

| Surface | Behaviour |
| --- | --- |
| Daily tickets (`/tickets/daily`) | Balanced card/row is returned to administrators only. Non-admins receive no Balanced object, no superseded Balanced history, no publication-count contribution from it, and no Balanced keys in missing/relaxed/horizon metadata. |
| Ticket history (`/tickets/history`) | Balanced cohorts are filtered out for non-admins. |
| Ticket detail (`/tickets/{id}`) | A direct request for a Balanced ticket returns `404` to non-admins. |
| Match history (`/tickets/matches/history`) | Balanced legs no longer contribute for any non-admin user. The endpoint is readable by every signed-in user; only the filter controls are administrator-only. |
| Public record (`/tickets/public-proof`) | Balanced never appears; anonymous visitors only see the public portfolio. |
| Paper Ledger / Tracker | Readable by every signed-in user. The From/To date controls on both Ticket history and Match outcomes are available to all signed-in users; the other filter controls and the validation shortcut remain administrator-only. Balanced cohorts are filtered out server-side for non-admins. Administrators still see Balanced rows in the ledger; the default "Portfolio tiers" summary excludes them from P&L, ROI, hit rate and stake, and selecting the Balanced tier shows its standalone record. The observation list comes from `/tickets/tracker-meta`, so it follows the flag. |
| Analytics (`/performance/summary`) | Balanced is excluded from headline stakes, returns, P&L, ROI, hit rate, drawdown and calibration. A separate `observation_only` block and `by_ticket_type` rows reserve its metrics for administrators (the endpoint itself is admin/research-key gated). |
| Automatic daily merge ("My accumulators") | The automatic merge is built from Conservative + Balanced legs, so its settled row is withheld from portfolio ROI/P&L while the flag is on. The count is reported in `observation_only.excluded_daily_merges`. Manually built accumulators are unaffected. |
| Other ROI/P&L reports | Individual-selection what-if ROI, totals calibration, market reliability and the recommendation ledger exclude Balanced cohorts. |

Generation is intentionally untouched: `PUBLIC_TICKET_TYPES` still includes
Balanced, so the publication minimum and settlement pipeline behave exactly as
before and the forward record remains complete for the eventual decision. The
frontend also reads observation status from the API, so switching the flag off
restores the normal card, copy and P&L inclusion without a code change.

## Why this shape

- Hiding only the card would leave Balanced in public ROI/P&L numbers.
- Removing it from `PUBLIC_TICKET_TYPES` would stop generating and settling it,
  losing the forward evidence needed to decide whether to restore it.
- A config flag makes restoration a one-line deployment change with no data
  migration.
