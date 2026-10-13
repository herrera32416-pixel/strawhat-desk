"""Team bullpen (relief) rate layer — sourced only; never invent rates.

Unit: team-level reliever RA9 (runs allowed per 9 IP) from MLB Stats API
situation split sitCodes=rp (description: Reliever).

Preferred source (v1.1):
  https://statsapi.mlb.com/api/v1/teams/{teamId}/stats
    ?season=2026&group=pitching&stats=statSplits&sitCodes=rp
  Columns used: runsScoredPer9 → bullpen_ra9; also era, inningsPitched, runs.

Alternate (documented, not required for v1.1):
  FanGraphs team relief leaders (stats=rel&team=0,ts) — ERA / xERA / FIP / xFIP
  https://www.fangraphs.com/leaders/major-league?stats=rel&team=0,ts&season=2026&season1=2026&type=8

Formula (full-game λ before park/offense):
  λ_full = λ_sp + (bullpen_ra9 / 9) * relief_ip
  where λ_sp = xERA_sp * starter_ip / 9  (already from poisson.py)
        relief_ip = game_ip - starter_ip   (default 9.0 - 5.5 = 3.5)

Hard rules:
  - No silent defaults that invent rates.
  - Empty / missing table → loader returns {}.
  - require_bullpen=True (or expand_sp_lambda with require=True) FAILS LOUDLY
    if the table is empty or the team has no rate.
  - Soft path (use_bullpen=False in model_v1) leaves SP-only v1 unchanged.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from park import canonicalize_team
from poisson import DEFAULT_STARTER_IP

DEFAULT_GAME_IP = 9.0
BULLPEN_SOURCE_CITATION = (
    "https://statsapi.mlb.com/api/v1/teams/{teamId}/stats"
    "?season=2026&group=pitching&stats=statSplits&sitCodes=rp"
)
FANGRAPHS_RELIEF_CITATION = (
    "https://www.fangraphs.com/leaders/major-league"
    "?stats=rel&team=0,ts&season=2026&season1=2026&type=8"
)


def _float(raw: object) -> float | None:
    text = str(raw or "").strip()
    if not text or text.upper() in {"NA", "NAN", "NULL", "N"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def resolve_bullpen_rate(row: dict[str, Any]) -> tuple[float | None, str]:
    """Pick sourced rate. Prefer bullpen_ra9 → rate_value → xera → fip → xfip → era.

    Returns (rate_per_9, metric_name) or (None, '') when no numeric rate present.
    """
    metric_hint = str(row.get("rate_metric") or "").strip().lower()
    preferred_order = [
        "bullpen_ra9",
        "rate_value",
        "xera",
        "fip",
        "xfip",
        "era",
    ]
    if metric_hint and metric_hint in preferred_order:
        preferred_order = [metric_hint] + [m for m in preferred_order if m != metric_hint]
    for key in preferred_order:
        val = _float(row.get(key))
        if val is not None and val >= 0:
            return val, key
    return None, ""


def load_team_bullpen(path: Path) -> dict[str, dict[str, Any]]:
    """Map canonical team → bullpen row. Missing/empty file → {} (no invent)."""
    out: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return out
        for row in reader:
            team = canonicalize_team(row.get("team") or "")
            if not team:
                continue
            rate, metric = resolve_bullpen_rate(row)
            out[team] = {
                "team": team,
                "team_id": (row.get("team_id") or "").strip(),
                "season": (row.get("season") or "").strip(),
                "relief_ip_season": _float(row.get("relief_ip")),
                "runs_allowed": _float(row.get("runs_allowed")),
                "bullpen_ra9": _float(row.get("bullpen_ra9")),
                "era": _float(row.get("era")),
                "xera": _float(row.get("xera")),
                "fip": _float(row.get("fip")),
                "xfip": _float(row.get("xfip")),
                "rate": rate,
                "rate_metric": metric,
                "source": (row.get("source") or "").strip(),
                "source_url": (row.get("source_url") or "").strip(),
                "as_of": (row.get("as_of") or "").strip(),
                "split_code": (row.get("split_code") or "").strip(),
            }
    return out


def bullpen_rate_for_team(
    team: str,
    bullpen: dict[str, dict[str, Any]],
    *,
    require: bool = False,
) -> tuple[float | None, str, str]:
    """Return (rate_per_9, metric, note).

    require=False → missing → (None, '', 'bullpen_missing_...') without inventing.
    require=True  → missing empty table or team → raise RuntimeError (fail loud).
    """
    if not bullpen:
        if require:
            raise RuntimeError(
                "bullpen table empty/missing — refuse to invent rates. "
                f"Populate data/team_bullpen.csv from {BULLPEN_SOURCE_CITATION}"
            )
        return None, "", "bullpen_skipped_no_table"
    canon = canonicalize_team(team)
    row = bullpen.get(canon)
    if not row:
        for k, v in bullpen.items():
            if canonicalize_team(k) == canon:
                row = v
                break
    if not row or row.get("rate") is None:
        if require:
            raise RuntimeError(
                f"bullpen rate missing for team={team!r} (canonical={canon!r}) — "
                "no silent default; fill sourced row in data/team_bullpen.csv"
            )
        return None, "", "bullpen_missing_team"
    return float(row["rate"]), str(row.get("rate_metric") or "rate"), "ok"


def expand_sp_lambda(
    lambda_sp: float,
    team: str,
    bullpen: dict[str, dict[str, Any]],
    *,
    starter_ip: float = DEFAULT_STARTER_IP,
    game_ip: float = DEFAULT_GAME_IP,
    require: bool = True,
) -> tuple[float, dict[str, Any]]:
    """Expand SP-outing λ to full-game λ using team bullpen RA9 for remainder IP.

    λ_full = λ_sp + (bullpen_rate / 9) * (game_ip - starter_ip)

    FAILS LOUDLY when require=True and rate missing (default for active bullpen path).
    """
    if starter_ip <= 0 or game_ip <= 0:
        raise ValueError("starter_ip and game_ip must be positive")
    if game_ip < starter_ip:
        raise ValueError("game_ip must be >= starter_ip")
    relief_ip = game_ip - starter_ip
    rate, metric, note = bullpen_rate_for_team(team, bullpen, require=require)
    if rate is None:
        # Soft skip only when require=False: return SP λ unchanged with note.
        return float(lambda_sp), {
            "bullpen_applied": False,
            "bullpen_rate": None,
            "bullpen_metric": "",
            "bullpen_note": note,
            "starter_ip": starter_ip,
            "relief_ip": relief_ip,
            "lambda_sp": float(lambda_sp),
            "lambda_bullpen": None,
            "lambda_full": float(lambda_sp),
        }
    lam_bp = rate * relief_ip / 9.0
    lam_full = float(lambda_sp) + lam_bp
    return lam_full, {
        "bullpen_applied": True,
        "bullpen_rate": round(rate, 6),
        "bullpen_metric": metric,
        "bullpen_note": note,
        "starter_ip": starter_ip,
        "relief_ip": relief_ip,
        "lambda_sp": float(lambda_sp),
        "lambda_bullpen": round(lam_bp, 4),
        "lambda_full": round(lam_full, 4),
    }


def assert_bullpen_ready(bullpen: dict[str, dict[str, Any]], teams: list[str]) -> None:
    """Fail loud if any required team lacks a sourced rate."""
    if not bullpen:
        raise RuntimeError(
            "bullpen table empty — cannot enable use_bullpen without sourced rates"
        )
    missing = []
    for t in teams:
        rate, _, note = bullpen_rate_for_team(t, bullpen, require=False)
        if rate is None:
            missing.append(f"{t} ({note})")
    if missing:
        raise RuntimeError("bullpen rates missing for: " + ", ".join(missing))
