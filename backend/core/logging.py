"""Structured logging configuration.

Call ``configure_logging()`` once at application startup (in ``main.py``).

In JSON mode each log record is a single-line JSON object::

    {"ts": "2026-09-07T12:00:00.000Z", "level": "INFO",
     "logger": "backend.api.routes.health", "msg": "...", "request_id": "abc123"}

In plain mode the standard format is used (suitable for local dev).
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        doc: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None)
        if request_id:
            doc["request_id"] = request_id
        if record.exc_info:
            doc["exc"] = self.formatException(record.exc_info)
        return json.dumps(doc, ensure_ascii=False)


def configure_logging(*, log_level: str = "INFO", log_format: str = "plain") -> None:
    """Configure root logger.

    Parameters
    ----------
    log_level:
        Standard Python level name (``DEBUG``, ``INFO``, ``WARNING``, …).
    log_format:
        ``"json"`` for structured JSON output (production) or ``"plain"``
        for human-readable text (development).
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    if log_format.lower() == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s — %(message)s")
        )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Silence chatty third-party loggers
    for noisy in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
