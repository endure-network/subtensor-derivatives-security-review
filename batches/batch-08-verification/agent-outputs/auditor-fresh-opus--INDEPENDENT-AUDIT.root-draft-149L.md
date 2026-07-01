# Independent Audit: PR #2764 Derivative Surfaces

## Verdict

**PASS WITH FINDINGS for the pre-launch derivative code path.**

I found two reproducible issues in the covered short/long mechanics. Both are dormant for current production reachability because `ShortsEnabled` and `LongsEnabled` default to `false` and the user-provided mainnet fact is that the 128 finney pools currently use 0.5/0.5 Balancer weights. They are still release blockers before enabling derivatives on pools whose Balancer weights can diverge from 0.5/0.5, and before enabling shorts on fresh/cold-EMA subnets.

## Scope

- Target checkout: `/tmp/opencode/subtensor-hephaestus`
- Target commit: `1a7aa379e89b0d9b05b0ae0ca973e54dd753793b`
- Explicitly excluded: `/projects/subtensor/security-review`
- Primary files reviewed:
  - `pallets/subtensor/src/derivatives/mod.rs`
  - `pallets/subtensor/src/derivatives/long.rs`
  - `pallets/subtensor/src/macros/dispatches.rs`
  - `pallets/subtensor/src/lib.rs`
  - `pallets/subtensor/src/staking/stake_utils.rs`
  - `pallets/swap/src/pallet/impls.rs`
  - `pallets/swap/src/pallet/balancer.rs`
- Added PoC/defense harness:
  - `pallets/subtensor/src/tests/derivative_hephaestus.rs`
  - registered from `pallets/subtensor/src/tests/mod.rs`

## Commands

```bash
. "$HOME/.cargo/env" && SKIP_WASM_BUILD=1 cargo test -p pallet-subtensor --lib derivative_hephaestus -- --nocapture
```

Latest focused run passed with:

```text
6 passed; 0 failed; 0 ignored; 0 measured; 1291 filtered out
[poc_weight_skew] trader_delta=499127146400 rao, pool_delta=-499127146400 rao
[poc_weight_skew_long] stake_delta=499127146400 rao
```

## Findings

| Severity | Title | CWE | Exploitability | Impact | PoC | Minimal fix |
|---|---|---|---|---|---|---|
| Medium, pre-launch | CPMM derivative accounting can be round-tripped against skewed Balancer weights | CWE-682 | Requires derivatives enabled and a subnet whose Balancer weights are materially non-0.5/0.5 | Short self-close extracts TAO from pool; long self-close mints alpha stake/issuance | `poc_weight_skew_short_self_close_extracts_tao_from_pool`, `poc_weight_skew_long_self_close_extracts_alpha_issuance` | Use one pricing/invariant model for both open sizing and close cost, or reject derivative opens unless pool weights are exactly/safely near 0.5/0.5 |
| Low-to-Medium, pre-launch | Cold EMA fallback lets same-account stake injection enlarge short capacity on fresh subnets | CWE-841 | Requires shorts enabled on a fresh/cold-EMA dynamic subnet and capital to stake before opening | Capacity intended to be EMA-bounded can be bypassed in the cold window | `poc_fresh_cold_ema_add_stake_pump_bypasses_short_capacity` | Do not use live reserve as an unlimited cold fallback; seed/require warmed EMA or cap cold fallback to launch-time reserve |

## Finding Details

### 1. CPMM derivative accounting can be round-tripped against skewed Balancer weights

**Evidence**

- Short open sizing in `pallets/subtensor/src/derivatives/mod.rs:322` to `pallets/subtensor/src/derivatives/mod.rs:329` derives `phi`, `N`, `E`, and `Q` from live `SubnetTAO`/`SubnetAlphaIn` using the derivative-side `solve_phi` model.
- Short self-close in `pallets/subtensor/src/derivatives/mod.rs:568` to `pallets/subtensor/src/derivatives/mod.rs:571` charges the claim using `short_spot_close_cost`, which calls the swap interface quote.
- The swap quote is weight-aware: `pallets/swap/src/pallet/impls.rs:394` to `pallets/swap/src/pallet/impls.rs:410` uses `SwapBalancer::<T>::get(netuid).get_quote_needed_for_base(...)`.
- Balancer price and swap formulas explicitly depend on weights: `pallets/swap/src/pallet/balancer.rs:1` to `pallets/swap/src/pallet/balancer.rs:39`.
- Longs mirror the same mismatch: long open derives `D` through derivative-side sizing in `pallets/subtensor/src/derivatives/long.rs:111` to `pallets/subtensor/src/derivatives/long.rs:119`, while self-close uses a Balancer-weighted quote in `pallets/subtensor/src/derivatives/long.rs:356` to `pallets/subtensor/src/derivatives/long.rs:363` via `sim_alpha_in_for_tao_out` at `pallets/swap/src/pallet/impls.rs:422` to `pallets/swap/src/pallet/impls.rs:438`.

**Attack path**

1. Preconditions: derivatives are enabled, fees are low or the skew is large enough to exceed fees, and the target dynamic subnet has Balancer weights materially away from 0.5/0.5.
2. Open a short or long. The derivative open path sizes liability/collateral as if the pool is effectively equal-weight/CPMM.
3. Immediately self-close. The close path prices the liability through the actual Balancer weights.
4. When the two models disagree, the claim returned by self-close is larger than the position input even though no external price movement occurred.

**PoC**

`poc_weight_skew_short_self_close_extracts_tao_from_pool` initializes a 1,000,000 TAO / 1,000,000 alpha market with a Balancer price of 0.5, opens a 1,000 TAO short, then self-closes it. The observed result was:

```text
[poc_weight_skew] trader_delta=499127146400 rao, pool_delta=-499127146400 rao
```

