"""Board rule change backtest (2026-10-03): old rules (EV>=2%, ML picks allowed, no spread cap) vs new rules
(EV>=3%, ML reference-only, no spread/total pick when |spread|>=30), plus each change alone.
Uses the live board code (desk.board.game_row) on the 31 saved 9am-CT historical snapshots (NFL 2025-26, CFB 2025-26),
games kicking within 20h of the snapshot, graded on nflverse / CFB results. Walk-forward KEYS pmf (prior seasons)."""
import sys, os, glob, gzip, json, datetime as dt, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zoneinfo import ZoneInfo
from desk import board
from desk.names import NFL, norm
from sharp_ev import nfl_results, cfb_results
CT = ZoneInfo("America/Chicago")


def grade(mk, side, line, res):
    y = res["margin"] if mk in ("spread", "ml") else res["total"]
    if mk == "ml":
        v = y if side == "home" else -y
    elif mk == "spread":
        v = (y if side == "home" else -y) + line
    else:
        v = (y - line) if side == "over" else (line - y)
    return "W" if v > 0 else ("P" if v == 0 else "L")


cands = []  # every market's best side with the fields needed to re-apply any rule set
for sport in ("nfl", "cfb"):
    R = nfl_results() if sport == "nfl" else cfb_results()
    for f in sorted(glob.glob(f"data/raw/hist/{sport}_*.json.gz")):
        snap = json.load(gzip.open(f)); ts = dt.datetime.fromisoformat(snap["timestamp"].replace("Z", "+00:00"))
        for e in snap["data"]:
            ct = dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
            if not (ts < ct <= ts + dt.timedelta(hours=20)):
                continue
            day = ct.astimezone(CT).date().isoformat()
            k = (day, NFL.get(e["home_team"]), NFL.get(e["away_team"])) if sport == "nfl" else (day, norm(e["home_team"]), norm(e["away_team"]))
            res = R.get(k)
            if res is None:
                continue
            g = board.game_row(e, sport, res["season"])
            for mk, m in g["markets"].items():
                if m.get("status") != "ok":
                    continue
                b = m["best"]
                r = grade(mk, b["side"], b["line"], res)
                dd = b["price"] / 100 if b["price"] > 0 else 100 / -b["price"]
                cands.append(dict(sport=sport, day=day, game=f"{e['away_team']} @ {e['home_team']}", mk=mk, side=b["team"], line=b["line"],
                                  price=b["price"], ev=b["ev"], gap=abs(b["model_pct"] - b["market_pct"]), nref=m["n_ref_books"],
                                  spread_abs=g.get("spread_abs"), res=r, u=0.0 if r == "P" else (dd if r == "W" else -1.0)))


def picked(c, ev_min, ml, cap):
    if c["ev"] < ev_min or c["gap"] > board.MAX_PRICE_GAP or c["nref"] < 3:
        return False
    if c["mk"] == "ml":
        return ml and board.ML_PRICE_RANGE[0] <= c["price"] <= board.ML_PRICE_RANGE[1]
    return not (cap and c["spread_abs"] is not None and c["spread_abs"] >= board.MAX_ABS_SPREAD)


def summ(B):
    if not B:
        return dict(n=0, record="0-0-0", units=0.0)
    u = [c["u"] for c in B]; rng = random.Random(7)
    bs = sorted(sum(rng.choice(u) for _ in u) for _ in range(2000))
    return dict(n=len(B), record=f"{sum(c['res']=='W' for c in B)}-{sum(c['res']=='L' for c in B)}-{sum(c['res']=='P' for c in B)}",
                units=round(sum(u), 2), roi=round(sum(u) / len(u), 3), ci90=[round(bs[100], 1), round(bs[1900], 1)])


RULES = {"old (EV>=2%, ML on, no cap)": (0.02, True, False), "EV>=3% only": (0.03, True, False), "ML reference-only only": (0.02, False, False),
         "|spread|>=30 cap only": (0.02, True, True), "new (all three)": (0.03, False, True)}
out = {}
for name, (e, ml, cap) in RULES.items():
    B = [c for c in cands if picked(c, e, ml, cap)]
    out[name] = dict(all=summ(B), **{f"{sp}_{mk}": summ([c for c in B if c["sport"] == sp and c["mk"] == mk]) for sp in ("nfl", "cfb") for mk in ("spread", "total", "ml")})
    print(name, out[name]["all"], {k: v["record"] + f" {v['units']:+}u" for k, v in out[name].items() if k != "all" and v["n"]})
dropped = [c for c in cands if picked(c, 0.02, True, False) and not picked(c, 0.03, False, True)]
out["_dropped_by_new_rules"] = summ(dropped)
out["_note"] = f"{len(cands)} market-sides from {len(glob.glob('data/raw/hist/*.json.gz'))} saved 9am snapshots; small sample, CIs wide."
print("dropped by new rules:", out["_dropped_by_new_rules"])
os.makedirs("backtest/out", exist_ok=True)
json.dump(out, open("backtest/out/board_rules_bt.json", "w"), indent=1)
json.dump(out, open("data/board_rules_bt.json", "w"), indent=1)
