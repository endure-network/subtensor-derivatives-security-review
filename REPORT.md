# Security review — Bittensor covered continuous-unwind derivatives (subtensor PR #2764)

**Target:** `pallet-subtensor` covered short/long derivatives (`open_*`/`close_*`/`close_*_self`/`default_*`),
the EMA references (`short_t_ref`/`long_a_ref`), and the `pallet-subtensor-swap` Balancer engine, at PR #2764
head `1a7aa37` (`feat/pool-borrowing-spec`, base `devnet-ready`, open/unmerged as of 2026-06-29).
**Client under test:** `btcli` PR #1007 (`btcli deriv`).
**Status of feature:** shorts/longs are **default-OFF** (`ShortsEnabled`/`LongsEnabled`) and **not on mainnet** — this is a pre-launch review.

## Summary

| # | Finding | Severity | Live today? | Class |
|---|---------|----------|-------------|-------|
| 01 | Self-cover close prices the liability on a different curve than open ⇒ pool drain under non-0.5 Balancer weights | **MEDIUM** | No (all mainnet pools at 0.5/0.5) | Latent fund-loss / conservation break |
| 02 | Cold-EMA fresh-subnet window bypasses short and long capacity caps | **MEDIUM** | No (pre-launch) | Risk-limit bypass / hardening |
| 03 | Coldkey-swap destination collision can orphan short derivative aggregate state | **MEDIUM** | No (pre-launch) | Lifecycle/accounting integrity |
| 04 | Short **and long** terminal settlement can pay identical positions different equity based on storage order | **MEDIUM** | No (pre-launch) | Terminal-settlement fairness/accounting |

All four are **real, harness-confirmed code defects** in pre-launch derivative paths. They are currently
non-exploitable on mainnet because `ShortsEnabled`/`LongsEnabled` are default-off and the affected feature is not live,
but they should be fixed before any production enablement. Three further **LOW / LOW–MEDIUM** findings
(emission-redirection **L2a**, pruning-sabotage **L2b**, and unguarded terminal equity transfer **F-06**) and three
**disproved** escalation probes (cross-state drain, hook atomicity, slippage rollback) are documented below; the
complete ledger is in `FINDINGS.md`.

**Independent verification round (2026-07-01).** Findings 01–04 and both LOW economic findings were re-checked by a
parallel round of independent audit agents — two blind first-pass auditors (working from the unbiased `CONTEXT/` only)
and two adversarial verifiers — each reproducing in the real harness. Result: **all findings upheld, none overturned,
no false positives**; the three disproved probes were independently re-confirmed **defended** (including the long-mirror,
regular in-kind, and amortized-pump cross-state regimes this report had earlier left un-reproduced); and one scope
correction is adopted here — **F-04 is not short-only: the long terminal-settlement mirror is confirmed with the same
root cause (F-04b, below).** The round also surfaced one new LOW code defect (F-06). Full detail, per-agent, in
`batches/batch-08-verification/`.

**External code review (2026-07-01).** A separate full-PR code review (10 first-pass reviewers across four provider
families + security/tests/maintainability/database specialists, evidence-adjudicated) was then run over the entire
#2764 diff. It **independently corroborated** findings 02, 03 (which it rates HIGH), 06 (HIGH), `executable_price_ppb`,
and our χ/flow-dead conclusion, and surfaced four additional **in-scope** defects — all re-verified against the source
here and folded in: **F-07** — unbounded terminal-settlement iteration under a *fixed* dissolve weight (**HIGH**,
liveness/DoS — the **highest-severity item in this report**); **F-08** — 1:1 exact-output fallback for non-dynamic pools
in settlement (MEDIUM); **F-09** — long terminal equity realized asymmetrically as Alpha stake (LOW–MEDIUM); **F-10** —
`limit_price` binds the fee-less raw spot, not the realized price (LOW). F-06 is correspondingly raised to **LOW→MEDIUM**.
See "Cross-reference: independent full code review" below.

> **Severity basis (unchanged, made explicit).** We hold all four confirmed findings at **MEDIUM** on a *pre-launch
> fund-handling* rubric (active fund-handling machinery; fix-before-enable). A strict *current-exploitability*
> bug-bounty rubric would score most of them **LOW/informational** (dormant, pre-launch, no proven theft today). Both
> independent verifiers concurred the MEDIUMs are defensible but lean toward the generous end; we **keep MEDIUM and
> disclose the tension** rather than split the rating per finding.

## Method

