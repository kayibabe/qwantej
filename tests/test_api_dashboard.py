from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.deps import get_db
from backend.main import app
from backend.models import Base, Competition, Fixture, FixtureStatus, OddsQuote, Season, Team


def test_today_status_fails_closed_when_no_data() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            response = client.get("/dashboard/today")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "collecting"
        assert body["tickets_available"] == 0
        assert body["data_freshness_utc"] is None
        assert body["checked_leagues"] == []
        assert body["observed_leagues"] == []
        assert body["observed_fixture_count"] == 0
        assert body["next_run_utc"] is None
    finally:
        app.dependency_overrides.clear()


def test_today_status_stays_collecting_when_scheduled_fixture_has_no_price() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    now = datetime.now(UTC)
    local_day = now.astimezone(ZoneInfo("Africa/Blantyre"))
    kickoff = local_day.replace(hour=20, minute=0, second=0, microsecond=0).astimezone(UTC)

    with factory() as session:
        competition = Competition(id=uuid.uuid4(), name="Validated League", validated=True)
        season = Season(id=uuid.uuid4(), competition=competition, label="2026")
        home = Team(id=uuid.uuid4(), name="Home")
        away = Team(id=uuid.uuid4(), name="Away")
        session.add(
            Fixture(
                id=uuid.uuid4(),
                competition=competition,
                season=season,
                home_team=home,
                away_team=away,
                kickoff_utc=kickoff,
                status=FixtureStatus.SCHEDULED,
            )
        )
        session.commit()

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            response = client.get("/dashboard/today")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "collecting"
        assert body["label"] == "Collecting prices"
        assert body["observed_leagues"] == ["Validated League"]
        assert body["observed_fixture_count"] == 1
    finally:
        app.dependency_overrides.clear()


def test_today_status_exposes_research_coverage_without_treating_it_as_validated() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    local_day = datetime.now(UTC).astimezone(ZoneInfo("Africa/Blantyre"))
    kickoff = local_day.replace(hour=20, minute=0, second=0, microsecond=0).astimezone(UTC)

    with factory() as session:
        competition = Competition(id=uuid.uuid4(), name="Research League", validated=False)
        season = Season(id=uuid.uuid4(), competition=competition, label="2026")
        session.add(
            Fixture(
                id=uuid.uuid4(),
                competition=competition,
                season=season,
                home_team=Team(id=uuid.uuid4(), name="Home"),
                away_team=Team(id=uuid.uuid4(), name="Away"),
                kickoff_utc=kickoff,
                status=FixtureStatus.SCHEDULED,
            )
        )
        session.commit()

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            response = client.get("/dashboard/today")
        assert response.status_code == 200
        body = response.json()
        assert body["checked_leagues"] == []
        assert body["observed_leagues"] == ["Research League"]
        assert body["observed_fixture_count"] == 1
        assert body["detail"] == (
            "1 scheduled fixture record observed in research coverage; "
            "no validated-league fixture or price observation is available for this date."
        )
    finally:
        app.dependency_overrides.clear()


def test_today_status_rejects_invalid_date() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            response = client.get("/dashboard/today", params={"date": "not-a-date"})
        assert response.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_today_status_scopes_to_requested_date() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yesterday_local = (
        datetime.now(UTC).astimezone(ZoneInfo("Africa/Blantyre")) - timedelta(days=1)
    )
    kickoff = yesterday_local.replace(hour=20, minute=0, second=0, microsecond=0).astimezone(UTC)

    with factory() as session:
        competition = Competition(id=uuid.uuid4(), name="Validated League", validated=True)
        season = Season(id=uuid.uuid4(), competition=competition, label="2026")
        home = Team(id=uuid.uuid4(), name="Home")
        away = Team(id=uuid.uuid4(), name="Away")
        session.add(
            Fixture(
                id=uuid.uuid4(),
                competition=competition,
                season=season,
                home_team=home,
                away_team=away,
                kickoff_utc=kickoff,
                status=FixtureStatus.SCHEDULED,
            )
        )
        session.commit()

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            today_response = client.get("/dashboard/today")
            yesterday_response = client.get(
                "/dashboard/today", params={"date": yesterday_local.date().isoformat()}
            )
        assert today_response.status_code == 200
        assert today_response.json()["status"] == "collecting"
        assert today_response.json()["detail"] == (
            "No current fixture or price observations are available yet."
        )

        assert yesterday_response.status_code == 200
        yesterday_body = yesterday_response.json()
        assert yesterday_body["date"] == yesterday_local.date().isoformat()
        assert yesterday_body["status"] == "no_ticket_recorded"
        assert yesterday_body["label"] == "No paper ticket recorded"
        assert yesterday_body["detail"] == (
            "No paper ticket was published for this date. 1 currently stored "
            "scheduled fixture record appears in research coverage."
        )
    finally:
        app.dependency_overrides.clear()


def test_today_status_marks_old_price_as_stale() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    now = datetime.now(UTC)
    local_day = now.astimezone(ZoneInfo("Africa/Blantyre"))
    kickoff = local_day.replace(hour=20, minute=0, second=0, microsecond=0).astimezone(UTC)

    with factory() as session:
        competition = Competition(id=uuid.uuid4(), name="Validated League", validated=True)
        season = Season(id=uuid.uuid4(), competition=competition, label="2026")
        home = Team(id=uuid.uuid4(), name="Home")
        away = Team(id=uuid.uuid4(), name="Away")
        fixture = Fixture(
            id=uuid.uuid4(),
            competition=competition,
            season=season,
            home_team=home,
            away_team=away,
            kickoff_utc=kickoff,
            status=FixtureStatus.SCHEDULED,
        )
        session.add(fixture)
        session.flush()
        session.add(
            OddsQuote(
                fixture_id=fixture.id,
                bookmaker="TestBook",
                market="1X2",
                selection="home",
                decimal_odds=2.0,
                captured_at=now.replace(microsecond=0) - timedelta(hours=3),
                source="test",
            )
        )
        session.commit()

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            response = client.get("/dashboard/today")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "stale"
        assert body["label"] == "Prices need refreshing"
    finally:
        app.dependency_overrides.clear()
