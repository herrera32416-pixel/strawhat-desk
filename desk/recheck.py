"""RECHECK role: kickoff-driven pre-kick rechecks (since 2026-10-04; replaces the single ~11:30am slot).
Scheduled crons fire every 30 min on game days (:15/:45); desk/recheck_plan.py decides whether anything OPEN kicks
within 70 min and has not been rechecked yet. Typical Sunday: ~11:15am CT (noon games), ~2:15pm (3:05/3:25),
~6:15pm (7:20 SNF), each with a :45 backup. Per pass:
- Official items (board picks): re-pull lines for the affected games only (eventIds filter;
  us+eu x spreads,totals = 4 credits per sport, under the 40/day cap; the 9am run reserves them).
  * Board pick DROPPED if EV (same side, best of DK/Bovada) < 3%, the line moved through a key number, or the fair line
    now differs from the book line by > 3 points.
  * Teasers/parlays were retired 2026-10-08 (none are produced, so none are rechecked).
- Props (research): free ESPN injury report for the game; a prop on a player now listed Out/IR/inactive is VOID.
No new picks are added at recheck. The ledger keeps the original stamp; pulled items are VOID with void_reason/voided_ct.
Rechecked item ids are stored in data/recheck_done.json (per CT day) so backups don't repeat work or spend credits."""
import datetime as dt, json, os, gzip, sys
from zoneinfo import ZoneInfo
from . import toa, lines, board, grader, espn
from .recheck_plan import plan, load_done, DONE, COST, WINDOW_MIN, MAX_WINDOWS, windows
from .names import norm

CT = ZoneInfo("America/Chicago")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DATA = os.path.join(ROOT, "docs", "data")
KEYS = {("nfl", "spread"): (3, 7, 10, 14), ("cfb", "spread"): (3, 7, 10, 14, 17, 21),
        ("nfl", "total"): (37, 41, 44, 47, 51), ("cfb", "total"): ()}


def through_key(sport, mkt, old, new):
    """True if the line moved strictly across a key number (spreads: +/-k on the signed line)."""
    if old is None or new is None or old == new:
        return None
    lo, hi = min(old, new), max(old, new)
    ks = KEYS.get((sport, mkt), ())
    cands = [k for k in ks] + ([-k for k in ks] if mkt == "spread" else [])
    hit = [k for k in cands if lo < k < hi]
    return hit[0] if hit else None


def reserve_credits(kicks):
    """Credits the 9am run must hold back: COST per distinct recheck window of today's official items (max 3)."""
    return COST * min(MAX_WINDOWS, windows(kicks))


def sports_for(now):  # kept for backward compatibility (old callers); recheck is now item-driven
    wd = now.astimezone(CT).weekday()
    return ["cfb"] if wd == 5 else (["nfl"] if wd == 6 else [])


def pull(sport, ids, stamp):
    d, row = toa.get(f"/v4/sports/{lines.SPORTS[sport]}/odds",
                     {"regions": "us,eu", "markets": "spreads,totals", "oddsFormat": "american", "eventIds": ",".join(ids)},
                     COST, f"recheck odds {sport}")
    os.makedirs(os.path.join(lines.RAW, "odds"), exist_ok=True)
    p = os.path.join(lines.RAW, "odds", f"recheck_{sport}_{stamp}.json.gz")
    json.dump({"pulled_ct": dt.datetime.now(CT).isoformat(timespec="seconds"), "credits": row, "data": d}, gzip.open(p, "wt"))
    return d


def _eid_map():
    """(sport, norm home, norm away) -> TOA event id, from the latest daily odds files."""
    m = {}
    for sp in ("nfl", "cfb"):
        j, _ = lines.latest(sp)
        for e in (j or {}).get("data", []):
            m[(sp, norm(e["home_team"]), norm(e["away_team"]))] = e["id"]
    return m


def _load(name, default):
    p = os.path.join(SITE_DATA, f"{name}.json")
    try:
        return json.load(open(p))
    except Exception:
        return default


