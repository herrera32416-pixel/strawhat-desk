"""NBA market-anchored possession simulator (INFO ONLY), 1,000 sims per game.

Each sim: both teams get N possessions, N ~ Normal(N0, sd_N) (league possession spread from box scores). Every
possession ends in 0/2/3 points from a field goal, or a free-throw trip worth Binomial(2, FT%) points; the 2/3-point
make rates are scaled so the team's expected points hit its target. A per-game team-level shock (sd fitted so the
sim's margin/total spread matches the historical residual spread around the close) captures shooting nights.
Ties go to 5-minute overtimes (N*5/48 possessions each) until decided.
Market anchoring: the home margin center and the total center are solved (bisection, common random numbers) so that
P(home covers the market spread | no push) and P(over | no push) equal the de-vigged market. Matchup leans then shift
the centers (points). Base rates come from data/nba/team_games.csv.gz (calibrate())."""
import json, os
import numpy as np
from scipy.special import ndtr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARAMS = os.path.join(ROOT, "data", "nba", "sim_params.json")


def calibrate(T, G, seasons):
    """League possession mix + dispersion from past seasons only."""
    t = T[T.season.isin(seasons)]
    poss = 0.5 * ((t.fga - t.orb + t.tov + 0.44 * t.fta) + (t.o_fga - t.o_orb + t.o_tov + 0.44 * t.o_fta))
    reg = t.periods == 4
    p = dict(p3=float((t.tpm / poss).mean()), p2=float(((t.fgm - t.tpm) / poss).mean()), pft=float((0.44 * t.fta / poss).mean()),
             ft=float(t.ftm.sum() / t.fta.sum()), N0=float(poss[reg].mean()), sdN=float(poss[reg].groupby(t.espn_id[reg]).first().std()))
    g = G[G.season.isin(seasons)].dropna(subset=["spread_home", "total"])
    p["sd_margin_emp"] = float((g.home_score - g.away_score + g.spread_home).std())
    p["sd_total_emp"] = float((g.home_score + g.away_score - g.total).std())
    # independent possessions overstate the margin spread, so fit the between-team possession correlation rho to the
    # empirical margin SD, then add a shared total shock for the remaining total spread
    c0 = 2 * p["N0"] * (2 * p["p2"] + 3 * p["p3"] + 2 * p["pft"] * p["ft"])
    lo, hi = 0.0, 0.9
    for _ in range(14):
        p["rho"] = (lo + hi) / 2
        m, tt = Sim(p, shock_m=0.0, shock_t=0.0, n=4000, seed=1).run(0.0, c0)
        lo, hi = (p["rho"], hi) if np.std(m) > p["sd_margin_emp"] else (lo, p["rho"])
    p["rho"] = (lo + hi) / 2
    m, tt = Sim(p, shock_m=0.0, shock_t=0.0, n=4000, seed=1).run(0.0, c0)
    p["sd_margin_poss"], p["sd_total_poss"] = float(np.std(m)), float(np.std(tt))
    p["shock_m"] = float(np.sqrt(max(p["sd_margin_emp"] ** 2 - p["sd_margin_poss"] ** 2, 0)))
    p["shock_t"] = float(np.sqrt(max(p["sd_total_emp"] ** 2 - p["sd_total_poss"] ** 2, 0)))
    p["seasons"] = [int(s) for s in seasons]
    return p


