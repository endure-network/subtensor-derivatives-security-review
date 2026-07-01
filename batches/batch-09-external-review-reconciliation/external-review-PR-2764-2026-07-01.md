## PR Review: Pool borrowing spec: covered continuous-unwind shorts (proposal)

**PR:** [opentensor/subtensor#2764](https://github.com/opentensor/subtensor/pull/2764) · base `devnet-ready` ← head `feat/pool-borrowing-spec` · 27 files
**Profile:** full | **Run outcome:** full | **Recommendation:** request_changes

### Executive Summary

The PR is a substantial RFC-quality derivatives implementation, but several validated accounting and weight issues are not safe to ship as-is even with feature flags defaulting off. The highest-risk issues are late fallible checks after irreversible mutations without explicit FRAME transaction wrapping, unbounded terminal settlement during subnet dissolution, silent value loss/desynchronization paths, and documentation/default mismatches around derivative TaoFlow.

**Findings:** 0 critical, 4 high, 14 medium, 12 low, 0 info

**Key themes:**
- Financial state transitions rely on implicit or absent transactional semantics
- Unbounded or inaccurately weighted block/upgrade work
- Aggregate/count/custody accounting can desynchronize on exceptional paths
- Documentation and launch scope diverge from implemented behavior
- Several load-bearing paths lack direct tests

**Reduction:** net: ~-1100 LOC possible (defer the gated long side ~-900 LOC, delete stale `IMPLEMENTATION_PLAN.md` -180 LOC, collapse `SimSwapOpts` ~-20 LOC)

---

### Findings

#### 🟠 Late slippage and limit checks can leave mutated state committed
- **Category:** correctness | **File:** `pallets/subtensor/src/derivatives/mod.rs` (`do_open_short`/`do_close_short`/`do_open_long`/`do_close_long`)
- **Severity:** high | **Confidence:** high | **Status:** validated
- **Claim:** Derivative open/close helpers perform transfers, reserve mutations, flow writes, position/count updates, or stake mutations *before* fallible slippage/count/hotkey checks, and the dispatch wrappers are not annotated `#[transactional]` or wrapped in `with_transaction`.
- **Evidence:**
  - `do_open_short` transfers TAO to custody, decreases `SubnetTAO`/`TotalStake`, writes flow, inserts position/aggregate, *then* calls `ensure_price_at_least`.
  - `do_close_short` moves alpha/TAO and records flow before `ensure_price_at_most`; long side mirrors the pattern.
  - `dispatches.rs` calls the helpers directly with placeholder weights and no `#[transactional]`; the repo uses explicit `#[transactional]`/`with_transaction` elsewhere.
- **Why it matters:** A failed slippage/count/mismatch check can return `DispatchError` after balances, reserves, positions, or aggregate state have already changed. Correctness depends entirely on the implicit FRAME extrinsic-rollback guarantee — undocumented and fragile to any future non-extrinsic caller.
- **Suggested fix:** Move all fallible checks before mutations where possible; wrap each multi-step state transition in explicit `#[transactional]`/`with_transaction`. Add `assert_noop!` tests proving no state persists on a violating `limit_price`.
- **Consensus:** 4 reviewers (generalist-claude, generalist-openai, ai-slop) — merged claude:generalist_1, openai:generalist_1, ai_slop_1, claude:generalist_9

#### 🟠 Subnet dissolution performs unbounded derivative terminal settlement under fixed weight
- **Category:** performance | **File:** `pallets/subtensor/src/coinbase/root.rs` (`do_dissolve_network`)
- **Severity:** high | **Confidence:** high | **Status:** validated
- **Claim:** `do_dissolve_network` now calls `settle_shorts_on_dereg` and `settle_longs_on_dereg`, each collecting and iterating **all** positions for the subnet, while dissolve weights remain fixed and the per-side caps are governance-clampable up to 4096.
- **Evidence:**
  - Both settlement fns `iter_prefix(netuid).collect()` and loop over every position (materialize + up to two `transfer_tao` + `recycle_custody_tao` each), before `destroy_alpha_in_out_stakes`.
  - `ShortMaxPositions`/`LongMaxPositions` clamp to `[1,4096]` → up to ~8192 positions in one dissolution block; `dissolve_network` weight stays fixed (`reads(6)/writes(31)`).
- **Why it matters:** A heavily-populated subnet can make dissolution exceed block weight — a liveness/DoS risk on consensus-critical chain maintenance. An adversary can pre-open min-input positions before a governance dereg. (PR body itself flags incremental settlement as a required follow-up.)
- **Suggested fix:** Paginated/incremental settlement, or benchmarked weight scaling with live position count; keep production caps within proven block limits.
- **Consensus:** 5 reviewers (generalist-kimi, generalist-glm, generalist-claude, generalist-openai, database) — merged kimi:generalist_6, glm:generalist_4, claude:generalist_3, openai:generalist_2, database_5

#### 🟠 Coldkey-swap collision silently drops positions and desynchronizes aggregates/counts
- **Category:** correctness | **File:** `pallets/subtensor/src/derivatives/mod.rs` (`swap_positions_for_coldkey_swap`)
- **Severity:** high | **Confidence:** high | **Status:** validated
- **Claim:** When the destination coldkey already has a position, the migrated position is `take`n and the count decremented, but the position is dropped **without** subtracting its `ShortAggregate`/`LongAggregate` (r/e/b/q or d sigma) contribution or returning/recycling collateral.
- **Evidence:**
  - Collision branch only decrements `ShortPositionCount`; no aggregate `r/e/b/q` adjustment, no custody/stake value returned. Long branch mirrors it.
  - `cleanup_short_if_empty` can then remove aggregate/active-set state based on the decremented count while a destination position still exists.
  - The "unreachable" precondition is enforced externally (`do_swap_coldkey` checks `StakingHotkeys` empty) — it does **not** assert absence of a derivative position.
- **Why it matters:** If the precondition is ever violated, user value is silently dropped and aggregate/active-set state becomes inconsistent — capacity, per-block decay restoration (draining orphaned custody into the pool), and settlement then operate on phantom or missing positions.
- **Suggested fix:** Reject/abort on collision, or explicitly settle/transfer/recycle the dropped position and subtract its materialized aggregate contribution; emit an event.
- **Consensus:** 3 reviewers (generalist-glm, generalist-claude, database) — merged glm:generalist_3, claude:generalist_10, database_3, database_6, database_10

#### 🟠 Terminal short equity transfer failure is ignored while events report payment
- **Category:** correctness | **File:** `pallets/subtensor/src/derivatives/mod.rs` (`settle_shorts_on_dereg`)
- **Severity:** high | **Confidence:** high | **Status:** validated
- **Claim:** `settle_shorts_on_dereg` discards the result of the trader equity transfer (`let _ = transfer_tao(...)`), then recycles cover and sweeps residual custody, while emitting `ShortTerminalSettled { equity }` regardless of whether the transfer succeeded.
- **Evidence:**
  - Equity leg uses `let _ = Self::transfer_tao(&custody, &coldkey, equity)`; the escrow leg immediately above is correctly gated by `.is_ok()`.
  - `recycle_custody_tao(cover)` then `recycle_custody_tao(TaoBalance::MAX)` burn/sweep residual custody; the event is emitted with the booked `equity`.
- **Why it matters:** A terminal settlement transfer failure can silently underpay a trader and burn the remaining custody while on-chain events claim the equity was paid — unrecoverable (one-shot dereg) and corrupting off-chain reconciliation.
- **Suggested fix:** Cap equity to available transferable custody, keep unpaid equity in a refundable ledger, or emit/pay only the actual transferred amount.
- **Consensus:** 3 reviewers (generalist-kimi, generalist-glm, security) — merged kimi:generalist_3, glm:generalist_1, security_2

#### 🟡 DerivativeFlowFactor defaults to full TaoFlow effect despite flow-neutral documentation
- **Category:** api-contract | **File:** `pallets/subtensor/src/lib.rs` (`DefaultDerivativeFlowFactor`)
- **Severity:** medium | **Confidence:** high | **Status:** validated
- **Claim:** `DerivativeFlowFactor` defaults to `I64F64::from_num(1)` (full effect), while `DESIGN.md` and the rollout text describe derivative TaoFlow as off / flow-neutral by default.
- **Evidence:**
  - `lib.rs` documents and returns a default of `1.0`; `mod.rs` routes derivative flow through `record_tao_outflow/inflow` when `scale_flow` is nonzero.
  - `DESIGN.md` says derivatives "never call `record_tao_inflow/outflow`, so TaoFlow is untouched" and lists derivative TaoFlow as off / not wired.
- **Why it matters:** Governance enabling shorts/longs without first setting χ=0 would immediately activate full synthetic TaoFlow effects on subnet emissions — contrary to the stated safe-rollout expectation and the design's core "emissions untouched" safety argument.
- **Suggested fix:** Default χ to 0 (flow-neutral), or update the design/launch docs and require an explicit governance step acknowledging χ=1.
- **Consensus:** 6 reviewers (generalist-kimi, generalist-glm, generalist-claude, security, maintainability, database) — merged kimi:generalist_7, glm:generalist_8, claude:generalist_7, security_1, maintainability_2, database_8

#### 🟡 Short decay commits aggregate decrement before restoration transfer succeeds
- **Category:** correctness | **File:** `pallets/subtensor/src/derivatives/mod.rs` (`run_short_decay`)
- **Severity:** medium | **Confidence:** high | **Status:** validated
- **Claim:** `run_short_decay` reduces `r_sigma/e_sigma/b_sigma` and writes `ShortAggregate` **before** attempting the custody→subnet restoration transfer; on transfer failure the aggregate records decay that was not actually restored to the pool.
- **Evidence:**
  - Aggregate decremented, `omega` advanced, and `ShortAggregate::insert` committed, *then* `transfer_tao(...).is_ok()` gates only the `SubnetTAO`/`TotalStake` credit. No retry ledger or rollback.
- **Why it matters:** A failed restoration transfer permanently breaks the documented custody-vs-materialized-obligation invariant, and future decay/capacity calculations use understated aggregate values (compounding).
- **Suggested fix:** Perform the transfer first and commit the aggregate only on success, or record undelivered restoration for retry.
- **Consensus:** 3 reviewers (generalist-kimi, generalist-glm, generalist-claude) — merged kimi:generalist_5, glm:generalist_5, claude:generalist_4

#### 🟡 recycle_custody_tao mutates TotalIssuance before unchecked withdraw
- **Category:** correctness | **File:** `pallets/subtensor/src/derivatives/mod.rs` (`recycle_custody_tao`)
- **Severity:** medium | **Confidence:** medium | **Status:** plausible
- **Claim:** `recycle_custody_tao` decrements `TotalIssuance` by the planned amount *before* calling `Currency::withdraw` and ignores the withdraw result.
- **Evidence:**
  - `amt` capped to custody balance; `TotalIssuance::mutate` decrements; `Currency::withdraw(... Precision::Exact ... Fortitude::Force)` result discarded with `let _`.
- **Why it matters:** If the Exact withdraw fails for a reason other than free-balance insufficiency (lock/hold/hook), recorded issuance decreases while balances remain — a supply-accounting mismatch on value-conservation-critical default/dereg paths.
- **Suggested fix:** Withdraw/burn first and decrement `TotalIssuance` only by the realized withdrawn amount, or propagate failure.
- **Consensus:** 2 reviewers (generalist-kimi, security) — merged kimi:generalist_4, security_5

#### 🟡 Self-cover close paths use live manipulable quotes and lack success-path tests
- **Category:** correctness | **File:** `pallets/subtensor/src/derivatives/mod.rs` (`do_close_short_self`/`do_close_long_self`)
- **Severity:** medium | **Confidence:** medium | **Status:** plausible
- **Claim:** `close_short_self`/`close_long_self` settle liabilities arithmetically against **live** swap-engine quote costs without executing real swaps, and their successful dispatch paths are not directly tested.
- **Evidence:**
  - `do_close_short_self` computes `k` from `short_spot_close_cost` on live reserves, injects `k+e_close` TAO and returns `claim-k` with **no** alpha reserve/`SubnetAlphaOut` movement; long mirror injects alpha with no TAO transfer.
  - `tests/derivatives.rs` references `do_close_short_self` once (underwater rejection only); `do_close_long_self` has zero test references.
- **Why it matters:** These paths move real value through synthetic settlement priced off a live (sandwichable) quote — unlike the open side, which was hardened to a lagged reference. Tests currently catch neither over-recovery, under-crediting, nor reserve/flow divergence.
- **Suggested fix:** Price the self-cover leg against a conservative reference (max of spot and lagged EMA, mirroring `K_D`); add dispatch-level success + manipulation + conservation tests for both sides.
- **Consensus:** 4 reviewers (generalist-kimi, security, generalist-claude, tests) — merged kimi:generalist_2, security_4, claude:generalist_6, tests_1

#### 🟡 limit_price slippage guard compares raw reserve spot, not engine-realized price
- **Category:** correctness | **File:** `pallets/subtensor/src/derivatives/mod.rs` (`executable_price_ppb`)
- **Severity:** medium | **Confidence:** high | **Status:** validated
- **Claim:** `ensure_price_at_least/at_most` use `executable_price_ppb` (a fee-less raw `SubnetTAO/SubnetAlphaIn` ratio), while close-cost quotes use fee- and weight-aware exact-output simulation (`sim_*` `WITH_FEES`).
- **Evidence:**
  - `executable_price_ppb` = `t * 1e9 / a` from raw reserves only; `short_spot_close_cost`/`long_spot_close_cost` route through the fee+weight-aware engine. The PR's own `engine_cover_diverges_from_naive_cpmm` test shows >1% divergence under skewed weights.
- **Why it matters:** Users believe `limit_price` bounds actual engine execution price, but it can pass while the fee/weight-aware realized price is outside the intended bound — weaker MEV/sandwich protection than the parameter implies.
- **Suggested fix:** Define `limit_price` semantics explicitly and enforce against the swap-engine quote / post-trade effective price.
- **Consensus:** 2 reviewers (generalist-glm, tests) — merged glm:generalist_9, tests_2

#### 🟡 Long terminal settlement realizes equity as alpha stake before pro-rata subnet destruction
- **Category:** architecture | **File:** `pallets/subtensor/src/derivatives/long.rs` (`settle_longs_on_dereg`)
- **Severity:** medium | **Confidence:** medium | **Status:** plausible
- **Claim:** `settle_longs_on_dereg` credits long terminal equity as **Alpha stake** (+`SubnetAlphaOut`), then `do_dissolve_network` later distributes the `SubnetTAO` pot pro-rata — unlike shorts, which pay TAO equity directly from custody.
- **Evidence:**
  - Long equity → `increase_stake_for_hotkey_and_coldkey_on_subnet` + `SubnetAlphaOut`; `destroy_alpha_in_out_stakes` runs after and distributes the pot pro-rata by alpha value. Shorts attempt direct `transfer_tao`.
  - Test `long_dereg_collects_max_spot_over_stale_high_ema` asserts only the stake-credit delta, never the final TAO through `destroy_alpha_in_out_stakes`.
- **Why it matters:** The terminal value-realization mechanism for longs differs materially from shorts and may dilute/under-realize the computed equity once the pot is distributed — an asymmetry not surfaced by any test.
- **Suggested fix:** Document the asymmetric terminal semantics, or settle long equity through a mechanism matching the intended TAO-equivalent value.
- **Consensus:** 1 reviewer (generalist-glm) — glm:generalist_2

#### 🟡 Per-block decay hook iterates all active derivative subnets without explicit bound or weight accounting
- **Category:** performance | **File:** `pallets/subtensor/src/derivatives/mod.rs` (`run_short_decay`/`run_long_decay`)
- **Severity:** medium | **Confidence:** high | **Status:** validated
- **Claim:** `run_short_decay`/`run_long_decay` `collect()` every active derivative subnet each block, but the active-subnet count is not separately bounded and `block_step` does not account a proportional hook weight.
- **Evidence:**
  - `ShortActiveSubnets::iter_keys().collect()` / `LongActiveSubnets` per block; both hooks called unconditionally from `block_step`. Bound is per-subnet cost (O(1)), not the number of subnets.
- **Why it matters:** Enabling derivatives across many subnets creates O(active-subnets) per-block work invisible to dispatch weights, risking block-time degradation.
- **Suggested fix:** Account hook weight, bound the active set, or process active subnets incrementally with a cursor.
- **Consensus:** 2 reviewers (generalist-glm, database) — merged glm:generalist_7, database_4

#### 🟡 Derivative extrinsics use placeholder weights without benchmarks
- **Category:** maintainability | **File:** `pallets/subtensor/src/macros/dispatches.rs`
- **Severity:** medium | **Confidence:** high | **Status:** validated
- **Claim:** New derivative dispatches use hardcoded `DbWeight::reads_writes` estimates despite performing transfers, reserve mutations, aggregate writes, swap-quote computation, and optional late-failure paths.
- **Evidence:**
  - `open_short` = `reads_writes(12,8)`, `top_up_short` = `reads_writes(5,4)`, admin setters = `reads_writes(0,1)` ignoring the pallet write path. PR body lists benchmarked weights as a follow-up.
- **Why it matters:** Underestimated weights let blocks include more derivative work than intended (consensus-timeout risk) and make load-bearing economic ops hard to reason about pre-launch.
- **Suggested fix:** Add `WeightInfo` implementations and benchmarks before enabling the feature.
- **Consensus:** 1 reviewer (generalist-claude) — claude:generalist_13

#### 🟡 Migration weight accounting miscounts per-subnet reads and writes
- **Category:** database | **File:** `pallets/subtensor/src/migrations/migrate_seed_alpha_in_moving_reserve.rs`
- **Severity:** medium | **Confidence:** high | **Status:** validated
- **Claim:** `migrate_seed_alpha_in_moving_reserve` charges `reads_writes(1,1)` per subnet unconditionally, though each iteration reads the iterator item *and* the moving-reserve entry (2 reads) and only writes when the reserve is zero.
- **Evidence:**
  - `for (netuid, ...) in SubnetAlphaIn::iter()` (per-item read) + `SubnetAlphaInMovingReserve::get` (read); insert only in the cold-entry branch; `weight += reads_writes(1,1)` outside the branch.
- **Why it matters:** Upgrade weight is inaccurate — over-counting writes for warm entries, under-counting reads — which can waste upgrade budget or mask real migration cost.
- **Suggested fix:** Charge two reads per subnet and add one write only when the insert branch executes.
- **Consensus:** 1 reviewer (database) — merged database_1, database_7

#### 🟡 Slippage guard behavior is untested
- **Category:** testing | **File:** `pallets/subtensor/src/tests/derivatives.rs`
- **Severity:** medium | **Confidence:** high | **Status:** validated
- **Claim:** Tests pass `None` for `limit_price` and never assert `SlippageExceeded` or `executable_price_ppb` edge behavior.
- **Evidence:**
  - No test asserts `SlippageExceeded` or passes `limit_price: Some(...)`; every derivative call uses `None`.
- **Why it matters:** The user's MEV/sandwich protection could be inverted, ineffective, or too strict with no regression failure.
- **Suggested fix:** Add tight-limit `assert_noop!` and loose-limit `assert_ok!` tests for open/close on both sides; unit-test `executable_price_ppb` edges.
- **Consensus:** 1 reviewer (tests) — tests_2

#### 🟡 Alpha-reserve EMA tick is not directly tested
- **Category:** testing | **File:** `pallets/subtensor/src/staking/stake_utils.rs` (`update_moving_price`)
- **Severity:** medium | **Confidence:** high | **Status:** validated
- **Claim:** Derivative tests directly insert `SubnetAlphaInMovingReserve` but never verify `update_moving_price` maintains the reserve EMA across blocks.
- **Evidence:**
  - Tests set the EMA directly in setup; no test steps blocks and asserts the reserve EMA moves/converges. The migration seeds the initial value, but the ongoing anti-manipulation primitive is the per-block tick.
- **Why it matters:** The core anti-manipulation reference can be mis-wired or frozen in production while math tests that seed the EMA manually still pass green — the highest "tests pass but production broken" risk in the suite.
- **Suggested fix:** Add an integration test: cold/warm A_EMA, step blocks, assert the EMA updates monotonically toward the live reserve with the expected smoothing.
- **Consensus:** 1 reviewer (tests) — tests_4

#### 🟡 Legacy-pool exact-output simulation falls back to 1:1 for terminal settlement
- **Category:** correctness | **File:** `pallets/swap/src/pallet/impls.rs` (`sim_tao_in_for_alpha_out`/`sim_alpha_in_for_tao_out`)
- **Severity:** medium | **Confidence:** medium | **Status:** plausible
- **Claim:** The exact-output sims return a 1:1 cost when `mechanism != 1`, while terminal derivative settlement does not re-check that positions are still on a dynamic subnet.
- **Evidence:**
  - Non-dynamic branch returns `Ok(alpha_out.to_u64().into())` / `Ok(tao_out.to_u64().into())`; `settle_shorts_on_dereg`/`settle_longs_on_dereg` iterate positions without checking `SubnetMechanism == 1`.
- **Why it matters:** If a position survives a dynamic→legacy mechanism transition, terminal cover/equity can be computed from a non-market 1:1 quote — potentially an unbacked payout.
- **Suggested fix:** Define settlement behavior for non-dynamic pools; avoid a silent 1:1 fallback for derivative liability valuation.
- **Consensus:** 1 reviewer (generalist-claude) — claude:generalist_8

#### 🟡 Dormant long-side implementation conflicts with shorts-first launch scope
- **Category:** maintainability | **File:** `pallets/subtensor/src/derivatives/long.rs`
- **Severity:** medium | **Confidence:** high | **Status:** validated
- **Claim:** The PR lands a full gated long-side engine, dispatch/API/storage surface, and tests while `DESIGN.md` states the launch scope is shorts-only and longs are not in the launch diff.
- **Evidence:**
  - `DESIGN.md` says launch scope is shorts only / longs not in the launch diff; `long.rs` implements the full lifecycle + read views; `dispatches.rs` exposes long extrinsics despite `LongsEnabled` defaulting false. Line-reduction estimate: ~-900 production LOC + tests.
- **Why it matters:** Disabled runtime code still expands storage/API compatibility, audit surface, and future maintenance burden before a launch requirement needs it; short-side fixes risk not propagating to the dormant mirror.
- **Suggested fix:** Defer executable long-side code/API/storage to a follow-up PR unless explicitly in scope for this launch.
- **Consensus:** 2 reviewers (maintainability, line-reduction) — merged maintainability_1, line_reduction_1

#### 🟡 Migration seeds all subnets in one upgrade block and lacks direct tests
- **Category:** testing | **File:** `pallets/subtensor/src/migrations/migrate_seed_alpha_in_moving_reserve.rs`
- **Severity:** medium | **Confidence:** medium | **Status:** plausible
- **Claim:** The migration iterates all `SubnetAlphaIn` entries in one `on_runtime_upgrade` pass, and its seeding/idempotency/skip behavior is not directly tested.
- **Evidence:**
  - `SubnetAlphaIn::iter()` with no pagination; `HasMigrationRun` guard + skip-nonzero branch both untested (grep found no test invoking the migration).
- **Why it matters:** The migration protects the reserve-EMA cold-start window; untested behavior or unexpectedly large iteration cost can undermine upgrade safety (empty seeding leaves every A_EMA at 0 → references fall back to the manipulable live reserve).
- **Suggested fix:** Add tests for seeded / already-warm / idempotent / large-N cases with returned `Weight` checked; consider a cursor/cap if subnet counts can approach block limits.
- **Consensus:** 2 reviewers (tests, database) — merged tests_3, database_2

#### 🔵 Partial close does not refresh default grace `last_active`
- **Category:** correctness | **File:** `pallets/subtensor/src/derivatives/mod.rs` (`do_close_short`/`do_close_long`)
- **Severity:** low | **Confidence:** high | **Status:** validated
- **Claim:** Partial-close paths reinsert positions without updating `last_active`, unlike open/merge and top-up.
- **Evidence:** `do_close_short` reinserts `pos` with no `last_active` update; `do_top_up_short` refreshes it; `do_default_short` checks `current_block >= last_active + ShortDefaultGrace`.
- **Why it matters:** A user action that reduces exposure does not renew the anti-snipe default-grace window — surprising, and can shorten the owner's expected response time before a permissionless default.
- **Suggested fix:** Set `last_active` to the current block when reinserting after a partial close.
- **Consensus:** 1 reviewer (generalist-glm) — glm:generalist_6

#### 🔵 Aggregate decay approximation can accumulate documented custody dust
- **Category:** correctness | **File:** `pallets/subtensor/src/derivatives/mod.rs` (`run_short_decay`/`materialize_short`)
- **Severity:** low | **Confidence:** medium | **Status:** plausible
- **Claim:** Aggregate decay uses per-block integer-floor multiplication while per-position materialization reconstructs `exp(-ΔΩ)`, creating rounding drift documented as safe but not tightly bounded by adversarial tests.
- **Evidence:** Module docs explicitly acknowledge the aggregate floors faster and residual dust is reclaimed at dereg.
- **Why it matters:** The design accepts the drift, but without tight worst-case bounds it can hide orphaned custody or under-restoration over long horizons and many positions.
- **Suggested fix:** Tighten tests/bounds, or compute aggregate decay using the same effective exponential factor.
- **Consensus:** 1 reviewer (generalist-claude) — claude:generalist_2

#### 🔵 A_EMA fixed-point saturation edge is not bounded or tested
- **Category:** correctness | **File:** `pallets/subtensor/src/derivatives/mod.rs` (`short_t_ref`/`long_a_ref`)
- **Severity:** low | **Confidence:** medium | **Status:** plausible
- **Claim:** `SubnetAlphaInMovingReserve` is stored as `U64F64` and read into `I64F64` via `saturating_from_num`; extreme reserves can silently clamp the anti-manipulation reference.
- **Evidence:** `short_t_ref`/`long_a_ref` convert with `saturating_from_num`; `update_moving_price` stores the EMA as `U64F64` (range exceeds `I64F64::MAX`).
- **Why it matters:** Silent saturation in the reference reserve can distort capacity and manipulation defenses at large reserve values (practical reachability needs further analysis).
- **Suggested fix:** Document reachable bounds, or use a representation/conversion that cannot silently clamp economically relevant reserves.
- **Consensus:** 2 reviewers (generalist-claude, security) — merged claude:generalist_11, security_3

#### 🔵 Decay runs before reserve EMA sampling, coupling derivative restoration into A_EMA
- **Category:** architecture | **File:** `pallets/subtensor/src/coinbase/block_step.rs` (`block_step`)
- **Severity:** low | **Confidence:** medium | **Status:** plausible
- **Claim:** `block_step` runs derivative decay before `update_moving_prices`, so long decay's Alpha restoration mutates `SubnetAlphaIn` before the same block samples `SubnetAlphaInMovingReserve`.
- **Evidence:** Order is `run_short_decay; run_long_decay; update_moving_prices`; `run_long_decay` increases the provided Alpha reserve; `short_t_ref`/`long_a_ref` rely on the lagged reserve EMA.
- **Why it matters:** Derivative open interest feeds the reserve EMA used to bound derivative capacity. May be intended, but the coupling is not analyzed in the design.
- **Suggested fix:** Document the ordering semantics, or sample the reserve EMA before derivative restoration if the reference should exclude derivative decay effects.
- **Consensus:** 1 reviewer (security) — security_6

#### 🔵 `BLOCKS_PER_DAY` is duplicated and decay-series precision is lightly documented
- **Category:** maintainability | **File:** `pallets/subtensor/src/derivatives/mod.rs` (`BLOCKS_PER_DAY`/`neg_ln_one_minus`)
- **Severity:** low | **Confidence:** high | **Status:** validated
- **Claim:** `BLOCKS_PER_DAY` is hardcoded separately in `mod.rs` and `long.rs`, and `neg_ln_one_minus` uses a 3-term Taylor series that must remain valid across configured decay bounds.
- **Evidence:** Two independent `BLOCKS_PER_DAY = 7200` definitions; `neg_ln_one_minus` uses three terms.
- **Why it matters:** A future one-sided constant update would desynchronize short and long decay rates; precision assumptions should stay tied to configured decay bounds.
- **Suggested fix:** Extract a shared constant and add a unit test bounding the approximation error over allowed decay values.
- **Consensus:** 1 reviewer (generalist-claude) — claude:generalist_12

#### 🔵 Normal cleanup leaves zero-valued position-count storage entries
- **Category:** database | **File:** `pallets/subtensor/src/derivatives/mod.rs` (`cleanup_short_if_empty`/`cleanup_long_if_empty`)
- **Severity:** low | **Confidence:** high | **Status:** validated
- **Claim:** `cleanup_*_if_empty` removes aggregates and active-set entries when counts reach zero but does not remove the count-map entries themselves; dereg settlement does remove them, so the normal path differs.
- **Evidence:** `cleanup_short_if_empty` removes `ShortAggregate` + `ShortActiveSubnets` only; `settle_shorts_on_dereg` explicitly `remove`s `ShortPositionCount`.
- **Why it matters:** Subnets that open then fully close all positions retain stale zero entries — avoidable trie/storage bloat over time.
- **Suggested fix:** Remove `ShortPositionCount`/`LongPositionCount` in `cleanup_*_if_empty` when the count is zero.
- **Consensus:** 1 reviewer (database) — database_9

#### 🔵 Short-close stake-lock rejection lacks a regression test
- **Category:** testing | **File:** `pallets/subtensor/src/tests/derivatives.rs`
- **Severity:** low | **Confidence:** high | **Status:** validated
- **Claim:** `do_close_short` calls `ensure_available_to_unstake` before consuming repayment alpha, but tests only cover the mirrored long-open stake-lock path.
- **Evidence:** `StakeUnavailable` appears only in `open_long_respects_stake_lock`; no short-close locked-alpha rejection test.
- **Why it matters:** A regression could let a short close consume locked stake and bypass the subnet-ownership lock policy without any test failure.
- **Suggested fix:** Mirror the long stake-lock regression test for short close.
- **Consensus:** 1 reviewer (tests) — tests_5

#### 🔵 Conservation tests use one-sided alpha bounds with loose tolerance
- **Category:** testing | **File:** `pallets/subtensor/src/tests/derivatives.rs`
- **Severity:** low | **Confidence:** high | **Status:** validated
- **Claim:** Headline conservation tests assert `alpha1 <= alpha0` (only catches minting) and tolerate alpha loss up to a loose tolerance, rather than a symmetric tight bound; TAO is asserted exactly.
- **Evidence:** `alpha1 <= alpha0` with `alpha0-alpha1 <= 1_000_000` (single) / `10_000_000` (multi); observed drift ~5e2 rao (tolerance ~2000×).
- **Why it matters:** Trader-under-crediting or alpha leakage below the loose tolerance passes the main proofs — a leak the exact-equality TAO assertion would have caught.
- **Suggested fix:** Use two-sided `abs(alpha1-alpha0) <= tight_epsilon` and document the exact rounding tolerance.
- **Consensus:** 1 reviewer (tests) — tests_6

#### 🔵 `keep_stake=true` hotkey-swap derivative behavior is untested
- **Category:** testing | **File:** `pallets/subtensor/src/tests/derivatives.rs`
- **Severity:** low | **Confidence:** high | **Status:** validated
- **Claim:** The derivative key-swap test covers `keep_stake=false`; no test asserts that `keep_stake=true` leaves derivative positions on the old hotkey.
- **Evidence:** `swap_positions_for_hotkey_swap` runs only in the `!keep_stake` branch; no `keep_stake=true` position assertion exists.
- **Why it matters:** A future regression could rehome positions without moving backing stake, stranding or breaking closes/defaults for every position during such a swap.
- **Suggested fix:** Add a `keep_stake=true` regression test asserting the position hotkey and closeability are unchanged.
- **Consensus:** 1 reviewer (tests) — tests_7

#### 🔵 Review-loop IDs leaked into test comments
- **Category:** maintainability | **File:** `pallets/subtensor/src/tests/derivatives.rs`
- **Severity:** low | **Confidence:** high | **Status:** validated
- **Claim:** Several derivative test comments reference internal review labels like `Fix (L3)`, `H1`, `M1`, `M4` rather than durable invariants.
- **Evidence:** Comments at lines 853, 877, 888, 1231, 1332, 1382 contain review-loop labels requiring external context.
- **Why it matters:** Internal review labels reduce maintainability and make tests harder for future auditors to understand (AI review-loop residue).
- **Suggested fix:** Rewrite comments to state the invariant being tested, without external labels.
- **Consensus:** 1 reviewer (ai-slop) — ai_slop_2

#### 🔵 Stale implementation plan duplicates and contradicts the implemented PR
- **Category:** documentation | **File:** `docs/derivatives/IMPLEMENTATION_PLAN.md`
- **Severity:** low | **Confidence:** high | **Status:** validated
- **Claim:** `IMPLEMENTATION_PLAN.md` is a pre-implementation plan with stale call indexes and file-layout references that no longer match the worktree.
- **Evidence:** The plan says "code is not written here" while the PR implements the feature; cited call indexes (139–142) and a `rpc_info/derivatives_info.rs` file don't match the actual `143–152` / module layout.
- **Why it matters:** Conflicting documentation forces future reviewers/operators to reconcile obsolete source-of-truth claims.
- **Suggested fix:** Delete the stale plan (~-180 LOC) or move only current acceptance criteria into `DESIGN.md`.
- **Consensus:** 1 reviewer (line-reduction) — line_reduction_2

#### 🔵 `SimSwapOpts` is a speculative one-field wrapper
- **Category:** maintainability | **File:** `primitives/swap-interface/src/lib.rs` (`SimSwapOpts`)
- **Severity:** low | **Confidence:** medium | **Status:** plausible
- **Claim:** `SimSwapOpts` currently wraps only `drop_fees` and is used solely to pass that boolean through the exact-output quote calls.
- **Evidence:** Swap impls immediately read `opts.drop_fees` and pass it to `gross_up_fee`; line-reduction estimate ~-20 LOC.
- **Why it matters:** The wrapper adds exported API surface for speculative future options without simplifying current callers.
- **Suggested fix:** Use a plain `drop_fees: bool` until a second simulation option actually exists.
- **Consensus:** 1 reviewer (line-reduction) — line_reduction_3

---

### Appendix

<details>
<summary>Uncertain findings (0)</summary>

None.

</details>

<details>
<summary>Rejected findings (2)</summary>

- **`kimi:generalist_1` — Partial close removes min-size positions while leaving aggregates nonzero** (`pallets/subtensor/src/derivatives/mod.rs:520`). *Rejection:* The code subtracts `p_close` before the removal check. If `p_close = 0`, `pos.p_floor` remains the original nonzero floor, so `pos.p_floor.is_zero()` is false and the position is **not** removed. The claimed min-size removal scenario is not supported by the code.
- **`claude:generalist_5` — `materialize_long` `checked_exp().unwrap_or(0)` risks total wipeout on large-negative arg** (`pallets/subtensor/src/derivatives/long.rs`). *Rejection:* The code clamps `arg <= 0`, and a large-negative exponent economically corresponds to decay toward zero (intended saturation-to-dust). The short-side code documents this intent; no reachable erroneous case was established.

</details>

<details>
<summary>Disagreements (2)</summary>

- **Slippage checks after mutations — transactional framing.** generalist-claude: correct *today* only if extrinsic transaction wrapping applies, but fragile and undocumented. generalist-openai / ai-slop: the dispatch wrappers are not `#[transactional]` and the repo uses explicit transactions elsewhere, so late errors can commit partial state. *(Adjudicated as HIGH `adj_1` — validated regardless of which framing holds, because the fix is the same: make the transaction boundary explicit.)*
- **Long self-cover `TotalStake`/TAO-neutral semantics.** generalist-claude: the asymmetry can be correct if `TotalStake` tracks TAO-in-pool and no TAO moves. generalist-kimi / security: the path records flow and settles by arithmetic/live quote without matching TAO reserve movement or success-path tests. *(Folded into `adj_8`.)*

</details>

<details>
<summary>Reviewer observations (5)</summary>

- Strong value-conservation coverage for standard lifecycles and good defensive `SubnetAlphaOut >=` guards before stake mint/burn (security).
- Gating is generally correct: opens check feature flags, dynamic subnet mechanism, min input, capacity, caps; setters are root-only; default grace resets on top-up (security).
- No reachable panic found in block hooks from the reviewed diff, but fuzzing extreme decay/reserve values is recommended (security).
- Many tests bypass real state transitions via direct storage setup — useful for math isolation but weaker for integration with staking/swap/coinbase state machines (tests).
- The migration is technically idempotent via `HasMigrationRun` + an inner `EMA==0` guard; post-migration newly-created subnets still cold-start by falling back to the live reserve (database).

</details>

---

### Review Metadata

- **Reviewers (10 first-pass + adjudicator):** 4 cold generalists across 4 provider families — `reviewer-generalist-kimi` (Kimi), `reviewer-generalist-glm` (GLM), `reviewer-generalist-claude` (Anthropic), `reviewer-generalist-openai` (OpenAI); + `reviewer-security`, `reviewer-maintainability`, `reviewer-tests`, AI-slop dispatch, line-reduction dispatch (supplemental), `reviewer-database` (adaptive — triggered by the storage migration); adjudicated by `reviewer-adjudicator` (OpenAI).
- **Profile:** full | **Run outcome:** full | **Degraded reason:** none
- **Note:** the kimi and glm generalist transcripts were truncated by output-size limits and recovered from saved transcripts; both yielded complete, parseable findings arrays and count as successful reviewers.
- **Method:** 61 raw first-pass findings → adjudicated to 30 (26 validated / 4 plausible via merge+dedup), 2 rejected, 0 uncertain. Every finding was evidence-verified against the PR head worktree.

