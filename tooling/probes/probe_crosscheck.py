"""Cross-check the all-0.5 result: print RAW SwapBalancer quote parts + verify
price == (w1/w2)*(TAO/Alpha) for a sample of subnets. If w=0.5, spot should == TAO/Alpha."""
import sys
from substrateinterface import SubstrateInterface

sub = SubstrateInterface(url="wss://entrypoint-finney.opentensor.ai:443")
print("connected; block:", sub.get_block_number(sub.get_chain_head()))

sample = [1, 3, 4, 8, 9, 12, 19, 23, 56, 64, 100, 128]
print(f"{'net':>4} {'raw_quote':>20} {'w_quote':>8} {'SubnetTAO':>18} {'SubnetAlphaIn':>18} {'T/A':>10} {'MovingPrice':>12}")
nonhalf = 0
for n in sample:
    try:
        b = sub.query("Swap", "SwapBalancer", [n]).value
        tao = int(sub.query("SubtensorModule", "SubnetTAO", [n]).value)
        alp = int(sub.query("SubtensorModule", "SubnetAlphaIn", [n]).value)
        mp = sub.query("SubtensorModule", "SubnetMovingPrice", [n]).value
    except Exception as e:
        print(f"{n:>4}  ERR {repr(e)[:80]}"); continue
    q = b.get("quote", b) if isinstance(b, dict) else b
    if isinstance(q, dict):
        q = next(iter(q.values()))
    wq = float(q) / 1e18
    if abs(wq - 0.5) > 1e-9:
        nonhalf += 1
    ratio = tao / alp if alp else 0.0
    try:
        mpf = float(mp) / (2**32) if isinstance(mp, int) and mp > 2**20 else float(mp)
    except Exception:
        mpf = mp
    print(f"{n:>4} {str(q):>20} {wq:>8.5f} {tao:>18} {alp:>18} {ratio:>10.5f} {str(mpf):>12}")

print(f"\nsubnets in sample with w_quote != 0.5: {nonhalf}/{len(sample)}")
print("If all w=0.5 AND spot(=T/A) tracks MovingPrice, the all-0.5 read is correct => no skew on mainnet.")
