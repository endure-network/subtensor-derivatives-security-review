# Findings ledger

Status: **confirmed** (harness-proven) · **dormant** (real but precondition absent on live mainnet) · **in-progress** · **candidate** (unverified lead).
Keep this table current; detail lives in each batch dir. Severity per `METHODOLOGY.md` (impact × reachability, honest).

| ID | Title | Severity | Status | Live today? | Batch | Evidence |
|----|-------|----------|--------|-------------|-------|----------|
| F-01 | Self-cover close prices the liability on a different curve than open → pool drain under non-0.5 Balancer weights | MEDIUM | confirmed, **dormant** | No (finney all 0.5/0.5) | batch-01 | 7 harness PoCs + sims + live-weights probe + amplifier sweep |
| F-02 | Cold-EMA fresh-subnet window bypasses short and long capacity caps | MEDIUM | confirmed | No (pre-launch) | batch-02 | `poc_cold_ema_breaches_capacity_cap`; `long_open_cold_ema_live_alpha_bypasses_capacity_cap`. **Review (batch-09) corroborates**: post-migration newly-created subnets still cold-start to the live reserve |
| F-03 | Coldkey-swap destination collision can orphan short derivative aggregate state | MEDIUM *(review: HIGH)* | confirmed | No (pre-launch) | batch-04 | `coldkey_swap_collision_orphans_short_aggregate`; long mirror blocked by guard. **Independent review (batch-09) corroborates, rates HIGH**: `cleanup_short_if_empty` may drop aggregate/active-set while a destination position still lives |
| F-04 | Short terminal settlement can pay identical positions different equity based on storage order | MEDIUM | confirmed | No (pre-launch) | batch-05 | `terminal_settlement_pays_identical_shorts_different_equity` |
| F-04b | **Long** terminal-settlement mirror — identical long positions settle to different equity (same root cause in `settle_longs_on_dereg`) | MEDIUM | **confirmed (batch-08)** | No (pre-launch) | batch-08 | `terminal_settlement_pays_identical_longs_different_equity` + `poc_long_terminal_settlement_order_dependent` (\|diff\| 8.34 α-TAO); two independent impls |
| F-06 | Unguarded terminal equity transfer in `settle_shorts_on_dereg` silently burns a trader's payout when the destination coldkey is sub-ED (remainder swept to issuance), **while `ShortTerminalSettled{equity}` is emitted regardless of transfer success** (off-chain reconciliation corruption) | **LOW→MEDIUM** | confirmed (code, batch-08/09) | No (pre-launch) | batch-08, batch-09 | `let _ = transfer_tao(...)` (mod.rs:769-772) unguarded + unconditional event (mod.rs:775-780) + `recycle_custody_tao(custody, MAX)` (mod.rs:784); escrow-restore credit (mod.rs:754-759) is `.is_ok()`-guarded by contrast. Independent review rates HIGH |
| F-07 | Unbounded terminal-settlement iteration under **fixed** dissolve weight — `settle_*_on_dereg` loops over ALL positions (cap ≤4096/side ⇒ ~8192) → block-weight / liveness DoS | **HIGH** | confirmed (code, batch-09) | No (pre-launch) | batch-09 | `iter_prefix(netuid).collect()` loop (mod.rs:747-748 / long.rs:497-499); caps `[1,4096]` (mod.rs:892, long.rs:555); FIXED `dissolve_network` weight `reads(6)/writes(31)` (dispatches.rs:1234-1236); composes with F-05 prune-forced settlement. 5-reviewer consensus |
| F-08 | Terminal settlement uses a **1:1 exact-output fallback** for non-dynamic pools — `sim_*_out` returns 1:1 when `mechanism≠1` and settlement never re-checks ⇒ a position surviving a dynamic→legacy transition gets non-market cover/equity (possible unbacked payout) | **MEDIUM** | confirmed (code, batch-09) | No (pre-launch) | batch-09 | `sim_tao_in_for_alpha_out`/`sim_alpha_in_for_tao_out` non-dynamic branch `Ok(x.to_u64())` (impls.rs:412-418, 440-446); `settle_*_on_dereg` don't gate on `SubnetMechanism==1` |
| F-09 | Long terminal equity realized as **Alpha stake** (`increase_stake` + `SubnetAlphaOut`) then distributed pro-rata by `destroy_alpha_in_out_stakes`, unlike shorts' direct-TAO custody payout — asymmetric realization can dilute/under-realize equity | **LOW–MEDIUM** | confirmed (code, batch-09) | No (pre-launch) | batch-09 | `settle_longs_on_dereg` (long.rs:519-523) alpha-stake credit vs shorts' `transfer_tao` (mod.rs:769-770); no test asserts final TAO through pro-rata destruction |
| F-10 | `limit_price` slippage guard compares the **fee-less raw** reserve spot (`executable_price_ppb = T·1e9/A`) while execution cost is fee+weight-aware ⇒ weaker MEV/sandwich protection than implied, even at 0.5/0.5 | **LOW** | confirmed (code, batch-09) | No (pre-launch) | batch-09 | `executable_price_ppb` raw ratio (mod.rs:804-811) vs `short_spot_close_cost` `SimSwapOpts::WITH_FEES` (mod.rs:794); promotes the batch-08 un-promoted note |
| C-rollback | Late slippage/limit checks after state mutations; no explicit `#[transactional]` | tested paths roll back (implicit extrinsic rollback); **hardening gap acknowledged** | No (pre-launch) | local + batch-09 | `slippage_failure_rolls_back_state` passes ⇒ current safety via FRAME extrinsic rollback; **independent review (5-reviewer HIGH)** flags the missing *explicit* transaction boundary as fragile/undocumented — we concur |
| C-L2 | Emission-redirection: sustained short depresses a subnet's EMA price ⇒ cuts its price-based emission share | **LOW** (infeasible) | settled — mechanism real, uneconomical | No (shorts OFF) | batch-03 | `sim_l2_economics.py`: best-case redir/carry = 0.12–0.25 (κ cap bounds depression; carry 4–8× benefit) |
| C-L2b | Pruning sabotage: a sustained short tips a near-min subnet's pEMA below the field ⇒ redirects deregistration onto it | **LOW–MEDIUM** | **settled — confirmed, bounded** | No (shorts OFF) | batch-03 | `poc_pruning_sabotage_redirect` (redirect + immunity + bound) + `sim_l2b_pruning.py`: κ=0.05 caps depression ~9.75% ⇒ bottom-cluster only (target within ~10.8% of min); pure griefing; can't touch healthy subnets |
| C-xstate | Cold-EMA cross-state drain: open short at a pumped reserve / cash-settle at the restored reserve (F-02 escalation probe) | n/a — **DEFENDED** | settled — not a drain | No (shorts OFF) | batch-06 + batch-08 | `poc_cold_ema_cross_state_*`: gap `N1−K1` is real (≤ +33.5k TAO) but the pump round-trip cost strictly exceeds it at every size (ratio→1.0⁺); best net −0.001 TAO. **batch-08** broke & defended 3 un-reproduced regimes: amortized pump m∈{1,4,16} (best −0.826 TAO), regular in-kind close_short (best −0.0025 TAO), long-mirror cold-A_ref (best +3012 rao≈0) — `break_amortized_pump_short_self_close`, `break_regular_close_short_cross_state`, `break_long_mirror_cross_state` |
| C-atomicity | Non-transactional decay/dereg hooks (`run_*_decay` / `settle_*_on_dereg`): could a failed hook transfer desync custody vs obligations? | **DEFENDED** (solvency) + accuracy edges noted | settled — no insolvency | No (pre-launch) | batch-07 + batch-09 | solvency holds: longs can't-fail mint, short credits `.is_ok()`-guarded, custody ≥ Σ obligations (`poc_decay_drift_custody_solvency` +6,894/+7,088 rao). **batch-09 (review) accuracy edges**: `run_short_decay` decrements aggregate *before* the restoration transfer (understates on failure); `recycle_custody_tao` decrements `TotalIssuance` *before* an unchecked `Exact` withdraw (non-balance failure could desync) — no theft, real hardening |
| D-chi-moot | χ/`SubnetTaoFlow` flow channel is DEAD for emissions (`get_shares`→`get_shares_price_ema` only; `get_shares_flow`/`get_ema_flow` are `#[allow(dead_code)]`/uncalled) — **but `DerivativeFlowFactor` defaults to `1.0`, so derivatives DO write `SubnetTaoFlow` (non-neutral) contra DESIGN.md**; inert only because readers are dead (latent — arms if the flow path is wired) | informational (latent) | confirmed (batch-03/09) | n/a (dead read path) | batch-03, batch-09 | reads dead (subnet_emissions.rs:135, 257); `DefaultDerivativeFlowFactor=1` (lib.rs:1457); review flags the default/doc mismatch |

