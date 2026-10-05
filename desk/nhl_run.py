"""NHL daily (INFO ONLY): refresh free data -> today's/tomorrow's slate (NHL API) -> lines (cached or <= 4 credits) ->
walk-forward ratings + matchup features -> market-anchored sim (1,000 sims/game) -> docs/data/nhl.json."""
import datetime as dt, json, os, traceback
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd
from . import nhl_data, nhl_match as nm, nhl_sim, pro_lines, pro_ratings as pr

CT = ZoneInfo("America/Chicago")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "docs", "data", "nhl.json")
NAMES = {"Anaheim Ducks": "ANA", "Boston Bruins": "BOS", "Buffalo Sabres": "BUF", "Carolina Hurricanes": "CAR", "Columbus Blue Jackets": "CBJ",
         "Calgary Flames": "CGY", "Chicago Blackhawks": "CHI", "Colorado Avalanche": "COL", "Dallas Stars": "DAL", "Detroit Red Wings": "DET",
         "Edmonton Oilers": "EDM", "Florida Panthers": "FLA", "Los Angeles Kings": "LAK", "Minnesota Wild": "MIN", "Montréal Canadiens": "MTL",
         "Montreal Canadiens": "MTL", "New Jersey Devils": "NJD", "Nashville Predators": "NSH", "New York Islanders": "NYI", "New York Rangers": "NYR",
         "Ottawa Senators": "OTT", "Philadelphia Flyers": "PHI", "Pittsburgh Penguins": "PIT", "Seattle Kraken": "SEA", "San Jose Sharks": "SJS",
         "St Louis Blues": "STL", "St. Louis Blues": "STL", "Tampa Bay Lightning": "TBL", "Toronto Maple Leafs": "TOR", "Utah Mammoth": "UTA",
         "Utah Hockey Club": "UTA", "Vancouver Canucks": "VAN", "Vegas Golden Knights": "VGK", "Winnipeg Jets": "WPG", "Washington Capitals": "WSH"}


ACTIVE = set()


def slate(now):
    """NHL API schedule: regular-season games not yet started, today and tomorrow (CT)."""
    d0 = now.astimezone(CT).date()
    j = json.loads(nhl_data.http(f"https://api-web.nhle.com/v1/schedule/{d0.isoformat()}", 30))
    out = []
    for day in j.get("gameWeek", [])[:2]:
        for g in day.get("games", []):
            if g.get("gameType") != 2:
                continue
            st = dt.datetime.fromisoformat(g["startTimeUTC"].replace("Z", "+00:00"))
            if st <= now:
                continue
            out.append(dict(gameId=g["id"], start=st, date=day["date"], home=nhl_data.fx(g["homeTeam"]["abbrev"]), away=nhl_data.fx(g["awayTeam"]["abbrev"])))
    return out


def projected_starters(GL, team, date):
    """Most-used starter over the team's last 10 games; on the 2nd night of a back-to-back, the other goalie
    (desk rule: expect the backup unless confirmed). Returns (pid, name, note)."""
    x = GL[(GL.team == team) & (GL.gs == 1) & (GL.date < date)].sort_values("date")
    if x.empty:
        return None, None, "no starts logged"
    last10 = x.tail(10)
    order = last10.groupby(["pid", "name"]).size().sort_values(ascending=False)
    (pid, name) = order.index[0]
    last_date = x.date.iloc[-1]
    b2b = (pd.Timestamp(date) - pd.Timestamp(last_date)).days == 1
    if b2b and x.pid.iloc[-1] == pid and len(order) > 1:
        (pid, name) = order.index[1]
        return pid, name, "projected: back-to-back, backup expected (not confirmed)"
    if b2b and x.pid.iloc[-1] == pid:
        alt = x[x.pid != pid].tail(20)
        if len(alt):
            r = alt.groupby(["pid", "name"]).size().sort_values(ascending=False).index[0]
            return r[0], r[1], "projected: back-to-back, backup expected (not confirmed)"
    return pid, name, "projected from recent starts (not confirmed)"


def rank(series, higher_better=True):
    return series.rank(ascending=not higher_better, method="min").astype(int)


