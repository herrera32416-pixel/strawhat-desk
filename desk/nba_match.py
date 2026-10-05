"""NBA MATCHUP features (INFO ONLY): walk-forward opponent-adjusted four factors / pace / shot profile, rest,
strength-vs-weakness interactions, style-similar foes and common opponents, all as residuals vs the closing line."""
import os, numpy as np, pandas as pd
from . import pro_ratings as pr
from .nhl_match import style_sim, common_opp_for

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data", "nba")
METRICS = ["ortg", "pace", "efg", "tov_pct", "orb_pct", "ftr", "tpar", "tp_pct", "paint", "fbp"]
UNIT_LABEL = {"ortg": "points per 100 possessions", "pace": "pace (possessions/48)", "efg": "effective FG%", "tov_pct": "turnover rate",
              "orb_pct": "offensive rebound %", "ftr": "free-throw rate (FTM/FGA)", "tpar": "3-point attempt rate", "tp_pct": "3-point %",
              "paint": "paint points per possession", "fbp": "fast-break points per possession"}
PENALTY = 10.0   # fixed a priori (full-weight games of shrinkage)


def load_team_games():
    T = pd.read_csv(os.path.join(D, "team_games.csv.gz"), dtype={"espn_id": str})
    T["date"] = (pd.to_datetime(T.date_utc) - pd.Timedelta(hours=5)).dt.strftime("%Y-%m-%d")
    poss = 0.5 * ((T.fga - T.orb + T.tov + 0.44 * T.fta) + (T.o_fga - T.o_orb + T.o_tov + 0.44 * T.o_fta))
    T["poss"] = poss
    T["ortg"] = 100 * T.pts / poss
    T["pace"] = poss * 48 / (48 + 5 * (T.periods.fillna(4) - 4))
    T["efg"] = (T.fgm + 0.5 * T.tpm) / T.fga
    T["tov_pct"] = T.tov / poss
    T["orb_pct"] = T.orb / (T.orb + T.o_drb)
    T["ftr"] = T.ftm / T.fga
    T["tpar"] = T.tpa / T.fga
    T["tp_pct"] = T.tpm / T.tpa.clip(lower=1)
    T["paint"] = T.paint / poss
    T["fbp"] = T.fbp / poss
    return T


def load_games():
    G = pd.read_csv(os.path.join(D, "games.csv"), dtype={"espn_id": str})
    G["date"] = (pd.to_datetime(G.date_utc) - pd.Timedelta(hours=5)).dt.strftime("%Y-%m-%d")
    return G


def rest_table(dates_teams):
    r = dates_teams.drop_duplicates(["date", "team"]).sort_values("date").copy()
    r["dt"] = pd.to_datetime(r.date)
    r["rest"] = (r.groupby("team").dt.diff().dt.days.fillna(4).clip(upper=4) - 1)
    r["b2b"] = (r.rest == 0).astype(int)
    r["g4"] = r.groupby("team").dt.transform(lambda s: s.rolling("4D").count() if False else s.diff(2).dt.days.fillna(9).le(3).astype(int))  # 3 games in 4 nights
    return r[["date", "team", "rest", "b2b", "g4"]]


