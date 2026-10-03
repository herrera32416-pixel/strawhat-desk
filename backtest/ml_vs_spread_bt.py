"""Does the KEYS spread->ML conversion price moneylines better than the ML market itself?
nflverse closing spread (+prices) and closing ML, 2012-2025 REG+POST, walk-forward (pmf fit on prior seasons)."""
import sys, os, csv, math, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from desk.keys import Dist
from desk.market import novig
rows = []; D = {}
for r in csv.DictReader(open("data/history/nfl_games.csv")):
    try:
        s = int(r["season"]); sp = float(r["spread_line"]); res = float(r["result"])
        hm, am = float(r["home_moneyline"]), float(r["away_moneyline"]); hs, as_ = float(r["home_spread_odds"]), float(r["away_spread_odds"])
    except ValueError:
        continue
    if s < 2012 or res == 0:
        continue
    if s not in D: D[s] = Dist("nfl_margin", max_season=s - 1)
    c = D[s].anchor(sp, novig(hs, as_))
    w, pu, l = D[s].probs(c, 0)
    p_keys = w + pu / 2
    q_ml = novig(hm, am)
    y = 1.0 if res > 0 else 0.0
    rows.append(dict(season=s, p_keys=p_keys, q_ml=q_ml, y=y, hm=hm, am=am))
P = np.array([r["p_keys"] for r in rows]); Q = np.array([r["q_ml"] for r in rows]); Y = np.array([r["y"] for r in rows])
bk, bq = ((P - Y) ** 2).mean(), ((Q - Y) ** 2).mean()
rng = np.random.default_rng(0); d = (P - Y) ** 2 - (Q - Y) ** 2
bs = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(2000)]
print(f"n={len(rows)} Brier keys(spread->ML) {bk:.4f} vs ML no-vig {bq:.4f}; diff 90% CI [{np.quantile(bs,.05):.4f},{np.quantile(bs,.95):.4f}]")
print("mean |p_keys - q_ml| = %.4f" % np.abs(P - Q).mean())
for thr in (0.01, 0.02, 0.03):
    u = []
    for r in rows:
        for side, p, px, won in (("h", r["p_keys"], r["hm"], r["y"] == 1), ("a", 1 - r["p_keys"], r["am"], r["y"] == 0)):
            dd = px / 100 if px > 0 else 100 / -px
            if p * dd - (1 - p) >= thr and -300 <= px <= 300:
                u.append(dd if won else -1.0)
    if u:
        bb = sorted((lambda g: sum(g.choice(u) for _ in u))(random.Random(i)) for i in range(500))
        print(f"EV>={thr}: n={len(u)} units {sum(u):+.1f} roi {np.mean(u):+.3f} 90% CI [{bb[25]:.1f},{bb[475]:.1f}]")
