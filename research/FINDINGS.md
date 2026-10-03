# Research findings: how sharps attack NFL/CFB sides, totals, props and teasers
Compiled Fri Oct 2 2026 (CT) for Strawhat Desk. Web sources were read Oct 2 2026. "Our data" means a computation in this repo (`backtest/`).

## 1. Sides and totals
- **The close is the benchmark.** Pros grade by CLV and expected ROI against a sharp no-vig close. Pinnacle or a consensus is the fair price, and you bet longer prices elsewhere. Sources: Buchdahl, *Wisdom of the Crowd* (football-data.co.uk); x-findings.md in `/workspace/research/pro-models-2026-10/`, with @spanky, @BettingIsCool and Unabated cited there. Buchdahl's ratio method is expected yield = your odds ÷ the sharp no-vig closing odds.
- **Prior DESK work on this box agrees.** FPI, public ratings, QB repricing, EPA features and non-QB injury values all get a fitted weight of about 0 against the close. See `betbot-revamp/research/upgrades-2026-10/FINAL_REPORT.md` and the nfl-/cfb-build FINAL_REPORTs. One analyst (@Matt_barlowe, 2026-08-21) also found no significant edge from "Pinnacle as truth + shop lines" on NFL/MLB moneylines.
- **Our data.** Odds API historical snapshots at 9am CT on game day: 20 NFL Sundays (2025 wk1–18, 2026 wk1–3) and 10 CFB Saturdays. Each one carries DK, Bovada, Pinnacle and about 20 other books.
  - A KEYS fair anchored to the consensus is marginally sharper than DK's own no-vig. CFB spreads: Brier .2496 vs .2503, ΔCI [−.0013, .0000].
  - But DK and Bovada sides with EV ≥ 2% vs that fair are rare: 5 NFL spread bets in 20 weeks.
  - None of the units are significant.
  - The Pinnacle-only anchor did worse. At 9am, Pinnacle is not yet the close.
- **Key numbers.** In nflverse 1999–2025, about 38.6% of NFL margins land between 3 and 7 (nflanalytic.com). Our KEYS pmf reproduces a push rate of about 8.8% at 3 for a −3 game. Half points around 3 and 7 are worth far more than other half points, so translating DK's line to the consensus line has to go through the empirical distribution rather than a normal.

## 2. Teasers
- **Payout (verified).** The DK football teaser at 6 points pays 2:−120, 3:+160, 4:+260, 5:+400, 6:+600. Source: ats.io DK teaser table, read Oct 2 2026. The Bovada regular-season NFL table also lists 6-team 6-pt at +600 (bovada.lv/help/sports-faq/teaser-betting). On both books, ties reduce the ticket (DK: "if a pick is a tie, the pick is removed").
- **Break-even.** A 6-leg ticket at +600 needs 1/7 = 14.29%, which is 72.3% per leg if legs are independent. A 2-team at −120 needs 73.9% per leg (nflanalytic.com).
- **Wong teasers.** Tease only through both 3 and 7: underdogs +1.5 to +2.5 up to +7.5/+8.5, and favorites −7.5 to −8.5 down to −1.5/−2.5.
  - nflanalytic.com, 1999–2025 closes: favorite legs 72.8% (493), dog legs 75.2% (904), fav −2.5/−3 62.8%, fav −10 64.8%, dog +7/+8 62.5%.
  - SportsGamblingPodcast/Reddit SDQL by season: +1.5 to +3 dogs at 74–80% in 2018–22; −7.5 to −9 favs at 71–89%.
  - Books have repriced the 2-teamers (−120 to −135), which is why "Wong is dead" at those prices.
