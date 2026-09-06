# Reliability Engine (Phase 6)

Canonical reference: [`QWANTEJ_FRAMEWORK.md`](../QWANTEJ_FRAMEWORK.md) §25–27
and Phase 6. The implementation lives in
`src/qwantej/performance/reliability.py`.

## Evidence and point-in-time boundary

Each settled observation identifies its league, market family and competition
class and records the decision time, outcome-observation time, calibrated
prediction, unit profit, optional CLV and model-stability score. A matrix at
`evaluated_as_of` excludes every outcome observed after that cutoff. Duplicate
observation IDs and leagues mapped to conflicting competition classes fail
closed.

Reliability is not hit rate. Policy `reliability-v1` combines six normalized
components: calibration 30%, ROI 20%, CLV 15%, return variance 10%, drawdown
10% and model stability 15%. Missing CLV receives a neutral component score
and remains visible through the source snapshot rather than becoming invented
closing-price evidence. These weights and transforms are research defaults and
must be validated before promotion.

## Recency and hierarchical shrinkage

Evidence receives exponential decay with a 180-day research half-life. The
engine sums those recency weights into an effective sample count, so evidence
loses influence against the prior as it ages, then applies:

```text
w         = n_eff / (n_eff + k)
posterior = w * segment_score + (1 - w) * parent_posterior
```

The initial shrinkage strength is `k = 100`. The hierarchy is global →
competition class → league and global → market family; a league-market cell
uses the evidence-weighted league/market posterior as its parent. Thus a 6/7
segment remains close to broader evidence instead of being labelled 86%
reliable.

Posterior uncertainty is reported as a standard deviation and conservative
lower bound. Dynamic status uses that lower bound plus effective sample size:
Qualified, Watch, Restricted or Blacklisted. Recovery therefore requires new
evidence; elapsed time alone cannot promote a segment. Matrix grades summarize
the posterior mean, while qualification always uses status as well.

## Immutable matrix archive

`reliability_snapshots` stores one row per league-market cell and cutoff. Each
row includes LRS, MRS, segment reliability, uncertainty, lower bound, status,
grade, components, effective sample size, lineage hashes and policy/code
versions. Predictions may link to the exact snapshot used at decision time.
Database triggers forbid update, delete and truncate; a recalculation creates a
new cutoff row.

`backend.services.reliability.archive_reliability_matrix` validates that every
league has an explicit canonical competition mapping before inserting rows.
The Value Gate treats Restricted and Blacklisted states as `RELIABILITY_LOW`.
No live league-market grades are hard-coded and no status is production-approved
by this phase.
