#!/usr/bin/env python3
"""Daily timestamped archive (research only; never feeds live picks).

Saves to data/archive/YYYY-MM-DD/ (CT date):
  injuries/<league>_<HHMM>.json   ESPN injuries (nfl, cfb, nhl, nba, mlb)
  nhl_goalies_<HHMM>.json         DailyFaceoff starting goalies (today + tomorrow)
  mlb_lineups_<HHMM>.json         MLB StatsAPI probables + lineups (today + tomorrow)
  odds/<sport>_<HHMM>.json        The Odds API sides/totals/ML (draftkings, bovada, betr*)
  props/<sport>_<event>_<open|close>.json   player props, once when first seen (open) and once <=3h pre-start (close)
  runs.jsonl                      one row per run: what ran, what failed, credits spent
Every fetch is wrapped: a failure is logged in runs.jsonl and the run continues (exit 0).
Idempotent: odds skip if a snapshot <75 min old exists; props open/close are taken once per event (data/archive/props_seen.json).
Credits: own log data/archive/credits.jsonl (does NOT touch data/credits.jsonl), daily cap ARCH_DAILY_CAP,
monthly cap ARCH_MONTHLY_CAP, and stop if the key would drop below ARCH_MIN_REMAINING (protects the live desk).
"""
import datetime as dt, json, os, re, sys, time, traceback, urllib.parse, urllib.request
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCH = os.path.join(ROOT, "data", "archive")
CRED = os.path.join(ARCH, "credits.jsonl")
DESK_CRED = os.path.join(ROOT, "data", "credits.jsonl")
SEEN = os.path.join(ARCH, "props_seen.json")
DAILY_CAP = int(os.environ.get("ARCH_DAILY_CAP", "200"))
MONTHLY_CAP = int(os.environ.get("ARCH_MONTHLY_CAP", "4000"))
MIN_REMAINING = int(os.environ.get("ARCH_MIN_REMAINING", "3000"))
PROPS_ON = os.environ.get("ARCH_PROPS", "1") == "1"
BOOKS = os.environ.get("ARCH_BOOKS", "draftkings,bovada,betr_au")
UA = {"User-Agent": "Mozilla/5.0 (strawhat-desk archive)"}

NOW = dt.datetime.now(CT)
DAY = NOW.strftime("%Y-%m-%d")
HM = NOW.strftime("%H%M")
OUT = os.path.join(ARCH, DAY)
RUN = {"time_ct": NOW.isoformat(timespec="seconds"), "ok": [], "failed": [], "skipped": [], "credits": 0}

ESPN = {"nfl": "football/nfl", "cfb": "football/college-football", "nhl": "hockey/nhl",
        "nba": "basketball/nba", "mlb": "baseball/mlb"}
TOA = {"nfl": "americanfootball_nfl", "cfb": "americanfootball_ncaaf", "nhl": "icehockey_nhl",
       "nba": "basketball_nba", "mlb": "baseball_mlb"}
PROP_MKTS = {
    "nfl": "player_pass_yds,player_rush_yds,player_reception_yds,player_receptions,player_anytime_td",
    "nba": "player_points,player_rebounds,player_assists,player_threes",
    "nhl": "player_points,player_shots_on_goal,player_goal_scorer_anytime,player_total_saves",
    "mlb": "pitcher_strikeouts,batter_hits,batter_total_bases,batter_home_runs",
    "cfb": "player_pass_yds,player_rush_yds,player_reception_yds",
}
PROP_SPORTS = os.environ.get("ARCH_PROP_SPORTS", "nfl,nba,nhl,mlb").split(",")


