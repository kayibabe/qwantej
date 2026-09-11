"""Tests for backend.services.notifier (Telegram channel)."""

from __future__ import annotations

import pytest

from backend.services.notifier import TelegramNotifier
from qwantej.notifications.types import (
    Notification,
    NotificationEvent,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _CapturingTransport:
    """Records calls so tests can assert on them."""

    def __init__(self, *, raise_on_call: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self._raise = raise_on_call

    def post_json(self, url: str, *, payload: dict, timeout_seconds: float) -> None:
        if self._raise:
            raise self._raise
        self.calls.append({"url": url, "payload": payload})


def _notifier(transport=None, *, token="bot123:ABC", chat="42"):
    return TelegramNotifier(
        bot_token=token,
        chat_id=chat,
        timeout_seconds=5.0,
        transport=transport or _CapturingTransport(),
    )


# ---------------------------------------------------------------------------
# Notification.format_text
# ---------------------------------------------------------------------------

def test_format_text_contains_title_and_body():
    n = Notification(
        event=NotificationEvent.SETTLEMENT_BATCH_DONE,
        title="Settlement done",
        body="3 won, 1 lost.",
    )
    text = n.format_text()
    assert "Settlement done" in text
    assert "3 won, 1 lost." in text


def test_format_text_includes_metadata():
    n = Notification(
        event=NotificationEvent.DRIFT_ALERT,
        title="Drift",
        body="MCE exceeded.",
        metadata={"MCE": "0.08", "threshold": "0.05"},
    )
    text = n.format_text()
    assert "MCE: 0.08" in text
    assert "threshold: 0.05" in text


# ---------------------------------------------------------------------------
# TelegramNotifier.enabled
# ---------------------------------------------------------------------------

def test_enabled_when_configured():
    assert _notifier().enabled is True


def test_rejects_non_positive_timeout():
    with pytest.raises(ValueError, match="timeout_seconds"):
        TelegramNotifier(bot_token="tok", chat_id="1", timeout_seconds=0)


def test_non_retryable_notification_error_is_not_retried():
    from backend.services.notifier import NonRetryableNotificationError

    class _RejectedTransport:
        attempts = 0

        def post_json(self, url, *, payload, timeout_seconds):
            self.attempts += 1
            raise NonRetryableNotificationError("bad token")

    transport = _RejectedTransport()
    result = _notifier(transport).send(
        Notification(event=NotificationEvent.WORKER_FAILED, title="T", body="B")
    )
    assert result is False
    assert transport.attempts == 1


def test_disabled_when_no_token():
    n = TelegramNotifier(bot_token="", chat_id="42")
    assert n.enabled is False


def test_disabled_when_no_chat_id():
    n = TelegramNotifier(bot_token="bot123:ABC", chat_id="")
    assert n.enabled is False


# ---------------------------------------------------------------------------
# TelegramNotifier.send — happy path
# ---------------------------------------------------------------------------

def test_send_calls_transport():
    transport = _CapturingTransport()
    n = _notifier(transport)
    result = n.send(
        Notification(
            event=NotificationEvent.WORKER_SUCCEEDED,
            title="Worker OK",
            body="All good.",
        )
    )
    assert result is True
    assert len(transport.calls) == 1
    assert "bot123:ABC" in transport.calls[0]["url"]
    assert transport.calls[0]["payload"]["chat_id"] == "42"
    assert "Worker OK" in transport.calls[0]["payload"]["text"]


def test_send_returns_false_when_not_enabled():
    n = TelegramNotifier(bot_token="", chat_id="")
    result = n.send(
        Notification(
            event=NotificationEvent.WORKER_FAILED,
            title="X",
            body="Y",
        )
    )
    assert result is False


# ---------------------------------------------------------------------------
# TelegramNotifier.send — retry on transient error
# ---------------------------------------------------------------------------

def test_send_retries_on_transport_error():
    """Transport fails twice then succeeds — send() retries and returns True."""

    class _FlakyTransport:
        def __init__(self):
            self.attempts = 0

        def post_json(self, url, *, payload, timeout_seconds):
            self.attempts += 1
            if self.attempts < 3:
                raise OSError("transient")

    transport = _FlakyTransport()
    n = TelegramNotifier(bot_token="tok", chat_id="1", transport=transport)
    # Patch sleep so tests don't block
    import backend.services.notifier as m
    original = m.time.sleep
    m.time.sleep = lambda _: None  # type: ignore[attr-defined]
    try:
        result = n.send(
            Notification(event=NotificationEvent.WORKER_SUCCEEDED, title="T", body="B")
        )
    finally:
        m.time.sleep = original
    assert result is True
    assert transport.attempts == 3


def test_send_returns_false_after_all_retries_exhausted():
    """Transport always fails — send() returns False without raising."""
    import backend.services.notifier as m

    transport = _CapturingTransport(raise_on_call=OSError("always fails"))
    n = TelegramNotifier(bot_token="tok", chat_id="1", transport=transport)
    original = m.time.sleep
    m.time.sleep = lambda _: None
    try:
        result = n.send(
            Notification(event=NotificationEvent.WORKER_FAILED, title="T", body="B")
        )
    finally:
        m.time.sleep = original
    assert result is False


# ---------------------------------------------------------------------------
# TelegramHttpTransport — Telegram ok field
# ---------------------------------------------------------------------------

def test_telegram_http_transport_raises_on_ok_false():
    """HTTP 200 with ok=false must raise OSError so the retry loop acts on it."""
    import json as _json

    from backend.services.notifier import TelegramHttpTransport

    class _FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return _json.dumps({"ok": False, "description": "Bad Token"}).encode()

    import backend.services.notifier as m
    original = m.urlopen
    m.urlopen = lambda req, timeout: _FakeResp()
    try:
        transport = TelegramHttpTransport()
        with pytest.raises(OSError, match="Bad Token"):
            transport.post_json("https://api.telegram.org/botX/sendMessage",
                                payload={"chat_id": "1", "text": "hi"},
                                timeout_seconds=5.0)
    finally:
        m.urlopen = original


def test_telegram_http_transport_ok_on_success():
    """HTTP 200 with ok=true must not raise."""
    import json as _json

    from backend.services.notifier import TelegramHttpTransport

    class _FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return _json.dumps({"ok": True, "result": {}}).encode()

    import backend.services.notifier as m
    original = m.urlopen
    m.urlopen = lambda req, timeout: _FakeResp()
    try:
        transport = TelegramHttpTransport()
        # Must not raise
        transport.post_json("https://api.telegram.org/botX/sendMessage",
                            payload={"chat_id": "1", "text": "hi"},
                            timeout_seconds=5.0)
    finally:
        m.urlopen = original


def test_telegram_http_transport_non_object_raises_oserror():
    """A JSON non-object body (array, scalar) must raise OSError — not AttributeError."""
    import json as _json

    from backend.services.notifier import TelegramHttpTransport

    class _FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return _json.dumps([{"ok": True}]).encode()  # array, not object

    import backend.services.notifier as m
    original = m.urlopen
    m.urlopen = lambda req, timeout: _FakeResp()
    try:
        transport = TelegramHttpTransport()
        with pytest.raises(OSError, match="non-object"):
            transport.post_json("https://api.telegram.org/botX/sendMessage",
                                payload={"chat_id": "1", "text": "hi"},
                                timeout_seconds=5.0)
    finally:
        m.urlopen = original


def test_telegram_http_transport_non_json_raises_oserror():
    """A non-JSON body must raise OSError, not propagate ValueError."""
    from backend.services.notifier import TelegramHttpTransport

    class _FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return b"<html>bad gateway</html>"

    import backend.services.notifier as m
    original = m.urlopen
    m.urlopen = lambda req, timeout: _FakeResp()
    try:
        transport = TelegramHttpTransport()
        with pytest.raises(OSError, match="non-JSON"):
            transport.post_json("https://api.telegram.org/botX/sendMessage",
                                payload={"chat_id": "1", "text": "hi"},
                                timeout_seconds=5.0)
    finally:
        m.urlopen = original


# ---------------------------------------------------------------------------
# TelegramNotifier.ping — validates ok field
# ---------------------------------------------------------------------------

def test_ping_returns_true_when_ok():
    """ping() must return True only when the getMe response has ok=true."""
    import json as _json

    class _FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return _json.dumps({"ok": True, "result": {"id": 1}}).encode()

    import backend.services.notifier as m
    original = m.urlopen
    m.urlopen = lambda req, timeout: _FakeResp()
    try:
        n = _notifier()
        assert n.ping() is True
    finally:
        m.urlopen = original


def test_ping_returns_false_when_ok_false():
    """ping() must return False when getMe responds with ok=false."""
    import json as _json

    class _FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return _json.dumps({"ok": False, "description": "Unauthorized"}).encode()

    import backend.services.notifier as m
    original = m.urlopen
    m.urlopen = lambda req, timeout: _FakeResp()
    try:
        n = _notifier()
        assert n.ping() is False
    finally:
        m.urlopen = original
