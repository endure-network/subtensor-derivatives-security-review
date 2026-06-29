# Findings ledger

Status: **confirmed** (harness-proven) · **dormant** (real but precondition absent on live mainnet) · **in-progress** · **candidate** (unverified lead).
Keep this table current; detail lives in each batch dir. Severity per `METHODOLOGY.md` (impact × reachability, honest).

| ID | Title | Severity | Status | Live today? | Batch | Evidence |
|----|-------|----------|--------|-------------|-------|----------|
| F-01 | Self-cover close prices the liability on a different curve than open → pool drain under non-0.5 Balancer weights | MEDIUM | confirmed, **dormant** | No (finney all 0.5/0.5) | batch-01 | 7 harness PoCs + sims + live-weights probe + amplifier sweep |
| F-02 | Cold-EMA fresh-subnet window bypasses the capacity cap | MEDIUM | confirmed | No (pre-launch) | batch-02 | `poc_cold_ema_breaches_capacity_cap` (cap 119→399) |
| F-02b | Cold-EMA long-side mirror | MEDIUM | in-progress (parallel agent) | No | batch-02 | `derivative_cold_ema.rs::long_open_cold_ema_live_alpha_bypasses_capacity_cap` (in worktree) |
| C-rollback | Non-transactional decay/dereg rollback/atomicity | candidate | in-progress (parallel agent) | ? | — | `derivative_rollback.rs` (in worktree) |
| C-L2 | Emission-redirection: sustained short depresses a subnet's EMA price ⇒ cuts its price-based emission share | LOW–MEDIUM (economics open) | mechanism confirmed; profitability TBD | No (shorts OFF) | batch-03 | `get_shares`→`get_shares_price_ema`; finney: −50% EMA ≈ 95 TAO/day; EMA half-life ~8h |
| C-L2b | Pruning sabotage: sustained short tips a near-min subnet's EMA below the prune threshold ⇒ force its deregistration | LOW–MEDIUM (cost-framed) | candidate | No (shorts OFF) | batch-03 | `get_network_to_prune` selects lowest `get_moving_alpha_price`; prune-min ≈ 0.0033 |
| D-chi-moot | Design: the derivatives' χ/`SubnetTaoFlow` flow-neutrality defends a DEAD channel (`get_shares_flow` uncalled); live emission is price-EMA based | informational | confirmed | n/a | batch-03 | `get_shares` calls only `get_shares_price_ema` |

## Severity rationale notes
- **F-01 MEDIUM:** high impact (theft of pooled funds) in active weighted-pool machinery that supports `w≠0.5`, but the
  precondition is absent on mainnet and is a *code change* away (user-LP permanently deprecated; emission proportional).
  Not LOW (impact high), not HIGH (no reachable trigger today). Escalates to HIGH if `w≠0.5` ever becomes reachable.
- **F-02 MEDIUM:** re-enables a defended attack class on fresh subnets, but pre-launch, fresh-subnet-scoped, and a
  *risk-limit bypass* (not a direct drain at the 0.5/0.5 baseline).
