# Batch 07 — Non-transactional decay/dereg hook atomicity (custody desync probe)

**Verdict:** lead SETTLED · **DEFENDED** · a failed `on_initialize` hook transfer cannot desync custody vs obligations,
cause insolvency, or mint phantom value. No new finding (maps to recurring subtensor class #2662, which the authors
defended against here). Two informational hardening notes only.

**One-liner:** `run_*_decay` / `settle_*_on_dereg` run in the non-transactional `on_initialize`; their transfers are
`.is_ok()`-guarded while the aggregate/`omega` advance unconditionally. Three independent reasons it's safe: (1) **longs
use pure mint accounting** — no `transfer_tao` that can fail; (2) on shorts, the **value-creating pool credit is inside
the `.is_ok()` guard** while only the safe-direction obligation *decrease* advances unconditionally (a failed
restoration over-collateralizes custody, reclaimed by the sweep — no #2662 phantom-credit path); (3) the
**custody-solvency invariant holds adversarially**.

**Proof:** `poc_decay_drift_custody_solvency` drives the untested edge (many STAGGERED-entry positions, max decay, long
horizon) and measures `drift = custody − Σ(materialized floor+buffer+escrow)`:
`cfg A (40 varied) → +6,894 rao`, `cfg B (80 tiny, maximal per-position rounding) → +7,088 rao` — both **custody OVER
obligations** (the safe direction the docs claim). Structural reason: per-position materialization floors each of N
claims down (N floors) > the single aggregate-restoration floor, so `custody ≥ Σ claims` robustly. No insolvency ⇒ the
guarded transfers to the always-existing `subnet_account` never fail.

**Residual (hardening, not exploitable):** (a) `settle_shorts_on_dereg`'s equity transfer is unguarded
(`let _ = transfer_tao`) — fails only for a self-reaped coldkey with `equity < ED` (sub-ED dust burn, no attacker
profit); guard it / record unpaid. (b) the `get_subnet_account_id == None` early-return would orphan custody but isn't
reachable under the current dereg ordering; add a regression guard.

**Files:** `finding.md`. **Action:** none required; optional hardening on the two residuals. Settles the open-surface
"hook-transfer failure" lead.
