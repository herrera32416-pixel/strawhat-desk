# NBA SOP (INFO ONLY): matchups + possession sim
**Purpose:** the same as NHL. Unit mismatches and a 1,000-sim score distribution anchored to the de-vigged spread and total, with an honest test vs the close. It never makes a pick.

**Season:** opens Tue Oct 20 2026. Until ESPN lists games within 36h, the tab says "season starts Oct 20" and shows the backtest. The daily job starts sims automatically when games appear.

**Data (free, 0 Odds API credits for history):** ESPN site scoreboard + summary box scores + ESPN core `/odds` (`desk/nba_data.py`), regular seasons 2020-21 → 2025-26: 7,233 games (All-Star/exhibition teams dropped), box stats for every game. Lines: the ESPN-listed pregame close for 99.9% of games (spread, total, ML with prices). Provider: DraftKings 2020-23 and most of 2025-26; ESPN BET 2024-25 and part of 2025-26. Not used: stats.nba.com / nba_api (timed out from the box), the SBRO archive (stops around 2022-23), Kaggle odds sets (login needed). **Honest limit:** this is one book's final pregame line, not a sharp consensus close.

**Ratings (`desk/nba_match.py`):** walk-forward ridge as for NHL (shrinkage 10 games, fixed a priori). Units, offense and allowed: points/100 possessions, pace, eFG%, turnover rate, offensive-rebound %, FT rate (FTM/FGA), 3PA rate, 3P%, paint points/possession, fast-break points/possession. Possessions = FGA − ORB + TOV + 0.44·FTA (two-team average). Rest days, back-to-back, 3 games in 4 nights.

**Matchup features (home − away):** expected gaps for every unit; strength × weakness interactions (3PA rate vs 3PA allowed, 3P% vs 3P% defense, offensive vs defensive rebounding, paint vs rim protection, ball security vs turnover forcing, FT rate vs fouling); pace control and pace clash; rest/B2B/3-in-4; style-similar foes and common opponents on the cover residual. Totals: unit sums, pace, pace clash, rest.

**Sim (`desk/nba_sim.py`):** both teams get N possessions, N ~ Normal(101.4, 4.7). Each possession ends in a 2, a 3, a free-throw trip worth Binomial(2, FT%), or 0, with league rates from past box scores; make rates are scaled to each team's target points. Independent possessions overstate the margin spread, so a between-team possession correlation (ρ = 0.41) is fitted to the historical margin-vs-spread SD (13.47). Simulated total SD is 19.5 vs 18.9 actual, slightly wide. Ties go to 5-minute overtimes. The home margin and total centers are solved by bisection on common random numbers so that P(cover) and P(over) equal the de-vigged market, and the shrunk matchup lean then shifts them.

**Test (`backtest/nba_bt.py`, pre-registered in `research/PREREG_NBA_NHL.md`):** residual = home margin + home spread, and total − line; ridge with leave-one-season-out CV; out of sample 2022-23 → 2025-26. For speed the backtest uses the normal shortcut p = Φ(Φ⁻¹(q) + lean/σ). Checked against the full sim on 150 games: mean abs diff 0.3pp (cover), 0.3pp (over), 0.9pp (ML).
**Result (2026-10-04): fails all three criteria on every market → INFO ONLY.**
| Market | OOS games | Log loss model / market | Δ 90% CI | Bets | Record / units | Seasons + |
|---|---|---|---|---|---|---|
| Spread | 4,879 | .69236 / .69273 | −.00036 … +.00112 | |lean| ≥ 1.5: 95 | 48-47 (50.5%, CI 42.6-59.0% vs BE 52.2%), −3.2u | 1 of 4 |
| Total | 4,889 | .69271 / .69281 | −.00049 … +.00067 | 120 | 62-58, −1.7u | 1 of 4 |
| ML (from spread) | 4,917 | .58953 / .58861 | −.00200 … +.00025 | edge ≥ 3pp: 863 | −26.9u | 1 of 4 |
CV keeps the leans small (SD 0.55 pt spread, 0.58 total; only about 2% of games reach 1.5 pts). The spread→ML conversion is a worse pricer than the ML market itself, even with no lean (.58941 vs .58861).

**Live:** `desk/nba_run.py` via `desk/pro_run.py` (same workflow as NHL). When games are within 36h: ESPN results refresh, one `/odds` pull per CT day (us,eu × spreads,totals = 4 credits), features, then sim → `docs/data/nba.json` → **NBA** tab. `data/nba/model.json` has `influence=false`.
