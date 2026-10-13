#!/usr/bin/env python3
"""Daily MODEL-% log for NHL + MLB (paper/info only) so the models can be graded against results later.

  python scripts/model_log.py grade      # settle logged games from ESPN finals (free)
  (logging is called from auto_board.py right after the board is built)

data/model_log.json: one entry per game x market, first pre-game snapshot of the day only (never re-priced):
  model % and market no-vig % for side 0 (away / over) and side 1 (home / under), the line, then after the
  final: winning side, whether the model side (>50%) won, and Brier scores for model vs market.
Blank model % stays null and is skipped in grading. Never invents numbers.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import paper_model as PM  # noqa: E402

PATH = HERE.parent / "data" / "model_log.json"
SPORTS = ("NHL", "MLB")


def load(path: Path = PATH) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schema": "desk-model-log/v1", "label": "PAPER / INFO ONLY — model % vs results, not bets", "entries": []}


def save(d: dict, path: Path = PATH) -> None:
    d["summary"] = summarize(d)
    path.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def log_rows(rows_by_sport: dict, now_ct: datetime, path: Path = PATH) -> int:
    d = load(path)
    have = {e["id"] for e in d["entries"]}
    n = 0
    for sport in SPORTS:
        for r in rows_by_sport.get(sport) or []:
            if not r.get("kick_utc") or PM.kick_ct(r["kick_utc"]) <= now_ct:
                continue
            blk = r.get("paper") or {}
            for mk, m in (blk.get("markets") or {}).items():
                sides = m.get("sides") or []
                if len(sides) != 2:
                    continue
                eid = f"{sport.lower()}-{r.get('espn_event_id') or r.get('event_id')}-{mk}"
                if eid in have:
                    continue
                e = {"id": eid, "sport": sport, "market": mk, "logged_at_ct": now_ct.isoformat(timespec="seconds"),
                     "slate_date_ct": PM.kick_ct(r["kick_utc"]).date().isoformat(), "kick_utc": r["kick_utc"],
                     "matchup": r.get("matchup"), "away": r.get("away"), "home": r.get("home"),
                     "espn_event_id": r.get("espn_event_id"), "espn_home_id": r.get("espn_home_id"),
                     "model": blk.get("model"),
                     "sides": [{"side": s["side"], "label": s["label"], "line": s.get("line"),
                                "price_american": s.get("price_american"), "book": s.get("book"),
                                "novig_pct": s.get("novig_pct"), "model_pct": s.get("model_pct")} for s in sides],
                     "status": "open"}
                d["entries"].append(e)
                have.add(eid)
                n += 1
    save(d, path)
    return n


def _outcome(e: dict, ev: dict):
    """Returns index of the winning side (0/1), 'push', or None."""
    try:
        hs, as_ = float(ev["home_score"]), float(ev["away_score"])
    except (TypeError, ValueError):
        return None
    if ev["home_id"] == e.get("espn_home_id"):
        h, a = hs, as_
    elif ev["away_id"] == e.get("espn_home_id"):
        h, a = as_, hs
    else:
        return None
    s0 = e["sides"][0]
    if e["market"] == "ml":
        x = a - h                       # side 0 = away
    elif e["market"] == "spread":
        x = (a - h) + float(s0["line"])  # side 0 = away at its line
    else:
        x = (h + a) - float(s0["line"])  # side 0 = over
    return 0 if x > 0 else (1 if x < 0 else "push"), f"{e['away']} {int(a)} - {e['home']} {int(h)}"


def grade(now_ct: datetime, path: Path = PATH) -> int:
    d = load(path)
    open_e = [e for e in d["entries"] if e["status"] == "open" and PM.kick_ct(e["kick_utc"]) < now_ct]
    days: dict[str, set] = {}
    for e in open_e:
        k = PM.kick_ct(e["kick_utc"])
        for j in (-1, 0, 1):
            days.setdefault(e["sport"], set()).add((k + timedelta(days=j)).strftime("%Y%m%d"))
    evs = {s: PM.espn_events(s, sorted(v)) for s, v in days.items()}
    n = 0
    for e in open_e:
        ev = evs.get(e["sport"], {}).get(str(e.get("espn_event_id")))
        if not ev:
            continue
        if "CANCEL" in ev["status"] or "POSTPONE" in ev["status"]:
            if now_ct - PM.kick_ct(e["kick_utc"]) > timedelta(days=3):
                e.update(status="void")
                n += 1
            continue
        if not (ev["completed"] and ev["state"] == "post"):
            continue
        o = _outcome(e, ev)
        if not o:
            continue
        w, score = o
        e.update(status="graded", score=score, graded_at_ct=now_ct.isoformat(timespec="seconds"))
        if w == "push":
            e["result"] = "push"
        else:
            e["winner"] = e["sides"][w]["label"]
            for src in ("model", "novig"):
                p0 = e["sides"][0].get(f"{src}_pct")
                if p0 is None:
                    continue
                y = 1.0 if w == 0 else 0.0
                e[f"{src}_brier"] = round((p0 / 100 - y) ** 2, 4)
                if p0 != 50:
                    e[f"{src}_side_won"] = (p0 > 50) == (w == 0)
        n += 1
    save(d, path)
    return n


def summarize(d: dict) -> dict:
    out = {}
    for sport in SPORTS:
        for mk in ("ml", "spread", "total"):
            g = [e for e in d["entries"] if e["sport"] == sport and e["market"] == mk and e["status"] == "graded"
                 and e.get("model_brier") is not None]
            if not g:
                continue
            mw = sum(1 for e in g if e.get("model_side_won") is True)
            ml = sum(1 for e in g if e.get("model_side_won") is False)
            out[f"{sport} {mk}"] = {"n": len(g), "model_fav_side_W_L": f"{mw}-{ml}",
                                    "brier_model": round(sum(e["model_brier"] for e in g) / len(g), 4),
                                    "brier_market": round(sum(e["novig_brier"] for e in g if e.get("novig_brier") is not None)
                                                          / max(1, sum(1 for e in g if e.get("novig_brier") is not None)), 4)}
    return out


if __name__ == "__main__":
    if sys.argv[1:] == ["grade"]:
        now = datetime.now(PM.CT) if hasattr(PM, "CT") else datetime.now().astimezone()
        print(f"[model_log] graded {grade(now)}")
    else:
        print(__doc__)
