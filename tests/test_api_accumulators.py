"""Tests for GET /accumulators and GET /accumulators/{id} (Phase 10)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.deps import get_db
from backend.main import app
from backend.models import (
    Accumulator,
    AccumulatorLeg,
    Base,
    Competition,
    Fixture,
    FixtureStatus,
    Prediction,
    Season,
    Team,
)
from backend.models.settlements import TicketStatus
from backend.services.accumulator import persist_accumulator_decision
from qwantej.accumulator.decision import (
    AccumulatorDecision,
    AccumulatorProductDecision,
)
from qwantej.accumulator.optimiser import AccumulatorResult
from qwantej.accumulator.types import (
    AccumulatorRejectionReason,
    AccumulatorTicket,
    QualifiedSelection,
)
from qwantej.bankroll.state import OperatingState, ProductTier

NOW = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)
KICKOFF = NOW + timedelta(hours=2)


@pytest.fixture()
def seeded_client():
    """Client with one PENDING accumulator (2 legs) and one SETTLED accumulator."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _override():
        with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _override

    with factory() as seed:
        comp = Competition(name="EPL")
        ssn = Season(competition=comp, label="2026/27")
        home, away = Team(name="Home FC"), Team(name="Away FC")
        fixture = Fixture(
            competition=comp,
            season=ssn,
            home_team=home,
            away_team=away,
            kickoff_utc=KICKOFF,
            status=FixtureStatus.SCHEDULED,
        )
        seed.add_all([comp, ssn, home, away, fixture])
        seed.flush()

        p1 = Prediction(
            fixture_id=fixture.id,
            prediction_timestamp=NOW - timedelta(hours=1),
            decision_as_of=NOW - timedelta(hours=1),
            market="1X2",
            selection="home",
            conservative_probability=0.62,
            executable_odds=1.85,
            bookmaker="Bet365",
        )
        p2 = Prediction(
            fixture_id=fixture.id,
            prediction_timestamp=NOW - timedelta(hours=1),
            decision_as_of=NOW - timedelta(hours=1),
            market="BTTS",
            selection="yes",
            conservative_probability=0.55,
            executable_odds=1.72,
            bookmaker="Betway",
        )
        seed.add_all([p1, p2])
        seed.flush()

        acca1 = Accumulator(
            product="Core",
            optimiser_version="v1.0",
            policy_version="v1.0",
            combined_odds=3.19,
            conservative_joint_probability=0.34,
            stressed_joint_probability=0.28,
            objective_score=0.92,
            dependence_penalty_applied=0.0,
            published_at=NOW - timedelta(hours=1),
            status=TicketStatus.PENDING,
        )
        acca2 = Accumulator(
            product="Growth",
            optimiser_version="v1.0",
            policy_version="v1.0",
            combined_odds=5.80,
            conservative_joint_probability=0.18,
            stressed_joint_probability=0.14,
            objective_score=0.87,
            dependence_penalty_applied=0.01,
            published_at=NOW - timedelta(hours=2),
            status=TicketStatus.SETTLED,
        )
        seed.add_all([acca1, acca2])
        seed.flush()

        QUOTE_TS = NOW - timedelta(minutes=30)
        leg1 = AccumulatorLeg(
            accumulator_id=acca1.id,
            prediction_id=p1.id,
            leg_index=0,
            fixture_id=fixture.id,
            league_id="39",
            market_family="1X2",
            selection="home",
            decimal_odds=1.85,
            conservative_probability=0.62,
            edge=0.07,
            qss=88.0,
            bookmaker="Bet365",
            quote_captured_at=QUOTE_TS,
        )
        leg2 = AccumulatorLeg(
            accumulator_id=acca1.id,
            prediction_id=p2.id,
            leg_index=1,
            fixture_id=fixture.id,
            league_id="39",
            market_family="BTTS",
            selection="yes",
            decimal_odds=1.72,
            conservative_probability=0.55,
            edge=0.05,
            qss=85.0,
            bookmaker="Betway",
            quote_captured_at=QUOTE_TS,
        )
        seed.add_all([leg1, leg2])
        seed.commit()
        acca1_id = acca1.id
        acca2_id = acca2.id

    with TestClient(app) as client:
        yield client, acca1_id, acca2_id

    app.dependency_overrides.clear()


