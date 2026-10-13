#!/usr/bin/env python3
"""MLB model % for the DESK board — PAPER / INFO ONLY (A/B/C grades stay market-only).

Colab MLB model v1.1 (vendored from colab-sorts/mlb into scripts/mlb_colab/, unchanged):
  starter lambda = Savant xERA x 5.5/9, + team bullpen RA9 x 3.5/9, x park factor (BBRef BPF/100),
  x opponent offense (R/G vs league)  ->  independent Poisson runs (home, away), 9 innings.
From that one score grid:
  ML      P(home) = P(H>A) + 0.5 P(tie)            (the Colab model's own tie rule)
  Run line home -1.5 = P(H-A >= 2), away +1.5 = 1 - that; extra-inning games are 1-run games,
          so a 9-inning tie can never cover -1.5 (home +1.5 = 1 - P(A-H >= 2)).
  Total   9-inning runs + 1 for a tie (extras end on a 1-run edge); push-free %:
          P(over) / (1 - P(push)) so it is comparable with the market no-vig %.
Inputs refreshed each run from free sources (Savant CSV, MLB Stats API); a failed refresh keeps the
last committed snapshot and records its as_of. A missing probable starter / pitcher row -> model blank.
Never invents numbers.
"""
from __future__ import annotations

import csv
import io
import json
import math
import sys
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLAB = HERE / "mlb_colab"
DATA = COLAB / "data"
sys.path.insert(0, str(COLAB))

import model_v1  # noqa: E402
from park import canonicalize_team  # noqa: E402

MODEL_NAME = ("Colab MLB v1.1 (Savant xERA starter + bullpen RA9 + park + opp offense -> Poisson) "
              "— PAPER / INFO ONLY, not used for grades")
SAVANT = ("https://baseballsavant.mlb.com/leaderboard/expected_statistics?type=pitcher&year={y}"
          "&position=&team=&min=1&csv=true")
SCHED = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={d}&hydrate=probablePitcher"
CAP = 25


def _get(url: str, timeout: int = 30, tries: int = 3) -> bytes:
    import time
    req = urllib.request.Request(url, headers={"User-Agent": "strawhat-desk/1.0 (paper research)"})
    for k in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:  # noqa: BLE001
            if k == tries - 1:
                raise
            time.sleep(2 * (k + 1))


def _ip(s) -> float:
    whole, _, frac = str(s).partition(".")
    return int(whole or 0) + int(frac or 0) / 3


