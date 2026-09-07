"""Tests for Phase 11 retry logic in UrllibJsonTransport."""

from __future__ import annotations

import pytest

from backend.services.api_football_client import ApiFootballError, UrllibJsonTransport

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeHeaders:
    def items(self):
        return []


class _FakeResponse:
    def __init__(self, body: bytes = b'{"response": [], "paging": {"current": 1, "total": 1}}'):
        self.status = 200
        self.headers = _FakeHeaders()
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def read(self):
        return self._body


def _make_urlopen(fail_times: int = 0):
    """Return a fake urlopen that fails *fail_times* before succeeding."""
    call_count = [0]

    def _urlopen(req, timeout):
        call_count[0] += 1
        if call_count[0] <= fail_times:
            raise OSError(f"simulated error #{call_count[0]}")
        return _FakeResponse()

    _urlopen.call_count = call_count  # type: ignore[attr-defined]
    return _urlopen


# ---------------------------------------------------------------------------
# UrllibJsonTransport retry behaviour
# ---------------------------------------------------------------------------

def test_transport_succeeds_on_first_attempt(monkeypatch):
    import backend.services.api_football_client as m

    fake = _make_urlopen(fail_times=0)
    monkeypatch.setattr(m, "urlopen", fake)
    monkeypatch.setattr("time.sleep", lambda _: None)

    transport = UrllibJsonTransport(max_attempts=3, backoff_base=0.0)
    status, _, payload = transport.get_json("https://x.com", headers={}, timeout_seconds=1.0)

    assert status == 200
    assert fake.call_count[0] == 1


def test_transport_retries_on_os_error(monkeypatch):
    """OSError on first two attempts; success on the third."""
    import backend.services.api_football_client as m

    fake = _make_urlopen(fail_times=2)
    monkeypatch.setattr(m, "urlopen", fake)
    monkeypatch.setattr("time.sleep", lambda _: None)

    transport = UrllibJsonTransport(max_attempts=3, backoff_base=0.0)
    status, _, payload = transport.get_json("https://x.com", headers={}, timeout_seconds=1.0)

    assert status == 200
    assert fake.call_count[0] == 3


def test_transport_raises_after_all_retries_exhausted(monkeypatch):
    """Persistent OSError across all attempts raises ApiFootballError."""
    import backend.services.api_football_client as m

    fake = _make_urlopen(fail_times=99)
    monkeypatch.setattr(m, "urlopen", fake)
    monkeypatch.setattr("time.sleep", lambda _: None)

    transport = UrllibJsonTransport(max_attempts=3, backoff_base=0.0)
    with pytest.raises(ApiFootballError, match="transport failed"):
        transport.get_json("https://x.com", headers={}, timeout_seconds=1.0)

    assert fake.call_count[0] == 3


# ---------------------------------------------------------------------------
# Notification types — basic smoke test
# ---------------------------------------------------------------------------

def test_notification_types_importable():
    from qwantej.notifications.types import Notification, NotificationEvent, NotificationLevel

    n = Notification(
        event=NotificationEvent.SETTLEMENT_BATCH_DONE,
        title="test",
        body="body",
        level=NotificationLevel.INFO,
    )
    text = n.format_text()
    assert "test" in text
    assert "body" in text
