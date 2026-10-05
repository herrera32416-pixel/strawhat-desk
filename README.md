# Strawhat Desk

A separate NFL + college football picks desk. It is market-anchored: KEYS outcome distributions, line shopping, and key-number teasers. **Picks only.** It never places bets and never messages anyone.

- Site: https://herrera32416-pixel.github.io/strawhat-desk/
- Daily run: GitHub Actions, one scheduled run per CT day between 9 and 11:59am CT: crons at 14:07/15:07 UTC plus backups at 15:37/16:37 UTC. A guard skips a slot if the CT hour is outside 9-11 or `data/last_scheduled_run_ct.txt` already has today. Manual runs always go and do not use up the slot. Pre-kick rechecks are driven by kickoff times: crons at :15/:45 run a free planner and only proceed when an unstarted official pick/PLAY teaser/prop kicks within ~70 min (Sunday ≈ 11:15am, 2:15pm, 6:15pm CT; 4 credits per window, max 3/day; see `team/RECHECK.md`). The 40-credit daily cap is enforced in `desk/toa.py`. See `.github/workflows/daily.yml`.
- Team and SOPs: `team/`. Research: `research/FINDINGS.md`. Backtests: `backtest/` (outputs in `backtest/out/`).
- Odds: The Odds API (DK + Bovada targets, consensus from every other book incl. Pinnacle), capped at 40 credits/day. Finals and box scores: ESPN. History: nflverse, desk-v1 CFB history (ESPN closes).

Reproduce the backtests (needs the cached historical snapshots in `data/raw/hist/`, already committed):
```
python backtest/sharp_ev.py            # ANCHOR=consensus|pinnacle|mix
python backtest/teasers_bt.py
python backtest/teaser_split_bt.py     # current teaser rule vs previous, Sunday NFL / Saturday CFB
python backtest/cfb_keys_buckets.py    # CFB key numbers by |spread| bucket
python backtest/matchup_bt.py --rebuild  # NFL matchup layer vs the market (needs data/matchup/team_games.csv.gz)
python backtest/matchup_cfb_bt.py --rebuild  # CFB matchup layer (cfbfastR pbp -> data/matchup/cfb_team_games.csv.gz)
python backtest/sim_bt.py              # simulator, 1,000 sims/game, vs the closing line
python backtest/props_bt.py && python backtest/props_market_bt.py && python backtest/props_shop_bt.py
```
