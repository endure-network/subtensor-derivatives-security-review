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
| 02 | Cold-EMA fresh-subnet window bypasses the capacity cap (T_ref manipulation-resistance inactive during warmup) | **MEDIUM** | No (pre-launch) | Risk-limit bypass / hardening |

Both are **real, harness-confirmed code defects** that are currently **non-exploitable** due to operational state,
and both should be fixed **before** `ShortsEnabled`/`LongsEnabled` are turned on.

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
`SubnetAlphaInMovingReserve` (the block-lagged `A_EMA` that the T_ref manipulation-resistance relies on) is written
in only two places: a one-time migration that seeds **existing** subnets, and the per-block `update_moving_price`
tick. **There is no initialization at subnet creation.** So a freshly-created dynamic subnet has `A_EMA = 0` and
`pEMA = 0` until its EMA warms, and `short_t_ref = min(t_live, pEMA·A_EMA)` ([mod.rs L136-149]) falls back to the
**live, in-block-manipulable** reserve (`long_a_ref` mirrors this). The crossover/sandwich manipulation-resistance
tests all use a *warm* EMA; the only cold-EMA test (`small_open_on_fresh_subnet_with_cold_ema`) asserts merely that a
small open succeeds, with no bound.

### Impact
During the warmup window an attacker can pump the live reserve in-block to inflate `T_ref`, inflating the capacity
cap (`κ·T_ref`) and retained proceeds, and open shorts **beyond the intended risk limit** on a fresh subnet.

### Proof — `poc_cold_ema_breaches_capacity_cap`
```
honest cap = 119 TAO -> pumped cap = 399 TAO ; the over-cap open rejected at the honest reserve SUCCEEDS after pump
```
This is exactly the sandwich `sandwich_open_cannot_breach_capacity_cap` proves IMPOSSIBLE on a warm subnet.

### Severity rationale: MEDIUM (hardening)
It re-enables a known attack class the authors explicitly defend for warm subnets, but it is **pre-launch**,
**fresh-subnet-scoped** (only during EMA warmup, before the subnet starts emitting), and it is a **risk-limit
bypass, not a direct drain** — at the live 0.5/0.5 baseline `K0=N`, so an oversized cold-window position still
returns ~`P` on self-close (no minting). **Open follow-up:** whether the cold window composes into a cross-state
drain (open at a pumped reserve / close at the restored reserve) was not settled; the proven result is the cap bypass.

### Recommended fix
Seed `SubnetAlphaInMovingReserve` (and the price EMA) at **subnet creation**, mirroring the migration's seeding for
existing subnets; or make the cold-EMA fallback conservative (reject derivative opens until the EMA warms, or use a
floor reference) instead of falling back to the live reserve.

---

## Reproduction

```bash
# toolchain (HOME is non-persistent in this sandbox; the target/ cache under /projects persists)
. "$HOME/.cargo/env" 2>/dev/null || curl --proto '=https' -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain none
cd /projects/subtensor && export SKIP_WASM_BUILD=1
# FINDING-01 (7 PoCs) + FINDING-02 (1 PoC), all in pallets/subtensor/src/tests/derivatives.rs:
cargo test -p pallet-subtensor --lib poc_ -- --nocapture
# closed-form sims + live-weights probe:
python3 .omo/ultraresearch/20260629-120006/sim_weighted_v2_pricefixed.py
uv run --with substrate-interface python /tmp/probe_mainnet_weights.py   # finney SwapBalancer weights
```
PoC tests: `poc_*` in `pallets/subtensor/src/tests/derivatives.rs`. Sims + data: `.omo/ultraresearch/20260629-120006/`.

## Note for the program
Both findings are currently non-exploitable on mainnet; we report them as **pre-launch hardening** with full,
transparent reachability analysis (harness PoCs proving the mechanism + live-state proof of current dormancy +
amplifier sweep). A strict current-exploitability rubric may score them LOW/informational; a pre-launch fund-handling
review scores them MEDIUM. We recommend fixing both before enabling shorts/longs.
