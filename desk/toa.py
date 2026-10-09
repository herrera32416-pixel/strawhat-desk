"""The Odds API client with credit logging and a hard budget guard.

Every call appends one row to data/credits.jsonl with the x-requests-* headers.
A call is refused (not made) if its estimated cost would push today's (CT) spend
over DAILY_CAP or the project's total over PROJECT_CAP.
"""
import datetime as dt, json, os, urllib.parse, urllib.request
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "data", "credits.jsonl")
BASE = "https://api.the-odds-api.com"
# FREE TIER since 2026-10-09 (paid plan payment failed 10/8): 500 credits/month shared with DESK (desk-v1, same key).
# Strawhat budget: <= SH_DAILY_CAP per CT day and <= SH_MONTHLY_CAP per CT month, and never below SH_MIN_REMAINING
# credits left on the key (last x-requests-remaining header seen). Anything refused falls back to ESPN odds (tagged).
DAILY_CAP = int(os.environ.get("SH_DAILY_CAP", "10"))
MONTHLY_CAP = int(os.environ.get("SH_MONTHLY_CAP", "220"))
MIN_REMAINING = int(os.environ.get("SH_MIN_REMAINING", "40"))
REGIONS = os.environ.get("SH_REGIONS", "us")  # free tier: us only (1 credit per market); was "us,eu"
PROJECT_CAP = int(os.environ.get("SH_PROJECT_CAP", "1500"))


class BudgetError(RuntimeError):
    pass


def _key():
    k = os.environ.get("THE_ODDS_API_KEY", "").strip()
    if not k:
        raise RuntimeError("THE_ODDS_API_KEY not set")
    return k


def log_rows():
    if not os.path.exists(LOG):
        return []
    return [json.loads(l) for l in open(LOG) if l.strip()]


def last_remaining():
    for r in reversed(log_rows()):
        if r.get("remaining") not in (None, ""):
            try:
                return int(float(r["remaining"]))
            except ValueError:
                return None
    return None


def spent(day=None, kind=None):
    tot = 0
    for r in log_rows():
        if day and r.get("day_ct") != day:
            continue
        if kind and r.get("kind") != kind:
            continue
        tot += int(r.get("last") or 0)
    return tot


def get(path, params, est_cost, label, kind="daily"):
    today = dt.datetime.now(CT).strftime("%Y-%m-%d")
    if kind == "daily" and spent(today, "daily") + est_cost > DAILY_CAP:
        raise BudgetError(f"daily cap {DAILY_CAP}: spent {spent(today,'daily')}, need {est_cost} ({label})")
    since = max(today[:7] + "-01", os.environ.get("SH_FREE_SINCE", "2026-10-10"))  # paid-plan spend doesn't count
    mspent = sum(int(r.get("last") or 0) for r in log_rows() if since <= str(r.get("day_ct", "")) <= today)
    if est_cost and mspent + est_cost > MONTHLY_CAP:
        raise BudgetError(f"monthly cap {MONTHLY_CAP}: spent {mspent} this month, need {est_cost} ({label})")
    rem = last_remaining()
    if est_cost and rem is not None and rem - est_cost < MIN_REMAINING:
        raise BudgetError(f"key has {rem} credits left (floor {MIN_REMAINING}) ({label})")
    if spent() + est_cost > PROJECT_CAP and kind != "daily":
        raise BudgetError(f"project cap {PROJECT_CAP} hit ({label})")
    q = dict(params); q["apiKey"] = _key()
    url = f"{BASE}{path}?{urllib.parse.urlencode(q)}"
    req = urllib.request.Request(url, headers={"User-Agent": "strawhat-desk/1"})
    status, body, h = None, None, {}
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            status, body, h = r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        status, body, h = e.code, e.read(), e.headers
    row = {"time_ct": dt.datetime.now(CT).isoformat(timespec="seconds"), "day_ct": today,
           "kind": kind, "label": label, "path": path, "status": status,
           "est": est_cost, "last": h.get("x-requests-last"),
           "used": h.get("x-requests-used"), "remaining": h.get("x-requests-remaining")}
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write(json.dumps(row) + "\n")
    if status != 200:
        raise RuntimeError(f"TOA {status} {label}: {body[:200]!r}")
    return json.loads(body), row