def mismatches(h, a, Rd, gh, ga):
    """Plain-English strength-vs-weakness notes from current unit ranks (1 = best of 32)."""
    notes = []
    O = {m: rank(Rd["O_" + m], True) for m in nm.METRICS}
    Dk = {m: rank(Rd["D_" + m], False) for m in nm.METRICS}   # D = what a team concedes: lower is better
    idx = {t: k for k, t in enumerate(Rd.team)}
    n = len(Rd)
    for off, de in ((h, a), (a, h)):
        for m, lab, dlab in (("xgf60_e", "5v5 chance creation", "5v5 chance suppression"), ("hdf60_e", "5v5 high-danger chances", "high-danger defense"),
                             ("pp_xg", "power play", "penalty kill"), ("pp_min", "drawing penalties", "discipline")):
            ro, rd = int(O[m].iloc[idx[off]]), int(Dk[m].iloc[idx[de]])
            if ro <= 8 and rd >= n - 7:
                notes.append(f"{off} {lab} (#{ro}) vs {de} {dlab} (#{rd} of {n}): strength meets weakness, edge {off}")
            elif ro >= n - 7 and rd <= 8:
                notes.append(f"{off} {lab} (#{ro}) runs into {de} {dlab} (#{rd}): edge {de}")
    if gh is not None and ga is not None and abs(gh - ga) >= 0.25:
        better = h if gh > ga else a
        notes.append(f"goalie edge {better}: projected starter GSAx/game {gh:+.2f} vs {ga:+.2f}")
    return notes


def main(now=None, pull=True):
    now = now or dt.datetime.now(dt.timezone.utc)
    nct = now.astimezone(CT)
    season = nct.year if nct.month >= 8 else nct.year - 1
    notes = []
    if pull:
        notes += nhl_data.refresh(season)
    S = slate(now)
    soon = [g for g in S if (g["start"] - now).total_seconds() <= 36 * 3600]
    notes.append(f"slate: {len(S)} upcoming (today/tomorrow), {len(soon)} within 36h")
    lines_note = pro_lines.pull("nhl", now) if (pull and soon) else "no pull"
    notes.append(f"LINES: {lines_note}")
    J, path = pro_lines.latest("nhl")
    model = json.load(open(os.path.join(nm.D, "model.json")))
    bt = json.load(open(os.path.join(ROOT, "backtest", "out", "nhl_bt.json")))
    P = model["sim_params"]
    ev = {}
    for e in (J or {}).get("data", []):
        h, a = NAMES.get(e["home_team"]), NAMES.get(e["away_team"])
        if h and a:
            ev[(h, a, e["commence_time"][:13])] = e
    rows = []
    for g in S:
        e = next((v for (h, a, t), v in ev.items() if h == g["home"] and a == g["away"] and abs((dt.datetime.fromisoformat(t + ":00+00:00") - g["start"]).total_seconds()) < 6 * 3600), None)
        c = pro_lines.consensus(e) if e else None
        if not c or not c.get("h2h") or not c.get("total"):
            rows.append(dict(g, consensus=c)); continue
        rows.append(dict(g, consensus=c, ml_q=c["h2h"]["q"], total=c["total"]["line"], q_over=c["total"]["q"]))
    out = dict(sport="nhl", generated_ct=nct.strftime("%a %b %-d %Y %-I:%M %p CT"), odds_file=os.path.basename(path) if path else None,
               odds_asof=(J or {}).get("pulled_ct"), status=model["status"], influence=model["influence"], backtest=bt_summary(bt), notes=notes, games=[])
    priced = [r for r in rows if r.get("ml_q") is not None]
    if priced:
        T = nm.load_team_games()
        ACTIVE.clear(); ACTIVE.update(set(T[T.season >= season - 1].team) - {"ARI"} | {"UTA"})
        GL = pd.read_csv(os.path.join(nm.D, "goalies.csv.gz"))
        GR, hist = nm.goalie_ratings(T, GL)
        GR = GR.merge(GL[["gameId", "date"]].drop_duplicates("gameId"), on="gameId")
        live_g = []
        for r in priced:
            for team in (r["home"], r["away"]):
                pid, name, note = projected_starters(GL, team, r["date"])
                live_g.append(dict(date=r["date"], team=team, g_rating=nm.goalie_rating_now(hist, pid, season) if pid else 0.0, goalie=name, gnote=note))
        LG = pd.DataFrame(live_g)
        GRall = pd.concat([GR[["date", "team", "g_rating", "goalie"]], LG[["date", "team", "g_rating", "goalie"]]])
        L = pd.read_csv(os.path.join(nm.D, "lines.csv"))
        L = L[L.season >= season - 1].dropna(subset=["ml_home", "ml_away", "home_score"])
        med = L.total.median()
        L["total_fill"] = med
        live = pd.DataFrame([dict(date=r["date"], season=season, home=r["home"], away=r["away"], ml_home=None, ml_away=None,
                                  total=r["total"], over_price=None, under_price=None, total_fill=r["total"]) for r in priced])
        g_live, R = live_features(T, L, live, priced, P, GRall)   # history rows give the style / common-opponent residuals
        for r, (_, f) in zip(priced, g_live.iterrows()):
            out["games"].append(game_card(r, f, model, P, R, LG, now))
    for r in rows:
        if r.get("ml_q") is None:
            out["games"].append(dict(home=r["home"], away=r["away"], start_ct=r["start"].astimezone(CT).strftime("%a %-I:%M %p CT"),
                                     no_line=True, note="no saved line for this game yet (never invented)"))
    os.makedirs(os.path.dirname(SITE), exist_ok=True)
    json.dump(out, open(SITE, "w"), default=_js)
    return out, notes


