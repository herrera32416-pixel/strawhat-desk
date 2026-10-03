"""BOARD / SHOPPER role: every NFL game in the coming week and every FBS game in the next 36h.
For ML, spread, total: DK + Bovada prices, market no-vig (book's own two-way), model % (KEYS fair at that
line, anchored to the consensus of the other books incl. Pinnacle), EV at the best of DK/Bovada, pick/pass."""
import datetime as dt, statistics
from zoneinfo import ZoneInfo
import numpy as np
from .keys import Dist, ev
from .market import parse_event, novig, imp, TARGET
from .names import norm

CT = ZoneInfo("America/Chicago")
EV_PICK = 0.02     # pre-set: 2% EV vs fair at a real DK/Bovada price
ML_PRICE_RANGE = (-300, 300)  # longshot/heavy-fav MLs: few reference books, fair is noise -> never PICK outside this
MAX_PRICE_GAP = 0.06  # sanity: if our fair differs from the book's own no-vig by >6pp, treat as stale/odd -> pass
BOOKN = {"draftkings": "DK", "bovada": "Bovada"}
_D = {}


def dist(kind, season):
    k = (kind, season)
    if k not in _D:
        _D[k] = Dist(kind, max_season=season - 1)
    return _D[k]


def fmt_am(a):
    return None if a is None else (f"+{a}" if a > 0 else str(a))


def consensus_center(books, mkt, D):
    cs, pin = [], None
    for bk, bd in books.items():
        if bk in TARGET or mkt not in bd:
            continue
        x = bd[mkt]
        if mkt == "spreads":
            c = D.anchor(-x[0], novig(x[1], x[3]))
        else:
            c = D.anchor(x[0], novig(x[1], x[2]))
        cs.append(c)
        if bk == "pinnacle":
            pin = c
    if len(cs) >= 3:
        return float(np.median(cs)), len(cs), pin
    if pin is not None:
        return pin, len(cs), pin
    return None, len(cs), pin


def game_row(e, sport, season):
    books = parse_event(e)
    H, A = e["home_team"], e["away_team"]
    kick = dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")).astimezone(CT)
    row = dict(sport=sport, toa_id=e["id"], home=H, away=A, kick_ct=kick.strftime("%a %b %-d %-I:%M %p CT"),
               kick_iso=kick.isoformat(), markets={}, n_books=len(books))
    Dm, Dt = dist(f"{sport}_margin", season), dist(f"{sport}_total", season)
    # ---- spread ----
    cm, nm, pinm = consensus_center(books, "spreads", Dm)
    sides = []
    if cm is not None:
        for bk in TARGET:
            if bk in books and "spreads" in books[bk]:
                hp, hpx, ap, apx = books[bk]["spreads"]
                q = novig(hpx, apx)
                for side, team, pt, px, opx in (("home", H, hp, hpx, apx), ("away", A, ap, apx, hpx)):
                    t = -pt if side == "home" else pt
                    w, pu, l = Dm.probs(cm, t)
                    if side == "away":
                        w, l = l, w
                    mq = q if side == "home" else 1 - q
                    sides.append(dict(book=BOOKN[bk], side=side, team=team, line=pt, price=px, market_pct=round(mq, 4),
                                      model_pct=round(w / (w + l), 4), push_pct=round(pu, 4), ev=round(ev(w, pu, l, px), 4)))
    row["markets"]["spread"] = pick(sides, "spread", cm, nm, pinm)
    # ---- total ----
    ct_, nt, pint = consensus_center(books, "totals", Dt)
    sides = []
    if ct_ is not None:
        for bk in TARGET:
            if bk in books and "totals" in books[bk]:
                pt, opx, upx = books[bk]["totals"]
                q = novig(opx, upx)
                for side, px in (("over", opx), ("under", upx)):
                    w, pu, l = Dt.probs(ct_, pt)
                    if side == "under":
                        w, l = l, w
                    mq = q if side == "over" else 1 - q
                    sides.append(dict(book=BOOKN[bk], side=side, team=side.title(), line=pt, price=px, market_pct=round(mq, 4),
                                      model_pct=round(w / (w + l), 4), push_pct=round(pu, 4), ev=round(ev(w, pu, l, px), 4)))
    row["markets"]["total"] = pick(sides, "total", ct_, nt, pint)
    # ---- moneyline: fair = median no-vig of other books (Pinnacle included) ----
    qs = [novig(bd["h2h"][0], bd["h2h"][1]) for bk, bd in books.items() if bk not in TARGET and "h2h" in bd]
    pinq = novig(*books["pinnacle"]["h2h"]) if "pinnacle" in books and "h2h" in books["pinnacle"] else None
    fair = statistics.median(qs) if len(qs) >= 3 else pinq
    if fair is None and cm is not None:  # fall back to KEYS conversion of the spread fair
        w, pu, l = Dm.probs(cm, 0); fair = w + pu / 2
    sides = []
    if fair is not None:
        for bk in TARGET:
            if bk in books and "h2h" in books[bk]:
                hpx, apx = books[bk]["h2h"]
                q = novig(hpx, apx)
                for side, team, px, mq, p in (("home", H, hpx, q, fair), ("away", A, apx, 1 - q, 1 - fair)):
                    sides.append(dict(book=BOOKN[bk], side=side, team=team, line=None, price=px, market_pct=round(mq, 4),
                                      model_pct=round(p, 4), push_pct=0.0, ev=round(ev(p, 0, 1 - p, px), 4)))
    row["markets"]["ml"] = pick(sides, "ml", None, len(qs), None)
    if cm is not None:
        row["fair_home_margin"] = round(cm, 2)
    if ct_ is not None:
        row["fair_total"] = round(ct_, 2)
    return row


