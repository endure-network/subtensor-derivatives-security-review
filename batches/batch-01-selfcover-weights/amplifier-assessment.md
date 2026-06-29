# Amplifier assessment — do recent/in-flight changes ARM FINDING-01?

FINDING-01 arms only if a subnet pool's Balancer weights leave 0.5/0.5. Question: does any recent
PR / release / branch move toward that? Method: gh file-histories of pallets/swap + run_coinbase,
open-PR search, branch identity, releases/CHANGELOG, PR #2764 status. (librarian doing web/roadmap breadth.)

## Recent changes that TOUCH the relevant logic
1. **`balancer.rs` cap exp_scaled at 1 (98151ecd, 2026-06-26) — NOT an amplifier.**
   The cap is CONDITIONAL: `if dx >= 0 { result.min(1) } else { result }`. The derivatives' exact-output
   buyback helpers call `exp_scaled` with NEGATIVE dx ⇒ hit the UN-capped branch ⇒ `e>1` preserved ⇒
   `K = reserve·(e−1)` unchanged. (Initially feared it zeroed K ⇒ would've made the leak fire at 0.5/0.5
   / live; the `if dx>=0` guard refutes that.) Precision retune 1024→…→256 is just accuracy.
2. **`impls.rs` "forbid swaps too large vs liquidity" + 1000× input cap (593de8a1/1ad16880, 2026-06-26)
   — MITIGATION.** Bounds the per-trade self-cover buyback: oversized `Q` ⇒ sim errors ⇒ derivative treats
   as the seize-full sentinel ⇒ underwater ⇒ rejected. Caps exploit magnitude per trade.
3. **Emission → price-based shares + root-proportion injection cap (c3841130, 2026-06-22).**
   The weight-drift GOVERNOR. Empirically NOT drifting finney weights (all 128 at 0.5 a week after the
   change; real drift ~1e-9). The one mechanism that COULD arm it, but isn't.

## In-flight amplifiers: NONE found
- Open PRs touching liquidity/balancer/weighted/concentrated: **zero**.
- PRs re-enabling user/concentrated liquidity (un-deprecate add_liquidity/modify_position): **zero**.
- Suspicious branches `alpha_injection_cap` (2025-12-12), `alpha_pool_contract` (2025-09-30): **stale**.
- PR #2764 (derivatives): open, base=devnet-ready, mergeable, NOT merged → pre-deployment.
- Releases through v3.4.8-423 (2026-06-25); CHANGELOG: no balancer/liquidity/weight entries.

## Trajectory (Feb–Mar 2026 history) moves AWAY from arming it
`2026-02-03 More user liquidity cleanup` → `2026-02-25 revert balancer_swap` → `2026-03-17 Re-enable balancer`:
user/concentrated liquidity was DELIBERATELY removed when they adopted the protocol-only Balancer pool, and
the user-LP extrinsics were left as permanent `Err(Deprecated)` stubs. Re-enabling it would be a conscious
reversal, not drift. Combined with the new swap-size caps, recent dev REDUCES exposure.

## In-flight emission/init PRs (librarian-surfaced) — verified, none arm it
My keyword search missed these (they're emission/init/injection PRs, not "liquidity"-titled). Verified each:
- **#2594** (merged devnet-ready 2026-04-16) "Owner Alpha Stake": subnet registration now inits the pool from
  a MEDIAN-PRICE snapshot instead of 1:1. Sets initial PRICE via the reserve ratio (reserves seeded at target
  price ⇒ w=0.5). This is WHY all 128 finney subnets are uniformly 0.5 despite different prices. Price, not
  weights. NOT arming.
- **#2758** (open devnet-ready) "Handle balancer misbalance on injection": when an injection would push weights
  out of range, RESERVES the non-price-active excess and applies only the proportional (price-active) part ⇒
  keeps injection proportional, weights bounded. MITIGATION, not arming.
- **#2785** (open devnet-ready): propagates the SAME price-based emission already live on finney (0.5). NOT arming.
- **#2799** (open main): re-adds Swap::AlphaSqrtPrice as a back-compat READ shim (price is derived). NOT arming.
- **#2558** (merged): owner alpha stake at registration — subnet init, but about owner stake not weights.

ARCHITECTURAL CONCLUSION: weights are STRUCTURALLY pinned at 0.5 — fresh pools seed reserves AT the target
price (p=y/x ⇒ w=0.5), protocol injection is proportional (#2758 reserves any excess), user-LP is deprecated.
The only non-0.5 source is the one-time v3→balancer migration (price≠reserve ratio), and live finney is 0.5
even there. No in-flight change moves toward non-0.5.

## VERDICT
No recent or in-flight change amplifies FINDING-01; the cap-exp_scaled change is correctly scoped (neutral),
the swap-size cap is mitigating, emission keeps weights pinned at 0.5, and nothing re-enables user-LP.
FINDING-01 stays MEDIUM (dormant; trajectory not arming it). Forward-looking WATCH ITEMS (none in-flight):
(a) any future re-enablement of user/concentrated liquidity; (b) any emission/injection change that makes
protocol injection materially disproportionate; (c) any pool init/migration seeding non-0.5 weights.
