"""RECHECK role (~11:30am CT Sat/Sun): re-pull lines only for today's games not yet started, then
- drop any 9am board PICK whose EV (same side, best of DK/Bovada) fell below the pick threshold or whose line moved
  through a key number;
- drop any teaser leg whose line moved through a key number, or whose fresh leg % fell below threshold: it crossed below
  the per-leg break-even (72.3%), or it fell more than 1pp from its 9am value. A ticket with a dropped leg is pulled (VOID);
  a 9am PLAY ticket whose recomputed EV at +600 is no longer > 0 is also pulled.
No new picks are added at recheck (picks lock at 9am). The ledger keeps every original stamp; pulled items are marked VOID
with void_reason/voided_ct. Credits: 6 per sport re-pulled (us+eu x h2h/spreads/totals, filtered by eventIds),
reserved by the 9am run, still capped by toa.DAILY_CAP."""
import datetime as dt, json, os, gzip
from zoneinfo import ZoneInfo
from . import toa, lines, board, teasers, grader
from .teaser_math import DK6, breakeven_leg, ticket_prob

CT = ZoneInfo("America/Chicago")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DATA = os.path.join(ROOT, "docs", "data")
KEYS = {("nfl", "spread"): (3, 7, 10, 14), ("cfb", "spread"): (3, 7, 10, 14, 17, 21),
        ("nfl", "total"): (37, 41, 44, 47, 51), ("cfb", "total"): ()}
COST = 6


def through_key(sport, mkt, old, new):
    """True if the line moved strictly across a key number (spreads: +/-k on the signed line)."""
    if old is None or new is None or old == new:
        return None
    lo, hi = min(old, new), max(old, new)
    ks = KEYS.get((sport, mkt), ())
    cands = [k for k in ks] + ([-k for k in ks] if mkt == "spread" else [])
    hit = [k for k in cands if lo < k < hi]
    return hit[0] if hit else None


def today_unstarted(data, now):
    d = now.astimezone(CT).date()
    return [e for e in (data or []) if (k := dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))) > now
            and k.astimezone(CT).date() == d]


def sports_for(now):
    """Which sports get a recheck today: Saturday -> CFB, Sunday -> NFL (only if they have games today)."""
    wd = now.astimezone(CT).weekday()
    return ["cfb"] if wd == 5 else (["nfl"] if wd == 6 else [])


def pull(sport, ids, stamp):
    d, row = toa.get(f"/v4/sports/{lines.SPORTS[sport]}/odds",
                     {"regions": "us,eu", "markets": "h2h,spreads,totals", "oddsFormat": "american", "eventIds": ",".join(ids)},
                     COST, f"recheck odds {sport}")
    os.makedirs(os.path.join(lines.RAW, "odds"), exist_ok=True)
    p = os.path.join(lines.RAW, "odds", f"recheck_{sport}_{stamp}.json.gz")
    json.dump({"pulled_ct": dt.datetime.now(CT).isoformat(timespec="seconds"), "credits": row, "data": d}, gzip.open(p, "wt"))
    return d


