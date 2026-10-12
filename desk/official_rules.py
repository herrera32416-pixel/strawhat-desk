"""Official-book gate (Luis, 2026-10-12). Config: data/official_rules.json.
Candidate dict keys: sport (NFL/CFB/MLB/...), market (ml/spread/total/f5.../teaser/parlay/anytime_td),
side, line, price_american, model_pct (0-100, market-based fair), edge_pp, source (optional), units (default 1).
check() -> (ok, reason). apply_day() -> (kept, rejected) with the daily cap."""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_PATH = os.path.join(ROOT, "data", "official_rules.json")


def load(path=CFG_PATH):
    with open(path) as f:
        return json.load(f)


def _is_fav(c):
    m, line, price = c.get("market", ""), c.get("line"), c.get("price_american")
    if "spread" in m and line is not None:
        return float(line) < 0
    return price is not None and price < 0


def _check_one(c, cfg):
    return _check_one_skip(dict(c, _skip=()), cfg)


def _mf(c, cfg, v):
    """Model-% floor; dropped for market-only candidates (model% there is just the consensus no-vig)."""
    if c.get("source") == "market_only" and cfg.get("market_only", {}).get("drop_model_floors"):
        return float("-inf")
    return v


def _r(f):
    _RULES.append(f); return f


_RULES = []


def _norm(c):
    return ((c.get("sport") or "").upper().replace("NCAAF", "CFB"), (c.get("market") or "").lower(),
            (c.get("source") or "").lower(), (c.get("side") or "").lower(),
            c.get("price_american"), c.get("edge_pp"), c.get("model_pct"))


@_r
def r_source(c, cfg):
    src = _norm(c)[2]
    if src and any(b in src for b in cfg["blocked_sources"]):
        return f"source '{src}' is info only (sim never drives official picks)"


@_r
def r_market(c, cfg):
    mkt = _norm(c)[1]
    if any(b in mkt for b in cfg["blocked_markets"]) or c.get("legs"):
        return f"market '{mkt}' not allowed in official book (no teasers/parlays/ATD)"


@_r
def r_missing(c, cfg):
    _, _, _, _, p, e, m = _norm(c)
    if e is None or m is None or p is None:
        return "missing market-based edge/model/price"


@_r
def r_edge(c, cfg):
    e = c["edge_pp"]
    if e < cfg["edge_min_pp"]:
        return f"edge {e:+.1f}pp < {cfg['edge_min_pp']}pp"


@_r
def r_longshot(c, cfg):
    if "ml" in _norm(c)[1] and c["price_american"] > cfg["longshot_ml_max_plus"]:
        return f"long-shot ML +{c['price_american']} > +{cfg['longshot_ml_max_plus']}"


@_r
def r_cfb_key(c, cfg):
    sp, mkt = _norm(c)[:2]
    k = cfg["cfb"]; line = c.get("line")
    if sp == "CFB" and _is_fav(c) and line is not None and "spread" in mkt and \
            any(abs(abs(float(line)) - n) <= k["key_band"] for n in k["key_numbers"]):
        return f"CFB favorite {line} near key number 3/7/10"


@_r
def r_cfb_fav(c, cfg):
    k = cfg["cfb"]
    if _norm(c)[0] == "CFB" and _is_fav(c) and (c["edge_pp"] < k["fav_edge_min_pp"] or c["model_pct"] < _mf(c, cfg, k["fav_model_min_pct"])):
        return f"CFB favorite needs edge>={k['fav_edge_min_pp']} & model>={k['fav_model_min_pct']} (dogs-first)"


@_r
def r_nfl(c, cfg):
    k = cfg["nfl"]
    if _norm(c)[0] == "NFL" and (c["edge_pp"] < k["edge_min_pp"] or c["model_pct"] < _mf(c, cfg, k["model_min_pct"])):
        return f"NFL needs edge>={k['edge_min_pp']} & model>={k['model_min_pct']}"


@_r
def r_mlb_rl(c, cfg):
    sp, mkt = _norm(c)[:2]
    if sp == "MLB" and "spread" in mkt and "f5" not in mkt:
        return "MLB run line not in official book"


@_r
def r_mlb_f5(c, cfg):
    sp, mkt = _norm(c)[:2]
    if sp == "MLB" and "f5" in mkt and c["price_american"] <= cfg["mlb"]["f5_price_floor"]:
        return f"MLB F5 price {c['price_american']} not better than {cfg['mlb']['f5_price_floor']}"


