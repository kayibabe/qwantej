# Phase 12 evidence and governance readiness

Phase 12 closes the boundary between a functioning research system and a
system with evidence that could be considered for live promotion. The work is
deliberately evidence-first: historical rows fetched after a match are valid
outcomes or training history, but they do not create historical pre-kickoff
availability.

## Controlled runbook

Run these commands from the repository root against the disposable local
PostgreSQL service:

```powershell
docker compose up -d db
.venv\Scripts\alembic.exe upgrade head
.venv\Scripts\python.exe -m backend.workers.ingestion_worker
.venv\Scripts\python.exe scripts\run_signal_pipeline.py --shadow
.venv\Scripts\python.exe -m backend.workers.settlement_worker
.venv\Scripts\python.exe scripts\run_readiness_report.py --json
```

For continuous prospective collection, start the scheduler from the
repository root:

```powershell
.venv\Scripts\python.exe -m backend.workers.scheduler
```

The scheduler runs ingestion, the signal pipeline in mandatory shadow mode,
and settlement on separate intervals. It never enables live publishing or
builds live accumulators; stop it with Ctrl-C when the collection window is
complete.

The ingestion worker's default scope is the four validated leagues. The
shadow signal pipeline archives gate-rejected PIT-safe forecasts with a
current-code challenger, feature snapshot, model run, code commit, and input
hash. It never builds accumulators. Settlement and reliability/KPI rebuilds
must complete before the readiness report is evaluated.

If migration, provider credentials, or a required service is unavailable,
stop and record the failure. Do not stamp an unknown Alembic revision, use
backfilled timestamps as PIT evidence, or substitute retrospective research
metrics for a PIT-certified walk-forward run.

## Readiness command

`run_readiness_report.py` is read-only and exits `0` only when all checks pass.
It requires a succeeded de-vigged-market walk-forward experiment marked
`pit_certified`, a minimum sample, zero recorded leakage rows, persisted Brier,
log-loss, calibration, CLV, and ROI metrics, complete forecast provenance,
enough settled predictions, reliable snapshots without future rows, exactly one
champion model and calibrator, and no non-paper accumulators.

A passing report is evidence for human governance review, not an automatic
promotion. The paper-only boundary remains in force until a separately
reviewed promotion change is approved.
