"""
Full Jul 8–27 scorecard — current engine rules.

Reads settled TrackedBets from the DB (source_rule_key='system_hybrid_b'),
groups by date and market, and prints the complete scorecard table.

Run from backend/:
    python scorecard_jul8_27.py
"""
import asyncio, sys
sys.path.insert(0, '.')

START = "2026-07-08"
END   = "2026-07-27"

STAKE_LOW    = 50_000
STAKE_MED    = 75_000
STAKE_HIGH   = 75_000
STAKE_BONUS  = 100_000   # Away O0.5 only — X2 capped at 75k

async def main():
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:

        # ── 1. Raw settled bets ──────────────────────────────────────────────
        r = await db.execute(text(f"""
            SELECT
                tb.id,
                tb.event_date,
                tb.match_name,
                tb.market_type,
                tb.odds,
                tb.stake,
                tb.result_status,
                tb.profit_loss,
                tb.source_rule_label,
                f.league,
                f.country
            FROM tracked_bets tb
            LEFT JOIN fixtures f ON f.id = tb.fixture_id
            WHERE tb.event_date BETWEEN '{START}' AND '{END}'
              AND tb.source_rule_key = 'system_hybrid_b'
              AND tb.result_status IN ('Won', 'Lost')
            ORDER BY tb.event_date, tb.id
        """))
        rows = r.fetchall()

        if not rows:
            print("No settled Hybrid B bets found for Jul 8–27.")
            return

        # ── 2. Per-day aggregation ───────────────────────────────────────────
        from collections import defaultdict
        days = defaultdict(lambda: {"won": 0, "lost": 0, "pnl": 0.0, "stake": 0.0})
        markets = defaultdict(lambda: {"won": 0, "lost": 0, "pnl": 0.0, "stake": 0.0})
        odds_bands = {
            "1.21–1.30": {"won": 0, "lost": 0, "pnl": 0.0, "stake": 0.0},
            "1.31–1.40": {"won": 0, "lost": 0, "pnl": 0.0, "stake": 0.0},
            "1.41–1.50": {"won": 0, "lost": 0, "pnl": 0.0, "stake": 0.0},
            "other":     {"won": 0, "lost": 0, "pnl": 0.0, "stake": 0.0},
        }

        total_won = total_lost = 0
        total_pnl = 0.0
        total_staked = 0.0
        losses = []

        for b in rows:
            d = str(b.event_date)[:10]
            w = 1 if b.result_status == "Won" else 0
            l = 1 - w
            pnl   = float(b.profit_loss or 0)
            stake = float(b.stake or 0)

            days[d]["won"]   += w
            days[d]["lost"]  += l
            days[d]["pnl"]   += pnl
            days[d]["stake"] += stake

            mkt = b.market_type or "unknown"
            markets[mkt]["won"]   += w
            markets[mkt]["lost"]  += l
            markets[mkt]["pnl"]   += pnl
            markets[mkt]["stake"] += stake

            odds = float(b.odds or 0)
            if 1.21 <= odds <= 1.30:
                band = "1.21–1.30"
            elif 1.31 <= odds <= 1.40:
                band = "1.31–1.40"
            elif 1.41 <= odds <= 1.50:
                band = "1.41–1.50"
            else:
                band = "other"
            odds_bands[band]["won"]   += w
            odds_bands[band]["lost"]  += l
            odds_bands[band]["pnl"]   += pnl
            odds_bands[band]["stake"] += stake

            total_won   += w
            total_lost  += l
            total_pnl   += pnl
            total_staked += stake

            if l:
                losses.append({
                    "date": d,
                    "match": b.match_name,
                    "market": mkt,
                    "odds": odds,
                    "league": b.league or "",
                    "country": b.country or "",
                    "pnl": pnl,
                })

        total = total_won + total_lost
        wr  = total_won / total * 100 if total else 0
        roi = total_pnl / total_staked * 100 if total_staked else 0

        # ── 3. Print scorecard ───────────────────────────────────────────────
        W = 72
        def hdr(title):
            pad = (W - len(title) - 2) // 2
            print(f"\n{'─'*pad} {title} {'─'*(W - pad - len(title) - 2)}")

        print("=" * W)
        print(f"  HYBRID B SCORECARD — Jul 8–27 2026  ({total} settled bets)")
        print("=" * W)
        print(f"  Win rate : {wr:>6.1f}%")
        print(f"  ROI      : {roi:>+7.2f}%")
        print(f"  Net P&L  : {total_pnl:>+12,.0f} MWK")
        print(f"  Total staked: {total_staked:>12,.0f} MWK")
        print(f"  Won: {total_won}   Lost: {total_lost}")

        # ── Day-by-day table ─────────────────────────────────────────────────
        hdr("BY DATE")
        print(f"  {'Date':<12}  {'W':>3}  {'L':>3}  {'Picks':>5}  {'WR%':>6}  {'P&L (MWK)':>14}")
        print(f"  {'─'*12}  {'─'*3}  {'─'*3}  {'─'*5}  {'─'*6}  {'─'*14}")
        for d in sorted(days):
            dd = days[d]
            n  = dd["won"] + dd["lost"]
            wr_d = dd["won"] / n * 100 if n else 0
            flag = " ◄" if wr_d < 65 else ""
            print(f"  {d}  {dd['won']:>3}  {dd['lost']:>3}  {n:>5}  {wr_d:>5.1f}%  {dd['pnl']:>+14,.0f}{flag}")
        print(f"  {'─'*12}  {'─'*3}  {'─'*3}  {'─'*5}  {'─'*6}  {'─'*14}")
        print(f"  {'TOTAL':<12}  {total_won:>3}  {total_lost:>3}  {total:>5}  {wr:>5.1f}%  {total_pnl:>+14,.0f}")

        # ── By market ────────────────────────────────────────────────────────
        hdr("BY MARKET")
        print(f"  {'Market':<20}  {'W':>3}  {'L':>3}  {'Picks':>5}  {'WR%':>6}  {'ROI%':>7}  {'P&L (MWK)':>14}")
        print(f"  {'─'*20}  {'─'*3}  {'─'*3}  {'─'*5}  {'─'*6}  {'─'*7}  {'─'*14}")
        for mkt, md in sorted(markets.items()):
            n = md["won"] + md["lost"]
            wr_m  = md["won"] / n * 100 if n else 0
            roi_m = md["pnl"] / md["stake"] * 100 if md["stake"] else 0
            print(f"  {mkt:<20}  {md['won']:>3}  {md['lost']:>3}  {n:>5}  {wr_m:>5.1f}%  {roi_m:>+6.2f}%  {md['pnl']:>+14,.0f}")

        # ── By odds band ─────────────────────────────────────────────────────
        hdr("BY ODDS BAND")
        print(f"  {'Band':<12}  {'W':>3}  {'L':>3}  {'Picks':>5}  {'WR%':>6}  {'ROI%':>7}  {'P&L (MWK)':>14}")
        print(f"  {'─'*12}  {'─'*3}  {'─'*3}  {'─'*5}  {'─'*6}  {'─'*7}  {'─'*14}")
        for band in ["1.21–1.30", "1.31–1.40", "1.41–1.50", "other"]:
            bd = odds_bands[band]
            n  = bd["won"] + bd["lost"]
            if not n:
                continue
            wr_b  = bd["won"] / n * 100
            roi_b = bd["pnl"] / bd["stake"] * 100 if bd["stake"] else 0
            print(f"  {band:<12}  {bd['won']:>3}  {bd['lost']:>3}  {n:>5}  {wr_b:>5.1f}%  {roi_b:>+6.2f}%  {bd['pnl']:>+14,.0f}")

        # ── All losses ───────────────────────────────────────────────────────
        hdr(f"ALL LOSSES ({len(losses)} total)")
        if losses:
            print(f"  {'Date':<12}  {'Mkt':<12}  {'Odds':>5}  {'P&L':>12}  Match / League")
            print(f"  {'─'*12}  {'─'*12}  {'─'*5}  {'─'*12}  {'─'*30}")
            for lo in sorted(losses, key=lambda x: x["date"]):
                league_str = f"{lo['country']} · {lo['league']}" if lo['country'] else lo['league']
                print(f"  {lo['date']}  {lo['market']:<12}  {lo['odds']:>5.3f}  {lo['pnl']:>+12,.0f}  {lo['match']}")
                print(f"  {'':12}  {'':12}  {'':5}  {'':12}  {league_str}")

        print()
        print("=" * W)

if __name__ == "__main__":
    asyncio.run(main())
