"""Tests for accumulator ticket results grouped by year/month/day.

Covers the pure derivation/tally (``qwantej.performance.accumulator_results``)
and GET /performance/accumulator-results against a real SQLAlchemy session.
"""

from __future__ import annotations

import itertools
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
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
from backend.models.settlements import Settlement, SettlementOutcome, TicketStatus
from qwantej.performance.accumulator_results import (
    TicketRecord,
    derive_ticket_result,
    flat_unit_profit,
    period_key,
    tally_by_period,
)

# ---------------------------------------------------------------------------
# Pure derivation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("legs", "expected"),
    [
        (["win", "win", "win"], "won"),
        (["win", "void", "win"], "won"),  # void leg drops out
        (["win", "push"], "won"),
        (["win", "loss", "win"], "lost"),
        (["loss", None, None], "lost"),  # dead before the other legs finish
        (["win", None], "pending"),
        ([None, None], "pending"),
        (["void", "push"], "void"),
        ([], "void"),
    ],
)
def test_derive_ticket_result(legs, expected):
    assert derive_ticket_result(legs) == expected


def test_voided_ticket_is_void_even_with_winning_legs():
    assert derive_ticket_result(["win", "win"], ticket_voided=True) == "void"


def test_unknown_leg_outcome_is_rejected():
    with pytest.raises(ValueError, match="unknown leg outcome"):
        derive_ticket_result(["win", "half-win"])


def test_period_key_uses_utc_calendar():
    # 23:30 on 31 Dec in UTC-2 is already 1 Jan in UTC.
    ts = datetime(2026, 12, 31, 23, 30, tzinfo=timezone(timedelta(hours=-2)))
    assert period_key(ts, "day") == "2027-01-01"
    assert period_key(ts, "month") == "2027-01"
    assert period_key(ts, "year") == "2027"
    # Naive timestamps are read as UTC.
    assert period_key(datetime(2026, 9, 7, 23, 59), "day") == "2026-09-07"


def test_period_key_rejects_unknown_granularity():
    with pytest.raises(ValueError):
        period_key(datetime(2026, 9, 7, tzinfo=UTC), "week")  # type: ignore[arg-type]


def test_tally_groups_by_period_and_product_newest_first():
    d1 = datetime(2026, 9, 6, 8, tzinfo=UTC)
    d2 = datetime(2026, 9, 7, 8, tzinfo=UTC)
    records = [
        TicketRecord("core", d1, "won"),
        TicketRecord("core", d1, "lost"),
        TicketRecord("daily_safe", d1, "won"),
        TicketRecord("core", d2, "pending"),
        TicketRecord("core", d2, "void"),
    ]

    by_day = tally_by_period(records, "day")
    assert [p.period for p in by_day] == ["2026-09-07", "2026-09-06"]
    sep6 = {t.product: t for t in by_day[1].products}
    assert (sep6["core"].won, sep6["core"].lost, sep6["core"].total) == (1, 1, 2)
    assert sep6["core"].win_rate == pytest.approx(0.5)
    assert sep6["daily_safe"].win_rate == 1.0
    sep7_core = by_day[0].products[0]
    assert (sep7_core.pending, sep7_core.void) == (1, 1)
    assert sep7_core.win_rate is None  # nothing decided yet

    by_month = tally_by_period(records, "month")
    assert len(by_month) == 1
    core = next(t for t in by_month[0].products if t.product == "core")
    assert (core.won, core.lost, core.void, core.pending) == (1, 1, 1, 1)


def test_tally_of_nothing_is_empty():
    assert tally_by_period([], "year") == []


@pytest.mark.parametrize(
    ("result", "odds", "expected"),
    [("won", 3.5, 2.5), ("lost", 3.5, -1.0), ("void", None, 0.0), ("pending", None, None)],
)
def test_flat_unit_profit(result, odds, expected):
    profit = flat_unit_profit(result, odds)
    assert profit is None if expected is None else profit == pytest.approx(expected)


def test_flat_unit_profit_needs_odds_for_a_win():
    with pytest.raises(ValueError, match="settlement odds"):
        flat_unit_profit("won", None)


def test_tally_sums_profit_of_decided_tickets_only():
    d = datetime(2026, 9, 6, 8, tzinfo=UTC)
    records = [
        TicketRecord("core", d, "won", 2.5),
        TicketRecord("core", d, "lost", -1.0),
        TicketRecord("core", d, "void", 0.0),
        TicketRecord("core", d, "pending"),  # no profit yet
        TicketRecord("alpha", d, "lost", -1.0),
    ]
    by_product = {t.product: t for t in tally_by_period(records, "day")[0].products}
    assert by_product["core"].profit_units == pytest.approx(1.5)
    assert by_product["alpha"].profit_units == pytest.approx(-1.0)
    # Records built without a profit (older callers) still tally to zero.
    legacy = tally_by_period([TicketRecord("core", d, "won")], "day")
    assert legacy[0].products[0].profit_units == 0.0


