# Adversarial verification of covered-derivatives security report

Verifier worktree: `/data/xdg/data/opencode/worktree/1f8508c7675de8f25c263d8ddfe698b9cf27792b/verify-gpt`  
Target execution tree: `/projects/subtensor`  
Review corpus read: `REPORT.md`, `FINDINGS.md`, `METHODOLOGY.md`, all `CONTEXT/*`, all `batches/*/{finding,summary,brief}.md`, methodology journals, and `tooling/{sims,probes,poc}`.

## Bottom line

The report is mostly correct on the original six claims: F-01, F-02, F-03, F-04, L2a, and L2b all reproduce, and the three defended probes remain defended for the paths actually exercised.

However, the headline is **understated in scope**: F-04's terminal-settlement order-dependence is not short-only. I added and ran a local harness PoC showing the **long** terminal-settlement mirror pays identical long positions different equity. I would report this either as **F-04 broadened to both sides** or as a new **MEDIUM** mirror finding.

F-01 is a real conservation break under non-0.5 Balancer weights, but the report's final **dormant MEDIUM** framing is supported by live finney state: 128/128 probed `SwapBalancer` entries are at `w_quote ~= 0.5` and matching-side leak is 0% today.

## Per-finding verdict table

| ID | Claim | My verdict | Evidence | Notes |
|---|---|---|---|---|
| F-01 | Self-cover open/close pricing-curve asymmetry drains pool under non-0.5 weights; dormant on live mainnet | **UPHELD** as code defect; **MEDIUM/dormant** severity upheld | `cargo test -p pallet-subtensor --lib poc_ -- --nocapture`: six intentional F-01 failures printed extraction; `poc_baseline_no_skew_no_leak ... ok`; live probe: `N=128`, median/max leak `0.000%`, `128/128` within 0.001 of 0.5; source `pallets/subtensor/src/derivatives/mod.rs:289`, `pallets/subtensor/src/derivatives/mod.rs:324`, `pallets/subtensor/src/derivatives/mod.rs:544`, `pallets/swap/src/pallet/impls.rs:394`, `pallets/swap/src/pallet/balancer.rs:403` | The early batch's HIGH/CRITICAL language is over-severe for current reachability, but the final report corrected this. The forced emission-drift PoC demonstrates the defect if weights are driven off 0.5, not current live exploitability. |
| F-02 | Cold-EMA fresh-subnet short/long capacity cap bypass | **UPHELD**, MEDIUM | `poc_cold_ema_breaches_capacity_cap ... ok` printed `honest cap = 119 TAO -> pumped cap = 399 TAO`; `long_open_cold_ema_live_alpha_bypasses_capacity_cap ... ok`; source fallback at `pallets/subtensor/src/derivatives/mod.rs:136` and `pallets/subtensor/src/derivatives/long.rs:27`; migration seeds only existing entries at `pallets/subtensor/src/migrations/migrate_seed_alpha_in_moving_reserve.rs:34` | This is a risk-limit bypass, not a direct drain under tested 0.5/0.5 conditions. |
| F-03 | Coldkey-swap destination collision can orphan short aggregate | **UPHELD**, MEDIUM | `coldkey_swap_collision_orphans_short_aggregate ... ok`; `long_coldkey_swap_collision_is_blocked_by_staking_hotkey_guard ... ok`; source destination guard `pallets/subtensor/src/swap/swap_coldkey.rs:10`; collision drop path `pallets/subtensor/src/derivatives/mod.rs:1131` | Long mirror is currently blocked because long opens leave `StakingHotkeys(new_coldkey)` non-empty. |
| F-04 | Short terminal settlement pays identical positions different equity by storage order | **UPHELD, but scope UNDERSTATED** | Original short PoC printed `[TERMINAL-ORDER] first equity = 332745565022 rao, second equity = 277162020499 rao`; source short loop restores escrow before spot quote at `pallets/subtensor/src/derivatives/mod.rs:747` and `pallets/subtensor/src/derivatives/mod.rs:752`-`765` | I added a long mirror PoC; see new finding N-01 below. Severity remains MEDIUM, but affected surface is both short and long terminal settlement. |
| L2a | Emission skim via short-depressed price EMA is real but economically infeasible | **UPHELD**, LOW/infeasible | `sim_l2_economics.py`: redir/carry `0.117`-`0.246`; source emission share path `pallets/subtensor/src/coinbase/subnet_emissions.rs:354` -> `get_shares_price_ema` at `pallets/subtensor/src/coinbase/subnet_emissions.rs:395`; independent derivation: κ=0.05 gives max spot depression `9.75%`, carry/day `0.015*N`, carry exceeds best-case redirected emission 4-8x | Live `SubnetMovingAlpha` is `bits=1288490` (~3e-4), so the report's ~8h live half-life is plausible for established subnets. Code default is `0.000003` (`pallets/subtensor/src/lib.rs:1032`), which would make L2 even less feasible on a default-fresh deployment unless governance sets it higher. |
| L2b | Pruning sabotage can redirect pruning within bottom cluster, bounded by κ cap | **UPHELD**, LOW-MEDIUM | `poc_pruning_sabotage_redirect ... ok` printed baseline A, redirected B, healthy D still safe; `sim_l2b_pruning.py`: max depression `9.75%`, reach window `+10.80%`; source `get_network_to_prune` selects lowest non-immune pEMA at `pallets/subtensor/src/coinbase/root.rs:598` | Real griefing against near-min non-immune subnets; not profit, cannot reach healthy subnets under default κ. |
| C-xstate | Cold-EMA cross-state drain escalation is defended | **UPHELD for tested short self-close path** | `poc_cold_ema_cross_state_short_self_close_drain ... ok`; fine sweep best net `-0.001 TAO`; fee=0 best-case | I did not produce a profitable long mirror or regular-close variant. Fees and smaller/default κ only worsen the tested attacker. |
| C-atomicity | Non-transactional hook atomicity cannot desync custody vs obligations | **UPHELD** | `poc_decay_drift_custody_solvency ... ok`; drift `+6894` and `+7088` rao; source guard keeps value-creating pool credit inside successful transfer at `pallets/subtensor/src/derivatives/mod.rs:719`-`729` | Residual hardening is real: unguarded equity transfer at `pallets/subtensor/src/derivatives/mod.rs:769`-`771`, but I found no attacker-profit path. |
| C-rollback | Slippage failure rollback is safe | **UPHELD only for tested paths** | `slippage_failure_rolls_back_state`: `short_open_slippage_failure_rolls_back_state ... ok`, `long_self_close_slippage_failure_rolls_back_state ... ok` | The report should not imply every derivative slippage path is exhaustively proven. The two tested paths roll back cleanly; I found no extra exploit, but regular close/open-long self-contained rollback coverage is still thin. |
| D-chi-moot | χ/`SubnetTaoFlow` defends a dead emission channel | **UPHELD informational** | `get_shares` calls `get_shares_price_ema` at `pallets/subtensor/src/coinbase/subnet_emissions.rs:354`; `get_shares_flow` is present but not used in the live share path | Not a vulnerability by itself; relevant because L2a/L2b act through price EMA, not flow. |

