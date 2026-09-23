"""Response contracts for the Today dashboard view."""

from datetime import datetime

from pydantic import BaseModel


class TodayStatusOut(BaseModel):
    # See the dashboard status branches for the supported states.
    status: str
    label: str
    detail: str
    date: str
    data_freshness_utc: datetime | None
    checked_leagues: list[str]
    observed_leagues: list[str]
    observed_fixture_count: int
    next_run_utc: datetime | None
    tickets_available: int
