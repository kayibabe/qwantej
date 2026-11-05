"""Scheduled account and session lifecycle reconciliation.

These jobs are deliberately separate from request handling: a browser request
must never silently downgrade a subscription or prune authentication rows.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AuditEvent, BillingSubscription, User, UserSession
from app.services.auth_tokens import prune_auth_tokens


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def prune_auth_sessions(db: AsyncSession, now: datetime | None = None) -> int:
    """Delete sessions that expired or were revoked beyond the retention window."""
    cutoff = (now or _utc_now()) - timedelta(days=settings.auth_session_retention_days)
    result = await db.execute(
        delete(UserSession).where(
            or_(
                UserSession.expires_at < cutoff,
                UserSession.revoked_at < cutoff,
            )
        )
    )
    return int(result.rowcount or 0)


async def expire_stale_pro_subscriptions(db: AsyncSession, now: datetime | None = None) -> int:
    """Downgrade active Pro subscriptions that have not paid within period + grace."""
    current = now or _utc_now()
    cutoff = current - timedelta(
        days=settings.pro_subscription_period_days + settings.pro_subscription_grace_days
    )
    result = await db.execute(
        select(BillingSubscription).where(
            BillingSubscription.provider == "flutterwave",
            BillingSubscription.status == "active",
            BillingSubscription.last_paid_at < cutoff,
        )
    )
    expired = 0
    for subscription in result.scalars().all():
        user = await db.get(User, subscription.user_id)
        subscription.status = "expired"
        if user is not None and user.plan_source == "flutterwave":
            user.plan = "free"
            user.plan_source = "manual"
        db.add(
            AuditEvent(
                entity_type="billing_subscription",
                entity_id=str(subscription.id),
                event_type="expired",
                actor="account_lifecycle",
                reason="No successful payment within the subscription period and grace window",
                payload={
                    "user_id": subscription.user_id,
                    "last_paid_at": subscription.last_paid_at.isoformat(),
                    "period_days": settings.pro_subscription_period_days,
                    "grace_days": settings.pro_subscription_grace_days,
                },
            )
        )
        expired += 1
    return expired


async def reconcile_account_lifecycle(
    db: AsyncSession, now: datetime | None = None
) -> dict[str, int]:
    """Run both idempotent lifecycle checks in one transaction."""
    return {
        "sessions_pruned": await prune_auth_sessions(db, now),
        "tokens_pruned": await prune_auth_tokens(db, now),
        "subscriptions_expired": await expire_stale_pro_subscriptions(db, now),
    }
