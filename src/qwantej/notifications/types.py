"""Notification event types and message envelope.

Pure domain — no I/O, no external dependencies.  Channel implementations
(Telegram, email, …) live in ``backend/services/notifier.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class NotificationLevel(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class NotificationEvent(StrEnum):
    TICKET_QUALIFIED = "ticket_qualified"
    TICKET_WITHDRAWN = "ticket_withdrawn"
    SETTLEMENT_BATCH_DONE = "settlement_batch_done"
    RISK_STATE_CHANGED = "risk_state_changed"
    NO_QUALIFIED_ACCA = "no_qualified_acca"
    DRIFT_ALERT = "drift_alert"
    WORKER_FAILED = "worker_failed"
    WORKER_SUCCEEDED = "worker_succeeded"


_LEVEL_ICON: dict[NotificationLevel, str] = {
    NotificationLevel.INFO: "ℹ️",
    NotificationLevel.WARNING: "⚠️",
    NotificationLevel.ERROR: "🚨",
}

_EVENT_ICON: dict[NotificationEvent, str] = {
    NotificationEvent.TICKET_QUALIFIED: "✅",
    NotificationEvent.TICKET_WITHDRAWN: "🚫",
    NotificationEvent.SETTLEMENT_BATCH_DONE: "📊",
    NotificationEvent.RISK_STATE_CHANGED: "🔄",
    NotificationEvent.NO_QUALIFIED_ACCA: "⏸️",
    NotificationEvent.DRIFT_ALERT: "📉",
    NotificationEvent.WORKER_FAILED: "❌",
    NotificationEvent.WORKER_SUCCEEDED: "✔️",
}


@dataclass(frozen=True)
class Notification:
    event: NotificationEvent
    title: str
    body: str
    level: NotificationLevel = NotificationLevel.INFO
    metadata: dict[str, str] = field(default_factory=dict)

    def format_text(self) -> str:
        """Plain text suitable for Telegram or any chat channel."""
        icon = _EVENT_ICON.get(self.event, _LEVEL_ICON.get(self.level, ""))
        lines = [f"{icon} *{self.title}*", self.body]
        if self.metadata:
            lines.append("\n".join(f"  {k}: {v}" for k, v in self.metadata.items()))
        return "\n".join(lines)
