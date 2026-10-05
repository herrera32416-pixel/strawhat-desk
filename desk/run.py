"""Daily orchestrator (GitHub Actions ~9:00am CT). Roles run in order:
LINES -> BOARD -> TEASERS -> PROPS (budget after the recheck reserve) -> GRADER -> MATCHUP (info) -> PUBLISHER. Deterministic; no messages, no bets."""
import datetime as dt, json, os, sys, traceback
from zoneinfo import ZoneInfo
from . import toa, lines, board, teasers, grader, espn
from .names import norm

CT = ZoneInfo("America/Chicago")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DATA = os.path.join(ROOT, "docs", "data")


def main():
    now = dt.datetime.now(dt.timezone.utc)
    nct = now.astimezone(CT)
    stamp = nct.strftime("%Y%m%d_%H%M")
    season = nct.year if nct.month >= 3 else nct.year - 1
    notes = []
    start_remaining = None
    # LINES
    pulled = lines.run(stamp) if os.environ.get("THE_ODDS_API_KEY") else {"nfl": "no key", "cfb": "no key"}
    notes.append(f"LINES: {pulled}")
    odds, asof = {}, {}
    for sp in ("nfl", "cfb"):
        j, p = lines.latest(sp)
        if j:
            odds[sp] = j["data"]; asof[sp] = j["pulled_ct"]
    # FBS filter from ESPN FBS scoreboard (today + next 2 days)
    fbs = set()
    for k in range(3):
        d = (nct + dt.timedelta(days=k)).strftime("%Y%m%d")
        for g in espn.games(espn.scoreboard("cfb", d)):
            fbs |= {norm(g["home"]), norm(g["away"])}
    B = board.build(odds, fbs or None, season, now)
    notes.append(f"BOARD: {len(B)} games ({sum(g['sport']=='nfl' for g in B)} NFL, {sum(g['sport']=='cfb' for g in B)} FBS), "
                 f"{sum(m.get('decision')=='PICK' for g in B for m in g['markets'].values())} picks")
    # TEASERS
    legs = teasers.candidate_legs(odds, season, now)
    TS = teasers.build_days(legs, now)
    notes.append("TEASERS: " + "; ".join(f"{S['label']} {S['date']}: {len(S['tickets'])} tickets from {S['n_candidate_legs']} legs, "
                                          f"{sum(t['decision']=='PLAY' for t in S['tickets'])} PLAY" for S in TS.values()))
    # PROPS
    P, pnotes = [], []
    try:
        from . import props_run
        nfl_events = lines.events("nfl") if os.environ.get("THE_ODDS_API_KEY") else []
        today = nct.strftime("%Y-%m-%d")
        from . import recheck
        # keep credits for the kickoff-driven rechecks: 4 per distinct kick window of TODAY's official items (max 3 = 12)
        d0 = nct.date()
        kd = lambda iso: dt.datetime.fromisoformat(iso).astimezone(CT).date() == d0
        kicks = [dt.datetime.fromisoformat(g["kick_iso"]) for g in B if kd(g["kick_iso"]) and any(m.get("decision") == "PICK" for m in g["markets"].values())]
        kicks += [dt.datetime.fromisoformat(i["kick_iso"]) for i in grader.load()["items"] if i["tab"] == "board" and i["status"] == "open" and kd(i["kick_iso"])]
        kicks += [min(dt.datetime.fromisoformat(l["kick_iso"]) for l in t["legs"]) for S in TS.values() for t in S["tickets"]
                  if t["decision"] == "PLAY" and S["date"] == d0.isoformat()]
        reserve = recheck.reserve_credits(kicks)
        left = toa.DAILY_CAP - toa.spent(today, "daily") - reserve
        pnotes.append(f"props budget {max(left, 0)} (reserve {reserve} for pre-kick rechecks)")
        if nfl_events and left > 0:
            pnotes = pnotes + props_run.plan_and_pull(nfl_events, now, left)
        ctx = {g["toa_id"]: g for g in B if g["sport"] == "nfl"}
        win = [e for e in nfl_events if 0 < (dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) - now).total_seconds() / 3600 <= props_run.WINDOW_H]
        P = props_run.build(win, ctx, now)
    except Exception as ex:
        pnotes.append("PROPS error: " + repr(ex)); traceback.print_exc()
    notes.append(f"PROPS: {pnotes}")
    # GRADER
    L = grader.load()
    v = grader.void_rule_changes(L, now)
    if v:
        notes.append(f"GRADER: {v} open ML pick(s) VOID (ML reference-only rule)")
    a = grader.add_board(L, B, nct); b = grader.add_props(L, P, nct); c = grader.add_teasers(L, TS, now)
    gcount = grader.grade(L, now)
    grader.save(L)
    notes.append(f"GRADER: +{a} board, +{b} props, +{c} teasers logged; {gcount} settled")
    # MATCHUP (NFL, INFO ONLY unless data/matchup/model.json says otherwise; free nflverse pbp, 0 Odds API credits)
    try:
        from . import matchup, matchup_data
        nfl_season = now.year if now.month >= 3 else now.year - 1
        try:
            matchup_data.build([nfl_season])
        except Exception as ex:
            notes.append(f"MATCHUP: pbp refresh failed ({ex!r}); using committed team-game data")
        MU = matchup.live(now)
        notes.append(f"MATCHUP: {len(MU['games'])} NFL games, {MU['status']}, data through {MU['data_through']}")
    except Exception as ex:
        notes.append("MATCHUP error: " + repr(ex)); traceback.print_exc()
    # credits
    rows = toa.log_rows()
    today = nct.strftime("%Y-%m-%d")
    credits = dict(spent_today=toa.spent(today, "daily"), daily_cap=toa.DAILY_CAP,
                   remaining=next((r["remaining"] for r in reversed(rows) if r.get("remaining")), None),
                   spent_build=toa.spent(kind="build"), spent_daily_total=toa.spent(kind="daily"))
    # PUBLISH
    os.makedirs(SITE_DATA, exist_ok=True)
    meta = dict(generated_ct=nct.strftime("%a %b %-d %Y %-I:%M %p CT"), odds_asof=asof, credits=credits, notes=notes,
                headline=grader.headline(L), season=season)
    json.dump(dict(meta=meta, games=B), open(os.path.join(SITE_DATA, "board.json"), "w"))
    json.dump(dict(meta=meta, games=P), open(os.path.join(SITE_DATA, "props.json"), "w"))
    try:
        bt = json.load(open(os.path.join(ROOT, "data", "teaser_backtest.json")))
    except Exception:
        bt = {}
    for S in TS.values():
        S["backtest"] = bt.get(S["sport"])
    json.dump(dict(meta=meta, sets=TS, backtest_note=bt.get("_note")), open(os.path.join(SITE_DATA, "teasers.json"), "w"))
    json.dump(dict(meta=meta, ledger=L), open(os.path.join(SITE_DATA, "ledger.json"), "w"))
    json.dump(meta, open(os.path.join(SITE_DATA, "meta.json"), "w"))
    json.dump({}, open(os.path.join(SITE_DATA, "recheck.json"), "w"))  # the 9am run starts a fresh day; recheck fills this
    print("\n".join(notes)); print(credits)


if __name__ == "__main__":
    main()
