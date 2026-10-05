# SHOPPER (Board) SOP
**Purpose:** for every NFL game this week (to Tuesday 6am CT) and every FBS game in the next 40h, show ML, spread and O/U with Mkt %, Model %, edge, EV, and PICK or PASS.
1. Fair center = the median of KEYS anchors over every non-target book's two-way line (Pinnacle included). If fewer than 3 books are available, fall back to Pinnacle alone. If neither exists, show no model.
2. ML fair = the median no-vig h2h across non-target books. If there is no h2h, use the KEYS conversion of the spread fair.
3. For each DK and Bovada side: Model % = KEYS P(win | no push) at that exact line, EV = p_win·payout − p_loss (a push returns the stake), and Mkt % = that book's two-way no-vig.
4. **PICK** (spread/total only) requires: best-side EV ≥ 3% (raised from 2% on 2026-10-03), at least 3 reference books, |model − book no-vig| ≤ 6pp (a stale-line guard), the game's |spread| < 30 (blowout guard; uses the DK/Bovada line), and |fair center − book line| ≤ 3 pts (`board.MAX_PT_GAP`; spread center = −line for home, line for away; total = line). A bigger gap usually means a stale/bad price or a model miss, not an edge. Anything else is PASS, with the reason shown.
4b. **ML is reference-only** (`ML_PICKS = False`). It is shown with model %, market % and EV, labeled REF, and never logged. Reason: the ML backtest at EV ≥ 2% went 253 bets, −22.3u, and Washington ML +285 lost on 2026-10-03. Open ML ledger items whose game had not kicked were VOIDed.
4c. Rule-change backtest: `backtest/board_rules_bt.py` → `data/board_rules_bt.json`. Old rules: 24 picks, +1.07u. New rules: 8 picks, 5-3, +1.63u. Both are small samples.
5. FBS filter: the TOA game's teams must appear on the ESPN FBS scoreboard (groups=80) for today through +2 days.
Backtest note: Brier is about equal to the book. The EV≥2% rule fired rarely, and none of the units are significant (see Method).
