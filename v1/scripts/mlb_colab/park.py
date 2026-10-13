"""Park factor table + apply to SP λ.

v1: both team λs × home-park runs_factor (neutral 1.0).
Sourced from Baseball-Reference multi-year BPF / 100.
Coors Field and Wrigley Field must be present (Main lesson).
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

PARK_SOURCE_URL = "https://www.baseball-reference.com/leagues/majors/2025-misc.shtml"
DEFAULT_PARK_FACTOR = 1.0
KNOWN_PARK_NAMES = {
    "Colorado Rockies": "Coors Field",
    "Chicago Cubs": "Wrigley Field",
}


def _norm_team(name: str) -> str:
    return " ".join((name or "").strip().lower().replace(".", "").split())


TEAM_ALIASES: dict[str, str] = {
    "arizona diamondbacks": "Arizona Diamondbacks",
    "diamondbacks": "Arizona Diamondbacks",
    "athletics": "Athletics",
    "oakland athletics": "Athletics",
    "a's": "Athletics",
    "atlanta braves": "Atlanta Braves",
    "braves": "Atlanta Braves",
    "baltimore orioles": "Baltimore Orioles",
    "orioles": "Baltimore Orioles",
    "boston red sox": "Boston Red Sox",
    "red sox": "Boston Red Sox",
    "chicago cubs": "Chicago Cubs",
    "cubs": "Chicago Cubs",
    "chicago white sox": "Chicago White Sox",
    "white sox": "Chicago White Sox",
    "cincinnati reds": "Cincinnati Reds",
    "reds": "Cincinnati Reds",
    "cleveland guardians": "Cleveland Guardians",
    "guardians": "Cleveland Guardians",
    "colorado rockies": "Colorado Rockies",
    "rockies": "Colorado Rockies",
    "detroit tigers": "Detroit Tigers",
    "tigers": "Detroit Tigers",
    "houston astros": "Houston Astros",
    "astros": "Houston Astros",
    "kansas city royals": "Kansas City Royals",
    "royals": "Kansas City Royals",
    "los angeles angels": "Los Angeles Angels",
    "angels": "Los Angeles Angels",
    "los angeles dodgers": "Los Angeles Dodgers",
    "dodgers": "Los Angeles Dodgers",
    "miami marlins": "Miami Marlins",
    "marlins": "Miami Marlins",
    "milwaukee brewers": "Milwaukee Brewers",
    "brewers": "Milwaukee Brewers",
    "minnesota twins": "Minnesota Twins",
    "twins": "Minnesota Twins",
    "new york mets": "New York Mets",
    "mets": "New York Mets",
    "new york yankees": "New York Yankees",
    "yankees": "New York Yankees",
    "philadelphia phillies": "Philadelphia Phillies",
    "phillies": "Philadelphia Phillies",
    "pittsburgh pirates": "Pittsburgh Pirates",
    "pirates": "Pittsburgh Pirates",
    "san diego padres": "San Diego Padres",
    "padres": "San Diego Padres",
    "san francisco giants": "San Francisco Giants",
    "giants": "San Francisco Giants",
    "seattle mariners": "Seattle Mariners",
    "mariners": "Seattle Mariners",
    "st louis cardinals": "St. Louis Cardinals",
    "st. louis cardinals": "St. Louis Cardinals",
    "cardinals": "St. Louis Cardinals",
    "tampa bay rays": "Tampa Bay Rays",
    "rays": "Tampa Bay Rays",
    "texas rangers": "Texas Rangers",
    "rangers": "Texas Rangers",
    "toronto blue jays": "Toronto Blue Jays",
    "blue jays": "Toronto Blue Jays",
    "washington nationals": "Washington Nationals",
    "nationals": "Washington Nationals",
}


def canonicalize_team(name: str) -> str:
    key = _norm_team(name)
    if key in TEAM_ALIASES:
        return TEAM_ALIASES[key]
    # exact title match pass-through
    return name.strip()


def load_park_factors(path: Path) -> dict[str, dict[str, Any]]:
    """Map canonical team → {park_name, runs_factor, source, as_of}."""
    out: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            team = canonicalize_team(row.get("team") or "")
            if not team:
                continue
            rf = None
            raw_rf = (row.get("runs_factor") or "").strip()
            if raw_rf:
                try:
                    rf = float(raw_rf)
                except ValueError:
                    rf = None
            if rf is None:
                raw_bpf = (row.get("bpf") or "").strip()
                if raw_bpf:
                    try:
                        rf = float(raw_bpf) / 100.0
                    except ValueError:
                        rf = None
            if rf is None:
                rf = DEFAULT_PARK_FACTOR
            if not (row.get("park_name") or "").strip():
                # ops-style file has no park_name; leave blank (mlb table has names)
                pass
            out[team] = {
                "team": team,
                "park_name": (row.get("park_name") or "").strip()
                or KNOWN_PARK_NAMES.get(team, ""),
                "runs_factor": rf,
                "source": (row.get("source") or "").strip(),
                "as_of": (row.get("as_of") or "").strip(),
            }
    return out


def park_factor_for_home(
    home_team: str,
    parks: dict[str, dict[str, Any]],
) -> tuple[float, str, str]:
    """Return (runs_factor, park_name, note). Missing → 1.0 neutral."""
    team = canonicalize_team(home_team)
    row = parks.get(team)
    if not row:
        # try alias key scan
        for k, v in parks.items():
            if canonicalize_team(k) == team:
                row = v
                break
    if not row:
        return DEFAULT_PARK_FACTOR, "", "park_missing_neutral_1.0"
    return float(row["runs_factor"]), str(row.get("park_name") or ""), "ok"


def apply_park(lambda_sp: float, park_factor: float) -> float:
    return lambda_sp * park_factor


def assert_coors_wrigley(parks: dict[str, dict[str, Any]]) -> None:
    """Main lesson: Coors and Wrigley must be in the table."""
    col = parks.get("Colorado Rockies") or parks.get(canonicalize_team("Colorado Rockies"))
    chc = parks.get("Chicago Cubs") or parks.get(canonicalize_team("Chicago Cubs"))
    if not col or "coors" not in (col.get("park_name") or "").lower():
        raise RuntimeError("park table missing Coors Field (Colorado Rockies)")
    if not chc or "wrigley" not in (chc.get("park_name") or "").lower():
        raise RuntimeError("park table missing Wrigley Field (Chicago Cubs)")
