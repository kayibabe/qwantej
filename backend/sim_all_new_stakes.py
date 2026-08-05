"""
Retrospective simulation — ALL settled signals in DB.
Uses new stake tiers: HIGH=K100k, MEDIUM=K75k, LOW=K40k, X2 cap=K100k.
Run from backend/ on the Fly machine:
    python sim_all_new_stakes.py
"""
import asyncio, sys, os
sys.path.insert(0, '.')

# ── New stake config (hardcoded so no deploy needed) ──────────────────────────
NEW_STAKE_LEVELS = {
    "HIGH":   {"min_odds": 1.40, "base_stake": 100_000.0},
    "MEDIUM": {"min_odds": 1.25, "base_stake":  75_000.0},
    "LOW":    {"min_odds": 1.10, "base_stake":  40_000.0},
}
NEW_X2_MAX_STAKE = 100_000.0

OLD_STAKE_LEVELS = {
    "HIGH":   {"min_odds": 1.40, "base_stake": 75_000.0},
    "MEDIUM": {"min_odds": 1.25, "base_stake": 75_000.0},
    "LOW":    {"min_odds": 1.10, "base_stake": 50_000.0},
}
OLD_X2_MAX_STAKE = 75_000.0

MIN_ODDS = 1.21
MAX_ODDS = 1.50
MIN_ODDS_AO05 = 1.40

try:
    from app.core.config import (
        HYBRID_B_PERMANENT_BLACKLIST,
        HYBRID_B_AO05_SUPPRESSED_COUNTRIES,
    )
except Exception:
    HYBRID_B_PERMANENT_BLACKLIST = frozenset()
    HYBRID_B_AO05_SUPPRESSED_COUNTRIES = frozenset()


def _recover_odds(ep: float | None, stake_levels) -> float | None:
    if ep is None or ep <= 0:
        return None
    low_base = stake_levels["LOW"]["base_stake"]
    mid_base = stake_levels["MEDIUM"]["base_stake"]
    # discriminator: if ep implies odds < 1.25 at LOW base → LOW tier
    # ep = base * (odds - 1)  →  odds = ep/base + 1
    implied_low = ep / low_base + 1
    if implied_low < stake_levels["MEDIUM"]["min_odds"]:
        return round(implied_low, 6)
    return round(ep / mid_base + 1, 6)


def _recover_odds_for_sim(ep: float | None) -> float | None:
    """Use OLD stake levels for odds recovery (that's what was stored)."""
    if ep is None or ep <= 0:
        return None
    if ep < 12_500:
        return round(ep / 50_000 + 1, 6)
    return round(ep / 75_000 + 1, 6)


def _stake_for(odds: float, market: str, stake_levels: dict, x2_cap: float) -> float:
    for tier in ("HIGH", "MEDIUM", "LOW"):
        if odds >= stake_levels[tier]["min_odds"]:
            base = stake_levels[tier]["base_stake"]
            if market == "X2":
                return min(base, x2_cap)
            return base
    return 0.0


def _is_win(market: str, home_score, away_score) -> bool | None:
    if home_score is None or away_score is None:
        return None
    h, a = int(home_score), int(away_score)
    if market == "X2":
        return h <= a
    if market == "Away O0.5":
        return a >= 1
    return None


