"""TEASERS role: two day sets of 6-point teasers from DK (fallback Bovada) lines:
'Saturday CFB' (only Saturday CFB games) and 'Sunday NFL' (only Sunday NFL games; Mon/Thu excluded).
Leg probability = KEYS pmf at the consensus fair center, evaluated at the teased line, then shrunk toward the
leg's historical band win rate (bands = Wong/key-number bands; rates from closes, k=150).
Rules since 2026-10-04: spread legs only (totals are still scored and listed, never ticketed). Ticket #1 = Wong-first,
every leg >= 72.3%, 4-6 legs at the standard payout (+260/+400/+600); PLAY only for NFL when model EV > 0.
CFB is always PASS (research). Tickets #2-5 = research (greedy next-best spread legs), always PASS."""
import json, os, collections, itertools, math
from .teaser_math import DK6, dec, breakeven_leg, ticket_prob, MIN_LEG_P
from .market import parse_event
from .board import dist, BOOKN, consensus_center, nfl_cutoff
from .names import norm
import datetime as dt
from zoneinfo import ZoneInfo
CT = ZoneInfo("America/Chicago")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANDS = os.path.join(ROOT, "data", "teaser_bands.json")
T = 6.0
K = 150


def band(mkt, side, orig):
    if mkt == "total":
        return f"total {side} {'<=41' if orig <= 41 else ('41.5-47' if orig <= 47 else '>47')}"
    o = orig
    if -8.5 <= o <= -7.5: return "Wong fav -7.5..-8.5"
    if 1.5 <= o <= 2.5: return "Wong dog +1.5..+2.5"
    if o == 3: return "dog +3"
    if -3 <= o <= -1: return "fav -1..-3"
    if -7 <= o <= -3.5: return "fav -3.5..-7"
    if o < -8.5: return "fav < -8.5"
    if 3.5 <= o <= 7: return "dog +3.5..+7"
    if o > 7: return "dog > +7"
    return "pk/other"


def load_bands():
    return json.load(open(BANDS)) if os.path.exists(BANDS) else {}


def candidate_legs(odds_by_sport, season, now, cfb_ok=True):
    bands = load_bands()
    legs = []
    for sport, data in odds_by_sport.items():
        if not data:
            continue
        for e in data:
            k = dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
            hrs = (k - now).total_seconds() / 3600
            if hrs <= 0 or hrs > 8 * 24:
                continue
            books = parse_event(e)
            src = "draftkings" if "draftkings" in books else ("bovada" if "bovada" in books else None)
            if not src:
                continue
            gname = f"{e['away_team']} @ {e['home_team']}"
            kick = k.astimezone(CT).strftime("%a %-I:%M %p CT")
            for mkt, kind in (("spreads", "margin"), ("totals", "total")):
                if mkt not in books[src]:
                    continue
                D = dist(f"{sport}_{kind}", season)
                c, n, _ = consensus_center(books, mkt, D)
                if c is None:
                    continue
                if mkt == "spreads":
                    hp, _, ap, _ = books[src]["spreads"]
                    opts = [("spread", "home", e["home_team"], hp, -(hp + T)), ("spread", "away", e["away_team"], ap, ap + T)]
                else:
                    tp = books[src]["totals"][0]
                    opts = [("total", "over", "Over", tp, tp - T), ("total", "under", "Under", tp, tp + T)]
                for m, side, team, orig, thr in opts:
                    w, pu, l = D.probs(c, thr)
                    if side in ("away", "under"):
                        w, l = l, w
                    cond = w / max(w + l, 1e-9)
                    b = band(m, side, orig)
                    bs = bands.get(sport, {}).get(b)
                    adj = cond
                    if bs and bs["n"] > 0:
                        adj = (bs["w"] + K * cond) / (bs["n"] + K)
                    teased = orig + T if m == "spread" else thr
                    legs.append(dict(sport=sport, game=gname, toa_id=e["id"], kick_ct=kick, kick_iso=k.isoformat(), kick_date=k.astimezone(CT).date().isoformat(), market=m,
                                     side=side, pick=team, orig_line=orig, teased_line=teased, book=BOOKN[src], band=b,
                                     p_keys=round(cond, 4), p_band=None if not bs else round(bs["w"] / bs["n"], 4),
                                     p_push=round(pu, 4), p_win=round(adj * (1 - pu), 4), p_cond=round(adj, 4)))
    return legs


def rank_key(l):
    """Wong-style ordering: Wong legs (dog +1.5..+2.5, fav -7.5..-8.5: teased through both 3 and 7) first, then by leg %."""
    return (0 if str(l.get("band", "")).startswith("Wong") else 1, -l["p_cond"])


