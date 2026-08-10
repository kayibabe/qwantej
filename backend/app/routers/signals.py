"""
signals.py — Legacy signals router (Phase 1 transition).

The main signals feed has moved to /api/forecasts (ForecastSnapshot).
This router retains two endpoints still used by MatchIntelligencePage
for live fixtures:
  - GET /{fixture_id}/odds-matrix   (bookmaker comparison table)
  - GET /{fixture_id}/match-info    (form, H2H, contextual stats)
"""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.odds import MarketSnapshot
from app.services.match_info import get_match_info

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("/{fixture_id}/odds-matrix")
async def odds_matrix(fixture_id: int, db: AsyncSession = Depends(get_db)):
    """Bookmaker × market odds comparison for a live fixture."""
    snap_rows = await db.execute(
        select(MarketSnapshot)
        .where(MarketSnapshot.fixture_id == fixture_id)
        .order_by(MarketSnapshot.market_type, MarketSnapshot.selection_name)
    )
    snapshots = snap_rows.scalars().all()

    data: dict = defaultdict(lambda: defaultdict(dict))
    bookmakers_seen: set[str] = set()

    for snap in snapshots:
        if snap.odds and snap.odds > 1.0:
            existing = data[snap.market_type][snap.selection_name].get(snap.bookmaker, 0.0)
            if snap.odds > existing:
                data[snap.market_type][snap.selection_name][snap.bookmaker] = snap.odds
                bookmakers_seen.add(snap.bookmaker)

    sharp = {"Pinnacle", "Bet365"}
    bookmakers = sorted(bookmakers_seen, key=lambda b: (0 if b in sharp else 1, b))

    rows = []
    for market_type in sorted(data.keys()):
        for sel_name in sorted(data[market_type].keys()):
            odds_map = data[market_type][sel_name]
            best_bookie = max(odds_map, key=odds_map.get)
            rows.append({
                "market_type": market_type,
                "selection": sel_name,
                "odds": {bk: odds_map.get(bk) for bk in bookmakers},
                "best_bookie": best_bookie,
            })

    return {"bookmakers": bookmakers, "rows": rows}


@router.get("/{fixture_id}/match-info")
async def match_info(fixture_id: int, db: AsyncSession = Depends(get_db)):
    """Team form, H2H, and contextual stats for a live fixture."""
    return await get_match_info(db, fixture_id)
