"""SIM panel: 1,000 simulations per upcoming NFL and FBS game (desk/sim.py), INFO ONLY.
Lines: NFL = nflverse schedule lines (free; includes next week's lookahead lines), FBS = ESPN/DraftKings lines on
the ESPN scoreboard (free). 0 Odds API credits. Market % = de-vigged odds where the source gives them (else -110),
market win % = de-vigged moneyline (else the KEYS spread->ML conversion)."""
import os, json, datetime as dt
import numpy as np
from zoneinfo import ZoneInfo
from desk import sim, matchup, matchup_cfb
from desk.keys import Dist

ROOT = matchup.ROOT
CT = ZoneInfo("America/Chicago")


def _f(x):
    try:
        return None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)
    except Exception:
        return None


def game_row(g, sport, D, S=1000):
    Dm, Dt = D
    sl, tl = _f(g.get("spread_line")), _f(g.get("total_line"))
    if sl is None or tl is None:
        return None
    q_c = sim.devig(_f(g.get("home_spread_odds")), _f(g.get("away_spread_odds")))
    q_o = sim.devig(_f(g.get("over_odds")), _f(g.get("under_odds")))
    import zlib
    rng = np.random.default_rng(zlib.crc32(g["game"].encode()))
    r = sim.run_game(sport, sl, tl, Dm, Dt, g.get("features"), g.get("lean_spread_pts") or 0.0, g.get("lean_total_pts") or 0.0, q_c, q_o, S, rng)
    hm, am = _f(g.get("home_ml")), _f(g.get("away_ml"))
    if hm is not None and am is not None:
        mkt_win, win_src = sim.devig(hm, am), "de-vigged moneyline"
    else:
        c = Dm.anchor(sl, q_c); w, pu, l = Dm.probs(c, 0)
        mkt_win, win_src = w + pu / 2, "KEYS spread->ML (no moneyline in source)"
    rd = lambda x: round(x, 4)
    return dict(sport=sport, game=g["game"], home=g["home"], away=g["away"], when=f"{g['gameday']} {g.get('gametime') or ''}".strip(),
                line_src=g.get("line_src"), home_line=-sl, total_line=tl,
                sim_home_win=rd(r["home_win"]), mkt_home_win=rd(mkt_win), win_src=win_src, d_win=rd(r["home_win"] - mkt_win),
                sim_home_cover=rd(r["home_cover_ex_push"]), mkt_home_cover=rd(q_c), d_cover=rd(r["home_cover_ex_push"] - q_c), cover_push=rd(r["cover_push"]),
                sim_over=rd(r["over_ex_push"]), mkt_over=rd(q_o), d_over=rd(r["over_ex_push"] - q_o), total_push=rd(r["total_push"]),
                home_pts_median=r["home_pts_median"], away_pts_median=r["away_pts_median"],
                home_pts_10_90=r["home_pts_10_90"], away_pts_10_90=r["away_pts_10_90"],
                margin_10_90=r["margin_10_90"], total_10_90=r["total_10_90"], n_sims=r["n_sims"], n_eff=r["n_eff"],
                lean_spread_pts=g.get("lean_spread_pts"), lean_total_pts=g.get("lean_total_pts"))


def run(now=None, nfl=None, cfb=None, write=True):
    now = (now or dt.datetime.now(CT)).astimezone(CT)
    nfl = nfl if nfl is not None else matchup.live(now, write=False)
    cfb = cfb if cfb is not None else matchup_cfb.live(now)
    yr = now.year if now.month >= 3 else now.year - 1
    D = {"nfl": (Dist("nfl_margin", max_season=yr - 1, tilt=True), Dist("nfl_total", max_season=yr - 1, tilt=True)),
         "cfb": (Dist("cfb_margin", max_season=yr - 1, tilt=True), Dist("cfb_total", max_season=yr - 1, tilt=True))}
    rows = []
    for sport, src in (("nfl", nfl), ("cfb", cfb)):
        for g in src.get("games", []):
            r = game_row(g, sport, D[sport])
            if r:
                rows.append(r)
    try:
        bt = json.load(open(os.path.join(ROOT, "data", "sim_backtest.json")))
    except Exception:
        bt = {}
    res = dict(generated_ct=now.strftime("%a %b %-d %Y %-I:%M %p CT"), status="INFLUENCES PICKS" if bt.get("nfl", {}).get("passes") or bt.get("cfb", {}).get("passes") else "INFO ONLY",
               n_sims_per_game=1000, games=rows, backtest=summary(bt),
               lines_note="NFL: nflverse schedule lines (incl. next-week lookahead). FBS: ESPN scoreboard DraftKings lines. No Odds API credits used.")
    if write:
        json.dump(res, open(os.path.join(ROOT, "docs", "data", "sim.json"), "w"))
    return res


def summary(bt):
    out = {}
    for sp in ("nfl", "cfb"):
        b = bt.get(sp)
        if not b:
            continue
        s, t = b["spread_sim+matchup"], b["total_sim+matchup"]
        out[sp] = (f"OOS {b['oos']}: spread log loss {s['logloss_sim']:.4f} vs market {s['logloss_market']:.4f} "
                   f"(CI {s['ll_improvement_ci90'][0]:+.4f}..{s['ll_improvement_ci90'][1]:+.4f}), |gap|>=3pp bets {s['bets_gap>=3pp']['w']}-{s['bets_gap>=3pp']['l']} "
                   f"{s['bets_gap>=3pp']['units']:+.1f}u; total {t['logloss_sim']:.4f} vs {t['logloss_market']:.4f} "
                   f"(CI {t['ll_improvement_ci90'][0]:+.4f}..{t['ll_improvement_ci90'][1]:+.4f}), bets {t['bets_gap>=3pp']['w']}-{t['bets_gap>=3pp']['l']} "
                   f"{t['bets_gap>=3pp']['units']:+.1f}u. Passes criteria: {'yes' if b['passes'] else 'no'}.")
    return out


if __name__ == "__main__":
    r = run()
    print(r["status"], len(r["games"]))
