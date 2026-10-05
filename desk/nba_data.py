"""NBA data (free, 0 Odds API credits): ESPN site scoreboard + summary box scores + ESPN core /odds (pregame close).

History build:  python -m desk.nba_data --seasons 2020-2025   (season = start year; 2025 = 2025-26)
Live refresh:   nba_data.refresh(season) re-pulls only dates after the last stored game.
Outputs: data/nba/games.csv (one row per game, scores + ESPN-listed close spread/total/ML and prices)
         data/nba/team_games.csv.gz (one row per team-game: box counts for possessions / four factors).
Raw responses are cached gzipped in $NBA_CACHE (default /workspace/tmp/nba_cache; not committed)."""
import argparse, concurrent.futures as cf, datetime as dt, gzip, hashlib, json, os, time, urllib.request
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "nba")
CACHE = os.environ.get("NBA_CACHE", "/workspace/tmp/nba_cache")
SB = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={d}"
SUM = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={i}"
ODDS = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/events/{i}/competitions/{i}/odds"
NBA30 = {"ATL", "BKN", "BOS", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GS", "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NO", "NY",
         "OKC", "ORL", "PHI", "PHX", "POR", "SA", "SAC", "TOR", "UTAH", "WSH"}   # ESPN codes; All-Star / exhibition teams are dropped
PROV_PRI = ["DraftKings", "ESPN BET", "Caesars Sportsbook", "consensus", "numberfire", "teamrankings"]


def get(url, cache=True, tries=3):
    p = os.path.join(CACHE, hashlib.md5(url.encode()).hexdigest() + ".json.gz")
    if cache and os.path.exists(p):
        return json.load(gzip.open(p))
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (strawhat-desk research)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                j = json.loads(r.read())
            if cache:
                os.makedirs(CACHE, exist_ok=True)
                json.dump(j, gzip.open(p, "wt"))
            return j
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(1 + 2 * k)
        except Exception:
            time.sleep(1 + 2 * k)
    return None


def _am(x):
    try:
        s = str(x).replace("+", "")
        return None if s in ("", "None", "EVEN") and s != "EVEN" else (100 if s == "EVEN" else int(float(s)))
    except Exception:
        return None


def pick_odds(js):
    items = [it for it in (js or {}).get("items") or [] if "live" not in it.get("provider", {}).get("name", "").lower()]
    if not items:
        return {}
    def pri(it):
        n = it.get("provider", {}).get("name", "")
        return next((k for k, p in enumerate(PROV_PRI) if p.lower() in n.lower()), 99)
    items.sort(key=pri)
    it = next((i for i in items if i.get("spread") is not None and i.get("overUnder") is not None), items[0])
    h, a = it.get("homeTeamOdds") or {}, it.get("awayTeamOdds") or {}
    return dict(odds_provider=it.get("provider", {}).get("name"), odds_providers_n=len(items),
                spread_home=it.get("spread"), total=it.get("overUnder"),
                sp_price_home=_am(h.get("spreadOdds")), sp_price_away=_am(a.get("spreadOdds")),
                over_price=_am(it.get("overOdds")), under_price=_am(it.get("underOdds")),
                ml_home=_am(h.get("moneyLine")), ml_away=_am(a.get("moneyLine")),
                spread_home_open=_num(((h.get("open") or {}).get("pointSpread") or {}).get("american")),
                total_open=_num(((it.get("open") or {}).get("total") or {}).get("american", "").lstrip("ou") if isinstance((it.get("open") or {}).get("total"), dict) else None))


def _num(x):
    try:
        return float(str(x).replace("+", ""))
    except Exception:
        return None


def scoreboard_games(d):
    j = get(SB.format(d=d), cache=d < (dt.date.today() - dt.timedelta(days=2)).strftime("%Y%m%d"))
    out = []
    for e in (j or {}).get("events", []):
        if e.get("season", {}).get("type") != 2:
            continue
        c = e["competitions"][0]
        st = c["status"]["type"]
        t = {x["homeAway"]: x for x in c["competitors"]}
        if t["home"]["team"]["abbreviation"] not in NBA30 or t["away"]["team"]["abbreviation"] not in NBA30:
            continue
        out.append(dict(espn_id=e["id"], date_utc=e["date"], season=e["season"]["year"] - 1, completed=st.get("completed", False),
                        period=c["status"].get("period"), neutral=c.get("neutralSite", False),
                        home=t["home"]["team"]["abbreviation"], away=t["away"]["team"]["abbreviation"],
                        home_name=t["home"]["team"]["displayName"], away_name=t["away"]["team"]["displayName"],
                        home_score=_num(t["home"].get("score")), away_score=_num(t["away"].get("score"))))
    return out


STATS = {"fieldGoalsMade-fieldGoalsAttempted": ("fgm", "fga"), "threePointFieldGoalsMade-threePointFieldGoalsAttempted": ("tpm", "tpa"),
         "freeThrowsMade-freeThrowsAttempted": ("ftm", "fta"), "offensiveRebounds": "orb", "defensiveRebounds": "drb",
         "totalRebounds": "trb", "assists": "ast", "steals": "stl", "blocks": "blk", "totalTurnovers": "tov", "turnovers": "tov_pl",
         "pointsInPaint": "paint", "fastBreakPoints": "fbp", "fouls": "pf", "turnoverPoints": "tovpts"}


