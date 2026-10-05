"""MATCHUP layer (NFL): opponent-adjusted unit ratings, offense-vs-defense matchup gaps, style similarity and
common opponents -> a residual model ON TOP of the market spread/total. Walk-forward only: every rating and
feature for a game uses games played strictly before that game's date (current season + prior season at
reduced weight). Free nflverse data, never the Odds API.

Status is decided by backtest/matchup_bt.py against criteria fixed before the test (team/MATCHUP.md). Unless
data/matchup/model.json says influence=true, the layer is INFO ONLY and never changes a board pick."""
import os, json, math, datetime as dt
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TG = os.path.join(ROOT, "data", "matchup", "team_games.csv.gz")
GAMES = os.path.join(ROOT, "data", "history", "nfl_games.csv")
MODEL = os.path.join(ROOT, "data", "matchup", "model.json")
TEAM_FIX = {"OAK": "LV", "SD": "LAC", "STL": "LA", "LAR": "LA", "JAC": "JAX", "WSH": "WAS"}

METRICS = ["pass_epa", "pass_sr", "rush_epa", "rush_sr", "sack_rate", "press_rate", "expl_rate", "rz_td", "ed_pass_rate"]
WCOL = {"pass_epa": "dropbacks", "pass_sr": "dropbacks", "sack_rate": "dropbacks", "press_rate": "dropbacks",
        "rush_epa": "runs", "rush_sr": "runs", "rz_td": "rz_trips", "expl_rate": "plays", "ed_pass_rate": "plays"}
PRIOR_W = 0.35   # weight of last season's games (regression to a new season)
LAM = 6.0        # ridge penalty in full-weight games: a team's rating is ~half shrunk after 6 games
TAU = 0.6        # style-similarity kernel width (z units / sqrt(dims))
K0 = 3.0         # shrinkage pseudo-games for similar-opponent / common-opponent residuals
SPREAD_F = ["pass_gap", "rush_gap", "prot_gap", "press_gap", "expl_gap", "rz_gap",
            "pass_int", "rush_int", "prot_int", "sim_gap", "comopp_gap"]
TOTAL_F = ["tot_pass", "tot_rush", "tot_expl", "tot_rz", "tot_sack", "tot_edpr", "tot_pass_int"]


def fix(t):
    return TEAM_FIX.get(t, t)


def load_games():
    g = pd.read_csv(GAMES, low_memory=False)
    g = g[g.season >= 2014].copy()
    g["home_team"], g["away_team"] = g.home_team.map(fix), g.away_team.map(fix)
    return g


def load_tg(games=None):
    t = pd.read_csv(TG)
    t["team"], t["opp"] = t.team.map(fix), t.opp.map(fix)
    if games is not None:  # only completed games (guards against in-progress pbp)
        done = set(games.loc[games.result.notna(), "game_id"])
        t = t[t.game_id.isin(done)]
    return t


