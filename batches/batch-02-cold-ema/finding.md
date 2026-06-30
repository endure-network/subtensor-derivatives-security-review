# FINDING-02 — Cold-EMA fresh-subnet capacity-cap bypass (MEDIUM, hardening)

**Component:** `pallet-subtensor` derivatives — `short_t_ref` / `long_a_ref` references (subtensor #2764).
**Status:** pre-launch (shorts/longs default-OFF); a risk-limit bypass, not a direct drain.

## Root cause
`SubnetAlphaInMovingReserve` (the block-lagged `A_EMA` that the T_ref manipulation-resistance relies on) is written
in only two places: a one-time migration that seeds **existing** subnets (`migrate_seed_alpha_in_moving_reserve`),
and the per-block `update_moving_price` tick. **There is no initialization at subnet creation.**

So a freshly-created dynamic subnet has `A_EMA = 0` and `pEMA = 0` until its EMA warms, and
`short_t_ref = min(t_live, pEMA·A_EMA)` falls back to the **live, in-block-manipulable** reserve (`long_a_ref`
mirrors this). The crossover/sandwich manipulation-resistance tests (`naive_single_side_pump_cannot_raise_t_ref`,
`crossover_nudge_does_not_inflate_t_ref_proceeds_or_capacity`, `sandwich_open_cannot_breach_capacity_cap`) all use a
*warm* EMA; the only cold-EMA test (`small_open_on_fresh_subnet_with_cold_ema`) asserts merely that a small open
succeeds, with no bound on `T_ref`.

## Impact
During the warmup window an attacker can pump the live reserve in-block to inflate `T_ref`, inflating the capacity
cap (`κ·T_ref`) and retained proceeds, and open positions **beyond the intended risk limit** on a fresh subnet.

## Proof
`poc/derivatives-poc.patch` → `poc_cold_ema_breaches_capacity_cap`:
```
honest cap = 119 TAO  ->  pumped cap = 399 TAO
# the over-cap open REJECTED at the honest reserve SUCCEEDS after an in-block pump of the live reserve
```
This is exactly the sandwich `sandwich_open_cannot_breach_capacity_cap` proves IMPOSSIBLE on a warm subnet.

The long side is symmetric and was confirmed with
`derivative_cold_ema.rs::long_open_cold_ema_live_alpha_bypasses_capacity_cap`. A separate rollback/atomicity probe,
`derivative_rollback.rs::slippage_failure_rolls_back_state`, passed for the tested slippage-failure paths, so the
confirmed issue is the cold-reference capacity bypass rather than broad extrinsic rollback failure.

## Severity — MEDIUM (hardening)
Re-enables a known attack class the authors explicitly defend for warm subnets, but it is **pre-launch**,
**fresh-subnet-scoped** (only during EMA warmup, before the subnet starts emitting), and is a **risk-limit bypass,
not a direct drain** — at the live 0.5/0.5 baseline `K0=N`, so an oversized cold-window position still returns ~`P`
on self-close (no minting). Whether the cold window composes into a cross-state drain (open at a pumped reserve /
close at the restored reserve) was not proven; the confirmed result is the short/long capacity bypass.

## Fix
Seed `SubnetAlphaInMovingReserve` (and the price EMA) at **subnet creation**, mirroring the migration's seeding for
existing subnets; or make the cold-EMA fallback conservative (reject derivative opens until the EMA warms, or use a
floor reference) instead of falling back to the live reserve.
