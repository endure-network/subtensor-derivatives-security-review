#!/usr/bin/env python3
"""
Verify the CORE "covered" invariant of subtensor covered-short derivatives.

Claim under test (from derivatives/mod.rs do_open_short + do_close_short_self):
  At OPEN, the protocol removes N+E TAO from the pool and books an Alpha
  liability Q = phi * A_live, with N = retained proceeds (the trader's buffer R0),
  E = phi * T_live (escrow), phi = solve_phi(N, T_live).

  At CLOSE_SELF (zero price movement, zero fee), the protocol must rebuy Q Alpha
  from the now-(T-N-E, A) pool at cost K0, and returns claim - K0 = (P + N) - K0.

If K0 < N  -> open + instant self-close mints free TAO (CRITICAL value leak).
If K0 = N  -> baseline is exactly covered; only fees + price moves create P&L.
If K0 > N  -> trader pays a premium to exit instantly (safe).

We test in (a) real arithmetic and (b) I64F64-style truncation (floor toward 0 at
to_tao/to_alpha boundaries, as the Rust code does via saturating_to_num::<u64>()).
"""
from decimal import Decimal, getcontext
import math

getcontext().prec = 80
D = Decimal

def solve_collateral(P, T_ref, S, lam):
    if T_ref <= 0 or lam <= 0:
        return None
    a = lam * lam / T_ref
    b = D(1) - lam + (D(2) * lam * S / T_ref)
    disc = b * b + D(4) * a * P
    root = disc.sqrt()
    C = (root - b) / (D(2) * a)
    N = C - P
    if N <= 0 or C <= 0:
        return None
    return C, N

def solve_phi(N, T_live):
    if T_live <= 0:
        return None
    frac = D(4) * N / T_live
    if frac > 1:
        return None
    root = (D(1) - frac).sqrt()
    return (D(1) - root) / D(2)

def buyback_tao_in(T, A, a_out, fee):
    """Exact-output CPMM: TAO in to remove a_out Alpha. Fee taken on input."""
    base = T * a_out / (A - a_out)
    return base / (D(1) - fee)

def floor0(x):
    return D(int(x)) if x > 0 else D(0)  # truncate toward zero, min 0 (to_tao/to_alpha)

def run(T, A, P, lam, S, fee, trunc):
    T, A, P, lam, S, fee = map(D, (T, A, P, lam, S, fee))
    t_ref = T  # no EMA divergence baseline
    sc = solve_collateral(P, t_ref, S, lam)
    if sc is None:
        return None
    C, N = sc
    phi = solve_phi(N, T)
    if phi is None:
        return None
    if trunc:
        N_tao = floor0(N)
        E_tao = floor0(phi * T)
        Q = floor0(phi * A)
    else:
        N_tao, E_tao, Q = N, phi * T, phi * A
    Tp = T - N_tao - E_tao            # pool TAO after open
    if Tp <= 0 or Q >= A or Q <= 0:
        return None
    K0 = buyback_tao_in(Tp, A, Q, D(0))    # no-fee buyback
    Kf = buyback_tao_in(Tp, A, Q, fee)     # with-fee buyback
    residual = N_tao - K0                   # >0 => CRITICAL free TAO
    return dict(C=C, N=N, phi=phi, N_tao=N_tao, E_tao=E_tao, Q=Q, Tp=Tp,
                K0=K0, Kf=Kf, residual=residual,
                pnl_nofee=N_tao - K0, pnl_fee=N_tao - Kf)

RAO = 10**9
print("=== (a) REAL arithmetic: is K0 == N exactly? (baseline coverage) ===")
worst = D(0)
for (T, A, P, lam, S) in [
    (1_000_000*RAO, 2_000_000*RAO, 1_000*RAO, "0.5", 0),
    (1_000_000*RAO, 500_000*RAO,  10_000*RAO, "0.8", 0),
    (5_000_000*RAO, 5_000_000*RAO, 50_000*RAO,"0.3", 0),
    (250_000*RAO,  4_000_000*RAO,   100*RAO, "0.5", 0),
    (1_000_000*RAO, 2_000_000*RAO, 100_000*RAO,"0.5", 0),  # large P
]:
    r = run(T, A, P, lam, S, "0.003", trunc=False)
    if not r: 
        print(f"  P={P/RAO:>10}  -> domain reject"); continue
    rel = abs(r['residual']) / r['N_tao']
    worst = max(worst, rel)
    print(f"  T={T//RAO:>8} A={A//RAO:>8} P={int(P)//RAO:>7} lam={lam}: "
          f"N={float(r['N']/RAO):.4f}  K0={float(r['K0']/RAO):.4f}  "
          f"residual/N={float(rel):.2e}  pnl_fee={float(r['pnl_fee']/RAO):.4f} TAO")
print(f"  -> max |K0-N|/N in real arithmetic = {float(worst):.2e}  (≈0 confirms K0==N)\n")

print("=== (b) I64F64-style TRUNCATION: residual sign & magnitude (rao) ===")
print("    residual>0 (rao) would be extractable free TAO per open+self-close.")
maxres = D(-10**30); maxctx=None
for (T, A, P, lam, S) in [
    (1_000_000*RAO, 2_000_000*RAO, 1_000*RAO, "0.5", 0),
    (1_000_000*RAO, 500_000*RAO,  10_000*RAO, "0.8", 0),
    (5_000_000*RAO, 5_000_000*RAO, 50_000*RAO,"0.3", 0),
    (250_000*RAO,  4_000_000*RAO,   100*RAO, "0.5", 0),
    (123*RAO,      4567*RAO,         1*RAO,  "0.5", 0),   # tiny / dusty
    (10**15,       3*10**15,        10**11, "0.6", 0),
]:
    r = run(T, A, P, lam, S, "0.003", trunc=True)
    if not r:
        print(f"  P={int(P)//RAO:>8}  -> domain reject"); continue
    res = r['residual']
    if res > maxres: maxres, maxctx = res, (T,A,P,lam)
    print(f"  T={T//RAO if T>=RAO else float(T)/RAO:>10} A={A//RAO if A>=RAO else float(A)/RAO:>10} "
          f"P_rao={int(P):>14}: N_tao={int(r['N_tao']):>16} K0={float(r['K0']):>18.2f} "
          f"residual_rao={float(res):>12.2f} pnl_fee_rao={float(r['pnl_fee']):>14.2f}")
print(f"\n  -> worst-case truncation residual = {float(maxres):.2f} rao "
      f"({float(maxres)/RAO:.2e} TAO)  ctx={maxctx}")
print("  VERDICT: residual<=0 (after fee) => no free-TAO baseline leak; only")
print("  price movement + fees produce P&L. residual>0 => investigate dust extraction.")
