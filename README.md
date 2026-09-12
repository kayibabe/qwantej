# Qwantej

A football forecasting laboratory: historical and live match data feed an
ensemble of statistical models (Poisson, ZINB, Bayesian) into a calibrated,
value-driven, risk-controlled accumulator engine. Every forecast is
archived and measured against realized outcomes.

## Status

The implementation is through Phase 11, with Phase 12 evidence and governance
closure now in progress. The system includes point-in-time storage, immutable
forecast lineage, baseline models, calibration, value and risk controls,
settlement, reliability/KPI tracking, the API/dashboard, validated-league
publication gating, retries, security, and disposable backup/restore drills.
Signals and accumulators remain research/paper-only until a genuinely
pre-kickoff PIT archive passes the model-governance promotion criteria. Run
`python scripts/run_readiness_report.py` for the current fail-closed decision.

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
