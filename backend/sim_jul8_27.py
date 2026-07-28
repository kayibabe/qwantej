"""
Retrospective simulation — Jul 8–27 2026, current Hybrid B engine rules.

Reads raw signal rows from the DB, recovers implied odds from stored EP values,
applies ALL current engine filters (blacklist, odds window, Phase 3 EP logic,
X2 stake cap), determines win/loss from fixture scores, and prints the full
scorecard.

Does NOT touch tracked_bets — read-only simulation.

Run from backend/:
    python sim_jul8_27.py
"""
import asyncio, sys
sys.path.insert(0, '.')

from app.core.config import (
    HYBRID_B_PERMANENT_BLACKLIST,
    HYBRID_B_STAKE_LEVELS,
    HYBRID_B_MIN_ODDS,
    HYBRID_B_MAX_ODDS,
    HYBRID_B_X2_MAX_STAKE,
    HYBRID_B_AO05_SUPPRESSED_COUNTRIES,
)

START = "2026-07-08"
END   = "2026-07-27"


def _recover_odds(ep: float | None) -> float | None:
    """Recover the implied market odds from a stored EP value.

    EP was computed as: round(base_stake × (odds - 1), 2)
    Tier boundaries:
        LOW    [1.10, 1.25)  → base = 50,000
        MEDIUM [1.25, 1.40)  → base = 75,000
        HIGH   [1.40, ∞)     → base = 75,000

    Discriminator: ep < 12,500 → LOW (50k base); else → MEDIUM/HIGH (75k base).
    """
    if ep is None or ep <= 0:
        return None
    if ep < 12_500:
        return round(ep / 50_000 + 1, 6)
    return round(ep / 75_000 + 1, 6)


def _odds_in_window(odds: float | None) -> bool:
    if odds is None:
        return False
    return HYBRID_B_MIN_ODDS <= odds <= HYBRID_B_MAX_ODDS


def _is_blacklisted(league: str, country: str) -> bool:
    league_l  = (league  or "").lower().strip()
    country_l = (country or "").lower().strip()
    # Permanent blacklist matches league name only (same as engine Filter 3)
    return any(bl in league_l for bl in HYBRID_B_PERMANENT_BLACKLIST)


def _stake_for(odds: float, market: str) -> float:
    """Apply Phase 4 staking: tier by odds, X2 cap."""
    for tier in ("HIGH", "MEDIUM", "LOW"):
        if odds >= HYBRID_B_STAKE_LEVELS[tier]["min_odds"]:
            base = HYBRID_B_STAKE_LEVELS[tier]["base_stake"]
            if market == "X2" and base > HYBRID_B_X2_MAX_STAKE:
                return HYBRID_B_X2_MAX_STAKE
            return base
    return 0.0


def _is_win(market: str, home_score, away_score) -> bool | None:
    if home_score is None or away_score is None:
        return None
    h, a = int(home_score), int(away_score)
    if market == "X2":
        return h <= a       # Draw or Away Win
    if market == "Away O0.5":
        return a >= 1       # Away team scores
    return None


