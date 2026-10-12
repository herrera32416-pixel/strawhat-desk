"""Dry run: grade a published v1 board file A/B/C without writing anything.
usage: python3 tests/dryrun_grades.py v1/data/20261011.json [now_iso]"""
import os, sys, json, copy
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [R, os.path.join(R, "v1", "scripts")]
from datetime import datetime
import paper_model as pm
d = json.load(open(sys.argv[1]))
rows = [r for k in ("clears", "fills", "holds") for r in (d.get("card") or {}).get(k) or []]
seen, rows_by = set(), {}
for r in rows:
    if r["event_id"] in seen or not r.get("paper"):
        continue
    seen.add(r["event_id"]); rows_by.setdefault(r["sport"], []).append(copy.deepcopy(r))
now = datetime.fromisoformat(sys.argv[2]).astimezone(pm.CT) if len(sys.argv) > 2 else datetime.now(pm.CT)
led = {"picks": []}
new = pm.stamp_today(led, rows_by, now)
for g in "ABC":
    xs = [p for p in new if p["grade"] == g]
    print(f"--- {g}: {len(xs)}")
    for p in sorted(xs, key=lambda p: -(p["edge_pp"] or 0)):
        print(f"  {p['sport']:4} {p['kick_ct'] or ''} {p['matchup']}: {p['selection']} {p['price_american']} "
              f"edge {p['edge_pp']} model {p['model_pct']} | {'; '.join(p['grade_reasons']) or 'all rules pass'}")
pm.summarize(led, now)
print("by_grade:", {k: v["record"] + f" open {v['open']}" for k, v in led["summary"]["by_grade"].items()})
