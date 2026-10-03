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
