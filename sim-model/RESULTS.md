# sim-model v1 results: strict walk-forward, Oct 10 2026

Every prediction uses only games before that week. The ridge mappings were refit each season on prior seasons. The noise parameter was calibrated on one season that isn't reported (NFL 2014, CFB 2022). Test sets: **NFL 2015–2025 (3,028 games)** and **CFB 2023–Oct 2026 (2,617 FBS games with ESPN BET closes)**. Market = closing no-vig.

## Headline: v1 does NOT beat the close in any market
| | Sim log loss | Market log loss | Sim Brier | Market Brier | Best sim weight in a sim/market blend |
|---|---|---|---|---|---|
| NFL ML | 0.6469 | **0.6122** | 0.2279 | **0.2122** | 0 |
| NFL spread | 0.7136 | **0.6930** | 0.2595 | **0.2499** | 0 |
| NFL total | 0.7050 | **0.6931** | 0.2557 | **0.2500** | 0.1 (0.69301 vs 0.69307, which is noise) |
| CFB ML | 0.5870 | **0.5180** | 0.2018 | **0.1737** | 0 |
| CFB spread | 0.7934 | **0.6931** | 0.2867 | **0.2499** | 0 |
| CFB total | 0.7178 | 0.6931 | 0.2610 | 0.2500 | **0.1–0.2 → 0.69238 (beats the market slightly)** |

The 70/30 blend loses to the pure market in every market: NFL ML 0.6299, spread 0.7031, total 0.6986. The CFB 70/30 blend is worse too.

| Mean absolute error | Sim | Closing line |
|---|---|---|
| NFL margin | 10.30 | **9.81** |
| NFL total | 10.68 | **10.44** |
| CFB margin | 14.11 | **11.88** |
| CFB total | 13.24 | **12.52** |

Correlation of the sim with the close: NFL margin 0.83, total 0.74; CFB margin 0.78, total 0.71. The sim is genuinely independent, but less accurate.

**Information beyond the close** (regressing actual−close on sim−close): NFL margin slope −0.02 (t −0.4), NFL total +0.03 (t 0.4), CFB margin +0.01 (t 0.4). **CFB total +0.16 (t 2.59)** is the only signal. It is consistent with the blend result but not yet a bettable edge (see ROI).

## Paper ROI, flat $20, sim edge ≥4 pts vs no-vig (actual closing prices; CFB totals assume −110)
- NFL ML −5.1% (2,283 bets). Spread −2.2% (1,999). Total −3.1% (1,817). Positive seasons: ML 4/11, spread 6/11, total 5/11. That's a coin flip, as expected with no edge.
- CFB ML −13.1%. Spread −5.5%. **Total −1.4%** by season: 2023 +1.4%, 2024 +2.3%, 2025 −7.4%, 2026 −1.7%.
- Blend (30% sim) at edge ≥3 pts: NFL total +1.8%, CFB total +0.4%. Everything else is negative.

## Why it loses, and what came closest
1. **Strength compression.** The sim's mean-margin SD is 3.6 points in the NFL vs 6.0 for the close. A walk-forward linear stretch helps (NFL margin MAE ~10.0–10.4 by season), but it still trails the close by 0.2–0.7 points every season.
2. **Overconfidence.** Per-game outcome spread is too wide in some places and too narrow in others, so tier-A "edges" of 15–30 points are common. They're miscalibration, not value.
3. **CFB totals bias:** +4.4 points high.
4. **Closest components:** CFB totals (tempo × drive efficiency), then NFL totals in high wind. Overs hit 43% of the time in 228 games with 15+ mph wind, while the sim said 46%. The QB adjustment did not beat the close in QB-change games (sim MAE 10.52 vs close 9.97, 459 games).

