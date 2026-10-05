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
- **Break-even.** A 6-leg ticket at +600 needs 1/7 = 14.29%, which is 72.3% per leg if legs are independent. 5 legs at +400: 20.0% ticket, 72.48% per leg. 4 legs at +260: 27.78% ticket, 72.60% per leg. A 2-team at −120 needs 73.9% per leg (nflanalytic.com).
- **Wong teasers.** Tease only through both 3 and 7: underdogs +1.5 to +2.5 up to +7.5/+8.5, and favorites −7.5 to −8.5 down to −1.5/−2.5.
  - nflanalytic.com, 1999–2025 closes: favorite legs 72.8% (493), dog legs 75.2% (904), fav −2.5/−3 62.8%, fav −10 64.8%, dog +7/+8 62.5%.
  - SportsGamblingPodcast/Reddit SDQL by season: +1.5 to +3 dogs at 74–80% in 2018–22; −7.5 to −9 favs at 71–89%.
  - Books have repriced the 2-teamers (−120 to −135), which is why "Wong is dead" at those prices.
- **Our data** (nflverse closes 2015–2026, walk-forward):
  - Wong dog 77.1% (363-108); Wong fav 72.0%; dog +3 72.8%; dog +3.5..+7 71.0%; fav −1..−3 68.1%; fav < −8.5 65.2%.
  - Totals legs run 66.7–69.9%. Totals have weak key numbers, so totals teasers rarely clear 72.3%.
  - CFB legs top out around 71% and lose as tickets.
  - **Correction (2026-10-04).** This line used to say "top-6 NFL spread legs each week made +55u on 195 tickets (90% CI [−6, +118])". That number is real but comes from `backtest/teaser_robust.py`, which picks from *every* game day of the week (Thu/Sun/Mon), so it can't be bet as one Sunday ticket. The bettable Sunday-only version (`backtest/teaser_split_bt.py`) made **+11u on 193 tickets** (30 cashed, ROI +6%, 90% CI [−43, +69]): no established edge.
  - **Current rule (2026-10-04):** spread legs only, Wong first, every leg ≥ 72.3%, 4–6 legs at +260/+400/+600, never padded. Sunday NFL 2015–26 (196 Sundays): 153 tickets, 31 cashed, **+1.2u**, ROI +1%, 90% CI [−38.6, +46.0]; 43 Sundays had no ticket. By size: 4 legs 46 tickets, −2.8u; 5 legs 44, +6.0u; 6 legs 63, −2.0u. Legs won 73.3%. Rules were fixed from the Oct 4 eval before this run and were not tuned to it. Break-even, not an edge.
  - CFB under the current rule: 0 tickets in 38 Saturdays (no Saturday had 4 spread legs ≥ 72.3%). CFB teasers are research only.
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

## Addendum 2026-10-04: CFB key numbers by spread size
`backtest/cfb_keys_buckets.py` (FBS 2023–26, 3,043 games, walk-forward). The old KEYS CFB pmf under-predicted the share of margins landing on 3/7/10/14/17/21 in every |spread| bucket: 15 of 30 bucket×key cells had |z| > 2 (max 6.8), worst at 7.5–21 and for road favorites. Two causes: the kernel was home-signed (road favorites are rare, so the bandwidth widened into home-favorite games), and the mean correction `np.roll` moved all key-number mass off its integers whenever the neighbours' mean line sat ≥ 0.5 from c. Fix (CFB margin only): a sign-symmetric kernel plus an exponential tilt for the mean. Result: 4 of 30 cells |z| > 2 (max 2.4), mean log-lik −4.247 → −4.032. Separate bucket tables were not needed because the kernel is already conditional on the line. NFL keeps the old kernel (dense data; not re-tested here). With the new CFB pmf the CFB research teasers backtest at −41u on 174 (was −69u); still losing.

## Addendum 2026-10-04: NFL matchup layer (unit vs unit, style similarity, common opponents)
Opponent-adjusted unit ratings were built from nflverse pbp 2015–26: pass and run EPA/SR, pressure proxy and sack rate, explosives, red zone, early-down pass rate. Features: offense-vs-defense gaps, strength×weakness interactions, a style-similar-opponent cover residual, and common-opponent cover gaps. Everything is walk-forward by game date. A residual model on the closing line, tested out of sample 2018–25 against criteria fixed before the run (`backtest/matchup_bt.py`, team/MATCHUP.md):
- Spread: log loss 0.6926 vs market 0.6925 on 2,175 games (improvement 90% CI −0.0005…+0.0004). CV shrinks every coefficient to ~0.
- Total: 0.6933 vs 0.6931 on 2,205 games.
- Forcing light shrinkage makes it worse: ATS |lean| ≥ 1.5: 188-197, −26u; O/U 301-306, −32u.
- **Conclusion:** the closing line already prices "elite pass rush vs weak OL", "run game vs run D" and common-opponent results. Shipped INFO ONLY (Matchups tab); it never changes a pick. This matches the desk-v1 finding that public ratings get ~0 weight on top of the market.

## Addendum 2026-10-04 (b): CFB matchup layer and the game simulator
- **CFB matchup** (cfbfastR pbp 2021–26, FBS, ridge penalty 12, walk-forward), OOS 2024–25 vs the ESPN close:
  - Spread: log loss 0.6939 vs 0.6936 on 1,788 games. Total: 0.6927 vs 0.6932 (CI −0.0001…+0.0011). CV shrinks leans to ~0.25 pt. Fails → info only.
  - Watch item: a lightly-shrunk total model went 166-131 (+19.9u, both seasons positive). It was not pre-registered and is one of ~12 sensitivity cells, so it needs 2026 confirmation.
- **Simulator** (drive-level Monte Carlo anchored to the de-vigged market, shrunk matchup adjustments, raked to KEYS key-number pmfs; 1,000 sims/game, walk-forward):
  - NFL 2018–25: spread 0.6931 vs market 0.6925; total 0.6936 vs 0.6931. Bets at a 3pp gap: 2-8 and 25-31.
  - CFB 2024–25: spread 0.6936 vs 0.6932; total 0.6925 vs 0.6932 (CI just above 0) but only 4 bets.
  - Fails the pre-registered criteria → info only.
  - Lesson: a simulator built on the market can't beat the market unless its inputs carry information the market lacks. Here the inputs don't.
- **KEYS finding:** the NFL margin pmf's `np.roll` mean correction is discontinuous for road favorites around 7 (4.3% vs ~14% on |margin| = 3 at a home line of +7). The sim uses the tilt correction. The board's NFL pmf is unchanged until a walk-forward test.
