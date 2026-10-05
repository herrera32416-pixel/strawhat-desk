"""Does the CFB MATCHUP layer beat the market? (2026-10-04)  Walk-forward, out-of-sample by season.

PRE-REGISTERED CRITERIA (written before the first run; also in team/MATCHUP.md). The CFB matchup model may change
board picks ONLY if, on the pooled out-of-sample seasons 2024-2025 (FBS games with an ESPN close), for the spread
OR the total:
  (1) log-loss improvement vs the de-vigged closing market with 90% bootstrap CI > 0; AND
  (2) |lean| >= 1.5 pts bets at -110 win with the 90% CI lower bound above 52.38%; AND
  (3) units at -110 positive in BOTH test seasons (2 of 2).
Otherwise INFO ONLY. Training data: features from 2022 on (2021 pbp only seeds the prior season); test season s
trains on 2022..s-1. 2026 to date is reported but not part of the decision.
Same method as backtest/matchup_bt.py (NFL), with the CFB ratings penalty 12 games and KEYS cfb pmfs."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from desk import matchup as M, matchup_cfb as C
import matchup_bt as B

ROOT = M.ROOT
FEAT = os.path.join(ROOT, "data", "matchup", "cfb_features.csv.gz")

if __name__ == "__main__":
    if "--rebuild" in sys.argv or not os.path.exists(FEAT):
        ft = C.feature_table(list(range(2022, 2027)))
        ft.to_csv(FEAT, index=False); print("features", len(ft))
    kw = dict(feat=FEAT, test=[2024, 2025, 2026], train_min=2022, sport="cfb", oos=(2024, 2025), need_pos=2)
    R = {k: B.run(k, **kw) for k in ("spread", "total")}
    R["sensitivity_lam30"] = {k: B.run(k, 30, **kw)["oos_2024_2025"] for k in ("spread", "total")}
    R["_criteria_text"] = __doc__.split("PRE-REGISTERED CRITERIA")[1].split("Otherwise")[0].strip()
    # live model (all completed seasons, CV lambda)
    F = pd.read_csv(FEAT); live = {}
    for kind, cols in (("spread", M.SPREAD_F), ("total", M.TOTAL_F)):
        G = F.copy(); G["y"] = (G.result - G.spread_line) if kind == "spread" else (G.total - G.total_line)
        G = G.dropna(subset=cols + ["y"]); lam = M.choose_lam(G, cols, "y")
        live[kind] = dict(features=cols, model=M.fit_ridge(G[cols].values, G.y.values, lam), n=int(len(G)))
    passes = R["spread"]["passes"] or R["total"]["passes"]
    s, t = R["spread"]["oos_2024_2025"], R["total"]["oos_2024_2025"]
    ss, st = R["sensitivity_lam30"]["spread"]["ats_at_-110"]["lean>=1.5"], R["sensitivity_lam30"]["total"]["ou_at_-110"]["lean>=1.5"]
    b15s, b15t = s["ats_at_-110"]["lean>=1.5"], t["ou_at_-110"]["lean>=1.5"]
    live.update(status="INFLUENCES PICKS" if passes else "INFO ONLY", influence=bool(passes), backtest_summary=dict(
        spread=f"OOS 2024-25, {s['n']} FBS games: log loss {s['logloss_model']:.4f} vs market {s['logloss_market']:.4f} (improvement 90% CI "
               f"{s['ll_improvement_ci90'][0]:+.4f}..{s['ll_improvement_ci90'][1]:+.4f}); |lean|>=1.5: {b15s['w']}-{b15s['l']}, {b15s['units']:+.1f}u. "
               f"Lightly-shrunk: {ss['w']}-{ss['l']} ({100*ss['win_pct']:.1f}%), {ss['units']:+.1f}u.",
        total=f"OOS 2024-25, {t['n']} games: log loss {t['logloss_model']:.4f} vs {t['logloss_market']:.4f} (CI {t['ll_improvement_ci90'][0]:+.4f}.."
              f"{t['ll_improvement_ci90'][1]:+.4f}); |lean|>=1.5: {b15t['w']}-{b15t['l']}, {b15t['units']:+.1f}u. Lightly-shrunk: {st['w']}-{st['l']}, {st['units']:+.1f}u.",
        criteria=R["_criteria_text"], passes=bool(passes)))
    json.dump(live, open(C.MODEL, "w"), indent=1)
    json.dump(R, open(os.path.join(ROOT, "data", "matchup", "cfb_backtest.json"), "w"), indent=1, default=float)
    print(live["status"]); print(json.dumps(live["backtest_summary"], indent=1))
    for k in ("spread", "total"):
        print(k, R[k]["criteria"], {x: R[k]["oos_2024_2025"][x] for x in ("lean_sd",)}, R[k]["coefs_by_test_season"])
