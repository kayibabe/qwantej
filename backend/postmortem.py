"""
Deep-dive postmortem on bad dates + structural patterns.

Outputs:
1. All picks (W/L) for Jul 10, 19, 21, 25
2. Stats by country for 'World' (UEFA qualifying) picks across full window
3. Stats by Russia picks
4. Stats by cup-pattern leagues (League Cup, Coppa, Pokal, Copa, Cup in league name)
5. xG difference distribution for losses vs wins
"""
import asyncio, sys
sys.path.insert(0, '.')

from app.core.config import (
    HYBRID_B_PERMANENT_BLACKLIST,
    HYBRID_B_STAKE_LEVELS,
    HYBRID_B_MIN_ODDS,
    HYBRID_B_MAX_ODDS,
    HYBRID_B_X2_MAX_STAKE,
)

START = "2026-07-08"
END   = "2026-07-27"

# Copy recovery/filter logic from sim
def _recover_odds(ep):
    if ep is None or ep <= 0:
        return None
    if ep < 12_500:
        return round(ep / 50_000 + 1, 6)
    return round(ep / 75_000 + 1, 6)

def _odds_in_window(odds):
    if odds is None: return False
    return HYBRID_B_MIN_ODDS <= odds <= HYBRID_B_MAX_ODDS

def _is_blacklisted(league, country):
    ll = (league or "").lower().strip()
    return any(bl in ll for bl in HYBRID_B_PERMANENT_BLACKLIST)

def _stake_for(odds, market):
    for tier in ("HIGH", "MEDIUM", "LOW"):
        if odds >= HYBRID_B_STAKE_LEVELS[tier]["min_odds"]:
            base = HYBRID_B_STAKE_LEVELS[tier]["base_stake"]
            if market == "X2" and base > HYBRID_B_X2_MAX_STAKE:
                return HYBRID_B_X2_MAX_STAKE
            return base
    return 0.0

def _is_win(market, home_score, away_score):
    if home_score is None or away_score is None: return None
    h, a = int(home_score), int(away_score)
    if market == "X2": return h <= a
    if market == "Away O0.5": return a >= 1
    return None

def _qualify(row):
    """Return (market, odds, stake, win) or None if rejected."""
    if _is_blacklisted(row.league, row.country):
        return None
    raw_ep_x2   = row.ep_x2
    raw_ep_ao05 = row.ep_ao05
    odds_x2   = _recover_odds(raw_ep_x2)
    odds_ao05 = _recover_odds(raw_ep_ao05)
    x2_in   = _odds_in_window(odds_x2)
    ao05_in = _odds_in_window(odds_ao05)
    ep_x2   = raw_ep_x2   if x2_in   else None
    ep_ao05 = raw_ep_ao05 if ao05_in else None
    if ep_x2 is None and ep_ao05 is None:
        return None
    if ep_x2 and ep_ao05:
        if ep_x2 > ep_ao05:
            market, odds = "X2", odds_x2
        elif ep_ao05 > ep_x2:
            market, odds = "Away O0.5", odds_ao05
        else:
            market, odds = ("X2", odds_x2) if (row.away_xg or 0) >= (row.home_xg or 0) else ("Away O0.5", odds_ao05)
    elif ep_x2:
        market, odds = "X2", odds_x2
    else:
        market, odds = "Away O0.5", odds_ao05
    if not odds:
        return None
    stake = _stake_for(odds, market)
    win = _is_win(market, row.home_score, row.away_score)
    if win is None:
        return None
    return market, odds, stake, win

