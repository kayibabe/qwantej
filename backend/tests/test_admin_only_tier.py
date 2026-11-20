"""Balanced observation-only policy: visibility and portfolio accounting."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.v1 import tickets as tickets_api
from app.models import RunStatus, SelectionResult, TicketType
from app.services import performance
from app.models.custom_accumulator import CustomAccumulatorStatus
from app.services.ticket_visibility import is_admin_only, reader_ticket_types


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


def _ticket(ticket_type, *, result=SelectionResult.WON, version=1):
    return SimpleNamespace(
        id=1,
        target_date=date(2026, 11, 20),
        ticket_type=ticket_type,
        version=version,
        results=[SimpleNamespace(
            version=version, result=result, stake=1.0,
            return_amount=2.0, profit_loss=1.0,
        )],
        selections=[],
        model_version="0.3.0",
        pricing="market",
    )


def test_visibility_keeps_balanced_admin_only():
    assert is_admin_only(TicketType.BALANCED) is True
    assert is_admin_only(TicketType.SAFE) is False
    assert reader_ticket_types(False, admin=False) == [TicketType.SAFE]
    assert reader_ticket_types(False, admin=True) == [TicketType.SAFE, TicketType.BALANCED]


@pytest.mark.asyncio
async def test_balanced_ticket_is_missing_for_non_admin(monkeypatch):
    ticket = SimpleNamespace(ticket_type=TicketType.BALANCED)
    monkeypatch.setattr(tickets_api, "get_ticket_by_id", AsyncMock(return_value=ticket))

    with pytest.raises(HTTPException) as error:
        await tickets_api.get_ticket(
            5,
            request=SimpleNamespace(),
            db=SimpleNamespace(),
            user=SimpleNamespace(role="user", plan="pro"),
        )

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_balanced_is_settled_but_excluded_from_portfolio_summary(monkeypatch):
    safe = _ticket(TicketType.SAFE, result=SelectionResult.WON)
    balanced = _ticket(TicketType.BALANCED, result=SelectionResult.LOST)
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[_Scalars([safe, balanced]), _Scalars([])])
    )

    summary = await performance.performance_summary(db)

    assert summary["published_tickets"] == 1
    assert summary["settled_tickets"] == 1
    assert summary["wins"] == 1
    assert summary["losses"] == 0
    assert summary["profit_loss"] == 1.0
    assert summary["observation_only"]["ticket_types"] == ["balanced"]
    assert summary["observation_only"]["totals"]["settled_tickets"] == 1
    assert summary["observation_only"]["totals"]["profit_loss"] == 1.0
    by_type = {row["ticket_type"]: row for row in summary["by_ticket_type"]}
    assert by_type["safe"]["counted_in_portfolio"] is True
    assert by_type["balanced"]["observation_only"] is True
    assert by_type["balanced"]["profit_loss"] == 1.0


@pytest.mark.asyncio
async def test_daily_merge_accumulator_stays_out_of_portfolio_pnl():
    safe = _ticket(TicketType.SAFE)
    merged = SimpleNamespace(
        target_date=date(2026, 11, 20),
        status=CustomAccumulatorStatus.WON,
        stake=10.0,
        actual_return=25.0,
        combined_odds=2.5,
        settlement_details={"source": "daily_ticket_merge"},
    )
    manual = SimpleNamespace(
        target_date=date(2026, 11, 20),
        status=CustomAccumulatorStatus.WON,
        stake=10.0,
        actual_return=12.0,
        combined_odds=1.2,
        settlement_details={},
    )
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[_Scalars([safe]), _Scalars([merged, manual])])
    )

    summary = await performance.performance_summary(db)

    assert summary["my_accumulators"]["tickets"] == 1
    assert summary["my_accumulators"]["profit_loss"] == 2.0
    assert summary["observation_only"]["excluded_daily_merges"] == 1


class _QueryResult:
    def __init__(self, *, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_daily_ticket_counts_and_metadata_hide_balanced_from_non_admin(monkeypatch):
    generation = SimpleNamespace(
        id=7,
        input_count=50,
        output_count=2,
        status=RunStatus.PARTIAL,
        config_snapshot={
            "publication_summary": {
                "published_ticket_types": ["safe", "balanced"],
                "missing_public_ticket_types": ["balanced"],
                "relaxed_ticket_types": {"safe": 1, "balanced": 2},
                "horizon_ticket_types": {"safe": 1, "balanced": 1},
            }
        },
    )
    safe = SimpleNamespace(id=1, ticket_type=TicketType.SAFE)
    balanced = SimpleNamespace(id=2, ticket_type=TicketType.BALANCED)
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[
            _QueryResult(scalar=generation),
            _QueryResult(rows=[]),
            _QueryResult(rows=[]),
        ])
    )
    monkeypatch.setattr(
        tickets_api, "get_latest_published_tickets",
        AsyncMock(return_value=[safe, balanced]),
    )
    monkeypatch.setattr(
        tickets_api, "_ticket",
        lambda ticket, reveal: SimpleNamespace(ticket_id=ticket.id),
    )
    monkeypatch.setattr(
        tickets_api, "DailyTicketsOut",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )

    response = await tickets_api.get_daily_tickets(
        date(2026, 11, 20),
        db=db,
        user=SimpleNamespace(role="user", plan="free"),
    )

    assert response.conservative.ticket_id == 1
    assert response.balanced is None
    assert response.generated_ticket_count == 1
    assert response.missing_public_ticket_types == []
    assert response.relaxed_ticket_types == {"safe": 1}
    assert response.horizon_ticket_types == {"safe": 1}
    assert response.observation_only_ticket_types == []