def run(now=None, dry=False):
    now = now or dt.datetime.now(dt.timezone.utc)
    nct = now.astimezone(CT); stamp = nct.strftime("%Y%m%d_%H%M"); season = nct.year if nct.month >= 3 else nct.year - 1
    L = grader.load()
    P = plan(now, L)
    print(P["why"])
    if not P["go"] or dry:
        return None
    Bj = _load("board", {"meta": {}, "games": []})
    rep = dict(ran_ct=nct.strftime("%a %b %-d %-I:%M %p CT"), window_min=WINDOW_MIN, sports={}, board_changes=[],
               props_changes=[], notes=[P["why"]])
    voided = 0
    done = load_done(now)
    # ---------- official items: line re-pull ----------
    if P["odds"]:
        eids = _eid_map(); need = {}
        for it in P["odds"]:
            games = [(it["sport"], it["home"], it["away"])] if it["tab"] == "board" else \
                    [(l["sport"], l["home"], l["away"]) for l in it["legs"] if dt.datetime.fromisoformat(l["kick_iso"]) > now]
            for sp, h, a in games:
                e = eids.get((sp, norm(h), norm(a)))
                if e:
                    need.setdefault(sp, set()).add(e)
                else:
                    rep["notes"].append(f"no odds event id for {a} @ {h}")
        fresh = {}
        for sp, ids in need.items():
            try:
                fresh[sp] = pull(sp, sorted(ids), stamp)
                rep["sports"][sp] = f"re-pulled {len(fresh[sp])} game(s) ({COST} credits)"
            except toa.BudgetError as ex:
                rep["sports"][sp] = f"skipped: {ex}"
            except Exception as ex:
                rep["sports"][sp] = f"error: {ex!r}"
        rows = {}
        for sp, data in fresh.items():
            for e in data:
                if dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) > now:
                    r = board.game_row(e, sp, season); rows[(norm(r["home"]), norm(r["away"]))] = r
        for it in P["odds"]:
            if it["tab"] == "board":
                nr = rows.get((norm(it["home"]), norm(it["away"])))
                if nr is None and it["sport"] not in fresh:
                    continue  # pull failed: leave open, do not mark done (a backup slot can retry)
                nm = (nr or {}).get("markets", {}).get(it["market"], {})
                same = [s for s in nm.get("sides", []) if s["side"] == it["side"]]
                nb = max(same, key=lambda s: s["ev"]) if same else None
                k = through_key(it["sport"], it["market"], it["line"], nb["line"] if nb else None) if it["market"] != "ml" else None
                fc = nm.get("fair_center")
                ptg = None
                if nb and fc is not None and nb.get("line") is not None:
                    bc = nb["line"] if it["market"] == "total" else (-nb["line"] if nb["side"] == "home" else nb["line"])
                    ptg = abs(fc - bc)
                why = ("no DK/Bovada price at recheck" if nb is None else
                       f"EV {nb['ev']*100:+.1f}% < {board.EV_PICK*100:.0f}%" if nb["ev"] < board.EV_PICK else
                       f"line moved through key {k:g} ({it['line']:+g} -> {nb['line']:+g})" if k is not None else
                       f"fair vs book line gap {ptg:.1f} > {board.MAX_PT_GAP:g} pts" if (ptg is not None and ptg > board.MAX_PT_GAP) else None)
                ch = dict(game=f"{it['away']} @ {it['home']}", market=it["market"], pick=it["pick"], line_9am=it["line"], price_9am=it["price"],
                          ev_9am=it["ev"], line_now=nb and nb["line"], price_now=nb and nb["price"], ev_now=nb and nb["ev"],
                          book_now=nb and nb["book"], action="DROPPED" if why else "KEPT", reason=why or "still >= threshold, no key crossed")
                rep["board_changes"].append(ch)
                for g in Bj.get("games", []):
                    if g["home"] == it["home"] and g["away"] == it["away"] and it["market"] in g["markets"]:
                        m = g["markets"][it["market"]]; m["recheck"] = ch; m["sides_recheck"] = nm.get("sides", [])
                        if why:
                            m.update(decision="DROPPED", reason=f"pre-kick recheck: {why}")
                if why:
                    it.update(status="VOID", units=0.0, void_reason=f"pulled before kickoff at recheck: {why}",
                              voided_ct=now.isoformat(timespec="minutes")); voided += 1
                done["items"].append(it["id"])
    # ---------- props: injury report (free) ----------
    for it in P["props"]:
        inj = espn.injuries_for_game("nfl", it["home"], it["away"], it["kick_iso"])
        if inj is None:
            rep["notes"].append(f"injury report unavailable for {it['away']} @ {it['home']}"); continue
        from .props import pname
        st = inj.get(pname(it["player"]))
        if st in espn.OUT_STATUSES:
            it.update(status="VOID", units=0.0, void_reason=f"player listed {st} at recheck (ESPN injury report)",
                      voided_ct=now.isoformat(timespec="minutes")); voided += 1
            rep["props_changes"].append(dict(player=it["player"], market=it["market"], side=it["side"], status=st, action="VOID"))
        done["items"].append(it["id"])
    rep["ledger_voided"] = voided
    rep["props_checked"] = len(P["props"])
    grader.save(L)
    json.dump(done, open(DONE, "w"), indent=0)
    today = nct.strftime("%Y-%m-%d")
    prev = _load("recheck", {})
    passes = (prev.get("passes", []) if prev.get("date") == today else []) + [rep]
    meta = dict(Bj.get("meta") or {})
    meta["headline"] = grader.headline(L); meta["recheck"] = rep; meta["recheck_passes"] = passes
    meta["credits"] = dict(meta.get("credits", {}), spent_today=toa.spent(today, "daily"))
    for name, obj in (("board", Bj),):
        obj["meta"] = meta; json.dump(obj, open(os.path.join(SITE_DATA, f"{name}.json"), "w"))
    p = os.path.join(SITE_DATA, "props.json")
    if os.path.exists(p):
        o = json.load(open(p)); o["meta"] = meta; json.dump(o, open(p, "w"))
    json.dump(dict(meta=meta, ledger=L), open(os.path.join(SITE_DATA, "ledger.json"), "w"))
    json.dump(meta, open(os.path.join(SITE_DATA, "meta.json"), "w"))
    json.dump(dict(date=today, passes=passes, **rep), open(os.path.join(SITE_DATA, "recheck.json"), "w"))
    print(json.dumps(rep, indent=1, default=str)[:4000])
    return rep


if __name__ == "__main__":
    run(dry="--dry" in sys.argv)
