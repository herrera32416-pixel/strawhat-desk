# Board model-% accuracy (Oct 14 2026 CT): PAPER research
Rule tested: Luis plays the side with the higher board model % in each market (ML, spread/puck/run line, total).

## Data
- Live board: every git version of v1 + docs paper.json/today.json plus v1/data/2026*.json day files. For each game and market, the last snapshot taken before the game started, graded with ESPN finals (collect.py, grade.py → graded.json). Board games Oct 3–14: 564 graded (CFB 236, NHL 258, NFL 61, MLB 9).
- History (walk-forward, wf.py and mk.py): NHL xG model preds 2023-25 (1,937 games), MLB ESPN predictor 2023-26 (7,268 games, a stand-in because the Colab model has no backtest history), CFB FPI 2022-26 (2,751 games), plus ESPN/nflverse closing lines for spreads and totals.

## Live record (higher model % side)
307-250-7 (.551) overall: CFB 127-106-3, NHL 144-114, NFL 31-26-4, MLB 5-4. Brier: model 0.2339 vs market 0.2310.
- Right: favorites the model rated 60% or higher (CFB ML 78-37, NHL 55-58% bucket 37-21).
- Wrong: markets near 50/50. CFB spreads went 47-67 and NFL spreads 12-15, because the model is the market there (w=0), so the 'higher' side is noise or a tie. NHL totals went 39-47. NHL 50-55% plays went 50-56.
- NHL model vs market: the model's spread and total errors were larger than the market's. When the model favored a market underdog by 5+pp, it was worse than the market.

## Walk-forward tests
| test | market fav hit | raw model hit | logloss model / market |
|---|---|---|---|
| NHL ML | .578 | .559 | .6758 / .6724 (fitted model weight ≤0) |
| NHL puck line / total (v1 backtest, 2,636) | – | – | .6479/.6452, .6940/.6914 |
| MLB ML (ESPN predictor) | .567 | .559 | .6829 / .6766 (weight 0.06) |
| CFB ML (FPI) | .749 | .739 | .5062 / .4948 (weight 0.08) |
| NHL n7 factor | no gain in hit rate (.574 vs .578 shrink-only) | | dropped |
| FPI vs spread (CFB 3,930 / NFL 882) | – | .504 / .478 | no edge; NFL worse at bigger gaps |
Spreads and totals priced 50–52% hit about 50% (NHL tot .501 n=1818, MLB tot .507 n=5587, CFB spread .493 n=3056). From 52% up: .53–.65.

## Shipped (display only; no change to A/B/C, stamps or live pick rules)
1. NHL model weight 0: the board NHL model % = the market no-vig %, and the raw xG % is kept as model_raw_pct (hover). The old raw model was worse out of sample on all 3 markets in both log loss and hit rate.
2. 'Play' flag: the higher-% side is marked ★ only when it is ≥52%. Below that it shows ~ (coin flip, no play). Applies to all sports.
Live board replay: NHL .566 → .593 with weight 0. All sports, higher % with no play below 52%: 222-150 (.597) raw → 232-140 (.624) with NHL at weight 0, skipping 193 of 557 coin-flip markets.

## Proposed, not shipped
- MLB Colab: no backtest. Log at least 300 games, then fit its weight (the ESPN stand-in says ~0).
- A 55% threshold for a 'strong' tier: live .661 on 274 plays, history .55–.65. Small sample.
- Refresh after late news (goalie/pitcher): the stale log was fixed in f0e0260. No point-in-time history exists to test it.
Caveats: the live sample covers 11 days, and CFB/NHL games repeat across snapshots. The gain is about +2pp on NHL hit rate (history 57.8 vs 55.9 over 1,937 games), and the 52% cut is what removes most of the losses.
