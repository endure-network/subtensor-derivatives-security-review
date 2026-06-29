# Ultraresearch Synthesis: Bittensor alpha shorting (subtensor #2764 / btcli #1007)

Workers: 5 librarians + 3 explore (3 cancelled, redone locally) · Waves: 2 · Code read: full derivatives pallet, types, balancer, stake_utils EMA, client, 94-test suite · Verifications: 1 (baseline K0=N)

## FINDING-01 (RECALIBRATED → LOW / latent) — see FINDING-01-selfcover-weight-asymmetry.md
LIVE CHECK: all 128 finney subnet pools are at exactly w=0.5/0.5 (price==T/A), where the leak is ZERO.
The code defect is real (proven by 7 PoCs given skew) but NOT exploitable on mainnet — the skew
precondition does not occur (emission injects ~proportionally; weights stay pinned at 0.5). Fix as
defense-in-depth (make open weight-aware), not a live drain. Original (skew-contingent) framing below:
## ⚠️ FINDING-01 mechanics (HIGH *only under* weight skew, which mainnet does not exhibit)
`close_short_self`/`close_long_self` price the liability buyback through the weight-aware Balancer
engine while `open_*` books it with weight-unaware constant-product math. Under ANY Balancer weight
skew, open + instant self-close drains ~N·(1−w1/w2) from the subnet pool, no price move, repeatable.
PROVEN in their harness: short r=0.5 → +499 TAO; short r=0.99 (0.5% drift) → +985 TAO on 100k; long
r=2.0 → +499 α. Real-code numbers match the Python model to the decimal.

## What it is
Covered continuous-unwind short/long derivatives on per-subnet Balancer pools.
Default-OFF (`ShortsEnabled`/`LongsEnabled`), gated behind a "trading-games" adversarial
test gate; NOT on mainnet as of 2026-06-29 (PR #2764 open). Authored by `unconst`;
messaging from Const/OpenTensor. No public cash-bounty terms found (gate = the test suite).

## Mechanics (verified)
- **Short** (collateral TAO, liability Alpha Q): post floor P→custody; remove N+E TAO from pool
  (price↓, **fee-free direct reserve write** `decrease_provided_tao_reserve`); book Q=φ·A_live.
  Buffer R=N decays as carry (convex d(u)). Close: repay Q (own stake) OR self-cover (protocol
  buys Q from pool at **live SPOT** K via weighted swap, charges to P+R; reject if K>P+R).
  Default (permissionless, after R≤dust + grace): R+E→pool, **floor P burned**, Q extinguished.
- **Long**: mirror (collateral Alpha, liability TAO D); collateral burned/minted via issuance.
- **References block-lagged**: `T_ref=min(T_live, pEMA·A_EMA)`, ticked once/block in `update_moving_price`.
  Close cost + dereg cover use **live spot** through the weighted engine. EMA defends in-block, not multi-block.
- Pool is **Balancer-weighted** (`p=(w1/w2)(τ/α)`, w∈[0.01,0.99], default 0.5/0.5); at 0.5/0.5 = CPMM.

## Benefits (claimed): price discovery, hedging, capital efficiency, NO short squeeze / NO
liquidation cascade (carry-decay-to-dust default, no price liquidation), gradual unwind.

## Drawbacks/risks: carry cost; large new math-heavy surface bolted on the AMM with direct
fee-free reserve writes; same-pool-as-oracle-and-venue; emission externality (L2).

## VERIFIED baseline-sound (K0=N) + DEFENDED by regression tests (do not chase)
Independent sim: self-close buyback K0 == retained proceeds N exactly at 0.5/0.5 (residual <1 rao,
fees make round-trips lossy). Tests lock: non-profitable roundtrip, anti-mint, global conservation
(incl. weights+fee in-kind close), cover via real weighted engine vs naive CPMM, **in-block T_ref/
capacity manipulation (authors found & fixed the crossover bug)**, underwater self-close reject,
dereg max(spot,stale-EMA), key-swap rehoming, default grace, stake locks, partial-close dust drain.
Client slippage uses naive τ/α matching chain (consistent → not exploitable, only a unit quirk).

## CANDIDATE EXPLOIT AREAS (survive the known defenses — ranked)
1. **Multi-block EMA manipulation (HIGH).** In-block fix relies on block-lagged A_EMA/pEMA; the EMA
   is movable over ~`EMAPriceHalvingBlocks`. Push it to over-size positions / inflate capacity /
   cheapen cover, net of carry+skew cost? Tests cover only in-block.
2. **Emission redirection L2 (HIGH, economic, reviewer-acknowledged).** Price-based emission share ∝
   EMA price. Sustained short depresses target subnet's emissions → redistributes to attacker's other
   subnets. Internal-conservation tests don't model this externality.
3. **close_*_self conservation under weights+fee+decay (MED).** Only in-kind close has a named
   conservation proof; cash-settled self-cover path under skewed weights over long decay unproven.
4. **Carry-timing / same-block (MED).** Decay runs once/block in a hook; open+close same block pays ~0
   carry → cheap repeated price-move tool (each round-trip costs ~one swap fee + reserve round-trip).
5. **Non-transactional decay hook (MED).** `run_*_decay` in on_initialize is NOT rolled back; transfers
   guarded by `.is_ok()`, but rounding-driven custody shortfall could desync aggregate vs custody
   (reviewer flagged "non-transactional economic mutations").
6. **Permissionless-default MEV / cross-position coupling (MED).** Default moves the shared pool; sequence
   defaults/closes to cascade or sandwich others.
7. **Boundary/precision (LOW-MED).** fraction_ppb=1, long cold A_EMA, recycle min()/MAX sweep, saturating
   conversions at extremes, weight-bound doc/code discrepancy [0.1,0.9] vs [0.01,0.99].
8. **Dereg settlement DoS (LOW).** settle_*_on_dereg O(positions≤4096) in one block.

## Pen-testing methodology
A. Property/differential tests in the SHIPPED mock runtime (`tests/derivatives.rs` + skew_pool/set_fee
   helpers) — extend with multi-block EMA loops, same-block compositions, default cascades; assert gate props.
B. Closed-form/numeric sims (sim_baseline.py style) for weighted-K-vs-N under skew, multi-block-EMA P&L,
   emission-redirection economics — settle profitability before chain code.
C. Local devnet e2e: build node, sudo-enable shorts, drive via btcli deriv / direct extrinsics, incl. the
   real coinbase/emission loop (mock stubs it) — needed for L2.
D. Targeted audit: decay hook atomicity, direct-reserve-write vs Balancer-weight consistency, saturating edges.

## Contradictions / gaps
- Break-even formula not in checked-in docs (only runtime-API field) — likely in upstream shorting.pdf.
- Real weight-drift magnitude in production (tests skew artificially) — unknown.
- Public bounty reward terms — not found (gate is the only public scope).
- Prior-subtensor-vulns librarian still running (historical bug-pattern context pending).

## Sources: subtensor PR #2764, btcli PR #1007, docs.learnbittensor.org (dTAO/slippage/emissions/balancer),
dTAO whitepaper, arxiv 2603.29751/2606.03548, OpenZeppelin ERC4626, Aave/Euler/Arcadia postmortems, code @ 1a7aa37.
