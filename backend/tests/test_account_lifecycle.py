"""Account/session lifecycle reconciliation and admin-key separation."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.models import BillingSubscription, User
from app.services.account_lifecycle import (
    expire_stale_pro_subscriptions,
    prune_auth_sessions,
    reconcile_account_lifecycle,
)


@pytest.mark.asyncio
async def test_prune_auth_sessions_deletes_beyond_retention():
    result = SimpleNamespace(rowcount=3)
    db = SimpleNamespace(execute=AsyncMock(return_value=result))

    assert await prune_auth_sessions(
        db, now=datetime(2026, 11, 5, tzinfo=timezone.utc)
    ) == 3
    statement = db.execute.call_args.args[0]
    assert statement.table.name == "user_sessions"


def _subscription(*, subscription_id: int, user_id: int, last_paid_at: datetime):
    return BillingSubscription(
        id=subscription_id,
        user_id=user_id,
        provider="flutterwave",
        provider_plan_id="plan-1",
        status="active",
        last_paid_at=last_paid_at,
    )


def _user(*, user_id: int, plan: str = "pro", plan_source: str = "flutterwave"):
    return User(
        id=user_id,
        username=f"user{user_id}",
        email=f"user{user_id}@example.com",
        password_hash="hash",
        plan=plan,
        plan_source=plan_source,
        account_status="active",
    )


class _Scalars:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


@pytest.mark.asyncio
async def test_expire_stale_pro_subscription_downgrades_and_audits():
    now = datetime(2026, 11, 5, tzinfo=timezone.utc)
    subscription = _subscription(
        subscription_id=1,
        user_id=7,
        last_paid_at=now - timedelta(days=40),
    )
    user = _user(user_id=7)
    db = SimpleNamespace(
        execute=AsyncMock(return_value=_Scalars([subscription])),
        get=AsyncMock(return_value=user),
        add=Mock(),
    )

    assert await expire_stale_pro_subscriptions(db, now=now) == 1
    assert subscription.status == "expired"
    assert user.plan == "free"
    assert user.plan_source == "manual"

    event = db.add.call_args.args[0]
    assert event.event_type == "expired"
    assert event.entity_type == "billing_subscription"
    assert event.payload["user_id"] == 7


@pytest.mark.asyncio
async def test_expired_subscription_does_not_override_a_manual_plan():
    now = datetime(2026, 11, 5, tzinfo=timezone.utc)
    subscription = _subscription(
        subscription_id=2,
        user_id=8,
        last_paid_at=now - timedelta(days=40),
    )
    user = _user(user_id=8, plan="pro", plan_source="manual")
    db = SimpleNamespace(
        execute=AsyncMock(return_value=_Scalars([subscription])),
        get=AsyncMock(return_value=user),
        add=Mock(),
    )

    assert await expire_stale_pro_subscriptions(db, now=now) == 1
    assert subscription.status == "expired"
    assert user.plan == "pro"
    assert user.plan_source == "manual"


@pytest.mark.asyncio
async def test_reconcile_combines_both_counts():
    now = datetime(2026, 11, 5, tzinfo=timezone.utc)
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[SimpleNamespace(rowcount=2), _Scalars([])]),
        get=AsyncMock(),
        add=Mock(),
    )

    assert await reconcile_account_lifecycle(db, now=now) == {
        "sessions_pruned": 2,
        "subscriptions_expired": 0,
    }
