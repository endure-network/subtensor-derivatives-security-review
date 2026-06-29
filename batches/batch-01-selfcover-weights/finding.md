# FINDING-01 — Self-cover close leaks value under Balancer weight skew (open=naive, close=weighted)

**Status:** ✅ CONFIRMED IN THE RUST HARNESS (real pallet + real Balancer engine). Model and on-chain
numbers agree to the decimal (sim_weighted_v2 r=0.5, P=1000 → 499.13 TAO; harness → 499.1271 TAO).
**Severity:** HIGH→CRITICAL — direct extraction of pooled TAO (stakers' funds). Gated only by how far
production Balancer weights deviate from 0.5/0.5 (the one quantity left to calibrate). Shorts are
default-OFF / pre-mainnet, so this is a pre-launch catch.

## HARNESS PROOF (definitive)
Test appended at `pallets/subtensor/src/tests/derivatives.rs::poc_short_self_close_leaks_under_skewed_weights`.
Repro: `SKIP_WASM_BUILD=1 cargo test -p pallet-subtensor --lib poc_short_self_close_leaks -- --nocapture`
```
setup_market(1_000_000 TAO, 1_000_000 TAO, price 1.0); skew_pool(netuid, 0.5, fee 0)  // w1/w2 = 0.5
open_short(P = 1_000 TAO);  do_close_short_self(fraction = 1e9)   // instant, no move, no decay
=> trader balance delta = +499.1271 TAO
=> SubnetTAO (pool)  delta = -499.1271 TAO    (pool drained to trader)
=> TotalIssuance delta = 0                     (pure redistribution stakers->attacker)
=> custody left = 0
ASSERT trader_delta <= 1 TAO  ==> FAILED (leak proven)
```
Profit law confirmed: ~N·(1−w1/w2). Repeatable, scales with capital. Long mirror leaks at w1/w2>1
(open books D=φ·T naive, close sells K'=sim_alpha_in_for_tao_out weighted) — pending its own PoC.
**Affected:** `do_close_short_self` (call 151) and `do_close_long_self` (call 152). The in-kind
`close_short`/`close_long` are NOT affected (they move real Alpha, conservation-tested).

## Mechanism
- **Open** ([mod.rs do_open_short L289-409], [long.rs do_open_long L79-196]) books the liability and
  escrow with **pure constant-product** math: `phi = solve_phi(N, T_live)` (no weights), `Q = phi·A_live`,
  `E = phi·T_live`, and removes `N+E` TAO from the pool via the direct reserve write.
- **Self-cover close** ([mod.rs do_close_short_self L544-629]) prices the buyback through the
  **weight-aware** swap engine: `K = short_spot_close_cost = sim_tao_in_for_alpha_out(...)` →
  `balancer.get_quote_needed_for_base = T'·((A/(A−Q))^(w1/w2) − 1)` (fee grossed up).
- At default weights w1=w2=0.5 the exponent is 1 ⇒ `K=N` (baseline covered, my sim_baseline.py).
  At **w1/w2 = r ≠ 1** the exponent ≠ 1 ⇒ `K ≈ r·N` ⇒ **profit = N − K ≈ N·(1−r)** on an
  open+instant self-close, **with no price movement and no decay**.

## Evidence (sim_weighted_v2_pricefixed.py — price held at 1.0, vary only weights)
| r=w1/w2 | w1 | leak (% of P) |
|--------|------|------|
| 1.00 | 0.500 | −0.05% (fee only) — baseline OK |
| 0.99 | 0.497 | **+0.95%** |
| 0.95 | 0.487 | **+4.95%** |
| 0.90 | 0.474 | **+9.94%** |
| 0.80 | 0.444 | **+19.9%** |
| 0.50 | 0.333 | **+49.9%** |
Scales with P (P=50,000 → ~4,657 TAO at r=0.9). Short leaks at r<1; **long mirror leaks at r>1**
(open books `D=φ·T` naive, close sells `K'=sim_alpha_in_for_tao_out` weighted) — so either drift
direction is exploitable on the matching side. NOT blocked by the underwater guard (K<N<P+N).

## Why the test suite misses it
`short_lifecycle_conserves_tao_under_weights_and_fee` (L2044) skews the pool (price 1.4) but closes
**in-kind** (`close_short`), explicitly noting "no engine fee leaks on this path". `engine_cover_inverts_
real_swap_short` (L1833) only checks K inverts the swap at r=1.6 (the SAFE/overcharge side). There is
**no test** that open + `close_short_self` conserves under weights, and none at r<1 (the leak side).

## Root-cause hypothesis
Likely introduced when the close cost was moved to the swap engine (commit `e919c37` "quote close cost
through the swap engine" / `77007ee` SimSwapOpts) without making the OPEN's `solve_phi`/`Q`/`E`
weight-aware. The two legs now price on different curves.

## Open questions before declaring exploit-grade
1. **Reachability of r≠1.** Pools init at 0.5/0.5; `update_weights_for_added_liquidity` shifts weights on
   disproportionate emission injection ("won't get far from 0.5" — unquantified). Even r=0.99 ⇒ 1% leak.
   Can an attacker *induce* drift (user liquidity provision / disproportionate add) to set up r<1? → check.
2. **Definitive confirmation** in the Rust harness (gold standard):
   ```
   skew_pool(netuid, 0.6, fee);            // r = w1/w2 < 1
   open_short(P); let i0 = TotalIssuance;
   close_short_self(1e9);                   // full cash-settled close, no move
   assert_eq!(TotalIssuance, i0);           // EXPECT: fails — trader minted ~N*(1-r)
   ```
   (mirror: setup_long + skew_pool(price>1) + close_long_self.)

## All three PoCs CONFIRMED (real pallet + real Balancer engine)
`pallets/subtensor/src/tests/derivatives.rs`: `poc_short_self_close_leaks_under_skewed_weights`,
`poc_short_self_close_leaks_small_skew`, `poc_long_self_close_leaks_under_skewed_weights`.
Repro: `SKIP_WASM_BUILD=1 cargo test -p pallet-subtensor --lib poc_ -- --nocapture`
| PoC | skew (w1/w2) | size | extracted (no move/decay) |
|-----|------|------|------|
| short | 0.5  | 1,000 TAO   | +499.13 TAO (pool −499.13, issuance 0) |
| short | **0.99** | 100,000 TAO | **+985.23 TAO** (~1%/round-trip at 0.5% drift) |
| long  | 2.0  | 1,000 Alpha | +499.13 Alpha (mirror, opposite skew) |

## Severity conclusion
HIGH→CRITICAL. Direct, riskless extraction of pooled TAO/Alpha (stakers' funds) at ANY weight
deviation from 0.5/0.5, either drift direction (short r<1 / long r>1), repeatable, capital-scaling.
Even a 0.5% deviation yields ~1% per round-trip. Pools init at 0.5/0.5 and drift via emission
injection (`update_weights_for_added_liquidity`). Shorts/longs default-OFF / pre-mainnet ⇒ pre-launch catch.

## Fix direction
Make the OPEN weight-aware: size `Q`/`E` and the `φ` solve through the SAME swap engine the close uses,
so `K=N` holds under any weights (open and close price on one curve). Alternatives: price the self-cover
buyback on the open's naive curve (worse), or reject/clamp self-cover when |w−0.5| exceeds an epsilon.

## Severity calibration — what moves the weights (checked)
`update_weights_for_added_liquidity` has ONE non-test caller: `adjust_protocol_liquidity`
(swap/src/pallet/impls.rs:84) — the PROTOCOL emission-injection path. The user `add_liquidity`
extrinsic (call_index 1) does NOT skew weights (proportional add; balancer.rs comment: "we only allow
the protocol to inject disproportionally"). ⇒ skew accumulates from emission drift over time, NOT a
single attacker call. So the EASY path is HIGH (any drifted pool is exploitable, 0.5% drift→~1%/round-trip);
escalates to CRITICAL only if (a) production pools drift materially (likely over a subnet's life), or
(b) a multi-block attack that nudges reserves right before each emission injection can AMPLIFY the
weight drift (UNVERIFIED — next investigation). Either way: unambiguous pre-launch bug; fix before enabling.

## RE-VERIFICATION — 7 harness PoCs (all consistent), task (A) complete
`SKIP_WASM_BUILD=1 cargo test -p pallet-subtensor --lib poc_ -- --nocapture` (toolchain: rustup 1.89;
re-source `~/.cargo/env` — HOME is non-persistent, target/ cache under /projects persists).
| PoC | result | proves |
|-----|--------|--------|
| poc_baseline_no_skew_no_leak | **PASS** +0.000074 TAO | CONTROL: at 0.5/0.5 NO leak ⇒ skew is the cause, not a test artifact |
| poc_short_self_close_leaks_under_skewed_weights | leak +499.13 TAO (pool −499.13) | core short leak (r=0.5) |
| poc_short_self_close_leaks_small_skew | leak +985.23 TAO | leak at near-default 0.5% drift (r=0.99), P=100k |
| poc_short_self_close_leaks_with_fee | leak +483.42 TAO | **survives ~3% swap fee** (fee eats only ~16 TAO) |
| poc_long_self_close_leaks_under_skewed_weights | leak +499.13 α | mirror, opposite skew (r=2.0) |
| poc_repeat_drain | +2499.57 TAO over 5×, pool drain == gain to the rao | **sustained**, linear, capital-scaling |
| poc_emission_drift_then_leak | weights 0.5→0.52 via REAL adjust_protocol_liquidity, then +22,394 TAO | **REACHABLE via normal emission, no skew_pool** |

## REACHABILITY RESOLVED
- Skewed weights are NOT a contrived state: (1) the v3→balancer migration inits weights from the v3
  PRICE via `maybe_initialize_palswap(Some(price))` (the exact fn `skew_pool` calls) — and v3 price ≠
  reserve ratio (concentrated liquidity) ⇒ migrated subnets are BORN skewed; (2) per-block emission
  `adjust_protocol_liquidity` drifts weights (PoC-confirmed 0.5→0.52). 0.5/0.5 is the special case.
- Attacker need NOT induce skew — normal operation provides it; the attacker just opens+self-closes.
  Either drift direction leaves one side exploitable (short r<1 / long r>1).

## LIVE MAINNET CHECK (finney, block 8512669) — SEVERITY RECALIBRATED DOWN
Queried `Swap.SwapBalancer` for ALL 128 subnets + cross-checked `MovingPrice == T/A`:
**every pool is at `w_quote = 0.5` (`w1/w2 = 1.0`); max deviation ~1e-9; `MovingPrice == T/A`** (pure
constant-product behavior). At 0.5/0.5 the open & close price on the SAME curve ⇒ leak = 0 (control PoC:
+0.000074 TAO). **The exploit's precondition (`w != 0.5`) exists on ZERO mainnet subnets today.**
Why the earlier reachability claim was wrong in practice:
 - Emission injection is ~proportional by design (`Δα ≈ Δτ/price`) ⇒ weights stay pinned at 0.5; the
   observed real drift is ~1e-9, NOT the 0.5→0.52 my drift PoC forced with UNREALISTIC disproportionate
   injections (`adjust_protocol_liquidity` returns (0,0) / rejects large disbalance).
 - User `add_liquidity` is proportional (does not call `update_weights_for_added_liquidity`).
 - "Migration inits from v3 price ⇒ born skewed" is REFUTED by the data (all 0.5; price==T/A).

## VERDICT (recalibrated): LOW / latent defense-in-depth defect.
The CODE defect is REAL (open weight-unaware vs close weight-aware; proven by 7 PoCs *given* skew), but
REAL-WORLD SEVERITY ON MAINNET IS ~NONE because the required skew does not occur. Worth fixing: make the
open weight-aware so it stays correct IF weights ever leave 0.5 (a future emission mode whose
disproportionate result isn't rejected, a disproportionate user-LP feature, or a migration/governance
init from a non-unity price). NOT a live drain. The earlier "CRITICAL" framing was contingent on skew
reachability, which the live state refutes — this is the verification working as intended.

## Repro artifacts
`sim_baseline.py` (K0=N at r=1), `sim_weighted_selfclose.py` (v1, T=A sweep),
`sim_weighted_v2_pricefixed.py` (price-fixed sweep); 7 Rust PoCs in tests/derivatives.rs (poc_*).
