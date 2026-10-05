"""Backtest of the game SIMULATOR vs the closing line (2026-10-04). Walk-forward, 1,000 sims per game.

PRE-REGISTERED CRITERIA (written before the first run; also in team/SIM.md). The simulator may affect board picks
for a sport/market ONLY if, on that sport's pooled out-of-sample seasons (NFL 2018-2025, CFB 2024-2025):
  (1) log loss of the sim's cover (or over) probability beats the de-vigged closing market, 90% bootstrap CI > 0; AND
  (2) bets where |sim % - market %| >= 3pp, at -110, win with 90% CI lower bound above 52.38%; AND
  (3) units at -110 positive in >= 6 of 8 NFL seasons / 2 of 2 CFB seasons.
Otherwise INFO ONLY.
Inputs per game, all available before kickoff: closing spread/total and de-vigged odds (the baseline), KEYS pmfs fit
on seasons < s (tilt mean correction), matchup leans from the walk-forward residual models trained on seasons < s
(backtest/out/matchup_*preds.csv.gz), matchup sim inputs (red zone, pace) from features using only prior games.
Reported for both: 'sim+matchup' (the shipped sim) and 'sim only' (market + drive model + key raking, no matchup)."""
import os, sys, json, zlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
from desk import sim
from desk.keys import Dist

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "backtest", "out")
rng0 = np.random.default_rng(11)
CFG = {"nfl": dict(pre="matchup_", feat="data/matchup/features.csv.gz", oos=(2018, 2025), need=6),
       "cfb": dict(pre="matchup_cfb_", feat="data/matchup/cfb_features.csv.gz", oos=(2024, 2025), need=2)}


def boot(x, n=4000):
    x = np.asarray(x, float)
    m = [x[rng0.integers(0, len(x), len(x))].mean() for _ in range(n)]
    return [round(float(np.percentile(m, 5)), 5), round(float(np.percentile(m, 95)), 5)]


def score(df, pcol, mcol, ycol, season_col, need):
    Q = df[df[ycol] >= 0]
    y = Q[ycol].values; ps, pm = Q[pcol].clip(0.01, 0.99).values, Q[mcol].values
    ll = lambda p: -(y * np.log(p) + (1 - y) * np.log(1 - p))
    d = ll(pm) - ll(ps)
    out = dict(n=int(len(Q)), logloss_market=round(float(ll(pm).mean()), 5), logloss_sim=round(float(ll(ps).mean()), 5),
               ll_improvement=round(float(d.mean()), 5), ll_improvement_ci90=boot(d),
               brier_market=round(float(((pm - y) ** 2).mean()), 5), brier_sim=round(float(((ps - y) ** 2).mean()), 5))
    B = df[(df[pcol] - df[mcol]).abs() >= 0.03]
    side = np.where(B[pcol] > B[mcol], 1, 0)
    res = np.where(B[ycol] < 0, 0, np.where(B[ycol].values == side, 1, -1))
    u = np.where(res > 0, 100 / 110, np.where(res < 0, -1.0, 0.0))
    w, l = int((res > 0).sum()), int((res < 0).sum())
    per = {int(s): round(float(u[B[season_col].values == s].sum()), 2) for s in sorted(B[season_col].unique())}
    wl = np.r_[np.ones(w), np.zeros(l)]
    out["bets_gap>=3pp"] = dict(bets=int(len(B)), w=w, l=l, win_pct=round(w / max(w + l, 1), 4),
                                win_pct_ci90=boot(wl) if len(wl) else [0, 0], units=round(float(u.sum()), 2),
                                seasons_positive=f"{sum(v > 0 for v in per.values())}/{len(per)}", by_season=per)
    sp = out["bets_gap>=3pp"]["seasons_positive"].split("/")
    out["criteria"] = dict(c1=out["ll_improvement_ci90"][0] > 0, c2=out["bets_gap>=3pp"]["win_pct_ci90"][0] > 0.5238,
                           c3=int(sp[0]) >= need)
    out["passes"] = all(out["criteria"].values())
    return out


