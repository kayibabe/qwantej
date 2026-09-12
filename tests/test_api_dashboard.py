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
