"""Team offense adjustment (wOBA/wRC+-style sourced index).

Scale opposing λ: pitcher's λ faced vs team offense.
  λ *= offense_index / 100   (wRC+-style; 100 = league average)

If team_offense.csv is empty/missing, loader returns empty map and callers
skip the layer (status note) rather than inventing numbers.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from park import TEAM_ALIASES, canonicalize_team, _norm_team

DEFAULT_OFFENSE_INDEX = 100.0


def load_team_offense(path: Path) -> dict[str, dict[str, Any]]:
    """Map canonical team → offense row. Empty file → {} (skip layer)."""
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
            idx = None
            # Prefer explicit wrc_plus, else offense_index, else derive from RPG later
            for key in ("wrc_plus", "offense_index"):
                raw = (row.get(key) or "").strip()
                if raw:
                    try:
                        idx = float(raw)
                        break
                    except ValueError:
                        pass
            rpg = None
            raw_rpg = (row.get("runs_per_game") or "").strip()
            if raw_rpg:
                try:
                    rpg = float(raw_rpg)
                except ValueError:
                    rpg = None
            out[team] = {
                "team": team,
                "offense_index": idx,
                "runs_per_game": rpg,
                "wrc_plus": (row.get("wrc_plus") or "").strip() or None,
                "source": (row.get("source") or "").strip(),
                "as_of": (row.get("as_of") or "").strip(),
            }

    # If only RPG present, build index vs league mean
    need_idx = [t for t, r in out.items() if r["offense_index"] is None and r["runs_per_game"] is not None]
    if need_idx:
        rpgs = [out[t]["runs_per_game"] for t in out if out[t]["runs_per_game"] is not None]
        if rpgs:
            league = sum(rpgs) / len(rpgs)
            if league > 0:
                for t in need_idx:
                    out[t]["offense_index"] = 100.0 * float(out[t]["runs_per_game"]) / league
    return out


def offense_scale(
    team: str,
    offense: dict[str, dict[str, Any]],
) -> tuple[float, str]:
    """Return (scale, note). Missing team → 1.0 (skip), note explains."""
    if not offense:
        return 1.0, "offense_skipped_no_table"
    row = offense.get(canonicalize_team(team))
    if not row:
        for k, v in offense.items():
            if canonicalize_team(k) == canonicalize_team(team):
                row = v
                break
    if not row or row.get("offense_index") is None:
        return 1.0, "offense_missing_team_neutral_1.0"
    idx = float(row["offense_index"])
    if idx <= 0:
        return 1.0, "offense_bad_index_neutral_1.0"
    return idx / 100.0, "ok"


def apply_offense(lambda_sp: float, scale: float) -> float:
    return lambda_sp * scale
