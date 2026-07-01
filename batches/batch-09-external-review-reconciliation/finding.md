# batch-09 — External code review reconciliation (detail)

Reconciles the archived full-PR code review (`external-review-PR-2764-2026-07-01.md`) against our report. Every adopted
finding was re-verified against head `1a7aa37` at the code level (these are structural/correctness/liveness defects, not
economic PoCs). Source anchors below were read directly.

## New in-scope findings adopted

### F-07 — Unbounded terminal settlement under a fixed dissolve weight (HIGH, pre-launch)
- `settle_shorts_on_dereg` collects and loops all positions: `ShortPositions::iter_prefix(netuid).collect()`
  ([mod.rs:747-748]); `settle_longs_on_dereg` mirrors it: `LongPositions::iter_prefix(netuid).collect()`
  ([long.rs:497-499]). Each iteration does materialize + up to two `transfer_tao` + `recycle_custody_tao`.
- Caps clamp to `[1,4096]`/side: `set_short_max_positions` ([mod.rs:892]), `set_long_max_positions` ([long.rs:555]) —
  the authors' comment says the clamp exists "so governance can't lift the dereg-settlement" cost ⇒ up to ~8192
  settlements in one dissolution block.
- `dissolve_network` dispatch weight is **fixed**: `Weight::from_parts(119_000_000, 0) + reads(6) + writes(31)`
  ([dispatches.rs:1234-1236]) — does not scale with position count.
- **Impact:** liveness/DoS on consensus-critical chain maintenance; composes with **F-05** (prune-forced settlement: any
  registration at `SubnetLimit` forces the victim through settlement). Attacker pre-stuffs min-input positions.
- **Severity:** HIGH (the 4096/side cap is a partial mitigation the authors added; the fixed weight + unbounded loop
  remain a real weight-accounting gap — the PR body itself lists incremental settlement as a follow-up). Pre-launch.
- **Fix:** paginated/incremental settlement, or benchmarked weight scaling with live position count.

### F-08 — 1:1 exact-output fallback for non-dynamic pools in settlement (MEDIUM, pre-launch)
- `sim_tao_in_for_alpha_out` / `sim_alpha_in_for_tao_out` `match mechanism`: the `_` (non-dynamic) branch returns a
  non-market 1:1 quote — `Ok(alpha_out.to_u64().into())` / `Ok(tao_out.to_u64().into())` ([impls.rs:412-418, 440-446]).
- `settle_*_on_dereg` price cover via `short_spot_close_cost`/`long_spot_close_cost` → these sims, **without** re-checking
  `SubnetMechanism == 1`.
- **Impact:** a position surviving a dynamic→legacy mechanism transition gets terminal cover/equity valued off 1:1 —
  potential unbacked payout. Confidence medium (reachability of the transition with live positions needs analysis).
- **Fix:** define settlement for non-dynamic pools; don't silently value derivative liabilities at 1:1.

### F-09 — Long terminal equity realized asymmetrically as Alpha stake (LOW–MEDIUM, pre-launch)
- `settle_longs_on_dereg` credits equity as **minted stake**: `increase_stake_for_hotkey_and_coldkey_on_subnet(...)` +
  `SubnetAlphaOut += equity` ([long.rs:519-523]); the pot is then distributed pro-rata by `destroy_alpha_in_out_stakes`.
- Shorts pay TAO directly: `let _ = transfer_tao(&custody, &coldkey, equity)` ([mod.rs:769-770]).
- **Impact:** asymmetric realization can dilute/under-realize the computed equity after pro-rata distribution; no test
  asserts the final TAO-equivalent. (Because longs *mint* — a can't-fail credit — F-06's burn does not apply to longs;
  the long-side risk is dilution, not silent loss.)
- **Fix:** document the asymmetric terminal semantics, or preserve TAO-equivalent value on the long side.

### F-10 — `limit_price` binds the fee-less raw spot, not the realized price (LOW, pre-launch)
- `executable_price_ppb` = raw `SubnetTAO * 1e9 / SubnetAlphaIn` — fee-less, weight-unaware ([mod.rs:804-811]).
- Close-cost quotes route through the fee+weight-aware engine (`SimSwapOpts::WITH_FEES`, [mod.rs:794]).
- **Impact:** `limit_price` can pass while the realized price is outside the intended bound — weaker MEV/sandwich
  protection than implied, **even at 0.5/0.5** (the fee gap alone). Promotes the batch-08 un-promoted observation.
- **Fix:** enforce `limit_price` against the engine quote / post-trade effective price. Couples to F-01's fix.

## Enrichment: F-06 raised LOW→MEDIUM
The unguarded `let _ = transfer_tao(...)` burn ([mod.rs:769-772]) is compounded by the event
`Event::ShortTerminalSettled { equity, .. }` being emitted **unconditionally** ([mod.rs:775-780]) — the chain asserts a
payment that may not have happened, corrupting off-chain reconciliation. batch-08 held it LOW (narrow ED-edge burn);
this event-integrity dimension (review rated HIGH) moves it to LOW→MEDIUM (pre-launch keeps it below firm MEDIUM).

## Reconciliations — our DEFENDED verdicts stand
- **C-rollback:** `slippage_failure_rolls_back_state` passes ⇒ current safety, but only via the **implicit** FRAME
  extrinsic rollback; wrappers are not `#[transactional]`. We concur with the review (5-reviewer HIGH): make the boundary
  explicit (checks-first + `with_transaction`).
- **C-atomicity:** solvency stands (custody ≥ Σ obligations); the review adds two accuracy edges — `run_short_decay`
  decrements the aggregate before the restoration transfer (understates on failure); `recycle_custody_tao` decrements
  `TotalIssuance` before an unchecked `Exact` withdraw (non-balance failure could desync). No theft; hardening.
- **D-chi-moot:** flow→emissions is dead (`get_shares`→`get_shares_price_ema` only; `get_shares_flow`/`get_ema_flow` are
  `#[allow(dead_code)]`/uncalled — subnet_emissions.rs:135, 257). Caveat added: `DerivativeFlowFactor` defaults to `1.0`
  ([lib.rs:1457]), so derivatives write `SubnetTaoFlow` (non-neutral, contra DESIGN.md) — inert only because readers are
  dead; latent-arms if the flow path is wired.

## Corroboration (no change needed, cited)
F-02 (post-migration new subnets cold-start to the live reserve), F-03 (rated HIGH; `cleanup_short_if_empty` drops
aggregate while a destination position lives), F-06 (rated HIGH), `executable_price_ppb` (→ F-10).

## Out of scope (acknowledged, not absorbed)
~16 code-quality / testing-coverage / weight-benchmark / documentation findings (placeholder extrinsic weights, migration
weight miscount, untested slippage-guard / EMA-tick / migration, partial-close `last_active`, decay-dust bounds, `A_EMA`
saturation, duplicated `BLOCKS_PER_DAY`, zero-count storage bloat, review-loop IDs in test comments, stale
`IMPLEMENTATION_PLAN.md`, `SimSwapOpts` wrapper, dormant long-side launch scope). Legitimate; outside this report's
economic/reachability mandate; catalogued in the archived review.
