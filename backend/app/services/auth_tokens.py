"""One-time password-reset and email-verification tokens."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AuthToken

PURPOSE_PASSWORD_RESET = "password_reset"
PURPOSE_EMAIL_VERIFICATION = "email_verification"


def token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


async def issue_token(
    db: AsyncSession, user_id: int, purpose: str, ttl_minutes: int
) -> str:
    """Invalidate older unused tokens for the purpose and issue a fresh one."""
    await db.execute(
        delete(AuthToken).where(
            AuthToken.user_id == user_id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        )
    )
    raw_token = secrets.token_urlsafe(32)
    db.add(
        AuthToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=token_hash(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
        )
    )
    await db.flush()
    return raw_token


async def consume_token(
    db: AsyncSession, raw_token: str, purpose: str, now: datetime | None = None
) -> AuthToken | None:
    """Return and mark a valid token used; expired or reused tokens return None."""
    current = now or datetime.now(timezone.utc)
    row = await db.scalar(
        select(AuthToken).where(
            AuthToken.token_hash == token_hash(raw_token),
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        )
    )
    if row is None or row.used_at is not None or _as_utc(row.expires_at) <= current:
        return None
    row.used_at = current
    await db.flush()
    return row


async def prune_auth_tokens(db: AsyncSession, now: datetime | None = None) -> int:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(
        days=settings.auth_token_retention_days
    )
    result = await db.execute(
        delete(AuthToken).where(
            or_(
                AuthToken.expires_at < cutoff,
                AuthToken.used_at < cutoff,
            )
        )
    )
    return int(result.rowcount or 0)