def http(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read(), r.headers


def save(rel, payload, source):
    p = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"fetched_at_ct": dt.datetime.now(CT).isoformat(timespec="seconds"),
                   "fetched_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                   "source": source, "data": payload}, f, separators=(",", ":"))
    os.replace(tmp, p)
    return p


def step(name, fn):
    try:
        r = fn()
        RUN["ok"].append(name if r is None else f"{name}: {r}")
    except Exception as e:  # never fatal
        RUN["failed"].append(f"{name}: {type(e).__name__}: {str(e)[:200]}")
        traceback.print_exc()


# ---------- free sources ----------
def espn_injuries(lg):
    url = f"https://site.api.espn.com/apis/site/v2/sports/{ESPN[lg]}/injuries"
    _, b, _ = http(url)
    d = json.loads(b)
    n = sum(len(t.get("injuries", [])) for t in d.get("injuries", []))
    save(f"injuries/{lg}_{HM}.json", d, url)
    return f"{n} players"


def nhl_goalies():
    out, n = {}, 0
    for k in (0, 1):
        day = (NOW + dt.timedelta(days=k)).strftime("%Y-%m-%d")
        url = f"https://www.dailyfaceoff.com/starting-goalies/{day}"
        _, b, _ = http(url)
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', b.decode("utf-8", "replace"), re.S)
        rows = (json.loads(m.group(1))["props"]["pageProps"].get("data") or []) if m else []
        out[day] = rows; n += len(rows)
    save(f"nhl_goalies_{HM}.json", out, "dailyfaceoff.com/starting-goalies")
    return f"{n} games"


def mlb_lineups():
    s, e = DAY, (NOW + dt.timedelta(days=1)).strftime("%Y-%m-%d")
    url = ("https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=%s&endDate=%s"
           "&hydrate=probablePitcher,lineups,team" % (s, e))
    _, b, _ = http(url)
    d = json.loads(b)
    g = [x for dd in d.get("dates", []) for x in dd.get("games", [])]
    lu = sum(1 for x in g if (x.get("lineups") or {}).get("homePlayers"))
    save(f"mlb_lineups_{HM}.json", d, url)
    return f"{len(g)} games, {lu} with posted lineups"


# ---------- The Odds API (budgeted) ----------
def _rows(path):
    if not os.path.exists(path):
        return []
    out = []
    for l in open(path):
        try: out.append(json.loads(l))
        except Exception: pass
    return out


def key_remaining():
    best = None  # latest remaining header across both logs
    for r in _rows(DESK_CRED) + _rows(CRED):
        if r.get("remaining") not in (None, ""):
            t = r.get("time_ct", "")
            if best is None or t > best[0]:
                best = (t, int(float(r["remaining"])))
    return best[1] if best else None


def arch_spent(prefix):
    return sum(int(r.get("last") or 0) for r in _rows(CRED) if str(r.get("day_ct", "")).startswith(prefix))


def toa(path, params, est, label):
    if est:
        if arch_spent(DAY) + est > DAILY_CAP:
            raise RuntimeError(f"budget: daily cap {DAILY_CAP} (spent {arch_spent(DAY)}, need {est})")
        if arch_spent(DAY[:7]) + est > MONTHLY_CAP:
            raise RuntimeError(f"budget: monthly cap {MONTHLY_CAP}")
        rem = key_remaining()
        if rem is not None and rem - est < MIN_REMAINING:
            raise RuntimeError(f"budget: key has {rem} left, floor {MIN_REMAINING}")
    k = os.environ.get("THE_ODDS_API_KEY", "").strip()
    if not k:
        raise RuntimeError("THE_ODDS_API_KEY not set")
    q = dict(params); q["apiKey"] = k
    url = f"https://api.the-odds-api.com{path}?{urllib.parse.urlencode(q)}"
    try:
        st, b, h = http(url, 60)
    except urllib.error.HTTPError as e:
        st, b, h = e.code, e.read(), e.headers
    row = {"time_ct": dt.datetime.now(CT).isoformat(timespec="seconds"), "day_ct": DAY, "kind": "archive",
           "label": label, "path": path, "status": st, "est": est, "last": h.get("x-requests-last"),
           "used": h.get("x-requests-used"), "remaining": h.get("x-requests-remaining")}
    os.makedirs(ARCH, exist_ok=True)
    with open(CRED, "a") as f:
        f.write(json.dumps(row) + "\n")
    RUN["credits"] += int(row["last"] or 0)
    if st != 200:
        raise RuntimeError(f"TOA {st}: {b[:150]!r}")
    return json.loads(b)


def recent_odds(lg, minutes=75):
    d = os.path.join(OUT, "odds")
    if not os.path.isdir(d):
        return False
    for f in os.listdir(d):
        m = re.match(rf"{lg}_(\d{{4}})\.json$", f)
        if m:
            t = NOW.replace(hour=int(m.group(1)[:2]), minute=int(m.group(1)[2:]))
            if 0 <= (NOW - t).total_seconds() < minutes * 60:
                return True
    return False


EVENTS = {}


def game_odds(lg):
    if recent_odds(lg):
        RUN["skipped"].append(f"odds {lg}: snapshot <75 min old (idempotent)")
        return "skipped"
    p = f"/v4/sports/{TOA[lg]}/odds"
    d = toa(p, {"bookmakers": BOOKS, "markets": "h2h,spreads,totals", "oddsFormat": "american"}, 3, f"arch odds {lg}")
    EVENTS[lg] = d
    save(f"odds/{lg}_{HM}.json", d, p)
    books = sorted({b["key"] for e in d for b in e.get("bookmakers", [])})
    return f"{len(d)} events, books={books}"


def events_free(lg):
    if lg in EVENTS:
        return EVENTS[lg]
    d = toa(f"/v4/sports/{TOA[lg]}/events", {}, 0, f"arch events {lg}")
    EVENTS[lg] = d
    return d


def props(lg):
    seen = json.load(open(SEEN)) if os.path.exists(SEEN) else {}
    evs = sorted(events_free(lg), key=lambda e: e["commence_time"])
    took, spent_here, nbooks = 0, 0, set()
    for e in evs:
        start = dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")).astimezone(CT)
        hrs = (start - NOW).total_seconds() / 3600
        if hrs <= 0 or hrs > 36:
            continue
        st = seen.get(e["id"], {})
        tag = "close" if hrs <= 3 and "close" not in st else "open" if "open" not in st else None
        if not tag:
            continue
        est = len(PROP_MKTS[lg].split(","))
        p = f"/v4/sports/{TOA[lg]}/events/{e['id']}/odds"
        try:
            d = toa(p, {"bookmakers": BOOKS, "markets": PROP_MKTS[lg], "oddsFormat": "american"}, est,
                    f"arch props {lg} {e['away_team']}@{e['home_team']} {tag}")
        except RuntimeError as ex:
            if str(ex).startswith("budget"):
                RUN["skipped"].append(f"props {lg}: {ex}"); break
            raise
        nbooks |= {b["key"] for b in d.get("bookmakers", [])}
        save(f"props/{lg}_{e['id'][:10]}_{tag}.json", d, p)
        st[tag] = dt.datetime.now(CT).isoformat(timespec="seconds"); st["commence"] = e["commence_time"]
        seen[e["id"]] = st
        with open(SEEN, "w") as f:
            json.dump(seen, f)
        took += 1
    # prune events started >3 days ago
    cut = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)).isoformat()
    seen = {k: v for k, v in seen.items() if v.get("commence", "9") > cut}
    with open(SEEN, "w") as f:
        json.dump(seen, f)
    return f"{took} event snapshots, books={sorted(nbooks)}"


def main():
    os.makedirs(OUT, exist_ok=True)
    for lg in ESPN:
        step(f"injuries {lg}", lambda lg=lg: espn_injuries(lg))
    step("nhl goalies", nhl_goalies)
    step("mlb probables/lineups", mlb_lineups)
    if os.environ.get("ARCH_ODDS", "1") == "1":
        for lg in TOA:
            step(f"odds {lg}", lambda lg=lg: game_odds(lg))
        if PROPS_ON:
            for lg in PROP_SPORTS:
                step(f"props {lg}", lambda lg=lg: props(lg))
    RUN["key_remaining"] = key_remaining()
    RUN["archive_spent_today"] = arch_spent(DAY)
    with open(os.path.join(OUT, "runs.jsonl"), "a") as f:
        f.write(json.dumps(RUN) + "\n")
    print(json.dumps(RUN, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
