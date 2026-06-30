# Batch 02 — Cold-EMA fresh-subnet capacity bypass (F-02)

**Verdict:** MEDIUM (hardening) · confirmed · pre-launch · a **risk-limit bypass, not a direct drain**.

**One-liner:** `SubnetAlphaInMovingReserve` (A_EMA) is not seeded at subnet creation (the migration only seeds
*existing* subnets), so a fresh subnet's `short_t_ref = min(t_live, pEMA·A_EMA)` falls back to the **live,
in-block-manipulable** reserve while the EMA is cold. The capacity sandwich that `sandwich_open_cannot_breach_
capacity_cap` proves impossible on a warm subnet then succeeds.

**Proof:** `poc_cold_ema_breaches_capacity_cap` — honest cap 119 TAO (over-cap open rejected) → in-block pump → cap
399 TAO → the same open succeeds. Long-side mirror
`derivative_cold_ema.rs::long_open_cold_ema_live_alpha_bypasses_capacity_cap` also passes. Rollback/atomicity probe
`derivative_rollback.rs::slippage_failure_rolls_back_state` passed, so the confirmed issue is the cold-reference cap
bypass rather than broad extrinsic rollback failure.

**Severity:** re-enables a defended attack class, but pre-launch, fresh-subnet-scoped, and not a direct drain (at the
0.5/0.5 baseline `K0=N`, so an oversized cold-window position still returns ~P on self-close). A cross-state drain
composition was not proven; the verified result is short/long risk-limit bypass.

**Files:** `finding.md`. **Fix:** seed A_EMA (and pEMA) at subnet creation, or make the cold fallback conservative
(reject opens until the EMA warms / use a floor reference) instead of falling back to the live reserve.
