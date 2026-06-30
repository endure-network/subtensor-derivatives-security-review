# Findings ledger

Status: **confirmed** (harness-proven) · **dormant** (real but precondition absent on live mainnet) · **in-progress** · **candidate** (unverified lead).
Keep this table current; detail lives in each batch dir. Severity per `METHODOLOGY.md` (impact × reachability, honest).

| ID | Title | Severity | Status | Live today? | Batch | Evidence |
|----|-------|----------|--------|-------------|-------|----------|
| F-01 | Self-cover close prices the liability on a different curve than open → pool drain under non-0.5 Balancer weights | MEDIUM | confirmed, **dormant** | No (finney all 0.5/0.5) | batch-01 | 7 harness PoCs + sims + live-weights probe + amplifier sweep |
| F-02 | Cold-EMA fresh-subnet window bypasses short and long capacity caps | MEDIUM | confirmed | No (pre-launch) | batch-02 | `poc_cold_ema_breaches_capacity_cap`; `long_open_cold_ema_live_alpha_bypasses_capacity_cap` |
| F-03 | Coldkey-swap destination collision can orphan short derivative aggregate state | MEDIUM | confirmed | No (pre-launch) | batch-04 | `coldkey_swap_collision_orphans_short_aggregate`; long mirror blocked by guard |
| F-04 | Short terminal settlement can pay identical positions different equity based on storage order | MEDIUM | confirmed | No (pre-launch) | batch-05 | `terminal_settlement_pays_identical_shorts_different_equity` |
| C-rollback | Non-transactional slippage rollback/atomicity | rejected for tested paths | no issue observed | n/a | local follow-up | `slippage_failure_rolls_back_state` passed |
| C-L2 | Emission-redirection: sustained short depresses a subnet's EMA price ⇒ cuts its price-based emission share | **LOW** (infeasible) | settled — mechanism real, uneconomical | No (shorts OFF) | batch-03 | `sim_l2_economics.py`: best-case redir/carry = 0.12–0.25 (κ cap bounds depression; carry 4–8× benefit) |
| C-L2b | Pruning sabotage: sustained short tips a near-min subnet's EMA below the prune threshold ⇒ force its deregistration | LOW–MEDIUM (cost-framed) | candidate | No (shorts OFF) | batch-03 | `get_network_to_prune` selects lowest `get_moving_alpha_price`; prune-min ≈ 0.0033 |
| D-chi-moot | Design: the derivatives' χ/`SubnetTaoFlow` flow-neutrality defends a DEAD channel (`get_shares_flow` uncalled); live emission is price-EMA based | informational | confirmed | n/a | batch-03 | `get_shares` calls only `get_shares_price_ema` |

## Severity rationale notes
- **F-01 MEDIUM:** high impact (theft of pooled funds) in active weighted-pool machinery that supports `w≠0.5`, but the
  precondition is absent on mainnet and is a *code change* away (user-LP permanently deprecated; emission proportional).
  Not LOW (impact high), not HIGH (no reachable trigger today). Escalates to HIGH if `w≠0.5` ever becomes reachable.
- **F-02 MEDIUM:** re-enables a defended attack class on fresh subnets, but pre-launch, fresh-subnet-scoped, and a
  *risk-limit bypass* (not a direct drain at the 0.5/0.5 baseline).
- **F-03 MEDIUM:** breaks derivative storage/accounting invariants and can leave ghost short aggregate/custody state;
  direct value theft was not proven, and the feature is pre-launch.
- **F-04 MEDIUM:** terminal payout fairness/accounting issue; it can redistribute equity among derivative holders at
  deregistration, but is not proven as direct pool theft and is pre-launch.
