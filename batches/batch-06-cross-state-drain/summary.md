# Batch 06 — Cold-EMA cross-state drain composition (F-02 escalation probe)

**Verdict:** lead SETTLED · **DEFENDED** · the short self-close cross-state attack is **not a drain** · F-02 stays
**MEDIUM** (it does **not** escalate to direct theft).

**One-liner:** F-02's cold-EMA bypass lets you open a short against an in-block-PUMPED reserve (genuinely inflated
retained proceeds `N1`) and cash-settle (`do_close_short_self`) at the restored reserve where the buyback `K1` is
cheap — a **real** cross-state gap `N1 − K1` (up to +33,577 TAO in the PoC). But manufacturing the required price move
via a real `add_stake`/`remove_stake` round-trip costs **strictly more** than the gap at every pump size, so the
attacker always nets a loss.

**Proof:** `poc_cold_ema_cross_state_short_self_close_drain` + `poc_cold_ema_cross_state_fine_pump_sweep`. Pump via real
`add_stake` (asserts `Tpump > Tbase`, so `T_ref` actually moves — a raw `SwapInterface::swap` does NOT move
`SubnetTAO`), open, unpump via `remove_stake`, self-close; P&L = trader free-balance delta decomposed into
`short_leg = N1 − K1` and `pump_loss`. `fee = 0` (best case). `ratio = pump_loss/short_leg → 1.0` from above as
pump → 0 and never crosses below 1.0; best net = **−0.001 TAO**. The `pump = 0` control nets ~0 (`K0 = N`).

**Why defended:** in the cold window `T_ref = t_live` exactly, so the pumped open is self-consistent (opening on a
genuinely larger pool), not a stale reference. Realizing the gap requires reverting the price move, and the AMM charges
the convex round-trip spread — the value extractable equals the price-move value (paid once) while creating+reverting
it costs that value plus second-order slippage. The pool keeps the convexity.

**Scope:** short self-close, `fee = 0`, `kappa = 0.9`, pumps 100 TAO–200k TAO. Long mirror + regular `do_close_short`
expected defended by the same principle (not separately reproduced); fees only worsen the attacker.

**Files:** `finding.md`. **Action:** none beyond the existing F-02 fix (seed `SubnetAlphaInMovingReserve` at subnet
creation). Closes the batch-02 "drain composition remains unproven" open question.
