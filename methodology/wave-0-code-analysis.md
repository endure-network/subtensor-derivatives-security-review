# Wave 0 — Deep code analysis of the derivatives engine (orchestrator-read)

Files read in full: `derivatives/mod.rs` (shorts + engine), `derivatives/long.rs` (longs), `derivatives/types.rs`.
Spec version in header: **v3.6.1**. Both sides default-OFF (`ShortsEnabled`/`LongsEnabled`).

## Mental model — what a "covered continuous-unwind" position is
A short = synthetic bearish position on a subnet's Alpha. Instead of borrowing real Alpha,
the protocol **removes TAO from the pool** at open (price ↓) and books a fixed **Alpha
liability Q** you must "repay" to close. A buffer **R** (= retained proceeds N at open)
**decays each block as carry**; when R hits dust, anyone can **default** you (you forfeit
floor P). Long = exact mirror (collateral Alpha, liability TAO D).

## SHORT accounting (collateral = TAO; liability = Alpha `Q`)
- **open_short(hotkey, netuid, P, limit_price)** — call 143
  - `t_ref = min(T_live, pEMA·A_EMA)` (block-lagged EMA upper bound; cold→T_live).
  - `(C,N) = solve_collateral(P, t_ref, b_sigma, λ)`; `B = λC`; capacity gate `b_sigma+B ≤ κ_S·t_ref`.
  - `φ = solve_phi(N, T_live)`; `E = φ·T_live` (escrow), `Q = φ·A_live` (alpha liability).
  - Money moves: P (trader→custody); **N+E TAO pool→custody, `decrease_provided_tao_reserve`, `TotalStake−=N+E` — NO swap, NO fee** (price↓ for free). Custody now = P+N+E.
  - Flow: `record_derivative_outflow(Q·pEMA)`.
- **decay (run_short_decay, per block, on active subnets)**: convex `d(u)=dmin+(dmax−dmin)u²`, `u=util(b_sigma, κ_S·t_ref)`. Decremented `dr,de,db`; `Ω += −ln(1−δ)`. **Restoration zap**: decayed `dr+de` TAO custody→pool (`increase_provided_tao_reserve`, `TotalStake+=`). Floor P never decays.
- **close_short (own alpha)** — call 145: repay `ρQ` alpha from stake@(pos.hotkey, coldkey) → `decrease_stake`, `SubnetAlphaOut−=ρQ`, `increase_provided_alpha_reserve(ρQ)`. Escrow `ρE` custody→pool. `ρ(P+R)`→trader. Guards: stake≥ρQ, `SubnetAlphaOut≥ρQ` (anti-mint), `ensure_available_to_unstake`.
- **close_short_self (cash)** — call 151: `K = short_spot_close_cost(ρQ)` (SPOT, sim_tao_in_for_alpha_out WITH_FEES). Underwater iff `K>claim=ρ(P+R)`. Inject `K+ρE` TAO custody→pool. `claim−K`→trader. **Alpha-neutral (no SubnetAlphaOut/AlphaIn move).**
- **default_short (PERMISSIONLESS)** — call 146: needs `R≤ShortDust` AND `block≥last_active+grace`. R+E→pool; **floor P recycled/BURNED (`recycle_custody_tao`, `TotalIssuance−=`)**; Q extinguished (never repaid).
- **dereg settle**: per pos `cover=min(C, max(K_spot, Q·pEMA))`, `equity=C−cover`→trader, cover burned; final custody dust swept.

## LONG accounting (collateral = Alpha; liability = TAO `D`) — mirror, long.rs
- No custody account; collateral Alpha is **burned at open** (`decrease_stake`, `SubnetAlphaOut−=P`, `decrease_provided_alpha_reserve(N+E)`), **minted back** on close/restore.
- open_long sources P from stake@(hotkey,coldkey); guards `stake≥P`, `ensure_available_to_unstake`, `SubnetAlphaOut≥P`.
- close_long: repay `ρD` TAO into pool; mint `ρE` alpha to pool + `ρ(P+R)` alpha back as stake (`SubnetAlphaOut+=`).
- close_long_self: sell `K'=long_spot_close_cost(ρD)` alpha (SPOT, sim_alpha_in_for_tao_out); inject `K'+ρE`; mint `claim−K'` as stake. Underwater iff `K'>claim`.
- default_long: R+E alpha→pool; floor stays burned; D extinguished.

