"""WATCH lines: tracked paper leans that are NOT pre-registered and NEVER picks.

cfb_totals_lam30: the CFB matchup total model with light fixed shrinkage (ridge lambda = 30 instead of the
CV choice). It surfaced only as a sensitivity cell in backtest/matchup_cfb_bt.py (OOS 2024-25: |lean| >= 1.5
went 166-131, +19.9u at -110; one of ~12 sensitivity cells, so likely partly luck). We track it forward on
paper to see whether it holds on new games. Fixed rule (2026-10-04): lean = model on the game's matchup
features; WATCH when |lean| >= 1.5 pts; side = over if lean > 0; line = ESPN/DraftKings total; the entry
refreshes until kickoff and freezes at kick; graded on ESPN finals at -110 (push = 0). Free data only."""
import os, json, datetime as dt
import pandas as pd
from desk import matchup as M, espn

ROOT = M.ROOT
WM = os.path.join(ROOT, "data", "matchup", "cfb_watch_model.json")
LEDGER = os.path.join(ROOT, "data", "watch", "cfb_totals_watch.json")
THRESH = 1.5


def fit():
    F = pd.read_csv(os.path.join(ROOT, "data", "matchup", "cfb_features.csv.gz"))
    F["y"] = F.total - F.total_line
    F = F.dropna(subset=M.TOTAL_F + ["y"])
    m = M.fit_ridge(F[M.TOTAL_F].values, F.y.values, 30.0)
    json.dump(dict(features=M.TOTAL_F, model=m, lam=30.0, n=int(len(F)), seasons=sorted(map(int, F.season.unique())),
                   fitted="2026-10-04", note=__doc__), open(WM, "w"), indent=1)
    return m


def load():
    return json.load(open(LEDGER)) if os.path.exists(LEDGER) else {"items": []}


def update(cfb_live, now):
    """Log/refresh watch entries from the CFB matchup live output, then grade finished games."""
    W = json.load(open(WM)); L = load(); ix = {i["espn_id"]: i for i in L["items"]}
    for g in cfb_live.get("games", []):
        if g.get("total_line") is None or not g.get("features"):
            continue
        kick = dt.datetime.fromisoformat(g["kick_iso"])
        if kick <= now:
            continue
        lean = float(M.predict(W["model"], [[g["features"][c] for c in W["features"]]])[0])
        it = ix.get(g["espn_id"])
        if abs(lean) < THRESH:
            if it and it["status"] == "open":     # lean dropped below threshold before kick -> withdrawn
                it.update(status="WITHDRAWN", lean=round(lean, 2), updated_ct=now.isoformat(timespec="minutes"))
            continue
        rec = dict(espn_id=g["espn_id"], game=g["game"], kick_iso=g["kick_iso"], gameday=g["gameday"], line=float(g["total_line"]),
                   side="over" if lean > 0 else "under", lean=round(lean, 2), price=-110, status="open",
                   updated_ct=now.isoformat(timespec="minutes"))
        if it:
            it.update(rec)
        else:
            rec["logged_ct"] = now.isoformat(timespec="minutes"); L["items"].append(rec); ix[rec["espn_id"]] = rec
    # grade
    for it in L["items"]:
        if it["status"] != "open" or dt.datetime.fromisoformat(it["kick_iso"]) > now:
            continue
        try:
            sb = espn.scoreboard("cfb", it["gameday"].replace("-", ""))
            gm = next((x for x in espn.games(sb) if str(x["id"]) == str(it["espn_id"])), None)
        except Exception:
            gm = None
        if not gm or not gm["completed"]:
            continue
        tot = gm["home_score"] + gm["away_score"]
        r = "P" if tot == it["line"] else ("W" if (tot > it["line"]) == (it["side"] == "over") else "L")
        it.update(status=r, final_total=tot, units=0.0 if r == "P" else (100 / 110 if r == "W" else -1.0))
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    json.dump(L, open(LEDGER, "w"), indent=1)
    s = [i for i in L["items"] if i["status"] in ("W", "L", "P")]
    rec = dict(w=sum(i["status"] == "W" for i in s), l=sum(i["status"] == "L" for i in s), p=sum(i["status"] == "P" for i in s),
               units=round(sum(i.get("units", 0) for i in s), 2), open=sum(i["status"] == "open" for i in L["items"]))
    out = dict(name="CFB totals, lightly-shrunk matchup model (WATCH: not pre-registered, no picks)", rule=__doc__.split("Fixed rule")[1].strip(),
               backtest="Sensitivity cell only: OOS 2024-25 |lean|>=1.5: 166-131 (55.9%), +19.9u at -110; not pre-registered; one of ~12 cells.",
               record=rec, items=sorted(L["items"], key=lambda i: i["kick_iso"], reverse=True)[:200],
               generated_ct=now.strftime("%a %b %-d %Y %-I:%M %p CT"))
    json.dump(out, open(os.path.join(ROOT, "docs", "data", "watch.json"), "w"))
    return out


if __name__ == "__main__":
    fit(); print("fitted", WM)
