# LEAD SETTLED — Non-transactional decay/dereg hook transfers are DEFENDED (no custody desync)

**Component:** `pallet-subtensor` derivatives — the `on_initialize` hooks `run_short_decay` / `settle_shorts_on_dereg`
(custody-based) and `run_long_decay` / `settle_longs_on_dereg` (issuance-based), subtensor #2764.
**Status:** settled on `opentensor/subtensor#2764` — a failed hook transfer cannot desync custody vs obligations or
mint phantom value. No exploitable finding. Maps to the recurring subtensor class #2662
(failed-transfer-but-bookkeeping-advances) — and the authors defended against exactly that here.

## The question (from open-surface)
`run_*_decay` and `settle_*_on_dereg` run in `on_initialize`, which is **not** transactional — a mid-hook failure is
**not** rolled back. Their TAO transfers are `.is_ok()`-guarded (or, in one spot, ignored with `let _`) while the
aggregate / `omega` advance **unconditionally**. Could a failed hook transfer desync custody vs obligations (an
insolvency / phantom-value bug)?

## Why it is DEFENDED (three independent reasons)

**1. Longs are structurally immune.** `run_long_decay` and `settle_longs_on_dereg` use **pure issuance accounting**
(`increase_provided_alpha_reserve`, `increase_stake_for_hotkey_and_coldkey_on_subnet`) — there is **no `transfer_tao`**
that can fail. Restoration/settlement mints cannot partially fail, and total mint ≤ total open-time burn (the existing
`proof_multi_position_decay_conserves` asserts no net Alpha mint). The atomicity surface is **short-only**.

**2. The credits are guarded; only the SAFE-direction bookkeeping advances unconditionally.** In `run_short_decay`,
the obligation **decrease** (`r_sigma`/`e_sigma` down, `omega` up) advances unconditionally, but the value-creating
pool credit (`increase_provided_tao_reserve` + `TotalStake +=`) sits **inside** the `.is_ok()` transfer guard. So a
failed restoration leaves obligations reduced **and** the TAO retained in custody = **over-collateralized** (custody >
obligations), reclaimed by the terminal sweep. There is **no #2662-exploitable path**: no user record is ever credited
without its backing transfer succeeding. (The same shape holds for the escrow leg of `settle_shorts_on_dereg`.)

**3. The custody-solvency invariant holds adversarially.** The guarded transfers target the always-existing
`subnet_account`, so they can only fail on a custody shortfall (insolvency). The module doc claims "the aggregate
Σ-decay floors faster than the per-position exp decay ⇒ custody ≥ obligations." The existing suite tests this only with
**same-entry positions + regular close**; the PoC drives the untested edge — many **staggered-entry** positions, max
decay, long horizon — and measures `drift = custody − Σ(materialized floor+buffer+escrow)`:

```text
[DRIFT] cfg=0 n=40 size=7x(1..11)  custody=1759270654897  Σclaims=1759270648003  drift=+6894 rao  (+0.000007 TAO)
[DRIFT] cfg=1 n=80 size=1x(1..3)   custody= 163634680780  Σclaims= 163634673692  drift=+7088 rao  (+0.000007 TAO)
```

`SKIP_WASM_BUILD=1 cargo test -p pallet-subtensor --lib poc_decay_drift_custody_solvency -- --nocapture`

Both configs leave custody **OVER** obligations (the safe direction), including cfg B which maximizes per-position
floor rounding (80 tiny positions). This is structural: per-position materialization floors each of the N claims
**down** (N separate `mul_tao` floors), which loses more precision than the single aggregate-restoration floor, so
`custody ≥ Σ claims` robustly. No insolvency ⇒ the guarded transfers never fail.

## Residual (informational hardening, not exploitable)
- **Unguarded equity transfer.** `settle_shorts_on_dereg` pays trader equity with `let _ = transfer_tao(custody,
  coldkey, equity)` (return ignored). Given solvency, this only fails when the trader's **own** coldkey is reaped
  (below ED) **and** `equity < ED` — a self-inflicted sub-ED dust loss, burned by the terminal sweep, with **no
  attacker profit**. Hardening: guard it (or record unpaid equity) so a future ED/precision change can't silently burn
  a non-dust equity.
- **Early-return orphaning.** `settle_shorts_on_dereg` returns early if `get_subnet_account_id` is `None`, which would
  orphan custody. Not reachable under the current dereg ordering (settlement runs "before the pool is drained"), but
  worth a regression guard.

## Bottom line
The non-transactional decay/dereg hooks do **not** admit a custody-vs-obligations desync, insolvency, or phantom mint.
The authors guarded the value-creating credits and let only safe-direction bookkeeping advance unconditionally, and the
custody-solvency invariant holds even adversarially. No new finding; the two informational items above are hardening
only. Settles the open-surface "hook-transfer failure" lead.

**PoC:** `tooling/poc/derivatives-poc.patch` → `poc_decay_drift_custody_solvency`.
