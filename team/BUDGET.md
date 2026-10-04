# BUDGET SOP (Odds API credits)
- Every call goes through `desk/toa.get`, which logs the `x-requests-last/used/remaining` headers to `data/credits.jsonl`.
- **Daily cap: 40** credits (`SH_DAILY_CAP`). A call that would exceed it is refused before it is sent.
- Typical day: NFL 6, plus NCAAF 6 on CFB days, plus props with whatever is left after the **recheck reserve**.
- Recheck reserve: on Sat (CFB) and Sun (NFL), the 9am run holds back 6 credits per recheck sport (`recheck.COST × sports`), so props get about 28 on Sunday and about 22 on Saturday. The ~11:30am CT recheck re-pulls `/odds` filtered by `eventIds` for today's unstarted games (6 credits) through the same 40/day guard.
- The project build cap is 1,500 credits for historical and build pulls. The build used 1,240 for 30 historical snapshots.
- `/events` and `/sports` are free. Historical endpoints cost 10 per market per region and are never called by the daily job.