- **Our data** (nflverse closes 2015–2026, walk-forward):
  - Wong dog 77.1% (363-108); Wong fav 72.0%; dog +3 72.8%; dog +3.5..+7 71.0%; fav −1..−3 68.1%; fav < −8.5 65.2%.
  - Totals legs run 66.7–69.9%. Totals have weak key numbers, so totals teasers rarely clear 72.3%.
  - CFB legs top out around 71% and lose as tickets.
  - Picking the top-6 NFL spread legs each week by modeled probability made +55u on 195 tickets (90% CI [−6, +118]).
  - Forcing 5 tickets a week from weaker legs lost 118u.
  - **Lesson:** the edge, if any, lives only in the very best legs, and leg count must be earned.
- Practical points: shop teaser prices, check push rules, and remember that books may price key-number teasers differently (DFF notes DK "prices may adjust according to the spreads").

## 3. Player props
- **What pros model** (Wincast "Prop Trading Desk"; Sports Command; PredictionMarketsPicks):
  - Usage first: snap share, route participation, target share, carry share. Then opponent-adjusted efficiency, then game environment from the market's spread and total. The output is a distribution, not a point estimate.
  - Medians matter because yardage is right-skewed. Sports Command claims +4.1pp from medians.
  - One shop publishes only receiving yards, rushing yards, receptions and pass TDs, and suppresses pass yards and anytime TD because those failed its walk-forward test. Its raw overs "run hot" and need calibration. These are self-reported claims.
- **Market structure.**
  - Props carry about 7.2–7.7% median/mean hold vs about 4.7–5.0% for NFL head-to-head (Bet Better Margin Index via bettorsearch.com, Sep 28 2026).
  - Books differ on nearly half of shared prop lines (BetBlum, 2025 wk1–9).
  - The public bets overs. SickFade's closing-line study (36,926 NFL props) puts blind NFL unders at +2.1% and overs at −15.8%. Upside.tools found unders are only more *numerous* among +EV rows, not larger.
  - Recency overreaction: unders on lines bumped after a spike hit 58.3% (Sports Command, self-reported).
- **Our data.**
  - The nflverse usage projection roughly ties a naive EWMA on MAE (2025: rec yds 15.56 vs 15.49, rush 10.11 vs 10.24, pass 39.1 vs 39.8).
  - On 1,608 real 2026 wk2–3 prop/book pairs it is worse than the market (Brier .266 vs .248), with fitted weight 0.00 [0, .23].
  - Blind DK unders: −20.6u on 865.
  - The props tab is therefore labelled paper leans.

## 4. What this means for the design
1. Do not out-rate the market. Price the market's own information correctly (KEYS) and shop across books.
2. Teasers are the one area where the structure (key numbers) gives a measurable, though not yet significant, edge. Ticket #1 follows that rule, and the others are flagged.
3. Props are tracked to build a sample. Nothing is called a winner until the ledger says so.

## Sources
- https://ats.io/sportsbooks/draftkings/parlays/ (DK teaser table)
- https://www.bovada.lv/help/sports-faq/teaser-betting
- https://nflanalytic.com/betting-teasers.html
- https://www.sportsgamblingpodcast.com/2023/09/06/lets-talk-about-teasers-week-1-nfl-wong-teasers/
- https://www.reddit.com/r/sportsbook/comments/16ofl02/
- https://blog.sportscommand.ai/player-props-football-the-analytical-playbook-for-finding-value-where-the-public-can-t
- https://predictionmarketspicks.com/articles/nfl-player-prop-projections-vs-the-market
- https://bettorsearch.com/nfl-prop-pricing-gaps-across/ , https://bettorsearch.com/player-prop-margins-nfl-week-1-data/
- https://wincastbetting.com/sports-guides/the-prop-trading-desk-how-sharp-shops-attack-nfl-player-markets/
- https://sickfade.com/overs-vs-unders , https://upside.tools/research/unders-vs-overs-player-props
- https://dailyfantasyfocus.com/how-to-do-teasers-on-draftkings-sportsbook/
- nflverse: https://github.com/nflverse/nfldata (games.csv), https://github.com/nflverse/nflverse-data/releases (stats_player)
- Box research reused: `/workspace/research/pro-models-2026-10/`, `/workspace/betbot-revamp/research/*/FINAL_REPORT.md`