Code analysis → closed-form Python sims → **PoC tests in the project's own mock-runtime harness** (`cargo test
-p pallet-subtensor`, real pallet + real Balancer engine) → **live-mainnet state verification** (finney RPC) →
**in-flight-change (amplifier) sweep** (`gh`, recent PRs/releases). Every PoC runs against the real compiled code.

---

## FINDING-01 — Self-cover close / open pricing-curve asymmetry (MEDIUM, latent)

### Root cause
`do_open_short` ([mod.rs L289-409]) sizes the Alpha liability `Q` and escrow `E` with **weight-unaware
constant-product** math (`solve_phi(N, t_live)`, `Q = φ·a_live`, `E = φ·t_live`). `do_close_short_self`
([mod.rs L544-629]) prices the **buyback** of `Q` through the **weight-aware** Balancer engine
(`sim_tao_in_for_alpha_out` → `get_quote_needed_for_base = T·((A/(A−Q))^(w1/w2) − 1)`). The two legs price on
**different curves** whenever a pool's Balancer weights `w1/w2 ≠ 1` (i.e. ≠ 0.5/0.5). The long mirror is symmetric
(`do_open_long` books `D=φ·t_live` naive; `do_close_long_self` sells via the weighted engine).

### Impact
At a weight ratio `r = w1/w2`, an **open + immediate self-close at an unchanged price** returns `≈ P + N·(1−r)`
instead of `P` — the surplus `N·(1−r)` is drained directly from the subnet pool (i.e. from stakers). Short side
leaks at `r<1`; long side at `r>1` (so either drift direction is exploitable). Riskless, repeatable, capital-scaling.

### Proof — 7 PoCs in `pallets/subtensor/src/tests/derivatives.rs`
`SKIP_WASM_BUILD=1 cargo test -p pallet-subtensor --lib poc_ -- --nocapture`

| test | weight | result |
|------|--------|--------|
| `poc_baseline_no_skew_no_leak` | 0.5/0.5 | **+0.000074 TAO (control: no leak ⇒ skew is the cause)** |
| `poc_short_self_close_leaks_under_skewed_weights` | r=0.5 | +499.13 TAO (pool −499.13, issuance 0) |
| `poc_short_self_close_leaks_small_skew` | r=0.99 | +985.23 TAO on a 100k position (~1%/round-trip at 0.5% drift) |
| `poc_short_self_close_leaks_with_fee` | r=0.5, ~3% fee | +483.42 TAO (survives the fee) |
| `poc_long_self_close_leaks_under_skewed_weights` | r=2.0 | +499.13 Alpha (mirror) |
| `poc_repeat_drain` | r=0.5, 5× | +2,499.57 TAO; `pool drained == attacker gained` to the rao |
| `poc_emission_drift_then_leak` | drift 0.5→0.52 via REAL `adjust_protocol_liquidity` | +22,394 TAO |

Closed-form model (`sim_weighted_v2_pricefixed.py`) matches the on-chain numbers to the decimal.

### Why it is currently DORMANT (live-state verification)
A finney RPC probe of `Swap.SwapBalancer` for **all 128 subnets** returned **`w_quote = 0.5` (`w1/w2 = 1.0`)
everywhere** (max deviation ~1e-9; cross-checked: `MovingPrice == T/A`, the `w=0.5` signature). At 0.5/0.5 the
Balancer formula reduces to constant product and `K0 = N` exactly (the control PoC confirms +0.0 TAO). **The
precondition (`w≠0.5`) exists on zero mainnet subnets today**, so the live extraction is `$0`.

### Reachability (why it can't currently be armed)
The system **structurally pins weights at 0.5**: fresh pools seed reserves *at* the target price (`p=y/x ⇒ w=0.5`);
protocol emission injection is proportional (PR #2758 explicitly reserves any disproportionate excess rather than
shifting weights); and the user-liquidity extrinsics (`add_liquidity`/`remove_liquidity`/`modify_position`/
`toggle_user_liquidity`/`disable_lp`) are **permanently deprecated** `Err(Deprecated)` stubs (user-LP was
deliberately removed when Balancer was adopted, Feb–Mar 2026). The only non-0.5 source is the one-time v3→balancer
migration (price≠reserve ratio), and live finney reads 0.5 even there. **It is a code-change away, not a config flip.**

### Amplifier sweep (recent/in-flight changes)
No recent or in-flight change arms it. `cap exp_scaled at 1` (2026-06-26) is conditional on `dx≥0` (exact-input)
and does **not** touch the exact-output buyback (`dx<0`, uncapped). The new swap-size caps **mitigate**
(oversized self-cover ⇒ sim errors ⇒ rejected). Emission rework keeps weights at 0.5. No PR re-enables user-LP.

### Severity rationale: MEDIUM
High impact (direct theft of pooled funds) in **active** weighted-pool machinery that explicitly supports `w≠0.5`,
in a **pre-launch** feature → fix-before-enable. Not LOW (impact is high; machinery is live; even 0.5% drift ⇒ ~1%
leak). Not HIGH/CRITICAL (no currently-reachable trigger; real drift is ~1e-9 and non-accumulating). Escalates to
HIGH the instant anything re-enables disproportionate liquidity provision or a disproportionate emission/init mode.

### Recommended fix
Make the OPEN weight-aware: derive `Q`/`E`/`φ` through the **same** swap engine the self-cover close uses, so
`K = N` holds at any weight (open and close on one curve). Alternatives: price the self-cover buyback on the open's
naive curve; or reject/clamp self-cover when `|w−0.5|` exceeds an epsilon. Add a conservation regression test for
the `close_*_self` path under skewed weights (the existing weighted-conservation test covers only the in-kind close).

---

## FINDING-02 — Cold-EMA fresh-subnet capacity-cap bypass (MEDIUM, hardening)

### Root cause
`SubnetAlphaInMovingReserve` (the block-lagged `A_EMA` that the T_ref/A_ref manipulation-resistance relies on) is written
in only two places: a one-time migration that seeds **existing** subnets, and the per-block `update_moving_price`
tick. **There is no initialization at subnet creation.** So a freshly-created dynamic subnet has `A_EMA = 0` and
`pEMA = 0` until its EMA warms, and `short_t_ref = min(t_live, pEMA·A_EMA)` ([mod.rs L136-149]) falls back to the
**live, in-block-manipulable** reserve. `long_a_ref` mirrors this with the live Alpha reserve. The crossover/sandwich manipulation-resistance
tests all use a *warm* EMA; the only cold-EMA test (`small_open_on_fresh_subnet_with_cold_ema`) asserts merely that a
small open succeeds, with no bound.

### Impact
During the warmup window an attacker can pump the relevant live reserve in-block to inflate `T_ref`/`A_ref`, inflating
the capacity cap and retained proceeds, and open shorts or longs **beyond the intended risk limit** on a fresh subnet.

### Proof
```
honest cap = 119 TAO -> pumped cap = 399 TAO ; the over-cap open rejected at the honest reserve SUCCEEDS after pump
long_open_cold_ema_live_alpha_bypasses_capacity_cap ... ok
```
This is exactly the sandwich `sandwich_open_cannot_breach_capacity_cap` proves IMPOSSIBLE on a warm subnet.

### Severity rationale: MEDIUM (hardening)
It re-enables a known attack class the authors explicitly defend for warm subnets, but it is **pre-launch**,
**fresh-subnet-scoped** (only during EMA warmup, before the subnet starts emitting), and it is a **risk-limit
bypass, not a direct drain** — at the live 0.5/0.5 baseline `K0=N`, so an oversized cold-window position still
returns ~`P` on self-close (no minting). **Cross-state escalation — settled (batch-06), not a drain:** opening at an
in-block-pumped reserve and cash-settling at the restored reserve yields a *real* `N1−K1` gap (up to +33.5k TAO in the
PoC), but the staking round-trip (`add_stake`/`remove_stake`) that manufactures the price move costs strictly more than
the gap at every size (`pump_loss/short_leg → 1.0⁺`; best net −0.001 TAO). So F-02 stays MEDIUM and does **not**
escalate to direct theft. PoC: `poc_cold_ema_cross_state_short_self_close_drain`, `poc_cold_ema_cross_state_fine_pump_sweep`.

### Recommended fix
Seed `SubnetAlphaInMovingReserve` (and the price EMA) at **subnet creation**, mirroring the migration's seeding for
existing subnets; or make the cold-EMA fallback conservative (reject derivative opens until the EMA warms, or use a
floor reference) instead of falling back to the live reserve.

---

## FINDING-03 — Coldkey-swap derivative aggregate orphaning (MEDIUM, pre-launch)

### Root cause
`do_swap_coldkey` treats a destination coldkey as fresh if `StakingHotkeys(new_coldkey)` is empty and the destination
is not itself a hotkey. A coldkey can still hold a short derivative position without staking hotkeys. During rekeying,
`swap_positions_for_coldkey_swap` drops the source short position when the destination already has a short position,
and only decrements `ShortPositionCount`; it does not settle the dropped position or subtract it from `ShortAggregate`.

### Impact
After the swap, position storage/count report one live position while aggregate open interest/footprint still include
the dropped position. The resulting ghost aggregate/custody state is no longer reachable through normal close/default
paths. Direct theft was not proven; the issue is storage/accounting integrity and potential capacity/settlement griefing.

### Proof
`SKIP_WASM_BUILD=1 cargo test -p pallet-subtensor coldkey_swap -- --nocapture`

The focused test `coldkey_swap_collision_orphans_short_aggregate` passes by showing `ShortAggregate.q_sigma` remains
greater than the sum of live `ShortPositions` after a source/destination collision. The long-side mirror was tested and
is currently blocked by `ColdKeyAlreadyAssociated` because `StakingHotkeys(new_coldkey)` remains non-empty after a long
open.

> The independent code review (2026-07-01) corroborates this finding and rates it **HIGH**, adding that
> `cleanup_short_if_empty` can then remove the aggregate/active-set based on the decremented count while a destination
> position still exists — so per-block decay restoration and settlement subsequently operate on phantom/missing state.

### Recommended fix
Reject coldkey swaps when the destination already has a short derivative position on any subnet where the source also
has a short position, or merge/settle the source position with full aggregate/custody/flow accounting.

---

## FINDING-04 — Terminal settlement order dependence, short AND long (MEDIUM, pre-launch)

### Root cause
`settle_shorts_on_dereg` ([mod.rs L738-788]) restores each position's escrow to the live subnet reserve immediately
before quoting that same position's spot cover cost. Because settlement iterates positions sequentially
(`ShortPositions::iter_prefix`), later positions quote against a pool already mutated by earlier positions' escrow
restoration. Identical positions can receive different terminal equity solely because of storage iteration order.
**The long mirror is identical (F-04b):** `settle_longs_on_dereg` ([long.rs L494-535]) restores each position's Alpha
escrow into the live reserve before quoting its own `long_spot_close_cost`, so identical longs also settle to different
equity.

### Impact
Terminal payout fairness depends on coldkey/storage order rather than position economics. Splitting exposure across
coldkeys may not be equivalent to a single equivalent exposure. Value is **conserved** (over-charged cover is
recycled/burned, escrow rejoins the pool, equity is paid to the trader), so this is a terminal-settlement
fairness/accounting + non-determinism bug on **both** sides — not proven as direct pool theft.

### Reachability (F-05 — force-reachable via subnet prune)
Terminal settlement is **not** limited to a subnet owner voluntarily dissolving. When the network is at `SubnetLimit`
(128), `do_register_network` calls `get_network_to_prune` → `do_dissolve_network`, which runs `settle_shorts_on_dereg`
/ `settle_longs_on_dereg` **before** `destroy_alpha_in_out_stakes`. So **any** party who registers a subnet at capacity
forces the lowest-price-EMA non-immune subnet through terminal settlement — the same prune target an attacker can bias
via the **L2b** pruning-sabotage lever. This converts F-04 from "owner-only" into "permissionless-ish under capacity";
it adds no drain on its own, but it is why fixing F-04's order-dependence matters.

### Proof — short and long, independently reproduced (2026-07-01)
```bash
# short (followup patch, batch-05):
cargo test -p pallet-subtensor --lib terminal_settlement_pays_identical_shorts_different_equity -- --nocapture
# long mirror F-04b (verification-round patch — poc_long_terminal_settlement_order_dependent):
cargo test -p pallet-subtensor --lib poc_long_terminal_settlement_order_dependent -- --nocapture
```
```text
[TERMINAL-ORDER]  first equity = 332745565022 rao, second equity = 277162020499 rao          # short
[F-04 long NEW]   identical longs -> equity(alpha) c1=49974809931 c2=41637278252 |diff|=8337531679 (8.3375 alpha-TAO)   # long F-04b
```
A second, independent long-mirror implementation (verify-gpt's `terminal_settlement_pays_identical_longs_different_equity`,
first = 277.16 / second = 332.75 rao) is archived in `batches/batch-08-verification/agent-outputs/`. F-04b was
previously flagged only "investigate"; two independent agents each wrote a PoC and both confirm the long mirror with
the same root cause and magnitude as the short side.

### Recommended fix
Quote every terminal position against a common reserve snapshot, or restore all escrow/aggregate terminal pool state
before any per-position quote — on **both** `settle_shorts_on_dereg` and `settle_longs_on_dereg`. Add regression checks
that identical positions settle equally and that split-vs-merged exposure is equivalent within rounding tolerance.

---

## Lower-severity confirmed findings

Below the four MEDIUMs sit two cross-subnet economic findings (both throttled by the `κ = 0.05` capacity cap; detail in
`batches/batch-03-emission-redirection/`) and one fund-handling code defect (**F-06**). All are pre-launch (shorts OFF).

- **L2a — Emission-redirection (LOW, infeasible).** A sustained short depresses a subnet's spot → price-EMA → its
  price-based emission share (`get_shares` → `get_shares_price_ema`), redirecting block TAO to other subnets. The
  mechanism is real, but `sim_l2_economics.py` shows the κ cap bounds the depression to ~9.75%, and at that maximum the
  best-case **redirected-emission / carry = 0.12–0.25** — the short's carry alone is **4–8× the benefit**, even assuming
  100% capture and no arbitrage. Economically infeasible. *Design note (D-chi-moot):* the derivatives' χ/`SubnetTaoFlow`
  flow-neutrality machinery defends a DEAD channel (`get_shares_flow` is uncalled); the live emission channel is price-EMA.
- **L2b — Pruning sabotage (LOW–MEDIUM, bounded).** `get_network_to_prune` deregisters the **non-immune** subnet with
  the lowest price-EMA at capacity (128) on registration. A sustained short can **redirect** that prune onto a chosen
  victim — proven in `poc_pruning_sabotage_redirect` (redirect + immunity protection + the bound). But the κ cap limits
  the depression to ~9.75% (`sim_l2b_pruning.py`), so only subnets **already within ~10.8% of the min** (the bottom
  cluster) are reachable; a healthy subnet is out of reach. Pure griefing (no profit) / self-protection via the long
  mirror; immunity ~180 days; pre-launch. Fix: select the prune victim on a longer-horizon / robust price, with hysteresis.
- **F-06 — Unguarded terminal equity transfer can silently burn a trader's payout (LOW→MEDIUM, pre-launch).** In
  `settle_shorts_on_dereg` the equity payout is fire-and-forget — `let _ = Self::transfer_tao(&custody, &coldkey,
  equity.into())` ([mod.rs L769-772]) with no `.is_ok()` check (unlike the escrow-restore credit at [mod.rs L754-759],
  which *is* guarded) — and any custody remainder is then swept to issuance by `recycle_custody_tao(&custody,
  TaoBalance::MAX)` ([mod.rs L784]). If the transfer fails (destination coldkey left below the existential deposit, or
  dust-empty), the equity is **not paid and is then burned** by the sweep — a silent loss of funds the trader was owed.
  **Worse, `ShortTerminalSettled { equity }` is emitted regardless of transfer success** ([mod.rs L775-780]): the
  on-chain event asserts a payment that did not happen, corrupting off-chain reconciliation. batch-08 held this LOW (the
  burn itself is narrow — ED-edge, dereg-gated, pre-launch, no third-party profit); the independent code review (which
  rates it HIGH, 3 reviewers incl. security) adds the event-integrity dimension, so we raise it to **LOW→MEDIUM**. Fix:
  cap equity to transferable custody / hold unpaid equity in a refundable ledger, and emit only the amount transferred.

---

## Settled escalation probes (negative results)

We also pursued the highest-upside escalation angles and **disproved** them with the same harness discipline — useful
for triage, since they bound the blast radius of the confirmed findings:

- **Cross-state drain (F-02 escalation, batch-06 + verification round):** opening a short at an in-block-pumped reserve
  and cash-settling at the restored reserve yields a *real* `N1−K1` gap (≤ +33.5k TAO), but the staking round-trip that
  manufactures the price move costs strictly more than the gap at every size (`pump_loss/short_leg → 1.0` from above;
  best net −0.001 TAO). F-02 does **not** escalate to direct theft. The verification round additionally **attacked**
  three regimes this report had left un-reproduced — all **defended** (reproduced 2026-07-01, `derivative_break_opus.rs`):
  amortizing one pump across `m∈{1,4,16}` self-closes (best net **−0.826 TAO**, more negative as `m` grows), the regular
  in-kind `close_short` vehicle (best net **−0.0025 TAO**), and the long-mirror cold-`A_ref` cross-state (best net
  **+3012 rao ≈ 0**, dust both signs). PoC: `poc_cold_ema_cross_state_*`, `break_amortized_pump_short_self_close`,
  `break_regular_close_short_cross_state`, `break_long_mirror_cross_state`.
- **Non-transactional hook atomicity (batch-07):** the `on_initialize` decay/dereg hooks (`run_*_decay` /
  `settle_*_on_dereg`) cannot desync custody vs obligations — longs use can't-fail mints; short pool credits are
  `.is_ok()`-guarded (only safe-direction bookkeeping advances unconditionally); and `custody ≥ Σ obligations` holds
  adversarially (`poc_decay_drift_custody_solvency`: +6,894 / +7,088 rao over, staggered entries + max decay). Maps to
  and defends against recurring class #2662. Hardening: guard the one ignored equity transfer in `settle_shorts_on_dereg`
  (now tracked as **F-06** above).
- **Slippage-failure rollback (batch-02 follow-up):** the tested derivative-open slippage-failure paths roll back
  cleanly (`slippage_failure_rolls_back_state` passes); no state desync on the extrinsic paths probed.

---

## Independent verification round (2026-07-01)

To stress-test this report before submission, four independent audit agents were run in parallel against the same
target, each reproducing in the real harness: **two blind first-pass auditors** (given only the unbiased `CONTEXT/`,
withheld from `FINDINGS.md`/`REPORT.md`) and **two adversarial verifiers** (tasked to overturn every claim). Raw
deliverables are archived under `batches/batch-08-verification/`.

| Agent | Role | Verdict | Contribution |
|-------|------|---------|--------------|
| verifier A | adversarial re-check | **all 6 findings + 3 probes UPHELD; 0 overturned; 0 false positives** | strengthened F-01 dormancy; independently broke the 3 un-reproduced cross-state regimes |
| verifier B | adversarial re-check | **all 6 findings + 3 probes UPHELD; found F-04 scope understated** | contributed the F-04b long-mirror PoC; flagged `executable_price_ppb` naive pricing |
| auditor A | blind first pass | broke none of the priced economics | independently re-derived F-02 + F-04; found F-04b and F-06; disproved 5 drain hypotheses |
| auditor B | blind first pass | did not deliver (context exhaustion) | — (run archived for completeness) |

**Outcome.** Every confirmed finding and every "defended" verdict was independently reproduced; nothing was overturned;
no false positive was found. Two substantive results were folded into this report: **F-04b** (long terminal-settlement
mirror, promoted "investigate" → confirmed) and **F-06** (unguarded terminal equity transfer, new LOW). The three
disproved cross-state probes were positively re-defended (see the escalation-probes section).

**F-01 dormancy — strengthened.** A verifier added an emission-stability test (`stability_realistic_emission_keeps_weight_pinned`)
showing that *proportional* protocol emission is an exact fixed point at `w=0.5` (drift `0.00e0` over 200 injections)
and that a seeded migration-style skew **self-heals** toward 0.5 (0.4500 → 0.4571 over 400 injections). This confirms
at the code level — not only via the finney snapshot — that `w≠0.5` is a code change away and self-correcting; F-01's
dormancy is robust, if anything *more* dormant than the live probe alone shows.

**Honesty note (recorded).** Two independent agents' first long-mirror cross-state harness printed a spurious
"+80,000 TAO drain" that was a P&L-measurement bug (initial balance captured *after* the manipulation stake, so the
recovered principal counted as profit); after fixing the measurement (init before the pump) the long mirror nets ~0.
Two separate harnesses hitting and self-correcting the same artifact is the exact "don't claim a leak you didn't truly
measure" discipline this review holds itself to.

**Observation (now promoted to F-10).** `executable_price_ppb` uses the naive fee-less `T/A` spot price rather than the
fee+weight-aware realized cost ([mod.rs L802-811]); this weakens `limit_price` protection more broadly than first
thought — the fee gap bites even at 0.5/0.5. The independent code review promoted this to a MEDIUM correctness finding;
we carry it as **F-10** in the cross-reference section below.

**Process note.** The four agents shared one target checkout, so their PoC test files collided in the shared tree; each
agent's work was preserved separately and the substantive findings are unaffected, but future parallel rounds should
give each agent an isolated checkout (captured in `METHODOLOGY.md`).

---

## Cross-reference: independent full code review (2026-07-01)

After the internal verification round, a separate **full-PR code review** (10 first-pass reviewers across four provider
families + security / tests / maintainability / database specialists, evidence-adjudicated) was run over the entire
#2764 diff (4 high / 14 medium / 12 low). Most of its volume is code-quality / testing / weight-benchmark / documentation
work outside this report's economic + reachability scope (see "Out of scope" below); the security-relevant overlap is
reconciled here. **Every item we adopt below was re-verified against the source ourselves** (code-level — these are
structural/correctness defects, not economic PoCs). The review is archived in
`batches/batch-09-external-review-reconciliation/`.

### Independent corroboration
- **F-03** (coldkey-swap orphaning) — independently hit; rated **HIGH**; adds that `cleanup_short_if_empty` can drop the
  aggregate/active-set while a destination position still lives.
- **F-06** (unguarded equity transfer) — independently hit and rated **HIGH** (see the event-integrity angle we adopt).
- **F-02** (cold-EMA cold-start) — a reviewer observation confirms post-migration newly-created subnets still cold-start
  by falling back to the live reserve.
- **`executable_price_ppb`** and **D-chi-moot** — both corroborated (promoted / refined below).

### New in-scope findings adopted (code-verified)

**F-07 — Unbounded terminal settlement under a fixed dissolve weight (HIGH, pre-launch).**
`settle_shorts_on_dereg` / `settle_longs_on_dereg` do `iter_prefix(netuid).collect()` and loop over **every** position
(materialize + up to two `transfer_tao` + recycle each), while the `dissolve_network` dispatch carries a **fixed** weight
(`reads(6)/writes(31)`, [dispatches.rs L1234-1236]) that does not scale with position count. Per-side caps clamp to
`[1,4096]` ([mod.rs L892], [long.rs L555]) ⇒ up to ~8192 settlements in one dissolution block. A heavily-populated subnet
can push dissolution past the block's real budget — a **liveness/DoS** on consensus-critical chain maintenance — and it
composes with **F-05**: an attacker pre-stuffs a subnet with min-input positions, then forces it through the prune path.
The authors deliberately capped at 4096/side ("so governance can't lift the dereg-settlement" cost) — a partial
mitigation — but the fixed weight + unbounded loop remain a weight-accounting gap the PR body itself flags for
incremental settlement. **This is the highest-severity item in the report** (liveness, not dormant-economic), though
still pre-launch. Fix: paginated/incremental settlement, or benchmarked weight that scales with live position count.

**F-08 — 1:1 exact-output fallback for non-dynamic pools in settlement (MEDIUM, pre-launch).**
`sim_tao_in_for_alpha_out` / `sim_alpha_in_for_tao_out` return a non-market **1:1** cost for `mechanism ≠ 1`
([impls.rs L412-418, L440-446]), and `settle_*_on_dereg` never re-assert the subnet is still dynamic. A position that
survives a dynamic→legacy mechanism transition would have its terminal cover/equity valued off 1:1 — a potential unbacked
payout. Fix: define settlement for non-dynamic pools; don't silently value derivative liabilities at 1:1.

**F-09 — Long terminal equity realized asymmetrically as Alpha stake (LOW–MEDIUM, pre-launch).**
`settle_longs_on_dereg` credits long terminal equity as **minted Alpha stake** (`increase_stake_for_hotkey_and_coldkey_on_subnet`
+ `SubnetAlphaOut`, [long.rs L519-523]), then `destroy_alpha_in_out_stakes` distributes the pot pro-rata — whereas shorts
pay **TAO** directly from custody. The asymmetry can dilute/under-realize the computed equity once the pot is distributed;
no test asserts the final TAO-equivalent through destruction. (Because longs *mint* stake — a can't-fail credit — the
F-06 burn does **not** apply to the long side; the long-side risk is dilution, not silent loss.) Fix: document the
asymmetric terminal semantics, or settle long equity through a TAO-equivalent-preserving mechanism.

**F-10 — `limit_price` binds the fee-less raw spot, not the realized price (LOW, pre-launch).**
`ensure_price_at_least/at_most` use `executable_price_ppb` — a fee-less raw `SubnetTAO/SubnetAlphaIn` ratio
([mod.rs L804-811]) — while close-cost quotes route through the fee- and weight-aware engine (`SimSwapOpts::WITH_FEES`).
So `limit_price` can pass while the fee/weight-aware realized price is outside the intended bound: weaker MEV/sandwich
protection than the parameter implies, **even at 0.5/0.5** (the fee gap alone). Fix: enforce `limit_price` against the
engine quote / post-trade effective price. Couples to F-01's fix.

### Reconciliations (our DEFENDED verdicts stand; hardening framing adopted)
- **C-rollback (review HIGH "late checks after mutations"):** our `slippage_failure_rolls_back_state` test confirms the
  probed open/close paths *do* roll back — but only via the **implicit** FRAME extrinsic-rollback guarantee; the dispatch
  wrappers are not `#[transactional]` and the repo uses explicit transactions elsewhere. We concur: the current behavior
  is safe, but the missing explicit transaction boundary is a real, undocumented fragility (breaks for any future
  non-extrinsic caller). Fix: wrap each multi-step transition in `#[transactional]`/`with_transaction`, checks-first.
