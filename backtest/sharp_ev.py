"""Walk-forward backtest of the SHOPPER rule: bet DK/Bovada spreads & totals when EV vs the
Pinnacle-anchored KEYS fair price clears a threshold. Snapshot = 9am CT game day."""
import sys, os, glob, gzip, json, csv, datetime as dt, math, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from zoneinfo import ZoneInfo
from desk.keys import Dist, ev
from desk.market import parse_event, sharp_ref, novig, TARGET
from desk.names import NFL, norm, espn_cfb_id_to_norm
CT = ZoneInfo("America/Chicago")
OUT = "backtest/out"
ANCHOR = os.environ.get("ANCHOR", "pinnacle")


def nfl_results():
    R = {}
    for r in csv.DictReader(open("data/history/nfl_games.csv")):
        if r["result"] in ("", "NA"):
            continue
        R[(r["gameday"], r["home_team"], r["away_team"])] = dict(margin=float(r["result"]), total=float(r["total"]),
            season=int(r["season"]), close_sp=float(r["spread_line"]) if r["spread_line"] not in ("", "NA") else None,
            close_tot=float(r["total_line"]) if r["total_line"] not in ("", "NA") else None,
            c_hsp=r["home_spread_odds"], c_asp=r["away_spread_odds"], c_o=r["over_odds"], c_u=r["under_odds"])
    return R


def cfb_results():
    idn = espn_cfb_id_to_norm(); R = {}
    for y in range(2022, 2027):
        for r in csv.DictReader(open(f"data/history/cfb_{y}.csv")):
            if r["home_score"] in ("", "nan") or r.get("completed") not in ("1", "True", "1.0"):
                continue
            d = dt.datetime.fromisoformat(r["date"].replace("Z", "+00:00")).astimezone(CT).date().isoformat()
            h, a = idn.get(r["home_id"]), idn.get(r["away_id"])
            f = lambda k: float(r[k]) if r.get(k) not in ("", "nan", None) else None
            R[(d, h, a)] = dict(margin=float(r["home_score"]) - float(r["away_score"]),
                total=float(r["home_score"]) + float(r["away_score"]), season=int(r["season"]),
                close_sp=(-f("close_spread") if f("close_spread") is not None else None), close_tot=f("close_total"),
                c_hsp=r.get("close_h_sp_price"), c_asp=r.get("close_a_sp_price"), c_o=None, c_u=None)
    return R


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def run(sport):
    R = nfl_results() if sport == "nfl" else cfb_results()
    dists = {}
    rows = []
    for f in sorted(glob.glob(f"data/raw/hist/{sport}_*.json.gz")):
        snap = json.load(gzip.open(f)); ts = dt.datetime.fromisoformat(snap["timestamp"].replace("Z", "+00:00"))
        for e in snap["data"]:
            ct = dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
            if not (ts < ct <= ts + dt.timedelta(hours=20)):
                continue
            day = ct.astimezone(CT).date().isoformat()
            if sport == "nfl":
                k = (day, NFL.get(e["home_team"]), NFL.get(e["away_team"]))
            else:
                k = (day, norm(e["home_team"]), norm(e["away_team"]))
            res = R.get(k)
            if res is None:
                continue
            season = res["season"]
            books = parse_event(e)
            for mkt, kind in (("spreads", f"{sport}_margin"), ("totals", f"{sport}_total")):
                ref = sharp_ref(books, mkt)
                if not ref:
                    continue
                src, line, q = ref
                dk = (kind, season)
                if dk not in dists:
                    dists[dk] = Dist(kind, max_season=season - 1)
                D = dists[dk]
                t_ref = -line if mkt == "spreads" else line
                c_pin = D.anchor(t_ref, q)
                cs = []
                for bk2, bd in books.items():
                    if bk2 in TARGET or mkt not in bd:
                        continue
                    x2 = bd[mkt]
                    if mkt == "spreads":
                        cs.append(D.anchor(-x2[0], novig(x2[1], x2[3])))
                    else:
                        cs.append(D.anchor(x2[0], novig(x2[1], x2[2])))
                c_cons = float(np.median(cs)) if len(cs) >= 3 else c_pin
                c = {"pinnacle": c_pin, "consensus": c_cons, "mix": (c_pin + c_cons) / 2}[ANCHOR]
                # close center for xROI / CLV
                cc = None
                if mkt == "spreads" and res["close_sp"] is not None:
                    a, b = fnum(res["c_hsp"]), fnum(res["c_asp"])
                    qc = novig(a, b) if a and b else 0.5
                    cc = D.anchor(res["close_sp"], qc)  # nflverse/CFB close as expected home margin; threshold = close line
                elif mkt == "totals" and res["close_tot"] is not None:
                    a, b = fnum(res["c_o"]), fnum(res["c_u"])
                    qc = novig(a, b) if a and b else 0.5
                    cc = D.anchor(res["close_tot"], qc)
                y = res["margin"] if mkt == "spreads" else res["total"]
                for bk in TARGET:
                    if bk not in books or mkt not in books[bk]:
                        continue
                    x = books[bk][mkt]
                    if mkt == "spreads":
                        sides = [("home", -x[0], x[1], x[3]), ("away", x[2], x[3], x[1])]
                    else:
                        sides = [("over", x[0], x[1], x[2]), ("under", x[0], x[2], x[1])]
                    for side, t, px, opx in sides:
                        w, pu, l = D.probs(c, t)
                        if side in ("away", "under"):
                            w, l = l, w
                        # market (book's own) no-vig for this side
                        qb = novig(px, opx)
                        pm = w / (w + l)
                        if side in ("home", "over"):
                            won = y > t; push = y == t
                        else:
                            won = y < t; push = y == t
                        xr = None
                        if cc is not None:
                            w2, pu2, l2 = D.probs(cc, t)
                            if side in ("away", "under"):
                                w2, l2 = l2, w2
                            xr = ev(w2, pu2, l2, px)
                        dd = px / 100 if px > 0 else 100 / -px
                        rows.append(dict(sport=sport, season=season, day=day, game=f"{k[2]}@{k[1]}", market=mkt, book=bk,
                            side=side, line=t if side in ("home", "over") else (t if mkt == "totals" else t), price=px,
                            ref=src, ref_line=line, ref_q=round(q, 4), center=c, p_model=round(pm, 4), p_book=round(qb, 4),
                            ev=round(ev(w, pu, l, px), 4), outcome=("P" if push else ("W" if won else "L")),
                            units=0.0 if push else (dd if won else -1.0), xroi_close=None if xr is None else round(xr, 4)))
    return rows