def _process_rows(rows, stake_levels, x2_cap):
    picks = []
    rejected_by = {"phase2_no_ep": 0, "blacklist": 0, "odds_window": 0,
                   "ao05_suppressed": 0, "no_result": 0}

    for row in rows:
        if row.ep_x2 is None and row.ep_away_o05 is None:
            rejected_by["phase2_no_ep"] += 1
            continue

        league  = row.league or ""
        country = row.country or ""
        league_l  = league.lower().strip()
        country_l = country.lower().strip()

        if any(bl in league_l for bl in HYBRID_B_PERMANENT_BLACKLIST):
            rejected_by["blacklist"] += 1
            continue

        # Recover odds from stored EP (always using OLD stake levels — that's
        # what the engine used when it wrote the EP values to the DB)
        odds_x2   = _recover_odds_for_sim(row.ep_x2)
        odds_ao05 = _recover_odds_for_sim(row.ep_away_o05)

        def in_window(o, mkt="X2"):
            if o is None: return False
            if not (MIN_ODDS <= o <= MAX_ODDS): return False
            if mkt == "Away O0.5" and o < MIN_ODDS_AO05: return False
            return True

        x2_in   = in_window(odds_x2, "X2")
        ao05_in = in_window(odds_ao05, "Away O0.5")

        ep_x2   = row.ep_x2        if x2_in   else None
        ep_ao05 = row.ep_away_o05  if ao05_in else None

        if country_l in HYBRID_B_AO05_SUPPRESSED_COUNTRIES:
            ep_ao05   = None
            odds_ao05 = None

        if ep_x2 is None and ep_ao05 is None:
            rejected_by["odds_window"] += 1
            continue

        if ep_x2 is not None and ep_ao05 is not None:
            if ep_x2 > ep_ao05:
                market, odds = "X2", odds_x2
            elif ep_ao05 > ep_x2:
                market, odds = "Away O0.5", odds_ao05
            else:
                away_xg = row.away_xg or 0
                home_xg = row.home_xg or 0
                market, odds = ("X2", odds_x2) if away_xg >= home_xg else ("Away O0.5", odds_ao05)
        elif ep_x2 is not None:
            market, odds = "X2", odds_x2
        else:
            market, odds = "Away O0.5", odds_ao05

        if odds is None:
            continue

        result = _is_win(market, row.home_score, row.away_score)
        if result is None:
            rejected_by["no_result"] += 1
            continue

        stake = _stake_for(odds, market, stake_levels, x2_cap)
        pnl   = round(stake * (odds - 1) if result else -stake, 2)

        picks.append({
            "date":    str(row.event_date)[:10],
            "match":   f"{row.home_team} vs {row.away_team}",
            "league":  league,
            "country": country,
            "market":  market,
            "odds":    odds,
            "stake":   stake,
            "result":  "Won" if result else "Lost",
            "pnl":     pnl,
        })

    return picks, rejected_by


