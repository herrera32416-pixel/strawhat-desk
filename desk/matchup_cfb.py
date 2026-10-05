"""CFB MATCHUP layer (FBS): same unit ratings / matchup features / style similarity / common opponents as the
NFL layer (desk/matchup.py), built from free cfbfastR play-by-play (sportsdataverse-data releases) and the desk's
ESPN closing lines. Stronger shrinkage than NFL (12-game seasons, 130+ teams): ridge penalty 12 games.
No pressure data in CFB pbp, so the pass-rush/protection unit uses sack rate (press_rate := sack_rate).
FCS opponents are rated (connectivity) but ranks are among FBS teams only. INFO ONLY unless
backtest/matchup_cfb_bt.py passes its pre-registered criteria."""
import os, json, glob, datetime as dt
import numpy as np
import pandas as pd
from desk import matchup as M

ROOT = M.ROOT
TG = os.path.join(ROOT, "data", "matchup", "cfb_team_games.csv.gz")
MODEL = os.path.join(ROOT, "data", "matchup", "cfb_model.json")
URL = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfbfastR_cfb_pbp/play_by_play_{y}.parquet"
LAM, PRIOR_W = 12.0, 0.35
COLS = ["game_id", "season", "week", "season_type", "pos_team", "def_pos_team", "home", "away", "home_team_division",
        "away_team_division", "pass", "rush", "sack", "EPA", "success", "yards_gained", "down", "wp_before", "period",
        "yards_to_goal", "drive_id", "drive_result", "play_type", "wallclock"]


def lines_table():
    fr = []
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "history", "cfb_20*.csv"))):
        fr.append(pd.read_csv(p, low_memory=False))
    c = pd.concat(fr, ignore_index=True)
    return c


def team_games(pbp, lt):
    d = pbp[(pbp.home_team_division == "fbs") | (pbp.away_team_division == "fbs")]
    d = d[d.pos_team.notna() & d.EPA.notna() & ((d["pass"] == 1) | (d["rush"] == 1))].copy()
    d["is_db"], d["is_run"] = (d["pass"] == 1).astype(float), ((d["rush"] == 1) & (d["pass"] != 1)).astype(float)
    d["sackf"] = (d["sack"] == 1).astype(float) * d["is_db"]
    d["expl"] = (((d.is_db == 1) & (d.yards_gained >= 20)) | ((d.is_run == 1) & (d.yards_gained >= 10))).astype(float)
    neu = d.down.isin([1, 2]) & d.wp_before.between(0.2, 0.8) & (d.period <= 3)
    d["neu"], d["neu_pass"] = neu.astype(float), (neu & (d.is_db == 1)).astype(float)
    k = [d.game_id, d.pos_team]
    g = d.groupby(["game_id", "pos_team"])
    out = pd.DataFrame({"season": g.season.first(), "week": g.week.first(), "season_type": g.season_type.first(),
                        "opp": g.def_pos_team.first(), "home": (g.pos_team.first() == g.home.first()).astype(int),
                        "plays": g.size(), "dropbacks": g.is_db.sum(), "runs": g.is_run.sum()})
    sm = lambda col: (d[col]).groupby(k).sum()
    wm = lambda col, mask: (d[col] * d[mask]).groupby(k).sum() / d[mask].groupby(k).sum().replace(0, np.nan)
    out["pass_epa"], out["pass_sr"] = wm("EPA", "is_db"), wm("success", "is_db")
    out["rush_epa"], out["rush_sr"] = wm("EPA", "is_run"), wm("success", "is_run")
    out["sack_rate"] = sm("sackf") / out.dropbacks.replace(0, np.nan)
    out["press_rate"] = out["sack_rate"]
    out["expl_rate"] = g.expl.mean()
    out["ed_pass_rate"] = sm("neu_pass") / sm("neu").replace(0, np.nan)
    dr = d.groupby(["game_id", "pos_team", "drive_id"]).agg(minyl=("yards_to_goal", "min"), res=("drive_result", "first"))
    rz = dr[dr.minyl <= 20].groupby(["game_id", "pos_team"]).agg(rz_trips=("res", "size"), rz_td=("res", lambda s: (s == "TD").mean()))
    out = out.join(rz); out["rz_trips"] = out.rz_trips.fillna(0)
    out = out.reset_index().rename(columns={"pos_team": "team"})
    # dates: the desk's ESPN schedule (same ids) else the play wallclock
    dmap = dict(zip(lt.espn_id.astype(str), lt.gameday.astype(str)))
    wc = d.groupby("game_id").wallclock.min().astype(str).str[:10]
    out["game_date"] = [dmap.get(str(i), wc.get(i)) for i in out.game_id]
    return out


