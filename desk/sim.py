"""Game SIMULATOR (NFL + FBS): possession-level Monte Carlo anchored to the market.

1. Baseline = the market. Expected home margin c and expected total T are the KEYS centers at which the
   de-vigged closing/current odds are reproduced (Dist.anchor), i.e. the sim starts exactly at the market.
2. Matchup adjustments, all shrunk:
   - means: c += spread lean, T += total lean from the matchup residual model (desk/matchup*.py). Those leans map
     the unit gaps (pass rush vs OL, run O vs run D, pass O vs coverage, explosives, red zone, interactions,
     similar foes, common opponents) to points with ridge shrinkage chosen by season-out CV.
   - red zone: each offense's TD share of scoring drives moves by 0.5 x (its expected red-zone TD rate vs this
     defense - league mean) (shrunk by half).
   - pace: drives per team x (1 + 0.02 x mean early-down-pass-rate z of the two offenses).
3. Each team gets N drives (shared count, small noise). Each drive is TD / FG / nothing; TD = 7 (6 after a missed
   PAT or failed 2-pt, 8 after a 2-pt), FG = 3, so margins land on 3/7/10/14 like real games. Per-drive TD and FG
   probabilities are solved so the team's expected points equal its market-implied mean. Ties go to OT (NFL +3,
   CFB +7 to a coin-flip winner).
4. Key numbers: a pure drive model under-produces real key-number mass (NFL |margin|=3: ~11% vs ~15% in real
   games, because of end-game FG/2-pt decisions). So the 1,000 sims are RAKED (iterative proportional weights) to
   the KEYS margin pmf and total pmf at the adjusted centers. Margins and totals then respect key numbers, and each
   simulated game keeps consistent team scores; all outputs are weighted (n_eff reported).
Constants were measured on seasons BEFORE every backtest window (NFL pbp 2015-17, CFB pbp 2021-23):
   NFL 11.6 drives/team, TD share 0.585, TD points 7/6/8 = .87/.09/.04; resid sd check 13.4 (sim ~13.4).
   CFB 12.15 drives/team, TD share 0.73, TD points .92/.05/.03; resid sd check 15.3 (sim ~15.2).
INFO ONLY unless backtest/sim_bt.py passes its pre-registered criteria (team/SIM.md)."""
import math
import numpy as np

P = {"nfl": dict(N=11.6, N_sd=0.5, td_share=0.585, td_pts=(7, 6, 8), td_p=(0.87, 0.09, 0.04), ot=3),
     "cfb": dict(N=12.15, N_sd=0.6, td_share=0.73, td_pts=(7, 6, 8), td_p=(0.92, 0.05, 0.03), ot=7)}
RZ_SHRINK, PACE_K = 0.5, 0.02


def devig(a, b):
    def imp(x):
        if x is None or (isinstance(x, float) and math.isnan(x)):
            x = -110
        return 100 / (x + 100) if x > 0 else -x / (-x + 100)
    pa, pb = imp(a), imp(b)
    return pa / (pa + pb)


def _drive_probs(mu, n, s, e_td):
    e = max(mu, 0.5) / n
    pt = e / (e_td + 3 * (1 - s) / s)
    pf = pt * (1 - s) / s
    tot = pt + pf
    if tot > 0.95:
        pt, pf = pt * 0.95 / tot, pf * 0.95 / tot
    return pt, pf


def simulate(mu_h, mu_a, sport, S=1000, rng=None, s_h=None, s_a=None, pace_z=0.0):
    """Return (home_pts, away_pts) arrays of length S."""
    p = P[sport]; rng = rng or np.random.default_rng()
    e_td = float(np.dot(p["td_pts"], p["td_p"]))
    n_mean = p["N"] * (1 + PACE_K * pace_z)
    N = np.clip(np.rint(rng.normal(n_mean, p["N_sd"], S)), 6, 22).astype(int)
    out = []
    for mu, sh in ((mu_h, s_h), (mu_a, s_a)):
        s = min(max(sh if sh is not None else p["td_share"], 0.35), 0.9)
        pt, pf = _drive_probs(mu, n_mean, s, e_td)
        u = rng.random((S, 22))
        mask = np.arange(22)[None, :] < N[:, None]
        td = (u < pt) & mask
        fg = (u >= pt) & (u < pt + pf) & mask
        tdp = rng.choice(p["td_pts"], size=(S, 22), p=p["td_p"])
        out.append((td * tdp).sum(1) + 3 * fg.sum(1))
    hs, as_ = out
    tie = hs == as_
    if tie.any():
        coin = rng.random(S) < 0.5
        hs = hs + np.where(tie & coin, p["ot"], 0); as_ = as_ + np.where(tie & ~coin, p["ot"], 0)
    return hs, as_


