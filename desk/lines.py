"""LINES role: pull game odds (NFL daily; NCAAF when FBS games are within 36h), store raw JSON.
Free calls (0 credits): /events. Paid: /odds us+eu x h2h,spreads,totals = 6 credits per sport."""
import datetime as dt, json, os, gzip
from zoneinfo import ZoneInfo
from . import toa

CT = ZoneInfo("America/Chicago")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
SPORTS = {"nfl": "americanfootball_nfl", "cfb": "americanfootball_ncaaf"}


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def events(sport):
    d, _ = toa.get(f"/v4/sports/{SPORTS[sport]}/events", {}, 0, f"events {sport}")
    return d


def pull_odds(sport, stamp):
    d, row = toa.get(f"/v4/sports/{SPORTS[sport]}/odds",
                     {"regions": "us,eu", "markets": "h2h,spreads,totals", "oddsFormat": "american"}, 6, f"odds {sport}")
    os.makedirs(os.path.join(RAW, "odds"), exist_ok=True)
    p = os.path.join(RAW, "odds", f"{sport}_{stamp}.json.gz")
    json.dump({"pulled_ct": dt.datetime.now(CT).isoformat(timespec="seconds"), "credits": row, "data": d}, gzip.open(p, "wt"))
    return d, p


def latest(sport):
    dd = os.path.join(RAW, "odds")
    if not os.path.isdir(dd):
        return None, None
    fs = sorted(f for f in os.listdir(dd) if f.startswith(sport + "_"))
    if not fs:
        return None, None
    p = os.path.join(dd, fs[-1])
    j = json.load(gzip.open(p))
    return j, p


def run(stamp):
    """Decide what to pull. NFL: always (if any game in next 8 days). NCAAF: if any event within 36h."""
    pulled = {}
    for sport in ("nfl", "cfb"):
        ev = events(sport)
        horizon = 8 * 24 if sport == "nfl" else 36
        soon = [e for e in ev if 0 < (dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) - now_utc()).total_seconds() / 3600 <= horizon]
        if not soon:
            pulled[sport] = "skipped (no games in window)"
            continue
        try:
            d, p = pull_odds(sport, stamp)
            pulled[sport] = p
        except toa.BudgetError as e:
            pulled[sport] = f"skipped: {e}"
    return pulled