# ---------------------------------------------------------------- ratings
def ratings(tg, asof, season):
    """Opponent-adjusted ratings from games before `asof` (YYYY-MM-DD): metric = mu + O[off] + D[def] + h*home.
    O = offense unit effect, D = effect the defense has on opponents (sack_rate D > 0 = generates sacks)."""
    d = tg[(tg.game_date < asof) & (tg.season.isin([season, season - 1]))]
    if len(d) < 40:
        return None
    teams = sorted(set(d.team) | set(d.opp))
    ix = {t: i for i, t in enumerate(teams)}; T = len(teams)
    n = len(d)
    X = np.zeros((n, 2 + 2 * T))
    X[:, 0] = 1; X[:, 1] = d.home.values
    X[np.arange(n), 2 + d.team.map(ix).values] = 1
    X[np.arange(n), 2 + T + d.opp.map(ix).values] = 1
    sw = np.where(d.season.values == season, 1.0, PRIOR_W)
    pen = np.r_[0, 0, np.full(2 * T, LAM)]
    R = {"teams": teams, "mu": {}, "O": {}, "D": {}, "n_games": {}}
    for m in METRICS:
        y = d[m].values.astype(float)
        wc = d[WCOL[m]].values.astype(float)
        w = sw * wc / max(np.nanmean(wc), 1e-9)
        ok = ~np.isnan(y) & (w > 0)
        Xw = X[ok] * w[ok, None]
        A = X[ok].T @ Xw + np.diag(pen)
        b = Xw.T @ y[ok]
        beta = np.linalg.solve(A, b)
        R["mu"][m] = float(beta[0])
        R["O"][m] = dict(zip(teams, beta[2:2 + T]))
        R["D"][m] = dict(zip(teams, beta[2 + T:]))
    cnt = d[d.season == season].groupby("team").size()
    R["n_games"] = {t: int(cnt.get(t, 0)) for t in teams}
    # z-scores across teams for interactions / style / ranks
    R["zO"], R["zD"] = {}, {}
    for m in METRICS:
        for k, src in (("zO", R["O"][m]), ("zD", R["D"][m])):
            v = np.array(list(src.values())); s = v.std() or 1.0
            R[k][m] = {t: (x - v.mean()) / s for t, x in src.items()}
    return R


def style(R, t):
    """Style vector: offense pass-lean, pass-vs-run efficiency, explosiveness, OL sack exposure;
    defense pass-funnel (worse vs pass than run), sack generation, explosives allowed."""
    zO, zD = R["zO"], R["zD"]
    return np.array([zO["ed_pass_rate"][t], zO["pass_epa"][t] - zO["rush_epa"][t], zO["expl_rate"][t], zO["sack_rate"][t],
                     zD["pass_epa"][t] - zD["rush_epa"][t], zD["sack_rate"][t], zD["expl_rate"][t]])


def style_label(R, t):
    o = "pass-first" if R["zO"]["ed_pass_rate"][t] >= 0 else "run-first"
    dfn = "pass-funnel D (softer vs pass)" if (R["zD"]["pass_epa"][t] - R["zD"]["rush_epa"][t]) >= 0 else "run-funnel D (softer vs run)"
    return f"{o} offense, {dfn}"


# ---------------------------------------------------------------- residual history (cover margins vs the market)
def cover_rows(games):
    g = games[games.result.notna() & games.spread_line.notna()]
    h = pd.DataFrame(dict(team=g.home_team, opp=g.away_team, date=g.gameday, season=g.season, c=g.result - g.spread_line))
    a = pd.DataFrame(dict(team=g.away_team, opp=g.home_team, date=g.gameday, season=g.season, c=-(g.result - g.spread_line)))
    return pd.concat([h, a], ignore_index=True)


def sim_resid(CR, R, team, foe, asof, season):
    """How `team` did vs the market (cover margin) against opponents styled like `foe` (games before asof)."""
    h = CR[(CR.team == team) & (CR.date < asof) & (CR.season.isin([season, season - 1]))]
    if not len(h) or foe not in R["teams"]:
        return 0.0, 0.0
    sf = style(R, foe); k = []
    for o, s in zip(h.opp, h.season):
        if o not in R["teams"]:
            k.append(0.0); continue
        dd = 0.0 if o == foe else np.linalg.norm(style(R, o) - sf) / math.sqrt(len(sf))
        k.append((1.0 if s == season else 0.5) * math.exp(-0.5 * (dd / TAU) ** 2))
    k = np.array(k)
    return float((k * h.c.values).sum() / (k.sum() + K0)), float(k.sum())


def comopp(CR, a, b, asof, season):
    """Common opponents: a's cover margin vs each shared opponent minus b's, shrunk by K0."""
    w = CR[(CR.date < asof) & (CR.season.isin([season, season - 1]))]
    A = w[w.team == a].groupby("opp").c.mean(); B = w[w.team == b].groupby("opp").c.mean()
    common = sorted(set(A.index) & set(B.index) - {a, b})
    if not common:
        return 0.0, []
    diffs = np.array([A[o] - B[o] for o in common])
    return float(diffs.sum() / (len(common) + K0)), common


