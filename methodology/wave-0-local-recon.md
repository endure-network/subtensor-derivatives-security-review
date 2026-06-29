# Wave 0 — Local code recon (orchestrator)

## Repos cloned (shallow, PR heads)
- subtensor `pull/2764/head` @ `1a7aa37` "feat(derivatives): block-lagged Alpha-reserve EMA refs + position key-swap support" → `/projects/subtensor`
- btcli `pull/1007/head` @ `ecf5c01` "deriv: add --slippage/--limit-price guard rails" → `/projects/btcli`

## Implementation location
`/projects/subtensor/pallets/subtensor/src/derivatives/`
- `mod.rs` — math engine: conversions (I64F64), `solve_collateral` (§4.2), `solve_phi` (§4.3), price refs, `ensure_price_at_most/at_least`, governance setters (§14.6), per-block decay
- `long.rs` — `do_open_long`, `do_close_long_self`, `do_default_long`, `materialize_long`
- `short.rs` (presumed) — short side
- tests: `pallets/subtensor/src/tests/derivatives.rs`
- runtime API: `pallets/subtensor/runtime-api/src/lib.rs`
- dispatches: `pallets/subtensor/src/macros/dispatches.rs` (call_index 143–152)

## Extrinsic table (dispatches.rs)
| idx | name | key args |
|-----|------|----------|
| 143 | open_short | hotkey, netuid, position_input: TaoBalance, limit_price |
| 144 | top_up_short | netuid, amount: TaoBalance, limit_price |
| 145 | close_short | (partial via fraction_ppb) |
| 146 | default_short | coldkey, netuid — PERMISSIONLESS |
| 147 | open_long | hotkey, netuid, position_input: AlphaBalance, limit_price |
| 148 | top_up_long | ... |
| 149/150 | close_long / default_long | ... |
| 151 | close_short_self | netuid, fraction_ppb, limit_price — cash-settled from pool |
| 152 | close_long_self | netuid, fraction_ppb, limit_price — cash-settled from pool |

## Core math (mod.rs, from codegraph)
- `solve_collateral(P, ref_reserve, S, lambda)`: a=λ²/T_ref; b=1−λ+2λS/T_ref; C=(−b+√(b²+4aP))/2a; N=C−P. None if N≤0 or C≤0.
- `solve_phi(N, T_live)`: ϕ=(1−√(1−4N/T))/2; None if 4N>T.
- `ref_reserve` = block-lagged EMA (T_ref shorts / A_ref longs) ← the commit's headline.
- Fixed point I64F64; decay runs in non-transactional on_initialize → uses saturating_* (panic = consensus halt).

## Initial suspicions (to validate)
1. **EMA price reference** — block-lagged Alpha-reserve EMA as the oracle. Manipulation surface: can you move spot away from EMA and arbitrage open/close? How many blocks lag? Is the EMA itself manipulable cheaply?
2. **`open_short(hotkey,...)` arbitrary hotkey** — btcli notes only coldkey validated for SS58. Liability parked on someone else's validator hotkey → griefing / accounting abuse?
3. **`close_*_self` mints stake back** (`SubnetAlphaOut += returned`, `increase_stake...`) — verify conservation; does pool actually hold the Alpha it "covers"? Self-cover buys liability from SAME pool it priced against.
4. **Permissionless `default_*`** — anyone defaults a dusted position after grace. Can decay be accelerated / can attacker force a victim underwater?
5. **Rounding/precision** — partial close via fraction_ppb (ρ=fraction/1e9); mul_tao/mul_alpha truncate via saturating_to_num. Repeated tiny closes / dust accumulation favoring attacker?
6. **Carry dodge** — open+close same block; does carry/decay accrue at all within a block?
7. **solve_phi domain `4N≤T`** — what happens at the boundary / when None bubbles up; DoS by forcing None?

## Status
- 5 librarians running (external axes). 3 explore agents fired (base AMM plumbing / btcli client / tests+API). Reading core mod.rs+short.rs+long.rs myself.
