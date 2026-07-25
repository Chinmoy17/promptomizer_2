"""Aggregate the one-liner -> FDPO runs for the report."""
import glob
import json
import os

RUNS = {
    "hearsay": sorted(glob.glob("results/smoke/legalbench_hearsay_simple_fdpo_gpt-4o-mini_s*_20260725-231*")),
    "gsm8k": sorted(glob.glob("results/smoke/gsm8k_simple_fdpo_gpt-4o-mini_s*_20260725-23*")),
}


def summarize(run):
    m = json.load(open(os.path.join(run, "metrics.json"), encoding="utf-8"))
    opt = m["optimization"]
    seed_t = m["seed_test"]["accuracy"]
    final_t = m["final_test"]["accuracy"]
    tc = opt.get("test_confusion", {})
    reverted = opt["baseline_train"]["accuracy"] == opt["current_train"]["accuracy"] \
        and len(opt["train_confusion"]["recoveries"]) == 0 \
        and len(opt["train_confusion"]["regressions"]) == 0
    return {
        "run": os.path.basename(run),
        "seed": m["seed"],
        "seed_test": seed_t,
        "final_test": final_t,
        "delta": final_t - seed_t,
        "baseline_train_wrong": opt["baseline_train"]["n_wrong"],
        "baseline_failing_ids": opt.get("baseline_failing_ids", []),
        "rounds": opt.get("rounds_log", []),
        "test_rec": tc.get("recoveries", []),
        "test_reg": tc.get("regressions", []),
        "test_net": tc.get("net_gain"),
        "reverted_to_baseline": reverted,
        "final_train_wrong": opt["current_train"]["n_wrong"],
        "opt_temp": opt.get("optimizer_temperature", "?"),
        "solver_temp": opt.get("solver_temperature", "?"),
    }


for ds, runs in RUNS.items():
    print(f"\n{'='*80}\n{ds.upper()}\n{'='*80}")
    for run in runs:
        s = summarize(run)
        print(f"\n--- seed {s['seed']}  ({s['run']}) ---")
        print(f"  TEST: {s['seed_test']:.3f} -> {s['final_test']:.3f}  (delta {s['delta']:+.3f})")
        print(f"  baseline train wrong: {s['baseline_train_wrong']}  ->  final train wrong: {s['final_train_wrong']}")
        print(f"  reverted to baseline prompt: {s['reverted_to_baseline']}")
        print(f"  TEST confusion: recovered {len(s['test_rec'])}, regressed {len(s['test_reg'])}, net {s['test_net']:+d}")
        if s["test_reg"]:
            print(f"    REGRESSED test ids: {s['test_reg']}")
        print(f"  temps: solver={s['solver_temp']} optimizer={s['opt_temp']}")
        print(f"  per-round:")
        for r in s["rounds"]:
            rec = r.get("recovered_this_round", [])
            reg = r.get("regressed_this_round", [])
            print(f"    R{r['round']} [{r['status']}]: |F| {r.get('n_failures_before')}->{r.get('n_failures_after', '-')}"
                  f"  train_acc {r.get('train_acc_after')}  changed={r.get('sections_changed')}"
                  f"  +{len(rec)}/-{len(reg)}")
