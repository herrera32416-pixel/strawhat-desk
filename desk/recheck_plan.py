"""RECHECK planner (stdlib only, no credits): decides whether a pre-kick recheck has work to do right now.
Used by the workflow guard (cheap, before installing deps) and by desk/recheck.py.

A recheck target is an OPEN ledger item whose kick is within WINDOW_MIN minutes and that has not been rechecked yet
(data/recheck_done.json):
- official odds targets: board picks -> line re-pull (COST credits per sport, eventIds filter);
- props targets: open props -> free ESPN injury report (void players newly Out).
Teasers/parlays were retired 2026-10-08 and are never rechecked."""
import datetime as dt, json, os, sys
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "data", "ledger", "ledger.json")
DONE = os.path.join(ROOT, "data", "recheck_done.json")
WINDOW_MIN = 70     # crons fire at :15/:45; 70 min puts the noon-kick recheck at ~11:15 CT (backup 11:45)
import os as _os
COST = 2 * len(_os.environ.get("SH_REGIONS", "us,eu").split(","))  # regions x spreads,totals (free tier: us only = 2)
MAX_WINDOWS = int(_os.environ.get("SH_MAX_RECHECKS", "3"))  # paid plan: 3/day (free tier: 1)     # at most 3 odds rechecks reserved per day (e.g. Sun 12:00 / 3:05-3:25 / 7:20 CT) = 12 credits


def _t(iso):
    return dt.datetime.fromisoformat(iso)


def kind_of(it):
    if it.get("kind"):
        return it["kind"]
    if it["tab"] == "board":
        return "official"
    if it["tab"] == "teasers":
        return "official" if it.get("decision") == "PLAY" else "research"
    return "research"


def first_kick(it):
    if it.get("legs"):
        return min(_t(l["kick_iso"]) for l in it["legs"])
    return _t(it["kick_iso"])


def load_done(now):
    d = now.astimezone(CT).date().isoformat()
    try:
        j = json.load(open(DONE))
    except Exception:
        j = {}
    if j.get("date") != d:
        j = {"date": d, "items": []}
    return j


def plan(now=None, ledger=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    L = ledger or (json.load(open(LEDGER)) if os.path.exists(LEDGER) else {"items": []})
    done = set(load_done(now)["items"])
    lim = now + dt.timedelta(minutes=WINDOW_MIN)
    odds, props = [], []
    for it in L["items"]:
        if it["status"] != "open" or it["id"] in done:
            continue
        k = first_kick(it)
        if not (now < k <= lim):
            continue
        if it["tab"] == "props":
            props.append(it)
        elif kind_of(it) == "official" and it["tab"] == "board":
            odds.append(it)
    return dict(odds=odds, props=props, go=bool(odds or props),
                why=f"{len(odds)} official item(s) and {len(props)} prop(s) kick within {WINDOW_MIN} min" if (odds or props)
                else f"nothing open kicks within {WINDOW_MIN} min (or already rechecked)")


def windows(kicks, minutes=WINDOW_MIN):
    """Number of distinct recheck windows needed for these kick times (clustered: a new window when a kick is more
    than `minutes` after the first kick of the current window)."""
    n, start = 0, None
    for k in sorted(kicks):
        if start is None or (k - start).total_seconds() / 60 > minutes:
            n += 1; start = k
    return n


if __name__ == "__main__":
    p = plan()
    print(f"go={'yes' if p['go'] else 'no'}")
    print(p["why"], file=sys.stderr)
