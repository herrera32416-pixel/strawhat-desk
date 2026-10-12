"""Dry run: market-only edges + A/B/C on a published v1 day file (row best-of-posted-books prices; no API calls, no writes).
usage: python3 tests/dryrun_market_edge.py v1/data/20261012.json 2026-10-12T11:00:00-05:00"""
import os, sys, json, copy
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [R, os.path.join(R, "v1", "scripts")]
from datetime import datetime
import paper_model as pm
d = json.load(open(sys.argv[1]))
now = datetime.fromisoformat(sys.argv[2]).astimezone(pm.CT)
rows, seen, by = [r for k in ("clears", "fills", "holds") for r in (d.get("card") or {}).get(k) or []], set(), {}
for r in rows:
    if r["event_id"] in seen: continue
    seen.add(r["event_id"]); r = copy.deepcopy(r); r.setdefault("paper", {})
    r["market_edge"] = r.get("market_edge") or pm.market_edge(r["sport"], r, None)
    by.setdefault(r["sport"], []).append(r)
led = {"picks": []}
new = pm.stamp_today(led, by, now)
for r in [x for v in by.values() for x in v if pm.kick_ct(x["kick_utc"]).date() == now.date()]:
    print(f"\n{r['sport']} {r['kick_ct']} {r['matchup']}")
    for mk, m in r["market_edge"].items():
        b = m.get("best")
        print(f"  {mk:6} " + (f"{b['selection']:28} {b['price_american']:+5d} {b['book']:22} no-vig {b['novig_pct']}% edge {b['edge_pp']:+.1f}pp grade {m.get('grade','-')} {('; '.join(m.get('grade_reasons') or []))}" if b else m["note"]))
print("\nSTAMPED:", [(p["grade"], p["selection"], p["price_american"], p["book"], p["edge_pp"]) for p in new])
