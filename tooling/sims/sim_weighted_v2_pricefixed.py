#!/usr/bin/env python3
"""
v2: hold the SPOT PRICE fixed (no adverse move) and vary ONLY the Balancer weight
ratio r=w1/w2, to rule out the v1 confound (v1 varied r with T=A, which also moved price).

Pool price p = (w1/w2)*(T/A) = r*(T/A).  Fix p=1 (honest no-move baseline) => T = A/r.
A short opened and INSTANTLY self-closed at an unchanged price should net ~0 (minus fee).
If profit>0 with no move, the self-cover path leaks purely from the open(naive)/close(weighted)
pricing asymmetry.

Faithful to code:
  open  (do_open_short): N from solve_collateral(P,t_ref=T,S=0,lam); phi=solve_phi(N,T);
        E=phi*T; Q=phi*A  -- NO weights. removes N+E TAO.
  close (do_close_short_self): K = get_quote_needed_for_base(T',A,Q) = T'*((A/(A-Q))^r - 1),
        grossed up by fee. returned = (P+N) - K. underwater iff K>P+N.
"""
from decimal import Decimal, getcontext
getcontext().prec = 60
D = Decimal

def solve_collateral(P, T_ref, S, lam):
    a = lam*lam/T_ref
    b = D(1) - lam + (D(2)*lam*S/T_ref)
    C = ((b*b + D(4)*a*P).sqrt() - b)/(D(2)*a)
    N = C - P
    return N if (N > 0 and C > 0) else None

def solve_phi(N, T):
    frac = D(4)*N/T
    return None if frac > 1 else (D(1) - (D(1)-frac).sqrt())/D(2)

def wbuyback(T, A, Q, r, fee):
    powed = D(float(A/(A-Q)) ** float(r))
    return (T*(powed - D(1)))/(D(1)-fee)

def roundtrip(P, A, r, lam, fee, price=D(1)):
    T = price*A/r                      # price = r*(T/A) = p  => T = p*A/r
    N = solve_collateral(P, T, D(0), lam)
    if N is None: return None
    phi = solve_phi(N, T)
    if phi is None: return None
    E = phi*T; Q = phi*A
    Tp = T - N - E
    if Tp <= 0 or Q >= A or Q <= 0: return None
    K = wbuyback(Tp, A, Q, r, fee)
    return dict(T=T, N=N, Q=Q, K=K, profit=N-K, underwater=K > P+N)

A = D(1_000_000); lam = D("0.5"); fee = D("0.0005")
print("PRICE FIXED AT 1.0 (no move). Vary weight ratio r=w1/w2 only.  A=1,000,000 alpha")
for P in [D(1000), D(50_000)]:
    print(f"\n--- P = {int(P):,} TAO ---")
    print(f"{'r':>6} {'w1':>6} {'T (rsv)':>14} {'N':>12} {'K(fee)':>12} {'profit_fee':>12} {'%ofP':>7} {'flag':>6}")
    for r in ["0.5","0.8","0.9","0.95","0.98","0.99","1.0","1.02","1.1","1.25","1.6"]:
        rr = D(r); w1 = rr/(rr+1)  # w1/w2=r, w1+w2=1 => w1=r/(r+1)
        x = roundtrip(P, A, rr, lam, fee)
        if not x: print(f"{r:>6}  reject"); continue
        pct = x['profit']/P*100
        flag = "LEAK" if x['profit'] > 0 else "safe"
        print(f"{r:>6} {float(w1):>6.3f} {float(x['T']):>14.0f} {float(x['N']):>12.4f} "
              f"{float(x['K']):>12.4f} {float(x['profit']):>12.4f} {float(pct):>6.2f}% {flag:>6}"
              + ("  UW" if x['underwater'] else ""))

print("\nInterpretation: at r=1 (w=0.5/0.5) profit≈0 (baseline holds). If profit>0 for r<1")
print("at FIXED price, the self-cover path leaks ~N*(1-r) with NO move => open(naive)/close(weighted)")
print("asymmetry, untested (only the in-kind close has a weighted conservation proof).")
print("CONFIRM in the Rust harness: skew_pool(price<1)+open_short+close_short_self, assert TotalIssuance.")
