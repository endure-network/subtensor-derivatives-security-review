# Independent security audit — subtensor #2764 covered continuous‑unwind derivatives

**Auditor:** fresh, independent second‑opinion pass (no access to the prior team's conclusions).
**Target:** `opentensor/subtensor` PR #2764, `pallet-subtensor` derivatives, head `1a7aa37`.
**Scope:** `pallets/subtensor/src/derivatives/{mod.rs,long.rs,types.rs}`, the swap/coinbase/dereg
interactions, and the real `pallet-subtensor-swap` Balancer engine (wired into the mock runtime).
**Method:** own threat model → measurable per hypothesis → PoC against the REAL compiled pallet
(`tests/derivative_break_opus.rs`, copied to `poc/` in this worktree) → reachability/severity calibration.

> **Status caveat (applies to every finding):** `ShortsEnabled`/`LongsEnabled` are default‑OFF and NOT
> on mainnet. Everything here is **pre‑launch**. Severities are `impact × reachability` with that
> understood; nothing below is exploitable on mainnet today.

---

## Executive summary

The heavily‑tested economic core (open/close pricing, in‑kind & cash‑settled conservation, anti‑mint,
in‑block reference/capacity resistance, decay closed‑form) is **sound** — I could not break it, and I
tried harder variants than the project's own suite. The residual risk that remains is concentrated in
**two structural places the pricing tests don't cover**:

1. **Reference cold‑start (F‑02):** a fresh subnet's capacity cap `κ·T_ref` follows the *live,
   in‑block‑manipulable* reserve until the EMA warms, so the prudential cap is bypassable with a real
   stake pump (independently reproduced: honest cap **49 → 199 TAO**, opened a **78 TAO** footprint that
   the honest cap would reject; a warm subnet is immune).
2. **Terminal settlement determinism (F‑04):** at deregistration, each position's escrow is restored
   into the *shared* pool **before** its own spot cover is quoted, so identical positions settle to
   different equity depending on iteration order (short: **±8.34 TAO**; **long mirror newly confirmed**,
   same magnitude). This is now **force‑reachable**: `do_register_network` auto‑prunes and dissolves a
   subnet when the network is full.

I **disproved** every value‑extraction hypothesis I could construct against the cross‑state and
weight‑skew surfaces (all attacker P&L ≤ 0), including a false positive **I generated and then caught**
in my own harness (a mismeasured "+80 000 TAO long drain" that was the staked principal being
double‑counted — corrected to ≈ 0).

### Findings table

| ID | Title | Severity | Status | Reachability | Evidence |
|----|-------|----------|--------|--------------|----------|
| **F‑02** | Cold‑EMA capacity cap bypassable by in‑block reserve pump (short **and** long) | **Medium** (risk‑limit integrity; no direct theft) | **confirmed** | Cold subnet window + shorts enabled (OFF today) | `poc_cold_ema_capacity_cap_bypass` — cap 49→199 TAO, footprint 78>49, warm immune |
| **F‑04a** | Short terminal‑settlement equity is order‑dependent for identical positions | **Low** (distributional / non‑deterministic; value conserved) | **confirmed** | Dereg (now force‑reachable, see F‑05) + longs/shorts enabled | `poc_short_terminal_settlement_order_dependent` — 49.97 vs 41.64 TAO |
| **F‑04b** | **Long** terminal‑settlement equity is order‑dependent (mirror) | **Low** | **confirmed (NEW)** | same as F‑04a | `poc_long_terminal_settlement_order_dependent` — 49.97 vs 41.64 α |
| **F‑05** | Terminal settlement is *forced‑reachable* via subnet prune on registration | **Info / reachability amplifier** | **confirmed (path)** | Network at subnet limit; attacker registers a subnet | Code path `do_register_network → get_network_to_prune → do_dissolve_network` |
| **F‑06** | Unguarded equity transfer at short dereg can silently burn a trader's equity | **Low** | **confirmed (code)** | Dereg + trader coldkey below ED at settle | `settle_shorts_on_dereg` `let _ = transfer_tao(...)` (mod.rs:770) + MAX sweep (mod.rs:784) |
| D‑1 | Cross‑state drain: amortize one stake pump across M short self‑closes | — | **disproved** | — | `break_amortized_pump_short_self_close` best net **−0.83 TAO** |
| D‑2 | Cross‑state drain: regular in‑kind `close_short` vehicle | — | **disproved** | — | `break_regular_close_short_cross_state` best net **−0.0025 TAO** |
| D‑3 | Cross‑state drain: long self‑close mirror (cold `A_ref`) | — | **disproved** | — | `break_long_mirror_cross_state` best net **+3 012 rao ≈ 0** |
| D‑4 | F‑01 weight‑skew self‑cover leak is emission‑reachable | — | **disproved (dormant)** | — | `stability_realistic_emission_keeps_weight_pinned` — weight pinned 0.5, seeded skew self‑heals |
| D‑5 | Phantom α‑mint via long decay/partial‑close flooring drift | — | **disproved (analysis)** | — | per‑position floor removes ≫ aggregate floor ⇒ safe direction (see below) |

---

## F‑02 — Cold‑EMA capacity cap is bypassable by an in‑block reserve pump

**Root cause.** `short_t_ref` ([mod.rs:136‑149](file:///projects/subtensor/pallets/subtensor/src/derivatives/mod.rs#L136-L149))
returns `min(T_live, pEMA·A_EMA)`, but on a cold subnet (`T_EMA == 0`, e.g. a freshly created subnet
whose reserve/price EMA has not warmed) it **falls back to the live reserve `T_live`**:

```rust
if t_ema <= I64F64::from_num(0) { t_live } else { t_live.min(t_ema) }
```

The capacity gate `agg.b_sigma + B ≤ κ_S·T_ref`
([mod.rs:317‑320](file:///projects/subtensor/pallets/subtensor/src/derivatives/mod.rs#L317-L320)) therefore
uses a reference an attacker can move **in the same block** by staking TAO into the pool (raising
`SubnetTAO`). The long mirror is identical: `long_a_ref`
([long.rs:27‑34](file:///projects/subtensor/pallets/subtensor/src/derivatives/long.rs#L27-L34)) falls back
to live `A_live`, gated at [long.rs:106‑109](file:///projects/subtensor/pallets/subtensor/src/derivatives/long.rs#L106-L109).

The lagged factor is exactly the in‑block‑manipulation defense the project relies on elsewhere (and which
the 94‑test suite locks for *warm* subnets); the cold fallback silently removes it during the warm‑up window.

**Impact.** The `κ` capacity cap is a prudential limit on aggregate short/long footprint per subnet
(bounds unwinding pressure / systemic risk). During a subnet's cold window it can be inflated arbitrarily
(bounded only by the attacker's willingness to pay stake round‑trip fees), and the oversized position
**persists after the EMA warms** because capacity is only checked at open. No funds are stolen — this is a
risk‑model integrity break, most dangerous on thin fresh subnets.

**PoC — `poc_cold_ema_capacity_cap_bypass`** (real `add_stake` pump, real Balancer engine):
```
cd /projects/subtensor
SKIP_WASM_BUILD=1 cargo test -p pallet-subtensor --lib poc_cold_ema_capacity_cap_bypass -- --nocapture
```
Observed:
```
[F-02] cold cap honest=49 TAO -> pumped=199 TAO  (t_live 1000 -> 3998 TAO)
[F-02] opened footprint b_sigma=78 TAO > honest cap 49 TAO => cap BYPASSED
[F-02-control] warm cap 49 -> 49 TAO after identical pump (immune)
```
The cold cap quadruples with a real stake pump and admits a footprint the honest cap rejects; the warm
control (T_EMA pinned via `SubnetMovingPrice`/`SubnetAlphaInMovingReserve`) is provably immune.

**Reachability.** Any user can create a dynamic subnet (pay the lock); it starts cold (the A_EMA seeding
migration covers *existing* subnets only — `migrate_seed_alpha_in_moving_reserve`, cf. `02-substrate.md`),
and stays cold until `update_moving_price` warms it over `EMAPriceHalvingBlocks`. **Dormant on mainnet
(shorts/longs OFF)** — a config‑flip away, not a code change.

**Severity: Medium.** Real, durable prudential‑limit bypass with a concrete reproduction, but no direct
value extraction and pre‑launch.

**Recommended fix.** On a cold reference, do **not** fall back to the raw live reserve for the *capacity
cap*. Options: (a) seed `SubnetAlphaInMovingReserve`/`SubnetMovingPrice` at subnet creation (as the
migration does for existing subnets) so `T_ref` is lagged from block 0; (b) gate short/long opens behind a
minimum EMA‑warmup age per subnet; or (c) cap `T_ref` by a slow‑moving floor (e.g. an initialization
snapshot) instead of the instantaneous `T_live` while `T_EMA == 0`.

---

## F‑04 — Terminal deregistration settlement is order‑dependent (short **and** long)

**Root cause.** `settle_shorts_on_dereg`
([mod.rs:738‑788](file:///projects/subtensor/pallets/subtensor/src/derivatives/mod.rs#L738-L788)) iterates
positions and, **for each position, restores that position's escrow into the shared pool before quoting
its own spot cover**:

```rust
// escrow → pool (raises SubnetTAO)         mod.rs:754-759
if !pos.e_stored.is_zero() && transfer_tao(custody, subnet_account, e_stored).is_ok() {
    Self::increase_provided_tao_reserve(netuid, pos.e_stored); ...
}
let k_spot = Self::short_spot_close_cost(netuid, pos.q_liability); // reads the now-moved reserve  mod.rs:764
```

So the position iterated **later** covers at a pool that earlier positions already moved. `iter_prefix`
order is the storage (hash) order of the coldkey — not something an honest trader controls, but grindable.
The long mirror `settle_longs_on_dereg`
([long.rs:494‑535](file:///projects/subtensor/pallets/subtensor/src/derivatives/long.rs#L494-L535)) has the
identical shape: escrow α is restored at [long.rs:502](file:///projects/subtensor/pallets/subtensor/src/derivatives/long.rs#L502)
before `long_spot_close_cost` at [long.rs:510](file:///projects/subtensor/pallets/subtensor/src/derivatives/long.rs#L510).

**Impact.** Two byte‑identical positions receive **different terminal equity**. Total value is conserved
(the price move is absorbed by the pool; the "lost" equity is simply cover recycled/burned), so this is a
**distributional fairness + non‑determinism** defect, not a protocol drain. By extrapolation (not separately
PoC'd), with enough escrow restored ahead of it a later identical position can be pushed from positive equity
toward **zero** (cover clamped to `C`) while an earlier twin is paid in full. An actor who can influence
iteration order (grind a coldkey that hashes early) gains a small,
bounded front‑of‑line advantage.

**PoC.** Two identical positions are seeded directly into storage so that **settlement order is the only
free variable** (the real swap engine computes the covers):
```
SKIP_WASM_BUILD=1 cargo test -p pallet-subtensor --lib poc_short_terminal_settlement_order_dependent -- --nocapture
SKIP_WASM_BUILD=1 cargo test -p pallet-subtensor --lib poc_long_terminal_settlement_order_dependent  -- --nocapture
```
Observed:
```
[F-04 short] identical shorts -> equity c1=49974809931 rao  c2=41637278252 rao  |diff|=8337531679 rao (8.3375 TAO)
[F-04 long NEW] identical longs -> equity(alpha) c1=49974809931 c2=41637278252 |diff|=8337531679 (8.3375 alpha-TAO)
```
The short result independently reproduces the project's confirmed F‑04; the **long mirror was previously
only flagged "investigate"** — it is here confirmed with the same magnitude.

**Reachability.** Requires deregistration of a subnet with ≥2 positions. See **F‑05** — dereg is
force‑reachable, not just a voluntary owner action. Pre‑launch (longs/shorts OFF).

**Severity: Low.** Value‑conserving unfairness/non‑determinism with a small grindable edge; dereg‑gated.

**Recommended fix.** Make settlement order‑independent: quote **all** covers against a single snapshot of
the pool taken *before* any escrow is restored (two passes — price every position first, then mutate), or
restore *all* escrow first and price everyone at the common post‑restoration reserve. Either removes the
intra‑loop coupling.

---

## F‑05 — Terminal settlement is force‑reachable via subnet prune (reachability amplifier)

**Root cause / path.** `do_register_network`
([subnet.rs:161‑178](file:///projects/subtensor/pallets/subtensor/src/subnets/subnet.rs#L161-L178)) prunes
when the subnet limit is hit: `get_network_to_prune()` selects a victim and `do_dissolve_network(prune_netuid)`
runs — which calls `settle_shorts_on_dereg` / `settle_longs_on_dereg`
([root.rs:206‑233](file:///projects/subtensor/pallets/subtensor/src/coinbase/root.rs#L206-L233)) **before**
`destroy_alpha_in_out_stakes`.

**Why it matters.** Terminal settlement (and its F‑04 order dependence, plus any terminal‑price edge) is
**not** limited to a subnet owner voluntarily dissolving. When the network is at capacity, *any* party who
registers a new subnet forces the prune target through terminal settlement. Because the prune target is
selected by emission/price standing, this is the concrete bridge to the acknowledged **emission‑redirection
lead**: durably depress a subnet's price → it becomes the prune target → force its positions to settle at a
moment/price of the attacker's choosing. I did **not** value‑quantify the end‑to‑end economic gain (the
mock stubs the live coinbase selection loop), so I flag this as a **reachability amplifier**, not a
standalone drain.

**Severity: Info** (amplifies F‑04; converts "owner‑only" into "permissionless‑ish under capacity").

**Recommended fix.** None on its own; fixing F‑04 (order‑independence) removes the exploitable surface this
amplifies. Separately, consider whether prune‑victim selection should be resistant to short‑driven price
depression (cross‑cutting with the emission lead).

---

## F‑06 — Unguarded equity transfer at short dereg can silently burn a trader's equity

**Root cause.** In `settle_shorts_on_dereg` the equity payout is fire‑and‑forget
([mod.rs:769‑772](file:///projects/subtensor/pallets/subtensor/src/derivatives/mod.rs#L769-L772)):
```rust
if !equity.is_zero() { let _ = Self::transfer_tao(&custody, &coldkey, equity.into()); }
Self::recycle_custody_tao(&custody, cover);
```
and any custody remainder is then swept to issuance
([mod.rs:784](file:///projects/subtensor/pallets/subtensor/src/derivatives/mod.rs#L784),
`recycle_custody_tao(&custody, TaoBalance::MAX)`). If the `transfer_tao` fails (e.g. the destination coldkey
would be left below the existential deposit, or is dust‑empty), the equity is **not** paid **and** is then
burned by the sweep — a silent loss of funds the trader was owed.

**Impact / reachability.** Low: traders normally hold a live, funded coldkey (they posted `P` from it), so
the transfer fails only in a narrow ED‑edge state; dereg‑gated; pre‑launch. Contrast with the well‑guarded
in‑loop reserve credits (escrow restore and `recycle` are `.is_ok()`‑/balance‑capped — no #2662‑style
phantom‑credit path here).

**Severity: Low.** Recommended fix: settle equity with an existence/ED‑safe transfer, or on failure hold
the amount in a claimable ledger rather than letting the terminal sweep burn it.

---

## Hypotheses I DISPROVED (equally important)

**D‑1..D‑3 — Cross‑state "open at moved reserve, close at restored reserve" drains.** The project's own
review settled the single‑shot cross‑state case as non‑profitable; I attacked the residual vehicles it left
"not separately reproduced," in regimes it did not test, summing P&L across **every** attacker‑controlled
account and charging the real manipulation legs (`add_stake`/`remove_stake`, real fees):

- **D‑1 amortized pump** — one stake pump shared across `m ∈ {1,4,16}` short self‑closes. If the per‑position
  gap summed faster than the single shared pump cost, net would go positive. It does not: best net across all
  `(m, pump, P)` = **−0.826 TAO** (every cell negative; larger `m`/pump ⇒ more negative).
  `break_amortized_pump_short_self_close`.
- **D‑2 regular in‑kind `close_short`** — pump alpha at the hotkey, open, repay `Q` in‑kind from the pumped
  alpha, unwind. Best net = **−0.0025 TAO**. `break_regular_close_short_cross_state`.
- **D‑3 long mirror** — move `A_ref` in‑block, open long, self‑close, unwind. Best net = **+3 012 rao
  ≈ 0.000003 TAO** (pure floor dust). `break_long_mirror_cross_state`.

  > **Honesty note / caught false positive.** My first cut of D‑3 reported **+80 000 TAO** "profit" — which
  > was exactly the staked `move_tao` each run. It was a *measurement artifact*: `init` was captured **after**
  > the manipulation `add_stake`, so the principal recovered by the closing `remove_stake` counted as profit.
  > Fixed by measuring from before the pump ([poc lines ~236‑240](file:///projects/subtensor/pallets/subtensor/src/tests/derivative_break_opus.rs)); the drain vanished to dust. This is the exact "don't claim
  > a leak you didn't truly measure" failure mode — flagged here rather than buried.

**D‑4 — F‑01 weight‑skew self‑cover leak is emission‑reachable.** The self‑cover leak `≈ N·(1−w1/w2)` is real
only at `w ≠ 0.5`. I checked whether realistic (price‑proportional) emission injection can drift the Balancer
weight off 0.5: it cannot. `stability_realistic_emission_keeps_weight_pinned`:
```
[STAB-A] proportional emission x200: w_quote 0.500000 -> 0.500000 (drift 0.00e0)
[STAB-B] seeded skew 0.4500; realistic emission x400 -> 0.457071 (toward 0.5 = self-heal ...)
```
Proportional emission keeps the weight pinned at 0.5, and even a **seeded** 0.45 skew drifts back **toward**
0.5. Combined with all‑user‑LP being permanently `Err(Deprecated)`, `w ≠ 0.5` is a **code change** away, not a
runtime/emission‑reachable state ⇒ F‑01 stays **dormant**.

**D‑5 — Phantom α‑mint via long decay/partial‑close flooring.** Longs use mint accounting (dangerous
direction), so I checked whether aggregate `Σ`‑decay can restore/mint **more** α than the sum of per‑position
obligations. It cannot: per‑position materialization floors each of `N` positions **every block**
(`mul_alpha(·, exp(−ΔΩ))`), removing ≈ `N·T` rao over `T` blocks, whereas the aggregate floors the **sum
once** per block (≈ `T` rao). Hence aggregate `r_sigma ≥ Σ` per‑position `R`, so close/decay mints **≤**
what was de‑issued — the safe (deflationary‑dust) direction. This matches the project's short‑side custody
result and the full‑lifecycle α‑conservation tests; the long partial‑close chain adds only sub‑rao dust in
the safe direction. (Analysis‑confirmed; no adversarial mint could be constructed.)

**Other surfaces checked and found defended:** `top_up` has no `ShortsEnabled` gate but only credits the
owner's own buffer (position management under halt — intended); close/default correctly ungated;
`recycle_custody_tao` is balance‑capped so an `Exact` withdraw can't desync issuance
([mod.rs:86‑101](file:///projects/subtensor/pallets/subtensor/src/derivatives/mod.rs#L86-L101)); the decay
restoration reserve credit sits **inside** the `.is_ok()` transfer guard
([mod.rs:719‑730](file:///projects/subtensor/pallets/subtensor/src/derivatives/mod.rs#L719-L730)); the
`None`‑subnet early return in dereg settle ([mod.rs:742‑745](file:///projects/subtensor/pallets/subtensor/src/derivatives/mod.rs#L742-L745))
is dormant because `do_dissolve_network` settles **while the subnet still exists**
(destroy happens after — [root.rs:217‑221](file:///projects/subtensor/pallets/subtensor/src/coinbase/root.rs#L217-L221)).

---

## Reproduction

All PoCs live in `pallets/subtensor/src/tests/derivative_break_opus.rs` (registered as
`mod derivative_break_opus;` in `tests/mod.rs`), copied verbatim to **`poc/derivative_break_opus.rs`** in
this worktree so a reviewer can re‑apply and rerun:

```
cd /projects/subtensor
# (if not already present) cp <worktree>/poc/derivative_break_opus.rs pallets/subtensor/src/tests/ && add `mod derivative_break_opus;` to tests/mod.rs
export SKIP_WASM_BUILD=1
cargo test -p pallet-subtensor --lib tests::derivative_break_opus -- --nocapture   # all PoCs
```

The mock wires the **real** `pallet-subtensor-swap` Balancer engine, so every cover/quote is computed by the
production swap math, and every manipulation leg (`add_stake`, `remove_stake`, `open_*`, `close_*`) is a real
extrinsic charged real fees.

## Bottom line

The derivatives' priced economics are solid; I broke none of them. The exploitable‑in‑principle residue is
**reference cold‑start (F‑02)** and **settlement determinism (F‑04a/b, amplified by F‑05)** — both structural,
both pre‑launch, both with concrete PoCs and concrete fixes. Everything I could frame as a value drain
disproved cleanly, including a false positive I generated and corrected.
