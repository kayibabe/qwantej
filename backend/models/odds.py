"""Bookmaker odds quotes (framework §11-12, §20).

Every quote is an immutable, timestamped observation — this table is
append-only. Closing-line values are new rows, not updates to earlier ones,
so a prediction's feature set can never accidentally see a later price
(framework §13's point-in-time integrity rule).
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, CreatedAtMixin, UUIDPKMixin

if TYPE_CHECKING:
    from backend.models.fixtures import Fixture


class OddsQuote(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "odds_quotes"

    fixture_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fixtures.id"), nullable=False, index=True
    )
    bookmaker: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    selection: Mapped[str] = mapped_column(String(40), nullable=False)
    line: Mapped[float | None] = mapped_column(Numeric(6, 2))  # e.g. 2.5 for O/U 2.5

    decimal_odds: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False)

    # The moment this price was observed — the point-in-time-critical field.
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(80), nullable=False)

    fixture: Mapped["Fixture"] = relationship()
