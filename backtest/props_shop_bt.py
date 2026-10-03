"""Props SHOPPER test: DK (and Bovada when present) price vs no-vig consensus of the OTHER books at the same line."""
import sys, os, ast, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from desk.market import novig
R = pd.read_csv("backtest/out/props_market_rows.csv")  # has actual + p_model for matched (week, player, market, line, book)
L = pd.read_csv("backtest/out/props_saved_lines_flat.csv")
act = {(r.week, r.player, r.market, r.line): (r.actual, r.p_model) for r in R.itertuples()}
rows = []
w2 = L[(L.week == 2) & L.side.isin(["over", "under"])]
for (pl, mk, ln), g in w2.groupby(["player", "market", "line"]):
    o = g[g.side == "over"]; u = g[g.side == "under"]
    if not (len(o) and len(u)): continue
    oo = ast.literal_eval(o.other.iloc[0]) if isinstance(o.other.iloc[0], str) else {}
    uu = ast.literal_eval(u.other.iloc[0]) if isinstance(u.other.iloc[0], str) else {}
    if pd.notna(o.fd.iloc[0]) and pd.notna(u.fd.iloc[0]):
        oo["FanDuel"] = o.fd.iloc[0]; uu["FanDuel"] = u.fd.iloc[0]
    tgt = {"draftkings": (o.dk.iloc[0], u.dk.iloc[0]), "bovada": (oo.pop("Bovada", None), uu.pop("Bovada", None))}
    refs = [novig(oo[b], uu[b]) for b in oo if b in uu]
    if len(refs) < 2: continue
    rows.append(dict(week=2, player=pl, market=mk, line=ln, fair=float(np.median(refs)), nref=len(refs), tgt=tgt))
w3 = L[L.week == 3]
for (pl, mk, ln), g in w3.groupby(["player", "market", "line"]):
    px = {}
    for bk, gg in g.groupby("book"):
        o = gg[gg.side == "over"]; u = gg[gg.side == "under"]
        if len(o) and len(u): px[bk] = (o.price.iloc[0], u.price.iloc[0])
    if "draftkings" not in px: continue
    refs = [novig(*v) for b, v in px.items() if b != "draftkings"]
    if not refs: continue
    rows.append(dict(week=3, player=pl, market=mk, line=ln, fair=float(np.median(refs)), nref=len(refs), tgt={"draftkings": px["draftkings"]}))
bets = []
for r in rows:
    a = act.get((r["week"], r["player"], r["market"], r["line"]))
    if a is None: continue
    actual, pm = a
    for bk, (po, pu) in r["tgt"].items():
        if po is None or pu is None or pd.isna(po) or pd.isna(pu): continue
        for side, pfair, px, won in (("over", r["fair"], po, actual > r["line"]), ("under", 1 - r["fair"], pu, actual < r["line"])):
            d = px / 100 if px > 0 else 100 / -px
            ev = pfair * d - (1 - pfair)
            bets.append(dict(week=r["week"], player=r["player"], market=r["market"], book=bk, side=side, ev=ev, nref=r["nref"],
                             model_agrees=(pm > r["fair"]) == (side == "over"),
                             u=0 if actual == r["line"] else (d if won else -1)))
B = pd.DataFrame(bets)
def boot(u, cl, reps=2000):
    rng = random.Random(9); by = {}
    for a, c in zip(u, cl): by.setdefault(c, []).append(a)
    ks = list(by); s = sorted(sum(sum(by[rng.choice(ks)]) for _ in ks) for _ in range(reps)); return s[int(.05*reps)], s[int(.95*reps)]
out = []
for thr in (0.0, 0.02, 0.04):
    for agree in (None, True):
        S = B[(B.ev >= thr)]
        if agree: S = S[S.model_agrees]
        # one bet per prop-side: best book
        S = S.sort_values("ev", ascending=False).drop_duplicates(["week", "player", "market", "side"])
        if len(S) == 0: continue
        lo, hi = boot(list(S.u), list(S.player))
        out.append(dict(rule=f"EV>={thr}" + (" & model agrees" if agree else ""), n=len(S), units=round(S.u.sum(), 2),
                        roi=round(S.u.mean(), 3), ci90=f"[{lo:.1f},{hi:.1f}]", mean_ev=round(S.ev.mean(), 4),
                        overs=int((S.side == 'over').sum())))
O = pd.DataFrame(out); print("props with consensus fair:", len(rows)); print(O.to_string())
O.to_csv("backtest/out/props_shop_summary.csv", index=False)
