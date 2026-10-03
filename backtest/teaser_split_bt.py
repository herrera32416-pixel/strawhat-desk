"""Backtest of the day-split teaser sets (walk-forward, closing lines, band-shrunk leg %):
 NFL Sunday-only set (2015-2026) and CFB Saturday-only set (2024-2026; CFB band rates from prior seasons only).
 Same construction as live: ticket #1, then greedy tickets #2-5 with each leg used <=2x; PLAY = model EV > 0.
 Writes data/teaser_backtest.json for the Teasers tab."""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import teasers_bt as tb
from desk.teaser_math import settle, ticket_prob
from desk.teasers import build_set


def conv(l):  # backtest leg -> live leg dict
    return dict(sport=l["sport"], game=l["game"], market=l["mkt"], side=l["side"], p_cond=l["p_win"] / max(1 - l["p_push"], 1e-9),
                p_win=l["p_win"], p_push=l["p_push"], res=l["res"])


out = {}
for sport, G, day, start in (("nfl", tb.nfl_games(), "Sunday", 2015), ("cfb", tb.cfb_games(), "Saturday", 2024)):
    L = tb.legs_for(G, sport); tb.band_adjust(L, sport)
    weeks = collections.defaultdict(list)
    for l in L:
        if l["season"] >= start and l["dow"] == day:
            weeks[l["wk"]].append(conv(l))
    rec = {k: [] for k in ("ticket1", "all5", "play")}
    for wk, legs in sorted(weeks.items()):
        T = build_set(legs, sport)
        for t in T:
            u = settle([l["res"] for l in t["legs"]])
            rec["all5"].append(u)
            if t["n"] == 1: rec["ticket1"].append(u)
            if t["ev_per_unit"] > 0: rec["play"].append(u)
    o = {}
    for k, U in rec.items():
        if U:
            lo, hi = tb.boot_units(U)
            o[k] = dict(tickets=len(U), cashed=int(sum(u > 0 for u in U)), units=round(sum(U), 1), roi=round(float(np.mean(U)), 3), ci90=[round(lo, 1), round(hi, 1)])
        else:
            o[k] = dict(tickets=0)
    o["weeks"] = len(weeks); o["seasons"] = f"{start}-2026"; o["day"] = day
    out[sport] = o
    print(sport, json.dumps(o))
out["_note"] = "Closing lines (nflverse for NFL; ESPN-listed close for CFB), walk-forward KEYS pmf + band shrink fit on prior seasons. Live uses 9am DK lines, so results will differ."
json.dump(out, open("data/teaser_backtest.json", "w"), indent=1)