async def main():
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    from collections import defaultdict

    async with AsyncSessionLocal() as db:
        r = await db.execute(text(f"""
            SELECT
                s.id AS sig_id,
                f.event_date,
                f.home_team, f.away_team,
                f.league, f.country,
                f.home_score, f.away_score,
                s.ep_x2, s.ep_away_o05,
                s.away_xg, s.home_xg,
                s.selected_market AS engine_selected
            FROM signals s
            JOIN fixtures f ON f.id = s.fixture_id
            WHERE f.event_date BETWEEN '{START}' AND '{END}'
              AND f.home_score IS NOT NULL
              AND f.away_score IS NOT NULL
            ORDER BY f.event_date, s.id
        """))
        rows = r.fetchall()

    picks = []
    rejected_by = defaultdict(int)

    for row in rows:
        date    = str(row.event_date)[:10]
        league  = row.league or ""
        country = row.country or ""

        # Skip if no EP values — engine rejected at Phase 2 filters
        if row.ep_x2 is None and row.ep_away_o05 is None:
            rejected_by["phase2_no_ep"] += 1
            continue

        # Recover implied odds
        odds_x2   = _recover_odds(row.ep_x2)
        odds_ao05 = _recover_odds(row.ep_away_o05)

        # Blacklist filter (matches current engine Filter 3)
        if _is_blacklisted(league, country):
            rejected_by["blacklist"] += 1
            continue

        # EP-based market selection (mirrors Phase 3 decision matrix)
        x2_in   = _odds_in_window(odds_x2)
        ao05_in = _odds_in_window(odds_ao05)

        # Use only in-window markets for EP comparison
        ep_x2   = row.ep_x2   if x2_in   else None
        ep_ao05 = row.ep_away_o05 if ao05_in else None

        if ep_x2 is None and ep_ao05 is None:
            rejected_by["odds_window"] += 1
            continue

        # Select market by higher EP (same tie-break logic as engine)
        country_l = country.lower().strip()
        # When country is in AO0.5 suppressed list, zero out ao05 EP
        # so the engine is forced to X2 or rejects
        if country_l in HYBRID_B_AO05_SUPPRESSED_COUNTRIES:
            ep_ao05 = None
            odds_ao05 = None

        if ep_x2 is None and ep_ao05 is None:
            rejected_by["ao05_country_suppressed"] += 1
            continue

        if ep_x2 is not None and ep_ao05 is not None:
            if ep_x2 > ep_ao05:
                market, odds = "X2", odds_x2
            elif ep_ao05 > ep_x2:
                market, odds = "Away O0.5", odds_ao05
            else:
                if row.away_xg >= row.home_xg:
                    market, odds = "X2", odds_x2
                else:
                    market, odds = "Away O0.5", odds_ao05
        elif ep_x2 is not None:
            market, odds = "X2", odds_x2
        else:
            market, odds = "Away O0.5", odds_ao05

        if odds is None:
            rejected_by["no_odds"] += 1
            continue

        stake  = _stake_for(odds, market)
        result = _is_win(market, row.home_score, row.away_score)
        if result is None:
            rejected_by["no_result"] += 1
            continue

        pnl = round(stake * (odds - 1) if result else -stake, 2)

        picks.append({
            "date":    date,
            "match":   f"{row.home_team} vs {row.away_team}",
            "league":  league,
            "country": country,
            "market":  market,
            "odds":    odds,
            "stake":   stake,
            "result":  "Won" if result else "Lost",
            "pnl":     pnl,
        })

    if not picks:
        print("No qualifying picks found.")
        return

    # ── Aggregation ──────────────────────────────────────────────────────
    total_won   = sum(1 for p in picks if p["result"] == "Won")
    total_lost  = sum(1 for p in picks if p["result"] == "Lost")
    total       = len(picks)
    total_pnl   = sum(p["pnl"] for p in picks)
    total_stake = sum(p["stake"] for p in picks)
    wr  = total_won / total * 100 if total else 0
    roi = total_pnl / total_stake * 100 if total_stake else 0

    days    = defaultdict(lambda: {"won":0,"lost":0,"pnl":0.0,"stake":0.0})
    markets = defaultdict(lambda: {"won":0,"lost":0,"pnl":0.0,"stake":0.0})
    bands   = {
        "1.21–1.30": {"won":0,"lost":0,"pnl":0.0,"stake":0.0},
        "1.31–1.40": {"won":0,"lost":0,"pnl":0.0,"stake":0.0},
        "1.41–1.50": {"won":0,"lost":0,"pnl":0.0,"stake":0.0},
    }

    losses = []

    for p in picks:
        d  = p["date"]
        w  = 1 if p["result"] == "Won" else 0
        days[d]["won"]   += w; days[d]["lost"]   += 1-w
        days[d]["pnl"]   += p["pnl"]; days[d]["stake"] += p["stake"]
        markets[p["market"]]["won"]   += w
        markets[p["market"]]["lost"]  += 1-w
        markets[p["market"]]["pnl"]   += p["pnl"]
        markets[p["market"]]["stake"] += p["stake"]
        o = p["odds"]
        band = ("1.21–1.30" if o <= 1.30 else
                "1.31–1.40" if o <= 1.40 else "1.41–1.50")
        bands[band]["won"]   += w; bands[band]["lost"]   += 1-w
        bands[band]["pnl"]   += p["pnl"]; bands[band]["stake"] += p["stake"]
        if not w:
            losses.append(p)

    # ── Print ─────────────────────────────────────────────────────────────
    W = 74
    def hdr(t): pad=(W-len(t)-2)//2; print(f"\n{'─'*pad} {t} {'─'*(W-pad-len(t)-2)}")

    print("=" * W)
    print(f"  HYBRID B SCORECARD (RETROSPECTIVE) — Jul 8–27 2026")
    print(f"  Engine: odds window {HYBRID_B_MIN_ODDS}–{HYBRID_B_MAX_ODDS} "
          f"| X2 cap K{HYBRID_B_X2_MAX_STAKE/1000:.0f}k "
          f"| {len(HYBRID_B_PERMANENT_BLACKLIST)} blacklist terms")
    print("=" * W)
    print(f"  Qualifying picks : {total}")
    print(f"  Win rate         : {wr:.1f}%")
    print(f"  ROI              : {roi:+.2f}%")
    print(f"  Net P&L          : {total_pnl:+,.0f} MWK")
    print(f"  Total staked     : {total_stake:,.0f} MWK")
    print(f"  Won / Lost       : {total_won} / {total_lost}")
    print(f"\n  (Rejected: {sum(rejected_by.values())} signals — "
          f"phase2={rejected_by['phase2_no_ep']}, "
          f"blacklist={rejected_by['blacklist']}, "
          f"window={rejected_by['odds_window']}, "
          f"ao05_suppressed={rejected_by['ao05_country_suppressed']})")

    hdr("BY DATE")
    print(f"  {'Date':<12}  {'W':>3}  {'L':>3}  {'N':>4}  {'WR%':>6}  {'P&L (MWK)':>14}")
    print(f"  {'─'*12}  {'─'*3}  {'─'*3}  {'─'*4}  {'─'*6}  {'─'*14}")
    for d in sorted(days):
        dd = days[d]; n = dd["won"]+dd["lost"]
        wrd = dd["won"]/n*100 if n else 0
        flag = " ◄" if wrd < 65 else ""
        print(f"  {d}  {dd['won']:>3}  {dd['lost']:>3}  {n:>4}  {wrd:>5.1f}%  {dd['pnl']:>+14,.0f}{flag}")
    print(f"  {'─'*12}  {'─'*3}  {'─'*3}  {'─'*4}  {'─'*6}  {'─'*14}")
    print(f"  {'TOTAL':<12}  {total_won:>3}  {total_lost:>3}  {total:>4}  {wr:>5.1f}%  {total_pnl:>+14,.0f}")

    hdr("BY MARKET")
    print(f"  {'Market':<12}  {'W':>3}  {'L':>3}  {'N':>4}  {'WR%':>6}  {'ROI%':>7}  {'P&L (MWK)':>14}")
    print(f"  {'─'*12}  {'─'*3}  {'─'*3}  {'─'*4}  {'─'*6}  {'─'*7}  {'─'*14}")
    for mkt, md in sorted(markets.items()):
        n = md["won"]+md["lost"]
        wrm = md["won"]/n*100 if n else 0
        roim = md["pnl"]/md["stake"]*100 if md["stake"] else 0
        print(f"  {mkt:<12}  {md['won']:>3}  {md['lost']:>3}  {n:>4}  {wrm:>5.1f}%  {roim:>+6.2f}%  {md['pnl']:>+14,.0f}")

    hdr("BY ODDS BAND")
    print(f"  {'Band':<12}  {'W':>3}  {'L':>3}  {'N':>4}  {'WR%':>6}  {'ROI%':>7}  {'P&L (MWK)':>14}")
    print(f"  {'─'*12}  {'─'*3}  {'─'*3}  {'─'*4}  {'─'*6}  {'─'*7}  {'─'*14}")
    for band, bd in bands.items():
        n = bd["won"]+bd["lost"]
        if not n: continue
        wrb  = bd["won"]/n*100
        roib = bd["pnl"]/bd["stake"]*100 if bd["stake"] else 0
        print(f"  {band:<12}  {bd['won']:>3}  {bd['lost']:>3}  {n:>4}  {wrb:>5.1f}%  {roib:>+6.2f}%  {bd['pnl']:>+14,.0f}")

    hdr(f"ALL LOSSES ({len(losses)})")
    print(f"  {'Date':<12}  {'Mkt':<12}  {'Odds':>5}  {'P&L':>12}  Match")
    print(f"  {'─'*12}  {'─'*12}  {'─'*5}  {'─'*12}  {'─'*32}")
    for lo in sorted(losses, key=lambda x: x["date"]):
        league_str = f"{lo['country']} · {lo['league']}" if lo['country'] else lo['league']
        print(f"  {lo['date']}  {lo['market']:<12}  {lo['odds']:>5.3f}  {lo['pnl']:>+12,.0f}  {lo['match']}")
        print(f"  {'':12}  {'':12}  {'':5}  {'':12}  {league_str}")

    print()
    print("=" * W)


if __name__ == "__main__":
    asyncio.run(main())
