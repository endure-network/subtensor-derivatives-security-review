"""Probe finney (mainnet) for per-subnet Balancer weights → real skew → leak fraction.

FINDING-01 leak = N*(1 - w1/w2) on the matching side (short if w1/w2<1, long if >1).
w1=base/Alpha weight, w2=quote/TAO weight; pool stores quote weight (Perquintill, /1e18).
"""
import sys, statistics

def main():
    try:
        from substrateinterface import SubstrateInterface
    except Exception as e:
        print("IMPORT_FAIL", repr(e)[:200]); return 2

    urls = [
        "wss://entrypoint-finney.opentensor.ai:443",
        "wss://lite.sub.latent.to:443",
        "wss://archive.chain.opentensor.ai:443",
    ]
    sub = None
    for url in urls:
        try:
            sub = SubstrateInterface(url=url)
            print("CONNECTED:", url)
            break
        except Exception as e:
            print("CONNECT_FAIL:", url, repr(e)[:160])
    if sub is None:
        print("NO_CONNECTION"); return 3

    try:
        print("chain:", sub.chain, "| spec_version:", sub.runtime_version)
    except Exception as e:
        print("ver-err", repr(e)[:120])

    funcs = None
    try:
        funcs = sub.get_metadata_storage_functions()
        bal = sorted({(f['module_id'], f['storage_name']) for f in funcs
                      if 'balancer' in f['storage_name'].lower()})
        v3 = sorted({(f['module_id'], f['storage_name']) for f in funcs
                     if 'sqrtprice' in f['storage_name'].lower()})
        swapmods = sorted({f['module_id'] for f in funcs if 'swap' in f['module_id'].lower()})
        print("balancer storage:", bal)
        print("v3 sqrtprice storage:", v3)
        print("swap-ish pallets:", swapmods)
    except Exception as e:
        print("storage-fn-err", repr(e)[:200])

    target = None
    if funcs:
        for f in funcs:
            if f['storage_name'] == 'SwapBalancer':
                target = f['module_id']; break
    if target is None:
        for cand in ["SubtensorSwap", "Swap", "Pal", "SubtensorModule"]:
            try:
                sub.query_map(cand, "SwapBalancer", max_results=1)
                target = cand; break
            except Exception:
                pass
    if target is None:
        print("NO_SWAPBALANCER_STORAGE — balancer not on this runtime (so no skew source yet)")
        return 0

    print("querying", target, "SwapBalancer ...")
    rows = []
    try:
        for k, v in sub.query_map(target, "SwapBalancer", max_results=1024, page_size=200):
            netuid = int(getattr(k, "value", k))
            val = getattr(v, "value", v)
            rows.append((netuid, val))
    except Exception as e:
        print("query_map-err", repr(e)[:200]); return 4

    print(f"got {len(rows)} subnet balancer entries")
    ACC = 10**18
    out = []
    for netuid, val in rows:
        q = val
        if isinstance(q, dict):
            q = q.get('quote', q.get('Quote', next(iter(q.values()))))
        if isinstance(q, dict):
            q = next(iter(q.values()))
        try:
            wq = float(q) / ACC
        except Exception:
            continue
        if not (0.0 < wq < 1.0):
            continue
        r = (1.0 - wq) / wq            # w1/w2
        leak = max(1.0 - r, 1.0 - 1.0 / r) if r > 0 else 0.0
        out.append((netuid, wq, r, leak))

    out.sort(key=lambda x: -x[3])
    print("\nnetuid  w_quote   w1/w2    leak%(matching side)")
    for netuid, wq, r, leak in out[:30]:
        print(f"{netuid:>5}  {wq:.5f}  {r:.5f}  {leak*100:7.3f}%")
    if out:
        leaks = [o[3] for o in out]
        devs = [abs(o[1] - 0.5) for o in out]
        near = sum(1 for d in devs if d < 0.001)
        print(f"\nN={len(out)} subnets")
        print(f"median |w_quote-0.5| = {statistics.median(devs):.4f}  (0 = exactly balanced)")
        print(f"median leak = {statistics.median(leaks)*100:.3f}%  |  mean leak = {statistics.mean(leaks)*100:.3f}%  |  max leak = {max(leaks)*100:.3f}%")
        print(f"subnets within 0.001 of 0.5 (≈ no leak): {near}/{len(out)}")
        print(f"subnets with leak >= 1%:  {sum(1 for l in leaks if l>=0.01)}/{len(out)}")
        print(f"subnets with leak >= 5%:  {sum(1 for l in leaks if l>=0.05)}/{len(out)}")
    return 0

sys.exit(main())
