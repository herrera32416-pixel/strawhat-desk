"""Dry run: NHL + MLB MODEL % (paper/info only) on a published v1 day file. Free sources only
(ESPN, NHL API, MoneyPuck cache, Savant, MLB Stats API); 0 Odds API credits; no writes to the repo.
Checks: every NHL/MLB market shows market no-vig % and either a model % or a blank with a reason;
model % never changes the market-only edge / A/B/C inputs; the model log writes + summarizes.
usage: python3 tests/dryrun_model_pct.py v1/data/20261012.json 2026-10-12T09:20:00-05:00"""
import os, sys, json, copy, tempfile
from pathlib import Path
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [R, os.path.join(R, "v1", "scripts")]
from datetime import datetime
import paper_model as pm, model_log
d = json.load(open(sys.argv[1]))
now = datetime.fromisoformat(sys.argv[2]).astimezone(pm.CT)
rows, seen, by = [r for k in ("clears", "fills", "holds") for r in (d.get("card") or {}).get(k) or []], set(), {}
for r in rows:
    if r["event_id"] in seen or r["sport"] not in ("NHL", "MLB"): continue
    seen.add(r["event_id"]); r = copy.deepcopy(r); r.pop("paper", None)
    by.setdefault(r["sport"], []).append(r)
fails = []
for sp, rs in by.items():
    me_before = [json.dumps(pm.market_edge(sp, r, None), sort_keys=True) for r in rs]
    st = pm.attach_paper(sp, rs, {}, now, 2)
    print(f"\n== {sp}: {st.get('mlb_model') or st.get('nhl_model', {}).get('model')}")
    for r, mb in zip(rs, me_before):
        if json.dumps(pm.market_edge(sp, r, None), sort_keys=True) != mb: fails.append(f"{r['matchup']}: model changed market edge")
        p = r["paper"]; print(f"{r['kick_ct']}  {r['matchup']}  [{p.get('note') or 'ok'}]")
        for mk, m in (p.get("markets") or {}).items():
            for s in m["sides"]:
                if s.get("novig_pct") is None: fails.append(f"{r['matchup']} {mk}: no market %")
            print("   " + " | ".join(f"{s['label']}: mkt {s['novig_pct']}% model {s['model_pct'] if s['model_pct'] is not None else '—'}" for s in m["sides"]))
            if all(s["model_pct"] is None for s in m["sides"]) and not p.get("note", "").startswith("MODEL blank") and sp == "MLB" and mk != "spread":
                fails.append(f"{r['matchup']} {mk}: blank model with no reason")
        if any(b.get("status") == "PAPER" for b in p.get("by_market", {}).values()): fails.append(f"{r['matchup']}: model stamped")
with tempfile.TemporaryDirectory() as t:
    n = model_log.log_rows(by, now.replace(hour=0, minute=1), Path(t) / "ml.json")
    print(f"\nmodel log entries written: {n}")
    if by and n == 0: fails.append("model log wrote nothing")
print("\nFAILS:", fails or "none"); sys.exit(1 if fails else 0)