## Reproduction commands and observed outputs

### Main PoC suite

Command:

```bash
. "$HOME/.cargo/env" && SKIP_WASM_BUILD=1 cargo test -p pallet-subtensor --lib poc_ -- --nocapture
```

Observed key output:

```text
running 12 tests
[POC-BASELINE] r=1.0 control: trader delta = 74110 rao (0.000074 TAO)
test tests::derivatives::poc_baseline_no_skew_no_leak ... ok
[COLD-EMA] honest cap = 119 TAO -> pumped cap = 399 TAO
test tests::derivatives::poc_cold_ema_breaches_capacity_cap ... ok
[PRUNE] baseline victim=Some(NetUid(1)) (A=NetUid(1)); C (min price, immune) protected
[PRUNE] after within-bound depression of B: victim=Some(NetUid(2)) (B=NetUid(2)) -> redirect
[PRUNE] D depressed by the MAX ~9.75% is still safe: victim=Some(NetUid(2)) (still B)
test tests::derivatives::poc_pruning_sabotage_redirect ... ok
[FINE] BEST net = -0.001 TAO at pump=100 P=1000
test tests::derivatives::poc_cold_ema_cross_state_fine_pump_sweep ... ok
[XSTATE] WORST-CASE attacker net = -2869 rao (-0.000 TAO)
test tests::derivatives::poc_cold_ema_cross_state_short_self_close_drain ... ok
[DRIFT] cfg=0 n=40 size=7x(1..11) custody=1759270654897 sum_claims=1759270648003 drift=6894 rao (0.000007 TAO)
[DRIFT] cfg=1 n=80 size=1x(1..3) custody=163634680780 sum_claims=163634673692 drift=7088 rao (0.000007 TAO)
test tests::derivatives::poc_decay_drift_custody_solvency ... ok
```

