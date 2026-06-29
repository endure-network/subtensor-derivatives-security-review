# Batch 01 — Self-cover / open pricing-curve asymmetry (F-01)

**Verdict:** MEDIUM · confirmed · **currently dormant** (mainnet all 0.5/0.5).

**One-liner:** `open_*` books the liability/escrow with weight-unaware **constant-product** math (`solve_phi`,
`Q=φ·A`, `E=φ·T`); `close_*_self` prices the buyback with the weight-aware **Balancer** engine. They diverge whenever
`w1/w2 ≠ 1`, so open + instant self-close at an unchanged price drains `≈ N·(1−w1/w2)` from the subnet pool.

**Proof (8 PoCs in `tooling/poc/derivatives-poc.patch`):** baseline control 0.5/0.5 → +0.0 (no leak); short r=0.5 →
+499 TAO (pool −499); r=0.99 (0.5% drift) → +985 on 100k; survives ~3% fee → +483; long r=2.0 → +499α; repeat 5× →
+2,499 (pool==attacker to the rao); emission-drift 0.5→0.52 via real `adjust_protocol_liquidity` → +22,394. Sims match
to the decimal.

**Why dormant:** finney all pools at 0.5/0.5 (probe), where `K0=N`. Weights are structurally pinned at 0.5 (emission
proportional; user-LP permanently deprecated; fresh pools seed at price). No in-flight change arms it
(`amplifier-assessment.md`). ⇒ a code change away, not a config flip.

**Files:** `finding.md` (full writeup), `amplifier-assessment.md`. **Fix:** make the open weight-aware (size Q/E/φ via
the same swap engine the close uses, so `K=N` at any weight); add a `close_*_self` conservation test under skewed weights.
