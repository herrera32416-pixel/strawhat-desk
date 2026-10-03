"""PROPS role: nflverse usage -> projection -> empirical outcome distribution -> P(over).

Projection (all inputs strictly pre-game):
  team volume  = OLS(team pass att / carries ~ EWMA volume + market expected margin + market implied team total)
  player share = EWMA target share / carry share (half-life 4 games, carries across seasons)
  efficiency   = EWMA yds/target, catch rate, yds/carry, yds/att, TD rates, each shrunk to the position mean
  matchup      = opponent EWMA allowed yds/target, yds/carry, yds/att relative to league (shrunk 50%)
P(over line)  = share of training residual ratios (actual/projection), binned by projection size, with
                ratio*projection > line.  This keeps the skew (median < mean) and the zero mass.
"""
import os, re, unicodedata, math
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "cache")
HL = 4.0
MARKETS = {  # odds-api key -> (stat column, kind)
    "player_reception_yds": "receiving_yards", "player_receptions": "receptions", "player_rush_yds": "rushing_yards",
    "player_pass_yds": "passing_yards", "player_pass_tds": "passing_tds", "player_anytime_td": "anytime_td",
}
LABEL = {"player_reception_yds": "Rec Yds", "player_receptions": "Receptions", "player_rush_yds": "Rush Yds",
         "player_pass_yds": "Pass Yds", "player_pass_tds": "Pass TDs", "player_anytime_td": "Anytime TD"}


