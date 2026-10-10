# Strawhat Desk

A separate NFL + college football picks desk. It is market-anchored: KEYS outcome distributions, and line shopping. **Picks only.** Teasers and parlays were retired on Oct 8 2026 (no longer built, logged or published; past tickets stay in the ledger). It never places bets and never messages anyone.

- Site: https://herrera32416-pixel.github.io/strawhat-desk/
- Daily run: GitHub Actions, one scheduled run per CT day between 9 and 11:59am CT: crons at 14:07/15:07 UTC plus backups at 15:37/16:37 UTC. A guard skips a slot if the CT hour is outside 9-11 or `data/last_scheduled_run_ct.txt` already has today. Manual runs always go and do not use up the slot. Pre-kick rechecks are driven by kickoff times: crons at :15/:45 run a free planner and only proceed when an unstarted official pick/prop kicks within ~70 min (Sunday ≈ 11:15am, 2:15pm, 6:15pm CT; 4 credits per window, max 3/day; see `team/RECHECK.md`). The 40-credit daily cap is enforced in `desk/toa.py`. See `.github/workflows/daily.yml`.
- **NBA + NHL (info only, Oct 4 2026):** NBA and NHL tabs with Matchups + a market-anchored 1,000-sim Sim panel. Own workflow `.github/workflows/pro.yml` (once per CT day ~11:53am CT; ≤ 4 Odds API credits per sport per day, set aside by the 9am run). Both failed their pre-registered tests vs the close, so they never make picks. See `team/NHL.md`, `team/NBA.md`.
- Team and SOPs: `team/`. Research: `research/FINDINGS.md`. Backtests: `backtest/` (outputs in `backtest/out/`).
- Odds: The Odds API (DK + Bovada targets, consensus from every other book incl. Pinnacle), capped at 40 credits/day. Finals and box scores: ESPN. History: nflverse, desk-v1 CFB history (ESPN closes).

Reproduce the backtests (needs the cached historical snapshots in `data/raw/hist/`, already committed):
```
python backtest/sharp_ev.py            # ANCHOR=consensus|pinnacle|mix
python backtest/teasers_bt.py          # historical research only (teasers retired 2026-10-08)
python backtest/cfb_keys_buckets.py    # CFB key numbers by |spread| bucket
python backtest/matchup_bt.py --rebuild  # NFL matchup layer vs the market (needs data/matchup/team_games.csv.gz)
python backtest/matchup_cfb_bt.py --rebuild  # CFB matchup layer (cfbfastR pbp -> data/matchup/cfb_team_games.csv.gz)
python backtest/sim_bt.py              # simulator, 1,000 sims/game, vs the closing line
python backtest/nhl_bt.py && python backtest/nba_bt.py   # NBA/NHL layers vs the close (data/nhl, data/nba committed)
python backtest/props_bt.py && python backtest/props_market_bt.py && python backtest/props_shop_bt.py
```

## Odds API budget (paid plan, October 2026)
Luis's paid Odds API plan is active for October 2026 only. Strawhat jobs (`daily.yml`, `pro.yml`) again use the key with
SH_DAILY_CAP=40, SH_MONTHLY_CAP=1200, SH_MIN_REMAINING=60 (floor guard), SH_REGIONS=us,eu, SH_PROPS=1 (NFL props on),
SH_MAX_RECHECKS=3 (pre-kick rechecks). Every call is still logged to data/credits.jsonl (x-requests-* headers).
**REVERT when he cancels next month:** SH_DAILY_CAP=10, SH_MONTHLY_CAP=220, SH_REGIONS=us, SH_PROPS=0, SH_MAX_RECHECKS=1
(keep SH_MIN_REMAINING=60). Same note is in desk/toa.py.
