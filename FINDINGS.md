# Findings ledger

Status: **confirmed** (harness-proven) · **dormant** (real but precondition absent on live mainnet) · **in-progress** · **candidate** (unverified lead).
Keep this table current; detail lives in each batch dir. Severity per `METHODOLOGY.md` (impact × reachability, honest).

| ID | Title | Severity | Status | Live today? | Batch | Evidence |
|----|-------|----------|--------|-------------|-------|----------|
| F-01 | Self-cover close prices the liability on a different curve than open → pool drain under non-0.5 Balancer weights | MEDIUM | confirmed, **dormant** | No (finney all 0.5/0.5) | batch-01 | 7 harness PoCs + sims + live-weights probe + amplifier sweep |
| F-02 | Cold-EMA fresh-subnet window bypasses short and long capacity caps | MEDIUM | confirmed | No (pre-launch) | batch-02 | `poc_cold_ema_breaches_capacity_cap`; `long_open_cold_ema_live_alpha_bypasses_capacity_cap` |
| F-03 | Coldkey-swap destination collision can orphan short derivative aggregate state | MEDIUM | confirmed | No (pre-launch) | batch-04 | `coldkey_swap_collision_orphans_short_aggregate`; long mirror blocked by guard |
| F-04 | Short terminal settlement can pay identical positions different equity based on storage order | MEDIUM | confirmed | No (pre-launch) | batch-05 | `terminal_settlement_pays_identical_shorts_different_equity` |
| F-04b | **Long** terminal-settlement mirror — identical long positions settle to different equity (same root cause in `settle_longs_on_dereg`) | MEDIUM | **confirmed (batch-08)** | No (pre-launch) | batch-08 | `terminal_settlement_pays_identical_longs_different_equity` + `poc_long_terminal_settlement_order_dependent` (\|diff\| 8.34 α-TAO); two independent impls |
| F-06 | Unguarded terminal equity transfer in `settle_shorts_on_dereg` can silently burn a trader's payout when the destination coldkey is sub-ED (remainder then swept to issuance) | **LOW** | **confirmed (code, batch-08)** | No (pre-launch) | batch-08 | `let _ = transfer_tao(custody,coldkey,equity)` (mod.rs:769-772) unguarded + `recycle_custody_tao(custody, MAX)` (mod.rs:784); the escrow-restore credit (mod.rs:754-759) is `.is_ok()`-guarded by contrast |
| C-rollback | Non-transactional slippage rollback/atomicity | rejected for tested paths | no issue observed | n/a | local follow-up | `slippage_failure_rolls_back_state` passed |
| C-L2 | Emission-redirection: sustained short depresses a subnet's EMA price ⇒ cuts its price-based emission share | **LOW** (infeasible) | settled — mechanism real, uneconomical | No (shorts OFF) | batch-03 | `sim_l2_economics.py`: best-case redir/carry = 0.12–0.25 (κ cap bounds depression; carry 4–8× benefit) |
| C-L2b | Pruning sabotage: a sustained short tips a near-min subnet's pEMA below the field ⇒ redirects deregistration onto it | **LOW–MEDIUM** | **settled — confirmed, bounded** | No (shorts OFF) | batch-03 | `poc_pruning_sabotage_redirect` (redirect + immunity + bound) + `sim_l2b_pruning.py`: κ=0.05 caps depression ~9.75% ⇒ bottom-cluster only (target within ~10.8% of min); pure griefing; can't touch healthy subnets |
| C-xstate | Cold-EMA cross-state drain: open short at a pumped reserve / cash-settle at the restored reserve (F-02 escalation probe) | n/a — **DEFENDED** | settled — not a drain | No (shorts OFF) | batch-06 + batch-08 | `poc_cold_ema_cross_state_*`: gap `N1−K1` is real (≤ +33.5k TAO) but the pump round-trip cost strictly exceeds it at every size (ratio→1.0⁺); best net −0.001 TAO. **batch-08** broke & defended 3 un-reproduced regimes: amortized pump m∈{1,4,16} (best −0.826 TAO), regular in-kind close_short (best −0.0025 TAO), long-mirror cold-A_ref (best +3012 rao≈0) — `break_amortized_pump_short_self_close`, `break_regular_close_short_cross_state`, `break_long_mirror_cross_state` |
| C-atomicity | Non-transactional decay/dereg hooks (`run_*_decay` / `settle_*_on_dereg`): could a failed hook transfer desync custody vs obligations? | n/a — **DEFENDED** | settled — no desync | No (pre-launch) | batch-07 | longs use can't-fail mints; short pool credits are `.is_ok()`-guarded (only safe-direction bookkeeping advances unconditionally); custody ≥ Σ obligations holds adversarially — `poc_decay_drift_custody_solvency` drift +6,894 / +7,088 rao |
| D-chi-moot | Design: the derivatives' χ/`SubnetTaoFlow` flow-neutrality defends a DEAD channel (`get_shares_flow` uncalled); live emission is price-EMA based | informational | confirmed | n/a | batch-03 | `get_shares` calls only `get_shares_price_ema` |

## Severity rationale notes
- **F-01 MEDIUM:** high impact (theft of pooled funds) in active weighted-pool machinery that supports `w≠0.5`, but the
  precondition is absent on mainnet and is a *code change* away (user-LP permanently deprecated; emission proportional).
  Not LOW (impact high), not HIGH (no reachable trigger today). Escalates to HIGH if `w≠0.5` ever becomes reachable.
- **F-02 MEDIUM:** re-enables a defended attack class on fresh subnets, but pre-launch, fresh-subnet-scoped, and a
  *risk-limit bypass* (not a direct drain at the 0.5/0.5 baseline). The cross-state drain escalation (open at a pumped
  reserve / cash-settle at the restored reserve) was probed in **batch-06 and rejected**: the cold window genuinely
  inflates retained proceeds and yields a real `N1−K1` gap, but the staking round-trip that manufactures the price move
  costs strictly more than the gap at every size (ratio→1.0⁺) ⇒ F-02 does **not** escalate to HIGH.
- **F-03 MEDIUM:** breaks derivative storage/accounting invariants and can leave ghost short aggregate/custody state;
  direct value theft was not proven, and the feature is pre-launch.
- **F-04 MEDIUM:** terminal payout fairness/accounting issue; it can redistribute equity among derivative holders at
  deregistration, but is not proven as direct pool theft and is pre-launch.
- **F-04b MEDIUM:** the long mirror of F-04 (same `settle_longs_on_dereg` root cause — escrow restored into the pool
  before each position's own spot cover); value-conserving order-dependent equity, confirmed by two independent PoCs in
  batch-08. Same severity basis as F-04. F-05 (batch-08) notes both are force-reachable when the network is at
  `SubnetLimit`: `do_register_network` → `get_network_to_prune` → `do_dissolve_network` runs terminal settlement.
- **F-06 LOW:** narrow ED-edge reachability (a trader normally holds a funded coldkey — they posted `P` from it),
  dereg-gated, pre-launch, and no third-party profit or protocol insolvency — both adversarial verifiers in batch-08
  noted the unguarded transfer but declined to promote it above LOW.
- **Verification (batch-08):** an independent parallel round (2 blind auditors + 2 adversarial verifiers) upheld every
  finding above and every DEFENDED verdict, overturned none, and found no false positive; it strengthened F-01 dormancy
  (proportional emission is an exact fixed point at `w=0.5`; a seeded skew self-heals) and adopted F-04b + F-06.