## Next steps (v2), in order
1. Calibrate distributions walk-forward: a margin stretch, an isotonic map on cover/over %, and fixing the CFB totals bias.
2. Model the drive at the play level (down/distance/field-position chain) so pace and red-zone effects come out naturally.
3. Add Open-Meteo weather for CFB, travel distance, returning production and injury-report starters (pregame snapshots only).
4. Add a game-day news layer (confirmed QB/weather vs line) — historically the most realistic edge.
5. Keep the gate at false until a market beats the close in ≥2 out-of-sample seasons with positive tier ROI.

# v2: NFL first, Oct 10 2026 ~11pm CT (same walk-forward rules; table on the common NFL 2016–2025 test set)
Changes kept: (a) **less shrinkage** (rating prior k 3→1, decay .93→.95, carryover .7→.8, ridge α 5→0.5); (b) **a walk-forward margin/total stretch** fit only on prior seasons' out-of-sample sim output (NFL margin ≈1.5–1.8×sim − 2.5; totals ≈1.0×); (c) Normal(sd from prior residuals) probabilities. A Platt layer was also tested. It flattens spread/total probabilities to ~49%, which means the sim's spread/total disagreement carries almost no information. I kept the Normal probabilities for display.

| NFL | Log loss v1 → v2 | Market | MAE v1 → v2 | Close |
|---|---|---|---|---|
| ML | 0.6442 → **0.6338** | 0.6086 | — | — |
| Spread | 0.7138 → 0.7119 (Platt 0.6943) | 0.6927 | margin 10.26 → **10.15** | 9.78 |
| Total | 0.7047 → 0.7098 (Platt 0.6943) | 0.6930 | total 10.68 → 10.72 | 10.44 |

v2 log loss minus market, by season (positive = worse than the market). **ML:** worse in 2016–2025, every season. **Spread:** better in 2018, 2019 and 2024 (−0.002 each). **Total:** better in 2020, 2022 and 2023 (−0.001 to −0.003). None of these is significant.
Paper ROI at edge ≥4 pts, $20 flat (v2 Normal): ML −9.3%, spread −3.0%, total −3.5%. Positive seasons: ML 2/10, spread 4/10, total 3/10.
**Gate check: no NFL market passes.** None beats the close in ≥2 seasons *and* is profitable overall. `SIM_LIVE` stays false.

## Matchup layer (tested, NOT kept)
- **Inputs:**
  - nflverse PBP for pass rate over expected, early-down pass rate, deep-pass rate, sack rate, run/pass success and run/pass explosive rate.
  - nflverse participation (FTN/NGS, 2016–2025) for pressure rate, blitz rate (5+ rushers) and man-coverage rate.
  - Play-action isn't in the free data.
- **Model:** these were added as opponent-adjusted ratings, plus 9 offense×defense interaction terms (pressure×pressure-allowed, sack×sack, blitz×pass success, man×deep rate, run×run, pass×pass, deep×explosive allowed, PROE and early-down pass rate × the defense's pass-run split).
- **Result (walk-forward, 2015–2025):**

| | ML log loss | Spread log loss | Total log loss | Margin MAE | Total MAE |
|---|---|---|---|---|---|
| With matchup | 0.6344 | 0.7110 | 0.7124 | 10.154 | 10.776 |
| Without | 0.6340 | 0.7116 | 0.7109 | 10.145 | 10.745 |

**No improvement, so it's dropped from the numbers.** The code stays behind `MATCHUP=1`. The picks file uses it only for a descriptive one-line note.

## Not done this round
- **CFB step 2** (Open-Meteo kickoff weather, travel distance, returning production): `src/cfb_env.py` is written, but its first run was interrupted when Luis moved NFL first. Not run yet.
- **CFB v2:** the CFB calibration result is from the v1 sims, 2024–26. The total stretch removed the +4 pt bias and the totals log loss reached 0.6929 vs 0.6931 for the market. ROI at edge ≥4 was +4.2% on few bets: 2024 +15.7%, 2025 −0.3%, 2026 +7.7%. That doesn't pass, because 2025 lost.
- **Play-level sim:** not started.
- **News-delta:** built into the slate picks as QB-change and wind flags vs the line. It has no backtest yet, because historical line timestamps around news aren't on the box.
