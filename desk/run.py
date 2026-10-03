"""Daily orchestrator (GitHub Actions ~9:00am CT). Roles run in order:
LINES -> BOARD -> PROPS -> TEASERS -> GRADER -> PUBLISHER. Deterministic; no messages, no bets."""
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
    # PROPS
    P, pnotes = [], []
    try:
        from . import props_run
        nfl_events = lines.events("nfl") if os.environ.get("THE_ODDS_API_KEY") else []
        today = nct.strftime("%Y-%m-%d")
        left = toa.DAILY_CAP - toa.spent(today, "daily")
        if nfl_events and left > 0:
            pnotes = props_run.plan_and_pull(nfl_events, now, left)
        ctx = {g["toa_id"]: g for g in B if g["sport"] == "nfl"}
        win = [e for e in nfl_events if 0 < (dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) - now).total_seconds() / 3600 <= props_run.WINDOW_H]
        P = props_run.build(win, ctx, now)
    except Exception as ex:
        pnotes.append("PROPS error: " + repr(ex)); traceback.print_exc()
    notes.append(f"PROPS: {pnotes}")
    # TEASERS
    legs = teasers.candidate_legs(odds, season, now)
    TZ, tmeta = teasers.build(legs)
    notes.append(f"TEASERS: {len(TZ)} tickets from {len(legs)} candidate legs")
    # GRADER
    L = grader.load()
    a = grader.add_board(L, B, nct); b = grader.add_props(L, P, nct); c = grader.add_teasers(L, TZ, nct)
    gcount = grader.grade(L, now)
    grader.save(L)
    notes.append(f"GRADER: +{a} board, +{b} props, +{c} teasers logged; {gcount} settled")
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
    json.dump(dict(meta=meta, tickets=TZ, n_candidate_legs=len(legs),
                   candidate_legs=sorted(legs, key=lambda l: -l["p_cond"])[:40]), open(os.path.join(SITE_DATA, "teasers.json"), "w"))
    json.dump(dict(meta=meta, ledger=L), open(os.path.join(SITE_DATA, "ledger.json"), "w"))
    json.dump(meta, open(os.path.join(SITE_DATA, "meta.json"), "w"))
    print("\n".join(notes)); print(credits)


if __name__ == "__main__":
    main()
