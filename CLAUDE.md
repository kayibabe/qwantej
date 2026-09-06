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
migration against a real database or run `flyctl deploy` without the user
confirming first.

`DEVELOPMENT.md` is the authoritative engineering specification.
