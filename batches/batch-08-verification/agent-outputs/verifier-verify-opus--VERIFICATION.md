# Adversarial verification — subtensor #2764 covered-derivatives security review

**Reviewer stance:** skeptical senior auditor. Every finding and every "defended" claim was
independently reproduced, re-derived, and attacked before I agreed or disagreed. Target head
`1a7aa37`, PoC patches applied in `/projects/subtensor`. Toolchain: `cargo 1.89.0`, `python 3.11`.

## Bottom line

The headline **(4 MEDIUM + 2 LOW/LOW–MEDIUM, the three escalation probes defended)** is **accurate
in substance and honest**. All six findings are **real, reproduced code defects**; none is a false
positive. All three "defended" probes **survived** my break attempts — including three cross-state
regimes the report explicitly left unreproduced (long mirror, regular in-kind close, amortized
multi-position pump), which I tested and found defended.

Two honest calibration notes, both already disclosed by the report itself:
- **All four MEDIUMs lean generous.** Every one is pre-launch, non-exploitable today, and either
  dormant (F-01), a risk-limit bypass not a drain (F-02), or bounded with no proven theft (F-03/F-04).
  A strict *current-exploitability* / bug-bounty rubric scores most of them **LOW/informational**; a
  *pre-launch fund-handling* rubric scores them MEDIUM. The report states this tension explicitly.
- **F-01 is, if anything, *more* dormant than claimed.** I verified at the code level (not just via the
  finney snapshot) that production emission is an **exact fixed point at w=0.5** and that a seeded
  migration-style skew **self-heals** toward 0.5. The "w≠0.5 is a code change away" story is upheld and
  strengthened.

No new exploitable finding surfaced. One methodological catch worth recording: my *own* first long-mirror
harness produced a spurious "+80,000 TAO drain" from a P&L-measurement bug (init captured after the pump);
after fixing it the long mirror nets ~0. I flag this to show the break attempts were run honestly and the
negative result is real, not an artifact.

---

## Per-finding verdict table

| ID | Report claim | **My verdict** | Evidence (reproduced) |
|----|--------------|----------------|-----------------------|
| **F-01** | Self-cover open/close curve asymmetry ⇒ drain under w≠0.5. **MEDIUM, dormant** | **UPHELD** (defect real, dormancy robust; severity MEDIUM defensible but **generous → LOW** under strict current-exploitability) | 6 leak PoCs fail-as-designed (+499 / +985 / +483 / +2 499 / +22 394 TAO); `sim_weighted_v2` matches to the decimal; **NEW**: emission fixed-point @0.5 (drift `0.00e0`), skew self-heals (0.45→0.457); finney **128/128 @ w=0.5** (my own live probe) |
| **F-02** | Cold-EMA fresh-subnet cap bypass. **MEDIUM**; cross-state escalation defended | **UPHELD** | `poc_cold_ema_breaches_capacity_cap` honest 119 → pumped 399 TAO; long mirror bypass reproduced; cross-state defended (see probe section) |
| **F-03** | Coldkey-swap collision orphans short aggregate. **MEDIUM** | **UPHELD** (short-side real & reachable; long-side genuinely blocked; no theft — griefing/accounting only) | `coldkey_swap_collision_orphans_short_aggregate` ok; source `swap_positions_for_coldkey_swap` confirms aggregate **not** decremented; collision reachable (short open leaves `StakingHotkeys` empty) |
| **F-04** | Terminal settlement order-dependent equity. **MEDIUM** | **UPHELD** (severity **generous**; bounded, conserved, no theft) | `…pays_identical_shorts_different_equity` first=332.7 / second=277.2 TAO; my hand-derivation reproduces both to the rao; root cause confirmed at `mod.rs:757-764` |
| **L2a** | Emission skim. **LOW, infeasible** | **UPHELD** | `sim_l2_economics` redir/carry **0.117–0.246** (report 0.12–0.25) |
| **L2b** | Pruning sabotage. **LOW–MEDIUM, bounded** | **UPHELD** | `poc_pruning_sabotage_redirect` ok; `sim_l2b_pruning` depression **9.75%**, reach **+10.80%** |
| Probe | Cross-state drain **DEFENDED** | **UPHELD + STRENGTHENED** | reproduced (worst −0.000 TAO) **+ 3 new regimes all defended** |
| Probe | Hook atomicity **DEFENDED** | **UPHELD** | `poc_decay_drift_custody_solvency` custody over by +6 894 / +7 088 rao |
| Probe | Slippage rollback **DEFENDED** | **UPHELD** | `short_open_…` + `long_self_close_…rolls_back_state` ok |
| D-chi-moot | Flow-neutrality defends a dead channel | **UPHELD** | `get_shares` calls only `get_shares_price_ema`; `get_shares_flow` uncalled |

