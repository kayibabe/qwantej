"""One-time authentication tokens and transactional email behaviour."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.models import AuthToken
from app.services import auth_tokens, email_delivery


def _db(**kwargs):
    defaults = {
        "execute": AsyncMock(return_value=SimpleNamespace(rowcount=1)),
        "scalar": AsyncMock(return_value=None),
        "add": Mock(),
        "flush": AsyncMock(),
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_issue_token_stores_only_a_hash_and_expiry():
    db = _db()
    raw = await auth_tokens.issue_token(
        db, user_id=7, purpose=auth_tokens.PURPOSE_PASSWORD_RESET, ttl_minutes=30
    )

    assert len(raw) >= 32
    stored = db.add.call_args.args[0]
    assert isinstance(stored, AuthToken)
    assert stored.user_id == 7
    assert stored.purpose == auth_tokens.PURPOSE_PASSWORD_RESET
    assert stored.token_hash == auth_tokens.token_hash(raw)
    assert stored.token_hash != raw
    assert stored.used_at is None
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_consume_token_marks_a_valid_token_used():
    now = datetime(2026, 11, 5, tzinfo=timezone.utc)
    token = AuthToken(
        id=1,
        user_id=7,
        purpose=auth_tokens.PURPOSE_PASSWORD_RESET,
        token_hash=auth_tokens.token_hash("raw-token"),
        expires_at=now + timedelta(minutes=5),
    )
    db = _db(scalar=AsyncMock(return_value=token))

    consumed = await auth_tokens.consume_token(
        db, "raw-token", auth_tokens.PURPOSE_PASSWORD_RESET, now=now
    )

    assert consumed is token
    assert token.used_at == now
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_consume_token_rejects_expired_or_used_tokens():
    now = datetime(2026, 11, 5, tzinfo=timezone.utc)
    base = dict(
        id=1,
        user_id=7,
        purpose=auth_tokens.PURPOSE_PASSWORD_RESET,
        token_hash=auth_tokens.token_hash("raw-token"),
    )
    expired = AuthToken(**base, expires_at=now - timedelta(minutes=1))
    used = AuthToken(**base, expires_at=now + timedelta(minutes=5), used_at=now)

    for row in (expired, used):
        db = _db(scalar=AsyncMock(return_value=row))
        assert await auth_tokens.consume_token(
            db, "raw-token", auth_tokens.PURPOSE_PASSWORD_RESET, now=now
        ) is None
        db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_unconfigured_email_is_not_sent(monkeypatch):
    monkeypatch.setattr(email_delivery, "_configured", lambda: False)
    assert await email_delivery.send_email("user@example.com", "subject", "body") is False


@pytest.mark.asyncio
async def test_configured_email_is_delivered_off_the_event_loop(monkeypatch):
    calls = []
    monkeypatch.setattr(email_delivery, "_configured", lambda: True)
    monkeypatch.setattr(
        email_delivery,
        "_deliver",
        lambda to_email, subject, body: calls.append((to_email, subject, body)),
    )

    assert await email_delivery.send_email("user@example.com", "subject", "body") is True
    assert calls == [("user@example.com", "subject", "body")]
