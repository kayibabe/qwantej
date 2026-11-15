"""Forward-experiment problems must raise and clear alerts on their own.

The monitor is the only thing that notices a broken closing capture or a dead
paper tick without a human running the CLI, so the raise/clear behaviour is
worth pinning. A missing closing line must also stay attributed to the right
cause: lost capture uptime is not a CLV defect.
"""
from datetime import datetime, timezone

import pytest

from app.services import forward_health, operational_monitor


def _snapshot(problems, *, enabled=True, rules=("policy-x",)):
    return {
        "paper_rules_enabled": enabled,
        "paper_rules": [{"rule": rule} for rule in rules],
        "problems": problems,
    }


@pytest.fixture
def captured(monkeypatch):
    recorded, resolved = [], []

    async def record(db, **kwargs):
        recorded.append(kwargs)

    async def resolve(db, key):
        resolved.append(key)

    monkeypatch.setattr(operational_monitor, "record_automation_alert", record)
    monkeypatch.setattr(
        operational_monitor, "resolve_automation_alert_by_dedupe_key", resolve
    )
    return recorded, resolved


def _patch_snapshot(monkeypatch, snapshot):
    async def fake(db, now=None):
        return snapshot

    monkeypatch.setattr(forward_health, "forward_experiment_snapshot", fake)


@pytest.mark.asyncio
async def test_a_problem_raises_one_rule_scoped_alert(captured, monkeypatch):
    recorded, resolved = captured
    _patch_snapshot(monkeypatch, _snapshot([
        {"key": "missing_clv:policy-x", "title": "t", "detail": "d", "context": {"a": 1}},
    ]))

    await operational_monitor.monitor_forward_experiment(object())

    assert [alert["dedupe_key"] for alert in recorded] == ["forward:missing_clv:policy-x"]
    assert recorded[0]["task_name"] == "forward_experiment"
    assert recorded[0]["severity"] == "warning"
    # Every other candidate key is cleared, so a fixed problem stops alerting.
    assert set(resolved) == {
        "forward:clv_invalid_rows",
        "forward:learning_slot_missed",
        "forward:tick_stale:policy-x",
        "forward:capture_missing:policy-x",
    }


@pytest.mark.asyncio
async def test_healthy_snapshot_clears_every_candidate_key(captured, monkeypatch):
    recorded, resolved = captured
    _patch_snapshot(monkeypatch, _snapshot([]))

    await operational_monitor.monitor_forward_experiment(object())

    assert recorded == []
    assert set(resolved) == {
        "forward:clv_invalid_rows",
        "forward:learning_slot_missed",
        "forward:tick_stale:policy-x",
        "forward:missing_clv:policy-x",
        "forward:capture_missing:policy-x",
    }


@pytest.mark.asyncio
async def test_disabled_paper_tracking_does_not_page_for_paper_problems(captured, monkeypatch):
    recorded, resolved = captured
    _patch_snapshot(monkeypatch, _snapshot(
        [{"key": "tick_stale:policy-x", "title": "t", "detail": "d", "context": {}}],
        enabled=False,
    ))

    await operational_monitor.monitor_forward_experiment(object())

    assert recorded == []
    assert "forward:tick_stale:policy-x" in resolved


@pytest.mark.asyncio
async def test_clv_problems_alert_even_when_paper_tracking_is_disabled(captured, monkeypatch):
    recorded, _ = captured
    _patch_snapshot(monkeypatch, _snapshot([
        {"key": "clv_invalid_rows", "title": "t", "detail": "d", "context": {}},
    ], enabled=False))

    await operational_monitor.monitor_forward_experiment(object())

    assert [alert["dedupe_key"] for alert in recorded] == ["forward:clv_invalid_rows"]


# A pick that never got a second quote is a capture gap, not a CLV defect. The
# distinction has to survive in the report or a host outage gets read as a
# modelling problem.
ENTRY = datetime(2026, 11, 14, 5, 40, tzinfo=timezone.utc)


def test_a_pick_with_no_second_quote_is_a_capture_gap():
    causes = forward_health.classify_missing_clv(
        [(32876, "under_2.5", "under_2.5", ENTRY)], set()
    )
    assert causes["no_post_entry_quote"] == [32876]
    assert causes["quote_without_derived_close"] == []


def test_a_pick_with_a_second_quote_is_a_derivation_defect():
    causes = forward_health.classify_missing_clv(
        [(32916, "btts_no", "btts_no", ENTRY)],
        {(32916, "btts_no", "btts_no")},
    )
    assert causes["no_post_entry_quote"] == []
    assert causes["quote_without_derived_close"] == [32916]


def test_picks_without_a_market_or_entry_time_are_not_guessed():
    causes = forward_health.classify_missing_clv(
        [(1, "", "", ENTRY), (2, "over_1.5", "over_1.5", None)], set()
    )
    assert causes["unclassified"] == [1, 2]
    assert causes["no_post_entry_quote"] == []
    assert causes["quote_without_derived_close"] == []


def test_missing_clv_causes_are_deduplicated_and_sorted():
    causes = forward_health.classify_missing_clv(
        [
            (9, "over_1.5", "over_1.5", ENTRY),
            (3, "over_1.5", "over_1.5", ENTRY),
            (9, "over_1.5", "over_1.5", ENTRY),
        ],
        set(),
    )
    assert causes["no_post_entry_quote"] == [3, 9]


def test_task_alert_keys_are_identical_for_failure_and_success():
    from app.tasks.pipeline import _task_alert_key

    # refresh_live_status takes no arguments; both signals see the same shape.
    assert _task_alert_key("pipeline.refresh_live_status", [], {}) == (
        "pipeline.refresh_live_status:global:automatic"
    )
    assert _task_alert_key("pipeline.run_models", ["2026-11-15"], {}) == (
        "pipeline.run_models:2026-11-15:automatic"
    )
    assert _task_alert_key(
        "pipeline.run_models", [], {"target_date": "2026-11-15", "trigger_source": "manual"}
    ) == "pipeline.run_models:2026-11-15:manual"


# The weekly learning job leaves no trace when the scheduler is down at its
# slot, so the slot has to be derived from the schedule rather than the last run.
SUNDAY_0430 = datetime(2026, 11, 15, 4, 30, tzinfo=timezone.utc)


def test_the_last_slot_is_this_sunday_once_it_has_passed():
    assert forward_health.last_learning_slot(SUNDAY_0430) == SUNDAY_0430
    after = datetime(2026, 11, 15, 6, 0, tzinfo=timezone.utc)
    assert forward_health.last_learning_slot(after) == SUNDAY_0430


def test_before_the_slot_the_last_slot_is_the_previous_week():
    before = datetime(2026, 11, 15, 3, 0, tzinfo=timezone.utc)
    assert forward_health.last_learning_slot(before) == datetime(
        2026, 11, 8, 4, 30, tzinfo=timezone.utc
    )


def test_the_last_slot_is_the_most_recent_sunday_from_midweek():
    wednesday = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
    assert forward_health.last_learning_slot(wednesday) == datetime(
        2026, 11, 8, 4, 30, tzinfo=timezone.utc
    )