def _js(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (dt.datetime, pd.Timestamp)):
        return o.isoformat()
    return str(o)


def live_features(T, L, live, priced, P, GRall):
    """Features for the live slate: the same build() on history + live rows, with the live market anchor
    set from the consensus de-vigged ML / total."""
    live = live.copy()
    # put the consensus probabilities in as synthetic two-way prices with zero vig so market_anchor de-vigs to q exactly
    def am(q):
        return -100 * q / (1 - q) if q >= 0.5 else 100 * (1 - q) / q
    live["ml_home"] = [am(r["ml_q"]) for r in priced]; live["ml_away"] = [am(1 - r["ml_q"]) for r in priced]
    live["over_price"] = [am(r["q_over"]) for r in priced]; live["under_price"] = [am(1 - r["q_over"]) for r in priced]
    allg = pd.concat([L, live], ignore_index=True)
    g, R = nm.build(T, allg, P, GRall)
    key = set(zip(live.date, live.home))
    g = g[np.array([(d, h) in key for d, h in zip(g.date, g.home)]) & g.home_score.isna().to_numpy()]
    return g.set_index(["date", "home"]).loc[list(zip(live.date, live.home))].reset_index(), R


def lean(model, f, part, feats):
    m = model[part]
    x = np.array([0.0 if pd.isna(f.get(k)) else float(f[k]) for k in m["features"]])
    return float(((x - np.array(m["mean"])) / np.array(m["sd"])) @ np.array(m["beta"]))