class TestListAccumulators:
    def test_returns_all(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get("/accumulators")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2

    def test_filter_by_status_pending(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get("/accumulators", params={"status": "pending"})
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == "pending"

    def test_legs_included(self, seeded_client) -> None:
        client, acca1_id, _ = seeded_client
        r = client.get("/accumulators", params={"status": "pending"})
        assert r.status_code == 200
        item = r.json()["items"][0]
        assert item["id"] == str(acca1_id)
        assert len(item["legs"]) == 2

    def test_legs_carry_fixture_display_fields(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get("/accumulators", params={"status": "pending"})
        leg = r.json()["items"][0]["legs"][0]
        assert leg["home_team"] == "Home FC"
        assert leg["away_team"] == "Away FC"
        assert leg["competition_name"] == "EPL"
        assert leg["kickoff_utc"] is not None

    def test_legs_carry_quote_captured_at(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get("/accumulators", params={"status": "pending"})
        leg = r.json()["items"][0]["legs"][0]
        assert leg["quote_captured_at"] is not None
        # The serialised value must parse to a datetime with the correct date and
        # wall-clock time.  SQLite strips tzinfo on read-back, so we compare the
        # naive time components rather than full UTC equality (PostgreSQL preserves
        # the offset and would pass either comparison).
        from datetime import datetime
        parsed = datetime.fromisoformat(leg["quote_captured_at"].replace("Z", "+00:00"))
        expected = NOW - timedelta(minutes=30)
        assert parsed.replace(tzinfo=None) == expected.replace(tzinfo=None)

    def test_legs_carry_bookmaker_attribution(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get("/accumulators", params={"status": "pending"})
        legs = r.json()["items"][0]["legs"]
        assert [leg["bookmaker"] for leg in legs] == ["Bet365", "Betway"]

    def test_legs_ordered_by_leg_index(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get("/accumulators", params={"status": "pending"})
        legs = r.json()["items"][0]["legs"]
        indices = [leg["leg_index"] for leg in legs]
        assert indices == sorted(indices)


class TestGetAccumulator:
    def test_returns_by_id(self, seeded_client) -> None:
        client, acca1_id, _ = seeded_client
        r = client.get(f"/accumulators/{acca1_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == str(acca1_id)
        assert data["product"] == "Core"
        assert len(data["legs"]) == 2

    def test_404_for_unknown_id(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get(f"/accumulators/{uuid.uuid4()}")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Service-path round-trip: persist_accumulator_decision → API → quote_captured_at
# ---------------------------------------------------------------------------

_QUOTE_TS = NOW - timedelta(minutes=45)
_PUBLISHED_AT = NOW + timedelta(seconds=1)
_LINEAGE = dict(
    model_version="model-v1",
    calibration_version="cal-v1",
    feature_version="feat-v1",
    code_commit="abc123",
)


def _make_qs(fixture_id: str, prediction_id: str, *, i: int) -> QualifiedSelection:
    return QualifiedSelection(
        prediction_id=prediction_id,
        fixture_id=fixture_id,
        league_id=f"L{i}",
        market_family="TOTALS",
        selection="Over 2.5",
        calibrated_probability=0.62,
        conservative_probability=0.60,
        decimal_odds=Decimal("1.70"),
        edge=0.11,
        qss=88.0,
        dqs=80.0,
        reliability=75.0,
        quote_timestamp=_QUOTE_TS,
        **_LINEAGE,
    )


def _make_result(
    ticket: AccumulatorTicket | None,
    product: ProductTier,
) -> AccumulatorResult:
    if ticket is not None:
        return AccumulatorResult(
            product=product,
            ticket=ticket,
            rejection_reason=None,
            legs_evaluated=len(ticket.legs),
            legs_qualified=len(ticket.legs),
            combinations_evaluated=1,
            combinations_rejected_odds_band=0,
            combinations_rejected_concentration=0,
            combinations_rejected_ticket_ev=0,
            search_truncated=False,
            policy_version=f"policy-{product.value}-v1",
            as_of=NOW,
        )
    return AccumulatorResult(
        product=product,
        ticket=None,
        rejection_reason=AccumulatorRejectionReason.INSUFFICIENT_QUALIFIED_LEGS,
        legs_evaluated=0,
        legs_qualified=0,
        combinations_evaluated=0,
        combinations_rejected_odds_band=0,
        combinations_rejected_concentration=0,
        combinations_rejected_ticket_ev=0,
        search_truncated=False,
        policy_version=f"policy-{product.value}-v1",
        as_of=NOW,
    )


@pytest.fixture()
def service_seeded_client():
    """Client whose accumulator is written by persist_accumulator_decision.

    This fixture exercises the full service → ORM → API path so that the
    quote_captured_at coverage cannot be satisfied by direct ORM construction.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _override():
        with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _override

    with factory() as seed:
        # Seed three fixtures, each with a competition, season, and prediction.
        pairs: list[tuple[Fixture, Prediction]] = []
        comp = Competition(name="Test League")
        ssn = Season(competition=comp, label="2026/27")
        seed.add_all([comp, ssn])
        seed.flush()
        for i in range(3):
            home = Team(name=f"Home{i} FC")
            away = Team(name=f"Away{i} FC")
            fix = Fixture(
                competition=comp,
                season=ssn,
                home_team=home,
                away_team=away,
                kickoff_utc=KICKOFF,
                status=FixtureStatus.SCHEDULED,
            )
            seed.add_all([home, away, fix])
            seed.flush()
            pred = Prediction(
                fixture_id=fix.id,
                prediction_timestamp=NOW - timedelta(hours=1),
                decision_as_of=NOW - timedelta(hours=1),
                market="TOTALS",
                selection="Over 2.5",
                conservative_probability=0.60,
                executable_odds=1.70,
                bookmaker="Bet365",
            )
            seed.add(pred)
            seed.flush()
            pairs.append((fix, pred))

        # Build domain legs with a known quote_timestamp (captured_at).
        domain_legs = tuple(
            _make_qs(str(fix.id), str(pred.id), i=i).to_leg()
            for i, (fix, pred) in enumerate(pairs)
        )
        from qwantej.accumulator.constraints import (
            combined_odds,
            conservative_joint_probability,
            dependence_penalty,
            stressed_joint_probability,
        )
        ticket = AccumulatorTicket(
            legs=domain_legs,
            product=ProductTier.CORE,
            combined_odds=combined_odds(domain_legs),
            conservative_joint_probability=conservative_joint_probability(domain_legs),
            stressed_joint_probability=stressed_joint_probability(domain_legs, 0.05),
            objective_score=0.40,
            dependence_penalty_applied=dependence_penalty(domain_legs),
        )
        products = tuple(
            AccumulatorProductDecision(
                product=p,
                result=_make_result(ticket if p is ProductTier.CORE else None, p),
                stake_decision=None,
            )
            for p in ProductTier
        )
        decision = AccumulatorDecision(
            as_of=NOW,
            operating_state=OperatingState.NORMAL,
            candidate_count=3,
            input_manifest_hash="c" * 64,
            products=products,
            paper_only=True,
        )
        persist_accumulator_decision(seed, decision, published_at=_PUBLISHED_AT)
        seed.commit()

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


class TestServicePathRoundTrip:
    def test_quote_captured_at_written_by_service_and_returned_by_api(
        self, service_seeded_client
    ) -> None:
        """quote_captured_at must survive persist_accumulator_decision → DB → API."""
        r = service_seeded_client.get("/accumulators")
        assert r.status_code == 200
        legs = r.json()["items"][0]["legs"]
        for leg in legs:
            assert leg["quote_captured_at"] is not None, (
                "quote_captured_at must be non-null for legs written by the service"
            )
            parsed = datetime.fromisoformat(
                leg["quote_captured_at"].replace("Z", "+00:00")
            )
            # Wall-clock comparison: SQLite strips tzinfo; PostgreSQL preserves it.
            assert parsed.replace(tzinfo=None) == _QUOTE_TS.replace(tzinfo=None)

    def test_bookmaker_written_by_service_and_returned_by_api(self, service_seeded_client) -> None:
        r = service_seeded_client.get("/accumulators")
        assert r.status_code == 200
        legs = r.json()["items"][0]["legs"]
        assert all(leg["bookmaker"] == "Bet365" for leg in legs)
