"""NHL market-anchored score simulator (INFO ONLY).

Regulation: independent Poisson goals (lam_h, lam_a) with draw inflation theta on tied regulation scores
(the box research rejected bivariate Poisson / negative binomial for NHL: home/away goal correlation -0.098,
dispersion 0.976, research/nhl-2026-10/sim/SIM_NHL.md; a bivariate-Poisson covariance term would be <= 0).
Empty net (late, trailing team pulls the goalie): from a 1-goal regulation lead the leader adds an EN goal with
prob e1 or the trailer ties it (-> OT) with prob t1; from a 2-goal lead the leader adds one with prob e2.
OT: sudden-death 3v3, decided by a goal with prob g (else shootout). OT goal goes to home with prob
0.5 + 0.5*(lam_h/(lam_h+lam_a) - 0.5); shootout 50/50. The OT/SO winner gets +1 goal (book settlement).
theta, e1, t1, e2, g are fitted on past seasons only (fit_params). The exact joint pmf of final scores is computed
on a grid; `simulate()` draws 1,000 Monte Carlo games from it for the site."""
import numpy as np

G = 13            # regulation goals 0..12 per team
K = G + 2         # final-score grid (EN +1, OT/SO +1)
DEFAULT = dict(theta=1.5, e1=0.35, t1=0.08, e2=0.12, g=0.62)

_x, _y = np.meshgrid(np.arange(K), np.arange(K), indexing="ij")
MARG = (_x - _y).ravel()
TOT = (_x + _y).ravel()


def _pois(lam):
    k = np.arange(G)
    lf = np.cumsum(np.r_[0, np.log(np.arange(1, G))])
    return np.exp(k[None, :] * np.log(lam[:, None]) - lam[:, None] - lf[None, :])


def final_joint(lh, la, P=DEFAULT):
    """Exact joint pmf of final (home, away) goals, shape (n, K, K)."""
    lh, la = np.atleast_1d(np.asarray(lh, float)), np.atleast_1d(np.asarray(la, float))
    n = len(lh)
    J = _pois(lh)[:, :, None] * _pois(la)[:, None, :]
    d = np.arange(G)
    J[:, d, d] *= P["theta"]
    J /= J.sum((1, 2), keepdims=True)
    R = np.zeros((n, K, K))                # regulation after empty-net overlay
    R[:, :G, :G] += J
    diff = d[:, None] - d[None, :]
    for sgn in (1, -1):
        m1 = (diff == sgn).astype(float)
        m2 = (diff == 2 * sgn).astype(float)
        J1, J2 = J * m1, J * m2
        R[:, :G, :G] -= (P["e1"] + P["t1"]) * J1 + P["e2"] * J2
        if sgn == 1:   # home leads
            R[:, 1:G + 1, :G] += P["e1"] * J1 + P["e2"] * J2   # home EN goal
            R[:, :G, 1:G + 1] += P["t1"] * J1                   # away ties late
        else:
            R[:, :G, 1:G + 1] += P["e1"] * J1 + P["e2"] * J2
            R[:, 1:G + 1, :G] += P["t1"] * J1
    F = R.copy()
    k = np.arange(K - 1)
    tie = R[:, k, k].copy()
    F[:, k, k] = 0
    ph_ot = 0.5 + 0.5 * (lh / (lh + la) - 0.5)
    ph = P["g"] * ph_ot + (1 - P["g"]) * 0.5
    F[:, k + 1, k] += tie * ph[:, None]
    F[:, k, k + 1] += tie * (1 - ph)[:, None]
    return F


def probs(F, pl_home=-1.5, total=None):
    """Return dict of home win, P(home covers pl_home), P(over total | no push), reg-tie prob not needed."""
    f = F.reshape(len(F), -1)
    out = {"p_home": f[:, MARG > 0].sum(1)}
    out["p_home_pl"] = f[:, MARG + pl_home > 0].sum(1)
    if total is not None:
        total = np.broadcast_to(np.asarray(total, float), (len(F),))
        over = (f * (TOT[None, :] > total[:, None])).sum(1)
        push = (f * (TOT[None, :] == total[:, None])).sum(1)
        out["p_over"] = over / np.maximum(1 - push, 1e-12)
        out["p_push_total"] = push
    out["exp_h"] = (f * _x.ravel()).sum(1); out["exp_a"] = (f * _y.ravel()).sum(1)
    return out


def anchor(p_home, total_line, q_over, P=DEFAULT, iters=28):
    """Vectorized: find (lam_h, lam_a) so the model reproduces the de-vigged home-win prob and P(over)."""
    p_home, total_line, q_over = (np.asarray(a, float) for a in (p_home, total_line, q_over))
    n = len(p_home)
    slo, shi = np.full(n, 2.5), np.full(n, 10.0)
    for _ in range(iters):
        S = (slo + shi) / 2
        lh, la = _ratio(S, p_home, P, iters)
        po = probs(final_joint(lh, la, P), total=total_line)["p_over"]
        hi = po > q_over
        shi = np.where(hi, S, shi); slo = np.where(hi, slo, S)
    S = (slo + shi) / 2
    return _ratio(S, p_home, P, iters)


def _ratio(S, p_home, P, iters):
    lo, hi = np.full(len(S), -2.5), np.full(len(S), 2.5)
    for _ in range(iters):
        r = np.exp((lo + hi) / 2)
        lh, la = S * r / (1 + r), S / (1 + r)
        ph = probs(final_joint(lh, la, P))["p_home"]
        up = ph > p_home
        hi = np.where(up, (lo + hi) / 2, hi); lo = np.where(up, lo, (lo + hi) / 2)
    r = np.exp((lo + hi) / 2)
    return S * r / (1 + r), S / (1 + r)


def loglik(F, hg, ag):
    hg, ag = np.minimum(hg, K - 1).astype(int), np.minimum(ag, K - 1).astype(int)
    return np.log(np.maximum(F[np.arange(len(F)), hg, ag], 1e-12))


def fit_params(p_home, total_line, q_over, hg, ag, result_type):
    """Fit theta, e1, t1, e2 (score-grid likelihood) and g (share of tied games decided in OT) on PAST games only."""
    rt = np.asarray(result_type)
    g = float((rt == "OT").sum() / max(((rt == "OT") | (rt == "SO")).sum(), 1))
    best, P = None, dict(DEFAULT, g=g)
    lh, la = anchor(p_home, total_line, q_over, P)
    for it in range(2):
        for th in (1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8):
            for e1 in (0.25, 0.3, 0.35, 0.4, 0.45, 0.5):
                for t1 in (0.04, 0.07, 0.10, 0.13):
                    for e2 in (0.05, 0.1, 0.15, 0.2):
                        Q = dict(theta=th, e1=e1, t1=t1, e2=e2, g=g)
                        ll = loglik(final_joint(lh, la, Q), hg, ag).sum()
                        if best is None or ll > best[0]:
                            best = (ll, Q)
        P = best[1]
        lh, la = anchor(p_home, total_line, q_over, P)
        best = None if it == 0 else best
    return P


def simulate(lh, la, P=DEFAULT, n=1000, seed=0):
    """Monte Carlo: n games drawn from the model's joint final-score pmf. Returns (home goals, away goals) arrays."""
    F = final_joint([lh], [la], P)[0].ravel()
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(F), size=n, p=F / F.sum())
    return _x.ravel()[idx], _y.ravel()[idx]
