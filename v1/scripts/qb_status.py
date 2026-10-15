#!/usr/bin/env python3
"""Starting-QB status for NFL/CFB board rows (DISPLAY FLAG ONLY; never changes model %, A/B/C or stamps).

NFL: QB1 from the ESPN team depth chart, status from the ESPN league injury report.
CFB: ESPN has no FBS depth charts, so the flag lists QBs on the ESPN CFB injury report (Out/Doubtful/Questionable).
Backtest 2026-10-15 (research/accuracy-2026-10/qb_backtest.txt): an NFL QB-change term on top of the close
did not beat the market (n=5,139, Brier worse, better in 10/20 seasons), so it stays a flag.
Each pre-kick build appends status changes to data/qb_log.jsonl.
"""
from __future__ import annotations
import json, re, sys, urllib.request
from pathlib import Path

PATH = {"NFL": "football/nfl", "CFB": "football/college-football"}
BAD = ("Out", "Doubtful", "Questionable", "Injured Reserve", "Suspension")


def _get(url: str):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)


def _aid(a: dict):
    for l in a.get("links") or []:
        m = re.search(r"/id/(\d+)", l.get("href", ""))
        if m:
            return m.group(1)
    return str(a.get("id") or "") or None


def injured_qbs(sport: str) -> dict:
    """team_id -> [{name, id, status, comment}] for QBs on the ESPN injury report."""
    d = _get(f"https://site.api.espn.com/apis/site/v2/sports/{PATH[sport]}/injuries")
    out: dict = {}
    for t in d.get("injuries") or []:
        for i in t.get("injuries") or []:
            a = i.get("athlete") or {}
            if ((a.get("position") or {}).get("abbreviation") or "").upper() != "QB":
                continue
            out.setdefault(str(t.get("id")), []).append({"name": a.get("displayName"), "id": _aid(a),
                                                        "status": i.get("status"), "comment": i.get("shortComment"),
                                                        "date": i.get("date")})
    return out


def nfl_qb1(team_id: str):
    d = _get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/depthcharts")
    for dc in d.get("depthchart") or []:
        q = (dc.get("positions") or {}).get("qb")
        if q and q.get("athletes"):
            a = q["athletes"][0]
            return {"name": a.get("displayName"), "id": str(a.get("id"))}
    return None


def team_flag(sport: str, team_id: str, inj: dict, qb1_cache: dict) -> dict:
    qbs = inj.get(str(team_id)) or []
    if sport == "NFL":
        if team_id not in qb1_cache:
            try:
                qb1_cache[team_id] = nfl_qb1(team_id)
            except Exception:  # noqa: BLE001
                qb1_cache[team_id] = None
        qb1 = qb1_cache[team_id]
        hit = [q for q in qbs if qb1 and (q["id"] == qb1["id"] or q["name"] == qb1["name"])]
        st = hit[0]["status"] if hit else ("not on injury report" if qb1 else "unknown")
        return {"qb1": qb1 and qb1["name"], "status": st, "flag": st in BAD,
                "note": hit[0]["comment"] if hit else None, "source": "ESPN depth chart + injury report"}
    bad = [q for q in qbs if q["status"] in BAD]
    return {"qb1": None, "status": "QB(s) on injury report" if bad else "none listed", "flag": bool(bad),
            "injured": [f"{q['name']} ({q['status']})" for q in bad], "source": "ESPN CFB injury report (no FBS depth chart)"}


def attach(sport: str, rows: list, now_ct, log_path: Path | None = None) -> int:
    if sport not in PATH or not rows:
        return 0
    inj = injured_qbs(sport)
    cache: dict = {}
    n = 0
    log = []
    for r in rows:
        f = {}
        for side in ("away", "home"):
            tid = r.get(f"espn_{side}_id")
            if tid:
                f[side] = team_flag(sport, str(tid), inj, cache)
        r["qb_status"] = {"as_of_ct": now_ct.isoformat(timespec="seconds"), **f}
        n += sum(1 for v in f.values() if v.get("flag"))
        log.append({"ts_ct": now_ct.isoformat(timespec="seconds"), "sport": sport, "espn_event_id": r.get("espn_event_id"),
                    "kick_utc": r.get("kick_utc"), "matchup": r.get("matchup"),
                    **{s: {k: v.get(k) for k in ("qb1", "status", "flag", "injured")} for s, v in f.items()}})
    if log_path is not None:
        prev = {}
        if log_path.exists():
            for line in log_path.read_text(encoding="utf-8").splitlines():
                try:
                    e = json.loads(line); prev[(e["sport"], str(e["espn_event_id"]))] = (e.get("away"), e.get("home"))
                except Exception:  # noqa: BLE001
                    pass
        with log_path.open("a", encoding="utf-8") as fh:
            for e in log:
                if prev.get((e["sport"], str(e["espn_event_id"]))) != (e.get("away"), e.get("home")):
                    fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    return n
