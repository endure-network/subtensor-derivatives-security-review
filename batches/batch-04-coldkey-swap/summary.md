# Batch 04 — Coldkey-swap derivative aggregate orphaning (F-03)

**Verdict:** MEDIUM · confirmed · pre-launch · storage/accounting integrity bug, not proven direct theft.

**One-liner:** `do_swap_coldkey` treats a destination coldkey as fresh when `StakingHotkeys(new_coldkey)` is empty,
but a coldkey can hold a short derivative position without staking hotkeys. If source and destination both hold a
short on the same subnet, derivative rekeying drops the source position and decrements only the count, leaving
`ShortAggregate`/custody/footprint state for a position that no longer exists in `ShortPositions`.

**Proof:** `coldkey_swap_collision_orphans_short_aggregate` shows `ShortAggregate.q_sigma` remains greater than the
sum of live short-position liabilities after a source/destination collision. The long-side mirror was tested and is
currently blocked by `ColdKeyAlreadyAssociated` because `StakingHotkeys(new_coldkey)` remains non-empty after a long
open.

**Severity:** aggregate and position storage diverge, producing ghost open interest/footprint and unreachable custody
state with possible capacity griefing or settlement distortion. Direct value theft was not proven, and shorts/longs are
pre-launch.

**Files:** `finding.md`. **Fix:** reject destination collisions for derivative positions, or merge/settle source and
destination positions with full aggregate/custody/flow accounting.