async def main():
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    from collections import defaultdict

    async with AsyncSessionLocal() as db:
        r = await db.execute(text(f"""
            SELECT
                f.event_date, f.home_team, f.away_team,
                f.league, f.country,
                f.home_score, f.away_score,
                s.ep_x2, s.ep_away_o05 AS ep_ao05, s.away_xg, s.home_xg
            FROM signals s
            JOIN fixtures f ON f.id = s.fixture_id
            WHERE f.event_date BETWEEN '{START}' AND '{END}'
              AND f.home_score IS NOT NULL AND f.away_score IS NOT NULL
            ORDER BY f.event_date, s.id
        """))
        rows = r.fetchall()

    # Build qualified pick list
    picks = []
    for row in rows:
        q = _qualify(row)
        if not q:
            continue
        market, odds, stake, win = q
        pnl = round(stake * (odds - 1) if win else -stake, 2)
        picks.append({
            "date": str(row.event_date)[:10],
            "match": f"{row.home_team} vs {row.away_team}",
            "league": row.league or "",
            "country": row.country or "",
            "market": market,
            "odds": odds,
            "stake": stake,
            "win": win,
            "pnl": pnl,
            "home_xg": row.home_xg or 0,
            "away_xg": row.away_xg or 0,
        })

    W = 78
    def hdr(t): pad=(W-len(t)-2)//2; print(f"\n{'─'*pad} {t} {'─'*(W-pad-len(t)-2)}")

    # ── 1. BAD-DATE PICK DETAILS ───────────────────────────────────────────
    BAD_DATES = {"2026-07-10", "2026-07-19", "2026-07-21", "2026-07-25"}
    for bd in sorted(BAD_DATES):
        day_picks = [p for p in picks if p["date"] == bd]
        won  = sum(1 for p in day_picks if p["win"])
        lost = sum(1 for p in day_picks if not p["win"])
        hdr(f"{bd} — {won}W / {lost}L ({len(day_picks)} picks)")
        for p in day_picks:
            icon = "✓" if p["win"] else "✗"
            xg_str = f"H{p['home_xg']:.2f}/A{p['away_xg']:.2f}"
            print(f"  {icon} {p['market']:<12} {p['odds']:.3f}  {xg_str}  {p['match']}")
            print(f"    {p['country']} · {p['league']}")

    # ── 2. COUNTRY STATS ─────────────────────────────────────────────────
    hdr("STATS BY COUNTRY (≥3 picks)")
    country_stats = defaultdict(lambda: {"won":0,"lost":0,"pnl":0.0,"stake":0.0})
    for p in picks:
        c = p["country"]
        country_stats[c]["won"]   += 1 if p["win"] else 0
        country_stats[c]["lost"]  += 0 if p["win"] else 1
        country_stats[c]["pnl"]   += p["pnl"]
        country_stats[c]["stake"] += p["stake"]
    print(f"  {'Country':<24}  {'W':>3}  {'L':>3}  {'N':>4}  {'WR%':>6}  {'ROI%':>7}  {'P&L':>12}")
    print(f"  {'─'*24}  {'─'*3}  {'─'*3}  {'─'*4}  {'─'*6}  {'─'*7}  {'─'*12}")
    for c, cs in sorted(country_stats.items(), key=lambda x: -(x[1]["won"]+x[1]["lost"])):
        n = cs["won"]+cs["lost"]
        if n < 3: continue
        wr = cs["won"]/n*100
        roi = cs["pnl"]/cs["stake"]*100 if cs["stake"] else 0
        flag = " ◄" if wr < 70 else ""
        print(f"  {c:<24}  {cs['won']:>3}  {cs['lost']:>3}  {n:>4}  {wr:>5.1f}%  {roi:>+6.2f}%  {cs['pnl']:>+12,.0f}{flag}")

    # ── 3. LEAGUE PATTERN ANALYSIS ───────────────────────────────────────
    # Cup competitions
    hdr("CUP COMPETITIONS (league name contains cup/copa/pokal/coupe/coppa/league cup/cup)")
    CUP_KEYWORDS = ["cup", "copa", "pokal", "coupe", "coppa"]
    cup_picks = [p for p in picks if any(k in p["league"].lower() for k in CUP_KEYWORDS)]
    mkt_stats = defaultdict(lambda: {"won":0,"lost":0,"pnl":0.0,"stake":0.0})
    for p in cup_picks:
        mkt_stats[p["market"]]["won"]   += 1 if p["win"] else 0
        mkt_stats[p["market"]]["lost"]  += 0 if p["win"] else 1
        mkt_stats[p["market"]]["pnl"]   += p["pnl"]
        mkt_stats[p["market"]]["stake"] += p["stake"]
    cup_w = sum(1 for p in cup_picks if p["win"])
    cup_l = len(cup_picks) - cup_w
    cup_wr = cup_w/(cup_w+cup_l)*100 if cup_picks else 0
    print(f"  Total cup picks: {len(cup_picks)}, WR={cup_wr:.1f}%")
    for mkt, ms in sorted(mkt_stats.items()):
        n = ms["won"]+ms["lost"]
        wr = ms["won"]/n*100
        roi = ms["pnl"]/ms["stake"]*100 if ms["stake"] else 0
        print(f"    {mkt:<14} {ms['won']}W/{ms['lost']}L  WR={wr:.1f}%  ROI={roi:+.2f}%")
    print(f"\n  Cup losses:")
    for p in cup_picks:
        if not p["win"]:
            print(f"    ✗ {p['market']:<12} {p['odds']:.3f}  {p['match']}  ({p['country']} · {p['league']})")

    # ── 4. WORLD (UEFA) ANALYSIS ──────────────────────────────────────────
    hdr("WORLD (UEFA QUALIFYING) — breakdown by market")
    world_picks = [p for p in picks if p["country"].lower() == "world"]
    w_w = sum(1 for p in world_picks if p["win"])
    w_l = len(world_picks) - w_w
    print(f"  Total World picks: {len(world_picks)}, WR={w_w/(w_w+w_l)*100 if world_picks else 0:.1f}%")
    by_mkt = defaultdict(lambda: {"won":0,"lost":0,"pnl":0.0,"stake":0.0})
    for p in world_picks:
        by_mkt[p["market"]]["won"]   += 1 if p["win"] else 0
        by_mkt[p["market"]]["lost"]  += 0 if p["win"] else 1
        by_mkt[p["market"]]["pnl"]   += p["pnl"]
        by_mkt[p["market"]]["stake"] += p["stake"]
    for mkt, ms in sorted(by_mkt.items()):
        n = ms["won"]+ms["lost"]
        wr = ms["won"]/n*100
        roi = ms["pnl"]/ms["stake"]*100 if ms["stake"] else 0
        print(f"    {mkt:<14} {ms['won']}W/{ms['lost']}L  WR={wr:.1f}%  ROI={roi:+.2f}%")
    print(f"\n  World losses:")
    for p in world_picks:
        if not p["win"]:
            print(f"    ✗ {p['market']:<12} {p['odds']:.3f}  {p['match']}  {p['league']}")

    # ── 5. HIGH-VOLUME LOSING LEAGUES ────────────────────────────────────
    hdr("ALL LEAGUES WITH LOSSES (sorted by loss count)")
    league_stats = defaultdict(lambda: {"won":0,"lost":0,"pnl":0.0,"stake":0.0,"country":""})
    for p in picks:
        ls = league_stats[p["league"]]
        ls["won"]   += 1 if p["win"] else 0
        ls["lost"]  += 0 if p["win"] else 1
        ls["pnl"]   += p["pnl"]
        ls["stake"] += p["stake"]
        ls["country"] = p["country"]
    print(f"  {'League':<40}  {'W':>3}  {'L':>3}  {'WR%':>6}  {'ROI%':>7}")
    print(f"  {'─'*40}  {'─'*3}  {'─'*3}  {'─'*6}  {'─'*7}")
    for lg, ls in sorted(league_stats.items(), key=lambda x: -x[1]["lost"]):
        if ls["lost"] == 0: continue
        n = ls["won"]+ls["lost"]
        wr = ls["won"]/n*100
        roi = ls["pnl"]/ls["stake"]*100 if ls["stake"] else 0
        flag = " ◄◄" if wr < 50 else (" ◄" if wr < 70 else "")
        print(f"  {lg:<40}  {ls['won']:>3}  {ls['lost']:>3}  {wr:>5.1f}%  {roi:>+6.2f}%{flag}")

    # ── 6. xG PROFILE OF LOSSES ──────────────────────────────────────────
    hdr("xG PROFILE: losses vs wins")
    losses = [p for p in picks if not p["win"]]
    wins   = [p for p in picks if p["win"]]
    def avg(lst, key): return sum(p[key] for p in lst)/len(lst) if lst else 0
    print(f"  Losses ({len(losses)}): avg away_xg={avg(losses,'away_xg'):.2f}  avg home_xg={avg(losses,'home_xg'):.2f}  avg gap={avg(losses,'away_xg')-avg(losses,'home_xg'):.2f}")
    print(f"  Wins   ({len(wins)}):   avg away_xg={avg(wins,'away_xg'):.2f}  avg home_xg={avg(wins,'home_xg'):.2f}  avg gap={avg(wins,'away_xg')-avg(wins,'home_xg'):.2f}")
    # Bucket by xG gap
    print(f"\n  By xG gap (away_xg - home_xg):")
    buckets = [("< -0.5", lambda p: p["away_xg"]-p["home_xg"] < -0.5),
               ("-0.5 to 0", lambda p: -0.5 <= p["away_xg"]-p["home_xg"] < 0),
               ("0 to 0.5", lambda p: 0 <= p["away_xg"]-p["home_xg"] < 0.5),
               ("0.5 to 1.0", lambda p: 0.5 <= p["away_xg"]-p["home_xg"] < 1.0),
               (">= 1.0", lambda p: p["away_xg"]-p["home_xg"] >= 1.0)]
    for label, fn in buckets:
        bp = [p for p in picks if fn(p)]
        if not bp: continue
        bw = sum(1 for p in bp if p["win"])
        bl = len(bp) - bw
        bwr = bw/(bw+bl)*100 if bp else 0
        broi = sum(p["pnl"] for p in bp)/sum(p["stake"] for p in bp)*100 if bp else 0
        print(f"    {label:<14}  {bw}W/{bl}L  WR={bwr:.1f}%  ROI={broi:+.2f}%")

    print()

asyncio.run(main())
