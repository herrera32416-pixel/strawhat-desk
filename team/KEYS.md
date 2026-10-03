# KEYS SOP
**Purpose:** convert any market line into win/push/loss probabilities, respecting NFL key numbers.
- Data: nflverse `games.csv` closes and results, 1999–2025 (NFL margin and total). For CFB, the desk-v1 ESPN closes 2022–25.
- The pmf at center c is the kernel-weighted empirical distribution of outcomes for games whose closing line was near c. Bandwidth starts at 0.5 pt and widens until the effective n is at least 400. It is mixed 85/15 with a discretized normal (σ 13.5 NFL margin, 15.5 CFB margin, 13.5/16.5 totals).
- `anchor(t, q)` uses bisection to find the center c* at which P(outcome > t | no push) equals the sharp no-vig q.
- Walk-forward rule: live and backtests use `max_season = season − 1` only.
- Sanity checks (2015–24 fit): at −3, the push rate is about 8.8%, and a −3 favorite at 50% ATS converts to about 60% ML.
