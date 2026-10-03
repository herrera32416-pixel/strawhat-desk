# BUDGET SOP (Odds API credits)
- Every call goes through `desk/toa.get`, which logs the `x-requests-last/used/remaining` headers to `data/credits.jsonl`.
- **Daily cap: 40** credits (`SH_DAILY_CAP`). A call that would exceed it is refused before it is sent.
- Typical day: NFL 6, plus NCAAF 6 on CFB days, plus props with whatever is left (up to about 28 on a Saturday or Sunday).
- The project build cap is 1,500 credits for historical and build pulls. The build used 1,240 for 30 historical snapshots.
- `/events` and `/sports` are free. Historical endpoints cost 10 per market per region and are never called by the daily job.
