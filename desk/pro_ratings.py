"""Shared helpers for the NBA and NHL matchup layers (separate from the NFL desk/matchup.py).

1. walk_forward(): leakage-free opponent-adjusted unit ratings. For every game date d, a weighted ridge on team-games
   strictly before d (current season weight 1, previous season PREV_W, older 0):
       metric = mu + O[team] + D[opp] + home*h
   O = the team's unit (offense) rating, D = what the team concedes as a defense (its value when it is `opp`).
2. style_resid(): each team's past residual vs the market against opponents whose style looks like this week's foe.
3. common_opp(): each team's mean residual vs opponents both have played (this + last season), gap shrunk.
4. ridge_cv(): ridge, no intercept, standardized features, lambda by leave-one-season-out CV inside training seasons.
Nothing here reads a future game."""
import numpy as np, pandas as pd

PREV_W = 0.35


def walk_forward(tg, metrics, penalty=6.0, prev_w=PREV_W, date_col="date"):
    """tg: one row per team-game with columns team, opp, home, season, date, and metrics.
    Returns DataFrame (date, team) -> O_<m>, D_<m>, mu_<m>, n_cur (games this season before date)."""
    tg = tg.sort_values(date_col).reset_index(drop=True)
    teams = sorted(set(tg.team) | set(tg.opp))
    ti = {t: k for k, t in enumerate(teams)}
    nT = len(teams)
    Y = tg[metrics].to_numpy(float)
    tix, oix = tg.team.map(ti).to_numpy(), tg.opp.map(ti).to_numpy()
    hm = tg.home.to_numpy(float)
    seas = tg.season.to_numpy()
    dts = tg[date_col].to_numpy()
    out = []
    udates = sorted(set(dts))
    # game dates per season, plus each season's first date for teams in upcoming games
    for d in udates:
        s = seas[dts == d][0]
        m = (dts < d) & ((seas == s) | (seas == s - 1))
        if m.sum() < 20:
            continue
        w = np.where(seas[m] == s, 1.0, prev_w)
        n = m.sum()
        X = np.zeros((n, 2 + 2 * nT))
        X[:, 0] = 1; X[:, 1] = hm[m]
        X[np.arange(n), 2 + tix[m]] = 1
        X[np.arange(n), 2 + nT + oix[m]] = 1
        Xw = X * w[:, None]
        A = X.T @ Xw
        A[2:, 2:] += penalty * np.eye(2 * nT)
        B = Xw.T @ np.nan_to_num(Y[m])
        beta = np.linalg.solve(A, B)
        ncur = np.bincount(tix[m][seas[m] == s], minlength=nT)
        for t, k in ti.items():
            r = {"date": d, "team": t, "n_cur": int(ncur[k])}
            for j, mt in enumerate(metrics):
                r["O_" + mt] = beta[2 + k, j]; r["D_" + mt] = beta[2 + nT + k, j]; r["mu_" + mt] = beta[0, j]; r["h_" + mt] = beta[1, j]
            out.append(r)
    return pd.DataFrame(out)


def ratings_asof(tg, metrics, when, season, penalty=6.0, prev_w=PREV_W):
    """Ratings for a live date `when` (string YYYY-MM-DD) using all games before it."""
    t = tg[tg.season.isin([season, season - 1]) & (tg.date < when)].copy()
    stub = t.iloc[:1].copy(); stub["date"] = when; stub["season"] = season
    R = walk_forward(pd.concat([t, stub]), metrics, penalty, prev_w)
    return R[R.date == when]


