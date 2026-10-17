"""Serve frozen scans promptly and delegate missing scans to Celery."""

import asyncio
from datetime import date

from sqlalchemy import select

from app.config import CURRENT_MODEL_VERSION
from app.models import ParameterSweepScan
from app.services import cache
from app.services.parameter_sweep import POLICY_VERSION, _scan_out


def job_key(target: date) -> str:
    return f"qwantej:parameter-sweep:{POLICY_VERSION}:{CURRENT_MODEL_VERSION}:{target}"


async def ready_scan(db, target: date) -> dict | None:
    saved = await db.scalar(select(ParameterSweepScan).where(ParameterSweepScan.target_date == target))
    if saved is not None:
        return _scan_out(saved, target, saved.payload, provisional=False)
    cached = await cache.get(job_key(target) + ':result')
    return cached


async def enqueue_scan(target: date) -> None:
    from app.tasks.pipeline import capture_parameter_sweep

    client = await cache._get_client()
    if await client.exists(job_key(target) + ':failed'):
        raise RuntimeError('The worker could not complete this scan; retry shortly')
    key = job_key(target) + ':queued'
    # Polling and concurrent browser tabs must not enqueue duplicate sweeps.
    if await client.set(key, '1', nx=True, ex=7200):
        try:
            await asyncio.to_thread(capture_parameter_sweep.delay, target.isoformat())
        except Exception:
            await client.delete(key)
            raise
