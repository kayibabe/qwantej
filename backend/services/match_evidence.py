"""Read-only, point-in-time match context for the ticket drill-down.

The context is deliberately derived from immutable/archived rows and only
uses completed fixtures strictly before the selected fixture's kickoff.  It is
presentation evidence, not a new prediction or settlement calculation.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.models import Fixture, FixtureStatus, Prediction

_FINAL_STATUSES = (FixtureStatus.FINISHED,)
_FORM_LIMIT = 10
_H2H_LIMIT = 7


def _team_name(fixture: Fixture, team_id: object) -> str:
    if fixture.home_team_id == team_id:
        return fixture.home_team.name
    return fixture.away_team.name


def _team_goals(fixture: Fixture, team_id: object) -> tuple[int, int]:
    if fixture.home_team_id == team_id:
        return fixture.home_goals or 0, fixture.away_goals or 0
    return fixture.away_goals or 0, fixture.home_goals or 0


def _form_row(fixture: Fixture, team_id: object) -> dict[str, Any]:
    goals_for, goals_against = _team_goals(fixture, team_id)
    opponent_id = (
        fixture.away_team_id
        if fixture.home_team_id == team_id
        else fixture.home_team_id
    )
    return {
        "date": fixture.kickoff_utc.date().isoformat() if fixture.kickoff_utc else None,
        "opponent": _team_name(fixture, opponent_id),
        "venue": "home" if fixture.home_team_id == team_id else "away",
        "result": "W" if goals_for > goals_against else "D" if goals_for == goals_against else "L",
        "score": f"{goals_for}–{goals_against}",
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(row["result"] == "W" for row in rows)
    draws = sum(row["result"] == "D" for row in rows)
    losses = len(rows) - wins - draws
    goals_for = sum(int(row["score"].split("–")[0]) for row in rows)
    goals_against = sum(int(row["score"].split("–")[1]) for row in rows)
    return {
        "played": len(rows),
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "points_per_game": round((wins * 3 + draws) / len(rows), 2) if rows else None,
    }


def build_match_evidence(
    db: Session, fixture: Fixture, prediction: Prediction | None,
) -> dict[str, Any]:
    """Build evidence without using the selected match's post-kickoff data."""
    cutoff = fixture.kickoff_utc
    common = (
        Fixture.status.in_(_FINAL_STATUSES),
        Fixture.home_goals.is_not(None),
        Fixture.away_goals.is_not(None),
        Fixture.kickoff_utc < cutoff,
    )

    def prior_for(team_id: object) -> list[Fixture]:
        stmt = (
            select(Fixture)
            .options(selectinload(Fixture.home_team), selectinload(Fixture.away_team))
            .where(*common, or_(Fixture.home_team_id == team_id, Fixture.away_team_id == team_id))
            .order_by(Fixture.kickoff_utc.desc())
            .limit(_FORM_LIMIT)
        )
        return list(db.scalars(stmt))

    home_history = prior_for(fixture.home_team_id)
    away_history = prior_for(fixture.away_team_id)
    h2h_stmt = (
        select(Fixture)
        .options(selectinload(Fixture.home_team), selectinload(Fixture.away_team))
        .where(
            *common,
            or_(
                and_(
                    Fixture.home_team_id == fixture.home_team_id,
                    Fixture.away_team_id == fixture.away_team_id,
                ),
                and_(
                    Fixture.home_team_id == fixture.away_team_id,
                    Fixture.away_team_id == fixture.home_team_id,
                ),
            ),
        )
        .order_by(Fixture.kickoff_utc.desc())
        .limit(_H2H_LIMIT)
    )
    h2h = list(db.scalars(h2h_stmt))
    home_form = [_form_row(row, fixture.home_team_id) for row in home_history]
    away_form = [_form_row(row, fixture.away_team_id) for row in away_history]

    archived_prediction = None
    if prediction is not None:
        archived_prediction = {
            "market": prediction.market,
            "selection": prediction.selection,
            "line": float(prediction.line) if prediction.line is not None else None,
            "ensemble_probability": prediction.ensemble_probability,
            "calibrated_probability": prediction.calibrated_probability,
            "conservative_probability": prediction.conservative_probability,
            "fair_market_probability": prediction.fair_market_probability,
            "edge_pp": prediction.edge_pp,
            "qss": prediction.qss,
            "dqs": prediction.dqs,
            "model_probabilities": prediction.model_probabilities or {},
            "decision_as_of": prediction.decision_as_of,
            "model_version_id": (
                str(prediction.model_version_id)
                if prediction.model_version_id
                else None
            ),
            "feature_version": prediction.feature_version,
            "calibration_version": prediction.calibration_version,
        }

    return {
        "as_of": cutoff,
        "home_form": home_form,
        "away_form": away_form,
        "home_summary": _summary(home_form),
        "away_summary": _summary(away_form),
        "h2h": [
            {
                "date": row.kickoff_utc.date().isoformat() if row.kickoff_utc else None,
                "home_team": row.home_team.name,
                "away_team": row.away_team.name,
                "home_score": row.home_goals,
                "away_score": row.away_goals,
            }
            for row in h2h
        ],
        "prediction": archived_prediction,
    }