def box(eid):
    j = get(SUM.format(i=eid))
    rows = {}
    for t in ((j or {}).get("boxscore") or {}).get("teams", []):
        r = {}
        for s in t.get("statistics", []):
            k = STATS.get(s["name"])
            if not k:
                continue
            v = s.get("displayValue", "")
            if isinstance(k, tuple):
                try:
                    a, b = v.split("-"); r[k[0]], r[k[1]] = float(a), float(b)
                except Exception:
                    pass
            else:
                r[k] = _num(v)
        rows[t["team"]["abbreviation"]] = r
    return rows


def game_detail(g):
    o = pick_odds(get(ODDS.format(i=g["espn_id"]))) if g["completed"] else {}
    b = box(g["espn_id"]) if g["completed"] else {}
    return g, o, b


def season_dates(season):
    s = dt.date(season, 12, 20) if season == 2020 else dt.date(season, 10, 1)
    e = dt.date(season + 1, 5, 20) if season == 2020 else dt.date(season + 1, 4, 20)
    return [(s + dt.timedelta(days=k)).strftime("%Y%m%d") for k in range((e - s).days + 1)]


def build(seasons, start_after=None, workers=8):
    games, tg = [], []
    for season in seasons:
        dates = [d for d in season_dates(season) if d <= dt.date.today().strftime("%Y%m%d") and (start_after is None or d > start_after)]
        with cf.ThreadPoolExecutor(workers) as ex:
            gl = [g for lst in ex.map(scoreboard_games, dates) for g in lst]
        gl = [g for g in gl if g["completed"]]
        with cf.ThreadPoolExecutor(workers) as ex:
            for g, o, b in ex.map(game_detail, gl):
                row = dict(g); row.update(o); games.append(row)
                for side, opp, hs in (("home", "away", 1), ("away", "home", 0)):
                    tb, ob = b.get(g[side], {}), b.get(g[opp], {})
                    if not tb or not ob:
                        continue
                    r = dict(espn_id=g["espn_id"], date_utc=g["date_utc"], season=g["season"], team=g[side], opp=g[opp], home=hs,
                             neutral=g["neutral"], periods=g["period"], pts=g[side + "_score"], opp_pts=g[opp + "_score"])
                    r.update(tb); r.update({"o_" + k: v for k, v in ob.items()})
                    tg.append(r)
        print(f"NBA {season}: {len(gl)} final games, odds {sum(1 for x in games if x['season']==season and x.get('spread_home') is not None)}", flush=True)
    return pd.DataFrame(games), pd.DataFrame(tg)


def save(G, T, merge=True):
    os.makedirs(OUT, exist_ok=True)
    gp, tp = os.path.join(OUT, "games.csv"), os.path.join(OUT, "team_games.csv.gz")
    if merge and os.path.exists(gp):
        G = pd.concat([pd.read_csv(gp, dtype={"espn_id": str}), G.astype({"espn_id": str})]).drop_duplicates("espn_id", keep="last")
        T = pd.concat([pd.read_csv(tp, dtype={"espn_id": str}), T.astype({"espn_id": str})]).drop_duplicates(["espn_id", "team"], keep="last")
    G = G[G.home.isin(NBA30) & G.away.isin(NBA30)]; T = T[T.team.isin(NBA30) & T.opp.isin(NBA30)]
    G.sort_values("date_utc").to_csv(gp, index=False)
    T.sort_values(["date_utc", "espn_id", "home"]).to_csv(tp, index=False)
    return G, T


def refresh(season):
    """Daily: pull completed games of `season` after the last stored date (cheap: a few scoreboard + summary calls)."""
    gp = os.path.join(OUT, "games.csv")
    last = None
    if os.path.exists(gp):
        G = pd.read_csv(gp)
        s = G[G.season == season]
        if len(s):
            last = (pd.to_datetime(s.date_utc.max()) - pd.Timedelta(days=2)).strftime("%Y%m%d")
    G, T = build([season], start_after=last, workers=4)
    if len(G):
        save(G, T)
    return len(G)


def upcoming(days=2):
    """Scheduled regular-season games in the next `days` days (ESPN; free)."""
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for k in range(-1, days + 1):
        d = (now + dt.timedelta(days=k)).astimezone(dt.timezone(dt.timedelta(hours=-5))).strftime("%Y%m%d")
        out += [g for g in scoreboard_games(d) if not g["completed"]]
    seen, res = set(), []
    for g in out:
        if g["espn_id"] not in seen:
            seen.add(g["espn_id"]); res.append(g)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default="2020-2025")
    a = ap.parse_args()
    lo, hi = map(int, a.seasons.split("-"))
    G, T = build(range(lo, hi + 1))
    save(G, T, merge=False)