The six failures are intentional F-01 conservation assertions. Their printed deltas are the extraction proof, not a harness artifact:

```text
FINDING-01 LEAK: trader extracted 499127146400 rao (499.1271 TAO) from the pool via self-close under skewed weights, no price move
leak at near-default skew r=0.99: trader extracted 985233614927 rao
leak persists net of ~3% swap fee: trader extracted 483423118846 rao
FINDING-01 LONG LEAK: trader minted 499127146400 rao alpha via long self-close under skewed weights
sustained drain: attacker netted 2499571858469 rao over 5 round-trips with no price move
leak after emission-driven drift (no skew_pool): trader extracted 22394454688998 rao
test result: FAILED. 6 passed; 6 failed; 0 ignored; 0 measured; 1297 filtered out
```

### Focused follow-up modules

Command:

```bash
. "$HOME/.cargo/env"; export SKIP_WASM_BUILD=1
cargo test -p pallet-subtensor --lib derivative_cold -- --nocapture
cargo test -p pallet-subtensor --lib coldkey_swap -- --nocapture
cargo test -p pallet-subtensor --lib terminal_settlement_pays_identical_shorts_different_equity -- --nocapture
cargo test -p pallet-subtensor --lib slippage_failure_rolls_back_state -- --nocapture
cargo test -p pallet-subtensor --lib engine_cover -- --nocapture
```

Observed key output:

```text
running 3 tests
test tests::derivative_cold_ema::long_open_cold_ema_live_alpha_bypasses_capacity_cap ... ok
test tests::derivative_coldkey_swap::coldkey_swap_collision_orphans_short_aggregate ... ok
test tests::derivative_coldkey_swap::long_coldkey_swap_collision_is_blocked_by_staking_hotkey_guard ... ok

running 35 tests
test tests::derivative_coldkey_swap::coldkey_swap_collision_orphans_short_aggregate ... ok
test tests::derivative_coldkey_swap::long_coldkey_swap_collision_is_blocked_by_staking_hotkey_guard ... ok
test tests::swap_coldkey::test_coldkey_swap_total ... ok

running 1 test
[TERMINAL-ORDER] first equity = 332745565022 rao, second equity = 277162020499 rao
test tests::derivative_terminal_settlement::terminal_settlement_pays_identical_shorts_different_equity ... ok

running 2 tests
test tests::derivative_rollback::short_open_slippage_failure_rolls_back_state ... ok
test tests::derivative_rollback::long_self_close_slippage_failure_rolls_back_state ... ok

running 3 tests
test tests::derivatives::engine_cover_diverges_from_naive_cpmm ... ok
test tests::derivatives::engine_cover_inverts_real_swap_long ... ok
test tests::derivatives::engine_cover_inverts_real_swap_short ... ok
```

### Residual defended-regression tests

Command:

```bash
. "$HOME/.cargo/env"; export SKIP_WASM_BUILD=1
cargo test -p pallet-subtensor --lib short_many_partial_closes_drain_cleanly -- --nocapture
cargo test -p pallet-subtensor --lib short_lifecycle_conserves_tao_under_weights_and_fee -- --nocapture
cargo test -p pallet-subtensor --lib proof_multi_position_decay_conserves -- --nocapture
cargo test -p pallet-subtensor --lib open_close_roundtrip_is_not_profitable -- --nocapture
cargo test -p pallet-subtensor --lib short_self_close_rejects_when_underwater -- --nocapture
```

Observed output: all five filters passed (`1 passed; 0 failed` each). This supports the defended status for partial-close dust, weighted in-kind close, multi-position decay, baseline roundtrip, and underwater self-close rejection.

### Live-state probes

Commands:

```bash
uv run --with substrate-interface python /projects/subtensor/security-review/tooling/probes/probe_mainnet_weights.py
uv run --with substrate-interface python /projects/subtensor/security-review/tooling/probes/probe_crosscheck.py
uv run --with substrate-interface python /projects/subtensor/security-review/tooling/probes/probe_emission_params.py
```

Observed key output:

```text
CONNECTED: wss://entrypoint-finney.opentensor.ai:443
balancer storage: [('Swap', 'SwapBalancer')]
got 128 subnet balancer entries
N=128 subnets
median |w_quote-0.5| = 0.0000  (0 = exactly balanced)
median leak = 0.000%  |  mean leak = 0.000%  |  max leak = 0.000%
subnets within 0.001 of 0.5 (≈ no leak): 128/128
subnets with leak >= 1%:  0/128
subnets with leak >= 5%:  0/128
```

