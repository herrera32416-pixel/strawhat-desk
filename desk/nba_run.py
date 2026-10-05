"""NBA daily (INFO ONLY). Before opening night (Tue Oct 20 2026) it publishes 'season starts Oct 20', the backtest and
last season's closing unit ranks. As soon as ESPN lists regular-season games within 36h it starts automatically:
results refresh (ESPN, free) -> lines (<= 4 credits, once per CT day) -> walk-forward features -> possession sim
(1,000 sims/game) -> docs/data/nba.json."""
import datetime as dt, json, os
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd
from . import nba_data, nba_match as nm, nba_sim, pro_lines, pro_ratings as pr

CT = ZoneInfo("America/Chicago")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "docs", "data", "nba.json")
OPENING = "2026-10-20"
ESPN_FIX = {"GS": "GS", "NO": "NO", "NY": "NY", "SA": "SA", "UTAH": "UTAH", "WSH": "WSH"}


def odds_name_map(G):
    m = {}
    for h, hn in zip(G.home, G.home_name):
        m[hn] = h
    m["LA Clippers"] = m.get("LA Clippers", "LAC"); m["Los Angeles Clippers"] = m.get("LA Clippers", "LAC")
    return m


def rank(s, higher_better=True):
    return s.rank(ascending=not higher_better, method="min").astype(int)


GOOD_HIGH = {"ortg": True, "pace": True, "efg": True, "tov_pct": False, "orb_pct": True, "ftr": True, "tpar": True, "tp_pct": True, "paint": True, "fbp": True}


def unit_ranks(Rd, t):
    k = Rd.index[Rd.team == t][0]
    out = {}
    for m in nm.METRICS:
        hb = GOOD_HIGH[m]
        out[m] = dict(o_rank=int(rank(Rd["O_" + m], hb).iloc[k]), d_rank=int(rank(Rd["D_" + m], not hb).iloc[k]))
    out["n_games"] = int(Rd.n_cur.iloc[k])
    return out


def mismatches(h, a, Rd):
    notes, n = [], len(Rd)
    for off, de in ((h, a), (a, h)):
        U, V = unit_ranks(Rd, off), unit_ranks(Rd, de)
        for m, lab, dlab in (("tpar", "3-point volume", "3-point attempts allowed"), ("tp_pct", "3-point shooting", "3-point defense"),
                             ("orb_pct", "offensive rebounding", "defensive rebounding"), ("paint", "paint scoring", "rim protection (paint pts allowed)"),
                             ("tov_pct", "ball security", "turnover forcing"), ("ftr", "getting to the line", "fouling discipline"),
                             ("ortg", "offense (pts/100)", "defense (pts/100 allowed)")):
            ro, rd = U[m]["o_rank"], V[m]["d_rank"]
            if ro <= 7 and rd >= n - 6:
                notes.append(f"{off} {lab} (#{ro}) vs {de} {dlab} (#{rd} of {n}): strength meets weakness, edge {off}")
            elif ro >= n - 6 and rd <= 7:
                notes.append(f"{off} {lab} (#{ro}) runs into {de} {dlab} (#{rd}): edge {de}")
    ph, pa = unit_ranks(Rd, h)["pace"]["o_rank"], unit_ranks(Rd, a)["pace"]["o_rank"]
    if abs(ph - pa) >= 18:
        fast, slow = (h, a) if ph < pa else (a, h)
        notes.append(f"pace clash: {fast} plays fast (#{min(ph, pa)}), {slow} slow (#{max(ph, pa)})")
    return notes


def bt_summary(bt):
    keep = ("n", "ll_model", "ll_market", "ll_improve_ci90", "bets", "wins", "win_pct", "breakeven", "units", "roi", "roi_ci90", "seasons_positive", "by_season")
    return dict({k: {kk: bt[k].get(kk) for kk in keep} for k in ("spread", "total", "ml")}, verdict=bt["verdict"], sim_check=bt.get("sim_check"),
                coverage=bt.get("coverage"))


