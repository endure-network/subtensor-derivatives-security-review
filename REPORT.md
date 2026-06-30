# Security review — Bittensor covered continuous-unwind derivatives (subtensor PR #2764)

**Target:** `pallet-subtensor` covered short/long derivatives (`open_*`/`close_*`/`close_*_self`/`default_*`),
the EMA references (`short_t_ref`/`long_a_ref`), and the `pallet-subtensor-swap` Balancer engine, at PR #2764
head `1a7aa37` (`feat/pool-borrowing-spec`, base `devnet-ready`, open/unmerged as of 2026-06-29).
**Client under test:** `btcli` PR #1007 (`btcli deriv`).
**Status of feature:** shorts/longs are **default-OFF** (`ShortsEnabled`/`LongsEnabled`) and **not on mainnet** — this is a pre-launch review.

## Summary

| # | Finding | Severity | Live today? | Class |
|---|---------|----------|-------------|-------|
| 01 | Self-cover close prices the liability on a different curve than open ⇒ pool drain under non-0.5 Balancer weights | **MEDIUM** | No (all mainnet pools at 0.5/0.5) | Latent fund-loss / conservation break |
| 02 | Cold-EMA fresh-subnet window bypasses short and long capacity caps | **MEDIUM** | No (pre-launch) | Risk-limit bypass / hardening |
| 03 | Coldkey-swap destination collision can orphan short derivative aggregate state | **MEDIUM** | No (pre-launch) | Lifecycle/accounting integrity |
| 04 | Short terminal settlement can pay identical positions different equity based on storage order | **MEDIUM** | No (pre-launch) | Terminal-settlement fairness/accounting |

All four are **real, harness-confirmed code defects** in pre-launch derivative paths. They are currently
non-exploitable on mainnet because `ShortsEnabled`/`LongsEnabled` are default-off and the affected feature is not live,
but they should be fixed before any production enablement.

## Method

