# TEASERS SOP
**Purpose:** two day sets of 5 teasers, each 6 legs at +6 points, from DK spreads and totals (Bovada line if DK is missing).
- **Saturday CFB**: only FBS games kicking on the coming Saturday (CT date).
- **Sunday NFL**: only NFL games kicking on the coming Sunday (CT date). Thursday and Monday games are excluded.

1. Candidate legs: both sides of every spread and total for that day's games, with kick still in the future. CFB odds are pulled only when a game is within 36h (credit cap), so the Saturday set fills in from the Friday 9am run.
2. Leg % = KEYS P(cover teased line | no push) at the consensus center, shrunk toward the band's historical rate with k = 150 (`data/teaser_bands.json`).
3. Ticket #1: NFL = top 6 **spread** legs, one per game (the backtested rule). CFB = top 6 legs, spreads or totals.
4. Tickets #2–5: greedy next-best legs. Each leg used at most twice across the day's 5 tickets; never two legs from one game in a ticket.
5. Ticket math assumes independent legs and enumerates push states. Ties reduce (6→5 legs pays +400, etc.). EV per 1u at +600. Break-even 14.29% per ticket, 72.3% per leg.
6. Labels: **PLAY** = model EV > 0; **PASS** = otherwise.
7. Backtest per set (`backtest/teaser_split_bt.py` → `data/teaser_backtest.json`) is shown on each set, including ticket #1, all-5 and PLAY-only records. Current: Sunday NFL ticket #1 +11u on 193 (CI [−43, +69]); Saturday CFB ticket #1 −21u on 35 (2 cashed), 0 PLAY tickets ever qualified.