- **C-atomicity (review accuracy edges):** our solvency verdict stands (custody ≥ Σ obligations; no theft/insolvency),
  but the review correctly flags two accounting-**accuracy** edges on failure paths: `run_short_decay` commits the
  aggregate decrement *before* the restoration transfer (understates the aggregate if the transfer fails), and
  `recycle_custody_tao` decrements `TotalIssuance` *before* an unchecked `Exact` withdraw (a non-balance failure —
  lock/hold/hook — could desync issuance vs balances). Neither is a drain; both are hardening. Fix: transfer/withdraw
  first, commit accounting only on realized success.
- **D-chi-moot (χ default vs docs):** our conclusion holds — the flow→emissions channel is **dead** (`get_shares` uses
  only `get_shares_price_ema`; `get_shares_flow`/`get_ema_flow` are `#[allow(dead_code)]`/uncalled). The review adds a
  valid caveat we now record: `DerivativeFlowFactor` **defaults to `1.0`** ([lib.rs L1457]), so derivatives *do* write
  `SubnetTaoFlow` by default — a non-neutral write that contradicts DESIGN.md's "flow-neutral by default." It is inert
  only because the readers are dead code; it **arms latently** the instant the flow-based emission path is ever wired.
  Fix: default χ to 0, or reconcile the docs and gate enablement on an explicit χ acknowledgment.

