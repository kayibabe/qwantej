"""Regression coverage for request serialization and CPU work in page reads."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

from app.api import security
from app.api.v1 import selections
from app.services import parameter_sweep_jobs as jobs


@pytest.mark.asyncio
async def test_missing_sweep_returns_accepted_without_computing(monkeypatch):
    monkeypatch.setattr(selections, 'ready_scan', AsyncMock(return_value=None))
    enqueue = AsyncMock()
    monkeypatch.setattr(selections, 'enqueue_scan', enqueue)
    target = date(2026, 10, 17)
    response = await selections.get_parameter_sweep_selections(target, AsyncMock())
    assert response.status_code == 202
    assert response.headers['retry-after'] == '15'
    enqueue.assert_awaited_once_with(target)


@pytest.mark.asyncio
async def test_polling_enqueues_only_one_job(monkeypatch):
    from app.tasks import pipeline
    client = SimpleNamespace(set=AsyncMock(side_effect=[True, False]), delete=AsyncMock(), exists=AsyncMock(return_value=False))
    monkeypatch.setattr(jobs.cache, '_get_client', AsyncMock(return_value=client))
    enqueue = MagicMock()
    monkeypatch.setattr(pipeline.capture_parameter_sweep, 'delay', enqueue)
    await jobs.enqueue_scan(date(2026, 10, 17))
    await jobs.enqueue_scan(date(2026, 10, 17))
    enqueue.assert_called_once_with('2026-10-17')
    assert client.set.call_args.kwargs['nx'] is True


@pytest.mark.asyncio
async def test_broker_failure_allows_retry(monkeypatch):
    from app.tasks import pipeline
    client = SimpleNamespace(set=AsyncMock(return_value=True), delete=AsyncMock(), exists=AsyncMock(return_value=False))
    monkeypatch.setattr(jobs.cache, '_get_client', AsyncMock(return_value=client))
    monkeypatch.setattr(pipeline.capture_parameter_sweep, 'delay', MagicMock(side_effect=RuntimeError('offline')))
    with pytest.raises(RuntimeError):
        await jobs.enqueue_scan(date(2026, 10, 17))
    client.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_session_activity_uses_separate_nonblocking_transaction(monkeypatch):
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    browser_session = SimpleNamespace(id=1, user_id=1, last_seen_at=old)
    user = SimpleNamespace(account_status='active')
    page_db = SimpleNamespace(scalar=AsyncMock(return_value=browser_session), get=AsyncMock(return_value=user))
    activity = SimpleNamespace(last_seen_at=old)
    activity_db = AsyncMock()
    activity_db.scalar.return_value = activity
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=activity_db)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(security, 'AsyncSessionLocal', lambda: context)
    request = Request({'type': 'http', 'headers': [(b'cookie', f'{security.settings.auth_cookie_name}=token'.encode())]})
    assert await security.get_optional_current_user(request, page_db) is user
    assert browser_session.last_seen_at == old  # no autoflush/row lock in the page transaction
    assert activity.last_seen_at > old
    activity_db.commit.assert_awaited_once()
    assert activity_db.scalar.call_args.args[0]._for_update_arg.skip_locked is True