Cross-check sample:

```text
connected; block: 8520842
 net            raw_quote  w_quote          SubnetTAO      SubnetAlphaIn        T/A  MovingPrice
   1   499999999837464543  0.50000     26227943133164   3016055871353909    0.00870 {'bits': 37496403}
  64   499999999979687502  0.50000    202793441973125   2691613095985235    0.07534 {'bits': 323913704}
 128   500000000000000000  0.50000      4702198646284   1218051507833378    0.00386 {'bits': 16639543}
subnets in sample with w_quote != 0.5: 0/12
```

Emission probe:

```text
connected; block: 8520842
subnets with price>0: 127 | Σprice=1.3876
 net   priceEMA   share%  emit TAO/day half-life(blk/d)
  64    0.07542   5.435%        195.67         None / ?
 120    0.05563   4.009%        144.33         None / ?
  51    0.05415   3.903%        140.50         None / ?
...
net  64: -50% EMA → share  5.435%→ 2.794% → ~   95.10 TAO/day redirected
lowest-priceEMA subnets (prune order, ignoring immunity): [(90, 0.00324), (27, 0.003284), (94, 0.003322), (72, 0.003328), (65, 0.003409)]
```

The report's probe did not print `EMAPriceHalvingBlocks`, so I queried it directly:

```text
block 8520854
SubnetMovingAlpha {'bits': 1288490}
EMAPriceHalvingBlocks 1 201600
EMAPriceHalvingBlocks 4 201600
EMAPriceHalvingBlocks 64 201600
EMAPriceHalvingBlocks 90 201600
EMAPriceHalvingBlocks 120 201600
```

`1288490 / 2^32 ~= 0.000300`, and with an established subnet age around 8.52M blocks this gives effective per-block alpha `~0.000293` and half-life `~2365` blocks (`~7.9h`). That supports the report's live-finney EMA timing. The source default `0.000003` would produce a much slower `~32.8d` half-life, so any non-finney deployment using defaults would make L2a/L2b less reachable, not more.

## Independent numerical re-derivation

I reran the report sims and a separate Decimal script.

Report sims:

```text
sim_baseline.py: max |K0-N|/N in real arithmetic = 3.90e-78; worst truncation residual = 0.67 rao; with fee P&L negative
sim_weighted_selfclose.py: r<1 short side leaks, r=1 safe, r>1 safe/underwater for short side
sim_weighted_v2_pricefixed.py: fixed price r=0.99, P=1,000 -> +9.4909 TAO after 0.05% fee; P=50,000 -> +443.3339 TAO after fee
sim_l2_economics.py: redir/carry = 0.117-0.246
sim_l2b_pruning.py: max_depr = 9.75%, reach window = +10.80%
```

Independent script outputs:

```text
F01 harness r=0.5 P=1000 N= 998.003990 K= 498.877307 profit= 499.126683 profit%P= 49.9127
F01 small r=0.99 P=100k/T=10M N= 98039.027186 K= 97053.799766 profit= 985.227420 profit%P= 0.9852
F01 fee r=0.5 P=1000 fee~2000/65535 N= 998.003990 K= 514.581322 profit= 483.422668 profit%P= 48.3423
L2 cap T 5000 N/T 0.047500 E/T 0.050000 depr% 9.7500 window% 10.8033 carry/day 3.5625
L2 cap T 26278 N/T 0.047500 E/T 0.050000 depr% 9.7500 window% 10.8033 carry/day 18.7231
L2 cap T 100000 N/T 0.047500 E/T 0.050000 depr% 9.7500 window% 10.8033 carry/day 71.2500
L2 cap T 203942 N/T 0.047500 E/T 0.050000 depr% 9.7500 window% 10.8033 carry/day 145.3087
EMA moving_alpha 0.0003 effective_alpha 0.0002930661715154932 half_blocks 2364.8092955221673 half_hours@12s 7.882697651740558
EMA moving_alpha 3e-06 effective_alpha 2.9306617151549324e-06 half_blocks 236515.24202732425 half_days 32.849339170461704
```

The F-01 and L2 numbers therefore hold independently. The most important severity limiter is not the math; it is reachability: live weights are 0.5/0.5 and derivatives are default-off.

## Source-level root-cause checks

### F-01

Short open is weight-unaware:

