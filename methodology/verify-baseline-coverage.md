# Verify — baseline "covered" conservation (Phase 3, executed)

**Claim:** at open, protocol removes `N+E` TAO from pool & books Alpha liability
`Q=φ·A_live`; at `close_short_self` (no move, no fee) it rebuys `Q` at cost `K0`
and returns `claim−K0 = (P+N)−K0`. Is `K0 = N`? (`K0<N` ⇒ free-TAO mint.)

**Method:** Python (`sim_baseline.py`), Decimal prec=80, real + I64F64-truncation modes.
CPMM exact-output buyback `tao_in = T·a_out/(A−a_out)`, fee on input.

**Result — CONFIRMED `K0 = N`.**
- Real arithmetic: `max|K0−N|/N = 3.9e-78` across 5 param sets ⇒ exact identity.
  Algebraic proof: `E=φT`, `N=φT(1−φ)` ⇒ pool after open `T−N−E = T(1−φ)²`;
  buyback `= T(1−φ)²·φ/(1−φ) = φT(1−φ) = N`. ∎
- With 0.3% fee: instant round-trip P&L strictly negative (−3 to −250 TAO on the
  tested sizes) — you pay the swap fee to exit. No baseline edge.
- I64F64 truncation: worst residual **+0.67 rao** (6.7e-10 TAO) per open+self-close,
  and the with-fee P&L is −10^9..−10^11 rao. ⇒ dust extraction via close_self is
  economically impossible (fee ≫ dust). **H3 (close_self dust) REFUTED.**

**Implication for the hunt:** baseline is exactly covered; value can only be moved by
(1) genuine price movement while open, (2) spot-vs-EMA asymmetry (open sizing uses
lagged EMA `t_ref`/`pEMA`; `close_*_self` & dereg-cover use live spot), (3) the
NON-self close/default legs that actually mint/burn Alpha & touch `SubnetAlphaOut`/
`TotalStake`/`TotalIssuance` (H8 cross-leg), (4) decay restoration timing, (5)
permissionless-default MEV. Focus there; stop chasing baseline/dust leaks.

**Status:** sim at `sim_baseline.py`. Param-dependent sims (carry curve, fee-free
price-push edge H2) deferred until explore agent returns the real param defaults &
swap-fee model. 8 background agents still running.
