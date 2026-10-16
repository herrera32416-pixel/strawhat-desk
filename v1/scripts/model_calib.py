"""Board model-% calibration + 'higher-%' play flag (PAPER / display only; never touches A/B/C grades or stamps).

Walk-forward evidence (2026-10-14, /workspace/acc, research/accuracy-2026-10/REPORT.md):
- NHL xG v1 vs the de-vigged market, held-out 2023-25: ML logloss 0.6745 vs 0.6699, puck line 0.6479 vs 0.6452,
  total 0.6940 vs 0.6914; picking the higher-model side won 55.9% of MLs vs 57.8% for the market favourite.
  Fitted shrink weight toward the model (logit space) was <= 0 in every fold, so NHL weight = 0.
  Live board Oct 3-14: NHL higher-model side 146-112 (.566) vs higher no-vig side 153-105 (.593).
- MLB Colab v1.1 / NFL / CFB: unchanged (NFL/CFB are already w=0; Colab has no walk-forward history, 9 live games).
- Spreads/totals priced 50-52%: higher no-vig side hit 50.1% (NHL tot, n=1818), 50.7% (MLB tot, n=5587),
  49.3% (CFB spread, n=3056). So a side under 52% is shown as 'no play (coin flip)'.

2026-10-15 (Luis, 9:19pm CT): the board's HEADLINE % (shown_pct) is the market's no-vig fair % for every
sport/market until that sport/market passes the model gate in v1/data/model_gate.json (all OFF). The raw model %
stays on each side as model_unproven_pct ('model (unproven)'). The ★ / ★★ lean and the board's higher-% grading
use shown_pct. model_pct itself is left untouched so model_log keeps grading the model for the gate.
"""
from __future__ import annotations
import json
import math
from pathlib import Path

W_MODEL = {"NHL": 0.0}          # logit-space weight on (model - market); sport missing = leave model % as is
MARKET_ONLY = ("NFL", "CFB")
PLAY_MIN_PCT = 52.0
STRONG_MIN_PCT = 55.0   # Luis OK 2026-10-14: strong tier (★★); applies to the SHOWN % since 2026-10-15
GATE_PATH = Path(__file__).resolve().parents[1] / "data" / "model_gate.json"


def load_gate(path: Path = GATE_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # missing/broken config = every gate OFF (market % shown)
        return {"gate": {}}


def model_proven(sport: str, mkt: str, gate: dict | None = None) -> bool:
    g = (gate or load_gate()).get("gate") or {}
    return bool((g.get(sport) or {}).get(mkt, False))


def apply_shown(sport: str, mkt: str, m: dict, gate: dict | None = None) -> None:
    """Headline % per side: model % if this sport/market passed the gate, else the market no-vig fair %."""
    proven = model_proven(sport, mkt, gate)
    for s in m.get("sides") or []:
        raw = s.get("model_raw_pct", s.get("model_pct"))
        s["model_unproven_pct"] = None if s.get("model_source", "").startswith("market no-vig") else raw
        if proven and s.get("model_pct") is not None:
            s["shown_pct"], s["shown_source"] = s["model_pct"], "model (passed gate)"
        else:
            s["shown_pct"] = s.get("novig_pct")
            s["shown_source"] = "market no-vig fair % (model unproven)"
    m["shown_basis"] = "model" if proven else "market_novig"


def _lg(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def calibrate_markets(sport: str, markets: dict | None, gate: dict | None = None) -> None:
    """In place: model_pct -> calibrated %, raw kept in model_raw_pct; adds shown_pct + market['lean']."""
    w = W_MODEL.get(sport)
    gate = gate or load_gate()
    for mk, m in (markets or {}).items():
        sides = m.get("sides") or []
        if sport in MARKET_ONLY:  # FPI weight 0: model % = market no-vig % (fills blank spreads/totals)
            for s in sides:
                if s.get("model_pct") is None and s.get("novig_pct") is not None:
                    s["model_pct"] = s["novig_pct"]
                    s["model_source"] = "market no-vig (FPI w=0)"
        if w is not None and len(sides) == 2 and all(s.get("model_pct") is not None and s.get("novig_pct") is not None
                                                      for s in sides):
            for s in sides:
                q, raw = s["novig_pct"] / 100, s["model_pct"] / 100
                s["model_raw_pct"] = s["model_pct"]
                s["model_pct"] = round(100 / (1 + math.exp(-(_lg(q) + w * (_lg(raw) - _lg(q))))), 1)
            m["calibration"] = f"{sport} model weight {w} vs market (walk-forward 2026-10-14)"
        apply_shown(sport, mk, m, gate)
        m["lean"] = lean(sides)


STAR_EDGE_PP = 1.0     # Luis OK 2026-10-15 9:33pm CT: ★ only if shown % beats the break-even of the listed price by >= 1pp
STRONG_EDGE_PP = 3.0   # ★★ tier: >= 3pp over break-even


def breakeven_pct(price) -> float | None:
    try:
        pr = float(price)
    except (TypeError, ValueError):
        return None
    if pr == 0:
        return None
    return 100 * (-pr / (100 - pr) if pr < 0 else 100 / (pr + 100))


def lean(sides: list, key: str = "shown_pct") -> dict | None:
    """Higher shown-% side; play (★) only when shown % - break-even(listed price) >= STAR_EDGE_PP, strong (★★) >= STRONG_EDGE_PP."""
    if len(sides) != 2 or any(s.get(key) is None for s in sides):
        return None
    a, b = sides
    if a[key] == b[key]:
        return {"side": None, "pct": a[key], "play": False, "why": "tie", "basis": key}
    hi = a if a[key] > b[key] else b
    be = breakeven_pct(hi.get("price_american"))
    edge = None if be is None else round(hi[key] - be, 1)
    ok = edge is not None and edge >= STAR_EDGE_PP
    return {"side": hi.get("side"), "label": hi.get("label"), "pct": hi[key], "play": ok, "basis": key,
            "breakeven_pct": None if be is None else round(be, 2), "edge_vs_price_pp": edge,
            "strong": edge is not None and edge >= STRONG_EDGE_PP,
            "why": f"beats break-even by {edge}pp" if ok else "no edge, pass"}
