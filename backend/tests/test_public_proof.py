"""Public settled-record sample used by the landing page."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1 import tickets as tickets_api
from app.models import TicketType


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


def _result(value: str, profit_loss: float, version: int = 1):
    return SimpleNamespace(
        version=version,
        result=SimpleNamespace(value=value),
        stake=1.0,
        return_amount=1.0 + profit_loss,
        profit_loss=profit_loss,
        settled_at=datetime(2026, 11, 8, 4, 5, tzinfo=timezone.utc),
    )


def _ticket(
    *,
    ticket_id: int,
    ticket_type: TicketType,
    target_date: date,
    result: str,
    published_at: datetime,
    profit_loss: float,
    selections=None,
):
    return SimpleNamespace(
        id=ticket_id,
        target_date=target_date,
        ticket_type=ticket_type,
        combined_odds=2.0295,
        published_at=published_at,
        results=[_result(result, profit_loss)],
        selections=selections or [],
    )


def _selection():
    match = SimpleNamespace(
        home_team=SimpleNamespace(name="Cuiaba"),
        away_team=SimpleNamespace(name="Juventude"),
        competition=SimpleNamespace(name="Brasileirao Serie B"),
        kickoff_at=datetime(2026, 11, 7, 19, 0, tzinfo=timezone.utc),
        status=SimpleNamespace(value="finished"),
        home_goals=1,
        away_goals=2,
    )
    return SimpleNamespace(
        position=1,
        market="1X2",
        selection="Home",
        result=SimpleNamespace(value="won"),
        match=match,
    )


@pytest.mark.asyncio
async def test_public_proof_returns_latest_decided_ticket_and_tier_metrics():
    sample_date = date(2026, 11, 7)
    published_at = datetime(2026, 11, 7, 10, 1, tzinfo=timezone.utc)
    safe_win = _ticket(
        ticket_id=174,
        ticket_type=TicketType.SAFE,
        target_date=sample_date,
        result="won",
        published_at=published_at,
        profit_loss=1.0295,
        selections=[_selection()],
    )
    safe_void = _ticket(
        ticket_id=173,
        ticket_type=TicketType.SAFE,
        target_date=date(2026, 11, 6),
        result="void",
        published_at=published_at,
        profit_loss=0.0,
    )
    balanced_loss = _ticket(
        ticket_id=175,
        ticket_type=TicketType.BALANCED,
        target_date=sample_date,
        result="lost",
        published_at=published_at,
        profit_loss=-1.0,
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=_Result([safe_win, safe_void, balanced_loss]))
    )

    proof = await tickets_api.get_public_proof(db)

    assert proof.days is None
    assert proof.sample_size == 3
    assert proof.first_settled_date == "2026-11-06"
    assert proof.last_settled_date == "2026-11-07"
    safe = next(tier for tier in proof.tiers if tier.ticket_type == "safe")
    balanced = next(tier for tier in proof.tiers if tier.ticket_type == "balanced")
    assert (safe.settled, safe.won, safe.lost, safe.void) == (2, 1, 0, 1)
    assert safe.win_rate == 1.0
    assert (balanced.settled, balanced.won, balanced.lost, balanced.void) == (1, 0, 1, 0)
    assert balanced.win_rate == 0.0

    # Void tickets return the stake, so they add a flat equity point and do
    # not count as turnover.
    assert safe.staked_units == 1.0
    assert safe.profit_units == pytest.approx(1.03)
    assert safe.roi == pytest.approx(1.0295)
    assert [point.date for point in safe.equity] == ["2026-11-06", "2026-11-07"]
    assert safe.equity[0].cumulative_units == 0.0
    assert safe.equity[1].cumulative_units == pytest.approx(1.03)
    assert [ticket.ticket_id for ticket in safe.recent_tickets] == [174, 173]
    assert balanced.profit_units == -1.0
    assert balanced.roi == -1.0
    assert [ticket.ticket_id for ticket in balanced.recent_tickets] == [175]

    assert proof.latest_ticket is not None
    assert proof.latest_ticket.ticket_id == 174
    assert proof.latest_ticket.result == "won"
    assert proof.latest_ticket.profit_units == 1.03
    assert proof.latest_ticket.publication_timing == "pre_kickoff"
    assert proof.latest_ticket.combined_odds == 2.0295
    assert proof.latest_ticket.legs[0].market == "1X2"
    assert proof.latest_ticket.legs[0].selection == "Home"
    assert not hasattr(proof.latest_ticket.legs[0], "best_odds")


@pytest.mark.asyncio
async def test_public_proof_applies_day_window(monkeypatch):
    monkeypatch.setattr(tickets_api, "cat_today", lambda: date(2026, 11, 8))
    ticket = _ticket(
        ticket_id=174,
        ticket_type=TicketType.SAFE,
        target_date=date(2026, 11, 7),
        result="won",
        published_at=datetime(2026, 11, 7, 10, 1, tzinfo=timezone.utc),
        profit_loss=0.5,
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=_Result([ticket])))

    proof = await tickets_api.get_public_proof(db, days=2)

    assert proof.days == 2
    assert proof.sample_size == 1
    statement = db.execute.await_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "target_date >= '2026-11-07'" in compiled
