# Wave 1 — Test coverage map (DEFENDED vs GAPS)

`pallets/subtensor/src/tests/derivatives.rs` — **94 tests, 2398 lines.** The test
NAMES are a confession of the threat model the authors already closed. Bug-bounty
value is in the GAPS, not these.

## Balancer swap formula (balancer.rs) — L1 mechanism confirmed
- Buy Alpha: `Δy = y·((x/(x−Δx))^(w1/w2) − 1)` (`get_quote_needed_for_base`).
- Sell Alpha: `Δy = y·((x/(x+Δx))^? )` via `get_base_needed_for_quote`.
- At **w1=w2=0.5 ⇒ exponent 1 ⇒ exact constant product** (my K0=N baseline holds).
- Skewed weights ⇒ diverges. **MIN_WEIGHT = ACCURACY/100 = 0.01** ⇒ weights ∈ [0.01,0.99].
- **DISCREPANCY**: header comment (line 35) says weights clamped to **[0.1,0.9]**, but the
  constant + `check_constraints` allow **[0.01,0.99]**. Worth a note (which is the real bound?).
- `update_weights_for_added_liquidity` shifts weights on disproportionate liquidity adds
  (emission injection) — "will not cause weights to get far from 0.5" (claim, unquantified).

## DEFENDED (has a regression test — do NOT chase)
- `open_close_roundtrip_is_not_profitable` (830) ⇒ my K0=N baseline is tested.
- `close_guards_against_alpha_mint` (855), `open_long_guards_against_alpha_mint` (1233) ⇒ H8 anti-mint.
- `proof_full_lifecycle_conserves_tao_and_alpha` (933), `proof_default_recycles_exactly_the_floor` (996),
  `proof_multi_position_decay_conserves` (1035) ⇒ global conservation.
- `short_many_partial_closes_drain_cleanly` (1094) ⇒ **H3 (partial-close dust) defended**.
- `materialize_never_inflates` (808) ⇒ decay/omega can't inflate.
- `engine_cover_inverts_real_swap_short/long` (1833/1854), `engine_cover_diverges_from_naive_cpmm` (1877)
  ⇒ **L1 core**: cover uses the real weighted swap, divergence from naive CPMM is tested.
- `short_lifecycle_conserves_tao_under_weights_and_fee` (2044) ⇒ **L1 conservation under weights+fee**.
- T_ref manipulation block: `naive_single_side_pump_cannot_raise_t_ref` (2261),
  `crossover_nudge_does_not_inflate_t_ref_proceeds_or_capacity` (2285),
  `sandwich_open_cannot_breach_capacity_cap` (2329), `crossover_nudge_does_not_inflate_a_ref_or_capacity` (2371)
  ⇒ **H1/H6 (EMA/capacity manipulation) defended**.
- `short_self_close_rejects_when_underwater` (2017); dereg `max(spot, stale EMA)` (1932/1975).
- Key-swap: `hotkey_swap_rehomes_short`/`third_party_delegator`/`coldkey_swap_rekeys` (2096/2158/2207) ⇒ H10.
- `permissionless_default_respects_grace_window` (627), `top_up_resets_default_grace` (654) ⇒ H5 partial.
- `open_long_respects_stake_lock` (1738) ⇒ **H7 defended**.
- `decay_rate_matches_closed_form` (1563); `derivatives_write_subnet_flow` (1324).

## CANDIDATE GAPS (where to actually hunt)
1. **Slippage-guard ⟷ weighted-price mismatch (HIGH):** `executable_price_ppb = t·1e9/a` is NAIVE τ/α,
   but true price is `(w1/w2)·(τ/α)`. No test seen for `ensure_price_at_least/at_most` under skewed
   weights ⇒ the caller's `--slippage` bound protects the WRONG price when w≠0.5. MEV/sandwich window.
2. **L2 emission externality (HIGH, likely out-of-scope of tests):** tests prove INTERNAL conservation,
   not the cross-subnet effect — a sustained short lowers `SubnetMovingPrice` ⇒ cuts the subnet's
   price-based emission share ⇒ redistributes TAO to other subnets the attacker holds. Economic, not accounting.
3. **Weight-drift realism:** tests `skew_pool()` artificially. Does production `update_weights_for_added_liquidity`
   actually keep w near 0.5, or can emission history push it toward 0.01/0.99 where divergence is large?
4. **Same-block composition:** open+decay-tick+close, or open then normal swap then close, MEV ordering,
   many coldkeys/one hotkey — beyond `stacked_opens_share_capacity` (188).
5. **Boundary dust:** `fraction_ppb=1` (1-rao close), default after a chain of partial closes, cold A_EMA on LONG side.
6. **`no covering tests found`** (codegraph): `increase/decrease_provided_tao_reserve` only indirectly tested.

## Background status
- DONE: spec (bg_a30315c2), dTAO (bg_603a37a3).
- Fetching now: prior-vulns (bg_6a508635), community/bounty (bg_8cbe62cc), attack-taxonomy (bg_42117413).
