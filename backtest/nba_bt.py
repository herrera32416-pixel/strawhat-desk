"""NBA matchup layer vs the closing line: pre-registered test (research/PREREG_NBA_NHL.md).

python backtest/nba_bt.py   -> backtest/out/nba_bt.json, backtest/out/nba_preds.csv.gz, data/nba/model.json, data/nba/sim_params.json
Market = ESPN-listed pregame close (DraftKings 2020-23 & most of 2025, ESPN BET 2024), de-vigged two-way.
Model probability = market-anchored distribution shifted by the shrunk lean: p = Phi(Phi^-1(q) + lean / sd), sd = the
historical residual SD (the possession sim is near-normal; checked against the sim on a sample, reported as sim_check)."""
import json, os, sys
import numpy as np, pandas as pd
from scipy.stats import norm
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from desk import nba_match as nm, nba_sim, pro_ratings as pr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "backtest", "out")
TEST = [2022, 2023, 2024, 2025]


def ll(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def nv(a, b):
    return np.array([pr.novig(x, y) if pd.notna(x) and pd.notna(y) else np.nan for x, y in zip(a, b)])


def evaluate(d, pm, pk, y, px_yes, px_no, bet_yes, bet_no):
    lm, lk = ll(pm, y), ll(pk, y)
    imp = lk - lm
    ci = pr.boot_ci(imp, d.date)
    pay = np.where(bet_yes, np.where(y == 1, [pr.payout(a) for a in px_yes], -1.0), np.where(bet_no, np.where(y == 0, [pr.payout(a) for a in px_no], -1.0), 0.0))
    bet = bet_yes | bet_no
    be = np.where(bet_yes, [pr.imp(a) for a in px_yes], np.where(bet_no, [pr.imp(a) for a in px_no], np.nan))
    win = (pay > 0)[bet].astype(float)
    wci = pr.boot_ci(win, d.date[bet]) if bet.sum() > 5 else (None, None)
    rci = pr.boot_ci(pay[bet], d.date[bet]) if bet.sum() > 5 else (None, None)
    seasons = {int(s): dict(bets=int(bet[(d.season == s).to_numpy()].sum()), units=round(float(pay[(d.season == s).to_numpy()].sum()), 2)) for s in sorted(d.season.unique())}
    return dict(n=int(len(d)), ll_model=round(float(lm.mean()), 5), ll_market=round(float(lk.mean()), 5), ll_improve=round(float(imp.mean()), 6),
                ll_improve_ci90=[round(ci[0], 6), round(ci[1], 6)], bets=int(bet.sum()), wins=int(win.sum()),
                win_pct=round(float(win.mean()), 4) if bet.sum() else None, win_ci90=[round(x, 4) if x is not None else None for x in wci],
                breakeven=round(float(np.nanmean(be)), 4) if bet.sum() else None, units=round(float(pay[bet].sum()), 2),
                roi=round(float(pay[bet].mean()), 4) if bet.sum() else None, roi_ci90=[round(x, 4) if x is not None else None for x in rci],
                by_season=seasons, seasons_positive=sum(1 for v in seasons.values() if v["units"] > 0))


def main():
    T, G = nm.load_team_games(), nm.load_games()
    G = G.dropna(subset=["home_score", "away_score"])
    g, R = nm.build(T, G)
    g = g[g.season >= 2021].reset_index(drop=True)
    g.to_csv(os.path.join(OUT, "nba_features.csv.gz"), index=False)
    FS, FT = nm.F_SPREAD, nm.F_TOTAL
    g["lean_s"] = 0.0; g["lean_t"] = 0.0
    g["sd_m"] = np.nan; g["sd_t"] = np.nan
    lams, simp = {}, {}
    for s in TEST:
        tr = g[(g.season < s)].dropna(subset=["resid_s", "resid_t"])
        te = (g.season == s).to_numpy()
        b, mu, sd, lam = pr.ridge_cv(tr[FS].fillna(0).to_numpy(float), tr.resid_s.to_numpy(float), tr.season.to_numpy())
        g.loc[te, "lean_s"] = ((g.loc[te, FS].fillna(0).to_numpy(float) - mu) / sd) @ b
        bt, mut, sdt, lamt = pr.ridge_cv(tr[FT].fillna(0).to_numpy(float), tr.resid_t.to_numpy(float), tr.season.to_numpy())
        g.loc[te, "lean_t"] = ((g.loc[te, FT].fillna(0).to_numpy(float) - mut) / sdt) @ bt
        P = nba_sim.calibrate(T, G, list(range(2020, s)))
        simp[s] = P
        g.loc[te, "sd_m"], g.loc[te, "sd_t"] = P["sd_margin_emp"], P["sd_total_emp"]
        lams[s] = dict(spread=lam, total=lamt, coef_spread=dict(zip(FS, np.round(b, 4).tolist())), coef_total=dict(zip(FT, np.round(bt, 4).tolist())))
        print(s, "lambda", lam, lamt, "lean sd", round(float(g.loc[te, "lean_s"].std()), 3), round(float(g.loc[te, "lean_t"].std()), 3), flush=True)
    t = g[g.season.isin(TEST)].dropna(subset=["spread_home", "total", "sp_price_home", "sp_price_away", "over_price", "under_price"]).copy()
    q_s = nv(t.sp_price_home, t.sp_price_away); q_t = nv(t.over_price, t.under_price)
    t["q_cover"], t["q_over"] = q_s, q_t
    t["p_cover_m"] = norm.cdf(norm.ppf(q_s) + t.lean_s / t.sd_m)
    t["p_over_m"] = norm.cdf(norm.ppf(q_t) + t.lean_t / t.sd_t)
    cm0 = -t.spread_home + t.sd_m * norm.ppf(q_s)
    t["p_ml_0"] = norm.cdf(cm0 / t.sd_m); t["p_ml_m"] = norm.cdf((cm0 + t.lean_s) / t.sd_m)
    t["q_ml"] = nv(t.ml_home, t.ml_away)
    marg = t.home_score - t.away_score
    cov = (marg + t.spread_home); tot = t.home_score + t.away_score
    res = {}
    ms = (cov != 0).to_numpy(); mt = (tot != t.total).to_numpy()
    d = t[ms]; y = (cov[ms] > 0).astype(int).to_numpy()
    res["spread"] = evaluate(d, d.p_cover_m.to_numpy(), d.q_cover.to_numpy(), y, d.sp_price_home, d.sp_price_away,
                             (d.lean_s >= 1.5).to_numpy(), (d.lean_s <= -1.5).to_numpy())
    d = t[mt]; y = (tot[mt] > t.total[mt]).astype(int).to_numpy()
    res["total"] = evaluate(d, d.p_over_m.to_numpy(), d.q_over.to_numpy(), y, d.over_price, d.under_price,
                            (d.lean_t >= 1.5).to_numpy(), (d.lean_t <= -1.5).to_numpy())
    mm = t.q_ml.notna().to_numpy()
    d = t[mm]; y = (marg[mm] > 0).astype(int).to_numpy(); e = d.p_ml_m - d.q_ml
    res["ml"] = evaluate(d, d.p_ml_m.to_numpy(), d.q_ml.to_numpy(), y, d.ml_home, d.ml_away, (e >= 0.03).to_numpy(), (e <= -0.03).to_numpy())
    e0 = d.p_ml_0 - d.q_ml
    res["calib_market_only_ml"] = evaluate(d, d.p_ml_0.to_numpy(), d.q_ml.to_numpy(), y, d.ml_home, d.ml_away, (e0 >= 0.03).to_numpy(), (e0 <= -0.03).to_numpy())
    # check: possession sim vs the normal shortcut on 150 random test games
    rng = np.random.default_rng(3); samp = t.sample(150, random_state=3)
    diffs = []
    for r in samp.itertuples():
        S = nba_sim.Sim(simp[r.season], n=1000, seed=int(rng.integers(1e9)))
        cm, ct = S.anchor(r.spread_home, r.q_cover, r.total, r.q_over)
        m_, t_ = S.run(cm + r.lean_s, ct + r.lean_t)
        diffs.append((float((m_ > 0).mean()) - r.p_ml_m, nba_sim._cond(m_ + r.spread_home) - r.p_cover_m, nba_sim._cond(t_ - r.total) - r.p_over_m))
    diffs = np.array(diffs)
    res["sim_check"] = dict(n=150, mean_abs_diff_ml=round(float(np.abs(diffs[:, 0]).mean()), 4), mean_diff_ml=round(float(diffs[:, 0].mean()), 4),
                            mean_abs_diff_cover=round(float(np.abs(diffs[:, 1]).mean()), 4), mean_abs_diff_over=round(float(np.abs(diffs[:, 2]).mean()), 4),
                            note="1,000-sim Monte Carlo noise alone is about +-1.6pp per game")
    def verdict(r, kind):
        c1 = r["ll_improve_ci90"][0] > 0
        if kind == "ml":
            c2 = r["bets"] >= 100 and r["roi_ci90"][0] is not None and r["roi_ci90"][0] > 0
        else:
            c2 = r["win_ci90"][0] is not None and r["win_ci90"][0] > r["breakeven"]
        c3 = r["seasons_positive"] >= 3
        return dict(c1_ll_ci_gt0=bool(c1), c2=bool(c2), c3_seasons=bool(c3), passed=bool(c1 and c2 and c3))
    res["verdict"] = {k: verdict(res[k], k) for k in ("spread", "total", "ml")}
    res["influence"] = any(v["passed"] for v in res["verdict"].values())
    res["lean_sd"] = dict(spread=round(float(t.lean_s.std()), 4), total=round(float(t.lean_t.std()), 4),
                          share_abs_ge_1p5=dict(spread=round(float((t.lean_s.abs() >= 1.5).mean()), 4), total=round(float((t.lean_t.abs() >= 1.5).mean()), 4)))
    res["lambdas"] = {str(k): v for k, v in lams.items()}
    res["coverage"] = {str(int(s)): dict(games=int((G.season == s).sum()), lined=int(G[(G.season == s)].spread_home.notna().sum()),
                                          ml=int(G[(G.season == s)].ml_home.notna().sum()),
                                          providers=G[G.season == s].odds_provider.value_counts().to_dict()) for s in sorted(G.season.unique())}
    t[["date", "season", "home", "away", "home_score", "away_score", "spread_home", "total", "ml_home", "ml_away", "q_cover", "p_cover_m", "q_over", "p_over_m",
       "q_ml", "p_ml_0", "p_ml_m", "lean_s", "lean_t"]].to_csv(os.path.join(OUT, "nba_preds.csv.gz"), index=False)
    # live model: all lined seasons through 2025-26
    tr = g.dropna(subset=["resid_s", "resid_t"])
    b, mu, sd, lam = pr.ridge_cv(tr[FS].fillna(0).to_numpy(float), tr.resid_s.to_numpy(float), tr.season.to_numpy())
    bt, mut, sdt, lamt = pr.ridge_cv(tr[FT].fillna(0).to_numpy(float), tr.resid_t.to_numpy(float), tr.season.to_numpy())
    P = nba_sim.calibrate(T, G, list(range(2020, 2026)))
    json.dump(P, open(nba_sim.PARAMS, "w"), indent=1)
    model = dict(influence=bool(res["influence"]), status="INFO ONLY" if not res["influence"] else "PASSED - needs Luis review",
                 spread=dict(features=FS, beta=b.tolist(), mean=mu.tolist(), sd=sd.tolist(), lam=lam),
                 total=dict(features=FT, beta=bt.tolist(), mean=mut.tolist(), sd=sdt.tolist(), lam=lamt),
                 backtest={k: {kk: res[k][kk] for kk in ("n", "ll_model", "ll_market", "ll_improve_ci90", "bets", "wins", "units", "roi")} for k in ("spread", "total", "ml")},
                 trained_through=str(tr.date.max()))
    json.dump(model, open(os.path.join(nm.D, "model.json"), "w"), indent=1, default=float)
    json.dump(res, open(os.path.join(OUT, "nba_bt.json"), "w"), indent=1, default=float)
    print(json.dumps({k: res[k] for k in ("spread", "total", "ml", "calib_market_only_ml", "verdict", "sim_check", "lean_sd")}, indent=1, default=float))


if __name__ == "__main__":
    main()