def build(seasons, src=None, merge=True):
    lt = lines_table(); fr = []
    for y in seasons:
        p = os.path.join(src, f"pbp_{y}.parquet") if src else None
        pbp = pd.read_parquet(p if p and os.path.exists(p) else URL.format(y=y), columns=COLS)
        fr.append(team_games(pbp, lt))
    new = pd.concat(fr, ignore_index=True)
    if merge and os.path.exists(TG):
        old = pd.read_csv(TG); new = pd.concat([old[~old.season.isin(seasons)], new], ignore_index=True)
    new = new.sort_values(["game_date", "game_id", "home"]).reset_index(drop=True)
    new.round(5).to_csv(TG, index=False)
    return new


def load_tg():
    t = pd.read_csv(TG)
    t["game_id"] = t.game_id.astype(str)
    return t[t.game_date.notna()]


def load_games(tg=None):
    """Desk CFB lines in the NFL games format (home expected margin = -close_spread)."""
    lt = lines_table(); tg = load_tg() if tg is None else tg
    tg = tg.assign(game_id=tg.game_id.astype(str))
    # team names per game from pbp rows (home flag)
    h = tg[tg.home == 1].drop_duplicates("game_id").set_index("game_id").team
    a = tg[tg.home == 0].drop_duplicates("game_id").set_index("game_id").team
    lt["gid"] = lt.espn_id.astype(str)
    lt = lt[lt.gid.isin(h.index) & lt.gid.isin(a.index)].copy()
    done = lt.completed.astype(str).isin(["1", "True", "true", "1.0"])
    g = pd.DataFrame(dict(
        game_id=lt.gid, season=lt.season, week=lt.week, gameday=lt.gameday.astype(str), gametime="",
        home_team=lt.gid.map(h), away_team=lt.gid.map(a),
        result=np.where(done, lt.home_score - lt.away_score, np.nan), total=np.where(done, lt.home_score + lt.away_score, np.nan),
        spread_line=-lt.close_spread, total_line=lt.close_total,
        home_spread_odds=lt.close_h_sp_price, away_spread_odds=lt.close_a_sp_price, over_odds=np.nan, under_odds=np.nan,
        game_type=np.where(lt.seasontype == 3, "POST", "REG"), neutral=lt.neutral))
    return g.reset_index(drop=True)


def fbs_pool(tg, season):
    """Teams with an FBS schedule: appear in the desk's FBS lines table for that season (or last)."""
    g = load_games(tg)
    g = g[g.season == season - 1] if (g.season == season).sum() < 300 else g[g.season == season]
    c = pd.concat([g.home_team, g.away_team]).value_counts()
    thr = 5 if len(g) > 600 else 3
    return set(c[c >= thr].index)  # FCS teams appear in only 1-2 FBS games a season


def feature_table(seasons):
    tg = load_tg(); games = load_games(tg)
    return M.feature_table(games, tg, seasons, lam=LAM, prior_w=PRIOR_W)


# ---------------------------------------------------------------- live (ESPN scoreboard lines: free)
def _odds(o, mk, side):
    try:
        x = o[mk][side]["close"]["odds"]
        return None if x in (None, "", "OFF", "EVEN") else float(str(x).replace("+", ""))
    except Exception:
        return None


def espn_slate(dates, fbs_only=True):
    import urllib.request
    out = []
    for d in dates:
        u = f"https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?dates={d}&groups=80&limit=300"
        j = json.load(urllib.request.urlopen(u, timeout=30))
        for e in j.get("events", []):
            c = e["competitions"][0]
            if c.get("status", {}).get("type", {}).get("state") != "pre":
                continue
            tm = {x["homeAway"]: x["team"] for x in c["competitors"]}
            o = (c.get("odds") or [{}])[0]
            out.append(dict(espn_id=e["id"], kick_iso=e["date"], home_id=tm["home"]["id"], away_id=tm["away"]["id"],
                            home_name=tm["home"].get("location"), away_name=tm["away"].get("location"),
                            home_disp=tm["home"].get("displayName"), away_disp=tm["away"].get("displayName"),
                            neutral=c.get("neutralSite", False),
                            spread=o.get("spread"), total=o.get("overUnder"), details=o.get("details"),
                            book=(o.get("provider") or {}).get("name"),
                            home_ml=_odds(o, "moneyline", "home"), away_ml=_odds(o, "moneyline", "away"),
                            home_spread_odds=_odds(o, "pointSpread", "home"), away_spread_odds=_odds(o, "pointSpread", "away"),
                            over_odds=_odds(o, "total", "over"), under_odds=_odds(o, "total", "under")))
    return out


