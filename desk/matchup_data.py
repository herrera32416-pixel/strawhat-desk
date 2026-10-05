"""MATCHUP data: nflverse play-by-play -> one row per team-game (offense perspective).
The defense view of a game is simply the opponent's offense row. Free data, no Odds API.

Columns per (game_id, team=posteam): dropbacks, pass EPA/play + success rate, designed-run EPA + SR,
sack rate and pressure proxy (sack or QB hit per dropback; nflverse has no charted pressure before 2022),
neutral early-down pass rate (downs 1-2, win prob 20-80%, Q1-3), explosive-play rate (pass >= 20 yds,
run >= 10 yds), red-zone TD rate (drives that reached the 20 -> TD), points.
Usage: python -m desk.matchup_data [--seasons 2015-2026] [--src DIR]   (writes data/matchup/team_games.csv.gz)
The daily run refreshes only the current season (one ~5-20 MB download)."""
import os, sys, argparse
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "matchup", "team_games.csv.gz")
URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{y}.parquet"
TEAM_FIX = {"OAK": "LV", "SD": "LAC", "STL": "LA", "LAR": "LA", "JAC": "JAX", "WSH": "WAS"}
COLS = ["game_id", "season", "week", "season_type", "game_date", "posteam", "defteam", "home_team", "away_team",
        "pass", "rush", "qb_dropback", "qb_scramble", "epa", "success", "sack", "qb_hit", "yards_gained", "down",
        "wp", "yardline_100", "fixed_drive", "fixed_drive_result", "qtr", "play_type", "two_point_attempt",
        "total_home_score", "total_away_score"]


def fix(t):
    return TEAM_FIX.get(t, t)


def load_season(y, src=None):
    p = os.path.join(src, f"pbp_{y}.parquet") if src else None
    if p and os.path.exists(p):
        return pd.read_parquet(p, columns=COLS)
    return pd.read_parquet(URL.format(y=y), columns=COLS)


def team_games(pbp):
    d = pbp[pbp.posteam.notna() & pbp.epa.notna() & (pbp.two_point_attempt != 1)].copy()
    for c in ("posteam", "defteam", "home_team", "away_team"):
        d[c] = d[c].map(fix)
    d = d[d.play_type.isin(["pass", "run", "no_play"]) & ((d["pass"] == 1) | (d["rush"] == 1))]
    db = d["qb_dropback"] == 1
    run = (d["rush"] == 1) & (d["qb_scramble"] != 1) & ~db
    d["is_db"], d["is_run"] = db.astype(float), run.astype(float)
    d["press"] = ((d["sack"] == 1) | (d["qb_hit"] == 1)).astype(float) * d["is_db"]
    d["expl"] = (((d["pass"] == 1) & (d["yards_gained"] >= 20)) | (run & (d["yards_gained"] >= 10))).astype(float)
    neu = d["down"].isin([1, 2]) & d["wp"].between(0.2, 0.8) & (d["qtr"] <= 3)
    d["neu"], d["neu_pass"] = neu.astype(float), (neu & db).astype(float)
    g = d.groupby(["game_id", "posteam"])
    out = pd.DataFrame({
        "season": g["season"].first(), "week": g["week"].first(), "season_type": g["season_type"].first(),
        "game_date": g["game_date"].first(), "opp": g["defteam"].first(),
        "home": (g["posteam"].first() == g["home_team"].first()).astype(int),
        "plays": g.size(), "dropbacks": g["is_db"].sum(), "runs": g["is_run"].sum(),
    })
    def wmean(col, mask):
        x = d[col] * d[mask]
        return x.groupby([d.game_id, d.posteam]).sum() / d[mask].groupby([d.game_id, d.posteam]).sum().replace(0, np.nan)
    out["pass_epa"], out["pass_sr"] = wmean("epa", "is_db"), wmean("success", "is_db")
    out["rush_epa"], out["rush_sr"] = wmean("epa", "is_run"), wmean("success", "is_run")
    out["sack_rate"] = wmean("sack", "is_db")
    out["press_rate"] = (d["press"].groupby([d.game_id, d.posteam]).sum() / out["dropbacks"].replace(0, np.nan))
    out["expl_rate"] = g["expl"].mean()
    out["ed_pass_rate"] = (d["neu_pass"].groupby([d.game_id, d.posteam]).sum() / d["neu"].groupby([d.game_id, d.posteam]).sum().replace(0, np.nan))
    # red zone: drives whose min yardline_100 <= 20
    dr = d.groupby(["game_id", "posteam", "fixed_drive"]).agg(minyl=("yardline_100", "min"), res=("fixed_drive_result", "first"))
    rz = dr[dr.minyl <= 20]
    rzg = rz.groupby(["game_id", "posteam"]).agg(rz_trips=("res", "size"), rz_td=("res", lambda s: (s == "Touchdown").mean()))
    out = out.join(rzg)
    out["rz_trips"] = out["rz_trips"].fillna(0)
    # points from final score
    fs = pbp.groupby("game_id").agg(hs=("total_home_score", "max"), as_=("total_away_score", "max"))
    out = out.reset_index().rename(columns={"posteam": "team"})
    out = out.merge(fs, left_on="game_id", right_index=True, how="left")
    out["points"] = np.where(out.home == 1, out.hs, out.as_)
    out["opp_points"] = np.where(out.home == 1, out.as_, out.hs)
    return out.drop(columns=["hs", "as_"])


def build(seasons, src=None, merge=True):
    fr = [team_games(load_season(y, src)) for y in seasons]
    new = pd.concat(fr, ignore_index=True)
    if merge and os.path.exists(OUT):
        old = pd.read_csv(OUT)
        old = old[~old.season.isin(seasons)]
        new = pd.concat([old, new], ignore_index=True)
    new = new.sort_values(["game_date", "game_id", "home"]).reset_index(drop=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    new.round(5).to_csv(OUT, index=False)
    return new


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default="2015-2026")
    ap.add_argument("--src", default=None)
    a = ap.parse_args()
    lo, hi = (a.seasons.split("-") + [a.seasons])[:2]
    t = build(range(int(lo), int(hi) + 1), a.src)
    print(len(t), "team-games;", t.season.min(), "-", t.season.max())
