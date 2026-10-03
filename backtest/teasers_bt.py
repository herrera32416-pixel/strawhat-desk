"""Teaser backtest on closing lines (nflverse 2012-2026; CFB ESPN close 2023-2026), walk-forward KEYS model.
Leg prob = P(cover teased line) from the outcome pmf centred at the close no-vig center."""
import sys, os, csv, math, random, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from desk.keys import Dist
from desk.market import novig
from desk.teaser_math import settle, breakeven_leg, ticket_prob
T = 6.0


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def nfl_games():
    G = []
    for r in csv.DictReader(open("data/history/nfl_games.csv")):
        if r["result"] in ("", "NA") or int(r["season"]) < 2006 or r["game_type"] != "REG":
            continue
        G.append(dict(season=int(r["season"]), wk=f"{r['season']}-{int(r['week']):02d}", game=r["game_id"], dow=r["weekday"],
             sp=f(r["spread_line"]), hsp=f(r["home_spread_odds"]), asp=f(r["away_spread_odds"]),
             tot=f(r["total_line"]), o=f(r["over_odds"]), u=f(r["under_odds"]),
             margin=f(r["result"]), total=f(r["total"])))
    return G


def _cfb_dow(iso):
    import datetime as dt
    from zoneinfo import ZoneInfo
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ZoneInfo("America/Chicago")).strftime("%A")


def cfb_games():
    G = []
    for y in range(2023, 2027):
        for r in csv.DictReader(open(f"data/history/cfb_{y}.csv")):
            if r.get("completed") not in ("1", "True", "1.0") or f(r["close_spread"]) is None:
                continue
            G.append(dict(season=int(r["season"]), wk=f"{r['season']}-{int(r['week']):02d}", game=r["espn_id"], dow=_cfb_dow(r["date"]),
                 sp=-f(r["close_spread"]), hsp=f(r["close_h_sp_price"]), asp=f(r["close_a_sp_price"]),
                 tot=f(r["close_total"]), o=None, u=None,
                 margin=f(r["home_score"]) - f(r["away_score"]), total=f(r["home_score"]) + f(r["away_score"])))
    return G


def legs_for(G, sport):
    D = {}; L = []
    for g in G:
        s = g["season"]
        for kind in ("margin", "total"):
            key = (kind, s)
            if key not in D:
                D[key] = Dist(f"{sport}_{kind}", max_season=s - 1)
            d = D[key]
            if kind == "margin" and g["sp"] is not None:
                q = novig(g["hsp"], g["asp"]) if g["hsp"] and g["asp"] else 0.5
                c = d.anchor(g["sp"], q)  # threshold for home cover at close: margin > sp
                for side, t in (("home", g["sp"] - T), ("away", g["sp"] + T)):
                    w, pu, l = d.probs(c, t)
                    if side == "away":
                        w, l = l, w
                        res = "W" if g["margin"] < t else ("P" if g["margin"] == t else "L")
                    else:
                        res = "W" if g["margin"] > t else ("P" if g["margin"] == t else "L")
                    # side's original line in conventional notation (negative = favorite)
                    orig = -g["sp"] if side == "home" else g["sp"]
                    L.append(dict(sport=sport, season=s, wk=g["wk"], game=g["game"], dow=g.get("dow"), mkt="spread", side=side, orig=orig,
                                  teased=orig + T, p_win=w, p_push=pu, res=res))
            if kind == "total" and g["tot"] is not None:
                q = novig(g["o"], g["u"]) if g["o"] and g["u"] else 0.5
                c = d.anchor(g["tot"], q)
                for side, t in (("over", g["tot"] - T), ("under", g["tot"] + T)):
                    w, pu, l = d.probs(c, t)
                    if side == "under":
                        w, l = l, w
                        res = "W" if g["total"] < t else ("P" if g["total"] == t else "L")
                    else:
                        res = "W" if g["total"] > t else ("P" if g["total"] == t else "L")
                    L.append(dict(sport=sport, season=s, wk=g["wk"], game=g["game"], dow=g.get("dow"), mkt="total", side=side, orig=g["tot"],
                                  teased=t, p_win=w, p_push=pu, res=res))
    return L


def band(l):
    if l["mkt"] == "total":
        return f"total {l['side']} {'<=41' if l['orig'] <= 41 else ('41.5-47' if l['orig'] <= 47 else '>47')}"
    o = l["orig"]
    if -8.5 <= o <= -7.5: return "Wong fav -7.5..-8.5"
    if 1.5 <= o <= 2.5: return "Wong dog +1.5..+2.5"
    if o == 3: return "dog +3"
    if -3 <= o <= -1: return "fav -1..-3"
    if -7 <= o <= -3.5: return "fav -3.5..-7"
    if o < -8.5: return "fav < -8.5"
    if 3.5 <= o <= 7: return "dog +3.5..+7"
    if o > 7: return "dog > +7"
    return "pk/other"


K_SHRINK = 150


def band_adjust(L, sport):
    """Walk-forward: shrink each leg's p toward its band's empirical non-push win rate from PRIOR seasons."""
    seasons = sorted({l["season"] for l in L})
    for s in seasons:
        prior = [l for l in L if l["season"] < s]
        stats = collections.defaultdict(lambda: [0, 0])
        for l in prior:
            if l["res"] != "P":
                b = band(l); stats[b][0] += l["res"] == "W"; stats[b][1] += 1
        for l in L:
            if l["season"] != s:
                continue
            l["p_model_raw"] = l["p_win"]
            w, n = stats[band(l)]
            if n:
                cond = l["p_win"] / (1 - l["p_push"])
                adj = (n * (w / n) + K_SHRINK * cond) / (n + K_SHRINK)
                l["p_win"] = adj * (1 - l["p_push"])


