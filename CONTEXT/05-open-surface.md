# 05 — Open attack surface (LEADS, not verdicts)

Pursue, refine, or **disprove**. These are questions, not findings. Don't assume any is real or unreal — verify.

## Economic / accounting
- **Emission-redirection (L2):** a sustained short depresses a subnet's spot → its EMA price (`SubnetMovingPrice`) →
  its price-based emission share, redistributing block TAO to other subnets the attacker holds. Reviewer-acknowledged.
  Needs the live coinbase loop (the mock stubs it). *(batch-03 is on this.)*
- **Self-cover under skewed weights (F-01):** confirmed but dormant (mainnet 0.5/0.5). Any path to `w≠0.5` re-arms it.
- **Cross-state manipulation:** open at one reserve/price state, close/settle at another (e.g. cold-EMA pump-open /
  restore-close). **SETTLED (batch-06) — not a drain:** the open(pumped)/close(restored) asymmetry yields a *real*
  `N1−K1` gap (≤ +33.5k TAO in the PoC), but the staking round-trip that manufactures the price move costs strictly
  more than the gap at every size (ratio→1.0⁺; best net −0.001 TAO). Residual (expected-defended, not separately
  reproduced): the long-side mirror and the regular `do_close_short` vehicle.
- **Rounding/precision dust:** `mul_tao`/`mul_alpha` truncation across the ~12 legs; long partial-close chains. The
  aggregate-Σ vs per-position `exp` decay drift was **verified (batch-07): the sign is the SAFE direction** (custody
  over obligations by ~7k rao even adversarially — per-position flooring across N claims exceeds the single aggregate
  floor). Remaining: the long partial-close-chain dust on its own.

## Atomicity / state
- **Non-transactional decay/dereg hooks:** `run_*_decay` / `settle_*_on_dereg` run in `on_initialize` (NOT rolled back);
  transfers are `.is_ok()`-guarded while the aggregate/omega advance unconditionally — could a failed transfer desync
  custody vs obligations? **SETTLED (batch-07) — no desync:** longs use can't-fail mints; short pool credits sit INSIDE
  the `.is_ok()` guard (only the safe-direction obligation *decrease* advances unconditionally — no #2662 phantom-credit
  path); and `custody ≥ Σ obligations` holds adversarially (`poc_decay_drift_custody_solvency`: +6,894 / +7,088 rao
  over). Residual hardening only: the unguarded equity transfer (`let _`) and the `None`-subnet-account early return.
- **Cold-EMA fresh-subnet window (F-02):** references fall back to live reserves before the EMA warms.
- **Coldkey-swap derivative collisions (F-03):** short destination collisions are confirmed; watch long-side reachability
  if staking-hotkey cleanup semantics change.
- **Terminal settlement ordering (F-04):** confirmed short settlement order dependence; investigate any long/dereg mirror.

## Manipulation / MEV
- **Multi-block EMA manipulation:** in-block is defended; the EMA itself moves over `EMAPriceHalvingBlocks`. Cost vs benefit?
- **Permissionless-default MEV / cross-position coupling** through the single shared pool.
- **Slippage guard vs weighted price:** `executable_price_ppb` uses naive `t/a`; at `w≠0.5` it bounds a different
  quantity than the true price (the client matches it, so it's internally consistent — but is there an edge?).

## Capacity / DoS
- Dereg settlement is O(positions ≤ 4096) in one block. The footprint-cap bypass (F-02) lets positions exceed the cap.
- `default_*` and `close_*_self` move the shared pool — sequencing across positions/blocks.
