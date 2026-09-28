"""Retired products stay in the append-only archive but out of every read.

A withdrawn product's already-published tickets (and their ticket
settlements) must not appear in the ticket archive, the day's ticket count,
the settlement log, or any performance report.
"""

from __future__ import annotations

from datetime import UTC, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from test_accumulator_results import SEP6, _Seeder

from backend.api.deps import get_db
from backend.api.routes.dashboard import PRODUCT_DAY_ZONE
from backend.main import app
from backend.models import Accumulator, Base
from backend.models.settlements import Settlement, SettlementOutcome, TicketStatus
from backend.services.performance import awaiting_settlement_count
from qwantej.accumulator.daily import RETIRED_PRODUCTS

[RETIRED] = sorted(RETIRED_PRODUCTS)


@pytest.fixture()
def seeded():
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
        t.ticket("daily_safe", SEP6, ["win", "win"], status=TicketStatus.SETTLED)
        t.ticket(RETIRED, SEP6, ["loss", "win"], status=TicketStatus.SETTLED)
        t.ticket(RETIRED, SEP6, ["win", None])  # still open, first leg kicked off
        for acca in seed.scalars(
            select(Accumulator).where(Accumulator.status == TicketStatus.SETTLED)
        ):
            seed.add(Settlement(
                subject_type="accumulator",
                subject_id=acca.id,
                outcome=(
                    SettlementOutcome.LOSS if acca.product == RETIRED
                    else SettlementOutcome.WIN
                ),
                settled_at=SEP6 + timedelta(hours=4),
                taken_odds=3.24,
                stake=1,
                profit_loss=-1 if acca.product == RETIRED else 2.24,
            ))
        seed.commit()
        retired_ids = [
            str(i) for i in seed.scalars(
                select(Accumulator.id).where(Accumulator.product == RETIRED)
            )
        ]

    with TestClient(app) as client:
        yield client, factory, retired_ids

    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def test_ticket_archive_and_detail_hide_retired_tickets(seeded):
    client, _, retired_ids = seeded
    page = client.get("/accumulators").json()
    assert page["total"] == 1
    assert [a["product"] for a in page["items"]] == ["daily_safe"]

    day = SEP6.astimezone(PRODUCT_DAY_ZONE).date().isoformat()
    assert client.get("/accumulators", params={"date": day}).json()["total"] == 1
    for ticket_id in retired_ids:
        assert client.get(f"/accumulators/{ticket_id}").status_code == 404


def test_day_ticket_count_ignores_retired_tickets(seeded):
    client, _, _ = seeded
    day = SEP6.astimezone(PRODUCT_DAY_ZONE).date().isoformat()
    body = client.get("/dashboard/today", params={"date": day}).json()
    assert body["tickets_available"] == 1


def test_performance_reports_exclude_retired_tickets(seeded):
    client, factory, _ = seeded
    report = client.get(
        "/performance/report", params={"subject_type": "accumulator"}
    ).json()
    assert report["n_settled"] == 1
    assert report["n_wins"] == 1 and report["n_losses"] == 0
    # Only the retired ticket is open with a kicked-off leg.
    assert report["n_awaiting"] == 0

    segments = client.get(
        "/performance/segments", params={"by": "product", "subject_type": "accumulator"}
    ).json()["segments"]
    assert set(segments) == {"daily_safe"}

    results = client.get("/performance/accumulator-results").json()["periods"]
    assert {p["product"] for period in results for p in period["products"]} == {"daily_safe"}
    only_retired = client.get(
        "/performance/accumulator-results", params={"product": RETIRED}
    ).json()
    assert only_retired["periods"] == []

    with factory() as s:
        # The open retired ticket has a kicked-off leg but is not "awaiting".
        assert awaiting_settlement_count(
            s, subject_type="accumulator", now=SEP6.astimezone(UTC) + timedelta(days=1)
        ) == 0


def test_settlement_log_excludes_retired_tickets(seeded):
    client, _, _ = seeded
    log = client.get("/settlements", params={"subject_type": "accumulator"}).json()
    assert log["total"] == 1
    summary = client.get(
        "/settlements/summary", params={"subject_type": "accumulator"}
    ).json()
    assert (summary["n_settled"], summary["n_wins"], summary["n_losses"]) == (1, 1, 0)
    # Prediction settlements (the forecast archive) are untouched.
    predictions = client.get("/settlements", params={"subject_type": "prediction"}).json()
    assert predictions["total"] == 5
