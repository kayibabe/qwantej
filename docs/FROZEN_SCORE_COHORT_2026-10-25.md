# Frozen score-snapshot pilot: 25 October 2026

The 74-fixture / 1,332-forecast pilot documented in
[the joint-score research report](JOINT_SCORE_DISTRIBUTION_RESEARCH_2026-10-24.md)
is now supported by a separate read-only scorer. It is **not** the
[180-day holdout](FORWARD_SCORE_DISTRIBUTION_HOLDOUT_PLAN_2026-10-25.md), which
has not passed its capture readiness gate.

The initial live check on 25 October found all 74 snapshot-bearing fixtures
scheduled. Kickoffs run from 11:00 to 21:05 UTC (13:00 to 23:05 CAT). No pilot
outcomes were available for scoring. The day's other 32 forecast-bearing
fixtures lack complete snapshots and are outside this selected pilot; the
manifest retains the original 106-fixture / 1,908-forecast capture denominator.

## Frozen inputs and analysis

`docs/evidence/score_snapshot_pilot_2026-10-25/manifest.json` records the exact
prediction IDs, original probabilities, timestamps, score parameters, feature
snapshot hashes, and baseline history. The export reconstructs the latest
strictly pre-kickoff forecast available by the documented 05:37 UTC check,
requires the documented 74 / 1,332 counts, and refuses an initial freeze after
any selected fixture has kicked off. The file is created without overwrite.

The baseline uses the existing replay's earlier-UTC-date convention: latest
pre-kickoff model-run forecasts of version 0.3.0 captured by the cutoff, joined
to finished, non-excluded match scores. Global and competition estimates use
`(wins + 1) / (nonvoid outcomes + 2)` and require 30 previous outcomes. Baseline
inputs are saved before this pilot's matches begin and do not expand with
pilot results. Baseline outcome labels reflect the database at export time.

The scorer reads only current match outcomes and uses the manifest's saved
probabilities. It does not select newer predictions or refit anything. It
reports Brier score, log loss, AUC, reliability bins, paired baseline Brier
skill, and expected-goal bias/MAE. Missing, scheduled, live, excluded, invalid
score, and void forecasts remain accounted for. Draw-no-bet draws are void
for binary scoring, but their scores can contribute to goal-rate diagnostics.
Reports retain the result snapshot and its update timestamps so later result
corrections can be distinguished using a fresh report.

Both manifest integrity and analysis-source fingerprints are checked before
scoring. A changed evaluator must be reviewed and versioned separately.
The fingerprint covers the pilot scorer, evaluation helpers, settlement,
market catalogue, and Poisson distribution implementation. This is an analysis
fingerprint, not a retroactive forecast build ID. Original forecast build IDs
remain missing.

## Score after results arrive

From the repository root in PowerShell, copy the frozen manifest to the running
backend and write a new report for each scoring run:

```powershell
rtk docker cp docs/evidence/score_snapshot_pilot_2026-10-25/manifest.json qwantej-backend-1:/tmp/score-snapshot-pilot-2026-10-25.json
rtk docker exec -w /app qwantej-backend-1 python -m app.services.frozen_score_cohort score --manifest /tmp/score-snapshot-pilot-2026-10-25.json --output /tmp/pilot-score-after-results.json
rtk docker cp qwantej-backend-1:/tmp/pilot-score-after-results.json docs/evidence/score_snapshot_pilot_2026-10-25/score-after-results.json
```

Use a fresh output filename for subsequent runs. The database transaction is
repeatable-read and read-only; no result ingestion or ticket settlement occurs.
Result availability still depends on the existing ingestion process.

This pilot provides descriptive evidence only. Its snapshot-selected coverage,
missing forecast build IDs, and maximum 74 fixtures preclude a confirmatory
market conclusion. Complementary selections do not add independent fixtures.
The 500-fixture threshold and prospective holdout requirements remain intact.
No promotion, model, qualification, or betting changes follow from this report.
