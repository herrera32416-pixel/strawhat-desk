"""Board model-% calibration + 'higher-%' play flag (PAPER / display only; never touches A/B/C grades or stamps).

Walk-forward evidence (2026-10-14, /workspace/acc, research/accuracy-2026-10/REPORT.md):
- NHL xG v1 vs the de-vigged market, held-out 2023-25: ML logloss 0.6745 vs 0.6699, puck line 0.6479 vs 0.6452,
  total 0.6940 vs 0.6914; picking the higher-model side won 55.9% of MLs vs 57.8% for the market favourite.
  Fitted shrink weight toward the model (logit space) was <= 0 in every fold, so NHL weight = 0.
  Live board Oct 3-14: NHL higher-model side 146-112 (.566) vs higher no-vig side 153-105 (.593).
- MLB Colab v1.1 / NFL / CFB: unchanged (NFL/CFB are already w=0; Colab has no walk-forward history, 9 live games).
- Spreads/totals priced 50-52%: higher no-vig side hit 50.1% (NHL tot, n=1818), 50.7% (MLB tot, n=5587),
  49.3% (CFB spread, n=3056). So a side under 52% is shown as 'no play (coin flip)'.
"""
from __future__ import annotations
import math

W_MODEL = {"NHL": 0.0}          # logit-space weight on (model - market); sport missing = leave model % as is
PLAY_MIN_PCT = 52.0


def _lg(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def calibrate_markets(sport: str, markets: dict | None) -> None:
    """In place: model_pct -> calibrated %, raw kept in model_raw_pct; adds market['lean']."""
    w = W_MODEL.get(sport)
    for m in (markets or {}).values():
        sides = m.get("sides") or []
        if w is not None and len(sides) == 2 and all(s.get("model_pct") is not None and s.get("novig_pct") is not None
                                                      for s in sides):
            for s in sides:
                q, raw = s["novig_pct"] / 100, s["model_pct"] / 100
                s["model_raw_pct"] = s["model_pct"]
                s["model_pct"] = round(100 / (1 + math.exp(-(_lg(q) + w * (_lg(raw) - _lg(q))))), 1)
            m["calibration"] = f"{sport} model weight {w} vs market (walk-forward 2026-10-14)"
        m["lean"] = lean(sides)


def lean(sides: list) -> dict | None:
    if len(sides) != 2 or any(s.get("model_pct") is None for s in sides):
        return None
    a, b = sides
    if a["model_pct"] == b["model_pct"]:
        return {"side": None, "pct": a["model_pct"], "play": False, "why": "tie"}
    hi = a if a["model_pct"] > b["model_pct"] else b
    ok = hi["model_pct"] >= PLAY_MIN_PCT
    return {"side": hi.get("side"), "label": hi.get("label"), "pct": hi["model_pct"], "play": ok,
            "why": f">= {PLAY_MIN_PCT:g}%" if ok else f"< {PLAY_MIN_PCT:g}% = coin flip, no play"}