def boot(vals, clusters, reps=2000, seed=7):
    rng = random.Random(seed); by = {}
    for v, c in zip(vals, clusters):
        by.setdefault(c, []).append(v)
    keys = list(by); sums = []
    for _ in range(reps):
        s = 0.0
        for _ in keys:
            s += sum(by[rng.choice(keys)])
        sums.append(s)
    sums.sort(); return sums[int(.05 * reps)], sums[int(.95 * reps)]


def summarize(rows, label):
    out = []
    import itertools
    for sport in ("nfl", "cfb"):
        for mkt in ("spreads", "totals"):
            R = [r for r in rows if r["sport"] == sport and r["market"] == mkt]
            if not R:
                continue
            # scoring: one row per game-side at DK (two-sided), non-push
            S = [r for r in R if r["book"] == "draftkings" and r["side"] in ("home", "over") and r["outcome"] != "P"]
            yv = [1.0 if r["outcome"] == "W" else 0.0 for r in S]
            bm = np.mean([(r["p_model"] - y) ** 2 for r, y in zip(S, yv)]) if S else None
            bb = np.mean([(r["p_book"] - y) ** 2 for r, y in zip(S, yv)]) if S else None
            lm = np.mean([-math.log(r["p_model"] if y else 1 - r["p_model"]) for r, y in zip(S, yv)]) if S else None
            lb = np.mean([-math.log(r["p_book"] if y else 1 - r["p_book"]) for r, y in zip(S, yv)]) if S else None
            diffs = [((r["p_model"] - y) ** 2 - (r["p_book"] - y) ** 2) for r, y in zip(S, yv)]
            lo, hi = boot(diffs, [r["game"] + r["day"] for r in S]) if S else (None, None)
            n = len(S)
            out.append(dict(set=label, sport=sport, market=mkt, kind="score", n=n, brier_model=bm, brier_dk_novig=bb,
                            ll_model=lm, ll_dk_novig=lb, dbrier_sum_ci90=f"[{lo:.3f},{hi:.3f}]" if S else ""))
            for thr in (0.0, 0.01, 0.02, 0.03):
                # best price per game-side across DK/Bovada, bet if EV >= thr
                best = {}
                for r in R:
                    key = (r["day"], r["game"], r["side"])
                    if r["ev"] >= thr and (key not in best or r["ev"] > best[key]["ev"]):
                        best[key] = r
                B = list(best.values())
                if not B:
                    out.append(dict(set=label, sport=sport, market=mkt, kind=f"bets ev>={thr}", n=0)); continue
                u = [r["units"] for r in B]; cl = [r["day"] + r["game"] for r in B]
                lo, hi = boot(u, cl)
                xr = [r["xroi_close"] for r in B if r["xroi_close"] is not None]
                w = sum(r["outcome"] == "W" for r in B); l = sum(r["outcome"] == "L" for r in B); p = len(B) - w - l
                out.append(dict(set=label, sport=sport, market=mkt, kind=f"bets ev>={thr}", n=len(B), record=f"{w}-{l}-{p}",
                                units=round(sum(u), 2), roi=round(sum(u) / len(B), 4), units_ci90=f"[{lo:.1f},{hi:.1f}]",
                                mean_ev_at_bet=round(float(np.mean([r['ev'] for r in B])), 4),
                                mean_xroi_vs_close=round(float(np.mean(xr)), 4) if xr else None, n_xroi=len(xr)))
    return out


if __name__ == "__main__":
    rows = run("nfl") + run("cfb")
    os.makedirs(OUT, exist_ok=True)
    with open(f"{OUT}/shopper_rows_{ANCHOR}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    summ = summarize(rows, ANCHOR)
    keys = sorted({k for s in summ for k in s}, key=lambda k: list(summ[0].keys()).index(k) if k in summ[0] else 99)
    with open(f"{OUT}/shopper_summary_{ANCHOR}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(summ)
    for s in summ:
        print({k: v for k, v in s.items() if v not in (None, "")})
