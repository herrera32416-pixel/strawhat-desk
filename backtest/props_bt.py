"""Props backtest.
(1) Projection walk-forward on 2025 + 2026 wk1-4 (fit on prior data): MAE vs naive EWMA, calibration.
(2) Model vs market on the only free real prop lines on disk: Odds API pulls saved by the old desk for
    2026-09-20 (week 2, 8 books) and 2026-09-27 (week 3, DK/FanDuel/BetRivers). Brier/log loss vs no-vig,
    and flat-1u units at the real DK price on edge rules."""
import sys, os, json, math, random, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from desk.props import *
from desk.market import novig

games = pd.read_csv("data/history/nfl_games.csv", low_memory=False)
d = load_stats([2023, 2024, 2025, 2026])
t = team_table(d, games)
pf = player_features(d, t)
league = {c: t[c].mean() for c in ["ypt", "ypc", "ypa", "cr", "tds"]}
tidx = t.set_index(["game_id", "team"])


def proj_rows(pf, coefs, mask):
    R = []
    sub = pf[mask & (pf.n_prior >= 2)]
    for _, row in sub.iterrows():
        try:
            tr = tidx.loc[(row.game_id, row.team)]
            orow = tidx.loc[(row.game_id, row.opponent_team)]
        except KeyError:
            continue
        if any(pd.isna([tr.e_pass_att, tr.e_carries, tr.exp_margin, tr.implied])):
            continue
        va = coefs["pass_att"] @ [1, tr.e_pass_att, tr.exp_margin, tr.implied]
        vc = coefs["carries"] @ [1, tr.e_carries, tr.exp_margin, tr.implied]
        # opponent defense = what the opponent allowed prior: stored on rows where opponent_team == opponent
        df = dfactors(tidx.loc[(row.game_id, row.team)].to_dict(), league)
        p = project(row, va, vc, df)
        base = dict(player=row.player_display_name, pkey=row.pkey, pos=row.position, season=row.season, week=row.week,
                    team=row.team, game_id=row.game_id)
        for m, col in [("receiving_yards", "receiving_yards"), ("receptions", "receptions"), ("rushing_yards", "rushing_yards"),
                       ("passing_yards", "passing_yards"), ("passing_tds", "passing_tds")]:
            naive = row[f"e_{col}"]
            if p[m] <= 0.05 and (pd.isna(naive) or naive <= 0.05):
                continue
            R.append(dict(base, market=m, proj=p[m], naive=naive, actual=row[col]))
        R.append(dict(base, market="anytime_td", proj=p["tds_mean"], naive=row.e_tds, actual=row.anytime_td))
    return pd.DataFrame(R)


out = {}
# training: 2023 wk5+ .. 2024 -> fit volume + ratio dists; test 2025 (refit on <=2024); 2026 (refit on <=2025)
res = []
for test_season in (2025, 2026):
    tr_t = t[t.season < test_season]
    coefs = fit_volume(tr_t)
    train = proj_rows(pf, coefs, (pf.season < test_season) & (pf.order >= 202305))
    rd = RatioDist(); rd.fit(train)
    test = proj_rows(pf, coefs, pf.season == test_season)
    test["season_fit"] = test_season
    res.append((test_season, coefs, rd, test))
    print(test_season, "train rows", len(train), "test rows", len(test))

summ = []
for season, coefs, rd, test in res:
    for m, g in test.groupby("market"):
        g = g[g.actual.notna()]
        if m == "anytime_td":
            continue
        summ.append(dict(season=season, market=m, n=len(g), mae_model=round((g.proj - g.actual).abs().mean(), 2),
                         mae_naive_ewma=round((g.naive.fillna(0) - g.actual).abs().mean(), 2),
                         mean_proj=round(g.proj.mean(), 2), mean_actual=round(g.actual.mean(), 2)))
pd.DataFrame(summ).to_csv("backtest/out/props_projection_mae.csv", index=False)
print(pd.DataFrame(summ).to_string())

# ---- market test on saved lines (2026 weeks 2-3) ----
coefs26, rd26, test26 = res[1][1], res[1][2], res[1][3]
lines = []
s20 = json.load(open("/workspace/bet-bot/research/sun-sep20-nfl-props.json"))
for p in s20["props"]:
    lines.append(dict(week=2, player=p["player"], market="player_" + p["market"] if not p.get("market_key") else p["market_key"],
                      line=p.get("line"), side=p.get("side"), dk=p.get("draftkings_price"), other=p.get("other_prices") or {},
                      fd=p.get("fanduel_price")))
raw27 = json.load(open("/workspace/bet-bot/research/_scratch/sun27/toa_nfl_props_raw_20260927_0858ct.json"))
for e in raw27["events"]:
    for b in e["bookmakers"]:
        for mk in b["markets"]:
            for o in mk["outcomes"]:
                lines.append(dict(week=3, player=o.get("description"), market=mk["key"], line=o.get("point"),
                                  side=o["name"].lower(), book=b["key"], price=o["price"]))
L = pd.DataFrame(lines)
print("saved prop rows", len(L), L.week.value_counts().to_dict())
L.to_csv("backtest/out/props_saved_lines_flat.csv", index=False)
import pickle
pickle.dump({"res": res, "league": league}, open("backtest/out/props_models.pkl", "wb"))
