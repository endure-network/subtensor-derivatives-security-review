# Batch 03 — Emission-redirection via price-based emissions (L2)

## Hypothesis
A sustained short depresses a subnet's spot price → its EMA price (`SubnetMovingPrice`) → its **price-based emission
share** (`share_i ∝ r_i·p_i·(1−b_i)`), redistributing block TAO to other subnets. An attacker holding stake in
competing subnets (or shorting a rival) could profit from the redistribution — **independent of weight-skew (F-01) and
the cold-EMA window (F-02)**.

## Why it isn't settled yet
The leak is a cross-subnet **externality**, not internal accounting — the derivatives' conservation tests don't model
it. It needs the live coinbase/emission loop (the mock stubs it) plus a cost/benefit model: carry + price-impact cost
of holding the short vs emission TAO gained elsewhere, net of the EMA half-life (`EMAPriceHalvingBlocks`).

## Approach (per METHODOLOGY)
1. Read the emission-share math (`coinbase/run_coinbase.rs`, `coinbase/subnet_emissions.rs`) and confirm how a short's
   reserve removal feeds `SubnetMovingPrice` (does the open's direct `decrease_provided_tao_reserve` move the spot that
   the EMA samples?).
2. Closed-form model: short size → spot drop → EMA drop over N blocks → Δ(emission share) → TAO redirected, vs the
   short's carry + price-impact cost. Find the break-even and whether any regime is net-profitable.
3. Harness/integration: drive the coinbase across blocks with a live short open; measure per-subnet emission deltas
   (this likely needs more than the derivatives mock — assess whether `run_coinbase` is callable in the test runtime).
4. Live-state: shorts are OFF (pre-launch), but the price-based emission channel itself is live — quantify on finney
   numbers (real reserves, real EMA half-life) what a given short would redirect.
5. Severity: economic, cross-subnet; calibrate honestly (impact × reachability; note pre-launch).

## Log
### Grounding (code, confirmed)
- Emission share is **purely price-EMA based**: `get_shares` (subnet_emissions.rs:354) calls ONLY
  `get_shares_price_ema` (395). The flow path `get_shares_flow` (257) exists but is **not called** ⇒ dead.
  ⇒ `emission_i = block_emission · (root_prop_i · priceEMA_i · (1−miner_burned_i)) / Σ_j(...)`,
  `priceEMA_i = get_moving_alpha_price = SubnetMovingPrice`.
- **L2 mechanism is real:** a short open does `decrease_provided_tao_reserve(N+E)` ⇒ `SubnetTAO`↓ ⇒ spot
  `p=(w1/w2)(T/A)`↓ ⇒ `update_moving_price` samples it into the EMA over blocks ⇒ subnet i's share↓ ⇒ its TAO
  emission is redirected to other subnets. A SUSTAINED open short biases this for as long as it's held.
- **The derivative's χ flow-neutrality defense is MOOT here.** `record_derivative_inflow/outflow` write
  `SubnetTaoFlow`, which only feeds the DEAD `get_shares_flow`. The live (price) channel is what the short moves,
  and χ does not defend it. (Design note worth reporting regardless of severity.)
- **Side-lead L2b (pruning sabotage):** `get_network_to_prune` (root.rs:598-629) selects the non-immune subnet with
  the **lowest `get_moving_alpha_price`** for deregistration. A sustained short that depresses a rival subnet's EMA
  below the field could force its **pruning/deregistration** — competitive sabotage, framed as cost not profit.

### Open questions (to model/quantify)
- L2a magnitude: short size → spot drop → EMA drop over `EMAPriceHalvingBlocks` → Δshare → TAO redirected/block ×
  hold; the attacker captures only their stake fraction of other subnets. vs the short's carry + locked-floor +
  price-impact cost. Is any regime net-profitable? (likely marginal unless attacker dominates other subnets.)
- L2b cost: TAO/blocks to push a target EMA below the current prune-min and hold it until prune fires.
- Harness feasibility: needs the real `run_coinbase`/`block_step` loop (the derivatives mock stubs emission). Assess
  whether `run_coinbase` is drivable in the pallet test runtime, else quantify off finney numbers.

## Result (interim — mechanism CONFIRMED; economics OPEN)
- **Mechanism confirmed:** emission share ∝ priceEMA (`get_shares`→`get_shares_price_ema`; the flow path is dead).
  A short ↓`SubnetTAO` ↓spot ↓priceEMA ↓share ↓emission, redirected to others. The derivatives' χ/`SubnetTaoFlow`
  flow-neutrality defends the DEAD flow channel — a reportable **design observation**, not itself an exploit.
- **Finney magnitude (probe_emission_params.py):** 127 priced subnets, Σprice 1.39; top subnet (net 64) ≈ 5.4% share
  ≈ 195 TAO/day. Depressing a top subnet's EMA −10/−50/−90% redirects ≈ 18 / 95 / 174 TAO/day. Prune-min ≈ 0.0033.
- **EMA speed (cost driver) — corrected:** `EMAPriceHalvingBlocks=201600` is the `b/(b+halving)` RAMP param; the actual
  per-block smoothing is `SubnetMovingAlpha ≈ 3e-4`, so an established subnet's EMA half-life is ~2,300 blocks (**~8h**)
  and ~88% of a sustained price move lands within ~1 day. ⇒ manipulation is hours-to-days, not weeks.
- **Economics — OPEN:** depressing a TOP subnet's spot ~50% means removing ~half its reserve (~100k TAO for net 64)
  and holding it ~a day+ against arbitrage (carry cost) to redirect ~95 TAO/day, of which the attacker captures only
  their stake fraction of the other 126 subnets ⇒ likely unprofitable as a pure skim on large subnets; cheaper on small
  subnets but little emission to capture. **L2b (pruning sabotage)** is the sharper variant: tipping an already-near-min
  subnet below the prune threshold for ~a day could force its deregistration (cost-framed competitive sabotage).
- **Profitability — SETTLED (`tooling/sims/sim_l2_economics.py`):** the capacity cap (κ=0.05) bounds the max short to a
  ~9.75% spot depression; at that max, best-case **redirected-emission / carry = 0.12–0.25** across finney subnets — i.e.
  even ignoring arbitrage, the locked floor P, and the close spread, AND assuming the attacker captures 100% of the
  redirected emission, the short's carry alone is **4–8× the benefit**. ⇒ **L2a is economically infeasible.** The κ cap +
  decay/carry are the effective defense (not χ).

## Verdict
- **L2a (emission skim): LOW** — mechanism real, economically infeasible (carry 4–8× best-case benefit; κ cap bounds depression).
- **L2b (pruning sabotage): LOW–MEDIUM — SETTLED, mechanism confirmed (`finding-l2b.md`).** Harness
  `poc_pruning_sabotage_redirect` proves the prune redirect (lowest non-immune pEMA) + immunity protection + the κ bound
  (a 10×-min subnet is unreachable); `sim_l2b_pruning.py` shows κ=0.05 caps depression at ~9.75% ⇒ only the bottom
  cluster (target within ~10.8% of the min) is reachable. Pure griefing (no profit) / self-protection via the long
  mirror; carry-cost; immunity ~180d; pre-launch.
- **D-chi-moot: informational** — the derivatives' χ/`SubnetTaoFlow` flow-neutrality machinery defends a DEAD channel
  (`get_shares_flow` is uncalled); the live emission channel is price-EMA, defended by the κ cap + slow EMA. Worth a one-line note to maintainers.
