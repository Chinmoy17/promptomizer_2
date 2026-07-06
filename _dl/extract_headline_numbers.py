"""Extract headline numbers from simple_fdpo run metrics.json for the report."""
import json
import glob
import os

runs = sorted(glob.glob("results/smoke/*_simple_fdpo_gpt-4o-mini_s*"))
runs = [r for r in runs if os.path.isdir(r)]

print(f"{'run':<70} {'seed_test':>10} {'final_test':>10} {'delta':>8}  net")
print("-" * 110)
for r in runs:
    mpath = os.path.join(r, "metrics.json")
    if not os.path.exists(mpath):
        continue
    m = json.load(open(mpath, encoding="utf-8"))
    seed = m.get("seed_test", {}).get("accuracy", None)
    final = m.get("final_test", {}).get("accuracy", None)
    net = m.get("optimization", {}).get("test_confusion", {}).get("net_gain")
    rec = len(m.get("optimization", {}).get("test_confusion", {}).get("recoveries", []))
    reg = len(m.get("optimization", {}).get("test_confusion", {}).get("regressions", []))
    if seed is None or final is None:
        continue
    delta = final - seed
    name = os.path.basename(r)
    print(f"{name:<70} {seed:>10.4f} {final:>10.4f} {delta:>+8.4f}  +{rec}/-{reg} net={net}")
