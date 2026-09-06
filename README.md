# Qwantej

A football forecasting laboratory: historical and live match data feed an
ensemble of statistical models (Poisson, ZINB, Bayesian) into a calibrated,
value-driven, risk-controlled accumulator engine. Every forecast is
archived and measured against realized outcomes.

## Status

Rebuild through Phase 7: canonical point-in-time storage, immutable prediction
lineage, coherent baseline probability models, calibration monitoring, a
versioned conservative-probability policy, an explicit reason-coded Value Gate,
reproducible walk-forward evaluation against a de-vigged market baseline,
recency-weighted Bayesian LRS/MRS with an immutable league-market matrix, and a
risk engine — fractional Kelly, exposure caps and a drawdown-aware operating
state over an append-only bankroll ledger. These components remain research-only
until a real historical snapshot passes the model-governance promotion criteria.

## Start here

- [`DEVELOPMENT.md`](DEVELOPMENT.md) — the authoritative engineering
  specification: architecture, non-negotiable rules, model/forecast
  integrity requirements, the multi-agent workflow, deployment steps.
- [`AGENTS.md`](AGENTS.md) — instructions for Codex.
- [`CLAUDE.md`](CLAUDE.md) — instructions for Claude Code.

## Layout

```
backend/       FastAPI app — api, core, models, schemas, services, workers
frontend/      React / Next.js app
src/qwantej/   Core domain package — data, features, models (poisson/zinb/
               bayesian/ensemble), calibration, value, markets, accumulator,
               bankroll, performance
tests/         Test suites
docs/          architecture / modelling / decisions
```

See `DEVELOPMENT.md` for what belongs in each directory and the rules that
govern changes to them.

## Local development

```powershell
# Create the virtualenv and install the domain package + backend + dev tools
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[backend,dev]"

# Configure the database connection
copy .env.example .env
# edit .env — DATABASE_URL must point at a real Postgres instance

# Apply the schema
.venv\Scripts\alembic.exe upgrade head

# Run the test suite
.venv\Scripts\python.exe -m pytest
```

The `qwantej` package (`src/qwantej/`) has no FastAPI/Postgres dependency and
can be tested with just the base `dependencies` group — `pip install -e .`
— if you're only working on modelling/calibration logic.

## AI task router

The primary interface is the installable `@qwantej` participant in VS Code
Chat. It compares read-only technical proposals from Claude Code and Codex and
does not let either agent implement a change.

After installing `tools/vscode-qwantej-router/qwantej-ai-router.vsix`, open VS
Code Chat and enter:

```text
@qwantej /smart Describe the task here
```

Use `/deep` for major work, `/critical` for modelling or betting logic, and
`/doctor` to check the two CLIs. The participant remains selected after each
response, so follow-up tasks stay in the same router conversation.

The terminal interface remains available as a fallback. Run the diagnostic:

```powershell
python tools/ai_router.py doctor
```

When both CLIs are available, use **Terminal > Run Task** and select
`Qwantej: Smart AI Task`, or run:

```powershell
python tools/ai_router.py route "Describe the task here" --mode smart
```

Tasks involving odds, calibration, models, backtesting, or bankroll logic are
automatically escalated to critical mode. Proposal decisions are written to
`.ai/router_logs/`; implementation remains a separate, serial handoff so only
one agent can edit the working tree at a time.
