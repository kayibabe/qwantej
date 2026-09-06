"""Structural persistence coverage for Phase 6 reliability snapshots."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import (
    Base,
    Competition,
    Fixture,
    FixtureStatus,
    Prediction,
    ReliabilitySnapshot,
    ReliabilityState,
    Season,
    Team,
)
from backend.services.reliability import archive_reliability_matrix
from qwantej.performance import ReliabilityObservation, build_reliability_matrix

NOW = datetime(2026, 9, 1, tzinfo=UTC)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


def _matrix():
    observations = [
        ReliabilityObservation(
            observation_id=str(index), league="EPL", market_family="O2.5",
            competition_class="tier-1", decision_as_of=NOW - timedelta(days=index + 2),
            outcome_observed_at=NOW - timedelta(days=index + 1),
            predicted_probability=0.7, outcome=index % 2,
            profit_units=0.8 if index % 2 else -1.0,
            closing_line_value=0.02, model_stability=0.9,
        )
        for index in range(10)
    ]
    return build_reliability_matrix(observations, evaluated_as_of=NOW)


def test_archive_matrix_round_trips_lineage_and_scores(session: Session) -> None:
    competition = Competition(name="EPL", country="England", tier=1)
    session.add(competition)
    session.flush()
    rows = archive_reliability_matrix(
        session, _matrix(), competition_ids={"EPL": competition.id},
        window_start=NOW - timedelta(days=30), input_snapshot_ref="snapshot:settled-v1",
        input_snapshot_hash="sha256:inputs", code_commit="abc123",
    )
    session.commit()
    session.expire_all()
    stored = session.query(ReliabilitySnapshot).one()
    assert rows[0].id == stored.id
    assert stored.status in set(ReliabilityState)
    assert 0 <= stored.segment_reliability <= 100
    assert stored.input_snapshot_hash == "sha256:inputs"
    assert stored.components["calibration"] >= 0


def test_archive_requires_every_competition_mapping(session: Session) -> None:
    with pytest.raises(ValueError, match="competition ids missing"):
        archive_reliability_matrix(
            session, _matrix(), competition_ids={},
            window_start=NOW - timedelta(days=30), input_snapshot_ref="snapshot:v1",
            input_snapshot_hash="sha256:inputs", code_commit="abc123",
        )


def test_database_rejects_invalid_effective_sample(session: Session) -> None:
    competition = Competition(name="EPL")
    session.add(competition)
    session.flush()
    snapshot = ReliabilitySnapshot(
        competition=competition, competition_class="tier-1", market_family="O2.5",
        evaluated_as_of=NOW, window_start=NOW - timedelta(days=30), window_end=NOW,
        policy_version="reliability-v1", observation_count=2,
        effective_sample_size=3, shrinkage_weight=0.1,
        league_reliability=50, market_reliability=50, segment_reliability=50,
        posterior_standard_deviation=0.1, conservative_lower_bound=0.3,
        status=ReliabilityState.RESTRICTED, grade="Reject", components={},
        diagnostics={}, future_rows_excluded=0, input_snapshot_ref="snapshot:v1",
        input_snapshot_hash="sha256:inputs", code_commit="abc123",
    )
    session.add(snapshot)
    with pytest.raises(IntegrityError):
        session.commit()


def test_prediction_links_exact_reliability_snapshot(session: Session) -> None:
    competition = Competition(name="EPL")
    season = Season(competition=competition, label="2026/27")
    home, away = Team(name="Home"), Team(name="Away")
    fixture = Fixture(
        competition=competition, season=season, home_team=home, away_team=away,
        kickoff_utc=NOW + timedelta(days=1), status=FixtureStatus.SCHEDULED,
    )
    session.add_all([competition, season, home, away, fixture])
    session.flush()
    snapshot = archive_reliability_matrix(
        session, _matrix(), competition_ids={"EPL": competition.id},
        window_start=NOW - timedelta(days=30), input_snapshot_ref="snapshot:v1",
        input_snapshot_hash="sha256:inputs", code_commit="abc123",
    )[0]
    prediction = Prediction(
        fixture=fixture, prediction_timestamp=NOW, decision_as_of=NOW,
        market="OU", selection="over", reliability_snapshot=snapshot,
        lrs=snapshot.league_reliability, mrs=snapshot.market_reliability,
        dynamic_states={"reliability": snapshot.status.value},
    )
    session.add(prediction)
    session.commit()
    session.expire_all()
    stored = session.query(Prediction).one()
    assert stored.reliability_snapshot.policy_version == "reliability-v1"
