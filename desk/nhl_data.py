"""NHL data (free, 0 Odds API credits).

- Team-game shot quality: MoneyPuck team game-by-game CSV (xG, shot attempts, high-danger xG by situation:
  all / 5on5 / 5on4 / 4on5). Free for non-commercial use with credit (moneypuck.com/data.htm); this desk is a
  personal, non-commercial paper desk. One file per day, no scraping.
- Results + closing lines 2021-22..2026-27: desk-v1 history (ESPN core /odds close, DraftKings / ESPN BET), copied
  read-only into data/nhl/lines.csv. Current-season finals: NHL API (api-web.nhle.com) scores.
- Goalie game logs (starter, SA, SV): NHL stats API goalie summary (isGame=true), desk-v1 copies for 2020-21..2025-26.

Outputs: data/nhl/team_games.csv.gz, data/nhl/lines.csv, data/nhl/goalies.csv.gz"""
import argparse, datetime as dt, glob, gzip, io, json, os, urllib.request
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "nhl")
MP_URL = "https://moneypuck.com/moneypuck/playerData/careers/gameByGame/all_teams.csv"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) strawhat-desk"}
FIX = {"L.A": "LAK", "N.J": "NJD", "S.J": "SJS", "T.B": "TBL", "LA": "LAK", "NJ": "NJD", "SJ": "SJS", "TB": "TBL", "UTAH": "UTA"}
NHL32 = {"ANA", "ARI", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL", "NJD", "NSH",
         "NYI", "NYR", "OTT", "PHI", "PIT", "SEA", "SJS", "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WPG", "WSH"}
fx = lambda t: FIX.get(t, t)


def http(url, timeout=120):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def team_games_from_mp(csv_bytes_or_path, min_season=2019):
    cols = ["team", "season", "gameId", "opposingTeam", "home_or_away", "gameDate", "situation", "iceTime", "xGoalsFor", "xGoalsAgainst",
            "goalsFor", "goalsAgainst", "shotsOnGoalFor", "shotsOnGoalAgainst", "shotAttemptsFor", "shotAttemptsAgainst",
            "highDangerxGoalsFor", "highDangerxGoalsAgainst", "penalityMinutesFor", "penalityMinutesAgainst", "playoffGame"]
    src = io.BytesIO(csv_bytes_or_path) if isinstance(csv_bytes_or_path, bytes) else csv_bytes_or_path
    d = pd.read_csv(src, usecols=cols)
    d = d[(d.season >= min_season) & (d.playoffGame == 0) & d.situation.isin(["all", "5on5", "5on4", "4on5"])]
    d["team"] = d.team.map(fx); d["opposingTeam"] = d.opposingTeam.map(fx)
    key = ["gameId", "season", "team", "opposingTeam", "home_or_away", "gameDate"]
    ren = {"all": "a", "5on5": "e", "5on4": "pp", "4on5": "pk"}
    parts = []
    for s, p in ren.items():
        x = d[d.situation == s].set_index(key)
        x = x[["iceTime", "xGoalsFor", "xGoalsAgainst", "goalsFor", "goalsAgainst", "shotsOnGoalFor", "shotsOnGoalAgainst",
               "shotAttemptsFor", "shotAttemptsAgainst", "highDangerxGoalsFor", "highDangerxGoalsAgainst"]]
        x.columns = [f"{p}_{c}" for c in ["toi", "xgf", "xga", "gf", "ga", "sf", "sa", "cf", "ca", "hdf", "hda"]]
        parts.append(x)
    T = pd.concat(parts, axis=1).reset_index().fillna(0)
    T = T.rename(columns={"opposingTeam": "opp"})
    T["home"] = (T.home_or_away == "HOME").astype(int)
    T["date"] = pd.to_datetime(T.gameDate.astype(str), format="%Y%m%d").dt.strftime("%Y-%m-%d")
    T = T.drop(columns=["home_or_away", "gameDate"])
    return T[T.team.isin(NHL32)].sort_values(["date", "gameId", "home"])