# ---------------------------------------------------------------- features
def features(R, CR, home, away, asof, season):
    if R is None or home not in R["teams"] or away not in R["teams"]:
        return None
    mu, O, D, zO, zD = R["mu"], R["O"], R["D"], R["zO"], R["zD"]
    e = lambda m, off, de: mu[m] + O[m][off] + D[m][de]
    f = {}
    f["pass_gap"] = e("pass_epa", home, away) - e("pass_epa", away, home)
    f["rush_gap"] = e("rush_epa", home, away) - e("rush_epa", away, home)
    f["prot_gap"] = e("sack_rate", away, home) - e("sack_rate", home, away)      # + = away QB sacked more
    f["press_gap"] = e("press_rate", away, home) - e("press_rate", home, away)
    f["expl_gap"] = e("expl_rate", home, away) - e("expl_rate", away, home)
    f["rz_gap"] = e("rz_td", home, away) - e("rz_td", away, home)
    # interactions: does a unit strength meet a matching weakness (beyond the additive effect)?
    f["pass_int"] = zO["pass_epa"][home] * zD["pass_epa"][away] - zO["pass_epa"][away] * zD["pass_epa"][home]
    f["rush_int"] = zO["rush_epa"][home] * zD["rush_epa"][away] - zO["rush_epa"][away] * zD["rush_epa"][home]
    f["prot_int"] = zO["sack_rate"][away] * zD["sack_rate"][home] - zO["sack_rate"][home] * zD["sack_rate"][away]
    sh, nh = sim_resid(CR, R, home, away, asof, season)
    sa, na = sim_resid(CR, R, away, home, asof, season)
    f["sim_gap"], f["sim_home"], f["sim_away"], f["sim_n_home"], f["sim_n_away"] = sh - sa, sh, sa, nh, na
    f["comopp_gap"], co = comopp(CR, home, away, asof, season)
    f["n_common"] = len(co)
    f["tot_pass"] = e("pass_epa", home, away) + e("pass_epa", away, home)
    f["tot_rush"] = e("rush_epa", home, away) + e("rush_epa", away, home)
    f["tot_expl"] = e("expl_rate", home, away) + e("expl_rate", away, home)
    f["tot_rz"] = e("rz_td", home, away) + e("rz_td", away, home)
    f["tot_sack"] = e("sack_rate", home, away) + e("sack_rate", away, home)
    f["tot_edpr"] = O["ed_pass_rate"][home] + O["ed_pass_rate"][away]
    f["tot_pass_int"] = zO["pass_epa"][home] * zD["pass_epa"][away] + zO["pass_epa"][away] * zD["pass_epa"][home]
    return f


def feature_table(games, tg, seasons):
    """Walk-forward features for every completed game in `seasons` (ratings re-fit per game date)."""
    CR = cover_rows(games)
    G = games[games.season.isin(seasons) & games.result.notna() & games.spread_line.notna()].sort_values("gameday")
    rows = []
    for (season, date), gg in G.groupby(["season", "gameday"]):
        R = ratings(tg, date, season)
        for _, g in gg.iterrows():
            f = features(R, CR, g.home_team, g.away_team, date, season)
            if f is None:
                continue
            f.update(game_id=g.game_id, season=season, week=g.week, gameday=date, home=g.home_team, away=g.away_team,
                     spread_line=g.spread_line, total_line=g.total_line, result=g.result, total=g.total,
                     home_spread_odds=g.home_spread_odds, away_spread_odds=g.away_spread_odds,
                     over_odds=g.over_odds, under_odds=g.under_odds, game_type=g.game_type)
            rows.append(f)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- residual model (ridge, standardized)
def fit_ridge(X, y, lam):
    mu, sd = X.mean(0), X.std(0); sd[sd == 0] = 1
    Z = (X - mu) / sd
    b = np.linalg.solve(Z.T @ Z + lam * np.eye(Z.shape[1]), Z.T @ (y - y.mean()))
    return dict(mu=mu.tolist(), sd=sd.tolist(), b=b.tolist(), y0=float(y.mean()), lam=lam)


