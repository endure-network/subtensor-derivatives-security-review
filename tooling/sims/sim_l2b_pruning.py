"""L2b pruning sabotage: can a short force a target subnet's deregistration? Settle the numbers.

`get_network_to_prune` (root.rs:598) deregisters the NON-IMMUNE subnet with the lowest `get_moving_alpha_price`
(pEMA) when the network is at capacity (128) and someone registers a new subnet. A sustained short depresses a
target's spot -> pEMA, but the kappa cap bounds the depression. So the attacker can only REDIRECT the prune among
subnets already within that bound of the current min -- it cannot prune a healthy subnet (proven in the harness:
poc_pruning_sabotage_redirect, where a 10x-min subnet is unreachable), and it is pure griefing (no profit).

Defaults: kappa=0.05, lambda=0.5, dmax=0.015/day, blocks/day 7200, immunity 1_296_000 blocks (~180d),
prune-min pEMA ~0.0033 (finney), EMA half-life ~8h (a sustained move settles in ~1 day).
"""
from decimal import Decimal as D, getcontext
getcontext().prec = 50

def solve_phi(N, T):
    frac = D(4) * N / T
    return None if frac > 1 else (D(1) - (D(1) - frac).sqrt()) / D(2)

KAPPA, LAM, DMAX, BPD = D("0.05"), D("0.5"), D("0.015"), D(7200)

def max_depression(T):
    # Max spot drop at the cap (footprint B = lambda*C = kappa*T_ref): depr = (N+E)/T. Scale-free in T.
    C = KAPPA * T / LAM
    a = LAM * LAM / T
    b = D(1) - LAM
    P = a * C * C + b * C
    N = C - P
    phi = solve_phi(N, T)
    if phi is None:
        return None, None
    E = phi * T
    return (N + E) / T, N  # (depression fraction, retained proceeds N for the carry estimate)

print(f"{'reserve T':>10} {'max_depr':>9} {'reach window':>13} {'carry/day':>12}")
for T in [D(5000), D(26278), D(100000), D(203942)]:
    depr, N = max_depression(T)
    if depr is None:
        print(f"{float(T):>10.0f}  domain reject"); continue
    window = D(1) / (D(1) - depr) - D(1)   # target must sit within this fraction ABOVE the current min
    carry_day = DMAX * N                    # buffer R ~ N decays at dmax (u=1 at the cap), per day
    print(f"{float(T):>10.0f} {float(depr)*100:>8.2f}% {'+'+format(float(window)*100,'.2f')+'%':>13} {float(carry_day):>10.2f} TAO")

print("\nVerdict — the kappa=0.05 cap bounds the spot/pEMA depression to ~9.75%, so a short can only push a target")
print("below the prune-min if the target is ALREADY within ~10.8% above it (the bottom cluster). It CANNOT prune a")
print("healthy mid/top subnet (a 10x-min subnet is unreachable; proven in poc_pruning_sabotage_redirect). The cost is")
print("sustained carry (a few-to-tens of TAO/day, held ~1 day for the EMA to settle) until a registration fires, and")
print("it is pure GRIEFING (no attacker profit) -- or self-protection via the long mirror (pump your own near-min")
print("subnet out of the prune slot, pushing it onto the next-lowest). Immunity (~180d) protects new subnets; the")
print("victim was already a prune candidate; shorts are OFF (pre-launch). => L2b: LOW-MEDIUM, niche/bounded sabotage.")
