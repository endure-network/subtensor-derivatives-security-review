# 03 — Build, test, and tooling

## Toolchain (sandbox note: `$HOME` is non-persistent; the `target/` cache under `/projects` persists)
```bash
. "$HOME/.cargo/env" 2>/dev/null || curl --proto '=https' -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain none
. "$HOME/.cargo/env"   # rust-toolchain.toml pins 1.89; the first cargo invocation installs it
```
`clang`/`protoc` are NOT needed for the pallet tests (the swap + subtensor pallet test build avoids rocksdb/libp2p).

## Run the derivative tests / PoCs
The target subtensor #2764 checkout is the parent dir `/projects/subtensor`. Apply our PoCs and run:
```bash
cd /projects/subtensor
git apply security-review/tooling/poc/derivatives-poc.patch    # adds poc_* to tests/derivatives.rs
export SKIP_WASM_BUILD=1
cargo test -p pallet-subtensor --lib poc_ -- --nocapture        # our PoCs
cargo test -p pallet-subtensor --lib derivatives -- --nocapture # the full 94-test suite
```
(External clone: `git clone https://github.com/opentensor/subtensor && cd subtensor && git fetch origin pull/2764/head && git checkout FETCH_HEAD`, then apply the patch.)

## Writing a new PoC
Append a `#[test]` to `pallets/subtensor/src/tests/derivatives.rs`. Helpers available there:
- `setup_market(tao, alpha, price)` — dynamic subnet, **warm** EMA, shorts enabled, κ=0.9.
- `setup_long(...)`, `give_alpha(hot, cold, netuid, q)`, `bal(acc)`, `custody_bal(netuid)`, `t(v)`.
- `skew_pool(netuid, price, fee)` — sets Balancer weights via the **real** `maybe_initialize_palswap` (the migration
  init path), so a skewed weight is a real reachable state, not a hack.
- `add_dynamic_network(hot, cold)` — fresh subnet, **COLD** EMA (A_EMA=pEMA=0); `setup_reserves(netuid, tao, alpha)`.
- The mock wires the **real** `pallet-subtensor-swap` as `SwapInterface`, so PoCs exercise the real Balancer engine.
- Convention used by our F-01 PoCs: assert the *sound* invariant so a FAIL prints the leak; F-02's PoC asserts the breach (passes).

## Sims (`tooling/sims/`)
`python3 tooling/sims/<name>.py` (Decimal, exact). `sim_weighted_v2_pricefixed.py` is the decisive weight-sweep
(holds price fixed, varies w1/w2, shows the leak `≈N·(1−w1/w2)`). `sim_baseline.py` proves `K0=N` at 0.5/0.5.
**Always reconcile sims to harness numbers before trusting either.**

## Live-mainnet probes (`tooling/probes/`)
```bash
uv run --with substrate-interface python tooling/probes/probe_mainnet_weights.py   # finney SwapBalancer weights, all subnets
uv run --with substrate-interface python tooling/probes/probe_crosscheck.py         # raw quote + price==T/A cross-check
```
Connects to `wss://entrypoint-finney.opentensor.ai:443`. Use to decide whether a precondition (e.g. weight skew) is
actually present in production — the reachability gate.