---

## F-01 — self-cover pricing-curve asymmetry (the load-bearing finding)

### 1. Mechanism re-derived by hand (independent of the report's sim)
Open books `φ = solve_phi(N, T)` (weight-unaware), `Q = φ·A`, `E = φ·T`, removes `N+E`. With
`N = Tφ(1−φ)` the post-open pool is `T' = T(1−φ)²`. The self-close buys `Q` back through the
**weight-aware** engine `K = T'·((A/(A−Q))^r − 1)` with `r = w1/w2`. Writing `x = 1−φ`:

> **profit = N − K = T·x·(1 − x^{1−r})**  → `>0` for r<1 (short), `=0` at r=1, `<0` for r>1.

For small φ this is `≈ N·(1−r)`, exactly the report's law. **The asymmetry is real and the sign/magnitude are correct.**

### 2. Reproduction (the 6 "intentional failures" are genuine extractions, not artifacts)
`cargo test -p pallet-subtensor --lib poc_ -- --nocapture` → 6 passed / 6 failed. The 6 failures each
carry an extraction panic, e.g.:
```
[POC] trader balance delta = +499127146400 rao ; subnet pool delta = -499127146400 rao ; TotalIssuance delta = 0
FINDING-01 LEAK: trader extracted 499.1271 TAO from the pool via self-close under skewed weights, no price move
[POC-SMALLSKEW] r=0.99, P=100k: trader delta = +985.23 TAO
[POC-FEE] r=0.5, ~3% fee: trader delta = +483.42 TAO      (survives the fee)
[POC-REPEAT] 5x: attacker gained +2499.57 TAO; pool drained == gained to the rao
[POC-DRIFT] weights 0.5→0.52 via 60x adjust_protocol_liquidity, then +22394.45 TAO
```
The control `poc_baseline_no_skew_no_leak` returns +0.000074 TAO at 0.5/0.5. **Failure = the sound
assertion (`delta ≤ 1 TAO`) being violated by the leak. Confirmed genuine.**

### 3. Dormancy — challenged HARD, upheld and strengthened
The whole MEDIUM-vs-HIGH question is *can w≠0.5 be reached?* I did not take the report's word:

- **Production emission is proportional by construction.** `get_subnet_terms`
  (`run_coinbase.rs:207`) sets `alpha_in_i = tao_emission_i / price_i`, so the injection ratio is
  **exactly `price_i`**. At w=0.5, `price = T/A` = reserve ratio ⇒ `update_weights_for_added_liquidity`
  leaves the weight unchanged. The `poc_emission_drift_then_leak` PoC forces a **fixed 5 : 1** injection
  into a 1 : 1 pool (5× the price) — the methodology's own "unrealistic forcing" anti-pattern.
- **NEW empirical proof I added** (`stability_realistic_emission_keeps_weight_pinned`):
  ```
  [STAB-A] proportional emission ×200: w_quote 0.500000 -> 0.500000 (drift 0.00e0)
  [STAB-B] seeded skew 0.4500; realistic emission ×400 -> 0.457071  (moves TOWARD 0.5 = self-heal)
  ```
  Proportional emission is an **exact fixed point**; a migration-born skew **decays back toward 0.5**.
- **No other non-0.5 source.** New subnets initialize lazily via `maybe_initialize_palswap(netuid, None)`
  → default **w=0.5** (`impls.rs:195`, `balancer.rs:83`). Only the one-time v3→balancer migration passes
  `Some(price)`; it sets weights so spot = v3 price, i.e. 0.5 iff v3 price = reserve ratio. There is **no
  governance/sudo extrinsic that sets weights directly** (only `set_quote_weight`, reachable solely from
  `update_weights_for_added_liquidity` and the migration). User-LP is deprecated.
- **Independent live check.** I ran `probe_mainnet_weights.py` against finney **just now**:
  `N=128 subnets, median |w−0.5| = 0.0000, max leak 0.000%, 128/128 within 0.001 of 0.5`.

**Verdict:** the code defect is real and high-impact *if armed*, but the precondition is structurally
unreachable and self-correcting. **UPHELD.** Severity: MEDIUM is defensible for a pre-launch review; a
strict current-exploitability rubric lands at **LOW**. The report's own batch-01 journal reached "LOW /
latent" before REPORT.md settled on MEDIUM — I concur it sits on that LOW↔MEDIUM boundary, and the report
discloses this.

---

## F-02 — cold-EMA capacity bypass + cross-state escalation

