"""One-time historical pulls (Odds API historical endpoint, 10 credits/market/region).
Snapshot = 9:00am CT on game day, regions us+eu (DK, Bovada, Pinnacle + ~20 books), spreads+totals."""
import sys, os, json, gzip, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from desk import toa
SNAPS = {
 "americanfootball_nfl": ["2025-09-07T14","2025-09-21T14","2025-09-28T14","2025-10-05T14","2025-10-12T14",
   "2025-10-19T14","2025-10-26T14","2025-11-02T15","2025-11-09T15","2025-11-16T15","2025-11-23T15","2025-11-30T15",
   "2025-12-07T15","2025-12-14T15","2025-12-21T15","2025-12-28T15","2026-01-04T15",
   "2026-09-13T14","2026-09-20T14","2026-09-27T14"],
 "americanfootball_ncaaf": ["2025-09-06T14","2025-09-20T14","2025-10-04T14","2025-10-18T14","2025-11-08T15","2025-11-22T15",
   "2026-09-05T14","2026-09-12T14","2026-09-19T14","2026-09-26T14"],
}
for sport, snaps in SNAPS.items():
    tag = "nfl" if sport.endswith("nfl") else "cfb"
    for s in snaps:
        out = f"data/raw/hist/{tag}_{s}.json.gz"
        if os.path.exists(out):
            continue
        d, row = toa.get(f"/v4/historical/sports/{sport}/odds", {"date": s + ":00:00Z", "regions": "us,eu",
                         "markets": "spreads,totals", "oddsFormat": "american"}, 40, f"hist {tag} {s}", kind="build")
        json.dump(d, gzip.open(out, "wt"))
        print(s, len(d["data"]), row["last"], row["remaining"], flush=True)
        time.sleep(0.5)