def _scorecard(label, picks, rejected_by):
    from collections import defaultdict

    if not picks:
        print(f"\n[{label}] No qualifying picks found.")
        return {}

    total_won   = sum(1 for p in picks if p["result"] == "Won")
    total_lost  = len(picks) - total_won
    total       = len(picks)
    total_pnl   = sum(p["pnl"] for p in picks)
    total_stake = sum(p["stake"] for p in picks)
    wr  = total_won / total * 100
    roi = total_pnl / total_stake * 100 if total_stake else 0

    markets = defaultdict(lambda: {"won": 0, "lost": 0, "pnl": 0.0, "stake": 0.0})
    bands   = {
        "1.21–1.30": {"won": 0, "lost": 0, "pnl": 0.0, "stake": 0.0},
        "1.31–1.40": {"won": 0, "lost": 0, "pnl": 0.0, "stake": 0.0},
        "1.41–1.50": {"won": 0, "lost": 0, "pnl": 0.0, "stake": 0.0},
    }

    for p in picks:
        w = 1 if p["result"] == "Won" else 0
        m = markets[p["market"]]
        m["won"] += w; m["lost"] += 1 - w
        m["pnl"] += p["pnl"]; m["stake"] += p["stake"]
        o = p["odds"]
        band = ("1.21–1.30" if o <= 1.30 else "1.31–1.40" if o <= 1.40 else "1.41–1.50")
        b = bands[band]
        b["won"] += w; b["lost"] += 1 - w
        b["pnl"] += p["pnl"]; b["stake"] += p["stake"]

    W = 74
    print("\n" + "=" * W)
    print(f"  {label}")
    print("=" * W)
    print(f"  Qualifying picks : {total}")
    print(f"  Win rate         : {wr:.1f}%")
    print(f"  ROI              : {roi:+.2f}%")
    print(f"  Net P&L          : {total_pnl:+,.0f} MWK")
    print(f"  Total staked     : {total_stake:,.0f} MWK")
    print(f"  Won / Lost       : {total_won} / {total_lost}")

    print(f"\n  BY MARKET")
    print(f"  {'Market':<14}  {'W':>3}  {'L':>3}  {'N':>4}  {'WR%':>6}  {'ROI%':>7}  {'P&L':>14}")
    for mkt, md in sorted(markets.items()):
        n = md["won"] + md["lost"]
        wrm  = md["won"] / n * 100 if n else 0
        roim = md["pnl"] / md["stake"] * 100 if md["stake"] else 0
        print(f"  {mkt:<14}  {md['won']:>3}  {md['lost']:>3}  {n:>4}  {wrm:>5.1f}%  {roim:>+6.2f}%  {md['pnl']:>+14,.0f}")

    print(f"\n  BY ODDS BAND")
    print(f"  {'Band':<12}  {'W':>3}  {'L':>3}  {'N':>4}  {'WR%':>6}  {'ROI%':>7}  {'P&L':>14}")
    for band, bd in bands.items():
        n = bd["won"] + bd["lost"]
        if not n: continue
        wrb  = bd["won"] / n * 100
        roib = bd["pnl"] / bd["stake"] * 100 if bd["stake"] else 0
        print(f"  {band:<12}  {bd['won']:>3}  {bd['lost']:>3}  {n:>4}  {wrb:>5.1f}%  {roib:>+6.2f}%  {bd['pnl']:>+14,.0f}")

    print("=" * W)
    return {
        "picks": total, "won": total_won, "lost": total_lost,
        "wr": wr, "roi": roi, "pnl": total_pnl, "staked": total_stake,
        "markets": dict(markets), "bands": dict(bands),
    }


async def main():
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        r = await db.execute(text("""
            SELECT
                s.id,
                f.event_date,
                f.home_team, f.away_team,
                f.league, f.country,
                f.home_score, f.away_score,
                s.ep_x2, s.ep_away_o05,
                s.away_xg, s.home_xg
            FROM signals s
            JOIN fixtures f ON f.id = s.fixture_id
            WHERE f.home_score IS NOT NULL
              AND f.away_score IS NOT NULL
            ORDER BY f.event_date, s.id
        """))
        rows = r.fetchall()

    print(f"\nLoaded {len(rows)} settled signal rows from DB.")

    old_picks, old_rej = _process_rows(rows, OLD_STAKE_LEVELS, OLD_X2_MAX_STAKE)
    new_picks, new_rej = _process_rows(rows, NEW_STAKE_LEVELS, NEW_X2_MAX_STAKE)

    old = _scorecard("OLD STAKES  (K50k / K75k / K75k X2 cap)", old_picks, old_rej)
    new = _scorecard("NEW STAKES  (K40k / K75k / K100k)", new_picks, new_rej)

    if old and new:
        W = 74
        print("\n" + "=" * W)
        print("  DELTA  (new vs old)")
        print("=" * W)
        dpnl   = new["pnl"]   - old["pnl"]
        droi   = new["roi"]   - old["roi"]
        dstake = new["staked"] - old["staked"]
        print(f"  ROI change      : {old['roi']:+.2f}%  →  {new['roi']:+.2f}%  (Δ {droi:+.2f}pp)")
        print(f"  P&L change      : {old['pnl']:+,.0f}  →  {new['pnl']:+,.0f}  (Δ {dpnl:+,.0f} MWK)")
        print(f"  Total staked    : {old['staked']:,.0f}  →  {new['staked']:,.0f}  (Δ {dstake:+,.0f} MWK)")
        print("=" * W)


if __name__ == "__main__":
    asyncio.run(main())