Code analysis → closed-form Python sims → **PoC tests in the project's own mock-runtime harness** (`cargo test
-p pallet-subtensor`, real pallet + real Balancer engine) → **live-mainnet state verification** (finney RPC) →
**in-flight-change (amplifier) sweep** (`gh`, recent PRs/releases). Every PoC runs against the real compiled code.

---

## FINDING-01 — Self-cover close / open pricing-curve asymmetry (MEDIUM, latent)

### Root cause
`do_open_short` ([mod.rs L289-409]) sizes the Alpha liability `Q` and escrow `E` with **weight-unaware
constant-product** math (`solve_phi(N, t_live)`, `Q = φ·a_live`, `E = φ·t_live`). `do_close_short_self`
([mod.rs L544-629]) prices the **buyback** of `Q` through the **weight-aware** Balancer engine
(`sim_tao_in_for_alpha_out` → `get_quote_needed_for_base = T·((A/(A−Q))^(w1/w2) − 1)`). The two legs price on
**different curves** whenever a pool's Balancer weights `w1/w2 ≠ 1` (i.e. ≠ 0.5/0.5). The long mirror is symmetric
(`do_open_long` books `D=φ·t_live` naive; `do_close_long_self` sells via the weighted engine).

### Impact
At a weight ratio `r = w1/w2`, an **open + immediate self-close at an unchanged price** returns `≈ P + N·(1−r)`
instead of `P` — the surplus `N·(1−r)` is drained directly from the subnet pool (i.e. from stakers). Short side
leaks at `r<1`; long side at `r>1` (so either drift direction is exploitable). Riskless, repeatable, capital-scaling.

### Proof — 7 PoCs in `pallets/subtensor/src/tests/derivatives.rs`
`SKIP_WASM_BUILD=1 cargo test -p pallet-subtensor --lib poc_ -- --nocapture`

| test | weight | result |
|------|--------|--------|
| `poc_baseline_no_skew_no_leak` | 0.5/0.5 | **+0.000074 TAO (control: no leak ⇒ skew is the cause)** |
| `poc_short_self_close_leaks_under_skewed_weights` | r=0.5 | +499.13 TAO (pool −499.13, issuance 0) |
| `poc_short_self_close_leaks_small_skew` | r=0.99 | +985.23 TAO on a 100k position (~1%/round-trip at 0.5% drift) |
| `poc_short_self_close_leaks_with_fee` | r=0.5, ~3% fee | +483.42 TAO (survives the fee) |
| `poc_long_self_close_leaks_under_skewed_weights` | r=2.0 | +499.13 Alpha (mirror) |
| `poc_repeat_drain` | r=0.5, 5× | +2,499.57 TAO; `pool drained == attacker gained` to the rao |
| `poc_emission_drift_then_leak` | drift 0.5→0.52 via REAL `adjust_protocol_liquidity` | +22,394 TAO |

Closed-form model (`sim_weighted_v2_pricefixed.py`) matches the on-chain numbers to the decimal.

### Why it is currently DORMANT (live-state verification)
A finney RPC probe of `Swap.SwapBalancer` for **all 128 subnets** returned **`w_quote = 0.5` (`w1/w2 = 1.0`)
everywhere** (max deviation ~1e-9; cross-checked: `MovingPrice == T/A`, the `w=0.5` signature). At 0.5/0.5 the
Balancer formula reduces to constant product and `K0 = N` exactly (the control PoC confirms +0.0 TAO). **The
precondition (`w≠0.5`) exists on zero mainnet subnets today**, so the live extraction is `$0`.

### Reachability (why it can't currently be armed)
The system **structurally pins weights at 0.5**: fresh pools seed reserves *at* the target price (`p=y/x ⇒ w=0.5`);
protocol emission injection is proportional (PR #2758 explicitly reserves any disproportionate excess rather than
shifting weights); and the user-liquidity extrinsics (`add_liquidity`/`remove_liquidity`/`modify_position`/
`toggle_user_liquidity`/`disable_lp`) are **permanently deprecated** `Err(Deprecated)` stubs (user-LP was
deliberately removed when Balancer was adopted, Feb–Mar 2026). The only non-0.5 source is the one-time v3→balancer
migration (price≠reserve ratio), and live finney reads 0.5 even there. **It is a code-change away, not a config flip.**

### Amplifier sweep (recent/in-flight changes)
No recent or in-flight change arms it. `cap exp_scaled at 1` (2026-06-26) is conditional on `dx≥0` (exact-input)
and does **not** touch the exact-output buyback (`dx<0`, uncapped). The new swap-size caps **mitigate**
(oversized self-cover ⇒ sim errors ⇒ rejected). Emission rework keeps weights at 0.5. No PR re-enables user-LP.

### Severity rationale: MEDIUM
High impact (direct theft of pooled funds) in **active** weighted-pool machinery that explicitly supports `w≠0.5`,
in a **pre-launch** feature → fix-before-enable. Not LOW (impact is high; machinery is live; even 0.5% drift ⇒ ~1%
leak). Not HIGH/CRITICAL (no currently-reachable trigger; real drift is ~1e-9 and non-accumulating). Escalates to
HIGH the instant anything re-enables disproportionate liquidity provision or a disproportionate emission/init mode.

### Recommended fix
Make the OPEN weight-aware: derive `Q`/`E`/`φ` through the **same** swap engine the self-cover close uses, so
`K = N` holds at any weight (open and close on one curve). Alternatives: price the self-cover buyback on the open's
naive curve; or reject/clamp self-cover when `|w−0.5|` exceeds an epsilon. Add a conservation regression test for
the `close_*_self` path under skewed weights (the existing weighted-conservation test covers only the in-kind close).

---

## FINDING-02 — Cold-EMA fresh-subnet capacity-cap bypass (MEDIUM, hardening)

### Root cause
`SubnetAlphaInMovingReserve` (the block-lagged `A_EMA` that the T_ref/A_ref manipulation-resistance relies on) is written
in only two places: a one-time migration that seeds **existing** subnets, and the per-block `update_moving_price`
tick. **There is no initialization at subnet creation.** So a freshly-created dynamic subnet has `A_EMA = 0` and
`pEMA = 0` until its EMA warms, and `short_t_ref = min(t_live, pEMA·A_EMA)` ([mod.rs L136-149]) falls back to the
**live, in-block-manipulable** reserve. `long_a_ref` mirrors this with the live Alpha reserve. The crossover/sandwich manipulation-resistance
tests all use a *warm* EMA; the only cold-EMA test (`small_open_on_fresh_subnet_with_cold_ema`) asserts merely that a
small open succeeds, with no bound.

### Impact
During the warmup window an attacker can pump the relevant live reserve in-block to inflate `T_ref`/`A_ref`, inflating
the capacity cap and retained proceeds, and open shorts or longs **beyond the intended risk limit** on a fresh subnet.

### Proof
```
honest cap = 119 TAO -> pumped cap = 399 TAO ; the over-cap open rejected at the honest reserve SUCCEEDS after pump
long_open_cold_ema_live_alpha_bypasses_capacity_cap ... ok
```
This is exactly the sandwich `sandwich_open_cannot_breach_capacity_cap` proves IMPOSSIBLE on a warm subnet.

### Severity rationale: MEDIUM (hardening)
It re-enables a known attack class the authors explicitly defend for warm subnets, but it is **pre-launch**,
**fresh-subnet-scoped** (only during EMA warmup, before the subnet starts emitting), and it is a **risk-limit
bypass, not a direct drain** — at the live 0.5/0.5 baseline `K0=N`, so an oversized cold-window position still
returns ~`P` on self-close (no minting). **Cross-state escalation — settled (batch-06), not a drain:** opening at an
in-block-pumped reserve and cash-settling at the restored reserve yields a *real* `N1−K1` gap (up to +33.5k TAO in the
PoC), but the staking round-trip (`add_stake`/`remove_stake`) that manufactures the price move costs strictly more than
the gap at every size (`pump_loss/short_leg → 1.0⁺`; best net −0.001 TAO). So F-02 stays MEDIUM and does **not**
escalate to direct theft. PoC: `poc_cold_ema_cross_state_short_self_close_drain`, `poc_cold_ema_cross_state_fine_pump_sweep`.

### Recommended fix
Seed `SubnetAlphaInMovingReserve` (and the price EMA) at **subnet creation**, mirroring the migration's seeding for
existing subnets; or make the cold-EMA fallback conservative (reject derivative opens until the EMA warms, or use a
floor reference) instead of falling back to the live reserve.

---

## FINDING-03 — Coldkey-swap derivative aggregate orphaning (MEDIUM, pre-launch)

### Root cause
`do_swap_coldkey` treats a destination coldkey as fresh if `StakingHotkeys(new_coldkey)` is empty and the destination
is not itself a hotkey. A coldkey can still hold a short derivative position without staking hotkeys. During rekeying,
`swap_positions_for_coldkey_swap` drops the source short position when the destination already has a short position,
and only decrements `ShortPositionCount`; it does not settle the dropped position or subtract it from `ShortAggregate`.

### Impact
After the swap, position storage/count report one live position while aggregate open interest/footprint still include
the dropped position. The resulting ghost aggregate/custody state is no longer reachable through normal close/default
paths. Direct theft was not proven; the issue is storage/accounting integrity and potential capacity/settlement griefing.

### Proof
`SKIP_WASM_BUILD=1 cargo test -p pallet-subtensor coldkey_swap -- --nocapture`

The focused test `coldkey_swap_collision_orphans_short_aggregate` passes by showing `ShortAggregate.q_sigma` remains
greater than the sum of live `ShortPositions` after a source/destination collision. The long-side mirror was tested and
is currently blocked by `ColdKeyAlreadyAssociated` because `StakingHotkeys(new_coldkey)` remains non-empty after a long
open.

### Recommended fix
Reject coldkey swaps when the destination already has a short derivative position on any subnet where the source also
has a short position, or merge/settle the source position with full aggregate/custody/flow accounting.

---

## FINDING-04 — Short terminal settlement order dependence (MEDIUM, pre-launch)

### Root cause
`settle_shorts_on_dereg` restores each position's escrow to the live subnet reserve immediately before quoting that
same position's spot cover cost. Because settlement iterates positions sequentially, later positions quote against a
pool already mutated by earlier positions' escrow restoration. Identical positions can receive different terminal
equity solely because of storage iteration order.

### Impact
Terminal payout fairness depends on coldkey/storage order rather than position economics. Splitting exposure across
coldkeys may not be equivalent to a single equivalent exposure. This is not proven as direct pool theft; it is a
terminal-settlement fairness/accounting bug.

### Proof
`SKIP_WASM_BUILD=1 cargo test -p pallet-subtensor terminal_settlement_pays_identical_shorts_different_equity -- --nocapture`

Observed local output:
```text
[TERMINAL-ORDER] first equity = 332745565022 rao, second equity = 277162020499 rao
```

### Recommended fix
Quote every terminal position against a common reserve snapshot, or restore all escrow/aggregate terminal pool state
before any per-position quote. Add regression checks that identical positions settle equally and that split-vs-merged
exposure is equivalent within rounding tolerance.

---

## Reproduction

```bash
# toolchain (HOME is non-persistent in this sandbox; the target/ cache under /projects persists)
. "$HOME/.cargo/env" 2>/dev/null || curl --proto '=https' -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain none
cd /projects/subtensor && export SKIP_WASM_BUILD=1
git apply security-review/tooling/poc/derivatives-poc.patch
git apply security-review/tooling/poc/followup-derivative-modules.patch
# FINDING-01 (intentional invariant failures proving extraction) + FINDING-02 short PoC:
cargo test -p pallet-subtensor --lib poc_ -- --nocapture
# FINDING-01 quote-engine control:
cargo test -p pallet-subtensor --lib engine_cover -- --nocapture
# FINDING-02 long mirror, FINDING-03, FINDING-04:
cargo test -p pallet-subtensor --lib derivative_cold -- --nocapture
cargo test -p pallet-subtensor --lib coldkey_swap -- --nocapture
cargo test -p pallet-subtensor --lib terminal_settlement_pays_identical_shorts_different_equity -- --nocapture
# closed-form sims + live-weights probe:
python3 security-review/tooling/sims/sim_weighted_v2_pricefixed.py
uv run --with substrate-interface python security-review/tooling/probes/probe_mainnet_weights.py   # finney SwapBalancer weights
```
PoC tests: `poc_*` in `pallets/subtensor/src/tests/derivatives.rs`, plus focused modules from
`tooling/poc/followup-derivative-modules.patch`: `derivative_cold_ema.rs`, `derivative_coldkey_swap.rs`,
`derivative_rollback.rs`, and `derivative_terminal_settlement.rs`.

## Note for the program
These findings are currently non-exploitable on mainnet; we report them as **pre-launch hardening** with full,
transparent reachability analysis (harness PoCs proving the mechanism + live-state proof of current dormancy +
amplifier sweep). A strict current-exploitability rubric may score them LOW/informational; a pre-launch fund-handling
review scores them MEDIUM. We recommend fixing all confirmed issues before enabling shorts/longs.
