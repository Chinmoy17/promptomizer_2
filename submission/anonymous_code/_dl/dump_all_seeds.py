import json
import os

RUNS = {
    "seed 0": "results/smoke/legalbench_hearsay_simple_fdpo_gpt-4o-mini_s0_20260725-231519",
    "seed 1": "results/smoke/legalbench_hearsay_simple_fdpo_gpt-4o-mini_s1_20260725-231640",
    "seed 2": "results/smoke/legalbench_hearsay_simple_fdpo_gpt-4o-mini_s2_20260725-231801",
}
SCHEMA = ["system_role", "context", "task_details", "constraints", "output_format"]
TITLES = {"system_role": "System Role", "context": "Context",
          "task_details": "Task Details", "constraints": "Constraints",
          "output_format": "Output Format"}


def reverted(m):
    opt = m["optimization"]
    return (opt["baseline_train"]["accuracy"] == opt["current_train"]["accuracy"]
            and not opt["train_confusion"]["recoveries"]
            and not opt["train_confusion"]["regressions"])


for label, run in RUNS.items():
    m = json.load(open(os.path.join(run, "metrics.json"), encoding="utf-8"))
    rev = reverted(m)
    seed_t = m["seed_test"]["accuracy"]
    final_t = m["final_test"]["accuracy"]
    print("=" * 90)
    print(f"{label.upper()}   TEST {seed_t:.3f} -> {final_t:.3f} ({final_t-seed_t:+.3f})   "
          f"FINAL PROMPT = {'REVERTED to one-liner baseline' if rev else 'ENRICHED (a round won)'}")
    print("=" * 90)
    pc = os.path.join(run, "prompt_current.md")
    print("---- FINAL ACTIVE PROMPT (what was actually used for the final test) ----")
    print(open(pc, encoding="utf-8").read().rstrip())
    if rev:
        # Show what the optimizer PRODUCED but was NOT kept (last round version).
        reg = json.load(open(os.path.join(run, "registry.json"), encoding="utf-8"))
        print("\n---- what the optimizer TRIED this run (last round, discarded by keep-best) ----")
        for sec in SCHEMA:
            v = reg["sections"][sec]["versions"]
            if len(v) > 1:
                print(f"## {TITLES[sec]}\n{v[-1]['text'][:500]}\n")
    print()
