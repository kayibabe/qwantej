from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Date, DateTime, Float, Integer, SmallInteger,
    String, UniqueConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class HistoricalFixture(Base):
    """
    Canonical warehouse row per completed match.

    One row per match regardless of how many sources contributed data.
    Source fields track the primary data origin; enrichment from secondary
    sources (e.g. StatsBomb xG on top of Football-Data.co.uk results)
    updates the same row.
    """
    __tablename__ = "historical_fixtures"
    __table_args__ = (
        UniqueConstraint("match_date", "league", "home_team", "away_team",
                         name="uq_historical_fixtures_match"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Primary data source
    source: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    source_fixture_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)

    # --- Match identity -------------------------------------------------
    match_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    season: Mapped[int] = mapped_column(SmallInteger, nullable=False, index=True)
    country: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    league: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    league_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    home_team: Mapped[str] = mapped_column(String(120), nullable=False)
    away_team: Mapped[str] = mapped_column(String(120), nullable=False)

    # --- Full-time result -----------------------------------------------
    home_goals: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    away_goals: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    # "H" | "D" | "A" — derived from goals, stored for fast filtering
    result: Mapped[Optional[str]] = mapped_column(String(1), nullable=True)

    # --- Half-time result -----------------------------------------------
    home_goals_ht: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    away_goals_ht: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)

    # --- Pre-computed market outcomes (set once goals are known) --------
    btts: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    over_1_5: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    over_2_5: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    over_3_5: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    under_2_5: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    under_3_5: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # --- Match stats (Football-Data.co.uk, Opta, etc.) ------------------
    home_shots: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    away_shots: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    home_shots_on_target: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    away_shots_on_target: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    home_corners: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    away_corners: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    home_yellow_cards: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    away_yellow_cards: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    home_red_cards: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    away_red_cards: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    home_fouls: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    away_fouls: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    # Percentage 0-100; away_possession = 100 - home_possession
    home_possession: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # --- xG (StatsBomb open data or other event-level providers) --------
    home_xg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    away_xg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    xg_source: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)

    # --- Pre-match odds (decimal, best available across sources) --------
    odds_home_win: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    odds_draw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    odds_away_win: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    odds_over_1_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    odds_under_1_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    odds_over_2_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    odds_under_2_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    odds_over_3_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    odds_under_3_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    odds_btts_yes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    odds_btts_no: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # --- Data quality score (0-1, computed by ETL) ----------------------
    # Increases as more fields are populated; used by the ensemble and
    # DataSourceExperiment framework to weight predictions.
    data_quality: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    # -------------------------------------------------------------------

    def compute_market_outcomes(self) -> None:
        """Derive boolean market outcomes from goals and store on self."""
        if self.home_goals is None or self.away_goals is None:
            return
        h, a = self.home_goals, self.away_goals
        total = h + a
        self.result = "H" if h > a else ("D" if h == a else "A")
        self.btts = h > 0 and a > 0
        self.over_1_5 = total >= 2
        self.over_2_5 = total >= 3
        self.over_3_5 = total >= 4
        self.under_2_5 = total <= 2
        self.under_3_5 = total <= 3

    def compute_data_quality(self) -> float:
        """Return a 0-1 completeness score and store it on self."""
        score = 0.0
        if self.home_goals is not None and self.away_goals is not None:
            score += 0.25
        if self.home_goals_ht is not None and self.away_goals_ht is not None:
            score += 0.05
        stats_fields = (
            self.home_shots, self.away_shots,
            self.home_shots_on_target, self.away_shots_on_target,
            self.home_corners, self.away_corners,
        )
        if any(f is not None for f in stats_fields):
            score += 0.15
        if self.home_xg is not None and self.away_xg is not None:
            score += 0.25
        odds_fields = (
            self.odds_home_win, self.odds_draw, self.odds_away_win,
            self.odds_over_2_5, self.odds_under_2_5,
        )
        if all(f is not None for f in odds_fields):
            score += 0.25
        elif any(f is not None for f in odds_fields):
            score += 0.05
        if self.home_possession is not None:
            score += 0.05
        self.data_quality = round(min(score, 1.0), 3)
        return self.data_quality
