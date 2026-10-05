"""Does CFB need key-number tables bucketed by spread size? (2026-10-04)
Result: the old kernel under-predicted key-number mass in every |spread| bucket (15 of 30 cells |z|>2, max z 6.8,
worst at 7.5-21 and for away favourites) because (a) it was home-signed and (b) np.roll moved key mass off its
integers. Fix in desk/keys.py for cfb_margin: sign-symmetric kernel + exponential tilt -> 4 of 30 cells |z|>2,
max z 2.4, walk-forward mean log-lik -4.247 -> -4.032. Explicit bucket tables were not needed.
For each FBS game with an ESPN close (2023-2026, walk-forward: the KEYS pmf is fit on seasons < the game's season),
compare the observed share of final margins landing on the key numbers with the KEYS kernel pmf's prediction, by
|closing spread| bucket. KEYS is a kernel-weighted empirical pmf centred on the game's own line (adaptive bandwidth,
effective n >= 400), so it is already conditional on spread size; a bucketed table would only help if the kernel
misses bucket-level key-number mass. Writes backtest/out/cfb_keys_buckets.json."""
import sys, os, json, collections, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from desk.keys import load_rows, Dist

KEYS = (3, 7, 10, 14, 17, 21)
BUCKETS = ((0, 3.5), (3.5, 7.5), (7.5, 14.5), (14.5, 21.5), (21.5, 99))
L, Y, S = load_rows("cfb_margin")


def table(sym):
  D = {}
  rows = []
  ll = 0.0
  for l, y, s in zip(L, Y, S):
    if s < 2023:
        continue
    if s not in D:
        D[s] = Dist("cfb_margin", max_season=s - 1, sym=sym)
    p = D[s].pmf(l); g = D[s].grid
    pk = {k: float(p[g == k].sum() + p[g == -k].sum()) for k in KEYS}
    ll += math.log(max(float(p[g == y].sum()), 1e-9))
    rows.append((abs(l), y, pk))
  out = {}
  for lo, hi in BUCKETS:
      R = [r for r in rows if lo <= r[0] < hi]
      n = len(R)
      if not n:
          continue
      b = {"n": n}
      for k in KEYS:
          obs = sum(abs(r[1]) == k for r in R); exp = sum(r[2][k] for r in R)
          sd = math.sqrt(max(sum(r[2][k] * (1 - r[2][k]) for r in R), 1e-9))
          b[f"margin_{k}"] = dict(obs=int(obs), exp=round(exp, 1), obs_pct=round(obs / n, 4), exp_pct=round(exp / n, 4), z=round((obs - exp) / sd, 2))
      out[f"|spread| {lo}-{hi if hi < 99 else '+'}"] = b
  zs = [v["z"] for b in out.values() for k, v in b.items() if k.startswith("margin_")]
  out["_summary"] = dict(cells=len(zs), max_abs_z=max(abs(z) for z in zs), n_abs_z_over_2=sum(abs(z) > 2 for z in zs),
                         games=len(rows), seasons="2023-2026 (walk-forward)")
  out["_summary"]["mean_loglik"] = round(ll / len(rows), 4)
  return out


out = {"home_signed_kernel_(old)": table(False), "symmetric_tilted_kernel_(new)": table(True)}
os.makedirs("backtest/out", exist_ok=True)
json.dump(out, open("backtest/out/cfb_keys_buckets.json", "w"), indent=1, default=float)
for name, t in out.items():
    print("==", name)
    for k, v in t.items():
        print(k, json.dumps(v, default=float))
