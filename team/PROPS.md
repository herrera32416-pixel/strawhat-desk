# PROPS SOP
**Purpose:** 5 NFL player props per game with line, price, model %, market % and edge.
1. **Planner.** For NFL events within 54h, pull missing markets in priority order: rec yds, rush yds, pass yds, receptions, anytime TD. On game day (kick within 14h), also re-pull any market last pulled more than 12h ago. Markets are spread round-robin across events until today's BUDGET is used (1 credit per market per event, region `us`).
2. **Projection** uses nflverse weekly player stats, pre-game only:
   - Team pass attempts and carries come from an OLS on the EWMA volume, the market's expected margin and the implied team total.
   - Share = EWMA target or carry share with a half-life of 4 games.
   - Efficiency is shrunk toward league priors.
   - The opponent's allowed efficiency is applied at 50% strength.
3. **Probability:** the empirical ratio of actual to projection, by market and projection tercile (`data/props_model.json`, 401 quantiles). Pass TDs use a Poisson. Anytime TD uses P(≥1) = 1 − e^(−EWMA TDs).
4. **Market %** is the median no-vig across every US book quoting that exact line. Anytime TD is one-sided, so it uses the median implied probability with vig included, and is labelled that way.
5. Rank by model − market and show the top 5 per game, one per player and market. Each one gets the best DK/Bovada price.
6. **Status: paper leans.** In backtest the model loses to the market (fitted w = 0). Leans are logged for tracking.
