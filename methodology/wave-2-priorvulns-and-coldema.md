# Wave 2 — prior subtensor vulns + VERIFIED cold-EMA finding

## Prior-vulns librarian (bg_6a508635)
- **NO public audit PDFs** found for subtensor (SRLabs/Quantstamp/Halborn/Zellic/OAK) ⇒ the derivatives are **unaudited**. Raises pen-test value.
- Recurring bug classes (issue#) that map straight onto the derivative code:
  - **Partial-fill / limit-swap moved FULL not slippage-safe amount** (#1383, #1538, #1877) → derivative partial-close `fraction_ppb` + `limit_price`.
  - **Reserve-accounting / migration drift**: unwired cleanup migration shrank reserves (#2793); chain-buys accounting diluted stakers (#2706) → derivative adds `migrate_seed_alpha_in_moving_reserve` + direct fee-free reserve writes.
  - **Aggregate raw-subtraction wiping others' contributions** (#2665 `force_reduce_lock`) → `ShortAggregate`/`LongAggregate` Σ decrements vs per-position decay.
  - **Failed transfer still advances bookkeeping** (#2662 `root_claim_on_subnet`) → non-transactional decay/dereg hooks guarded only by `.is_ok()` while aggregate/omega advance unconditionally.
  - Fixed-point rounding/truncation; emission-split subtotal errors (#1167, #855) → derivative flow-χ accounting.
- 2024 PyPI wallet compromise → chain has a safe-mode kill switch (context).

## VERIFIED FINDING — cold-EMA fresh-subnet window (NEW, grounded)
- `SubnetAlphaInMovingReserve` (A_EMA) has only TWO write sites: (a) one-time migration seeding EXISTING subnets at upgrade ([hooks.rs:183], correctly wired); (b) per-block `update_moving_price` tick. **No init at subnet creation.**
- ⇒ a newly-created dynamic subnet starts `A_EMA = 0`, `pEMA = 0`. In `short_t_ref`/`long_a_ref`: `t_ema = pema·a_ema = 0` ⇒ **`t_ref = t_live`** (the in-block-manipulable live reserve).
- The in-block manipulation-resistance tests (`naive_single_side_pump_cannot_raise_t_ref`, `crossover_nudge_*`, `sandwich_open_cannot_breach_capacity_cap`) ALL use `setup_market` with a WARM EMA. The ONLY cold-EMA test (`small_open_on_fresh_subnet_with_cold_ema`, L224-243) asserts merely that a small open SUCCEEDS — NO `t_ref` bound, NO manipulation check.
- ⇒ **During a fresh subnet's EMA warmup the crossover-manipulation defense is INACTIVE** (falls back to live spot). Whether inflating capacity/proceeds via an in-block reserve pump is net-profitable there is the open question → sim/PoC.
- Elevates candidate #1 → "multi-block EMA manipulation **+ cold-start fresh-subnet window**".

## STATUS: research COMPLETE. All 8 background agents collected & journaled. Awaiting user steer
(scope priority / environment / depth) before any PoC work — per the "assess together" request.
