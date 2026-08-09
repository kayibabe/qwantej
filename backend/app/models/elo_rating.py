from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, Integer, SmallInteger, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EloRating(Base):
    """Persisted Elo rating for a team in a given league/season."""
    __tablename__ = "elo_ratings"
    __table_args__ = (
        UniqueConstraint("team_name", "league", "season", name="uq_elo_ratings_team_league_season"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    league: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    country: Mapped[str] = mapped_column(String(120), nullable=False)
    season: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    rating: Mapped[float] = mapped_column(Float, nullable=False, default=1500.0)
    n_matches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_match_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
