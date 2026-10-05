# Pre-registration: NBA and NHL matchup layers vs the closing line
*Written Sun Oct 4 2026, ~8:45 PM CT, before any NBA/NHL backtest was run. Committed to git before `backtest/nhl_bt.py` / `backtest/nba_bt.py` exist, so the commit time proves the order. Same method as the NFL layer (team/MATCHUP.md).*

## Common design
- Ratings: walk-forward weighted ridge on games strictly before each game date (`desk/pro_ratings.py`): metric = mu + O[team] + D[opp] + home; current season weight 1, previous 0.35.
- Target = residual vs the market: NBA spread residual = home margin + home spread; total residual = total points - total line. NHL goal-diff residual = home goals - away goals - market-implied expected diff; total residual = goals - market-implied expected total (from the market-anchored sim of the de-vigged ML + total).
- Model = ridge on standardized matchup features, no intercept, lambda by leave-one-season-out CV inside the training seasons; train on seasons < s, test on s. The lean is applied as a shift of the market-anchored distribution.
- Market = the ESPN-listed pregame close (single provider: DraftKings / ESPN BET / Caesars, as recorded) de-vigged two-way. It is not a sharp consensus close, which makes it *easier* to beat, so a pass would still need live CLV confirmation.
- 90% CIs are cluster bootstraps over game dates (2,000 reps).

## NHL (OOS seasons 2022-23, 2023-24, 2024-25, 2025-26; training starts 2021-22)
Markets: ML (incl. OT/SO), puck line +-1.5, total (2023-24 totals are mostly missing in the source, so totals are tested on the seasons that have them).
A market passes only if ALL hold, pooled OOS:
1. Log loss (model vs de-vigged close) improvement with 90% CI lower bound > 0.
2. Bets where model edge vs the de-vigged close >= 3 pp, priced at the recorded close: >= 100 bets and ROI 90% CI lower bound > 0.
3. Positive units in >= 3 of the 4 OOS seasons (>= 2 of 3 for totals).

## NBA (OOS seasons 2022-23, 2023-24, 2024-25, 2025-26; training starts 2021-22; 2020-21 is warm-up only)
Markets: spread, total, ML.
A market passes only if ALL hold, pooled OOS:
1. Log loss improvement (cover / over / home win, pushes excluded) with 90% CI lower bound > 0.
2. Spread/total: |lean| >= 1.5 points bets at the recorded close price, win% 90% CI lower bound > the break-even of those prices (52.38% at -110). ML: edge >= 3 pp bets, >= 100 bets, ROI 90% CI lower bound > 0.
3. Positive units in >= 3 of the 4 OOS seasons.

## Decision rule
Fail any criterion -> INFO ONLY (sim + matchups shown on the site, never a pick, never logged as official). Pass all three -> still not auto-enabled: flagged for Luis to review, plus a live CLV check, before any code change lets it influence picks.
Calibration checks of the market-only simulator (does the sim reproduce the market's own probabilities?) are reported but are not pass criteria.
