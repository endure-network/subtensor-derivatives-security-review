# 04 — Verified facts (empirical ground-truth; re-verifiable)

These are *verified* facts with repro, shareable across batches. **Re-verify any that are load-bearing for your finding.**

## Live mainnet (finney, block ~8.51M, 2026-06-29)
- **All 128 subnet pools are at Balancer weight `w_quote = 0.5` (`w1/w2 = 1.0`)**, max deviation ~1e-9. Cross-checked:
  `MovingPrice == T/A` (the `w=0.5` signature). Repro: `tooling/probes/probe_mainnet_weights.py`.
  ⇒ anything that *requires* `w≠0.5` is currently **dormant** on mainnet.
- Shorts/longs are **OFF** (not deployed). All derivative findings are therefore pre-launch.

## Baseline conservation
- At 0.5/0.5, self-cover `K0 = N` exactly (no free value). Repro: `tooling/sims/sim_baseline.py` and harness
  `poc_baseline_no_skew_no_leak` (+0.000074 TAO).

## What the project's own test suite already defends (don't re-litigate)
The 94 tests in `tests/derivatives.rs` lock: roundtrip non-profitability, anti-mint, global conservation,
in-kind-close conservation **under weights + fee**, cover-via-real-weighted-engine, **in-block** T_ref/capacity
manipulation (they found & fixed the crossover bug themselves), underwater self-close rejection, dereg `max(spot,EMA)`
cover, key-swap rehoming, default grace, stake locks, partial-close dust drain, decay closed-form.

## Weight reachability (why F-01 is dormant and not a config flip)
Weights move only via emission injection (proportional; PR #2758 reserves the disproportionate excess). User-LP is
permanently deprecated. Fresh pools seed at price ⇒ 0.5. No open PR re-enables LP; recent swap changes are
neutral/mitigating (`cap exp_scaled` is `dx≥0`-only; swap-size caps bound large self-covers). Details:
`batches/batch-01-selfcover-weights/amplifier-assessment.md`. ⇒ `w≠0.5` is a **code change** away, not a runtime toggle.

## Known prior subtensor bug classes (recur-watch)
partial-fill / limit-swap moved full not slippage-safe (#1383/#1538/#1877); reserve/migration drift (#2793/#2706);
aggregate raw-subtract wiping others' contributions (#2665); failed-transfer-but-bookkeeping-advances (#2662);
fixed-point rounding; emission subtotal errors (#1167/#855). No public subtensor audit found ⇒ the derivatives are unaudited.

## Follow-up harness facts from this review
- The cold-EMA capacity bypass is confirmed on both short and long references. Short repro:
  `poc_cold_ema_breaches_capacity_cap` (honest cap 119 TAO → pumped cap 399 TAO). Long repro:
  `long_open_cold_ema_live_alpha_bypasses_capacity_cap`.
- Slippage-failure rollback probes passed for the tested derivative open paths:
  `derivative_rollback.rs::slippage_failure_rolls_back_state`.
- Coldkey-swap short destination collisions can orphan aggregate state:
  `coldkey_swap_collision_orphans_short_aggregate`. The long mirror is currently blocked by
  `ColdKeyAlreadyAssociated`.
- Short deregistration terminal settlement is order-dependent for identical positions:
  `terminal_settlement_pays_identical_shorts_different_equity`.
