"""NHL MATCHUP features (INFO ONLY): walk-forward unit ratings, goalie GSAx, rest, matchup gaps, style-similar foes,
common opponents, all relative to the market-anchored sim (desk/nhl_sim.py). Used by backtest/nhl_bt.py and desk/nhl_run.py."""
import os, numpy as np, pandas as pd
from . import pro_ratings as pr, nhl_sim

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data", "nhl")
METRICS = ["xgf60_e", "cf60_e", "hdf60_e", "pp_xg", "pp_min", "fin"]
UNIT_LABEL = {"xgf60_e": "5v5 chance creation (xG/60)", "cf60_e": "5v5 shot volume (attempts/60)", "hdf60_e": "5v5 high-danger xG/60",
              "pp_xg": "power play xG per game", "pp_min": "power-play time drawn (min/game)", "fin": "finishing (goals - xG)"}
PENALTY = 15.0   # full-weight games of shrinkage toward league average (hockey is noisy); fixed a priori, not tuned
GK0 = 20.0       # goalie GSAx prior, in games


def load_team_games():
    T = pd.read_csv(os.path.join(D, "team_games.csv.gz"))
    e = T.e_toi.clip(lower=60) / 3600
    T["xgf60_e"] = T.e_xgf / e; T["cf60_e"] = T.e_cf / e; T["hdf60_e"] = T.e_hdf / e
    T["pp_xg"] = T.pp_xgf; T["pp_min"] = T.pp_toi / 60; T["fin"] = T.a_gf - T.a_xgf
    # situational GSAx conceded by the team's goalies this game (5v5 + PP + PK; excludes empty-net states)
    T["sit_xga"] = T.e_xga + T.pp_xga + T.pk_xga; T["sit_ga"] = T.e_ga + T.pp_ga + T.pk_ga
    return T


def rest_table(T):
    r = T[["gameId", "date", "team"]].drop_duplicates().sort_values("date").copy()
    r["dt"] = pd.to_datetime(r.date)
    r["rest"] = r.groupby("team").dt.diff().dt.days.fillna(5).clip(upper=4) - 1
    r["b2b"] = (r.rest == 0).astype(int)
    return r[["date", "team", "rest", "b2b"]]


def goalie_ratings(T, GL):
    """Per (gameId, team): the starter's GSAx/game rating from games strictly before (decayed, shrunk by GK0 games)."""
    GL = GL.copy()
    GL["team"] = GL.team.replace({"ARI": "ARI"})
    tsa = GL.groupby(["gameId", "team"]).sa.transform("sum").clip(lower=1)
    GL["share"] = GL.sa / tsa
    x = GL.merge(T[["gameId", "team", "sit_xga"]], on=["gameId", "team"], how="left")
    x["gsax"] = x.share * x.sit_xga - (x.sa - x.sv)
    x = x.dropna(subset=["gsax"]).sort_values("date")
    x["season"] = x.gameId // 1000000
    rows = []
    hist = {}
    for d, grp in x.groupby("date", sort=True):
        for _, r in grp.iterrows():
            if r.gs == 1:
                h = hist.get(r.pid, [])
                w = np.array([1.0 if s == r.season else (0.5 if s == r.season - 1 else 0.25) for s, _ in h])
                v = np.array([g for _, g in h])
                rows.append((r.gameId, r.team, r.pid, r["name"], float((w * v).sum() / (w.sum() + GK0)) if len(h) else 0.0, len(h)))
        for _, r in grp.iterrows():
            hist.setdefault(r.pid, []).append((r.season, r.gsax))
    return pd.DataFrame(rows, columns=["gameId", "team", "pid", "goalie", "g_rating", "g_n"]), hist


def goalie_rating_now(hist, pid, season):
    h = hist.get(pid, [])
    if not h:
        return 0.0
    w = np.array([1.0 if s == season else (0.5 if s == season - 1 else 0.25) for s, _ in h])
    return float((w * np.array([g for _, g in h])).sum() / (w.sum() + GK0))


def market_anchor(df, P):
    """df with ml_home, ml_away, total, over_price, under_price -> lam_h, lam_a, p_mkt_home, q_over."""
    ph = np.array([pr.novig(a, b) for a, b in zip(df.ml_home, df.ml_away)])
    has_t = df.total.notna() & df.over_price.notna() & df.under_price.notna()
    tl = df.total.where(has_t, df.total_fill).to_numpy(float)
    qo = np.where(has_t, [pr.novig(o, u) if t else 0.5 for o, u, t in zip(df.over_price.fillna(-110), df.under_price.fillna(-110), has_t)], 0.5)
    lh, la = nhl_sim.anchor(ph, tl, qo, P)
    return lh, la, ph, qo, has_t.to_numpy()