def id_to_name():
    """ESPN team id -> cfbfastR name via the desk lines table (ids) joined to pbp team-games (names)."""
    tg = load_tg(); lt = lines_table(); lt["gid"] = lt.espn_id.astype(str)
    h = tg[tg.home == 1].drop_duplicates("game_id").set_index("game_id").team
    a = tg[tg.home == 0].drop_duplicates("game_id").set_index("game_id").team
    m = {}
    for _, r in lt[lt.gid.isin(h.index)].iterrows():
        m[str(r.home_id)] = h[r.gid]
        if r.gid in a.index:
            m[str(r.away_id)] = a[r.gid]
    return m


def live(now=None, days=7):
    """FBS games in the next `days` days with ESPN (DraftKings) lines: free, 0 Odds API credits."""
    from zoneinfo import ZoneInfo
    CT = ZoneInfo("America/Chicago")
    now = (now or dt.datetime.now(CT)).astimezone(CT)
    tg = load_tg(); games = load_games(tg); CR = M.cover_rows(games)
    Mo = json.load(open(MODEL)) if os.path.exists(MODEL) else None
    names = id_to_name()
    slate = espn_slate([(now + dt.timedelta(days=i)).strftime("%Y%m%d") for i in range(days + 1)])
    season = now.year if now.month >= 3 else now.year - 1
    pool = fbs_pool(tg, season)
    out, R = [], None
    asof = now.strftime("%Y-%m-%d")
    R = M.ratings(tg, asof, season, lam=LAM, prior_w=PRIOR_W, pool=pool)
    R["press_desc"] = "sack rate per dropback (no pressure data in CFB pbp)"
    for e in slate:
        h, a = names.get(str(e["home_id"])), names.get(str(e["away_id"]))
        if not h or not a:
            continue
        f = M.features(R, CR, h, a, asof, season)
        if f is None:
            continue
        ls = lt = None
        if Mo:
            ls = float(M.predict(Mo["spread"]["model"], [[f[c] for c in Mo["spread"]["features"]]])[0])
            lt = float(M.predict(Mo["total"]["model"], [[f[c] for c in Mo["total"]["features"]]])[0])
        sp = e.get("spread")
        kick = dt.datetime.fromisoformat(e["kick_iso"].replace("Z", "+00:00")).astimezone(CT)
        g = pd.Series(dict(home_team=h, away_team=a))
        out.append(dict(sport="cfb", game=f"{a} @ {h}", home=h, away=a, espn_id=e["espn_id"], kick_iso=kick.isoformat(),
                        gameday=kick.strftime("%Y-%m-%d"), gametime=kick.strftime("%-I:%M %p CT"), neutral=e["neutral"],
                        spread_line=None if sp is None else -float(sp), total_line=e.get("total"), line_src=f"ESPN ({e.get('book') or 'n/a'})",
                        styles={h: M.style_label(R, h), a: M.style_label(R, a)}, edges=M.edges(R, h, a),
                        ranks={t: M.unit_ranks(R, t) for t in (h, a)},
                        similar=dict(home=round(f["sim_home"], 2), away=round(f["sim_away"], 2), n_home=round(f["sim_n_home"], 1), n_away=round(f["sim_n_away"], 1)),
                        common_opponents=M.comopp(CR, h, a, asof, season)[1], comopp_gap=round(f["comopp_gap"], 2),
                        lean_spread_pts=None if ls is None else round(ls, 2), lean_total_pts=None if lt is None else round(lt, 2),
                        lean_text=M.lean_text(g, ls, lt), features={k: round(float(v), 5) for k, v in f.items()},
                        **{k: e.get(k) for k in ("home_ml", "away_ml", "home_spread_odds", "away_spread_odds", "over_odds", "under_odds")}))
    return dict(generated_ct=now.strftime("%a %b %-d %Y %-I:%M %p CT"), status=(Mo or {}).get("status", "INFO ONLY"),
                influence=bool((Mo or {}).get("influence", False)), backtest=(Mo or {}).get("backtest_summary"),
                games=out, data_through=str(tg.game_date.max()), n_fbs=len(pool))
