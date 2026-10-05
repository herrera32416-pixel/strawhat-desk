"""NFL margin pmf: np.roll (old) vs exponential tilt (new). Pre-registration: research/PREREG_KEYS_NFL_TILT.md."""
import os, sys, json, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
from desk.keys import Dist

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rng = np.random.default_rng(5)
D_OFF = [x for x in np.arange(-7, 7.5, 0.5) if x != 0]
BANDS = [(-99, -10.5), (-10, -7), (-6.5, -3.5), (-3, 0), (0.5, 3), (3.5, 5), (5.5, 8.5), (9, 99)]


def devig(a, b):
    imp = lambda x: 0.5238 if (x is None or math.isnan(x)) else (100 / (x + 100) if x > 0 else -x / (-x + 100))
    pa, pb = imp(a), imp(b)
    return pa / (pa + pb)


def boot(g, v, n=3000):
    """game-clustered bootstrap of the mean of v."""
    df = pd.DataFrame(dict(g=g, v=v)).groupby("g").v.agg(["sum", "count"])
    s, c = df["sum"].values, df["count"].values
    m = []
    for _ in range(n):
        i = rng.integers(0, len(s), len(s)); m.append(s[i].sum() / c[i].sum())
    return [round(float(np.percentile(m, 5)), 6), round(float(np.percentile(m, 95)), 6)]


def main():
    G = pd.read_csv(os.path.join(ROOT, "data", "history", "nfl_games.csv"), low_memory=False)
    G = G[(G.season >= 2015) & (G.season <= 2025) & G.result.notna() & G.spread_line.notna()]
    rows, anch, exact = [], [], []
    for s, gs in G.groupby("season"):
        old, new = Dist("nfl_margin", max_season=s - 1, tilt=False), Dist("nfl_margin", max_season=s - 1, tilt=True)
        for _, g in gs.iterrows():
            q = devig(g.home_spread_odds, g.away_spread_odds)
            L = g.spread_line                     # expected home margin; home covers if result > L
            home_line = -L
            for nm, D in (("old", old), ("new", new)):
                c = D.anchor(L, q)
                anch.append(dict(m=nm, err=abs(D.cond_over(c, L) - q)))
                p = D.pmf(c)
                exact.append(dict(m=nm, ll=math.log(max(float(p[D.grid == g.result].sum()), 1e-9))))
                for d in D_OFF:
                    t = L + d
                    w, pu, l = D.probs(c, t)
                    if float(t).is_integer():
                        rows.append(dict(game=g.game_id, season=s, home_line=home_line, d=d, m=nm, kind="push", pred=pu, y=float(g.result == t)))
                    if g.result == t:
                        continue
                    pw = w / max(w + l, 1e-12)
                    pw = min(max(pw, 1e-6), 1 - 1e-6); y = float(g.result > t)
                    rows.append(dict(game=g.game_id, season=s, home_line=home_line, d=d, m=nm, kind="cover", pred=pw, y=y,
                                     ll=-(y * math.log(pw) + (1 - y) * math.log(1 - pw))))
    R = pd.DataFrame(rows)
    C = R[R.kind == "cover"]
    o, n = C[C.m == "old"].reset_index(drop=True), C[C.m == "new"].reset_index(drop=True)
    assert (o.game.values == n.game.values).all() and (o.d.values == n.d.values).all()
    imp = o.ll.values - n.ll.values
    out = {"n_games": int(G.shape[0]), "n_events": int(len(o)),
           "logloss_old": round(float(o.ll.mean()), 6), "logloss_new": round(float(n.ll.mean()), 6),
           "improvement": round(float(imp.mean()), 6), "improvement_ci90": boot(o.game.values, imp)}
    bands = {}
    for lo, hi in BANDS:
        mk = (o.home_line >= lo) & (o.home_line <= hi)
        if mk.sum() == 0:
            continue
        bands[f"{lo:+g}..{hi:+g}"] = dict(n_games=int(o.game[mk].nunique()), old=round(float(o.ll[mk].mean()), 6), new=round(float(n.ll[mk].mean()), 6),
                                          improvement=round(float(imp[mk].mean()), 6), ci90=boot(o.game[mk].values, imp[mk.values]))
    out["bands"] = bands
    calib = {}
    for nm, X in (("old", o), ("new", n)):
        calib[nm] = dict(cover_abs_err=round(abs(float(X.pred.mean() - X.y.mean())), 5),
                         cover_bins_ece=round(float(np.average(np.abs(X.groupby(pd.cut(X.pred, np.linspace(0, 1, 21))).apply(lambda z: z.pred.mean() - z.y.mean()).fillna(0)),
                                                                weights=X.groupby(pd.cut(X.pred, np.linspace(0, 1, 21))).size())), 5))
        P = R[(R.kind == "push") & (R.m == nm)]
        calib[nm]["push_pred"] = round(float(P.pred.mean()), 5); calib[nm]["push_actual"] = round(float(P.y.mean()), 5)
        calib[nm]["push_abs_err"] = round(abs(float(P.pred.mean() - P.y.mean())), 5)
    out["calibration"] = calib
    A = pd.DataFrame(anch); E = pd.DataFrame(exact)
    out["anchor_within_0.5pp"] = {nm: round(float((A[A.m == nm].err <= 0.005).mean()), 4) for nm in ("old", "new")}
    out["exact_margin_loglik"] = {nm: round(float(E[E.m == nm].ll.mean()), 5) for nm in ("old", "new")}
    rf = bands.get("+5.5..+8.5", {})
    crit = {
        "c1_pooled_ll_ci_above_0": out["improvement_ci90"][0] > 0,
        "c2_road_fav_band_improves": rf.get("improvement", -1) > 0,
        "c3_no_band_hurt": all(b["improvement"] >= -0.0005 and b["ci90"][1] > 0 for b in bands.values()),
        "c4_calibration_not_worse": calib["new"]["cover_abs_err"] <= calib["old"]["cover_abs_err"] + 0.002
                                     and calib["new"]["push_abs_err"] <= calib["old"]["push_abs_err"] + 0.002,
        "c5_anchor_fidelity_99pct": out["anchor_within_0.5pp"]["new"] >= 0.99}
    out["criteria"] = crit; out["passes"] = all(crit.values())
    json.dump(out, open(os.path.join(ROOT, "data", "keys_nfl_tilt_bt.json"), "w"), indent=1, default=float)
    print(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