That is about 499.127 TAO profit to the trader and the same loss from `SubnetTAO`.

`poc_weight_skew_long_self_close_extracts_alpha_issuance` initializes the mirror long case and observes:

```text
[poc_weight_skew_long] stake_delta=499127146400 rao
```

That is about 499.127 alpha stake minted/returned to the trader after an unchanged-price long round trip.

The control `defended_weight_balanced_short_self_close_does_not_materially_profit` sets the Balancer price to 1.0 on equal reserves and confirms the 0.5/0.5 case is near flat within 1 TAO.

**Severity rationale**

- Impact is direct reserve/issuance extraction once the preconditions hold.
- Current reachability is limited: `ShortsEnabled` and `LongsEnabled` default to `false` in `pallets/subtensor/src/lib.rs:1416` to `pallets/subtensor/src/lib.rs:1420` and are stored at `pallets/subtensor/src/lib.rs:1479` to `pallets/subtensor/src/lib.rs:1485`; the stated current mainnet pools are 0.5/0.5.
- Severity is therefore **Medium pre-launch**: not currently exploitable under the provided deployment facts, but unsafe to enable on skewable Balancer pools.

**Minimal fix**

Pick one invariant and use it consistently:

- Either size derivative open legs with the same Balancer-weighted math used for close quotes, or
- force derivative eligibility to pools whose Balancer weights are exactly, or governance-configurably near, 0.5/0.5 and fail opens outside that bound.

Add regression tests for both short and long round trips on intentionally skewed weights.

### 2. Cold EMA fallback lets same-account stake injection enlarge short capacity on fresh subnets

**Evidence**

- `short_t_ref` uses `T_ref = min(T_live, pEMA * A_EMA)` after warm-up, but if `t_ema <= 0`, it falls back to live `T_live`: `pallets/subtensor/src/derivatives/mod.rs:130` to `pallets/subtensor/src/derivatives/mod.rs:149`.
- Open-short capacity is enforced as `agg.b_sigma + B <= ShortKappa * T_ref`: `pallets/subtensor/src/derivatives/mod.rs:316` to `pallets/subtensor/src/derivatives/mod.rs:320`.
- The moving price getter returns the stored moving price for dynamic subnets: `pallets/subtensor/src/staking/stake_utils.rs:24` to `pallets/subtensor/src/staking/stake_utils.rs:35`. Fresh dynamic subnets can therefore have a zero moving price in tests until the EMA warms.
- EMA reserve updates happen once per block in `update_moving_price`: `pallets/subtensor/src/staking/stake_utils.rs:72` to `pallets/subtensor/src/staking/stake_utils.rs:83`, so the cold fallback is specifically the path that removes the lagged bound.

**Attack path**

1. Preconditions: shorts are enabled on a fresh dynamic subnet whose price/reserve EMA is cold (`get_moving_alpha_price(netuid) == 0`).
2. Attempting a large short is rejected under the current live reserve.
3. The same coldkey stakes a large amount into the subnet, increasing live reserves before opening the short.
4. Because `short_t_ref` falls back to `T_live` when the EMA product is zero, the increased live reserve immediately raises the capacity limit and the same short succeeds.

**PoC**

`poc_fresh_cold_ema_add_stake_pump_bypasses_short_capacity` creates a cold dynamic subnet, sets `ShortKappa` to 0.08, confirms a 200 TAO short is rejected with `ShortCapacityExceeded`, stakes 5,000 TAO into the subnet, then confirms the same 200 TAO short succeeds in the same cold-EMA state.

**Severity rationale**

- The impact is capacity bypass rather than direct immediate profit in this PoC.
- Reachability is restricted to fresh/cold-EMA subnets and dormant shorts.
- Severity is **Low-to-Medium pre-launch**. It becomes more important if derivatives can be enabled globally while new subnets are still in their cold-EMA period.

**Minimal fix**

Avoid an unlimited live-reserve fallback for short capacity:

- Seed `SubnetMovingPrice` and `SubnetAlphaInMovingReserve` at subnet creation/migration before derivatives can open, or
- disable derivative opens until the reserve EMA is warmed, or
- cap cold fallback at a launch-time reserve snapshot that cannot be raised by same-block/user staking.

Add a regression test that a cold-EMA stake pump cannot turn a `ShortCapacityExceeded` rejection into success.

## Downgraded or Rejected Candidates

| Candidate | Result | Reason |
|---|---|---|
| Slippage error after `open_short` mutates state leaks custody/pool state | Rejected | `defended_short_open_slippage_error_rolls_back_state` forces `SlippageExceeded` after the price-lowering open path and confirms no position, no custody balance, no trader balance loss, and zero aggregate liability remain. |
| Slippage error after `close_short_self` pays the trader leaks claim payment | Rejected | `defended_short_self_close_slippage_error_rolls_back_claim_payment` forces `SlippageExceeded` after close-side transfers and confirms the trader balance, custody balance, and stored position floor are unchanged. |
| 0.5/0.5 Balancer pools allow material short self-close profit | Rejected for equal weights | `defended_weight_balanced_short_self_close_does_not_materially_profit` confirms the equal-weight control is within 1 TAO. The confirmed extraction depends on skewed Balancer weights. |

## Residual Risk

- I did not inspect `/projects/subtensor/security-review` by instruction.
- The PoC harness directly initializes test Balancer weights to create skew. I did not prove an unprivileged mainnet path to skew a currently equal-weight pool; the finding is therefore calibrated as pre-launch / conditional on skewed weights.
- I focused on self-close, cold-EMA capacity, and slippage rollback. Other derivative surfaces such as deregistration settlement, default incentives, oracle/EMA governance settings, and terminal settlement scalability remain separate audit targets.
