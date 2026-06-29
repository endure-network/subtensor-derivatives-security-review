# 00 — Target & scope

## What's under review
The **covered continuous-unwind short/long derivatives** added to `pallet-subtensor` in
[opentensor/subtensor#2764](https://github.com/opentensor/subtensor/pull/2764) (`feat/pool-borrowing-spec`,
base `devnet-ready`, open/unmerged), and its client [latent-to/btcli#1007](https://github.com/latent-to/btcli/pull/1007) (`btcli deriv`).
All PoCs are pinned to subtensor head `1a7aa37` ("feat(derivatives): block-lagged Alpha-reserve EMA refs + position key-swap support").

## Code locations (subtensor tree)
- `pallets/subtensor/src/derivatives/mod.rs` — short engine + shared math (`solve_collateral`, `solve_phi`, decay, references, self-cover, default, dereg settle).
- `pallets/subtensor/src/derivatives/long.rs` — long mirror.
- `pallets/subtensor/src/derivatives/types.rs` — position/aggregate/quote structs.
- `pallets/subtensor/src/macros/dispatches.rs` — extrinsics, call_index 143–152.
- `pallets/subtensor/src/tests/derivatives.rs` — the 94-test suite (+ our `poc_*` after applying the patch).
- `pallets/subtensor/runtime-api/src/lib.rs` — `DerivativesRuntimeApi`.
- `pallets/swap/src/pallet/{balancer.rs,impls.rs,mod.rs}` — Balancer weighted-pool swap engine.
- `pallets/subtensor/src/staking/stake_utils.rs` — reserves, `update_moving_price` (the EMA tick).
- `pallets/subtensor/src/coinbase/run_coinbase.rs`, `coinbase/subnet_emissions.rs` — emission injection + shares.
- `pallets/subtensor/src/migrations/migrate_seed_alpha_in_moving_reserve.rs` — A_EMA seeding (existing subnets only).

## Extrinsics (call_index)
143 `open_short` · 144 `top_up_short` · 145 `close_short` · 146 `default_short` (permissionless) · 147 `open_long` ·
148 `top_up_long` · 149 `close_long` · 150 `default_long` · 151 `close_short_self` (cash-settled) · 152 `close_long_self`.
Admin: `sudo_set_shorts_enabled`/`_longs_enabled` + per-parameter setters.

## Status / why it matters
Default-OFF (`ShortsEnabled`/`LongsEnabled`), NOT on mainnet — a **pre-launch review**: find & fix before governance
enables it. A public bug-bounty is associated with the btcli PR.

## In scope
Economic exploits (value extraction, conservation breaks), risk-limit bypasses, griefing/DoS, accounting/rounding,
manipulation of the references/oracle, MEV/sandwich, and the derivatives' interactions with the swap/emission/staking layers.

## Out of scope (for this review)
Generic substrate/runtime bugs unrelated to the derivatives; the btcli client UX; non-derivative pallets except where
the derivatives touch them (swap, staking, coinbase).
