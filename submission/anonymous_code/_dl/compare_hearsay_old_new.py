"""Ad-hoc: compare old (single-pass) vs new (multi-round rescue) hearsay runs."""
import json
import glob
import os

fields = ("run", "seed_test", "base_train", "cur_train",
          "train_rec", "train_reg", "train_net", "test_delta")
header = "  ".join(f"{f:>10}" for f in fields[1:])
print(f"{'run':<70} {header}")

for pattern in ("results/smoke/legalbench_hearsay_simple_fdpo_gpt-4o-mini_s*_20260706-1618*",
                "results/smoke/legalbench_hearsay_simple_fdpo_gpt-4o-mini_s*_20260706-1619*",
                "results/smoke/legalbench_hearsay_simple_fdpo_gpt-4o-mini_s*_20260706-1633*",
                "results/smoke/legalbench_hearsay_simple_fdpo_gpt-4o-mini_s*_20260709-*"):
    for r in sorted(glob.glob(pattern)):
        m = json.load(open(f"{r}/metrics.json", encoding="utf-8"))
        seed_t = m["seed_test"]["accuracy"]
        final_t = m["final_test"]["accuracy"]
        opt = m["optimization"]
        tr = opt.get("train_confusion", {})
        name = os.path.basename(r)
        vals = (
            f"{seed_t:>10.3f}",
            f"{opt['baseline_train']['accuracy']:>10.3f}",
            f"{opt['current_train']['accuracy']:>10.3f}",
            f"{len(tr.get('recoveries', [])):>10}",
            f"{len(tr.get('regressions', [])):>10}",
            f"{tr.get('net_gain', 0):>+10}",
            f"{final_t - seed_t:>+10.3f}",
        )
        print(f"{name[:70]:<70} {'  '.join(vals)}")
