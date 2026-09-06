# Model Governance

Canonical reference: [`QWANTEJ_FRAMEWORK.md`](QWANTEJ_FRAMEWORK.md) §§42–44,
51. Covers the model registry, versioning, validation and promotion process
for anything in `src/qwantej/models/` and `qwantej/calibration/`.

## Principle

Qwantej should learn every day but must not rewrite its live decision rules
after every short losing sequence. Daily jobs update descriptive statistics,
posterior reliability, and drift indicators; **material model or policy
changes require a separate promotion process.**

## Daily learning loop (non-promoting)

1. Settle outcomes
2. Update prediction errors and calibration monitoring
3. Update LRS/MRS posterior statistics
4. Update CLV and execution diagnostics
5. Detect drift
6. Train or score challengers where scheduled
7. Run backtests/validation
8. Record model/policy candidate version
9. Promote only after governance criteria below are satisfied

## Champion–challenger framework

| Stage | Requirement |
| --- | --- |
| Champion | Current approved production model/policy |
| Challenger | Runs in shadow mode; **cannot control live tickets** |
| Minimum evidence | Sufficient predictions across relevant markets; 500+ is a practical target for broad comparison, but segmented tests need context-specific power |
| Comparison | Calibration, Brier/log loss, ROI/yield, CLV, drawdown, stability, operational reliability |
| Promotion | Challenger demonstrates robust improvement on pre-specified criteria and does not materially degrade risk |
| Rollback | Previous champion artefacts and configuration remain deployable |

No challenger is promoted on a single favorable metric or a hunch — the
comparison row above is the checklist, and it must be satisfied and
recorded in `model_registry`/`experiments` before a promotion PR is opened.

## Drift detection

Six independent drift types, each tracked separately (do not collapse them
into a single "things feel off" signal):

- **Feature drift** — input distributions change
- **Prediction drift** — probability distributions change unexpectedly
- **Calibration drift** — observed frequencies no longer match predicted
  probabilities
- **Market drift** — bookmaker efficiency/pricing relationships change
- **League regime drift** — scoring, home advantage, styles or competition
  structure change
- **Execution drift** — prices move faster, or Qwantej captures less
  favorable odds

Drift should first **reduce reliability or widen uncertainty**. It must not
automatically trigger a new production model without validation — drift is
an input to the promotion decision, not a bypass of it.

## Definition of Done for a quantitative feature (framework §51)

Before a model/calibration change merges:

- [ ] Functional specification exists and states the exact decision rule
- [ ] Inputs/outputs and timestamps are defined in `DATA_DICTIONARY.md`
- [ ] Unit tests cover normal, boundary and failure cases
- [ ] Leakage test demonstrates future data cannot enter the computation
- [ ] Numerical sanity tests compare against a known baseline
- [ ] Backtest is walk-forward and configuration is preserved (see
      `BACKTEST_POLICY.md`)
- [ ] Metrics include calibration and risk, not only hit rate
- [ ] Logging/audit records identify model, code and policy versions
- [ ] Codex/independent review resolves probability, data and risk findings
- [ ] Documentation updated before production promotion

## Model registry minimum fields

Per `DATA_DICTIONARY.md`'s `model_registry` / `model_runs` tables: model
family/version, training window, code/artefact hashes, status
(`champion`/`challenger`/`retired`), execution metadata, data snapshot used,
parameters, outputs. No model is live without a registry row.