def predict(m, X):
    Z = (np.asarray(X, float) - np.array(m["mu"])) / np.array(m["sd"])
    return Z @ np.array(m["b"])  # intercept dropped: the market line is the baseline (no home/over bias term)


def choose_lam(df, cols, target, grid=(10, 30, 100, 300, 1000, 3000, 10000)):
    """Leave-one-season-out CV inside the training seasons only."""
    best, bl = None, None
    ss = sorted(df.season.unique())
    if len(ss) < 2:
        return grid[-1]
    for lam in grid:
        se = 0.0
        for s in ss:
            tr, te = df[df.season != s], df[df.season == s]
            m = fit_ridge(tr[cols].values, tr[target].values, lam)
            se += float(((te[target].values - predict(m, te[cols].values)) ** 2).sum())
        if bl is None or se < bl:
            best, bl = lam, se
    return best


# ---------------------------------------------------------------- plain-English edges
def _rank(d, t, high_good=True):
    v = sorted(d.values(), reverse=high_good)
    return v.index(d[t]) + 1, len(v)


def edges(R, home, away):
    """Unit-vs-unit edges in plain English, strongest first."""
    out = []
    zO, zD = R["zO"], R["zD"]
    units = [  # (label offense, label defense, metric, offense high is good?, defense D high is good for defense?)
        ("pass rush", "OL", "press_rate", "pressure rate (sack or QB hit per dropback)"),
        ("run defense", "run game", "rush_epa", "EPA per designed run"),
        ("pass defense", "passing game", "pass_epa", "EPA per dropback"),
        ("defense vs explosives", "explosive-play offense", "expl_rate", "explosive-play rate"),
        ("red-zone defense", "red-zone offense", "rz_td", "red-zone TD rate"),
    ]
    for off, de in ((home, away), (away, home)):
        for dlab, olab, m, desc in units:
            if m in ("press_rate",):
                # offense: low pressure allowed is good; defense: high D (more pressure) is good
                so, sd_ = -zO[m][off], zD[m][de]
                ro, n = _rank(R["O"][m], off, high_good=False); rd, _ = _rank(R["D"][m], de, high_good=True)
                # edge for DEFENSE when rush good (sd_>0) and OL bad (so<0)
                score = sd_ - so
                txt = f"{de} pass rush #{rd} vs {off} OL #{ro} of {n} in {desc}"
            else:
                so, sd_ = zO[m][off], -zD[m][de]   # D high = allows more = bad defense
                ro, n = _rank(R["O"][m], off, True); rd, _ = _rank(R["D"][m], de, high_good=False)
                score = so - sd_
                txt = f"{off} {olab} #{ro} vs {de} {dlab} #{rd} of {n} in {desc}"
            # only show real mismatches: one side clearly good and the other clearly bad
            if m == "press_rate":
                if sd_ > 0.7 and so < -0.7:
                    out.append(dict(edge_for=de, score=round(float(score), 2), text=txt + f" -> edge {de}"))
                elif so > 0.7 and sd_ < -0.7:
                    out.append(dict(edge_for=off, score=round(float(-score), 2), text=txt + f" -> edge {off} (protection holds)"))
            else:
                if so > 0.7 and sd_ < -0.7:
                    out.append(dict(edge_for=off, score=round(float(score), 2), text=txt + f" -> edge {off}"))
                elif so < -0.7 and sd_ > 0.7:
                    out.append(dict(edge_for=de, score=round(float(-score), 2), text=txt + f" -> edge {de}"))
                elif so > 0.9 and sd_ > 0.9:
                    out.append(dict(edge_for="strength vs strength", score=round(float(min(so, sd_)), 2), text=txt + " (strength vs strength)"))
    return sorted(out, key=lambda x: -abs(x["score"]))[:5]