- `pallets/subtensor/src/derivatives/mod.rs:312` solves `C,N` from `t_ref` using `solve_collateral`.
- `pallets/subtensor/src/derivatives/mod.rs:324` solves `phi` from `N,t_live`.
- `pallets/subtensor/src/derivatives/mod.rs:326`-`329` stores `N`, `E=phi*T`, `Q=phi*A` with no Balancer weight.

Short self-close is weight-aware:

- `pallets/subtensor/src/derivatives/mod.rs:570` uses `short_spot_close_cost`.
- `pallets/subtensor/src/derivatives/mod.rs:793` calls `sim_tao_in_for_alpha_out`.
- `pallets/swap/src/pallet/impls.rs:394`-`410` routes to `SwapBalancer::get_quote_needed_for_base`.
- `pallets/swap/src/pallet/balancer.rs:403`-`415` computes weighted exact-output cost.

Long mirror has the same asymmetry:

- `pallets/subtensor/src/derivatives/long.rs:101`-`118` books `D=phi*T` from naive open math.
- `pallets/subtensor/src/derivatives/long.rs:320`-`323` and `pallets/subtensor/src/derivatives/long.rs:356`-`359` self-close via weighted exact-output cost.

I did not find a source guard that neutralizes this at non-0.5 weights. The live-state guard is external: weights are currently 0.5/0.5.

### F-02

The fallback is explicit:

- `pallets/subtensor/src/derivatives/mod.rs:136`-`148`: if `t_ema <= 0`, `short_t_ref` returns `t_live`.
- `pallets/subtensor/src/derivatives/long.rs:27`-`33`: if `a_ema <= 0`, `long_a_ref` returns `a_live`.
- `pallets/subtensor/src/staking/stake_utils.rs:37`-`83`: `update_moving_price` updates `SubnetMovingPrice` and `SubnetAlphaInMovingReserve` per block.
- `pallets/subtensor/src/migrations/migrate_seed_alpha_in_moving_reserve.rs:34`-`45`: the migration iterates existing `SubnetAlphaIn` entries; I found no analogous subnet-creation initialization.

No source guard blocks a fresh subnet from opening derivatives while cold; the PoCs confirm the bypass.

### F-03

Destination freshness checks only staking-hotkey association and hotkey identity:

- `pallets/subtensor/src/swap/swap_coldkey.rs:10`-`17` checks `StakingHotkeys(new_coldkey).is_empty()` and `!hotkey_account_exists(new_coldkey)`.
- `pallets/subtensor/src/swap/swap_coldkey.rs:26`-`32` calls derivative rekeying for every subnet.

Collision handling drops the source derivative position without aggregate repair:

- `pallets/subtensor/src/derivatives/mod.rs:1136`-`1141`: short source is taken; if destination exists, only `ShortPositionCount` is decremented.
- `pallets/subtensor/src/derivatives/mod.rs:1143`-`1148`: long has the same code shape, but the current coldkey-swap destination guard blocks the tested long collision.

No source guard checks derivative storage before accepting the destination coldkey.

### F-04 and new long mirror

Short terminal settlement mutates the pool inside the per-position loop before quoting the same position:

- `pallets/subtensor/src/derivatives/mod.rs:747` collects positions.
- `pallets/subtensor/src/derivatives/mod.rs:752`-`759` restores that position's escrow into the live TAO reserve.
- `pallets/subtensor/src/derivatives/mod.rs:761`-`768` quotes `k_spot` after the mutation and pays equity.

Long terminal settlement has the same order-dependent shape:

- `pallets/subtensor/src/derivatives/long.rs:497` collects positions.
- `pallets/subtensor/src/derivatives/long.rs:499`-`502` restores that position's Alpha escrow into the live reserve.
- `pallets/subtensor/src/derivatives/long.rs:504`-`519` quotes cover after the mutation and pays equity.

No snapshot or all-escrow-first phase exists on either side.

## Defended probes: break attempts and result

### Cross-state drain

The short self-close attack was tested under favorable attacker conditions: fee=0, high κ=0.9, large pump ranges, same block cold EMA. It still lost money:

```text
[FINE]    100   1000 ... short_leg 2.0 pump_loss 2.0 ratio 1.001 net -0.001
[FINE]  50000  10000 ... short_leg 4985.2 pump_loss 6076.4 ratio 1.219 net -1091.160
[FINE] BEST net = -0.001 TAO at pump=100 P=1000
[XSTATE] WORST-CASE attacker net = -2869 rao (-0.000 TAO)
```