def pname(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", s)
    return re.sub(r"[^a-z]", "", s)


def load_stats(seasons):
    fr = []
    for y in seasons:
        p = os.path.join(CACHE, f"stats_player_week_{y}.csv")
        if os.path.exists(p):
            fr.append(pd.read_csv(p, low_memory=False))
    d = pd.concat(fr, ignore_index=True)
    d = d[d.season_type.isin(["REG", "POST"])].copy()
    for c in ["attempts", "passing_yards", "passing_tds", "carries", "rushing_yards", "rushing_tds", "targets",
              "receptions", "receiving_yards", "receiving_tds", "completions"]:
        d[c] = d[c].fillna(0.0)
    d["anytime_td"] = ((d.rushing_tds + d.receiving_tds) > 0).astype(float)
    d["tds"] = d.rushing_tds + d.receiving_tds
    d["order"] = d.season * 100 + d.week
    d["pkey"] = d.player_display_name.map(pname)
    return d


def _ewm_prior(g, col, hl=HL):
    """EWMA of col using only rows before each row (shifted)."""
    return g[col].transform(lambda s: s.shift(1).ewm(halflife=hl, min_periods=1).mean())


def team_table(d, games):
    t = d.groupby(["season", "week", "order", "game_id", "team", "opponent_team"], as_index=False).agg(
        pass_att=("attempts", "sum"), carries=("carries", "sum"), targets=("targets", "sum"),
        rec_yds=("receiving_yards", "sum"), rush_yds=("rushing_yards", "sum"), pass_yds=("passing_yards", "sum"),
        rec=("receptions", "sum"), tds=("tds", "sum"))
    t = t.sort_values("order")
    g = t.groupby("team")
    for c in ["pass_att", "carries", "targets"]:
        t[f"e_{c}"] = _ewm_prior(g, c, 6)
    # defense allowed (opponent perspective)
    t["ypt"] = t.rec_yds / t.targets.clip(lower=1); t["ypc"] = t.rush_yds / t.carries.clip(lower=1)
    t["ypa"] = t.pass_yds / t.pass_att.clip(lower=1); t["cr"] = t.rec / t.targets.clip(lower=1)
    gd = t.groupby("opponent_team")
    for c in ["ypt", "ypc", "ypa", "cr", "tds"]:
        t[f"dall_{c}"] = _ewm_prior(gd, c, 6)
    # market context from nflverse schedule (closing spread/total) for training
    gm = games[["game_id", "home_team", "away_team", "spread_line", "total_line"]]
    t = t.merge(gm, on="game_id", how="left")
    home = t.team == t.home_team
    t["exp_margin"] = np.where(home, t.spread_line, -t.spread_line)
    t["implied"] = (t.total_line + t.exp_margin) / 2
    return t


def fit_volume(t):
    m = t.dropna(subset=["e_pass_att", "e_carries", "exp_margin", "implied"])
    m = m[m.order > m.order.min() + 3]
    coefs = {}
    for y in ["pass_att", "carries"]:
        X = np.c_[np.ones(len(m)), m[f"e_{y}"], m.exp_margin, m.implied]
        b, *_ = np.linalg.lstsq(X, m[y].values, rcond=None)
        coefs[y] = b
    return coefs


def player_features(d, t):
    d = d.sort_values("order").copy()
    tt = t[["game_id", "team", "pass_att", "carries", "targets"]].rename(
        columns={"pass_att": "t_att", "carries": "t_car", "targets": "t_tgt"})
    d = d.merge(tt, on=["game_id", "team"], how="left")
    d["tshare"] = d.targets / d.t_tgt.clip(lower=1)
    d["cshare"] = d.carries / d.t_car.clip(lower=1)
    d["ashare"] = d.attempts / d.t_att.clip(lower=1)
    g = d.groupby("player_id")
    for c in ["tshare", "cshare", "ashare", "targets", "carries", "attempts", "receiving_yards", "receptions",
              "rushing_yards", "passing_yards", "passing_tds", "tds"]:
        d[f"e_{c}"] = _ewm_prior(g, c)
    # efficiency sums (cumulative prior, decayed) for shrinkage
    for num, den, nm in [("receiving_yards", "targets", "ypt"), ("receptions", "targets", "cr"),
                         ("rushing_yards", "carries", "ypc"), ("passing_yards", "attempts", "ypa"),
                         ("passing_tds", "attempts", "tdpa"), ("tds", None, "tdr")]:
        if den:
            d[f"s_{num}_{nm}"] = g[num].transform(lambda s: s.shift(1).ewm(halflife=8, min_periods=1).mean())
            d[f"s_{den}_{nm}"] = g[den].transform(lambda s: s.shift(1).ewm(halflife=8, min_periods=1).mean())
    d["n_prior"] = g.cumcount()
    return d


POS_PRIOR = {  # league-ish priors (per opportunity), weights in opportunities
    "ypt": (7.6, 40), "cr": (0.65, 40), "ypc": (4.3, 60), "ypa": (6.6, 150), "tdpa": (0.043, 200)}


def shrunk(row, nm, num, den):
    mu, k = POS_PRIOR[nm]
    n = row.get(f"s_{den}_{nm}"); s = row.get(f"s_{num}_{nm}")
    if n is None or (isinstance(n, float) and math.isnan(n)) or n <= 0:
        return mu
    # decayed means -> approximate with 8-game equivalent counts
    nn, ss = n * 8, s * 8
    return (ss + mu * k) / (nn + k)


def project(row, vol_att, vol_car, dfac):
    """dfac: dict of opponent multipliers (ypt, ypc, ypa, cr)."""
    out = {}
    ts = row["e_tshare"] if not math.isnan(row["e_tshare"]) else 0
    cs = row["e_cshare"] if not math.isnan(row["e_cshare"]) else 0
    as_ = row["e_ashare"] if not math.isnan(row["e_ashare"]) else 0
    tgt = vol_att * 0.954 * ts  # team targets = 0.954 x pass attempts (nflverse 2024-25)
    ypt = shrunk(row, "ypt", "receiving_yards", "targets") * dfac["ypt"]
    cr = min(0.95, shrunk(row, "cr", "receptions", "targets") * dfac["cr"])
    ypc = shrunk(row, "ypc", "rushing_yards", "carries") * dfac["ypc"]
    ypa = shrunk(row, "ypa", "passing_yards", "attempts") * dfac["ypa"]
    tdpa = shrunk(row, "tdpa", "passing_tds", "attempts")
    car = vol_car * cs
    att = vol_att * as_
    out["receiving_yards"] = tgt * ypt
    out["receptions"] = tgt * cr
    out["rushing_yards"] = car * ypc
    out["passing_yards"] = att * ypa
    out["passing_tds"] = att * tdpa
    e_tds = row["e_tds"] if not math.isnan(row["e_tds"]) else 0
    out["tds_mean"] = e_tds * dfac.get("tds", 1.0)
    return out


def dfactors(t_row_def, league):
    f = {}
    for c in ["ypt", "ypc", "ypa", "cr", "tds"]:
        v = t_row_def.get(f"dall_{c}") if t_row_def is not None else None
        f[c] = 1.0 if v is None or (isinstance(v, float) and math.isnan(v)) else 1 + 0.5 * (v / league[c] - 1)
    return f


class RatioDist:
    """Empirical actual/projection ratios by market and projection tercile."""

    def __init__(self):
        self.r = {}

    def fit(self, rows):  # rows: DataFrame with market, proj, actual
        for m, g in rows.groupby("market"):
            g = g[g.proj > 0.05]
            if len(g) < 200:
                continue
            qs = np.quantile(g.proj, [1 / 3, 2 / 3])
            self.r[m] = (qs, [ (g[(g.proj > lo) & (g.proj <= hi)].actual / g[(g.proj > lo) & (g.proj <= hi)].proj).values
                         for lo, hi in ((-1, qs[0]), (qs[0], qs[1]), (qs[1], 1e9))])

    def p_over(self, market, proj, line):
        if market not in self.r or proj <= 0.05:
            return None
        qs, arrs = self.r[market]
        i = 0 if proj <= qs[0] else (1 if proj <= qs[1] else 2)
        a = arrs[i] * proj
        over = (a > line).mean(); push = (a == line).mean()
        return float(over / max(1 - push, 1e-9))


def poisson_p_over(mu, line):
    k = math.floor(line)
    cdf = sum(math.exp(-mu) * mu ** i / math.factorial(i) for i in range(k + 1))
    return 1 - cdf


def proj_rows(pf, t, coefs, mask, league):
    """Pre-game projections for historical player-games (used for fitting ratio distributions and backtests)."""
    tidx = t.set_index(["game_id", "team"])
    R = []
    sub = pf[mask & (pf.n_prior >= 2)]
    for row in sub.itertuples(index=False):
        row = row._asdict()
        try:
            tr = tidx.loc[(row["game_id"], row["team"])]
        except KeyError:
            continue
        if any(pd.isna([tr.e_pass_att, tr.e_carries, tr.exp_margin, tr.implied])):
            continue
        va = float(np.dot(coefs["pass_att"], [1, tr.e_pass_att, tr.exp_margin, tr.implied]))
        vc = float(np.dot(coefs["carries"], [1, tr.e_carries, tr.exp_margin, tr.implied]))
        df = dfactors(tr.to_dict(), league)
        p = project(row, va, vc, df)
        base = dict(player=row["player_display_name"], pkey=row["pkey"], pos=row["position"], season=row["season"],
                    week=row["week"], team=row["team"], game_id=row["game_id"])
        for m in ["receiving_yards", "receptions", "rushing_yards", "passing_yards", "passing_tds"]:
            naive = row[f"e_{m}"]
            if p[m] <= 0.05 and (pd.isna(naive) or naive <= 0.05):
                continue
            R.append(dict(base, market=m, proj=p[m], naive=naive, actual=row[m]))
        R.append(dict(base, market="anytime_td", proj=p["tds_mean"], naive=row["e_tds"], actual=row["anytime_td"]))
    return pd.DataFrame(R)
