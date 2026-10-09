"""LINES for NBA / NHL (separate from desk/lines.py). Odds API pulls go through desk/toa.get (logged in
data/credits.jsonl, shared 40/day cap). Rules:
- at most ONE pull per sport per CT day (4 credits: regions us,eu x 2 markets), only if a game starts within 36h;
- the desk's 9am run leaves these 4 credits aside (run.py hook -> reserve_for_pro) on top of its own pre-kick recheck
  reserve, so this pull never eats a recheck; toa.get still refuses anything over the 40/day cap;
- otherwise fall back to the latest saved file (data/raw/odds/<sport>_*.json.gz). Never invents a price."""
import datetime as dt, glob, gzip, json, os, statistics
from zoneinfo import ZoneInfo
from . import toa, market, espn_odds

CT = ZoneInfo("America/Chicago")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw", "odds")
KEYS = {"nhl": ("icehockey_nhl", "h2h,totals"), "nba": ("basketball_nba", "spreads,totals")}
COST = 2 * len(toa.REGIONS.split(","))  # free tier: us only = 2 credits
RECHECK_RESERVE = 12


def spent_label(prefix, day):
    return sum(int(r.get("last") or 0) for r in toa.log_rows() if r.get("day_ct") == day and str(r.get("label", "")).startswith(prefix))


def pull(sport, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    day = now.astimezone(CT).strftime("%Y-%m-%d")
    if spent_label(f"{sport}_odds", day) > 0:
        return "already pulled today"
    key, mk = KEYS[sport]
    try:
        if not os.environ.get("THE_ODDS_API_KEY"):
            raise toa.BudgetError("no key")
        ev, _ = toa.get(f"/v4/sports/{key}/events", {}, 0, f"{sport}_events")
        soon = [e for e in ev if 0 < (dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) - now).total_seconds() / 3600 <= 36]
        if not soon:
            return "no game within 36h (events call is free)"
        data, row = toa.get(f"/v4/sports/{key}/odds", dict(regions=toa.REGIONS, markets=mk, oddsFormat="american"), COST, f"{sport}_odds")
    except toa.BudgetError as e:
        data, row = [], {"skipped": str(e)}
    try:
        data, st = espn_odds.merge(data, espn_odds.fetch(sport.upper(), 2, now))
        row = {**(row or {}), "espn_fallback": st}
    except Exception:  # noqa: BLE001
        pass
    if not data:
        return f"no lines (Odds API: {row.get('skipped', 'empty')}; ESPN empty)"
    os.makedirs(RAW, exist_ok=True)
    stamp = now.astimezone(CT).strftime("%Y%m%d_%H%M")
    json.dump(dict(pulled_ct=now.astimezone(CT).strftime("%a %b %-d %-I:%M %p CT"), credits=row, data=data),
              gzip.open(os.path.join(RAW, f"{sport}_{stamp}.json.gz"), "wt"))
    return f"pulled {len(data)} events ({row.get('last')} credits)"


def latest_today(sport, day):
    return bool(glob.glob(os.path.join(RAW, f"{sport}_{day.replace('-', '')}_*.json.gz")))


def latest(sport):
    fs = sorted(glob.glob(os.path.join(RAW, f"{sport}_2*.json.gz")))
    if not fs:
        return None, None
    j = json.load(gzip.open(fs[-1]))
    return j, fs[-1]


def consensus(e):
    """Fair two-way probabilities for one event. Pinnacle if present, else the median no-vig across every book
    (totals/spreads at the modal line). Also returns DraftKings / Bovada prices for display."""
    books = market.parse_event(e)
    out = dict(n_books=len(books), books=sorted(books))
    def pick(mkt, f):
        rows = [(k, f(v[mkt])) for k, v in books.items() if mkt in v]
        if not rows:
            return None
        if "pinnacle" in books and mkt in books["pinnacle"]:
            return dict(src="pinnacle", **f(books["pinnacle"][mkt]))
        lines = [r[1].get("line") for r in rows]
        mode = statistics.mode(lines) if lines[0] is not None else None
        qs = [r[1]["q"] for r in rows if r[1].get("line") == mode]
        return dict(src=f"median of {len(qs)} books", line=mode, q=statistics.median(qs))
    out["h2h"] = pick("h2h", lambda x: dict(line=None, q=market.novig(x[0], x[1])))
    out["spread"] = pick("spreads", lambda x: dict(line=x[0], q=market.novig(x[1], x[3])))
    out["total"] = pick("totals", lambda x: dict(line=x[0], q=market.novig(x[1], x[2])))
    out["target"] = {b: books[b] for b in ("draftkings", "bovada") if b in books}
    return out


def reserve_for_pro(now=None):
    """Credits the 9am desk run should leave for today's NBA/NHL pull (4 per sport with a game within 36h that has not
    been pulled yet today). Free schedule calls only (NHL API, ESPN)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    day = now.astimezone(CT).strftime("%Y-%m-%d")
    need = 0
    try:
        from . import nhl_run
        if spent_label("nhl_odds", day) == 0 and any((g["start"] - now).total_seconds() <= 36 * 3600 for g in nhl_run.slate(now)):
            need += COST
    except Exception:
        need += COST
    try:
        from . import nba_data
        if spent_label("nba_odds", day) == 0 and any(0 < (dt.datetime.fromisoformat(g["date_utc"].replace("Z", "+00:00")) - now).total_seconds() <= 36 * 3600
                                                    for g in nba_data.upcoming(2)):
            need += COST
    except Exception:
        pass
    return need
