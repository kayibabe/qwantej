# Qwantej Engineering Standard

This is the master engineering constitution for Qwantej. It is the single
source of truth for architecture, workflow, and non-negotiable rules. Every
contributor — human or AI coding agent — follows this document. `CLAUDE.md`
and `AGENTS.md` exist to route tool-specific agents here; they must not
duplicate or contradict what's written below.

Qwantej is a football forecasting laboratory: it ingests historical and live
match data, runs an ensemble of statistical models, and produces calibrated
probability forecasts and betting signals. The product's credibility rests
entirely on whether its numbers are honest, reproducible, and empirically
tracked — that constraint shapes every rule in this document more than any
normal web-app concern does.

## 1. Architecture

- **Backend:** FastAPI (Python)
- **Database:** PostgreSQL, hosted on [Neon](https://neon.tech)
- **ORM:** SQLAlchemy
- **Migrations:** Alembic — every schema change is a migration, no exceptions
- **Frontend:** React / Next.js
- **Hosting:** [Railway](https://railway.app), exclusively — one Railway
  project, three services, all sourced from this repo:
  - `qwantej-api`: the FastAPI web service (`railway.toml` at repo root).
  - `qwantej-scheduler`: the Background Worker that runs
    ingestion/signal-pipeline/settlement on a loop
    (`backend/workers/scheduler.py`); start command
    `python -m backend.workers.scheduler`.
  - `qwantej-frontend`: the Next.js app (`frontend/railway.toml`).
  The `Procfile` at repo root documents the backend's two process types.
  No other hosting provider (Vercel, Render, Fly.io) is used for any part of
  this project — if you find a reference to one, it's stale; fix it or flag
  it.
- **Containerization:** Docker (local dev only — Railway builds every service
  natively via Nixpacks from its `railway.toml`, it does not use a
  Dockerfile)
- **CI:** GitHub Actions
- **Deployment:** Neon + Railway — **deploys are manual for all three
  services.** Pushing to GitHub does not deploy anything: "deploy on push"
  must stay disabled for `qwantej-api`, `qwantej-scheduler`, and
  `qwantej-frontend` alike, so after a change is merged and CI is green,
  trigger each Railway deploy explicitly (dashboard "Deploy" button or
  `railway up --detach`) and say so out loud before doing it. The frontend
  gets the same manual-deploy discipline as the backend now that it lives on
  Railway too — there is no platform-default auto-deploy-on-push left in this
  stack to rely on.

## 2. Repository Layout

```
D:\WebApps\qwantej\
├── .github/
│   └── workflows/        # CI pipelines
├── backend/               # FastAPI app
│   ├── api/               # routers / endpoints
│   ├── core/              # config, startup, cross-cutting concerns
│   ├── models/             # SQLAlchemy models + Alembic migrations
│   ├── schemas/            # Pydantic request/response schemas
│   ├── services/           # application/business logic
│   └── workers/            # background jobs, scheduled tasks
├── frontend/              # React / Next.js app
├── src/
│   └── qwantej/            # core domain package — the quant engine itself
│       ├── data/            # raw/loaded data access
│       ├── fixtures/        # fixture ingestion & normalization
│       ├── features/        # feature engineering
│       ├── models/          # statistical models
│       │   ├── poisson/
│       │   ├── zinb/
│       │   ├── bayesian/
│       │   └── ensemble/
│       ├── calibration/     # probability calibration & measurement
│       ├── value/            # fair odds / value detection
│       ├── markets/          # market/odds representation
│       ├── accumulator/      # accumulator construction logic
│       ├── bankroll/         # staking / bankroll management
│       └── performance/      # forecast archive & model performance tracking
├── tests/                 # test suites (unit, integration, backtest validation)
├── docs/
│   ├── architecture/       # system architecture notes
│   ├── modelling/          # model methodology write-ups
│   └── decisions/          # ADRs
├── AGENTS.md              # instructions for Codex
├── CLAUDE.md               # instructions for Claude Code
├── DEVELOPMENT.md          # this file — the engineering constitution
├── README.md
├── .gitignore
└── .env.example
```

`backend/` is the web-app shell (HTTP, auth, request/response). `src/qwantej/`
is the domain package that owns the actual forecasting logic and must stay
importable/testable independent of FastAPI — `backend/services` calls into
`qwantej` (installed/importable via `src/`), not the other way around. It
lives under `src/` rather than as a top-level `qwantej/` to avoid the
classic flat-layout gotcha where running tests from the repo root can
silently import the local directory instead of the properly installed
package.

Keep this layout intact. New top-level directories require a reason written
in a commit message or PR description, not silent sprawl.

## 3. Non-Negotiable Rules

### Data & Migrations
- Never modify production data directly (no ad-hoc `UPDATE`/`DELETE` against
  the live database, no manual psql surgery). Fix it in code, ship it through
  a migration or an application code path.
- Every database schema change ships as an Alembic migration, committed in
  the same PR as the code that depends on it. No migration, no schema change.
- Migrations must be reversible (`downgrade()` implemented) unless there is a
  documented reason they can't be (e.g. irreversible data backfill) — state
  that reason in the migration's docstring.
- Never delete historical forecasts, settled bets, or archived model output.
  If data is wrong, append a correction/annotation; don't erase the record.

### Secrets & Configuration
- Never hard-code API keys, database URLs, or credentials in source.
- All secrets live in environment variables, loaded via `.env` locally
  (never committed) and via each Railway service's own Variables tab in
  production (`qwantej-api`, `qwantej-scheduler`, `qwantej-frontend`).
- Commit `.env.example` with every new required variable, kept in sync with
  reality — a missing var here is a bug.

### Testing
- New calculation logic (model math, staking logic, calibration, odds
  conversion, settlement logic) requires tests. No exceptions for "it's just
  a small formula" — small formulas are exactly where sign errors and
  off-by-one probability bugs hide.
- A bug fix in scoring/settlement/calibration logic gets a regression test
  that fails on the old code and passes on the new code, not just a manual
  check.
- Don't mock the database in integration tests that exercise migrations or
  query correctness — run them against a real (local/test) Postgres instance.

### Git & Review
- No direct pushes to `main`. Work happens on feature branches, merged via
  PR.
- A PR that touches model output, staking, or settlement logic must state in
  its description what backtest or validation was run and what it showed.
- Commit messages describe *why*, not just *what* — the diff already shows
  what changed.

## 4. Betting Model & Forecast Integrity

This section is Qwantej-specific and is the part most likely to be violated
by a well-intentioned but generic "clean up the code" pass. Read it before
touching anything under model/ensemble/calibration/forecast code.

- **Every prediction is archived.** A forecast that was generated but never
  written to the forecast archive effectively didn't happen — it can't be
  scored, and it breaks the calibration feedback loop. Model code paths that
  produce a probability must write it to the archive as part of the same
  transaction/flow, not as a best-effort side effect.
- **Reproducibility.** Given the same inputs (fixture data, model version,
  config), a model must produce the same output. If a model has a stochastic
  element (e.g. Monte Carlo simulation), the random seed must be recorded
  alongside the forecast so it can be replayed exactly.
- **No data leakage in backtesting.** A backtest must only use information
  that would have been available *before* the match it's predicting. This
  includes: no using final-season tables to predict early-season matches, no
  using post-match odds movement, no using a model version trained on data
  that includes the test set. When adding a new feature or data source, ask
  explicitly "would this have existed at prediction time?" before wiring it
  into training or inference.
- **Probability calibration must be measurable.** Every model that outputs a
  probability must be checkable against realized outcomes (Brier score,
  calibration curve/reliability diagram, log loss). A model with no way to
  measure its calibration is not shippable, regardless of how plausible its
  logic looks.
- **Model changes require validation against baseline.** A change to model
  logic, weights, or ensemble composition must be backtested against the
  current production baseline before merging, with the comparison (sample
  size, Brier score / ROI / hit-rate delta) stated in the PR. "It should be
  more accurate" is not a validation result.
- **External data sources earn their place.** A new data source is adopted
  because it measurably improves calibration/Brier score on held-out data,
  not because it seems intuitively useful.
- **League validation gate (fully enforced).** The ingestion worker defaults
  to the four validated leagues (PL 39, Bundesliga 78, Ligue 1 61, La Liga
  140).  `--all-leagues` widens ingestion scope for research, but the signal
  pipeline enforces a hard publication barrier: `_upcoming_unpredicted_fixtures()`
  JOINs `Competition` and filters `Competition.validated IS TRUE` before any
  feature extraction or inference — unvalidated leagues can never generate
  live signals regardless of how many reliability snapshots they accumulate.
  To promote a new league to production, set `Competition.validated = True`
  for its row (a data migration is the correct path, not an ad-hoc UPDATE).
  **Documented exception — Daily Picks** (owner decision 2026-09-23, see
  `docs/ACCUMULATOR_POLICY.md`): the separately labelled, paper-only,
  unstaked `daily_*` tickets may use archived research-stream forecasts from
  unvalidated leagues so the platform always publishes its daily minimum.
  They never pass through, relax, or count towards the value products.

### Retrospective research evaluator

`scripts/run_retrospective_eval.py` and `backend/services/retrospective_extraction.py`
implement a **non-PIT-certified** calibration evaluator for research use only.

Key design decisions that must be preserved:

- **Not PIT-certified.** Features are derived from canonical mutable fixture
  rows (`Fixture.home_goals`, `Fixture.away_goals`, etc.), not from immutable
  provider snapshots whose `as_of_timestamp` precedes the simulated decision
  cutoff.  A zero `temporal_order_rejections` count does not imply historical
  availability — it only means ordering constraints within the supplied
  observation set are internally consistent.
- **Cross-season history is intentional.** The extractor queries all finished
  fixtures in the same competition regardless of season.  ELO ratings are
  a continuous chain across seasons; restricting to the current season
  would produce artificially uncertain ratings for early-season fixtures.
- **`leakage_rows_rejected` is always 0** for research runs.
  The weaker `temporal_order_rejections` count is stored only in the metrics
  JSON so it is queryable without polluting the PIT-leakage column semantic.
- **Provenance hashes**: every research experiment record embeds a
  `data_snapshot_ref` containing two SHA-256 digests — one over the full
  observation set (all fields that affect rejection or calibrator training),
  one over the historical training fixture inputs.  A change to any mutable
  fixture column changes the hash and flags the record as derived from
  different data.  The hash is an integrity identifier, not a restorable
  snapshot; canonical mutable state cannot be reconstructed from it alone.

## 5. Multi-Agent Collaboration

Qwantej is built with two coding agents — Claude Code and Codex — used in
different roles, not editing the same code at the same time. Two agents
modifying the same files concurrently produces merge conflicts, duplicate
migrations, or silently overwritten work, so the default workflow is a
serial hand-off, not parallel editing:

```
Claude Code
     ↓
Plan / build feature
     ↓
Git diff
     ↓
Codex
     ↓
Review / test / find bugs
     ↓
Claude or Codex fixes
     ↓
Tests
     ↓
Git commit
     ↓
GitHub
```

- **Claude Code** is the builder: plans and implements the change.
- **Codex** is the reviewer: runs tests, lints/type-checks, and hunts for
  bugs against the diff — especially the §4 risks (data leakage, look-ahead
  bias, broken reproducibility, calibration regressions).
- Whichever agent is better positioned applies the fix for what review
  found, but only one agent edits the working tree at a time.
- Only after tests pass again does the change get committed and pushed.
- If a task genuinely needs to run in parallel (e.g. independent backend and
  frontend work with no file overlap), split explicitly by directory and say
  so — the default assumption is serial hand-off, never silent concurrent
  editing.
- Database migrations are especially collision-prone even across a serial
  hand-off if branches diverge: check `alembic heads` shows a single head
  before merging a migration PR.

`AGENTS.md` (read by Codex) and `CLAUDE.md` (read by Claude Code) both state
the same core principles and defer to this document, so switching which
agent is building vs. reviewing on a given task doesn't change the rules
being enforced.

## 6. Deployment

1. Merge to `main` via PR.
2. Confirm CI (GitHub Actions) is green.
3. Run any pending Alembic migrations against the Neon database
   (`alembic upgrade head` with `DATABASE_URL` pointed at Neon —
   from a machine/CI runner that has the production connection string, never
   from a developer's local `.env`).
4. Trigger the Railway deploy manually — open the Railway dashboard, select
   the `qwantej-api` service, and click "Deploy" (or run `railway up --detach`
   from the repo root with the Railway CLI). This step is **never automatic**
   ("deploy on push" must be disabled in the Railway dashboard) — say
   explicitly when you're about to do it.
5. Trigger the `qwantej-scheduler` Railway service deploy the same way.
6. Trigger the `qwantej-frontend` Railway service deploy the same way — it is
   **not** automatic either. Confirm the resulting deployment builds
   successfully and its `NEXT_PUBLIC_API_URL` variable points at the correct
   `qwantej-api` public URL (visible under that service's "Settings →
   Domains" in the Railway dashboard); this is a Next.js build-time variable,
   so a value change only takes effect after `qwantej-frontend` is rebuilt,
   not just restarted.
7. Verify the deployed forecast/signal pipeline is producing archived output,
   not just that the app boots.

## 7. Definition of Done

Before calling a change complete:
- [ ] Tests added/updated for any new or changed calculation logic
- [ ] Migration included if schema changed, and `alembic heads` is singular
- [ ] No secrets introduced into source or committed `.env`
- [ ] If model/staking/settlement logic changed: backtest result stated in
      the PR description, compared against baseline
- [ ] No historical forecast/bet record deleted or silently overwritten
- [ ] Docs (`docs/`) updated if the change alters methodology, not just code

## 8. Tooling & Roles

| Component | Role |
|---|---|
| VS Code | Main development environment |
| Git | Version-control engine |
| GitHub | Authoritative code repository |
| Claude Code | Primary implementation / refactoring agent |
| Codex | Architecture, implementation, testing and independent review |
| ChatGPT | Product architecture, modelling decisions, specifications and difficult technical reasoning |
| GitHub branches/PRs | Safety barrier and change control |

Claude Code and Codex are both capable of architecture and implementation
work — the roles above describe emphasis, not an exclusive lane. The rule
that never bends regardless of who's doing what is §5: only one agent edits
the working tree at a time.
