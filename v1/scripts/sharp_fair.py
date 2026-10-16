#!/usr/bin/env python3
"""Board fair % source (Luis approved 2026-10-15 9:51pm CT): per game + market, the fair % is the no-vig pair of the
sharpest book present AT THE BOARD'S LINE: Pinnacle -> LowVig -> DraftKings. If none of the three quotes that market
(at that line for spread/total), the previous fair % (DK pair / consensus median) is kept and labelled as such.
Sets side['novig_pct'] (the fair % feeding shown_pct) + side['fair_book']; old value kept in side['novig_prev_pct'].
The star rule (model_calib.lean) is unchanged; callers run model_calib.calibrate_markets afterwards.

Offline republish (0 Odds API credits):  python sharp_fair.py --today ../data/today.json --events FILE [FILE ...]
  FILE = saved Odds API event lists (list or {"events": [...]}); rows are matched by home/away team + kick date.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime
from pathlib import Path

ORDER = (("pinnacle", "Pinnacle"), ("lowvig", "LowVig"), ("draftkings", "DraftKings"))


def _imp(a):
    a = float(a)
    return -a / (100 - a) if a < 0 else 100 / (a + 100)


def _nv(a, b):
    pa, pb = _imp(a), _imp(b)
    return pa / (pa + pb)


def book_pairs(ev: dict) -> dict:
    """{book_key: {'ml': (h, a), 'spread': (L, h, a), 'total': (T, o, u)}} from a raw Odds API event."""
    home, away = ev.get("home_team"), ev.get("away_team")
    out = {}
    for bk in ev.get("bookmakers") or []:
        key = (bk.get("key") or "").lower()
        q = out.setdefault(key, {})
        for m in bk.get("markets") or []:
            o = {x.get("name"): x for x in m.get("outcomes") or []}
            try:
                if m.get("key") == "h2h" and home in o and away in o:
                    q["ml"] = (o[home]["price"], o[away]["price"])
                elif m.get("key") == "spreads" and home in o and away in o:
                    q["spread"] = (float(o[home]["point"]), o[home]["price"], o[away]["price"])
                elif m.get("key") == "totals" and "Over" in o and "Under" in o and o["Over"].get("point") == o["Under"].get("point"):
                    q["total"] = (float(o["Over"]["point"]), o["Over"]["price"], o["Under"]["price"])
            except (KeyError, TypeError, ValueError):
                continue
    return out


def pick(pairs: dict, mk: str, line=None):
    """(book_title, p_first_side) first side = home for ml/spread, over for total. None if no sharp book matches."""
    for key, title in ORDER:
        q = (pairs.get(key) or {}).get(mk)
        if not q:
            continue
        if mk == "ml":
            return title, _nv(q[0], q[1])
        if line is not None and abs(q[0] - float(line)) < 1e-9:
            return title, _nv(q[1], q[2])
    return None


def apply(markets: dict | None, ev: dict | None) -> dict:
    """In place on row['paper']['markets']. Returns {market: source} for logging."""
    pairs = book_pairs(ev) if ev else {}
    used = {}
    for mk, m in (markets or {}).items():
        sides = m.get("sides") or []
        if mk not in ("ml", "spread", "total") or len(sides) != 2:
            continue
        if mk == "ml":
            first, line = next((s for s in sides if s.get("side") == "home"), None), None
        elif mk == "spread":
            first = next((s for s in sides if s.get("side") == "home"), None)
            line = m.get("line_home", None if first is None else first.get("line"))
        else:
            first = next((s for s in sides if s.get("side") == "over"), None)
            line = m.get("line", None if first is None else first.get("line"))
        if first is None:
            continue
        other = sides[1] if sides[0] is first else sides[0]
        got = pick(pairs, mk, line)
        for s in sides:
            s.setdefault("novig_prev_pct", s.get("novig_pct"))
        if got:
            book, p = got
            first["novig_pct"], other["novig_pct"] = round(100 * p, 1), round(100 - round(100 * p, 1), 1)
            src = f"{book} no-vig"
        else:
            prev = str(m.get("novig_source") or "DK pair / consensus")
            src = f"fallback: {prev} (no Pinnacle/LowVig/DK at this line)"
        for s in sides:
            s["fair_book"] = src
        m["fair_source"] = src
        used[mk] = src
    return used


def _norm(t):
    return (t or "").lower().replace(".", "").strip()


def match_event(row: dict, events: list[dict]):
    try:
        kd = row.get("kick_utc", "")[:10]
    except Exception:
        kd = ""
    for e in events:
        if _norm(e.get("home_team")) == _norm(row.get("home")) and _norm(e.get("away_team")) == _norm(row.get("away")):
            if not kd or abs((datetime.fromisoformat(e["commence_time"][:10]) - datetime.fromisoformat(kd)).days) <= 1:
                return e
    return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", required=True)
    ap.add_argument("--events", nargs="+", required=True)
    a = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import model_calib
    evs = []
    for f in a.events:
        raw = json.loads(Path(f).read_text())
        evs += raw if isinstance(raw, list) else (raw.get("events") or raw.get("data") or [])
    doc = json.loads(Path(a.today).read_text())
    card = doc.get("card") or {}
    n = {"matched": 0, "pinnacle": 0, "lowvig": 0, "draftkings": 0, "fallback": 0}
    for k in ("clears", "fills", "holds"):
        for r in card.get(k) or []:
            mk = (r.get("paper") or {}).get("markets")
            if not mk:
                continue
            ev = match_event(r, evs)
            n["matched"] += bool(ev)
            for src in apply(mk, ev).values():
                n["pinnacle" if src.startswith("Pinnacle") else "lowvig" if src.startswith("LowVig")
                  else "draftkings" if src.startswith("DraftKings") else "fallback"] += 1
            for m in mk.values():  # undo the earlier calibration so it is not applied twice
                for sd in m.get("sides") or []:
                    if "model_raw_pct" in sd:
                        sd["model_pct"] = sd.pop("model_raw_pct")
            model_calib.calibrate_markets(r.get("sport"), mk)
    Path(a.today).write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    print("sharp_fair offline:", n)


if __name__ == "__main__":
    main()