def rake(m, t, pm, gm, pt_, gt, iters=6):
    """Weights so the weighted margin/total distributions match target pmfs (on values present in the sample)."""
    w = np.ones(len(m))
    for _ in range(iters):
        for x, pmf, grid in ((m, pm, gm), (t, pt_, gt)):
            vals, inv = np.unique(x, return_inverse=True)
            tgt = np.interp(vals, grid, pmf, left=0, right=0)
            if tgt.sum() <= 0:
                continue
            tgt = tgt / tgt.sum()
            cur = np.bincount(inv, weights=w) / w.sum()
            ratio = np.where(cur > 0, tgt / np.maximum(cur, 1e-12), 0)
            w = w * ratio[inv]
    return w / w.sum()


def wq(x, w, q):
    o = np.argsort(x); cw = np.cumsum(w[o])
    return float(x[o][min(np.searchsorted(cw, q), len(x) - 1)])


def adjusted_inputs(c, T, f=None, lean_s=0.0, lean_t=0.0):
    """Market centers + shrunk matchup adjustments -> (mu_home, mu_away, td_share_h, td_share_a, pace_z)."""
    c2, T2 = c + (lean_s or 0.0), T + (lean_t or 0.0)
    mu_h, mu_a = (T2 + c2) / 2, (T2 - c2) / 2
    s_h = s_a = None; pz = 0.0
    if f:
        if f.get("rz_home") is not None and f.get("rz_mu") is not None:
            s_h = RZ_SHRINK * (f["rz_home"] - f["rz_mu"]); s_a = RZ_SHRINK * (f["rz_away"] - f["rz_mu"])
        pz = f.get("pace_z") or 0.0
    return mu_h, mu_a, s_h, s_a, pz


def run_game(sport, spread_line, total_line, D_m, D_t, f=None, lean_s=0.0, lean_t=0.0, q_cover=0.5, q_over=0.5,
             S=1000, rng=None, rake_keys=True):
    """spread_line = expected home margin per the market (nflverse convention). Returns summary dict."""
    p = P[sport]
    c = D_m.anchor(spread_line, q_cover) if spread_line is not None else 0.0
    T = D_t.anchor(total_line, q_over) if total_line is not None else (44.0 if sport == "nfl" else 55.0)
    mu_h, mu_a, dsh, dsa, pz = adjusted_inputs(c, T, f, lean_s, lean_t)
    s_h = None if dsh is None else p["td_share"] + dsh
    s_a = None if dsa is None else p["td_share"] + dsa
    hs, as_ = simulate(mu_h, mu_a, sport, S, rng, s_h, s_a, pz)
    m, t = hs - as_, hs + as_
    W = rake(m, t, D_m.pmf(mu_h - mu_a), D_m.grid, D_t.pmf(mu_h + mu_a), D_t.grid) if rake_keys else np.full(S, 1 / S)
    E = lambda b: float((W * b).sum())
    r = dict(n_sims=int(S), n_eff=round(float(1 / (W ** 2).sum()), 1), home_win=E(m > 0),
             home_pts_median=wq(hs, W, 0.5), away_pts_median=wq(as_, W, 0.5),
             home_pts_10_90=[wq(hs, W, 0.1), wq(hs, W, 0.9)], away_pts_10_90=[wq(as_, W, 0.1), wq(as_, W, 0.9)],
             margin_10_90=[wq(m, W, 0.1), wq(m, W, 0.9)], total_10_90=[wq(t, W, 0.1), wq(t, W, 0.9)],
             p_margin_3=E(np.abs(m) == 3), p_margin_7=E(np.abs(m) == 7),
             mu_home=round(mu_h, 2), mu_away=round(mu_a, 2), market_center=round(c, 2), market_total_center=round(T, 2))
    if spread_line is not None:
        w, pu = E(m > spread_line), E(m == spread_line)
        r.update(home_cover=w, cover_push=pu, home_cover_ex_push=w / max(1 - pu, 1e-9))
    if total_line is not None:
        o, pu = E(t > total_line), E(t == total_line)
        r.update(over=o, total_push=pu, over_ex_push=o / max(1 - pu, 1e-9))
    return r
