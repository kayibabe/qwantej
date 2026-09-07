"""Telegram notification channel.

Sends :class:`~qwantej.notifications.types.Notification` messages to a
configured Telegram chat.  All failures are caught and logged — a broken
notification must never crash the settlement or ingestion pipeline.

Usage::

    notifier = TelegramNotifier.from_settings(get_settings())
    notifier.send(Notification(
        event=NotificationEvent.SETTLEMENT_BATCH_DONE,
        title="Settlement complete",
        body="4 predictions settled — 3 won, 1 lost.",
    ))

If ``TELEGRAM_BOT_TOKEN`` or ``TELEGRAM_CHAT_ID`` is empty the notifier is a
no-op (logs at DEBUG level).  This keeps dev environments silent without any
code change.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen

from qwantej.notifications.types import Notification

log = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 2.0  # seconds; doubled each retry


class NotificationTransport(Protocol):
    """Injectable channel — real HTTP or test double."""

    def post_json(
        self, url: str, *, payload: dict, timeout_seconds: float
    ) -> None: ...


class TelegramHttpTransport:
    """Standard-library Telegram transport."""

    def post_json(
        self, url: str, *, payload: dict, timeout_seconds: float
    ) -> None:
        body = json.dumps(payload).encode()
        request = Request(  # noqa: S310
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=timeout_seconds) as resp:  # noqa: S310
            raw = resp.read()
        # Telegram always returns {"ok": true/false, ...} even on HTTP 200.
        # A false ok is an API-level error.  Raise OSError so the retry loop
        # in send() handles it consistently with network failures.
        # json.JSONDecodeError (ValueError) is also converted to OSError so
        # post_json's only failure mode is OSError — preserving send()'s
        # never-raises contract (which catches OSError but not ValueError).
        try:
            data = json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            raise OSError("Telegram returned a non-JSON response") from exc
        if not data.get("ok"):
            description = data.get("description", "unknown error")
            raise OSError(f"Telegram API error: {description}")


class TelegramNotifier:
    """Sends :class:`Notification` objects to a Telegram chat.

    Parameters
    ----------
    bot_token:
        Telegram Bot API token (``123456:ABC-…``).  Empty string disables the
        channel silently.
    chat_id:
        Telegram chat/channel/group id.  Empty string disables silently.
    timeout_seconds:
        Per-request HTTP timeout.
    transport:
        Injectable for tests; defaults to :class:`TelegramHttpTransport`.
    """

    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: str,
        timeout_seconds: float = 10.0,
        transport: NotificationTransport | None = None,
    ) -> None:
        self._bot_token = bot_token.strip()
        self._chat_id = chat_id.strip()
        self._timeout = timeout_seconds
        self._transport = transport or TelegramHttpTransport()

    @classmethod
    def from_settings(cls, settings) -> TelegramNotifier:  # type: ignore[no-untyped-def]
        from backend.core.config import Settings

        s: Settings = settings
        return cls(
            bot_token=s.telegram_bot_token,
            chat_id=s.telegram_chat_id,
            timeout_seconds=getattr(s, "telegram_timeout_seconds", 10.0),
        )

    @property
    def enabled(self) -> bool:
        return bool(self._bot_token and self._chat_id)

    def send(self, notification: Notification) -> bool:
        """Send *notification*; return ``True`` on success, ``False`` on failure.

        Never raises — all errors are caught and logged.
        """
        if not self.enabled:
            log.debug(
                "Telegram not configured (no token/chat_id); skipping notification: %s",
                notification.event,
            )
            return False

        text = notification.format_text()
        url = _TELEGRAM_API.format(token=self._bot_token)
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        for attempt in range(_MAX_ATTEMPTS):
            try:
                self._transport.post_json(url, payload=payload, timeout_seconds=self._timeout)
                log.info("Telegram notification sent: %s", notification.event)
                return True
            except (URLError, OSError, TimeoutError) as exc:
                if attempt < _MAX_ATTEMPTS - 1:
                    delay = _BACKOFF_BASE * (2**attempt)
                    log.warning(
                        "Telegram send attempt %d/%d failed (%s); retrying in %.1fs",
                        attempt + 1,
                        _MAX_ATTEMPTS,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    log.error(
                        "Telegram notification failed after %d attempts: %s — %s",
                        _MAX_ATTEMPTS,
                        notification.event,
                        exc,
                    )
        return False

    def ping(self) -> bool:
        """Return True if getMe returns ok=true (health-check use)."""
        if not self.enabled:
            return False
        url = f"https://api.telegram.org/bot{self._bot_token}/getMe"
        try:
            req = Request(url, method="GET")  # noqa: S310
            with urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
                raw = resp.read()
            data = json.loads(raw.decode("utf-8"))
            return bool(data.get("ok"))
        except Exception:  # noqa: BLE001
            return False
