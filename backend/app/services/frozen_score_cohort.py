"""Freeze and score the 25 October snapshot pilot; database access is read-only.

This pilot is separate from the gated 180-day prospective holdout.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path

from sqlalchemy import select, text

from app.database import AsyncSessionLocal, engine
from app.models import Match, Prediction
from app.services.score_distribution_evaluation import (
    _binary_metrics, _paired_baseline_metrics, _valid_score_snapshot_parameters,
    evaluate_score_rate_snapshots,
)
from app.services.settlement import evaluate_selection


CUTOFF = datetime(2026, 10, 25, 5, 37, tzinfo=timezone.utc)
DAY = datetime(2026, 10, 25, tzinfo=timezone.utc)
END = datetime(2026, 10, 26, tzinfo=timezone.utc)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode()).hexdigest()


def code_digest():
    root = Path(__file__).parent
    return digest({name: sha256((root / name).read_bytes()).hexdigest() for name in (
        "frozen_score_cohort.py", "score_distribution_evaluation.py",
        "settlement.py", "market_catalog.py", "models/poisson_dc.py",
    )})


async def freeze(db):
    # Reconstruct the documented pre-outcome cutoff, never today's latest run.
    pairs = (await db.execute(select(Prediction, Match).join(
        Match, Match.id == Prediction.match_id
    ).where(Prediction.model_run_id.is_not(None), Prediction.model_version == "0.3.0",
            Prediction.created_at <= CUTOFF, Match.kickoff_at < END))).all()
    latest = {}
    for prediction, match in pairs:
        forecast_at = prediction.decision_at or prediction.created_at
        if forecast_at >= match.kickoff_at or forecast_at > CUTOFF:
            continue
        key = (match.id, prediction.market)
        rank = (forecast_at, prediction.id)
        if key not in latest or rank > latest[key][0]:
            latest[key] = (rank, prediction, match)
    forecasts, history = [], []
    for _, prediction, match in latest.values():
        if match.kickoff_at < DAY:
            if (match.status.value != "finished" or match.excluded_from_models
                    or match.home_goals is None or match.away_goals is None):
                continue
            if prediction.poisson_prob is None:
                continue
            outcome = evaluate_selection(prediction.market, match.home_goals, match.away_goals).value
            if outcome in ("won", "lost"):
                history.append(dict(match_id=match.id, prediction_id=prediction.id,
                                    market=prediction.market, competition_id=match.competition_id,
                                    kickoff_at=match.kickoff_at.isoformat(),
                                    outcome=int(outcome == "won")))
            continue
        snapshot = prediction.feature_snapshot or {}
        parameters = snapshot.get("joint_score_distributions", {}).get(
            "poisson_dixon_coles", {}).get("parameters", {})
        if not _valid_score_snapshot_parameters(parameters):
            continue
        if match.status.value != "scheduled" or match.kickoff_at <= datetime.now(timezone.utc):
            raise ValueError("Initial freeze must occur before every pilot fixture kicks off")
        forecasts.append(dict(
            prediction_id=prediction.id, match_id=match.id,
            api_football_id=match.api_football_id, competition_id=match.competition_id,
            market=prediction.market, forecast_at=(prediction.decision_at or prediction.created_at).isoformat(),
            created_at=prediction.created_at.isoformat(), kickoff_at=match.kickoff_at.isoformat(),
            model_run_id=prediction.model_run_id, model_version=prediction.model_version,
            forecast_build_id=snapshot.get("forecast_build_id"),
            feature_snapshot_sha256=digest(snapshot), score_distribution_parameters=parameters,
            poisson_prob=prediction.poisson_prob, model_probability=prediction.model_probability,
        ))
    forecasts.sort(key=lambda row: row["prediction_id"])
    history.sort(key=lambda row: row["prediction_id"])
    if len(forecasts) != 1332 or len({r["match_id"] for r in forecasts}) != 74:
        raise ValueError("Documented cohort does not reconcile to 74 fixtures / 1,332 forecasts")
    for row in forecasts:
        for field in ("poisson_prob", "model_probability"):
            p = row[field]
            if p is None or not math.isfinite(p) or not 0 <= p <= 1:
                raise ValueError(f"Invalid saved {field}")
    payload = dict(
        schema_version=1, cohort_id="score-snapshot-pilot-2026-10-25",
        frozen_at=datetime.now(timezone.utc).isoformat(), selection_cutoff=CUTOFF.isoformat(),
        research_only=True, confirmatory_holdout=False, analysis_code_sha256=code_digest(),
        baseline_policy="Latest pre-kickoff model_run 0.3.0 per fixture/market captured by cutoff; finished non-excluded matches on earlier UTC kickoff dates; Laplace (wins+1)/(n+2), minimum 30 nonvoid outcomes; inputs frozen before pilot kickoff.",
        capture_denominator=dict(cat_date="2026-10-25", fixtures=106, forecasts=1908,
                                 snapshot_fixtures=74, snapshot_forecasts=1332),
        forecasts=forecasts, baseline_history=history,
    )
    return dict(payload=payload, sha256=digest(payload))


def score(manifest, outcomes):
    payload = manifest["payload"]
    if digest(payload) != manifest["sha256"]:
        raise ValueError("Frozen manifest checksum mismatch")
    if payload["analysis_code_sha256"] != code_digest():
        raise ValueError("Analysis code changed since freeze; review and version separately")
    forecasts = payload["forecasts"]
    grouped = defaultdict(list)
    dispositions = Counter()
    rates = []
    for row in forecasts:
        result = outcomes.get(row["match_id"])
        disposition = "missing_match"
        if result:
            disposition = result["status"]
            if result.get("excluded_from_models"):
                disposition = "excluded_from_models"
            elif disposition == "finished":
                goals = (result.get("home_goals"), result.get("away_goals"))
                if any(type(g) is not int or g < 0 for g in goals):
                    disposition = "missing_or_invalid_score"
                else:
                    outcome = evaluate_selection(row["market"], *goals).value
                    disposition = "scored" if outcome in ("won", "lost") else "void"
                    rate_row = {**row, "kickoff_at": datetime.fromisoformat(row["kickoff_at"]),
                                "forecast_at": datetime.fromisoformat(row["forecast_at"]),
                                "home_goals": goals[0], "away_goals": goals[1]}
                    rates.append(rate_row)
                    if disposition == "scored":
                        grouped[row["market"]].append({**rate_row, "outcome": int(outcome == "won")})
        dispositions[disposition] += 1
    markets = {}
    for market in sorted({row["market"] for row in forecasts}):
        market_rows = grouped[market]
        fields = {}
        for field in ("poisson_prob", "model_probability"):
            rows = [{**row, "probability": row[field]} for row in market_rows]
            comparisons = {}
            for scope in ("global", "competition"):
                paired = []
                for row in rows:
                    prior = [h for h in payload["baseline_history"] if h["market"] == market
                             and datetime.fromisoformat(h["kickoff_at"]).date() < row["kickoff_at"].date()
                             and (scope == "global" or h["competition_id"] == row["competition_id"])]
                    if len(prior) >= 30:
                        paired.append({**row, "baseline_probability": (sum(h["outcome"] for h in prior) + 1) / (len(prior) + 2)})
                comparisons[scope] = {"model_on_paired_rows": _binary_metrics(paired),
                                      "baseline": _paired_baseline_metrics(paired)}
            fields[field] = dict(model=_binary_metrics(rows), comparisons=comparisons)
        markets[market] = fields
    return dict(
        cohort_id=payload["cohort_id"], manifest_sha256=manifest["sha256"],
        scored_at=datetime.now(timezone.utc).isoformat(), research_only=True,
        status="awaiting_outcomes" if not rates else "descriptive_scoring_available",
        total_fixtures=len({r["match_id"] for r in forecasts}), total_forecasts=len(forecasts),
        resolved_score_fixtures=len({r["match_id"] for r in rates}),
        forecast_dispositions=dict(dispositions), markets=markets,
        score_rate_diagnostics=evaluate_score_rate_snapshots(rates),
        outcome_snapshot=outcomes,
        limitations=["Selected snapshot pilot, not the registered 180-day holdout",
                     "Legacy forecasts have no scorer build ID",
                     "Complementary markets are dependent; 74 fixtures cannot meet the 500-fixture conclusion threshold",
                     "No qualification, calibration, settlement or promotion changes"],
    )


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "score"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            if args.action == "freeze":
                report = await freeze(db)
                destination = args.manifest
            else:
                manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
                ids = {r["match_id"] for r in manifest["payload"]["forecasts"]}
                matches = (await db.scalars(select(Match).where(Match.id.in_(ids)))).all()
                outcomes = {m.id: dict(status=m.status.value, home_goals=m.home_goals,
                                      away_goals=m.away_goals, fixture_status_code=m.fixture_status_code,
                                      excluded_from_models=m.excluded_from_models,
                                      kickoff_at=m.kickoff_at.isoformat(), updated_at=m.updated_at.isoformat()) for m in matches}
                report = score(manifest, outcomes)
                destination = args.output
            if destination is None:
                parser.error("score requires --output")
            with destination.open("x", encoding="utf-8") as stream:
                json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
                stream.write("\n")
            print(json.dumps({"output": str(destination), "status": report.get("status", "frozen"),
                              "sha256": report.get("sha256", report.get("manifest_sha256")),
                              "dispositions": report.get("forecast_dispositions")}))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
