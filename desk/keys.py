"""KEYS role: empirical outcome distributions conditional on the market line.

For a market center c (expected home margin, or expected total), the pmf of the
integer outcome is a kernel-weighted empirical pmf of historical outcomes whose
closing line was near c (adaptive bandwidth, effective n >= NMIN), mixed 85/15
with a discretized normal for smoothness. Because it uses raw outcomes, the
NFL key numbers (3, 7, 6, 10, 14 ...) come straight from the data.

anchor(): finds the center c* at which the model reproduces a sharp no-vig
cover probability at the sharp line. Any other line (DK/Bovada, teased line,
moneyline) is then priced at c*.
"""
import csv, math, os
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = os.path.join(ROOT, "data", "history")
SIG = {"nfl_margin": 13.5, "cfb_margin": 15.5, "nfl_total": 13.5, "cfb_total": 16.5}
NMIN = 400


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_rows(kind, max_season=None, min_season=None):
    """Return arrays (line, outcome, season). Lines in 'expected value' form:
    margin kinds -> expected HOME margin (positive = home favored)."""
    L, Y, S = [], [], []
    if kind.startswith("nfl"):
        for r in csv.DictReader(open(os.path.join(H, "nfl_games.csv"))):
            s = int(r["season"])
            if r["home_score"] in ("", "NA"):
                continue
            if kind == "nfl_margin":
                l, y = _f(r["spread_line"]), _f(r["result"])
            else:
                l, y = _f(r["total_line"]), _f(r["total"])
            if l is None or y is None:
                continue
            L.append(l); Y.append(y); S.append(s)
    else:
        for yr in range(2022, 2027):
            p = os.path.join(H, f"cfb_{yr}.csv")
            if not os.path.exists(p):
                continue
            for r in csv.DictReader(open(p)):
                hs, as_ = _f(r["home_score"]), _f(r["away_score"])
                if hs is None or as_ is None or str(r.get("completed")) not in ("1", "True", "true", "1.0"):
                    continue
                if kind == "cfb_margin":
                    sp = _f(r["close_spread"])
                    if sp is None:
                        continue
                    l, y = -sp, hs - as_
                else:
                    l, y = _f(r["close_total"]), hs + as_
                    if l is None:
                        continue
                L.append(l); Y.append(y); S.append(int(r["season"]))
    L, Y, S = map(np.array, (L, Y, S))
    m = np.ones(len(L), bool)
    if max_season is not None:
        m &= S <= max_season
    if min_season is not None:
        m &= S >= min_season
    return L[m], Y[m], S[m]


class Dist:
    def __init__(self, kind, max_season=None, min_season=None, mix=0.15):
        self.kind = kind
        self.L, self.Y, _ = load_rows(kind, max_season, min_season)
        self.sig = SIG[kind]
        self.mix = mix
        lo = int(self.Y.min()) - 40 if kind.endswith("margin") else 0
        hi = int(self.Y.max()) + 40
        self.grid = np.arange(lo, hi + 1)
        self._cache = {}

    def pmf(self, c):
        key = round(c, 2)
        if key in self._cache:
            return self._cache[key]
        bw = 0.5
        while True:
            w = np.exp(-0.5 * ((self.L - c) / bw) ** 2)
            neff = w.sum() ** 2 / max((w ** 2).sum(), 1e-12)
            if neff >= NMIN or bw > 8:
                break
            bw *= 1.25
        # shift each outcome by (c - its line) only for the fractional remainder that
        # keeps integer outcomes: we keep raw outcomes (key numbers) and correct the mean below
        idx = (self.Y - self.grid[0]).astype(int)
        emp = np.bincount(idx, weights=w, minlength=len(self.grid)).astype(float)
        emp /= emp.sum()
        # mean correction: move mass by integer shift of the weighted-mean gap (rounded)
        gap = c - float((self.L * w).sum() / w.sum())
        sh = int(round(gap))
        if sh:
            emp = np.roll(emp, sh)
        z = (self.grid + 0.5 - c) / self.sig
        zc = (self.grid - 0.5 - c) / self.sig
        nrm = 0.5 * (np.vectorize(math.erf)(z / math.sqrt(2)) - np.vectorize(math.erf)(zc / math.sqrt(2)))
        nrm /= nrm.sum()
        p = (1 - self.mix) * emp + self.mix * nrm
        self._cache[key] = p
        return p

    # threshold form: "outcome > t wins, == t pushes"
    def probs(self, c, t):
        p = self.pmf(c)
        win = p[self.grid > t].sum()
        push = p[self.grid == t].sum() if float(t).is_integer() else 0.0
        return win, push, 1 - win - push

    def cond_over(self, c, t):
        w, pu, l = self.probs(c, t)
        return w / max(w + l, 1e-12)

    def anchor(self, t, q_over):
        """Center c* so that P(outcome > t | no push) == q_over (sharp no-vig)."""
        lo, hi = t - 25, t + 25
        for _ in range(40):
            mid = (lo + hi) / 2
            if self.cond_over(mid, t) < q_over:
                lo = mid
            else:
                hi = mid
        return round((lo + hi) / 2, 2)


def ev(win, push, loss, american):
    d = american / 100 if american > 0 else 100 / -american
    return win * d - loss