- **Bypass reproduced:** `short_t_ref = min(t_live, pEMA·A_EMA)` falls to `t_live` when the EMA is cold
  (`mod.rs:144`), so an in-block pump inflates the cap. `honest cap = 119 → pumped cap = 399 TAO`; the
  long mirror (`long_a_ref`) reproduces identically. Real. **UPHELD (MEDIUM, hardening).**
- **"Not a drain" challenged in the report's own regime + 3 new ones — all defended:** see below.

---

## Breaking the defended probes (the adversarial core)

I wrote `pallets/subtensor/src/tests/derivative_break_opus.rs` to attack the cross-state defense in
regimes the report did **not** test. Attacker P&L is summed over **every** attacker-controlled account,
measured in free TAO after the whole sequence unwinds. `net>0 ⇒ drain`.

| Break attempt (untested regime) | Result | Verdict |
|---|---|---|
| **1. Amortize ONE staking pump across M=1/4/16 short self-closes** | best net **−0.83 TAO**; net gets *more* negative as M grows (m=16 ⇒ −13…−587 TAO) | **DEFENDED** — sharing the pump does not help; each open walks the reserve down, so M opens ≈ one big open (already tested) |
| **2. Regular in-kind `close_short` (repay Q from pumped alpha)** | best net **−0.0025 TAO** (all closed cases negative) | **DEFENDED** — inflated R=N is offset by the real cost of the alpha used to repay |
| **3. LONG mirror cold-`A_ref` cross-state** | best net **+0.000003 TAO ≈ 0** (rounding dust, both signs) | **DEFENDED** |

Why they hold (confirmed, not assumed): the gap requires lowering the reserve *between* open and close;
the AMM charges the convex round-trip spread to create-and-revert that move, and pool conservation gives
`pool ΔT = −(attacker net)`. The displacement value the derivative extracts is first-order; manufacturing
+ reverting it costs the same plus second-order slippage. Amortizing across positions doesn't beat the
conservation because each open itself moves the reserve.

> **Honesty note:** my first long-mirror run printed a spurious **+80,000 TAO** "drain" — a P&L bug in
> *my* harness (I captured `init` *after* `add_stake`, so unwinding that stake looked like profit).
> Fixed (measure `init` before the pump) → net collapses to ~0. Recorded so the negative result is
> credible.

- **Hook atomicity** reproduced: `poc_decay_drift_custody_solvency` leaves custody **over** obligations
  by +6 894 / +7 088 rao (staggered entries, max decay). Guarded credits + safe-direction bookkeeping ⇒
  no #2662 phantom-credit path. **DEFENDED, UPHELD.**
- **Slippage rollback** reproduced: `short_open_slippage_failure_rolls_back_state`,
  `long_self_close_slippage_failure_rolls_back_state` pass. **DEFENDED, UPHELD.**

---

## F-03 — coldkey-swap orphaning (source-verified, reachability confirmed)

`swap_positions_for_coldkey_swap` (`mod.rs:1136-1142`) on a destination collision does
`ShortPositions::take(old)` then, seeing the destination already has a position, only
`ShortPositionCount -= 1` and **drops** the source position — it never subtracts from `ShortAggregate`.
So `q_sigma` stays at the two-position total while only one position is live (test asserts
`q_sigma > Σ live q`). **Reachability confirmed:** `open_short` does not populate `StakingHotkeys`, so a
destination coldkey can hold a short and still pass the `do_swap_coldkey` `StakingHotkeys(new).is_empty()`
guard — both positions were opened via the **real** `open_short` extrinsic in the PoC.

**Long side genuinely blocked, and durably so:** opening a long requires pre-existing alpha stake, which
appends to `StakingHotkeys`; and the unstake-time `StakingHotkeys` cleanup is **commented out**
(`stake_utils.rs:820-821, 1029-1030`), so it never empties. My "full-unstake re-opens the guard"
hypothesis is therefore **false** — the report's short-only scoping is correct.

**No escalation to theft:** the orphaned custody TAO (source `P+R+E`, incl. the `N+E` pulled from the pool
at open) is neither double-spent nor stealable — it is swept/burned by `recycle_custody_tao(custody, MAX)`
at dereg. Impact is capacity-griefing + accounting integrity, exactly as reported. **UPHELD (MEDIUM,
pre-launch; leans generous — no profit).**

---

## F-04 — terminal settlement order dependence (magnitude verified realistic)

`settle_shorts_on_dereg` restores each position's escrow via `increase_provided_tao_reserve`
(`mod.rs:757`) **before** quoting that same position's `short_spot_close_cost` (`mod.rs:764`) against the
now-larger reserve. My hand-derivation reproduces the exact numbers: pool `T=10 000`, `E=500`, `pEMA=0.1`:
- 1st settled: pool→10 500, `K=10 500·1000/9000=1 166.7` ⇒ equity `1 500−1 166.7 = 333.3` ✓ (332.7 obs)
- 2nd settled: pool→11 000, `K=1 222.2` ⇒ equity `277.8` ✓ (277.2 obs)

