"""Fit the live PROPS model artifacts on all data to date (2023 wk5 .. latest) -> data/props_model.json.
Stores team-volume OLS coefs and 201 quantiles of actual/projection ratios per market x projection tercile."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import importlib.util
from desk.props import *
games = pd.read_csv("data/history/nfl_games.csv", low_memory=False)
d = load_stats([2023, 2024, 2025, 2026]); t = team_table(d, games); pf = player_features(d, t)
league = {c: float(t[c].mean()) for c in ["ypt", "ypc", "ypa", "cr", "tds"]}
coefs = fit_volume(t)
rows = proj_rows(pf, t, coefs, pf.order >= 202305, league)
art = {"fit_through": int(d.order.max()), "coefs": {k: list(map(float, v)) for k, v in coefs.items()}, "league": league, "ratio": {}}
for m, g in rows.groupby("market"):
    g = g[g.proj > 0.05]
    qs = np.quantile(g.proj, [1 / 3, 2 / 3])
    bins = []
    for lo, hi in ((-1, qs[0]), (qs[0], qs[1]), (qs[1], 1e9)):
        r = (g[(g.proj > lo) & (g.proj <= hi)].actual / g[(g.proj > lo) & (g.proj <= hi)].proj).values
        bins.append(list(map(lambda x: round(float(x), 4), np.quantile(r, np.linspace(0, 1, 401)))))
    art["ratio"][m] = {"cuts": list(map(float, qs)), "q": bins, "n": int(len(g))}
json.dump(art, open("data/props_model.json", "w"))
print("saved", {m: v["n"] for m, v in art["ratio"].items()}, art["coefs"])