def main(now=None, pull=True):
    now = now or dt.datetime.now(dt.timezone.utc)
    nct = now.astimezone(CT)
    season = nct.year if nct.month >= 8 else nct.year - 1
    notes = []
    model = json.load(open(os.path.join(nm.D, "model.json")))
    bt = json.load(open(os.path.join(ROOT, "backtest", "out", "nba_bt.json")))
    up = []
    try:
        up = [g for g in nba_data.upcoming(2) if 0 < (dt.datetime.fromisoformat(g["date_utc"].replace("Z", "+00:00")) - now).total_seconds() <= 36 * 3600]
    except Exception as ex:
        notes.append(f"ESPN schedule error {ex!r}")
    out = dict(sport="nba", generated_ct=nct.strftime("%a %b %-d %Y %-I:%M %p CT"), status=model["status"], influence=model["influence"],
               backtest=bt_summary(bt), opening_night=OPENING, games=[], notes=notes)
    T, G = nm.load_team_games(), nm.load_games()
    if not up:
        out["season_note"] = f"Season starts Tue Oct 20 2026. Sims start automatically when ESPN lists the first games (within 36h)." \
            if nct.strftime("%Y-%m-%d") < OPENING else "No NBA regular-season games within 36h."
        # last season's closing unit ranks (end of 2025-26), for reference
        last = G.date.max()
        stub = pd.DataFrame([dict(espn_id="0", season=season, date=(pd.Timestamp(last) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"), team=t, opp=t, home=0)
                             for t in sorted(set(T[T.season == season - 1].team))])
        notes.append(f"no games within 36h; data through {last}")
        json.dump(out, open(SITE, "w"), default=float)
        return out, notes
    if pull:
        try:
            k = nba_data.refresh(season)
            notes.append(f"ESPN results refresh: {k} games")
            T, G = nm.load_team_games(), nm.load_games()
        except Exception as ex:
            notes.append(f"results refresh failed {ex!r}")
        notes.append("LINES: " + pro_lines.pull("nba", now))
    J, path = pro_lines.latest("nba")
    out["odds_asof"] = (J or {}).get("pulled_ct")
    nmap = odds_name_map(G)
    P = nba_sim.load_params()
    live = []
    for g in up:
        e = next((x for x in (J or {}).get("data", []) if nmap.get(x["home_team"]) == g["home"] and nmap.get(x["away_team"]) == g["away"]), None)
        c = pro_lines.consensus(e) if e else None
        if not c or not c.get("spread") or not c.get("total"):
            out["games"].append(dict(home=g["home"], away=g["away"], no_line=True, start_ct=_ct(g["date_utc"]), note="no saved line yet (never invented)"))
            continue
        live.append((g, c))
    if live:
        L = pd.DataFrame([dict(espn_id=g["espn_id"], season=season, date=(pd.Timestamp(g["date_utc"]) - pd.Timedelta(hours=5)).strftime("%Y-%m-%d"),
                               home=g["home"], away=g["away"]) for g, c in live])
        hist = G[G.season >= season - 1].dropna(subset=["home_score"])
        gF, R = nm.build(T, pd.concat([hist, L], ignore_index=True))
        for (g, c), (_, f) in zip(live, gF[gF.home_score.isna()].set_index("espn_id").loc[L.espn_id].reset_index().iterrows()):
            out["games"].append(card(g, c, f, model, P, R))
    json.dump(out, open(SITE, "w"), default=float)
    return out, notes


def _ct(iso):
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(CT).strftime("%a %b %-d %-I:%M %p CT")


def lean(model, f, part):
    m = model[part]
    x = np.array([0.0 if pd.isna(f.get(k)) else float(f[k]) for k in m["features"]])
    return float(((x - np.array(m["mean"])) / np.array(m["sd"])) @ np.array(m["beta"]))


def card(g, c, f, model, P, R):
    sp, tl = c["spread"]["line"], c["total"]["line"]
    ls, lt = lean(model, f, "spread"), lean(model, f, "total")
    S = nba_sim.Sim(P, n=1000, seed=int(g["espn_id"]) % 100000)
    cm, ct = S.anchor(sp, c["spread"]["q"], tl, c["total"]["q"])
    m0, t0 = S.run(cm, ct)
    m1, t1 = S.run(cm + ls, ct + lt)
    s0, s1 = nba_sim.summarize(m0, t0, sp, tl), nba_sim.summarize(m1, t1, sp, tl)
    Rd = R[R.date == f["date"]].reset_index(drop=True)
    dk = c["target"].get("draftkings", {})
    return dict(home=g["home"], away=g["away"], start_ct=_ct(g["date_utc"]),
                market=dict(spread_home=sp, cover=c["spread"]["q"], total=tl, over=c["total"]["q"], src=c["spread"]["src"], n_books=c["n_books"],
                            dk=dict(spreads=dk.get("spreads"), totals=dk.get("totals"))),
                sim_market_only=s0, sim=s1, lean=dict(spread_pts=ls, total_pts=lt),
                delta=dict(cover=s1["p_home_cover"] - c["spread"]["q"], over=s1["p_over"] - c["total"]["q"], home_win=s1["p_home_win"] - s0["p_home_win"]),
                rest=dict(home=_n(f.get("rest_h")), away=_n(f.get("rest_a")), b2b_home=_n(f.get("b2b_h")), b2b_away=_n(f.get("b2b_a"))),
                similar_style=dict(home=_n(f.get("sim_h")), away=_n(f.get("sim_a"))), common_opp=dict(gap=_n(f.get("co_gap")), n=_n(f.get("co_n"))),
                units={g["home"]: unit_ranks(Rd, g["home"]), g["away"]: unit_ranks(Rd, g["away"])}, mismatches=mismatches(g["home"], g["away"], Rd))


def _n(x):
    try:
        return None if pd.isna(x) else round(float(x), 3)
    except Exception:
        return None


if __name__ == "__main__":
    import sys
    o, n = main(pull="--no-pull" not in sys.argv)
    print("\n".join(n)); print(len(o["games"]), "games")
