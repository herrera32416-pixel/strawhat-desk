# NFL + CFB morning plan (Thu Oct 15 2026 CT)

## Working
- Coverage: every ESPN game this weekend is on the board (NFL Week 7: 14/14, FBS Week 8: 60/60). Built from Wed 9:41 AM CT run.
- ML/spread/total lines are on every game except 2 FCS-opponent MLs (Charleston Southern @ Clemson, Citadel @ Texas A&M): no DK/Betr/Bovada price exists.
- Stars and BE prices show wherever a model % exists.

## Broken → fixed tonight
- Model % blank on 19 spreads (best-book line ≠ consensus line) and on every NFL/CFB total (74). With FPI weight 0 the model IS the no-vig %, so the board now fills it (paper_model.board_model_view + model_calib). Football now has 0 blank model cells besides the 2 FCS MLs.

## Not wired (needs work, not safe overnight)
- QB / depth chart: v1 board has no QB or depth-chart input at all; the ESPN depth-chart pull is still pending.
- Injuries and weather: not used by v1 scripts (only the old betting-ops desk reads ESPN injuries for props).
- Line staleness: the board refreshes once a day (~9:15 CT) plus fallbacks; Saturday lines are ~3 days old by kickoff.

## Accuracy tests (walk-forward by season; football_results.txt)
Nothing passed cleanly (needs log loss + Brier + hit rate better, and most seasons):
- CFB ML favorite-longshot calibration: dLL −0.96, hit .749→.751, n=2,754, but only 2/4 seasons better → NOT on board. The 'p=0.97 n=1189' result does not hold up as a robust board change.
- CFB spread calibration: hit .502→.506, 3/4 seasons, tiny → no.
- Key numbers (3/7 hooks), home favorite, 21+ point spreads, FPI-minus-spread, line movement: all worse or flat (CFB n≈3,000, NFL n≈840).
- NFL FPI-minus-spread on ML (n=569, 1/2 seasons) and NFL total moved down open→close (n=248, 1 season): pass on paper, too small to trust.
- Spreads and totals stay coin flips: they show ~ (no play) unless one side is priced ≥52%.

## Ranked next steps
1. Wire ESPN depth chart + injury report for starting QB; log 'QB out' per game pre-kick. Need ~1 season of logs (or nflverse historical starters for NFL backtest now: doable, free).
2. Backtest NFL QB-out with nflverse starters 2006-25 (only free point-in-time QB data). Highest expected value.
3. Add a Saturday-morning refresh for CFB lines (stale 3-day lines).
4. Re-test NFL total line movement and FPI-minus-spread after 2026 season ends (n doubles).
5. Weather: pull game-time wind for NFL totals (wind dLL −0.43 near-miss, hit not better yet).
6. Multi-book consensus vs single book: start testing once our Odds API archive has ~8 weeks.
