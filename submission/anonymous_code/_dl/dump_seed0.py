import json

print("===== HEARSAY SEED 0: FINAL ENRICHED PROMPT (built from the one-liner) =====")
print(open("results/smoke/legalbench_hearsay_simple_fdpo_gpt-4o-mini_s0_20260725-231519/prompt_current.md",
           encoding="utf-8").read())
print()

test = {json.loads(l)["id"]: json.loads(l)
        for l in open("Dataset/legalbench_hearsay/test.jsonl", encoding="utf-8")}
train = {json.loads(l)["id"]: json.loads(l)
         for l in open("Dataset/legalbench_hearsay/train.jsonl", encoding="utf-8")}
lk = {**test, **train}

print("===== REGRESSED test examples (hearsay seed 0: right at baseline, wrong after) =====")
for tid in ("hearsay_test_43", "hearsay_test_80"):
    ex = lk.get(tid, {})
    print(f"[{tid}] gold={ex.get('gold')} slice={ex.get('meta', {}).get('slice')}")
    print("   " + ex.get("question", "")[:280].replace("\n", " "))
    print()