I tried to overturn the framing by checking whether different parameters could improve the attacker. Lower/default κ constrains maximum open size; fee>0 worsens the pump/unpump and self-close path; the report's fee=0/high-κ sweep is therefore already more favorable than production defaults. I did not produce a profitable regular-close or long mirror harness. Given the source symmetry, those remain reasonable residuals for maintainers to regression-test, but not a demonstrated missed exploit.

### Hook atomicity

The value-creating short pool credit is guarded by successful transfer:

```rust
if !restore.is_zero()
    && let Some(subnet_account) = Self::get_subnet_account_id(netuid)
    && Self::transfer_tao(...).is_ok()
{
    Self::increase_provided_tao_reserve(netuid, restore);
    TotalStake::<T>::mutate(|t| *t = t.saturating_add(restore));
}
```

This is at `pallets/subtensor/src/derivatives/mod.rs:719`-`729`. The drift PoC stresses many staggered positions with max decay and observed custody over obligations by `+6894` and `+7088` rao. I did not find an insolvency path. The ignored equity transfer at `pallets/subtensor/src/derivatives/mod.rs:769`-`771` can burn a trader's own sub-ED/dust equity, but I did not find third-party profit or protocol insolvency.

### Slippage rollback

The existing rollback tests pass for:

- short open slippage failure;
- long self-close slippage failure.

I do **not** treat that as a complete proof for all derivative slippage paths because `ensure_price_at_least/at_most` is placed late in all open/close functions (`pallets/subtensor/src/derivatives/mod.rs:396`-`399`, `pallets/subtensor/src/derivatives/mod.rs:503`-`505`, `pallets/subtensor/src/derivatives/mod.rs:597`-`599`, `pallets/subtensor/src/derivatives/long.rs:183`-`185`, `pallets/subtensor/src/derivatives/long.rs:282`-`284`, `pallets/subtensor/src/derivatives/long.rs:379`-`381`). The tested paths rolled back; no exploit found; coverage should be extended.

## New finding / missed surface

### N-01 / F-04b — Long terminal settlement is also order-dependent (MEDIUM, pre-launch)

**Claim:** The report only confirmed short terminal-settlement order dependence. The long mirror has the same root cause and is harness-confirmed.

**Affected code:** `pallets/subtensor/src/derivatives/long.rs:494`-`519`.

**Root cause:** `settle_longs_on_dereg` restores each position's Alpha escrow into the live pool before quoting that same position's spot cover. Later positions quote against a pool mutated by earlier positions.

**Local PoC added:** `pallets/subtensor/src/tests/derivative_terminal_settlement.rs::terminal_settlement_pays_identical_longs_different_equity` in `/projects/subtensor`.

Command:

```bash
. "$HOME/.cargo/env" && SKIP_WASM_BUILD=1 cargo test -p pallet-subtensor --lib terminal_settlement_pays_identical_longs_different_equity -- --nocapture
```

Observed output:

```text
running 1 test
[TERMINAL-LONG-ORDER] first equity = 277162020499 rao, second equity = 332745565022 rao
test tests::derivative_terminal_settlement::terminal_settlement_pays_identical_longs_different_equity ... ok
test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 1312 filtered out
```

**Severity:** MEDIUM, same as F-04. This is not a new direct drain, but it is terminal-settlement fairness/accounting failure. The feature is pre-launch/default-off. Recommended fix is the same as F-04: quote every terminal position against a common reserve snapshot, or restore all terminal escrow before any per-position quote.

## Other missed-surface note not promoted to a finding

`executable_price_ppb` uses naive `T/A`, not Balancer-weighted price (`pallets/subtensor/src/derivatives/mod.rs:802`-`811`). This means caller slippage bounds are weight-unaware if weights ever leave 0.5. I did not promote this because live weights are 0.5/0.5 and the client/report say the client uses the same quantity, but it is another reason F-01's fix should make the open/close/limit-price model weight-consistent rather than merely clamping self-close.

## Verification caveats

- LSP diagnostics for the added Rust harness file failed with `Connection closed`; compilation via `cargo test` succeeded and is the effective verification for the Rust change.
- `/projects/subtensor` already had the report's PoC patches applied before this run. I added only the long terminal-settlement mirror test to that existing follow-up test module.
- I did not run a full `cargo test -p pallet-subtensor --lib` after adding the new test because the known F-01 PoCs intentionally fail under the broad `poc_` filter; focused filters compile and pass as listed above.