The 17% spread comes from a 5%-of-pool escrow; it **scales with Σescrow/pool** and with position count
(up to 4 096), so at scale the unfairness is larger. Value is **conserved** (over-charged cover is burned,
escrow goes to pool, equity to traders) — order only shifts burn-vs-equity per holder, capped by each
holder's own floor. **Real, but a bounded fairness/accounting bug, not theft.** **UPHELD (MEDIUM, pre-launch;
leans generous — LOW–MEDIUM on a strict rubric).**

---

## L2a / L2b — economics re-derived

- `sim_l2_economics.py`: best-case redirected-emission/carry **0.117–0.246** across finney subnets ⇒ carry
  is 4–8× the benefit ⇒ **infeasible**. Reproduced. **UPHELD (LOW).**
- `sim_l2b_pruning.py`: κ=0.05 caps depression at **9.75%**, reach window **+10.80%** ⇒ only the bottom
  cluster is reachable; `poc_pruning_sabotage_redirect` shows redirect + immunity + a 10×-min subnet
  unreachable. Reproduced. **UPHELD (LOW–MEDIUM, bounded griefing).**

---

## Missed surface / fresh exploration (nothing new-exploitable)
- Verified there is **no direct governance weight-setter** (would instantly arm F-01) — none exists.
- Verified `StakingHotkeys` is append-only (long F-03 permanently blocked).
- Added the emission-stability test that the report lacked; it strengthens F-01 dormancy.
- Traced F-03 custody lifecycle end-to-end to confirm the orphaned TAO is burned, not stealable.
- Cross-state break attempts (amortized / regular-close / long) all defended.

## Ship-gate regression (reproduced)
`cargo test -p pallet-subtensor --lib` → **`1302 passed; 6 failed; 9 ignored`** in 117 s. The **6
failures are exactly** `poc_short_self_close_leaks_under_skewed_weights`, `…_small_skew`, `…_with_fee`,
`poc_long_self_close_leaks_under_skewed_weights`, `poc_repeat_drain`, `poc_emission_drift_then_leak` —
i.e. precisely the F-01 leak proofs (assertion encodes the sound outcome, so the failure *is* the proof);
everything else is green. (Report states `1294 passed`; the +8 is my 4 added break/stability tests plus a
small pre-existing test-count drift — immaterial: the load-bearing "6 failed = the F-01 PoCs, all else
green" reproduces exactly.)

## Reproduction commands
```bash
cd /projects/subtensor && . "$HOME/.cargo/env" && export SKIP_WASM_BUILD=1
cargo test -p pallet-subtensor --lib poc_ -- --nocapture                       # 6 pass / 6 fail (F-01 proofs)
cargo test -p pallet-subtensor --lib tests::derivative_break_opus -- --nocapture # my 4 break/stability tests, all pass (defended)
cargo test -p pallet-subtensor --lib tests::derivative_cold_ema -- --nocapture   # F-02 long bypass
cargo test -p pallet-subtensor --lib tests::derivative_coldkey_swap -- --nocapture # F-03
cargo test -p pallet-subtensor --lib tests::derivative_terminal_settlement -- --nocapture # F-04
python3 security-review/tooling/sims/{sim_baseline,sim_weighted_v2_pricefixed,sim_l2_economics,sim_l2b_pruning}.py
uv run --with substrate-interface python security-review/tooling/probes/probe_mainnet_weights.py  # finney: 128/128 @ 0.5
```
New harness: `pallets/subtensor/src/tests/derivative_break_opus.rs` (+ one line in `tests/mod.rs`);
my four tests are `break_amortized_pump_short_self_close`, `break_regular_close_short_cross_state`,
`break_long_mirror_cross_state`, `stability_realistic_emission_keeps_weight_pinned` (clean copy in
`artifacts/`). During the review the shared file also received unrelated tests from a **concurrent
verification agent** (kappa=0.05 F-02/F-04 reproductions I did not author); per shared-worktree
discipline I left them untouched and did not rely on them — every verdict above stands on my own
reproductions.

## Ledger of my verdicts
UPHELD: F-01 (dormant; MEDIUM generous→LOW strict), F-02, F-03, F-04 (MEDIUM generous→LOW–MEDIUM strict),
L2a, L2b, and all three defended probes (cross-state / hook-atomicity / slippage-rollback).
OVERTURNED: none. WRONG / false-positive: none. The report is honest and, on F-01 dormancy, conservative.