# ---------------------------------------------------------------------------
# API over a real session
# ---------------------------------------------------------------------------

SEP6 = datetime(2026, 9, 6, 7, 0, tzinfo=UTC)
SEP7 = datetime(2026, 9, 7, 7, 0, tzinfo=UTC)
AUG31 = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)
DEC31_2025 = datetime(2025, 12, 31, 7, 0, tzinfo=UTC)


class _Seeder:
    def __init__(self, session: Session) -> None:
        self.s = session
        comp = Competition(name="EPL")
        ssn = Season(competition=comp, label="2026/27")
        home, away = Team(name="H"), Team(name="A")
        self.fixture = Fixture(
            competition=comp,
            season=ssn,
            home_team=home,
            away_team=away,
            kickoff_utc=SEP6,
            status=FixtureStatus.FINISHED,
            home_goals=1,
            away_goals=0,
        )
        session.add_all([comp, ssn, home, away, self.fixture])
        session.flush()
        self._clock = itertools.count()

    def _settle(self, prediction_id: uuid.UUID, outcome: str, *, supersedes=None) -> Settlement:
        row = Settlement(
            subject_type="prediction",
            subject_id=prediction_id,
            outcome=SettlementOutcome(outcome),
            settled_at=SEP7 + timedelta(minutes=next(self._clock)),
            supersedes_id=supersedes,
        )
        self.s.add(row)
        self.s.flush()
        return row

    def ticket(
        self,
        product: str,
        published_at: datetime,
        legs: list[str | None],
        *,
        status: TicketStatus = TicketStatus.PENDING,
    ) -> list[uuid.UUID]:
        acca = Accumulator(
            product=product,
            optimiser_version="v1",
            policy_version="v1",
            combined_odds=3.5,
            conservative_joint_probability=0.3,
            stressed_joint_probability=0.25,
            objective_score=0.9,
            dependence_penalty_applied=0.0,
            published_at=published_at,
            status=status,
        )
        self.s.add(acca)
        self.s.flush()
        prediction_ids = []
        for idx, outcome in enumerate(legs):
            p = Prediction(
                fixture_id=self.fixture.id,
                prediction_timestamp=published_at - timedelta(hours=1),
                decision_as_of=published_at - timedelta(hours=1),
                market="1X2",
                selection="home",
                conservative_probability=0.6,
                executable_odds=1.8,
            )
            self.s.add(p)
            self.s.flush()
            self.s.add(
                AccumulatorLeg(
                    accumulator_id=acca.id,
                    prediction_id=p.id,
                    leg_index=idx,
                    fixture_id=self.fixture.id,
                    league_id="39",
                    market_family="1X2",
                    selection="home",
                    decimal_odds=1.8,
                    conservative_probability=0.6,
                    edge=0.02,
                    qss=85.0,
                )
            )
            if outcome is not None:
                self._settle(p.id, outcome)
            prediction_ids.append(p.id)
        self.s.flush()
        return prediction_ids


@pytest.fixture()
def client():
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
        t = _Seeder(seed)
        # 2026-09-06
        t.ticket("core", SEP6, ["win", "win", "win"])            # won
        t.ticket("core", SEP6, ["win", "loss", None])            # lost
        t.ticket("daily_safe", SEP6, ["win", "void"])            # won
        t.ticket("growth", SEP6, ["win", "win"], status=TicketStatus.VOID)  # void
        # 2026-09-07
        t.ticket("core", SEP7, ["win", None])                    # pending
        t.ticket("daily_safe", SEP7, ["loss", "win"])            # lost
        # 2026-08-31 — first leg's loss later corrected to a win -> won
        fixed = t.ticket("alpha", AUG31, ["loss", "win"])
        original = seed.query(Settlement).filter_by(subject_id=fixed[0]).one()
        t._settle(fixed[0], "win", supersedes=original.id)
        # 2025-12-31
        t.ticket("core", DEC31_2025, ["void", "push"])           # void
        seed.commit()

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def _products(period: dict) -> dict[str, dict]:
    return {p["product"]: p for p in period["products"]}