def build(T, games):
    tg = T[["espn_id", "season", "date", "team", "opp", "home"] + METRICS].copy()
    have = set(zip(tg.date, tg.team))
    stubs = [dict(espn_id="0", season=r.season, date=r.date, team=t, opp=o, home=hm) for r in games.itertuples()
             for t, o, hm in ((r.home, r.away, 1), (r.away, r.home, 0)) if (r.date, t) not in have]
    if stubs:
        tg = pd.concat([tg, pd.DataFrame(stubs)], ignore_index=True)
    R = pr.walk_forward(tg, METRICS, penalty=PENALTY)
    for m in METRICS:
        for side in ("O", "D"):
            c = f"{side}_{m}"
            R["z" + c] = R.groupby("date")[c].transform(lambda s: (s - s.mean()) / (s.std() + 1e-9))
    g = games.copy()
    g = g.merge(R.add_prefix("h.").rename(columns={"h.date": "date", "h.team": "home"}), on=["date", "home"], how="left")
    g = g.merge(R.add_prefix("a.").rename(columns={"a.date": "date", "a.team": "away"}), on=["date", "away"], how="left")
    rest = rest_table(tg[["date", "team"]])
    g = g.merge(rest.rename(columns={"team": "home", "rest": "rest_h", "b2b": "b2b_h", "g4": "g4_h"}), on=["date", "home"], how="left")
    g = g.merge(rest.rename(columns={"team": "away", "rest": "rest_a", "b2b": "b2b_a", "g4": "g4_a"}), on=["date", "away"], how="left")
    for m in METRICS:
        g["xh_" + m] = g[f"h.O_{m}"] + g[f"a.D_{m}"]
        g["xa_" + m] = g[f"a.O_{m}"] + g[f"h.D_{m}"]
        g["f_" + m] = g["xh_" + m] - g["xa_" + m]
        g["t_" + m] = g["xh_" + m] + g["xa_" + m]
    zi = lambda m: g[f"h.zO_{m}"] * g[f"a.zD_{m}"] - g[f"a.zO_{m}"] * g[f"h.zD_{m}"]
    g["ix_3par"], g["ix_3p"], g["ix_reb"], g["ix_paint"], g["ix_tov"], g["ix_ftr"] = zi("tpar"), zi("tp_pct"), zi("orb_pct"), zi("paint"), zi("tov_pct"), zi("ftr")
    g["pace_clash"] = (g["h.zO_pace"] - g["a.zO_pace"]).abs()
    g["f_pace_ctrl"] = g["h.zO_pace"] - g["a.zO_pace"]
    g["f_rest"] = g.rest_h.fillna(2).clip(upper=3) - g.rest_a.fillna(2).clip(upper=3)
    g["f_b2b"] = g.b2b_h.fillna(0) - g.b2b_a.fillna(0)
    g["f_g4"] = g.g4_h.fillna(0) - g.g4_a.fillna(0)
    g["t_b2b"] = g.b2b_h.fillna(0) + g.b2b_a.fillna(0)
    g["t_rest"] = g.rest_h.fillna(2).clip(upper=3) + g.rest_a.fillna(2).clip(upper=3)
    # market residuals
    if "home_score" in g:
        g["resid_s"] = g.home_score - g.away_score + g.spread_home
        g["resid_t"] = g.home_score + g.away_score - g.total
    style_cols = ["O_pace", "O_tpar", "O_ftr", "O_orb_pct", "O_paint", "D_tpar", "D_orb_pct", "O_tov_pct"]
    St = R[["date", "team"] + ["z" + c for c in style_cols]]
    lined = g.dropna(subset=["resid_s"]) if "resid_s" in g else g.iloc[:0]
    both = pd.concat([pd.DataFrame(dict(date=lined.date, season=lined.season, team=lined.home, opp=lined.away, resid=lined.resid_s)),
                      pd.DataFrame(dict(date=lined.date, season=lined.season, team=lined.away, opp=lined.home, resid=-lined.resid_s))], ignore_index=True)
    tgt = pd.concat([pd.DataFrame(dict(date=g.date, season=g.season, team=g.home, opp=g.away, resid=np.nan)),
                     pd.DataFrame(dict(date=g.date, season=g.season, team=g.away, opp=g.home, resid=np.nan))])
    allrows = pd.concat([both, tgt]).drop_duplicates(["date", "team", "opp"])
    sim = style_sim(allrows, St)
    g = g.merge(sim.rename(columns={"team": "home", "opp": "away", "sim_resid": "sim_h"}), on=["date", "home", "away"], how="left")
    g = g.merge(sim.rename(columns={"team": "away", "opp": "home", "sim_resid": "sim_a"}), on=["date", "home", "away"], how="left")
    g["f_simstyle"] = g.sim_h.fillna(0) - g.sim_a.fillna(0)
    g = g.merge(common_opp_for(both, g), on=["date", "home", "away"], how="left")
    g["f_common"] = g.co_gap.fillna(0)
    return g, R


F_SPREAD = ["f_ortg", "f_efg", "f_tov_pct", "f_orb_pct", "f_ftr", "f_tpar", "f_tp_pct", "f_paint", "f_fbp", "ix_3par", "ix_3p", "ix_reb",
            "ix_paint", "ix_tov", "ix_ftr", "f_pace_ctrl", "pace_clash", "f_rest", "f_b2b", "f_g4", "f_simstyle", "f_common"]
F_TOTAL = ["t_ortg", "t_pace", "t_efg", "t_tov_pct", "t_orb_pct", "t_ftr", "t_tpar", "t_tp_pct", "t_paint", "t_fbp", "pace_clash", "t_b2b", "t_rest"]
