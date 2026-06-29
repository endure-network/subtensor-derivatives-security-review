# 01 — How the derivatives work (mechanics, facts)

A "covered continuous-unwind short" is a synthetic bearish position on a subnet's Alpha. Three terms: **P** = floor/
capital posted; **R** = retained-proceeds buffer that decays over time as carry; **Q** (short, Alpha) / **D** (long,
TAO) = a fixed liability repaid to close. Long is the mirror (collateral Alpha, liability TAO).

## Short lifecycle (collateral TAO, liability Alpha `Q`)
- **open_short(hotkey, netuid, P, limit_price)** (`do_open_short`):
  - `t_ref = min(t_live, pEMA·A_EMA)` (block-lagged EMA reference; **cold ⇒ falls back to `t_live`**).
  - `(C,N) = solve_collateral(P, t_ref, b_sigma, λ)`; footprint `B=λC`; capacity gate `b_sigma+B ≤ κ_S·t_ref`.
  - `φ = solve_phi(N, t_live)`; escrow `E=φ·t_live`; liability `Q=φ·a_live`.
  - Moves: P (trader→custody); **removes N+E TAO from the pool into custody** via `decrease_provided_tao_reserve`
    (direct reserve write — no swap, no fee); records a bearish TaoFlow at `Q·pEMA`.
- **carry / decay** (`run_short_decay`, per block): R/E/B decay on a convex curve `d(u)=dmin+(dmax−dmin)u²`,
  `u=util(b_sigma, κ·t_ref)`; the decayed TAO is restored to the pool. Floor P never decays.
- **close_short** (in-kind): repay `ρQ` Alpha from your stake at `pos.hotkey`; settle `ρE` to pool; return `ρ(P+R)`.
- **close_short_self** (cash-settled): protocol buys `ρQ` Alpha back from the pool at spot cost `K`
  (`sim_tao_in_for_alpha_out`, **weight + fee aware**), charged to the claim; returns `ρ(P+R)−K`. Rejected if underwater (`K>claim`).
- **default_short** (permissionless): once `R ≤ ShortDust` and the grace window has passed; restores R+E, **burns floor P**, extinguishes Q.
- **dereg settle**: per position `cover = min(C, max(K_spot, Q·pEMA))`, `equity = C−cover` → trader, cover burned.

## The math
- `solve_collateral(P, ref, S, λ)`: `a=λ²/ref`, `b=1−λ+2λS/ref`, `C=(−b+√(b²+4aP))/2a`, `N=C−P`. **Constant-product geometry — NO weights.**
- `solve_phi(N, T)`: `φ=(1−√(1−4N/T))/2`. Domain `4N≤T`.
- Fixed-point `I64F64`; decay path uses `saturating_*` (non-transactional `on_initialize` — a panic would halt consensus).

## Baseline conservation FACT (verify: `tooling/sims/sim_baseline.py`)
At Balancer weights 0.5/0.5 the self-cover buyback **`K0 == N` exactly** (removing N+E drops the pool to `T(1−φ)²`,
rebuying `Q=φA` costs `φT(1−φ)=N`). So open + instant self-close returns ~P; fees make it strictly lossy. This is the
"no-bug" baseline — deviations from it are where leaks live.

## Long mirror (`long.rs`)
Collateral Alpha (burned at open via issuance accounting, minted back on close/restore); liability TAO `D=φ·t_live`.
`close_long_self` sells `K'` Alpha (`sim_alpha_in_for_tao_out`) to raise `ρD` TAO.

## Parameter defaults
`ShortBaseLtv λ=0.50` · `ShortKappa κ=0.05` · `DecayMin 0.001/day` · `DecayMax 0.015/day` · `ShortDust 1 TAO` ·
`ShortDefaultGrace 360 blocks` · `ShortMinInput 0.1 TAO` · `ShortMaxPositions 128`. Clamps: κ∈(0,2], λ∈(0,1),
decay∈[0,1], maxpos∈[1,4096], χ (`DerivativeFlowFactor`)∈[0,1].
