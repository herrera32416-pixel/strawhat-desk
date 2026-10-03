"""LINES role helpers: parse Odds API events into per-book two-sided markets and no-vig probs."""
import statistics

SHARP = ["pinnacle"]
SEMI = ["betonlineag", "lowvig", "matchbook", "circasports"]
TARGET = ["draftkings", "bovada"]


def imp(a):
    return 100 / (a + 100) if a > 0 else -a / (-a + 100)


def novig(a, b):
    pa, pb = imp(a), imp(b)
    return pa / (pa + pb)


def parse_event(e):
    """-> {book: {'spreads': (home_pt, home_px, away_pt, away_px), 'totals': (pt, over_px, under_px), 'h2h': (home_px, away_px)}}"""
    out = {}
    H, A = e["home_team"], e["away_team"]
    for b in e.get("bookmakers", []):
        d = {}
        for m in b.get("markets", []):
            oc = {o["name"]: o for o in m.get("outcomes", [])}
            try:
                if m["key"] == "spreads" and H in oc and A in oc:
                    d["spreads"] = (float(oc[H]["point"]), int(oc[H]["price"]), float(oc[A]["point"]), int(oc[A]["price"]))
                elif m["key"] == "totals" and "Over" in oc and "Under" in oc and oc["Over"].get("point") == oc["Under"].get("point"):
                    d["totals"] = (float(oc["Over"]["point"]), int(oc["Over"]["price"]), int(oc["Under"]["price"]))
                elif m["key"] == "h2h" and H in oc and A in oc:
                    d["h2h"] = (int(oc[H]["price"]), int(oc[A]["price"]))
            except (KeyError, TypeError, ValueError):
                continue
        if d:
            out[b["key"]] = d
    return out


def sharp_ref(books, market):
    """Sharp anchor: Pinnacle if present, else median no-vig across SEMI books with the modal line.
    Returns (source, line, q) where q = no-vig P(home covers / over) at `line`."""
    if "pinnacle" in books and market in books["pinnacle"]:
        x = books["pinnacle"][market]
        if market == "spreads":
            return "pinnacle", x[0], novig(x[1], x[3])
        if market == "totals":
            return "pinnacle", x[0], novig(x[1], x[2])
        return "pinnacle", None, novig(x[0], x[1])
    rows = []
    for k in SEMI:
        if k in books and market in books[k]:
            x = books[k][market]
            if market == "spreads":
                rows.append((x[0], novig(x[1], x[3])))
            elif market == "totals":
                rows.append((x[0], novig(x[1], x[2])))
            else:
                rows.append((None, novig(x[0], x[1])))
    if not rows:
        return None
    if market == "h2h":
        return "semi-consensus", None, statistics.median(r[1] for r in rows)
    mode = statistics.mode(r[0] for r in rows)
    return "semi-consensus", mode, statistics.median(r[1] for r in rows if r[0] == mode)