def game_card(r, f, model, P, R, LG, now):
    ld, lt = lean(model, f, "diff", None), lean(model, f, "total", None)
    lh0, la0 = float(f.lam_h), float(f.lam_a)
    lh, la = max(lh0 + lt / 2 + ld / 2, 0.3), max(la0 + lt / 2 - ld / 2, 0.3)
    F0, Fm = nhl_sim.final_joint([lh0], [la0], P), nhl_sim.final_joint([lh], [la], P)
    tl = r["total"]
    p0, pm = nhl_sim.probs(F0, total=[tl]), nhl_sim.probs(Fm, total=[tl])
    hg, ag = nhl_sim.simulate(lh, la, P, n=1000, seed=int(r["gameId"]) % 100000)
    mc = dict(home_win=float((hg > ag).mean()), home_m15=float((hg - ag >= 2).mean()), away_p15=float((ag - hg >= -1).mean()),
              over=float((hg + ag > tl).sum() / max(((hg + ag) != tl).sum(), 1)),
              home_goals=[int(np.percentile(hg, q)) for q in (10, 50, 90)], away_goals=[int(np.percentile(ag, q)) for q in (10, 50, 90)],
              total=[int(np.percentile(hg + ag, q)) for q in (10, 50, 90)], ot_share=None)
    top = _top_scores(hg, ag)
    Rd = R[(R.date == r["date"]) & R.team.isin(ACTIVE)].reset_index(drop=True)   # rank among the 32 current clubs
    gh = LG[(LG.team == r["home"]) & (LG.date == r["date"])].iloc[0]; ga = LG[(LG.team == r["away"]) & (LG.date == r["date"])].iloc[0]
    c = r["consensus"]
    dk = c["target"].get("draftkings", {})
    units = {}
    for t in (r["home"], r["away"]):
        k = Rd.index[Rd.team == t][0]
        units[t] = {m: dict(o_rank=int(rank(Rd["O_" + m]).iloc[k]), d_rank=int(rank(Rd["D_" + m], False).iloc[k])) for m in nm.METRICS}
        units[t]["n_games"] = int(Rd.n_cur.iloc[k])
    pl_mkt = None
    return dict(home=r["home"], away=r["away"], start_ct=r["start"].astimezone(CT).strftime("%a %b %-d %-I:%M %p CT"), gameId=r["gameId"],
                market=dict(home_win=r["ml_q"], total=tl, over=r["q_over"], src_ml=c["h2h"]["src"], src_total=c["total"]["src"], n_books=c["n_books"],
                            dk=dict(h2h=dk.get("h2h"), totals=dk.get("totals"))),
                sim_market_only=dict(home_win=float(p0["p_home"][0]), home_m15=float(p0["p_home_pl"][0]), over=float(p0["p_over"][0]),
                                     exp_h=float(p0["exp_h"][0]), exp_a=float(p0["exp_a"][0])),
                sim=dict(home_win=float(pm["p_home"][0]), home_m15=float(pm["p_home_pl"][0]), over=float(pm["p_over"][0]),
                         exp_h=float(pm["exp_h"][0]), exp_a=float(pm["exp_a"][0]), mc1000=mc, top_scores=top),
                delta=dict(home_win=float(pm["p_home"][0] - r["ml_q"]), over=float(pm["p_over"][0] - r["q_over"]),
                           home_m15=float(pm["p_home_pl"][0] - p0["p_home_pl"][0])),
                lean=dict(goal_diff=ld, total=lt),
                goalies=dict(home=dict(name=gh.goalie, gsax_per_game=float(gh.g_rating), note=gh.gnote), away=dict(name=ga.goalie, gsax_per_game=float(ga.g_rating), note=ga.gnote)),
                rest=dict(home=_n(f.get("rest_h")), away=_n(f.get("rest_a")), b2b_home=_n(f.get("b2b_h")), b2b_away=_n(f.get("b2b_a"))),
                similar_style=dict(home=_n(f.get("sim_h")), away=_n(f.get("sim_a"))), common_opp=dict(gap=_n(f.get("co_gap")), n=_n(f.get("co_n"))),
                units=units, mismatches=mismatches(r["home"], r["away"], Rd, float(gh.g_rating), float(ga.g_rating)))


def _n(x):
    try:
        return None if pd.isna(x) else round(float(x), 3)
    except Exception:
        return None


def _top_scores(hg, ag, k=3):
    s = pd.Series(list(zip(hg.tolist(), ag.tolist()))).value_counts().head(k)
    return [dict(score=f"{a}-{b}", share=float(v / len(hg))) for (a, b), v in s.items()]


def bt_summary(bt):
    keep = ("n", "ll_model", "ll_market", "ll_improve_ci90", "bets", "wins", "units", "roi", "roi_ci90", "seasons_positive", "by_season")
    return dict({k: {kk: bt[k].get(kk) for kk in keep} for k in ("ml", "puck_line", "total")}, verdict=bt["verdict"],
                calib_puck_line=bt["calib_market_only_sim"]["puck_line"]["ll_market"], calib_puck_line_sim=bt["calib_market_only_sim"]["puck_line"]["ll_model"])


if __name__ == "__main__":
    import sys
    o, n = main(pull="--no-pull" not in sys.argv)
    print("\n".join(n)); print(len(o["games"]), "games")