class Sim:
    def __init__(self, p, shock_m=None, shock_t=None, n=1000, seed=0):
        self.p, self.n = p, n
        self.sm = p.get("shock_m", 0.0) if shock_m is None else shock_m
        self.st = p.get("shock_t", 0.0) if shock_t is None else shock_t
        rng = np.random.default_rng(seed)
        self.Nmax = int(p["N0"] + 5 * p["sdN"]) + 40
        self.N = np.clip(np.round(rng.normal(p["N0"], p["sdN"], n)), 70, self.Nmax - 40).astype(int)
        rho = p.get("rho", 0.0)   # per-possession outcome correlation between the two teams (game flow / pace / whistle)
        z0, z1 = rng.normal(size=(n, self.Nmax)), rng.normal(size=(n, self.Nmax))
        self.U = np.stack([ndtr(z0), ndtr(rho * z0 + np.sqrt(1 - rho ** 2) * z1)])
        self.Uft = rng.random((2, n, self.Nmax, 2))
        self.Z = rng.normal(size=(2, n))

    def _team(self, k, target):
        """target expected points per team per game, shape (n,) -> points (n,) for regulation + OT tail possessions."""
        p = self.p
        ftpts = 2 * p["pft"] * p["ft"]
        c = np.clip((target / self.N - ftpts) / (2 * p["p2"] + 3 * p["p3"]), 0.2, 3.0)
        p3, p2 = p["p3"] * c, p["p2"] * c
        u = self.U[k]
        is3 = u < p3[:, None]
        is2 = (u >= p3[:, None]) & (u < (p3 + p2)[:, None])
        isft = (u >= (p3 + p2)[:, None]) & (u < (p3 + p2 + p["pft"])[:, None])
        ftm = (self.Uft[k] < p["ft"]).sum(-1)
        pts = 3 * is3 + 2 * is2 + isft * ftm
        cs = np.cumsum(pts, 1)
        return cs

    def run(self, center_m, center_t):
        """Returns (margin, total) arrays of the n sims, home perspective, OT included."""
        cm = center_m + self.sm * self.Z[0]
        ct = center_t + self.st * self.Z[1]
        H, A = self._team(0, (ct + cm) / 2), self._team(1, (ct - cm) / 2)
        idx = np.arange(self.n)
        h, a = H[idx, self.N - 1].astype(float), A[idx, self.N - 1].astype(float)
        n_ot = np.maximum(np.round(self.N * 5 / 48).astype(int), 1)
        end = self.N.copy()
        for _ in range(6):   # up to 6 overtimes
            tie = h == a
            if not tie.any():
                break
            new_end = np.minimum(end + n_ot, self.Nmax - 1)
            h = np.where(tie, H[idx, new_end - 1], h); a = np.where(tie, A[idx, new_end - 1], a)
            end = np.where(tie, new_end, end)
        return h - a, h + a

    def anchor(self, spread_home, q_cover, total, q_over, iters=24):
        """Solve centers so P(margin + spread > 0 | no push) = q_cover and P(total > line | no push) = q_over."""
        cm, ct = -spread_home, total
        for _ in range(2):
            lo, hi = cm - 15, cm + 15
            for _ in range(iters):
                mid = (lo + hi) / 2
                m, _t = self.run(mid, ct)
                pc = _cond(m + spread_home)
                lo, hi = (lo, mid) if pc > q_cover else (mid, hi)
            cm = (lo + hi) / 2
            lo, hi = ct - 25, ct + 25
            for _ in range(iters):
                mid = (lo + hi) / 2
                _m, tt = self.run(cm, mid)
                po = _cond(tt - total)
                lo, hi = (lo, mid) if po > q_over else (mid, hi)
            ct = (lo + hi) / 2
        return cm, ct


def _cond(x):
    w, l = (x > 0).sum(), (x < 0).sum()
    return w / max(w + l, 1)


def summarize(m, t, spread_home, total):
    h = (t + m) / 2; a = (t - m) / 2
    pct = lambda x, q: float(np.percentile(x, q))
    return dict(p_home_win=float((m > 0).mean()), p_home_cover=_cond(m + spread_home), p_over=_cond(t - total),
                p_push_spread=float((m + spread_home == 0).mean()), p_push_total=float((t == total).mean()),
                p_ot=None, home_pts=[pct(h, 10), pct(h, 50), pct(h, 90)], away_pts=[pct(a, 10), pct(a, 50), pct(a, 90)],
                margin=[pct(m, 10), pct(m, 50), pct(m, 90)], total=[pct(t, 10), pct(t, 50), pct(t, 90)],
                exp_margin=float(m.mean()), exp_total=float(t.mean()))


def load_params():
    return json.load(open(PARAMS))
