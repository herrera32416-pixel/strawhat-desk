# SHOPPER (Board) SOP
**Purpose:** for every NFL game this week (to Tuesday 6am CT) and every FBS game in the next 40h, show ML, spread and O/U with Mkt %, Model %, edge, EV, and PICK or PASS.
1. Fair center = the median of KEYS anchors over every non-target book's two-way line (Pinnacle included). If fewer than 3 books are available, fall back to Pinnacle alone. If neither exists, show no model.
2. ML fair = the median no-vig h2h across non-target books. If there is no h2h, use the KEYS conversion of the spread fair.
3. For each DK and Bovada side: Model % = KEYS P(win | no push) at that exact line, EV = p_win·payout − p_loss (a push returns the stake), and Mkt % = that book's two-way no-vig.
4. **PICK** requires all three: best-side EV ≥ 2%, at least 3 reference books, and |model − book no-vig| ≤ 6pp (a stale-line guard). Anything else is PASS, with the reason shown.
5. FBS filter: the TOA game's teams must appear on the ESPN FBS scoreboard (groups=80) for today through +2 days.
Backtest note: Brier is about equal to the book. The EV≥2% rule fired rarely, and none of the units are significant (see Method).