# ---------------------------------------------------------------- live
def live(now=None, write=True):
    """Matchup panel for this week's NFL games. 0 Odds API credits: the market line shown is the nflverse
    schedule line (the board's DK line is on the Board tab)."""
    from zoneinfo import ZoneInfo
    CT = ZoneInfo("America/Chicago")
    now = (now or dt.datetime.now(CT)).astimezone(CT)
    games = load_games(); tg = load_tg(games); CR = cover_rows(games)
    M = json.load(open(MODEL)) if os.path.exists(MODEL) else None
    today = now.strftime("%Y-%m-%d"); horizon = (now + dt.timedelta(days=7)).strftime("%Y-%m-%d")
    up = games[(games.gameday >= today) & (games.gameday <= horizon) & games.result.isna()].sort_values(["gameday", "gametime"])
    out = []
    ET = ZoneInfo("America/New_York")
    for _, g in up.iterrows():
        try:  # skip games already kicked (nflverse gametime is ET)
            if dt.datetime.fromisoformat(f"{g.gameday}T{g.gametime}").replace(tzinfo=ET) <= now:
                continue
        except Exception:
            pass
        season = int(g.season)
        R = ratings(tg, g.gameday, season)
        f = features(R, CR, g.home_team, g.away_team, g.gameday, season)
        if f is None:
            continue
        lean_s = lean_t = None
        if M:
            lean_s = float(predict(M["spread"]["model"], [[f[c] for c in M["spread"]["features"]]])[0])
            lean_t = float(predict(M["total"]["model"], [[f[c] for c in M["total"]["features"]]])[0])
        co_list = comopp(CR, g.home_team, g.away_team, g.gameday, season)[1]
        out.append(dict(
            game=f"{g.away_team} @ {g.home_team}", home=g.home_team, away=g.away_team, gameday=g.gameday, gametime=g.gametime,
            spread_line=None if pd.isna(g.spread_line) else float(g.spread_line), total_line=None if pd.isna(g.total_line) else float(g.total_line),
            styles={g.home_team: style_label(R, g.home_team), g.away_team: style_label(R, g.away_team)},
            edges=edges(R, g.home_team, g.away_team),
            ranks={t: unit_ranks(R, t) for t in (g.home_team, g.away_team)},
            similar=dict(home=round(f["sim_home"], 2), away=round(f["sim_away"], 2), n_home=round(f["sim_n_home"], 1), n_away=round(f["sim_n_away"], 1)),
            common_opponents=co_list, comopp_gap=round(f["comopp_gap"], 2),
            lean_spread_pts=None if lean_s is None else round(lean_s, 2), lean_total_pts=None if lean_t is None else round(lean_t, 2),
            lean_text=lean_text(g, lean_s, lean_t)))
    res = dict(generated_ct=now.strftime("%a %b %-d %Y %-I:%M %p CT"), status=(M or {}).get("status", "INFO ONLY"),
               influence=bool((M or {}).get("influence", False)), backtest=(M or {}).get("backtest_summary"), games=out,
               data_through=str(tg.game_date.max()))
    if write:
        json.dump(res, open(os.path.join(ROOT, "docs", "data", "matchups.json"), "w"))
    return res


def unit_ranks(R, t):
    r = lambda d, hg: _rank(d, t, hg)[0]
    return {"pass_off": r(R["O"]["pass_epa"], True), "rush_off": r(R["O"]["rush_epa"], True),
            "pass_prot": r(R["O"]["press_rate"], False), "pass_def": r(R["D"]["pass_epa"], False),
            "rush_def": r(R["D"]["rush_epa"], False), "pass_rush": r(R["D"]["press_rate"], True),
            "n_games": R["n_games"].get(t, 0)}


def lean_text(g, ls, lt):
    if ls is None:
        return "no model"
    side = g.home_team if ls > 0 else g.away_team
    s = f"Matchup lean: {side} by {abs(ls):.1f} pts vs the market spread"
    if lt is not None:
        s += f"; total {'over' if lt > 0 else 'under'} by {abs(lt):.1f}"
    return s
