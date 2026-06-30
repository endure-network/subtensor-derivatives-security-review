# LEAD SETTLED — Cold-EMA cross-state drain composition is DEFENDED (F-02 does not escalate)

**Component:** `pallet-subtensor` derivatives — `do_open_short` / `do_close_short_self` / `short_t_ref`, composed with
the F-02 cold-EMA capacity bypass and the `pallet-subtensor-swap` Balancer engine (subtensor #2764).
**Status:** settled on `opentensor/subtensor#2764` — the short self-close cross-state attack is **not a drain**.
**Outcome:** F-02 stays **MEDIUM** (capacity / risk-limit bypass); it does **not** escalate to direct theft.

## The question (from batch-02 / open-surface)
F-02 proved that on a fresh subnet the cold EMA makes `short_t_ref = min(t_live, pEMA·A_EMA)` fall back to the live,
in-block-pumpable reserve, so an attacker can inflate the capacity cap and the retained proceeds `N`. The open
question: does that **compose into a value drain** — open a short at an in-block-PUMPED reserve (inflated `N1`),
restore the reserve, then cash-settle (`do_close_short_self`) at the restored reserve where the buyback `K1` is cheap,
and keep `N1 − K1`?

## Method (honest full-cost accounting)
PoC in the real mock-runtime harness (`poc_cold_ema_cross_state_short_self_close_drain`,
`poc_cold_ema_cross_state_fine_pump_sweep` in `tests/derivatives.rs`):
- **PUMP** the live reserve in-block via **real `add_stake`** — the production path that moves BOTH `SubnetTAO`
  (= `T_ref`) and the swap reserves together. (A raw `SwapInterface::swap` moves only the palswap reserves, NOT
  `SubnetTAO`, so it does not inflate `T_ref`; an earlier naive pump was invalid. The PoC now asserts `Tpump > Tbase`
  and that the EMA stays cold throughout.)
- **OPEN** a short against the pumped reserve (inflated `N1`, read via `quote_open_short`).
- **UNPUMP** via **real `remove_stake`**, then `do_close_short_self` at the restored reserve (`K1` via
  `quote_close_short`).
- Attacker P&L = the trader's **free-balance delta** (add_stake / open / remove_stake / close all move it), decomposed
  into `short_leg = returned − P ≈ N1 − K1` and `pump_loss = pump_in − unpump_out`. `fee = 0` isolates the engine math
  (best case for the attacker).

## Result — the gap is REAL, but always smaller than the cost to create it
`SKIP_WASM_BUILD=1 cargo test -p pallet-subtensor --lib poc_cold_ema_cross_state -- --nocapture`

The cold-EMA pump genuinely inflates `N1` (P=50k: `N1` = 23,205 → 29,129 → 37,298 TAO at pump 0 → 50k → 200k), and the
cross-state open/close produces a **real positive gap** `short_leg = N1 − K1` (up to **+33,577 TAO** at pump=200k,
P=50k, where `K1` collapses to 3,722 TAO at the restored reserve). **But the staking round-trip needed to manufacture
the price move costs strictly more than the gap at every size:**

| pump (TAO) | short_leg (N1−K1) | pump_loss | ratio | net (TAO) |
|-----------:|------------------:|----------:|------:|----------:|
| 100        | 2.0               | 2.0       | 1.001 | −0.001    |
| 500        | 9.8               | 9.8       | 1.003 | −0.025    |
| 5,000      | 91.6              | 93.9      | 1.025 | −2.27     |
| 50,000     | 549.2             | 660.1     | 1.202 | −110.9    |
| 200,000    | 33,576.7          | 53,965.3  | 1.607 | −20,388.6 |

`ratio = pump_loss / short_leg → 1.0` **from above** as pump → 0 and grows with pump; it **never crosses below 1.0**,
so `net = short_leg − pump_loss < 0` at every size (best observed: **−0.001 TAO** at the smallest pump). The `pump = 0`
control nets ~0 (the same-state `K0 = N` invariant), confirming the gap is created purely by the price move and is not
a test artifact.

## Why it is structurally defended
In the cold window `T_ref = t_live` **exactly** (the fallback makes them equal), so opening at the pumped reserve is
opening on a genuinely larger pool — self-consistent, not a stale-reference exploit. Realizing the cross-state gap
requires moving the live reserve back down (unpump), and the AMM charges the convex spread on that round-trip. The
value extractable through the derivative equals the value of the price move (paid once); manufacturing **and** reverting
that price move costs the same value **plus** the second-order slippage (paid on the round-trip). Both legs are
first-order in the pump; the second-order term keeps the AMM convexity with the pool (the defender). Net ≤ 0 always.

## Scope / limits (honest)
Proven for the **short self-close** vehicle (the natural cash-settled path), `fee = 0` (best case), `kappa = 0.9`,
pumps 100 TAO – 200k TAO on a 100k/100k pool. The **long mirror** (cold `A_ref`) and the **regular `do_close_short`**
vehicle (repay held Alpha instead of a spot buyback) are expected defended by the **same** structural principle and
were not separately reproduced — residual low-priority leads. Fees only worsen the attacker (charged on the
round-trip), so `fee = 0` being unprofitable implies `fee > 0` is too.

## Bottom line
The cold-EMA cap bypass (F-02) does **not** compose into a value drain via cross-state open/close. F-02 remains a
**MEDIUM** risk-limit / capacity bypass — fix by seeding `SubnetAlphaInMovingReserve` at subnet creation (per batch-02);
it does not escalate to direct theft. This settles the batch-02 "drain composition remains unproven" open question.

**PoC:** `tooling/poc/derivatives-poc.patch` → `poc_cold_ema_cross_state_short_self_close_drain`,
`poc_cold_ema_cross_state_fine_pump_sweep`.
