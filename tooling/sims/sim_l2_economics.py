"""L2a economics: is emission-redirection profitable? Settle by running the numbers.

The capacity cap bounds the max short (footprint B=λC ≤ κ·T_ref), hence the max price depression,
hence the emission it can redirect. Compare (best-case, no-arbitrage, attacker-captures-all) redirected
emission vs the short's CARRY cost (buffer R decays at d(u); at the cap u=1 ⇒ d=dmax).

Defaults: κ=0.05, λ=0.5, dmax=0.015/day, block emission 0.5 TAO, 7200 blocks/day, Σ(priceEMA)=1.39 (finney).
Share ∝ priceEMA (first-pass; root_prop·(1−burned) only reduces it further).
"""
from decimal import Decimal as D, getcontext
getcontext().prec = 50

def solve_phi(N, T):
    frac = D(4) * N / T
    return None if frac > 1 else (D(1) - (D(1) - frac).sqrt()) / D(2)

KAPPA, LAM, DMAX = D("0.05"), D("0.5"), D("0.015")
BE, BPD, SUM_P = D("0.5"), D(7200), D("1.39")

# finney subnets (T,A in TAO/alpha): big, mid, small-price (from probes)
subs = [("net64 (top)", D(203942), D(2674207)),
        ("net4  (mid)", D(130125), D(2441202)),
        ("net1  (low-price)", D(26278), D(3009493)),
        ("net120", D(77618), D(1386658))]

print(f"{'subnet':>18} {'price':>8} {'maxShort B':>12} {'removal/T':>9} {'redir TAO/day':>13} {'carry TAO/day':>13} {'redir/carry':>11}")
for label, T, A in subs:
    price = T / A
    # max short at the cap: B = λC = κ·T_ref ⇒ C = κ·T/λ ; invert solve_collateral (S=0): P = a·C² + b·C
    C = KAPPA * T / LAM
    a = LAM * LAM / T
    b = D(1) - LAM
    P = a * C * C + b * C
    N = C - P
    phi = solve_phi(N, T)
    if phi is None:
        print(f"{label:>18}  domain reject"); continue
    E = phi * T
    removal = N + E
    depr = removal / T                      # spot drops by this fraction
    # EMA (after it settles, ~1 day at ~8h half-life) tracks the depressed spot:
    p2 = (T - removal) / A
    redirected_day = ((price / SUM_P) - (p2 / (SUM_P - price + p2))) * BE * BPD
    carry_day = DMAX * N                    # buffer R≈N decays at dmax (u=1 at the cap)
    ratio = redirected_day / carry_day if carry_day > 0 else D(0)
    print(f"{label:>18} {float(price):>8.4f} {float(C*LAM):>12.0f} {float(depr):>9.4f} "
          f"{float(redirected_day):>13.2f} {float(carry_day):>13.2f} {float(ratio):>11.3f}")

print("\nredir/carry < 1 ⇒ even the BEST case (no arbitrage, attacker captures 100% of redirected emission,")
print("ignoring the locked floor P and the close spread) loses money to carry alone. The κ cap (max ~10% depression)")
print("+ the decay/carry mechanism throttle L2a. Real attacker captures only a fraction ⇒ L2a infeasible.")
