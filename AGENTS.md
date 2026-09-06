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

Codex is typically the reviewer: given a diff from Claude Code (or a human),
run tests, lint/type-check, and look for bugs — especially data leakage,
look-ahead bias, broken reproducibility, and calibration regressions (see
`DEVELOPMENT.md` §4). Report findings; whichever agent is better positioned
applies the fix, one agent editing at a time (see `DEVELOPMENT.md` §5).
Never run migrations or `flyctl deploy` against a real target without
explicit user confirmation. Never modify production data directly.

`DEVELOPMENT.md` is the authoritative engineering specification.
