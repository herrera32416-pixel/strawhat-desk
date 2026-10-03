"""PROPS live run: plan Odds API player-prop pulls under the daily cap, project, rank top 5 per NFL game."""
import datetime as dt, json, os, glob, math, statistics
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd
from . import toa
from .props import (load_stats, team_table, player_features, project, dfactors, pname, poisson_p_over, LABEL)
from .market import novig
from .names import NFL

CT = ZoneInfo("America/Chicago")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDIR = os.path.join(ROOT, "data", "raw", "props")
PRIORITY = ["player_reception_yds", "player_rush_yds", "player_pass_yds", "player_receptions", "player_anytime_td"]
STAT = {"player_reception_yds": "receiving_yards", "player_receptions": "receptions", "player_rush_yds": "rushing_yards",
        "player_pass_yds": "passing_yards", "player_pass_tds": "passing_tds", "player_anytime_td": "anytime_td"}
WINDOW_H = 54
SHOW_PER_GAME = 5
W_SHRINK = 0.2  # upper end of the 90% CI of the fitted model weight (0.00 [0, 0.23]) on 2026 wk2-3 real lines


def _load(eid):
    p = os.path.join(PDIR, f"{eid}.json")
    return json.load(open(p)) if os.path.exists(p) else None


def plan_and_pull(nfl_events, now, budget_left):
    """Round-robin markets across in-window events until the day's budget is used. Returns notes."""
    os.makedirs(PDIR, exist_ok=True)
    ev = [e for e in nfl_events if 0 < (dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) - now).total_seconds() / 3600 <= WINDOW_H]
    ev.sort(key=lambda e: e["commence_time"])
    have = {e["id"]: set((_load(e["id"]) or {}).get("markets_pulled", [])) for e in ev}
    want = {e["id"]: [m for m in PRIORITY if m not in have[e["id"]]] for e in ev}
    # how many markets per event can we afford this run?
    alloc = {e["id"]: [] for e in ev}
    left = budget_left
    for rnd in range(len(PRIORITY)):
        for e in ev:
            w = want[e["id"]]
            if rnd < len(w) and left >= 1:
                alloc[e["id"]].append(w[rnd]); left -= 1
    notes = []
    for e in ev:
        mk = alloc[e["id"]]
        if not mk:
            continue
        try:
            d, row = toa.get(f"/v4/sports/americanfootball_nfl/events/{e['id']}/odds",
                             {"regions": "us", "markets": ",".join(mk), "oddsFormat": "american"}, len(mk), f"props {e['away_team']}@{e['home_team']}")
        except toa.BudgetError as ex:
            notes.append(str(ex)); break
        except RuntimeError as ex:
            notes.append(str(ex)); continue
        old = _load(e["id"]) or {"event": {k: e[k] for k in ("id", "home_team", "away_team", "commence_time")}, "pulls": [], "markets_pulled": []}
        old["pulls"].append({"pulled_ct": dt.datetime.now(CT).isoformat(timespec="seconds"), "markets": mk, "bookmakers": d.get("bookmakers", []),
                             "credits_last": row.get("last")})
        old["markets_pulled"] = sorted(set(old["markets_pulled"]) | set(mk))
        json.dump(old, open(os.path.join(PDIR, f"{e['id']}.json"), "w"))
        notes.append(f"{e['away_team']}@{e['home_team']}: {','.join(mk)} ({row.get('last')} cr)")
    return notes


def offers(eid):
    """Latest price per (player, market, line, book, side) for an event."""
    j = _load(eid)
    if not j:
        return None, []
    latest = {}
    for pull in j["pulls"]:
        for b in pull["bookmakers"]:
            for m in b.get("markets", []):
                for o in m.get("outcomes", []):
                    k = (o.get("description"), m["key"], o.get("point"), b["key"], o["name"].lower())
                    latest[k] = dict(price=o["price"], pulled_ct=pull["pulled_ct"])
    return j["event"], latest


class Live:
    def __init__(self):
        art = json.load(open(os.path.join(ROOT, "data", "props_model.json")))
        self.art = art
        games = pd.read_csv(os.path.join(ROOT, "data", "history", "nfl_games.csv"), low_memory=False)
        self.d = load_stats([2024, 2025, 2026])
        self.t = team_table(self.d, games)
        self.league = art["league"]

    def player_state(self, pkey, teams):
        d = self.d[(self.d.pkey == pkey)]
        if d.empty:
            return None
        d = d.sort_values("order")
        last = d.iloc[-1]
        if last.team not in teams:
            return None
        # synthetic next-game row so the shifted EWMAs include every played game
        nxt = last.copy()
        for c in d.columns:
            if c not in ("player_id", "player_display_name", "position", "team", "pkey"):
                nxt[c] = np.nan
        nxt["order"] = 999999; nxt["game_id"] = "NEXT"; nxt["season"] = last.season
        sub = pd.concat([self.d[self.d.team == last.team], pd.DataFrame([nxt])], ignore_index=True)
        tt = self.t[self.t.team == last.team][["game_id", "team", "pass_att", "carries", "targets"]]
        pf = player_features(sub[sub.player_id == last.player_id].copy(), pd.concat([self.t]))
        row = pf[pf.game_id == "NEXT"]
        return None if row.empty else (row.iloc[0], last.team, int((d.season == d.season.max()).sum()))

    def team_vol(self, team, opp, exp_margin, implied):
        tt = self.t[self.t.team == team].sort_values("order")
        e_att = tt.pass_att.ewm(halflife=6).mean().iloc[-1]; e_car = tt.carries.ewm(halflife=6).mean().iloc[-1]
        c = self.art["coefs"]
        va = float(np.dot(c["pass_att"], [1, e_att, exp_margin, implied]))
        vc = float(np.dot(c["carries"], [1, e_car, exp_margin, implied]))
        od = self.t[self.t.opponent_team == opp].sort_values("order")
        drow = {f"dall_{k}": od[k].ewm(halflife=6).mean().iloc[-1] for k in ["ypt", "ypc", "ypa", "cr", "tds"]} if len(od) else None
        return va, vc, dfactors(drow, self.league)

    def p_over(self, market, proj, line):
        st = STAT[market]
        if st in ("anytime_td",):
            return 1 - math.exp(-max(proj, 1e-3))
        if st == "passing_tds":
            return poisson_p_over(max(proj, 0.01), line)
        r = self.art["ratio"].get(st)
        if not r or proj <= 0.05:
            return None
        i = 0 if proj <= r["cuts"][0] else (1 if proj <= r["cuts"][1] else 2)
        a = np.array(r["q"][i]) * proj
        # interpolate share above line from 401 quantiles
        return float((a > line).mean())