## Severity rationale notes
- **F-01 MEDIUM:** high impact (theft of pooled funds) in active weighted-pool machinery that supports `w≠0.5`, but the
  precondition is absent on mainnet and is a *code change* away (user-LP permanently deprecated; emission proportional).
  Not LOW (impact high), not HIGH (no reachable trigger today). Escalates to HIGH if `w≠0.5` ever becomes reachable.
- **F-02 MEDIUM:** re-enables a defended attack class on fresh subnets, but pre-launch, fresh-subnet-scoped, and a
  *risk-limit bypass* (not a direct drain at the 0.5/0.5 baseline). The cross-state drain escalation (open at a pumped
  reserve / cash-settle at the restored reserve) was probed in **batch-06 and rejected**: the cold window genuinely
  inflates retained proceeds and yields a real `N1−K1` gap, but the staking round-trip that manufactures the price move
  costs strictly more than the gap at every size (ratio→1.0⁺) ⇒ F-02 does **not** escalate to HIGH.
- **F-03 MEDIUM (review HIGH):** breaks derivative storage/accounting invariants and can leave ghost short aggregate/custody
  state; direct value theft was not proven, and the feature is pre-launch. The independent code review rates it HIGH on
  the desync severity — the gap is our "no proven theft, pre-launch" discount vs their "silent value drop + inconsistent
  aggregate" framing; both agree the fix (reject-on-collision / settle+subtract) is required before launch.
