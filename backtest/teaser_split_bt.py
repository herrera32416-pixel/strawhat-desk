"""Backtest of the day-split teaser sets (walk-forward, closing lines, band-shrunk leg %):
 NFL Sunday-only set (2015-2026) and CFB Saturday-only set (2024-2026; CFB band rates from prior seasons only).
 Uses the LIVE construction (desk.teasers.build_set). Rules since 2026-10-04: ticket #1 = spread legs only, Wong first,
 every leg >= 72.3%, 4-6 legs at +260/+400/+600 (ties reduce); PLAY = NFL and model EV > 0; CFB always PASS;
 tickets #2-5 = research (spread-only, always PASS). Rules were set from the Oct 3-4 eval BEFORE this run; no tuning.
 Writes data/teaser_backtest.json for the Teasers tab (the pre-change result is kept under "previous_rule")."""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import teasers_bt as tb
from desk.teaser_math import settle
from desk.teasers import build_set

PREVIOUS = {  # data/teaser_backtest.json as of 2026-10-03 (old rule: 6 legs always, ticket #1 NFL = top-6 spread legs,
    # CFB = top-6 spreads+totals; tickets #2-5 spreads+totals)
    "nfl": {"ticket1": {"tickets": 193, "cashed": 30, "units": 11.0, "roi": 0.057, "ci90": [-43.0, 69.0]},
            "all5": {"tickets": 965, "cashed": 121, "units": -144.0, "roi": -0.149, "ci90": [-258.0, -25.0]},
            "play": {"tickets": 159, "cashed": 26, "units": 17.0, "roi": 0.107, "ci90": [-34.0, 73.0]}},
    "cfb": {"ticket1": {"tickets": 35, "cashed": 2, "units": -21.0, "roi": -0.6, "ci90": [-35.0, -7.0]},
            "all5": {"tickets": 175, "cashed": 16, "units": -63.0, "roi": -0.36, "ci90": [-105.0, -21.0]}, "play": {"tickets": 0}}}


def conv(l):  # backtest leg -> live leg dict
    return dict(sport=l["sport"], game=l["game"], market=l["mkt"], side=l["side"], band=tb.band(l),
                p_cond=l["p_win"] / max(1 - l["p_push"], 1e-9), p_win=l["p_win"], p_push=l["p_push"], res=l["res"])


def summ(U):
    if not U:
        return dict(tickets=0)
    lo, hi = tb.boot_units(U)
    return dict(tickets=len(U), cashed=int(sum(u > 0 for u in U)), units=round(sum(U), 1), roi=round(float(np.mean(U)), 3), ci90=[round(lo, 1), round(hi, 1)])


out = {}
for sport, G, day, start in (("nfl", tb.nfl_games(), "Sunday", 2015), ("cfb", tb.cfb_games(), "Saturday", 2024)):
    L = tb.legs_for(G, sport); tb.band_adjust(L, sport)
    weeks = collections.defaultdict(list)
    for l in L:
        if l["season"] >= start and l["dow"] == day:
            weeks[l["wk"]].append(conv(l))
    rec = collections.defaultdict(list)
    sizes = collections.Counter(); legs_hit = [0, 0]
    for wk, legs in sorted(weeks.items()):
        T = build_set(legs, sport)
        for t in T:
            u = settle([l["res"] for l in t["legs"]])
            rec["all5"].append(u)
            if t["n"] == 1:
                rec["ticket1"].append(u); rec[f"ticket1_{t['n_legs']}leg"].append(u); sizes[t["n_legs"]] += 1
                for l in t["legs"]:
                    if l["res"] != "P":
                        legs_hit[0] += l["res"] == "W"; legs_hit[1] += 1
                if t["ev_per_unit"] > 0:
                    rec["ticket1_ev_pos"].append(u)
            else:
                rec["research"].append(u)
            if t["decision"] == "PLAY":
                rec["play"].append(u)
    o = {k: summ(U) for k, U in rec.items()}
    o.setdefault("play", dict(tickets=0))
    o["ticket1_sizes"] = dict(sorted(sizes.items()))
    o["ticket1_leg_win_pct_excl_push"] = round(legs_hit[0] / max(legs_hit[1], 1), 4)
    o["weeks"] = len(weeks); o["weeks_without_ticket1"] = len(weeks) - sum(sizes.values())
    o["seasons"] = f"{start}-2026"; o["day"] = day
    o["previous_rule"] = PREVIOUS[sport]
    out[sport] = o
    print(sport, json.dumps(o, indent=1))
out["_note"] = ("Closing lines (nflverse for NFL; ESPN-listed close for CFB), walk-forward KEYS pmf + band shrink fit on prior seasons. "
                "Live uses 9am DK lines, so results will differ. Rules fixed before this run (Oct 4 2026 eval); not tuned to this backtest. "
                "CFB is research only (never PLAY) regardless of the numbers.")
out["_rules"] = "spread legs only; Wong first; every leg >= 72.3%; 4-6 legs at +260/+400/+600; PLAY = NFL & EV > 0; tickets #2-5 research"
json.dump(out, open("data/teaser_backtest.json", "w"), indent=1)
