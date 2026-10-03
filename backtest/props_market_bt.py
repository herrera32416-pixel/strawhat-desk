import sys, os, pickle, math, random, ast
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from desk.props import pname, RatioDist, poisson_p_over
from desk.market import novig
M = pickle.load(open("backtest/out/props_models.pkl", "rb"))
season, coefs, rd, test = M["res"][1]
MK = {"player_reception_yds": "receiving_yards", "player_receptions": "receptions", "player_rush_yds": "rushing_yards",
      "player_pass_yds": "passing_yards", "player_pass_tds": "passing_tds"}
L = pd.read_csv("backtest/out/props_saved_lines_flat.csv")
pairs = []
w2 = L[(L.week == 2) & L.market.isin(MK)]
for (pl, mk, ln), g in w2.groupby(["player", "market", "line"]):
    o = g[g.side == "over"]; u = g[g.side == "under"]
    if len(o) and len(u) and pd.notna(o.dk.iloc[0]) and pd.notna(u.dk.iloc[0]):
        pairs.append(dict(week=2, player=pl, market=mk, line=ln, o=int(o.dk.iloc[0]), u=int(u.dk.iloc[0]), book="draftkings"))
w3 = L[(L.week == 3) & L.market.isin(MK)]
for (pl, mk, ln, bk), g in w3.groupby(["player", "market", "line", "book"]):
    o = g[g.side == "over"]; u = g[g.side == "under"]
    if len(o) and len(u):
        pairs.append(dict(week=3, player=pl, market=mk, line=ln, o=int(o.price.iloc[0]), u=int(u.price.iloc[0]), book=bk))
P = pd.DataFrame(pairs)
P["q"] = [novig(a, b) for a, b in zip(P.o, P.u)]
P["pkey"] = P.player.map(pname)
tt = test[test.week.isin([2, 3])].copy()
tt["mk"] = tt.market
rows = []
for _, r in P.iterrows():
    m = tt[(tt.week == r.week) & (tt.pkey == r.pkey) & (tt.mk == MK[r.market])]
    if not len(m):
        continue
    m = m.iloc[0]
    if MK[r.market] == "passing_tds":
        pm = poisson_p_over(max(m.proj, 0.01), r.line)
    else:
        pm = rd.p_over(MK[r.market], m.proj, r.line)
    if pm is None:
        continue
    pm = min(max(pm, 0.02), 0.98)
    y = 1.0 if m.actual > r.line else 0.0
    rows.append(dict(r, proj=m.proj, actual=m.actual, p_model=pm, y=y))
R = pd.DataFrame(rows)
R.to_csv("backtest/out/props_market_rows.csv", index=False)
print("matched", len(R), "of", len(P), R.groupby(["week", "book"]).size().to_dict())


def bs(x): return float(np.mean(x))


def boot(u, cl, reps=2000):
    rng = random.Random(5); by = {}
    for a, c in zip(u, cl): by.setdefault(c, []).append(a)
    ks = list(by); s = []
    for _ in range(reps): s.append(sum(sum(by[rng.choice(ks)]) for _ in ks))
    s.sort(); return s[int(.05 * reps)], s[int(.95 * reps)]


out = []
for w in (0.0, 0.25, 0.5, 1.0):
    p = R.q + w * (R.p_model - R.q)
    out.append(dict(test="score", w=w, n=len(R), brier=round(bs((p - R.y) ** 2), 4), brier_market=round(bs((R.q - R.y) ** 2), 4),
                    logloss=round(bs(-(R.y * np.log(p) + (1 - R.y) * np.log(1 - p))), 4),
                    logloss_market=round(bs(-(R.y * np.log(R.q) + (1 - R.y) * np.log(1 - R.q))), 4)))
# fitted w (Brier-min) with game-cluster bootstrap
def fitw(df):
    d = df.p_model - df.q
    return float(np.clip(((df.y - df.q) * d).sum() / max((d * d).sum(), 1e-9), 0, 1))
wf = fitw(R); rng = np.random.default_rng(1); pl = R.player.unique(); ws = []
for _ in range(1000):
    s = rng.choice(pl, len(pl)); ws.append(fitw(pd.concat([R[R.player == x] for x in s[:200]])) if False else None)
# faster: resample rows by player
grp = {k: g for k, g in R.groupby("player")}
ws = []
for _ in range(1000):
    s = rng.choice(list(grp), len(grp)); ws.append(fitw(pd.concat([grp[x] for x in s])))
out.append(dict(test="fitted w (Brier-min, player-cluster bootstrap 90% CI)", w=round(wf, 3),
                ci=f"[{np.quantile(ws,.05):.3f},{np.quantile(ws,.95):.3f}]", n=len(R)))
# betting rules at the real price of that book: DK rows only for units (week 3 includes FD/BetRivers too)
for book in ("draftkings", "all"):
    B0 = R if book == "all" else R[R.book == "draftkings"]
    for w in (0.5, 1.0):
        for thr in (0.03, 0.05, 0.08):
            bets = []
            for _, r in B0.iterrows():
                p = r.q + w * (r.p_model - r.q)
                for side, pp, px, won in (("over", p, r.o, r.actual > r.line), ("under", 1 - p, r.u, r.actual < r.line)):
                    qq = r.q if side == "over" else 1 - r.q
                    if pp - qq >= thr:
                        d = px / 100 if px > 0 else 100 / -px
                        push = r.actual == r.line
                        bets.append(dict(u=0 if push else (d if won else -1), cl=r.player, side=side))
            if bets:
                u = [b["u"] for b in bets]; lo, hi = boot(u, [b["cl"] for b in bets])
                out.append(dict(test=f"bets book={book} w={w} edge>={thr}", n=len(bets), units=round(sum(u), 2),
                                roi=round(sum(u) / len(u), 3), ci=f"[{lo:.1f},{hi:.1f}]",
                                overs=sum(b['side'] == 'over' for b in bets)))
# blind unders control
for book in ("draftkings",):
    B0 = R[R.book == book]
    u = [0 if r.actual == r.line else ((r.u / 100 if r.u > 0 else 100 / -r.u) if r.actual < r.line else -1) for _, r in B0.iterrows()]
    out.append(dict(test=f"control: every under at {book}", n=len(u), units=round(sum(u), 2), roi=round(sum(u) / len(u), 3)))
O = pd.DataFrame(out); O.to_csv("backtest/out/props_market_summary.csv", index=False); print(O.to_string())
