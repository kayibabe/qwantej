# Qwantej

A football forecasting laboratory: historical and live match data feed an
ensemble of statistical models (Poisson, ZINB, Bayesian) into a calibrated,
value-driven, risk-controlled accumulator engine. Every forecast is
archived and measured against realized outcomes.

## Status

Early rebuild (Phase 1 forecasting-lab pivot). The repository currently
holds the project scaffold and governance docs; application code is being
built out.

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
