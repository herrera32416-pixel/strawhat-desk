"""NHL matchup layer vs the closing line: pre-registered test (research/PREREG_NBA_NHL.md).

python backtest/nhl_bt.py            # builds features (walk-forward), runs OOS 2022-23..2025-26, writes
                                     # backtest/out/nhl_bt.json, backtest/out/nhl_preds.csv.gz, data/nhl/model.json
Market = ESPN-listed pregame close (DraftKings / ESPN BET), de-vigged. Units at the recorded close price, 1u flat."""
import json, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from desk import nhl_match as nm, nhl_sim, pro_ratings as pr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "backtest", "out")
TEST = [2022, 2023, 2024, 2025]


def load_lines():
    L = pd.read_csv(os.path.join(nm.D, "lines.csv"))
    L = L[L.season.between(2021, 2025) & L.ml_home.notna() & L.ml_away.notna() & L.home_score.notna()].copy()
    med = L.groupby("season").total.median()
    L["total_fill"] = L.season.map(lambda s: med.get(s - 1, med.get(s, 6.0)))
    return L.reset_index(drop=True)


def fit_P(L):
    P = {}
    for s in sorted(L.season.unique()):
        tr = L[(L.season < s) & L.total.notna() & L.over_price.notna()] if s > 2021 else L[(L.season == 2021) & L.total.notna() & L.over_price.notna()]
        ph = np.array([pr.novig(a, b) for a, b in zip(tr.ml_home, tr.ml_away)])
        qo = np.array([pr.novig(o, u) for o, u in zip(tr.over_price, tr.under_price)])
        P[int(s)] = nhl_sim.fit_params(ph, tr.total.to_numpy(float), qo, tr.home_score.to_numpy(), tr.away_score.to_numpy(), tr.result_type.to_numpy())
        print("sim params for", s, "fit on", "<" + str(s) if s > 2021 else "2021 (training-only season)", P[int(s)], flush=True)
    return P


def features():
    T = nm.load_team_games()
    GL = pd.read_csv(os.path.join(nm.D, "goalies.csv.gz"))
    GR, _ = nm.goalie_ratings(T, GL)
    GR = GR.merge(GL[["gameId", "date"]].drop_duplicates("gameId"), on="gameId")
    L = load_lines()
    P = fit_P(L)
    g, R = nm.build(T, L, P, GR)
    return g, P


