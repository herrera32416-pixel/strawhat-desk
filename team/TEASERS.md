# TEASERS SOP (RETIRED 2026-10-08)
**Status: RETIRED.** Luis removed teasers and parlays on Oct 8 2026. `desk/teasers.py` was deleted, `desk/run.py` no longer builds or logs teaser sets, the recheck no longer touches them and the site has no Teasers tab. Past tickets stay in `data/ledger/ledger.json` and are still settled by the GRADER. The text below is kept for history only; do not run it.

**Purpose:** two day sets of 6-point teasers from DK spreads (Bovada line if DK is missing): one rule ticket plus up to 4 research tickets.
- **Saturday CFB**: only FBS games kicking on the coming Saturday (CT date). Research only: never PLAY.
- **Sunday NFL**: only NFL games kicking on the coming Sunday (CT date). Thursday and Monday games are excluded.

1. Candidate legs: both sides of every **spread** for that day's games, kick still in the future. Totals are not used (totals legs ran 66.7–69.9%; Oct 4 2026 live totals legs went 10-11).
2. Leg % = KEYS P(cover teased line | no push) at the consensus center, shrunk toward the band's historical rate with k = 150 (`data/teaser_bands.json`).
3. **Ticket #1 (rule ticket):** Wong legs first (dog +1.5..+2.5, fav −7.5..−8.5), then by leg %. Every leg must be ≥ **72.3%** (`teaser_math.MIN_LEG_P`), one per game, at most 6. 4, 5 or 6 legs, never padded with weaker legs; fewer than 4 qualifying legs means no ticket.
4. Prices (DK/Bovada standard 6-pt, `teaser_math.DK6`): 4 legs +260 (break-even 27.78% ticket, 72.60% per leg), 5 legs +400 (20.00%, 72.48%), 6 legs +600 (14.29%, 72.30%). Ties reduce the ticket.
5. **PLAY** = NFL rule ticket with model EV > 0 at its price. CFB is always PASS (`decision_reason` says why). These are the only official teaser plays.
6. Tickets #2–5: research, greedy 6-leg spread tickets, each leg used at most twice across the day; always PASS.
7. Ticket math assumes independent legs and enumerates push states.
8. Backtest (`backtest/teaser_split_bt.py` → `data/teaser_backtest.json`, uses the live `build_set`). Rules fixed before the run (Oct 4 2026), not tuned. Sunday NFL 2015–26: rule ticket 153 tickets, 31 cashed, **+1.2u**, 90% CI [−38.6, +46.0] (4 legs −2.8u on 46; 5 legs +6.0u on 44; 6 legs −2.0u on 63); research −115u on 812. Previous rule (top-6 legs, always 6): +11u on 193. CFB: 0 rule tickets in 38 Saturdays; research −41u on 174.