def build(nfl_events, game_ctx, now):
    """game_ctx: toa_id -> dict(home_abbr, away_abbr, exp_home_margin, total) from the Board."""
    L = Live()
    out = []
    for e in sorted(nfl_events, key=lambda e: e["commence_time"]):
        ev, latest = offers(e["id"])
        if not latest:
            continue
        H, A = NFL.get(e["home_team"]), NFL.get(e["away_team"])
        ctx = game_ctx.get(e["id"], {})
        em, tot = ctx.get("fair_home_margin"), ctx.get("fair_total")
        rows = []
        props = {}
        for (pl, mk, pt, bk, side), v in latest.items():
            props.setdefault((pl, mk, pt), {}).setdefault(bk, {})[side] = v["price"]
        cache = {}
        for (pl, mk, pt), byb in props.items():
            if mk not in STAT or pl is None:
                continue
            refs = [novig(x["over"], x["under"]) for b, x in byb.items() if "over" in x and "under" in x]
            if mk == "player_anytime_td":
                yes = {b: x.get("yes") for b, x in byb.items() if x.get("yes") is not None}
                if not yes:
                    continue
            pk = pname(pl)
            if pk not in cache:
                cache[pk] = L.player_state(pk, {H, A})
            stt = cache[pk]
            if stt is None:
                continue
            row, team, n_season = stt
            opp = A if team == H else H
            if em is None or tot is None:
                continue
            exp_margin = em if team == H else -em
            implied = (tot + exp_margin) / 2
            va, vc, df = L.team_vol(team, opp, exp_margin, implied)
            pj = project(row, va, vc, df)
            st = STAT[mk]
            proj = pj["tds_mean"] if st == "anytime_td" else pj[st]
            if mk == "player_anytime_td":
                pm = L.p_over(mk, proj, 0.5)
                # one-sided market: no two-way no-vig; market % = median implied prob across books x 0.93 (typical anytime-TD hold, labelled)
                imps = [100 / (p + 100) if p > 0 else -p / (-p + 100) for p in yes.values()]
                q = statistics.median(imps)
                best_b, best_px = max(((b, p) for b, p in yes.items() if b in ("draftkings", "bovada")), key=lambda x: x[1], default=(None, None))
                if best_b is None:
                    continue
                ps = q + W_SHRINK * (pm - q)
                dd = best_px / 100 if best_px > 0 else 100 / -best_px
                rows.append(dict(player=pl, team=team, market=LABEL[mk], line=None, side="Yes", price=best_px, book="DK" if best_b == "draftkings" else "Bovada",
                                 projection=round(proj, 2), model_raw_pct=round(pm, 4), model_pct=round(ps, 4), market_pct=round(q, 4),
                                 market_basis="median implied (with vig; one-sided)", edge=round(ps - q, 4), raw_edge=round(pm - q, 4),
                                 ev_model=round(ps * dd - (1 - ps), 4), n_books=len(yes)))
                continue
            if not refs:
                continue
            q = statistics.median(refs)
            pm = L.p_over(mk, proj, pt)
            if pm is None:
                continue
            pm = min(max(pm, 0.02), 0.98)
            for side, p_, q_ in (("Over", pm, q), ("Under", 1 - pm, 1 - q)):
                cand = [(b, byb[b][side.lower()]) for b in ("draftkings", "bovada") if b in byb and side.lower() in byb[b]]
                if not cand:
                    continue
                b, px = max(cand, key=lambda x: x[1])
                dd = px / 100 if px > 0 else 100 / -px
                ps = q_ + W_SHRINK * (p_ - q_)
                rows.append(dict(player=pl, team=team, market=LABEL[mk], line=pt, side=side, price=px, book="DK" if b == "draftkings" else "Bovada",
                                 projection=round(proj, 1), model_raw_pct=round(p_, 4), model_pct=round(ps, 4), market_pct=round(q_, 4),
                                 market_basis=f"median no-vig of {len(refs)} books", edge=round(ps - q_, 4), raw_edge=round(p_ - q_, 4),
                                 ev_model=round(ps * dd - (1 - ps), 4), n_books=len(refs)))
        rows.sort(key=lambda r: -r["edge"])
        seen, top = set(), []
        for r in rows:
            k = (r["player"], r["market"])
            if k in seen:
                continue
            seen.add(k); top.append(r)
            if len(top) == SHOW_PER_GAME:
                break
        kick = dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")).astimezone(CT)
        out.append(dict(toa_id=e["id"], game=f"{e['away_team']} @ {e['home_team']}", kick_ct=kick.strftime("%a %b %-d %-I:%M %p CT"),
                        kick_iso=kick.isoformat(), markets_pulled=(_load(e["id"]) or {}).get("markets_pulled", []),
                        n_candidates=len(rows), top=top))
    return out
