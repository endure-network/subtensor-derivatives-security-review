# FINDING-03 — Coldkey-swap derivative aggregate orphaning (MEDIUM, pre-launch)

**Component:** `pallet-subtensor` derivatives and coldkey swap (`swap_coldkey.rs` + `derivatives/mod.rs`).
**Status:** confirmed locally on `opentensor/subtensor#2764` head `1a7aa37` for short positions; long mirror blocked by
the current staking-hotkey destination guard.

## Root cause
`do_swap_coldkey` treats the destination coldkey as fresh if `StakingHotkeys::<T>::get(new_coldkey).is_empty()` and the
destination is not itself a hotkey. That guard does not check derivative position storage. A coldkey can therefore hold
a short derivative position while having no staking-hotkey association.

During derivative rekeying, `swap_positions_for_coldkey_swap` takes the source short position. If the destination
already has a short position on the same subnet, the code decrements `ShortPositionCount` and drops the source position;
it does not close, settle, merge, or subtract the dropped position from `ShortAggregate`.

## Impact
After the swap, live position storage/count can report one position while aggregate open interest and footprint still
include two. The ghost aggregate/custody state is no longer reachable through the normal close/default/settlement path
for the dropped owner. This can consume capacity, keep active derivative state alive, and distort later settlement or
accounting. Direct value theft was not proven; the issue is storage-lifecycle/accounting integrity.

## Proof
Repro:
```bash
SKIP_WASM_BUILD=1 cargo test -p pallet-subtensor coldkey_swap -- --nocapture
```

Focused evidence:
```text
test tests::derivative_coldkey_swap::coldkey_swap_collision_orphans_short_aggregate ... ok
test tests::derivative_coldkey_swap::long_coldkey_swap_collision_is_blocked_by_staking_hotkey_guard ... ok
```

The short PoC creates source and destination short positions on the same subnet, runs `do_swap_coldkey`, and verifies:

- `ShortPositions(old_coldkey)` is gone.
- `ShortPositions(new_coldkey)` remains.
- `ShortPositionCount` is `1`.
- `ShortAggregate` is unchanged from the two-position aggregate.
- `ShortAggregate.q_sigma` is greater than the sum of live `ShortPositions` liabilities.

The long-side falsifier creates source and destination long positions, verifies both exist, and then verifies the swap is
rejected with `ColdKeyAlreadyAssociated` because `StakingHotkeys(new_coldkey)` remains non-empty after the long open.

## Fix
Reject coldkey swaps when `new_coldkey` already has any short derivative position on a subnet where the source also has
a short position. Alternatively, merge or settle the source position during swap and update aggregate, custody, active
subnet, and flow state atomically. Keep a long-side regression so future staking-hotkey cleanup changes cannot make the
same collision reachable without aggregate-safe handling.
