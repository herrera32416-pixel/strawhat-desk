# Strawhat Desk

A separate NFL + college football picks desk. It is market-anchored: KEYS outcome distributions, line shopping, and key-number teasers. **Picks only.** It never places bets and never messages anyone.

- Site: https://herrera32416-pixel.github.io/strawhat-desk/
- Daily run: GitHub Actions at 9:00am CT (DST-safe double cron with a guard). See `.github/workflows/daily.yml`.
- Team and SOPs: `team/`. Research: `research/FINDINGS.md`. Backtests: `backtest/` (outputs in `backtest/out/`).
- Odds: The Odds API (DK + Bovada targets, consensus from every other book incl. Pinnacle), capped at 40 credits/day. Finals and box scores: ESPN. History: nflverse, desk-v1 CFB history (ESPN closes).

Reproduce the backtests (needs the cached historical snapshots in `data/raw/hist/`, already committed):
```
python backtest/sharp_ev.py            # ANCHOR=consensus|pinnacle|mix
python backtest/teasers_bt.py
python backtest/props_bt.py && python backtest/props_market_bt.py && python backtest/props_shop_bt.py
```
