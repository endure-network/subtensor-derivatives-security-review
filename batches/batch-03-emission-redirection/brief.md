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
- (pending)

## Result
- (pending) — update `../../FINDINGS.md` (`C-L2`) when settled.
