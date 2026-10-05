"""ESPN public endpoints (no key): scoreboards for finals/closing lines, summaries for box scores."""
import json, urllib.request, time
BASE = "https://site.api.espn.com/apis/site/v2/sports/football"


def _get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "strawhat-desk/1"}), timeout=30) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def scoreboard(sport, yyyymmdd):
    if sport == "nfl":
        return _get(f"{BASE}/nfl/scoreboard?dates={yyyymmdd}")
    return _get(f"{BASE}/college-football/scoreboard?dates={yyyymmdd}&groups=80&limit=400")


def summary(sport, event_id):
    lg = "nfl" if sport == "nfl" else "college-football"
    return _get(f"{BASE}/{lg}/summary?event={event_id}")


def games(sb):
    out = []
    for e in (sb or {}).get("events", []):
        c = e["competitions"][0]
        teams = {x["homeAway"]: x for x in c["competitors"]}
        if "home" not in teams:
            continue
        st = c["status"]["type"]
        odds = (c.get("odds") or [{}])[0] if c.get("odds") else {}
        out.append(dict(id=e["id"], date=e["date"], home=teams["home"]["team"]["displayName"], away=teams["away"]["team"]["displayName"],
                        home_abbr=teams["home"]["team"].get("abbreviation"), away_abbr=teams["away"]["team"].get("abbreviation"),
                        home_score=float(teams["home"].get("score") or 0), away_score=float(teams["away"].get("score") or 0),
                        completed=bool(st.get("completed")), state=st.get("state"), status=st.get("name"),
                        espn_spread=odds.get("spread"), espn_total=odds.get("overUnder"), espn_details=odds.get("details"),
                        espn_provider=(odds.get("provider") or {}).get("name")))
    return out


def box_players(summ):
    """-> {normalized_name: {stat: value}} from ESPN summary boxscore (passing/rushing/receiving)."""
    from .props import pname
    out = {}
    for tm in (summ or {}).get("boxscore", {}).get("players", []):
        for cat in tm.get("statistics", []):
            keys = cat.get("keys") or []
            for a in cat.get("athletes", []):
                nm = pname(a["athlete"]["displayName"])
                st = dict(zip(keys, a.get("stats", [])))
                o = out.setdefault(nm, {"name": a["athlete"]["displayName"]})
                o["_present"] = True  # appeared in the box score in ANY category (incl. defense/returns/kicking)
                def num(k):
                    try:
                        return float(str(st.get(k, "")).replace(",", ""))
                    except ValueError:
                        return None
                if cat["name"] == "passing":
                    o["passing_yards"] = num("passingYards"); o["passing_tds"] = num("passingTouchdowns")
                elif cat["name"] == "rushing":
                    o["rushing_yards"] = num("rushingYards"); o["rushing_tds"] = num("rushingTouchdowns")
                elif cat["name"] == "receiving":
                    o["receiving_yards"] = num("receivingYards"); o["receptions"] = num("receptions"); o["receiving_tds"] = num("receivingTouchdowns")
    for o in out.values():
        o["anytime_td"] = 1.0 if ((o.get("rushing_tds") or 0) + (o.get("receiving_tds") or 0)) > 0 else 0.0
    return out


# ---- injury report (ESPN summary "injuries"; free) ----
OUT_STATUSES = {"out", "injured reserve", "ir", "suspended", "physically unable to perform", "pup", "non-football injury",
                "reserve/covid-19", "inactive"}
SKIP_AT_LOG = OUT_STATUSES | {"doubtful"}


def injuries(summ):
    """-> {pname: status_lower} from an ESPN summary (pre-game or live)."""
    from .props import pname
    out = {}
    for tm in (summ or {}).get("injuries", []) or []:
        for i in tm.get("injuries", []) or []:
            nm = (i.get("athlete") or {}).get("displayName")
            st = str(i.get("status") or (i.get("type") or {}).get("description") or "").strip().lower()
            fs = str(((i.get("details") or {}).get("fantasyStatus") or {}).get("description") or "").strip().lower()
            if nm:
                out[pname(nm)] = "inactive" if fs == "inactive" and st not in OUT_STATUSES else st
    return out


def event_for(sport, home, away, kick_iso):
    """ESPN event id for a game (by normalized team names on the kick date, CT and UTC)."""
    import datetime as dt
    from zoneinfo import ZoneInfo
    from .names import norm
    k = dt.datetime.fromisoformat(kick_iso)
    for d in {k.astimezone(ZoneInfo("America/Chicago")).strftime("%Y%m%d"), k.astimezone(dt.timezone.utc).strftime("%Y%m%d")}:
        for g in games(scoreboard(sport, d)):
            if {norm(g["home"]), norm(g["away"])} == {norm(home), norm(away)}:
                return g["id"]
    return None


_INJ = {}


def injuries_for_game(sport, home, away, kick_iso):
    key = (sport, home, away, kick_iso)
    if key not in _INJ:
        eid = event_for(sport, home, away, kick_iso)
        _INJ[key] = injuries(summary(sport, eid)) if eid else None
    return _INJ[key]
