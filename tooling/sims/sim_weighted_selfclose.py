#!/usr/bin/env python3
"""
Does the cash-settled self-cover round-trip conserve under SKEWED Balancer weights?

Open math (do_open_short) is pure constant-product: solve_collateral / solve_phi
ignore pool weights. The self-cover buyback K routes through the weight-aware engine
get_quote_needed_for_base:  K = T * ((A/(A-Q))^(w1/w2) - 1),  fee grossed up.

Baseline (w1=w2=0.5) gave K0 == N exactly (open+instant self-close returns floor P).
Here we sweep the weight ratio r = w1/w2 (= spot price when reserves are equal) and
measure trader profit = N - K on an immediate full self-close (no move, no decay):

  profit > 0  ->  pool LOSES N-K, trader MINTS it: open+self-close is a value leak.
  profit <= 0 ->  trader pays a premium (safe).

w1 = base/Alpha weight, w2 = quote/TAO weight, w in [0.01,0.99] => r in [~0.0102, ~98].
"""
from decimal import Decimal, getcontext
getcontext().prec = 60
D = Decimal

def solve_collateral(P, T_ref, S, lam):
    a = lam*lam/T_ref
    b = D(1) - lam + (D(2)*lam*S/T_ref)
    disc = b*b + D(4)*a*P
    C = (disc.sqrt() - b)/(D(2)*a)
    N = C - P
    return (C, N) if (N > 0 and C > 0) else (None, None)

def solve_phi(N, T):
    frac = D(4)*N/T
    if frac > 1:
        return None
    return (D(1) - (D(1)-frac).sqrt())/D(2)

def weighted_buyback(T, A, Q, r, fee):
    """K = T*((A/(A-Q))**r - 1), fee on input. r = w1/w2. Decimal**Decimal via float exp."""
    ratio = A/(A-Q)                       # > 1
    powed = D(float(ratio) ** float(r))   # ratio**r
    base = T*(powed - D(1))
    return base/(D(1)-fee)

def roundtrip(P, T, A, lam, r, fee):
    C, N = solve_collateral(P, T, D(0), lam)      # t_ref = T (warm EMA == live)
    if N is None:
        return None
    phi = solve_phi(N, T)
    if phi is None:
        return None
    N_tao = N
    E = phi*T
    Q = phi*A
    Tp = T - N_tao - E          # pool TAO after open (alpha unchanged on short open)
    if Tp <= 0 or Q >= A or Q <= 0:
        return None
    K = weighted_buyback(Tp, A, Q, r, fee)
    claim = P + N_tao
    profit = N_tao - K          # returned - P
    underwater = K > claim
    return dict(N=N_tao, K=K, profit=profit, underwater=underwater)

TAO = D(1)
P   = D(1000)
T   = D(1_000_000)
A   = D(1_000_000)             # equal reserves => spot price r = w1/w2
lam = D("0.5")

print(f"Pool T=A={int(T):,} TAO, P={int(P)} TAO, lambda={lam}")
print(f"{'r=w1/w2':>9} {'spot':>6} {'N (TAO)':>12} {'K nofee':>14} {'profit_nofee':>14} {'profit_fee(0.05%)':>18} {'flag':>8}")
leak_nofee = []
for r in ["0.1","0.2","0.333","0.5","0.7","0.8","0.9","0.99","1.0","1.01","1.1","1.25","1.6","2.0","3.0","10.0"]:
    rr = D(r)
    a = roundtrip(P, T, A, lam, rr, D(0))
    b = roundtrip(P, T, A, lam, rr, D("0.0005"))
    if not a:
        print(f"{r:>9}  domain-reject"); continue
    flag = "LEAK" if a['profit'] > 0 else "safe"
    if a['profit'] > 0:
        leak_nofee.append((r, a['profit']))
    print(f"{r:>9} {r:>6} {float(a['N']):>12.4f} {float(a['K']):>14.4f} "
          f"{float(a['profit']):>14.6f} {float(b['profit']):>18.6f} {flag:>8}"
          + ("  underwater" if a['underwater'] else ""))

print()
if leak_nofee:
    print("RESULT: open+instant-self-close is PROFITABLE (pool loses) at weight ratios r<1:")
    for r, p in leak_nofee:
        print(f"   r={r}: trader mints ~{float(p):.4f} TAO per {int(P)}-TAO open (no move, no decay)")
    print("   => the 'covered' invariant for the SELF-COVER path breaks under skewed weights.")
    print("   NOTE: magnitude scales with position size; verify against the real engine + underwater guard.")
else:
    print("RESULT: no leak in sweep (profit<=0 everywhere) — self-cover stays covered under weights.")