- **F-04 MEDIUM:** terminal payout fairness/accounting issue; it can redistribute equity among derivative holders at
  deregistration, but is not proven as direct pool theft and is pre-launch.
- **F-04b MEDIUM:** the long mirror of F-04 (same `settle_longs_on_dereg` root cause — escrow restored into the pool
  before each position's own spot cover); value-conserving order-dependent equity, confirmed by two independent PoCs in
  batch-08. Same severity basis as F-04. F-05 (batch-08) notes both are force-reachable when the network is at
  `SubnetLimit`: `do_register_network` → `get_network_to_prune` → `do_dissolve_network` runs terminal settlement.
- **F-06 LOW→MEDIUM:** the burn itself is narrow (sub-ED destination coldkey, dereg-gated, pre-launch, no third-party
  profit), which is why batch-08 held it LOW; batch-09 (external review, rated HIGH by 3 reviewers incl. security) adds
  the load-bearing angle we missed — the `ShortTerminalSettled{equity}` event is emitted **regardless of transfer
  success**, so on-chain events assert a payment that did not happen and off-chain reconciliation is corrupted. That
  event-integrity dimension moves it off pure-LOW; we settle at LOW→MEDIUM (pre-launch keeps it below a firm MEDIUM).
- **F-07 HIGH:** liveness/DoS class (block-weight exhaustion on consensus-critical chain maintenance) — the highest-impact
  item in the ledger *if armed*. Mitigant: the caps are deliberately clamped to `[1,4096]`/side (the authors' own comment
  says "so governance can't lift the dereg-settlement" cost). Residual: the `dissolve_network` dispatch weight is a **fixed**
  `reads(6)/writes(31)` that does not scale with the up-to-~8192 per-position settlements, and the loop is unbounded; a
  pre-stuffed subnet forced through dissolution (incl. via the **F-05** prune path) can exceed the block's real budget.
  Pre-launch (shorts/longs OFF) + stuffing cost gate reachability, but this is a genuine weight-accounting gap. The PR body
  itself lists incremental settlement as a required follow-up.
- **F-08 MEDIUM:** the exact-output sim returns a non-market 1:1 quote for non-dynamic pools and terminal settlement never
  re-asserts `SubnetMechanism==1`; a position surviving a dynamic→legacy transition would value cover/equity off 1:1,
  risking an unbacked payout. Confidence medium (reachability of the mechanism transition with live positions needs
  further analysis); pre-launch.
- **F-09 LOW–MEDIUM:** longs realize equity as *minted Alpha stake* (a can't-fail mint — so F-06's burn does **not** apply
  to the long side) then subject it to pro-rata distribution at `destroy_alpha_in_out_stakes`, unlike shorts' direct-TAO
  payout; the asymmetry can dilute/under-realize the computed equity. Value-accounting fairness, not proven theft;
  pre-launch; no test asserts the final TAO-equivalent through the pot distribution.
- **F-10 LOW:** `limit_price` binds the fee-less raw reserve spot, not the fee+weight-aware realized cost, so the caller's
  MEV/sandwich bound is weaker than the parameter implies — even at 0.5/0.5 (the fee gap alone). Pre-launch; correctness /
  API-contract, no direct theft. Couples to F-01's fix (make the whole open/close/limit-price model weight- and
  fee-consistent).
- **Verification (batch-08):** an independent parallel round (2 blind auditors + 2 adversarial verifiers) upheld every
  finding above and every DEFENDED verdict, overturned none, and found no false positive; it strengthened F-01 dormancy
  (proportional emission is an exact fixed point at `w=0.5`; a seeded skew self-heals) and adopted F-04b + F-06.
- **External code review (batch-09):** a separate 10-reviewer + adjudicator full-PR code review (`.reviews/PR-2764-…`,
  archived in `batches/batch-09-external-review-reconciliation/`) independently corroborated F-02, F-03, F-06,
  `executable_price_ppb`, and the χ/flow-dead conclusion; it added the in-scope defects F-07–F-10 (all code-verified here)
  and a set of code-quality / testing / weight-benchmark / documentation findings that sit outside this report's
  economic/reachability scope but are relevant to the maintainers (see that batch's `finding.md`).