def test_daily_results(client):
    body = client.get("/performance/accumulator-results").json()
    assert body["granularity"] == "day"
    assert [p["period"] for p in body["periods"]] == [
        "2026-09-07", "2026-09-06", "2026-08-31", "2025-12-31",
    ]
    assert body["total_periods"] == 4

    sep6 = _products(body["periods"][1])
    assert (sep6["core"]["won"], sep6["core"]["lost"], sep6["core"]["total"]) == (1, 1, 2)
    assert sep6["core"]["win_rate"] == pytest.approx(0.5)
    assert sep6["core"]["daily_pick"] is False
    assert sep6["daily_safe"]["won"] == 1
    assert sep6["daily_safe"]["daily_pick"] is True
    assert sep6["growth"]["void"] == 1
    assert sep6["growth"]["win_rate"] is None

    sep7 = _products(body["periods"][0])
    assert sep7["core"]["pending"] == 1
    assert sep7["daily_safe"]["lost"] == 1

    # Superseded settlement is ignored: the corrected win decides the ticket.
    aug31 = _products(body["periods"][2])
    assert (aug31["alpha"]["won"], aug31["alpha"]["lost"]) == (1, 0)

    dec31 = _products(body["periods"][3])
    assert dec31["core"]["void"] == 1


def test_monthly_and_yearly_results(client):
    months = client.get(
        "/performance/accumulator-results", params={"granularity": "month"}
    ).json()
    assert [p["period"] for p in months["periods"]] == ["2026-09", "2026-08", "2025-12"]
    sep_core = _products(months["periods"][0])["core"]
    assert (sep_core["won"], sep_core["lost"], sep_core["pending"]) == (1, 1, 1)

    years = client.get(
        "/performance/accumulator-results", params={"granularity": "year"}
    ).json()
    assert [p["period"] for p in years["periods"]] == ["2026", "2025"]
    y2026 = _products(years["periods"][0])
    assert y2026["daily_safe"]["won"] == 1 and y2026["daily_safe"]["lost"] == 1
    assert y2026["daily_safe"]["win_rate"] == pytest.approx(0.5)


def test_period_profit_is_flat_unit_pnl_of_decided_tickets(client):
    """Every leg is priced 1.8; void legs drop out of a win, pending adds nothing."""
    days = client.get("/performance/accumulator-results").json()["periods"]
    sep7, sep6, aug31, dec31 = (_products(p) for p in days)
    assert sep6["core"]["profit_units"] == pytest.approx((1.8**3 - 1) - 1)  # won + lost
    assert sep6["daily_safe"]["profit_units"] == pytest.approx(0.8)  # void leg dropped
    assert sep6["growth"]["profit_units"] == 0.0  # voided ticket
    assert sep7["core"]["profit_units"] == 0.0  # still pending
    assert sep7["daily_safe"]["profit_units"] == pytest.approx(-1.0)
    assert aug31["alpha"]["profit_units"] == pytest.approx(1.8**2 - 1)  # corrected win
    assert dec31["core"]["profit_units"] == 0.0

    years = client.get(
        "/performance/accumulator-results", params={"granularity": "year"}
    ).json()["periods"]
    assert _products(years[0])["daily_safe"]["profit_units"] == pytest.approx(0.8 - 1)


def test_filters_and_limit(client):
    body = client.get(
        "/performance/accumulator-results",
        params={"product": "core", "since": "2026-01-01T00:00:00Z"},
    ).json()
    assert [p["period"] for p in body["periods"]] == ["2026-09-07", "2026-09-06"]
    assert all(
        prod["product"] == "core" for p in body["periods"] for prod in p["products"]
    )

    window = client.get(
        "/performance/accumulator-results",
        params={"since": "2026-09-06T00:00:00Z", "until": "2026-09-07T00:00:00Z"},
    ).json()
    assert [p["period"] for p in window["periods"]] == ["2026-09-06"]

    limited = client.get(
        "/performance/accumulator-results", params={"limit": 2}
    ).json()
    assert [p["period"] for p in limited["periods"]] == ["2026-09-07", "2026-09-06"]
    assert limited["total_periods"] == 4


@pytest.mark.parametrize(
    "params",
    [
        {"granularity": "week"},
        {"since": "2026-09-07T00:00:00Z", "until": "2026-09-06T00:00:00Z"},
        {"limit": 0},
    ],
)
def test_invalid_parameters_are_rejected(client, params):
    assert client.get("/performance/accumulator-results", params=params).status_code == 422


def test_empty_database_returns_no_periods():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def _override():
        with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _override
    try:
        with TestClient(app) as c:
            body = c.get("/performance/accumulator-results").json()
        assert body == {"granularity": "day", "periods": [], "total_periods": 0}
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
