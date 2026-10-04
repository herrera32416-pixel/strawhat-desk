"""GRADER role: append new picks to the ledger and settle open ones from ESPN finals / box scores."""
import datetime as dt, json, os, hashlib
from zoneinfo import ZoneInfo
from . import espn
from .names import norm
from .props import pname
from .teaser_math import settle, dec

CT = ZoneInfo("America/Chicago")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "data", "ledger", "ledger.json")
STAT_OF = {"Rec Yds": "receiving_yards", "Receptions": "receptions", "Rush Yds": "rushing_yards", "Pass Yds": "passing_yards",
           "Pass TDs": "passing_tds", "Anytime TD": "anytime_td"}


def load():
    return json.load(open(LEDGER)) if os.path.exists(LEDGER) else {"items": []}


def save(L):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    json.dump(L, open(LEDGER, "w"), indent=1)


def _id(*parts):
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12]


def payout(price):
    return dec(price) - 1


def add_board(L, board, now):
    have = {i["id"] for i in L["items"]}
    n = 0
    for g in board:
        for mk, m in g["markets"].items():
            if m.get("decision") != "PICK":
                continue
            b = m["best"]
            iid = _id("board", g["toa_id"], mk, b["side"])
            if iid in have:
                continue
            L["items"].append(dict(id=iid, tab="board", sport=g["sport"], logged_ct=now.isoformat(timespec="minutes"), kick_iso=g["kick_iso"],
                                   kick_ct=g["kick_ct"], home=g["home"], away=g["away"], market=mk, side=b["side"], pick=b["team"],
                                   line=b["line"], price=b["price"], book=b["book"], model_pct=b["model_pct"], market_pct=b["market_pct"],
                                   ev=b["ev"], stake_u=1.0, status="open"))
            n += 1
    return n


def void_rule_changes(L, now):
    """Rule change 2026-10-03: no ML picks. Open board ML items whose game has not kicked are pulled (VOID);
    the original stamp is kept."""
    n = 0
    for it in L["items"]:
        if it["tab"] == "board" and it["market"] == "ml" and it["status"] == "open" and dt.datetime.fromisoformat(it["kick_iso"]) > now:
            it.update(status="VOID", units=0.0, void_reason="pulled before kickoff: ML is reference-only from 2026-10-03 (ML backtest EV>=2%: 253 bets -22.3u)",
                      voided_ct=now.isoformat(timespec="minutes"))
            n += 1
    return n


def add_props(L, props, now, within_h=24):
    have = {i["id"] for i in L["items"]}
    n = 0
    for g in props:
        k = dt.datetime.fromisoformat(g["kick_iso"])
        if not (0 < (k - now).total_seconds() / 3600 <= within_h):
            continue
        if any(i.get("toa_id") == g["toa_id"] and i["tab"] == "props" for i in L["items"]):
            continue  # a game's five are locked once
        home, away = g["game"].split(" @ ")[1], g["game"].split(" @ ")[0]
        for r in g["top"]:
            iid = _id("props", g["toa_id"], r["player"], r["market"], r["side"])
            if iid in have:
                continue
            L["items"].append(dict(id=iid, tab="props", sport="nfl", toa_id=g["toa_id"], logged_ct=now.isoformat(timespec="minutes"),
                                   kick_iso=g["kick_iso"], kick_ct=g["kick_ct"], home=home, away=away, player=r["player"],
                                   market=r["market"], side=r["side"], line=r["line"], price=r["price"], book=r["book"],
                                   model_pct=r["model_pct"], market_pct=r["market_pct"], edge=r["edge"], stake_u=1.0, status="open"))
            n += 1
    return n


def add_teasers(L, sets, now):
    """Log each day set once, on the run whose CT date is the set's date (Sat 9am run -> Saturday CFB,
    Sun 9am run -> Sunday NFL), before its first leg kicks. Keyed by set + date."""
    n = 0
    today = now.astimezone(CT).date().isoformat()
    for sk, S in sets.items():
        T = S["tickets"]
        if not T or S["date"] != today:
            continue
        first = min(dt.datetime.fromisoformat(l["kick_iso"]) for t in T for l in t["legs"])
        if first <= now:
            continue
        key = f"{sk}:{S['date']}"
        if any(i["tab"] == "teasers" and i.get("set_key") == key for i in L["items"]):
            continue
        for t in T:
            L["items"].append(dict(id=_id("teaser", key, t["n"]), tab="teasers", set=sk, set_label=S["label"], set_key=key, n=t["n"], name=t["name"],
                                   decision=t["decision"], logged_ct=now.isoformat(timespec="minutes"), kick_iso=max(l["kick_iso"] for l in t["legs"]),
                                   p_all_six=t["p_all_six"], ev=t["ev_per_unit"], price=600, stake_u=1.0, status="open",
                                   legs=[dict(sport=l["sport"], home=l["game"].split(" @ ")[1], away=l["game"].split(" @ ")[0], kick_iso=l["kick_iso"],
                                              market=l["market"], side=l["side"], pick=l["pick"], orig_line=l["orig_line"], teased_line=l["teased_line"],
                                              p=l["p_cond"], status="open") for l in t["legs"]]))
            n += 1
    return n


_SB = {}