def build(T, games, P, GR):
    """games: one row per game (date, season, home, away, gameId optional, + market cols + results if known).
    Returns games with lam/expected values, residuals and matchup features."""
    tg = T[["gameId", "season", "date", "team", "opp", "home"] + METRICS].copy()
    # stub rows so ratings exist for game dates without MoneyPuck rows (live slate / missing)
    have = set(zip(tg.date, tg.team))
    stubs = [dict(gameId=0, season=r.season, date=r.date, team=t, opp=o, home=hm) for r in games.itertuples()
             for t, o, hm in ((r.home, r.away, 1), (r.away, r.home, 0)) if (r.date, t) not in have]
    if stubs:
        tg = pd.concat([tg, pd.DataFrame(stubs)], ignore_index=True)
    R = pr.walk_forward(tg, METRICS, penalty=PENALTY)
    # z-scores across teams per date (for interactions + style)
    for m in METRICS:
        for side in ("O", "D"):
            c = f"{side}_{m}"
            R["z" + c] = R.groupby("date")[c].transform(lambda s: (s - s.mean()) / (s.std() + 1e-9))
    g = games.copy()
    hR = R.add_prefix("h.").rename(columns={"h.date": "date", "h.team": "home"})
    aR = R.add_prefix("a.").rename(columns={"a.date": "date", "a.team": "away"})
    g = g.merge(hR, on=["date", "home"], how="left").merge(aR, on=["date", "away"], how="left")
    rest = rest_table(pd.concat([T[["gameId", "date", "team"]], tg[tg.gameId == 0][["gameId", "date", "team"]]]))
    g = g.merge(rest.rename(columns={"team": "home", "rest": "rest_h", "b2b": "b2b_h"}), on=["date", "home"], how="left")
    g = g.merge(rest.rename(columns={"team": "away", "rest": "rest_a", "b2b": "b2b_a"}), on=["date", "away"], how="left")
    # starting goalies (pre-game GSAx rating)
    gr = GR[["date", "team", "g_rating", "goalie"]].drop_duplicates(["date", "team"])
    g = g.merge(gr.rename(columns={"team": "home", "g_rating": "g_h", "goalie": "goalie_h"}), on=["date", "home"], how="left")
    g = g.merge(gr.rename(columns={"team": "away", "g_rating": "g_a", "goalie": "goalie_a"}), on=["date", "away"], how="left")
    # market anchor (sim params P: dict season -> params, fitted on earlier seasons)
    for c in ("lam_h", "lam_a", "p_mkt", "q_over", "exp_h", "exp_a"):
        g[c] = np.nan
    g["has_total"] = False
    for s_, idx in g.groupby("season").groups.items():
        Ps = P[s_] if isinstance(P, dict) and s_ in P else (P if not isinstance(P, dict) or "theta" in P else nhl_sim.DEFAULT)
        sub = g.loc[idx]
        lh, la, ph, qo, has_t = market_anchor(sub, Ps)
        pm = nhl_sim.probs(nhl_sim.final_joint(lh, la, Ps))
        g.loc[idx, "lam_h"], g.loc[idx, "lam_a"], g.loc[idx, "p_mkt"], g.loc[idx, "q_over"] = lh, la, ph, qo
        g.loc[idx, "has_total"] = has_t
        g.loc[idx, "exp_h"], g.loc[idx, "exp_a"] = pm["exp_h"], pm["exp_a"]
    if "home_score" in g:
        g["resid_d"] = (g.home_score - g.away_score) - (g.exp_h - g.exp_a)
        g["resid_t"] = (g.home_score + g.away_score) - (g.exp_h + g.exp_a)
    ex = lambda m, s1, s2: g[f"{s1}.O_{m}"] + g[f"{s2}.D_{m}"]
    for m in METRICS:
        g["xh_" + m], g["xa_" + m] = ex(m, "h", "a"), ex(m, "a", "h")
        g["f_" + m] = g["xh_" + m] - g["xa_" + m]
        g["t_" + m] = g["xh_" + m] + g["xa_" + m]
    g["ix_xg"] = g["h.zO_xgf60_e"] * g["a.zD_xgf60_e"] - g["a.zO_xgf60_e"] * g["h.zD_xgf60_e"]
    g["ix_pp"] = g["h.zO_pp_xg"] * g["a.zD_pp_xg"] - g["a.zO_pp_xg"] * g["h.zD_pp_xg"]
    g["ix_hd"] = g["h.zO_hdf60_e"] * g["a.zD_hdf60_e"] - g["a.zO_hdf60_e"] * g["h.zD_hdf60_e"]
    g["f_goalie"] = g.g_h.fillna(0) - g.g_a.fillna(0)
    g["t_goalie"] = -(g.g_h.fillna(0) + g.g_a.fillna(0))
    g["ix_goalie_hd"] = g.g_h.fillna(0) * g["xa_hdf60_e"] - g.g_a.fillna(0) * g["xh_hdf60_e"]  # goalie vs shot quality faced
    g["f_rest"] = g.rest_h.fillna(2) - g.rest_a.fillna(2)
    g["f_b2b"] = g.b2b_h.fillna(0) - g.b2b_a.fillna(0)
    g["t_b2b"] = g.b2b_h.fillna(0) + g.b2b_a.fillna(0)
    # style similarity + common opponents (on the market residual, lined games only)
    style_cols = ["O_cf60_e", "O_xgf60_e", "D_xgf60_e", "O_hdf60_e", "O_pp_min", "D_pp_min", "O_fin"]
    St = R[["date", "team"] + ["z" + c for c in style_cols]]
    if "resid_d" in g:
        lined = g.dropna(subset=["resid_d"])
        both = pd.concat([pd.DataFrame(dict(date=lined.date, season=lined.season, team=lined.home, opp=lined.away, resid=lined.resid_d)),
                          pd.DataFrame(dict(date=lined.date, season=lined.season, team=lined.away, opp=lined.home, resid=-lined.resid_d))], ignore_index=True)
    else:
        both = pd.DataFrame(columns=["date", "season", "team", "opp", "resid", "home"])
    # include target rows (unlined/live) so they get features too
    tgt = pd.concat([g.assign(team=g.home, opp=g.away, resid=np.nan), g.assign(team=g.away, opp=g.home, resid=np.nan)])[["date", "season", "team", "opp", "resid"]]
    allrows = pd.concat([both[["date", "season", "team", "opp", "resid"]], tgt]).drop_duplicates(["date", "team", "opp"])
    sim = style_sim(allrows, St)
    g = g.merge(sim.rename(columns={"team": "home", "opp": "away", "sim_resid": "sim_h"}), on=["date", "home", "away"], how="left")
    g = g.merge(sim.rename(columns={"team": "away", "opp": "home", "sim_resid": "sim_a"}), on=["date", "home", "away"], how="left")
    g["f_simstyle"] = g.sim_h.fillna(0) - g.sim_a.fillna(0)
    co_live = common_opp_for(both, g)
    g = g.merge(co_live, on=["date", "home", "away"], how="left")
    g["f_common"] = g.co_gap.fillna(0)
    return g, R