def boot_units(u, reps=2000, seed=3):
    rng = random.Random(seed); s = []
    for _ in range(reps):
        s.append(sum(rng.choice(u) for _ in u))
    s.sort(); return s[int(.05 * reps)], s[int(.95 * reps)]


def build_week(legs, n_tickets, cap, min_p=0.0):
    """Greedy: rank legs by p_win (+ half push credit); each ticket = 6 legs from distinct games; each leg used <= cap times."""
    legs = sorted([l for l in legs if l["p_win"] >= min_p], key=lambda l: -(l["p_win"] + 0.5 * l["p_push"]))
    use = collections.Counter(); T = []
    for _ in range(n_tickets):
        tk, games = [], set()
        # start from least-used high legs to diversify
        for l in sorted(legs, key=lambda l: (use[id(l)] >= 1, -(l["p_win"] + 0.5 * l["p_push"]))):
            if use[id(l)] >= cap or l["game"] in games:
                continue
            tk.append(l); games.add(l["game"])
            if len(tk) == 6:
                break
        if len(tk) < 6:
            break
        for l in tk:
            use[id(l)] += 1
        T.append(tk)
    return T


def main():
    out = []
    allrows = []
    for sport, G in (("nfl", nfl_games()), ("cfb", cfb_games())):
        L = legs_for(G, sport)
        band_adjust(L, sport)
        allrows += L
        test = [l for l in L if l["season"] >= (2015 if sport == "nfl" else 2024)]
        # leg calibration
        nonp = [l for l in test if l["res"] != "P"]
        y = np.array([l["res"] == "W" for l in nonp], float)
        p = np.array([l["p_win"] / (l["p_win"] + (1 - l["p_win"] - l["p_push"])) for l in nonp])
        out.append(dict(sport=sport, what="leg calibration (all teased legs, non-push)", n=len(nonp),
                        mean_p=round(p.mean(), 4), actual=round(y.mean(), 4), brier=round(((p - y) ** 2).mean(), 4)))
        # by band
        B = collections.defaultdict(list)
        for l in test:
            B[band(l) if sport == "nfl" else ("CFB " + band(l))].append(l)
        for b, ls in sorted(B.items()):
            w = sum(l["res"] == "W" for l in ls); lo = sum(l["res"] == "L" for l in ls)
            out.append(dict(sport=sport, what=f"band {b}", n=len(ls), record=f"{w}-{lo}-{len(ls)-w-lo}",
                            win_pct_excl_push=round(w / max(w + lo, 1), 4),
                            mean_model_p=round(np.mean([l['p_win'] / (l['p_win'] + 1 - l['p_win'] - l['p_push']) for l in ls]), 4)))
        # by model-prob bucket
        for lo_, hi_ in ((0, .65), (.65, .70), (.70, .72), (.72, .74), (.74, .76), (.76, 1)):
            ls = [l for l in nonp if lo_ <= l["p_win"] / (l["p_win"] + 1 - l["p_win"] - l["p_push"]) < hi_]
            if ls:
                w = sum(l["res"] == "W" for l in ls)
                out.append(dict(sport=sport, what=f"model p bucket [{lo_},{hi_})", n=len(ls), win_pct_excl_push=round(w / len(ls), 4)))
        # weekly ticket strategies (walk-forward: model trained on prior seasons only)
        weeks = collections.defaultdict(list)
        for l in test:
            weeks[l["wk"]].append(l)
        for strat, kw in (("top6 1 ticket/wk spreads+totals", dict(n=1, cap=1, mk=("spread", "total"))),
                          ("top6 1 ticket/wk spreads only", dict(n=1, cap=1, mk=("spread",))),
                          ("5 tickets/wk cap2 spreads+totals", dict(n=5, cap=2, mk=("spread", "total"))),
                          ("Wong-only legs, 1 ticket/wk if >=6", dict(n=1, cap=1, mk=("spread",), wong=True))):
            U = []; wins = 0; probs = []
            for wk, ls in sorted(weeks.items()):
                ls = [l for l in ls if l["mkt"] in kw["mk"]]
                if kw.get("wong"):
                    ls = [l for l in ls if band(l).startswith("Wong")]
                for tk in build_week(ls, kw["n"], kw["cap"]):
                    u = settle([l["res"] for l in tk]); U.append(u); wins += u > 0
                    probs.append(ticket_prob([(l["p_win"], l["p_push"]) for l in tk]))
            if U:
                lo, hi = boot_units(U)
                out.append(dict(sport=sport, what=f"strategy {strat}", n=len(U), tickets_won=wins,
                                units=round(sum(U), 2), roi=round(sum(U) / len(U), 3), units_ci90=f"[{lo:.1f},{hi:.1f}]",
                                mean_model_ticket_p=round(np.mean([p[0] for p in probs]), 4),
                                mean_model_ev=round(np.mean([p[1] for p in probs]), 4)))
    os.makedirs("backtest/out", exist_ok=True)
    keys = []
    for r in out:
        for k in r:
            if k not in keys: keys.append(k)
    with open("backtest/out/teasers_summary.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(out)
    for r in out:
        print(r)
    print("break-even per leg 6-team +600:", round(breakeven_leg(), 4))


if __name__ == "__main__":
    main()