def style_resid(games, styles, tau=0.6, k0=3.0):
    """games: rows (date, season, team, opp, resid) for lined team-games (both orientations).
    styles: DataFrame (date, team) -> standardized style columns (pre-game). For each row, the team's prior games
    (before date, this + last season) weighted by similarity of that past opponent's style (at that time) to this
    row's opponent style (now). Same opponent gets weight 1. Shrunk by k0 pseudo-games of 0."""
    sc = [c for c in styles.columns if c not in ("date", "team")]
    S = styles.set_index(["date", "team"])[sc]
    g = games.sort_values("date").reset_index(drop=True)
    g = g.join(S.add_prefix("os_"), on=["date", "opp"])
    out = np.zeros(len(g))
    by_team = {t: x for t, x in g.groupby("team")}
    OS = ["os_" + c for c in sc]
    for i, r in g.iterrows():
        x = by_team[r.team]
        p = x[(x.date < r.date) & (x.season >= r.season - 1)]
        if len(p) == 0 or pd.isna(r[OS[0]]):
            continue
        d2 = ((p[OS].to_numpy(float) - r[OS].to_numpy(float)) ** 2).sum(1)
        w = np.exp(-d2 / (2 * tau ** 2 * len(sc)))
        w[p.opp.to_numpy() == r.opp] = 1.0
        w *= np.where(p.season.to_numpy() == r.season, 1.0, PREV_W)
        w = np.nan_to_num(w)
        out[i] = (w * p.resid.to_numpy()).sum() / (w.sum() + k0)
    g["sim_resid"] = out
    return g[["date", "team", "opp", "sim_resid"]]


def common_opp(games, k0=3.0):
    """For each lined game (home h vs away a): mean residual of h vs opponents both teams have faced (this + last
    season, before date) minus the same for a, shrunk by k0. Returns DataFrame (date, home, away, co_gap, co_n)."""
    g = games.sort_values("date")
    by_team = {t: x for t, x in g.groupby("team")}
    rows = []
    for _, r in g[g.home == 1].iterrows():
        h, a = r.team, r.opp
        ph = by_team[h]; ph = ph[(ph.date < r.date) & (ph.season >= r.season - 1)]
        pa = by_team[a]; pa = pa[(pa.date < r.date) & (pa.season >= r.season - 1)]
        com = (set(ph.opp) & set(pa.opp)) - {h, a}
        if not com:
            rows.append((r.date, h, a, 0.0, 0)); continue
        mh = ph[ph.opp.isin(com)].groupby("opp").resid.mean()
        ma = pa[pa.opp.isin(com)].groupby("opp").resid.mean()
        dlt = (mh - ma).dropna()
        rows.append((r.date, h, a, float(dlt.sum() / (len(dlt) + k0)), len(dlt)))
    return pd.DataFrame(rows, columns=["date", "home", "away", "co_gap", "co_n"])


LAMBDAS = [1, 3, 10, 30, 100, 300, 1000, 3000, 10000, 30000, 100000]


def _ridge(X, y, lam):
    return np.linalg.solve(X.T @ X + lam * np.eye(X.shape[1]), X.T @ y)


def ridge_cv(X, y, seasons, lambdas=LAMBDAS):
    """Standardize on the training rows, choose lambda by leave-one-season-out MSE, refit. Returns (beta, mean, sd, lam)."""
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = (X - mu) / sd
    us = sorted(set(seasons))
    best = None
    for lam in lambdas:
        if len(us) < 2:
            break
        e = 0.0
        for s in us:
            tr, te = seasons != s, seasons == s
            b = _ridge(Z[tr], y[tr], lam)
            e += ((y[te] - Z[te] @ b) ** 2).sum()
        if best is None or e < best[0]:
            best = (e, lam)
    lam = best[1] if best else lambdas[-1]
    return _ridge(Z, y, lam), mu, sd, lam


def boot_ci(x, clusters, reps=2000, seed=7, stat=np.mean):
    """Cluster bootstrap 90% CI of stat(x) (clusters = game dates)."""
    rng = np.random.default_rng(seed)
    x = np.asarray(x, float); cl = pd.factorize(np.asarray(clusters))[0]
    groups = [np.where(cl == k)[0] for k in range(cl.max() + 1)]
    vals = []
    for _ in range(reps):
        idx = np.concatenate([groups[k] for k in rng.integers(0, len(groups), len(groups))])
        vals.append(stat(x[idx]))
    return float(np.percentile(vals, 5)), float(np.percentile(vals, 95))


def imp(a):
    return 100 / (a + 100) if a > 0 else -a / (-a + 100)


def novig(a, b):
    pa, pb = imp(a), imp(b)
    return pa / (pa + pb)


def payout(a):
    """Profit per 1u stake at American price a."""
    return a / 100 if a > 0 else 100 / -a
