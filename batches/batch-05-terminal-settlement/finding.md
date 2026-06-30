# FINDING-04 — Short terminal settlement order dependence (MEDIUM, pre-launch)

**Component:** `pallet-subtensor` derivatives — `settle_shorts_on_dereg`.
**Status:** confirmed locally on `opentensor/subtensor#2764` head `1a7aa37` for short deregistration settlement.

## Root cause
`settle_shorts_on_dereg` collects short positions and settles them sequentially. For each position, it restores that
position's escrow to the subnet account and increases the live `SubnetTAO` reserve before calculating the same
position's spot cover cost. The quote for each later position therefore sees a reserve already mutated by earlier
positions' escrow restoration.

## Impact
Identical positions can receive different terminal equity solely because of storage/coldkey order. Splitting exposure
across coldkeys may not be equivalent to holding one economically equivalent position, and deregistration payout
fairness becomes hard to reason about at position-limit scale. Direct pool theft was not proven; the issue is terminal
settlement fairness/accounting.

## Proof
Repro:
```bash
SKIP_WASM_BUILD=1 cargo test -p pallet-subtensor terminal_settlement_pays_identical_shorts_different_equity -- --nocapture
```

Observed local output:
```text
[TERMINAL-ORDER] first equity = 332745565022 rao, second equity = 277162020499 rao
```

The isolated PoC inserts two identical short positions with the same floor, liability, escrow, decay accumulator, and
subnet state. Settlement removes both positions, but their terminal equity differs by more than `1 TAO`.

## Fix
Snapshot terminal reserves before per-position settlement and quote every position against the same snapshot. Another
safe shape is to restore all terminal escrow/aggregate state first, then quote all positions against that common restored
reserve. Add regressions that identical positions settle equally within rounding tolerance, split-vs-merged exposure is
equivalent, and settlement is independent of coldkey/storage ordering.
