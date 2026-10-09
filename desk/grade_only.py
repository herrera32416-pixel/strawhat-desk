"""Credit-free regrade: settle the ledger from ESPN and refresh the site's ledger + headline only.
Touches no odds (0 Odds API credits) and leaves the board/props content as published.
Usage: python -m desk.grade_only"""
import json, os, datetime as dt
from zoneinfo import ZoneInfo
from desk import grader

CT = ZoneInfo("America/Chicago")
DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "data")


def main():
    now = dt.datetime.now(CT)
    L = grader.load()
    for it in L["items"]:
        it.setdefault("kind", grader.kind_of(it))
    n = grader.grade(L, now)
    grader.save(L)
    hl = grader.headline(L)
    for f in ("board", "props", "ledger", "meta"):
        p = os.path.join(DOCS, f + ".json")
        if not os.path.exists(p):
            continue
        d = json.load(open(p))
        m = d if f == "meta" else d.get("meta")
        if m is None:
            continue
        m["headline"] = hl
        m["graded_ct"] = now.strftime("%a %b %-d %-I:%M %p CT")
        if f == "ledger":
            d["ledger"] = L
        json.dump(d, open(p, "w"))
    print(f"GRADE-ONLY: {n} settled; official {hl['official']['record']} {hl['official']['units']:+.2f}u; "
          f"research {hl['research']['record']} {hl['research']['units']:+.2f}u")


if __name__ == "__main__":
    main()
