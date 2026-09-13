"""Response contracts for the Today dashboard view."""

from datetime import datetime

from pydantic import BaseModel


class TodayStatusOut(BaseModel):
    status: str  # qualified, no_qualifying_combination, collecting, stale, no_upcoming_data
    label: str
    detail: str
    date: str
    data_freshness_utc: datetime | None
    checked_leagues: list[str]
    next_run_utc: datetime | None
    tickets_available: int
