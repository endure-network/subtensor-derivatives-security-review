"""L2 quantification: pull finney emission params (EMA price + half-life) to size the
emission-redirection (L2a) and pruning-sabotage (L2b) economics.

Share ∝ root_prop·priceEMA·(1−miner_burned); first-pass here approximates share ∝ priceEMA
(the dominant term). Repro of the channel: a short ↓SubnetTAO ↓spot ↓priceEMA (over the half-life)
↓share ↓emission, redirected to other subnets / toward the prune-min.
"""
import sys
from substrateinterface import SubstrateInterface

sub = SubstrateInterface(url="wss://entrypoint-finney.opentensor.ai:443")
print("connected; block:", sub.get_block_number(sub.get_chain_head()))

def i96f32(v):
    if isinstance(v, dict):
        v = v.get("bits", next(iter(v.values())))
    return float(v) / (2**32)

prices, halving = {}, {}
for k, v in sub.query_map("SubtensorModule", "SubnetMovingPrice", max_results=1024, page_size=200):
    prices[int(getattr(k, "value", k))] = i96f32(getattr(v, "value", v))
try:
    for k, v in sub.query_map("SubtensorModule", "EMAPriceHalvingBlocks", max_results=1024, page_size=200):
        halving[int(getattr(k, "value", k))] = int(getattr(v, "value", v))
except Exception as e:
    print("halving query err:", repr(e)[:120])

prices = {n: p for n, p in prices.items() if p > 0}
total = sum(prices.values())
shares = {n: p / total for n, p in prices.items()} if total else {}
BE, BLOCKS_DAY = 0.5, 7200  # ~0.5 TAO/block post-halving

print(f"\nsubnets with price>0: {len(prices)} | Σprice={total:.4f}")
print(f"{'net':>4} {'priceEMA':>10} {'share%':>8} {'emit TAO/day':>13} {'half-life(blk/d)':>16}")
top = sorted(shares.items(), key=lambda x: -x[1])[:12]
for n, s in top:
    hl = halving.get(n)
    print(f"{n:>4} {prices[n]:>10.5f} {s*100:>7.3f}% {s*BE*BLOCKS_DAY:>13.2f} {str(hl)+' / '+(f'{hl/7200:.1f}' if hl else '?'):>16}")

print("\n=== L2a sensitivity: depress one subnet's EMA by δ → TAO/day redirected away from it (first-order) ===")
for n, _ in top[:3]:
    for d in (0.10, 0.50, 0.90):
        p2 = dict(prices); p2[n] = prices[n] * (1 - d)
        t2 = sum(p2.values()); s2 = p2[n] / t2
        redirected = (shares[n] - s2) * BE * BLOCKS_DAY
        hl = halving.get(n) or 0
        print(f"  net {n:>3}: -{int(d*100):>2}% EMA → share {shares[n]*100:6.3f}%→{s2*100:6.3f}% → ~{redirected:8.2f} TAO/day redirected "
              f"(EMA half-life ~{hl/7200:.1f}d ⇒ a sustained short needs ~that long to fully bite)")

print("\n=== L2b: current prune candidate = lowest priceEMA among non-immune subnets ===")
lo = sorted(prices.items(), key=lambda x: x[1])[:5]
print("  lowest-priceEMA subnets (prune order, ignoring immunity):", [(n, round(p, 6)) for n, p in lo])
print("  ⇒ to force-prune a target, a short must push its EMA below the current min and hold until prune fires.")
