#!/usr/bin/env python3
"""Daily MODEL-% log for NHL + MLB (paper/info only) so the models can be graded against results later.

  python scripts/model_log.py grade      # settle logged games from ESPN finals (free)
  (logging is called from auto_board.py right after the board is built)

  python scripts/model_log.py check [paper.json] [model_log.json]   # exit 1 if log != board for today's games
  python scripts/model_log.py backfill [paper.json] [model_log.json] # upsert log from a published paper.json

data/model_log.json: one entry per game x market, upserted from the SAME numbers each board build publishes
in paper.json (board[].market_edge). The last pre-game snapshot wins; earlier values are kept in
entry["snapshots"] with their snapshot_at_ct. Graded entries are never touched. Then:
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


SIDE_ORDER = {"ml": ("away", "home"), "spread": ("away", "home"), "total": ("over", "under")}


def _board_sides(g: dict, mk: str):
    me = (g.get("market_edge") or {}).get(mk) or {}
    by = {sd.get("side"): sd for sd in me.get("sides") or []}
    order = SIDE_ORDER.get(mk)
    if not order or any(k not in by for k in order):
        return None
    return [{"side": k, "label": by[k].get("label"), "line": by[k].get("line"),
             "price_american": by[k].get("price_american"), "book": by[k].get("book"),
             "novig_pct": by[k].get("novig_pct"), "model_pct": by[k].get("model_pct")} for k in order]


def sync_from_board(board: list, rows_by_sport: dict | None, now_ct: datetime, path: Path = PATH,
                    snapshot_ct: str | None = None) -> dict:
    """Upsert log entries from the published paper.json board (game x market). Only pre-game, non-graded
    entries are (re)written; a changed snapshot pushes the old values into entry['snapshots']."""
    d = load(path)
    idx = {e["id"]: e for e in d["entries"]}
    meta = {str(r.get("espn_event_id")): r for rs in (rows_by_sport or {}).values() for r in rs or []}
    snap = snapshot_ct or now_ct.isoformat(timespec="seconds")
    cnt = {"new": 0, "updated": 0, "same": 0, "skipped": 0}
    for g in board or []:
        sport = g.get("sport")
        if sport not in SPORTS or not g.get("kick_utc") or not g.get("espn_event_id"):
            continue
        if PM.kick_ct(g["kick_utc"]) <= now_ct:
            cnt["skipped"] += 1
            continue
        r = meta.get(str(g["espn_event_id"])) or {}
        for mk in ("ml", "spread", "total"):
            sides = _board_sides(g, mk)
            if not sides:
                continue
            eid = f"{sport.lower()}-{g['espn_event_id']}-{mk}"
            e = idx.get(eid)
            if e is not None and e.get("status") != "open":
                cnt["skipped"] += 1
                continue
            if e is not None and e.get("sides") == sides:
                cnt["same"] += 1
                continue
            away, home = (g.get("matchup") or " at ").split(" at ", 1) if " at " in (g.get("matchup") or "") else (None, None)
            new = {"id": eid, "sport": sport, "market": mk, "logged_at_ct": (e or {}).get("logged_at_ct") or snap,
                   "snapshot_at_ct": snap, "source": "paper.json board",
                   "slate_date_ct": PM.kick_ct(g["kick_utc"]).date().isoformat(), "kick_utc": g["kick_utc"],
                   "matchup": g.get("matchup"), "away": r.get("away") or (e or {}).get("away") or away,
                   "home": r.get("home") or (e or {}).get("home") or home,
                   "espn_event_id": str(g["espn_event_id"]),
                   "espn_home_id": r.get("espn_home_id") or (e or {}).get("espn_home_id"),
                   "model": ((r.get("paper") or {}).get("model")) or (e or {}).get("model"),
                   "sides": sides, "status": "open", "snapshots": list((e or {}).get("snapshots") or [])}
            if e is not None:
                new["snapshots"].append({"snapshot_at_ct": e.get("snapshot_at_ct") or e.get("logged_at_ct"), "sides": e["sides"]})
                e.clear(); e.update(new); cnt["updated"] += 1
            else:
                d["entries"].append(new); idx[eid] = new; cnt["new"] += 1
    save(d, path)
    return cnt


def check_board(paper: dict, log: dict, slate_date: str | None = None) -> list:
    """Mismatches between paper.json board and the log for the board's slate (pre-game/open entries)."""
    slate = slate_date or paper.get("slate_date_ct")
    idx = {e["id"]: e for e in log.get("entries", [])}
    bad = []
    for g in paper.get("board") or []:
        if g.get("sport") not in SPORTS or not g.get("espn_event_id") or not g.get("kick_utc"):
            continue
        if PM.kick_ct(g["kick_utc"]).date().isoformat() != slate:
            continue
        for mk in ("ml", "spread", "total"):
            sides = _board_sides(g, mk)
            if not sides:
                continue
            eid = f"{g['sport'].lower()}-{g['espn_event_id']}-{mk}"
            e = idx.get(eid)
            if e is None:
                bad.append(f"{eid}: missing from model_log")
                continue
            for a, b in zip(sides, e.get("sides") or []):
                for k in ("side", "line", "novig_pct", "model_pct", "price_american"):
                    if a.get(k) != b.get(k):
                        bad.append(f"{eid} {a['side']} {k}: board {a.get(k)} vs log {b.get(k)}")
    return bad


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
    a = sys.argv[1:]
    if a and a[0] in ("check", "backfill"):
        pp = Path(a[1]) if len(a) > 1 else PATH.parent / "paper.json"
        lp = Path(a[2]) if len(a) > 2 else PATH
        paper = json.loads(pp.read_text(encoding="utf-8"))
        if a[0] == "backfill":
            gen = datetime.fromisoformat(paper["generated_at_ct"])
            print(f"[model_log] backfill {sync_from_board(paper['board'], None, gen, lp, paper['generated_at_ct'])}")
        bad = check_board(paper, load(lp))
        print("[model_log] check:", "OK" if not bad else f"{len(bad)} mismatch(es)")
        for b in bad:
            print("  ", b)
        sys.exit(1 if bad else 0)
    if a == ["grade"]:
        now = datetime.now(PM.CT) if hasattr(PM, "CT") else datetime.now().astimezone()
        print(f"[model_log] graded {grade(now)}")
    else:
        print(__doc__)
