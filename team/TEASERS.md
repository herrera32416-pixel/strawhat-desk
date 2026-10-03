# TEASERS SOP
**Purpose:** 5 teasers, each 6 legs at +6 points, from DK spreads and totals (Bovada line if DK is missing).
1. Candidate legs: both sides of every NFL spread and total this week, plus FBS games within 40h. A CFB leg is allowed only if its leg % is at least 73.5% AND it beats the 18th-best NFL leg (CFB teasers lost in backtest).
2. Leg % = KEYS P(cover teased line | no push) at the consensus center, shrunk toward the band's historical rate with k = 150. Bands are in `data/teaser_bands.json` and come from nflverse closes 2006–2025.
3. Ticket #1 is the backtested rule: the top 6 NFL **spread** legs, one per game.
4. Tickets #2–5 are filled greedily from the remaining highest legs, spreads and totals. Each leg is used at most twice across the 5 tickets, and a ticket never holds two legs from one game.
5. Ticket math assumes independent legs and enumerates push states. DK rule: ties reduce the ticket (6→5 legs pays +400, and so on). EV is per 1u at +600. Break-even is 14.29% per ticket and 72.3% per leg.
6. Decision labels:
   - **PLAY**: ticket #1 with model EV > 0.
   - **LEAN +EV (untested rule)**: tickets #2–5 with EV > 0.
   - **PASS (−EV)**: everything else.