def pick(sides, mkt, center, nref, pin):
    if not sides:
        return dict(status="no DK/Bovada price", sides=[])
    # best price per side across books
    best = {}
    for s in sides:
        if s["side"] not in best or s["ev"] > best[s["side"]]["ev"]:
            best[s["side"]] = s
    top = max(best.values(), key=lambda s: s["ev"])
    gap = abs(top["model_pct"] - top["market_pct"])
    in_range = mkt != "ml" or (ML_PRICE_RANGE[0] <= top["price"] <= ML_PRICE_RANGE[1])
    decision = "PICK" if (top["ev"] >= EV_PICK and gap <= MAX_PRICE_GAP and nref >= 3 and in_range) else "PASS"
    reason = (f"EV {top['ev']*100:+.1f}% at {top['book']} vs fair from {nref} books" if decision == "PICK" else
              (f"best EV {top['ev']*100:+.1f}% < {EV_PICK*100:.0f}%" if top["ev"] < EV_PICK else
               (f"fair-vs-book gap {gap*100:.1f}pp > {MAX_PRICE_GAP*100:.0f}pp (stale/odd line)" if gap > MAX_PRICE_GAP else
                ("ML price outside -300..+300 (longshot guard)" if not in_range else "too few reference books"))))
    return dict(status="ok", decision=decision, reason=reason, best=top, sides=sides, n_ref_books=nref,
                fair_center=None if center is None else round(center, 2), pinnacle_center=None if pin is None else round(pin, 2))


def nfl_cutoff(now):
    """End of the current NFL week: the next Tuesday 06:00 CT strictly after now."""
    n = now.astimezone(CT)
    days = (1 - n.weekday()) % 7
    t = (n + dt.timedelta(days=days)).replace(hour=6, minute=0, second=0, microsecond=0)
    if t <= n:
        t += dt.timedelta(days=7)
    return t


def build(odds_by_sport, fbs_filter, season, now):
    rows = []
    for sport, data in odds_by_sport.items():
        if not data:
            continue
        for e in data:
            k = dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
            hrs = (k - now).total_seconds() / 3600
            if hrs <= 0:
                continue
            if sport == "nfl" and k > nfl_cutoff(now):
                continue
            if sport == "cfb":
                if hrs > 40:
                    continue
                if fbs_filter is not None and not ({norm(e["home_team"]), norm(e["away_team"])} & fbs_filter):
                    continue
            rows.append(game_row(e, sport, season))
    rows.sort(key=lambda r: (r["sport"] != "nfl", r["kick_iso"]))
    return rows