def run(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    nct = now.astimezone(CT); stamp = nct.strftime("%Y%m%d_%H%M"); season = nct.year if nct.month >= 3 else nct.year - 1
    Bj = json.load(open(os.path.join(SITE_DATA, "board.json")))
    Tj = json.load(open(os.path.join(SITE_DATA, "teasers.json")))
    rep = dict(ran_ct=nct.strftime("%a %b %-d %-I:%M %p CT"), sports={}, board_changes=[], teaser_changes=[], notes=[])
    fresh = {}
    for sp in sports_for(now):
        j, _ = lines.latest(sp)
        ev = today_unstarted(j["data"] if j else [], now)
        if not ev:
            rep["sports"][sp] = "no unstarted games today"; continue
        try:
            fresh[sp] = pull(sp, [e["id"] for e in ev], stamp)
            rep["sports"][sp] = f"re-pulled {len(fresh[sp])} unstarted games ({COST} credits)"
        except toa.BudgetError as ex:
            rep["sports"][sp] = f"skipped: {ex}"
        except Exception as ex:
            rep["sports"][sp] = f"error: {ex!r}"
    L = grader.load()
    voided = 0
    if fresh:
        new_rows = {}
        for sp, data in fresh.items():
            for e in data:
                if dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) > now:
                    new_rows[e["id"]] = board.game_row(e, sp, season)
        # ---- board picks ----
        for g in Bj["games"]:
            nr = new_rows.get(g["toa_id"])
            if not nr:
                continue
            for mk, m in g["markets"].items():
                nm = nr["markets"].get(mk, {})
                if m.get("decision") == "PICK":
                    b = m["best"]
                    same = [s for s in nm.get("sides", []) if s["side"] == b["side"]]
                    nb = max(same, key=lambda s: s["ev"]) if same else None
                    k = through_key(g["sport"], mk, b["line"], nb["line"] if nb else None) if mk != "ml" else None
                    why = ("no DK/Bovada price at recheck" if nb is None else
                           f"EV {nb['ev']*100:+.1f}% < {board.EV_PICK*100:.0f}%" if nb["ev"] < board.EV_PICK else
                           f"line moved through key {k:g} ({b['line']:+g} -> {nb['line']:+g})" if k is not None else None)
                    ch = dict(game=f"{g['away']} @ {g['home']}", market=mk, pick=b["team"], line_9am=b["line"], price_9am=b["price"], ev_9am=b["ev"],
                              line_now=nb and nb["line"], price_now=nb and nb["price"], ev_now=nb and nb["ev"], book_now=nb and nb["book"],
                              action="DROPPED" if why else "KEPT", reason=why or "still >= threshold, no key crossed")
                    rep["board_changes"].append(ch)
                    m["recheck"] = ch
                    if why:
                        m.update(decision="DROPPED", reason=f"11:30 recheck: {why}")
                        for it in L["items"]:
                            if (it["tab"] == "board" and it["status"] == "open" and it["market"] == mk and it["side"] == b["side"]
                                    and it["home"] == g["home"] and it["away"] == g["away"] and dt.datetime.fromisoformat(it["kick_iso"]) > now):
                                it.update(status="VOID", units=0.0, void_reason=f"pulled before kickoff at recheck: {why}",
                                          voided_ct=now.isoformat(timespec="minutes")); voided += 1
                # refresh displayed prices for this market (decisions are not upgraded at recheck)
                m["sides_recheck"] = nm.get("sides", [])
        # ---- teaser legs ----
        be = breakeven_leg(6, DK6[6])
        nlegs = {(l["game"], l["market"], l["side"]): l for l in teasers.candidate_legs(fresh, season, now)}
        for sk, S in Tj.get("sets", {}).items():
            if S["sport"] not in fresh:
                continue
            for t in S["tickets"]:
                dropped = []
                for l in t["legs"]:
                    if dt.datetime.fromisoformat(l["kick_iso"]) <= now:
                        continue  # already started: cannot recheck
                    nl = nlegs.get((l["game"], l["market"], l["side"]))
                    k = through_key(S["sport"], l["market"], l["orig_line"], nl["orig_line"] if nl else None)
                    p0 = l["p_cond"]
                    why = ("no line at recheck" if nl is None else
                           f"line moved through key {k:g} ({l['orig_line']:+g} -> {nl['orig_line']:+g})" if k is not None else
                           f"leg % {p0*100:.1f} -> {nl['p_cond']*100:.1f}, below break-even {be*100:.1f}" if (nl["p_cond"] < be <= p0) else
                           f"leg % fell {p0*100:.1f} -> {nl['p_cond']*100:.1f} (>1pp)" if nl["p_cond"] < p0 - 0.01 else None)
                    l["recheck"] = dict(line_now=nl and nl["orig_line"], p_now=nl and round(nl["p_cond"], 4), action="DROPPED" if why else "KEPT", reason=why)
                    if why:
                        dropped.append(f"{l['pick']} {l['orig_line']:+g}: {why}")
                if not dropped and t["decision"] == "PLAY":
                    pr = [(nlegs[(l["game"], l["market"], l["side"])]["p_win"], nlegs[(l["game"], l["market"], l["side"])]["p_push"])
                          if (l["game"], l["market"], l["side"]) in nlegs else (l["p_win"], l["p_push"]) for l in t["legs"]]
                    _, ev_now = ticket_prob(pr)
                    t["ev_recheck"] = round(ev_now, 4)
                    if ev_now <= 0:
                        dropped.append(f"ticket EV {t['ev_per_unit']*100:+.1f}% -> {ev_now*100:+.1f}% (no longer > 0)")
                if dropped:
                    t["decision_9am"] = t["decision"]; t["decision"] = "VOID"
                    rep["teaser_changes"].append(dict(set=S["label"], n=t["n"], dropped=dropped))
                    for it in L["items"]:
                        if it["tab"] == "teasers" and it.get("set") == sk and it.get("set_key") == f"{sk}:{S['date']}" and it["n"] == t["n"] and it["status"] == "open":
                            it.update(status="VOID", units=0.0, void_reason="pulled before kickoff at recheck: " + "; ".join(dropped),
                                      voided_ct=now.isoformat(timespec="minutes")); voided += 1
    grader.save(L)
    rep["ledger_voided"] = voided
    today = nct.strftime("%Y-%m-%d")
    meta = dict(Bj["meta"])
    meta["headline"] = grader.headline(L); meta["recheck"] = rep
    meta["credits"] = dict(meta.get("credits", {}), spent_today=toa.spent(today, "daily"))
    for name, obj in (("board", Bj), ("teasers", Tj)):
        obj["meta"] = meta; json.dump(obj, open(os.path.join(SITE_DATA, f"{name}.json"), "w"))
    for name in ("props",):
        p = os.path.join(SITE_DATA, f"{name}.json"); o = json.load(open(p)); o["meta"] = meta; json.dump(o, open(p, "w"))
    json.dump(dict(meta=meta, ledger=L), open(os.path.join(SITE_DATA, "ledger.json"), "w"))
    json.dump(meta, open(os.path.join(SITE_DATA, "meta.json"), "w"))
    json.dump(rep, open(os.path.join(SITE_DATA, "recheck.json"), "w"))
    print(json.dumps(rep, indent=1)[:4000])


if __name__ == "__main__":
    run()