def find_game(sport, home, away, kick_iso):
    k = dt.datetime.fromisoformat(kick_iso)
    dates = {k.astimezone(CT).strftime("%Y%m%d"), k.astimezone(dt.timezone.utc).strftime("%Y%m%d")}
    for d in dates:
        key = (sport, d)
        if key not in _SB:
            _SB[key] = espn.games(espn.scoreboard(sport, d))
        for g in _SB[key]:
            if {norm(g["home"]), norm(g["away"])} == {norm(home), norm(away)}:
                flip = norm(g["home"]) != norm(home)
                return g, flip
    return None, None


def grade_side(market, side, line, g, flip):
    hs, as_ = (g["away_score"], g["home_score"]) if flip else (g["home_score"], g["away_score"])
    margin, total = hs - as_, hs + as_
    if market == "ml":
        if margin == 0: return "P"
        return "W" if (margin > 0) == (side == "home") else "L"
    if market == "spread":
        v = (margin + line) if side == "home" else (-margin + line)
    else:
        v = (total - line) if side == "over" else (line - total)
    return "P" if v == 0 else ("W" if v > 0 else "L")


_BOX = {}


def grade(L, now):
    n = 0
    for it in L["items"]:
        if it["status"] != "open":
            continue
        if dt.datetime.fromisoformat(it["kick_iso"]) > now - dt.timedelta(hours=4):
            continue
        if it["tab"] == "board":
            g, flip = find_game(it["sport"], it["home"], it["away"], it["kick_iso"])
            if not g or not g["completed"]:
                continue
            r = grade_side(it["market"], it["side"], it["line"], g, flip)
            it.update(status=r, units=0.0 if r == "P" else (payout(it["price"]) if r == "W" else -1.0),
                      final=f"{g['away']} {g['away_score']:.0f} @ {g['home']} {g['home_score']:.0f}", espn_id=g["id"], settled_ct=now.isoformat(timespec="minutes"))
            n += 1
        elif it["tab"] == "props":
            g, flip = find_game("nfl", it["home"], it["away"], it["kick_iso"])
            if not g or not g["completed"]:
                continue
            if g["id"] not in _BOX:
                _BOX[g["id"]] = espn.box_players(espn.summary("nfl", g["id"]))
            st = _BOX[g["id"]].get(pname(it["player"]))
            val = None if st is None else st.get(STAT_OF[it["market"]])
            if it["market"] == "Anytime TD" and st is not None:
                val = st.get("anytime_td", 0.0)
            if val is None:
                it.update(status="VOID", units=0.0, note="player not in ESPN box score (DNP?)", settled_ct=now.isoformat(timespec="minutes")); n += 1
                continue
            if it["market"] == "Anytime TD":
                r = "W" if val > 0 else "L"
            else:
                r = "P" if val == it["line"] else ("W" if (val > it["line"]) == (it["side"] == "Over") else "L")
            it.update(status=r, actual=val, units=0.0 if r == "P" else (payout(it["price"]) if r == "W" else -1.0),
                      espn_id=g["id"], settled_ct=now.isoformat(timespec="minutes"))
            n += 1
        elif it["tab"] == "teasers":
            done = True
            for l in it["legs"]:
                if l["status"] != "open":
                    continue
                if dt.datetime.fromisoformat(l["kick_iso"]) > now - dt.timedelta(hours=4):
                    done = False; continue
                g, flip = find_game(l["sport"], l["home"], l["away"], l["kick_iso"])
                if not g or not g["completed"]:
                    done = False; continue
                mk = "spread" if l["market"] == "spread" else "total"
                l["status"] = grade_side(mk, l["side"], l["teased_line"], g, flip)
                l["final"] = f"{g['away_score']:.0f}-{g['home_score']:.0f}"
            res = [l["status"] for l in it["legs"]]
            if "L" in res:
                it.update(status="L", units=-1.0, settled_ct=now.isoformat(timespec="minutes")); n += 1
            elif done and "open" not in res:
                u = settle(res)
                it.update(status="W" if u > 0 else "P", units=u, settled_ct=now.isoformat(timespec="minutes")); n += 1
    return n


def _rec(s):
    v = sum(i["status"] == "VOID" for i in s); s = [i for i in s if i["status"] != "VOID"]
    w = sum(i["status"] == "W" for i in s); l = sum(i["status"] == "L" for i in s); p = sum(i["status"] == "P" for i in s)
    u = round(sum(i.get("units", 0) for i in s), 2)
    return dict(record=f"{w}-{l}-{p}", units=u, dollars=round(u * 20, 2), settled=len(s), void=v)


def headline(L):
    out = {}
    done = lambda its: [i for i in its if i["status"] in ("W", "L", "P", "VOID")]
    for tab in ("board", "props", "teasers"):
        its = [i for i in L["items"] if i["tab"] == tab]
        out[tab] = dict(_rec(done(its)), open=len(its) - len(done(its)))
    for sk, lab in (("cfb_sat", "Saturday CFB"), ("nfl_sun", "Sunday NFL")):
        its = [i for i in L["items"] if i["tab"] == "teasers" and i.get("set") == sk]
        s = done(its)
        out["teasers_" + sk] = dict(_rec(s), label=lab, open=len(its) - len(s),
                                   ticket1=_rec([i for i in s if i.get("n") == 1]),
                                   play_only=_rec([i for i in s if i.get("decision") == "PLAY"]))
    return out