def ll(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def evaluate(g, col_model, col_mkt, y, price_yes, price_no, mask, edge=0.03):
    d = g[mask].copy()
    yy = y[mask]
    lm, lk = ll(d[col_model].to_numpy(), yy), ll(d[col_mkt].to_numpy(), yy)
    imp = lk - lm
    ci = pr.boot_ci(imp, d.date)
    # bets: edge >= 3pp vs de-vigged market, at the recorded price of that side
    e = d[col_model] - d[col_mkt]
    side_yes = e >= edge; side_no = e <= -edge
    pay = np.where(side_yes, np.where(yy == 1, [pr.payout(a) for a in d[price_yes]], -1.0),
                   np.where(side_no, np.where(yy == 0, [pr.payout(a) for a in d[price_no]], -1.0), 0.0))
    bet = side_yes | side_no
    units = pay[bet]
    roi_ci = pr.boot_ci(units, d.date[bet]) if bet.sum() > 5 else (None, None)
    by = d.assign(u=pay, b=bet).groupby("season").apply(lambda x: pd.Series(dict(n=int(x.b.sum()), units=float(x.u.sum()),
          ll_model=float(ll(x[col_model].to_numpy(), yy[x.index.map(lambda i: d.index.get_loc(i))]).mean()) if False else None)))
    seasons = {int(s): dict(bets=int(x.b.sum()), units=round(float(x.u.sum()), 2)) for s, x in d.assign(u=pay, b=bet).groupby("season")}
    pos = sum(1 for v in seasons.values() if v["units"] > 0)
    return dict(n=int(len(d)), ll_model=round(float(lm.mean()), 5), ll_market=round(float(lk.mean()), 5),
                ll_improve=round(float(imp.mean()), 5), ll_improve_ci90=[round(ci[0], 5), round(ci[1], 5)],
                bets=int(bet.sum()), wins=int(((pay > 0) & bet).sum()), units=round(float(units.sum()), 2),
                roi=round(float(units.mean()), 4) if bet.sum() else None,
                roi_ci90=[round(x, 4) if x is not None else None for x in roi_ci], by_season=seasons, seasons_positive=pos)


def main():
    g, P = features()
    g = g[g.season.between(2021, 2025)].reset_index(drop=True)
    g.to_csv(os.path.join(OUT, "nhl_features.csv.gz"), index=False)
    F, FT = nm.F_DIFF, nm.F_TOT
    g["lean_d"] = 0.0; g["lean_t"] = 0.0
    lams = {}
    for s in TEST:
        tr = g[(g.season < s)].dropna(subset=["resid_d"])
        te = g.season == s
        Xd = tr[F].fillna(0).to_numpy(float)
        b, mu, sd, lam = pr.ridge_cv(Xd, tr.resid_d.to_numpy(float), tr.season.to_numpy())
        g.loc[te, "lean_d"] = ((g.loc[te, F].fillna(0).to_numpy(float) - mu) / sd) @ b
        trt = tr[tr.has_total.astype(bool)]
        bt, mut, sdt, lamt = pr.ridge_cv(trt[FT].fillna(0).to_numpy(float), trt.resid_t.to_numpy(float), trt.season.to_numpy())
        g.loc[te, "lean_t"] = ((g.loc[te, FT].fillna(0).to_numpy(float) - mut) / sdt) @ bt
        lams[s] = dict(diff=lam, total=lamt, coef_diff=dict(zip(F, np.round(b, 4).tolist())), coef_total=dict(zip(FT, np.round(bt, 4).tolist())))
        print(s, "lambda diff", lam, "total", lamt, "lean_d sd", round(float(g.loc[te, "lean_d"].std()), 4), flush=True)
    t = g[g.season.isin(TEST)].copy()
    # adjusted sim: shift expected goals by the shrunk leans
    lh = np.clip(t.lam_h + t.lean_t / 2 + t.lean_d / 2, 0.3, None); la = np.clip(t.lam_a + t.lean_t / 2 - t.lean_d / 2, 0.3, None)
    res = {}
    for s in TEST:
        idx = t.season == s
        Fm = nhl_sim.final_joint(lh[idx].to_numpy(), la[idx].to_numpy(), P[s])
        F0 = nhl_sim.final_joint(t.lam_h[idx].to_numpy(), t.lam_a[idx].to_numpy(), P[s])
        tl = t.loc[idx, "total"].fillna(6.0).to_numpy(float)
        for nm_, FF in (("m", Fm), ("0", F0)):
            pp = nhl_sim.probs(FF, total=tl)
            f = FF.reshape(len(FF), -1)
            sp = t.loc[idx, "spread_home"].fillna(-1.5).to_numpy(float)
            t.loc[idx, "p_ml_" + nm_] = pp["p_home"]
            t.loc[idx, "p_pl_" + nm_] = (f * ((nhl_sim.MARG[None, :] + sp[:, None]) > 0)).sum(1)
            t.loc[idx, "p_ov_" + nm_] = pp["p_over"]
    hw = (t.home_score > t.away_score).astype(int).to_numpy()
    t["mkt_pl"] = [pr.novig(a, b) if pd.notna(a) and pd.notna(b) else np.nan for a, b in zip(t.sp_price_home, t.sp_price_away)]
    t["mkt_ov"] = [pr.novig(a, b) if pd.notna(a) and pd.notna(b) else np.nan for a, b in zip(t.over_price, t.under_price)]
    plc = ((t.home_score - t.away_score + t.spread_home) > 0).astype(int).to_numpy()
    tot = t.home_score + t.away_score
    ov = (tot > t.total).astype(int).to_numpy()
    m_ml = np.ones(len(t), bool)
    m_pl = t.mkt_pl.notna().to_numpy() & t.spread_home.abs().eq(1.5).to_numpy()
    m_ov = t.mkt_ov.notna().to_numpy() & (tot != t.total).to_numpy() & t.has_total.astype(bool).to_numpy()
    res["ml"] = evaluate(t, "p_ml_m", "p_mkt", hw, "ml_home", "ml_away", m_ml)
    res["puck_line"] = evaluate(t, "p_pl_m", "mkt_pl", plc, "sp_price_home", "sp_price_away", m_pl)
    res["total"] = evaluate(t, "p_ov_m", "mkt_ov", ov, "over_price", "under_price", m_ov)
    # calibration of the market-only sim (derived puck line vs the market's own puck line)
    res["calib_market_only_sim"] = dict(
        puck_line=evaluate(t, "p_pl_0", "mkt_pl", plc, "sp_price_home", "sp_price_away", m_pl),
        ml_check_ll=round(float(ll(t.p_ml_0.to_numpy(), hw).mean()), 5), ml_market_ll=round(float(ll(t.p_mkt.to_numpy(), hw).mean()), 5))
    def verdict(r, need_pos):
        c1 = r["ll_improve_ci90"][0] > 0
        c2 = r["bets"] >= 100 and r["roi_ci90"][0] is not None and r["roi_ci90"][0] > 0
        c3 = r["seasons_positive"] >= need_pos
        return dict(c1_ll_ci_gt0=bool(c1), c2_bets_roi_ci_gt0=bool(c2), c3_seasons=bool(c3), passed=bool(c1 and c2 and c3))
    res["verdict"] = {"ml": verdict(res["ml"], 3), "puck_line": verdict(res["puck_line"], 3), "total": verdict(res["total"], 2)}
    res["influence"] = any(v["passed"] for v in res["verdict"].values())
    res["lean_sd"] = dict(diff=round(float(t.lean_d.std()), 4), total=round(float(t.lean_t.std()), 4))
    res["lambdas"] = {str(k): v for k, v in lams.items()}
    res["sim_params"] = {str(k): v for k, v in P.items()}
    res["coverage"] = {str(int(s)): dict(games=int((g.season == s).sum()), with_total=int(g[(g.season == s)].has_total.sum()),
                                          with_goalie=int(g[(g.season == s)].g_h.notna().sum())) for s in sorted(g.season.unique())}
    t[["date", "season", "home", "away", "home_score", "away_score", "result_type", "ml_home", "ml_away", "spread_home", "total", "p_mkt", "p_ml_0", "p_ml_m",
       "mkt_pl", "p_pl_0", "p_pl_m", "mkt_ov", "p_ov_0", "p_ov_m", "lean_d", "lean_t"]].to_csv(os.path.join(OUT, "nhl_preds.csv.gz"), index=False)
    json.dump(res, open(os.path.join(OUT, "nhl_bt.json"), "w"), indent=1, default=float)
    # final live model: train on all lined seasons <= 2025
    tr = g.dropna(subset=["resid_d"])
    b, mu, sd, lam = pr.ridge_cv(tr[F].fillna(0).to_numpy(float), tr.resid_d.to_numpy(float), tr.season.to_numpy())
    trt = tr[tr.has_total.astype(bool)]
    bt, mut, sdt, lamt = pr.ridge_cv(trt[FT].fillna(0).to_numpy(float), trt.resid_t.to_numpy(float), trt.season.to_numpy())
    Lall = load_lines()
    Pl = nhl_sim.fit_params(*[np.array(x) for x in (
        [pr.novig(a, b_) for a, b_ in zip(Lall.dropna(subset=["total", "over_price"]).ml_home, Lall.dropna(subset=["total", "over_price"]).ml_away)],
        Lall.dropna(subset=["total", "over_price"]).total, [pr.novig(o, u) for o, u in zip(Lall.dropna(subset=["total", "over_price"]).over_price, Lall.dropna(subset=["total", "over_price"]).under_price)],
        Lall.dropna(subset=["total", "over_price"]).home_score, Lall.dropna(subset=["total", "over_price"]).away_score, Lall.dropna(subset=["total", "over_price"]).result_type)])
    model = dict(influence=bool(res["influence"]), status="INFO ONLY" if not res["influence"] else "PASSED - needs Luis review",
                 diff=dict(features=F, beta=b.tolist(), mean=mu.tolist(), sd=sd.tolist(), lam=lam),
                 total=dict(features=FT, beta=bt.tolist(), mean=mut.tolist(), sd=sdt.tolist(), lam=lamt), sim_params=Pl,
                 backtest=dict((k, {kk: res[k][kk] for kk in ("n", "ll_model", "ll_market", "ll_improve_ci90", "bets", "units", "roi")}) for k in ("ml", "puck_line", "total")),
                 trained_through=str(tr.date.max()))
    json.dump(model, open(os.path.join(nm.D, "model.json"), "w"), indent=1, default=float)
    print(json.dumps({k: res[k] for k in ("ml", "puck_line", "total", "verdict", "calib_market_only_sim", "lean_sd")}, indent=1, default=float))


if __name__ == "__main__":
    main()
