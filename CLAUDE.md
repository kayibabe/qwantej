# Claude Code Instructions

Before making any changes:

1. Read `DEVELOPMENT.md`.
2. Understand the existing architecture.
3. Do not introduce another framework without justification.
4. Preserve existing functionality.
5. Run relevant tests after modifications.
6. Never expose secrets or credentials.
7. Never modify production data.
8. Explain significant architectural changes before implementing them.

Qwantej's objective is to become a continuously calibrated, value-driven and
risk-controlled football accumulator engine.

## Role in the multi-agent workflow

Claude Code is typically the builder: plan and implement the feature or fix,
then hand off a git diff for Codex to review, test, and hunt for bugs (see
`DEVELOPMENT.md` §5). When Codex's review comes back, either agent may apply
the fix — but only one agent edits the working tree at a time. Never run a
migration against the real (Neon) database or trigger a Railway deploy
without the user confirming first.

### Temporary: Claude solo mode (until 2026-09-30)

Codex is unavailable until 30 September 2026 (owner decision, 2026-09-27).
Until then Claude Code is both builder and reviewer. The review step is not
skipped; it runs as a separate pass after the build:

1. Build and commit on a feature branch as usual.
2. Review the full branch diff against `main` as a reviewer would, with the
   `DEVELOPMENT.md` §4 risks (leakage, reproducibility, calibration,
   settlement correctness) and §7 Definition of Done as the checklist.
3. Fix what the review finds, rerun the full test suites, and state in the
   PR description that the review was a Claude self-review.

Migration and deploy rules are unchanged: never run a migration against the
real database or trigger a Railway deploy without the user confirming first.
Remove this section when Codex returns and resume the normal split.

`DEVELOPMENT.md` is the authoritative engineering specification.
