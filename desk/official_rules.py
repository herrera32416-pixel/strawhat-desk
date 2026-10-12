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


def check(c, cfg):
    sport = (c.get("sport") or "").upper().replace("NCAAF", "CFB")
    mkt = (c.get("market") or "").lower()
    src = (c.get("source") or "").lower()
    side = (c.get("side") or "").lower()
    price, edge, model = c.get("price_american"), c.get("edge_pp"), c.get("model_pct")
    if src and any(b in src for b in cfg["blocked_sources"]):
        return False, f"source '{src}' is info only (sim never drives official picks)"
    if any(b in mkt for b in cfg["blocked_markets"]) or c.get("legs"):
        return False, f"market '{mkt}' not allowed in official book (no teasers/parlays/ATD)"
    if edge is None or model is None or price is None:
        return False, "missing market-based edge/model/price"
    if edge < cfg["edge_min_pp"]:
        return False, f"edge {edge:+.1f}pp < {cfg['edge_min_pp']}pp"
    if "ml" in mkt and price > cfg["longshot_ml_max_plus"]:
        return False, f"long-shot ML +{price} > +{cfg['longshot_ml_max_plus']}"
    if sport == "CFB":
        k = cfg["cfb"]
        if _is_fav(c):
            line = c.get("line")
            if line is not None and "spread" in mkt and any(abs(abs(float(line)) - n) <= k["key_band"] for n in k["key_numbers"]):
                return False, f"CFB favorite {line} near key number 3/7/10"
            if edge < k["fav_edge_min_pp"] or model < k["fav_model_min_pct"]:
                return False, f"CFB favorite needs edge>={k['fav_edge_min_pp']} & model>={k['fav_model_min_pct']} (dogs-first)"
    elif sport == "NFL":
        k = cfg["nfl"]
        if edge < k["edge_min_pp"] or model < k["model_min_pct"]:
            return False, f"NFL needs edge>={k['edge_min_pp']} & model>={k['model_min_pct']}"
    elif sport == "MLB":
        k = cfg["mlb"]
        if "spread" in mkt and "f5" not in mkt:
            return False, "MLB run line not in official book"
        if "f5" in mkt and price <= k["f5_price_floor"]:
            return False, f"MLB F5 price {price} not better than {k['f5_price_floor']}"
        if mkt in ("ml",) and price > 0 and (model < k["plus_ml_model_min_pct"] or edge < k["plus_ml_edge_min_pp"]):
            return False, f"MLB plus-money ML needs model>={k['plus_ml_model_min_pct']} & edge>={k['plus_ml_edge_min_pp']}"
        if "total" in mkt and side == "under" and (edge < k["under_edge_min_pp"] or model < k["under_model_min_pct"]):
            return False, "MLB thin under dropped"
    return True, "ok"


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
