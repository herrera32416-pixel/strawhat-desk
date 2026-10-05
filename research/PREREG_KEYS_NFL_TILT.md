# Pre-registration: NFL margin pmf fix (written 2026-10-04 8:50 PM CT, BEFORE any run)

**Problem.** `desk/keys.py` NFL margin pmf corrects the kernel's mean with `np.roll(round(gap))`. Where the
neighbouring closing lines' mean sits >= 0.5 pt from the centre (sparse regions, e.g. road favourites ~7),
the whole pmf shifts by 1 and key-number mass lands on 2/4, 6/8. Example (fit <= 2025): home line +7 →
P(|margin| = 3) 4.3% (vs ~14% nearby), and `anchor()` cannot reach 50% (0.467).

**Fix (single candidate, no alternatives will be tried):** NFL margin uses the exponential-tilt mean
correction already used for CFB (`Dist(..., tilt=True)`): same kernel, same bandwidth, same 15% normal mix;
the mean is moved by reweighting outcomes, so key numbers stay on their integers. No sign symmetry for NFL.

**Test (`backtest/keys_nfl_tilt_bt.py`).** Seasons 2015–2025, walk-forward: each season's pmf is fit on
seasons < s, old (roll) vs new (tilt). For every game with a closing spread and odds: centre = `anchor()` at
the closing line and de-vigged closing odds (that is how the board/teasers use KEYS). Evaluate cover
probabilities at alternative lines close + d, d ∈ {±0.5, ±1, …, ±7} (board DK-vs-consensus gaps and teaser
legs live here): event = home margin > line (pushes at integer lines excluded), prediction = P(win | no push).

**Pass criteria (all required to ship):**
1. Pooled log loss over all alt-line events improves (old − new), 90% game-level bootstrap CI > 0.
2. Road-favourite band (close home line +5.5…+8.5): log-loss improvement point estimate > 0.
3. No other band hurt: bands by close home line (≤ −10.5, −10…−7, −6.5…−3.5, −3…0, +0.5…+3, +3.5…+5, +5.5…+8.5,
   ≥ +9); in every band the improvement point estimate ≥ −0.0005 and its 90% CI upper bound > 0.
4. Calibration: pooled |mean predicted − actual| of alt-line cover (new) ≤ old + 0.002, and push-rate at integer
   alt lines: |predicted − actual| (new) ≤ old + 0.002.
5. Anchor fidelity: new `anchor()` reproduces the de-vigged closing probability within 0.5 pp for ≥ 99% of games.
Reported but not criteria: exact-margin log likelihood, the closing-line cover log loss (≈ market by construction).
If any criterion fails, the board is left unchanged and the result documented here and in FINDINGS.

## Result (run 2026-10-04 ~8:55 PM CT): FAILS → board unchanged
`data/keys_nfl_tilt_bt.json`: 3,028 games, 83,439 alt-line events.
- C1: pooled log loss 0.647679 → 0.647418, improvement +0.00026, 90% CI −0.00011…+0.00064 → **fail** (CI includes 0).
- C2: road-fav band +5.5…+8.5 (282 games): 0.646098 → 0.646292 (−0.00019) → **fail**. The fix does not help the band it was aimed at on alt-line cover: the roll artifact shows at particular centres/seasons and averages out.
- C3: home fav ≤ −10.5 −0.00106 (CI −0.0034…+0.0014) breaks the −0.0005 floor; −10…−7 −0.00018 (CI upper +0.00002) → **fail**. The big gain is only at road favs ≥ +9 (+0.0113, CI +0.0025…+0.0199, 102 games).
- C4: calibration about equal (cover |err| .0101 → .0105, push |err| .0019 → .0020) → pass.
- C5: anchor within 0.5pp: 94.1% → 98.8% (needs ≥ 99%) → **fail**.
- Not criteria: exact-margin log-lik −3.9038 → −3.8727 (better).
Board, teasers and recheck keep the roll pmf. The simulator keeps using tilt (its own backtest already ran with it). A narrower fix (tilt only when |gap| ≥ 0.5, or only for road favourites ≥ +9) would be a new hypothesis, chosen after seeing these bands. It needs fresh data (2026 season) before any test.
