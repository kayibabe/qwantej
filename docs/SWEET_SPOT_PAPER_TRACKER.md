# Frozen away-win paper experiment

Open **Research workspace → Track → Sweet-spot test**. This is a separate experiment from the existing singles ledger and ticket publication.

The fixed hypothesis is away win, Q >=65, decimal odds >=1.80 and <3.00, quote age <=3 hours, one paper unit per fixture. First stored away-win prediction wins identity; a rejected or missing-price first prediction is never replaced by a later attractive prediction. Source quotes must still be fresh when the tracker actually captures them. Explicit decision timestamps, stored features, model identity and named bookmaker/provider are required. This stricter evidence cohort must not be conflated with the legacy historical audit.

## Collection and storage

- `SWEET_SPOT_TRACKING_ENABLED=true` is enabled in the local `.env`. Default is false elsewhere. No remote deployment was changed.
- API scheduler queues `pipeline.track_sweet_spot` at startup and every five minutes. Celery retries twice on failure; the existing final-retry alert mechanism records failures. The server, worker, database and Redis must remain running.
- A PostgreSQL transaction lock serializes runs. Each fixture has one unique decision event. First predictions, exclusions, original features, identities, prices and timestamps are copied into an append-only ledger. The selection query does not read final scores.
- Known fixtures from 19 October 2026 onwards enter the monitoring window seven days before kickoff. Missing predictions are retried until kickoff; after kickoff they are permanently recorded as missed decisions. Fixtures absent from the source database cannot be measured.
- PostgreSQL triggers reject UPDATE/DELETE and reject qualified inserts after kickoff. Hashes detect payload changes; they do not constitute independent external timestamp certification. Routine retry never replaces a decision.
- A successful run records a heartbeat even with zero picks. The screen calls collection stale after 15 minutes and shows missing daily observations. One heartbeat does not certify a fully observed day.
- Final scores settle paper picks automatically. Revisions append a new outcome event; the report uses the latest revision. A corrected non-final result returns the pick to pending. Postponed/cancelled games are not assumed refunded. Unresolved picks older than six hours are counted separately.

## Review

Review only once **16 January 2027**, **300 settled fixtures**, and **30 distinct settled matchdays** have all been reached. This enables a review, not automatic promotion or real-money authority. Do not tune thresholds on interim results.

The screen reports flat-stake profit/ROI, pending results, drawdown in kickoff order, league/model concentration, and a 5% winnings-reduction scenario. The scenario is not actual execution cost. A descriptive day-cluster ROI interval appears after ten settled matchdays; its assumptions and limited sample remain material. A changing model version is reported separately and needs review, not silent pooling as proof of a stable model.

## Verification

- `python -m pytest tests/test_sweet_spot_tracker.py -q`: timing, odds/Q boundaries, fallback/replay protection, outcome-blind selection, corrected settlements, integrity and stale heartbeat tests.
- `PYTHONPATH=/app python scripts/verify_sweet_spot_tracker.py`: temporary isolated PostgreSQL schema; repeat migration, capture/retry, first-prediction rejection, settlement revisions, DB immutability and pre-kickoff guard. The script removes only its randomly named `test_sweet_spot_*` schema in a finally block.
- Authenticated monitoring: `GET /api/v1/sweet-spot`. There are no public mutation endpoints or betting actions.
- Supervised local deployment: `D:/WebApps/local-server/scripts/start-app.ps1 -App qwantej`. Migration `b208d5e9f3a2` adds only the new ledger and its protection functions/triggers.

Stopping collection requires disabling its local setting and restarting the API/worker; existing evidence remains. Do not downgrade/drop the ledger to pause an experiment.