def style_sim(rows, St, tau=0.6, k0=3.0):
    """Like pr.style_resid but rows without a residual (future/target) still get a value from prior lined rows."""
    sc = [c for c in St.columns if c not in ("date", "team")]
    S = St.set_index(["date", "team"])[sc]
    g = rows.sort_values("date").reset_index(drop=True).join(S.add_prefix("os_"), on=["date", "opp"])
    OS = ["os_" + c for c in sc]
    out = np.full(len(g), np.nan)
    for t, x in g.groupby("team"):
        x = x.sort_values("date")
        lined = x.dropna(subset=["resid"])
        L_d, L_s, L_o, L_r = lined.date.to_numpy(), lined.season.to_numpy(), lined.opp.to_numpy(), lined.resid.to_numpy()
        L_S = lined[OS].to_numpy(float)
        for i, r in zip(x.index, x.itertuples(index=False)):
            m = (L_d < r.date) & (L_s >= r.season - 1)
            if not m.any():
                out[i] = 0.0; continue
            v = np.array([getattr(r, c) for c in OS], float)
            if np.isnan(v).any():
                out[i] = 0.0; continue
            d2 = np.nansum((L_S[m] - v) ** 2, 1)
            w = np.exp(-d2 / (2 * tau ** 2 * len(sc)))
            w[L_o[m] == r.opp] = 1.0
            w *= np.where(L_s[m] == r.season, 1.0, pr.PREV_W)
            out[i] = float((w * L_r[m]).sum() / (w.sum() + k0))
    g["sim_resid"] = out
    return g[["date", "team", "opp", "sim_resid"]].drop_duplicates(["date", "team", "opp"])


def common_opp_for(both, g, k0=3.0):
    by = {t: x for t, x in both.groupby("team")} if len(both) else {}
    rows = []
    for r in g[["date", "season", "home", "away"]].itertuples(index=False):
        ph, pa = by.get(r.home), by.get(r.away)
        if ph is None or pa is None:
            rows.append((r.date, r.home, r.away, 0.0, 0)); continue
        ph = ph[(ph.date < r.date) & (ph.season >= r.season - 1)]; pa = pa[(pa.date < r.date) & (pa.season >= r.season - 1)]
        com = (set(ph.opp) & set(pa.opp)) - {r.home, r.away}
        if not com:
            rows.append((r.date, r.home, r.away, 0.0, 0)); continue
        dl = (ph[ph.opp.isin(com)].groupby("opp").resid.mean() - pa[pa.opp.isin(com)].groupby("opp").resid.mean()).dropna()
        rows.append((r.date, r.home, r.away, float(dl.sum() / (len(dl) + k0)), len(dl)))
    return pd.DataFrame(rows, columns=["date", "home", "away", "co_gap", "co_n"]).drop_duplicates(["date", "home", "away"])


F_DIFF = ["f_xgf60_e", "f_hdf60_e", "f_cf60_e", "f_pp_xg", "f_pp_min", "f_fin", "ix_xg", "ix_pp", "ix_hd", "f_goalie", "ix_goalie_hd",
          "f_rest", "f_b2b", "f_simstyle", "f_common"]
F_TOT = ["t_xgf60_e", "t_hdf60_e", "t_cf60_e", "t_pp_xg", "t_pp_min", "t_fin", "t_goalie", "t_b2b"]
