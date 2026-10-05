"""Does the MATCHUP layer beat the market? (2026-10-04)  Walk-forward, out-of-sample by season.

PRE-REGISTERED CRITERIA (written before the first run; also in team/MATCHUP.md). The matchup model may change
board picks ONLY if, on the pooled out-of-sample seasons 2018-2025, for the spread OR the total:
  (1) log loss vs the de-vigged closing market improves, with the 90% bootstrap CI of the improvement > 0; AND
  (2) bets with |lean| >= 1.5 pts at -110 win > 52.38% with the 90% CI lower bound above 52.38%; AND
  (3) units at -110 are positive in at least 6 of the 8 test seasons.
Otherwise the layer ships INFO ONLY. Thresholds (1.0/1.5/2.0 pts) are reported, not chosen after the fact.

Method: features (desk/matchup.py) use only games before each game's date. Target = residual vs the closing
line (result - spread_line; total - total_line). Ridge on standardized features, intercept dropped (the market
is the baseline), lambda by leave-one-season-out CV inside the training seasons only. Train on seasons < s,
test on s. Probabilities: market p = de-vigged closing odds (nflverse); model p = market p + [KEYS P(cover) at
line + lean - KEYS P(cover) at line] (KEYS pmf fit on seasons < s). Pushes excluded from Brier/LL/ATS."""
import os, sys, json, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
from desk import matchup as M
from desk.keys import Dist

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEAT = os.path.join(ROOT, "data", "matchup", "features.csv.gz")
TEST = list(range(2018, 2027))
rng = np.random.default_rng(7)


def devig(a, b):
    def imp(x):
        x = -110 if (x is None or (isinstance(x, float) and math.isnan(x))) else x
        return 100 / (x + 100) if x > 0 else -x / (-x + 100)
    pa, pb = imp(a), imp(b)
    return pa / (pa + pb)


def boot(x, n=4000):
    x = np.asarray(x, float)
    if not len(x):
        return [0, 0]
    m = [x[rng.integers(0, len(x), len(x))].mean() for _ in range(n)]
    return [float(np.percentile(m, 5)), float(np.percentile(m, 95))]


def run(kind, lam_fixed=None):
    F = pd.read_csv(FEAT)
    cols = M.SPREAD_F if kind == "spread" else M.TOTAL_F
    if kind == "spread":
        F["y"] = F.result - F.spread_line; F["line"] = F.spread_line
        F["p_mkt"] = [devig(h, a) for h, a in zip(F.home_spread_odds, F.away_spread_odds)]
        F["win"] = np.where(F.result > F.spread_line, 1, np.where(F.result < F.spread_line, 0, -1))
    else:
        F = F[F.total_line.notna()].copy()
        F["y"] = F.total - F.total_line; F["line"] = F.total_line
        F["p_mkt"] = [devig(o, u) for o, u in zip(F.over_odds, F.under_odds)]
        F["win"] = np.where(F.total > F.total_line, 1, np.where(F.total < F.total_line, 0, -1))
    F = F.dropna(subset=cols + ["y"])
    out, preds, coefs = {}, [], {}
    for s in TEST:
        tr, te = F[(F.season < s) & (F.season >= 2016)], F[F.season == s].copy()
        if not len(te):
            continue
        lam = lam_fixed or M.choose_lam(tr, cols, "y")
        mdl = M.fit_ridge(tr[cols].values, tr.y.values, lam)
        te["lean"] = M.predict(mdl, te[cols].values)
        D = Dist("nfl_margin" if kind == "spread" else "nfl_total", max_season=s - 1)
        pm = []
        for c, l, pmk in zip(te.line, te.lean, te.p_mkt):
            base, adj = D.cond_over(c, c), D.cond_over(c + l, c)
            pm.append(min(max(pmk + (adj - base), 0.01), 0.99))
        te["p_model"] = pm
        te["lam"] = lam
        preds.append(te); coefs[s] = dict(lam=lam, b=dict(zip(cols, np.round(mdl["b"], 3).tolist())))
    P = pd.concat(preds)
    if not lam_fixed:
        P.to_csv(os.path.join(ROOT, "backtest", "out", f"matchup_{kind}_preds.csv.gz"), index=False)
    res = {}
    for name, Q in (("oos_2018_2025", P[P.season <= 2025]), ("2026_to_date", P[P.season == 2026])):
        Q = Q[Q.win >= 0]
        if not len(Q):
            continue
        y = Q.win.values
        ll = lambda p: -(y * np.log(p) + (1 - y) * np.log(1 - p))
        d_ll = ll(Q.p_mkt.values) - ll(Q.p_model.values)          # > 0 = model better
        d_br = (Q.p_mkt.values - y) ** 2 - (Q.p_model.values - y) ** 2
        r = dict(n=int(len(Q)), logloss_market=round(float(ll(Q.p_mkt.values).mean()), 5), logloss_model=round(float(ll(Q.p_model.values).mean()), 5),
                 ll_improvement=round(float(d_ll.mean()), 5), ll_improvement_ci90=[round(v, 5) for v in boot(d_ll)],
                 brier_market=round(float(((Q.p_mkt.values - y) ** 2).mean()), 5), brier_model=round(float(((Q.p_model.values - y) ** 2).mean()), 5),
                 brier_improvement_ci90=[round(v, 5) for v in boot(d_br)], lean_sd=round(float(Q.lean.std()), 3))
        bets = {}
        for th in (1.0, 1.5, 2.0):
            B = P[(P.season.isin(Q.season.unique())) & (P.lean.abs() >= th)]
            side = np.sign(B.lean.values)        # +1 = home/over
            res_ = B.y.values * side
            w, l = int((res_ > 0).sum()), int((res_ < 0).sum())
            u = np.where(res_ > 0, 100 / 110, np.where(res_ < 0, -1.0, 0.0))
            wl = np.r_[np.ones(w), np.zeros(l)]
            per = {int(s): round(float(u[B.season.values == s].sum()), 2) for s in sorted(B.season.unique())}
            bets[f"lean>={th}"] = dict(bets=int(len(B)), w=w, l=l, p=int(len(B) - w - l),
                                       win_pct=round(w / max(w + l, 1), 4), win_pct_ci90=[round(v, 4) for v in boot(wl)],
                                       units=round(float(u.sum()), 2), units_ci90=[round(v * len(u), 1) for v in boot(u)],
                                       seasons_positive=f"{sum(v > 0 for v in per.values())}/{len(per)}", by_season=per)
        r["ats_at_-110" if kind == "spread" else "ou_at_-110"] = bets
        res[name] = r
    oos = res["oos_2018_2025"]; b15 = oos[("ats_at_-110" if kind == "spread" else "ou_at_-110")]["lean>=1.5"]
    sp = b15["seasons_positive"].split("/")
    crit = dict(c1_logloss_ci_above_0=oos["ll_improvement_ci90"][0] > 0,
                c2_win_ci_low_above_52_38=b15["win_pct_ci90"][0] > 0.5238,
                c3_units_positive_6_of_8=int(sp[0]) >= 6)
    res["criteria"] = crit; res["passes"] = all(crit.values()); res["coefs_by_test_season"] = coefs
    return res


