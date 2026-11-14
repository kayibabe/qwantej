"""Paper picks must be closing-quote candidates, not just published tickets.

Their CLV is only meaningful if a genuine near-kickoff quote exists. Without
the paper-rule source in ``_closing_candidate_ids`` the experiments would get
whatever the last scheduled odds refresh happened to store, and every settled
pick would show ``clv_valid = false``. These tests pin the union, the dedupe,
and the qualified-only filter.
"""
from datetime import datetime, timezone

import pytest

from app.services import odds_fetcher
from app.services.odds_fetcher import LiveOddsFetcher

NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)


class _Result:
    """Stand-in for a SQLAlchemy result: ``scalars().all()`` is all we use."""

    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _ScriptedDb:
    """Return queued results in call order and keep the statements for review."""

    def __init__(self, *results):
        self._results = list(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self._results.pop(0))


@pytest.mark.asyncio
async def test_paper_pick_without_a_ticket_is_a_candidate():
    db = _ScriptedDb([], ["32961"])

    ids = await LiveOddsFetcher(db)._closing_candidate_ids(NOW)

    assert ids == [32961]
    assert len(db.statements) == 2


@pytest.mark.asyncio
async def test_candidates_are_deduplicated_and_bad_payloads_ignored():
    db = _ScriptedDb([10, 11], ["11", "12", "not-a-match", None])

    ids = await LiveOddsFetcher(db)._closing_candidate_ids(NOW)

    assert ids == [10, 11, 12]


@pytest.mark.asyncio
async def test_paper_source_selects_only_qualified_policy_decisions():
    db = _ScriptedDb([], [])

    await LiveOddsFetcher(db)._closing_candidate_ids(NOW)

    ticket_sql, paper_sql = (str(statement) for statement in db.statements)
    assert "ticket" in ticket_sql.lower()
    assert "paper_rule_events" in paper_sql
    params = db.statements[1].compile().params.values()
    assert "decision:policy%" in params
    assert "true" in params


@pytest.mark.asyncio
async def test_no_candidates_short_circuits_before_any_match_query(monkeypatch):
    async def quota():
        return {
            "daily_limit": 7500,
            "daily_remaining": 7000,
            "observed_at": NOW.isoformat(),
            "minute_remaining": 100,
        }

    monkeypatch.setattr(odds_fetcher.cache, "get_api_football_quota", quota)
    monkeypatch.setattr(odds_fetcher.settings, "api_football_host", "direct")
    monkeypatch.setattr(odds_fetcher.settings, "api_football_key", "test-key")
    db = _ScriptedDb([], [])

    result = await LiveOddsFetcher(db).refresh_published_closing_quotes(now=NOW)

    assert result == {"status": "ok", "candidates": 0, "attempted": 0,
                      "snapshots": 0, "errors": []}
    assert len(db.statements) == 2
