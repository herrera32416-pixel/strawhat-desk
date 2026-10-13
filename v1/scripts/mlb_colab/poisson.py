"""SP λ from Baseball Savant xERA → Poisson ML probabilities.

Citation (Savant expected-statistics pitcher CSV):
  https://baseballsavant.mlb.com/leaderboard/expected_statistics?type=pitcher&year=2026&position=&team=&min=1&csv=true

λ = xERA × (starter_IP / 9), default IP=5.5.
Actual ERA is NEVER used as λ. Missing SP / missing λ → status N, no model_prob.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

SAVANT_EXPECTED_STATS_URL = (
    "https://baseballsavant.mlb.com/leaderboard/expected_statistics"
    "?type=pitcher&year={year}&position=&team=&min=1&csv=true"
)
SAVANT_CITATION = (
    "https://baseballsavant.mlb.com/leaderboard/expected_statistics"
    "?type=pitcher&year=2026&position=&team=&min=1&csv=true"
)
DEFAULT_STARTER_IP = 5.5
POISSON_CAP = 20


def normalize_pitcher_id(raw: object) -> str:
    text = str(raw or "").replace("\ufeff", "").strip().strip('"').strip("'")
    if text.endswith(".0") and text[:-2].lstrip("-").isdigit():
        text = text[:-2]
    if text.isdigit():
        return str(int(text))
    return text


def _norm_key(key: str) -> str:
    text = (key or "").replace("\ufeff", "").strip()
    while len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    return text.lower()


def _cell(row: dict[str, str], *names: str) -> str | None:
    lowered = {_norm_key(k): v for k, v in row.items()}
    for name in names:
        raw = lowered.get(_norm_key(name))
        if raw is None:
            continue
        text = str(raw).strip().replace("\ufeff", "").strip('"').strip("'")
        if text and text.upper() not in {"NA", "NAN", "NULL", "N"}:
            return text
    return None


def _float(row: dict[str, str], *names: str) -> float | None:
    raw = _cell(row, *names)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def display_name(row: dict[str, str]) -> str:
    combined = _cell(row, "last_name, first_name", "last_name,first_name")
    if combined and "," in combined:
        last, first = [part.strip() for part in combined.split(",", 1)]
        return f"{first} {last}".strip() or combined
    name = _cell(row, "player_name", "name", "fullName") or "unknown"
    if "," in name:
        last_part, first_part = [part.strip() for part in name.split(",", 1)]
        flipped = f"{first_part} {last_part}".strip()
        if flipped:
            return flipped
    return name


def xera_to_lambda(xera: float, *, starter_ip: float = DEFAULT_STARTER_IP) -> float:
    """Savant xERA → expected earned runs in a starter outing. Not actual ERA."""
    if starter_ip <= 0:
        raise ValueError("starter_ip must be positive")
    return xera * starter_ip / 9.0


def resolve_sp_lambda(
    row: dict[str, str],
    *,
    starter_ip: float = DEFAULT_STARTER_IP,
) -> tuple[float | None, str, str]:
    """Return (lambda_runs, status, source). ERA never converted."""
    for field_name in ("expected_runs", "x_runs", "xruns", "est_runs", "lambda_runs"):
        value = _float(row, field_name)
        if value is not None and value >= 0:
            # Prefer precomputed lambda_runs only when lambda_source says xera proxy
            if field_name == "lambda_runs":
                src = (_cell(row, "lambda_source") or "lambda_runs").strip()
                status = (_cell(row, "lambda_status") or "ok").strip()
                if status == "N":
                    return None, "N", ""
                return round(value, 4), "ok", src or "lambda_runs"
            return round(value, 4), "ok", field_name
    xera = _float(row, "xera", "x_era", "expected_era")
    if xera is not None and xera >= 0:
        return (
            round(xera_to_lambda(xera, starter_ip=starter_ip), 4),
            "ok",
            "xera_runs_per_start",
        )
    return None, "N", ""


def load_savant_lambdas(
    path: Path,
    *,
    starter_ip: float = DEFAULT_STARTER_IP,
) -> dict[str, dict[str, Any]]:
    """Map pitcher_id → {name, lambda_runs, status, source, xera}."""
    out: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            pid = normalize_pitcher_id(_cell(raw, "player_id", "mlbam_id", "pitcher_id") or "")
            if not pid:
                continue
            lam, status, source = resolve_sp_lambda(raw, starter_ip=starter_ip)
            out[pid] = {
                "pitcher_id": pid,
                "pitcher_name": display_name(raw),
                "lambda_runs": lam,
                "lambda_status": status,
                "lambda_source": source,
                "xera": _float(raw, "xera", "x_era", "expected_era"),
            }
    return out


def poisson_pmf(lam: float, cap: int = POISSON_CAP) -> list[float]:
    if lam < 0:
        raise ValueError("lambda must be >= 0")
    probs = [0.0] * (cap + 1)
    p = math.exp(-lam)
    probs[0] = p
    for k in range(1, cap + 1):
        p *= lam / k
        probs[k] = p
    return probs


def home_win_prob(
    *,
    lambda_home_scored: float,
    lambda_away_scored: float,
    cap: int = POISSON_CAP,
) -> float:
    """P(home wins) = P(X>Y) + 0.5 P(tie); X~Pois(away_SP λ), Y~Pois(home_SP λ)."""
    home_runs = poisson_pmf(lambda_home_scored, cap)  # X: home scored vs away SP
    away_runs = poisson_pmf(lambda_away_scored, cap)  # Y: away scored vs home SP
    p_home = 0.0
    p_tie = 0.0
    for x, px in enumerate(home_runs):
        for y, py in enumerate(away_runs):
            mass = px * py
            if x > y:
                p_home += mass
            elif x == y:
                p_tie += mass
    return p_home + 0.5 * p_tie
