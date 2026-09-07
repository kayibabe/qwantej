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
state over an append-only bankroll ledger. The foundation also includes an
immutable point-in-time feature store and an API-Football acquisition adapter.
These components remain research-only
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
