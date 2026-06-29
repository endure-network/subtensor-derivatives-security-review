# 02 — Substrate the derivatives sit on (facts)

## Subnet pools = Balancer WEIGHTED pools (not pure CPMM)
Each dynamic subnet has a pool with TAO reserve (`SubnetTAO`) and Alpha reserve (`SubnetAlphaIn`), priced by a
Balancer weight: **`p = (w1/w2)·(T/A)`**, where w1 = base/Alpha weight, w2 = quote/TAO weight, stored as
`SwapBalancer<netuid>.quote` (Perquintill, /1e18). Default 0.5/0.5 ⇒ reduces to constant product. Weight bounds:
code `MIN_WEIGHT = 0.01` (the header comment says 0.1 — discrepancy) ⇒ w∈[0.01,0.99].
- Buy Alpha (exact-out): `K = T·((A/(A−Q))^(w1/w2) − 1)` (`get_quote_needed_for_base`), fee grossed up. The `e>1`
  (exact-output) path is **uncapped**; `exp_scaled` caps `min(·,1)` only for `dx≥0` (exact-input).
- The derivatives' `sim_tao_in_for_alpha_out` / `sim_alpha_in_for_tao_out` route through this (weight + fee aware).

## What moves the weights (key for any reference/oracle attack)
Only `update_weights_for_added_liquidity`, whose **single** non-test caller is `adjust_protocol_liquidity` (emission
injection). Emission injects ~proportionally; PR #2758 reserves disproportionate excess rather than skewing weights.
**User-LP extrinsics (`add_liquidity`/`remove_liquidity`/`modify_position`/`toggle_user_liquidity`/`disable_lp`) are
permanently `Err(Deprecated)`.** Fresh pools seed reserves *at* the target price ⇒ w=0.5. ⇒ weights are structurally
pinned near 0.5 (see `04-verified-facts.md`).

## EMA references
`update_moving_price` (stake_utils.rs, once per block in the coinbase) ticks `SubnetMovingPrice` (pEMA) and
`SubnetAlphaInMovingReserve` (A_EMA) from live values, smoothing `α = SubnetMovingAlpha·(b/(b+halving))`, `b = block − start`.
The derivative references read these *lagged* values so an in-block swap can't move them.
**Caveat:** A_EMA is seeded for existing subnets by a migration but **NOT at subnet creation** ⇒ fresh subnets start
cold (A_EMA=pEMA=0) ⇒ references fall back to live `t_live`/`a_live` (see batch-02 / `05-open-surface.md`).

## Emission (price-based, since June 2026)
Subnet TAO share ∝ EMA price: `share_i = r_i·p_i·(1−b_i)/Σ` (`r` = root_proportion, shrinks with subnet age; `b` =
miner-burned). Alpha injected `min(Δτ/p, r·cap)`. Block emission ~0.5 TAO. So a subnet's price (and its EMA) drives its
emissions — relevant to the L2 (emission-redirection) lead.

## Staking / keys / fees
Stake is per `(coldkey, hotkey, netuid)`. `open_short(hotkey,…)` can name any hotkey (only the signer/coldkey is
validated); the liability is repaid from the signer's stake at that hotkey. Validator weight = alpha + tao·0.18.
Swap fee ≈ 0.05% (per-subnet, on input, to the block author).
