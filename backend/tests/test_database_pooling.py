"""Database engine pooling selection."""

from sqlalchemy.pool import NullPool

from app.database import build_engine_options


def test_celery_workers_use_nullpool():
    options = build_engine_options(worker=True)
    assert options["poolclass"] is NullPool


def test_api_uses_a_bounded_queue_pool():
    options = build_engine_options(worker=False)
    assert "poolclass" not in options
    assert options["pool_size"] >= 1
    assert options["max_overflow"] >= 0
    assert options["pool_timeout"] >= 1


def test_worker_environment_selects_nullpool(monkeypatch):
    monkeypatch.setenv("CELERY_WORKER", "1")
    assert build_engine_options()["poolclass"] is NullPool


def test_non_worker_environment_selects_queue_pool(monkeypatch):
    monkeypatch.delenv("CELERY_WORKER", raising=False)
    assert "poolclass" not in build_engine_options()
