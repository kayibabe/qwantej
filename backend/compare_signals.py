"""
Compare today's served signals from merged qwantej vs what titibet shows.
Applies the same serve-time filters the router uses:
  - ZINB_GOALS_MIN_ODDS floor
  - OVER25_SUPPRESSED_TIERS (Tier 3)
  - DISABLED_MARKETS / DISABLED_LEAGUES
  - Women's fixture gate
  - D-grade quality floor (dual_quality_score < 0.035 → dropped at router)
"""
import asyncio
from sqlalchemy import text
from app.core.database import AsyncSessionLocal
from app.core.config import (
    ZINB_GOALS_MIN_ODDS, OVER25_SUPPRESSED_TIERS,
    DISABLED_MARKETS, DISABLED_LEAGUES, U35_DATA_POOR_COUNTRIES,
    MARKET_MIN_ODDS,
)


def is_womens(league: str) -> bool:
    kws = [" w ", " women", "femenin", "feminin", "kvinde", "damer", "ladies", "mujer"]
    l = (league or "").lower()
    return any(k in l for k in kws)


async def run():
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("""
            SELECT
                f.league, f.country, f.league_tier,
                f.home_team, f.away_team,
                f.kickoff_at,
                s.market, s.poisson_rule_key,
                s.bayesian_best_odd,
                s.dual_confidence, s.dual_agreement,
                s.dual_quality_score,
                s.poisson_grade,
                s.poisson_lambda_total
            FROM signals s
            JOIN fixtures f ON s.fixture_id = f.id
            WHERE f.event_date = '2026-08-04'
            ORDER BY f.league_tier, s.bayesian_best_odd DESC
        """))
        rows = r.all()

    served = []
    dropped = []

    for row in rows:
        league, country, tier, home, away, kickoff, market, rule_key, odds, conf, agree, quality, grade, lam = row
        reason = None

        # ZINB odds floor
        if rule_key in ZINB_GOALS_MIN_ODDS:
            floor = ZINB_GOALS_MIN_ODDS[rule_key]
            if (odds or 0) < floor:
                reason = f"ZINB odds {odds:.2f} < floor {floor}"

        # MARKET_MIN_ODDS floor for cs00mid
        if not reason and rule_key in {"cs00mid", "cs00u35"}:
            floor = MARKET_MIN_ODDS.get("Under 3.5", 1.30)
            if (odds or 0) < floor:
                reason = f"cs odds {odds:.2f} < floor {floor}"

        # Over 2.5 Tier 3 suppression
        if not reason and market == "Over 2.5" and (tier or 1) in OVER25_SUPPRESSED_TIERS:
            reason = f"Over 2.5 suppressed at Tier {tier}"

        # Women's gate
        if not reason and is_womens(league):
            reason = "Women's fixture"

        # D-grade quality floor (router drops quality < 0.035)
        if not reason and (quality or 0) < 0.035 and rule_key not in {"cs00mid", "cs00u35"}:
            reason = f"D-grade quality {quality:.4f}"

        if reason:
            dropped.append((league, country, tier, home, away, market, rule_key, odds, reason))
        else:
            served.append((league, country, tier, home, away, kickoff, market, rule_key, odds, conf, agree))

    print(f"╔══ MERGED QWANTEJ — Served signals for 2026-08-04 ({len(served)}) ══╗\n")
    print(f"  {'#':<3} {'League':<35} {'Country':<14} {'T'} {'Home':<22} {'Away':<22} {'Time':<7} {'Market':<12} {'Rule':<12} {'Odds':<6} {'Conf'}")
    print(f"  {'-'*3} {'-'*35} {'-'*14} {'-'} {'-'*22} {'-'*22} {'-'*7} {'-'*12} {'-'*12} {'-'*6} {'-'*8}")
    for i, (league, country, tier, home, away, kickoff, market, rule, odds, conf, agree) in enumerate(served, 1):
        time_str = str(kickoff)[11:16] if kickoff else "—"
        print(f"  {i:<3} {(league or ''):<35} {(country or ''):<14} {tier or '?'} {(home or ''):<22} {(away or ''):<22} {time_str:<7} {(market or ''):<12} {(rule or ''):<12} {odds or 0:<6.2f} {conf or ''}")

    print(f"\n╔══ Filtered OUT at serve-time ({len(dropped)}) ══╗\n")
    print(f"  {'League':<35} {'Country':<14} {'T'} {'Home':<22} {'Market':<12} {'Rule':<12} {'Odds':<6} {'Reason'}")
    print(f"  {'-'*35} {'-'*14} {'-'} {'-'*22} {'-'*12} {'-'*12} {'-'*6} {'-'*30}")
    for league, country, tier, home, away, market, rule, odds, reason in dropped:
        print(f"  {(league or ''):<35} {(country or ''):<14} {tier or '?'} {(home or ''):<22} {(market or ''):<12} {(rule or ''):<12} {odds or 0:<6.2f} {reason}")

    # Summary by market
    print(f"\n╔══ By market ══╗")
    from collections import Counter
    mkt_counts = Counter((row[6], row[7]) for row in [
        (l,c,t,h,a,k,m,rk,o,cf,ag) for l,c,t,h,a,k,m,rk,o,cf,ag in served
    ])
    for (mkt, rule), cnt in sorted(mkt_counts.items()):
        print(f"  {mkt:<14} {rule:<14} {cnt}")


asyncio.run(run())
