"""Forward-experiment problems must raise and clear alerts on their own.

The monitor is the only thing that notices a broken closing capture or a dead
paper tick without a human running the CLI, so the raise/clear behaviour is
worth pinning.
"""
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