def import_desk_v1(src="/workspace/desk-v1/data/history/nhl"):
    """One-time, read-only copy of desk-v1 NHL lines + goalie logs (never writes to desk-v1)."""
    L = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(os.path.join(src, "20*.csv")))])
    L["home"] = L.home.map(fx); L["away"] = L.away.map(fx)
    L = L[L.home.isin(NHL32) & L.away.isin(NHL32)]
    L["date"] = (pd.to_datetime(L.date_utc) - pd.Timedelta(hours=5)).dt.strftime("%Y-%m-%d")  # CT-ish date for joining
    keep = ["espn_id", "date_utc", "date", "season", "home", "away", "home_score", "away_score", "result_type", "neutral", "ml_home", "ml_away",
            "spread_home", "sp_price_home", "sp_price_away", "total", "over_price", "under_price", "odds_provider"]
    L[keep].to_csv(os.path.join(OUT, "lines.csv"), index=False)
    G = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(os.path.join(src, "goalies_*.csv")))])
    G.to_csv(os.path.join(OUT, "goalies.csv.gz"), index=False)
    return len(L), len(G)


def goalie_logs(season_id):
    """NHL stats API goalie per-game summary (free, no key)."""
    rows, start = [], 0
    while True:
        url = (f"https://api.nhle.com/stats/rest/en/goalie/summary?isAggregate=false&isGame=true&start={start}&limit=100"
               f"&cayenneExp=seasonId={season_id}%20and%20gameTypeId=2")
        j = json.loads(http(url, 60))
        for r in j.get("data", []):
            rows.append(dict(gameId=r["gameId"], date=r["gameDate"], team=r["teamAbbrev"], pid=r["playerId"], name=r["goalieFullName"],
                             gs=r.get("gamesStarted", 0), sa=r.get("shotsAgainst", 0), sv=r.get("saves", 0)))
        start += 100
        if start >= j.get("total", 0) or not j.get("data"):
            break
    return pd.DataFrame(rows)


def finals_nhlapi(days_back=10):
    """Current-season regular-season finals from api-web.nhle.com (free)."""
    out, seen = [], set()
    today = dt.date.today()
    for k in range(days_back, -1, -1):
        d = (today - dt.timedelta(days=k)).isoformat()
        try:
            j = json.loads(http(f"https://api-web.nhle.com/v1/score/{d}", 30))
        except Exception:
            continue
        for g in j.get("games", []):
            if g.get("gameType") != 2 or g.get("gameState") not in ("OFF", "FINAL") or g["id"] in seen:
                continue
            seen.add(g["id"])
            lp = (g.get("gameOutcome") or {}).get("lastPeriodType", "REG")
            out.append(dict(gameId=g["id"], date=g["gameDate"], home=fx(g["homeTeam"]["abbrev"]), away=fx(g["awayTeam"]["abbrev"]),
                            home_score=g["homeTeam"].get("score"), away_score=g["awayTeam"].get("score"), result_type=lp))
    return pd.DataFrame(out)


def refresh(season=None):
    """Daily: MoneyPuck team gbg (current season rows) + goalie logs for the current season. Returns notes."""
    now = dt.datetime.now()
    season = season or (now.year if now.month >= 8 else now.year - 1)
    notes = []
    tp = os.path.join(OUT, "team_games.csv.gz")
    try:
        new = team_games_from_mp(http(MP_URL, 300), min_season=season)
        old = pd.read_csv(tp)
        T = pd.concat([old[old.season < season], new]).sort_values(["date", "gameId", "home"])
        T.to_csv(tp, index=False)
        notes.append(f"MoneyPuck: {len(new)//2} {season} games, through {new.date.max() if len(new) else '-'}")
    except Exception as ex:
        notes.append(f"MoneyPuck refresh failed ({ex!r}); using committed team games")
    gp = os.path.join(OUT, "goalies.csv.gz")
    try:
        sid = int(f"{season}{season+1}")
        g = goalie_logs(sid)
        old = pd.read_csv(gp)
        old = old[old.gameId // 1000000 != season]
        pd.concat([old, g]).to_csv(gp, index=False)
        notes.append(f"goalie logs: {len(g)} rows for {sid}")
    except Exception as ex:
        notes.append(f"goalie log refresh failed ({ex!r})")
    return notes


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mp", default=None, help="local all_teams.csv (else download)")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    T = team_games_from_mp(a.mp if a.mp else http(MP_URL, 300))
    T.to_csv(os.path.join(OUT, "team_games.csv.gz"), index=False)
    print("team games", len(T), T.season.value_counts().sort_index().to_dict())
    print("desk-v1 import (lines, goalie rows):", import_desk_v1())