def rule_ticket(legs, sport):
    """Ticket #1 (the only ticket that can be a PLAY). Rules from 2026-10-04 (weekend eval, approved by Luis):
    spread legs only (no totals); every leg p_cond >= MIN_LEG_P (72.3%, the 6-leg break-even); one leg per game;
    Wong legs ranked first, then by leg %; up to 6 legs, and a 4- or 5-leg ticket at the standard payout when fewer
    than 6 legs qualify (never padded with weaker legs). Fewer than 4 qualifying legs -> no ticket."""
    pool = sorted([l for l in legs if l["market"] == "spread" and l["p_cond"] >= MIN_LEG_P], key=rank_key)
    tk, gs = [], set()
    for l in pool:
        if l["game"] in gs:
            continue
        tk.append(l); gs.add(l["game"])
        if len(tk) == 6:
            break
    return tk if len(tk) >= 4 else [], len(pool)


def _ticket(n, name, tk, sport, research):
    k = len(tk)
    pw, evv = ticket_prob([(l["p_win"], l["p_push"]) for l in tk])
    p_all = math.prod(l["p_cond"] for l in tk)
    if research:
        decision, why = "PASS", "research ticket (never a play)"
    elif sport != "nfl":
        decision, why = "PASS", "CFB teasers are research only (CFB ticket #1 backtest -21u on 35)"
    else:
        decision, why = ("PLAY", f"model EV {evv*100:+.1f}% > 0 at {DK6[k]:+d}") if evv > 0 else ("PASS", f"model EV {evv*100:+.1f}% <= 0")
    return dict(n=n, name=name, legs=tk, n_legs=k, p_all_six=round(p_all, 4), p_all_legs=round(p_all, 4), p_cash_incl_push=round(pw, 4),
                breakeven_ticket=round(1 / dec(DK6[k]), 4), breakeven_leg=round(breakeven_leg(k), 4), ev_per_unit=round(evv, 4),
                decision=decision, decision_reason=why, kind="research" if (research or decision != "PLAY") else "official",
                price=DK6[k], payout=f"{DK6[k]:+d} (DK & Bovada {k}-team 6-pt; ties reduce)")


def build_set(legs, sport, n_tickets=5, cap=2):
    """One day's set from legs of ONE sport.
    Ticket #1 = rule_ticket (spread-only, Wong-first, every leg >= 72.3%, 4-6 legs). PLAY only for NFL with model EV > 0.
    Tickets #2-5 = research: greedy next-best SPREAD legs (no totals), 6 legs, each leg used <= cap times, one leg per
    game per ticket; always PASS (kept to keep measuring how weaker legs do)."""
    out = []
    use = collections.Counter()
    t1, nq = rule_ticket(legs, sport)
    if t1:
        nm = f"Ticket #1: {len(t1)}-leg rule ticket (spread only, Wong first, every leg >= {MIN_LEG_P*100:.1f}%)"
        out.append(_ticket(1, nm, t1, sport, research=False))
        for l in t1:
            use[id(l)] += 1
    pool = sorted([l for l in legs if l["market"] == "spread"], key=lambda l: -l["p_cond"])
    while len(out) < n_tickets:
        tk, gs = [], set()
        for l in sorted(pool, key=lambda l: (use[id(l)], -l["p_cond"])):
            if use[id(l)] >= cap or l["game"] in gs:
                continue
            tk.append(l); gs.add(l["game"])
            if len(tk) == 6:
                break
        if len(tk) < 6:
            break
        for l in tk:
            use[id(l)] += 1
        n = len(out) + (1 if t1 else 2)
        out.append(_ticket(n, f"Ticket #{n}: research (next-best spread legs, each used <=2x)", tk, sport, research=True))
    for t in out:
        t["max_leg_use"] = max(use[id(l)] for l in t["legs"])
        t["n_qualifying_legs"] = nq
    return out


def next_dow(now, dow):
    """CT date of the next given weekday (Mon=0..Sun=6), today included."""
    d = now.astimezone(CT).date()
    return d + dt.timedelta(days=(dow - d.weekday()) % 7)


def build_days(legs, now):
    """Two sets: Saturday CFB (only Saturday CFB games) and Sunday NFL (only Sunday NFL games)."""
    sat, sun = next_dow(now, 5).isoformat(), next_dow(now, 6).isoformat()
    sets = {}
    for key, sport, day, label in (("cfb_sat", "cfb", sat, "Saturday CFB"), ("nfl_sun", "nfl", sun, "Sunday NFL")):
        L = [l for l in legs if l["sport"] == sport and l["kick_date"] == day]
        sets[key] = dict(key=key, label=label, sport=sport, date=day, n_candidate_legs=len(L), n_games=len({l["game"] for l in L}),
                         tickets=build_set(L, sport), top_legs=sorted(L, key=lambda l: -l["p_cond"])[:20])
    return sets
