# FINDING-L2b — Pruning sabotage via short-depressed pEMA (LOW–MEDIUM, confirmed but bounded)

**Component:** `pallet-subtensor` — `get_network_to_prune` (`coinbase/root.rs:598`) + the registration prune trigger
(`subnets/subnet.rs:152-185`), driven by a derivatives short that depresses `SubnetMovingPrice` (subtensor #2764).
**Status:** settled on `opentensor/subtensor#2764` — **mechanism confirmed in the harness; bounded to the bottom
cluster; pure griefing; pre-launch.** Severity **LOW–MEDIUM**. (Last open candidate in the ledger — now closed.)

## The question (batch-03 side-lead)
`get_network_to_prune` deregisters the **non-immune** subnet with the **lowest `get_moving_alpha_price` (pEMA)** when
the network is at capacity (`SubnetLimit = 128`; finney is full) and someone registers a new subnet. A sustained short
depresses a subnet's spot → pEMA. Can an attacker force a **chosen** subnet's deregistration by tipping its pEMA below
the field?

## Mechanism — CONFIRMED (harness)
`poc_pruning_sabotage_redirect` (real runtime): set up four subnets, then call `get_network_to_prune`:

```text
[PRUNE] baseline victim=Some(NetUid(1)) (A); C (min price 0.001, immune) protected
[PRUNE] after within-bound depression of B: victim=Some(NetUid(2)) (B) -> redirect
[PRUNE] D depressed by the MAX ~9.75% is still safe: victim=Some(NetUid(2)) (still B)
```

`SKIP_WASM_BUILD=1 cargo test -p pallet-subtensor --lib poc_pruning_sabotage_redirect -- --nocapture`

So: (1) the prune targets the lowest **non-immune** pEMA; (2) **immunity protects new subnets** — C has the lowest price
but is skipped; (3) a within-bound pEMA depression of target B **redirects** the prune onto B; (4) a **healthy** subnet
D (10× the min) depressed by the **maximum** is still safe — out of reach.

## Why it is BOUNDED (the κ cap is the throttle)
`sim_l2b_pruning.py` — the short's footprint is capped at `B = λC = κ·T_ref` (κ = 0.05), which bounds the spot/pEMA
depression to **~9.75%** (scale-free in the reserve):

| reserve T | max depression | reach window (above min) | carry/day |
|----------:|---------------:|-------------------------:|----------:|
| 5,000     | 9.75%          | +10.80%                  | 3.56 TAO  |
| 26,278    | 9.75%          | +10.80%                  | 18.72 TAO |
| 100,000   | 9.75%          | +10.80%                  | 71.25 TAO |
| 203,942   | 9.75%          | +10.80%                  | 145.31 TAO |

So a short can only push a target below the prune-min if the target is **already within ~10.8% above it** (the bottom
cluster). It **cannot** prune a healthy mid/top subnet. The cost is sustained carry (a few-to-tens of TAO/day for a
near-min subnet, held ~1 day for the EMA to settle, per the ~8h half-life) until a registration fires.

## Impact (honest)
The attacker can choose **which** of the already-near-bottom subnets is deregistered (redirect the prune from the
natural-lowest onto a specific near-min victim), or **self-protect** via the long mirror (pump your own near-min subnet
out of the prune slot, pushing it onto the next-lowest — bounded by `LongKappa = 0.05` likewise). It is **pure
griefing / competitive sabotage** (no attacker profit), it only reorders the bottom cluster (the victim was already a
prune candidate), `NetworkImmunityPeriod ≈ 1,296,000 blocks (~180 days)` protects new subnets, and shorts are **OFF**
(pre-launch).

## Severity — LOW–MEDIUM
Forcing a specific subnet's deregistration is real harm to its owner/stakers, and the preconditions are reachable (at
capacity, established target in the bottom cluster, a registration event). But the κ cap confines it to the bottom
cluster (~10.8% window), it cannot touch a healthy subnet, it is pure griefing at a sustained carry cost, and it is
pre-launch. Not LOW-only (it can deterministically pick a near-min victim cheaply); not MEDIUM-plus (bounded, no
profit, victim already near-prune, pre-launch).

## Recommended fix
Make prune selection harder to sustain-manipulate: select on a **longer-horizon / more robust** price (or a
stake/activity-weighted metric) rather than the κ-cap-movable pEMA; and/or add **hysteresis** (don't reorder the prune
victim unless the pEMA gap exceeds the max single-actor depression). The immunity window already blunts the attack for
new subnets; tightening κ or the footprint cap further shrinks the reach window.

**PoC:** `tooling/poc/derivatives-poc.patch` → `poc_pruning_sabotage_redirect`. **Sim:** `tooling/sims/sim_l2b_pruning.py`.