if __name__ == "__main__" and "--fit-final" not in sys.argv:
    if "--rebuild" in sys.argv or not os.path.exists(FEAT):
        games = M.load_games(); tg = M.load_tg(games)
        ft = M.feature_table(games, tg, list(range(2016, 2027)))
        ft.to_csv(FEAT, index=False); print("features", len(ft))
    os.makedirs(os.path.join(ROOT, "backtest", "out"), exist_ok=True)
    R = {k: run(k) for k in ("spread", "total")}
    # Sensitivity (NOT used for the decision): light fixed shrinkage, i.e. trusting the features far more than CV does.
    R["sensitivity_lam30"] = {k: {x: v for x, v in run(k, 30)["oos_2018_2025"].items()} for k in ("spread", "total")}
    R["_criteria_text"] = __doc__.split("PRE-REGISTERED CRITERIA")[1].split("Method:")[0].strip()
    json.dump(R, open(os.path.join(ROOT, "data", "matchup", "backtest.json"), "w"), indent=1, default=float)
    for k in ("spread", "total"):
        print("==", k, json.dumps({x: R[k][x] for x in R[k] if x != "coefs_by_test_season"}, indent=1, default=float))


def fit_final():
    """Live model: same procedure on every completed season (CV lambda), plus status from the criteria."""
    R = json.load(open(os.path.join(ROOT, "data", "matchup", "backtest.json")))
    F = pd.read_csv(FEAT); out = {}
    for kind, cols in (("spread", M.SPREAD_F), ("total", M.TOTAL_F)):
        G = F.copy()
        G["y"] = (G.result - G.spread_line) if kind == "spread" else (G.total - G.total_line)
        G = G.dropna(subset=cols + ["y"])
        lam = M.choose_lam(G, cols, "y")
        out[kind] = dict(features=cols, model=M.fit_ridge(G[cols].values, G.y.values, lam), n=int(len(G)))
    passes = R["spread"]["passes"] or R["total"]["passes"]
    s, t = R["spread"]["oos_2018_2025"], R["total"]["oos_2018_2025"]
    ss, st = R["sensitivity_lam30"]["spread"]["ats_at_-110"]["lean>=1.5"], R["sensitivity_lam30"]["total"]["ou_at_-110"]["lean>=1.5"]
    out.update(status="INFLUENCES PICKS" if passes else "INFO ONLY", influence=bool(passes),
               backtest_summary=dict(
                   spread=f"OOS 2018-25, {s['n']} games: log loss {s['logloss_model']:.4f} vs market {s['logloss_market']:.4f} "
                          f"(improvement 90% CI {s['ll_improvement_ci90'][0]:+.4f}..{s['ll_improvement_ci90'][1]:+.4f}); CV shrinkage picks the "
                          f"largest penalty, leans ~{s['lean_sd']:.2f} pts, no bet ever reaches 1 pt. Lightly-shrunk version: ATS |lean|>=1.5 "
                          f"{ss['w']}-{ss['l']} ({100*ss['win_pct']:.1f}%), {ss['units']:+.1f}u at -110.",
                   total=f"OOS 2018-25, {t['n']} games: log loss {t['logloss_model']:.4f} vs market {t['logloss_market']:.4f} "
                         f"(CI {t['ll_improvement_ci90'][0]:+.4f}..{t['ll_improvement_ci90'][1]:+.4f}). Lightly-shrunk: O/U |lean|>=1.5 "
                         f"{st['w']}-{st['l']} ({100*st['win_pct']:.1f}%), {st['units']:+.1f}u.",
                   criteria=R["_criteria_text"], passes=bool(passes)))
    json.dump(out, open(M.MODEL, "w"), indent=1)
    print(out["status"], out["backtest_summary"])


if __name__ == "__main__" and "--fit-final" in sys.argv:
    fit_final()
