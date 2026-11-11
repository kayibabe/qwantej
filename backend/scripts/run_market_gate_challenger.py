"""Run the weekly challenger over an explicit, clamped validation window.

This is the reproducible version of the P1 audit run. It uses the same service
the Celery job uses, so the market-relative promotion gate is exercised exactly
as it will be in production.

Example (inside the backend container):

    python scripts/run_market_gate_challenger.py \
        --validation-start 2026-10-25 --validation-end 2026-11-10 \
        --challenger-version 0.3.0-l261110-mktg
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, timedelta

from sqlalchemy import select

from app.config import CURRENT_MODEL_VERSION, settings
from app.database import AsyncSessionLocal
from app.models import MarketLearningProfile
from app.services.model_learning import train_learning_challenger


def _date(value: str) -> date:
    return date.fromisoformat(value)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation-start", type=_date,
                        default=settings.learning_validation_not_before)
    parser.add_argument("--validation-end", type=_date,
                        default=date.today() - timedelta(days=1))
    parser.add_argument("--train-days", type=int, default=settings.learning_train_days)
    parser.add_argument("--challenger-version", default=None)
    args = parser.parse_args()

    validation_start = max(args.validation_start, settings.learning_validation_not_before)
    train_end = validation_start - timedelta(days=1)
    train_start = train_end - timedelta(days=args.train_days - 1)
    challenger_version = args.challenger_version or (
        f"{CURRENT_MODEL_VERSION.split('-l', 1)[0]}-l{args.validation_end:%y%m%d}-mktg"
    )

    async with AsyncSessionLocal() as db:
        run = await train_learning_challenger(
            db,
            base_model_version=CURRENT_MODEL_VERSION,
            train_start=train_start,
            train_end=train_end,
            validation_start=validation_start,
            validation_end=args.validation_end,
            challenger_version=challenger_version,
        )
        await db.commit()
        print("RUN", json.dumps({
            "id": run.id,
            "challenger": run.challenger_version,
            "status": str(run.status),
            "train": [train_start.isoformat(), train_end.isoformat()],
            "validation": [validation_start.isoformat(), args.validation_end.isoformat()],
            "summary": run.summary,
        }, default=str))
        profiles = (await db.execute(
            select(MarketLearningProfile)
            .where(MarketLearningProfile.learning_run_id == run.id)
            .order_by(MarketLearningProfile.market)
        )).scalars().all()
        for profile in profiles:
            metrics = profile.validation_metrics or {}
            print("PROFILE", json.dumps({
                "market": profile.market,
                "status": profile.status,
                "train": profile.train_sample_size,
                "validation": profile.validation_sample_size,
                "reason": profile.rejection_reason,
                "checks": profile.promotion_checks,
                "market_baseline": metrics.get("market_baseline"),
            }, default=str))


if __name__ == "__main__":
    asyncio.run(main())
