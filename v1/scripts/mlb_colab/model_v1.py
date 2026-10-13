"""MLB model v1 / v1.1: λ = SP(+bullpen) → park → opp_offense → Poisson ML. Colab-owned."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from poisson import SAVANT_CITATION, home_win_prob, load_savant_lambdas, normalize_pitcher_id
from park import apply_park, assert_coors_wrigley, load_park_factors, park_factor_for_home
from offense import apply_offense, load_team_offense, offense_scale
from bullpen import (
    BULLPEN_SOURCE_CITATION,
    expand_sp_lambda,
    load_team_bullpen,
)

DATA = Path(__file__).resolve().parent / "data"
MODEL_VERSION_V1 = "colab_mlb_v1_poisson_park_offense"
MODEL_VERSION_V11 = "colab_mlb_v1_1_poisson_park_offense_bullpen"
MODEL_VERSION = MODEL_VERSION_V1  # default export label when bullpen off
SAVANT_URL = SAVANT_CITATION
BULLPEN_URL = BULLPEN_SOURCE_CITATION


def score_game(
    home: str,
    away: str,
    home_pitcher: str,
    away_pitcher: str,
    home_pitcher_id: str = "",
    away_pitcher_id: str = "",
    *,
    savant: dict[str, dict[str, Any]] | None = None,
    parks: dict[str, dict[str, Any]] | None = None,
    offense: dict[str, dict[str, Any]] | None = None,
    bullpen: dict[str, dict[str, Any]] | None = None,
    use_park: bool = True,
    use_offense: bool = True,
    use_bullpen: bool = False,
) -> dict[str, Any]:
    """Score one game.

    use_bullpen=False (default): v1 SP-only λ path — unchanged if bullpen CSV missing.
    use_bullpen=True: expand each SP λ with that team's sourced bullpen RA9 for
    remainder IP; FAILS LOUDLY (lambda_status=N + skip_reason) if rates missing —
    never invents bullpen numbers.
    """
    savant = savant if savant is not None else load_savant_lambdas(DATA / "savant_pitcher_expected.csv")
    parks = parks if parks is not None else load_park_factors(DATA / "park_factors.csv")
    offense = offense if offense is not None else load_team_offense(DATA / "team_offense.csv")
    if bullpen is None:
        bullpen = load_team_bullpen(DATA / "team_bullpen.csv") if use_bullpen else {}

    hid = normalize_pitcher_id(home_pitcher_id)
    aid = normalize_pitcher_id(away_pitcher_id)
    sp_h = savant.get(hid) or {}
    sp_a = savant.get(aid) or {}

    # name fallback
    if not sp_h and home_pitcher:
        for v in savant.values():
            if (v.get("pitcher_name") or "").lower() == home_pitcher.lower():
                sp_h = v
                break
    if not sp_a and away_pitcher:
        for v in savant.values():
            if (v.get("pitcher_name") or "").lower() == away_pitcher.lower():
                sp_a = v
                break

    lam_h = sp_h.get("lambda_runs")
    lam_a = sp_a.get("lambda_runs")
    ok_h = sp_h.get("lambda_status") == "ok" and lam_h is not None
    ok_a = sp_a.get("lambda_status") == "ok" and lam_a is not None

    version = MODEL_VERSION_V11 if use_bullpen else MODEL_VERSION_V1

    if use_park:
        pf, park_name, park_note = park_factor_for_home(home, parks)
    else:
        pf, park_name, park_note = 1.0, "", "park_off"

    if use_offense:
        off_home_scale, off_home_note = offense_scale(home, offense)  # batters for home
        off_away_scale, off_away_note = offense_scale(away, offense)
    else:
        off_home_scale = off_away_scale = 1.0
        off_home_note = off_away_note = "offense_off"

    base = {
        "home": home,
        "away": away,
        "home_pitcher": home_pitcher or sp_h.get("pitcher_name", ""),
        "away_pitcher": away_pitcher or sp_a.get("pitcher_name", ""),
        "home_pitcher_id": hid,
        "away_pitcher_id": aid,
        "lambda_home_raw": lam_h,
        "lambda_away_raw": lam_a,
        "park_factor": round(pf, 4),
        "park_name": park_name,
        "offense_adj_home": round(off_home_scale, 4),
        "offense_adj_away": round(off_away_scale, 4),
        "model_version": version,
        "citation": SAVANT_URL,
        "bullpen_citation": BULLPEN_URL if use_bullpen else "",
        "park_note": park_note,
        "offense_note_home": off_home_note,
        "offense_note_away": off_away_note,
        "lambda_source_home": sp_h.get("lambda_source", ""),
        "lambda_source_away": sp_a.get("lambda_source", ""),
        "use_bullpen": use_bullpen,
        "bullpen_rate_home": None,
        "bullpen_rate_away": None,
        "bullpen_note_home": "bullpen_off",
        "bullpen_note_away": "bullpen_off",
        "lambda_bullpen_home": None,
        "lambda_bullpen_away": None,
    }

    if not ok_h or not ok_a:
        skip = []
        if not ok_h:
            skip.append("missing_home_sp_lambda")
        if not ok_a:
            skip.append("missing_away_sp_lambda")
        return {
            **base,
            "lambda_home": None,
            "lambda_away": None,
            "model_prob_home": None,
            "model_prob_away": None,
            "lambda_status": "N",
            "skip_reason": "|".join(skip),
        }

    # Optional bullpen expansion: SP λ covers starter_ip; add relief_ip × BP rate/9
    # Home SP (+ home BP) → runs allowed to away; Away SP (+ away BP) → runs to home.
    lam_h_pitch = float(lam_h)
    lam_a_pitch = float(lam_a)
    if use_bullpen:
        try:
            lam_h_pitch, meta_h = expand_sp_lambda(lam_h_pitch, home, bullpen, require=True)
            lam_a_pitch, meta_a = expand_sp_lambda(lam_a_pitch, away, bullpen, require=True)
        except RuntimeError as exc:
            return {
                **base,
                "lambda_home": None,
                "lambda_away": None,
                "model_prob_home": None,
                "model_prob_away": None,
                "lambda_status": "N",
                "skip_reason": f"bullpen_required_missing|{exc}",
                "bullpen_note_home": "bullpen_error",
                "bullpen_note_away": "bullpen_error",
            }
        base["bullpen_rate_home"] = meta_h.get("bullpen_rate")
        base["bullpen_rate_away"] = meta_a.get("bullpen_rate")
        base["bullpen_note_home"] = meta_h.get("bullpen_note", "")
        base["bullpen_note_away"] = meta_a.get("bullpen_note", "")
        base["lambda_bullpen_home"] = meta_h.get("lambda_bullpen")
        base["lambda_bullpen_away"] = meta_a.get("lambda_bullpen")

    # Home scored ~ away pitching λ * park * home offense
    # Away scored ~ home pitching λ * park * away offense
    lam_home_scored = apply_offense(apply_park(lam_a_pitch, pf), off_home_scale)
    lam_away_scored = apply_offense(apply_park(lam_h_pitch, pf), off_away_scale)
    p_home = home_win_prob(lambda_home_scored=lam_home_scored, lambda_away_scored=lam_away_scored)

    return {
        **base,
        "lambda_home": round(lam_away_scored, 4),  # λ used for away runs (home pitch side)
        "lambda_away": round(lam_home_scored, 4),  # λ used for home runs (away pitch side)
        "model_prob_home": round(p_home, 6),
        "model_prob_away": round(1.0 - p_home, 6),
        "lambda_status": "ok",
        "skip_reason": "",
    }


def load_context(
    *,
    load_bullpen: bool = False,
) -> tuple[dict, dict, dict, dict]:
    """Return (savant, parks, offense, bullpen).

    bullpen map is {} unless load_bullpen=True (soft: missing file → {}).
    """
    parks = load_park_factors(DATA / "park_factors.csv")
    assert_coors_wrigley(parks)
    bp = load_team_bullpen(DATA / "team_bullpen.csv") if load_bullpen else {}
    return (
        load_savant_lambdas(DATA / "savant_pitcher_expected.csv"),
        parks,
        load_team_offense(DATA / "team_offense.csv"),
        bp,
    )
