# batch-08 — Independent verification round (detail)

Consolidation of a 4-agent parallel verification pass. Reproduced locally 2026-07-01 on head `1a7aa37`
(`cargo 1.89`, `SKIP_WASM_BUILD=1`). Two substantive findings adopted (F-04b, F-06); everything else upheld.

## 1. F-04b — long terminal-settlement mirror (MEDIUM, adopted)

`settle_longs_on_dereg` ([long.rs:494-535]) restores each long position's Alpha escrow into the live reserve **before**
quoting that position's own `long_spot_close_cost`, so identical long positions settle to different terminal equity by
storage iteration order — the exact mirror of F-04 short (`settle_shorts_on_dereg`, [mod.rs:738-788]). Previously flagged
"investigate"; now confirmed by two independent implementations:

```
# fresh-opus (poc_long_terminal_settlement_order_dependent, positions seeded directly):
[F-04 long NEW]   identical longs -> equity(alpha) c1=49974809931 c2=41637278252 |diff|=8337531679 (8.3375 alpha-TAO)
# verify-gpt (terminal_settlement_pays_identical_longs_different_equity):
[TERMINAL-LONG-ORDER] first equity = 277162020499 rao, second equity = 332745565022 rao
```

Value is conserved (over-charged cover recycled/burned, escrow rejoins the pool, equity paid); this is a
fairness/accounting + non-determinism bug on both sides, not a drain. **Reachability (F-05):** terminal settlement is
force-reachable — at `SubnetLimit` (128), `do_register_network` → `get_network_to_prune` → `do_dissolve_network` runs
`settle_*_on_dereg`, so any party registering a subnet at capacity forces the lowest-price-EMA non-immune subnet through
settlement (the same target the L2b lever can bias). Fix: quote all terminal positions against one pre-restoration
snapshot, on **both** short and long paths.

Shipped PoC: `../../tooling/poc/verification-round.patch` (`poc_long_terminal_settlement_order_dependent`).

## 2. F-06 — unguarded terminal equity transfer (LOW, adopted)

In `settle_shorts_on_dereg` the equity payout is fire-and-forget:
```rust
if !equity.is_zero() { let _ = Self::transfer_tao(&custody, &coldkey, equity.into()); }   // mod.rs:769-772
...
Self::recycle_custody_tao(&custody, TaoBalance::MAX);                                       // mod.rs:784 (sweep to issuance)
```
No `.is_ok()` guard — unlike the escrow-restore credit at [mod.rs:754-759], which *is* guarded. If the transfer fails
(destination coldkey left below the existential deposit, or dust-empty), the equity is not paid **and** is then burned by
the MAX sweep — a silent loss of funds the trader was owed. Narrow reachability (a trader normally holds a funded
coldkey — they posted `P` from it), dereg-gated, pre-launch, no third-party profit; both adversarial verifiers noted the
path and declined to promote it above LOW. Fix: ED-safe transfer, or hold on failure in a claimable ledger.

## 3. Three cross-state regimes — positively DEFENDED

The report had left these "expected defended, not separately reproduced". Attacked (fee=0, κ=0.9, T0=A0=20k), all lose
money (`derivative_break_opus.rs`, reproduced 2026-07-01):

| regime | test | best attacker net |
|---|---|---|
| amortize one pump across `m∈{1,4,16}` short self-closes | `break_amortized_pump_short_self_close` | **−0.826 TAO** (more negative as `m` grows) |
| regular in-kind `close_short` (repay Q from pumped alpha) | `break_regular_close_short_cross_state` | **−0.0025 TAO** |
| long-mirror cold-`A_ref` cross-state | `break_long_mirror_cross_state` | **+3012 rao ≈ 0** (dust, both signs) |

Conservation reason: the gap requires moving the reserve between open and close; the AMM charges the convex round-trip
spread to create-and-revert that move, first-order-equal to the displacement value the derivative extracts.

## 4. F-01 dormancy — strengthened

`stability_realistic_emission_keeps_weight_pinned`: proportional protocol emission (`alpha_in = tao_in / price`) is an
**exact fixed point** at `w=0.5` (drift `0.00e0` over 200 injections); a seeded migration-style skew **self-heals**
(0.4500 → 0.4571 over 400 injections). Confirms at the code level — not only via the finney snapshot — that `w≠0.5` is a
code change away and self-correcting.

## 5. Un-promoted observation

`executable_price_ppb` uses naive `T/A` rather than the Balancer-weighted price ([mod.rs:802-811]) — inert at 0.5/0.5,
but caller slippage bounds would be weight-unaware if F-01 were ever armed. Another reason F-01's fix should make the
whole open/close/limit-price model weight-consistent, not merely clamp self-close.

## 6. Process note (→ METHODOLOGY)

The four agents shared one target checkout (`/projects/subtensor`), so their PoC files collided in the shared tree
(both opus agents wrote `derivative_break_opus.rs`; on-disk winner = fresh-opus's superset, verify-opus's archived here
as `verify-opus-break-harness.rs`). Each agent's work was preserved and the findings are unaffected, but future parallel
rounds must give each agent an isolated checkout. Captured in `../../METHODOLOGY.md`.