def refresh(season: int, notes: list[str]) -> None:
    """Best-effort refresh of the three input CSVs. On any failure the committed snapshot stays."""
    try:
        raw = _get(SAVANT.format(y=season)).decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(raw)))
        if len(rows) < 100 or "xera" not in rows[0]:
            raise ValueError(f"unexpected Savant CSV ({len(rows)} rows)")
        with (DATA / "savant_pitcher_expected.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        notes.append(f"Savant xERA refreshed ({len(rows)} pitchers)")
    except Exception as e:  # noqa: BLE001
        notes.append(f"Savant refresh failed ({type(e).__name__}); kept snapshot")
    today = date.today().isoformat()
    try:
        js = json.loads(_get(f"https://statsapi.mlb.com/api/v1/teams/stats?season={season}&group=hitting&stats=season&sportId=1"))
        out = []
        for sp in js["stats"][0]["splits"]:
            g, r = sp["stat"]["gamesPlayed"], sp["stat"]["runs"]
            out.append({"team": sp["team"]["name"], "runs_per_game": round(r / g, 6), "offense_index": "", "wrc_plus": "",
                        "source": "mlb_stats_api_team_hitting", "as_of": today, "season": season, "games": g, "runs": r})
        if len(out) != 30:
            raise ValueError(f"{len(out)} teams")
        with (DATA / "team_offense.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
            w.writeheader()
            w.writerows(out)
        notes.append("team offense refreshed")
        teams = {sp["team"]["name"]: sp["team"]["id"] for sp in js["stats"][0]["splits"]}
        bp = []
        for name, tid in sorted(teams.items()):
            url = (f"https://statsapi.mlb.com/api/v1/teams/{tid}/stats?season={season}&group=pitching"
                   f"&stats=statSplits&sitCodes=rp")
            st = json.loads(_get(url))["stats"][0]["splits"][0]["stat"]
            ip = _ip(st["inningsPitched"])
            ra9 = round(9 * st["runs"] / ip, 2)
            bp.append({"team": name, "team_id": tid, "season": season, "games": st["gamesPlayed"], "relief_ip": st["inningsPitched"],
                       "runs_allowed": st["runs"], "earned_runs": st["earnedRuns"], "bullpen_ra9": ra9, "era": st["era"],
                       "rate_metric": "bullpen_ra9", "rate_value": ra9, "source": "mlb_stats_api_team_pitching_sitCodes_rp",
                       "source_url": url, "as_of": today, "split_code": "rp"})
        with (DATA / "team_bullpen.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(bp[0].keys()))
            w.writeheader()
            w.writerows(bp)
        notes.append("bullpen RA9 refreshed")
    except Exception as e:  # noqa: BLE001
        notes.append(f"MLB Stats API refresh failed ({type(e).__name__}); kept snapshot")


def probables(days: list[str]) -> list[dict]:
    out = []
    for d in days:
        js = json.loads(_get(SCHED.format(d=d)))
        for dt in js.get("dates") or []:
            for g in dt.get("games") or []:
                t = g["teams"]
                out.append({"game_pk": g["gamePk"], "game_date": g["gameDate"],
                            "home": t["home"]["team"]["name"], "away": t["away"]["team"]["name"],
                            "home_pitcher": (t["home"].get("probablePitcher") or {}).get("fullName", ""),
                            "away_pitcher": (t["away"].get("probablePitcher") or {}).get("fullName", ""),
                            "home_pitcher_id": str((t["home"].get("probablePitcher") or {}).get("id", "")),
                            "away_pitcher_id": str((t["away"].get("probablePitcher") or {}).get("id", ""))})
    return out


def _pmf(lam: float) -> list[float]:
    p = [math.exp(-lam)]
    for k in range(1, CAP):
        p.append(p[-1] * lam / k)
    return p


def probs(lh: float, la: float, home_line: float | None = None, total: float | None = None) -> dict:
    """lh = expected home runs, la = expected away runs (9 innings)."""
    ph, pa = _pmf(lh), _pmf(la)
    win = tie = 0.0
    margin: dict[int, float] = {}
    tot: dict[int, float] = {}
    for i, x in enumerate(ph):
        for j, y in enumerate(pa):
            m = x * y
            if i > j:
                win += m
            elif i == j:
                tie += m
            margin[i - j] = margin.get(i - j, 0.0) + m
            t = i + j + (1 if i == j else 0)
            tot[t] = tot.get(t, 0.0) + m
    out = {"ml_home": win + 0.5 * tie, "tie9": tie}
    if home_line is not None:
        if abs(abs(home_line) - 1.5) < 1e-9:
            if home_line < 0:   # home -1.5
                out["pl_home"] = sum(v for k, v in margin.items() if k >= 2)
            else:               # home +1.5 loses only when away wins by 2+
                out["pl_home"] = 1 - sum(v for k, v in margin.items() if k <= -2)
        # other run lines: blank (not modelled)
    if total is not None:
        over = sum(v for k, v in tot.items() if k > total)
        push = sum(v for k, v in tot.items() if k == total)
        if push < 1:
            out["over"] = over / (1 - push)
    return out


class MLBLive:
    def __init__(self, days: list[str], season: int, fetch: bool = True):
        self.notes: list[str] = []
        self.model_name = MODEL_NAME
        if fetch:
            refresh(season, self.notes)
        self.ctx = model_v1.load_context(load_bullpen=True)
        self.games = probables(days) if fetch else []
        self.as_of = {n: _asof(DATA / f) for n, f in (("offense", "team_offense.csv"), ("bullpen", "team_bullpen.csv"))}

    def find(self, home: str, away: str, kick_utc: str):
        h, a = canonicalize_team(home), canonicalize_team(away)
        c = [g for g in self.games if canonicalize_team(g["home"]) == h and canonicalize_team(g["away"]) == a]
        if not c:
            return None
        return min(c, key=lambda g: abs(_ts(g["game_date"]) - _ts(kick_utc)))

    def predict(self, home: str, away: str, kick_utc: str, home_line=None, total=None) -> dict:
        g = self.find(home, away, kick_utc)
        if not g:
            return {"status": "N", "reason": "game not on MLB schedule"}
        if not g["home_pitcher_id"] or not g["away_pitcher_id"]:
            return {"status": "N", "reason": "probable starter not announced", "game_pk": g["game_pk"]}
        sv, pk, of, bp = self.ctx
        r = model_v1.score_game(g["home"], g["away"], g["home_pitcher"], g["away_pitcher"], g["home_pitcher_id"],
                                g["away_pitcher_id"], savant=sv, parks=pk, offense=of, bullpen=bp,
                                use_park=True, use_offense=True, use_bullpen=True)
        if r.get("lambda_status") != "ok":
            return {"status": "N", "reason": r.get("skip_reason") or "model N", "game_pk": g["game_pk"]}
        # model_v1 naming: lambda_away = runs the HOME team scores; lambda_home = runs the AWAY team scores
        lh, la = float(r["lambda_away"]), float(r["lambda_home"])
        p = probs(lh, la, home_line, total)
        p.update(status="ok", game_pk=g["game_pk"], runs_home=round(lh, 2), runs_away=round(la, 2),
                 home_pitcher=g["home_pitcher"], away_pitcher=g["away_pitcher"], park=r.get("park_factor"),
                 colab_ml_home=r["model_prob_home"])
        return p


def _ts(iso: str) -> float:
    from datetime import datetime
    return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()


def _asof(path: Path) -> str:
    try:
        with path.open() as f:
            return next(csv.DictReader(f)).get("as_of", "")
    except Exception:  # noqa: BLE001
        return ""
