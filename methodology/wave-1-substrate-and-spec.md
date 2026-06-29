# Wave 1 — dTAO substrate + spec (librarians) + critical leads

## Spec librarian (bg_a30315c2) — confirmed
- Docs exist: `docs/derivatives/DESIGN.md`, `docs/derivatives/IMPLEMENTATION_PLAN.md` (read these).
- Formulas match code (T_ref=min(T_live,pEMA·A_EMA); C/N quadratic; φ=(1−√(1−4N/T))/2; Q=φA,E=φT short; D=φT,E=φA long; carry d(u)=dmin+(dmax−dmin)u²; K_D=max(K_spot,Q·pEMA)).
- **Param DEFAULTS**: ShortsEnabled=false, LongsEnabled=false, ShortBaseLtv=**0.50**, ShortKappa=**0.05**, DecayMin=**0.001/day**, DecayMax=**0.015/day**, ShortDust=**1 TAO**, ShortDefaultGrace=**360 blocks**, ShortMinInput=**0.1 TAO**, ShortMaxPositions=**128** (long mirrors). κ clamp (0,2], λ (0,1), decay [0,1], maxpos [1,4096].
- **Break-even formula NOT in checked-in docs** — only the `breakeven_close_price` runtime-API field. Likely in upstream `shorting.pdf v3.6.1`. (open lead)
- 23 commits. Notable: #5 "global value-conservation proofs" (tests), #16 self-cover cash-settle, #18 "caller slippage guard + fix close-cost overflow", #23 block-lagged EMA + key-swap. Touched files include `pallets/swap/src/pallet/{balancer.rs,impls.rs}`, `primitives/swap-interface/src/lib.rs`, `staking/stake_utils.rs`, `coinbase/block_step.rs`, `migrations/migrate_seed_alpha_in_moving_reserve.rs`, `macros/hooks.rs`.

## dTAO librarian (bg_603a37a3) — substrate
- **Balancer WEIGHTED pools** (not pure CPMM): `p = (w_base/w_quote)·(τ/α)`, weights default 0.5/0.5, bounds [0.01,0.99]; `SwapBalancer<T>` map. **Weights shift on liquidity injection** via `update_weights_for_added_liquidity()` (absorbs emission without moving price). With 0.5/0.5 → reduces to constant product.
- Swap: `swap_tao_for_alpha` / `swap_alpha_for_tao` in stake_utils.rs; updates SubnetTAO, SubnetAlphaIn, SubnetAlphaOut, Alpha[(ck,hk,netuid)].
- **Swap fee ≈ 0.05%** (per-subnet, on input, → block author, 10% forwarded). [I assumed 0.3% in sim — fee is ~6× smaller.]
- Slippage: `add_stake_limit`/`remove_stake_limit` with limit_price+allow_partial; strict mode error `SlippageTooHigh`.
- Coldkey/hotkey: stake keyed (coldkey,hotkey,netuid); validator weight = alpha + tao·tao_weight (tao_weight=0.18).
- **EMISSIONS = PRICE-BASED as of June 2026**: subnet share ∝ EMA price `SubnetMovingPrice`: share_i = r_i·p_i·(1−b_i)/Σ. Block emission 0.5 TAO/block. TaoFlow (net-flow model, Nov2025–Jun2026) **DEPRECATED**.

## CRITICAL LEADS opened by the substrate
- **L1 (weighted-pool mismatch, HIGH):** derivative `open` removes N+E TAO via `decrease_provided_tao_reserve` (direct reserve write); `close_self` buyback uses `sim_tao_in_for_alpha_out` (Balancer-weighted swap); slippage guard `executable_price_ppb = t·1e9/a` (naive, ignores weights). If w≠0.5/0.5 (after emission injection shifts weights), these 3 diverge ⇒ (a) my K0=N baseline breaks, possible value leak; (b) slippage guard bounds the WRONG price. **Verify: does decrease/increase_provided_*_reserve adjust Balancer weights? does sim_* use weights?**
- **L2 (price-based emission channel, HIGH):** a short persistently lowers SubnetTAO ⇒ lowers spot, and over time the EMA `SubnetMovingPrice` ⇒ **cuts the target subnet's TAO emission share**, redistributing to other subnets. The derivative's χ/TaoFlow neutrality is moot under price-based emissions. Cross-subnet emission manipulation / competitive griefing. Quantify EMA impact + whether short open's direct reserve removal feeds SubnetMovingPrice.
- **L3 (fee):** real fee ~0.05% not 0.3% — instant round-trip loss is ~6× smaller; re-check dust/rounding edges at the true fee.
- **L4:** `update_weights_for_added_liquidity` — does the derivative's restoration zap / dereg escrow return (which calls increase_provided_*_reserve) trigger weight shifts that an attacker can time?

## Background status
- DONE: spec (bg_a30315c2), dTAO (bg_603a37a3).
- QUEUED (concurrency ~2): prior-vulns (bg_6a508635, 15m), community (bg_8cbe62cc), attack-taxonomy (bg_42117413).
- Explore agents CANCELLED (were stuck queued) → doing local plumbing/tests/client read myself.
