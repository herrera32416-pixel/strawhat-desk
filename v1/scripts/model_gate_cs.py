#!/usr/bin/env python3
"""Pre-registered, always-valid (anytime) model gate check. REPORT ONLY: never flips a gate flag.

Registered 2026-10-15 9:33pm CT (Luis approved Colab Backtest proposal #1), BEFORE any game is evaluated under it:
  statistic  d_i = logloss(no-vig market) - logloss(model) per graded game, side-0 probability, clipped to [-1, 1]
             (d > 0 means the model beat the no-vig market on that game)
  test       one-sided betting confidence sequence (Waudby-Smith & Ramdas 2023, predictable-plugin bets, grid over m)
             for the mean of d; lower bound L_t valid at every t simultaneously (safe to check weekly)
  alpha      0.10 (90% anytime-valid lower bound)
  pass       n >= 100 graded games AND L_t > 0  -> 'eligible'. Eligible only means Luis may be asked;
             the flag in model_gate.json stays false until Luis says yes.
  start      only games graded on/after 2026-10-15 (registration date); per sport x market.
Refs: Ramdas et al., Statistical Science 2023 (arXiv 2210.01948); Waudby-Smith & Ramdas, JRSS-B 2023 (arXiv 2010.09686).
Usage: python3 v1/scripts/model_gate_cs.py [model_log.json]   -> prints table, writes v1/data/model_gate_cs.json
"""
from __future__ import annotations
import json, math, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALPHA, MIN_N, CLIP, START = 0.10, 100, 1.0, "2026-10-15"
GRID = [i / 200 - 1 for i in range(401)]  # m in [-1, 1] step 0.005


def ll(p, y):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return -math.log(p if y else 1 - p)


def diffs(entries, sport, mk):
    out = []
    for e in sorted(entries, key=lambda e: e.get("graded_at_ct", "")):
        if e.get("sport") != sport or e.get("market") != mk or e.get("status") != "graded" or not e.get("winner"):
            continue
        if str(e.get("graded_at_ct", ""))[:10] < START:
            continue
        s0 = e["sides"][0]
        if s0.get("model_pct") is None or s0.get("novig_pct") is None:
            continue
        y = e["winner"] == s0["label"]
        d = ll(s0["novig_pct"] / 100, y) - ll(s0["model_pct"] / 100, y)
        out.append(max(-CLIP, min(CLIP, d)))
    return out


def lower_bound(xs, alpha=ALPHA):
    """Anytime-valid lower confidence bound for mean(xs), xs in [-1,1]. Returns -1 if no data."""
    if not xs:
        return -1.0
    lb = -1.0
    for m in GRID:
        logK, mu, var, n, rejected = 0.0, 0.0, 0.25, 0, False
        for x in xs:
            t = n + 1
            lam = min(math.sqrt(2 * math.log(1 / alpha) / (var * t * math.log(t + 1) + 1e-9)), 0.5 / max(1 + m, 1e-9))
            lam = max(0.0, lam)
            logK += math.log(max(1e-12, 1 + lam * (x - m)))
            n += 1
            mu += (x - mu) / n
            var += ((x - mu) ** 2 - var) / (n + 1)
            if logK >= math.log(1 / alpha):
                rejected = True
                break
        if rejected:
            lb = m  # H0: mean <= m rejected
        else:
            break
    return lb


def main():
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "model_log.json"
    entries = json.loads(p.read_text())["entries"]
    gate = json.loads((ROOT / "data" / "model_gate.json").read_text())
    res = {}
    for sport, mks in gate["gate"].items():
        for mk in mks:
            xs = diffs(entries, sport, mk)
            L = lower_bound(xs)
            res[f"{sport} {mk}"] = {"n": len(xs), "mean_d": round(sum(xs) / len(xs), 5) if xs else None,
                                    "cs_lower_90": round(L, 4), "eligible": len(xs) >= MIN_N and L > 0,
                                    "gate_flag": mks[mk]}
            print(f"{sport:4} {mk:7} n={len(xs):4} mean={res[f'{sport} {mk}']['mean_d']} L90={L:+.3f} "
                  f"{'ELIGIBLE (ask Luis)' if res[f'{sport} {mk}']['eligible'] else 'not eligible'} flag={mks[mk]}")
    (ROOT / "data" / "model_gate_cs.json").write_text(json.dumps(
        {"schema": "desk-model-gate-cs/v1", "registered": "2026-10-15 9:33pm CT", "alpha": ALPHA,
         "min_n": MIN_N, "statistic": "clipped logloss(no-vig) - logloss(model)", "results": res}, indent=1) + "\n")


if __name__ == "__main__":
    main()