### Out of scope (acknowledged, not absorbed)
The remaining ~16 review findings are code-quality / testing-coverage / weight-benchmark / documentation items —
placeholder extrinsic weights without benchmarks, migration weight miscounting, untested slippage-guard / EMA-tick /
migration paths, partial-close `last_active` grace, decay-dust bounds, `A_EMA` saturation, duplicated `BLOCKS_PER_DAY`,
zero-count storage bloat, review-loop ID leakage in test comments, a stale `IMPLEMENTATION_PLAN.md`, the speculative
`SimSwapOpts` wrapper, and the dormant long-side launch-scope question. They are legitimate and worth fixing but sit
outside this report's economic / reachability mandate; they are catalogued in the review itself (archived under
`batches/batch-09-external-review-reconciliation/`).

---

## Reproduction

```bash
# toolchain (HOME is non-persistent in this sandbox; the target/ cache under /projects persists)
. "$HOME/.cargo/env" 2>/dev/null || curl --proto '=https' -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain none
cd /projects/subtensor && export SKIP_WASM_BUILD=1
git apply security-review/tooling/poc/derivatives-poc.patch              # 12 poc_* in derivatives.rs
git apply security-review/tooling/poc/followup-derivative-modules.patch  # F-02 long, F-03, F-04, rollback modules
# All 12 poc_* — the F-01 leak proofs are INTENTIONAL failures (assertion encodes the SOUND outcome, so failure = proof);
# F-02 cap-bypass, cross-state x2, decay-drift solvency, and pruning-sabotage all PASS:
cargo test -p pallet-subtensor --lib poc_ -- --nocapture
# FINDING-01 quote-engine control:
cargo test -p pallet-subtensor --lib engine_cover -- --nocapture
# FINDING-02 long mirror, FINDING-03, FINDING-04, slippage-rollback probe:
cargo test -p pallet-subtensor --lib derivative_cold -- --nocapture
cargo test -p pallet-subtensor --lib coldkey_swap -- --nocapture
cargo test -p pallet-subtensor --lib terminal_settlement_pays_identical_shorts_different_equity -- --nocapture
cargo test -p pallet-subtensor --lib slippage_failure_rolls_back_state -- --nocapture
# Verification round (2026-07-01) — apply tooling/poc/verification-round.patch first:
cargo test -p pallet-subtensor --lib tests::derivative_break_opus -- --nocapture  # F-04b long mirror + 3 cross-state breaks DEFENDED + F-01 STAB + F-02/F-04 reproductions (7 pass)
# full regression — expect: 1294 passed; 6 failed; 9 ignored (the 6 failures ARE the F-01 leak proofs, by design):
cargo test -p pallet-subtensor --lib
# closed-form sims (offline) + live-weights probe (finney RPC):
python3 security-review/tooling/sims/sim_weighted_v2_pricefixed.py   # F-01 weighted self-close model
python3 security-review/tooling/sims/sim_l2_economics.py             # L2a emission redirect vs carry (0.12–0.25)
python3 security-review/tooling/sims/sim_l2b_pruning.py              # L2b depression bound (~9.75%) + reach window + carry
uv run --with substrate-interface python security-review/tooling/probes/probe_mainnet_weights.py   # finney SwapBalancer weights
```
PoC tests: `poc_*` in `pallets/subtensor/src/tests/derivatives.rs`, plus focused modules from
`tooling/poc/followup-derivative-modules.patch`: `derivative_cold_ema.rs`, `derivative_coldkey_swap.rs`,
`derivative_rollback.rs`, and `derivative_terminal_settlement.rs` (the last now also carries the F-04b long-mirror
test); the verification round adds `derivative_break_opus.rs` via `tooling/poc/verification-round.patch`.

**Reproducibility verified (ship gate):** both patches `git apply --check` cleanly — individually and composed — onto a
**fresh `#2764` checkout at head `1a7aa37`**; the full pallet suite then reports **`1294 passed; 6 failed; 9 ignored`**,
where the 6 failures are exactly the F-01 leak-proof PoCs (their assertion encodes the SOUND outcome, so the failure *is*
the extraction proof). All five sims run offline and reproduce the documented numbers.

## Note for the program
These findings are currently non-exploitable on mainnet; we report them as **pre-launch hardening** with full,
transparent reachability analysis (harness PoCs proving the mechanism + live-state proof of current dormancy +
amplifier sweep). A strict current-exploitability rubric may score them LOW/informational; a pre-launch fund-handling
review scores them MEDIUM. We recommend fixing all confirmed issues before enabling shorts/longs.
