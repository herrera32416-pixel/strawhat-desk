# NHL SOP (INFO ONLY): matchups + market-anchored sim
**Purpose:** for every NHL game today/tomorrow, show unit-vs-unit mismatches and a 1,000-sim score distribution anchored to the de-vigged market, and say honestly whether any of it beats the close. It never makes a pick and never touches the board or ledger.

**Data (free, 0 Odds API credits for history):**
- MoneyPuck team game-by-game CSV (`desk/nhl_data.py`): xG, shot attempts, high-danger xG by situation (all / 5v5 / 5v4 / 4v5), 2019-20 → 2026-27 (17,088 team-games; 2026-27 through Oct 3 at build). Free for non-commercial use with credit (moneypuck.com/data.htm); one file per day, no scraping. Note: the separate Bet Bot NHL plan treated MoneyPuck as research-only for licensing reasons. This desk is a personal paper desk that makes no money, and Luis asked for it by name, but **stop using it if the desk ever goes commercial**.
- Results + closing lines 2021-22 → 2026-27: copied read-only from desk-v1 `data/history/nhl` (ESPN core /odds; DraftKings 2021-23, ESPN BET 2023-25): 6,533 games, ML/puck line ~99.8%, **totals missing for most of 2023-24** (108 of 1,312).
- Goalie game logs (starter, SA, SV): NHL stats API, 2020-21 → now (15,817 rows at build), refreshed daily for the current season.
- Rest/B2B from the schedule. Today's slate: api-web.nhle.com.

**Ratings (`desk/pro_ratings.walk_forward`, `desk/nhl_match.py`):** for each game date, a weighted ridge on games strictly before it (this season weight 1, last season 0.35, shrinkage 15 full-weight games, fixed a priori): metric = mu + O[team] + D[opp] + home. Units: 5v5 xGF/60, shot attempts/60, high-danger xG/60, power-play xG per game (D side = the opponent's penalty kill), PP time drawn (D = penalties taken), finishing (goals − xG). Goalie: starter's GSAx per game (situational xGA share − GA, decayed by season, shrunk by 20 games). Projected starter live = most starts in the last 10 games; on night 2 of a back-to-back the backup (never "confirmed").

**Matchup features (home − away):** expected 5v5 xG, HD xG, attempts, PP xG, PP time, finishing gaps; z(offense) × z(opposing defense) interactions for 5v5 xG, HD xG and PP-vs-PK; goalie GSAx gap and goalie × shot-quality faced; rest and B2B; style-similar foes (team's past goal-diff residual vs the market against opponents whose style looks like tonight's foe; Gaussian kernel τ 0.6, same foe counts fully, shrunk by 3) and common opponents (gap shrunk by 3). Totals: sums of the same units, goalies, B2B.

**Sim (`desk/nhl_sim.py`):** regulation goals = independent Poisson with draw inflation θ (the box research rejected bivariate Poisson: goal correlation −0.098). Empty net: from a 1-goal lead the leader scores an EN goal with prob e1 or the trailer ties with t1; from 2 up the leader adds one with e2. OT: decided in 3v3 with prob g (strength-tilted), else shootout 50/50; the winner gets +1 goal (book settlement). θ, e1, t1, e2 are fitted by likelihood on past seasons only and g is the past OT/(OT+SO) share. Live params: θ 1.3, e1 0.25, t1 0.04, e2 0.20, g 0.669. (λh, λa) are solved so the model reproduces the de-vigged ML (incl. OT) and P(over). The shrunk matchup lean then shifts λ. The site shows the exact model % and 1,000 Monte Carlo sims (score ranges, most common scores; ±1.6pp sampling noise per game).

**Test (`backtest/nhl_bt.py`, criteria in `research/PREREG_NBA_NHL.md`, committed before the run):** target = goal-diff and total residual vs the market-anchored sim; ridge with leave-one-season-out CV; out of sample 2022-23 → 2025-26.
**Result (2026-10-04): fails all three criteria on every market → INFO ONLY.**
| Market | OOS games | Log loss model / market | Δ 90% CI | Bets (edge ≥ 3pp, close price) | Units | Seasons + |
|---|---|---|---|---|---|---|
| ML | 5,248 | .66176 / .66206 | −.00049 … +.00106 | 425 (185 W), ROI +6.2% [−4.4%, +16.8%] | +26.2u | 2 of 4 |
| Puck line | 5,219 | .65495 / .65424 | −.00185 … +.00036 | 1,036 | −4.7u | 2 of 4 |
| Total | 3,905 | .68916 / .68877 | −.00089 … +.00011 | 110 | −10.4u | 0 of 3 |
The ML number looks good but its CI includes zero. 2022-23 had no bets at all (one training season, so CV shrinks fully), and 2025-26 was −1.9u. It goes on watch, not into picks. Calibration: the market-only sim's derived puck line is *worse* than DK's own puck-line price (log loss .65547 vs .65424, CI −.00213…−.00036), so the sim is a consistent pricer, not a sharper one (desk-v1 found the same). Leans are small: SD 0.11 goals (diff), 0.07 (total).

**Live:** `.github/workflows/pro.yml` (11:53am CT, backup 1:23pm CT, once per CT day) → `desk/pro_run.py` → `desk/nhl_run.py` → `docs/data/nhl.json` → site **NHL** tab (Matchups + Sim). Odds: one `/odds` pull per CT day (regions us,eu × h2h,totals = 4 credits), only when a game starts within 36h. The 9am desk run leaves those credits aside (`pro_lines.reserve_for_pro`). Otherwise it uses the latest saved file and the site shows its time. `data/nhl/model.json` has `influence=false`. Turning it on would need a passing re-run plus Luis's review.
Rebuild: `python -m desk.nhl_data --mp all_teams.csv` · `python backtest/nhl_bt.py` · `python -m desk.nhl_run --no-pull`.
