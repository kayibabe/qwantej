# Qwantej Agent Instructions

Always read `DEVELOPMENT.md` before modifying the repository.

Core principles:

- Reliability before speed.
- Statistical validity before attractive predictions.
- Tests before deployment.
- Reproducibility before experimentation.
- Historical predictions must never be rewritten.
- Prevent look-ahead bias and data leakage.
- All betting probabilities must be auditable.
- All model changes must be benchmarked.

After changing code:

1. Run tests.
2. Run linting/type checking where applicable.
3. Check git diff.
4. Describe what changed.
5. Identify remaining risks.

## Role in the multi-agent workflow

Codex normally operates as the reviewer. When Claude Code is unavailable,
Codex assumes both the builder and reviewer roles. The pipeline is the same;
the agent is the same for both steps. **Enforce the split explicitly:**

### Builder pass (implement)

1. Read `DEVELOPMENT.md` in full.
2. Create a feature branch (`git checkout -b feature/<name>`).
3. Plan the change before writing code — describe the approach and identify
   any §4 risks (data leakage, look-ahead bias, calibration impact,
   reproducibility) before the first edit.
4. Implement the change: code, Alembic migration if schema changed, tests.
5. Run tests and linting. Fix failures before proceeding.
6. Commit to the feature branch. Do **not** merge yet.
7. Hand off to the reviewer pass below.

### Reviewer pass (self-review)

Given the diff on the feature branch, perform an independent review:

1. `git diff main...HEAD` — read the full diff cold, as if you didn't write it.
2. Run the §4 checklist against every changed file:
   - No data leakage or look-ahead bias introduced?
   - Every probability-producing code path archives its forecast?
   - Random seeds recorded if stochastic?
   - Backtest result stated in PR description if model/staking/settlement changed?
   - No historical forecast or settled bet deleted or silently overwritten?
3. Run tests, lint, type-check again from a clean state.
4. Report findings explicitly, even if there are none ("No §4 issues found").
5. If findings exist: fix them on the branch, re-run tests, re-review the fix.
6. Only after a clean reviewer pass: open a PR to `main`, fill in the
   Definition of Done checklist (`DEVELOPMENT.md` §7).

Never run migrations or `flyctl deploy` against a real target without
explicit user confirmation. Never modify production data directly.

`DEVELOPMENT.md` is the authoritative engineering specification.
