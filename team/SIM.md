# SIM SOP (game simulator, NFL + FBS, INFO ONLY)
**Purpose:** 1,000 Monte Carlo games per upcoming NFL/FBS game. Output: win %, cover % at the current line, over %, median and 10–90% team scores, margin and total ranges, each with Δ vs the de-vigged market.

**Model (`desk/sim.py`):**
1. Baseline = market. The expected home margin c and total T are the KEYS centers that reproduce the de-vigged spread/total odds (`Dist.anchor`, tilt mean-correction).
2. Shrunk matchup adjustments:
   - means += the spread and total leans from the matchup residual models (CV ridge, which shrank them to ~0.1–0.3 pt);
   - each offense's TD share of scoring drives += 0.5 × (expected red-zone TD rate vs this defense − league);
   - drives × (1 + 0.02 × early-down pass-rate z), for pace.
3. Drive-level play: N drives per team (NFL 11.6, CFB 12.15); each drive is a TD (7, or 6/8 after a PAT miss or 2-pt try), a FG (3) or nothing. Per-drive probabilities are solved to hit each team's mean. Ties go to OT (NFL +3, CFB +7). Constants were measured on NFL pbp 2015–17 and CFB pbp 2021–23, before the backtest windows. Sim margin sd 13.5 NFL / 15.1 CFB vs real residual sd 13.4 / 15.3.
4. Key numbers: a pure drive model under-produces them (NFL |margin| = 3: 11% vs 15%), so the 1,000 sims are raked to the KEYS margin and total pmfs. All outputs are weighted (n_eff ≈ 700). Simulation noise is about ±3.5pp on any probability.

**Lines (0 Odds API credits):** NFL = nflverse schedule lines (includes next week's lookahead, e.g. Week 6 on Oct 4). FBS = ESPN scoreboard DraftKings lines. Market win % = de-vigged moneyline from the same source.

**Backtest (`backtest/sim_bt.py`, pre-registered):** walk-forward (KEYS and matchup leans fit on seasons < s), 1,000 sims per game. Criteria per sport/market on pooled OOS seasons (NFL 2018–25, CFB 2024–25): (1) log-loss improvement CI > 0; (2) bets with |sim − market| ≥ 3pp at −110 win, with CI low > 52.38%; (3) positive units in ≥ 6/8 NFL or 2/2 CFB seasons.

**Result: fails → INFO ONLY.**
- NFL spread: 0.6931 vs 0.6925 (CI −0.0012…+0.0001); 3pp bets 2-8.
- NFL total: 0.6936 vs 0.6931; bets 25-31, −8.3u.
- CFB spread: 0.6936 vs 0.6932; bets 6-4.
- CFB total: 0.6925 vs 0.6932, the one log-loss CI that excludes 0 (+0.0000…+0.0012), but only 4 bets (3-1), so criteria 2 and 3 fail.
- "Sim only" (no matchup) is about equal to the market, as it should be.

**Live:** `desk/run.py` → `desk/sim_run.py` → `docs/data/sim.json` → site **Sim** tab. It never changes a pick.
