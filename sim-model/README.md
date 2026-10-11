# sim-model: independent drive-level football simulator (PAPER ONLY)

Status (Oct 10 2026, ~11pm CT): v2 NFL done (see RESULTS.md); still does not beat the close, SIM_LIVE=false. Slate picks: `src/nfl_slate_picks.py` -> `out/picks/nfl_2026_w6.json` + `.md` (paper).

## Pipeline
| Step | Script | Output |
|---|---|---|
| NFL data | `src/nfl_build.py` | nflverse play-by-play 2012-2025 (`data/nfl/pbp_*.parquet`, downloaded from the nflverse-data releases) + `nfldata/games.csv` (closing ML/spread/total, rest, roof, surface, game-time temp/wind, starting QB ids) -> `data/nfl_team_games.parquet`, `data/nfl_qb_games.parquet` |
| CFB data | `src/cfb_build.py` | cfbfastR-style PBP 2021-2026 (`/workspace/cfbpbp`) + ESPN BET closing lines (`/workspace/eval/oct10/bt_games.parquet`, 3,411 FBS games 2022-26) -> `data/cfb_*`. FCS-vs-FCS games were dropped because the source has no drive results for them |
| Ratings + features | `src/ratings.py`, `src/build_features.py` (env `LEAGUE=nfl|cfb`) | Sequential per-week ratings: opponent-adjusted, recency-decayed (0.93/week), Bayesian-shrunk (prior k=3 games), with a 30-65% carryover between seasons. The metrics are EPA/play, success, explosive rate, TD/FG/turnover per drive, red-zone TD rate, drives (pace) and pass rate. Plus 4th-down go rate, FG%, a QB adjustment (the starter's shrunk dropback EPA, k=120, minus the team's previous starter's), rest differential, home/neutral, wind, cold, dome, turf and altitude |
| Sim + walk-forward | `src/sim.py`, `src/sim_eval.py` | For each test season, ridge maps (prior seasons only) turn the ratings into per-drive TD/FG/TO probabilities and drive counts. The drive-level Monte Carlo then runs 10,000 sims per game (TD = 7/6/8 points, defensive return TDs, OT handling, per-sim "day" noise calibrated on a non-reported season). The output is win %, cover %, over %, the margin and total distributions, and team totals -> `out/<lg>_sim_preds.parquet` |
| Report | `src/report.py` | `out/<lg>_results_v1.json` |
| Picks | `src/picks.py` | `out/picks/<lg>_<season>_w<week>.json`. One pick per game for each of ML, spread and total, with model %, market no-vig %, blend %, edge, tier A (8+ pts) / B (5+) / C (2+), and `status: paper` until the gate passes |

Run: `PYTHONPATH=src LEAGUE=nfl python3 src/build_features.py && PYTHONPATH=src LEAGUE=nfl python3 src/sim_eval.py && PYTHONPATH=src python3 src/report.py out/nfl_sim_preds.parquet NFL out/nfl_results_v1.json`

## Sunday rerun (one command)
`bash /workspace/sim-model/run_sunday.sh [nflverse_week=5] [out=out/picks/nfl_2026_w6.json]`: newest desk odds file (no credits) + fresh ESPN QB injuries + Open-Meteo forecast -> picks JSON + markdown.

## Board hookup (behind a flag)
`picks.py` JSON is the board contract: `games[].markets[] = {market, pick, price, model_pct, market_pct, blend_pct, edge_pts, tier, status}`. A market becomes `live` only when `config/gate.json` has `SIM_LIVE=true` and that market `passed=true`. The gate rule is written in the file. Flipping it is a desk-rule change and needs Luis's yes.

## Known gaps (not done yet; nothing invented)
- **Weather:** NFL uses nflverse's recorded game-time temp/wind, which is close to the kickoff forecast but not identical. CFB has no weather yet. The Open-Meteo archive pull and stadium coordinates are still to do.
- **Not built yet:** travel distance and CFB returning production. The CFB surface flag is also missing.
- **QB "starter":** this is the actual starter (NFL games.csv; CFB = the passer with the most dropbacks). That assumes the starter is known at kickoff, which is mildly optimistic.
- **Prices:** CFB total prices aren't in the history, so ROI assumes −110. CFB has no opening lines for most games, so no true CLV test was possible. Instead, the "beyond-close" regression tests whether (actual − close) is predicted by (sim − close).
- **Bias:** the CFB sim runs about 4 points high on totals, and both sims compress team strength. See RESULTS.md.

## NHL (next phase)
Reuse the same skeleton at the shot level. Data: NHL API play-by-play and shifts, plus MoneyPuck xG history and closing lines already in `/workspace/nhl-research`. Ratings: opponent-adjusted, shrunk 5v5 xGF/xGA per 60 by team and line, power-play/penalty-kill xG rates, and penalty-draw rates. **Goalie** GSAx is shrunk heavily, and the confirmed starter acts like an NFL QB. Rest/back-to-back and travel are included. The sim draws Poisson shot-attempt arrivals by game state (5v5/PP/PK), with xG→goal and goalie adjustment, empty-net logic and OT/shootout, over 10k sims. It outputs ML, puck line ±1.5 and total. Validation follows the same walk-forward/report/gate approach.