## Key params / clamps (governance, mod.rs §14.6)
- κ (kappa) clamp (0,2.0]; λ (base LTV) clamp (0,1); decay dmin/dmax ∈[0,1]/day, dmin≤dmax; χ (DerivativeFlowFactor) ∈[0,1]; MaxPositions clamp [1,4096]; dust/grace/min_input setters.
- Fixed-point **I64F64** everywhere; decay path uses **saturating_*** (non-transactional on_initialize → panic would halt consensus).

## RANKED ATTACK HYPOTHESES (to validate by sim / deeper read)
- **H1 — Spot-vs-EMA asymmetry (HIGH).** Open collateral/capacity use `T_ref=min(T_live,EMA)` and flow uses `pEMA`; but `close_*_self` and dereg-cover use **live SPOT** (`sim_*`). A trader who makes spot diverge from the lagged EMA (sustained push, or exploit cold/stale EMA) may open on favorable EMA terms and close/settle on favorable spot terms. EMA defends flash, NOT multi-block.
- **H2 — Fee-free price impact (HIGH).** Short open removes N+E TAO from the pool with NO swap fee (`decrease_provided_tao_reserve`). This is a cheaper way to push subnet price DOWN than a real swap. Quantify carry vs saved fee+slippage → sandwich other stakers / emission-weight timing.
- **H3 — Rounding/dust drift (HIGH).** All `mul_tao/mul_alpha` truncate (`saturating_to_num`). Repeated tiny partial closes (`fraction_ppb` small, many calls) — does Σtruncation let trader extract > P+R, or break custody≥obligations? Header CLAIMS drift is safe-direction; must verify numerically.
- **H4 — close_short_self self-sandwich (MED-HIGH).** Push spot down (dump alpha), self-close at small K (large `claim−K`), unwind. Net-positive after fees? Protocol injects K computed at the depressed spot.
- **H5 — Permissionless default MEV/griefing (MED).** Anyone defaults dusted+grace position (floor burned). Back-running; combined with key-swap to strand/seize. Can an attacker accelerate a victim to dust? (decay is per-subnet utilization, not per-victim → likely no, but stacking opens raises util/decay for everyone.)
- **H6 — Capacity DoS (MED).** Drop T_live (remove TAO) to shrink `κ_S·t_ref` and block others' opens, or stack opens to hit `b_sigma` cap → freeze market.
- **H7 — Locked-alpha bypass (MED).** open_long+close_long round-trip — does `ensure_available_to_unstake` fully prevent freeing subnet-owner-locked alpha? Check lock semantics.
- **H8 — Conservation break (CRITICAL if found).** Many `saturating_add/sub` on `TotalStake`, `SubnetAlphaOut`, `TotalIssuance`, reserves across 12 legs. Find any path that nets minting TAO/Alpha (close mints `returned` alpha into SubnetAlphaOut — always ≤ burned at open?). Cross-leg with decay restoration + dereg.
- **H9 — Cold-EMA fallback (MED).** Fresh subnet `t_ema≤0` → `t_ref=T_live` (in-block manipulable). Open on cold subnet with nudged live reserve to inflate capacity/terms.
- **H10 — key-swap / merge edge (MED).** `swap_positions_for_hotkey_swap` re-homes by netuid; merge requires same hotkey. Coldkey re-key path (mod.rs ~1120+). Stranding / double-count across swap.

## Open questions for background agents
- How `increase/decrease_provided_tao_reserve`, `increase/decrease_provided_alpha_reserve`, `SubnetAlphaOut`, `increase_stake_*` actually mutate reserves/issuance (explore bg_ad63ecc8).
- EMA update cadence/formula `update_moving_price`, `SubnetAlphaInMovingReserve`, `get_moving_alpha_price` (explore bg_ad63ecc8).
- Test coverage gaps + param defaults + where decay/dereg hooks are wired (explore bg_70472730).
- btcli client checks vs chain (explore bg_a12e4a9e).
