"""Robustness of the ticket-#1 teaser rule: split periods, raw vs band-shrunk, and top-k legs."""
import sys, os, collections, copy
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import teasers_bt as tb
from desk.teaser_math import settle
L = tb.legs_for(tb.nfl_games(), "nfl")
raw = copy.deepcopy(L)
tb.band_adjust(L, "nfl")
def run(legs, seasons, label, spreads_only=True):
    weeks = collections.defaultdict(list)
    for l in legs:
        if l["season"] in seasons and (l["mkt"] == "spread" or not spreads_only):
            weeks[l["wk"]].append(l)
    U = []
    for wk, ls in weeks.items():
        T = tb.build_week(ls, 1, 1)
        for tk in T: U.append(settle([l["res"] for l in tk]))
    lo, hi = tb.boot_units(U) if U else (0, 0)
    print(f"{label:55s} n={len(U):3d} won={sum(u>0 for u in U):3d} units={sum(U):+7.1f} roi={np.mean(U):+.3f} 90%CI [{lo:.0f},{hi:.0f}]")
for nm, legs in (("band-shrunk (live)", L), ("raw KEYS only", raw)):
    run(legs, range(2015, 2021), f"{nm} 2015-2020")
    run(legs, range(2021, 2027), f"{nm} 2021-2026")
    run(legs, range(2015, 2027), f"{nm} 2015-2026")
    run(legs, range(2015, 2027), f"{nm} 2015-2026 spreads+totals", spreads_only=False)
