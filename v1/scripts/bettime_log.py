"""Append-only bet-time log (Luis approved 2026-10-15 9:33pm CT, Colab Backtest #2). PAPER / audit only.

One line per board row x market each time the board (or the NHL refresh) writes, to v1/data/bettime_log.jsonl:
timestamp CT, sim_version (sha256 of the model scripts), model % (raw/unproven), no-vig %, shown %, BOTH prices + books.
Lines are never edited: the file is only opened in append mode, and each line carries prev_hash + line_hash
(sha256 chain), so any edit or deletion of an earlier line breaks `python3 bettime_log.py verify`.
"""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATH = HERE.parent / "data" / "bettime_log.jsonl"
VERSION_FILES = ("paper_model.py", "model_calib.py", "auto_board.py", "nhl_refresh.py")


def sim_version() -> str:
    h = hashlib.sha256()
    for f in VERSION_FILES:
        p = HERE / f
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:12]


def _last_hash(path: Path) -> str:
    if not path.exists() or path.stat().st_size == 0:
        return "genesis"
    with path.open("rb") as f:
        f.seek(max(0, path.stat().st_size - 8192))
        tail = f.read().decode("utf-8", "replace").strip().splitlines()
    try:
        return json.loads(tail[-1])["line_hash"]
    except Exception:  # noqa: BLE001
        return "unknown"


def append(sport: str, rows: list, now_ct, source: str, path: Path = PATH) -> int:
    ver, prev, n = sim_version(), _last_hash(path), 0
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            for mk, m in ((r.get("paper") or {}).get("markets") or {}).items():
                sides = (m.get("sides") or [])[:2]
                if not sides:
                    continue
                rec = {"ts_ct": now_ct.isoformat(timespec="seconds"), "source": source, "sport": sport,
                       "event_id": r.get("event_id"), "matchup": r.get("matchup"), "kick_utc": r.get("kick_utc"),
                       "market": mk, "sim_version": ver,
                       "sides": [{"label": s.get("label"), "price_american": s.get("price_american"), "book": s.get("book"),
                                  "model_pct": s.get("model_unproven_pct", s.get("model_raw_pct", s.get("model_pct"))),
                                  "novig_pct": s.get("novig_pct"), "shown_pct": s.get("shown_pct")} for s in sides],
                       "lean": m.get("lean"), "prev_hash": prev}
                body = json.dumps(rec, sort_keys=True, ensure_ascii=False)
                rec["line_hash"] = prev = hashlib.sha256(body.encode()).hexdigest()[:16]
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
    return n


def verify(path: Path = PATH) -> int:
    prev, bad = None, 0
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        rec = json.loads(line)
        h = rec.pop("line_hash")
        if hashlib.sha256(json.dumps(rec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16] != h or \
                (prev is not None and rec["prev_hash"] != prev):
            print(f"BROKEN at line {i}"); bad += 1
        prev = h
    print("bettime_log OK" if not bad else f"{bad} broken line(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(verify() if sys.argv[1:] == ["verify"] else print(__doc__))