def run(sport, S=1000):
    c = CFG[sport]
    sp = pd.read_csv(os.path.join(OUT, f"{c['pre']}spread_preds.csv.gz"))
    tt = pd.read_csv(os.path.join(OUT, f"{c['pre']}total_preds.csv.gz"))[["game_id", "lean", "p_mkt", "win"]]
    tt.columns = ["game_id", "lean_t", "p_mkt_over", "over_win"]
    F = pd.read_csv(os.path.join(ROOT, c["feat"]))[["game_id", "rz_home", "rz_away", "rz_mu", "pace_z"]]
    sp["game_id"], tt["game_id"], F["game_id"] = sp.game_id.astype(str), tt.game_id.astype(str), F.game_id.astype(str)
    df = sp.merge(tt, on="game_id", how="inner")
    if "rz_home" not in df.columns:
        df = df.merge(F, on="game_id", how="left")
    rows = []; D = {}
    for _, g in df.iterrows():
        s = int(g.season)
        if s not in D:
            D[s] = (Dist(f"{sport}_margin", max_season=s - 1, tilt=True), Dist(f"{sport}_total", max_season=s - 1, tilt=True))
        Dm, Dt = D[s]
        f = dict(rz_home=g.rz_home, rz_away=g.rz_away, rz_mu=g.rz_mu, pace_z=g.pace_z)
        rng = np.random.default_rng(zlib.crc32(str(g.game_id).encode()))
        a = sim.run_game(sport, g.spread_line, g.total_line, Dm, Dt, f, g.lean, g.lean_t, g.p_mkt, g.p_mkt_over, S, rng)
        b = sim.run_game(sport, g.spread_line, g.total_line, Dm, Dt, None, 0.0, 0.0, g.p_mkt, g.p_mkt_over, S, rng)
        rows.append(dict(game_id=g.game_id, season=s, p_mkt=g.p_mkt, p_mkt_over=g.p_mkt_over, win=g.win, over_win=g.over_win,
                         sim_cover=a["home_cover_ex_push"], sim_over=a["over_ex_push"], base_cover=b["home_cover_ex_push"],
                         base_over=b["over_ex_push"], home_win_sim=a["home_win"], n_eff=a["n_eff"]))
    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(OUT, f"sim_{sport}_preds.csv.gz"), index=False)
    lo, hi = c["oos"]; O = R[(R.season >= lo) & (R.season <= hi)]
    res = {"oos": f"{lo}-{hi}"}
    for lab, pc, mc, yc in (("spread_sim+matchup", "sim_cover", "p_mkt", "win"), ("total_sim+matchup", "sim_over", "p_mkt_over", "over_win"),
                            ("spread_sim_only", "base_cover", "p_mkt", "win"), ("total_sim_only", "base_over", "p_mkt_over", "over_win")):
        res[lab] = score(O, pc, mc, yc, "season", c["need"])
    res["2026_to_date"] = {lab: score(R[R.season == 2026], pc, mc, yc, "season", 1)["logloss_sim"] for lab, pc, mc, yc in
                           (("spread_sim+matchup", "sim_cover", "p_mkt", "win"),)} if (R.season == 2026).any() else None
    res["mean_n_eff"] = round(float(R.n_eff.mean()), 1)
    res["passes"] = res["spread_sim+matchup"]["passes"] or res["total_sim+matchup"]["passes"]
    return res


if __name__ == "__main__":
    R = {sp: run(sp) for sp in ("nfl", "cfb")}
    R["_criteria_text"] = __doc__.split("PRE-REGISTERED CRITERIA")[1].split("Otherwise")[0].strip()
    json.dump(R, open(os.path.join(ROOT, "data", "sim_backtest.json"), "w"), indent=1, default=float)
    for sp in ("nfl", "cfb"):
        for k in ("spread_sim+matchup", "total_sim+matchup", "spread_sim_only", "total_sim_only"):
            r = R[sp][k]
            print(sp, k, {x: r[x] for x in ("n", "logloss_market", "logloss_sim", "ll_improvement_ci90", "brier_market", "brier_sim")},
                  {x: r["bets_gap>=3pp"][x] for x in ("bets", "w", "l", "win_pct", "win_pct_ci90", "units", "seasons_positive")}, r["passes"])
