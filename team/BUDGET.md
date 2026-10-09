# BUDGET SOP (Odds API credits)
- Every call goes through `desk/toa.get`, which logs the `x-requests-last/used/remaining` headers to `data/credits.jsonl`.
- **Daily cap: 40** credits (`SH_DAILY_CAP`). A call that would exceed it is refused before it is sent.
- Typical day: NFL 6, plus NCAAF 6 on CFB days, plus props with whatever is left after the **recheck reserve**.
- Recheck reserve: the 9am run holds back 4 credits per kickoff window that has an official item today (board PICKs, open board ledger items), max 12 (`recheck.reserve_credits`). Each recheck window re-pulls `/odds` (us+eu, spreads+totals) filtered by `eventIds` = 4 credits. Backup crons run the free planner first and stop unless an unstarted official item kicks within ~70 min, so they cost nothing otherwise.
- The project build cap is 1,500 credits for historical and build pulls. The build used 1,240 for 30 historical snapshots.
- `/events` and `/sports` are free. Historical endpoints cost 10 per market per region and are never called by the daily job.
- **NBA/NHL (since 2026-10-04):** `desk/pro_lines.py` makes at most one `/odds` pull per sport per CT day (us,eu × 2 markets = 4 credits), only with a game within 36h. The 9am run adds these to its reserve (`reserve_for_pro`: 4 per sport that still needs a pull), so props never eat them. The NBA/NHL build used 0 credits: history is free (ESPN, MoneyPuck, NHL API, desk-v1 copies), and the first NHL slate reused an already-paid box snapshot (Oct 4, 5:14 PM CT, DK + Bovada).