@_r
def r_mlb_plus(c, cfg):
    sp, mkt = _norm(c)[:2]; k = cfg["mlb"]
    if sp == "MLB" and mkt == "ml" and c["price_american"] > 0 and \
            (c["model_pct"] < _mf(c, cfg, k["plus_ml_model_min_pct"]) or c["edge_pp"] < k["plus_ml_edge_min_pp"]):
        return f"MLB plus-money ML needs model>={k['plus_ml_model_min_pct']} & edge>={k['plus_ml_edge_min_pp']}"


@_r
def r_mlb_under(c, cfg):
    sp, mkt, _, side = _norm(c)[:4]; k = cfg["mlb"]
    if sp == "MLB" and "total" in mkt and side == "under" and \
            (c["edge_pp"] < k["under_edge_min_pp"] or c["model_pct"] < _mf(c, cfg, k["under_model_min_pct"])):
        return "MLB thin under dropped"


def apply_day(cands, cfg=None, already_count=0, already_units=0.0):
    """Filter, rank by edge, and cap the day's official bets. Returns (kept, rejected[(cand, reason)])."""
    cfg = cfg or load()
    ok, rej = [], []
    for c in cands:
        good, why = check(c, cfg)
        (ok.append(c) if good else rej.append((c, why)))
    ok.sort(key=lambda c: -(c.get("edge_pp") or 0))
    kept, n, u = [], already_count, already_units
    for c in ok:
        cu = float(c.get("units") or 1)
        if n >= cfg["daily_max_bets"] or u + cu > cfg["daily_max_units"]:
            rej.append((c, f"daily cap ({cfg['daily_max_bets']} bets / {cfg['daily_max_units']}u) reached"))
            continue
        kept.append(c); n += 1; u += cu
    return kept, rej


def clv_pp(stamp_price, close_price):
    """Closing-line value in implied-probability pp (positive = beat the close)."""
    def imp(a):
        return 100 / (a + 100) if a > 0 else -a / (-a + 100)
    if stamp_price is None or close_price is None:
        return None
    return round(100 * (imp(close_price) - imp(stamp_price)), 2)


HARD = ("info only", "not allowed in official book", "long-shot ML", "missing market-based")


def violations(c, cfg):
    """All rule misses for one candidate (each rule checked independently; stops at a hard block)."""
    out = []
    for rule in _RULES:
        r = rule(c, cfg)
        if r:
            out.append(r)
            if any(h in r for h in HARD):
                return out
    g = c.get("gap_pp")
    if g is not None and abs(g) > cfg.get("gap_max_pp", 8.0):
        out.append(f"model-vs-market gap {g:+.1f}pp > {cfg.get('gap_max_pp', 8.0)}pp (stale/odd line)")
    return out


def _check_one_skip(c, cfg):
    skip = c.get("_skip", ())
    for rule in _RULES:
        r = rule(c, cfg)
        if r and r not in skip:
            return False, r
    return True, "ok"


def check(c, cfg):
    v = violations(c, cfg)
    return (not v, v[0] if v else "ok")


def is_coinflip(c, cfg):
    k = cfg.get("grade_c", {})
    e, m = c.get("edge_pp"), c.get("model_pct")
    if e is None or m is None or e < k.get("edge_lt_pp", 1.5):
        return True
    if c.get("source") == "market_only":  # market % near 50 is normal for spreads/totals; edge alone decides
        return False
    return abs(m - 50) < k.get("model_within_pp_of_50", 2.0)


def grade_day(cands, cfg=None, already_a=0, already_a_units=0.0):
    """A = passes every rule and fits the daily cap (bettable card). B = misses exactly one rule
    (a cap overflow counts as that one miss). C = everything else: lean / near coin-flip / hard-blocked, board only.
    Sets c['grade'], c['grade_reasons']; returns the list."""
    cfg = cfg or load()
    pool = []
    for c in cands:
        v = violations(c, cfg)
        c["grade_reasons"] = v
        if any(any(h in x for h in HARD) for x in v) or is_coinflip(c, cfg) or len(v) >= 2:
            c["grade"] = "C"
        elif len(v) == 1:
            c["grade"] = "B"
        else:
            pool.append(c)
    pool.sort(key=lambda c: -(c.get("edge_pp") or 0))
    n, u = already_a, already_a_units
    for c in pool:
        cu = float(c.get("units") or 1)
        if n >= cfg["daily_max_bets"] or u + cu > cfg["daily_max_units"]:
            c["grade"], c["grade_reasons"] = "B", [f"daily A cap ({cfg['daily_max_bets']} bets / {cfg['daily_max_units']}u) reached"]
        else:
            c["grade"] = "A"; n += 1; u += cu
    return cands
