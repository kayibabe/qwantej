"""Canonical fixture/team/competition/season entities (framework §11-12)."""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDPKMixin


class Competition(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "competitions"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    country: Mapped[str | None] = mapped_column(String(80))
    tier: Mapped[int | None] = mapped_column()

    seasons: Mapped[list["Season"]] = relationship(back_populates="competition")


class Season(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "seasons"
    __table_args__ = (
        UniqueConstraint("competition_id", "label", name="uq_season_competition_label"),
    )

    competition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competitions.id"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. "2025/2026"
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)

    competition: Mapped[Competition] = relationship(back_populates="seasons")


class Team(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(40))
    country: Mapped[str | None] = mapped_column(String(80))


class FixtureStatus(enum.StrEnum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"


class Fixture(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "fixtures"
    __table_args__ = (
        CheckConstraint("home_team_id <> away_team_id", name="ck_fixture_distinct_teams"),
    )

    competition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competitions.id"), nullable=False, index=True
    )
    season_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("seasons.id"), nullable=False, index=True
    )
    home_team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    away_team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)

    # Stored in UTC (framework §11) — convert to user timezone only at presentation.
    kickoff_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    status: Mapped[FixtureStatus] = mapped_column(
        Enum(
            FixtureStatus,
            name="fixture_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=FixtureStatus.SCHEDULED,
        nullable=False,
    )
    venue: Mapped[str | None] = mapped_column(String(150))

    home_goals: Mapped[int | None] = mapped_column()
    away_goals: Mapped[int | None] = mapped_column()

    competition: Mapped[Competition] = relationship()
    season: Mapped[Season] = relationship()
    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id])
